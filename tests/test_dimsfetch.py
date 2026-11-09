"""面向指標盤查第 1 段的新資料（docs/lab_dims_plan.md）：解析函式用探針看到的格式測（CI run 42537259417），不連網。"""
from __future__ import annotations

from datetime import date

from arm.lab import heatfetch as F
from arm.lab import heatfetch_us as U
from arm.lab import txocalc as C
from arm.lab import txodata as T
from arm.lab import txoiv as V

LARGE = ("日期,商品(契約),商品名稱(契約名稱),到期月份(週別),交易人類別,前五大交易人買方,前五大交易人賣方,前十大交易人買方,前十大交易人賣方,全市場未沖銷部位數\n"
         "2010/01/04,CPF    ,三十天期利率期貨,201001  ,0,3,3,3,3,3\n"
         "2010/01/04,TX     ,臺股期貨,201001  ,0,20000,15000,28000,22000,60000\n"
         "2010/01/04,TX     ,臺股期貨,999999  ,0,21000,16000,30000,24000,70000\n"
         "2010/01/04,TX     ,臺股期貨,999999  ,1,9000,12000,11000,15000,70000\n"
         "2010/01/04,MTX    ,小型臺指,999999  ,0,4000,3000,5000,4500,20000\n"
         "2010/01/05,TX     ,臺股期貨,999999  ,0,21500,16500,30500,24500,71000\n"
         "說明,,,,,,,,,\n")


def test_parse_large_keeps_all_months_tx_mtx():
    d = F.parse_large(LARGE)
    assert sorted(d) == ["2010-01-04", "2010-01-05"]
    assert d["2010-01-04"]["TX"] == {"0": [21000, 16000, 30000, 24000, 70000], "1": [9000, 12000, 11000, 15000, 70000]}
    assert d["2010-01-04"]["MTX"]["0"] == [4000, 3000, 5000, 4500, 20000]
    assert "CPF" not in d["2010-01-04"]


def test_parse_sbl_sums_by_field_name_and_skips_total_rows():
    doc = {"stat": "OK", "fields": ["代號", "名稱", "前日餘額", "賣出", "買進", "現券", "今日餘額", "次一營業日限額",
                                    "前日餘額", "當日賣出", "當日還券", "當日調整", "當日餘額", "次一營業日可限額", "備註"],
           "data": [["0050", "元大台灣50", "3,140,000", "0", "0", "0", "3,000,000", "1", "10", "0", "0", "0", "2,000,000", "1", ""],
                    ["2330", "台積電", "1", "0", "0", "0", "500,000", "1", "10", "0", "0", "0", "8,000,000", "1", ""],
                    ["合計", "", "", "", "", "", "3,500,000", "", "", "", "", "", "10,000,000", "", ""]]}
    assert F.parse_sbl(doc) == [3_500_000, 10_000_000, 2]
    assert F.parse_sbl({"stat": "查詢日期小於94年7月1日，請重新查詢!", "total": 0}) is None


def test_parse_daytrade_reads_market_share_table():
    doc = {"stat": "OK", "tables": [
        {"title": "115年11月06日 當日沖銷交易統計資訊",
         "fields": ["當日沖銷交易總成交股數", "當日沖銷交易總成交股數占市場比重%", "當日沖銷交易總買進成交金額",
                    "當日沖銷交易總買進成交金額占市場比重%", "當日沖銷交易總賣出成交金額", "當日沖銷交易總賣出成交金額占市場比重%"],
         "data": [["5,979,512,000", "40.12", "300,000,000,000", "35.50", "301,000,000,000", "35.60"]]},
        {"title": "個股", "fields": ["證券代號"], "data": [["2330"]]}]}
    assert F.parse_daytrade(doc) == [40.12, 35.5, 35.6, 300_000_000_000.0]
    assert F.parse_daytrade({"stat": "OK", "tables": []}) is None


def test_parse_nfci():
    txt = ("Friday_of_Week,NFCI,ANFCI,Risk,Credit,Leverage,Nonfinancial_Leverage\n"
           "01/08/1971,0.594,0.588,0.622,-1.114,-1.024,-1.407\n"
           "10/31/2026,-0.512,-0.401,-0.3,-0.2,-0.1,0.05\n")
    d = U.parse_nfci(txt)
    assert d == {"1971-01-08": [0.594, 0.588, 0.622, -1.114, -1.024], "2026-10-31": [-0.512, -0.401, -0.3, -0.2, -0.1]}
    assert U.parse_nfci("Date,X\n01/08/1971,1\n") == {}


def test_parse_aaii_rows_needs_shares_summing_to_one():
    rows = [["1987-07-24", 0.36, 0.5, 0.14], ["2026-11-05", "0.42", "0.30", "0.28"],
            ["2026-11-12", 0.9, 0.5, 0.1], ["Reported Date", "Bullish", "Neutral", "Bearish"]]
    assert U.parse_aaii_rows(rows) == {"1987-07-24": [0.36, 0.5, 0.14], "2026-11-05": [0.42, 0.3, 0.28]}


def test_parse_payems_only_nonfarm_monthly():
    doc = {"Results": {"series": [
        {"seriesID": "CES0000000001", "data": [{"year": "2026", "period": "M10", "value": "159,500"},
                                               {"year": "2026", "period": "M13", "value": "1"}]},
        {"seriesID": "LNS14000000", "data": [{"year": "2026", "period": "M10", "value": "4.3"}]}]}}
    assert U.parse_payems(doc) == {"2026-10": 159500.0}
    assert U.parse_bls(doc) == {"2026-10": [4.3, None, None]}           # us_bls 三欄的格式不變


def _rows_for(day: str, f: float, specs: list[tuple[str, str, float]]) -> list[list]:
    """specs＝[(到期別, 到期日, 波動率)]：用 r＝0 的 Black-Scholes 產生價平附近的結算價。"""
    rows = []
    cal = _cal()
    for code, xd, vol in specs:
        n = V.td_between(cal, day, date.fromisoformat(xd))
        t = n / V.TRADING_YEAR
        for k in range(int(f) - 400, int(f) + 401, 100):
            for cp in ("C", "P"):
                px = round(C.bs(cp, f, k, t, vol), 4)
                row = [None] * len(T.COLS)
                ci = {c: i for i, c in enumerate(T.COLS)}
                row[ci["d"]], row[ci["exp"]], row[ci["k"]], row[ci["cp"]], row[ci["s"]], row[ci["xd"]] = day, code, k, cp, px, xd
                rows.append(row)
    return rows


def _cal() -> list[str]:
    from datetime import timedelta
    d, out = date(2024, 1, 1), []
    while d <= date(2024, 6, 30):
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_day_iv_recovers_flat_vol_and_skips_weeklies_and_near_expiry():
    cal = _cal()
    rows = _rows_for("2024-03-01", 18000, [("202403", "2024-03-20", 0.10), ("202404", "2024-04-17", 0.20),
                                           ("202405", "2024-05-15", 0.20)])
    rows += _rows_for("2024-03-01", 18000, [("202403W1", "2024-03-06", 0.90)])     # 週選不用
    v = V.day_iv(rows, "2024-03-01", 18000.0, cal)
    assert v is not None
    n1 = V.td_between(cal, "2024-03-01", date(2024, 3, 20))
    n2 = V.td_between(cal, "2024-03-01", date(2024, 4, 17))
    assert n1 < V.TARGET_TD < n2
    w = (n2 - V.TARGET_TD) / (n2 - n1)
    want = ((w * 0.01 * n1 + (1 - w) * 0.04 * n2) / V.TARGET_TD) ** 0.5 * 100
    assert abs(v[0] - want) < 0.05 and abs(v[1] - 10.0) < 0.05 and v[2] == n1
    near = _rows_for("2024-03-18", 18000, [("202403", "2024-03-20", 0.5), ("202404", "2024-04-17", 0.15)])
    v2 = V.day_iv(near, "2024-03-18", 18000.0, cal)               # 3 月那批只剩 2 個交易日 → 只用 4 月
    assert abs(v2[0] - 15.0) < 0.05 and v2[2] > V.TARGET_TD


def test_td_between_past_calendar_end_uses_holiday_table():
    cal = ["2026-11-04", "2026-11-05", "2026-11-06"]
    assert V.td_between(cal, "2026-11-04", date(2026, 11, 6)) == 2
    assert V.td_between(cal, "2026-11-05", date(2026, 11, 11)) == 1 + C.trading_days(date(2026, 11, 6), date(2026, 11, 11))
