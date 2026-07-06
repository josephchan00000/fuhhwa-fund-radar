"""ETF 數據追蹤（arm/etfwatch＋儀表板第四分頁）測試——離線、吃 repo 內種子落檔。"""
import json

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


def test_ret_from_stats_dict_and_list_shapes():
    assert etfwatch._ret_from_stats({"week": 3.32, "month": 15.17},
                                    etfwatch._WEEK_KEYS) == 3.32
    rows = [{"period": "近1週", "value": "+2.9%"}, {"period": "近1月", "value": "+19.89%"}]
    assert etfwatch._ret_from_stats(rows, etfwatch._MONTH_KEYS) == 19.89
    assert etfwatch._ret_from_stats(None, etfwatch._WEEK_KEYS) is None


# ── 追蹤清單與種子落檔（repo 內真實檔） ───────────────────────

def test_watchlist_matches_weekly_report():
    codes = [c for c, *_ in etfwatch.WATCHLIST]
    assert len(codes) == len(set(codes)) == 17
    passive = [c for c, _, k, _ in etfwatch.WATCHLIST if k == "passive"]
    active = [c for c, _, k, _ in etfwatch.WATCHLIST if k == "active"]
    assert set(passive) == {"0056", "00878", "00919", "00929", "0050", "006208"}
    assert "00991A" in active and len(active) == 11    # 含本家主動復華未來50


def test_seed_file_loads_and_covers_watchlist():
    doc = etfwatch.load()
    assert doc and not etfwatch.is_empty(doc)
    by_code = {i["code"]: i for i in doc["items"]}
    assert set(by_code) == {c for c, *_ in etfwatch.WATCHLIST}
    assert by_code["0056"]["ret_1w"] == 3.32 and by_code["0056"]["freq"] == "季配"
    assert by_code["0050"]["aum_e8"] == 22413.0        # 2兆2413億
    assert by_code["00994A"]["ret_1w"] == -0.93        # 唯一週線收黑
    assert by_code["00985A"]["yield_pct"] is None      # N/A → null


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


def test_fetch_falls_back_to_previous_values_when_source_down(monkeypatch):
    def boom(code):
        raise RuntimeError("CONNECT 403")
    monkeypatch.setattr(etfwatch, "_fetch_one", boom)
    doc = etfwatch.fetch()                              # 來源全倒 → 逐檔沿用種子值
    by_code = {i["code"]: i for i in doc["items"]}
    assert by_code["00929"]["ret_1w"] == 4.03 and by_code["00929"]["src"] == "seed"
    assert not etfwatch.is_empty(doc)
    assert "不可達" in doc["source"]


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
