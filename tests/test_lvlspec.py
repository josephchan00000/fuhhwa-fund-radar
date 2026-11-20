"""價位補充規則的規格鎖定（arm/lab/lvlspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import lvlspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-20" and S.LOOKBACK == 750
    assert S.fingerprint() == "48f718e0e21a"
