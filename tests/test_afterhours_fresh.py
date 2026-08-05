"""盤後「當日完整性」看門狗（scripts/check_afterhours_fresh.py）。

2026-08-03 根因回歸：三大法人當日沒更新時，run 全綠、無 commit、無警示——
使用者自己打開網頁才發現。這裡守住「時間到了、該在而不在 → 看得見的失敗」。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime
from pathlib import Path

from arm import clock

_SPEC = importlib.util.spec_from_file_location(
    "check_afterhours_fresh",
    Path(__file__).resolve().parent.parent / "scripts" / "check_afterhours_fresh.py")
af = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(af)

_MON = date(2026, 8, 3)                       # 週一（實際踩坑日）
_CAL_OK = "> 更新：2026/08/03；市況：台股 正常交易｜美股 正常交易｜日股 正常交易；後市焦點…"
_CAL_CLOSED = "> 更新：2026/10/10；市況：台股 10/10 因國慶日休市｜美股 正常交易；…"


def _tw(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=clock.TW_TZ)


def _chips(inst_days=(), margin_days=(), as_of=""):
    return {"as_of": as_of,
            "series": {"inst_total": {d: 1.0 for d in inst_days},
                       "margin_bal": {d: 1.0 for d in margin_days}}}


def _index(nav="2026/07/31"):
    return {"funds": [{"nav_date": nav}, {"nav_date": "2026/07/30"}]}


# ── 交易日判定 ──────────────────────────────────────────────

def test_trading_day_平日且市況正常():
    assert af.is_trading_day(_MON, _CAL_OK) is True


def test_trading_day_市況寫休市就不是交易日():
    assert af.is_trading_day(date(2026, 10, 9), _CAL_CLOSED) is False


def test_trading_day_週末一律非交易日():
    assert af.is_trading_day(date(2026, 8, 2), _CAL_OK) is False


def test_trading_day_行事曆缺檔視為交易日_寧可誤報不靜默():
    assert af.is_trading_day(_MON, None) is True


# ── 時窗斷言 ────────────────────────────────────────────────

def test_missing_1630前不斷言():
    got = af.compute_missing(_tw(2026, 8, 3, 16, 0), _chips(), _index(), trading=True)
    assert got == []


def test_missing_1630後當日三大法人缺席要抓出來():
    got = af.compute_missing(_tw(2026, 8, 3, 16, 45),
                             _chips(inst_days=("2026-07-31",)), _index(), trading=True)
    assert got == ["當日三大法人買賣超"]


def test_missing_當日已在就無缺口():
    got = af.compute_missing(_tw(2026, 8, 3, 16, 45),
                             _chips(inst_days=("2026-08-03",)), _index(), trading=True)
    assert got == []


def test_missing_2245後驗融資融券與NAV():
    got = af.compute_missing(
        _tw(2026, 8, 3, 22, 50),
        _chips(inst_days=("2026-08-03",), margin_days=("2026-07-31",)),
        _index(nav="2026/07/30"), trading=True)          # 週一晚 NAV 最新僅上週四＝斷更
    assert "當日融資融券餘額" in got
    assert any(x.startswith("基金 NAV") for x in got)


def test_missing_NAV到上一交易日即可_T加1不誤報():
    got = af.compute_missing(
        _tw(2026, 8, 3, 22, 50),
        _chips(inst_days=("2026-08-03",), margin_days=("2026-08-03",)),
        _index(nav="2026/07/31"), trading=True)          # 週一晚最新＝上週五 → 正常 T+1
    assert got == []


def test_missing_非交易日一律無缺口():
    got = af.compute_missing(_tw(2026, 8, 2, 23, 0), _chips(), _index(), trading=False)
    assert got == []


# ── 抓取守門（重複場次零請求早退） ──────────────────────────

def test_guard_午後窗當日籌碼已在就SKIP():
    c = _chips(inst_days=("2026-08-03",))
    assert af.guard_decision(_tw(2026, 8, 3, 17, 10), c, trading=True) == "SKIP"


def test_guard_午後窗當日籌碼未到要RUN():
    c = _chips(inst_days=("2026-07-31",))
    assert af.guard_decision(_tw(2026, 8, 3, 15, 38), c, trading=True) == "RUN"


def test_guard_晚間窗30分內剛跑過就SKIP_超過要RUN():
    c = _chips(inst_days=("2026-08-03",), as_of="2026-08-03 19:05")
    assert af.guard_decision(_tw(2026, 8, 3, 19, 20), c, trading=True) == "SKIP"
    assert af.guard_decision(_tw(2026, 8, 3, 22, 10), c, trading=True) == "RUN"


def test_guard_晚間窗不受午後籌碼已在影響():
    # 18:00 後就算 inst 已是今日，仍要 RUN（晚間目標是 NAV／融資融券）
    c = _chips(inst_days=("2026-08-03",), as_of="2026-08-03 15:45")
    assert af.guard_decision(_tw(2026, 8, 3, 18, 58), c, trading=True) == "RUN"


# ── 警示檔寫/清（不製造空 commit） ──────────────────────────

def test_write_alert_健康且本來乾淨不動檔(tmp_path, monkeypatch):
    monkeypatch.setattr(af, "ALERT_FP", tmp_path / "afterhours_alert.json")
    assert af.write_alert([], _MON) is False
    assert not (tmp_path / "afterhours_alert.json").exists()


def test_write_alert_缺口要落檔_同內容不重寫_復原要清空(tmp_path, monkeypatch):
    fp = tmp_path / "afterhours_alert.json"
    monkeypatch.setattr(af, "ALERT_FP", fp)
    assert af.write_alert(["當日三大法人買賣超"], _MON) is True
    doc = json.loads(fp.read_text(encoding="utf-8"))
    assert doc == {"date": "2026-08-03", "missing": ["當日三大法人買賣超"]}
    assert af.write_alert(["當日三大法人買賣超"], _MON) is False      # 同內容不重寫
    assert af.write_alert([], _MON) is True                            # 復原 → 清空
    assert json.loads(fp.read_text(encoding="utf-8"))["missing"] == []


# ── 儀表板端（紅章＋瀏覽器橫幅） ────────────────────────────

def _alert_file(tmp_path, doc):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "afterhours_alert.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def test_儀表板紅章_今日缺口要亮_昨日殘留與健康不亮(tmp_path, monkeypatch):
    from arm import fund_dashboard as fd
    monkeypatch.setattr(fd, "ROOT_DIR", tmp_path)
    _alert_file(tmp_path, {"date": "2026-08-03", "missing": ["當日三大法人買賣超"]})
    chip = fd._afterhours_chip(today=_MON)
    assert "盤後更新" in chip and "當日三大法人買賣超" in chip and "stale" in chip
    assert fd._afterhours_chip(today=date(2026, 8, 4)) == ""           # 昨日殘留不亮
    _alert_file(tmp_path, {"date": "2026-08-03", "missing": []})
    assert fd._afterhours_chip(today=_MON) == ""                       # 健康不亮


def test_儀表板紅章有掛進網頁更新時間列():
    from arm import fund_dashboard as fd
    import inspect
    src = inspect.getsource(fd._freshness_view)
    assert "_afterhours_chip" in src


def test_瀏覽器端盤後時窗橫幅存在_且逾期橫幅只剩一份():
    """2026-08-03：①加盤後時窗警示（cron 遲到／整班消失時唯一看得到的地方）；
    ②原本兩份一模一樣的「未重建」IIFE 逾期時會 prepend 兩條橫幅——去重後只准一份。"""
    from arm import fund_dashboard as fd
    assert fd._JS.count("盤後數據（三大法人・ETF 當日漲跌）尚未上線") == 1
    assert fd._JS.count("夜間數據（融資融券・基金NAV）尚未上線") == 1
    assert fd._JS.count("天未重建（每日 CI 可能停擺）") == 1


def test_guard_清晨窗美股收盤場次_30分內剛跑過SKIP_否則RUN():
    """2026-08-05 新增台北 05:20 cron（美股收盤兜底）：05:08 Routine dispatch 剛成功
    → 零請求早退；沒跑過（Routine 失敗）→ RUN。台股 trading 與否不影響——
    美股交易日與台股休市互相獨立（台北週六清晨也要抓週五美股收盤）。"""
    c = _chips(as_of="2026-08-05 05:10")
    assert af.guard_decision(_tw(2026, 8, 5, 5, 20), c, trading=True) == "SKIP"
    assert af.guard_decision(_tw(2026, 8, 5, 6, 40), c, trading=True) == "RUN"    # 遲到逾 30 分
    assert af.guard_decision(_tw(2026, 8, 5, 5, 20), _chips(), trading=True) == "RUN"
    sat = _chips(as_of="2026-08-08 05:09")                                        # 週六清晨
    assert af.guard_decision(_tw(2026, 8, 8, 5, 20), sat, trading=False) == "SKIP"
