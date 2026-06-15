# 分點買賣超 drop-in（籌碼推敲的人工/第三方覆蓋層）

> **預設已接 Histock live**（`arm/connectors/brokers/histock.py`）：`brokers.load_flows`
> 會先讀本目錄的 `{code}.json`，**沒有才**自動抓 Histock「分公司進出」頁。所以本目錄
> 平常可留空；要**覆蓋**某檔（人工修正/換第三方來源）時才落檔。

籌碼「關鍵分點大買→推估買家」需要**券商分點買賣超**。證交所 `bsr.twse.com.tw` 為
「逐檔 + 驗證碼」、Wantgoo 會員制 → 不易自動化；**Histock 把當日買超/賣超前 N 大分點
放在靜態 HTML 表**（無 API/登入），已接為預設 live。引擎採 **source-agnostic**：只要把
分點資料放成下列格式檔，就**優先**於 live 生效、**無需改任何程式碼**。

> ⚠️ **鐵則**：分點只到分公司層級，買家真實身份**無法 100% 確認**。所有買家推論一律
> 標『推估・非確認』（§18.4）。

## 檔名規則
```
config/broker_flows/{target_id}.json
```
- `target_id` = 標的代號：可為**復華 ETF 本身**（如 `00991A.json`）或**重倉成分股**（如 `2330.json`）。
- 管線每天會對「本檔 + 當日前 5 大重倉股」嘗試載入；落檔即生效。

## 格式
```json
{
  "target_id": "2330",
  "target_name": "台積電",
  "as_of": "2026-06-12",
  "tier": "B",
  "provenance": "來源說明（證交所分點/玩股網/Wantgoo/Histock），務必標明；身份一律『推估』",
  "day_volume": { "2026-06-12": 28000, "2026-06-11": 25000 },
  "flows": [
    { "date": "2026-06-12", "broker_id": "1470", "broker_name": "台灣摩根士丹利", "net": 1200 },
    { "date": "2026-06-11", "broker_id": "1470", "broker_name": "台灣摩根士丹利", "net": 900 },
    { "date": "2026-06-12", "broker_id": "9200", "broker_name": "凱基-台北", "net": -800 }
  ]
}
```
- `net` 為當日該分點買賣超**張數**（買超為正、賣超為負）。
- `flows` 為窗內**逐日 × 各分點**；引擎會自動彙總窗內淨買超、算**連續買超天數**與
  **買超佔成交比**（需 `day_volume`，可省）。
- `day_volume`（選填）= 各日該標的總成交張數，供「買超佔成交比」計算。
- 身份推估走 `config/broker_map.json`（分點代號／名稱關鍵字 → 外資/投信/中實戶/特定金主）。

## 落地路線（擇一補實，引擎不變）
1. **證交所 bsr 承接**：逐檔下載分點 + 驗證碼（OCR／人工），轉成本格式。
2. **第三方彙整源**：玩股網／Wantgoo／Histock／XQ／付費資料，下載後落成本格式，`tier` 標 B。
3. **逐家 adapter**：在 `arm/connectors/brokers/` 加解析器，輸出統一 `BrokerFlow`（slot 已備於 `SOURCES`）。
