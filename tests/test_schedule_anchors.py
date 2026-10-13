"""核心排程錨（config/official_schedule.json，資料可信度盤查 Phase 3，2026-10-13）。

行事曆日期原本全靠搜尋摘要；核心事件（央行決議、美國 CPI／非農、台灣官方數據）改以排程檔為準。
這裡守：檔案本身合格（每筆有來源與層級、次級來源至少兩個）、還沒用完、比對與閘門的行為。"""
import importlib
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from arm import clock, macronews  # noqa: E402


def test_schedule_file_is_well_formed():
    evs = macronews.load_schedule()
    assert evs, "config/official_schedule.json 讀不到或為空"
    for e in evs:
        assert e["region"] in {"美", "歐", "中", "日", "台"}, e
        assert e["item"] and e["match"] and all(isinstance(g, list) and g for g in e["match"]), e
        assert e["level"] in {"official", "secondary"}, e
        urls = re.findall(r"https?://\S+", e["source"])
        assert urls, f"{e['item']} 缺來源連結"
        if e["level"] == "secondary":           # 非官方須兩家主流媒體一致（使用者 2026-10-13 同意的收錄門檻）
            assert len(urls) >= 2, f"{e['item']} 標 secondary 但來源不足兩個"


def test_schedule_not_running_out():
    # 排程檔是手工維護的有限清單：最後一筆在 21 天內就要補下一段（各央行／BLS 隔年排程年初前都已公布）
    last = max(e["d"] for e in macronews.load_schedule())
    assert last >= clock.today_tw() + timedelta(days=21), \
        f"排程錨只到 {last}——依官方排程補下一段（FOMC／ECB／BOJ／BLS／主計總處等）"


def test_anchor_matches_region_and_keywords():
    cpi = {"region": "美", "item": "9月CPI", "match": [["9月", "CPI"]]}
    assert macronews.anchor_matches(cpi, {"region": "美", "item": "9月CPI（年增；月增／核心月增）"})
    assert not macronews.anchor_matches(cpi, {"region": "中", "item": "9月CPI（年增）"})   # 前綴不同＝別國數據
    fomc = {"region": "美", "item": "FOMC", "match": [["FOMC"], ["聯準會", "利率"], ["Fed", "利率決議"]]}
    assert macronews.anchor_matches(fomc, {"region": "美", "item": "聯準會利率決議（10/27–28）"})
    assert macronews.anchor_matches(fomc, {"region": "美", "item": "fomc 利率決議"})        # 大小寫不拘
    jan = {"region": "美", "item": "1月CPI", "match": [["1月", "CPI"]]}
    assert macronews.anchor_matches(jan, {"region": "美", "item": "1月CPI（年增）"})
    assert not macronews.anchor_matches(jan, {"region": "美", "item": "11月CPI（年增）"})   # 月份整詞比
    feb = {"region": "美", "item": "2月CPI", "match": [["2月", "CPI"]]}
    assert not macronews.anchor_matches(feb, {"region": "美", "item": "12月CPI"})


_EVS = [{"d": date(2026, 10, 14), "date": "2026-10-14", "region": "美", "item": "9月CPI",
         "match": [["9月", "CPI"]], "level": "official", "source": "https://www.bls.gov/x", "time": ""}]


def _cal(rows: str, notes: str = "") -> str:
    return ("# 本週重點財經行事曆（10/12–10/16）\n> 更新：2026/10/14；市況：台股 正常交易\n\n"
            "| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n" + rows + "\n\n註：\n" + notes)


def test_check_reports_anchor_gate(monkeypatch):
    check = importlib.import_module("check_reports")
    monkeypatch.setattr(macronews, "load_schedule", lambda *a, **k: _EVS)
    ok = _cal("| 10/14 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |")
    assert check._check_calendar_anchors(ok, "c.md", "2026-10-14") == []
    missing = _cal("| 10/14 | 美：Fed褐皮書 | — | — | — | 未公布 |")
    assert any("沒列" in e for e in check._check_calendar_anchors(missing, "c.md", "2026-10-14"))
    moved = _cal("| 10/15 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |")
    assert any("排程錨為 10/14" in e for e in check._check_calendar_anchors(moved, "c.md", "2026-10-14"))
    explained = _cal("| 10/15 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |",
                     "- 修正：9月CPI——BLS 公告改期至 10/15（bls.gov）\n")
    assert check._check_calendar_anchors(explained, "c.md", "2026-10-14") == []
    other_week = ok.replace("10/12–10/16", "10/19–10/23")
    assert check._check_calendar_anchors(other_week, "c.md", "2026-10-20") == []   # 該週沒有錨＝不檢查


def test_cal_prompt_carries_week_anchors(monkeypatch):
    import gen_macronews
    monkeypatch.setattr(macronews, "load_schedule", lambda *a, **k: _EVS)
    p = gen_macronews.build_cal_prompt(date(2026, 10, 13))
    assert "【本週核心排程錨" in p and "10/14（週三）美：9月CPI［官方］" in p
    assert "【本週核心排程錨" not in gen_macronews.build_cal_prompt(date(2026, 10, 20))
