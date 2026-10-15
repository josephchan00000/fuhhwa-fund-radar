"""診斷：FinMind 日 K 是否混進「興櫃」（掛牌前）交易，以及怎麼分辨（只印到 CI 日誌，不寫檔）。

對每一檔：官方上市／上櫃日（證交所、櫃買 openapi 公司基本資料）vs FinMind 第一筆日 K、第一筆三大法人；
官方日前後的「收盤 − 漲跌價差 = 前一日收盤」一致比例、單日漲跌超過 10.5% 的比例，並列出官方日前後幾列。
用法：python scripts/diag_listing.py 6488 7769 ...
"""

from __future__ import annotations

import re
import sys

import pandas as pd
import requests

from superstock.config import get_token, load_config
from superstock.finmind_client import FinMindClient

OFFICIAL = {"twse": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "tpex": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"}
_LIST_KEY = re.compile(r"上市日期|上櫃日期|ListingDate|Listing_Date|DateOfListing", re.I)
_CODE_KEY = re.compile(r"代號|代碼|Code|code")


def iso(v) -> str | None:
    s = re.sub(r"[^\d/.-]", "", str(v or "").strip())
    m = re.match(r"^(\d{2,4})[/.-](\d{1,2})[/.-](\d{1,2})$", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    elif s.isdigit() and len(s) in (7, 8):
        y, mo, d = int(s[:-4]), int(s[-4:-2]), int(s[-2:])
    else:
        return None
    if y < 1911:
        y += 1911
    return f"{y:04d}-{mo:02d}-{d:02d}"


def official() -> dict[str, tuple[str, str]]:
    out = {}
    for mkt, url in OFFICIAL.items():
        try:
            rows = requests.get(url, timeout=30).json()
        except Exception as exc:  # noqa: BLE001
            print(f"[官方] {mkt} 失敗：{exc}")
            continue
        n = 0
        for r in rows:
            code = next((str(v).strip() for k, v in r.items() if _CODE_KEY.search(str(k))), None)
            d = next((iso(v) for k, v in r.items() if _LIST_KEY.search(str(k))), None)
            if code and d:
                out[code] = (d, mkt)
                n += 1
        print(f"[官方] {mkt} {len(rows)} 列、有日期 {n}；鍵名={list(rows[0])[:20] if rows else []}")
    return out


def main(codes: list[str]) -> None:
    cfg = load_config("config.yaml")
    client = FinMindClient(get_token(cfg), cfg.finmind)
    off = official()
    for code in codes:
        o = off.get(code)
        p = client.get("TaiwanStockPrice", code, "2008-01-01", pd.Timestamp.now().date().isoformat())
        inst = client.get("TaiwanStockInstitutionalInvestorsBuySell", code, "2008-01-01",
                          pd.Timestamp.now().date().isoformat())
        if p.empty:
            print(f"== {code}: 沒有日 K")
            continue
        p = p.sort_values("date").reset_index(drop=True)
        p["prev"] = p["close"].shift(1)
        p["match"] = (p["close"] - p["spread"] - p["prev"]).abs() <= 0.011
        p["ret"] = p["close"] / p["prev"] - 1
        p["big"] = p["ret"].abs() > 0.105
        first_inst = str(inst["date"].min()) if not inst.empty else "—"
        print(f"== {code} 官方 {o} FinMind 日K {p['date'].iloc[0]}～{p['date'].iloc[-1]}（{len(p)} 列）"
              f" 法人首日 {first_inst}")
        if o:
            before, after = p[p["date"] < o[0]], p[p["date"] >= o[0]]
            for name, g in (("官方日前", before), ("官方日後", after)):
                if len(g) > 1:
                    print(f"   {name} {len(g)} 列：價差一致 {g['match'].iloc[1:].mean():.1%}、"
                          f"|漲跌|>10.5% {g['big'].mean():.1%}、成交筆數中位 {g['Trading_turnover'].median():.0f}、"
                          f"開盤=0 {(g['open'] == 0).mean():.1%}")
            k = int(p["date"].searchsorted(o[0]))
            show = p.iloc[max(0, k - 4):k + 3]
        else:
            show = p.head(5)
        cols = ["date", "open", "max", "min", "close", "spread", "Trading_Volume", "Trading_turnover", "match"]
        print(show[cols].to_string(index=False))
        print("   最前 2 列：", p[cols].head(2).to_dict("records"))


if __name__ == "__main__":
    main(sys.argv[1:])
