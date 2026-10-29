"""美股個股報告的資料包（docs/lab_equity_report_plan.md 第 3、6 節；評等規格 eqspec VER 3）。

只讀 repo 裡已有的資料、不連外網：
- data/lab/ussx_fin.json：SEC 第一次公布的每季營收、毛利、營業利益、淨利、EPS、股東權益（百萬美元）與流通股數；GICS 細產業同業（每週）。
- data/lab/ussx_card.json：近一年每天收盤、5 年每週收盤、股利、Yahoo 分析師（預估、目標價、評等、做空、法人與內部人持股）。
- data/lab/fwd/us.json.gz：約 650 家的股價與 Yahoo 今年、明年 EPS 預估（同業的未來本益比用它）。
- data/lab/ussx_gics.json：S&P 1500 的 GICS 大類、細產業、公司名。
- data/lab/heat/us_px_spx.json.gz：S&P 500 每天收盤。
- data/lab/ussx_qm.json：美股強勢品質股的名單、五個條件的數字、下一次買進日。
金額一律億美元（百萬美元 ÷ 100）、比例 %。近四季口徑照 eqspec VER 3：本益比＝市值 ÷ 近四季淨利，基數＝近四季淨利 ÷ 最新流通股數；
Yahoo 的 EPS 預估與「實際」多半是調整後數字，只和調整後的比（隱含剩餘期間用 Yahoo 的實際，不用 SEC 的）。
"""
from __future__ import annotations

import gzip
import json
import re
from datetime import date
from pathlib import Path

from . import eqfacts as E
from . import eqspec as S

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "lab"
VER = 1
BAND_N = S.BAND_YEARS * 12
QN = 12


def _read(p: Path, default=None):
    try:
        if p.suffix == ".gz":
            return json.loads(gzip.open(p, "rt", encoding="utf-8").read())
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _r(x, d=2):
    return None if x is None else round(x, d)


def _pc(a, b):
    return round((a / b - 1) * 100, 1) if a and b else None


def _pct(x, d=1):
    return None if x is None else round(x * 100, d)


def slug(ind: str) -> str:
    """GICS 細產業 → 產業報告代號（us-小寫英文字母數字與連字號，最多 40 字）。"""
    s = re.sub(r"[^a-z0-9]+", "-", (ind or "").lower().replace("&", "and")).strip("-")
    return ("us-" + s)[:40].rstrip("-")


# ── 財報（SEC 第一次公布） ─────────────────────────────────────────────────

def shares_at(sh: list, d: str) -> float | None:
    """d（含）以前已公布的最新流通股數（百萬股）。sh＝[[日期, 公布日, 股數]]。"""
    xs = [r for r in sh or [] if r[1] and r[1] <= d and r[2]]
    return xs[-1][2] if xs else None


def _year_ago(qs: list, i: int) -> int | None:
    """第 i 季的去年同季（季底差 350～380 天）。"""
    a = date.fromisoformat(qs[i]["q"])
    for j in range(i - 1, -1, -1):
        dd = (a - date.fromisoformat(qs[j]["q"])).days
        if 350 <= dd <= 380:
            return j
        if dd > 380:
            return None
    return None


def quarters(fq: dict) -> list[dict]:
    """ussx_fin 的一檔 → 每季（億美元、%）；ni4＝近四季淨利、eps4＝近四季淨利 ÷ 公布那時的流通股數（VER 3 口徑）、
    eps4r＝近四季財報 EPS 加總（加權股數，只給人看）。第四季是全年減前三季（SEC 的做法）。"""
    out = []
    for r in fq.get("q") or []:
        qe, filed, rev, gp, op, ni, eps, eq = (list(r) + [None] * 8)[:8]
        o = {"q": qe, "dl": filed, "rev": _r(rev / 100) if rev is not None else None, "gp": _r(gp / 100) if gp is not None else None,
             "op": _r(op / 100) if op is not None else None, "nip": _r(ni / 100) if ni is not None else None, "eps": eps,
             "eqp": _r(eq / 100) if eq is not None else None, "_ni": ni, "_eq": eq, "_rev": rev,
             "ocf": None, "icf": None, "fcf": None, "cash": None, "ta": None, "tl": None, "ca": None, "cl": None, "dr": None, "cr": None}
        for k, num in (("gm", gp), ("om", op), ("nm", ni)):
            o[k] = round(num / rev * 100, 1) if num is not None and rev else None
        o["sh"] = shares_at(fq.get("sh"), filed or qe)
        out.append(o)
    for i, o in enumerate(out):
        j = _year_ago(out, i)
        p = out[j] if j is not None else None
        o["rev_yoy"] = _pc(o["_rev"], p["_rev"]) if p else None              # 用原始數字算，不用四捨五入後的億美元
        o["eps_yoy"] = round((o["eps"] / p["eps"] - 1) * 100, 1) if p and p["eps"] and p["eps"] > 0 and o["eps"] is not None else None
        last4 = out[max(0, i - 3):i + 1]
        ok = len(last4) == 4 and all(x["_ni"] is not None for x in last4) and \
            (date.fromisoformat(last4[-1]["q"]) - date.fromisoformat(last4[0]["q"])).days <= 290
        o["ni4"] = _r(sum(x["_ni"] for x in last4) / 100) if ok else None
        o["eps4"] = _r(sum(x["_ni"] for x in last4) / o["sh"]) if ok and o["sh"] else None
        o["eps4r"] = _r(sum(x["eps"] for x in last4)) if ok and all(x["eps"] is not None for x in last4) else None
        e0 = out[j]["_eq"] if j is not None else None
        o["roe4"] = round(sum(x["_ni"] for x in last4) / ((o["_eq"] + e0) / 2) * 100, 1) if ok and o["_eq"] and e0 else None
        o["bvps"] = _r(o["_eq"] / o["sh"]) if o["_eq"] and o["sh"] else None
    for o in out:
        for k in ("_ni", "_eq", "_rev"):
            o.pop(k, None)
    return out


def fy_of(qend: str, fy_end_m: int) -> int:
    """季底屬於哪個會計年度（年度結束那一年）。"""
    d = date.fromisoformat(qend)
    return d.year if d.month <= fy_end_m else d.year + 1


def annual(qs: list[dict], fy_end_m: int, div: list) -> list[dict]:
    """完整四季的會計年度（年度結束那一年當標籤）；股利＝那個會計年度裡除息的合計。"""
    by: dict[int, list] = {}
    for q in qs:
        by.setdefault(fy_of(q["q"], fy_end_m), []).append(q)
    out = []
    for y in sorted(by):
        g = by[y]
        if len(g) != 4:
            continue
        s = {k: _r(sum(q[k] for q in g if q[k] is not None)) if all(q[k] is not None for q in g) else None
             for k in ("rev", "gp", "op", "nip", "eps")}
        dps = sum(v for d0, v in div or [] if fy_of(d0, fy_end_m) == y)
        o = {"y": str(y), **s, "ocf": None, "icf": None, "fcf": None, "dps": round(dps, 3) if dps else None,
             "bvps": g[-1].get("bvps"), "roe": g[-1].get("roe4")}
        for k, num in (("gm", "gp"), ("om", "op"), ("nm", "nip")):
            o[k] = round(s[num] / s["rev"] * 100, 1) if s[num] is not None and s["rev"] else None
        out.append(o)
    for i, o in enumerate(out):
        p = out[i - 1] if i and int(out[i - 1]["y"]) == int(o["y"]) - 1 else None
        o["rev_yoy"] = _pc(o["rev"], p["rev"]) if p else None
        o["eps_yoy"] = round((o["eps"] / p["eps"] - 1) * 100, 1) if p and p["eps"] and p["eps"] > 0 and o["eps"] is not None else None
    return out


# ── 股價 ─────────────────────────────────────────────────────────────────

def closes(card: dict, cal: list) -> list[tuple[str, float]]:
    """5 年每週收盤（較早的）＋近一年每天收盤，依日期排。"""
    wk = [(r[0], r[1]) for r in card.get("wk") or [] if r[1]]
    dl = [(d, c) for d, c in zip(cal, card.get("c") or []) if c]
    first = dl[0][0] if dl else "9999"
    return [x for x in wk if x[0] < first] + dl


def month_ends(px: list[tuple[str, float]]) -> list[tuple[str, float, str]]:
    """每個月最後一個收盤 → [(年月, 收盤, 那天)]。"""
    out: dict[str, tuple] = {}
    for d, c in px:
        out[d[:7]] = (d[:7], c, d)
    return [out[k] for k in sorted(out)]


def bands(px: list, qs: list[dict], sh: list, asof_ym: str) -> dict:
    """近 5 年每個月底（eqspec VER 3 美股口徑）：本益比＝月底收盤 × 當時已公布的股數 ÷ 當時已公布的近四季淨利；
    淨值比＝月底收盤 × 股數 ÷ 當時已公布的股東權益。rows＝[年月, 收盤, 近四季淨利 ÷ 股數, 每股淨值]（畫區間線用）。"""
    ms = [m for m in month_ends(px) if m[0] <= asof_ym][-BAND_N:]
    pe, pb, rows = [], [], []
    for ym, c, d in ms:
        avail = [q for q in qs if q["dl"] and q["dl"] <= d]
        last = next((q for q in reversed(avail) if q.get("ni4") is not None), None)
        n = shares_at(sh, d)
        e4 = _r(last["ni4"] * 100 / n) if last and n else None
        bq = avail[-1] if avail else None
        bv = _r(bq["eqp"] * 100 / n) if bq and bq.get("eqp") and n else None
        rows.append([ym, c, e4, bv])
        v = c / e4 if e4 and e4 > 0 else None
        pe.append([ym, _r(v, 1) if v is not None and 0 < v <= S.BAND_PE_MAX else None])
        w = c / bv if bv and bv > 0 else None
        pb.append([ym, _r(w, 2) if w is not None and 0 < w <= S.BAND_PB_MAX else None])
    out: dict = {"rows": rows}
    for k, ser in (("pe", pe), ("pb", pb)):
        b = S.band([v for _, v in ser])
        out[k] = {"ser": ser, **({kk: _r(vv, 2) for kk, vv in b.items()} if b else {})}
    return out


def daily(card: dict, cal: list, spx: dict) -> dict:
    """價格摘要與近 2 年走勢（第一年每週、最近一年每天；S&P 500 取同一天或之前最近一天）。52 週區間用收盤。"""
    px = closes(card, cal)
    if not px:
        return {}
    d1, c1 = cal[-1], card["c"][-1]
    cut = f"{int(d1[:4]) - 2}{d1[4:]}"
    ser_px = [x for x in px if x[0] > cut]
    sd = sorted(spx)

    def ix_at(d):
        import bisect
        j = bisect.bisect_right(sd, d) - 1
        return spx[sd[j]] if j >= 0 else None
    yr = [c for c in card["c"] if c]
    cs = card["c"]

    def back(n):
        return cs[-1 - n] if len(cs) > n else None
    ix_now = ix_at(d1)

    def ixback(n):
        return ix_at(cal[-1 - n]) if len(cal) > n else None
    ret = {k: _pc(c1, back(n)) for k, n in (("1m", 21), ("3m", 63), ("6m", 126), ("1y", len(cs) - 1))}
    ixr = {k: _pc(ix_now, ixback(n)) for k, n in (("1m", 21), ("3m", 63), ("6m", 126), ("1y", len(cs) - 1))}
    return {"px": {"c": c1, "d": d1, "hi52": max(yr), "lo52": min(yr), "close52": True, "ret": ret, "ixret": ixr},
            "ser": {"d": [x[0] for x in ser_px], "c": [x[1] for x in ser_px], "v": [], "ix": [_r(ix_at(x[0])) for x in ser_px],
                    "ix_name": "S&P 500"}}


# ── 法人共識（Yahoo，多半是調整後 EPS） ────────────────────────────────────

def _fy(y: dict) -> str | None:
    return (y.get("end") or "")[:4] or None


def f12m_eps(an: dict, asof: str) -> dict:
    y0, y1 = an.get("y0") or {}, an.get("y1") or {}
    e0, e1 = y0.get("e") or [None] * 5, y1.get("e") or [None] * 5
    n = e0[3] or 0
    if n >= S.CONS_MIN and e0[0] is not None and e1[0] is not None and y0.get("end"):
        w = S.year_weight(asof, y0["end"])
        return {"eps": round(S.f12m(asof, e0[0], e1[0], y0["end"]), 2), "src": "cons", "w": round(w, 4),
                "eps_y": e0[0], "eps_y1": e1[0], "y": int(_fy(y0)), "y_end": y0["end"], "n": n, "adj": True}
    return {"eps": None, "src": "none"}


def consensus(an: dict, an_at: str | None) -> dict:
    if not an:
        return {}
    eps = {}
    for k in ("y0", "y1"):
        y = an.get(k) or {}
        e, r = y.get("e") or [None] * 5, y.get("r") or [None] * 5
        if _fy(y):
            eps[_fy(y)] = {"med": e[0], "lo": e[1], "hi": e[2], "n": e[3], "rev": r[0], "end": y.get("end")}
    tp = an.get("tp") or [None] * 4
    ev = [{"d": u[0], "firm": u[1], "from": u[3], "to": u[4], "tp_from": u[5], "tp_to": u[6]} for u in an.get("ud") or []]
    return {"src": "Yahoo Finance", "stat": "平均", "d": an_at, "n": ((an.get("y0") or {}).get("e") or [None] * 5)[3],
            "eps": eps, "tp": {"v": tp[0], "med": tp[1], "hi": tp[2], "lo": tp[3], "n": an.get("n"), "d": an_at, "src": "Yahoo Finance"},
            "rt": an.get("rc"), "rm": an.get("rm"), "ev": ev, "eh": an.get("eh") or []}


def implied(an: dict, fy_end_m: int, last_q: str | None) -> dict:
    """今年還要多少（全部用 Yahoo 的調整後數字，不和 SEC 的混）：今年預估 − 今年已公布的季；去年同期＝一年前那幾季的實際。"""
    y0 = an.get("y0") or {}
    e0 = (y0.get("e") or [None] * 5)[0]
    end = y0.get("end")
    eh = {r[0]: r[1] for r in an.get("eh") or [] if r[1] is not None}
    if e0 is None or not end or not eh:
        return {}
    fy = int(end[:4])
    done = [q for q in sorted(eh) if fy_of(q, fy_end_m) == fy]
    if not done or (last_q and done[-1] != last_q):
        return {}
    rest_q = []
    d = date.fromisoformat(done[-1])
    for _ in range(4 - len(done)):
        m = d.month + 3
        y, m = (d.year + (m - 1) // 12, (m - 1) % 12 + 1)
        nd = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)
        from datetime import timedelta
        d = nd - timedelta(days=1)
        rest_q.append(d.isoformat())
    ly = []
    for q in rest_q:
        qd = date.fromisoformat(q)
        cand = [k for k in eh if abs((qd - date.fromisoformat(k)).days - 365) <= 10]
        ly.append(eh[cand[0]] if cand else None)
    ytd = round(sum(eh[q] for q in done), 2)
    rest = round(e0 - ytd, 2)
    out = {"q_done": len(done), "eps_ytd": ytd, "eps_rest": rest, "adj": True, "y": fy}
    if ly and all(x is not None for x in ly):
        rl = round(sum(ly), 2)
        out.update(eps_rest_ly=rl, eps_rest_x=round(rest / rl, 1) if rl > 0 else None,
                   eps_rest_yoy=round((rest / rl - 1) * 100, 1) if rl > 0 else None)
    return out


# ── 同業（GICS 細產業，S&P 1500） ──────────────────────────────────────────

def _fwd_pe(fwd: dict, c: str, asof: str) -> tuple[float | None, float | None]:
    """同業的股價與未來 12 個月本益比（同一個加權法、各自的會計年度、分析師 ≥ CONS_MIN）。"""
    q, s = (fwd.get("q") or {}).get(c), (fwd.get("s") or {}).get(c)
    px = q[2] if q and len(q) > 2 else None
    if not s or not px:
        return px, None
    f = f12m_eps({"y0": s.get("y0"), "y1": s.get("y1")}, asof)
    return px, (round(px / f["eps"], 1) if f.get("eps") and f["eps"] > 0 else None)


def peer_rows(code: str, fq: dict, gics: dict, fwd: dict, asof: str) -> tuple[list[dict], dict | None]:
    """ussx_fin 的同業列（每週：市值、最新一季營收年增、近四季營益率、近四季 ROE、本益比＝市值 ÷ 近四季淨利、近一年漲跌）。"""
    rows = ((fq.get("peer") or {}).get("rows")) or []
    out, me = [], None
    for c, cap, rq, om, roe, pe, r1y in rows:
        px, fpe = _fwd_pe(fwd, c, asof)
        o = {"c": c, "n": ((gics.get(c) or [None] * 4)[3]) or c, "cap": cap, "px": px, "pe": pe, "fpe": fpe,
             "rq": _pct(rq), "om": _pct(om), "roe": _pct(roe), "r1y": _pct(r1y, 0), "pb": None, "gm": None, "yld": None, "ry3": None}
        if c == code:
            me = o
        else:
            out.append(o)
    return out, me


# ── 為什麼被選上（美股強勢品質股） ─────────────────────────────────────────

QM_KEYS = ("rs", "d52h", "om", "roe", "cap")


def pick_info(code: str, qm: dict) -> dict:
    now = qm.get("now") or {}
    lst = [x.get("c") for x in now.get("list") or []]
    if code not in lst:
        return {}
    met = (now.get("met") or {}).get(code) or []
    rule = (qm.get("rule") or {}).get("qm") or {}
    m = dict(zip(QM_KEYS, met))
    return {"list": "美股強勢品質股", "d": now.get("wk") or now.get("d"), "rank": lst.index(code) + 1, "n": now.get("n_list"),
            "rs": m.get("rs"), "d52h": _pct(m.get("d52h")), "om": _pct(m.get("om")), "roe": _pct(m.get("roe")),
            "cap": round(m["cap"] / 1e8, 1) if m.get("cap") else None,
            "rule": {"rs": rule.get("rs"), "d52h": _pct(rule.get("d52h"), 0), "om": _pct(rule.get("om"), 0), "roe": _pct(rule.get("roe"), 0),
                     "cap": round(rule["cap"] / 1e8) if rule.get("cap") else None},
            "buy": code in (now.get("buy") or []), "buyd": now.get("next"),
            "hold": code in [h.get("c") for h in now.get("hold") or []], "slots": (qm.get("rule") or {}).get("slots"),
            "exit_ma": ((qm.get("rule") or {}).get("exit") or {}).get("ma")}


# ── 組資料包 ───────────────────────────────────────────────────────────────

def us_pack(code: str, asof: str | None = None) -> dict:
    fin = _read(LAB / "ussx_fin.json", {}) or {}
    card_all = _read(LAB / "ussx_card.json", {}) or {}
    fq = (fin.get("s") or {}).get(code)
    card = (card_all.get("s") or {}).get(code)
    if not fq or not card:
        raise FileNotFoundError(f"{code} 不在 ussx_fin.json／ussx_card.json（只有選股頁美股那幾檔有）")
    gics = (_read(LAB / "ussx_gics.json", {}) or {}).get("s") or {}
    fwd = _read(LAB / "fwd" / "us.json.gz", {}) or {}
    spx = ((_read(LAB / "heat" / "us_px_spx.json.gz", {}) or {}).get("d")) or {}
    qm = _read(LAB / "ussx_qm.json", {}) or {}
    cal = card_all.get("cal") or []
    an = card.get("an") or {}
    dl = daily(card, cal, spx)
    asof = asof or dl["px"]["d"]
    g = gics.get(code) or [None] * 4
    end = ((an.get("y0") or {}).get("end")) or "2000-12-31"
    fy_end_m = int(end[5:7])
    qs = quarters(fq)
    yrs = annual(qs, fy_end_m, card.get("div") or [])
    px = dl["px"]["c"]
    bd = bands(closes(card, cal), qs, fq.get("sh") or [], asof[:7])
    f12 = f12m_eps(an, asof)
    cons = consensus(an, card.get("an_at"))
    prow, me = peer_rows(code, fq, gics, fwd, asof)
    last = qs[-1] if qs else {}
    sh_now = shares_at(fq.get("sh") or [], asof)
    cap = _r(px * sh_now / 100, 1) if sh_now else None
    pe_now = _r(cap / last["ni4"], 1) if cap and last.get("ni4") and last["ni4"] > 0 else None
    pb_now = _r(cap / last["eqp"], 2) if cap and last.get("eqp") and last["eqp"] > 0 else None
    me = dict(me or {"c": code})
    me.update(n=fin.get("names", {}).get(code) or g[3] or code, cap=cap, px=px, pe=pe_now, pb=pb_now, r1y=dl["px"]["ret"].get("1y"),
              fpe=_r(px / f12["eps"], 1) if f12.get("eps") and f12["eps"] > 0 else None, roe=last.get("roe4"))
    keys = ("cap", "px", "pe", "fpe", "rq", "om", "roe", "r1y")
    med = {k: _r(E._med([p[k] for p in prow]), 2) for k in keys}
    my = {"pe": pe_now, "pb": pb_now, "yld": None}
    sector = g[1]
    val = E.valuation(f12, qs, bd, prow, px, my, "金融保險" if sector == "Financials" else g[2], "us")
    if val.get("basis") == "ttm" and val.get("method") == "pe":           # 美股近四季口徑（eqspec VER 3）
        val["base_label"] = "近四季淨利 ÷ 最新流通股數"
        val["range_how"] = (f"本公司近 {S.BAND_YEARS} 年每月本益比與同業現在本益比（都是市值 ÷ 近四季淨利），第 25～75 百分位取最寬")
    elif val.get("method") == "pb":
        val["range_how"] = f"本公司近 {S.BAND_YEARS} 年每月淨值比與同業現在淨值比（市值 ÷ 股東權益），第 25～75 百分位取最寬"
    ed = an.get("ed") or []
    return {"ver": VER, "spec": S.VER, "mk": "us", "code": code, "name": me["n"], "asof": asof,
            "made": date.today().isoformat(), "ind": g[2], "sector": sector, "index": g[0], "intro": E._intro(code),
            "src_d": {"sec": fin.get("sec"), "scr": fin.get("scr"), "gics": fin.get("gics"), "card": card_all.get("d"),
                      "an": card.get("an_at"), "fwd": fwd.get("d")},
            "px": dl["px"], "cap": cap, "shares": sh_now, "fy_end": fy_end_m, "my": my,
            "q": qs[-QN:], "y": yrs[-5:], "mo": [], "ytd": {}, "val": val, "cons": cons,
            "implied": implied(an, fy_end_m, last.get("q")),
            "peers": prow, "peers_auto": [p["c"] for p in prow], "peer_me": me, "peer_med": med,
            "peer_how": "GICS 細產業", "peer_n": (fq.get("peer") or {}).get("n"),
            "chain": [], "chain_main": None, "ind_key": slug(g[2] or ""),
            "ser": dl["ser"], "chips": {}, "chip_sum": {}, "fp": {}, "mb": {}, "sb": {}, "etf": {},
            "us_chips": {"sh": an.get("sh"), "mh": an.get("mh"), "ns": an.get("ns"), "tx": (an.get("tx") or [])[:6],
                         "rc": an.get("rc"), "rm": an.get("rm")},
            "div": (card.get("div") or [])[-8:],
            "pick": pick_info(code, qm),
            "next": {"earn": ed[0] if ed else None, "earn_est": bool(an.get("ede"))}}


# ── 產業資料包（GICS 細產業，S&P 1500） ────────────────────────────────────

def ind_pack_us(key: str) -> dict:
    """同一個 GICS 細產業的 S&P 1500 成員：指數、市值與未來本益比（有 Yahoo 預估的那些）、
    近四季本益比、最新一季營收年增、營益率、ROE（ussx_fin 同業列裡有的那些；每週）。沒有的就空著，不補。"""
    gics = (_read(LAB / "ussx_gics.json", {}) or {}).get("s") or {}
    fwd = _read(LAB / "fwd" / "us.json.gz", {}) or {}
    fin = _read(LAB / "ussx_fin.json", {}) or {}
    mem = sorted(c for c, v in gics.items() if v and slug(v[2] or "") == key)
    if not mem:
        raise ValueError(f"沒有這個細產業：{key}")
    g0 = gics[mem[0]]
    rows: dict = {}
    for s in (fin.get("s") or {}).values():
        for r in ((s.get("peer") or {}).get("rows")) or []:
            rows[r[0]] = r
    asof = fwd.get("d") or fin.get("scr")
    out = []
    for c in mem:
        q = (fwd.get("q") or {}).get(c)
        r = rows.get(c)
        px, fpe = _fwd_pe(fwd, c, asof or date.today().isoformat())
        cap = r[1] if r else (round(q[0] / 1e8, 1) if q and q[0] else None)            # 同一欄先用同一個日期的來源（每週篩選器）
        out.append({"c": c, "n": gics[c][3], "ix": gics[c][0], "cap": cap, "cap_src": "fin" if r else ("fwd" if q and q[0] else None),
                    "fpe": fpe, "pe": r[5] if r else None, "rq": _pct(r[2]) if r else None, "om": _pct(r[3]) if r else None,
                    "roe": _pct(r[4]) if r else None, "r1y": _pct(r[6], 0) if r else None})
    out.sort(key=lambda m: -(m["cap"] or 0))
    caps = [m["cap"] for m in out if m["cap"]]
    pe = S.band([m["pe"] for m in out if m["pe"] is not None and 0 < m["pe"] <= S.BAND_PE_MAX])
    fpe = S.band([m["fpe"] for m in out if m["fpe"] is not None and 0 < m["fpe"] <= S.BAND_PE_MAX])
    return {"ver": VER, "kind": "ind", "mk": "us", "key": key, "name": g0[2], "sector": g0[1], "asof": asof,
            "made": date.today().isoformat(), "members": out, "n_members": len(out), "n_cap": len(caps),
            "cap_total": round(sum(caps), 1) if caps else None, "pe": {k: _r(v, 2) for k, v in pe.items()} if pe else None,
            "fpe": {k: _r(v, 2) for k, v in fpe.items()} if fpe else None, "rev_agg": [], "nodes": [], "bubble": [],
            "src_d": {"gics": (_read(LAB / "ussx_gics.json", {}) or {}).get("d"), "fwd": fwd.get("d"), "scr": fin.get("scr")}}
