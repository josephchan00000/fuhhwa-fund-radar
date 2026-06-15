#!/usr/bin/env python3
"""一次性回補各主角產品的每日 NAV/AUM 至 nav_history（M1-4）。

用法： python scripts/backfill_nav.py            # 全部主角
       python scripts/backfill_nav.py 00991A     # 指定一檔
首次較慢（逐交易日抓 assetsExcel），之後走 DB + http 快取增量。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import calendar as cal, config, db, navhist  # noqa: E402


def main(only: str | None = None) -> None:
    cfg = config.load()
    latest = cal.latest_trading_day()
    conn = db.connect()
    for p in cfg["fh_products"]:
        if only and p["id"] != only:
            continue
        days = cal.trading_days(p["inception"], latest)
        print(f"[{p['id']}] 交易日 {len(days)} 天（{p['inception']}→{latest}）回補中…")
        n = navhist.backfill(conn, p["id"], p["fund_id"], days, verbose=True)
        total = conn.execute("SELECT COUNT(*) FROM nav_history WHERE etf_id=?",
                             (p["id"],)).fetchone()[0]
        print(f"[{p['id']}] 新增 {n} 筆，nav_history 現有 {total} 筆。")
    conn.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
