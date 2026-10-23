"""景氣溫度頁 x9m.html（arm/lab/heatpage.py；第五版：熱度色帶頁首、對照台股互動圖、五個面向卡、邊際變化、關鍵價位與事件）：
用合成資料跑完整條管線（heatcalc → view → render）；（2026-10-20 前）瀏覽器端的交互分析用 node 和 Python 的 heatrel.group_stats 比對。"""
import html
import json
import random
from datetime import date, timedelta
from pathlib import Path

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


def m6_stub() -> dict:
    """第六版研究結果的合成樣本：大多看不出，M1B 累積 3 個月樣本內有、樣本外沒有；美國 CPI 15～18 個月後樣本內有（沒有做樣本外）；
    外資台指期樣本不足。"""
    def res(b=0.01, v="none", n=300):
        if b is None:
            return {"n": n, "a": "2023-09", "z": "2024-06", "b": None, "t": None, "lo": None, "hi": None, "p": None,
                    "h1": None, "h2": None, "q": None, "v": "few"}
        return {"n": n, "a": "1997-08", "z": "2024-01", "b": b, "t": 1.0, "lo": b - 0.02, "hi": b + 0.02, "p": 0.3,
                "h1": b, "h2": b, "q": 0.5, "v": v}

    def l1(b=0.01):
        return {"d": {f"{k},{S.M6_WIN}": res(b) for k in S.M6_DELAY}, "c": {f"0,{m}": res(b) for m in S.M6_CUM}}

    def oos(r2=-0.01, p=0.4, few=False):
        mm = {"m0": {"hit": 0.6}, "m1": {"hit": 0.55, "r2_0": -0.02, "terc": []}, "m2": {"hit": 0.56, "r2_0": -0.03, "r2_1": r2, "terc": []}}
        return {"n": 20 if few else 200, "a": "2008-01", "z": "2024-06", "few": few, "models": mm,
                "cw": {"m2>m1": {"t": 0.3, "p": p, "r2": r2}}}

    st = {s_: {"n": 80, "runs": 30, "avg": 0.05, "all": 0.06, "diff": -0.01, "lo": -0.05, "hi": 0.03, "d1": -0.01, "d2": 0.0,
               "verdict": "none", "yrs": ["2001"]} for s_ in ("hi_acc", "hi_dec", "lo_acc", "lo_dec")}
    ev = {"n": 10, "dates": [], "path": [0.01] * 24, "h": {str(h): {"n": 10, "diff": 0.01, "lo": -0.02, "hi": 0.03, "verdict": "few"}
                                                         for h in S.M6_STATE_H}}
    items = {}
    for k in S.DERIV:
        e = {"first": "1997-07", "x1": k in ("B1", "C1", "C5"), "l1": l1(), "l2": l1()["d"], "l3a": l1()["d"],
             "l3c": {"bull": l1()["d"], "hike": l1()["d"]}, "l3b": {str(h): st for h in S.M6_STATE_H},
             "oos": {f"{a},{b}": oos() for a, b in S.M6_OOS_WINDOWS},
             "l6": {"n": 40, "flat": 0, "base": [0.01] * 24, "kinds": {str(x): ev for x in (1, 2, 3, 4)}},
             "sum": {"react": [], "oos": "none"}}
        items[k] = e
    items["L2"]["l1"]["c"]["0,3"] = res(0.0529, "in_only")
    items["L2"]["sum"] = {"react": [["c", 0, 3, 1, "in_only"]], "oos": "fail"}
    items["L2"]["oos"]["0,3"] = oos(0.0017, 0.083)
    items["B8"]["l1"]["d"]["15,3"] = res(-0.0439, "in_untested")
    items["B8"]["sum"] = {"react": [["d", 15, 3, -1, "in_untested"]], "oos": "untested"}
    items["C5"]["l1"] = {"d": {w: res(None, n=40) for w in items["C5"]["l1"]["d"]}, "c": {w: res(None, n=40) for w in items["C5"]["l1"]["c"]}}
    items["C5"]["sum"] = {"react": [], "oos": "few"}
    groups = {g: {"first": "1997-07", "l1": l1(), "sum": {"react": [], "oos": "none"}}
              for g in ("GA_grow", "GA_rate", "GA_lev", "DI", "SH_grow", "SH_rate", "SH_lev")}
    groups["SH_rate"]["l1"]["d"]["15,3"] = res(-0.0333, "in_untested")
    groups["SH_rate"]["sum"] = {"react": [["d", 15, 3, -1, "in_untested"]], "oos": "untested"}
    prim = {h: {"n": 327, "b": -0.02, "lo": -0.1, "hi": 0.05, "p": 0.3, "holm": 0.6, "pass": False, "what": S.M6_PRIMARY[h][0]}
            for h in S.M6_PRIMARY}
    prim["H2"] = {"n": 327, "b": [-0.02, 0.0, -0.1], "w": 7.06, "p": 0.076, "holm": 0.306, "nw_p": 0.08, "pass": False,
                  "what": S.M6_PRIMARY["H2"][0], "states": {}}
    prim["H3"].update(n_dec=90, n_acc=77)
    g = {"n": 200, "a": "2008-01", "z": "2024-06", "few": False, "tree": None,
         "models": {"m0": {"hit": 0.6}, **{m: {"hit": 0.6, "r2_0": -0.01, "r2_1": -0.02, "terc": []} for m in ("m1", "m2", "m3", "ridge", "tree")}},
         "cw": {c: {"t": 0.1, "p": 0.5, "r2": -0.01} for c in ("m2>m1", "m3>m1", "m3>m2", "ridge>m1", "tree>m0")}}
    return {"ver": S.VER, "sample": {"a": "1997-07", "z": "2026-10", "T": 352, "oos_start": S.M6_OOS_START},
            "items": items, "groups": groups,
            "l4": {"inter": l1(), "states": {str(h): {s_: dict(st["hi_acc"]) for s_ in ("gA_rA", "gA_rD", "gD_rA", "gD_rD")}
                                             for h in S.M6_STATE_H}},
            "goos": {f"{a},{b}": g for a, b in S.M6_OOS_WINDOWS}, "primary": prim,
            "ext": {"a": "1982-01", "z": "2026-08", "T": 536, "l1": {"L2": l1()}, "H1": res(-0.0452), "H4": res(-0.0382)},
            "now": {}}


@pytest.fixture(scope="module")
def built():
    B = C.build(synthetic_D())
    R = research_stub(B)
    R["m6"] = m6_stub()
    V = P.view(B, R)
    return B, R, V, P.render(V)


def test_each_item_has_own_heat_and_pulls_sum_to_score(built):
    _, _, V, _ = built
    assert list(V["dims"]) == ["fund", "chip", "gliq", "tliq", "tech"]          # 泡沫面向另放泡沫頁（不在景氣頁顯示）
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
    assert '<a class="sr" href="#c-' not in page                                # 視覺化版面拿掉 52 週色帶，改成雷達（docs/lab_visual_plan.md）
    assert page.count('<template id="dt-') == len(P.shown_dims()) == 5                 # 每個面向一個右側面板（泡沫另放最下面）
    assert S.HORIZON_NOTE not in page                     # 「怎麼看」的說明拿掉（docs/lab_ia_v5_plan.md 第 8 節；每個面向看多久寫在面板裡）
    for d in P.shown_dims():
        st = V["strips"][d]
        assert len(st["cells"]) == min(S.STRIP_WEEKS, len(P.HP.week_ends(built[0]["cal"])))
        assert P.strip_text(st) in page                                       # 色帶旁的說明搬到面向面板
    assert V["summary"] and V["summary"] not in page                          # 頁首一列不寫句子（docs/lab_ia_v5_plan.md 第 3 節①）
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
    assert len(have_dv) >= 10 and page.count('<i class="idv" title="') == len(have_dv)   # 第六版：只留短標籤，數字放滑過的說明
    for k in have_dv:
        assert f'>邊際變化 {P.acc_label(k, V["dvn"][k])}</i>' in page
    assert '<i class="idv">邊際變化：' not in page                             # 第五版的長句不再出現在每一項下面
    dv = page[page.index('id="dv"'):page.index('id="valid"')]                   # 視覺化版面：邊際變化搬到研究畫面
    assert sum(dv.count(f'class="nmb" data-k="{k}"') for k in S.DERIV) == len(S.DERIV) == 13   # 核心 13 項（規劃時數錯寫成 14）
    for k in have_dv:
        assert html.escape(P.dv_line(k, V["dvn"][k])) in dv                   # 數字還在（滑過的說明）
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


def test_acc_label_and_counts():
    assert P.acc_label("B5", {"d2": 12.7, "streak": 3}) == "▲ 加速 3 個月"
    assert P.acc_label("C5", {"d2": -11317.0, "streak": 11}) == "▼ 減速 11 天"              # 日資料寫天
    assert P.acc_label("B1", {"d2": 0, "streak": 0}) == "持平" and P.acc_label("B1", None) == ""
    dvn = {k: {"d2": 1.0} for k in S.DERIV}
    dvn["C5"] = {"d2": -1.0}
    dvn["G2"] = None
    c = P.acc_counts(dvn)
    assert c["all"] == (11, 12) and c["lev"] == (1, 2) and c["rate"] == (3, 3) and c["grow"] == (7, 7)


def test_dv_section_v6_headline_conclusion_and_table(built):
    _, R, V, page = built
    dv = page[page.index('id="dv"'):page.index('id="valid"')]
    a, b = P.acc_counts(V["dvn"])["all"]
    assert f"{len(S.DERIV)} 項裡 {a} 項在加速" in dv
    for g in S.M6_GROUPS:                                                     # 三組都可以點到對照圖
        assert dv.count(f'class="nmb" data-k="A_{g}"') == 2                    # 一句話裡一次、表格裡一次
    assert '<table class="dvs stk">' in dv and "幾個月後有反應（加速時）" in dv and ">樣本外</th>" in dv
    assert dv.count('<tr><td class="l">') == len(S.DERIV) and dv.count('<tr class="grow">') == len(S.M6_GROUPS)
    assert "研究：</b>二階（加速度）在 1～24 個月看不出穩定的預測性：4 個主要假說都沒有通過（Holm 校正後 p 最小 0.31）" in dv
    assert f"比較接近的是 {P._iname('L2')}（累積 3 個月較強），但樣本外沒有成立" in dv   # 中英之間空一格
    assert f"只在樣本內看到、那段期間沒有做樣本外：{P._iname('B8')}（15～18 個月後較弱）" in dv
    m6 = json.loads(json.dumps(R["m6"]))                                      # 有預測性的時候先講有預測性
    m6["items"]["L2"]["sum"]["oos"] = "pred"
    m6["primary"]["H4"]["pass"] = True
    txt = P.m6_conclusion(m6)
    assert txt.startswith(f"有預測性：{S.M6_PRIMARY['H4'][0]}；{P._iname('L2')}（累積 3 個月較強）") and "看不出" not in txt
    row = lambda k: dv[dv.index(f'data-k="{k}"'):].split("</tr>")[0]          # noqa: E731
    assert "累積 3 個月較強" in row("L2") and ">不成立<" in row("L2")
    assert "15～18 個月後較弱" in row("B8") and ">沒有做<" in row("B8")
    assert "樣本不足" in row("C5") and "看不出" in row("B1")
    assert 'data-h="現在"' in dv and 'data-h="樣本外"' in dv                   # 手機上一項一塊
    V0 = P.view(built[0], {k: v for k, v in R.items() if k != "m6"})
    assert "多層回歸的結果還沒產生" in P._dv_section(V0)


def test_m6_validation_is_collapsed_with_all_layers(built):
    _, _, V, page = built
    val = page[page.index('id="valid"'):page.index('id="src"')]
    m6 = val[val.index('<details class="ovw" id="m6">'):]
    depth, i = 0, 0
    while True:                                                               # 對到外層的 </details>（裡面還有一層一層的 details）
        a, b = m6.find("<details", i), m6.find("</details>", i)
        if a != -1 and a < b:
            depth, i = depth + 1, a + 8
        else:
            depth, i = depth - 1, b + 10
            if depth == 0:
                break
    m6 = m6[:i]
    for t in ("主要假說", "L1 延遲反應", "L1 累積期間", "L2 扣掉水準", "L3a 水準 × 二階", "L3c 二階 × 環境（台股在 10 個月均線之上）",
              "L3c 二階 × 環境（聯準會 6 個月內升息）", "L4 景氣動能加速度 × 通膨利率加速度", "L3b 四個狀態", "L4 景氣動能 × 通膨利率四個狀態",
              "樣本外：單項", "樣本外：組與綜合模型", "L6 轉折事件", "延伸樣本", "第五版：每週樣本"):
        assert t in m6, t
    assert m6.count('<tr><td class="l">H') == len(S.M6_PRIMARY) and "沒有通過" in m6
    assert "<b>●</b>" in m6 and "<b>○</b>" in m6                             # M1B 樣本內有樣本外沒有、美國 CPI 沒有做樣本外
    assert m6.count('<details class="m6s">') >= 12                             # 每一層各自收起，標題列寫數一數的結果
    assert "個有結果：○ 2</span>" in m6 and "個有結果：● 1</span>" in m6      # 延遲：美國 CPI、通膨利率組；累積：M1B
    grp = m6[m6.index("L1 延遲反應"):]
    assert grp.index("景氣動能（組加速度）") < grp.index("通膨利率（組加速度）") < grp.index("籌碼（組加速度）") < grp.index("加速擴散")
    assert '<table class="m6t">' in m6 and "position:sticky" in page          # 寬表的第一欄固定
    assert "個有結果，重抽 p &lt; 0.05 的 0 個；H1 −4.52（p 0.30）；H4 −3.82（p 0.30）" in m6   # 延伸樣本沒有判定：標題列數 p 值
    assert '<table class="m6p stk">' in m6                                    # 主要假說表手機一項一塊
    assert P._m6_valid({"m6": {}}).startswith('<p class="warn">')


def test_chart_acc_lines_match_research_shares(built):
    from arm.lab import heatchart as HC
    from arm.lab import heatreg as G
    B, R, _, _ = built
    data = HC.build_data(B, R)
    for g in S.M6_GROUPS:
        sid = f"A_{g}"
        assert set(data["s"][sid]) == {"h", "hd"}                            # 只有 0～100，沒有原始值
        assert all(v is None or 0 <= v <= 100 for v in data["s"][sid]["h"]["v"])
    lines = HC.acc_lines(B)
    Pn = G.panel(B)
    n = 0
    for t, i in enumerate(Pn["me"]):
        for g in S.M6_GROUPS:
            sh = Pn["SH"][g][t]
            v = lines[f"A_{g}"][i]
            assert (sh is None) == (v is None)
            if sh is not None:
                assert abs(v - 50 * (sh + 1)) < 1e-9                         # 對照圖的組線＝研究的「幾成在加速」
                n += 1
    assert n > 50
    m6 = data["m6"]
    assert set(m6) == set(S.DERIV) | {f"A_{g}" for g in S.M6_GROUPS}
    assert m6["L2"]["txt"] == "累積 3 個月較強" and m6["B1"]["txt"] == ""
    assert [x[0] for x in m6["B1"]["d"]] == list(S.M6_DELAY) and [x[0] for x in m6["B1"]["c"]] == list(S.M6_CUM)
    assert m6["L2"]["c"][1][1] == 5.29 and m6["L2"]["oos"]["0,3"] == [200, 0.17, 0.083, False]
    assert HC.build_data(B, {**R, "ver": 5})["m6"] == {}                      # 舊版研究檔不用


def test_page_js_has_acc_lines_and_response_block():
    js = P._JS
    assert "const isAcc" in js and "const noRaw" in js and "function respBlock(" in js and "function rspPanel(" in js
    assert "h.textContent = '加速度'" in js                                  # 對照圖「＋ 細項」多一組三條線
    assert "!noRaw(st.sel[0].id)" in js and "isDim(st.sel[0].id)" not in js   # 組線沒有原始值
    assert "respBlock(id, W)" in js


def test_meta_matches_spec_and_is_embedded(built):
    _, _, V, page = built
    m = P.meta()
    a = page.index("<script>window.HEAT_META=") + len("<script>window.HEAT_META=")
    b = page.index(";</script>", a)
    assert json.loads(page[a:b].replace("<\\/", "</")) == json.loads(json.dumps(m))
    assert "</" not in page[a:b]                                              # 內嵌 JSON 不會提前結束 script
    assert "cpl" not in m and "hdef" not in m                                 # 交互分析 2026-10-20 拿掉（改成情境卡）
    assert m["max"] == S.CH_MAX == 5 and len(m["pal"]) == S.CH_MAX and m["rdef"] in m["ranges"]
    assert set(m["items"]) == set(S.KEYS) and [d["id"] for d in m["dims"]] == list(P.shown_dims())   # 泡沫另放泡沫頁
    assert [a["id"] for a in m["acc"]] == [f"A_{g}" for g in S.M6_GROUPS] and m["acc"][0]["name"] == "景氣動能加速度"
    assert m["m6"] == {"delay": list(S.M6_DELAY), "win": S.M6_WIN, "cum": list(S.M6_CUM), "minn": S.M6_MIN_N}
    assert page.count("<script>") == 4 and "x9mh.json" in page                 # HEAT_META、景氣頁程式、全部指標與泡沫的程式、<head> 的深淺色（appnav）；序列資料另外下載


def test_coupling_replaced_by_scenarios():
    """對照圖選多條線：原本瀏覽器算的交互分析拿掉（2026-10-20 使用者：「交互分析那邊超沒意義」），改成框出「所有情境」表裡用到這幾個面向的列（2026-10-20 起情境卡改成一張表）。"""
    js = P._JS
    for old in ("@@CALC", "function couple(", "function gstats(", "function consensus(", "function grid(", "M.cpl"):
        assert old not in js
    assert "function scenHint(box, ids)" in js and "#scen .sqr" in js and "#scen .sqi" not in js and "else scenHint(box, st.sel.map(x => x.id));" in js
    src = Path(P.__file__).read_text(encoding="utf-8")
    assert "<b>交互分析</b>" not in src and "<b>情境</b>" in src                 # 研究畫面的方法說明一起改


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
    assert "{{APPTAB}}" in page._HTML and "{{APPTAB}}" in P._HTML              # 兩頁共用頂欄（arm/lab/appnav.py）
    root = Path(__file__).resolve().parents[1]
    assert (root / "arm" / "fund_dashboard.py").read_text(encoding="utf-8").count('href="x9m.html"') == 1   # 主頁只有頁尾的「·」
    for wf in ("afterhours_refresh.yml", "daily.yml", "etf_holdings.yml"):
        t = (root / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert t.count("git add -f dashboard/x9m.html 2>/dev/null || true") == 2, wf   # 一般與重試迴圈各一、分開 add
        assert t.count("git add -f dashboard/x9mh.json 2>/dev/null || true") == 2, wf  # 對照圖資料（第五版）
    assert "fetch_heat.py" in (root / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    assert "fetch_heat.py" in (root / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    assert "heatpage.build()" in (root / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")   # 和籌碼雷達分開建


def test_bubble_dimension_moved_to_bubble_page(built):
    """泡沫面向從景氣頁拿掉（docs/lab_risk_plan.md 第 7 節）：卡片、色帶、雷達、地形、對照圖、證據地圖、驗證都不再有；
    頁面只留一行泡沫等級，連到泡沫頁。規格與研究檔照舊（heatspec VER 7）。"""
    B, R, V, page = built
    assert "bubl" in S.DIMS and "bubl" not in V["dims"] and "bubl" not in P.shown_dims()
    assert [d["id"] for d in V["meta"]["dims"]] == list(P.shown_dims()) and "bubl" not in V["meta"]["order"]
    assert set(V["strips"]) == set(P.shown_dims())
    for bad in ('id="c-bubl"', 'id="bubv"', 'data-tf="bubl"', 'id="e-bubl"', 'id="dt-bubl"', 'class="bubx"', 'class="refs"'):
        assert bad not in page, bad
    for k in S.ITEMS["bubl"]:
        assert f'<template id="it-{k}">' not in page
    from arm.lab import heatchart as HC
    data = HC.build_data(B, R)
    assert "bubl" not in data["s"] and not any(k in data["s"] for k in S.ITEMS["bubl"])
    V2 = dict(V, bubnow={"mk": "tw", "L": 3, "cond": ["P1", "P2"], "d": "2026-10-16"})
    # 面向那一塊的標題列有一格泡沫等級，連到最下面的泡沫（docs/lab_ia_v5_plan.md 第 3 節①、第 15.1 節）
    chip = '<a class="stc mfb" href="#bub" data-jump="bub" title="泡沫等級 3 泡沫警戒（價格爆發、兩年翻倍），點了看最下面的泡沫">'
    page2 = P.render(dict(V2, bubblock='<section class="cd mbub" id="bub">泡沫</section>'))
    assert chip in page2 and page2.index(chip) < page2.index('id="today"') < page2.index('id="bub"')   # 面向的標題列有一格，泡沫在最下面
    assert 'class="stc mfb"' not in P.render(dict(V2, bubblock=""))    # 泡沫那一塊沒有（算不出來）就不放這一格
    assert "x9b.html" not in page2
    for w in BANNED:
        assert w not in page2, w
