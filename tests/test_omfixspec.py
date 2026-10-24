"""美股三成營益率的一次性收入修法（omfixspec VER 1）鎖住：要改就 VER＋1、寫進 docs/lab_us_sleeve_plan.md 第 14 節。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import omfixspec as S  # noqa: E402
from arm.lab import ussxspec as X  # noqa: E402


def test_omfix_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-24"
    assert S.OM_MIN == 0.10 and S.SPIKE == 0.20
    assert S.CANDS == {"A": {"kind": "spike", "spike": 0.20}, "B": {"kind": "prev"}, "C": {"kind": "median"}}
    assert S.ORDER == ("A", "B", "C")
    assert S.DESC == {"A10": {"kind": "spike", "spike": 0.10}, "A30": {"kind": "spike", "spike": 0.30}, "T": {"kind": "ttm"}}
    assert S.TARGET == ("CDNA", "2026-07-31")
    assert S.KEYS == ("om1", "om4", "omm") and S.PLANS == ("spx", "ndx")


def test_research_does_not_touch_live_rule():
    """研究期間 ussxspec 照舊（VER 6）：網頁與每週紀錄都比對它的版本號。"""
    assert X.VER == 6 and X.QM["om"] == S.OM_MIN
