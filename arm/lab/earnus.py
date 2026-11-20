"""美股財報季（規格 arm/lab/ernusspec.py VER 1；docs/lab_earnings_plan.md 第 11.2 節）。只讀 repo 裡的資料、不連網。

  members()      → 清單：{代號: {"n": 名稱, "who": [[來源, 比重或 None], ...]}}（規格第 1 點；CI 抓資料也用這一份）
  season(today)  → 這一季的季底（規格第 3 點）
  company(...)   → 一家的數字（規格第 3～8 點）
  build(today)   → data/lab/earn_us.json 的內容
  write(today)   → 寫檔（內容沒變不改寫）；scripts/gen_fund_dashboard.py 建選擇權頁之前叫
資料＝data/lab/earn_us_raw.json（arm/lab/earnusdata.py，CI 抓）；頁面在 arm/lab/earnpage.py（「財報」分頁的美股）。
"""
from __future__ import annotations

import glob
import json
import statistics as st
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import ernusspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "earn_us.json"
QEND = ("03-31", "06-30", "09-30", "12-31")
MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _read(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _us(t) -> str | None:
    t = str(t or "").strip().upper()
    ok = t and len(t) <= 6 and t.replace(".", "").replace("-", "").isalpha()
    return S.ALIAS.get(t, t) if ok else None


def _is_etf(nm: str, v: dict) -> bool:
    """名稱或簡介第一句（第一個「，」以前）有 ETF（簡介後面提到「旗下 iShares ETF」的資產管理公司不算）。"""
    head = str(v.get("intro") or "").split("，", 1)[0]
    return "ETF" in (nm or "").upper() or "ETF" in head.upper()


def members(root: Path = ROOT) -> dict:
    """規格第 1 點：復華基金前十大的美股＋自家 ETF 的美股持股＋美股強勢品質股；排除 ETF。"""
    out: dict[str, dict] = {}
    prof = (_read(root / "config" / "holding_profiles.json", {}) or {}).get("profiles") or {}
    etf_tk = {_us(v.get("ticker")) for nm, v in prof.items() if isinstance(v, dict) and _is_etf(nm, v)}

    def add(c, name, who, w):
        if not c or c in etf_tk:
            return
        o = out.setdefault(c, {"n": name, "who": []})
        if not o.get("n") and name:
            o["n"] = name
        for x in o["who"]:
            if x[0] == who:
                if w is not None:
                    x[1] = round((x[1] or 0) + w, 2)            # 同一檔基金拿兩種股別：比重相加
                return
        o["who"].append([who, w])
    code_of = {nm: _us(v.get("ticker")) for nm, v in prof.items()
               if isinstance(v, dict) and v.get("country") == "美國" and not _is_etf(nm, v) and _us(v.get("ticker"))}
    for p in sorted(glob.glob(str(root / "data" / "funds" / "*.json"))):
        f = _read(Path(p), {}) or {}
        who = f.get("short_name") or f.get("fund_id")
        for h in f.get("top_holdings") or []:
            add(code_of.get(h.get("name")), h.get("name"), who, h.get("weight"))
    from .. import etfwatch
    eh = (_read(root / "data" / "etf_holdings.json", {}) or {}).get("etfs") or {}
    for row in etfwatch.WATCHLIST:
        if "復華" not in row[1]:
            continue
        for h in (eh.get(row[0]) or {}).get("holdings") or []:
            s = str(h.get("stock_id") or "").strip()
            if s.upper().endswith(" US"):
                add(_us(s[:-3]), h.get("name"), row[0], h.get("weight"))
    try:
        from .. import fund_intro as FI
        from . import ussxqm as QM
        codes, names = FI.qm_codes(QM.load_live())
    except Exception:                                        # noqa: BLE001 —— 每週紀錄讀不到：少這個來源
        codes, names = [], {}
    for c in codes:
        add(_us(c), names.get(c), "美股強勢品質股", None)
    return out


# ── 季 ───────────────────────────────────────────────────────────────────────

def cq(end: str) -> str:
    """規格第 3 點：期末日往前 QMAP_DAYS 天落在的日曆季 → 那一季的季底。"""
    d = date.fromisoformat(end) - timedelta(days=S.QMAP_DAYS)
    return f"{d.year}-{QEND[(d.month - 1) // 3]}"


def season(today: str) -> str:
    d = date.fromisoformat(today) - timedelta(days=S.SEASON_LAG)
    for k in range(3, -1, -1):
        q = f"{d.year}-{QEND[k]}"
        if q <= d.isoformat():
            return q
    return f"{d.year - 1}-12-31"


# ── 一家 ─────────────────────────────────────────────────────────────────────

def _r(x, n=1):
    return None if x is None else round(x, n)


def _pc(a, b):
    return _r((a / b - 1) * 100) if a is not None and b and b > 0 else None


def beat(a, e) -> str | None:
    """規格第 4 點：hi／ok／lo；任一沒有＝None。"""
    if a is None or e is None:
        return None
    tol = max(S.FLAT_PCT * abs(e), S.FLAT_ABS)
    return "ok" if abs(a - e) <= tol + 1e-9 else "hi" if a > e else "lo"


def _sur(a, e):
    return _r((a - e) / abs(e) * 100) if a is not None and e not in (None, 0) else None


def nasdaq(nq: dict, c: str, end: str, rt: str | None) -> list | None:
    """規格第 4 點：同代號、公布日相差 NQ_DAYS 天以內、會計季的月份對得上（那斯達克沒寫會計季就不比）。"""
    if not rt:
        return None
    d0 = date.fromisoformat(rt[:10])
    fq = f"{MON[int(end[5:7]) - 1]}/{end[:4]}"
    for k in sorted(range(-S.NQ_DAYS, S.NQ_DAYS + 1), key=abs):
        x = (nq.get((d0 + timedelta(days=k)).isoformat()) or {}).get(c)
        if x and (not x[3] or x[3] == fq):
            return x
    return None


def ly(q: dict, end: str) -> dict | None:
    """去年同季：期末日離「一年前」最近、相差 20 天以內的那一季。"""
    t = date.fromisoformat(end) - timedelta(days=365)
    best = None
    for k in q:
        gap = abs((date.fromisoformat(k) - t).days)
        if gap <= 20 and (best is None or gap < best[0]):
            best = (gap, k)
    return q[best[1]] if best else None


def ni_yoy(ni, ni_ly):
    """規格第 6 點：→ (百分比或 None, 字或 None)。"""
    if ni is None or ni_ly is None:
        return None, None
    if ni_ly > 0 and ni > 0:
        return _pc(ni, ni_ly), None
    if ni_ly <= 0 < ni:
        return None, "轉盈"
    if ni_ly > 0 >= ni:
        return None, "轉虧"
    return None, "虧損"


def react(ev: list, rt: str | None) -> dict | None:
    """規格第 7 點：→ {"f": 起日, "t": 迄日, "p": 百分比, "k": pre／post／mid}；要用的那一天還沒收盤＝None。"""
    if not ev or not rt:
        return None
    d, hm = rt[:10], rt[11:16]
    ds = [x[0] for x in ev]
    px = dict((x[0], x[1]) for x in ev)
    before = max((x for x in ds if x < d), default=None)
    after = min((x for x in ds if x > d), default=None)
    on = d if d in px else None
    k = "pre" if hm and hm < S.OPEN else "post" if hm and hm >= S.CLOSE else "mid"
    if k == "pre":
        f, t = before, on or after
    elif k == "post":
        f, t = on or before, after
    else:
        f, t = before, after
    if not f or not t or not px.get(f):
        return None
    return {"f": f, "t": t, "p": _r((px[t] / px[f] - 1) * 100), "k": k}


def company(c: str, raw: dict, nq: dict, sq: str, now_et: str) -> dict:
    """一家（規格第 3～8 點）。raw＝earn_us_raw.json 裡這一家。"""
    q = raw.get("q") or {}
    done = sorted(k for k, v in q.items() if v.get("rt") and v["rt"] <= now_et)
    mine = [k for k in done if cq(k) == sq]
    r: dict = {"q": sq, "ed": raw.get("ed"), "ede": raw.get("ede")}
    pm = raw.get("p1m")
    r["px1m"] = _r((pm[0][1] / pm[1][1] - 1) * 100) if pm and pm[1][1] else None
    if done:
        r["last"] = [done[-1], q[done[-1]]["rt"]]
    if not mine:
        r["in"] = False
        return r
    end = mine[-1]
    x = q[end]
    r.update({"in": True, "end": end, "rt": x["rt"], "rev": x.get("rev"), "ni": x.get("ni")})
    # EPS 對預估（兩家）
    ya, ye = x.get("ea"), x.get("ee")
    n = nasdaq(nq, c, end, x.get("rt"))
    na, ne = (n[0], n[1]) if n else (None, None)
    ly_, ln_ = beat(ya, ye), beat(na, ne)
    if ly_ and ln_:
        k, src = (ly_, "both") if ly_ == ln_ else ("mix", "both")
    elif ly_ or ln_:
        k, src = (ly_ or ln_), ("yahoo" if ly_ else "nasdaq")
    else:
        k, src = "na", None
    r["eps"] = {"k": k, "src": src, "y": [ya, ye, _sur(ya, ye)], "n": [na, ne, _sur(na, ne), n[2] if n else None]}
    # 營收對公布前最後一版預估（只有 Yahoo）
    sn = (raw.get("snap") or {}).get(end)
    if sn and sn.get("r") and x.get("rev"):
        p = (x["rev"] / sn["r"] - 1) * 100
        r["revb"] = {"k": "ok" if abs(p) <= S.REV_FLAT else "hi" if p > 0 else "lo", "p": _r(p), "est": sn["r"], "d": sn.get("d")}
    else:
        r["revb"] = {"k": "nosnap"}
    # 比去年同季
    lq = ly(q, end) or {}
    r["rev_yoy"] = _pc(x.get("rev"), lq.get("rev"))
    r["ni_yoy"], r["ni_txt"] = ni_yoy(x.get("ni"), lq.get("ni"))
    r["ni_ly"] = lq.get("ni")
    r["suspect"] = bool((r["rev_yoy"] or 0) >= S.SUSPECT_REV and x.get("ni") is not None and x["ni"] < 0 < (lq.get("ni") or 0))
    r["rev8"] = []
    for k2 in sorted(q)[-8:]:
        if k2 <= end:
            r["rev8"].append([k2, _pc(q[k2].get("rev"), (ly(q, k2) or {}).get("rev"))])
    r["react"] = react((raw.get("ev") or {}).get(end), x.get("rt"))
    return r


def growth(r: dict) -> str | None:
    """規格第 6 點的成長／差不多／衰退（轉盈算成長、轉虧算衰退、兩年都虧不算）。"""
    if r.get("ni_txt") == "轉盈":
        return "up"
    if r.get("ni_txt") == "轉虧":
        return "dn"
    v = r.get("ni_yoy")
    if v is None:
        return None
    return "up" if v > S.FLAT else "dn" if v < -S.FLAT else "flat"


def summary(rows: dict, today: str) -> dict:
    """規格第 9 點。"""
    inq = [r for r in rows.values() if r.get("in")]
    ok = [r for r in inq if not r.get("suspect")]
    eps = {"hi": 0, "ok": 0, "lo": 0, "mix": 0, "na": 0}
    for r in inq:
        eps[(r.get("eps") or {}).get("k", "na")] += 1
    rv = {"hi": 0, "ok": 0, "lo": 0, "nosnap": 0}
    for r in inq:
        rv[(r.get("revb") or {}).get("k", "nosnap")] += 1
    g = {"up": 0, "flat": 0, "dn": 0, "na": 0}
    for r in ok:
        g[growth(r) or "na"] += 1
    rs = [r["react"]["p"] for r in inq if r.get("react")]
    end = (date.fromisoformat(today) + timedelta(days=S.UPCOMING_DAYS)).isoformat()
    up = []
    for c, r in rows.items():
        if r.get("in"):
            continue
        d = min((x for x in r.get("ed") or [] if x >= today), default=None)
        if d and d <= end:
            up.append([d, c, bool(r.get("ede"))])
    return {"n": len(rows), "in": len(inq), "out": len(rows) - len(inq), "eps": eps, "rev": rv, "g": g,
            "rx": {"up": sum(1 for p in rs if p > 0), "dn": sum(1 for p in rs if p < 0), "n": len(rs),
                   "med": _r(st.median(rs)) if rs else None},
            "suspect": sorted(c for c, r in rows.items() if r.get("suspect")), "upcoming": sorted(up)}


def build(today: str, root: Path = ROOT, raw: dict | None = None, now: datetime | None = None) -> dict:
    from .corepage import us_label
    from .earnusdata import load, _ny
    M = members(root)
    raw = raw if raw is not None else load()
    now_et = (now or datetime.now(timezone.utc)).astimezone(_ny()).strftime("%Y-%m-%dT%H:%M")
    sq = season(today)
    rows = {}
    for c in sorted(M):
        rw = (raw.get("s") or {}).get(c)
        if not rw or not rw.get("q"):
            rows[c] = {"q": sq, "in": False, "nodata": True}
        else:
            rows[c] = company(c, rw, raw.get("nq") or {}, sq, now_et)
        nm, what = us_label(c)
        rows[c]["n"] = nm if nm != c else (M[c].get("n") or c)
        rows[c]["ind"] = what
        rows[c]["who"] = M[c]["who"]
    return {"ver": S.VER, "fp": S.fingerprint(), "made": today, "q": sq, "at": raw.get("at"), "rows": rows, "sum": summary(rows, today)}


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
