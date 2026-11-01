"""集保 TDCC 開放資料連接器：集保戶股權分散表（id=1-5）的原始 CSV。

來源：TDCC 開放資料「集保戶股權分散表」(id=1-5)，每週更新，含所有上市櫃證券，每檔 17 個分級列。
籌碼雷達用它算大戶持股（arm/lab/market.py 呼叫 _fetch_csv）。

注意：TDCC 政府憑證在 OpenSSL 嚴格模式（Missing Subject Key Identifier）下無法被
certifi 驗證；為「不關閉 TLS 驗證」又能取得資料，改用系統 curl（走系統信任庫，仍有驗證）。取不到回 None。

2026-11-01 拿掉舊的本機流程時，只有它在用的受益人數週增（holders_table、holders_change，寫 SQLite）
與 arm/db.py 一起拿掉（要看從 git 歷史找）。
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "http_cache" / "tdcc_1-5.csv"


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

