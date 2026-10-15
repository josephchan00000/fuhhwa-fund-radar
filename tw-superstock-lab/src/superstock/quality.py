"""資料品質檢查 → reports/data_quality.md（給人看）與 data_quality.json（給程式讀）。

每一項檢查回傳 PASS / WARN / FAIL：
  FAIL 代表資料不能直接拿來研究，必須先修；WARN 代表要看一下原因；PASS 沒問題。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .adjust import limit_pct
from .config import Config
from .datasets import REGISTRY, get_spec
from .storage import GLOBAL_KEY, Manifest, Store
from .universe import reused_codes

CORE_STORES = {s.store_name for s in REGISTRY if s.group in ("meta", "core")}


@dataclass
class Check:
    id: str
    title: str
    status: str = "PASS"
    summary: str = ""
    metrics: dict = field(default_factory=dict)
    examples: list = field(default_factory=list)

    def worst(self, status: str) -> None:
        order = {"PASS": 0, "WARN": 1, "FAIL": 2}
        if order[status] > order[self.status]:
            self.status = status


def _load(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def check_downloads(manifest: Manifest) -> Check:
    c = Check("C1", "下載完成度")
    summary = manifest.summary()
    ds = manifest.datasets_table()
    rows = []
    for rec in summary.to_dict("records") if not summary.empty else []:
        total = sum(int(rec.get(k, 0)) for k in ("done", "empty", "failed"))
        failed = int(rec.get("failed", 0))
        rows.append({"dataset": rec["store"], "done": int(rec.get("done", 0)),
                     "empty": int(rec.get("empty", 0)), "failed": failed,
                     "failed_pct": round(100 * failed / total, 2) if total else 0.0})
        if rec["store"] in CORE_STORES and total and failed / total > 0.02:
            c.worst("FAIL")
        elif failed:
            c.worst("WARN")
    disabled = []
    if not ds.empty:
        for rec in ds.to_dict("records"):
            if rec.get("disabled_reason"):
                disabled.append({"dataset": rec["store"], "reason": rec["disabled_reason"]})
                c.worst("FAIL" if rec["store"] in CORE_STORES else "WARN")
    if not rows:
        c.worst("FAIL")
        c.summary = "還沒有任何下載紀錄"
    else:
        c.summary = f"{len(rows)} 個資料集；停用 {len(disabled)} 個"
    c.metrics = {"datasets": rows, "disabled": disabled}
    return c


def check_universe(universe: pd.DataFrame, info: pd.DataFrame | None,
                   delisting: pd.DataFrame | None, start_date: str) -> Check:
    c = Check("C2", "股票池")
    if universe.empty:
        c.worst("FAIL")
        c.summary = "股票池是空的"
        return c
    by_market = universe["market"].value_counts().to_dict()
    n_del = int(universe["is_delisted"].sum())
    reused = reused_codes(info, delisting, start_date)
    c.metrics = {"total": len(universe), "by_market": by_market, "delisted": n_del,
                 "reused_codes": reused[:50]}
    if n_del == 0:
        c.worst("WARN")
    if reused:
        c.worst("WARN")
    c.summary = f"共 {len(universe)} 檔（下市 {n_del} 檔）；疑似代號重複使用 {len(reused)} 個"
    return c


def check_price_integrity(prices: pd.DataFrame) -> Check:
    c = Check("C3", "價格完整性")
    if prices.empty:
        c.worst("FAIL")
        c.summary = "沒有價格資料"
        return c
    dup = int(prices.duplicated(["stock_id", "date"]).sum())
    hl = int((prices["high"] < prices["low"]).sum())
    outside = int(((prices["close"] > prices["high"] + 1e-9) | (prices["close"] < prices["low"] - 1e-9)).sum())
    zero_vol = (float((pd.to_numeric(prices["volume"], errors="coerce") == 0).mean())
                if "volume" in prices.columns else float("nan"))
    n = len(prices)
    c.metrics = {"rows": n, "stocks": int(prices["stock_id"].nunique()),
                 "first_date": str(prices["date"].min().date()), "last_date": str(prices["date"].max().date()),
                 "duplicates": dup, "high_below_low": hl, "close_outside_range": outside,
                 "zero_volume_share": round(zero_vol, 4)}
    if dup or hl / n > 1e-4:
        c.worst("FAIL")
    elif hl or outside:
        c.worst("WARN")
    c.summary = f"{n:,} 列；重複 {dup}、高<低 {hl}、收盤超出高低範圍 {outside}"
    return c


def unexplained_jumps(prices: pd.DataFrame, tolerance: float = 0.01, skip_first: int = 5) -> pd.DataFrame:
    """還原日報酬超過漲跌幅上限的日子（新股前 5 日除外）——多半是缺少還原事件或資料錯誤。"""
    if prices.empty or "ret" not in prices.columns:
        return pd.DataFrame()
    df = prices[["stock_id", "date", "ret", "close"]].copy()
    df["nth"] = df.groupby("stock_id").cumcount()
    lim = limit_pct(df["date"])
    mask = (df["nth"] >= skip_first) & (df["ret"].abs() > lim + tolerance)
    return df.loc[mask, ["stock_id", "date", "ret", "close"]].sort_values("ret", key=np.abs, ascending=False)


def check_jumps(prices: pd.DataFrame) -> Check:
    c = Check("C4", "未解釋的大漲跌（缺還原事件？）")
    jumps = unexplained_jumps(prices)
    n = len(prices) or 1
    share = len(jumps) / n
    c.metrics = {"count": len(jumps), "share": round(share, 6),
                 "stocks": int(jumps["stock_id"].nunique()) if not jumps.empty else 0}
    c.examples = [
        {"stock_id": r.stock_id, "date": str(pd.Timestamp(r.date).date()), "ret": round(float(r.ret), 4)}
        for r in jumps.head(20).itertuples(index=False)
    ]
    if share > 1e-3:
        c.worst("FAIL")
    elif len(jumps):
        c.worst("WARN")
    c.summary = f"{len(jumps)} 筆（占 {share:.4%}）"
    return c


def check_calendar(prices: pd.DataFrame, calendar: pd.DataFrame) -> Check:
    c = Check("C5", "交易日對齊")
    if prices.empty or calendar.empty:
        c.worst("WARN")
        c.summary = "缺價格或交易日資料，略過"
        return c
    cal = set(pd.to_datetime(calendar["date"]))
    price_dates = pd.to_datetime(prices["date"])
    not_in_cal = int((~price_dates.isin(cal)).sum())
    per_day = prices.groupby("date")["stock_id"].nunique()
    rolling_med = per_day.rolling(20, min_periods=5).median()
    thin = per_day[(per_day < 0.5 * rolling_med)]
    in_range = [d for d in cal if price_dates.min() <= d <= price_dates.max()]
    missing_days = sorted(set(in_range) - set(per_day.index))
    c.metrics = {"rows_not_in_calendar": not_in_cal, "thin_days": len(thin),
                 "calendar_days_without_prices": len(missing_days)}
    c.examples = [str(pd.Timestamp(d).date()) for d in list(thin.index[:10]) + missing_days[:10]]
    if not_in_cal or missing_days:
        c.worst("WARN")
    c.summary = f"非交易日資料 {not_in_cal} 列；資料稀少的交易日 {len(thin)} 天；整天缺資料 {len(missing_days)} 天"
    return c


def check_gaps(prices: pd.DataFrame, min_gap_days: int = 30) -> Check:
    c = Check("C6", "長期缺漏（停牌或資料缺）")
    if prices.empty:
        c.worst("WARN")
        return c
    df = prices[["stock_id", "date"]].sort_values(["stock_id", "date"])
    gap = df.groupby("stock_id")["date"].diff().dt.days
    big = df.assign(gap_days=gap)[gap > min_gap_days]
    c.metrics = {"gaps": len(big), "stocks": int(big["stock_id"].nunique())}
    c.examples = [{"stock_id": r.stock_id, "resume_date": str(pd.Timestamp(r.date).date()),
                   "gap_days": int(r.gap_days)}
                  for r in big.sort_values("gap_days", ascending=False).head(20).itertuples(index=False)]
    if len(big):
        c.worst("WARN")
    c.summary = f"{len(big)} 段超過 {min_gap_days} 天的空白（{c.metrics['stocks']} 檔）"
    return c


def check_events(events: pd.DataFrame, dividend_raw: pd.DataFrame) -> Check:
    c = Check("C7", "還原事件")
    if events.empty:
        c.worst("FAIL")
        c.summary = "沒有任何還原事件（除權息資料沒下載成功？）"
        return c
    by_source = events["source"].value_counts().to_dict()
    q = events["factor"].quantile([0.01, 0.5, 0.99]).round(4).to_dict()
    mismatch = 0
    checked = 0
    if dividend_raw is not None and not dividend_raw.empty and \
            {"before_price", "after_price", "stock_and_cache_dividend", "stock_or_cache_dividend"} <= set(dividend_raw.columns):
        cash = dividend_raw[dividend_raw["stock_or_cache_dividend"].astype(str).str.strip() == "息"]
        before = pd.to_numeric(cash["before_price"], errors="coerce")
        after = pd.to_numeric(cash["after_price"], errors="coerce")
        value = pd.to_numeric(cash["stock_and_cache_dividend"], errors="coerce")
        expected = before - value
        ok = before > 0
        diff = ((after - expected).abs() / before)[ok]
        checked = int(ok.sum())
        mismatch = int((diff > 0.005).sum())
    c.metrics = {"events": len(events), "by_source": by_source, "factor_quantiles": q,
                 "cash_dividend_checked": checked, "cash_dividend_mismatch": mismatch}
    if checked and mismatch / checked > 0.01:
        c.worst("WARN")
    c.summary = f"{len(events)} 個事件；純現金股利一致性檢查 {checked} 筆、不一致 {mismatch} 筆"
    return c


def check_finmind_adj(prices: pd.DataFrame, finmind_adj: pd.DataFrame) -> Check:
    c = Check("C8", "自算還原價 vs FinMind 還原價")
    if finmind_adj.empty or prices.empty:
        c.summary = "沒有下載 FinMind 還原價（extended 群組），略過"
        return c
    fa = finmind_adj[["stock_id", "date", "close"]].copy()
    fa["date"] = pd.to_datetime(fa["date"])
    fa["stock_id"] = fa["stock_id"].astype(str)
    fa = fa.sort_values(["stock_id", "date"])
    fa["ret_finmind"] = fa.groupby("stock_id")["close"].pct_change()
    m = prices[["stock_id", "date", "ret"]].merge(fa[["stock_id", "date", "ret_finmind"]],
                                                  on=["stock_id", "date"], how="inner").dropna()
    if m.empty:
        c.worst("WARN")
        c.summary = "兩份資料沒有重疊"
        return c
    diff = (m["ret"] - m["ret_finmind"]).abs()
    share = float((diff > 0.005).mean())
    c.metrics = {"compared_rows": len(m), "share_diff_gt_0.5pct": round(share, 5)}
    bad = m.assign(diff=diff).sort_values("diff", ascending=False).head(20)
    c.examples = [{"stock_id": r.stock_id, "date": str(pd.Timestamp(r.date).date()),
                   "ours": round(float(r.ret), 4), "finmind": round(float(r.ret_finmind), 4)}
                  for r in bad.itertuples(index=False)]
    if share > 0.01:
        c.worst("WARN")
    c.summary = f"比對 {len(m):,} 列，日報酬差異 > 0.5% 的占 {share:.3%}"
    return c


def check_revenue(revenue: pd.DataFrame, universe: pd.DataFrame) -> Check:
    c = Check("C9", "月營收")
    if revenue.empty:
        c.worst("FAIL")
        c.summary = "沒有月營收資料"
        return c
    rv = revenue.copy()
    rv["period"] = pd.to_datetime(rv["period"])
    dup = int(rv.duplicated(["stock_id", "period"]).sum())
    neg = int((pd.to_numeric(rv["revenue"], errors="coerce") < 0).sum())
    per_stock = rv.groupby("stock_id")["period"].agg(["min", "max", "count"])
    expected = ((per_stock["max"].dt.year - per_stock["min"].dt.year) * 12
                + (per_stock["max"].dt.month - per_stock["min"].dt.month) + 1)
    missing_months = int((expected - per_stock["count"]).clip(lower=0).sum())
    coverage = rv["stock_id"].nunique() / max(1, len(universe))
    c.metrics = {"rows": len(rv), "stocks": int(rv["stock_id"].nunique()), "coverage": round(coverage, 4),
                 "latest_period": str(rv["period"].max().date()), "duplicates": dup,
                 "negative": neg, "missing_months_inside_range": missing_months}
    if dup:
        c.worst("FAIL")
    if coverage < 0.9 or missing_months:
        c.worst("WARN")
    c.summary = f"{rv['stock_id'].nunique()} 檔（覆蓋 {coverage:.1%}）；最新 {c.metrics['latest_period'][:7]}；區間內缺 {missing_months} 個月"
    return c


def check_financials(fin: pd.DataFrame) -> Check:
    c = Check("C10", "綜合損益表")
    if fin.empty:
        c.worst("FAIL")
        c.summary = "沒有財報資料"
        return c
    pe = pd.to_datetime(fin["period_end"])
    not_qe = int((~(pe.dt.is_month_end & pe.dt.month.isin([3, 6, 9, 12]))).sum())
    types = fin["type"].value_counts()
    has_eps = "EPS" in set(fin["type"])
    c.metrics = {"rows": len(fin), "stocks": int(fin["stock_id"].nunique()),
                 "non_quarter_end_rows": not_qe, "has_EPS": has_eps,
                 "top_types": types.head(15).to_dict()}
    if not has_eps:
        c.worst("WARN")
    if not_qe:
        c.worst("WARN")
    c.summary = f"{fin['stock_id'].nunique()} 檔；非季底日期 {not_qe} 列；{'有' if has_eps else '缺'} EPS 欄位"
    return c


def check_chips(inst: pd.DataFrame, margin: pd.DataFrame, universe: pd.DataFrame) -> Check:
    c = Check("C11", "籌碼資料覆蓋")
    n = max(1, len(universe))
    inst_cov = inst["stock_id"].nunique() / n if not inst.empty else 0.0
    margin_cov = margin["stock_id"].nunique() / n if not margin.empty else 0.0
    c.metrics = {"institutional_coverage": round(inst_cov, 4), "margin_coverage": round(margin_cov, 4),
                 "institutional_first": str(pd.to_datetime(inst["date"]).min().date()) if not inst.empty else None}
    if inst_cov < 0.8 or margin_cov < 0.6:
        c.worst("WARN")
    c.summary = f"三大法人覆蓋 {inst_cov:.1%}、融資融券覆蓋 {margin_cov:.1%}（部分股票不能信用交易屬正常）"
    return c


def run_quality(cfg: Config) -> list[Check]:
    store = Store(cfg.raw_dir)
    manifest = Manifest(cfg.manifest_path)
    proc = cfg.processed_dir
    universe = _load(proc / "universe.parquet")
    prices = _load(proc / "prices.parquet")
    calendar = _load(proc / "calendar.parquet")
    events = _load(proc / "events.parquet")
    revenue = _load(proc / "revenue.parquet")
    fin = _load(proc / "financials.parquet")
    inst = _load(proc / "institutional.parquet")
    margin = _load(proc / "margin.parquet")
    info = store.read(get_spec("TaiwanStockInfo"), GLOBAL_KEY)
    delisting = store.read(get_spec("TaiwanStockDelisting"), GLOBAL_KEY)
    dividend_raw = store.read_all(get_spec("TaiwanStockDividendResult"))
    finmind_adj = store.read_all(get_spec("TaiwanStockPriceAdj"))
    try:
        checks = [
            check_downloads(manifest),
            check_universe(universe, info, delisting, cfg.start_date),
            check_price_integrity(prices),
            check_jumps(prices),
            check_calendar(prices, calendar),
            check_gaps(prices),
            check_events(events, dividend_raw),
            check_finmind_adj(prices, finmind_adj),
            check_revenue(revenue, universe),
            check_financials(fin),
            check_chips(inst, margin, universe),
        ]
    finally:
        manifest.close()
    return checks


def write_report(checks: list[Check], reports_dir: Path, generated_at: str | None = None) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = generated_at or pd.Timestamp.now(tz="Asia/Taipei").strftime("%Y-%m-%d %H:%M")
    n_fail = sum(c.status == "FAIL" for c in checks)
    n_warn = sum(c.status == "WARN" for c in checks)
    verdict = "未通過（有 FAIL）" if n_fail else ("有條件通過（請看 WARN）" if n_warn else "通過")
    lines = [
        "# 資料品質報告（Phase 1）",
        "",
        f"產生時間：{ts}（台北）　結論：**{verdict}**　FAIL {n_fail}／WARN {n_warn}／共 {len(checks)} 項",
        "",
        "| 編號 | 檢查 | 結果 | 摘要 |",
        "| --- | --- | --- | --- |",
    ]
    for c in checks:
        lines.append(f"| {c.id} | {c.title} | {c.status} | {c.summary} |")
    for c in checks:
        lines += ["", f"## {c.id} {c.title}：{c.status}", "", c.summary or ""]
        if c.metrics:
            lines += ["", "```json", json.dumps(c.metrics, ensure_ascii=False, indent=2, default=str), "```"]
        if c.examples:
            lines += ["", "範例（最多 20 筆）：", "", "```json",
                      json.dumps(c.examples, ensure_ascii=False, indent=2, default=str), "```"]
    md_path = reports_dir / "data_quality.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (reports_dir / "data_quality.json").write_text(
        json.dumps({"generated_at": ts, "verdict": verdict, "checks": [asdict(c) for c in checks]},
                   ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return md_path
