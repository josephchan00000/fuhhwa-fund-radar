"""景氣頁的視覺化版面（arm/lab/heatviz.py；docs/lab_visual_plan.md）：雷達的資料、比較日期、關鍵狀態、右側面板、
研究畫面原封搬移、深淺配色、瀏覽器程式。只改呈現，分數與研究不動。"""
import html
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from arm.lab import heatcalc as C
from arm.lab import heatpage as P
from arm.lab import heatspec as S
from arm.lab import heatviz as VZ

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatpage import BANNED, m6_stub, research_stub, synthetic_D  # noqa: E402


@pytest.fixture(scope="module")
def built():
    B = C.build(synthetic_D())
    R = research_stub(B)
    R["m6"] = m6_stub()
    V = P.view(B, R)
    return B, R, V, P.render(V)


def test_episodes_need_a_new_high_to_close():
    d = [f"2020-01-{i + 1:02d}" for i in range(12)]
    px = [100, 110, 90, 80, 95, 112, 120, 100, 96, 130, 125, 100]
    e = VZ.episodes(d, px)
    assert [(x["peak"], x["trough"], x["open"]) for x in e] == [("2020-01-02", "2020-01-04", False),
                                                                ("2020-01-10", "2020-01-12", True)]
    assert abs(e[0]["dd"] - (80 / 110 - 1)) < 1e-12 and abs(e[1]["dd"] - (100 / 130 - 1)) < 1e-12
    assert VZ.episodes(d, [100, 95, 90, 85, 100, 101]) == []                  # 沒跌到 20% 不算一段
    assert VZ.episodes(["a", "b"], [None, 100]) == []


def test_pack_radar_data(built):
    B, _, V, _ = built
    viz = V["viz"]
    cal = B["cal"]
    we = P.HP.week_ends(cal)
    wd = [cal[i] for i in we]
    assert [d["id"] for d in viz["dims"]] == list(P.shown_dims())          # 泡沫另放泡沫頁
    for d in viz["dims"]:
        L = V["dims"][d["id"]]
        assert d["sc"] == VZ._r1(L["score"]) and d["ago"] == VZ._r1(L["ago"])
    shown = list(P.shown_dims())                                               # 泡沫另放泡沫頁
    need = -(-2 * len(shown) // 3)
    j0 = wd.index(viz["start"])
    assert sum(B["comp"][d][we[j0]] is not None for d in shown) >= need        # 時間軸從 2/3 的面向有分數那週開始
    assert j0 == 0 or sum(B["comp"][d][we[j0 - 1]] is not None for d in shown) < need
    want = VZ.swings(cal, B["px"], VZ.SWING_TW, start=viz["start"])         # 雷達底下＝近期波段高低點（那一天的面向分數）
    assert [(p["d"], p["k"]) for p in viz["pre"]] == [(cal[x["i"]], x["k"]) for x in want]
    for p in viz["pre"]:
        i = cal.index(p["d"])
        assert p["v"] == [VZ._r1(B["comp"][d][i]) for d in shown] and p["px"] == VZ._r1(B["px"][i])
        assert p["lab"] == ("高點" if p["k"] in ("H", "h") else "低點")
    assert "qs" not in viz and viz["sthr"] == 10.0 and viz["npx"] == VZ._r1(B["px"][-1])
    t = len(cal) - 1
    for d in viz["dims"]:                                                     # 括號裡的變化＝和前一個交易日比（取整數後相減）
        c = B["comp"][d["id"]]
        want_d1 = None if c[t] is None or c[t - 1] is None else VZ._ri(c[t]) - VZ._ri(c[t - 1])
        assert d["d1"] == want_d1
    assert {it["k"] for it in viz["items"]} == {k for d in shown for k in S.ITEMS[d]}
    for d in shown:
        assert sorted(viz["ord"][d]) == sorted(S.ITEMS[d])
    assert "bubl" not in viz["ord"]
    assert viz["t0"] == cal[len(cal) - 1 - P.WEEK]


def test_terrain_layers_and_wording(built):
    """地形圖（2026-10-18 使用者：「地形圖好醜喔 看起來很不清楚」）：山脊一個顏色，只塗過熱與過冷；地面灰帶是大跌期間（全部列出）。"""
    B, _, V, page = built
    cal, px = B["cal"], B["px"]
    a0 = cal.index(V["viz"]["start"])
    want = VZ.episodes(cal[a0:], px[a0:])
    assert [(e["p"], e["t"], e["o"]) for e in V["viz"]["eps"]] == [(e["peak"], e["trough"], e["open"]) for e in want]
    assert all(e["dd"] == VZ._r1(100 * x["dd"]) for e, x in zip(V["viz"]["eps"], want))
    tv = page[page.index('<div class="hview" data-view="terrain"'):page.index('<div class="hview" data-view="research"')]
    assert "紅色山頂＝過熱（80 以上）" in tv and "藍色谷底＝過冷（20 以下）" in tv and "同一週有幾個面向過熱" in tv
    assert f"灰色地面＝{P.MK['px'].strip()}從高點跌 20% 以上的期間" in tv
    assert all(f"{nm}</span>" in tv for _, _, nm in S.BANDS)                   # 平面那一組圖例：五個區
    assert "紅色平面" not in tv and "addColorStop(pos" not in VZ.JS           # 舊版：半透明紅色平面、逐週依分區上色（條紋）


def test_terrain_identity_colors_and_focus(built):
    """地形圖辨認（2026-10-18 使用者選 A＋B）：每個面向一個顏色（深淺兩套），上方按鈕或右側名字點一下只看那一條。"""
    from arm.lab import heatspec_us as U
    _, _, V, page = built
    dims_tw = list(S.DIMS)
    with S.use(U.spec_for("spx")):
        dims_us = list(S.DIMS)
    assert set(dims_tw) | set(dims_us) <= set(VZ.DCOL)                         # 台股、美股每個面向都有顏色
    assert len({VZ.DCOL[d] for d in dims_tw}) == len(dims_tw)                  # 同一頁裡不重複
    css = P._CSS
    light = css[css.index(":root{"):css.index("@media (prefers-color-scheme:dark)")]
    dark = css[css.index("@media (prefers-color-scheme:dark)"):]
    for tok in set(VZ.DCOL.values()):
        assert f"--{tok}:" in light and f"--{tok}:" in dark, tok
    shown = list(P.shown_dims())                                               # 泡沫另放泡沫頁，地形只畫景氣頁的面向
    assert [d["col"] for d in V["viz"]["dims"]] == [VZ.DCOL[d] for d in shown]
    tv = page[page.index('<div class="hview" data-view="terrain"'):page.index('<div class="hview" data-view="research"')]
    chips = re.findall(r'<button type="button" class="rch(?: on)?" data-tf="(\w*)"', tv)
    assert chips == [""] + shown                                               # 「全部」＋每個面向一顆
    for d in shown:
        assert f'data-tf="{d}" aria-pressed="false"><i class="tfd" style="background:var(--{VZ.DCOL[d]})"></i>{S.DSHORT[d]}</button>' in tv
    assert "__ter" not in VZ.JS and "O.lab" not in VZ.JS                       # 沒選的示意（名字寫在起點、拉開不重疊）已拿掉
    assert "function tFocus(" in VZ.JS and "TS.focus && p.id !== TS.focus" in VZ.JS


def test_key_states_definition(built):
    """關鍵狀態＝研究判定較弱／較強，而且現在在過熱或過冷；面向在前。"""
    B, R, V, page = built
    ks = V["ks"]
    want = 0
    for d, L in V["dims"].items():
        if L["score"] is not None and S.band(L["score"]) in ("過熱", "過冷"):
            want += any(P._ev(L["cev"], h).get("verdict") in ("weak", "strong") for h in L["fwd"])
        for it in L["items"]:
            if it["heat"] is None or it["proxy"] or S.band(it["heat"]) not in ("過熱", "過冷"):
                continue
            want += any(P._ev(it["ev"], h).get("verdict") in ("weak", "strong") for h in L["fwd"])
    assert len(ks) == want > 0
    kinds = [a["kind"] for a in ks]
    assert kinds == sorted(kinds, key=lambda k: k != "dim")
    for a in ks:
        assert a["band"] in ("過熱", "過冷") and a["h"] == max(a["hs"])
        assert all(a["verdict"][h] in ("weak", "strong") for h in a["hs"])
    # 2026-10-19 起頁面不再列「關鍵狀態」（依學術判定），改列「今天的重點」（訊號總覽的實務判定，docs/lab_signal_plan.md 第 6.1 節）
    assert '<article class="kcard"' not in page and 'id="key"' not in page and 'id="today"' in page


def test_every_item_and_dimension_has_a_panel(built):
    _, _, V, page = built
    for d in P.shown_dims():
        assert page.count(f'<template id="dt-{d}"') == 1
        assert f'<section class="cd" id="c-{d}">' in page                    # 原本的面向卡片在面板裡
    for k in [k for d in P.shown_dims() for k in S.ITEMS[d]]:
        t = page[page.index(f'<template id="it-{k}"'):]
        t = t[:t.index("</template>")]
        assert f'<div class="dchart" data-k="{k}"></div>' in t and f'class="tb cmpk" data-k="{k}"' in t
    assert page.count('<template id="it-') == sum(len(S.ITEMS[d]) for d in P.shown_dims())   # 泡沫的項目不在景氣頁
    assert '<aside class="drw" id="drw" hidden' in page                      # 一個共用的右側面板


def test_views_and_research_moved_intact(built):
    _, _, V, page = built
    assert re.findall(r'<div class="hview" data-view="(\w+)"', page) == ["radar", "phase", "terrain", "research"]
    assert re.findall(r'<button type="button" data-view="(\w+)"', page) == [k for k, _ in VZ.VIEWS]
    res = page[page.index('<div class="hview" data-view="research"'):page.index('<div class="dtpl"')]
    for part in (P._dv_section(V), P._rel_overview(V), P._m6_valid(V), P._ta_study(V)):
        assert part and part in res                                           # 研究內容原封搬到研究畫面
    for d, L in V["dims"].items():
        assert P._valid(d, L) in res and f'id="v-{d}"' in res
    assert 'id="src"' in res and P._METHOD in res
    main = page[page.index('<div class="hview" data-view="radar"'):page.index('<div class="hview" data-view="phase"')]
    assert P._ta_main(V) in main and P._cmp_section() in main and 'id="today"' in main and 'id="imap"' in main
    assert "看事件研究" in P._ta_main(V) and 'class="evt"' not in P._ta_main(V)


def test_hviz_json_embedded_safely(built):
    _, _, V, page = built
    a = page.index('<script type="application/json" class="hviz">') + len('<script type="application/json" class="hviz">')
    raw = page[a:page.index("</script>", a)]
    assert "</" not in raw
    assert json.loads(raw.replace("<\\/", "</")) == json.loads(json.dumps(V["viz"]))
    assert page.count("<script>") == 3                                        # 雷達程式和對照圖程式在同一個 script；另一個＝<head> 的深淺色（appnav）


def test_theme_tokens_for_light_and_dark():
    css = P._CSS
    dark = css[css.index("@media (prefers-color-scheme:dark)"):]
    dark = dark[:dark.index("}}") + 2]
    light = css[css.index(":root{"):css.index("@media (prefers-color-scheme:dark)")]
    for tok in ("--bg", "--panel", "--card2", "--ink", "--ink2", "--mut", "--line", "--acc", "--c0", "--c4", "--t0", "--t4",
                "--p0", "--p4", "--zh", "--zc", "--ring", "--tipbg", "--dfund", "--dbubl", "--q0", "--q1", "--q2", "--q3"):
        assert tok + ":" in light and tok + ":" in dark, tok                  # 深淺兩套都有定義
    for s in (VZ.CSS, VZ.JS, P._JS):                                          # 新加的樣式與程式不寫死白底
        assert "background:#fff" not in s and 'stroke="#fff"' not in s
    assert "M.pal[" not in P._JS                                              # 線色走 CSS 變數（深淺各一套）


def test_wording_and_banned_words(built):
    _, _, V, page = built
    text = re.sub(r"<script>.*?</script>", "", page, flags=re.S)
    for w in BANNED:
        assert w not in page, w
    assert "只當參考" in text and "今天的重點" in text and "研究顯示有穩定關係" not in text
    assert P.render(V) == page


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_scripts_parse_and_rounding_matches_python(built, tmp_path):
    _, _, _, page = built
    for i, src in enumerate(re.findall(r"<script>(.*?)</script>", page, flags=re.S)):
        f = tmp_path / f"s{i}.js"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:500]
    fn = re.search(r"function n0\(v\) \{.*?\n", VZ.JS).group(0)
    xs = [0, 0.2, 12.3, 19.5, 19.96, 20, 39.7, 40.0, 59.9, 74.8, 79.6, 79.96, 80, 99.6, 100]
    prog = fn + "process.stdout.write(JSON.stringify(" + json.dumps(xs) + ".map(n0)));"
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [P.n0(x) for x in xs]                      # 頁面取整和 Python 一樣（不跨區）


def test_us_page_items_use_us_wording():
    from arm.lab import heatcalc_us as CU
    from arm.lab import heatpage_us as PU
    from arm.lab import heatspec_us as U
    from test_heatcalc_us import fake_D
    D = fake_D()
    SH = CU.shared(D)
    pages = {k: PU.index_page(k, CU.build(k, D, SH), {}) for k in U.INDEX_ORDER}
    page = PU.render(pages)
    assert page.count('<aside class="drw" id="drw"') == 1 and "{{VSW}}" not in page and "{{DRAWER}}" not in page
    assert page.count('<script type="application/json" class="hviz">') == len(U.INDEX_ORDER)   # 每個指數一份雷達資料
    assert "來源：證交所" not in page                                         # 台股項目的來源表不用在美股頁
    assert S.MARKET == "tw" and P.MK["mkt"] == "台股"


# ── 階段時間軸（2026-10-18 取代羅盤；docs/lab_visual_plan.md 第 11 節）

def _walk(n, seed, gaps=()):
    """可重現的隨機走勢（0～100），中間挖幾段空白。"""
    import random
    rnd, v, out = random.Random(seed), 50.0, []
    for i in range(n):
        v = min(100.0, max(0.0, v + rnd.gauss(0, 6)))
        out.append(None if any(a <= i < b for a, b in gaps) else round(v, 4))
    return out


def test_phase_track_cycles_in_order_and_holds_inside_the_band():
    import math
    x = [50 + 40 * math.sin(2 * math.pi * i / 104) for i in range(520)]   # 兩年一個循環的平滑波
    L, M, Q = VZ.phase_track(x)
    w, c = VZ.PH["ma"], VZ.PH["chg"]
    assert all(v is None for v in Q[:w - 1 + c]) and Q[w - 1 + c] is not None
    runs = [q for k, q in enumerate(Q) if q is not None and (k == 0 or Q[k - 1] != q)]
    nxt = {3: 0, 0: 1, 1: 2, 2: 3}                                           # 冷回溫 → 熱升溫 → 熱降溫 → 冷降溫 → …
    assert len(runs) >= 16 and all(nxt[a] == b for a, b in zip(runs, runs[1:]))
    for i, q in enumerate(Q):                                               # 階段和位置一致；跨線前沿用原本的
        if q is None:
            continue
        hot, up = q in (0, 1), q in (0, 3)
        if abs(L[i] - 50) >= VZ.PH["hl"]:
            assert hot == (L[i] >= 50)
        if abs(M[i]) >= VZ.PH["hm"]:
            assert up == (M[i] >= 0)
    flat = VZ.phase_track([60.0] * 40)[2]                                   # 完全不動＝熱、還在升溫（變化 0 算升溫），之後一直沿用
    assert set(q for q in flat if q is not None) == {0}
    _, _, Qg = VZ.phase_track(_walk(200, 3, gaps=((80, 83),)))
    assert all(q is None for q in Qg[80:83 + VZ.PH["ma"] - 1])               # 缺資料：8 週平均要湊滿才有，之後重新判斷


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_phase_track_js_matches_python():
    src = VZ.JS[VZ.JS.index("// @@PH"):VZ.JS.index("// @@ENDPH")]
    cases = [_walk(700, 1), _walk(700, 2, gaps=((100, 104), (300, 340))), _walk(60, 9), [None] * 30 + _walk(300, 4)]
    prog = ("const PHC=" + json.dumps(VZ.PH) + ";function val(t,i){if(!t)return null;const j=i-t.o;return j>=0&&j<t.v.length?t.v[j]:null;}"
            + src + "const C=" + json.dumps(cases) + ";process.stdout.write(JSON.stringify(C.map(x=>{const r=phTrack({o:0,v:x},x.length);"
            "return {L:r.L,M:r.M,Q:r.Q,S:x.map((_,i)=>r.Q[i]==null?null:phSince(r.Q,i))};})));")
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:800]
    for x, got in zip(cases, json.loads(r.stdout)):
        L, M, Q = VZ.phase_track(x)
        assert got["Q"] == Q
        assert all((a is None and b is None) or abs(a - b) < 1e-9 for a, b in zip(got["L"], L))
        assert all((a is None and b is None) or abs(a - b) < 1e-9 for a, b in zip(got["M"], M))
        for i, j in enumerate(got["S"]):                                    # 「已幾週」：往回找同一階段的起點
            if j is not None:
                assert Q[j] == Q[i] and all(Q[k] == Q[i] for k in range(j, i + 1)) and (j == 0 or Q[j - 1] != Q[i])


def test_phase_view_replaces_compass(built):
    _, _, V, page = built
    assert [k for k, _ in VZ.VIEWS] == ["radar", "phase", "terrain", "research"] and dict(VZ.VIEWS)["phase"] == "階段"
    ph = page[page.index('<div class="hview" data-view="phase"'):page.index('<div class="hview" data-view="terrain"')]
    for tag in ('id="phx"', 'id="phtip"', 'id="phlead"', 'data-phr="2"', 'data-phr="5"', 'data-phr="10"', 'data-phr="0"'):
        assert tag in ph, tag
    for q in VZ.PH_ORDER:
        assert f'class="pq{q}"' in ph and VZ.PHN[q] in ph and VZ.PHS[q] in ph
    assert V["viz"]["ph"] == {**VZ.PH, "n": list(VZ.PHN), "s": list(VZ.PHS)}
    for old in ("cDraw", "cShow", "chaikin", "quadPanel", "data-cd", "#cps", "cplay", "ctin", ".cbub", ".cit "):
        assert old not in VZ.JS and old not in VZ.CSS, old                   # 羅盤的程式與樣式都拿掉了
    assert "if (v === 'compass') v = 'phase';" in VZ.JS                      # 舊網址 #v=compass 轉到階段
    assert "升溫、降溫沒有驗證過" in ph                                       # 只描述位置


# ── 研究畫面＝證據地圖（2026-10-18 使用者選 B；docs/lab_visual_plan.md 第 11 節）

def test_evidence_map_rows_counts_and_old_content_folded(built):
    _, _, V, page = built
    res = page[page.index('<div class="hview" data-view="research"'):page.index('<div class="dtpl"')]
    emap = res[res.index('id="emap"'):res.index('<details class="card emore" id="more">')]
    for d, L in V["dims"].items():                                          # 每個面向一張卡：面向分數＋每一項各一列
        card = emap[emap.index(f'id="e-{d}"'):]
        card = card[:card.index('class="note enone"')]
        assert card.count('class="erow') == 1 + len(L["items"])
        assert f'data-open="dim:{d}"' in card and all(f'data-open="item:{it["k"]}"' in card for it in L["items"])
        assert all(f'<template id="it-{it["k"]}"' in page for it in L["items"]) and f'<template id="dt-{d}"' in page
    n = {"s": [0, 0], "l": [0, 0]}                                           # 篩選鈕上的數字＝列數／穩定的列數
    for L in V["dims"].values():
        hs = tuple(L["fwd"])
        for ev in [L.get("cev") or {}] + [it.get("ev") or {} for it in L["items"]]:
            for key, h in (("s", hs[0]), ("l", hs[1])):
                n[key][0] += 1
                n[key][1] += int((ev.get(str(h)) or {}).get("verdict") in ("weak", "strong"))
    assert f'data-cs="{n["s"][0]}" data-cl="{n["l"][0]}"' in emap and f'data-cs="{n["s"][1]}" data-cl="{n["l"][1]}"' in emap
    rows = re.findall(r'<button type="button" class="erow[^"]*" data-open="[^"]+" data-ss="(\d)" data-sl="(\d)"', emap)
    assert sum(int(a) for a, _ in rows) == n["s"][1] and sum(int(b) for _, b in rows) == n["l"][1]
    more = res[res.index('<details class="card emore" id="more">'):]
    for part in (P._dv_section(V), P._rel_overview(V), P._m6_valid(V), P._ta_study(V)):
        assert part in more                                                   # 原本的內容收在「完整數字與方法」，沒有刪
    assert 'data-anchor="e-' in page and 'data-anchor="v-' not in page        # 面板的連結改到證據地圖那張卡
    assert "function eApply(" in VZ.JS and "function jump(" in VZ.JS and "if (o.anchor) jump(o.anchor);" in VZ.JS


def test_evidence_summary_is_computed_from_verdicts(built):
    _, _, V, _ = built
    lines = VZ.evidence_summary(V)
    cnt = {"weak": 0, "strong": 0, "none": 0, "few": 0}
    for L in V["dims"].values():
        for it in L["items"]:
            for e in (it.get("ev") or {}).values():
                if e and e.get("verdict") in cnt:
                    cnt[e["verdict"]] += 1
    head = re.sub(r"<[^>]+>", "", lines[0])
    assert f"共 {sum(cnt.values())} 個檢驗" in head and f"{cnt['weak'] + cnt['strong']} 個有穩定關係" in head
    assert f"{cnt['weak']} 個熱了之後較弱、{cnt['strong']} 個較強" in head
    good = [d for d, L in V["dims"].items() if any(((L.get("cev") or {}).get(str(h)) or {}).get("verdict") in ("weak", "strong") for h in L["fwd"])]
    text = re.sub(r"<[^>]+>", "", "".join(lines))
    for d in V["dims"]:
        assert S.DSHORT[d] in text
    if len(good) < len(V["dims"]):
        assert "的面向分數本身看不出穩定關係" in text
    for w in BANNED:
        assert w not in text


def test_evidence_track_positions():
    assert VZ._epos(0) == 50 and VZ._epos(-0.8) == 0 and VZ._epos(0.8) == 100 and VZ._epos(-2) == 0 and VZ._epos(5) == 100
    t = VZ._etrack({"rho": -0.3, "lo": -0.5, "hi": -0.1, "verdict": "weak"}, "eh-l")
    assert 'class="etk eh-l ev-weak"' in t and "left:31.25%" in t and 'left:18.75%;width:25.00%' in t
    assert "<em>—</em>" in VZ._etrack(None, "eh-s") and "<em>—</em>" in VZ._etrack({"verdict": "few"}, "eh-s")
    assert VZ._rho(-0.234) == "−0.23" and VZ._rho(0.65) == "+0.65" and VZ._rho(None) == "—"
    # 標題列（字比較小）和資料列要同一套欄寬，座標軸的 0 才會對齊零線：欄寬不可用 em
    grids = re.findall(r"\.erow,\.ehead\{[^}]*grid-template-columns:([^;}]+)", VZ.CSS)
    assert len(grids) == 2 and not any("em" in g for g in grids), grids


def test_swings_pivots_tentative_and_change():
    """波段高低點（docs/lab_heatviz_v2_plan.md 第 1 節）：已確認的轉折點＋目前這一段的極值（還沒確認）；之後漲跌到下一個點。"""
    cal = [f"2026-01-{d:02d}" for d in range(1, 15)]
    px = [115, 118, 120, 105, 100, 108, 116, 130, 125, 118, 120, 124, 119, 121]
    sw = VZ.swings(cal, px, 0.10)
    assert [(x["k"], x["i"]) for x in sw] == [("H", 2), ("L", 4), ("h", 7)]      # 120 → 100 回落 16.7%、100 → 130 反彈；130 之後只回落 9%
    assert sw[0]["chg"] == pytest.approx(100 / 120 - 1) and sw[1]["chg"] == pytest.approx(130 / 100 - 1)
    assert sw[2]["chg"] == pytest.approx(121 / 130 - 1)                          # 還沒確認的點：到今天
    assert VZ.swing_sub(sw[0], 0.10) == "之後跌 17%" and VZ.swing_sub(sw[1], 0.10) == "之後漲 30%"
    assert VZ.swing_sub(sw[2], 0.10) == "還沒確認（已回落 7%，未滿 10%）"
    assert VZ.swing_sub({**sw[2], "k": "l", "chg": 0.02}, 0.066) == "還沒確認（已反彈 2%，未滿 6.6%）"
    up = px[:8]                                                                 # 今天就是最高點 → 不列「還沒確認」那一張
    assert [x["k"] for x in VZ.swings(cal[:8], up, 0.10)] == ["H", "L"]
    assert [x["k"] for x in VZ.swings(cal, px, 0.10, start="2026-01-04")] == ["L", "h"]   # start 之前的已確認點不列
    assert [x["k"] for x in VZ.swings(cal, px, 0.10, n=1)] == ["L", "h"]


def test_swing_threshold_by_market():
    from arm.lab import crashspec as CS
    assert VZ.swing_thr("tw") == 0.10 and VZ.swing_thr(None) == 0.10
    assert all(VZ.swing_thr(m) == CS.TH[m][2] for m in ("spx", "ixic", "ndx", "sox"))


def test_swing_read_wording():
    pts = [{"k": "H", "v": [80, 70]}, {"k": "L", "v": [30, 66]}, {"k": "H", "v": [90, 60]}, {"k": "L", "v": [20, 70]},
           {"k": "h", "v": [10, 10]}]                                           # 還沒確認的點不算
    r = VZ.swing_read(pts, ["技術", "籌碼"], [36, 92])
    assert r == "這 2 個高點和 2 個低點：高點時比低點熱：技術（高點平均 85、低點 25，現在 36）。只描述這幾個點，不是訊號。"
    flat = [{"k": "H", "v": [30, 70]}, {"k": "H", "v": [35, 60]}, {"k": "L", "v": [25, 66]}, {"k": "L", "v": [20, 70]}]
    assert "形狀差不多" in VZ.swing_read(flat, ["技術", "籌碼"], [36, 92])
    assert VZ.swing_read(pts[:3], ["技術", "籌碼"], [36, 92]) == ""                # 低點不到 2 個不寫


def test_radar_card_has_swings_not_quarters(built):
    _, _, V, page = built
    rc = page[page.index('<div class="rcard card">'):page.index('<div class="vside">')]
    assert 'id="rsm"' in rc and 'id="rsmc"' in rc and "近期波段高點、低點" in rc and 'id="rchips"' not in rc
    assert "分數後面括號＝和前一個交易日比" in rc
    assert "P.qs" not in VZ.JS and "#cchips" not in VZ.JS and "function dlt()" in VZ.JS
    assert "比昨日" in page or "和昨日一樣" in page                               # 面板的分數格


def test_today_card_beside_radar(built):
    """今天的重點（溫度計＋偏多、警示）放在雷達右邊的窄欄、這週變化上面（2026-10-20 使用者：「我比較喜歡之前的排版」→ 雷達放回最上面）。
    窄欄裡溫度計的讀數排在長條下面、偏多與警示上下排；說明收進「怎麼看」。"""
    _, _, V, page = built
    side = page[page.index('<div class="vside">'):page.index('<p class="hz">')]
    assert page.index('<div class="vgrid">') < page.index('<div class="vside">') < page.index('id="today"')
    # 這週變化 2026-10-20 起移到兩欄下面整條（使用者：「左邊空空的 沒對齊」）；兩欄等高
    assert 'id="today"' in side and side.index('id="today"') < side.index('</div></div><section class="wchg card" id="wchg">')
    assert ".vgrid{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(0,1fr);gap:14px;align-items:stretch}" in page
    assert ".vside>.card:last-child{flex:1}" in page
    assert '<details class="tzx"><summary>怎麼看</summary>' in side
    css = page[page.index(".tzcols{"):]
    assert css.startswith(".tzcols{display:grid;grid-template-columns:1fr;")
    assert ".vside{order:-1}" not in page                                    # 手機也是雷達在最上面




def test_sig_items_feed_overview(built, monkeypatch):
    """訊號總覽依指標整理（docs/lab_sigview_plan.md 第 2.1 節）：景氣頁算好每一項與每個面向的現在、近一年每週 0～100，交給訊號總覽。"""
    from arm.lab import sigpage as SPG
    B, _, V, _ = built
    it = V["sigitems"]
    for d, L in V["dims"].items():
        assert "D" + d in it and it["D" + d]["band"] == L["band"]
        for x in L["items"]:
            v = it[x["k"]]
            assert v["v"] == x["val"] and v["d"] == x["src"] and len(v["sp"]) == min(53, len(VZ.PO.week_ends(B["cal"])))
            assert all(s is None or (isinstance(s, int) and 0 <= s <= 100) for s in v["sp"])
            assert set(v) == {"v", "d", "h", "band", "pos", "dv", "why", "u", "dec", "hot", "sp"}
    monkeypatch.setattr(SPG, "ITEMS", {})
    monkeypatch.setattr(SPG, "CARDS", {})
    VZ.stash_cards(V)
    assert SPG.ITEMS == {V["mk"]: it}


def _it(k, name, ago, heat, n, rec=None):
    return {"k": k, "name": name, "ago": ago, "heat": heat, "dpull": (heat - ago) / n, "pos": {"rec": rec or {}}}


def test_moves_one_row_per_dimension_with_main_reasons():
    """這週變化（2026-10-20 使用者：「這週變化那邊看不懂，有點亂」）：每個面向一列＝上週 → 現在、換區、主要原因
    （拉動最多、和變化同方向的兩項），動 ±3 分以內收成一行；3 年以上新高新低照舊列在最後。"""
    tech = [_it("t1", "對 20 日線乖離", 74, 8, 4), _it("t2", "RSI", 72, 12, 4), _it("t3", "美國 VIX", 30, 17, 4),
            _it("t4", "距高點", 60, 70, 4)]
    liq = [_it("g1", "高收益債", 62, 27, 5), _it("g2", "2 年債", 10, 13, 5), _it("g3", "貨幣基金", 5, 2, 5),
           _it("g4", "聯準會", 20, 27, 5), _it("g5", "10 年債", 8, 12, 5)]
    fund = [_it("f1", "燈號", 93, 94, 2, {"kind": "since_y", "n": 42, "side": "hi"}), _it("f2", "PMI", 95, 94, 2)]
    sc = lambda its: 50 + sum((it["heat"] - 50) / len(its) for it in its)  # noqa: E731
    ag = lambda its: 50 + sum((it["ago"] - 50) / len(its) for it in its)  # noqa: E731
    V = {"viz": {"t0": "2026-10-12"}, "dims": {
        "fund": {"score": sc(fund), "ago": ag(fund), "items": fund},
        "gliq": {"score": sc(liq), "ago": ag(liq), "items": liq},
        "tech": {"score": sc(tech), "ago": ag(tech), "items": tech}}}
    h = VZ.moves_html(V)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    rows = re.findall(r'<li class="wr">.*?</li>', h)
    assert len(rows) == 2 and 'data-k="tech"' in rows[0] and 'data-k="gliq"' in rows[1]   # 依變化大小排序
    assert "和 10/12（一）比" in txt
    assert "59 → 27 −32 中性 → 偏冷" in txt and "21 → 16 −5 偏冷 → 過冷" in txt
    assert "主要是 對 20 日線乖離 74→8 （−16.5） 進入過冷 、 RSI 72→12 （−15.0） 進入過冷 ；另外 美國 VIX 進入過冷" in txt
    assert "距高點" not in rows[0]                                            # 反方向的不算主要原因
    assert "主要是 高收益債 62→27 （−7.0） ；其他項目往反方向拉回 +2.2" in txt  # 只有一項同方向超過 1 分
    assert "貨幣基金" not in rows[1]                                          # 拉動不到 1 分不算
    assert "其他沒什麼變 燈號" not in txt and "其他沒什麼變 基本面 94（0）" in txt
    assert "創新高、新低 燈號 42 年新高" in txt
    assert txt.count("wtk") == 0 and h.count('class="wtk"') == 2             # 每列一條小軌道
    assert 'style="left:66.5%;width:' not in h and re.search(r'class="wo" style="left:\d', h)
    assert not any(w in txt for w in BANNED)


def test_moves_empty_week():
    its = [_it("f1", "燈號", 50, 51, 1)]
    V = {"viz": {"t0": "2026-10-12"}, "dims": {"fund": {"score": 51, "ago": 50, "items": its}}}
    txt = html.unescape(re.sub(r"<[^>]+>", " ", VZ.moves_html(V)))
    assert "其他沒什麼變" in txt and "創新高" not in txt
    V["dims"]["fund"] = {"score": None, "ago": 50, "items": its}
    assert "這週各面向都沒什麼變" in VZ.moves_html(V)


def _scen_row(mk, key, name, up, warn, occ, a="2009-01-02", z="2026-10-19", ret=None):
    st = lambda hit, base, t, n=12: {"n": n, "hit": hit, "base": base, "tier": t, "n10": n, "hit10": hit, "base10": base}  # noqa: E731
    r = {"id": f"{mk}:scen:{key}", "mk": mk, "cat": "scen", "grp": "scen", "var": key, "vn": name, "name": name,
         "kind": "state", "H": 60, "th": 0.10, "a": a, "z": z, "up": st(*up), "warn": st(*warn), "tier": up[2],
         "dir": ["up"], "occ": occ}
    if ret:
        r["ret"] = ret
    return r


def _cell(n, med, up, mae):
    return [n, med, med - 0.03, med, med + 0.03, up, mae, mae - 0.05, mae - 0.1]


def test_scenario_table(monkeypatch):
    """所有情境＝一張表（docs/lab_outlook_plan.md 第 3 節；2026-10-20 使用者：「交互的頁面看起來很不清楚」）：每列＝條件附現在的分數、
    3 個月後上漲（橫條＋隨便挑一天）、報酬中位數、中途最多跌、大跌、判定、段數；現在成立的排最上面；點一列展開過去出現的時候。"""
    from arm.lab import sigcat as G
    from arm.lab import sigspec as SS
    j = SS.RET_H.index(60)
    ret = {"s": [None] * j + [_cell(12, 0.044, 0.65, -0.03)] + [None] * (len(SS.RET_H) - j - 1), "bk": "b1"}
    bases = {"b1": {"s": [None] * j + [_cell(5000, 0.026, 0.63, -0.04)] + [None] * (len(SS.RET_H) - j - 1)}}
    rows = [_scen_row("tw", "SC1", "景氣好、價格強", (0.47, 0.63, "none"), (0.39, 0.35, "none"), []),
            _scen_row("tw", "SC2", "景氣好、價格回檔", (0.65, 0.63, "none"), (0.38, 0.35, "none"),
                      [["2015-03-02", "2015-05-29", 60, 0.7, 0.3, 0.05, 0.02], ["2026-07-17", "2026-10-19", 66, 1, 0, 0.04, 0.03]],
                      ret=ret),
            _scen_row("tw", "SC6", "資金寬鬆、價格弱", (0.67, 0.68, "few", 3), (0.33, 0.24, "few", 3), []),
            _scen_row("spx", "SC2", "景氣好、價格回檔", (0.76, 0.66, "ref"), (0.36, 0.40, "none"), [])]
    monkeypatch.setattr(G, "research_rows", lambda: rows)
    monkeypatch.setattr(G, "research_bases", lambda: bases)
    dims = {"fund": {"score": 94.0, "band": "過熱"}, "chip": {"score": 88.0, "band": "過熱"},
            "gliq": {"score": 17.0, "band": "過冷"}, "tliq": {"score": 45.0, "band": "中性"}, "tech": {"score": 33.0, "band": "偏冷"}}
    V = {"mk": "tw", "dims": dims, "signow": {"on": {"tw:scen:SC2": {"since": "2026-07-17", "n": 66}}}}
    assert VZ.scen_now(V) == {"fund": 94.0, "chip": 88.0, "liq": 31.0, "tech": 33.0}
    h = VZ.scen_html(V)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    assert h.count('<details class="sqr') == 3 and 'class="sqr on" id="sq-SC2"' in h
    assert h.index('id="sq-SC2"') < h.index('id="sq-SC1"')                   # 現在成立的排最上面
    assert "現在成立的 1 個列在上面" in txt and "現在・2026/7/17 起" in txt
    # 2026-10-21 起在「之後怎麼走？」面板裡：沒成立的收起來（docs/lab_noise_plan.md 第 11 節）
    assert '<details class="osq"><summary>其他 2 個情境（現在沒有成立）</summary>' in h
    assert h.index('id="sq-SC2"') < h.index('<details class="osq">') < h.index('id="sq-SC1"')
    assert "基本面 ≥ 60（現在 94 ）・技術 < 40（現在 33 ）" in txt              # 「<」要跳脫，不能被當成標籤吞掉
    assert "&lt; 40" in h and "資金 ≥ 60（現在 31 ）" in txt                     # 台股資金＝(17＋45)÷2
    assert "65% 隨便挑一天 63%" in txt and "38% 隨便挑一天 35%" in txt and "3 個月內大跌（回撤 10% 以上）" in txt
    assert "+4.4% 隨便挑一天 +2.6%" in txt and "−3.0% 隨便挑一天 −4.0%" in txt   # 報酬中位數、中途最多跌（第 4.11 節）
    assert 'style="width:65.0%"' in h and 'style="left:63.0%"' in h           # 上漲橫條＋隨便挑一天的細線
    assert 'data-dims="fund tech"' in h and 'data-dims="gliq,tliq tech"' in h   # 台股資金一組兩個（對照圖選到任一個就算）
    assert h.count('class="sqtb"') == 3 and 'title="2015/3/2～2015/5/29"' in h
    assert 'href="x9o.html#s=tw:scen:SC2"' in h and "90 個比較" in txt and "2009 年起" in txt
    assert txt.count("次數不夠") >= 1 or "—" in txt
    assert not any(w in txt for w in BANNED)
    V2 = {**V, "signow": {"on": {}}}
    assert "現在成立的 0 個" in html.unescape(VZ.scen_html(V2)) and 'class="sqr on"' not in VZ.scen_html(V2)
    assert '<details class="osq" open><summary>全部 3 個情境' in VZ.scen_html(V2)       # 沒有成立的：全部列出來、展開
    monkeypatch.setattr(G, "research_rows", lambda: [])
    assert "情境的研究結果還沒產生" in VZ.scen_html(V)
    # 美股不寫台股的說明
    monkeypatch.setattr(G, "research_rows", lambda: rows)
    Vu = {"mk": "spx", "dims": {"fund": {"score": 65.0}, "sent": {"score": 41.0}, "liq": {"score": 38.0}, "tech": {"score": 37.0}},
          "signow": {"on": {}}}
    hu = VZ.scen_html(Vu)
    assert "台股" not in hu and "情緒籌碼 2008 年起" in hu and 'data-dims="fund tech"' in hu
    assert [k for k, *_ in SS.SCENARIOS][:2] == ["SC1", "SC2"]


def _sim_est(n_list=8, far=False, chip=True):
    from arm.lab import sigspec as SS
    rows = []
    for h in SS.RET_H:
        rows.append({"h": h, "n": 20 if h < 250 else 14, "dist": 16.0 if far else 4.2, "far": far, "a": "2009-03-02",
                     "s": _cell(20, 0.052, 0.75, -0.025), "b": _cell(4000, 0.032, 0.68, -0.032)})
    lst = [{"d": f"20{10 + i}-02-0{1 + i % 8}", "dist": 1.0 + i, "x": [89.0, 31.0, 33.0], "c": None if i == 1 else 64.0,
            "r": {20: 0.005, 60: -0.085, 250: None if i == 0 else -0.099}, "mae": -0.112} for i in range(n_list)]
    E = {"d": "2026-10-20", "dims": ["fund", "liq", "tech"], "x": [94.0, 30.0, 33.0], "rows": rows, "list": lst}
    if chip:
        E["chip"] = {"dims": ["fund", "chip", "liq", "tech"], "x": [94.0, 87.0, 30.0, 33.0],
                     "rows": [{"h": 60, "n": 20, "dist": 15.2, "a": "2019-12-12", "s": _cell(20, 0.049, 0.75, -0.03),
                               "b": _cell(1500, 0.058, 0.71, -0.035)}]}
    return E


def test_now_section(monkeypatch):
    """現在的情境（docs/lab_outlook_plan.md 第 2 節；sigspec 第 4.12 節）：現在的面向、最像的日子之後 1 天～1 年、
    準不準（樣本外，第 11 節；沒有一個期間比平常準 → 寫明不要當成預估）、最像的幾段（前 5 段，其餘收起）、現在成立的情境。"""
    from arm.lab import sigcat as G
    from arm.lab import sigspec as SS
    rows = [_scen_row("tw", "SC2", "景氣好、價格回檔", (0.65, 0.63, "none"), (0.38, 0.35, "none"), [])]
    monkeypatch.setattr(G, "research_rows", lambda: rows)
    oos = {h: {"h": h, "n": 140, "a": "2015-01-30", "v": "worse" if h < 120 else "none", "bp": 0.259, "bq": 0.221, "d": -0.037,
               "lo": -0.054, "hi": -0.014, "h1": -0.032, "h2": -0.042, "hi_n": 52, "hi_up": 0.577, "hi_q": 0.663} for h in SS.RET_H}
    monkeypatch.setattr(VZ, "sim_research", lambda mk: oos)
    V = {"mk": "tw", "signow": {"on": {"tw:scen:SC2": {"since": "2026-07-17"}}, "sim": _sim_est()}}
    h = VZ.now_html(V)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    assert 'id="now"' in h and "基本面 94 過熱" in txt and "資金 30 偏冷" in txt and "籌碼 87 過熱" in txt
    assert "過去和現在最像的 20 段（2009 年起找，平均每個面向差 4.2 分），之後 3 個月上漲 75% （隨便挑一天 68%）" in txt
    assert "比平常準 0、看不出比較準 2、比平常差 5" in txt and "不要當成預估" in txt and 'class="nsacc bad"' in h
    assert h.count('<td class="l nsp">') == len(SS.RET_H) + len(SS.RET_H) + 8   # 期間表、樣本外表、最像的幾段
    assert "只找到 14 段" in txt and "比平常差" in txt and "看不出比較準" in txt
    assert "+5.2% +3.2%" in txt and "−2.5%／−7.5%" in txt                         # 報酬中位數（小字＝隨便挑一天）、中途最多跌中位／最差 10%
    assert "加上籌碼一起比（2019 年起才有）" in txt and "歷史短，沒有做樣本外檢查" in txt
    assert "52 個月：實際 58%（隨便挑一天 66%）" in txt and "−0.054～−0.014" in txt
    assert h.count('class="nsh"') == 3 and 'id="nsall"' in h and "看全部 8 段" in txt   # 前 5 段以外收起來
    assert "2010/2/1" in txt and "−8.5%" in txt and "1.0" in txt
    assert 'href="#sq-' not in h and "<h2" not in h                              # 面板裡：標題由收合列給、情境就在上一段
    assert not any(w in txt for w in BANNED)
    # 過去沒有很像的日子、籌碼今天沒有分數、研究檔沒有、最像的不到 5 段
    monkeypatch.setattr(VZ, "sim_research", lambda mk: {})
    h2 = VZ.now_html({"mk": "tw", "signow": {"on": {}, "sim": _sim_est(n_list=3, far=True, chip=False)}})
    t2 = html.unescape(re.sub(r"<[^>]+>", " ", h2))
    assert "過去沒有很像現在的日子" in t2 and "籌碼今天沒有分數" in t2 and "樣本外檢查還沒產生" in t2
    assert 'id="nsall"' not in h2 and "沒有" in t2
    assert "沒有找相似的日子" in VZ.now_html({"mk": "tw", "signow": {"on": {}}})
    # 美股：情緒籌碼、沒有台股字樣
    hu = VZ.now_html({"mk": "spx", "signow": {"on": {}, "sim": _sim_est()}})
    assert "情緒籌碼 87" in re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", hu))) and "台股" not in hu


def test_outlook_drawer_replaces_now_and_scenario_sections(built, monkeypatch):
    """2026-10-21（docs/lab_noise_plan.md 第 4、11 節；使用者 10/20 選「雷達按鈕打開的面板」）：「現在的情境」「所有情境」不在主畫面，
    改成雷達卡片裡「之後怎麼走？」按鈕打開右側面板（template ot-out）；目錄、市場狀態那一行、對照圖都打開同一個面板。"""
    _, _, V, page = built
    i = page.index('<template id="ot-out"')
    j = page.index("</template>", i)
    main, body = page[:i] + page[j:], page[i:j]
    assert 'id="now"' not in main and 'id="scen"' not in main and 'id="now"' in body and 'id="scen"' in body
    assert page.index('id="today"') < page.index('id="items"') < page.index('id="cmp"')
    assert 'href="#now"' not in page and 'href="#scen"' not in page
    assert 'class="snout" data-open="out:out">之後怎麼走？</button>' in page
    assert page.count('class="rout" data-open="out:out"') == 1 and page.index('class="rout"') < page.index('id="rtin"')
    assert 'data-title="之後怎麼走？"' in body and '<details class="osim" id="o-sim">' in body
    assert body.index("好訊號成立之後") < body.index("五個面向現在的位置") < body.index('id="scen"') < body.index('id="o-sim"')
    assert 'data-open="out:out"' in page[page.index('<template id="dt-fund"'):]          # 面向面板也連得過去
    from arm.lab import heatpage as HP
    V2 = {**V, "mk": "tw", "signow": {"on": {"tw:scen:SC5": {"since": "2026-07-17", "n": 66}}}}
    line = HP.state_line(V2)
    assert 'data-open="out:out" data-to="scen"' in line and "籌碼熱、價格轉弱" in line
    assert "情境" not in HP.state_line({**V, "signow": {"on": {}}})
    js = VZ.JS
    assert "kind === 'out' ? 'ot-'" in js and "function oJump(id)" in js and "hget('o')" in js
    assert "bx.dataset.ix !== ix0" in js                                                   # 美股頁：等切到網址上的指數再開
    assert "window.heatScenHl(DC)" in js and "push: !!(DRW && DRW.contains(op))" in js


def _board_v(fams_up, fams_warn, xsb=None, more=None):
    """sigcat.board 的輸出形狀：溫度計照 sigspec 第 5 節 ③（VER 12）由這些類算（more＝溫度計另外算進去的 ●、△ 類）。"""
    from arm.lab import sigspec as SS
    allf = {"up": list(fams_up) + [x for x in (more or []) if x["side"] == "up"],
            "warn": list(fams_warn) + [x for x in (more or []) if x["side"] == "warn"]}
    th = []
    for k, nm, h in SS.THERMO_HZ:
        n = {s: {t: sum(1 for x in allf[s] if x.get("hz") == k and x.get("tier", "good") == t) for t in SS.THERMO_W}
             for s in allf}
        w = {s: sum(SS.THERMO_W[t] * c for t, c in n[s].items()) for s in n}
        tot = w["up"] + w["warn"]
        share = w["up"] / tot if tot else None
        lean = None if share is None else "up" if share >= SS.THERMO_LEAN else "warn" if share <= 1 - SS.THERMO_LEAN else "even"
        mo = {s: [x for x in allf[s] if x.get("hz") == k and x.get("tier", "good") != "good"] for s in allf}
        th.append({"k": k, "name": nm, "h": h, "n": n, "w": w, "share": share, "lean": lean, "more": mo})
    return {"up": fams_up, "warn": fams_warn, "thermo": th}


def test_outlook_signals_table_and_summary(monkeypatch):
    """面板第一段：現在成立的 ★（同類合併後一類一列），過去出現之後 1 週～1 年的上漲機率、報酬中位數、中途最多跌，
    小字＝隨便挑一天；判定看的期間框起來；次數少的格子標次數。三支溫度計的一句話也用在雷達按鈕上。"""
    from arm.lab import sigcat as G
    from arm.lab import sigspec as SS
    cells = [_cell(80 - k, 0.01 * (k + 1), 0.6 + 0.03 * k, -0.01 * (k + 1)) for k in range(len(SS.RET_H))]
    cells[SS.RET_H.index(250)] = _cell(7, 0.15, 0.86, -0.08)
    base = [_cell(5000, 0.005 * (k + 1), 0.55, -0.02 * (k + 1)) for k in range(len(SS.RET_H))]
    monkeypatch.setattr(G, "research_bases", lambda: {"b9": {"s": base}})
    up = {"id": "tw:heat:T4:cold", "name": "RSI（14 日）・過冷中", "cat": "heat", "var": "T4", "H": 20, "d": "up", "side": "up",
          "hz": "short", "tier": "good", "edge": 0.23, "now": {"since": "2026-09-15"},
          "up": {"hit": 0.81, "base": 0.58, "n": 82, "tier": "good"}, "ret": {"s": cells, "bk": "b9"},
          "fam": [{"id": "tw:heat:T1:cold", "name": "對 20 日線乖離・過冷中", "cat": "heat"}]}
    warn = {"id": "tw:multi:M2:hot_in", "name": "進入同時兩個以上面向過熱", "cat": "multi", "var": "M2", "H": 60, "d": "warn",
            "side": "warn", "hz": "mid", "tier": "good", "edge": 0.38, "th": 0.10, "now": {"since": "2026-09-17"},
            "warn": {"hit": 0.67, "base": 0.29, "n": 6, "tier": "good", "mdd": 0.12, "mdd_base": 0.06},
            "ret": {"s": cells, "bk": "b9"}, "fam": []}
    V = {"mk": "tw", "sigtoday": _board_v([up], [warn]), "xsb": [{"name": "RSI(2) 超賣反彈", "side": "up"}]}
    assert VZ.out_summary(V) == "溫度計 短線偏多｜中線偏警示｜長線中性"                 # VER 12：按鈕上寫三支溫度計的讀數
    h = VZ.out_sig(V)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    assert h.count('class="ofam ofam-') == 2 and h.index("RSI（14 日）") < h.index("進入同時兩個以上面向過熱")   # 短線在前
    assert "同時成立：對 20 日線乖離・過冷中" in txt and "之後 1 個月上漲的機率 81%" in txt
    j20, j60 = SS.RET_H.index(20), SS.RET_H.index(60)
    assert f"{cells[j20][5] * 100:.0f}%" in txt and f"{base[j20][5] * 100:.0f}%" in txt
    t0 = h.index('class="ofam ofam-up"')
    one = h[t0:h.index('class="ofam ofam-warn"')]
    assert one.count('<th class="oj">') == 1 and '<th class="oj">1 個月</th>' in one        # 判定看 1 個月
    assert '<th class="oj">3 個月</th>' in h[h.index('class="ofam ofam-warn"'):]
    assert "7 次" in txt                                                                      # 次數少的格子標次數
    assert "大跌（最大回撤 10% 以上）的機率 67%" in txt and "RSI(2) 超賣反彈" in txt
    assert not any(w in txt for w in BANNED)
    assert "現在沒有成立的好訊號" in VZ.out_sig({"mk": "tw", "sigtoday": _board_v([], [])})
    assert "研究結果還沒產生" in VZ.out_sig({"mk": "tw"}) and VZ.out_summary({"mk": "tw"}) == "好訊號的研究結果還沒產生"


def test_outlook_dims_use_zone_backtest(built):
    """面板第二段：五個面向（泡沫不列）現在這一區，過去在這一區之後的平均、上漲機率、中途最多跌（括號＝所有日子）與研究判定。"""
    _, _, V, _ = built
    h = VZ.out_dims(V)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h)))
    from arm.lab import heatpage as HP
    shown = [d for d in V["dims"] if d not in HP.HIDE_DIMS]
    assert h.count('class="odim"') == len(shown) and "泡沫" not in txt
    L = next(L for d, L in V["dims"].items() if d in shown and L.get("band"))
    e = VZ._zones(VZ._ev(L["cev"], L["fwd"][0]))
    cur = e.get(L["band"]) or {}
    if cur.get("n"):
        assert f'上漲 {cur["up"]:.0f}%' in txt
    assert not any(w in txt for w in BANNED)

def test_outlook_lead_sentence():
    from arm.lab import sigspec as SS
    th = [{"k": k, "name": n, "h": h} for k, n, h in SS.THERMO_HZ]
    V = {"sigtoday": {"up": [{"hz": "short"}, {"hz": "short"}, {"hz": "mid"}], "warn": [{"hz": "mid"}], "thermo": th}}
    assert VZ.out_sentence(V) == "短線偏多 2 類；中線偏多 1 類、警示 1 類；長線沒有"
    assert "——" not in VZ.out_tpl.__doc__ + VZ.out_sentence(V)
    # VER 12：面板開頭先寫三支溫度計的讀數（溫度計比 ★ 寬：長線沒有 ★ 也可能有讀數）
    up = [{"hz": "short", "tier": "good", "side": "up"}, {"hz": "mid", "tier": "good", "side": "up"}]
    more = [{"hz": "long", "tier": "ref", "side": "warn"}, {"hz": "long", "tier": "lean", "side": "up"},
            {"hz": "mid", "tier": "ref", "side": "warn"}, {"hz": "mid", "tier": "lean", "side": "warn"}]
    V2 = {"sigtoday": _board_v(up, [], more=more)}
    assert VZ.out_thermo(V2) == "短線偏多、中線差不多、長線偏警示"        # 中線 ★2 對 ●1＋△0.5＝57%；長線 △0.5 對 ●1＝33%
    assert VZ.out_thermo({"sigtoday": _board_v([], [])}) == "短線中性、中線中性、長線中性"
