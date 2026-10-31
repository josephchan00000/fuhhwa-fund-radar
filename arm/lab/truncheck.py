"""截斷重建（docs/lab_signal_quality_plan.md 第 5、8 節，A 段第 2 道）：抓「偷看未來」。

原始資料截到某一天（日資料留到那天；月資料留到「照公布時間差那天已經公布」的月份，REL 表，沒列的留到前一個月），
照網頁同一套程式整條重算景氣頁的 0～100（各項目與面向），
和用全部資料算的比：截斷那天以前的每一天都要一樣。不一樣＝那一天當時其實還拿不到的資料被用到了。
補缺月（heat.fill_gaps）在截斷之後才補，和當時的人看到的一樣。

三層，各自只假設上一層沒問題：
  ① 景氣頁 0～100：check(day, full) → {"tw"／指數: {"items": 比了幾個, "bad": [[項目, 第一天不同, 不同的天數, 全部, 截斷]]}}
     （cut 一個落檔截到 day；load_tw／load_us 同 heatcalc.load／heatcalc_us.load，但每個落檔先截斷）
  ② 泡沫頁每月條件：bub_check(day, full) → {市場: {"rows": 比了幾個月, "bad": [[月底, 不同的欄位]]}}
     （load_bub 同 bubble.load_tw／load_us，但每個落檔先截斷；比 P1～F、G1、G2、等級）
  ③ 訊號：sig_check(F, day) → {"n": 比了幾個訊號, "bad": [[訊號, 第一個不同的日子]]}
     （F＝sigcat.frames() 的一個市場；把逐日資料截到 day 重新找訊號，day 以前的出現日、狀態、大跌後買點都要一樣）
"""
from __future__ import annotations

import math
import re

import numpy as np

from . import heat as H
from . import heatcalc as HC
from . import heatcalc_us as HU
from . import heatdata as HD
from . import heatspec as HS
from . import heatspec_us as U
from . import store

TOL = 1e-9


# 月資料的落檔 → 公布時間差（同 heatspec.RELEASE、heatspec_us.RELEASE 用到它的項目；一個落檔多個項目取最早的）
REL = {"ndc": (2, 28), "pmi": (1, 6), "orders": (1, 21), "exports": (2, 28), "twcpi": (1, 10), "uscpi": (1, 16),
       "money": (1, 27), "cbcbank": (1, 27), "sfbflow": (1, 6), "mmf": (1, 15), "rev": (1, 11),
       "us_philly": (0, 22), "us_cli": (1, 15), "us_bls": (1, 8), "us_umich": (1, 1), "us_wsts": (2, 10),
       "us_z1": (3, 15), "us_ebp": (1, 20), "us_m2": (1, 28), "us_shiller": (1, 1), "tsmc": (1, 11)}


def cut(ser, day: str, rel: tuple[int, int] | None = None):
    """{日期: …} 留到 day（含）；{YYYY-MM: …} 留到 day 已經公布的月份（rel＝公布時間差；沒給＝前一個月）；其他鍵不動。"""
    if not isinstance(ser, dict):
        return ser
    out = {}
    for k, v in ser.items():
        ks = str(k)
        if len(ks) == 10 and ks[4] == "-" and ks[7] == "-":
            if ks <= day:
                out[k] = v
        elif len(ks) == 7 and ks[4] == "-" and ks[5:7].isdigit():
            if (H.avail_date(ks, rel) <= day) if rel else (ks < day[:7]):
                out[k] = v
        else:
            out[k] = v
    return out


def load_tw(day: str) -> dict:
    D = {n: cut(HD.load(n), day, REL.get(n)) for n in HC.FILES}
    D["uscpi"] = H.fill_gaps(D.get("uscpi") or {}, HS.GAP_FILL_MAX, geo=True)
    D["rev"] = HC.rev_sums([(ym, doc) for ym, doc in store.load("rev") if H.avail_date(str(ym)[:7], REL["rev"]) <= day],
                           HC.fin_codes())
    from .heatcalc_bub import load_tw_val
    D["twval"] = cut(load_tw_val(), day)
    return D


def load_us(day: str) -> dict:
    D = {n: cut(HD.load(n), day, REL.get(n)) for n in HU.FILES}
    D["us_bls"] = HU.fill_bls(D.get("us_bls") or {})
    D["tsmc"] = cut(HU.tsmc_rev(), day, REL["tsmc"])
    return D


def _diff(a: list, b: list, cal: list, n: int) -> tuple | None:
    """前 n 天：(第一天不同, 不同的天數, 全部的值, 截斷的值)；一樣回 None。"""
    bad = []
    for i in range(n):
        x, y = a[i] if i < len(a) else None, b[i] if i < len(b) else None
        fx = x is not None and not (isinstance(x, float) and math.isnan(x))
        fy = y is not None and not (isinstance(y, float) and math.isnan(y))
        if fx != fy or (fx and abs(float(x) - float(y)) > TOL):
            bad.append(i)
    if not bad:
        return None
    i = bad[0]
    return cal[i], len(bad), a[i], b[i] if i < len(b) else None


def compare(Bf: dict, Bc: dict, day: str) -> dict:
    """同一個市場：全部資料 Bf、截斷 Bc；比截斷那天以前每一天的各項目 0～100（hc）與面向分數（comp）。"""
    cal = Bf["cal"]
    n = sum(1 for d in cal if d <= day)
    if Bc["cal"][:n] != cal[:n]:
        return {"items": 0, "bad": [["日曆", "截斷前的日曆不同"]]}
    out = {"items": 0, "bad": []}
    for grp in ("hc", "comp"):
        for k, a in sorted((Bf.get(grp) or {}).items()):
            out["items"] += 1
            b = (Bc.get(grp) or {}).get(k)
            if b is None:
                if any(v is not None for v in list(a)[:n]):
                    out["bad"].append([f"{grp}:{k}", "截斷之後沒有這一項"])
                continue
            d = _diff(list(a), list(b), cal, n)
            if d:
                out["bad"].append([f"{grp}:{k}", *d])
    return out


def check(day: str, full: dict | None = None) -> dict:
    """截斷到 day 重算台股與美股四個指數的景氣頁，和 full（{"tw": B, 指數: B}；沒給就現算）比。"""
    full = full if full is not None else {"tw": HC.build(), **HU.build_all()}
    out = {"tw": compare(full["tw"], HC.build(load_tw(day)), day)}
    BA = HU.build_all(load_us(day))
    for idx in U.INDEX_ORDER:
        if idx in full and idx in BA:
            out[idx] = compare(full[idx], BA[idx], day)
    return out


# ── ② 泡沫頁 ──────────────────────────────────────────────────────────────────

# 泡沫頁才用到的季資料（同 heatcalc_us.GDP_REL、bubspec.FUND_REL4／PROXY_REL）
REL_BUB = {"us_gdp": (2, 1), "us_cp": (3, 1), "us_tech_q": (3, 1)}
BUB_KEYS = ("P1", "P2", "P3", "E", "V", "G1", "G2", "G", "gs", "F", "L", "L3v", "L2v", "L1", "Gr")


def cut_q(ser, day: str):
    """{YYYY-Qn: …}（專業預測者調查）留到 day 已經公布的季（fwd.spf_avail）；其他鍵不動。"""
    from . import fwd as FW
    out = {}
    for k, v in (ser or {}).items():
        m = re.match(r"^(\d{4})-Q([1-4])$", str(k))
        if not m or FW.spf_avail(int(m.group(1)), int(m.group(2))) <= day:
            out[k] = v
    return out


def load_bub(day: str) -> tuple[dict, dict]:
    """同 bubble.load_tw／load_us，但每個落檔先截斷（台股估值 twval 是月底市值與當時已到期的四季淨利，截到 day 的前一個月）。"""
    from . import bubble as B
    from .heatcalc_bub import load_tw_val
    rel = {**REL, **REL_BUB}
    tw = {n: cut(HD.load(n), day, rel.get(n)) for n in B.TW_FILES}
    tw["twval"] = cut(load_tw_val(), day)
    us = {n: cut(HD.load(n), day, rel.get(n)) for n in B.US_FILES}
    us["us_spf"] = cut_q(HD.load("us_spf"), day)
    return tw, us


def compare_bub(Xf: dict, Xc: dict, day: str) -> dict:
    """bubble.compute 的全部資料 Xf、截斷 Xc：截斷那天以前每個月底的條件與等級都要一樣。"""
    out = {}
    for mk in ("tw", "spx", "ixic", "ndx", "sox"):
        rf = ((Xf.get(mk) or {}).get("_C") or {}).get("rows") or []
        rc = {r["d"]: r for r in ((Xc.get(mk) or {}).get("_C") or {}).get("rows") or []}
        n, bad = 0, []
        for r in rf:
            if r["d"] > day:
                break
            c = rc.get(r["d"])
            if c is None:
                bad.append([r["d"], "截斷之後沒有這個月"])
                continue
            n += 1
            diff = [k for k in BUB_KEYS if r.get(k) != c.get(k)]
            if diff:
                bad.append([r["d"], diff])
        out[mk] = {"rows": n, "bad": bad}
    return out


def bub_check(day: str, full: dict | None = None) -> dict:
    """截斷到 day 重算泡沫頁五個市場的每月條件，和 full（bubble.compute()；沒給就現算）比。"""
    from . import bubble as B
    T = B.load_cv_table()
    full = full if full is not None else B.compute(T)
    tw, us = load_bub(day)
    return compare_bub(full, B.compute(T, tw, us), day)


# ── ③ 訊號 ────────────────────────────────────────────────────────────────────

def cut_frame(F: dict, day: str) -> dict:
    """sigcat.frames() 的一個市場截到 day（含）：逐日陣列（含大跌後買點的輸入）切到那天，泡沫頁只留那天以前的月底。
    每週取樣的日子用全部資料的週末（day 那一週還沒過完就不算）：heatpos.week_ends 把最新一天當成週末，
    截斷那天如果不是週五，會多出一個「暫定」的週樣本——那是網頁平日的暫定訊號（另外量），不是偷看。"""
    T = len(F["cal"])
    c = sum(1 for d in F["cal"] if d <= day)

    def sl(a):
        if isinstance(a, dict):
            return {k: sl(v) for k, v in a.items()}
        if a is not None and not isinstance(a, str) and hasattr(a, "__len__") and len(a) == T:
            return a[:c]
        return a

    G = dict(F)
    G["cal"] = list(F["cal"][:c])
    G["px"] = np.asarray(F["px"])[:c]
    G["we"] = [i for i in F["we"] if i < c - 1 or (i == c - 1 and i < T - 1)]
    for key in ("vars", "cvars", "ivars", "bvars", "deriv"):
        G[key] = [sl(d) for d in (F.get(key) or [])]
    G["comp"] = sl(F["comp"])
    G["bub"] = [r for r in (F.get("bub") or []) if str(r.get("d")) <= day]
    G["IB"] = sl(F["IB"]) if F.get("IB") else F.get("IB")
    return G


def sig_map(F: dict, upto: int, upto_m: int) -> dict:
    """{訊號: 第 upto 天以前的出現日（事件）或在狀態中的日子＋有資料的日子（狀態）}，含大跌後買點。
    泡沫（每月一個樣本）只比第 upto_m 天以前：sigcat 只用已經過完的月份，截斷那個月在截斷的資料裡還沒過完
    （程式不知道那天是不是那個月最後一個交易日），要到下一個交易日才算——比全部資料晚一天，不是偷看。"""
    from . import sigcat as G
    out = {}
    for sd in G.signals(F):
        if sd["kind"] == "event":
            out[sd["id"]] = tuple(int(t) for t in sd["days"] if t < upto)
        else:
            samp = np.asarray(sd["samp"], dtype=np.int64)
            st = np.asarray(sd["state"], dtype=bool)
            m = samp < (upto_m if sd.get("monthly") else upto)
            out[sd["id"]] = (tuple(int(t) for t in samp[m][st[m]]), tuple(int(t) for t in samp[m]))
    for sd in G.buy_signals(F)[1]:
        out[sd["id"]] = tuple(int(t) for t in sd["days"] if t < upto)
    return out


def _first(a, b) -> int | None:
    """兩個訊號的紀錄第一個不同的日子（索引）。"""
    if a and isinstance(a[0], tuple):
        a, b = a[0] + a[1], (b or ((), ()))[0] + (b or ((), ()))[1]
    sa, sb = set(a), set(b or ())
    d = sa ^ sb
    return min(d) if d else None


def sig_check(F: dict, day: str) -> dict:
    """一個市場截到 day 重新找訊號，和全部資料的比：day 以前每一天都要一樣。"""
    cal = F["cal"]
    c = sum(1 for d in cal if d <= day)
    cm = sum(1 for d in cal if d[:7] < day[:7])
    a, b = sig_map(F, c, cm), sig_map(cut_frame(F, day), c, cm)
    bad = []
    for k in sorted(a):
        empty = a[k] in ((), ((), ()))
        if a[k] != b.get(k) and not (empty and k not in b):
            i = _first(a[k], b.get(k))
            bad.append([k, cal[i] if i is not None else "截斷之後沒有這個訊號"])
    return {"n": len(a), "bad": bad}
