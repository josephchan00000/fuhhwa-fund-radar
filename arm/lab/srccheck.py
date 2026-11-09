"""資料來源比對（docs/lab_signal_quality_plan.md 第 11.3 節，A-3c）：同一個數字的兩個來源、或可以互相推算的兩條序列，差太多就列出來。

只讀已入庫的資料、不連網；每週 verify.yml 跟著 scripts/run_verify.py 跑（不一致＝bad，網頁標紅、推播，不擋發佈）。
每一項 → {"n": 比了幾筆, "bad": [[項目, 日期, 甲, 乙, 差], …]}：
  inst      三大法人（外資、投信、自營商、合計）：FinMind（訊號用）vs 證交所 BFI82U（data/macro_chips.json，近 45 個交易日），
            差 > TOL_INST 億；證交所有、FinMind 沒有的交易日也列（訊號的那一天會變成「沒有資料」）。
  margin    融資餘額：FinMind vs 證交所 MI_MARGN，差 > TOL_MARGIN 億。
  yields    美債 2 年、10 年殖利率：美國財政部 vs 聯準會 H.15（兩個官方來源），差 > TOL_YIELD 個百分點。
  taiex     加權指數：Yahoo 每天收盤的月平均 vs 國發會月平均（1997 起），差 > TOL_TAIEX；交易日不到 MIN_DAYS 天的月份不比。
  taiex_day 加權指數每天收盤：證交所（turnover，景氣頁與訊號用的就是它）vs Yahoo，差 > TOL_TAIEX_DAY。
            Yahoo 2000-10-23 收盤錯（差 1.3%，KNOWN_YAHOO）；Yahoo 在三個颱風停市日（2001-09-18、2014-07-23、2016-07-08）有假的一列、
            沒有 1999～2018 年週六補班日的交易——日曆以證交所為準（heatcalc.calendar），這幾天不影響計算。
  etf       S&P 500 vs SPY、那斯達克 100 vs QQQ 的每天漲跌（ETF_SINCE 起），差 > TOL_ETF。
            2010 年以前 Yahoo 的 ETF 有幾天價格明顯有問題（2008-09-29 QQQ、2008-10-10～13 SPY），這兩檔只用在寬度的參考讀數，不比。
  same      同一個數字兩條抓取管線：VIX、美元指數、費半（景氣頁落檔 vs 全球溫度計），差 > TOL_SAME；新台幣（央行 vs 溫度計）差 > TOL_FX。
            溫度計的新台幣（Yahoo TWD=X）2026-11-06 是 33.1093，央行收盤 32.768、Yahoo 前後兩天 32.821／32.773——
            使用者 2026-11-09 決定當 Yahoo 錯誤（KNOWN_YAHOO_FX；沒有第二個可信來源，景氣頁與訊號用的是央行那一條）。
  jumps     單日跳動：|日對數報酬| > JUMP（各序列自己的門檻），或值 ≤ 0。KNOWN_JUMPS＝核對過真的發生的日子（1987 股災等），不列。
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from . import heatdata as HD

ROOT = Path(__file__).resolve().parents[2]
MACRO = ROOT / "data" / "macro_chips.json"
TOL_INST = 0.2            # 億元（證交所公布到 0.01 億；實測最大差 0.055）
TOL_MARGIN = 0.5          # 億元（溫度計存到 0.1 億）
TOL_YIELD = 0.03          # 百分點
TOL_TAIEX = 0.01          # 月平均相對差
MIN_DAYS = 15
TOL_TAIEX_DAY = 0.002     # 每天收盤相對差（實測 1999～2026：除 KNOWN_YAHOO 外最大 0.05%）
KNOWN_YAHOO = ("2000-10-23",)
TOL_ETF = 0.025           # 日報酬差（對數）
ETF_SINCE = "2010-01-01"
TOL_SAME = 0.005          # 同來源兩條管線：相對差
TOL_FX = 0.01             # 新台幣：央行收盤 vs Yahoo，收盤時點不同
KNOWN_YAHOO_FX = ("2026-11-06",)   # 溫度計（Yahoo）新台幣錯的日子，不比（見檔頭 same）
JUMP = {"taiex": 0.12, "us_px_spx": 0.15, "us_px_ixic": 0.15, "us_px_ndx": 0.15, "us_px_sox": 0.15,
        "vix": 1.0, "us_dxy": 0.05, "usdtwd": 0.05}
KNOWN_JUMPS = {"us_px_spx": ("1933-03-15", "1987-10-19"), "us_px_ndx": ("1987-10-19", "2001-01-03"),
               "us_px_sox": ("2000-10-19", "2001-01-03", "2020-03-16", "2025-04-09")}


def _macro() -> dict:
    try:
        return (json.loads(MACRO.read_text(encoding="utf-8")).get("series") or {})
    except (OSError, ValueError):
        return {}


def _r(x: float, d: int = 4) -> float:
    return round(float(x), d)


def compare(name: str, a: dict, b: dict, tol: float, rel: bool = False) -> dict:
    """兩條 {日期: 值} 共同日期逐一比：|a − b|（rel＝相對 b）> tol 列出。"""
    n, bad = 0, []
    for k in sorted(set(a) & set(b)):
        x, y = a[k], b[k]
        if x is None or y is None:
            continue
        n += 1
        d = abs(x - y) / abs(y) if rel and y else abs(x - y)
        if d > tol:
            bad.append([name, k, _r(x), _r(y), _r(d)])
    return {"n": n, "bad": bad}


def _merge(*rs: dict) -> dict:
    return {"n": sum(r["n"] for r in rs), "bad": [b for r in rs for b in r["bad"]]}


def inst(D: dict | None = None, M: dict | None = None) -> dict:
    D = HD.load("inst") if D is None else D
    M = _macro() if M is None else M
    g = lambda v, k: float(v.get(k) or 0)                                       # noqa: E731
    fm = {"inst_total": {k: g(v, "total") / 1e8 for k, v in D.items()},
          "inst_foreign": {k: (g(v, "Foreign_Investor") + g(v, "Foreign_Dealer_Self")) / 1e8 for k, v in D.items()},
          "inst_trust": {k: g(v, "Investment_Trust") / 1e8 for k, v in D.items()},
          "inst_dealer": {k: (g(v, "Dealer_self") + g(v, "Dealer_Hedging")) / 1e8 for k, v in D.items()}}
    out = _merge(*(compare(f"法人・{k}", fm[k], M.get(k) or {}, TOL_INST) for k in fm))
    tw = M.get("inst_total") or {}
    if D and tw:
        lo, hi = min(D), max(D)
        out["bad"] += [["法人・FinMind 缺日", k, None, _r(tw[k]), None] for k in sorted(tw) if lo <= k <= hi and k not in D]
    return out


def margin(D: dict | None = None, M: dict | None = None) -> dict:
    D = HD.load("margin") if D is None else D
    M = _macro() if M is None else M
    a = {k: v[0] / 1e8 for k, v in D.items() if isinstance(v, list) and v and v[0]}
    return compare("融資餘額（億）", a, M.get("margin_bal") or {}, TOL_MARGIN)


def yields(ust: dict | None = None, h15: dict | None = None) -> dict:
    """財政部 {日: [3 個月, 2 年, 10 年]} vs H.15 {日: [3 個月國庫券, 3 個月固定期限, 2 年, 10 年]}。"""
    ust = HD.load("ust") if ust is None else ust
    h15 = HD.load("us_h15") if h15 is None else h15
    col = lambda s, j: {k: v[j] for k, v in s.items() if isinstance(v, list) and len(v) > j and v[j] is not None}  # noqa: E731
    return _merge(compare("美債 2 年", col(ust, 1), col(h15, 2), TOL_YIELD),
                  compare("美債 10 年", col(ust, 2), col(h15, 3), TOL_YIELD))


def taiex(tx: dict | None = None, tm: dict | None = None) -> dict:
    tx = HD.load("taiex") if tx is None else tx
    tm = HD.load("taiexm") if tm is None else tm
    mon: dict[str, list] = defaultdict(list)
    for k, v in tx.items():
        if v:
            mon[k[:7]].append(v)
    last = max(mon) if mon else ""
    a = {ym: sum(v) / len(v) for ym, v in mon.items() if ym < last and len(v) >= MIN_DAYS}
    return compare("加權指數月平均（Yahoo vs 國發會）", a, {k: v for k, v in tm.items() if v}, TOL_TAIEX, rel=True)


def taiex_day(off: dict | None = None, yh: dict | None = None) -> dict:
    off = HD.load("turnover") if off is None else off
    yh = HD.load("taiex") if yh is None else yh
    a = {d: v[1] for d, v in off.items() if isinstance(v, list) and len(v) > 1 and v[1]}
    b = {d: v for d, v in yh.items() if v and d not in KNOWN_YAHOO}
    return compare("加權指數收盤（證交所 vs Yahoo）", a, b, TOL_TAIEX_DAY, rel=True)


def _rets(s: dict) -> dict:
    ks = sorted(k for k in s if s[k])
    return {ks[i]: math.log(s[ks[i]] / s[ks[i - 1]]) for i in range(1, len(ks))}


def etf(pairs=(("us_px_spx", "us_spy", "S&P 500 vs SPY"), ("us_px_ndx", "us_qqq", "那斯達克 100 vs QQQ")),
        load=HD.load, since: str = ETF_SINCE) -> dict:
    rs = []
    for a, b, name in pairs:
        ra, rb = _rets(load(a)), _rets(load(b))
        rs.append(compare(f"日漲跌・{name}", {k: v for k, v in ra.items() if k >= since}, rb, TOL_ETF))
    return _merge(*rs)


def same(load=HD.load, M: dict | None = None) -> dict:
    M = _macro() if M is None else M
    return _merge(compare("VIX", load("vix"), M.get("vix") or {}, TOL_SAME, rel=True),
                  compare("美元指數", load("us_dxy"), M.get("dxy") or {}, TOL_SAME, rel=True),
                  compare("費半", load("us_px_sox"), M.get("sox") or {}, TOL_SAME, rel=True),
                  compare("新台幣（央行 vs 溫度計）", load("usdtwd"),
                          {k: v for k, v in (M.get("usdtwd") or {}).items() if k not in KNOWN_YAHOO_FX}, TOL_FX, rel=True))


def jumps(load=HD.load, thr: dict | None = None, known: dict | None = None) -> dict:
    thr = JUMP if thr is None else thr
    known = KNOWN_JUMPS if known is None else known
    n, bad = 0, []
    for name, t in thr.items():
        s = load(name)
        bad += [["值 ≤ 0", k, name, _r(v), None] for k, v in sorted(s.items()) if v is not None and v <= 0]
        r = _rets(s)
        n += len(r)
        bad += [["單日跳動", k, name, _r(v), t] for k, v in sorted(r.items()) if abs(v) > t and k not in known.get(name, ())]
    return {"n": n, "bad": bad}


CHECKS = {"inst": inst, "margin": margin, "yields": yields, "taiex": taiex, "taiex_day": taiex_day, "etf": etf, "same": same,
          "jumps": jumps}


def run_all() -> dict:
    """→ {項目: {"n", "bad"}}；某一項讀不到資料就記成 bad（不擋其他項）。"""
    out = {}
    for k, f in CHECKS.items():
        try:
            out[k] = f()
        except Exception as e:                            # noqa: BLE001
            out[k] = {"n": 0, "bad": [[k, None, f"{type(e).__name__}: {e}"[:120], None, None]]}
    return out
