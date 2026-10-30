"""個股報告資料包（arm/lab/eqfacts.py）：季、年、月、估值區間、F12M、同業。用假資料逐項驗算。"""
import pytest

from arm.lab import eqfacts as E
from arm.lab import eqpage

QK = ["rev", "gp", "opex", "op", "nonop", "pti", "nip", "eps", "ca", "ta", "cl", "tl", "eqp", "bvps", "ocf", "icf", "cash"]


def _co(nq=12, ms=36):
    q = []
    qe = ["03-31", "06-30", "09-30", "12-31"]
    for i in range(nq):
        y, k = 2023 + i // 4, i % 4
        rev = 1000 + 100 * i
        q.append([f"{y}-{qe[k]}", rev, rev * 0.2, 50, rev * 0.1, 5, rev * 0.105, rev * 0.08, 1.0 + 0.1 * i,
                  500, 2000, 300, 800, 1200 + 10 * i, 50.0 + i, 200, -150, 400])
    mo = []
    for j in range(ms):
        y, m = 2023 + j // 12, j % 12 + 1
        mo.append([f"{y}-{m:02d}", 300 + 10 * j, 100 + j, 100000])
    return {"c": "9999", "n": "測試", "ind": "半導體業", "qk": QK, "q": q, "mo": mo,
            "ye": {"2023": 4.6, "2024": 5.0}, "dv": [["2024-07-01", 2.0, "息"], ["2025-07-01", 2.5, "息"]]}


def test_quarters_units_ratios_and_ttm():
    qs = E.quarters(_co())
    o = qs[-1]
    assert o["q"] == "2025-12-31" and o["rev"] == 21.0                       # 2,100 百萬 → 21 億
    assert o["gm"] == 20.0 and o["om"] == 10.0 and o["nm"] == 8.0
    assert o["rev_yoy"] == pytest.approx((2100 / 1700 - 1) * 100, abs=0.05)
    assert o["eps4"] == round(1.8 + 1.9 + 2.0 + 2.1, 2)
    assert o["fcf"] == 0.5 and o["dl"] == "2026-03-31"
    nip4 = sum(qs[j]["nip"] for j in range(8, 12))
    assert o["roe4"] == round(nip4 / ((qs[11]["eqp"] + qs[7]["eqp"]) / 2) * 100, 1)
    assert E.next_quarter("2025-12-31") == "2026-03-31" and E.deadline("2026-09-30") == "2026-11-14"


def test_annual_uses_reported_eps_and_dividends():
    ys = E.annual(E.quarters(_co()), {"2023": 4.6}, [["2024-07-01", 2.0, "息"]])
    assert [y["y"] for y in ys] == ["2023", "2024", "2025"]
    assert ys[0]["eps"] == 4.6                                                 # 年報全年數優先
    assert ys[1]["eps"] == round(1.4 + 1.5 + 1.6 + 1.7, 2) and ys[1]["dps"] == 2.0
    assert ys[1]["rev_yoy"] == pytest.approx((sum(1400 + 100 * k for k in range(4)) / sum(1000 + 100 * k for k in range(4)) - 1) * 100, abs=0.05)


def test_months_three_month_yoy():
    mo = E.months(_co())
    o = mo[-1]
    assert o["ym"] == "2025-12" and o["rev"] == round((300 + 350) / 100, 2)
    cur = sum(300 + 10 * j for j in (33, 34, 35))
    ly = sum(300 + 10 * j for j in (21, 22, 23))
    assert o["rev3"] == round(cur / 100, 2) and o["rev3_yoy"] == round((cur / ly - 1) * 100, 1)


def test_bands_only_use_reported_quarters():
    co = _co()
    qs, mo = E.quarters(co), E.months(co)
    b = E.bands(mo, qs, "2025-12")
    ser = dict(b["pe"]["ser"])
    # 2025-04 月底：已公布到 2024-12-31（3/31 期限），第一季（5/15）還沒有
    e4 = next(q["eps4"] for q in qs if q["q"] == "2024-12-31")
    assert ser["2025-04"] == round((100 + 27) / e4, 1)
    assert b["pe"]["n"] == len([v for v in ser.values() if v is not None])


def test_f12m_consensus_only():
    cons = {"n": 5, "eps": {"2026": {"med": 10.0}, "2027": {"med": 16.0}}}
    f = E.f12m_eps(cons, [], [], "2026-10-29")
    assert f["src"] == "cons" and f["eps"] == round(2 / 12 * 10 + 10 / 12 * 16, 2)
    co = _co()
    assert E.f12m_eps({"n": 2, "eps": {}}, E.months(co), E.quarters(co), "2026-01-05") == {"eps": None, "src": "none"}   # 不自己推估


def test_pick_peers_leaders_then_shared_then_size():
    cols = ["cap", "ii"]
    rows = {c: [cap, 0] for c, cap in {"A": 1000, "B": 900, "C": 100, "D": 110, "E": 95, "ME": 100, "F": 5000}.items()}
    nodes = [{"chain": "L", "cn": "鏈", "node": "L1", "nn": "細", "mem": ["ME", "A", "B", "C", "D", "E"]},
             {"chain": "L", "cn": "鏈", "node": "L2", "nn": "粗", "mem": ["ME", "E", "F", "A", "B", "C", "D", "X"]}]
    peers, how = E.pick_peers("ME", nodes, rows, cols, {})
    assert how == "產業鏈" and peers[:2] == ["A", "B"]                       # 最具體節點的兩家龍頭
    assert peers[2:] == ["C", "E", "D", "F"]                                  # 共同節點多的先，再看市值接近
    assert E.primary_chain(nodes) == "L"
    peers2, how2 = E.pick_peers("ME", [], rows, cols, {"ME": "半", "A": "半", "C": "半", "F": "半"})
    assert how2 == "證交所產業別" and set(peers2) == {"A", "C", "F"}


def test_numbers_collects_all():
    assert E.numbers({"a": 1, "b": [2.5, {"c": "3.0"}], "d": True}) == {1.0, 2.5, 3.0}


def test_implied_rest_of_year():
    co = _co(nq=11, ms=33)                       # 2025 只有前三季、月營收到 2025-09
    qs, mo = E.quarters(co), E.months(co)
    yd = E.ytd(qs, mo)
    yrs = E.annual(qs, {"2024": 5.0}, [])
    cons = {"y": 2025, "eps": {"2025": {"med": 9.0, "rev": 80.0}}}
    imp = E.implied(cons, yd, yrs, qs, mo)
    assert yd["q_n"] == 3 and yd["q_eps"] == round(1.8 + 1.9 + 2.0, 2)
    assert imp["eps_rest"] == round(9.0 - yd["q_eps"], 2)
    assert imp["eps_rest_ly"] == round(5.0 - yd["q_eps_ly"], 2)
    assert imp["rev_rest"] == round(80.0 - yd["m_rev"], 2)
    assert E.implied({}, yd, yrs, qs, mo) == {}


def test_valuation_uses_one_yardstick():
    """eqspec VER 2：共識法＝未來 12 個月 EPS × 同業未來本益比；同業有共識的不到 3 家或本公司沒有共識＝近四季 EPS × 近四季本益比。"""
    qs = [{"q": "2026-06-30", "eps4": 8.0, "bvps": 60.0}]
    bd = {"pe": {"p25": 10.0, "p50": 12.0, "p75": 14.0, "n": 60}, "pb": {"p25": 1.0, "p50": 1.2, "p75": 1.4, "n": 60}, "rows": []}
    peers = [{"pe": pe, "fpe": fpe, "pb": 3.0} for pe, fpe in ((30, 18), (40, 20), (50, 22), (60, None))]
    cons = {"eps": 10.0, "src": "cons"}
    v = E.valuation(cons, qs, bd, peers, 200.0, {}, "半導體業")
    assert v["basis"] == "fwd" and v["base"] == 10.0 and v["range"] == {"lo": 19.0, "hi": 21.0, "dflt": 20.0}
    assert v["tp_dflt"] == 200.0 and "同業未來 12 個月本益比" in v["range_how"]
    v2 = E.valuation({"eps": None, "src": "none"}, qs, bd, peers, 200.0, {}, "半導體業")
    assert v2["basis"] == "ttm" and v2["base"] == 8.0 and v2["range"] == {"lo": 10.0, "hi": 52.5, "dflt": (12 + 45) / 2}
    v3 = E.valuation(cons, qs, bd, peers[:2] + [{"pe": 50, "fpe": None, "pb": 3.0}], 200.0, {}, "半導體業")
    assert v3["basis"] == "ttm" and v3["base"] == 8.0                      # 同業有共識的只有 2 家 → 近四季法
    v4 = E.valuation(cons, qs, bd, peers, 200.0, {}, "金融保險")
    assert v4["method"] == "pb" and v4["base"] == 60.0


def test_pick_info_and_why_box_follow_the_strategy_only(tmp_path):
    """選股頁新飆股名單那一列（最後一欄＝現況）→ 報告的「為什麼在名單上」只寫這條策略自己的買法，
    不寫書上的位置與參考價位（docs/lab_pick_arch_plan.md；2026-10-30 前的報告說「照規則會買」又說「突破 659 才算」）。"""
    h = tmp_path / "x9.html"
    h.write_text('const D={"pick":{"tw":{"bx":{"d":"2026-10-29","fix":"2026-10-30","buyd":"2026-11-02","rows":'
                 '[["6870","騰雲",93,1,"符合：強度 93",397,"b"],["4958","臻鼎-KY",94,3,"符合：月營收創歷史新高",520,"w"]]}}}};',
                 encoding="utf-8")
    p = E.pick_info("4958", h)
    assert p["rank"] == 2 and p["weeks"] == 3 and not p["will_buy"] and not p["hold"] and "spot" not in p and "plan" not in p
    assert E.pick_info("6870", h)["will_buy"] and E.pick_info("0000", h) == {}
    w = eqpage.why_box({"pick": E.pick_info("6870", h), "mk": "tw"})
    assert "照規則 11/02 開盤買" in w and "不等買點" in w and "收盤試算" in w
    assert "格子滿了等空位" in eqpage.why_box({"pick": p, "mk": "tw"})
    old = {"list": "新飆股", "d": "2026-10-29", "fix": "2026-10-30", "buyd": "2026-11-02", "rank": 8, "rs": 94, "weeks": 3,
           "why": "符合：近 20 日漲停 1 次", "spot": "打底中", "plan": ["突破 659 才算", "52 週高點，還差 26.7%"], "will_buy": True}
    for x in (w, eqpage.why_box({"pick": old, "mk": "tw"})):                              # 舊的資料包重建也不再寫書上的買點
        for bad in ("突破", "才算", "等拉回", "還差", "位置：", "打底中"):
            assert bad not in x, bad
