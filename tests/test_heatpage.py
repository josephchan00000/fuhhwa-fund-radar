"""景氣溫度頁 x9m.html（arm/lab/heatpage.py；第五版：熱度色帶頁首、對照台股互動圖、五個面向卡、邊際變化、關鍵價位與事件）：
用合成資料跑完整條管線（heatcalc → view → render）；瀏覽器端的交互分析用 node 和 Python 的 heatrel.group_stats 比對。"""
import json
import random
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from arm.lab import heat as H
from arm.lab import heatcalc as C
from arm.lab import heatpage as P
from arm.lab import heatspec as S

BANNED = ["保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠"]


def _days(a: date, n: int):
    d, out = a, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def synthetic_D(n=1300, seed=5):
    rnd = random.Random(seed)
    cal = _days(date(2021, 6, 1), n)
    D = {k: {} for k in C.FILES + ["rev"]}
    D["sfbflow"] = {"2026-09": [178.7, 4285.53], "2026-08": [None, 4106.83]}
    p, mg, fx, h, i_, v, u10 = 15000.0, 2.5e11, 28.0, 80.0, 100.0, 18.0, 4.0
    for d in cal:
        p *= 1 + rnd.gauss(0.0004, 0.011)
        mg *= 1 + rnd.gauss(0, 0.004)
        fx *= 1 + rnd.gauss(0, 0.002)
        h *= 1 + rnd.gauss(0.0001, 0.004)
        i_ *= 1 + rnd.gauss(0, 0.003)
        v = max(9.0, v * (1 + rnd.gauss(0, 0.05)))
        u10 = max(0.5, u10 + rnd.gauss(0, 0.05))
        D["turnover"][d] = [3e11 * (1 + rnd.random()), round(p, 2)]
        D["margin"][d] = [mg, 4e6 * (1 + rnd.random() / 10), 1e5 * (1 + rnd.random())]
        D["inst"][d] = {"total": rnd.gauss(0, 1e10), "Foreign_Investor": rnd.gauss(0, 8e9)}
        D["pcr"][d] = [1, 1, 80 + rnd.gauss(0, 15), 1, 1, 1]
        D["vix"][d] = v
        D["hyg"][d], D["ief"][d], D["usdtwd"][d] = h, i_, fx
        D["ust"][d] = [4.0, 4.2 + rnd.gauss(0, 0.05), u10]
        D["spx"][d] = 4000 * (1 + rnd.gauss(0, 0.01))
        D["qfii"][d] = [3e9 * (1 + rnd.gauss(0, 0.002)), 1e10]
        if date.fromisoformat(d).weekday() == 4:
            D["sitca"][d] = 90 + rnd.random() * 8
        D["breadth"][d] = [rnd.randint(200, 800), rnd.randint(200, 800), rnd.randint(300, 900), 1000, rnd.randint(0, 60),
                           rnd.randint(0, 60), 1000]
        D["futi"][d] = {"TX": {"外資": [rnd.randint(5000, 30000), rnd.randint(5000, 60000)]},
                        "MTX": {"外資": [rnd.randint(1000, 9000), rnd.randint(1000, 9000)], "投信": [10, 20], "自營商": [30, 40]}}
        D["mtxoi"][d] = 40000 + rnd.randint(-5000, 5000)
        D["opti"][d] = {"買權": {"外資": [rnd.randint(1, 9) * 1e5, rnd.randint(1, 9) * 1e5]},
                        "賣權": {"外資": [rnd.randint(1, 9) * 1e5, rnd.randint(1, 9) * 1e5]}}
    for d in cal[-60:]:
        D["vixtw"][d] = 20 + rnd.random()
    for k in range(400):
        ym = C.ym_add("1993-01", k)
        D["ndc"][ym] = [100.0, 100 + rnd.gauss(0, 2), 100.0, 100.0, 100.0, 100.0, float(rnd.randint(12, 40)), "綠"]
        D["orders"][ym] = 1000 + 10 * k + rnd.gauss(0, 50)
        D["exports"][ym] = 800 + 8 * k + rnd.gauss(0, 40)
        D["money"][ym] = [1e6, rnd.gauss(5, 3), 2e6, rnd.gauss(5, 1)]
        D["twcpi"][ym] = [100.0, rnd.gauss(1.5, 1)]
        D["uscpi"][ym] = 150 * (1.002 ** k) * (1 + rnd.gauss(0, 0.002))
        if k > 230:
            D["pmi"][ym] = 50 + rnd.gauss(0, 4)
        D["cbcbank"][ym] = [3e5 * (1 + rnd.random()), rnd.gauss(5, 2), rnd.gauss(6, 2), 1 + rnd.random()]
        if ym >= "2010-11":
            D["mmf"][ym] = 3e12 * (1 + rnd.random())
        if ym >= "2012-01":
            a = 1e9 * (1 + rnd.random())
            D["rev"][ym] = [a, a / (1 + rnd.gauss(0.08, 0.1)), 1500]
    for d in _days(date(1993, 1, 4), 8800):                  # 聯邦基金利率：每天一筆（G1 每天算，要涵蓋到日曆最後一天）
        D["effr"][d] = 3.0 + (int(d[:4]) * 12 + int(d[5:7])) % 40 / 20
    return D


def research_stub(B):
    R = {"ver": S.VER, "dims": {}, "data": {"margin": [10, "2021-06-01", "2026-07-01"]},
         "events": {k: {str(h): {"n": 40, "avg": 0.01, "up": 0.55, "all_avg": 0.008, "all_up": 0.54, "diff": 0.002,
                                 "lo": -0.004, "hi": 0.008, "a": "1998-07-01", "verdict": "none",
                                 "h1": {"n": 20, "diff": 0.001}, "h2": {"n": 20, "diff": 0.003}} for h in S.EV_FWD}
                    for k in S.EVENTS}}
    bands = [{"band": b, "n": 100, "avg": 0.5, "med": 0.4, "up": 55.0, "dd": -2.0, "yrs": ["2004", "2010", "2021", "2022"]}
             for b in ("過冷", "偏冷", "中性", "偏熱", "過熱")] + [{"band": "全部", "n": 500, "avg": 0.5, "med": 0.4, "up": 55.0, "dd": -2.0}]

    def ev():
        return {"n": 1200, "rho": -0.1, "lo": -0.2, "hi": -0.01, "a": "2014-01-02", "z": "2026-01-02",
                "h1": {"n": 600, "rho": -0.12, "z": "2019-06-28"}, "h2": {"n": 600, "rho": -0.05, "a": "2019-07-01"},
                "verdict": "weak", "bands": bands, "ref": [{"n": 500, "rho": -0.1}, {"n": 600, "rho": 0.02}], "block": 10}
    for dim, L in S.DIMS.items():
        R["dims"][dim] = {"items": {k: {str(h): ev() for h in L["fwd"]} for k in S.ITEMS[dim]},
                          "first": {k: B["cal"][0] for k in S.ITEMS[dim]},
                          "comp": {str(h): ev() for h in L["fwd"]}, "comp_first": B["cal"][0]}
    return R


@pytest.fixture(scope="module")
def built():
    B = C.build(synthetic_D())
    R = research_stub(B)
    V = P.view(B, R)
    return B, R, V, P.render(V)


def test_each_item_has_own_heat_and_pulls_sum_to_score(built):
    _, _, V, _ = built
    assert list(V["dims"]) == ["fund", "chip", "gliq", "tliq", "tech"]
    for dim, L in V["dims"].items():
        assert L["score"] is not None, dim
        pulls = [it["pull"] for it in L["items"] if it["pull"] is not None]
        assert len(pulls) == L["n_have"] >= H.need(len(S.ITEMS[dim]))
        assert abs(50 + sum(pulls) - L["score"]) < 1e-9                   # 拉動加起來＋50＝分數
        shares = [it["share"] for it in L["items"] if it["share"] is not None]
        assert abs(sum(shares) - 100) < 1e-6
        for it in L["items"]:
            assert it["heat"] is None or 0 <= it["heat"] <= 100            # 每一項都有自己的 0～100
            assert it["pull"] is not None or it["proxy"] or it["why"]       # 沒算進分數的寫原因
    t10 = next(it for it in V["dims"]["tech"]["items"] if it["k"] == "T10")
    t9 = next(it for it in V["dims"]["tech"]["items"] if it["k"] == "T9")
    assert t10["proxy"] and t10["pull"] is None and t10["heat"] == t9["heat"]   # 台指 VIX 用美國 VIX 代替、不算進分數


def test_render_structure_and_wording(built):
    _, _, V, page = built
    for sec in ('id="top"', 'id="cmp"', 'id="c-fund"', 'id="c-chip"', 'id="c-gliq"', 'id="c-tliq"', 'id="c-tech"',
                'id="dv"', 'id="ta"', 'id="valid"', 'id="src"'):
        assert sec in page, sec
    for gone in ('id="trend"', 'id="detail"', 'class="tile"'):              # 第五版拿掉靜態走勢圖、各項明細、頁首數字卡
        assert gone not in page, gone
    assert page.count('<a class="sr" href="#c-') == 5 and S.HORIZON_NOTE in page    # 五個面向的近 52 週色帶
    for d in S.DIMS:
        st = V["strips"][d]
        assert len(st["cells"]) == min(S.STRIP_WEEKS, len(P.HP.week_ends(built[0]["cal"])))
        assert P.strip_text(st) in page
    assert V["summary"] and V["summary"] in page
    assert page.count('class="it"') >= 35 and "拉動分數" in page and "佔比" in page and "本週" in page
    assert page.count('<tr><td class="l">', page.index('class="evt"')) >= len(S.EVENTS)      # 16 種事件各一列
    for nm in ("月線（20 日）", "季線（60 日）", "年線（240 日）", "扣抵值", "前波高點", "近 60 個交易日的事件"):
        assert nm in page, nm
    assert "證期局只公開最新一期新聞稿" in page                                  # 外資淨匯入沒有 0～100 的原因
    assert "用美國 VIX 的排名代替，不算進分數" in page and "前一半" in page and "後一半" in page
    assert "熱＝散戶擁擠、槓桿高、外資站在對面" in page
    assert "出現在 2004、2010、2021–2022 年" in page                            # 樣本集中在哪幾段要看得出來
    assert P._yrs(["2021", "2022", "2024", "2025", "2026"]) == "2021–2022、2024–2026" and P._yrs(None) == ""
    assert 'href="x9.html"' in page
    for w in BANNED:                                                         # 頁面文字與 JS 都不能有
        assert w not in page, w
    assert P.render(V) == page                                                # 決定性


def test_items_show_history_position_and_marginal_change(built):
    B, _, V, page = built
    n_pos = sum(1 for L in V["dims"].values() for it in L["items"] if P.pos_line(it["k"], it["pos"]))
    assert n_pos >= 35 and page.count('<i class="ipos">') == n_pos             # 每一項名稱下面有歷史位置
    assert "的日子高" in page or "的日子低" in page
    have_dv = [k for k in S.DERIV if V["dvn"].get(k)]
    assert len(have_dv) >= 10 and page.count('<i class="idv">邊際變化：') == len(have_dv)
    dv = page[page.index('id="dv"'):page.index('id="ta"')]
    assert dv.count('<button type="button" class="nmb" data-k="') == len(S.DERIV) == 13   # 核心 13 項（規劃時數錯寫成 14）
    for k in have_dv:
        assert P.dv_line(k, V["dvn"][k]) in dv
    for it in (i for L in V["dims"].values() for i in L["items"]):             # 點項目名稱 → 對照圖只看這一項
        assert f'class="nmb" data-k="{it["k"]}"' in page


def test_pos_line_wording():
    pos = {"x": 41, "p3": 99.8, "p10": 100.0, "pall": 100.0, "from": "1984-01",
           "rec": {"side": "hi", "kind": "since_y", "d": "1984-01", "tie": False, "n": 42},
           "rng": {"hi": 41, "hi_d": "2026-09", "lo": 9, "lo_d": "2016-01", "side": "hi", "dist": 0, "how": "abs", "a": "2016-10"}}
    assert P.pos_line("B1", pos) == "比近 3 年 99%、近 10 年 100%、1984 年以來 100% 的月份高；1984 年 1 月以來最高，42 年新高"
    pos = {"x": 6456, "p3": 99.6, "p10": 99.9, "pall": 99.9, "from": "2001-01-02",
           "rec": {"side": "hi", "kind": None, "d": "2026-10-12", "tie": False, "n": None},
           "rng": {"hi": 6533, "hi_d": "2026-10-12", "lo": 1000, "lo_d": "2020-03-19", "side": "hi", "dist": -1.18,
                   "how": "pct", "a": "2016-10-17"}}
    assert P.pos_line("C1", pos) == "比近 3 年 99%、近 10 年 99%、2001 年以來 99% 的日子高；近 10 年最高 6,533 億（2026/10/12），現在低 1.2%"
    pos = {"x": 1.097, "p3": 30.0, "p10": 20.4, "pall": 8.0, "from": "2015-12",
           "rec": {"side": "lo", "kind": "ath", "d": "2015-12", "tie": True, "n": None},
           "rng": {"hi": 2.0, "hi_d": "2020-03", "lo": 1.097, "lo_d": "2026-09", "side": "lo", "dist": 0, "how": "pct", "a": "2015-12"}}
    assert P.pos_line("G5", pos) == "比近 3 年 70%、近 10 年 79%、2015 年以來 92% 的月份低；有資料以來最低（並列，資料從 2015 年起）"
    mixed = {"p3": 30.0, "p10": 65.0, "pall": None, "from": "2010-01-04", "rec": None, "rng": None}
    assert P.pct_phrase(mixed, "d") == "比近 3 年 70% 的日子低，比近 10 年 65% 的日子高"
    short = {"x": 1.0, "p3": None, "p10": None, "pall": None, "from": "2026-09",
             "rec": None, "rng": {"hi": 2.0, "hi_d": "2026-09", "lo": 1.0, "lo_d": "2026-10", "side": "hi", "dist": -50.0,
                                  "how": "pct", "a": "2026-09"}}
    assert P.pos_line("L6", short) == ""                                       # 歷史太短：不寫範圍
    assert P.pos_line("C1", None) == ""


def test_dv_line_wording():
    dv = {"d1": 49.4, "d2": 12.7, "state": 1, "word": "成長加速", "streak": 3, "note": None, "asof": "2026-07"}
    assert P.dv_line("B5", dv) == "年增率 +49.4%，比 3 個月前高 12.7 個百分點：成長加速（連 3 個月）"
    dv = {"d1": -8453.2, "d2": -11317.0, "state": 3, "word": "下降加速", "streak": 11, "note": "淨空增加", "asof": "2026-10-16"}
    assert P.dv_line("C5", dv) == "20 日變化（5 日平均） −8,453 口，比前 20 日的變化低 11,317 口：下降加速（淨空增加）（連 11 天）"
    dv = {"d1": 13.4, "d2": 0.0, "state": 0, "word": S.DERIV_FLAT, "streak": 0, "note": None, "asof": "2026-09"}
    assert P.dv_line("B3", dv) == f"PMI − 50 +13.4，PMI 和 3 個月前一樣：{S.DERIV_FLAT}"
    assert P.dv_line("T1", dv) == "" and P.dv_line("B5", None) == ""


def test_dv_past_and_more_texts():
    st = {"n": 694, "runs": 51, "avg": 0.0101, "all_avg": 0.0441, "verdict": "weak"}
    rr = {"h": {"120": {"states": {"1": st}, "pc": {"r": -0.104, "q": 0.52, "verdict": "none"}},
                "250": {"states": {"1": {**st, "avg": 0.0302, "all_avg": 0.0851}}, "pc": {"r": -0.221, "q": 0.13, "verdict": "none"}}}}
    assert P.dv_past(rr, 1, (120, 250)) == "120 日 +1.0%（所有週 +4.4%）；250 日 +3.0%（所有週 +8.5%）。694 週、51 段；120 日之後較弱、250 日之後較弱"
    assert P.dv_more(rr, (120, 250)) == "沒有（120／250 日：偏相關 −0.10／−0.22，校正後 q 0.52／0.13）"
    rr["h"]["120"]["pc"] = {"r": 0.2153, "q": 0.052, "verdict": "strong"}
    assert P.dv_more(rr, (120, 250)) == "120 日：加速之後較強，比水準多出預測資訊（偏相關 +0.22，校正後 q＝0.05）"
    assert P.dv_past(rr, None, (120, 250)) == "—" and P.dv_past({}, 1, (120,)) == "—" and P.dv_more({}, (120,)) == "—"


def test_meta_matches_spec_and_is_embedded(built):
    _, _, V, page = built
    m = P.meta()
    a = page.index("<script>window.HEAT_META=") + len("<script>window.HEAT_META=")
    b = page.index(";</script>", a)
    assert json.loads(page[a:b].replace("<\\/", "</")) == json.loads(json.dumps(m))
    assert "</" not in page[a:b]                                              # 內嵌 JSON 不會提前結束 script
    assert m["cpl"]["hot"] == S.CPL_HOT and m["cpl"]["cold"] == S.CPL_COLD and m["cpl"]["boot"] == S.CPL_BOOT
    assert m["cpl"]["minw"] == S.CPL_MIN_WEEKS and m["cpl"]["minr"] == S.CPL_MIN_RUNS and m["cpl"]["seed"] == S.BOOT_SEED
    assert m["max"] == S.CH_MAX == 5 and len(m["pal"]) == S.CH_MAX and m["rdef"] in m["ranges"]
    assert set(m["items"]) == set(S.KEYS) and [d["id"] for d in m["dims"]] == list(S.DIMS)
    assert page.count("<script>") == 2 and "x9mh.json" in page                 # 序列資料另外下載


def _node_calc(payload: dict) -> dict:
    src = P._JS
    calc = src[src.index("// @@CALC"):src.index("// @@ENDCALC")]
    prog = ("const M = " + json.dumps(P.meta()) + ";\n" + calc +
            "\nconst inp = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
            "const out = inp.cases.map(c => gstats(c.rows, c.flag, c.L));\n"
            "const sp = inp.sp.map(p => spear(p[0], p[1]));\n"
            "process.stdout.write(JSON.stringify({g: out, sp: sp}));\n")
    r = subprocess.run(["node", "-e", prog], input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_browser_coupling_matches_python_group_stats():
    from arm.lab import heat as Hh
    from arm.lab import heatrel as R
    rnd = random.Random(21)
    n = 420
    wi = list(range(200)) + list(range(201, 421))                          # 中間缺一週：段數要在那裡斷開
    ret = [rnd.gauss(0.004, 0.03) for _ in range(n)]
    flags = [[False] * n for _ in range(3)]
    for a in (10, 80, 150, 196, 260, 330):
        for i in range(a, a + 7):
            flags[0][i] = True
            ret[i] += 0.03
    flags[1] = [rnd.random() < 0.3 for _ in range(n)]
    flags[2] = [i < 20 for i in range(n)]
    dates = [f"20{10 + i // 52:02d}-01-01" for i in range(n)]
    cases = [{"rows": [{"i": wi[k], "r": ret[k]} for k in range(n)], "flag": f, "L": 12} for f in flags]
    x = [rnd.gauss(0, 1) for _ in range(300)]
    y = [0.4 * v + rnd.gauss(0, 1) for v in x]
    x[5] = x[6]                                                             # 有同值
    out = _node_calc({"cases": cases, "sp": [[x, y]]})
    for f, g in zip(flags, out["g"]):
        p = R.group_stats(ret, f, dates, 12, wi)
        assert g["n"] == p["n"] and g["runs"] == p["runs"]
        for a, b in (("avg", "avg"), ("up", "up"), ("all", "all_avg"), ("diff", "diff"), ("d1", "d1"), ("d2", "d2")):
            assert (g[a] is None) == (p[b] is None) and (g[a] is None or abs(g[a] - p[b]) < 1e-12), a
        if p["lo"] is not None:                                             # 重抽亂數不同（瀏覽器 1,000 次）：區間要接近
            w = p["hi"] - p["lo"]
            assert abs(g["lo"] - p["lo"]) < 0.25 * w and abs(g["hi"] - p["hi"]) < 0.25 * w
    assert out["g"][0]["runs"] == 7 and out["g"][0]["v"] == "strong"            # 第 196～202 筆跨過缺的那週 → 斷成兩段
    assert out["g"][2]["v"] == "few"
    assert abs(out["sp"][0] - Hh.spearman(x, y)) < 1e-12


def test_week_change_and_source_dates(built):
    B, _, V, _ = built
    t, t0 = len(B["cal"]) - 1, len(B["cal"]) - 1 - P.WEEK
    keys = S.ITEMS["chip"]
    hn = {x: B["hc"][x][t] for x in keys}
    ha = {x: B["hc"][x][t0] for x in keys}
    it = next(i for i in V["dims"]["chip"]["items"] if i["k"] == "C1")
    assert abs(it["dpull"] - (H.contrib(hn, keys)["C1"]["pull"] - H.contrib(ha, keys)["C1"]["pull"])) < 1e-9
    t9 = next(i for i in V["dims"]["tech"]["items"] if i["k"] == "T9")
    assert t9["src"] < B["cal"][t]                                            # 美國資料晚一天才用
    b1 = next(i for i in V["dims"]["fund"]["items"] if i["k"] == "B1")
    assert len(b1["src"]) == 7                                                # 月資料標月份


def test_old_research_file_is_ignored(built):
    B, _, _, _ = built
    V = P.view(B, {"ver": 2, "lines": {}})
    assert V["R"] == {} and "驗證結果還沒產生" in P.render(V)


def test_entry_link_and_workflow_add_lines():
    from pathlib import Path
    from arm.lab import page
    assert '<a class="back" href="x9m.html">景氣</a>' in page._HTML           # 入口只在籌碼雷達頂欄
    root = Path(__file__).resolve().parents[1]
    assert "x9m" not in (root / "arm" / "fund_dashboard.py").read_text(encoding="utf-8")   # 主頁不加入口
    for wf in ("afterhours_refresh.yml", "daily.yml", "etf_holdings.yml"):
        t = (root / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9m.html 2>/dev/null || true") == 2, wf   # 一般與重試迴圈各一、分開 add
        assert t.count("git add -f dashboard/x9mh.json 2>/dev/null || true") == 2, wf  # 對照圖資料（第五版）
    assert "fetch_heat.py" in (root / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    assert "fetch_heat.py" in (root / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    assert "heatpage.build()" in (root / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")   # 和籌碼雷達分開建
