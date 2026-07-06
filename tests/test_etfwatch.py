"""ETF 數據追蹤（arm/etfwatch＋儀表板第四分頁）測試——離線、吃 repo 內種子落檔。"""
import json
from datetime import date, timedelta

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


def test_dividend_split_actual_vs_current_month_estimate():
    today = date(2026, 7, 6)
    divs = [{"exDate": "2026-04-15", "amount": 0.70},
            {"exDate": "2026-07-16", "amount": 0.80},   # 本月、除息日未到 → 預估配息
            {"exDate": "2026-01-15", "amount": 0.65}]
    last, ld, est, ed = etfwatch._dividend_split(divs, today=today)
    assert last == 0.70 and ld == "2026-04-15"          # 最近一次「實際」（除息日 <= 今天）
    assert est == 0.80 and ed == "2026-07-16"           # 當月未到期 → 預估


def test_dividend_split_respects_estimate_flag():
    today = date(2026, 7, 6)
    divs = [{"exDate": "2026-07-03", "amount": 0.50, "type": "estimate"}]  # 明確標預估
    last, ld, est, ed = etfwatch._dividend_split(divs, today=today)
    assert est == 0.50 and last is None                 # 標預估者不計入「實際」


def test_dividend_split_no_estimate_off_month():
    today = date(2026, 7, 6)
    divs = [{"exDate": "2026-04-15", "amount": 0.70}, {"exDate": "2026-01-15", "amount": 0.65}]
    last, ld, est, ed = etfwatch._dividend_split(divs, today=today)
    assert last == 0.70 and est is None                 # 本月無公告 → 無預估


def test_mops_parse_handles_4_5_6_digit_codes_and_roc_dates():
    from arm.connectors import mops
    codes = {"0056", "006208", "00929", "00980A"}
    html = ("<table><tr><td>0056</td><td>元大高股息</td><td>2026/07/16</td><td>0.8000</td></tr>"
            "<tr><td>006208</td><td>富邦</td><td>2026/07/18</td><td>1.2500</td></tr></table>")
    r = mops._parse_rows(html, codes)
    assert r["0056"] == {"ex_date": "2026-07-16", "amount": 0.8, "announced": None}
    assert r["006208"]["amount"] == 1.25                # 代碼數字不會被誤當金額
    js = '{"data":[["00929","復華","115/07/16","0.0600"]]}'  # 民國年
    assert mops._parse_rows(js, codes)["00929"] == {"ex_date": "2026-07-16", "amount": 0.06,
                                                     "announced": None}


def test_announced_est_fallback_when_etfinfo_and_mops_empty(monkeypatch):
    # etfinfo/MOPS 都沒預估 → 用投信已公告人工清單 ANNOUNCED_EST（本月、除息未到）
    import arm.connectors.mops as mops
    today = date(2026, 7, 6)
    monkeypatch.setattr(etfwatch, "load", lambda: None)
    monkeypatch.setattr(etfwatch, "_fetch_market", lambda code: {})       # etfinfo 無配息/預估
    monkeypatch.setattr(etfwatch, "_fetch_returns",
                        lambda code: {"ret_1w": None, "ret_1m": None, "perf_date": None, "ret_src": None})
    monkeypatch.setattr(etfwatch.clock, "today_tw", lambda: today)
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})    # MOPS 空
    monkeypatch.setattr(etfwatch, "ANNOUNCED_EST",
                        {"00991A": {"amount": 0.77, "ex_date": "2026-07-21"}})
    by = {i["code"]: i for i in etfwatch.fetch()["items"]}
    assert by["00991A"]["est_div"] == 0.77 and by["00991A"]["est_div_date"] == "2026-07-21"
    assert by["00991A"]["est_src"] == "announced"


def test_announced_est_dict_entries_are_valid():
    # 維護清單格式檢查：金額為正、除息日為 ISO
    for code, e in etfwatch.ANNOUNCED_EST.items():
        assert code in {c for c, *_ in etfwatch.WATCHLIST}
        assert isinstance(e["amount"], (int, float)) and e["amount"] > 0
        assert date.fromisoformat(e["ex_date"])


def test_fetch_fills_estimate_from_mops_for_current_month(monkeypatch):
    import arm.connectors.mops as mops
    today = date(2026, 7, 6)
    monkeypatch.setattr(etfwatch, "load", lambda: None)
    monkeypatch.setattr(etfwatch, "_fetch_market", lambda code: {})      # etfinfo 無配息/預估
    monkeypatch.setattr(etfwatch, "_fetch_returns", lambda code: {"ret_1w": None, "ret_1m": None,
                                                                  "perf_date": None, "ret_src": None})
    monkeypatch.setattr(etfwatch.clock, "today_tw", lambda: today)
    monkeypatch.setattr(etfwatch, "ANNOUNCED_EST", {})   # 隔離：本測試只驗 MOPS 來源
    monkeypatch.setattr(mops, "etf_distributions",
                        lambda *a, **k: {"0056": {"ex_date": "2026-07-16", "amount": 0.80}})
    by = {i["code"]: i for i in etfwatch.fetch()["items"]}
    assert by["0056"]["est_div"] == 0.80 and by["0056"]["est_div_date"] == "2026-07-16"
    assert by["0056"]["est_src"] == "mops"               # MOPS 優先於人工清單
    assert by["00929"].get("est_div") is None            # 該來源無公告者不填


def _dense_series(last: date, n: int, base: float, step: float) -> dict:
    """造 n 個連續日曆日的密收盤序列（測試用；週末也放值，_ret 取 <=target 最後一筆即可）。"""
    return {(last - timedelta(days=i)).isoformat(): base + step * (n - i) for i in range(n)}


def test_returns_from_dense_series_computes_week_and_month():
    # 密序列（每日都有）→ 一週(7)/一月(30 日曆日)基準明確、算得出報酬
    close = {"2026-06-06": 20.0}
    close.update({(date(2026, 7, 6) - timedelta(days=i)).isoformat(): 24.0
                  for i in range(0, 8)})            # 近8日都 24.0
    close["2026-06-29"] = 23.0                       # 一週前基準
    r = etfwatch._returns_from_series(close)
    assert r["perf_date"] == "2026-07-06"
    assert r["ret_1w"] == round((24.0 / 23.0 - 1) * 100, 2)   # 基準 06/29
    assert r["ret_1m"] == round((24.0 / 20.0 - 1) * 100, 2)   # 基準 06/06


def test_returns_guard_suppresses_sparse_series():
    # 稀疏序列：只有 06/05 與近幾日 → 一週前(06/29)最近的 <= 點是 06/05，離 target 24 天 > 12 → 不報
    close = {"2026-06-05": 20.0, "2026-07-01": 23.5, "2026-07-02": 23.8,
             "2026-07-03": 23.9, "2026-07-06": 24.0}
    r = etfwatch._returns_from_series(close)
    assert r["ret_1w"] is None                       # 防呆：基準離目標日 >12 天 → 不報（寧缺勿錯）
    # 一月前(06/06)最近 <= 點 06/05（差 1 天）→ 可報
    assert r["ret_1m"] == round((24.0 / 20.0 - 1) * 100, 2)


def test_fetch_returns_prefers_first_dense_source(monkeypatch):
    # 來源順序：stooq → Yahoo → FinMind → TWSE，取第一個「乾淨且夠密」者
    dense = _dense_series(date(2026, 7, 6), 40, 20.0, 0.1)
    monkeypatch.setattr(etfwatch, "_stooq_series", lambda code: {})          # stooq 空
    monkeypatch.setattr(etfwatch, "_yahoo_series", lambda code: {})          # Yahoo 空
    monkeypatch.setattr(etfwatch, "_finmind_series", lambda code, today: dense)  # FinMind 命中
    monkeypatch.setattr(etfwatch, "_twse_series", lambda code, today: {})
    r = etfwatch._fetch_returns("0056", today=date(2026, 7, 6))
    assert r["ret_1w"] is not None and r["ret_1m"] is not None
    assert r["perf_date"] == "2026-07-06" and r["ret_src"] == "finmind" and r["ret_n"] == 40


def test_fetch_returns_skips_degenerate_series(monkeypatch):
    # 髒序列（多日同一收盤，如 Yahoo 對 0056 回 51.8）→ 跳過，改用乾淨 stooq
    degen = {(date(2026, 7, 6) - timedelta(days=i)).isoformat(): 51.8 for i in range(40)}
    degen[date(2026, 7, 6).isoformat()] = 53.25          # 只有最新不同 → 相異值極少
    clean = _dense_series(date(2026, 7, 6), 40, 48.0, 0.13)
    monkeypatch.setattr(etfwatch, "_stooq_series", lambda code: clean)   # stooq 乾淨、先採用
    monkeypatch.setattr(etfwatch, "_yahoo_series", lambda code: degen)
    monkeypatch.setattr(etfwatch, "_finmind_series", lambda code, today: {})
    monkeypatch.setattr(etfwatch, "_twse_series", lambda code, today: {})
    assert etfwatch._is_degenerate(degen) is True
    r = etfwatch._fetch_returns("0056", today=date(2026, 7, 6))
    assert r["ret_src"] == "stooq" and r["ret_1w"] != r["ret_1m"]   # 乾淨源、週≠月


def test_fetch_returns_accepts_equal_bases_when_series_varied(monkeypatch):
    # 兩基準日剛好同價（近月盤整，如 0056 6/5 與 6/29 都 51.8）但整體序列相異值充足
    # → 一週==一月報酬是合理結果、不得判髒（2026-07-06 教訓，舊 _same_base_price 已移除）。
    varied = {(date(2026, 7, 6) - timedelta(days=i)).isoformat(): 50.0 + 0.05 * i for i in range(45)}
    varied["2026-06-29"] = 51.8                          # 一週基準
    varied["2026-06-06"] = 51.8                          # 一月基準（同價但序列整體相異 → 不判髒）
    monkeypatch.setattr(etfwatch, "_stooq_series", lambda code: {})
    monkeypatch.setattr(etfwatch, "_yahoo_series", lambda code: varied)
    monkeypatch.setattr(etfwatch, "_finmind_series", lambda code, today: {})
    monkeypatch.setattr(etfwatch, "_twse_series", lambda code, today: {})
    r = etfwatch._fetch_returns("0056", today=date(2026, 7, 6))
    assert r["ret_src"] == "yahoo" and r["ret_1w"] is not None   # 採用、未被誤攔
    assert not hasattr(etfwatch, "_same_base_price")             # 舊守衛確已移除


def test_fetch_returns_none_when_all_sources_empty(monkeypatch):
    monkeypatch.setattr(etfwatch, "_stooq_series", lambda code: {})
    monkeypatch.setattr(etfwatch, "_yahoo_series", lambda code: {})
    monkeypatch.setattr(etfwatch, "_finmind_series", lambda code, today: {})
    monkeypatch.setattr(etfwatch, "_twse_series", lambda code, today: {})
    r = etfwatch._fetch_returns("0056", today=date(2026, 7, 6))
    assert r["ret_1w"] is None and r["ret_1m"] is None and r["ret_src"] is None


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
    # 每檔的成立日期／週報酬／月報酬／規模一律有值（不再整片留空）；
    # 不斷言確切報酬數字——那些會被 CI 以最新市場資料更新，只驗「完整且合理」。
    for i in doc["items"]:
        assert i.get("inception") and i.get("ret_1w") is not None
        assert i.get("ret_1m") is not None and i.get("aum_e8") is not None
        assert -50 < i["ret_1w"] < 50 and -80 < i["ret_1m"] < 80   # 合理範圍防呆
    assert by_code["0056"]["freq"] == "季配" and by_code["00929"]["freq"] == "月配"


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
    """所有外部來源皆不可達（etfinfo 規模／殖利率 ＋ 報酬 ＋ MOPS 預估）。"""
    import arm.connectors.mops as mops
    monkeypatch.setattr(etfwatch, "_fetch_market", _boom)
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})


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
    # 欄位改名：最近一次配息金額、換算年化配息率
    assert "最新收盤價" in html and "最近一次配息金額" in html and "換算年化配息率" in html
    assert "配息殖利率" not in html and "報酬來源" not in html   # 舊欄名／獨立來源欄已移除
    assert "預計配息金額" in html                        # 預估配息 * 的註腳說明
    assert "mops.twse.com.tw" in html                    # 預估配息來源 MOPS 連結


def test_ret_cell_shows_base_date_and_price():
    i = {"ret_1w": 4.35, "ret_1w_base": "2026-06-29=51.8", "perf_asof": "2026-07-06",
         "close_px": 53.25}
    cell = fund_dashboard._ret_cell(i, "ret_1w")
    assert "+4.35%" in cell
    assert "起算 06/29 收 51.8" in cell                  # 可見小字：起算日 收 價格（不用＠）
    assert "近一週＝最新 2026-07-06 收 53.25 ÷ 基準 2026-06-29 收 51.8" in cell   # tooltip 完整算式
    # 無基準資料（seed/舊檔）→ 只顯示 %、不加基準行
    assert fund_dashboard._ret_cell({"ret_1w": 3.0}, "ret_1w") == fund_dashboard._pct_span(3.0)


def test_div_cell_shows_estimate_with_asterisk():
    cell = fund_dashboard._div_cell({"last_div": 0.72, "est_div": 0.80})
    assert "0.72" in cell and "預估" in cell and "*" in cell and "estdiv" in cell
    plain = fund_dashboard._div_cell({"last_div": 0.72, "est_div": None})
    assert "0.72" in plain and "預估" not in plain
