"""同類排名引擎單元測試（M1-8）：分類、名次、被比下去、YTD 公平性。"""
from arm import peers


def test_is_tw_equity_filters_foreign_and_bond():
    assert peers.is_tw_equity("主動台灣未來50", "00991A")
    assert not peers.is_tw_equity("主動復華全球金融股息", "00998A")   # 全球 → 排除
    assert not peers.is_tw_equity("主動國泰智能電動車", "009D")        # 非 A 結尾 → 排除
    assert not peers.is_tw_equity("主動野村臺灣優選非投等債", "00985B")


def _table():
    return {
        "00991A": {"name": "復華", "ret": {"ytd": 0.80, "3m": 0.40}},
        "00981A": {"name": "統一", "ret": {"ytd": 0.50, "3m": 0.30}},
        "00992A": {"name": "群益", "ret": {"ytd": 0.60, "3m": None}},
    }


def test_rank_of():
    rank, n = peers.rank_of("00991A", _table(), "ytd")
    assert rank == 1 and n == 3
    rank2, n2 = peers.rank_of("00981A", _table(), "ytd")
    assert rank2 == 3 and n2 == 3
    # 3m 只有兩檔有值 → 樣本數 2
    rank3, n3 = peers.rank_of("00991A", _table(), "3m")
    assert rank3 == 1 and n3 == 2


def test_beaten_lists_lower_peers_named_first():
    bl = peers.beaten("00991A", _table(), "ytd")
    codes = [b["code"] for b in bl]
    assert set(codes) == {"00981A", "00992A"}
    # 重點競品（issuer 有值）優先 + 差距大者在前
    assert all(b["gap"] > 0 for b in bl)


def test_beaten_none_when_target_missing_period():
    assert peers.beaten("00992A", _table(), "3m") == []   # 群益 3m 無值
