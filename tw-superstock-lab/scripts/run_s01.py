"""P4.0：S01 SEPA（《超級績效》）在 lab 面板上的 IS／VAL 回測（規則與細節：reports/P4_S01_plan.md）。保留期上鎖。

    .venv/bin/python scripts/run_s01.py           → reports/P4_S01_sepa_lab.{md,json}，試驗附加到 reports/trials.csv
    .venv/bin/python scripts/run_s01.py --quick   → 只跑主規格（檢查用，不寫報告、不記試驗）
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from superstock import engine as EN  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402
from superstock import strategies as ST  # noqa: E402

REPORTS = ROOT / "reports"
PER = {"IS": ("2014-01-02", "2019-12-31"), "VAL": ("2020-01-02", "2022-12-30")}
LOG = print


# ---------------------------------------------------------------------------------------------- 對照組
def ew_level(m: EN.Market, elig: np.ndarray) -> pd.Series:
    """B1：每天依前一天合格名單等權（不計成本）；單日漲跌超過 11% 當資料錯誤不計。"""
    c = m.c
    with np.errstate(invalid="ignore", divide="ignore"):
        r = c[1:] / c[:-1] - 1
    ok = elig[:-1] & ~np.isnan(r) & (np.abs(r) <= 0.11)
    s = np.where(ok, r, 0.0).sum(axis=1)
    n = ok.sum(axis=1)
    daily = np.where(n > 0, s / np.maximum(n, 1), 0.0)
    lv = np.concatenate([[1.0], np.cumprod(1 + daily)])
    return pd.Series(lv, index=m.dates)


def seg_stats(level: pd.Series, a: str, b: str) -> dict:
    x = level[(level.index >= pd.Timestamp(a)) & (level.index <= pd.Timestamp(b))].dropna()
    return {"cagr": EN._cagr(x), "maxdd": EN.max_drawdown(x)}


def yearly(eq: pd.Series) -> dict[int, float]:
    out, prev = {}, None
    for y in sorted(set(eq.index.year)):
        e = eq[eq.index.year == y]
        base = prev if prev is not None else e.iloc[0]
        out[int(y)] = float(e.iloc[-1] / base - 1)
        prev = e.iloc[-1]
    return out


# ---------------------------------------------------------------------------------------------- 逐筆分析
def trade_view(tr: pd.DataFrame, names: dict, k: int = 10) -> dict:
    if tr is None or tr.empty:
        return {"n": 0}
    t = tr.copy()
    t["name"] = t["stock_id"].map(lambda c: names.get(c, c))
    reasons = t["reason"].value_counts().to_dict()
    pos = t[t["pnl"] > 0]["pnl"].sort_values(ascending=False)
    top10 = pos.iloc[: max(1, int(math.ceil(len(t) * 0.10)))].sum() if len(pos) else 0.0
    total = float(t["pnl"].sum())
    cols = ["stock_id", "name", "entry_date", "exit_date", "ret", "hold_days", "reason"]

    def rows(d):
        return [{**{c: (str(r[c].date()) if c.endswith("_date") else r[c]) for c in cols},
                 "ret": round(float(r["ret"]), 4)} for _, r in d.iterrows()]
    big = t["ret"]
    return {
        "n": int(len(t)), "reasons": {str(a): int(b) for a, b in reasons.items()},
        "win": float((t["pnl"] > 0).mean()), "avg": float(big.mean()), "med": float(big.median()),
        "avg_win": float(big[big > 0].mean()) if (big > 0).any() else None,
        "avg_loss": float(big[big <= 0].mean()) if (big <= 0).any() else None,
        "ge50": int((big >= 0.5).sum()), "ge100": int((big >= 1.0).sum()),
        "top10_share": float(top10 / total) if total > 0 else None, "pnl": total,
        "best": rows(t.sort_values("ret", ascending=False).head(k)),
        "worst": rows(t.sort_values("ret").head(k)),
        "hold_med": float(t["hold_days"].median()),
    }


# ---------------------------------------------------------------------------------------------- S20：現行飆股規則
def s20_signals(log=LOG) -> pd.DataFrame:
    """fuhhwa 機會頁的 A 規則（superx v2）：每週最後一個交易日收盤符合任一條 → 訊號。"""
    LP.arm()
    sys.path.insert(0, str(LP.REPO / "scripts"))
    import run_super  # noqa: WPS433
    from arm.lab import superx as SX  # noqa: WPS433

    res = SX.load_res()
    rules = SX.live_rules(res)
    preds = [SX.rule_pred([tuple(c) for c in conds]) for _, conds in rules]
    rows = run_super.samples(log=log)
    out = [{"date": pd.Timestamp(r["d"]), "stock_id": r["c"], "entry": "open", "stop_pct": 0.08,
            "score": float(r["f"].get("rs") or 0), "tag": "S20"}
           for r in rows if any(p(r["f"]) for p in preds)]
    return pd.DataFrame(out)


def hold_study(m: EN.Market, sig: pd.DataFrame, n: int = 60, cost: float = 0.006) -> dict:
    """照做頁面上的「3 個月後」：訊號隔天開盤買、第 60 個交易日收盤賣，不停損（每筆獨立，不受資金限制）。"""
    rs = []
    for r in sig.itertuples(index=False):
        j = m.col.get(r.stock_id)
        i = m.i_of(r.date)
        if j is None or i + 1 + n >= m.n:
            continue
        o = m.o[i + 1, j]
        x = m.c_ff[min(i + n, m.last[j]), j]
        if o == o and x == x and o > 0 and not m.lu[i + 1, j]:
            rs.append(x / o - 1 - cost)
    a = np.array(rs)
    return {"n": int(len(a)), "avg": float(a.mean()) if len(a) else None, "med": float(np.median(a)) if len(a) else None,
            "win": float((a > 0).mean()) if len(a) else None}


# ---------------------------------------------------------------------------------------------- 報告（表格全由程式產生）
def _p(x, d: int = 1) -> str:
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x * 100:.{d}f}%"


def _f(x, d: int = 2) -> str:
    return "—" if x is None or (isinstance(x, float) and x != x) else f"{x:.{d}f}"


VNAME = {"S01": "主規格（SPEC S01）", "S01_stop_entry": "盤中漲過樞紐就買", "S01_no_market": "拿掉大盤濾網",
         "S01_fund": "＋EPS 年增≥25%、營收年增≥20%", "S01_code33": "＋Code 33", "S01_be3": "保本改 3R",
         "S01_no_be": "不移到保本", "S01_no_vcp": "不看 VCP（樣板＋創 50 日新高）", "S01_no_tt": "不看趨勢樣板",
         "S20_sepa_exit": "現行飆股規則＋同一套出場"}
REASON = {"stop": "停損（含保本後停損）", "rule": "跌破 50 日線", "end": "期末出清", "delisted": "下市", "time": "到期"}


def write_md(out: dict) -> str:
    L = ["# P4.0　S01 SEPA（《超級績效》）lab 面板回測結果", "",
         f"規則與細節：`reports/P4_S01_plan.md`（v1，跑結果前 commit）。資料：fuhhwa data/lab（{out['panel']['start']}～"
         f"{out['panel']['end']}，{out['panel']['stocks']} 檔，含已下市）。保留期（2023 起）上鎖、沒有打開。"
         "表格全部由 `scripts/run_s01.py` 產生。", ""]
    m0 = out["runs"]["S01"]
    L += ["## 1. 主規格 vs 大盤", "",
          "| 期間 | 年化 | 最大回落 | 加權報酬指數 年化／回落 | 合格股等權 年化／回落 | 交易數 | 勝率 | 賺賠比 | 每筆期望值 | 平均持有（日） | 平均持股 | 進場後 60 日 +50% 的比例（基準） |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in PER:
        x, b = m0[p]["metrics"], out["bench"][p]
        L.append(f"| {p} | {_p(x['cagr'])} | {_p(x['maxdd'])} | {_p(b['B0_taiex_tr']['cagr'])}／{_p(b['B0_taiex_tr']['maxdd'])} | "
                 f"{_p(b['B1_equal_weight']['cagr'])}／{_p(b['B1_equal_weight']['maxdd'])} | {x['trades']} | {_p(x['win_rate'], 0)} | "
                 f"{_f(x['payoff'])} | {_p(x['expectancy'])} | {_f(x['avg_hold'], 0)} | {_p(x['exposure'], 0)} | "
                 f"{_p(x.get('y_A_precision'))}（{_p(x.get('y_A_base'))}） |")
    gate = m0["VAL"]["metrics"]
    ok = (gate.get("excess_cagr") or -1) > 0 and gate["maxdd"] >= (gate.get("bench_maxdd") or 0)
    L += ["", f"GATE P4 標準（VAL 扣成本後年化超額 > 0，且 VAL 最大回落不比加權報酬指數深）："
              f"超額 {_p(gate.get('excess_cagr'))}、回落 {_p(gate['maxdd'])} vs {_p(gate.get('bench_maxdd'))} → "
              f"**{'通過' if ok else '未通過'}**", ""]
    L += ["## 2. 變體（只看各環節的貢獻，不拿來挑新主規格）", "",
          "| 變體 | IS 年化 | IS 超額 | IS 回落 | IS 筆數 | IS 勝率 | IS 期望值 | VAL 年化 | VAL 超額 | VAL 回落 | VAL 筆數 | VAL 勝率 | VAL 期望值 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for k, r in out["runs"].items():
        if k.startswith("S01_grid"):
            continue
        c = []
        for p in PER:
            x = r[p]["metrics"]
            c += [_p(x["cagr"]), _p(x.get("excess_cagr")), _p(x["maxdd"]), str(x["trades"]), _p(x["win_rate"], 0),
                  _p(x["expectancy"])]
        L.append(f"| {VNAME.get(k, k)} | " + " | ".join(c) + " |")
    L += ["", "## 3. 參數鄰近（停損 × 突破量，年化超額 IS／VAL）", "", "| 停損＼量 | 1.25 倍 | 1.5 倍 | 2.0 倍 |",
          "| --- | --- | --- | --- |"]
    for sp in ST.GRID["stop_pct"]:
        row = [f"{_p(out['grid'][f'stop{int(sp * 100)}_vol{v:g}']['IS'])}／{_p(out['grid'][f'stop{int(sp * 100)}_vol{v:g}']['VAL'])}"
               for v in ST.GRID["vol"]]
        L.append(f"| {int(sp * 100)}% | " + " | ".join(row) + " |")
    pos = {p: sum(1 for g in out["grid"].values() if (g[p] or -1) > 0) for p in PER}
    L += ["", f"超額為正：IS {pos['IS']}／9 組、VAL {pos['VAL']}／9 組。", ""]
    L += ["## 4. 主規格的交易長什麼樣子", ""]
    for p in PER:
        t = m0[p]["trades"]
        if not t.get("n"):
            continue
        rs = "、".join(f"{REASON.get(k, k)} {v}" for k, v in t["reasons"].items())
        L += [f"**{p}**：{t['n']} 筆；賺錢 {_p(t['win'], 0)}；平均 {_p(t['avg'])}、中位數 {_p(t['med'])}；"
              f"賺的平均 {_p(t['avg_win'])}、賠的平均 {_p(t['avg_loss'])}；單筆 ≥ +50% 有 {t['ge50']} 筆、≥ +100% 有 {t['ge100']} 筆；"
              f"最賺的 10% 交易占總獲利 {_p(t['top10_share'], 0)}；持有中位數 {t['hold_med']:.0f} 日；出場原因：{rs}。", "",
              "| 最好 10 筆 | 進場 | 出場 | 報酬 | 持有 | 出場原因 |", "| --- | --- | --- | --- | --- | --- |"]
        L += [f"| {x['stock_id']} {x['name']} | {x['entry_date']} | {x['exit_date']} | {_p(x['ret'])} | {x['hold_days']} | "
              f"{REASON.get(x['reason'], x['reason'])} |" for x in t["best"]]
        L += ["", "| 最差 10 筆 | 進場 | 出場 | 報酬 | 持有 | 出場原因 |", "| --- | --- | --- | --- | --- | --- |"]
        L += [f"| {x['stock_id']} {x['name']} | {x['entry_date']} | {x['exit_date']} | {_p(x['ret'])} | {x['hold_days']} | "
              f"{REASON.get(x['reason'], x['reason'])} |" for x in t["worst"]]
        L.append("")
    L += ["## 5. 逐年（主規格 vs 加權報酬指數）", "", "| 年 | 主規格 | 加權報酬指數 |", "| --- | --- | --- |"]
    for p, (s, e) in PER.items():
        for y, v in m0[p]["yearly"].items():
            L.append(f"| {y} | {_p(v)} | {_p(out['bench_yearly'].get(str(y)))} |")
    L += ["", "## 6. 對照：現行飆股規則（機會頁 A 規則）", "",
          "這 5 條規則是用 2014–2022 找出、選定的，IS／VAL 對它們不是樣本外，成績偏好看。", "",
          "| 期間 | 套同一套出場：年化／超額／回落 | 筆數 | 勝率 | 期望值 | 照頁面持有 60 日：筆數 | 平均 | 中位數 | 賺錢比例 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p in PER:
        x = out["runs"]["S20_sepa_exit"][p]["metrics"]
        h = out["s20"][f"hold60_{p}"]
        L.append(f"| {p} | {_p(x['cagr'])}／{_p(x.get('excess_cagr'))}／{_p(x['maxdd'])} | {x['trades']} | {_p(x['win_rate'], 0)} | "
                 f"{_p(x['expectancy'])} | {h['n']} | {_p(h['avg'])} | {_p(h['med'])} | {_p(h['win'], 0)} |")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------- 主程式
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    m, extra = LP.load()
    LOG(f"[s01] 面板 {len(m.stocks)} 檔、{m.n} 個交易日（{m.dates[0].date()}～{m.dates[-1].date()}），{time.time() - t0:.0f} 秒")
    F = FT.compute(m, extra["cap"])
    LOG(f"[s01] 特徵 {time.time() - t0:.0f} 秒；合格股票日 {int(F['elig'].sum()):,}、樣板全過 {int(F['tt_pass'].sum()):,}、"
        f"VCP 成立 {int(F['vcp_ok'].sum()):,}")
    yA = FT.label(m, 60, 0.5, F["elig"])
    yB = FT.label(m, 250, 1.0, F["elig"])
    ii, jj = np.nonzero(F["elig"])
    labels = pd.DataFrame({"date": m.dates[ii], "stock_id": np.array(m.stocks)[jj], "y_A": yA[ii, jj], "y_B": yB[ii, jj]})
    fund = LP.fundamentals(extra["cal"], m.stocks)
    names = {}
    try:
        from arm.lab import company  # noqa: WPS433
        names = company.names()
    except Exception as e:  # noqa: BLE001
        LOG(f"[s01] 名稱讀不到：{e}")
    ew = ew_level(m, F["elig"])
    out = {"plan": "reports/P4_S01_plan.md v1", "panel": {"stocks": len(m.stocks), "start": str(m.dates[0].date()),
           "end": str(m.dates[-1].date())}, "periods": PER, "bench": {}, "runs": {}, "grid": {}, "s20": {}}
    for p, (s, e) in PER.items():
        out["bench"][p] = {"B0_taiex_tr": seg_stats(m.index_tr, s, e), "B1_equal_weight": seg_stats(ew, s, e)}

    def go(name: str, spec: dict, sig=None, log_trial: bool = True) -> dict:
        r = {}
        for p, (s, e) in PER.items():
            res, sg = ST.run(m, F, spec, s, e, fund=fund, sig=sig)
            lab = labels[(labels["date"] >= pd.Timestamp(s)) & (labels["date"] <= pd.Timestamp(e))]
            params = {**{k: v for k, v in spec.items()}, "period": p, "data": "lab-A8"}
            if log_trial and not a.quick:
                mt = EN.evaluate(f"{name}_{p}", "trade", res, params, m, labels=lab, reports_dir=REPORTS)
            else:
                mt = res.metrics(bench=m.index_tr, labels=lab)
            r[p] = {"metrics": {k: (None if isinstance(v, float) and v != v else v) for k, v in mt.items()},
                    "signals": int(((sg["date"] >= pd.Timestamp(s)) & (sg["date"] <= pd.Timestamp(e))).sum()),
                    "trades": trade_view(res.trades, names), "yearly": yearly(res.equity)}
        LOG(f"[s01] {name}: " + "；".join(
            f"{p} 年化 {r[p]['metrics']['cagr']:.1%}、超額 {r[p]['metrics'].get('excess_cagr', float('nan')):.1%}、"
            f"回落 {r[p]['metrics']['maxdd']:.1%}、{r[p]['metrics']['trades']} 筆、勝率 {r[p]['metrics']['win_rate'] or 0:.0%}"
            for p in PER) + f"（{time.time() - t0:.0f} 秒）")
        return r

    out["runs"]["S01"] = go("S01", ST.spec_of("S01"))
    if a.quick:
        return
    for name in ST.VARIANTS:
        if name != "S01":
            out["runs"][name] = go(name, ST.spec_of(name))
    for sp in ST.GRID["stop_pct"]:
        for vol in ST.GRID["vol"]:
            k = f"stop{int(sp * 100)}_vol{vol:g}"
            r = out["runs"]["S01"] if (sp, vol) == (0.08, 1.5) else go(f"S01_grid_{k}", ST.spec_of("S01", stop_pct=sp, vol=vol))
            out["grid"][k] = {p: r[p]["metrics"].get("excess_cagr") for p in PER}
    sig20 = s20_signals()
    out["s20"]["signals"] = int(len(sig20))
    out["runs"]["S20_sepa_exit"] = go("S20_sepa_exit", ST.spec_of("S01"), sig=sig20)
    for p, (s, e) in PER.items():
        sg = sig20[(sig20["date"] >= pd.Timestamp(s)) & (sig20["date"] <= pd.Timestamp(e))]
        out["s20"][f"hold60_{p}"] = hold_study(m, sg)
    tr = m.index_tr.dropna()
    out["bench_yearly"] = {str(y): v for y, v in yearly(tr[tr.index >= pd.Timestamp(PER["IS"][0])]).items()}
    out["elapsed_s"] = round(time.time() - t0)
    (REPORTS / "P4_S01_sepa_lab.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), "utf-8")
    (REPORTS / "P4_S01_sepa_lab.md").write_text(write_md(out), "utf-8")
    LOG(f"[s01] 完成 {time.time() - t0:.0f} 秒 → reports/P4_S01_sepa_lab.{{json,md}}")


if __name__ == "__main__":
    main()
