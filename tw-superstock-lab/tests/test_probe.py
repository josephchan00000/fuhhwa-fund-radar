from __future__ import annotations

from datetime import date

import pandas as pd

from conftest import FakeClient
from test_download import handlers
from superstock.config import FinMindConfig
from superstock.download import Downloader
from superstock.finmind_client import NO_TOKEN_LIMIT, FinMindClient
from superstock.probe import (dividend_semantics, financial_semantics, revenue_semantics, run_probe,
                              summarize, write_probe_report)
from superstock.storage import Manifest, Store


def test_no_token_uses_300_per_hour():
    assert FinMindClient("", FinMindConfig()).limiter.per_hour == int(NO_TOKEN_LIMIT * 0.92)
    assert FinMindClient("tok", FinMindConfig()).limiter.per_hour == int(600 * 0.92)


def test_revenue_date_meaning():
    df = pd.DataFrame({"date": ["2024-02-01", "2024-03-01"], "revenue_year": [2024, 2024],
                       "revenue_month": [1, 2], "revenue": [1, 2]})
    sem = revenue_semantics(df)
    assert sem["checked"] == 2 and sem["date_is_first_of_next_month"] == 1.0
    assert sem["date_is_first_of_same_month"] == 0.0


def test_financial_quarter_end_and_types():
    df = pd.DataFrame({"date": ["2024-03-31", "2024-06-30", "2024-05-15"], "type": ["EPS", "Revenue", "EPS"]})
    sem = financial_semantics(df)
    assert sem["quarter_end_share"] == round(2 / 3, 4) and sem["types"] == ["EPS", "Revenue"]


def test_dividend_cash_consistency():
    df = pd.DataFrame({"before_price": [100.0, 50.0, 80.0], "after_price": [97.0, 45.0, 70.0],
                       "stock_and_cache_dividend": [3.0, 1.0, 1.0],
                       "stock_or_cache_dividend": ["息", "息", "權"]})
    sem = dividend_semantics(df)
    assert sem["checked"] == 2 and sem["after_eq_before_minus_cash_share"] == 0.5


def test_summarize_has_no_rows_only_shape():
    df = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "stock_id": ["2330", "2330"],
                       "close": [593.0, 590.0], "type": ["twse", "twse"]})
    s = summarize(df)
    assert s["rows"] == 2 and s["first_date"] == "2024-01-02" and s["values"]["type"] == {"twse": 2}
    assert "593" not in str(s)  # 價格不進報告


def test_probe_report_from_store_and_extra_calls(cfg):
    h = handlers()
    client = FakeClient(h)
    Downloader(cfg, client, Store(cfg.raw_dir), Manifest(cfg.manifest_path),
               today=date(2016, 1, 1)).run(["meta", "core", "events"])
    before = client.calls
    h["TaiwanStockPriceAdj"] = lambda sid, s, e: pd.DataFrame({"date": ["2015-12-30"], "stock_id": [sid],
                                                               "close": [1.0]})
    result = run_probe(cfg, client, "2016-01-01")
    ds = result["datasets"]
    assert ds["TaiwanStockPrice"]["rows"] > 400 and ds["TaiwanStockPrice"]["source"].startswith("本機")
    assert ds["TaiwanStockPriceAdj"]["ok"] is True and ds["TaiwanStockPriceAdj"]["rows"] == 1
    assert ds["TaiwanStockMarginPurchaseShortSale"]["disabled"]  # 下載時連 3 檔失敗被停用
    assert result["semantics"]["revenue"]["date_is_first_of_next_month"] == 1.0
    # 只對本機沒有資料的逐檔資料集各送一次（extended 群組 5 個）
    assert client.calls - before == 5
    path = write_probe_report(result, cfg.reports_dir, generated_at="2026-10-15 20:00")
    text = path.read_text(encoding="utf-8")
    assert "TaiwanStockPriceAdj" in text and (cfg.reports_dir / "live_probe.json").exists()


def test_probe_offline_sends_nothing(cfg):
    client = FakeClient(handlers())
    result = run_probe(cfg, client, "2016-01-01", extra_calls=False)
    assert client.calls == 0 and result["datasets"]["TaiwanStockPrice"]["source"] == "本機沒有資料"
