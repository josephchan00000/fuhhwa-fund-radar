"""部位參考卡（arm/lab/pospage.py；docs/lab_crash_plan.md 第 18～19 節）。"""
import re
from pathlib import Path

import numpy as np

from arm.lab import pos as P
from arm.lab import pospage as PP
from arm.lab import posspec as S

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買", "建議賣", "目標價", "零風險", "無風險")


def _C():
    rng = np.random.default_rng(5)
    px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, 2000)))
    cal = [f"{2000 + i // 250}-{1 + (i // 21) % 12:02d}-{1 + i % 21:02d}" for i in range(2000)]
    act = {d: np.zeros(2000, dtype=bool) for d in ("warn", "buy", "up")}
    act["warn"][1500:1600] = True
    M = P.run_market("spx", cal, px, act)
    M["ids"], M["days"] = {"warn": ["spx:heat:S1:cold_in"], "buy": [], "up": []}, {}
    now = P.now("spx", cal, px, {"spx:heat:S1:cold_in": {"since": cal[-3]}}, M["ids"])
    return {"mk": "spx", "M": M, "now": now, "names": {"spx:heat:S1:cold_in": "資產管理人期貨淨多單・進入過冷"}}


def test_card_lead_chart_table_and_wording():
    C = _C()
    h = PP.card(C)
    assert 'id="pos"' in h and "<h2>部位參考</h2>" in h and "<svg" in h and h.count("<polyline") == 3
    assert f'今天的部位參考 {100 * C["now"]["pos"][S.MAIN]:.0f}%' in h and "★ 警示有效（資產管理人期貨淨多單・進入過冷）→ 最多 50%" in h
    assert all(S.VERSION_NAMES[k] in h for k in S.VERSIONS) and "不是買賣指示" in h and "樣本內" in h
    txt = re.sub(r"<[^>]+>", "", h)
    for w in BANNED:
        assert w not in txt, w
    assert PP.card(None) == ""
    css = set(re.findall(r"\.([a-zA-Z][\w-]*)", PP.CSS))
    assert css and all(c.startswith("xv") for c in css - {"card", "sec", "l"}), css     # 只借用 td.l


def test_chip_and_wiring():
    C = _C()
    ch = PP.chip(C)
    assert 'href="x9o.html#r=spx:pos"' in ch and "<b>部位參考</b>" in ch and "回測" in ch and "不是買賣指示" in ch
    assert PP.chip(None) == "" and PP.chip(dict(C, now=None)) == ""
    hp = (ROOT / "arm/lab/heatpage.py").read_text(encoding="utf-8")
    assert 'out["pos"] = pos_now(out["signow"])' in hp and "chips.append(pospage.chip(V.get(\"pos\")))" in hp
    viz = (ROOT / "arm/lab/heatviz.py").read_text(encoding="utf-8")
    assert '"pos": PSP.card(V.get("pos"))' in viz
    from arm.lab import sigpage
    assert sigpage.CARD_ORDER[0] == "pos" and sigpage.CARD_NAMES["pos"] == "部位參考"
    assert "PSP.CSS" in (ROOT / "arm/lab/sigpage.py").read_text(encoding="utf-8")


def test_committed_research_matches_spec():
    R = P.load()
    assert R is not None and R["ver"] == S.VER and set(R["mk"]) == set(S.MARKETS)
    for mk, M in R["mk"].items():
        assert set(M["m"]) == set(S.VERSIONS) and set(M["verdict"]) == set(S.VERSIONS) - {"full"}
        assert all(v in S.VERDICTS for v in M["verdict"].values())
        assert M["m"]["full"]["avg_w"] == 1.0 and M["m"]["full"]["tr_y"] == 0
        assert len(M["curve"]["d"]) == len(M["curve"]["full"])
    assert "tr" in R["mk"]["tw"]
