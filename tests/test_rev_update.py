"""月營收分片只增不減（2026-10-29 踩坑：上櫃那一支沒抓到，只剩上市的結果蓋掉了整個 9 月）。"""
from datetime import date

from arm.lab import collect, market, store


def _setup(monkeypatch, tmp_path, fetched):
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(market, "fetch_revenue", lambda: fetched)
    monkeypatch.setattr(market, "log", lambda *a, **k: None)
    monkeypatch.setattr(collect.clock, "today_tw", lambda: date(2026, 10, 29))


def test_partial_fetch_keeps_existing_companies(monkeypatch, tmp_path):
    full = {f"{1000 + i}": [100.0, 1.0, 1.0] for i in range(1980)}
    _setup(monkeypatch, tmp_path, ("2026-09", {f"{1000 + i}": [200.0, 2.0, 2.0] for i in range(1087)}))
    store.write("rev", "2026-09", {"ym": "2026-09", "s": full, "src": "mops"})
    assert collect.update_revenue()
    doc = store.read("rev", "2026-09")
    assert len(doc["s"]) == 1980 and doc["src"] == "mops"
    assert doc["s"]["1000"] == [200.0, 2.0, 2.0] and doc["s"]["2979"] == [100.0, 1.0, 1.0]


def test_same_data_does_not_rewrite(monkeypatch, tmp_path):
    full = {f"{1000 + i}": [100.0, 1.0, 1.0] for i in range(1200)}
    _setup(monkeypatch, tmp_path, ("2026-09", dict(full)))
    store.write("rev", "2026-09", {"ym": "2026-09", "s": full})
    assert not collect.update_revenue()


def test_fetch_keeps_only_newest_month(monkeypatch):
    rows = {market.REV_URLS[0]: [{"公司代號": "2330", "資料年月": "11510", "營業收入-當月營收": "1"}],
            market.REV_URLS[1]: [{"公司代號": "3081", "資料年月": "11509", "營業收入-當月營收": "2"}]}
    import json
    monkeypatch.setattr(market, "get_bytes", lambda url, **k: json.dumps(rows[url]).encode())
    monkeypatch.setattr(market, "log", lambda *a, **k: None)
    ym, out = market.fetch_revenue()
    assert ym == "2026-10" and set(out) == {"2330"}


def test_committed_months_are_not_half_empty():
    """入庫的每個月營收分片：2020 年起每個月都要有上市與上櫃（≥ 1,700 家）。"""
    for ym in store.dates("rev"):
        if ym >= "2020-01":
            assert len((store.read("rev", ym) or {}).get("s") or {}) >= 1700, ym
