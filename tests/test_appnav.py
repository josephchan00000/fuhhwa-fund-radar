"""景氣與個股共用的頂欄（arm/lab/appnav.py；docs/lab_heat_us_plan.md 第 7 節）。"""
from arm.lab import appnav, heatpage, heatpage_us, page


def test_bar_marks_the_current_page():
    tw = appnav.bar("tw")
    assert tw.startswith('<nav class="apptab"') and tw.count("<a") == len(appnav.TABS)
    assert '<a class="on" aria-current="page" href="x9m.html">台股景氣</a>' in tw
    assert '<a href="x9.html">個股</a>' in tw
    stk = appnav.bar("stk")
    assert '<a class="on" aria-current="page" href="x9.html">個股</a>' in stk and '<a href="x9m.html">台股景氣</a>' in stk
    assert [k for k, _, _ in appnav.TABS] == ["tw", "us", "bub", "stk", "sig"]   # 景氣排第一個（點「·」先到景氣頁）；泡沫獨立一頁；訊號總覽最後
    assert '<a class="on" aria-current="page" href="x9o.html">訊號總覽</a>' in appnav.bar("sig")
    bub = appnav.bar("bub")
    assert '<a class="on" aria-current="page" href="x9b.html">泡沫</a>' in bub and '<a href="x9.html">個股</a>' in bub
    us = appnav.bar("us")
    assert '<a class="on" aria-current="page" href="x9mu.html">美股景氣</a>' in us and '<a href="x9m.html">台股景氣</a>' in us


def test_both_pages_use_the_shared_bar_and_back_link():
    lab = page.render({"etfs": {}, "asof": {}})
    assert appnav.bar("stk") in lab and appnav.CSS in lab
    assert '<a class="back" href="./">返回主頁</a>' in lab and "<b>籌碼雷達</b>" not in lab
    from arm.lab import bubpage, sigpage
    for tpl in (page._HTML, heatpage._HTML, heatpage_us._HTML, bubpage._HTML, sigpage._HTML):
        top = tpl.split('<div class="top">', 1)[1].split("</div>", 1)[0]
        assert top.startswith("{{APPTAB}}") and 'href="./">返回主頁' in top
        assert 'class="back" href="x9' not in top                              # 舊的小字互連拿掉，改由主分頁切換


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
            '<div class="top"><nav></nav><a class="back" href="./">返回主頁</a></div></body></html>')
    f = A.finish(page)
    head = f[:f.index("</head>")]
    assert ':root[data-theme="dark"]{--bg:#000}' in head and A.THEME_CSS in head and A.THEME_HEAD in head
    assert head.index("</style>") < head.index(A.THEME_HEAD)
    assert f.count('id="thm"') == 1 and f.index('id="thm"') < f.index('<a class="back"')
    assert '"labTheme"' in A.THEME_HEAD and '["auto","light","dark"]' in A.THEME_HEAD and 'new Event("labtheme")' in A.THEME_HEAD
    assert "localStorage.removeItem(K)" in A.THEME_HEAD                             # 回到自動＝不留紀錄


def test_all_lab_pages_finish_with_theme_toggle():
    """五頁（台股景氣、美股景氣、泡沫、個股、訊號總覽）都經過 appnav.finish；主頁（復華雷達）不碰。"""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "arm" / "lab"
    for f in ("heatpage.py", "heatpage_us.py", "bubpage.py", "sigpage.py", "page.py"):
        assert "return appnav.finish(_HTML" in (root / f).read_text(encoding="utf-8"), f
    fd = (root.parent / "fund_dashboard.py").read_text(encoding="utf-8")
    assert "appnav" not in fd and "labTheme" not in fd
    viz, sv = (root / "heatviz.py").read_text(encoding="utf-8"), (root / "stockviz.py").read_text(encoding="utf-8")
    assert "addEventListener('labtheme'" in viz and "addEventListener('labtheme',vzTheme)" in sv
