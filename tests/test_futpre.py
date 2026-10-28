"""台指期早盤策略：每天盤前取樣（arm/lab/futpre.py）——輪流的批次、欄位、只記變了的欄位、時間表、只增不改。"""
from __future__ import annotations

from pathlib import Path

import pytest

from arm.lab import futpre as P
from arm.lab import futsig as G
from arm.lab import store

ROOT = Path(__file__).resolve().parents[1]

# 2026-10-27 探針抓到的一檔（盤後，欄位格式）
MIS_2330 = {"@": "2330.tw", "tv": "6434", "ps": "6434", "pz": "2400.0000", "a": "2400.0000_2405.0000_",
            "b": "2395.0000_2390.0000_", "c": "2330", "f": "399_2015_", "g": "31_235_", "ip": "0",
            "h": "2405.0000", "l": "2380.0000", "o": "2380.0000", "t": "13:30:00", "tlong": "1793082600000",
            "v": "33726", "y": "2385.0000", "z": "2400.0000", "ts": "0", "%": "14:30:00", "n": "台積電"}


def test_plan_rotates_batches_two_per_tick():
    assert P.plan(3, 4) == [[0, 1], [2, 0], [1, 2], [0, 1]]
    assert P.plan(1, 2) == [[0], [0]]


def test_ticks_cover_0858_to_090015_every_5s():
    tk = P.ticks()
    assert tk[0] == 8 * 3600 + 58 * 60 and tk[-1] == 9 * 3600 + 15 and len(tk) == 28
    assert 8 * 3600 + 59 * 60 + 30 in tk                                  # 決定時間 08:59:30 那一輪


def test_tw_row_keeps_first_level_quotes():
    r = dict(zip(P.TW_F, P.tw_row(MIS_2330)))
    assert r["pz"] == "2400.0000" and r["a1"] == "2400.0000" and r["b1"] == "2395.0000"
    assert r["f1"] == "399" and r["g1"] == "31" and r["t"] == "13:30:00"


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LAB", tmp_path)
    syms = [f"{1100 + i}" for i in range(120)]
    monkeypatch.setattr(G, "weights", lambda dp: {c: (200 - i) / 10000 for i, c in enumerate(syms)})
    clk = {"t": 8 * 3600 + 50 * 60.0, "n": 0}
    calls = []

    def now_s():
        return clk["t"]

    def sleep(s):
        clk["t"] += s

    def get_tw(codes):
        clk["t"] += 1.8
        clk["n"] += 1
        calls.append((round(clk["t"] - 1.8, 2), tuple(codes)))
        rows = []
        for c in codes:
            px = "100.0" if clk["n"] < 3 else "101.0"                      # 第 3 個請求起價格變了
            rows.append({"c": c, "pz": px, "y": "99.0", "a": "101.5_102_", "b": "100.5_100_"})
        return rows, "HTTP 200"

    def get_tf():
        clk["t"] += 0.4
        return [{"SymbolID": "TXF-S", "CTestPrice": "46000"}, {"SymbolID": "TXFL6-F", "CLastPrice": "46300"}], "HTTP 200"

    return {"syms": syms, "clk": clk, "calls": calls, "now_s": now_s, "sleep": sleep, "get_tw": get_tw, "get_tf": get_tf}


def test_sample_schedule_and_delta_roundtrip(fake):
    f = fake
    doc = P.sample("2026-10-28", "2026-10-27", now_s=f["now_s"], sleep=f["sleep"], get_tw=f["get_tw"], get_tf=f["get_tf"])
    assert doc["syms"] == f["syms"] and len(doc["w"]) == 120                 # 120 檔＝三批（50、50、20）
    assert f["calls"][0][0] == P.START_S and f["calls"][0][1][:2] == P.IDX  # 第一個請求帶指數、08:58:00 開始
    assert len(f["calls"][0][1]) == 2 + 50 and len(f["calls"][1][1]) == 50
    assert doc["n"] == {"ok": 56, "err": 0, "skip_ticks": 0}                 # 28 輪 × 2 個請求
    snaps = P.decode(doc)
    tws = [s for s in snaps if s["k"] == "tw"]
    # 第一個請求每檔是完整欄位；第 3 個請求（第 2 輪第 1 批）同一批 0 號檔再出現時只記變了的 pz
    assert tws[0]["r"]["1100"]["pz"] == "100.0" and tws[0]["r"]["1100"]["a1"] == "101.5"
    raw = doc["s"]
    third_tw = [s for s in raw if s["k"] == "tw"][3]                         # 第 2 輪第 2 個請求＝第 0 批（價格已經變了）
    assert third_tw["b"] == 0 and third_tw["r"]["1100"] == {"0": "101.0"}
    assert [s for s in snaps if s["k"] == "tw"][3]["r"]["1100"]["pz"] == "101.0"
    assert snaps[2]["k"] == "tf" and snaps[2]["r"]["TXF-S"]["CTestPrice"] == "46000"
    assert doc["y"]["1100"] == "99.0"
    assert P.save(doc) and not P.save(doc)                                  # 只增不改


def test_sample_skips_ticks_already_passed(fake):
    f = fake
    f["clk"]["t"] = 9 * 3600 + 0 * 60 + 2.0                                  # 09:00:02 才開始
    doc = P.sample("2026-10-28", "2026-10-27", now_s=f["now_s"], sleep=f["sleep"], get_tw=f["get_tw"], get_tf=f["get_tf"])
    assert doc["n"]["skip_ticks"] == 24                                     # 08:58:00～08:59:55 共 24 輪過了不補
    assert f["calls"][0][0] == pytest.approx(9 * 3600 + 2.0)                  # 09:00:00 那一輪還在 5 秒內，照抓


def test_sample_without_weights_returns_none(fake, monkeypatch):
    monkeypatch.setattr(G, "weights", lambda dp: {})
    f = fake
    assert P.sample("2026-10-28", "2026-10-27", now_s=f["now_s"], sleep=f["sleep"], get_tw=f["get_tw"], get_tf=f["get_tf"]) is None


def test_workflow_schedules_five_runs_and_commits_only_samples():
    y = (ROOT / ".github/workflows/fut_preopen.yml").read_text(encoding="utf-8")
    for c in ('"47 19 * * 0-4"', '"31 20 * * 0-4"', '"17 21 * * 0-4"', '"3 22 * * 0-4"', '"17 23 * * 0-4"'):
        assert c in y
    # 最早一班（台北 03:47）準時開跑也要等得到 09:00:15：等的時間 < python 的 timeout < job 的 timeout
    wait_min = (9 * 60 + 0.25) - (3 * 60 + 47)
    assert wait_min < 19500 / 60 < 330 and "timeout-minutes: 330" in y
    assert "group: fut-preopen" in y and "cancel-in-progress: false" in y
    assert "ref: main" in y and "git add -f data/lab/fut/pre" in y and "HEAD:main" in y
    assert "timeout 19500 python3 scripts/fut_preopen.py" in y
