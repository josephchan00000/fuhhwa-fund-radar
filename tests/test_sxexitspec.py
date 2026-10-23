"""飆股出場法（W8，sxexitspec VER 1）鎖住：要改就 VER＋1、寫進 tw-superstock-lab/reports/W8_plan.md。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sxexitspec as S  # noqa: E402


def test_sxexit_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-23"
    assert S.EXITS == {"X0": {"hold": 60}, "X1": {"ma": 50}, "X2": {"ma": 20}, "X3": {"trail": 0.20},
                       "X4": {"trail": 0.30}, "X5": {"stop": 0.08, "ma": 50}, "X6": {"stop": 0.20, "trail": 0.30}}
    assert S.BASE == "X0" and S.NEIGHBORS == (("X1", "X2"), ("X3", "X4"))
    assert S.LABELS == ("R60", "A") and S.PRIMARY == "R60" and S.PASS == {"mdd_extra": 5.0}
