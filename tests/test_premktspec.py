"""盤前作戰圖第 3 段規格（premktspec VER 2）鎖定：改任何常數都要 VER＋1 並更新這裡（docs/lab_premarket_plan.md 第 11、13 節）。"""
from arm.lab import premktspec as S


def test_spec_locked():
    assert S.VER == 2 and S.SPEC_DATE == "2026-11-05"
    assert S.fingerprint() == "4c8647a85caea9cf"          # VER 1＝dbd6b710e11b2e66（開盤 09:00:05）


def test_spec_sane():
    assert S.OPEN_T == 12                                  # 09:01:00
    assert S.MIN_X < S.MAX_X and 0 < S.BOUNCE < 1 and S.P_MAX <= 0.05
    assert all(d in (+1, -1) and t and set(t) <= {"oc", "cc"} for d, _, t in S.FACTORS.values())
    assert "vol" not in " ".join(S.LEVEL_KINDS)          # 成交量價位只有 30 天逐筆，不驗證
