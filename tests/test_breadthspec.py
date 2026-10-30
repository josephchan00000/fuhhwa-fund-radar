"""寬度與深度的規格鎖定：算任何新讀數之後的漲跌之前寫定（arm/lab/breadthspec.py、docs/lab_breadth_plan.md 第 9 節）。"""
from arm.lab import breadthspec as S
from arm.lab import sigspec


def test_spec_v1_is_locked():
    assert S.VER == 1 and S.SPEC_DATE == "2026-10-30"
    assert S.MKT_VARS == ("TW_EWGAP", "TW_MA200", "US_ADV", "US_UPV", "US_EWGAP")
    assert set(S.VAR_NAMES) == set(S.MKT_VARS) == set(S.VAR_MKT)
    assert (S.LB, S.MA_N, S.ADV_W, S.MIN_N, S.H) == (120, 200, 10, 50, 20) and S.H == sigspec.H_TECH
    assert S.EW_PAIRS == {"spx": ("SPY", "RSP"), "ixic": ("QQQ", "QQEW"), "ndx": ("QQQ", "QQEW")}
    assert "sox" not in S.VAR_MKT["US_EWGAP"]                                      # 費半沒有等權 ETF
    assert S.GROUPS == ("tw", "tg", "us", "ff") and S.DEPTH_GROUPS == ("tw", "ff") and S.LEVEL_MIN == 2
    assert (S.FWD_M, S.DD, S.IB_TH, S.ID_TH, S.EDGE) == (12, 0.20, 0.20, 0.20, 0.10)
    assert (S.BLOCK, S.BOOT, S.SEED, S.EPI_GAP, S.MIN_EPI, S.MIN_EPI2) == (12, 2000, 20261030, 12, 5, 3)
    assert S.DESCRIBE_TH == (0.10, 0.30)


def test_episodes_passes_and_verdict():
    assert S.episodes([]) == 0
    assert S.episodes(["1999-01", "1999-02", "1999-12"]) == 1                       # 相隔 11 個月還是同一段
    assert S.episodes(["1986-06", "1987-10"]) == 2                                  # 相隔 16 個月＝新的一段
    assert S.passes(0.12, 0.01, 5, S.MIN_EPI) and not S.passes(0.09, 0.05, 9, S.MIN_EPI)
    assert not S.passes(0.30, -0.01, 9, S.MIN_EPI) and not S.passes(0.30, 0.05, 4, S.MIN_EPI)
    assert not S.passes(None, None, 9, S.MIN_EPI)
    assert S.verdict(True, True) == "寫進泡沫等級的候選" and S.verdict(True, False).startswith("參考讀數加一句")
    assert S.verdict(False, True) == S.verdict(False, False) == "只當參考讀數（看不出）"
