"""交易計畫卡片（arm/lab/corepage.py；docs/lab_core70_plan.md 第 10 節）：版面結構、數字跟研究檔一致、
沒有內部術語與禁用詞、class 一律 pln 開頭、訊號總覽・研究結論怎麼接。"""
import json
import re

import pytest

from arm.lab import core as CO
from arm.lab import corepage as P
from arm.lab import corespec as S
from arm.lab import sigpage as SG

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買", "建議賣", "目標價", "零風險", "無風險")
JARGON = ("VER", "候選", "門檻", "夏普", "前後兩半", "信賴", "區間", "扣掉波動", "BH", "固定持有", "樣本外", "corespec")   # 平均拿 95% 是部位、不是信賴區間


def _fams(inf=76.7, lev=88.2, pct=15.0):
    return [{"k": "inf", "name": "通膨", "desc": "美國 CPI 年增率", "lit": inf >= S.HOT, "v": inf, "vd": "2026-10-22",
             "item": "B8", "stale": None, "src": "2026-09"},
            {"k": "lev", "name": "槓桿", "desc": "融資 ÷ 上市市值", "lit": lev >= S.HOT, "v": lev, "vd": "2026-10-22", "item": "W2",
             "stale": None},
            {"k": "trend", "name": "趨勢", "desc": "加權指數 vs 年線", "lit": pct < 0, "px": 23000.0, "ma": 23000.0 / (1 + pct / 100),
             "pct": pct, "trig": 20010.5}]


def _now(n_lit_extra=False, held=True):
    f = _fams(inf=82.0 if n_lit_extra else 76.7)
    n = sum(x["lit"] for x in f)
    on = n < S.NEED
    sat = 1.0 if held else 0.0
    return {"mk": "tw", "d": "2026-10-22", "fams": f, "n": n, "on": on, "now": S.CORE + S.SAT * sat,
            "next": S.CORE + S.SAT * (1.0 if on else 0.0), "due": (sat > 0.5) != on}


STK = {"d": "2026-10-23", "w": 0.10,
       "st": [{"k": "v3l", "name": "財報驚喜（大型股）", "kind": "per"}, {"k": "s3", "name": "臺灣50 提前卡位", "kind": "event"},
              {"k": "s5", "name": "長線投信動能", "kind": "trade"}],
       "hold": {"v3l": [{"c": "2330", "n": "台積電", "ent": "2026-08-17", "out": "2026-11-12", "r": 3.1}], "s3": [], "s5": []},
       "ev": [{"d": "2026-11-12", "at": "收盤", "act": "賣出", "k": "v3l", "sname": "財報驚喜（大型股）", "held": True,
               "ent": "2026-08-17", "items": [{"c": "2330", "n": "台積電"}], "n_items": 1},
              {"d": "2026-11-17", "at": "開盤", "act": "買進", "k": "v3l", "sname": "財報驚喜（大型股）", "pending": True,
               "fix": "2026-11-16", "items": [], "n_items": 0}]}


def _text(h: str) -> str:
    h = re.sub(r"<style.*?</style>|<script.*?</script>", "", h, flags=re.S)
    h = re.sub(r'\s(?:title|aria-label|class|id|style|viewBox|d|data-[a-z]+)="[^"]*"', "", h)
    return re.sub(r"<[^>]+>", " ", h)


@pytest.fixture(scope="module")
def R():
    R = CO.load()
    assert R is not None, "研究檔 data/lab/core_research.json 要先跑 scripts/run_core.py"
    return R


def test_card_sections_and_numbers_match_research(R):
    h = P.card("tw", _now(), R, STK, {"n": 0, "next": S.CHECKS[0]})
    assert 'id="pln-tw"' in h and "前瞻驗證中" in h
    order = [h.index(x) for x in ('class="plnnow"', "接下來要做的事", "每天收盤看", "好處", "可以期待的報酬與風險", "細節")]
    assert order == sorted(order)                                                 # 照示意圖的順序
    sc = R["mk"]["tw"]["sc"]
    p, hd = sc["plan"]["plan"], sc["plan"]["hold"]
    assert P._wan(p["m"]) in h and P._wan(hd["m"]) in h and P._ab(p["mdd"]) in h   # 好處＝照計畫（衛星放策略）
    assert P._wan(sc["rule"]["plan"]["m"]) in h                                   # 規則本身另列一行
    for q in p["q"]:
        assert P._pc(q) in h                                                       # 往後 12 個月的三個百分位
    w, n = P._wins(p, hd)
    assert f"{w}／{n} 年" in h
    assert h.count("<tr><td") >= len(sc["plan"]["eps"])                          # 每一次換成現金都列出來
    assert "財報驚喜（大型股）、臺灣50 提前卡位、長線投信動能，各 10%" in h
    assert "11/12" in h and "賣掉 8/17 買的 1 檔（台積電）" in h and "買新名單（11/16 收盤產生）" in h


def test_card_has_no_jargon_or_banned_words_and_classes_are_prefixed(R):
    for mk in S.MARKETS:
        N = dict(_now(), mk=mk)
        h = P.card(mk, N, R, STK if mk == "tw" else None, {"n": 3, "next": S.CHECKS[0]})
        t = _text(h)
        for w in BANNED + JARGON:
            assert w not in t, (mk, w)
        cls = {c for a in re.findall(r'class="([^"]+)"', h) for c in a.split()}
        assert cls and all(c.startswith("pln") for c in cls), cls
    assert "保證金" not in P.CSS and "保證" not in _text(P.card("tw", _now(), R, STK))


def test_card_states_hold_cash_and_due(R):
    from arm.lab.xstrat import future_days
    nxt = future_days("tw", "2026-10-22", 1)[0]
    h = P.card("tw", _now(n_lit_extra=True, held=True), R, STK)                   # 兩種亮了、衛星還拿著 → 下一個交易日收盤換現金
    assert "70%" in h and "把衛星 30% 全部賣掉、換成現金" in h and P._mdw(nxt) in h and "衛星 30% 現金" in h
    assert "今天收盤前 100%" in h
    h = P.card("tw", _now(n_lit_extra=False, held=False), R, STK)                 # 少於兩種、衛星在現金 → 買回
    assert "把衛星 30% 買回" in h and "100%" in h
    h = P.card("tw", _now(), R, STK)                                              # 一種亮、拿滿、沒事
    assert "再亮一種就換現金" in h and "換成現金</b>" not in h
    h = P.card("tw", None, R, STK)
    assert "今天的讀數還沒算" in h and "好處" in h
    assert "plnoff" in P.card("ixic", None, R) and "plnoff" in P.card("sox", None, R)


def test_us_card_says_satellite_is_index_and_shows_early_period(R):
    for mk in ("spx", "ndx"):
        N = dict(_now(), mk=mk)
        N["fams"] = [dict(f, desc=d) for f, (_, _, d, _, _) in zip(N["fams"], S.FAMS[mk])]
        h = P.card(mk, N, R)
        e = R["mk"][mk]["sc"]["early"]
        assert "衛星 30% 現在也放同一個指數" in h and P._wan(e["plan"]["m"]) in h
        assert "財報驚喜" not in h and "個股策略頁" not in h and "融資 ÷ 上市市值" not in h          # 台股衛星與台股槓桿的說法不出現在美股


def test_chart_draws_both_lines_and_cash_spans(R):
    C = R["mk"]["tw"]["sc"]["rule"]["chart"]
    svg = P.chart(C, 640, 210, 11, "dsk")
    assert svg.count('class="plncash"') == len(C["cash"]) and 'class="plnpp"' in svg and 'class="plnhl"' in svg
    assert P.chart({"pts": [["2020-01-02", 1.0, 1.0]]}, 640, 210, 11, "dsk") == ""


def test_other_pages_css_has_no_pln_selectors():
    from arm.lab import appnav, bottompage, crashpage, findings, heatpage, heatviz, hotchpage, hotddpage, practpage
    for css in (heatpage._CSS, appnav.CSS, heatviz.CSS, crashpage.CSS, hotddpage.CSS, hotchpage.CSS, bottompage.CSS, SG.CSS,
                practpage.CSS, findings.CSS):
        assert ".pln" not in css


def test_research_html_puts_plan_card_on_top_of_each_market(R):
    V = {"rmk": [], "pr": {}, "find": {"tw": {}, "spx": {}},
         "core": {"R": R, "now": {"tw": _now()}, "stk": STK, "fw": {"tw": {"n": 0, "next": 63}}}}
    h = SG.research_html(V)
    tw = h[h.index('data-mk="tw"'):h.index('data-mk="spx"')]
    assert tw.index('id="pln-tw"') < tw.index('class="rfnow')
    spx = h[h.index('data-mk="spx"'):]
    assert 'id="pln-spx"' in spx and "今天的讀數還沒算" in spx                    # 沒有讀數也列過去的成績
    import inspect
    assert "CPG.CSS" in inspect.getsource(SG.render)                              # 卡片的樣式跟著訊號總覽一起載入


def test_card_json_keeps_core_and_stk_and_core_data_reads_them_back(tmp_path, monkeypatch):
    N = _now()
    txt = SG.card_json("tw", {"d": "2026-10-22", "core": N}, STK)
    J = json.loads(txt)
    assert J["core"] == N and J["stk"] == STK
    assert "stk" not in json.loads(SG.card_json("spx", {"d": "2026-10-21", "core": dict(N, mk="spx")}))
    (tmp_path / "x9or-tw.json").write_text(txt, encoding="utf-8")
    monkeypatch.setattr(SG, "CARDS", {})
    monkeypatch.setattr(CO, "STK", {})
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setattr(CO, "LIVE", tmp_path / "core_live.json")
    X = SG.core_data(tmp_path)
    assert X["now"] == {"tw": N} and X["stk"] == STK and not (tmp_path / "core_live.json").exists()
    assert set(X["fw"]) == set(S.MARKETS)


def test_sat_weights_split_like_the_backtest():
    """衛星現在拿著什麼：定期換股＝那一份平分給每一期的名單、名單內平分；其他＝每一檔那一份 ÷ SLOTS；剩下的放大盤。"""
    stk = {"st": [{"k": "v3l", "name": "財報驚喜（大型股）", "kind": "per"}, {"k": "s3", "name": "臺灣50 提前卡位", "kind": "rev"},
                  {"k": "s5", "name": "長線", "kind": "trade"}],
           "hold": {"v3l": [{"c": "2330", "n": "台積電", "ent": "2026-08-17"}, {"c": "2303", "n": "聯電", "ent": "2026-08-17"},
                            {"c": "2454", "n": "聯發科", "ent": "2026-10-01"}],
                    "s3": [{"c": "3189", "n": "景碩", "ent": "2026-10-19"}], "s5": []}}
    W = {x["k"]: x for x in P.sat_weights(stk)}
    assert [round(r["w"], 6) for r in W["v3l"]["rows"]] == [0.025, 0.025, 0.05] and W["v3l"]["idle"] == pytest.approx(0)
    assert W["s3"]["rows"][0]["w"] == pytest.approx(S.SAT / 3 / S.SLOTS["s3"]) and W["s3"]["idle"] == pytest.approx(0.075)
    assert W["s5"]["rows"] == [] and W["s5"]["idle"] == pytest.approx(0.10)
    assert sum(sum(r["w"] for r in x["rows"]) + x["idle"] for x in W.values()) == pytest.approx(S.SAT)
    h = P.card("tw", _now(), CO.load(), dict(STK, **stk))
    assert "衛星現在拿著（占全部資金）" in h and "台積電 2.5%" in h and "聯發科 5%" in h and "景碩 2.5%；大盤 7.5%" in h and "大盤 10%" in h
    h = P.card("tw", _now(held=False), CO.load(), dict(STK, **stk))
    assert "衛星現在是現金；買回時照下面這樣買" in h


def test_trend_gauge_fills_toward_the_line():
    """三條長條同一個意思：越長越接近亮。趨勢的直線在一半（年線），比年線高 20% 以上是空的。"""
    def fill(pct):
        N = _now()
        N["fams"][2].update(pct=pct, lit=pct < 0)
        h = P._fam_html("tw", N)
        return float(re.findall(r'<i class="[^"]*" style="width:([0-9.]+)%"></i><b style="left:50%">', h)[0])
    assert fill(25.0) == 0.0 and fill(14.1) == pytest.approx(14.75, abs=0.06) and fill(0.0) == 50.0 and fill(-30.0) == 100.0

