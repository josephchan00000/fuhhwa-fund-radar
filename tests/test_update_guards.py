"""資料更新防呆單測：台北時區單一來源（arm/clock）＋ fundnews 空結果不覆寫。"""
import json
from datetime import date, timedelta, timezone

from arm import clock, fundnews


# ── arm/clock：台北時區 ───────────────────────────────────────
def test_clock_is_taipei_tz():
    assert clock.TW_TZ.utcoffset(None) == timedelta(hours=8)
    n = clock.now_tw()
    assert n.tzinfo is not None and n.utcoffset() == timedelta(hours=8)
    assert isinstance(clock.today_tw(), date)
    # UTC 20:00 = 台北隔日 04:00 → today_tw 必須等於「UTC 時間 +8h」的日期
    assert clock.today_tw() == (n.astimezone(timezone.utc) + timedelta(hours=8)).date()


# ── fundnews：全空結果不得覆寫非空落檔 ───────────────────────
def _doc(brand=None, items=None, social=None):
    return {"as_of": "2026/07/04 05:00", "window_days": 7, "source": "test",
            "brand": brand or [], "social": social or [],
            "funds": [{"fund_id": "47", "items": items or []}], "highlights": []}


def test_fundnews_is_empty():
    assert fundnews.is_empty(None)
    assert fundnews.is_empty(_doc())
    assert not fundnews.is_empty(_doc(brand=[{"title": "x"}]))
    assert not fundnews.is_empty(_doc(items=[{"title": "x"}]))
    assert not fundnews.is_empty(_doc(social=[{"title": "x"}]))


def test_fundnews_save_keeps_previous_when_empty(tmp_path, monkeypatch):
    out = tmp_path / "fund_news.json"
    monkeypatch.setattr(fundnews, "OUT", out)

    # 先落一份非空
    path, saved = fundnews.save(_doc(brand=[{"title": "既有新聞"}]))
    assert saved and json.loads(out.read_text(encoding="utf-8"))["brand"]

    # 全空結果（如網路被擋）→ 不覆寫、舊資料仍在
    path, saved = fundnews.save(_doc())
    assert not saved
    assert json.loads(out.read_text(encoding="utf-8"))["brand"] == [{"title": "既有新聞"}]

    # 非空結果 → 正常覆寫
    path, saved = fundnews.save(_doc(brand=[{"title": "新一批"}]))
    assert saved
    assert json.loads(out.read_text(encoding="utf-8"))["brand"] == [{"title": "新一批"}]


def test_fundnews_save_empty_when_no_previous(tmp_path, monkeypatch):
    """無既有落檔時，全空 doc 仍要落檔（首跑標 as-of、儀表板顯示提示）。"""
    out = tmp_path / "fund_news.json"
    monkeypatch.setattr(fundnews, "OUT", out)
    path, saved = fundnews.save(_doc())
    assert saved and out.exists()
