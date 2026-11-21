"""大盤修正中的領導股規格鎖定（arm/lab/leadspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import leadspec as S


def test_spec_locked():
    assert S.VER == 2 and S.SPEC_DATE == "2026-11-21" and S.GROWTH == 0.25
    assert S.fingerprint() == "e26618277c4f"   # VER 1：325de5d6a9ec
