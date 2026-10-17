"""景氣溫度頁的資料層（docs/lab_heat_plan.md 第 7 節）。

存檔：data/lab/heat/{名稱}.json.gz，{"src": 來源, "d": {日期或 YYYY-MM: 值}}（store.write，內容沒變不改寫）。
抓取只在 CI（本容器的 proxy 擋這些站）；這支檔先放「用 repo 既有資料就能算」的部分：

廣度（S2、M2、M3）：每檔日線用 bt3d.Panel（2013 起、含已下市、含息還原），範圍＝當天最近一個月底市值 ≥ 40 億
（月底快照，事前看得到的名單；不用「現在夠大」挑股票，免得把日後長大的股票放進過去的名單）。
"""
from __future__ import annotations

from collections import deque

from . import store

KIND = "heat"
CAP_MIN = 40e8


def save(name: str, src: str, d: dict) -> bool:
    return store.write(KIND, name, {"src": src, "d": dict(sorted(d.items()))})


def load(name: str) -> dict:
    return (store.read(KIND, name) or {}).get("d") or {}


def breadth(P, cap_min: float = CAP_MIN) -> dict[str, list]:
    """→ {"cal", "adv", "dec", "above", "n60", "hi", "lo", "n250"}（逐日家數）。P＝bt3d.Panel。
    上漲／下跌：還原收盤比前一天高／低；站上 60 日線：還原收盤 > 近 60 日平均（60 天都要有價）；
    創新高／新低：還原收盤 ≥／≤ 近 250 日最高／最低（250 天裡至少 240 天有價）。"""
    T = P.T
    adv, dec, above, n60, hi, lo, n250 = ([0] * T for _ in range(7))
    for c in P.codes:
        cl, cap = P.s[c]["c"], P.cap[c]
        s60 = 0.0
        q60: deque = deque()
        qmax: deque = deque()                      # 250 日最高（遞減佇列，存索引）
        qmin: deque = deque()
        cnt250 = 0
        for i in range(T):
            x = cl[i]
            # 60 日平均（連續 60 天有價）
            if x is None:
                s60, q60 = 0.0, deque()
            else:
                q60.append(x)
                s60 += x
                if len(q60) > 60:
                    s60 -= q60.popleft()
            # 250 日最高最低（有價的天數）
            if x is not None:
                while qmax and cl[qmax[-1]] <= x:
                    qmax.pop()
                qmax.append(i)
                while qmin and cl[qmin[-1]] >= x:
                    qmin.pop()
                qmin.append(i)
                cnt250 += 1
            j = i - 250
            if j >= 0 and cl[j] is not None:
                cnt250 -= 1
            while qmax and qmax[0] <= i - 250:
                qmax.popleft()
            while qmin and qmin[0] <= i - 250:
                qmin.popleft()
            if x is None or not cap[i] or cap[i] < cap_min:
                continue
            p = cl[i - 1] if i > 0 else None
            if p is not None:
                if x > p:
                    adv[i] += 1
                elif x < p:
                    dec[i] += 1
            if len(q60) == 60:
                n60[i] += 1
                if x > s60 / 60:
                    above[i] += 1
            if cnt250 >= 240:
                n250[i] += 1
                if qmax[0] == i:                   # 今天就是 250 日內最高（同價也算）
                    hi[i] += 1
                if qmin[0] == i:
                    lo[i] += 1
    return {"cal": list(P.cal), "adv": adv, "dec": dec, "above": above, "n60": n60, "hi": hi, "lo": lo, "n250": n250}


def breadth_ind(b: dict) -> dict[str, dict]:
    """廣度 → 三個指標的原始值 {指標: {日期: 值（%）}}：S2 上漲家數占比（10 日）、M2 站上 60 日線比例、M3 新高減新低（20 日平均）。"""
    cal, adv, dec = b["cal"], b["adv"], b["dec"]
    out: dict[str, dict] = {"S2": {}, "M2": {}, "M3": {}}
    for i, d in enumerate(cal):
        if i >= 9:
            a = sum(adv[i - 9:i + 1])
            z = a + sum(dec[i - 9:i + 1])
            if z >= 100:
                out["S2"][d] = round(100.0 * a / z, 3)
        if b["n60"][i] >= 100:
            out["M2"][d] = round(100.0 * b["above"][i] / b["n60"][i], 3)
        if i >= 19:
            xs = [(b["hi"][k] - b["lo"][k]) / b["n250"][k] for k in range(i - 19, i + 1) if b["n250"][k] >= 100]
            if len(xs) == 20:
                out["M3"][d] = round(100.0 * sum(xs) / 20, 3)
    return out


class ShardPanel:
    """官方每日分片（data/lab/mkt，上市 q_tw＋上櫃 q_tp，2024-11 起）組成和 bt3d.Panel 同介面的小面板：
    收盤依除權息事件還原（bt3d.events，參考價 ÷ 前收）、市值＝最近一個月底快照。v3px 只在回補時更新，
    每天的廣度改用分片算；兩種算法在重疊的日子對照過（tests/test_heat.py）。"""

    def __init__(self, since: str | None = None):
        import bisect

        from . import bt3d
        from .v3data import stock
        days = []
        for d, doc in store.load("mkt", since=since):
            if len(doc.get("q_tw") or {}) >= 500:
                days.append((d, doc))
        self.cal = [d for d, _ in days]
        self.T = len(self.cal)
        ix = {d: i for i, d in enumerate(self.cal)}
        raw: dict[str, list] = {}
        for i, (d, doc) in enumerate(days):
            for part in ("q_tw", "q_tp"):
                for c, q in (doc.get(part) or {}).items():
                    if stock(c) and q and len(q) > 3 and q[3]:
                        raw.setdefault(c, [None] * self.T)[i] = q[3]
        ev = bt3d.events()
        snaps = bt3d.month_end_caps()
        sd = [d for d, _ in snaps]
        kof = [bisect.bisect_right(sd, d) - 1 for d in self.cal]
        self.s, self.cap = {}, {}
        for c, cl in raw.items():
            F = bt3d.factor_events(self.cal, [(d, f) for d, f, _ in ev.get(c) or []])
            self.s[c] = {"c": [None if x is None else x * F[i] for i, x in enumerate(cl)]}
            self.cap[c] = [snaps[k][1].get(c) if k >= 0 else None for k in kof]
        self.codes = sorted(self.s)
        self.ix = ix


def extend(P, SP) -> None:
    """把分片面板 SP 在 P 最後一天之後的日子接到 P（就地修改）：每檔在 P 最後一天（或之前最近有價的一天）
    兩邊都有價時，用比例接續（P 的還原價 × 分片還原價的變化）；P 沒有的股票只用分片的價格。"""
    import bisect

    from . import bt3d
    last = P.cal[-1] if P.cal else ""
    add = [d for d in SP.cal if d > last]
    if not add:
        return
    jx = SP.ix.get(last)
    n0 = P.T
    P.cal = list(P.cal) + add
    P.T = len(P.cal)
    P.ix = {d: i for i, d in enumerate(P.cal)}
    snaps = bt3d.month_end_caps()
    sd = [d for d, _ in snaps]
    kof = [bisect.bisect_right(sd, d) - 1 for d in add]
    caps_add = lambda c: [snaps[k][1].get(c) if k >= 0 else None for k in kof]   # noqa: E731
    for c in sorted(set(P.s) | set(SP.s)):
        sc = (SP.s.get(c) or {}).get("c")
        ext = [None] * len(add)
        if sc:
            vals = [sc[SP.ix[d]] for d in add]
            base = (P.s.get(c) or {}).get("c")
            if base is not None:
                b0 = next((base[i] for i in range(n0 - 1, -1, -1) if base[i] is not None), None)
                s0 = sc[jx] if jx is not None else None
                if b0 and s0:
                    ext = [None if v is None else v * b0 / s0 for v in vals]
            else:
                ext = vals
        if c in P.s:
            P.s[c]["c"] = list(P.s[c]["c"]) + ext
            P.cap[c] = list(P.cap[c]) + caps_add(c)
        else:
            P.s[c] = {"c": [None] * n0 + ext}
            P.cap[c] = [None] * n0 + caps_add(c)
    P.codes = sorted(P.s)
