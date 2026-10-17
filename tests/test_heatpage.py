"""景氣溫度頁 x9m.html（arm/lab/heatpage.py；第三版四個面向）：用合成資料跑完整條管線（heatcalc → view → render）。"""
import random
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
        D["ust"][d] = [4.0, 4.2, u10]
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
        if ym >= "2012-01":
            a = 1e9 * (1 + rnd.random())
            D["rev"][ym] = [a, a / (1 + rnd.gauss(0.08, 0.1)), 1500]
    for d in _days(date(1993, 1, 4), 8600):                  # 聯邦基金利率：每天一筆，取當月平均
        D["effr"][d] = 3.0 + (int(d[:4]) * 12 + int(d[5:7])) % 40 / 20
    return D


def research_stub(B):
    R = {"ver": S.VER, "dims": {}, "data": {"margin": [10, "2021-06-01", "2026-07-01"]}}
    bands = [{"band": b, "n": 100, "avg": 0.5, "med": 0.4, "up": 55.0, "dd": -2.0}
             for b in ("過冷", "偏冷", "中性", "偏熱", "過熱", "全部")]

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
    assert list(V["dims"]) == ["fund", "chip", "liq", "tech"]
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
    for sec in ('id="c-fund"', 'id="c-chip"', 'id="c-liq"', 'id="c-tech"', 'id="trend"', 'id="detail"', 'id="valid"',
                'id="src"'):
        assert sec in page
    assert page.count('class="tile"') == 4 and S.HORIZON_NOTE in page
    assert page.count('class="it"') >= 25 and "拉動分數" in page and "佔比" in page and "本週" in page
    assert "用美國 VIX 的排名代替，不算進分數" in page and "前一半" in page and "後一半" in page
    assert "熱＝散戶擁擠、槓桿高、外資站在對面" in page
    assert 'href="x9.html"' in page and "<script" not in page                 # 純靜態頁
    for w in BANNED:
        assert w not in page, w
    assert P.render(V) == page                                                # 決定性


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
    assert "fetch_heat.py" in (root / ".github" / "workflows" / "afterhours_refresh.yml").read_text(encoding="utf-8")
    assert "fetch_heat.py" in (root / "scripts" / "daily_fund.sh").read_text(encoding="utf-8")
    assert "heatpage.build()" in (root / "scripts" / "gen_fund_dashboard.py").read_text(encoding="utf-8")   # 和籌碼雷達分開建
