"""籌碼雷達（arm/lab/）——解析、帳本口徑、指標、頁面安全性。全部離線、不打網路。"""
from __future__ import annotations

from pathlib import Path

from arm.lab import backtest, ledger, market, page, store, ta


# ── 官方端點解析（格式取自 2026-10-14 CI 探針實測） ──────────────────────

def test_tpex_insti_flat_headers_use_verified_columns():
    """櫃買新站表頭沒有分組前綴（7 組重複「買進/賣出/買賣超股數」）→ 依驗證欄序。"""
    row = ["00411A", "主動統一前沿科技", "798,100", "2,808,000", "-2,009,900", "0", "0", "0",
           "798,100", "2,808,000", "-2,009,900", "0", "0", "0", "0", "0", "0", "2,956,000",
           "9,478,904", "-6,522,904", "2,956,000", "9,478,904", "-6,522,904", "-8,532,804"]
    fields = ["代號", "名稱"] + ["買進股數", "賣出股數", "買賣超股數"] * 7 + ["三大法人買賣超股數合計"]
    out = market.parse_tp_insti({"tables": [{"fields": fields, "data": [row]}]})
    f, t, d = out["00411A"]
    assert (f, t, d) == (-2009900, 0, -6522904)
    assert f + t + d == -8532804                    # 與三大法人合計欄自洽


def test_margin_takes_first_and_second_balance_columns():
    doc = {"tables": [{"fields": ["代號", "名稱", "買進", "賣出", "現金償還", "前日餘額", "今日餘額",
                                  "次一營業日限額", "買進", "賣出", "現券償還", "前日餘額", "今日餘額"],
                       "data": [["2330", "台積電", "1", "1", "0", "20,000", "32,869", "9", "0", "0", "0",
                                 "20", "23"]]}]}
    assert market.parse_margn(doc) == {"2330": [32869, 23]}


def test_sbl_uses_lending_balance_not_short_balance():
    fields = ["代號", "名稱", "前日餘額", "賣出", "買進", "現券", "今日餘額", "次一營業日限額",
              "前日餘額", "當日賣出", "當日還券", "當日調整", "當日餘額", "次一營業日可限額"]
    doc = {"fields": fields, "data": [["2330", "台積電", "1", "1", "1", "0", "310", "9",
                                       "1", "1", "1", "0", "12,031,514", "9"]]}
    assert market.parse_sbl(doc) == {"2330": 12031514}


def test_mi_index_extracts_taiex_and_skips_warrants():
    doc = {"tables": [
        {"fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "48,341.31"]]},
        {"fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價",
                    "最低價", "收盤價"],
         "data": [["2330", "台積電", "40,796,261", "1", "101,920,437,251", "2,500.00", "2,510.00",
                   "2,490.00", "2,490.00"],
                  ["030001", "某權證", "1", "1", "1", "1", "1", "1", "1"]]}]}
    q, idx = market.parse_mi_index(doc)
    assert idx == {"taiex": 48341.31}
    assert set(q) == {"2330"} and q["2330"][3] == 2490.0


def test_tdcc_big_holder_levels():
    txt = ("資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%\n"
           "20261008,2330,12,10,1,1.10\n20261008,2330,15,1500,1,84.78\n"
           "20261008,2330,17,3007088,1,100.00\n")
    iso, out = market.parse_tdcc(txt)
    assert iso == "2026-10-08"
    assert out["2330"] == [84.78, 85.88, 3007088]


# ── 帳本口徑 ─────────────────────────────────────────────────────────

def _pos(d, etf, h):
    return (d, {"etf": {etf: {"h": {c: [s, 1.0] for c, s in h.items()}}}})


def _px(table):
    return lambda c, d: table.get((c, d))


def test_creation_flow_is_not_counted_as_conviction():
    """申購讓全部持股 ×1.1 → 不是看好；只有額外多買的那檔才是真加碼。"""
    base = {f"{1000 + i}": 10000.0 for i in range(10)}
    after = {c: s * 1.1 for c, s in base.items()}
    after["1000"] = 10000 * 1.3
    L = ledger.build([_pos("2026-10-01", "X", base), _pos("2026-10-02", "X", after)],
                     _px({}))
    kinds = {e.code: e.kind for e in L.events if e.kind != ledger.HOLD}
    assert kinds == {"1000": ledger.ADD}
    ev = next(e for e in L.events if e.code == "1000")
    assert round(ev.conv) == 2000                  # 13000 − 10000×1.1
    assert abs(L.flows[("X", "2026-10-02")] - 1.1) < 1e-9


def test_average_cost_new_partial_sell_and_exit():
    px = _px({("2330", "2026-10-02"): (100.0, 100.0), ("2330", "2026-10-03"): (120.0, 120.0),
              ("2330", "2026-10-06"): (90.0, 90.0)})
    filler = {f"{1100 + i}": 5000.0 for i in range(6)}           # 讓申贖倍率估得出 1.0
    seq = [_pos("2026-10-01", "A", dict(filler)),
           _pos("2026-10-02", "A", {**filler, "2330": 1000.0}),
           _pos("2026-10-03", "A", {**filler, "2330": 3000.0}),
           _pos("2026-10-06", "A", {**filler, "2330": 1500.0})]
    L = ledger.build(seq, px)
    P = L.pos[("A", "2330")]
    # 建倉 1000@100 → 加碼 2000@120 → 平均 113.33；減碼 1500 不改平均
    assert P.first == "2026-10-02" and P.exact and P.quality == "A"
    assert abs(P.avg - (1000 * 100 + 2000 * 120) / 3000) < 1e-6
    assert P.shares == 1500
    assert P.realized < 0                          # 90 賣出低於平均成本
    L2 = ledger.build(seq + [_pos("2026-10-07", "A", dict(filler))], px)
    assert L2.pos[("A", "2330")].shares == 0
    assert any(e.kind == ledger.EXIT for e in L2.events)


def test_capital_reduction_is_corporate_action_not_selling():
    """減資一半：兩檔 ETF 股數同時 ×0.5、股價 ×2 → 公司行動，不記減碼。"""
    filler = {f"{1200 + i}": 8000.0 for i in range(6)}
    px = _px({("2603", "2026-10-01"): (50.0, 50.0), ("2603", "2026-10-02"): (100.0, 100.0)})
    seq = []
    for etf in ("A", "B"):
        seq.append(("2026-10-01", {"etf": {etf: {"h": {**{c: [s, 1] for c, s in filler.items()},
                                                       "2603": [4000, 1]}}}}))
        seq.append(("2026-10-02", {"etf": {etf: {"h": {**{c: [s, 1] for c, s in filler.items()},
                                                       "2603": [2000, 1]}}}}))
    merged: dict[str, dict] = {}
    for d, doc in seq:
        merged.setdefault(d, {"etf": {}})["etf"].update(doc["etf"])
    L = ledger.build(sorted(merged.items()), px, cal={"2026-10-01": 0, "2026-10-02": 1})
    assert ("2026-10-02", "2603", 0.5) in L.ca
    assert not [e for e in L.events if e.code == "2603" and e.kind in (ledger.CUT, ledger.EXIT)]
    assert abs(L.pos[("A", "2603")].avg - 100.0) < 1e-6   # 每股成本 50 → 100


def test_unpriced_start_is_priced_on_first_day_with_a_price():
    """首日缺價格的部位不以 0 元入帳：先記待補，第一個有價格的日子按當天均價補入。
    2026-10-14 村田製作所：海外 ETF 缺首日揭露價，舊版當 0 元入帳 → 估計成本 2,078（實際約 7,900）。"""
    filler = {f"{1300 + i}": 6000.0 for i in range(6)}
    px = _px({("6981 JP", "2026-10-02"): (200.0, 200.0), ("6981 JP", "2026-10-03"): (210.0, 210.0)})
    seq = [_pos("2026-10-01", "A", {**filler, "6981 JP": 1000.0}),       # 無價格
           _pos("2026-10-02", "A", {**filler, "6981 JP": 1500.0}),       # 買 500 @200
           _pos("2026-10-03", "A", {**filler, "6981 JP": 1000.0})]       # 賣 500 @210
    P = ledger.build(seq[:1], px).pos[("A", "6981 JP")]
    assert P.pend == 1000 and P.avg is None
    P = ledger.build(seq, px).pos[("A", "6981 JP")]
    assert P.pend == 0 and abs(P.avg - 200.0) < 1e-9 and P.shares == 1000
    assert abs(P.realized - 500 * 10) < 1e-6
    assert P.quality == "B"                         # 觀測起點就持有 → 頁面主動成本不計


def test_active_cost_counts_only_positions_built_during_observation():
    """主動成本只算觀測期內新建倉（品質 A）的主動 ETF 部位；舊部位、被動 ETF、缺價格部位都不計。"""
    from arm.lab import analyze
    act, pas = {"k": "a"}, {"k": "p"}
    a1 = ledger.Pos(shares=1000, cost=100_000, quality="A")
    a2 = ledger.Pos(shares=3000, cost=360_000, quality="A")
    old = ledger.Pos(shares=50_000, cost=2_500_000, quality="B")      # 起點價 50：不是真實買價
    unpriced = ledger.Pos(shares=9000, cost=0.0, quality="A", pend=9000)
    passive = ledger.Pos(shares=8000, cost=400_000, quality="A")
    cost, n = analyze.active_cost([(act, a1), (act, a2), (act, old), (act, unpriced), (pas, passive)])
    assert n == 2 and abs(cost - 460_000 / 4000) < 1e-9
    assert analyze.active_cost([(act, old)]) == (None, 0)


def test_unpriced_add_does_not_dilute_average_cost():
    """部位中途某天缺價格的加碼：先記待補，不拉低平均成本；隔天有價格再按當天均價補入。"""
    filler = {f"{1400 + i}": 6000.0 for i in range(6)}
    px = _px({("2330", "2026-10-01"): (100.0, 100.0), ("2330", "2026-10-03"): (130.0, 130.0)})
    seq = [_pos("2026-10-01", "A", {**filler, "2330": 1000.0}),
           _pos("2026-10-02", "A", {**filler, "2330": 2000.0}),          # 缺價格
           _pos("2026-10-03", "A", {**filler, "2330": 2000.0})]
    L = ledger.build(seq[:2], px)
    P = L.pos[("A", "2330")]
    assert P.pend == 1000 and abs(P.avg - 100.0) < 1e-9                # 舊版：100,000 ÷ 2,000 ＝ 50
    P = ledger.build(seq, px).pos[("A", "2330")]
    assert P.pend == 0 and abs(P.avg - (1000 * 100 + 1000 * 130) / 2000) < 1e-9


# ── 技術指標 ─────────────────────────────────────────────────────────

def test_indicators_basic_properties():
    c = [100 + (i % 7) - 3 + i * 0.2 for i in range(80)]
    h = [x + 1 for x in c]
    l = [x - 1 for x in c]
    assert ta.sma([1, 2, 3, None, 4], 3) == [None, None, 2.0, None, 3.0]
    r = ta.rsi(c)
    assert all(v is None or 0 <= v <= 100 for v in r)
    K, D = ta.kd(h, l, c)
    assert all(v is None or 0 <= v <= 100 for v in K + D)
    a = ta.atr(h, l, c)
    assert ta.last(a) > 0
    dif, dea, hist = ta.macd(c)
    assert ta.last(hist) is not None


def test_backtest_enters_next_open_and_charges_costs():
    S = {"c": [100, 100, 110, 110, 110, 110, 110], "o": [100, 105, 105, 105, 105, 105, 105]}
    idx = [1000] * 7
    r = backtest._ret(S, idx, 0, 5)
    assert abs(r["r"] - (110 / 105 - 1 - backtest.COST)) < 1e-12   # t+1 開盤進場、不是 t 收盤
    assert abs(r["g"] - 0.05) < 1e-12


# ── 分片與頁面 ───────────────────────────────────────────────────────

def test_store_write_is_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    doc = {"b": 1, "a": [1, 2, "台積電"]}
    assert store.write("mkt", "2026-10-13", doc) is True
    assert store.write("mkt", "2026-10-13", dict(reversed(list(doc.items())))) is False
    assert store.read("mkt", "2026-10-13") == doc


def test_page_escapes_script_close_and_is_deterministic():
    data = {"asof": {"pos": "2026-10-13"}, "etfs": {}, "rows": [
        {"c": "9999", "n": "</script><b>壞</b>", "m": "tw", "sg": [], "hd": []}],
        "ser": {}, "sigdef": {}, "risk": [], "stats": {}, "iss": {}, "iev": {}, "iow": {}, "dates": []}
    a, b = page.render(data), page.render(data)
    assert a == b
    blob = a.split('id="labdata">', 1)[1].split("</script>", 1)[0]
    assert "</script" not in blob and "<\\/script>" in blob


def test_page_has_no_banned_words():
    from arm.lab import analyze
    banned = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "建議買賣", "建議買",
              "建議賣", "目標價", "零風險", "無風險", "穩賺不賠")
    from arm.lab import growth, hdflow, strategy
    from arm.lab import advice
    st_txt = "".join(str(v) for x in strategy.STRATEGIES + [strategy.S3, growth.S5, hdflow.ALERT] + strategy.TW50_VERS
                     for k, v in x.items() if k in ("name", "kind", "basis", "risk", "rule", "buy", "sell", "pass"))
    st_txt += "".join(t[2] for t in hdflow.TESTS) + str(advice.RULE) + advice.RULE_STOP + str(advice.LABEL)
    from arm.lab import v3live                                       # 回測方法 v3（2026-10-15）：評級、成本、規則、名稱
    st_txt += str(advice.RULE3) + advice.PAY3 + advice.COST3 + str(advice.V3_RULES) + str(advice.BUCKET_TXT) + \
        str(advice.V3_HOLD) + str(v3live.LIVE) + str(advice.HOW) + str(advice.HOLD) + str(advice.SELL)
    from arm.lab import packtest                                     # 資料包策略（2026-10-15）：規則、未採用清單、試過的做法
    st_txt += str(packtest.PACK) + str(packtest.SKIPPED) + "".join(
        str(x.get("tried")) for x in strategy.STRATEGIES + strategy.TW50_VERS + [growth.S5, hdflow.ALERT])
    from pathlib import Path
    from arm.lab import valog                                        # 版面 v4：下一批說明、驗證事件與推播文字
    st_txt += str(advice.NEXT_TXT) + Path(valog.__file__).read_text("utf-8")
    text = page._HTML + page._JS + "".join(n + d for n, d in analyze.SIG_DEF.values()) + st_txt
    assert not [w for w in banned if w in text]


def test_page_layout_v4_tabs_opp_first_and_backend():
    """分頁（2026-10-23 起，docs/lab_ia_v5_plan.md 第 18 節）：同一頁兩種身分——
    配置（台股｜美股｜策略｜個股；一打開是台股）與研究紀錄（個股策略｜總經策略｜後台＋名詞，從 x9r.html 進來）。
    原「機會」「策略」兩頁＝研究紀錄的個股策略「這一期」「規則與成績」；頁首的目的句拿掉。"""
    import re
    tabs = re.findall(r'<a data-t="(\w+)" data-p="(\w+)"(?: hidden)?>([^<]+)</a>', page._HTML)
    assert tabs == [("tw", "pick", "台股"), ("us", "pick", "美股"), ("tool", "pick", "個股"),            # 2026-10-28 起選股（docs/lab_pick_page_plan.md）
                    ("stg", "r", "個股策略"), ("mac", "r", "總經策略"), ("plan", "r", "交易計畫"), ("strat", "r", "全部策略")]
    assert 'id="glb"' in page._HTML and "說明</a>" not in page._HTML
    assert '<a class="vlb" data-t="bo" data-p="r" hidden>後台</a><a class="glb" id="glb" data-p="r" hidden>' in page._HTML
    assert 'class="purp"' not in page._HTML and "const PURP=" not in page._JS
    assert "const S={tab:'stk'," in page._JS and "go(v,at);if(gl)openGl();}" in page._JS
    js_views = re.search(r"const VIEWS=\{([^}]*)\}", page._JS).group(1)
    assert [k.split(":")[0] for k in js_views.split(",")] == ["tw", "us", "stk", "chip", "idx", "opp", "st", "mac", "macst", "plan", "strat", "bo"]
    tabg = re.search(r"const TABG=\{([^}]*)\}", page._JS).group(1)
    assert dict(x.split(":") for x in tabg.replace("'", "").split(",")) == {
        "tw": "tw", "us": "us", "stk": "tool", "chip": "tool", "idx": "tool",
        "opp": "stg", "st": "stg", "mac": "mac", "macst": "mac", "plan": "plan", "strat": "strat", "bo": "bo"}
    for k in ("today", "iss", "sig", "val"):                                 # 舊分頁已併入機會、籌碼、後台
        assert f'data-t="{k}"' not in page._HTML and f'data-go="{k}"' not in page._JS, k


def test_opp_strategy_chip_backend_v4_structure():
    """版面 v4：機會＝摘要（含時間表）→ 推薦策略卡（做法／隱含獲利／現在／下一批）→ 避開；
    策略＝比較表（推薦順序）→ 各策略說明 → 部位；籌碼＝資金地圖、重點、買賣、新建倉、投信（今日訊號、風險提醒 2026-10-23 拿掉）；
    後台＝今天的驗證、前瞻紀錄、策略健檢與改良（2026-10-16）、事件紀錄 → 評級規則、評級總表、各策略依據、全部策略總表
    → 訊號成績 → 換股研究 → 更新時程。"""
    js = page._JS
    assert "h+=bookSec()+(ADV.book||[]).map(stCard).join('')+posSec();" in js
    assert ("h+=boToday()+boFwd()+hlSec()+boHist()+valRule()+gradeSec()+valSecs()+bt3Sec()+sigAllSec()+studySec(I.study)+"
            "hdStudySec(I.hd)+hdFlowSec(I.hd)+hdPreSec(I.hd)+boSched();") in js
    assert "sec('bo-hl'" in js and "function hlDet(" in js
    for k in ("sec('o-sum'", "sec('o-'+c.k", "sec('o-avoid'", "sec('st-book'", "sec('st-pos'", "sec('val-rule'", "sec('val-grade'",
              "sec('bo-today'", "sec('bo-fwd'", "sec('bo-hist'", "sec('bo-sig'", "sec('bo-sched'",
              "sec('c-lead'", "sec('c-flow'", "sec('c-new'", "sec('c-iss'",
              "valSec('s1'", "valSec('s3'", "valSec('hd'", "valSec('s5'", "valSec(k,V3NAV[k]||L.name", "function valSecs(",
              "ADV.grades3", "ADV.opp", "['做法',", "`隱含獲利${gi('隱含獲利')}`", "['現在',", "['下一批',",
              "['結論',", "['怎麼做',", "['過去成績',", "['風險',", "['評級',", "['評級依據',",
              "function yearTbl(", "function acurveChart(", "function oCard(", "function oTl(", "function stCardSec(",
              "data-go=\"bo\" data-at=\"val-", "data-go=\"st\" data-at=\"st-", "data-go=\"opp\" data-at=\"o-",
              "'推薦順序':", "'事後驗證':", "'隱含獲利':"):
        assert k in js, k
    for k in ("function calEv(", "function expTxt(", "function calLine(", "function vToday(", "function vSig(", "function vIss(",
              "function vVal(", "sec('st-cal'", "sec('st-avoid'", "sec('t-", "function nowSec(", "function pickBlocks(",
              "function pickCard(", "function stSecs(", "function riskSec(", "sec('st-now'", "sec('st-grade'", "sec('st-bt3'",
              "sec('c-sig'", "sec('c-risk'", "function sigTodaySec(", "function sjTxt(", "function hdRisk("):   # 籌碼頁的今日訊號、風險提醒 2026-10-23 拿掉
        assert k not in js, k
    # 機會、策略兩頁不出現驗證用語（使用者：驗證跟我沒關係，切開來）
    import re
    seg = js.split("/* ---------- 機會（首頁，版面 v4", 1)[1].split("*/", 1)[1].split("/* ---------- 後台（頂欄小字", 1)[0]
    op = re.sub(r"/\*.*?\*/", "", seg, flags=re.S)
    assert "function vOpp(" in op and "function vSt(" in op
    for w in ("t 值", "樣本外", "樣本內", "穩健度", "參數鄰近", "因子檢定", "同一批股票"):
        assert w not in op, w
    assert not re.search(r"(?<![\w])tT\(", op)                             # t 值格式化只在後台用
    for k in ("在賭什麼", "為什麼有效", "會失效", "s4", "群益新建倉"):           # 舊四小標與群益策略已移除
        assert k not in js, k
    assert "c-cost" not in js and "costSec" not in js
    assert "'成本品質'" not in js                      # 舊部位成本不顯示，不再需要 A／B 品質說明


def test_stock_table_views_stay_narrow():
    """個股表三個視角（ETF 動向／法人籌碼／技術面），每個視角連同股票、收盤兩欄 ≤9 欄、欄名都有 ⓘ。"""
    import re
    assert "const VW={etf:'ETF 動向',chip:'法人籌碼',ta:'技術面'}" in page._JS
    block = page._JS.split("const CV={", 1)[1].split("};", 1)[0]
    views = re.findall(r"(\w+):\[(.*?)\n \]", block, re.S)
    assert [v for v, _ in views] == ["etf", "chip", "ta"]
    for v, body in views:
        cols = re.findall(r"\{k:'(\w+)'", body)
        assert 2 + len(cols) <= 9, (v, cols)
        assert body.count("g:'") >= len(cols) - 1, v     # 訊號欄以外都接名詞辭典


def test_asof_line_merges_same_day_and_flags_lagging():
    data = {"asof": {"pos": "2026-10-13", "px": "2026-10-13", "chip": "2026-10-13",
                     "margin": "2026-10-12", "tdcc": "2026-10-08"},
            "etfs": {"A": {"d": "2026-10-13"}, "B": {"d": "2026-10-12"}}}
    s = page.asof_line(data)
    assert s.startswith("資料日 10/13")
    assert "融資券 10/12" in s and "價量" not in s and "法人" not in s
    assert "集保 10/8（每週）" in s and "ETF 揭露 1/2 檔到 10/13" in s
    assert page.asof_line({}) == "尚無資料"


def test_entrance_is_low_key_footer_link_only():
    """入口只在頁尾、不進導覽列（使用者：沒那麼好找到就好）；點了先到市場頁・台股（2026-10-18 使用者：先出現景氣頁面；
    2026-10-23 IA v5 起景氣頁＝市場頁，頂欄「市場｜配置」的第一格）。"""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1].joinpath("arm", "fund_dashboard.py").read_text("utf-8")
    assert src.count('href="x9m.html"') == 1 and 'href="x9.html"' not in src
    foot = src.split('<div class="foot">', 1)[1].split("</div>", 1)[0]
    assert 'href="x9m.html"' in foot


# ── 指數調整（臺灣50）與擴充 ETF ─────────────────────────────────────

def test_tw50_buffer_rule_and_fixed_count():
    from arm.lab import indexes
    ranked = [(f"{1000 + i}", 1e12 - i * 1e9, 100.0) for i in range(120)]
    cons = {f"{1000 + i}" for i in range(50)}
    cons -= {"1039"}                      # 第 40 名不在成分股 → 必須納入
    cons |= {"1065"}                      # 第 66 名在成分股 → 必須刪除
    adds, dels = indexes.tw50_select(ranked, cons)
    assert "1039" in adds and "1065" in dels
    assert len(cons) - len(dels) + len(adds) == 50
    # 41～60 名的成分股留任（緩衝區）
    cons2 = {f"{1000 + i}" for i in range(40)} | {f"{1000 + i}" for i in range(45, 55)}
    adds2, dels2 = indexes.tw50_select(ranked, cons2)
    assert not dels2 and not adds2


def test_tw50_common_stock_filter():
    from arm.lab import indexes
    assert indexes._common_tw("2330")
    assert not indexes._common_tw("0050")       # ETF
    assert not indexes._common_tw("2881A")      # 特別股
    assert not indexes._common_tw("9105")       # TDR


def test_tw50_top_half_rounds_up_and_ranks_by_momentum():
    """選股定案（2026-10-14 使用者）：漲勢前一半、無條件進位；只有 1 檔就是它；沒有漲幅資料的排最後。"""
    from arm.lab import indexes
    mom = {"a": 0.10, "b": 0.50, "c": None, "d": 0.30}
    assert indexes.top_half(["a", "b", "c", "d"], mom) == {"b", "d"}
    assert indexes.top_half(["a", "b", "c"], mom) == {"b", "a"}
    assert indexes.top_half(["c"], mom) == {"c"} and indexes.top_half([], mom) == set()


def test_tw50_skips_stocks_not_yet_listed_at_cutoff():
    """資料截止日時還沒上市（興櫃轉上市）的股票沒有資格，由下一順位遞補（鴻勁 2025-09／12 誤判的教訓）。"""
    from arm.lab import indexes
    ranked = [(f"{1000 + i}", 1e12 - i * 1e9, 100.0) for i in range(120)]
    cons = {f"{1000 + i}" for i in range(50)} - {"1012"}
    ranked.insert(5, ("7769", 1e12 - 4.5e9, 100.0))
    cons -= {"1049"}
    listed = {"7769": "2025-11-27"}
    skip = indexes.not_listed(ranked, cons, listed, "2025-11-24")
    assert skip == {"7769"}
    adds, _ = indexes.tw50_select(ranked, cons, skip)
    assert "7769" not in adds and "1012" in adds
    assert indexes.not_listed(ranked, cons, listed, "2026-02-23") == set()      # 上市後下一次就有資格


def _tw50_fake(cal, series, idx, io=None):
    class _D:
        pass
    D = _D()
    D.cal, D.T = cal, len(cal)
    D.ix = {d: i for i, d in enumerate(cal)}
    D.series = lambda c: series[c]
    D.taiex = lambda: idx
    D.taiex_open = lambda: io or [None] * len(cal)
    return D


def test_tw50_version_trade_windows_and_states():
    """卡位版：截止日隔天開盤進、生效前一天收盤出；公告沒納入 → 公告後第一天開盤出；資料未到＝待進場／持有中。"""
    from arm.lab import tw50study as TS
    cal = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-12-04", "2026-12-07", "2026-12-17", "2026-12-18"]
    S = {"X": {"o": [None, 100, 101, 104, 103, 110, 111], "c": [99, 100, 102, 105, 104, 112, 113]}}
    idx = [1000.0, 1000, 1010, 1020, 1015, 1030, 1040]
    io = [None, 1000.0, 1005, 1018, 1016, 1028, 1035]
    D = _tw50_fake(cal, S, idx, io)
    P = TS._Px(D)
    t = TS._trade(D, P, "X", 1, "2026-11-24", "2026-12-17", False, "生效前一天出", {"c": "X"})
    assert t["st"] == "closed" and t["entry"] == 100 and t["exit"] == 112 and t["held"] == 5
    assert abs(t["r"] - round((112 / 100 - 1 - TS.COST) * 100, 2)) < 1e-9
    assert abs(t["x"] - round((112 / 100 - 1 - TS.COST - (1030 / 1000 - 1)) * 100, 2)) < 1e-9
    t2 = TS._trade(D, P, "X", 1, "2026-11-24", "2026-12-07", True, "公告未納入・隔日開盤出", {"c": "X"})
    assert t2["exit"] == 103 and t2["held"] == 3 and abs(t2["r"] - round((103 / 100 - 1 - TS.COST) * 100, 2)) < 1e-9
    D2 = _tw50_fake(cal[:3], {"X": {k: v[:3] for k, v in S["X"].items()}}, idx[:3], io[:3])
    t3 = TS._trade(D2, TS._Px(D2), "X", 1, "2026-11-24", "2026-12-17", False, "生效前一天出", {"c": "X"})
    assert t3["st"] == "open" and t3["now"] == 102 and t3["out"] == "2026-12-17"
    D3 = _tw50_fake(cal[:1], {"X": {k: v[:1] for k, v in S["X"].items()}}, idx[:1], io[:1])
    t4 = TS._trade(D3, TS._Px(D3), "X", None, "2026-11-24", "2026-12-17", False, "生效前一天出", {"c": "X"})
    assert t4["st"] == "cand" and t4["ent"] == "2026-11-24"


def test_tw50_td_shift_follows_official_calendar():
    from arm.lab import tw50study as TS
    assert TS.td_shift("2026-11-23", 1) == "2026-11-24"
    assert TS.td_shift("2026-12-18", -1) == "2026-12-17"
    assert TS.td_shift("2026-10-12", -1) == "2026-10-08"            # 10/9 國慶補假＋週末
    assert TS.td_shift("2026-12-04", 1) == "2026-12-07"             # 週五公告 → 下週一


def test_tw50_spearman_basic():
    from arm.lab import tw50study as TS
    a = [1, 2, 3, 4, 5, 6]
    assert TS._spearman(a, [10, 20, 30, 40, 50, 60]) == (1.0, 6)
    assert TS._spearman(a, [6, 5, 4, 3, 2, 1]) == (-1.0, 6)
    assert TS._spearman(a[:5], a[:5])[0] is None                      # 少於 6 檔不算
    assert TS._spearman([1, 1, 2, 3, 4, 5], [1, 2, 3, 4, 5, None])[1] == 5


def test_tw50_control_respects_stock_level_effective_date(monkeypatch):
    """對照組（官方名單全部）：個股生效日延後以個股為準；資料還沒到生效日的刪除股＝待進場，不拿最新收盤冒充。"""
    from arm.lab import indexes, strategy
    cal = ["2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13"]
    S = {c: {"o": [10.0] * 7, "c": [10.0, 10, 10, 10, 11, 12, 13]} for c in ("1111", "2222", "3333")}
    D = _tw50_fake(cal, S, [1000.0] * 7, [1000.0] * 7)
    cfg = {"indexes": {"tw50": {"history": [{"review": "2026-03", "announce": "2026-03-06", "effective": "2026-03-11",
                                             "adds": ["1111", "2222"], "dels": ["3333"],
                                             "eff_override": {"2222": "2026-03-13"}}]}}}
    monkeypatch.setattr(indexes, "load_cfg", lambda: cfg)
    trs = {t["c"]: t for t in strategy.tw50_trades(D, [1000.0] * 7, [1000.0] * 7, {}, cal[-1])}
    assert trs["1111"]["exit"] == 11 and trs["1111"]["held"] == 3
    assert trs["2222"]["exit"] == 13 and trs["2222"]["d"] == "2026-03-13"
    assert trs["3333"]["st"] == "open" and trs["3333"]["entry"] == 11            # 生效日收盤承接，5 日後還沒到
    D2 = _tw50_fake(cal[:4], {c: {k: v[:4] for k, v in x.items()} for c, x in S.items()}, [1000.0] * 4, [1000.0] * 4)
    trs2 = {t["c"]: t for t in strategy.tw50_trades(D2, [1000.0] * 4, [1000.0] * 4, {}, cal[3])}
    assert trs2["3333"]["st"] == "cand" and trs2["1111"]["st"] == "open"


def test_tw50_by_review_drops_two_largest_gaps_between_versions():
    """「成績集中在少數幾次」由資料算：扣掉兩版差距最大的 2 次後重算平均，並附公告後第一天開盤跳空。"""
    from arm.lab import strategy
    cal = ["2026-03-06", "2026-03-09", "2026-06-05", "2026-06-08"]
    D = _tw50_fake(cal, {"A": {"o": [None, 90.0, None, 95.0], "c": [100.0, 100, 100, 100]}}, [1000.0] * 4)
    pl = [{"review": r, "announce": a, "pick_b": ["A"] if a else []}
          for r, a in (("2025-12", None), ("2026-03", "2026-03-06"), ("2026-06", "2026-06-05"), ("2025-09", None))]
    tr = lambda r, v: {"review": r, "r": v, "st": "closed", "d": "2025-01-01"}
    V = {"early": [tr("2025-12", 5.0), tr("2026-03", 10.0), tr("2026-06", 4.0), tr("2025-09", 3.0)],
         "post": [tr("2025-12", 4.0), tr("2026-03", 30.0), tr("2026-06", 30.0), tr("2025-09", 1.0)]}
    rows, sens = strategy._tw50_by_review(D, pl, V, [])
    assert [r[0] for r in rows] == ["2025-12", "2026-03", "2026-06", "2025-09"]
    assert rows[1][4] == -10.0 and rows[2][4] == -5.0 and rows[0][4] is None
    assert sorted(sens["revs"]) == ["2026-03", "2026-06"] and sens["early"] == 4.0 and sens["post"] == 2.5
    assert sens["n_left"] == 2 and sens["early_all"] == 5.5 and sens["post_all"] == 16.25


def test_tw50_early_basket_cutoff_check_and_topup():
    """提前卡位：早買的股票截止日名單沒有 → 截止日隔天開盤賣；名單上有的抱到生效前一天；沒買到的確定納入股補位。"""
    from arm.lab import tw50study as TS
    cal = ["2026-10-16", "2026-10-19", "2026-11-23", "2026-11-24", "2026-12-04", "2026-12-07", "2026-12-17", "2026-12-18"]
    S = {"A": {"o": [None, 100.0, None, 120.0, None, None, None, None], "c": [99.0, 101, 118, 121, 125, 126, 130, 128]},
         "C": {"o": [None, 50.0, None, 47.0, None, None, None, None], "c": [50.0, 50, 48, 47, 46, 46, 45, 45]},
         "B": {"o": [None, 80.0, None, 90.0, None, None, None, None], "c": [80.0, 82, 88, 91, 95, 96, 99, 97]}}
    D = _tw50_fake(cal, S, [1000.0] * 8, [1000.0] * 8)
    p = {"review": "2026-12", "cutoff": "2026-11-23", "frozen": True, "official": True, "pred": ["A", "B"],
         "act": ["A", "B"], "ic": 2, "a_in": "2026-11-24", "b_in": "2026-12-07", "out": "2026-12-17", "out_c": {},
         "e_sig": "2026-10-16", "e_in": "2026-10-19", "e_t": 0, "pick_e": ["A", "C"], "pick_t": ["B"],
         "mom": {}, "mom_e": {}}
    trs = {t["c"]: t for t in TS.early_trades(D, TS._Px(D), p, {})}
    assert trs["A"]["entry"] == 100 and trs["A"]["exit"] == 130 and trs["A"]["tag"] == "早"
    assert trs["C"]["exit"] == 47 and trs["C"]["why"].startswith("截止日名單沒有")       # 截止日隔天開盤賣
    assert trs["B"]["entry"] == 90 and trs["B"]["exit"] == 99 and trs["B"]["tag"] == "補"
    p2 = dict(p, frozen=False, official=False, pred=None, act=None, pick_t=[])           # 截止前：持有中
    D2 = _tw50_fake(cal[:2], {c: {k: v[:2] for k, v in x.items()} for c, x in S.items()}, [1000.0] * 2, [1000.0] * 2)
    t2 = {t["c"]: t for t in TS.early_trades(D2, TS._Px(D2), p2, {})}
    assert t2["A"]["st"] == "open" and t2["C"]["st"] == "open" and t2["A"]["now"] == 101


def test_tw50_card_has_versions_plan_and_research_section():
    """臺灣50 卡：三個版本並列（兩個新版本＋原官方名單對照）、下一次計畫；指數頁有換股研究段。"""
    from arm.lab import strategy
    from arm.lab import tw50study
    assert [v["k"] for v in strategy.TW50_VERS] == ["early", "post"]
    assert all(v["since"] == "2026-10-14" and v["ver"] == 1 and v["rule"] for v in strategy.TW50_VERS)
    assert (tw50study.EARLY_K, tw50study.EARLY_N, tw50study.EARLY_W) == (25, 4, 45)   # 使用者：3～4 檔、越早越好
    assert strategy.S3["name"] == "臺灣50 提前卡位"                     # 頁面只列一條策略（使用者：三個看不出差在哪）
    js = page._JS
    for k in ("function s3Now(", "function verCmp(", "三種做法比較", "function studySec(", "+studySec(I.study)+", "'idx-study'",
              "'漲勢前一半':", "'資料截止日':", "'估計權重':", "function earlyChart(", "提前幾天建倉"):
        assert k in js, k
    assert "sq('三個版本'" not in js


def test_index_reviews_config_is_well_formed():
    import json
    from pathlib import Path
    d = json.loads(Path(__file__).resolve().parents[1].joinpath("config", "index_reviews.json")
                   .read_text("utf-8"))
    assert d.get("as_of") and d["indexes"]
    for k, ix in d["indexes"].items():
        assert ix.get("name") and ix.get("etfs") and ix.get("rule"), k
        for h in ix.get("history") or []:
            assert h.get("src"), (k, h.get("review"))          # 每筆結果都要有來源
            for c in (h.get("adds") or []) + (h.get("dels") or []):
                assert len(c) == 4 and c.isdigit(), (k, c)


def test_extra_etf_candidates_filter():
    from arm.lab import collect
    items = [
        {"code": "0050", "aum": 9e11, "managementStyle": "passive", "name": "元大台灣50"},
        {"code": "009816", "aum": 2e11, "managementStyle": "passive", "name": "某台灣TOP50"},
        {"code": "00679B", "aum": 3e11, "managementStyle": "passive", "name": "某美債20年"},
        {"code": "00631L", "aum": 4e11, "managementStyle": "passive", "name": "某正2"},
        {"code": "00940", "aum": 1e11, "managementStyle": "passive", "name": "某高息"},
        {"code": "2330", "aum": 9e12, "name": "台積電"},
    ]
    out = collect.extra_candidates(items, tracked={"0050"})
    assert [x["code"] for x in out] == ["009816", "00940"]     # 依規模、排除已追蹤／債券／槓桿／個股


def test_weight_constant_trim_is_not_mistaken_for_capital_reduction():
    """單一 ETF 維持固定權重：股價隔數日漲 18%、股數減 15% → 是交易，不是減資（華邦電 8/5 實例）。"""
    filler = {f"{1300 + i}": 9000.0 for i in range(6)}
    px = _px({("2344", "2026-08-03"): (143.0, 143.0), ("2344", "2026-08-05"): (169.0, 169.0)})
    seq = [_pos("2026-08-03", "A", {**filler, "2344": 100000.0}),
           _pos("2026-08-05", "A", {**filler, "2344": 84700.0})]
    L = ledger.build(seq, px, cal={"2026-08-03": 0, "2026-08-04": 1, "2026-08-05": 2})
    assert not L.ca
    assert any(e.code == "2344" and e.kind == ledger.CUT for e in L.events)


def test_stock_dividend_credit_without_price_move_is_corporate_action():
    """配股入帳日股價不動、所有持有 ETF 同比例增加 4% → 公司行動，不是集體加碼（元大金 8/18 實例）。"""
    filler = {f"{1400 + i}": 9000.0 for i in range(6)}
    px = _px({("2885", "2026-08-17"): (40.0, 40.0), ("2885", "2026-08-18"): (40.2, 40.2)})
    merged: dict[str, dict] = {"2026-08-17": {"etf": {}}, "2026-08-18": {"etf": {}}}
    for etf in ("A", "B", "C"):
        merged["2026-08-17"]["etf"][etf] = {"h": {**{c: [s, 1] for c, s in filler.items()}, "2885": [100000, 1]}}
        merged["2026-08-18"]["etf"][etf] = {"h": {**{c: [s, 1] for c, s in filler.items()}, "2885": [104000, 1]}}
    L = ledger.build(sorted(merged.items()), px)
    assert {(d, c) for d, c, _ in L.ca} == {("2026-08-18", "2885")}
    assert not [e for e in L.events if e.code == "2885" and e.kind == ledger.ADD]


# ── 策略紙上交易 ─────────────────────────────────────────────────────

def _st_series(o, c, h=None, l=None):
    return {"o": o, "c": c, "h": h or [x and x * 1.01 for x in c], "l": l or [x and x * 0.99 for x in c]}


def test_s1_skips_gap_up_and_flat_open():
    from arm.lab import strategy
    st = next(s for s in strategy.STRATEGIES if s["key"] == "s1")
    idx = [1000.0] * 8
    S = _st_series([100, 101, 100, 100, 100, 100, 100, 100], [100] * 8)
    assert strategy._trade(st, "2330", 0, S, [2.0] * 8, idx, 8)["st"] == "skip"      # 開高
    S2 = _st_series([100, 100, 100, 100, 100, 100, 100, 100], [100] * 8)
    assert strategy._trade(st, "2330", 0, S2, [2.0] * 8, idx, 8)["st"] == "skip"     # 平盤也放棄


def test_s1_enters_gap_down_exits_on_hold_day_with_costs():
    from arm.lab import strategy
    st = next(s for s in strategy.STRATEGIES if s["key"] == "s1")
    idx = [1000.0, 1000, 1000, 1010, 1010, 1010]
    S = _st_series([100, 98, 99, 99, 99, 99], [100, 99, 100, 102, 102, 102])
    r = strategy._trade(st, "2330", 0, S, [2.0] * 6, idx, 6)
    assert r["st"] == "closed" and r["held"] == 3 and r["why"] == "到期"
    assert abs(r["r"] - round((102 / 98 - 1 - strategy.COST) * 100, 2)) < 1e-9
    assert abs(r["x"] - round((102 / 98 - 1 - strategy.COST - 0.01) * 100, 2)) < 1e-9


def test_s1_stop_loss_and_pending_candidate():
    from arm.lab import strategy
    st = next(s for s in strategy.STRATEGIES if s["key"] == "s1")
    idx = [1000.0] * 6
    S = _st_series([100, 98, 95, 95, 95, 95], [100, 96, 93, 95, 95, 95])
    r = strategy._trade(st, "2330", 0, S, [2.0] * 6, idx, 6)   # 停損＝98−4＝94，第 2 天收 93
    assert r["st"] == "closed" and r["why"] == "停損" and r["held"] == 2
    assert strategy._trade(st, "2330", 5, S, [2.0] * 6, idx, 6) is None              # 隔日資料未到＝候選


def test_strategy_dist_percentiles_and_stop_count():
    from arm.lab import strategy
    trs = [{"st": "closed", "entry": 100.0, "exit": 100.0 + g, "r": g - 0.585, "x": g - 1, "d": "2026-08-0%d" % (i + 1),
            "held": 3, "why": "停損" if g < -5 else "到期"} for i, g in enumerate([-8, -2, 0, 2, 4, 6, 10])]
    trs.append({"st": "skip", "why": "開高 +1.0%"})                     # 沒進場的不算
    d = strategy.dist(trs)
    assert d["n"] == 7 and d["p"][2] == 2.0 and d["stop"] == 1
    assert d["p"][1] < d["p"][2] < d["p"][3]
    assert d["mo"] == [["2026-08", 7, round(sum(g - 1 for g in [-8, -2, 0, 2, 4, 6, 10]) / 7, 2)]]
    assert strategy.dist([]) == {"n": 0}


def test_strategy_holding_scan_matches_scorecard_definition():
    """持有天數掃描與成績單同口徑：t+1 開盤進、t+h 收盤出、扣成本、對大盤同一時窗。"""
    from arm.lab import strategy
    S = _st_series([100, 98, 99, 99, 99], [100, 99, 101, 102, 103])
    idx = [1000.0, 1000, 1010, 1010, 1020]
    out = strategy.scan([("s", "開低", [("2330", 0)], lambda g: g < 0),
                         ("c", "開高", [("2330", 0)], lambda g: g >= 0)], lambda c: S, idx, None, 3)
    a, c = out["grp"]
    assert out["h"] == 3 and a["n"] == [1, 1, 1] and c["n"] == [0, 0, 0] and c["x"] == [None] * 3
    assert a["x"][1] == round((101 / 98 - 1 - strategy.COST - (1010 / 1000 - 1)) * 100, 2)
    assert a["w"][1] == 100


def test_trading_days_after_skips_weekends_and_official_holidays():
    from arm.lab import strategy
    assert strategy.trading_days_after("2026-10-08", 3) == ["2026-10-12", "2026-10-13", "2026-10-14"]  # 10/9 國慶補假
    assert strategy.trading_days_after("2026-10-14", 3) == ["2026-10-15", "2026-10-16", "2026-10-19"]


# ── 長線成長股：出場模擬 ─────────────────────────────────────────────

class _FakePanel:
    def __init__(self, o, c):
        self.T = len(c)
        self.s = {"X": {"o": o, "c": c, "h": c, "l": c}}
        self.ma60 = {"X": [None] * len(c)}
        self.ma120 = {"X": [None] * len(c)}


def test_growth_trailing_exit_locks_gain_and_initial_stop_caps_loss():
    from arm.lab import growth
    up = [100, 100] + [100 + 10 * i for i in range(1, 16)] + [150] * 5     # 漲到 250 後回落到 150
    P = _FakePanel(up, up)
    r = growth.simulate(P, "X", 0, init=0.20, trail=0.30, maxd=40)
    assert abs(r["r"] - (150 / 100 - 1 - 0.00585)) < 1e-9                 # 從 250 回落 >30% → 以 150 出
    down = [100, 100, 95, 85, 79, 70, 60] + [60] * 10
    P2 = _FakePanel(down, down)
    r2 = growth.simulate(P2, "X", 0, init=0.20, trail=0.30, maxd=40)
    assert r2["d"] == 4 and abs(r2["r"] - (79 / 100 - 1 - 0.00585)) < 1e-9  # 跌破 −20% 那天收盤出


def test_rev_available_respects_publication_lag():
    from arm.lab import growth
    rev = {"2025-08": 100.0, "2026-08": 130.0, "2025-09": 100.0, "2026-09": 150.0,
           **{f"2025-{m:02d}": 100.0 for m in range(1, 8)}, **{f"2026-{m:02d}": 120.0 for m in range(1, 8)}}
    yoy, _ = growth._rev_avail(rev, "2026-10-09")       # 9 月營收 10/10 前未必公布 → 用 8 月
    assert abs(yoy - 0.30) < 1e-9
    yoy2, _ = growth._rev_avail(rev, "2026-10-12")
    assert abs(yoy2 - 0.50) < 1e-9


def test_store_dates_handles_month_shards(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write("rev", "2026-09", {"s": {"2330": [1, 2, 3]}})
    store.write("mkt", "2026-10-13", {"q_tw": {}})
    assert store.dates("rev") == ["2026-09"] and store.load("rev")[0][0] == "2026-09"
    assert store.dates("mkt") == ["2026-10-13"]


def test_extra_etf_candidates_read_nested_latest_market_aum():
    """etfinfo 清單的規模在 latestMarket.aum（2026-10-14 正式環境首輪實測鍵名）。"""
    from arm.lab import collect
    items = [{"code": "0051", "name": "小檔", "managementStyle": "passive", "latestMarket": {"aum": 5e9}},
             {"code": "009816", "name": "大檔", "managementStyle": "passive", "latestMarket": {"aum": 2e11}},
             {"code": "00981A", "name": "主動大檔", "managementStyle": "active", "latestMarket": {"aum": 1e11}}]
    out = collect.extra_candidates(items, tracked=set())
    assert [x["code"] for x in out] == ["009816", "00981A", "0051"]
    assert out[1]["style"] == "a"


def test_shard_retention_covers_long_term_backtest():
    """長線回測（月選、12 個月前瞻＋120 日均線暖身）至少要兩年分片，保留天數不可再縮回 400。"""
    assert store.KEEP_DAYS >= 730


def test_series_out_exports_active_flow_not_etf_total():
    """個股走勢圖下方改畫「主動 ETF 每日真加減碼」：ETF 陸續進資料集會讓合計持股憑空跳增，不再輸出 et。"""
    from arm.lab import analyze
    T = analyze.CHART_N + 5
    S = {k: [100.0] * T for k in ("c", "o", "h", "l")}
    S["v"] = [5000.0] * T
    qa = [0.0] * T
    out = analyze._series_out(None, S, None, [None] * T, qa, True)
    assert "et" not in out and "qa" not in out                      # 全 0 不輸出
    qa[-1], qa[-3] = 12_400.0, -3_000.0                             # 股 → 張
    out = analyze._series_out(None, S, None, [None] * T, qa, True)
    assert len(out["qa"]) == analyze.CHIP_N and out["qa"][-1] == 12 and out["qa"][-3] == -3


def test_build_splits_series_into_side_file(tmp_path, monkeypatch):
    """個股走勢序列另存 x9s.json（開個股卡才載入）：頁面不含序列、版本號＝序列檔雜湊、檔案自帶日期軸；同資料重建零變更。"""
    import json as _json
    from arm.lab import analyze
    data = {"asof": {"pos": "2026-10-13"}, "etfs": {}, "dates": ["2026-10-08", "2026-10-13"],
            "rows": [{"c": "2330", "n": "台積電", "m": "tw", "sg": [], "hd": []}],
            "ser": {"2330": {"c": [2400.0, 2490.5], "qa": [0, 3]}}, "sigdef": {}, "risk": [],
            "stats": {}, "iss": {}, "iev": {}, "iow": {}}
    monkeypatch.setattr(analyze, "run", lambda **kw: data)
    html_p, ser_p = tmp_path / "x9.html", tmp_path / "x9s.json"
    assert page.build(out=html_p, out_ser=ser_p) is True
    blob = html_p.read_text("utf-8").split('id="labdata">', 1)[1].split("</script>", 1)[0]
    main = _json.loads(blob.replace("<\\/", "</"))
    assert "ser" not in main and main["dates"] == data["dates"]
    sj = ser_p.read_text("utf-8")
    assert main["serv"] == page._ver(sj)
    assert _json.loads(sj) == {"dates": data["dates"], "ser": {"2330": {"c": [2400, 2490.5], "qa": [0, 3]}}}
    assert page.build(out=html_p, out_ser=ser_p) is False


def test_workflows_commit_series_file_on_its_own_line():
    """三支會重建儀表板的 workflow 都要把 x9s.json 帶進 commit，且分開 add（缺檔時 git 會整行放棄，不可連累分片）。"""
    from pathlib import Path
    wf = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for name in ("daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"):
        lines = (wf / name).read_text("utf-8").splitlines()
        page_lines = [i for i, ln in enumerate(lines) if "dashboard/x9.html" in ln]
        assert page_lines, name
        for i in page_lines:
            assert "x9s.json" not in lines[i], name
            assert lines[i + 1].strip().startswith("git add -f dashboard/x9s.json"), (name, i)


def test_workflows_that_build_pages_install_numpy():
    """會重建儀表板的 workflow 都要裝 numpy（2026-10-21 踩坑：etf_holdings.yml 只裝 certifi，
    每班建頁時策略判定算不出來 → 機會頁推薦全空、景氣頁與訊號總覽不重建）。"""
    import re
    wf = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    builders = []
    for p in sorted(wf.glob("*.yml")):
        text = p.read_text("utf-8")
        if "gen_fund_dashboard.py" in text or "daily_fund.sh" in text:
            builders.append(p.name)
            pip = [ln for ln in text.splitlines() if "pip install" in ln]
            assert any(re.search(r"\bnumpy\b", ln) for ln in pip), p.name
    assert {"daily.yml", "afterhours_refresh.yml", "etf_holdings.yml"} <= set(builders)


# ── 高股息四檔（0056／00878／00919／00929）換股研究與預測（2026-10-14）────────────

def _hd_fake(cal, mkt, yh=None):
    class _D:
        pass
    D = _D()
    D.cal, D.T, D.mkt, D.yh = cal, len(cal), mkt, yh or {}
    D.ix = {d: i for i, d in enumerate(cal)}
    D.names = {}

    def quote(c, d):
        doc = D.mkt.get(d) or {}
        for part in ("q_tw", "q_tp"):
            q = (doc.get(part) or {}).get(c)
            if q and q[3]:
                return q
        y = (D.yh.get(c) or {}).get(d)
        return [y[0], y[1], y[2], y[3], y[4], None] if y else None
    D.quote = quote
    return D


def _hd_model(D, raw):
    from arm.lab.hdmodel import HD
    H = HD.__new__(HD)
    H.D, H.raw, H.approx, H.eps = D, raw, set(), {}
    H.iss_tw, H.iss_tp, H._ser, H._div = {}, {}, {}, {}
    return H


def test_hd_par_value_change_restates_prices_and_dividends():
    """面額十比一（寶雅 2026-07-30 實例）：相鄰兩日價格比超過 1.8 倍＝口徑改變，更早的價格與股利全部換到最新口徑
    （Yahoo 區段本來就是新口徑，接到官方舊價那天也會被接回來）。"""
    cal = ["2026-06-01", "2026-06-02", "2026-07-29", "2026-07-30", "2026-07-31"]
    q = lambda p: {"q_tw": {}, "q_tp": {"5904": [p, p, p, p, 1000, p * 1000]}}
    mkt = {"2026-06-02": q(570.0), "2026-07-29": q(720.0), "2026-07-30": q(72.0), "2026-07-31": q(73.0)}
    yh = {"5904": {"2026-06-01": [56.8, 56.8, 56.8, 56.8, 1000]}}
    D = _hd_fake(cal, mkt, yh)
    H = _hd_model(D, {"5904": [("2026-07-16", 25.5, None, False)]})
    s = H.ser("5904")
    assert [d for d, _ in s["jumps"]] == ["2026-06-02", "2026-07-30"]  # Yahoo→官方、面額變更各一次
    assert [round(x, 2) for x in s["c"]] == [57.0, 57.0, 72.0, 72.0, 73.0]   # 全部換成最新口徑
    assert abs(H.divs("5904")[0][1] - 2.55) < 1e-9                     # 舊股股利 25.5 → 新股 2.55
    assert abs(H.yld("5904", "2026-07-31") - 2.55 / 73.0) < 1e-9
    assert abs(H.mom("5904", 4, 3) - (73.0 / 57.0 - 1)) < 1e-9          # 動能跨過口徑改變也正確


def test_hd_dividend_rescaled_by_pre_ex_close_on_yahoo_days():
    """Yahoo 區段的價格已依日後面額變更還原，股利是「當時每股」→ 用證交所除權息前收盤價換算（可寧衛 8422 實例）。"""
    cal = ["2025-06-09", "2025-06-10", "2025-06-11"]
    yh = {"8422": {"2025-06-09": [19.1, 19.1, 19.1, 19.1, 100], "2025-06-10": [18.2, 18.2, 18.2, 18.2, 100],
                   "2025-06-11": [18.3, 18.3, 18.3, 18.3, 100]}}
    D = _hd_fake(cal, {}, yh)
    H = _hd_model(D, {"8422": [("2025-06-10", 9.94, 191.0, False)]})
    assert abs(H.divs("8422")[0][1] - 9.94 * 19.1 / 191.0) < 1e-9       # ≈ 0.994


def test_hd_trade_window_inferred_from_trust_flows():
    """被動買賣期間＝納入股投信買超（÷該檔區間最大）平均 ≥ 0.3 的連續交易日，容許中間 1 天低於門檻。"""
    from arm.lab import hdstudy as HS
    from datetime import date
    cal = [f"2026-06-{d:02d}" for d in range(1, 29) if date(2026, 6, d).weekday() < 5]
    buy = {"2026-06-10": 0.9, "2026-06-11": 1.0, "2026-06-12": 0.1, "2026-06-15": 0.8, "2026-06-16": 0.7}
    mkt = {d: {"i_tw": {c: [0, int(buy.get(d, 0.02) * 1e6), 0] for c in ("1111", "2222")}} for d in cal}
    D = _hd_fake(cal, mkt)
    w = HS.trade_window(D, {"adds": ["1111", "2222"]}, D.ix["2026-06-11"])
    assert (D.cal[w[0]], D.cal[w[1]]) == ("2026-06-10", "2026-06-16")
    assert HS.trade_window(D, {"adds": ["9999"]}, 10) is None             # 沒有投信資料 → 交給慣例


def test_hd_constituents_walk_back_from_current_holdings(monkeypatch):
    from arm.lab import hdstudy as HS
    monkeypatch.setattr(HS, "_cur_holdings", lambda etf: {"A", "B", "C"})
    ix = {"etfs": ["X"], "n": 3, "history": [
        {"review": "2026-06", "effective": "2026-06-18", "adds": ["C"], "dels": ["D"]},
        {"review": "2026-03", "effective": "2026-03-20", "adds": [], "dels": ["E"], "kind": "季審"},
        {"review": "2025-12", "effective": "2025-12-19", "adds": ["D"], "dels": ["F"]}]}
    cons = HS.constituents(ix)
    assert cons["2026-06"] == ({"A", "B", "D"}, {"A", "B", "C"})
    assert cons["2026-03"] == ({"A", "B", "D", "E"}, {"A", "B", "D"})
    assert cons["2025-12"] == ({"A", "B", "E", "F"}, {"A", "B", "D", "E"})
    bad = {"etfs": ["X"], "history": [{"review": "2026-06", "effective": "2026-06-18", "adds": ["Z"], "dels": []}]}
    assert HS.constituents(bad)["2026-06"] is None                       # 納入股不在目前持股 → 對不上，不用


def test_hd_buffer_select_top_in_keep_rank_and_change_cap():
    from arm.lab import hdpredict as HP
    ranked = [f"S{i:02d}" for i in range(1, 13)]
    pre = {"S03", "S07", "S09", "S12", "X1"}                              # X1 不合格（沒有名次）
    sel, adds, dels = HP.buffer_select(ranked, pre, 5, 2, 8)
    assert sel == ["S01", "S02", "S03", "S07", "S04"] and adds == ["S01", "S02", "S04"]
    assert dels[0] == "X1" and set(dels) == {"X1", "S09", "S12"}
    sel2, adds2, dels2 = HP.buffer_select(ranked, pre, 5, 2, 8, max_chg=1)
    assert adds2 == ["S01"] and len(sel2) == 5 and "X1" in dels2 and len(dels2) == 1


def test_hd_page_sections_and_glossary():
    js = page._JS
    for k in ("function hdPredSec(", "function hdStudySec(", "h+=hdPredSec(X.hd);", "+hdStudySec(I.hd)+", "'idx-hd'", "'idx-hds'",
              "'被動買賣期間':", "'對其他成分股':"):
        assert k in js, k


# —— 高股息：被動買盤大小（hdflow）

def test_hdflow_flow_subtracts_baseline_and_counts_days_of_volume():
    """被動買賣＝期間投信買賣超扣掉平常水準（之前第 25～6 個交易日中位數），× 期間均價 ÷ 20 日均成交金額＝幾天的量。"""
    from datetime import date, timedelta
    from arm.lab import hdflow as HF
    cal, d = [], date(2026, 3, 2)
    while len(cal) < 40:
        if d.weekday() < 5:
            cal.append(d.isoformat())
        d += timedelta(days=1)
    T0, T1 = 30, 32
    mkt = {x: {"q_tw": {"1111": [50.0, 50.0, 50.0, 50.0, 20000, 1_000_000]}, "q_tp": {},
               "i_tw": {"1111": [0, 101_000 if T0 <= i <= T1 else 1_000, 0]}} for i, x in enumerate(cal)}
    D = _hd_fake(cal, mkt)
    H = _hd_model(D, {})
    val, days = HF._flow(D, H, "1111", T0, T1)
    assert val == 3 * 100_000 * 50.0                                       # 平常每天 1,000 股不算被動買盤
    assert abs(days - 15.0) < 1e-9                                         # 1,500 萬 ÷ 每天 100 萬


def test_hdflow_fk_median_and_leave_one_out():
    """f_k＝各次審核「買進金額占市值」中位數的中位數；回測時用「其他次」的（不用到當次自己）。"""
    from arm.lab import hdflow as HF
    rows = [{"k": "tip_hd", "rev": r, "side": "add", "val": 1.0, "fm": fm}
            for r, fms in (("A", (4, 6)), ("B", (2, 2)), ("C", (10, 10))) for fm in fms]
    rows.append({"k": "tip_hd", "rev": "D", "side": "add", "val": 1.0, "fm": 50})       # 只有 1 檔的審核不算
    rows.append({"k": "tip_hd", "rev": "A", "side": "del", "val": -9.0, "fm": -3})      # 刪除股不算
    F = HF.fk(rows)
    assert abs(F["tip_hd"]["f"] - 0.05) < 1e-12 and set(F["tip_hd"]["per"]) == {"A", "B", "C"}
    assert abs(HF._f_loo(F, "tip_hd", "A") - 0.06) < 1e-12
    assert HF._f_loo(F, "tw_div", "A") is None


def test_hdflow_estimate_capped_by_single_stock_weight_limit():
    """市值 × f 對權值股會爆掉（台積電 × 2.35% ≈ 1.5 兆）→ 以單檔權重上限 × 規模封頂。"""
    from arm.lab import hdflow as HF
    assert abs(HF.est_amt(0.0235, 645_000, 0.10 * 1611) - 161.1) < 1e-9
    assert abs(HF.est_amt(0.045, 500, 0.15 * 6310) - 22.5) < 1e-9
    assert HF.est_amt(None, 500) is None and HF.est_amt(0.03, None) is None


def test_hdflow_phase_and_per_review_weighting():
    from arm.lab import hdflow as HF
    from arm.lab import tw50study as TS
    t0, t1 = "2026-12-16", "2026-12-28"
    until = TS.td_shift(t1, HF.AFTER)
    assert HF._phase("2026-10-14", t0, t1) == ("pre", until)
    assert HF._phase("2026-12-22", t0, t1)[0] == "in" and HF._phase(t1, t0, t1)[0] == "in"
    assert HF._phase(TS.td_shift(t1, 1), t0, t1)[0] == "after" and HF._phase(until, t0, t1)[0] == "after"
    assert HF._phase(TS.td_shift(t1, HF.AFTER + 1), t0, t1)[0] == "done"
    assert HF._phase("2026-10-14", None, None) == ("pre", None)
    rows = [{"k": "tip_hd", "rev": "R1", "x": -1.0}] * 3 + [{"k": "tip_hd", "rev": "R2", "x": 5.0}]
    out = HF._per_rev(rows, lambda r: True, "x")                         # 每次審核等權：(−1＋5)／2
    assert out["rev"] == {"n": 2, "avg": 2.0, "med": 2.0, "pos": 1}
    assert out["tr"]["n"] == 4 and out["tr"]["avg"] == 0.5 and out["by"][0][:2] == ["00919", "R1"]


def test_hd_flow_sections_alert_card_and_today_row():
    js = page._JS
    for k in ("function hdFlowSec(", "'idx-hdw'", "+hdStudySec(I.hd)+hdFlowSec(I.hd)+hdPreSec(I.hd)+",
              "function hdGroups(", "valSec('hd'", "hdGroups(false)",
              "'被動買賣日量':", "'被動買賣提醒':"):
        assert k in js, k
    assert "12 月首次觀察" not in js and "function hdAlertCard(" not in js


# —— 策略頁 v2：評級、信賴區間、部位、推薦清單（arm/lab/advice.py）

def _st(n=30, x=2.0, xwin=60, ci=(0.5, 3.5), conc=None, event=False, nb=None, rb=None, xe_rule=False):
    return {"n": n, "event": event, "x": x, "xwin": xwin, "ci": ci, "conc": conc,
            "nb": {"n": 9, "pos": 9} if nb is None else nb, "rb": {"x2": 1.0} if rb is None else rb, "xe_rule": xe_rule}


def test_advice_grade_thresholds():
    from arm.lab import advice as A
    ok_f = {"n": 10, "x": 1.0}
    assert A.grade(_st(), ok_f)[0] == "A"
    assert A.grade(_st(n=9), ok_f) == ("C", ["樣本只有 9 筆"])
    assert A.grade(_st(x=-0.1), ok_f)[0] == "C" and A.grade(_st(x=0.0), ok_f)[0] == "C"
    assert A.grade(_st(xwin=49), ok_f)[0] == "C"
    assert A.grade(_st(conc=["2026-08", 71]), ok_f)[0] == "C"
    assert A.grade(_st(), {"n": 10, "x": -0.5})[0] == "C"               # 前瞻滿額但輸大盤 → C
    g, why = A.grade(_st(ci=(-0.2, 3.0), conc=["2026-08", 46]), {"n": 3, "x": 1.0})
    assert g == "B" and len(why) == 3 and "含 0" in why[0] and "46%" in why[1] and "3／10" in why[2]
    assert A.grade(_st(n=29), ok_f)[0] == "B" and A.grade(_st(), {"n": 9, "x": 2.0})[0] == "B"
    ev = _st(n=6, event=True)                                           # 事件型：≥6 次、前瞻 2 次
    assert A.grade(ev, {"n": 2, "x": 1.0})[0] == "A" and A.grade(ev, {"n": 1, "x": 1.0})[0] == "B"
    assert A.grade(_st(n=3, event=True), {})[0] == "C" and A.grade(_st(n=4, event=True), {})[0] == "B"
    assert A.grade({"n": 0}, {})[0] == "C"


def test_advice_boot_ci_is_deterministic_and_contains_mean():
    import random
    import statistics
    from arm.lab import advice as A
    rnd = random.Random(7)
    xs = [rnd.gauss(1.0, 3.0) for _ in range(40)]
    a, b = A.boot_ci(xs), A.boot_ci(list(xs))
    assert a == b and a[0] < statistics.mean(xs) < a[1]
    assert A.boot_ci([1.0, 2.0]) is None and A.boot_ci([None, 1.0, 2.0]) is None


def test_advice_score_rounds_output_but_grades_on_raw_values():
    from arm.lab import advice as A
    units = [{"d": f"2026-0{1 + i % 9}-01", "r": r, "x": r - 0.95} for i, r in enumerate([1.0, 1.0, 1.0, 1.0] * 3)]
    sc = A.score(units)                                                 # 原始平均超額 +0.05（>0），顯示為 +0.1
    assert sc["x"] == 0.1 and sc["grade"] == "B" and sc["n"] == 12
    assert all(isinstance(v, int) or round(v, 1) == v for k, v in sc.items() if isinstance(v, (int, float)))
    assert isinstance(sc["ci"], list) and all(round(v, 1) == v for v in sc["ci"])


def test_advice_position_size():
    from arm.lab import advice as A
    assert A.size("B", 100.0, 80.0) == {"pct": 2.0, "amt": 20000, "sh": 200}        # 停損 20% → 0.5%／20%＝2.5%，取 2%
    assert A.size("A", 100.0, 80.0)["pct"] == 2.5                                     # A 上限 5%，被停損限制在 2.5%
    assert A.size("A", 100.0, None)["pct"] == 5.0
    assert A.size("C", 100.0, 80.0) is None and A.size("B", None, None) is None


def test_advice_per_review_equal_weights_each_review():
    from arm.lab import advice as A
    trs = [{"st": "closed", "review": "R1", "d": "2026-01-05", "r": 10.0, "x": 4.0},
           {"st": "closed", "review": "R1", "d": "2026-01-06", "r": -2.0, "x": -4.0},
           {"st": "closed", "review": "R2", "d": "2026-04-05", "r": 3.0, "x": 1.0},
           {"st": "open", "review": "R2", "d": "2026-04-06", "r": 50.0, "x": None}]
    u = A.per_review(trs)
    assert [(x["review"], x["n"], x["r"], x["x"]) for x in u] == [("R1", 2, 4.0, 0.0), ("R2", 1, 3.0, 1.0)]


def _adv_data(e_sig="2026-10-16"):
    from arm.lab import advice as A
    s1 = A.score([{"d": "2026-08-01", "r": 3.0, "x": 2.0}] * 6 + [{"d": "2026-09-01", "r": 2.0, "x": 1.0}] * 6)
    s3 = A.score([{"d": f"202{5 + i // 4}-0{1 + i % 4}-01", "r": 8.0, "x": 3.0} for i in range(6)], event=True)
    s5 = A.score([{"d": "2026-01-01", "r": -5.0, "x": -6.0}] * 12)
    return {"last": "2026-10-14",
            "rows": [{"c": "2327", "ia5": ["中信", "兆豐", "國泰"], "a5v": 6.3}],
            "strat": {"list": [
                {"key": "s1", "name": "共識加碼・開低進場", "kind": "短線", "hold": 3, "stop_atr": 2.0, "score": s1,
                 "cands": [{"c": "2327", "n": "國巨", "d": "2026-10-14", "px": 627.0, "stop": 555.0,
                            "ent": "2026-10-15", "out": "2026-10-19"}], "fwd": []},
                {"key": "s3", "name": "臺灣50 提前卡位", "kind": "事件型",
                 "vers": [{"k": "early", "score": s3}],
                 "plan": {"stage": "watch", "e_sig": e_sig, "e_in": "2026-10-19", "out": "2026-12-17",
                          "effective": "2026-12-18", "cutoff": "2026-11-23", "a_in": "2026-11-24",
                          "items": [{"c": "1301", "n": "台塑", "rank": 44, "px": 88.9, "mom": 48.2}]}}],
                "alerts": [{"c": "2330", "n": "台積電", "d": "2026-10-14", "gap": 3.5}]},
            "grow": {"s5": {"name": "長線：投信動能成長股", "kind": "長線", "score": s5, "screen_d": ["2026-10-30", "2026-11-02"]},
                     "screen": [{"c": "3605", "n": "宏致", "px": 187.0, "pass": True, "trust": 4.18, "tdays": 8}]},
            "idx": {},
            "v3ex": {k: {"grade": g, "why": [], "sel": {"n": 20, "xe": 0.5, "t": 1.2}, "pay": {"ok": True, "win": 60.0, "m": 1.5},
                         "unit": u} for k, g, u in (("s1", "B", "檔"), ("s3", "B", "次"), ("s5", "C", "檔"))}}


def _judge(tier, win, m, avg, n, path=None, ratio=None):
    return {"tier": tier, "win": win, "m": m, "avg": avg, "n": n, "path": path, "ratio": ratio, "few": 0 < n < 30}


JUDGE = {"s1": _judge("ref", 59.6, 11.2, 1.6, 47), "s3": _judge("good", 66.7, 10.8, 15.7, 24, "一般", 2.9),
         "s5": _judge("none", 40.0, -1.0, -5.0, 12)}


def test_advice_build_picks_watch_and_exits(monkeypatch):
    """機會頁推薦用報酬型態判定（docs/lab_signal_plan.md 第 15 節）：★ 在前、● 其次，○／— 不列；部位上限 ★ 5%、● 2%。"""
    from arm.lab import advice as A
    from arm.lab import sigcat
    monkeypatch.setattr(sigcat, "strat_judge", lambda tb: JUDGE)
    out = A.build(_adv_data())
    assert [g["k"] for g in out["grades"]] == ["s1", "s3", "s5"]
    assert [(p["k"], p["c"], p["ent"]) for p in out["picks"]] == [("s3", "1301", "2026-10-19"), ("s1", "2327", "2026-10-15")]
    p = out["picks"][1]
    assert p["grade"] == "B" and p["tier"] == "ref" and p["cond"] == "開盤價 < 627 才買" and p["out"] == "2026-10-19"
    assert p["exp"]["per10"] == round(p["exp"]["med"] * 1000) and p["size"]["pct"] == 2.0
    assert "中信" in p["why"][0] and "6.3 億元" in p["why"][1]
    tw = out["picks"][0]
    assert tw["tier"] == "good" and tw["tent"] and tw["fix"] == "2026-10-16" and tw["stop"] is None and tw["exp"]["event"]
    assert tw["size"]["pct"] == 5.0
    assert "11/24 開盤先賣出" in tw["out_how"]                          # 文字裡的日期一律 M/D
    assert [(w["k"], w["c"], w["tier"]) for w in out["watch"]] == [("s5", "3605", "none")]
    assert out["watch"][0]["size"] is None                              # ○ 不下單
    assert [(x["k"], x["c"]) for x in out["exits"]] == [("gap", "2330")]
    G = {g["k"]: g for g in out["grades3"]}
    assert (G["s3"]["rank"], G["s1"]["rank"], G["s5"]["rank"]) == (1, 2, None)     # ★ 在前；○ 不排
    assert G["s3"]["rank_why"] == "逐筆賺錢 67%，每月平均 +10.8%（24 筆，次數少）"
    assert "還沒到好策略的門檻（47 筆）" in G["s1"]["rank_why"]
    assert [b["k"] for b in out["book"]][:2] == ["s3", "s1"] and out["opp"]["n"] == 2
    assert out["caps"]["good"] == 0.05 and out["caps"]["ref"] == 0.02 and out["caps"]["A"] == 0.05


def test_advice_build_without_judgement_lists_nothing(monkeypatch):
    """判定算不出來（例如逐筆交易壞掉）：全部當次數不夠，機會頁不列推薦，不會拿舊評級頂上。"""
    from arm.lab import advice as A
    from arm.lab import sigcat

    def boom(tb):
        raise ValueError("x")
    monkeypatch.setattr(sigcat, "strat_judge", boom)
    out = A.build(_adv_data())
    assert out["picks"] == [] and out["opp"]["n"] == 0 and all(g["tier"] == "few" for g in out["grades3"])


def test_advice_build_lists_tw50_trial_picks_only_near_build_day(monkeypatch):
    from arm.lab import advice as A
    from arm.lab import sigcat
    monkeypatch.setattr(sigcat, "strat_judge", lambda tb: JUDGE)
    assert [p["k"] for p in A.build(_adv_data("2026-10-24"))["picks"]] == ["s3", "s1"]     # 10 天內
    assert [p["k"] for p in A.build(_adv_data("2026-10-25"))["picks"]] == ["s1"]           # 太早：只是試算，不列


def test_strategy_s4_removed_and_tw50_single_strategy():
    """使用者 2026-10-15：「群益那個策略拿掉吧，不具可靠性」；臺灣50 只留提前卡位一條策略。"""
    from arm.lab import strategy
    assert [s["key"] for s in strategy.STRATEGIES] == ["s1"]
    assert not hasattr(strategy, "_other_new")
    txt = str(strategy.STRATEGIES) + str(strategy.S3)
    assert "群益" not in txt and "——" not in str(strategy.TW50_VERS)


# —— 高股息「依編製規則提前卡位」回測（arm/lab/hdpre.py，2026-10-15）

class _FakeD:
    def __init__(self, n):
        self.cal = [f"2026-01-{i + 1:02d}" for i in range(n)]
        self.T = n


class _FakeP:
    """開盤＝收盤＝px[代號][i]；加權指數固定 100（超額＝報酬）。"""
    def __init__(self, px, n):
        self.D, self.p = _FakeD(n), px

    def px(self, c, i, opn):
        xs = self.p.get(c) or []
        return xs[i] if 0 <= i < len(xs) else None

    def bx(self, i, opn):
        return 100.0

    def ret(self, c, i0, o0, i1, o1):
        p0, p1 = self.px(c, i0, o0), self.px(c, i1, o1)
        if not p0 or not p1:
            return None, None
        r = p1 / p0 - 1 - 0.00585
        return r, r


def _hd_ev():
    # 截止日 C＝5、公告 N＝8、被動買盤 T0＝8～T1＝11；官方納入 A、B（C 猜錯）
    return {"key": "tip_hd", "review": "2026-05", "C": 5, "A": 8, "N": 8, "T0": 8, "T1": 11, "act": ["A", "B"],
            "stays": [f"S{i}" for i in range(5)],
            "preds": {0: {"adds": ["A", "C"], "est": {"A": [10.0, 8.0], "C": [5.0, 6.0]}},
                      3: {"adds": ["A", "D"], "est": {"A": [10.0, 7.0], "D": [4.0, 9.0]}}},
            "truth": {"A": [10.0, 8.0], "B": [9.0, 12.0]}}


def _hd_px():
    up = [100.0 + i for i in range(14)]
    flat = [100.0] * 14
    return {"A": up, "B": up, "C": flat, "D": flat, **{f"S{i}": flat for i in range(5)}}


def test_hdpre_main_spec_is_fixed():
    from arm.lab import hdpre
    assert hdpre.MAIN == {"lead": 0, "th": 5.0, "exit": "T1"}          # 看結果前寫死的主規格，不得事後改
    assert hdpre.capw("tip_hd", "2025-05") == 0.15 and hdpre.capw("tip_hd", "2024-12") == 0.10
    assert hdpre.capw("tip_tech", "2026-06") == 0.10


def test_hdpre_capped_weights_sum_to_one():
    from arm.lab import hdpre
    w = hdpre._capped({"a": 0.6, "b": 0.3, "c": 0.1}, 0.4)
    assert abs(sum(w.values()) - 1) < 1e-9 and abs(w["a"] - 0.4) < 1e-9 and w["b"] > w["c"]


def test_hdpre_simulate_cutoff_correction_and_official_miss():
    from arm.lab import hdpre
    P, ev = _FakeP(_hd_px(), 14), _hd_ev()
    t0 = {t["c"]: t for t in hdpre.simulate(ev, P, 0, 5.0)}                # 截止日隔天（6）開盤買 A、C
    assert set(t0) == {"A", "C"} and t0["A"]["i0"] == 6 and t0["A"]["i1"] == 11
    assert t0["C"]["i1"] == 9 and t0["C"]["why"] == "官方沒有納入"            # 公告後第一個交易日開盤賣
    t3 = {t["c"]: t for t in hdpre.simulate(ev, P, 3, 5.0)}                # 提前 3 日（3）買 A、D；截止日校正
    assert t3["A"]["i0"] == 3 and t3["D"]["i1"] == 6 and t3["D"]["why"] == "截止日名單沒有"
    assert t3["C"]["i0"] == 6                                              # 截止日名單新增的補進
    tp = {t["c"]: t for t in hdpre.simulate(ev, P, 0, 5.0, perfect=True)}  # 完美預知：官方名單
    assert set(tp) == {"A", "B"} and all(t["hit"] for t in tp.values())
    assert hdpre.simulate(ev, P, 0, 10.0, perfect=True)[0]["c"] == "B"    # 門檻：只有 ≥10 日量的


def test_hdpre_simulate_ann_and_per_review():
    from arm.lab import hdpre
    P, ev = _FakeP(_hd_px(), 14), _hd_ev()
    tr = {t["c"]: t for t in hdpre.simulate_ann(ev, P, 2, 5.0)}            # 公告前 2 日（6）開盤買
    assert tr["A"]["i0"] == 6 and tr["A"]["i1"] == 11 and tr["C"]["i1"] == 9
    assert hdpre.simulate_ann(ev, P, 3, 5.0) == []                         # 進場日不晚於截止日 → 不做
    u = hdpre.per_review(list(tr.values()))
    assert len(u) == 1 and u[0]["n"] == 2 and u[0]["review"] == "tip_hd:2026-05"
    assert abs(u[0]["r"] - (tr["A"]["r"] + tr["C"]["r"]) / 2) < 1e-9 and u[0]["hit"] == 1


def test_hd_conv_window_single_day_rebalance():
    """00929 2024-06 沒有過渡期（生效日收盤一次換完）：過渡期最後一天早於公告日時，期間＝公告日～最後一天。"""
    from arm.lab import hdstudy as HS
    h = {"announce": "2024-06-28", "effective": "2024-06-28", "trans_start": "2024-06-28", "trans_end": "2024-06-28"}
    assert HS._conv_window(None, "tip_tech", h) == ("2024-06-28", "2024-06-28")


def test_hdpre_page_sections():
    js = page._JS
    for k in ("function hdPreSec(", "sec('idx-hdpre'", "data-at=\"idx-hdpre\"", "v.k==='main'||v.k==='ann3'"):
        assert k in js, k


# ── 資料包策略回測與回測紀律（2026-10-15；docs/strategy_pack_plan.md） ─────────────────

def test_pack_main_specs_are_fixed():
    """主規格在回測前寫定並 commit（docs/strategy_pack_plan.md），不得事後調參數。"""
    from arm.lab import packtest as PT
    assert PT.P1 == {"look": 126, "skip": 21, "top": 0.10, "nmin": 10}
    assert PT.P2 == {"stop": 0.08, "vol": 1.5, "base": 25, "depth": 0.25, "tight": 0.10, "maxd": 120}
    assert PT.P3 == {"top": 0.20, "nmin": 10, "hold": 60}
    assert PT.P4 == {"look": 126, "skip": 21, "top": 0.10, "nmin": 10, "ep_max": 0.25}
    assert PT.P5 == {"look": 5, "top": 0.10, "nmin": 10}
    assert PT.P7 == {"win": 12, "min": 6, "top": 0.10, "nmin": 10}           # S26 月營收（第 6 節）
    assert (PT.CAP_L, PT.LIQ_L, PT.CAP_S) == (300e8, 2e8, 100e8)
    assert [r["k"] for r in PT.PACK] == ["p1", "p2", "p3", "p4", "p5", "p7"]


def test_advice_grade_robustness_rules():
    from arm.lab import advice as A
    ok_f = {"n": 10, "x": 1.0}
    g, why = A.grade(_st(nb={"n": 9, "pos": 4}), ok_f)
    assert g == "C" and "參數稍微改動就失效" in why[0]                        # 不到一半為正 → C
    g, why = A.grade(_st(nb={"n": 9, "pos": 5}), ok_f)
    assert g == "B" and why == ["參數鄰近 9 組中 5 組為正（A 級需 ≥6）"]
    assert A.grade(_st(nb={"n": 9, "pos": 6}), ok_f)[0] == "A"
    assert A.grade(_st(nb={}), ok_f) == ("B", ["尚未做參數鄰近檢查"])
    g, why = A.grade(_st(rb={"x2": -0.2}), ok_f)
    assert g == "B" and why == ["成本加倍後平均超額 −0.2%"]
    g, why = A.grade(_st(rb={"x2": 1.0, "xe": -0.3}, xe_rule=True), ok_f)
    assert g == "C" and "同一批股票" in why[0]                               # Yahoo 宇宙選股：沒贏同宇宙等權 → C
    assert A.grade(_st(rb={"x2": 1.0, "xe": -0.3}), ok_f)[0] == "A"         # 非 Yahoo 宇宙策略不套這條


def test_advice_robust_metrics():
    from arm.lab import advice as A
    us = [{"d": "2026-01-05", "x": 2.0, "xe": 1.0}, {"d": "2026-01-02", "x": -1.0, "cost": 0.2},
          {"d": "2026-01-07", "x": -3.0}, {"d": "2026-01-09", "x": 5.0, "xe": -0.5}]
    reg = {"2026-01-02": True, "2026-01-05": True, "2026-01-07": False}
    rb = A.robust(us, reg)
    assert abs(rb["x2"] - (0.75 - (0.2 + 0.585 * 3) / 4)) < 1e-9            # 帶 cost 的單位用自己的成本
    assert abs(rb["drop1"] - (-1.0 + 2.0 - 3.0) / 3) < 1e-9
    assert rb["mdd"] == 3.0 and rb["streak"] == 1                           # 依日期排序：−1,+2,−3,+5 → 累計 −1,1,−2,3
    assert rb["up"] == [2, 0.5] and rb["dn"] == [1, -3.0]                  # 2026-01-09 沒有年線資料 → 不分組
    assert rb["xe"] == 0.25 and rb["kxe"] == 1 and rb["nxe"] == 2
    sc = A.score([{"d": f"2026-0{1 + i % 9}-01", "r": 3.0, "x": 2.0} for i in range(12)], reg={}, nb={"n": 9, "pos": 9})
    assert sc["rb"]["x2"] == 1.4 and sc["nb"]["pos"] == 9 and sc["xe_rule"] is False


def test_fill_checks_limit_up_open_and_locked_limit_down():
    from arm.lab import backtest as B
    S = {"o": [100, 109.6, 95, 85.5, 82, 92], "h": [101, 110, 96, 85.5, 82, 93],
         "l": [99, 105, 94, 85.5, 82, 91], "c": [100, 106, 95, 85.5, 82, 92]}
    assert B.limit_up_open(S, 1) and not B.limit_up_open(S, 2)               # 109.6 ≥ 100×1.095
    assert B.locked_down(S, 3) and not B.locked_down(S, 4)                    # 一價到底但只跌 4.1%，不是鎖跌停
    S2 = {"o": [100, 90, 81, 85], "h": [100, 90, 81, 86], "l": [100, 90, 81, 80], "c": [100, 90, 81, 84]}
    assert B.exit_day(S2, 1, 4) == 3                                          # 連兩天鎖跌停 → 第三天收盤賣
    assert B.exit_day(S2, 1, 4, n_max=1) == 2 and B.exit_day(S2, 3, 4) == 3
    assert not B.locked_down({"o": [1, 1], "c": [1, 0.8]}, 1)                 # 沒有高低價的序列不判定


def test_tw50_trade_delays_limit_up_entry():
    from arm.lab import tw50study as TS
    cal = ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26", "2026-12-17"]
    S = {"X": {"o": [None, 110, 112, 105, 120], "c": [100, 110, 111, 106, 121],
               "h": [None, 110, 115, 108, 122], "l": [None, 109, 110, 104, 119]}}
    D = _tw50_fake(cal, S, [1000.0] * 5, [1000.0] * 5)
    t = TS._trade(D, TS._Px(D), "X", 1, "2026-11-24", "2026-12-17", False, "生效前一天出", {"c": "X"})
    assert t["st"] == "closed" and t["entry"] == 112 and t["lim"] == 1        # 11/24 漲停開盤 → 11/25 開盤買


def test_packtest_deadline_sue_and_ttm():
    from arm.lab import packtest as PT
    assert PT.deadline("2026-06-30") == "2026-08-14" and PT.deadline("2025-12-31") == "2026-03-31"
    eps = {"2023-03-31": 1.0, "2023-06-30": 1.0, "2023-09-30": 1.0, "2023-12-31": 1.0,
           "2024-03-31": 2.0, "2024-06-30": 1.5, "2024-09-30": 1.0, "2024-12-31": 1.5, "2025-03-31": 4.0}
    s = PT.sue(eps, "2025-03-31")                                             # 前 4 季同季差：1, 0.5, 0, 0.5
    import statistics
    assert abs(s - 2.0 / statistics.stdev([1.0, 0.5, 0.0, 0.5])) < 1e-9
    assert PT.sue(eps, "2024-12-31") is None                                  # 前面只有 3 季同季差
    assert PT.ttm_eps(eps, "2025-03-30") == 1.0 + 2.0 + 1.5 + 1.0            # 2024 年報 3/31 才到期 → 還不能用
    assert PT.ttm_eps(eps, "2025-05-15") == 1.5 + 1.0 + 1.5 + 4.0
    assert PT.ttm_eps({"2023-03-31": 1, "2023-06-30": 1, "2023-09-30": 1, "2024-06-30": 1}, "2025-01-01") is None


def test_packtest_basis_rolling_and_mean():
    from arm.lab import packtest as PT
    F = PT._basis([100.0, 102.0, None, 10.4, 10.5])
    assert abs(F[0] - 102 / 10.4) < 1e-9 and F[2:] == [1.0, 1.0, 1.0]       # 十比一面額變更：更早的價格換到新口徑
    assert PT._roll([3, None, 5, 1, 2], 2, max) == [3, 3, 5, 5, 2]
    assert PT._roll([3, None, 5, 1, 2], 2, min) == [3, 3, 5, 1, 1]
    assert PT._rmean([1.0, None, 3.0, 5.0], 2, 1) == [1.0, 1.0, 3.0, 4.0]


def _fake_px(series: dict, T: int, cap: float = 400e8):
    from arm.lab import packtest as PT
    P = PT.Px.__new__(PT.Px)
    P.T, P.cal = T, [f"2026-01-{i + 1:02d}" for i in range(T)]
    P.s = {c: {"o": o, "h": [x * 1.01 for x in cl], "l": [x * 0.99 for x in cl], "c": cl, "v": [1.0] * T}
           for c, (o, cl) in series.items()}
    P.cap = {c: [cap] * T for c in series}
    P.liq = {c: [5e8] * T for c in series}
    P.codes, P.lock_n, P._el, P._win = sorted(series), 0, {}, {}
    return P


def test_packtest_xsec_turnover_cost_and_limit_up():
    from arm.lab import packtest as PT
    flat = [100.0] * 6
    ser = {"A": (flat[:], [100, 110, 110, 120, 120, 130]), "B": (flat[:], [100, 105, 105, 106, 106, 107]),
           "C": (flat[:], [100, 90, 90, 80, 80, 70])}
    ser["A"][0][3] = 115.0                                                    # A 第 3 天開盤 115（對前收 110 未漲停）
    ser["B"][0][1] = 110.0                                                    # B 第 1 天開盤漲停（對前收 100）
    P = _fake_px({k: (o, [float(x) for x in c]) for k, (o, c) in ser.items()}, 6)
    score = lambda c, t: P.s[c]["c"][t]
    r = PT.xsec(P, ["A", "B", "C"], [0, 2, 4], score, top=0.5, nmin=2, cap_min=300e8, idx=[1000.0] * 6, io=[1000.0] * 6)
    u0, u1 = r["units"]
    assert u0["lim"] == 1 and u0["n"] == 1 and u0["to"] == 1.0                # B 漲停開盤買不到，只買到 A
    assert abs(u0["r"] - ((110 / 100 - 1) - PT.COST) * 100) < 1e-9
    assert u1["to"] == 0.0 and u1["cost"] == 0.0 and u1["lim"] == 0           # 續抱 A、B 不計成本也不檢查漲停
    assert r["now"]["picks"] == ["A", "B"] and r["now"]["d"] == "2026-01-05"


def test_packtest_p7_revenue_surprise_and_formation_dates():
    import statistics
    from arm.lab import packtest as PT
    assert PT.ym_shift("2026-01", -1) == "2025-12" and PT.ym_shift("2025-12", 13) == "2027-01"
    assert PT.ym_shift("2026-03", -15) == "2024-12"
    months = [PT.ym_shift("2024-01", i) for i in range(26)]                  # 2024-01 … 2026-02
    base = {ym: 100.0 + (i % 5) for i, ym in enumerate(months)}
    rev = {**base, "2026-01": base["2026-01"] + 30}
    diffs = [rev[PT.ym_shift("2026-01", -k)] - rev[PT.ym_shift("2026-01", -k - 12)] for k in range(1, 13)]
    want = (rev["2026-01"] - rev["2025-01"]) / statistics.stdev(diffs)
    assert abs(PT.sur(rev, "2026-01") - want) < 1e-12
    assert PT.sur(rev, "2025-06") is None and PT.sur(rev, "2025-07") is not None   # 前 12 個月有去年同月的不到 6 個 → 不算
    assert PT.sur({**rev, "2025-01": None}, "2026-01") is None               # 去年同月沒公告
    # 形成日＝10 日當天或之後的第一個交易日（2026-01-10 是週六 → 01-12；法定期限遇假日順延）
    cal = ["2026-01-09", "2026-01-12", "2026-01-13", "2026-02-10", "2026-02-11", "2026-03-10", "2026-03-11"]
    assert PT.rev_forms(cal) == [(1, "2025-12"), (3, "2026-01"), (5, "2026-02")]


def test_packtest_p7_units_pick_highest_surprise():
    from arm.lab import packtest as PT
    cal = ["2026-01-09", "2026-01-12", "2026-01-13", "2026-02-10", "2026-02-11", "2026-03-10", "2026-03-11"]
    T = len(cal)
    cl = {"A": [100, 100, 100, 110, 110, 110, 110], "B": [100, 100, 100, 100, 100, 95, 95], "C": [100.0] * T}
    P = PT.Px.__new__(PT.Px)
    P.T, P.cal = T, cal
    P.s = {c: {"o": [100.0] * T, "h": [x * 1.01 for x in v], "l": [x * 0.99 for x in v], "c": [float(x) for x in v],
               "v": [1.0] * T} for c, v in cl.items()}
    P.cap, P.liq = {c: [400e8] * T for c in cl}, {c: [5e8] * T for c in cl}
    P.codes, P.lock_n, P._el, P._win = sorted(cl), 0, {}, {}
    months = [PT.ym_shift("2024-01", i) for i in range(26)]
    base = {ym: 100.0 + (i % 5) for i, ym in enumerate(months)}
    rev = {"A": {**base, "2025-12": base["2025-12"] + 30}, "B": {**base, "2026-01": base["2026-01"] + 30}, "C": dict(base)}
    r = PT.p7_units(P, ["A", "B", "C"], rev, [1000.0] * T, [1000.0] * T, {**PT.P7, "top": 0.3, "nmin": 1})
    u0, u1 = r["units"]
    assert u0["d"] == "2026-01-12" and abs(u0["r"] - (0.10 - PT.COST) * 100) < 1e-9   # 12 月營收 A 最出乎意料
    assert u1["d"] == "2026-02-10" and abs(u1["r"] - (-0.05 - PT.COST) * 100) < 1e-9  # 1 月換成 B
    assert r["now"]["d"] == "2026-03-10" and r["now"]["ym"] == "2026-02" and len(r["now"]["picks"]) == 1


def test_packtest_p7_excludes_financials(monkeypatch):
    from arm import stockmeta
    from arm.lab import packtest as PT
    monkeypatch.setattr(stockmeta, "industry_map", lambda: {"2330": "半導體業", "2881": "金融保險"})
    assert PT.non_fin(["2330", "2881", "9999"]) == ["2330", "9999"]


def test_backfill_rev_mops_writes_complete_months_only(tmp_path, monkeypatch):
    from datetime import date
    from arm import clock
    from arm.lab import collect, market, store
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(clock, "today_tw", lambda: date(2020, 4, 15))         # 可得到 2020-03
    calls = []

    def fake(mkt, y, m, k=0):
        calls.append((y, m, mkt, k))
        if (y, m) == (2020, 2) and mkt == "otc" and k == 0:
            return None                                                         # 上櫃國內頁抓不到 → 整月不寫
        return {f"{mkt}{k}{i:04d}": [1.0, 2.0, 3.0] for i in range(300)}
    monkeypatch.setattr(market, "fetch_mops_rev", fake)
    monkeypatch.setattr(collect.time, "sleep", lambda s: None)
    assert collect.backfill_rev_mops("2020-01") == 2
    assert store.dates("rev") == ["2020-01", "2020-03"] and len(calls) == 12
    assert len(store.read("rev", "2020-03")["s"]) == 1200
    calls.clear()
    assert collect.backfill_rev_mops("2020-01") == 0 and {c[:2] for c in calls} == {(2020, 2)}   # 已有的月份跳過


def test_packtest_grid_counts_positive_cells():
    from arm.lab import packtest as PT
    g = PT.grid(lambda a, b: a - b, (1, 2, 3), (0.5, 1.5, 2.5), ("甲", "乙"))
    assert g["n"] == 9 and g["pos"] == 6 and g["lbl"] == ["甲", "乙"]
    assert g["ad"] == ["1", "2", "3"] and g["bd"] == ["50%", "1.5", "2.5"]
    assert PT.grid(lambda a, b: None, (1,), (2,))["n"] == 0


def test_growth_eps_growth_gate_uses_published_quarters():
    from arm.lab import growth
    eps = {"2025-03-31": 1.0, "2025-06-30": 1.0, "2026-03-31": 1.3, "2026-06-30": 1.2}
    assert growth.eps_growth_ok(eps, "2026-05-15")                            # 2026Q1 年增 30%
    assert not growth.eps_growth_ok(eps, "2026-08-14")                        # 2026Q2 年增 20%
    assert not growth.eps_growth_ok(eps, "2026-05-14")                        # 2026Q1 尚未到期 → 用 2025Q4（沒有）
    assert growth.eps_growth_ok({"2025-03-31": -0.5, "2026-03-31": 0.2}, "2026-06-01")   # 由虧轉盈
    assert not growth.eps_growth_ok({"2025-03-31": 1.0, "2026-03-31": -0.2}, "2026-06-01")


def test_strategy_page_robustness_and_pack_sections():
    js = page._JS
    for k in ("function robTbl(", "function nbGrid(", "function bt3Sec(", "sec('val-bt3'", "function totPos(",
              "+robTbl(g,v3);", "看 ${N.n} 組", "沒有採用的項目與原因", "同一批股票"):
        assert k in js, k
    assert "function packSec(" not in js and "sec('st-pack'" not in js      # 舊資料包表（5 年、對加權指數）由 v3 總表取代
    assert "低回落例外檢查" in js and "g.lowdd?" in js                        # 第 15 節：例外檢查表與評級表標示
    for k in ("穩健度檢查", "成本加倍", "參數鄰近", "同一批股票的平均", "存活者偏誤", "大盤年線", "成交檢查",
              "相對強勢", "趨勢樣板", "SUE", "月營收驚喜", "CAN SLIM",
              "樣本外", "樣本內", "t 值", "賺錢機率", "每月平均", "賺賠比", "報酬型態", "前 5 檔", "大型股", "中型股",
              "因子檢定", "資金帳戶", "最大回落", "去掉最好 5%", "低回落例外"):
        assert f"'{k}':" in js, k                                            # 名詞辭典



def test_v3_grading_order_and_texts(tmp_path, monkeypatch):
    """回測方法 v3（2026-10-15 使用者：每條策略只取最強前 5 檔、全部 B 級依證據強弱排序）：
    有樣本外的排前面、再依樣本內外 t 值較小者；A 級另需樣本外報酬型態；既有策略的 C 級移到觀察。"""
    from arm.lab import advice
    assert advice._ev({"t": 1.46}, {"t": 2.22}) < advice._ev({"t": 1.46}, {"t": 1.52})   # 同分看較大的那個
    assert advice._ev({"t": 0.5}, {"t": 0.6}) < advice._ev(None, {"t": 3.0})           # 有樣本外的永遠在前
    side = lambda xe, t, n=40, win=65, m=2.0, ok=True: {"n": n, "xe": xe, "t": t, "drop5": 0.5, "x2": 0.6, "win": win,
                                                        "m": m, "ratio": 1.5, "pay_ok": ok, "d0": "2013-08-12",
                                                        "d1": "2021-09-30"}
    nb = {"n": 9, "pos": 9}
    r = {"ins": side(1.5, 2.5), "oos": side(1.2, 1.8, ok=False), "nb": nb, "event": False}
    g = advice.grade_v3(r, {"n": 12, "xe": 0.8})
    assert g["grade"] == "B" and any("樣本外報酬型態" in w for w in g["why"])          # 只差樣本外報酬型態 → B
    r["oos"]["pay_ok"] = True
    assert advice.grade_v3(r, {"n": 12, "xe": 0.8})["grade"] == "A"
    assert advice.grade_v3(r, {"n": 3, "xe": 0.8})["grade"] == "B"                     # 前瞻未滿 10 期
    assert advice.grade_v3({**r, "oos": side(-0.3, -1.2)}, None)["grade"] == "C"         # 樣本外反向
    t = advice._oos_txt(side(1.41, 1.46, n=98), "月")
    assert t == "樣本外 2013-08～2021-09（98 月）：每月平均報酬比同一批股票高 1.41%（t 1.46）"
    assert "低 0.20%" in advice._oos_txt(side(-0.2, None), "季") and "（t —）" in advice._oos_txt(side(-0.2, None), "季")
    e = advice._exp3({"n": 158, "med": 1.26, "p25": -3.8, "p75": 8.0, "win": 59, "kwin": 94, "lo": -25.2, "per10": 1260,
                      "lo10": -25200}, "月")
    assert e["event"] and e["grp"] == "期" and e["n"] == 158                           # 每期＝同一期 5 檔等額平均


def test_v3_build_puts_oos_first_and_c_into_watch(tmp_path, monkeypatch):
    from arm.lab import advice, store
    monkeypatch.setattr(store, "LAB", tmp_path)
    side = lambda xe, t, ok=True: {"n": 60, "xe": xe, "t": t, "drop5": 0.4, "x2": 0.5, "win": 62, "m": 2.0, "ratio": 1.4,
                                   "pay_ok": ok, "d0": "2013-08-12", "d1": "2021-09-30"}
    row = lambda k, xi, ti, xo, to: {"k": k, "ver": "top5", "src": "p7", "event": False, "ins": side(xi, ti),
                                     "oos": side(xo, to), "nb": {"n": 9, "pos": 9}, "nb_oos": {"n": 9, "pos": 9},
                                     "dist": {"n": 100, "med": 1.0, "p25": -2, "p75": 4, "win": 60, "kwin": 60, "lo": -20,
                                              "per10": 1000, "lo10": -20000}}
    store.write_json("bt3_research.json", {"asof": "2026-10-14", "oos_end": "2021-10-01", "meta": {},
                                           "rows": [row("v7m", 1.25, 1.5, 1.4, 1.46), row("v3m", -3.1, -2.7, 0.4, 0.2)]})
    now = {"d": "2026-10-12", "ent": "2026-10-13", "out": "2026-11-10", "entered": True, "n_uni": 270,
           "picks": [{"c": "2355", "n": "敬鵬", "entry": 49.0, "now": 51.9, "now_r": 5.9, "why": ["9 月營收年增 44%"]}]}
    v3 = {k: {"k": k, "src": "p7", "b": "M", "name": k, "unit": "月", "since": "2026-10-15", "res": r, "fwd": {"n": 0},
              "now": now, "next": {"d": "2026-11-10", "ent": "2026-11-11"}}
          for k, r in (("v7m", row("v7m", 1.25, 1.5, 1.4, 1.46)), ("v3m", row("v3m", -3.1, -2.7, 0.4, 0.2)))}
    ex = {"s1": {"grade": "B", "why": ["選股超額 t 值 -0.04（A 級需 ≥2）"], "sel": {"n": 39, "xe": 1.2, "t": -0.04},
                 "pay": {"win": 64, "m": 19.7, "ratio": 1.7, "ok": True}, "x2": 0.7, "nb": {"n": 9, "pos": 9}, "unit": "筆"}}
    out = advice.build_v3(v3, ex, "2026-10-14")
    G = {g["k"]: g for g in out["grades"]}
    assert G["v7m"]["grade"] == "B" and G["v3m"]["grade"] == "C" and G["s1"]["grade"] == "B"
    assert sorted(out["grades"], key=lambda g: g["ev"])[0]["k"] == "v7m"                # 有樣本外的 B 排第一
    assert [p["k"] for p in out["picks"]] == ["v7m"] and [p["k"] for p in out["watch"]] == ["v3m"]
    p = out["picks"][0]
    assert p["act"] == "持有中" and p["oos"] and p["out"] == "2026-11-10" and p["stop"] is None
    assert p["oos_txt"].startswith("樣本外 2013-08～2021-09") and p["exp"]["grp"] == "期"
    assert set(out["live"]["v7m"]) >= {"rules", "bucket", "res", "now", "next", "grade", "why"}


def test_v3live_next_formation_dates():
    """月營收：每月 10 日（遇假日順延）；財報：法定期限遇假日順延（2026-11-14 週六 → 11/16）。"""
    from arm.lab import v3live
    assert v3live.next_rev_form("2026-10-12") == "2026-11-10"
    q, d = v3live.next_eps_form("2026-06-30")
    assert q == "2026-09-30" and d == "2026-11-16"
    q, d = v3live.next_eps_form("2026-09-30")
    assert q == "2026-12-31" and d >= "2027-03-31"


# ── 版面 v3（2026-10-15；docs/lab_layout_v3_plan.md）：實際報酬、行事曆、策略一覽 ──────────────────

def test_signal_stats_report_actual_return_and_market():
    """訊號成績另給實際報酬：rm＝中位、rw＝賺錢比例、mk＝同一時窗大盤平均（＝實際 − 超額）。"""
    from arm.lab import backtest
    a = backtest._agg([{"r": 0.02, "x": 0.01, "g": 0.0}, {"r": -0.01, "x": -0.03, "g": 0.01}, {"r": 0.04, "x": 0.0, "g": 0.0}])
    assert (a["r"], a["rm"], a["rw"]) == (1.67, 2.0, 67.0)
    assert a["mk"] == round(((0.01) + (0.02) + (0.04)) / 3 * 100, 2) and a["w"] == 33.0
    js = page._JS
    for k in ("function sigVerdict(", "function sigConcl(", "const SIGST={cons:'s1'}", "照做的實際報酬（持有 5／20 天、同期大盤）",
              "不是買點", "function sigShort(", "function sigAllSec("):
        assert k in js, k
    assert "勝率" not in js.split("/* ---------- 訊號（版面 v4", 1)[1].split("/* ---------- 投信動向", 1)[0]


def test_advice_expect_book_and_ex_best_year():
    from arm.lab import advice
    e = advice.expect({"n": 10, "avg": 2.7, "med": 1.5, "p25": -2.4, "p75": 7.1, "lo": -8.3, "hi": 16.1, "win": 64,
                       "kwin": 25, "x": 2.0, "d0": "2026-07", "d1": "2026-10"})
    assert e["mk"] == 0.7 and (e["d0"], e["d1"]) == ("2026-07", "2026-10") and e["avg"] == 2.7
    yearly = [["2014", 10.0, 5.0, "2014-12-31"], ["2015", 100.0, 10.0, "2015-12-31"], ["2016", 10.0, 5.0, "2016-12-30"]]
    x = advice._ex_best({"d0": "2014-01-02"}, yearly)
    assert x["y"] == "2015" and x["r"] == 100.0 and 9.5 < x["cagr"] < 10.5 and 4.5 < x["tr_cagr"] < 5.5
    assert advice._ex_best({"d0": "2014-01-02"}, yearly[:2]) is None                   # 至少 3 年才算
    live = {"v7m": {"src": "p7", "res": {"dist": {"n": 3, "avg": 2.6, "med": 1.3, "mk": 1.6, "win": 59, "kwin": 2,
                                                  "d0": "2013-08-12", "d1": "2026-09-10"}, "all": {"cagr": 29.1}}, "unit": "月"}}
    bk = advice.book([{"k": "v7m", "name": "月營收驚喜（中型股）", "grade": "B"}, {"k": "s1", "name": "共識加碼", "grade": "B"}],
                     live, {"s1": {"n": 5, "avg": 2.0, "med": 1.0, "p25": 0, "p75": 3, "lo": -1, "win": 60, "kwin": 3, "x": 1.0}})
    assert [b["k"] for b in bk] == ["v7m", "s1"] and bk[0]["exp"]["d0"] == "2013-08" and bk[0]["all"]["cagr"] == 29.1
    assert bk[1]["unit"] == "檔" and bk[1]["exp"]["mk"] == 1.0 and bk[0]["unit"] == "次"
    assert advice._sell("v7m", live, None).startswith("下一次換股日") and "停損" in advice._sell("s1", live, None)


def test_advice_calendar_orders_by_date_and_skips_c_and_past():
    """行事曆：今天之後的買進、賣出、換股依日期排（同一天開盤在前）；○／— 不列（sigspec VER 2）；名單還沒產生的列名單產生日。"""
    from arm.lab import advice
    gm = {"s1": {"grade": "B", "tier": "ref"}, "v7m": {"grade": "B", "tier": "good"}, "v3m": {"grade": "B", "tier": "none"}}
    picks = [
        {"k": "s1", "sname": "共識加碼", "act": "佈局", "c": "2330", "n": "台積電", "ent": "2026-10-15", "out": "2026-10-19",
         "px": 1000.0, "stop": 950.0, "exp": {"n": 3}},
        {"k": "v7m", "sname": "月營收驚喜（中型股）", "act": "持有中", "c": "2355", "n": "敬鵬", "ent": "2026-10-13",
         "out": "2026-11-10", "entry": 49.0, "now": 51.9, "now_r": 5.9}]
    live = {"v7m": {"src": "p7", "name": "月營收驚喜（中型股）", "next": {"d": "2026-11-10", "ent": "2026-11-11"}},
            "v3m": {"src": "p3", "name": "財報驚喜（中型股）", "next": {"d": "2026-11-16", "ent": "2026-11-17"}}}
    cal = advice.calendar(picks, live, gm, {"v7m": 0, "s1": 1}, {"v7m": {"exp": {"n": 158}}}, None, None, 0, "2026-10-14")
    got = [(e["d"], e["at"], e["act"], e["k"]) for e in cal]
    assert got == [("2026-10-15", "開盤", "買進", "s1"), ("2026-10-19", "收盤", "賣出", "s1"),
                   ("2026-11-10", "收盤", "換股", "v7m"), ("2026-11-11", "開盤", "買進", "v7m")]
    assert cal[3]["pending"] and cal[3]["fix"] == "2026-11-10" and cal[3]["exp"] == {"n": 158}
    assert cal[0]["items"][0]["stop"] == 950.0 and cal[0]["sell"] and cal[1]["note"] == "10/15 有買到的"
    assert cal[0]["tier"] == "ref" and cal[2]["tier"] == "good"
    assert advice.calendar(picks, live, gm, {}, {}, None, None, 0, "2026-10-16")[0]["d"] == "2026-10-19"   # 已過的不列


# ── 逐筆交易（2026-10-15 使用者：「我希望每個策略都會有像是 0050 策略的逐筆歷史交易，我才能去驗證」；docs/lab_trades_plan.md）

def test_strategy_trades_section_and_columns_match_python():
    """策略卡多一列「逐筆交易」（預設收起、展開才畫）；頁面解碼用的欄位順序要和 trades.py 一致；年份、搜尋、CSV 都在。"""
    import re
    from arm.lab import trades
    js = page._JS
    trc = re.search(r"TRC=\[([^\]]*)\]", js).group(1)
    assert [x.strip("'") for x in trc.split(",")] == trades.TR_COLS
    prc = re.search(r"PRC=\[([^\]]*)\]", js).group(1)
    assert [x.strip("'") for x in prc.split(",")] == trades.PER_COLS
    for k in ("parts.push(['逐筆交易',tb])", "function trCsv(", "function trData(", "function trCheck(", "trBind();",
              "data-tcsv", "data-ty", "data-tq", "'\\ufeff'", "<details class=\"mr trb\""):
        assert k in js, k
    howt = re.search(r"const HOWT=\{([^}]*)\}", js).group(1)
    for code in trades._HOW.values():                                       # 賣出原因代碼頁面都要認得
        assert f"{code}:'" in howt, code
    assert "bt:'" in howt
    for k in ("function tradeTbl(", "function pastTrades(", "function revTbl(", "function tradeLists("):   # 舊的三種逐筆表已統一
        assert k not in js, k


def test_research_trades_reconcile_with_strategy_numbers():
    """研究檔每條前 5 檔策略都有逐筆交易；每期表的期數、平均、正的比例＝策略頁「每月（季）平均」用的 dist。"""
    import statistics
    res = store.read_json("bt3_research.json", {}) or {}
    rows = [r for r in res.get("rows") or [] if r.get("ver") == "top5"]
    assert rows
    for r in rows:
        t = r.get("trades") or {}
        per, d = t.get("per") or [], r.get("dist") or {}
        assert len(per) == d.get("n"), r["k"]
        rs = [p[3] for p in per]
        assert abs(statistics.mean(rs) - d["avg"]) < 0.01, r["k"]
        assert round(100 * sum(1 for x in rs if x > 0) / len(rs)) == d["win"], r["k"]
        tr = [x for x in t.get("tr") or [] if x[8] == "c"]
        assert len(tr) >= len(per), r["k"]                                  # 每期至少一筆
        assert all(x[3] and x[5] for x in tr), r["k"]                       # 每筆都有實際買賣價


def test_trade_book_collects_all_strategies_without_duplicates(monkeypatch):
    from arm.lab import advice
    monkeypatch.setattr(store, "read_json", lambda name, default=None: {"9999": "已下市公司"} if name == "names_hist.json" else {})
    s1 = {"key": "s1", "since": "2026-10-14", "tr": {"per": [], "tr": [["2330", 1, 2]]}}
    s3 = {"key": "s3", "vers": [{"k": "early", "since": "2026-10-14", "tr": {"per": [], "tr": [["2317", 1, 2]]}},
                                {"k": "post", "tr": None}]}
    data = {"strat": {"list": [s1, s3]}, "grow": {"s5": {"since": "2026-10-14", "tr": {"per": [], "tr": [["2454", 1, 2]]}}},
            "idx": {"hd": {"flow": {"tr": {"per": [], "tr": [["2412", 1, 2]]}}, "alert": {"since": "2026-10-14"}}},
            "rows": [{"c": "2330", "n": "台積電"}]}
    live = {"v7m": {"unit": "月", "since": "2026-10-15", "src": "p7", "b": "M", "tr_res": {"per": [[1]], "tr": [["9999", 1, 2]]},
                    "tr": {"per": [], "tr": []}}}
    out, nm = advice.trade_book(data, live, {"v7m", "s1", "s3", "s5", "hd"})
    assert {k: v["kind"] for k, v in out.items()} == {"v7m": "per", "s1": "trade", "s3": "rev", "s5": "trade", "hd": "rev"}
    assert "tr" not in s1 and "tr" not in s3["vers"][0] and "tr" not in data["grow"]["s5"]   # 搬到 ADV.trades，頁面不重複內嵌
    assert "tr_res" not in live["v7m"] and "tr" not in live["v7m"]
    assert nm == {"2330": "台積電", "9999": "已下市公司"}



def test_signal_sections_use_overview_judgement():
    """後台「訊號成績」：命中率／平常（訊號總覽同一套，docs/lab_signal_plan.md 第 6.3 節），每個訊號連到訊號總覽那一列；
    照做的實際報酬收在展開。籌碼頁的「今日訊號」2026-10-23 拿掉（docs/lab_ia_v5_plan.md 第 4 節）。"""
    from arm.lab import sigcat
    js = page._JS
    for k in ("const SJ=D.sigj||{}", "x9r.html#s=stk:sig:", "<th>命中率</th><th>平常</th>"):
        assert k in js, k
    rows = [{"cat": "stock", "var": "cons", "dir": ["up"], "up": {"tier": "none", "n": 103, "hit": 0.5926, "base": 1.0}},
            {"cat": "stock", "var": "exit", "dir": ["warn"], "warn": {"tier": "ref", "n": 90, "hit": 0.3556, "base": 0.0111}},
            {"cat": "strat", "var": "s1", "dir": ["up"], "up": {"tier": "ref", "n": 47, "hit": 0.6, "base": 0.5}}]
    assert sigcat.stock_brief(rows) == {"cons": ["none", "up", 103, 59.3, 100.0], "exit": ["ref", "warn", 90, 35.6, 1.1]}
    assert sigcat.stock_brief(None) == {}
    pg = (Path(__file__).resolve().parents[1] / "arm" / "lab" / "page.py").read_text(encoding="utf-8")
    assert 'data["sigj"] = sigcat.stock_brief(srows)' in pg and "sigcat.write_stock(data, ctx, rows=srows)" in pg


def test_opportunity_and_strategy_views_show_judgement_not_letter_grades():
    """機會頁、策略頁（研究紀錄的個股策略）用 ★／●（sigspec VER 2）；A／B／C 只留在後台。
    個股卡（配置的工具分頁）2026-10-23 起只列台股配置裡的策略，不放 ★／●（docs/lab_ia_v5_plan.md 第 8 節第 4 條）。"""
    js = page._JS
    assert "function tBadge(" in js and "const TN={good:'好策略',ref:'可參考',none:'不推薦',few:'次數不夠'}" in js
    for fn in ("function oCard(", "function bookSec(", "function stCard("):
        body = js.split(fn, 1)[1].split("\nfunction ", 1)[0]
        assert "tBadge(" in body and "gBadge(" not in body, fn
    body = js.split("function stCardSec(", 1)[1].split("\nfunction ", 1)[0]
    assert "tBadge(" not in body and "gBadge(" not in body and "推薦順序" not in body
    opp = js.split("function vOpp(", 1)[1].split("\nfunction ", 1)[0]
    assert "A、B 級" not in opp and "★ 好策略、● 可參考" in opp
    assert "'判定':" in js and "capTxt(e.tier)" in js


def test_pos_px_only_takes_closes_from_the_disclosure_day():
    """ETF 部位分片的「揭露當下收盤」：2026-10-21 起持股明細的收盤是報價日 pd（最新交易日）的——
    快照較舊（pd≠揭露日）時不可當成揭露日的收盤（docs/etf_chg_fix_plan.md）。舊格式沒有 pd，照舊。"""
    from arm.lab import collect

    def doc(pd):
        det = {"date": "2026-10-19", "all": [{"stock_id": "NVDA US", "close": 217.09, "ccy": "USD"},
                                            {"stock_id": "2330", "close": 2420.0, "ccy": None}]}
        if pd is not None:
            det["pd"] = pd
        return {"etfs": {"00988A": {"date": "2026-10-19", "src": "etfinfo", "detail": det,
                                    "holdings": [{"stock_id": "2330", "shares": 1, "weight": 1.0}]}}}
    same = collect.snaps_from_holdings(doc("2026-10-19"), skip=set())["2026-10-19"]["00988A"]
    assert same["px"] == {"NVDA US": [217.09, "USD"], "2330": [2420.0, None]}
    later = collect.snaps_from_holdings(doc("2026-10-20"), skip=set())["2026-10-19"]["00988A"]
    assert later["px"] == {}
    legacy = collect.snaps_from_holdings(doc(None), skip=set())["2026-10-19"]["00988A"]
    assert legacy["px"] == same["px"]
