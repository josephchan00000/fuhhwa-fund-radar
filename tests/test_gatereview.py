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


def test_compute_stable_counts_last_20_days(monkeypatch):
    """heatspec VER 14 ③e：最近 20 個交易日各判一次（compute），算分 ≥ 15 天才算分；平行和依序結果相同。"""
    from arm.lab import heatgate as G
    from arm.lab import heatspec as S
    assert (S.GATE_DAYS, S.GATE_NEED) == (20, 15)
    cal = [f"2026-10-{d:02d}" for d in range(1, 26)]                            # 25 天 → 結尾是第 6～25 天
    B = {"cal": cal, "px": list(range(25)), "hc": {"A": list(range(25))}}
    seen = []

    def fake(Bc):
        T = len(Bc["cal"])
        assert len(Bc["px"]) == len(Bc["hc"]["A"]) == T                            # 日曆、價格、0～100 一起截
        seen.append(T)
        adm = ["A"] + (["B"] if T % 2 else []) + (["C"] if T not in (7, 9, 11, 13) else [])
        its = {k: {"pass": k in adm, "a": True, "b": True, "c": True, "h": {}} for k in "ABCD"}
        return {"ver": S.VER, "admit": adm, "items": its,
                "dims": {"chip": {"cands": list("ABCD"), "passed": adm, "admit": adm}}}

    monkeypatch.setattr(G, "compute", fake)
    one = G.compute_stable(B, procs=1)
    assert sorted(seen) == list(range(6, 26))
    assert one["admit"] == ["A", "C"] and one["dims"]["chip"]["admit"] == ["A", "C"]
    assert {k: e["days"] for k, e in one["items"].items()} == {"A": 20, "B": 10, "C": 16, "D": 0}
    assert one["items"]["B"]["pass"] and not one["items"]["B"]["adm"]                # 最後一天過，但只有 10 天 → 不算
    st = one["stable"]
    assert (st["n"], st["need"], st["from"], st["to"]) == (20, 15, cal[5], cal[24]) and len(st["lists"]) == 20
    assert G.compute_stable(B, procs=2) == one                                       # fork 平行算，結果一樣
