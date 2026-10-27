"""台指期早盤策略的訊號（arm/lab/futsig.py）：結算日換月、加權指數比重、除權息點數、落差 E。"""
from __future__ import annotations

from datetime import date

import pytest

from arm.lab import futsig as G
from arm.lab import store


def test_settle_day_is_third_wednesday():
    assert G.settle_day(2026, 10) == date(2026, 10, 21)
    assert G.settle_day(2026, 9) == date(2026, 9, 16)


def test_contract_switches_to_next_month_on_settlement_day():
    cs = {"202610": [], "202611": [], "202612": []}
    assert G.contract_for("2026-10-20", cs) == "202610"
    assert G.contract_for("2026-10-21", cs) == "202611"      # 10 月契約今天結算
    assert G.contract_for("2026-10-22", {"202611": [], "202612": []}) == "202611"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write("v3me_tw", "2026-09", {"d": "2026-09-30", "s": {"2330": [2000, 30], "2317": [200, 100], "0050": [50, 999]}})
    store.write("mkt", "2026-10-26", {"q_tw": {"2330": [0, 0, 0, 2400, 0, 0], "2317": [0, 0, 0, 240, 0, 0]}})
    store.write("divtw", "2026", {"rows": [["2026-10-27", "2330", 6.0, "息", 2400.0, 2394.0],
                                           ["2026-10-27", "9999", 1.0, "息", 10.0, 9.0]]})
    return tmp_path


def test_weights_use_month_end_shares_and_previous_close(lab):
    w = G.weights("2026-10-26")
    assert set(w) == {"2330", "2317"}                         # ETF（0 開頭）不算
    assert w["2330"] == pytest.approx(72000 / (72000 + 24000))


def test_div_points(lab):
    pts, top = G.div_points("2026-10-27", "2026-10-26", 46000.0)
    assert pts == pytest.approx(0.75 * 6 / 2400 * 46000)       # 不在比重表裡的 9999 不算
    assert top == [(round(pts, 2), "2330")]
    assert G.div_points("2026-10-28", "2026-10-27", 46000.0) == (0.0, [])


def test_edge_formula():
    inp = {"basis": 150.0, "div": 30.0}
    assert G.edge(inp, f_now=46500, i_est=46400) == pytest.approx(80.0)   # 46400＋150＋30−46500
