"""研究結論（arm/lab/findings.py；docs/lab_research_v2_plan.md）：七則問答的答案跟研究判定一致、數字跟研究檔一致、
版面沒有內部術語與禁用詞、訊號總覽怎麼接。"""
import json
import re

import pytest

from arm.lab import findings as FD
from arm.lab import practsim as PS
from arm.lab import sigpage as SP

BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買", "建議賣", "目標價", "零風險", "無風險")
JARGON = ("VER", "候選", "門檻", "夏普", "前後兩半", "95%", "區間", "扣掉波動", "BH", "practspec", "固定持有", "樣本外")


def _st(v, vv=None, n=100, med=0.12, q10=0.58, bmed=0.067, bq10=0.30):
    return {"v": v, "vv": vv or v, "n": n, "ep": 7, "ev": {"med": med, "q10": q10}, "base": {"med": bmed, "q10": bq10}}


def _hotch(mk="tw", c1=("up", "up"), w=47, key="H26"):
    """反向檢查的狀態（hotchpage.state 的形狀，只留研究結論用到的）。"""
    st = {"H1": _st("none"), "H4": _st("none"), "H13": _st(*c1), "H26": _st("few")}
    runs = [{"a": "2007-03-03", "wk": 48, "mdd": 0.2448, "open": False, "hot": False},
            {"a": "2014-06-13", "wk": 10, "mdd": 0.11, "open": False, "hot": False},
            {"a": "2025-11-28", "wk": w, "mdd": 0.1636, "open": True, "hot": True}]
    B = {"ev": {"ma60_dn": {"a": "1991-01-10", "n": 69, "v": "none", "vv": "none", "ev": {"med": 0.072, "q10": 0.39},
                            "base": {"med": 0.083, "q10": 0.41}}},
         "dsum": {"20": {"ma60_dn": {"n": 3, "hit": 2, "days": 14.0, "lost": 0.103, "rem": 0.238}}},
         "decl": {"20": [{"pk": "1990-02-10", "tr": "1990-10-01", "dd": 0.53, "open": False},
                         {"pk": "2000-02-17", "tr": "2001-09-26", "dd": 0.66, "open": False},
                         {"pk": "2008-05-19", "tr": "2008-11-20", "dd": 0.56, "open": False}]},
         "drows": {"20": {"ma60_dn": [None, [None], ["2008-06-02", 9, 0.08, 0.40]]}}}
    return {"mk": mk, "px": "", "names": {"C1": "融資餘額水位", "C3": "券資比"}, "order": ("C1", "C3"),
            "R": {"start": "1990-01-04", "A": {"C1": {"st": st, "runs": runs}, "C3": {"st": {s: _st("none") for s in st}}}, "B": B},
            "now": {"chip": {"C1": {"w": w, "key": key}, "C3": {"w": 0}}, "runs": {"C1": runs},
                    "recent": {"ma60_dn": ["2026-10-20"]}, "states": {"below60": {"on": False}}}}


def _hotdd(v="none"):
    E = dict(_st(v, n=40, med=0.066, q10=0.25, bmed=0.074, bq10=0.35), a="2002-01-04",
             list=[["2021-03-10", 0.127, 0.0, 0.055, "2021-04-27", "2021-05-17", 82.0]])
    return {"R": {"start": "1997-01-02", "rows": {"tech": {"kind": "dim", "ev": {"E": E, "S4": _st("down")}},
                                                    "fund": {"kind": "dim", "ev": {"E": _st("few")}}, "mkt": {"kind": "mkt", "ev": {"E": _st("up")}}}},
            "now": {"hot": [{"k": "fund", "kind": "dim", "wk": 28}, {"k": "x1", "kind": "item", "wk": 3}]},
            "short": {"fund": "基本面", "tech": "技術面"}, "names": {"fund": "基本面熱度"}}


def _bottom(mk="tw", good=False, active=False):
    lp = {"n": 40, "few": False, "lp_rule": 0.62, "lp_base": 0.38, "lp_lo": 0.05, "lp_dir": "none"}
    rules = {"W10": {"lp": {"n": 61, "lp_rule": 0.34, "lp_base": 0.34}, "v": "none"},
             "C2": {"lp": lp, "v": "better" if good else "none"},
             "C1": {"lp": {"n": 40, "few": False, "lp_rule": 0.1, "lp_base": 0.4, "lp_lo": -0.4, "lp_dir": "down"}, "v": "worse"}}
    E = {"n": 62, "all": {"lp": {"rate": 0.34}, "r60": {"mean": 0.001, "med": 0.001, "up": 0.5}}, "rules": rules,
         "list": [{"d": "2024-08-05", "depth": -0.12, "r60": 0.08, "pos": 0.2, "mae": 0.05}]}
    act = [{"ev": "E5", "t": "2026-10-14", "p": "2026-10-06", "days": 5, "nowdd": -0.13, "low": "2026-10-16", "lowdd": -0.157,
            "depth": -0.106}] if active else []
    return {"mk": mk, "R": {"start": "1990-01-04", "ev": {"E5": E}}, "now": {"active": act, "dd60": -0.076, "last": {"E5": "2026-06-10"}}}


def _crash(mk="tw", hot=True):
    out = {"A2": {"v": "up", "hot": 0.21, "not": 0.06, "base": 0.08, "oos": {"v": "same", "n": 100}, "zones": [], "strata": []}}
    return {"mk": mk, "px": "加權指數", "R": {"preds": {"C6": {"a": "2019-12-02", "out": out}}},
            "now": {"preds": {"C6": {"v": 87.0, "hot": hot, "g": {"A2": 1}}}}, "vs": {"vol": 0.013, "pct": 0.62, "g": 1}}


def _practsim(bh_end=7.0, a1_end=4.7, m2_end=2.9):
    d = [f"20{y:02d}-01-0{1 + i}" for y in range(6, 26) for i in range(1)]
    n = len(d)

    def ser(end, p):
        return {"nav": [1 + (end - 1) * i / (n - 1) for i in range(n)], "pos": [p] * n, "fix": [1.0] * n}
    t = {"d": d, "bh": [1 + (bh_end - 1) * i / (n - 1) for i in range(n)], "r": {"A1": ser(a1_end, 0.75), "D1": ser(bh_end, 1.0)}}
    x = {"d": ["2002-01-04"] + d, "bh": [0.8] + t["bh"], "r": {"M2": {"nav": [1.0] + ser(m2_end, 0.4)["nav"], "pos": [0.4] * (n + 1)}}}
    return {"mk": {"tw": {"t_series": t, "x_series": x}}}


def _vis(h: str) -> str:
    return re.sub(r"<[^>]+>", "", h)


def test_chip_answer_follows_verdict_and_current_state():
    F = FD.chip(_hotch())
    assert F["ans"] == "yes" and F["k"] == "C1" and F["st"] == "H13" and F["on"] and F["w"] == 47
    assert F["ev"] == [0.12, 0.58] and F["base"] == [0.067, 0.3]
    assert [r[0] for r in F["runs"]] == ["2007-03-03", "2025-11-28"]          # 13 週以上的段（10 週那段不列）
    assert FD.chip(_hotch(c1=("up", "none")))["ans"] == "raw"                  # 扣掉波動看不出＝表面上會
    F2 = FD.chip(_hotch(c1=("none", "none"), w=0))
    assert F2["ans"] == "no" and not F2["on"]
    h, line = FD.chip_card("tw", F)
    assert "會" in _vis(h) and line[0] == "risk" and "融資餘額水位已連續過熱 47 週" in line[1] and "12.0%" in line[1]
    h2, line2 = FD.chip_card("tw", F2)
    assert line2 == "" and "現在沒有融資項目過熱" in _vis(h2)


def test_hotin_counts_all_comparisons_and_lists_hot_dims():
    F = FD.hotin(_hotdd("none"))
    assert F["ans"] == "same" and F["cnt"] == {"all": 3, "up": 0, "down": 1} and F["hot"] == [["基本面", 28]]
    assert FD.hotin(_hotdd("down"))["ans"] == "less" and FD.hotin(_hotdd("up"))["ans"] == "yes"
    h, line = FD.hotin_card("tw", F)
    assert "不會" in _vis(h) and "基本面已連續過熱 28 週" in _vis(h) and line == ""


def test_ma60_rows_and_now():
    F = FD.ma60(_hotch())
    assert F["ans"] == "same" and F["big"]["n"] == 3 and F["recent"] == "2026-10-20"
    assert F["rows"][0][4] == "2008-06-02" and F["rows"][1][4] is None and F["rows"][2][4] == "na"      # 新的在前
    h, line = FD.ma60_card("tw", F)
    assert "和平常差不多" in _vis(h) and line[0] == "side" and "2026/10/20 跌破季線" in line[1]
    assert "低點前沒有跌破" in h and "還沒有資料" in h


def test_bottom_answer_and_active_event():
    F = FD.bottom(_bottom())
    assert F["ans"] == "no" and F["lp_b1"] == 0.34 and F["lp_w10"] == 0.34
    assert [x[0] for x in F["lean"]] == ["融資減少"] and [x[0] for x in F["low"]] == ["VIX 回落"]
    assert FD.bottom(_bottom(good=True))["good"] == ["融資減少"]
    h, line = FD.bottom_card("tw", FD.bottom(_bottom(active=True)))
    assert line[0] == "side" and "2026/10/14 出現 5 日急跌" in line[1] and "比 10/6 的高點低 13.0%" in _vis(h)
    assert FD.bottom_card("tw", F)[1] == ""


def test_crash_items_with_direction_words():
    F = FD.crash(_crash())
    assert F["ans"] == "some" and F["up"][0][0] == "外資選擇權淨部位" and F["up"][0][7] == "偏低" and F["better"] == 0
    h, line = FD.crash_card("tw", F)
    v = _vis(h)
    assert "有 1 項" in v and "外資選擇權淨部位偏低・20 日內急跌" in v and "21% → 6%" in v and "沒有比只看「最近波動大不大」更準" in v
    assert line[0] == "risk" and "外資選擇權淨部位偏低" in line[1]
    assert FD.crash_card("tw", FD.crash(_crash(hot=False)))[1] == ""


def test_money_compares_with_holding_from_common_start():
    X = FD.money(_practsim(), "tw")
    assert X["start"] == "2006-01-01" and X["ans"] == "no" and X["adj"] == ["A1", "M2"]
    assert X["rows"]["bh"][0] == pytest.approx(7.0) and X["rows"]["A1"][0] == pytest.approx(4.7) and X["rows"]["bh"][2] == 1.0
    assert X["rows"]["M2"][0] == pytest.approx(2.9) and X["rows"]["M2"][2] == pytest.approx(0.4)    # 從共同起點重算
    assert FD.money(_practsim(a1_end=8.0), "tw")["more"] == ["A1"]
    h, _ = FD.money_card("tw", X)
    v = _vis(h)
    assert "不能" in v and "700 萬" in v and "470 萬" in v and "290 萬" in v and "每週走勢" in v and 'href="#p=A1:tw"' in h


def test_money_on_real_research_is_consistent():
    """實測研究檔（入庫）：答案＝「不能」若且唯若每一種調整持股的做法都比一直抱著少。"""
    R = PS.load()
    if not R:
        pytest.skip("實測研究檔還沒產生")
    for mk in R["mk"]:
        X = FD.money(R, mk)
        assert X and set(X["adj"]) <= set(FD.MONEY_RULES)
        below = all(X["rows"][k][0] <= X["rows"]["bh"][0] for k in X["adj"])
        assert (X["ans"] == "no") == below


def test_market_html_seven_cards_plain_words():
    F = {"d": "2026-10-22", "chip": FD.chip(_hotch()), "hotin": FD.hotin(_hotdd()), "ma60": FD.ma60(_hotch()),
         "bottom": FD.bottom(_bottom()), "crash": FD.crash(_crash())}
    kp = {"u1": 0.0, "u3": 0.03, "u12": 0.03, "w1": 0.22, "w3": 0.0}
    h = FD.market_html("tw", F, FD.money(_practsim(), "tw"), kp, show=True)
    assert h.count('<article class="rfc') == 7 and 'data-mk="tw"' in h and " hidden" not in h.split(">")[0]
    v = _vis(h)
    for w in BANNED + JARGON:
        assert w not in v, w
    assert "現在適用" in v and v.index("融資餘額水位已連續過熱 47 週") < v.index("2026/10/20 跌破季線")   # 風險在前、參考在後
    assert h.count('<li class="rfi">') == 1
    empty = FD.market_html("spx", {}, None, None)
    assert "hidden" in empty and "研究狀態還沒產生" in empty and "現在適用</b>：沒有" in empty


def test_css_prefixed():
    classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", FD.CSS))
    shared = {"yes", "mid", "no", "risk", "side", "on", "l", "mu", "hi", "ac", "rfy"}
    assert all(c.startswith("rf") or c in shared for c in classes), sorted(c for c in classes if not c.startswith("rf") and c not in shared)


def test_overview_reads_find_from_previous_card_files(tmp_path, monkeypatch):
    """單獨建訊號總覽時，研究結論第 2～6 則從上一版的 x9or-{市場}.json 讀回來；同一個程序裡景氣頁算的優先。"""
    monkeypatch.setattr(SP, "CARDS", {"spx": {"find": {"mk": "spx", "d": "2026-10-21", "chip": {"ans": "less"}}}})
    (tmp_path / "x9or-tw.json").write_text(json.dumps({"mk": "tw", "html": "", "find": {"mk": "tw", "chip": {"ans": "yes"}}}))
    (tmp_path / "x9or-ndx.json").write_text("{broken")
    got = SP.find_data(tmp_path)
    assert set(got) == {"tw", "spx"} and got["tw"]["chip"]["ans"] == "yes" and got["spx"]["d"] == "2026-10-21"
    c = {"d": "2026-10-22", "crash": "<p>a</p>", "find": {"mk": "tw", "d": "2026-10-22"}}
    assert json.loads(SP.card_json("tw", c))["find"] == {"mk": "tw", "d": "2026-10-22"}
    assert "find" not in json.loads(SP.card_json("tw", {"d": "x", "crash": "<p>a</p>"}))


def test_research_section_layout_and_js():
    """研究結論在上、完整研究表（實測細節＋研究卡）收在最下面；選市場切換七則；#r=市場:卡 打開完整研究表那一張。"""
    V = {"rmk": ["tw", "spx"], "find": {"tw": {"d": "2026-10-22", "chip": FD.chip(_hotch())}}, "pr": {"P": {"ok": False}, "R": None}}
    h = SP.research_html(V)
    assert h.index('<h2>研究結論') < h.index('id="rmk"') < h.index('class="rfm"') < h.index('id="rfull"') < h.index('id="rbox"')
    assert h.count('class="rfm"') == 2 and h.count(" hidden>") >= 1
    assert "研究細節" not in h and "各市場的研究卡" not in h
    for k in ("function rfShow(", "RPEND", "rfShow(m[1]); if (m[2]) loadR(m[1], m[2])", "addEventListener('toggle'"):
        assert k in SP.JS, k


def _tilt_R():
    from arm.lab import tilt as TL
    R = TL.load()
    if not R:
        pytest.skip("沒有期貨加碼研究檔")
    return R


def test_tilt_matches_research_file_and_page_rule():
    """第 2 則（期貨加碼）：數字跟研究檔一致；放上網頁的規則（tiltspec 第 8 節）當主角；版面沒有術語與禁用詞、手機改直排。"""
    from arm.lab import tiltspec as TS
    R = _tilt_R()
    ok = [k for k in TS.PAGE_RULES if R["page"][k]["ok"]]
    for mk in ("tw", "spx", "ndx", "ixic", "sox"):
        X = FD.tilt(R, mk, live=False)
        M = R["mk"][mk]
        assert X["main"] == (ok[0] if ok else X["main"]) and X["judged"] == (mk in TS.JUDGED)
        for k, r in X["rows"].items():
            x = M["rules"][k]
            assert r["m"] == x["man"] / 1e6 and r["fm"] == x["man_fix"] / 1e6 and r["v"] == x["v"]
            assert r["dd"] == x["full"]["rule"]["mdd"] and r["fdd"] == x["full"]["fix"]["mdd"]
        h, line = FD.tilt_card(mk, X)
        v = _vis(h)
        k = X["main"]
        for w in (f"{X['bh']['m'] * 100:,.0f} 萬", f"{X['rows'][k]['m'] * 100:,.0f} 萬", f"{X['rows'][k]['fm'] * 100:,.0f} 萬"):
            assert w in v, (mk, w)
        for w in BANNED + JARGON:
            assert w not in v, (mk, w)
        assert 'class="rftb rftk"' in h and 'id="rf-tilt"' in h and f"<i>{FD.QN['tilt']}</i>" in h
        assert ("沒有對應的期貨" in v) == (mk not in TS.JUDGED)
    assert ".rftk tr{display:grid" in FD.CSS


def test_tilt_answer_follows_verdict_and_live_state():
    import copy
    R = copy.deepcopy(_tilt_R())
    k = FD.tilt(R, "tw", live=False)["main"]
    R["page"][k]["ok"] = True
    ans = lambda mk, **kw: re.sub("<[^>]+>", " ", re.search(r'<div class="rfa[^"]*">(.*?)</div>', FD.tilt_card(mk, FD.tilt(R, mk, live=False) | kw)[0]).group(1))
    R["mk"]["tw"]["rules"][k]["v"] = "better"
    assert ans("tw").startswith("可以參考")
    R["mk"]["tw"]["rules"][k]["v"] = "same"
    assert ans("tw").startswith("差不多")
    R["mk"]["tw"]["rules"][k]["v"] = "worse"
    assert ans("tw").startswith("比固定多拿差")
    assert ans("sox").startswith("沒有對應的期貨")
    for q in R["page"]:
        R["page"][q]["ok"] = False
    assert ans("tw").startswith("多賺的是多拿股票")
    R["page"][k]["ok"] = True
    R["mk"]["tw"]["rules"][k]["v"] = "better"
    X = FD.tilt(R, "tw", live=False)
    if k == "K4":
        up = {"since": "2026-10-23", "days": 70, "rule": 0.05, "fix": 0.04, "bh": 0.03, "a": "2026-10-23",
              "state": {"up": True, "since": "2025-06-25", "d": "2027-01-30"}}
        h, line = FD.tilt_card("tw", X | {"live": up})
        assert line[0] == "side" and "正在加碼" in _vis(h) and "+5.0%" in _vis(h)
        dn = dict(up, days=10, state={"up": False, "since": "2027-01-20", "d": "2027-01-30"})
        h, line = FD.tilt_card("tw", X | {"live": dn})
        assert line == "" and "不加碼" in _vis(h) and "還在累積" in _vis(h)


def test_market_html_with_tilt_has_eight_cards():
    R = _tilt_R()
    h = FD.market_html("tw", {}, None, None, show=True, tilt_x=FD.tilt(R, "tw", live=False))
    assert h.count('<article class="rfc') == 1 and 'id="rf-tilt"' in h
    F = {"d": "2026-10-22", "chip": FD.chip(_hotch()), "hotin": FD.hotin(_hotdd()), "ma60": FD.ma60(_hotch()),
         "bottom": FD.bottom(_bottom()), "crash": FD.crash(_crash())}
    kp = {"u1": 0.0, "u3": 0.03, "u12": 0.03, "w1": 0.22, "w3": 0.0}
    h = FD.market_html("tw", F, FD.money(_practsim(), "tw"), kp, show=True, tilt_x=FD.tilt(R, "tw", live=False))
    assert h.count('<article class="rfc') == 8
    nums = re.findall(r'<div class="rfq"><i>(\d+)</i>', h)
    assert nums == [str(i) for i in range(1, 9)]


