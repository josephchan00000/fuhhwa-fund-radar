"""今年逐月、逐筆表（ytdspec VER 1；docs/lab_review_plan.md 第 9.2 節）：每月報酬、上線後的紀錄、頁面用字、美股做法名稱。"""
import json
import re

import pytest

from arm.lab import cfgpage as CF
from arm.lab import ussxgrid as G
from arm.lab import ytd
from arm.lab import ytdspec as S
from tests.test_plain import METHOD, NOT_PLAIN, STATUS


def test_month_rows_month_and_cumulative():
    days = ["2025-12-31", "2026-01-02", "2026-01-30", "2026-02-02", "2026-02-27", "2026-03-02"]
    nav = [1.0, 1.01, 1.10, 1.12, 1.21, 1.20]
    rows = ytd.month_rows(days, {"a": nav, "b": [None, None, None, None, 1.0, 1.05]})
    assert [r["m"] for r in rows] == [1, 2, 3]
    jan, feb, mar = rows
    assert jan["a"][0] == pytest.approx(0.10) and jan["a"][1] == pytest.approx(0.10)
    assert feb["a"][0] == pytest.approx(1.21 / 1.10 - 1) and feb["a"][1] == pytest.approx(0.21)
    assert mar["a"][0] == pytest.approx(1.20 / 1.21 - 1)
    assert jan["full"] and feb["full"]
    assert mar["to"] == "2026-03-02" and not mar["full"]           # 這個月還沒走完
    assert jan["b"] is None and feb["b"][0] is None                 # 上線以前沒有值；上線那個月沒有月初值


def test_weights_of_adds_long_hold_and_skips_pending():
    pos = {"2330": [{"w": 0.03, "h": 1}, {"w": 0.01, "h": 0}], "3189": [{"w": 0.02, "h": 0}]}
    assert ytd.weights_of(pos, 0.2) == {"2330": 0.03, "0050": 0.2}


def test_record_tw_only_in_ci(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(ytd, "load_live", lambda: {"ver": S.VER, "tw": {}})
    p = tmp_path / "live.json"
    pos = {"2330": [{"w": 0.05, "h": 1}]}
    assert not ytd.record_tw("2026-10-28", pos, 0.2, path=p)
    assert not p.exists()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert not ytd.record_tw("2026-10-20", pos, 0.2, path=p)       # 上線以前不記
    assert ytd.record_tw("2026-10-28", pos, 0.2, path=p)
    doc = json.loads(p.read_text())
    assert doc == {"ver": S.VER, "tw": {"2026-10-28": {"0050": 0.2, "2330": 0.05}}}


def test_live_tw_starts_at_first_record(monkeypatch):
    days = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]
    px = {"0050": [None, 100.0, 101.0, 99.0], "2330": [None, 50.0, 55.0, 55.0]}
    monkeypatch.setattr(ytd, "_adj_closes", lambda D, codes, ds: {c: px[c][-len(ds):] for c in codes})
    live = {"tw": {"2026-10-27": {"0050": 0.5}, "2026-10-28": {"0050": 0.5, "2330": 0.5}}}
    out = ytd.live_tw(None, live, days)
    assert list(out) == ["2026-10-27", "2026-10-28", "2026-10-29"]
    assert out["2026-10-27"] == 1.0
    assert out["2026-10-28"] == pytest.approx(1 + 0.5 * 0.01)        # 10/27 收盤的持股：只有 0050 一半
    assert out["2026-10-29"] == pytest.approx((1 + 0.5 * 0.01) * (1 + 0.5 * (99 / 101 - 1)))
    assert ytd.live_tw(None, {"tw": {}}, days) == {}


def _plain(text: str) -> list[str]:
    t = re.sub(r"<[^>]+>", " ", text)
    return [w for w in METHOD + STATUS + NOT_PLAIN if w in t]


def _row(m, a, b, c):
    return {"m": m, "to": f"2026-{m:02d}-28", "full": True, "nolook": a, "hold": b, "live": c}


def test_ytd_html_tw_plain_words():
    Y = {"mk": "tw", "days": ["2025-12-31", "2026-10-28"], "w": S.TW_W, "live_from": "2026-10-27", "take": "2026-10-22",
         "rows": [_row(1, [0.05, 0.05], [0.03, 0.03], None), _row(10, [0.02, 0.4], [0.01, 0.3], [0.004, 0.004])],
         "tot": {"nolook": 0.4, "hold": 0.3, "live": 0.004},
         "trades": [{"k": "0050", "c": "0050", "n": "元大台灣50", "ent": "2025-12-31", "exit": None, "ret": 0.3, "w": 0.2, "pnl": 0.06},
                    {"k": "R60", "c": "2408", "n": "南亞科", "ent": "2025-10-13", "exit": "2026-01-09", "ret": 1.48, "bpx": 93.55,
                     "spx": 232.88, "w": 0.09, "pnl": 0.018},
                    {"k": "R60", "c": "3189", "n": "景碩", "ent": "2026-07-27", "exit": None, "ret": 0.2, "w": 0.05, "pnl": 0.01}]}
    h = CF.ytd_html(Y, "tw")
    assert not _plain(h)
    assert "不偷看" in h and "一直抱著" in h and "上線後" in h and "今年每一筆（3 筆）" in h
    assert 'data-m=",1,2,3,4,5,6,7,8,9,10,"' in h                 # 去年就拿著、還拿著＝整年
    assert 'data-m=",1,"' in h and 'data-m=",7,8,9,10,"' in h
    assert "10/27 起" in h


def test_ytd_html_us_plain_words_and_missing():
    Y = {"mk": "us", "days": ["2025-12-31", "2026-10-23"], "L": 5, "k": 3, "rank": 13, "live_from": "2026-10-23",
         "data_last": "2026-10-23", "picks": ["強勢｜50日線（最多一年）｜5檔｜不看大盤"],
         "range": {"min": -0.1, "med": 0.2, "max": 0.5},
         "rows": [_row(1, [0.05, 0.05], [0.02, 0.02], None)], "tot": {"nolook": 0.2, "hold": 0.15, "live": 0.0},
         "trades": [{"k": "強勢", "m": "強勢｜50日線（最多一年）｜5檔｜不看大盤", "c": "MU", "nm": "Micron Technology",
                     "ent": "2026-03-30", "exit": None, "ret": 0.8, "w": 0.06, "pnl": 0.05}]}
    h = CF.ytd_html(Y, "us")
    assert not _plain(h)
    assert "Micron Technology" in h and "MU" in h and "第 13 名" in h
    assert "還沒算出來" in CF.ytd_html(None, "us")


def test_grid_names_and_parse():
    N = G.names()
    assert len(N["全部"]) == S.n_grid() == 2016 and len(set(N["全部"])) == 2016
    assert len(N["不換股"]) + len(N["每週換股"]) == 2016
    for nm in N["全部"][::97]:
        p = G.parse(nm)
        assert p["sel"] in S.US_SELS and p["n"] in S.US_NS and p["reg"] in S.US_REG
        assert (p["exit"] in S.US_EXITS_ROT) == p["rot"]
    assert G.parse("強勢｜50日線（最多一年）｜5檔｜不看大盤") == {"sel": "強勢", "n": 5, "reg": "不看大盤", "rot": False,
                                                            "exit": "50日線（最多一年）"}


def test_page_does_not_embed_ytd_data():
    import inspect
    from arm.lab import page
    src = inspect.getsource(page.render)
    assert '"ytd"' in src and '"ytd_day"' in src                   # 表已組成 HTML，資料不再內嵌一份
