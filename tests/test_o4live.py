"""O4 結算均價的紙上紀錄（arm/lab/o4live.py、scripts/run_o4live.py；docs/lab_txo_plan.md 第 21 節）：只增不改、規格改了不再加。"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from arm.lab import o4live as L
from arm.lab import txo1 as X
from arm.lab import txospec as S

ROOT = Path(__file__).resolve().parents[1]
PICK = {"F": 39823.89, "band": 231.38, "cp": "C", "d": "2026-11-06", "exp": "202611F1", "floor": 179.43, "gap": 2.08,
        "k": 3120, "kx": 39600.0, "p0": 175.0, "parts": [["all", 223.89, 3240, "settle"]], "w": 1.0}


def _fake(monkeypatch, sett: dict, bars: set):
    idx = {d: np.full(3241, 40000.0) for d in sett}                       # 一整天的 5 秒指數（09:00:00～13:30:00）
    monkeypatch.setattr(X, "load_idx", lambda root: idx)
    monkeypatch.setattr(X, "load_book", lambda root: (sorted(sett), {}, {}))
    monkeypatch.setattr(X, "settle_days", lambda days, last, idx: dict(sett))
    monkeypatch.setattr(X, "load_bars", lambda root, d: {} if d in bars else None)
    monkeypatch.setattr(X, "o4_day", lambda m, root, d: ([dict(PICK, d=d)] if d == "2026-11-06" else [], [1, 2, 3]))


def test_update_appends_only_new_complete_days(monkeypatch):
    sett = {"2026-09-10": "x", "2026-11-04": "x", "2026-11-06": "x", "2026-11-11": "x", "2026-11-13": "x", "2026-11-18": "x"}
    _fake(monkeypatch, sett, bars={"2026-11-04", "2026-11-06", "2026-11-11", "2026-11-18"})
    led = L.new_book()
    led["days"]["2026-11-04"] = {"F": 1.0, "cands": 9, "picks": [], "rec": "2026-11-06"}          # 已經記過：不動
    new = L.update(Path("."), led, "2026-11-13", log=lambda *a: None)
    assert new == ["2026-11-06", "2026-11-11"]          # 9/10 在 O4_FROM 之前、11/13 沒有分 K、11/18 還沒到
    assert led["days"]["2026-11-04"] == {"F": 1.0, "cands": 9, "picks": [], "rec": "2026-11-06"}
    assert led["days"]["2026-11-06"]["picks"][0]["kx"] == 39600.0 and led["days"]["2026-11-06"]["cands"] == 3
    assert led["days"]["2026-11-11"]["rec"] == "2026-11-13" and led["asof"] == "2026-11-18"


def test_update_stops_when_spec_changes(monkeypatch):
    _fake(monkeypatch, {"2026-11-06": "x"}, bars={"2026-11-06"})
    led = dict(L.new_book(), spec_fp="0000000000000000")
    assert L.update(Path("."), led, "2026-11-13", log=lambda *a: None) == [] and led["days"] == {}


def test_summary_resizes_from_ledger_with_backtest_rules():
    led = L.new_book()
    led["days"] = {"2026-11-04": {"F": 42978.23, "cands": 151, "picks": [], "rec": "2026-11-13"},
                   "2026-11-06": {"F": 39823.89, "cands": 121, "picks": [PICK], "rec": "2026-11-13"},
                   "2026-11-11": {"F": 43991.65, "cands": 120, "picks": [], "rec": "2026-11-13"}}
    s = L.summarize(led)
    assert s["metrics"]["n"] == 1 and s["trades"][0]["lots"] == 1 and round(s["trades"][0]["pnl"], 1) == 2204.6
    assert s["judge"]["verdict"] == "只列、不判定（筆數不夠）"
    assert [x["picks"] for x in s["days"]] == [0, 1, 0] and s["after_spec"] == 1           # 規格 11/11 寫定之後的結算日
    assert S.O4_CAP_EACH == 0.01


def test_script_refuses_to_rewrite_old_days(tmp_path, monkeypatch):
    """舊的日子被改（例如資料或程式變了）就不寫，紀錄維持原樣。"""
    out = tmp_path / "live.json"
    led = L.new_book()
    led["days"]["2026-11-06"] = {"F": 1.0, "cands": 1, "picks": [], "rec": "2026-11-13"}
    out.write_text(json.dumps(led), encoding="utf-8")
    code = ("import sys,json;sys.path.insert(0,%r);from arm.lab import o4live as L;"
            "L.update=lambda root,led,today,log=print:led['days'].update({'2026-11-06':{'F':2.0,'cands':1,'picks':[],'rec':'x'}}) or [];"
            "sys.argv=['x','--root','.','--out',%r];import runpy;runpy.run_path(%r,run_name='__main__')"
            % (str(ROOT), str(out), str(ROOT / "scripts/run_o4live.py")))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 1 and "只增不改" in r.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["days"]["2026-11-06"]["F"] == 1.0


def test_live_file_in_repo_is_consistent():
    p = ROOT / "data/lab/txo_o4_live.json"
    if not p.exists():
        return
    led = json.loads(p.read_text(encoding="utf-8"))
    assert led["spec_fp"] == S.fingerprint() and all(d >= S.O4_FROM for d in led["days"])
    assert [x["d"] for x in led["sum"]["days"]] == sorted(led["days"])
