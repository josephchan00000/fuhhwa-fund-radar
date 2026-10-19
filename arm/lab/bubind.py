"""產業泡沫的計算（規格 bubindspec VER 2；docs/lab_risk_plan.md 第 12 節、docs/lab_crash_plan.md 第 21.2 節）。

三組產業，每個產業每月一個樣本（月底），算條件（P1 價格爆發、P2 兩年翻倍比大盤多漲而且在高點、P3 偏離長期趨勢、
E 價格漲得比營收快、G 未來獲利跟不上、F 燃料）與 0～4 級（bubspec.level4，V 一律不判定）：
  · tw：台股產業指數用 bt3d.Panel 自己組（前月底市值 ≥ 40 億、前月底市值加權、月內買進持有、含息）；
  · us：SPDR 類股 ETF 收盤（大盤 SPY）；
  · ff：Ken French 49 產業不含股利的月報酬累乘（大盤＝依前月市值加權）。
PSY 臨界值表、方向條件、趨勢偏離與市場層級共用 bubble 的函式；只描述位置，不是買賣訊號。
"""
from __future__ import annotations

import bisect
import math
import random

from . import bubble as BU
from . import bubindspec as BI
from . import heatdata as HD

REL = BU.REL                                           # 月資料下個月 1 日起才用（同市場層級）
_ym_add, _mdiff = BU._ym_add, BU._mdiff


# ── 共用：月序列小工具 ─────────────────────────────────────────────────────

def months_between(a: str, b: str) -> list[str]:
    out = [a]
    while out[-1] < b:
        out.append(_ym_add(out[-1], 1))
    return out


def chain(rets: dict, months: list[str]) -> dict:
    """{YYYY-MM: 月報酬（%）或 None} → {YYYY-MM: 指數}；缺一個月就斷開，下一個有值的月份從 1 重新開始（另一段）。
    每一段的第一個月記成「那個月月底＝1 × (1 + 報酬)」，前一個月月底當基準 1（只用來接段，不輸出）。"""
    out: dict = {}
    lvl = None
    for m in months:
        r = rets.get(m)
        if r is None:
            lvl = None
            continue
        lvl = (1.0 if lvl is None else lvl) * (1.0 + r / 100.0)
        out[m] = lvl
    return out


def drawdown(vals: list, a: int, b: int) -> float | None:
    """vals[a..b]（含兩端）內，收盤高點到之後低點的最大跌幅（正數，0.25＝跌 25%）；中間缺值或超出範圍＝None。"""
    if b >= len(vals) or a < 0:
        return None
    seg = vals[a:b + 1]
    if any(v is None or v <= 0 for v in seg):
        return None
    hi, dd = seg[0], 0.0
    for v in seg:
        hi = max(hi, v)
        dd = max(dd, 1.0 - v / hi)
    return dd


def pct_span(ser: dict, min_months: int) -> dict:
    return BU.expanding_pct_span(ser, min_months)


# ── 台股產業指數（bt3d.Panel＋官方分片接續；CI 抓資料時算好，按月存 data/lab/indtw） ─────────────

IND_KIND = "indtw"
TG_KIND = "indtg"
MKT = "__mkt__"


def _shard_values(since: str) -> dict:
    """官方分片的成交金額 {代號: [(日期, 元)]}（since 起；上市 q_tw[5]、上櫃 q_tp[5]）。Panel 接續分片的日子用。"""
    from . import store
    out: dict = {}
    for d, doc in store.load("mkt", since=since):
        for part in ("q_tw", "q_tp"):
            for c, q in (doc.get(part) or {}).items():
                if q and len(q) > 5 and q[5]:
                    out.setdefault(c, []).append((d, q[5]))
    return out


def _liq_at(P, c: str, i: int, sv: dict) -> float | None:
    """第 i 天的 20 日平均成交值：Panel 有就用 Panel（bt3d.liq），Panel 接續分片的日子用分片的成交金額（至少 10 天）。"""
    L = P.liq.get(c) if hasattr(P.liq, "get") else None
    if L is not None and i < len(L):
        return L[i]
    xs = sv.get(c) or []
    d = P.cal[i]
    j = bisect.bisect_right([x[0] for x in xs], d)
    w = [v for _, v in xs[max(0, j - 20):j]]
    return sum(w) / len(w) if len(w) >= 10 else None


def tw_ind_map() -> dict[str, str]:
    """台股產業別（bubindspec 第 1b 節）：現在的產業表＋已下市公司在官方歷史分類行情裡最後一次出現的產業別（現在的優先）。"""
    from arm import stockmeta
    from . import indhist
    cur = stockmeta.industry_map()
    return {**indhist.delisted_map(cur), **cur}


def tg_members(doc: dict | None = None, cur: dict | None = None) -> dict:
    """細分族群的成員（bubindspec 第 1c 節）→ {"groups": {族群: 代號集合}, "n": {族群: 家數}, "d": 名單日期,
    "skip": {族群: 原因}}。節點或分頁找不到＝整個族群不算（不讓族群悄悄變小）；成員 < TG_MIN_MEMBERS＝不算。"""
    import re
    from arm import stockmeta
    from . import icchain
    doc = doc if doc is not None else icchain.load()
    chains = (doc or {}).get("chains") or {}
    out: dict = {"groups": {}, "n": {}, "d": (doc or {}).get("d"), "skip": {}}
    if not chains:
        return out
    cur = cur if cur is not None else stockmeta.industry_map()
    for key, _, src in BI.TG_GROUPS:
        cs: set = set()
        why = None
        for ic, title, tab in src:
            nodes = [nd for nd in ((chains.get(ic) or {}).get("nodes") or []) if title == "*" or nd[1] == title]
            if not nodes:
                why = f"找不到 {ic}「{title}」"
                break
            for nd in nodes:
                if tab is None:
                    cs |= icchain.node_codes(nd)
                    continue
                t = icchain.tabs(nd)
                if not t or tab not in t:
                    why = f"找不到 {ic}「{title}」的分頁「{tab}」"
                    break
                cs |= t[tab]
            if why:
                break
        if why:
            out["skip"][key] = why
            continue
        cs = {c for c in cs if c in cur and re.match(r"^[1-9]\d{3}$", c)}
        if len(cs) < BI.TG_MIN_MEMBERS:
            out["skip"][key] = f"現在上市櫃只有 {len(cs)} 家"
            continue
        out["groups"][key] = cs
        out["n"][key] = len(cs)
    return out


def tw_build(P=None, ind_map: dict | None = None, groups: dict | None = None) -> dict:
    """→ {"cal", "me"（每月最後一個交易日的位置）, "grp": {名稱: {"px": 每天指數, "n": {月: 成分數}, "turn": {月: 換手率}}}}；
    MKT＝大盤。每月以前月底為基準重算權重；成分 < TW_MIN_N 那個月整月 None，之後重新起算（第 12.1 節）。
    groups＝{族群: 代號集合}（細分族群，第 1c 節；一家公司可以在好幾個族群）→ 改算這些族群，不算產業別。"""
    from . import bt3d
    P = P or bt3d.Panel(start=BI.TW_START)
    cal, T = P.cal, P.T
    me = BU.month_end_idx(cal)
    n0 = min((len(v) for v in P.liq.values()), default=T)
    sv = _shard_values(cal[max(0, n0 - 40)]) if n0 < T else {}
    gof: dict[str, list] = {}
    if groups is not None:
        names = sorted(groups)
        for g in names:
            for c in groups[g]:
                gof.setdefault(c, []).append(g)
    else:
        im = ind_map if ind_map is not None else tw_ind_map()
        names = sorted({v for v in im.values() if v and v not in BI.TW_SKIP})
        ok = set(names)
        gof = {c: [g] for c, g in im.items() if g in ok}
    G = {g: {"px": [None] * T, "n": {}, "turn": {}} for g in names + [MKT]}
    lvl = {g: None for g in G}
    for k in range(1, len(me)):
        b, e = me[k - 1], me[k]
        ym = cal[e][:7]
        mem: dict[str, list] = {g: [] for g in G}
        for c in P.codes:
            cap = P.cap[c][b]
            p0 = P.s[c]["c"][b]
            if not cap or cap < BI.TW_CAP_MIN or not p0:
                continue
            mem[MKT].append(c)
            for g in gof.get(c, ()):
                mem[g].append(c)
        for g, cs in mem.items():
            if len(cs) < BI.TW_MIN_N:
                lvl[g] = None
                continue
            W = sum(P.cap[c][b] for c in cs)
            base = lvl[g] if lvl[g] is not None else 1.0
            last = {c: P.s[c]["c"][b] for c in cs}
            p0 = dict(last)
            px = G[g]["px"]
            for i in range(b + 1, e + 1):
                acc = 0.0
                for c in cs:
                    x = P.s[c]["c"][i]
                    if x:
                        last[c] = x
                    acc += P.cap[c][b] * last[c] / p0[c]
                px[i] = base * acc / W
            lvl[g] = px[e]
            G[g]["n"][ym] = len(cs)
            liq = capm = 0.0
            for c in cs:
                q, cp = _liq_at(P, c, e, sv), P.cap[c][e]
                if q and cp:
                    liq += q
                    capm += cp
            if capm > 0 and liq > 0:
                G[g]["turn"][ym] = liq / capm
    return {"cal": cal, "me": me, "grp": G}


def indtw_save(P, kind: str = IND_KIND, groups: dict | None = None, extra: dict | None = None) -> int:
    """tw_build 的結果按月存（store kind indtw，鍵 YYYY-MM）：{"cal": [那個月的交易日], "px": {產業: [每天]}, "n", "turn"}。
    store.write 內容沒變不改寫，所以每天只會改寫當月那一檔。回傳改寫的月數。
    細分族群：kind＝TG_KIND、groups＝tg_members()，extra＝{"src": 名單日期}（每一檔都帶，名單換了整段重寫）。"""
    from . import store
    TB = tw_build(P, groups=groups)
    cal, G = TB["cal"], TB["grp"]
    by: dict[str, list[int]] = {}
    for i, d in enumerate(cal):
        by.setdefault(d[:7], []).append(i)
    n = 0
    for ym, ix in sorted(by.items()):
        px = {g: [None if G[g]["px"][i] is None else round(G[g]["px"][i], 6) for i in ix] for g in sorted(G)}
        px = {g: v for g, v in px.items() if any(x is not None for x in v)}
        if not px:
            continue
        doc = {"cal": [cal[i] for i in ix], "px": px,
               "n": {g: G[g]["n"][ym] for g in sorted(G) if ym in G[g]["n"]},
               "turn": {g: round(G[g]["turn"][ym], 8) for g in sorted(G) if ym in G[g]["turn"]}, **(extra or {})}
        if store.write(kind, ym, doc):
            n += 1
    return n


def indtw_last(kind: str = IND_KIND) -> str:
    """indtw 最後一天（沒有檔＝空字串）。"""
    from . import store
    ks = store.dates(kind)
    if not ks:
        return ""
    return ((store.read(kind, ks[-1]) or {}).get("cal") or [""])[-1]


def _tg_src() -> str:
    """indtg 用的名單日期（最後一檔的 src；沒有＝空字串）。"""
    from . import store
    ks = store.dates(TG_KIND)
    return str((store.read(TG_KIND, ks[-1]) or {}).get("src") or "") if ks else ""


def indtw_update(force: bool = False) -> int:
    """CI 每天（scripts/fetch_heat.py）：官方分片有比 indtw 更新的交易日才重算（Panel＋分片接續，約 30 秒）。
    細分族群（indtg）一起算；族群名單（icchain.json）換了也重算。"""
    from . import bt3d, icchain, store
    T = tg_members()
    src = (icchain.load() or {}).get("d") or ""
    tg_need = bool(T["groups"]) and (force or _tg_src() != src)
    last = indtw_last()
    tg_last = indtw_last(TG_KIND)
    newest = max(store.dates("mkt") or [""])
    if not force and not tg_need and last and last >= newest and (not T["groups"] or tg_last >= newest):
        return 0
    SP = HD.ShardPanel()
    if not force and not tg_need and last and SP.cal and last >= SP.cal[-1] and (not T["groups"] or tg_last >= SP.cal[-1]):
        return 0
    P = bt3d.Panel(start=BI.TW_START)
    HD.extend(P, SP)
    n = indtw_save(P)
    if T["groups"]:
        n += indtw_save(P, TG_KIND, T["groups"], {"src": src})
    return n


def load_indtw(kind: str = IND_KIND) -> dict:
    """indtw 按月檔 → {"cal": [每天], "grp": {產業: {"px": [每天], "n": {月: 成分數}, "turn": {月: 換手率}}}}（indtg 另帶 "src"）。"""
    from . import store
    cal: list = []
    G: dict = {}
    src = ""
    for ym, doc in store.load(kind):
        src = doc.get("src") or src
        c = doc.get("cal") or []
        n0 = len(cal)
        cal += c
        for g, v in (doc.get("px") or {}).items():
            G.setdefault(g, {"px": [None] * n0, "n": {}, "turn": {}})
        for g, Gd in G.items():
            v = (doc.get("px") or {}).get(g)
            Gd["px"] += v if v else [None] * len(c)
            if g in (doc.get("n") or {}):
                Gd["n"][ym] = doc["n"][g]
            if g in (doc.get("turn") or {}):
                Gd["turn"][ym] = doc["turn"][g]
    return {"cal": cal, "grp": G, "src": src}


def monthly_from_daily(cal: list, px: list, last_day: str | None = None) -> tuple[dict, dict]:
    """每天指數 → ({月: 月底值}, {月: 月平均}）；月平均只算 last_day 那個月以前的完整月份（同 heatcalc_bub.month_avg_px）。"""
    from .heatcalc_bub import month_avg_px, month_end_px
    daily = {d: v for d, v in zip(cal, px) if v}
    last_day = last_day or cal[-1]
    return month_end_px(daily), month_avg_px(daily, last_day)


def load_rev() -> dict:
    """月營收 {代號: {營收月: 千元}}（2012 起）。"""
    from . import store
    out: dict = {}
    for ym, doc in store.load("rev"):
        for c, r in (doc.get("s") or {}).items():
            if r and r[0] is not None:
                out.setdefault(c, {})[ym] = r[0]
    return out


def tw_ps(grp: str, im: dict, caps: list, rev: dict, mem: set | None = None) -> dict:
    """產業 P/S（取對數）{月: log(成員月底市值合計 ÷ 它們近 12 個月營收合計)}；成員＝月底市值 ≥ TW_CAP_MIN、
    營收月 m−12～m−1 都有的公司（第 m−1 個月營收第 m 個月 10 日公布，月底 m 拿得到）。caps＝bt3d.month_end_caps()。
    mem＝族群成員集合（細分族群；給了就不看 im）。"""
    out: dict = {}
    for d, cp in caps:
        ym = d[:7]
        ms = [_ym_add(ym, -j) for j in range(1, BI.E_SUM + 1)]
        num = den = 0.0
        for c, cap in cp.items():
            if (c not in mem if mem is not None else im.get(c) != grp) or not cap or cap < BI.TW_CAP_MIN:
                continue
            r = rev.get(c)
            if not r:
                continue
            xs = [r.get(m) for m in ms]
            if any(x is None for x in xs):
                continue
            s = sum(xs) * 1000.0
            if s <= 0:
                continue
            num += cap
            den += s
        if num > 0 and den > 0:
            out[ym] = math.log(num / den)
    return out


def rev_s12(rev: dict) -> dict:
    """{代號: {營收月: 近 12 個月合計}}（12 個月都有才算）。tw_rev_proxy 共用，只算一次。"""
    out: dict = {}
    for c, r in rev.items():
        ms = sorted(r)
        d: dict = {}
        run: list = []
        prev = None
        for m in ms:
            if prev is not None and _mdiff(prev, m) != 1:
                run = []
            run.append(r[m])
            if len(run) > 12:
                run.pop(0)
            if len(run) == 12:
                d[m] = sum(run)
            prev = m
        if d:
            out[c] = d
    return out


def tw_rev_proxy(grp: str, im: dict, caps: list, rev: dict, s12: dict | None = None, mem: set | None = None) -> dict:
    """台股產業 G 的替代資料：{營收月: {"G1", "R", "y12", "y12b"}}（同一批公司，第 12.2 節）。
    成員＝那個營收月月底市值 ≥ TW_CAP_MIN 的產業公司（月底快照；沒有那個月的快照用之前最近的）。"""
    s12 = s12 if s12 is not None else rev_s12(rev)
    snap = {d[:7]: cp for d, cp in caps}
    keys = sorted(snap)

    def members(ym):
        i = bisect.bisect_right(keys, ym) - 1
        if i < 0:
            return []
        cp = snap[keys[i]]
        return [c for c, cap in cp.items() if (c in mem if mem is not None else im.get(c) == grp)
                and cap and cap >= BI.TW_CAP_MIN and c in s12]

    def pair(cs, a_m, b_m):
        a = b = 0.0
        for c in cs:
            d = s12[c]
            x, y = d.get(a_m), d.get(b_m)
            if x is None or y is None:
                continue
            a += x
            b += y
        return a, b

    allm = sorted({m for d in s12.values() for m in d})
    out: dict = {}
    for ym in allm:
        cs = members(ym)
        if not cs:
            continue
        a, b = pair(cs, ym, _ym_add(ym, -12))
        y0 = a / b - 1.0 if b > 0 else None
        y6m = _ym_add(ym, -BI.G1_BACK)
        a, b = pair(cs, y6m, _ym_add(y6m, -12))
        y6 = a / b - 1.0 if b > 0 else None
        a, b = pair(cs, ym, _ym_add(ym, -BI.R_BACK))
        R = (a < b) if b > 0 else None
        G1 = (y0 < y6) if y0 is not None and y6 is not None else None
        if G1 is None and R is None:
            continue
        out[ym] = {"G1": G1, "R": R, "y12": y0, "y12b": y6}
    return out


# ── 美股：類股 ETF、Ken French 49 產業 ──────────────────────────────────────

def etf_daily(sym: str) -> tuple[list, list]:
    d = HD.load(f"us_etf_{sym}")
    cal = sorted(k for k, v in d.items() if v)
    return cal, [d[k] for k in cal]


def ff_build() -> dict:
    """Ken French → {"months", "ind": {代號: {月: 指數}}, "mkt": {月: 指數}, "n": {代號: {月: 家數}}}。
    大盤＝每月依前一個月市值（平均公司規模 × 家數；KF 的平均公司規模是月初市值）加權的不含股利報酬。"""
    X, N, Sz = HD.load("us_ff49x"), HD.load("us_ff49n"), HD.load("us_ff49s")
    months = sorted(X)
    if not months:
        return {}
    ind, nf = {}, {}
    for j, code in enumerate(BI.FF49):
        if code in BI.FF_SKIP:
            continue
        rets = {m: (X[m][j] if j < len(X[m]) else None) for m in months}
        ind[code] = chain(rets, months)
        nf[code] = {m: N[m][j] for m in months if m in N and j < len(N[m]) and N[m][j]}
    mret = {}
    for m in months:
        num = den = 0.0
        for j in range(len(BI.FF49)):
            r = X[m][j] if j < len(X[m]) else None
            n = (N.get(m) or [None] * 49)[j]
            s = (Sz.get(m) or [None] * 49)[j]
            if r is None or not n or not s:
                continue
            num += r * n * s
            den += n * s
        mret[m] = num / den if den > 0 else None
    return {"months": months, "ind": ind, "mkt": chain(mret, months), "n": nf}


# ── 條件（三組共用） ─────────────────────────────────────────────────────

def _segments_px(me_px: dict) -> dict:
    """{月: 月底值} → {月: 這一段到當月的最高月底值}（缺月斷開）。"""
    out, hi, prev = {}, None, None
    for m in sorted(me_px):
        v = me_px[m]
        if prev is None or _mdiff(prev, m) != 1:
            hi = None
        hi = v if hi is None else max(hi, v)
        out[m] = hi
        prev = m
    return out


def conditions(S: dict, T: dict) -> dict:
    """S＝一個產業的輸入：{"me": {月: 月底值}, "pm": {月: 月平均或月底值}, "mkt": {月: 大盤月底值}, "cpi": {月: CPI},
    "ps": {月: log P/S}（選）, "gp": {營收月: 替代資料}（選）, "f": {月: 燃料原始值}（選）, "fmin": 燃料最少月數,
    "trend": 算不算 P3}。→ {"rows": [每月], "R": PSY, "z": 趨勢 z, "EF": E 的 PSY}。"""
    from . import heat as H
    from . import heatbubble as HB
    from .heatcalc_bub import real_log
    me, mkt = S["me"], S["mkt"]
    months = sorted(me)
    lr = real_log(S["pm"], S["cpi"], BI.PSY["cpi_lag"])
    R = BU.psy_drift(lr, T)
    p1r = BU.p1_flags(R)
    p1m = {m: bool(v and BU.dir_up(lr, m)) for m, v in p1r.items()}
    z = HB.trend_z(lr, BI.TREND["min"])[0] if S.get("trend", True) else {}
    ef: dict = {}
    if S.get("ps"):
        lme = {m: math.log(v) for m, v in me.items() if v and v > 0}
        ER = BU.psy_drift(S["ps"], T)
        f0 = {m: all((ER.get(_ym_add(m, -j)) or {}).get("hit") for j in range(BI.E_RUN)) for m in ER}
        ef = {m: bool(x and BU.dir_up(lme, m) and BU.dir_up(S["ps"], m)) for m, x in f0.items()}
    fp = pct_span(S["f"], S["fmin"]) if S.get("f") else {}
    hi = _segments_px(me)
    p1 = H.asof_monthly([f"{m}-31" for m in months], p1m, REL)
    p3 = H.asof_monthly([f"{m}-31" for m in months], z, REL) if z else [None] * len(months)
    ea = H.asof_monthly([f"{m}-31" for m in months], ef, REL) if ef else [None] * len(months)
    fa = H.asof_monthly([f"{m}-31" for m in months], fp, REL) if fp else [None] * len(months)
    gp = S.get("gp") or {}
    gav = sorted((H.avail_date(k, BI.REV_REL), k) for k in gp)
    gad = [x[0] for x in gav]
    rows = []
    for j, m in enumerate(months):
        v = me[m]
        a = _ym_add(m, -BI.RUN2_MONTHS)
        P2 = None
        if a in me and me[a] and m in mkt and a in mkt and mkt[a] and _contig(me, a, m):
            ru = v / me[a] - 1.0
            mu = mkt[m] / mkt[a] - 1.0
            P2 = ru * 100 >= BI.RUN2_PCT and (ru - mu) * 100 >= BI.NET_PP and v >= hi[m] * (1.0 - BI.RUN2_ATH)
        P1 = p1[j]
        P3 = None if p3[j] is None else p3[j] >= BI.TREND_Z
        E = ea[j] if ef else None
        F = None if fa[j] is None else fa[j] >= BI.FUEL_PCT
        G1 = G2 = G = None
        if gp:
            k = bisect.bisect_right(gad, f"{m}-31") - 1
            if k >= 0 and _mdiff(gav[k][1], m) <= BU.FUND_STALE:
                rec = gp[gav[k][1]]
                b3 = _ym_add(m, -BI.G_PRICE_MONTHS)
                up = None if b3 not in me or not _contig(me, b3, m) else v > me[b3]
                G1, G2, G = BU.g_flags(rec.get("G1"), rec.get("R"), up)
        price = bool(P1 or P2 or P3)
        rows.append({"d": m, "P1": P1, "P2": P2, "P3": P3, "E": E, "G1": G1, "G2": G2, "G": G, "F": F,
                     "L": BI.level4(price, bool(E), False, bool(G), bool(F))})
    return {"rows": rows, "R": R, "z": z, "lr": lr, "ef": ef, "fp": fp}


def _contig(me: dict, a: str, b: str) -> bool:
    """a 到 b 每個月都有值（中間沒有斷開）。"""
    m = a
    while m <= b:
        if not me.get(m):
            return False
        m = _ym_add(m, 1)
    return True


# ── 最後一個月（只算需要的那幾個點；美股 49 細產業每天建頁用，結果和 conditions 的最後一列相同） ──────

def _bsadf_tail(ys: list, k: int) -> list:
    """ys 最後 k 個位置的 BSADF（其他位置 None）；O(n × k)。"""
    from .heatbubble import bsadf
    return bsadf(ys, BI.PSY["w0"], start=max(0, len(ys) - k))


def _psy_tail(lr: dict, T: dict, k: int) -> dict:
    """{月: {"s", "q95", "hit", "g"}}：只算 lr 最後一段的最後 k 個月（同 bubble.psy_drift 的漂移與臨界值內插）。"""
    segs = BU._segments(lr)
    if not segs:
        return {}
    sg = segs[-1]
    ys = [lr[m] for m in sg]
    st = _bsadf_tail(ys, k)
    out: dict = {}
    n, mean, m2 = 0, 0.0, 0.0
    for i, m in enumerate(sg):
        if i:
            d = ys[i] - ys[i - 1]
            n += 1
            delta = d - mean
            mean += delta / n
            m2 += delta * (d - mean)
        if st[i] is None or n < BU.BS.DRIFT_MIN_N or m2 <= 0:
            continue
        g = mean / math.sqrt(m2 / (n - 1))
        q50, q95 = BU.cv_at(T, i, g)
        if q95 is None:
            continue
        out[m] = {"s": st[i], "q95": q95, "g": g, "hit": st[i] > q95}
    return out


def _trend_last(lr: dict, upto: str) -> float | None:
    """heatbubble.trend_z 在 upto 那個月的 z（同一套算式，只算一個點）。"""
    ks = [k for k in sorted(lr) if k <= upto]
    if len(ks) < BI.TREND["min"] or ks[-1] != upto:
        return None
    base = ks[0]
    xs = [float(_mdiff(base, k)) for k in ks]
    ys = [lr[k] for k in ks]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    ssr = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    s_ = math.sqrt(ssr / (n - 2)) if ssr > 0 else 0.0
    if s_ <= 0:
        return None
    return (ys[-1] - a - b * xs[-1]) / s_


def ff_last_row(S: dict, T: dict) -> dict | None:
    """美股 49 細產業最後一個月的條件（同 conditions 的最後一列；P1、P3、F 用前一個月的讀數＝REL）。"""
    from .heatcalc_bub import real_log
    me, mkt = S["me"], S["mkt"]
    if not me:
        return None
    m = max(me)
    p = _ym_add(m, -1)
    lr = real_log(S["pm"], S["cpi"], BI.PSY["cpi_lag"])
    R = _psy_tail(lr, T, BI.PSY_RUN + 24)
    run = 0
    while (R.get(_ym_add(p, -run)) or {}).get("hit"):
        run += 1
    have = p in R
    P1 = (run >= BI.PSY_RUN and BU.dir_up(lr, p)) if have and all(_ym_add(p, -j) in R for j in range(BI.PSY_RUN)) else (
        False if have else None)
    z = _trend_last(lr, p) if p in lr else None
    P3 = None if z is None else z >= BI.TREND_Z
    hi = _segments_px(me)[m]
    a = _ym_add(m, -BI.RUN2_MONTHS)
    P2 = None
    ru = mu = None
    if a in me and me[a] and m in mkt and a in mkt and mkt[a] and _contig(me, a, m):
        ru, mu = me[m] / me[a] - 1.0, mkt[m] / mkt[a] - 1.0
        P2 = ru * 100 >= BI.RUN2_PCT and (ru - mu) * 100 >= BI.NET_PP and me[m] >= hi * (1.0 - BI.RUN2_ATH)
    fp = pct_span(S["f"], S["fmin"]) if S.get("f") else {}
    fv = fp.get(p)
    F = None if fv is None else fv >= BI.FUEL_PCT
    price = bool(P1 or P2 or P3)
    return {"d": m, "P1": P1, "P2": P2, "P3": P3, "E": None, "G1": None, "G2": None, "G": None, "F": F,
            "L": BI.level4(price, False, False, False, bool(F)),
            "p1": {"ym": p, **R[p], "run": run} if have else None, "p3": {"ym": p, "z": z},
            "p2": {"ru": None if ru is None else 100.0 * ru, "net": None if ru is None else 100.0 * (ru - mu),
                   "dist": 100.0 * (me[m] / hi - 1.0)}, "f": fv}


# ── 現在的狀態 ─────────────────────────────────────────────────────────

def now_p2(cal: list, px: list, mcal: list, mpx: list, me: dict) -> dict:
    """現在的 P2：最新收盤 ÷ 24 個月前同一天（那天或之前最後一個交易日）收盤；大盤同；歷史最高＝之前的月底值與最新收盤。"""
    import calendar
    from datetime import date
    d = cal[-1]
    dt = date.fromisoformat(d)
    y = dt.year - BI.RUN2_MONTHS // 12
    a = date(y, dt.month, min(dt.day, calendar.monthrange(y, dt.month)[1])).isoformat()
    pa = BU.px_on(cal, px, a)
    ma, mz = BU.px_on(mcal, mpx, a), BU.px_on(mcal, mpx, d)
    v = px[-1]
    seg = _segments_px({m: x for m, x in me.items() if m < d[:7] and x})
    hi = max(seg[max(seg)], v) if seg else v
    if not pa or not ma or not mz or not v:
        return {"ru": None, "net": None, "dist": 100.0 * (v / hi - 1.0) if v and hi else None, "P2": None}
    ru, mu = v / pa - 1.0, mz / ma - 1.0
    on = ru * 100 >= BI.RUN2_PCT and (ru - mu) * 100 >= BI.NET_PP and v >= hi * (1.0 - BI.RUN2_ATH)
    return {"ru": 100.0 * ru, "net": 100.0 * (ru - mu), "dist": 100.0 * (v / hi - 1.0), "P2": on}


def _latest(ser: dict, day: str, rel=REL):
    return BU._latest(ser, day, rel)


def now_status(S: dict, C: dict, day: str, p2: dict, gnow: dict | None) -> dict:
    """day 當下的條件（P1、E、P3、F 用拿得到的最新一個月；P2 用 now_p2；G 有預估用預估，不然用替代資料）。"""
    ym1, r1 = _latest(C["R"], day)
    run = 0
    if ym1:
        while (C["R"].get(_ym_add(ym1, -run)) or {}).get("hit"):
            run += 1
    P1 = None if not ym1 else (run >= BI.PSY_RUN and BU.dir_up(C["lr"], ym1))
    ym3, z = _latest(C["z"], day) if C["z"] else (None, None)
    P3 = None if z is None else z >= BI.TREND_Z
    E = None
    if C["ef"]:
        _, E = _latest(C["ef"], day)
    F = None
    fpct = None
    if C["fp"]:
        _, fpct = _latest(C["fp"], day)
        F = None if fpct is None else fpct >= BI.FUEL_PCT
    G, gsrc, gi = None, None, None
    if gnow and gnow.get("G") is not None:
        G, gsrc, gi = gnow["G"], "est", gnow
    elif S.get("gp"):
        from . import heat as H
        av = [(H.avail_date(k, BI.REV_REL), k) for k in S["gp"]]
        av = [x for x in av if x[0] <= day]
        if av:
            k = max(av)[1]
            if _mdiff(k, day[:7]) <= BU.FUND_STALE:
                rec = S["gp"][k]
                up = BU.up_days(S["cal"], S["px"], day, BI.G_PRICE_DAYS) if S.get("cal") else None
                G1, G2, G = BU.g_flags(rec.get("G1"), rec.get("R"), up)
                gsrc, gi = "proxy", {"per": k, "G1": G1, "G2": G2, "G": G, "y12": rec.get("y12"), "y12b": rec.get("y12b")}
        if gi is None and gnow:
            gi = gnow
    elif gnow:
        gi = gnow
    price = bool(P1 or p2.get("P2") or P3)
    L = BI.level4(price, bool(E), False, bool(G), bool(F))
    return {"d": day, "P1": P1, "P2": p2.get("P2"), "P3": P3, "E": E, "G": G, "F": F, "L": L,
            "p1": None if not ym1 else {"ym": ym1, "s": r1["s"], "q95": r1["q95"], "x": r1["x"], "run": run},
            "p2": p2, "p3": {"ym": ym3, "z": z}, "f": fpct, "g": gi, "gsrc": gsrc}


# ── 現在的分析師預估（台股產業、美股類股） ──────────────────────────────────

def tw_est_now(im: dict, groups: dict | None = None) -> dict:
    """{產業: fwd.aggregate＋"d"}（Yahoo 預估依產業加總；涵蓋＝用到的公司市值 ÷ 產業全部普通股市值）。
    groups＝{族群: 代號集合}（細分族群）→ 依族群加總。"""
    import re
    from . import fcst
    from . import fwd as FW
    from .fwdfetch import tw_shares_close
    yh = fcst.load_yahoo()
    if not yh.get("s"):
        return {}
    sh, px, _ = tw_shares_close()
    rows = FW.est_rows_tw(yh["s"], sh, px)
    out = {}
    if groups is not None:
        mem = {g: sorted(groups[g]) for g in sorted(groups)}
    else:
        mem = {g: [c for c, x in im.items() if x == g] for g in sorted({v for v in im.values() if v and v not in BI.TW_SKIP})}
    for g, cs0 in mem.items():
        cs = [c for c in cs0 if re.match(r"^[1-9]\d{3}$", c)]
        cap_all = sum((sh.get(c) or 0) * (px.get(c) or 0) for c in cs)
        rs = {c: rows[c] for c in cs if c in rows}
        if not rs or cap_all <= 0:
            continue
        a = FW.aggregate(rs, cap_all)
        a["d"] = yh.get("d")
        a["top"] = FW.top_contrib(rs, 3)
        out[g] = a
    return out


def us_est_now() -> dict:
    """{ETF 代號: fwd.aggregate＋"d"}（S&P 500 成分股依 GICS 類別加總；每家公司資料在 EST_STALE_DAYS 天內）。"""
    from datetime import date, timedelta
    from . import fwd as FW
    from . import store
    doc = store.read("fwd", "us") or {}
    const = doc.get("const") or {}
    gics = const.get("gics") or {}
    d = doc.get("d")
    if not gics or not d:
        return {}
    lim = (date.fromisoformat(d) - timedelta(days=BI.EST_STALE_DAYS)).isoformat()
    recs = {k: v for k, v in (doc.get("s") or {}).items() if v.get("d", "") >= lim and v.get("y0")}
    q, fx = doc.get("q") or {}, doc.get("fx") or {}
    out = {}
    for sec, etf in BI.GICS_ETF.items():
        syms = [s for s, g in gics.items() if g == sec]
        rows = FW.est_rows_us(recs, q, fx, syms)
        cap_all = sum((q.get(x) or [0])[0] or 0 for x in syms)
        if not rows or cap_all <= 0:
            continue
        a = FW.aggregate(rows, cap_all)
        a["d"] = d
        a["top"] = FW.top_contrib(rows, 3)
        out[etf] = a
    return out


def g_now_est(a: dict | None, cal: list, px: list) -> dict | None:
    """預估加總＋價格（91 天前）→ {"d", "n", "cov", "g0", "g1", "rev", "px3", "G1", "G2", "G", "top"}。"""
    if not a:
        return None
    from datetime import date, timedelta
    ed = a.get("d")
    if not ed:
        return None
    x = BU.px_on(cal, px, ed)
    y = BU.px_on(cal, px, (date.fromisoformat(ed) - timedelta(days=BI.G_PRICE_DAYS)).isoformat())
    up = None if not x or not y else x > y
    G1, G2, G = BU.g_flags(a.get("G1"), a.get("R"), up)
    return {"d": ed, "n": a.get("n"), "cov": a.get("cov"), "g0": a.get("g0"), "g1": a.get("g1"), "rev": a.get("rev"),
            "px3": None if not x or not y else 100.0 * (x / y - 1.0), "G1": G1, "G2": G2, "G": G, "top": a.get("top")}


# ── 三組的輸入 ─────────────────────────────────────────────────────────

def tw_inputs(TB: dict | None = None) -> dict:
    """台股產業：{"cal", "mkt": (cal, px), "S": {產業: 條件輸入}}；TB＝load_indtw()（或 tw_build 的結果）。"""
    from . import bt3d
    im = tw_ind_map()
    TB = TB if TB is not None else load_indtw()
    cal = TB.get("cal") or []
    if not cal or MKT not in TB["grp"]:
        return {}
    mk = TB["grp"][MKT]
    mme, _ = monthly_from_daily(cal, mk["px"])
    cpi = BU.fill_cpi({k: v[0] for k, v in HD.load("twcpi").items() if v and v[0]})
    caps = bt3d.month_end_caps()
    rev = load_rev()
    s12 = rev_s12(rev)
    out = {}
    for g, Gd in TB["grp"].items():
        if g == MKT or g in BI.TW_SKIP:
            continue
        me, pm = monthly_from_daily(cal, Gd["px"])
        if not me:
            continue
        S = {"me": me, "pm": pm, "mkt": mme, "cpi": cpi, "cal": cal, "px": Gd["px"], "trend": True,
             "n": Gd["n"], "f": Gd["turn"], "fmin": BI.F_MIN_MONTHS["tw"]}
        if g not in BI.E_SKIP:
            S["ps"] = tw_ps(g, im, caps, rev)
            S["gp"] = tw_rev_proxy(g, im, caps, rev, s12)
        out[g] = S
    return {"cal": cal, "mkt": (cal, mk["px"]), "mme": mme, "S": out, "im": im}


def tg_inputs(TB: dict | None = None, TM: dict | None = None) -> dict:
    """台股細分族群：同 tw_inputs，成員＝tg_members()；指數讀 indtg（名單日期和現在的名單不同＝不用，等 CI 重算）。"""
    from . import bt3d
    TM = TM if TM is not None else tg_members()
    if not TM["groups"]:
        return {}
    TB = TB if TB is not None else load_indtw(TG_KIND)
    cal = TB.get("cal") or []
    if not cal or MKT not in TB["grp"] or (TB.get("src") and TB["src"] != TM["d"]):
        return {}
    mk = TB["grp"][MKT]
    mme, _ = monthly_from_daily(cal, mk["px"])
    cpi = BU.fill_cpi({k: v[0] for k, v in HD.load("twcpi").items() if v and v[0]})
    caps = bt3d.month_end_caps()
    rev = load_rev()
    s12 = rev_s12(rev)
    out = {}
    for g, mem in TM["groups"].items():
        Gd = TB["grp"].get(g)
        if not Gd:
            continue
        me, pm = monthly_from_daily(cal, Gd["px"])
        if not me:
            continue
        out[g] = {"me": me, "pm": pm, "mkt": mme, "cpi": cpi, "cal": cal, "px": Gd["px"], "trend": True,
                  "n": Gd["n"], "f": Gd["turn"], "fmin": BI.F_MIN_MONTHS["tw"],
                  "ps": tw_ps(g, {}, caps, rev, mem), "gp": tw_rev_proxy(g, {}, caps, rev, s12, mem)}
    last = caps[-1][1] if caps else {}
    order = {g: sorted(mem, key=lambda c: (-(last.get(c) or 0), c)) for g, mem in TM["groups"].items()}
    return {"cal": cal, "mkt": (cal, mk["px"]), "mme": mme, "S": out, "TM": TM, "order": order}


def us_inputs(L: dict | None = None) -> dict:
    """美股類股：{"S": {ETF: 條件輸入}, "mkt": (cal, px)}。"""
    if L is None:
        L = BU.us_inputs(BU.load_us())["L"]
    mcal, mpx = etf_daily(BI.US_MKT)
    if not mcal:
        return {}
    mme, _ = monthly_from_daily(mcal, mpx)
    out = {}
    for sym in sorted(BI.US_ETF):
        cal, px = etf_daily(sym)
        if not cal:
            continue
        me, pm = monthly_from_daily(cal, px)
        out[sym] = {"me": me, "pm": pm, "mkt": mme, "cpi": L["cpi"], "cal": cal, "px": px, "trend": True}
    return {"S": out, "mkt": (mcal, mpx), "mme": mme}


def ff_inputs(L: dict | None = None) -> dict:
    """美股 49 細產業：月底指數當月平均（沒有日資料），燃料＝家數 12 個月增加率。"""
    F = ff_build()
    if not F:
        return {}
    if L is None:
        L = BU.us_inputs(BU.load_us())["L"]
    out = {}
    for code, me in F["ind"].items():
        n = F["n"][code]
        ng = {m: 100.0 * (n[m] / n[_ym_add(m, -12)] - 1.0) for m in n if n.get(_ym_add(m, -12))}
        out[code] = {"me": me, "pm": me, "mkt": F["mkt"], "cpi": L["cpi"], "trend": True,
                     "f": ng, "fmin": BI.F_MIN_MONTHS["ff"], "nf": n}
    return {"S": out, "mme": F["mkt"], "last": F["months"][-1]}


# ── 驗證（研究時跑） ────────────────────────────────────────────────────

def _flag(r: dict, t: str):
    if t == "PX":
        vs = [r["P1"], r["P2"], r["P3"]]
        return None if all(v is None for v in vs) else bool(any(vs))
    if t == "P2F":
        if r["P2"] is None or r["F"] is None:
            return None
        return bool(r["P2"] and r["F"])
    if t == "L3":
        return r["L"] >= 3
    return r.get(t)


def samples(S: dict, C: dict) -> list[dict]:
    """每個月一個樣本：月底值序列上之後 12、24 個月的最大回落與報酬（缺月＝None）。"""
    me = S["me"]
    months = sorted(me)
    pos = {m: i for i, m in enumerate(months)}
    vals = [me[m] for m in months]
    out = []
    for r in C["rows"]:
        i = pos[r["d"]]
        rec = {"d": r["d"], "r": r}
        for h, _ in BI.DD_MONTHS:
            j = i + h
            ok = j < len(months) and _mdiff(months[i], months[j]) == h
            rec[f"dd{h}"] = drawdown(vals, i, j) if ok else None
            rec[f"ret{h}"] = 100.0 * (vals[j] / vals[i] - 1.0) if ok and vals[i] else None
        out.append(rec)
    return out


def panel_test(pan: dict[str, list[dict]], t: str) -> dict:
    """pan＝{產業: samples()}；t＝條件代號 → 每個期間 {n, n_hot, p_hot, p_all, diff, lo, hi, h1, h2, n_epi, n_iepi, verdict,
    ret_hot, ret_all}（第 12.4 節）。以月份為單位做移動區塊重抽。"""
    from .heatbubble import episodes, _mno
    out: dict = {}
    for h, thr in BI.DD_MONTHS:
        by: dict[str, list] = {}
        rh, ra = [], []
        for code, ss in pan.items():
            for s in ss:
                f = _flag(s["r"], t)
                if f is None or s[f"dd{h}"] is None:
                    continue
                c = 1.0 if s[f"dd{h}"] >= thr else 0.0
                by.setdefault(s["d"], []).append((f, c))
                if s[f"ret{h}"] is not None:
                    ra.append(s[f"ret{h}"])
                    if f:
                        rh.append(s[f"ret{h}"])
        ms = sorted(by)
        nh = [sum(1 for f, _ in by[m] if f) for m in ms]
        ch = [sum(c for f, c in by[m] if f) for m in ms]
        na = [len(by[m]) for m in ms]
        ca = [sum(c for _, c in by[m]) for m in ms]

        def diff(a, b):
            NH, CH, NA, CA = sum(nh[a:b]), sum(ch[a:b]), sum(na[a:b]), sum(ca[a:b])
            return None if not NH or not NA else CH / NH - CA / NA
        n_hot = sum(nh)
        lo = hi = None
        Lb = BI.BUB_BLOCK
        if n_hot >= 2 and len(ms) >= 2 * Lb:
            rnd = random.Random(BI.BUB_SEED)
            reps = []
            starts = len(ms) - Lb + 1
            pnh, pch, pna, pca = [0], [0.0], [0], [0.0]
            for i in range(len(ms)):
                pnh.append(pnh[-1] + nh[i])
                pch.append(pch[-1] + ch[i])
                pna.append(pna[-1] + na[i])
                pca.append(pca[-1] + ca[i])
            for _ in range(BI.BUB_BOOT):
                NH = NA = 0
                CH = CA = 0.0
                k = 0
                while k < len(ms):
                    s0 = rnd.randrange(starts)
                    NH += pnh[s0 + Lb] - pnh[s0]
                    CH += pch[s0 + Lb] - pch[s0]
                    NA += pna[s0 + Lb] - pna[s0]
                    CA += pca[s0 + Lb] - pca[s0]
                    k += Lb
                if NH and NA:
                    reps.append(CH / NH - CA / NA)
            if len(reps) >= BI.BUB_BOOT // 2:
                reps.sort()
                lo, hi = reps[int(0.025 * len(reps))], reps[min(len(reps) - 1, int(0.975 * len(reps)))]
        m2 = len(ms) // 2
        d1, d2 = diff(0, m2), diff(m2, len(ms))
        hot_months = [m for m, k in zip(ms, nh) if k]
        ne = len(episodes([_mno(m + "-28") for m in hot_months], [True] * len(hot_months)))
        nie = 0
        for code, ss in pan.items():
            fl = [(s["d"], _flag(s["r"], t)) for s in ss if s[f"dd{h}"] is not None]
            hm = [m for m, f in fl if f]
            nie += len(episodes([_mno(m + "-28") for m in hm], [True] * len(hm)))
        dall = diff(0, len(ms))
        if n_hot < BI.BUB_MIN_HOT or ne < BI.BUB_EPI_MIN or lo is None:
            vd = "few"
        elif lo > 0 and d1 is not None and d2 is not None and d1 > 0 and d2 > 0:
            vd = "crash"
        elif hi < 0 and d1 is not None and d2 is not None and d1 < 0 and d2 < 0:
            vd = "calm"
        else:
            vd = "none"
        out[str(h)] = {"n": sum(na), "n_hot": n_hot, "thr": thr,
                       "p_hot": sum(ch) / n_hot if n_hot else None, "p_all": sum(ca) / sum(na) if sum(na) else None,
                       "diff": dall, "lo": lo, "hi": hi,
                       "h1": {"diff": d1, "z": ms[m2 - 1] if m2 else None}, "h2": {"diff": d2, "a": ms[m2] if len(ms) > m2 else None},
                       "a": ms[0] if ms else None, "z": ms[-1] if ms else None, "n_epi": ne, "n_iepi": nie, "verdict": vd,
                       "ret_hot": sum(rh) / len(rh) if rh else None, "ret_all": sum(ra) / len(ra) if ra else None}
    return out


def group_research(grp: str, I: dict, T: dict) -> dict:
    pan = {}
    for code, S in I["S"].items():
        C = conditions(S, T)
        rows = C["rows"]
        j0 = next((j for j, r in enumerate(rows) if r["P1"] is not None and r["P2"] is not None), None)
        if j0 is None:
            continue
        C["rows"] = rows[j0:]
        pan[code] = samples(S, C)
    out = {"tests": {t: panel_test(pan, t) for t in BI.TESTS[grp]}, "n_ind": len(pan),
           "a": min((ss[0]["d"] for ss in pan.values() if ss), default=None),
           "z": max((ss[-1]["d"] for ss in pan.values() if ss), default=None)}
    out["dist"] = {str(lv): sum(1 for ss in pan.values() for s in ss if s["r"]["L"] == lv) for lv in BI.LEVELS}
    out["epi"] = _episodes_list(pan)
    return out


def _episodes_list(pan: dict) -> list[dict]:
    """每個產業等級 ≥ 2 的段（只描述）：起訖月、月數、最高等級、出現過的條件、段內最高月底值之後 24 個月內最大跌幅。"""
    from .heatbubble import episodes, _mno
    out = []
    for code, ss in pan.items():
        fl = [s["r"]["L"] >= 2 for s in ss]
        for a, b in episodes([_mno(s["d"] + "-28") for s in ss], fl):
            seg = [s for s in ss[a:b + 1] if s["r"]["L"] >= 2]
            out.append({"id": code, "a": ss[a]["d"], "z": ss[b]["d"], "n": len(seg), "max": max(s["r"]["L"] for s in seg),
                        "cond": [c for c in ("P1", "P2", "P3", "E", "G", "F") if any(s["r"].get(c) for s in seg)],
                        "dd24": max((s["dd24"] for s in seg if s["dd24"] is not None), default=None)})
    out.sort(key=lambda e: (e["a"], e["id"]))
    return out


RESEARCH = "data/lab/bubind_research.json"


def research(T: dict | None = None) -> dict:
    from .heatbubble import _rnd
    T = T or BU.load_cv_table()
    if not T:
        raise SystemExit("沒有 PSY 漂移臨界值表：先跑 scripts/run_bub.py --cv")
    L = BU.us_inputs(BU.load_us())["L"]
    out = {"ver": BI.VER, "spec_date": BI.SPEC_DATE}
    FF = ff_inputs(L)
    if FF:
        out["ff"] = group_research("ff", FF, T)
    US = us_inputs(L)
    if US:
        out["us"] = group_research("us", US, T)
    out["tw"] = group_research("tw", tw_inputs(), T)
    TG = tg_inputs()
    if TG:
        out["tg"] = group_research("tg", TG, T)
        out["tg"]["src"] = TG["TM"]["d"]
    return _rnd(out)


def save_research(R: dict) -> bool:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / RESEARCH
    txt = json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.write_text(txt, encoding="utf-8")
    return True


def load_research() -> dict | None:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[2] / RESEARCH
    try:
        R = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if R.get("ver") == BI.VER else None


# ── 每天建頁：現在的狀態與歷史等級 ─────────────────────────────────────────

def _hist(C: dict, me: dict) -> dict:
    code = lambda r: "".join(c for c, k in (("1", "P1"), ("2", "P2"), ("3", "P3"), ("e", "E"), ("g", "G"), ("f", "F"))  # noqa: E731
                             if r.get(k))
    rows = [r for r in C["rows"] if r["P1"] is not None or r["P2"] is not None]
    return {"d": [r["d"] for r in rows], "L": [r["L"] for r in rows], "c": [code(r) for r in rows],
            "p": [round(me[r["d"]], 4) for r in rows]}


def _tw_now(I: dict, T: dict, est: dict) -> dict:
    """台股產業／細分族群：每一組的現在狀態與歷史等級。"""
    mcal, mpx = I["mkt"]
    grp = {}
    for g, S in I["S"].items():
        C = conditions(S, T)
        cal, px = S["cal"], S["px"]
        ix = [i for i, v in enumerate(px) if v]
        if not ix:
            continue
        cal2, px2 = [cal[i] for i in ix], [px[i] for i in ix]
        S2 = dict(S, cal=cal2, px=px2)
        p2 = now_p2(cal2, px2, [mcal[i] for i, v in enumerate(mpx) if v], [v for v in mpx if v], S["me"])
        n = now_status(S2, C, cal2[-1], p2, g_now_est(est.get(g), cal2, px2))
        n["mem"] = S["n"].get(max(S["n"])) if S["n"] else None
        grp[g] = {"now": n, "hist": _hist(C, S["me"])}
    return grp


def compute(T: dict | None = None, TB: dict | None = None, TGB: dict | None = None) -> dict:
    """四組產業的現在狀態與歷史等級（每天建頁用；不跑驗證）。"""
    T = T or BU.load_cv_table()
    if not T:
        return {}
    out: dict = {"ver": BI.VER}
    L = BU.us_inputs(BU.load_us())["L"]
    try:
        TW = tw_inputs(TB)
        if not TW:
            raise ValueError("沒有 indtw（scripts/fetch_heat.py 會在 CI 算）")
        out["tw"] = _tw_now(TW, T, tw_est_now(TW["im"]))
    except Exception as e:                                        # noqa: BLE001 —— 台股產業失敗不影響美股
        out["tw_err"] = f"{type(e).__name__}: {e}"
    try:
        TM = tg_members()
        TG = tg_inputs(TGB, TM)
        if not TG:
            raise ValueError("沒有細分族群指數（data/lab/indtg 由 CI 算；名單換了要等下一次重算）")
        out["tg"] = _tw_now(TG, T, tw_est_now({}, TM["groups"]))
        out["tg_d"], out["tg_n"], out["tg_skip"], out["tg_list"] = TM["d"], TM["n"], TM["skip"], TG["order"]
    except Exception as e:                                        # noqa: BLE001 —— 細分族群失敗不影響其他組
        out["tg_err"] = f"{type(e).__name__}: {e}"
    US = us_inputs(L)
    if US:
        est = us_est_now()
        mcal, mpx = US["mkt"]
        grp = {}
        for sym, S in US["S"].items():
            C = conditions(S, T)
            p2 = now_p2(S["cal"], S["px"], mcal, mpx, S["me"])
            n = now_status(S, C, S["cal"][-1], p2, g_now_est(est.get(sym), S["cal"], S["px"]))
            grp[sym] = {"now": n, "hist": _hist(C, S["me"])}
        out["us"] = grp
    FF = ff_inputs(L)
    if FF:
        grp = {}
        for code, S in FF["S"].items():
            r = ff_last_row(S, T)
            if r:
                grp[code] = {"now": r}
        out["ff"] = grp
        out["ff_last"] = FF["last"]
    return out
