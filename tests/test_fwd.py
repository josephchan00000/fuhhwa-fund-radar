"""泡沫頁 VER 4「未來獲利」的計算與解析（arm/lab/fwd.py、fwdfetch 的 parse_*；規格 docs/lab_risk_plan.md 第 11 節）。"""
import pytest

from arm.lab import bubspec as BS
from arm.lab import fwd as FW
from arm.lab import fwdfetch as FF


def test_pick_fx_rules():
    fx = {"EUR": 1.16, "TWD": 0.0316, "CNY": 0.14}
    assert FW.pick_fx("USD", fx, 100, 5, 6) == 1.0 and FW.pick_fx(None, fx, 100, 5, 6) == 1.0
    assert FW.pick_fx("EUR", fx, 1641.52, 41.21, 55.9) == 1.16          # ASML：歐元預估，換匯後 34 倍
    assert FW.pick_fx("TWD", fx, 412.61, 17.504, 23.4) == 1.0           # 台積電 ADR：預估已是每 ADR 美元
    assert FW.pick_fx("CNY", fx, 80.97, 68.57, 82.6) == 0.14            # 拼多多：人民幣預估
    assert FW.pick_fx("EUR", fx, 50, -1.0, 2.0) == 1.16                 # 今年虧損：用明年判斷（50 ÷ 2.32 ＝ 21.6 倍）
    assert FW.pick_fx("EUR", fx, 50, -1.0, -2.0) == 1.16                # 兩年都虧：換匯
    assert FW.pick_fx("JPY", fx, 50, 1.0, 2.0) is None                  # 沒有匯率：不算


def _rec(e0, ea, e1, e1o):
    return {"y0": {"e": [e0, None, None, 10, ea], "t": [e0, None, None, None, None]},
            "y1": {"e": [e1, None, None, 10, e0], "t": [e1, None, None, None, e1o]}}


def test_aggregate_growth_revision_and_coverage():
    rows = {"A": FW.est_row(_rec(10, 8, 12, 12.5), 100, 1000), "B": FW.est_row(_rec(5, 5, 5.5, 5), 200, 1000)}
    a = FW.aggregate(rows, 2500)
    assert a["n"] == 2 and a["cov"] == pytest.approx(0.8)
    assert a["g0"] == pytest.approx(2000 / 1800 - 1)                    # 今年 2000 ÷ 去年 1800
    assert a["g1"] == pytest.approx(2300 / 2000 - 1)                    # 明年 2300 ÷ 今年 2000
    assert a["rev"] == pytest.approx(2300 / 2250 - 1)                   # 明年 ÷ 明年 90 天前（1250＋1000）
    assert a["G1"] is False and a["R"] is False                        # 明年 +15% 比今年 +11.1% 快；預估上修 2.2%
    assert FW.aggregate(rows, 10_000)["G1"] is None                     # 涵蓋 20% < 50%：不判定
    assert FW.est_row(_rec(10, None, 12, 12), 100, 1) is None           # 缺去年：不算


def test_aggregate_g1_direction():
    rows = {"A": FW.est_row(_rec(20, 10, 22, 23), 1, 1)}                 # 今年 +100%、明年 +10%、90 天下修
    a = FW.aggregate(rows, 1)
    assert a["G1"] is True and a["R"] is True
    rows = {"A": FW.est_row(_rec(11, 10, 15, 14), 1, 1)}                 # 今年 +10%、明年 +36%、上修
    a = FW.aggregate(rows, 1)
    assert a["G1"] is False and a["R"] is False


def _spf(y, q, c1, A, B):
    return f"{y}-Q{q}", [c1, None, None, None, None, None, A, B]


def test_spf_table_growth_base_revision_and_break():
    raw = dict([_spf(1980, 2, 100, None, None), _spf(1980, 3, 104, None, None), _spf(1980, 4, 108, None, None),
                _spf(1981, 1, 112, None, None), _spf(1981, 2, 116, None, None), _spf(1981, 3, 120, 118, 130),
                _spf(1981, 4, 122, 119, 125), _spf(1982, 1, 124, 128, 140)])
    T = {r["k"]: r for r in FW.spf_table(raw)}
    assert set(T) == {"1981-Q3", "1981-Q4", "1982-Q1"}                    # 年度預測 1981Q3 起
    base81 = (112 + 108 + 104 + 100) / 4                                  # 1981Q1、1980Q4、Q3、Q2 調查的上一季
    assert T["1981-Q3"]["g0"] == pytest.approx(118 / base81 - 1) and T["1981-Q3"]["g1"] == pytest.approx(130 / 118 - 1)
    assert T["1981-Q3"]["rev"] is None                                    # 上一季調查沒有明年預估
    assert T["1981-Q4"]["rev"] == pytest.approx(125 / 130 - 1) and T["1981-Q4"]["R"] is True
    assert T["1982-Q1"]["rev"] == pytest.approx(128 / 125 - 1)            # 第 1 季：今年預估 ÷ 上一季調查的明年預估
    assert T["1982-Q1"]["g0"] == pytest.approx(128 / ((124 + 122 + 120 + 116) / 4) - 1)   # 1982Q1、1981Q4、Q3、Q2 調查的上一季
    assert FW.spf_avail(1981, 3) == "1981-08-31" and FW.spf_avail(1984, 1) == "1984-02-29" and FW.spf_avail(1983, 4) == "1983-11-30"


def test_spf_break_year():
    raw = dict([_spf(2005, 2, 900, 950, 1000), _spf(2005, 3, 1000, 1030, 1070), _spf(2005, 4, 1030, 1046, 1106),
                _spf(2006, 1, 1031, 1072, 1132), _spf(2006, 2, 1105, 1122, 1155), _spf(2007, 1, 1124, 1150, 1180),
                _spf(2006, 3, 1120, 1124, 1178), _spf(2006, 4, 1124, 1119, 1175)])
    T = {r["k"]: r for r in FW.spf_table(raw)}
    assert all(T[k]["g0"] is None for k in ("2006-Q1", "2006-Q2", "2006-Q3", "2006-Q4"))   # 2006 年去年基準是舊口徑
    assert T["2006-Q1"]["rev"] is None and T["2006-Q2"]["rev"] is not None
    assert T["2007-Q1"]["g0"] == pytest.approx(1150 / ((1124 + 1124 + 1120 + 1105) / 4) - 1)


def test_tech_series_splice():
    nq, na = BS.TECH_NAICS_Q, BS.TECH_NAICS_A
    cq, ca, bq = BS.TECH_SIC_C_Q, BS.TECH_SIC_C_A, BS.TECH_SIC_B_Q
    q = {}
    for m in (3, 6, 9, 12):
        q[f"1986-{m:02d}"] = {c: 10.0 for c in bq}                       # 舊舊分類 30
        q[f"1987-{m:02d}"] = {**{c: 10.0 for c in bq}, **{c: 20.0 for c in cq}}   # 1987 重疊：60 ÷ 30 → k2＝2
        q[f"2000-{m:02d}"] = {c: 20.0 for c in cq}
        q[f"2001-{m:02d}"] = {c: 50.0 for c in nq}
    a = {str(y): {**{c: 40.0 for c in na}, **{c: 20.0 for c in ca}} for y in (1998, 1999, 2000)}   # k1＝80 ÷ 60
    ts = FW.tech_series(q, a)
    k1 = 80.0 / 60.0
    assert ts["2001-03"] == 100.0 and ts["2000-12"] == pytest.approx(60 * k1)
    assert ts["1987-03"] == pytest.approx(60 * k1)                       # 1987 用 6.16C（重疊年以新的為準）
    assert ts["1986-03"] == pytest.approx(30 * k1 * 2.0)
    assert FW.tech_series(q, {})["2001-03"] == 100.0 and "2000-12" not in FW.tech_series(q, {})   # 沒有 k1：舊分類不接


def test_proxy_flags_monthly():
    F = {}
    import datetime
    d = datetime.date(2000, 1, 1)
    vals = [100 * (1.02 ** i) for i in range(36)] + [100 * (1.02 ** 35) * (0.99 ** j) for j in range(1, 13)]
    for i, v in enumerate(vals):
        y, m = 2000 + i // 12, i % 12 + 1
        F[f"{y}-{m:02d}"] = v
    P = FW.proxy_flags(F, "m", 12)
    assert P["2001-12"]["G1"] is None                                    # 年增率要 24 個月、比 6 個月前要 30 個月
    assert P["2002-12"]["G1"] is False and P["2002-12"]["R"] is False    # 穩定成長：沒減速、沒下滑
    assert P["2003-12"]["G1"] is True and P["2003-12"]["R"] is True      # 開始下滑
    assert set(P["2003-12"]) == {"g", "S", "G1", "R"}


def test_parsers_on_probe_formats():
    html = ('<table id="constituents"><tr><th>Symbol</th></tr><tr><td><a href="x">MMM</a></td><td>3M</td></tr>'
            '<tr><td><a>BRK.B</a></td><td>Berkshire</td></tr></table>')
    assert FF.parse_wiki_sp(html) == ["MMM", "BRK-B"]
    ndx = {"data": {"data": {"rows": [{"symbol": "AAPL", "marketCap": "5,012,517,062,800"}, {"symbol": "AMAT", "marketCap": ""}]}}}
    assert FF.parse_nq_rows(ndx) == [("AAPL", 5012517062800.0), ("AMAT", None)]
    scr = {"data": {"rows": [{"symbol": "AACG", "marketCap": "43337725.00"}]}}
    assert FF.parse_nq_rows(scr) == [("AACG", 43337725.0)]
    assert FF.parse_sox({"aaData": [{"Name": "ANALOG DEVICES CMN", "Symbol": "ADI"}, {"Symbol": "ASML"}]}) == ["ADI", "ASML"]
    v7 = {"quoteResponse": {"result": [{"symbol": "TSM", "marketCap": 2.14e12, "sharesOutstanding": 5186474013,
                                         "regularMarketPrice": 412.61, "financialCurrency": "TWD"},
                                        {"symbol": "EURUSD=X", "regularMarketPrice": 1.16}]}}
    assert FF.parse_v7(v7) == {"TSM": [2.14e12, 5186474013, 412.61, "TWD"], "EURUSD=X": [None, None, 1.16, None]}
    rows = [["YEAR", "QUARTER", "CPROF1", "CPROF2", "CPROF3", "CPROF4", "CPROF5", "CPROF6", "CPROFA", "CPROFB"],
            [1968.0, 4.0, 51.0, 51.2, 51.0, 51.0, 52.0, 53.0, "#N/A", "#N/A"]]
    assert FW.spf_parse(rows) == {"1968-Q4": [51.0, 51.2, 51.0, 51.0, 52.0, 53.0, None, None]}
