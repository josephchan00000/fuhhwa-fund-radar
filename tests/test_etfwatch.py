"""ETF 數據追蹤（arm/etfwatch＋儀表板第四分頁）測試——離線、吃 repo 內種子落檔。"""
import json
from datetime import date

from arm import etfwatch, fund_dashboard


# ── 數值解析與規模單位正規化 ─────────────────────────────────

def test_num_parses_display_strings():
    assert etfwatch._num("+3.32%") == 3.32
    assert etfwatch._num("-0.93%") == -0.93
    assert etfwatch._num("7,270.42") == 7270.42
    assert etfwatch._num("2兆2413億") == 22413.0
    assert etfwatch._num("4658.56億") == 4658.56
    assert etfwatch._num("N/A") is None and etfwatch._num("—") is None
    assert etfwatch._num(None) is None


def test_norm_aum_prefers_unit_closest_to_previous():
    # 既有值 7270 億：元／百萬／億三種進位都應正規化回 ~7270
    assert abs(etfwatch._norm_aum_e8(7.27042e11, 7270.0) - 7270.42) < 1
    assert abs(etfwatch._norm_aum_e8(727042.0, 7270.0) - 7270.42) < 1
    assert abs(etfwatch._norm_aum_e8(7270.42, 7270.0) - 7270.42) < 0.01
    # 無既有值時用門檻猜：31.94 億的元計數 → 億
    assert abs(etfwatch._norm_aum_e8(3.194e9, None) - 31.94) < 0.01


def test_annualized_yield_from_latest_dividend_price_and_freq():
    # 最新一次配息（依除息日取最近）÷ 最新市價 × 年配息次數
    divs = [{"exDate": "2025-04-15", "amount": 0.5},
            {"exDate": "2026-01-15", "amount": 0.6},   # 最近一次 → 用 0.6
            {"exDate": "2025-10-15", "amount": 0.55}]
    assert etfwatch._latest_dividend(divs) == 0.6
    assert etfwatch._annualized_yield(divs, 20.0, "季配") == 12.0   # 0.6/20*4*100
    assert etfwatch._annualized_yield(divs, 20.0, "月配") == 36.0   # ×12
    assert etfwatch._annualized_yield(divs, 20.0, "年配") == 3.0    # ×1
    # 缺配息／市價／頻率 → None
    assert etfwatch._annualized_yield([], 20.0, "季配") is None
    assert etfwatch._annualized_yield(divs, None, "季配") is None
    assert etfwatch._annualized_yield(divs, 20.0, None) is None


def test_returns_computed_from_twse_daily_close(monkeypatch):
    # 過去一週(7 日曆日)／一月(30 日曆日)報酬＝最新收盤對回推日前最後交易日收盤計算
    series = [("2026-06-05", 20.0, 0),   # <=06/06（一月前）最後交易日 → 1月基準
              ("2026-06-29", 23.0, 0),   # <=06/29（一週前）最後交易日 → 1週基準
              ("2026-07-06", 24.0, 0)]   # 最新交易日
    import arm.connectors.twse as twse
    monkeypatch.setattr(twse, "fetch_month", lambda code, y, m: series)
    r = etfwatch._fetch_returns("0056", today=date(2026, 7, 6))
    assert r["ret_1w"] == round((24.0 / 23.0 - 1) * 100, 2)   # 4.35%
    assert r["ret_1m"] == round((24.0 / 20.0 - 1) * 100, 2)   # 20.0%
    assert r["perf_date"] == "2026-07-06"


def test_returns_none_when_twse_has_no_history(monkeypatch):
    import arm.connectors.twse as twse
    monkeypatch.setattr(twse, "fetch_month", lambda code, y, m: [])   # 上櫃檔／休市初
    r = etfwatch._fetch_returns("0056", today=date(2026, 7, 6))
    assert r == {"ret_1w": None, "ret_1m": None, "perf_date": None}


# ── 追蹤清單與種子落檔（repo 內真實檔） ───────────────────────

def test_watchlist_matches_weekly_report():
    codes = [c for c, *_ in etfwatch.WATCHLIST]
    assert len(codes) == len(set(codes)) == 17
    passive = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "passive"]
    active = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "active"]
    assert set(passive) == {"0056", "00878", "00919", "00929", "0050", "006208"}
    assert "00991A" in active and len(active) == 11    # 含本家主動復華未來50
    # 成立日期為 WATCHLIST 靜態值（不需抓、永不空白）
    for c, name, kind, cat, inception in etfwatch.WATCHLIST:
        assert inception and inception.count("/") == 2


def test_seed_perf_covers_every_watchlist_code():
    # 內建週報底稿要涵蓋每一檔（來源全倒時的最後 fallback，避免整片留空）
    assert set(etfwatch.SEED_PERF) == {c for c, *_ in etfwatch.WATCHLIST}
    for code, base in etfwatch.SEED_PERF.items():
        assert base.get("ret_1w") is not None and base.get("ret_1m") is not None


def test_seed_file_loads_and_covers_watchlist():
    doc = etfwatch.load()
    assert doc and not etfwatch.is_empty(doc)
    by_code = {i["code"]: i for i in doc["items"]}
    assert set(by_code) == {c for c, *_ in etfwatch.WATCHLIST}
    # 每檔的成立日期／週報酬／月報酬／規模一律有值（不再整片留空）
    for i in doc["items"]:
        assert i.get("inception") and i.get("ret_1w") is not None
        assert i.get("ret_1m") is not None and i.get("aum_e8") is not None
    assert by_code["0056"]["ret_1w"] == 3.32 and by_code["0056"]["freq"] == "季配"
    assert by_code["00994A"]["ret_1w"] == -0.93        # 唯一週線收黑


# ── 防呆：全空不覆寫（同 fundnews 教訓） ──────────────────────

def test_save_guard_keeps_nonempty_file(tmp_path, monkeypatch):
    out = tmp_path / "etf_watch.json"
    monkeypatch.setattr(etfwatch, "OUT", out)
    good = {"as_of": "2026-07-03", "items": [{"code": "0056", "aum_e8": 7270.0}]}
    _, saved = etfwatch.save(good)
    assert saved
    empty = {"as_of": "2026-07-06", "items": [{"code": "0056"}]}   # 全欄位空 → 來源異常
    _, saved = etfwatch.save(empty)
    assert not saved
    assert json.loads(out.read_text())["as_of"] == "2026-07-03"   # 舊檔完好


def _boom(*a, **k):
    raise RuntimeError("CONNECT 403")


def _down_both(monkeypatch):
    """兩來源皆不可達（etfinfo 規模／殖利率 ＋ TWSE 報酬）。"""
    monkeypatch.setattr(etfwatch, "_fetch_market", _boom)
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)


def test_fetch_falls_back_to_seed_when_source_down_and_no_file(monkeypatch):
    # 兩來源全倒＋既有落檔不存在 → 純靠內建 SEED_PERF 週報底稿，仍每檔有值、不整片留空
    monkeypatch.setattr(etfwatch, "load", lambda: None)
    _down_both(monkeypatch)
    doc = etfwatch.fetch()
    by_code = {i["code"]: i for i in doc["items"]}
    assert by_code["00929"]["ret_1w"] == 4.03 and by_code["00929"]["src"] == "seed"
    assert by_code["00929"]["inception"] == "2023/06/01"     # 靜態成立日
    assert doc["perf_asof"] == etfwatch.SEED_ASOF
    assert not etfwatch.is_empty(doc) and "不可達" in doc["source"]
    for i in doc["items"]:                                    # 無一欄位留空
        assert i.get("inception") and i.get("ret_1w") is not None and i.get("aum_e8") is not None


def test_fetch_does_not_wipe_existing_values_with_nulls(monkeypatch):
    # 既有落檔某欄位是顯式 null（CI 曾寫過）→ 不可用 null 覆蓋，要退回週報底稿
    prev = {"items": [{"code": "0056", "aum_e8": 7243.74, "ret_1w": None,
                       "ret_1m": None, "yield_pct": 7.51, "freq": "季配", "src": "etfinfo"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    _down_both(monkeypatch)
    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0056"]
    assert i["ret_1w"] == 3.32 and i["ret_1m"] == 15.17       # 由 SEED_PERF 補回，非 null
    assert i["aum_e8"] == 7243.74 and i["inception"] == "2007/12/13"


# ── 儀表板第四分頁（吃 repo 內種子檔，離線） ──────────────────

def test_dashboard_has_etf_tab_and_tables():
    html = fund_dashboard.render()
    assert 'for="mkt-etf">ETF<' in html                 # 左上第四分頁
    assert 'id="mkt-etf"' in html                       # 純 CSS radio
    assert '#mkt-etf:checked ~ * .fundview{display:none}' in html.replace(
        "#mkt-macro:checked ~ * .fundview,", "")        # 分頁互斥規則存在
    assert 'id="etfwatch"' in html and "ETF 數據追蹤" in html
    assert 'id="etf-passive"' in html and 'id="etf-active"' in html
    assert "00919" in html and "主動中信台灣卓越" in html
    assert html.count('class="mine"') >= 2              # 00929＋00991A 本家高亮
    assert "minepill" in html
    assert "非投資建議" in html
    # 成立日期不空白（靜態值直接進表）＋殖利率缺值顯示「尚無配息」而非 bare「—」
    assert "2007/12/13" in html and "2025/12/09" in html
    assert "尚無配息" in html
    assert "報酬基準" in html                            # 資料時間備注（規模／殖利率 vs 報酬基準日）
    # 可點擊人工驗證：逐檔代碼連 Yahoo、註腳連 etfinfo.tw 與 TWSE 官方
    assert "tw.stock.yahoo.com/quote/0056" in html      # 每列代碼可點對照
    assert "etfinfo.tw" in html and "twse.com.tw" in html
    assert "stock-day" in html                          # TWSE 官方每日收盤（報酬來源）
