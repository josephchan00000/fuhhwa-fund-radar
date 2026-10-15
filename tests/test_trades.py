"""逐筆交易（arm/lab/trades.py；docs/lab_trades_plan.md）：帳戶紀錄不改數字、買賣配對、核對規則、當時價格還原、頁面格式。"""
import pytest

from arm.lab import bt3, bt3d, trades


class _P:
    """最小的 Px 介面（同 tests/test_bt3.py）。"""

    def __init__(self, ser: dict, T: int):
        self.T, self.cal = T, [f"2026-01-{i + 1:02d}" for i in range(T)]
        self.s = {c: {"o": [float(x) for x in o], "c": [float(x) for x in cl], "h": [x * 1.01 for x in cl],
                      "l": [x * 0.99 for x in cl], "v": [1.0] * T} for c, (o, cl) in ser.items()}


def _panel():
    T = 9
    return _P({"A": ([100, 100, 101, 102, 103, 104, 105, 106, 107], [100, 101, 102, 103, 104, 105, 106, 107, 108]),
               "B": ([50, 50, 50, 51, 52, 52, 52, 53, 53], [50, 50, 51, 52, 52, 52, 53, 53, 54]),
               "C": ([20, 20, 20, 20, 23, 21, 21, 21, 21], [20, 20, 20, 21, 21, 21, 21, 21, 21])}, T)


PERIODS = [(0, 2, ["A", "B"]), (2, 4, ["A", "C"]), (4, 6, ["C"]), (7, 8, ["B"])]   # 前三期相連、第四期隔開


def test_log_does_not_change_numbers():
    P = _panel()
    for mult in (0, 1, 2):
        log = []
        a, b = bt3.account(P, PERIODS, "L", mult=mult), bt3.account(P, PERIODS, "L", mult=mult, log=log)
        assert a == b and log


def test_trips_pair_buys_and_sells_and_reasons():
    P = _panel()
    log = []
    bt3.account(P, PERIODS, "L", log=log)
    tp, skip = trades.trips(log)
    got = {(t["c"], t["j"], t["i"], t["op"], t["how"]) for t in tp}
    assert ("B", 1, 3, True, "drop") in got                 # 第二期不在名單 → 第二期開盤賣
    assert ("A", 1, 5, True, "drop") in got                 # 續抱一期、第三期開盤賣
    assert ("C", 3, 6, False, "end") in got                 # 第三期後不相連 → 期末收盤賣
    assert ("B", 8, 8, False, "end") in got
    assert not skip
    # 單筆報酬＝同帳戶的成本算法
    t = next(t for t in tp if t["c"] == "B" and t["j"] == 1)
    assert trades.trip_ret(t["o"], t["p"], "L") == pytest.approx(((51 / 50) * (1 - bt3.side_cost("L", True))
                                                                   / (1 + bt3.side_cost("L", False)) - 1) * 100)


def test_limit_up_skip_is_logged():
    P = _P({"A": ([100, 100, 100, 100], [100, 100, 100, 100]), "B": ([50, 55, 55, 55], [50, 55, 55, 55])}, 4)
    log = []
    bt3.account(P, [(0, 2, ["A", "B"])], "L", log=log)
    _, skip = trades.trips(log)
    assert [(s["c"], s["why"]) for s in skip] == [("B", "lim")]


def test_build_periods_match_account_and_non_rolling_period_equals_trade_mean():
    P = _panel()
    tr = [100.0 + i for i in range(P.T)]
    log = []
    acc = bt3.account(P, PERIODS, "L", log=log)
    doc = trades.build(P.cal, PERIODS, acc["units"], log, "L", tr)
    assert [p["r"] for p in doc["per"]] == pytest.approx([u["r"] for u in acc["units"]], abs=1e-3)
    assert doc["chk"]["np"] == len(acc["units"])
    # 第四期前後都不相連（現金進、現金出）→ 這一期報酬＝這期唯一一筆
    last = doc["per"][-1]
    t = next(r for r in doc["tr"] if r["c"] == "B" and r["bd"] == P.cal[8])
    assert last["r"] == pytest.approx(t["r"], abs=0.006) and last["end"] is True     # 逐筆報酬存到兩位小數
    a = next(r for r in doc["tr"] if r["c"] == "A")
    assert a["np"] == 2 and a["so"] is True and a["how"] == "drop"   # 連續兩期入選、一筆交易


def test_rolling_last_period_is_marked_as_backtest_settlement():
    P = _panel()
    pk = [(0, 2, ["A"]), (2, 4, ["A", "B"])]
    log = []
    acc = bt3.account(P, pk, "L", log=log)
    doc = trades.build(P.cal, pk, acc["units"], log, "L", [1.0] * P.T, roll=True)
    assert doc["per"][-1]["end"] == 2
    assert {r["how"] for r in doc["tr"]} == {"bt"}
    doc2 = trades.build(P.cal, pk, acc["units"], log, "L", [1.0] * P.T)
    assert doc2["per"][-1]["end"] is True and {r["how"] for r in doc2["tr"]} == {"end"}


def test_market_return_uses_close_before_buy():
    tr = [100, 100, 110, 121, 133.1]
    assert trades.mk_ret(tr, 1, 3, False) == pytest.approx(21.0)       # 買進前一天收盤（100）→ 賣出日收盤（121）
    assert trades.mk_ret(tr, 1, 3, True) == pytest.approx(10.0)        # 開盤賣：只到前一天收盤
    assert trades.mk_ret([None, None, None], 1, 2, False) is None


def test_tick_grid_and_snap():
    assert trades.tick(9.99) == 0.01 and trades.tick(49.95) == 0.05 and trades.tick(99.9) == 0.1
    assert trades.tick(499.5) == 0.5 and trades.tick(999) == 1 and trades.tick(1005) == 5
    assert trades.on_tick(245.5) and not trades.on_tick(245.3) and trades.on_tick(36.65) and not trades.on_tick(36.68)
    assert trades.snap(117.46) == 117.5 and trades.snap(1054.99) == 1055


class _Raw(trades.Raw):
    """不讀檔：直接塞月底官方收盤、除權息、Yahoo 日線。"""

    def __init__(self, doc, me, ev):
        self.me, self.ev = {"X": me}, {"X": ev}
        self._doc, self._k, self._sw = {"X": {**doc, "_ix": {d: i for i, d in enumerate(doc["t"])}}}, {}, {}


def test_raw_price_factor_switches_at_capital_reduction():
    # 減資（例 3105 2016）：Yahoo 把減資前的價格除以 0.7（＝實際價 ÷ 0.7），3/16 恢復交易後才是實際價。
    # 月底官方收盤：2 月 70.0、3 月 102.0。實際價在升降單位上（50～100 元＝0.1），乘錯 K 會有零頭 → 找得到切換日。
    t = ["2026-02-27", "2026-03-02", "2026-03-03", "2026-03-04", "2026-03-16", "2026-03-17", "2026-03-31"]
    c = [100.0, 70.1 / 0.7, 70.2 / 0.7, 70.3 / 0.7, 101.0, 101.5, 102.0]
    raw = _Raw({"src": "yahoo", "t": t, "o": c, "c": c}, [("2026-02-27", 70.0), ("2026-03-31", 102.0)], [])
    assert raw.px("X", "2026-03-03", False) == (70.2, False)           # 減資前：K 0.7
    assert raw.px("X", "2026-03-16", False) == (101.0, False)          # 減資後：K 1
    assert raw.px("X", "2026-02-27", True) == (70.0, False)            # 量測當天


def test_raw_price_uses_single_dividend_date_when_tick_grid_cannot_tell():
    # 10 元以下升降單位 0.01：K 1.1 與 1 都對得上 → 中間只有一個除權息日就從那天切開（配股一成）
    t = ["2026-05-29", "2026-06-01", "2026-06-15", "2026-06-16", "2026-06-30"]
    c = [8.0, 8.1, 8.2, 8.3, 8.4]
    raw = _Raw({"src": "yahoo", "t": t, "o": c, "c": c}, [("2026-05-29", 8.8), ("2026-06-30", 8.4)],
               [("2026-06-16", 9.02, 8.2, "權", 0.82, None, None)])
    assert raw.px("X", "2026-06-01", False)[0] == pytest.approx(8.91)
    assert raw.px("X", "2026-06-16", False)[0] == pytest.approx(8.3)
    assert raw.divs("X", "2026-06-01", "2026-06-16") == [["2026-06-16", "權", 0.82, 9.02, 8.2]]
    assert raw.divs("X", "2026-06-16", "2026-06-30") == []             # 除權息日開盤才買＝沒領


def test_pack_trims_and_columns():
    doc = {"per": [{"d": "2026-01-05", "bd": "2026-01-06", "ed": "2026-02-10", "r": 1.234, "mk": 0.5, "pk": ["A"], "new": ["A"],
                    "drop": [], "skip": [], "sc": [3.2], "end": 2, "nu": 200, "fw": False}],
           "tr": [{"c": "A", "d": "2026-01-05", "bd": "2026-01-06", "bp": 10.0, "sd": "2026-02-10", "sp": 11.0, "r": 9.5, "mk": 0.5,
                   "st": "closed", "hd": 25, "how": "drop", "so": True, "np": 1, "dv": [], "mul": 1.0002, "kc": 0}]}
    pk = trades.pack(doc)
    assert pk["per"][0][0] == trades.dnum("2026-01-05") and pk["per"][0][10] == 2 and len(pk["per"][0]) == len(trades.PER_COLS)
    row = pk["tr"][0]
    assert row[:11] == ["A", trades.dnum("2026-01-05"), trades.dnum("2026-01-06"), 10.0, trades.dnum("2026-02-10"), 11.0, 9.5, 0.5,
                        "c", 25, "d"]
    assert len(row) == 13                                              # 尾端空值省略；還原倍數 ≈1 不存
    assert trades.dnum("2013-01-01") == 0


def test_pack_simple_market_and_skip():
    out = trades.pack_simple([
        {"c": "A", "d": "2026-08-01", "bd": "2026-08-04", "sd": "2026-08-06", "entry": 100, "exit": 103, "held": 3, "r": 2.4, "x": 1.0,
         "why": "到期", "st": "closed", "review": "2026-06"},
        {"c": "B", "d": "2026-08-01", "st": "skip", "why": "開高 +3.2%"},
        {"c": "C", "d": "2026-08-01", "st": "cand"}], "2026-09-01", grp="review")
    rows = {r[0]: r for r in out["tr"]}
    assert set(rows) == {"A", "B"}                                     # 待進場不列
    i = {c: k for k, c in enumerate(trades.TR_COLS)}
    assert rows["A"][i["mk"]] == pytest.approx(1.4) and rows["A"][i["st"]] == "c" and rows["A"][i["g"]] == "2026-06"
    assert rows["B"][i["st"]] == "s" and rows["B"][i["why"]] == "開高 +3.2%"


def test_panel_dividends_holiday_and_missing_cash(monkeypatch):
    # 除權息日休市（颱風假）→ 算在下一個交易日；上櫃現金與配股欄都空白 → 現金部分不知道（None，用 Yahoo 隱含倍數）
    cal = ["2024-07-22", "2024-07-23", "2024-07-26", "2024-07-29"]
    F = bt3d.factor_yahoo(cal, [10.0, 10.0, 9.8, 9.8], [9.7, 9.7, 9.8, 9.8], [("2024-07-24", 0.98, 0.98)])
    assert F[:2] == pytest.approx([0.98, 0.98]) and F[2:] == pytest.approx([1.0, 1.0])
    monkeypatch.setattr(bt3d.store, "load", lambda kind: [] if kind == "divtw" else
                        [("2026", {"rows": [["2026-06-01", "3709", 88.8, 86.35, 0.0, 0.0], ["2026-07-01", "1111", 50.0, 45.0, 0.0, 100.0],
                                            ["2026-08-10", "3709", 79.4, 77.24, 2.15652134, 0.0]]})])
    ev = bt3d.events()
    assert ev["3709"][0][2] is None and ev["1111"][0][2] == 1.0
    assert ev["3709"][1][2] == pytest.approx(1 - 2.15652134 / 79.4)


def test_reprice_existing_strategy_keeps_returns_verifiable():
    # 京元電子型：買進日官方分片缺價格、回測用了 Yahoo 換算過的 301.9048（實際 317）；賣出日是官方實際價 301
    t = ["2026-02-24", "2026-03-19", "2026-03-31"]
    raw = _Raw({"src": "yahoo", "t": t, "o": [301.9048, 300.0, 301.0], "c": [310.4762, 300.9524, 301.0]},
               [("2026-03-31", 316.05)], [])
    r_old = (301.0 / 301.9048 - 1 - 0.00585) * 100
    row = ["X", trades.dnum("2026-02-23"), trades.dnum("2026-02-24"), 301.9048, trades.dnum("2026-03-19"), 301.0,
           round(r_old, 2), 1.0, "c", 18, "生效前一天出"]
    pk = {"tr": [row]}
    st = trades.reprice(pk, raw)
    i = {c: k for k, c in enumerate(trades.TR_COLS)}
    out = pk["tr"][0]
    assert st == {"fixed": 1, "approx": 0} and out[i["bp"]] == 317.0 and out[i["sp"]] == 301.0
    assert out[i["kc"]] == 2 and out[i["mul"]] == pytest.approx(1.05, abs=1e-4)
    assert (out[i["sp"]] / out[i["bp"]] * out[i["mul"]] - 1 - 0.00585) * 100 == pytest.approx(r_old, abs=0.01)
    assert trades.exact_tick(301.0) and not trades.exact_tick(300.9524) and not trades.exact_tick(46.29)
