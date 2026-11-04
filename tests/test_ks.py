"""策略熔斷（arm/lab/ks.py）：門檻從回測淨值與大盤算、只用 SPEC_DATE 以前、同版本不覆蓋。手寫小數列，不碰任何策略的成績。"""
import pytest

from arm.lab import ks
from arm.lab import ksspec as K


def test_bounds_of_uses_relative_lag_and_stops_at_spec_date():
    d = ["2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-11-05"]
    nav = [100, 90, 99, 110, 1]                     # 11/05 在規格日之後：不算
    bench = {"2026-01-01": 10, "2026-01-02": 10, "2026-01-05": 11, "2026-01-06": 10, "2026-11-05": 10}
    b = ks.bounds_of(d, nav, bench)
    assert b["n"] == 4 and b["b"] == "2026-01-06"
    assert b["dd_bt"] == pytest.approx(0.1) and b["dd"] == pytest.approx(0.15)     # 1/02 落後 10%（1/05 雖然漲但大盤漲更多也是 10%）
    assert b["dd_at"][0] == "2026-01-01" and b["uw_bt"] == 2 and b["uw"] == 3
    assert ks.bounds_of(d[:1], nav[:1], bench) == {}


def test_save_bounds_locks_numbers_for_the_same_spec_version(tmp_path, monkeypatch):
    from arm.lab import store
    monkeypatch.setattr(store, "LAB", tmp_path, raising=False)
    saved = {}
    monkeypatch.setattr(store, "read_json", lambda name, default=None: saved.get(name, default))
    monkeypatch.setattr(store, "write_json", lambda name, doc: saved.__setitem__(name, doc) or True)
    ks.save_bounds({"tw_boom": {"dd": 0.3, "uw": 10}}, "2026-11-04")
    ks.save_bounds({"tw_boom": {"dd": 0.9, "uw": 99}, "tw_v3l": {"dd": 0.2, "uw": 5}}, "2026-11-05")
    sl = saved[K.BOUNDS_FILE]["slices"]
    assert sl["tw_boom"]["dd"] == 0.3 and sl["tw_boom"]["made"] == "2026-11-04"          # 同版本不覆蓋
    assert sl["tw_v3l"]["dd"] == 0.2 and sl["tw_v3l"]["src"] == K.BT_SRC["tw_v3l"] and sl["tw_v3l"]["ver"] == K.VER


# ── 前瞻：狀態、推播、頁面（手寫小數列）────────────────────────────────────────

BD = {"dd": 0.3, "uw": 100, "dd_bt": 0.2, "uw_bt": 66}


def _ser(rel):
    ds = [f"2026-11-{i + 1:02d}" for i in range(len(rel))]
    return ds, [r * 100 for r in rel], [100.0] * len(rel)


def test_status_pause_need_and_resume_restarts_measuring():
    st = ks.status(*_ser([1.0, 0.9, 0.69, 0.6]), BD)
    assert st["st"] == "pause" and st["trig"] == {"d": "2026-11-03", "lag": pytest.approx(0.31)}
    assert st["need"] == pytest.approx(0.69 / 0.6 - 1) and st["ev"] == [["2026-11-03", "pause"]]
    st = ks.status(*_ser([1.0, 0.9, 0.69, 0.6, 0.7, 0.65]), BD)
    assert st["st"] == "on" and st["ev"][-1] == ["2026-11-05", "resume"]
    assert st["lag"] == pytest.approx(1 - 0.65 / 0.7) and st["uw"] == 1                 # 恢復那天（0.7）起重新量
    st = ks.status(*_ser([1.0] + [0.99] * 3), {**BD, "uw": 2})
    assert st["st"] == "on" and st["slow"] and st["ev"] == [["2026-11-04", "slow"]]


def test_live_series_boom_starts_at_the_base_row(monkeypatch):
    from arm.lab import store
    nav = {"2026-10-22": [100] * 7, "2026-10-27": [0, 0, 0, 98, 0, 101, 0], "2026-10-28": [0, 0, 0, 97, 0, 99, 0]}
    monkeypatch.setattr(store, "read_json", lambda name, default=None: {"nav": nav} if name == "sxlive.json" else default)
    ds, s, b = ks.live_series("tw_boom")
    assert ds == ["2026-10-22", "2026-10-27", "2026-10-28"] and s == [100, 101, 99] and b == [100, 98, 97]


def test_valog_push_line_only_for_new_events_and_buys_held():
    from arm.lab import valog as V
    cur = {"tw_boom": {"st": "pause", "lag": 0.5, "dd": 0.488, "uw": 3, "uwb": 522, "uw_bt": 348, "d": "2026-11-05",
                       "ev": ["2026-11-05", "pause"], "trig": 0.5}}
    line = V.ks_line(cur, {})
    assert line.startswith("策略熔斷：台股新飆股落後大盤 50.0%，超過熔斷邊界 48.8%，暫停") and "自動買回" in line
    assert V.ks_line(cur, cur) is None                                                # 同一個事件不重推
    rec = {"ks": cur, "boom": {"td": [["11/06", "賣", "A"], ["11/06", "買", "B"]]},
           "todo": {"items": [{"k": "v3l", "act": "買進"}, {"k": "s3", "act": "買進"}]}}
    V.ks_hold(rec)
    assert rec["boom"]["td"] == [["11/06", "賣", "A"]] and len(rec["todo"]["items"]) == 2  # 財報驚喜沒暫停：照舊
    rec["ks"]["tw_v3l"] = {"st": "pause"}
    V.ks_hold(rec)
    assert rec["todo"]["items"] == [{"k": "s3", "act": "買進"}]
    assert "策略熔斷" in "".join(V.push_lines({"todo": {}, "ksl": line}))


def test_plan_block_and_pick_banner():
    from arm.lab import cfgpage as CF
    from arm.lab import pickpage as PK
    live = {"slices": {"tw_boom": {"st": "on", "lag": 0.026, "dd": 0.488, "uw": 1, "slow": False},
                       "tw_v3l": {"st": "pause", "lag": 0.6, "dd": 0.691, "trig": {"d": "2026-11-05", "lag": 0.70}, "need": 0.12}}}
    h = CF.ks_html("tw", None, live)
    assert "台股新飆股" in h and "落後大盤 2.6%" in h and "48.8% 以上暫停" in h and "暫停中" in h
    assert "11/5 收盤落後 70.0%" in h and "多賺 12.0%" in h and 'class="cfwr on"' in h
    assert CF.ks_html("us", None, live) == ""                                         # 美股沒換成強勢品質股：不放
    b = PK.halt_note("v3l", live)
    assert "暫停中" in b and "11/5 收盤" in b and "70.0%" in b and "69.1%" in b and "買進先不做" in b
    assert PK.halt_note("boom", live) == "" and PK.halt_note("qm", {}) == ""
