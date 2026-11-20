"""財報彙總表補抓時機（arm/lab/v3data._fs_todo；2026-11-20 加期限後 2～7 天那一段）。"""
from arm.lab import store
from arm.lab import v3data as V


def test_refetch_windows(monkeypatch):
    docs = {"2026Q3": {p: {"x": {}} for p in V.FS_PARTS} | {"at": {p: "2026-11-15" for p in V.FS_PARTS}}}
    monkeypatch.setattr(V, "_quarters_due", lambda: [(2026, 3)])
    monkeypatch.setattr(store, "read", lambda kind, key: docs.get(key))
    assert V._fs_todo("2026-11-15") == []                                   # 期限隔天剛抓過
    assert len(V._fs_todo("2026-11-20")) == len(V.FS_PARTS)                 # 第 2～7 天：補抓一次
    docs["2026Q3"]["at"] = {p: "2026-11-20" for p in V.FS_PARTS}
    assert V._fs_todo("2026-11-21") == []                                   # 這一段已補過
    assert len(V._fs_todo("2026-11-28")) == len(V.FS_PARTS)                 # 第 14～45 天：再補一次
