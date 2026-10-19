"""訊號總覽頁（arm/lab/sigpage.py；docs/lab_signal_plan.md 第 5 節）。"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from arm.lab import appnav, sigcat, sigpage, sigspec

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買", "建議賣", "目標價", "零風險", "無風險")


def _st(n, hit, base, tier, n10=0, hit10=None, base10=None):
    return {"n": n, "hit": hit, "base": base, "n10": n10, "hit10": hit10, "base10": base10, "tier": tier}


def _rows():
    a = {"id": "tw:heat:C1:hot", "mk": "tw", "cat": "heat", "grp": "chip", "var": "C1", "vn": "融資餘額水位", "sig": "hot",
         "name": "融資餘額水位・過熱中", "kind": "state", "H": 60, "th": 0.10, "a": "2001-01-02", "z": "2026-10-16",
         "up": _st(12, 0.70, 0.66, "none"), "warn": _st(12, 0.58, 0.29, "good"), "tier": "good", "dir": ["warn"],
         "occ": [["2020-01-02", "2020-03-01", 40, 0.5, 0.8]]}
    b = dict(a, id="tw:heat:C1:hot_in", sig="hot_in", name="融資餘額水位・進入過熱", kind="event",
             up=_st(13, 0.85, 0.66, "good"), warn=_st(13, 0.40, 0.29, "ref"), dir=["up"], occ=[["2020-01-02", 1, 0]])
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
    assert T["good"][0]["d"] == "warn" and abs(T["good"][0]["edge"] - 0.29) < 1e-9 and T["ref"] == []
    assert sigcat.today(V["rows"], {}, "tw") == {"good": [], "ref": []}


def test_render_structure_and_data():
    html = sigpage.render(_view())
    assert appnav.bar("sig") in html and "<title>訊號總覽</title>" in html
    for sid in ('id="today"', 'id="all"', 'id="mth"', 'id="sgq"', 'id="sgcsv"', 'id="sgnow"'):
        assert sid in html
    assert "融資餘額水位・過熱中" in html and "之後 3 個月內跌 10% 以上 <b>58%</b>（平常 29%）" in html
    assert "12/1 起" in html and "inf" not in html.split('id="all"')[0] and "每月平均 +6.8%・30 筆" in html
    data = json.loads(re.search(r'<script type="application/json" id="sgd">(.*?)</script>', html, re.S).group(1))
    assert len(data["rows"]) == 4 and all(len(r) == 16 for r in data["rows"])
    assert data["rows"][3][15]["pay"]["ratio"] is None                    # inf 不能進 JSON
    assert data["on"]["tw:heat:C1:hot_in"] == {"since": "2026-10-01", "n": 11, "left": 49}
    assert "const I = {id:0,mk:1,cat:2,grp:3,name:4,kind:5,H:6,th:7,tier:8,dir:9,up:10,warn:11,buy:12,a:13,z:14,x:15};" in sigpage.JS
    det = json.loads(sigpage.detail_json(_view()))
    assert det["occ"]["tw:heat:C1:hot"] == [["2020-01-02", "2020-03-01", 40, 0.5, 0.8]]


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
    g = (ROOT / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")
    assert g.index("heatpage.build()") < g.index("heatpage_us.build()") < g.index("bubpage.build()") < g.index("sigpage.build()")


def test_research_file_matches_spec_version():
    R = sigcat.load_research()
    assert R is not None and R["ver"] == sigspec.VER
    ids = [r["id"] for r in R["rows"]]
    assert len(ids) == len(set(ids)) and len(ids) > 1500
    for r in R["rows"]:
        assert r["tier"] in sigspec.TIERS
        for d in r["dir"]:
            assert d in sigspec.DIRS and r[d]["tier"] == r["tier"]
