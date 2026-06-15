"""集保 TDCC 受益人數連接器（M1-5）——「X 萬人選擇復華」的權威佐證。

來源：TDCC 開放資料「集保戶股權分散表」(id=1-5)，每週更新，含所有上市櫃證券，
每檔 17 個分級列，第 17 列為「合計」→ 人數即受益人數、股數即集保總庫存。

注意：TDCC 政府憑證在 OpenSSL 嚴格模式（Missing Subject Key Identifier）下無法被
certifi 驗證；為「不關閉 TLS 驗證」又能取得資料，改用系統 curl（走 macOS 系統信任庫，
仍有驗證）。取不到時回退 (None, None)，讓流程優雅降級（規模面仍可由 AUM 撐起）。

受益人數為週更，週增需跨週快照相減 → 落地 holders_history，隨系統每週累積。
"""
from __future__ import annotations

import csv
import subprocess
import time
from pathlib import Path

from .. import db

URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "http_cache" / "tdcc_1-5.csv"
TOTAL_LEVEL = "17"          # 第 17 分級 = 合計


def _fetch_csv(ttl: int = 12 * 3600) -> str | None:
    if CACHE.exists() and (time.time() - CACHE.stat().st_mtime) < ttl:
        return CACHE.read_text(encoding="utf-8-sig")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["curl", "-sS", "--max-time", "90", URL, "-o", str(CACHE)],
                       check=True, capture_output=True, timeout=120)
    except Exception:
        return CACHE.read_text(encoding="utf-8-sig") if CACHE.exists() else None
    return CACHE.read_text(encoding="utf-8-sig") if CACHE.exists() else None


def holders_table() -> dict[str, tuple[int, str]]:
    """{證券代號: (受益人數, 資料日YYYYMMDD)}；取不到回 {}。"""
    txt = _fetch_csv()
    if not txt:
        return {}
    out: dict[str, tuple[int, str]] = {}
    for r in csv.DictReader(txt.splitlines()):
        if r.get("持股分級") == TOTAL_LEVEL:
            try:
                out[r["證券代號"]] = (int(r["人數"]), r["資料日期"])
            except (ValueError, KeyError):
                continue
    return out


def holders_change(conn, etf_id: str) -> tuple[int | None, int | None]:
    """回傳 (最新受益人數, 跨週淨增)；落地週快照供日後比對。取不到回 (None, None)。"""
    table = holders_table()
    cur = table.get(etf_id)
    if not cur:
        # 沒抓到當期 → 用 DB 最後一筆（不報週增）
        row = conn.execute("SELECT holders FROM holders_history WHERE etf_id=? "
                           "ORDER BY data_date DESC LIMIT 1", (etf_id,)).fetchone()
        return (row[0] if row else None), None
    holders, ddate = cur
    iso = f"{ddate[:4]}-{ddate[4:6]}-{ddate[6:8]}"
    db.upsert(conn, "holders_history", {"etf_id": etf_id, "data_date": iso, "holders": holders})
    conn.commit()
    prev = conn.execute("SELECT holders FROM holders_history WHERE etf_id=? AND data_date<? "
                        "ORDER BY data_date DESC LIMIT 1", (etf_id, iso)).fetchone()
    chg = (holders - prev[0]) if prev else None
    return holders, chg
