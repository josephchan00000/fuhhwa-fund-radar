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


# ── fund_dashboard：鮮度徽章（逾期標紅；頂欄只標網頁更新時間、其餘分散各區塊） ──
def test_age_days_parses_both_formats():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 4)
    assert fd._age_days("2026/07/02", t) == 2
    assert fd._age_days("2026-07-03 08:17", t) == 1
    assert fd._age_days("2026/07/04 11:12", t) == 0
    assert fd._age_days(None, t) is None
    assert fd._age_days("—", t) is None


def test_fresh_chip_marks_stale_and_gen():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 10)
    assert "⚠ 9 天未更新" in fd._fresh_chip("NAV 日", "2026/07/01", 6, today=t)      # 9 > 6 → 標紅
    assert "stale" not in fd._fresh_chip("台股新聞", "2026-07-09", 3, today=t)       # 1 天前 → 正常
    assert "⚠ 缺資料" in fd._fresh_chip("基金新聞", None, 3, today=t)                # 缺值 → 標紅
    chip = fd._fresh_chip("網頁更新", "2026/07/10 06:50", None, today=t, gen=True)   # 帶 data-gen
    assert 'data-gen="2026/07/10 06:50"' in chip and "stale" not in chip


def test_freshness_view_top_shows_gen_and_aggregates_stale():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 10)
    html_out = fd._freshness_view("2026/07/10 06:50", [
        ("NAV 日", "2026/07/01", 6),        # 9 天前 > 6 → 逾期
        ("台股新聞", "2026-07-09", 3),       # 正常
        ("基金新聞・社群", None, 3),          # 缺值 → 逾期
    ], today=t)
    assert "網頁更新時間" in html_out and 'data-gen="2026/07/10 06:50"' in html_out
    assert "2 項資料逾期未更新" in html_out
    assert "NAV 日、基金新聞・社群" in html_out


def test_freshness_view_all_fresh_no_warning():
    from arm import fund_dashboard as fd
    t = date(2026, 7, 4)
    html_out = fd._freshness_view("2026/07/04 11:12", [("NAV 日", "2026/07/03", 6),
                                                       ("台股新聞", "2026-07-04", 3)], today=t)
    assert "stale" not in html_out and "逾期" not in html_out
