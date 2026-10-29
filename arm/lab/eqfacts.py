"""個股深度報告的資料包（docs/lab_equity_report_plan.md 第 3、5、6 節）。

報告裡的每個數字都從這裡來（或附來源連結）。資料包＝repo 裡已有的資料算出來，不連外網；和報告存在一起、之後不再改，
所以報告的文字和圖永遠對得上。金額一律「億元」（co 檔是百萬元 → ÷100）、比例一律「%」（已乘 100）、每股數字「元」。

台股來源：dashboard/co/{代號}.json（每季財報、月營收、月底股價、股利）、dashboard/x9t.json（全市場估值與體質）、
dashboard/x9f.json（法人預估）、data/lab/icchain.json（產業鏈 → 同業）、data/lab/mkt（每天價量、法人、融資）、
data/lab/pos（ETF 持股）、config/holding_profiles.json（簡介）、dashboard/x9.html（選股頁新飆股名單的符合條件）。
評等與目標價的算法在 eqspec（VER 1）；這裡只算預設值與可用範圍，撰寫者在範圍內選倍數。
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

from . import eqspec as S
from . import store

ROOT = Path(__file__).resolve().parents[2]
VER = 1
DASH = ROOT / "dashboard"
DAYS_PX = 500                 # 每天股價：約 2 年
DAYS_CHIP = 250               # 籌碼：約 1 年
QN = 12                       # 每季表：最近 12 季
YN = 5                        # 年度表：最近 5 年
MN = 25                       # 月營收：最近 25 個月
LISTED_GROUPS = ("本國上市公司", "本國上櫃公司", "外國上市公司")


def _r(x, d=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, d)


def _yi(x):
    """百萬元 → 億元。"""
    return None if x is None else round(x / 100, 2)


def _pc(a, b, d=1):
    """a ÷ b − 1，以 %；b ≤ 0 不算。"""
    if a is None or b is None or b <= 0:
        return None
    return round((a / b - 1) * 100, d)


def _ratio(a, b, d=1):
    if a is None or not b:
        return None
    return round(a / b * 100, d)


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ── 季、年、月 ─────────────────────────────────────────────────────────────

def deadline(q: str) -> str:
    """季底日（YYYY-MM-DD）→ 法定公告期限。"""
    y = int(q[:4])
    return {"03-31": f"{y}-05-15", "06-30": f"{y}-08-14", "09-30": f"{y}-11-14", "12-31": f"{y + 1}-03-31"}[q[5:]]


def next_quarter(q: str) -> str:
    y = int(q[:4])
    return {"03-31": f"{y}-06-30", "06-30": f"{y}-09-30", "09-30": f"{y}-12-31", "12-31": f"{y + 1}-03-31"}[q[5:]]


def quarters(co: dict) -> list[dict]:
    """co 的 q 列 → 每季一個 dict（單季損益與現金流、季底資產負債），加上三率、年增、近四季 ROE。"""
    keys = co.get("qk") or []
    raw = [dict(zip(["q"] + keys, r + [None] * (len(keys) + 1 - len(r)))) for r in co.get("q") or []]
    by = {r["q"]: r for r in raw}
    out = []
    for r in raw:
        q = r["q"]
        ly = by.get(f"{int(q[:4]) - 1}{q[4:]}")
        rev = r.get("rev")
        o = {"q": q, "rev": _yi(rev), "gp": _yi(r.get("gp")), "op": _yi(r.get("op")), "nip": _yi(r.get("nip")),
             "eps": r.get("eps"), "ocf": _yi(r.get("ocf")), "icf": _yi(r.get("icf")),
             "fcf": _yi(r["ocf"] + r["icf"]) if r.get("ocf") is not None and r.get("icf") is not None else None,
             "cash": _yi(r.get("cash")), "ta": _yi(r.get("ta")), "tl": _yi(r.get("tl")), "ca": _yi(r.get("ca")),
             "cl": _yi(r.get("cl")), "eqp": _yi(r.get("eqp")), "bvps": r.get("bvps"),
             "gm": _ratio(r.get("gp"), rev), "om": _ratio(r.get("op"), rev), "nm": _ratio(r.get("nip"), rev),
             "rev_yoy": _pc(rev, (ly or {}).get("rev")), "dl": deadline(q)}
        e0, e1 = r.get("eps"), (ly or {}).get("eps")
        o["eps_yoy"] = _r((e0 / e1 - 1) * 100, 1) if e0 is not None and e1 and e1 > 0 else None
        o["dr"] = _ratio(r.get("tl"), r.get("ta"))
        o["cr"] = _ratio(r.get("ca"), r.get("cl"))
        out.append(o)
    for i, o in enumerate(out):                                  # 近四季 ROE＝近四季淨利 ÷ 平均（期初、期末）權益
        if i >= 4 and all(out[j]["nip"] is not None for j in range(i - 3, i + 1)):
            e_now, e_then = out[i]["eqp"], out[i - 4]["eqp"]
            if e_now and e_then and e_now > 0 and e_then > 0:
                o["roe4"] = round(sum(out[j]["nip"] for j in range(i - 3, i + 1)) / ((e_now + e_then) / 2) * 100, 1)
        if i >= 3 and all(out[j]["eps"] is not None for j in range(i - 3, i + 1)):
            o["eps4"] = round(sum(out[j]["eps"] for j in range(i - 3, i + 1)), 2)
    return out


def annual(qs: list[dict], ye: dict, dv: list) -> list[dict]:
    """完整四季的年度：營收、毛利、營業利益、淨利、現金流加總；EPS 用年報全年數（ye），沒有才四季相加。"""
    by: dict[str, list] = {}
    for o in qs:
        by.setdefault(o["q"][:4], []).append(o)
    cash = {}
    for d, amt, _k in dv or []:
        if amt:
            cash[d[:4]] = round(cash.get(d[:4], 0) + amt, 4)
    out = []
    for y in sorted(by):
        rows = by[y]
        if len(rows) != 4:
            continue

        def s(k):
            v = [o[k] for o in rows]
            return round(sum(v), 2) if all(x is not None for x in v) else None
        rev, gp, op, nip = s("rev"), s("gp"), s("op"), s("nip")
        eps = ye.get(y) if ye.get(y) is not None else s("eps")
        last = rows[-1]
        out.append({"y": y, "rev": rev, "gp": gp, "op": op, "nip": nip, "eps": eps, "ocf": s("ocf"), "icf": s("icf"),
                    "fcf": s("fcf"), "gm": _ratio(gp, rev), "om": _ratio(op, rev), "nm": _ratio(nip, rev),
                    "roe": last.get("roe4"), "bvps": last.get("bvps"), "dps": cash.get(y)})
    for i, o in enumerate(out):
        prev = out[i - 1] if i else None
        o["rev_yoy"] = _pc(o["rev"], prev["rev"]) if prev else None
        o["eps_yoy"] = _pc(o["eps"], prev["eps"]) if prev else None
    return out


def ytd(qs: list[dict], mo: list[dict]) -> dict:
    """最新一季那年到目前的合計（給報告寫「前三季」「今年以來」用）。"""
    out: dict = {}
    if qs:
        y = qs[-1]["q"][:4]
        cur = [q for q in qs if q["q"][:4] == y]
        ly = [q for q in qs if q["q"][:4] == str(int(y) - 1) and q["q"][5:] <= cur[-1]["q"][5:]]
        for k in ("eps", "rev", "nip"):
            v = [q[k] for q in cur]
            w = [q[k] for q in ly]
            if all(x is not None for x in v):
                out[f"q_{k}"] = round(sum(v), 2)
                if len(w) == len(v) and all(x is not None for x in w):
                    out[f"q_{k}_ly"] = round(sum(w), 2)
                    out[f"q_{k}_yoy"] = _pc(sum(v), sum(w))
        out["q_n"] = len(cur)
        out["q_y"] = y
    if mo:
        y = mo[-1]["ym"][:4]
        cur = [o["rev"] for o in mo if o["ym"][:4] == y]
        ly = [o["rev"] for o in mo if o["ym"][:4] == str(int(y) - 1) and o["ym"][5:] <= mo[-1]["ym"][5:]]
        if cur and all(x is not None for x in cur):
            out["m_rev"] = round(sum(cur), 2)
            if len(ly) == len(cur) and all(x is not None for x in ly):
                out["m_rev_ly"] = round(sum(ly), 2)
                out["m_rev_yoy"] = _pc(sum(cur), sum(ly))
        out["m_n"] = len(cur)
        out["m_y"] = y
    return out


def months(co: dict) -> list[dict]:
    rows = co.get("mo") or []
    rev = {r[0]: r[1] for r in rows if len(r) > 1 and r[1] is not None}
    out = []
    for r in rows:
        ym = r[0]
        y, m = int(ym[:4]), int(ym[5:])
        ly = f"{y - 1}-{m:02d}"
        o = {"ym": ym, "rev": _yi(rev.get(ym)), "px": r[2] if len(r) > 2 else None,
             "sh": r[3] if len(r) > 3 else None, "rev_yoy": _pc(rev.get(ym), rev.get(ly))}
        out.append(o)
    for i, o in enumerate(out):                                  # 近 3 個月合計年增
        if i >= 2:
            cur = [out[j]["rev"] for j in range(i - 2, i + 1)]
            yms = [out[j]["ym"] for j in range(i - 2, i + 1)]
            prev = [_yi(rev.get(f"{int(x[:4]) - 1}{x[4:]}")) for x in yms]
            if all(v is not None for v in cur + prev):
                o["rev3"] = round(sum(cur), 2)
                o["rev3_ly"] = round(sum(prev), 2)
                o["rev3_yoy"] = _pc(sum(cur), sum(prev))
    return out


# ── 估值區間 ───────────────────────────────────────────────────────────────

def _month_end(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return (date.fromordinal(nxt.toordinal() - 1)).isoformat()


def bands(mo: list[dict], qs: list[dict], asof_ym: str) -> dict:
    """近 BAND_YEARS 年每個月底：本益比＝月底收盤 ÷ 當時已公布的近四季 EPS；淨值比＝÷ 當時已公布的最近一季每股淨值。"""
    n = S.BAND_YEARS * 12
    ms = [o for o in mo if o["ym"] <= asof_ym and o.get("px")][-n:]
    pe, pb, rows = [], [], []
    for o in ms:
        me = _month_end(o["ym"])
        avail = [q for q in qs if q["dl"] <= me]
        e4 = avail[-1].get("eps4") if avail else None
        bv = avail[-1].get("bvps") if avail else None
        rows.append([o["ym"], o["px"], e4, bv])
        v = o["px"] / e4 if e4 and e4 > 0 else None
        pe.append([o["ym"], _r(v, 1) if v is not None and 0 < v <= S.BAND_PE_MAX else None])
        w = o["px"] / bv if bv and bv > 0 else None
        pb.append([o["ym"], _r(w, 2) if w is not None and 0 < w <= S.BAND_PB_MAX else None])
    out: dict = {"rows": rows}
    for k, ser in (("pe", pe), ("pb", pb)):
        b = S.band([v for _, v in ser])
        out[k] = {"ser": ser, **({kk: _r(vv, 2) for kk, vv in b.items()} if b else {})}
    return out


# ── 法人共識 ───────────────────────────────────────────────────────────────

def consensus(fc: dict | None, y: int) -> dict:
    """x9f.json 的一檔 → 今年、明年、後年 EPS 中位數、營收（億）、家數、目標價、評等分布、近期修正。"""
    if not fc:
        return {}
    pe = fc.get("pe") or {}
    rows = {int(r[0]): r for r in pe.get("rows") or []}
    eps = {str(k): {"med": r[1], "lo": r[2], "hi": r[3], "rev": r[4] if len(r) > 4 else None} for k, r in sorted(rows.items())}
    pt = fc.get("pt") or {}
    t = fc.get("t") or {}
    ev = [{"d": e[0], "k": "EPS" if e[1] == "e" else "目標價", "from": e[2], "to": e[3],
           "y": e[4] if e[1] == "e" else None, "pct": e[4] if e[1] == "t" else None,
           "url": f"https://news.cnyes.com/news/id/{e[5]}"} for e in fc.get("ev") or []]
    yh = (fc.get("y") or {}).get("y0") or {}
    return {"src": {"fs": "FactSet（鉅亨網）", "y": "Yahoo Finance"}.get(pe.get("src"), pe.get("src")),
            "d": pe.get("d"), "n": pe.get("n"), "eps": eps,
            "tp": {"v": pt.get("v"), "hi": pt.get("hi"), "lo": pt.get("lo"), "n": pt.get("n"), "d": pt.get("d"),
                   "src": {"fs": "FactSet（鉅亨網）", "y": "Yahoo Finance"}.get(pt.get("src"), pt.get("src"))} if pt else None,
            "rt": t.get("rt"), "rt_d": t.get("d"), "ev": ev[:12],
            "rev30": {"up": (yh.get("rv") or [None] * 4)[2], "dn": (yh.get("rv") or [None] * 4)[3]} if yh.get("rv") else None,
            "y": y}


def f12m_eps(cons: dict, mo: list[dict], qs: list[dict], asof: str) -> dict:
    y = int(asof[:4])
    e = cons.get("eps") or {}
    n = max(cons.get("n") or 0, ((cons.get("tp") or {}).get("n") or 0))
    ey, ey1 = (e.get(str(y)) or {}).get("med"), (e.get(str(y + 1)) or {}).get("med")
    if n >= S.CONS_MIN and ey is not None and ey1 is not None:
        return {"eps": round(S.f12m(asof, ey, ey1), 2), "src": "cons", "w": round(S.year_weight(asof), 4),
                "eps_y": ey, "eps_y1": ey1, "y": y, "n": n}
    e4 = next((q.get("eps4") for q in reversed(qs) if q.get("eps4") is not None), None)
    last = next((o for o in reversed(mo) if o.get("rev3") is not None), None)
    k = S.mom_factor(last["rev3"], last["rev3_ly"]) if last else None
    if e4 is None or k is None:
        return {"eps": None, "src": "none"}
    return {"eps": round(e4 * k, 2), "src": "rule", "eps4": e4, "mom": round(k, 4), "ym": last["ym"]}


# ── 同業 ───────────────────────────────────────────────────────────────────

def chain_nodes(ic: dict, code: str) -> list[dict]:
    out = []
    for cid, ch in (ic.get("chains") or {}).items():
        for nid, nn, groups in ch.get("nodes") or []:
            mem = [c for g in groups if g[0] in LISTED_GROUPS for c in g[2]]
            if code in mem:
                out.append({"chain": cid, "cn": ch.get("n"), "node": nid, "nn": nn, "mem": mem})
    return out


def primary_chain(nodes: list[dict]) -> str | None:
    """本公司出現最多節點的那條鏈；一樣多取成員多的。"""
    cnt: dict[str, list] = {}
    for n in nodes:
        c = cnt.setdefault(n["chain"], [0, 0])
        c[0] += 1
        c[1] += len(n["mem"])
    return max(cnt, key=lambda k: (cnt[k][0], cnt[k][1], k)) if cnt else None


def pick_peers(code: str, nodes: list[dict], rows: dict, cols: list, ind_of: dict) -> tuple[list[str], str]:
    """→ (同業代號, 怎麼選的一句)。規則見 eqspec 與規劃第 5 節。"""
    ci = {k: i for i, k in enumerate(cols)}

    def cap(c):
        r = rows.get(c)
        return r[ci["cap"]] if r and r[ci["cap"]] else None
    me = cap(code)
    shared: dict[str, int] = {}
    for n in nodes:
        for c in n["mem"]:
            if c != code and cap(c):
                shared[c] = shared.get(c, 0) + 1
    how = "產業鏈"
    if len(shared) < S.PEER_MIN:
        ind = ind_of.get(code)
        shared = {c: 1 for c, v in ind_of.items() if v == ind and c != code and cap(c)}
        how = "證交所產業別"
    if not shared:
        return [], how

    def dist(c):
        return abs(math.log(cap(c)) - math.log(me)) if me else 0
    leaders: list[str] = []
    if how == "產業鏈" and nodes:
        main = min(nodes, key=lambda n: (len(n["mem"]), n["node"]))           # 最具體的節點（成員最少）
        lead = sorted((c for c in main["mem"] if c != code and cap(c)), key=lambda c: -cap(c))
        leaders = lead[:S.PEER_LEADERS]
    rest = sorted((c for c in shared if c not in leaders), key=lambda c: (-shared[c], dist(c), c))
    return (leaders + rest)[:S.PEER_N], how


def peer_row(c: str, rows: dict, cols: list, names: dict, fcs: dict, pxs: dict | None, asof: str) -> dict:
    ci = {k: i for i, k in enumerate(cols)}
    r = rows.get(c) or [None] * len(cols)

    def g(k):
        return r[ci[k]] if k in ci and ci[k] < len(r) else None
    px = g("px")
    cons = consensus(fcs.get(c), int(asof[:4]))
    f = f12m_eps(cons, [], [], asof) if cons else {"eps": None}
    fpe = round(px / f["eps"], 1) if f.get("src") == "cons" and f["eps"] and f["eps"] > 0 and px else None
    p1 = (pxs or {}).get(c)
    return {"c": c, "n": names.get(c, c), "cap": g("cap"), "px": px, "pe": g("pe"), "fpe": fpe, "pb": g("pb"),
            "yld": g("yld"), "ry3": g("ry3"), "gm": g("gm"), "om": g("om"), "roe": g("roe"), "rs": g("rs"),
            "r1y": _pc(px, p1) if p1 else None}


def _med(xs):
    v = sorted(x for x in xs if x is not None)
    return S.pctl(v, 0.5) if v else None


# ── 每天價量與籌碼 ─────────────────────────────────────────────────────────

def daily(D, code: str) -> dict:
    s = D.series(code)
    ch = D.chips(code)
    ix = D.taiex()
    T = D.T
    last = max((i for i in range(T) if s["c"][i]), default=None)
    if last is None:
        return {}
    a = max(0, last - DAYS_PX + 1)
    out = {"d": D.cal[a:last + 1], "c": s["c"][a:last + 1], "v": [round(v / 1000) if v else None for v in s["v"][a:last + 1]],
           "ix": [_r(x, 2) for x in ix[a:last + 1]]}
    c = [x for x in s["c"][max(0, last - 249):last + 1] if x]
    hi = [x for x in s["h"][max(0, last - 249):last + 1] if x] or c
    lo = [x for x in s["l"][max(0, last - 249):last + 1] if x] or c
    px = s["c"][last]

    def back(n):
        j = last - n
        while j >= 0 and not s["c"][j]:
            j -= 1
        return s["c"][j] if j >= 0 else None

    def ixback(n):
        j = last - n
        return ix[j] if j >= 0 else None
    ret = {k: _pc(px, back(n)) for k, n in (("1m", 21), ("3m", 63), ("6m", 126), ("1y", 245))}
    ixr = {k: _pc(ix[last], ixback(n)) for k, n in (("1m", 21), ("3m", 63), ("6m", 126), ("1y", 245))}
    b = max(0, last - DAYS_CHIP + 1)

    def zhang(xs):
        return [round(x / 1000) if x is not None else None for x in xs[b:last + 1]]
    chips = {"d": D.cal[b:last + 1], "f": zhang(ch["f"]), "t": zhang(ch["t"]), "dl": zhang(ch["d"]),
             "fp": ch["fp"][b:last + 1], "mb": ch["mb"][b:last + 1], "sb": ch["sb"][b:last + 1]}
    sums = {}
    for k in ("f", "t", "dl"):
        xs = chips[k]
        for n in (5, 20, 60):
            v = [x for x in xs[-n:] if x is not None]
            sums[f"{k}{n}"] = sum(v) if v else None
    def span(k, n=60):
        """最新值，和 n 個交易日前（資料不到 n 天就取最早那天）的值與日期。"""
        xs = [(d, x) for d, x in zip(chips["d"], chips[k]) if x is not None]
        if not xs:
            return {}
        d0, x0 = xs[max(0, len(xs) - 1 - n)]
        return {"now": xs[-1][1], "d": xs[-1][0], "then": x0, "then_d": d0}
    return {"px": {"c": px, "d": D.cal[last], "hi52": max(hi), "lo52": min(lo), "ret": ret, "ixret": ixr},
            "ser": out, "chips": chips, "chip_sum": sums, "fp": span("fp"), "mb": span("mb"), "sb": span("sb")}


def etf_hold(code: str, pos: list) -> dict:
    """最新揭露日持有本公司的 ETF（股數、權重），主動式（代號 A 結尾）檔數與近 20 個揭露日的張數變化。"""
    if not pos:
        return {}
    d, doc = pos[-1]
    h = []
    for etf, ent in (doc.get("etf") or {}).items():
        v = (ent.get("h") or {}).get(code)
        if v:
            h.append({"etf": etf, "sh": round(v[0] / 1000), "w": v[1]})
    h.sort(key=lambda x: -(x["w"] or 0))
    act = [x for x in h if x["etf"].endswith("A")]
    old = pos[-21] if len(pos) > 20 else pos[0]
    act_old = sum(round(((old[1].get("etf") or {}).get(e) or {}).get("h", {}).get(code, [0])[0] / 1000)
                  for e in (old[1].get("etf") or {}) if e.endswith("A"))
    return {"d": d, "n": len(h), "n_act": len(act), "act_sh": sum(x["sh"] for x in act), "act_sh_20": act_old,
            "d_20": old[0], "top": h[:10]}


# ── 為什麼被選上（選股頁） ─────────────────────────────────────────────────

def _json_obj(text: str, key: str):
    i = text.find(f'"{key}":{{')
    if i < 0:
        return None
    j = i + len(key) + 3
    depth = 0
    for k in range(j, len(text)):
        ch = text[k]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[j:k + 1])
                except ValueError:
                    return None
    return None


def pick_info(code: str, html_path: Path | None = None) -> dict:
    """選股頁新飆股名單（dashboard/x9.html 的 D.pick.tw.bx）裡這一檔的那一列：符合哪一條、名次、位置、參考價位。"""
    p = html_path or DASH / "x9.html"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return {}
    bx = _json_obj(text, "bx") or {}
    for i, r in enumerate(bx.get("rows") or []):
        if r and r[0] == code:
            return {"list": "新飆股", "d": bx.get("d"), "fix": bx.get("fix"), "buyd": bx.get("buyd"), "rank": i + 1,
                    "rs": r[2], "weeks": r[3], "why": r[4], "spot": r[5], "plan": r[6], "will_buy": r[8] == "b"}
    return {}


# ── 組資料包 ───────────────────────────────────────────────────────────────

def _intro(code: str) -> dict:
    prof = (_read(ROOT / "config" / "holding_profiles.json", {}) or {}).get("profiles") or {}
    for k, v in prof.items():
        if str((v or {}).get("ticker") or "").split(".")[0] == code:
            return {"name": k, "intro": v.get("intro"), "country": v.get("country")}
    return {}


def _next_month10(asof: str) -> str:
    d = date.fromisoformat(asof)
    y, m = (d.year, d.month + 1) if d.day > 10 else (d.year, d.month)
    if m == 13:
        y, m = y + 1, 1
    return f"{y:04d}-{m:02d}-10"


def tw_pack(code: str, D=None, pos=None, asof: str | None = None, peers: list[str] | None = None) -> dict:
    """台股一家公司的資料包。D＝analyze.Data（可共用）；asof＝報告日（預設＝最新收盤日）；
    peers＝撰寫者換過的同業（最多換 PEER_SWAP_MAX 家，原因寫在報告開頭）；不給＝照規則選。"""
    co = _read(DASH / "co" / f"{code}.json")
    if not co:
        raise FileNotFoundError(f"沒有 dashboard/co/{code}.json")
    t = _read(DASH / "x9t.json", {}) or {}
    fx = (_read(DASH / "x9f.json", {}) or {}).get("s") or {}
    ic = _read(ROOT / "data" / "lab" / "icchain.json", {}) or {}
    if D is None:
        from .analyze import Data
        D = Data()
    if pos is None:
        pos = store.load("pos")
    cols, rows = t.get("cols") or [], t.get("rows") or {}
    inds = t.get("inds") or []
    ci = {k: i for i, k in enumerate(cols)}
    ind_of = {c: inds[r[ci["ii"]]] for c, r in rows.items() if r and r[ci["ii"]] is not None and r[ci["ii"]] < len(inds)}
    dly = daily(D, code)
    asof = asof or (dly.get("px") or {}).get("d") or t.get("d")
    px = (dly.get("px") or {}).get("c")
    qs = quarters(co)
    yrs = annual(qs, co.get("ye") or {}, co.get("dv") or [])
    mo = months(co)
    bd = bands(mo, qs, asof[:7])
    cons = consensus(fx.get(code), int(asof[:4]))
    f12 = f12m_eps(cons, mo, qs, asof)
    my = dict(zip(cols, rows.get(code) or []))
    names = {c: n for c, n in ((co.get("c"), co.get("n")),)}
    nm_all = {}
    for p in (ROOT / "data" / "lab" / "names_mkt.json", ROOT / "data" / "lab" / "names.json"):
        nm_all.update(_read(p, {}) or {})
    names.update({c: nm_all.get(c, c) for c in rows})
    nodes = chain_nodes(ic, code)
    auto, how = pick_peers(code, nodes, rows, cols, ind_of)
    if peers:
        bad = [c for c in peers if c not in rows or c == code]
        if bad:
            raise ValueError(f"同業不在全市場表：{bad}")
        if len(set(peers) - set(auto)) > S.PEER_SWAP_MAX:
            raise ValueError(f"同業最多換 {S.PEER_SWAP_MAX} 家")
        peers = list(peers)
    else:
        peers = auto
    px1y = {}
    for c in peers + [code]:
        s = D.series(c)["c"]
        last = max((i for i in range(D.T) if s[i]), default=None)
        if last is not None and last >= 245:
            j = last - 245
            while j >= 0 and not s[j]:
                j -= 1
            if j >= 0:
                px1y[c] = s[j]
    prow = [peer_row(c, rows, cols, nm_all, fx, px1y, asof) for c in peers]
    me = peer_row(code, rows, cols, nm_all, fx, px1y, asof)
    me["n"] = co.get("n")
    keys = ("cap", "px", "pe", "fpe", "pb", "yld", "ry3", "gm", "om", "roe", "r1y")
    med = {k: _r(_med([p[k] for p in prow]), 2) for k in keys}
    peer_pe = S.band([p["pe"] for p in prow if p["pe"] is not None and 0 < p["pe"] <= S.BAND_PE_MAX])
    peer_pb = S.band([p["pb"] for p in prow if p["pb"] is not None and 0 < p["pb"] <= S.BAND_PB_MAX])
    bvps = next((q["bvps"] for q in reversed(qs) if q.get("bvps")), None)
    meth = S.method(f12.get("eps"), px, bvps, co.get("ind"))
    val: dict = {"px": px, "pe_ttm": my.get("pe"), "pb": my.get("pb"), "yld": my.get("yld"), "bvps": bvps,
                 "f12m": f12, "method": meth, "band": bd,
                 "peer_pe": {k: _r(v, 2) for k, v in peer_pe.items()} if peer_pe else None,
                 "peer_pb": {k: _r(v, 2) for k, v in peer_pb.items()} if peer_pb else None}
    if meth in ("pe", "pb"):
        own = {k: bd[meth].get(k) for k in ("p25", "p50", "p75", "n")} if bd[meth].get("n") else None
        rng = S.mult_range(own, val[f"peer_{meth}"])
        base = f12["eps"] if meth == "pe" else bvps
        if rng:
            tp = S.round_tp(base * rng["dflt"])
            val.update({"base": base, "range": {k: _r(v, 2) for k, v in rng.items()},
                        "fpe_now": _r(px / base, 1) if meth == "pe" and base and px else None,
                        "fpb_now": _r(px / base, 2) if meth == "pb" and base and px else None,
                        "tp_dflt": tp, "up_dflt": _pc(tp, px), "rating_dflt": S.rating(tp, px),
                        "scen_dflt": S.scenarios(base, rng, tp, "tw", pe=meth == "pe"),
                        "tp_lo": S.round_tp(base * rng["lo"]), "tp_hi": S.round_tp(base * rng["hi"])})
    nq = None
    if qs:
        nxt = next_quarter(qs[-1]["q"])
        nq = {"q": nxt, "dl": deadline(nxt)}
    return {"ver": VER, "spec": S.VER, "mk": "tw", "code": code, "name": co.get("n"), "asof": asof,
            "made": date.today().isoformat(), "ind": co.get("ind"), "intro": _intro(code),
            "src_d": {"co": co.get("asof"), "x9t": t.get("d"), "x9f": (_read(DASH / "x9f.json", {}) or {}).get("d")},
            "px": dly.get("px"), "cap": my.get("cap"), "shares": (mo[-1].get("sh") if mo else None),
            "my": {k: my.get(k) for k in ("rs", "d52h", "r120", "ry", "ry3", "racc", "ey", "eacc", "gm", "om", "roe",
                                          "pe", "pb", "yld", "dr", "cr", "liq", "tt")},
            "q": qs[-QN:], "y": yrs[-YN:], "mo": mo[-MN:], "ytd": ytd(qs, mo), "val": val, "cons": cons,
            "peers": prow, "peers_auto": auto, "peer_me": me, "peer_med": med, "peer_how": how,
            "chain": [{k: n[k] for k in ("chain", "cn", "node", "nn")} | {"n": len(n["mem"])} for n in nodes],
            "chain_main": primary_chain(nodes),
            "ser": dly.get("ser"), "chips": dly.get("chips"), "chip_sum": dly.get("chip_sum"),
            "fp": dly.get("fp"), "mb": dly.get("mb"), "sb": dly.get("sb"),
            "etf": etf_hold(code, pos), "div": (co.get("dv") or [])[-8:],
            "pick": pick_info(code),
            "next": {"quarter": nq, "month_rev": _next_month10(asof)}}


def numbers(pack: dict) -> set[float]:
    """資料包裡出現的所有數字（給檢查用；含常見的換算：億 ↔ 百萬不換，只收原值）。"""
    out: set[float] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            out.add(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, str) and re.fullmatch(r"-?\d+(\.\d+)?", x):
            out.add(float(x))
    walk(pack)
    return out


# ── 產業資料包（產業報告用；規劃第 7 節） ────────────────────────────────

def _ym_shift(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def ind_pack_tw(chain_id: str, bub: dict | None = None) -> dict:
    """台股產業鏈（icchain 的一條鏈）→ 節點、成員、成員合計月營收（同一批公司）、估值分布、細分族群泡沫。
    bub＝bubind.compute() 的結果（可共用；不給就自己算，約 12 秒；失敗只是少泡沫那段）。"""
    ic = _read(ROOT / "data" / "lab" / "icchain.json", {}) or {}
    ch = (ic.get("chains") or {}).get(chain_id)
    if not ch:
        raise KeyError(f"產業鏈沒有 {chain_id}")
    t = _read(DASH / "x9t.json", {}) or {}
    cols, rows = t.get("cols") or [], t.get("rows") or {}
    ci = {k: i for i, k in enumerate(cols)}
    names: dict = {}
    for p in (ROOT / "data" / "lab" / "names_mkt.json", ROOT / "data" / "lab" / "names.json"):
        names.update(_read(p, {}) or {})

    def g(c, k):
        r = rows.get(c)
        return r[ci[k]] if r and k in ci and ci[k] < len(r) else None
    nodes, mem_nodes = [], {}
    for nid, nn, groups in ch.get("nodes") or []:
        mem = [c for gg in groups if gg[0] in LISTED_GROUPS for c in gg[2] if c in rows]
        foreign = sum(gg[1] for gg in groups if gg[0] == "知名外國企業")
        for c in mem:
            mem_nodes.setdefault(c, []).append(nn)
        top = sorted(mem, key=lambda c: -(g(c, "cap") or 0))[:6]
        nodes.append({"node": nid, "nn": nn, "n": len(mem), "foreign": foreign, "cap": _r(sum(g(c, "cap") or 0 for c in mem), 1),
                      "top": [[c, names.get(c, c), g(c, "cap")] for c in top]})
    members = []
    for c, nns in mem_nodes.items():
        members.append({"c": c, "n": names.get(c, c), "nodes": nns, **{k: g(c, k) for k in
                        ("cap", "px", "pe", "pb", "yld", "ry3", "gm", "om", "roe", "rs", "d52h")}})
    members.sort(key=lambda x: -(x["cap"] or 0))
    revs = {}
    for m in members:
        co = _read(DASH / "co" / f"{m['c']}.json")
        if co:
            revs[m["c"]] = {r[0]: r[1] for r in co.get("mo") or [] if len(r) > 1 and r[1] is not None}
    last = max((ym for r in revs.values() for ym in r), default=None)
    agg = []
    if last:
        for k in range(MN - 1, -1, -1):
            ym = _ym_shift(last, -k)
            ly = _ym_shift(ym, -12)
            both = [c for c, r in revs.items() if ym in r and ly in r]
            if both:
                cur, prev = sum(revs[c][ym] for c in both), sum(revs[c][ly] for c in both)
                agg.append({"ym": ym, "n": len(both), "rev": _yi(cur), "rev_ly": _yi(prev), "yoy": _pc(cur, prev)})
    pe = S.band([m["pe"] for m in members if m["pe"] is not None and 0 < m["pe"] <= S.BAND_PE_MAX])
    pb = S.band([m["pb"] for m in members if m["pb"] is not None and 0 < m["pb"] <= S.BAND_PB_MAX])
    ry = S.band([m["ry3"] for m in members if m["ry3"] is not None])
    out = {"ver": VER, "kind": "ind", "mk": "tw", "key": f"tw-{chain_id}", "chain": chain_id, "name": ch.get("n"),
           "asof": t.get("d"), "made": date.today().isoformat(), "nodes": nodes, "members": members,
           "n_members": len(members), "cap_total": _r(sum(m["cap"] or 0 for m in members), 1), "rev_agg": agg,
           "pe": {k: _r(v, 2) for k, v in pe.items()} if pe else None,
           "pb": {k: _r(v, 2) for k, v in pb.items()} if pb else None,
           "ry3": {k: _r(v, 2) for k, v in ry.items()} if ry else None, "bubble": []}
    try:
        from . import bubind as BI
        from . import bubindspec as BS
        bub = bub if bub is not None else BI.compute()
        for key, nm, parts in BS.TG_GROUPS:
            if any(p[0] == chain_id for p in parts) and (bub.get("tg") or {}).get(key):
                now = bub["tg"][key].get("now") or {}
                p2 = now.get("p2") or {}
                out["bubble"].append({"key": key, "name": nm, "level": now.get("L"), "d": now.get("d"),
                                      "P1": now.get("P1"), "P2": now.get("P2"), "P3": now.get("P3"), "E": now.get("E"),
                                      "G": now.get("G"), "F": now.get("F"), "run2": _r(p2.get("ru"), 1),
                                      "net2": _r(p2.get("net"), 1), "from_hi": _r(p2.get("dist"), 1), "mem": now.get("mem")})
    except Exception as e:  # noqa: BLE001 —— 泡沫算不出來不影響產業報告其他部分
        out["bubble_err"] = f"{type(e).__name__}: {e}"
    return out
