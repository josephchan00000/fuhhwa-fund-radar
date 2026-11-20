"""台股財報季規格鎖定（arm/lab/ernspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import ernspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-20"
    assert S.fingerprint() == "b47e324e0e1a"
