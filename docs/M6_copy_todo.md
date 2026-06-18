# TODO — M6 Claude 文案層 + 合規 LLM 標注（詳細執行清單）

> 本檔是 **M6 的執行層細節**，補充 `docs/SPEC.md` Part II 的高階勾選與 §10 設計。SPEC 仍是單一規格來源；本檔只展開「怎麼做、碰哪些檔、驗收條件、待授權項」。
> 規格依據：SPEC §10（智能文案層 + 合規事後標注）、Part II M6。
> 狀態圖例：`[ ]` 待辦　`[~]` 部分　`[x]` 完成。

---

## 0. 目標與 DoD

**目標**：每個「想法（Idea）」自動長出 **3~4 種長度/通路的文案**，附 **逐句合規標注**（🟢🟡🔴 不擋），並給 **一鍵合規改寫版**。

**DoD（驗收）**：
- 跑 `run_daily` 後，每個想法附 `line / ig / sales / punchy` 至少 3 版文案。
- 每版文案有 `annotations[]`（span+風險+規則+建議）+ `overall_risk` + `compliant_rewrite`。
- **數字 100% 可追溯**：文案中的所有數字皆來自該想法的 `evidence/headline`，杜撰數字會被偵測並標 🔴。
- 合規**不攔截**：所有版本都能複製，標注只是把風險攤開（沿用事後標注精神）。
- `tests/test_copy.py` 全綠；既有測試不破。

---

## 1. 核心設計決策（先確定，再寫碼）

### 1.1 LLM-agnostic：baseline 一定能離線跑，LLM 是可注入的增強
本專案是「純標準庫 + SQLite、零安裝、launchd 每日自動」。**文案層不可硬依賴 Anthropic SDK / API key**（那是對外動作、待授權），否則每日排程會斷。
→ 比照 M4 `social.analyze(m, llm=...)` 的模式：
- **baseline（確定性、純 stdlib、必做）**：用模板從 `idea.evidence` 結構化數字產生各通路文案 + 規則式合規標注 + 規則式改寫版。**每日排程只靠 baseline 就能完整產出**。
- **LLM 層（可注入、待授權）**：`generate(idea, ctx, llm=None)`、`review(text, rules, llm=None)`。`llm` 是一個 callable（簽名見 §4），接上 `claude-opus-4-8`（Anthropic SDK）後「火力全開」覆蓋/增補 baseline，**呼叫端不改**。未授權時 `llm=None`，自動走 baseline。

### 1.2 數字不得杜撰（硬底線，對齊 Tier A 正確性）
SPEC §10.1：唯一硬底線=數字只能用 evidence 內真實數據。
→ 機制：
1. 從 `idea.evidence + idea.headline` 抽出 **allowed tokens**（數字、`%`、`+/-`、`倍/億/張/萬/pt`、個股/競品名）。
2. baseline 模板**只插入** allowed 欄位 → 天生不會杜撰。
3. LLM 產出做 **post-check**：掃描輸出的每個數字 token，正規化後若不在 allowed set → 標 🔴「數字未見於 evidence、疑似杜撰」，並可選擇丟棄該版或保留+重警示（預設保留+🔴，交人決定）。
4. `tests/` 必含：注入一個假數字 → 偵測器要抓到。

### 1.3 合規兩層、皆不擋（事後標注）
- **規則層（必做）**：把現有 `ideas.annotate()` 的 `BANNED` + 必揭露邏輯**外移到 `config/compliance.yaml`**，升級成 span 級 + 風險分級（高/中/低）+ `compliant_rewrite`（規則式）。
- **LLM 法遵層（待授權）**：第二次呼叫 Claude 扮「投信投顧公會法遵」逐句判讀（SPEC §10.2 JSON 格式），`review(text, rules, llm=)` 注入；未授權走規則層。
- 風險分級沿用：高=絕對化/保證/最高級；中=缺揭露/比較未標基準；低=用語偏軟。
- 沿用 `ideas.py` 既有 🟢🟡🔴 與 `_violates()`（「非保證」不誤判）邏輯，**不要重寫、要重用**。

### 1.4 打架邊界（多 session 協作鐵則）
- **隔壁的禁區，一律不碰**：`arm/connectors/brokers/`、`arm/chips.py`、`arm/connectors/etfinfo.py`、`config/broker_flows/`、`config/active_flow/`、`config/competitor_holdings/`。
- **本 session（M6）只新增/碰**：`arm/copy/`（新）、`config/compliance.yaml`（新）、`tests/test_copy.py`（新）、`scripts/gen_copy.py`（新，見 §5）、`arm/db.py`（只**新增** copy 表，不動既有）、`docs/SPEC.md`+`README.md`（只動 M6 段落）。
- **`arm/ideas.py` / `arm/pipeline.py` 是共用熱區**：M6 盡量**不改** ideas.py、**最小改或不改** pipeline.py。優先採 §5 的「獨立 `scripts/gen_copy.py`」串接（零 pipeline 編輯=零打架）；要動 pipeline 前先確認隔壁沒在改。

---

## 2. 檔案計畫

| 檔案 | 動作 | 內容 |
|---|---|---|
| `arm/copy/__init__.py` | 新 | re-export `generate_for_idea` / `review` / `write_for_portfolio` |
| `arm/copy/generator.py` | 新 | 模板文案生成（line/ig/sales/punchy）+ allowed-token 抽取 + LLM 注入點 |
| `arm/copy/compliance.py` | 新 | 載 `compliance.yaml` → span 級標注 + overall_risk + 規則式 `compliant_rewrite` + 數字杜撰偵測 + LLM 法遵注入點 |
| `arm/copy/templates.py` | 新 | 各通路模板與字數規則（line ≤60、ig、sales、punchy） |
| `config/compliance.yaml` | 新 | 禁詞（分級）、必揭露語句、改寫對照表、通路設定 |
| `arm/db.py` | 改(加表) | `CREATE TABLE copy(...)`；用既有 `upsert` 落地 |
| `scripts/gen_copy.py` | 新 | 獨立 CLI：讀當日想法 → 產文案/標注 → 落 DB + 出 `reports/{date}_{etf}_copy.md` |
| `tests/test_copy.py` | 新 | 見 §6 |
| `docs/SPEC.md` / `README.md` | 改(M6段) | 勾選 + 現況；標 baseline 完成 / LLM 待授權 |

---

## 3. 逐任務（對應 SPEC M6-1~M6-4）

### M6-1 文案生成器 `arm/copy/generator.py`
- [ ] 定義 `CopyVariant(channel, text, length, source)`（source: `template` / `llm`）。
- [ ] `allowed_tokens(idea) -> set[str]`：regex 從 `evidence + headline` 抽數字/`%`/`+-`/單位/名稱。
- [ ] `generate_for_idea(idea, ctx, llm=None) -> list[CopyVariant]`：
  - 依 `idea.category` 選模板族（績效/籌碼/題材/配息/差異化/逆向誠實/社群KOL…）。
  - 產 `line`(≤60字短訊)、`ig`(社群貼文)、`sales`(通路話術)、`punchy`(最敢講吸睛版)。
  - 數字只從結構化欄位插入（§1.2）。
  - `llm is not None` 時呼叫 LLM 產增強版並做數字 post-check（§1.2.3）。
- DoD：給定一個想法→回 ≥3 版、每版數字皆 ⊆ allowed。

### M6-2 合規升級 `arm/copy/compliance.py`
- [ ] `load_rules()` 讀 `config/compliance.yaml`（禁詞分級 + 必揭露 + 改寫表）。
- [ ] `annotate_spans(text, rules) -> list[ann]`：span 級（沿用 `_violates` 不誤判「非保證」）。
- [ ] `overall_risk(anns)`：取最高。
- [ ] `compliant_rewrite(text, rules)`：規則式——禁詞替換（保證→可能/刪、完勝→領先、最強→表現突出、翻倍賺→大幅成長）+ 缺免責則補「（過去績效不代表未來，投資有風險）」+ 軟化絕對化。
- [ ] `detect_fabricated_numbers(text, allowed) -> list[ann]`：🔴 杜撰數字（§1.2）。
- [ ] `review(text, rules, allowed, llm=None)`：合併規則層 + 數字檢查（+ LLM 法遵層 if llm）。回 SPEC §10.2 JSON 結構。
- DoD：`報酬完勝大盤` → 高風險 + 改寫版「…報酬領先對標指數…（附免責）」；假數字被抓。

### M6-3 文案入庫 + 輸出 `arm/db.py` + `scripts/gen_copy.py`
- [ ] `db.py` 加 `copy` 表（§4 schema），用既有 `upsert`。
- [ ] `scripts/gen_copy.py`：對指定/全部主角，讀「當日想法組合」→ 逐想法 `generate_for_idea` + `review` → 落 `copy` 表 + 寫 `reports/{date}_{etf}_copy.md`（原文 + 🟡🔴 標注 + 改寫版並陳）。
- [ ] 想法來源：優先**重跑 `ideas.build_portfolio`**（離線、不需網路重抓；用既有 `pipeline.build_context`？會觸發網路→改為讀已存 `reports/{date}_{etf}.md` 解析想法，或讀 `signals` 表）。**決策點見 §5**。
- DoD：跑 `gen_copy.py 00991A` 產出 copy 報告 + DB 有列。

### M6-4 設定化 `config/compliance.yaml`
- [ ] 禁詞（沿用現有 `BANNED` + 分級）、必揭露語句、改寫對照、通路字數上限、各通路 tone。
- [ ] `ideas.annotate()` 可選擇改為讀同一份 yaml（**保持向後相容**，不破既有 28+ 測試）——或先不動 ideas，只讓 copy 層用 yaml，待穩定再收斂（避免打架 ideas.py）。
- DoD：改 yaml 即改標注行為，無需動碼。

---

## 4. 介面 / 資料結構（草案）

```python
# arm/copy/generator.py
@dataclass
class CopyVariant:
    channel: str          # line / ig / sales / punchy
    text: str
    length: int
    source: str = "template"   # template | llm
    annotations: list = field(default_factory=list)
    overall_risk: str = "低"
    compliant_rewrite: str = ""

# LLM 注入點簽名（待授權接 claude-opus-4-8）
#   gen_llm(idea: dict, ctx: dict, channels: list[str]) -> dict[channel, str]
#   review_llm(text: str, rules: dict) -> dict   # 回 SPEC §10.2 JSON
```

```sql
-- arm/db.py 新增（不動既有表）
CREATE TABLE IF NOT EXISTS copy (
    etf_id      TEXT, trade_date TEXT,
    idea_idx    INTEGER, category TEXT,
    channel     TEXT,  text TEXT,
    overall_risk TEXT, compliant_rewrite TEXT,
    src         TEXT,  created_at TEXT,
    PRIMARY KEY (etf_id, trade_date, idea_idx, channel)
);
```

```yaml
# config/compliance.yaml（草案）
banned:
  high:  [保證, 穩賺, 必漲, 完勝, 最強, 包賺, 穩賺不賠, 零風險, 絕對, 鐵定, 翻倍賺]
required_disclaimers:
  performance: "過去績效不代表未來，投資有風險"
  dividend:    "配息率非報酬率，配息可能含本金"
rewrite_map:
  完勝: 領先
  最強: 表現突出
  翻倍賺: 大幅成長
  保證: ""          # 刪除或改「可能」
channels:
  line:  {max_len: 60, tone: 精簡好轉傳}
  ig:    {max_len: 280, tone: 情境+emoji}
  sales: {max_len: 200, tone: 顧問口吻、附數字佐證}
  punchy:{max_len: 120, tone: 最敢講吸睛、必過合規標注}
```

---

## 5. 串接方式（打架關鍵決策）

**選項 A（最小 pipeline hook）**：在 `pipeline.run()` 產完 portfolio 後呼叫 copy 層、一起落地。
- 優點：單一指令出全部。缺點：**改 pipeline.py（隔壁熱區）→ 有打架風險**。

**選項 B（獨立 `scripts/gen_copy.py`，推薦）**：copy 完全獨立，讀「已產出的當日想法」再生成。
- 優點：**零 pipeline/ideas 編輯 = 零打架**；可單獨重跑、不重抓網路。
- 想法來源二選一：(B1) 解析既有 `reports/{date}_{etf}.md` 的「**想法**/佐證」行（已有穩定格式，`_recent_headlines` 證明可解析）；(B2) 從 `signals` 表讀。**建議 B1**（想法層的 evidence 完整在報告裡）。

> **預設走 B**。待隔壁工作告一段落、確認不衝突，再評估是否補 A 的一鍵整合。

---

## 6. 測試計畫 `tests/test_copy.py`
- [ ] `generate_for_idea` 對各 category 產 ≥3 版；每版數字 ⊆ allowed_tokens。
- [ ] `compliant_rewrite`：禁詞被替換/刪、缺免責被補。
- [ ] `detect_fabricated_numbers`：在文案塞一個 evidence 沒有的「99%」→ 必須被標 🔴。
- [ ] `annotate_spans`：「完勝」高風險；「過去績效不代表未來」不再觸發缺免責；「非保證」不誤判（回歸）。
- [ ] `review` 回傳結構含 `annotations/overall_risk/compliant_rewrite`。
- [ ] LLM 注入點：傳一個假 `llm` callable → 能覆蓋 baseline 且仍跑數字 post-check。
- [ ] 既有 25→68+ 測試不破。

---

## 7. 待使用者授權（對外動作，slot 先備）
- [ ] **Anthropic API key / claude-opus-4-8 接入**：`generate(...llm=)` / `review(...llm=)` 的真 LLM callable。未授權前 baseline 全功能運作。
- [ ] （與 M4 共用）每日雲端 routine 觸發 LLM 文案 + 法遵審查。

---

## 8. 建議執行順序
1. `config/compliance.yaml` + `arm/copy/compliance.py`（規則層 + 數字杜撰偵測）→ 測試。
2. `arm/copy/templates.py` + `generator.py`（baseline 文案）→ 測試。
3. `arm/db.py` 加 `copy` 表 + `scripts/gen_copy.py`（選項 B1：讀當日報告）→ 端到端跑 00991A。
4. 文件同步（SPEC M6 勾選 + README 現況）。
5.（待授權）接 LLM callable，baseline → LLM 增強。

---
*合規定位：內部行銷發想輔助，非投顧；對外發布前經法遵核可。文案層先給最強、再誠實標風險、不擋發布（SPEC §10、§16）。*
