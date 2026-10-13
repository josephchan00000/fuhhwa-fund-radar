"""行事曆「以昨日版為底稿」＋漂移閘門（資料可信度盤查 Phase 2，2026-10-13）。

回測：同週相鄰兩版行事曆裡，日期來回翻（Ifo 08/25→08/24→08/25）、已公布實際值被改寫
（8 月失業率 4.3%→4.1%、時薪 3.7%→3.1%）卻沒有任何交代。這裡守偵測的準度——真改動要抓到、
換順序／補細節／精度不同／談話要點換句話說都不能誤報。"""
import importlib
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from arm import macronews  # noqa: E402

_HEAD = "# 本週重點財經行事曆（10/12–10/16）\n> 更新：2026/10/1{d}；市況：台股 正常交易\n\n| 日期 | 項目 | 預期 | 實際 | 前值 | 狀態 |\n|---|---|---|---|---|---|\n"


def _cal(day: int, rows: list[str], notes: str = "") -> str:
    return _HEAD.format(d=day) + "\n".join(rows) + "\n\n註：\n" + notes


def test_target_week_and_prior_lookup(tmp_path):
    assert macronews.target_week_start(date(2026, 10, 14)) == date(2026, 10, 12)
    assert macronews.target_week_start(date(2026, 10, 10)) == date(2026, 10, 12)   # 週六的檔是下週預覽
    (tmp_path / "2026-10-09.md").write_text("# 本週重點財經行事曆（10/05–10/09）\n", encoding="utf-8")
    (tmp_path / "2026-10-10.md").write_text("# 本週重點財經行事曆（10/12–10/16）\nsat\n", encoding="utf-8")
    (tmp_path / "2026-10-13.md").write_text("# 本週重點財經行事曆（10/12–10/16）\ntue\n", encoding="utf-8")
    got = macronews.prior_cal(date(2026, 10, 14), cal_dir=tmp_path)
    assert got and got[0] == date(2026, 10, 13)
    got = macronews.prior_cal(date(2026, 10, 12), cal_dir=tmp_path)
    assert got and got[0] == date(2026, 10, 10)                       # 週一的底稿＝週末預覽版
    assert macronews.prior_cal(date(2026, 10, 5), cal_dir=tmp_path) is None


def test_drift_catches_real_changes_only():
    prev = _cal(3, [
        "| 10/14 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |",
        "| 10/12 | 美：8月失業率 | 4.3% | 4.3%（2021年以來新高） | 4.2% | 已公布 |",
        "| 10/12 | 美：7月JOLTS職缺 | — | 727萬 | 740萬 | 已公布 |",
        "| 10/12 | 財報：PLTR Q3財報 | — | 營收19.4億美元/EPS 0.41 | — | 已公布 |",
        "| 10/12 | 美：Fed理事沃勒談話 | — | 支持9月維持利率不變 | — | 已公布 |",
        "| 10/12 | 美：9月PPI（月增） | +0.3% | +0.4% | +0.2% | 已公布 |",
    ])
    cur = _cal(4, [
        "| 10/15 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |",          # 日期改了 → 抓
        "| 10/12 | 美：8月失業率 | 4.3% | 4.1%（與7月持平） | 4.2% | 已公布 |",      # 實際值數字改了 → 抓
        "| 10/12 | 美：7月JOLTS職缺 | — | 727.1萬 | 740萬 | 已公布 |",               # 精度不同 → 不抓
        "| 10/12 | 財報：PLTR Q3財報 | — | EPS 0.41美元、營收19.4億美元、年增63% | — | 已公布 |",  # 換順序＋補細節 → 不抓
        "| 10/12 | 美：Fed理事沃勒談話 | — | 視8月CPI數據決定按兵不動 | — | 已公布 |",  # 談話換句話說 → 不抓
        "| 10/12 | 美：9月PPI（月增） | +0.3% | — | +0.2% | 未公布 |",              # 已公布退回未公布 → 抓
    ])
    got = {(d["item"], d["kind"]) for d in macronews.cal_drift(prev, cur)}
    assert got == {("9月CPI（年增）", "日期"), ("8月失業率", "實際值"), ("9月PPI（月增）", "狀態")}


def test_drift_explained_by_correction_note():
    d = {"item": "8月失業率", "kind": "實際值", "old": "4.3%", "new": "4.1%"}
    assert not macronews.drift_explained(d, _cal(4, ["| 10/12 | 美：8月失業率 | — | 4.1% | — | 已公布 |"]))
    noted = _cal(4, ["| 10/12 | 美：8月失業率 | — | 4.1% | — | 已公布 |"],
                 "- 修正：8月失業率——原 4.3% 改為 4.1%（BLS 新聞稿）\n")
    assert macronews.drift_explained(d, noted)


def test_check_reports_drift_gate(tmp_path, monkeypatch):
    check = importlib.import_module("check_reports")
    mc = tmp_path / "reports" / "macrocal"
    mc.mkdir(parents=True)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    (mc / "2026-10-13.md").write_text(_cal(3, ["| 10/14 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |"]),
                                      encoding="utf-8")
    moved = _cal(4, ["| 10/15 | 美：9月CPI（年增） | +3.6%* | — | +3.4% | 未公布 |"])
    errs = check._check_calendar_drift(moved, "c.md", "2026-10-14")
    assert len(errs) == 1 and "9月CPI" in errs[0] and "修正" in errs[0]
    ok = moved + "- 修正：9月CPI——BLS 公告改期至 10/15（bls.gov）\n"
    assert check._check_calendar_drift(ok, "c.md", "2026-10-14") == []
    assert check._check_calendar_drift(moved, "c.md", "2026-10-12") == []   # 週一第一份：沒有同週前版 → 不比


def test_cal_prompt_carries_yesterday(monkeypatch):
    import gen_macronews
    monkeypatch.setattr(macronews, "prior_cal", lambda *a, **k: (date(2026, 10, 12), "# 本週重點財經行事曆（10/12–10/16）\nYESTERDAY"))
    p = gen_macronews.build_cal_prompt(date(2026, 10, 13))
    assert "以昨日版為底稿增修" in p and "【同週昨日版（2026/10/12）】" in p and "YESTERDAY" in p
    monkeypatch.setattr(macronews, "prior_cal", lambda *a, **k: None)
    assert "同週昨日版（" not in gen_macronews.build_cal_prompt(date(2026, 10, 12))
