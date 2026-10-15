"""回測 v3 長歷史資料回補（docs/backtest_v3_plan.md 第 10 節）：2013 起、含下市公司、含息、月底官方市值。

另存（不併入 yh／yhl／mkt，日常分析與現有策略的回測期間不受影響）：
  v3px/{代號}        日線（欄式）{"m": tw|tp|idx, "src": yahoo|finmind, "t": [日期], "o", "h", "l", "c", "v",
                     "a": [還原收盤]（Yahoo）或 "val": [成交金額]（FinMind 原始價）}
  v3me_tw/{YYYY-MM}  上市月底 {"d": 日期, "s": {代號: [收盤, 發行股數]}}（證交所 MI_INDEX＋MI_QFIIS）
  v3me_tp/{YYYY-MM}  上櫃月底（櫃買日收盤，內含發行股數）
  v3div/{年}         上櫃除權息 [[日, 代號, 前收, 參考價, 現金股利, 每仟股配股]]
  v3eps/{代號}       {"eps": {季底: 單季 EPS}}（FinMind；空的也寫＝查過）
  v3_tr.json         {"q": {日期: 加權報酬指數}, "m": [已抓月份]}
五條線平行（證交所、櫃買、Yahoo、公開資訊觀測站、FinMind），各寫各的檔，都可重跑續補。
"""
from __future__ import annotations

import threading
import time

from . import market, store

START = "2013-01-01"
CAP_FETCH = 40e8              # 已下市股價與 EPS 只抓曾經月底市值 ≥40 億者（中型股下限 50 億留緩衝）
CAP_NOW = 30e8                # 第一輪 Yahoo：目前市值 ≥30 億（之後依月底市值補曾經夠大的）


def stock(c: str) -> bool:
    return len(c) == 4 and c.isdigit() and not c.startswith("0")


def _cols(q: dict, extra: str) -> dict:
    """{日期: [o, h, l, c, v, x]} → 欄式（x 存到 extra 欄名）。"""
    ds = sorted(q)
    out = {"t": ds}
    for k, i in (("o", 0), ("h", 1), ("l", 2), ("c", 3), ("v", 4), (extra, 5)):
        out[k] = [q[d][i] if len(q[d]) > i else None for d in ds]
    return out


def px_doc(c: str) -> dict | None:
    return store.read("v3px", c)


def twii() -> list[str]:
    """交易日曆（加權指數日線，2013 起）；本輪第一次呼叫時更新。"""
    doc = px_doc("TWII")
    if not doc or not doc.get("t") or doc["t"][-1] < _recent():
        h = market.yahoo_hist_from("^TWII", START, adj=True)
        if len(h) > 3000:
            store.write("v3px", "TWII", {"m": "idx", "src": "yahoo", **_cols(h, "a")})
            doc = px_doc("TWII")
    return (doc or {}).get("t") or []


def _recent() -> str:
    from .. import clock
    from datetime import timedelta
    return (clock.today_tw() - timedelta(days=7)).isoformat()


def month_ends(cal: list[str], k: int = 3) -> list[tuple[str, list[str]]]:
    """→ [(YYYY-MM, 該月最後 k 個交易日（新到舊）)]，不含本月（還沒過完）。月底那天官方查無時退一天再試。"""
    from .. import clock
    cur = clock.today_tw().isoformat()[:7]
    by: dict[str, list[str]] = {}
    for d in cal:
        by.setdefault(d[:7], []).append(d)
    return [(ym, ds[::-1][:k]) for ym, ds in sorted(by.items()) if ym < cur]


def current_list() -> list[tuple[str, str, float]]:
    """目前上市櫃普通股 [(代號, tw|tp, 市值)]，市值由大到小（最新官方分片：收盤 × 發行股數）。"""
    ds = store.dates("mkt")
    q_tw, q_tp, x_tw = {}, {}, {}
    for d in reversed(ds[-15:]):
        doc = store.read("mkt", d) or {}
        q_tw = q_tw or doc.get("q_tw") or {}
        q_tp = q_tp or doc.get("q_tp") or {}
        x_tw = x_tw or doc.get("x_tw") or {}
        if q_tw and q_tp and x_tw:
            break
    out = []
    for c, q in q_tw.items():
        sh = (x_tw.get(c) or [None, None])[1]
        if stock(c) and q and q[3]:
            out.append((c, "tw", q[3] * sh if sh else 0.0))
    for c, q in q_tp.items():
        if stock(c) and q and q[3]:
            out.append((c, "tp", q[3] * q[6] if len(q) > 6 and q[6] else 0.0))
    return sorted(out, key=lambda x: (-x[2], x[0]))


def me_caps() -> dict[str, float]:
    """各代號歷次月底市值的最大值（上市＋上櫃）。"""
    mx: dict[str, float] = {}
    for kind in ("v3me_tw", "v3me_tp"):
        for _, doc in store.load(kind):
            for c, (px, sh) in (doc.get("s") or {}).items():
                if px and sh:
                    mx[c] = max(mx.get(c, 0.0), px * sh)
    return mx


# ── 五條線 ───────────────────────────────────────────────────────────

class _Run:
    def __init__(self, budget_s: float):
        self.t0, self.budget = time.time(), budget_s
        self.n: dict[str, int] = {}
        self.lock = threading.Lock()

    def left(self) -> bool:
        return time.time() - self.t0 < self.budget

    def add(self, k: str, v: int = 1) -> None:
        with self.lock:
            self.n[k] = self.n.get(k, 0) + v


def line_twse(R: _Run, mes: list[tuple[str, str]]) -> None:
    """上市月底收盤＋發行股數 → 加權報酬指數 → 除權息 2013–2017。"""
    have = set(store.dates("v3me_tw"))
    for ym, days in mes:
        if ym in have:
            continue
        for d in days:
            if not R.left():
                return
            q, st, _ = market.fetch_part("q_tw", d)
            if not q:
                continue
            x, st2, _ = market.fetch_part("x_tw", d)
            s = {c: [v[3], x[c][1]] for c, v in q.items() if stock(c) and v and v[3] and c in (x or {}) and x[c][1]}
            if len(s) >= 500:
                store.write("v3me_tw", ym, {"d": d, "s": s})
                R.add("me_tw")
                break
            market.log(f"[v3] 上市月底 {ym}（{d}）：價 {st}、股數 {st2}、配對 {len(s)} 檔，不寫入")
    tr = store.read_json("v3_tr.json", {}) or {}
    q, done = dict(tr.get("q") or {}), set(tr.get("m") or [])
    from .. import clock
    y, m = 2013, 1
    cur = clock.today_tw()
    while (y, m) <= (cur.year, cur.month) and R.left():
        ym = f"{y:04d}-{m:02d}"
        if ym not in done or ym >= cur.isoformat()[:7]:
            rows = market.twse_tr_month(y, m)
            if rows is not None:
                q.update(rows)
                if ym < cur.isoformat()[:7]:
                    done.add(ym)
                R.add("tr")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    store.write_json("v3_tr.json", {"q": q, "m": sorted(done)})
    if R.left():
        from .collect import backfill_divtw
        R.add("divtw", backfill_divtw((2013, 2014, 2015, 2016, 2017)))


def line_tpex(R: _Run, mes: list[tuple[str, str]]) -> None:
    """上櫃月底收盤＋發行股數 → 上櫃除權息（2013 起每年一請求）。"""
    have = set(store.dates("v3me_tp"))
    for ym, days in mes:
        if ym in have:
            continue
        for d in days:
            if not R.left():
                return
            q, st, _ = market.fetch_part("q_tp", d)
            if not q:
                continue
            s = {c: [v[3], v[6]] for c, v in q.items() if stock(c) and v and v[3] and len(v) > 6 and v[6]}
            if len(s) >= 300:
                store.write("v3me_tp", ym, {"d": d, "s": s})
                R.add("me_tp")
                break
            market.log(f"[v3] 上櫃月底 {ym}（{d}）：{st}、{len(s)} 檔，不寫入")
    from .. import clock
    for y in range(2013, clock.today_tw().year + 1):
        if not R.left():
            return
        if store.read("v3div", str(y)) and y < clock.today_tw().year:
            continue
        rows = market.tpex_exright_year(y)
        if rows:
            store.write("v3div", str(y), {"rows": rows})
            R.add("div_tp")


def _yahoo_one(c: str, m: str) -> bool:
    sufs = [".TW", ".TWO"] if m == "tw" else [".TWO", ".TW"]
    for k, suf in enumerate(sufs):
        h = market.yahoo_hist_from(c + suf, START, adj=True)
        time.sleep(0.5)
        if len(h) >= 20:
            store.write("v3px", c, {"m": "tw" if suf == ".TW" else "tp", "src": "yahoo", **_cols(h, "a")})
            return True
    return False


def line_yahoo(R: _Run, todo: list[tuple[str, str]], workers: int = 2) -> None:
    """目前上市櫃股的 2013 起日線（含還原收盤）。todo＝[(代號, tw|tp)]，已有最新資料的跳過。"""
    rec = _recent()
    need = []
    for c, m in todo:
        doc = px_doc(c)
        if doc and doc.get("src") == "yahoo" and doc.get("t") and doc["t"][-1] >= rec:
            continue
        need.append((c, m))
    it = iter(need)
    lk = threading.Lock()

    def work():
        while R.left():
            with lk:
                nx = next(it, None)
            if nx is None:
                return
            R.add("yahoo" if _yahoo_one(*nx) else "yahoo_miss")
    ts = [threading.Thread(target=work) for _ in range(workers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


def line_mops(R: _Run) -> None:
    from .collect import backfill_rev_mops
    R.add("rev", backfill_rev_mops("2012-01", budget_s=max(0.0, R.budget - (time.time() - R.t0))))


def line_finmind(R: _Run, cur: dict[str, float]) -> None:
    """已下市股價（曾經月底市值 ≥40 億、目前不在名單）先抓 → 單季 EPS（市值由大到小）。被限流就停。"""
    mx = me_caps()
    gone = sorted((c for c, v in mx.items() if v >= CAP_FETCH and c not in cur and stock(c)
                   and not px_doc(c)), key=lambda c: -mx[c])
    for c in gone:
        if not R.left():
            return
        rows = market.finmind("TaiwanStockPrice", c, START)
        time.sleep(1.2)
        if rows == market.FINMIND_LIMIT:
            market.log(f"[v3] FinMind 限流（下市股價，停在 {c}）")
            return
        q = {}
        for r in rows or []:
            d = str(r.get("date") or "")[:10]
            if d and r.get("close"):
                q[d] = [r.get("open"), r.get("max"), r.get("min"), r.get("close"),
                        r.get("Trading_Volume"), r.get("Trading_money")]
        store.write("v3px", c, {"m": "?", "src": "finmind", **_cols(q, "val")})
        R.add("fm_px")
    caps = {**{c: v for c, v in mx.items() if v >= CAP_FETCH}, **{c: v for c, v in cur.items() if v >= CAP_FETCH}}
    have = {d for d in store.dates("v3eps")}
    for c in sorted((c for c in caps if stock(c) and c not in have), key=lambda c: -caps[c]):
        if not R.left():
            return
        rows = market.finmind("TaiwanStockFinancialStatements", c, "2012-01-01")
        time.sleep(1.2)
        if rows == market.FINMIND_LIMIT:
            market.log(f"[v3] FinMind 限流（EPS，停在 {c}）")
            return
        if rows is None:
            continue
        store.write("v3eps", c, {"eps": market.fm_eps(rows)})
        R.add("fm_eps")


def line_probe_is(R: _Run) -> None:
    """探針：公開資訊觀測站綜合損益表彙總能不能從 CI 抓（能的話，EPS 一季一市場一請求，取代 FinMind 逐檔）。"""
    for y, q in ((2014, 1), (2014, 4), (2024, 2)):
        for mkt in ("sii", "otc"):
            if not R.left():
                return
            d = market.mops_is(mkt, y, q)
            smp = {c: (d or {}).get(c) for c in ("2330", "1101", "5347", "8299")}
            market.log(f"[v3探針] MOPS 綜合損益 {y}Q{q} {mkt}：{len(d or {})} 檔 {smp}")
            time.sleep(2)


def run(budget_s: float = 2700) -> dict:
    """一輪：五條線平行到時間預算用完。回傳各線本輪新增數。"""
    R = _Run(budget_s)
    cal = twii()
    mes = month_ends(cal)
    cl = current_list()
    cur = {c: cap for c, _, cap in cl}
    mx = me_caps()
    todo = [(c, m) for c, m, cap in cl if cap >= CAP_NOW]
    todo += [(c, "tw") for c in sorted(mx, key=lambda c: -mx[c]) if mx[c] >= CAP_FETCH and c in cur
             and c not in {t[0] for t in todo}]
    market.log(f"[v3] 日曆 {len(cal)} 日、月底 {len(mes)} 個、目前上市櫃 {len(cl)} 檔（Yahoo 待抓候選 {len(todo)}）、"
               f"月底市值已知 {len(mx)} 檔")
    lines = [threading.Thread(target=line_twse, args=(R, mes)), threading.Thread(target=line_tpex, args=(R, mes)),
             threading.Thread(target=line_yahoo, args=(R, todo)), threading.Thread(target=line_mops, args=(R,)),
             threading.Thread(target=line_finmind, args=(R, cur)), threading.Thread(target=line_probe_is, args=(R,))]
    for t in lines:
        t.start()
    for t in lines:
        t.join()
    summ = {"本輪": R.n, "v3px": len(store.dates("v3px")), "月底上市": len(store.dates("v3me_tw")),
            "月底上櫃": len(store.dates("v3me_tp")), "上櫃除權息年": len(store.dates("v3div")),
            "EPS": len(store.dates("v3eps")), "月營收月": len(store.dates("rev")),
            "報酬指數月": len((store.read_json("v3_tr.json", {}) or {}).get("m") or []),
            "秒": round(time.time() - R.t0)}
    market.log(f"[v3] {summ}")
    return summ
