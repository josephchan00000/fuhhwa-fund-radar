"""訊號總覽頁（arm/lab/sigpage.py；docs/lab_signal_plan.md 第 5 節）。"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from arm.lab import appnav, sigcat, sigpage, sigspec
from arm.lab import xstratspec as XS

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買", "建議賣", "目標價", "零風險", "無風險")


def _st(n, hit, base, tier, n10=0, hit10=None, base10=None):
    return {"n": n, "hit": hit, "base": base, "n10": n10, "hit10": hit10, "base10": base10, "tier": tier}


def _rows():
    a = {"id": "tw:heat:C1:hot", "mk": "tw", "cat": "heat", "grp": "chip", "var": "C1", "vn": "融資餘額水位", "sig": "hot",
         "name": "融資餘額水位・過熱中", "kind": "state", "H": 60, "th": 0.10, "a": "2001-01-02", "z": "2026-10-16",
         "up": _st(12, 0.70, 0.66, "none"), "warn": dict(_st(12, 0.58, 0.29, "good"), mdd=0.124, mdd_base=0.067),
         "tier": "good", "dir": ["warn"], "occ": [["2020-01-02", "2020-03-01", 40, 0.5, 0.8, 0.11]]}
    b = dict(a, id="tw:heat:C1:hot_in", sig="hot_in", name="融資餘額水位・進入過熱", kind="event",
             up=_st(13, 0.85, 0.66, "good"), warn=_st(13, 0.40, 0.29, "ref"), dir=["up"], occ=[["2020-01-02", 1, 0, 0.05]])
    c = dict(a, id="tw:tech:ma60_dn", cat="tech", grp="tech", var="ma60_dn", vn="跌破季線", sig="ev", name="跌破季線",
             kind="event", H=20, th=0.08, up=_st(40, 0.5, 0.55, "none"), warn=_st(40, 0.2, 0.16, "none"), tier="none",
             dir=["up"], occ=[])
    s = {"id": "stk:strat:s5", "mk": "stk", "cat": "strat", "grp": "strat", "var": "s5", "vn": "長線", "sig": "s5",
         "name": "長線：投信動能成長股", "desc": "月選", "kind": "trade", "H": None, "up": _st(30, 0.53, 0.87, "good"),
         "tier": "good", "dir": ["up"], "pay": {"n": 30, "win": 53.3, "ratio": float("inf"), "m": 6.76, "avg": 26.3,
                                                 "ok": True, "path": "上漲空間大"}, "old": "B", "occ": []}
    return [a, b, c, s]


def _view():
    rows = _rows()
    on = {"tw:heat:C1:hot": {"since": "2025-12-01", "n": 200}, "tw:heat:C1:hot_in": {"since": "2026-10-01", "n": 11, "left": 49}}
    return {"rows": rows, "on": on, "today": {"tw": sigcat.today(rows, on, "tw")}, "stk": [rows[3]],
            "asof": {"tw": "2026-10-16", "stk": "2026-10-19"}, "run": None, "last": {}}


def test_today_one_row_per_variable_sorted_by_edge():
    V = _view()
    T = V["today"]["tw"]
    assert [r["id"] for r in T["good"]] == ["tw:heat:C1:hot"]           # 同一個變數只留差最大的（警示 +29 > 偏多 +19）
    assert T["good"][0]["d"] == "warn" and abs(T["good"][0]["edge"] - 0.29) < 1e-9 and "ref" not in T   # VER 9：沒有 ★ 不補 ●
    assert sigcat.today(V["rows"], {}, "tw") == {"good": [], "rare": []}                      # VER 17：◆ 另列


def test_render_structure_and_data(monkeypatch):
    monkeypatch.setattr(sigpage.OOS, "load", lambda path=None: None)           # 預估之後另外測（test_forward_estimate_*）
    html = sigpage.render(_view())
    assert appnav.bar("sig") in html and "<title>訊號總覽</title>" in html
    for sid in ('id="today"', 'id="all"', 'id="mth"', 'id="sgq"', 'id="sgcsv"', 'id="sgnow"'):
        assert sid in html
    assert "融資餘額水位・過熱中" in html and "之後 3 個月內大跌（最大回撤 10% 以上）的機率 <b>58%</b>（隨便挑一天 29%）・出現過 12 次" in html
    assert "回撤中位數 12%（隨便挑一天 7%）" in html and "最大回撤" in html.split('id="mth"')[1]           # VER 3
    # 白話用語（docs/lab_sigview_plan.md 第 2.3 節）：表頭與名詞說明不再用「命中率／平常」
    vis = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    assert "命中率" not in vis and "平常" not in re.sub(r"<[^>]+>", "", vis.split('id="mth"')[0])
    for w in ("之後上漲的機率", "之後大跌的機率", "隨便挑一天", "多幾個百分點", "近 10 年也成立嗎", "出現過幾次"):
        assert w in html.split('id="mth"')[1], w
    assert 'id="sgpv"' in html and 'id="sgtip"' in html and 'data-tip="now"' in html
    assert "12/1 起" in html and "inf" not in html.split('id="all"')[0] and "每月平均 +6.8%・30 筆" in html
    data = json.loads(re.search(r'<script type="application/json" id="sgd">(.*?)</script>', html, re.S).group(1))
    assert len(data["rows"]) == 4 and all(len(r) == 16 for r in data["rows"])
    assert data["rows"][3][15]["pay"]["ratio"] is None                    # inf 不能進 JSON
    assert data["on"]["tw:heat:C1:hot_in"] == {"since": "2026-10-01", "n": 11, "left": 49}
    assert "const I = {id:0,mk:1,cat:2,grp:3,name:4,kind:5,H:6,th:7,tier:8,dir:9,up:10,warn:11,buy:12,a:13,z:14,x:15};" in sigpage.JS
    det = json.loads(sigpage.detail_json(_view()))
    assert det["occ"]["tw:heat:C1:hot"] == [["2020-01-02", "2020-03-01", 40, 0.5, 0.8, 0.11]]


def test_indicators_group_signals_by_item():
    """依指標整理（docs/lab_sigview_plan.md 第 2.1 節）：同一個景氣項目的水準與邊際變化同一個指標；面向、泡沫、產業、買點各自分組。"""
    rows = _rows()
    a = rows[0]
    d1 = dict(a, id="tw:deriv:C1:1", cat="deriv", grp="deriv", sig="1", name="融資餘額水位・成長加速")
    dm = dict(a, id="tw:heat:Dchip:hot", var="Dchip", grp="chip", vn="籌碼熱度", name="籌碼熱度・過熱中")
    bb = [dict(a, id=f"tw:bub:{k}", cat="bub", grp="bub", var=k, vn=k, name=k, kind="state") for k in ("L2", "P1")]
    by = dict(a, id="tw:buy:E5:W10", cat="buy", grp="E5", var="W10", vn="固定等 10 天", name="5 日急跌・固定等 10 天")
    ind = dict(a, id="ind:ff:L2", mk="us", cat="ind", grp="ff", var="L2", vn="美股 49 細產業", name="美股 49 細產業・泡沫等級 2 以上")
    rs = [d1] + rows + [dm] + bb + [by, ind]
    out = {x[0]: x for x in sigpage.indicators(rs)}
    c1 = out["tw:C1"]
    assert c1[2] == "heat" and c1[3] == "融資餘額水位" and c1[4] == "chip" and c1[6] == "C1"     # 面向取水準那一列（deriv 那一列是 deriv）
    assert [rs[i]["id"] for i in c1[5]] == ["tw:deriv:C1:1", "tw:heat:C1:hot", "tw:heat:C1:hot_in"]
    assert out["tw:Dchip"][2] == "dim" and out["tw:Dchip"][6] == "Dchip"
    assert out["tw:tech:ma60_dn"][2] == "tech" and out["tw:tech:ma60_dn"][6] is None
    cw = sigpage.indicators([dict(a, id="tw:crash:W1:hot", cat="crash", grp="crash", var="W1", vn="融資 ÷ 上市市值（月底）")])[0]
    assert cw[:4] == ["tw:W1", "tw", "crash", "融資 ÷ 上市市值（月底）"] and cw[6] == "W1"   # 現在的值在 ITEMS（sigcat.crash_now）
    assert len(out["tw:bub"][5]) == 2 and out["tw:bub"][3] == "泡沫等級與條件"
    assert out["tw:buy:E5"][3] == "5 日急跌" and out["ind:ff"][1] == "us" and out["stk:strat:s5"][2] == "strat"
    assert set(sigpage.CHART) == set(sigpage.TODAY_MK) and sigpage.CHART["tw"] == "x9mh.json"
    j = json.loads(sigpage.page_json(_view()))
    assert [x[0] for x in j["inds"]] == ["tw:C1", "tw:tech:ma60_dn", "stk:strat:s5"]
    assert j["dimn"]["tw"]["chip"] and j["dimn"]["spx"]["sent"] and j["hit"] == {"up": 60, "warn": 50, "buy": 60}


def test_no_banned_words_and_no_class_collisions():
    html = sigpage.render(_view())
    txt = re.sub(r"<[^>]+>", "", html)
    for w in BANNED:
        assert w not in txt, w
    from arm.lab.heatpage import _CSS as HCSS
    mine = set(re.findall(r"\.(sg[a-z0-9-]*)", sigpage.CSS))
    assert mine and all(not re.search(r"\." + re.escape(c) + r"\b", HCSS) for c in mine)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_js_parses(tmp_path):
    f = tmp_path / "s.js"
    f.write_text(sigpage.JS, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_workflows_add_overview_files_and_build_order():
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9o.html 2>/dev/null || true") == 2, wf
        assert t.count("git add -f dashboard/x9oh.json 2>/dev/null || true") == 2, wf
        assert t.count("git add -f dashboard/x9or-*.json 2>/dev/null || true") == 2, wf
        assert t.count("git add -f dashboard/x9x.html 2>/dev/null || true") == 2, wf      # 大神策略頁（docs/lab_nav_plan.md）
        assert t.count("git add -f dashboard/x9xh.json 2>/dev/null || true") == 2, wf
    g = (ROOT / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")
    assert (g.index("heatpage.build()") < g.index("heatpage_us.build()") < g.index("bubpage.build()") < g.index("sigpage.build()")
            < g.index("xspage.build()"))


def test_research_file_matches_spec_version():
    R = sigcat.load_research()
    assert R is not None and sigspec.RES_VER <= R["ver"] <= sigspec.VER     # 研究檔不比最後一次改到研究內容的版本舊
    ids = [r["id"] for r in R["rows"]]
    assert len(ids) == len(set(ids)) and len(ids) > 1500
    for r in R["rows"]:
        assert r["tier"] in sigspec.TIERS
        for d in r["dir"]:
            assert d in sigspec.DIRS and r[d]["tier"] == r["tier"]


def test_research_cards_move_to_overview(tmp_path, monkeypatch):
    """景氣頁的四張研究卡 2026-10-19 起搬到這裡（docs/lab_signal_plan.md 第 10 節 Q3）：每個市場一個檔、點了才載入，空的卡不放。"""
    c = {"d": "2026-10-16", "crash": "<section>A</section>", "bottom": "", "hotdd": "<section>C</section>", "hotch": "<section>D</section>"}
    j = json.loads(sigpage.card_json("tw", c))
    assert j["mk"] == "tw" and j["d"] == "2026-10-16"
    assert re.findall(r'<details class="sgrc" id="rc-(\w+)">', j["html"]) == ["crash", "hotdd", "hotch"]
    assert "<summary>短線大跌風險</summary><section>A</section>" in j["html"]
    r = sigpage.research_html(dict(_view(), rmk=["tw", "spx"]))
    assert 'id="research"' in r and 'data-r="tw"' in r and 'data-r="spx"' in r and 'id="rbox"' in r
    assert sigpage.research_html(_view()) == ""
    monkeypatch.setattr(sigpage, "CARDS", {"tw": c})
    monkeypatch.setattr(sigpage, "view", lambda: dict(_view(), rmk=["tw"]))
    out, data_out = tmp_path / "x9o.html", tmp_path / "x9oh.json"
    assert sigpage.build(out, data_out) is True
    assert (tmp_path / "x9or-tw.json").read_text(encoding="utf-8") == sigpage.card_json("tw", c)
    assert 'id="research"' in out.read_text(encoding="utf-8")
    assert sigpage.build(out, data_out) is False                           # 內容沒變不改寫


def test_heat_pages_stash_cards_and_list_today(monkeypatch):
    """景氣頁照樣算四張卡、存給訊號總覽；頁面只列「今天的重點」（訊號總覽的實務判定）。"""
    from arm.lab import heatviz as VZ
    monkeypatch.setattr(sigpage, "CARDS", {})
    VZ.stash_cards({"mk": "spx", "asof": "2026-10-16"})
    assert sigpage.CARDS == {"spx": {"d": "2026-10-16", "crash": "", "bottom": "", "hotdd": "", "hotch": ""}}
    VZ.stash_cards({"mk": None, "asof": "2026-10-16"})                     # 不知道哪個市場就不存
    assert list(sigpage.CARDS) == ["spx"]
    assert "還沒產生" in VZ.today_html({"sigtoday": None})
    V = _view()
    T = dict(sigcat.board(V["rows"], V["on"], "tw"), d="2026-10-16")
    h = VZ.today_html({"sigtoday": T})
    assert 'href="x9o.html#s=tw:heat:C1:hot"' in h and "融資餘額水位・過熱中" in h
    assert "12/1 起" in h and 'href="x9o.html"' in h
    # VER 3：兩個方向各看各的——同一個項目（融資 C1、看 3 個月）偏多 ★、警示 ★ 兩欄都列、標「震盪」
    assert 'href="x9o.html#s=tw:heat:C1:hot_in"' in h and h.count('class="tzo"') == 2
    assert "最大回撤 10% 以上" in h and "回撤中位數 12%（隨便挑一天 7%）" in h
    assert h.count('<div class="tzr">') == 3 and "中線" in h and "差不多" in h and "警示 ★1" in h
    assert 'aria-label="中線（看 3 個月）：偏多 ★1・警示 ★1，偏多占 50%"' in h
    assert 'aria-label="短線（看 1 個月）：中性，沒有偏多或警示的訊號"' in h and "偏多占比只是數一數現在成立的訊號，本身沒有驗證過" in h
    assert "每支溫度計下面兩行是用之前的資料逐年檢查的結果" in h                    # VER 16
    h0 = VZ.today_html({"sigtoday": dict(sigcat.board(V["rows"], {}, "tw"), d="2026-10-16")})
    assert "現在沒有可靠的警示訊號" in h0 and h0.count('class="tzw tzw-none">中性') == 3 and 'class="tzq"' not in h0
    # VER 17：◆ 難得機會不列在兩欄，列在下面「難得機會」一區，溫度計算 1；偏多 70%／平常 66% 的 ○＝△ 勝率過了（算 0.5）
    low = dict(V["rows"][0], warn=_st(12, 0.58, 0.29, "rare"), tier="rare")
    h1 = VZ.today_html({"sigtoday": dict(sigcat.board([low], V["on"], "tw"), d="2026-10-16")})
    main, rz = h1.split('<div class="tzrare">')
    assert "融資餘額水位・過熱中" not in main.split('class="tzcols"')[1] and "機率較低" not in h1
    assert "融資餘額水位・過熱中" in rz and "難得機會" in rz and 'href="x9o.html#s=tw:heat:C1:hot"' in rz
    assert 'aria-label="中線（看 3 個月）：偏多 △1・警示 ◆1，偏多占 33%"' in h1 and "偏警示" in h1
    q = h1.split('<details class="tzq">')[1].split("</details>")[0]
    assert "△ 勝率過了 1 類" in q and "融資餘額水位・過熱中" in q
    assert "亂排" in h and "大盤本身" in h and "警示類過去的事後驗證比偏多弱" in h


def test_board_sides_thermometer_and_one_item_once():
    """景氣頁「今天的重點」（sigspec 第 5 節）：VER 9 起只列 ★，分偏多、警示；同一個項目只算一次（水準與邊際變化同一個）；
    溫度計依看多久三支（VER 17：★ 2、◆ 1、△ 0.5）；◆ 不列在兩欄、另列「難得機會」；個股訊號才有的 ● 不算。"""
    rows = _rows()
    a = rows[0]
    d1 = dict(a, id="tw:deriv:C1:1", cat="deriv", sig="1", name="融資餘額水位・成長加速", up=_st(30, 0.9, 0.5, "good"),
              warn=_st(30, 0.1, 0.3, "none"), tier="good", dir=["up"])           # 同一個項目（C1）：差 +40 > 進入過熱的 +19
    e = dict(a, id="tw:tech:x", cat="tech", var="x", name="站回季線", H=20, up=_st(12, 0.66, 0.6, "rare"),
             warn=_st(12, 0.1, 0.2, "none"), tier="rare", dir=["up"])            # ◆：不列在兩欄（另列難得機會）
    e2 = dict(e, id="tw:tech:x2", var="x2", name="站回月線", up=_st(40, 0.75, 0.6, "good"), tier="good")
    f = dict(a, id="tw:bub:L2", cat="bub", var="L2", name="泡沫等級 2 以上", H=250, up=_st(12, 0.5, 0.6, "none"),
             warn=_st(12, 0.55, 0.3, "good"), tier="good", dir=["warn"])
    g = dict(a, id="tw:buy:E5:W10", cat="buy", var="W10", name="急跌後固定等 10 天", H=None,
             buy=_st(20, 0.7, 0.5, "good"), tier="good", dir=["buy"])
    o = dict(a, id="spx:heat:F1:hot", mk="spx")                                  # 別的市場不算
    rs = rows + [d1, e, e2, f, g, o]
    on = {r["id"]: {"since": "2026-10-01", "n": 3} for r in rs}
    B = sigcat.board(rs, on, "tw")
    assert [r["id"] for r in B["up"]] == ["tw:deriv:C1:1", "tw:buy:E5:W10", "tw:tech:x2"]   # 差大的在前；買點算偏多；◆ 不列
    assert [r["id"] for r in B["rare"]["up"]] == ["tw:tech:x"] and B["rare"]["warn"] == []
    assert all(r["tier"] == "good" for r in B["up"] + B["warn"])
    # VER 3：警示看每一列自己的警示判定——融資 C1 過熱中（警示 ★）和同項目的 deriv（偏多 ★）不同邊，兩邊都留、標震盪
    assert [r["id"] for r in B["warn"]] == ["tw:heat:C1:hot", "tw:bub:L2"]
    assert B["warn"][0]["d"] == "warn" and B["warn"][0]["both"] is True
    assert B["up"][0]["both"] is True and not any(r["both"] for r in B["up"][1:] + B["warn"][1:])
    assert [r["hz"] for r in B["up"]] == ["mid", "mid", "short"] and [r["hz"] for r in B["warn"]] == ["mid", "long"]
    th = {t["k"]: t for t in B["thermo"]}
    # VER 17：★ 2、◆ 1、△ 0.5——站回季線（◆）不列在兩欄，但算進短線溫度計；「溫度計另外算進去的」只收 △
    assert th["short"]["n"]["up"] == {"good": 1, "rare": 1, "lean": 0} and th["short"]["w"] == {"up": 3, "warn": 0}
    assert th["short"]["lean"] == "up" and th["short"]["share"] == 1
    assert th["short"]["more"]["up"] == [] and th["short"]["more"]["warn"] == []
    assert th["mid"]["n"]["up"] == {"good": 2, "rare": 0, "lean": 0} and th["mid"]["w"] == {"up": 4, "warn": 2}
    assert th["mid"]["lean"] == "up"
    assert th["long"]["w"] == {"up": 0, "warn": 2} and th["long"]["lean"] == "warn"
    assert sigcat.horizon(dict(a, cat="ind", H=12)) == "long" and sigcat.horizon(dict(a, H=250)) == "long"
    assert sigcat.item_key(a) == sigcat.item_key(d1) != sigcat.item_key(dict(a, cat="buy"))
    # 一列的偏多是 ★、警示是 ●（個股訊號的判定，市場訊號 VER 17 不會出現）：只列偏多、溫度計也不算
    m = dict(e, id="tw:tech:m", var="m", up=_st(40, 0.75, 0.6, "good"), warn=_st(40, 0.3, 0.2, "ref"), tier="good", dir=["up"])
    Bm = sigcat.board([m], {"tw:tech:m": {}}, "tw")
    assert [r["tier"] for r in Bm["up"]] == ["good"] and Bm["warn"] == [] and not Bm["up"][0]["both"]
    lng = dict(a, id="tw:heat:C1:hot13", sig="hot13", H=250, tier="good", warn=_st(12, 0.6, 0.3, "good"))
    B2 = sigcat.board(rs + [lng], dict(on, **{lng["id"]: {}}), "tw")           # 同一個項目、看多久不同 → 各算一次
    assert [r["id"] for r in B2["warn"]] == ["tw:heat:C1:hot13", "tw:heat:C1:hot", "tw:bub:L2"]   # 差 +30、+29、+25
    even = sigcat.board([dict(e2, id="tw:tech:y", var="y"), dict(e2, id="tw:tech:z", var="z", up=_st(40, 0.1, 0.2, "none"),
                                                             warn=_st(40, 0.6, 0.2, "good"), dir=["warn"])],
                        {"tw:tech:y": {}, "tw:tech:z": {}}, "tw")
    assert {t["k"]: t["lean"] for t in even["thermo"]} == {"short": "even", "mid": None, "long": None}


def test_board_families_merge_signals_that_appear_together():
    """同類合併（sigspec 第 5 節 ①b；VER 11 起看比較少出現的那個）：溫度計一類算一次；買點同一市場一類。"""
    import numpy as np
    rows = _rows()
    a = rows[0]
    mk = lambda i, nm, hit: dict(a, id=f"tw:tech:{i}", cat="tech", var=i, name=nm, H=20, up=_st(40, hit, 0.6, "good"),
                                 warn=_st(40, 0.1, 0.2, "none"), tier="good", dir=["up"])
    x, y, z = mk("x", "RSI 過冷", 0.80), mk("y", "20 日線乖離過冷", 0.78), mk("z", "站回月線", 0.75)
    b1 = dict(a, id="tw:buy:E5:C1", cat="buy", var="C1", name="VIX 回落", H=None, buy=_st(20, 0.7, 0.5, "good"), tier="good", dir=["buy"])
    b2 = dict(b1, id="tw:buy:E5:C2", var="C2", name="融資減少", buy=_st(20, 0.75, 0.5, "good"))
    T = 100
    act = lambda lo, hi: np.array([lo <= t < hi for t in range(T)])
    acts = {"tw:tech:x": act(0, 30), "tw:tech:y": act(5, 30), "tw:tech:z": act(60, 80)}   # x、y 重疊 25／30 ≥ 0.4
    on = {r["id"]: {"since": "2026-10-01", "n": 1} for r in (x, y, z, b1, b2)}
    B = sigcat.board([x, y, z, b1, b2], on, "tw", acts)
    ups = {r["id"]: [f["id"] for f in r["fam"]] for r in B["up"]}
    assert ups == {"tw:tech:x": ["tw:tech:y"], "tw:tech:z": [], "tw:buy:E5:C2": ["tw:buy:E5:C1"]}
    th = {t["k"]: t for t in B["thermo"]}
    assert th["short"]["w"]["up"] == 4 and th["mid"]["w"]["up"] == 2            # 一類算一次（★ 一類算 2）
    from arm.lab import heatviz as VZ
    h = VZ.today_html({"sigtoday": dict(B, d="2026-10-16")})
    assert "同時成立：20 日線乖離過冷（過去常一起出現，算同一件事）" in h and "3 類（共 5 個訊號）" in h



def test_thermometer_v17_counts_rare_and_lean_and_merges_by_tier():
    """VER 17（docs/lab_practical_plan.md；使用者選「溫度計照新的 ★ 算」）：溫度計算 ★ 2、◆ 1、△ 0.5；
    △＝判定 ○、這個方向的命中率門檻過了（次數 ≥ 5、機率 ≥ 60%（警示 50%）、不比平常差）；— 次數不夠、● 都不算。
    同類合併由高到低：◆、△ 併進已有的類、不另外算，也不會把兩個 ★ 類連成一類；兩欄照舊只列 ★，「同時成立」列併進來的 ◆。"""
    import numpy as np
    a = _rows()[0]
    assert sigcat.thermo_tier(_st(30, 0.66, 0.60, "none")) == "lean"
    assert sigcat.thermo_tier(_st(30, 0.64, 0.60, "none")) == "lean"            # VER 12～16 要比平常高 5 點，VER 17 不用
    assert sigcat.thermo_tier(_st(30, 0.58, 0.50, "none")) is None              # 機率不到 60%
    assert sigcat.thermo_tier(_st(30, 0.62, 0.65, "none")) is None              # 比平常差
    assert sigcat.thermo_tier(_st(30, 0.52, 0.40, "none"), "warn") == "lean"    # 警示的門檻 50%
    assert sigcat.thermo_tier(_st(30, 0.52, 0.40, "none")) is None
    assert sigcat.thermo_tier(_st(3, 0.90, 0.60, "few")) is None                # 次數不夠不算
    assert sigcat.thermo_tier(_st(30, 0.66, 0.60, "ref")) is None and sigcat.thermo_tier(None) is None
    assert sigcat.thermo_tier(_st(9, 0.80, 0.60, "rare")) == "rare"
    mk = lambda i, tier, hit: dict(a, id=f"tw:tech:{i}", cat="tech", var=i, name=i, H=20, up=_st(40, hit, 0.6, tier),
                                   warn=_st(40, 0.1, 0.2, "none"), tier=tier, dir=["up"])
    s1, s2 = mk("s1", "good", 0.80), mk("s2", "good", 0.78)                    # 兩個 ★，彼此不重疊
    r1, l1, l2 = mk("r1", "rare", 0.75), mk("l1", "none", 0.68), mk("l2", "none", 0.67)
    T = 100
    act = lambda lo, hi: np.array([lo <= t < hi for t in range(T)])
    acts = {"tw:tech:s1": act(0, 10), "tw:tech:s2": act(50, 60),
            "tw:tech:r1": act(0, 10) | act(50, 60),                            # ◆ 和兩個 ★ 都重疊：併進第一個，不把它們連起來
            "tw:tech:l1": act(80, 90), "tw:tech:l2": act(82, 90)}              # 兩個 △ 自己成一類
    on = {r["id"]: {"since": "2026-10-01"} for r in (s1, s2, r1, l1, l2)}
    B = sigcat.board([s1, s2, r1, l1, l2], on, "tw", acts)
    assert [(r["id"], [f["id"] for f in r["fam"]]) for r in B["up"]] == [("tw:tech:s1", ["tw:tech:r1"]), ("tw:tech:s2", [])]
    assert B["rare"] == {"up": [], "warn": []}                                # 和 ★ 同一類的 ◆ 不另列
    th = {t["k"]: t for t in B["thermo"]}["short"]
    assert th["n"]["up"] == {"good": 2, "rare": 0, "lean": 1} and th["w"]["up"] == 4.5
    assert [x["id"] for x in th["more"]["up"]] == ["tw:tech:l1"] and [f["id"] for f in th["more"]["up"][0]["fam"]] == ["tw:tech:l2"]
    fams = sigcat.thermo_families([dict(x, hz="short", side="up", edge=x["up"]["hit"] - 0.6) for x in (s1, s2, r1)], acts)
    assert {f["id"]: [m["id"] for m in f["fam"]] for f in fams} == {"tw:tech:s1": ["tw:tech:r1"], "tw:tech:s2": []}
    from arm.lab import heatviz as VZ
    h = VZ.today_html({"sigtoday": dict(B, d="2026-10-16")})
    assert 'aria-label="短線（看 1 個月）：偏多 ★2 △1・警示 0，偏多占 100%"' in h
    assert "△ 勝率過了 1 類" in h and h.count('class="tzg tzg-up tzg-lean"') == 1 and h.count('class="tzg tzg-up tzg-good"') == 1
    assert '同時成立：r1<span class="tzfr">◆</span>' in h                       # 併進 ★ 那一列的 ◆ 標出來
    # ◆ 自己一類（和 ★ 不重疊）→ 列在「難得機會」
    B2 = sigcat.board([s1, dict(r1, id="tw:tech:r2", var="r2", name="r2")],
                      {"tw:tech:s1": {"since": "2026-10-01"}, "tw:tech:r2": {"since": "2026-10-01"}}, "tw", acts)
    assert [r["id"] for r in B2["rare"]["up"]] == ["tw:tech:r2"]
    h2 = VZ.today_html({"sigtoday": dict(B2, d="2026-10-16")})
    assert '<div class="tzrare"><h3>難得機會' in h2 and "r2" in h2.split('<div class="tzrare">')[1]


def test_family_rule_v11_smaller_signal_inside_and_chance_guard():
    """VER 11（docs/lab_noise_plan.md 第 11 節）：比較少出現的那個，出現的日子裡另一個也成立的比例 ≥ 0.5，而且 ≥ 2 倍
    「另一個在全部樣本日成立的比例」才併。持續天數不同的同一件事（舊條件 ÷ 任一個只有 0.16）要併；長期狀態碰巧重疊的不併。"""
    import numpy as np
    T = 200
    act = lambda lo, hi: np.array([lo <= t < hi for t in range(T)])
    x, w = act(0, 60), act(50, 62)                       # w 的 12 天裡 10 天 x 也成立；x 只占 30% → 0.83 ≥ 0.6
    assert sigcat.overlap(x, w) == (10 / 12, 0.30) and sigcat.same_family(x, w)
    assert int((x & w).sum()) / int((x | w).sum()) < 0.2   # 舊條件（÷ 任一個）只有 0.16，以前併不起來
    big, v = act(0, 150), act(100, 110)                  # v 整段都在 big 裡，但 big 占 75%：互不相干也會有 75%
    assert sigcat.overlap(big, v)[0] == 1.0 and not sigcat.same_family(big, v)
    assert not sigcat.same_family(x, act(120, 140)) and not sigcat.same_family(None, x) and sigcat.overlap(x, act(0, 0)) == (0.0, 1.0)


def test_signal_overview_today_list_merges_families():
    """訊號總覽「今天有效的好訊號」VER 11 起同一套合併：一類一列、下面寫「同時成立」。"""
    import numpy as np
    a = _rows()[0]
    mk = lambda i, nm, hit: dict(a, id=f"tw:tech:{i}", cat="tech", var=i, name=nm, H=20, up=_st(40, hit, 0.6, "good"),
                                 warn=_st(40, 0.1, 0.2, "none"), tier="good", dir=["up"])
    x, y, z = mk("x", "RSI 過冷", 0.80), mk("y", "上漲家數占比過冷", 0.78), mk("z", "站回月線", 0.75)
    T = 200
    act = lambda lo, hi: np.array([lo <= t < hi for t in range(T)])
    acts = {"tw:tech:x": act(0, 60), "tw:tech:y": act(50, 62), "tw:tech:z": act(120, 140)}
    on = {r["id"]: {"since": "2026-10-01", "n": 1} for r in (x, y, z)}
    G = sigcat.today([x, y, z], on, "tw", acts)["good"]
    assert [(r["id"], [f["id"] for f in r["fam"]]) for r in G] == [("tw:tech:x", ["tw:tech:y"]), ("tw:tech:z", [])]
    assert [r["id"] for r in sigcat.today([x, y, z], on, "tw")["good"]] == ["tw:tech:x", "tw:tech:y", "tw:tech:z"]   # 沒有 acts：不併
    V = {**_view(), "today": {"tw": {"good": G}}}
    h = sigpage.today_html(V)
    assert "同時成立：上漲家數占比過冷（過去常一起出現，算同一件事）" in h and "過去常一起出現的併成一列" in h
    assert ".sgfm{" in sigpage.CSS


def test_research_files_survive_presentation_only_versions(tmp_path, monkeypatch):
    """研究檔版本 ≥ RES_VER 就能用（VER 11 只改合併，研究檔不用重跑；以前要求＝VER，一升版訊號總覽就會整個空掉）。"""
    monkeypatch.setattr(sigcat, "RESEARCH", tmp_path / "r.json")
    monkeypatch.setattr(sigcat, "STOCK", tmp_path / "s.json")
    for v, ok in ((sigspec.RES_VER - 1, False), (sigspec.RES_VER, True), (sigspec.VER, True)):
        (tmp_path / "r.json").write_text(json.dumps({"ver": v, "rows": []}), encoding="utf-8")
        (tmp_path / "s.json").write_text(json.dumps({"ver": v, "rows": []}), encoding="utf-8")
        assert (sigcat.load_research() is not None) is ok and (sigcat.load_stock() is not None) is ok
    assert sigspec.RES_VER == 20 <= sigspec.VER

def test_position_card_removed():
    """部位參考 2026-10-19 拿掉（docs/lab_crash_plan.md 第 20 節）：研究卡、景氣頁狀態列、相關研究連結都不得接回來。"""
    from pathlib import Path
    assert "pos" not in sigpage.CARD_ORDER and "pos" not in sigpage.CARD_NAMES
    assert not Path(sigpage.__file__).with_name("pospage.py").exists()
    for f in ("sigpage.py", "heatpage.py", "heatviz.py", "sigcat.py"):
        src = Path(sigpage.__file__).with_name(f).read_text()
        assert "pospage" not in src and "部位參考" not in src, f


def test_crash_now_latest_value_and_weekly_spark():
    """大跌風險項目的現在（訊號總覽依指標整理；景氣頁沒有這幾項）：最後一個有值的 0～100、區、日期、近 53 個週末。"""
    import numpy as np
    cal = [f"2026-{m:02d}-{d:02d}" for m in range(1, 11) for d in (5, 12, 19, 26)]
    x = np.linspace(10, 90, len(cal))
    x[-1] = np.nan
    F = {"cal": cal, "we": list(range(len(cal))), "cvars": [{"key": "W1", "x": x}, {"key": "W2", "x": np.full(len(cal), np.nan)}]}
    out = sigcat.crash_now(F)
    assert list(out) == ["W1"] and out["W1"]["d"] == cal[-2] and out["W1"]["h"] == round(float(x[-2]), 1)
    assert out["W1"]["band"] == "過熱" and len(out["W1"]["sp"]) == len(cal) and out["W1"]["sp"][-1] is None and out["W1"]["sp"][0] == 10


def test_facets_follow_heat_page_faces():
    """分類（docs/lab_nav_plan.md 第 2.2 節）：第一層照景氣頁的面向；籌碼、技術、策略再分第二層；判定、方向、只看現在、CSV 收進「更多篩選」。"""
    a = _rows()[0]
    h = lambda mk, var, grp: dict(a, id=f"{mk}:heat:{var}:hot", mk=mk, cat="heat", grp=grp, var=var, vn=var, name=f"{var}・過熱中")
    rs = [h("tw", "B1", "fund"), h("tw", "C1", "chip"), h("spx", "S1", "sent"), h("tw", "G1", "gliq"), h("tw", "L1", "tliq"),
          h("spx", "R1", "liq"), h("tw", "T1", "tech"), h("tw", "Dchip", "chip"), h("tw", "Dfund", "fund"), h("tw", "Dtech", "tech"),
          dict(a, id="tw:multi:hot", cat="multi", grp="multi", var="multi", vn="同時兩個面向過熱", name="同時兩個面向過熱"),
          dict(a, id="tw:crash:W1:hot", cat="crash", grp="crash", var="W1", vn="W1", name="W1・過熱中"),
          dict(a, id="tw:crash:W4:hot", cat="crash", grp="crash", var="W4", vn="W4", name="W4・過熱中"),
          dict(a, id="spx:crash:VOL:hot", mk="spx", cat="crash", grp="crash", var="VOL", vn="VOL", name="VOL・過熱中"),
          dict(a, id="tw:inst:fi5:hot", cat="inst", grp="fi", var="fi5", vn="外資 5 日", name="外資 5 日・大賣超"),
          dict(a, id="tw:tech:ma60_dn", cat="tech", grp="tech", var="ma60_dn", vn="跌破季線", name="跌破季線"),
          dict(a, id="tw:scen:SC5", cat="scen", grp="scen", var="SC5", vn="情境", name="情境"),
          dict(a, id="tw:bub:L2", cat="bub", grp="bub", var="L2", vn="L2", name="L2"),
          dict(a, id="ind:ff:L2", mk="us", cat="ind", grp="ff", var="L2", vn="美股 49 細產業", name="美股 49 細產業・L2"),
          dict(a, id="tw:buy:E5:W10", cat="buy", grp="E5", var="W10", vn="固定等 10 天", name="5 日急跌・固定等 10 天"),
          dict(a, id="stk:sig:cons", mk="stk", cat="stock", grp="stock", var="cons", vn="共識加碼", name="共識加碼"),
          dict(a, id="stk:strat:s5", mk="stk", cat="strat", grp="strat", var="s5", vn="長線", name="長線")]
    got = {x[0]: (x[7], x[8]) for x in sigpage.indicators(rs)}
    assert got == {"tw:B1": ("fund", None), "tw:C1": ("chip", "margin"), "spx:S1": ("chip", "margin"), "tw:G1": ("liq", None),
                   "tw:L1": ("liq", None), "spx:R1": ("liq", None), "tw:T1": ("tech", "ind"), "tw:Dchip": ("chip", "dim"),
                   "tw:Dfund": ("fund", None), "tw:Dtech": ("tech", "dim"), "tw:multi": ("scen", None), "tw:W1": ("chip", "margin"),
                   "tw:W4": ("liq", None), "spx:VOL": ("liq", None), "tw:inst:fi5": ("chip", "inst"), "tw:tech:ma60_dn": ("tech", "ev"),
                   "tw:scen:SC5": ("scen", None), "tw:bub": ("bub", None), "ind:ff": ("bub", None), "tw:buy:E5": ("buy", None),
                   "stk:sig:cons": ("stock", None), "stk:strat:s5": ("strat", "stk")}
    assert set(sigpage.SUBS) <= set(sigpage.FACETS) and set(sigpage.SUBS["strat"]) >= set(XS.GROUPS)   # 大神策略照它自己的分組
    assert all(v in sigpage.FACETS for v, _ in got.values())
    j = json.loads(sigpage.page_json(_view()))
    assert j["fac"] == sigpage.FACETS and j["sub"] == sigpage.SUBS and all(len(x) == 9 for x in j["inds"])
    t = sigpage.TABLE
    assert 'data-k="c1"' in t and '<div class="sgchips sgc2" data-k="c2" hidden>' in t and 'data-k="cat"' not in t
    adv = t[t.index('<details class="sgadv">'):t.index("</details>")]
    assert 'data-k="tier"' in adv and 'data-k="dir"' in adv and 'id="sgnow"' in adv and 'id="sgcsv"' in adv
    assert t.index('data-k="c2"') < t.index('<details class="sgadv">') and 'href="x9.html#v=mac"' in t
    for f in ("x.c1 !== st.c1", "if (k === 'c1') st.c2 = ''", "c1: 'strat', c2: sp.grp", "facName(x)", "sgadvn"):
        assert f in sigpage.JS, f


def test_scenarios_are_their_own_indicators():
    """情境（sigspec VER 4 第 4.10 節）：每個情境一個指標、類別「情境」；指標頁畫指數＋情境期間；現在欄寫用到的面向分數。"""
    a = _rows()[0]
    sc = dict(a, id="tw:scen:SC5", cat="scen", grp="scen", var="SC5", vn="籌碼熱、價格轉弱", name="籌碼熱、價格轉弱",
              sig="on", kind="state", H=60)
    x = sigpage.indicators([sc])[0]
    assert x[:4] == ["tw:scen:SC5", "tw", "scen", "籌碼熱、價格轉弱"] and x[6] is None
    assert sigpage.IND_CATS["scen"] == "情境" and sigcat.CAT_NAMES["scen"] == "情境"
    m = sigpage.scen_meta()
    assert list(m) == [k for k, *_ in sigspec.SCENARIOS]
    assert m["SC5"] == ["籌碼熱、價格轉弱", "籌碼 60 以上、技術 未滿 40", "追價的人被套，會不會再跌", ["chip", "tech"]]
    assert m["SC8"][1].startswith("四個面向（基本面、籌碼、資金、技術）至少 3 個有值") and m["SC8"][3] == list(sigspec.SCEN_DIMS)
    items = {"tw": {"Dfund": {"h": 94.0}, "Dchip": {"h": 88.0}, "Dgliq": {"h": 17.0}, "Dtliq": {"h": 45.0}, "Dtech": {"h": 33.0}},
             "spx": {"Dfund": {"h": 65.0}, "Dsent": {"h": 41.0}, "Dliq": {"h": 38.0}, "Dtech": {"h": None}}}
    assert sigpage.scen_values(items) == {"tw": {"fund": 94.0, "chip": 88.0, "liq": 31.0, "tech": 33.0},
                                          "spx": {"fund": 65.0, "chip": 41.0, "liq": 38.0, "tech": None}}
    js = sigpage._JS if hasattr(sigpage, "_JS") else sigpage.render(_view())
    assert "const PXC = ['tech', 'crash', 'dim', 'scen', 'inst', 'bub', 'buy'];" in js and "function scenNow(x)" in js
    assert "if (c === 'scen')" in js and "x9m.html#o=scen" in js and "'&o=scen'" in js


def test_entry_returns_go_to_detail_file_and_panel():
    """VER 5：訊號觸發後的報酬只放訊號總覽指標頁（使用者選定）；資料在 x9oh.json（點開才下載），平常存一份共用。"""
    V = _view()
    cell = [17, 0.1049, 0.0342, 0.0794, 0.1627, 0.8231, -0.0166, -0.1791, -0.2614]
    V["rows"][0]["ret"] = {"s": [cell] + [None] * (len(sigspec.RET_H) - 1), "p": [[0.01, 0.02, 0.03]] * len(sigspec.PATH_D),
                           "bk": "tw:abc"}
    V["rows"][1]["ret"] = {"s": [cell] * len(sigspec.RET_H), "p": [None] * len(sigspec.PATH_D), "bk": "tw:abc"}
    V["bases"] = {"tw:abc": {"s": [cell] * len(sigspec.RET_H), "p": [[0.0, 0.01, 0.02]] * len(sigspec.PATH_D)},
                  "tw:unused": {"s": [], "p": []}}
    det = json.loads(sigpage.detail_json(V))
    a = det["ret"]["tw:heat:C1:hot"]
    assert a["b"] == "tw:abc" and a["s"][0] == [17, 10.5, 3.4, 7.9, 16.3, 82.3, -1.7, -17.9, -26.1] and a["s"][1] is None
    assert set(det["rb"]) == {"tw:abc"} and det["ret"]["tw:heat:C1:hot_in"]["b"] == "tw:abc"
    assert "tw:tech:ma60_dn" not in det["ret"]                           # 沒有報酬資料的列不放
    j = json.loads(sigpage.page_json(V))
    assert j["rh"] == list(sigspec.RET_H) and j["pd"] == list(sigspec.PATH_D) and j["rhm"] == list(sigspec.RET_H_M)
    js = sigpage.JS
    for w in ("進場之後：", "function retHtml", "function drawRet", "中途最多跌", "判定看這一期", "id=\"sgret\""):
        assert w in js.replace("\\'", "'") or w.replace('"', "'") in js, w
    for w in BANNED:
        assert w not in js, w
    for c in ("sgrr", "sgrw", "sgrcv", "sgrch"):
        assert "." + c in sigpage.CSS


def test_inst_indicators_and_trigger_text():
    """VER 6 法人買賣超：一個期間一個指標（單日極端與連續同一個）；VER 7 起只當訊號，現在的值都由 sigcat.crash_now 算。"""
    base = {"mk": "tw", "cat": "inst", "kind": "event", "H": 20}
    r1 = dict(base, id="tw:inst:fi1:day_sell", grp="fi", var="fi1", vn="外資單日買賣超", name="外資單日買賣超・單日大賣")
    r2 = dict(base, id="tw:inst:fi1:sell_run5", grp="fi", var="fi1", vn="外資單日買賣超", name="外資單日買賣超・外資連續 5 天賣超")
    r3 = dict(base, id="tw:inst:fi5:hot", grp="fi", var="fi5", vn="外資 5 日買賣超", name="外資 5 日買賣超・大賣超中", kind="state")
    r4 = dict(base, id="tw:inst:tot60:cold", grp="tot", var="tot60", vn="三大法人合計 60 日買賣超", name="x", kind="state", H=60)
    assert sigpage.ind_of(r1) == ("tw:inst:fi1", "inst", "外資單日買賣超", "fi1")
    assert sigpage.ind_of(r2)[0] == "tw:inst:fi1" and sigpage.ind_of(r3) == ("tw:inst:fi5", "inst", "外資 5 日買賣超", "fi5")
    assert sigpage.ind_of(r4)[3] == "tot60" and sigpage.IND_CATS["inst"] == sigcat.CAT_NAMES["inst"] == "法人買賣超"
    js = sigpage.JS
    assert "const ITRIG = {" in js and "if (c === 'inst') return x.vn + '：' + itrig(x);" in js
    for k in sigspec.INST_VARIANTS + ("day_sell", "day_buy"):
        assert k + ":" in js.split("const ITRIG = {")[1].split("};")[0], k


def test_ver17_method_text_and_luck_summary():
    """VER 17：名詞與判定方式寫絕對成績的 ★、◆ 難得機會、報酬中位數與排除極端、打亂日子測試只當參考（個股訊號照舊，● 可能是運氣）、
    運氣會產生幾個 ★、◆（研究檔的 luck，[★, 運氣 ★, ◆, 運氣 ◆]）；警示寫明只當提醒。"""
    luck = {"tw": {"up": [20, 2.2, 5, 4.1], "warn": [9, 1.1, 3, 2.0]}, "spx": {"up": [11, 1.2, 2, 1.5], "warn": [0, 0.8, 1, 0.4]}}
    h = sigpage.method_html(luck)
    assert "打亂日子測試" in h and "● 可能是運氣" in h and "亂排 400 次" in h and "只當參考、不參與判定" in h
    assert "偏多（含大跌後買點）★ 31 個，運氣大約也會產生 3 個；◆ 7 個，運氣大約 6 個" in h
    assert "警示 ★ 9 個、運氣大約 2 個；◆ 4 個、運氣大約 2 個" in h and "大部分是大盤本身就會給的" in h
    assert "只當提醒" in h and "至少 15 次" in h and "只出現 5～14 次" in h and "◆ 難得機會" in h
    assert "報酬中位數與排除極端的平均都比來回成本高（台股 0.2%、美股 0.05%）" in h
    assert "去掉最好和最差各 5%（不到 20 次時各去掉一次）" in h
    assert "運氣會產生幾個" not in sigpage.method_html(None)
    for w in BANNED:
        assert w not in h


def test_bottom_chip_lists_rules_regardless_of_tier():
    """一段大跌進行中：景氣頁最上面那一行列出這一次每個落底訊號出現了沒（不論判定），連到大跌後檢查卡（2026-10-20）。"""
    from arm.lab import heatpage as HP
    a = {"w10": {"st": "wait", "left": 7}, "sig": {"C1": {"st": "on", "d": "2026-10-17"}, "C5": {"st": "none"}}}
    h = HP.bottom_chip(a, "sox")
    assert 'href="x9o.html#r=sox:bottom"' in h and "<b>落底訊號</b>1／3 出現" in h
    assert "固定等 10 個交易日：還沒（再 7 個交易日）" in h and "10/17 出現" in h and "這一次沒有出現" in h
    assert "台股" not in h and "加權指數" not in h


def test_thermometer_v15_cross_horizon_votes():
    """VER 15（docs/lab_noise_plan.md 第 14 節；使用者選「三個看多久都算」）：研究列的 xh 有另外兩支溫度計的統計，
    現在有效（xon）而且那個方向的命中率門檻過了（VER 17：次數 ≥ 5、機率 ≥ 60%（警示 50%）、不比平常差）→ 那支溫度計算 △；
    不給 ★／◆、不進兩欄；
    同一個項目同一支溫度計同一邊只算一種（原本那個看多久的 ★ 優先）；沒有 xon 就和 VER 14 一樣。"""
    import numpy as np
    a = _rows()[0]
    xh = lambda up, wn: {"H": 60, "th": 0.10, "up": up, "warn": wn}
    s = lambda n, hit, base: {"n": n, "hit": hit, "base": base}
    r1 = dict(a, id="tw:heat:x:cold", cat="heat", var="x", name="RSI・進入過冷", H=20, up=_st(40, 0.62, 0.60, "none"),
              warn=_st(40, 0.20, 0.20, "none"), tier="none", dir=["up"],
              xh={"mid": xh(s(30, 0.75, 0.65), s(30, 0.30, 0.29)), "long": dict(xh(s(4, 0.95, 0.70), s(4, 0.0, 0.2)), H=250, th=0.2)})
    r2 = dict(a, id="tw:tech:y", cat="tech", var="y", name="跌破季線", H=20, up=_st(40, 0.60, 0.60, "none"),
              warn=_st(40, 0.20, 0.20, "none"), tier="none", dir=["up"],
              xh={"mid": xh(s(30, 0.62, 0.65), s(30, 0.55, 0.29))})                 # 偏多比平常差不算、警示 55% 算
    nat = dict(a, id="tw:heat:x:hot", cat="heat", var="x", name="RSI・過冷中", H=60, up=_st(20, 0.90, 0.65, "good"),
               warn=_st(20, 0.2, 0.29, "none"), tier="good", dir=["up"])            # 同一個項目（var x）原本看 3 個月的 ★
    rows = [r1, r2]
    on = {}                                                                      # 原本那個看多久都沒有成立
    xon = {"tw:heat:x:cold": {"mid": {"since": "2026-09-01", "n": 30, "left": 30}, "long": {"since": "2026-09-01", "n": 30, "left": 220}},
           "tw:tech:y": {"mid": {"since": "2026-10-01", "n": 10, "left": 50}}}
    assert {t["k"]: t["w"] for t in sigcat.board(rows, on, "tw")["thermo"]}["mid"] == {"up": 0, "warn": 0}   # 沒有 xon：同 VER 14
    B = sigcat.board(rows, on, "tw", {}, xon)
    th = {t["k"]: t for t in B["thermo"]}
    assert th["mid"]["n"]["up"] == {"good": 0, "rare": 0, "lean": 1} and th["mid"]["n"]["warn"] == {"good": 0, "rare": 0, "lean": 1}
    assert th["long"]["w"] == {"up": 0, "warn": 0}                                # 次數 4 < 5 不算
    assert th["short"]["w"] == {"up": 0, "warn": 0} and B["up"] == [] and B["warn"] == []   # 只進溫度計
    x = th["mid"]["more"]["up"][0]
    assert (x["id"], x["H"], x["H0"], x["xk"], x["ak"], x["tier"]) == ("tw:heat:x:cold", 60, 20, "mid", "tw:heat:x:cold@mid", "lean")
    assert abs(x["edge"] - 0.10) < 1e-12 and x["up"]["hit"] == 0.75 and x["now"]["left"] == 30
    # 同一個項目（景氣項目 x）原本看 3 個月的 ★ 成立：中線偏多算 ★，跨期間的 △ 不另外算（實際上同一個項目的訊號看多久都一樣，這裡只測規則）
    B2 = sigcat.board(rows + [nat], {nat["id"]: {"since": "2026-10-01"}}, "tw", {}, xon)
    th2 = {t["k"]: t for t in B2["thermo"]}
    assert th2["mid"]["n"]["up"] == {"good": 1, "rare": 0, "lean": 0} and [r["id"] for r in B2["up"]] == ["tw:heat:x:hot"]
    # 同類合併用跨期間的出現日子（ak）：兩個跨期間的 △ 重疊就併成一類
    T = 100
    act = lambda lo, hi: np.array([lo <= t < hi for t in range(T)])
    r3 = dict(r2, id="tw:tech:z", var="z", name="跌破月線", xh={"mid": xh(s(30, 0.30, 0.29), s(30, 0.56, 0.29))})
    xon3 = dict(xon, **{"tw:tech:z": {"mid": {"since": "2026-10-02", "n": 9, "left": 51}}})
    acts = {"tw:tech:y@mid": act(0, 40), "tw:tech:z@mid": act(5, 40)}
    B3 = sigcat.board(rows + [r3], on, "tw", acts, xon3)
    w3 = {t["k"]: t for t in B3["thermo"]}["mid"]
    assert w3["n"]["warn"]["lean"] == 1 and [f["id"] for f in w3["more"]["warn"][0]["fam"]] == ["tw:tech:y"]
    # 頁面：寫這支溫度計的看多久與機率，標「原本看 1 個月」
    from arm.lab import heatviz as VZ
    h = VZ.today_html({"sigtoday": dict(B, d="2026-10-16")})
    assert "3 個月・原本看 1 個月" in h and "之後 3 個月上漲的機率 <b>75%</b>（隨便挑一天 65%）・出現過 30 次" in h
    assert "標「原本看…」的是原本看別的期間的訊號" in h and "每個訊號三支溫度計都算" in h


def _fwd_table():
    return {"ver": sigspec.FWD_VER, "nrec": 1234,
            "cells": {"warn|60|0|4": {"k": 0.2, "kr": None, "n": 150, "ncl": 40}, "up|60|*|3": {"k": 0.25, "kr": 0.5, "n": 300, "ncl": 60},
                      "warn|60|*|p": {"k": 0.1, "kr": None}, "up|60|*|p": {"k": 0.1, "kr": 0.3}, "up|20|*|p": {"k": 0.5, "kr": 0.6}},
            "own": {"tw:heat:C1:hot": {"warn": [6, 0.25, 0.03, None, None]}}}


def test_forward_estimate_lines_panel_and_method(monkeypatch):
    """預估之後（sigspec 第 4.14 節，VER 18～19）：今天的清單與指標頁寫「過去 X% → 預估之後 Y%」，只算 ★、◆（跨期間的票、△ 不算）；
    判定方式加衰退表；研究檔沒有就不列。"""
    T = _fwd_table()
    monkeypatch.setattr(sigpage.OOS, "load", lambda path=None: T)
    V = _view()
    a = V["rows"][0]
    line = sigpage._line({**a, "d": "warn", "tier": "good"})
    assert "大跌（最大回撤 10% 以上）的機率：過去 58% → 預估之後 <b>35%</b>（隨便挑一天 29%）" in line      # 0.29 ＋ 0.2 × 0.29
    assert sigpage._fe({**a, "d": "warn", "tier": "lean"}) is None and sigpage._fe({**a, "d": "warn", "tier": "good", "xk": "short"}) is None
    b = dict(V["rows"][1], ret={"s": [None] * 4 + [[13, 0, 0, 0.06, 0, 0, 0, 0, 0, 0.05, 0.04]], "bk": "kb"})
    sigcat._RCACHE["rows"], sigcat._RCACHE["bases"] = [], {"kb": {"s": [None] * 4 + [[1, 0, 0, 0.02, 0]]}}
    try:
        lb = sigpage._line({**b, "d": "up", "tier": "good"})
        assert "過去 85% → 預估之後 <b>71%</b>（隨便挑一天 66%）" in lb and "預估之後比隨便挑一天多 2.0%" in lb   # 0.66 ＋ 0.25 × 0.19；0.5 × 4%
        fe, ow = sigpage._fe_pack(b, {})
        assert fe["up"] == [71, 25, 0, 2.0, 50, 0] and "warn" in fe and len(fe["warn"]) == 3
    finally:
        sigcat._RCACHE.clear()
    j = json.loads(sigpage.page_json(V))
    assert j["fwd"]["ok"] and set(j["fwd"]) >= {"nb", "eb", "sg", "keys", "omin"}
    ra = next(r for r in j["rows"] if r[0] == "tw:heat:C1:hot")
    assert ra[15]["fe"]["warn"][:2] == [35, 20] and j["fwd"]["keys"][ra[15]["fe"]["warn"][2]] == "warn|60|0|4"
    assert ra[15]["ow"]["warn"] == [6, 25.0, 3.0]
    assert all("fe" not in r[15] for r in j["rows"] if r[2] == "strat")                      # 策略沒有預估之後
    m = sigpage.method_html()
    assert "<dt>預估之後</dt>" in m and 'class="sgfw"' in m and "1,234 筆" in m and "偏多的優勢看 1 個月留下 50%" in m
    for f in ("function feOf", "function feHtml", "function cellTxt", "function moreTxt", 'id="sgfe"', "預估之後的機率%"):
        assert f in sigpage.JS, f
    monkeypatch.setattr(sigpage.OOS, "load", lambda path=None: None)
    assert sigpage.fwd_html() == "" and sigpage._fe({**a, "d": "warn", "tier": "good"}) is None


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_forward_estimate_js_cells_text():
    """頁面把衰退表的格子（sigoos.key）寫成白話、多賺寫成多／少／差不多。"""
    fns = [re.search(r"^function " + n + r"\(.*?\n(?=function |const |// )", sigpage.JS, re.S | re.M).group(0) for n in ("moreTxt", "cellTxt")]
    prog = ("const SG = {dirs: {up: '偏多', warn: '警示', buy: '買點'}, fwd: " + json.dumps(sigpage.fwd_meta({}), ensure_ascii=False) + "};\n"
            "const HT = {20:'1 個月',60:'3 個月',250:'12 個月'};\n" + "".join(fns) +
            "console.log(JSON.stringify([moreTxt(0.94), moreTxt(-0.2), moreTxt(0.04), cellTxt('up|20|1|3'), cellTxt('warn|250|*|0'), cellTxt('buy|60|*|p')]));")
    r = subprocess.run(["node", "-"], input=prog, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["多 0.9%", "少 0.2%", "差不多", "偏多・看 1 個月・出現過 15～39 次・過去比平常高 10～20 點",
                                    "警示・看 12 個月・過去比平常低", "大跌後買點・看 3 個月・過去不比平常低"]
