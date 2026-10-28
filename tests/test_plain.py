"""主頁面用字（docs/lab_ia_v5_plan.md 第 8 節第 7 條）：建好市場頁（台股、美股四個指數）與選股頁（台股、美股、
個股工具、個股卡、公司卡、美股個股卡；2026-10-28 起取代配置頁），用無頭瀏覽器打開，讀「看得到的字」（收起來的段落全部打開、右側面板與指標面板一個一個打開），
不得出現：第 2 條的方法字（只當參考、樣本外、隨便挑一天……）、第 4 條研究用的狀態符號（★●○◆△、好策略、可參考、A／B／C 級）、
第 6 條的字（核心、衛星、前瞻、箭頭……）。研究紀錄頁、市場頁的研究畫面（#v=research／phase／terrain）不掃；
細項面板裡只在研究畫面才看得到的部分（.rsx）也不算。要用真的資料建頁（約 3 分鐘），瀏覽器或資料不在就跳過。"""
import pytest

pytest.importorskip("playwright.sync_api")
METHOD = ("只當參考", "不當成預估", "看不出", "樣本不足", "亂排", "打亂", "預估之後", "逐年檢查", "判定依據", "前後兩半",
          "樣本外", "穩健度", "對照", "規格", "VER", "門檻", "區間", "研究", "候選", "注意", "教訓", "本頁", "我們",
          "隨便挑一天", "判定", "樣本", "信賴", "顯著", "p 值")
STATUS = ("★", "●", "○", "◆", "△", "好策略", "可參考", "A 級", "B 級", "C 級")
NOT_PLAIN = ("核心", "衛星", "三種過熱", "亮", "前瞻", "→", "←")
ALLOW = ("研究紀錄", "核心 CPI", "核心 PCE")          # 連到研究紀錄頁的小字；指標名稱
CFG_ALLOW = ("候選",)                                # 策略狀態（使用中・觀察中・候選・淘汰）
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


@pytest.fixture(scope="module")
def site(labsite):
    """整站（tests/conftest.py 的 labsite，和舊網址測試共用同一次建頁）。"""
    b, base, _ = labsite
    return b, base


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
    if "#ix=" in url:                                         # 美股頁：預設以外的指數下載完才換上（x9mup-{指數}.json）
        pg.wait_for_function(f"() => document.getElementById('ixc').dataset.ix === '{name}' && !document.getElementById('ixc').hasAttribute('aria-busy')",
                             timeout=15000)
        assert pg.evaluate("() => window.heatPanels()") is True    # 細項面板：預設的指數點到才下載，這裡先載好
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
    if "#ix=" in url:                                         # 這個指數自己的列（預設以外的指數由 x9mup 併進來）
        assert any(r.startswith(name + ":") for r in rows), name
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
    """選股頁：台股、美股、個股工具（個股、籌碼、指數），個股卡、公司卡、美股個股卡。進場行事曆（.pkcalw：圖例、月曆、接下來）
    與時間軸（.cftl）的 ◇▲▼◆●○ 是名單、買賣、財報的記號、不是評級，只檢查方法字。原本配置頁的交易計畫、全部策略搬到研究紀錄，不掃。"""
    b, base = site
    found = []
    for v in ("tw", "us", "stk", "chip", "idx"):
        pg, errs = _page(b, f"{base}/x9.html?v={v}")
        pg.evaluate(OPEN, "#main")
        tl = pg.evaluate("() => [...document.querySelectorAll('#main .cftl, #main .pkcalw')].map(e => e.innerText).join('\\n')")
        pg.evaluate("() => document.querySelectorAll('#main .cftl, #main .pkcalw').forEach(e => { e.style.display = 'none'; })")
        found += [f"{v} {x}" for x in bad(pg.evaluate("() => document.getElementById('main').innerText"), allow=CFG_ALLOW)]
        found += [f"{v} 時間軸 {x}" for x in bad(tl, METHOD + NOT_PLAIN, CFG_ALLOW)]
        found += [f"{v} JS 錯誤：{e}" for e in errs]
        pg.close()
    pg, errs = _page(b, f"{base}/x9.html?v=us")                  # 美股個股卡：每一檔都打開
    codes = pg.evaluate("() => (typeof UCD !== 'undefined' && UCD && UCD.o) || []")   # 頂層 const 不在 window 上
    for c in codes:
        pg.evaluate("(c) => ucOpen(c)", c)
        pg.wait_for_timeout(200)
        t = pg.evaluate("() => document.getElementById('dv').innerText")
        assert len(t) > 200, c
        intro = pg.evaluate("() => [...document.querySelectorAll('#uc-co .ucl')].map(e => e.innerText).join('')")
        t = t.replace(intro, "") if intro else t                 # 公司簡介是公司本身的描述（例「基因體研究中心」），不是頁面的方法用字
        found += [f"美股卡 {c} {x}" for x in bad(t, allow=CFG_ALLOW)]
    found += [f"美股卡 JS 錯誤：{e}" for e in errs]
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
