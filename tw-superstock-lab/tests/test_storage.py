from __future__ import annotations

import pandas as pd

from superstock.datasets import get_spec
from superstock.storage import Manifest, Store


def test_merge_write_dedupes_and_keeps_latest(tmp_path):
    store = Store(tmp_path)
    spec = get_spec("TaiwanStockPrice")
    a = pd.DataFrame({"date": ["2024-01-02", "2024-01-03"], "stock_id": "2330", "close": [100.0, 101.0]})
    b = pd.DataFrame({"date": ["2024-01-03", "2024-01-04"], "stock_id": "2330", "close": [101.5, 102.0]})
    assert store.merge_write(spec, "2330", a) == 2
    assert store.merge_write(spec, "2330", b) == 3
    df = store.read(spec, "2330")
    assert list(df["close"]) == [100.0, 101.5, 102.0]  # 重疊日以新資料為準
    assert not list(tmp_path.rglob("*.tmp"))


def test_revenue_dedupe_key(tmp_path):
    store = Store(tmp_path)
    spec = get_spec("TaiwanStockMonthRevenue")
    a = pd.DataFrame({"date": ["2024-02-01"], "stock_id": "2330", "revenue_year": [2024],
                      "revenue_month": [1], "revenue": [100]})
    b = a.assign(revenue=[110])
    store.merge_write(spec, "2330", a)
    store.merge_write(spec, "2330", b)
    assert list(store.read(spec, "2330")["revenue"]) == [110]


def test_manifest_failure_keeps_last_success_range(tmp_path):
    m = Manifest(tmp_path / "m.sqlite")
    m.mark_done("TaiwanStockPrice", "2330", 10, "2014-01-01", "2024-05-01")
    m.mark_failed("TaiwanStockPrice", "2330", "boom")
    m.mark_failed("TaiwanStockPrice", "2330", "boom again")
    row = m.get("TaiwanStockPrice", "2330")
    assert row["status"] == "failed"
    assert row["last_end"] == "2024-05-01" and row["last_start"] == "2014-01-01"
    assert row["attempts"] == 3
    m.disable("TaiwanStockPriceAdj", "需付費")
    assert m.disabled_reason("TaiwanStockPriceAdj") == "需付費"
    m.enable("TaiwanStockPriceAdj")
    assert not m.disabled_reason("TaiwanStockPriceAdj")
    m.close()
