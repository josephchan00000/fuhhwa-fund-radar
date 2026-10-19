"""泡沫頁（arm/lab/bubpage.py；docs/lab_risk_plan.md 第 7～11 節）：版面結構、用字、資料嵌入、JS 語法。假資料，不碰網路。"""
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


def _e(k, run, dec=True, cyc=None):
    e = {"ym": "2026-09", "s": 1.5 if run else -0.7, "q95": 0.8, "g": 0.03, "run": run, "r": 26.7,
         "dec": {"a": "2024-09", "p": 119.2, "f": 82.6, "r": 20.0, "fa": "2024-09", "fz": "2026-09"} if dec else None,
         "cyc": cyc, "on": run >= BS.E_RUN}
    return e


def _g(G1=True, rev=0.061, G2=False, src="est"):
    est = {"d": "2026-10-18", "n": 494, "cov": 0.9945, "g0": 0.3262, "g1": 0.1531, "rev": rev, "px3": 2.7, "G1": G1, "G2": G2,
           "G": bool(G1 and G2), "top": [["NVDA", 0.0215, 0.247], ["MU", 0.0139, 0.267], ["MPC", 0.0024, 1.213]]}
    proxy = {"src": "spf", "per": "2026-Q3", "G1": True, "G2": False, "G": False, "g0": 0.1127, "g1": 0.0599, "rev": 0.0067}
    g = {"est": est, "proxy": proxy, "src": src} if src == "est" else {"proxy": proxy, "src": "proxy"}
    g["G"] = g[g["src"]]["G"]
    return g


def _market(name, idx, L, cond, val=False, e=None, g=None):
    now = {"d": "2026-10-16", "L": L, "P1": "P1" in cond, "P2": "P2" in cond, "P3": "P3" in cond,
           "E": "E" in cond, "e": e if e is not None else {"pe_tw": _e("pe_tw", 4 if "E" in cond else 0)},
           "V": ("V" in cond) if val else None, "F": "F" in cond,
           "p1": {"ym": "2026-09", "s": 2.69, "q95": 1.23, "x": 100.0, "g": 0.012, "run": 9},
           "p2": {"ru": 115.6, "dist": -1.2}, "p3": {"ym": "2026-09", "z": 1.5},
           "f": {"ym": "2026-09", "pct": 12.0, "raw": 0.37}}
    now["g"] = g if g is not None else _g()
    now["G"] = now["g"]["G"]
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
    for t in BS.TESTS4_SPX:
        main[t] = {"252": dict(cell), "504": dict(cell, verdict="none"), "share": 7.0}
    main["L4"] = {"n_hot": 0}
    ext = {"a": "1987-01", "z": "2026-08", "n": 476, "epi": [{"a": "1987-04", "z": "1990-04", "n": 37, "max": 3, "cond": ["P1", "P2"],
           "peak": {"d": "1990-02", "px": 11000.0}, "low": {"d": "1990-10", "px": 3000.0}, "dd": -72.7, "open": False}],
           "hist": {"d": ["1987-01", "1987-02"], "L": [0, 3], "c": ["", "12"], "p": [1113.6, 1216.0]}}
    for t in BP.EXT_TESTS:
        ext[t] = {"252": dict(cell), "504": dict(cell), "share": 8.0}
    return {"ver": BS.VER, "tw": {"main": main, "ext": ext}, "spx": {"main": main, "robust": main}}


@pytest.fixture(scope="module")
def page():
    V = {"asof": "2026-10-16", "M": {"tw": _market("台股", "加權指數", 3, ["P1", "P2", "E"]),
                                     "spx": _market("S&P 500", "S&P 500", 3, ["P3", "V"], val=True,
                                                    e={"pe": _e("pe", 0, cyc={"per": "2026-03", "z": 2.4})})},
         "R": _research()}
    return V, BP.render(V)


def test_structure_tiles_cards_types_method(page):
    V, html = page
    assert appnav.bar("bub") in html and '<a class="back" href="./">返回主頁</a>' in html
    assert html.count('class="bt bt') == 2 and 'href="#tw"' in html and 'href="#spx"' in html
    for mk in ("tw", "spx"):
        assert f'<section class="sec cd bm" id="{mk}">' in html and f'id="h-{mk}"' in html and f'id="t-{mk}"' in html
    assert 'id="types"' in html and 'id="mth"' in html and 'id="lv"' in html
    assert html.count('<div class="bty">') == len(BP.TYPES) == 7
    assert "台股現在是等級 3「泡沫警戒」：價格爆發、兩年翻倍成立，而且價格漲得比基本面快（本益比爆發）" in html
    assert "S&amp;P 500 現在是等級 3「泡沫警戒」：偏離趨勢成立，而且估值在歷史前 5%" in html
    assert "S&amp;P 500 盈餘比長期趨勢高 2.4 個標準差，基本面本身可能在景氣高峰" in html          # 景氣高峰提醒進一句話
    assert '<p class="note cyc">景氣高峰參考（不進等級）：S&amp;P 500 盈餘比長期趨勢高 2.4 個標準差（2026/3）' in html
    assert "本益比 26.7 倍：BSADF 1.50，95% 臨界值 0.80" in html and "2026/9 為止連續 4 個月超過" in html
    assert "兩年（2024/9→2026/9）：有盈餘公司的市值 +119%、近四季淨利 +83% → 比值 +20%" in html
    assert "現在的七個條件" in html and "七種條件代表什麼" in html
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
    assert ("價格過熱時，漲得比基本面快 60%（30 個月）、基本面有跟上 60%（30 個月）；"
            "未來獲利跟不上 60%（30 個月）、還跟得上 60%（30 個月）") in html              # PF／PN、PG／PnG 摘要
    assert html.count("1990 年以前：國發會月平均") == 1                            # 延伸樣本圖例只在台股卡
    m = _market("S&P 500", "S&P 500", 2, ["P3"], val=True, e={"pe": _e("pe", 0)})
    m["now"]["V"], m["now"]["v"]["X8"]["pct"] = False, 92.0
    s = BP.summary("spx", m)
    assert "估值只有 CAPE 在歷史前 5%（要 2 項才算）" in s
    assert "偏離趨勢成立，但價格沒有漲得比基本面快（兩年股價 +119%、近 12 個月盈餘 +83%）" in s      # 基本面有跟上：最多到 2
    m0 = _market("那斯達克", "那斯達克綜合指數", 0, [], e={"cp": _e("cp", 0)})
    assert BP.summary("ixic", m0).startswith("那斯達克現在是等級 0「沒有泡沫跡象」。")
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


def test_future_earnings_row_and_sentence(page):
    """VER 4：未來獲利一列（分析師預估＋替代資料並列）、一句話說哪一半成立、驗證表多 G 幾列。"""
    V, html = page
    assert "分析師預估（S&amp;P 500 成分股 494 家、涵蓋 99% 市值，10/18）：今年 +32.6%、明年 +15.3% → 成長減速" in html
    assert "明年預估近 3 個月上修 6.1%，股價近 3 個月 +2.7% → 沒有「下修而股價漲」" in html
    assert "→ 成長減速：成立；預估下修而股價漲：沒有" in html
    assert "修正影響最大：NVDA +25%、MU +27%、MPC +121%" in html
    assert "過去驗證用：專業預測者調查（美國企業稅後獲利預測中位數）（2026 年第 3 季調查）：今年 +11.3%、明年 +6.0%" in html
    assert "未來獲利跟不上（兩個都成立）" in html and "價格過熱，未來獲利還跟得上" in html and "對照：VER 3（沒有未來獲利）等級 ≥ 3" in html
    assert "對照：用實際獲利算的未來獲利跟不上" in html                          # S&P 500 才有的 Gr
    m = _market("S&P 500", "S&P 500", 2, ["P3"], e={"pe": _e("pe", 0)})
    assert "未來獲利也還跟得上（明年預估成長 +15%，比今年 +33% 低，但明年預估近 3 個月上修 6.1%）" in BP.summary("spx", m)
    m = _market("S&P 500", "S&P 500", 3, ["P3"], e={"pe": _e("pe", 0)}, g=_g(rev=-0.02, G2=True))
    assert "偏離趨勢成立，而且未來獲利跟不上（明年預估成長 +15%，比今年 +33% 低，明年預估近 3 個月下修 2.0%、股價還在漲）" in BP.summary("spx", m)
    m = _market("那斯達克", "那斯達克綜合指數", 2, ["P1"], e={"tech": _e("tech", 0)}, g=_g(src="proxy"))
    assert "明年專業預測者預估成長 +6%，比今年 +11% 低，但明年預估近 3 個月上修 0.7%" in BP.summary("ixic", m)
    t = BP._g_text("ixic", m["now"])
    assert t.startswith('<span class="rat">替代資料（等級用，分析師預估還沒有）') and "分析師預估（" not in t


def test_market_card_has_overview_judgement_line(monkeypatch):
    """市場卡多一行（docs/lab_signal_plan.md 第 6.2 節）：現在的等級過去之後 12 個月跌 20% 的比例／平常與判定，連到訊號總覽。"""
    from arm.lab import sigcat
    rows = [{"id": "spx:bub:L2", "warn": {"n": 13, "hit": 0.1851, "base": 0.1155, "tier": "ref"}},
            {"id": "spx:bub:L3", "warn": {"n": 12, "hit": 0.1886, "base": 0.1155, "tier": "ref"}},
            {"id": "tw:bub:L2", "warn": {"n": 0, "hit": None, "base": 0.338, "tier": "few"}}]
    monkeypatch.setattr(sigcat, "research_rows", lambda: rows)
    a = BP.sig_line("spx", {"L": 2})
    assert "泡沫等級 2 以上的時候：過去 13 段，之後 12 個月內跌 20% 以上 <b>19%</b>（平常 12%）" in a
    assert "● 可參考" in a and 'href="x9o.html#s=spx:bub:L2"' in a
    assert "泡沫等級 3 以上的時候" in BP.sig_line("spx", {"L": 4})
    assert "（現在等級 0）" in BP.sig_line("spx", {"L": 0})
    assert "過去沒有出現過" in BP.sig_line("tw", {"L": 2}) and "— 次數不夠" in BP.sig_line("tw", {"L": 2})
    assert BP.sig_line("ndx", {"L": 2}) == ""
    monkeypatch.setattr(sigcat, "research_rows", lambda: (_ for _ in ()).throw(OSError("x")))
    assert BP.sig_line("spx", {"L": 2}) == ""
