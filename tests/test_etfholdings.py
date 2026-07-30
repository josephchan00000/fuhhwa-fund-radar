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

def test_dashboard_payload_carries_moves_and_holdings():
    """ETF 詳情（2026-07-30 改版）：內容由前端依內嵌資料渲染，故渲染測試改測 payload。"""
    d = eh.contributions(eh.merge_one(DAY1, DAY2), QUOTES)
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
    """三段版面骨架（比照使用者提供的架構）：方塊圖／異動表／完整持股＋搜尋＋分頁。"""
    doc = {"etfs": {"0050": {**eh.merge_one(DAY1, DAY2), "detail": None}}}
    doc["etfs"]["0050"]["detail"] = eh.contributions(doc["etfs"]["0050"], QUOTES)
    html = fd._etf_detail_view({"items": [{"code": "0050", "name": "元大台灣50"}]}, doc)
    for anchor in ('id="etf-detail"', 'id="ed-tmap"', 'id="ed-mv"', 'id="ed-hb"',
                   'id="ed-q"', 'id="ed-pgn"', 'class="edchip"'):
        assert anchor in html, anchor
    assert "每格＝一檔異動股票" in html
    assert "</script>" not in html.split("window.__EH=")[1].split(";</script>")[0]


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
    assert "fig.hidden=!tm.length" in js                   # 有東西可畫就畫；只有全無異動才收掉
    assert "tm.length<3" not in js                         # 「少於 3 格不畫」規則已移除


def test_treemap_legend_names_both_directions():
    """圖例必須同時標出兩個方向與亮度的意義——顏色不可是唯一線索。"""
    entry = eh.merge_one(DAY1, DAY2)
    entry["detail"] = eh.contributions(entry, QUOTES)
    html = fd._etf_detail_view({"items": [{"code": "0050", "name": "元大台灣50"}]},
                               {"etfs": {"0050": entry}})
    assert "加碼／新增" in html and "減碼／出清" in html
    assert "色塊越亮＝幅度越大" in html and "虛線框＝新增或出清" in html
    assert fd._TM_UP in html and fd._TM_DN in html


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
    assert "ed-mvfoot" in fd._JS


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
