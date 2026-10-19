"""台股細分族群（bubindspec VER 3 第 1c 節；docs/lab_crash_plan.md 第 21.5 節）：成員、指數、頁面。"""
import re
from types import SimpleNamespace

import pytest

from arm.lab import bubind as BD
from arm.lab import bubindpage as IP
from arm.lab import bubindspec as BI
from arm.lab import bubpage as BP

from tests.test_bubind import BANNED, ROOT, _hist, _now


# ── 成員 ─────────────────────────────────────────────────────────────────

def _seg(lab, codes):
    return [lab, len(codes), list(codes)]


def _doc():
    heads = [["記憶體IC", 2, []], ["記憶體控制IC", 1, []]]
    return {"d": "2026-10-19", "chains": {
        "L000": {"n": "印刷電路板", "nodes": [
            ["L500", "硬板、軟板、IC載板製造", [_seg("本國上市公司", ["3037", "8046", "2368"]), _seg("本國上櫃公司", ["3189", "6153", "0050"]),
                                         _seg("本國興櫃公司", ["7777"]), ["知名外國企業", 2, []]]]]},
        "F000": {"n": "電腦週邊", "nodes": [
            ["F900", "伺服器", [_seg("本國上市公司", ["2382", "3231", "6669"])]],
            ["F500", "記憶體", [_seg("本國上市公司", ["3260", "2451"]), _seg("本國上櫃公司", ["4967"])]]]},
        "D000": {"n": "半導體", "nodes": [
            ["D100", "IC設計", heads + [_seg("本國上市公司", ["2408", "2344"]), _seg("本國上櫃公司", ["8299"])]]]}}}


CUR = {c: "x" for c in ("3037", "8046", "2368", "3189", "6153", "0050", "2382", "3231", "6669", "3260", "2451", "4967",
                         "2408", "2344", "8299")}


def test_members_resolve_nodes_tabs_and_filters():
    T = BD.tg_members(_doc(), CUR)
    assert T["groups"]["pcb"] == {"3037", "8046", "2368", "3189", "6153"}            # 興櫃、00 開頭不收
    assert T["groups"]["memory"] == {"2408", "2344", "8299", "3260", "2451", "4967"}  # 兩個分頁＋模組節點
    assert T["n"] == {"pcb": 5, "memory": 6} and T["d"] == "2026-10-19"
    assert T["skip"]["server"] == "現在上市櫃只有 3 家"
    assert T["skip"]["optical"].startswith("找不到 I000")
    assert set(T["skip"]) | set(T["groups"]) == {k for k, _, _ in BI.TG_GROUPS}


def test_members_skip_group_when_tab_cannot_be_parsed():
    d = _doc()
    d["chains"]["D000"]["nodes"][0][2][0][1] = 3                                      # 分頁家數對不上
    T = BD.tg_members(d, CUR)
    assert "memory" not in T["groups"] and "分頁「記憶體IC」" in T["skip"]["memory"]
    assert BD.tg_members({}, CUR) == {"groups": {}, "n": {}, "d": None, "skip": {}}


# ── 指數：族群模式和產業別模式算法相同、可以重疊 ───────────────────────────────

def _panel():
    import datetime as dt
    cal, d = [], dt.date(2024, 1, 2)
    while len(cal) < 70:
        if d.weekday() < 5:
            cal.append(d.isoformat())
        d += dt.timedelta(days=1)
    T = len(cal)
    codes = ["1101", "1102", "1103", "1104", "1105"]
    s, cap, liq = {}, {}, {}
    for j, c in enumerate(codes):
        px = [100.0 * (1 + 0.002 * (j + 1)) ** i for i in range(T)]
        s[c] = {"c": px}
        cap[c] = [50e8 * (j + 1) * v / 100.0 for v in px]
        liq[c] = [1e8] * T
    return SimpleNamespace(cal=cal, T=T, codes=codes, s=s, cap=cap, liq=liq)


def test_group_mode_equals_industry_mode_and_allows_overlap():
    P = _panel()
    a = BD.tw_build(P, ind_map={"1101": "g", "1102": "g", "1103": "g", "1104": "h", "1105": "h"})
    b = BD.tw_build(P, ind_map={"1101": "g", "1102": "g", "1103": "g", "1104": "g", "1105": "h"})
    G = BD.tw_build(P, groups={"x": {"1101", "1102", "1103"}, "y": {"1101", "1102", "1103", "1104"}})
    assert G["grp"]["x"]["px"] == a["grp"]["g"]["px"] and G["grp"]["y"]["px"] == b["grp"]["g"]["px"]
    assert G["grp"]["x"]["n"] == a["grp"]["g"]["n"] and G["grp"]["x"]["turn"] == a["grp"]["g"]["turn"]
    assert G["grp"][BD.MKT]["px"] == a["grp"][BD.MKT]["px"]                            # 大盤和產業別模式同一個
    assert any(v is not None for v in G["grp"]["x"]["px"])


def test_inputs_refuse_index_built_from_another_member_list():
    TM = {"groups": {"pcb": {"3037"}}, "n": {"pcb": 1}, "d": "2026-10-19", "skip": {}}
    TB = {"cal": ["2026-10-16"], "grp": {BD.MKT: {"px": [1.0], "n": {}, "turn": {}}}, "src": "2026-09-01"}
    assert BD.tg_inputs(TB, TM) == {}


# ── 頁面 ─────────────────────────────────────────────────────────────────

def _I():
    est = {"n": 8, "cov": 0.93, "g0": 6.82, "g1": 0.63, "rev": 0.467, "px3": 41.7}
    tg = {"pcbm": {"now": _now(4, ["P1", "P2", "E", "F"], ru=609.0, net=503.0, dist=0.0, g=est, gsrc="est", f=91.0, mem=24, run=8),
                   "hist": _hist()},
          "memory": {"now": _now(2, ["P1"], ru=488.0, net=381.0, dist=-16.9, mem=15), "hist": _hist()},
          "conn": {"now": _now(0, [], ru=30.0, net=-76.0, dist=-14.0, mem=25), "hist": _hist()}}
    return {"ver": BI.VER, "tg": tg, "tg_d": "2026-10-19", "tg_n": {"pcbm": 26, "memory": 20, "conn": 49},
            "tg_skip": {"server": "現在上市櫃只有 3 家"},
            "tg_list": {"pcbm": ["1303", "2383"], "memory": ["2408"], "conn": ["3533"]}}


@pytest.fixture(scope="module")
def sec(monkeypatch_module):
    I = _I()
    data, keys = IP.hist_data(I)
    return I, data, keys, IP.section(I, {}, keys)


@pytest.fixture(scope="module")
def monkeypatch_module():
    mp = pytest.MonkeyPatch()
    import arm.lab.company as CO
    mp.setattr(CO, "names", lambda: {"1303": "南亞", "2383": "台光電", "2408": "南亞科"})
    yield mp
    mp.undo()


def test_section_has_finer_group_table(sec):
    I, data, keys, html = sec
    assert "台股細分族群<span class=\"sub\">用現在的成員往回算・只描述</span>" in html
    t = html[html.index("<h3>台股細分族群"):]
    assert 'class="bind bsort bgrp"' in t and "<th class=\"l\" data-si=\"0\">族群</th>" in t
    order = re.findall(r'<td class="l bnm" data-v="([^"]+)"', t)
    assert order == ["PCB 材料", "記憶體（晶片、控制 IC、模組）", "連接器"]                  # 等級高的在前
    assert "成員 2 家（平台現在的名單，依市值排列）：1303 南亞、2383 台光電" in t and "成員 1 家（平台現在的名單，依市值排列）：3533" in t
    assert "PCB 材料：等級 4「嚴重泡沫」（價格爆發、兩年翻倍、漲得比營收快、換手率）" in t and "換手率第 91 百分位" in t
    assert "2026/10/19 的名單" in t and "已下市或移出的公司不在裡面" in t and "這次沒算：伺服器（現在上市櫃只有 3 家）" in t
    assert keys["tg"] == {"conn": "@g0", "memory": "@g1", "pcbm": "@g2"} and all(k in data for k in keys["tg"].values())
    assert "3 個細分族群" in html and "台股 3 個細分族群：1 個在等級 4（PCB 材料）、1 個在等級 2（記憶體）" in html


def test_class_names_do_not_collide_with_bubble_page():
    """btg 是泡沫頁的等級磚格線（2026-10-19 撞名：表格變成 grid、手機橫捲）。"""
    for c in ("bgrp", "bmem"):                                                       # 細分族群新加的 class
        assert re.search(r"\." + c + r"(?![\w-])", IP.CSS)
        assert not re.search(r"(?<![\w-])\." + c + r"(?![\w-])", BP.CSS + BP.JS), c
    assert "btg" not in IP.CSS


def test_finer_group_warning_and_no_banned_words(sec):
    assert "細分族群還算不出來（ValueError: x）" in IP.tg_block({"tg_err": "ValueError: x"}, {})
    assert IP.tg_block({}, {}) == ""
    _, _, _, html = sec
    assert not [w for w in BANNED if w in html + IP.TG_NOTE]


def test_wired_into_ci_and_research():
    fh = (ROOT / "scripts" / "fetch_heat.py").read_text(encoding="utf-8")
    assert "icchain.fetch" in fh and fh.index("icchain.fetch") < fh.index('run("台股產業指數", BD.indtw_update)')
    wf = (ROOT / ".github" / "workflows" / "lab_backfill.yml").read_text(encoding="utf-8")
    assert '"$MODE" = "icfill"' in wf and "--ic-chain" in wf
    R = BD.load_research()
    assert R is not None and R["ver"] == BI.VER == 3 and "tg" in R and R["tg"]["src"]
    assert set(R["tg"]["tests"]) == set(BI.TESTS["tg"])
    assert "tg" not in BI.JUDGE
