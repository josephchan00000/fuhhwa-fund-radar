"""大盤修正中的領導股規格鎖定（arm/lab/leadspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import leadspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-21"
    assert S.fingerprint() == "325de5d6a9ec"
