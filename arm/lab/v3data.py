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


def _quarters_due() -> list[tuple[int, int]]:
    """法定期限已過的 (年, 季)，2012 起（2012 年是 IFRS 前，抓得到才算）。"""
    from .. import clock
    from .packtest import deadline
    today = clock.today_tw().isoformat()
    out = []
    for y in range(2012, clock.today_tw().year + 1):
        for q, qe in ((1, "03-31"), (2, "06-30"), (3, "09-30"), (4, "12-31")):
            if deadline(f"{y}-{qe}") < today:
                out.append((y, q))
    return out


def line_mops_eps(R: _Run) -> None:
    """公開資訊觀測站綜合損益表彙總：一季、一市場一請求 → v3isq/{年}Q{季} {"sii": {代號: 累計 EPS}, "otc": {...}}。
    彙總表的基本每股盈餘是當年累計值（例：台積電 2014Q4＝10.18＝全年），單季在載入時相減。"""
    from concurrent.futures import ThreadPoolExecutor
    todo = []
    for y, q in _quarters_due():
        doc = store.read("v3isq", f"{y}Q{q}") or {}
        if not (doc.get("sii") and doc.get("otc")):
            todo.append((y, q, doc))
    with ThreadPoolExecutor(max_workers=4) as ex:
        for k in range(0, len(todo), 2):
            if not R.left():
                return
            grp = todo[k:k + 2]
            jobs = {(y, q, m): ex.submit(market.mops_is, m, y, q) for y, q, _ in grp for m in ("sii", "otc")}
            for y, q, doc in grp:
                new = dict(doc)
                for m in ("sii", "otc"):
                    d = jobs[(y, q, m)].result()
                    if d and len(d) >= 200:
                        new[m] = d
                if new != doc:
                    store.write("v3isq", f"{y}Q{q}", new)
                    R.add("is_q")
                else:
                    market.log(f"[v3] 綜合損益彙總 {y}Q{q}：抓不到")
            time.sleep(1.0)


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
             threading.Thread(target=line_finmind, args=(R, cur)), threading.Thread(target=line_mops_eps, args=(R,))]
    for t in lines:
        t.start()
    for t in lines:
        t.join()
    summ = {"本輪": R.n, "v3px": len(store.dates("v3px")), "月底上市": len(store.dates("v3me_tw")),
            "月底上櫃": len(store.dates("v3me_tp")), "上櫃除權息年": len(store.dates("v3div")),
            "EPS": len(store.dates("v3eps")), "綜合損益彙總季": len(store.dates("v3isq")), "月營收月": len(store.dates("rev")),
            "報酬指數月": len((store.read_json("v3_tr.json", {}) or {}).get("m") or []),
            "秒": round(time.time() - R.t0)}
    market.log(f"[v3] {summ}")
    return summ

# ── 每日維護（不必另外回補） ─────────────────────────────────────────

def me_from_mkt() -> int:
    """月底市值快照從每日官方分片補（上市 q_tw × x_tw 發行股數、上櫃 q_tp 內含發行股數），不發請求。
    只補「已過完、還沒有快照」的月份；回測 v3 的市值口徑（最近一個月底）每天名單照用。"""
    from .. import clock
    cur = clock.today_tw().isoformat()[:7]
    last: dict[str, str] = {}
    for d in store.dates("mkt"):
        last[d[:7]] = d
    n = 0
    have_tw, have_tp = set(store.dates("v3me_tw")), set(store.dates("v3me_tp"))
    for ym, d in sorted(last.items()):
        if ym >= cur or (ym in have_tw and ym in have_tp):
            continue
        doc = store.read("mkt", d) or {}
        q_tw, x_tw, q_tp = doc.get("q_tw") or {}, doc.get("x_tw") or {}, doc.get("q_tp") or {}
        if ym not in have_tw and q_tw and x_tw:
            s = {c: [q[3], x_tw[c][1]] for c, q in q_tw.items() if stock(c) and q and q[3] and (x_tw.get(c) or [None, None])[1]}
            if len(s) >= 500:
                store.write("v3me_tw", ym, {"d": d, "s": s, "src": "mkt"})
                n += 1
        if ym not in have_tp and q_tp:
            s = {c: [q[3], q[6]] for c, q in q_tp.items() if stock(c) and q and q[3] and len(q) > 6 and q[6]}
            if len(s) >= 300:
                store.write("v3me_tp", ym, {"d": d, "s": s, "src": "mkt"})
                n += 1
    return n


def update_tr_recent() -> int:
    """每日維護：加權報酬指數（含息）補到官方分片的最新交易日——給前瞻紀錄的「同期大盤」（v4 後台驗證）。
    只查上個月（還沒標完成時）與本月，一輪最多 2 請求；已經到最新交易日就零請求。→ 新增天數"""
    from datetime import timedelta
    from .. import clock
    tr = store.read_json("v3_tr.json", {}) or {}
    q, done = dict(tr.get("q") or {}), set(tr.get("m") or [])
    ds = store.dates("mkt")
    if not ds or (q and max(q) >= ds[-1]):
        return 0
    cur = clock.today_tw()
    pm = cur.replace(day=1) - timedelta(days=1)
    n0 = len(q)
    for y, m in ((pm.year, pm.month), (cur.year, cur.month)):
        ym = f"{y:04d}-{m:02d}"
        if ym in done:
            continue
        rows = market.twse_tr_month(y, m)
        if rows is None:
            continue
        q.update(rows)
        if ym < cur.isoformat()[:7] and rows:
            done.add(ym)
    if len(q) > n0 or done != set(tr.get("m") or []):
        store.write_json("v3_tr.json", {"q": q, "m": sorted(done)})
    return len(q) - n0


# ── 公司財報分析（docs/lab_company_plan.md 第 3.2 節）：綜合損益＋資產負債彙總的全部科目 ─────────────
FS_PARTS = ("is_sii", "is_otc", "bs_sii", "bs_otc", "cf_sii", "cf_otc")
FS_MIN = 200                       # 一市場一季至少幾家才算抓到（同 EPS）
FS_RE = (14, 45)                   # 法定期限後第 14～45 天再抓一次（補晚報的公司），只抓一次
FS_FLOW = ("rev", "cogs", "gp", "opex", "op", "nonop", "pti", "tax", "ni", "nip", "eps",
           "ocf", "icf", "ffc")      # 損益、現金流量：當年累計 → 單季要相減
QEND = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def _fs_todo(today: str) -> list[tuple[int, int, str]]:
    """要抓的 (年, 季, 部件)：法定期限已過而沒有的；期限後 14～45 天還沒補抓過的。新的季先抓。"""
    from datetime import date, timedelta
    from .packtest import deadline
    out = []
    for y, q in sorted(_quarters_due(), reverse=True):
        if y < 2013:
            continue
        doc = store.read("fsq", f"{y}Q{q}") or {}
        at = doc.get("at") or {}
        dl = deadline(f"{y}-{QEND[q]}")
        re_lo = (date.fromisoformat(dl) + timedelta(days=FS_RE[0])).isoformat()
        re_hi = (date.fromisoformat(dl) + timedelta(days=FS_RE[1])).isoformat()
        for p in FS_PARTS:
            if not doc.get(p):
                out.append((y, q, p))
            elif re_lo <= today <= re_hi and (at.get(p) or "") < re_lo:
                out.append((y, q, p))
    return out


def update_fs(budget_s: float = 600, workers: int = 4, max_req: int | None = None) -> dict:
    """綜合損益＋資產負債彙總（一季、一市場、一張表一請求；MOPS 一個請求約 1～3 分鐘）→ fsq/{年}Q{季}
    {"is_sii": {代號: {欄位: 值}}, "is_otc", "bs_sii", "bs_otc", "at": {部件: 抓取日}}。損益是當年累計（載入時相減）。
    每日只在法定期限過後補缺（max_req 限制每輪請求數），回補用大預算多輪續跑。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .. import clock
    today = clock.today_tw().isoformat()
    todo = _fs_todo(today)
    if max_req is not None:
        todo = todo[:max_req]
    st = {"req": 0, "ok": 0, "todo": len(todo)}
    if not todo:
        return st
    t0 = time.time()
    docs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs, k = {}, 0

        def submit_next():
            nonlocal k
            if k < len(todo) and time.time() - t0 < budget_s:
                y, q, p = todo[k]
                kind, mkt = p.split("_")
                futs[ex.submit(market.mops_fs, kind, mkt, y, q)] = (y, q, p)
                st["req"] += 1
                k += 1
                return True
            return False
        for _ in range(workers):
            submit_next()
        while futs:
            for fut in as_completed(list(futs)):
                y, q, p = futs.pop(fut)
                try:
                    d = fut.result()
                except Exception as e:                    # noqa: BLE001
                    market.log(f"[fs] {y}Q{q} {p} ✗ {type(e).__name__}: {e}")
                    d = None
                key = f"{y}Q{q}"
                doc = docs.setdefault(key, store.read("fsq", key) or {})
                if d and len(d) >= FS_MIN:
                    old = doc.get(p) or {}
                    doc[p] = {**old, **d}                 # 補抓只增不減（晚報公司加進來）
                    doc.setdefault("at", {})[p] = today
                    store.write("fsq", key, doc)
                    st["ok"] += 1
                else:
                    market.log(f"[fs] {key} {p}：抓不到或太少（{len(d or {})} 家）")
                submit_next()
                break
    market.log(f"[fs] 綜合損益／資產負債彙總：請求 {st['req']}、寫入 {st['ok']}、待抓 {st['todo']}、{time.time() - t0:.0f} 秒")
    return st


def load_fs() -> dict[str, dict[str, dict]]:
    """fsq → {代號: {季底: {欄位: 值}}}：損益與現金流量為單季（Q1＝累計、Qn＝累計(n) − 累計(n−1)，前一季缺就不算），
    資產負債與期末現金為季底值。金額單位仟元、EPS 元。"""
    cum: dict[str, dict] = {}
    bal: dict[str, dict] = {}
    for key, doc in store.load("fsq"):
        y, q = int(key[:4]), int(key[5])
        for m in ("sii", "otc"):
            for c, d in (doc.get(f"is_{m}") or {}).items():
                cum.setdefault(c, {}).setdefault((y, q), {}).update(d)
            for c, d in (doc.get(f"cf_{m}") or {}).items():
                cum.setdefault(c, {}).setdefault((y, q), {}).update({k: v for k, v in d.items() if k != "cash"})
                if d.get("cash") is not None:
                    bal.setdefault(c, {}).setdefault((y, q), {})["cash"] = d["cash"]
            for c, d in (doc.get(f"bs_{m}") or {}).items():
                bal.setdefault(c, {}).setdefault((y, q), {}).update(d)
    out: dict[str, dict] = {}
    for c in set(cum) | set(bal):
        e: dict[str, dict] = {}
        cc = cum.get(c) or {}
        for (y, q), d in cc.items():
            if q == 1:
                one = {k: d[k] for k in FS_FLOW if k in d}
            else:
                p = cc.get((y, q - 1))
                if not p:
                    continue
                one = {k: round(d[k] - p[k], 4) for k in FS_FLOW if k in d and k in p}
            if one:
                e.setdefault(f"{y}-{QEND[q]}", {}).update(one)
        for (y, q), d in (bal.get(c) or {}).items():
            e.setdefault(f"{y}-{QEND[q]}", {}).update(d)
        if e:
            out[c] = e
    return out


def update_isq() -> int:
    """每季法定期限過後補一次綜合損益表彙總（一季兩請求）；平常沒有缺就不發請求。"""
    n = 0
    for y, q in _quarters_due():
        doc = store.read("v3isq", f"{y}Q{q}") or {}
        if doc.get("sii") and doc.get("otc"):
            continue
        if y < 2013:
            continue
        new = dict(doc)
        for m in ("sii", "otc"):
            if not new.get(m):
                d = market.mops_is(m, y, q)
                if d and len(d) >= 200:
                    new[m] = d
        if new != doc:
            store.write("v3isq", f"{y}Q{q}", new)
            n += 1
    return n


# ── 已下市公司名稱（逐筆交易顯示用；docs/lab_trades_plan.md 第 5 節） ─────────────

NAMES_SRC = [  # (說明, 網址)；一個來源一個請求，依序試，抓到的併起來
    ("FinMind 下市櫃表", "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockDelisting"),
    ("FinMind 台股總覽", "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo"),
    ("證交所終止上市", "https://www.twse.com.tw/rwd/zh/company/suspendListing?response=json"),
    ("櫃買終止上櫃", "https://www.tpex.org.tw/www/zh-tw/company/suspendListing?response=json"),
]


def _name_pairs(doc) -> list[tuple[str, str]]:
    """任意 JSON（FinMind data、證交所 rwd tables、櫃買 tables）→ [(代號, 名稱)]：同一列裡 4 碼數字＋含中文的欄位。"""
    import re
    rows = []
    if isinstance(doc, dict):
        if isinstance(doc.get("data"), list):
            rows += doc["data"]
        for t in doc.get("tables") or []:
            if isinstance(t, dict):
                rows += t.get("data") or []
    out = []
    for r in rows:
        if isinstance(r, dict):
            c, n = str(r.get("stock_id") or "").strip(), str(r.get("stock_name") or "").strip()
            if c and n:
                out.append((c, n))
            continue
        if not isinstance(r, (list, tuple)):
            continue
        cells = [re.sub(r"<[^>]+>", "", str(x)).strip() for x in r]
        c = next((x for x in cells if re.fullmatch(r"\d{4}", x)), None)
        n = next((x for x in cells if re.search(r"[一-鿿]", x) and not re.search(r"\d{2,3}/\d{1,2}/\d{1,2}", x)), None)
        if c and n:
            out.append((c, n))
    return out


def update_names_hist() -> dict:
    """長歷史裡「目前名稱表沒有」的代號（多為已下市）→ data/lab/names_hist.json {代號: 名稱}。
    名稱表＝names_mkt.json（官方價量順手收的）＋names.json（ETF 持股）。抓不到的印出代號，頁面顯示代號。容器內不跑。"""
    import json
    from ..http import get_bytes
    have = {**(store.read_json("names_mkt.json", {}) or {}), **(store.read_json("names.json", {}) or {})}
    old = store.read_json("names_hist.json", {}) or {}
    want = {c for c in store.dates("v3px") if stock(c) and c not in have and c not in old}
    got: dict[str, str] = {}
    for lbl, url in NAMES_SRC:
        if not want - set(got):
            break
        try:
            doc = json.loads(get_bytes(url, retries=1, timeout=40, use_cache=False).decode("utf-8"))
        except Exception as e:                            # noqa: BLE001 —— 記下原因，換下一個來源
            market.log(f"[名稱] {lbl} ✗ {str(e)[:120]}")
            continue
        pairs = _name_pairs(doc)
        hit = {c: n for c, n in pairs if c in want and c not in got}
        st = doc.get("status") if isinstance(doc, dict) else None
        smp = json.dumps((doc.get("data") or [None])[0] if isinstance(doc, dict) and doc.get("data") else
                         (doc if not isinstance(doc, dict) else {k: doc[k] for k in list(doc)[:4]}), ensure_ascii=False)[:200]
        market.log(f"[名稱] {lbl}：status={st} 解析 {len(pairs)} 對、補到 {len(hit)} 檔｜樣本={smp}")
        got.update(hit)
    if got:
        store.write_json("names_hist.json", {**old, **got})
    left = sorted(want - set(got))
    market.log(f"[名稱] 需要 {len(want)} 檔，本輪補到 {len(got)} 檔；仍缺 {len(left)} 檔：{' '.join(left[:40])}")
    return {"want": len(want), "got": len(got), "left": left}
