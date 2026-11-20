"""盤前自我檢討規格鎖定（arm/lab/pmrevspec.py；docs/lab_premarket_plan.md 第 17 節）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import pmrevspec as R


def test_spec_locked():
    assert R.VER == 2 and R.SPEC_DATE == "2026-11-20"
    assert R.fingerprint() == "f2cc1137fdda"   # VER 1：558e88ac2247


def test_switch_rule_is_conservative():
    assert R.SWITCH_MIN >= 40 and R.SWITCH_R1[0] < 0.8 < R.SWITCH_R1[1] and R.R1_CLAMP == (1.0, 2.0)
