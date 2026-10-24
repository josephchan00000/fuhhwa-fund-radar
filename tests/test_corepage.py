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
# 2026-10-23 使用者：「白話文一點不要那麼AI」——頁面不說核心／衛星／三種過熱／亮／前瞻，也不用箭頭
NOT_PLAIN = ("衛星", "核心", "三種過熱", "亮", "前瞻", "→")


def _fams(inf=76.7, lev=88.2, pct=15.0):
    return [{"k": "inf", "name": "通膨", "desc": "美國 CPI 年增率", "lit": inf >= S.HOT, "v": inf, "vd": "2026-10-22",
             "item": "B8", "stale": None, "src": "2026-09"},
            {"k": "lev", "name": "槓桿", "desc": "融資 ÷ 上市市值", "lit": lev >= S.HOT, "v": lev, "vd": "2026-10-22", "item": "W2",
             "stale": None},
            {"k": "trend", "name": "趨勢", "desc": "加權指數 vs 年線", "lit": pct < 0, "px": 23000.0, "ma": 23000.0 / (1 + pct / 100),
             "pct": pct, "trig": 20010.5}]


def _now(n_lit_extra=False, held=True, mk="tw"):
    f = _fams(inf=82.0 if n_lit_extra else 76.7)
    n = sum(x["lit"] for x in f)
    on = n < S.NEED
    sat = 1.0 if held else 0.0
    c, w = S.core_of(mk), S.sat_of(mk)                                          # corespec VER 4：長抱的比例照市場
    return {"mk": mk, "d": "2026-10-22", "fams": f, "n": n, "on": on, "now": c + w * sat,
            "next": c + w * (1.0 if on else 0.0), "due": (sat > 0.5) != on,
            "ok": on, "clear": 30 if on else 0, "need": S.REENTRY.get(mk, 1)}


def _us(mk="spx", held=("10 個月均線", "200 日均線", "12 個月動能"), flat=False):
    N = dict(_now(mk=mk), mk=mk, need=1)
    N["fams"] = [dict(f, desc=d) for f, (_, _, d, _, _) in zip(N["fams"], S.FAMS[mk])] + [
        {"k": "flat", "name": "總經策略全部空手", "desc": "", "lit": flat, "held": list(held), "n_all": 12, "vd": "2026-10-22"}]
    if flat:
        N.update(on=False, ok=False, clear=0, next=S.core_of(mk), due=True)
    return N


BOOM = {"book": "R60", "start": "2026-10-23", "d": "2026-11-06", "next": "2026-11-09", "next_wk": "2026-11-13", "wk_today": True,
        "wk": "2026-11-06", "n_list": 3, "cash": 0.25, "hold_n": 60, "w": 0.125, "trial": [],
        "list": [{"c": "2368", "n": "金像電", "rs": 95.0}, {"c": "6274", "n": "台燿", "rs": 90.0}, {"c": "3017", "n": "奇鋐", "rs": 88.0}],
        "hold": [{"c": "3017", "n": "奇鋐", "ent": "2026-11-02", "sig": "2026-10-30", "epx": 1000.0, "px": 1100.0, "r": 0.10,
                  "w": 0.5, "due": "2027-02-02", "out": "2027-02-03", "sell": False},
                 {"c": "2383", "n": "台光電", "ent": "2026-11-02", "sig": "2026-10-30", "epx": 900.0, "px": 870.0, "r": -0.033,
                  "w": 0.25, "due": "2026-11-20", "out": "2026-11-23", "sell": False}],
        "sell": [], "buy": [{"c": "2368", "n": "金像電", "rs": 95.0, "fill": True}, {"c": "6274", "n": "台燿", "rs": 90.0, "fill": False}],
        "n_buy": 1}
STK = {"d": "2026-10-23", "w": 0.8 * 0.5 / 3, "bw": 0.4, "boom": BOOM,
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
    assert 'id="pln-tw"' in h and "上線觀察中" in h
    order = [h.index(x) for x in ('class="plnnow"', "接下來要做的事", "每天收盤後", "過去照做的結果", "照做一年會怎樣", "細節")]
    assert order == sorted(order)                                                 # 照示意圖的順序
    sc = R["mk"]["tw"]["sc"]
    p, hd = sc["plan"]["plan"], sc["plan"]["hold"]
    assert P._wan(p["m"]) in h and P._wan(hd["m"]) in h and P._ab(p["mdd"]) in h   # 好處＝照計畫（衛星放策略）
    assert P._wan(sc["rule"]["plan"]["m"]) in h and P._wan(sc["long"]["plan"]["m"]) in h   # 規則本身、機動只放個股策略另列
    for q in p["q"]:
        assert P._pc(q) in h                                                       # 往後 12 個月的三個百分位
    w, n = P._wins(p, hd)
    assert f"{w}／{n} 年" in h
    assert h.count("<tr><td") >= len(sc["plan"]["eps"])                          # 每一次換成現金都列出來
    assert "交易計畫：兩成長抱，八成機動" in h and "兩成買大盤 ETF" in h
    assert "一半（40%）照<b>新飆股</b>每週五收盤的名單買（每檔約占全部資金 5%，抱 60 個交易日）" in h
    assert "另一半分給 3 條個股策略（每條約 13.3%）：財報驚喜（大型股）、臺灣50 提前卡位、長線投信動能。" in h
    assert "11/12" in h and "賣掉 8/17 買的 1 檔（台積電）" in h and "買新名單（11/16 收盤產生）" in h
    # 新飆股：現在拿著的（占全部資金＝那本帳的比重 × 40%）、明天開盤要買的、到期要賣的、下一次看名單
    assert "奇鋐 20%、台光電 10%；現金 10%" in h
    assert "<b>新飆股</b> 買進 金像電" in h and "名單後面還有 1 檔現金不夠" in h and "11/9（一）" in h
    assert "<b>新飆股</b> 賣掉 台光電" in h and "11/2 買的，11/20 收盤滿 60 個交易日" in h
    assert "看新飆股這一週的名單" in h and "11/13（五）" in h


def test_card_has_no_jargon_or_banned_words_and_classes_are_prefixed(R):
    for mk in S.MARKETS:
        N = dict(_now(), mk=mk)
        h = P.card(mk, N, R, STK if mk == "tw" else None, {"n": 3, "next": S.CHECKS[0]})
        t = _text(h)
        for w in BANNED + JARGON + NOT_PLAIN:
            assert w not in t, (mk, w)
        cls = {c for a in re.findall(r'class="([^"]+)"', h) for c in a.split()}
        assert cls and all(c.startswith("pln") for c in cls), cls
    assert "保證金" not in P.CSS and "保證" not in _text(P.card("tw", _now(), R, STK))


def test_card_states_hold_cash_and_due(R):
    from arm.lab.xstrat import future_days
    nxt = future_days("tw", "2026-10-22", 1)[0]
    h = P.card("tw", _now(n_lit_extra=True, held=True), R, STK)                   # 兩種亮了、機動還拿著 → 下一個交易日收盤換現金
    assert "20%" in h and "把機動的八成賣掉，改放現金" in h and "之後只留兩成" in h and P._mdw(nxt) in h and "機動 80% 放現金" in h
    sw = P.stock_w("tw", _now(n_lit_extra=True, held=True), STK)                 # 股票占全部資金：長抱＋機動裡有股票的（空位放現金）
    assert sw == pytest.approx((0.2 + 0.2 + 0.1 + 0.8 * 0.5 / 3, 0.2))            # 奇鋐 20%、台光電 10%、台積電 13.3%
    assert f"現在手上 {P.pct0(sw[0])}" in h and "現在手上 63%" in h and f"{P._mdw(nxt)} 收盤調整之後的股票比例" in h
    h = P.card("tw", _now(n_lit_extra=False, held=False), R, STK)                 # 少於兩種、機動在現金 → 買回
    assert "把機動的八成買回來" in h and "63%" in h and "照各策略和新飆股當時該有的股票買" in h
    h = P.card("tw", _now(), R, STK)                                              # 一種亮、拿滿、沒事
    assert "再多一個就要賣掉機動的八成" in h and "改放現金</b>" not in h
    h = P.card("tw", None, R, STK)
    assert "今天的分數還沒算出來" in h and "過去照做的結果" in h
    assert "plnoff" in P.card("ixic", None, R) and "plnoff" in P.card("sox", None, R)


def test_us_card_says_satellite_is_index_and_shows_early_period(R):
    for mk in ("spx", "ndx"):
        N = _us(mk)
        h = P.card(mk, N, R)
        e = R["mk"][mk]["sc"]["early"]
        assert "交易計畫：全部機動" in h and "不留一直抱著的部分，全部買" in h and "有警訊時整個帳戶換成現金" in h
        assert P._wan(e["plan"]["m"]) in h
        assert "財報驚喜" not in h and "個股策略頁" not in h and "融資 ÷ 上市股票總市值" not in h and "融資偏多" not in h          # 台股衛星與台股槓桿的說法不出現在美股


def test_v2_us_fourth_warning_and_tw_two_week_buy_back(R):
    """VER 2：美股多一列「總經策略全部空手」（單獨就換現金）；台股換現金後要警訊少於兩個滿 10 個交易日才買回。"""
    from arm.lab.xstrat import future_days
    h = P.card("spx", _us(), R)
    t = _text(h)
    assert "看四個警訊" in t and "或總經策略全部空手" in t and "總經策略全部空手" in t
    assert "3 條有部位" in t and "有部位的：10 個月均線、200 日均線、12 個月動能" in t
    assert "只拿" not in t.split("每天收盤後")[1].split("過去照做的結果")[0]          # 沒有觸發
    h = P.card("spx", _us(held=(), flat=True), R)
    t = _text(h)
    assert "全部空手（警訊）" in t and "總經策略全部空手， 全部放現金" in t and "把全部持股賣掉，改放現金" in t
    assert "整個帳戶都是現金" in t
    t = _text(P.card("spx", _us(held=("200 日均線",)), R))
    assert "1 條有部位" in t and "有部位的：200 日均線" in t
    th = _text(P.card("tw", _now(), R, STK))
    assert "看三個警訊" in th and "滿 10 個交易日（約兩週）" in th and "總經策略全部空手" not in th
    N = _now(n_lit_extra=False, held=False)                                     # 台股：機動是現金、警訊少於兩個第 4 天
    N.update(on=False, ok=True, clear=4, next=S.core_of("tw"), now=S.core_of("tw"), due=False)
    t = _text(P.card("tw", N, R, STK))
    buy = future_days("tw", "2026-10-22", S.REENTRY["tw"] - 4 + 1)[-1]
    assert "警訊已經少於兩個（第 4 天），要滿 10 個交易日才買回" in t and f"最快 {P._mdw(buy)} 收盤買回" in t
    assert "機動的八成還在等買回（警訊少於兩個第 4 天，要滿 10 天）" in t and "現在拿  20%" in t


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
    assert 'id="pln-spx"' in spx and "今天的分數還沒算出來" in spx                    # 沒有讀數也列過去的成績
    import inspect
    assert "CPG.CSS" in inspect.getsource(SG.research_css)                        # 卡片的樣式跟著研究紀錄頁的訊號研究一起載入


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
    """★ 策略那一半現在拿著什麼：定期換股＝那一份平分給每一期的名單、名單內平分；其他＝每一檔那一份 ÷ SLOTS；剩下的放現金（VER 4）。"""
    stk = {"st": [{"k": "v3l", "name": "財報驚喜（大型股）", "kind": "per"}, {"k": "s3", "name": "臺灣50 提前卡位", "kind": "rev"},
                  {"k": "s5", "name": "長線", "kind": "trade"}],
           "hold": {"v3l": [{"c": "2330", "n": "台積電", "ent": "2026-08-17"}, {"c": "2303", "n": "聯電", "ent": "2026-08-17"},
                            {"c": "2454", "n": "聯發科", "ent": "2026-10-01"}],
                    "s3": [{"c": "3189", "n": "景碩", "ent": "2026-10-19"}], "s5": []}}
    W = {x["k"]: x for x in P.sat_weights(stk)}
    sh = S.sat_of("tw") * (1 - S.BOOM_SHARE["tw"]) / 3                          # ★ 那一半（40%）平分給 3 條
    assert [round(r["w"], 6) for r in W["v3l"]["rows"]] == [round(sh / 4, 6), round(sh / 4, 6), round(sh / 2, 6)]
    assert W["v3l"]["idle"] == pytest.approx(0)
    assert W["s3"]["rows"][0]["w"] == pytest.approx(sh / S.SLOTS["s3"]) and W["s3"]["idle"] == pytest.approx(sh * 3 / 4)
    assert W["s5"]["rows"] == [] and W["s5"]["idle"] == pytest.approx(sh)
    assert sum(sum(r["w"] for r in x["rows"]) + x["idle"] for x in W.values()) == pytest.approx(0.40)
    h = P.card("tw", _now(), CO.load(), dict(STK, **stk))
    assert "機動現在買了這些（占全部資金）" in h and "台積電 3.3%" in h and "聯發科 6.7%" in h and "景碩 3.3%；現金 10%" in h
    assert "現金 13.3%" in h and "大盤" not in h.split("機動現在買了這些")[1].split("</div></div>")[0]
    h = P.card("tw", _now(held=False), CO.load(), dict(STK, **stk))
    assert "機動的八成現在放現金；買回時照這樣買" in h
    B = P.boom_rows(STK)                                                          # 新飆股那一半：那本帳的比重 × 40%，剩下的是現金
    assert [r["c"] for r in B] == ["3017", "2383", None] and [round(r["w"], 6) for r in B] == [0.2, 0.1, 0.1]


def test_trend_gauge_fills_toward_the_line():
    """三條長條同一個意思：越長越接近亮。趨勢的直線在一半（年線），比年線高 20% 以上是空的。"""
    def fill(pct):
        N = _now()
        N["fams"][2].update(pct=pct, lit=pct < 0)
        h = P._fam_html("tw", N)
        return float(re.findall(r'<i class="[^"]*" style="width:([0-9.]+)%"></i><b style="left:50%">', h)[0])
    assert fill(25.0) == 0.0 and fill(14.1) == pytest.approx(14.75, abs=0.06) and fill(0.0) == 50.0 and fill(-30.0) == 100.0



# ── corespec VER 3：美股三成換成「美股強勢品質股」（ussxspec QM；docs/lab_us_sleeve_plan.md 第 13 節）──────────

@pytest.fixture(scope="module")
def QMX():
    from arm.lab import ussxqm as QM
    R = QM.load()
    assert R is not None, "研究檔 data/lab/ussx_qm.json 要先跑 scripts/run_ussx.py --qm"
    L = QM.load_live()
    assert (L.get("now") or {}).get("hold"), "每週紀錄 data/lab/ussx_qm_live.json 要有最新的持股"
    R = json.loads(json.dumps(R))
    R["switch"] = {"spx": True, "ndx": True}                                      # 這裡測「機動放 QM」怎麼顯示（判定另外測）
    return {"R": R, "L": L, "W": None}


def test_qm_card_shows_holdings_todo_and_new_numbers(R, QMX):
    from arm.lab import ussxspec as X
    for mk in ("spx", "ndx"):
        assert P.qm_on(mk, QMX), mk                                               # 判定過了才換（研究檔 switch）
        h = P.card(mk, _us(mk), R, None, {"n": 0, "next": S.CHECKS[0]}, QMX)
        t = _text(h)
        assert "新規則驗證中" in t and P.QM_NAME in t and "也買同一個指數" not in t and "交易計畫：全部機動" in t
        order = [h.index(x) for x in ('class="plnnow"', "接下來要做的事", "每天收盤後", "過去照做的結果", "照做一年會怎樣", "細節")]
        assert order == sorted(order)
        n = QMX["L"]["now"]
        for x in n["hold"]:                                                       # 現在拿著的每一檔：比重、買進日、到最新一天漲跌
            assert f'{x["c"]} {P._wp(x["w"] * S.sat_of(mk))}' in t and f'{P._md(x["ent"])} 買，到 {P._md(n["d"])} {P._pc(x["r"])}' in t
        assert f"最多 {X.QM_SLOTS} 檔、每檔約占全部資金 {P._qm_per(mk)}" in t and "收盤跌破 50 日線，就在下一個交易日開盤賣" in t
        assert "空的位子放現金" in t
        assert "看這一週的新名單" in t and "每天收盤" in t                                # 接下來要做的事
        sc = QMX["R"]["sc"][mk]
        cur = QMX["R"]["plans"][f"{mk}_main"]["cur"]
        assert P._wan(sc["plan"]["m"]) in t and P._wan(sc["hold"]["m"]) in t and P._ab(sc["plan"]["mdd"]) in t   # 好處＝三成放 QM
        assert f'如果機動也買{P._ixn(mk)}、只靠警訊進出：100 萬變 {P._wan(cur["plan"]["m"])}' in h                 # 同一段時間的舊做法
        assert P._wan(R["mk"][mk]["sc"]["rule"]["plan"]["m"]) in t                 # 只靠警訊進出的長紀錄仍列在拆期間表
        alt = QMX["R"]["plans"][f"{mk}_alt"]["new"]["plan"]["m"]
        assert f"放進計畫 100 萬變 {P._wan(alt)}" in t                               # 複委託的成本
        assert "美股個股策略做好、驗證過才會換" not in t
        for w in BANNED + JARGON + NOT_PLAIN:
            assert w not in t, (mk, w)
        cls = {c for a in re.findall(r'class="([^"]+)"', h) for c in a.split()}
        assert all(c.startswith("pln") for c in cls), cls


def test_qm_card_sell_buy_and_watch(R, QMX):
    import copy
    from arm.lab import ussxqm as QM
    from arm.lab import ussxspec as X
    q = copy.deepcopy(QMX)
    n = q["L"]["now"]
    c0 = n["hold"][0]["c"]
    nd = QM.next_day(n["d"])
    q["W"] = {"ver": X.VER, "base": n["d"], "d": nd, "hold": [{"c": c0, "pct": -0.012, "trig": nd}],
              "sell": [{"c": c0, "trig": nd, "on": QM.next_day(nd)}]}
    t = _text(P.card("spx", _us(), R, None, None, q))
    nm0 = _text(P.us_name(c0, P._qm_names(q)))                                     # 公司名（代號）（2026-10-24 起）
    assert f"賣掉 {nm0}" in t and f"{P._md(nd)} 收盤跌破 50 日線，{P._md(QM.next_day(nd))} 開盤賣" in t
    q["W"]["base"] = "2000-01-03"                                                 # 對不上最新一週紀錄的檢查不採用
    assert f"賣掉 {nm0}" not in _text(P.card("spx", _us(), R, None, None, q))
    q = copy.deepcopy(QMX)                                                        # 一週結束：下一個交易日開盤補空位
    q["L"]["now"].update(wk=q["L"]["now"]["d"], wk_done=True, buy=["PAYC"])
    t = _text(P.card("spx", _us(), R, None, None, q))
    assert f'{P._mdw(q["L"]["now"]["next"])}' in t and f"買進 {P.us_name('PAYC')}" in t and "PAYC 約" in t
    N = _us(flat=True, held=())                                                   # 有警訊、還拿著：下一個交易日收盤換現金
    t = _text(P.card("spx", N, R, None, None, QMX))
    assert "現在買了這些" in t and "把全部持股賣掉，改放現金" in t and "整個帳戶都是現金" in t
    N.update(now=S.core_of("spx"), due=False)                                    # 已經是現金：照樣列出買回時的持股
    t = _text(P.card("spx", N, R, None, None, QMX))
    assert "全部持股現在放現金；買回時照這樣買" in t
    N = _us()
    N.update(now=S.core_of("spx"), next=1.0, due=True)
    t = _text(P.card("spx", N, R, None, None, QMX))
    assert "照美股強勢品質股當時拿著的股票買，空的位子留現金" in t


def test_qm_off_keeps_index_and_says_why(R, QMX):
    import copy
    q = copy.deepcopy(QMX)
    q["R"]["switch"]["ndx"] = False
    q["R"]["verdict"]["c2"]["ndx"] = False
    q["R"]["verdict"]["pass"]["ndx"] = False
    assert not P.qm_on("ndx", q) and P.qm_on("spx", q) and not P.qm_on("tw", q)
    t = _text(P.card("ndx", _us("ndx"), R, None, None, q))
    assert "照舊買指數" in t and "放進計畫沒有比原本七成長抱的計畫好" in t and "新規則驗證中" not in t
    assert P._wan(R["mk"]["ndx"]["sc"]["rule"]["plan"]["m"]) in t                 # 好處照舊用三成也買指數的回測
    assert not P.qm_on("spx", {"R": None}) and not P.qm_on("spx", None)


def test_core_data_loads_qm_and_record_marks_sleeve(tmp_path, monkeypatch, R, QMX):
    from arm.lab import ussxqm as QM
    monkeypatch.setattr(SG, "CARDS", {"spx": {"core": _us()}, "tw": {"core": _now()}})
    monkeypatch.setattr(CO, "STK", dict(STK))
    monkeypatch.setattr(CO, "LIVE", tmp_path / "core_live.json")
    monkeypatch.setattr(QM, "WATCH", tmp_path / "none.json")
    monkeypatch.setattr(QM, "load", lambda path=None: QMX["R"])                 # 機動放 QM 的版面（判定另外測）
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    X = SG.core_data(tmp_path)
    assert X["qm"] and X["qm"]["R"]["ver"] == QMX["R"]["ver"] and X["qm"]["W"] is None
    L = json.loads((tmp_path / "core_live.json").read_text(encoding="utf-8"))
    day = L["days"][_us()["d"]] if _us()["d"] >= S.LIVE_START else {}
    if day:                                                                       # LIVE_START 之後的資料日才記
        assert day["spx"]["sat"] == ["qm"] and day["tw"]["sat"] == [s["k"] for s in STK["st"]] + ["R60"]
    V = {"rmk": [], "pr": {}, "find": {"spx": {}}, "core": dict(X, now={"spx": _us()})}
    h = SG.research_html(V)
    assert 'id="pln-spx"' in h and P.QM_NAME in h and "新規則驗證中" in h


def test_core_record_writes_qm_sleeve(tmp_path, monkeypatch):
    monkeypatch.setattr(CO, "LIVE", tmp_path / "core_live.json")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    N = dict(_us(), d="2026-10-26")
    assert CO.record({"spx": N, "ndx": dict(N, mk="ndx")}, None, {"spx": True, "ndx": False})
    L = json.loads((tmp_path / "core_live.json").read_text(encoding="utf-8"))
    assert L["ver"] == S.VER and L["days"]["2026-10-26"]["spx"]["sat"] == ["qm"] and "sat" not in L["days"]["2026-10-26"]["ndx"]


def test_start_year_is_first_return_year():
    """「X 年起」寫第一個算報酬的年份：起點是 2013-12-31 收盤 → 2014 年起（美股強勢品質股的回測）。"""
    assert P.yr0("2013-12-31") == "2014" and P.yr0("2019-01-02") == "2019" and P.yr0("2006-01-25") == "2006"
    assert P.yr0(None) == "—"


def test_qm_buy_split_respects_remaining_cash():
    """2026-10-24：FTNT 寫「約 12.5%」但現金只剩 10.3%，持股表加起來 102%——要買的每一檔不超過剩下的現金（同 ussxbook），
    開盤先賣的部位那一份也算進可以用的現金。"""
    n = {"next": "2026-10-26", "idle": 0.103, "hold": [{"c": "A", "w": 0.45}, {"c": "B", "w": 0.447}], "buy": ["FTNT"], "sell": []}
    split, idle = P.qm_buy_split(n)
    assert split == [("FTNT", 0.103)] and idle == 0.0
    n2 = {**n, "idle": 0.30, "buy": ["X", "Y", "Z"]}
    split, idle = P.qm_buy_split(n2)
    assert [round(w, 4) for _, w in split] == [0.125, 0.125, 0.05] and idle == 0.0
    n3 = {**n, "idle": 0.05, "hold": [{"c": "A", "w": 0.5, "sell": True}, {"c": "B", "w": 0.45}], "buy": ["X"]}
    split, idle = P.qm_buy_split(n3)                                    # 開盤先賣 A，賣掉的錢拿去買
    assert split == [("X", 0.125)] and idle == 0.0
    W = {"sell": [{"c": "B", "on": "2026-10-26", "trig": "2026-10-23"}]}
    split, _ = P.qm_buy_split({**n, "idle": 0.0, "buy": ["X"]}, W)     # 每天的 50 日線檢查要賣的也算
    assert split == [("X", 0.125)]
