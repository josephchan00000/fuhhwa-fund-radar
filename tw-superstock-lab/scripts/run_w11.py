"""W11：新飆股到條件才買（規格 ../arm/lab/sxentryspec.py VER 1、../docs/lab_pick_arch_plan.md 第 7 節，跑之前寫定）。

名單、8 格、新上名單先、抱 60 天同 W10 挑出來的那一組（sxfixspec 的 s8-new-off-h60），只換進場：
E0 現在、E1 開低、E2 拉回 10 日線下、E3 創 20 日新高、E4 一半一半（另外只描述 E0r：下一個交易日開盤買、不遞補）。
    python3 scripts/run_w11.py          → reports/W11_results.json＋W11_results.md
    python3 scripts/run_w11.py --smoke  → 只取 150 檔試跑（不寫檔、不記試驗）
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import run_w7 as W7  # noqa: E402
import run_w10 as R10  # noqa: E402
from superstock import engine as EN  # noqa: E402
from arm.lab import sxentryspec as S  # noqa: E402
from arm.lab import sxfixspec as F  # noqa: E402

REPORTS = ROOT / "reports"
LOG = print


class WaitSim(R10.Sim):
    """N8 的 8 格（R10.Sim）＋E1 的開低條件：開盤不比前一天收盤低就不買（那天的單作廢，隔天再看）。"""

    def _buy(self, i, o, px_adj, how):
        if o.tag == "E1":
            m = self.m
            if not (i > 0 and EN._ok(m.c[i - 1, o.s]) and m.o[i, o.s] < m.c[i - 1, o.s]):
                return False
        return super()._buy(i, o, px_adj, how)


def run_wait(ctx, mask: np.ndarray, wk: list[int], e: str, start: str):
    """E1–E3、E0r（預約制）：名單日收盤把空格依 N8 的順序分給要等的股票，每一檔等自己的條件；等不到不遞補。
    → (Result, 預約統計)。"""
    m = ctx.m
    size = F.SIZE[S.BASE[0]]
    n = size["slots"]
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=None, max_positions=size["max_pos"])
    rs = ctx.F["rs"]
    st = R10.streaks(m, mask, wk)
    by_day: dict[int, list] = {}
    for i, j in zip(*np.nonzero(mask)):
        by_day.setdefault(int(i), []).append((int(j), float(np.nan_to_num(rs[i, j])) - 1000.0 * (int(st[i, j]) - 1)))
    cdf = pd.DataFrame(m.c)
    ma = cdf.rolling(S.E2_MA, min_periods=S.E2_MA).mean().to_numpy()
    hi = cdf.shift(1).rolling(S.E3_HIGH, min_periods=S.E3_HIGH).max().to_numpy()
    last_k = {"E2": S.E2_DAYS, "E3": S.E3_DAYS}.get(e, 0)
    W = S.window(e)
    wait: dict[int, dict] = {}
    stats = {"reserved": 0, "filled": 0, "expired": 0, "wait_days": []}

    def hit(i: int, s: int) -> bool:
        c = m.c[i, s]
        if not EN._ok(c):
            return False
        if e == "E2":
            return EN._ok(ma[i, s]) and c < ma[i, s]
        return EN._ok(hi[i, s]) and c > hi[i, s]

    def decide(i: int, sim: EN.Simulator) -> list:
        for s, p in sim.pos.items():                       # 出場同 W10 的 h60：第 60 個交易日收盤到期、隔天開盤賣
            if not p.exit_pending and EN._ok(m.c[i, s]) and i - p.entry_i >= F.HOLD_N:
                p.exit_pending = "time"
        for s in list(wait):                               # 買到的、過了最晚能買那天的
            r = wait[s]
            if s in sim.pos and sim.pos[s].entry_i > r["w"]:
                stats["filled"] += 1
                stats["wait_days"].append(int(sim.pos[s].entry_i - r["w"]))
                del wait[s]
            elif i + 1 > r["w"] + W:
                stats["expired"] += 1
                del wait[s]
        if i in by_day:                                    # 名單日：空格依 N8 的順序預約
            free = n - sum(1 for p in sim.pos.values() if not p.exit_pending) - len(wait)
            for s, sc in sorted(by_day[i], key=lambda x: -x[1]):
                if free <= 0:
                    break
                if s in sim.pos or s in wait:
                    continue
                wait[s] = {"w": i, "sc": sc, "hit": False}
                stats["reserved"] += 1
                free -= 1
        out = []
        for s, r in wait.items():                          # 明天開盤要試的單
            k = i - r["w"]
            if e == "E0r":
                go = k == 0
            elif e == "E1":
                go = 0 <= k < S.E1_DAYS                    # 開不開低在 WaitSim._buy 看
            else:
                if not r["hit"] and 1 <= k <= last_k and hit(i, s):
                    r["hit"] = True
                go = r["hit"]                              # 條件出現後每天開盤試，直到買到或過期
            if go:
                out.append(EN.Order(s, "open", weight=float("nan"), score=r["sc"], tag=e))
        return out

    sim = WaitSim(m, cfg, size)
    res = sim.run(decide, start)
    stats["waiting_at_end"] = len(wait)
    wd = stats.pop("wait_days")
    stats["wait_med"] = float(np.median(wd)) if wd else None
    return res, stats


def blend(a: EN.Result, b: EN.Result, w: float) -> EN.Result:
    """E4：w 的錢照 a、其餘照 b，兩邊各自買賣、從頭到尾不互相調整。"""
    eq = w * a.equity / a.equity.iloc[0] + (1 - w) * b.equity / b.equity.iloc[0]
    eq = eq * a.equity.iloc[0]
    tr = pd.concat([a.trades, b.trades], ignore_index=True)
    return EN.Result(eq.rename("equity"), tr, (w * a.exposure + (1 - w) * b.exposure).rename("exposure"),
                     a.turnover_value + b.turnover_value, list(a.entries) + list(b.entries))


def main(smoke: bool = False) -> None:
    t0 = time.time()
    P = R10.prep(smoke)
    m, el, mask, wk, ctx = P["m"], P["el"], P["mask"], P["wk"], P["ctx"]
    LOG(f"[w11] 面板、特徵、名單 {time.time() - t0:.0f} 秒")
    W10R = json.loads((REPORTS / "W10_results.json").read_text("utf-8"))
    if W10R.get("pick") != F.name(S.BASE):
        raise SystemExit(f"W10 挑出來的是 {W10R.get('pick')}，不是規格寫的 {F.name(S.BASE)}")

    results: dict[str, EN.Result] = {}
    stats: dict[str, dict] = {}
    results["E0"] = R10.run(ctx, mask, wk, S.BASE, S.START)
    got, want = W7.curve_stats(results["E0"].equity)["cagr"]["all"], W10R["runs"][W10R["pick"]]["cagr"]["all"]
    LOG(f"[w11] E0 重建：{got * 100:.4f}%（W10 存的 {want * 100:.4f}%）")
    if not smoke and abs(got - want) > 1e-9:
        raise SystemExit("E0 重建和 W10 不一樣，不出結果")
    for e in ("E1", "E2", "E3", "E0r"):
        results[e], stats[e] = run_wait(ctx, mask, wk, e, S.START)
    a, b, w = S.E4_MIX
    results["E4"] = blend(results[a], results[b], w)

    runs, out = {}, {}
    for e in S.ENTRY + S.DESCRIBE:
        res = results[e]
        cs = W7.curve_stats(res.equity)
        runs[e] = cs
        out[e] = {**cs, "trades": W7.trade_stats(res), "wait": stats.get(e), "capture": R10.capture(m, el, res)}
        if not smoke and e != "E0":                     # E0＝W10 那一組，W10 已經記過
            EN.evaluate(f"W11_{e}", "trade", res, {"w11": e, "spec": f"sxentryspec VER {S.VER}", "base": F.name(S.BASE),
                                                  "start": S.START, "data": "lab-A8"}, m, reports_dir=REPORTS, allow_holdout=True)
        LOG(f"[w11] {e} {S.NAMES[e]}：{cs['cagr']['all'] * 100:.1f}%（{cs['cagr']['h1'] * 100:.1f}／{cs['cagr']['h2'] * 100:.1f}）"
            f"回落 {cs['mdd']['all'] * 100:.0f}%，{out[e]['trades'].get('n')} 筆，等待 {stats.get(e)}")
    v, pk = S.verdict({e: runs[e] for e in S.ENTRY})
    tr_all = m.index_tr.dropna()
    bench = W7.curve_stats(tr_all[tr_all.index >= pd.Timestamp(S.START)])
    res = {"ver": S.VER, "spec": S.SPEC_DATE, "made": time.strftime("%Y-%m-%d"), "last": str(m.dates[-1].date()),
           "base": F.name(S.BASE), "verdict": v, "pick": pk, "runs": out, "bench_tr": bench}
    LOG(f"[w11] 挑出 {pk}；判定：{v}；{time.time() - t0:.0f} 秒")
    if smoke:
        return
    (REPORTS / "W11_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), "utf-8")
    report()


def _p(x, d=1, sign=False):
    if x is None:
        return "—"
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def report() -> None:
    R = json.loads((REPORTS / "W11_results.json").read_text("utf-8"))
    pk = R["pick"]
    L = ["# W11　新飆股到條件才買：結果", "",
         f"規格：`arm/lab/sxentryspec.py` VER {R['ver']}（{R['spec']}，跑之前 commit）；規劃 `docs/lab_pick_arch_plan.md` 第 7 節。"
         f"資料到 {R['last']}。數字由 `scripts/run_w11.py` 產生。名單、8 格、新上名單先、抱 60 天同 W10 挑出來的那一組（{R['base']}）。", "",
         f"## 判定：{R['verdict']}（2019–2022 挑出來的是 {pk}・{S.NAMES.get(pk, '—') if pk else '—'}）", "",
         "| 進場 | 整段年化 | 2019–2022 | 2023 起 | 最大回落 | 2019–2022 回落 | 筆數 | 賺錢比例 | 每筆中位數 | 平均持股比例 | 預約／等到／沒等到 | 等幾天 | 每年前 30 檔買到 | 買到時已走完 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for e, s in R["runs"].items():
        t, wt, ca = s["trades"], s.get("wait") or {}, s.get("capture") or {}
        tag = "（只描述）" if e in S.DESCRIBE else ("（挑出來的）" if e == pk and e != "E0" else "")
        wtxt = f"{wt['reserved']}／{wt['filled']}／{wt['expired']}" if wt else "—"
        L.append(f"| {e} {S.NAMES[e]}{tag} | {_p(s['cagr']['all'])} | {_p(s['cagr']['h1'])} | {_p(s['cagr']['h2'])} | "
                 f"{_p(s['mdd']['all'], 0)} | {_p(s['mdd']['h1'], 0)} | {t.get('n')} | {_p(t.get('win'), 0)} | {_p(t.get('med'), 1, True)} | "
                 f"{_p(t.get('exposure'), 0)} | {wtxt} | {wt.get('wait_med') if wt.get('wait_med') is not None else ('1' if e == 'E0' else '—')} | "
                 f"{ca.get('bought', '—')} | {_p(ca.get('done_med'), 0)} |")
    b = R["bench_tr"]
    L += ["", f"加權報酬指數同期：整段 {_p(b['cagr']['all'])}、2019–2022 {_p(b['cagr']['h1'])}、2023 起 {_p(b['cagr']['h2'])}、"
          f"最大回落 {_p(b['mdd']['all'], 0)}。", "",
          "等幾天＝名單日到真正買進隔了幾個交易日（中位數）；平均持股比例＝每天股票市值占總資產的平均。", "",
          "## 逐年", "", "| 年 | " + " | ".join(R["runs"]) + " | 加權報酬指數 |", "| --- " * (len(R["runs"]) + 2) + "|"]
    years = sorted(R["runs"]["E0"]["yearly"])
    for y in years:
        L.append(f"| {y} | " + " | ".join(_p(R["runs"][e]["yearly"].get(y)) for e in R["runs"]) + f" | {_p(b['yearly'].get(y))} |")
    L.append("")
    (REPORTS / "W11_results.md").write_text("\n".join(L), "utf-8")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        main(smoke="--smoke" in sys.argv)
