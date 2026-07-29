"""ETF 每日持股：合併鐵則、加減碼判定、當日貢獻歸因、儀表板展開明細渲染。

（2026-07-29 使用者需求：ETF 尤其是主動式 ETF 可以拉開，看持股加減碼與當天影響漲跌的比例。）
"""
from arm import etfholdings as eh
from arm import fund_dashboard as fd
from arm.connectors.issuers import pcf


def _h(sid, name, shares, weight):
    return {"stock_id": sid, "name": name, "shares": shares, "weight": weight}


DAY1 = {"date": "2026-07-27", "src": "test",
        "holdings": [_h("2330", "台積電", 1000, 20.0), _h("2317", "鴻海", 500, 10.0)]}
DAY2 = {"date": "2026-07-28", "src": "test",
        "holdings": [_h("2330", "台積電", 1200, 22.0), _h("2454", "聯發科", 300, 8.0)]}
QUOTES = {"2330": {"close": 110.0, "change": 10.0},      # +10%
          "2454": {"close": 95.0, "change": -5.0}}       # -5%


# ── 合併鐵則 ─────────────────────────────────────────────────────

def test_merge_promotes_prev_only_when_date_advances():
    """揭露日推進才把舊持股降級為 prev。"""
    m = eh.merge_one(DAY1, DAY2)
    assert m["date"] == "2026-07-28" and m["prev_date"] == "2026-07-27"
    assert m["prev"]["2330"]["shares"] == 1000


def test_merge_same_day_refetch_keeps_prev():
    """同一揭露日重抓不可把 prev 洗成今天自己——否則 Δ 全變 0、看起來像「都沒異動」。"""
    m1 = eh.merge_one(DAY1, DAY2)
    m2 = eh.merge_one(m1, dict(DAY2))                     # 同日再抓一次
    assert m2["prev"]["2330"]["shares"] == 1000           # 仍是 7/27 的股數
    assert m2["prev_date"] == "2026-07-27"


def test_merge_empty_never_wipes():
    """本次抓不到＝原封保留既有揭露（絕不洗空，同 etf_watch／macro_chips 的鐵則）。"""
    assert eh.merge_one(DAY1, None) == DAY1
    assert eh.merge_one(DAY1, {"date": "x", "holdings": []}) == DAY1
    doc = eh.merge({"etfs": {"00991A": DAY1}}, {})
    assert doc["etfs"]["00991A"] == DAY1


# ── 加減碼與當日貢獻 ─────────────────────────────────────────────

def test_contributions_delta_and_attribution():
    merged = eh.merge_one(DAY1, DAY2)
    d = eh.contributions(merged, QUOTES)
    by = {r["stock_id"]: r for r in d["rows"]}
    # 台積電：1000→1200＝加碼 200 股、權重 +2.0；貢獻＝22% × 10% ÷ 100 ＝ 2.2pp
    assert by["2330"]["d_shares"] == 200 and by["2330"]["d_weight"] == 2.0
    assert by["2330"]["chg_pct"] == 10.0 and by["2330"]["contrib"] == 2.2
    # 聯發科：前一揭露日沒有 → 新進，Δ 股數不可硬編 0
    assert by["2454"]["is_new"] is True and by["2454"]["d_shares"] is None
    assert by["2454"]["contrib"] == -0.4                  # 8% × -5% ÷ 100
    assert d["total_contrib"] == 1.8
    # 鴻海：今日已不在持股 → 列入「已出清」
    assert [x["stock_id"] for x in d["dropped"]] == ["2317"]


def test_contributions_skip_unpriced_holdings():
    """沒有報價的持股仍列出但不計入合計——寧可少算，不憑空補值。"""
    d = eh.contributions(eh.merge_one(DAY1, DAY2), {"2330": {"close": 110.0, "change": 10.0}})
    by = {r["stock_id"]: r for r in d["rows"]}
    assert by["2454"]["contrib"] is None
    assert d["total_contrib"] == 2.2 and d["covered_weight"] == 22.0


def test_annotate_never_wipes_detail_without_quotes():
    doc = {"etfs": {"X": {**eh.merge_one(DAY1, DAY2)}}}
    eh.annotate(doc, QUOTES)
    keep = doc["etfs"]["X"]["detail"]
    eh.annotate(doc, {})                                  # 報價整段不可得
    assert doc["etfs"]["X"]["detail"] == keep


# ── 渲染 ─────────────────────────────────────────────────────────

def test_dashboard_detail_renders_delta_and_contribution():
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
    html = fd._holdings_detail("00991A", d)
    assert "持股變化與當日貢獻" in html
    assert "加碼 +200" in html and "新進" in html and "已出清" in html
    assert "+2.20pp" in html                              # 貢獻以百分點標示，不與 % 漲跌混淆
    assert "不會完全相等" in html                          # 殘差誠實揭露、不硬湊


def test_dashboard_detail_absent_when_no_data():
    assert fd._holdings_detail("00991A", None) == ""


# ── PCF 通用解析 ─────────────────────────────────────────────────

def test_pcf_parse_json_finds_holdings_anywhere():
    raw = (b'{"ok":1,"data":{"pcf":[{"stockNo":"2330","stockName":"\xe5\x8f\xb0",'
           b'"shares":"1,000","weight":"20.5"},{"stockNo":"2317","shares":"500","weight":"10"}]}}')
    rows = pcf.parse_json(raw)
    assert [r["stock_id"] for r in rows] == ["2330", "2317"]
    assert rows[0]["shares"] == 1000 and rows[0]["weight"] == 20.5


def test_pcf_parse_html_table_without_recognisable_header():
    raw = ("<table><tr><th>序</th><th>代號</th><th>名稱</th><th>股數</th><th>比重</th></tr>"
           "<tr><td>1</td><td>2330</td><td>台積電</td><td>1,234,000</td><td>22.5</td></tr>"
           "</table>").encode()
    rows = pcf.parse_html(raw)
    assert rows and rows[0]["stock_id"] == "2330" and rows[0]["shares"] == 1234000
    assert rows[0]["weight"] == 22.5


def test_pcf_ignores_non_stock_rows():
    """現金／期貨等非個股列不可被當成持股（代號需為台股 4 碼格式）。"""
    raw = b'[{"code":"CASH","weight":"3.2"},{"code":"2330","weight":"20"}]'
    assert [r["stock_id"] for r in pcf.parse_json(raw)] == ["2330"]


# ── 假陽性防呆（2026-07-29 首輪 CI 實際踩到） ──────────────────────

def _rows(n, weight=1.0, prefix="23"):
    return [{"stock_id": f"{prefix}{i:02d}", "name": f"股{i}", "shares": 1000,
             "weight": weight} for i in range(n)]


def test_plausible_rejects_etf_link_list():
    """證交所 ETFortune SPA 外殼的「其他 ETF 推薦連結」被刮成假持股：
    3 檔、權重股數全 None、且全部是 0 開頭的 ETF 代碼 —— 三道驗證都該擋下。"""
    junk = [{"stock_id": "0050", "name": "元大台灣50", "shares": None, "weight": None},
            {"stock_id": "0056", "name": "元大高股息", "shares": None, "weight": None},
            {"stock_id": "0052", "name": "富邦科技", "shares": None, "weight": None}]
    assert pcf.is_plausible(junk) is False


def test_plausible_rejects_quantityless_list():
    """檔數夠但整份沒有權重／股數 → 算不出貢獻，本來就不能用。"""
    rows = [{"stock_id": f"23{i:02d}", "name": "x", "shares": None, "weight": None}
            for i in range(20)]
    assert pcf.is_plausible(rows) is False


def test_plausible_rejects_all_etf_codes():
    """整份都是 0 開頭（ETF 代碼）＝導覽／推薦清單的長相。"""
    assert pcf.is_plausible(_rows(20, prefix="00")) is False


def test_plausible_accepts_real_holdings():
    assert pcf.is_plausible(_rows(20)) is True
    # 組合型：多數為個股、少數持有其他 ETF → 不可誤殺
    mixed = _rows(18) + [{"stock_id": "0050", "name": "元大台灣50", "shares": 1, "weight": 1.0}]
    assert pcf.is_plausible(mixed) is True


def test_api_hints_extracts_xhr_endpoints_from_spa_shell():
    """SPA 外殼時，探針要把疑似資料端點撈進 CI 日誌，一輪就能收斂（不是一輪換一個猜測）。"""
    html = (b'<html><script src="/rsrc/main.js"></script>'
            b'<script>var u="/api/etf/pcf/00991A.json";fetch("/rwd/zh/ETFortune/holdings")'
            b';var img="/img/logo.png";</script></html>')
    hints = pcf._api_hints(html)
    assert "/api/etf/pcf/00991A.json" in hints
    assert "/rwd/zh/ETFortune/holdings" in hints
    assert not any(h.endswith((".js", ".png")) for h in hints)


# ── 內嵌 JSON 解析（第 2 輪 CI：元大回 1MB HTML，資料在 script 裡不是 <table>） ──

def test_parse_embedded_json_from_script_state():
    html = ('<html><script>window.__S={"pcf":{"list":['
            '{"stockNo":"2330","stockName":"台積電","shares":123000,"weight":22.5},'
            '{"stockNo":"2317","stockName":"鴻海","shares":5000,"weight":5.1}]}}</script></html>').encode()
    rows = pcf.parse_embedded_json(html)
    assert [r["stock_id"] for r in rows] == ["2330", "2317"]
    assert rows[0]["shares"] == 123000 and rows[0]["weight"] == 22.5


def test_parse_embedded_json_handles_json_in_json():
    """狀態常以字串內嵌（JSON-in-JSON）→ 反跳脫版也要試一次（同 cnyesfund 的做法）。"""
    esc = (r'<html><script>var s="{\"stockNo\":\"2454\",\"weight\":8.0,\"shares\":300}";'
           r'</script></html>').encode()
    assert pcf.parse_embedded_json(esc)[0]["stock_id"] == "2454"


def test_parse_embedded_json_skips_quantityless_objects():
    """導覽／推薦連結物件沒有股數權重 → 不可當持股（同 is_plausible 的第②道）。"""
    junk = '<html><script>{"stockNo":"0050","stockName":"元大台灣50"}</script></html>'.encode()
    assert pcf.parse_embedded_json(junk) == []


def test_api_hints_word_boundary_on_api():
    """無詞界的 'api' 會匹配 c-api-tal（群益 capitalfund），讓 hint 全是導覽連結。"""
    raw = (b'<a href="https://www.capitalfund.com.tw/capital/about"></a>'
           b'<script>fetch("/api/pcf/0050")</script>')
    assert pcf._api_hints(raw) == ["/api/pcf/0050"]


def test_key_hits_distinguishes_spa_shell_from_unknown_keys():
    big_shell = b"<html>" + b"x" * 200_000 + b"</html>"
    assert "全無" in pcf._key_hits(big_shell)[0]
    big_data = b'<html>{"stockNo":"2330","weight":1}' + b"y" * 200_000 + b"</html>"
    assert "stockNo" in pcf._key_hits(big_data)[0]
    assert pcf._key_hits(b"<html>small</html>") == []      # 小頁面不列（純噪音）


# ── 第 3 輪 CI 收斂：錨點鍵名放寬 ＋ 上下文片段診斷 ──────────────────

def test_embedded_json_anchor_covers_unknown_id_key_names():
    """元大頁面 stockNo/stockId/stockCode 命中皆 0 → 代號欄叫別的名字。
    錨點須涵蓋 code/symbol/ticker/secId 等常見命名，否則平衡掃描一次都不觸發。"""
    for key in ("code", "symbol", "ticker", "secId"):
        html = (f'<html><script>var d=[{{"{key}":"2330","name":"台積電",'
                f'"shares":123000,"weight":22.5}}];</script></html>').encode()
        assert pcf.parse_embedded_json(html)[0]["stock_id"] == "2330", key


def test_key_hits_discounts_css_font_weight():
    """weight 的命中次數要扣掉 CSS 的 font-weight，否則是假訊號
    （元大實測 weight=191，其中絕大多數是樣式）。"""
    raw = (b"<style>" + b"font-weight:700;" * 50 + b"</style>" + b"z" * 150_000
           + b'<script>{"weight":1.5}</script>')
    line = pcf._key_hits(raw)[0]
    assert "'weight': 1" in line and "191" not in line


def test_key_hits_dumps_context_around_data_anchor():
    """只印次數不夠決斷——要直接看到資料附近的原始片段，才知道是表格、內嵌 JSON 還是樣板。"""
    raw = (b"<html>" + b"x" * 150_000
           + '<div class="row"><span>成分股</span><td>2330</td><td>22.5</td></div>'.encode()
           + b"</html>")
    hints = pcf._key_hits(raw)
    assert any("末次上下文" in h and "2330" in h for h in hints)


# ── 第 4 輪定案：資料全靠 XHR → 改掃 JS bundle 找 API 路徑 ─────────────

def test_bundle_api_hints_fetches_bundles_and_extracts_paths(monkeypatch):
    """SPA 的 API 路徑一定寫在 JS bundle 裡（HTML 裡只有文案）。"""
    pcf._bundle_cache.clear()
    html = (b'<html><script src="/rsrc/runtime.abc.js"></script>'
            b'<script src="/rsrc/main.def.js"></script></html>')
    js = {"https://x.tw/rsrc/runtime.abc.js": b'var a=1;',
          "https://x.tw/rsrc/main.def.js":
              b'fetch("/api/etf/pcf/"+code);var u="/api/fund/holding";var s="/img/a.png";'}

    def fake_get(url, probe):
        return js.get(url)

    monkeypatch.setattr(pcf, "_get", fake_get)
    hints = pcf._bundle_api_hints(html, "https://x.tw/tradeInfo/pcf/0050")
    assert "/api/etf/pcf/" in hints and "/api/fund/holding" in hints
    assert not any(".png" in h for h in hints)


def test_bundle_api_hints_caches_per_host(monkeypatch):
    """23 檔 ETF 逐檔重掃會對投信站發出上百個不必要請求 → 每 host 每次執行只掃一次。"""
    pcf._bundle_cache.clear()
    calls = []

    def fake_get(url, probe):
        calls.append(url)
        return b'var u="/api/pcf/x";'

    monkeypatch.setattr(pcf, "_get", fake_get)
    html = b'<html><script src="/main.a.js"></script></html>'
    pcf._bundle_api_hints(html, "https://y.tw/tradeInfo/pcf/0050")
    n = len(calls)
    pcf._bundle_api_hints(html, "https://y.tw/tradeInfo/pcf/0056")
    assert len(calls) == n                       # 第二檔不再重抓 bundle
