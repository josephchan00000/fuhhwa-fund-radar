"""台指期早盤策略的訊號：落差 E（docs/lab_fut_plan.md 第 4.1 節；規格在 arm/lab/futspec.py）。

  E ＝ 估算的開盤指數 ＋ 平常的價差 − 決定時間的期貨價
  平常的價差 ＝ 前一個交易日 13:30:00 的期貨價（同一個月份契約，13:30:00 以前最後一筆）− 13:30 收盤指數
               ＋ 今天除權息讓加權指數開盤少掉的點數（證交所除權息計算結果 data/lab/divtw）

E 是正的：現貨估得比期貨強，做多期貨；負的做空。

估算的開盤水準：偷看版＝每檔上市普通股今天真正的開盤價、照前一天的市值比重換算（open_full；不是證交所 09:00:05 的
「開盤指數」，那時很多股票還沒開出來）；即時版＝同一個式子、開盤價換成決定時間當下看得到的試撮價（est_realtime，futspec VER 2）。
契約：當天的近月；結算日（每月第三個星期三，遇休市順延）改用下個月。
"""
from __future__ import annotations

from datetime import date, timedelta

from .. import twholidays as H
from . import futdata as F
from . import store

S_1330 = 13 * 3600 + 30 * 60
TAIEX_REF_SHARES = "v3me_tw"        # 月底收盤＋發行股數（算加權指數裡各股的比重）


def settle_day(y: int, m: int) -> date:
    """台指期 y 年 m 月契約的最後交易日：第三個星期三，遇休市（含颱風臨時休市）順延到下一個交易日。"""
    d = date(y, m, 15)
    while d.weekday() != 2:
        d += timedelta(days=1)
    yrs = H.load()
    while d.weekday() >= 5 or H.is_closed(d, yrs):
        d += timedelta(days=1)
    return d


def contract_for(d: str, contracts) -> str | None:
    """當天要交易的契約：近月；近月今天結算就改用下個月。"""
    c = F.near(d, contracts)
    if c is None:
        return None
    dd = date.fromisoformat(d)
    if c == f"{dd:%Y%m}" and dd == settle_day(dd.year, dd.month):
        nx = sorted(k for k in contracts if k > c)
        return nx[0] if nx else None
    return c


def weights(dprev: str) -> dict[str, float]:
    """前一個交易日收盤時，上市普通股（4 碼、非 0 開頭）占加權指數的比重：最近一個月底的發行股數 × 前一天收盤。"""
    ms = store.dates(TAIEX_REF_SHARES)
    use = [m for m in ms if m <= dprev[:7]] or ms
    if not use:
        return {}
    sh = (store.read(TAIEX_REF_SHARES, use[-1]) or {}).get("s") or {}
    qt = (store.read("mkt", dprev) or {}).get("q_tw") or {}
    cap = {}
    for c, (px, n) in sh.items():
        if len(c) == 4 and not c.startswith("0") and n:
            q = qt.get(c)
            cl = q[3] if q and q[3] else px
            if cl:
                cap[c] = cl * n
    tot = sum(cap.values())
    return {c: v / tot for c, v in cap.items()} if tot else {}


def div_points(d: str, dprev: str, i_prev: float) -> tuple[float, list]:
    """今天除權息讓加權指數開盤少掉的點數，與影響最大的三檔 [(點數, 代號)]。"""
    rows = [r for r in (store.read("divtw", d[:4]) or {}).get("rows") or [] if r[0] == d]
    if not rows:
        return 0.0, []
    w = weights(dprev)
    tot, top = 0.0, []
    for r in rows:
        c, prev, ref = r[1], r[4], r[5]
        if c in w and prev and ref:
            x = w[c] * (prev - ref) / prev * i_prev
            tot += x
            top.append((round(x, 2), c))
    return tot, sorted(top, reverse=True)[:3]


def day_inputs(d: str, dprev: str) -> dict | None:
    """一天的訊號材料：契約、當天的逐筆、前一天的價差、除權息點數（i_open＝證交所 09:00:05 指數，只當參考）。缺任何一樣回 None。"""
    T, Tp = F.load_day(d), F.load_day(dprev)
    I, Ip = F.load_idx(d), F.load_idx(dprev)
    if not (T and Tp and I and Ip):
        return None
    c = contract_for(d, T)
    if not c or c not in Tp:
        return None
    f1330 = None
    for s, p, _q, _a in Tp[c]:
        if s > S_1330:
            break
        f1330 = p
    if f1330 is None:
        return None
    i_close = Ip[-1]
    dv, top = div_points(d, dprev, i_close)
    return {"d": d, "dprev": dprev, "c": c, "ticks": T[c], "f1330": f1330, "i_close": i_close,
            "basis": f1330 - i_close, "div": dv, "div_top": top, "i_open": I[1]}


def open_full(d: str, dprev: str, i_prev: float, cover_min: float) -> float | None:
    """偷看版的開盤水準：每檔上市普通股今天的開盤價，照前一天的市值比重換算（前一天收盤指數 × Σ 比重 × 開盤價／前一天收盤）。
    開盤價找得到的比重合計不到 cover_min 回 None。除權息股開盤價本來就是除息後的價格，所以除息讓指數少掉的點數已經在裡面。"""
    q = (store.read("mkt", d) or {}).get("q_tw") or {}
    qp = (store.read("mkt", dprev) or {}).get("q_tw") or {}
    if not q or not qp:
        return None
    w = weights(dprev)
    num = cov = 0.0
    for c, wi in w.items():
        o = (q.get(c) or [None])[0]
        cp = (qp.get(c) or [None] * 4)[3]
        if o and cp:
            num += wi * o / cp
            cov += wi
    if cov < cover_min:
        return None
    return i_prev * num / cov


def _sec(t) -> int | None:
    """MIS 的資料時間 "HH:MM:SS" → 當天第幾秒（台北）。"""
    try:
        h, m, x = str(t).split(":")
        return int(h) * 3600 + int(m) * 60 + int(x)
    except (TypeError, ValueError):
        return None


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def latest_quotes(recs: list[dict], decide_s: float) -> dict[str, dict]:
    """盤前取樣（futpre.decode 的結果）→ 每檔在決定時間當下看得到的最新資料：只看收到時間 ≤ decide_s 的回應，
    同一檔取資料時間（MIS 的 t）最新的那一筆，資料時間相同取比較晚收到的（MIS 有時候回比上一次還舊的資料）。"""
    best: dict[str, tuple[int, dict]] = {}
    for r in recs:
        if r.get("k") != "tw" or r.get("t1") is None or r["t1"] > decide_s:
            continue
        for c, m in (r.get("r") or {}).items():
            if c in ("t00", "o00"):
                continue
            ts = _sec(m.get("t"))
            if ts is None:
                continue
            if c not in best or ts >= best[c][0]:
                best[c] = (ts, m)
    return {c: dict(m, _ts=ts) for c, (ts, m) in best.items()}


def est_realtime(recs: list[dict], dprev: str, i_prev: float, *, decide_s: float, fresh_s: int,
                 cover_min: float, field: str = "pz") -> dict:
    """即時版的開盤水準（futspec VER 2）：前一天收盤指數 × Σ 比重 × 試撮價／前一天官方收盤 ÷ Σ 比重。
    只用決定時間當下看得到、資料時間 ≥ fresh_s、試撮價是正數、前一天有官方收盤的股票；比重＝weights(dprev)。
    回 {"est": 估算（比重不到 cover_min 是 None）, "cov": 用到的比重合計, "n": 用到幾檔, "stale": 資料太舊幾檔, "nopx": 沒有試撮價幾檔}。"""
    q = latest_quotes(recs, decide_s)
    w = weights(dprev)
    qp = (store.read("mkt", dprev) or {}).get("q_tw") or {}
    num = cov = 0.0
    n = stale = nopx = 0
    for c, m in q.items():
        wi = w.get(c)
        if not wi:
            continue
        if m["_ts"] < fresh_s:
            stale += 1
            continue
        px = _num(m.get(field))
        cp = _num((qp.get(c) or [None] * 4)[3])
        if px is None or cp is None:
            nopx += 1
            continue
        num += wi * px / cp
        cov += wi
        n += 1
    est = i_prev * num / cov if cov >= cover_min and cov > 0 else None
    return {"est": est, "cov": round(cov, 4), "n": n, "stale": stale, "nopx": nopx}


def edge(inp: dict, f_now: float, i_est: float) -> float:
    """E ＝ 估算的開盤指數 ＋ 前一天價差 ＋ 除權息點數 − 現在的期貨價。"""
    return i_est + inp["basis"] + inp["div"] - f_now
