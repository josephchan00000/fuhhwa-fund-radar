"""台股官方休市表（arm/twholidays，2026-10-13）：交易日判定改以證交所官方表為準。

起因：盤查發現看門狗與鮮度判定都讀「子代理寫的行事曆市況段」決定今天有沒有開——
2026-10-05～08 四天的市況寫「台股 正常交易」，同週 10/09 國慶補假其實休市（今日重點 chip 因此
連四天告訴讀者「本週無休市」）。這裡守：官方表解析、種子正確、覆蓋期限、消費端以官方為準。"""
import importlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from arm import clock, twholidays, usnews  # noqa: E402

_API_ROWS = [
    {"Name": "國慶日", "Date": "1151010", "Weekday": "六", "Description": "依規定放假1日。"},
    {"Name": "國慶日（補假）", "Date": "1151009", "Weekday": "五", "Description": "依規定補假1日。"},
    {"Name": "農曆春節前最後交易日", "Date": "1150211", "Weekday": "三", "Description": "最後交易日。"},
    {"Name": "農曆春節前", "Date": "1150212", "Weekday": "四", "Description": "市場無交易，僅辦理結算交割作業。"},
    {"Name": "農曆春節後開始交易日", "Date": "1150223", "Weekday": "一", "Description": "開始交易。"},
]


def test_parse_api_keeps_only_no_trade_weekdays():
    got = twholidays.parse_api(_API_ROWS)
    assert set(got) == {"2026-10-09", "2026-02-12"}   # 週末列、最後／開始交易日都不是平日休市
    assert got["2026-10-09"] == "國慶日（補假）"
    assert twholidays.parse_api({"not": "a list"}) == {}


def test_seed_2026_matches_twse_trading_day_count():
    # 證交所公告 2026 全年 243 個交易日；平日 261 天 − 18 天休市＝243（兩來源核對＋總數自洽）
    seed = twholidays.SEED[2026]
    assert all(date.fromisoformat(k).weekday() < 5 for k in seed)
    weekdays = sum(1 for n in range(365) if (date(2026, 1, 1) + timedelta(n)).weekday() < 5)
    assert weekdays - len(seed) == 243
    assert {"2026-10-26", "2026-12-25"} <= set(seed)    # 盤查當時最近的兩個休市日


def test_load_prefers_official_file_but_rejects_truncated(tmp_path, monkeypatch):
    p = tmp_path / "tw_holidays.json"
    monkeypatch.setattr(twholidays, "PATH", p)
    p.write_text(json.dumps({"years": {"2026": {"2026-01-01": "x"}}}), encoding="utf-8")
    assert twholidays.load()[2026] == twholidays.SEED[2026]      # 半截（<5 天）不採信、留種子
    full = {f"2027-0{m}-0{d}": "y" for m, d in ((1, 1), (2, 8), (2, 9), (2, 10), (2, 11))}
    p.write_text(json.dumps({"years": {"2027": full}}), encoding="utf-8")
    yrs = twholidays.load()
    assert yrs[2027] == full and 2026 in yrs                     # 官方新年份加入、種子年份保留
    assert twholidays.is_closed(date(2027, 2, 8), yrs) is True
    assert twholidays.is_closed(date(2028, 2, 8), yrs) is None   # 未涵蓋＝交給呼叫端後備


def test_fetch_and_save_is_fail_open(tmp_path, monkeypatch):
    from arm import http
    p = tmp_path / "tw_holidays.json"
    monkeypatch.setattr(twholidays, "PATH", p)
    logs = []
    monkeypatch.setattr(http, "get_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("403")))
    assert twholidays.fetch_and_save(log=logs.append) is False and not p.exists()
    assert "403" in logs[-1]                                     # 失敗原因要印出來，不吞
    monkeypatch.setattr(http, "get_json", lambda *a, **k: _API_ROWS)   # 只解析出 2 天 → 不採信
    assert twholidays.fetch_and_save(log=logs.append) is False and not p.exists()
    rows = [{"Name": n, "Date": f"115{k[5:7]}{k[8:10]}", "Weekday": "", "Description": ""}
            for k, n in twholidays.SEED[2026].items()]
    monkeypatch.setattr(http, "get_json", lambda *a, **k: rows)
    assert twholidays.fetch_and_save(log=logs.append) is True
    assert json.loads(p.read_text(encoding="utf-8"))["years"]["2026"] == twholidays.SEED[2026]


def test_watchdog_trading_day_follows_official_table():
    fresh = importlib.import_module("check_afterhours_fresh")
    normal = "> 更新：…；市況：台股 正常交易｜美股 正常交易；本週焦點：…"
    wrong = "> 更新：…；市況：台股 10/13 因颱風休市｜美股 正常交易"
    assert fresh.is_trading_day(date(2026, 10, 26), normal) is False   # 漏寫休市 → 仍判休市（不誤報）
    assert fresh.is_trading_day(date(2026, 10, 13), wrong) is True     # 誤寫休市 → 仍判交易（不靜默）
    assert fresh.is_trading_day(date(2026, 10, 13), None) is True
    # 官方表未涵蓋的年份才退回文字（市況寫了日期就只認那一天）
    assert fresh.is_trading_day(date(2030, 3, 5), "> 市況：台股 3/5 因颱風休市｜美股 正常交易") is False
    assert fresh.is_trading_day(date(2030, 3, 5), wrong) is True       # 預告別天休市 → 今天照常交易


def test_dashboard_closed_days_use_official_table():
    from arm import fund_dashboard as fd
    closed = fd._tw_closed_days()
    assert date(2026, 10, 26) in closed and date(2026, 12, 25) in closed  # 行事曆還沒寫到也算得出來
    assert date(2026, 10, 10) not in closed                               # 行事曆把週末寫成休市不入表


def test_holiday_tables_cover_next_45_days():
    # 年度表會「到期」：只涵蓋今年時，跨年後提示包與看門狗會靜默退化。提早 45 天變紅＝逼補下一年。
    # 證交所隔年表公告前，人事行政總處辦公日曆的暫代層可先頂著（下一支測試逼它在 12/1 前換正）。
    horizon = clock.today_tw() + timedelta(days=45)
    assert twholidays.covers_partly(horizon), \
        f"台股休市表未涵蓋 {horizon.year}——依人事行政總處辦公日曆補 PROVISIONAL，或證交所公告後補 SEED"
    assert horizon.year in {d.year for d in usnews._US_MKT_HOLIDAYS}, \
        f"美股休市表未涵蓋 {horizon.year}——依 NYSE 公告補 _US_MKT_HOLIDAYS"


def test_calendar_anchor_lists_official_tw_holidays():
    a = usnews.calendar_anchor(date(2026, 10, 20))
    assert "10/26（週一）" in a and "證交所官方表" in a
    assert "台股近 10 日無休市日" in usnews.calendar_anchor(date(2026, 10, 13))
    assert "鄰近美股休市日" in usnews.calendar_anchor(date(2027, 1, 18))   # 2027 美股表已補


def test_check_reports_holiday_gate():
    check = importlib.import_module("check_reports")
    head = "# 本週重點財經行事曆（10/26–10/30）\n> 更新：2026/10/26；市況：台股 {tw}｜美股 正常交易；本週焦點：…\n"
    ok = head.format(tw="10/26 因光復節補假休市")
    assert check._check_calendar_holidays(ok, "c.md", "2026-10-26") == []
    missed = head.format(tw="正常交易")
    assert any("10/26 台股休市" in e for e in check._check_calendar_holidays(missed, "c.md", "2026-10-26"))
    wrong = "# 本週重點財經行事曆（10/12–10/16）\n> 更新：2026/10/13；市況：台股 10/14 因颱風休市｜美股 正常交易\n"
    assert any("官方表該日為交易日" in e for e in check._check_calendar_holidays(wrong, "c.md", "2026-10-13"))
    future = "# 本週重點財經行事曆（03/04–03/08）\n> 更新：2030/03/04；市況：台股 正常交易\n"
    assert check._check_calendar_holidays(future, "c.md", "2030-03-04") == []   # 未涵蓋年份 fail-open


def test_provisional_2027_is_self_consistent():
    # 人事行政總處 116 年辦公日曆：全年放假 121 天、無補行上班日 → 週末 104＋平日 17
    prov = twholidays.PROVISIONAL[2027]
    assert all(date.fromisoformat(k).weekday() < 5 for k in prov)
    weekend = sum(1 for n in range(365) if (date(2027, 1, 1) + timedelta(n)).weekday() >= 5)
    assert weekend + len(prov) == 121


def test_provisional_year_replaced_before_december():
    # 暫代層只知道「一定休市」的日子，證交所另加的（春節前無交易僅結算）要等它公告。
    # 證交所 2026 年表是 2025-10-29 公告——到隔年前一年 12/1 還沒換正就紅。
    today = clock.today_tw()
    for y in twholidays.provisional():
        assert today < date(y - 1, 12, 1), (
            f"證交所 {y} 年休市表應已公告：確認 CI 落檔 data/tw_holidays.json 有 {y}；"
            f"官方 API 不含隔年就依證交所公告補進 SEED[{y}]")


def test_provisional_layer_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr(twholidays, "PATH", tmp_path / "none.json")      # 只有種子＋暫代層
    assert twholidays.is_closed(date(2027, 2, 5)) is True                # 辦公日曆放假日＝一定休市
    assert twholidays.is_closed(date(2027, 2, 6)) is True                # 週末
    assert twholidays.is_closed(date(2027, 2, 2)) is None                # 證交所可能另加 → 不猜
    assert not twholidays.covers(date(2027, 3, 1)) and twholidays.covers_partly(date(2027, 3, 1))
    fresh = importlib.import_module("check_afterhours_fresh")
    assert fresh.is_trading_day(date(2027, 2, 5), "> 市況：台股 正常交易") is False
    assert fresh.is_trading_day(date(2027, 2, 2), "> 市況：台股 2/2–2/3 因春節前休市") is False   # 未知 → 退回文字
    assert fresh.is_trading_day(date(2027, 2, 2), "> 市況：台股 正常交易") is True
    # 證交所表一到即整年取代暫代層（含證交所另加的日子）
    official = {f"2027-{k}": "x" for k in ("01-01", "02-02", "02-03", "02-04", "02-05", "02-08")}
    (tmp_path / "none.json").write_text(json.dumps({"years": {"2027": official}}), encoding="utf-8")
    assert twholidays.is_closed(date(2027, 2, 2)) is True
    assert twholidays.is_closed(date(2027, 4, 30)) is False                # 只信證交所表
    assert twholidays.provisional() == {}


def test_prompt_and_gate_mark_provisional_days(tmp_path, monkeypatch):
    monkeypatch.setattr(twholidays, "PATH", tmp_path / "none.json")
    a = usnews.calendar_anchor(date(2026, 12, 28))
    assert "01/01（週五）開國紀念日＊" in a and "人事行政總處" in a
    check = importlib.import_module("check_reports")
    head = "# 本週重點財經行事曆（02/01–02/05）\n> 更新：2027/02/01；市況：台股 {tw}｜美股 正常交易；本週焦點：…\n"
    ok = head.format(tw="2/2–2/5 因春節休市")
    assert check._check_calendar_holidays(ok, "c.md", "2027-02-01") == []
    missed = head.format(tw="正常交易")
    errs = check._check_calendar_holidays(missed, "c.md", "2027-02-01")
    assert len(errs) == 2 and all("人事行政總處" in e for e in errs)   # 2/4、2/5；2/2 未知不驗
