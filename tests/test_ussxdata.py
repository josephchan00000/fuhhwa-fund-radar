"""美股飆股研究的資料層（arm/lab/ussxdata.py、scripts/backfill_ussx.py；docs/lab_us_sleeve_plan.md 第 8 節）。不連網。"""
from __future__ import annotations

import importlib.util
import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from arm.lab import ussxdata as UD

ROOT = Path(__file__).resolve().parents[1]


def _ts(d: str, hh: int = 13, mm: int = 30) -> int:
    """美東 d hh:mm 的 epoch（夏令 UTC−4）。"""
    y, m, dd = map(int, d.split("-"))
    return int(datetime(y, m, dd, hh + 4, mm, tzinfo=timezone.utc).timestamp())


def _chart(days, closes, *, opens=None, highs=None, lows=None, vols=None, divs=(), splits=(), live=None):
    n = len(days)
    reg = {}
    if live:
        reg = {"start": _ts(live, 9, 30), "end": _ts(live, 16, 0)}
    return {"chart": {"result": [{
        "meta": {"gmtoffset": -14400, "currentTradingPeriod": {"regular": reg}},
        "timestamp": [_ts(d) for d in days],
        "indicators": {"quote": [{
            "open": opens or closes, "high": highs or closes, "low": lows or closes, "close": closes,
            "volume": vols or [1000] * n}]},
        "events": {
            "dividends": {str(_ts(d)): {"amount": a, "date": _ts(d)} for d, a in divs},
            "splits": {str(_ts(d)): {"date": _ts(d), "numerator": n_, "denominator": m_} for d, n_, m_ in splits},
        },
    }]}}


def test_parse_chart_skips_weekend_live_and_missing_close():
    days = ["2024-03-01", "2024-03-02", "2024-03-04", "2024-03-05", "2024-03-06"]   # 五、六、一、二、三
    doc = _chart(days, [10.0, 10.5, None, 11.0, 12.0], opens=[9.8, 10.5, 10.1, None, 11.5],
                 highs=[10.2, 10.6, 10.4, 11.2, 12.4], lows=[9.7, 10.4, 9.9, 10.8, 11.3],
                 vols=[100, 200, 300, None, 500], divs=[("2024-03-05", 0.25)], splits=[("2024-03-01", 2, 1)],
                 live="2024-03-06")
    s = UD.parse_chart(doc, now=_ts("2024-03-06", 11, 0))
    assert s["d"] == ["2024-03-01", "2024-03-05"]          # 週六、收盤空的那天、還在交易的那天都不收
    assert s["c"] == [10.0, 11.0]
    assert s["o"] == [9.8, 11.0]                           # 開盤沒有＝用收盤
    assert s["v"] == [100.0, 0.0]
    assert s["div"] == [["2024-03-05", 0.25]]
    assert s["spl"] == [["2024-03-01", 2.0]]
    assert UD.parse_chart({"chart": {"result": None}}) is None


def test_parse_chart_keeps_high_low_around_close():
    s = UD.parse_chart(_chart(["2024-03-04"], [10.0], highs=[9.5], lows=[10.5]))
    assert s["h"] == [10.0] and s["l"] == [10.0]           # 資料錯（高點比收盤低）時夾回收盤


def test_encode_roundtrip_precision():
    days = ["2020-01-02", "2020-01-03", "2020-01-06", "2020-01-07"]
    c = [123.456, 120.0, 0.0875, 5000.0]
    s = {"d": days, "c": c, "o": [x * 1.01 for x in c], "h": [x * 1.03 for x in c], "l": [x * 0.97 for x in c],
         "v": [0.0, 1.0, 2_500_000.0, 9e9], "div": [["2020-01-06", 0.01]], "spl": [["2020-01-03", 0.1]]}
    rec = UD.enc_px(s, "2026-10-24")
    assert rec["asof"] == "2026-10-24" and rec["d0"] == "2020-01-02" and rec["dd"] == [0, 1, 3, 1]
    p = UD.dec_px(rec)
    assert p["d"] == days and p["div"] == s["div"] and p["spl"] == s["spl"]
    for k in ("c", "o", "h", "l"):
        for a, b in zip(p[k], s[k]):
            assert abs(math.log(a / b)) <= 0.00015            # 1bp 精度（加上四捨五入）
    assert abs(p["v"][0]) < 0.01
    for a, b in zip(p["v"][1:], s["v"][1:]):
        assert abs(math.log1p(a) - math.log1p(b)) <= 0.006   # 量約 1%
    assert UD.dec_px({})["d"] == []


def test_total_return_close_applies_dividend_before_ex_date():
    p = {"d": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-08"], "c": [100.0, 100.0, 99.0, 99.0],
         "div": [["2024-01-04", 1.0], ["2024-01-06", 0.99]]}   # 第二筆落在週六＝算在下一個交易日
    tr = UD.total_return_close(p)
    assert tr[-1] == pytest.approx(99.0)
    assert tr[2] == pytest.approx(99.0 * (1 - 0.99 / 99.0))             # 01-04 在第二次除息之前
    assert tr[1] == pytest.approx(100.0 * 0.99 * (1 - 0.99 / 99.0))      # 01-03 兩次都要乘
    assert tr[1] / tr[0] == pytest.approx(1.0)
    assert tr[2] / tr[1] == pytest.approx(1.0)                           # 除息當天含息報酬＝0


def test_universe_has_calendar_symbols_and_etfs():
    u = UD.universe()
    assert "AAPL" in u and "NVDA" in u
    for e in UD.ETFS:
        assert e in u
    assert len(u) > 4000
    assert all(s == UD.ysym(s) for s in u)


def test_parse_screen():
    doc = {"data": {"rows": [
        {"symbol": "BRK.B", "marketCap": "1,000,000,000", "sector": "Finance", "industry": "Insurance",
         "country": "United States", "ipoyear": ""},
        {"symbol": "XYZ", "marketCap": "", "sector": "", "industry": "", "country": "", "ipoyear": "2021"},
        {"symbol": ""}]}}
    got = UD.parse_screen(doc, "nyse")
    assert got["BRK-B"] == ["nyse", "Finance", "Insurance", "United States", None, 1e9]
    assert got["XYZ"] == ["nyse", "", "", "", 2021, None]
    assert len(got) == 2


@pytest.fixture()
def tmpdata(tmp_path, monkeypatch):
    monkeypatch.setenv("USSX_DIR", str(tmp_path))
    monkeypatch.setattr(UD, "universe", lambda: ["AAA", "BBB", "CCC", "SPY"])
    return tmp_path


def test_backfill_px_writes_and_counts_failures(tmpdata, monkeypatch):
    seen = []

    def fake(sym, now=None):
        seen.append(sym)
        if sym == "BBB":
            return sym, {"d": []}, "404"
        if sym == "CCC":
            return sym, None, "RuntimeError: HTTP 500"
        return sym, {"d": ["2024-01-02"], "c": [10.0], "o": [10.0], "h": [10.0], "l": [10.0], "v": [5.0],
                     "div": [], "spl": []}, "ok"

    monkeypatch.setattr(UD, "fetch_chart", fake)
    st = UD.backfill_px(budget_s=60, workers=1)
    assert st["ok"] == 2 and st["none"] == 1 and st["err"] == 1 and st["left"] == 1
    meta = UD.load_meta()
    assert meta["px_done"] == {"AAA": 1, "BBB": 0, "SPY": 1} and meta["fail"] == {"CCC": 1}
    assert UD.load_px("AAA")["c"] == pytest.approx([10.0], rel=1e-4)          # 1bp 精度
    for _ in range(UD.FAIL_MAX - 1):
        UD.backfill_px(budget_s=60, workers=1)
    assert UD.load_meta()["fail"]["CCC"] == UD.FAIL_MAX
    assert UD.todo_px(UD.load_meta(), UD.universe()) == []        # 失敗三次就放棄
    assert seen.count("AAA") == 1                                  # 抓過的不重抓
    assert "放棄 1 檔" in UD.status() and UD.status().startswith("LEFT")   # 篩選器還沒抓


def test_update_screen_needs_all_exchanges(tmpdata, monkeypatch):
    monkeypatch.setattr(UD, "fetch_screen", lambda: {"AAA": ["nasdaq", "", "", "", None, None]})
    assert UD.update_screen() == 0 and not UD.load_meta().get("screen")
    monkeypatch.setattr(UD, "fetch_screen", lambda: {"AAA": ["nasdaq"] + [""] * 3 + [None, None],
                                                     "BBB": ["nyse"] + [""] * 3 + [None, None],
                                                     "CCC": ["amex"] + [""] * 3 + [None, None]})
    assert UD.update_screen() == 3 and UD.load_meta().get("screen")
    assert UD.update_screen() == 0                                 # 同一天不再抓


def _script():
    spec = importlib.util.spec_from_file_location("backfill_ussx", ROOT / "scripts" / "backfill_ussx.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_status_line_waits_for_sec_only_when_secret_set(tmpdata, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "STUCK", tmpdata / "stuck.txt")
    meta = {"px_done": {s: 1 for s in UD.universe()}, "fail": {}, "screen": "2026-10-24"}
    UD.save_meta(meta)
    monkeypatch.delenv("SEC_CONTACT_EMAIL", raising=False)
    assert mod.line().startswith("DONE")
    monkeypatch.setenv("SEC_CONTACT_EMAIL", "someone@example.com")
    out = mod.line()
    assert out.startswith("LEFT") and "someone@example.com" not in out
    (tmpdata / "stuck.txt").write_text("股價一檔都抓不到\n", encoding="utf-8")
    assert mod.line().startswith("STUCK")


def test_workflow_mode_only_on_data_branch_and_secret_from_secrets():
    y = (ROOT / ".github" / "workflows" / "lab_backfill.yml").read_text(encoding="utf-8")
    i = y.index('"${MODE#ussxfill}"')
    block = y[i:y.index("elif", i + 30)]
    assert 'github.ref_name }}" != "claude/ussx-data"' in block and "exit 1" in block
    assert "scripts/backfill_ussx.py --budget-min" in block and "git add -f data/lab/ussx" in block
    assert "mode=ussxfill" in block
    assert "SEC_CONTACT_EMAIL: ${{ secrets.SEC_CONTACT_EMAIL }}" in y


def test_merge_px_appends_recent_and_detects_new_splits():
    old = {"asof": "2026-10-23", "d": ["2026-10-20", "2026-10-21", "2026-10-22"], "c": [10.0, 11.0, 12.0],
           "o": [10.0, 11.0, 12.0], "h": [10.0, 11.0, 12.0], "l": [10.0, 11.0, 12.0], "v": [1.0, 2.0, 3.0],
           "div": [["2026-10-21", 0.1]], "spl": []}
    new = {"d": ["2026-10-22", "2026-10-23", "2026-10-26"], "c": [12.05, 13.0, 14.0], "o": [12.0, 13.0, 14.0],
           "h": [12.1, 13.0, 14.0], "l": [11.9, 13.0, 14.0], "v": [3.0, 4.0, 5.0], "div": [["2026-10-26", 0.2]], "spl": []}
    m = UD.merge_px(old, new)
    assert m["d"] == ["2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26"]
    assert m["c"] == [10.0, 11.0, 12.05, 13.0, 14.0]                    # 重疊的日子用新的
    assert m["div"] == [["2026-10-21", 0.1], ["2026-10-26", 0.2]]
    assert UD.merge_px(old, {**new, "spl": [["2026-10-26", 2.0]]}) is None    # 抓完以後才分割 → 整段重抓
    assert UD.merge_px(old, {**new, "c": [6.0, 6.5, 7.0]}) is None            # 重疊的日子對不上 → 整段重抓
    assert UD.merge_px(old, {"d": []}) is old                                 # 查不到（下市）→ 原封不動


def test_update_recent_keeps_delisted_and_refetches_on_split(tmpdata, monkeypatch):
    def put(sym, closes):
        s = {"d": ["2026-10-20", "2026-10-21", "2026-10-22"], "c": closes, "o": closes, "h": closes, "l": closes,
             "v": [1.0, 1.0, 1.0], "div": [], "spl": []}
        UD._write(UD.px_path(sym), UD.enc_px(s, "2026-10-23"))
    for s_ in ("AAA", "BBB", "CCC"):
        put(s_, [10.0, 10.0, 10.0])
    UD.save_meta({"px_done": {"AAA": 3, "BBB": 3, "CCC": 3, "SPY": 0}, "fail": {}, "screen": "2026-10-23"})

    def since(sym, start, now=None):
        if sym == "AAA":
            return sym, {"d": ["2026-10-22", "2026-10-23"], "c": [10.0, 11.0], "o": [10.0, 11.0], "h": [10.0, 11.0],
                         "l": [10.0, 11.0], "v": [1.0, 1.0], "div": [], "spl": []}, "ok"
        if sym == "BBB":
            return sym, {"d": []}, "404"
        return sym, {"d": ["2026-10-23"], "c": [5.0], "o": [5.0], "h": [5.0], "l": [5.0], "v": [2.0], "div": [],
                     "spl": [["2026-10-23", 2.0]]}, "ok"

    def full(sym, now=None):
        return sym, {"d": ["2026-10-22", "2026-10-23"], "c": [5.0, 5.0], "o": [5.0, 5.0], "h": [5.0, 5.0], "l": [5.0, 5.0],
                     "v": [2.0, 2.0], "div": [], "spl": [["2026-10-23", 2.0]]}, "ok"
    monkeypatch.setattr(UD, "fetch_since", since)
    monkeypatch.setattr(UD, "fetch_chart", full)
    st = UD.update_recent(budget_s=60, workers=1)
    assert st["ok"] == 1 and st["same"] == 1 and st["full"] == 1 and st["err"] == 0
    assert UD.load_px("AAA")["d"][-1] == "2026-10-23"
    assert UD.load_px("BBB")["d"] == ["2026-10-20", "2026-10-21", "2026-10-22"]           # 下市的留著
    assert UD.load_px("CCC")["spl"] == [["2026-10-23", 2.0]] and len(UD.load_px("CCC")["d"]) == 2
    assert UD.load_meta()["updated"]


def test_weekly_workflow_targets_data_branch_only():
    y = (ROOT / ".github" / "workflows" / "ussx_weekly.yml").read_text(encoding="utf-8")
    assert "cron: '5 2 * * 6'" in y and "ref: claude/ussx-data" in y
    assert "git push origin HEAD:claude/ussx-data" in y and "scripts/backfill_ussx.py --weekly" in y
    assert "SEC_CONTACT_EMAIL: ${{ secrets.SEC_CONTACT_EMAIL }}" in y
    assert "main" not in y.split("on:")[1].split("jobs:")[0]                  # 不推 main
