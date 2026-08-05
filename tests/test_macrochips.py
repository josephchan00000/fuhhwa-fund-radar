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
    monkeypatch.setattr(mc, "_taifex_csv", lambda url, body, diag=None: rows)
    from datetime import date
    out = mc._taifex_tx_foreign(date(2026, 7, 14), date(2026, 7, 22), now_hour=23)
    assert out == {"2026-07-21": -86189.0}     # 外資列、倒數第2個整數欄＝未平倉淨額


def test_taifex_tx_foreign_skips_zero(monkeypatch):
    # 今日盤中未結算 → 外資列全 0；不可寫入（踩過：CI 於 7/23 把外資淨部位讀成 0）
    rows = [["2026/07/23", "臺股期貨", "外資", "0", "0", "0", "0",
             "0", "0", "0", "0", "0", "0", "0", "0"]]
    monkeypatch.setattr(mc, "_taifex_csv", lambda url, body, diag=None: rows)
    from datetime import date
    assert mc._taifex_tx_foreign(date(2026, 7, 23), date(2026, 7, 23), now_hour=23) == {}


def test_taifex_pc_ratio_parse(monkeypatch):
    rows = [["日期", "賣權成交量", "買權成交量", "買賣權成交量比率%",
             "賣權未平倉量", "買權未平倉量", "買賣權未平倉量比率%"],
            ["2026/07/22", "500000", "600000", "83.33", "300000", "280000", "107.14"]]
    monkeypatch.setattr(mc, "_taifex_csv", lambda url, body, diag=None: rows)
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
    # 每列統一：來源連結為下方小「官方↗」；名稱非粗體純文字
    assert "官方↗" in html and 'class="mdslsm"' in html
    assert 'class="mdgname"' in html
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
    out, src = mc._twse_inst_all(date(2026, 7, 22))
    assert out["foreign"] == 173.43 and out["trust"] == 169.92
    assert out["dealer"] == -23.98 and out["total"] == 319.38
    assert src == "twse:BFI82U"          # 官方可得時不得改用備援


def test_twse_inst_all_falls_back_when_official_down(monkeypatch):
    """官方 rwd 掛掉時：走備援鏈，且來源標籤要能區分官方／非官方
    （2026-08-03 使用者：「官方抓不到就抓其他來源」，但官方永遠優先）。"""
    from datetime import date
    monkeypatch.setattr(mc.factcheck, "_get_json", lambda url: None)      # rwd 不可得
    monkeypatch.setattr(mc, "_inst_from_openapi", lambda d, diag: None)   # 官方備援也不可得
    monkeypatch.setattr(mc, "_inst_from_thirdparty",
                        lambda d, diag: {"foreign": 1.0, "trust": 2.0,
                                         "dealer": 3.0, "total": 6.0})
    out, src = mc._twse_inst_all(date(2026, 7, 22))
    assert out["total"] == 6.0
    assert "非官方" in src               # 第三方值必須標示，不可冒充官方
    # 三源皆不可得 → 回 None（沿用既有序列，絕不寫入猜測值）
    monkeypatch.setattr(mc, "_inst_from_thirdparty", lambda d, diag: None)
    assert mc._twse_inst_all(date(2026, 7, 22)) == (None, "")


def test_macro_data_view_empty_hint():
    assert "尚無市場數據" in fd._macro_data_view(None)
    assert "尚無市場數據" in fd._macro_data_view(_doc({k: {} for k in mc.ALL_KEYS}))


def test_spark_degenerate():
    assert fd._spark([1.0]) == '<span class="na">—</span>'
    assert "<svg" in fd._spark([1.0, 1.0])                # 純平序列不當機（rng=0 防呆）


# ── 外資臺股期貨(TX)淨部位：口徑鎖定與版式容錯（2026-07-29 序列靜默凍結 6 天的回歸測試） ──

_TX_HEADER = ["日期", "商品名稱", "身份別", "多方交易口數", "多方契約金額", "空方交易口數",
              "空方契約金額", "多空淨額交易口數", "多空淨額契約金額", "多方未平倉口數",
              "多方未平倉契約金額", "空方未平倉口數", "空方未平倉契約金額",
              "多空淨額未平倉口數", "多空淨額未平倉契約金額"]


def _tx_row(d, prod, ident, net):
    return [d, prod, ident, "1", "2", "3", "4", "-2", "-2", "10", "20", "30", "40", net, "-5"]


def test_tx_rows_locks_to_taiex_futures_and_foreign():
    """只認「臺股期貨（大台）＋外資」：小台列、外資自營商列都不可混入。

    使用者 2026-07-29 回報數字對不上——彙整站常以「大台＋小台＋微台合計」揭露，
    舊解析只看「列中有外資」，期交所若忽略 commodityId 就會安靜讀到別的契約。"""
    rows = [_TX_HEADER,
            _tx_row("2026/07/28", "臺股期貨", "外資", "-82255"),
            _tx_row("2026/07/28", "小型臺指期貨", "外資", "9999"),
            _tx_row("2026/07/28", "電子期貨", "外資", "-279"),
            _tx_row("2026/07/27", "臺股期貨", "外資自營商", "-111")]
    assert mc._tx_rows_to_series(rows) == {"2026-07-28": -82255.0}


def test_tx_rows_carry_commodity_across_rowspan_blank():
    """商品名在官方版式是 rowspan——CSV 常只出現在該商品首列（自營商），
    其餘身份別留空。若不延續「最後見到的商品名」，外資列會被整批丟棄（回空序列）。"""
    rows = [_TX_HEADER,
            _tx_row("2026/07/28", "臺股期貨", "自營商", "-20"),
            _tx_row("2026/07/28", "", "投信", "5"),
            _tx_row("2026/07/28", "", "外資", "-82255")]
    assert mc._tx_rows_to_series(rows) == {"2026-07-28": -82255.0}


def test_tx_rows_skip_zero_sentinel():
    """0＝盤中未結算的哨兵（2026-07-23 踩過：最新值變「淨多 0 口」、走勢尾端插歸零）。"""
    rows = [_TX_HEADER, _tx_row("2026/07/29", "臺股期貨", "外資", "0")]
    assert mc._tx_rows_to_series(rows) == {}


def test_last_settled_clamps_to_settled_session():
    """期交所盤後 15:00 才有當日資料；查詢結束日帶到未結算當日是序列停更的最可疑主因。"""
    from datetime import date
    assert mc._last_settled(date(2026, 7, 29), 9) == date(2026, 7, 28)   # 盤中 → 前一日
    assert mc._last_settled(date(2026, 7, 29), 16) == date(2026, 7, 29)  # 盤後 → 當日
    assert mc._last_settled(date(2026, 7, 27), 9) == date(2026, 7, 24)   # 週一盤中 → 上週五


def test_missing_weekdays_includes_today_after_publish_hour():
    """2026-08-03 根因：舊版從 i=1 起算 → **今天永遠被排除**，盤後場次（15:40／22:05）
    從不抓當日三大法人與融資融券，當日值要等隔天早上才補，看起來像「證交所抓不到」。"""
    from datetime import date
    series = {"2026-07-31": 873.1, "2026-07-30": -495.4}
    today = date(2026, 8, 3)                      # 週一
    # 未過公布時點 → 不含今天（不對尚未公布的資料發請求，也避免誤觸第三方備援）
    assert today not in mc._missing_weekdays(series, today, now_hour=9, today_after=15)
    # 已過公布時點 → 含今天，且排在最前面（優先補當日）
    got = mc._missing_weekdays(series, today, now_hour=15, today_after=15)
    assert got[0] == today
    # 不給門檻時維持舊行為（只補歷史日），確保其他呼叫端不受影響
    assert today not in mc._missing_weekdays(series, today)
    # 已在序列中的日期不重抓
    assert date(2026, 7, 31) not in got


def test_flow_split_into_own_table_with_explicit_headers():
    """2026-08-03 使用者定案：買賣超（流量）與水準值**拆成兩張表**，「近5日」在每張表內
    只有一種意思。流量表欄頭＝當日買賣超｜近5日累計；且不再顯示「前日」值（會與當日值
    搶焦點——08/03 實例：當日 −165.2 旁的紅色「前日 +873.1」被誤讀成今天買超）。"""
    import re
    doc = _doc({"inst_total": {"2026-07-28": -1176.0, "2026-07-29": -351.4,
                               "2026-07-30": -495.4, "2026-07-31": 873.1,
                               "2026-08-03": -165.2}})
    html = fd._macro_data_view(doc)
    assert "當日買賣超" in html and "近5日累計" in html   # 流量表欄頭
    assert "法人買賣超" in html and "水準值" in html      # 兩張表的小標
    assert "資料日" in html
    row = re.search(r"三大法人買賣超.*?</tr>", html, re.S).group(0)
    assert "前日" not in row                              # 前日值已移除
    cell = re.search(r'<td class="mdchg">(.*?)</td>', row, re.S).group(1)
    assert "-1,314" in cell or "-1314" in cell            # 近5日累計＝五日相加


def test_level_row_keeps_daychange_semantics():
    """水準值列（VIX 等）維持「日變化／近5日變化」語意，不得混入流量表的欄位。"""
    import re
    html = fd._macro_data_view(_doc({"vix": {"2026-07-21": 17.05, "2026-07-22": 16.64}}))
    assert "VIX" in html and "資料日" in html
    row = re.search(r"VIX 恐慌指數.*?</tr>", html, re.S).group(0)
    assert "近5日累計" not in row and "前日" not in row      # 水準值列不掛流量欄位
    assert "-0.41" in row                                    # 真的日變化（17.05→16.64）


# ── 收盤口徑序列（sox/tsm_adr）：盤中 bar 不入檔（2026-08-05 踩坑） ──────────

def _chart_doc(ts_closes, mkt=None, end=None):
    meta = {}
    if end is not None:
        meta = {"regularMarketTime": mkt,
                "currentTradingPeriod": {"regular": {"start": end - 23400, "end": end}}}
    return {"chart": {"result": [{
        "meta": meta,
        "timestamp": [t for t, _ in ts_closes],
        "indicators": {"quote": [{"close": [c for _, c in ts_closes]}]}}]}}


class _Resp:
    def __init__(self, doc):
        self._b = json.dumps(doc).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _utc(*a):
    from datetime import datetime, timezone
    return int(datetime(*a, tzinfo=timezone.utc).timestamp())


def test_yahoo_series_close_only_drops_inprogress_bar(monkeypatch):
    """2026-08-05 實際踩坑重演：22:05 班遲到 ~2h、台北 00:14（美東 12:13 盤中）跑，
    把 8/4 盤中值以當日 bar 寫進落檔 → 晨報依「收盤優先讀落檔」整批引成收盤。
    close_only（sox/tsm_adr）：session 未收盤（regularMarketTime < regular.end）
    → 當日 bar 不入檔；一般溫度計序列（close_only=False）行為不變。"""
    doc = _chart_doc([(_utc(2026, 8, 3, 13, 30), 11000.0), (_utc(2026, 8, 4, 13, 30), 11200.0)],
                     mkt=_utc(2026, 8, 4, 16, 13), end=_utc(2026, 8, 4, 20, 0))
    monkeypatch.setattr(mc.urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(doc))
    assert mc._yahoo_series("^SOX", close_only=True) == {"2026-08-03": 11000.0}
    assert mc._yahoo_series("^SOX") == {"2026-08-03": 11000.0, "2026-08-04": 11200.0}


def test_yahoo_series_close_only_keeps_final_bar_after_close(monkeypatch):
    """已收盤（regularMarketTime ≥ regular.end）→ 當日 bar 是最終收盤，照常入檔
    ——05:08 美股收盤場次與翌晨 daily 走這條路，防呆不得關掉正常入檔能力。"""
    doc = _chart_doc([(_utc(2026, 8, 3, 13, 30), 11000.0), (_utc(2026, 8, 4, 13, 30), 11311.1)],
                     mkt=_utc(2026, 8, 4, 20, 0, 2), end=_utc(2026, 8, 4, 20, 0))
    monkeypatch.setattr(mc.urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(doc))
    assert mc._yahoo_series("^SOX", close_only=True) == {
        "2026-08-03": 11000.0, "2026-08-04": 11311.1}


def test_yahoo_series_close_only_conservative_when_meta_missing(monkeypatch):
    """meta 缺漏／格式不明 → 保守維持既有行為（保留全部 bar），不因判定不了而丟資料。"""
    doc = _chart_doc([(_utc(2026, 8, 4, 13, 30), 11200.0)])          # 無 meta
    monkeypatch.setattr(mc.urllib.request, "urlopen",
                        lambda req, timeout=0: _Resp(doc))
    assert mc._yahoo_series("^SOX", close_only=True) == {"2026-08-04": 11200.0}


def test_drop_open_bar_noop_before_open():
    """盤前時段：regular.end 指向尚未開盤的 session，序列裡沒有那天的 bar → 無作用。
    （15:40 台北班＝美東 03:40 盤前走到這條——既有三班的行為不因 close_only 而變。）"""
    out = {"2026-08-03": 11000.0}
    res = {"meta": {"regularMarketTime": _utc(2026, 8, 3, 20, 0, 2),
                    "currentTradingPeriod": {"regular": {"end": _utc(2026, 8, 4, 20, 0)}}}}
    assert mc._drop_open_bar(res, dict(out)) == out
