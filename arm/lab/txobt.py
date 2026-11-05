"""台指選擇權日資料回測：O2 大事件前買跨式、O3 已驗證訊號改買買權（txospec VER 1；docs/lab_txo_plan.md 第 16、18 節）。

規格在 arm/lab/txospec.py（常數）與規劃第 18.2 節（看任何成績之前寫定的實作細節），這裡照做、不改：
  · 交易日＝日行情裡有資料的日子（2002 起）；價平用的收盤指數＝heatbubble.taiex_daily()（含週六補班日）。
  · 價格＝收盤價，沒有成交（空或 0）用結算價；兩個都沒有那筆不做。
  · 成本＝txospec.side_cost（手續費＋期交稅＋1 檔滑價，每口每邊）；判定用兩倍成本。
  · 口數＝floor(帳戶 × 上限 ÷ 一組的權利金與一邊成本)；帳戶＝ACCOUNT＋已實現損益；一天、一個月停損照 txospec（每條各自一個帳戶）。
  · O2：事件日（美國日期）台股休市那一次不做；出場＝下一個交易日收盤；到期日晚於出場日的最近一批；價平＝離收盤指數最近、
    買權賣權都有價格的履約價（一樣近取低的）。不貴過濾＝價平跨式結算價反推的隱含波動率，比過去 250 個有值的交易日裡
    低於它的比例 < IV_PCT 才做（不到 250 個不做）。
  · O3：rare_research.json 台股 lnypre、santa 的進出場日；到期日比出場日至少晚 O3_BUFFER 個交易日的最近月選，價平買權。
  · 打亂測試：O2 每個事件換成同一個月隨機的非事件交易日、O3 換成同一年隨機進場日（持有天數相同），規則照舊，PLACEBO_N 次。
本模組只讀資料、只算，不抓任何東西。
"""
from __future__ import annotations

import gzip
import json
import math
import random
from bisect import bisect_right
from datetime import date, timedelta
from pathlib import Path

from . import txocalc as C
from . import txospec as S

VER = 1
ROOT = Path(__file__).resolve().parents[2]
TRADING_YEAR = 252
XD_MAX_DAYS = 200          # 只留到期日在 200 個日曆天以內的批（O3 最遠要到出場後 10 個交易日的月選）


# ── 資料 ──────────────────────────────────────────────────────────────────────

def _px(c, s):
    if c:
        return float(c)
    if s:
        return float(s)
    return None


def load_book(root: Path) -> tuple[list[str], dict]:
    """資料分支 day/*.json.gz → (交易日清單, {日: {到期別: (到期日, {履約價: [C收, C結, P收, P結]})}})。"""
    from . import txodata as T
    book: dict[str, dict] = {}
    for f in sorted((Path(root) / "day").glob("*.json.gz")):
        doc = json.loads(gzip.decompress(f.read_bytes()))
        ci = {c: i for i, c in enumerate(doc["cols"])}
        for r in doc["rows"]:
            d, exp = r[ci["d"]], r[ci["exp"]]
            xd = r[ci["xd"]] or T.exp_date(exp).isoformat()
            if xd < d or (date.fromisoformat(xd) - date.fromisoformat(d)).days > XD_MAX_DAYS:
                continue
            e = book.setdefault(d, {}).setdefault(exp, (xd, {}))
            q = e[1].setdefault(r[ci["k"]], [None, None, None, None])
            j = 0 if r[ci["cp"]] == "C" else 2
            q[j], q[j + 1] = r[ci["c"]], r[ci["s"]]
    return sorted(book), book


def load_close() -> dict[str, float]:
    """加權指數收盤：heatbubble.taiex_daily()（少見策略、總經策略用的同一份；含週六補班日）。
    第一輪用 data/lab/heat/taiex.json.gz，少了 24 個週六補班日與 4 個平日，2026-11-05 改（規劃第 18.3 節）。"""
    from . import heatbubble as BB
    return {k: float(v) for k, v in BB.taiex_daily().items() if v}


class Mkt:
    """交易日、收盤指數、選擇權價格的查詢。"""

    def __init__(self, days: list[str], book: dict, close: dict[str, float]):
        self.days = [d for d in days if d in close]
        self.ix = {d: i for i, d in enumerate(self.days)}
        self.book = book
        self.close = close

    def next(self, d: str) -> str | None:
        i = self.ix.get(d)
        return self.days[i + 1] if i is not None and i + 1 < len(self.days) else None

    def shift(self, d: str, n: int) -> str | None:
        i = self.ix.get(d)
        return self.days[i + n] if i is not None and 0 <= i + n < len(self.days) else None

    def td_between(self, a: str, b: str) -> int:
        """(a, b] 之間的交易日數；b 在資料最後一天之後的部分用平日數估。"""
        i = self.ix.get(a)
        if i is None:
            i = bisect_right(self.days, a) - 1
        last = self.days[-1]
        if b <= last:
            return bisect_right(self.days, b) - 1 - i
        n = len(self.days) - 1 - i
        x = date.fromisoformat(last)
        end = date.fromisoformat(b)
        while x < end:
            x += timedelta(days=1)
            n += x.weekday() < 5
        return n

    def price(self, d: str, exp: str, k: float, cp: str) -> float | None:
        e = (self.book.get(d) or {}).get(exp)
        q = e[1].get(k) if e else None
        if not q:
            return None
        return _px(q[0], q[1]) if cp == "C" else _px(q[2], q[3])

    def settle(self, d: str, exp: str, k: float, cp: str) -> float | None:
        e = (self.book.get(d) or {}).get(exp)
        q = e[1].get(k) if e else None
        if not q:
            return None
        v = q[1] if cp == "C" else q[3]
        return float(v) if v else None


# ── 選契約 ────────────────────────────────────────────────────────────────────

def _atm(strikes, close: float):
    return min(strikes, key=lambda k: (abs(k - close), k)) if strikes else None


def o2_pick(m: Mkt, d: str, x: str) -> dict | None:
    """O2：d 進場、x 出場。到期日晚於 x 的最近一批，價平跨式。"""
    exps = sorted((xd, exp) for exp, (xd, _) in (m.book.get(d) or {}).items() if xd > x)
    if not exps:
        return None
    xd, exp = exps[0]
    ks = [k for k, q in m.book[d][exp][1].items() if _px(q[0], q[1]) and _px(q[2], q[3])]
    k = _atm(ks, m.close[d])
    if k is None:
        return None
    return {"exp": exp, "xd": xd, "legs": [(exp, k, "C", 1), (exp, k, "P", 1)]}


def o3_pick(m: Mkt, d: str, x: str, spread: float | None = None) -> dict | None:
    """O3：到期日比出場日 x 至少晚 O3_BUFFER 個交易日的最近月選（到期別 YYYYMM），價平買權；spread＝價差的賣出價外幅度。"""
    exps = sorted((xd, exp) for exp, (xd, _) in (m.book.get(d) or {}).items()
                  if len(exp) == 6 and exp.isdigit() and xd > x and m.td_between(x, xd) >= S.O3_BUFFER)
    if not exps:
        return None
    xd, exp = exps[0]
    ks = [k for k, q in m.book[d][exp][1].items() if _px(q[0], q[1])]
    k = _atm(ks, m.close[d])
    if k is None:
        return None
    legs = [(exp, k, "C", 1)]
    if spread is not None:
        k2 = _atm([kk for kk in ks if kk > k], m.close[d] * (1 + spread))
        if k2 is None:
            return None
        legs.append((exp, k2, "C", -1))
    return {"exp": exp, "xd": xd, "legs": legs}


def straddle_iv(m: Mkt, d: str) -> float | None:
    """那天的價平跨式隱含波動率（O2 的選法、出場＝下一個交易日；結算價、收盤指數、到期剩幾個交易日 ÷ 252）。"""
    x = m.next(d)
    if not x:
        return None
    p = o2_pick(m, d, x)
    if not p:
        return None
    k = p["legs"][0][1]
    sc, sp = m.settle(d, p["exp"], k, "C"), m.settle(d, p["exp"], k, "P")
    if not sc or not sp:
        return None
    s, t = m.close[d], m.td_between(d, p["xd"]) / TRADING_YEAR
    if t <= 0:
        return None
    tgt = sc + sp

    def f(v):
        return C.bs("C", s, k, t, v) + C.bs("P", s, k, t, v)
    lo, hi = 0.01, 3.0
    if tgt < f(lo) - 1e-9 or tgt > f(hi):
        return None
    for _ in range(70):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < tgt else (lo, mid)
    return round((lo + hi) / 2, 5)


def iv_pct(series: list[tuple[str, float | None]], lookback: int = S.IV_LOOKBACK) -> dict[str, float]:
    """每天的隱含波動率在過去 lookback 個有值的交易日（不含當天）裡，比它低的比例；不到 lookback 個不給。"""
    out, past = {}, []
    for d, v in series:
        if v is not None:
            if len(past) >= lookback:
                w = past[-lookback:]
                out[d] = sum(1 for x in w if x < v) / lookback
            past.append(v)
    return out


# ── 帳戶 ──────────────────────────────────────────────────────────────────────

def sim(trades: list[dict], cap: float, fee: float = S.FEE, cmult: float = 2.0, stops: bool = True) -> dict:
    """trades：[{d 進場, x 出場, legs [(到期別, 履約價, C/P, ±1)], pin [進場價], pout [出場價], tag}]，照進場日排序。
    回傳每筆（口數、損益、對權利金報酬）與帳戶資料。"""
    acct = float(S.ACCOUNT)
    pend: list[tuple[str, float]] = []          # 還沒實現的（出場日, 損益）
    rows, curve = [], [(None, acct)]
    day_real: dict[str, float] = {}
    day_open: dict[str, float] = {}
    mon_open: dict[str, float] = {}
    mon_real: dict[str, float] = {}

    def realize(upto: str):
        nonlocal acct
        for x, pnl in sorted(p for p in pend if p[0] <= upto):
            day_open.setdefault(x, acct)
            mon_open.setdefault(x[:7], acct)
            acct += pnl
            day_real[x] = day_real.get(x, 0.0) + pnl
            mon_real[x[:7]] = mon_real.get(x[:7], 0.0) + pnl
            curve.append((x, acct))
        pend[:] = [p for p in pend if p[0] > upto]

    for t in sorted(trades, key=lambda t: (t["d"], t["x"])):
        realize(t["d"])
        day_open.setdefault(t["d"], acct)
        mon_open.setdefault(t["d"][:7], acct)
        if stops:
            if day_real.get(t["d"], 0.0) <= -S.DAY_STOP * day_open[t["d"]]:
                rows.append({**t, "skip": "day_stop"})
                continue
            if mon_real.get(t["d"][:7], 0.0) <= -S.MONTH_STOP * mon_open[t["d"][:7]]:
                rows.append({**t, "skip": "month_stop"})
                continue
        basis = t.get("basis_legs", t["legs"])
        bin_ = t.get("basis_pin", t["pin"])
        per = sum(sd * p * S.MULT for (_, _, _, sd), p in zip(basis, bin_)) + sum(S.side_cost(p, fee) for p in bin_)
        lots = int(acct * cap // per) if per > 0 else 0
        if lots < 1:
            rows.append({**t, "skip": "lots0"})
            continue
        unit = sum(sd * (po - pi) * S.MULT for (_, _, _, sd), pi, po in zip(t["legs"], t["pin"], t["pout"]))
        unit -= sum(S.side_cost(pi, fee, cmult) + S.side_cost(po, fee, cmult) for pi, po in zip(t["pin"], t["pout"]))
        pnl = lots * unit
        pend.append((t["x"], pnl))
        rows.append({**t, "lots": lots, "pnl": round(pnl, 1), "ret": round(unit / per, 4), "acct0": round(acct, 1)})
    realize("9999-12-31")
    return {"rows": rows, "curve": curve, "final": acct}


def metrics(res: dict) -> dict:
    tr = [r for r in res["rows"] if "pnl" in r]
    n = len(tr)
    if not n:
        return {"n": 0}
    pnl = [r["pnl"] for r in tr]
    ret = [r["ret"] for r in tr]
    yrs: dict[str, float] = {}
    for r in tr:
        yrs[r["x"][:4]] = yrs.get(r["x"][:4], 0.0) + r["pnl"]
    peak, dd = float(S.ACCOUNT), 0.0
    for _, v in res["curve"]:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak)
    top3 = sorted(pnl, reverse=True)[3:]
    srt = sorted(ret)
    return {
        "n": n, "skips": sum(1 for r in res["rows"] if "skip" in r),
        "mean": round(sum(pnl) / n, 1), "med_ret": round(srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2, 4),
        "mean_ret": round(sum(ret) / n, 4), "win": round(sum(1 for x in pnl if x > 0) / n, 4),
        "best_ret": max(ret), "worst_ret": min(ret), "x2": round(sum(1 for x in ret if x >= 1.0) / n, 4),
        "years": {y: round(v, 1) for y, v in sorted(yrs.items())},
        "years_ok": round(sum(1 for v in yrs.values() if v >= 0) / len(yrs), 4),
        "maxdd": round(dd, 4), "final": round(res["final"], 1), "total": round(res["final"] - S.ACCOUNT, 1),
        "mean_ex_top3": round(sum(top3) / len(top3), 1) if top3 else None,
    }


def judge(mt: dict, p: float | None, key: str) -> dict:
    n = mt.get("n", 0)
    ok = {
        "1_mean": n > 0 and mt["mean"] > 0,
        "2_placebo": p is not None and p <= S.PLACEBO_P,
        "3_years": n > 0 and mt["years_ok"] >= S.YEARS_OK - 1e-9,
        "4_dd": n > 0 and mt["maxdd"] <= S.MAX_DD,
        "5_n": n >= S.MIN_N[key],
    }
    if not ok["5_n"]:
        return {"ok": ok, "verdict": "只列、不判定（筆數不夠）"}
    return {"ok": ok, "verdict": "過關" if all(ok.values()) else "沒過"}


# ── O2 ────────────────────────────────────────────────────────────────────────

def events() -> dict[str, list[str]]:
    """CPI（reldates.cpi 的公布日）＋ FOMC（txo_events.json 的排定聲明日）。"""
    rel = json.loads(gzip.decompress((ROOT / "data/lab/heat/reldates.json.gz").read_bytes()))["d"]
    cpi = sorted(set((rel.get("cpi") or {}).values()))
    fomc = json.loads((ROOT / "data/lab/txo_events.json").read_text("utf-8"))["fomc"]
    return {"cpi": cpi, "fomc": sorted(fomc)}


def o2_trade(m: Mkt, d: str, pct: dict, tag: str, filt: float | None = S.IV_PCT) -> tuple[dict | None, str]:
    if d not in m.ix:
        return None, "休市"
    x = m.next(d)
    if not x:
        return None, "沒有出場日"
    if filt is not None:
        v = pct.get(d)
        if v is None:
            return None, "波動率歷史不足"
        if v >= filt:
            return None, "太貴"
    p = o2_pick(m, d, x)
    if not p:
        return None, "沒有契約"
    pin = [m.price(d, *leg[:3]) for leg in p["legs"]]
    pout = [m.price(x, *leg[:3]) for leg in p["legs"]]
    if not all(pin) or not all(pout):
        return None, "沒有價格"
    return {"d": d, "x": x, "legs": p["legs"], "pin": pin, "pout": pout, "tag": tag, "ivp": pct.get(d)}, ""


def o2_trades(m: Mkt, ev: dict[str, list[str]], pct: dict, filt: float | None = S.IV_PCT,
              short: bool = False) -> tuple[list[dict], dict]:
    days: dict[str, list[str]] = {}
    for k, ds in ev.items():
        for d in ds:
            if m.days[0] <= d <= m.days[-1]:
                days.setdefault(d, []).append(k)
    out, why = [], {}
    for d in sorted(days):
        t, w = o2_trade(m, d, pct, "+".join(days[d]), filt)
        if t:
            if short:
                t = {**t, "basis_legs": t["legs"], "basis_pin": t["pin"], "legs": [(a, b, c, -1) for a, b, c, _ in t["legs"]]}
            out.append(t)
        else:
            why[w] = why.get(w, 0) + 1
    return out, why


def o2_placebo(m: Mkt, ev: dict[str, list[str]], pct: dict, actual: float, n: int = S.PLACEBO_N,
               seed: int = S.SEED) -> dict:
    evset = {d for ds in ev.values() for d in ds}
    evdays = sorted(d for d in evset if d in m.ix and m.next(d))
    pool: dict[str, list[str]] = {}
    for d in m.days[:-1]:
        if d not in evset:
            pool.setdefault(d[:7], []).append(d)
    cache: dict[str, dict | None] = {}
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        tr = []
        for d in evdays:
            cand = pool.get(d[:7])
            if not cand:
                continue
            r = rng.choice(cand)
            if r not in cache:
                cache[r] = o2_trade(m, r, pct, "placebo")[0]
            if cache[r]:
                tr.append(cache[r])
        mt = metrics(sim(tr, S.CAP["O2"]))
        means.append(mt.get("mean", 0.0) if mt.get("n") else 0.0)
    return {"p": round(sum(1 for v in means if v >= actual) / n, 4), "mean": round(sum(means) / n, 1),
            "q": [round(sorted(means)[int(n * q)], 1) for q in (0.05, 0.5, 0.95)]}


# ── O3 ────────────────────────────────────────────────────────────────────────

def o3_signals() -> list[dict]:
    r = json.loads((ROOT / "data/lab/rare_research.json").read_text("utf-8"))
    out = []
    for k in S.O3_RULES:
        for t in r["rules"][k]["tw"]["tr"]:
            out.append({"rule": k, "d": t[1], "x": t[3], "i0": t[2], "i1": t[4], "h": t[5]})
    return sorted(out, key=lambda t: t["d"])


def o3_trade(m: Mkt, d: str, x: str, tag: str, spread: float | None = None) -> tuple[dict | None, str]:
    if d not in m.ix or x not in m.ix:
        return None, "不在資料裡"
    p = o3_pick(m, d, x, spread)
    if not p:
        return None, "沒有契約"
    pin = [m.price(d, *leg[:3]) for leg in p["legs"]]
    pout = [m.price(x, *leg[:3]) for leg in p["legs"]]
    if not all(pin) or not all(pout):
        return None, "沒有價格"
    return {"d": d, "x": x, "legs": p["legs"], "pin": pin, "pout": pout, "tag": tag}, ""


def o3_trades(m: Mkt, sig: list[dict], spread: float | None = None) -> tuple[list[dict], dict]:
    out, why = [], {}
    for s in sig:
        if s["d"] < m.days[0]:
            continue
        t, w = o3_trade(m, s["d"], s["x"], s["rule"], spread)
        if t:
            out.append({**t, "idx_ret": round(s["i1"] / s["i0"] - 1, 4)})
        else:
            why[w] = why.get(w, 0) + 1
    return out, why


def o3_placebo(m: Mkt, sig: list[dict], actual: float, n: int = S.PLACEBO_N, seed: int = S.SEED) -> dict:
    sig = [s for s in sig if s["d"] >= m.days[0] and s["d"] in m.ix and s["x"] in m.ix]
    by_year: dict[str, list[str]] = {}
    for d in m.days:
        by_year.setdefault(d[:4], []).append(d)
    cache: dict[tuple[str, int], dict | None] = {}
    rng = random.Random(seed)
    means = []
    for _ in range(n):
        tr = []
        for s in sig:
            h = m.ix[s["x"]] - m.ix[s["d"]]
            cand = [d for d in by_year[s["d"][:4]] if m.ix[d] + h < len(m.days)]
            r = rng.choice(cand)
            key = (r, h)
            if key not in cache:
                cache[key] = o3_trade(m, r, m.days[m.ix[r] + h], "placebo")[0]
            if cache[key]:
                tr.append(cache[key])
        mt = metrics(sim(tr, S.CAP["O3"]))
        means.append(mt.get("mean", 0.0) if mt.get("n") else 0.0)
    return {"p": round(sum(1 for v in means if v >= actual) / n, 4), "mean": round(sum(means) / n, 1),
            "q": [round(sorted(means)[int(n * q)], 1) for q in (0.05, 0.5, 0.95)]}


# ── 整體 ──────────────────────────────────────────────────────────────────────

def _rows(res: dict) -> list[list]:
    """每筆：[進場, 出場, 標記, 到期別, 履約價, 進場價…, 出場價…, 口數, 損益, 對權利金報酬]（沒做的帶原因）。"""
    out = []
    for r in res["rows"]:
        base = [r["d"], r["x"], r["tag"], r["legs"][0][0], [leg[1] for leg in r["legs"]], r["pin"], r["pout"]]
        out.append(base + ([r["lots"], r["pnl"], r["ret"]] if "pnl" in r else [0, None, r["skip"]]))
    return out


def run(root: Path, placebo_n: int = S.PLACEBO_N, log=print) -> dict:
    days, book = load_book(root)
    m = Mkt(days, book, load_close())
    log(f"交易日 {len(m.days)}（{m.days[0]}～{m.days[-1]}）")
    ivs = [(d, straddle_iv(m, d)) for d in m.days]
    pct = iv_pct(ivs)
    ev = events()
    out = {"ver": VER, "spec": S.VER, "spec_fp": S.fingerprint(), "asof": m.days[-1],
           "events": {k: len(v) for k, v in ev.items()}}

    # O2 主規格（不貴過濾、兩倍成本、25 元）
    tr, why = o2_trades(m, ev, pct)
    res = sim(tr, S.CAP["O2"])
    mt = metrics(res)
    log(f"O2：{mt.get('n')} 筆（沒做：{why}）")
    pl = o2_placebo(m, ev, pct, mt.get("mean", 0.0), placebo_n) if mt.get("n") else None
    cmp_ = {}
    for name, kw in (("fee50", {"fee": S.FEE_ALT}),):
        cmp_[name] = metrics(sim(tr, S.CAP["O2"], **kw))
    for name, f in (("nofilter", None), ("pct40", 0.40), ("pct60", 0.60)):
        cmp_[name] = metrics(sim(o2_trades(m, ev, pct, f)[0], S.CAP["O2"]))
    cmp_["short"] = metrics(sim(o2_trades(m, ev, pct, S.IV_PCT, short=True)[0], S.CAP["O2"]))
    cmp_["short_nofilter"] = metrics(sim(o2_trades(m, ev, pct, None, short=True)[0], S.CAP["O2"]))
    for k in ev:
        cmp_[f"only_{k}"] = metrics(sim(o2_trades(m, {k: ev[k]}, pct)[0], S.CAP["O2"]))
    cmp_["cost1x"] = metrics(sim(tr, S.CAP["O2"], cmult=1.0))
    out["O2"] = {"main": mt, "why": why, "placebo": pl, "judge": judge(mt, pl and pl["p"], "O2"), "compare": cmp_,
                 "trades": _rows(res)}

    # O3
    sig = o3_signals()
    tr3, why3 = o3_trades(m, sig)
    res3 = sim(tr3, S.CAP["O3"])
    mt3 = metrics(res3)
    log(f"O3：{mt3.get('n')} 筆（沒做：{why3}）")
    pl3 = o3_placebo(m, sig, mt3.get("mean", 0.0), placebo_n) if mt3.get("n") else None
    c3 = {"fee50": metrics(sim(tr3, S.CAP["O3"], fee=S.FEE_ALT)), "cost1x": metrics(sim(tr3, S.CAP["O3"], cmult=1.0)),
          "spread": metrics(sim(o3_trades(m, sig, S.SPREAD_OTM)[0], S.CAP["O3"]))}
    for k in S.O3_RULES:
        c3[f"only_{k}"] = metrics(sim([t for t in tr3 if t["tag"] == k], S.CAP["O3"]))
    ir = [t["idx_ret"] for t in tr3]
    c3["index"] = {"n": len(ir), "mean_ret": round(sum(ir) / len(ir), 4) if ir else None,
                   "win": round(sum(1 for x in ir if x > 0) / len(ir), 4) if ir else None}
    out["O3"] = {"main": mt3, "why": why3, "placebo": pl3, "judge": judge(mt3, pl3 and pl3["p"], "O3"), "compare": c3,
                 "trades": _rows(res3)}
    out["iv_days"] = sum(1 for _, v in ivs if v is not None)
    return out
