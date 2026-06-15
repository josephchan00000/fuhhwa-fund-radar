"""跨家持股差異化引擎單元測試（M2）：主動度/獨門/偏離/重疊/領先/降級。"""
from arm import diff_engine as de
from arm.connectors.issuers.base import Holding


def _h(fund, *pairs):
    """pairs: (stock_id, weight[, name])。"""
    return [Holding(fund, "2026-06-12", sid, (extra[0] if extra else sid), w)
            for sid, w, *extra in pairs]


# 復華：台積電 30、聯發科 20、獨門A 25、獨門B 25（合計 100）
FUND = _h("00991A", ("2330", 30, "台積電"), ("2454", 20, "聯發科"),
          ("9999", 25, "獨門A"), ("8888", 25, "獨門B"))
# 競品一：台積電 50、聯發科 10、其他X 40（不持有 9999/8888）
P1 = _h("00981A", ("2330", 50), ("2454", 10), ("1111", 40))
# 競品二：台積電 45、聯發科 15、9999 5、其他Y 35
P2 = _h("00992A", ("2330", 45), ("2454", 15), ("9999", 5), ("2222", 35))
PEERS = [("統一00981A", P1), ("群益00992A", P2)]
BENCH = _h("0050", ("2330", 52), ("2454", 4), ("2317", 44))


def test_active_share_basic():
    # 對齊 100%：fund {2330:30,2454:20} vs bench {2330:52,2454:4,2317:44}
    # 0.5*(|30-52|+|20-4|+|25-0|+|25-0|+|0-44|) = 0.5*(22+16+25+25+44)=66
    a = de.active_share(FUND, BENCH)
    assert a == 66.0


def test_active_share_none_without_bench():
    assert de.active_share(FUND, []) is None


def test_unique_holdings():
    uq = de.unique_holdings(FUND, PEERS, max_peer_ratio=0.34)
    ids = {u["stock_id"] for u in uq}
    # 8888 無人持有 → 獨門；9999 被 1/2=50% 持有 → 超過門檻、非獨門
    assert "8888" in ids and "9999" not in ids
    u8 = next(u for u in uq if u["stock_id"] == "8888")
    assert u8["uniqueness"] == 1.0 and u8["peers_holding"] == 0


def test_divergence_zscore_and_overweight():
    dv = de.divergence(FUND, PEERS)
    by = {d["stock_id"]: d for d in dv}
    # 台積電：30 − mean(50,45)=47.5 → −17.5（低配）
    assert by["2330"]["diff"] == -17.5
    # 獨門B：25 − mean(0,0)=0 → +25（最大偏離，排第一）
    assert dv[0]["stock_id"] == "8888" and dv[0]["diff"] == 25.0
    assert all("z" in d for d in dv)


def test_lead_positions():
    leads = de.lead_positions(FUND, PEERS, min_weight=3.0)
    ids = {l["stock_id"] for l in leads}
    # 9999：復華 25 > 競品二 5 → 領先；2330：復華 30 < 競品 50/45 → 非領先
    assert "9999" in ids and "2330" not in ids
    l = next(x for x in leads if x["stock_id"] == "9999")
    assert l["peer_max"] == 5.0


def test_overlaps_jaccard_and_weight():
    ov = de.overlaps(FUND, PEERS)
    o1 = next(o for o in ov if o["peer"] == "統一00981A")
    # 共同持股 = {2330,2454}；union = {2330,2454,9999,8888,1111}=5 → 2/5
    assert o1["n_common"] == 2 and o1["jaccard"] == 0.4
    # 權重重疊 = min(30,50)+min(20,10)=30+10=40
    assert o1["weight_overlap"] == 40.0


def test_bet_performance_sorted():
    bets = de.bet_performance(
        [{"stock_id": "8888", "name": "獨門B", "weight": 25}],
        {"8888": 0.05})
    assert bets and bets[0]["today_pct"] == 0.05


def test_compute_data_status_degrades():
    assert de.compute(FUND)["data_status"] == "none"
    assert de.compute(FUND, benchmark=BENCH)["data_status"] == "benchmark_only"
    assert de.compute(FUND, peers=PEERS)["data_status"] == "peers_only"
    full = de.compute(FUND, benchmark=BENCH, peers=PEERS, price_lookup={"8888": 0.05})
    assert full["data_status"] == "full"
    assert full["active_share"] == 66.0 and full["unique"] and full["bets"]


def test_normalize_handles_uneven_sum():
    # 復華 equity 合計 98（含現金）vs 0050 合計 100 → 正規化後仍可比、不爆
    fund98 = _h("00991A", ("2330", 49), ("2454", 49))   # 合計 98
    a = de.active_share(fund98, _h("0050", ("2330", 50), ("2454", 50)))
    assert a == 0.0   # 正規化後 50/50 vs 50/50 → 主動度 0
