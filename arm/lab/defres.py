"""個股策略的防守研究（defspec VER 1；docs/lab_stock_page_plan.md 第 9、10 節）：D1 大盤走弱先不買、D2 同一類最多幾檔、D3 熔斷不偷看。

實作細節（第 10 節，看任何結果之前寫定）照做、不改：
  · 判定的回測期間到官方結果檔的最後一天（boom＝sx_n8_curve.json 的最後一天；v3l＝bt3_research.json 的 d1；qm＝ussx_qm.json），
    這樣基準重跑才比得了官方數字；「2026-10 以後」另外用到最新資料的回測只描述。
  · 統計照各策略原本的算法：boom＝run_w7.curve_stats（日曆天年化、兩半 2019–2022／2023 起）；v3l＝bt3.curve_stats（交易日 ÷ 252，
    兩半在 2021-10-01 切開、各自從那一段第一天算起）；qm＝ussxbook.curve_stats（日曆天年化、交易日中點切兩半）。
  · v3l 的官方年報酬只存到小數一位（30.4%），比對時重跑的數字也四捨五入到同一位。
  · D2 的財報驚喜：同一期名單裡同一類最多 K 檔（財報年報那一期和第一季那一期重疊持有時，兩份名單各自算）。
本模組只讀 repo 裡的資料（美股另外讀資料分支），不抓任何東西。
"""
from __future__ import annotations

import json
import math
from bisect import bisect_right
from pathlib import Path

from . import defspec as S

ROOT = Path(__file__).resolve().parents[2]


# ── 類別 ──────────────────────────────────────────────────────────────────────

class TwInd:
    """台股產業別：那一天以前最近的一份證交所／櫃買快照（data/lab/indsnap.json），快照沒有的用 stockmeta 現在的分類。"""

    def __init__(self, path: Path | None = None):
        from arm import stockmeta as M
        d = json.loads((path or ROOT / "data" / "lab" / "indsnap.json").read_text(encoding="utf-8"))
        snaps: dict[str, dict] = {}
        for mk in ("twse", "tpex"):
            for dt, inds in (d.get(mk) or {}).items():
                m = snaps.setdefault(dt, {})
                for ic, codes in inds.items():
                    for c in codes:
                        m[c] = M.IND_CODE.get(ic, ic)
        self.snaps = sorted(snaps.items())
        self.dates = [x for x, _ in self.snaps]
        self.cur = M.industry_map()
        self._c: dict = {}

    def at(self, code: str, date: str) -> str | None:
        k = bisect_right(self.dates, date) - 1
        key = (code, k)
        if key not in self._c:
            v = self.snaps[k][1].get(code) if k >= 0 else None
            self._c[key] = v or self.cur.get(code)
        return self._c[key]


def ma_gate(px: list, n: int) -> list[bool]:
    """gate[i]＝那天可以下新的買單：收盤 ≥ 含當天的 n 日均線；資料不夠 n 天、或當天沒有收盤 → 可以。"""
    out, win, tot = [], [], 0.0
    for x in px:
        if x is None or not (x == x):
            out.append(True)
            continue
        win.append(float(x))
        tot += float(x)
        if len(win) > n:
            tot -= win.pop(0)
        out.append(len(win) < n or float(x) >= tot / n)
    return out


def cap_pick(rows, k: int, ind, cal, top_n: int = 5, umin: int = 20) -> list[tuple]:
    """財報驚喜的 D2：照分數由高到低，同一類滿 k 檔就跳過，補到 top_n 檔（有分數的不到 umin 檔那一期不選，同原規則）。"""
    out = []
    for t, x, sc in rows:
        if len(sc) < umin:
            continue
        got, cnt = [], {}
        for c in sorted(sc, key=lambda c: (-sc[c], c)):
            g = ind.at(c, cal[t])
            if g is not None and cnt.get(g, 0) >= k:
                continue
            got.append(c)
            if g is not None:
                cnt[g] = cnt.get(g, 0) + 1
            if len(got) == top_n:
                break
        out.append((t, x, got))
    return out


# ── D3：熔斷不偷看 ─────────────────────────────────────────────────────────────

def ks_overlay(nav: list[float], bench: list[float], mult: float | None = None, fixed: float | None = None,
               warm: int = S.D3_WARM) -> tuple[list[float], list[dict]]:
    """逐日淨值（策略、大盤同一串日子）→ 加上熔斷之後的淨值與事件。每一天的門檻＝那天以前紙上最大落後 × mult（或固定 fixed）；
    前 warm 天不熔斷。觸發／恢復照 ksspec：第 i 天收盤發現 → 第 i＋ACT_LAG 天收盤換現金／買回；恢復＝紙上相對淨值回到觸發那天；
    恢復之後最高點重新算。"""
    from . import ksspec as K
    rel = K.rel_series(nav, bench)
    paper, _ = K.lag(rel)
    run_max, bnd = 0.0, []
    for i, d in enumerate(paper):
        bnd.append(math.inf if i < warm else (fixed if fixed is not None else mult * run_max))
        if d is not None:
            run_max = max(run_max, d)
    hold = [True] * len(nav)
    ev, paused, r_trig, pk = [], False, None, None
    off_from = None
    for i, r in enumerate(rel):
        if r is None:
            continue
        if paused:
            if K.AUTO_RESUME and r >= r_trig * (1 - K.EPS):
                ev.append({"i": i, "k": "resume"})
                for j in range(off_from, min(len(nav), i + K.ACT_LAG + 1)):
                    hold[j] = False
                paused, pk, off_from = False, r, None
            continue
        if pk is None or r >= pk * (1 - K.EPS):
            pk = max(r, pk or r)
        if 1.0 - r / pk > bnd[i]:
            ev.append({"i": i, "k": "pause"})
            paused, r_trig, off_from = True, r, i + K.ACT_LAG + 1
    if paused and off_from is not None:
        for j in range(off_from, len(nav)):
            hold[j] = False
    out = [float(nav[0])]
    for i in range(1, len(nav)):
        g = nav[i] / nav[i - 1] if hold[i] and nav[i - 1] else 1.0
        out.append(out[-1] * g)
    return out, ev


# ── 判定用的三段統計 ──────────────────────────────────────────────────────────

def three(all_: dict, h1: dict, h2: dict) -> dict:
    """{"all": {"cagr", "mdd"}, "h1", "h2"}（小數；mdd 正的跌幅）。"""
    return {"all": all_, "h1": h1, "h2": h2}


def verdicts(base: dict, alts: dict, primary: dict) -> dict:
    """primary＝{"D1": 鍵, "D2": 鍵, "D3": 鍵} → 每個主做法對基準的判定。"""
    return {d: {"key": k, **S.judge(base, alts[k])} for d, k in primary.items() if k in alts}
