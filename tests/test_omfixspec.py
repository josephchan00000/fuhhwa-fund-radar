"""美股三成營益率的一次性收入修法（omfixspec VER 2）鎖住：要改就 VER＋1、寫進 docs/lab_us_sleeve_plan.md 第 14 節。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import omfixspec as S  # noqa: E402
from arm.lab import ussxspec as X  # noqa: E402


def test_omfix_spec_v2_is_locked():
    assert S.VER == 2 and S.SPEC_DATE == "2026-10-24"
    assert S.OM_MIN == 0.10 and S.SPIKE == 0.20
    assert S.CANDS == {"A": {"kind": "spike", "spike": 0.20}, "B": {"kind": "prev"}, "C": {"kind": "median"},
                       "D": {"kind": "spike_ox", "spike": 0.20}}
    assert S.ORDER == ("A", "B", "C") and S.PREFER == "D"
    assert S.DESC == {"A10": {"kind": "spike", "spike": 0.10}, "A30": {"kind": "spike", "spike": 0.30},
                      "D10": {"kind": "spike_ox", "spike": 0.10}, "D30": {"kind": "spike_ox", "spike": 0.30}, "T": {"kind": "ttm"}}
    assert S.TARGET == ("CDNA", "2026-07-31")
    assert S.KEYS == ("om1", "om4", "omm", "oxr") and S.PLANS == ("spx", "ndx")


def test_live_rule_adopted_d():
    """研究期間 ussxspec 照舊（VER 6）；使用者 2026-10-24 選 D 之後才出 VER 7，名單條件＝D。"""
    assert X.VER == 7 and X.QM["om"] == S.OM_MIN and X.QM_OM_FIX == S.CANDS["D"]
