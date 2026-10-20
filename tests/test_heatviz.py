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
    assert page.count("<script>") == 2                                        # 雷達程式和對照圖程式在同一個 script


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
    assert 'id="today"' in side and side.index('id="today"') < side.index('id="wchg"')
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
