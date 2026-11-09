"""新項目過關每年重驗（arm/lab/gatereview.py；使用者 2026-11-09：「沒過的指標每年 1 月重驗」＋「先通知、你說好才換」）。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml

from arm.lab import gatereview as R

ROOT = Path(__file__).resolve().parents[1]

DOC = {"made": "2027-01-10", "changed": True,
       "tw": {"live": ["B9", "B11", "C11"], "new": ["B9", "B10", "B11", "C11"], "add": ["B10"], "drop": []},
       "us": {"ndx": {"live": [], "new": ["S10"], "add": ["S10"], "drop": []},
              "spx": {"live": ["T15"], "new": [], "add": [], "drop": ["T15"]},
              "sox": {"live": ["S10"], "new": ["S10"], "add": [], "drop": []}}}
LIVE_OLD = {"tw": {"B9", "B11", "C11"}, "spx": {"T15"}, "ixic": {"S10"}, "ndx": set(), "sox": {"S10"}}
LIVE_NEW = {"tw": {"B9", "B10", "B11", "C11"}, "spx": set(), "ixic": {"S10"}, "ndx": {"S10"}, "sox": {"S10"}}


def test_diff():
    assert R._diff({"a", "b"}, {"b", "c"}) == {"live": ["a", "b"], "new": ["b", "c"], "add": ["c"], "drop": ["a"]}
    assert R.changed(DOC) and not R.changed({"tw": {"add": [], "drop": []}, "us": {"spx": {"add": [], "drop": []}}})


def test_state_pending_then_applied():
    st = R.state(datetime(2027, 1, 11), DOC, LIVE_OLD)
    assert st["pending"] and st["push"] and st["d"] == "2027-01-10"
    assert set(st["us"]) == {"ndx", "spx"}                                       # 沒變的指數不列
    line = R.push_line(st)
    assert line.startswith("新指標年度重驗（1/10）：") and "台積電營收年增率 這次過關" in line
    assert "那斯達克 100：AAII" in line and "S&P 500：上漲家數占比" in line and "不再過關" in line
    assert "回「好」才重跑整套研究換上" in line and "VER" not in line
    assert st["sum"] and st["sum"][0].startswith("台股：")
    done = R.state(datetime(2027, 1, 11), DOC, LIVE_NEW)                        # 使用者說好、重跑換上之後
    assert not done["pending"] and R.push_line(done) is None and done["changed"]


def test_state_old_review_stops_pushing_and_missing_file():
    st = R.state(datetime(2027, 3, 1), DOC, LIVE_OLD)                           # 超過 NOTIFY_DAYS：只留在後台
    assert st["pending"] and not st["push"] and R.push_line(st) is None
    same = dict(DOC, changed=False, tw={"live": ["B9"], "new": ["B9"], "add": [], "drop": []}, us={})
    st = R.state(datetime(2027, 1, 11), same, {"tw": {"B9"}})
    assert not st["pending"] and R.push_line(st) is None and st["sum"] == []
    assert R.state(datetime(2027, 1, 11), {"x": 1}, LIVE_OLD) is None


def test_valog_push_line_and_backstage_block():
    from arm.lab import valog as V
    st = R.state(datetime(2027, 1, 11), DOC, LIVE_OLD)
    lines = V.push_lines({"todo": {"d": "2027-01-11", "items": []}, "gate": st})
    assert lines[0].startswith("1/11") and any(x.startswith("新指標年度重驗") for x in lines)
    assert not any(x.startswith("新指標年度重驗") for x in V.push_lines({"todo": {"d": "2027-01-11", "items": []}}))
    src = (ROOT / "arm/lab/page.py").read_text(encoding="utf-8")
    assert src.count("function boGate(") == 1 and "b+=boGate(T.gate);" in src


def test_review_never_writes_live_gate_files():
    src = (ROOT / "arm/lab/gatereview.py").read_text(encoding="utf-8")
    assert "G.write(" not in src and "GATE_FILE" not in src and "write_text" not in src
    run = (ROOT / "scripts/run_gate_review.py").read_text(encoding="utf-8")
    assert "store.write_json(R.REVIEW_FP" in run and "heat_gate.json" not in run


def test_workflow_runs_in_january_and_commits_only_review_file():
    wf = yaml.safe_load((ROOT / ".github/workflows/gate_review.yml").read_text(encoding="utf-8"))
    cron = wf[True]["schedule"][0]["cron"].split()                              # yaml 把 on: 讀成 True
    assert cron[3] == "1" and "workflow_dispatch" in wf[True]
    steps = " ".join(s.get("run", "") for s in wf["jobs"]["review"]["steps"])
    assert "scripts/run_gate_review.py" in steps and "git add -f data/lab/heat_gate_review.json" in steps
    assert "heat_gate.json" not in steps and "heat_us_gate.json" not in steps
