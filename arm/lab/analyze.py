"""籌碼雷達：逐檔彙整（ETF 面＋官方籌碼＋技術面＋訊號）→ 頁面資料。

資料全來自入庫分片（data/lab/），建頁零網路——容器端與 CI 端產出一致。
所有「窗口」以**交易日曆**計：日曆＝官方價量分片日 ∪ ETF 揭露日（揭露日一定是交易日）。
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from . import ledger as LG
from . import store, ta

ISSUERS = ("第一金", "元大", "國泰", "群益", "復華", "富邦", "野村", "統一", "安聯", "台新",
           "中信", "凱基", "聯博", "兆豐", "永豐", "摩根")

SIG_DEF = {
    "cons": ("共識加碼", "近 5 個交易日 ≥3 家不同投信的主動 ETF 真加碼／新建倉（已扣申贖），且主動合計淨買"),
    "new2": ("多家新建倉", "10 個交易日內 ≥2 家投信的主動 ETF 首次建倉，且當日有新建倉"),
    "strk": ("連續加碼", "同一檔主動 ETF 連續 ≥3 個揭露日真加碼"),
    "exit": ("集體撤退", "近 5 個交易日 ≥3 家投信主動 ETF 真減碼／出清，且主動合計淨賣（風險訊號）"),
    "cost": ("成本線回測", "股價回到主動 ETF 新建倉成本 ±3%（≥2 檔主動 ETF 觀測期內建倉），近 20 日曾高於成本 5% 以上，且近 10 日主動 ETF 未淨賣"),
    "reso": ("籌碼共振", "主動 ETF 5 日真加碼＞0、投信 5 日買超＞0、融資 5 日減少"),
    "brk": ("量價突破", "收盤創 20 日新高、量 ≥1.5 倍 20 日均量、站上 60 日線"),
    "trst": ("投信連買", "投信連續 ≥3 日買超"),
}
RISK_SIGS = {"exit"}


def _issuer(name: str) -> str:
    s = (name or "").replace("主動", "", 1)
    for i in ISSUERS:
        if s.startswith(i):
            return i
    return s[:2] or "?"


def etf_meta() -> dict[str, dict]:
    from .. import etfwatch
    out = {}
    for code, name, kind, cat, _inc in etfwatch.watch_tuples():
        if "債" in (cat or ""):
            continue
        out[code] = {"n": name, "k": "a" if kind == "active" else "p", "is": _issuer(name)}
    # 擴充 ETF（規模前段、只進籌碼雷達；collect.update_extra_etfs 維護）
    ext = (store.read_json("extra_etfs.json", {}) or {}).get("etfs") or {}
    for code, m in ext.items():
        if code in out or m.get("skip"):
            continue
        out[code] = {"n": m.get("n") or code, "k": m.get("k") or "p",
                     "is": _issuer(str(m.get("is") or "") + str(m.get("n") or "")) if not m.get("is")
                     else _issuer(str(m["is"])), "x": 1}
    return out


class Data:
    """把分片載入成「交易日曆對齊」的陣列。"""

    def __init__(self, long: bool = False):
        self.mkt = dict(store.load("mkt"))
        self.pos = store.load("pos")
        self.tdcc = store.load("tdcc")
        self.names = {**(store.read_json("names_mkt.json", {}) or {}),
                      **(store.read_json("names.json", {}) or {})}
        # Yahoo 歷史日線備援（只補官方分片沒有的日子；collect.backfill_yahoo 產）
        self.yh: dict[str, dict] = {}
        self.yh_m: dict[str, str] = {}
        from .collect import yh_codes
        for c in yh_codes():
            doc = store.read("yh", c) or {}
            if doc.get("q"):
                self.yh[c] = doc["q"]
                self.yh_m[c] = doc.get("m") or ""
        if long:    # 高股息提前卡位研究：Yahoo 五年日線（yhl）只補 yh 沒有的日子；其他策略不用 long，回測期間不變
            from .collect import yhl_codes
            for c in yhl_codes():
                doc = store.read("yhl", c) or {}
                if doc.get("q"):
                    self.yh[c] = {**doc["q"], **(self.yh.get(c) or {})}
                    self.yh_m.setdefault(c, doc.get("m") or "")
        cal = set(d for d, doc in self.mkt.items() if doc.get("q_tw") or doc.get("q_tp"))
        cal |= {d for d, _ in self.pos}
        cal |= set((self.yh.get("TWII") or {}))
        self.cal = sorted(cal)
        self.ix = {d: i for i, d in enumerate(self.cal)}
        self.T = len(self.cal)
        # 海外／退回用報價：pos 分片裡揭露當下的收盤
        self.pos_px: dict[tuple[str, str], tuple] = {}
        for d, doc in self.pos:
            for ent in (doc.get("etf") or {}).values():
                for c, v in (ent.get("px") or {}).items():
                    if v and v[0]:
                        self.pos_px[(c, d)] = (float(v[0]), v[1])

    # —— 報價
    def quote(self, code: str, d: str):
        doc = self.mkt.get(d)
        if doc:
            for part in ("q_tw", "q_tp"):
                q = (doc.get(part) or {}).get(code)
                if q and q[3]:
                    return q
            if doc.get("q_tw") and doc.get("q_tp"):
                return None                       # 官方當日兩市齊全卻沒有此檔＝當天沒交易，不用備援
        y = (self.yh.get(code) or {}).get(d)
        if y and y[3]:
            return [y[0], y[1], y[2], y[3], y[4], None]     # Yahoo 無成交金額 → 均價退回收盤
        return None

    def price(self, code: str, d: str):
        """→ (均價, 收盤)；台股優先官方價量，否則退回揭露當下收盤。"""
        q = self.quote(code, d)
        if q:
            vol, val = q[4], q[5]
            vwap = (val / vol) if vol and val else None
            return (vwap, q[3])
        p = self.pos_px.get((code, d))
        return (None, p[0]) if p else None

    def series(self, code: str) -> dict:
        T = self.T
        o, h, l, c, v, val = ([None] * T for _ in range(6))
        for i, d in enumerate(self.cal):
            q = self.quote(code, d)
            if q:
                o[i], h[i], l[i], c[i], v[i], val[i] = q[0], q[1], q[2], q[3], q[4], q[5]
            elif not LG.is_tw(code):
                p = self.pos_px.get((code, d))
                if p:
                    c[i] = p[0]
        return {"o": o, "h": h, "l": l, "c": c, "v": v, "val": val}

    def chips(self, code: str) -> dict:
        T = self.T
        f, t, dl, mb, sb, lb, fp = ([None] * T for _ in range(7))
        for i, d in enumerate(self.cal):
            doc = self.mkt.get(d) or {}
            x = (doc.get("i_tw") or {}).get(code) or (doc.get("i_tp") or {}).get(code)
            if x:
                f[i], t[i], dl[i] = x[0], x[1], x[2]
            m = (doc.get("m_tw") or {}).get(code) or (doc.get("m_tp") or {}).get(code)
            if m:
                mb[i], sb[i] = m[0], m[1]
            b = (doc.get("l_tw") or {}).get(code)
            if b is not None:
                lb[i] = b
            q = (doc.get("x_tw") or {}).get(code)
            if q:
                fp[i] = q[0]
        return {"f": f, "t": t, "d": dl, "mb": mb, "sb": sb, "lb": lb, "fp": fp}

    def taiex_open(self) -> list:
        """加權指數開盤（Yahoo ^TWII；官方 MI_INDEX 只有收盤）。開盤進場的回測必須用它當基準起點。"""
        yi = self.yh.get("TWII") or {}
        return [(yi.get(d) or [None])[0] for d in self.cal]

    def taiex(self) -> list:
        yi = self.yh.get("TWII") or {}
        return [((self.mkt.get(d) or {}).get("idx") or {}).get("taiex") or (yi.get(d) or [None] * 4)[3]
                for d in self.cal]

    def latest(self, part: str) -> tuple[str | None, dict]:
        for d in reversed(sorted(self.mkt)):
            p = (self.mkt[d] or {}).get(part)
            if p:
                return d, p
        return None, {}

    def issued(self) -> dict[str, int]:
        out: dict[str, int] = {}
        _, tp = self.latest("q_tp")
        for c, q in tp.items():
            if len(q) > 6 and q[6]:
                out[c] = q[6]
        _, xt = self.latest("x_tw")
        for c, q in xt.items():
            if q and len(q) > 1 and q[1]:
                out[c] = q[1]
        return out


# ── 小工具 ─────────────────────────────────────────────────────────

def _sum(xs, a, b):
    s, n = 0.0, 0
    for x in xs[max(a, 0):b + 1]:
        if x is not None:
            s += x
            n += 1
    return s if n else None


def _streak(xs, t) -> int:
    """t 往回連續同號天數（正＝連買、負＝連賣）；缺值即停。"""
    s = 0
    i = t
    while i >= 0 and xs[i] is not None and xs[i] != 0:
        if s == 0:
            s = 1 if xs[i] > 0 else -1
        elif (xs[i] > 0) != (s > 0):
            break
        else:
            s += 1 if s > 0 else -1
        i -= 1
    return s


def _r(x, n=2):
    return None if x is None else round(x, n)


def active_cost(held: list) -> tuple[float | None, int]:
    """主動成本＝主動 ETF「觀測期內新建倉」部位（品質 A）的平均成本，與納入的檔數。
    held＝[(ETF 屬性, Pos)]。舊部位（觀測起點前就持有）不知道真正買價——2026-10-14 查遍網路
    （投信官網、證交所、公會、財報投資明細）都沒有公布經理人成本，使用者定案「只算 7/27 後新買的」。
    缺價格的部位（成本 0）也不計，否則股數會把平均成本稀釋。"""
    sh = cost = 0.0
    n = 0
    for m, P in held:
        if m.get("k") == "a" and P.quality == "A" and P.shares > 0 and P.cost > 0:
            sh += P.priced
            cost += P.cost
            n += 1
    return (cost / sh if sh else None), n


def _lots(x, tw=True):
    if x is None:
        return None
    return round(x / 1000, 1) if tw else round(x)


# ── 主流程 ─────────────────────────────────────────────────────────

def run(data: Data | None = None, keep: dict | None = None) -> dict:
    """keep＝空 dict 時把中間物件留給呼叫端（每週改良回測 scripts/run_opt.py 用）：每日資料、訊號歷史、
    各策略完整交易、長線面板、v3 面板、五年加權指數。頁面輸出不受影響（完整交易一律在回傳前移除）。"""
    D = data or Data()
    ctxd = keep if keep is not None else {}                # 中間物件（策略健檢、影子版本、每週改良回測共用）
    meta = etf_meta()
    skip = {e for d, doc in D.pos for e in (doc.get("etf") or {}) if e not in meta}
    L = LG.build(D.pos, D.price, skip_etfs=skip, cal=D.ix)
    T = D.T
    if T == 0:
        return {"empty": True}

    # 台股權益型主動 ETF（台股權重 ≥70%）＝超配比較的分母
    last_h: dict[str, dict] = {}
    last_w: dict[str, dict] = {}
    for d, doc in D.pos:
        for etf, ent in (doc.get("etf") or {}).items():
            if etf in meta:
                last_h[etf] = {c: v[0] for c, v in (ent.get("h") or {}).items() if v and v[0]}
                last_w[etf] = {c: (v[1] or 0) for c, v in (ent.get("h") or {}).items() if v}
    for etf, w in last_w.items():
        tot = sum(w.values()) or 1
        meta[etf]["tw"] = sum(x for c, x in w.items() if LG.is_tw(c)) / tot >= 0.7
        meta[etf]["d"] = L.last_obs.get(etf)
        f = [v for (e, _d), v in L.flows.items() if e == etf]
        meta[etf]["f"] = _r(f[-1], 4) if f else None
    act_tw = [e for e, m in meta.items() if m["k"] == "a" and m.get("tw") and e in last_w]

    # 市值權重（台股普通股；分母＝全體上市櫃普通股市值）
    iss = D.issued()
    pxd, qtw = D.latest("q_tw")
    _, qtp = D.latest("q_tp")
    cap = {}
    for src in (qtw, qtp):
        for c, q in src.items():
            if LG.is_tw(c) and not c.startswith("00") and iss.get(c) and q[3]:
                cap[c] = q[3] * iss[c]
    cap_tot = sum(cap.values()) or None

    # 事件 → 交易日索引
    ev_by_code: dict[str, list] = defaultdict(list)
    for ev in L.events:
        if ev.date in D.ix:
            ev_by_code[ev.code].append(ev)

    # 宇宙：目前任一 ETF 持有 ＋ 近 20 個交易日內被出清者。
    # 擴充的被動檔不擴宇宙（006204 這類全市場 ETF 持有近千檔，首輪把頁面撐到 6.2MB）——
    # 它們只貢獻 ETF 面指標（合計持股、被動換股）；擴充的主動檔才帶入新個股。
    cur_codes = {c for e, h in last_h.items() for c in h
                 if not (meta.get(e) or {}).get("x") or (meta.get(e) or {}).get("k") == "a"}
    recent = set(D.cal[-20:])
    exited = {ev.code for ev in L.events if ev.kind == LG.EXIT and ev.date in recent}
    universe = sorted(cur_codes | exited)

    taiex = D.taiex()
    ind = {}
    try:
        from .. import stockmeta
        ind = stockmeta.industry_map()
    except Exception:                                     # noqa: BLE001
        pass
    tdcc_last = D.tdcc[-1][1].get("s", {}) if D.tdcc else {}
    tdcc_prev = D.tdcc[-2][1].get("s", {}) if len(D.tdcc) > 1 else {}

    # 主動 ETF 每日成本線：逐 (etf, code) 前推。只算觀測期內新建倉的部位（品質 A）——
    # 觀測起點前就持有的舊部位不知道真正買價（2026-10-14 使用者定案：舊部位不計）
    cost_line: dict[str, list] = {}
    state: dict[tuple, tuple] = {}
    act_set = {e for e, m in meta.items() if m["k"] == "a"}
    daily = L.daily_cost
    per_code_days: dict[str, list] = defaultdict(lambda: [None] * T)
    for i, d in enumerate(D.cal):
        for k, v in (daily.get(d) or {}).items():
            state[k] = v
        if not daily.get(d) and i > 0:
            continue
        agg: dict[str, list] = defaultdict(lambda: [0.0, 0.0])
        cnt: dict[str, int] = defaultdict(int)
        for (e, c), (s, cst, q) in state.items():
            if e in act_set and q == "A" and s > 0 and cst > 0:
                agg[c][0] += s
                agg[c][1] += cst
                cnt[c] += 1
        for c in set(agg) | set(cnt):
            s, cst = agg.get(c, (0.0, 0.0))
            per_code_days[c][i] = ((cst / s) if s else None, cnt.get(c, 0))
    act_n: dict[str, list] = {}
    for c, arr in per_code_days.items():
        last_v, last_n = None, 0
        out, outn = [], []
        for x in arr:
            if x is not None:
                last_v, last_n = x
            out.append(last_v)
            outn.append(last_n)
        cost_line[c] = out
        act_n[c] = outn

    rows, ser, sig_hist = [], {}, {}
    for code in universe:
        tw = LG.is_tw(code)
        S = D.series(code)
        C = D.chips(code) if tw else None
        evs = ev_by_code.get(code, [])

        # —— ETF 日序列
        conv_act = [0.0] * T
        raw_all = [0.0] * T
        add_iss = [set() for _ in range(T)]
        cut_iss = [set() for _ in range(T)]
        new_iss = [set() for _ in range(T)]
        strk = [0] * T
        for ev in evs:
            i = D.ix[ev.date]
            m = meta.get(ev.etf) or {}
            raw_all[i] += ev.raw
            if m.get("k") != "a":
                continue
            conv_act[i] += ev.conv if ev.kind != LG.EXIT else -ev.s0
            if ev.kind in (LG.ADD, LG.NEW):
                add_iss[i].add(m["is"])
            if ev.kind == LG.NEW:
                new_iss[i].add(m["is"])
            if ev.kind in (LG.CUT, LG.EXIT):
                cut_iss[i].add(m["is"])
            if ev.kind == LG.ADD and ev.streak >= 3:
                strk[i] = max(strk[i], ev.streak)

        c, h, v = S["c"], S["h"], S["v"]
        ma60 = ta.sma(c, 60)
        v20 = ta.sma(v, 20)
        cl = cost_line.get(code, [None] * T)
        an = act_n.get(code, [0] * T)

        def sig_at(t: int) -> list[str]:
            out = []
            w5 = range(max(t - 4, 0), t + 1)
            iss_add = set().union(*(add_iss[i] for i in w5))
            iss_cut = set().union(*(cut_iss[i] for i in w5))
            net5 = sum(conv_act[i] for i in w5)
            if len(iss_add) >= 3 and net5 > 0:
                out.append("cons")
            if new_iss[t]:
                n10 = set().union(*(new_iss[i] for i in range(max(t - 9, 0), t + 1)))
                if len(n10) >= 2:
                    out.append("new2")
            if strk[t] >= 3:
                out.append("strk")
            if len(iss_cut) >= 3 and net5 < 0:
                out.append("exit")
            if tw and c[t] and cl[t]:
                holders = an[t]
                was_above = any(c[i] and cl[i] and c[i] / cl[i] - 1 > 0.05
                                for i in range(max(t - 20, 0), t))
                net10 = sum(conv_act[i] for i in range(max(t - 9, 0), t + 1))
                if holders >= 2 and abs(c[t] / cl[t] - 1) <= 0.03 and was_above and net10 >= 0:
                    out.append("cost")
            if tw and C:
                t5 = _sum(C["t"], t - 4, t)
                mbn, mb0 = C["mb"][t], ta.last_at(C["mb"], max(t - 5, 0)) if t >= 5 else None
                if net5 > 0 and t5 and t5 > 0 and mbn is not None and mb0 and mbn < mb0:
                    out.append("reso")
                if _streak(C["t"], t) >= 3:
                    out.append("trst")
            if tw and c[t] and ma60[t] and v[t] and v20[t]:
                hw = [x for x in h[max(t - 20, 0):t] if x is not None]
                if len(hw) >= 15 and c[t] > max(hw) and v[t] >= 1.5 * v20[t] and c[t] > ma60[t]:
                    out.append("brk")
            return out

        hist = [sig_at(t) for t in range(T)]
        sig_hist[code] = hist
        last_t = T - 1
        # 今日訊號以「最新價量日」為準（揭露日可能比價量新一天）
        pt = max((i for i in range(T) if c[i] is not None), default=last_t) if tw else last_t
        today_sigs = sorted(set(hist[last_t]) | set(hist[pt]))

        # —— 持有明細
        hd = []
        tot_sh = 0.0
        held_pos = []
        wts_act = []
        for etf in sorted(meta):
            P = L.pos.get((etf, code))
            m = meta[etf]
            w = (last_w.get(etf) or {}).get(code, 0) or 0
            if m["k"] == "a" and m.get("tw"):
                wts_act.append((m["is"], w))
            if not P or P.shares <= 0:
                continue
            tot_sh += P.shares
            held_pos.append((m, P))
            known = P.quality == "A"          # 舊部位（B）成本不明：不計也不顯示（見 active_cost）
            conv5 = sum(ev.conv for ev in evs if ev.etf == etf and D.ix[ev.date] >= T - 5)
            held = None
            if P.first and P.first in D.ix:
                held = T - 1 - D.ix[P.first]
            px_now = ta.last(c)
            avg = P.avg if known else None
            pnl = (px_now / avg - 1) * 100 if px_now and avg else None
            hd.append([etf, _r(w), _lots(P.shares, tw), P.first, int(P.exact), held,
                       _r(avg), _r(pnl, 1), _lots(conv5, tw), P.last_kind, P.last_date,
                       (P.streak_add or -P.streak_cut), P.quality])
        exits = [[ev.etf, ev.date, _lots(ev.s0, tw)] for ev in evs
                 if ev.kind == LG.EXIT and ev.date in recent]

        px_now = ta.last(c)
        ci = max((i for i in range(T) if c[i] is not None), default=None)
        prev_c = ta.last_at(c, ci - 1) if ci else None
        chg = (px_now / prev_c - 1) * 100 if px_now and prev_c else None
        avg_v20 = ta.last(v20)
        act_cost, act_n_ = active_cost(held_pos)
        dev = (px_now / act_cost - 1) * 100 if px_now and act_cost else None
        mw = cap.get(code, 0) / cap_tot * 100 if cap_tot and code in cap else None
        iss_w: dict[str, list] = defaultdict(list)
        for i_, w in wts_act:
            iss_w[i_].append(w)
        aw = statistics.mean(w for _, w in wts_act) if wts_act else None
        n_ow = sum(1 for ws in iss_w.values() if mw is not None and statistics.mean(ws) > mw) \
            if mw is not None else None
        w5 = range(max(T - 5, 0), T)
        w10 = range(max(T - 10, 0), T)
        row = {
            "c": code, "n": D.names.get(code, code), "ind": ind.get(code),
            "m": _market(D, code, tw),
            "px": _r(px_now), "ch": _r(chg),
            "ne": len(hd), "na": sum(1 for r in hd if meta[r[0]]["k"] == "a"),
            "np": sum(1 for r in hd if meta[r[0]]["k"] == "p"),
            "ni": len({meta[r[0]]["is"] for r in hd}),
            "sh": _lots(tot_sh, tw),
            "hp": _r(tot_sh / iss[code] * 100, 2) if tw and iss.get(code) else None,
            "dx": _r(tot_sh / avg_v20, 1) if tw and avg_v20 else None,
            "r1": _lots(raw_all[-1], tw), "r5": _lots(sum(raw_all[i] for i in w5), tw),
            "r20": _lots(sum(raw_all[max(T - 20, 0):]), tw),
            "a1": _lots(conv_act[-1], tw), "a5": _lots(sum(conv_act[i] for i in w5), tw),
            "a5v": _r(sum(conv_act[i] for i in w5) * px_now / 1e8, 2) if tw and px_now else None,
            "a20": _lots(sum(conv_act[max(T - 20, 0):]), tw),
            "v5": _r(sum(raw_all[i] for i in w5) / (5 * avg_v20) * 100, 1) if tw and avg_v20 else None,
            "ia5": sorted(set().union(*(add_iss[i] for i in w5))),
            "ic5": sorted(set().union(*(cut_iss[i] for i in w5))),
            "nb10": sorted({ev.etf for ev in evs if ev.kind == LG.NEW and D.ix[ev.date] in w10
                            and meta.get(ev.etf, {}).get("k") == "a"}),
            "ex": exits,
            "cost": _r(act_cost), "dev": _r(dev, 1), "cn": act_n_,
            "mw": _r(mw, 3), "aw": _r(aw, 3), "ow": _r(aw - mw, 3) if aw is not None and mw is not None else None,
            "now": n_ow, "nact": len(iss_w),
            "sg": today_sigs, "hd": hd,
        }
        if tw and C:
            row.update(_chip_metrics(C, S, T, iss.get(code)))
            row.update(_ta_metrics(S, taiex, T))
            big = tdcc_last.get(code)
            bigp = tdcc_prev.get(code)
            if big:
                row["big"] = big[0]
                row["big4"] = big[1]
                row["bigd"] = _r(big[0] - bigp[0], 2) if bigp else None
                row["hold"] = big[2]
                row["holdd"] = (big[2] - bigp[2]) if bigp and big[2] and bigp[2] else None
        rows.append(row)
        ser[code] = _series_out(D, S, C, cl, conv_act, tw)

    # —— 投信動向：近 5 個交易日的真加減碼事件＋各投信超配最多的個股
    recent5 = set(D.cal[-5:])
    iev: dict[str, list] = defaultdict(list)
    for ev in L.events:
        m = meta.get(ev.etf) or {}
        if m.get("k") != "a" or ev.date not in recent5 or ev.kind == LG.HOLD:
            continue
        tw = LG.is_tw(ev.code)
        iev[m["is"]].append([ev.date, ev.kind, ev.code, D.names.get(ev.code, ev.code), ev.etf,
                             _lots(ev.conv if ev.kind != LG.EXIT else -ev.s0, tw)])
    for k in iev:
        iev[k].sort(key=lambda x: (x[0], abs(x[5] or 0), x[2], x[4], x[1]), reverse=True)   # 同日同量依代號：每次建頁順序一樣
        iev[k] = iev[k][:300]       # 投信頁依股票彙整新建倉／加碼／減碼／出清檔數，截太短會少算（安聯 5 日就有 212 筆）
    mw_map = {r["c"]: r.get("mw") for r in rows}
    iss_w: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for etf in act_tw:
        for c2, w in (last_w.get(etf) or {}).items():
            iss_w[meta[etf]["is"]][c2].append(w or 0)
    iss_ow = {}
    for i_, mp in iss_w.items():
        n_etf = sum(1 for e in act_tw if meta[e]["is"] == i_)
        lst = []
        for c2, ws in mp.items():
            aw_ = sum(ws) / n_etf
            mw_ = mw_map.get(c2)
            if mw_ is not None:
                lst.append([c2, D.names.get(c2, c2), round(aw_, 2), mw_, round(aw_ - mw_, 2)])
        lst.sort(key=lambda x: -x[4])
        iss_ow[i_] = lst[:8]

    from . import backtest, indexes
    from .. import clock
    try:
        idx_out = indexes.run(D, L, meta, clock.today_tw())
    except Exception as e:                                # noqa: BLE001 —— 指數區塊失敗不拖垮整頁
        idx_out = {"err": f"{type(e).__name__}: {e}"}
    # 五年日線只載一次（約 6 秒）：高股息提前卡位研究、v3 策略、公司分析小表、大盤年線分組共用；失敗不影響其他區塊。
    # 資料包策略 P1–P7（packtest.run）不再每次建頁重算（2026-10-16）：頁面只用到長線 P6 對照列與不採用清單，
    # P1–P7 的成績在 docs/strategy_pack_plan.md，要重看就手動跑 packtest.summary(packtest.run(Data(long=True)), reg)
    DL, reg = None, None
    from . import packtest
    pack: dict = {"rows": [], "skipped": packtest.SKIPPED, "meta": {}}
    try:
        DL = Data(long=True)
        reg = packtest.regime_map(DL)
        ctxd.update({"DL_cal": list(DL.cal), "DL_taiex": DL.taiex(), "DL_taiex_open": DL.taiex_open()})
    except Exception as e:                                # noqa: BLE001
        pack = {"err": f"{type(e).__name__}: {e}"}
    # 高股息「依編製規則提前卡位」回測（2026-10-15）：約十幾秒
    try:
        from . import hdpre
        if isinstance(idx_out.get("hd"), dict):
            idx_out["hd"]["pre"] = hdpre.page_data(D=DL)
    except Exception as e:                                # noqa: BLE001
        if isinstance(idx_out.get("hd"), dict):
            idx_out["hd"]["pre"] = {"err": f"{type(e).__name__}: {e}"}
    # 回測方法 v3（2026-10-15；docs/backtest_v3_plan.md）：月營收驚喜、財報驚喜的本期 5 檔與前瞻；研究成績讀 bt3_research.json
    v3, v3ctx = {}, None
    if DL is not None:
        try:
            from . import v3live
            v3 = v3live.run(DL, D.names)
            v3ctx = v3.pop("_ctx", None)
        except Exception as e:                            # noqa: BLE001
            v3 = {"err": f"{type(e).__name__}: {e}"}
    # 公司分析（docs/lab_company_plan.md 第 3.4 節）：全市場每日小表（飆股特徵、估值、體質）→ page.build 另存 x9t.json
    mtab: dict = {}
    sx: dict = {}
    wl: dict = {}
    ind_tab: dict = {}
    if DL is not None:
        try:
            from . import company
            from . import superx as SX
            res = SX.load_res()                           # 飆股研究結果（scripts/run_super.py）；沒有就只有小表
            mtab = company.market_table(DL, rules=[c for _, c in SX.live_rules(res)])
            hits = mtab.pop("hits", {})
            watch = mtab.pop("watch", {})
            lay_today = mtab.pop("layer", {})
            ind_tab = mtab.pop("ind", {})                 # 產業比較（docs/lab_forward_plan.md）→ 頁面 D.ind
            mcols, mrows = mtab.get("cols") or [], mtab.get("rows") or {}     # 別叫 rows：後面頁面列表用這個名字
            nm_all = {**company.names(), **(D.names or {})}
            sx = SX.page_data(res, hits, {c: dict(zip(mcols, mrows[c])) for c in hits if c in mrows}, nm_all)
            if sx:
                sx["d"] = mtab.get("d")
            from . import watchlist as WL                 # 超級飆股觀察名單（tw-superstock-lab W1；只列名單與過去統計）
            wl = WL.page_data(WL.load_res(), watch, {c: dict(zip(mcols, mrows[c])) for c in watch if c in mrows}, nm_all)
            if wl:
                wl["d"] = mtab.get("d")
                from . import layer as LYR            # 第二層篩選（tw-superstock-lab W3）
                wl["lay"] = LYR.page_data(LYR.load_res(), lay_today)
                try:                                  # 法人預估一行小字（docs/lab_forward_plan.md；只顯示當參考）
                    from . import fcst
                    wl["fc"] = fcst.briefs(list(watch), {c: mrows[c][0] for c in watch if c in mrows}, company.fy_eps())
                except Exception as e:                # noqa: BLE001
                    print(f"[fcst] 飆股段法人預估失敗：{type(e).__name__}: {e}")
        except Exception as e:                            # noqa: BLE001
            mtab = {"err": f"{type(e).__name__}: {e}"}
    DL = None
    stats = backtest.signal_stats(D, sig_hist, taiex)
    from . import strategy
    try:
        strat = strategy.run(D, sig_hist, L, meta, taiex, D.names, reg=reg)
    except Exception as e:                                # noqa: BLE001
        strat = {"err": f"{type(e).__name__}: {e}"}
    # 長線：投信動能成長股（回測＋今日篩選）
    try:
        from . import growth
        P = growth.Panel(D)
        gbt = growth.backtest(P, growth.load_rev_hist())
        gbt.pop("cand_codes", None)
        rv = store.load("rev", last=1)
        rev_now = {c: (x[1], x[2]) for c, x in (rv[-1][1].get("s") or {}).items()} if rv else {}
        new20: dict[str, set] = defaultdict(set)
        cut20 = set(D.cal[-20:])
        for ev in L.events:
            m = meta.get(ev.etf) or {}
            if ev.kind == LG.NEW and m.get("k") == "a" and ev.date in cut20:
                new20[ev.code].add(m["is"])
        etf2 = {c for c, s_ in new20.items() if len(s_) >= 2}
        rev_shards = {d: {c: x for c, x in (doc.get("s") or {}).items()} for d, doc in store.load("rev")}
        grow = {"bt": gbt, "screen": growth.screen_now(P, rev_now, etf2),
                "rev_ym": rv[-1][0] if rv else None, "n_uni": len(P.codes),
                "s5": growth.s5_trades(P, growth.load_rev_hist(), rev_shards, taiex, D.taiex_open(), reg=reg,
                                       eps=_eps_safe())}
        ctxd.update({"gP": P, "rev_shards": rev_shards})
    except Exception as e:                                # noqa: BLE001
        grow = {"err": f"{type(e).__name__}: {e}"}
    full = _take_full(strat, grow, v3)                     # 各策略完整交易（不進頁面）
    ctxd.update({"D": D, "sig_hist": sig_hist, "L": L, "meta": meta, "taiex": taiex, "reg": reg, "v3ctx": v3ctx,
                 "full": full, "v3": v3})
    # 策略健檢與改良（docs/lab_selfopt_plan.md）：燈號、持有中百分位、拆解；每週改良結果與影子版本前瞻。失敗不影響其他區塊
    try:
        from . import health
        hl = health.daily(full, v3, D, v3ctx, reg)
    except Exception as e:                                # noqa: BLE001
        hl = {"err": f"{type(e).__name__}: {e}"}
    try:
        from . import optim
        opt = optim.page_data(ctxd)
    except Exception as e:                                # noqa: BLE001
        opt = {"err": f"{type(e).__name__}: {e}"}
    v3ex = {}
    if v3ctx is not None:                                 # 既有策略改用 v3 評級（要等 strat、grow 算完）
        try:
            from . import v3live
            v3ex = v3live.existing(v3ctx, strat, grow)
        except Exception as e:                            # noqa: BLE001
            v3ex = {"err": f"{type(e).__name__}: {e}"}
    v3ctx = None
    iss_stats = backtest.issuer_stats(D, L, meta, taiex)
    # 策略頁 v2：評級＋本期推薦／觀察／出場清單（2026-10-15）
    try:
        from . import advice
        adv = advice.build({"rows": rows, "strat": strat, "grow": grow, "idx": idx_out, "stats": stats,
                            "pack": pack, "v3": v3, "v3ex": v3ex, "last": D.cal[-1] if D.cal else None})
    except Exception as e:                                # noqa: BLE001
        adv = {"err": f"{type(e).__name__}: {e}"}
    asof = {
        "pos": D.pos[-1][0] if D.pos else None,
        "px": pxd,
        "chip": D.latest("i_tw")[0],
        "margin": D.latest("m_tw")[0],
        "sbl": D.latest("l_tw")[0],
        "tdcc": D.tdcc[-1][0] if D.tdcc else None,
        "start": D.pos[0][0] if D.pos else None,
        "cal": len(D.cal),
    }
    return {"asof": asof, "etfs": meta, "rows": rows, "ser": ser,
            "sigdef": {k: list(v) for k, v in SIG_DEF.items()}, "risk": sorted(RISK_SIGS),
            "stats": stats, "iss": iss_stats, "iev": dict(iev), "iow": iss_ow,
            "idx": idx_out, "strat": strat, "grow": grow, "adv": adv, "hl": hl, "opt": opt,
            "mtab": mtab, "sx": sx, "wl": wl, "ind": ind_tab, "dates": D.cal[-CHART_N:]}


def _take_full(strat: dict, grow: dict, v3: dict | None = None) -> dict:
    """從策略結果取出完整交易並移除（strategy.run 的 _all、臺灣50 的 _V、長線的 _recs、v3 策略的 _hl）：
    頁面只放截短的清單。→ {"s1": [...], "s3": [...]（提前卡位版）, "s5": [...], "hl": {v3 鍵: 前瞻逐筆與每期一批}}"""
    out: dict = {"hl": {}}
    for k, x in (v3 or {}).items():
        if isinstance(x, dict) and "_hl" in x:
            out["hl"][k] = x.pop("_hl")
    for s in (strat or {}).get("list") or []:
        if not isinstance(s, dict):
            continue
        a = s.pop("_all", None)
        if a is not None:
            out[s.get("key")] = a
        V = s.pop("_V", None)
        if V is not None:
            out["s3"] = V.get("early") or []
    s5 = (grow or {}).get("s5") if isinstance(grow, dict) else None
    if isinstance(s5, dict):
        r = s5.pop("_recs", None)
        if r is not None:
            out["s5"] = r
    return out


def _eps_safe() -> dict:
    try:
        from .packtest import load_eps
        return load_eps()
    except Exception:                                     # noqa: BLE001
        return {}


CHART_N = 130
CHIP_N = 60


def _market(D: Data, code: str, tw: bool) -> str:
    if not tw:
        return "os"
    for d in reversed(D.cal[-10:]):
        doc = D.mkt.get(d) or {}
        if code in (doc.get("q_tw") or {}):
            return "tw"
        if code in (doc.get("q_tp") or {}):
            return "tp"
    return "tw"


def _chip_metrics(C: dict, S: dict, T: int, issued: int | None) -> dict:
    t = T - 1
    f, tr, dl, mb, sb, lb, fp = C["f"], C["t"], C["d"], C["mb"], C["sb"], C["lb"], C["fp"]
    vwap = [(val / v) if v and val else None for v, val in zip(S["v"], S["val"])]

    def cost60(xs):
        num = den = 0.0
        for i in range(max(T - 60, 0), T):
            if xs[i] and xs[i] > 0 and vwap[i]:
                num += xs[i] * vwap[i]
                den += xs[i]
        return num / den if den else None

    mb_now = ta.last(mb)
    mb5 = ta.last_at(mb, max(t - 5, 0)) if T > 5 else None
    mb20 = ta.last_at(mb, max(t - 20, 0)) if T > 20 else None
    sb_now = ta.last(sb)
    lb_now = ta.last(lb)
    lb5 = ta.last_at(lb, max(t - 5, 0)) if T > 5 else None
    fp_now = ta.last(fp)
    fp20 = ta.last_at(fp, max(t - 20, 0)) if T > 20 else None
    lt = max((i for i in range(T) if tr[i] is not None), default=t)
    return {
        "f1": _lots(f[lt]), "f5": _lots(_sum(f, lt - 4, lt)), "f20": _lots(_sum(f, lt - 19, lt)),
        "t1": _lots(tr[lt]), "t5": _lots(_sum(tr, lt - 4, lt)), "t20": _lots(_sum(tr, lt - 19, lt)),
        "d5": _lots(_sum(dl, lt - 4, lt)),
        "fs": _streak(f, lt), "ts": _streak(tr, lt),
        "tc": _r(cost60(tr)), "fc": _r(cost60(f)),
        "t20p": _r(_sum(tr, lt - 19, lt) / issued * 100, 3) if issued and _sum(tr, lt - 19, lt) else None,
        "fp": _r(fp_now), "fpd": _r(fp_now - fp20, 2) if fp_now is not None and fp20 is not None else None,
        "mb": mb_now, "mb5": _r((mb_now / mb5 - 1) * 100, 1) if mb_now is not None and mb5 else None,
        "mb20": _r((mb_now / mb20 - 1) * 100, 1) if mb_now is not None and mb20 else None,
        "sb": sb_now, "sr": _r(sb_now / mb_now * 100, 1) if sb_now is not None and mb_now else None,
        "lb": _lots(lb_now), "lb5": _lots(lb_now - lb5) if lb_now is not None and lb5 is not None else None,
    }


def _ta_metrics(S: dict, taiex: list, T: int) -> dict:
    c, h, l, v, val = S["c"], S["h"], S["l"], S["v"], S["val"]
    if ta.last(c) is None:
        return {}
    ma = {n: ta.last(ta.sma(c, n)) for n in (5, 10, 20, 60, 120, 240)}
    px = ta.last(c)
    t = max(i for i in range(T) if c[i] is not None)
    v20 = ta.last(ta.sma(v, 20))
    K, Dd = ta.kd(h, l, c)
    rs = ta.last(ta.rsi(c))
    dif, dea, hist = ta.macd(c)
    hs = [x for x in hist[max(t - 3, 0):t + 1] if x is not None]
    cross = 0
    if len(hs) >= 2:
        if hs[-1] > 0 >= min(hs[:-1]):
            cross = 1
        elif hs[-1] < 0 <= max(hs[:-1]):
            cross = -1
    hw20 = [x for x in h[max(t - 20, 0):t] if x is not None]
    hw60 = [x for x in h[max(t - 60, 0):t] if x is not None]
    lw20 = [x for x in l[max(t - 20, 0):t] if x is not None]
    hi = [x for x in h[max(t - 250, 0):t + 1] if x is not None]
    lo = [x for x in l[max(t - 250, 0):t + 1] if x is not None]
    p52 = (px - min(lo)) / (max(hi) - min(lo)) * 100 if hi and lo and max(hi) > min(lo) else None
    c20 = ta.last_at(c, t - 20) if t >= 20 else None
    i_now, i20 = ta.last_at(taiex, t), (ta.last_at(taiex, t - 20) if t >= 20 else None)
    rs20 = ((px / c20 - 1) - (i_now / i20 - 1)) * 100 if c20 and i_now and i20 else None
    a = ta.last(ta.atr(h, l, c))
    vv = [x for x in val[max(t - 19, 0):t + 1] if x]
    if ma[5] and ma[20] and ma[60]:
        align = "多頭" if px > ma[5] > ma[20] > ma[60] else "空頭" if px < ma[5] < ma[20] < ma[60] else "整理"
    else:
        align = None
    return {
        "ma": {str(k): _r(x) for k, x in ma.items() if x is not None}, "al": align,
        "b20": _r((px / ma[20] - 1) * 100, 1) if ma[20] else None,
        "b60": _r((px / ma[60] - 1) * 100, 1) if ma[60] else None,
        "vr": _r(v[t] / v20, 2) if v[t] and v20 else None,
        "k": _r(ta.last(K), 1), "d": _r(ta.last(Dd), 1), "rsi": _r(rs, 1),
        "mh": _r(hist[t], 3) if hist[t] is not None else None, "mx": cross,
        "h20": int(bool(hw20) and px > max(hw20)), "h60": int(bool(hw60) and px > max(hw60)),
        "l20": int(bool(lw20) and px < min(lw20)),
        "p52": _r(p52, 0), "n52": len(hi),
        "rs20": _r(rs20, 1), "atrp": _r(a / px * 100, 2) if a else None,
        "liq": _r(sum(vv) / len(vv) / 1e8, 2) if vv else None,
    }


def _series_out(D: Data, S: dict, C: dict | None, cl: list, qa: list, tw: bool) -> dict:
    n = CHART_N
    sl = slice(-n, None)

    def rr(xs, k=2):
        return [None if x is None else round(x, k) for x in xs[sl]]
    out = {"c": rr(S["c"])}
    if tw:
        out.update({"o": rr(S["o"]), "h": rr(S["h"]), "l": rr(S["l"]),
                    "v": [None if x is None else round(x / 1000) for x in S["v"][sl]]})
    out["ac"] = rr(cl)
    # 主動 ETF 每日真加減碼（已扣申贖；近 CHIP_N 日）。原「ETF 合計持股」走勢已拿掉：
    # ETF 陸續進資料集（回補、擴充檔納入）會讓合計持股憑空跳增，畫成走勢會誤導。
    if any(qa[-CHIP_N:]):
        out["qa"] = [round(x / 1000) if tw else round(x) for x in qa[-CHIP_N:]]
    if C:
        m = CHIP_N
        for k in ("f", "t", "d"):
            out["q" + k] = [None if x is None else round(x / 1000) for x in C[k][-m:]]
        out["mb"] = C["mb"][-m:]
        out["sb"] = C["sb"][-m:]
    return out
