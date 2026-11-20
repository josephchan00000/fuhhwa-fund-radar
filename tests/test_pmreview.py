"""盤前自我檢討（arm/lab/pmreview.py；規格 arm/lab/pmrevspec.py；docs/lab_premarket_plan.md 第 17 節）。"""
from datetime import datetime

from arm.lab import pmreview as R
from arm.lab import pmrevspec as S

PM = {"next": "2026-11-18", "est": 39716, "em": 1397, "est_src": "夜盤收盤", "made": "2026-11-18 06:07",
      "v": {"typ": 320, "p80": 644},
      "bands": [{"lo": 40000, "hi": 40100, "side": "up", "touch": 0.4}, {"lo": 39000, "hi": 39100, "side": "dn", "touch": 0.3},
                {"lo": 39700, "hi": 39750, "side": "at", "touch": 1.0}]}


def _log():
    return {"ver": S.VER, "fp": S.fingerprint(), "pub": {}, "rev": {}, "sum": {}}


def test_record_only_before_0845_of_that_day():
    log = _log()
    assert R.record(log, PM, datetime(2026, 11, 18, 6, 7))
    p = log["pub"]["2026-11-18"]
    assert p["est"] == 39716 and p["p80"] == 644 and p["bands"] == [[40000, 40100, 0.4], [39000, 39100, 0.3]]   # 預估在帶子裡那條不算
    assert not R.record(log, dict(PM, est=1), datetime(2026, 11, 18, 8, 45))                                    # 08:45 之後不改公布的那一版
    assert log["pub"]["2026-11-18"]["est"] == 39716


def test_one_day_review_and_reason():
    p = R.snap(PM)
    r = R.one(p, {"open": 40774, "hi": 41200, "lo": 39050}, {"est": 40969})
    assert r["err"] == 1058 and r["in"] is False and r["x"] == round(1058 / 1397, 3)
    assert r["seg"] == [1253, -195] and R.reason(r) == "夜盤收盤後到 08:45 台指期又漲 1,253 點"
    assert r["touch"] == [[0.4, True], [0.3, True]]
    assert R.reason(dict(r, seg=[206, -287])) == "08:45 到 09:01 又跌 287 點"
    assert R.reason({"err": 5}) == "沒有 08:46 重估，拆不出是哪一段"


def test_summary_warnings_shadow_and_push_line():
    log = _log()
    acts = {}
    for i in range(12):
        d = f"2026-10-{i + 1:02d}"
        log["pub"][d] = R.snap(dict(PM, next=d))
        acts[d] = {"open": 39716 + (900 if i % 2 else 100), "hi": 41000, "lo": 38000}        # 一半超出八成範圍；當天晃動 3,000 點
    assert R.update(log, {}, act=lambda d: acts.get(d))
    s = log["sum"]
    assert s["n"] == 12 and s["in"] == 6 and s["rng_med"] == round(3000 / 1397, 3)
    assert s["warn"][0].startswith("範圍太窄") and s["warn"][1].startswith("最近實際晃得比正常波動大")   # 3000/1397＝2.1 > 2.0
    r1 = log["rev"]["2026-10-12"]
    assert r1["r1"] == round(644 * min(max((3000 / 1397) / S.RANGE_NORM, 1), 2))                       # 只用前幾天的晃動
    assert "r1" not in log["rev"]["2026-10-01"] and not s["switch"]                                      # 第一天沒有前面的天數；天數不夠不判斷
    line = R.push_line(log, "2026-10-12")
    assert line.startswith("盤前檢討（10/12）：估 39,716、實際 40,616，差 +900（0.64 倍正常波動，超出八成範圍）")
    assert "近 12 天八成範圍包住 6 天；範圍太窄" in line
    assert R.push_line(log, "2026-10-13") is None                                                         # 檢討日不是最新資料日：不帶


def test_switch_rule():
    s = {"n": 40, "n_in": 40, "in": 24, "r1": {"n": 40, "in": 32, "w": 1.3}}
    assert R.switch_ok(s)
    assert not R.switch_ok(dict(s, r1={"n": 39, "in": 32, "w": 1.3}))
    assert not R.switch_ok(dict(s, in_=0, **{"in": 32}))          # 現行版已經在 70%～90%：不換
    assert not R.switch_ok(dict(s, r1={"n": 40, "in": 32, "w": 1.7}))
