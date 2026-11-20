"""股市位階規格鎖定（arm/lab/mposspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import mposspec as S


def test_spec_locked():
    assert S.VER == 2 and S.SPEC_DATE == "2026-11-20" and S.MIN_ITEMS == 2
    assert S.fingerprint() == "0634cf8ac99b"   # VER 1：d3b67c22036f
    assert [g for g, _ in S.GROUPS] == ["價格位置", "部位與籌碼", "情緒", "廣度"]
