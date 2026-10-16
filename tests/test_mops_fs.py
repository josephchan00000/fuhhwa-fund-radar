"""MOPS 綜合損益／資產負債彙總表全部科目解析（docs/lab_company_plan.md 第 3.2 節）。
表頭與樣本列取自 2026-10-16 CI 探針（115 年第 2 季）。"""
from arm.lab import market


def _tbl(head: str, *rows: str) -> str:
    th = "".join(f"<th>{h.strip()}</th>" for h in head.split("|"))
    trs = "".join("<tr>" + "".join(f"<td>{c.strip()}</td>" for c in r.split("|")) + "</tr>" for r in rows)
    return f"<table><tr>{th}</tr>{trs}</table>"


IS_GEN = ("公司代號 | 公司名稱 | 營業收入 | 營業成本 | 原始認列生物資產及農產品之利益（損失） | "
          "生物資產當期公允價值減出售成本之變動利益（損失） | 營業毛利（毛損） | 未實現銷貨（損）益 | 已實現銷貨（損）益 | "
          "營業毛利（毛損）淨額 | 營業費用 | 其他收益及費損淨額 | 營業利益（損失） | 營業外收入及支出 | 稅前淨利（淨損） | "
          "所得稅費用（利益） | 繼續營業單位本期淨利（淨損） | 停業單位損益 | 合併前非屬共同控制股權損益 | 本期淨利（淨損） | "
          "其他綜合損益（淨額） | 合併前非屬共同控制股權綜合損益淨額 | 本期綜合損益總額 | 淨利（淨損）歸屬於母公司業主 | "
          "淨利（淨損）歸屬於共同控制下前手權益 | 淨利（淨損）歸屬於非控制權益 | 綜合損益總額歸屬於母公司業主 | "
          "綜合損益總額歸屬於共同控制下前手權益 | 綜合損益總額歸屬於非控制權益 | 基本每股盈餘（元）")
IS_1301 = ("1301 | 台塑 | 89,239,090 | 81,703,844 | -- | -- | 7,535,246 | -- | -- | 7,535,246 | 5,957,378 | -- | 1,577,868 | "
           "12,657,953 | 14,235,821 | 315,189 | 13,920,632 | -- | -- | 13,920,632 | 200,312,727 | -- | 214,233,359 | "
           "13,920,632 | -- | -- | 214,233,359 | -- | -- | 2.19")
IS_BANK = ("公司代號 | 公司名稱 | 利息淨收益 | 利息以外淨損益 | 呆帳費用、承諾及保證責任準備提存 | 營業費用 | "
           "繼續營業單位稅前淨利（淨損） | 所得稅費用（利益） | 繼續營業單位本期稅後淨利（淨損） | 停業單位損益 | "
           "合併前非屬共同控制股權損益 | 本期稅後淨利（淨損） | 其他綜合損益（稅後） | 合併前非屬共同控制股權綜合損益淨額 | "
           "本期綜合損益總額（稅後） | 淨利（損）歸屬於母公司業主 | 淨利（損）歸屬於共同控制下前手權益 | "
           "淨利（損）歸屬於非控制權益 | 綜合損益總額歸屬於母公司業主 | 綜合損益總額歸屬於共同控制下前手權益 | "
           "綜合損益總額歸屬於非控制權益 | 基本每股盈餘（元）")
IS_2801 = ("2801 | 彰銀 | 15,221,502 | 10,607,584 | 1,490,700 | 11,225,331 | 13,113,055 | 1,798,702 | 11,314,353 | -- | -- | "
           "11,314,353 | 7,471,507 | -- | 18,785,860 | 11,314,353 | -- | -- | 18,785,860 | -- | -- | 0.94")
BS_GEN = ("公司代號 | 公司名稱 | 流動資產 | 非流動資產 | 資產總計 | 流動負債 | 非流動負債 | 負債總計 | 股本 | "
          "權益─具證券性質之虛擬通貨 | 資本公積 | 保留盈餘 | 其他權益 | 庫藏股票 | 歸屬於母公司業主之權益合計 | 共同控制下前手權益 | "
          "合併前非屬共同控制股權 | 非控制權益 | 權益總計 | 待註銷股本股數（單位：股） | 預收股款（權益項下）之約當發行股數（單位：股） | "
          "母公司暨子公司所持有之母公司庫藏股股數（單位：股） | 每股參考淨值")
BS_1301 = ("1301 | 台塑 | 324,650,972 | 456,310,346 | 780,961,318 | 107,764,931 | 98,934,232 | 206,699,163 | 63,657,408 | 0 | "
           "11,858,579 | 210,746,809 | 287,999,359 | 0 | 574,262,155 | 0 | -- | 0 | 574,262,155 | 0 | 0 | 0 | 90.21")
BS_SEC = ("公司代號 | 公司名稱 | 流動資產 | 非流動資產 | 資產總計 | 流動負債 | 非流動負債 | 負債總計 | 股本 | "
          "權益－具證券性質之虛擬通貨 | 資本公積 | 保留盈餘（或累積虧損） | 其他權益 | 庫藏股票 | 歸屬於母公司業主權益合計 | "
          "共同控制下前手權益 | 合併前非屬共同控制股權 | 非控制權益 | 權益總計 | 待註銷股本股數（單位：股） | "
          "預收股款（權益項下）之約當發行股數（單位：股） | 母公司暨子公司持有之母公司庫藏股股數（單位：股） | 每股參考淨值")
BS_2855 = ("2855 | 統一證 | 378,904,715 | 16,319,984 | 395,224,699 | 336,624,016 | 8,568,912 | 345,192,928 | 16,014,145 | -- | "
           "91,201 | 27,897,118 | 4,030,139 | -- | 48,032,603 | -- | -- | 1,999,168 | 50,031,771 | 0 | 0 | 0 | 29.99")


def test_income_statement_general_and_bank():
    html = _tbl(IS_BANK, IS_2801) + _tbl(IS_GEN, IS_1301)
    d = market.parse_mops_fs(html, "is")
    t = d["1301"]
    assert t["rev"] == 89239090 and t["cogs"] == 81703844 and t["gp"] == 7535246
    assert t["op"] == 1577868 and t["pti"] == 14235821 and t["ni"] == 13920632 and t["nip"] == 13920632
    assert t["eps"] == 2.19
    b = d["2801"]
    assert b["rev"] == 15221502 + 10607584              # 銀行：利息淨收益＋利息以外淨損益
    assert "gp" not in b and b["pti"] == 13113055 and b["ni"] == 11314353 and b["eps"] == 0.94


def test_balance_sheet_general_and_securities():
    d = market.parse_mops_fs(_tbl(BS_GEN, BS_1301) + _tbl(BS_SEC, BS_2855), "bs")
    a = d["1301"]
    assert (a["ca"], a["ta"], a["cl"], a["tl"]) == (324650972, 780961318, 107764931, 206699163)
    assert a["eqp"] == 574262155 and a["eq"] == 574262155 and a["cap"] == 63657408 and a["bvps"] == 90.21
    assert d["2855"]["eqp"] == 48032603                 # 證券格式欄名少一個「之」


def test_unknown_table_skipped():
    assert market.parse_mops_fs("<table><tr><th>代號</th></tr></table>", "is") == {}


def test_update_fs_and_load_single_quarter(monkeypatch, tmp_path):
    """回補：每部件一請求、只增不減；載入：損益相減成單季、資產負債取季底值。"""
    from arm import clock
    from arm.lab import store, v3data
    from datetime import date
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(clock, "today_tw", lambda: date(2026, 1, 10))
    monkeypatch.setattr(v3data, "_quarters_due", lambda: [(2025, 1), (2025, 2)])
    cum = {(2025, 1): {"rev": 100.0, "gp": 30.0, "nip": 10.0, "eps": 1.0},
           (2025, 2): {"rev": 250.0, "gp": 80.0, "nip": 25.0, "eps": 2.5}}
    calls = []

    def fake(kind, mkt, y, q, timeout=60):
        calls.append((kind, mkt, y, q))
        base = {f"{1000 + k}": {"ta": 1.0} for k in range(250)}
        if kind == "is":
            base = {f"{1000 + k}": dict(cum[(y, q)]) for k in range(250)}
        if kind == "bs":
            base["1000"] = {"ta": 900.0 + q, "eqp": 400.0 + q}
        return base
    monkeypatch.setattr(v3data.market, "mops_fs", fake)
    st = v3data.update_fs(budget_s=60, workers=2)
    assert st["req"] == 8 and st["ok"] == 8 and len(calls) == 8
    assert v3data.update_fs(budget_s=60)["req"] == 0          # 都有了就不再請求
    fs = v3data.load_fs()["1000"]
    assert fs["2025-03-31"]["rev"] == 100 and fs["2025-06-30"]["rev"] == 150    # 單季＝累計相減
    assert fs["2025-06-30"]["eps"] == 1.5 and fs["2025-06-30"]["eqp"] == 402.0


def test_fs_todo_refetch_window(monkeypatch, tmp_path):
    """法定期限後 14～45 天補抓一次晚報公司；抓過就不再抓。"""
    from arm.lab import store, v3data
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(v3data, "_quarters_due", lambda: [(2026, 2)])
    full = {p: {"1": {}} for p in v3data.FS_PARTS}
    store.write("fsq", "2026Q2", {**full, "at": {p: "2026-08-15" for p in v3data.FS_PARTS}})
    assert v3data._fs_todo("2026-08-20") == []                 # 期限（8/14）後 6 天：不補抓
    assert len(v3data._fs_todo("2026-09-01")) == 4             # 第 18 天：補抓一次
    store.write("fsq", "2026Q2", {**full, "at": {p: "2026-09-01" for p in v3data.FS_PARTS}})
    assert v3data._fs_todo("2026-09-10") == []                 # 補抓過了
    assert v3data._fs_todo("2026-10-10") == []                 # 過了 45 天
