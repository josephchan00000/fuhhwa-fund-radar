"""行事曆官方自動補值（arm/calfill.py；docs/macrocal_fill_plan.md 第二段）。

10/28～10/30 三份行事曆的「9月景氣對策信號」都空著，國發會 10/28 16:00 公布、CI 10/30 01:31 就抓進專案了；
9/4 那份的「8月失業率」寫成 4.3%（官方 4.1%）。這裡守：只補空白、日期已到、序列有那個月；項目還要月增／非農
這類抓不到的整列不補；四捨五入邊界不補；已填而不同只加「官方核對」、不覆寫；同一行註不重複；只動最新一份。"""
from datetime import date, datetime

from arm import calfill as CF

SER = {
    "ndc": {"2026-08": [0, 0, 0, 0, 0, 0, 40.0, "紅"], "2026-09": [0, 0, 0, 0, 0, 0, 41.0, "紅"]},
    "ndc_first": {"2026-08": [41.0, "2026-09-28"], "2026-09": [41.0, "2026-10-30"]},
    "twcpi": {"2026-09": [112.82, 2.73]},
    "orders": {"2025-09": 70356.0, "2026-09": 114210.0},
    "us_bls": {"2025-08": [4.3, 323.976, 330.0], "2026-08": [4.1, 334.98, 338.041],
               "2025-09": [4.3, 324.8, 330.82], "2026-09": [4.2, 336.94, 339.287]},
    "uscpi": {},
    "fedtgt": {"2026-10-27": [3.75, 4.0], "2026-10-28": [3.75, 4.0], "2026-10-29": [3.5, 3.75]},
    # 第三段（arm/calsrc.py）：勞工統計局 2026-10-30 抓到的值（9 月非農 +2.9 萬、CPI 月增 0.6／核心 0.3、PPI 月增 1.3、8 月 JOLTS 707.9 萬）
    "us_bls_cal": {"2025-09": {"CES0500000003": 36.71, "WPUFD4": 150.11},
                   "2026-08": {"CES0000000001": 159015.0, "CES0500000003": 37.76, "CUSR0000SA0": 334.131,
                               "CUSR0000SA0L1E": 337.765, "WPSFD4": 157.662, "JTS000000000000000JOL": 7079.0},
                   "2026-09": {"CES0000000001": 159044.0, "CES0500000003": 37.81, "CUSR0000SA0": 336.298,
                               "CUSR0000SA0L1E": 338.896, "WPSFD4": 159.780, "WPUFD4": 159.613},
                   "2026-Q2": {"CIS1010000000000Q": 0.9, "CIU1010000000000A": 3.4}},
    "ecb_dec": {"2026-10-29": [2.5, 0.0], "2026-09-10": [2.5, 0.25]},
    "twgdp_yoy": {"2026-06": 12.93},
}


def S(name):
    return SER.get(name, {})


def _md(rows, notes=("- 前值依官方。", "- 僅為資訊彙編、非投資建議，不含禁用詞。")):
    head = ("# 本週重點財經行事曆（10/26–10/30）\n\n> 更新：2026/10/30；市況：台股 正常交易\n\n"
            "| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n")
    return head + "\n".join(rows) + "\n\n註：\n" + "\n".join(notes) + "\n"


R = "| {d} | {i} | — | {a} | — | {s} |"
T, NOW = date(2026, 10, 30), datetime(2026, 10, 30, 19, 12)


def test_fills_blank_rows_from_official_series():
    md = _md([R.format(d="10/28", i="台：9月景氣對策信號（16:00）", a="—", s="未公布"),
              R.format(d="10/20", i="台：9月外銷訂單（金額；年增）", a="—", s="未公布"),
              R.format(d="10/07", i="台：9月CPI（年增）", a="—", s="未公布"),
              R.format(d="10/02", i="美：9月失業率", a="—", s="未公布"),
              R.format(d="10/14", i="美：9月CPI（年增；核心）", a="—", s="未公布"),
              R.format(d="10/14", i="美：9月核心CPI（年增）", a="—", s="未公布")])
    new, acts = CF.fill(md, T, T, NOW, S)
    assert [a["value"] for a in acts] == ["41分（紅燈）", "1,142.1億美元（+62.3%）", "+2.73%", "4.2%",
                                          "+3.7%（核心+2.6%）", "+2.6%"]
    assert "| 10/28 | 台：9月景氣對策信號（16:00） | — | 41分（紅燈） | — | 已公布 |" in new
    assert "- 官方自動補值（10/30 19:12）：台：9月景氣對策信號 41分（紅燈）（國發會）。" in new
    assert new.rstrip().endswith("非投資建議，不含禁用詞。")         # 註加在免責聲明前面
    assert CF.fill(new, T, T, NOW, S) == (new, [])                   # 再跑一次：沒有可補的、不重複加註


def test_skips_what_it_cannot_fill_completely():
    md = _md([R.format(d="11/04", i="美：10月失業率", a="—", s="未公布"),                 # 還沒到
              R.format(d="10/30", i="美：10月CPI（年增）", a="—", s="未公布"),             # 序列還沒有 10 月
              R.format(d="10/14", i="美：9月CPI（超級核心）", a="—", s="未公布"),            # 沒有序列
              R.format(d="10/02", i="美：9月非農就業／失業率", a="—", s="未公布"),          # 還要非農
              R.format(d="10/07", i="台：9月CPI（年增；核心）", a="—", s="未公布"),          # 台灣核心沒有序列
              R.format(d="10/28", i="美：FOMC 10月會議紀要", a="—", s="未公布"),
              R.format(d="10/28", i="台：9月景氣對策信號", a="—", s="延後公布"),
              R.format(d="10/26", i="台股休市", a="—", s="休市")])
    assert CF.fill(md, T, T, NOW, S) == (md, [])


def test_fomc_compares_ranges_around_decision_day():
    up = lambda d: CF.official({"region": "美", "item": "FOMC利率決議"}, d, S)  # noqa: E731
    assert up(date(2026, 10, 28))[0] == "降息1碼至3.50%–3.75%"
    assert up(date(2026, 10, 27)) is None                    # 會前那天（10/26 以前）沒有資料 → 不補
    hold = {"fedtgt": {"2026-10-27": [3.75, 4.0], "2026-10-28": [3.75, 4.0], "2026-10-30": [3.75, 4.0]}}
    assert CF.official({"region": "美", "item": "FOMC 利率決議（台北10/29 02:00）"}, date(2026, 10, 29),
                       lambda n: hold.get(n, {}))[0] == "維持3.75%–4.00%"
    assert CF.official({"region": "美", "item": "FOMC利率決議"}, date(2026, 10, 29), lambda n: {}) is None


def test_mismatch_is_flagged_not_overwritten():
    md = _md([R.format(d="09/04", i="美：8月失業率", a="4.3%（2021年10月以來新高）", s="已公布"),
              R.format(d="10/28", i="台：8月景氣對策信號", a="41分（紅燈）", s="已公布")])   # 第一次公布 41、後來修正 40：算對
    new, acts = CF.fill(md, date(2026, 9, 6), date(2026, 9, 6), NOW, S)
    assert [a["kind"] for a in acts] == ["mismatch"] and "4.3%（2021年10月以來新高）" in new
    assert "官方核對：美：8月失業率官方公布 4.1%（勞工統計局），表中寫「4.3%（2021年10月以來新高）」" in new
    assert CF.fill(new, date(2026, 9, 6), date(2026, 9, 6), NOW, S)[0] == new   # 同一行不重複加
    old = CF.fill(md, date(2026, 9, 30), date(2026, 9, 30), NOW, S)            # 超過 10 天的不核對（可能是修正值）
    assert old == (md, [])
    later = _md([R.format(d="10/02", i="美：9月失業率", a="延後至11/5公布", s="未公布")])  # 不是結果：不核對、也不補
    assert CF.fill(later, T, T, NOW, S) == (later, [])


def test_month_year_and_rounding_edges():
    assert CF._ym(12, date(2027, 1, 13)) == "2026-12" and CF._ym(9, date(2026, 10, 28)) == "2026-09"
    assert CF._ym(10, date(2026, 10, 30)) is None
    assert CF._r(2.35, 1) is None and CF._r(2.36, 1) == 2.4      # 落在進位邊界就不補


def test_run_touches_latest_file_only(tmp_path):
    a, b = tmp_path / "2026-10-29.md", tmp_path / "2026-10-30.md"
    rows = [R.format(d="10/28", i="台：9月景氣對策信號（16:00）", a="—", s="未公布")]
    a.write_text(_md(rows), encoding="utf-8")
    b.write_text(_md(rows), encoding="utf-8")
    (tmp_path / "2026-11-02.md").write_text(_md([]), encoding="utf-8")       # 明天的（不該有，有也不碰）
    r = CF.run(T, NOW, tmp_path, S)
    assert r["wrote"] and r["file"].endswith("2026-10-30.md") and len(r["acts"]) == 1
    assert "41分（紅燈）" in b.read_text(encoding="utf-8") and "41分" not in a.read_text(encoding="utf-8")
    assert CF.run(T, NOW, tmp_path, S, write=True)["wrote"] is False         # 第二次沒東西可寫


def test_release_day_refetch_waits_only_when_due(monkeypatch):
    from arm.lab import heatdata as HD
    data = {"ndc": {"2026-08": [0] * 6 + [40.0, "紅"]}, "us_bls": {"2026-09": [4.2, None, None]}}
    monkeypatch.setattr(HD, "load", lambda n: data.get(n, {}))
    at = lambda d, h: datetime(2026, 10, d, h, 5)  # noqa: E731
    assert HD.waiting("ndc", at(28, 19), 22, 16, 6)            # 9 月該出來了、還沒有、過了 16 點 → 再抓
    assert not HD.waiting("ndc", at(28, 15), 22, 16, 6)        # 還沒到公布時間
    assert not HD.waiting("ndc", at(21, 19), 22, 16, 6)        # 還沒到該出來的日子
    data["ndc"]["2026-09"] = [0] * 6 + [41.0, "紅"]
    assert not HD.waiting("ndc", at(28, 19), 22, 16, 6)        # 已經有了：回到一天一次
    assert not HD.waiting("us_bls", at(3, 22), 1, 21, 0)       # 失業率有了
    assert HD.waiting("us_bls", at(14, 22), 10, 21, 1)         # CPI 那一欄還空著


def test_ci_runs_fill_after_fetch_and_commits_calendar():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sh = (root / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    assert sh.index("fetch_heat_us.py") < sh.index("run_calfill.py") < sh.index("gen_fund_dashboard.py")
    y = (root / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    assert y.index("fetch_heat_us.py") < y.index("run_calfill.py") < y.index("id: guard")
    assert 'git status --porcelain data/ reports/macrocal/' in y            # 只有行事曆補了值也要重建、commit
    assert y.count("git add -f reports/macrocal/*.md") == 2                  # commit 一次、rebase 重試一次
    assert "git checkout origin/main -- reports/macrocal" in y               # 重試時以 main 最新版為底稿重算
    d = (root / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8")
    assert "git checkout origin/main -- reports/macrocal" not in d           # 每日那支帶著今天的新聞，絕不能拿 main 的舊版蓋掉


def test_ndc_previous_value_revised_is_flagged_once():
    row = "| 10/28 | 台：9月景氣對策信號（16:00） | — | — | 41分（紅燈） | 未公布 |"     # 前值寫 8 月第一次公布的 41
    new, acts = CF.fill(_md([row]), T, T, NOW, S)
    assert [a["kind"] for a in acts] == ["prev", "fill"]
    assert "官方核對：台：9月景氣對策信號的前值（8月）國發會已修正為 40分（紅燈），表中寫「41分（紅燈）」" in new
    assert "| 41分（紅燈） | 41分（紅燈） | 已公布 |" in new                     # 前值不覆寫，只加註
    again, acts2 = CF.fill(new, T, T, NOW, S)
    assert again == new and [a["new"] for a in acts2] == [False]             # 同一行不重複加
    fixed = row.replace("| 41分（紅燈） |", "| 40分（紅燈）（原41分） |")
    assert [a["kind"] for a in CF.fill(_md([fixed]), T, T, NOW, S)[1]] == ["fill"]


def test_stage3_rows_from_bls_ecb_dgbas():
    """第三段：非農、時薪、季調 CPI 月增、PPI、JOLTS、ECI、歐洲央行、台灣 GDP。"""
    S3 = {**SER, "us_bls_cal": {**SER["us_bls_cal"]}}

    def got(region, item, d):
        x = CF.official({"region": region, "item": item}, d, lambda n: S3.get(n, {}))
        return x[0] if x else None
    d = date(2026, 10, 3)
    assert got("美", "9月非農就業", d) == "+2.9萬"
    assert got("美", "9月非農就業／失業率", d) is None                      # 合在一起的列不補
    assert got("美", "9月平均時薪（年增）", d) == "+3.0%"                     # 季調，和新聞稿一致
    assert got("美", "9月平均時薪（月增）", d) is None                        # 0.13% 只到分算不準 → 不補
    assert got("美", "9月CPI（年增；月增／核心月增）", date(2026, 10, 14)) == "年增+3.7%、月增+0.6%（核心月增+0.3%）"
    assert got("美", "9月CPI（月增）", date(2026, 10, 14)) == "+0.6%"
    assert got("美", "9月PPI（月增）", date(2026, 10, 15)) == "+1.3%"
    assert got("美", "9月PPI", date(2026, 10, 15)) == "月增+1.3%、年增+6.3%"
    assert got("美", "9月核心PPI（年增）", date(2026, 10, 15)) is None         # 核心有兩種定義，不補
    assert got("美", "8月JOLTS職缺", date(2026, 10, 6)) == "707.9萬"
    assert got("美", "第二季就業成本指數ECI", date(2026, 7, 31)) == "+0.9%"
    assert got("美", "Q2僱用成本指數ECI（季增；年增）", date(2026, 7, 31)) == "季增+0.9%、年增+3.4%"
    assert got("歐", "ECB利率決議（存款利率）", date(2026, 10, 29)) == "維持2.50%"
    assert got("歐", "ECB利率決議暨拉加德記者會", date(2026, 9, 10)) == "升息1碼至2.50%"
    assert got("歐", "ECB 9月會議紀要", date(2026, 10, 9)) is None
    assert got("台", "第二季GDP初值（年增）", date(2026, 8, 28)) == "+12.93%"
    assert got("台", "2026年經濟成長率預測", date(2026, 8, 28)) is None


def test_wanted_only_fetches_when_a_row_waits():
    md = _md([R.format(d="10/29", i="美：9月非農就業", a="—", s="未公布"),        # 序列沒有 → 要抓
              R.format(d="10/29", i="歐：ECB利率決議", a="—", s="未公布"),          # 本機已有 10/29 → 不抓
              R.format(d="10/30", i="台：第三季GDP概估（年增）", a="—", s="未公布"),
              R.format(d="10/20", i="美：9月PPI（月增）", a="—", s="未公布"),        # 超過 3 天 → 留給早上的 Claude
              R.format(d="11/04", i="美：10月JOLTS職缺", a="—", s="未公布"),        # 還沒到
              R.format(d="10/29", i="美：9月CPI（年增）", a="—", s="未公布"),        # 年增用景氣頁的序列 → 不抓
              R.format(d="10/29", i="美：FOMC利率決議", a="—", s="未公布")])
    empty = {**SER, "us_bls_cal": {}}
    assert CF.wanted(md, T, T, lambda n: empty.get(n, {})) == {"bls_cal", "twgdp"}
    assert CF.wanted(md, T, T, S) == {"twgdp"}                               # 非農那一期已經有了


def test_run_calfill_fetches_before_filling_and_never_fails(monkeypatch, tmp_path, capsys):
    import importlib.util
    from pathlib import Path
    from arm import calsrc
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("run_calfill", root / "scripts" / "run_calfill.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "2026-10-30.md").write_text(_md([R.format(d="10/29", i="歐：ECB利率決議", a="—", s="未公布")]),
                                            encoding="utf-8")
    monkeypatch.setattr(CF.MN, "CAL_DIR", tmp_path)
    monkeypatch.setattr(mod, "today_tw", lambda: T)
    monkeypatch.setattr(mod, "now_tw", lambda: NOW)
    calls = []
    monkeypatch.setattr(calsrc, "fetch", lambda keys, today: calls.append(set(keys)) or ["ecb ✓ 1 筆更新"])
    monkeypatch.setattr(CF.HD, "load", lambda n: {})
    monkeypatch.setattr("sys.argv", ["run_calfill.py", "--no-fetch"])
    assert mod.main() == 0 and calls == []                                   # 重試那一次不抓
    monkeypatch.setattr("sys.argv", ["run_calfill.py"])
    assert mod.main() == 0 and calls == [{"ecb"}]
    monkeypatch.setattr(calsrc, "fetch", lambda keys, today: 1 / 0)
    assert mod.main() == 0                                                   # 抓取出錯也不擋發佈
    assert "[calfill]" in capsys.readouterr().out


def test_ci_hooks_keep_fetch_inside_time_budget():
    from pathlib import Path
    from arm import calsrc
    root = Path(__file__).resolve().parent.parent
    y = (root / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    assert "timeout 300 python3 scripts/run_calfill.py" in y
    assert "run_calfill.py --no-fetch" in y                                  # push 被拒重試時不再連網
    assert "timeout 300 python3 scripts/run_calfill.py" in (root / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    assert calsrc.BUDGET_S + 90 + 60 < 300                                   # 預算到了才開始抓的最後一個也來得及
