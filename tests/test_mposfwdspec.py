"""位階和之後漲跌的規格鎖定（arm/lab/mposfwdspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import mposfwdspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-20"
    assert S.fingerprint() == "7afbcec62737"
