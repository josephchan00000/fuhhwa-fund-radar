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
