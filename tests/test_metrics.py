"""指標引擎單元測試（M1-8）。"""
from arm import metrics


def _series(pairs):
    return [(d, c, 0) for d, c in pairs]


def test_period_return():
    s = _series([("2026-06-01", 10.0), ("2026-06-02", 11.0), ("2026-06-03", 12.0)])
    assert metrics.period_return(s, 1) == 12.0 / 11.0 - 1
    assert metrics.period_return(s, 2) == 12.0 / 10.0 - 1
    assert metrics.period_return(s, 5) is None        # 不足 n+1 筆 → None


def test_si_return():
    s = _series([("2025-12-18", 10.0), ("2026-06-12", 19.7)])
    assert round(metrics.si_return(s), 4) == round(19.7 / 10.0 - 1, 4)


def test_ytd_fairness_year_mid_listing_excluded():
    """年中才掛牌者沒有可比 YTD → 回 None（不拿掛牌日當年初虛報）。"""
    mid = _series([("2026-03-31", 15.0), ("2026-06-12", 16.85)])
    assert metrics.ytd_return(mid, 2026) is None
    early = _series([("2026-01-02", 10.0), ("2026-06-12", 18.0)])
    assert round(metrics.ytd_return(early, 2026), 4) == round(18.0 / 10.0 - 1, 4)


def test_alpha_vs_handles_none():
    etf = {"1m": 0.10, "ytd": None, "si": 0.5}
    bench = {"1m": 0.06, "ytd": 0.2, "si": None}
    a = metrics.alpha_vs(etf, bench)
    assert round(a["1m"], 4) == 0.04
    assert a["ytd"] is None and a["si"] is None


def test_holdings_diff_classifies():
    prev = [{"stock_id": "A", "stock_name": "A", "shares": 1000, "weight": 5},
            {"stock_id": "B", "stock_name": "B", "shares": 2000, "weight": 5}]
    curr = [{"stock_id": "A", "stock_name": "A", "shares": 1500, "weight": 6},   # 加碼
            {"stock_id": "C", "stock_name": "C", "shares": 800, "weight": 3}]     # 新建倉；B 出清
    d = metrics.holdings_diff(prev, curr)
    assert [x["stock_id"] for x in d["new"]] == ["C"]
    assert [x["stock_id"] for x in d["add"]] == ["A"] and d["add"][0]["delta_shares"] == 500
    assert [x["stock_id"] for x in d["exit"]] == ["B"]
    assert d["cut"] == []


def test_premium_discount():
    assert round(metrics.premium_discount(19.05, 19.01), 5) == round((19.05 - 19.01) / 19.01, 5)
