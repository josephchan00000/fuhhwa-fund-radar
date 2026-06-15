# 主動ETF/投信籌碼追蹤 drop-in（§18.4 聰明錢的法人層級替代源）

§18.4「籌碼分點推敲」的理想資料是**券商分點買賣超**（個別買家），但無公開 live 源
（證交所驗證碼、第三方 SPA/付費）。在此之前，etfinfo.tw 提供**法人層級**的可得替代：
「哪些個股被多檔主動ETF / 多家投信**估算新進/加碼**」。

> ⚠️ **Tier B**：這是**主動ETF/投信(集合)層級**的籌碼，**不是個別券商分點、不是實名買家**。
> 金額為 etfinfo「依最新收盤價估算」，標『estimated・待核對』。上線前以投信公告核實。

## 來源與更新
```
python scripts/fetch_etfinfo.py active      # 取 etfinfo /api/active/tracking → 本目錄 {date}.json
```
管線（`arm/chips.load_active_flow`）讀**最新一份** `{date}.json`，與本檔持股取交集，
產出「重倉○○ 同步獲 N 檔 ETF / M 家投信買盤、估算 +Z 億（聰明錢共識）」。

## 格式（由 `scripts/fetch_etfinfo.py` 產生）
```json
{
  "as_of": "2026-06-12", "side": "buy", "tier": "B",
  "provenance": "etfinfo.tw /api/active/tracking（法人層級非券商分點）；Tier B，待核對",
  "meta": { "snapshotRangeDays": 30, "...": "..." },
  "items": [
    { "stockCode": "2327", "stockName": "國巨*", "industry": "電子零組件業",
      "reason": "4 檔 ETF / 3 家投信新進，後續加碼 6 筆",
      "metrics": [ { "label": "估算新進", "value": "+9.1 億" },
                   { "label": "估算加碼", "value": "+20.0 億" } ] }
  ]
}
```
`_` 開頭或非 `{date}.json` 命名的檔不會被當成最新快照載入。
