"""台股官方全市場報價——「最新交易日」那一天的收盤與漲跌（ETF 持股詳情用）。

2026-10-21 使用者：「你ETF持股異動那邊，漲跌幅是錯的欸」。盤查（docs/etf_chg_fix_plan.md）：
漲跌數字本身沒算錯，錯在**拿錯天**——舊做法一律抓證交所／櫃買 openapi 全市場表「當下那份」、不看日期：
  · 證交所 openapi 要到**隔天清晨**才更新、櫃買**當晚**就更新 → 19:00、22:30、凌晨那幾班，
    同一張持股表上市股是前一天的漲跌、上櫃股是當天的（10/20 晚上 00981A：欣興顯示 10/19 的 +2.75%，
    10/20 實際 −5.80%）；
  · 9/20～10/21 共 83 版落檔，39% 的台股列不是快照日的漲跌。

使用者決定（2026-10-21）：漲跌一律用**最新交易日 T**。本模組負責「上市、上櫃都取到 T 那一天」：
  ① 決定 T：今天是交易日（證交所官方休市表）而且已過 14:00 → 先試今天，否則從前一交易日起試，最多 3 天；
  ② openapi 的日期剛好是 T → 直接用（零額外請求）；不是 → 抓指定日期版：證交所 MI_INDEX、櫃買每日收盤
     （rwd，與籌碼雷達分片同端點；官方正式漲跌，除權息日對參考價）；
  ③ 自我檢查：「收盤 − 漲跌 ＝ 前一交易日官方收盤」（籌碼雷達分片）要在 ≥80% 的股票成立才採用——
     除權息、減資日本來就不成立，但只是少數；比例過低＝正負號或欄位解析錯，不採用；
  ④ 任一市場拿不到 T → 換前一個交易日再試（標示的日期跟著變，**絕不上市、上櫃各取各的**）。

本容器 proxy 擋 twse／tpex——抓取只在正式區 CI 有意義；容器內呼叫全數快速失敗、回 (None, {}, 診斷)。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from . import clock, twholidays

TODAY_FROM = (14, 0)       # 台北 14:00 以後才試「今天」（MI_INDEX 約 14 點後公布；籌碼雷達分片實測 14:09 入庫）
TRY_DAYS = 3               # 最多往前試幾個交易日
CHECK_MIN_N = 100          # 自我檢查至少要比到幾檔才判定（不夠＝無從判斷，不擋）
CHECK_MIN_RATE = 0.80      # 「收盤 − 漲跌 ＝ 前一交易日收盤」成立比例下限
CHECK_TOL = 0.006          # 價格比對容差（元；台股最小跳動 0.01）
MIN_ROWS = {"twse": 600, "tpex": 300}   # 列數低於此＝回應不完整，不收（同籌碼雷達 MIN_ROWS）

_TAG = re.compile(r"<[^>]+>")


# ── 交易日 ───────────────────────────────────────────────────────────

def is_trading_day(d: date) -> bool:
    """證交所官方休市表優先；表未涵蓋的年份退回「平日就算」。"""
    c = twholidays.is_closed(d)
    return (d.weekday() < 5) if c is None else (not c)


def prev_trading_day(d: date) -> date:
    x = d - timedelta(days=1)
    for _ in range(40):
        if is_trading_day(x):
            return x
        x -= timedelta(days=1)
    return x


def candidates(now: datetime | None = None, n: int = TRY_DAYS) -> list[str]:
    """最新交易日的候選（新到舊）：今天是交易日且已過 14:00 → 從今天起；否則從前一交易日起。"""
    now = now or clock.now_tw()
    d = now.date()
    if not (is_trading_day(d) and (now.hour, now.minute) >= TODAY_FROM):
        d = prev_trading_day(d)
    out = [d]
    while len(out) < n:
        out.append(prev_trading_day(out[-1]))
    return [x.isoformat() for x in out]


# ── 解析（指定日期版） ────────────────────────────────────────────────

def _sign(x) -> int | None:
    """MI_INDEX「漲跌(+/-)」欄：<p style= color:red>+</p>／…green>-</p>／空白＝平盤；X＝不比價 → None。"""
    s = _TAG.sub("", str(x if x is not None else "")).strip()
    if s == "+":
        return 1
    if s == "-":
        return -1
    if s == "":
        return 0
    return None


def parse_mi_index(doc) -> dict[str, dict]:
    """證交所 MI_INDEX（type=ALLBUT0999）→ {代號: {close, change, name}}。

    漲跌＝「漲跌(+/-)」正負號 × 「漲跌價差」；沒有正負號欄時退回價差本身的正負。
    無成交（收盤 --）不列；不比價（X）的漲跌為 None。"""
    from .lab import market as M
    out: dict[str, dict] = {}
    for fields, rows in M.tables(doc):
        ci, cc = M.col(fields, "證券代號"), M.col(fields, "收盤價")
        cm = M.col(fields, "漲跌價差")
        if ci is None or cc is None or cm is None:
            continue
        cs = M.col(fields, "漲跌", "+/-")
        cn = M.col(fields, "證券名稱")
        for r in rows:
            if not isinstance(r, list) or max(ci, cc, cm) >= len(r):
                continue
            code = _TAG.sub("", str(r[ci])).strip()
            if not M.CODE_RE.match(code):
                continue
            close = M.num(r[cc])
            if close is None:
                continue
            mag = M.num(r[cm])
            if cs is not None and cs < len(r):
                sg = _sign(r[cs])
                change = None if (sg is None or mag is None) else (0.0 if sg == 0 else sg * abs(mag))
            else:
                change = mag
            out[code] = {"close": close, "change": change,
                         "name": (_TAG.sub("", str(r[cn])).strip() if cn is not None and cn < len(r) else "")}
    return out


def parse_tpex(doc) -> dict[str, dict]:
    """櫃買每日收盤（dailyQuotes，type=EW）→ {代號: {close, change, name}}。
    已知欄序：代號,名稱,收盤,漲跌,開盤,…（表頭在時以表頭定位）。漲跌欄自帶正負號；除權息等文字 → None。"""
    from .lab import market as M
    out: dict[str, dict] = {}
    for fields, rows in M.tables(doc):
        if fields:
            ci, cn, cc, cg = (M.col(fields, "代號"), M.col(fields, "名稱"),
                              M.col(fields, "收盤"), M.col(fields, "漲跌"))
        else:
            ci, cn, cc, cg = 0, 1, 2, 3
        if ci is None or cc is None or cg is None:
            continue
        for r in rows:
            if not isinstance(r, list) or max(ci, cc, cg) >= len(r):
                continue
            code = _TAG.sub("", str(r[ci])).strip()
            if not M.CODE_RE.match(code):
                continue
            close = M.num(r[cc])
            if close is None:
                continue
            out[code] = {"close": close, "change": M.num(r[cg]),
                         "name": (_TAG.sub("", str(r[cn])).strip() if cn is not None and cn < len(r) else "")}
    return out


# ── 抓取（指定日期版） ────────────────────────────────────────────────

def fetch_twse(d: str) -> tuple[dict | None, str]:
    """證交所 MI_INDEX 指定日期 → (報價, 狀態)。回應日≠d 不收（同櫃買規則）。"""
    from .lab import market as M
    doc, st = M._get(M.TWSE["mi_index"].format(ymd=M.ymd(d)), sleep=M.UA_SLEEP_TWSE)
    if st != "ok":
        return None, st
    rd = re.sub(r"\D", "", str((doc or {}).get("date") or "")) if isinstance(doc, dict) else ""
    if len(rd) == 8 and rd != M.ymd(d):
        return None, f"nodata:回應日 {rd}≠{M.ymd(d)}"
    q = parse_mi_index(doc)
    if len(q) < MIN_ROWS["twse"]:
        return None, f"err:解析 {len(q)} 列（低於 {MIN_ROWS['twse']}）"
    return q, "ok"


def fetch_tpex(d: str) -> tuple[dict | None, str]:
    """櫃買每日收盤指定日期（新站民國／西元兩種日期都試）→ (報價, 狀態)。回應日≠d 不收。"""
    from .lab import market as M
    last = "err:無候選"
    for tmpl in M.TPEX["quotes"]:
        doc, st = M._get(tmpl.format(roc=M.roc(d), ad=M.ad(d)), sleep=M.UA_SLEEP_TPEX)
        if st != "ok":
            last = st
            continue
        bad = M.tpex_date_mismatch(doc, d)
        if bad:
            last = bad
            continue
        q = parse_tpex(doc)
        if len(q) >= MIN_ROWS["tpex"]:
            return q, "ok"
        last = f"err:解析 {len(q)} 列（低於 {MIN_ROWS['tpex']}）"
    return None, last


# ── 自我檢查 ─────────────────────────────────────────────────────────

def _prev_closes(d: str) -> dict[str, float]:
    """籌碼雷達官方分片：d 的**前一交易日**（官方休市表）上市＋上櫃收盤。分片不存在 → {}。

    只認前一交易日那一片——那片缺時不可拿更早的頂（漲跌會變成兩天的累計，整批誤判）。"""
    from .lab import store
    p = prev_trading_day(date.fromisoformat(d)).isoformat()
    doc = store.read("mkt", p) or {}
    out: dict[str, float] = {}
    for part in ("q_tw", "q_tp"):
        for k, v in (doc.get(part) or {}).items():
            if v and len(v) > 3 and v[3]:
                out[k] = v[3]
    return out


def selfcheck(q: dict[str, dict], d: str, prev: dict[str, float] | None = None) -> tuple[int, int]:
    """(成立檔數, 可比檔數)：收盤 − 漲跌 ＝ 前一交易日收盤。"""
    prev = _prev_closes(d) if prev is None else prev
    ok = n = 0
    for code, v in (q or {}).items():
        pc, c, ch = prev.get(code), v.get("close"), v.get("change")
        if pc is None or c is None or ch is None:
            continue
        n += 1
        if abs(c - ch - pc) <= CHECK_TOL:
            ok += 1
    return ok, n


def check_ok(ok: int, n: int) -> bool:
    return n < CHECK_MIN_N or ok >= CHECK_MIN_RATE * n


# ── 主流程 ───────────────────────────────────────────────────────────

def _on_date(oa: dict | None, d: str) -> dict:
    """openapi 全市場表（twse/tpex.fetch_today_all 格式）中日期＝d 的部分。"""
    return {k: {"close": v.get("close"), "change": v.get("change"), "name": v.get("name") or ""}
            for k, v in (oa or {}).items() if v.get("date") == d and v.get("close") is not None}


def _safe(fn):
    try:
        return fn() or {}
    except Exception as e:                                # noqa: BLE001 —— 走指定日期版
        print(f"  · openapi 全市場表不可得：{type(e).__name__}: {str(e)[:80]}")
        return {}


def _one(market: str, oa: dict | None, d: str, fetch) -> tuple[dict | None, str, str]:
    """單一市場取 d 那天：openapi 日期剛好＝d → 直接用；否則抓指定日期版。→ (報價, 來源, 狀態)"""
    got = _on_date(oa, d)
    if len(got) >= MIN_ROWS[market]:
        return got, "openapi", "ok"
    q, st = fetch(d)
    return q, ("mi_index" if market == "twse" else "dailyQuotes"), st


def latest(now: datetime | None = None, *, today_all: dict | None = None,
           fetch_tw=None, fetch_tp=None, prev_closes=None) -> tuple[str | None, dict, dict]:
    """最新交易日 T 的上市＋上櫃官方報價 → (T, {代號: {close, change, name, date, src}}, 診斷)。

    today_all＝{"twse": …, "tpex": …}（openapi 全市場表；None＝這裡抓）。fetch_tw／fetch_tp／prev_closes
    供測試替換。上市、上櫃要同一天都拿到且過自我檢查才回 T；都不行 → (None, {}, 診斷)。"""
    if today_all is None:
        from .connectors import tpex, twse
        today_all = {"twse": _safe(twse.fetch_today_all),
                     "tpex": _safe(lambda: tpex.fetch_today_all(rwd_fallback=False))}
    fetch_tw = fetch_tw or fetch_twse
    fetch_tp = fetch_tp or fetch_tpex
    info: dict = {"tried": []}
    for d in candidates(now):
        tw, tw_src, tw_st = _one("twse", today_all.get("twse"), d, fetch_tw)
        if not tw:
            info["tried"].append(f"{d} 上市 {tw_src} {tw_st}")
            continue
        tp, tp_src, tp_st = _one("tpex", today_all.get("tpex"), d, fetch_tp)
        if not tp:
            info["tried"].append(f"{d} 上櫃 {tp_src} {tp_st}")
            continue
        prev = prev_closes(d) if prev_closes else _prev_closes(d)
        c_tw, c_tp = selfcheck(tw, d, prev), selfcheck(tp, d, prev)
        if not (check_ok(*c_tw) and check_ok(*c_tp)):
            info["tried"].append(f"{d} 自我檢查未過（上市 {c_tw[0]}/{c_tw[1]}、上櫃 {c_tp[0]}/{c_tp[1]}）")
            continue
        out = {k: {**v, "date": d, "src": f"tp_{tp_src}"} for k, v in tp.items()}
        out.update({k: {**v, "date": d, "src": f"tw_{tw_src}"} for k, v in tw.items()})
        info.update({"T": d, "tw_src": tw_src, "tp_src": tp_src, "tw_n": len(tw), "tp_n": len(tp),
                     "tw_check": c_tw, "tp_check": c_tp})
        return d, out, info
    return None, {}, info


def describe(info: dict) -> str:
    """CI 日誌一行摘要。"""
    if not info.get("T"):
        return "⚠ 台股報價：最近交易日都拿不到上市＋上櫃同一天的官方表（" + "；".join(info.get("tried") or []) + "）"
    def ck(c):
        ok, n = c
        return f"{ok}/{n}（{ok / n:.0%}）" if n else "略過（前一交易日分片不存在）"
    s = (f"台股報價日 {info['T']}：上市 {info['tw_src']} {info['tw_n']} 檔・自檢 {ck(info['tw_check'])}"
         f"｜上櫃 {info['tp_src']} {info['tp_n']} 檔・自檢 {ck(info['tp_check'])}")
    if info.get("tried"):
        s += "｜先試過：" + "；".join(info["tried"])
    return s
