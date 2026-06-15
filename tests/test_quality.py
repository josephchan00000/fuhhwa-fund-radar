"""品質閘門單元測試（M1-8）：股票 / 債券分流 + fail-loud。"""
from arm import quality


def _equity_snap(weights_ok=True, shares_ok=True):
    w = 98.0 if weights_ok else 50.0
    sh = 1000 if shares_ok else 0
    return {"nav": 19.0, "aum": 19.0 * 1000, "units": 1000,
            "holdings": [{"kind": "equity", "stock_id": "2330", "stock_name": "台積電",
                          "shares": sh, "market_value": 19000, "weight": w}]}


def _bond_snap():
    return {"nav": 14.88, "aum": 14.88 * 1000, "units": 1000,
            "holdings": [
                {"kind": "future", "stock_id": "XT", "stock_name": "避險", "shares": -10,
                 "market_value": -100, "weight": 0.0},
                {"kind": "bond", "stock_id": "US1", "stock_name": "JPM", "shares": 4900000,
                 "market_value": 177835783, "weight": 99.0},
            ]}


def test_gate_performance_pass_and_fail():
    good = [(f"2026-06-{d:02d}", 10.0 + d, 0) for d in (10, 11, 12)]
    r = quality.gate_performance(good, "2026-06-12", "X")
    assert r.passed
    # 最新日不吻合 → CRITICAL 失敗
    r2 = quality.gate_performance(good, "2026-06-13", "X")
    assert not r2.passed


def test_gate_holdings_equity_pass():
    assert quality.gate_holdings(_equity_snap(), "00991A", "tw_equity").passed


def test_gate_holdings_equity_fail_weight_and_shares():
    assert not quality.gate_holdings(_equity_snap(weights_ok=False), "X", "tw_equity").passed
    assert not quality.gate_holdings(_equity_snap(shares_ok=False), "X", "tw_equity").passed


def test_gate_holdings_bond_uses_bond_section_only():
    """債券基金：以債券區段算權重/正性；期貨避險（負值）不該讓閘門誤判失敗。"""
    r = quality.gate_holdings(_bond_snap(), "00986D", "global_bond")
    assert r.passed
    names = [c.name for c in r.checks]
    assert any("債券權重合計" in n for n in names)
    assert any("債券市值皆為正" in n for n in names)


def test_gate_holdings_navxunits_mismatch_fails():
    snap = _equity_snap()
    snap["aum"] = snap["aum"] * 1.2          # 蓄意對不上
    assert not quality.gate_holdings(snap, "X", "tw_equity").passed
