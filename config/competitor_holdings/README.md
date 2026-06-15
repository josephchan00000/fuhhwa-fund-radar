# 競品逐日持股 drop-in（跨家持股差異化的 Tier B 承接層）

跨家「獨門股／重疊／領先卡位」需要**競品每日持股**。已查證：各投信官網皆為
SPA、無單一乾淨公開 JSON（見 docs/SPEC.md §18.1）。因此差異化引擎採
**source-agnostic** 設計——只要把競品持股放成下列格式檔，引擎就會立即計算，
**無需改任何程式碼**。

## 檔名規則
```
config/competitor_holdings/{fund_id}.json     例：00981A.json、00992A.json
```
`_` 開頭的檔（如 `_SAMPLE_00981A.json`）= 範例/說明，**不會被載入**。

## 格式（與 0050 benchmark 同結構）
```json
{
  "fund_id": "00981A",
  "issuer": "統一",
  "as_of": "2026-06-12",
  "tier": "B",
  "provenance": "來源說明（手動下載/第三方彙整/逐家 adapter），務必標明",
  "holdings": [
    {"stock_id": "2330", "stock_name": "台積電", "weight": 18.5, "shares": 1200000},
    {"stock_id": "2317", "stock_name": "鴻海",   "weight": 6.2,  "shares": 800000}
  ]
}
```
- `weight` 為百分比（與復華持股一致，0–100）；引擎會對 equity 權重正規化到 100% 再比。
- `shares` 可省略（差異化只用 weight）。
- 已宣告的競品清單見 `arm/connectors/issuers/__init__.py` 的 `COMPETITORS`。

## 落地路線（擇一補實，引擎不變）
0. **✅ etfinfo.tw（已接，預設）**：`python scripts/fetch_etfinfo.py holdings` 會自動把
   `arm/connectors/issuers/__init__.py` 的 `COMPETITORS` 全部抓下來、落成本目錄的 `{code}.json`
   （`source` 多為 issuer-official，標 as-of/provenance/Tier B）。本目錄現有的 `00981A.json` 等
   即由此產生——**數字屬「先給可能值」，上線前請以投信官網/公開說明書核對**。
1. **逐家投信 adapter**：在 `arm/connectors/issuers/` 加一家解析器，輸出統一 `Holding`
   （如復華已完成的 `assetsExcel`）。把結果寫成本目錄的 json，或讓 adapter 直接回傳。
2. **其他第三方彙整源**：CMoney／玩股網／付費資料，下載後落成本格式，`tier` 標 B。
