"""行事曆「預期」欄自動補（arm/calcons.py；docs/macrocal_fill_plan.md 第五段）。

事件的數字取自 2026-11-03 CI 探針（scripts/probe_calcons.py）實際抓到的 ForexFactory 週曆與 Nasdaq 經濟日曆。
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from arm import calcons as C

TODAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 21, 30)

MD = """# 本週重點財經行事曆（11/02–11/06）

> 更新：2026/11/03；市況：台股 正常交易｜美股 正常交易｜日股 11/3 因文化日休市｜韓股 正常交易｜陸股 正常交易｜港股 正常交易；本週焦點：11/6 美國10月非農

| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |
|---|---|---|---|---|---|
| 11/02 | 美：10月ISM製造業PMI | 54.7* | 55.5 | 54.5 | 已公布 |
| 11/02 | 美：芝加哥聯銀總裁古爾斯比對談（金融市場集團秋季會議） | — | — | — | 未公布 |
| 11/03 | 美：期中選舉投票日 | — | — | — | 未公布 |
| 11/03 | 美：9月JOLTS職缺 | — | — | — | 未公布 |
| 11/04 | 歐：歐元區10月HICP快報（年增；核心） | — | — | +3.8%（核心+2.5%） | 未公布 |
| 11/04 | 美：10月ISM服務業PMI | 55.1* | — | 54.9 | 未公布 |
| 11/04 | 中：10月財新服務業PMI | — | — | — | 未公布 |
| 11/05 | 歐：英國央行（BoE）利率決議（台北20:00） | — | — | 3.75% | 未公布 |
| 11/05 | 美：截至10/31當週初領失業金人數 | — | — | 19.4萬 | 未公布 |
| 11/06 | 美：10月非農就業（失業率） | — | — | +2.9萬（4.2%） | 未公布 |

註：
- 標「*」為第三方市場共識或機構預估，非官方數據：ISM 製造業 10 月 54.7 依 Newsquawk 週前瞻。
- 本表僅供參考，非投資建議。
"""

EV = [
    ["FF", "US", "JOLTS Job Openings", "2026-11-03", "7.15M"],
    ["NQ", "US", "JOLTS Job Openings", "2026-11-03", "7.150M"],
    ["FF", "EZ", "CPI Flash Estimate y/y", "2026-11-04", "4.0%"],
    ["FF", "EZ", "Core CPI Flash Estimate y/y", "2026-11-04", "2.5%"],
    ["NQ", "EZ", "CPI", "2026-11-04", "4.0%"],
    ["NQ", "EZ", "Core CPI", "2026-11-04", "2.5%"],
    ["FF", "US", "ISM Services PMI", "2026-11-04", "54.8"],
    ["NQ", "US", "ISM Non-Manufacturing PMI", "2026-11-04", "54.8"],
    ["NQ", "CN", "RatingDog Services PMI", "2026-11-04", "51.7"],
    ["FF", "UK", "Official Bank Rate", "2026-11-05", "4.00%"],
    ["FF", "US", "Unemployment Claims", "2026-11-05", "197K"],
    ["NQ", "US", "Initial Jobless Claims", "2026-11-05", "197K"],
    ["FF", "US", "Non-Farm Employment Change", "2026-11-06", "65K"],
    ["FF", "US", "Unemployment Rate", "2026-11-06", "4.2%"],
    ["FF", "US", "Average Hourly Earnings m/m", "2026-11-06", "0.3%"],
]


def _cells(md: str, key: str) -> list[str]:
    line = next(ln for ln in md.split("\n") if key in ln)
    return [x.strip() for x in line.strip().strip("|").split("|")]


@pytest.mark.parametrize("kind,raw,word,want", [
    ("cnt", "7.15M", "", "715萬"), ("cnt", "7.079M", "", "707.9萬"), ("cnt", "197K", "", "19.7萬"),
    ("cnt", "200K", "", "20.0萬"), ("cnt", "651K", "萬戶", "65.1萬戶"), ("cnt", "4.05M", "萬戶", "405萬戶"),
    ("chg", "67K", "", "+6.7萬"), ("chg", "-23K", "", "-2.3萬"), ("chg", "90K", "", "+9萬"),
    ("bn", "-107.9B", "", "-1,079億美元"), ("rate", "4.00%", "", "4.00%"), ("rate", "0.75%", "", "0.75%"),
    ("spct", "0.3%", "", "+0.3%"), ("spct", "2.40%", "", "+2.4%"), ("spct", "-0.4%", "", "-0.4%"),
    ("spct", "0.0%", "", "0.0%"), ("pct", "4.2%", "", "4.2%"), ("idx", "54.8", "", "54.8"),
    ("idx", "-8.70", "", "-8.70"), ("sidx", "26", "", "+26"), ("bbl", "-1.9M", "", "-190萬桶"),
    ("bbl", "1,700K", "", "+170萬桶"),
])
def test_formats_follow_calendar_style(kind, raw, word, want):
    assert C.fmt(kind, C.parse(raw), word) == want


def test_parse_rejects_blank_and_text():
    for s in ("", " ", "&nbsp;", "-", "7-0-2", "4.18|1.6", None):
        assert C.parse(s) is None
    assert C.parse("1,701K") == (1701.0, "K", 0)


@pytest.mark.parametrize("region,item,n,tpl", [
    ("美", "10月非農就業（失業率）", 2, "{0}（{1}）"),
    ("美", "10月非農就業", 1, "{0}"),
    ("美", "9月JOLTS職缺", 1, "{0}"),
    ("美", "截至10/31當週初領失業金人數", 1, "{0}"),
    ("美", "10月ISM服務業PMI", 1, "{0}"),
    ("美", "10月CPI（年增；核心）", 2, "{0}（核心{1}）"),
    ("美", "10月核心CPI（月增）", 1, "{0}"),
    ("美", "10月S&P Global製造業／服務業PMI初值", 2, "{0}／{1}"),
    ("歐", "歐元區10月HICP快報（年增；核心）", 2, "{0}（核心{1}）"),
    ("中", "10月財新服務業PMI", 1, "{0}"),
    ("中", "第三季GDP（年增；季增）", 2, "{0}（{1}）"),
    ("日", "10月東京CPI（核心，年增）", 1, "{0}"),
    ("日", "10月東京CPI（年增；核心）", 2, "{0}（核心{1}）"),
])
def test_rules_match_calendar_items(region, item, n, tpl):
    m = C.match({"region": region, "item": item})
    assert m and len(m[1]) == n and m[2] == tpl


@pytest.mark.parametrize("region,item", [
    ("美", "芝加哥聯銀總裁古爾斯比對談（金融市場集團秋季會議）"),
    ("美", "期中選舉投票日"),
    ("美", "10月CPI（年增；月增／核心月增）"),       # 一列要三個數，月增年增混在一起 → 不補
    ("美", "10月CPI"),                              # 沒寫月增還是年增 → 不補
    ("美", "11月密大一年通膨預期初值"),
    ("美", "10月非農就業（失業率、時薪）"),           # 要時薪 → 整列不補
    ("美", "FOMC 利率決議"),                         # 區間寫法，留給早上
    ("台", "第三季GDP概估（年增）"),
])
def test_rules_skip_what_they_cannot_fill(region, item):
    assert C.match({"region": region, "item": item}) is None


def test_fill_blank_rows_only_and_add_one_note_line():
    new, acts = C.fill(MD, TODAY, TODAY, NOW, EV)
    assert _cells(new, "JOLTS")[2] == "715萬*"
    assert _cells(new, "HICP")[2] == "+4.0%（核心+2.5%）*"
    assert _cells(new, "財新服務業")[2] == "51.7*"                       # 只有 Nasdaq 有，名字不會混
    assert _cells(new, "初領")[2] == "19.7萬*"
    assert _cells(new, "美：10月非農")[2] == "+6.5萬（4.2%）*"
    assert _cells(new, "BoE")[2] == "4.00%（升息25bp）*"               # 和前值比，寫維持／升息／降息
    assert _cells(new, "ISM服務業")[2] == "55.1*"                        # 子代理寫了 → 不動（即使來源是 54.8）
    assert _cells(new, "ISM製造業")[2] == "54.7*"                        # 已公布 → 不動
    assert _cells(new, "古爾斯比")[2] == "—" and _cells(new, "期中選舉")[2] == "—"
    notes = [ln for ln in new.split("\n") if ln.startswith(C.NOTE_HEAD)]
    assert len(notes) == 1
    assert "美：9月JOLTS職缺 715萬（ForexFactory、Nasdaq一致）" in notes[0]
    assert "中：10月財新服務業PMI 51.7（Nasdaq）" in notes[0] and "市場共識、非官方" in notes[0]
    assert new.index(notes[0]) < new.index("非投資建議")                 # 免責聲明留在最後
    assert {a["kind"] for a in acts} == {"fill"}
    again, acts2 = C.fill(new, TODAY, TODAY, NOW, EV)                    # 第二輪：都補了，原文不變
    assert again == new and acts2 == []


def test_disagreement_and_check_only_names_do_not_fill():
    ev = [e for e in EV if "JOLTS" not in e[2]] + [["FF", "US", "JOLTS Job Openings", "2026-11-03", "7.2M"],
                                                    ["NQ", "US", "JOLTS Job Openings", "2026-11-03", "7.150M"]]
    new, acts = C.fill(MD, TODAY, TODAY, NOW, ev)
    assert _cells(new, "JOLTS")[2] == "—"
    assert any(a["kind"] == "skip" and "兩邊不同" in a["why"] for a in acts)
    # 歐元區 CPI：Nasdaq 名字分不出月增年增 → 只能核對；ForexFactory 沒有就不補
    ev2 = [e for e in EV if e[0] == "NQ" or "CPI" not in e[2]] + [["NQ", "EZ", "CPI", "2026-11-04", "0.3%"]]
    new2, _ = C.fill(MD, TODAY, TODAY, NOW, ev2)
    assert _cells(new2, "HICP")[2] == "—"


def test_check_only_confirms_one_of_several_nasdaq_values():
    md = MD.replace("| 11/04 | 中：10月財新服務業PMI | — | — | — | 未公布 |",
                    "| 11/04 | 美：10月CPI（年增；核心） | — | — | +3.0%（核心+2.5%） | 未公布 |")
    ev = EV + [["FF", "US", "CPI y/y", "2026-11-04", "3.4%"], ["FF", "US", "Core CPI y/y", "2026-11-04", "2.4%"],
               ["NQ", "US", "CPI", "2026-11-04", "3.4%"], ["NQ", "US", "CPI", "2026-11-04", "0.3%"],
               ["NQ", "US", "Core CPI", "2026-11-04", "2.4%"], ["NQ", "US", "Core CPI", "2026-11-04", "0.2%"]]
    new, _ = C.fill(md, TODAY, TODAY, NOW, ev)
    assert _cells(new, "10月CPI")[2] == "+3.4%（核心+2.4%）*"
    assert "美：10月CPI +3.4%（核心+2.4%）（ForexFactory、Nasdaq一致）" in new
    ev_bad = [e for e in ev if not (e[0] == "NQ" and e[2] == "Core CPI")] + [["NQ", "US", "Core CPI", "2026-11-04", "2.6%"]]
    assert _cells(C.fill(md, TODAY, TODAY, NOW, ev_bad)[0], "10月CPI")[2] == "—"


def test_dates_must_be_within_a_day_and_rows_within_window():
    ev = [["FF", "US", "Unemployment Claims", "2026-11-12", "205K"]]          # 下一週的初領，不能補到這一週
    assert _cells(C.fill(MD, TODAY, TODAY, NOW, ev)[0], "初領")[2] == "—"
    far = date(2026, 10, 20)                                                # 列都超過 10 天以後 → 不補
    assert C.fill(MD, TODAY, far, NOW, EV)[0] == MD


def test_note_line_is_updated_in_place():
    md = MD.replace("- 本表僅供參考", "- 預期自動補（11/03 06:50；市場共識、非官方）：美：10月ISM服務業PMI 54.8（ForexFactory）。\n- 本表僅供參考")
    new, _ = C.fill(md, TODAY, TODAY, NOW, EV)
    notes = [ln for ln in new.split("\n") if ln.startswith(C.NOTE_HEAD)]
    assert len(notes) == 1 and notes[0].startswith("- 預期自動補（11/03 21:30；")
    assert "美：10月ISM服務業PMI 54.8（ForexFactory）" in notes[0] and "715萬" in notes[0]


def test_event_dates_are_local_dates():
    ff = C._ev_ff([{"title": "RatingDog Services PMI", "country": "CNY", "date": "2026-11-03T20:45:00-05:00",
                    "impact": "Medium", "forecast": "51.7", "previous": "51.6"},
                   {"title": "Unemployment Claims", "country": "USD", "date": "2026-11-05T08:30:00-05:00",
                    "impact": "Medium", "forecast": "197K", "previous": "194K"},
                   {"title": "Loan Officer Survey", "country": "USD", "date": "2026-11-02T14:00:00-05:00",
                    "impact": "Low", "forecast": "", "previous": ""}])
    assert ff == [["FF", "CN", "RatingDog Services PMI", "2026-11-04", "51.7"],
                  ["FF", "US", "Unemployment Claims", "2026-11-05", "197K"]]
    nq = C._ev_nq([{"gmt": "09:00", "country": "United States", "eventName": "JOLTS Job Openings",
                    "consensus": "7.150M"},
                   {"gmt": "20:45", "country": "China", "eventName": "RatingDog Services PMI", "consensus": "51.7"},
                   {"gmt": "24H", "country": "Japan", "eventName": "Household Confidence", "consensus": " "},
                   {"gmt": "09:00", "country": "Brazil", "eventName": "X", "consensus": "1"}], date(2026, 11, 4))
    assert nq == [["NQ", "US", "JOLTS Job Openings", "2026-11-03", "7.150M"],
                  ["NQ", "CN", "RatingDog Services PMI", "2026-11-04", "51.7"]]


class _Snap:
    def __init__(self):
        self.d = {}

    def save(self, name, src, d):
        self.d[name] = dict(d)
        return True

    def load(self, name):
        return dict(self.d.get(name) or {})


def test_run_fetches_writes_and_reuses_snapshot(tmp_path, monkeypatch):
    snap = _Snap()
    monkeypatch.setattr(C, "HD", snap)
    f = tmp_path / "2026-11-03.md"
    f.write_text(MD, encoding="utf-8")
    ff = [{"title": "JOLTS Job Openings", "country": "USD", "date": "2026-11-03T10:00:00-05:00", "forecast": "7.15M"}]
    nq = {"rows": [{"gmt": "09:00", "country": "United States", "eventName": "JOLTS Job Openings", "consensus": "7.150M"}]}
    asked = []

    def get(url):
        asked.append(url)
        if "faireconomy" in url:
            return json.dumps(ff).encode()
        return json.dumps({"data": nq if url.endswith("2026-11-04") else {"rows": []}}).encode()

    r = C.run(TODAY, NOW, cal_dir=tmp_path, get=get, pause=0)
    assert r["wrote"] and _cells(f.read_text(encoding="utf-8"), "JOLTS")[2] == "715萬*"
    assert any("faireconomy" in u for u in asked) and any("2026-11-04" in u for u in asked)
    assert snap.d["calcons"]["ev"]
    # push 被拒重算（--no-fetch）：用剛存的事件
    f.write_text(MD, encoding="utf-8")
    r2 = C.run(TODAY, NOW, cal_dir=tmp_path, fetch=False)
    assert r2["wrote"] and _cells(f.read_text(encoding="utf-8"), "JOLTS")[2] == "715萬*"
    # 兩天前存的不用
    f.write_text(MD, encoding="utf-8")
    snap.d["calcons"]["as_of"] = "2026-10-31T21:30"
    r3 = C.run(TODAY, NOW, cal_dir=tmp_path, fetch=False)
    assert not r3["wrote"] and f.read_text(encoding="utf-8") == MD


def test_run_survives_both_sources_failing(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "HD", _Snap())
    (tmp_path / "2026-11-03.md").write_text(MD, encoding="utf-8")

    def get(url):
        raise RuntimeError("HTTP Error 403")

    r = C.run(TODAY, NOW, cal_dir=tmp_path, get=get, pause=0)
    assert not r["wrote"] and any("ForexFactory 抓取失敗" in x for x in r["log"])
