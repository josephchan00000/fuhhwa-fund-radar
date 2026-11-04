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
