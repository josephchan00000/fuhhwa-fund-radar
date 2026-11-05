"""夜盤探針（docs/lab_premarket_plan.md 第 7 節第 1 段）：清晨拿不拿得到台指期夜盤的收盤、最高、最低，資料掛在哪一天。
只在 CI 跑一次；只印、不寫任何檔。看兩個來源：
  ① 期交所 MIS getQuoteList：MarketType＝"1"（盤後）與 "0"（一般），台指期各月份與臺指現貨的成交價、高低、時間、日期。
  ② 期交所「期貨每日交易行情」下載（futDataDown，TX，最近兩天）：「交易時段」＝盤後的列，交易日期記在哪一天。
容器連不到期交所，不要在容器裡跑。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from arm.lab import txodata as T  # noqa: E402
from probe_txolive import TF, quotes, req, tf_body  # noqa: E402

TW = timezone(timedelta(hours=8))
KEYS = ("DispCName", "SymbolID", "CLastPrice", "COpenPrice", "CHighPrice", "CLowPrice", "CRefPrice", "CTime", "CDate",
        "CTotalVolume", "SettlementPrice", "Status")


def mis(market: str) -> None:
    body = {**tf_body("F", "TXF"), "MarketType": market}
    st, h, b, dt = req(TF + "getQuoteList", json.dumps(body).encode(),
                       headers={"Content-Type": "application/json;charset=UTF-8", "Origin": "https://mis.taifex.com.tw"})
    try:
        q = quotes(json.loads(b.decode("utf-8")))
    except Exception:                                                     # noqa: BLE001
        q = []
    print(f"\n=== MIS getQuoteList MarketType={market}：HTTP {st}，{dt*1000:.0f} ms，{len(q)} 筆", flush=True)
    for x in q:
        print("   ", {k: x.get(k) for k in KEYS})
    if not q:
        print("    回應", b[:300])


def daily() -> None:
    now = datetime.now(TW)
    a, z = now - timedelta(days=4), now
    try:
        b = T._get(T.TFX + "/cht/3/futDataDown", {"down_type": "1", "commodity_id": "TX", "commodity_id2": "",
                                                   "queryStartDate": f"{a:%Y/%m/%d}", "queryEndDate": f"{z:%Y/%m/%d}"})
    except Exception as e:                                                # noqa: BLE001
        print("\n=== futDataDown 失敗", type(e).__name__, e)
        return
    txt = b.decode("cp950", "replace")
    lines = [x for x in txt.splitlines() if x.strip()]
    print(f"\n=== futDataDown TX {a:%m/%d}～{z:%m/%d}：{len(lines)} 行", flush=True)
    print("    表頭", lines[:1])
    for x in lines[1:]:
        if ",TX," in x.replace(" ", "") or x.split(",")[1].strip() == "TX":
            print("   ", x)


def main() -> int:
    print(f"[night] 開始 {datetime.now(TW):%F %H:%M:%S}（台北）", flush=True)
    mis("1")
    mis("0")
    daily()
    print(f"\n[night] 結束 {datetime.now(TW):%H:%M:%S}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
