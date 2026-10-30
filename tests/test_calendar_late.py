"""行事曆「待更新」與週末「上週結果」（2026-10-30 使用者：「總經的行事曆有資料沒更新到」）。

10/30 那份有 6 列日期已過、狀態仍「未公布」（9 月景氣燈號 41 分紅燈 CI 凌晨就從國發會抓進專案了）；
週末版只寫下一週，10/17、10/24 兩份都沒有上週五的列（非農、日本 CPI 的結果從沒上過網頁）。
這裡守：結束日早於今天＝待更新（多日會議看結束日、跨年推對年份）、週末版的上週列收合在最下面、
上週列不算進列數上限、週末版沒帶齊上週列要擋、提示包週末才帶上週最後一版。"""
import importlib
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from arm import fund_dashboard as fd  # noqa: E402
from arm import macronews, printview  # noqa: E402

_ROW = "| {d} | {item} | — | {a} | — | {st} |"


def _cal(title: str, upd: str, rows: list[str], notes: str = "") -> str:
    return (f"# 本週重點財經行事曆（{title}）\n> 更新：{upd}；市況：台股 正常交易\n\n"
            "| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n"
            + "\n".join(rows) + "\n\n註：\n" + notes)


def test_row_end_date_ranges_and_year():
    ref = date(2026, 10, 30)
    assert macronews.row_end_date({"date": "10/29", "item": "美：初領失業金"}, ref) == date(2026, 10, 29)
    assert macronews.row_end_date({"date": "09/17–18", "item": "日銀會議"}, ref) == date(2026, 9, 18)
    # 項目文字寫了從同一天開始的區間：多日會議開完才有結果
    assert macronews.row_end_date({"date": "10/26", "item": "二十屆五中全會（10/26–10/29）"}, ref) == date(2026, 10, 29)
    assert macronews.row_end_date({"date": "10/26", "item": "峰會（10/27–10/28）"}, ref) == date(2026, 10, 26)
    assert macronews.row_end_date({"date": "01/02", "item": ""}, date(2026, 12, 31)) == date(2027, 1, 2)
    assert macronews.row_end_date({"date": "12/30", "item": ""}, date(2027, 1, 2)) == date(2026, 12, 30)
    assert macronews.row_end_date({"date": "—", "item": ""}, ref) is None


def test_is_late_only_past_and_unpublished():
    ref = today = date(2026, 10, 30)
    late = {"date": "10/28", "item": "台：9月景氣對策信號", "status": "未公布"}
    assert macronews.is_late(late, ref, today)
    assert not macronews.is_late({**late, "status": "已公布"}, ref, today)
    assert not macronews.is_late({**late, "status": "休市"}, ref, today)
    assert not macronews.is_late({**late, "date": "10/30"}, ref, today)      # 今天的：還不知道幾點公布，不判
    assert not macronews.is_late({**late, "date": "10/26", "item": "五中全會（10/26–10/30）"}, ref, today)


def test_week_split_keeps_last_week_rows_apart():
    md = _cal("11/02–11/06", "2026/10/31", [
        _ROW.format(d="11/04", item="美：FOMC", a="—", st="未公布"),
        _ROW.format(d="10/30", item="日：日銀利率決議", a="維持0.75%", st="已公布"),
    ])
    rows = macronews._parse_cal_rows(md)
    cur, prev = macronews.week_split(rows, macronews.cal_week_start(md, date(2026, 10, 31)), date(2026, 10, 31))
    assert [r["item"] for r in cur] == ["FOMC"] and [r["item"] for r in prev] == ["日銀利率決議"]
    assert macronews.week_split(rows, None, date(2026, 10, 31)) == (rows, [])


def _view_cal():
    return {"date": "2026-10-31", "week_start": date(2026, 11, 2),
            "rows": [{"date": "11/04", "item": "FOMC", "region": "美", "cons": "—", "actual": "—", "prev": "—", "status": "未公布"}],
            "prev_rows": [{"date": "10/30", "item": "第三季就業成本指數ECI", "region": "美", "cons": "—", "actual": "—",
                           "prev": "—", "status": "未公布"},
                          {"date": "10/30", "item": "第三季GDP概估", "region": "台", "cons": "—", "actual": "+7.6%",
                           "prev": "—", "status": "已公布"}],
            "note": "", "title": ""}


def test_dashboard_marks_late_and_collapses_last_week():
    cal = _view_cal()
    html = fd._macro_cal_view(cal, {}, date(2026, 10, 31))
    i = html.index('<details class="calprev">')
    assert "<details class=\"calprev\" open" not in html                     # 預設收合
    assert html.index("FOMC") < i                                            # 上週結果放在最下面
    assert "上週結果（10/26–10/30）・2 項" in html and "1 項待更新" in html
    assert html.count("⚠ 待更新") == 1 and 'class="creg tw"' in html        # 混排表台灣列也掛小徽章
    assert fd.cal_late_count(cal, date(2026, 10, 31)) == 1
    assert "⚠ 1 項待更新" in fd._cal_late_chip(1) and fd._cal_late_chip(0) == ""
    # 沒給今天（舊呼叫方式）：照舊只分已公布／未公布／休市
    assert "⚠ 待更新" not in fd._macro_cal_view(cal, {})
    assert fd.cal_late_count(cal) == 0


def test_print_marks_late_and_prints_this_week_only():
    cal = {**_view_cal(), "date": "2026-11-05",
           "rows": [{"date": "11/04", "item": "FOMC", "region": "美", "cons": "—", "actual": "—", "prev": "—", "status": "未公布"}]}
    html = printview.calendar_block(cal, {}, date(2026, 11, 5))
    assert 'class="pr-st late">待更新' in html and "就業成本指數" not in html
    assert "待更新" not in printview.calendar_block(cal, {})


def test_slim_limits_count_this_week_only(tmp_path, monkeypatch):
    check = importlib.import_module("check_reports")
    this_week = [_ROW.format(d="11/0" + str(2 + i % 5), item=f"美：數據{i}", a="—", st="未公布") for i in range(30)]
    last_week = [_ROW.format(d="10/30", item=f"美：上週{i}", a="—", st="未公布") for i in range(5)]
    md = _cal("11/02–11/06", "2026/10/31", this_week + last_week, "- 台：本週無台灣重點經濟數據\n")
    assert not any("超過" in e for e in check._check_calendar_slim(md, "c.md", "2026-10-31"))
    md31 = _cal("11/02–11/06", "2026/10/31", this_week + [_ROW.format(d="11/06", item="美：多一列", a="—", st="未公布")],
                "- 台：本週無台灣重點經濟數據\n")
    assert any("31 列超過" in e for e in check._check_calendar_slim(md31, "c.md", "2026-10-31"))


def test_weekend_gate_requires_last_week_rows(tmp_path, monkeypatch):
    check = importlib.import_module("check_reports")
    mc = tmp_path / "reports" / "macrocal"
    mc.mkdir(parents=True)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    (mc / "2026-10-30.md").write_text(_cal("10/26–10/30", "2026/10/30", [
        _ROW.format(d="10/28", item="台：9月景氣對策信號", a="—", st="未公布"),
        _ROW.format(d="10/29", item="美：第三季GDP初估", a="+3.4%", st="已公布"),
        _ROW.format(d="10/30", item="日：日銀利率決議", a="—", st="未公布"),
        _ROW.format(d="10/30", item="台股休市", a="—", st="休市"),
    ]), encoding="utf-8")
    need = macronews.lastweek_needed((mc / "2026-10-30.md").read_text(encoding="utf-8"), date(2026, 10, 30))
    assert [r["item"] for r in need] == ["9月景氣對策信號", "日銀利率決議"]      # 已公布的週四列、休市列不帶
    sat = _cal("11/02–11/06", "2026/10/31", [_ROW.format(d="11/04", item="美：FOMC", a="—", st="未公布"),
                                             _ROW.format(d="10/30", item="日：日銀利率決議", a="維持", st="已公布")])
    errs = check._check_calendar_lastweek(sat, "c.md", "2026-10-31")
    assert len(errs) == 1 and "9月景氣對策信號" in errs[0]
    full = sat.replace("| 10/30 | 日：", "| 10/28 | 台：9月景氣對策信號 | — | 41分（紅燈） | — | 已公布 |\n| 10/30 | 日：")
    assert check._check_calendar_lastweek(full, "c.md", "2026-10-31") == []
    assert check._check_calendar_lastweek(sat, "c.md", "2026-10-30") == []   # 平日不查


def test_weekend_prompt_brings_last_week(monkeypatch):
    import gen_macronews
    last = "# 本週重點財經行事曆（10/26–10/30）\nLASTWEEK"
    monkeypatch.setattr(macronews, "last_week_cal", lambda *a, **k: (date(2026, 10, 30), last))
    monkeypatch.setattr(macronews, "prior_cal", lambda *a, **k: None)
    p = gen_macronews.build_cal_prompt(date(2026, 10, 31))
    assert "週末版：保留上週結果" in p and "【上週最後一版（2026/10/30）" in p and "LASTWEEK" in p
    # 週日：底稿（週六版）已帶上週列，只附規則、不再附上週全文
    monkeypatch.setattr(macronews, "prior_cal", lambda *a, **k: (date(2026, 10, 31), "# 本週重點財經行事曆（11/02–11/06）\nSAT"))
    p = gen_macronews.build_cal_prompt(date(2026, 11, 1))
    assert "週末版：保留上週結果" in p and "LASTWEEK" not in p
    assert "週末版：保留上週結果" not in gen_macronews.build_cal_prompt(date(2026, 10, 30))
