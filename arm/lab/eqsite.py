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
    t = json.loads((ROOT / "dashboard" / "x9t.json").read_text(encoding="utf-8")) if (ROOT / "dashboard" / "x9t.json").exists() else {}
    cols = t.get("cols") or []
    i = cols.index("px") if "px" in cols else None
    return {("tw", c): {"px": r[i], "d": t.get("d")} for c, r in (t.get("rows") or {}).items() if i is not None and r and r[i]}


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
            hist.append({"made": made, "rating": v2.get("rating"), "tp": v2.get("tp"), "px": v2.get("px"),
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
