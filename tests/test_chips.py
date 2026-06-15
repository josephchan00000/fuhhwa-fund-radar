"""籌碼分點推敲引擎單元測試（M3）：關鍵分點/連續買超/佔比/身份推估/偵測器/降級。

設計鐵則：分點只到分公司層級，買家身份一律『推估・非確認』（§18.4）。
"""
from arm import chips, ideas, signals
from arm.connectors import brokers
from arm.connectors.brokers.base import BrokerFlow, TargetFlows

BMAP = {
    "by_id": {"1470": {"label": "台灣摩根士丹利", "kind": "外資"}},
    "by_name_keyword": {"美林": "外資", "投信": "投信"},
    "kinds": {"外資": "外資分點（推估）"},
}


def _flows(target, rows):
    """rows: (date, broker_id, broker_name, net)。"""
    return [BrokerFlow(target, d, bid, name, net) for d, bid, name, net in rows]


# 台積電：摩根連 3 日買超（合計 +2800）；凱基連續賣超。
TSMC = TargetFlows("2330", "台積電", _flows("2330", [
    ("2026-06-12", "1470", "台灣摩根士丹利", 1200),
    ("2026-06-11", "1470", "台灣摩根士丹利", 900),
    ("2026-06-10", "1470", "台灣摩根士丹利", 700),
    ("2026-06-12", "9200", "凱基-台北", -800),
    ("2026-06-11", "9200", "凱基-台北", -300),
]), {"2026-06-12": 28000, "2026-06-11": 25000, "2026-06-10": 24000})


def test_consecutive_buy_days_counts_from_latest():
    # 連續三日皆買超
    assert chips.consecutive_buy_days({"2026-06-10": 700, "2026-06-11": 900, "2026-06-12": 1200}) == 3
    # 最近一日賣超 → streak 0；中斷後不續計
    assert chips.consecutive_buy_days({"2026-06-11": 900, "2026-06-12": -100}) == 0
    assert chips.consecutive_buy_days({"2026-06-10": -5, "2026-06-11": 900, "2026-06-12": 1200}) == 2


def test_buy_ratio_uses_total_window_volume():
    assert chips.buy_ratio(2800, {"a": 28000, "b": 25000, "c": 24000}) == round(2800 / 77000, 4)
    assert chips.buy_ratio(100, {}) is None      # 無量資料 → None（誠實降級）


def test_classify_marks_estimate_always():
    by_id = brokers.classify("1470", "台灣摩根士丹利", BMAP)
    assert by_id["kind"] == "外資" and by_id["confidence"] == "推估"
    by_kw = brokers.classify("9999", "美商美林", BMAP)
    assert by_kw["kind"] == "外資" and by_kw["confidence"] == "推估"
    fallback = brokers.classify("9200", "凱基-台北", BMAP)
    assert fallback["kind"] == "中實戶" and fallback["confidence"] == "推估"


def test_key_brokers_ranks_net_buyer_first():
    kb = chips.key_brokers(TSMC, min_net=1, bmap=BMAP)
    assert kb[0]["broker_id"] == "1470"          # 淨買超最多者
    top = kb[0]
    assert top["net"] == 2800 and top["days"] == 3
    assert top["identity"]["kind"] == "外資" and top["identity"]["confidence"] == "推估"
    # 凱基淨賣超 → 不入關鍵買盤
    assert all(b["broker_id"] != "9200" for b in kb)


def test_aggregate_by_identity_and_foreign():
    bmap = {"by_id": {}, "by_name_keyword": {"摩根": "外資", "高盛": "外資"}, "kinds": {}}
    # 三家外資買超 + 一家中實戶；賣超側不計
    tf = TargetFlows("2330", "台積電", _flows("2330", [
        ("2026-06-12", "1470", "台灣摩根士丹利", 1200),
        ("2026-06-12", "8440", "摩根大通", 800),
        ("2026-06-12", "9268", "美商高盛", 500),
        ("2026-06-12", "9200", "凱基-台北", 300),
        ("2026-06-12", "1110", "富邦", -900),
    ]), {})
    ident = chips.aggregate_by_identity(tf, bmap=bmap)
    assert ident["外資"]["net"] == 2500 and ident["外資"]["n"] == 3   # 摩根+摩根大通+高盛
    res = chips.analyze_target(tf, bmap=bmap)
    assert res["foreign_net"] == 2500 and res["foreign_n"] == 3
    sig = signals.d_foreign_branch({"chips": {"fund": res, "holdings": []}})
    assert sig and sig.detector == "FOREIGN_BRANCH_BUY"
    assert "3 家外資分點" in sig.headline and "推估" in sig.headline
    # 外資家數 < 2 → 不觸發
    assert signals.d_foreign_branch({"chips": {"fund": None, "holdings": []}}) is None


def test_analyze_and_compute_data_status():
    fund = TargetFlows("00991A", "復華台灣未來50", _flows("00991A", [
        ("2026-06-12", "1470", "台灣摩根士丹利", 500),
        ("2026-06-11", "1470", "台灣摩根士丹利", 300),
    ]), {"2026-06-12": 9000, "2026-06-11": 8000})

    assert chips.compute([])["data_status"] == "none"
    assert chips.compute([fund], fund_id="00991A", broker_map=BMAP)["data_status"] == "fund_only"
    assert chips.compute([TSMC], fund_id="00991A", broker_map=BMAP)["data_status"] == "holdings_only"
    full = chips.compute([fund, TSMC], fund_id="00991A", broker_map=BMAP)
    assert full["data_status"] == "full"
    assert full["fund"]["target_id"] == "00991A"
    assert full["holdings"][0]["target_id"] == "2330"
    assert "推估" in full["disclaimer"]


def test_smart_money_detector_fires_and_degrades():
    cx = chips.compute([TSMC], fund_id="00991A", broker_map=BMAP)
    sig = signals.d_smart_money({"chips": cx})
    assert sig is not None and sig.detector == "SMART_MONEY"
    assert "推估" in sig.headline and "非確認" in sig.headline
    assert sig.evidence["confidence"] == "推估" and sig.evidence["consecutive_days"] == 3
    # 無資料 → 不觸發（誠實降級，寧缺勿錯）
    assert signals.d_smart_money({"chips": {"data_status": "none"}}) is None
    assert signals.d_smart_money({}) is None


def test_idea_generator_real_vs_intel_stub():
    cx = chips.compute([TSMC], fund_id="00991A", broker_map=BMAP)
    real = ideas.g_chip_branch({"chips": cx}, {})
    assert real and real[0].status == "real" and "推估" in real[0].headline
    # 缺料 → 退回誠實 intel 樁（介面已就緒）
    stub = ideas.g_chip_branch({"chips": {"data_status": "none"}}, {})
    assert stub and stub[0].status == "intel"


# ───────────────────────── 主動ETF/投信法人籌碼（etfinfo 替代源）─────────────────────────
ACTIVE_ITEMS = [
    {"stockCode": "2327", "stockName": "國巨*", "industry": "電子零組件業",
     "reason": "4 檔 ETF / 3 家投信新進，後續加碼 6 筆",
     "metrics": [{"label": "新進 ETF", "value": "4 檔"}, {"label": "投信", "value": "3 家"},
                 {"label": "估算新進", "value": "+9.1 億"}, {"label": "估算加碼", "value": "+20.0 億"}],
     "tags": ["多 ETF 追買"]},
    {"stockCode": "2330", "stockName": "台積電", "industry": "半導體業",
     "reason": "1 檔 ETF 新進",
     "metrics": [{"label": "估算新進", "value": "+5,000 萬"}]},
]
FUND_HOLDINGS = [
    {"stock_id": "2327", "stock_name": "國巨股份", "weight": 8.9},
    {"stock_id": "2330", "stock_name": "台灣積體", "weight": 14.0},
    {"stock_id": "9999", "stock_name": "某不在清單股", "weight": 3.0},
]


def test_to_yi_parses_units():
    assert chips._to_yi("+9.1 億") == 9.1
    assert chips._to_yi("+5,000 萬") == 0.5         # 萬 → 億
    assert chips._to_yi(None) == 0.0


def test_institutional_flow_ranks_by_estimate():
    inst = chips.institutional_flow(FUND_HOLDINGS, ACTIVE_ITEMS)
    assert [r["stock_id"] for r in inst] == ["2327", "2330"]   # 9999 不在清單 → 排除
    top = inst[0]
    assert top["est_yi"] == 29.1 and top["n_etf"] == "4 檔" and top["n_sitc"] == "3 家"
    assert top["name"] == "國巨股份"               # 用本檔持股名（非 etfinfo 名）


def test_compute_includes_institutional_and_detector_fires():
    cx = chips.compute([], fund_id="00991A", fund_holdings=FUND_HOLDINGS,
                       active_items=ACTIVE_ITEMS, active_asof="2026-06-12")
    assert cx["data_status"] == "none"             # 無券商分點
    assert cx["institutional"] and cx["active_asof"] == "2026-06-12"
    sig = signals.d_institutional_buy({"chips": cx})
    assert sig is not None and sig.detector == "INSTITUTIONAL_BUY"
    assert "國巨股份" in sig.headline and "法人" in sig.headline
    # 純法人籌碼時：券商分點偵測器不觸發（兩源獨立、誠實降級）
    assert signals.d_smart_money({"chips": cx}) is None
    assert signals.d_institutional_buy({"chips": {"institutional": []}}) is None


def test_idea_generator_surfaces_institutional():
    cx = chips.compute([], fund_id="00991A", fund_holdings=FUND_HOLDINGS,
                       active_items=ACTIVE_ITEMS, active_asof="2026-06-12")
    ideas_out = ideas.g_chip_branch({"chips": cx}, {})
    assert any(i.status == "real" and "聰明錢共識" in i.headline for i in ideas_out)


def test_load_active_flow_reads_latest(tmp_path, monkeypatch):
    import json
    (tmp_path / "2026-06-11.json").write_text(json.dumps({"as_of": "2026-06-11", "items": []}), encoding="utf-8")
    (tmp_path / "2026-06-12.json").write_text(
        json.dumps({"as_of": "2026-06-12", "items": ACTIVE_ITEMS}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(chips, "ACTIVE_FLOW_DIR", tmp_path)
    asof, items = chips.load_active_flow()
    assert asof == "2026-06-12" and len(items) == 2     # 取最新日
    monkeypatch.setattr(chips, "ACTIVE_FLOW_DIR", tmp_path / "nope")
    assert chips.load_active_flow() == (None, [])        # 無目錄 → 誠實空


def test_curated_flows_drop_in_roundtrip(tmp_path, monkeypatch):
    import json
    from arm.connectors.brokers import base
    f = tmp_path / "2330.json"
    f.write_text(json.dumps({
        "target_id": "2330", "target_name": "台積電", "as_of": "2026-06-12",
        "day_volume": {"2026-06-12": 28000},
        "flows": [{"date": "2026-06-12", "broker_id": "1470",
                   "broker_name": "台灣摩根士丹利", "net": 1200}],
    }), encoding="utf-8")
    monkeypatch.setattr(base, "DROP_DIR", tmp_path)
    tf = base.curated_flows("2330")
    assert tf is not None and tf.target_name == "台積電"
    assert tf.flows[0].net == 1200 and tf.day_volume["2026-06-12"] == 28000
    assert base.curated_flows("9999") is None    # 無檔 → None
