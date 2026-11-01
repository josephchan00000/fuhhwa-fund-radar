"""參數鄰近檢查（nbrspec VER 1；docs/lab_signal_quality_plan.md 第 12 節，B 段）：每一組（訊號, 方向, 看多久）一次動一個參數，
看鄰近的參數是不是也過列出門檻 → data/lab/robust_research.json（scripts/run_robust.py）。

做法：鄰近的訊號一律用正式程式重算——暫時換掉規格常數（patched／windows），再呼叫 sigcat.signals、sigcat.buy_signals、
bubble.compute、heatpos.deriv；技術事件的參數是 heattech 函式的預設值（定義時就固定，換常數沒有用），另外照 heattech.all_events
的寫法把參數明寫傳進去（tech_events），原本的參數要和 all_events 一模一樣。
次數、命中率、平常用 sigcat.ev_stat／st_stat（和研究檔同一套），數字照研究檔四捨五入（sigcat._r）。
原本參數重算的訊號與每一組數字都要和研究檔一模一樣（selfcheck；不一樣就停，不出結果）。
"""
from __future__ import annotations

import bisect
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import nbrspec as N
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / N.OUT


# ── 換參數 ─────────────────────────────────────────────────────────────────

@contextmanager
def patched(*pairs):
    """暫時把 (模組, 名稱, 值) 換上去，離開時照原樣換回來。"""
    old = [(m, a, getattr(m, a)) for m, a, _ in pairs]
    try:
        for m, a, v in pairs:
            setattr(m, a, v)
        yield
    finally:
        for m, a, v in reversed(old):
            setattr(m, a, v)


@contextmanager
def windows(i: int):
    """百分位比較期間換成 nbrspec.WIN 的第 i 個（0＝短、1＝長）：景氣頁日、月資料（heatspec.PCT_WIN／PCT_MIN，美股同一個 dict，
    寬度與深度、法人也讀它）、10 年的項目（PCT_WIN_ITEM，台股與美股各一份）、大跌風險（crashspec.PCT_DAILY／PCT_MONTHLY）。"""
    from . import crashspec as CS
    from . import heatspec as HS
    from . import heatspec_us as U
    W = N.WIN
    old_w, old_m = dict(HS.PCT_WIN), dict(HS.PCT_MIN)
    HS.PCT_WIN.update(d=W["d"][i][0], m=W["m"][i][0])
    HS.PCT_MIN.update(d=W["d"][i][1], m=W["m"][i][1])

    def item(t: dict) -> dict:
        return {k: (W["q10"][i] if v == (40, 20) else W["d10"][i] if v == (2500, 1250) else v) for k, v in t.items()}
    try:
        with patched((HS, "PCT_WIN_ITEM", item(HS.PCT_WIN_ITEM)), (U, "PCT_WIN_ITEM", item(U.PCT_WIN_ITEM)),
                     (CS, "PCT_DAILY", W["cd"][i]), (CS, "PCT_MONTHLY", W["cm"][i])):
            yield
    finally:
        HS.PCT_WIN.clear()
        HS.PCT_WIN.update(old_w)
        HS.PCT_MIN.clear()
        HS.PCT_MIN.update(old_m)


def th_pairs(hot: float, cold: float) -> tuple:
    """過熱／過冷線：訊號總覽（sigspec）、進入事件（heatspec.EVT）、過熱結束與兩個面向（hotddspec）、連續過熱週數（hotchspec）一起換。"""
    from . import heatspec as HS
    from . import hotchspec as HCS
    from . import hotddspec as HDS
    pr = HS.EVT["hot"][1]
    return ((S, "HOT", hot), (S, "COLD", cold), (HS, "EVT", {"hot": (hot, pr), "cold": (cold, pr)}),
            (HDS, "HOT", hot), (HCS, "HOT", hot))


def prior_pairs(n: int) -> tuple:
    from . import heatspec as HS
    from . import hotddspec as HDS
    return ((HS, "EVT", {k: (v[0], n) for k, v in HS.EVT.items()}), (HDS, "EVT_PRIOR", n))


# ── 技術事件（heattech.all_events 的參數明寫版） ─────────────────────────────────

def tech_params(**kw) -> dict:
    from . import heatspec as HS
    p = {"ma20": 20, "ma60": 60, "ma240": 240, "tpr": HS.EV_PRIOR, "tcf": HS.EV_CONF, "pv": HS.PIVOT_THR,
         "dtol": HS.DT_TOL, "dgap": HS.DT_GAP, "hsr": HS.HS_RATIO}
    p.update(kw)
    return p


def tech_events(px: list, p: dict) -> dict[str, list[int]]:
    """同 heattech.all_events，參數照 p（tech_params）。"""
    from . import heat as H
    from . import heatspec as HS
    from . import heattech as TT
    M = {n: H.roll_mean(px, n) for n in {p["ma20"], p["ma60"], p["ma240"]}}
    pv = TT.pivots(px, p["pv"])
    se = lambda sd: TT.state_events(sd, p["tpr"], p["tcf"])        # noqa: E731
    ev: dict[str, list[int]] = {}
    for key, n in (("ma20", "ma20"), ("ma60", "ma60"), ("ma240", "ma240")):
        ev[f"{key}_dn"], ev[f"{key}_up"] = se([TT._side(a, m) for a, m in zip(px, M[p[n]])])
    ev["x_dead"], ev["x_gold"] = se([TT._side(a, b) for a, b in zip(M[p["ma20"]], M[p["ma60"]])])
    m60 = M[p["ma60"]]
    ev["s60_dn"], ev["s60_up"] = se([None] + [TT._side(m60[i], m60[i - 1]) for i in range(1, len(m60))])
    ev["pv_dn"], ev["pv_up"] = TT.break_events(px, pv)
    ev["dtop"], ev["dbot"] = TT.double_events(px, pv, p["dtol"], p["dgap"])
    ev["hstop"], ev["hsbot"] = TT.hs_events(px, pv, p["hsr"])
    return {k: ev[k] for k in HS.EVENTS}


def tech_sds(F: dict, p: dict) -> dict[str, dict]:
    """這個市場的技術事件（同 sigcat.signals 的技術事件段，只有出現日）。"""
    from . import sigcat as G
    px = [None if G._nan(v) else float(v) for v in F["px"]]
    ev = tech_events(px, p)
    samp = np.arange(S.EV_START, len(F["cal"]))
    return {f"{F['mk']}:tech:{k}": {"kind": "event", "samp": samp, "days": [t for t in ds if t >= S.EV_START]}
            for k, ds in ev.items()}


# ── 邊際變化（heatpos.deriv；規格常數換掉重算） ───────────────────────────────────

def deriv_spec(mk: str) -> dict:
    """這個市場的邊際變化規格（美股要在 heatspec.use(該指數) 裡讀才是那個指數的；這裡直接讀 spec_for）。"""
    from . import heatspec as HS
    from . import heatspec_us as U
    return dict(HS.DERIV) if mk == "tw" else U.spec_for(mk)["DERIV"]


def deriv_sds(F: dict, B: dict, k: str, spec_k: dict) -> dict[str, dict]:
    """一個邊際變化項目、換上 spec_k 之後的四個狀態訊號（同 sigcat.frame 的 DV＋signals 的邊際變化段）。"""
    from . import crash as CR
    from . import heatpos as P
    from . import heatspec as HS
    from . import heatspec_us as U
    mk, cal = F["mk"], F["cal"]

    def run():
        with patched((HS, "DERIV", {**HS.DERIV, k: spec_k})):
            st = P.deriv(B, k)["state"]
        x = CR.align(cal, B["cal"], [None if s in (None, 0) else float(s) for s in st])
        flat = CR.align(cal, B["cal"], [None if s is None else float(s) for s in st])
        samp = np.nonzero(~np.isnan(flat))[0]
        return {f"{mk}:deriv:{k}:{s}": {"kind": "state", "samp": samp, "state": x[samp] == s} for s in S.DERIV_STATES}
    if mk == "tw":
        return run()
    with HS.use(U.spec_for(mk)):
        return run()


# ── 泡沫（bubble.compute；規格常數換掉重算） ───────────────────────────────────────

def bub_sds(F: dict, rows: list) -> dict[str, dict]:
    """同 sigcat.signals 的泡沫段：每月最後一個交易日一個樣本、只用已經過完的月份。"""
    from . import crash as CR
    cal = F["cal"]
    me = CR.month_ends(cal)
    done = CR.complete_months(cal)
    rows = [r for r in rows if str(r.get("d"))[:7] in done and str(r.get("d"))[:7] in me]
    out = {}
    for k in S.BUB_SIGNALS:
        val = []
        for r in rows:
            if k in ("L2", "L3"):
                L = r.get("L")
                val.append((me[str(r["d"])[:7]], None if L is None else L >= int(k[1])))
            else:
                f = r.get(k)
                val.append((me[str(r["d"])[:7]], None if f is None else bool(f)))
        val = [(i, f) for i, f in val if f is not None]
        if val:
            out[f"{F['mk']}:bub:{k}"] = {"kind": "state", "monthly": True, "samp": np.array([i for i, _ in val], dtype=np.int64),
                                         "state": np.array([f for _, f in val], dtype=bool)}
    return out


def bub_rows(BX: dict, mk: str) -> list:
    return ((BX or {}).get(mk) or {}).get("_C", {}).get("rows") or []


# ── 大跌後買點（bottom；規格常數換掉重算） ─────────────────────────────────────────

def buy_inputs(mk: str, base: dict) -> dict | None:
    """這個市場的大跌後買點輸入（同 sigcat.frames；落底訊號裡 C2、C6 的天數在這一步算，要換參數就重建）。"""
    from . import bottom as BO
    from . import bottomspec as BOS
    from . import crash as CR
    from . import heatdata as HD
    from . import heatspec as HS
    from . import heatspec_us as U
    BX = base["BX"]
    if mk == "tw":
        IT = CR.tw_inputs(B=base["BT"], BX=BX)
        return BO.inputs_tw(base["BT"], IT, BX)
    with HS.use(U.spec_for(mk)):
        I0 = CR.us_inputs(mk, Bu=base["BA"][mk], BX=BX)
        vol = HD.load(f"us_vol_{mk}") if "C7" in BOS.SIG_MK[mk] else None
        return BO.inputs_us(mk, base["BA"][mk], I0, vol, BX)


def buy_sds(F: dict, IB: dict | None = None) -> tuple[dict | None, dict[str, dict]]:
    from . import sigcat as G
    I, sds = G.buy_signals(F if IB is None else {**F, "IB": IB})
    return I, {sd["id"]: {"kind": "event", "samp": sd["samp"], "days": sd["days"]} for sd in sds}


def buy_pairs(dim: str, i: int) -> tuple:
    from . import bottomspec as BOS
    out = []
    for k, nb in N.BUY[dim].items():
        v = nb[i]
        if k == "E5_TH":
            v = {m: x * nb[i] for m, x in BOS.E5_TH.items()}
        out.append((BOS, k, v))
    return tuple(out)


# ── 次數、命中率、平常 ─────────────────────────────────────────────────────────

def _r3(R: dict, d: str) -> list:
    from . import sigcat as G
    st = R[d]
    return [int(st["n"]), G._r(st["hit"]), G._r(st["base"])]


def stats(px, cal, r0d: str, sd: dict, H: int, th: float, cache: dict) -> dict:
    """一個訊號在看多久 H、警示門檻 th 的次數、命中率、平常（sigcat.ev_stat／st_stat）→ {"up": [n, hit, base], "warn": [...]}。"""
    from . import sigcat as G
    key = (id(px), H, th)
    if key not in cache:
        cache[key] = G.outcomes(px, H, th)
    Yu, Yw, _ = cache[key]
    r0 = bisect.bisect_left(cal, r0d)
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if sd["kind"] == "event":
        R = G.ev_stat(sd["days"], Yu, Yw, samp, H, r0)
    else:
        gap = 1 if sd.get("monthly") else S.EP_GAP
        R = G.st_stat(np.asarray(sd["state"], dtype=bool), samp, Yu, Yw, gap, r0, brk=sd.get("brk"))
    return {d: _r3(R, d) for d in ("up", "warn")}


def halves(px, cal, r0d: str, sd: dict, H: int, th: float, cache: dict) -> list:
    """前後兩半（nbrspec 第 4 點）：樣本日照第 ⌊L ÷ 2⌋ 個分開，各自的 {"up": [n, hit, base], "warn": [...]}。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if len(samp) < 2:
        return []
    cut = samp[len(samp) // 2]
    out = []
    for m in (samp < cut, samp >= cut):
        h = {"kind": sd["kind"], "samp": samp[m], "monthly": sd.get("monthly")}
        if sd["kind"] == "event":
            h["days"] = sd["days"]
        else:
            h["state"] = np.asarray(sd["state"], dtype=bool)[m]
            if sd.get("brk") is not None:
                h["brk"] = np.asarray(sd["brk"], dtype=bool)[m]
        out.append(stats(px, cal, r0d, h, H, th, cache))
    return out


def same(a: dict | None, b: dict | None) -> bool:
    """兩個訊號定義一模一樣（出現日；狀態型＝樣本日與狀態）。"""
    if a is None or b is None:
        return a is b
    if a["kind"] != b["kind"]:
        return False
    if a["kind"] == "event":
        return list(map(int, a["days"])) == list(map(int, b["days"]))
    return (np.array_equal(np.asarray(a["samp"]), np.asarray(b["samp"]))
            and np.array_equal(np.asarray(a["state"], dtype=bool), np.asarray(b["state"], dtype=bool)))


# ── 範圍：原本參數過得了列出門檻的組 ─────────────────────────────────────────────────

def passes(st) -> bool:
    if not st:
        return False
    n, hit, base = (st["n"], st.get("hit"), st.get("base")) if isinstance(st, dict) else st
    return (n or 0) >= S.N_MIN and hit is not None and base is not None and hit - base >= S.THERMO_EDGE


def targets(rows: list[dict]) -> list[dict]:
    """研究檔的列 → 要檢查的組 [{"id", "mk", "cat", "d", "H", "th", "k"（自己的＝None、跨期間＝溫度計）, "st": [n, hit, base]}]。
    警示門檻 th 用 sigcat.warn_th 的原值（研究檔的 "th" 四捨五入過，拿來重算會差一點）。"""
    from . import sigcat as G
    out = []
    for r in rows:
        if r.get("cat") not in N.CATS or r.get("mk") not in S.MARKETS:
            continue
        mk = r["mk"]
        for d in (("buy",) if r["cat"] == "buy" else ("up", "warn")):
            st = r.get(d)
            if passes(st):
                out.append({"id": r["id"], "mk": mk, "cat": r["cat"], "d": d, "H": r["H"], "th": G.warn_th(mk, r["H"]), "k": None,
                            "st": [st["n"], st["hit"], st["base"]]})
        for k, X in (r.get("xh") or {}).items():
            for d in ("up", "warn"):
                if passes(X.get(d)):
                    st = X[d]
                    out.append({"id": r["id"], "mk": mk, "cat": r["cat"], "d": d, "H": X["H"], "th": G.warn_th(mk, X["H"]), "k": k,
                                "st": [st["n"], st["hit"], st["base"]]})
    return out


def dims_of(r: dict, mk: str) -> tuple[str, ...]:
    """這一列的參數維度（看多久 "hz" 另外加）。"""
    cat, sig, var = r["cat"], r.get("sig"), r.get("var")
    if cat in ("heat", "crash", "bd"):
        return N.VAR_DIMS[sig]
    if cat == "inst":
        if sig in N.VAR_DIMS:
            return N.VAR_DIMS[sig] + N.INST_POS_EXTRA
        if sig in ("day_sell", "day_buy"):
            return N.INST_DAY_DIMS
        return N.INST_RUN_DIMS
    if cat == "multi":
        return N.MULTI_DIMS[sig]
    if cat == "scen":
        return N.SCEN_DIMS
    if cat == "tech":
        return N.TECH_DIMS[var]
    if cat == "deriv":
        sp = deriv_spec(mk).get(var) or {}
        return tuple(f for f in N.DERIV_KEYS if f in sp)
    if cat == "bub":
        return N.BUB_DIMS[var]
    if cat == "buy":
        ev, k = r["id"].split(":")[2], r["id"].split(":")[3]
        return N.BUY_EVENT_DIMS[ev] + N.BUY_RULE_DIMS[k]
    return ()


# ── 全部 ─────────────────────────────────────────────────────────────────────

def base_data() -> dict:
    """原本參數的資料（同 sigcat.frames）：{"BX", "BT", "BA", "F"}。"""
    from . import bubble as BU
    from . import heatcalc as HC
    from . import heatcalc_us as HU
    from . import sigcat as G
    BX = BU.compute()
    BT = HC.build()
    BA = HU.build_all()
    return {"BX": BX, "BT": BT, "BA": BA, "F": G.frames(BT, BA, BX)}


def market_sds(F: dict) -> dict[str, dict]:
    from . import sigcat as G
    return {sd["id"]: sd for sd in G.signals(F)}


def variants(base: dict, log=print) -> dict:
    """每一個維度、每一個鄰近值 → {訊號 id: 定義}（只放這個維度會動到的類別）；鍵 (維度, 標籤)。
    市場層級訊號用 market_sds（正式程式）；技術事件、邊際變化、泡沫、大跌後買點各自重算。"""
    from . import bubble as BU
    from . import sigcat as G
    F = base["F"]
    V: dict = {}

    def add(key, sds):
        V.setdefault(key, {}).update(sds)

    def each_market(pairs, key, cats):
        with patched(*pairs):
            for mk in F:
                add(key, {i: sd for i, sd in market_sds(F[mk]).items() if sd["cat"] in cats})
    zcats = ("heat", "crash", "bd", "inst", "multi")
    for j, (hot, cold) in enumerate(N.TH):
        each_market(th_pairs(hot, cold), ("th", f"{hot}／{cold}"), zcats)
    for n in N.PRIOR:
        each_market(prior_pairs(n), ("pr", str(n)), zcats)
    for n in N.EXIT:
        each_market(((S, "EXIT_MIN", n),), ("ex", str(n)), zcats)
    for n in N.WEEKS:
        each_market(((S, "HOT_WEEKS", n),), ("wk", str(n)), zcats)
    for hi, lo in N.SCEN:
        each_market(((S, "SCEN_HI", hi), (S, "SCEN_LO", lo)), ("hl", f"{hi}／{lo}"), ("scen",))
    for hi, lo in N.INST_TAIL:
        each_market(((S, "INST_DAY", (hi, lo)),), ("tail", f"{100 - hi}%"), ("inst",))
    log("[robust] 門檻類的鄰近 ok")
    # 法人連續天數：直接用單日金額（sigcat.run_days）
    for mk in F:
        for v in F[mk].get("ivars") or []:
            if v["w"] != 1:
                continue
            amt = np.asarray(v["amt"], dtype=float)
            sa = np.nonzero(~np.isnan(amt))[0]
            for sign, tag in ((-1, "sell"), (1, "buy")):
                for n, nbs in N.INST_RUN.items():
                    for m in nbs:
                        add(("run", str(m)), {f"{mk}:inst:{v['key']}:{tag}_run{n}":
                                              {"kind": "event", "samp": sa, "days": G.run_days(amt, sign, m)}})
    # 法人位階的合計天數（只有台股有法人）
    if "tw" in F:
        ws = tuple(sorted({w for nb in N.INST_WIN.values() for w in nb}))
        H2 = {**S.INST_H, **{w: S.INST_H[k] for k, nb in N.INST_WIN.items() for w in nb}}
        with patched((S, "INST_WIN", (1,) + ws), (S, "INST_POS_WIN", ws), (S, "INST_H", H2)):
            F2 = {**F["tw"], "ivars": G.inst_vars(F["tw"]["cal"], base["BT"])}
            sds = {sd["id"]: sd for sd in G.inst_signals(F2)}
        for k, nb in N.INST_WIN.items():
            for i, w in enumerate(nb):
                tag = ("短", "長")[i]
                for sid, sd in sds.items():
                    p = sid.split(":")
                    if p[2].endswith(str(w)) and p[2][:-len(str(w))] in S.INST_WHO:
                        add(("iw", tag), {f"tw:inst:{p[2][:-len(str(w))]}{k}:{p[3]}": sd})
    log("[robust] 法人 ok")
    # 百分位比較期間：全部 0～100 重算（泡沫照原本）
    for i in range(2):
        with windows(i):
            from . import heatcalc as HC
            from . import heatcalc_us as HU
            Fw = G.frames(HC.build(), HU.build_all(), base["BX"])
        for mk in Fw:
            add(("win", N.WIN_TAGS[i]), {sid: sd for sid, sd in market_sds(Fw[mk]).items()
                                         if sd["cat"] in zcats + ("scen",)})
        log(f"[robust] 和過去多久比（{N.WIN_TAGS[i]}）ok")
    # 技術事件
    for dim, nbs in (("ma20", N.MA[20]), ("ma60", N.MA[60]), ("ma240", N.MA[240]), ("tpr", N.EV_PRIOR), ("tcf", N.EV_CONF),
                     ("pv", N.PIVOT), ("dtol", N.DT_TOL), ("dgap", N.DT_GAP), ("hsr", N.HS_RATIO)):
        for v in nbs:
            p = tech_params(**{dim: v})
            for mk in F:
                add((dim, str(v)), tech_sds(F[mk], p))
    log("[robust] 技術事件 ok")
    # 邊際變化
    for mk in F:
        B = base["BT"] if mk == "tw" else base["BA"][mk]
        for k, sp in deriv_spec(mk).items():
            for f in N.DERIV_KEYS:
                if f not in sp:
                    continue
                for i, v in enumerate(N.deriv_nb(sp[f])):
                    add((f, ("短", "長")[i]), deriv_sds(F[mk], B, k, {**sp, f: v}))
    log("[robust] 邊際變化 ok")
    # 泡沫
    from . import bubspec as BS
    for dim, ps in N.BUB.items():
        for i in range(2):
            with patched(*((BS, k, nb[i]) for k, nb in ps.items())):
                BX = BU.compute()
            for mk in F:
                add((dim, ("小", "大")[i]), bub_sds(F[mk], bub_rows(BX, mk)))
    log("[robust] 泡沫 ok")
    # 大跌後買點
    for dim in N.BUY:
        for i in range(2):
            with patched(*buy_pairs(dim, i)):
                for mk in F:
                    IB = buy_inputs(mk, base) if dim in ("c2d", "c6") else None
                    add((dim, ("小", "大")[i]), buy_sds(F[mk], IB)[1])
    log("[robust] 大跌後買點 ok")
    return V


def selfcheck(base: dict) -> list[str]:
    """原本參數走這裡的重算路徑，要和正式程式一模一樣（技術事件、邊際變化、泡沫、大跌後買點、法人位階）。→ 不一樣的訊號 id。"""
    from . import heattech as TT
    from . import sigcat as G
    F = base["F"]
    bad = []
    for mk in F:
        ref = market_sds(F[mk])
        got = tech_sds(F[mk], tech_params())
        px = [None if G._nan(v) else float(v) for v in F[mk]["px"]]
        if tech_events(px, tech_params()) != TT.all_events(px):
            bad.append(f"{mk}:tech（all_events）")
        B = base["BT"] if mk == "tw" else base["BA"][mk]
        for k, sp in deriv_spec(mk).items():
            got.update(deriv_sds(F[mk], B, k, sp))
        got.update(bub_sds(F[mk], bub_rows(base["BX"], mk)))
        for sid, sd in got.items():
            if not same(sd, ref.get(sid)):
                bad.append(sid)
        _, b0 = buy_sds(F[mk])
        _, b1 = buy_sds(F[mk], buy_inputs(mk, base))
        bad += [sid for sid in b0 if not same(b0[sid], b1.get(sid))]
    if "tw" in F:
        with patched((S, "INST_WIN", S.INST_WIN), (S, "INST_POS_WIN", S.INST_POS_WIN)):
            F2 = {**F["tw"], "ivars": G.inst_vars(F["tw"]["cal"], base["BT"])}
            got = {sd["id"]: sd for sd in G.inst_signals(F2)}
        ref = market_sds(F["tw"])
        bad += [sid for sid, sd in got.items() if not same(sd, ref.get(sid))]
    return bad


def run(base: dict | None = None, rows: list | None = None, log=print) -> dict:
    """全部：範圍 → 原本的訊號與數字核對 → 鄰近 → 判定 → 研究檔內容。"""
    from . import sigcat as G
    base = base if base is not None else base_data()
    F = base["F"]
    rows = rows if rows is not None else (G.load_research() or {}).get("rows") or []
    byid = {r["id"]: r for r in rows}
    T = targets(rows)
    log(f"[robust] 要檢查的組：{len(T)}")
    bad = selfcheck(base)
    if bad:
        raise RuntimeError(f"原本參數重算和正式程式不一樣：{bad[:10]}（共 {len(bad)} 個）")
    sds = {}
    buyI = {}
    for mk in F:
        sds.update(market_sds(F[mk]))
        I, b = buy_sds(F[mk])
        sds.update(b)
        buyI[mk] = I
    cache: dict = {}

    def ctx(t):
        """這一組用哪一條收盤、日曆、近 10 年起點。"""
        mk = t["mk"]
        if t["cat"] == "buy":
            I = buyI[mk]
            return I["px"], list(I["cal"]), F[mk]["r0"]
        return F[mk]["px"], F[mk]["cal"], F[mk]["r0"]

    def dkey(t):
        return "up" if t["d"] == "buy" else t["d"]
    bad = []
    for t in T:                                          # 原本的數字要和研究檔一模一樣
        px, cal, r0 = ctx(t)
        got = stats(px, cal, r0, sds[t["id"]], t["H"], t["th"], cache)[dkey(t)]
        if got != t["st"]:
            bad.append((t["id"], t["d"], t["k"], got, t["st"]))
    if bad:
        raise RuntimeError(f"原本參數的次數、命中率、平常和研究檔不一樣：{bad[:5]}（共 {len(bad)} 組）")
    log("[robust] 原本的訊號與數字和研究檔一模一樣")
    V = variants(base, log)
    labels: dict = {}
    for dim, lab in V:
        labels.setdefault(dim, []).append(lab)
    out = []
    for t in T:
        r = byid[t["id"]]
        px, cal, r0 = ctx(t)
        sd0 = sds[t["id"]]
        dims: dict = {}
        res: dict = {}
        for h in N.HZ[t["H"]]:
            res.setdefault("hz", []).append([str(h), *stats(px, cal, r0, sd0, h, t["th"], cache)[dkey(t)]])
        dims["hz"] = N.dim_ok([tuple(x[1:]) for x in res["hz"]], S.N_MIN, S.THERMO_EDGE)
        for dim in dims_of(r, t["mk"]):
            vs, sm = [], True
            labs = ([str(m) for m in N.INST_RUN[int(r["sig"].split("run")[1])]] if dim == "run" else labels.get(dim, []))
            for lab in labs:
                sd = V[(dim, lab)].get(t["id"])
                sm = sm and same(sd, sd0)
                if sd is None:
                    vs.append([lab, 0, None, None])
                else:
                    vs.append([lab, *stats(px, cal, r0, sd, t["H"], t["th"], cache)[dkey(t)]])
            res[dim] = vs
            dims[dim] = N.dim_ok([tuple(x[1:]) for x in vs], S.N_MIN, S.THERMO_EDGE, same=sm and bool(vs))
        hv = halves(px, cal, r0, sd0, t["H"], t["th"], cache)
        hh = [x[dkey(t)] for x in hv]
        cons = (len(hh) == 2 and all(n >= 1 and h is not None and b is not None and h > b for n, h, b in hh))
        out.append({"id": t["id"], "mk": t["mk"], "cat": t["cat"], "d": t["d"], "H": t["H"], "k": t["k"], "st": t["st"],
                    "ok": N.overall(dims), "dims": dims, "nb": res, "halves": hh, "cons": bool(cons)})
    return {"ver": N.VER, "spec_date": N.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "rows": out, "summary": summary(out)}


def summary(out: list[dict]) -> dict:
    """每一類：穩定／只在這個參數成立／看不出來 幾組；每個參數維度不穩定幾次。"""
    sm: dict = {}
    for x in out:
        c = sm.setdefault(x["cat"], {"ok": 0, "bad": 0, "na": 0, "dims": {}})
        c["ok" if x["ok"] else "na" if x["ok"] is None else "bad"] += 1
        for dim, v in x["dims"].items():
            if v is False:
                c["dims"][dim] = c["dims"].get(dim, 0) + 1
    return sm


def save(R: dict, path: Path | None = None) -> None:
    (path or OUT).write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def load(path: Path | None = None) -> dict | None:
    try:
        R = json.loads((path or OUT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= N.VER else None


# ── 今天的清單會少哪些（第 D 段接上之前先看影響；只呈現） ───────────────────────────

def filtered_rows(rows: list[dict], out: list[dict]) -> list[dict]:
    """研究檔的列，把「只在這個參數成立」的組拿掉（自己的看多久：那個方向當成沒過；跨期間：那支溫度計那個方向拿掉）。"""
    bad: dict = {}
    for x in out:
        if x["ok"] is False:
            bad.setdefault(x["id"], set()).add((x["d"], x["k"]))
    res = []
    for r in rows:
        b = bad.get(r["id"])
        if not b:
            res.append(r)
            continue
        r = dict(r)
        for d, k in b:
            if k is None:
                r[d] = {**(r.get(d) or {}), "hit": None}
            elif r.get("xh") and k in r["xh"]:
                r["xh"] = {**r["xh"], k: {**r["xh"][k], d: None}}
        res.append(r)
    return res


def impact(base: dict, rows: list[dict], out: list[dict]) -> dict:
    """每個市場今天的重點（sigcat.board）：照現在的規則 vs 拿掉只在這個參數成立的 → 列出來的類數、溫度計、
    少掉的訊號（gone：同類合併的成員也算，哪裡都不見了才算少掉；lead：本來領頭、現在變成別人那一類的成員）。"""
    from . import sigcat as G
    F = base["F"]
    rows2 = filtered_rows(rows, out)
    res = {}
    for mk in F:
        acts: dict = {}
        xon: dict = {}
        on = G.now_market(F[mk], acts, xon)
        b0 = G.board(rows, on, mk, acts, xon, RB=None)          # 兩邊都照 VER 26 的清單（不看參數鄰近的研究檔，比的就是它）
        b1 = G.board(rows2, on, mk, acts, xon, RB=None)

        def keys(b, members=True):
            out = {}
            for side in ("up", "warn"):
                for f in b[side]:
                    for m in [f] + (list(f.get("fam") or []) if members else []):
                        out[(m["id"], m["d"], m.get("xk") or m["hz"])] = m["name"]
            return out
        a0, a1 = keys(b0), keys(b1)
        l0, l1 = keys(b0, False), keys(b1, False)
        res[mk] = {"n0": {s: len(b0[s]) for s in ("up", "warn")}, "n1": {s: len(b1[s]) for s in ("up", "warn")},
                   "thermo0": [[t["k"], t["n"]["up"], t["n"]["warn"], t["lean"]] for t in b0["thermo"]],
                   "thermo1": [[t["k"], t["n"]["up"], t["n"]["warn"], t["lean"]] for t in b1["thermo"]],
                   "gone": sorted(list(k) + [a0[k]] for k in set(a0) - set(a1)),
                   "lead": sorted(list(k) + [l0[k]] for k in set(l0) - set(l1) if k in a1),
                   "new": sorted(list(k) for k in set(a1) - set(a0))}
    return res
