"""股市位階規格鎖定（arm/lab/mposspec.py）：改規格＝VER＋1，這支測試跟著改。"""
from arm.lab import mposspec as S


def test_spec_locked():
    assert S.VER == 3 and S.SPEC_DATE == "2026-11-20" and S.MIN_ITEMS == 2 and S.MACRO_US == ("fund", "liq")
    assert S.fingerprint() == "dd0bc8b87ff1"   # VER 1：d3b67c22036f；VER 2：0634cf8ac99b
    assert [g for g, _ in S.GROUPS] == ["價格位置", "部位與籌碼", "情緒", "廣度"]
