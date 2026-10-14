"""籌碼雷達：長線「投信動能成長股」篩選與回測（2026-10-14 使用者：「更為長期波段……利用投信加入持股
做完篩選找到新一波的動能成長股，有超過 100% 的潛在報酬」）。

四關（每月底篩一次；現況每天篩）：
  1 投信關：投信 20 日買超 ≥ 股本 0.5% 且 20 天中 ≥12 天買超（官方三大法人；涵蓋全部投信基金）
           ——即時篩選另認「主動 ETF 20 日內 ≥2 家投信新建倉」（持股史只到 2026-07，回測不用）
  2 成長關：最新可得月營收年增 ≥20% 且累計年增 ≥15%（營收次月 10 日前公布 → 11 日起才算可得）
  3 動能關：收盤 > MA60 > MA120、MA60 較 20 日前上揚、距 120 日高點 20% 內、比 120 日低點高 30% 以上、
           近 120 日報酬在全宇宙前 30%
  4 空間關：市值 50～1,500 億、20 日均成交值 ≥1 億
出場（回測的「照規則操作」）：初始停損 −10%；曾漲 30% 後停損拉到成本；之後收盤跌破 MA60 出場；最長 250 日。

口徑：進場＝篩選日隔日開盤；「翻倍」＝進場後 N 個交易日內最高價曾達進場價 2 倍（是否抱得住另看照規則操作的報酬）。
限制：宇宙只有現存上市櫃股（下市股不在 → 倖存者偏差、結果偏樂觀）；兩年資料大致是多頭；發行股數用最新值。
"""
from __future__ import annotations

import statistics

from . import ta

CAP_MIN, CAP_MAX = 50e8, 1500e8
LIQ_MIN = 1e8
TRUST_PCT, TRUST_DAYS = 0.005, 12
H6, H12 = 120, 250


def _universe(D, issued: dict) -> list[str]:
    from .collect import yh_codes
    codes = set(yh_codes()) - {"TWII"}
    for d in D.cal[-5:]:
        doc = D.mkt.get(d) or {}
        codes |= set(doc.get("q_tw") or {}) | set(doc.get("q_tp") or {})
    return sorted(c for c in codes if len(c) == 4 and c.isdigit() and not c.startswith("00")
                  and c in issued)


def _month_ends(cal: list[str]) -> list[int]:
    out = []
    for i in range(len(cal) - 1):
        if cal[i][:7] != cal[i + 1][:7]:
            out.append(i)
    return out


def _rev_avail(rev: dict, d: str):
    """篩選日 d 可得的最新月營收 → (年增, 累計年增) 或 None。rev＝{YYYY-MM: 營收}。"""
    if not rev:
        return None
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    back = 1 if day >= 11 else 2
    m -= back
    while m <= 0:
        m += 12
        y -= 1
    key = f"{y:04d}-{m:02d}"
    prev = f"{y - 1:04d}-{m:02d}"
    if key not in rev or prev not in rev or not rev[prev]:
        return None
    yoy = rev[key] / rev[prev] - 1
    cur = sum(rev.get(f"{y:04d}-{k:02d}", 0) for k in range(1, m + 1))
    old = sum(rev.get(f"{y - 1:04d}-{k:02d}", 0) for k in range(1, m + 1))
    return yoy, (cur / old - 1 if old else None)


def load_rev_hist() -> dict[str, dict]:
    from . import store
    d = store.LAB / "revh"
    out = {}
    if d.exists():
        for p in d.glob("*.json.gz"):
            doc = store.read("revh", p.name.split(".json")[0]) or {}
            if doc.get("r"):
                out[p.name.split(".json")[0]] = doc["r"]
    return out


class Panel:
    """每檔與日曆對齊的陣列（價量、均線、投信、市值、成交值）。"""

    def __init__(self, D):
        self.D = D
        self.iss = D.issued()
        self.codes = _universe(D, self.iss)
        self.T = D.T
        self.s, self.ma60, self.ma120, self.trust, self.val = {}, {}, {}, {}, {}
        for c in self.codes:
            S = D.series(c)
            if sum(1 for x in S["c"] if x) < 130:
                continue
            self.s[c] = S
            self.ma60[c] = ta.sma(S["c"], 60)
            self.ma120[c] = ta.sma(S["c"], 120)
            self.trust[c] = D.chips(c)["t"]
            self.val[c] = [(vl if vl else (v * cl if v and cl else None))
                           for v, cl, vl in zip(S["v"], S["c"], S["val"])]
        self.codes = sorted(self.s)

    def trust_cov(self, t: int) -> int:
        """t 往回 20 日有投信資料的天數（看歷史回補到哪裡）。"""
        return sum(1 for i in range(max(t - 19, 0), t + 1)
                   if any(self.trust[c][i] is not None for c in self.codes[:50]))

    def factors(self, c: str, t: int, ret120_rank: dict) -> dict | None:
        S = self.s[c]
        cl = S["c"][t]
        if not cl:
            return None
        cap = cl * self.iss[c]
        vals = [x for x in self.val[c][max(t - 19, 0):t + 1] if x]
        liq = sum(vals) / len(vals) if vals else None
        tr = [x for x in self.trust[c][max(t - 19, 0):t + 1] if x is not None]
        t20 = sum(tr) if tr else None
        tdays = sum(1 for x in tr if x > 0)
        m60, m120 = self.ma60[c][t], self.ma120[c][t]
        m60p = self.ma60[c][t - 20] if t >= 20 else None
        hi = [x for x in S["h"][max(t - 119, 0):t + 1] if x] or [x for x in S["c"][max(t - 119, 0):t + 1] if x]
        lo = [x for x in S["l"][max(t - 119, 0):t + 1] if x] or hi
        f = {
            "cap": cap, "liq": liq,
            "trust": (t20 / self.iss[c]) if t20 is not None else None, "tdays": tdays if tr else None,
            "mom_ma": bool(m60 and m120 and cl > m60 > m120),
            "mom_up": bool(m60 and m60p and m60 > m60p),
            "near_hi": bool(hi and cl >= 0.8 * max(hi)),
            "off_lo": bool(lo and cl >= 1.3 * min(lo)),
            "rs": ret120_rank.get(c),
        }
        f["g_space"] = CAP_MIN <= cap <= CAP_MAX and (liq or 0) >= LIQ_MIN
        f["g_mom"] = f["mom_ma"] and f["mom_up"] and f["near_hi"] and f["off_lo"] and (f["rs"] or 0) >= 0.7
        f["g_trust"] = (f["trust"] or 0) >= TRUST_PCT and (f["tdays"] or 0) >= TRUST_DAYS
        return f

    def rs_rank(self, t: int) -> dict:
        rets = {}
        for c in self.codes:
            S = self.s[c]["c"]
            a = ta.last_at(S, t - 120) if t >= 120 else None
            if a and S[t]:
                rets[c] = S[t] / a - 1
        order = sorted(rets, key=lambda c: rets[c])
        n = len(order)
        return {c: (i + 1) / n for i, c in enumerate(order)}

    def outcome(self, c: str, t: int) -> dict | None:
        """篩選日 t → t+1 開盤進場：6／12 個月內最高曾漲幅、期末報酬、照規則操作的報酬。"""
        S = self.s[c]
        T = self.T
        if t + 1 >= T or not S["o"][t + 1]:
            return None
        e = S["o"][t + 1]
        out = {"entry": e}
        for key, h in (("6", H6), ("12", H12)):
            j = min(t + h, T - 1)
            hs = [x for x in S["h"][t + 1:j + 1] if x] or [x for x in S["c"][t + 1:j + 1] if x]
            if not hs:
                continue
            out["pk" + key] = max(hs) / e - 1
            out["full" + key] = (t + h) < T          # 前瞻期是否完整
            endp = ta.last_at(S["c"], j)
            out["end" + key] = endp / e - 1 if endp else None
        # 照規則操作
        stop = e * 0.9
        be = False
        exit_i = None
        for i in range(t + 1, min(t + H12, T - 1) + 1):
            cl = S["c"][i]
            if not cl:
                continue
            if not be and (S["h"][i] or cl) >= e * 1.3:
                be = True
                stop = max(stop, e)
            m60 = self.ma60[c][i]
            if cl < stop or (be and m60 and cl < m60):
                exit_i = i
                break
        if exit_i is None:
            exit_i = max(i for i in range(t + 1, min(t + H12, T - 1) + 1))
            out["open"] = exit_i >= T - 1
        out["rule"] = S["c"][exit_i] / e - 1 - 0.00585 if S["c"][exit_i] else None
        out["held"] = exit_i - t
        return out


def _summ(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    def rate(k, full):
        xs = [r for r in rows if r.get(full)]
        return (round(sum(1 for r in xs if r.get(k, -1) >= 1.0) / len(xs) * 100, 1), len(xs)) if xs else (None, 0)
    def avg(k, full=None):
        xs = [r[k] for r in rows if r.get(k) is not None and (full is None or r.get(full))]
        return (round(statistics.mean(xs) * 100, 1), round(statistics.median(xs) * 100, 1)) if xs else (None, None)
    rule = [r["rule"] for r in rows if r.get("rule") is not None]
    wins = [x for x in rule if x > 0]
    loss = [x for x in rule if x <= 0]
    return {"n": len(rows),
            "dbl6": rate("pk6", "full6"), "dbl12": rate("pk12", "full12"),
            "end6": avg("end6", "full6"), "end12": avg("end12", "full12"),
            "rule": avg("rule"), "rule_w": round(len(wins) / len(rule) * 100) if rule else None,
            "rule_aw": round(statistics.mean(wins) * 100, 1) if wins else None,
            "rule_al": round(statistics.mean(loss) * 100, 1) if loss else None,
            "rule_big": round(sum(1 for x in rule if x >= 1.0) / len(rule) * 100, 1) if rule else None}


EXITS = {
    # 2026-10-14 首輪回測：原規則（−10%、+30% 保本、破 60 日線）把 6 個月持有的 +80% 砍成 +33%、中位數 −4%
    # ——動能股正常回檔就被洗出場。保留原規則當對照，其餘為放寬版本；頁面並列，不只報最好的那個。
    "hold6": {"lbl": "持有 6 個月（−25% 停損）", "init": 0.25, "maxd": H6},
    "trail30": {"lbl": "−20% 停損・高點回落 30% 出", "init": 0.20, "trail": 0.30},
    "ma120": {"lbl": "−20% 停損・破 120 日線出", "init": 0.20, "ma": 120},
    "orig": {"lbl": "原規則：−10%・+30% 保本・破 60 日線", "init": 0.10, "be": 0.30, "ma": 60},
}


def simulate(P: Panel, c: str, t: int, *, init=0.10, trail=None, ma=None, be=None, maxd=H12, lbl=None) -> dict | None:
    S = P.s[c]
    T = P.T
    if t + 1 >= T or not S["o"][t + 1]:
        return None
    e = S["o"][t + 1]
    stop = e * (1 - init) if init else 0.0
    peak = e
    xi = None
    last = min(t + maxd, T - 1)
    for i in range(t + 1, last + 1):
        x = S["c"][i]
        if not x:
            continue
        peak = max(peak, x)
        if be and peak >= e * (1 + be):
            stop = max(stop, e)
        if trail:
            stop = max(stop, peak * (1 - trail))
        m = P.ma60[c][i] if ma == 60 else P.ma120[c][i] if ma == 120 else None
        if x < stop or (m and x < m):
            xi = i
            break
    if xi is None:
        xi = max((i for i in range(t + 1, last + 1) if S["c"][i]), default=None)
        if xi is None:
            return None
    return {"r": S["c"][xi] / e - 1 - 0.00585, "d": xi - t, "full": t + H6 < T}


def _exit_stats(rs: list[dict]) -> dict:
    r = [x["r"] for x in rs if x and x["full"]]
    if not r:
        return {"n": 0}
    w = [x for x in r if x > 0]
    lo = [x for x in r if x <= 0]
    return {"n": len(r), "avg": round(statistics.mean(r) * 100, 1), "med": round(statistics.median(r) * 100, 1),
            "win": round(len(w) / len(r) * 100), "aw": round(statistics.mean(w) * 100, 1) if w else None,
            "al": round(statistics.mean(lo) * 100, 1) if lo else None,
            "dbl": round(sum(1 for x in r if x >= 1) / len(r) * 100, 1),
            "days": round(statistics.mean(x["d"] for x in rs if x and x["full"]))}


def backtest(P: Panel, rev: dict) -> dict:
    """每月底篩選：基準（空間關）／動能／投信／投信＋動能／四關全過，各組結果。"""
    groups = {k: [] for k in ("base", "mom", "trust", "trust_mom", "all4")}
    months = []
    for t in _month_ends(P.D.cal):
        if t < 125 or P.trust_cov(t) < 15:                # 均線／投信資料不足的月份不算
            continue
        months.append(P.D.cal[t])
        rk = P.rs_rank(t)
        for c in P.codes:
            f = P.factors(c, t, rk)
            if not f or not f["g_space"]:
                continue
            o = P.outcome(c, t)
            if not o:
                continue
            o["c"], o["d"] = c, P.D.cal[t]
            groups["base"].append(o)
            if f["g_mom"]:
                groups["mom"].append(o)
            if f["g_trust"]:
                groups["trust"].append(o)
            if f["g_mom"] and f["g_trust"]:
                groups["trust_mom"].append(o)
                rv = _rev_avail(rev.get(c) or {}, P.D.cal[t])
                if rv and rv[0] >= 0.2 and (rv[1] or 0) >= 0.15:
                    groups["all4"].append(o)
    res = {k: _summ(v) for k, v in groups.items()}
    picks = sorted(groups["all4"] or groups["trust_mom"], key=lambda r: -(r.get("pk12") or r.get("pk6") or 0))
    # 去重：同一檔前一筆進場 120 個交易日內又被篩出 → 不重複計（避免連續幾個月同一檔灌樣本）
    dedup: dict[str, list] = {}
    for k in ("base", "mom", "trust_mom", "all4"):
        seen: dict[str, int] = {}
        lst = []
        for o in sorted(groups[k], key=lambda o: o["d"]):
            t = P.D.ix[o["d"]]
            if t - seen.get(o["c"], -999) > H6:
                lst.append((o["c"], t))
                seen[o["c"]] = t
        dedup[k] = lst
    res["exits"] = {k: {ek: _exit_stats([simulate(P, c, t, **ev) for c, t in lst])
                        for ek, ev in EXITS.items()} for k, lst in dedup.items()}
    res["exit_lbl"] = {k: v["lbl"] for k, v in EXITS.items()}
    res["months"] = months
    res["top"] = [[r["c"], P.D.names.get(r["c"], r["c"]), r["d"],
                   round((r.get("pk12") or r.get("pk6") or 0) * 100), None if r.get("rule") is None
                   else round(r["rule"] * 100, 1)] for r in picks[:15]]
    res["cand_codes"] = sorted({r["c"] for r in groups["trust_mom"]})
    return res


def screen_now(P: Panel, rev_now: dict, etf_new2: set[str]) -> list[dict]:
    """今日篩選：四關逐條結果（投信關另認主動 ETF 多家新建倉）。"""
    t = max(i for i in range(P.T) if any(P.s[c]["c"][i] for c in P.codes[:30]))
    rk = P.rs_rank(t)
    out = []
    for c in P.codes:
        f = P.factors(c, t, rk)
        if not f or not f["g_space"]:
            continue
        g_trust = f["g_trust"] or c in etf_new2
        rv = rev_now.get(c)
        g_grow = bool(rv and rv[0] is not None and rv[0] >= 20 and (rv[1] or 0) >= 15)
        n_pass = sum([g_trust, g_grow, f["g_mom"]])
        if n_pass < 2:
            continue
        out.append({"c": c, "n": P.D.names.get(c, c), "pass": n_pass == 3,
                    "trust": None if f["trust"] is None else round(f["trust"] * 100, 2), "tdays": f["tdays"],
                    "etf2": c in etf_new2, "g_trust": g_trust,
                    "yoy": None if not rv else rv[0], "cyoy": None if not rv else rv[1], "g_grow": g_grow,
                    "g_mom": f["g_mom"], "rs": None if f["rs"] is None else round(f["rs"] * 100),
                    "near": f["near_hi"], "cap": round(f["cap"] / 1e8), "liq": round((f["liq"] or 0) / 1e8, 1)})
    out.sort(key=lambda r: (not r["pass"], -(r["rs"] or 0)))
    return out[:60]
