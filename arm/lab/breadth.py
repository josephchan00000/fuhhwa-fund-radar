"""寬度與深度（規格 arm/lab/breadthspec.py VER 1；docs/lab_breadth_plan.md 第 9、10 節）。只研究：不進頁面、不進訊號總覽。

一、股票層級：台股大型股撐盤、一般股票離 200 日線（bt3d 面板＋官方分片，範圍同 T5～T7）；美股上漲家數與上漲成交金額占比
   （us_breadth）、大型股撐盤（含息 ETF：SPY − RSP、QQQ − QQEW）。0～100 照景氣項目（heat.pct_series），訊號與判定用
   sigcat 的 _var_signals／evaluate（sigspec VER 24 的規則原樣）。
二、產業層級：bubind 四組的泡沫寬度（等級 ≥ 2 的產業占幾成）與深度（市值占幾成；ff、tw），美國 48 細產業 1931 起驗證 ①②。
研究：scripts/run_breadth.py → data/lab/breadth_research.json。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

from .. import clock
from . import breadthspec as S

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "lab" / "breadth_research.json"


# ── 一、股票層級：原始讀數 ─────────────────────────────────────────────────

def tw_matrix(P, cap_min: float | None = None) -> tuple[list, np.ndarray, np.ndarray]:
    """bt3d.Panel → (日曆, 含息還原收盤 [檔, 天]（缺＝NaN）, 當天在範圍內 [檔, 天])。範圍＝當天用的月底市值 ≥ cap_min（同 heatdata.breadth）。"""
    from . import heatdata as HD
    cap_min = HD.CAP_MIN if cap_min is None else cap_min
    codes = list(P.codes)
    C = np.full((len(codes), P.T), np.nan)
    E = np.zeros((len(codes), P.T), dtype=bool)
    for k, c in enumerate(codes):
        C[k] = [np.nan if x is None else float(x) for x in P.s[c]["c"]]
        E[k] = [bool(v) and v >= cap_min for v in P.cap[c]]
    return list(P.cal), C, E & ~np.isnan(C)


def ewgap_tw(cal: list, C: np.ndarray, E: np.ndarray, tr: dict, lb: int = S.LB, min_n: int = S.MIN_N) -> dict:
    """{日期: 加權報酬指數 lb 日報酬 − 當天範圍內個股 lb 日報酬的平均}（百分點）；兩端都要有收盤，少於 min_n 檔沒有值。"""
    out = {}
    for i in range(lb, len(cal)):
        a, b = tr.get(cal[i - lb]), tr.get(cal[i])
        if not a or not b:
            continue
        m = E[:, i] & ~np.isnan(C[:, i - lb])
        if int(m.sum()) < min_n:
            continue
        ew = float(np.mean(C[m, i] / C[m, i - lb] - 1.0))
        out[cal[i]] = 100.0 * ((b / a - 1.0) - ew)
    return out


def ma200_tw(cal: list, C: np.ndarray, E: np.ndarray, n: int = S.MA_N, min_n: int = S.MIN_N) -> dict:
    """{日期: 當天範圍內、近 n 天都有收盤的個股「收盤 ÷ n 日平均 − 1」的中位數}（百分比）。"""
    have = ~np.isnan(C)
    cs = np.cumsum(np.where(have, C, 0.0), axis=1)
    cc = np.cumsum(have, axis=1)
    out = {}
    for i in range(n - 1, len(cal)):
        s = cs[:, i] - (cs[:, i - n] if i >= n else 0.0)
        k = cc[:, i] - (cc[:, i - n] if i >= n else 0)
        m = E[:, i] & (k == n)
        if int(m.sum()) < min_n:
            continue
        out[cal[i]] = 100.0 * float(np.median(C[m, i] / (s[m] / n) - 1.0))
    return out


def us_adv(br: dict, w: int = S.ADV_W) -> tuple[dict, dict]:
    """us_breadth（{日期: [上漲, 下跌, 平盤, 上漲成交金額, 下跌成交金額, …]}）→ (上漲家數占比, 上漲成交金額占比)，近 w 筆合計（%）。"""
    ks = sorted(k for k, v in br.items() if v and len(v) >= 5)
    A = np.array([[br[k][0], br[k][1], br[k][3], br[k][4]] for k in ks], dtype=float)
    adv, upv = {}, {}
    for i in range(w - 1, len(ks)):
        s = A[i - w + 1:i + 1].sum(axis=0)
        if s[0] + s[1] > 0:
            adv[ks[i]] = 100.0 * s[0] / (s[0] + s[1])
        if s[2] + s[3] > 0:
            upv[ks[i]] = 100.0 * s[2] / (s[2] + s[3])
    return adv, upv


def ewgap_us(cw: dict, ew: dict, lb: int = S.LB) -> dict:
    """兩檔都有含息收盤的交易日上：市值加權 ETF lb 日報酬 − 等權 ETF lb 日報酬（百分點）。"""
    ks = sorted(set(k for k, v in cw.items() if v) & set(k for k, v in ew.items() if v))
    return {ks[i]: 100.0 * ((cw[ks[i]] / cw[ks[i - lb]] - 1.0) - (ew[ks[i]] / ew[ks[i - lb]] - 1.0))
            for i in range(lb, len(ks))}


def heat100(cal: list, raw: dict) -> np.ndarray:
    """原始讀數 → 這個日曆上的 0～100（同景氣項目：和自己過去 PCT_WIN 個交易日比、至少 PCT_MIN 天、只用當天以前；高＝熱）。"""
    from . import heat as H
    from . import heatspec as HS
    p = H.pct_series([raw.get(d) for d in cal], HS.PCT_WIN["d"], HS.PCT_MIN["d"])
    return np.array([np.nan if v is None else float(H.to_heat(v, 1)) for v in p], dtype=float)


def raw_vars() -> dict:
    """{變數: {市場: {日期: 原始讀數}}}（台股兩個要讀個股面板，約一兩分鐘）。"""
    from . import bt3d, store
    from . import heatdata as HD
    P = bt3d.Panel()
    HD.extend(P, HD.ShardPanel())
    cal, C, E = tw_matrix(P)
    tr = (store.read_json("v3_tr.json", {}) or {}).get("q") or {}
    adv, upv = us_adv(HD.load("us_breadth") or {})
    etf = {s: HD.load(f"us_{s.lower()}") or {} for s in ("SPY", "RSP", "QQQ", "QQEW")}
    out = {"TW_EWGAP": {"tw": ewgap_tw(cal, C, E, tr)}, "TW_MA200": {"tw": ma200_tw(cal, C, E)},
           "US_ADV": {mk: adv for mk in S.VAR_MKT["US_ADV"]}, "US_UPV": {mk: upv for mk in S.VAR_MKT["US_UPV"]},
           "US_EWGAP": {mk: ewgap_us(etf[a], etf[b]) for mk, (a, b) in S.EW_PAIRS.items()}}
    return out


# ── 一、股票層級：訊號與判定（sigcat 原樣） ──────────────────────────────────

def var_rows(F: dict, key: str, x: np.ndarray, Yc: dict) -> list[dict]:
    """一個變數在一個市場的 6 種訊號（sigspec 第 4.1 節同一套，含相反極端的分段與失效）→ sigcat.evaluate 的列；分類記成 "bd"。"""
    from . import sigcat as SC
    v = {"key": key, "name": S.VAR_NAMES[key], "grp": "bd", "H": S.H, "x": x}
    rows = []
    for sd in SC._var_signals(F, v, "heat"):
        sd["id"] = sd["id"].replace(":heat:", ":bd:", 1)
        sd["cat"] = "bd"
        rows.append(SC.evaluate(F, sd, Yc))
    return rows


_KEEP = ("id", "mk", "var", "sig", "name", "kind", "H", "th", "a", "z", "tier", "dir")
_DIR_KEEP = ("n", "n10", "hit", "hit10", "base", "base10", "p", "tier", "mdd", "mdd_base", "mddw", "mddw_d")


def compact(r: dict) -> dict:
    out = {k: r.get(k) for k in _KEEP}
    for d in ("up", "warn"):
        out[d] = {k: (r.get(d) or {}).get(k) for k in _DIR_KEEP if k in (r.get(d) or {})}
    out["n_occ"] = len(r.get("occ") or [])
    return out


def stock_research(F: dict, raw: dict | None = None) -> dict:
    """五個市場的 frame（sigcat.frames）→ {"rows": [...], "now": {變數: {市場: {d, raw, heat}}}}。"""
    raw = raw if raw is not None else raw_vars()
    rows, now = [], {}
    Yc = {mk: {"bases": {}} for mk in F}
    for key in S.MKT_VARS:
        for mk in S.VAR_MKT[key]:
            if mk not in F:
                continue
            ser = raw.get(key, {}).get(mk) or {}
            cal = F[mk]["cal"]
            x = heat100(cal, ser)
            rows += [compact(r) for r in var_rows(F[mk], key, x, Yc[mk])]
            ks = sorted(ser)
            ok = np.nonzero(~np.isnan(x))[0]
            now.setdefault(key, {})[mk] = {"raw_a": ks[0] if ks else None, "raw_z": ks[-1] if ks else None,
                                          "raw": ser[ks[-1]] if ks else None,
                                          "heat_d": cal[int(ok[-1])] if len(ok) else None,
                                          "heat": float(x[ok[-1]]) if len(ok) else None,
                                          "heat_a": cal[int(ok[0])] if len(ok) else None}
    return {"rows": rows, "now": now}


# ── 二、產業層級 ──────────────────────────────────────────────────────────

def levels(grp: str, T: dict | None = None, Lcpi: dict | None = None) -> dict:
    """bubind 的一組 → {"L": {產業: {月: 等級}}, "mme": 那一組的大盤月底值}（從 P1、P2 都有值的那個月起，同 bubind.group_research）。"""
    from . import bubble as BU
    from . import bubind as BI
    T = T or BU.load_cv_table()
    if grp in ("ff", "us"):
        Lcpi = Lcpi if Lcpi is not None else BU.us_inputs(BU.load_us())["L"]
        I = BI.ff_inputs(Lcpi) if grp == "ff" else BI.us_inputs(Lcpi)
    elif grp == "tw":
        I = BI.tw_inputs()
    else:
        I = BI.tg_inputs()
    out = {}
    for code, Sx in ((I or {}).get("S") or {}).items():
        rows = BI.conditions(Sx, T)["rows"]
        j0 = next((j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None), None)
        if j0 is not None:
            out[code] = {r["d"]: r["L"] for r in rows[j0:] if r.get("L") is not None}
    return {"L": out, "mme": (I or {}).get("mme") or {}}


def caps_ff() -> dict:
    """美國 48 細產業每月市值＝家數 × 平均規模（Ken French 月初市值）→ {產業: {月: 百萬美元}}。"""
    from . import bubindspec as BI
    from . import heatdata as HD
    N, Sz = HD.load("us_ff49n") or {}, HD.load("us_ff49s") or {}
    out: dict = {}
    for j, code in enumerate(BI.FF49):
        if code in BI.FF_SKIP:
            continue
        for m in N:
            n = N[m][j] if j < len(N[m]) else None
            s = ((Sz.get(m) or [None] * 49)[j]) if m in Sz else None
            if n and s:
                out.setdefault(code, {})[m] = float(n) * float(s)
    return out


def caps_tw(cap_min: float | None = None) -> dict:
    """台股產業每月市值＝月底市值 ≥ 40 億的成分股市值合計（產業別同 bubind.tw_ind_map）→ {產業: {月: 元}}。"""
    from . import bt3d
    from . import bubind as BI
    from . import heatdata as HD
    cap_min = HD.CAP_MIN if cap_min is None else cap_min
    im = BI.tw_ind_map()
    out: dict = {}
    for d, caps in bt3d.month_end_caps():
        m = d[:7]
        for c, v in caps.items():
            g = im.get(c)
            if g and v and v >= cap_min:
                out.setdefault(g, {})[m] = out.setdefault(g, {}).get(m, 0.0) + float(v)
    return out


def breadth_series(Lv: dict, caps: dict | None = None) -> dict:
    """{產業: {月: 等級}} → {月: [過熱產業數, 有等級的產業數, 泡沫寬度, 泡沫深度或 None]}。"""
    months = sorted({m for d in Lv.values() for m in d})
    out = {}
    for m in months:
        have = [c for c, d in Lv.items() if m in d]
        hot = [c for c in have if Lv[c][m] >= S.LEVEL_MIN]
        dep = None
        if caps is not None:
            hv = [(c, (caps.get(c) or {}).get(m)) for c in have]
            tot = sum(v for _, v in hv if v)
            dep = sum(v for c, v in hv if v and Lv[c][m] >= S.LEVEL_MIN) / tot if tot > 0 else None
        out[m] = [len(hot), len(have), len(hot) / len(have) if have else None, dep]
    return out


def _mno(m: str) -> int:
    y, mo = map(int, m.split("-"))
    return y * 12 + mo


def fwd_dd(mme: dict, h: int = S.FWD_M) -> dict:
    """{月: 月底值} → {月: 之後 h 個月內從這個月底起算的最大回落}（之後 h 個月沒走完、中間缺月＝None）。"""
    from . import bubind as BI
    ms = sorted(m for m, v in mme.items() if v)
    vals = [mme[m] for m in ms]
    out = {}
    for i, m in enumerate(ms):
        j = i + h
        ok = j < len(ms) and _mno(ms[j]) - _mno(m) == h
        out[m] = BI.drawdown(vals, i, j) if ok else None
    return out


def _boot(ms: list, cols: dict, stat, rnd: random.Random, boot: int = S.BOOT, block: int = S.BLOCK) -> list:
    """以 block 個月一塊（移動區塊、可重複）重抽 boot 次 → stat(各欄的合計) 的值（None 的不算）；同 bubind.panel_test 的做法。"""
    n = len(ms)
    if n < 2 * block:
        return []
    pre = {k: np.concatenate([[0.0], np.cumsum(np.asarray(v, dtype=float))]) for k, v in cols.items()}
    starts = n - block + 1
    out = []
    for _ in range(boot):
        tot = {k: 0.0 for k in cols}
        got = 0
        while got < n:
            s0 = rnd.randrange(starts)
            for k in cols:
                tot[k] += pre[k][s0 + block] - pre[k][s0]
            got += block
        v = stat(tot)
        if v is not None:
            out.append(v)
    return out


def _ci(reps: list) -> tuple:
    if len(reps) < S.BOOT // 2:
        return None, None
    reps = sorted(reps)
    return reps[int(0.025 * len(reps))], reps[min(len(reps) - 1, int(0.975 * len(reps)))]


def test_one(ev: dict, dd: dict, rnd: random.Random) -> dict:
    """① 單看：事件月大跌的比例 − 全部月份的比例；ev＝{月: 是不是事件月}，dd＝{月: 之後 12 個月最大回落}。"""
    ms = sorted(m for m in ev if ev[m] is not None and dd.get(m) is not None)
    e = [1.0 if ev[m] else 0.0 for m in ms]
    c = [1.0 if dd[m] >= S.DD else 0.0 for m in ms]
    ec = [a * b for a, b in zip(e, c)]

    def st(t):
        return None if not t["e"] or not t["n"] else t["ec"] / t["e"] - t["c"] / t["n"]
    tot = {"e": sum(e), "ec": sum(ec), "c": sum(c), "n": float(len(ms))}
    lo, hi = _ci(_boot(ms, {"e": e, "ec": ec, "c": c, "n": [1.0] * len(ms)}, st, rnd))
    evm = [m for m, x in zip(ms, e) if x]
    diff = st(tot)
    epi = S.episodes(evm)
    return {"n": len(ms), "n_ev": len(evm), "p_ev": tot["ec"] / tot["e"] if tot["e"] else None, "p_all": tot["c"] / tot["n"] if ms else None,
            "diff": diff, "lo": lo, "hi": hi, "epi": epi, "a": ms[0] if ms else None, "z": ms[-1] if ms else None,
            "pass": S.passes(diff, lo, epi, S.MIN_EPI)}


def test_two(ev: dict, lv: dict, dd: dict, rnd: random.Random) -> dict:
    """② 加值：市場泡沫等級 ≥ LEVEL_MIN 的月份裡，事件月大跌的比例 − 非事件月的比例。lv＝{月: 市場等級}。"""
    ms = sorted(m for m in ev if ev[m] is not None and dd.get(m) is not None and lv.get(m) is not None)
    g = [1.0 if lv[m] >= S.LEVEL_MIN else 0.0 for m in ms]
    e = [1.0 if ev[m] else 0.0 for m in ms]
    c = [1.0 if dd[m] >= S.DD else 0.0 for m in ms]
    cols = {"ge": [a * b for a, b in zip(g, e)], "gec": [a * b * d for a, b, d in zip(g, e, c)],
            "gn": [a * (1.0 - b) for a, b in zip(g, e)], "gnc": [a * (1.0 - b) * d for a, b, d in zip(g, e, c)]}

    def st(t):
        return None if not t["ge"] or not t["gn"] else t["gec"] / t["ge"] - t["gnc"] / t["gn"]
    tot = {k: sum(v) for k, v in cols.items()}
    lo, hi = _ci(_boot(ms, cols, st, rnd))
    m_e = [m for m, x in zip(ms, cols["ge"]) if x]
    m_n = [m for m, x in zip(ms, cols["gn"]) if x]
    diff = st(tot)
    e1, e2 = S.episodes(m_e), S.episodes(m_n)
    return {"n_g": int(sum(g)), "n_ev": len(m_e), "n_non": len(m_n),
            "p_ev": tot["gec"] / tot["ge"] if tot["ge"] else None, "p_non": tot["gnc"] / tot["gn"] if tot["gn"] else None,
            "diff": diff, "lo": lo, "hi": hi, "epi_ev": e1, "epi_non": e2,
            "pass": S.passes(diff, lo, min(e1, e2), S.MIN_EPI2)}


def spx_levels(BX: dict | None = None) -> dict:
    """bubble.py（VER 4）S&P 500 每月的等級 → {月: 等級}。"""
    from . import bubble as BU
    BX = BX if BX is not None else BU.compute()
    rows = ((BX.get("spx") or {}).get("_C") or {}).get("rows") or []
    return {str(r["d"])[:7]: r.get("L") for r in rows if r.get("L") is not None}


def ind_research(BX: dict | None = None) -> dict:
    from . import bubble as BU
    T = BU.load_cv_table()
    Lcpi = BU.us_inputs(BU.load_us())["L"]
    caps = {"ff": caps_ff(), "tw": caps_tw()}
    groups, dds = {}, {}
    for grp in S.GROUPS:
        Lg = levels(grp, T, Lcpi)
        ser = breadth_series(Lg["L"], caps.get(grp) if grp in S.DEPTH_GROUPS else None)
        dds[grp] = fwd_dd(Lg["mme"])
        last = max(ser) if ser else None
        hot_now = sorted(c for c, d in Lg["L"].items() if last and (d.get(last) or 0) >= S.LEVEL_MIN)
        groups[grp] = {"series": ser, "now": {"m": last, "ib": ser[last][2] if last else None, "id": ser[last][3] if last else None,
                                              "n_hot": ser[last][0] if last else None, "n": ser[last][1] if last else None,
                                              "hot": hot_now},
                       "max_ib": max(((v[2], m) for m, v in ser.items() if v[2] is not None), default=None)}
    lv = spx_levels(BX)
    ff = groups["ff"]["series"]
    tests, describe = {}, {}
    for kind, idx, th in (("IB", 2, S.IB_TH), ("ID", 3, S.ID_TH)):
        ev = {m: (None if v[idx] is None else v[idx] >= th) for m, v in ff.items()}
        one = test_one(ev, dds["ff"], random.Random(S.SEED))
        two = test_two(ev, lv, dds["ff"], random.Random(S.SEED))
        tests[kind] = {"th": th, "one": one, "two": two, "verdict": S.verdict(one["pass"], two["pass"])}
        for dth in S.DESCRIBE_TH:
            evd = {m: (None if v[idx] is None else v[idx] >= dth) for m, v in ff.items()}
            describe[f"{kind}{int(round(dth * 100))}"] = {"one": test_one(evd, dds["ff"], random.Random(S.SEED)),
                                                          "two": test_two(evd, lv, dds["ff"], random.Random(S.SEED))}
    other = {}
    for grp in ("tw", "tg", "us"):
        ser, dd = groups[grp]["series"], dds[grp]
        ev = {m: (None if v[2] is None else v[2] >= S.IB_TH) for m, v in ser.items()}
        ms = sorted(m for m in ev if ev[m] is not None and dd.get(m) is not None)
        evm = [m for m in ms if ev[m]]
        hit = [m for m in evm if dd[m] >= S.DD]
        allc = [m for m in ms if dd[m] >= S.DD]
        other[grp] = {"n": len(ms), "n_ev": len(evm), "epi": S.episodes(evm),
                      "p_ev": len(hit) / len(evm) if evm else None, "p_all": len(allc) / len(ms) if ms else None,
                      "ev_now": S.episodes(sorted(m for m, v in ev.items() if v))}
    return {"groups": groups, "ff_tests": tests, "describe": describe, "other": other,
            "spx_lv_a": min(lv) if lv else None}


# ── 研究檔 ────────────────────────────────────────────────────────────────

def _r(x):
    if isinstance(x, dict):
        return {k: _r(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if x != x else float(f"{float(x):.6g}")
    if isinstance(x, np.integer):
        return int(x)
    return x


def research(F: dict, BX: dict | None = None) -> dict:
    return _r({"ver": S.VER, "spec_date": S.SPEC_DATE, "run": clock.now_tw().isoformat(timespec="seconds"),
               "stock": stock_research(F), "ind": ind_research(BX)})


def save(R: dict) -> None:
    RESEARCH.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
