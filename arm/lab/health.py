"""籌碼雷達：推薦策略健檢的資料層（docs/lab_selfopt_plan.md 第 3、4 節）。

每一筆交易的進場特徵（名次、開盤跳空、大盤在不在 200 日均線上、進場前 20 日漲幅、市值）與持有路徑
（持有第 d 天的累積報酬），回測與前瞻用同一套算法。全部是純函式：輸入價格陣列與交易，輸出數字，
不改任何策略的回測結果。

口徑：
  · 第 d 天＝進場日算第 1 天；持有路徑＝進場日開盤 → 第 d 天收盤的累積報酬（%，未扣成本；收盤缺值沿用前一天）。
  · 開盤跳空＝進場日開盤 ÷ 前一個交易日收盤 − 1；進場前 20 日漲幅＝決定日收盤 ÷ 20 個交易日前收盤 − 1（%）。
  · 大盤狀態＝決定日加權指數收盤是否在 200 日均線（含）之上；當天缺值往前找最多 10 個交易日。
  · 一批（同一期買進的名單）的路徑＝各檔路徑逐日平均；臺灣50 同一次審核各檔買進日不同，從第一筆買進日起算，
    已賣出的固定在賣出時的報酬、還沒買的不算。
  · 逐筆報酬（扣成本）：成本依回測方法 v3（大型股來回 0.48%、中型股 0.68%）；決定日市值不到 300 億一律用中型股成本。
"""
from __future__ import annotations

import statistics

from . import bt3
from .optim import GAP_BINS, REG_MA

QS = tuple(range(0, 101, 5))       # 分位數表：0、5、…、100 百分位
PATH_MIN_N = 20                     # 持有第 d 天還在的筆數少於這個，分位數表就停在前一天
PATH_MIN_EV = 5                     # 臺灣50 一次審核一批、回測只有 8 次：一批的分位數表至少 5 次
PRE_N = 20                          # 進場前 N 個交易日漲幅
LOOK = 10                           # 缺值往前找幾個交易日


# ── 價格小工具 ─────────────────────────────────────────────────────────

def lc(xs: list, i: int, look: int = LOOK):
    """xs[i]，缺值往前找最多 look 個交易日；找不到回 None。"""
    for k in range(i, max(i - look, 0) - 1, -1):
        if 0 <= k < len(xs) and xs[k]:
            return xs[k]
    return None


def gap(S: dict, j: int) -> float | None:
    """進場日開盤跳空（%）。"""
    o = S["o"][j] if 0 <= j < len(S["o"]) else None
    pc = lc(S["c"], j - 1) if j >= 1 else None
    return round((o / pc - 1) * 100, 2) if o and pc else None


def pre(S: dict, t: int, n: int = PRE_N) -> float | None:
    """決定日前 n 個交易日漲幅（%）。"""
    if t - n < 0:
        return None
    a, z = lc(S["c"], t - n), lc(S["c"], t)
    return round((z / a - 1) * 100, 2) if a and z else None


def reg_line(idx: list, n: int = REG_MA) -> list:
    """加權指數 n 日簡單均線（與 idx 對齊）。"""
    from .ta import sma
    return sma(idx, n)


def regime(idx: list, ma: list, t: int) -> bool | None:
    """決定日加權指數收盤是否在均線（含）之上；缺值往前找最多 10 個交易日，都沒有回 None。"""
    for k in range(t, max(t - LOOK, 0) - 1, -1):
        if 0 <= k < len(idx) and idx[k] and ma[k]:
            return idx[k] >= ma[k]
    return None


def bucket(cap: float | None) -> str:
    """成本分組：市值 ≥300 億＝大型股，其餘（含不到 50 億、沒有市值）＝中型股成本。"""
    return "L" if cap and cap >= bt3.BUCKET["L"]["cap"][0] else "M"


def net(gross: float, b: str) -> float:
    """毛報酬（比例）→ 扣成本後報酬（%），同 bt3.account 的成本算法。"""
    return ((1 + gross) * (1 - bt3.side_cost(b, True)) / (1 + bt3.side_cost(b, False)) - 1) * 100


# ── 持有路徑 ─────────────────────────────────────────────────────────

def path(S: dict, j: int, i: int | None, op: bool = False) -> list:
    """j 開盤進場 → 第 1..n 天收盤的累積報酬（%）。i＝出場日（None＝持有中，算到最後一天）；
    op＝第 i 天開盤賣出（路徑到前一天收盤為止）。"""
    o = S["o"][j] if 0 <= j < len(S["o"]) else None
    if not o:
        return []
    T = len(S["c"])
    end = T - 1 if i is None else (i - 1 if op else i)
    out, last = [], None
    for k in range(j, min(end, T - 1) + 1):
        c = S["c"][k]
        if c:
            last = c
        out.append(round((last / o - 1) * 100, 2) if last else None)
    return out


def mean_path(ps: list[list]) -> list:
    """多條路徑逐日平均（每天只平均當天有值的）。"""
    n = max((len(p) for p in ps), default=0)
    out = []
    for d in range(n):
        v = [p[d] for p in ps if d < len(p) and p[d] is not None]
        out.append(round(statistics.mean(v), 2) if v else None)
    return out


def basket(S_of, picks: list[str], j: int, x: int) -> list:
    """同一天（j 開盤）買進的一批：各檔到第 x 天收盤的路徑逐日平均；j 沒有開盤價的不算。S_of(代號)→價格陣列。"""
    ps = [path(S_of(c), j, x) for c in picks]
    return mean_path([p for p in ps if p])


def staggered(items: list[tuple], i0: int) -> list:
    """買進日不同的一批（臺灣50 同一次審核）：items＝[(買進日 j, 路徑, 出場毛報酬% 或 None＝持有中)]，
    第 d 天＝i0 起第 d 個交易日：已買進、還在持有的用當天累積報酬；已賣出的固定在出場報酬；還沒買的不算。"""
    if not items:
        return []
    ends = [j + len(p) - 1 for j, p, _ in items if p]
    if not ends:
        return []
    last = max(ends)
    out = []
    for m in range(i0, last + 1):
        v = []
        for j, p, ex in items:
            if m < j or not p:
                continue
            k = m - j
            if k < len(p):
                if p[k] is not None:
                    v.append(p[k])
            elif ex is not None:
                v.append(ex)
        out.append(round(statistics.mean(v), 2) if v else None)
    return out


# ── 分位數表與百分位 ──────────────────────────────────────────────────

def pct(vs: list[float], q: float) -> float | None:
    """排序好的數列的第 q 百分位（0～100，線性內插）。"""
    if not vs:
        return None
    k = (len(vs) - 1) * q / 100
    f = int(k)
    c = min(f + 1, len(vs) - 1)
    return vs[f] + (vs[c] - vs[f]) * (k - f)


def qtable(paths: list[list], min_n: int = PATH_MIN_N) -> dict:
    """各筆（或各批）持有路徑 → 持有第 d 天的分位數表：{"q": [[QS 各百分位]…], "n": [第 d 天的筆數…]}。
    只收持有到第 d 天的；某一天少於 min_n 筆就停在前一天。"""
    rows, ns = [], []
    n = max((len(p) for p in paths), default=0)
    for d in range(n):
        v = sorted(p[d] for p in paths if d < len(p) and p[d] is not None)
        if len(v) < min_n:
            break
        rows.append([round(pct(v, q), 2) for q in QS])
        ns.append(len(v))
    return {"q": rows, "n": ns}


def pct_in(row: list[float], x: float | None) -> float | None:
    """分位數表的一列 → x 的百分位（0～100，線性內插；低於最小＝0、高於最大＝100）。"""
    if x is None or not row:
        return None
    if x <= row[0]:
        return 0.0
    if x >= row[-1]:
        return 100.0
    for k in range(1, len(row)):
        if x <= row[k]:
            lo, hi = row[k - 1], row[k]
            f = (x - lo) / (hi - lo) if hi > lo else 0.0
            return round(QS[k - 1] + f * (QS[k] - QS[k - 1]), 1)
    return 100.0


def at_day(tab: dict, d: int, x: float | None) -> float | None:
    """持有第 d 天（從 1 起）報酬 x 在分位數表的百分位；表沒有到第 d 天回 None。"""
    q = (tab or {}).get("q") or []
    return pct_in(q[d - 1], x) if 1 <= d <= len(q) else None


# ── 進場條件分組（第 4 節） ─────────────────────────────────────────────

def cuts(xs: list) -> list | None:
    """三等分的兩個切點（33.3、66.7 百分位）；少於 3 個值回 None。"""
    v = sorted(x for x in xs if x is not None)
    return [round(pct(v, 100 / 3), 4), round(pct(v, 200 / 3), 4)] if len(v) >= 3 else None


def tercile(x: float | None, cs: list | None) -> int | None:
    """0＝低、1＝中、2＝高。"""
    if x is None or not cs:
        return None
    return 0 if x < cs[0] else 1 if x < cs[1] else 2


def gap_bin(g: float | None) -> int | None:
    """開盤跳空（%）→ GAP_BINS 的第幾組。"""
    if g is None:
        return None
    x = g / 100
    for n, (lo, hi, _) in enumerate(GAP_BINS):
        if (lo is None or x >= lo) and (hi is None or x < hi):
            return n
    return None


# ── 逐筆交易（含進場特徵） ─────────────────────────────────────────────

def reg_lookup(reg_map: dict, cal: list[str], t: int) -> bool | None:
    """{日期: 是否在均線上}（packtest.regime_map，五年日線算）→ 決定日的大盤狀態；缺值往前找最多 10 個交易日。"""
    for k in range(t, max(t - LOOK, 0) - 1, -1):
        v = reg_map.get(cal[k]) if 0 <= k < len(cal) else None
        if v is not None:
            return v
    return None


def rec(S: dict, cal: list[str], c: str, t: int, j: int, i: int | None, op: bool, r: float | None, *,
        reg: bool | None, cap: float | None = None, rk: int | None = None, b: str | None = None,
        fw_from: str | None = None) -> dict:
    """一筆交易：t＝決定日、j＝進場日（開盤）、i＝出場日（None＝持有中）、op＝開盤賣出、r＝扣成本後報酬（%）；
    reg＝決定日大盤是否在 200 日均線上；b＝成本分組（定期換股策略用策略本身的範圍；沒給就依市值）；
    cap＝決定日市值（元，輸出時換成億元）。"""
    return {"c": c, "d": cal[t], "t": t, "j": j, "i": i, "op": bool(op), "r": None if r is None else round(r, 2),
            "rk": rk, "b": b or bucket(cap), "cap": None if cap is None else round(cap / 1e8),
            "gap": gap(S, j), "pre": pre(S, t), "reg": reg,
            "fw": bool(fw_from and cal[t] >= fw_from)}


def from_account(P, periods: list, log: list, b: str, *, scores: dict | None = None, fw_from: str | None = None,
                 ma: list | None = None) -> dict:
    """定期換股策略（財報、月營收）：bt3.account 的紀錄 → {"tr": 逐筆, "bk": 每期一批的路徑}。
    P＝packtest.Px 介面（s、cap、cal、idx 或 D.taiex）；名次＝決定日分數由高到低；每期一批＝當期名單（含續抱股）
    從當期第一天開盤起算（同後台「持有中」的算法）。"""
    from .trades import trips, trip_ret
    idx = P.idx if hasattr(P, "idx") else P.D.taiex()
    ma = ma if ma is not None else reg_line(idx)
    order: dict[int, dict] = {}

    def rank(t, c):
        sc = (scores or {}).get(t) or {}
        if t not in order:
            order[t] = {z: n + 1 for n, z in enumerate(sorted(sc, key=lambda z: (-sc[z], z)))}
        return order[t].get(c)
    tp, _ = trips(log)
    out = []
    for q in tp:
        t = periods[q["k0"]][0]
        r = trip_ret(q["o"], q["p"], b) if q["i"] is not None else None
        cap = (P.cap.get(q["c"]) or [None] * P.T)[t]
        out.append(rec(P.s[q["c"]], P.cal, q["c"], t, q["j"], q["i"], q["op"] or False, r, reg=regime(idx, ma, t), cap=cap,
                       rk=rank(t, q["c"]), b=b, fw_from=fw_from))
    bk = []
    for t, x, picks in periods:
        if t + 1 >= P.T or x is None:
            continue
        p = basket(lambda c: P.s[c], picks, t + 1, min(x, P.T - 1))
        if p:
            bk.append({"d": P.cal[t], "t": t, "p": p, "fw": bool(fw_from and P.cal[t] >= fw_from)})
    return {"tr": out, "bk": bk}


def from_trades(D, trs: list[dict], *, cap_of=None, fw_from: str | None = None, cost: float = 0.585,
                rank_key: str | None = None, group: str | None = None, reg_map: dict | None = None, series=None,
                b_fix: str | None = None) -> dict:
    """逐筆型策略（共識加碼、長線、臺灣50）的交易紀錄（strategy／growth／tw50study 的 dict：c, d, bd, sd, entry, so, r…）
    → {"tr": 逐筆（含持有中；每筆附路徑 path 與出場毛報酬 ex）}。r 原本扣舊成本 cost%，換成 v3 成本（依決定日市值分組；
    b_fix＝固定分組，臺灣50 算大型股）。cap_of(c, t)→市值；rank_key＝名次依據欄位（同一 group 內由高到低，
    臺灣50 用 40 日漲幅 mom）；group＝分批欄位（臺灣50＝review）；series(代號)→價格陣列（預設 D.series、自帶快取）；
    reg_map＝packtest.regime_map（五年日線；兩年的每日資料前 200 天算不出年線），沒給就用 D.taiex() 算。
    沒進場（skip）、候選中（cand）的不算。"""
    ix = D.ix
    cache: dict = {}

    def S_of(c):
        if c not in cache:
            cache[c] = (series or D.series)(c)
        return cache[c]
    idx = D.taiex()
    ma = reg_line(idx) if reg_map is None else None
    ranks: dict = {}
    if rank_key and group:
        g: dict = {}
        for x in trs:
            if x.get("st") in ("closed", "open") and x.get(rank_key) is not None:
                g.setdefault(x.get(group), []).append(x)
        for k, xs in g.items():
            for n, x in enumerate(sorted(xs, key=lambda x: (-x[rank_key], x["c"]))):
                ranks[(k, x["c"], x.get("bd"))] = n + 1
    out = []
    for x in trs:
        st = x.get("st")
        if st not in ("closed", "open") or x.get("d") not in ix or x.get("bd") not in ix:
            continue
        t, j = ix[x["d"]], ix[x["bd"]]
        i = ix.get(x.get("sd")) if st == "closed" else None
        if st == "closed" and i is None:
            continue
        cap = cap_of(x["c"], t) if cap_of else None
        b = b_fix or bucket(cap)
        r = None
        if st == "closed" and x.get("r") is not None:
            r = x["r"] + cost - bt3.rt_cost(b) * 100
        S = S_of(x["c"])
        rg = reg_lookup(reg_map, D.cal, t) if reg_map is not None else regime(idx, ma, t)
        rr = rec(S, D.cal, x["c"], t, j, i, bool(x.get("so")), r, reg=rg, cap=cap,
                 rk=ranks.get((x.get(group), x["c"], x.get("bd"))) if rank_key else None, b=b, fw_from=fw_from)
        if group:
            rr["g"] = x.get(group)
        rr["path"] = path(S, j, i, bool(x.get("so")))
        rr["ex"] = None if st != "closed" or not x.get("entry") or not x.get("exit") else \
            round((x["exit"] / x["entry"] - 1) * 100, 2)
        out.append(rr)
    return {"tr": out}


def review_baskets(trs: list[dict]) -> list[dict]:
    """臺灣50：同一次審核（g）的各筆 → 一批的路徑（從第一筆買進日起算，staggered）。"""
    g: dict = {}
    for x in trs:
        g.setdefault(x.get("g"), []).append(x)
    out = []
    for k, xs in g.items():
        i0 = min(x["j"] for x in xs)
        p = staggered([(x["j"], x.get("path") or [], x.get("ex")) for x in xs], i0)
        if p:
            out.append({"d": min(x["d"] for x in xs), "g": k, "t": min(x["t"] for x in xs), "p": p,
                        "fw": any(x.get("fw") for x in xs)})
    return sorted(out, key=lambda b: b["d"])


# ── 回測參考：燈號抽樣用的單位報酬、持有路徑分位數表、拆解用的逐筆（第 3、4 節） ─────────────────

_TRC = ("d", "r", "rk", "gap", "pre", "reg", "cap")   # 參考檔逐筆欄位（緊湊陣列）


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.mean(xs) if xs else None


def per_review(trs: list[dict]) -> list[float]:
    """臺灣50：同一次審核（g）已出場各筆的報酬平均＝一個單位；依決定日排序。"""
    g: dict = {}
    for x in trs:
        if x.get("r") is not None:
            g.setdefault(x.get("g"), []).append(x)
    rows = sorted(((min(y["d"] for y in v), statistics.mean(y["r"] for y in v)) for v in g.values()))
    return [round(r, 2) for _, r in rows]


def ref_pack(units: list[float], paths: list[list], trs: list[dict], *, min_n: int = PATH_MIN_N) -> dict:
    """一條策略的回測參考：u＝單位報酬（扣成本，%）、q＝持有路徑分位數表、cut＝前 20 日漲幅與市值的三等分切點、
    tr＝逐筆 [決定日, 報酬, 名次, 跳空, 前 20 日漲幅, 大盤在均線上(1/0), 市值(億)]（只收已出場的）。"""
    cl = [x for x in trs if x.get("r") is not None]
    return {"u": [round(x, 2) for x in units if x is not None], "q": qtable(paths, min_n),
            "cut": {"pre": cuts([x.get("pre") for x in cl]), "cap": cuts([x.get("cap") for x in cl])},
            "tr": [[x["d"], x["r"], x.get("rk"), x.get("gap"), x.get("pre"),
                    None if x.get("reg") is None else int(bool(x["reg"])), x.get("cap")] for x in cl]}


def ref_periodic(P, E, k: str, src: str, b: str, *, since: str, umin: int, n: int = 5, eps=None, rev=None) -> dict:
    """財報、月營收（v3 長歷史面板）：現行規則（前 n 檔）跑一次 → 起算日之前的每期報酬、每期一批的路徑、逐筆。"""
    from . import bt3s
    rows = bt3s.p3_rows(P, E, b, P.codes, eps, 60) if src == "p3" else bt3s.p7_rows(P, E, b, P.codes, rev)
    done = [r for r in rows if r[1] is not None and P.cal[r[0]] < since]
    pk = bt3s.pick(done, 0.0, n, False, umin)
    log: list = []
    acc = bt3.account(P, pk, b, log=log)
    h = from_account(P, pk, log, b, scores={t: sc for t, _, sc in done})
    units = [u["r"] for u in acc["units"] if u.get("r") is not None]
    return ref_pack(units, [x["p"] for x in h["bk"]], h["tr"])


def ref_trades(trs: list[dict], since: str, *, event: bool = False) -> dict:
    """逐筆型策略：起算日之前已出場的交易（from_trades 的輸出）→ 回測參考。
    事件型（臺灣50）的單位＝每次審核平均、路徑＝每次一批（至少 5 次）；其餘＝逐筆。"""
    ins = [x for x in trs if x["d"] < since]
    if event:
        return ref_pack(per_review(ins), [b["p"] for b in review_baskets(ins)], ins, min_n=PATH_MIN_EV)
    return ref_pack([x["r"] for x in ins if x.get("r") is not None],
                    [x["path"] for x in ins if x.get("r") is not None and x.get("path")], ins)


# ── 燈號（第 3c 節） ─────────────────────────────────────────────────────

def boot(ref_u: list[float], fwd_u: list[float]) -> dict:
    """前瞻平均在回測抽樣分布的百分位：從回測單位抽出和前瞻一樣多（放回抽樣）、重複 BOOT_N 次（固定種子）。
    → {pct（前瞻平均高於幾 % 的抽樣平均）, lo, hi（抽樣平均的 5～95 百分位）, ref（回測平均）}"""
    import random
    from .optim import BOOT_N, SEED
    if not ref_u or not fwd_u:
        return {"pct": None, "lo": None, "hi": None, "ref": _r2(_mean(ref_u))}
    rnd = random.Random(SEED)
    n, m = len(fwd_u), statistics.mean(fwd_u)
    ms = sorted(statistics.mean(rnd.choice(ref_u) for _ in range(n)) for _ in range(BOOT_N))
    below = sum(1 for x in ms if x < m) + 0.5 * sum(1 for x in ms if x == m)
    return {"pct": round(100 * below / len(ms), 1), "lo": _r2(pct(ms, 5)), "hi": _r2(pct(ms, 95)),
            "ref": _r2(statistics.mean(ref_u))}


def _r2(x):
    return None if x is None else round(x, 2)


# ── 依進場條件拆解（第 4 節） ─────────────────────────────────────────────

def welch_t(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb = statistics.variance(a), statistics.variance(b)
    s = (va / len(a) + vb / len(b)) ** 0.5
    return (statistics.mean(a) - statistics.mean(b)) / s if s > 0 else None


COND = (("rk", "名次"), ("gap", "開盤跳空"), ("reg", "大盤狀態"), ("pre", "進場前 20 日漲幅"), ("cap", "規模"))
TER = ("低", "中", "高")


def _labels(field: str, n_rank: int) -> list[str]:
    from .optim import GAP_BINS
    if field == "rk":
        return [f"第 {i} 名" for i in range(1, n_rank + 1)]
    if field == "gap":
        return [g[2] for g in GAP_BINS]
    if field == "reg":
        return ["年線上", "年線下"]
    return [f"{TER[i]}（三等分）" for i in range(3)]


def group_of(field: str, x: dict, cut: dict) -> int | None:
    """逐筆 → 第幾組（從 0 起；名次＝名次 − 1）。"""
    v = x.get(field)
    if v is None:
        return None
    if field == "rk":
        return int(v) - 1
    if field == "gap":
        return gap_bin(v)
    if field == "reg":
        return 0 if v else 1
    return tercile(v, (cut or {}).get(field))


def split(trs: list[dict], cut: dict, halves, *, n_rank: int = 5) -> list[list]:
    """各條件各組：[條件, 組名, 筆數, 平均報酬, 賺錢比例, 和其餘合併平均的差, Welch t, 差異明顯?]。
    halves(x)→0／1（前一半、後一半；有複驗期間的用主要／複驗期間）；差異明顯＝該組 ≥10 筆、|t| ≥ 2、
    兩半的差同方向（第 4 節）。只收已出場的。"""
    from .optim import SPLIT_MIN_N, SPLIT_T
    cl = [x for x in trs if x.get("r") is not None]
    out = []
    for field, name in COND:
        labs = _labels(field, n_rank)
        g = {}
        for x in cl:
            k = group_of(field, x, cut)
            if k is not None and 0 <= k < len(labs):
                g.setdefault(k, []).append(x)
        if len(g) < 2:
            continue
        for k in range(len(labs)):
            xs = g.get(k) or []
            if not xs:
                continue
            rest = [y for kk, ys in g.items() if kk != k for y in ys]
            a, b = [y["r"] for y in xs], [y["r"] for y in rest]
            diff = statistics.mean(a) - statistics.mean(b) if a and b else None
            t = welch_t(a, b)
            same = None
            if diff is not None:
                hs = []
                for h in (0, 1):
                    ah = [y["r"] for y in xs if halves(y) == h]
                    bh = [y["r"] for y in rest if halves(y) == h]
                    hs.append(statistics.mean(ah) - statistics.mean(bh) if ah and bh else None)
                same = all(v is not None and v * diff > 0 for v in hs)
            sig = bool(len(a) >= SPLIT_MIN_N and t is not None and abs(t) >= SPLIT_T and same)
            out.append([name, labs[k], len(a), _r2(statistics.mean(a)), round(100 * sum(1 for v in a if v > 0) / len(a)),
                        _r2(diff), None if t is None else round(t, 2), sig])
    return out


def unpack_ref_tr(rows: list[list]) -> list[dict]:
    return [dict(zip(_TRC, r)) | {"reg": None if r[5] is None else bool(r[5])} for r in rows]


# ── 每日健檢（第 3 節） ──────────────────────────────────────────────────

def check(k: str, ref: dict, fwd_u: list[float], *, open_items: list[dict], fwd_tr: list[dict], halves,
          event: bool, n_rank: int = 5) -> dict:
    """一條策略的當天健檢。ref＝回測參考（ref_pack）；fwd_u＝前瞻已完成單位的報酬；open_items＝持有中
    [{n（名稱）, d（持有第幾天）, x（目前累積報酬 %）}]（逐檔策略每檔一項、其餘每批一項）；fwd_tr＝前瞻已出場逐筆。
    → {n, avg, light, b（燈號抽樣）, hold（持有中百分位）, low（低於第 5 百分位的項目）, split（拆解）}"""
    from .optim import HOLD_PCT_EV, light
    b = boot(ref.get("u") or [], fwd_u)
    hold = []
    for it in open_items:
        p = at_day(ref.get("q") or {}, it["d"], it.get("x"))
        hold.append({**it, "pct": p})
    trs = unpack_ref_tr(ref.get("tr") or []) + [x for x in fwd_tr if x.get("r") is not None]
    return {"k": k, "n": len(fwd_u), "avg": _r2(_mean(fwd_u)), "light": light(b["pct"], len(fwd_u), event), "b": b,
            "hold": hold, "low": [h["n"] for h in hold if h["pct"] is not None and h["pct"] < HOLD_PCT_EV],
            "split": split(trs, ref.get("cut") or {}, halves, n_rank=n_rank),
            "ref_n": len(ref.get("u") or []), "q_days": len((ref.get("q") or {}).get("q") or [])}


SCOPE = ("v3l", "v7m", "v7l", "s3", "s5", "s1")       # 健檢範圍（docs 第 1 節；C 級與清單外的在頁面隱藏）
REF_FILE = "opt_research.json"                         # 每週重跑的產出（v3 長歷史面板的回測參考＋改良候選）


def _halves(k: str, ref_tr: list[dict]):
    """拆解的前後兩半：有複驗期間的用複驗（0）／主要期間（1）；其餘依回測逐筆決定日的中位數分。"""
    from .optim import HAS_REP, MAIN_FROM
    if k in HAS_REP:
        return lambda x: 0 if x["d"] < MAIN_FROM else 1
    ds = sorted(x["d"] for x in ref_tr)
    mid = ds[len(ds) // 2] if ds else "9999"
    return lambda x: 0 if x["d"] < mid else 1


def build_ref_file(P=None) -> dict:
    """每週：v3 長歷史面板 → 財報（大型）、月營收（中型、大型）的回測參考（現行規則、起算日之前）。"""
    from . import bt3d, packtest as PT, v3live
    P = P or bt3d.Panel()
    E = bt3.Elig(P)
    eps, rev = bt3d.load_eps(), PT.load_rev()
    ref = {}
    for k, src, b, _, _ in v3live.LIVE:
        if k in SCOPE:
            ref[k] = ref_periodic(P, E, k, src, b, since=v3live.SINCE, umin=v3live.UMIN[src], n=v3live.N, eps=eps, rev=rev)
    return {"asof": P.cal[-1], "ref": ref}


def daily(full: dict, v3: dict, D, ctx, reg_map: dict | None, ref_file: dict | None = None) -> dict:
    """每次建頁：六條策略的健檢（燈號、持有中百分位、拆解）。full＝analyze._take_full 的輸出；v3＝v3live.run 的輸出；
    ctx＝v3live 的 (P, E)（市值用）；ref_file＝每週產出（沒有時 v3 三條只顯示前瞻、不打燈號）。"""
    from . import growth, strategy, v3live
    from .optim import EVENT
    ref_file = ref_file if ref_file is not None else (store_read(REF_FILE) or {})
    P = ctx[0] if ctx else None
    pix = P.D.ix if P is not None else {}

    def cap_of(c, t):
        i = pix.get(D.cal[t])
        return (P.cap.get(c) or [None] * P.T)[i] if P is not None and i is not None else None
    names = D.names
    out = {"asof_ref": ref_file.get("asof")}
    for k in ("v3l", "v7m", "v7l"):
        R = (ref_file.get("ref") or {}).get(k)
        L = (v3 or {}).get(k) or {}
        if not R or not L:
            continue
        hl = (full.get("hl") or {}).get(k) or {}
        fu = [u["r"] for u in (L.get("fwd") or {}).get("units") or [] if u.get("r") is not None]
        items = []
        nw = hl.get("now")
        if nw and nw.get("p"):
            items.append({"n": f"{nw['d'][5:7].lstrip('0')}/{nw['d'][8:10].lstrip('0')} 那一批", "d": len(nw["p"]),
                          "x": nw["p"][-1]})
        out[k] = {**check(k, R, fu, open_items=items, fwd_tr=hl.get("tr") or [], halves=_halves(k, unpack_ref_tr(R["tr"])),
                          event=k in EVENT), "since": v3live.SINCE}
    sinces = {"s1": next(s["since"] for s in strategy.STRATEGIES if s["key"] == "s1"), "s5": growth.S5["since"],
              "s3": strategy.TW50_VERS[0]["since"]}
    for k in ("s1", "s5", "s3"):
        trs = full.get(k)
        if trs is None:
            continue
        ev = k == "s3"
        h = from_trades(D, trs, cap_of=cap_of, fw_from=sinces[k], reg_map=reg_map,
                        **({"rank_key": "mom", "group": "review", "b_fix": "L"} if ev else {}))["tr"]
        R = ref_trades(h, sinces[k], event=ev)
        fw = [x for x in h if x["fw"]]
        fwc = [x for x in fw if x.get("r") is not None]
        fu = per_review(fwc) if ev else [x["r"] for x in fwc]
        items = []
        if ev:
            cur = [x for x in h if x.get("i") is None]
            if cur:
                g = max(x.get("g") or "" for x in cur)
                bk = review_baskets([x for x in h if x.get("g") == g])
                if bk:
                    items.append({"n": f"{g} 這一次", "d": len(bk[0]["p"]), "x": bk[0]["p"][-1]})
        else:
            for x in h:
                if x.get("i") is None and x.get("path"):
                    items.append({"n": names.get(x["c"], x["c"]), "c": x["c"], "d": len(x["path"]), "x": x["path"][-1]})
        out[k] = {**check(k, R, fu, open_items=items, fwd_tr=fwc, halves=_halves(k, [x for x in h if not x["fw"]]),
                          event=ev, n_rank=4 if ev else 5), "since": sinces[k]}
    return out


def store_read(name: str):
    from . import store
    return store.read_json(name, {})
