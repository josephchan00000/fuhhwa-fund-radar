"""籌碼雷達（arm/lab/）——解析、帳本口徑、指標、頁面安全性。全部離線、不打網路。"""
from __future__ import annotations

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
    text = page._HTML + page._JS + "".join(n + d for n, d in analyze.SIG_DEF.values())
    assert not [w for w in banned if w in text]


def test_page_layout_six_tabs_today_first_and_glossary():
    """2026-10-14 改版定案：今日｜個股｜投信｜訊號｜策略｜指數，一打開是「今日」；「說明」改為 ⓘ 名詞。"""
    import re
    tabs = re.findall(r'<a data-t="(\w+)">([^<]+)</a>', page._HTML)
    assert tabs == [("today", "今日"), ("stk", "個股"), ("iss", "投信"), ("sig", "訊號"),
                    ("st", "策略"), ("idx", "指數")]
    assert 'id="glb"' in page._HTML and "說明</a>" not in page._HTML
    assert "go('today');" in page._JS
    js_views = re.search(r"const VIEWS=\{([^}]*)\}", page._JS).group(1)
    assert [k.split(":")[0] for k in js_views.split(",")] == [t for t, _ in tabs]


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
    """入口只在頁尾、不進導覽列（使用者：沒那麼好找到就好）。"""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1].joinpath("arm", "fund_dashboard.py").read_text("utf-8")
    assert src.count('href="x9.html"') == 1
    foot = src.split('<div class="foot">', 1)[1].split("</div>", 1)[0]
    assert 'href="x9.html"' in foot


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
