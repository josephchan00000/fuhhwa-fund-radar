"""實測區（arm/lab/practpage.py、practlive.py；docs/lab_practice_page_plan.md）：前瞻紀錄的規則、頁面結構、用字。"""
import json
import re
from datetime import date, timedelta

import numpy as np
import pytest

from arm.lab import practlive as PL
from arm.lab import practpage as PP
from arm.lab import practsim as P
from arm.lab import practspec as S
from arm.lab import sigpage as SP
from arm.lab import sigspec as SS

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買", "建議賣", "目標價", "零風險", "無風險")


def _cal(n: int, start: str = "2026-10-19") -> list[str]:
    out, d = [], date.fromisoformat(start)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_series_matches_compare():
    rng = np.random.default_rng(3)
    n = 400
    cal = _cal(n, "2020-01-01")
    px = 100 * np.cumprod(1 + rng.normal(0.0003, 0.01, n))
    p = rng.choice([0.5, 1.0], size=n)
    c = 0.001
    a = 5
    cost = P.turn_cost(p, c)
    cmp = P.compare(cal, P.daily_ret(px), p, cost, a, n)
    idx = [i for i in range(a, n, 5)] + [n - 1]
    sr = P.series(px, p, cost, a, cmp["wbar"], idx)
    g = P.group_series(cal, px, a, idx)
    want = float(np.prod(1 + P.day_ret(P.daily_ret(px), p, cost, a, n)))
    assert sr["nav"][-1] == pytest.approx(want, abs=1e-4)
    assert g["bh"][-1] == pytest.approx(px[-1] / px[a], abs=1e-4) and g["d"][0] == cal[a] and sr["nav"][0] == 1.0
    assert sr["pos"] == [round(float(p[i]), 3) for i in idx]


def test_live_positions_thermo_waits_for_week_end():
    """溫度計規則：第一筆紀錄的下一個交易日收盤才照做；之後只有週末的紀錄在下一個交易日收盤生效；沒紀錄的週末沿用。"""
    cal = _cal(15)                                     # 2026-10-19（一）起三週
    log = {cal[0]: {"A1": 0.5}, cal[2]: {"A1": 1.0}, cal[4]: {"A1": 1.0}, cal[9]: {}}
    p, s, gap = PL.positions(cal, log, "A1")
    assert s == 1 and np.isnan(p[0]) and p[1] == 0.5
    assert all(p[k] == 0.5 for k in range(1, 5))       # 週三的紀錄不算；週五（cal[4]）的決定在下週一（cal[5]）收盤生效
    assert all(p[k] == 1.0 for k in range(5, 15)) and gap == 1     # cal[9]（週五）沒有 A1 的紀錄 → 沿用
    M = {cal[0]: {"M2": 0.2}, cal[1]: {"M2": 0.4}, cal[3]: {"M2": 0.0}}
    q, s2, gap2 = PL.positions(cal, M, "M2")
    assert s2 == 0 and list(q[:5]) == [0.2, 0.4, 0.4, 0.0, 0.0] and gap2 == 12


def test_live_merge_dates_and_overwrite(tmp_path, monkeypatch):
    new = {"tw": {"d": "2026-10-22", "xd": "2026-10-22", "t": {"A1": 0.5, "M2": 0.2222}},
           "spx": {"d": "2026-10-21", "xd": "2026-10-21", "t": {"A1": 1.0, "M2": 0.4}}}
    L = PL.merge({"mk": {"tw": {"2026-10-22": {"A1": 1.0}}}}, new)
    assert L["mk"]["tw"]["2026-10-22"] == {"A1": 0.5, "M2": 0.2222}
    assert L["mk"]["spx"]["2026-10-21"]["M2"] == 0.4
    path = tmp_path / "live.json"
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    PL.update(new, path)
    assert not path.exists()                           # 本機不寫
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    PL.update(new, path)
    assert json.loads(path.read_text())["mk"]["tw"]["2026-10-22"]["A1"] == 0.5


def test_thermo_targets_follow_rules():
    C = {k: {"up": {"n": 3, "grp": "lo"}, "warn": {"n": 9, "grp": "hi"}} for k in SS.THERMO_H}
    C["long"]["warn"]["grp"] = "mid"
    t = PL.thermo_targets(C)
    assert t == {"A1": 0.5, "A2": 0.5, "A3": 1.0, "A4": 0.5, "B1": 0.5, "D1": 1.0}
    C["short"]["up"]["grp"] = None
    assert PL.thermo_targets(C) == {}


def test_forward_counts_from_log():
    cal = _cal(80)
    px = np.linspace(100, 120, 80)
    D = {"mk": "spx", "cal": cal, "px": px}
    log = {cal[0]: {"M2": 0.5, "A1": 1.0}}
    fw = PL.forward(log, D)
    assert fw["M2"]["n"] == 79 and fw["M2"]["ok"] and fw["A1"]["n"] == 78
    assert fw["M2"]["bh"] == pytest.approx(0.2)
    assert 0 < fw["M2"]["ret"] < fw["M2"]["bh"]


def _fake_R():
    rng = np.random.default_rng(5)
    mk_out = {}
    for mk in S.MARKETS:
        rules = {}
        for k in S.RULES:
            def blk():
                return {"rule": {"cagr": 0.05, "mdd": 0.3, "sharpe": 0.5, "worst": -0.2, "adj": 6.0, "a": "2000-01-03", "z": "2026-10-21",
                                 "yearly": [["2001", 0.1], ["2002", -0.1]]},
                        "fix": {"cagr": 0.04, "mdd": 0.4, "sharpe": 0.45, "worst": -0.25, "yearly": [["2001", 0.08], ["2002", -0.12]]},
                        "bh": {"cagr": 0.07, "mdd": 0.55, "sharpe": 0.45, "worst": -0.4, "yearly": [["2001", 0.12], ["2002", -0.3]]},
                        "wbar": 0.7}
            rules[k] = {"full": blk(), "h1": blk(), "h2": blk(), "rec": blk(), "v": S.VERDICTS[int(rng.integers(0, 3))],
                        "ci": [-0.1, 0.2], "now": 0.5, "bears": [{"pk": "2008-05-19", "tr": "2008-11-20", "bh": -0.5, "rule": -0.2, "fix": -0.3}]}
        mk_out[mk] = {"rules": rules, "t_a": "2006-02-03", "x_a": "2002-01-02"}
    return {"ver": 1, "run": "x", "mk": mk_out, "page": P.page_check(mk_out)}


def test_payload_and_fold_html():
    """完整研究表裡的實測（2026-10-22 改版）：選做法的按鈕＋細節的位置；原本的判定總表、前瞻紀錄格子、內部術語都拿掉。"""
    R = _fake_R()
    Pl = PP.payload(R)
    assert Pl["ok"] and [r["k"] for r in Pl["rules"]] == list(S.RULES)
    h = PP.html(Pl)
    assert h.count('class="prpk"') == len(S.RULES) and 'id="prd"' in h and 'id="prfw"' not in h and 'class="prc' not in h
    txt = re.sub(r"<[^>]+>", "", h)
    for w in BANNED + ("候選", "門檻", "夏普", "固定持有", "practspec", "VER"):
        assert w not in txt, w
    assert "起每天記下" not in txt
    assert "台股 2026/10/22、美股 2026/10/21 起每天記下" in re.sub(r"<[^>]+>", "", PP.html(PP.payload(R, {}, {}, {"tw": "2026-10-22", "spx": "2026-10-21"})))
    J = json.loads(PP.market_json(R, "tw"))
    assert set(J["det"]) == set(S.RULES) and J["det"]["A1"]["y"][0] == ["2001", 10.0, 8.0, 12.0]
    for k in ("固定", "報酬 ÷ 波動", "候選"):
        assert k not in PP.JS, k                                # 細節也不再和「每天固定拿一樣多」比


def test_css_and_js_are_prefixed_and_do_not_collide():
    classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", PP.CSS))
    shared = {"note", "sub", "on", "ng", "mu", "lb", "vl", "cp", "lk", "cap", "gl", "bz", "lr", "lb2", "ar", "hv", "hit", "l", "lbx",
              "r", "b", "z"}
    assert all(c.startswith("pr") or c in shared for c in classes), sorted(c for c in classes if not c.startswith("pr") and c not in shared)
    fn_pr = set(re.findall(r"function (\w+)\(", PP.JS))
    assert fn_pr and all(f.startswith("pr") for f in fn_pr)
    base = SP.JS.replace(PP.JS, "")
    fn_sg = set(re.findall(r"function (\w+)\(", base))
    assert not (fn_pr & fn_sg)
    assert "/*@@PRACTICE@@*/" not in SP.JS and "prOpen(m[1], m[2], true)" in SP.JS
    assert SP.JS.index(PP.JS) < SP.JS.index("draw(); fromHash();")      # 插在初始化之前（否則 #p= 直連會碰到還沒初始化的 const）


def test_research_section_has_practice_in_fold():
    """實測的細節收在研究結論最下面的「完整研究表」；研究結論第 1 則在上面。"""
    R = _fake_R()
    d = ["2006-01-06", "2016-01-08", "2026-01-09"]
    R["mk"]["tw"]["t_series"] = {"d": d, "bh": [1.0, 2.0, 4.0], "r": {"A1": {"nav": [1.0, 1.5, 2.5], "pos": [1, 0.5, 1], "fix": [1, 1, 1]}}}
    R["mk"]["tw"]["x_series"] = {"d": d, "bh": [1.0, 2.0, 4.0], "r": {"M2": {"nav": [1.0, 1.4, 2.0], "pos": [0.4, 0.4, 0.4]}}}
    V = {"rmk": ["tw"], "pr": {"P": PP.payload(R), "R": R}}
    h = SP.research_html(V)
    assert h.index('id="rf-money"') < h.index('id="rfull"') < h.index('id="pr"') < h.index('id="rbox"')
    assert "250 萬" in h and "400 萬" in h and "不能" in h
    assert SP.research_html({"rmk": [], "pr": {"P": {"ok": False}}}) == ""


def test_workflows_commit_practice_files():
    """三支會建頁的 workflow 都要 add 實測區的資料檔（分開 add；缺檔不連累其他檔）與 data/lab（前瞻紀錄在裡面）。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for f in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        s = (root / f).read_text(encoding="utf-8")
        assert s.count("git add -f dashboard/x9pr-*.json 2>/dev/null || true") == 2, f
        assert "git add -f data/lab " in s, f
