"""主頁面用字（docs/lab_ia_v5_plan.md 第 8 節第 7 條）：建好市場頁（台股、美股四個指數）與配置頁（台股、美股、策略、
個股工具、個股卡、公司卡），用無頭瀏覽器打開，讀「看得到的字」（收起來的段落全部打開、右側面板與指標面板一個一個打開），
不得出現：第 2 條的方法字（只當參考、樣本外、隨便挑一天……）、第 4 條研究用的狀態符號（★●○◆△、好策略、可參考、A／B／C 級）、
第 6 條的字（核心、衛星、前瞻、箭頭……）。研究紀錄頁、市場頁的研究畫面（#v=research／phase／terrain）不掃；
細項面板裡只在研究畫面才看得到的部分（.rsx）也不算。要用真的資料建頁（約 3 分鐘），瀏覽器或資料不在就跳過。"""
import functools
import glob
import http.server
import re
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

CHROME = next(iter(sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))), None)
METHOD = ("只當參考", "不當成預估", "看不出", "樣本不足", "亂排", "打亂", "預估之後", "逐年檢查", "判定依據", "前後兩半",
          "樣本外", "穩健度", "對照", "規格", "VER", "門檻", "區間", "研究", "候選", "注意", "教訓", "本頁", "我們",
          "隨便挑一天", "判定", "樣本", "信賴", "顯著", "p 值")
STATUS = ("★", "●", "○", "◆", "△", "好策略", "可參考", "A 級", "B 級", "C 級")
NOT_PLAIN = ("核心", "衛星", "三種過熱", "亮", "前瞻", "→", "←")
ALLOW = ("研究紀錄", "核心 CPI", "核心 PCE")          # 連到研究紀錄頁的小字；指標名稱
CFG_ALLOW = ("候選",)                                # 配置頁的策略狀態（使用中・觀察中・候選・淘汰）
OPEN = """(sel) => { const r = sel ? document.querySelector(sel) : document;
  if (r) r.querySelectorAll('details').forEach(d => { if (!d.closest('.hview[hidden]')) d.open = true; }); }"""


def bad(text: str, words=METHOD + STATUS + NOT_PLAIN, allow=()) -> list[str]:
    """不該出現的字（含前後各 25 字），一個字列一次。"""
    for a in ALLOW + tuple(allow):
        text = text.replace(a, "")
    out = []
    for w in words:
        i = text.find(w)
        if i >= 0:
            out.append(f"{w}：…{text[max(0, i - 25): i + len(w) + 25]}…".replace("\n", "⏎"))
    return out


def test_bad_finds_words_and_skips_allowed():
    assert bad("之後 1 個月上漲 65%（任一天 58%）・報酬中位 +2.1%") == []
    assert bad("過去 65%（隨便挑一天 58%）")[0].startswith("隨便挑一天")
    assert bad("看研究紀錄・核心 CPI 年增率") == []
    assert [x.split("：")[0] for x in bad("★ 好訊號 → 樣本外")] == ["樣本外", "樣本", "★", "→"]
    assert bad("使用中 4・候選 0", allow=CFG_ALLOW) == []


class _Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    if not CHROME:
        pytest.skip("沒有 Chromium")
    from arm.lab import heatpage, heatpage_us, page, sigpage
    O = tmp_path_factory.mktemp("plain")
    if not page.build(O / "x9.html", O / "x9s.json") and not (O / "x9.html").exists():
        pytest.skip("配置頁建不起來（資料不在）")
    heatpage.build(O / "x9m.html", O / "x9mh.json")
    heatpage_us.build(O / "x9mu.html", O)
    sigpage.build(O / "x9o.html", O / "x9oh.json")             # 指標面板每一次的清單 x9oh-{市場}.json
    page.finish()                                             # 配置頁用今天的警訊讀數
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Q, directory=str(O)))
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        yield b, f"http://127.0.0.1:{srv.server_address[1]}"
        b.close()
    srv.shutdown()


def _page(b, url):
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url, wait_until="load")
    pg.wait_for_timeout(1500)
    return pg, errs


def _market(b, url, name, every):
    """市場頁一個指數：主畫面（收起來的全部打開、全部指標列出全部）、每個右側面板、指標面板（每 every 個打開一個）。"""
    pg, errs = _page(b, url)
    found = []
    pg.evaluate(OPEN, ".hview[data-view=radar]")
    for _ in range(3):
        pg.evaluate("() => { const m = document.getElementById('sgmore'); if (m && !m.hidden) m.click(); }")
        pg.wait_for_timeout(150)
    found += [f"{name} 主畫面 {x}" for x in bad(pg.evaluate("() => document.querySelector('.hview[data-view=radar]').innerText"))]
    keys = pg.evaluate("() => [...document.querySelectorAll('template[id^=\"dt-\"],template[id^=\"it-\"]')].map(t => t.id.slice(3))")
    assert keys, name
    for k in keys:
        pg.evaluate("(k) => window.heatOpen(k)", k)
        pg.evaluate(OPEN, "#drw-c")
        t = pg.evaluate("() => document.getElementById('drw-k').innerText + ' ' + document.getElementById('drw-t').innerText"
                        " + '\\n' + document.getElementById('drw-c').innerText")
        found += [f"{name} 面板 {k} {x}" for x in bad(t)]
    pg.evaluate("() => window.heatClose(true)")
    pg.evaluate("() => document.querySelector('.rout').click()")
    pg.evaluate(OPEN, "#drw-c")
    found += [f"{name} 之後怎麼走 {x}" for x in bad(pg.evaluate("() => document.getElementById('drw-c').innerText"))]
    pg.evaluate("() => window.heatClose(true)")
    rows = [r for r in pg.evaluate("() => [...document.querySelectorAll('tr.sgr[data-k]')].map(t => t.dataset.k)")
            if not r.startswith("xs:")]                       # 總經策略那幾列連到研究紀錄的說明卡
    assert rows, name
    for k in rows[::every]:
        pg.evaluate("(k) => document.querySelector('tr.sgr[data-k=\"' + CSS.escape(k) + '\"]').click()", k)
        pg.wait_for_function("() => { const r = document.getElementById('sgrec'); return r && !/載入中/.test(r.innerText); }",
                             timeout=10000)
        pg.evaluate(OPEN, "#sgp")
        found += [f"{name} 指標 {k} {x}" for x in bad(pg.evaluate("() => document.getElementById('sgp').innerText"))]
    pg.close()
    return found + [f"{name} JS 錯誤：{e}" for e in errs]


def test_market_pages_have_no_method_words(site):
    b, base = site
    found = _market(b, f"{base}/x9m.html", "台股", 1)
    for ix in ("spx", "ixic", "ndx", "sox"):
        found += _market(b, f"{base}/x9mu.html#ix={ix}", ix, 3)
    assert not found, "\n".join(found[:40])


def test_config_pages_have_no_method_words(site):
    """配置頁：台股、美股、策略、個股工具（個股、籌碼、指數），個股卡、公司卡。時間軸（.cftl：圖例、範圍切換、圖）的 ▲▼◆●
    是買賣的記號、不是評級，時間軸只檢查方法字。"""
    b, base = site
    found = []
    for v in ("tw", "us", "strat", "stk", "chip", "idx"):
        pg, errs = _page(b, f"{base}/x9.html?v={v}")
        pg.evaluate(OPEN, "#main")
        tl = pg.evaluate("() => [...document.querySelectorAll('#main .cftl')].map(e => e.innerText).join('\\n')")
        pg.evaluate("() => document.querySelectorAll('#main .cftl').forEach(e => { e.style.display = 'none'; })")
        found += [f"{v} {x}" for x in bad(pg.evaluate("() => document.getElementById('main').innerText"), allow=CFG_ALLOW)]
        found += [f"{v} 時間軸 {x}" for x in bad(tl, METHOD + NOT_PLAIN, CFG_ALLOW)]
        found += [f"{v} JS 錯誤：{e}" for e in errs]
        pg.close()
    for h, nm in (("#s=2330", "個股卡"), ("#co=2330", "公司卡")):
        pg, errs = _page(b, f"{base}/x9.html?v=stk{h}")
        pg.wait_for_timeout(1500)
        pg.evaluate(OPEN, "#dv")
        t = pg.evaluate("() => { const d = document.getElementById('dv'); return d ? d.innerText : ''; }")
        assert len(t) > 500, nm
        found += [f"{nm} {x}" for x in bad(t, allow=CFG_ALLOW)] + [f"{nm} JS 錯誤：{e}" for e in errs]
        pg.close()
    assert not found, "\n".join(found[:40])
