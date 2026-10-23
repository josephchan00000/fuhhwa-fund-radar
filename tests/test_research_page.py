"""研究紀錄頁（arm/lab/research_page.py；docs/lab_ia_v5_plan.md 第 7 節）：不在頂欄、配置頁頁尾小字進；
每一個連到 x9.html 的項目都對得到 x9.html 裡的分頁與段落；建頁接進 gen_fund_dashboard 與三支 workflow。"""
import re
from pathlib import Path

from arm.lab import appnav, cfgpage, page
from arm.lab import research_page as RP

ROOT = Path(__file__).resolve().parents[1]


def test_page_has_toc_groups_and_shared_bar():
    h = RP.render()
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
    assert RP.build(out) is True and RP.build(out) is False                      # 內容沒變不改寫
    gen = (ROOT / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")
    assert "research_page.build()" in gen and gen.index("sigpage.build()") < gen.index("lab_page.finish()") < gen.index("research_page.build()")
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9r.html 2>/dev/null || true") == 2, wf
