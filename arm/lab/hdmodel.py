"""籌碼雷達：高股息指數事前預測的資料層（股利、殖利率、EPS、上市櫃市值、流動性、波動）。

資料來源（`backfill_lab.py --hd`，CI 抓）：
  · `data/lab/divtw/{年}.json.gz`：證交所除權息計算結果表（上市，一年一請求）→ [除權息日, 代號, 權值+息值, 權/息,
    除權息前收盤價, 參考價]。「息」＝現金股利；「權息」只有合計值 → 有 FinMind 資料就改用它的現金部分，
    沒有才照記並標 approx；「權」＝純配股、不算現金。
  · `data/lab/fin/{代號}.json.gz`：FinMind 單季 EPS ＋ 股利政策（上櫃股、有「權息」紀錄的上市股）。

價格口徑（踩過的坑，2026-10-14）：價量序列是「官方分片（當時價、沒還原）＋缺的日子用 Yahoo（依目前股數還原）」
拼起來的。面額變更（寶雅 2026-07-30 十比一）、配股之後，同一檔在兩種來源間會差好幾倍，股利也是「當時每股」——
直接相除會算出 40%、50% 的假殖利率。這裡一律換算到「目前股數」口徑：
  · 價格：相鄰兩個有價交易日的價格比超過 1.8 倍（台股漲跌幅限制 10%）＝口徑改變，更早的價格全部換到最新口徑。
  · 股利：有除權息前收盤價（證交所表）→ 乘上「序列前一天收盤 ÷ 當時前收盤」；沒有就除以當天的口徑倍數。
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
        tw: dict[str, list] = defaultdict(list)             # 代號 → [(除息日, 值, 類型, 前收盤)]
        for y in store.dates("divtw"):
            for r in (store.read("divtw", y) or {}).get("rows") or []:
                tw[r[1]].append((r[0], r[2], str(r[3]), r[4] if len(r) > 4 else None))
        self.eps: dict[str, dict] = {}
        fm: dict[str, list] = {}
        fin_dir = store.LAB / "fin"
        if fin_dir.exists():
            for p in fin_dir.glob("*.json.gz"):
                c = p.name.split(".json")[0]
                doc = store.read("fin", c) or {}
                if doc.get("eps"):
                    self.eps[c] = doc["eps"]
                rows = [(str(r[0])[:10], float(r[1])) for r in doc.get("div") or [] if r and r[0] and r[1]]
                if rows or doc.get("div_asof"):
                    fm[c] = rows
        self.raw: dict[str, list] = {}                         # 代號 → [(除息日, 當時每股現金股利, 前收盤或 None, approx)]
        self.approx: set[str] = set()
        for c in set(tw) | set(fm):
            pre_by = {d: pre for d, _, _, pre in tw.get(c, []) if pre}
            if c in fm:                                         # FinMind 現金股利（上櫃、或上市有配股的）
                ev = [(d, v, pre_by.get(d), False) for d, v in fm[c]]
            else:
                ev = []
                for d, v, t, pre in tw.get(c, []):
                    if "息" in t and v:
                        ev.append((d, float(v), pre, "權" in t))
                        if "權" in t:
                            self.approx.add(c)
            self.raw[c] = sorted(set(ev), key=lambda x: x[0])
        self.iss_tw, self.iss_tp = self._issued()
        self._ser: dict = {}
        self._div: dict = {}

    def _issued(self) -> tuple[dict, dict]:
        tw = tp = None
        for d in reversed(store.dates("mkt")):
            doc = store.read("mkt", d) or {}
            tw = tw or {c: r[1] for c, r in (doc.get("x_tw") or {}).items() if r and len(r) > 1 and r[1]}
            tp = tp or {c: r[6] for c, r in (doc.get("q_tp") or {}).items() if r and len(r) > 6 and r[6]}
            if tw and tp:
                break
        return tw or {}, tp or {}

    # —— 價量（目前股數口徑）
    def ser(self, c: str) -> dict:
        """→ {o, c: 開／收盤(目前股數口徑), raw: 原始收盤, src: 'o' 官方／'y' Yahoo, v, val, F: 口徑倍數, jumps}。
        口徑連續化：相鄰兩個有價的交易日價格比超過 1.8 倍（台股單日漲跌幅限制 10%，不可能是真漲跌）＝口徑改變
        （面額變更、減資、Yahoo 與官方口徑不同），之前的價格全部換到最新口徑。2026-10-14 實例：寶雅 7/30 十比一、
        緯穎 6/3 前的 Yahoo 歷史價只有官方的三分之一。"""
        if c in self._ser:
            return self._ser[c]
        D = self.D
        T = D.T
        raw, ro, src, v, val = [None] * T, [None] * T, [None] * T, [None] * T, [None] * T
        for i, d in enumerate(D.cal):
            doc = D.mkt.get(d)
            q = None
            if doc:
                for part in ("q_tw", "q_tp"):
                    x = (doc.get(part) or {}).get(c)
                    if x and x[3]:
                        q = x
                        break
            if q:
                raw[i], ro[i], src[i], v[i], val[i] = q[3], q[0], "o", q[4], q[5]
                continue
            if doc and doc.get("q_tw") and doc.get("q_tp"):
                continue                                        # 官方兩市齊全卻沒有此檔＝當天沒交易
            y = (D.yh.get(c) or {}).get(d)
            if y and y[3]:
                raw[i], ro[i], src[i], v[i] = y[3], y[0], "y", y[4]
        F, jumps = [1.0] * T, []
        f, later = 1.0, None
        for i in range(T - 1, -1, -1):                          # 由新往舊：口徑跳動就把更早的價格換算
            if raw[i] is not None:
                if later is not None:
                    r = raw[i] / raw[later]
                    if r > 1.8 or r < 1 / 1.8:
                        f *= r
                        jumps.append((D.cal[later], round(r, 4)))
                later = i
            F[i] = f
        cc = [None if raw[i] is None else raw[i] / F[i] for i in range(T)]
        oo = [None if ro[i] is None else ro[i] / F[i] for i in range(T)]
        self._ser[c] = {"o": oo, "c": cc, "raw": raw, "src": src, "v": v, "val": val, "F": F, "jumps": jumps[::-1]}
        return self._ser[c]

    def mom(self, c: str, i: int | None, n: int = 40) -> float | None:
        """i 日收盤相對 n 個交易日前（目前股數口徑）。"""
        cs = self.ser(c)["c"]
        if i is None or i < n or not cs[i] or not cs[i - n]:
            return None
        return cs[i] / cs[i - n] - 1

    def _i(self, d: str) -> int | None:
        i = self.D.ix.get(d)
        if i is not None:
            return i
        k = None
        for j, x in enumerate(self.D.cal):
            if x <= d:
                k = j
            else:
                break
        return k

    def px(self, c: str, d: str) -> float | None:
        i = self._i(d)
        if i is None:
            return None
        cs = self.ser(c)["c"]
        for k in range(i, max(i - 5, -1), -1):
            if cs[k]:
                return cs[k]
        return None

    def caps(self, d: str) -> dict[str, float]:
        """d 日上市＋上櫃普通股市值（元）＝最新發行股數 × 目前股數口徑收盤（當天有成交的才算）。"""
        out = {}
        for iss in (self.iss_tw, self.iss_tp):
            for c, sh in iss.items():
                if len(c) != 4 or not c.isdigit() or c.startswith("00") or c.startswith("91"):
                    continue
                if self.D.quote(c, d):
                    p = self.px(c, d)
                    if p:
                        out[c] = p * sh
        return out

    def adv(self, c: str, i: int, n: int = 20) -> float | None:
        """近 n 日平均成交金額（元）：官方有成交金額就用、否則原始收盤 × 成交股數。"""
        s = self.ser(c)
        xs = []
        for k in range(max(i - n + 1, 0), i + 1):
            if s["val"][k]:
                xs.append(s["val"][k])
            elif s["v"][k] and s["raw"][k]:
                xs.append(s["v"][k] * s["raw"][k])
        return sum(xs) / len(xs) if xs else None

    def vol(self, c: str, i: int, n: int = 250) -> float | None:
        """近 n 日日報酬標準差年化。"""
        cs = [x for x in self.ser(c)["c"][max(i - n, 0):i + 1] if x]
        rs = [math.log(b / a) for a, b in zip(cs, cs[1:]) if a and b]
        return statistics.pstdev(rs) * math.sqrt(250) if len(rs) >= 60 else None

    # —— 股利（目前股數口徑）
    def divs(self, c: str) -> list[tuple]:
        """→ [(除息日, 目前股數口徑現金股利, approx)]。有除權息前收盤價（證交所表）→ 乘「序列前一天收盤 ÷ 當時前收盤」；
        沒有（FinMind 上櫃股）→ 除以前一天的口徑倍數 F。"""
        if c in self._div:
            return self._div[c]
        s = self.ser(c)
        out = []
        for d, v, pre, ap in self.raw.get(c, []):
            i = self._i((_d(d) - timedelta(days=1)).isoformat())
            f = 1.0
            if i is not None:
                k = next((k for k in range(i, max(i - 5, -1), -1) if s["c"][k]), None)
                if k is not None:
                    f = s["c"][k] / pre if pre else 1.0 / s["F"][k]
                    if not 0.005 < f < 50:
                        f = 1.0
            out.append((d, v * f, ap))
        self._div[c] = out
        return out

    def cash_between(self, c: str, d0: str, d1: str) -> float:
        """除息日落在 (d0, d1] 的現金股利合計（目前股數口徑）。"""
        return sum(v for d, v, _ in self.divs(c) if d0 < d <= d1)

    def ttm(self, c: str, d: str, days: int = 365) -> float:
        return self.cash_between(c, (_d(d) - timedelta(days=days)).isoformat(), d)

    def n_pay(self, c: str, d: str, days: int = 365) -> int:
        d0 = (_d(d) - timedelta(days=days)).isoformat()
        return sum(1 for x, _, _ in self.divs(c) if d0 < x <= d)

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
