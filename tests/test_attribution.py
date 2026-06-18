"""績效歸因單元測試：貢獻度＝權重×漲跌、佔當日漲幅、持股權重差（含截圖實例對位）。"""
from arm import attribution as at


def _q(code, pct, date="2026-06-16"):
    return {code: {"change_pct": pct, "close": None, "date": date}}


# 截圖實例（2026-06-16 00991A）：南亞科 5.68%×+7.46%、台積 14.11%×+1.05%、川湖 2.79%×-4.45%
HOLD = [
    {"stock_id": "2408", "stock_name": "南亞科技", "weight": 5.68},
    {"stock_id": "2330", "stock_name": "台灣積體", "weight": 14.11},
    {"stock_id": "2059", "stock_name": "川湖科技", "weight": 2.79},
]
QUOTES = {
    "2408": {"change_pct": 7.46, "date": "2026-06-16"},
    "2330": {"change_pct": 1.05, "date": "2026-06-16"},
    "2059": {"change_pct": -4.45, "date": "2026-06-16"},
}


def test_contribution_matches_screenshot():
    a = at.compute(HOLD, QUOTES, etf_ret=0.76)
    by = {r["code"]: r for r in a["rows"]}
    # 貢獻度＝權重% × 漲跌% ÷ 100
    assert round(by["2408"]["contrib"], 2) == 0.42      # 截圖 +0.40~0.42
    assert round(by["2330"]["contrib"], 2) == 0.15      # 截圖 +0.15
    assert round(by["2059"]["contrib"], 2) == -0.12     # 截圖 -0.13
    # 佔當日漲幅＝貢獻 / ETF 實際當日報酬（截圖口徑，以未取整貢獻計）
    assert by["2408"]["share"] == round(5.68 * 7.46 / 100 / 0.76 * 100)   # ≈56（截圖約 52~56）


def test_up_down_split_and_est_ret():
    a = at.compute(HOLD, QUOTES, etf_ret=0.76)
    assert [r["code"] for r in a["up_top"]] == ["2408", "2330"]   # 依貢獻度
    assert [r["code"] for r in a["down_top"]] == ["2059"]
    assert a["est_ret"] == round(0.42 + 0.15 - 0.12, 2)           # 成分貢獻合計
    assert a["etf_ret"] == 0.76
    assert a["n_priced"] == 3 and a["n_total"] == 3


def test_missing_quote_is_skipped_not_crash():
    a = at.compute(HOLD, _q("2408", 7.46), etf_ret=None)          # 只有一檔有報價
    assert a["n_priced"] == 1 and a["n_total"] == 3
    # 無 etf_ret → 佔比退回以成分貢獻合計為分母
    assert a["rows"][0]["share"] == 100


def test_holdings_diff_weight_delta():
    prev = [{"stock_id": "2408", "stock_name": "南亞科技", "weight": 5.36},
            {"stock_id": "3017", "stock_name": "奇鋐科技", "weight": 1.50},
            {"stock_id": "6669", "stock_name": "緯穎科技", "weight": 2.40}]
    cur = [{"stock_id": "2408", "stock_name": "南亞科技", "weight": 5.68},   # +0.32 加碼
           {"stock_id": "3017", "stock_name": "奇鋐科技", "weight": 0.82},   # -0.68 減碼（截圖）
           {"stock_id": "6669", "stock_name": "緯穎科技", "weight": 1.56},   # -0.84 減碼（截圖）
           {"stock_id": "9999", "stock_name": "新進股", "weight": 0.5}]      # 新進
    d = at.holdings_diff(prev, cur)
    assert d["adds"][0]["code"] == "2408" and d["adds"][0]["delta"] == 0.32
    cuts = {x["code"]: x["delta"] for x in d["cuts"]}
    assert cuts["6669"] == -0.84 and cuts["3017"] == -0.68         # 減碼最大者在前
    assert d["cuts"][0]["code"] == "6669"
    assert [x["code"] for x in d["new"]] == ["9999"]
