"""交易計畫的規格（docs/lab_practical_plan.md 第 13 節）：規格鎖定、可以照做的市場和研究判定一致。

規格是在算任何計畫的新數字之前寫定的（VER 1，2026-10-23）。要改就 VER＋1、寫進規劃文件，不在舊版本上改。"""
import json
from pathlib import Path

from arm.lab import planspec as X
from arm.lab import practlive
from arm.lab import practspec
from arm.lab import tilt
from arm.lab import tiltspec

ROOT = Path(__file__).resolve().parents[1]


def test_plan_spec_v1_is_locked():
    assert X.VER == 1 and X.SPEC_DATE == "2026-10-23"
    assert X.MARKETS == practspec.MARKETS == tiltspec.MARKETS
    assert X.PLANS == {
        "def": {"name": "防守：總經策略全部照做", "short": "總經策略全部照做", "src": "practsim", "rule": "M2"},
        "atk": {"name": "進攻：一直抱著＋200 日均線上用期貨多拿 5 成", "short": "200 日均線上加碼", "src": "tilt", "rule": "K4"},
    }
    assert X.AVAIL == {"def": ("tw", "ixic", "ndx", "sox"), "atk": ("tw", "ndx")}
    assert X.LIVE_FROM == {"def": "practsim_live", "atk": "2026-10-23"} and X.LIVE_FROM["atk"] == tilt.LIVE_START
    assert X.CHECKS == (63, 126, 252, 504, 756) and X.CHECKS[0] == practlive.MIN_DAYS == tilt.LIVE_MIN_DAYS
    assert (X.WEEK_DAYS, X.NB_Q, X.NB_MIN, X.P_LOW, X.P_HIGH) == (5, 0.20, 30, 0.05, 0.95)
    assert X.RANGE_W == 52 and X.RANGE_Q == (0.05, 0.25, 0.50, 0.75, 0.95)
    assert set(X.STATUS) == set(X.STATUS_NAMES)
    assert X.CONTRACTS == {"tw": (("微台", 10), ("小台", 50), ("大台", 200)), "ndx": (("MNQ", 2), ("NQ", 20))}
    assert set(X.CONTRACTS) == set(X.CUR) == set(X.CAPITAL) == set(X.AVAIL["atk"])


def test_plan_rules_are_the_page_rules_of_their_studies():
    """收的規則＝兩個研究各自事前定好的上網頁條件過了的那一條；進攻只在有期貨、判定的市場。"""
    assert X.PLANS["def"]["rule"] in practspec.STRAT_RULES and X.PLANS["def"]["rule"] in practspec.PAGE_RULES
    assert X.PLANS["atk"]["rule"] in tiltspec.PAGE_RULES
    assert set(X.AVAIL["atk"]) <= set(tiltspec.JUDGED)
    assert set(X.AVAIL["def"]) <= set(X.MARKETS)


def test_avail_matches_research_verdicts():
    """研究檔重跑、判定變了 → 這裡會紅：要寫新版本的交易計畫（VER＋1），不能讓頁面默默換掉做法。"""
    P = json.loads((ROOT / "data/lab/practsim_research.json").read_text(encoding="utf-8"))
    T = json.loads((ROOT / "data/lab/tilt_research.json").read_text(encoding="utf-8"))
    assert P["page"]["M2"]["ok"] and T["page"]["K4"]["ok"]
    d = tuple(mk for mk in X.MARKETS if P["mk"][mk]["rules"]["M2"]["v"] == "better")
    a = tuple(mk for mk in X.MARKETS if mk in tiltspec.JUDGED and T["mk"][mk]["rules"]["K4"]["v"] == "better")
    assert d == X.AVAIL["def"] and a == X.AVAIL["atk"]
