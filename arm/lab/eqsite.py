"""個股報告與產業報告建頁（docs/lab_equity_report_plan.md 第 8、11 節）。

reports/eq/{tw|us}/{代號}/{報告日}.md（＋同名 .facts.json）每家取最新一版 → dashboard/rp/{tw|us}-{代號}.html；
舊版變成「評等歷史」。reports/eq/ind/{產業代號}/{日期}.md → dashboard/rp/ind-{產業代號}.html。
頁首「最新收盤」每次建頁更新（台股讀 dashboard/x9t.json），報告本文與資料包不動。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import eqpage as P
from . import eqreport as R

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "reports" / "eq"
OUT = ROOT / "dashboard" / "rp"


def _versions(d: Path) -> list[tuple[str, Path, Path]]:
    out = []
    for md in sorted(d.glob("*.md")):
        fp = md.with_suffix(".facts.json")
        if fp.exists():
            out.append((md.stem, md, fp))
    return out


def companies(src: Path = SRC) -> dict:
    """{(mk, 代號): [(報告日, md, facts)…]}（舊到新）。"""
    out = {}
    for mk in ("tw", "us"):
        for d in sorted((src / mk).glob("*")) if (src / mk).exists() else []:
            v = _versions(d)
            if v:
                out[(mk, d.name)] = v
    return out


def industries(src: Path = SRC) -> dict:
    out = {}
    for d in sorted((src / "ind").glob("*")) if (src / "ind").exists() else []:
        v = _versions(d)
        if v:
            out[d.name] = v
    return out


def live_prices() -> dict:
    """最新收盤：台股讀 dashboard/x9t.json；美股讀 data/lab/ussx_card.json（選股頁美股那幾檔，每天收盤後更新）。"""
    t = json.loads((ROOT / "dashboard" / "x9t.json").read_text(encoding="utf-8")) if (ROOT / "dashboard" / "x9t.json").exists() else {}
    cols = t.get("cols") or []
    i = cols.index("px") if "px" in cols else None
    out = {("tw", c): {"px": r[i], "d": t.get("d")} for c, r in (t.get("rows") or {}).items() if i is not None and r and r[i]}
    cp = ROOT / "data" / "lab" / "ussx_card.json"
    try:
        card = json.loads(cp.read_text(encoding="utf-8")) if cp.exists() else {}
    except ValueError:
        card = {}
    cal = card.get("cal") or []
    for c, s in (card.get("s") or {}).items():
        cs = s.get("c") or []
        if cs and cal and cs[-1]:
            out[("us", c)] = {"px": cs[-1], "d": cal[len(cs) - 1] if len(cs) <= len(cal) else cal[-1]}
    return out


def _load(md: Path, fp: Path) -> tuple[str, dict]:
    return md.read_text(encoding="utf-8"), json.loads(fp.read_text(encoding="utf-8"))


def summary(mk: str, code: str, vers: list, live: dict) -> dict:
    """清單、評等歷史用：最新一版的評等、目標價、報告日收盤、最新收盤。"""
    text, pack = _load(vers[-1][1], vers[-1][2])
    fm = R.parse(text)["fm"]
    val = R.valuation(pack, fm)
    lp = live.get((mk, code)) or {}
    return {"mk": mk, "code": code, "name": pack.get("name"), "made": vers[-1][0], "rating": val.get("rating"), "tp": val.get("tp"),
            "px": val.get("px"), "live": lp.get("px"), "live_d": lp.get("d"), "ind": fm.get("ind"), "title": fm.get("title"),
            "href": f"rp/{mk}-{code}.html", "industry": pack.get("ind")}


def links(src: Path = SRC) -> dict:
    """個股卡、公司卡、美股個股卡最上面的「個股報告」一行：{"tw:4958": [最新報告日, 評等]}。只讀最新一版的開頭欄位
    （評等由檢查保證等於規則算出來的）；不寫目標價（「目標價」只准出現在報告頁與研究紀錄頁的報告清單，wiki/ops/content-rules.md）。"""
    out = {}
    for (mk, code), vers in companies(src).items():
        fm = R.parse(vers[-1][1].read_text(encoding="utf-8"))["fm"]
        out[f"{mk}:{code}"] = [vers[-1][0], str(fm.get("rating") or "")]
    return out


def research_body(src: Path = SRC) -> str:
    """研究紀錄頁「個股報告」段：每家最新一版一列（新到舊）＋產業報告清單。網址相對於 dashboard/（x9r.html 所在）。"""
    live = live_prices()
    rows = sorted((summary(mk, c, v, live) for (mk, c), v in companies(src).items()), key=lambda r: (r["made"], r["code"]), reverse=True)
    inds = []
    for key, vers in industries(src).items():
        ip = json.loads(vers[-1][2].read_text(encoding="utf-8"))
        inds.append({"key": key, "name": ip.get("name") or key, "made": vers[-1][0], "n": ip.get("n_members")})
    if not rows and not inds:
        return '<p class="rnote">還沒有報告。</p>'
    iname = {i["key"]: i["name"] for i in inds}
    e = P.escape
    out = []
    if rows:
        body = []
        for r in rows:
            now = r.get("live") or r.get("px")
            gap = round((r["tp"] / now - 1) * 100, 1) if r.get("tp") and now else None
            ind = str(r.get("ind") or "")
            icell = f'<a href="rp/ind-{e(ind)}.html">{e(iname[ind])}</a>' if ind in iname else e(r.get("industry") or "")
            body.append(
                f'<tr><td class="l"><a href="{e(r["href"])}">{e(r["name"])}</a> <span class="eqc">{e(r["code"])}</span></td>'
                f'<td><b class="eqr-{P.RATING_CLS.get(r["rating"], "rx")}">{e(r["rating"])}</b></td><td>{P.f(r["tp"], 0)}</td>'
                f'<td>{e(r["made"])}</td><td>{P.f(r["px"])}</td><td>{P.f(r.get("live"))}</td><td>{P.sg(gap)}</td>'
                f'<td class="l">{icell}</td></tr>')
        out.append('<div class="eqlw"><table class="eqlt"><thead><tr><th class="l">公司</th><th>評等</th><th>目標價（元）</th><th>報告日</th>'
                   '<th>報告日收盤</th><th>最新收盤</th><th>最新收盤到目標價</th><th class="l">產業</th></tr></thead><tbody>'
                   + "".join(body) + '</tbody></table></div>')
    if inds:
        out.append('<ul class="rlist">' + "".join(
            f'<li><a href="rp/ind-{e(i["key"])}.html">產業報告・{e(i["name"])}</a><span>{e(i["made"])}；台灣上市櫃成員 {P.f(i["n"], 0)} 家</span></li>'
            for i in inds) + '</ul>')
    return "".join(out)


CSS = """
.eqlw{overflow-x:auto;margin:4px 0 12px}
.eqlt{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums;white-space:nowrap}
.eqlt th,.eqlt td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right}
.eqlt th{font-size:12.5px;color:var(--mut);font-weight:600}.eqlt .l{text-align:left}
.eqlt .eqc{color:var(--mut);font-size:12px}
.eqlt .eqr-rb{color:var(--up,#c0392b)}.eqlt .eqr-rs{color:var(--dn,#1e8449)}
"""


def _write(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def build(out: Path = OUT, src: Path = SRC) -> dict:
    live = live_prices()
    cos = companies(src)
    inds = industries(src)
    ind_meta = {}
    for key, vers in inds.items():
        text, ip = _load(vers[-1][1], vers[-1][2])
        ind_meta[key] = {"href": f"rp/ind-{key}.html", "name": ip.get("name"), "made": vers[-1][0]}
    rows, wrote, keep = [], 0, set()
    for (mk, code), vers in cos.items():
        text, pack = _load(vers[-1][1], vers[-1][2])
        hist = []
        lp = (live.get((mk, code)) or {}).get("px")
        for made, md, fp in vers:
            t2, p2 = _load(md, fp)
            v2 = R.valuation(p2, R.parse(t2)["fm"])
            hist.append({"made": made, "rating": v2.get("rating"), "tp": v2.get("tp"), "px": v2.get("px"), "spec": p2.get("spec"),
                         "since": round((lp / v2["px"] - 1) * 100, 1) if lp and v2.get("px") else None})
        fm = R.parse(text)["fm"]
        ctx = {"live": live.get((mk, code)), "hist": hist, "ind": ind_meta.get(str(fm.get("ind")))}
        name = f"{mk}-{code}.html"
        keep.add(name)
        wrote += _write(out / name, P.render(text, pack, ctx))
        rows.append(summary(mk, code, vers, live))
    for key, vers in inds.items():
        text, ip = _load(vers[-1][1], vers[-1][2])
        mine = [{"href": r["href"], "name": r["name"], "rating": r["rating"]} for r in rows if str(r.get("ind")) == key]
        name = f"ind-{key}.html"
        keep.add(name)
        wrote += _write(out / name, P.ind_render(text, ip, {"cos": mine}))
    for p in out.glob("*.html") if out.exists() else []:
        if p.name not in keep:
            p.unlink()
    return {"companies": rows, "industries": [{"key": k, **v} for k, v in ind_meta.items()], "wrote": wrote}
