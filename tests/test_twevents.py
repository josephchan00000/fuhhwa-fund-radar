"""台灣固定時程＋展會行事曆（arm/twevents.py）與「台：／展：」前綴管線（2026-09-18）。

守：央行季會＝第三個週四（對 2025／2026 官方實際日期）、種子檔可讀且日期合法、本週／下週分桶、
提示包段落有必列項目、行事曆解析／儀表板徽章／列印版 CSS 都認得「台」「展」、
check_reports 的「無台列」與「央行決議日未提及」閘門會紅、閘門不回溯 2026-09-19 之前。
"""
from datetime import date
from pathlib import Path

from arm import macronews, twevents

ROOT = Path(__file__).resolve().parent.parent


def test_cbc_meeting_is_third_thursday_matches_official_dates():
    # 央行官方：2025＝3/20、6/19、9/18、12/18；2026＝3/19、6/18、9/17、12/17
    assert twevents.cbc_meetings(2025) == [date(2025, 3, 20), date(2025, 6, 19),
                                           date(2025, 9, 18), date(2025, 12, 18)]
    assert twevents.cbc_meetings(2026) == [date(2026, 3, 19), date(2026, 6, 18),
                                           date(2026, 9, 17), date(2026, 12, 17)]
    assert twevents.cbc_meeting(2026, 7) is None
    for d in twevents.cbc_meetings(2026):
        assert d.weekday() == 3


def test_cbc_recent_covers_meeting_day_and_next_two_days_only():
    assert twevents.cbc_recent(date(2026, 9, 17)) == date(2026, 9, 17)   # 當日（盤後報）
    assert twevents.cbc_recent(date(2026, 9, 18)) == date(2026, 9, 17)   # 隔日盤前報
    assert twevents.cbc_recent(date(2026, 9, 19)) == date(2026, 9, 17)   # 週六合併時窗
    assert twevents.cbc_recent(date(2026, 9, 21)) is None
    assert twevents.cbc_recent(date(2026, 9, 16)) is None


def test_seed_file_loads_with_valid_dates_and_kinds():
    evs = twevents.load_seed()
    assert len(evs) >= 10
    assert {e["kind"] for e in evs} <= {"展", "台", "休市"}
    names = " ".join(e["name"] for e in evs)
    assert "SEMICON Taiwan" in names and "COMPUTEX" in names          # 半導體展＝使用者點名
    for e in evs:
        assert e["start"] <= e["end"]
    # 壞檔／缺檔 fail-open 回空
    assert twevents.load_seed(ROOT / "config" / "no_such_file.json") == []


def test_due_buckets_this_week_and_next_week():
    evs = [{"name": "A 展", "start": date(2026, 9, 2), "end": date(2026, 9, 4), "kind": "展",
            "note": "", "tentative": False},
           {"name": "B 發表會", "start": date(2026, 9, 9), "end": date(2026, 9, 9), "kind": "展",
            "note": "", "tentative": False},
           {"name": "C 休市", "start": date(2026, 9, 25), "end": date(2026, 9, 25), "kind": "休市",
            "note": "", "tentative": False}]
    info = twevents.due(date(2026, 9, 1), evs)
    assert [e["name"] for e in info["this"]] == ["A 展"]
    assert [e["name"] for e in info["next"]] == ["B 發表會"]
    assert info["cbc"] is None and info["cbc_next"] is None
    # 央行週：本週 9/17；週末（週六）仍歸本週
    info2 = twevents.due(date(2026, 9, 19), evs)
    assert info2["cbc"] == date(2026, 9, 17) and info2["week"] == (date(2026, 9, 14), date(2026, 9, 18))
    assert [e["name"] for e in info2["next"]] == ["C 休市"]
    assert twevents.due(date(2026, 9, 10), evs)["cbc_next"] == date(2026, 9, 17)


def test_calendar_note_lists_cbc_and_seed_and_monthly_hints():
    s = twevents.calendar_note(date(2026, 9, 18))
    assert "台：央行第 3 季理監事會（09/17 週四" in s
    assert "外銷訂單" in s                              # 月度慣例窗 18–22 日與本週交集
    assert "下週預告" in s and "中秋節" in s            # 種子檔 9/25 休市
    s2 = twevents.calendar_note(date(2026, 9, 1))
    assert "展：SEMICON Taiwan 2026" in s2 and "09/02–09/04" in s2
    assert "Apple 秋季發表會" in s2                      # 下週預告
    # 種子讀不到／本週無項目時仍給「至少 1 列台」的指示，段落不消失
    s3 = twevents.calendar_note(date(2026, 8, 12))
    assert "台灣固定時程" in s3 and ("必列" in s3 or "至少 1 筆" in s3)


def test_tw_policy_note_flags_meeting_day_and_next_day():
    for d in (date(2026, 9, 17), date(2026, 9, 18)):
        s = twevents.tw_policy_note(d)
        assert s.startswith("⚑【央行理監事會必收】") and "必成卡" in s and "房市" in s
    s = twevents.tw_policy_note(date(2026, 9, 22))
    assert "⚑" not in s and "台股本位必收" in s and "2026/12/17" in s   # 平日：常態提醒＋下次會期


def test_prompt_packs_inject_tw_policy_and_calendar_notes():
    import importlib.util
    import sys
    for name in ("gen_twnews", "gen_macronews"):
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    tw = sys.modules["gen_twnews"].build_prompt(date(2026, 9, 18), "pre")
    assert "⚑【央行理監事會必收】" in tw and "台灣官方政策與房市" in tw
    cal = sys.modules["gen_macronews"].build_cal_prompt(date(2026, 9, 18))
    assert "台灣固定時程" in cal and "央行第 3 季理監事會" in cal
    assert "美：／歐：／中：／日：／台：／展：／財報：" in cal
    macro = sys.modules["gen_macronews"].build_prompt(date(2026, 9, 18))
    assert "台灣央行理監事會決議日" in macro                  # 總經報總覽帶一句對照 Fed


def test_calendar_parse_and_badges_know_tw_and_ex():
    md = ("# 本週重點財經行事曆（09/14–09/18）\n> 更新：2026/09/18；市況：台股 正常交易\n\n"
          "| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n"
          "| 09/17 | 台：央行第3季理監事會 | — | 利率連10凍、第2戶房貸成數放寬至7成 | 2% | 已公布 |\n"
          "| 09/02 | 展：SEMICON Taiwan 2026（至 9/4） | — | 開幕 | — | 已公布 |\n"
          "| 09/16 | 美：FOMC利率決議 | — | 升息1碼 | — | 已公布 |\n")
    rows = macronews._parse_cal_rows(md)
    assert [r["region"] for r in rows] == ["台", "展", "美"]
    assert rows[0]["item"] == "央行第3季理監事會"
    from arm import fund_dashboard as fd
    html = fd._macro_cal_view({"date": "2026-09-18", "note": "", "title": "t", "rows": rows})
    assert '<span class="creg tw">台</span>' in html and '<span class="creg ex">展</span>' in html
    assert "台：" not in html and "展：" not in html
    css = fd._CSS if hasattr(fd, "_CSS") else (ROOT / "arm" / "fund_dashboard.py").read_text(encoding="utf-8")
    assert ".creg.tw{" in css and ".creg.ex{" in css
    from arm import printview
    assert ".pr-reg.tw{" in printview.CSS and ".pr-reg.ex{" in printview.CSS


def test_check_reports_gates_tw_row_and_cbc_mention(tmp_path, monkeypatch):
    import importlib.util
    import sys
    spec = importlib.util.spec_from_file_location("check_reports", ROOT / "scripts" / "check_reports.py")
    cr = importlib.util.module_from_spec(spec)
    sys.modules["check_reports"] = cr
    spec.loader.exec_module(cr)
    monkeypatch.setattr(cr, "ROOT", tmp_path)
    caldir = tmp_path / "reports" / "macrocal"
    caldir.mkdir(parents=True)
    rows = "".join(f"| 09/1{i % 5} | 美：數據{i} | — | — | — | 未公布 |\n" for i in range(10))
    head = "# 本週重點財經行事曆\n> 更新：2026/09/19；市況：台股 正常交易\n\n| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n"
    p = caldir / "2026-09-19.md"
    p.write_text(head + rows, encoding="utf-8")
    errs = cr._check_calendar(p, "2026-09-19")
    assert any("台：" in e for e in errs)
    p.write_text(head + rows + "| 09/17 | 台：央行第3季理監事會 | — | 利率不變 | 2% | 已公布 |\n", encoding="utf-8")
    assert cr._check_calendar(p, "2026-09-19") == []
    # 2026-09-19 之前不回溯
    p18 = caldir / "2026-09-18.md"
    p18.write_text(head.replace("09/19", "09/18") + rows, encoding="utf-8")
    assert not any("台：" in e for e in cr._check_calendar(p18, "2026-09-18"))
    # 央行決議隔日台股報未提「央行」→ 紅；提及即過；非會期不查
    twdir = tmp_path / "reports" / "twnews"
    twdir.mkdir(parents=True)
    t = twdir / "2026-09-19.md"
    t.write_text("# 〈台股盤後重點〉\n只有半導體。\n", encoding="utf-8")
    assert cr._check_cbc_mention(t, "2026-09-19")
    t.write_text("# 〈台股盤後重點〉\n央行連10凍。\n", encoding="utf-8")
    assert cr._check_cbc_mention(t, "2026-09-19") == []
    t22 = twdir / "2026-09-22.md"
    t22.write_text("沒有。\n", encoding="utf-8")
    assert cr._check_cbc_mention(t22, "2026-09-22") == []
