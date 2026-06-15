"""券商分點多日歷史測試（M3 延伸）：快照累積 → 窗 → 真實連續買超天數（含缺席中斷）。"""
from arm import chips
from arm.connectors.brokers import history
from arm.connectors.brokers.base import BrokerFlow


def _bf(date, name, net):
    return BrokerFlow("2330", date, name, name, net)


def test_record_and_load_window(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "STORE", tmp_path)
    history.record("2330", "2026-06-10", [_bf("2026-06-10", "美林", 700)])
    history.record("2330", "2026-06-11", [_bf("2026-06-11", "美林", 900)])
    history.record("2330", "2026-06-12", [_bf("2026-06-12", "美林", 1200), _bf("2026-06-12", "台新", -500)])
    assert history.stored_dates("2330") == ["2026-06-10", "2026-06-11", "2026-06-12"]

    tf = history.load_window("2330", days=6)
    assert tf is not None and tf.as_of == "2026-06-12"
    assert len({f.date for f in tf.flows}) == 3
    kb = chips.key_brokers(tf, min_net=1)
    top = next(b for b in kb if b["broker_name"] == "美林")
    assert top["net"] == 2800 and top["days"] == 3 and top["window_days"] == 3   # 連 3 日真實


def test_window_limit_and_idempotent_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "STORE", tmp_path)
    for d, net in [("2026-06-08", 1), ("2026-06-09", 2), ("2026-06-10", 3),
                   ("2026-06-11", 4), ("2026-06-12", 5)]:
        history.record("2330", d, [_bf(d, "美林", net)])
    history.record("2330", "2026-06-12", [_bf("2026-06-12", "美林", 99)])   # 同日覆寫
    tf = history.load_window("2330", days=3)
    assert sorted({f.date for f in tf.flows}) == ["2026-06-10", "2026-06-11", "2026-06-12"]
    assert sum(f.net for f in tf.flows if f.date == "2026-06-12") == 99      # 冪等覆寫


def test_streak_breaks_when_broker_absent_one_day(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "STORE", tmp_path)
    history.record("2330", "2026-06-10", [_bf("2026-06-10", "美林", 700)])
    history.record("2330", "2026-06-11", [_bf("2026-06-11", "台新", 300)])   # 美林當日未上榜
    history.record("2330", "2026-06-12", [_bf("2026-06-12", "美林", 1200)])
    tf = history.load_window("2330", days=6)
    mer = next(b for b in chips.key_brokers(tf, min_net=1) if b["broker_name"] == "美林")
    assert mer["days"] == 1            # 6/11 缺席 → 連續中斷、只算最近 1 日（非跨缺席的 2）


def test_prune_keeps_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "STORE", tmp_path)
    for i in range(1, 11):
        history.record("2330", f"2026-06-{i:02d}", [_bf("x", "美林", 1)])
    history.prune("2330", keep=3)
    assert len(history.stored_dates("2330")) == 3


def test_consecutive_buy_days_gap_aware():
    by = {"2026-06-12": 1200, "2026-06-10": 700}        # 6/11 缺
    # 不給 all_dates：只看有資料日 → 視為連續 2
    assert chips.consecutive_buy_days(by) == 2
    # 給窗內完整交易日 → 6/11 缺席中斷 → 1
    assert chips.consecutive_buy_days(by, ["2026-06-10", "2026-06-11", "2026-06-12"]) == 1
