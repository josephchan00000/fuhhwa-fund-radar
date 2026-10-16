"""《超級績效》技術線型（arm/lab/sepa.py）與第二層篩選定義（arm/lab/layer.py）：純 Python 核心。"""
from arm.lab import layer as LY
from arm.lab import sepa as SP


def test_rolling_mean_needs_full_window():
    assert SP.rolling_mean([1, 2, 3, 4, None, 6], 3) == [None, None, 2.0, 3.0, None, None]


def test_ma200_info_up_streak():
    c = [100 + 0.1 * t for t in range(260)]
    ma, prev, up = SP.ma200_info(c)
    assert ma[198] is None and ma[199] is not None
    assert prev[219] == ma[199] and prev[218] is None
    assert up[199] == 0 and up[200] == 1 and up[259] == 60


def test_rsl_new_high_and_lead():
    idx = [100.0] * 260
    c = [10.0] * 250 + [11.0] * 10                   # 漲上去 → RS 線、股價都創新高
    assert SP.rsl_at(c, idx, 255) == (True, False)
    idx2 = [100.0] * 250 + [80.0] * 10               # 大盤跌 20%、股價只跌 10% → RS 線創新高、股價沒有
    c2 = [10.0] * 250 + [9.0] * 10
    assert SP.rsl_at(c2, idx2, 255) == (True, True)
    assert SP.rsl_at(c2[:150], idx2[:150], 149) == (False, False)   # 不到 200 日


def test_tight_at():
    h = [101.0] * 300
    l = [96.0] * 300
    c = [100.0] * 300
    assert SP.tight_at(h, l, c, 105.0, 299, 10, 0.08) == (101.0, 96.0)
    assert SP.tight_at(h, l, c, 120.0, 299, 10, 0.08) is None            # 離 52 週高點超過 15%
    l2 = [90.0] * 300
    assert SP.tight_at(h, l2, c, 105.0, 299, 10, 0.08) is None           # 幅度 12%


def _pp_series(dd: float):
    n = 120
    c = [10.0] * 60 + [10 + 12 * (k + 1) / 30 for k in range(30)] + [22.0 * (1 - dd)] * 15 + [21.5] * 15
    h = [x * 1.01 for x in c]
    l = [x * 0.99 for x in c]
    v = [1e6] * n
    v[70] = 3e6                                      # 起漲段有一天大量
    v50 = [SP.mean_last(v, t, 50, 40) for t in range(n)]
    return h, l, c, v, v50


def test_power_play():
    h, l, c, v, v50 = _pp_series(0.12)
    t = 104                                          # 高點（第 89 天）之後 15 天
    r = SP.pp_at(h, l, c, v, v50, 20.0, 0.5, t)
    assert r is not None and abs(r[0] - 22.0 * 1.01) < 1e-9
    assert SP.pp_at(h, l, c, v, v50, 20.0, 0.9, t) is None               # 回檔 > 10% 卻沒量縮
    h2, l2, c2, v2, v502 = _pp_series(0.30)
    assert SP.pp_at(h2, l2, c2, v2, v502, 20.0, 0.5, t) is None           # 回檔 30%
    assert SP.pp_at(h, l, c, v, v50, 20.0, 0.5, 92) is None               # 高點後不到 10 天


def test_base_counts():
    up = [100 * 1.004 ** t for t in range(320)]
    pull = [up[-1] * (1 - 0.15 * min(k, 10) / 10) for k in range(1, 21)]
    rec = [up[-1] * 1.01 * 1.003 ** k for k in range(30)]
    c = up + pull + rec
    ma, prev, _ = SP.ma200_info(c)
    b = SP.base_counts(c, ma, prev)
    assert b[100] == 0 and b[230] == 1
    assert b[330] == 1                               # 回檔中仍是第 1 個基底
    assert b[-1] == 2                                # 回檔 15%、20 日後再創新高 → 第 2 個基底


def test_track_breakout_post_fail_extended():
    tr = SP.Track()
    ready = (100.0, 95.0, "tight")
    assert tr.step(0, 99.0, 1e6, 1e6, 90.0, True, ready)[0] == 3                 # 準備好
    st, piv, low, kind = tr.step(1, 102.0, 2e6, 1e6, 90.0, True, None)           # 帶量突破
    assert (st, piv, low, kind) == (1, 100.0, 95.0, "tight")
    assert tr.step(2, 103.0, 1e6, 1e6, 90.0, True, None)[0] == 2                 # 突破後仍在買點
    assert tr.step(3, 96.0, 1e6, 1e6, 90.0, True, None)[0] == 4                  # 跌回樞紐 × 0.97 以下
    assert tr.step(4, 101.0, 1e6, 1e6, 90.0, True, None)[0] == 0                 # 失敗後不再算買點
    tr2 = SP.Track()
    tr2.step(0, 99.0, 1e6, 1e6, 90.0, True, ready)
    assert tr2.step(1, 102.0, 1.2e6, 1e6, 90.0, True, None)[0] == 0              # 量不夠 → 不算突破
    assert SP.Track().step(0, 130.0, 1e6, 1e6, 100.0, True, None)[0] == 5         # 離 50 日線 30%
    assert SP.Track().step(0, 100.0, 1e6, 1e6, 100.0, False, None)[0] == -1       # 不在名單


def test_ready_at_order_and_dry():
    vcp, tg, pp = (100.0, 92.0), (101.0, 95.0), (104.0, 90.0)
    assert SP.ready_at(True, True, 99.0, 0.5, vcp, tg, pp)[2] == "vcp"
    assert SP.ready_at(True, True, 99.0, 0.9, None, tg, pp)[2] == "pp"           # 緊密整理要量縮
    assert SP.ready_at(False, True, 99.0, 0.5, vcp, tg, pp)[2] == "pp"           # 不在名單：只看爆發型
    assert SP.ready_at(True, True, 90.0, 0.5, vcp, tg, None) is None             # 離樞紐超過 5%
    assert SP.stop_px(100.0, 95.0) == 95.0 and SP.stop_px(100.0, 85.0) == 92.0


def test_ud_at():
    c = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0]
    v = [1.0, 3.0, 1.0, 3.0, 1.0, 3.0]
    assert SP.ud_at(c, v, 5, n=5) == 9.0 / 2.0
    assert SP.ud_at(c, v, 3, n=5) is None


def test_layer_families_and_score():
    cond = {k: False for k in LY.CKEYS}
    assert LY.score(cond) == 0
    cond.update({"rnha": True, "ey25": True, "rsl": True, "tight": True, "base12": True, "ind2": True})
    assert LY.families(cond) == [True, False, True, True, False, False, True]   # 獲利要 EPS 加速、階段要 200 日線
    cond.update({"eacc": True, "ma200up": True, "ud12": True})
    assert LY.score(cond) == 7
    assert len(LY.FAMILY) == 7 and len(LY.CKEYS) == 28 and set(LY.LIST_ONLY) <= set(LY.CKEYS)


def test_layer_top_set_and_cap():
    vals = {"a": 1.0, "b": 5.0, "c": 3.0, "d": None, "e": 4.0}
    assert LY.top_set(vals, 0.2) == {"b"}
    assert LY.top_set(vals, 0.5) == {"b", "e"}
    assert LY.cap_bucket(50e8) == {"cap_s": True, "cap_m": False, "cap_l": False}
    assert LY.cap_bucket(None) == {"cap_s": False, "cap_m": False, "cap_l": False}


def _breakout_series():
    """280 日從 50 漲到 100、12 日緊密整理（98～100，量縮）、帶量突破到 103，之後 30 日慢慢漲到 112。"""
    up = [50 + 50 * t / 279 for t in range(280)]
    base = [(100.0, 98.0, 99.0)[k % 3] for k in range(12)]
    post = [103 + 0.3 * k for k in range(31)]
    c = up + base + post
    v = [1e6] * 280 + [4e5] * 12 + [2e6] + [1e6] * 30
    return c, v, 280 + 12                                            # 突破日


def test_plan_today_breakout_and_memory():
    c, v, b = _breakout_series()
    r = SP.plan_today(c, c, c, v, c, b - 1)
    assert r["st"] == 3 and r["kind"] == "tight" and r["piv"] == 100.0  # 突破前一天：準備好
    r = SP.plan_today(c, c, c, v, c, b)
    assert (r["st"], r["piv"], r["stop"], r["kind"]) == (1, 100.0, 98.0, "tight")
    assert SP.plan_today(c, c, c, v, c, b + 3)["st"] == 2            # 突破後仍在買點
    assert SP.plan_today(c, c, c, v, c, b + 30)["st"] == 5           # 一個月前突破、已漲過樞紐 5%：漲太遠
    assert SP.plan_today(c, c, c, v, c, b + 30, look=20)["st"] == 0  # 看得太短會忘記那次突破（所以預設 65 日）


def test_layer_market_now():
    up = [100 + t for t in range(260)]
    r = LY.market_now(up, 259, [f"d{t}" for t in range(260)])
    assert r["m2"] is True and r["d"] == "d259" and r["ma50"] > r["ma200"]
    down = [400.0 - t for t in range(260)]
    down[100] = None                                                  # 缺值用前一天補
    assert LY.market_now(down, 259, [str(t) for t in range(260)])["m2"] is False
    assert LY.market_now(up[:150], 149, [str(t) for t in range(150)]) == {}


def test_layer_page_data_bits():
    x = [False] * len(LY.CKEYS)
    x[LY.CKEYS.index("rs90")] = x[LY.CKEYS.index("vcp")] = True
    fam = [True, False, True, False, False, False, True]
    lay = {"st": {"1111": {"s": 3, "fam": fam, "x": x, "base": 2, "plan": {"st": 3, "piv": 10.0, "stop": 9.2}}},
           "mnow": {"m2": True}}
    d = LY.page_data(None, lay)
    s = d["stocks"]["1111"]
    assert s["f"] == 1 + 4 + 64 and s["s"] == 3 and s["b"] == 2 and s["p"]["piv"] == 10.0
    assert s["x"] == (1 << LY.CKEYS.index("rs90")) | (1 << LY.CKEYS.index("vcp"))
    assert d["mnow"] == {"m2": True} and "specs" not in d and len(d["ck"]) == 28 and len(d["fam"]) == 7
