"""參數鄰近檢查的規格鎖（arm/lab/nbrspec.py；docs/lab_signal_quality_plan.md 第 12 節）。改任何一個值＝VER＋1。"""
from arm.lab import bottomspec as BOS
from arm.lab import bubspec as BS
from arm.lab import crashspec as CS
from arm.lab import heatspec as HS
from arm.lab import heatspec_us as U
from arm.lab import hotddspec as HDS
from arm.lab import nbrspec as N
from arm.lab import sigoos as OOS
from arm.lab import sigspec as S


def test_version_and_scope():
    assert N.VER == 1 and N.SPEC_DATE == "2026-11-01"
    assert N.CATS == OOS.MARKET_CATS + ("buy",)
    assert N.OUT == "data/lab/robust_research.json"


def test_neighbors_locked():
    assert N.HZ == {20: (15, 25), 60: (45, 75), 250: (190, 310)}
    assert N.TH == ((75, 25), (85, 15)) and N.PRIOR == (15, 25) and N.EXIT == (3, 5) and N.WEEKS == (11, 15)
    assert N.WIN == {"d": ((500, 250), (1000, 500)), "m": ((96, 48), (144, 72)), "d10": ((2000, 1000), (3000, 1500)),
                     "q10": ((32, 16), (48, 24)), "cd": ((500, 250), (1000, 500)), "cm": ((24, 24), (48, 48))}
    assert N.SCEN == ((55, 45), (65, 35))
    assert N.INST_TAIL == ((97, 3), (93, 7)) and N.INST_RUN == {5: (4, 6), 10: (8, 9, 11, 12)}
    assert N.INST_WIN == {5: (4, 6), 20: (16, 24), 60: (48, 72)}
    assert N.MA == {20: (18, 22), 60: (54, 66), 240: (216, 264)}
    assert N.EV_PRIOR == (8, 12) and N.EV_CONF == (2, 4) and N.PIVOT == (0.04, 0.06)
    assert N.DT_TOL == (0.012, 0.018) and N.DT_GAP == (18, 26) and N.HS_RATIO == (2.0, 3.0)
    assert [N.deriv_nb(n) for n in (3, 4, 5, 20, 63)] == [(2, 4), (3, 5), (4, 6), (16, 24), (50, 76)]
    assert N.BUB == {"psy": {"PSY_RUN": (2, 4)}, "run2": {"RUN2_PCT": (80.0, 120.0)}, "ath": {"RUN2_ATH": (0.04, 0.06)},
                     "tz": {"TREND_Z": (1.6, 2.4)}, "erun": {"E_RUN": (2, 4)},
                     "gpx": {"G_PRICE_MONTHS": (2, 4), "G_PRICE_DAYS": (61, 122)},
                     "fuel": {"FUEL_PCT": (88.0, 92.0)}, "val": {"VAL_PCT": (94.0, 96.0)}}
    assert N.BUB_DIMS["L2"] == N.BUB_DIMS["L3"] == tuple(N.BUB) and N.BUB_DIMS["P2"] == ("run2", "ath")
    assert N.BUY["e5th"] == {"E5_TH": (0.8, 1.2)} and N.BUY["c9"] == {"C9_LO": (135.0, 145.0), "C9_HI": (145.0, 155.0)}
    assert N.BUY["c3lo"] == {"C3_LO": (0.32, 0.48)} and N.BUY["c3hi"] == {"C3_HI": (0.538, 0.692)}
    assert N.BUY_RULE_DIMS["B1"] == () and N.BUY_RULE_DIMS["W10"] == ("wait",) and N.BUY_RULE_DIMS["C3"][0] == "sigwin"
    assert N.VAR_DIMS["hot13"] == ("th", "wk", "win") and N.VAR_DIMS["hot_out"] == ("th", "ex", "win")
    assert N.TECH_DIMS["x_dead"] == ("ma20", "ma60", "tpr", "tcf") and N.TECH_DIMS["dtop"] == ("pv", "dtol", "dgap")
    assert set(N.TECH_DIMS) == set(HS.EVENTS)


def test_neighbors_bracket_the_current_values():
    """每個維度的往下、往上要夾住現在正式用的值（規格寫的「原本」就是程式現在用的）。"""
    lo_hi = lambda nb, x: nb[0] < x < nb[1]           # noqa: E731
    assert set(N.HZ) == set(S.H_DIM.values()) | {S.H_TECH, S.H_CRASH, S.H_BUB, S.H_BUY, S.H_SCEN, S.H_MULTI, S.H_DERIV}
    assert all(lo_hi(v, h) for h, v in N.HZ.items())
    assert N.TH[0][0] < S.HOT < N.TH[1][0] and N.TH[1][1] < S.COLD < N.TH[0][1]
    assert HS.EVT == {"hot": (S.HOT, 20), "cold": (S.COLD, 20)} and HDS.EVT_PRIOR == 20 and lo_hi(N.PRIOR, 20)
    assert lo_hi(N.EXIT, S.EXIT_MIN) and lo_hi(N.WEEKS, S.HOT_WEEKS)
    assert HS.PCT_WIN == {"d": 750, "m": 120} and HS.PCT_MIN == {"d": 375, "m": 60}
    assert HS.PCT_WIN_ITEM == {"X2": (2500, 1250), "X3": (2500, 1250)}
    assert U.PCT_WIN_ITEM == {"X2": (2500, 1250), "X3": (2500, 1250), "X11": (2500, 1250), "S5": (40, 20)}
    assert CS.PCT_DAILY == (750, 375) and CS.PCT_MONTHLY == (36, 36)
    assert N.SCEN[0][0] < S.SCEN_HI < N.SCEN[1][0] and N.SCEN[1][1] < S.SCEN_LO < N.SCEN[0][1]
    assert S.INST_DAY == (95, 5) and set(N.INST_RUN) == set(S.INST_RUN) and set(N.INST_WIN) == set(S.INST_POS_WIN)
    assert all(lo_hi(v, k) for k, v in N.INST_WIN.items())
    assert all(min(v) < k < max(v) for k, v in N.INST_RUN.items())
    assert {20, 60, 240} <= set(HS.MA_NS) and all(lo_hi(v, k) for k, v in N.MA.items())
    assert lo_hi(N.EV_PRIOR, HS.EV_PRIOR) and lo_hi(N.EV_CONF, HS.EV_CONF) and lo_hi(N.PIVOT, HS.PIVOT_THR)
    assert lo_hi(N.DT_TOL, HS.DT_TOL) and lo_hi(N.DT_GAP, HS.DT_GAP) and lo_hi(N.HS_RATIO, HS.HS_RATIO)
    for dim, ps in N.BUB.items():
        for k, nb in ps.items():
            assert lo_hi(nb, getattr(BS, k)), (dim, k)
    for dim, ps in N.BUY.items():
        for k, nb in ps.items():
            base = 1.0 if k == "E5_TH" else getattr(BOS, k)
            assert lo_hi(nb, base), (dim, k)
    for spec in (HS.DERIV, U.DERIV):
        for k, sp in spec.items():
            for f in N.DERIV_KEYS:
                if f in sp:
                    assert lo_hi(N.deriv_nb(sp[f]), sp[f])


def test_judgment_rule():
    e = S.THERMO_EDGE
    assert N.dim_ok([(10, 0.70, 0.60), (12, 0.62, 0.60)], S.N_MIN, e) is True        # 1 of 2 過
    assert N.dim_ok([(10, 0.64, 0.60), (12, 0.62, 0.60)], S.N_MIN, e) is False       # 都不過
    assert N.dim_ok([(3, 0.10, 0.60), (12, 0.70, 0.60)], S.N_MIN, e) is True         # 次數不夠的不算
    assert N.dim_ok([(3, 0.90, 0.60), (4, 0.90, 0.60)], S.N_MIN, e) is None          # 能用的一個都沒有
    assert N.dim_ok([(10, 0.90, 0.60)], S.N_MIN, e, same=True) is None               # 鄰近都和原本一樣
    assert N.dim_ok([(9, 0.70, 0.6), (9, 0.6, 0.6), (9, 0.6, 0.6), (9, 0.7, 0.6)], S.N_MIN, e) is True   # 2 of 4
    assert N.dim_ok([(9, 0.70, 0.6), (9, 0.6, 0.6), (9, 0.6, 0.6)], S.N_MIN, e) is False                 # 1 of 3
    assert N.overall({"a": True, "b": None}) is True and N.overall({"a": True, "b": False}) is False
    assert N.overall({"a": None}) is None and N.overall({}) is None
