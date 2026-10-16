"""策略健檢資料層（arm/lab/health.py；docs/lab_selfopt_plan.md 第 3、4 節）：進場特徵、持有路徑、分位數表。"""
import pytest

from arm.lab import bt3, health as H, trades


class _P:
    """最小的 Px 介面（cal、T、s、cap、idx）。"""

    def __init__(self, ser: dict, T: int, cap: float = 400e8, idx=None):
        self.T, self.cal = T, [f"2026-01-{i + 1:02d}" for i in range(T)]
        self.s = {c: {"o": [None if x is None else float(x) for x in o], "c": [None if x is None else float(x) for x in cl],
                      "h": [None if x is None else x * 1.01 for x in cl], "l": [None if x is None else x * 0.99 for x in cl],
                      "v": [1.0] * T} for c, (o, cl) in ser.items()}
        self.cap = {c: [cap] * T for c in ser}
        self.codes = sorted(ser)
        self.idx = idx or [100.0] * T


def test_path_cumulative_open_exit_and_missing_close():
    S = {"o": [10, 10, 11, 12, 12], "c": [10, 11, None, 13, 9]}
    assert H.path(S, 1, 4) == [10.0, 10.0, 30.0, -10.0]                    # 缺收盤沿用前一天
    assert H.path(S, 1, 4, op=True) == [10.0, 10.0, 30.0]                  # 第 4 天開盤賣：路徑到前一天收盤
    assert H.path(S, 1, None) == [10.0, 10.0, 30.0, -10.0]                 # 持有中：到最後一天
    assert H.path({"o": [None, None], "c": [1, 1]}, 1, 1) == []


def test_entry_features_gap_pre_regime():
    S = {"o": [None] * 21 + [10.5], "c": [8.0] + [9.0] * 19 + [10.0, 10.0]}
    assert H.gap(S, 21) == 5.0                                             # 10.5 ÷ 前一天收盤 10 − 1
    assert H.pre(S, 20) == 25.0                                            # 第 20 天收盤 10 ÷ 第 0 天 8 − 1
    assert H.pre(S, 19) is None
    idx, ma = [100, None, 90], [95, None, 95]
    assert H.regime(idx, ma, 0) is True and H.regime(idx, ma, 2) is False
    assert H.regime(idx, ma, 1) is True                                    # 當天缺值往前找
    assert H.regime([None], [None], 0) is None


def test_bucket_and_net_cost():
    assert H.bucket(400e8) == "L" and H.bucket(100e8) == "M" and H.bucket(None) == "M" and H.bucket(10e8) == "M"
    assert H.net(0.0, "L") == pytest.approx(trades.trip_ret(100, 100, "L"))
    assert H.net(0.1, "M") == pytest.approx(trades.trip_ret(100, 110, "M"))


def test_mean_basket_and_staggered_paths():
    assert H.mean_path([[1, 2, 3], [3, 4]]) == [2.0, 3.0, 3.0]
    S = {"A": {"o": [None, 10, 0], "c": [10, 11, 12]}, "B": {"o": [None, 20, 0], "c": [20, 18, 22]},
         "C": {"o": [None, None, 0], "c": [5, 5, 5]}}
    assert H.basket(lambda c: S[c], ["A", "B", "C"], 1, 2) == [0.0, 15.0]   # C 沒開盤價不算
    # 臺灣50 同一次審核：A 第 0 天買、第 1 天賣（出場 +5%）；B 第 1 天才買
    out = H.staggered([(0, [2.0, 3.0], 5.0), (1, [-1.0, 1.0, 4.0], None)], 0)
    assert out == [2.0, 1.0, 3.0, 4.5]


def test_qtable_percentile_lookup():
    ps = [[float(v), float(v) * 2] for v in range(21)]                    # 21 筆：第 1 天 0～20、第 2 天 0～40
    tab = H.qtable(ps, min_n=20)
    assert tab["n"] == [21, 21] and tab["q"][0][0] == 0 and tab["q"][0][-1] == 20 and tab["q"][0][10] == 10
    assert H.at_day(tab, 1, 10.0) == 50.0 and H.at_day(tab, 2, 10.0) == 25.0
    assert H.at_day(tab, 1, -5.0) == 0.0 and H.at_day(tab, 1, 99.0) == 100.0
    assert H.at_day(tab, 3, 1.0) is None and H.at_day({}, 1, 1.0) is None
    short = H.qtable([[1.0]] * 19 + [[1.0, 2.0]], min_n=20)
    assert short["n"] == [20]                                              # 第 2 天只剩 1 筆 → 表停在第 1 天


def test_tercile_and_gap_bins():
    cs = H.cuts(list(range(1, 10)))
    assert cs == [pytest.approx(11 / 3, abs=1e-4), pytest.approx(19 / 3, abs=1e-4)]
    assert [H.tercile(x, cs) for x in (1, 4, 7, None)] == [0, 1, 2, None]
    assert H.cuts([1, 2]) is None
    assert [H.gap_bin(g) for g in (-1.5, -1.0, 0.99, 1.0, 2.9, 3.0, None)] == [0, 1, 1, 2, 2, 3, None]


def test_from_account_matches_trips_rank_and_basket():
    T = 8
    A = ([100] * T, [100, 100, 104, 106, 106, 108, 110, 110])
    B = ([50] * T, [50, 50, 49, 48, 47, 50, 51, 52])
    C = ([20] * T, [20, 20, 21, 22, 23, 24, 25, 26])
    P = _P({"A": A, "B": B, "C": C}, T)
    periods = [(0, 3, ["A", "B"]), (3, 6, ["A", "C"])]
    log = []
    bt3.account(P, periods, "L", log=log)
    out = H.from_account(P, periods, log, "L", scores={0: {"A": 2.0, "B": 3.0}, 3: {"A": 1.0, "C": 5.0}},
                         fw_from="2026-01-04")
    tr = {(x["c"], x["d"]): x for x in out["tr"]}
    tp, _ = trades.trips(log)
    assert len(tr) == len(tp) == 3                                         # A 續抱兩期＝一筆、B、C
    a = tr[("A", "2026-01-01")]
    assert a["j"] == 1 and a["i"] == 6 and a["rk"] == 2 and a["b"] == "L" and a["fw"] is False
    assert a["r"] == pytest.approx(trades.trip_ret(100, 110, "L"), abs=0.01)
    b_ = tr[("B", "2026-01-01")]
    assert b_["op"] is True and b_["rk"] == 1                              # 第二期不在名單 → 開盤賣
    assert tr[("C", "2026-01-04")]["fw"] is True and tr[("C", "2026-01-04")]["rk"] == 1
    assert [len(b["p"]) for b in out["bk"]] == [3, 3]
    assert out["bk"][0]["p"][:2] == [0.0, pytest.approx((4.0 + (-2.0)) / 2)]   # 第 1 天＝進場日收盤


class _D:
    def __init__(self, ser: dict, T: int):
        self.T, self.cal = T, [f"2026-02-{i + 1:02d}" for i in range(T)]
        self.ix = {d: i for i, d in enumerate(self.cal)}
        self._s = ser
        self.calls = 0

    def series(self, c):
        self.calls += 1
        o, cl = self._s[c]
        return {"o": o, "c": cl}

    def taiex(self):
        return [100.0] * self.T


def test_from_trades_cost_conversion_paths_and_review_ranks():
    T = 6
    D = _D({"A": ([10.0] * T, [10, 10, 11, 12, 12, 13]), "B": ([20.0] * T, [20, 20, 19, 18, 18, 17])}, T)
    cal = D.cal
    trs = [{"c": "A", "d": cal[0], "bd": cal[1], "sd": cal[4], "st": "closed", "r": 19.415, "entry": 10, "exit": 12,
            "review": "R1", "mom": 30.0},
           {"c": "B", "d": cal[0], "bd": cal[1], "st": "open", "r": -10.0, "entry": 20, "now": 18, "review": "R1",
            "mom": 40.0},
           {"c": "A", "d": cal[2], "st": "skip"}, {"c": "B", "d": cal[5], "st": "cand"}]
    out = H.from_trades(D, trs, cap_of=lambda c, t: 500e8 if c == "A" else 80e8, rank_key="mom", group="review")
    tr = out["tr"]
    assert [x["c"] for x in tr] == ["A", "B"] and D.calls == 2              # 沒進場、候選中的不算；價格有快取
    a, b = tr
    assert a["b"] == "L" and a["r"] == pytest.approx(19.415 + 0.585 - bt3.rt_cost("L") * 100, abs=0.01)
    assert a["path"] == [0.0, 10.0, 20.0, 20.0] and a["ex"] == 20.0 and a["rk"] == 2 and a["g"] == "R1"
    assert b["b"] == "M" and b["r"] is None and b["i"] is None and b["rk"] == 1 and len(b["path"]) == 5
    assert a["reg"] is None                                                # 沒給 reg_map：用 D.taiex() 算，6 天算不出 200 日均線
    fixed = H.from_trades(D, trs[:1], b_fix="L", cap_of=lambda c, t: 1e8, reg_map={cal[0]: False})["tr"][0]
    assert fixed["b"] == "L" and fixed["reg"] is False
    bk = H.review_baskets(tr)
    assert len(bk) == 1 and bk[0]["g"] == "R1" and bk[0]["p"][1] == pytest.approx((10.0 + -5.0) / 2)


def test_reg_lookup_looks_back():
    cal = ["2026-02-01", "2026-02-02", "2026-02-03"]
    assert H.reg_lookup({"2026-02-01": False}, cal, 2) is False
    assert H.reg_lookup({"2026-02-03": True, "2026-02-01": False}, cal, 2) is True
    assert H.reg_lookup({}, cal, 2) is None


def test_take_full_strips_private_lists():
    """完整交易（_all、_V、_recs、_hl）只給健檢用，回傳頁面前一定移除（頁面會內嵌整份資料）。"""
    from arm.lab import analyze
    strat = {"list": [{"key": "s1", "_all": [1, 2]}, {"key": "s3", "_V": {"early": [3], "post": [4]}}, "x"]}
    grow = {"s5": {"_recs": [5], "tr": {}}}
    v3 = {"v3l": {"_hl": {"tr": []}, "fwd": {}}, "err": "x"}
    full = analyze._take_full(strat, grow, v3)
    assert full == {"hl": {"v3l": {"tr": []}}, "s1": [1, 2], "s3": [3], "s5": [5]}
    assert strat["list"][0] == {"key": "s1"} and strat["list"][1] == {"key": "s3"}
    assert grow == {"s5": {"tr": {}}} and v3 == {"v3l": {"fwd": {}}, "err": "x"}
    assert analyze._take_full({"err": "x"}, {"err": "y"}) == {"hl": {}}
