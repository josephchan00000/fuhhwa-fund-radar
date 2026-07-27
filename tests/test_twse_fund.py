"""TWSE 基金基本資料彙總表連接器（ETF 規模第二來源交叉驗證）測試——離線、mock get_json。"""
from unittest.mock import patch

from arm.connectors import twse_fund


def test_fetch_units_parses_by_keyword_not_exact_key():
    """表頭常見括號/直線混排寫法——關鍵字比對而非精確鍵值。"""
    rows = [
        {"基金代號": "0056", "基金名稱": "元大台灣高股息基金", "發行單位數|轉換數": "3,510,000,000"},
        {"基金代號": "00929", "基金名稱": "復華台灣科技優息基金", "發行單位數（轉換數）": "4,790,000,000"},
    ]
    with patch.object(twse_fund, "get_json", return_value=rows):
        out = twse_fund.fetch_units()
    assert out == {"0056": 3_510_000_000.0, "00929": 4_790_000_000.0}


def test_fetch_units_skips_rows_without_code_or_units():
    rows = [
        {"基金名稱": "缺代號"},                              # 無代號欄
        {"基金代號": "00919", "備註": "無單位數欄"},           # 有代號無單位數
        {"基金代號": "00878", "發行單位數": "0"},              # 單位數為 0（不合理值）
        {"基金代號": "0050", "發行單位數": "2,240,000,000"},
    ]
    with patch.object(twse_fund, "get_json", return_value=rows):
        out = twse_fund.fetch_units()
    assert out == {"0050": 2_240_000_000.0}


def test_fetch_units_returns_empty_on_exception_or_bad_shape():
    with patch.object(twse_fund, "get_json", side_effect=RuntimeError("blocked")):
        assert twse_fund.fetch_units() == {}
    with patch.object(twse_fund, "get_json", return_value={"not": "a list"}):
        assert twse_fund.fetch_units() == {}
    with patch.object(twse_fund, "get_json", return_value=None):
        assert twse_fund.fetch_units() == {}
