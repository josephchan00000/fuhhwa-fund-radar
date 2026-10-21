"""台股「最新交易日」官方報價（ETF 持股詳情；2026-10-21 使用者：「ETF持股異動那邊，漲跌幅是錯的」）。

盤查（docs/etf_chg_fix_plan.md）：證交所 openapi 隔天清晨才更新、櫃買當晚就更新——舊碼抓「當下那份」，
晚上那幾班同一張表上市＝前一天、上櫃＝當天。這裡守住：上市、上櫃一定同一天；openapi 日期不對就抓指定日期版；
指定日期版的漲跌欄（正負號在另一欄）解析對；自我檢查擋下錯號。
"""
from datetime import datetime

from arm import clock, dayquotes as DQ
from arm import etfholdings as eh

TW = clock.TW_TZ


def _now(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=TW)


def _fill(n: int, d: str, prefix: str) -> dict:
    """湊滿列數門檻的平盤填充股（收盤 10、漲跌 0）。"""
    return {f"{prefix}{i:04d}": {"date": d, "close": 10.0, "change": 0.0, "name": ""} for i in range(n)}


def _prev_ok(q: dict) -> dict:
    """與報價自洽的前一交易日收盤（收盤 − 漲跌）。"""
    return {k: round(v["close"] - v["change"], 4) for k, v in q.items() if v.get("change") is not None}


# ── 最新交易日的候選 ─────────────────────────────────────────────────

def test_candidates_follow_official_calendar_and_two_pm_cut():
    # 早上：最新交易日＝前一交易日
    assert DQ.candidates(_now("2026-10-21T08:39"))[0] == "2026-10-20"
    # 交易日 14:00 以後：先試今天
    assert DQ.candidates(_now("2026-10-20T19:02")) == ["2026-10-20", "2026-10-19", "2026-10-16"]
    assert DQ.candidates(_now("2026-10-20T13:59"))[0] == "2026-10-19"
    # 週末 → 週五；10/9 國慶補假、10/12 週一盤前 → 10/8
    assert DQ.candidates(_now("2026-10-18T10:00"))[0] == "2026-10-16"
    assert DQ.candidates(_now("2026-10-12T10:00")) == ["2026-10-08", "2026-10-07", "2026-10-06"]


# ── 指定日期版解析 ───────────────────────────────────────────────────

_MI_FIELDS = ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價",
              "收盤價", "漲跌(+/-)", "漲跌價差", "最後揭示買價", "最後揭示買量", "最後揭示賣價",
              "最後揭示賣量", "本益比"]


def _mi_row(code, name, close, sign, mag):
    return [code, name, "1,000", "10", "1,000,000", close, close, close, close, sign, mag,
            close, "1", close, "1", "0.00"]


def test_parse_mi_index_sign_comes_from_separate_column():
    """MI_INDEX 的漲跌價差不帶正負號——正負號在「漲跌(+/-)」欄的 HTML 裡；X＝不比價。"""
    doc = {"stat": "OK", "date": "20261020", "tables": [
        {"fields": ["指數", "收盤指數", "漲跌(+/-)", "漲跌點數", "漲跌百分比(%)", "特殊處理註記"],
         "data": [["發行量加權股價指數", "46,292.93", "<p style ='color:green'>-</p>", "529.15", "-1.13", ""]]},
        {"fields": _MI_FIELDS, "data": [
            _mi_row("2330", "台積電", "2,405.00", "<p style= color:green>-</p>", "15.00"),
            _mi_row("2317", "鴻海", "241.50", "<p style= color:red>+</p>", "2.00"),
            _mi_row("2603", "長榮", "180.00", "<p> </p>", "0.00"),
            _mi_row("6666", "新股", "50.00", "<p>X</p>", "0.00"),
            _mi_row("1234", "無成交", "--", "<p> </p>", "0.00"),
            _mi_row("033456", "權證", "1.00", "<p style= color:red>+</p>", "0.10"),
        ]}]}
    q = DQ.parse_mi_index(doc)
    assert q["2330"]["close"] == 2405.0 and q["2330"]["change"] == -15.0
    assert q["2317"]["change"] == 2.0 and q["2603"]["change"] == 0.0
    assert q["6666"]["change"] is None                    # 不比價 → 不算漲跌
    assert "1234" not in q and "033456" not in q          # 無成交、權證不收
    assert q["2330"]["name"] == "台積電"


def test_parse_mi_index_without_sign_column_uses_signed_magnitude():
    fields = [f for f in _MI_FIELDS if f != "漲跌(+/-)"]
    row = ["2330", "台積電", "1", "1", "1", "2,405.00", "2,405.00", "2,405.00", "2,405.00", "-15.00",
           "1", "1", "1", "1", "1"]
    assert DQ.parse_mi_index({"tables": [{"fields": fields, "data": [row]}]})["2330"]["change"] == -15.0


def test_parse_tpex_change_column():
    fields = ["代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低", "均價 ", "成交股數  "]
    doc = {"date": "20261020", "tables": [{"fields": fields, "data": [
        ["6223", "旺矽", "4,585.00", "-315.00", "", "", "", "", "1,000"],
        ["5274", "信驊", "15,820.00", "+80.00", "", "", "", "", "1,000"],
        ["3105", "穩懋", "300.00", "0.00", "", "", "", "", "1,000"],
        ["8299", "群聯", "1,200.00", "除息", "", "", "", "", "1,000"],
    ]}]}
    q = DQ.parse_tpex(doc)
    assert q["6223"]["change"] == -315.0 and q["5274"]["change"] == 80.0
    assert q["3105"]["change"] == 0.0 and q["8299"]["change"] is None


def test_fetch_tpex_rejects_response_for_another_day(monkeypatch):
    """櫃買尚未公布或休市時會回最近交易日的資料——回應日≠請求日一律不收。"""
    from arm.lab import market as M
    doc = {"date": "20261019", "tables": [{"fields": ["代號", "名稱", "收盤", "漲跌"],
                                           "data": [["6223", "旺矽", "4,900", "+10"]] * 400}]}
    monkeypatch.setattr(M, "_get", lambda url, **kw: (doc, "ok"))
    q, st = DQ.fetch_tpex("2026-10-20")
    assert q is None and "回應日" in st


# ── 主流程：同一天、日期不對就換來源 ───────────────────────────────

def _scenario_evening():
    """10/20 19:02 實況：證交所 openapi 還是 10/19、櫃買 openapi 已是 10/20。"""
    tw19 = {**_fill(700, "2026-10-19", "T"),
            "2330": {"date": "2026-10-19", "close": 2420.0, "change": 0.0, "name": "台積電"},
            "3037": {"date": "2026-10-19", "close": 1120.0, "change": 30.0, "name": "欣興"}}
    tp20 = {**_fill(400, "2026-10-20", "P"),
            "6223": {"date": "2026-10-20", "close": 4585.0, "change": -315.0, "name": "旺矽"}}
    mi20 = {**{k: {**v, "date": "2026-10-20"} for k, v in _fill(700, "2026-10-20", "T").items()},
            "2330": {"close": 2405.0, "change": -15.0, "name": "台積電"},
            "3037": {"close": 1055.0, "change": -65.0, "name": "欣興"}}
    return tw19, tp20, mi20


def test_evening_twse_openapi_is_previous_day_so_fetch_mi_index():
    """回歸（2026-10-20 19:02 那版）：00981A 欣興顯示 10/19 的 +2.75%，10/20 實際 −5.80%。"""
    tw19, tp20, mi20 = _scenario_evening()
    calls = []

    def fetch_tw(d):
        calls.append(d)
        return ({k: {kk: vv for kk, vv in v.items() if kk != "date"} for k, v in mi20.items()}, "ok")

    def fetch_tp(d):
        raise AssertionError("櫃買 openapi 已是 10/20，不該再抓指定日期版")
    T, q, info = DQ.latest(_now("2026-10-20T19:02"), today_all={"twse": tw19, "tpex": tp20},
                           fetch_tw=fetch_tw, fetch_tp=fetch_tp,
                           prev_closes=lambda d: {**_prev_ok(mi20), **_prev_ok(tp20)})
    assert T == "2026-10-20" and calls == ["2026-10-20"]
    assert q["3037"]["change"] == -65.0 and q["3037"]["date"] == "2026-10-20"
    assert q["2330"]["close"] == 2405.0 and q["6223"]["change"] == -315.0
    assert {v["date"] for v in q.values()} == {"2026-10-20"}          # 上市、上櫃同一天
    assert info["tw_src"] == "mi_index" and info["tp_src"] == "openapi"
    # 接到持股明細：漲跌一律是 10/20
    entry = {"date": "2026-10-20", "src": "etfinfo", "prev": {},
             "holdings": [{"stock_id": "2330", "name": "台積電", "shares": 1, "weight": 9.0},
                          {"stock_id": "3037", "name": "欣興", "shares": 1, "weight": 5.0},
                          {"stock_id": "6223", "name": "旺矽", "shares": 1, "weight": 3.0}]}
    det = eh.contributions(entry, q, pd=T)
    by = {r["stock_id"]: r for r in det["all"]}
    assert by["3037"]["chg_pct"] == -5.8 and by["2330"]["chg_pct"] == -0.62
    assert by["6223"]["chg_pct"] == -6.43
    assert {r["qd"] for r in det["all"]} == {"2026-10-20"} and det["pd"] == "2026-10-20"


def test_morning_openapi_already_latest_needs_no_extra_request():
    q20 = _fill(700, "2026-10-20", "T")
    p20 = _fill(400, "2026-10-20", "P")

    def boom(d):
        raise AssertionError("openapi 已是最新交易日，不該再發請求")
    T, q, info = DQ.latest(_now("2026-10-21T08:39"), today_all={"twse": q20, "tpex": p20},
                           fetch_tw=boom, fetch_tp=boom, prev_closes=lambda d: {})
    assert T == "2026-10-20" and info["tw_src"] == info["tp_src"] == "openapi"


def test_never_mixes_days_when_one_market_lacks_the_latest_day():
    """櫃買 10/20 拿不到 → 整張表退到 10/19（兩市都 10/19），絕不上市 10/20 配上櫃 10/19。"""
    tw19 = _fill(700, "2026-10-19", "T")
    tp19 = _fill(400, "2026-10-19", "P")
    T, q, info = DQ.latest(_now("2026-10-20T19:02"), today_all={"twse": tw19, "tpex": tp19},
                           fetch_tw=lambda d: ({k: dict(v) for k, v in _fill(700, d, "T").items()}, "ok"),
                           fetch_tp=lambda d: (None, "nodata:回應日 20261019≠20261020"),
                           prev_closes=lambda d: {})
    assert T == "2026-10-19" and {v["date"] for v in q.values()} == {"2026-10-19"}
    assert any("上櫃" in t for t in info["tried"])


def test_selfcheck_rejects_flipped_signs():
    """正負號解析錯（漲跌號全反）→ 收盤 − 漲跌 對不上前一交易日收盤 → 不採用，換前一天。"""
    good = {f"{1000 + i}": {"close": 100.0 + i % 7, "change": float(i % 5 - 2)} for i in range(700)}
    bad = {k: {**v, "change": -v["change"]} for k, v in good.items()}
    prev = _prev_ok(good)
    assert DQ.check_ok(*DQ.selfcheck(good, "2026-10-20", prev))
    ok, n = DQ.selfcheck(bad, "2026-10-20", prev)
    assert not DQ.check_ok(ok, n) and n == 700
    tp = {**_fill(400, "2026-10-20", "P"), **_fill(400, "2026-10-19", "Q")}
    T, q, info = DQ.latest(_now("2026-10-20T19:02"),
                           today_all={"twse": {k: {**v, "date": "2026-10-19"} for k, v in good.items()},
                                      "tpex": tp},
                           fetch_tw=lambda d: (bad, "ok"), fetch_tp=lambda d: (None, "nodata"),
                           prev_closes=lambda d: prev if d == "2026-10-20" else {})
    assert T == "2026-10-19"
    assert any("自我檢查未過" in t for t in info["tried"])


def test_selfcheck_skipped_when_too_few_comparable():
    assert DQ.check_ok(0, 0) and DQ.check_ok(10, 99)
    assert not DQ.check_ok(50, 100)


def test_prev_closes_only_uses_the_exact_previous_trading_day(monkeypatch):
    """前一交易日那片缺時不可拿更早的頂——漲跌會變兩天累計，整批誤判。"""
    from arm.lab import store
    shards = {"2026-10-16": {"q_tw": {"2330": [1, 1, 1, 2420.0, 1, 1]}}}
    monkeypatch.setattr(store, "read", lambda kind, d: shards.get(d))
    assert DQ._prev_closes("2026-10-20") == {}           # 前一交易日＝10/19，那片不存在
    shards["2026-10-19"] = {"q_tw": {"2330": [1, 1, 1, 2420.0, 1, 1]}, "q_tp": {"6223": [1, 1, 1, 4900.0, 1, 1, 1]}}
    assert DQ._prev_closes("2026-10-20") == {"2330": 2420.0, "6223": 4900.0}


def test_describe_reports_date_sources_and_check():
    s = DQ.describe({"T": "2026-10-20", "tw_src": "mi_index", "tp_src": "openapi", "tw_n": 1300,
                     "tp_n": 900, "tw_check": (1250, 1290), "tp_check": (0, 0), "tried": []})
    assert "2026-10-20" in s and "mi_index" in s and "1250/1290" in s and "略過" in s
    assert "⚠" in DQ.describe({"tried": ["2026-10-20 上市 mi_index err"]})


def test_openapi_zero_change_with_moved_close_is_unknown_not_flat():
    """證交所 openapi 不比價（除權息等）的列 Change＝0：2026-09-23 1808 除息 1.5、收 31.9（前收 35.0、
    參考價 33.5，對參考價 −4.78%），隔天清晨那版明細顯示 0.0%。收盤≠前一交易日收盤卻漲跌 0 → 未知（None）。"""
    tw = {**_fill(700, "2026-09-23", "T"),
          "1808": {"date": "2026-09-23", "close": 31.9, "change": 0.0, "name": "潤隆"},
          "2330": {"date": "2026-09-23", "close": 1300.0, "change": 0.0, "name": "台積電"}}   # 真的平盤
    tp = _fill(400, "2026-09-23", "P")
    prev = {**_prev_ok(tw), "1808": 35.0}
    T, q, info = DQ.latest(_now("2026-09-24T08:31"), today_all={"twse": tw, "tpex": tp},
                           prev_closes=lambda d: prev, refs=lambda d: {})      # 沒有除權息參考價
    assert T == "2026-09-23"
    assert q["1808"]["change"] is None and q["1808"]["close"] == 31.9
    assert q["2330"]["change"] == 0.0
    assert tw["1808"]["change"] == 0.0                       # 不改呼叫端傳進來的表
    assert info["x_n"] == 1 and "1 檔漲跌留空（1808）" in DQ.describe(info)
    entry = {"date": "2026-09-23", "src": "etfinfo", "prev": {},
             "holdings": [{"stock_id": "1808", "name": "潤隆", "shares": 1, "weight": 2.0},
                          {"stock_id": "2330", "name": "台積電", "shares": 1, "weight": 9.0}]}
    by = {r["stock_id"]: r for r in eh.contributions(entry, q, pd=T)["all"]}
    assert by["1808"]["chg_pct"] is None and by["2330"]["chg_pct"] == 0.0

    # 有證交所除權息計算結果（前收 35.0、參考價 33.5）→ 漲跌對參考價算：31.9 − 33.5 ＝ −1.6（−4.78%）
    T, q, info = DQ.latest(_now("2026-09-24T08:31"), today_all={"twse": tw, "tpex": tp},
                           prev_closes=lambda d: prev, refs=lambda d: {"1808": (35.0, 33.5)})
    assert q["1808"]["change"] == -1.6 and q["1808"]["ref"] == 33.5 and q["1808"]["pc"] == 35.0
    assert info["x_n"] == 1 and info["xf_n"] == 1 and "1 檔依除權息參考價算" in DQ.describe(info)
    assert DQ.check_ok(*info["tw_check"])                   # 參考價在自我檢查之後才補，不拉低成立率
    by = {r["stock_id"]: r for r in eh.contributions(entry, q, pd=T)["all"]}
    assert by["1808"]["chg_pct"] == -4.78


def test_unknown_x_leaves_rows_alone_without_previous_close():
    q = {"1808": {"close": 31.9, "change": 0.0}}
    assert DQ.unknown_x(q, {}) == (q, 0)


def test_fill_x_only_fills_unknown_rows_whose_previous_close_matches():
    q = {"1808": {"close": 31.9, "change": None},          # MI_INDEX 標 X
         "2542": {"close": 39.55, "change": None},
         "2330": {"close": 1300.0, "change": -5.0}}
    refs = {"1808": (35.0, 33.5), "2542": (45.45, 41.45), "2330": (1305.0, 1300.0)}
    out, n = DQ.fill_x(q, refs, {"1808": 35.0, "2542": 46.0, "2330": 1305.0})
    assert n == 1 and out["1808"]["change"] == -1.6
    assert out["2542"]["change"] is None                    # 前收對不上前一交易日官方收盤 → 不用
    assert out["2330"]["change"] == -5.0 and "ref" not in out["2330"]   # 有漲跌的列不動


def test_refresh_exright_merges_recent_rows_into_lab_store_once_per_day(monkeypatch, tmp_path):
    """divtw／v3div 原本只在回補時更新（2026 年最後一列停在 10/15）；每天補最近兩週、明天的列不收、舊列不動。"""
    from datetime import date
    from arm.lab import store
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(DQ, "_EXR_DONE", set())
    store.write("divtw", "2026", {"rows": [["2026-10-15", "00401A", 0.131, "息", 14.39, 14.25]]})
    calls = []

    def tw(d0, d1):
        calls.append((d0, d1))
        return [["2026-10-15", "00401A", 0.131, "息", 14.39, 14.25],      # 已有
                ["2026-10-21", "00929", 0.38, "息", 29.26, 28.88],
                ["2026-10-22", "0056", 1.0, "息", 58.75, 57.75]]          # 明天：不收

    def tp(d0, d1):
        return [["2026-10-21", "00986D", 14.23, 14.14, 0.09, 0.0]]

    assert DQ.refresh_exright(date(2026, 10, 21), fetch_tw=tw, fetch_tp=tp) == 2
    assert calls == [("2026-10-07", "2026-10-21")]
    rows = store.read("divtw", "2026")["rows"]
    assert [r[1] for r in rows] == ["00401A", "00929"]
    assert DQ.exright_refs("2026-10-21") == {"00929": (29.26, 28.88), "00986D": (14.23, 14.14)}
    assert DQ.refresh_exright(date(2026, 10, 21), fetch_tw=tw, fetch_tp=tp) == 0 and len(calls) == 1
    monkeypatch.setattr(DQ, "_EXR_DONE", set())
    assert DQ.refresh_exright(date(2026, 10, 21), fetch_tw=lambda *a: None, fetch_tp=tp) == 0   # 抓不到：沿用落檔
    assert len(store.read("divtw", "2026")["rows"]) == 2

