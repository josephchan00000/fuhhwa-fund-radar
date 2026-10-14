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
    L = ledger.build(sorted(merged.items()), px)
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


def test_entrance_is_low_key_footer_link_only():
    """入口只在頁尾、不進導覽列（使用者：沒那麼好找到就好）。"""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1].joinpath("arm", "fund_dashboard.py").read_text("utf-8")
    assert src.count('href="x9.html"') == 1
    foot = src.split('<div class="foot">', 1)[1].split("</div>", 1)[0]
    assert 'href="x9.html"' in foot
