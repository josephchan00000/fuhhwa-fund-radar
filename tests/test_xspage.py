"""大神策略頁（arm/lab/xspage.py；docs/lab_nav_plan.md）：接下來要做的、全部策略的總表、共用的面板、資料檔與入口。"""
import html
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import appnav
from arm.lab import xspage as XP
from arm.lab import xstrat as X
from arm.lab import xstratpage as P
from arm.lab import xstratspec as S

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


@pytest.fixture(scope="module")
def R():
    return X.run_all()


def _visible(h):
    return re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", h)


def test_page_sections_matrix_and_nav(R):
    V = XP.view(R)
    h = XP.render(V)
    assert appnav.bar("xs") in h and "<title>大神策略</title>" in h
    for sid in ("next", "all", "mth", "more"):
        assert f'<section class="sec" id="{sid}">' in h, sid
    n = 0
    for mk in S.MARKETS:
        for k in R.get(mk) or {}:
            assert f'data-k="xs:{mk}:{k}"' in h and f'href="#i=xs:{mk}:{k}"' in h, (mk, k)
            n += 1
    mks = [mk for mk in S.MARKETS if mk in V["asof"]]
    shown = [s for s in S.STRATS if any(s["k"] in (R.get(mk) or {}) for mk in mks)]
    assert h.count('class="xpc xpna"') == len(shown) * len(mks) - n          # 那個市場沒有這種資料的格子
    for g in S.GROUP_ORDER:
        assert f'{S.GROUPS[g]}<span>{XP.GRP_TXT[g]}</span>' in h
    assert not [w for w in BANNED if w in _visible(h)]
    data = json.loads(h.split('<script type="application/json" id="xsd">', 1)[1].split("</script>", 1)[0].replace("<\\/", "</"))
    assert data == json.loads(json.dumps(P.payload(R), ensure_ascii=False))
    assert "@@XSPANEL" not in h and "function xsPanel" in h
    assert "XSHOME = true" in h                                             # 大神策略頁自己不放「在大神策略頁看」的連結
    for mk in V["asof"]:
        assert f'>{html.escape(P.MK_NAMES[mk])}<span class="sub">資料到' in h  # 現在的部位：每個市場一張卡


def _r(k, tier, st, **now):
    return {"k": k, "kind": S.BY_KEY[k]["kind"], "tier": tier, "now": {"st": st, "d": "2026-10-21", "nx": "2026-10-22", **now}}


def test_plan_lists_actions_soon_and_positions():
    """要做的＝★、● 有訊號或 14 天內排定要買賣（依日期排）；現在的部位＝★、● 有部位、沒列在上面的；判定沒過的另外收起來。"""
    R = {"tw": {"rsi2": _r("rsi2", "good", "near", hi_px=1.0, lo_px=0.9),
                "tom": _r("tom", "ref", "wait", ed="2026-10-29", qd="2026-11-04"),
                "hal": _r("hal", "ref", "out", sw="2026-12-30"),
                "faber": _r("faber", "good", "in"),
                "coppock": _r("coppock", "good", "hold", qd="2027-05-01"),
                "dev60": _r("dev60", "good", "hold", qd="2026-10-28"),
                "ma200": _r("ma200", "none", "in"),
                "zweig": _r("zweig", "none", "wait")},
         "spx": {"rsi2": _r("rsi2", "good", "sell", nx="2026-10-21"),
                 "vixs": _r("vixs", "ref", "hold"),
                 "mom12": _r("mom12", "few", "turn_out")}}
    Q = XP.plan(R)
    assert [(d, v, mk, k) for d, v, mk, k, _ in Q["todo"]] == [
        ("2026-10-21", "賣", "spx", "rsi2"), ("2026-10-22", "可能買", "tw", "rsi2"),
        ("2026-10-28", "賣", "tw", "dev60"), ("2026-10-29", "買", "tw", "tom")]
    assert [k for k, _ in Q["held"]["tw"]] == ["coppock", "faber"] and [k for k, _ in Q["held"]["spx"]] == ["vixs"]
    assert [(mk, k, d) for mk, k, _, d in Q["low"]] == [("tw", "ma200", None), ("spx", "mom12", "2026-10-22")]
    assert "hal" not in str(Q)                                              # 排定的買進在 14 天以後、現在空手：不列
    assert XP.due(_r("hal", "ref", "in", sw="2027-04-30")) == ("2027-04-30", "賣")
    assert XP.due(_r("tom", "good", "hold", ed="2026-10-20", qd="2026-10-23")) == ("2026-10-23", "賣")
    assert XP.due(_r("rsi2", "good", "wait")) is None and XP.due(_r("faber", "good", "turn_in")) == ("2026-10-22", "買")
    assert [XP.kind_of(st) for st in ("buy", "hold", "in", "wait", "out", "turn_out")] == ["a", "h", "h", "f", "f", "a"]


def test_next_section_renders_real_results(R):
    V = XP.view(R)
    h = XP.next_html(V)
    Q = XP.plan(R)
    for d, verb, mk, k, r in Q["todo"]:
        assert f'href="#i=xs:{mk}:{k}"' in h and f"{XP._mdw(d)}{verb}" in h
        assert r["tier"] in ("good", "ref")
    for mk, it in Q["held"].items():
        for k, r in it:
            assert r["now"]["st"] in P.HELD and r["tier"] in ("good", "ref")
    if Q["low"]:
        assert f'現在有訊號或有部位的 {len(Q["low"])} 條' in h


def test_build_writes_detail_and_keeps_old_files_when_empty(R, tmp_path, monkeypatch):
    out, data_out = tmp_path / "x9x.html", tmp_path / "x9xh.json"
    V = XP.view(R)
    monkeypatch.setattr(XP, "view", lambda: V)
    assert XP.build(out, data_out) is True
    dj = json.loads(data_out.read_text(encoding="utf-8"))
    assert set(dj) == {f"xs:{mk}:{k}" for mk, M in R.items() for k in M}
    assert all(set(v) == {"eq", "tr"} for v in dj.values())
    assert XP.build(out, data_out) is False                                # 內容沒變不改寫
    monkeypatch.setattr(XP, "view", lambda: {"R": {}, "asof": {}})
    e1, e2 = tmp_path / "e.html", tmp_path / "e.json"
    assert XP.build(e1, e2) is False and not e1.exists() and not e2.exists()   # 算不出來就留著上一版


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_js_parses(tmp_path):
    f = tmp_path / "x.js"
    f.write_text(XP.JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_phone_matrix_becomes_blocks():
    css = XP.CSS
    mob = css[css.index("@media (max-width:640px)"):]
    assert ".xpm thead{display:none}" in mob and "grid-template-columns:repeat(5,minmax(0,1fr))" in mob
    assert ".xpc::before{content:attr(data-h)" in mob and ".xpc small{display:none}" in mob
    assert set(XP.MK_SHORT) == set(S.MARKETS) and set(XP.WHO) == {s["k"] for s in S.STRATS}


def test_entry_points_link_to_strategy_page(R):
    """景氣頁今天的重點下面一行、10 個月均線與融資維持率兩格、訊號總覽的面板都連到大神策略頁。"""
    from arm.lab import heatviz as VZ
    from arm.lab import sigpage as SP
    line = P.summary_line("tw", R)
    q = P.summary("tw", R)
    assert line.startswith(f'<a href="{P.HOME}">') and f"大神策略 {q['n']} 條" in line and f"★ 好策略 {q['good']} 條" in line
    assert q["n"] == len(R["tw"]) and P.summary("tw", {}) is None and P.summary_line("tw", {}) == ""
    T = {"up": [], "warn": [], "d": "2026-10-21", "thermo": []}
    orig = VZ.thermo_html
    VZ.thermo_html = lambda T: ""
    try:
        h = VZ.today_html({"sigtoday": T, "xsl": line})
        h0 = VZ.today_html({"sigtoday": T})
    finally:
        VZ.thermo_html = orig
    assert f'<p class="tzm">{line}</p>' in h and P.HOME not in h0
    assert f'href="{P.HOME}#i=xs:tw:faber"' in P.chip("tw", R) and f'href="{P.HOME}#i=xs:tw:mmr"' in P.mr_chip("tw", R)
    assert "在大神策略頁看" in P.PANEL_JS and "if (!XSHOME)" in P.PANEL_JS and "const XSHOME = false;" in SP.JS
    assert 'href="x9x.html">大神策略頁</a>' in SP.method_html()


def test_overview_today_list_has_one_strategy_line_per_market(R):
    """訊號總覽「今天有效的好訊號」：大神策略每個市場縮成一行，連到大神策略頁；卡片裡只列訊號。"""
    from arm.lab import sigpage as SP
    asof = XP.view(R)["asof"]
    V = {"today": {mk: {"good": []} for mk in asof}, "asof": dict(asof), "xs": R, "stk": []}
    h = SP.today_html(V)
    assert h.count('<p class="sgxs"><a href="x9x.html">大神策略') == len(asof) and "策略・" not in h
    for mk in asof:
        its = P.board(mk, R)
        line = P.today_line(mk, R)
        assert line in h
        assert all(f"{it['name']} {P.TAG[it['st']]}" in line for it in its)
        assert ("看每一條現在持有還是空手" in line) == (not its)
    assert P.today_line("tw", {}) == ""
