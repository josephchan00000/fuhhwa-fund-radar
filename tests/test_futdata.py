"""台指期早盤策略資料層（arm/lab/futdata.py）：解析、差分編碼、只增不改。"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date

import pytest

from arm.lab import futdata as F
from arm.lab import store

HEAD = "成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價 "
CSV = "\n".join([
    HEAD,
    "20261026,TX     ,202611     ,150000,46100,4,-,-,*",          # 夜盤（前一天日期）：不收
    "20261027,BRF    ,202612     ,151937,3630.5,2,-,-, ",          # 別的商品：不收
    "20261027,TX     ,202611     ,084500,46505,466,-,-,*",         # 開盤集合競價
    "20261027,TX     ,202611     ,084500,46505,2,-,-,",
    "20261027,TX     ,202611     ,084500,46506,2,-,-,",
    "20261027,TX     ,202611     ,085905,46733,2,-,-,",
    "20261027,TX     ,202611/202612,090000,-37,2,46700,46663,",   # 價差單：不收
    "20261027,TX     ,202612     ,090001,46650,2,-,-,",
    "20261027,TX     ,202611     ,134459,46081,2,-,-,",
    "20261027,TX     ,202611     ,150500,46090,2,-,-,",           # 15:05：日盤以外
])


def test_parse_keeps_tx_day_session_single_month_in_file_order():
    rows = F.parse_csv(CSV, date(2026, 10, 27))
    assert set(rows) == {"202611", "202612"}
    r = rows["202611"]
    assert [x[0] for x in r] == [31500, 31500, 31500, 32345, 49499]
    assert [x[1] for x in r] == [46505, 46505, 46506, 46733, 46081]
    assert [x[2] for x in r] == [466, 2, 2, 2, 2]
    assert [x[3] for x in r] == [True, False, False, False, False]
    assert rows["202612"] == [(32401, 46650, 2, False)]


def test_parse_rejects_wrong_header():
    with pytest.raises(ValueError):
        F.parse_csv("a,b,c\n1,2,3", date(2026, 10, 27))


def test_encode_decode_roundtrip():
    rows = F.parse_csv(CSV, date(2026, 10, 27))["202611"]
    enc = F.encode(rows)
    assert enc["t"][0] == 31500 and enc["p"][0] == 46505 and enc["a"] == [0]
    assert F.decode(enc) == rows


def test_fetch_day_and_store_append_only(tmp_path, monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Daily_2026_10_27.csv", CSV.encode("cp950"))
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(F, "_get", lambda url, timeout=120: buf.getvalue())
    doc = F.fetch_day(date(2026, 10, 27))
    assert doc["d"] == "2026-10-27" and set(doc["c"]) == {"202611", "202612"}
    assert store.write(F.KIND_TX, "2026-10-27", doc)
    got = F.load_day("2026-10-27")
    assert got["202611"][0] == (31500, 46505, 466, True)
    # 同一天再跑：清單上已經有的日子不再抓
    calls = []
    monkeypatch.setattr(F, "fetch_day", lambda d: calls.append(d))
    monkeypatch.setattr(F, "fetch_idx", lambda d: None)
    F.update(days=[date(2026, 10, 27)])
    assert calls == []


def test_fetch_day_not_zip_returns_none(monkeypatch):
    monkeypatch.setattr(F, "_get", lambda url, timeout=120: b"<HTML>gone</HTML>")
    assert F.fetch_day(date(2026, 8, 18)) is None


def _idx_doc(n: int = F.IDX_N, start: float = 46041.43):
    rows = []
    for k in range(n):
        s = 9 * 3600 + 5 * k
        rows.append([f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}", f"{start + k * 0.01:,.2f}", "1"])
    return {"stat": "OK", "data": rows}


def test_fetch_idx_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "LAB", tmp_path)
    monkeypatch.setattr(F, "_get", lambda url, timeout=60: json.dumps(_idx_doc()).encode())
    doc = F.fetch_idx(date(2026, 10, 27))
    assert len(doc["v"]) == F.IDX_N
    store.write(F.KIND_IDX, "2026-10-27", doc)
    v = F.load_idx("2026-10-27")
    assert v[0] == pytest.approx(46041.43) and v[1] == pytest.approx(46041.44) and len(v) == F.IDX_N


def test_fetch_idx_refuses_partial_day(monkeypatch):
    monkeypatch.setattr(F, "_get", lambda url, timeout=60: json.dumps(_idx_doc(200)).encode())
    assert F.fetch_idx(date(2026, 10, 27)) is None


def test_near_contract():
    assert F.near("2026-10-27", {"202611": 1, "202612": 1}) == "202611"
    assert F.near("2026-10-21", {"202610": 1, "202611": 1}) == "202610"   # 結算日當天
    assert F.near("2026-10-21", {}) is None


def test_fut_shards_are_never_pruned():
    from arm.lab import collect
    import inspect
    src = inspect.getsource(collect.prune_all)
    assert "fut" not in src            # 期交所只留 30 天，存下來的不能清
