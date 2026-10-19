"""櫃買產業鏈平台解析（arm/lab/icchain.py）。樣本照 2026-10-19 探針看到的版式。"""
from arm.lab import icchain as IC

HOME = ('<a href="introduce.php?ic=D000" class="x">半導體</a><a href="introduce.php?ic=L000">印刷<br>電路板</a>'
        '<a href="introduce.php?ic=D000">半導體</a>')

NODE = ('<div id="companyList_{nid}" title="{t}" class="x-hidden"><div class="company-list"><table><tr>'
        "<td class='company' rowspan='1.4'><b>本國上市公司(2家)</b></td><td class=\"company\">"
        '<span class="ic-sprite"></span>&nbsp;<a href="company_basic.php?stk_code=2330">2330 台積電</a>'
        '&nbsp;<a href="company_basic.php?stk_code=2303">2303 聯電</a>'
        '&nbsp;<a href="company_basic.php?stk_code=2330">2330 台積電</a></td></tr>'
        "<tr><td><b>本國上櫃公司(1家)</b></td><td><a href=\"company_basic.php?stk_code=6488\">6488</a></td></tr>"
        "<tr><td><b>知名外國企業(1家)</b></td><td>Intel</td></tr></table></div></div>")
TAB = ('<div id="companyList_D200" title="IC設計" class="x-hidden"><b>&nbsp;LED驅動IC&nbsp;(2家)</b>'
       '<a href="company_basic.php?stk_code=3438">x</a><a href="company_basic.php?stk_code=34380">y</a>'
       '<b>&nbsp;光通訊IC&nbsp;（1家）</b><a href="company_basic.php?stk_code=3081">z</a></div>')


def test_parse_home_dedupes_and_cleans():
    assert IC.parse_home(HOME) == [("D000", "半導體"), ("L000", "印刷電路板")]


def test_parse_chain_nodes_segments_and_duplicates():
    h = "<div>圖</div>" + NODE.format(nid="D100", t="IC/晶圓製造") + TAB + NODE.format(nid="D100", t="IC/晶圓製造")
    nodes = IC.parse_chain(h)
    assert [n[:2] for n in nodes] == [["D100", "IC/晶圓製造"], ["D200", "IC設計"]]
    segs = nodes[0][2]
    assert segs[0] == ["本國上市公司", 2, ["2330", "2303"]]
    assert segs[1] == ["本國上櫃公司", 1, ["6488"]]
    assert segs[2] == ["知名外國企業", 1, []]
    tab = nodes[1][2]
    assert tab[0] == ["LED驅動IC", 2, ["3438"]]           # 5 碼不算代號
    assert tab[1] == ["光通訊IC", 1, ["3081"]]


def test_node_codes_filters_labels():
    nd = IC.parse_chain(NODE.format(nid="X", t="t"))[0]
    assert IC.node_codes(nd) == {"2330", "2303", "6488"}
    assert IC.node_codes(nd, ("本國上櫃公司",)) == {"6488"}


def test_stale_rule():
    assert IC.stale({}, "2026-10-19")
    doc = {"d": "2026-10-01", "chains": {"D000": {}}}
    assert not IC.stale(doc, "2026-10-19")
    assert IC.stale(doc, "2026-10-31")
