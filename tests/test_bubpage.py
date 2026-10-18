"""泡沫頁（arm/lab/bubpage.py；docs/lab_risk_plan.md 第 7、8 節）：版面結構、用字、資料嵌入、JS 語法。假資料，不碰網路。"""
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import appnav
from arm.lab import bubpage as BP
from arm.lab import bubspec as BS

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


def _market(name, idx, L, cond, val=False):
    now = {"d": "2026-10-16", "L": L, "P1": "P1" in cond, "P2": "P2" in cond, "P3": "P3" in cond,
           "V": ("V" in cond) if val else None, "F": "F" in cond,
           "p1": {"ym": "2026-09", "s": 2.69, "q95": 1.23, "x": 100.0, "g": 0.012, "run": 9},
           "p2": {"ru": 115.6, "dist": -1.2}, "p3": {"ym": "2026-09", "z": 1.5},
           "f": {"ym": "2026-09", "pct": 12.0, "raw": 0.37}}
    if val:
        now["v"] = {"X6": {"ym": "2026-09", "pct": 99.0, "raw": 38.6}, "X8": {"ym": "2026-09", "pct": 98.0, "raw": 72.0}}
    months = [f"{1990 + j // 12}-{j % 12 + 1:02d}" for j in range(240)]
    hist = {"d": months, "L": [(3 if 100 <= j < 120 else 0) for j in range(240)], "c": [("12" if 100 <= j < 120 else "") for j in range(240)],
            "p": [100.0 + j for j in range(240)]}
    epi = [{"a": "1998-05", "z": "1999-12", "n": 20, "max": 3, "cond": ["P1", "P2"], "peak": {"d": "1999-11-30", "px": 219.0},
            "low": {"d": "2001-09-28", "px": 120.0}, "dd": -45.2, "open": False}]
    return {"name": name, "index": idx, "now": now, "hist": hist, "epi": epi, "ref": {"pe": {"d": "2026-09", "v": 26.7}}}


def _research():
    cell = {"n": 200, "n_hot": 30, "p_hot": 0.6, "p_all": 0.2, "verdict": "crash", "n_epi": 5, "ret_hot": -8.0, "ret_all": 9.0}
    main = {"a": "1992-01", "z": "2026-09", "n": 417, "dist": {str(k): 20.0 for k in BS.LEVELS}}
    for t in BS.TESTS:
        main[t] = {"252": dict(cell), "504": dict(cell, verdict="none"), "share": 7.0}
    main["L4"] = {"n_hot": 0}
    ext = {"a": "1987-01", "z": "2026-08", "n": 476, "epi": [{"a": "1987-04", "z": "1990-04", "n": 37, "max": 3, "cond": ["P1", "P2"],
           "peak": {"d": "1990-02", "px": 11000.0}, "low": {"d": "1990-10", "px": 3000.0}, "dd": -72.7, "open": False}],
           "hist": {"d": ["1987-01", "1987-02"], "L": [0, 3], "c": ["", "12"], "p": [1113.6, 1216.0]}}
    for t in ("P1", "P2", "P3", "L2", "L3"):
        ext[t] = {"252": dict(cell), "504": dict(cell), "share": 8.0}
    return {"ver": BS.VER, "tw": {"main": main, "ext": ext}, "spx": {"main": main, "robust": main}}


@pytest.fixture(scope="module")
def page():
    V = {"asof": "2026-10-16", "M": {"tw": _market("台股", "加權指數", 3, ["P1", "P2"]),
                                     "spx": _market("S&P 500", "S&P 500", 3, ["P3", "V"], val=True)}, "R": _research()}
    return V, BP.render(V)


def test_structure_tiles_cards_types_method(page):
    V, html = page
    assert appnav.bar("bub") in html and '<a class="back" href="./">返回主頁</a>' in html
    assert html.count('class="bt bt') == 2 and 'href="#tw"' in html and 'href="#spx"' in html
    for mk in ("tw", "spx"):
        assert f'<section class="sec cd bm" id="{mk}">' in html and f'id="h-{mk}"' in html and f'id="t-{mk}"' in html
    assert 'id="types"' in html and 'id="mth"' in html and 'id="lv"' in html
    assert html.count('<div class="bty">') == len(BP.TYPES) == 5
    assert "台股現在是等級 3「泡沫警戒」：價格爆發、兩年翻倍同時成立" in html
    assert "估值不判定（台股本益比只有 2013 年起，歷史太短）" in html
    assert "不判定：台股本益比只有 2013 年起，歷史太短（現在本益比 26.7 倍）" in html
    assert "兩年已經漲 116%，但收盤離最高點 1.2%" not in html                  # 離最高 5% 以內：兩年翻倍成立，不用解釋
    assert '<details class="bvd"><summary><b>驗證：成立之後比較容易大跌嗎？</b>' in html          # 驗證收起來，摘要一句
    assert "等級 ≥ 3 之後一年內跌 20%：60%，全部月份 20%（30 個月、5 段，成立後較容易大跌）" in html
    assert "CAPE 38.6，第 99 百分位" in html                                     # S&P 500 估值讀數
    assert "1987/4～1990/4（37 個月）・月平均" in html                           # 台股延伸樣本的 1990 泡沫段
    assert "成立後較容易大跌" in html and "60% ／ 20%" in html                   # 驗證表：成立 ／ 全部
    assert "1950 年起另算一次" in html                                          # S&P 500 穩健度
    assert '<span class="na">不判定</span>' in html                              # 台股估值不判定
    assert "S&amp;P 500 現在是等級 3" in html                                    # 英數結尾的名字後面補空格
    assert html.count("1990 年以前：國發會月平均") == 1                            # 延伸樣本圖例只在台股卡
    m = _market("S&P 500", "S&P 500", 2, ["P3"], val=True)
    m["now"]["V"], m["now"]["v"]["X8"]["pct"] = False, 92.0
    assert "估值只有 CAPE 在歷史前 5%（要 2 項才算）" in BP.summary("spx", m)
    assert "（已依長期漲勢調整）" in html and "2026/9 為止連續 9 個月超過" in html


def test_psy_and_valuation_wording():
    n = {"p1": {"ym": "2026-09", "s": 1.15, "q95": 1.34, "x": 0.0, "g": 0.053, "run": 0}}
    txt = BP._p1_text(n)
    assert "2026/9 沒有超過" in txt and "連續 0 個月" not in txt and 'title="長期漲勢（每月變化的平均 ÷ 標準差）0.053"' in txt
    v = BP._v_text("spx", {"v": {"X6": {"pct": 98.9, "raw": 41.8}, "X8": {"pct": 92.6, "raw": 72.0},
                                 "X9": {"pct": 93.3, "raw": -5.0}}}, {})
    assert v == ("CAPE 41.8，第 99 百分位；巴菲特指標比長期趨勢高 72%，第 93 百分位；"
                 "Tobin&#x27;s Q 比長期趨勢低 5%，第 93 百分位（和有資料以來比）")


def test_embedded_data_and_script(page):
    V, html = page
    m = re.search(r'<script type="application/json" id="bubd">(.*?)</script>', html, re.S)
    D = json.loads(m.group(1))
    assert set(D) == {"tw", "spx"} and len(D["tw"]["d"]) == len(D["tw"]["L"]) == len(D["tw"]["p"]) == 240
    assert D["tw"]["xd"] == ["1987-01", "1987-02"] and D["tw"]["xL"] == [0, 3] and "xd" not in D["spx"]
    assert D["tw"]["xc"] == ["", "12"] and D["tw"]["xp"] == [1113.6, 1216.0]
    assert "</" not in m.group(1)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_script_parses(page):
    _, html = page
    js = re.findall(r"<script>(.*?)</script>", html, re.S)[-1]
    r = subprocess.run(["node", "--check", "-"], input=js, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]


def test_no_banned_words(page):
    _, html = page
    text = html + BP.CSS + BP.JS + "".join(t for _, _, t in BP.TYPES) + BP.METHOD
    assert not [w for w in BANNED if w in text]


def test_empty_view_renders_a_warning():
    html = BP.render({"asof": None, "M": {}, "R": {}})
    assert "泡沫等級還算不出來" in html and appnav.bar("bub") in html


def test_build_is_wired_into_dashboard_and_workflows():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    gen = (root / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")
    assert "bubpage.build()" in gen and gen.index("heatpage_us.build()") < gen.index("bubpage.build()")   # 沿用景氣頁算好的等級
    for wf in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        t = (root / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9b.html 2>/dev/null || true") == 2, wf
