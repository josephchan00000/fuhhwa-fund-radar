"""官方免費資料：處置公告（證交所、櫃買）與集保股權分散表。樣本格式取自 2026-10-15 CI 實測（scripts/probe_official.py）。"""

from __future__ import annotations

import re

import pandas as pd
import pytest
import requests

from superstock import official as O
from superstock.engine import Market

TW_FIELDS = ["編號", "公布日期", "證券代號", "證券名稱", "累計", "處置條件", "處置起迄時間", "處置措施", "處置內容", "備註"]
TP_FIELDS = ["編號", "公布日期", "證券代號", "證券名稱", "累計", "處置起訖時間", "處置原因", "處置措施", "處置內容",
             "收盤價", "本益比", " "]


def twse_json(rows, total=None):
    return {"stat": "OK", "title": "公布處置有價證券資訊", "fields": TW_FIELDS, "data": rows,
            "count": len(rows), "total": len(rows) if total is None else total}


def tpex_json(rows, date):
    return {"stat": "ok", "date": date, "tables": [{"title": "上櫃處置有價證券", "fields": TP_FIELDS, "data": rows}]}


TW_ROWS = [
    [1, "113/01/11", "8467", "波力-KY", 1, "連續三次及當日沖銷標準", "113/01/12～113/01/29", "第一次處置",
     "１處置原因：…\n３處置措施：\nａ以人工管制之撮合終端機執行撮合作業（約每五分鐘撮合一次）。\n", "\n提供…"],
    [2, "113/01/25", "9103", "美德醫療-DR", 3, "連續五次", "113/01/26～113/02/19", "第二次處置",
     "ａ以人工管制之撮合終端機執行撮合作業（約每二十分鐘撮合一次）。", ""],
    [3, "113/10/04", "068389", "T50反1元大3B購01", 1, "連續三次", "113/10/07～113/10/21", "第一次處置", "…", ""],
    [4, "96/12/28", "3041", "揚智", 1, "最近十個營業日已有六次", "96/12/31～97/01/07", "收足五成款券", " ", ""],
]
TP_ROWS = [
    [1, "113/01/30", "", "                ", "", "", "", "", "本日無處置資料", "", "", ""],
    [2, "113/12/30", "5314", "世紀(../../mainboard/listed/company-detail.html?code=5314)", 3, "113/12/31~114/01/14",
     "連續3個營業日", "再次處置", "…改以人工管制之撮合終端機執行撮合作業(約每20分鐘撮合一次)…", "726.00", "70.49", ""],
    [3, "115/10/15", "81114", "立碁四(../../mainboard/listed/company-detail.html?code=81114)", 2, "115/10/16~115/10/22",
     "轉(交)換公司債之標的證券經本中心或臺灣證券交易所發布處置", "第一次處置", "…", "", "", ""],
    [4, "115/10/15", "8111", "立碁(../../mainboard/listed/company-detail.html?code=8111)", 2, "115/10/16~115/10/22",
     "最近10個營業日內有6個營業日", "第一次處置", "(1)以人工管制之撮合終端機執行撮合作業(約每2分鐘撮合一次)；", "82.00", "71.93", ""],
]


def test_roc_dates_and_numbers():
    assert O.roc_date("113/01/11") == pd.Timestamp("2024-01-11")
    assert O.roc_date("96/12/28") == pd.Timestamp("2007-12-28")
    assert pd.isna(O.roc_date("")) and pd.isna(O.roc_date("113/13/01"))
    assert O.period("113/01/12～113/01/29") == (pd.Timestamp("2024-01-12"), pd.Timestamp("2024-01-29"))
    assert O.period("113/12/31~114/01/14") == (pd.Timestamp("2024-12-31"), pd.Timestamp("2025-01-14"))
    assert [O.cn_int(x) for x in ("五", "二十", "十", "二十五", "2", "２０")] == [5, 20, 10, 25, 2, 20]
    assert O.cn_int("abc") is None and O.match_minutes("沒有") is None


def test_parse_twse_keeps_common_stocks_with_period_level_minutes():
    df, total = O.parse_twse(twse_json(TW_ROWS))
    assert total == 4 and list(df["stock_id"]) == ["8467", "9103", "3041"]   # 6 碼權證剔除
    r = df.set_index("stock_id")
    assert r.loc["8467", "date"] == pd.Timestamp("2024-01-11")
    assert (r.loc["8467", "period_start"], r.loc["8467", "period_end"]) == (pd.Timestamp("2024-01-12"),
                                                                            pd.Timestamp("2024-01-29"))
    assert r.loc["8467", "level"] == 1 and r.loc["9103", "level"] == 2 and r.loc["3041", "level"] == 1
    assert r.loc["8467", "match_minutes"] == 5 and r.loc["9103", "match_minutes"] == 20
    assert pd.isna(r.loc["3041", "match_minutes"]) and r.loc["3041", "measure"] == "收足五成款券"
    assert set(df["market"]) == {"twse"} and list(df.columns) == O.DISP_COLS


def test_parse_twse_empty_and_error():
    df, total = O.parse_twse({"stat": "很抱歉，沒有符合條件的資料!"})
    assert df.empty and total == 0
    with pytest.raises(ValueError):
        O.parse_twse({"stat": "查詢日期大於今日"})
    with pytest.raises(ValueError):
        O.parse_twse({"stat": "OK", "fields": ["編號", "名稱"], "data": [[1, "x"]]})


def test_parse_tpex_skips_no_data_rows_cleans_names_and_checks_range():
    df = O.parse_tpex(tpex_json(TP_ROWS, "20240101~20241231"), expect="20240101~20241231")
    assert list(df["stock_id"]) == ["5314", "8111"]                            # 「本日無處置資料」、可轉債剔除
    r = df.set_index("stock_id")
    assert r.loc["5314", "stock_name"] == "世紀" and r.loc["8111", "stock_name"] == "立碁"
    assert r.loc["5314", "level"] == 2 and r.loc["8111", "level"] == 1           # 再次處置＝第二次
    assert r.loc["5314", "match_minutes"] == 20 and r.loc["8111", "match_minutes"] == 2
    assert r.loc["5314", "period_end"] == pd.Timestamp("2025-01-14")
    # 查詢失敗時櫃買回傳今天的資料：區間對不上要報錯，不能把今天的處置當成那一年
    with pytest.raises(ValueError):
        O.parse_tpex(tpex_json(TP_ROWS, "20261015~20261015"), expect="20080101~20081231")


class FakeResp:
    def __init__(self, payload=None, content=b"", status=200):
        self.payload, self.content, self.status_code = payload, content, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload


class FakeSession:
    """依網址回應：證交所／櫃買處置公告每年一筆（公告日在該年 3/1）。"""

    def __init__(self, twse_total_extra=0):
        self.urls: list[str] = []
        self.extra = twse_total_extra

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        if "twse.com.tw" in url:
            a = re.search(r"startDate=(\d{8})", url).group(1)
            b = re.search(r"endDate=(\d{8})", url).group(1)
            roc = int(a[:4]) - 1911
            row = [1, f"{roc}/03/01", "2330", "台積電", 1, "連續三次", f"{roc}/03/02～{roc}/03/15", "第一次處置",
                   "（約每五分鐘撮合一次）", ""]
            if a[4:] == "0101" and b[4:] != "0131":                # 整年（或今年到今天）的查詢
                return FakeResp(twse_json([row], total=1 + self.extra))
            return FakeResp(twse_json([row] if a[4:6] == "03" else []))
        a = re.search(r"startDate=(\d{4})/(\d{2})/(\d{2})", url)
        b = re.search(r"endDate=(\d{4})/(\d{2})/(\d{2})", url)
        y, roc = int(a.group(1)), int(a.group(1)) - 1911
        rows = [[1, f"{roc}/05/01", "6488", "環球晶(../../x)", 1, f"{roc}/05/02~{roc}/05/15", "連續3個營業日",
                 "第一次處置", "(約每5分鐘撮合一次)", "", "", ""]]
        return FakeResp(tpex_json(rows, f"{''.join(a.groups())}~{''.join(b.groups())}"))


def test_update_disposition_skips_final_years_and_refetches_current(tmp_path):
    s = FakeSession()
    res = O.update_disposition(tmp_path, "2023-01-01", pd.Timestamp("2025-01-20"), s, sleep=lambda *_: None)
    assert res["twse"] == {2023: 1, 2024: 1, 2025: 1} and res["tpex"] == {2023: 1, 2024: 1, 2025: 1}
    assert len(s.urls) == 6
    # 本年的查詢只到今天；櫃買用西元日期
    assert any("endDate=20250120" in u for u in s.urls) and any("endDate=2025/01/20" in u for u in s.urls)
    # 同一天再跑：2023、2024 年已在隔年 1/15 之後抓過＝完整，只重抓 2025
    s2 = FakeSession()
    res2 = O.update_disposition(tmp_path, "2023-01-01", pd.Timestamp("2025-01-20"), s2, sleep=lambda *_: None)
    assert res2["twse"][2023] is None and res2["twse"][2025] == 1 and len(s2.urls) == 2
    s3 = FakeSession()
    O.update_disposition(tmp_path, "2023-01-01", pd.Timestamp("2025-01-20"), s3, refresh=True, sleep=lambda *_: None)
    assert len(s3.urls) == 6
    d = O.build_disposition(tmp_path)
    assert len(d) == 6 and set(d["market"]) == {"twse", "tpex"}
    t = O.disposition_years(tmp_path)
    assert list(t["year"]) == [2023, 2024, 2025] and list(t["twse"]) == [1, 1, 1]


def test_year_fetched_before_jan_15_is_not_final(tmp_path):
    O.update_disposition(tmp_path, "2024-01-01", pd.Timestamp("2024-12-20"), FakeSession(), sleep=lambda *_: None)
    s = FakeSession()
    O.update_disposition(tmp_path, "2024-01-01", pd.Timestamp("2025-01-03"), s, sleep=lambda *_: None)
    assert any("startDate=20240101" in u for u in s.urls)   # 2024 年底前幾天的公告要補


def test_twse_total_mismatch_falls_back_to_months():
    s = FakeSession(twse_total_extra=5)
    df = O.fetch_disposition(s, "twse", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31"), sleep=lambda *_: None)
    assert len(s.urls) == 13 and len(df) == 1   # 整年 1 次＋逐月 12 次


def test_get_json_retries_html_block_page():
    calls = []

    class S:
        def get(self, url, headers=None, timeout=None):
            calls.append(url)
            return FakeResp(None if len(calls) < 3 else {"stat": "OK"})

    assert O._get_json(S(), "https://x", sleep=lambda *_: None) == {"stat": "OK"} and len(calls) == 3


def test_build_dedupes_overlapping_years_and_feeds_engine(tmp_path):
    d = O._disp_dir(tmp_path)
    d.mkdir(parents=True)
    df, _ = O.parse_twse(twse_json(TW_ROWS[:1]))
    df.to_parquet(d / "twse_2023.parquet", index=False)   # 跨年處置在兩年的查詢都會出現
    df.to_parquet(d / "twse_2024.parquet", index=False)
    disp = O.build_disposition(tmp_path)
    assert len(disp) == 1
    dates = pd.bdate_range("2024-01-08", "2024-02-02")
    prices = pd.DataFrame([{"date": t, "stock_id": "8467", "adj_open": 10.0, "adj_high": 10.0, "adj_low": 10.0,
                            "adj_close": 10.0, "adj_factor": 1.0, "value": 1e8, "volume": 1e6} for t in dates])
    m = Market.from_frames(prices, None, disp)
    dp = pd.Series(m.dp[:, 0], index=m.dates)
    assert not dp[pd.Timestamp("2024-01-11")] and dp[pd.Timestamp("2024-01-12")] and dp[pd.Timestamp("2024-01-29")]
    assert not dp[pd.Timestamp("2024-01-30")] and int(dp.sum()) == 12   # 1/12～1/29 共 12 個交易日


TDCC_CSV = """資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%
20261008,000218,1,0,0,0.00
20261008,2330,1,1000,100000,0.01
20261008,2330,12,10,5000000,1.50
20261008,2330,13,5,3500000,1.00
20261008,2330,14,3,2700000,0.80
20261008,2330,15,100,800000000,85.00
20261008,2330,16,0,0,0.00
20261008,2330,17,2000000,25930000000,100.00
"""


def test_tdcc_parse_summary_save_and_available_date(tmp_path):
    long = O.parse_tdcc(("﻿" + TDCC_CSV).encode("utf-8"))
    assert set(long["stock_id"]) == {"2330"} and long["level"].max() == 17
    s = O.tdcc_summary(long).iloc[0]
    assert s["big1000_pct"] == 85.0 and round(s["big400_pct"], 2) == 88.3
    assert s["holders"] == 2_000_000 and s["shares"] == 25_930_000_000
    path, new = O.save_tdcc(long, tmp_path)
    assert new and path.name == "2026-10-08.parquet"
    assert O.save_tdcc(long, tmp_path) == (path, False)
    cal = pd.Series(pd.to_datetime(["2026-10-07", "2026-10-08", "2026-10-12", "2026-10-13"]))   # 10/9 休市
    b = O.build_tdcc(tmp_path, cal)
    assert b.loc[0, "available_date"] == pd.Timestamp("2026-10-12")
    assert O.build_tdcc(tmp_path).loc[0, "available_date"] == pd.Timestamp("2026-10-09")   # 沒日曆：下一個平日


def test_tdcc_bad_header_raises():
    with pytest.raises(ValueError):
        O.parse_tdcc("代號,人數\n2330,1\n")


def test_fetch_tdcc_falls_back_to_lenient_tls(monkeypatch):
    class Bad:
        def get(self, *a, **k):
            raise requests.exceptions.SSLError("Missing Subject Key Identifier")

    class Good:
        def get(self, *a, **k):
            return FakeResp(content=TDCC_CSV.encode("utf-8"))

    monkeypatch.setattr(O, "_lenient_tls_session", lambda: Good())
    assert len(O.fetch_tdcc(Bad(), sleep=lambda *_: None)) == 7


def test_update_all_never_raises(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("維護中")

    monkeypatch.setattr(O, "fetch_disposition", boom)
    monkeypatch.setattr(O, "fetch_tdcc", boom)
    res = O.update_all(tmp_path, "2025-01-01", pd.Timestamp("2025-03-01"), session=FakeSession(), sleep=lambda *_: None)
    assert "disposition_error" in res and "tdcc_error" in res


def test_official_cli(tmp_path, monkeypatch, capsys):
    from superstock import cli
    cfg = tmp_path / "c.yaml"
    cfg.write_text(f'data_dir: "{tmp_path / "data"}"\nreports_dir: "{tmp_path / "r"}"\nstart_date: "2025-01-01"\n',
                   encoding="utf-8")
    monkeypatch.setattr(O, "fetch_disposition", lambda s, m, a, b, sleep=None: O.parse_twse(twse_json(TW_ROWS[:1]))[0]
                        .assign(market=m))
    monkeypatch.setattr(O, "fetch_tdcc", lambda session=None, sleep=None: O.parse_tdcc(TDCC_CSV))
    monkeypatch.setattr(O, "SPACING_SEC", 0)
    assert cli.main(["--config", str(cfg), "official"]) == 0
    out = capsys.readouterr().out
    assert "處置公告" in out and "集保股權分散表" in out
    assert (tmp_path / "data" / "raw" / "official" / "tdcc" / "2026-10-08.parquet").exists()


def test_sponsor_datasets_not_downloaded_by_default():
    from superstock.config import load_config
    from superstock.datasets import specs_for_groups
    names = {s.name for s in specs_for_groups(load_config("config.yaml").download_groups)}
    assert "TaiwanStockDispositionSecuritiesPeriod" not in names and "TaiwanStockHoldingSharesPer" not in names
    assert {s.name for s in specs_for_groups(["sponsor"])} == {
        "TaiwanStockDispositionSecuritiesPeriod", "TaiwanStockHoldingSharesPer", "TaiwanStockPriceAdj"}
