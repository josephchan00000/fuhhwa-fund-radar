"""W10：新飆股的買賣做法（規格 ../arm/lab/sxfixspec.py VER 1、../docs/lab_boom_v2_plan.md，跑之前寫定）。

選股不動（W7 的 R60 名單），只換部位、先買誰、漲太遠先不買、到期續抱，24 組。
    python3 scripts/run_w10.py          → reports/W10_results.json＋W10_results.md
    python3 scripts/run_w10.py --smoke  → 只取 150 檔試跑（不寫檔、不記試驗）
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
import run_w9 as W9  # noqa: E402
from superstock import combos as CB  # noqa: E402
from superstock import engine as EN  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402
from arm.lab import superfixspec as X  # noqa: E402
from arm.lab import superx as SX  # noqa: E402
from arm.lab import sxfixspec as S  # noqa: E402

REPORTS = ROOT / "reports"
LOG = print


class Sim(EN.Simulator):
    """固定 N 格：有空格時把現金平分給空格；一格不到總資產 1/N 的 MIN_SLOT 就不買。"""

    def __init__(self, m, cfg, size: dict):
        super().__init__(m, cfg, exit_flags=None, mf=np.ones(m.n, dtype=bool))
        self.size = size

    def _buy(self, i, o, px_adj, how):
        n = self.size["slots"]
        if n:
            free = n - len(self.pos)
            eq = self.eq_prev
            if free <= 0 or eq <= 0:
                return False
            per = self.cash / free
            if per < S.MIN_SLOT * eq / n:
                return False
            o.weight = per / eq
        return super()._buy(i, o, px_adj, how)


def streaks(m, mask: np.ndarray, wk: list[int]) -> np.ndarray:
    """每個週末：到這個週末為止連續幾個週末在名單上（不在名單上＝0）。"""
    out = np.zeros(mask.shape, dtype=np.int16)
    run = np.zeros(mask.shape[1], dtype=np.int16)
    for i in wk:
        run = np.where(mask[i], run + 1, 0).astype(np.int16)
        out[i] = run
    return out


def run(ctx: CB.Ctx, mask: np.ndarray, wk: list[int], g: tuple, start: str) -> EN.Result:
    m = ctx.m
    sz, order, ext, hold = g
    size = S.SIZE[sz]
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=None, max_positions=size["max_pos"])
    rs = ctx.F["rs"]
    st = streaks(m, mask, wk)
    with np.errstate(invalid="ignore"):
        far = m.c > S.EXT_MA50 * ctx.ma(50)
    by_day: dict[int, list] = {}
    for i, j in zip(*np.nonzero(mask)):
        if ext == "on" and far[i, j]:
            continue
        sc = float(np.nan_to_num(rs[i, j]))
        if order == "new":
            sc -= 1000.0 * (int(st[i, j]) - 1)
        by_day.setdefault(int(i), []).append((int(j), sc))
    last_wk = np.full(m.n, -1, dtype=np.int64)
    k = -1
    wset = set(wk)
    for i in range(m.n):
        if i in wset:
            k = i
        last_wk[i] = k
    due: dict[tuple, int] = {}

    def decide(i: int, sim: EN.Simulator) -> list:
        for s, p in sim.pos.items():
            if p.exit_pending or not EN._ok(m.c[i, s]):
                continue
            held = i - p.entry_i
            d = due.get((s, p.entry_i), S.HOLD_N)
            if held >= d:
                w = last_wk[i]
                if hold == "renew" and held < S.HOLD_MAX and w >= 0 and mask[w, s]:
                    due[(s, p.entry_i)] = min(d + S.HOLD_N, S.HOLD_MAX)
                else:
                    p.exit_pending = "time"
        return [EN.Order(s, "open", weight=size["weight"] if size["weight"] else float("nan"), score=sc)
                for s, sc in by_day.get(i, [])]

    return Sim(m, cfg, size).run(decide, start, None)


def crumbs(res: EN.Result) -> dict:
    t = res.trades
    if t is None or not len(t):
        return {}
    eq = res.equity
    w = t.apply(lambda r: r["cost_in"] / eq.asof(pd.Timestamp(r["entry_date"])), axis=1)
    small = w < 0.03
    pnl = t["pnl"]
    return {"n_small": int(small.sum()), "share_small": float(small.mean()),
            "pnl_small": float(pnl[small].sum() / pnl.sum()) if pnl.sum() else None, "w_med": float(w.median())}


def capture(m, el: np.ndarray, res: EN.Result, years=range(2019, 2027), top: int = 30) -> dict:
    """每年漲最多的 top 檔：買到幾檔、買到時這一年的漲幅已走完幾成（對數，中位數）。"""
    c = m.c_ff
    yr = np.array([d.year for d in m.dates])
    t = res.trades
    ix = {d: i for i, d in enumerate(m.dates)}
    out = {}
    for y in years:
        ii = np.nonzero(yr == y)[0]
        if not len(ii) or ii[0] == 0:
            continue
        a, b = ii[0] - 1, ii[-1]
        ok = el[ii].any(axis=0) & np.isfinite(c[a]) & np.isfinite(c[b])
        ret = np.where(ok, c[b] / c[a] - 1, np.nan)
        best = np.argsort(-np.nan_to_num(ret, nan=-9))[:top]
        got, done = 0, []
        for j in best:
            s = m.stocks[j]
            tr = t[(t["stock_id"] == s) & (pd.to_datetime(t["entry_date"]).dt.year == y)] if len(t) else t
            if len(tr):
                got += 1
                ei = ix[pd.Timestamp(tr["entry_date"].iloc[0])]
                if c[b, j] > c[a, j]:
                    done.append(float(np.log(c[ei, j] / c[a, j]) / np.log(c[b, j] / c[a, j])))
        out[int(y)] = {"bought": got, "done": float(np.median(done)) if done else None}
    tot = sum(v["bought"] for v in out.values())
    dn = [v["done"] for v in out.values() if v["done"] is not None]
    return {"years": out, "bought": tot, "done_med": float(np.median(dn)) if dn else None}


def main(smoke: bool = False) -> None:
    t0 = time.time()
    rows = W9.samples(150 if smoke else None)
    codes = sorted({r["c"] for r in rows}) if smoke else None
    m, extra = LP.load(codes=codes)
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    el = F["elig"]
    mix = {pd.Timestamp(d): i for i, d in enumerate(m.dates)}
    W7R = json.loads((REPORTS / "W7_results.json").read_text("utf-8"))
    FO = {(f["lab"], f["y"]): f for f in W7R["folds"]}
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    mk = np.zeros(m.c.shape, dtype=bool)
    for y in X.FOLDS:
        preds = [SX.rule_pred([tuple(c) for c in rr["conds"]]) for rr in FO[("R60", y)]["rules"]]
        for r in by_year.get(y, []):
            if preds and any(p(r["f"]) for p in preds):
                i, j = mix.get(pd.Timestamp(r["d"])), m.col.get(r["c"])
                if i is not None and j is not None:
                    mk[i, j] = True
    mask = mk & el
    wk = sorted({mix[pd.Timestamp(d)] for d in {r["d"] for r in rows} if pd.Timestamp(d) in mix})
    ctx = CB.Ctx(m, F, fund, [], CB.rev_days(list(extra["cal"])))
    LOG(f"[w10] 面板、特徵、名單 {time.time() - t0:.0f} 秒")

    runs, out = {}, {}
    for g in S.GRID:
        res = run(ctx, mask, wk, g, S.START)
        cs = W7.curve_stats(res.equity)
        runs[g] = cs
        out[S.name(g)] = {**cs, "trades": W7.trade_stats(res), "crumbs": crumbs(res), "capture": capture(m, el, res)}
        if g == S.CURRENT:
            want = W7R["runs"]["R60"]["cagr"]["all"]
            LOG(f"[w10] 現行重建：{cs['cagr']['all'] * 100:.4f}%（W7 存的 {want * 100:.4f}%）")
            if not smoke and abs(cs["cagr"]["all"] - want) > 1e-9:
                raise SystemExit("現行重建和 W7 不一樣，不出結果")
        if not smoke:
            EN.evaluate(f"W10_{S.name(g)}", "trade", res, {"w10": S.name(g), "spec": f"sxfixspec VER {S.VER}", "start": S.START,
                                                          "data": "lab-A8"}, m, reports_dir=REPORTS, allow_holdout=True)
        LOG(f"[w10] {S.name(g)}：{cs['cagr']['all'] * 100:.1f}%（{cs['cagr']['h1'] * 100:.1f}／{cs['cagr']['h2'] * 100:.1f}）"
            f"回落 {cs['mdd']['all'] * 100:.0f}%，{out[S.name(g)]['trades'].get('n')} 筆")
    v, g = S.verdict(runs)
    tr_all = m.index_tr.dropna()
    bench = W7.curve_stats(tr_all[tr_all.index >= pd.Timestamp(S.START)])
    res = {"ver": S.VER, "spec": S.SPEC_DATE, "made": time.strftime("%Y-%m-%d"), "last": str(m.dates[-1].date()),
           "verdict": v, "pick": S.name(g) if g else None, "current": S.name(S.CURRENT), "runs": out, "bench_tr": bench}
    LOG(f"[w10] 挑出 {res['pick']}；判定：{v}；{time.time() - t0:.0f} 秒")
    if smoke:
        return
    (REPORTS / "W10_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), "utf-8")
    report()


NM = {"cur": "現行部位", "s10": "10 格", "s8": "8 格", "rs": "強度先", "new": "新上名單先", "off": "不管漲太遠", "on": "漲太遠不買",
      "h60": "抱 60 天", "renew": "還在名單續抱"}


def _p(x, d=1, sign=False):
    if x is None:
        return "—"
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def report() -> None:
    R = json.loads((REPORTS / "W10_results.json").read_text("utf-8"))
    cur, pk = R["current"], R["pick"]
    L = ["# W10　新飆股的買賣做法：結果", "",
         f"規格：`arm/lab/sxfixspec.py` VER {R['ver']}（{R['spec']}，跑之前 commit）；規劃 `docs/lab_boom_v2_plan.md`。"
         f"資料到 {R['last']}。數字由 `scripts/run_w10.py` 產生。", "",
         f"## 判定：{R['verdict']}（2019–2022 挑出來的是 {'・'.join(NM[x] for x in pk.split('-')) if pk else '—'}）", "",
         "| 組合 | 整段年化 | 2019–2022 | 2023 起 | 最大回落 | 2019–2022 回落 | 筆數 | 賺錢比例 | 每筆中位數 | 零頭筆數 | 每年前 30 檔買到 | 買到時已走完 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, s in R["runs"].items():
        t, cr, ca = s["trades"], s.get("crumbs") or {}, s.get("capture") or {}
        tag = "（現行）" if k == cur else ("（挑出來的）" if k == pk else "")
        L.append(f"| {'・'.join(NM[x] for x in k.split('-'))}{tag} | {_p(s['cagr']['all'])} | {_p(s['cagr']['h1'])} | {_p(s['cagr']['h2'])} | "
                 f"{_p(s['mdd']['all'], 0)} | {_p(s['mdd']['h1'], 0)} | {t.get('n')} | {_p(t.get('win'), 0)} | {_p(t.get('med'), 1, True)} | "
                 f"{cr.get('n_small', '—')} | {ca.get('bought', '—')} | {_p(ca.get('done_med'), 0)} |")
    b = R["bench_tr"]
    L += ["", f"加權報酬指數同期：整段 {_p(b['cagr']['all'])}、2019–2022 {_p(b['cagr']['h1'])}、2023 起 {_p(b['cagr']['h2'])}、"
          f"最大回落 {_p(b['mdd']['all'], 0)}。", ""]
    if pk:
        P, C = R["runs"][pk], R["runs"][cur]
        L += ["## 逐年（挑出來的那一組對現行）", "", "| 年 | 挑出來的 | 現行 | 加權報酬指數 |", "| --- | --- | --- | --- |"]
        for y in sorted(C["yearly"]):
            L.append(f"| {y} | {_p(P['yearly'].get(y))} | {_p(C['yearly'].get(y))} | {_p(b['yearly'].get(y))} |")
        L.append("")
    (REPORTS / "W10_results.md").write_text("\n".join(L), "utf-8")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        main(smoke="--smoke" in sys.argv)
