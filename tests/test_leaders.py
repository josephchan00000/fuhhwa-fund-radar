"""大盤修正中的領導股（arm/lab/leaders.py；規格 arm/lab/leadspec.py VER 2）。"""
from arm.lab import leaders as L


def test_market_correction_and_ma():
    idx = [100.0] * 300 + [72.0]
    m = L.market(idx, len(idx) - 1)
    assert m["corr"] and abs(m["dd"] + 0.28) < 1e-9 and m["below200"] and m["vs50"] < 0
    assert not L.market([100.0] * 300 + [90.0], 300)["corr"]                     # 跌 10%：不算修正


def test_passes_three_conditions():
    mk = {"corr": True, "dd": -0.28}
    tt = [True, True, True, True, False, True, True, True]
    ok = {"el": True, "d52h": -0.10, "rs": 95, "tt": tt, "ey": 0.30, "ry3": 0.05}
    assert L.passes(ok, mk)
    assert not L.passes(dict(ok, d52h=-0.15), mk)                                # 跌超過指數的一半
    assert not L.passes(dict(ok, rs=89), mk)
    assert not L.passes(dict(ok, tt=[False] + tt[1:]), mk)                       # 收盤不在 150／200 日線上
    assert not L.passes(dict(ok, tt=tt[:2] + [False] + tt[3:]), mk)              # 200 日線沒上揚
    assert not L.passes(ok, {"corr": False, "dd": -0.10})                        # 不在修正中不列
    assert not L.passes(dict(ok, el=False), mk)
    assert not L.passes(dict(ok, ey=0.10, ry3=0.20), mk)                         # VER 2：沒有成長（防守股）
    assert L.passes(dict(ok, ey=None, ry3=0.40), mk) and not L.passes(dict(ok, ey=None, ry3=None), mk)


def test_three_gates():
    assert L.three_gates({"ey": 0.56, "ry3": 0.43, "eacc": 0.1}) is True
    assert L.three_gates({"ey": 3.0, "ry3": 1.5, "eacc": -0.1, "racc": -0.2}) is False
    assert L.three_gates({"ey": None, "ry3": 0.3}) is None


def _res(d, rows, corr=True):
    return {"ver": 2, "d": d, "n_el": 900, "mkt": {"close": 36000.0, "hi": 49800.0, "dd": -0.277 if corr else -0.05, "corr": corr,
                                                   "vs50": -0.21, "vs200": -0.13, "below200": True},
            "rows": [{"c": c, "n": c, "px": 100.0, "d52h": -0.02, "rs": 95.0} for c in rows]}


def test_add_week_keeps_last_day_and_never_rewrites_past_weeks():
    W = {}
    assert L.add_week(W, _res("2026-11-18", ["6199"]))
    assert L.add_week(W, _res("2026-11-20", ["6199", "6782"]))            # 同一週後面的日子蓋掉前面的
    assert list(W) == ["2026-W47"] and W["2026-W47"]["d"] == "2026-11-20" and [r[0] for r in W["2026-W47"]["rows"]] == ["6199", "6782"]
    assert not L.add_week(W, _res("2026-11-19", ["2412"]))               # 舊的日子不蓋新的
    assert L.add_week(W, _res("2026-11-23", ["6782"]))
    assert not L.add_week(W, _res("2026-11-20", ["2412"]))               # 已經過去的週不改
    assert not L.add_week(W, _res("2026-11-30", ["2412"], corr=False))   # 不在修正中不記
    assert sorted(W) == ["2026-W47", "2026-W48"]


def test_weeks_on_counts_consecutive_weeks():
    W = {}
    for d, rows in (("2026-11-06", ["A"]), ("2026-11-13", ["A", "B"]), ("2026-11-20", ["A", "B"]), ("2026-12-04", ["A"])):
        L.add_week(W, _res(d, rows))
    assert L.weeks_on(W, "A", "2026-11-20") == 3 and L.weeks_on(W, "B", "2026-11-20") == 2
    assert L.weeks_on(W, "A", "2026-12-04") == 1                         # 11/27 那一週沒有紀錄＝斷掉
    assert L.weeks_on(W, "C", "2026-11-20") == 0


def test_record_only_writes_on_ci(tmp_path, monkeypatch):
    from arm.lab import store
    monkeypatch.setattr(store, "LAB", tmp_path)
    W = L.record(_res("2026-11-20", ["6199"]), write_file=False)
    assert "2026-W47" in W and not (tmp_path / L.LOG_FILE).exists()
    L.record(_res("2026-11-20", ["6199"]), write_file=True)
    import json
    doc = json.loads((tmp_path / L.LOG_FILE).read_text(encoding="utf-8"))
    assert doc["ver"] == 2 and doc["weeks"]["2026-W47"]["rows"][0][0] == "6199"


def test_lead_box_hidden_outside_correction_and_plain_words():
    from arm.lab import pickpage as PK
    assert PK.lead_box(None) == "" and PK.lead_box(_res("2026-11-20", ["6199"], corr=False)) == ""
    r = _res("2026-11-20", ["6199"])
    r["rows"][0].update(ey=3.0, ry3=1.53, gates=False, st="打底中", piv=None, stop=None, wk=2)
    h = PK.lead_box(r)
    assert 'id="pk-lead"' in h and "6199" in h and "+300%" in h and "連續 2 週" in h and "打底中" in h
    for w in ("建議買", "建議賣", "目標價", "研究", "門檻", "規格", "判定", "→"):
        assert w not in h, w
    assert "沒有一檔" in PK.lead_box(_res("2026-11-20", []))
