"""台指期早盤策略的規格（futspec VER 1）鎖住：要改就 VER＋1、寫進 docs/lab_fut_plan.md。"""
from __future__ import annotations

import gzip
import json
import statistics
from pathlib import Path

import pytest

from arm.lab import futspec as S

ROOT = Path(__file__).resolve().parents[1]


def test_fut_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-27"
    assert S.PRODUCT == "TX" and S.POINT_NTD == 200
    assert S.DECIDE_S == 32370 and S.EXIT_S == 49440 and S.REF_S == 48600
    assert S.COVER_MIN == 0.95
    assert S.VERSIONS == ("lookahead", "realtime")
    assert S.TH_WINDOW == 20 and S.TH_MIN_HIST == 10 and S.TH_TOP_PCT == 45
    assert S.SCALE_BASE == 23919.0
    assert S.POINTS == {"stop": 10, "buf": 2, "clear": 20, "target": 60}
    assert S.SLIP == 1 and S.TAX == 0.00002 and S.FEE_NTD == 60
    assert S.JUDGE == {"days": 60, "min_trades": 30, "placebo_n": 1000, "placebo_p": 0.05}
    assert S.SEED == 20261027
    assert S.COMPARE == ("raw_points", "always_long", "always_short")


def test_realtime_estimator_waits_for_ver2():
    # 即時版用哪些欄位等 10/28 盤前探針看過再寫（VER 2），在那之前不能有即時版成績
    assert S.REALTIME is None


def test_scale_base_is_2025_taiex_average():
    d = json.loads(gzip.decompress((ROOT / "data/lab/heat/taiex.json.gz").read_bytes()))["d"]
    v = [x for k, x in d.items() if k.startswith("2025-")]
    assert round(statistics.mean(v)) == S.SCALE_BASE


def test_points_scale_with_index_level():
    assert S.points(23919.0) == {"stop": 10, "buf": 2, "clear": 20, "target": 60}
    assert S.points(46041.43) == {"stop": 19, "buf": 4, "clear": 38, "target": 115}
    assert S.points(46041.43, raw=True) == S.POINTS


def test_cost_per_side():
    assert S.cost_side(46000) == pytest.approx(0.92 + 0.3)


def test_threshold_is_top_45_percent_of_past_20_days():
    assert S.threshold([float(x) for x in range(9)]) is None            # 不到 10 天不做
    past = [float(x) for x in range(1, 21)]                             # 1..20
    th = S.threshold(past)
    assert th == 12.0 and sum(x >= th for x in past) == 9               # 20 天裡前 9 天（45%）
    assert S.threshold([float(x) for x in range(1, 31)]) == 22.0        # 只看最近 20 天（11..30）
    assert S.threshold([float(x) for x in range(1, 11)]) == 6.0         # 10 天：第 5 個（0 起算）
