# 社群 / KOL 情報 drop-in（創意情報層的 Tier B 承接層，M4）

「社群在講什麼賣點、誰在推、疑似業配、聲量多大」需要**社群/KOL 情報**。各平台
（YouTube/PTT/Dcard/vocus/新聞）多為登入/SPA，且爬取涉 **ToS / 個資 / 著作權**（M4-8），
**無單一乾淨公開 live 源**（見 docs/SPEC.md §18.5）。因此創意引擎採 **source-agnostic** 設計
——把社群情報放成下列格式檔，引擎立即取用、產出「社群熱議賣點 / 疑似業配反推投放」想法，
**無需改任何程式碼**。

> ⚠️ **鐵則**：聲量 / 情緒 / 疑似業配一律為**推估（Tier B）**，務必標來源與 as-of，
> 對外發布前人工核實。疑似業配只作「反推同業投放」內部素材，不對外指控。

## 檔名規則
```
config/social_mentions/{date}.json     # 例 2026-06-12.json
```
- `_` 開頭檔（如 `_SAMPLE_*.json`）**不載入**，僅供格式參考。
- 引擎以「資料日往回 7 天」為窗收集；落檔即生效。

## 格式（mention 陣列，或 {as_of, provenance, mentions:[...]}）
```json
{
  "as_of": "2026-06-12",
  "provenance": "來源說明（YouTube/PTT/Dcard/vocus/新聞），務必標明；聲量/業配為推估",
  "mentions": [
    {
      "platform": "youtube",
      "author": "某理財YouTuber",
      "date": "2026-06-11",
      "text": "這檔主動式ETF主動度高、季配息殖利率不錯，值得佈局…（本影片與廠商合作）",
      "url": "https://...",
      "etfs": ["00991A"],
      "reach": 52000,
      "tier": "B"
    }
  ]
}
```
- `etfs`：文中提及的本系統 ETF 代號；**空陣列=泛論**（仍會納入但不綁特定檔）。
- `reach`：觸及/觀看/讚數（推估），用來排聲量與分高/中/低。
- 逐則分析（賣點命中 / 情緒 / 疑似業配）由 `arm/connectors/social/base.py:analyze()` 自動算
  （確定性 baseline；日後可接 Claude 逐則深析，呼叫端不變）。

## 落地路線（擇一補實，引擎不變）
1. **逐家 adapter**：在 `arm/connectors/social/` 加解析器，於 `LIVE_ADAPTERS` 註冊
   （slot 已備於 `SOURCES`：YouTube Data API / PTT/Dcard 公開頁 / vocus·新聞 RSS）。
2. **第三方 / 人工彙整**：把當日社群觀察落成本格式檔，`tier` 標 B。
3. **Claude 逐則深析**：`analyze(m, llm=...)` 傳入 LLM callable，覆蓋/增補 baseline。
