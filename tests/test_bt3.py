"""回測方法 v3（arm/lab/bt3.py）：成本、資金帳戶、因子檢定、統計、報酬型態、評級。"""
import math

import pytest

from arm.lab import bt3


class _P:
    """最小的 Px 介面：cal、T、s、cap、liq、codes、close_on_or_before。"""

    def __init__(self, ser: dict, T: int, cap: float = 400e8, liq: float = 5e8):
        self.T, self.cal = T, [f"2026-01-{i + 1:02d}" for i in range(T)]
        self.s = {c: {"o": [float(x) for x in o], "c": [float(x) for x in cl], "h": [x * 1.01 for x in cl],
                      "l": [x * 0.99 for x in cl], "v": [1.0] * T} for c, (o, cl) in ser.items()}
        self.cap = {c: [cap] * T for c in ser}
        self.liq = {c: [liq] * T for c in ser}
        self.codes = sorted(ser)

    def close_on_or_before(self, c, x, lo):
        for i in range(x, lo - 1, -1):
            if self.s[c]["c"][i]:
                return self.s[c]["c"][i]
        return None


def test_costs_match_plan():
    assert abs(bt3.rt_cost("L") - 0.004798) < 1e-9                         # 0.04%×2＋稅 0.3%＋滑價 0.05%×2
    assert abs(bt3.rt_cost("M") - 0.006798) < 1e-9
    assert abs(bt3.rt_cost("L", 2) - 2 * bt3.rt_cost("L")) < 1e-12
    assert bt3.bucket_of(500e8) == "L" and bt3.bucket_of(100e8) == "M" and bt3.bucket_of(10e8) is None


def test_newey_west_t_and_spearman():
    assert abs(bt3.nw_t([1, 2, 3, 4], lag=0) - 2.5 / math.sqrt(1.25 / 4)) < 1e-9
    assert abs(bt3.nw_t([1, 2, 3, 4], lag=1) - 4.0) < 1e-9                  # 正自我相關 → t 變小
    assert bt3.nw_t([1.0, 1.0]) is None
    assert bt3.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert bt3.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert bt3.spearman([1, 1, 1], [1, 2, 3]) is None


def test_payoff_rules_standard_and_big_upside():
    u = lambda rs: [{"r": r, "hd": 21} for r in rs]
    p = bt3.payoff(u([5, -2, 3, -1, 4]))                                    # 賺錢機率 60%、每月 +1.8%
    assert p["ok"] and p["path"] == "一般" and p["win"] == 60 and abs(p["ratio"] - 4 / 1.5) < 1e-9
    p = bt3.payoff(u([10, -1, -1, 12, -1]))                                 # 40%、賺賠比 11、每月 +3.8%
    assert p["ok"] and p["path"] == "上漲空間大"
    assert not bt3.payoff(u([0.5, 0.4, -0.1]))["ok"]                        # 機率高但太薄
    p = bt3.payoff([{"r": 2.0, "hd": 5}, {"r": 1.0, "hd": 5}])               # 每月平均＝平均 ÷ 持有月數
    assert abs(p["m"] - 1.5 / (5 / 21)) < 1e-9 and p["ratio"] == math.inf


def test_sel_stats_drop_top_five_percent():
    us = [{"d": f"2026-{1 + i % 12:02d}-01", "xe": float(i)} for i in range(20)]
    s = bt3.sel_stats(us)
    assert s["n"] == 20 and s["k_drop"] == 1 and abs(s["drop5"] - sum(range(19)) / 19) < 1e-9
    assert s["pos"] == 95


def test_account_rollover_limit_up_and_liquidation():
    T = 7
    A = ([100, 100, 100, 110, 110, 110, 110], [100, 100, 110, 110, 121, 121, 121])
    B = ([50, 50, 50, 55, 50, 50, 50], [50, 50, 50, 50, 50, 50, 50])       # 第 3 天開盤 55 ≥ 50×1.095 → 漲停買不到
    P = _P({"A": A, "B": B}, T)
    acc = bt3.account(P, [(0, 2, ["A"]), (2, 4, ["A", "B"]), (5, 6, ["B"])], "L", mult=0)
    r = [u["r"] for u in acc["units"]]
    assert r == pytest.approx([10.0, 5.0, 0.0])                             # 第二期 A 減到一半、B 買不到 → 半倉 +10%
    assert [u["lim"] for u in acc["units"]] == [0, 1, 0]
    assert acc["curve"][-1][1] == pytest.approx(1.155)
    assert acc["units"][1]["to"] == pytest.approx(0.0)                      # 續抱 A 只減碼、沒有買進


def test_account_round_trip_cost_and_vs_ew():
    T = 4
    P = _P({"A": ([100] * T, [100] * T), "B": ([100] * T, [100, 100, 102, 104])}, T)
    acc = bt3.account(P, [(0, 2, ["A"])], "L")
    assert acc["units"][0]["r"] == pytest.approx(-bt3.rt_cost("L") * 100, abs=1e-3)   # 價格不動 → 只剩來回成本
    ew = bt3.account(P, [(0, 2, ["A", "B"])], "L", mult=0, limit=False)
    U = bt3.vs_ew(acc, ew)
    assert U[0]["ew"] == pytest.approx(1.0) and U[0]["xe"] == pytest.approx(U[0]["r"] - 1.0)


def test_quint_monotone_signal():
    T, n = 3, 25
    ser = {f"S{i:02d}": ([100] * T, [100, 100, 100 + i]) for i in range(n)}  # 分數越高、下一期漲越多
    P = _P(ser, T)
    rows = [(0, 2, {c: float(i) for i, c in enumerate(sorted(ser))})]
    q = bt3.quint(P, rows)
    assert q["n"] == 1 and q["mono"] == pytest.approx(1.0) and q["ic"] == pytest.approx(1.0)
    assert q["sp"] == pytest.approx(20.0)                                   # 最高組平均 +22%、最低組 +2%
    q2 = bt3.quint(P, rows, asc=True)                                       # 反轉策略：選分數低的那端
    assert q2["sp"] == pytest.approx(-20.0) and q2["ic"] == pytest.approx(-1.0)


def test_trade_units_and_slots():
    T = 6
    P = _P({"A": ([100] * T, [100, 100, 105, 110, 110, 110]), "B": ([100] * T, [100] * T)}, T)
    I = [1.0, 1.0, 1.01, 1.02, 1.02, 1.02]
    IO = [1.0, 1.0, 1.0, 1.01, 1.02, 1.02]
    EW = {"L": (I, IO), "M": (I, IO)}
    trs = [{"c": "A", "d": P.cal[0], "st": "closed", "held": 3, "r": 10.0 - 0.585},
           {"c": "B", "d": P.cal[1], "st": "closed", "held": 3, "r": -0.585}]
    U = bt3.trade_units(trs, P, EW)
    assert U[0]["b"] == "L" and U[0]["x"] == 3 and U[0]["r"] == pytest.approx(10.0 - bt3.rt_cost("L") * 100)
    assert U[0]["xe"] == pytest.approx(U[0]["r"] - 2.0)                     # 等權開盤 1.0 → 收盤 1.02
    sl = bt3.slots(P, U, n=1)
    assert sl["taken"] == 1 and sl["skipped"] == 1                          # 一格：B 進場時 A 還在
    assert sl["curve"][-1][1] == pytest.approx(1 + U[0]["r"] / 100)


def test_grade3_rules():
    sel = {"n": 40, "xe": 1.2, "t": 2.4, "drop5": 0.8}
    pay = {"n": 40, "ok": True, "win": 65, "m": 1.5, "ratio": 1.8}
    nb = {"n": 9, "pos": 9}
    g = bt3.grade3(sel, pay, 1.0, nb)
    assert g["grade"] == "B" and "樣本外尚未驗證" in g["why"]
    g = bt3.grade3(sel, pay, 1.0, nb, oos={"n": 60, "xe": 0.5, "t": 1.3}, fwd={"n": 12, "xe": 0.4})
    assert g["grade"] == "A" and g["why"] == []
    assert bt3.grade3(sel, {**pay, "ok": False, "win": 50, "m": 0.4, "ratio": 1.0}, 1.0, nb)["grade"] == "C"
    assert bt3.grade3({**sel, "drop5": -0.1}, pay, -0.2, nb)["grade"] == "C"     # 穩健度兩項未過
    assert bt3.grade3(sel, pay, 1.0, {"n": 9, "pos": 4})["grade"] == "C"         # 鄰近不到一半為正
    g = bt3.grade3(sel, pay, 1.0, {"n": 9, "pos": 5})
    assert g["grade"] == "B" and any("參數鄰近" in w for w in g["why"])
    assert bt3.grade3(sel, pay, 1.0, nb, oos={"n": 60, "xe": -0.3, "t": -1.0})["grade"] == "C"


def test_v3data_columns_month_ends_and_caps(tmp_path, monkeypatch):
    from datetime import date
    from arm import clock
    from arm.lab import store, v3data
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(clock, "today_tw", lambda: date(2013, 3, 15))
    doc = v3data._cols({"2013-01-03": [1, 2, 0.5, 1.5, 100, 1.4], "2013-01-02": [1, 1, 1, 1, 10, 0.9]}, "a")
    assert doc["t"] == ["2013-01-02", "2013-01-03"] and doc["c"] == [1, 1.5] and doc["a"] == [0.9, 1.4]
    cal = ["2013-01-30", "2013-01-31", "2013-02-26", "2013-02-27", "2013-03-01"]
    assert v3data.month_ends(cal, k=2) == [("2013-01", ["2013-01-31", "2013-01-30"]),
                                            ("2013-02", ["2013-02-27", "2013-02-26"])]   # 本月不算
    store.write("v3me_tw", "2013-01", {"d": "2013-01-31", "s": {"2330": [100.0, 2.5e10], "1101": [30.0, 3e9]}})
    store.write("v3me_tp", "2013-01", {"d": "2013-01-31", "s": {"5347": [20.0, 1.6e9]}})
    store.write("v3me_tw", "2013-02", {"d": "2013-02-27", "s": {"1101": [40.0, 3e9]}})
    mx = v3data.me_caps()
    assert mx == {"2330": 2.5e12, "1101": 1.2e11, "5347": 3.2e10}
    store.write("mkt", "2013-03-14", {"q_tw": {"2330": [0, 0, 0, 101.0, 0, 0], "0050": [0, 0, 0, 50.0, 0, 0]},
                                      "q_tp": {"5347": [0, 0, 0, 21.0, 0, 0, 1.6e9]},
                                      "x_tw": {"2330": [70.0, 2.5e10]}})
    assert [c for c, _, _ in v3data.current_list()] == ["2330", "5347"]               # ETF 排除、市值由大到小


def test_market_v3_parsers():
    from arm.lab import market
    assert market.parse_mfi94u({"fields": ["日期", "指數"], "data": [["103/01/02", "12,724.76"], ["x", "1"]]}) == \
        {"2014-01-02": 12724.76}
    doc = {"tables": [{"fields": ["除權息日期", "代號", "名稱", "除權息前收盤價", "除權息參考價", "權值", "息值",
                                  "權值+息值", "權/息", "漲停價", "跌停價", "開始交易基準價", "減除股利參考價", "現金股利",
                                  "每仟股無償配股"],
                       "data": [["102/07/16", "5347", "世界", "35.90", "34.93", "0", "0.97", "0.97", "息", "", "", "",
                                 "", "0.97", "0"]]}]}
    assert market.parse_tp_exright(doc) == [["2013-07-16", "5347", 35.9, 34.93, 0.97, 0.0]]


def test_bt3d_panel_total_return_prices_and_month_end_caps(tmp_path, monkeypatch):
    from arm.lab import bt3d, store
    monkeypatch.setattr(store, "LAB", tmp_path)
    t = ["2013-01-02", "2013-01-03", "2013-01-04", "2013-01-07", "2013-01-08", "2013-01-09", "2013-01-10",
         "2013-01-11", "2013-01-14", "2013-01-15", "2013-01-16", "2013-01-17"]
    n = len(t)
    flat = lambda xs: {"o": xs, "h": xs, "l": xs, "c": xs}
    store.write("v3px", "TWII", {"m": "idx", "src": "yahoo", "t": t, **flat([100.0 + i for i in range(n)]),
                                 "v": [1] * n, "a": [100.0 + i for i in range(n)]})
    # Yahoo：1/04 除息 0.5（還原收盤在除息前是 收盤 × 0.95）
    y = [10, 10] + [9.5] * (n - 2)
    store.write("v3px", "1101", {"m": "tw", "src": "yahoo", "t": t, **flat(y), "v": [1000] * n,
                                 "a": [9.8] * 2 + [9.5] * (n - 2)})          # Yahoo 少扣（0.98），以官方 0.95 為準
    # FinMind 原始價（已下市）：1/04 除息，前收 20、參考價 19
    store.write("v3px", "2311", {"m": "?", "src": "finmind", "t": t, **flat([20, 20] + [19] * (n - 2)),
                                 "v": [5] * n, "val": [100.0] * n})
    store.write("divtw", "2013", {"rows": [["2013-01-04", "2311", 1.0, "息", 20.0, 19.0],
                                          ["2013-01-04", "1101", 0.5, "息", 10.0, 9.5]]})
    store.write("v3me_tw", "2013-01", {"d": "2013-01-03", "s": {"1101": [10.0, 3e9], "2311": [20.0, 1e9]}})
    P = bt3d.Panel(min_days=3)
    assert P.codes == ["1101", "2311"] and P.T == n
    assert P.s["1101"]["c"] == pytest.approx([9.5] * n)                         # 除息日沒有跳空
    assert P.s["2311"]["c"] == pytest.approx([19] * n)
    assert P.s["1101"]["o"][2] / P.s["1101"]["c"][1] == pytest.approx(1.0)     # 除息日開盤對前收（以參考價為基準）
    assert P.cap["1101"][:3] == [None, 3e10, 3e10]                             # 月底快照日之前沒有市值
    assert P.liq["2311"][8] is None and P.liq["2311"][9] == pytest.approx(100.0)   # 20 日均要有 10 個值
    assert P.liq["1101"][11] == pytest.approx((2 * 10 + 10 * 9.5) * 1000 / 12)
    assert P.elig(10, 2.5e10, 0) == frozenset({"1101"})                       # packtest.Px 介面照用（2311 只有 200 億）


def test_bt3d_mops_cumulative_eps_to_quarterly(tmp_path, monkeypatch):
    from arm.lab import bt3d, store
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write("v3isq", "2014Q1", {"sii": {"2330": 1.85}, "otc": {"5347": 0.84}})
    store.write("v3isq", "2014Q2", {"sii": {"2330": 4.15}, "otc": {}})
    store.write("v3isq", "2014Q4", {"sii": {"2330": 10.18}, "otc": {"5347": 3.35}})   # 缺 Q3 → Q4 不算
    store.write("v3eps", "2330", {"eps": {"2013-12-31": 1.5, "2014-03-31": 1.9}})
    e = bt3d.load_eps()
    assert e["2330"] == {"2013-12-31": 1.5, "2014-03-31": 1.85, "2014-06-30": 2.3}  # 官方彙總表優先
    assert e["5347"] == {"2014-03-31": 0.84}
