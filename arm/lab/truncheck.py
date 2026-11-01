"""截斷重建（docs/lab_signal_quality_plan.md 第 5、8 節，A 段第 2 道）：抓「偷看未來」。

原始資料截到某一天（日資料留到那天；月資料留到「照公布時間差那天已經公布」的月份，REL 表，沒列的留到前一個月），
照網頁同一套程式整條重算景氣頁的 0～100（各項目與面向），
和用全部資料算的比：截斷那天以前的每一天都要一樣。不一樣＝那一天當時其實還拿不到的資料被用到了。
補缺月（heat.fill_gaps）在截斷之後才補，和當時的人看到的一樣。

三層，各自只假設上一層沒問題：
  ① 景氣頁 0～100：check(day, full) → {"tw"／指數: {"items": 比了幾個, "bad": [[項目, 第一天不同, 不同的天數, 全部, 截斷]]}}
     （cut 一個落檔截到 day；load_tw／load_us 同 heatcalc.load／heatcalc_us.load，但每個落檔先截斷）；
     也比邊際變化（heatpos.deriv 的一階、二階、二階熱度、狀態；2026-10-31 A-3b 加，那一層原本沒用到實際公布日）
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


# 月資料的落檔 → 公布時間差：直接取 heatspec.RELEASE、heatspec_us.RELEASE 用到它的項目（一個落檔多個項目取最早的；規格改了這裡跟著改）
REL = {"ndc": HS.RELEASE["B1"], "pmi": HS.RELEASE["B3"], "orders": HS.RELEASE["B4"], "exports": HS.RELEASE["B5"],
       "twcpi": HS.RELEASE["B7"], "uscpi": HS.RELEASE["B8"], "money": HS.RELEASE["L1"], "cbcbank": HS.RELEASE["L8"],
       "sfbflow": HS.RELEASE["L6"], "mmf": min(HS.RELEASE["G5"], U.RELEASE["R10"]), "rev": HS.RELEASE["B6"],
       "us_philly": U.RELEASE["F1"], "us_cli": U.RELEASE["F3"], "us_bls": U.RELEASE["F5"], "us_umich": U.RELEASE["F9"],
       "us_wsts": U.RELEASE["F10"], "us_z1": U.RELEASE["S5"], "us_ebp": U.RELEASE["R6"], "us_m2": U.RELEASE["R7"],
       "us_shiller": (1, 1), "tsmc": U.RELEASE["F11"]}


def late_tables() -> dict:
    """實際拿得到的日子（和每天建頁同一份，heatspec VER 11～12、heatspec_us VER 4～5）：截斷也照實際日期，
    才看得出「當時真的拿得到什麼」。→ {落檔: {月: 日}}、勞工統計局三欄、月營收與台積電的申報期限。"""
    k = HU.known_late()
    return {"uscpi": HC.late_b8(), "us_z1": k["S5"], "bls": (k["F5"], k["F6"], k["F7"])}


# 勞工統計局 us_bls 三欄各自的公布時間差（失業率、CPI、核心 CPI；heatspec_us.RELEASE 的 F5、F6、F7）
BLS_REL = (U.RELEASE["F5"], U.RELEASE["F6"], U.RELEASE["F7"])


def _ok(ym: str, day: str, rel, late) -> bool:
    return max(H.avail_date(ym, rel), (late or {}).get(ym, "")) <= day if rel else ym < day[:7]


def cut(ser, day: str, rel: tuple[int, int] | None = None, late: dict | None = None):
    """{日期: …} 留到 day（含）；{YYYY-MM: …} 留到 day 已經公布的月份（rel＝公布時間差、late＝已知延後公布的實際日期；
    沒給 rel＝前一個月）；其他鍵不動。"""
    if not isinstance(ser, dict):
        return ser
    out = {}
    for k, v in ser.items():
        ks = str(k)
        if len(ks) == 10 and ks[4] == "-" and ks[7] == "-":
            if ks <= day:
                out[k] = v
        elif len(ks) == 7 and ks[4] == "-" and ks[5:7].isdigit():
            if _ok(ks, day, rel, late):
                out[k] = v
        else:
            out[k] = v
    return out


def cut_bls(ser: dict, day: str, late: tuple | None = None) -> dict:
    """勞工統計局三欄各自截：那一欄在 day 還沒公布就當沒有（同一個月的失業率和 CPI 公布日不同）。"""
    late = late_tables()["bls"] if late is None else late
    out = {}
    for ym, v in (ser or {}).items():
        row = [x if x is not None and j < len(BLS_REL) and _ok(str(ym), day, BLS_REL[j], late[j]) else None
               for j, x in enumerate(v or [])]
        if any(x is not None for x in row):
            out[ym] = row
    return out


def load_tw(day: str) -> dict:
    """同 heatcalc.load，但每個落檔先截斷（月營收照公布時間差、台股估值截到 day 的前一個月）。"""
    from .heatcalc_bub import load_tw_val
    lt = late_tables()
    D = {n: cut(HD.load(n), day, REL.get(n), lt.get(n)) for n in HC.FILES}
    docs = list(store.load("rev"))
    rl = HC.late_rev({str(ym)[:7] for ym, _ in docs})
    D = HC.prep(D, [(ym, doc) for ym, doc in docs if _ok(str(ym)[:7], day, REL["rev"], rl)])
    D["twval"] = cut(load_tw_val(), day)
    return D


def load_us(day: str) -> dict:
    """同 heatcalc_us.load，但每個落檔先截斷（勞工統計局三欄各自截）。"""
    lt = late_tables()
    D = {n: cut(HD.load(n), day, REL.get(n), lt.get(n)) for n in HU.FILES}
    D["us_bls"] = cut_bls(HD.load("us_bls"), day, lt["bls"])
    ts = HU.tsmc_rev()
    return HU.prep(D, cut(ts, day, REL["tsmc"], HC.late_rev(ts)))


def _diff(a: list, b: list, cal: list, n: int) -> tuple | None:
    """前 n 天：(第一天不同, 不同的天數, 全部的值, 截斷的值)；一樣回 None。"""
    bad = []
    for i in range(n):
        x, y = a[i] if i < len(a) else None, b[i] if i < len(b) else None
        fx = x is not None and not (isinstance(x, float) and math.isnan(x))
        fy = y is not None and not (isinstance(y, float) and math.isnan(y))
        num = fx and fy and isinstance(x, (int, float)) and isinstance(y, (int, float))
        if fx != fy or (num and abs(float(x) - float(y)) > TOL) or (fx and fy and not num and x != y):
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


DERIV_KEYS = ("d1", "d2", "acc", "state")


def compare_deriv(Bf: dict, Bc: dict, day: str) -> dict:
    """邊際變化（heatpos.deriv；用目前換上的規格）：截斷那天以前每一天的一階、二階、二階熱度、狀態都要一樣。"""
    from . import heatpos as P
    cal = Bf["cal"]
    n = sum(1 for d in cal if d <= day)
    out = {"items": 0, "bad": []}
    for k in HS.DERIV:
        a, b = P.deriv(Bf, k), P.deriv(Bc, k)
        for f in DERIV_KEYS:
            out["items"] += 1
            d = _diff(list(a[f]), list(b[f]), cal, n)
            if d:
                out["bad"].append([f"deriv:{k}:{f}", *d])
    return out


def _both(Bf: dict, Bc: dict, day: str) -> dict:
    r, dv = compare(Bf, Bc, day), compare_deriv(Bf, Bc, day)
    return {"items": r["items"] + dv["items"], "bad": r["bad"] + dv["bad"]}


def check(day: str, full: dict | None = None) -> dict:
    """截斷到 day 重算台股與美股四個指數的景氣頁，和 full（{"tw": B, 指數: B}；沒給就現算）比（0～100、面向、邊際變化）。"""
    full = full if full is not None else {"tw": HC.build(), **HU.build_all()}
    out = {"tw": _both(full["tw"], HC.build(load_tw(day)), day)}
    BA = HU.build_all(load_us(day))
    for idx in U.INDEX_ORDER:
        if idx in full and idx in BA:
            with HS.use(U.spec_for(idx)):
                out[idx] = _both(full[idx], BA[idx], day)
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
    from . import bubspec as BS
    lt = {**late_tables(), "us_gdp": U.GDP_LATE, "us_cp": BS.CP_LATE, "us_tech_q": BS.CP_LATE}   # bubspec VER 5
    tw = {n: cut(HD.load(n), day, rel.get(n), lt.get(n)) for n in B.TW_FILES}
    tw["twval"] = cut(load_tw_val(), day)
    us = {n: cut(HD.load(n), day, rel.get(n), lt.get(n)) for n in B.US_FILES}
    us["us_bls"] = cut_bls(HD.load("us_bls"), day, lt["bls"])
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
    週末照網頁每天的算法重算（heatpos.week_ends 顯示用；done_week_ends 訊號用：那一週還沒過完的最新一天不算週末）。"""
    from . import heatpos as P
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
    G["we"], G["wes"] = P.week_ends(G["cal"]), P.done_week_ends(G["cal"], P.market_closed(F.get("mk")))
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
