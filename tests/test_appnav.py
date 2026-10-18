"""景氣與個股共用的頂欄（arm/lab/appnav.py；docs/lab_heat_us_plan.md 第 7 節）。"""
from arm.lab import appnav, heatpage, heatpage_us, page


def test_bar_marks_the_current_page():
    tw = appnav.bar("tw")
    assert tw.startswith('<nav class="apptab"') and tw.count("<a") == len(appnav.TABS)
    assert '<a class="on" aria-current="page" href="x9m.html">台股景氣</a>' in tw
    assert '<a href="x9.html">個股</a>' in tw
    stk = appnav.bar("stk")
    assert '<a class="on" aria-current="page" href="x9.html">個股</a>' in stk and '<a href="x9m.html">台股景氣</a>' in stk
    assert [k for k, _, _ in appnav.TABS] == ["tw", "us", "bub", "stk"]        # 景氣排第一個（點「·」先到景氣頁）；泡沫獨立一頁
    bub = appnav.bar("bub")
    assert '<a class="on" aria-current="page" href="x9b.html">泡沫</a>' in bub and '<a href="x9.html">個股</a>' in bub
    us = appnav.bar("us")
    assert '<a class="on" aria-current="page" href="x9mu.html">美股景氣</a>' in us and '<a href="x9m.html">台股景氣</a>' in us


def test_both_pages_use_the_shared_bar_and_back_link():
    lab = page.render({"etfs": {}, "asof": {}})
    assert appnav.bar("stk") in lab and appnav.CSS in lab
    assert '<a class="back" href="./">返回主頁</a>' in lab and "<b>籌碼雷達</b>" not in lab
    from arm.lab import bubpage
    for tpl in (page._HTML, heatpage._HTML, heatpage_us._HTML, bubpage._HTML):
        top = tpl.split('<div class="top">', 1)[1].split("</div>", 1)[0]
        assert top.startswith("{{APPTAB}}") and 'href="./">返回主頁' in top
        assert 'class="back" href="x9' not in top                              # 舊的小字互連拿掉，改由主分頁切換
