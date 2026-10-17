"""景氣溫度頁 x9m.html（arm/lab/heatpage.py）：用合成資料跑完整條管線（heatcalc → view → render）。"""
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
    D = {k: {} for k in C.FILES}
    p, mg, fx, h, i_, v = 15000.0, 2.5e11, 28.0, 80.0, 100.0, 18.0
    for d in cal:
        p *= 1 + rnd.gauss(0.0004, 0.011)
        mg *= 1 + rnd.gauss(0, 0.004)
        fx *= 1 + rnd.gauss(0, 0.002)
        h *= 1 + rnd.gauss(0.0001, 0.004)
        i_ *= 1 + rnd.gauss(0, 0.003)
        v = max(9.0, v * (1 + rnd.gauss(0, 0.05)))
        D["turnover"][d] = [3e11 * (1 + rnd.random()), round(p, 2)]
        D["margin"][d] = [mg, 1, 1]
        D["inst"][d] = {"total": rnd.gauss(0, 1e10), "Foreign_Investor": rnd.gauss(0, 8e9)}
        D["pcr"][d] = [1, 1, 80 + rnd.gauss(0, 15), 1, 1, 1]
        D["vix"][d] = v
        D["hyg"][d], D["ief"][d], D["usdtwd"][d] = h, i_, fx
        D["breadth"][d] = [rnd.randint(200, 800), rnd.randint(200, 800), rnd.randint(300, 900), 1000, rnd.randint(0, 60),
                           rnd.randint(0, 60), 1000]
        D["futi"][d] = {"TX": {"外資": [rnd.randint(5000, 30000), rnd.randint(5000, 60000)]},
                        "MTX": {"外資": [rnd.randint(1000, 9000), rnd.randint(1000, 9000)], "投信": [10, 20], "自營商": [30, 40]}}
        D["mtxoi"][d] = 40000 + rnd.randint(-5000, 5000)
        D["opti"][d] = {"買權": {"外資": [rnd.randint(1, 9) * 1e5, rnd.randint(1, 9) * 1e5]},
                        "賣權": {"外資": [rnd.randint(1, 9) * 1e5, rnd.randint(1, 9) * 1e5]}}
        D["effr"][d] = 2.0 + rnd.random()
        D["ust"][d] = [4.0, 4.2 + rnd.random() / 5, 4.4 + rnd.random() / 5]
    for d in cal[-60:]:
        D["vixtw"][d] = 20 + rnd.random()
    for k in range(400):
        ym = C.ym_add("1993-01", k)
        D["ndc"][ym] = [100.0, 100 + rnd.gauss(0, 2), 100.0, 100.0, 100.0, 100.0, float(rnd.randint(12, 40)), "綠"]
        D["orders"][ym] = 1000 + 10 * k + rnd.gauss(0, 50)
        D["money"][ym] = [1e6, rnd.gauss(5, 3), 2e6, rnd.gauss(5, 1)]
        D["twcpi"][ym] = [100.0, rnd.gauss(1.5, 1)]
        D["uscpi"][ym] = 150 * (1.002 ** k) * (1 + rnd.gauss(0, 0.002))
        if k > 230:
            D["pmi"][ym] = 50 + rnd.gauss(0, 4)
    for k in range(400):                                    # 長線的利率、利差要有 10 年以上
        ym = C.ym_add("1993-01", k)
        for dd in (5, 12, 19, 26, 27, 28, 29, 30, 2, 3, 4):
            D["effr"].setdefault(f"{ym}-{dd:02d}", 3.0 + (k % 40) / 20)
            D["ust"].setdefault(f"{ym}-{dd:02d}", [4.0, 4.0 + (k % 30) / 30, 4.5])
    return D


@pytest.fixture(scope="module")
def built():
    B = C.build(synthetic_D())
    R = {"lines": {}, "data": {"margin": [10, "2021-06-01", "2026-07-01"]}}
    for ln, L in S.LINES.items():
        keys = [k for k in S.KEYS if S.LINE_OF[k] == ln]
        inc = keys[:3] if ln != "fo" else []
        R["lines"][ln] = {"dir": -1, "inc": inc, "first": {k: B["cal"][0] for k in keys},
                          "items": {k: {str(h): {"verdict": "weak" if k in inc else "none", "dir": -1 if k in inc else 0,
                                                 "is": {"n": 900, "rho": -0.1, "lo": -0.2, "hi": -0.01, "a": "2014-01-02",
                                                        "bands": []},
                                                 "oos": {"n": 600, "rho": -0.05, "lo": -0.15, "hi": 0.05, "a": "2020-01-02",
                                                         "bands": []}} for h in L["fwd"]} for k in keys},
                          "comp": {str(h): {"verdict": "weak", "dir": -1, "is": {"n": 900, "bands": []},
                                            "oos": {"n": 600, "a": "2020-01-02",
                                                    "bands": [{"band": b, "n": 100, "avg": 0.5, "med": 0.4, "up": 55.0, "dd": -2.0}
                                                              for b in ("過冷", "偏冷", "中性", "偏熱", "過熱", "全部")]}}
                                   for h in L["fwd"]} if inc else None}
    V = P.view(B, R)
    return B, R, V, P.render(V)


def test_each_item_has_own_heat_and_pulls_sum_to_score(built):
    B, R, V, _ = built
    for ln in ("short", "mid", "long"):
        L = V["lines"][ln]
        assert L["score"] is not None and L["inc"]
        pulls = [it["pull"] for it in L["items"] if it["inc"] and it["pull"] is not None]
        assert abs(50 + sum(pulls) - L["score"]) < 1e-9                   # 拉動加起來＋50＝總分
        shares = [it["share"] for it in L["items"] if it["inc"] and it["share"] is not None]
        assert abs(sum(shares) - 100) < 1e-6
        for it in L["items"]:
            assert it["heat"] is None or 0 <= it["heat"] <= 100            # 每一項都有自己的 0～100
            assert it["inc"] or it["why"]                                   # 沒算進的寫原因
    assert V["lines"]["fo"]["score"] is None                               # 沒有指標通過 → 不給總分


def test_render_structure_and_wording(built):
    _, _, V, page = built
    for sec in ('id="c-short"', 'id="c-mid"', 'id="c-long"', 'id="c-fo"', 'id="trend"', 'id="detail"', 'id="valid"', 'id="src"'):
        assert sec in page
    assert page.count('class="it"') >= 9 and "拉動總分" in page and "佔比" in page and "本週" in page
    assert "沒算進總分" in page and "不給總分" in page
    assert 'href="x9.html"' in page and "<script" not in page                 # 純靜態頁
    for w in BANNED:
        assert w not in page, w
    assert P.render(V) == page                                                # 決定性


def test_week_change_and_source_dates(built):
    B, _, V, _ = built
    L = V["lines"]["short"]
    t, t0 = len(B["cal"]) - 1, len(B["cal"]) - 1 - P.WEEK
    k = L["inc"][0]
    hn = {x: B["heat"][x][t] for x in L["inc"]}
    ha = {x: B["heat"][x][t0] for x in L["inc"]}
    it = next(i for i in L["items"] if i["k"] == k)
    assert abs(it["dpull"] - (H.contrib(hn, L["inc"])[k]["pull"] - H.contrib(ha, L["inc"])[k]["pull"])) < 1e-9
    s5 = next(i for i in L["items"] if i["k"] == "S5")
    assert s5["src"] < B["cal"][t]                                            # 美國資料晚一天才用
    l1 = next(i for i in V["lines"]["long"]["items"] if i["k"] == "L1")
    assert len(l1["src"]) == 7                                                # 月資料標月份


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
