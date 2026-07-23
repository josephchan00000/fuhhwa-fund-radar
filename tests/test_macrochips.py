"""macrochips（總經・籌碼數據「市場溫度計」）：合併鐵則／取數／解析／儀表板渲染。"""
import json

from arm import macrochips as mc
from arm import fund_dashboard as fd


def _doc(series):
    return {"as_of": "2026-07-23 06:50", "series": series, "src": {}}


# ── 合併鐵則 ─────────────────────────────────────────────────────

def test_merge_keeps_old_when_new_empty():
    old = {"2026-07-21": 17.05, "2026-07-22": 16.64}
    assert mc._merge(old, {}) == old


def test_merge_new_overwrites_same_date_and_none_never_written():
    old = {"2026-07-22": 16.0}
    out = mc._merge(old, {"2026-07-22": 16.64, "2026-07-23": None})
    assert out == {"2026-07-22": 16.64}


def test_merge_trims_to_keep():
    old = {f"2026-01-{i:02d}": float(i) for i in range(1, 29)}
    new = {f"2026-02-{i:02d}": float(i) for i in range(1, 29)}
    out = mc._merge(old, new)
    assert len(out) == mc._KEEP
    assert max(out) == "2026-02-28"          # 留最近、汰最舊


def test_save_never_wipes_nonempty_file(tmp_path, monkeypatch):
    fp = tmp_path / "macro_chips.json"
    monkeypatch.setattr(mc, "DATA_FP", fp)
    mc.save(_doc({"vix": {"2026-07-22": 16.64}}))
    mc.save(_doc({k: {} for k in mc.ALL_KEYS}))          # 全空 doc → 不覆寫
    kept = json.loads(fp.read_text(encoding="utf-8"))
    assert kept["series"]["vix"] == {"2026-07-22": 16.64}


# ── 儀表板取數 ────────────────────────────────────────────────────

_S = _doc({"inst_total": {"2026-07-16": -431.4, "2026-07-17": -2617.2, "2026-07-20": 5.0,
                          "2026-07-21": 164.1, "2026-07-22": 319.4},
           "vix": {"2026-07-21": 17.05, "2026-07-22": 16.64}})


def test_latest_and_day_change():
    assert mc.latest(_S, "vix") == ("2026-07-22", 16.64)
    assert mc.day_change(_S, "vix") == -0.41
    assert mc.day_change(_S, "brent") is None            # 無序列 → None


def test_sum_and_change_n():
    assert mc.sum_n(_S, "inst_total", 5) == -2560.1      # 近5日累計
    assert mc.sum_n(_S, "inst_total", 6) is None         # 不足 n 筆不以偏概全
    assert mc.change_n(_S, "vix", 5) is None


def test_points_ordered():
    assert mc.points(_S, "inst_total", 3) == [5.0, 164.1, 319.4]


def test_norm_yield_handles_both_conventions():
    # ^TNX 回百分比本身（4.657）→ 原樣；回 ×10（46.57）→ ÷10。防 07-23 的 0.4657 坑。
    assert mc._norm_yield(4.657) == 4.657
    assert mc._norm_yield(46.57) == 4.657
    assert mc._norm_yield(0.46) == 0.46      # 極低但仍 <20 → 不動（不會誤除）


def test_vix_level_thresholds():
    assert mc.vix_level(12.0)[0] == "平靜"
    assert mc.vix_level(16.6)[0] == "正常"
    assert mc.vix_level(25.0)[0] == "偏高"
    assert mc.vix_level(35.0)[0] == "恐慌"
    assert mc.vix_level(None) is None


# ── 官方端點解析（離線 fixture） ──────────────────────────────────

def test_twse_margin_parse(monkeypatch):
    doc = {"stat": "OK", "tables": [
        {"data": [["融資(交易單位)", "1,000", "2,000", "10", "500,000", "480,000"],
                  ["融券(交易單位)", "3,000", "1,000", "20", "236,300", "210,900"],
                  ["融資金額(仟元)", "9,000,000", "27,900,000", "100", "587,962,000", "569,036,000"]]}]}
    monkeypatch.setattr(mc.factcheck, "_get_json", lambda url: doc)
    from datetime import date
    fin, short = mc._twse_margin(date(2026, 7, 20))
    assert fin == 5690.4            # 仟元 → 億
    assert short == 210900          # 融券餘額（張）


def test_taifex_tx_foreign_parse(monkeypatch):
    rows = [["日期", "契約", "身份別", "多方口數", "多方金額", "空方口數", "空方金額",
             "多空淨額口數", "多空淨額金額", "多方未平倉", "多方未平倉金額",
             "空方未平倉", "空方未平倉金額", "未平倉淨額口數", "未平倉淨額金額"],
            ["2026/07/21", "臺股期貨", "外資", "60000", "100", "70000", "120",
             "-10000", "-20", "90000", "500", "176189", "900", "-86189", "-400"],
            ["2026/07/21", "臺股期貨", "自營商", "1", "1", "1", "1",
             "0", "0", "1", "1", "1", "1", "0", "0"]]
    monkeypatch.setattr(mc, "_taifex_csv", lambda url, body: rows)
    from datetime import date
    out = mc._taifex_tx_foreign(date(2026, 7, 14), date(2026, 7, 22))
    assert out == {"2026-07-21": -86189.0}     # 外資列、倒數第2個整數欄＝未平倉淨額


def test_taifex_tx_foreign_skips_zero(monkeypatch):
    # 今日盤中未結算 → 外資列全 0；不可寫入（踩過：CI 於 7/23 把外資淨部位讀成 0）
    rows = [["2026/07/23", "臺股期貨", "外資", "0", "0", "0", "0",
             "0", "0", "0", "0", "0", "0", "0", "0"]]
    monkeypatch.setattr(mc, "_taifex_csv", lambda url, body: rows)
    from datetime import date
    assert mc._taifex_tx_foreign(date(2026, 7, 23), date(2026, 7, 23)) == {}


def test_taifex_pc_ratio_parse(monkeypatch):
    rows = [["日期", "賣權成交量", "買權成交量", "買賣權成交量比率%",
             "賣權未平倉量", "買權未平倉量", "買賣權未平倉量比率%"],
            ["2026/07/22", "500000", "600000", "83.33", "300000", "280000", "107.14"]]
    monkeypatch.setattr(mc, "_taifex_csv", lambda url, body: rows)
    from datetime import date
    out = mc._taifex_pc_ratio(date(2026, 7, 14), date(2026, 7, 22))
    assert out == {"2026-07-22": 107.14}


# ── 儀表板渲染 ────────────────────────────────────────────────────

def test_macro_data_view_renders_values_and_spark():
    html = fd._macro_data_view(_S)
    assert "VIX 恐慌指數" in html and "16.64" in html
    assert "三大法人買賣超" in html and "+319.4 億" in html
    assert "<svg" in html                                  # sparkline
    assert "正常" in html                                  # VIX 狀態標籤
    # 無資料指標整列不列、不留空格
    assert "布蘭特原油" not in html
    # 資料來源＝指標名稱本身的可點連結（按鈕放在名字）
    assert 'class="mdsl"' in html
    assert "finance.yahoo.com/quote/%5EVIX" in html        # 全球指標連 Yahoo
    assert "twse.com.tw/zh/trading/foreign/bfi82u.html" in html   # 台股籌碼連證交所


def test_inst_group_expandable_with_breakdown():
    doc = _doc({"inst_total": {"2026-07-21": 164.1, "2026-07-22": 319.4},
                "inst_foreign": {"2026-07-22": 173.4},
                "inst_trust": {"2026-07-22": 169.9},
                "inst_dealer": {"2026-07-22": -24.0}})
    html = fd._md_inst_group_html(doc)
    # 主列名稱＝大範圍展開鈕（好按、不誤觸連結），來源另做小「官方↗」
    assert 'class="mdtogbtn"' in html and 'data-grp="inst"' in html
    assert "官方↗" in html
    for name in ("外資及陸資", "投信", "自營商"):                      # 三分項子列
        assert name in html
    assert 'class="mdsub"' in html
    assert "+173.4 億" in html and "+169.9 億" in html and "-24.0 億" in html


def test_global_rows_have_units():
    html = fd._macro_data_view(_doc({"vix": {"2026-07-22": 16.64},
                                     "usdtwd": {"2026-07-21": 32.3, "2026-07-22": 32.4},
                                     "dxy": {"2026-07-22": 101.1}}))
    assert "32.400 元" in html and "101.10 點" in html    # 美元/台幣＝元、DXY＝點


def test_twse_inst_all_parse(monkeypatch):
    doc = {"stat": "OK", "data": [
        ["自營商(自行買賣)", "1", "2", "-3455000000"],
        ["自營商(避險)", "1", "2", "1057000000"],
        ["投信", "1", "2", "16992000000"],
        ["外資及陸資(不含外資自營商)", "1", "2", "17343000000"],
        ["合計", "1", "2", "31938000000"]]}
    monkeypatch.setattr(mc.factcheck, "_get_json", lambda url: doc)
    from datetime import date
    out = mc._twse_inst_all(date(2026, 7, 22))
    assert out["foreign"] == 173.43 and out["trust"] == 169.92
    assert out["dealer"] == -23.98 and out["total"] == 319.38


def test_macro_data_view_empty_hint():
    assert "尚無市場數據" in fd._macro_data_view(None)
    assert "尚無市場數據" in fd._macro_data_view(_doc({k: {} for k in mc.ALL_KEYS}))


def test_spark_degenerate():
    assert fd._spark([1.0]) == '<span class="na">—</span>'
    assert "<svg" in fd._spark([1.0, 1.0])                # 純平序列不當機（rng=0 防呆）
