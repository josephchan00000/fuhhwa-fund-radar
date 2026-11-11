"""台指選擇權資料層（arm/lab/txodata.py；docs/lab_txo_plan.md 第 15 節）：解析期交所格式、分 K、篩選、決定性輸出。
樣本列照 2026-11-04 CI 探針印出來的真實格式（scripts/probe_txo.py）。"""
import io
from datetime import date

from arm.lab import txodata as T

TICK_CSV = (
    "成交日期,商品代號,履約價格,到期月份(週別),買賣權別,成交時間,成交價格,成交數量(B or S),開盤集合競價\n"
    "---------- ---- ------- ---- -----\n"
    "20261104,CAO,235,202611W2,P,122057,1.95,1,\n"                 # 別的商品
    "20261103,TXO,42000,202611W1,P,231500,9.0,2,\n"                 # 前一晚夜盤（日期不同）
    "20261104,TXO,42000,202611W1,P,030000,8.5,2,\n"                 # 當天凌晨夜盤（時間在日盤外）
    "20261104,TXO,42000,202611W1,P,090114,7.0,4,\n"
    "20261104,TXO,42000,202611W1,P,090130,7.5,2,\n"
    "20261104,TXO,42000,202611W1,P,090159,6.5,2,\n"
    "20261104,TXO,42000,202611W1,P,115400,179.0,6,\n"
    "20261104,TXO,52000,202611W1,C,090500,0.1,2,\n"                 # 離指數太遠（±8% 外）
    "20261104,TXO,43000,202703,C,091000,2000,2,\n"                  # 到期超過 45 天
    "20261104,TXO,42500,202611F1,C,120647,10.5,2,\n"
)


def test_exp_date_rules():
    assert T.exp_date("202611W1") == date(2026, 11, 4)
    assert T.exp_date("202611F1") == date(2026, 11, 6)
    assert T.exp_date("202611W2") == date(2026, 11, 11)
    assert T.exp_date("202611") == date(2026, 11, 18)
    assert T.exp_date("202612") == date(2026, 12, 16)
    assert T.exp_date("202611F2") == date(2026, 11, 13)


def test_parse_ticks_keeps_txo_day_session_only():
    tk = T.parse_ticks(io.StringIO(TICK_CSV), date(2026, 11, 4))
    assert set(tk) == {("202611W1", "P", 42000), ("202611W1", "C", 52000), ("202703", "C", 43000), ("202611F1", "C", 42500)}
    assert [p for _, p, _ in tk[("202611W1", "P", 42000)]] == [7.0, 7.5, 6.5, 179.0]


def test_bars_roundtrip_and_selection():
    tk = T.parse_ticks(io.StringIO(TICK_CSV), date(2026, 11, 4))
    doc = T.bars_doc(date(2026, 11, 4), tk, 43307.54)
    assert set(doc["c"]) == {"202611W1|P|42000", "202611F1|C|42500"}            # 太遠、太久以後到期的都不存
    assert doc["exp"]["202611W1"] == "2026-11-04" and "202703" not in doc["exp"]
    b = T.from_bars(doc["c"]["202611W1|P|42000"])
    assert b[0] == (9 * 3600 + 60, 7.0, 7.5, 6.5, 6.5, 8)                       # 09:01 那一根：開 7.0、高 7.5、低 6.5、收 6.5、量 8
    assert b[1][1:] == (179.0, 179.0, 179.0, 179.0, 6) and b[1][0] == 11 * 3600 + 54 * 60


def test_bars_keep_holiday_shifted_expiry():
    # 202610F2 照規則 10/9（週五，國慶連假）到期，順延到 10/12（週一）：那天它就是當天到期的那一批
    tk = {("202610F2", "C", 43000): [(9 * 3600 + 60, 10.0, 2)], ("202610W2", "C", 43000): [(9 * 3600 + 60, 20.0, 2)],
          ("202609F4", "C", 43000): [(9 * 3600 + 60, 30.0, 2)]}
    doc = T.bars_doc(date(2026, 10, 12), tk, 43000.0)
    assert doc["exp"]["202610F2"] == "2026-10-12" and doc["exp"]["202610W2"] == "2026-10-14"
    assert "202609F4" not in doc["exp"]                                          # 超過 SHIFT_DAYS 的舊批不收
    assert set(doc["c"]) == {"202610F2|C|43000", "202610W2|C|43000"}


def test_bars_without_ref_uses_most_traded_strike():
    tk = T.parse_ticks(io.StringIO(TICK_CSV), date(2026, 11, 4))
    doc = T.bars_doc(date(2026, 11, 4), tk, None)
    assert doc["ref"] == 42000.0


DAY_CSV = (
    "交易日期,契約,到期月份(週別),履約價,買賣權,開盤價,最高價,最低價,收盤價,成交量,結算價,未沖銷契約數,最後最佳買價,最後最佳賣價,"
    "歷史最高價,歷史最低價,是否因訊息面暫停交易,交易時段,漲跌價,漲跌%,契約到期日,\n"
    "2026/11/04,TXO,202611W1,38900.0000,買權,-,-,-,-,0,0,0,35,-,-,-,,一般,-,-,20261104\n"         # 沒成交、沒未平倉、沒結算價 → 不留
    "2026/11/04,TXO,202611W1,42000.0000,賣權,7,179,0.1,0.1,1234,0.1,0,0.1,0.2,300,0.1,,一般,-50,-99%,20261104\n"
    "2026/11/04,TXO,202611W1,42000.0000,賣權,9,12,8,8,50,8,10,8,9,300,0.1,,盤後,-,-,20261104\n"     # 夜盤 → 不留
    "2026/11/04,MXO,202611,42000.0000,賣權,9,12,8,8,50,8,10,8,9,300,0.1,,一般,-,-,20261118\n"     # 別的商品
)
OLD_CSV = (
    "交易日期,契約,到期月份(週別),履約價,買賣權,開盤價,最高價,最低價,收盤價,成交量,結算價,未沖銷契約數,最後最佳買價,最後最佳賣價,"
    "歷史最高價,歷史最低價,是否因訊息面暫停交易,交易時段,漲跌價,漲跌%,\n"
    "2008/01/02,TXO,200801  ,7400.0000,買權,1060,1100,905,915,41,915,223,890,910,1100,340,,一般,-185,-16.82%,\n"
)


def test_parse_day_modern_and_old():
    rows = T.parse_day(DAY_CSV)
    assert rows == [["2026-11-04", "202611W1", 42000, "P", 7, 179, 0.1, 0.1, 1234, 0.1, 0, 0.1, 0.2, "2026-11-04"]]
    old = T.parse_day(OLD_CSV)
    assert old == [["2008-01-02", "200801", 7400, "C", 1060, 1100, 905, 915, 41, 915, 223, 890, 910, None]]
    assert len(T.COLS) == len(rows[0])


def test_dump_is_deterministic(tmp_path):
    doc = {"b": [1, 2], "a": "x"}
    assert T.dump(doc) == T.dump({"a": "x", "b": [1, 2]})
    assert T.write(tmp_path, "y/z.json.gz", doc) is True
    assert T.write(tmp_path, "y/z.json.gz", doc) is False                      # 內容沒變不改寫
    assert T.read(tmp_path, "y/z.json.gz") == doc


def test_workflow_puts_vercel_json_on_data_branch():
    # 資料分支沒有兩支 vercel.json 時，Vercel 會試著預覽部署、找不到 Root Directory「dashboard」而寄失敗信（wiki/ops/deploy.md）
    from pathlib import Path
    wf = (Path(__file__).resolve().parent.parent / ".github/workflows/txo_data.yml").read_text(encoding="utf-8")
    step = wf.split("commit 回資料分支", 1)[1]
    cp = step.index("cp ../dashboard/vercel.json dashboard/vercel.json")
    assert "cp ../vercel.json vercel.json" in step and cp < step.index("git add -A")
