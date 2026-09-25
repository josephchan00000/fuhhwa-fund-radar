"""ETF 數據追蹤（arm/etfwatch＋儀表板第四分頁）測試——離線、吃 repo 內種子落檔。"""
import json
import re

import pytest
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


def test_yield_uses_estimate_when_announced(monkeypatch):
    # 有當月預估配息 → 換算年化配息率改用預估值年化並標 yield_is_est（新聞口徑）
    import arm.connectors.mops as mops
    today = date(2026, 7, 6)
    monkeypatch.setattr(etfwatch, "load", lambda: None)
    # etfinfo 給收盤價與頻率，但不給預估；預估來自 ANNOUNCED_EST
    monkeypatch.setattr(etfwatch, "_fetch_market",
                        lambda code: {"close_px": 30.78, "freq": "月配", "yield_pct": 10.1,
                                      "last_div": 0.26, "aum_raw": 1e10})
    monkeypatch.setattr(etfwatch, "_fetch_returns",
                        lambda code: {"ret_1w": None, "ret_1m": None, "perf_date": None, "ret_src": None})
    monkeypatch.setattr(etfwatch.clock, "today_tw", lambda: today)
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})
    monkeypatch.setattr(etfwatch, "ANNOUNCED_EST",
                        {"00929": {"amount": 0.38, "ex_date": "2026-07-21"}})
    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["00929"]
    assert i["est_div"] == 0.38 and i["yield_is_est"] is True
    assert i["yield_pct"] == round(0.38 / 30.78 * 12 * 100, 2)   # ≈ 14.81%（新聞報 14.8%）
    # 無預估的檔維持實際年化、不標估
    j = {x["code"]: x for x in etfwatch.fetch()["items"]}["00878"]
    assert j["yield_is_est"] is False


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
    monkeypatch.setattr(etfwatch, "_fetch_returns", lambda code, **k: {"ret_1w": None, "ret_1m": None,
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
    # ret_n＝「經日期防呆濾過後」的點數：_dense_series 是日曆日密序列（含週末），
    # 而 _sane_series 會把週六日剔掉（台股不交易）——2026-09-21 起的正確行為。
    weekdays = sum(1 for d in dense if date.fromisoformat(d).weekday() < 5)
    assert r["perf_date"] == "2026-07-06" and r["ret_src"] == "finmind"
    assert r["ret_n"] == weekdays < 40


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


def test_returns_add_back_dividend_in_window():
    # 2026-07-22 教訓：原始收盤跨除息日會把配息當跌幅（006208 7/16 除息 4.75，一週報酬比
    # 同指數 0050 多跌整整一個股息）→ 區間內除息須加回（總報酬口徑）。
    close = {"2026-07-13": 246.75}
    close.update({(date(2026, 7, 20) - timedelta(days=i)).isoformat(): 226.0 for i in range(5)})
    divs = {"2026-07-16": 4.75}
    r = etfwatch._returns_from_series(close, divs)
    assert r["ret_1w"] == round((226.0 + 4.75) / 246.75 * 100 - 100, 2)   # 息加回
    assert r["ret_1w_div"] == 4.75 and r["last_close"] == 226.0
    # 除息日=基準日當天 → 基準收盤已是除息後價，不加回
    r2 = etfwatch._returns_from_series(close, {"2026-07-13": 4.75})
    assert r2["ret_1w"] == round(226.0 / 246.75 * 100 - 100, 2)
    assert "ret_1w_div" not in r2


def test_degenerate_relaxed_for_bond_codes(monkeypatch):
    # 債券型（00986D）收盤 tick 小、天然重複 → 60% 相異值門檻誤殺；放寬後仍可算報酬
    last = date(2026, 7, 21)
    bond = {(last - timedelta(days=i)).isoformat(): 14.70 + 0.01 * ((i * 7) % 12)
            for i in range(40)}                              # 40 點僅 ~12 個相異值（30%）
    assert etfwatch._is_degenerate(bond) is True             # 一般門檻：判髒（維持舊行為）
    assert etfwatch._is_degenerate(bond, relax=True) is False
    monkeypatch.setattr(etfwatch, "_stooq_series", lambda code: {})
    monkeypatch.setattr(etfwatch, "_yahoo_series", lambda code: bond)
    monkeypatch.setattr(etfwatch, "_finmind_series", lambda code, today: {})
    monkeypatch.setattr(etfwatch, "_twse_series", lambda code, today: {})
    r = etfwatch._fetch_returns("00986D", today=last)
    assert r["ret_src"] == "yahoo" and r["ret_1w"] is not None
    r0 = etfwatch._fetch_returns("0056", today=last)         # 股票型不放寬 → 仍判髒、退底稿
    assert r0["ret_1w"] is None


def test_fetch_fills_close_px_and_last_div_for_tpex_codes(monkeypatch):
    # 上櫃 00998A/00986D：etfinfo 未收錄 → 收盤價用報酬序列末值回填、
    # 配息用種子（首配 6/17），年化配息率以「配息 × 次數 ÷ 序列收盤」自算。
    import arm.connectors.mops as mops
    today = date(2026, 7, 22)
    monkeypatch.setattr(etfwatch, "load", lambda: None)
    monkeypatch.setattr(etfwatch, "_fetch_market", _boom)     # etfinfo 全倒（上櫃檔常態）
    monkeypatch.setattr(etfwatch, "_fetch_returns",
                        lambda code, **k: {"ret_1w": -0.29, "ret_1m": 1.48, "perf_date": "2026-07-21",
                                      "ret_src": "yahoo", "ret_n": 64, "last_close": 17.13,
                                      "ret_1w_base": "2026-07-14=17.18",
                                      "ret_1m_base": "2026-06-18=16.88"})
    monkeypatch.setattr(etfwatch.clock, "today_tw", lambda: today)
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})
    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["00998A"]
    # 2026-08-28 起上櫃檔分組照型態（kind=active、cat 帶「・上櫃」註記），不再另立 other
    assert i["kind"] == "active" and "上櫃" in i["cat"] and i["close_px"] == 17.13  # 序列末值回填
    assert i["last_div"] == 0.404 and i["last_div_date"] == "2026-06-17"   # 種子首配
    assert i["yield_pct"] == round(0.404 / 17.13 * 4 * 100, 2)             # 自算年化 ≈9.43%
    assert i["aum_e8"] == 35.21                               # 種子規模（Tier B）


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
    assert len(codes) == len(set(codes)) == 36
    passive = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "passive"]
    active = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "active"]
    assert set(passive) == {"0056", "00878", "00919", "00929", "0050", "006208"}
    assert "00991A" in active and len(active) == 30    # 含本家主動復華未來50／全球未來50＋上櫃 4 檔
    # 2026-07-06 新增熱門／新募集主動式 ETF 皆在清單中
    assert {"00988A", "00990A", "00403A", "00407A"} <= set(active)
    # 2026-08-05 使用者指示補齊缺檔（兩批；00410A 為「即將登場」畢業轉正的第一例）
    assert {"00404A", "00405A", "00996A", "00410A"} <= set(active)
    assert {"00400A", "00401A", "00402A", "00406A", "00408A", "00999A"} <= set(active)
    # 上櫃檔＝主動式組成員、cat 帶「・上櫃」註記（2026-08-28 使用者指示：分組照投資型態，
    # 不再另立「其他」組——kind=other 機制保留但常態無成員）
    assert {"00998A", "00986D", "00411A", "00987D"} <= set(active)
    for c, _n, _k, cat, _i in etfwatch.WATCHLIST:
        if c in {"00998A", "00986D", "00411A", "00987D"}:
            assert "上櫃" in cat
    assert [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "other"] == []
    assert etfwatch.bond_codes() >= {"00986D"}         # 債券型放寬髒序列門檻的名單
    # 成立日期為 WATCHLIST 靜態值（不需抓、永不空白）
    for c, name, kind, cat, inception in etfwatch.WATCHLIST:
        assert inception and inception.count("/") == 2


def test_seed_perf_covers_every_watchlist_code():
    # 內建週報底稿要涵蓋每一檔（來源全倒時的最後 fallback，避免整片留空）
    assert set(etfwatch.SEED_PERF) == {c for c, *_ in etfwatch.WATCHLIST}
    for code, base in etfwatch.SEED_PERF.items():
        if code in etfwatch._SEED_PENDING:              # 新增檔待 CI 首抓，報酬暫留空（不杜撰）
            continue
        assert base.get("ret_1w") is not None and base.get("ret_1m") is not None


def test_seed_file_loads_and_covers_watchlist():
    doc = etfwatch.load()
    assert doc and not etfwatch.is_empty(doc)
    by_code = {i["code"]: i for i in doc["items"]}
    assert set(by_code) == {c for c, *_ in etfwatch.WATCHLIST}
    # 每檔的成立日期／週報酬／月報酬／規模一律有值（不再整片留空）；
    # 不斷言確切報酬數字——那些會被 CI 以最新市場資料更新，只驗「完整且合理」。
    for i in doc["items"]:
        assert i.get("inception")                        # 成立日期一律有值
        if i["code"] in etfwatch._SEED_PENDING:          # 新增檔待 CI 首抓，報酬／規模可暫留空
            continue
        assert i.get("ret_1w") is not None
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


@pytest.fixture(autouse=True)
def _no_network_day_quotes(monkeypatch):
    """測試一律不打官方當日收盤表（2026-09-03）。

    這支在 fetch() 迴圈外呼叫 twse／tpex openapi，被擋時預設 retries=3×timeout=25
    會讓整個測試檔空轉數分鐘（實測 38 個連線失敗、pytest 逾時）。預設回空＝
    「官方表不可得」，需要它的測試自行 setattr 覆寫。
    """
    monkeypatch.setattr(etfwatch, "_official_day_quotes", lambda: {})


def _down_both(monkeypatch):
    """所有外部來源皆不可達（etfinfo 規模／殖利率 ＋ 報酬 ＋ MOPS 預估）。"""
    import arm.connectors.mops as mops
    monkeypatch.setattr(etfwatch, "_fetch_market", _boom)
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(etfwatch, "_official_day_quotes", lambda: {})  # 測試一律不打網路
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
    for i in doc["items"]:                                    # 除新增待抓檔外，無一欄位留空
        assert i.get("inception")
        if i["code"] in etfwatch._SEED_PENDING:
            continue
        assert i.get("ret_1w") is not None and i.get("aum_e8") is not None


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
    # 本家不再整列高亮／掛徽章，改在產品名內把「復華」標品牌色（00929＋00991A 至少 2 處）
    assert 'class="mine"' not in html and "minepill" not in html
    assert html.count('<span class="fh">復華</span>') >= 2
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
    # 舊欄名／獨立來源欄已移除——只掃 ETF 區塊，不可對整份 HTML 做子字串比對：
    # 2026-07-28 誤爆實例，新聞卡寫「少數的正報酬來源」即讓本斷言失敗。
    etf_sec = html.split('id="etfwatch"', 1)[1].split('id="brief"', 1)[0]
    assert "換算年化配息率" in etf_sec                    # 切片確實含 ETF 表（防邊界寫錯而假通過）
    assert "配息殖利率" not in etf_sec and "報酬來源" not in etf_sec
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


# ── 即將登場的新 ETF（募集／掛牌前瞻）─────────────────────────
# bucket 邏輯測試一律用合成 fixture、不釘真實條目——正式資料會隨掛牌／清理 churn，
# 釘真實條目的舊測試每次資料更新都要跟著改（2026-08-10 改版時的教訓）。

_UP_FIX = [
    {"code": "00901X", "name": "測試募集中", "issuer": "測A", "raise_start": "2026-08-10",
     "raise_end": "2026-08-14", "list_date": "2026-09-02", "freq": "季配", "theme": "t",
     "url": "http://u"},
    {"code": "00902X", "name": "測試即將募集", "issuer": "測B", "raise_start": "2026-08-17",
     "raise_end": "2026-08-20", "freq": "—", "theme": "t", "url": "http://u"},
    {"code": "00903X", "name": "測試待掛牌", "issuer": "測C", "raise_start": "2026-08-03",
     "raise_end": "2026-08-07", "freq": "—", "theme": "t", "url": "http://u"},  # 無掛牌日
    {"code": "00904X", "name": "測試已公告掛牌", "issuer": "測D", "raise_start": "2026-08-03",
     "raise_end": "2026-08-07", "list_date": "2026-08-26", "freq": "年配", "theme": "t",
     "url": "http://u"},
    {"code": "00905X", "name": "測試核准待定", "issuer": "測E", "raise_hint": "預計 9 月推出",
     "asof": "2026-08-10", "freq": "—", "theme": "t", "url": "http://u"},
]


def test_upcoming_five_states_three_buckets(monkeypatch):
    """五狀態三分組：now／soon 進募集組、list／pend 進掛牌組、hint 獨立「已核准」組
    （2026-08-10 使用者：「太長記得分類一下，尤其是只有核准還沒確定募集時間的」）；
    募集進行中的檔即使已知掛牌日也歸募集組（掛牌日當副標），不重複佔兩卡。"""
    monkeypatch.setattr(etfwatch, "UPCOMING", _UP_FIX)
    up = etfwatch.upcoming(date(2026, 8, 10))
    assert {x["code"]: x["stat"] for x in up["raising"]} == \
        {"00901X": "now", "00902X": "soon"}
    assert {x["code"]: x["stat"] for x in up["listing"]} == \
        {"00903X": "pend", "00904X": "list"}
    assert {x["code"]: x["stat"] for x in up["approved"]} == {"00905X": "hint"}
    # 募集組排序：募集中在前
    assert [x["code"] for x in up["raising"]] == ["00901X", "00902X"]


def test_upcoming_pending_no_longer_vanishes(monkeypatch):
    """2026-08-10 使用者抓包的主因：募集結束、掛牌日未公告的檔以前會直接消失。
    現在以「募集結束・待掛牌」續留（最長 45 天；守門測試 30 天就先紅逼補掛牌日）。"""
    monkeypatch.setattr(etfwatch, "UPCOMING", _UP_FIX)
    up = etfwatch.upcoming(date(2026, 8, 10))
    assert any(x["code"] == "00903X" and x["stat"] == "pend" for x in up["listing"])
    up2 = etfwatch.upcoming(date(2026, 9, 25))          # 截止 45 天後自動下架
    assert all(x["code"] != "00903X" for x in up2["listing"])


def test_upcoming_expiry_and_windows(monkeypatch):
    monkeypatch.setattr(etfwatch, "UPCOMING", _UP_FIX)
    # 掛牌日已過 → 前瞻卡退場（升級機制接手）
    up = etfwatch.upcoming(date(2026, 9, 3))
    codes = {x["code"] for g in ("raising", "listing", "approved") for x in up[g]}
    assert "00901X" not in codes
    # 「已核准・時程未定」登錄（asof）逾 45 天沒補日期 → 自動下架
    up2 = etfwatch.upcoming(date(2026, 9, 26))
    assert all(x["code"] != "00905X"
               for g in ("raising", "listing", "approved") for x in up2[g])
    # 已公告掛牌日視窗放寬到 45 天（舊版 14 天：00409A 的 9/2 要等到 8/19 才看得到）
    monkeypatch.setattr(etfwatch, "UPCOMING", [
        {"code": "00906X", "name": "n", "issuer": "i", "raise_start": "2026-08-03",
         "raise_end": "2026-08-07", "list_date": "2026-09-20", "theme": "t", "url": "http://u"}])
    assert [x["stat"] for x in etfwatch.upcoming(date(2026, 8, 10))["listing"]] == ["list"]


def test_upcoming_entries_have_required_fields():
    for it in etfwatch.UPCOMING:
        assert it.get("name") and it.get("issuer")
        # 代號未派碼者（hint 形態常見）填 None＝顯示「代號未定」；有代號就要合格式
        if it.get("code"):
            assert re.match(r"^\d{5,6}[A-Z]?$", it["code"])  # 00411A／009827 兩型都收
        else:
            assert it.get("raise_hint"), "無代號僅允許『已核准待定』hint 條目"
        assert it.get("url", "").startswith("http")          # 活動介紹連結必備
        # 三種登錄形態擇一：已知掛牌日／已知募集期／已核准待定（hint＋查證日）
        assert it.get("list_date") or it.get("raise_start") or \
            (it.get("raise_hint") and it.get("asof"))
        for k in ("list_date", "raise_start", "raise_end", "asof"):
            if it.get(k):
                date.fromisoformat(it[k])                    # 日期一律 ISO、可解析


def test_upcoming_seminar_slide_completeness():
    """2026-08-10 使用者研討會「即將上市ETF」投影片名單須全數在列——資料補齊的直接驗證。

    條目掛牌後會被 stale guard 清出 UPCOMING，但**不可從雷達上消失**：轉正進 WATCHLIST
    或（track:false 的海外被動檔）列入 NOT_TRACKED，兩者都算「認得」。所以斷言對
    known_codes() 而非只對 UPCOMING——009829 於 2026-09-20 週掃清理後就是走 NOT_TRACKED
    這條，舊斷言只看 UPCOMING 才會紅（2026-09-21 修）。"""
    from arm import etfdiscover
    known = etfdiscover.known_codes()
    assert {"009829", "00411A", "00987D", "009827", "00409A", "009828", "00412A"} <= known


def test_upcoming_single_source_is_data_file():
    """UPCOMING 唯一真實來源＝data/etf_upcoming.json（2026-08-10 搬出程式碼）——每週
    「ETF 募集週掃」Routine 只推資料檔即可經 daily.yml 併檔段自動入 main，不需人工
    merge 程式碼分支。壞檔會讓 UPCOMING 變空 → 本測試與 seminar/required-fields 一起紅。"""
    doc = json.loads(etfwatch.UPCOMING_FP.read_text(encoding="utf-8"))
    assert doc["items"] == etfwatch.UPCOMING and len(doc["items"]) >= 1
    assert doc.get("as_of")                    # daily.yml 併檔段以 as_of 比新舊，必填


def test_dashboard_shows_upcoming_etf_section():
    # 分頁骨架與日期無關（前瞻項目會隨時間過期，故 render 測試只驗恆存的結構）
    html = fund_dashboard.render()
    assert 'id="etf-upcoming"' in html and "即將登場的新 ETF" in html
    assert 'for="sec-eup"' in html                        # 分頁導覽有「即將登場」分段鈕
    assert '<div class="sec" data-sec="eup">' in html      # 且該段有分段包裝
    assert "即將登場的新 ETF" in html                       # 區塊標題
    # 有前瞻資料時列卡片、無則顯示「近期無」提示——兩者其一必在
    assert "活動介紹" in html or "近期無" in html


def test_upcoming_view_renders_cards_with_links():
    # 釘在 2026-08-10（研討會名單日；真實條目為既成事實、日期固定即恆定）：
    # 募集中玉山 009827、本家 00409A、PCB 009828，加上「已核准・時程未定」精簡列（00412A 等）。
    # 若日後清理 UPCOMING 舊條目，同步更新此測試的斷言即可——2026-09-25：統一雙檔
    # （00411A/00987D，掛牌 08/26）已轉正並清出 UPCOMING，8/10 的「即將掛牌」組因此變空，
    # 該組改由 8/20 的待掛牌檔（00409A、009827，掛牌 09/02）驗證。
    # 註：大華銀 KOSPI50（009829）2026-09-20 週掃依 stale guard 清出 UPCOMING、改列
    # NOT_TRACKED，故不再上版——由 seminar 測試確認它仍被認得。
    up = etfwatch.upcoming(date(2026, 8, 10))
    out = fund_dashboard._upcoming_etf_view(up)
    assert "募集中・即將募集" in out
    assert "已核准・募集時程未定" in out                     # 第三組（2026-08-10 使用者指示分類）
    assert "009827" in out and "00409A" in out and "00412A" in out
    assert "募集中 08/10–08/14" in out                       # 玉山 8/10 起正在募集
    assert "預定掛牌 09/02" in out                            # 募集卡帶掛牌日副標
    # 募集結束後轉入「即將掛牌・待掛牌」組
    out2 = fund_dashboard._upcoming_etf_view(etfwatch.upcoming(date(2026, 8, 20)))
    assert "即將掛牌・待掛牌" in out2 and "掛牌 09/02" in out2
    # 核准組＝精簡列：未派碼檔顯示「代號未定」、不佔卡片（uprow 非 upcard）。
    # 列數／未派碼數由資料推導——條目會隨每輪發現增補，釘死數字只會每次都紅。
    approved = up["approved"]
    assert len(approved) >= 3
    assert out.count('class="uprow"') == len(approved)
    assert out.count("代號未定") == sum(1 for x in approved if not x.get("code"))
    assert "大華銀優利美國非投資等級債券ETF" in out
    assert "加密科技與金融創新" in out
    assert "活動介紹" in out and "esunam.com/act/etf_009827" in out   # 卡片附投信活動頁
    assert '<span class="fh">復華</span>' in out             # 本家以品牌色標示


def test_upcoming_hint_row_compact():
    """核准待定精簡列：有代號顯示代號、無代號顯示「代號未定」；帶 hint 文字與介紹連結。"""
    row = fund_dashboard._upcoming_hint_row(
        {"code": "00412A", "name": "主動安聯亞洲半導體", "issuer": "安聯投信",
         "raise_hint": "預計9月募集", "url": "http://x"})
    assert "00412A" in row and "預計9月募集" in row and "介紹 ↗" in row
    row2 = fund_dashboard._upcoming_hint_row(
        {"code": None, "name": "測試未派碼", "issuer": "測", "raise_hint": "h", "url": "http://x"})
    assert "代號未定" in row2 and "測試未派碼" in row2


def test_upcoming_view_empty_shows_hint():
    out = fund_dashboard._upcoming_etf_view({"listing": [], "raising": [], "approved": []})
    assert "近期無" in out and "upnone" in out
    # 明確傳空 applied 也一樣（申請中無檔不該撐開版面）
    out2 = fund_dashboard._upcoming_etf_view(
        {"listing": [], "raising": [], "approved": []}, applied=[])
    assert "upnone" in out2


def test_upcoming_view_applied_section():
    """「已送件・審查中」第四組（2026-08-28 使用者：「有送件的ETF就可以更新上去即將登場了」）：
    發現層 gap 檔 pipeline 欄自動展示——精簡列、同名去重、本家復華排最前、
    無 approve 文字預設「審查中」；純展示不登錄不警示。"""
    applied = [
        {"name": "台新臺灣中小主動式ETF基金", "cat": "主動式ETF", "stage": "applied"},
        {"name": "復華台灣新星主動式ETF基金", "cat": "主動式ETF", "stage": "applied"},
        {"name": "兆豐美國黃金礦業ETF基金", "cat": "ETF", "stage": "applied",
         "approve": "115.9.8申報生效"},
        {"name": "台新臺灣中小主動式ETF基金", "cat": "主動式ETF", "stage": "applied"},  # 重複
    ]
    out = fund_dashboard._upcoming_etf_view(
        {"listing": [], "raising": [], "approved": []}, applied=applied)
    assert "已送件・審查中" in out and "upnone" not in out
    assert out.count('class="uprow"') == 3                    # 同名去重後 3 列
    assert out.count("申請中") >= 3                            # 每列帶「申請中」章
    assert "審查中" in out and "115.9.8申報生效" in out         # 預設與原文審核狀態
    assert '<span class="fh">復華</span>' in out               # 本家品牌色
    # 本家排最前（sort key：復華 0、其他 1；其餘依名稱碼位序）
    assert out.find("復華台灣新星") < out.find("台新臺灣中小")
    assert out.find("復華台灣新星") < out.find("兆豐美國黃金礦業")


def test_load_overrides_kind_cat_from_watchlist(tmp_path, monkeypatch):
    """kind／cat 是顯示分組的靜態值，load() 以當前 WATCHLIST 覆蓋落檔舊值——
    2026-08-28 上櫃檔 other→active 改分組時，不必等 CI 重抓當天就生效（同成立日慣例）。"""
    fp = tmp_path / "etf_watch.json"
    fp.write_text(json.dumps({"items": [
        {"code": "00998A", "name": "主動復華金融股息", "kind": "other", "cat": "主動式股票"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(etfwatch, "OUT", fp)
    doc = etfwatch.load()
    i = {x["code"]: x for x in doc["items"]}["00998A"]
    assert i["kind"] == "active" and i["cat"] == "主動式股票・上櫃"


# ── 掛牌日自動升級（2026-08-05 使用者：即將登場列過的檔，掛牌那天要自動加入追蹤） ─────

def test_watch_tuples_promotes_on_list_date(monkeypatch):
    """UPCOMING 有 list_date 且已到、又不在 WATCHLIST → 自動升級進有效追蹤清單；
    掛牌日前一天則不升級。"""
    monkeypatch.setattr(etfwatch, "UPCOMING", [
        {"code": "00999X", "name": "主動測試新兵", "issuer": "測試投信",
         "list_date": "2026-08-10", "freq": "季配", "theme": "t", "url": "u"},
    ])
    before = etfwatch.watch_tuples(date(2026, 8, 9))
    assert all(c != "00999X" for c, *_ in before)
    after = etfwatch.watch_tuples(date(2026, 8, 10))
    got = {c: (n, k, cat, inc) for c, n, k, cat, inc in after}
    assert got["00999X"] == ("主動測試新兵", "active", "主動式", "2026/08/10")
    # 靜態 WATCHLIST 原封在前，升級檔只增不改
    assert after[:len(etfwatch.WATCHLIST)] == list(etfwatch.WATCHLIST)


def test_watch_tuples_respects_kind_cat_and_dedupes(monkeypatch):
    """選填 kind/cat 供債券型／上櫃檔升級用；已轉正 WATCHLIST 者不重複出現。"""
    monkeypatch.setattr(etfwatch, "UPCOMING", [
        {"code": "00999D", "name": "主動測試美債", "issuer": "測試投信",
         "list_date": "2026-08-01", "freq": "月配", "cat": "主動式債券", "theme": "t", "url": "u"},
        {"code": "00410A", "name": "主動永豐科技趨勢", "issuer": "永豐投信",
         "list_date": "2026-08-03", "freq": "半年配", "theme": "t", "url": "u"},  # 已轉正
        {"code": "00408X", "name": "主動測試募集中", "issuer": "測試投信",
         "raise_start": "2026-08-05", "raise_end": "2026-08-07", "theme": "t", "url": "u"},  # 無掛牌日
    ])
    lst = etfwatch.watch_tuples(date(2026, 8, 10))
    codes = [c for c, *_ in lst]
    assert codes.count("00410A") == 1                  # 不因 UPCOMING 還留著就重複
    assert "00408X" not in codes                       # 沒有掛牌日＝不升級
    got = {c: (k, cat) for c, _n, k, cat, _i in lst}
    assert got["00999D"] == ("active", "主動式債券")
    assert "00999D" in etfwatch.bond_codes()           # 債券檔吃得到髒序列放寬門檻


def test_watch_tuples_skips_track_false(monkeypatch):
    """track: False（海外被動指數展示檔）掛牌後不自動進追蹤表——被動組是策展的
    6 檔台股大表，自動塞韓股／跨國主題檔會污染它（2026-08-10 設計決定）。"""
    monkeypatch.setattr(etfwatch, "UPCOMING", [
        {"code": "00907X", "name": "測試海外指數", "issuer": "測", "track": False,
         "raise_start": "2026-08-03", "raise_end": "2026-08-07",
         "list_date": "2026-08-08", "theme": "t", "url": "http://u"}])
    assert all(c != "00907X" for c, *_ in etfwatch.watch_tuples(date(2026, 8, 10)))


def test_upcoming_graduation_guard():
    """掛牌逾 14 天仍未轉正 WATCHLIST → 紅。升級只是 stub 兜底（成立日暫用掛牌日、
    無 SEED 底稿）；清理 UPCOMING 舊條目時未轉正的檔會掉出追蹤——這條測試逼在
    下一輪收斂時把它正式移入 WATCHLIST（查證成立日／頻率後補 SEED_PERF）。
    track: False 的展示檔不升級、不適用本守門。"""
    from datetime import timedelta
    from arm import clock
    have = {c for c, *_ in etfwatch.WATCHLIST}
    overdue = [it["code"] for it in etfwatch.UPCOMING
               if it.get("track") is not False
               and it.get("list_date") and it["code"] not in have
               and date.fromisoformat(it["list_date"])
               <= clock.today_tw() - timedelta(days=14)]
    assert not overdue, (
        f"{overdue} 掛牌已逾 14 天仍未轉正 WATCHLIST——請 WebSearch 查證成立日／配息頻率後"
        f"移入 WATCHLIST 並補 SEED_PERF（參考 2026-08-05 00410A 轉正做法）")


def test_upcoming_stale_entries_guard():
    """資料鮮度守門（2026-08-10 建，逼補模式同持股簡介）：
    ① 募集結束逾 30 天仍無掛牌日 → 紅（WebSearch 查掛牌日補上，或確認取消後除名）；
    ② 「已核准・時程未定」登錄逾 45 天沒補日期 → 紅（重查募集時程、更新 asof 或補日期）；
    ③ 掛牌已逾 30 天的條目 → 紅（清理：追蹤檔應已轉正、展示檔直接除名）。
    目的：讓「即將登場」不再靜默過時——過期條目自動下架只是遮住問題，守門測試才逼收斂。"""
    from arm import clock
    t = clock.today_tw()
    stale = []
    for it in etfwatch.UPCOMING:
        tag = it.get("code") or it["name"]               # 未派碼條目以名稱指認
        ld, re_ = it.get("list_date"), it.get("raise_end") or it.get("raise_start")
        if ld and date.fromisoformat(ld) <= t - timedelta(days=30):
            stale.append((tag, "掛牌已逾 30 天，請清理條目"))
        elif not ld and re_ and date.fromisoformat(re_) <= t - timedelta(days=30):
            stale.append((tag, "募集結束逾 30 天仍無掛牌日——WebSearch 查掛牌日或除名"))
        elif not ld and not re_ and it.get("asof") and \
                date.fromisoformat(it["asof"]) <= t - timedelta(days=45):
            stale.append((tag, "核准待定逾 45 天——重查募集時程"))
    assert not stale, f"UPCOMING 條目過期未維護：{stale}"


def test_load_sorts_items_by_code(tmp_path, monkeypatch):
    """績效表照代碼字典序（2026-08-05 使用者：「不然有點亂」）——load() 單一入口排序，
    績效表／詳情卡／代碼泡泡三處順序自動一致。"""
    fp = tmp_path / "etf_watch.json"
    fp.write_text(json.dumps({"as_of": "x", "items": [
        {"code": "00996A", "name": "c", "kind": "active", "cat": "主動式", "inception": "2026/03/16"},
        {"code": "00404A", "name": "a", "kind": "active", "cat": "主動式", "inception": "2026/05/28"},
        {"code": "0050", "name": "p", "kind": "passive", "cat": "市值型", "inception": "2003/06/30"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(etfwatch, "OUT", fp)
    codes = [i["code"] for i in etfwatch.load()["items"]]
    assert codes == sorted(codes)                      # 全體字典序
    assert codes.index("00404A") < codes.index("00405A") < codes.index("00996A")


def test_new_codes_have_seed_freq_and_pending():
    """新增四檔：freq 為查證值、規模／報酬留空不杜撰（列 _SEED_PENDING 待 CI 首抓）。"""
    assert etfwatch.SEED_PERF["00404A"]["freq"] == "季配"
    assert etfwatch.SEED_PERF["00405A"]["freq"] == "季配"
    assert etfwatch.SEED_PERF["00996A"]["freq"] == "季配"
    assert etfwatch.SEED_PERF["00410A"]["freq"] == "半年配"
    assert {"00404A", "00405A", "00996A", "00410A"} <= etfwatch._SEED_PENDING


# ── 當日漲跌備案 L1：序列缺當日 bar 時用 etfinfo 前收自算（2026-09-03） ──────────

def _mkt(px, mkt_date):
    """etfinfo 端只回收盤價與資料日（其餘欄位不影響本組測試）。"""
    return lambda code: {"close_px": px, "mkt_date": mkt_date}


def test_當日漲跌_序列缺當日bar時走L1備案由etfinfo前收自算(monkeypatch):
    """重現 2026-09-02 事故並驗證備案接手。

    當天 Yahoo 日線缺 9/2 bar，序列末兩點退成「9/1 vs 8/31」＝+2.07%，與 etfinfo 的
    9/2 收盤 106.80 並排——而 0050 當天其實跌約 1.5%，**方向完全相反**。
    備案＝改用落檔存下的 etfinfo 前收（9/1 的 108.45）自算，同源同口徑、零額外請求。
    """
    prev = {"items": [{"code": "0050", "close_px": 108.45, "as_of": "2026-09-01",
                       "prev_px": 106.25, "prev_px_date": "2026-08-31"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))
    # 序列只到 9/1：末兩點給出「9/1 vs 8/31」的舊漲跌（正是事故當天的形狀）
    monkeypatch.setattr(etfwatch, "_fetch_returns", lambda code, today=None, **k: {
        "ret_1w": 3.88, "ret_1m": 5.44, "perf_date": "2026-09-01", "ret_src": "yahoo",
        "chg_pct": 2.07, "chg_amt": 2.2, "prev_close": 106.25, "prev_date": "2026-08-31"})
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]

    # ① as_of 推進 → 舊收盤降級為前收
    assert i["prev_px"] == 108.45 and i["prev_px_date"] == "2026-09-01"
    # ② 當日漲跌改由 L1 自算，且方向正確（106.80 / 108.45 - 1 ≈ -1.52%）
    assert i["chg_src"] == "etfinfo_prev" and i["chg_asof"] == "2026-09-02"
    assert i["chg_pct"] == -1.52 and i["prev_date"] == "2026-09-01"
    assert i["chg_pct"] < 0                      # 事故版本會是 +2.07%（方向相反）
    # ③ 週／月報酬仍走序列（保留 Yahoo 還原收盤的總報酬口徑，不被 L1 影響）
    assert i["ret_1w"] == 3.88 and i["perf_asof"] == "2026-09-01"


def test_當日漲跌_序列夠新時不啟用L1(monkeypatch):
    """序列自己就有當日 bar → 一律讓序列走（它帶除息還原資訊，優於 etfinfo 市價）。"""
    prev = {"items": [{"code": "0050", "close_px": 108.45, "as_of": "2026-09-01"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", lambda code, today=None, **k: {
        "ret_1w": 1.0, "ret_1m": 2.0, "perf_date": "2026-09-02", "ret_src": "yahoo",
        "chg_pct": -1.52, "chg_amt": -1.65, "prev_close": 108.45, "prev_date": "2026-09-01"})
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i["chg_src"] == "yahoo" and i["chg_asof"] == "2026-09-02"


def test_當日漲跌_同一資料日重抓不得把前收洗成今天自己(monkeypatch):
    """同 etfholdings 的「假無異動」坑：同一 as_of 重抓若照樣降級，
    prev_px 會被洗成今天自己、當日漲跌永遠算成 0。"""
    prev = {"items": [{"code": "0050", "close_px": 106.8, "as_of": "2026-09-02",
                       "prev_px": 108.45, "prev_px_date": "2026-09-01"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))   # 同日重抓
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i["prev_px"] == 108.45 and i["prev_px_date"] == "2026-09-01"   # 未被洗成 106.8
    assert i["chg_pct"] != 0


def test_當日漲跌_落檔無收盤價可降級時不亂算(monkeypatch):
    """真正沒有前收可用（新檔首輪：落檔連 close_px 都還沒有）→ L1 不啟用、不杜撰。

    註：降級發生在同一輪的 etfinfo 段，所以「as_of 首次推進」的那一輪 L1 就已可用
    （不必等下一輪）——見上面的事故重現測試。這裡測的是連可降級的舊收盤都沒有的情形。
    """
    prev = {"items": [{"code": "0050", "as_of": "2026-09-01"}]}     # 無 close_px 可降級
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i.get("prev_px") is None              # 沒有舊收盤可降級
    assert i.get("chg_src") != "etfinfo_prev"    # 就不啟用 L1（寧缺勿錯）


def _day_q(quotes):
    """官方全市場當日收盤表（twse+tpex 合併後的形狀）。"""
    return lambda: quotes


def test_當日漲跌_序列缺當日bar時優先用官方當日收盤表(monkeypatch):
    """2026-09-03 使用者：「沒辦法從其他地方補嗎？」——官方 openapi 全市場當日表
    直接給 close 與 change，是序列缺當日 bar 時的第一順位備案（優於 etfinfo 前收自算）。
    """
    prev = {"items": [{"code": "0050", "close_px": 108.45, "as_of": "2026-09-01",
                       "prev_px": 106.25, "prev_px_date": "2026-08-31"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", lambda code, today=None, **k: {
        "ret_1w": 3.88, "ret_1m": 5.44, "perf_date": "2026-09-01", "ret_src": "yahoo",
        "chg_pct": 2.07, "chg_amt": 2.2, "prev_close": 106.25, "prev_date": "2026-08-31"})
    # 官方表：9/2 收 106.80、跌 1.65（＝前收 108.45）
    monkeypatch.setattr(etfwatch, "_official_day_quotes",
                        _day_q({"0050": {"date": "2026-09-02", "close": 106.8,
                                         "change": -1.65, "name": "元大台灣50"}}))
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i["chg_src"] == "twse_today" and i["chg_asof"] == "2026-09-02"
    assert i["chg_pct"] == -1.52 and i["prev_close"] == 108.45   # ref = close − change
    assert i["ret_1w"] == 3.88                                    # 週報酬仍走序列、不受影響


def test_當日漲跌_官方當日表不可得時才退到etfinfo前收(monkeypatch):
    """層級順序：序列 → 官方當日表 → etfinfo 前收自算 → （都沒有就維持既有值）。"""
    prev = {"items": [{"code": "0050", "close_px": 108.45, "as_of": "2026-09-01",
                       "prev_px": 106.25, "prev_px_date": "2026-08-31"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(etfwatch, "_official_day_quotes", _day_q({}))   # 官方表整個不可得
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i["chg_src"] == "etfinfo_prev" and i["chg_pct"] == -1.52


def test_當日漲跌_全部備案都落後時誠實記日期不假裝當日(monkeypatch):
    """官方表也停在舊日、且無前收可退 → 保留該值但 chg_asof 記其自報日，交由渲染端揭露。

    註：官方表落後而 etfinfo 前收「可用」時，會繼續退到前收拿真正的當日漲跌——
    層級是「一路試到拿得到當日為止」，不是「寫入就停」。此處刻意讓前收也不可用。
    """
    prev = {"items": [{"code": "0050", "as_of": "2026-09-01"}]}   # 無 close_px 可降級為前收
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(106.8, "2026-09-02"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(etfwatch, "_official_day_quotes",
                        _day_q({"0050": {"date": "2026-09-01", "close": 108.45,
                                         "change": 2.2, "name": "元大台灣50"}}))
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i["chg_asof"] == "2026-09-01"          # 誠實記來源自報日（< as_of 9/2）
    from arm import fund_dashboard as fd
    assert "mdstale" in fd._chg_cell(i)           # 渲染端據此標過期、不冒充當日


# ── 2026-09-21 事故：來源回了「週日」假 bar，整表當日漲跌與週／月報酬全錯 ──────────
# 使用者回報：「ETF 的當日淨值上櫃的沒有更新到，當日股價變動%都沒有更新到」
#             「你看你 00998A 整個數字都是錯的」

def test_假bar_週末與未來日期一律剔除():
    """Yahoo 2026-09-21 對 36 檔全回一個 9/20（週日）bar —— 台股週末不交易，不可能存在。"""
    today = date(2026, 9, 21)                      # 週一
    series = {"2026-09-16": 106.9, "2026-09-17": 108.05, "2026-09-18": 109.85,
              "2026-09-19": 111.0,                 # 週六（假）
              "2026-09-20": 102.0,                 # 週日（假）＝事故當天那個 bar
              "2026-09-22": 120.0}                 # 未來日（假）
    out = etfwatch._sane_series(series, today, "0050")
    assert sorted(out) == ["2026-09-16", "2026-09-17", "2026-09-18"]
    assert "2026-09-20" in etfwatch._BAD_BARS["0050"]      # 進 CI 日誌摘要


def test_假bar_被剔除後當日漲跌與週月報酬都回到正確值():
    """事故重現：0050 週五收 109.85、週四 108.05＝+1.67%。
    假 bar（週日 102.0）若採信，會算成 -7.15%（方向相反、幅度離譜）。"""
    today = date(2026, 9, 21)
    good = {"2026-09-11": 105.0, "2026-09-16": 106.9,
            "2026-09-17": 108.05, "2026-09-18": 109.85}
    bad = dict(good, **{"2026-09-20": 102.0})

    # 未濾：末兩點＝9/18 → 9/20，算出事故當天那個 -7.15%
    r_bad = etfwatch._returns_from_series(bad)
    assert r_bad["chg_pct"] == -7.15 and r_bad["perf_date"] == "2026-09-20"
    # 已濾：末兩點回到 9/17 → 9/18
    r_ok = etfwatch._returns_from_series(etfwatch._sane_series(bad, today))
    assert r_ok["perf_date"] == "2026-09-18"
    assert r_ok["chg_pct"] == 1.67 == etfwatch._returns_from_series(good)["chg_pct"]
    assert r_ok["ret_1w"] == etfwatch._returns_from_series(good)["ret_1w"]   # 區間報酬同時止血


def test_當日漲跌_序列日期超前收盤價時不採信改走官方當日表(monkeypatch):
    """舊版判準只擋「序列落後」（chg_asof < as_of），**超前**反而直接勝出並繞過所有防線
    ——2026-09-21 就是這樣讓 -7.15% 靜默上線的。超前只有兩種來路，都是壞資料：
    週末／未來的假 bar，或盤中未收盤的 partial bar。"""
    prev = {"items": [{"code": "0050", "close_px": 108.05, "as_of": "2026-09-17"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(109.85, "2026-09-18"))
    # 序列硬回一個比 as_of 還新的日期（模擬防呆被繞過的情形）
    monkeypatch.setattr(etfwatch, "_fetch_returns", lambda code, today=None, **k: {
        "ret_1w": 1.0, "ret_1m": 2.0, "perf_date": "2026-09-20", "ret_src": "yahoo",
        "chg_pct": -7.15, "chg_amt": -7.85, "prev_close": 109.85, "prev_date": "2026-09-18"})
    monkeypatch.setattr(etfwatch, "_official_day_quotes",
                        _day_q({"0050": {"date": "2026-09-18", "close": 109.85,
                                         "change": 1.8, "name": "元大台灣50"}}))
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    assert i["chg_src"] == "twse_today" and i["chg_asof"] == "2026-09-18" == i["as_of"]
    assert i["chg_pct"] == 1.67 and i["chg_pct"] > 0      # 事故版本是 -7.15%（方向相反）


def test_上櫃收盤價_官方當日表覆蓋etfinfo落後一日的市價(monkeypatch):
    """etfinfo 對上櫃檔的市價慢一個交易日、卻照樣把 mkt_date 標成當日
    （2026-09-21 逐日實測：00998A etfinfo 17.30@9/18 其實是 9/17 的收盤，9/18 實為 17.22）。
    官方全市場當日表同日也要覆蓋——上櫃的坑正是「日期相同、值差一天」。"""
    prev = {"items": [{"code": "00998A", "close_px": 17.78, "as_of": "2026-09-17"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(17.30, "2026-09-18"))   # 落後一日的值
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(etfwatch, "_official_day_quotes",
                        _day_q({"00998A": {"date": "2026-09-18", "close": 17.22,
                                           "change": -0.08, "name": "主動復華金融股息"}}))
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["00998A"]
    assert i["close_px"] == 17.22 and i["as_of"] == "2026-09-18"   # 官方值勝出（非 17.30）
    assert i["src"] == "official_px+etfinfo"
    # 漲跌與收盤價同源同日 → 渲染端不會標過期
    assert i["chg_asof"] == "2026-09-18" and i["chg_src"] == "twse_today"
    from arm import fund_dashboard as fd
    assert "mdstale" not in fd._chg_cell(i)


def test_上櫃收盤價_官方表落後時不倒灌回舊值(monkeypatch):
    """官方表自己停在舊日 → 不得把 as_of 往回拉、也不得覆蓋較新的 etfinfo 值。"""
    prev = {"items": [{"code": "00998A", "close_px": 17.78, "as_of": "2026-09-17"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(17.30, "2026-09-18"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(etfwatch, "_official_day_quotes",
                        _day_q({"00998A": {"date": "2026-09-17", "close": 17.78,
                                           "change": 0.1, "name": "主動復華金融股息"}}))
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["00998A"]
    assert i["close_px"] == 17.30 and i["as_of"] == "2026-09-18"   # 維持 etfinfo 的較新日


def test_上櫃收盤價_官方表不可得時行為與修法前一致(monkeypatch):
    """day_q 空（本容器 proxy 擋 twse/tpex）→ 整段跳過，不改任何欄位（fail-open）。"""
    prev = {"items": [{"code": "00998A", "close_px": 17.78, "as_of": "2026-09-17"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(17.30, "2026-09-18"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)
    monkeypatch.setattr(etfwatch, "_official_day_quotes", _day_q({}))
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["00998A"]
    assert i["close_px"] == 17.30 and i["as_of"] == "2026-09-18" and i["src"] == "etfinfo+px"
    assert i["prev_px"] == 17.78 and i["prev_px_date"] == "2026-09-17"   # 降級照舊運作


# ── NOT_TRACKED：「已掛牌、但刻意不追蹤」的第三種狀態（2026-09-21） ──────────────

def test_not_tracked_來源是資料檔且欄位齊全():
    """與 UPCOMING 同放 data/etf_upcoming.json（週掃只推資料檔即可自動入 main）。"""
    doc = json.loads(etfwatch.UPCOMING_FP.read_text(encoding="utf-8"))
    assert doc["not_tracked"] == etfwatch.NOT_TRACKED and etfwatch.NOT_TRACKED
    for it in etfwatch.NOT_TRACKED:
        assert it.get("code") and it.get("name") and it.get("why")   # why＝供日後複核
        date.fromisoformat(it["asof"])


def test_not_tracked_檔不再被判已掛牌未登錄():
    """009829 大華銀韓國KOSPI50 實例：stale guard 與自動發現層原本互相矛盾——
    掛牌逾 30 天依規清出 UPCOMING 後，發現層就天天判它「已掛牌未登錄」🔴 真漏網
    （儀表板紅章＋4 個 pytest 紅）。列入 NOT_TRACKED 後不再警示。"""
    from arm import etfdiscover
    known, today = etfdiscover.known_codes(), date(2026, 9, 21)
    seen = {"codes": {"009829": {"first": "2026-08-22", "name": "大華韓國KOSPI50"},
                      "00999X": {"first": "2026-09-15", "name": "某檔真的沒登錄的新 ETF"}}}
    codes = {g.get("code") for g in etfdiscover.listed_gaps(seen, known, today)}
    assert "009829" not in codes                 # 已列 NOT_TRACKED → 不再誤報
    assert "00999X" in codes                     # 真沒登錄的照樣抓到（不可把警示整個關掉）


def test_not_tracked_載入失敗時退回原行為(monkeypatch, tmp_path):
    """壞檔 fail-open 回 []＝該檔重新被警示（寧可多警示，不可靜默漏掉真的新 ETF）。"""
    bad = tmp_path / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(etfwatch, "UPCOMING_FP", bad)
    assert etfwatch._load_not_tracked() == []


def test_gap檔讀取端剔除已登錄代碼():
    """gap 檔是 CI 快照：補登後、下一輪重算前，舊版紅章會繼續掛著（補的人看不到生效）。
    讀取端再濾一次 → 補登後下一次重建即滅章。count 要跟著重算，否則章上檔數與清單不一致。"""
    from arm import etfdiscover
    g = etfdiscover.load_gap()
    assert all((i.get("code") or "") not in etfdiscover.known_codes() for i in g["items"])
    assert g["count"] == len(g["items"])


def test_落檔已被假bar汙染時_下一輪自動修正不需等來源恢復(monkeypatch):
    """今日（2026-09-21）落檔已帶 chg_asof=9/20 的假值：0050 -7.15%、0056 0.00%。
    雙向判準的附加好處——那個被沿用的髒值本身就會**觸發** L1／L2 去拿真值，
    不必等 Yahoo 恢復。舊版判準（< as_of）對它是 False，會原地凍結。
    此處刻意讓序列整個抓不到（最壞情況），驗證仍能自癒。"""
    prev = {"items": [{"code": "0050", "close_px": 109.85, "as_of": "2026-09-18",
                       "prev_px": 108.05, "prev_px_date": "2026-09-17",
                       "chg_pct": -7.15, "chg_amt": -7.85, "chg_asof": "2026-09-20",
                       "chg_src": "yahoo", "perf_asof": "2026-09-20"}]}
    monkeypatch.setattr(etfwatch, "load", lambda: prev)
    monkeypatch.setattr(etfwatch, "_fetch_market", _mkt(109.85, "2026-09-18"))
    monkeypatch.setattr(etfwatch, "_fetch_returns", _boom)          # 序列整個抓不到
    monkeypatch.setattr(etfwatch, "_official_day_quotes", _day_q({}))   # 官方表也不可得
    import arm.connectors.mops as mops
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})

    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["0050"]
    # 退到 L2（etfinfo 前收）：109.85 / 108.05 - 1 = +1.67%，且日期與收盤價同日
    assert i["chg_src"] == "etfinfo_prev" and i["chg_asof"] == "2026-09-18"
    assert i["chg_pct"] == 1.67 and i["chg_pct"] > 0
    from arm import fund_dashboard as fd
    assert "mdstale" not in fd._chg_cell(i)        # 不再是 ⚠，是真數字


# ── 報酬序列錨定官方當日收盤（2026-09-23 使用者：「所有的報酬率都是錯的」） ──────

def _ser(end: date, n: int = 40, px: float = 100.0) -> dict[str, float]:
    out, d = {}, end
    while len(out) < n:
        if d.weekday() < 5:
            out[d.isoformat()] = px - len(out) * 0.1      # 越早越低
        d -= timedelta(days=1)
    return out


def test_anchor_appends_official_close_when_series_lags_one_day():
    """重現 9/22：Yahoo 序列停在 9/21、收盤價已是 9/22 → 補上官方 9/22，報酬與收盤價同日。"""
    s = _ser(date(2026, 9, 21))
    out = etfwatch._anchor_series(s, {"date": "2026-09-22", "close": 111.85})
    assert max(out) == "2026-09-22" and out["2026-09-22"] == 111.85
    r = etfwatch._returns_from_series(out)
    assert r["perf_date"] == "2026-09-22" and r["prev_date"] == "2026-09-21"
    assert r["ret_1w_base"].startswith("2026-09-15")      # 基準日跟著推進一天


def test_anchor_across_weekend_is_one_trading_day():
    s = _ser(date(2026, 9, 18))                           # 週五
    out = etfwatch._anchor_series(s, {"date": "2026-09-21", "close": 1.0})   # 週一
    assert "2026-09-21" in out


def test_anchor_does_not_bridge_missing_trading_days():
    """落後超過一個交易日 → 不硬接（中間缺日會讓當日漲跌算成兩天的漲幅）。"""
    s = _ser(date(2026, 9, 17))
    out = etfwatch._anchor_series(s, {"date": "2026-09-22", "close": 1.0})
    assert "2026-09-22" not in out and max(out) == "2026-09-17"


def test_anchor_drops_bars_newer_than_official_and_overrides_same_day():
    """序列末日比官方日還新＝盤中 partial bar → 丟；同日不同值 → 官方為準。"""
    s = _ser(date(2026, 9, 23))
    out = etfwatch._anchor_series(s, {"date": "2026-09-22", "close": 99.0})
    assert max(out) == "2026-09-22" and out["2026-09-22"] == 99.0


def test_anchor_missing_is_noop():
    s = _ser(date(2026, 9, 21))
    assert etfwatch._anchor_series(s, None) == s
    assert etfwatch._anchor_series(s, {"date": "2026-09-22", "close": None}) == s


def test_fetch_returns_uses_anchor(monkeypatch):
    monkeypatch.setattr(etfwatch, "_stooq_series", lambda code: {})
    monkeypatch.setattr(etfwatch, "_yahoo_series", lambda code: _ser(date(2026, 9, 21)))
    r = etfwatch._fetch_returns("0050", today=date(2026, 9, 23),
                                anchor={"date": "2026-09-22", "close": 111.85})
    assert r["perf_date"] == "2026-09-22" and r["last_close"] == 111.85
