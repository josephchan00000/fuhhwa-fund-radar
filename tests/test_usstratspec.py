"""美股個股策略的規格（usstratspec VER 1）鎖住：要改就 VER＋1、寫進 docs/lab_core70_plan.md 第 15 節。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import usstratspec as S  # noqa: E402


def test_usstrat_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-23"
    assert S.STRATS == ("U1", "U2", "U3")
    assert (S.MIN_EST, S.EPS_FLOOR, S.TOP_N, S.LOOK, S.SKIP, S.COST) == (3, 0.10, 10, 252, 21, 0.0005)
    assert S.BOOK == {"weight": 0.125, "hold": 60, "max_positions": 20}
    assert S.START == "2009-01-01" and S.HALVES == (("2009-01-01", "2017-12-31"), ("2018-01-01", "2100-12-31"))
    assert S.PASS == {"ew_pts": 3.0, "mdd_extra": 10.0}
    assert S.NEIGHBORS == {"U1": ({"weight": 0.25}, {"weight": 0.0625}, {"hold": 40}, {"hold": 80}),
                           "U2": ({"top": 5}, {"top": 20}), "U3": ({"top": 5}, {"top": 20})}
