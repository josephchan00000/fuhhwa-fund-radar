"""大神策略的呈現（arm/lab/xstratpage.py）：白話文字、訊號總覽的資料、景氣頁今天的重點與最上面那一行。"""
import json
import re

from arm.lab import xstrat as X
from arm.lab import xstratpage as P
from arm.lab import xstratspec as S

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


def _all_text(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _all_text(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _all_text(v)


def _fake(k, kind, st, **now):
    n = {"st": st, "d": "2026-10-19", "nx": "2026-10-20", **now}
    return {"k": k, "kind": kind, "now": n}


def test_now_text_every_state_has_dates_and_no_banned_words():
    cases = [
        _fake("rsi2", "trade", "buy", rsi2=6.2, ma=0.05),
        _fake("rsi2", "trade", "hold", ed="2026-10-14", ep=7744.0, ret=-0.007, held=3, ex=-0.004, rsi2=30, ma=0.05),
        _fake("rsi2", "trade", "hold", ed="2026-10-19", ep=7744.0, ret=0.0, held=0, rsi2=8, ma=0.05),
        _fake("rsi2", "trade", "sell", ed="2026-10-14", ret=0.012, rsi2=60, ma=0.05),
        _fake("rsi2", "trade", "wait", rsi2=45, ma=-0.02),
        _fake("vixs", "trade", "buy", vix=25.0, vs=0.12, run=3, rsi2=20, ma=0.03),
        _fake("vixs", "trade", "wait", vix=15.0, vs=-0.03, run=0, rsi2=50, ma=0.03),
        _fake("tom", "trade", "buy", ed="2026-10-20", qd="2026-10-26"),
        _fake("tom", "trade", "hold", ed="2026-10-15", qd="2026-10-21", ret=0.004),
        _fake("tom", "trade", "wait", ed="2026-10-29", qd="2026-11-04"),
        _fake("hal", "alloc", "out", sw="2026-10-30"),
        _fake("hal", "alloc", "turn_in", sw="2026-10-20"),
        _fake("faber", "alloc", "in", dist=0.05, chk="2026-10-30", ed="2026-05-01", ret=0.06),
        _fake("faber", "alloc", "turn_out", dist=-0.01, chk="2026-10-30"),
        _fake("ma200", "alloc", "out", dist=-0.03),
        _fake("ma200", "alloc", "turn_in", dist=0.01),
        _fake("mom12", "alloc", "in", dist=0.12, chk="2026-10-30"),
    ]
    for r in cases:
        t = P.now_text(r)
        assert t and not any(w in t for w in BANNED), t
        assert "今天" not in t and "明天" not in t, t           # 美股的資料日是前一個美股交易日：一律寫日期
        if r["now"]["st"] in ("buy", "sell", "turn_in", "turn_out") and r["k"] not in ("tom", "hal"):
            assert "10/20" in t, t                                 # 下一個交易日寫日期
    same = [  # 台股 RSI(2)（VER 2）：當天收盤前用台指期，寫下一個交易日的價位
        _fake("rsi2", "trade", "hold", lag=0, ed="2026-10-13", ep=48341.31, ret=-0.042, held=5, ex_px=46799.04, px=46292.93,
              rsi2=5.6, ma=0.15),
        _fake("rsi2", "trade", "hold", lag=0, ed="2026-10-19", ep=46292.93, ret=0.0, held=0, ex_px=46800.0, px=46292.93,
              rsi2=5.6, ma=0.15),
        _fake("rsi2", "trade", "near", lag=0, hi_px=45800.12, lo_px=41000.5, hi_chg=-0.0107, can=True, rsi2=30, ma=0.15),
        _fake("rsi2", "trade", "wait", lag=0, hi_px=44800.12, lo_px=41000.5, hi_chg=-0.031, can=True, rsi2=45, ma=0.15),
        _fake("rsi2", "trade", "wait", lag=0, hi_px=40800.12, lo_px=41000.5, hi_chg=-0.12, can=False, rsi2=45, ma=0.01),
        _fake("rsi2", "trade", "wait", lag=0, hi_px=40800.12, lo_px=46000.5, hi_chg=-0.12, can=False, rsi2=45, ma=-0.02),
    ]
    for r in same:
        t = P.now_text(r)
        assert t and not any(w in t for w in BANNED) and "今天" not in t and "明天" not in t, t
        if r["now"]["st"] in ("hold", "near"):
            assert "10/20" in t and "台指期" in t, t
    assert "46,799" in P.now_text(same[0]) and "比 10/19 收盤高 1.1%" in P.now_text(same[0])
    assert "45,800" in P.now_text(same[2]) and "41,000" in P.now_text(same[2]) and P.side(same[2]) == "up"
    assert "不會出現買進訊號" in P.now_text(same[4]) and P.side(same[3]) is None
    assert "低於 45,800 就買" in P.now_short(same[2])
    dips = [  # 落底型（VER 3）
        _fake("coppock", "dip", "wait", H=250, cm="2026-09", cv=-12.3, cp=-15.0, cnow=-11.0, chk="2026-10-30", ld="2023-03-31", lret=0.25),
        _fake("coppock", "dip", "buy", H=250, cm="2026-10", cv=-12.3, cp=-15.0),
        _fake("vix40", "dip", "hold", H=60, sd="2026-10-01", ed="2026-10-02", ep=100.0, ret=0.03, held=12, qd="2026-12-29", left=48),
        _fake("vix40", "dip", "wait", H=60, vix=18.4, vmax=20.7),
        _fake("zweig", "dip", "wait", H=120, e=0.45, ed_="2026-10-19", emin=0.41),
        _fake("ftd", "dip", "wait", H=60, dd=-0.12, **{"in": True}, low_d="2026-10-10", low_px=100.0, rday=3, done=False),
        _fake("ftd", "dip", "wait", H=60, dd=-0.03, **{"in": False}, done=False),
        _fake("dev60", "dip", "wait", H=20, dev=-0.08),
    ]
    for r in dips:
        t = P.now_text(r)
        assert t and not any(w in t for w in BANNED) and "今天" not in t and "明天" not in t, t
        assert P.now_short(r)
    assert "10/20 收盤買" in P.now_text(dips[1]) and "12/29 收盤賣" in P.now_text(dips[2])
    assert "反彈第 3 天" in P.now_text(dips[5]) and "要低 15% 以上" in P.now_text(dips[7])
    assert "低 2.0 個百分點" in P._trade_why({"n": 40, "win": 0.6, "base": 0.62, "avg": 0.001})
    assert "多跌" in P._alloc_why({"cagr": 0.05, "mdd": 0.4, "mar": 0.125}, {"cagr": 0.08, "mdd": 0.3})


def test_payload_and_detail_from_real_results():
    R = X.run_all()
    pl = P.payload(R)
    assert set(pl["spec"]) == set(S.KEYS) and pl["ver"] == S.VER
    for mk in S.MARKETS:
        D = X.data(mk)                                   # VER 4：資料還沒回補的策略先不列
        assert set(pl["m"][mk]) == {s["k"] for s in S.STRATS if mk in s["mk"] and X.has_data(D, s["k"])}
        for k, x in pl["m"][mk].items():
            assert x["t"] in S.TIERS and x["st"] in P.TAG and x["now"] and x["line"] and x["rules"] and x["why"]
            assert x["ol"] == ("隔天收盤" if (mk, k) in S.SAME_DAY else "原作者時點") and x["os"]
            assert any("台指期" in t for t in x["rules"]) == ((mk, k) in S.FUT)
            assert all(ok in (0, 1, None) for ok, _ in x["why"])
            assert len(x["g"]) == len(R[mk][k]["grid"])
            assert x["side"] in (None, "up", "warn")
    text = list(_all_text(pl))
    assert not [t for t in text if any(w in t for w in BANNED)]
    dt = P.detail(R)
    assert len(dt) == sum(len(v) for v in R.values())
    for key, v in dt.items():
        assert len(v["eq"]["d"]) == len(v["eq"]["s"]) == len(v["eq"]["b"])
        dip = S.BY_KEY[key.split(":")[2]]["kind"] == "dip"
        assert all(len(t) == (8 if dip else 6) for t in v["tr"])           # 落底型多中途最多跌、訊號日
    json.dumps(pl, ensure_ascii=False)
    json.dumps(dt, ensure_ascii=False)


def test_board_lists_only_good_strategies_with_actions():
    R = X.run_all()
    for mk in S.MARKETS:
        for it in P.board(mk, R):
            r = R[mk][it["id"].split(":")[2]]
            assert r["tier"] == "good" and P.side(r) == it["side"]
            li = P.board_li(it)
            assert 'href="x9o.html#i=xs:' in li and ">策略<" in li
    fake = {"tw": {"rsi2": {**R["tw"]["rsi2"], "tier": "ref"}}}
    assert P.board("tw", fake) == []                              # ● 不列


def test_chip_every_market():
    R = X.run_all()
    for mk in S.MARKETS:
        c = P.chip(mk, R)
        assert "10 個月均線" in c and f"x9o.html#i=xs:{mk}:faber" in c
        assert re.search(r"<i>(持有|空手|要買回|要賣出)</i>", c)
    assert P.chip("tw", {}) == ""


def test_pages_wire_strategies():
    from arm.lab import heatpage as HP
    from arm.lab import heatviz as VZ
    from arm.lab import sigpage as SP
    assert SP.IND_CATS["xs"] == "大神策略"
    for f in ("function xsPanel", "function xsOpen", "function xsEq", "function xsTr", "function xsCsv", "x.cat === 'xs'"):
        assert f in SP.JS, f
    assert ".xsg{" in SP.CSS and ".xsseg" in SP.CSS
    R = X.run_all()
    V = {"rows": [], "on": {}, "xs": R, "items": {}, "asof": {}, "today": {}, "stk": [], "bases": {}}
    pj = json.loads(SP.page_json(V).replace("<\\/", "</"))
    assert set(pj["xs"]["m"]) == set(S.MARKETS)
    dj = json.loads(SP.detail_json(V))
    assert len(dj["xs"]) == sum(len(v) for v in R.values())
    # 景氣頁：今天的重點的策略列、最上面那一行的 10 個月均線
    T = {"up": [], "warn": [], "d": "2026-10-19", "thermo": []}
    item = {"id": "xs:spx:rsi2", "side": "up", "name": "RSI(2) 超賣反彈", "st": "hold", "now": "持有中：…", "line": "過去 309 筆：…",
            "grp": "短線（幾天）"}
    import arm.lab.heatviz as HV
    orig = HV.thermo_html
    HV.thermo_html = lambda T: ""
    try:
        h = VZ.today_html({"sigtoday": T, "xsb": [item]})
    finally:
        HV.thermo_html = orig
    assert "xs:spx:rsi2" in h and "1 個策略" in h and "tzs" in h
    sl = HP.state_line({"dims": {}, "xschip": P.chip("spx", R), "mk": "spx"})
    assert "10 個月均線" in sl
