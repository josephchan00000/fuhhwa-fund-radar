"""台股財報季（規格 arm/lab/ernspec.py VER 1；docs/lab_earnings_plan.md 第 10 節）。只讀 repo 裡的資料、不連網。

  members()        → 清單：{代號: {"n": 名稱, "who": [[來源, 比重或 None], ...]}}（規格第 1 點）
  target(today)    → 這一季的季底（法定期限已過的最新一季）
  company(...)     → 一家的數字（規格第 3～7 點）
  build(today)     → data/lab/earn_tw.json 的內容（彙總、每家、每檔基金的持股）
  write(today)     → 寫檔（內容沒變不改寫）；scripts/gen_fund_dashboard.py 建選擇權頁之前叫
頁面在 arm/lab/earnpage.py（選擇權頁的「財報」分頁，只讀這支檔）。
"""
from __future__ import annotations

import glob
import json
import statistics as st
from datetime import date, timedelta
from pathlib import Path

from . import ernspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "earn_tw.json"
DASH = ROOT / "dashboard"
QEND = ("03-31", "06-30", "09-30", "12-31")


def _read(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _tw(code) -> str | None:
    """4 碼台股代號；00 開頭是 ETF，不算公司（VER 2）。"""
    c = str(code or "").strip().split(".")[0]
    return c if len(c) == 4 and c.isdigit() and not c.startswith("00") else None


def members(root: Path = ROOT) -> dict:
    """規格第 1 點：復華基金前十大＋自家 ETF 台股持股＋選股頁拿著的。"""
    out: dict[str, dict] = {}

    def add(c, name, who, w):
        o = out.setdefault(c, {"n": name, "who": []})
        if not o.get("n") and name:
            o["n"] = name
        if not any(x[0] == who for x in o["who"]):
            o["who"].append([who, w])
    prof = (_read(root / "config" / "holding_profiles.json", {}) or {}).get("profiles") or {}
    code_of = {nm: _tw(v.get("ticker")) for nm, v in prof.items()
               if isinstance(v, dict) and v.get("country") in ("台灣", "臺灣") and _tw(v.get("ticker"))}
    for p in sorted(glob.glob(str(root / "data" / "funds" / "*.json"))):
        f = _read(Path(p), {}) or {}
        who = f.get("short_name") or f.get("fund_id")
        for h in f.get("top_holdings") or []:
            c = code_of.get(h.get("name"))
            if c:
                add(c, h.get("name"), who, h.get("weight"))
    from .. import etfwatch
    eh = (_read(root / "data" / "etf_holdings.json", {}) or {}).get("etfs") or {}
    for row in etfwatch.WATCHLIST:
        if "復華" not in row[1]:
            continue
        for h in (eh.get(row[0]) or {}).get("holdings") or []:
            c = _tw(h.get("stock_id"))
            if c:
                add(c, h.get("name"), row[0], h.get("weight"))
    try:
        from .eqqueue import page_pick
        tw = page_pick((root / "dashboard" / "x9.html").read_text(encoding="utf-8")).get("tw") or {}
    except OSError:
        tw = {}
    names = tw.get("names") or {}
    for c, items in (tw.get("pos") or {}).items():
        if _tw(c):
            for it in items or []:
                add(c, None, "選股頁：" + names.get(it.get("k"), it.get("k") or ""), None)
    return out


def target(today: str) -> str:
    """法定期限已過的最新一季的季底。"""
    from .packtest import deadline
    y = int(today[:4])
    for yy in (y, y - 1):
        for qe in reversed(QEND):
            q = f"{yy}-{qe}"
            if q < today and deadline(q) <= today:
                return q
    return f"{y - 1}-12-31"


def _r(x, n=1):
    return None if x is None else round(x, n)


def _pc(a, b):
    return _r((a / b - 1) * 100) if a is not None and b and b > 0 else None


def company(code: str, co: dict, cons: dict, tq: str, px1m: float | None = None) -> dict:
    """一家（規格第 3～7 點）。co＝dashboard/co/{代號}.json；cons＝eqfacts.consensus 的結果。"""
    from .eqfacts import months, quarters
    qs = quarters(co)
    by = {q["q"]: q for q in qs}
    r = {"n": co.get("n"), "ind": co.get("ind"), "q": tq, "px1m": px1m}
    q = by.get(tq)
    if not q:
        last = qs[-1]["q"] if qs else None
        r.update({"in": False, "last": last})
        return r
    y, qn = int(tq[:4]), QEND.index(tq[5:]) + 1
    this = [by.get(f"{y}-{e}") for e in QEND[:qn]]
    ly = [by.get(f"{y - 1}-{e}") for e in QEND]
    lyq = ly[qn - 1]
    eps, note = q.get("eps"), None
    if eps is not None and q.get("nip") and eps * q["nip"] < 0 and all(x and x.get("eps") is not None and x.get("nip") is not None for x in this):
        cum_eps, cum_nip = sum(x["eps"] for x in this), sum(x["nip"] for x in this)
        if cum_nip:
            eps, note = _r(cum_eps * q["nip"] / cum_nip, 2), "股數有變，用淨利比例換算"
    eps_ly = (lyq or {}).get("eps")
    ni, ni_ly = q.get("nip"), (lyq or {}).get("nip")
    r.update({"in": True, "rev": q.get("rev"), "rev_yoy": q.get("rev_yoy"), "eps": eps, "eps_ly": eps_ly,
              "ni": ni, "ni_ly": ni_ly, "ni_yoy": _pc(ni, ni_ly), "eps_note": note, "gm": q.get("gm"), "om": q.get("om")})
    prev = by.get(f"{y}-{QEND[qn - 2]}") if qn > 1 else by.get(f"{y - 1}-12-31")
    r["gm_q"] = (prev or {}).get("gm")
    r["gm_ly"] = (lyq or {}).get("gm")
    r["om_q"] = (prev or {}).get("om")
    r["om_ly"] = (lyq or {}).get("om")
    i = qs.index(q)
    r["rev8"] = [[x["q"], x.get("rev_yoy")] for x in qs[max(0, i - 7):i + 1]]
    pv = (prev or {}).get("rev_yoy")
    r["decel"] = bool(q.get("rev_yoy") is not None and pv is not None and q["rev_yoy"] < pv - S.DECEL)
    r["mo3"] = [[m["ym"], m.get("rev_yoy")] for m in months(co)[-3:]]
    r["suspect"] = bool((q.get("rev_yoy") or 0) >= S.SUSPECT_REV and ni is not None and ni < 0 and (ni_ly or 0) > 0)
    # 全年預估（規格第 6 點）
    yc = ((cons or {}).get("eps") or {}).get(str(y)) or {}
    r["cons"] = {"v": yc.get("med"), "src": (cons or {}).get("src"), "d": (cons or {}).get("d"), "n": (cons or {}).get("n")}
    r["fy"] = full_year(yc.get("med"), eps, this, ly, qn, tq, (cons or {}).get("d"), ytd=sum(x["eps"] for x in this) if all(
        x and x.get("eps") is not None for x in this) else None)
    return r


def full_year(cv, eps, this, ly, qn, tq, cd, ytd=None) -> dict:
    """規格第 6 點；ytd＝公布的今年累計每股盈餘（各季相加；股數變了也是同一個基準）。"""
    if qn >= 4:
        return {"k": "na", "why": "第四季公布時全年已知"}
    if cv is None:
        return {"k": "na", "why": "沒有全年預估"}
    if ytd is None:
        return {"k": "na", "why": "今年有一季沒有資料"}
    need = cv - ytd
    rest = [x.get("eps") if x else None for x in ly[qn:]]
    same = (ly[qn - 1] or {}).get("eps")
    out = {"need": _r(need, 2), "ytd": _r(ytd, 2)}
    stale_d = (date.fromisoformat(tq) + timedelta(days=S.STALE_DAYS)).isoformat()
    out["stale"] = bool(cd and cd < stale_d)
    if any(x is None for x in rest) or same is None:
        return {**out, "k": "na", "why": "去年的季資料不齊"}
    lyrest = sum(rest)
    n_rest = 4 - qn
    if eps <= 0 or same <= 0 or lyrest <= 0:
        return {**out, "k": "na", "why": "有一季虧損，照季節算不準"}
    mult = lyrest / same
    if not (n_rest / S.SEAS_MAX <= mult <= n_rest * S.SEAS_MAX):
        return {**out, "k": "na", "why": "去年季節變化太大"}
    exp = eps * mult
    ratio = need / exp
    k = "lo" if ratio < S.LOW else "hi" if ratio > S.HIGH else "ok"
    return {**out, "k": k, "exp": _r(exp, 2), "ratio": _r(ratio, 3)}


def build(today: str, root: Path = ROOT, D=None) -> dict:
    from .eqfacts import consensus
    M = members(root)
    tq = target(today)
    fx = (_read(DASH / "x9f.json", {}) or {}).get("s") or {}
    if D is None:
        try:
            from .analyze import Data
            D = Data()
        except Exception:                                 # noqa: BLE001 —— 價格讀不到：近 1 個月股價留空
            D = None
    rows = {}
    for c in sorted(M):
        co = _read(DASH / "co" / f"{c}.json")
        if not co:
            rows[c] = {"n": M[c]["n"], "q": tq, "in": False, "last": None, "nodata": True}
            continue
        px = None
        if D is not None:
            try:
                s = D.series(c)["c"]
                last = max((i for i in range(len(s)) if s[i]), default=None)
                if last is not None and last >= 21 and s[last - 21]:
                    px = _pc(s[last], s[last - 21])
            except Exception:                             # noqa: BLE001
                px = None
        rows[c] = company(c, co, consensus(fx.get(c), int(tq[:4])), tq, px)
        rows[c]["n"] = rows[c].get("n") or M[c]["n"]
    for c in rows:
        rows[c]["who"] = M[c]["who"]
    return {"ver": S.VER, "fp": S.fingerprint(), "made": today, "q": tq, "rows": rows, "sum": summary(rows)}


def summary(rows: dict) -> dict:
    """規格第 8 點。"""
    inq = [r for r in rows.values() if r.get("in")]
    ok = [r for r in inq if not r.get("suspect")]
    eps = {"up": 0, "flat": 0, "dn": 0, "na": 0}
    for r in ok:
        e = r.get("ni_yoy")                                # VER 2：獲利（母公司淨利）比去年同季
        eps["na" if e is None else "up" if e > S.FLAT else "dn" if e < -S.FLAT else "flat"] += 1
    fy = {"lo": 0, "ok": 0, "hi": 0, "na": 0}
    for r in inq:
        fy[(r.get("fy") or {}).get("k", "na")] += 1
    return {"n": len(rows), "in": len(inq), "out": sorted(c for c, r in rows.items() if not r.get("in")),
            "eps": eps, "fy": fy, "decel": sum(1 for r in inq if r.get("decel")),
            "suspect": sorted(c for c, r in rows.items() if r.get("suspect")),
            "stale": sum(1 for r in inq if (r.get("fy") or {}).get("stale")),
            "med_rev": _r(st.median([r["rev_yoy"] for r in ok if r.get("rev_yoy") is not None])) if ok else None}


def write(today: str | None = None) -> bool:
    from .. import clock
    doc = build(today or clock.today_tw().isoformat())
    old = _read(OUT)
    if old and {k: v for k, v in old.items() if k != "made"} == {k: v for k, v in doc.items() if k != "made"}:
        return False
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    return True
