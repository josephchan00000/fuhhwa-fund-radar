"""研究紀錄頁（arm/lab/research_page.py；docs/lab_ia_v5_plan.md 第 7 節）：不在頂欄、配置頁頁尾小字進；
每一個連到 x9.html 的項目都對得到 x9.html 裡的分頁與段落；建頁接進 gen_fund_dashboard 與三支 workflow。"""
import re
from pathlib import Path

from arm.lab import appnav, cfgpage, page
from arm.lab import research_page as RP

ROOT = Path(__file__).resolve().parents[1]


EMPTY = {"SV": {"rows": []}, "BV": {"M": {}}}                                  # 不算真的研究（測試用空的 view）


def test_page_has_toc_groups_and_shared_bar():
    h = RP.render(**EMPTY)
    assert h.startswith("<!doctype html>") and "<title>研究紀錄</title>" in h
    assert appnav.bar("") in h and 'aria-current="page"' not in h.split("</nav>", 1)[0]   # 不在頂欄：沒有一格亮
    assert 'id="thm"' in h                                                        # 深淺色按鈕（appnav.finish）
    for gid, title, _, items in RP.GROUPS:
        assert f'<section class="rsec" id="{gid}"><h2>{title}</h2>' in h and f'<a href="#{gid}">{title}</a>' in h
        for n, u, _ in items:
            assert f'<a href="{u.replace("&", "&amp;")}">{n}</a>' in h, n
    assert "x9r.html" not in appnav.bar("cfg")                                     # 頂欄不放研究紀錄


def test_links_into_x9_match_views_and_sections():
    J = page._JS
    views = set(re.search(r"const VIEWS=\{([^}]*)\}", J).group(1).replace(" ", "").split(","))
    views = {v.split(":")[0] for v in views}
    for _, _, _, items in RP.GROUPS:
        for n, u, _ in items:
            if not u.startswith("x9.html"):
                continue
            q = dict(x.split("=", 1) for x in u.split("?", 1)[1].split("#")[0].split("&"))
            assert q["v"] in views and q["v"] in ("opp", "st", "mac", "macst", "bo"), (n, u)   # 研究紀錄身分的分頁
            if "at" in q:
                assert f"sec('{q['at']}'" in J, (n, q["at"])                        # 段落 id 真的存在
    assert "at=q.get('at')||undefined" in J and "gl=location.hash==='#gl'" in J and "go(v,at);if(gl)openGl();}" in J   # 改寫網址前先記下


def test_cfg_footer_links_here_and_research_tabs_link_back():
    assert '<a href="x9r.html">研究紀錄</a>' in cfgpage.JS
    assert '<a class="rbk" href="x9r.html" data-p="r" hidden>‹ 研究紀錄</a>' in page._HTML


def test_build_writes_once_and_is_wired(tmp_path):
    out = tmp_path / "x9r.html"
    assert RP.build(out, **EMPTY) is True and RP.build(out, **EMPTY) is False    # 內容沒變不改寫
    gen = (ROOT / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")
    assert "research_page.build()" in gen and gen.index("sigpage.build()") < gen.index("lab_page.finish()") < gen.index("research_page.build()")
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9r.html 2>/dev/null || true") == 2, wf


def test_hosts_signal_and_bubble_research(monkeypatch):
    """第 2 段（docs/lab_ia_v5_plan.md 第 7 節）：原本訊號總覽的研究（研究結論、完整研究表、全部指標、名詞與判定方式）與
    原本泡沫頁的全部內容放在這頁；全部指標的面板、資料與程式也在這頁（個股訊號的 #s=stk:sig:… 從籌碼頁連過來）。"""
    from arm.lab import bubindpage as IP
    from arm.lab import bubpage as BPG
    from arm.lab import sigpage as SPG
    monkeypatch.setattr(SPG, "research_body", lambda V: '<section class="sec" id="research">研究結論</section><section id="all"></section><section id="mth"></section>')
    monkeypatch.setattr(SPG, "page_json", lambda V: '{"rows":[1]}')
    monkeypatch.setattr(BPG, "research_body", lambda V: '<section class="sec" id="bub-lv">五個市場</section>')
    monkeypatch.setattr(BPG, "research_data", lambda V: '{"tw":{}}')
    h = RP.render(SV={"rows": [1]}, BV={"M": {"tw": {}}})
    sig, bub, gl = h.index('<section class="rsec" id="sig">'), h.index('<section class="rsec" id="bub">'), h.index('<section class="rsec" id="gl">')
    assert sig < h.index('<div class="rhost" data-g="sig">') < h.index('id="research"') < bub < h.index('id="bub-lv"') < gl
    assert '<script type="application/json" id="sgd">{"rows":[1]}</script>' in h and SPG.PANEL in h
    assert '<script type="application/json" id="bubd">{"tw":{}}</script>' in h
    js = h[h.rindex("<script>"):]
    assert SPG.JS[:200] in js and BPG.JS[:200] in js and IP.JS[:120] in js
    for rule in (".sgch{", ".btg{", "table.bind tr.bir{", ".rhost{"):               # 訊號研究、泡沫、產業表、這頁自己的樣式
        assert rule in h, rule
    for u in ("#research", "#rfull", "#all", "#mth", "#bub-lv", "#bub-ind", "#bub-types", "#bub-mth"):
        assert f'href="{u}"' in h, u                                                 # 目錄連到這頁的段落
    e = RP.render(**EMPTY)
    assert 'id="sgd"' not in e and SPG.PANEL not in e                                # 還沒有研究結果：不放全部指標的程式


def test_empty_research_shows_warnings():
    e = RP.render(**EMPTY)
    assert "還沒有研究結果" in e and "泡沫等級還算不出來" in e


def test_market_research_links_point_at_market_page_research_views():
    """景氣頁的研究畫面（證據地圖、階段時間軸、熱度地形）留在市場頁（資料在那裡），這頁只列入口。"""
    mkt = dict((n, u) for gid, _, _, items in RP.GROUPS if gid == "mkt" for n, u, _ in items)
    assert set(mkt.values()) == {"x9m.html#v=research", "x9m.html#v=phase", "x9m.html#v=terrain",
                                 "x9mu.html#ix=spx&v=research", "x9mu.html#ix=spx&v=phase", "x9mu.html#ix=spx&v=terrain"}
    from arm.lab import heatviz as VZ
    for v in ("research", "phase", "terrain"):
        assert f'data-goview="{v}"' in VZ.research_bar(v) and '<a class="rbk" href="x9r.html">‹ 研究紀錄</a>' in VZ.research_bar(v)
    assert all("x9o.html" not in u and "x9b.html" not in u for _, _, _, items in RP.GROUPS for _, u, _ in items)
