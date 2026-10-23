"""產業泡沫（arm/lab/bubind.py、bubindfetch.py、bubindpage.py；docs/lab_risk_plan.md 第 12 節）。

解析、累乘、回落、驗證的重抽、最後一個月的快速算法（要和完整算法一樣）、現在的兩年漲幅、頁面結構與用字。假資料為主，不碰網路。"""
import json
import math
import random
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from arm.lab import bubble as BU
from arm.lab import bubind as BD
from arm.lab import bubindfetch as BF
from arm.lab import bubindpage as IP
from arm.lab import bubindspec as BI
from arm.lab import bubpage as BP

ROOT = Path(__file__).resolve().parents[1]
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


# ── 抓取：Ken French CSV 解析 ─────────────────────────────────────────────

def _ff_csv(cols=BI.FF49):
    head = "," + ",".join(cols)
    vw = [f"192607,{','.join(['1.5'] * len(cols))}", f"192608,{','.join(['-99.99'] + ['2.0'] * (len(cols) - 1))}"]
    yr = [f"1927,{','.join(['10.0'] * len(cols))}"]
    nf = [f"192607,{','.join(['3'] * len(cols))}", f"192608,{','.join(['4'] * len(cols))}"]
    return "\n".join(["This file was created ...", "", "  Average Value Weighted Returns -- Monthly", head, *vw, "",
                      "  Average Value Weighted Returns -- Annual", head, *yr, "",
                      "  Number of Firms in Portfolios", head, *nf, ""]) + "\n"


def test_parse_ff_csv_sections_missing_and_annual_rows():
    P = BF.parse_ff_csv(_ff_csv())
    vw = P["Average Value Weighted Returns -- Monthly"]
    assert vw["cols"] == list(BI.FF49) and vw["rows"]["1926-07"][0] == 1.5
    assert vw["rows"]["1926-08"][0] is None and vw["rows"]["1926-08"][1] == 2.0          # −99.99＝沒有資料
    assert set(P["Average Value Weighted Returns -- Annual"]["rows"]) == {"1927"}
    T = BF.ff_tables(_ff_csv(), ("vw", "n"))
    assert set(T["vw"]) == {"1926-07", "1926-08"} and T["n"]["1926-08"][0] == 4.0       # 只留月資料


def test_ff_tables_refuses_wrong_columns_or_missing_section():
    bad = list(BI.FF49)
    bad[0], bad[1] = bad[1], bad[0]
    with pytest.raises(ValueError):
        BF.ff_tables(_ff_csv(tuple(bad)), ("vw",))
    with pytest.raises(ValueError):
        BF.ff_tables(_ff_csv(), ("size",))


# ── 小工具 ───────────────────────────────────────────────────────────────

def test_chain_restarts_after_a_gap_and_drawdown():
    ms = BD.months_between("2020-01", "2020-06")
    out = BD.chain({"2020-01": 10.0, "2020-02": -50.0, "2020-04": 100.0, "2020-05": 0.0}, ms)
    assert out == pytest.approx({"2020-01": 1.1, "2020-02": 0.55, "2020-04": 2.0, "2020-05": 2.0})
    assert BD.drawdown([100, 120, 60, 90], 0, 3) == pytest.approx(0.5)
    assert BD.drawdown([100, None, 60], 0, 2) is None and BD.drawdown([100, 90], 0, 5) is None


def test_flags_for_composite_tests():
    r = {"P1": None, "P2": False, "P3": None, "F": True, "L": 3}
    assert BD._flag(r, "PX") is False and BD._flag(r, "P2F") is False and BD._flag(r, "L3") is True
    assert BD._flag({"P1": None, "P2": None, "P3": None, "F": None, "L": 0}, "PX") is None
    assert BD._flag({"P1": None, "P2": True, "P3": None, "F": None, "L": 2}, "P2F") is None   # 燃料沒資料＝不判定


# ── 驗證：以月份為單位重抽 ─────────────────────────────────────────────────

def _panel(hot_months, n_ind=4, n=240, crash=0.5):
    months = BD.months_between("2000-01", BD._ym_add("2000-01", n - 1))
    pan = {}
    for k in range(n_ind):
        ss = []
        for j, m in enumerate(months):
            hot = m in hot_months and k == 0
            r = {"d": m, "P1": hot, "P2": hot, "P3": hot, "E": None, "G": None, "F": False, "L": 2 if hot else 0}
            ss.append({"d": m, "r": r, "dd12": crash if hot else 0.0, "dd24": crash if hot else 0.0,
                       "ret12": -10.0 if hot else 5.0, "ret24": -10.0 if hot else 5.0})
        pan[f"i{k}"] = ss
    return pan


def test_panel_test_crash_verdict_and_deterministic():
    hot = set()
    for y in (2001, 2005, 2009, 2013, 2017):                              # 5 段、每段 4 個月、前後兩半都有
        hot |= {f"{y}-0{m}" for m in range(1, 5)}
    pan = _panel(hot)
    a, b = BD.panel_test(pan, "P2"), BD.panel_test(pan, "P2")
    assert a == b                                                          # 固定種子
    e = a["24"]
    assert e["n_hot"] == 20 and e["p_hot"] == 1.0 and e["n_epi"] == 5 and e["verdict"] == "crash"
    assert e["lo"] > 0 and e["ret_hot"] == -10.0
    few = BD.panel_test(_panel({"2001-01", "2001-02"}), "P2")["24"]
    assert few["n_hot"] == 2 and few["verdict"] == "few"


def test_panel_test_time_episodes_are_counted_across_industries():
    """同一段時間好幾個產業一起熱只算一段（n_epi），各產業各自的段另計（n_iepi）。"""
    months = BD.months_between("2000-01", "2019-12")
    pan = {}
    for k in range(3):
        ss = []
        for m in months:
            hot = m.startswith("2005-0") and int(m[-2:]) <= 6
            r = {"d": m, "P1": hot, "P2": hot, "P3": hot, "E": None, "G": None, "F": False, "L": 2 if hot else 0}
            ss.append({"d": m, "r": r, "dd12": 0.3 if hot else 0.0, "dd24": 0.5 if hot else 0.0, "ret12": 0.0, "ret24": 0.0})
        pan[f"i{k}"] = ss
    e = BD.panel_test(pan, "P1")["24"]
    assert e["n_hot"] == 18 and e["n_epi"] == 1 and e["n_iepi"] == 3 and e["verdict"] == "few"


# ── 條件：最後一個月的快速算法＝完整算法的最後一列 ──────────────────────────────

def _walk(n, seed, drift=0.006, boom=0):
    rnd = random.Random(seed)
    v, out = 100.0, []
    for j in range(n):
        g = drift + (0.05 if j >= n - boom else 0.0)
        v *= math.exp(g + rnd.gauss(0, 0.04))
        out.append(v)
    return out


@pytest.fixture(scope="module")
def cv():
    T = BU.load_cv_table()
    if not T:
        pytest.skip("沒有 PSY 漂移臨界值表")
    return T


@pytest.mark.parametrize("boom", [0, 14])
def test_ff_last_row_equals_full_conditions(cv, boom):
    n = 420
    months = BD.months_between("1980-01", BD._ym_add("1980-01", n - 1))
    me = dict(zip(months, _walk(n, 7, boom=boom)))
    mkt = dict(zip(months, _walk(n, 8)))
    cpi = {m: 100.0 * (1.002 ** j) for j, m in enumerate(months)}
    f = dict(zip(months, (random.Random(9).random() for _ in months)))
    S = {"me": me, "pm": me, "mkt": mkt, "cpi": cpi, "f": f, "fmin": BI.F_MIN_MONTHS["ff"]}
    full = BD.conditions(S, cv)["rows"][-1]
    fast = BD.ff_last_row(S, cv)
    for k in ("d", "P1", "P2", "P3", "F", "L"):
        assert fast[k] == full[k], k
    if boom:
        assert fast["P2"] and fast["L"] >= 2                               # 最後 14 個月暴漲：兩年翻倍而且在高點


def test_now_p2_uses_same_calendar_day_two_years_ago():
    cal = ["2024-10-15", "2024-10-16", "2025-06-30", "2026-10-15", "2026-10-16"]
    px = [100.0, 100.0, 180.0, 260.0, 255.0]
    mpx = [100.0, 100.0, 110.0, 130.0, 130.0]
    me = {"2024-10": 100.0, "2025-06": 180.0, "2026-09": 262.0}
    r = BD.now_p2(cal, px, cal, mpx, me)
    assert r["ru"] == pytest.approx(155.0) and r["net"] == pytest.approx(125.0)
    assert r["dist"] == pytest.approx(100 * (255 / 262 - 1)) and r["P2"] is True        # 離高點 2.7%：還在 5% 內
    r = BD.now_p2(cal, [100.0, 100.0, 180.0, 300.0, 250.0], cal, mpx, {"2024-10": 100.0, "2026-09": 300.0})
    assert r["P2"] is False and r["dist"] == pytest.approx(100 * (250 / 300 - 1))       # 離高點 16.7%


# ── 頁面 ─────────────────────────────────────────────────────────────────

def _now(L, cond, ru=120.0, net=60.0, dist=-1.0, g=None, gsrc=None, f=None, mem=None, run=0):
    n = {"d": "2026-10-16", "L": L, "p2": {"ru": ru, "net": net, "dist": dist},
         "p1": {"ym": "2026-09", "run": run} if run else None, "g": g, "gsrc": gsrc, "f": f}
    for c in ("P1", "P2", "P3", "E", "G", "F"):
        n[c] = c in cond
    if mem is not None:
        n["mem"] = mem
    return n


def _hist(n=30):
    ms = BD.months_between("2024-01", BD._ym_add("2024-01", n - 1))
    return {"d": ms, "L": [0] * (n - 3) + [2, 3, 3], "c": [""] * (n - 3) + ["1", "1e", "1ef"], "p": [1.0 + j / 10 for j in range(n)]}


def _I():
    est = {"n": 41, "cov": 0.9, "g0": 1.046, "g1": 0.691, "rev": 0.165, "px3": 13.0}
    tw = {"電子零組件業": {"now": _now(3, ["P1", "E"], ru=310.0, net=198.0, dist=-7.3, g=est, gsrc="est", f=69.0, mem=131, run=9),
                         "hist": _hist()},
          "塑膠工業": {"now": _now(2, ["P2", "F"], ru=258.0, net=146.0, dist=0.0,
                                  g={"per": "2026-09", "y12": 0.05, "y12b": -0.12}, gsrc="proxy", f=95.0, mem=16), "hist": _hist()},
          "金融保險": {"now": dict(_now(0, [], ru=-0.4, net=-37.0, dist=-0.4), E=None, G=None), "hist": _hist()}}
    us = {"XLP": {"now": _now(0, ["G"], ru=6.0, net=-25.0, dist=-2.7,
                              g={"n": 33, "cov": 0.99, "g0": 0.08, "g1": 0.07, "rev": -0.003, "px3": 2.9}, gsrc="est"),
                  "hist": _hist()}}
    ff = {"Hardw": {"now": _now(2, ["P1", "P2", "P3"], ru=140.0, net=103.0, dist=-1.4, f=12.0)},
          "Coal": {"now": _now(0, [], ru=32.0, net=-5.0, dist=-88.2, f=18.0)}}
    return {"ver": BI.VER, "tw": tw, "us": us, "ff": ff, "ff_last": "2026-08"}


def _R():
    cell = {"n": 9000, "n_hot": 671, "p_hot": 0.526, "p_all": 0.279, "verdict": "crash", "n_epi": 30, "ret_hot": 3.0, "ret_all": 11.0}
    c24 = dict(cell, n_hot=663, p_hot=0.377, p_all=0.127)
    ff = {"a": "1931-08", "z": "2026-08", "n_ind": 48, "tests": {t: {"12": dict(cell), "24": dict(c24)} for t in BI.TESTS["ff"]}}
    tw = {"a": "2018-03", "z": "2026-10", "n_ind": 31, "tests": {t: {"12": dict(cell, verdict="few"), "24": dict(c24, verdict="few")}
                                                                    for t in BI.TESTS["tw"]}}
    return {"ver": BI.VER, "ff": ff, "tw": tw}


@pytest.fixture(scope="module")
def sec():
    I = _I()
    data, keys = IP.hist_data(I)
    return I, data, keys, IP.section(I, _R(), keys)


def test_section_structure_and_order(sec):
    I, data, keys, html = sec
    assert html.startswith('<section class="sec cd" id="ind">') and html.endswith("</section>")
    assert "台股 3 個產業・美股 1 個類股・美股 2 個細產業" in html
    assert "台股 3 個產業：1 個在等級 3（電子零組件業）、1 個在等級 2（塑膠工業）" in html
    assert "美股 2 個細產業（月資料到 2026/8）：1 個在等級 2（電腦硬體）" in html
    tw = html[html.index("<h3>台股產業</h3>"):html.index("<h3>美股類股</h3>")]
    order = re.findall(r'<td class="l bnm" data-v="([^"]+)"', tw)
    assert order == ["電子零組件業", "塑膠工業", "金融保險"]                         # 等級高的在前
    for grp, ks in keys.items():
        for k, key in ks.items():
            assert f'data-k="{key}"' in html and f'id="h-{key}"' in html and f'id="t-{key}"' in html and key in data
    assert '<details class="bvd"><summary><b>美股 49 細產業（Ken French，月資料到 2026/8）</b>' in html   # 細產業收起來
    assert 'data-k="' not in html[html.index("美股 49 細產業（Ken French"):]                    # 細產業沒有展開列


def test_row_wording(sec):
    _, _, _, html = sec
    assert "電子零組件業：等級 3「泡沫警戒」（價格爆發、漲得比營收快）。兩年 +310%，比大盤多 198 個百分點，離最高點 7.3%" in html
    assert "兩年已經翻倍，但離最高點超過 5%，不算「兩年翻倍」" in html and "價格爆發讀數連 9 個月超過臨界值" in html
    assert "分析師預估（41 家、涵蓋 90% 市值）：今年 +105%、明年 +69%，成長減速；明年預估近 3 個月上修 16.5%" in html
    assert "塑膠工業：等級 2「漲勢過熱」（兩年翻倍、換手率）。兩年 +258%，比大盤多 146 個百分點，在最高點" in html
    assert "營收（替代資料，2026/9）近 12 個月年增 +5%，半年前 -12%" in html
    assert "金融保險：等級 0「沒有泡沫跡象」。兩年 0%" in html and "營收含投資損益，營收比值與未來獲利不判定" in html
    assert "必需消費（XLP）：等級 0「沒有泡沫跡象」（未來獲利跟不上），價格沒有過熱，所以不升級" in html
    assert '比大盤 <span class="nw">+198 個百分點</span>' in html and "<td class=\"dsk\" data-v=\"0.0\">在最高點</td>" in html
    assert '<i class="nil">—</i>' in html and '<i class="on">價格爆發</i>' in html
    assert ">-88.2%<" in html and "第 12 百分位" in html


def test_validation_judged_only_for_ken_french(sec):
    _, _, _, html = sec
    v = html[html.index('id="indv"'):]
    assert "「兩年翻倍、比大盤多漲而且在高點」之後兩年內跌 40% 的比例 38%，所有產業月份 13%（663 個產業月份、30 段，成立後較容易大跌）" in v
    ff = v[v.index("美股 49 細產業（Ken French，1931/8～2026/8"):v.index("台股產業（2018/3")]
    tw = v[v.index("台股產業（2018/3"):]
    assert "成立後較容易大跌" in ff and "53% ／ 28%" in ff
    assert "成立後較容易大跌" not in tw and "樣本不足" not in tw and "樣本太短，只描述" in tw    # 台股只描述


def test_number_formatting():
    assert IP._pct(-0.4) == "0%" and IP._pct(0.04, 1) == "0.0%" and IP._pct(12.6) == "+13%" and IP._pct(None) == "—"
    assert IP._dist(-0.04) == "在最高點" and IP._dist(-7.34) == "-7.3%" and IP._dist(None) == "—"


def test_hist_data_renames_fuel_and_keys_are_stable(sec):
    I, data, keys, _ = sec
    assert keys == {"tw": {"塑膠工業": "@t0", "金融保險": "@t1", "電子零組件業": "@t2"}, "us": {"XLP": "@u0"}, "tg": {}}
    assert data["@t2"]["c"][-1] == "1eh" and "f" not in "".join(data["@t2"]["c"])          # 燃料改 h，不和市場層級的槓桿混


def test_page_embeds_industry_charts_and_nav():
    from tests.test_bubpage import _market, _research
    V = {"asof": "2026-10-16", "M": {"tw": _market("台股", "加權指數", 2, ["P1"])}, "R": _research(), "I": _I(), "IR": _R()}
    html = BP.research_body(V)                                                               # 研究紀錄頁（段落 id 加 bub-）
    assert '<a href="#bub-ind">產業</a>' in html and html.index('id="bub-tw"') < html.index('id="bub-ind"') < html.index('id="bub-types"')
    D = json.loads(BP.research_data(V))
    assert {"tw", "@t0", "@t1", "@t2", "@u0"} <= set(D)
    assert "Object.keys(D).filter(k => k[0] !== '@').forEach(draw)" in BP.JS                # 產業圖展開才畫
    assert '<div class="bhw"><div class="bh" id="h-tw">' in html                            # 提示框跟著圖定位
    assert "mk[0] === '@' ? '產業指數'" in BP.JS


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_section_script_parses():
    r = subprocess.run(["node", "--check", "-"], input=IP.JS, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]


def test_no_banned_words(sec):
    _, _, _, html = sec
    text = html + IP.CSS + IP.JS + IP.NOTE + "".join(IP.TEST_NAMES.values()) + "".join(IP.VERDICT.values())
    assert not [w for w in BANNED if w in text]


def test_section_without_data_shows_a_warning():
    assert "產業泡沫還算不出來（KeyError: x）" in IP.section({"tw_err": "KeyError: x"}, {}, {})
    assert "驗證結果還沒產生" in IP.valid_sec({})


# ── 接線：抓取、回補、研究檔 ───────────────────────────────────────────────

def test_wired_into_fetch_backfill_and_research():
    fh = (ROOT / "scripts" / "fetch_heat.py").read_text(encoding="utf-8")
    assert "BD.indtw_update" in fh and '"indtw"' in fh
    fu = (ROOT / "scripts" / "fetch_heat_us.py").read_text(encoding="utf-8")
    assert "BF.ff49" in fu and '"ind_ff"' in fu and '"ind_etf"' in fu and '"gics"' in fu
    rb = (ROOT / "scripts" / "run_bubind.py").read_text(encoding="utf-8")
    assert "BD.research()" in rb and "save_research" in rb
    R = BD.load_research()
    assert R is not None and R["ver"] == BI.VER and {"ff", "tw", "us"} <= set(R)
    assert set(R["ff"]["tests"]) == set(BI.TESTS["ff"]) and R["ff"]["tests"]["P2"]["24"]["n_hot"] > 0
