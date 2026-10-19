"""景氣頁「過熱之後 3 個月的最大回撤」卡（arm/lab/hotddpage.py；docs/lab_hotdd_plan.md 第 4.9、6 節）：
一句話、研究重點、平常、現在過熱中（面向在前、展開）、剛結束過熱、點圖、清單上限、判定表、主要假說、用字、class 前綴。
研究數字只讀研究檔，不在頁面重算。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

from arm.lab import hotdd as K
from arm.lab import hotddpage as XP
from arm.lab import hotddspec as S

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatpage import BANNED  # noqa: E402


def _st(v="none", n=12, ep=10, med=0.08, a="2001-02-01"):
    lst = [[f"{2001 + i}-03-0{1 + i % 8}", 0.03 + 0.01 * i, 0.02, 0.01 * (i - 5), f"{2001 + i}-03-10", f"{2001 + i}-04-10", 85.0]
           for i in range(n)]
    base = {"mean": 0.09, "med": 0.07, "p25": 0.04, "p75": 0.12, "p90": 0.2, "q10": 0.35, "q20": 0.1, "r60": 0.02, "up": 0.6}
    return {"n": n, "ep": ep, "v": v, "a": a, "z": "2025-01-01",
            "ev": {"mean": med, "med": med, "p25": 0.04, "p75": 0.1, "p90": 0.15, "q10": 0.3, "q20": 0.05, "dd0": 0.03,
                   "r60": 0.02, "up": 0.6},
            "base": base, "d": med - 0.09, "lo": -0.02, "hi": 0.02, "h1": 0.0, "h2": 0.0, "vadj": 0.001, "q": 0.5,
            "worst": {"d": lst[-1][0] if lst else None, "mdd": lst[-1][1] if lst else None, "pk": "2012-03-10", "tr": "2012-04-10"},
            "list": lst}


def _inst(d="2026-09-30", mdd=0.057, days=10, full=False):
    return {"d": d, "days": days, "full": full, "mdd": mdd, "pk": "2026-10-06", "tr": "2026-10-15", "chg": -0.026}


def _C(mk="tw", hot=None, exits=None, rows=None):
    dims = ["fund", "chip", "tech"] if mk == "tw" else ["fund", "tech"]
    items = ["C1", "C2", "T2"]
    rows = rows or {}
    R = {"start": "1997-07-02", "end": "2026-10-16",
         "base": {"n": 7192, "mean": 0.102, "med": 0.076, "p25": 0.04, "p75": 0.13, "p90": 0.207, "q10": 0.38, "q20": 0.11,
                  "r60": 0.02, "up": 0.61},
         "rows": {k: {"kind": "dim" if k in dims else "item", "first": "2001-01-01",
                      "ev": {e: (rows.get(k) or {}).get(e) or _st() for e in S.EVENTS},
                      "rec": {"10": {"n": 35, "h1": 20, "h4": 9, "c1": 0.48, "c4": 0.12},
                              "20": {"n": 10, "h1": 6, "h4": 1, "c1": 0.48, "c4": 0.12}}}
                  for k in dims + items},
         "decl": {"20": [{"pk": "2008-05-19", "tr": "2008-11-20", "dd": 0.56, "open": False,
                          "dims": {d: ([1, 1] if d == "tech" else [0, 0]) for d in dims}},
                         {"pk": "2026-06-22", "tr": "2026-07-29", "dd": 0.29, "open": True, "dims": {d: None for d in dims}}]}}
    R["rows"]["M2"] = {"kind": "mkt", "first": "2009-01-01", "ev": {"E": _st("few", n=3, ep=3)}}
    N = {"d": "2026-10-16", "hot": hot or [], "exit": exits or [], "multi": {"n": 1, "have": 3, "dims": ["fund"]}}
    names = {"fund": "基本面熱度", "chip": "籌碼熱度", "tech": "技術面熱度", "C1": "融資餘額水位", "C2": "融資 20 日增減",
             "T2": "對 60 日線乖離"}
    names.update(S.MKT_NAMES)
    short = {"fund": "基本面", "chip": "籌碼", "tech": "技術"}
    tags = {d: "面向" for d in dims}
    tags.update({"C1": "籌碼", "C2": "籌碼", "T2": "技術"})
    today = {k: ("50", False) for k in dims + items}
    return {"mk": mk, "px": "加權指數" if mk == "tw" else "S&P 500", "R": R, "now": N, "primary": {
        "HD1": {"n": 40, "ep": 31, "d": -0.016, "lo": -0.032, "hi": 0.001, "p1": 0.97, "padj": 1.0, "h1": -0.03, "h2": 0.003,
                "ok": False, "few": False},
        "HD2": {"n": 13, "ep": 11, "d": -0.004, "lo": -0.04, "hi": 0.03, "p1": 0.66, "padj": 1.0, "ok": False, "few": False},
        "HD3": {"n": 15, "ep": 12, "d": -0.003, "lo": -0.03, "hi": 0.03, "p1": 0.58, "padj": 1.0, "ok": False, "few": False},
        "HD4": {"n": 37, "ep": 31, "d": -0.001, "lo": -0.02, "hi": 0.02, "p1": 0.58, "padj": 1.0, "ok": False, "few": False}},
        "dims": dims, "items": items, "names": names, "tags": tags, "short": short, "today": today}


def _hot(k, kind, wk, v=90.0):
    ev = ["E"] + ([f"S{n}" for n in S.STREAK_N if n <= wk][-1:])
    inst = {e: _inst() for e in ev}
    return {"k": k, "kind": kind, "v": v, "wk": wk, "start": "2026-09-30", "ev": ev, "inst": inst}


def _text(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", h))


def test_lead_counts_verdicts_of_hot_rows():
    C = _C(hot=[_hot("fund", "dim", 27), _hot("C1", "item", 46), _hot("C2", "item", 2)],
           rows={"C1": {"E": _st("down"), "S26": _st("few", n=5, ep=5)}, "C2": {"E": _st("none")}})
    ls = XP.lead(C)
    assert ls[0] == "現在過熱中：1 個面向（基本面已連續 27 週），另有 2 個項目。"
    assert "沒有一項判定比平常大" in ls[1]
    assert "進入過熱之後：比平常小 1 項、看不出差別 2 項" in ls[1]
    assert "連續過熱滿 N 週之後（已連續 4 週以上的 2 項）：看不出差別 1 項、次數太少 1 項" in ls[1]
    C2 = _C(hot=[_hot("T2", "item", 1)], rows={"T2": {"E": _st("up")}})
    assert XP.lead(C2)[0] == "現在過熱中：1 個項目。" and "有 1 個判定比平常大" in XP.lead(C2)[1]
    assert XP.lead(_C()) == ["現在沒有面向或項目在過熱（0～100 在 80 以上）。"]


def test_formats():
    assert XP.pct(0.1234) == "12.3%" and XP.pct(None) == "—" and XP.pct(0.38, 0) == "38%"
    assert XP.spct(-0.026) == "−2.6%" and XP.spct(0.02) == "+2.0%" and XP.spct(-0.0004) == "0.0%"
    assert XP.ppt(-0.0158) == "−1.6 個百分點" and XP.ci(-0.032, 0.001) == "−3.2～+0.1 個百分點"
    assert XP._d("2024-07-11") == "2024/7/11" and XP._d(None) == "—"


def test_strip_dots_band_median_and_this_time():
    st = _st(n=30)
    h = XP.strip(st["list"], st["base"], _inst(full=False), 0.4, "測試")
    assert h.count('class="xodt') == 30 and h.count('class="xonw xopart"') == 1
    assert 'class="xobd" style="left:10.00%;width:20.00%"' in h          # 平常中間一半：4%～12% → 10%～30%
    assert 'class="xobm" style="left:17.50%"' in h                       # 中位數 7%
    assert h.count("<span style=") == 5                                    # 0%、10%、20%、30%、40%
    full = XP.strip(st["list"], st["base"], _inst(full=True), 0.4, "測試")
    assert 'class="xonw"' in full
    # 點的排：同一排相鄰兩點至少隔 GAP（四排都滿才允許重疊）
    xs = [1.0, 1.5, 2.0, 2.5, 3.0, 10.0]
    rw = XP._rows(xs)
    for r in range(XP.ROWS_MAX):
        pts = sorted(x for x, k in zip(xs, rw) if k == r)
        assert all(b - a >= XP.GAP for a, b in zip(pts, pts[1:])) or r == min(rw[:5])


def test_xmax_and_block_list_cap():
    C = _C(hot=[_hot("tech", "dim", 5)], rows={"tech": {"E": _st(n=30), "S4": _st(n=3, ep=3, v="few")}})
    assert XP.xmax_of(C) == pytest.approx(0.4)                             # 最大 0.32 → 取到 40%
    b = XP.block(C, "tech", "E", _inst(), 0.4)
    assert "最近 20 次（共 30 次，點圖畫全部）" in _text(b)
    assert b.count("<tr>") == XP.LIST_MAX + 1 and b.count('class="xocur"') == 1   # 標題列＋20 次；這一次另一列
    nothing = XP.block(C | {"R": C["R"] | {"rows": {"tech": {"ev": {"E": {"n": 0, "v": "few"}}}}}}, "tech", "E", None, 0.4)
    assert "過去沒有這種情況" in _text(nothing)


def test_card_structure_wording_and_banned_words():
    C = _C(hot=[_hot("fund", "dim", 27), _hot("C1", "item", 46)],
           exits=[{"k": "C2", "kind": "item", "v": 70.0, "inst": {"X4": _inst("2026-08-14", full=True, days=45)}}])
    h = XP.card(C)
    assert h.startswith('<section class="sec xosec" id="hotdd">') and h.endswith("</section>")
    assert h.count('<details class="xoi"') == 3
    assert '<details class="xoi" data-k="fund" open>' in h and '<details class="xoi" data-k="C1">' in h   # 面向展開、項目收起
    t = _text(h)
    assert "過熱之後 3 個月的最大回撤" in t and "資料到 10/16（五）" in t
    assert "平常（1997 年起任挑一天，共 7,192 天）之後 3 個月：" in t and "7.6%" in t
    assert "最近 3 個月結束過熱" in t and "2026/8/14 結束過熱" in t
    assert "大跌前 3 個月有沒有過熱（跌 20% 以上的 2 次）" in t and "還沒反彈" in t
    m = re.search(r'<table class="xomt">(.*?)</table>', h, re.S).group(1)
    assert m.count("<tr>") == 1 + 3 + 1 + 3                                 # 標題＋面向＋綜合（M2）＋項目
    assert "4 個都沒有通過" in t and "HD1" in t and "HD3" in t and "HD4" not in t      # 台股頁只列台股有關的
    sp = _text(XP.card(_C("spx")))
    assert "HD4" in sp and "HD1" not in sp and "S&P 500 接下來" in sp and "台股" not in sp
    assert "沒有一個是針對這個指數的" in _text(XP.card(_C("sox")))
    for w in BANNED:
        assert w not in h, w
    assert XP.card(None) == ""


def test_card_reads_the_committed_research_file():
    """研究檔（data/lab/hotdd_research.json）的格式和頁面對得上：五個市場都畫得出來，數字和研究檔一樣。"""
    R = K.load_research()
    if R is None:
        pytest.skip("研究檔還沒產生")
    for mk in S.MARKETS:
        RM = R["markets"][mk]
        dims = RM["dims"]
        items = RM["items"]
        hot = [_hot(k, "dim" if k in dims else "item", 30) for k in (dims + items)[:6]]
        C = {"mk": mk, "px": "", "R": RM, "now": {"d": RM["end"], "hot": hot, "exit": [],
                                                   "multi": {"n": 0, "have": 4, "dims": []}},
             "primary": R["primary"], "dims": dims, "items": items, "names": {k: k for k in dims + items + list(S.MKT_VARS)},
             "tags": {}, "short": {d: d for d in dims}, "today": {}}
        h = XP.card(C)
        assert h.count('<details class="xoi"') == len(hot)
        assert XP.pct(RM["base"]["med"]) in _text(h)
        for w in BANNED:
            assert w not in h, (mk, w)
        k0 = (dims + items)[0]
        st = RM["rows"][k0]["ev"]["E"]
        if st.get("n"):
            assert f'中位數 {XP.pct(st["ev"]["med"])}' in _text(h)


def test_card_is_wired_into_both_heat_pages_and_classes_are_prefixed():
    """大跌風險下面、全部項目上面；頁首導覽多一個「過熱後回撤」；兩頁都載入卡片的樣式；class 一律 xo 開頭。"""
    viz = (ROOT / "arm/lab/heatviz.py").read_text(encoding="utf-8")
    # 2026-10-19 起四張研究卡搬到訊號總覽（docs/lab_signal_plan.md 第 10 節 Q3）：景氣頁照樣算、不放進頁面，存給訊號總覽
    assert "stash_cards(V)" in viz and "{top}{items}" in viz and 'href="#hotdd"' not in viz
    sp = (ROOT / "arm/lab/sigpage.py").read_text(encoding="utf-8")
    assert "XP.CSS" in sp and '"hotdd"' in sp
    hp = (ROOT / "arm/lab/heatpage.py").read_text(encoding="utf-8")
    assert '"hotdd": hotdd_now(B) if T else None' in hp
    css = set(re.findall(r"\.([a-zA-Z][\w-]*)", XP.CSS))
    from arm.lab import appnav
    from arm.lab import crashpage as CP
    from arm.lab import heatpage as HP
    from arm.lab import heatpage_us as HU
    from arm.lab import heatviz as VZ
    other = set(re.findall(r"\.([a-zA-Z][\w-]*)", HP._CSS + VZ.CSS + appnav.CSS + HU.CSS + CP.CSS))
    shared = {"vt"}                                  # 景氣頁現成的 class，只在 .xo… 底下調整
    assert css - shared == {c for c in css if c.startswith("xo")} and not (css - shared) & other, \
        "卡片的 class 一律 xo 開頭、不和景氣頁撞名"
    for c in shared:
        assert re.search(r"\.xo\w+ \." + c + r"\b", XP.CSS), c
