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
    """全球型主動 ETF 的海外持股進不了本表（代號非台股 4 碼）——權重合計遠低於 100%
    時必須標「僅台股部位」，否則 23% 的清單看起來像完整持股（誤導）。"""
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
    html = fd._holdings_detail("00988A", d)
    assert "僅台股部位" in html and "30%" in html
    # 權重合計正常（≥60%）的檔不標
    d2 = dict(d, sum_weight=90.5)
    assert "僅台股部位" not in fd._holdings_detail("00981A", d2)


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
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
    ok = dict(d, verify={"status": "match", "other": "moneydj", "top_hit": 9,
                         "top_n": 10, "max_dw": 0.3})
    assert "🟢 雙源相符" in fd._holdings_detail("X", ok)
    bad = dict(d, verify={"status": "mismatch", "other": "moneydj", "top_hit": 3,
                          "top_n": 10, "max_dw": 4.2})
    html = fd._holdings_detail("X", bad)
    assert "⚠ 兩源不符" in html and "4.2pp" in html
    one = dict(d, verify={"status": "single", "other": None})
    assert "單源未驗證" in fd._holdings_detail("X", one)
    assert "Tier B" in fd._holdings_detail("X", d)        # 來源誠實標示


def test_verify_flows_from_entry_to_detail():
    """verify 記在 entry、detail 由 contributions 帶出——儀表板端純渲染不重算。"""
    entry = {**eh.merge_one(DAY1, DAY2), "verify": {"status": "match", "other": "moneydj",
                                                    "top_hit": 10, "top_n": 10, "max_dw": 0.1}}
    d = eh.contributions(entry, QUOTES)
    assert d["verify"]["status"] == "match"
