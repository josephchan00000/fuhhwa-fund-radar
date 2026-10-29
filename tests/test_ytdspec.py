"""今年逐月、逐筆表的規格（ytdspec VER 2；VER 2 只把新飆股那四成從 R60 換成 N8）鎖住：要改就 VER＋1、寫進 docs/lab_review_plan.md 第 9.2 節。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import ytdspec as S  # noqa: E402


def test_ytd_spec_v2_is_locked():
    assert (S.VER, S.SPEC_DATE, S.YEAR) == (2, "2026-10-29", 2026)
    assert S.COLS == ("nolook", "hold", "live")
    assert S.TW_W == {"0050": 0.20, "N8": 0.40, "cash": 0.40} and S.TW_BOOM == "N8" and S.LIVE_KEEP == (1,) and abs(sum(S.TW_W.values()) - 1) < 1e-12
    assert S.TW_WARN is False and S.US_WARN is False
    assert S.TW_LIVE_FROM == "2026-10-27" and S.US_LIVE_FROM == "2026-10-23"
    assert (S.US_Y0, S.US_POOLS, S.US_L, S.US_K, S.US_SWITCH) == (2010, ("全部", "不換股", "每週換股"), (3, 5), (1, 3, 5, 10), 0.002)
    assert (S.US_RANK_Y0, S.US_RANK_Y1, S.US_RANK, S.US_IDLE) == (2014, 2025, 13, "cash")
    assert S.US_NS == (5, 8, 12, 20) and S.US_REG == ("不看大盤", "大盤年線上才買")
    assert len(S.US_EXITS_HOLD) == 6 and len(S.US_EXITS_ROT) == 3 and len(S.US_KEEPS) == 2
    assert len(S.US_SELS) == 21 and len(set(S.US_SELS)) == 21
    assert S.n_grid() == 2016
    assert len(S.wf_names()) == 24 and len(set(S.wf_names())) == 24
    assert (S.FILE_TW, S.FILE_US) == ("ytd_tw.json", "ytd_us.json")


def test_live_starts_match_the_plan_records():
    from arm.lab import corespec as C, ussxspec as X
    from arm.lab import corepage as CPG
    assert S.US_LIVE_FROM == X.QM_LIVE
    assert C.LIVE_START <= S.TW_LIVE_FROM
    assert CPG._next_day("tw", "2026-10-25") == S.TW_LIVE_FROM        # 10/26 光復節補假 → 第一個交易日 10/27
