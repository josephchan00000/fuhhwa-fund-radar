"""飆股前瞻記錄的規格（sxlivespec VER 1）鎖住：要改就 VER＋1、寫進 docs/lab_core70_plan.md 第 14 節。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import sxlivespec as S  # noqa: E402


def test_sxlive_spec_v1_is_locked():
    assert S.VER == 1
    assert S.SPEC_DATE == "2026-10-23"
    assert S.START == "2026-10-23"
    assert S.BOOKS == ("R60", "A", "R1")
    assert S.RULE_BOOKS == ("R60", "A")
    assert S.SEED_YEAR == 2026
    assert S.RULES_FILE == "sxlive_rules.json" and S.LOG_FILE == "sxlive.json"
    assert S.TRADE == {"capital": 10_000_000, "weight": 0.125, "hold": 60, "lot": 1000, "max_weight": 0.20,
                       "max_adv": 0.05, "max_positions": 20, "commission": 0.001425, "discount": 0.6, "min_fee": 20.0,
                       "sell_tax": 0.003, "slip_tiers": ((1e9, 0.0005), (1e8, 0.0015), (1e7, 0.0030), (0.0, 0.0060))}
    assert S.REVIEWS == (("half", "2027-04-23"), ("year", "2027-10-22"))
    assert S.SUGGEST == {"mdd_extra": 10.0}


def test_start_is_the_spec_date_and_first_week_follows_the_official_calendar():
    # 寫規格時 10/23（五）是這一週最後一個交易日；當天臨時因薔琵颱風休市（twholidays.ADHOC）。
    # 「START 起每週最後一個交易日」照字面：10/19 那一週的最後交易日 10/22 早於 START、不記，第一筆＝10/30。
    from datetime import date
    from arm import twholidays
    from arm.lab import sxlive as L
    d = date.fromisoformat(S.START)
    assert S.START == S.SPEC_DATE and d.weekday() == 4
    assert twholidays.is_closed(d) is True
    assert L.week_ends(S.START, "2026-11-06") == ["2026-10-30", "2026-11-06"]


def test_seed_rules_are_the_w7_2026_fold_unchanged():
    w7 = json.loads((ROOT / S.SEED_SRC).read_text(encoding="utf-8"))
    seed = json.loads((ROOT / "data" / "lab" / S.RULES_FILE).read_text(encoding="utf-8"))["years"][str(S.SEED_YEAR)]
    for lab in S.RULE_BOOKS:
        fold = next(f for f in w7["folds"] if f["lab"] == lab and f["y"] == S.SEED_YEAR)
        assert seed[lab]["thr"] == fold["thr"] == "main"
        assert seed[lab]["rules"] == fold["rules"] and len(fold["rules"]) == 5


def test_trade_settings_match_the_w7_engine():
    """照做的設定＝W7 用的引擎（tw-superstock-lab engine 的預設成本與設定、combos.run 的固定權重模式）。"""
    pytest.importorskip("pandas")
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "src"))
    from superstock import engine as EN
    from arm.lab import superfixspec as X
    c, cfg = EN.Costs(), EN.EngineConfig()
    T = S.TRADE
    assert (cfg.capital, cfg.lot, cfg.max_weight, cfg.max_adv, cfg.max_positions, cfg.entry_valid_days) == \
        (T["capital"], T["lot"], T["max_weight"], T["max_adv"], T["max_positions"], 1)
    assert (c.commission, c.discount, c.min_fee, c.sell_tax, c.slip_tiers) == \
        (T["commission"], T["discount"], T["min_fee"], T["sell_tax"], T["slip_tiers"])
    assert T["weight"] == X.TRADE["weight"] and T["hold"] == X.TRADE["hold"]["R60"] == X.TRADE["hold"]["A"]
