"""泡沫頁 VER 4「未來獲利」的計算（docs/lab_risk_plan.md 第 11 節；規格常數在 bubspec）。純計算，不碰網路。

現在（分析師預估）：每家公司 [股數, 今年預估, 明年預估, 去年實際, 明年預估 90 天前, 市值] 加總 → 今年成長、明年成長、修正。
  G1＝明年成長 < 今年成長；修正 < 0 是 G2 的一半，另一半（股價比 91 天前高）在 bubble 用指數收盤判斷。
過去（替代資料）：
  · 專業預測者調查（S&P 500）：每季調查的今年成長、明年成長、明年預估比上一季調查的修正；
  · 實際值（那斯達克科技業獲利、費半全球半導體銷售、台股外銷訂單、S&P 500 對照用的企業整體獲利）：
    年增率比 2 季（6 個月）前低＝G1；合計（平均）比 1 季（3 個月）前低＝G2 的一半。
"""
from __future__ import annotations

import re

from . import bubspec as BS

ROW = ("sh", "e0", "e1", "ea", "e1o", "cap")         # est_rows_* 回傳的每列欄位


# ── 分析師預估 ────────────────────────────────────────────────────────────

def pick_fx(fc: str | None, fx: dict, px: float | None, e0: float | None, e1: float | None) -> float | None:
    """美股預估的幣別（第 11.2 節）：財報幣別是美元 → 1；不是 → 股價 ÷（預估 × 匯率）落在 EST_PE_RANGE 就換匯，
    否則當作預估已經是美元（例：台積電 ADR 財報幣別標新台幣、預估卻是每 ADR 美元）。
    判斷用今年預估，≤ 0 改用明年預估，兩個都 ≤ 0 就換匯。沒有匯率 → None（這家公司不算）。"""
    if not fc or fc == "USD":
        return 1.0
    r = fx.get(fc)
    if not r:
        return None
    eps = e0 if e0 is not None and e0 > 0 else (e1 if e1 is not None and e1 > 0 else None)
    if eps is None or not px:
        return r
    lo, hi = BS.EST_PE_RANGE
    return r if lo <= px / (eps * r) <= hi else 1.0


def _y(rec: dict, key: str) -> tuple:
    y = (rec or {}).get(key) or {}
    e, t = y.get("e") or [None] * 5, y.get("t") or [None] * 5
    return e, t


def est_row(rec: dict, sh: float | None, cap: float | None, mult: float = 1.0) -> tuple | None:
    """一家公司 → (股數, 今年, 明年, 去年, 明年 90 天前, 市值)；預估乘 mult（匯率）。缺任一項 → None。"""
    e0a, _ = _y(rec, "y0")
    e1a, t1 = _y(rec, "y1")
    e0, ea, e1, e1o = e0a[0], e0a[4], e1a[0], t1[4]
    if not sh or sh <= 0 or None in (e0, ea, e1, e1o):
        return None
    return (float(sh), e0 * mult, e1 * mult, ea * mult, e1o * mult, float(cap or 0.0))


def est_rows_tw(yh: dict, shares: dict, close: dict) -> dict:
    """台股：yahoo.json 的 "s"（{代號: 紀錄}）＋官方發行股數＋收盤 → {代號: 列}。Yahoo 標成其他幣別的公司不算。"""
    out = {}
    for c, rec in (yh or {}).items():
        if rec.get("cur"):
            continue
        sh, px = shares.get(c), close.get(c)
        r = est_row(rec, sh, (sh or 0) * (px or 0))
        if r:
            out[c] = r
    return out


def est_rows_us(recs: dict, quotes: dict, fx: dict, syms) -> dict:
    """美股：Yahoo 紀錄＋v7 報價（{代號: [市值, 股數, 股價, 財報幣別]}）＋匯率 → {代號: 列}（預估換成美元）。"""
    out = {}
    for s in syms:
        rec, q = recs.get(s), quotes.get(s)
        if not rec or not q:
            continue
        cap, sh, px, fc = (list(q) + [None] * 4)[:4]
        e0a, _ = _y(rec, "y0")
        e1a, _ = _y(rec, "y1")
        m = pick_fx(fc, fx, px, e0a[0], e1a[0])
        if m is None:
            continue
        r = est_row(rec, sh, cap, m)
        if r:
            out[s] = r
    return out


def aggregate(rows: dict, cap_all: float | None) -> dict:
    """加總（第 11.2 節）→ {"n", "cov", "g0", "g1", "rev", "G1", "R"}。R＝修正 < 0（G2 的預估那一半）。
    涵蓋（用到的公司市值 ÷ 全部成分股市值）< EST_COVER_MIN → G1、R 都是 None。"""
    E0 = sum(r[0] * r[1] for r in rows.values())
    E1 = sum(r[0] * r[2] for r in rows.values())
    Ea = sum(r[0] * r[3] for r in rows.values())
    E1o = sum(r[0] * r[4] for r in rows.values())
    cap = sum(r[5] for r in rows.values())
    cov = cap / cap_all if cap_all else None
    g0 = E0 / Ea - 1.0 if Ea > 0 else None
    g1 = E1 / E0 - 1.0 if E0 > 0 else None
    rev = E1 / E1o - 1.0 if E1o > 0 else None
    ok = cov is not None and cov >= BS.EST_COVER_MIN and rows
    out = {"n": len(rows), "cov": cov, "g0": g0, "g1": g1, "rev": rev,
           "G1": (g1 < g0) if ok and g0 is not None and g1 is not None else None,
           "R": (rev < 0) if ok and rev is not None else None}
    return out


def top_contrib(rows: dict, k: int = 5) -> list:
    """明年預估 90 天修正（加總裡的金額）最大的公司：[(代號, 修正占加總的比例, 該公司修正 %)]（只顯示）。"""
    E1o = sum(r[0] * r[4] for r in rows.values())
    if E1o <= 0:
        return []
    items = []
    for c, r in rows.items():
        d = r[0] * (r[2] - r[4])
        items.append((c, d / E1o, (r[2] / r[4] - 1.0) if r[4] else None))
    items.sort(key=lambda x: -abs(x[1]))
    return items[:k]


# ── 專業預測者調查（S&P 500 的過去） ────────────────────────────────────────

def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def spf_parse(rows: list) -> dict:
    """水準檔（第一列表頭：YEAR、QUARTER、CPROF1～6、CPROFA、CPROFB）→ {"YYYY-Qq": [CPROF1, …, CPROF6, A, B]}（#N/A＝None）。"""
    if not rows:
        return {}
    hdr = [str(h).strip().upper() if h is not None else "" for h in rows[0]]
    need = ["YEAR", "QUARTER"] + [f"CPROF{i}" for i in range(1, 7)] + ["CPROFA", "CPROFB"]
    idx = [hdr.index(k) if k in hdr else None for k in need]
    if idx[0] is None or idx[1] is None:
        return {}
    out = {}
    for r in rows[1:]:
        y, q = _num(r[idx[0]]), _num(r[idx[1]])
        if not y or not q:
            continue
        out[f"{int(y)}-Q{int(q)}"] = [None if j is None else _num(r[j]) for j in idx[2:]]
    return out


def _prevq(y: int, q: int) -> tuple[int, int]:
    return (y, q - 1) if q > 1 else (y - 1, 4)


def spf_avail(y: int, q: int) -> str:
    """調查第 q 季在第 3q−1 個月月底才算拿得到。"""
    m = 3 * q - 1
    last = {2: 28, 5: 31, 8: 31, 11: 30}[m]
    if m == 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        last = 29
    return f"{y:04d}-{m:02d}-{last:02d}"


def spf_table(raw: dict) -> list[dict]:
    """→ 每季調查 [{"k", "avail", "g0", "g1", "rev", "G1", "R"}]（第 11.3 節）。"""
    S = {}
    for k, v in raw.items():
        m = re.match(r"^(\d{4})-Q([1-4])$", k)
        if m and v:
            S[(int(m.group(1)), int(m.group(2)))] = v
    out = []
    for (y, q) in sorted(S):
        v = S[(y, q)]
        A, B = v[6], v[7]
        if (y, q) < BS.SPF_FIRST_ANNUAL or A is None or B is None:
            continue
        base_k = [(y, 1), (y - 1, 4), (y - 1, 3), (y - 1, 2)]
        base = [S.get(k, [None])[0] for k in base_k]
        g0 = None
        if y != BS.SPF_BREAK[0] and all(b is not None and b > 0 for b in base) and (y, q) >= (y, 1):
            g0 = A / (sum(base) / 4.0) - 1.0
        g1 = B / A - 1.0 if A > 0 else None
        pv = S.get(_prevq(y, q))
        rev = None
        if (y, q) != BS.SPF_BREAK and pv and pv[7] is not None and pv[7] > 0:
            rev = (B if q > 1 else A) / pv[7] - 1.0
        out.append({"k": f"{y}-Q{q}", "avail": spf_avail(y, q), "g0": g0, "g1": g1, "rev": rev,
                    "G1": (g1 < g0) if g0 is not None and g1 is not None else None,
                    "R": (rev < 0) if rev is not None else None})
    return out


# ── 科技業獲利（那斯達克的 E 與 G 的過去） ──────────────────────────────────

def _sum(vals: list) -> float | None:
    return sum(vals) if vals and all(v is not None for v in vals) else None


def tech_series(q_raw: dict, a_raw: dict) -> dict:
    """新舊分類接成一條季序列 {季底 YYYY-MM: 年率百萬美元}（第 11.3 節的接法）。
    q_raw＝{季底: {代碼: 值}}、a_raw＝{"YYYY": {代碼: 值}}；代碼見 bubspec.TECH_*。"""
    def qsum(codes, k):
        d = q_raw.get(k) or {}
        return _sum([d.get(c) for c in codes])

    def asum(codes, y):
        d = a_raw.get(str(y)) or {}
        return _sum([d.get(c) for c in codes])

    na = [asum(BS.TECH_NAICS_A, y) for y in BS.TECH_K1_YEARS]
    sa = [asum(BS.TECH_SIC_C_A, y) for y in BS.TECH_K1_YEARS]
    k1 = sum(na) / sum(sa) if all(x is not None for x in na + sa) and sum(sa) > 0 else None
    yq = [f"{BS.TECH_K2_YEAR}-{m:02d}" for m in (3, 6, 9, 12)]
    c87 = [qsum(BS.TECH_SIC_C_Q, k) for k in yq]
    b87 = [qsum(BS.TECH_SIC_B_Q, k) for k in yq]
    k2 = sum(c87) / sum(b87) if all(x is not None for x in c87 + b87) and sum(b87) > 0 else None
    out: dict = {}
    for k in sorted(q_raw):
        v = qsum(BS.TECH_NAICS_Q, k)
        if v is None and k1 is not None:
            c = qsum(BS.TECH_SIC_C_Q, k)
            if c is not None:
                v = c * k1
            elif k2 is not None:
                b = qsum(BS.TECH_SIC_B_Q, k)
                v = b * k1 * k2 if b is not None else None
        if v is not None and v > 0:
            out[k] = v
    return out


# ── 實際值的 G1、G2（替代資料） ─────────────────────────────────────────────

def _ym_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + k
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def proxy_flags(F: dict, kind: str, nsum: int) -> dict:
    """{期別 YYYY-MM: 值} → {期別: {"g", "S", "G1", "R"}}。kind＝"q"（季資料：近 nsum 季平均）或 "m"（月資料：近 nsum 個月合計）。
    g＝年增率；G1＝g 比 PROXY_G1_BACK 期前低；R＝合計（平均）比 PROXY_G2_BACK 期前低。"""
    step = 3 if kind == "q" else 1
    S = {}
    for k in F:
        ks = [_ym_add(k, -step * j) for j in range(nsum)]
        vs = [F.get(x) for x in ks]
        if all(v is not None for v in vs):
            S[k] = sum(vs) / (nsum if kind == "q" else 1)
    g = {k: S[k] / S[_ym_add(k, -12)] - 1.0 for k in S if S.get(_ym_add(k, -12)) and S[_ym_add(k, -12)] > 0 and S[k] > 0}
    b1, b2 = BS.PROXY_G1_BACK[kind] * step, BS.PROXY_G2_BACK[kind] * step
    out = {}
    for k in S:
        g0, gb = g.get(k), g.get(_ym_add(k, -b1))
        sb = S.get(_ym_add(k, -b2))
        out[k] = {"g": g0, "S": S[k], "G1": (g0 < gb) if g0 is not None and gb is not None else None,
                  "R": (S[k] < sb) if sb is not None else None}
    return out
