"""景氣頁「大跌後檢查」卡（arm/lab/bottompage.py；docs/lab_crash_plan.md 第 13～15 節）：
一句話、進行中的事件、急跌之後的表現、等訊號再買、五個市場、每一次、主要假說、用字、class 前綴。
研究數字只讀研究檔，不在頁面重算。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from arm.lab import bottom as X
from arm.lab import bottompage as BP
from arm.lab import bottomspec as S

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatpage import BANNED  # noqa: E402


def _text(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'title="[^"]*"', "", h)))


def _R() -> dict:
    R = X.load_research()
    assert R and R["ver"] == S.VER, "研究檔要先跑：TZ=Asia/Taipei python3 scripts/run_bottom.py"
    return R


def _active(mk: str, ev: str = "E5", also: bool = True, fired: str | None = "C1") -> dict:
    sig = {k: {"st": "wait", "left": 40} for k in S.SIG_MK[mk]}
    if fired and fired in sig:
        sig[fired] = {"st": "on", "d": "2026-10-20", "after": 4}
    a = {"ev": ev, "t": "2026-10-14", "p": "2026-10-06", "ppx": 13217.8, "days": 4, "depth": -0.106 if ev == "E5" else -0.11,
         "low": "2026-10-16", "lowdd": -0.157, "nowdd": -0.12, "g": {"fund": 1, "chip": 0, "bub": 1},
         "gv": {"fund": 70.4, "fund0": 59.5, "chip": 75.0, "bub": 2}, "sig": sig, "w10": {"st": "wait", "left": 6}}
    if also and ev == "E5":
        a["also"] = "E10"
    return a


def _C(mk: str = "tw", active: list | None = None) -> dict:
    R = _R()
    now = {"d": "2026-10-20", "dd60": -0.054, "active": active or [], "last": {"E5": "2026-06-10", "E10": "2026-07-17"}}
    px = "加權指數" if mk == "tw" else f' {BP.MKN[mk]} '
    return {"mk": mk, "px": px, "now": now, "R": R["markets"][mk], "all": R["markets"], "primary": R["primary"]}


def test_lead_inactive_uses_research_numbers():
    for mk in S.MARKETS:
        C = _C(mk)
        ls = BP.lead(C)
        assert len(ls) == 3
        assert ls[0].startswith("現在沒有大跌：") and f"5 日跌 {S.E5_TH[mk] * 100:g}% 以上" in ls[0]
        E = C["R"]["ev"]["E5"]
        A = E["all"]
        assert f'{E["n"]} 次 5 日急跌' in ls[1] and f'{BP.pct(A["nl"]["rate"], 0)}' in ls[1]
        assert BP.spct(A["r60"]["mean"]) in ls[1]
        w = E["rules"]["W10"]
        assert f'固定等 10 天也從 {BP.pct(w["nl_b1"], 0)} 降到 {BP.pct(w["nl_rule"], 0)}' in ls[2]
        good = [k for k in S.SIG_MK[mk] if E["rules"][k]["v"] == "better"]
        if good:
            assert "、".join(BP.SHORT[k] for k in good) + "有用" in ls[2]
        else:
            assert "沒有一個訊號有用" in ls[2]
        beat = [k for k in S.SIG_MK[mk] if E["rules"][k].get("n") and not E["rules"][k]["few"]
                and ((E["rules"][k].get("w10") or {}).get("nl_hi") or 1) < 0]
        for k in beat:
            assert BP.SHORT[k] in ls[2].split("比固定等 10 天還少的")[1]
    us = BP.lead(_C("spx"))[0]
    assert "S&P 500 離 60 日高點" in us                           # 英文名後面要有空白


def test_lead_active_event():
    C = _C("sox", [_active("sox")])
    l0 = BP.lead(C)[0]
    assert l0.startswith("費半 2026/10/14 出現 5 日急跌（5 日跌 10.6%），同一天也從 60 日高點跌了 10% 以上")
    assert "現在比 2026/10/6 的高點低 12.0%" in l0 and "事件後第 4 個交易日" in l0
    C = _C("tw", [_active("tw", "E10", also=False)])
    assert BP._ev_main(C) == "E10"
    ls = BP.lead(C)
    assert "2026/10/14 起從 60 日高點跌 10% 以上" in ls[0] and "次從 60 日高點跌 10%" in ls[1]


def test_card_structure_and_banned_words():
    for mk in S.MARKETS:
        for act in (None, [_active(mk)]):
            C = _C(mk, act)
            h = BP.card(C)
            t = _text(h)
            assert h.count('id="bottom"') == 1 and "大跌後檢查" in t and "只描述過去，不是買賣指示" in t
            n_rules = 1 + len(S.SIG_MK[mk])
            assert h.count('<table class="xjrt">') == 2 and h.count('<table class="xjdt">') == 2   # 兩種事件各一張
            rt = h[h.index('<table class="xjrt">'):h.index("</table>", h.index('<table class="xjrt">'))]
            assert rt.count("<tr") == 1 + n_rules
            ft = h[h.index('<table class="xjft">'):h.index("</table>", h.index('<table class="xjft">'))]
            assert ft.count("<tr") == 1 + len(S.RULES)
            dt = h[h.index('<table class="xjdt">'):h.index("</table>", h.index('<table class="xjdt">'))]
            assert dt.count("<tr") == 1 + 1 + 2 * len(S.GROUPS)
            if act:                                           # 進行中：展開這一次，研究結果不收起來
                assert "這一次：2026/10/14 5 日急跌" in t and 'class="xjmore xjres"' not in h
                st = h[h.index('<table class="xjst">'):h.index("</table>", h.index('<table class="xjst">'))]
                assert st.count("<tr") == 1 + n_rules
                assert ("已出現 2026/10/20（第 4 天）" in t) == ("C1" in S.SIG_MK[mk])
                assert "還沒（還有 6 個交易日）" in t       # 固定等 10 天
            else:
                assert 'class="xjmore xjres"' in h and "這一次：" not in t
            for w in BANNED:
                assert w not in h, (mk, w)


def test_rule_numbers_come_from_research():
    C = _C("tw")
    h = BP.rule_table(C, "E5")
    r = C["R"]["ev"]["E5"]["rules"]["C7"]
    assert f'{BP.pct(r["nl_b1"], 0)} → <b>{BP.pct(r["nl_rule"], 0)}</b>' in h
    assert f'{BP.spct(r["r_b1"])} → <b>{BP.spct(r["r_rule"])}</b>' in h
    assert BP.VSHORT[r["v"]] in _text(h)
    w = r["w10"]
    assert f'再跌破低點 <b>{BP._sp(w["nl_d"], 0)}</b>' in h


def test_five_markets_and_lists():
    C = _C("spx")
    f = _text(BP.five_html(C, "E5"))
    assert f.count("不算") >= 5 * 4                           # 美股四個指數沒有融資、寬度、新低、P/C、90% 上漲日
    for k in S.RULES:
        vs = [((C["all"][m]["ev"]["E5"]["rules"].get(k) or {}).get("v")) for m in S.MARKETS
              if k == "W10" or k in S.SIG_MK[m]]
        nf = [v for v in vs if v != "few"]
        if len(nf) >= 2 and len(set(nf)) == 1:
            assert re.search(BP.SHORT[k] + r".*一致", f)
    h = BP.list_html(_C("tw"), "E5")
    L = _R()["markets"]["tw"]["ev"]["E5"]["list"]
    assert h.count("<tr") == 1 + min(len(L), BP.LIST_MAX) and f"共 {len(L)} 次" in _text(h)


def test_primary_html():
    C = _C("tw")
    t = _text(BP.primary_html(C))
    P = C["primary"]
    assert f'{sum(1 for h in S.PRIMARY if P[h].get("ok"))} 個成立' in t
    for h in S.PRIMARY:
        assert h in t
        if not P[h].get("few"):
            assert f'Holm 校正後 p＝{P[h]["padj"]:.3f}' in t


def test_card_is_wired_into_both_heat_pages_and_classes_are_prefixed():
    viz = (ROOT / "arm/lab/heatviz.py").read_text(encoding="utf-8")
    assert "{top}{crash}{bottom}{hotdd}{hotch}{items}" in viz and '<a href="#bottom">大跌後</a>' in viz
    for f in ("arm/lab/heatpage.py", "arm/lab/heatpage_us.py"):
        assert "BP.CSS" in (ROOT / f).read_text(encoding="utf-8"), f
    hp = (ROOT / "arm/lab/heatpage.py").read_text(encoding="utf-8")
    assert '"bottom": bottom_now(B) if T else None' in hp
    css = set(re.findall(r"\.([a-zA-Z][\w-]*)", BP.CSS))
    from arm.lab import appnav
    from arm.lab import crashpage as CP
    from arm.lab import heatpage as HP
    from arm.lab import heatpage_us as HU
    from arm.lab import heatviz as VZ
    from arm.lab import hotchpage as QP
    from arm.lab import hotddpage as XP
    other = set(re.findall(r"\.([a-zA-Z][\w-]*)", HP._CSS + VZ.CSS + appnav.CSS + HU.CSS + CP.CSS + XP.CSS + QP.CSS))
    shared = {"l", "vt"}                                # 景氣頁現成的 class，只在 .xj… 底下調整
    assert css - shared == {c for c in css if c.startswith("xj")} and not (css - shared) & other, \
        "卡片的 class 一律 xj 開頭、不和景氣頁撞名"
    assert re.search(r"\.xjul \.vt\b", BP.CSS)
    for c in ("l",):
        assert re.search(r"table\.xj\w+ \." + c + r"\b", BP.CSS), c


def test_committed_research_file_matches_spec():
    R = _R()
    assert set(R["markets"]) == set(S.MARKETS) and set(R["primary"]) == set(S.PRIMARY)
    for mk in S.MARKETS:
        M = R["markets"][mk]
        assert M["th"] == S.E5_TH[mk] and set(M["ev"]) == set(S.EVENTS)
        for ev in S.EVENTS:
            E = M["ev"][ev]
            assert set(E["rules"]) == {"W10", *S.SIG_MK[mk]} and set(E["groups"]) == set(S.GROUPS)
            assert all(st["v"] in S.VERDICT for st in E["rules"].values())
            assert all(st["v"] in S.GVERDICT for st in E["groups"].values())
            assert len(E["list"]) == E["n"]
