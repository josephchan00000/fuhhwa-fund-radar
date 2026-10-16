# 策略健檢與自我改良（docs/lab_selfopt_plan.md）：optim v1 的候選清單、門檻與判定在看結果前寫定，這裡鎖住。
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import optim as O  # noqa: E402


def test_optim_v1_menu_is_fixed():
    """候選清單事前寫定（2026-10-16 commit 在任何變體回測之前）。要改＝OPT_VER＋1，不在 v1 上改。"""
    assert O.OPT_VER == 1 and O.OPT_SINCE == "2026-10-16"
    keys = {k: [c[0] for c in v] for k, v in O.MENU.items()}
    assert keys == {
        "v3l": ["delay5", "delay10", "gap3", "hold40", "hold80", "stop15", "stop20", "n3", "n8", "reg200"],
        "v7m": ["gap3", "delay1", "delay3", "hold10", "hold2m", "stop10", "stop15", "n3", "n8", "reg200"],
        "v7l": ["gap3", "delay1", "delay3", "hold10", "hold2m", "stop10", "stop15", "n3", "n8", "reg200"],
        "s3": ["k20", "k30", "eff0", "stop10", "n3", "n5"],
        "s5": ["trail25", "trail35", "init15", "init25", "reg200"],
        "s1": ["gapany", "gapm1", "hold2", "hold4", "atr15", "atr25", "reg200"],
    }
    assert sum(len(v) for v in O.MENU.values()) == 48
    sets = {(k, c[0]): (c[2], c[3]) for k, v in O.MENU.items() for c in v}
    assert sets[("v3l", "hold80")] == ({"hold": 80}, [{"hold": 75}, {"hold": 85}])
    assert sets[("v3l", "delay10")] == ({"delay": 10}, [{"delay": 8}, {"delay": 12}])
    assert sets[("v3l", "stop20")] == ({"stop": 0.20}, [{"stop": 0.175}, {"stop": 0.225}])
    assert sets[("v7m", "hold2m")] == ({"sleeves": 2}, [{"sleeves": 3}])
    assert sets[("v7l", "delay1")] == ({"delay": 1}, [{"delay": 2}])
    assert sets[("v7m", "stop10")] == ({"stop": 0.10}, [{"stop": 0.08}, {"stop": 0.12}])
    assert sets[("s3", "eff0")] == ({"out": 0}, [{"out": 1}])
    assert sets[("s3", "n5")] == ({"n": 5}, [{"n": 6}])
    assert sets[("s5", "init25")] == ({"init": 0.25}, [{"init": 0.225}, {"init": 0.275}])
    assert sets[("s1", "gapany")] == ({"gap_max": None}, [{"gap_max": 0.01}, {"gap_max": 0.03}])
    assert sets[("s1", "gapm1")] == ({"gap_max": -0.01}, [{"gap_max": -0.005}, {"gap_max": -0.015}])
    assert sets[("s1", "atr25")] == ({"stop_atr": 2.5}, [{"stop_atr": 2.25}, {"stop_atr": 2.75}])
    for k in ("v3l", "v7m", "v7l", "s5", "s1"):
        assert sets[(k, "reg200")] == ({"reg": 200}, [{"reg": 150}, {"reg": 250}])


def test_optim_menu_one_knob_and_neighbors_differ():
    """每個候選只改一項；相鄰檢查改同一項、數值和現行與候選都不同；候選數值和現行不同。"""
    for k, menu in O.MENU.items():
        cur = O.CURRENT[k]
        assert len({c[0] for c in menu}) == len(menu)
        for key, what, st, nbs in menu:
            assert len(st) == 1 and set(st) <= set(cur), (k, key)
            knob = next(iter(st))
            assert st[knob] != cur[knob], (k, key)
            assert nbs, (k, key)
            for nb in nbs:
                assert set(nb) == {knob} and nb[knob] not in (cur[knob], st[knob]), (k, key, nb)
            assert what and not any(w in what for w in ("建議", "目標價", "保證"))
            assert O.params(k, key) == {**cur, **st}
            assert O.params(k, key, 0) == {**cur, **nbs[0]}
        assert O.params(k) == cur and O.params(k) is not cur


def test_optim_current_matches_live_rules():
    """現行參數必須和各策略程式的常數一致；現行規則改版而這裡沒跟著改 → 紅（改版時 optim 也要出新版本）。"""
    from arm.lab import bt3l, growth, strategy, tw50study, v3live
    assert O.MAIN_FROM == bt3l.OOS_END == "2021-10-01"
    assert O.CURRENT["v3l"]["hold"] == v3live.HOLD3 == 60
    for k in ("v3l", "v7m", "v7l"):
        assert O.CURRENT[k]["n"] == v3live.N == 5
    live = [x[0] for x in v3live.LIVE]
    assert {"v3l", "v7m", "v7l"} <= set(live)
    s1 = next(s for s in strategy.STRATEGIES if s["key"] == "s1")
    assert (O.CURRENT["s1"]["hold"], O.CURRENT["s1"]["stop_atr"], O.CURRENT["s1"]["gap_max"]) == \
        (s1["hold"], s1["stop_atr"], s1["gap_max"]) == (3, 2.0, 0.0)
    assert s1["gap_strict"] is True and s1["ver"] == 1
    assert (O.CURRENT["s3"]["k"], O.CURRENT["s3"]["n"]) == (tw50study.EARLY_K, tw50study.EARLY_N) == (25, 4)
    assert strategy.TW50_VERS[0]["k"] == "early" and strategy.TW50_VERS[0]["ver"] == 1
    for f in ("init", "trail", "maxd", "gap", "wait"):
        assert O.CURRENT["s5"][f] == growth.S5[f], f
    assert growth.S5["ver"] == 1


def test_optim_thresholds_fixed():
    assert (O.ALPHA, O.T_SIG, O.T_REP, O.T_NOREP, O.MDD_PP, O.COST_X) == (0.05, 1.645, 1.0, 2.5, 3.0, 2.0)
    assert O.MIN_N == {"v3l": 8, "v7m": 24, "v7l": 24, "s3": 4, "s1": 30, "s5": 30} and O.MIN_MONTHS == 6
    assert O.HAS_REP == ("v3l", "v7m", "v7l") and O.EVENT == ("v3l", "s3") and O.PER_SIGNAL == ("s1", "s5")
    assert (O.SHADOW_MAX, O.COOLDOWN_DAYS) == (2, 182)
    assert O.NEED == {"v3l": 2, "v7m": 10, "v7l": 10, "s3": 2, "s1": 10, "s5": 10}
    assert (O.BOOT_N, O.SEED) == (2000, 20261016)
    assert O.LIGHT == ((5.0, "明顯低於回測"), (20.0, "偏弱"), (80.0, "符合回測")) and O.LIGHT_TOP == "偏強"
    assert O.FWD_MIN == {"event": 2, "other": 3} and O.HOLD_PCT_EV == 5.0
    assert (O.SPLIT_MIN_N, O.SPLIT_T, O.REG_MA) == (10, 2.0, 200)
    assert [b[2] for b in O.GAP_BINS] == ["低開", "平開", "高開 1～3%", "高開 ≥3%"]
    assert set(O.CURRENT) == set(O.MENU) == set(O.MIN_N) == set(O.NEED) == set(O.UNIT)


def test_optim_p_one_and_holm():
    assert abs(O.p_one(1.645) - 0.05) < 1e-3 and abs(O.p_one(0.0) - 0.5) < 1e-12
    assert O.p_one(None) == 1.0 and O.p_one(-3) > 0.99
    # 4 個候選：0.01 ≤ 0.05/4、0.015 ≤ 0.05/3、0.03 > 0.05/2 → 第三小以後全部不過（即使 0.04 ≤ 0.05）
    assert O.holm([0.03, 0.01, 0.04, 0.015]) == [False, True, False, True]
    assert O.holm([0.2, 0.3]) == [False, False]
    assert O.holm([0.001]) == [True]
    assert O.holm([]) == []


def _c(**kw):
    base = {"n": 40, "months": 12, "mean": 0.8, "t": 3.0, "holm": True, "rep": (0.5, 1.2), "nb": [0.3, 0.1],
            "drop_year": 0.4, "x2": 0.6, "mdd": 30.0, "mdd0": 28.0}
    return {**base, **kw}


def test_optim_tier_rules():
    assert O.tier("v7m", _c()) == ("證據強", [])
    assert O.tier("v7m", _c(rep=(0.5, 0.9))) == ("待觀察", [2])              # 複驗 t 不到 1
    assert O.tier("v7m", _c(rep=None)) == ("待觀察", [2])                    # 有複驗期間的策略缺複驗結果＝不過
    assert O.tier("v7m", _c(holm=False)) == ("待觀察", [1])
    assert O.tier("v7m", _c(nb=[0.3, -0.01])) == ("待觀察", [3])
    assert O.tier("v7m", _c(nb=[])) == ("待觀察", [3])
    assert O.tier("v7m", _c(drop_year=-0.1)) == ("待觀察", [4])
    assert O.tier("v7m", _c(x2=0.0)) == ("待觀察", [5])
    assert O.tier("v7m", _c(mdd=31.01)) == ("待觀察", [6])                   # 回落差超過 3 個百分點
    assert O.tier("v7m", _c(mdd=31.0)) == ("證據強", [])                      # 剛好 3 個百分點仍算
    assert O.tier("v7m", _c(n=23)) == ("樣本不足", [])
    assert O.tier("v7m", _c(mean=0.2, t=1.0, holm=False))[0] == "沒有比較好"
    assert O.tier("v7m", _c(mean=-0.5, t=-2.0, holm=False))[0] == "比較差"
    assert O.tier("v7m", _c(mean=-0.5, t=-1.0, holm=False))[0] == "沒有比較好"
    # 沒有複驗期間：第 2 項改為主要期間校正前 t ≥ 2.5（複驗結果有也不看）
    assert O.tier("s1", _c(rep=None, t=2.6)) == ("證據強", [])
    assert O.tier("s1", _c(rep=None, t=2.4)) == ("待觀察", [2])
    assert O.tier("s1", _c(rep=(-1.0, -2.0), t=2.6)) == ("證據強", [])
    assert O.tier("s1", _c(rep=None, months=5)) == ("樣本不足", [])
    assert O.tier("s3", _c(rep=None, n=4, t=2.5)) == ("證據強", [])
    assert O.tier("s3", _c(rep=None, n=3)) == ("樣本不足", [])
    assert O.checks("s3", _c(rep=None, t=2.49))[2] is False and O.checks("s3", _c(rep=None))[2] is True


def test_optim_light():
    assert O.light(None, 5, False) == "樣本太少"
    assert O.light(50.0, 2, False) == "樣本太少" and O.light(50.0, 2, True) == "符合回測"
    assert O.light(4.9, 5, False) == "明顯低於回測"
    assert O.light(5.0, 5, False) == "偏弱" and O.light(19.9, 5, False) == "偏弱"
    assert O.light(20.0, 5, False) == "符合回測" and O.light(79.9, 5, False) == "符合回測"
    assert O.light(80.0, 5, False) == "偏強"


def test_selfopt_plan_doc_records_decisions():
    """規劃文件第 9 節寫明使用者的四個決定；第 5 節的候選清單與程式一致（48 個）。"""
    doc = (ROOT / "docs/lab_selfopt_plan.md").read_text(encoding="utf-8")
    assert "## 9. 使用者的決定（2026-10-16）" in doc and "待使用者確認" not in doc
    for s in ("你回「好」才換", "只改執行細節", "每週一重跑改良回測", "最大回落不變差"):
        assert s in doc, s
    assert "合計 48 個候選" in doc
    for k, menu in O.MENU.items():
        for key, *_ in menu:
            assert f"`{key}`" in doc, (k, key)
