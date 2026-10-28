"""《超級績效》選股（W9）的規格鎖定：算任何報酬之前寫定（arm/lab/sepaspec.py、docs/lab_sepa_pick_plan.md）。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import sepaspec as S
from arm.lab import superx as SX


def test_sepa_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-29"
    assert S.MAIN == (("tt_all", "=", True), ("rs", ">=", 80), ("ey", ">=", 0.25), ("ry3", ">=", 0.25),
                      ("or", (("eacc", ">", 0), ("racc", ">", 0))))
    assert S.SCREENS["main"] == S.MAIN
    assert S.SCREENS["strict"][-2:] == (("eacc", ">", 0), ("racc", ">", 0))
    assert S.SCREENS["trend"] == (("tt_all", "=", True), ("rs", ">=", 80))
    assert S.RS_WEIGHTS == ((63, 0.4), (126, 0.2), (189, 0.2), (252, 0.2))
    assert S.TRADE == {"weight": 0.125}
    assert S.EXITS == {"ma50": {"ma_exit": 50, "max_hold": None, "stop": None},
                       "hold60": {"ma_exit": None, "max_hold": 60, "stop": None},
                       "book": {"ma_exit": 50, "max_hold": None, "stop": 0.08}}
    assert S.EXIT == "ma50" and S.MARKET == {"ma": 200}
    assert S.MAIN_CFG == {"screen": "main", "exit": "ma50", "market": True}
    assert len(S.VARIANTS) == 13 and S.MAIN_CFG in S.VARIANTS
    assert S.START == "2019-01-02" and S.START_LONG == "2014-01-02"
    assert S.HALVES == (("2019-01-01", "2022-12-31"), ("2023-01-01", "2100-12-31"))
    assert S.COMPARE == "R60" and S.PASS == {"mdd_extra": 10.0}


def test_features_exist_in_superx():
    keys = {c[0] for scr in S.SCREENS.values() for c in scr if c[0] != "or"} | {"eacc", "racc"}
    assert keys <= set(SX.FK)


def test_passes_and_missing_values():
    f = {"tt_all": True, "rs": 85, "ey": 0.3, "ry3": 0.26, "eacc": -0.1, "racc": 0.02}
    assert S.passes(f) and not S.passes(f, "strict") and S.passes(f, "trend")
    assert not S.passes({**f, "racc": None})                 # 兩個都沒在加速
    assert not S.passes({**f, "ey": None})                   # 去年同季虧損＝沒有 EPS 年增率
    assert not S.passes({**f, "rs": 79})
    assert not S.passes({**f, "tt_all": False}, "trend")


def test_verdict():
    r60 = {"cagr": {"all": 0.40, "h1": 0.20, "h2": 0.60}, "mdd": {"all": 0.46}}
    tr = {"cagr": {"all": 0.27, "h1": 0.15, "h2": 0.42}, "mdd": {"all": 0.29}}
    win = {"cagr": {"all": 0.45, "h1": 0.21, "h2": 0.61}, "mdd": {"all": 0.55}}
    assert S.verdict(win, r60, tr) == "換"
    assert S.verdict({**win, "mdd": {"all": 0.57}}, r60, tr) == "觀察"      # 回落深超過 10 點
    obs = {"cagr": {"all": 0.30, "h1": 0.16, "h2": 0.43}, "mdd": {"all": 0.30}}
    assert S.verdict(obs, r60, tr) == "觀察"
    assert S.verdict({**obs, "cagr": {"all": 0.30, "h1": 0.10, "h2": 0.43}}, r60, tr) == "沒有用"
