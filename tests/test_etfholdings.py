"""ETF 每日持股：合併鐵則、加減碼判定、當日貢獻歸因、儀表板展開明細渲染。

（2026-07-29 使用者需求：ETF 尤其是主動式 ETF 可以拉開，看持股加減碼與當天影響漲跌的比例。）
"""
import importlib.util
import json
from pathlib import Path

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
    """報價整段不可得 → 沿用上一班的報價日與各列數值（2026-10-21 起：同一報價日才沿用）。"""
    doc = {"etfs": {"X": {**eh.merge_one(DAY1, DAY2)}}}
    eh.annotate(doc, QUOTES, pd="2026-07-28")
    keep = doc["etfs"]["X"]["detail"]
    eh.annotate(doc, {})                                  # 報價整段不可得
    assert doc["etfs"]["X"]["detail"] == keep
    assert keep["pd"] == "2026-07-28" and keep["total_contrib"] == 1.8


# ── 渲染 ─────────────────────────────────────────────────────────

def test_dashboard_payload_carries_moves_and_holdings():
    """ETF 詳情（2026-07-30 改版）：內容由前端依內嵌資料渲染，故渲染測試改測 payload。"""
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES, pd="2026-07-28")
    pl = fd._eh_payload(d, "測試 ETF")
    kinds = {m[4] for m in pl["mv"]}
    assert {"add", "new", "out"} <= kinds                 # 加碼／新增／出清都在異動清單
    assert pl["tc"] == d["total_contrib"] and pl["nm"] == "測試 ETF"
    assert len(pl["al"]) == len(d["all"])                 # 完整持股（分頁明細）全帶出
    assert "不會完全相等" in fd._JS                        # 殘差誠實揭露、不硬湊


def test_dashboard_detail_absent_when_no_data():
    assert fd._eh_payload(None) is None
    assert fd._etf_detail_view(None, None) == ""
    assert fd._etf_detail_view({"items": [{"code": "0050"}]}, None) == ""


def test_dashboard_detail_view_skeleton():
    """2026-07-31 改版：比照基金詳情——工具列（搜尋＋分類 chips＋全部展開／收合）＋
    每檔一張可收合 `<details class="etfd">` 卡；卡片內容延遲渲染（初始為空）。"""
    doc = {"etfs": {"0050": {**eh.merge_one(DAY1, DAY2), "detail": None}}}
    doc["etfs"]["0050"]["detail"] = eh.contributions(doc["etfs"]["0050"], QUOTES)
    html = fd._etf_detail_view(
        {"items": [{"code": "0050", "name": "元大台灣50", "kind": "passive"}]}, doc)
    for anchor in ('id="etf-detail"', 'id="esearch"', 'id="eexp"', 'id="ecol"',
                   'class="eg on"', 'details class="etfd"', 'data-group="passive"',
                   'class="etfd-body"'):
        assert anchor in html, anchor
    assert 'data-name="0050 元大台灣50"' in html          # 搜尋比對代碼或名稱
    assert "揭露" in html and "異動" in html               # summary 帶揭露日與異動筆數
    assert '<div class="etfd-body"></div>' in html        # 內容延遲渲染
    assert "</script>" not in html.split("window.__EH=")[1].split(";</script>")[0]
    # 三段內容在前端建出來（骨架在 JS 的 shell()）
    for k in ("持股異動", "完整持股明細", "搜尋代號或名稱", "上一頁"):
        assert k in fd._JS, k


def test_dashboard_embedded_json_is_parseable():
    """內嵌 JSON 內的 `</` 必須轉義（否則 HTML 解析器會提前結束 script）。"""
    entry = {**eh.merge_one(DAY1, DAY2)}
    entry["detail"] = eh.contributions(entry, QUOTES)
    html = fd._etf_detail_view({"items": [{"code": "0050", "name": "x</script>y"}]},
                               {"etfs": {"0050": entry}})
    raw = html.split("window.__EH=")[1].rsplit(";</script>", 1)[0]
    assert "<\\/" in raw
    parsed = json.loads(raw.replace("<\\/", "</"))
    assert "0050" in parsed["etfs"]


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
    pcf._bundle_cache.clear(); pcf._bundle_log.clear()
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
    # 回傳的必須是「乾淨的路徑清單」——診斷片段另存 _bundle_log，不可混進來
    # （否則日後把路徑餵進 _cands() 會炸，且片段裡本就含 .png 之類無關字串）
    assert not any(".png" in h or "診斷" in h for h in hints)
    assert any("呼叫脈絡" in x for x in pcf._bundle_log["x.tw"])


def test_bundle_api_hints_caches_per_host(monkeypatch):
    """23 檔 ETF 逐檔重掃會對投信站發出上百個不必要請求 → 每 host 每次執行只掃一次。"""
    pcf._bundle_cache.clear(); pcf._bundle_log.clear()
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


def test_bundle_scan_rejects_catch_all_html_shell(monkeypatch):
    """SPA 的 catch-all 路由會把 index.html 原封回給任何 .js 路徑——位元組數與頁面相同。
    當成 JS 掃只會得到 +0 且看不出原因（2026-07-29 第 6 輪：群益 424450B、安聯 9437B
    的「bundle」都與頁面同大小，白掃三輪）。必須辨識並在日誌講明。"""
    pcf._bundle_cache.clear(); pcf._bundle_log.clear()
    page = (b'<html><script src="/main.a.js"></script>'
            b'<script src="/main.b.js"></script></html>')
    resp = {"https://z.tw/main.a.js": page,                   # catch-all 回同一份 HTML
            "https://z.tw/main.b.js": b'x.post("/api/bridge",{svc:"pcf"});'}
    monkeypatch.setattr(pcf, "_get", lambda url, probe: resp.get(url))
    assert pcf._bundle_api_hints(page, "https://z.tw/p/0050") == ["/api/bridge"]
    log = " ".join(pcf._bundle_log["z.tw"])
    assert "catch-all" in log                                # 假 bundle 有講明
    assert "頁面 script 共 2 支" in log                       # 可用 script 清單有列出
    assert 'svc:"pcf"' in log                                # 呼叫脈絡（body 參數）有撈到


# ── 無頭瀏覽器抓取（2026-07-29：逐家逆向 6 輪後改走渲染路線） ──────────

def _browser_mod():
    """以檔案路徑載入抓取腳本——不在 scripts/ 放 __init__.py，
    以免把 scripts 變成套件、改動整個 repo 的 import 語意。"""
    fp = Path(__file__).resolve().parent.parent / "scripts" / "fetch_etf_holdings_browser.py"
    spec = importlib.util.spec_from_file_location("_etf_browser", fp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_page(responses, dom=b"<html></html>", fail=None):
    """最小 Playwright page 替身：goto/wait/content/on('response') 四件事。"""
    class Resp:
        def __init__(self, url, body):
            self.url, self._b = url, body
            self.headers = {"content-type": "application/json"}
            self.request = type("R", (), {"resource_type": "xhr"})()

        def body(self):
            return self._b

    class Page:
        def __init__(self):
            self._cb = None

        def on(self, _evt, cb):
            self._cb = cb

        def goto(self, _url, **_kw):
            if fail:
                raise RuntimeError(fail)
            for u, b in responses:
                self._cb(Resp(u, b))

        def wait_for_timeout(self, _ms):
            pass

        def content(self):
            return dom.decode()

    return Page()


def _holdings_json(n=15):
    rows = [{"stockNo": f"23{i:02d}", "stockName": f"股{i}",
             "shares": 1000 + i, "weight": round(1.0 + i / 10, 2)} for i in range(n)]
    return json.dumps({"data": {"pcf": rows}}).encode()


def test_browser_prefers_intercepted_xhr_and_reports_api_url():
    """攔到的 XHR 回應就是持股 API——順便把真正的 API URL 記進日誌，
    日後要退回純 HTTP（更省資源）直接照著補 pcf._cands() 即可。"""
    b = _browser_mod()
    page = _fake_page([("https://x.tw/js/nav.json", b'{"menu":[]}'),
                       ("https://x.tw/api/pcf?code=0050", _holdings_json())])
    rows, how, log = b._from_page(page, "https://x.tw/pcf/0050")
    assert len(rows) == 15 and how.startswith("xhr:")
    assert "/api/pcf?code=0050" in how
    assert any("可補進 pcf._cands()" in x for x in log)


def test_browser_falls_back_to_rendered_dom():
    """沒攔到可用 XHR 時，改解析渲染後的 DOM（SPA 渲染完就是普通表格）。"""
    b = _browser_mod()
    trs = "".join(f"<tr><td>23{i:02d}</td><td>股{i}</td><td>1000</td><td>1.5</td></tr>"
                  for i in range(15))
    dom = f"<table><tr><th>代號</th><th>名稱</th><th>股數</th><th>比重</th></tr>{trs}</table>"
    page = _fake_page([], dom=dom.encode())
    rows, how, _log = b._from_page(page, "https://x.tw/pcf/0050")
    assert len(rows) == 15 and how == "dom"


def test_browser_rejects_junk_via_is_plausible():
    """渲染後仍是導覽／推薦連結 → 同一道 is_plausible 擋下，不會上線錯誤明細。"""
    b = _browser_mod()
    junk = b'{"list":[{"stockNo":"0050"},{"stockNo":"0056"},{"stockNo":"0052"}]}'
    page = _fake_page([("https://x.tw/api/menu", junk)])
    rows, how, log = b._from_page(page, "https://x.tw/pcf/0050")
    assert rows == [] and how == ""
    assert any("未過：" in x for x in log)          # 並指名被哪一條規則擋


def test_browser_navigation_failure_degrades_quietly():
    b = _browser_mod()
    page = _fake_page([], fail="Timeout 45000ms exceeded")
    rows, how, log = b._from_page(page, "https://x.tw/pcf/0050")
    assert rows == [] and how == "" and any("導頁失敗" in x for x in log)


def test_implausible_reason_names_the_failing_rule():
    """只說「未通過驗證」無法決斷該放寬規則還是換來源——要指名是哪一條。"""
    assert "僅 3 檔" in pcf.implausible_reason(_rows(3))
    noqty = [{"stock_id": f"23{i:02d}", "shares": None, "weight": None} for i in range(20)]
    assert "帶權重／股數" in pcf.implausible_reason(noqty)
    assert "0 開頭" in pcf.implausible_reason(_rows(20, prefix="00"))
    assert pcf.implausible_reason(_rows(20)) == ""


def test_browser_logs_reason_and_sample_when_rejected():
    b = _browser_mod()
    junk = json.dumps({"list": [{"stockNo": f"00{i:02d}A", "name": f"基金{i}"}
                                for i in range(30)]}).encode()
    page = _fake_page([("https://x.tw/api/fundlist", junk)])
    rows, how, log = b._from_page(page, "https://x.tw/pcf/00998A")
    assert rows == [] and how == ""
    joined = " ".join(log)
    assert "/api/fundlist" in joined          # 是哪個回應
    assert "未過：" in joined                  # 被哪一條規則擋
    assert "樣本：" in joined                  # 那些列長什麼樣


def test_browser_logs_all_intercepted_urls_for_diagnosis():
    """只印「最佳那筆」時，看不到真正的持股端點就在旁邊——全部攔截網址都要列出來。
    （2026-07-29：復華只顯示 /api/warning，掩蓋了其他 8 筆回應。）"""
    b = _browser_mod()
    page = _fake_page([("https://x.tw/api/warning", b'[]'),
                       ("https://x.tw/api/etf/constituent?code=00991A", b'[]'),
                       ("https://x.tw/static/app.js", b'[]')])
    _rows_, _how, log = b._from_page(page, "https://x.tw/pcf/00991A")
    joined = " ".join(log)
    assert "攔截網址" in joined
    assert "/api/etf/constituent" in joined          # 旁邊那筆才是要找的
    assert "app.js" not in joined                    # 靜態資源不佔版面


def test_discover_finds_links_containing_the_etf_code():
    """猜 10 家的網址幾乎全錯（復華實際是 /ETF/etf_detail/ETF23 內部流水號）→
    改由列表頁自尋含該代碼的連結，投信改版也跟得上。"""
    b = _browser_mod()

    class Page:
        def goto(self, *_a, **_k):
            pass

        def wait_for_load_state(self, *_a, **_k):
            pass

        def wait_for_timeout(self, _ms):
            pass

        def eval_on_selector_all(self, *_a):
            return [["https://f.tw/ETF/etf_detail/ETF23", "主動復華未來50 00991A"],
                    ["https://f.tw/news/1", "公告"],
                    ["https://f.tw/ETF/00991A/pcf", "申購買回清單"]]

    found = b._discover(Page(), "https://f.tw/ETF/index", "00991A")
    # 排序：href 含代碼者優先（2026-07-29 起），文字含代碼者次之
    assert found == ["https://f.tw/ETF/00991A/pcf", "https://f.tw/ETF/etf_detail/ETF23"]


# ── 全球型 ETF「僅台股部位」誠實標示（00988A 首抓僅涵蓋 23.1% 權重） ────

def test_contributions_reports_sum_weight():
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
    assert d["sum_weight"] == 30.0            # 22 + 8


def test_dashboard_flags_partial_tw_only_coverage():
    """權重合計遠低於 100% 時必須標「僅台股部位」，否則 30% 的清單看起來像完整持股。
    門檻判定在前端（e.sw<60），payload 只負責把權重合計帶過去。"""
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
    assert fd._eh_payload(d)["sw"] == 30.0
    assert "僅台股部位" in fd._JS and "e.sw<60" in fd._JS


def test_discover_ranks_code_href_over_name_match():
    """命中排序：href 含代碼 > 文字含代碼 > 名稱比對；復華列表連結文字不含代碼、
    只有基金名（首輪自尋實測）——名稱比對是撿回復華的關鍵。"""
    b = _browser_mod()

    class Page:
        def goto(self, *_a, **_k):
            pass

        def wait_for_load_state(self, *_a, **_k):
            pass

        def wait_for_timeout(self, _ms):
            pass

        def eval_on_selector_all(self, *_a):
            return [["https://f.tw/ETF/etf_detail/ETF23", "主動復華未來50"],   # 名稱比對
                    ["https://f.tw/news/1", "公告"],
                    ["https://f.tw/etf/00991A", "申購買回清單 00991A"]]        # href 含代碼
    found = b._discover(Page(), "https://f.tw/ETF/index", "00991A", "主動復華未來50")
    assert found[0] == "https://f.tw/etf/00991A"
    assert "https://f.tw/ETF/etf_detail/ETF23" in found


# ── 「股數」其實是市值的誤收防呆（00929 實例）＋名稱鍵放寬 ─────────────

def test_normalize_drops_shares_proportional_to_weight():
    """shares÷weight 每列等比＝那欄是持股市值（權重×規模），不是股數
    （00929 實抓：聯詠 s=4,852,110,000，但其流通在外僅 6 億股；比值恆 1.292e9）。
    誤留會讓「加減碼(股)」顯示天文數字——判中就清 shares、保留權重。"""
    aum = 1.292e9
    rows = [{"stockId": f"23{i:02d}", "name": f"股{i}",
             "shares": int((1.0 + i / 10) * aum), "weight": round(1.0 + i / 10, 3)}
            for i in range(12)]
    import json as _j
    out = pcf.parse_json(_j.dumps({"list": rows}).encode())
    out = pcf._normalize(out)
    assert all(r["shares"] is None for r in out)          # 市值欄被清掉
    assert all(r["weight"] is not None for r in out)      # 權重保留


def test_normalize_keeps_genuine_shares():
    """真實股數與權重不等比（股價各檔不同）——不可誤殺。"""
    rows = [{"stock_id": f"23{i:02d}", "name": "x", "shares": 1000 + i * 977,
             "weight": round(1.0 + i / 7, 3)} for i in range(12)]
    out = pcf._normalize(list(rows))
    assert all(r["shares"] is not None for r in out)


def test_discover_matches_official_long_name_via_widest_key():
    """WATCHLIST 簡稱「主動復華未來50」vs 復華官網「復華台灣未來50主動式ETF」——
    只有去掉「主動」與品牌名後的最寬鍵「未來50」才配得到。"""
    b = _browser_mod()

    class Page:
        def goto(self, *_a, **_k):
            pass

        def wait_for_load_state(self, *_a, **_k):
            pass

        def wait_for_timeout(self, _ms):
            pass

        def eval_on_selector_all(self, *_a):
            return [["https://f.tw/ETF/etf_detail/ETF26", "復華台灣未來50主動式ETF基金"],
                    ["https://f.tw/news/1", "公告"]]
    found = b._discover(Page(), "https://f.tw/ETF/index", "00991A",
                        "主動復華未來50", "復華")
    assert found == ["https://f.tw/ETF/etf_detail/ETF26"]


# ── 彙整站雙源交叉驗證（2026-07-29 使用者指示：不抓官網第一手、雙重驗證） ──

def _src_rows(n=12, w0=5.0, prefix="23"):
    return [{"stock_id": f"{prefix}{i:02d}", "name": f"股{i}", "shares": 1000 + i,
             "weight": round(w0 - i * 0.3, 2)} for i in range(n)]


def test_cross_check_match_within_tolerance():
    """兩站快照時點差一天內的權重小幅差異（≤0.75pp）不應誤判為不符。"""
    pri = _src_rows()
    sec = [dict(r, weight=round((r["weight"] or 0) + 0.3, 2), shares=None) for r in pri]
    v = eh.cross_check(pri, sec)
    assert v["status"] == "match" and v["top_hit"] == 10 and v["max_dw"] <= 0.75


def test_cross_check_mismatch_on_disjoint_holdings():
    """前十大重合度太低＝兩站根本在講不同的組合 → mismatch。"""
    v = eh.cross_check(_src_rows(prefix="23"), _src_rows(prefix="45"))
    assert v["status"] == "mismatch" and v["top_hit"] == 0


def test_cross_check_mismatch_on_large_weight_gap():
    pri = _src_rows()
    sec = [dict(r, weight=round((r["weight"] or 0) + 2.0, 2)) for r in pri]   # 差 2pp
    v = eh.cross_check(pri, sec)
    assert v["status"] == "mismatch" and v["max_dw"] == 2.0


def test_cross_check_does_not_compare_shares():
    """股數口徑兩站常不同（張/股、時點）——股數天差地遠也不影響驗證結果。"""
    pri = _src_rows()
    sec = [dict(r, shares=(r["shares"] or 0) * 1000) for r in pri]
    assert eh.cross_check(pri, sec)["status"] == "match"


def test_dashboard_renders_verify_badges():
    chip = fd._eh_verify_chip({"status": "match", "weights_compared": True, "other": "moneydj",
                               "top_hit": 9, "top_n": 10, "max_dw": 0.3})
    assert chip[1] == "🟢 雙源相符"
    bad = fd._eh_verify_chip({"status": "mismatch", "other": "moneydj", "top_hit": 3,
                              "top_n": 10, "max_dw": 4.2})
    assert bad[0] == "hvbad" and bad[1] == "⚠ 兩源不符" and "4.2pp" in bad[2]
    assert fd._eh_verify_chip({"status": "single", "other": None})[1] == "單源未驗證"
    assert fd._eh_verify_chip({}) == ["", "", ""]
    assert "Tier B" in fd._JS                             # 來源誠實標示


def test_verify_flows_from_entry_to_detail():
    """verify 記在 entry、detail 由 contributions 帶出——儀表板端純渲染不重算。"""
    entry = {**eh.merge_one(DAY1, DAY2), "verify": {"status": "match", "other": "moneydj",
                                                    "top_hit": 10, "top_n": 10, "max_dw": 0.1}}
    d = eh.contributions(entry, QUOTES)
    assert d["verify"]["status"] == "match"


def test_row_from_mapping_strips_market_suffix():
    """Yahoo 等站代號帶 .TW／.TWO 市場字尾——去尾後才過台股 4 碼格式驗證。"""
    r = pcf._row_from_mapping({"symbol": "2330.TW", "name": "台積電",
                               "shares": 100, "weight": 9.9})
    assert r and r["stock_id"] == "2330"
    # 上櫃「個股」帶 .TWO（如環球晶）；5 碼 ETF 代碼（00986D 等）本就不在個股收錄範圍
    r2 = pcf._row_from_mapping({"symbol": "6488.TWO", "name": "環球晶",
                                "shares": 100, "weight": 1.0})
    assert r2 and r2["stock_id"] == "6488"


# ── 構成驗證模式（Yahoo 月度基準 vs etfinfo 每日快照——跨基準日不比權重） ──

def test_cross_check_composition_only_ignores_weight_gap():
    """weights=False：權重差再大（月度 vs 每日的時點差）只記錄不判失敗，構成重合即 match。
    首輪實測 19/21 檔因 1.2–4.2pp 權重差被誤判 mismatch——那全是基準日不同，非資料錯誤。"""
    pri = _src_rows()
    sec = [dict(r, weight=round((r["weight"] or 0) + 4.0, 2)) for r in pri]   # 差 4pp
    v = eh.cross_check(pri, sec, weights=False)
    assert v["status"] == "match" and v["weights_compared"] is False
    assert v["max_dw"] == 4.0                              # 仍記錄供 tooltip 參考


def test_cross_check_composition_still_fails_on_low_overlap():
    """構成重合過低仍不算 match（上層轉 weak——副源過舊、未能驗證，非紅色警報）。"""
    v = eh.cross_check(_src_rows(prefix="23"), _src_rows(prefix="45"), weights=False)
    assert v["status"] == "mismatch"


def test_dashboard_composition_and_weak_badges():
    comp = fd._eh_verify_chip({"status": "match", "weights_compared": False, "other": "yahoo",
                               "top_hit": 9, "top_n": 10, "max_dw": 3.8})
    assert comp[1] == "🟢 構成相符" and "月度基準" in comp[2]   # 不冒稱權重也相符
    weak = fd._eh_verify_chip({"status": "weak", "other": "yahoo", "top_hit": 3, "top_n": 10})
    assert weak[1] == "副源過舊・未能驗證" and "非主來源錯誤" in weak[2]


# ── 本家兩檔走復華官網 assetsExcel（曾誤標「不支援」——限制在 schema，不在資料） ──

def _fh_mod():
    fp = Path(__file__).resolve().parent.parent / "scripts" / "fetch_etf_holdings.py"
    spec = importlib.util.spec_from_file_location("_etf_fetch", fp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fhtrust_source_maps_foreign_tickers(monkeypatch):
    """00998A/00986D 由 products.json fund_id（ETF24/25）走 fhtrust assetsExcel——
    外股 ticker（'JPM US'）直接當鍵，不套台股 4 碼驗證（改驗 ≥5 檔且過半帶權重）。"""
    m = _fh_mod()
    from arm.connectors import fhtrust as fh
    monkeypatch.setattr(fh, "fetch_holdings", lambda fid, iso: {"holdings": [
        {"stock_id": f"T{i} US", "stock_name": f"Bank{i}", "kind": "equity",
         "shares": 1000 + i, "weight": 5.0 - i * 0.2} for i in range(8)]})
    rows, asof, _self, log = m._from_fhtrust("00998A")
    assert len(rows) == 8 and rows[0]["stock_id"] == "T0 US"
    assert "fhtrust ✓" in log


def test_etfinfo_bond_etf_with_few_holdings_passes(monkeypatch):
    """00987D 美國公債 ETF 只持有 3 檔：2026-08 掛牌以來被 10 檔門檻擋掉、詳情區沒有它。
    債券 ETF（追蹤清單分類含「債」）放寬到 1 檔；股票 ETF 照舊 10 檔，失敗時日誌帶樣本列。"""
    m = _fh_mod()
    three = [{"code": f"US91282C{i}", "name": f"T {4 + i} 08/15/2035", "weight": 30.0 - i,
              "shares": 1000000 * (i + 1)} for i in range(3)]
    from arm.connectors import etfinfo as ei
    monkeypatch.setattr(ei, "fetch_etf", lambda code, cache_ttl=600: {
        "holdings": {"stocks": three, "snapshotDate": "2026-10-20"}})
    rows, asof, log = m._from_etfinfo("00987D")
    assert len(rows) == 3 and asof == "2026-10-20"
    assert "債券 ETF" in log and "US91282C0" in log
    rows, asof, log = m._from_etfinfo("0050")                  # 股票 ETF：3 檔不像持股清單
    assert rows == [] and asof is None
    assert "門檻 10" in log and "US91282C0" in log              # 擋下時看得到是哪幾列


def test_fhtrust_source_skips_unmapped_codes():
    """products.json 沒對映的檔（一般上市 ETF）回空——不會誤打復華官網。"""
    m = _fh_mod()
    assert m._from_fhtrust("0050") == ([], None, False, "")


def test_foreign_delta_and_render_without_tw_quotes():
    """外股鍵的 Δ 加減碼照常成立；無台股報價 → 貢獻誠實顯示 —（不憑空補值）。"""
    r1 = [{"stock_id": "JPM US", "name": "JPMorgan", "shares": 12000, "weight": 8.5},
          {"stock_id": "C US", "name": "Citi", "shares": 15000, "weight": 6.2}]
    r2 = [dict(r1[0], shares=14000, weight=9.0), dict(r1[1])]
    merged = eh.merge_one({"date": "d1", "src": "fhtrust", "holdings": r1},
                          {"date": "d2", "src": "fhtrust", "holdings": r2})
    d = eh.contributions(merged, {})
    by = {r["stock_id"]: r for r in d["rows"]}
    assert by["JPM US"]["d_shares"] == 2000 and by["JPM US"]["contrib"] is None
    mv = {m[0]: m for m in fd._eh_payload(d)["mv"]}
    assert mv["JPM US"][2] == 2000 and mv["JPM US"][4] == "add" and mv["JPM US"][3] is None


def test_fhtrust_source_excludes_hedge_futures(monkeypatch):
    """期貨避險/轉倉列不算持股變化（舊管線 arm/pipeline.py 同一慣例：diff 前先剔除）。"""
    m = _fh_mod()
    from arm.connectors import fhtrust as fh
    monkeypatch.setattr(fh, "fetch_holdings", lambda fid, iso: {"holdings": (
        [{"stock_id": f"23{i:02d}", "stock_name": f"股{i}", "kind": "equity",
          "shares": 1000, "weight": 5.0} for i in range(6)]
        + [{"stock_id": "TXF", "stock_name": "臺股期貨避險", "kind": "future",
            "shares": -20, "weight": None}])})
    rows, _asof, _self, _log = m._from_fhtrust("00991A")
    assert len(rows) == 6 and all(r["stock_id"] != "TXF" for r in rows)


def test_merge_rejects_date_regression():
    """換來源時新來源可能給較舊的快照（fhtrust T-1 vs 稍早 etfinfo 當日）——
    不可把較新的快照降級成 prev，否則出現「揭露日 07-28（對比 07-29）」倒轉比較
    （2026-07-30 實踩：本家三檔上線後 prev_date > date）。舊快照直接丟棄、保留較新者。"""
    newer = {"date": "2026-07-29", "src": "etfinfo", "holdings": DAY2["holdings"]}
    older = {"date": "2026-07-28", "src": "fhtrust", "holdings": DAY1["holdings"]}
    assert eh.merge_one(newer, older) == newer


# ── 異動清單／完整持股（ETF 詳情三段版面；2026-07-30 使用者需求） ──────────

def _entry_moves():
    return {"date": "2026-07-30", "prev_date": "2026-07-29",
            "holdings": [{"stock_id": "2330", "name": "台積電", "shares": 1200, "weight": 30.0},
                         {"stock_id": "1303", "name": "南亞", "shares": 500, "weight": 10.0},
                         {"stock_id": "3653", "name": "健策", "shares": 800, "weight": 8.0},
                         {"stock_id": "2454", "name": "聯發科", "shares": 100, "weight": 5.0}],
            "prev": {"2330": {"shares": 1000, "weight": 28.0},
                     "1303": {"shares": 900, "weight": 14.0},
                     "2454": {"shares": 100, "weight": 5.0},
                     "6415": {"shares": 300, "weight": 3.0}}}


_Q = {"2330": {"close": 1000.0, "change": 10.0},
      "1303": {"close": 50.0, "change": -1.0},
      "3653": {"close": 200.0, "change": 2.0},
      "2454": {"close": 1500.0, "change": 0.0},
      "6415": {"close": 400.0, "change": -4.0}}
_IND = {"2330": "半導體業", "1303": "塑膠工業", "3653": "電子零組件業", "2454": "半導體業"}


def test_moves_分類加碼減碼新增出清():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    kinds = {m["stock_id"]: m["kind"] for m in d["moves"]}
    assert kinds["2330"] == "add"      # 1000 → 1200
    assert kinds["1303"] == "cut"      # 900 → 500
    assert kinds["3653"] == "new"      # prev 沒有
    assert kinds["6415"] == "out"      # 今日沒有
    assert "2454" not in kinds         # 股數沒動 → 不算異動


def test_moves_新增檔異動量為整個部位():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    m = [x for x in d["moves"] if x["stock_id"] == "3653"][0]
    assert m["m_shares"] == 800                    # 不是 None，是全額買進
    assert m["amount"] == 800 * 200


def test_moves_出清檔為負值():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    m = [x for x in d["moves"] if x["stock_id"] == "6415"][0]
    assert m["m_shares"] == -300
    assert m["amount"] == -300 * 400


def test_moves_金額與張數():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    m = [x for x in d["moves"] if x["stock_id"] == "2330"][0]
    assert m["amount"] == 200 * 1000               # Δ股數 × 收盤
    assert m["lots"] == 0.2                        # 200 股 ＝ 0.2 張


def test_moves_依金額絕對值排序():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    amts = [abs(m["amount"]) for m in d["moves"]]
    assert amts == sorted(amts, reverse=True)
    assert d["amount_basis"] == "amount"


def test_moves_無報價時面積依據退回股數():
    d = eh.contributions(_entry_moves(), None, _IND)
    assert d["amount_basis"] == "shares"
    assert all(m["amount"] is None for m in d["moves"])
    shs = [abs(m["m_shares"]) for m in d["moves"]]
    assert shs == sorted(shs, reverse=True)


def test_moves_帶產業別供方塊圖分組():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    assert {m["stock_id"]: m["industry"] for m in d["moves"]}["2330"] == "半導體業"
    # 沒有產業對照時為 None（渲染端歸「未分類」，不當成錯誤）
    d2 = eh.contributions(_entry_moves(), _Q, None)
    assert all(m["industry"] is None for m in d2["moves"])


def test_moves_上限與其餘合計():
    hold = [{"stock_id": f"{1000 + i}", "name": f"s{i}", "shares": 100 + i, "weight": 1.0}
            for i in range(50)]
    prev = {f"{1000 + i}": {"shares": 100, "weight": 1.0} for i in range(50)}
    d = eh.contributions({"date": "d", "holdings": hold, "prev": prev}, None)
    assert d["moves_n"] == 49                      # i=0 股數沒動
    assert len(d["moves"]) == 40                   # 清單上限
    assert d["moves_rest_n"] == 9


def test_all_為全部持股且依權重排序():
    d = eh.contributions(_entry_moves(), _Q, _IND)
    assert len(d["all"]) == 4                      # rows 只留貢獻前 N，all 要全部
    ws = [r["weight"] for r in d["all"]]
    assert ws == sorted(ws, reverse=True)
    r = d["all"][0]
    assert r["stock_id"] == "2330" and r["close"] == 1000.0 and r["industry"] == "半導體業"


def test_all_收盤價缺報價時為None不憑空補():
    d = eh.contributions(_entry_moves(), {}, _IND)
    assert all(r["close"] is None for r in d["all"])
    assert all(r["contrib"] is None for r in d["all"])


def test_首次揭露無prev時沒有異動():
    e = {"date": "2026-07-30", "holdings": _entry_moves()["holdings"], "prev": {}}
    d = eh.contributions(e, _Q, _IND)
    assert d["moves"] == [] and d["moves_n"] == 0


# ── 產業分層方塊圖（_eh_treemap；座標由 arm/treemap 算好、前端純渲染） ─────────

def _mv(sid, ind, amt, sh=None, kind="add"):
    return {"stock_id": sid, "name": sid, "industry": ind, "kind": kind,
            "amount": amt, "m_shares": sh if sh is not None else (amt or 0) // 100}


def _tm(moves, basis="amount"):
    """取方塊清單（_eh_treemap 回傳 {"blocks","hidden"}）。"""
    return fd._eh_treemap(moves, basis)["blocks"]


def _readable(t, th):
    """該格放得下完整資料嗎（代碼＋簡稱＋金額；堆疊版或寬版任一）。"""
    return fd._tm_fits(t["w"] / 100 * fd._TM_W_REF, t["h"] / 100 * th)


def test_treemap_is_flat_no_industry_grouping():
    """2026-07-30 使用者定案：不分產業（對照抓不齊，分層的資訊價值輸給版面代價）。
    產業名仍留在每格資料裡供 tooltip 用。"""
    tm = _tm([_mv("2330", "半導體業", 350_000_000),
              _mv("1303", "塑膠工業", -860_000_000, kind="cut"),
              _mv("2368", None, -520_000_000, kind="cut")])
    assert len(tm) == 3
    assert all("it" not in t and "g" not in t for t in tm)      # 不再有群組層
    by = {t["s"]: t for t in tm}
    assert by["2330"]["ind"] == "半導體業" and by["2368"]["ind"] is None
    assert by["1303"]["k"] == "cut" and by["2330"]["k"] == "add"
    for t in tm:                                                # 座標仍在畫布內
        assert 0 <= t["x"] and 0 <= t["y"] and t["x"] + t["w"] <= 100.01 and t["y"] + t["h"] <= 100.01


def test_treemap_area_follows_amount_not_shares():
    """面積依金額（不被股數帶偏），但**壓縮過**：面積 ∝ |金額|^0.5——排序與相對大小保留，
    極端值被壓平，否則單檔佔六成的日子（0050 的台積電）會把其餘擠成放不下標籤的細條。
    精確數字沒有損失（每格都印金額），圖註寫明口徑（`_TM_AREA_NOTE`）。"""
    tm = _tm([_mv("A", "甲", 900_000_000, sh=1), _mv("B", "乙", 100_000_000, sh=999),
              _mv("C", "丙", 100_000_000, sh=5)])
    area = {t["s"]: t["w"] * t["h"] for t in tm}
    assert area["A"] > area["B"]                                # 排序保留
    assert area["A"] < area["B"] * 9                            # 但不是 9 倍（已壓縮）
    assert fd._TM_AREA_GAMMA == 0.5 and "平方根壓縮" in fd._TM_AREA_NOTE


def test_treemap_falls_back_to_shares_without_quotes():
    tm = _tm([_mv("A", "甲", None, sh=900), _mv("B", "乙", None, sh=100),
              _mv("C", "丙", None, sh=100)], basis="shares")
    area = {t["s"]: t["w"] * t["h"] for t in tm}
    assert area["A"] > area["B"]


def test_treemap_targets_seven_blocks_plus_other():
    """基本格式＝**7 格＋其他**（2026-07-30 使用者指定）。"""
    moves = [_mv(f"{2000 + i}", "電子", (40 - i * 3) * 10_000_000) for i in range(12)]
    fig = fd._eh_treemap(moves, "amount")
    singles = [t for t in fig["blocks"] if not t.get("agg")]
    assert len(singles) == fd._ED_TM_ITEMS == 7
    assert [t for t in fig["blocks"] if t.get("agg")], "其餘要有『其他』格"


def test_treemap_every_block_can_show_its_label():
    """2026-07-30 使用者定案的判準：**畫得出標籤才值得單獨一格**——
    「如果會在網頁上圖示顯示不出來，表示沒那麼重要，那就歸類到其他」。
    反過來也要成立：佔比還行的變動不可以被排版擠成細條而顯示不完整。"""
    moves = ([_mv("2330", "半導體業", 900_000_000)]
             + [_mv(f"{3000 + i}", "電子", 3_000_000) for i in range(12)]
             + [_mv(f"{4000 + i}", "電子", 1_500_000, kind="cut") for i in range(8)])
    fig = fd._eh_treemap(moves, "amount")
    th = fig["height"]
    assert fig["blocks"]
    for t in fig["blocks"]:
        assert _readable(t, th), f"{t.get('s') or t['n']} 放不下標籤：{t['w']}%×{t['h']}%"


def test_treemap_folds_leftovers_into_other_by_direction():
    """降級者依方向併成「其他 N 檔」——顏色語意不可混（紅綠各自一格）。"""
    # 小額們「合計起來夠大」才會以併格入圖（各自太小、合計也小的話連併格都畫不出來，
    # 那就是下一個測試的情形）
    moves = ([_mv("2330", "半導體業", 900_000_000), _mv("1303", "塑膠", -800_000_000, kind="cut")]
             + [_mv(f"{3000 + i}", "電子", 30_000_000) for i in range(10)]
             + [_mv(f"{4000 + i}", "電子", 30_000_000, kind="cut") for i in range(10)])
    fig = fd._eh_treemap(moves, "amount")
    agg = [t for t in fig["blocks"] if t.get("agg")]
    assert agg, "應該要有併格"
    assert all(t["k"] in ("add", "cut") for t in agg)
    for t in agg:
        n = int(t["n"].replace("其他 ", "").replace(" 檔", ""))
        assert abs(t["a"]) == n * 30_000_000                     # 併格金額＝成員合計


def test_treemap_hidden_count_reported_when_other_block_too_small():
    """連「其他」併格自己都畫不出標籤時整格不入圖——但檔數要回報，不能悄悄消失。"""
    moves = [_mv("2330", "半導體業", 900_000_000), _mv("2317", "電子", 300_000_000),
             _mv("2454", "半導體業", 200_000_000)] + \
            [_mv(f"{5000 + i}", "電子", 300, kind="cut") for i in range(4)]
    fig = fd._eh_treemap(moves, "amount")
    assert not [t for t in fig["blocks"] if t.get("agg")]       # 併格太小 → 不入圖
    assert fig["hidden"] == 4                                   # 但誠實回報
    assert "未入圖" in fd._JS


def test_treemap_degenerate_skew_yields_no_chart():
    """異動極度集中（單檔佔 95%）時，其餘一律畫不出標籤 → 折到剩一格，
    前端「少於 3 格不畫圖」接手；檔數仍誠實回報，訊息也不能說成「沒有變化」。"""
    moves = [_mv("A", "甲", 1_000_000_000)] + [_mv(f"B{i}", "乙", 1_000_000) for i in range(5)]
    fig = fd._eh_treemap(moves, "amount")
    assert len(fig["blocks"]) < 3 and fig["hidden"] == 5
    assert all(_readable(t, fig["height"]) for t in fig["blocks"])   # 留下的仍完整


def test_treemap_caps_block_count():
    moves = [_mv(f"{2000 + i}", "甲", (60 - i) * 1_000_000) for i in range(40)]
    tm = _tm(moves)
    assert len([t for t in tm if not t.get("agg")]) <= fd._ED_TM_ITEMS


def test_treemap_height_is_shortest_that_keeps_labels():
    """圖高＝「每格都放得下完整資料」前提下**最矮**的高度：格數少就矮（不留大片空白），
    格數多才長高；折疊判定另用最大高度（先盡量留格）。"""
    one = fd._eh_treemap([_mv("A", "甲", 100_000_000)], "amount")
    many = fd._eh_treemap([_mv(f"{2000 + i}", "電子", (40 - i * 3) * 10_000_000)
                           for i in range(12)], "amount")
    assert one["height"] == fd._TM_H_MIN                      # 一格 → 最矮
    assert many["height"] > one["height"]                     # 格數多 → 才長高
    assert many["height"] <= fd._TM_H_MAX
    for fig in (one, many):
        assert all(_readable(t, fig["height"]) for t in fig["blocks"])
    assert fd._eh_treemap([], "amount")["height"] == 0


def test_treemap_empty_when_no_moves():
    assert _tm([]) == [] and fd._eh_treemap([], "amount")["hidden"] == 0
    assert _tm([_mv("A", "甲", 0, sh=0)]) == []


def test_view_backfills_legacy_detail_without_all():
    """落檔 detail 為舊 schema（無 all／moves）時就地補算，並嫁接既有報價／貢獻。"""
    entry = eh.merge_one(DAY1, DAY2)
    legacy = eh.contributions(entry, QUOTES)
    priced = {r["stock_id"]: (r["chg_pct"], r["contrib"]) for r in legacy["rows"]}
    legacy.pop("all"); legacy.pop("moves")
    doc = {"etfs": {"X": {**entry, "detail": legacy}}}
    got = eh.view(doc, "X")
    assert got["all"] and got["moves"]                      # 補算出來
    for r in got["all"]:
        if r["stock_id"] in priced:
            assert (r["chg_pct"], r["contrib"]) == priced[r["stock_id"]]
    assert got["total_contrib"] == legacy["total_contrib"]   # 合計沿用既有值


def test_view_returns_stored_detail_when_complete():
    entry = eh.merge_one(DAY1, DAY2)
    entry["detail"] = eh.contributions(entry, QUOTES)
    assert eh.view({"etfs": {"X": entry}}, "X") is entry["detail"]


def test_view_unescapes_html_entities_in_names():
    """舊落檔名稱帶 `&amp;`（復華 xlsx 解析 2026-10-21 前沒還原實體）：網頁 JS 會再跳脫一次，
    顯示成字面「M&amp;G」。讀取端還原，沒有要改的 detail 原物件回傳（不多做複製）。"""
    det = {"all": [{"stock_id": "MNG LN", "name": "M&amp;G公開有限公司", "weight": 1.9},
                   {"stock_id": "C US", "name": "花旗集團公司", "weight": 1.9}],
           "moves": [{"stock_id": "8725 JP", "name": "MS&amp;AD保險集團控股公司", "kind": "add"}],
           "rows": []}
    got = eh.view({"etfs": {"X": {"detail": det, "holdings": [{"stock_id": "C US"}]}}}, "X")
    assert [r["name"] for r in got["all"]] == ["M&G公開有限公司", "花旗集團公司"]
    assert got["moves"][0]["name"] == "MS&AD保險集團控股公司"
    assert det["all"][0]["name"] == "M&amp;G公開有限公司"          # 落檔物件不被改寫
    clean = {"all": [{"stock_id": "C US", "name": "花旗集團公司"}]}
    assert eh.view({"etfs": {"X": {"detail": clean}}}, "X") is clean
    assert eh.clean_name("JPMORGAN CHASE &amp; CO") == "JPMORGAN CHASE & CO"
    assert eh.clean_name(None) is None and eh.clean_name("台積電") == "台積電"


def test_lab_names_from_holdings_unescapes_entities():
    from arm.lab import collect
    doc = {"etfs": {"00998A": {
        "holdings": [{"stock_id": "MNG LN", "name": "M&amp;G公開有限公司"}],
        "prev": {"8725 JP": {"shares": 1, "weight": 1.0, "name": "MS&amp;AD保險集團控股公司"}}}}}
    assert collect.names_from_holdings(doc) == {"MNG LN": "M&G公開有限公司",
                                                "8725 JP": "MS&AD保險集團控股公司"}


def test_treemap_tint_scales_with_magnitude():
    """深色畫布上的雙向色階（2026-07-30 重新設計）：色相只表方向、亮度只表幅度。
    數值都是「算出來的」而非拍腦袋，所以測試守住那些算式與上限。"""
    js, css = fd._JS, fd._CSS
    # 亮度 ∝ 幅度；開 0.55 次方讓小額異動仍看得見
    assert "0.28+0.52*" in js and "Math.pow(mag/maxv,0.55)" in js
    # 色票：紅 #e6504c／綠松 #159c94（rgb 形式寫進 inline style）
    assert "'230,80,76'" in js and "'21,156,148'" in js
    assert fd._TM_UP == "#e6504c" and fd._TM_DN == "#159c94"
    # 亮度上限＝0.28+0.52＝0.80，是白字對比算出來的（紅 5.2:1／綠松 4.7:1，過 AA 正文
    # 4.5:1）——上限拉到 1.0 會掉到 3.4:1，別調。文字另加陰影再保一層。
    assert ".tmi i,.tmi em,.tmi u,.tmi s{text-shadow" in css
    # 深色畫布與圖例
    assert ".tmfig{background:#14171b" in css and fd._TM_SURFACE == "#14171b"
    # 格與格之間留「畫布色」縫，不畫線；新增／出清用內縮虛線環（亮度已被幅度佔用）
    assert "border:1.5px solid #14171b" in css
    assert ".tmi.new,.tmi.out{outline:1px dashed" in css
    assert ".tmi.add{background" not in css                # 不可再寫死每類一種底色
    assert "deep" not in js.split("paintTmap")[1][:1200]   # 深色畫布上文字一律白，不需切換
    assert ".tmg{" not in css                              # 產業群組層已移除（單層方塊圖）
    assert "wrap.hidden=!tm.length" in js                  # 有東西可畫就畫；只有全無異動才收掉
    assert "tm.length<3" not in js                         # 「少於 3 格不畫」規則已移除


def test_treemap_legend_names_both_directions():
    """圖例必須同時標出兩個方向與亮度的意義——顏色不可是唯一線索。"""
    entry = eh.merge_one(DAY1, DAY2)
    entry["detail"] = eh.contributions(entry, QUOTES)
    fd._etf_detail_view({"items": [{"code": "0050", "name": "元大台灣50"}]},
                        {"etfs": {"0050": entry}})
    # 圖例改由前端 shell() 建（卡片內容延遲渲染），色票與常數同值
    js = fd._JS
    assert "加碼／新增" in js and "減碼／出清" in js
    assert "色塊越亮＝幅度越大" in js and "虛線框＝新增或出清" in js
    assert fd._TM_UP in js and fd._TM_DN in js


def test_treemap_reports_unpriced_moves():
    """全球型 ETF 的海外持股沒有台股報價（amount 為 None）→ 算不出面積，
    不可靜靜濾掉：00990A 實測 18 檔異動只畫得出 1 格，其餘 17 檔必須在註解交代。"""
    moves = [_mv("2454", "半導體業", -182_700_000, kind="cut"),
             {"stock_id": "AMD US", "name": "AMD", "kind": "cut", "amount": None,
              "m_shares": -36000, "industry": None},
             {"stock_id": "NOW US", "name": "ServiceNow", "kind": "new", "amount": None,
              "m_shares": 258800, "industry": None}]
    fig = fd._eh_treemap(moves, "amount")
    assert [t["s"] for t in fig["blocks"]] == ["2454"]
    assert fig["unpriced"] == 2
    # 揭露文案寫在**異動表**底下，圖被收掉時仍看得到
    assert "無台股報價，無法計入方塊圖" in fd._JS
    assert "'.mvfoot'" in fd._JS


def test_treemap_omissions_are_all_accounted():
    """入圖格數＋併格成員＋未入圖＋無報價＝異動總數（帳要平，不能有檔數蒸發）。"""
    moves = ([_mv("2330", "半導體業", 900_000_000)]
             + [_mv(f"{3000 + i}", "電子", 20_000_000) for i in range(8)]
             + [_mv(f"{4000 + i}", "電子", 900_000, kind="cut") for i in range(7)])
    fig = fd._eh_treemap(moves, "amount")
    singles = [t for t in fig["blocks"] if not t.get("agg")]
    agg_n = sum(int(t["n"].replace("其他 ", "").replace(" 檔", ""))
                for t in fig["blocks"] if t.get("agg"))
    assert len(singles) + agg_n + fig["hidden"] + fig["unpriced"] == len(moves)


def test_treemap_other_blocks_sit_bottom_right_and_recede():
    """「其他」併格固定排最後 → 落在右下角，且顏色壓低不搶眼
    （2026-07-30 使用者：「既然都叫其他了就不要太明顯」）。"""
    moves = ([_mv(f"{2000 + i}", "電子", (40 - i * 3) * 10_000_000) for i in range(9)]
             + [_mv(f"{4000 + i}", "電子", 30_000_000, kind="cut") for i in range(4)])
    fig = fd._eh_treemap(moves, "amount")
    aggs = [t for t in fig["blocks"] if t.get("agg")]
    assert aggs, "應該要有『其他』格"
    # 併格一律排在清單末端（＝squarify 最後填的位置）
    assert all(t.get("agg") for t in fig["blocks"][-len(aggs):])
    last = fig["blocks"][-1]
    assert last["x"] + last["w"] > 99.9 and last["y"] + last["h"] > 99.9   # 含右下角
    for t in aggs:                                                        # 都在下半、右半
        assert t["x"] + t["w"] > 50 and t["y"] + t["h"] > 50
    # 亮度固定壓低（不隨幅度變亮）＋標籤改灰
    assert "it.agg?0.20:" in fd._JS
    assert ".tmi.agg i,.tmi.agg u{font-weight:600;color:rgba(255,255,255,.62)}" in fd._CSS


# ── 「同一份快照被標成兩天」防呆（2026-07-30 使用者抓到 00991A 假的「本次無異動」） ──

def _snap(date, shares, weights=None):
    ws = weights or [round(10 - i * 0.1, 3) for i in range(len(shares))]
    return {"date": date, "src": "fhtrust",
            "holdings": [{"stock_id": f"{2330 + i}", "name": f"s{i}",
                          "shares": sh, "weight": w}
                         for i, (sh, w) in enumerate(zip(shares, ws))]}


def test_merge_同內容不同日期視為同一次揭露():
    """復華 assetsExcel 的資料日原本取「我們請求的日期」，同一份檔案會被標成新的一天 →
    舊快照被降級成 prev、Δ 全變 0，看板出現假的「本次無異動」。內容全等就不推進日期。"""
    d1 = _snap("2026-07-28", [1000, 2000, 3000])
    m = eh.merge_one(d1, _snap("2026-07-29", [1000, 2000, 3000]))
    assert m["date"] == "2026-07-28"          # 日期不前進
    assert not m["prev"] and m["prev_date"] is None
    assert eh.contributions(m, None)["moves_n"] == 0


def test_merge_股數相同但權重不同視為新的一天():
    """權重是市值比重——不同交易日必然有變動；只有股數沒動才是真的『沒有加減碼』。"""
    d1 = _snap("2026-07-28", [1000, 2000], [10.0, 9.9])
    m = eh.merge_one(d1, _snap("2026-07-29", [1000, 2000], [10.4, 9.5]))
    assert m["date"] == "2026-07-29" and m["prev_date"] == "2026-07-28"
    assert len(m["prev"]) == 2
    det = eh.contributions(m, None)
    assert det["moves_n"] == 0                # 真的沒有加減碼
    assert all(r["d_shares"] == 0 for r in det["all"])   # 但有可比基準（不是 None）


def test_merge_清掉與今日全等的假prev():
    """既有落檔已被前述 bug 汙染（prev 是今天自己的複本）→ 合併時就地清掉，
    誠實顯示「尚無可對比的前一揭露日」，而不是假的「本次無異動」。"""
    bad = {"date": "2026-07-29", "src": "fhtrust",
           "holdings": _snap("x", [1000, 2000])["holdings"],
           "prev": {"2330": {"shares": 1000, "weight": 10.0},
                    "2331": {"shares": 2000, "weight": 9.9}},
           "prev_date": "2026-07-28"}
    m = eh.merge_one(bad, _snap("2026-07-29", [1000, 2000]))
    assert m["prev"] == {} and m["prev_date"] is None


def test_merge_真的加減碼照常推進():
    d1 = _snap("2026-07-28", [1000, 2000])
    m = eh.merge_one(d1, _snap("2026-07-29", [1200, 2000]))
    assert m["date"] == "2026-07-29" and m["prev_date"] == "2026-07-28"
    det = eh.contributions(m, None)
    assert det["moves_n"] == 1 and det["moves"][0]["m_shares"] == 200


def test_fhtrust_以檔案自報日期為資料日():
    """`fetch_holdings` 原本回傳「請求的日期」當資料日——同一份檔案換個 ymd 請求就變成
    「新的一天」。改以檔案內自報的日期為準（掃不到才回退請求日，並在 CI 日誌標明）。"""
    from arm.connectors import fhtrust
    assert fhtrust._meta_date(["資料日期", "2026/07/28"]) == "2026-07-28"
    assert fhtrust._meta_date(["資料日期：115/07/28"]) == "2026-07-28"      # 民國年
    assert fhtrust._meta_date(["本基金資產明細表 2026年7月28日"]) == "2026-07-28"
    assert fhtrust._meta_date(["基金資產淨值", "1,234,567,890"]) is None    # 金額不是日期
    assert fhtrust._meta_date([]) is None


def test_source_pick_prefers_newest_snapshot(monkeypatch):
    """主來源＝快照日最新者（2026-07-30 使用者：「不能用 etfinfo 頂著嗎」）。
    fhtrust 的日期只有「檔案自報」時才拿來比大小——沿用請求日的不可信，視為未知。
    同一天時仍讓第一手 fhtrust 勝（可與 etfinfo 做真正的權重驗證）。"""
    def pick(f_asof, f_self, e_asof):
        cands = []
        if True:
            cands.append(("fhtrust", f_asof, f_asof if f_self else "", 1))
            cands.append(("etfinfo", e_asof, e_asof or "", 0))
        cands.sort(key=lambda c: (c[2], c[3]), reverse=True)
        return cands[0][0]
    # etfinfo 較新 → etfinfo 頂著（00991A 的實況：fhtrust 回同一份舊檔）
    assert pick("2026-07-25", True, "2026-07-29") == "etfinfo"
    # fhtrust 日期不可信（沿用請求日）→ 一律讓 etfinfo 先
    assert pick("2026-07-30", False, "2026-07-29") == "etfinfo"
    # 同一天且 fhtrust 自報 → 第一手優先
    assert pick("2026-07-29", True, "2026-07-29") == "fhtrust"
    # fhtrust 較新且自報 → 第一手勝
    assert pick("2026-07-30", True, "2026-07-29") == "fhtrust"


def test_etf_table_row_is_compact_and_link_in_category_column():
    """2026-07-30 使用者：每一檔都好長 → Yahoo 連結移到「性質」欄、代碼與「詳情」同一行。
    識別欄原本堆四行（代碼／名稱／詳情鈕／Yahoo），列高近 180px，現為 71px。"""
    items = [{"code": "0056", "name": "元大高股息", "cat": "高股息", "kind": "passive"}]
    entry = eh.merge_one(DAY1, DAY2)
    entry["detail"] = eh.contributions(entry, QUOTES)
    html = fd._etf_table(items, {"etfs": {"0056": entry}})
    cat_cell = html.split("<tbody>")[1].split("</td>")[0]
    assert 'class="etcat"' in cat_cell and 'class="etyh"' in cat_cell   # 連結在性質欄
    id_cell = html.split("<tbody>")[1].split("</td>")[1]
    assert 'class="etline"' in id_cell and "詳情 ↓" in id_cell          # 代碼與詳情同一行
    assert "ehyh" not in html                                          # 舊的第四行連結已移除
    assert ".etline{display:flex" in fd._CSS


def test_moves_basis_falls_back_to_shares_when_any_unpriced():
    """全球型 ETF 的海外持股沒有台股報價 → 若仍用「金額」當面積依據，那些沒金額的會被
    靜靜濾掉（00988A 的 6 筆異動只畫得出 1 格）。**只要有一筆沒金額，整張圖改用股數**，
    保證每一筆異動都看得到（2026-07-30 使用者：海外的明明有變動但沒有顯示出來）。"""
    hold = [{"stock_id": "3665", "name": "貿聯-KY", "shares": 1200, "weight": 5.0},
            {"stock_id": "VECO US", "name": "VEECO", "shares": 800, "weight": 4.0}]
    prev = {"3665": {"shares": 1000, "weight": 4.8},
            "VECO US": {"shares": 990, "weight": 4.9}}
    q = {"3665": {"close": 200.0, "change": 2.0}}          # 只有台股有報價
    d = eh.contributions({"date": "d", "holdings": hold, "prev": prev}, q)
    assert d["amount_basis"] == "shares" and d["unpriced_n"] == 1
    assert {m["stock_id"] for m in d["moves"]} == {"3665", "VECO US"}   # 兩筆都在
    tm = fd._eh_treemap(d["moves"], d["amount_basis"])["blocks"]
    assert {t["s"] for t in tm} == {"3665", "VECO US"}                  # 圖上也都在
    # 全部有報價時才用金額
    d2 = eh.contributions({"date": "d", "holdings": hold, "prev": prev},
                          {**q, "VECO US": {"close": 50.0, "change": 1.0}})
    assert d2["amount_basis"] == "amount" and d2["unpriced_n"] == 0


def test_treemap_small_block_keeps_company_name():
    """小格寧可省金額也要留公司名（2026-07-30 使用者：有些只有代號沒有公司名）。"""
    js = fd._JS
    assert "pw>=48&&ph>=26)lab='<i>'+cd+'</i>'+(nm?'<em>'+nm+'</em>':'')" in js


def test_dropped_holding_keeps_company_name():
    """出清標的今天已不在 holdings，名稱只剩 prev 留得住——否則圖上／表上只有代號沒有
    公司名（2026-07-30 使用者回報）。補名順序：prev 存的 → 當日報價 → 其他 ETF 的持股
    名冊 → 最後才退回代號。"""
    d1 = {"date": "d1", "holdings": [
        {"stock_id": "2303", "name": "聯電", "shares": 1000, "weight": 5.0},
        {"stock_id": "3357", "name": "台星科", "shares": 500, "weight": 3.0}]}
    d2 = {"date": "d2", "holdings": [
        {"stock_id": "2303", "name": "聯電", "shares": 1000, "weight": 5.0}]}
    m = eh.merge_one(d1, d2)
    assert m["prev"]["3357"]["name"] == "台星科"          # prev 有存名稱
    det = eh.contributions(m, None)
    out = [x for x in det["moves"] if x["kind"] == "out"][0]
    assert out["stock_id"] == "3357" and out["name"] == "台星科"

    # prev 沒名稱（舊落檔）→ 依序用報價、別檔 ETF 的名冊
    m2 = {**m, "prev": {"3357": {"shares": 500, "weight": 3.0}}}   # 舊落檔的 prev 沒名稱
    def out_name(det):
        return [x for x in det["moves"] if x["kind"] == "out"][0]["name"]
    assert out_name(eh.contributions(
        m2, {"3357": {"close": 1.0, "change": 0.0, "name": "台星科"}})) == "台星科"   # 靠報價
    assert out_name(eh.contributions(m2, None, None, 12, {"3357": "台星科"})) == "台星科"  # 靠名冊
    assert out_name(eh.contributions(m2, None)) == "3357"           # 都沒有才退回代號


def test_annotate_builds_cross_etf_name_registry():
    """某檔 ETF 出清的股票往往還在別檔 ETF 的持股裡——拿來補名字最直接。"""
    doc = {"etfs": {
        "A": {"date": "d2", "holdings": [{"stock_id": "2330", "name": "台積電",
                                          "shares": 10, "weight": 9.0}],
              "prev": {"3357": {"shares": 500, "weight": 3.0}}},
        "B": {"date": "d2", "holdings": [{"stock_id": "3357", "name": "台星科",
                                          "shares": 20, "weight": 2.0}]},
    }}
    eh.annotate(doc, {})
    out = [m for m in doc["etfs"]["A"]["detail"]["moves"] if m["kind"] == "out"]
    assert out and out[0]["name"] == "台星科"


def test_treemap_label_never_prints_code_twice():
    """名稱與代號相同＝資料端沒補到名字 → 前端不要把代號印兩次。"""
    js = fd._JS
    assert "it.n&&it.n!==it.s" in js.replace(" ", "")
    assert "r[1]===r[0]?'':r[1]" in js       # 異動表同理


def test_etf_detail_cards_are_lazy_and_filterable():
    """比照基金詳情：每檔一張可收合卡、工具列可搜尋與依性質篩選、可全部展開／收合。
    內容延遲渲染——23 檔各含方塊圖＋兩張表，一次全建進 DOM 會讓頁面又大又慢。"""
    items = [{"code": "0050", "name": "元大台灣50", "kind": "passive"},
             {"code": "00991A", "name": "主動復華未來 50", "kind": "active"},
             {"code": "00986D", "name": "主動復華金融債息", "kind": "other"}]
    doc = {"etfs": {}}
    for i in items:
        e = eh.merge_one(DAY1, DAY2)
        e["detail"] = eh.contributions(e, QUOTES)
        doc["etfs"][i["code"]] = e
    html = fd._etf_detail_view({"items": items}, doc)
    assert html.count('<details class="etfd"') == 3
    for kind in ("passive", "active", "other"):
        assert f'data-group="{kind}"' in html
    assert html.count('<div class="etfd-body"></div>') == 3      # 初始都是空的
    js = fd._JS
    assert "card.open)render(card)" in js.replace(" ", "")       # 展開才渲染
    assert "box.dataset.done" in js                              # 渲染一次就不重建
    assert "classList.toggle('fhide'" in js                      # 搜尋／分類用同一套隱藏機制


def test_etf_detail_fhide_css_covers_etf_cards():
    """2026-07-31 使用者回報「這邊的按鈕都不能按」的真因：隱藏規則原本只寫 `.fund.fhide`，
    ETF 卡是 `.etfd`——分類 chips 與搜尋照樣加了 class，畫面卻毫無反應。
    另 `.eg`（ETF 分類 chip）沒併進 `.fg` 樣式，連選中狀態都看不出來；
    `#esearch` 沒併進 `#fsearch` 樣式，行動版會退回原生搜尋框（多一個放大鏡）。"""
    css = fd._CSS
    assert ".etfd.fhide" in css and ".edchip.fhide" in css
    assert ".fnit.fhide" in css                         # 2026-08-15 社群分類篩選同一套隱藏
    assert ".fg,.eg,.sg,.fexp{" in css                  # chip 樣式（.sg＝社群篩選 chips）
    assert ".fg.on,.eg.on,.sg.on{" in css               # 選中狀態
    assert ("#fsearch,.fundbar #esearch,.fundbar #ssearch,.fundbar #nsearch{"
            in css)                                     # 搜尋框樣式（含新聞列/社群列）


def test_etf_detail_code_chips():
    """2026-07-31 使用者：搜尋的地方也要有可直接點的代碼「泡泡」。
    照上方績效表分被動／主動式／其他三排；點一顆＝展開該檔並捲過去。"""
    items = [{"code": "0050", "name": "元大台灣50", "kind": "passive"},
             {"code": "00991A", "name": "主動復華未來 50", "kind": "active"},
             {"code": "00986D", "name": "主動復華金融債息", "kind": "other"}]
    doc = {"etfs": {}}
    for i in items:
        e = eh.merge_one(DAY1, DAY2)
        e["detail"] = eh.contributions(e, QUOTES)
        doc["etfs"][i["code"]] = e
    html = fd._etf_detail_view({"items": items}, doc)
    assert 'id="edpick"' in html
    assert html.count('class="edchip"') == 3
    for kind, label in (("passive", "被動"), ("active", "主動式"), ("other", "其他")):
        assert f'<div class="edprow" data-group="{kind}"><span class="edplab">{label}</span>' in html
    # 泡泡標籤去掉「主動」前綴（那排標籤已寫著主動式），但搜尋比對仍用完整名稱
    assert "<span>未來 50</span>" in html
    assert 'data-name="00991A 主動未來 50"' in html    # 搜尋比對用完整（_short 後）名稱
    js = fd._JS
    assert "#edpick .edchip" in js
    assert "syncPick" in js                              # 選中狀態＝該檔卡片是否展開


def test_etf_detail_holding_intro_is_shared_not_per_etf():
    """標的簡介共用 {代號: 簡介} 一份——同一檔股票出現在多檔 ETF，逐檔各存一份會讓
    內嵌 JSON 多出約 200KB。"""
    items = [{"code": "0050", "name": "元大台灣50", "kind": "passive"},
             {"code": "00991A", "name": "主動復華未來 50", "kind": "active"}]
    doc = {"etfs": {}}
    for i in items:
        e = eh.merge_one(DAY1, DAY2)
        e["detail"] = eh.contributions(e, QUOTES)
        doc["etfs"][i["code"]] = e
    html = fd._etf_detail_view({"items": items}, doc)
    raw = html.split("window.__EH=")[1].rsplit(";</script>", 1)[0].replace("<\\/", "</")
    data = json.loads(raw)
    assert "intro" in data and isinstance(data["intro"], dict)
    for p in data["etfs"].values():                              # 列裡不再帶簡介
        assert all(len(r) == 8 for r in p["al"])                 # 第 8 欄＝待收盤旗標（2026-10-21）
    assert "INTRO[r[0]]" in fd._JS                               # 前端依代號查
    assert 'class="introw"' in fd._JS                            # 簡介獨立整寬一列


def test_etf_subnav_matches_sections():
    """ETF 分頁二級選單＝即將登場／ETF 數據追蹤／ETF 持股詳情＆異動（2026-07-31 使用者）。"""
    import re
    html = fd._topbar([], True, "2026-07-31", "2026-07-31 08:00")
    nav = re.search(r'<nav class="tb-nav tb-nav-etf">(.*?)</nav>', html, re.S).group(1)
    # 2026-09-01 起二級選單＝分段切換 label（不再是錨點）；名稱與順序不變
    assert re.findall(r'for="(sec-[\w-]+)"', nav) == ["sec-eup", "sec-ewatch", "sec-edet"]
    assert "ETF 數據追蹤" in nav and "ETF 持股詳情" in nav


# ── 跨來源比較的假異動（2026-08-05 使用者：00986D「全部出清？加碼的也出清？」） ─────
#
# 實況重建：00986D 的主來源在 fhtrust（復華 assetsExcel）與 etfinfo（PCF 彙整）之間跳。
# 兩源的「列宇宙」不同——etfinfo 多給期貨（202609US／202609TY）、保證金（M_*）、
# 應付買回款（PFUR_*）、扣除應付證券款（DA_*）；fhtrust 只給證券／債券。
# 07-30 etfinfo 同日頂掉 fhtrust → 那 11 列被判「新增」；07-31 fhtrust 回來 →
# 同樣 11 列全被判「出清」，其中 PFUR_NTD 的前日股數是 **-14,749,392**（應付款），
# 出清 Δ ＝ 0 −(負) ＝ **正 14,749 張**，於是表上出現「加碼數字卻標出清」。

_ETFINFO_EXTRA = [                                        # etfinfo 給、fhtrust 不給的列
    {"stock_id": "202609US", "name": "美國三十年期政府公債", "shares": 85, "weight": 13.31},
    {"stock_id": "202609TY", "name": "美國十年期公債", "shares": 55, "weight": 8.54},
    {"stock_id": "M_NTD", "name": "MARGIN", "shares": 17015722, "weight": 0.75},
    {"stock_id": "DA_USD", "name": "AFTER DEDUCTING SECURITIES PURCHASES AMOUNT",
     "shares": -3209119, "weight": -4.59},
    {"stock_id": "PFUR_NTD", "name": "PAYABLES FOR UNITS REDEEMED",
     "shares": -14749392, "weight": -0.65},
]
_BONDS = [{"stock_id": f"US{i:08d}AA{i}", "name": f"BANK {i} 7 3/4 05/14/38",
           "shares": 1000000 + i, "weight": 7.0 - i * 0.1} for i in range(6)]


def test_非持股列被濾掉_現金保證金應付款期貨():
    """現金／保證金／應付款／公債期貨不是持股——任何來源都不該進 diff。"""
    kept = eh.drop_non_holdings(_BONDS + _ETFINFO_EXTRA)
    assert [r["stock_id"] for r in kept] == [b["stock_id"] for b in _BONDS]
    # 真持股不可誤殺：台股 4 碼、etfinfo 的外股（帶交易所碼、有空格）、ISIN
    for sid, nm in (("2330", "台積電"), ("TLTW US", "iShares 20+ Year Treasury Bo"),
                    ("US83368TBT43", "SOCGEN 7.367 01/10/53"), ("00878", "國泰永續高股息"),
                    ("US912810UW61", "T 5 1/8 08/15/56"), ("285A", "鎧俠"),
                    ("300476 C2", "Victory Giant Technology Huizhou Co Ltd")):
        assert not eh.is_non_holding(sid, nm), sid
    # 期貨另兩種寫法（2026-10-21）：商品碼在前、帶冒號（00987D 的超長美債期貨）
    for sid, nm in (("US202612", "美國長債期"), ("UB:2026-12:B", "超長美債"), ("TY202603", "")):
        assert eh.is_non_holding(sid, nm), sid


def test_跨來源時不判定新增出清_只比共同持股():
    """來源不同＝揭露範圍未必一致，「今天不在清單裡」分不出是真出清還是對方沒揭露。
    只比共同持股的加減碼，並在 detail 標 xsrc 誠實揭露。"""
    day1 = {"date": "2026-07-30", "src": "etfinfo",
            "holdings": _BONDS + _ETFINFO_EXTRA}
    day2 = {"date": "2026-07-31", "src": "fhtrust",
            "holdings": [dict(_BONDS[0], shares=_BONDS[0]["shares"] + 500_000)] + _BONDS[1:]}
    det = eh.contributions(eh.merge_one(day1, day2), None)
    kinds = {m["kind"] for m in det["moves"]}
    assert kinds == {"add"}                               # 沒有任何假的 new／out
    assert det["moves_n"] == 1 and det["moves"][0]["m_shares"] == 500_000
    assert det["xsrc"] == ["etfinfo", "fhtrust"]
    assert not det["dropped"]


def test_出清數字不可為正_應付款列不得被當成持股():
    """使用者原話「加碼的也出清？」——負股數的應付款列被判出清後 Δ 會變成正的。
    這種列一律不進 diff（既有落檔的 prev 也擋，見 contributions 的過濾）。"""
    entry = {"date": "2026-07-31", "prev_date": "2026-07-30",
             "src": "fhtrust", "prev_src": "fhtrust",     # 同源：xsrc 防呆不會生效
             "holdings": _BONDS,
             "prev": {r["stock_id"]: {"shares": r["shares"], "weight": r["weight"],
                                      "name": r["name"]}
                      for r in _BONDS + _ETFINFO_EXTRA}}
    det = eh.contributions(entry, None)
    assert det["moves_n"] == 0                            # 修好前：5 檔假出清
    assert [r["stock_id"] for r in det["dropped"]] == []
    # 鐵則：真出清的異動量一定是負的（前一日股數的相反數）
    assert all((m["m_shares"] or 0) < 0 for m in det["moves"] if m["kind"] == "out")


def test_同源時新增出清照常判定():
    """防呆不可矯枉過正：同一來源的真出清／真新增仍要報出來。"""
    day1 = {"date": "2026-07-30", "src": "fhtrust", "holdings": _BONDS}
    day2 = {"date": "2026-07-31", "src": "fhtrust",
            "holdings": _BONDS[1:] + [{"stock_id": "US99999999ZZ9", "name": "NEW 5 1/2 01/01/31",
                                       "shares": 700000, "weight": 2.0}]}
    det = eh.contributions(eh.merge_one(day1, day2), None)
    kinds = sorted(m["kind"] for m in det["moves"])
    assert kinds == ["new", "out"] and det["xsrc"] is None
    out = next(m for m in det["moves"] if m["kind"] == "out")
    assert out["stock_id"] == _BONDS[0]["stock_id"] and out["m_shares"] < 0


def test_merge_記錄prev來源():
    day1 = {"date": "2026-07-30", "src": "etfinfo", "holdings": _BONDS}
    day2 = {"date": "2026-07-31", "src": "fhtrust", "holdings": _BONDS}
    m = eh.merge_one(day1, dict(day2, holdings=[dict(b, weight=b["weight"] + 0.1)
                                                for b in _BONDS]))
    assert m["prev_src"] == "etfinfo" and m["src"] == "fhtrust"
    # 同日重抓不覆寫 prev_src
    assert eh.merge_one(m, dict(m))["prev_src"] == "etfinfo"


def test_換源必須換到更新的快照(monkeypatch):
    """同一揭露日內在兩源之間跳＝製造跨源 diff。贏家沒帶來更新的快照就維持既有來源。"""
    m = _fh_mod()
    fh = ("fhtrust", _BONDS, "2026-07-30", "", 1)         # 日期不可信（未自報）→ 排序鍵 ""
    ei = ("etfinfo", _BONDS, "2026-07-30", "2026-07-30", 0)
    cands = sorted([fh, ei], key=lambda c: (c[3], c[4]), reverse=True)
    assert cands[0][0] == "etfinfo"                       # 舊行為：etfinfo 頂掉 fhtrust
    # 既有落檔已是 fhtrust／同一揭露日 → 不換
    assert m._prefer_incumbent(cands, "fhtrust", "2026-07-30")[0][0] == "fhtrust"
    # etfinfo 真的更新 → 照換不誤（00991A 靠 etfinfo 頂著的情境）
    ei_new = ("etfinfo", _BONDS, "2026-07-31", "2026-07-31", 0)
    cands2 = sorted([fh, ei_new], key=lambda c: (c[3], c[4]), reverse=True)
    assert m._prefer_incumbent(cands2, "fhtrust", "2026-07-30")[0][0] == "etfinfo"
    # 既有來源這次抓不到 → 只能換
    assert m._prefer_incumbent([ei], "fhtrust", "2026-07-30")[0][0] == "etfinfo"


def test_dashboard_揭露跨來源時說明清楚():
    day1 = {"date": "2026-07-30", "src": "etfinfo", "holdings": _BONDS + _ETFINFO_EXTRA}
    day2 = {"date": "2026-07-31", "src": "fhtrust", "holdings": _BONDS}
    det = eh.contributions(eh.merge_one(day1, day2), None)
    assert fd._eh_payload(det, "主動復華金融債息")["xs"] == ["etfinfo", "fhtrust"]
    assert "新增／出清不予判定" in fd._JS


# ── 報價日（2026-10-21 使用者：「ETF持股異動那邊，漲跌幅是錯的」；docs/etf_chg_fix_plan.md） ──
# 盤查：舊碼不看日期——晚上那幾班上市＝前一天、上櫃＝當天；快照較舊的 ETF 配到別天的漲跌；
# 海外收到盤中價。現在：所有報價都是最新交易日 pd 那一天，每列記 qd，網頁只顯示 qd＝pd 的數字。

PD = "2026-07-28"
QD = {k: {**v, "date": PD} for k, v in QUOTES.items()}


def test_rows_carry_quote_date_and_reject_other_day_quotes():
    q = {**QD, "2454": {**QD["2454"], "date": "2026-07-27"}}         # 聯發科這筆是前一天的
    d = eh.contributions(eh.merge_one(DAY1, DAY2), q, pd=PD)
    by = {r["stock_id"]: r for r in d["all"]}
    assert d["pd"] == PD and by["2330"]["qd"] == PD and by["2330"]["chg_pct"] == 10.0
    assert by["2454"]["chg_pct"] is None and by["2454"]["qd"] is None  # 別天的報價不用
    assert d["total_contrib"] == 2.2


def test_missing_rows_reuse_prior_run_only_for_the_same_quote_date():
    entry = eh.merge_one(DAY1, DAY2)
    prior = eh.contributions(entry, QD, pd=PD)
    # 這班聯發科沒抓到 → 沿用上一班同一報價日的值
    d = eh.contributions(entry, {"2330": QD["2330"]}, pd=PD, prior=prior)
    by = {r["stock_id"]: r for r in d["all"]}
    assert by["2454"]["chg_pct"] == -5.0 and by["2454"]["qd"] == PD
    # 報價日不同 → 不沿用
    d2 = eh.contributions(entry, {"2330": {**QD["2330"], "date": "2026-07-29"}}, pd="2026-07-29", prior=prior)
    by2 = {r["stock_id"]: r for r in d2["all"]}
    assert by2["2454"]["chg_pct"] is None and by2["2330"]["qd"] == "2026-07-29"


def test_pending_foreign_rows_are_flagged():
    r1 = [_h("NVDA US", "NVIDIA", 10000, 8.0), _h("2330", "台積電", 1000, 20.0)]
    entry = eh.merge_one({"date": "d1", "src": "etfinfo", "holdings": r1},
                         {"date": "2026-07-28", "src": "etfinfo", "holdings": r1})
    d = eh.contributions(entry, {"2330": QD["2330"]}, pd=PD, pending={"NVDA US"})
    by = {r["stock_id"]: r for r in d["all"]}
    assert by["NVDA US"]["pend"] is True and by["NVDA US"]["chg_pct"] is None
    assert by["2330"]["pend"] is False and d["n_pend"] == 1


def test_annotate_without_quotes_keeps_prior_quote_date_but_recomputes_holdings():
    """這班完全拿不到台股報價：持股與異動照最新揭露重算，漲跌沿用上一班的報價日（整張表同一天）。"""
    old = {"etfs": {"X": eh.merge_one(DAY1, DAY2)}}
    eh.annotate(old, QD, pd=PD)
    day3 = {"date": "2026-07-29", "src": "test",
            "holdings": [_h("2330", "台積電", 1500, 25.0), _h("2454", "聯發科", 300, 8.0),
                         _h("2603", "長榮", 100, 2.0)]}
    doc = eh.merge(old, {"X": day3})
    assert "detail" not in doc["etfs"]["X"]                # 新揭露的 entry 不帶舊 detail → 要靠 prior_doc
    eh.annotate(doc, {}, prior_doc=old)
    det = doc["etfs"]["X"]["detail"]
    by = {r["stock_id"]: r for r in det["all"]}
    assert det["date"] == "2026-07-29" and det["pd"] == PD                 # 新快照、舊報價日
    assert by["2330"]["chg_pct"] == 10.0 and by["2330"]["shares"] == 1500
    assert by["2603"]["chg_pct"] is None                                   # 新進持股留白


def test_annotate_derives_quote_date_from_quotes():
    doc = {"etfs": {"X": eh.merge_one(DAY1, DAY2)}}
    eh.annotate(doc, QD)
    assert doc["etfs"]["X"]["detail"]["pd"] == PD


def test_dashboard_payload_hides_other_day_and_legacy_numbers():
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QD, pd=PD)
    d["all"][0]["qd"] = "2026-07-27"                       # 假設有一列混進別天（防線）
    pl = fd._eh_payload(d)
    by = {r[0]: r for r in pl["al"]}
    bad = d["all"][0]["stock_id"]
    assert by[bad][4] is None and by[bad][5] is None and by[bad][6] is None
    assert pl["pd"] == PD and pl["tc"] == round(sum(r[6] for r in pl["al"] if r[6] is not None), 2)
    # 舊格式（沒有 pd）：漲跌、收盤、貢獻一律不顯示，合計貢獻為 —
    legacy = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
    legacy.pop("pd", None)
    pl2 = fd._eh_payload(legacy)
    assert all(r[5] is None and r[6] is None for r in pl2["al"]) and pl2["tc"] is None


def test_dashboard_payload_and_js_show_pending_and_both_dates():
    r1 = [_h("NVDA US", "NVIDIA", 10000, 8.0), _h("2330", "台積電", 1000, 20.0)]
    r2 = [_h("NVDA US", "NVIDIA", 11000, 8.5), _h("2330", "台積電", 1000, 19.5)]   # 股數權重全等會被當成同一份快照
    entry = eh.merge_one({"date": "2026-07-24", "src": "etfinfo", "holdings": r1},
                         {"date": "2026-07-27", "src": "etfinfo", "holdings": r2})
    d = eh.contributions(entry, {"2330": QD["2330"]}, pd=PD, pending={"NVDA US"})
    pl = fd._eh_payload(d)
    by = {r[0]: r for r in pl["al"]}
    assert by["NVDA US"][7] == 1 and by["2330"][7] == 0 and pl["np"] == 1
    assert pl["d"] == "2026-07-27" and pl["pd"] == PD       # 快照日與報價日不同 → 前端兩個都標
    js = fd._JS
    assert "function pdTag(e)" in js and "不同日" in js and "漲跌為同日收盤" in js
    assert "待收盤" in js and "已收盤" in js
    assert "當地市場最近收盤" not in js                      # 舊說法（收到盤中價）已移除


def test_same_day_graft_survives_a_new_disclosure():
    """早上那班已補到美股（報價日 pd），下一班持股換新揭露、Yahoo 剛好抓不到 → 仍沿用同一報價日的值。"""
    r1 = [_h("NVDA US", "NVIDIA", 10000, 8.0), _h("2330", "台積電", 1000, 20.0)]
    r2 = [_h("NVDA US", "NVIDIA", 11000, 8.5), _h("2330", "台積電", 900, 19.0)]
    old = {"etfs": {"X": eh.merge_one({"date": "2026-07-27", "src": "etfinfo", "holdings": r1},
                                      {"date": "2026-07-28", "src": "etfinfo", "holdings": r2})}}
    nv = {"close": 185.5, "change": 5.5, "ccy": "USD", "date": PD}
    eh.annotate(old, {"2330": QD["2330"], "NVDA US": nv}, pd=PD)
    r3 = [_h("NVDA US", "NVIDIA", 12000, 9.0), _h("2330", "台積電", 900, 18.5)]
    doc = eh.merge(old, {"X": {"date": "2026-07-29", "src": "etfinfo", "holdings": r3}})
    eh.annotate(doc, {"2330": QD["2330"]}, pd=PD, prior_doc=old)           # 這班沒有 NVDA 報價
    by = {r["stock_id"]: r for r in doc["etfs"]["X"]["detail"]["all"]}
    assert by["NVDA US"]["chg_pct"] == round(5.5 / 180.0 * 100, 2) and by["NVDA US"]["qd"] == PD
    assert by["NVDA US"]["shares"] == 12000                                 # 持股照新揭露
