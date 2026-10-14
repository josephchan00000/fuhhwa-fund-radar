"""籌碼雷達：高股息指數事前預測（規則重算／近似）＋歷次回放。

2026-10-14 使用者：「幫我套用在高股息ETF」→「深度規劃分析後逐步執行」。四檔做法不同（規則摘要見
`config/index_reviews.json` 各指數 `rule`）：

  · 00919 精選高息（臺灣指數公司）：規則公開、資料免費 → 重算。12 月＝近四季股利率×(1＋前三季 EPS 年增率)、
    5 月＝近四季已公告股利率；前 20 名直接納入、既有第 61 名後刪除；至少 7 檔市值前 50、20 檔前 150；12 月最多換 8 檔。
  · 00929 科技優息（臺灣指數公司）：科技相關產業、篩選後依殖利率取前 50；6 月最多換 24 檔、12 月 16 檔。
  · 0056 臺灣高股息（富時／證交所）：官方用 I/B/E/S 分析師預估股利（付費）→ 用「近四季 EPS × 去年配發率」近似；
    非成分股前 35 名納入、成分股第 66 名後刪除、每次最多 5 進 5 出。
  · 00878 MSCI ESG 高息 30：ESG 評級付費、母體 MSCI 臺灣不公開 → 只能用「股利分數」排名近似，ESG 不知道。

近似的地方（每一條都會讓回放對不上，回放結果就是可信度）：
  · 股利：證交所除權息表（上市）＋FinMind 股利政策（上櫃）以「除息日」計；「已公告未除息」的股利沒有公告日資料，
    5／6 月審核改用之後實際除息的金額近似（回放有些微後見之明）。
  · 市值：最新發行股數 × 當日收盤；母體篩選的流動性、ROE、波動等門檻用近似值（見各函式）。
  · 0056 分析師預估、00878 ESG 評級、00929 本益比差距指標：拿不到，直接略過。
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from . import tw50study as TS

TECH = {"半導體業", "電腦及週邊設備業", "光電業", "通信網路業", "電子零組件業", "電子通路業", "資訊服務業", "其他電子業"}
TECH_PLUS = {"生技醫療業", "綠能環保", "數位雲端"}          # 00929 2025-12 起擴大採樣


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _deadline(q_end: str) -> str:
    """單季財報法定公告期限（Q1 5/15、Q2 8/14、Q3 11/14、Q4 隔年 3/31）。"""
    y, m = int(q_end[:4]), int(q_end[5:7])
    return {3: f"{y}-05-15", 6: f"{y}-08-14", 9: f"{y}-11-14", 12: f"{y + 1}-03-31"}[m]


class Ctx:
    """一次預測用的快取（價量序列、市值排名、產業別）。"""

    def __init__(self, D, H, industry: dict | None = None):
        self.D, self.H = D, H
        self.ind = industry or {}
        self._ser: dict = {}
        self._caps: dict = {}

    def i(self, d: str) -> int | None:
        return TS._on_or_before(self.D, d)

    def ser(self, c: str) -> dict:
        return self.H.ser(c)                                    # 目前股數口徑（面額變更、配股已換算）

    def px(self, c: str, d: str) -> float | None:
        return self.H.px(c, d)

    def caps(self, d: str) -> dict[str, float]:
        """d 日上市櫃普通股市值（元）＝最新發行股數 × 當日收盤（目前股數口徑）。"""
        if d not in self._caps:
            self._caps[d] = self.H.caps(d)
        return self._caps[d]

    def adv(self, c: str, d: str, n: int = 60) -> float | None:
        """近 n 個交易日平均成交金額（元）；有效天數不到一半回 None。"""
        i = self.i(d)
        if i is None:
            return None
        s = self.ser(c)
        xs = []
        for k in range(max(i - n + 1, 0), i + 1):
            if s["val"][k]:
                xs.append(s["val"][k])
            elif s["v"][k] and s["raw"][k]:
                xs.append(s["v"][k] * s["raw"][k])
        return sum(xs) / len(xs) if len(xs) >= n // 2 else None

    def vol(self, c: str, d: str, n: int = 250) -> float | None:
        i = self.i(d)
        return None if i is None else self.H.vol(c, i, n)

    def ret(self, c: str, d: str, n: int = 120) -> float | None:
        i = self.i(d)
        cs = self.ser(c)["c"]
        if i is None or i < n or not cs[i] or not cs[i - n]:
            return None
        return cs[i] / cs[i - n] - 1

    # —— 財報與股利（只用 d 當時已公告的）
    def eps_known(self, c: str, d: str) -> dict[str, float]:
        return {q: v for q, v in (self.H.eps.get(c) or {}).items() if _deadline(q) <= d}

    def eps_sum(self, c: str, d: str, year: int, qs=(1, 2, 3, 4)) -> float | None:
        e = self.eps_known(c, d)
        ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
        vals = [e.get(f"{year}-{ends[q]}") for q in qs]
        return sum(vals) if all(v is not None for v in vals) else None

    def eps_ttm(self, c: str, d: str) -> float | None:
        e = self.eps_known(c, d)
        qs = sorted(e)[-4:]
        return sum(e[q] for q in qs) if len(qs) == 4 else None

    def cash(self, c: str, d0: str, d1: str) -> float:
        return self.H.cash_between(c, d0, d1)

    def div_window(self, c: str, d: str, shift: int = 0) -> float:
        """除息日落在 (d−365+shift, d+shift] 的現金股利（shift>0＝把「已公告、還沒除息」的近似算進來）。"""
        a = (_d(d) - timedelta(days=365 - shift)).isoformat()
        b = (_d(d) + timedelta(days=shift)).isoformat()
        return self.cash(c, a, b)

    def n_pay(self, c: str, d: str) -> int:
        return self.H.n_pay(c, d)


# —— 共用選股：緩衝區＋換股上限

def buffer_select(ranked: list[str], pre: set, n: int, top_in: int, keep_rank: int,
                  max_chg: int | None = None, existing_first: bool = True) -> tuple[list, list, list]:
    """ranked＝合格股依分數排序。前 top_in 名直接入選；既有成分股名次 ≤ keep_rank 留任；不足 n 檔再依名次補
    （existing_first＝既有成分股優先補）。max_chg＝一次最多換幾檔（超過時留下名次最好的納入、刪掉名次最差的）。
    → (入選, 納入, 刪除)。"""
    rk = {c: k + 1 for k, c in enumerate(ranked)}
    sel = list(ranked[:top_in])
    for c in ranked[top_in:]:
        if c in pre and rk[c] <= keep_rank and len(sel) < n:
            sel.append(c)
    if len(sel) < n:
        rest = [c for c in ranked if c not in sel]
        if existing_first:
            rest = [c for c in rest if c in pre and rk[c] <= keep_rank] + [c for c in rest if not (c in pre and rk[c] <= keep_rank)]
        sel += rest[:n - len(sel)]
    sel = sel[:n]
    adds = sorted((c for c in sel if c not in pre), key=lambda c: rk[c])
    dels = sorted((c for c in pre if c not in sel), key=lambda c: -rk.get(c, 10 ** 6))   # 不合格（無名次）最先刪
    if max_chg is not None and len(adds) > max_chg:
        extra = len(adds) - max_chg
        adds = adds[:max_chg]
        keep_back = [c for c in reversed(dels) if c in rk][:extra]                     # 名次最好的刪除股留下
        dels = [c for c in dels if c not in keep_back]
        sel = [c for c in sel if c in pre or c in adds] + keep_back
    return sel, adds, dels


# —— 00919 精選高息

def tip_hd_rank(cx: Ctx, d: str, pre: set, month: int) -> tuple[list[str], dict]:
    caps = cx.caps(d)
    uni = sorted(caps, key=lambda c: -caps[c])[:300]
    score, info = {}, {}
    for c in uni:
        a = cx.adv(c, d)
        if a is None or a < (6e7 if c in pre else 8e7):
            continue
        e = cx.eps_ttm(c, d)
        if e is None or e <= 0:                              # 近四季 ROE>0 → 用近四季 EPS>0 近似
            continue
        p = cx.px(c, d)
        if not p:
            continue
        if month == 12:
            div = cx.div_window(c, d, 0)
            y = _d(d).year
            now, prev = cx.eps_sum(c, d, y, (1, 2, 3)), cx.eps_sum(c, d, y - 1, (1, 2, 3))
            g = (now / prev - 1) if (now is not None and prev and prev > 0) else 0.0
            s = div / p * (1 + max(g, -1.0))
        else:
            div = cx.div_window(c, d, 120)
            g = None
            s = div / p
        if div <= 0 or s <= 0:
            continue
        score[c] = s
        info[c] = {"yld": round(div / p * 100, 2), "g": None if g is None else round(g * 100, 1)}
    ranked = sorted(score, key=lambda c: -score[c])
    return ranked, info


def tip_hd_select(cx: Ctx, d: str, pre: set, month: int, n: int = 40) -> dict:
    ranked, info = tip_hd_rank(cx, d, pre, month)
    sel, adds, dels = buffer_select(ranked, pre, n, 20, 60, max_chg=8 if month == 12 else None)
    caps = cx.caps(d)
    order = sorted(caps, key=lambda c: -caps[c])
    top50, top150 = set(order[:50]), set(order[:150])
    rk = {c: k + 1 for k, c in enumerate(ranked)}
    for grp, need in ((top50, 7), (top150, 20)):            # 市值配額：不足就把名次最差的非配額股換成配額股
        while sum(1 for c in sel if c in grp) < need:
            cand = [c for c in ranked if c in grp and c not in sel]
            out = [c for c in sorted(sel, key=lambda c: -rk.get(c, 10 ** 6)) if c not in grp]
            if not cand or not out:
                break
            sel.remove(out[0])
            sel.append(cand[0])
    adds = sorted((c for c in sel if c not in pre), key=lambda c: rk.get(c, 10 ** 6))
    dels = sorted((c for c in pre if c not in sel), key=lambda c: -rk.get(c, 10 ** 6))
    return {"ranked": ranked, "info": info, "sel": sel, "adds": adds, "dels": dels}


# —— 00929 科技優息

def tip_tech_select(cx: Ctx, d: str, pre: set, month: int, n: int = 50, plus: bool = True) -> dict:
    caps = cx.caps(d)
    inds = TECH | (TECH_PLUS if plus else set())
    tech = [c for c in caps if cx.ind.get(c) in inds and caps[c] >= 5e9]
    uni = sorted(tech, key=lambda c: -caps[c])[:200]
    y = _d(d).year
    rows = {}
    for c in uni:
        a = cx.adv(c, d)
        if a is None or a < 3e7:                              # 流動性門檻未查到 → 先用 3,000 萬
            continue
        eps_y = [cx.eps_sum(c, d, y - k) for k in (1, 2, 3)]
        if any(v is not None and v <= 0 for v in eps_y):        # ROE 連 3 年為正 → 年度 EPS 為正近似
            continue
        p = cx.px(c, d)
        if not p:
            continue
        div = cx.div_window(c, d, 120 if month == 6 else 30)
        if div <= 0:
            continue
        hist = [cx.cash(c, f"{y - k - 1}-12-31", f"{y - k}-12-31") for k in range(1, 6)]
        avg3 = sum(hist[:3]) / 3 / p
        cv = (statistics.pstdev(hist) / statistics.mean(hist)) if statistics.mean(hist) > 0 else 9.0
        rows[c] = {"yld": div / p, "avg3": avg3, "cv": cv, "vol": cx.vol(c, d) or 0.0, "freq": cx.n_pay(c, d)}
    if not rows:
        return {"ranked": [], "info": {}, "sel": [], "adds": [], "dels": []}

    def cut(key, top):                                        # 剔除前／後 10%
        xs = sorted(rows, key=lambda c: rows[c][key], reverse=top)
        return set(xs[:max(1, len(xs) // 10)])
    bad = cut("vol", True) | cut("avg3", False) | cut("cv", True)
    ok = [c for c in rows if c not in bad]
    if month == 12:                                            # 12 月優先近四季配息 ≥2 次
        ranked = sorted(ok, key=lambda c: (rows[c]["freq"] < 2, -rows[c]["yld"]))
    else:
        ranked = sorted(ok, key=lambda c: -rows[c]["yld"])
    max_chg = 16 if month == 12 else 24
    sel, adds, dels = buffer_select(ranked, pre, n, n, n, max_chg=max_chg)
    info = {c: {"yld": round(rows[c]["yld"] * 100, 2), "freq": rows[c]["freq"]} for c in rows}
    return {"ranked": ranked, "info": info, "sel": sel, "adds": adds, "dels": dels}


# —— 0056 臺灣高股息（分析師預估股利 → 近似）

def tw_div_select(cx: Ctx, d: str, pre: set, n: int = 50, max_chg: int | None = 5,
                  proxy: str = "fwd", no_ky: bool = True) -> dict:
    caps = cx.caps(d)
    tw = [c for c in caps if c in cx.H.iss_tw]                  # 母體＝臺灣50＋中型100 → 上市市值前 150 近似
    uni = sorted(tw, key=lambda c: -caps[c])[:150]
    if no_ky:
        uni = [c for c in uni if "-KY" not in (cx.D.names.get(c) or "")]
    y = _d(d).year
    score, info = {}, {}
    for c in uni:
        p = cx.px(c, d)
        if not p:
            continue
        ttm = cx.div_window(c, d, 0)
        fy_div = cx.cash(c, f"{y - 1}-01-01", f"{y - 1}-12-31") or ttm
        fy_eps = cx.eps_sum(c, d, y - 2) or cx.eps_sum(c, d, y - 1)
        e_ttm = cx.eps_ttm(c, d)
        if proxy == "fwd" and e_ttm and fy_eps and fy_eps > 0:
            payout = min(max(fy_div / fy_eps, 0.0), 1.2)
            fwd = max(e_ttm, 0) * payout if payout > 0 else ttm
        else:
            fwd = ttm
        if fwd <= 0:
            continue
        score[c] = fwd / p
        info[c] = {"yld": round(ttm / p * 100, 2), "fwd": round(fwd / p * 100, 2)}
    ranked = sorted(score, key=lambda c: -score[c])
    rk = {c: k + 1 for k, c in enumerate(ranked)}
    adds = [c for c in ranked if c not in pre and rk[c] <= 35]
    dels = sorted((c for c in pre if rk.get(c, 10 ** 6) >= 66), key=lambda c: -rk.get(c, 10 ** 6))
    if max_chg is not None:
        adds, dels = adds[:max_chg], dels[:max_chg]
    sel = [c for c in pre if c not in dels] + adds
    while len(sel) < n:                                         # 不足 50 → 補名次最高的非成分股
        cand = [c for c in ranked if c not in sel]
        if not cand:
            break
        sel.append(cand[0])
        adds.append(cand[0])
    while len(sel) > n:                                         # 超過 50 → 刪名次最差的成分股
        worst = max((c for c in sel if c in pre), key=lambda c: rk.get(c, 10 ** 6))
        sel.remove(worst)
        dels.append(worst)
    return {"ranked": ranked, "info": info, "sel": sel, "adds": adds, "dels": dels}


# —— 00878 MSCI ESG 高息 30（ESG 不知道 → 只排股利分數）

def msci_hd_select(cx: Ctx, d: str, pre: set, n: int = 30, top_in: int = 20, keep_rank: int = 40,
                   uni_n: int = 90) -> dict:
    caps = cx.caps(d)
    uni = sorted(caps, key=lambda c: -caps[c])[:uni_n]
    rows = {}
    for c in uni:
        p = cx.px(c, d)
        if not p:
            continue
        ys = [cx.cash(c, (_d(d) - timedelta(days=365 * (k + 1))).isoformat(),
                      (_d(d) - timedelta(days=365 * k)).isoformat()) / p for k in range(3)]
        if ys[0] <= 0:
            continue
        rows[c] = {"y0": ys[0], "y1": ys[1], "y2": ys[2], "avg": sum(ys) / 3,
                   "sd": statistics.pstdev(ys) / (sum(ys) / 3) if sum(ys) > 0 else 9.0}
    if not rows:
        return {"ranked": [], "info": {}, "sel": [], "adds": [], "dels": []}
    bad = set()
    for key in ("y0", "y1", "y2"):                              # 各年殖利率後 10% 不具資格
        xs = sorted(rows, key=lambda c: rows[c][key])
        bad |= set(xs[:max(1, len(xs) // 10)])
    ok = [c for c in rows if c not in bad and rows[c]["sd"] <= 0.5]
    score = {c: 0.25 * rows[c]["y0"] + 0.75 * rows[c]["avg"] for c in ok}
    ranked = sorted(ok, key=lambda c: -score[c])
    sel, adds, dels = buffer_select(ranked, pre, n, top_in, keep_rank)
    info = {c: {"yld": round(rows[c]["y0"] * 100, 2), "score": round(score.get(c, 0) * 100, 2)} for c in rows}
    return {"ranked": ranked, "info": info, "sel": sel, "adds": adds, "dels": dels}


# —— 回放：用歷次審核當時的資料重跑，對照官方結果

def _month(h: dict) -> int:
    return int((h.get("review") or "0000-00")[5:7])


def predict(cx: Ctx, key: str, h: dict, pre: set, d: str | None = None) -> dict | None:
    d = d or h.get("cutoff")
    if not d:
        return None
    m = _month(h)
    if key == "tip_hd":
        return tip_hd_select(cx, d, pre, 12 if m == 12 else 5, n=40 if h.get("review", "") >= "2025-05" else 30)
    if key == "tip_tech":
        new = h.get("review", "") >= "2025-12"
        return tip_tech_select(cx, d, pre, 12 if m == 12 else 6, n=50 if new else 40, plus=new)
    if key == "tw_div":
        return tw_div_select(cx, d, pre, max_chg=5 if h.get("review", "") >= "2025-06" else None,
                             no_ky=h.get("review", "") >= "2025-12")
    if key == "msci_esg30":
        new = h.get("review", "") >= "2026-05"
        return msci_hd_select(cx, d, pre, top_in=20 if new else 25, keep_rank=40 if new else 35)
    return None


def msci_cutoff(D, h: dict) -> str | None:
    """MSCI 價格截止日（事前不公布、在審核公布前一個月最後 10 個營業日之一）→ 取倒數第 5 個交易日近似。"""
    ann = h.get("announce")
    if not ann:
        return None
    m0 = (_d(ann).replace(day=1) - timedelta(days=1)).isoformat()[:7]
    days = [x for x in D.cal if x[:7] == m0]
    return days[-5] if len(days) >= 5 else None


def replay(D, H, cfg: dict, industry: dict, keys=("tip_hd", "tip_tech", "tw_div", "msci_esg30"),
           leads=(0, 10, 20)) -> list[dict]:
    from . import hdstudy as HS
    cx = Ctx(D, H, industry)
    out = []
    for k in keys:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        cons = HS.constituents(ix)
        for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or ""):
            if h.get("kind") == "季審" or not (h.get("adds") or h.get("dels")):
                continue
            ba = cons.get(h.get("review"))
            if not ba:
                continue
            base = h.get("cutoff") or (msci_cutoff(D, h) if k == "msci_esg30" else None)
            ib = TS._on_or_before(D, base) if base else None
            if ib is None or ib < 60:
                continue
            act_a, act_d = set(h.get("adds") or []), set(h.get("dels") or [])
            rec = {"key": k, "review": h.get("review"), "cutoff": D.cal[ib], "act_add": sorted(act_a), "act_del": sorted(act_d), "lead": {}}
            for L in leads:
                if ib - L < 60:
                    continue
                p = predict(cx, k, h, ba[0], D.cal[ib - L])
                if not p:
                    continue
                pa, pd = set(p["adds"]), set(p["dels"])
                rec["lead"][L] = {"pred_add": p["adds"], "pred_del": p["dels"], "hit_add": len(pa & act_a),
                                  "hit_del": len(pd & act_d), "n_pred_add": len(pa), "n_pred_del": len(pd),
                                  "rank": {c: (p["ranked"].index(c) + 1 if c in p["ranked"] else None) for c in act_a}}
            out.append(rec)
    return out


if __name__ == "__main__":                  # 研究用：python3 -m arm.lab.hdpredict
    import json
    from pathlib import Path
    from . import analyze
    from .hdmodel import HD
    root = Path(__file__).resolve().parents[2]
    D = analyze.Data()
    H = HD(D)
    cfg = json.loads((root / "config" / "index_reviews.json").read_text(encoding="utf-8"))
    ind = json.loads((root / "data" / "stock_industry.json").read_text(encoding="utf-8")).get("industry") or {}
    for r in replay(D, H, cfg, ind):
        print(f"\n{r['key']} {r['review']} 截止 {r['cutoff']}：實際納入 {len(r['act_add'])} 刪除 {len(r['act_del'])}")
        for L, x in sorted(r["lead"].items()):
            print(f"  提前 {L:2d} 日：預測納入 {x['n_pred_add']} 中 {x['hit_add']}｜預測刪除 {x['n_pred_del']} 中 {x['hit_del']}"
                  f"｜實際納入名次 {sorted(v for v in x['rank'].values() if v) } 無名次 {[c for c, v in x['rank'].items() if not v]}")


# —— 下一次審核的即時預測（頁面用）

KEYS = ("tip_hd", "tip_tech", "tw_div", "msci_esg30")
CAP = {"tip_hd": 0.15, "tip_tech": 0.10, "tw_div": 0.10, "msci_esg30": 0.10}
# 回放準度夠才放預估名單。0056：五種近似（近四季股利、EPS×配發率、近兩季年化…）回放最好也只中 7／21、多猜 30
# （2026-10-14）——官方用分析師預估股利，免費資料重現不了；00878：ESG 評級拿不到。這兩檔只列時程，名單等公告。
PRED_KEYS = ("tip_hd", "tip_tech")
NOPRED_WHY = {"tw_div": "官方用分析師預估股利（付費資料）排名，免費資料重現不了（回放 21 檔只中 7 檔）——名單等公告；公告後到被動買盤開始還有約兩週",
              "msci_esg30": "ESG 評級是付費資料、母體不公開，名單重現不了——等 00878 開始換股、每日持股揭露出現新股票才知道"}


def _cur_holdings(etf: str) -> set[str]:
    from . import hdstudy as HS
    return {c for c in HS._cur_holdings(etf) if len(c) == 4 and c.isdigit()}


def _msci_cutoff_est(nx: dict) -> str | None:
    """MSCI 價格截止日估計：公布月的前一個月倒數第 5 個交易日。"""
    ann = nx.get("announce")
    if not ann:
        return None
    last = _d(ann).replace(day=1) - timedelta(days=1)
    while last.weekday() >= 5:
        last -= timedelta(days=1)
    return TS.td_shift(TS.td_shift(last.isoformat(), 1), -5)


def _acc(reps: list[dict], key: str) -> dict:
    """回放命中：{提前天數: {hit, tot, fp, n_rev}}（納入股）。"""
    out = {}
    for L in (0, 10, 20):
        rs = [r for r in reps if r["key"] == key and L in r["lead"]]
        if not rs:
            continue
        hit = sum(r["lead"][L]["hit_add"] for r in rs)
        tot = sum(len(r["act_add"]) for r in rs)
        fp = sum(r["lead"][L]["n_pred_add"] - r["lead"][L]["hit_add"] for r in rs)
        hd = sum(r["lead"][L]["hit_del"] for r in rs)
        td = sum(len(r["act_del"]) for r in rs)
        out[L] = {"hit": hit, "tot": tot, "fp": fp, "hit_del": hd, "tot_del": td, "n_rev": len(rs)}
    return out


def live(D, H, cfg: dict, industry: dict, reps: list[dict] | None = None, keys=KEYS, F: dict | None = None) -> dict:
    """各指數下一次審核：用最新資料（過了資料截止日就用截止日）重跑規則 → 預估納入／刪除＋估計被動買賣。
    F＝hdflow.fk()：納入股估計買進＝市值 × 該指數過去「實際買進占市值」中位數；刪除股＝ETF 目前實際持股。
    沒有 F 時退回「規模 × 殖利率占比」（舊估法，冷門股會高估）。"""
    from . import hdflow as HF
    from . import hdstudy as HS
    cx = Ctx(D, H, industry)
    reps = reps if reps is not None else replay(D, H, cfg, industry)
    last = D.cal[-1]
    out = {}
    for k in keys:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        nx = dict(ix.get("next") or {})
        etf = (ix.get("etfs") or [None])[0]
        pre = _cur_holdings(etf) if etf else set()
        if not nx or len(pre) < 10:
            continue
        cut = nx.get("cutoff") or (_msci_cutoff_est(nx) if k == "msci_esg30" else None)
        d = min(cut, last) if cut else last
        frozen = bool(cut and last >= cut)
        t0, t1 = HS._conv_window(D, k, nx)
        if k not in PRED_KEYS:
            out[k] = {"etf": etf, "review": nx.get("review"), "cutoff": cut, "announce": nx.get("announce"),
                      "reveal": nx.get("reveal"), "effective": nx.get("effective"), "trade": [t0, t1],
                      "status": nx.get("status"), "aum": HS._cur_aum(etf)[1], "n_pre": len(pre), "nopred": NOPRED_WHY.get(k),
                      "acc": _acc(reps, k)}
            continue
        try:
            p = predict(cx, k, nx, pre, d)
        except Exception as e:                            # noqa: BLE001
            out[k] = {"err": f"{type(e).__name__}: {e}"}
            continue
        if not p:
            continue
        ia = cx.i(d)
        _, aum = HS._cur_aum(etf)
        sel = p["sel"]
        ys = {c: max(H.yld(c, d) or 0.0, 0.0) for c in sel}
        tot = sum(ys.values()) or 1.0
        w = {c: min(y / tot, CAP.get(k, 0.1)) for c, y in ys.items()}
        rk = {c: i + 1 for i, c in enumerate(p["ranked"])}

        fk = ((F or {}).get(k) or {}).get("f")

        def row(c, side):
            m = H.mom(c, ia) if ia is not None else None
            a20 = cx.adv(c, d, 20)
            if side == "add" and fk:
                amt, days = HF.est_days(H, c, d, ia, fk, HF.CAPW.get(k, 0.1) * aum if aum else None)
            elif side == "del" and F is not None:
                amt, days = HF.del_est(D, H, etf, c, d, ia)
            else:
                amt = aum * w.get(c, 0) if (aum and side == "add") else (aum / max(len(pre), 1) if aum else None)
                days = round(amt * 1e8 / a20, 1) if (amt and a20) else None
            return [c, D.names.get(c, c), rk.get(c), (p["info"].get(c) or {}).get("yld"),
                    None if m is None else round(m * 100, 1),
                    None if amt is None else round(amt, 1), days, cx.px(c, d)]
        out[k] = {"etf": etf, "review": nx.get("review"), "asof": d, "frozen": frozen, "cutoff": cut,
                  "announce": nx.get("announce"), "reveal": nx.get("reveal"), "effective": nx.get("effective"),
                  "trade": [t0, t1], "status": nx.get("status"), "aum": aum, "n_pre": len(pre),
                  "max_chg": nx.get("max_changes"), "fk": None if not fk else round(fk * 100, 2),
                  "adds": [row(c, "add") for c in p["adds"]], "dels": [row(c, "del") for c in p["dels"]],
                  "acc": _acc(reps, k)}
    return out
