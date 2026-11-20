"""台股廣度往前補的規格鎖定（arm/lab/brearlyspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import brearlyspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-20" and S.SPLICE == "2014-01-01"
    assert S.fingerprint() == "5344521a40b5"
