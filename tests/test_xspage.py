"""舊的大神策略頁（arm/lab/xspage.py）：2026-10-22 起只剩轉址頁＋淨值與每一筆（x9xh.json）；
策略頁・總經策略的進入點（景氣頁、訊號總覽）都連到 x9.html#v=mac（docs/lab_strategy_ia_plan.md）。"""
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import xspage as XP
from arm.lab import xstrat as X
from arm.lab import xstratpage as P


@pytest.fixture(scope="module")
def R():
    return X.run_all()


def test_redirect_stub_maps_old_hash_to_strategy_page():
    """舊網址 x9x.html#i=xs:市場:策略 → x9.html#v=mac&m=市場&x=策略；沒有 JS 也會轉（noscript 的 meta refresh）；不需要頂欄。"""
    h = XP.render()
    assert P.HOME == "x9.html#v=mac" and XP.NEW == P.HOME
    js = h[h.index("<script>") + 8:h.index("</script>")]
    assert 'location.hash.match(/^#i=xs:([a-z0-9]+):([a-z0-9]+)$/)' in js and 'u+="&m="+m[1]+"&x="+m[2]' in js
    assert 'location.replace(u)' in js and f'u="{P.HOME}"' in js
    assert f'<noscript><meta http-equiv="refresh" content="0;url={P.HOME}"></noscript>' in h
    assert f'<a href="{P.HOME}">打開策略頁 →</a>' in h and "apptab" not in h and 'name="robots" content="noindex,nofollow"' in h


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_redirect_stub_js_computes_new_url(tmp_path):
    h = XP.render()
    js = h[h.index("<script>") + 8:h.index("</script>")]
    f = tmp_path / "r.js"
    f.write_text("let out=[];for(const hs of ['#i=xs:spx:vixs','','#i=xs:tw:mmr','#s=2330']){const location={hash:hs,replace:u=>out.push(u)};"
                 + js + "}console.log(JSON.stringify(out));", encoding="utf-8")
    r = subprocess.run(["node", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["x9.html#v=mac&m=spx&x=vixs", "x9.html#v=mac", "x9.html#v=mac&m=tw&x=mmr", "x9.html#v=mac"]


def test_build_writes_detail_and_keeps_old_files_when_empty(R, tmp_path, monkeypatch):
    out, data_out = tmp_path / "x9x.html", tmp_path / "x9xh.json"
    V = XP.view(R)
    monkeypatch.setattr(XP, "view", lambda: V)
    assert XP.build(out, data_out) is True
    dj = json.loads(data_out.read_text(encoding="utf-8"))
    assert set(dj) == {f"xs:{mk}:{k}" for mk, M in R.items() for k in M}
    assert all(set(v) == {"eq", "tr", "jd"} for v in dj.values())             # jd＝說明卡的判定依據（xsadvice.judge）
    from arm.lab import xsadvice as XA
    assert all(dj[f"xs:{mk}:{k}"]["jd"] == json.loads(json.dumps(XA.judge(r), ensure_ascii=False)) for mk, M in R.items() for k, r in M.items())
    assert out.read_text(encoding="utf-8") == XP.render()
    assert XP.build(out, data_out) is False                                # 內容沒變不改寫
    monkeypatch.setattr(XP, "view", lambda: {"R": {}})
    e1, e2 = tmp_path / "e.html", tmp_path / "e.json"
    assert XP.build(e1, e2) is False and not e1.exists() and not e2.exists()   # 算不出來就留著上一版


def test_entry_points_link_to_strategy_page(R):
    """景氣頁今天的重點下面一行、10 個月均線與融資維持率兩格、訊號總覽的面板與說明都連到策略頁・總經策略。"""
    from arm.lab import heatviz as VZ
    from arm.lab import sigpage as SP
    line = P.summary_line("tw", R)
    q = P.summary("tw", R)
    assert line.startswith('<a href="x9.html#v=mac&amp;m=tw">') and f"總經策略 {q['n']} 條" in line and f"★ 好策略 {q['good']} 條" in line
    assert q["n"] == len(R["tw"]) and P.summary("tw", {}) is None and P.summary_line("tw", {}) == ""
    assert P.link("spx") == "x9.html#v=mac&m=spx" and P.link("tw", "mmr") == "x9.html#v=mac&m=tw&x=mmr"
    T = {"up": [], "warn": [], "d": "2026-10-21", "thermo": []}
    h = VZ.today_html({"sigtoday": T, "xsl": line})
    h0 = VZ.today_html({"sigtoday": T})
    assert f'<p class="tzm">{line}</p>' in h and "x9.html#v=mac" not in h0
    assert 'href="x9.html#v=mac&amp;m=tw&amp;x=faber"' in P.chip("tw", R) and 'href="x9.html#v=mac&amp;m=tw&amp;x=mmr"' in P.mr_chip("tw", R)
    assert "在策略頁看" in P.PANEL_JS and "XSHOME" not in P.PANEL_JS and "XSHOME" not in SP.JS
    assert "x9.html#v=mac&amp;m='" in P.PANEL_JS
    assert 'href="x9.html#v=mac">策略頁的總經策略</a>' in SP.method_html()
    for src in (SP.JS, SP.method_html(), P.PANEL_JS, line):
        assert "x9x.html" not in src and "大神策略頁" not in src


def test_overview_today_list_has_one_strategy_line_per_market(R):
    """訊號總覽「今天有效的好訊號」：總經策略每個市場縮成一行，連到策略頁那個市場；卡片裡只列訊號。"""
    from arm.lab import sigpage as SP
    asof = {mk: max(r["now"]["d"] for r in M.values()) for mk, M in R.items() if M}
    V = {"today": {mk: {"good": []} for mk in asof}, "asof": dict(asof), "xs": R, "stk": []}
    h = SP.today_html(V)
    assert len(re.findall(r'<p class="sgxs"><a href="x9\.html#v=mac&amp;m=\w+">總經策略', h)) == len(asof) and "策略・" not in h
    for mk in asof:
        its = P.board(mk, R)
        line = P.today_line(mk, R)
        assert line in h
        assert all(f"{it['name']} {P.TAG[it['st']]}" in line for it in its)
        assert ("看每一條現在持有還是空手" in line) == (not its)
    assert P.today_line("tw", {}) == ""
