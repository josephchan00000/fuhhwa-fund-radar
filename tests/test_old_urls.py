"""舊網址都轉得到＋新頂欄（docs/lab_ia_v5_plan.md 第 10 節第 4 段的驗收、第 22 節）。

改版前頂欄六格：台股景氣 x9m.html、美股景氣 x9mu.html、泡沫 x9b.html、訊號總覽 x9o.html、策略 x9.html#v=mac、個股 x9.html，
再加更早的大神策略 x9x.html。這些網址與當時常用的參數（#s=訊號、#i=指標、#r=研究卡、#p=實測區、#tw／#ind 泡沫段、
#i=xs:市場:策略、?v=分頁、#s=代號 個股卡、#co=代號 公司卡、#gl 名詞、#v=compass）用無頭瀏覽器一個一個打開，
看最後落在哪一頁、畫面是不是那個位置。整站用 tests/conftest.py 的 labsite（和用字測試共用同一次建頁）。"""
import pytest

pytest.importorskip("playwright.sync_api")


def _open(b, url, wait=1500, ctx=None):
    pg = ctx.new_page() if ctx else b.new_page(viewport={"width": 1280, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url, wait_until="load")
    pg.wait_for_timeout(wait)
    return pg, errs


def _where(pg):
    """→ (檔名, ?查詢, #hash)；Vercel 的 cleanUrls 在本機沒有，檔名帶 .html。"""
    return pg.evaluate("() => [location.pathname.split('/').pop(), location.search, location.hash]")


# (舊網址, 落在哪一頁, 查詢, 畫面條件（JS，回 true）, 說明)
CASES = (
    ("x9m.html", "x9m.html", "", "document.querySelector('.apptab a.on').dataset.k === 'mkt'"
     " && document.querySelector('.ixsw a.on').textContent === '台股'", "舊頂欄「台股景氣」＝市場・台股"),
    ("x9mu.html", "x9mu.html", "", "document.querySelector('.apptab a.on').dataset.k === 'mkt'"
     " && document.getElementById('ixc').dataset.ix === 'spx'", "舊頂欄「美股景氣」＝市場・S&P 500"),
    ("x9b.html", "x9m.html", "", "document.getElementById('bub').getBoundingClientRect().top < 400",
     "舊頂欄「泡沫」＝市場頁最下面的泡沫"),
    ("x9o.html", "x9m.html", "", "document.getElementById('all') !== null", "舊頂欄「訊號總覽」＝市場・台股（全部指標在頁面裡）"),
    ("x9.html#v=mac", "x9.html", "?v=mac&m=tw", "document.querySelector('#tabs a[data-t=mac]').classList.contains('on')"
     " && document.title === '研究紀錄'", "舊頂欄「策略」＝研究紀錄・總經策略"),
    ("x9.html", "x9.html", "", "document.querySelector('#tabs a[data-t=tw]').classList.contains('on')"
     " && document.querySelector('.apptab a.on').dataset.k === 'cfg'", "舊頂欄「個股」＝配置（個股在配置的工具分頁）"),
    ("x9x.html", "x9.html", "?v=mac&m=tw", "document.querySelector('#tabs a[data-t=mac]').classList.contains('on')",
     "更早的大神策略頁"),
    ("x9x.html#i=xs:spx:rsi2", "x9.html", None, "S.mmk === 'spx' && !!(document.getElementById('m-rsi2') || document.getElementById('ms-rsi2'))",
     "大神策略的一條策略＝總經策略那一條"),
    ("x9o.html#s=tw:heat:Dfund:hot", "x9m.html", "", "!document.getElementById('sgp').hidden"
     " && document.getElementById('sgp').innerText.includes('基本面')", "訊號總覽的一個台股訊號＝市場頁的指標面板"),
    ("x9o.html#i=tw:Dfund", "x9m.html", "", "!document.getElementById('sgp').hidden", "訊號總覽的一個台股指標"),
    ("x9o.html#s=spx:heat:Dfund:hot", "x9mu.html", "", "document.getElementById('ixc').dataset.ix === 'spx'"
     " && !document.getElementById('sgp').hidden", "訊號總覽的一個美股訊號＝美股市場頁的指標面板"),
    ("x9o.html#s=ndx:heat:Dfund:hot", "x9mu.html", "", "document.getElementById('ixc').dataset.ix === 'ndx'"
     " && !document.getElementById('sgp').hidden", "美股其他指數先切到那個指數"),
    ("x9o.html#r=tw:crash", "x9r.html", "", "document.getElementById('rfull').open", "研究卡＝研究紀錄頁的完整研究表"),
    ("x9o.html#p=A1:tw", "x9r.html", "", "document.getElementById('rfull') !== null", "實測區＝研究紀錄頁"),
    ("x9b.html#tw", "x9m.html", "", "document.getElementById('bub').getBoundingClientRect().top < 400", "泡沫頁的台股卡"),
    ("x9b.html#ndx", "x9mu.html", "", "document.getElementById('ixc').dataset.ix === 'ndx'"
     " && document.getElementById('bub').getBoundingClientRect().top < 400", "泡沫頁的那斯達克 100 卡"),
    ("x9b.html#ind", "x9r.html", "", "document.getElementById('bub-ind') !== null", "泡沫頁的產業段＝研究紀錄頁"),
    ("x9.html?v=opp", "x9.html", "?v=opp", "document.querySelector('#tabs a[data-t=stg]').classList.contains('on')",
     "個股策略・這一期（研究紀錄）"),
    ("x9.html?v=bo&at=bo-sig", "x9.html", "?v=bo", "Math.abs(document.getElementById('bo-sig').getBoundingClientRect().top) < 300",
     "後台的一段"),
    ("x9.html#s=2330", "x9.html", "?v=stk", "!document.getElementById('dv').hidden && document.getElementById('dvin').innerText.includes('2330')",
     "個股卡"),
    ("x9.html#co=2330", "x9.html", "?v=stk", "!document.getElementById('dv').hidden", "公司卡"),
    ("x9.html#gl", "x9.html", "", "!document.getElementById('gl').hidden", "名詞"),
    ("x9m.html#v=compass", "x9m.html", "", "document.querySelector('.hview[data-view=phase]') && !document.querySelector('.hview[data-view=phase]').hidden",
     "舊的羅盤畫面＝階段時間軸"),
    ("x9.html#q", "x9.html", "?v=stk", "!document.getElementById('cos').hidden", "別頁頂欄的「查公司」"),
)


@pytest.mark.parametrize("old,page,query,cond,what", CASES, ids=[c[0] for c in CASES])
def test_old_url_lands(labsite, old, page, query, cond, what):
    b, base, _ = labsite
    pg, errs = _open(b, f"{base}/{old}", wait=2500 if "#" in old else 1500)
    try:
        f, q, _ = _where(pg)
        assert f == page, (what, f)
        if query is not None:
            assert q == query, (what, q)
        assert pg.evaluate(f"() => {{ try {{ return !!({cond}); }} catch (e) {{ return 'ERR ' + e; }} }}") is True, what
        assert not errs, (what, errs)
    finally:
        pg.close()


def test_candidate_link_opens_card(labsite):
    """配置頁策略表的候選列連到 x9r.html#cand-c###：研究紀錄頁打開那張卡（research_page.OPEN_JS）並捲到那裡。"""
    import re
    b, base, out = labsite
    ids = re.findall(r'<details[^>]* id="(cand-c\d{3})"', (out / "x9r.html").read_text(encoding="utf-8"))
    if not ids:
        pytest.skip("還沒有候選")
    pg, errs = _open(b, f"{base}/x9r.html#{ids[-1]}", wait=1500)
    try:
        st = pg.evaluate("(k) => { const e = document.getElementById(k); return [e.open, Math.round(e.getBoundingClientRect().top)]; }", ids[-1])
        assert st[0] is True and abs(st[1]) < 200, st
        assert not errs, errs
    finally:
        pg.close()


def test_top_bar_links_and_memory(labsite):
    """頂欄：兩格各記住上次看到哪裡；右邊小字的名詞、查公司在配置頁是頁內打開，其他頁連到研究紀錄、配置頁。"""
    b, base, _ = labsite
    ctx = b.new_context(viewport={"width": 1280, "height": 900})  # 同一個瀏覽器設定檔（localStorage 共用）
    try:
        pg, errs = _open(b, f"{base}/x9mu.html#ix=ndx", ctx=ctx)
        assert pg.evaluate("() => document.querySelector('.apptab a[data-k=cfg]').getAttribute('href')") == "x9.html"
        lk = pg.evaluate("() => [...document.querySelectorAll('.applk a')].map(a => [a.textContent, a.getAttribute('href')])")
        assert lk == [["研究紀錄", "x9r.html"], ["名詞", "x9r.html#mth"], ["查公司", "x9.html#q"]]
        pg.close()
        pg, errs2 = _open(b, f"{base}/x9.html?v=us", ctx=ctx)
        assert pg.evaluate("() => document.querySelector('.apptab a[data-k=mkt]').getAttribute('href')") == "x9mu.html#ix=ndx"
        pg.evaluate("() => document.querySelector('.applk .glk').click()")
        assert pg.evaluate("() => !document.getElementById('gl').hidden")                  # 名詞：頁內面板
        pg.evaluate("() => { document.getElementById('glx').click(); document.querySelector('.coqb').click(); }")
        assert pg.evaluate("() => !document.getElementById('cos').hidden && document.activeElement.id === 'coq'")   # 查公司：搜尋框
        pg.keyboard.press("Escape")
        assert pg.evaluate("() => document.getElementById('cos').hidden")
        pg.close()
        pg, errs3 = _open(b, f"{base}/x9m.html", ctx=ctx)
        assert pg.evaluate("() => document.querySelector('.apptab a[data-k=cfg]').getAttribute('href')") == "x9.html?v=us"
        pg.close()
        pg, errs4 = _open(b, f"{base}/x9.html", ctx=ctx)                 # 市場紀錄已換成台股
        assert pg.evaluate("() => document.querySelector('.apptab a[data-k=mkt]').getAttribute('href')") == "x9m.html"
        pg.close()
        pg, errs5 = _open(b, f"{base}/x9r.html", ctx=ctx)                 # 研究紀錄頁：兩格都不亮、各連到上次的位置
        assert pg.evaluate("() => document.querySelectorAll('.apptab a.on').length") == 0
        assert pg.evaluate("() => [...document.querySelectorAll('.apptab a')].map(a => a.getAttribute('href'))") == ["x9m.html", "x9.html"]
        assert pg.evaluate("() => document.querySelector('.applk a[aria-current]').textContent") == "研究紀錄"
        pg.close()
        assert not (errs + errs2 + errs3 + errs4 + errs5)
    finally:
        ctx.close()


@pytest.mark.parametrize("w", (320, 360, 375, 390, 414))
def test_phone_top_bar_fits(labsite, w):
    """手機：頂欄不橫捲；360px 以上兩格、小字、深淺色、主頁在同一列；320px 小字換到第二列。"""
    b, base, _ = labsite
    for url in ("x9m.html", "x9.html", "x9r.html"):
        pg = b.new_page(viewport={"width": w, "height": 800})
        pg.goto(f"{base}/{url}", wait_until="load")
        pg.wait_for_timeout(600)
        r = pg.evaluate("""() => { const t = document.querySelector('.top'), rs = [...t.children].filter(e => e.offsetParent !== null)
          .map(e => e.getBoundingClientRect()), mid = rs.map(r => r.top + r.height / 2).sort((a, b) => a - b);
          let rows = 1; for (let i = 1; i < mid.length; i++) if (mid[i] - mid[i - 1] > 12) rows++;
          const lk = document.querySelector('.applk').getBoundingClientRect(), ap = document.querySelector('.apptab').getBoundingClientRect();
          return {sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, rows,
                  right: Math.max(...rs.map(r => r.right)), lkBelow: lk.top > ap.bottom - 2}; }""")
        assert r["sw"] <= r["cw"] and r["right"] <= w, (url, w, r)
        if w >= 360:
            assert r["rows"] == 1, (url, w, r)
        else:
            assert r["rows"] == 2 and r["lkBelow"], (url, w, r)            # 小字在第二列（兩格、深淺色、主頁在第一列）
        pg.close()


@pytest.mark.parametrize("w", (360, 390))
def test_phone_no_sideways_scroll_with_everything_open(labsite, w):
    """手機：收起來的段落全部打開也不能整頁左右捲（2026-10-23 第 4 段量到：配置頁「細節」裡的表 1,213px 寬、
    市場頁泡沫的產業那一行在 320px 不換行）；配置頁「細節」的圖要有樣式（只顯示手機版那張、不是整片黑塊）。"""
    b, base, _ = labsite
    for url in ("x9m.html", "x9mu.html", "x9.html", "x9.html?v=us", "x9.html?v=strat"):
        pg = b.new_page(viewport={"width": w, "height": 800})
        pg.goto(f"{base}/{url}", wait_until="load")
        pg.wait_for_timeout(1000)
        pg.evaluate("() => document.querySelectorAll('main details').forEach(d => { d.open = true; })")
        pg.wait_for_timeout(300)
        sw = pg.evaluate("() => document.documentElement.scrollWidth")
        assert sw <= w, (url, w, sw)
        if url.startswith("x9.html") and pg.evaluate("() => !!document.querySelector('.cfpln .plnch')"):
            st = pg.evaluate("""() => { const d = document.querySelector('.cfpln .plnch.plnchd'), m = document.querySelector('.cfpln .plnch.plnchm'),
              p = document.querySelector('.cfpln .plnpp'); return [d && getComputedStyle(d).display, m && getComputedStyle(m).display,
              p && getComputedStyle(p).fill]; }""")
            assert st[0] == "none" and st[1] == "block" and st[2] == "none", (url, st)   # 手機只顯示手機版圖、線不是填滿的黑塊
        pg.close()


def test_us_card_clicks_and_direct_link(labsite):
    """美股個股卡（配置頁 v2 第 4 步）：配置頁美股列點了打開卡片（#us=代號）、‹ › 與左右鍵照配置頁的順序換檔、Esc 關掉回到原頁；
    直接打開 x9.html#us=代號 落在配置・美股並打開卡片；手機 320～414px 卡片不左右捲。"""
    b, base, _ = labsite
    pg, errs = _open(b, f"{base}/x9.html?v=us", wait=1000)
    try:
        codes = pg.evaluate("() => [...document.querySelectorAll('#main a.cfrow[data-us]')].map(a => a.dataset.us)")
        if not codes:
            pytest.skip("美股強勢品質股沒在用（判定沒過或還沒有每週紀錄）")
        st = "() => [location.hash, !document.getElementById('dv').hidden, (document.querySelector('#dvin .ttl b') || {}).textContent || '']"
        pg.click("#main a.cfrow[data-us] >> nth=0")
        pg.wait_for_timeout(400)
        h, vis, ttl = pg.evaluate(st)
        assert h == f"#us={codes[0]}" and vis and ttl, (h, vis, ttl)
        for s in ("#uc-st", "#uc-why", "#uc-px", "#uc-an", "#uc-co"):
            assert pg.query_selector(f"#dvin {s}") is not None, s
        order = pg.evaluate("() => UCD.o")
        if len(order) > 1:
            pg.click("#nx")
            pg.wait_for_timeout(300)
            assert pg.evaluate(st)[0] == f"#us={order[1]}"
            pg.keyboard.press("ArrowLeft")
            pg.wait_for_timeout(300)
            assert pg.evaluate(st)[0] == f"#us={order[0]}"
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(400)
        h, vis, _ = pg.evaluate(st)
        assert h == "" and not vis and pg.evaluate("() => location.search") == "?v=us"
        assert not errs, errs
    finally:
        pg.close()
    pg, errs = _open(b, f"{base}/x9.html#us={codes[0]}", wait=1200)
    try:
        assert pg.evaluate("() => [S.tab, location.search, !document.getElementById('dv').hidden]") == ["us", "?v=us", True]
        assert not errs, errs
    finally:
        pg.close()
    for w in (320, 360, 390, 414):
        pg = b.new_page(viewport={"width": w, "height": 800})
        try:
            pg.goto(f"{base}/x9.html?v=us#us={codes[0]}", wait_until="load")
            pg.wait_for_timeout(900)
            sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.getElementById('dv').scrollWidth]")
            assert max(sw) <= w, (w, sw)
        finally:
            pg.close()

