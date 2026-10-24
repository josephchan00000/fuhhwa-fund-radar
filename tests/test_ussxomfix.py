"""美股三成營益率的一次性收入修法研究（omfixspec VER 1、arm/lab/ussxomfix.py）。"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import omfixspec as S  # noqa: E402
from arm.lab import ussxfeat as F  # noqa: E402
from arm.lab import ussxomfix as OF  # noqa: E402

NAN = float("nan")


def _f(**kw):
    return {k: np.array(v, dtype=float) for k, v in kw.items()}


def test_block_spike_needs_both_jumps_and_weak_previous_quarter():
    # 列：CareDx 型、只比上一季暴增（季節性）、上一季已經 ≥10%、去年同季沒有資料、上一季沒有資料
    f = _f(om=[0.858, 0.35, 0.76, 0.50, 0.50], om1=[0.010, -0.50, 0.55, 0.0, NAN],
           omd=[0.986, 0.02, 0.57, NAN, 0.40], om4=[0.236, 0.19, 0.58, 0.3, 0.3], omm=[0.004, -0.08, 0.5, 0.2, 0.2])
    a = OF.block(f, S.CANDS["A"])
    assert a.tolist() == [True, False, False, False, False]
    assert OF.block(f, S.DESC["A30"]).tolist() == [True, False, False, False, False]
    assert OF.block(f, None).tolist() == [False] * 5


def test_block_spike_ox_only_when_operating_income_outgrew_revenue():
    """D：A 的條件之外，營業利益比去年同季增加的要比營收增加的多（oxr > 0）；oxr 沒有值＝不擋。"""
    f = _f(om=[0.858, 0.654, 0.858, 0.30], om1=[0.010, -0.482, 0.010, 0.0], omd=[0.986, 16.25, 0.986, 0.25],
           oxr=[0.599, -0.275, NAN, 0.01], om4=[0.2] * 4, omm=[0.0] * 4)
    assert OF.block(f, S.CANDS["D"]).tolist() == [True, False, False, True]          # CareDx 擋、Moderna 不擋
    assert OF.block(f, S.CANDS["A"]).tolist() == [True, True, True, True]
    assert OF.block(f, S.DESC["D30"]).tolist() == [True, False, False, False]


def test_block_prev_median_ttm_treat_missing_as_failing():
    f = _f(om=[0.12, 0.12, 0.12, 0.12], om1=[0.10, 0.09, NAN, 0.2], omd=[0.0] * 4,
           om4=[0.10, 0.2, 0.2, NAN], omm=[0.10, 0.099, NAN, 0.3])
    assert OF.block(f, S.CANDS["B"]).tolist() == [False, True, True, False]
    assert OF.block(f, S.CANDS["C"]).tolist() == [False, True, True, False]
    assert OF.block(f, S.DESC["T"]).tolist() == [False, False, False, True]
    with pytest.raises(ValueError):
        OF.block(f, {"kind": "x"})


def test_target_listed():
    cal = ["2026-07-24", "2026-07-30", "2026-07-31", "2026-08-03"]
    C = {"P": {"col": {"CDNA": 7, "VLO": 3}}, "cal": cal, "cols": {"wk": np.array([0, 2])}}
    assert OF.target_listed(C, {2: [(3, 98.0), (7, 99.0)]}) is True
    assert OF.target_listed(C, {2: [(3, 98.0)]}) is False
    assert OF.target_listed({**C, "cols": {"wk": np.array([0])}}, {}) is None      # 那一天不是週訊號日
    assert OF.target_listed({**C, "P": {"col": {}}}, {}) is None


def test_sec_reports_research_keys():
    """上一季營益率、近四季合計、近四季中位數（只給研究用，規則不看）。"""
    def q(e, v, s, fd):
        return [s, e, v, fd, "10-Q"]
    ends = [("2025-03-31", "2025-01-01", "2025-05-01"), ("2025-06-30", "2025-04-01", "2025-08-01"),
            ("2025-09-30", "2025-07-01", "2025-11-01"), ("2025-12-31", "2025-10-01", "2026-02-15"),
            ("2026-03-31", "2026-01-01", "2026-05-01"), ("2026-06-30", "2026-04-01", "2026-08-01")]
    rev = [85.0, 87.0, 100.0, 108.0, 118.0, 132.0]
    oi = [-13.0, -11.0, -0.2, -6.0, 1.2, 113.0]
    f = {"Revenues": [q(e, v, s, fd) for (e, s, fd), v in zip(ends, rev)],
         "OperatingIncomeLoss": [q(e, v, s, fd) for (e, s, fd), v in zip(ends, oi)]}
    sr, _ = F.sec_reports({"f": f}, [])
    x = {r["end"]: r for r in sr}["2026-06-30"]
    assert x["om"] == pytest.approx(113.0 / 132.0)
    assert x["om1"] == pytest.approx(1.2 / 118.0)
    assert x["om4"] == pytest.approx((-0.2 - 6.0 + 1.2 + 113.0) / (100.0 + 108.0 + 118.0 + 132.0))
    assert x["omm"] == pytest.approx(np.median([-0.2 / 100, -6 / 108, 1.2 / 118, 113 / 132]))
    assert x["omd"] == pytest.approx(113.0 / 132.0 - (-11.0 / 87.0))
    assert x["oxr"] == pytest.approx(((113.0 - -11.0) - (132.0 - 87.0)) / 132.0)     # 營業利益比營收多增加的部分
    first = {r["end"]: r for r in sr}["2025-03-31"]
    assert first["om1"] is None and first["om4"] is None and first["omm"] is None and first["oxr"] is None
