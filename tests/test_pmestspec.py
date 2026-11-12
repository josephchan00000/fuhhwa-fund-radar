"""盤前第 5 段規格（pmestspec VER 1）鎖定：改任何常數都要 VER＋1 並更新這裡（docs/lab_premarket_plan.md 第 16 節）。"""
from arm.lab import pmestspec as S


def test_spec_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-11-12"
    assert S.fingerprint() == "c56862eb5b2d2b93"
    assert S.MIN_GAIN == 0.10 and S.OPEN_T == 12
