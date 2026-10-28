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


def _rec(t1, rows, k="tw"):
    return {"k": k, "t0": t1 - 0.5, "t1": t1, "b": 0, "r": rows}


D = 8 * 3600 + 59 * 60 + 30
FRESH = 8 * 3600 + 59 * 60


def test_latest_quotes_pick_newest_data_time_received_before_decide():
    recs = [_rec(D - 20, {"2330": {"t": "08:59:10", "pz": "2410"}, "t00": {"t": "07:50:00"}}),
            _rec(D - 10, {"2330": {"t": "08:58:11", "pz": "2380"}}),            # 比上一次還舊的回應：不用
            _rec(D - 5, {"2317": {"t": "08:59:20", "pz": "248"}}),
            _rec(D + 0.6, {"2330": {"t": "08:59:27", "pz": "2420"}}),           # 決定時間以後才收到：不用
            _rec(D - 3, {"2330": {"t": "08:59:10", "pz": "2415"}})]             # 資料時間一樣：取比較晚收到的
    q = G.latest_quotes(recs, D)
    assert set(q) == {"2330", "2317"}                                          # 指數那兩列不算
    assert q["2330"]["pz"] == "2415" and q["2330"]["_ts"] == 8 * 3600 + 59 * 60 + 10
    assert q["2317"]["pz"] == "248"


def test_est_realtime_formula_freshness_and_cover(lab):
    # 比重：2330 0.75、2317 0.25（前一天收盤 2400、240）
    recs = [_rec(D - 5, {"2330": {"t": "08:59:20", "pz": "2424.0000"}, "2317": {"t": "08:59:21", "pz": "247.2000"}})]
    r = G.est_realtime(recs, "2026-10-26", 46000.0, decide_s=D, fresh_s=FRESH, cover_min=0.8)
    want = 46000.0 * (0.75 * 2424 / 2400 + 0.25 * 247.2 / 240)
    assert r["est"] == pytest.approx(want) and r["cov"] == 1.0 and r["n"] == 2 and r["stale"] == 0
    # 2317 沒有試撮價（"-"）：只用 2330，除以用到的比重 → 只看 2330 的漲跌；比重 0.75 不到 0.8 → 不算
    recs2 = [_rec(D - 5, {"2330": {"t": "08:59:20", "pz": "2424"}, "2317": {"t": "08:59:21", "pz": "-"}})]
    r2 = G.est_realtime(recs2, "2026-10-26", 46000.0, decide_s=D, fresh_s=FRESH, cover_min=0.8)
    assert r2["est"] is None and r2["cov"] == 0.75 and r2["nopx"] == 1
    r3 = G.est_realtime(recs2, "2026-10-26", 46000.0, decide_s=D, fresh_s=FRESH, cover_min=0.7)
    assert r3["est"] == pytest.approx(46000.0 * 2424 / 2400)
    # 資料時間早於 08:59:00 的不用
    recs4 = [_rec(D - 5, {"2330": {"t": "08:58:59", "pz": "2424"}, "2317": {"t": "08:59:21", "pz": "247.2"}})]
    r4 = G.est_realtime(recs4, "2026-10-26", 46000.0, decide_s=D, fresh_s=FRESH, cover_min=0.2)
    assert r4["stale"] == 1 and r4["n"] == 1 and r4["est"] == pytest.approx(46000.0 * 247.2 / 240)


def test_est_realtime_ignores_mis_y_and_uses_official_close(lab):
    # 除權息那天 MIS 的 y 可能是參考價；估算只用前一天官方收盤（口徑和偷看版一樣，除權息點數由價差錨加回）
    recs = [_rec(D - 5, {"2330": {"t": "08:59:20", "pz": "2400", "y": "2394"}, "2317": {"t": "08:59:20", "pz": "240", "y": "1"}})]
    r = G.est_realtime(recs, "2026-10-26", 46000.0, decide_s=D, fresh_s=FRESH, cover_min=0.8)
    assert r["est"] == pytest.approx(46000.0)
