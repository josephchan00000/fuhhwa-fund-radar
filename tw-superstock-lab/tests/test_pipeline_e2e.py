"""端到端：假資料下載 → build → quality → reconcile（不連網）。"""

from __future__ import annotations

from datetime import date

import pandas as pd

from conftest import FakeClient
from test_download import handlers
from superstock.build import build_all
from superstock.download import Downloader
from superstock.quality import run_quality, write_report
from superstock.reconcile import reconcile
from superstock.storage import Manifest, Store


def test_full_pipeline_runs(cfg):
    h = handlers()
    h["TaiwanStockMarginPurchaseShortSale"] = lambda sid, s, e: pd.DataFrame(
        {"date": ["2015-03-02"], "stock_id": [sid], "MarginPurchaseTodayBalance": [100],
         "ShortSaleTodayBalance": [5]})
    h["TaiwanStockInstitutionalInvestorsBuySell"] = lambda sid, s, e: pd.DataFrame(
        {"date": ["2015-03-02"] * 2, "stock_id": [sid] * 2, "name": ["Investment_Trust", "Foreign_Investor"],
         "buy": [1000, 500], "sell": [0, 800]})
    h["TaiwanStockFinancialStatements"] = lambda sid, s, e: pd.DataFrame(
        {"date": ["2015-03-31"], "stock_id": [sid], "type": ["EPS"], "value": [1.2], "origin_name": ["EPS"]})
    client = FakeClient(h)
    Downloader(cfg, client, Store(cfg.raw_dir), Manifest(cfg.manifest_path),
               today=date(2016, 1, 1)).run(["meta", "core", "events"])

    counts = build_all(cfg)
    assert counts["prices"] > 1000 and counts["universe"] == 3
    prices = pd.read_parquet(cfg.processed_dir / "prices.parquet")
    p2330 = prices[prices.stock_id == "2330"].set_index("date")
    # 2015-07-01 除息 100→97：之前的還原因子 = 0.97（該股之後沒有其他事件）
    assert abs(p2330.loc[pd.Timestamp("2015-06-30"), "adj_factor"] - 0.97) < 1e-9
    inst = pd.read_parquet(cfg.processed_dir / "institutional.parquet")
    assert {"net_trust", "net_foreign"} <= set(inst.columns)
    fin = pd.read_parquet(cfg.processed_dir / "financials.parquet")
    assert fin["available_date"].iloc[0] == pd.Timestamp("2015-05-15")

    checks = run_quality(cfg)
    path = write_report(checks, cfg.reports_dir)
    assert path.exists() and len(checks) == 11
    rpath = reconcile(cfg, n=3, fetch=False)
    assert "人工核對清單" in rpath.read_text(encoding="utf-8")
