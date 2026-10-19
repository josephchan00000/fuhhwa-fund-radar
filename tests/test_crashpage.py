"""景氣頁「短線大跌風險」卡（arm/lab/crashpage.py；docs/lab_crash_plan.md 第 3.6、10 節）：只列判定有差別的項目、
現在熱的排前面並展開、今天同樣狀態的格子、一句話、判定表、主要假說、用字。研究數字只讀研究檔，不在頁面重算。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

from arm.lab import crash as K
from arm.lab import crashpage as CP
from arm.lab import crashspec as S

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatpage import BANNED  # noqa: E402


def _res(v="none", hot=0.3, nott=0.1, d=0.1, strata=None, a="2002-07-19", oos="same", ok=True, nh=500, ep=10):
    st = strata or [[100, 0.25, 300, 0.08], [150, 0.30, 280, 0.10], [10, 0.5, 260, 0.12]]
    r = {"v": v, "a": a, "hot": hot, "not": nott, "base": 0.15, "d": d, "lo": d - 0.05, "hi": d + 0.05, "h1": d, "h2": d,
         "q": 0.05, "nh": nh, "nn": 3000, "ep": ep, "ok": ok, "strata": st, "cuts": [0.01, 0.02],
         "zones": [[nh, hot], [400, 0.2], [400, 0.15], [400, 0.1], [12, 0.09]]}
    if oos:
        r["oos"] = {"n": 2000, "v": oos}
    return r


def _C(mk="tw", now=None, preds=None, vol=0.015):
    preds = preds or {}
    R = {"start": S.START[mk], "end": "2026-10-16", "sigma": 0.015, "base": {o: 0.2 for o in S.OUTCOMES},
         "preds": {p: {"a": "2002-07-19", "out": {o: (preds.get(p) or {}).get(o) or _res() for o in S.OUTCOMES}}
                   for p in S.PRED[mk]}}
    now = now or {}
    N = {"d": "2026-10-16", "vol": vol, "preds": {}}
    for p in S.PRED[mk]:
        v = now.get(p)
        N["preds"][p] = {"v": v, "hot": None if v is None else v >= S.HOT, "g": {o: 1 for o in S.OUTCOMES}}
    prim = {h: {"d": 0.05, "lo": -0.01, "hi": 0.12, "p1": 0.05, "padj": 0.1, "h1": 0.04, "h2": 0.01, "few": False, "ok": False,
                "nh": 1600, "ep": 14} for h in S.PRIMARY}
    prim["HA3"] = {"few": True, "nh": 20, "ep": 3, "ok": False}
    vs = {"vol": vol, "pct": 0.62, "g": 1, "a": "1990-02-01",
          "rows": {o: {"g": 0.15, "ng": 3000, "all": 0.16, "n": 9000} for o in S.OUTCOMES}}
    return {"mk": mk, "px": "加權指數" if mk == "tw" else f" {S.NAMES[mk]} ", "now": N, "vs": vs, "R": R, "primary": prim}


def _text(h: str) -> str:
    t = re.sub(r"<svg.*?</svg>", "", h, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", t))


def test_items_only_list_up_and_down_outcomes_hot_first():
    C = _C(now={"C1": 99.5, "W2": 53.0, "C4": 86.0, "W1": None, "T9": 47.0},
           preds={"C1": {"A4": _res("up"), "A5": _res("up")}, "W2": {"A2": _res("up"), "A1": _res("few")},
                  "C4": {"A2": _res("up")}, "W1": {"A3": _res("down")}, "T9": {"A1": _res("none")}})
    its = CP.items(C)
    assert [it["p"] for it in its] == ["C1", "C4", "W2", "W1"]                 # 熱的先（依今天的值），沒有值的最後
    assert [r["o"] for r in its[0]["outs"]] == ["A4", "A5"] and [r["o"] for r in its[2]["outs"]] == ["A2"]
    assert all(r["v"] in S.SHOW for it in its for r in it["outs"])
    assert its[0]["hot"] and its[1]["hot"] and not its[2]["hot"] and not its[3]["hot"]
    assert its[0]["hotdef"].startswith("比過去 3 年 80% 的時候") and its[3]["monthly"]


def test_same_state_cell_uses_todays_vol_group_and_minimum_days():
    st = [[100, 0.25, 300, 0.08], [150, 0.30, 280, 0.10], [10, 0.50, 260, 0.12]]
    hot = {"v": 90.0, "hot": True, "g": {"A2": 1}}
    r = CP._orow("A2", _res("up", strata=st), hot)
    assert r["same"] == {"n": 150, "y": 0.30, "g": 1}
    r = CP._orow("A2", _res("up", strata=st), {"v": 50.0, "hot": False, "g": {"A2": 1}})
    assert r["same"] == {"n": 280, "y": 0.10, "g": 1}
    assert CP._orow("A2", _res("up", strata=st), {"v": 90.0, "hot": True, "g": {"A2": 2}})["same"] is None   # 熱的只有 10 天
    assert CP._orow("A2", _res("up", strata=st), {"v": None, "hot": None, "g": {}})["same"] is None
    assert CP._orow("A5", _res("up"), hot)["oos"] == "na"                       # 最差 3 天沒有做樣本外
    assert CP._orow("A2", _res("up", oos=None), hot)["oos"] is None               # 資料太短沒有做


def test_lead_sentence_from_verdicts_and_todays_values():
    C = _C(now={"C1": 99.5, "C4": 86.0, "W2": 53.0},
           preds={"C1": {"A4": _res("up", oos="same"), "A5": _res("up")}, "C4": {"A2": _res("up", oos=None)},
                  "W2": {"A2": _res("up")}})
    ls = CP.lead(CP.items(C))
    assert ls[0] == "2 項在熱區，歷史上這種時候之後比較容易大跌：融資餘額水位（波動放大、最差 3 天跌幅）、散戶小台多空比（20 日內急跌）。"
    assert "1 個沒有變準、1 個資料太短沒有做" in ls[1] and ls[1].endswith("只當參考。")
    C2 = _C(now={"W2": 53.0}, preds={"W2": {"A2": _res("up")}, "T9": {"A1": _res("down")}})
    assert CP.lead(CP.items(C2)) == ["研究判定有差別的 2 項，現在都不在熱區：沒有「之後比較容易或比較不容易大跌」的條件成立。"]
    assert CP.lead([]) == ["扣掉現在的波動之後，沒有項目判定和之後大跌有關。"]
    C3 = _C("spx", now={"T9": 85.0}, preds={"T9": {"A1": _res("down", oos="better"), "A4": _res("down", oos="same")}})
    ls3 = CP.lead(CP.items(C3))
    assert ls3[0] == "1 項在熱區，歷史上這種時候之後比較不容易大跌：VIX（單日大跌、波動放大）。"
    assert "1 個變準、1 個沒有變準" in ls3[1]
    C4 = _C("ixic", now={"BL2": 100.0}, preds={"BL2": {"A4": _res("up")}})
    assert CP.lead(CP.items(C4))[0].startswith("1 個條件成立，")                 # 泡沫兩項寫「條件成立」


def test_value_formats_and_thresholds():
    assert CP.val("A2", 0.2851, 0.015) == "28.5%" and CP.val("A2", 0.2851, 0.015, True) == "29%"
    assert CP.val("A2", 0.059, 0.015, True) == "5.9%" and CP.val("A2", None, 0.015) == "—"
    assert CP.val("A5", 2.0297, 0.015233) == "−3.09%"                            # 最差 3 天平均＝−（÷ 標準差的跌幅 × 標準差）
    assert CP.dtxt("A4", 0.12486, 0.015) == "+12.5 個百分點" and CP.dtxt("A5", 0.53022, 0.015233) == "−0.81 個百分點"
    assert CP.citxt("A5", 0.28864, 0.78454, 0.015233) == "−1.20～−0.44"
    assert "跌 3% 以上" in CP.odef("tw", "A1") and "低 8% 以上" in CP.odef("tw", "A2") and "低 10% 以上" in CP.odef("tw", "A3")
    assert "跌 2% 以上" in CP.odef("spx", "A1", " S&P 500 ") and "低 15.5% 以上" in CP.odef("sox", "A3")
    assert [CP.zone_k(v) for v in (100, 80, 79.9, 60, 40, 20, 19.9, 0)] == [0, 0, 1, 1, 2, 3, 4, 4]


def test_zone_bars_cold_to_hot_and_todays_zone_colored():
    r = _res("up", hot=0.3)
    svg = CP.zbars("A2", r, 0.015, 0, False)
    assert svg.count("<rect") == 4                                            # < 20 那一區只有 12 天：不畫，寫 —
    labs = re.findall(r'class="kzl[^"]*"[^>]*>([^<]+)<', svg)
    assert [html.unescape(x) for x in labs] == [z for _, z in reversed(S.ZONES)]   # 由冷到熱
    assert 'class="zf4"' in svg and 'class="kzl on zt4"' in svg and svg.count('class="kza"') == 1
    flag = CP.zbars("A4", _res("up"), 0.015, 0, True)
    assert flag.count("<rect") == 2 and "成立" in flag and "不成立" in flag
    assert CP.zbars("A2", {"zones": []}, 0.015, 0, False) == ""


def test_card_structure_wording_and_banned_words():
    C = _C(now={"C1": 99.5, "C4": 86.0, "W2": 53.0, "BL2": 100.0, "BP1": 0.0},
           preds={"C1": {"A4": _res("up"), "A5": _res("up")}, "C4": {"A2": _res("up", oos=None)}, "W2": {"A2": _res("up")}})
    h = CP.card(C)
    assert h.startswith('<section class="sec xrsec" id="crash">') and h.endswith("</section>")
    assert h.count('<details class="xri"') == 3 and h.count('<details class="xri" data-p="C1" open>') == 1
    assert '<details class="xri" data-p="W2">' in h                              # 不熱的收起
    t = _text(h)
    assert "短線大跌風險" in t and "先看波動" in t and "資料到 10/16（五）" in t
    assert "熱、波動中（2002 年起的日子分三組），150 天" in t                     # 今天同樣狀態
    m = re.search(r'<table class="xrmt">(.*?)</table>', h, re.S).group(1)
    assert m.count("<tr>") == len(S.PRED["tw"]) + 1 and "成立" in m and "不成立" in m
    assert "4 個都沒有通過" in t and "HA1" in t and "HA4" in t and "HA3" not in t     # 台股頁只列台股有關的
    sp = _text(CP.card(_C("spx", now={"T9": 50.0})))
    assert "HA3" in sp and "樣本不足（熱的日子 20 天、3 段）" in sp and "HA1" not in sp and "台股" not in sp
    assert "3 項；現在熱的先列、已展開" in t and "點一下展開" not in t
    assert "S&P 500 是價格指數" in sp and "加權指數是價格指數（不含息）" in t
    assert "沒有一個是針對這個指數的" in _text(CP.card(_C("sox")))
    for w in BANNED:
        assert w not in h, w
    assert CP.card(None) == ""


def test_card_reads_the_committed_research_file():
    """研究檔（data/lab/crash_research.json）的格式和頁面對得上：五個市場都畫得出來，數字和研究檔一樣。"""
    R = K.load_research()
    if R is None:
        pytest.skip("研究檔還沒產生")
    for mk in S.MARKETS:
        N = {"d": "2026-10-16", "vol": 0.012, "preds": {p: {"v": 85.0, "hot": True, "g": {o: 1 for o in S.OUTCOMES}}
                                                         for p in S.PRED[mk]}}
        C = {"mk": mk, "px": "", "now": N, "vs": {}, "R": R["markets"][mk], "primary": R["primary"]}
        its = CP.items(C)
        n_sig = sum(1 for p in S.PRED[mk] for o in S.OUTCOMES
                    if R["markets"][mk]["preds"][p]["out"][o].get("v") in S.SHOW)
        assert sum(len(it["outs"]) for it in its) == n_sig
        h = CP.card(C)
        assert h.count('<details class="xri"') == len(its)
        for w in BANNED:
            assert w not in h, (mk, w)
    r = R["markets"]["tw"]["preds"]["C1"]["out"]["A4"]
    it = next(x for x in CP.items(C | {"mk": "tw", "R": R["markets"]["tw"],
                                       "now": {"d": "2026-10-16", "preds": {"C1": {"v": 99.0, "hot": True, "g": {"A4": 2}}}}})
              if x["p"] == "C1")
    row = next(x for x in it["outs"] if x["o"] == "A4")
    assert row["hot"] == r["hot"] and row["same"]["y"] == r["strata"][2][1] and row["d"] == r["d"]


def test_card_is_wired_into_both_heat_pages():
    """雷達下面、全部項目上面；頁首導覽多一個「大跌風險」；兩頁都載入卡片的樣式。"""
    viz = (ROOT / "arm/lab/heatviz.py").read_text(encoding="utf-8")
    assert "{top}{crash}{hotdd}{items}" in viz and '<a href="#crash">大跌風險</a>' in viz
    for f in ("arm/lab/heatpage.py", "arm/lab/heatpage_us.py"):
        assert "CP.CSS" in (ROOT / f).read_text(encoding="utf-8"), f
    hp = (ROOT / "arm/lab/heatpage.py").read_text(encoding="utf-8")
    assert '"crash": crash_now(B) if T else None' in hp
    css = set(re.findall(r"\.([a-zA-Z][\w-]*)", CP.CSS))
    from arm.lab import appnav
    from arm.lab import heatpage as HP
    from arm.lab import heatpage_us as HU
    from arm.lab import heatviz as VZ
    other = set(re.findall(r"\.([a-zA-Z][\w-]*)", HP._CSS + VZ.CSS + appnav.CSS + HU.CSS))
    shared = {"vt", "kzv"}                           # 景氣頁現成的 class，只在 .xr… 底下調整
    assert css - shared == {c for c in css if c.startswith("xr")} and not (css - shared) & other, \
        "卡片的 class 一律 xr 開頭、不和景氣頁撞名"
    for c in shared:
        assert re.search(r"\.xr\w+ \." + c + r"\b", CP.CSS), c
