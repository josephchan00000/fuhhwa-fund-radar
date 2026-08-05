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
                        lambda code: {"ret_1w": -0.29, "ret_1m": 1.48, "perf_date": "2026-07-21",
                                      "ret_src": "yahoo", "ret_n": 64, "last_close": 17.13,
                                      "ret_1w_base": "2026-07-14=17.18",
                                      "ret_1m_base": "2026-06-18=16.88"})
    monkeypatch.setattr(etfwatch.clock, "today_tw", lambda: today)
    monkeypatch.setattr(mops, "etf_distributions", lambda *a, **k: {})
    i = {x["code"]: x for x in etfwatch.fetch()["items"]}["00998A"]
    assert i["kind"] == "other" and i["close_px"] == 17.13    # 序列末值回填
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
    assert len(codes) == len(set(codes)) == 33
    passive = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "passive"]
    active = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "active"]
    assert set(passive) == {"0056", "00878", "00919", "00929", "0050", "006208"}
    assert "00991A" in active and len(active) == 25    # 含本家主動復華未來50
    # 2026-07-06 新增熱門／新募集主動式 ETF 皆在清單中
    assert {"00988A", "00990A", "00403A", "00407A"} <= set(active)
    # 2026-08-05 使用者指示補齊缺檔（兩批；00410A 為「即將登場」畢業轉正的第一例）
    assert {"00404A", "00405A", "00996A", "00410A"} <= set(active)
    assert {"00400A", "00401A", "00402A", "00406A", "00408A", "00999A"} <= set(active)
    # 「其他」分類＝本家上櫃兩檔（00998A 股票＋00986D 債券，Yahoo 代碼 .TWO）
    other = [c for c, _, k, *_ in etfwatch.WATCHLIST if k == "other"]
    assert other == ["00998A", "00986D"]
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

def test_upcoming_buckets_and_self_expiry():
    # 2026-07-24：00410A 8/3 掛牌在窗、統一雙檔＋復華 00409A 募集在窗
    up = etfwatch.upcoming(date(2026, 7, 24))
    assert [x["code"] for x in up["listing"]] == ["00410A"]
    assert set(x["code"] for x in up["raising"]) == {"00411A", "00987D", "00409A"}
    # 掛牌後不再出現在「即將掛牌」；募集截止後（含未定截止以起日+fallback 估算）自動移除
    up2 = etfwatch.upcoming(date(2026, 8, 20))
    assert up2["listing"] == []
    assert [x["code"] for x in up2["raising"]] == ["00409A"]
    up3 = etfwatch.upcoming(date(2026, 10, 1))
    assert up3["listing"] == [] and up3["raising"] == []


def test_upcoming_entries_have_required_fields():
    for it in etfwatch.UPCOMING:
        assert it.get("code") and it.get("name") and it.get("issuer")
        assert it.get("url", "").startswith("http")          # 活動介紹連結必備
        assert it.get("list_date") or it.get("raise_start")  # 至少一種日期


def test_dashboard_shows_upcoming_etf_section():
    # 分頁骨架與日期無關（前瞻項目會隨時間過期，故 render 測試只驗恆存的結構）
    html = fund_dashboard.render()
    assert 'id="etf-upcoming"' in html and "即將登場的新 ETF" in html
    assert 'href="#etf-upcoming"' in html                 # 分頁導覽新增「即將登場」錨點
    assert "即將登場的新 ETF" in html                       # 區塊標題
    # 有前瞻資料時列卡片、無則顯示「近期無」提示——兩者其一必在
    assert "活動介紹" in html or "近期無" in html


def test_upcoming_view_renders_cards_with_links():
    # 固定日期（與 render 的 today 解耦，避免種子過期後測試失敗）
    up = etfwatch.upcoming(date(2026, 7, 24))
    out = fund_dashboard._upcoming_etf_view(up)
    assert "即將掛牌" in out and "即將募集" in out
    assert "00410A" in out and "00411A" in out and "00409A" in out
    assert "活動介紹" in out and "ezmoney.com.tw/events/2026GFTA" in out
    assert '<span class="fh">復華</span>' in out            # 本家以品牌色標示
    assert "掛牌 08/03" in out and "募集 08/05–08/07" in out  # 狀態日期呈現


def test_upcoming_view_empty_shows_hint():
    out = fund_dashboard._upcoming_etf_view({"listing": [], "raising": []})
    assert "近期無" in out and "upnone" in out


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


def test_upcoming_graduation_guard():
    """掛牌逾 14 天仍未轉正 WATCHLIST → 紅。升級只是 stub 兜底（成立日暫用掛牌日、
    無 SEED 底稿）；清理 UPCOMING 舊條目時未轉正的檔會掉出追蹤——這條測試逼在
    下一輪收斂時把它正式移入 WATCHLIST（查證成立日／頻率後補 SEED_PERF）。"""
    from datetime import timedelta
    from arm import clock
    have = {c for c, *_ in etfwatch.WATCHLIST}
    overdue = [it["code"] for it in etfwatch.UPCOMING
               if it.get("list_date") and it["code"] not in have
               and date.fromisoformat(it["list_date"])
               <= clock.today_tw() - timedelta(days=14)]
    assert not overdue, (
        f"{overdue} 掛牌已逾 14 天仍未轉正 WATCHLIST——請 WebSearch 查證成立日／配息頻率後"
        f"移入 WATCHLIST 並補 SEED_PERF（參考 2026-08-05 00410A 轉正做法）")


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
