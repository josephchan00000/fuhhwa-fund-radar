"""籌碼雷達資料層：每日分片讀寫。

分片＝`data/lab/{kind}/{YYYY-MM-DD}.json.gz`，**一天一檔、只增不改舊檔**——
大 JSON 每天整份重寫會讓 repo 一年多出數百 MB；分片每輪只新增／更新當天那一小檔。

輸出必須「決定性」（排序鍵、gzip mtime=0）：內容沒變時位元組完全相同，
git 看不到 diff、不產生空 commit。
"""
from __future__ import annotations

import gzip
import io
import json
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data" / "lab"

# 分片保留天數（日曆天）；超過自動清。⚠ 長線回測要兩年以上的投信／價量史——
# 2026-10-14 原設 400 天，上線第一班 daily 就把 2024-11～2025-09 的投信回補刪掉（從 git 史還原）
KEEP_DAYS = 1100


def path(kind: str, d: str) -> Path:
    return LAB / kind / f"{d}.json.gz"


def _dump(doc) -> bytes:
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(raw)
    return buf.getvalue()


def write(kind: str, d: str, doc) -> bool:
    """寫分片；內容與既有檔相同則不動（回 False）。"""
    p = path(kind, d)
    data = _dump(doc)
    if p.exists() and p.read_bytes() == data:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return True


def read(kind: str, d: str):
    p = path(kind, d)
    if not p.exists():
        return None
    try:
        return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8"))
    except Exception:                                     # noqa: BLE001 —— 壞檔視同不存在
        return None


def dates(kind: str) -> list[str]:
    d = LAB / kind
    if not d.exists():
        return []
    # 用副檔名切、不要固定取前 10 字：月份分片叫 2026-09.json.gz，前 10 字會變成「2026-09.js」
    #（2026-10-14 踩坑：月營收整份讀不到，長線篩選的成長關全數落空）
    return sorted(p.name[:-len(".json.gz")] for p in d.glob("*.json.gz"))


def load(kind: str, *, since: str | None = None, last: int | None = None) -> list[tuple[str, dict]]:
    ds = dates(kind)
    if since:
        ds = [x for x in ds if x >= since]
    if last:
        ds = ds[-last:]
    out = []
    for x in ds:
        doc = read(kind, x)
        if doc is not None:
            out.append((x, doc))
    return out


def read_json(name: str, default=None):
    p = LAB / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return default


def write_json(name: str, doc) -> bool:
    p = LAB / name
    txt = json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=0)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True


def prune(kind: str, *, today: date, keep_days: int = KEEP_DAYS) -> int:
    cut = (today - timedelta(days=keep_days)).isoformat()
    n = 0
    for x in dates(kind):
        if x < cut:
            path(kind, x).unlink(missing_ok=True)
            n += 1
    return n
