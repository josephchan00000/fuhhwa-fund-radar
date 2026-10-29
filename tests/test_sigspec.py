"""訊號總覽實務判定的規格（docs/lab_signal_plan.md）：規格鎖定。

規格是在算任何訊號的命中率之前寫定的（VER 1，2026-10-19；VER 2 同日只改個股策略的次數下限，規劃第 15 節；
VER 3，2026-10-20，警示改看最大回撤，docs/lab_warn_mdd_plan.md；VER 4 同日加情境；VER 5 同日加報酬與相似的日子；VER 6 同日加法人買賣超；VER 7 同日法人只當訊號；
VER 8 同日判定改用打折後的機率、運氣檢查、同類合併，docs/lab_noise_plan.md（沒有上線）；VER 9 同日改用打亂日子測試，同文件第 10 節；
VER 10，2026-10-21，大跌後買點改看實際報酬，docs/lab_expert_plan.md 第 9 節；VER 13 同日，落底訊號跟著 bottomspec VER 4 多三個；
VER 14，2026-10-22，次數少的訊號打亂測試門檻放寬到 10%，docs/lab_noise_plan.md 第 13 節；VER 15 同日，溫度計三個看多久都算，同文件第 14 節；VER 16 同日，溫度計下面加「過去讀數這樣的時候」，同文件第 14.10 節；
VER 17 同日，判定改看絕對成績、次數少的另列難得機會、報酬加排除極端，docs/lab_practical_plan.md；VER 18 同日，「預估之後」，同文件第 10 節；
VER 19 同日，「預估之後」的報酬留下來的比例改用平均量，同文件第 10.5 節；
VER 20 同日，資料與訊號盤查：一段遇到相反的極端就切開、最新的讀數取代舊的事件、資料過期的項目不算現在成立，docs/lab_audit_plan.md；
VER 21 同日，今天的清單與溫度計改用預估之後仍差 3 點以上、加偏弱（1 個月）、跨期間的逐年樣本外，同文件第 11 節；
VER 24，2026-10-28，跌幅一律列最差一次（不用中位數）、和大跌同一個算法，只改呈現，docs/lab_audit_plan.md 第 14 節）。
要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
from arm.lab import analyze as AN
from arm.lab import backtest as BT
from arm.lab import bottomspec as BS
from arm.lab import bt3
from arm.lab import crashspec as CS
from arm.lab import heatspec as HS
from arm.lab import heatspec_us as U
from arm.lab import sigspec as X


def test_sig_spec_v1_is_locked():
    assert X.VER == 24 and X.SPEC_DATE == "2026-10-28"
    assert BS.VER == 4 and "C9" in BS.SIG_MK["tw"] and "C8" in BS.SIG_MK["spx"]   # VER 13：大跌後買點的規則跟著 bottomspec VER 4
    assert X.H_BUY == 60                                                  # VER 10：大跌後買點看買進後 3 個月有沒有漲
    assert X.MARKETS == ("tw", "spx", "ixic", "ndx", "sox")
    assert X.LAG == 1 and X.DIRS == ("up", "warn", "buy") and X.WARN_LONG == 0.20
    assert X.WARN_TH_IDX == {20: 1, 60: 2}
    assert X.HIT_MIN == {"up": 0.60, "warn": 0.50, "buy": 0.60}
    assert (X.EDGE_GOOD, X.EDGE_REF, X.N_MIN, X.RECENT_YEARS, X.RECENT_N) == (0.10, 0.05, 5, 10, 5)   # VER 9：次數下限 10 → 5
    assert X.TIERS == ("good", "rare", "ref", "none", "few") and set(X.TIER_NAMES) == set(X.TIERS) == set(X.TIER_MARK)   # VER 17 多 ◆
    assert X.TIER_NAMES["ref"] == "可能是運氣"                                  # VER 9：● 的意思
    assert X.KINDS == ("event", "state") and X.EP_GAP == 20
    assert (X.HOT, X.COLD, X.HOT_WEEKS, X.EXIT_MIN) == (80, 20, 13, 4)
    assert X.VARIANTS == ("hot", "hot13", "hot_in", "hot_out", "cold", "cold_in")
    assert X.VARIANT_KIND == {"hot": "state", "hot13": "state", "hot_in": "event", "hot_out": "event",
                              "cold": "state", "cold_in": "event"}
    assert set(X.VARIANT_NAMES) == set(X.VARIANTS)
    assert X.H_DIM == {"tech": 20, "chip": 60, "sent": 60, "gliq": 60, "tliq": 60, "liq": 60, "fund": 250}
    assert (X.MULTI_K, X.MULTI_MIN_DIMS, X.H_MULTI) == (2, 3, 60)
    assert (X.H_TECH, X.EV_START) == (20, 250)
    assert X.DERIV_STATES == (1, 2, 3, 4) and X.H_DERIV == 60
    assert X.CRASH_VARS == {"tw": ("W1", "W2", "W3", "W4"), "spx": ("VOL",), "ixic": ("VOL",), "ndx": (), "sox": ()}
    assert X.H_CRASH == 60
    assert X.BUB_SIGNALS == ("L2", "L3", "P1", "P2", "P3", "E", "G", "F", "V") and set(X.BUB_NAMES) == set(X.BUB_SIGNALS)
    assert X.IND_GROUPS == ("ff", "us", "tw") and X.IND_SIGNALS == ("L2", "L3")
    assert (X.H_BUB, X.H_IND_M) == (250, 12)
    assert X.H_STOCK == 20 and X.STOCK_WARN == ("exit",) and X.STOCK_MDD == 0.10   # VER 3：集體撤退看 20 日最大回撤
    assert X.STRAT_N_MIN == 10 and X.STRAT_FEW == 30                      # VER 2：次數不夠沒關係（使用者 2026-10-19）；VER 9 不動
    assert X.STRAT_CAP == {"good": 0.05, "ref": 0.02, "none": 0.0, "few": 0.0}
    assert X.TODAY_MAX == 8 and not hasattr(X, "TODAY_REF")          # VER 9：沒有 ★ 就寫沒有
    # 景氣頁「今天的重點」2026-10-20 起：只改呈現、不改判定（VER 不變）
    assert X.TODAY_SIDE == 6 and X.THERMO_LEAN == 0.6
    # VER 12（使用者 2026-10-21：「溫度計可以標準寬鬆一些」，選「有傾向就算」）：★ 2、● 1、△ 0.5；△＝比平常高 5 個百分點以上
    # VER 17（使用者選「溫度計照新的 ★ 算」）：★ 2、◆ 1、△ 0.5；△＝勝率門檻過了但沒過完整的判定（THERMO_EDGE 只留給 VER 12～16 的紀錄）
    # VER 23：列出來與溫度計改回「比平常高 THERMO_EDGE 以上」（第 5 節 ④b）
    assert X.THERMO_W == {"good": 2, "rare": 1, "lean": 0.5} and X.THERMO_EDGE == 0.05 == X.EDGE_REF
    assert X.THERMO_MARK == {"good": "★", "rare": "◆", "lean": "△"} and set(X.THERMO_NAMES) == set(X.THERMO_W)
    assert X.RES_VER == 24                                          # VER 17 改了判定與報酬欄位、VER 20 改了分段、VER 22 狀態型的權重、VER 24 報酬格多最大跌幅，研究檔要重跑
    assert [k for k, *_ in X.THERMO_HZ] == ["short", "mid", "long"]


def test_sig_spec_v4_scenarios_are_locked():
    """VER 4（2026-10-20）：情境＝事前定義的面向組合（docs/lab_heatviz_v2_plan.md 第 11 節）。"""
    assert (X.H_SCEN, X.SCEN_HI, X.SCEN_LO, X.SCEN_MIN_DIMS, X.SCEN_MANY) == (60, 60, 40, 3, 3)
    assert X.SCEN_DIMS == ("fund", "chip", "liq", "tech") and set(X.SCEN_DIM_NAMES) == set(X.SCEN_DIMS)
    assert X.SCEN_SRC == {"tw": {"fund": ("fund",), "chip": ("chip",), "liq": ("gliq", "tliq"), "tech": ("tech",)},
                          "us": {"fund": ("fund",), "chip": ("sent",), "liq": ("liq",), "tech": ("tech",)}}
    conds = {k: c for k, _, c, _ in X.SCENARIOS}
    assert conds == {
        "SC1": (("fund", "hi"), ("tech", "hi")), "SC2": (("fund", "hi"), ("tech", "lo")),
        "SC3": (("fund", "lo"), ("tech", "hi")), "SC4": (("fund", "lo"), ("tech", "lo")),
        "SC5": (("chip", "hi"), ("tech", "lo")), "SC6": (("liq", "hi"), ("tech", "lo")),
        "SC7": (("liq", "lo"), ("chip", "hi")), "SC8": "many_hi", "SC9": "many_lo"}
    assert [n for _, n, _, _ in X.SCENARIOS] == ["景氣好、價格強", "景氣好、價格回檔", "景氣差、價格反彈", "景氣差、價格弱",
                                                 "籌碼熱、價格轉弱", "資金寬鬆、價格弱", "資金緊、籌碼熱", "多數面向偏熱", "多數面向偏冷"]
    for _, _, c, _ in X.SCENARIOS:                       # 條件只用四個共通面向
        assert c in ("many_hi", "many_lo") or all(d in X.SCEN_DIMS and o in ("hi", "lo") for d, o in c)
    # 對照的面向都是景氣頁顯示的面向
    assert {d for v in X.SCEN_SRC["tw"].values() for d in v} == set(HS.DIMS) - {"bubl"}
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            assert {d for v in X.SCEN_SRC["us"].values() for d in v} == set(HS.DIMS) - {"bubl"}


def test_sig_spec_v5_returns_and_similar_days_are_locked():
    """VER 5（2026-10-20）：訊號觸發後的報酬與相似的日子（docs/lab_outlook_plan.md）；只呈現，判定不變。"""
    assert X.RET_H == (1, 5, 10, 20, 60, 120, 250)                     # 使用者選「更細」
    assert X.RET_H_M == (1, 3, 6, 12) and X.PATH_D == (1, 5, 10, 20, 40, 60, 90, 120, 180, 250)
    assert X.RET_Q == (0.25, 0.5, 0.75) and X.MAE_Q == 0.10 and X.RET_N_MIN == 10
    assert X.NB_DIMS == ("fund", "liq", "tech") and X.NB_DIMS_X == ("fund", "chip", "liq", "tech")
    assert set(X.NB_DIMS_X) == set(X.SCEN_DIMS) and set(X.NB_DIMS) < set(X.NB_DIMS_X)
    assert (X.NB_H_X, X.NB_K, X.NB_GAP, X.NB_FAR, X.NB_LIST_H, X.NB_LIST_EXTRA) == ((60,), 20, 60, 15, 60, (20, 60, 250))
    assert set(X.NB_H_X) <= set(X.RET_H) and X.NB_LIST_H in X.RET_H and set(X.NB_LIST_EXTRA) <= set(X.RET_H)
    assert X.NB_OOS_START == {"tw": "2015-01-01", "spx": "1990-01-01", "ixic": "1990-01-01", "ndx": "2000-01-01",
                              "sox": "2005-01-01"} and set(X.NB_OOS_START) == set(X.MARKETS)
    assert (X.NB_BOOT, X.NB_BLOCK, X.NB_SEED, X.NB_OOS_MIN, X.NB_HI, X.NB_BINS) == (2000, 12, 20261020, 36, 0.70, (0.5, 0.6, 0.7))
    assert set(X.PATH_D) >= set(X.RET_H)


def test_sig_spec_v6_institutional_flows_are_locked():
    """VER 6（2026-10-20）：法人買賣超（docs/lab_inst_plan.md）；VER 7 同日法人只當訊號（heatspec VER 9 拿掉 C9～C14）。"""
    assert X.INST_WHO == ("tot", "fi", "it", "dl") and set(X.INST_NAMES) == set(X.INST_WHO)
    assert X.INST_WIN == (1, 5, 20, 60) and X.INST_POS_WIN == (5, 20, 60)
    assert not hasattr(X, "INST_HEAT")                                  # VER 7：法人不算進任何面向
    assert X.INST_SKIP == {("fi", 60): "L3"}
    assert X.INST_VARIANTS == ("hot", "hot_in", "hot_out", "cold", "cold_in", "cold_out")
    assert set(X.INST_VARIANT_NAMES) == set(X.INST_VARIANTS) and X.INST_VARIANT_NAMES["hot"] == "大賣超中"
    assert X.INST_DAY == (95, 5) and X.INST_RUN == (5, 10) and X.INST_H == {1: 20, 5: 20, 20: 60, 60: 60, "run": 20}
    assert not [k for k in HS.KEYS if k in ("C9", "C10", "C11", "C12", "C13", "C14")]
    assert HS.DIM_OF["L3"] == "tliq" and HS.HOT["L3"] == 1


def test_sig_spec_v9_luck_test_and_families_are_locked():
    """VER 9（2026-10-20）：打亂日子測試 1%（使用者選定）、次數下限 5、同類合併（VER 8 寫定）照用；VER 8 的打折沒有上線
    （docs/lab_noise_plan.md 第 10 節）。門檻與近 10 年規則照 VER 7。"""
    assert X.LUCK_P == 0.01 and (X.LUCK_DRAWS, X.LUCK_SEED, X.LUCK_SHIFT) == (400, 20261021, (0.15, 0.85))
    assert X.HIT_MIN == {"up": 0.60, "warn": 0.50, "buy": 0.60} and X.EDGE_GOOD == 0.10 and X.N_MIN == 5
    assert (X.RECENT_YEARS, X.RECENT_N) == (10, 5)
    assert not any(hasattr(X, k) for k in ("K_GOOD", "K_REF", "NOISE_DRAWS", "NOISE_SEED", "NOISE_SHIFT"))
    assert not hasattr(X, "FAMILY_J") and (X.FAMILY_O, X.FAMILY_X) == (0.50, 2.0)   # VER 11：合併改看比較少出現的那個
    # p 的解析度：1% 要能被 LUCK_DRAWS 次平移分辨（至少要有 3 次以上「做得到」的空間）
    assert (1 + 3) / (1 + X.LUCK_DRAWS) <= X.LUCK_P


def test_sig_spec_v14_rare_signals_threshold_is_locked():
    """VER 14（2026-10-22，使用者選「次數少於 15 次放寬到 10%」，docs/lab_noise_plan.md 第 13 節）：只改 ★ 的打亂測試門檻，
    命中率門檻、近 10 年、次數下限都不變。"""
    assert (X.LUCK_FEW_N, X.LUCK_P_FEW, X.LUCK_P) == (15, 0.10, 0.01)
    assert [X.luck_p(n) for n in (None, 0, 5, 14, 15, 16, 400)] == [0.10, 0.10, 0.10, 0.10, 0.01, 0.01, 0.01]
    assert X.N_MIN < X.LUCK_FEW_N and X.HIT_MIN == {"up": 0.60, "warn": 0.50, "buy": 0.60} and X.EDGE_GOOD == 0.10


def test_sig_spec_v15_thermometer_all_horizons_is_locked():
    """VER 15（2026-10-22，使用者選「三個看多久都算」、台股一起改，docs/lab_noise_plan.md 第 14 節）：只改溫度計——
    市場層級訊號在另外兩支溫度計也投票，只算 △；判定、兩欄、訊號總覽、研究檔原本的欄位都不變（RES_VER 不改）。"""
    assert X.THERMO_H == {"short": 20, "mid": 60, "long": 250} and list(X.THERMO_H) == [k for k, *_ in X.THERMO_HZ]
    assert X.THERMO_H["short"] == X.H_TECH and X.THERMO_H["mid"] == X.H_CRASH == X.H_DERIV == X.H_SCEN and X.THERMO_H["long"] == X.H_BUB
    assert X.THERMO_X_CATS == ("heat", "crash", "multi", "scen", "inst", "tech", "deriv", "bub")
    assert "buy" not in X.THERMO_X_CATS and "ind" not in X.THERMO_X_CATS            # 大跌後買點、產業泡沫不跨期間
    assert X.THERMO_W["lean"] == 0.5 and X.N_MIN == 5 and X.RES_VER == 24              # VER 17 起跨期間的票＝勝率門檻過了


def test_sig_spec_v16_thermometer_calibration_is_locked():
    """VER 16（2026-10-22，docs/lab_noise_plan.md 第 14.10 節）：溫度計下面加「過去讀數這樣的時候」——逐年滾動（不偷看之後）的票數、
    和自己的過去 10 年比的位置、過去同一組的週之後怎麼走；只是描述，判定與溫度計的算法都不變。"""
    assert X.CAL_VER == 23 and (X.CAL_WARM_Y, X.CAL_MIN_SAMP) == (10, 50)              # VER 17 投票規則、VER 20 分段與事件失效、VER 21 票的規則、VER 22 權重、VER 23 票改回比平常高 5 點，研究檔重跑
    assert (X.CAL_RANK_W, X.CAL_RANK_MIN, X.CAL_TERC) == (520, 260, (1 / 3, 2 / 3))
    assert (X.CAL_BLOCK, X.CAL_DRAWS, X.CAL_SEED, X.CAL_MIN_WEEKS) == (52, 1000, 20261022, 104)
    assert X.N_MIN == 5 and X.RES_VER == 24                                          # 投票規則同 △（VER 17：勝率門檻過了）


def test_sig_spec_v17_absolute_judgment_is_locked():
    """VER 17（2026-10-22，docs/lab_practical_plan.md）：使用者選「絕對成績好就算 ★」「至少不比隨便哪天差」、次數少的另開「難得機會」、
    報酬以中位數為主另列排除極端與去掉最好一次、溫度計照新的 ★ 算；套用到警示、大跌後買點、總經策略落底型（xstratspec VER 6）。"""
    from arm.lab import xstratspec as XS
    assert X.STAR_N == 15 and X.N_MIN == 5 and X.HIT_MIN == {"up": 0.60, "warn": 0.50, "buy": 0.60}
    assert X.TIER_MARK["rare"] == "◆" and X.TIER_NAMES["rare"] == "難得機會" and X.TIER_NAMES["good"] == "好訊號"
    assert {mk: X.ABS_COST[mk] for mk in XS.COST} == XS.COST and X.ABS_COST["us"] == XS.COST["spx"]   # 成本同總經策略
    assert (X.TRIM_Q, X.TRIM_N) == (0.05, 20) == (XS.DIP_TRIM_Q, XS.DIP_TRIM_N)
    assert XS.VER == 6 and XS.DIP_WIN == 0.60 and XS.DIP_N_MIN == 5
    assert X.RES_VER == 24 and X.CAL_VER >= 22 and X.VER >= 17    # VER 20 分段改了、VER 21 溫度計的票改了、VER 22 狀態型的權重，研究檔重跑（VER 23 只重跑溫度計校正、VER 24 多最大跌幅）
    assert X.THERMO_W == {"good": 2, "rare": 1, "lean": 0.5} and X.THERMO_NAMES["lean"] == "勝率過了"


def test_sig_spec_v18_forward_estimate_is_locked():
    """VER 18（2026-10-22，docs/lab_practical_plan.md 第 10 節）：「預估之後」＝逐年樣本外的衰退表（方向 × 看多久 × 次數 × 過去的優勢），
    預估之後的命中率＝平常 ＋ k ×（命中率 − 平常）、多賺＝k_r ×（報酬中位數 − 平常的報酬中位數），k 截在 0～1；只呈現，判定與研究檔不變。"""
    assert X.VER >= 19 and X.FWD_VER == 22 and X.RES_VER >= 22 and X.CAL_VER >= 22   # VER 18～19 只動 sigoos；VER 20 分段改了，三個都重跑；VER 21 多跨期間；VER 22 權重；VER 24 只動 sig_research
    # VER 19：報酬留下來的比例改用平均量（次數少時中位數的期望值比全部日子的中位數低，VER 18 的之後多賺系統性偏低）
    assert X.FWD_NB == (15, 40) and X.FWD_NB[0] == X.STAR_N                         # 5～14（難得機會）、15～39、40 以上
    assert X.FWD_EB == (0.0, 0.05, 0.10, 0.20)
    assert (X.FWD_MIN_N, X.FWD_MIN_CL, X.FWD_EPS, X.FWD_EPS_R) == (100, 30, 0.01, 0.001)
    assert (X.FWD_DRAWS, X.FWD_SEED, X.FWD_SPLIT, X.FWD_OWN_MIN) == (1000, 20261023, 2010, 5)
    assert (X.CAL_WARM_Y, X.CAL_MIN_SAMP, X.N_MIN, X.RECENT_YEARS) == (10, 50, 5, 10)   # 逐年滾動、訓練樣本日下限同 thermocal
    assert X.H_BUY == 60



def test_sig_spec_v20_audit_is_locked():
    """VER 20（2026-10-22，docs/lab_audit_plan.md；資料與訊號盤查，使用者選「最新的取代舊的」）：①狀態型的一段，中斷的日子裡到過相反的極端
    就切開；②事件出現之後同一個項目出現相反的讀數就不算現在有效（成績不變）；③資料過期的項目不算現在有效（heatspec VER 10、heatspec_us VER 2）。"""
    assert X.EP_GAP == 20 and X.EP_BREAK == {"hot": "lt_cold", "hot13": "lt_cold", "cold": "ge_hot"}
    assert X.EP_BREAK_CATS == ("heat", "crash", "inst")
    assert set(X.EP_BREAK) <= set(X.VARIANTS) and set(X.EP_BREAK) <= set(X.VARIANTS) | set(X.INST_VARIANTS)
    assert X.EXPIRE_ON == {"hot_in": ("lt_cold", "hot_out"), "cold_in": ("ge_hot", "cold_out"), "hot_out": ("ge_hot",),
                           "cold_out": ("lt_cold",)}
    assert set(X.EXPIRE_ON) <= set(X.VARIANTS) | set(X.INST_VARIANTS)
    for v in X.EXPIRE_ON.values():
        assert all(c in ("lt_cold", "ge_hot") or c in X.VARIANTS + X.INST_VARIANTS for c in v)
    pairs = [k for p in X.TECH_PAIRS for k in p]
    assert len(X.TECH_PAIRS) == 8 and sorted(pairs) == sorted(HS.EVENTS) and len(set(pairs)) == 16   # 16 種技術事件兩兩成對
    assert X.INST_SIDE == {"day_sell": "s", "sell_run5": "s", "sell_run10": "s", "day_buy": "b", "buy_run5": "b", "buy_run10": "b"}
    assert X.INST_RUN == (5, 10)
    assert X.RES_VER >= 20 and X.FWD_VER >= 20 and X.CAL_VER >= 20
    assert HS.VER == 10 and HS.SPEC_DATE == "2026-10-22" and (HS.GAP_FILL_MAX, HS.STALE_M) == (2, 2)
    # 美股 VER 2 是補缺月、資料過期；VER 3（2026-10-29）只換情緒籌碼項目，補缺月與過期規則沿用
    assert U.VER >= 2 and (U.GAP_FILL_MAX, U.STALE_M) == (HS.GAP_FILL_MAX, HS.STALE_M)


def test_sig_spec_v21_listing_is_locked():
    """VER 21（2026-10-22，docs/lab_audit_plan.md 第 11 節；使用者選 Q1「只加 1 個月」、Q3「只留預估之後仍差 3 點以上的」）：
    今天的重點、溫度計、訊號總覽的今天清單＝現在有效、預估之後和隨便挑一天差 3 點以上；偏弱只看 1 個月；跨期間另一套逐年格子；
    「過去讀數這樣的時候」的票只用那時已經走完的紀錄算留下來的比例。判定與 sig_research.json 不變。"""
    assert X.LIST_GAP == 0.03 and X.WEAK_H == X.H_TECH == 20
    assert X.LIST_CLS == ("up", "buy", "weak", "risk") and set(X.LIST_CLS_NAMES) == set(X.LIST_SIDE) == set(X.LIST_CLS)
    assert X.LIST_SIDE == {"up": "up", "buy": "up", "weak": "warn", "risk": "warn"}
    assert X.LIST_CLS_NAMES == {"up": "偏多", "buy": "買點", "weak": "偏弱", "risk": "大跌風險"}
    assert X.TODAY_PER_HZ == 4 and X.FWD_XP == "x:"
    assert X.CAL_K_LAG == {20: 2, 60: 2, 250: 3} and set(X.CAL_K_LAG) == set(X.THERMO_H.values())
    assert X.H_BUY in X.CAL_K_LAG                                        # 大跌後買點的格子（看 60 天）也查得到
    assert X.FWD_VER >= 21 and X.CAL_VER >= 21 and X.RES_VER >= 20 and X.VER >= 21
    # 格子、門檻與往上找的規則沿用第 4.14 節 ③（VER 18）
    assert (X.FWD_MIN_N, X.FWD_MIN_CL, X.FWD_EPS) == (100, 30, 0.01) and X.FWD_EB[0] == 0.0

def test_sig_spec_refers_to_existing_definitions():
    """規格引用的其他規格都還在、意思沒變。"""
    for mk in X.MARKETS:
        assert len(CS.TH[mk]) == 3                        # (A1 單日, A2 20 日, A3 60 日)
    assert CS.TH["tw"][X.WARN_TH_IDX[20]] == 0.08 and CS.TH["tw"][X.WARN_TH_IDX[60]] == 0.10
    assert len(HS.EVENTS) == 16
    assert set(HS.EVT) >= {"hot", "cold"} and HS.EVT["hot"][0] == X.HOT and HS.EVT["cold"][0] == X.COLD
    dims_tw = set(HS.DIMS) - {"bubl"}
    assert dims_tw <= set(X.H_DIM)
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            assert set(HS.DIMS) - {"bubl"} <= set(X.H_DIM)
            assert len(HS.DERIV) >= 1
    assert BS.VER == 4 and BS.LP_CUT == 1 / 3 and BS.SIG_BASE == "W10"         # VER 13：bottomspec VER 4（多 C9、美股 C3、C8）
    assert set(X.STOCK_WARN) <= set(AN.SIG_DEF) and len(AN.SIG_DEF) == 8
    assert BT.DEDUP == 5
    assert bt3.PAY == {"win": 60.0, "m": 1.0, "win2": 40.0, "ratio": 2.5, "m2": 2.0}


def test_sig_spec_v22_state_days_weighted_is_locked():
    """VER 22（docs/lab_audit_plan.md 第 12 節）：狀態型的命中率與報酬改成每一天一樣重（每一段一樣重有長短偏誤）；
    次數仍是段數、分段規則不變；三個研究檔都重跑。"""
    from arm.lab import sigspec as X
    assert X.VER >= 22 and X.STATE_W == "day" and X.RES_VER >= 22 and X.FWD_VER == 22 and X.CAL_VER >= 22
    assert X.EP_GAP == 20 and X.EP_BREAK == {"hot": "lt_cold", "hot13": "lt_cold", "cold": "ge_hot"}
    assert (X.TRIM_Q, X.TRIM_N) == (0.05, 20) and X.LIST_GAP == 0.03 and X.N_MIN == 5 and X.STAR_N == 15


def test_sig_spec_v23_loose_thermometer_is_locked():
    """VER 23（docs/lab_audit_plan.md 第 13 節）：使用者看過 VER 21～22 之後的景氣頁——「溫度計什麼屁都沒有了」。今天的重點、溫度計、
    訊號總覽的今天清單改回 VER 12 的「次數 ≥ 5、過去比隨便挑一天高 5 點以上就算」（每一天一樣重的數字），拿掉偏弱（VER 22 逐年檢查是反過來的），
    預估之後只用來標「之後也成立」；「過去讀數這樣的時候」的票同一條（CAL_VER 23 重跑）；sig_research、sigoos_research 不動。"""
    assert X.VER >= 23 and X.CAL_VER == 23 and X.RES_VER >= 22 and X.FWD_VER == 22 and X.STATE_W == "day"
    assert X.THERMO_EDGE == 0.05 and X.N_MIN == 5 and X.LIST_GAP == 0.03 and X.STAR_N == 15
    assert X.THERMO_CLS == ("up", "buy", "risk") and "weak" not in X.THERMO_CLS
    assert set(X.THERMO_CLS) <= set(X.LIST_CLS_NAMES) and {X.LIST_SIDE[c] for c in X.THERMO_CLS} == {"up", "warn"}
    assert X.TODAY_PER_SIDE == 3 and X.THERMO_LEAN == 0.6 and [k for k, *_ in X.THERMO_HZ] == ["short", "mid", "long"]


def test_sig_spec_v24_worst_drawdown_is_locked():
    """VER 24（2026-10-28，docs/lab_audit_plan.md 第 14 節）：使用者：「中途最多跌％才1.8%但又說遇到大跌8%機率23%……
    我要看到訊號出現後的最大跌幅就是最大跌幅不要幫偽用中位數」。只改呈現：跌幅一律列最差一次（附日期），算法和大跌同一個
    （期間最高收盤到之後最低收盤）；判定、門檻、次數、看多久、溫度計、預估之後不變；sig_research.json 重跑（RES_VER＝24），
    sigoos_research.json、thermo_research.json 不動。"""
    assert X.VER == 24 and X.RES_VER == 24 and X.FWD_VER == 22 and X.CAL_VER == 23
    assert X.WARN_TH_IDX == {20: 1, 60: 2} and X.WARN_LONG == 0.20 and X.LAG == 1     # 大跌的算法與門檻沒動
    assert X.HIT_MIN == {"up": 0.60, "warn": 0.50, "buy": 0.60} and X.STAR_N == 15 and X.N_MIN == 5
    assert X.THERMO_EDGE == 0.05 and X.THERMO_CLS == ("up", "buy", "risk")
