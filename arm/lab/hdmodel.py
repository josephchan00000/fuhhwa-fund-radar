"""籌碼雷達：高股息指數事前預測的資料層（股利、殖利率、EPS、上市櫃市值、流動性、波動）。

資料來源（`backfill_lab.py --hd`，CI 抓）：
  · `data/lab/divtw/{年}.json.gz`：證交所除權息計算結果表（上市，一年一請求）→ [除權息日, 代號, 權值+息值, 權/息]。
    「息」＝現金股利；「權息」只有合計值（配股另計）→ 視為現金、標 approx；「權」＝純配股、不算現金。
  · `data/lab/fin/{代號}.json.gz`：FinMind 單季 EPS（市值前 320）＋上櫃股利政策（現金除息日、現金股利）。
價格與成交量沿用 analyze.Data（官方分片＋Yahoo 兩年日線）。發行股數用最新值（同臺灣50 的 caps_at）。
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from . import store


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


class HD:
    def __init__(self, D):
        self.D = D
        self.div: dict[str, list] = defaultdict(list)          # 代號 → [(除息日, 現金股利, approx)]
        self.approx: set[str] = set()
        for y in store.dates("divtw"):
            for d, c, v, t in (store.read("divtw", y) or {}).get("rows") or []:
                if "息" in str(t) and v:
                    self.div[c].append((d, float(v), "權" in str(t)))
                    if "權" in str(t):
                        self.approx.add(c)
        self.eps: dict[str, dict] = {}
        tw_codes = set(self.div)                                  # 上市股已有證交所資料 → FinMind 股利不重複加
        fin_dir = store.LAB / "fin"
        if fin_dir.exists():
            for p in fin_dir.glob("*.json.gz"):
                c = p.name.split(".json")[0]
                doc = store.read("fin", c) or {}
                if doc.get("eps"):
                    self.eps[c] = doc["eps"]
                if c in tw_codes:
                    continue
                for row in doc.get("div") or []:
                    ex_c, cash = row[0], row[1]
                    if ex_c and cash:
                        self.div[c].append((str(ex_c)[:10], float(cash), False))
        for c in self.div:
            self.div[c] = sorted(set(self.div[c]))
        self.iss_tw, self.iss_tp = self._issued()

    def _issued(self) -> tuple[dict, dict]:
        tw = tp = None
        for d in reversed(store.dates("mkt")):
            doc = store.read("mkt", d) or {}
            tw = tw or {c: r[1] for c, r in (doc.get("x_tw") or {}).items() if r and len(r) > 1 and r[1]}
            tp = tp or {c: r[6] for c, r in (doc.get("q_tp") or {}).items() if r and len(r) > 6 and r[6]}
            if tw and tp:
                break
        return tw or {}, tp or {}

    # —— 價量
    def px(self, c: str, d: str) -> float | None:
        q = self.D.quote(c, d)
        return q[3] if q else None

    def caps(self, d: str) -> dict[str, float]:
        """d 日上市＋上櫃普通股市值（元）。"""
        out = {}
        for iss in (self.iss_tw, self.iss_tp):
            for c, sh in iss.items():
                if len(c) != 4 or not c.isdigit() or c.startswith("00") or c.startswith("91"):
                    continue
                p = self.px(c, d)
                if p:
                    out[c] = p * sh
        return out

    def adv(self, c: str, i: int, n: int = 20) -> float | None:
        """近 n 日平均成交金額（元）：官方有成交金額就用、否則收盤×成交股數。"""
        s = self.D.series(c)
        xs = []
        for k in range(max(i - n + 1, 0), i + 1):
            if s["val"][k]:
                xs.append(s["val"][k])
            elif s["v"][k] and s["c"][k]:
                xs.append(s["v"][k] * s["c"][k])
        return sum(xs) / len(xs) if xs else None

    def vol(self, c: str, i: int, n: int = 250) -> float | None:
        """近 n 日日報酬標準差年化。"""
        cs = [x for x in self.D.series(c)["c"][max(i - n, 0):i + 1] if x]
        rs = [math.log(b / a) for a, b in zip(cs, cs[1:]) if a and b]
        return statistics.pstdev(rs) * math.sqrt(250) if len(rs) >= 60 else None

    # —— 股利與殖利率
    def cash_between(self, c: str, d0: str, d1: str) -> float:
        """除息日落在 (d0, d1] 的現金股利合計。"""
        return sum(v for d, v, _ in self.div.get(c, []) if d0 < d <= d1)

    def ttm(self, c: str, d: str, days: int = 365) -> float:
        return self.cash_between(c, (_d(d) - timedelta(days=days)).isoformat(), d)

    def n_pay(self, c: str, d: str, days: int = 365) -> int:
        d0 = (_d(d) - timedelta(days=days)).isoformat()
        return sum(1 for x, _, _ in self.div.get(c, []) if d0 < x <= d)

    def yld(self, c: str, d: str, days: int = 365) -> float | None:
        p = self.px(c, d)
        return self.ttm(c, d, days) / p if p else None

    def avg_yld(self, c: str, d: str, years: int = 3) -> float | None:
        """近 years 年平均殖利率＝各年（以 d 往回每 365 天一段）現金股利 ÷ d 日價格 的平均（價格用同一天，近似）。"""
        p = self.px(c, d)
        if not p:
            return None
        ys = []
        for k in range(years):
            a = (_d(d) - timedelta(days=365 * (k + 1))).isoformat()
            b = (_d(d) - timedelta(days=365 * k)).isoformat()
            ys.append(self.cash_between(c, a, b) / p)
        return sum(ys) / len(ys)

    # —— EPS
    def eps_ytd(self, c: str, year: int, q: int) -> float | None:
        """year 年第 1～q 季 EPS 合計；缺季回 None。"""
        e = self.eps.get(c) or {}
        ends = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
        vals = [e.get(f"{year}-{ends[k]}") for k in range(1, q + 1)]
        return sum(vals) if all(v is not None for v in vals) else None

    def eps_ttm(self, c: str, d: str) -> float | None:
        """d 之前已到季底的最近四季 EPS 合計（不管財報公布時間——呼叫端自行確認可得性）。"""
        e = self.eps.get(c) or {}
        qs = sorted(k for k in e if k <= d)[-4:]
        return sum(e[k] for k in qs) if len(qs) == 4 else None

