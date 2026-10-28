"""檢討第 1 步（docs/lab_review_plan.md 第 9.1 節）：持股的買進日不晚於策略開始記錄的那一天＝回測，另寫上線以來。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import analyze as A  # noqa: E402


class _D:
    def __init__(self, cal, px):
        self.cal, self.px = cal, px

    def quote(self, c, d):
        x = (self.px.get(c) or {}).get(d)
        return None if x is None else [x, x, x, x, 1000, None]


def test_live_since_marks_backtest_buys_and_return_since_start():
    cal = ["2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]
    px = {"2330": {"2026-10-13": 100.0, "2026-10-14": 110.0, "2026-10-15": 105.0, "2026-10-16": 120.0, "2026-10-19": 121.0},
          "2454": {"2026-10-15": 50.0, "2026-10-19": 55.0},
          "3037": {"2026-10-13": 10.0, "2026-10-19": 9.0}}
    adv = {"grades3": [{"k": "v3l", "since": "2026-10-15"}], "book": [{"k": "v3l"}, {"k": "s3", "since": "2026-10-14"}],
           "picks": [{"k": "v3l", "c": "2330", "act": "持有中", "ent": "2026-10-13"},
                     {"k": "v3l", "c": "2454", "act": "持有中", "ent": "2026-10-16"},
                     {"k": "s3", "c": "3037", "act": "持有中", "ent": "2026-10-14"},
                     {"k": "v3l", "c": "2330", "act": "待買進", "ent": "2026-10-20"}]}
    ev = {"2330": [("2026-10-16", 0.98, 0.98)]}                   # 10/16 除息：還原倍數 0.98（含息）
    A.live_since(adv, _D(cal, px), ev)
    p1, p2, p3, p4 = adv["picks"]
    assert p1["bt"] and p1["since"] == "2026-10-15"
    assert p1["rl"] == pytest.approx(121.0 / (105.0 * 0.98) - 1, rel=1e-6)   # 收盤 105（10/15）→ 121，加回除息
    assert "bt" not in p2 and "rl" not in p2 and p2["since"] == "2026-10-15"  # 開始記錄以後才買
    assert p3["bt"] and p3["rl"] == pytest.approx(9.0 / 10.0 - 1)            # 10/14 那天沒有收盤：往前找 10/13
    assert "since" not in p4                                                 # 不是持有中：不動
