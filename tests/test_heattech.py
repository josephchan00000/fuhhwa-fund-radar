"""景氣溫度頁技術面事件（arm/lab/heattech.py；規劃文件第 13.3、13.8 節）：轉折點、事件、不偷看未來、事件研究、價位。"""
import random

from arm.lab import heattech as T
from arm.lab import heatspec as S


def _path(*legs):
    """[(起, 迄, 天數), ...] → 每段線性走勢的收盤序列（段與段首尾相接）。"""
    out = []
    for a, b, n in legs:
        step = (b - a) / n
        out += [a + step * k for k in range(n)]
    out.append(legs[-1][1])
    return out


def test_pivots_confirm_after_five_percent_and_alternate():
    px = _path((100, 120, 20), (120, 108, 12), (108, 130, 22), (130, 117, 13), (117, 125, 8))
    pv = T.pivots(px)
    assert [x["k"] for x in pv] == ["L", "H", "L", "H", "L"]
    h1 = pv[1]
    assert h1["p"] == 120 and px[h1["c"]] <= 120 * 0.95 and all(p > 120 * 0.95 for p in px[h1["i"]:h1["c"]])
    lo = pv[2]
    assert abs(lo["p"] - 108) < 1e-9 and px[lo["c"]] >= 108 * 1.05
    assert all(pv[k]["c"] < pv[k + 1]["c"] for k in range(len(pv) - 1))


def test_state_events_need_ten_days_before_and_three_days_after():
    sd = [1] * 12 + [-1] * 3 + [-1] * 5
    dn, up = T.state_events(sd)
    assert dn == [14] and up == []                          # 第 3 天（索引 14）
    sd = [1] * 12 + [-1, -1, 1, 1] + [-1] * 3              # 只跌破 2 天就站回 → 不算；之後前 10 天不全在上方 → 也不算
    assert T.state_events(sd) == ([], [])
    sd = [-1] * 10 + [1] * 3
    assert T.state_events(sd) == ([], [12])


def test_break_events_once_per_pivot():
    px = _path((100, 110, 10), (110, 90, 10), (90, 120, 15), (120, 100, 10), (100, 80, 10), (80, 85, 5))
    pv = T.pivots(px)
    dn, up = T.break_events(px, pv)
    assert [x["p"] for x in pv] == [100, 110, 90, 120, 80]            # 起點 100 漲 5% 就確認是低點
    assert len(up) == 1 and px[up[0]] > 110 >= px[up[0] - 1]          # 突破 110 的前波高點（120 之後沒再突破）
    assert len(dn) == 2                                                # 跌破 100、跌破 90 各一次
    assert px[dn[0]] < 100 <= px[dn[0] - 1] and px[dn[1]] < 90 <= px[dn[1] - 1]
    assert next(x for x in pv if x["p"] == 90)["c"] < dn[1]            # 低點確認後才算跌破


def test_double_top_and_head_shoulders_need_neckline_break():
    # M 頭：100 → 90 → 100.5，兩高相隔 ≥ 22 天，之後跌破 90
    px = _path((80, 100, 15), (100, 90, 12), (90, 100.5, 12), (100.5, 85, 15))
    dn, up = T.double_events(px, T.pivots(px))
    assert len(dn) == 1 and px[dn[0]] < 90 and up == []
    # 兩高相隔太近 → 不算
    px2 = _path((80, 100, 15), (100, 90, 5), (90, 100.5, 5), (100.5, 85, 15))
    assert T.double_events(px2, T.pivots(px2)) == ([], [])
    # 頭肩頂：左肩 100、腋下 90、頭 110、腋下 91、右肩 101，跌破頸線
    px3 = _path((80, 100, 15), (100, 90, 10), (90, 110, 12), (110, 91, 12), (91, 101, 10), (101, 80, 15))
    dn, up = T.hs_events(px3, T.pivots(px3))
    pv = T.pivots(px3)
    assert len(dn) == 1 and up == []
    a1, a2 = [x for x in pv if x["k"] == "L" and x["p"] in (90, 91)][:2]
    neck = a1["p"] + (dn[0] - a1["i"]) * (a2["p"] - a1["p"]) / (a2["i"] - a1["i"])
    assert px3[dn[0]] < neck <= px3[dn[0] - 1] or px3[dn[0]] < neck
    # 頭不是最高 → 不算
    px4 = _path((80, 100, 15), (100, 90, 10), (90, 99, 12), (99, 91, 12), (91, 101, 10), (101, 80, 15))
    assert T.hs_events(px4, T.pivots(px4))[0] == []


def test_no_lookahead_events_match_truncated_series():
    rnd = random.Random(3)
    px, p = [], 10000.0
    for _ in range(1500):
        p *= 1 + rnd.gauss(0.0003, 0.013)
        px.append(p)
    full = T.all_events(px)
    assert set(full) == set(S.EVENTS)
    assert sum(len(v) for v in full.values()) > 50
    for cut in (400, 777, 1200):
        part = T.all_events(px[:cut + 1])
        for k in S.EVENTS:
            assert part[k] == [i for i in full[k] if i <= cut], (k, cut)


def test_event_study_compares_with_all_days():
    px = [100.0 * (1.001 ** i) for i in range(600)]          # 每天 +0.1%：所有日子之後 10 日都是 +1.0%
    idx = list(range(300, 560, 10))
    r = T.event_study(px, [f"d{i}" for i in range(600)], idx, 10)
    assert r["n"] == len(idx) and abs(r["avg"] - (1.001 ** 10 - 1)) < 1e-12
    assert abs(r["diff"]) < 1e-12 and r["up"] == 1.0
    assert r["verdict"] in ("none", "few")
    few = T.event_study(px, [f"d{i}" for i in range(600)], idx[:5], 10)
    assert few["verdict"] == "few"


def test_levels_deduct_support_resistance():
    px = _path((100, 140, 200), (140, 120, 60), (120, 130, 40))
    cal = [f"2020-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(len(px))]
    L = T.levels(px, cal)
    t = len(px) - 1
    assert [d["v"] for d in L["deduct"]] == [px[t - 60 + k] for k in range(1, S.DEDUCT_N + 1)]
    assert L["sup"]["v"] < px[t] < L["res"]["v"]
    assert L["ma"][60]["v"] is not None and L["ma"][240]["v"] is not None
    assert L["hi"]["p"] == 140
