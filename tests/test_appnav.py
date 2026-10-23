"""市場、配置、研究紀錄共用的頂欄（arm/lab/appnav.py；docs/lab_ia_v5_plan.md 第 2、22 節）。"""
from arm.lab import appnav, heatpage, heatpage_us, page


def test_bar_marks_the_current_page():
    """頂欄（docs/lab_ia_v5_plan.md 第 2、22 節，照核准過的示意圖）：只剩「市場｜配置」兩格，右邊小字「研究紀錄・名詞・查公司」。"""
    assert [k for k, _, _ in appnav.TABS] == ["mkt", "cfg"]
    mkt = appnav.bar("mkt")
    assert mkt.startswith('<nav class="apptab" aria-label="頁面">') and mkt.count('data-k=') == 2
    assert '<a class="on" aria-current="page" data-k="mkt" href="x9m.html">市場</a><a data-k="cfg" href="x9.html">配置</a>' in mkt
    us = appnav.bar("mkt", cur="x9mu.html")                                      # 美股頁：「市場」亮、連回美股頁
    assert '<a class="on" aria-current="page" data-k="mkt" href="x9mu.html">市場</a>' in us
    cfg = appnav.bar("cfg")
    assert '<a data-k="mkt" href="x9m.html">市場</a><a class="on" aria-current="page" data-k="cfg" href="x9.html">配置</a>' in cfg
    r = appnav.bar("r")                                                          # 研究紀錄頁：兩格都不亮
    assert "aria-current=\"page\" data-k" not in r and 'class="on"' not in r
    for page in ("mkt", "cfg", "r", ""):
        b = appnav.bar(page)
        for old in ("x9x.html", "x9.html#v=mac", "x9b.html", "x9o.html", "景氣", "泡沫", "訊號總覽", ">策略<", ">個股<"):
            assert old not in b, (page, old)                                     # 舊的分頁名稱與舊頁面都不在頂欄


def test_right_links_research_glossary_company():
    """右邊小字：研究紀錄・名詞・查公司。名詞與查公司依頁面不同（見 appnav 開頭說明）。"""
    import re
    def links(b):
        return re.findall(r'<a ([^>]*)>([^<]+)</a>', b.split('<nav class="applk"', 1)[1])
    mkt = dict((t, a) for a, t in links(appnav.bar("mkt")))
    assert list(mkt) == ["研究紀錄", "名詞", "查公司"]
    assert mkt["研究紀錄"] == 'href="x9r.html"' and mkt["名詞"] == 'href="x9r.html#mth"' and mkt["查公司"] == 'href="x9.html#q"'
    search = '<div class="cos" id="cos" hidden>X</div>'
    cb = appnav.bar("cfg", search=search)
    cfg = dict((t, a) for a, t in links(cb))
    assert cfg["名詞"] == 'href="#gl" class="glk"' and 'class="coqb"' in cfg["查公司"] and 'aria-controls="cos"' in cfg["查公司"]
    assert cb.index("查公司</a>") < cb.index(search) < cb.index("</nav>", cb.index("applk"))   # 搜尋框在小字那一組裡（點了才打開）
    r = dict((t, a) for a, t in links(appnav.bar("r")))
    assert r["研究紀錄"] == 'href="x9r.html" aria-current="page"' and r["名詞"] == 'href="#gl"' and r["查公司"] == 'href="x9.html#q"'


def test_remember_last_place_per_tab():
    """兩格各記住上次看到哪裡（localStorage labLast）；只收看得到的位置，研究紀錄的分頁、個股卡不記。"""
    import re
    js = appnav.NAV_HEAD
    assert '"labLast"' in js and "window.labLast=function(k,v)" in js and 'classList.contains("on")' in js
    ok = dict(re.findall(r'(mkt|cfg):/(.*?)/[,}]', js))
    py = {k: re.compile(v.replace("\\/", "/")) for k, v in ok.items()}
    for v in ("x9m.html", "x9mu.html", "x9mu.html#ix=ndx", "x9mu.html#ix=sox"):
        assert py["mkt"].match(v), v
    for v in ("x9.html", "x9.html?v=us", "x9.html?v=strat", "x9.html?v=stk", "x9.html?v=chip", "x9.html?v=idx"):
        assert py["cfg"].match(v), v
    for v in ("x9.html?v=bo", "x9.html?v=mac", "x9.html#s=2330", "x9r.html", "https://evil.example/x9m.html", "x9mu.html#ix=x"):
        assert not py["mkt"].match(v) and not py["cfg"].match(v), v
    assert 'if(a[i].classList.contains("on")){if(!v||v.indexOf(h)!==0)window.labLast(k,h)}' in js   # 亮的那一格記成這一頁（台股市場頁）
    from arm.lab import heatpage_us
    assert "window.labLast('mkt', 'x9mu.html#ix=' + cur)" in heatpage_us.SWITCH_JS   # 美股市場頁（換指數時也記）
    assert "if(PER==='cfg'&&window.labLast)labLast('cfg','x9.html'+q);" in page._JS       # 配置頁（研究紀錄的分頁不記）


def test_phone_top_bar_fits_one_row():
    """手機（640px 以下）：深淺色鈕只留圖示、返回主頁寫「主頁」，兩格＋小字＋兩顆鈕放得下一列。"""
    css = appnav.CSS
    mob = css[css.index("@media (max-width:640px)"):]
    assert ".top .thm-t{display:none}" in mob and ".top .bk1{display:none}" in mob
    assert appnav.BACK == '<a class="back" href="./"><span class="bk1">返回</span>主頁</a>'
    assert ".applk{" in css and "margin-left:auto" in css.split(".applk{", 1)[1].split("}", 1)[0]


def test_both_pages_use_the_shared_bar_and_back_link():
    lab = page.render({"etfs": {}, "asof": {}})
    from arm.lab import copage
    assert appnav.bar("cfg", search=copage.SEARCH_HTML) in lab and appnav.CSS in lab
    assert appnav.BACK in lab and "<b>籌碼雷達</b>" not in lab
    from arm.lab import research_page
    for tpl in (page._HTML, heatpage._HTML, heatpage_us._HTML, research_page._HTML):
        top = tpl.split('<div class="top">', 1)[1].split("</div>", 1)[0]
        assert top == "{{APPTAB}}" + appnav.BACK                                # 頂欄只有兩格＋小字（APPTAB）與返回主頁；資料日不放頂欄
        assert 'class="asof"' not in tpl


def test_theme_toggle_dual_dark_css_and_finish():
    """日夜間按鈕（docs/lab_noise_plan.md 第 5、11 節；使用者選自動 → 淺色 → 深色）：深色樣式改寫成「系統深色而且沒選淺色」
    與「選了深色」兩份；<head> 在畫面出來之前套上 data-theme；頂欄「返回主頁」前面一顆按鈕；用程式算顏色的圖聽 labtheme 重畫。"""
    from arm.lab import appnav as A
    css = ":root{--bg:#fff}@media (prefers-color-scheme:dark){:root{--bg:#000}.a,.b{--c:1}}.z{color:red}"
    out = A.dual_dark(css)
    assert out == (':root{--bg:#fff}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#000}'
                   ':root:not([data-theme="light"]) .a,:root:not([data-theme="light"]) .b{--c:1}}'
                   ':root[data-theme="dark"]{--bg:#000}:root[data-theme="dark"] .a,:root[data-theme="dark"] .b{--c:1}.z{color:red}')
    odd = "@media (prefers-color-scheme:dark){@supports (x:y){.a{b:c}}}"
    assert A.dual_dark(odd) == odd                                                # 看不懂的段落照原樣保留
    page = ('<html><head><style>:root{--bg:#fff}@media (prefers-color-scheme:dark){:root{--bg:#000}}</style></head><body>'
            '<div class="top"><nav></nav>' + A.BACK + '</div></body></html>')
    f = A.finish(page)
    head = f[:f.index("</head>")]
    assert ':root[data-theme="dark"]{--bg:#000}' in head and A.THEME_CSS in head and A.THEME_HEAD in head
    assert head.index("</style>") < head.index(A.THEME_HEAD)
    assert f.count('id="thm"') == 1 and f.index('id="thm"') < f.index('<a class="back"')
    assert head.index(A.THEME_HEAD) < head.index(A.NAV_HEAD)                       # 記住上次位置的程式也在 <head>
    assert '"labTheme"' in A.THEME_HEAD and '["auto","light","dark"]' in A.THEME_HEAD and 'new Event("labtheme")' in A.THEME_HEAD
    assert "localStorage.removeItem(K)" in A.THEME_HEAD                             # 回到自動＝不留紀錄


def test_all_lab_pages_finish_with_theme_toggle():
    """四支頁面程式（台股市場頁、美股市場頁、配置、研究紀錄）都經過 appnav.finish；主頁（復華雷達）不碰。
    原大神策略頁 x9x.html（2026-10-22 起）、泡沫頁 x9b.html 與訊號總覽 x9o.html（2026-10-23 起）只是轉址頁，不需要頂欄與深淺色。"""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "arm" / "lab"
    for f in ("heatpage.py", "heatpage_us.py", "page.py", "research_page.py"):
        assert "return appnav.finish(_HTML" in (root / f).read_text(encoding="utf-8"), f
    fd = (root.parent / "fund_dashboard.py").read_text(encoding="utf-8")
    assert "appnav" not in fd and "labTheme" not in fd
    viz, sv = (root / "heatviz.py").read_text(encoding="utf-8"), (root / "stockviz.py").read_text(encoding="utf-8")
    assert "addEventListener('labtheme'" in viz and "addEventListener('labtheme',vzTheme)" in sv
