# 復華主動式 ETF 每日行銷情報雷達 — 技術規格書 + 建置路線圖 (SPEC)

> 代號：**FH-ARM**（Fuh Hwa Active-ETF Radar for Marketing）
> 版本：v0.6（規格 + 路線圖整合版）
>
> **本文件含兩部分**：
> - **Part I — 系統規格（§1–§21）**：設計「成什麼」——架構、資料源、schema、引擎、合規、資料正確性。
> - **Part II — 建置路線圖（§R）**：依「什麼順序做出來」——里程碑勾選清單、依賴、驗收(DoD)、執行順序；每個里程碑對應 Part I 章節。
> 想看「現在做到哪、下一步做什麼」直接跳 [Part II 建置路線圖](#part-ii--建置路線圖roadmap--checklist)。
> 定位：以復華主動式 ETF 為主角，每日自動產出「今天該主打什麼、怎麼講、給誰講」的行銷彈藥庫。
> 技術棧：**Python 資料管線 + PostgreSQL + FastAPI + Next.js 儀表板**
> 資料來源：**僅公開資料**（TWSE / TPEx / SITCA / 集保 / 各投信官網每日持股揭露）
> 首要產出通路：**Web 賣點儀表板**（LINE 推播、PDF 日報列為 P1/P2）

---

## 目錄
1. [目標與範圍](#1-目標與範圍)
2. [系統總架構](#2-系統總架構)
3. [Repo 結構](#3-repo-結構)
4. [資料來源對照表](#4-資料來源對照表僅公開資料)
5. [資料庫 Schema（DDL）](#5-資料庫-schemaddl)
6. [資料管線 Pipeline](#6-資料管線-pipeline)
7. [指標引擎](#7-指標引擎)
8. [賣點偵測器庫 Signal Library](#8-賣點偵測器庫-signal-library)
9. [賣點評分模型](#9-賣點評分模型)
10. [智能文案層 + 合規事後標注](#10-智能文案層--合規事後標注)
11. [後端 API 合約（FastAPI）](#11-後端-api-合約fastapi)
12. [前端儀表板（Next.js）](#12-前端儀表板nextjs)
13. [排程與部署](#13-排程與部署)
14. [設定檔（產品清單）](#14-設定檔產品清單)
15. [分階段路線圖](#15-分階段路線圖)
16. [合規與法律](#16-合規與法律)
17. [開放問題](#17-開放問題待確認)
18. [進階情報引擎（擴充需求）](#18-進階情報引擎擴充需求)
    - 18.1 持股差異化引擎（獨門 vs 同業）
    - 18.2 多週期績效引擎
    - 18.3 成交量突出偵測
    - 18.4 籌碼分點推敲模組
    - 18.5 社群 / KOL 情報引擎
    - 18.6 同業行銷情報 + 話術複製庫
19. [競品行銷情報實況附錄（已實地搜集）](#19-競品行銷情報實況附錄已實地搜集)
20. [資料正確性保證（Tier 分級）](#20-資料正確性保證tier-分級)
21. [多元想法組合引擎](#21-多元想法組合引擎philosophy每天給各種想法而非一個冠軍)

**Part II — 建置路線圖**
- [§R 建置路線圖與進度（Roadmap / Checklist）](#part-ii--建置路線圖roadmap--checklist)
- [變更紀錄 Changelog](#變更紀錄-changelog)

---

## 1. 目標與範圍

### 1.1 要解決的問題
復華行銷／業務／通路團隊每天需要快速知道：**今天哪一檔主動式 ETF 有最好的行銷切入點、用什麼數字證明、怎麼寫成合規文案。** 目前這件事仰賴人工翻數據、缺乏系統化與即時性。

### 1.2 MVP 範圍（本規格主攻）
- 主角產品：00991A、00998A、00986D（清單可設定，見 §14）。
- 全市場主動式 ETF 作為「對照組」（competitive benchmark）。
- 每日收盤後批次：抓資料 → 算指標 → 跑賣點偵測 → 評分排序 → 產出 Web 儀表板。
- 6 個核心偵測器先上（見 §8 標記 ★MVP）。

### 1.3 非範圍（本期不做）
- 即時 tick 行情（只做收盤後日更）。
- 投資建議 / 投顧功能（法規定位為內部行銷工具）。
- 對外公開上線（P2 才評估）。

### 1.4 成功指標
- 每日 18:30 前自動產出當日賣點榜，零人工介入。
- 每檔主角產品 ≥ 3 個有證據的賣點 + 3 種長度合規文案。
- 賣點「命中率」可回溯追蹤（P1 起記錄被採用率）。

---

## 2. 系統總架構

```
                        ┌──────────────── 排程器 (Prefect / APScheduler) ────────────────┐
                        │  每交易日 17:30 觸發 daily_flow                                  │
                        ▼                                                                  │
┌─────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐
│ Connectors  │──▶│  Raw Staging │──▶│  指標引擎     │──▶│ 賣點偵測+評分 │──▶│ Claude 文案 │
│ (公開資料源) │   │  (原始落地)   │   │  metrics      │   │ signals      │   │ +合規護欄   │
└─────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └────────────┘
        │                 │                 │                  │                   │
        └─────────────────┴─────────────────┴──────────────────┴───────────────────┘
                                          ▼
                                  PostgreSQL (時序快照)
                                          ▼
                                   FastAPI (read API)
                                          ▼
                              Next.js 儀表板 (Web 賣點榜)
```

設計原則：
- **快照式時序**：每日資料以日期為 key 落地，永不覆寫，方便做「昨日 vs 今日」diff 與歷史回放。
- **冪等**：同一交易日重跑不會產生重複資料（upsert on (代號, 日期)）。
- **分層**：connector 只負責「抓 + 正規化」，不做業務邏輯；指標/偵測器/文案各自獨立可測。

---

## 3. Repo 結構

```
fh-arm/
├── README.md
├── docs/
│   └── SPEC.md                  # 本文件
├── config/
│   ├── products.yaml            # 復華主角產品 + 對照組設定
│   ├── sources.yaml             # 資料源 endpoint 設定
│   └── compliance.yaml          # 禁詞表、必揭露語句
├── backend/                     # Python 管線 + API
│   ├── pyproject.toml           # uv / poetry
│   ├── arm/
│   │   ├── connectors/          # 各資料源抓取器
│   │   │   ├── twse.py
│   │   │   ├── tpex.py
│   │   │   ├── sitca.py
│   │   │   ├── tdcc.py          # 集保受益人/股權分散
│   │   │   └── issuers.py       # 各投信每日持股揭露
│   │   ├── models/              # SQLAlchemy ORM + Pydantic schema
│   │   ├── metrics/             # 指標引擎
│   │   │   ├── returns.py       # 報酬/alpha/sharpe
│   │   │   ├── flows.py         # 規模/受益人/資金流
│   │   │   └── holdings.py      # 持股 diff、加減碼、命中飆股
│   │   ├── signals/             # 賣點偵測器庫
│   │   │   ├── base.py          # Signal/Detector 介面
│   │   │   ├── detectors/       # 一檔一個偵測器
│   │   │   └── scoring.py       # 評分模型
│   │   ├── copy/                # Claude 文案 + 合規
│   │   │   ├── generator.py
│   │   │   └── compliance.py
│   │   ├── pipeline/
│   │   │   └── daily_flow.py    # 編排 DAG
│   │   ├── api/                 # FastAPI
│   │   │   ├── main.py
│   │   │   └── routers/
│   │   └── db.py
│   ├── alembic/                 # migration
│   └── tests/
└── frontend/                    # Next.js 儀表板
    ├── package.json
    ├── app/
    │   ├── page.tsx             # 首頁：今日賣點榜
    │   ├── etf/[id]/page.tsx    # 單檔賣點卡
    │   ├── compare/page.tsx     # 復華 vs 競品
    │   └── signals/page.tsx     # 賣點明細/歷史
    ├── components/
    └── lib/api.ts               # 呼叫 FastAPI
```

---

## 4. 資料來源對照表（僅公開資料）

> ⚠️ 端點以目前公開資訊整理，**Phase 0 第一件事是逐一驗證 endpoint 與欄位**（政府/公會 API 偶有改版）。標「待驗證」者需實測。

| 資料項 | 來源 | 取得方式 | 頻率 | 信心 |
|---|---|---|---|---|
| 上市 ETF 日報價/成交 | TWSE OpenAPI `openapi.twse.com.tw` | REST JSON | 日 | 高 |
| 上櫃 ETF 日報價 | TPEx OpenAPI `tpex.org.tw/openapi` | REST JSON | 日 | 高 |
| ETF 每日淨值/折溢價 | 各投信官網 PCF / TWSE ETF 揭露 | 官網下載 / 爬取 | 日 | 中（依發行商格式） |
| **主動式 ETF 每日完整持股** | 各投信官網每日揭露（法規強制） | 官網 CSV/HTML 爬取 | 日 | 中（每家格式不一，需各別 adapter） |
| 基金規模 / 受益人數 | SITCA 投信投顧公會 `sitca.org.tw` | 月報下載 + 每日揭露補充 | 日/月 | 中 |
| 受益人數 / 股權分散 | 集保 TDCC `smart.tdcc.com.tw` | 爬取（週更） | 週 | 中 |
| 大盤/報酬指數基準 | TWSE 發行量加權股價報酬指數、0050 | TWSE OpenAPI | 日 | 高 |
| 配息/除息資訊 | 各投信官網 + TWSE 公告 | 爬取 | 事件 | 中 |
| 個股日報價（算命中飆股） | TWSE `STOCK_DAY_ALL` | REST JSON | 日 | 高 |
| 產業/題材分類 | TWSE 產業別 + 自建題材對照表 | API + 人工維護 | 低頻 | 中 |
| **競品每日持股 / 配息 / 殖利率** | **etfinfo.tw**（Nuxt JSON API：`/api/etf/{code}`、`/api/etf/list`） | REST JSON | 日 | 中（Tier B 第三方彙整，`source` 多為 issuer-official，**上線前以投信官網核實**） |
| **主動ETF/投信籌碼追蹤（估算新進）** | **etfinfo.tw** `/api/active/tracking` | REST JSON | 日 | 中（Tier B，法人層級非券商分點，§18.4 聰明錢替代源） |
| **券商分點買賣超（個別買家）** | **Histock** `histock.tw/stock/branch.aspx?no={code}` | 靜態 HTML 表 | 日 | 中（Tier B，買家身份經 broker_map 推估、標『推估・非確認』；§18.4） |
| **券商分點（全分點+多日+量，最完整）** | **FinMind** `TaiwanStockTradingDailyReport` | REST JSON | 日 | 中（Tier B，需 `FINMIND_TOKEN` 付費 sponsor；§18.4） |
| **社群/KOL/新聞（§18.5）** | RSS（鉅亨/Yahoo）、PTT、Dcard、YouTube Data API、FB Graph | REST/HTML/RSS | 日 | 低（Tier B，聲量/業配推估；YouTube/FB 需金鑰） |

設計重點：
- **每家投信一個 holdings adapter**（`connectors/issuers.py` 下分模組），抽象成統一 `Holding(etf_id, date, stock_id, weight, shares)`。
- connector 全部走 `httpx` + 重試 + 快取原始回應（debug 用），輸出 Pydantic model 後才入庫。
- 遵守各站 robots / 合理抓取頻率，加 `User-Agent`、限速、退避。

---

## 5. 資料庫 Schema（DDL）

```sql
-- 維度：ETF 主檔
CREATE TABLE etf (
    etf_id       TEXT PRIMARY KEY,          -- 代號 e.g. 00991A
    name         TEXT NOT NULL,
    issuer       TEXT NOT NULL,             -- 發行投信
    is_active    BOOLEAN NOT NULL,          -- 是否主動式
    is_fh        BOOLEAN NOT NULL DEFAULT FALSE, -- 是否復華(主角)
    theme        TEXT,                      -- 投資主題/類別
    benchmark    TEXT,                      -- 對標指數
    inception    DATE,
    dividend_freq TEXT,                     -- 月/季/半年/不配
    listed_market TEXT                      -- TWSE/TPEx
);

-- 事實：每日報價/估值/規模
CREATE TABLE etf_daily (
    etf_id       TEXT REFERENCES etf,
    trade_date   DATE NOT NULL,
    close        NUMERIC,
    change_pct   NUMERIC,
    nav          NUMERIC,                   -- 淨值
    premium_disc NUMERIC,                   -- 折溢價 %
    aum          NUMERIC,                   -- 規模(億元)
    holders      INTEGER,                   -- 受益人數
    volume       BIGINT,
    PRIMARY KEY (etf_id, trade_date)
);

-- 事實：每日完整持股(主動式ETF)
CREATE TABLE holdings_daily (
    etf_id       TEXT REFERENCES etf,
    trade_date   DATE NOT NULL,
    stock_id     TEXT NOT NULL,
    stock_name   TEXT,
    weight       NUMERIC,                   -- 權重 %
    shares       BIGINT,                    -- 持股數
    PRIMARY KEY (etf_id, trade_date, stock_id)
);

-- 事實：個股日報價(算命中飆股/題材)
CREATE TABLE stock_daily (
    stock_id     TEXT,
    trade_date   DATE,
    close        NUMERIC,
    change_pct   NUMERIC,
    industry     TEXT,
    PRIMARY KEY (stock_id, trade_date)
);

-- 事實：配息/除息事件
CREATE TABLE dividends (
    etf_id       TEXT REFERENCES etf,
    ex_date      DATE,
    last_buy_date DATE,
    amount       NUMERIC,
    yield_pct    NUMERIC,
    PRIMARY KEY (etf_id, ex_date)
);

-- 基準指數(大盤報酬指數/0050)
CREATE TABLE benchmark_daily (
    bench_id     TEXT,                      -- TAIEX_TR / 0050
    trade_date   DATE,
    close        NUMERIC,
    change_pct   NUMERIC,
    PRIMARY KEY (bench_id, trade_date)
);

-- 計算結果：當日衍生指標(寬表，依需要擴欄)
CREATE TABLE metrics_daily (
    etf_id       TEXT REFERENCES etf,
    trade_date   DATE,
    ret_1d NUMERIC, ret_1w NUMERIC, ret_1m NUMERIC, ret_3m NUMERIC,
    ret_ytd NUMERIC, ret_si NUMERIC,        -- since inception
    alpha_1m NUMERIC, alpha_3m NUMERIC,     -- vs benchmark
    sharpe_3m NUMERIC, vol_3m NUMERIC,
    aum_chg_1w NUMERIC, holders_chg_1w NUMERIC,
    rank_peer_1m INTEGER,                   -- 同類排名
    nav_high_si BOOLEAN,                    -- 是否成立來新高
    PRIMARY KEY (etf_id, trade_date)
);

-- 產出：賣點訊號
CREATE TABLE signals (
    id           BIGSERIAL PRIMARY KEY,
    etf_id       TEXT REFERENCES etf,
    trade_date   DATE,
    detector     TEXT NOT NULL,             -- 偵測器代號 e.g. ALPHA_BEAT
    strength     NUMERIC,                   -- 0-100
    novelty      NUMERIC,                   -- 0-100 是否今天才發生
    theme_fit    NUMERIC,                   -- 0-100 題材熱度
    audience_fit NUMERIC,                   -- 0-100 受眾匹配
    score        NUMERIC,                   -- 綜合賣點分數(見§9)
    evidence     JSONB,                     -- 佐證數據(數字/排名/個股)
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_signals_etf_date ON signals(etf_id, trade_date, score DESC);

-- 產出：文案
CREATE TABLE copy (
    id           BIGSERIAL PRIMARY KEY,
    signal_id    BIGINT REFERENCES signals,
    channel      TEXT,                      -- line/ig/sales
    text         TEXT,
    compliance_status TEXT,                 -- pass/needs_review/blocked
    compliance_notes  TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);
```

---

## 6. 資料管線 Pipeline

`daily_flow`（Prefect flow，每交易日 17:30 觸發）：

```
1. ingest_quotes          # TWSE/TPEx 報價、淨值、折溢價 → etf_daily
2. ingest_holdings        # 全市場主動ETF每日持股 → holdings_daily
3. ingest_flows           # SITCA/TDCC 規模、受益人數 → etf_daily
4. ingest_stocks          # 個股日報價 → stock_daily
5. ingest_benchmark       # 大盤報酬指數/0050 → benchmark_daily
6. ingest_dividends       # 除息事件 → dividends
   ── 以上可平行 ──
7. compute_metrics        # → metrics_daily
8. run_detectors          # 跑所有偵測器 → signals
9. score_and_rank         # 評分排序
10. generate_copy         # Claude 文案 + 合規 → copy（僅對 score 高的訊號）
11. publish               # 標記當日 ready，前端可讀
```

容錯：
- 任一 connector 失敗 → 記錄、用上一交易日資料 fallback、在儀表板標「資料延遲」。
- 全流程冪等（依 `trade_date` upsert），可手動重跑。
- 交易日判定：用 TWSE 交易日曆，非交易日不觸發。

---

## 7. 指標引擎

`metrics/` 計算並寫入 `metrics_daily`。核心公式：

| 指標 | 公式 |
|---|---|
| **多週期報酬 ret_T** | `(nav_t / nav_{t-T}) - 1`，T ∈ {1d, 3d, 1w, 2w, 1m, 3m, 6m, ytd, SI(成立來)}（用調整後淨值含息） |
| **多週期 Alpha_T** | 每個週期都算：`ret_T(ETF) - ret_T(benchmark)`；台股型對 TAIEX_TR 或 0050 |
| **多週期同類排名** | 每個週期在同類主動 ETF 內排名（rank_peer_T），標出「哪些競品被比下去」 |
| 波動度 vol | 近 60 日日報酬標準差年化 |
| Sharpe | `(年化報酬 - rf) / 年化波動`，rf 用設定值 |
| 折溢價 | `(close - nav) / nav` |
| 資金流 aum_chg_1w | `(aum_t / aum_{t-5}) - 1` |
| 受益人週增 | `holders_t - holders_{t-5}` |
| 命中飆股貢獻 | `Σ(weight_i × change_pct_i)` 取前幾大正貢獻個股 |
| **成交量 / 換手率** | `volume_t`、相對 20 日均量倍數 `volume_t / MA20(volume)`、換手率 `volume_t / 在外流通張數` |
| **成交量同類排名** | 當日成交量在同類主動 ETF 的名次（量能人氣指標） |

> 多週期是這支系統的硬需求：每天、每三天、每週、每雙週、每月、每季、年初以來、成立以來都各算一組「報酬 + Alpha + 同類排名」，讓行銷可以挑「對我們最有利的那個週期」當主打（例：短線輸但年初以來大贏，就主打 YTD）。
> 計算結果存進 `metrics_daily`（寬表，依週期擴欄，如 `ret_3d / alpha_3d / rank_peer_3d / ret_2w / ...`）。

實作用 `polars`（大表效能），全部純函式、吃 DataFrame 回 DataFrame，方便單元測試。

---

## 8. 賣點偵測器庫 Signal Library

統一介面：

```python
class Detector(Protocol):
    code: str            # e.g. "ALPHA_BEAT"
    def detect(self, etf_id: str, date: date, ctx: Context) -> Signal | None:
        """回傳 Signal(strength, evidence) 或 None(今日無此賣點)"""
```

`Context` 提供當日所有資料的查詢介面（metrics、holdings、peers、benchmark、stocks）。

| # | 代號 | 觸發條件 | strength 計算 | evidence 內容 | MVP |
|---|---|---|---|---|---|
| 1 | `ALPHA_BEAT` | alpha_1m > 0 | alpha 百分位映射到 0-100 | 期間、alpha%、對標 | ★ |
| 2 | `PEER_CHAMPION` | rank_peer_1m ≤ 3 | 名次反映分數(第1=100) | 名次、同類檔數 | |
| 3 | `HIT_HOT_STOCK` | 重倉股當日漲幅高×權重高 | 命中貢獻度 | 個股、漲幅、權重、淨值貢獻 | ★ |
| 4 | `LEAD_POSITION` | 復華先持有、N日後≥M檔同業才買進 | 領先天數×跟進檔數 | 個股、領先天數、跟進名單 | |
| 5 | `MANAGER_ADD` | 持股diff出現顯著加碼 | 加碼權重變化 | 個股、加碼前後權重 | ★ |
| 6 | `FUND_INFLOW` | aum_chg_1w 或 holders_chg_1w 正且排名前段 | 流入幅度百分位 | 週增金額/人數、排名 | ★ |
| 7 | `MILESTONE` | 受益人/規模突破整數關卡 | 關卡量級 | 突破數值 | |
| 8 | `NAV_HIGH` | nav 創成立來/N日新高 | 新高區間長度 | 新高型態、區間 | ★ |
| 9 | `DISCOUNT_BUY` | premium_disc < -閾值 | 折價深度 | 折價% | |
| 10 | `EX_DIV_SOON` | 除息日距今 ≤ K 日 | 殖利率吸引力 | 除息日、最後買進日、金額、殖利率 | ★ |
| 11 | `STABLE_INCOME` | 連續配息紀錄(入息型) | 連配次數 | 配息歷史 | |
| 12 | `RISK_ADJ_WIN` | Sharpe 優於同類中位數 | Sharpe 百分位 | Sharpe、同類比較 | |
| 13 | `THEME_TAILWIND` | 重倉產業=當日強勢題材 | 題材熱度×權重 | 題材、相關持股 | |
| 14 | `CONCENTRATED_PICK` | 前十大集中且多檔強勢 | 集中度×強勢比例 | 前十大、漲幅 | |
| 15 | `ANNIVERSARY` | 成立滿月/季/年 | 里程碑量級 | 成立日、週期 | |
| 16 | `DCA_PROOF` | 定期定額回測贏被動對照 | 超額累積報酬 | 試算參數、結果 | |
| 17 | `VS_COMPETITOR` | 同題材贏競品主動/被動 | 超額報酬 | 競品代號、差距 | |
| 18 | `STREAK` | 連N日/週上漲或淨流入 | 連續長度 | 連續天數/週數 | |
| 19 | `UNIQUE_HOLDING` | 復華持有、同業多數沒持有的「獨門股」且表現佳 | 獨門度×個股表現 | 個股、僅復華持有、漲幅 | |
| 20 | `DIVERGENT_BET` | 復華權重 vs 同業平均權重落差大（重押/低配的差異化下注） | 權重偏離度 | 個股、復華權重 vs 同業均值 | |
| 21 | `VOLUME_SPIKE` | 成交量 > N×20日均量 或 同類量能排名前段 | 量能倍數百分位 | 當日量、均量倍數、同類名次 | |
| 22 | `BEAT_PEERS_MULTI` | 多個週期同類排名領先、特定週期把指名競品比下去 | 領先週期數×差距 | 各週期名次、被超越競品清單 | |
| 23 | `SMART_MONEY` | 重倉股出現關鍵分點/主力大量買超（籌碼面佐證） | 分點買超強度 | 個股、關鍵分點推估、買超量 | |

每個偵測器：純函式、可獨立測試、可開關（config）、產出標準化 `Signal`。詳見 §18 進階情報引擎。

---

## 9. 賣點評分模型

每個訊號最終分數：

```
score = 0.40 × strength      # 賣點本身有多強
      + 0.25 × novelty       # 是不是「今天才發生」(舊聞扣分)
      + 0.20 × theme_fit     # 是否搭上當前市場熱門題材
      + 0.15 × audience_fit  # 與目標受眾(通路/客群)匹配度
```

- `novelty`：與昨日 signals 比對，今日新觸發=100，連續第N日遞減。
- `theme_fit`：重倉產業 vs 當日漲幅最大產業/熱搜題材對照表。
- `audience_fit`：依產品設定的目標客群（如入息型→存股族）給權重。
- 權重放 `config`，可調校；P1 起用「被採用率」回饋微調。

**排序輸出**：
- 每檔產品 → 取 score Top 3 賣點 → 組「單檔賣點卡」。
- 全公司 → 取所有產品 score 最高者 → 「今日最強賣點」置頂。

---

## 10. 智能文案層 + 合規事後標注

> **設計取向（依需求調整）**：合規**不攔截、不限制發想**。文案產生器先「火力全開」把最有銷售力的版本寫出來，合規模組**事後在旁邊標注**哪裡有疑慮、屬於哪一類、可怎麼改。決定要不要照標注修改，由人決定——工具只負責「先給你最強的，再誠實告訴你哪裡踩線」。

### 10.1 文案生成（不設限）
- 模型：`claude-opus-4-8`（Anthropic SDK）。
- 輸入：賣點 evidence（結構化數字）+ 通路 + 產品設定 + §18.6 同業話術庫靈感。
- 輸出多版本：`line`（≤60字短訊）、`ig`（社群貼文）、`sales`（通路話術）、`punchy`（最敢講的吸睛版）。
- 唯一硬底線：**數字不得杜撰**，只能用 evidence 內的真實數據（避免假資訊風險，與合規分開）。

### 10.2 合規標注層（annotation，不 block）
產生文案後，第二次呼叫 Claude 扮「投信法遵」，**逐句標注**而非封鎖：

```json
{
  "text": "原文案",
  "annotations": [
    {"span": "報酬完勝大盤", "level": "高", "rule": "比較性/最高級用語",
     "note": "『完勝』屬絕對化用語，公會規範可能不允許", "suggest": "近一月報酬領先對標指數 X%"},
    {"span": "(缺免責)", "level": "中", "rule": "未揭露風險",
     "note": "績效訴求需附『過去績效不代表未來』", "suggest": "句尾補免責"}
  ],
  "overall_risk": "高/中/低",
  "compliant_rewrite": "（附一個改寫成合規的版本，但不取代原文）"
}
```

- 風險分級：高（絕對化/保證/最高級）、中（缺揭露/比較未標基準）、低（用語偏軟）。
- 規則來源：`config/compliance.yaml`（禁詞、必揭露語句）+ LLM 依投信投顧公會廣告自律規範判讀。
- 前端呈現：原文案 + **黃/紅底標注 highlight** + hover 看理由與建議 + 一鍵切換「合規改寫版」。
- **不擋發布**：使用者可複製任一版本；標注只是把風險攤開讓人自己決定。

> 法規定位：內部行銷發想輔助。對外正式發布前仍建議經法遵核可——但發想階段不被合規綁手。

---

## 11. 後端 API 合約（FastAPI）

供 Next.js 讀取（皆為唯讀 JSON）：

| Method | Path | 說明 | 回傳 |
|---|---|---|---|
| GET | `/api/daily?date=` | 當日總覽（最強賣點+各產品摘要） | `{date, top_signal, products[]}` |
| GET | `/api/etf/{id}?date=` | 單檔賣點卡（Top3 賣點+指標+文案） | `{etf, metrics, signals[], copy[]}` |
| GET | `/api/etf/{id}/history` | 單檔指標時序（畫圖） | `{series[]}` |
| GET | `/api/signals?date=&detector=` | 賣點明細/篩選 | `{signals[]}` |
| GET | `/api/compare?ids=` | 復華 vs 競品對照 | `{rows[]}` |
| GET | `/api/health` | 管線健康/資料新鮮度 | `{last_run, stale[]}` |

- Pydantic response model 定義型別，前端用 `openapi-typescript` 自動產 TS 型別。
- 全部讀 DB，不在 request 時計算（重運算在管線完成）。

---

## 12. 前端儀表板（Next.js）

技術：Next.js 14 App Router + TypeScript + Tailwind + shadcn/ui + TanStack Table + Recharts。複製 etfinfo 的清爽多頁式風格，但內容以復華為主角。

| 頁面 | 路徑 | 內容 |
|---|---|---|
| 今日賣點榜 | `/` | 置頂「今日最強賣點」卡 + 三檔產品賣點摘要 + 資料日期/新鮮度 |
| 單檔賣點卡 | `/etf/[id]` | Top3 賣點(含證據圖表) + 指標面板 + 三長度合規文案(可複製) + 競品對照 |
| 賣點明細 | `/signals` | 全部訊號表格，可依偵測器/分數/日期篩選排序、看歷史 |
| 對照分析 | `/compare` | 復華 vs 同題材競品的報酬/規模/折溢價並排 |

UI 重點：
- 每個賣點卡顯示 **分數徽章 + 一句話賣點 + 佐證數字 + 可複製文案**。
- 文案旁顯示**合規狀態燈**（綠=pass / 黃=needs_review / 紅=blocked）。
- 圖表：淨值走勢、alpha、資金流、命中飆股貢獻瀑布圖。

---

## 13. 排程與部署

- **排程**：Prefect（或先用 APScheduler）每交易日 17:30 跑 `daily_flow`；失敗告警到 Slack/Email。
- **部署**：
  - backend（管線+API）：Docker 容器，DB 用 PostgreSQL（雲端託管或內部）。
  - frontend：Vercel 或內部 Node 伺服器（內網限定，因屬內部工具）。
- **環境變數**：`ANTHROPIC_API_KEY`、`DATABASE_URL`、各資料源設定。
- **存取控制**：MVP 內網/SSO 限員工存取。

---

## 14. 設定檔（產品清單）

`config/products.yaml`：

```yaml
benchmarks:
  taiex_tr: "發行量加權股價報酬指數"
  market_etf: "0050"

fh_products:            # 復華主角(可隨新發產品擴充)
  - id: "00991A"
    name: "復華台灣未來50主動式ETF"
    theme: "台股大型主動選股"
    benchmark: "taiex_tr"
    dividend_freq: "半年"
    audience: ["成長型", "核心配置"]
  - id: "00998A"
    name: "復華全球金融股票入息主動式ETF"
    theme: "全球金融股入息"
    benchmark: "global_financials"
    dividend_freq: "季"          # 待確認
    audience: ["入息族", "存股族"]
  - id: "00986D"
    name: "復華全球金融債券入息主動式ETF"
    theme: "全球金融債入息"
    benchmark: "global_fin_bond"
    dividend_freq: "月"          # 待確認
    audience: ["保守入息", "退休族"]

peers:                  # 對照組：全市場主動式ETF(自動由ingest補齊)
  auto_discover: true
  manual_focus: ["00981A", "00403A", "00992A"]
```

---

## 15. 分階段路線圖

| 階段 | 時程 | 內容 | 交付 |
|---|---|---|---|
| **Phase 0** | 3-5 天 | 驗證所有公開資料 endpoint/欄位、確認復華三檔配息頻率與對標、建 repo 骨架+DB | 可跑的 connector 雛形 + schema migration |
| **MVP** | 2-3 週 | 6 個 ★ 偵測器 + 指標引擎 + 評分 + FastAPI + 今日賣點榜頁 | 內部每日賣點儀表板上線 |
| **P1** | +3-4 週 | 18 偵測器全開 + Claude 文案 + 合規護欄 + 競品對照 + 命中率追蹤 | 完整行銷彈藥庫 |
| **P2** | 後續 | LINE 推播 + PDF 日報 + 複製 etfinfo 全前台(總覽/比較/投組/回測) + 對外評估 | 對外可上線版本 |

---

## 16. 合規與法律

- **資料**：僅用公開來源；不複製 etfinfo 原始碼或受版權保護之設計，**重建相同功能**。遵守各站合理抓取規範。
- **文案**：全數通過合規護欄；對外發布前須經法遵/督察核可。績效標期間與對標、附免責、配息型揭露收益平準金。
- **定位**：內部行銷輔助工具，非投顧、非投資建議。
- **資安**：內網/SSO 限員工；API key 走 secret manager。

---

## 17. 開放問題（待確認）

1. ~~復華 00998A／00986D 的確切配息頻率與對標基準~~ → **已核實(M1-2)**：00998A 季配(2/5/8/11月底，年化逾10%)、00986D 月配(目標息率6~7%)。對標基準：兩檔為全球股/債，無 TWSE 可比序列 → 績效以 NAV 含息總報酬為準（`benchmark=null`）；逐期配息金額仍待官方公告接入以做完整含息再投入。
2. 是否需納入復華**被動式 ETF**（如 00929、00924）作為延伸主角？目前 MVP 僅主動式。
3. `theme_fit` 的「當日熱門題材」要用哪個公開來源（個股漲幅彙總 vs 新聞熱搜）？
4. 內網部署的身分驗證機制（SSO 供應商）。
5. 「命中率/被採用率」回饋要由誰、用什麼介面標記（影響 P1 評分微調）。

---

## 18. 進階情報引擎（擴充需求）

> 這六個模組是「找賣點」的真正火力，對應你提的：持股差異化、多週期績效、成交量突出、分點推敲買家、社群/KOL 地毯搜尋、同業招數複製。

### 18.1 持股差異化引擎（獨門 vs 同業）— 「我們的選股厲害在哪」

**目的**：用全市場主動 ETF 的每日持股，量化復華的選股**跟別家差在哪、特色在哪、賭對了沒**。

| 指標 | 定義 | 行銷用途 |
|---|---|---|
| 獨門持股 Unique Holdings | 復華持有，但同類同業 < X% 有持有的股票 | 「這幾檔是復華獨家卡位」 |
| 權重偏離 Divergence | `復華權重 − 同業平均權重`（z-score 排序） | 「我們重押○○，同業都低配」 |
| 主動度 Active Share | `0.5 × Σ|w_fund,i − w_bench,i|` | 「主動度高達 X%，真的有在選股」 |
| 持股重疊 Overlap | 與每檔競品的權重重疊 / Jaccard | 「跟 00981A 只重疊 X%，互補配置」 |
| 差異化下注成效 | 追蹤獨門股 / 偏離股的後續報酬 | 「獨門卡位的○○，事後大漲 X%，眼光獲驗證」 |
| 特色標籤 | 集中度、產業偏好、市值偏好(中小型 vs 大型)、換股頻率 | 自動生成「選股風格」一句話 |

**輸出**：差異化儀表板（獨門股表 + 權重偏離長條圖 + 競品重疊熱圖 + Active Share 數字），並餵給 `UNIQUE_HOLDING`/`DIVERGENT_BET` 偵測器。

> **實作狀態（2026-06-15，M2 引擎完成）**：差異化**引擎已落地並測過**（`arm/diff_engine.py` + `arm/connectors/issuers/` 統一介面 + 4 偵測器 + 9 單元測試）。主動度 Active Share 對標 0050（`config/benchmark_0050.json` 近似公開權重快照、標 Tier B/as-of）**已即時真實**（00991A 實測 76%）。跨家「獨門/重疊/領先」需**競品每日持股**——再次查證：TWSE PCF 無乾淨公開 JSON、各投信官網皆 SPA（元大走 `etfapi.yuantaetfs.com` 但 endpoint 不公開、統一/群益/野村抓不到結構化資料），**無單一權威公開源**。故採 source-agnostic 雙軌：(a) 逐家 adapter slot；(b) **drop-in 承接層** `config/competitor_holdings/{fund_id}.json`（落檔即生效、引擎不動，已實測獨門/偏離/重疊/領先全數點亮）。第三方彙整源（CMoney/玩股網/付費）下載落成同格式即可，標 Tier B。**復華自家持股 + 主動度已 100% 可算**。**競品逐日持股缺口已補（2026-06-15）**：`arm/connectors/etfinfo.py` 接 etfinfo.tw JSON API（`/api/etf/{code}.holdings`，`source` 多為 issuer-official），`scripts/fetch_etfinfo.py holdings` 落成 `config/competitor_holdings/{code}.json`（Tier B，標 as-of + provenance，待投信官網核實）。實測 6 競品（統一 00981A/00403A、群益 00992A、野村 00980A/00985A、元大 00990A）全數落地，00991A 跨家獨門/偏離/重疊/領先**已即時真實**（國巨偏離 +6.4pt 居同業之冠、與統一重疊 Jaccard 40%）。

### 18.2 多週期績效引擎 — 「挑對我們最有利的週期」

在 §7 多週期指標之上，建「**最佳切角探測 best-angle finder**」：

- 對每檔復華產品產生**績效矩陣**：週期 {1d,3d,1w,2w,1m,3m,6m,YTD,SI} × {報酬, Alpha, 同類排名}。
- 自動挑出「**對復華最有利的週期 + 對標**」當主打（例：3 日輸、但 YTD 大贏 → 主打 YTD）。
- 同時輸出「**這個週期把誰比下去了**」的競品清單（被超越名單 → `BEAT_PEERS_MULTI` 偵測器）。
- 行銷卡顯示：「近 ___（系統挑的週期）報酬 +X%，在 N 檔台股主動 ETF 中排第 ___，超越 00981A、00992A…」。

### 18.3 成交量突出偵測 — 「人氣量能」

- 爆量訊號：`當日量 > N × 20日均量`。
- 量能同類排名：成交量擠進主動 ETF 前 X 名 → 「今日最熱門主動 ETF」。
- 換手率：量 / 在外流通張數，衡量熱度。
- 競品量能對照：哪些競品被我們的量能比下去。
- 對應 `VOLUME_SPIKE` 偵測器。

### 18.4 籌碼分點推敲模組 — 「誰在大買」

**目的**：某分點大量買進 → 推敲可能買家（聰明錢佐證）。

- **資料源（公開）**：證交所每日「券商分點買賣超」；第三方彙整（玩股網、Wantgoo、Histock、XQ）做補充與交叉驗證。
- **對象**：(a) 復華 ETF 本身的分點進出；(b) 重倉成分股的分點進出（命中飆股的籌碼面）。
- **推估邏輯**：
  1. 關鍵分點 = 區間買超最多的分點。
  2. **分點 → 買家身份推估**：維護「分點別名對照表」——知名外資分點（美林/摩根/港商）、內資中實戶常用分點、特定地緣分點（地緣性買盤/特定金主）。用啟發式貼標籤。
  3. 連續性：連續買超天數、買超占成交比。
- ⚠️ **務必標「推估」**：分點只到分公司層級，**真實身份無法 100% 確認**。所有買家推論在 UI 標「推估・非確認」。
- 對應 `SMART_MONEY` 偵測器；行銷話術：「聰明錢連 X 日進場（推估為外資分點）」。

> **實作狀態（2026-06-15，M3 引擎完成）**：籌碼推敲**引擎已落地並測過**（`arm/chips.py` + `arm/connectors/brokers/` 統一 `BrokerFlow` 介面 + `SMART_MONEY` 偵測器 + 想法引擎 `g_chip_branch` + `tests/test_chips.py` 8 綠）。關鍵分點識別／連續買超天數／買超佔成交比／身份推估（`config/broker_map.json`：代號 + 名稱關鍵字 → 外資/投信/中實戶/特定金主，一律標「推估」）**邏輯已 100% 可算**。查證分點 live 來源：證交所 `bsr.twse.com.tw` 逐檔 + 驗證碼、第三方（玩股網/Wantgoo/Histock/XQ）SPA 或付費，**無單一權威公開 live 源**（性質同 §18.1 競品持股）。故採 source-agnostic 雙軌：(a) **live adapter—Histock 已接**（`connectors/brokers/histock.py`，`load_flows` 預設啟用）；(b) **drop-in 覆蓋層** `config/broker_flows/{target_id}.json`（人工/第三方落檔即優先生效）。**券商分點已即時真實**（2026-06-16 接 Histock）：實測 00991A 本檔港商野村 +7,899 張(推估外資)、重倉南亞科/國巨/台積電皆外資分點大買；身份經 `broker_map` 名稱關鍵字推估、一律標「推估・非確認」。單日快照（連續天數退化單日、無總量時佔比 None，誠實降級）；證交所 `bsr`(驗證碼)/Wantgoo(會員制) 保留 slot。
>
> **法人籌碼替代源已補（2026-06-15）**：etfinfo.tw 無券商分點，但有 `/api/active/tracking`＝**主動ETF/投信『估算新進/加碼』**（誰被法人大買、幾檔ETF幾家投信、估算金額、建倉脈絡）。已接成 `arm/chips.institutional_flow`（本檔持股 ∩ 法人買盤清單）＋ `INSTITUTIONAL_BUY` 偵測器＋想法引擎「聰明錢共識」，`scripts/fetch_etfinfo.py active` 落成 `config/active_flow/{date}.json`。**這是法人(集合)層級、非個別券商分點**，標 Tier B「estimated・待核對」。實測 00991A：重倉國巨被 4 檔 ETF/3 家投信新進、估算新進+加碼約 29 億（與「復華重押國巨」互相印證的聰明錢共識）。

### 18.5 社群 / KOL 情報引擎 — 「地毯式撈賣點與聲量」

**目的**：把網路上網紅／社群講的賣點、想法、聲量全撈回來，**直接當行銷素材庫 + 競品監測**。

- **監看來源**：YouTube、FB 社團/粉專、IG、Threads、Dcard、PTT（Stock/ETF 板）、部落格（方格子 vocus、痞客邦）、財經論壇（fundhot、CMoney、股感、商周/今周刊/鉅亨/Yahoo 股市）、新聞。
- **流程**：
  1. 關鍵字監看：復華產品代號/名稱 + 競品代號 + 「主動式 ETF」。
  2. 抓取：YouTube Data API、RSS、合規爬取、（可選）第三方社群監測 API。
  3. **Claude 逐則分析**：情緒（正/負/中）、提到哪些賣點、用什麼說法、**是否疑似業配**、觸及/熱度推估。
  4. 入庫 `social_mentions`，萃取「**可借用賣點**」與「**可複製說法**」。
  5. 聲量儀表板：聲量趨勢、熱門賣點文字雲、**KOL 名單（誰在談、立場正負）**、復華 vs 競品聲量對比。
- **業配偵測**：用語（合作/邀約/廣告/#ad/#業配）、短期集中發文、話術高度雷同 → **反推同業正在投放哪些 KOL**（競品口碑佈局情報）。
- 法務風險（事後標注）：爬取條款、個資、著作權——標注於風險區，不擋流程。

**資料表**：
```sql
CREATE TABLE social_mentions (
  id BIGSERIAL PRIMARY KEY,
  platform TEXT, url TEXT, author TEXT, posted_at TIMESTAMPTZ,
  etf_id TEXT, is_competitor BOOLEAN,
  sentiment TEXT,                 -- pos/neg/neu
  selling_points JSONB,          -- 萃取出的賣點
  phrasing JSONB,                -- 可複製的說法
  suspected_ad BOOLEAN,          -- 疑似業配
  reach_estimate INTEGER,
  raw_text TEXT
);
```

### 18.6 同業行銷情報 + 話術複製庫 — 「對手的招，我們照抄改良」

**目的**：把同業的訴求、說法、銷售手段、口碑行銷全收進**可檢索的話術複製庫**，懷疑有銷售影子的都收。

- **監看**：各投信官網活動頁/新聞稿、財經新聞、廣告、KOL 業配、券商通路頁、活動（定期定額/抽獎/手續費優惠/首購禮）。
- **萃取維度**：訴求 slogan、績效包裝手法（挑哪個週期/對標）、題材包裝、通路與門檻策略、配息設計行銷、公關事件操作、口碑/業配佈局、姊妹商品連動。
- **輸出**：每條一張「招數卡」，欄位：來源 / 招數類型 / 原文 / 可複製性(高中低) / **套用到復華怎麼改** / 合規標注（事後）。
- 與 §10 文案層串接：寫文案時自動參考話術庫找靈感。

```sql
CREATE TABLE competitor_tactics (
  id BIGSERIAL PRIMARY KEY,
  competitor TEXT, etf_id TEXT, source_url TEXT, observed_at DATE,
  tactic_type TEXT,              -- 績效訴求/題材包裝/通路/配息/公關/口碑...
  raw_quote TEXT,
  reusability TEXT,             -- high/med/low
  fh_adaptation TEXT,          -- 套用到復華的改法
  compliance_note TEXT
);
```

---

## 19. 競品行銷情報實況附錄（已實地搜集）

> 以下為本次規劃當下實際上網蒐集的情報，已可作為話術庫種子資料與 MVP 假資料。**數字以新聞為準、未全部對帳，上線前需以官方資料核實。**

### 19.1 主角產品事實底牌（00991A）
- 2025/12/18 掛牌，發行價 10 元，**首募 108 億，刷新台股主動式 ETF 首募紀錄**。
- 選股邏輯：市值前 50 大依成長潛力調權重 + 從第 51~150 大挖「未來會擠進前 50」的潛力股。
- **科技股比重 > 85%**（強勢題材順風，但系統性回檔跌幅可能大於 0050 → 風險揭露點）。
- 半年配（6 月底 / 12 月底評價），配息來源可能含收益平準金。
- 費用率約 0.84%~1.0%（高於 0050 的 0.32% → 競品/被動會攻擊的點，要先準備說法）。
- 另兩檔主角：00998A 全球金融股票入息、00986D 全球金融債券入息（配息頻率待官方核實）。

### 19.2 同業招數清單（可複製，已標可複製性）

| 競品 | 招數 | 類型 | 可複製性 | 套用到復華的改法 |
|---|---|---|---|---|
| 統一 00981A | 「不到 1 年漲逾 6 成、年報酬 70.98% 完勝 0050(36.87%)」 | 績效訴求 | 高 | 挑復華最有利週期+對標，同樣對比 0050（合規：標期間/免責） |
| 統一 00403A | 募資破 800 億當新聞「改寫紀錄」 | 公關事件 | 高 | 復華已有「首募 108 億破紀錄」可同樣操作 |
| 統一 00403A | 「1 萬元就能買」低門檻 | 通路/門檻 | 高 | 主打定期定額小額入手 |
| 統一 00403A | 21 家代銷通路鋪貨 | 通路 | 中 | 盤點復華代銷家數做對比 |
| 統一 00403A | 配息月份「錯開」→ 打造月月領組合 | 配息設計 | 高 | 復華多檔搭配組「現金流月曆」 |
| 統一 00403A | 掛牌首日發文「別加價買、先確認 3 件事」 | 公關/形象 | 高 | 負責任形象 + 製造熱度，可仿 |
| 統一/群益 | 「小台積電們」題材包裝 | 題材包裝 | 高 | 復華科技股>85%，可包「下一個護國群山」 |
| 群益 00992A | 「2026 今年漲逾 6 成、Q1 領跑」短週期戰報 | 績效訴求 | 高 | 用多週期引擎自動產戰報 |
| 全業界 | 「70 萬人轉向相信經理人」人氣訴求 | 人氣/社會認同 | 高 | 用受益人數成長講「X 萬人選擇復華」 |
| 全業界核心話術 | 超額報酬/打敗大盤、專業經理人操盤、掛牌便利+靈活選股雙重優勢 | 訴求 slogan | 高 | 直接沿用為主訴求骨架 |

### 19.3 KOL / 媒體聲量地景（監看名單種子）
- **財經內容站常態報導**：股感 StockFeel、豐雲學堂（永豐）、MoneyDJ、今周刊、商周、天下、鉅亨、Yahoo 股市、經理人、Business Insider TW、Pocket、TVBS。
- **社群/部落格**：方格子 vocus（已見 00991A 拆解筆記）、PTT 股票公社、fundhot 論壇、個人理財部落格（如 stevenhongisme「稀飯套餐」）。
- **觀察**：00991A 已有大量「成分股/配息/績效解析」型內容，**但缺少強力 KOL 推播聲量**（相對 00981A/00403A 的話題度）→ **這是缺口也是機會**，行銷可主動經營 KOL。

### 19.4 雷區（要避開的負面案例）
- udn 報導批評部分主動式 ETF「**荒謬行銷**、把 ETF 當追飆股工具、吃 00940 豆腐」。
- 對 00991A 的常見質疑：**費用率偏高**、科技股過度集中、半年配（不如月配吸睛）。
- → 文案策略：主打「主動選股價值 + 風險分散後的科技成長」，**正面回應費用率**（用超額報酬攤提），別碰「追飆股」式話術。

---

## 20. 資料正確性保證（Tier 分級）

> 對應需求：**績效數據 + 持股張數必須 100% 正確**，其他情報不強制核實。

### 20.1 資料分級
| Tier | 內容 | 要求 | 來源 |
|---|---|---|---|
| **A（必須 100% 正確）** | 績效（報酬/Alpha）、持股**張數**、NAV、AUM、在外單位數、折溢價 | 走權威來源 + 品質閘門 + fail-loud | 見 20.2 |
| **B（情報參考）** | 競品行銷、社群/KOL、分點買家推估 | 不強制核實，標來源與信心、推估註記 | 公開網路 |

### 20.2 Tier A 權威來源（已實測串通）
- **績效（官方收盤）**：TWSE `STOCK_DAY_ALL`（當日全上市）+ `STOCK_DAY`（單檔逐月歷史）。
- **張數 / NAV / AUM**：復華官網 `GET /api/assetsExcel/{fund_id}/{YYYYMMDD}` → 官方持股 xlsx（含每檔證券代號/名稱/**股數**/金額/權重，及 NAV、AUM、在外單位數）。
- **fund_id 對照（M1-1 已補齊）**：00991A=`ETF23`、00998A=`ETF24`、00986D=`ETF25`（由 `assetsExcel/ETF{n}` 逐號探勘確認，xlsx 內含證券代碼可驗證）。
- **NAV 含息歷史（M1-4）**：`nav_history` 由 `assetsExcel` 逐交易日回補（00991A 114 天、00998A/00986D 各約 50 天），為績效權威序列。
- **受益人數（M1-5）**：集保 TDCC 開放資料 id=1-5「集保戶股權分散表」第 17 分級(合計)，落 `holders_history`（週更）。政府憑證走系統 `curl`（仍驗證）。

### 20.3 品質閘門檢查（已實作於 `arm/quality.py`）
| 檢查 | 等級 | 通過標準 | 00991A 實測 |
|---|---|---|---|
| 價格序列完整 / 日期遞增不重複 | CRITICAL | 無缺漏亂序 | ✅ 114 筆 |
| 最新交易日吻合 | CRITICAL | = TWSE 最新交易日 | ✅ 2026-06-12 |
| 收盤價皆正數 | CRITICAL | 無 null/≤0 | ✅ |
| **NAV × 在外單位數 ≈ AUM** | CRITICAL | 誤差 < 0.5% | ✅ 差 0.0028% |
| **權重合計 ≈ 100%** | CRITICAL | 95~105% | ✅ 98.07% |
| **持股股數皆為正** | CRITICAL | 無 ≤0 | ✅ 50 檔 |
| 折溢價合理 | WARN | \|x\| < 10% | ⚠️ +0.21% |

### 20.4 原則與稽核
- **Fail-loud**：Tier A 任一 CRITICAL 未過 → **該訊號家族不產出**（寧缺勿錯）。
- **交叉對帳**：收盤(TWSE) × NAV(復華) 算折溢價互驗；AUM × 單位數×NAV 互驗；P1 再加「復華 NAV vs 公會/TWSE 第二來源」雙核對。
- **稽核軌跡**：`etf_daily` 存 `src_price`/`src_nav` 來源欄位；原始回應快取於 `data/http_cache`，可回溯重現。

> 同類排名引擎（`arm/peers.py`）細節見 [Part II · M0](#m0--可執行骨架--想法引擎--每日排程已完成規格-5-9-20-21)；版本演進見文末 [Changelog](#變更紀錄-changelog)。

---

## 21. 多元想法組合引擎（philosophy：每天給「各種想法」而非「一個冠軍」）

> 依使用者明確指示：不要「必勝單一解」，要每天針對架構給**多元想法**；加重**籌碼/題材/內容創意**；合規**事後標注、不擋發揮**。

**`arm/ideas.py`** 把輸出從 argmax 改為「想法組合 portfolio」：
- **涵蓋面向（每個都有 generator）**：績效(多週期)、籌碼經理人動作、題材時事、同類排名/誰被比下去、成交量突出、持股差異化(自體真實+跨家待接)、配息時程倒數、分點推敲(待接)、社群KOL、同業招數複製、逆向誠實。
- **多樣性機制**：類別加權（籌碼/題材×1.5、內容創意×1.4）＋**主題日**（週一績效/二籌碼/三題材/四同業/五逆向…）＋**防重複**（讀近 5 日報告標題降權）＋**wildcard**（每天硬塞一個冷門角度）。
- **合規事後標注**：`annotate()` 標 🟢🟡🔴（禁詞=高、缺免責=中），附建議改法，但**不阻擋**。
- **每日報告**：寫 `reports/{date}_{etf}.md`；情報層（獨門/分點/KOL/同業）由 Claude 每日補實。
- **情報種子**：`config/intel_seed.json`（同業招數、KOL 名單、題材對照、配息排程），可持續擴充。

**每日自動排程**：`scripts/daily_run.sh` + launchd `~/Library/LaunchAgents/com.fhtrust.fharm.daily.plist`，週一～五 17:40 自動跑並產出當日想法報告。

> **兩層架構**：(1) **資料想法層**＝本機 launchd 自動跑（績效/籌碼/題材/排名/配息…，已全自動）。(2) **創意情報層**＝KOL 地毯搜尋、競品最新招數、創意文案，需 LLM；目前由 Claude 在 session 補實，未來可在 repo 進 git 後改用排程雲端 routine 全自動。

---

# Part II — 建置路線圖（Roadmap / Checklist）

> 與 Part I 互為表裡：規格說「設計成什麼」，路線圖說「依什麼順序做出來」。每個里程碑標注對應規格章節。
> 本路線圖取代並擴充 §15 的高階分階段表。
> **圖例**：`[x]` 已完成　`[~]` 部分完成　`[ ]` 待辦　`★` 使用者高優先（籌碼/題材/創意/跨家差異/分點/KOL/同業）。

## 進度總覽

| 里程碑 | 主題 | 對應規格 | 狀態 |
|---|---|---|---|
| M0 | 可執行骨架 + 想法引擎 + 每日排程 | §5–§9, §20, §21 | ✅ 完成 |
| M1 | 多檔產品 + 資料正確性強化（NAV含息、規模受益人） | §4, §7, §20 | ✅ 完成 |
| M2 ★ | 跨家持股差異化（獨門/重疊/主動度） | §18.1 | ✅ 完成（主動度即時真實；**競品持股已接 etfinfo live**） |
| M3 ★ | 籌碼分點推敲買家 | §18.4 | ✅ 完成（**券商分點 Histock live + 法人籌碼 etfinfo live**） |
| M4 ★ | 創意情報層自動化（KOL/社群/同業招數） | §18.5, §18.6 | 🟡 引擎/介面完成（live adapters + 雲端 routine 待授權） |
| M5 ★ | 題材/時事引擎（動態熱點） | §8(#13), §21 | 🟢 引擎完成（盤面熱度動態化；新聞熱搜/自動擴充待補） |
| M6 | Claude 文案層 + 合規 LLM 標注 | §10 | ⏳ 待辦 |
| M7 | 後端服務化 + Next.js 儀表板 | §11, §12 | ⏳ 待辦 |
| M8 | 通路推播 + 命中率回饋 | §9, §13 | ⏳ 待辦 |
| M9 | 維運 / 監控 / 部署 | §13 | ⏳ 待辦 |

---

## M0 — 可執行骨架 + 想法引擎 + 每日排程　✅ 已完成　（規格 §5–§9, §20, §21）

- [x] M0-1 repo 骨架（`arm/` 套件、`config/`、`scripts/`、`reports/`、`docs/`）
- [x] M0-2 HTTP 層（`arm/http.py`，重試/快取/SSL 退回）、SQLite 落地（`arm/db.py`，§5）
- [x] M0-3 TWSE 連接器（`STOCK_DAY_ALL` 當日 + `STOCK_DAY` 歷史，官方收盤；§4, §20.2）
- [x] M0-4 復華持股連接器（`/api/assetsExcel/{fund_id}/{date}` xlsx → 股數/NAV/AUM；§20.2）
- [x] M0-5 資料品質閘門（績效+張數 100%；§20.3）
- [x] M0-6 指標：多週期報酬/Alpha、折溢價、持股張數 diff（§7）
- [x] M0-7 全市場主動 ETF 同類排名（含 YTD 公平性規則；`arm/peers.py`）
- [x] M0-8 偵測器庫 9 個（§8）
- [x] M0-9 **多元想法組合引擎**（`arm/ideas.py`，11 面向 + 加權 + 主題日 + 防重複 + wildcard；§21）
- [x] M0-10 合規事後標注 `annotate()`（🟢🟡🔴 不擋；§10, §21）
- [x] M0-11 每日報告輸出 `reports/{date}_{etf}.md`
- [x] M0-12 每日自動排程（launchd `com.fhtrust.fharm.daily`，週一~五 17:40；§21）

---

## M1 — 多檔產品 + 資料正確性強化　✅ 完成（2026-06-15）　（規格 §4, §7, §20）

- [x] M1-1 取得 fund_id（`assetsExcel/ETF{n}` 逐號探勘）：**00998A=ETF24、00986D=ETF25**（00991A=ETF23），補進 `config/products.json`（加 `asset_class`/`price_source`/`benchmark`）
- [x] M1-2 配息頻率/評價日確認（官方＋媒體核實）：00991A 半年配(6/12月底)、**00998A 季配(2/5/8/11月底，年化逾10%)**、**00986D 月配(目標息率6~7%)**；更新 `intel_seed.dividend_schedule` 並加 `income_highlight`，入息亮點進想法引擎
- [x] M1-3 多檔輪播：`run_daily all` 跑全部主角（`pipeline.run_all`），依交易日序數選「今日輪播主角」
- [x] M1-4 **NAV 含息總報酬**：`arm/navhist.py` 逐交易日回補 NAV/AUM 入 `nav_history`（`scripts/backfill_nav.py`）；績效改 NAV 含息（`total_return_series` 支援配息再投入，配息數字待官方逐期公告，現為純 NAV）；台股型保留 TWSE 市價交叉驗證。**全球股/債本就無 TWSE 市價，NAV 是唯一權威績效源**
- [x] M1-5 規模/受益人：規模＝`assetsExcel` 每日 AUM（比 SITCA 月報更即時，已入 `nav_history`）；受益人＝**集保 TDCC 開放資料(id=1-5) 合計列**（00991A 23.6萬人、00998A 1.4萬人、00986D 2,442人），落地 `holders_history`（週更，跨週相減算淨增）
- [x] M1-6 資金流偵測器：`FUND_INFLOW`（規模週增）、`MILESTONE`（規模破整數關卡）＋ 想法引擎「資金流」類別
- [x] M1-7 SSL 正規化：`http.py` 一律走 `certifi` 完整驗證、移除 `CERT_NONE` 退回；TDCC 政府憑證在嚴格模式無法驗證 → 改走系統 `curl`（仍驗證，不關閉 TLS）
- [x] M1-8 單元測試 `tests/`（25 passed）：metrics、quality(股/債分流)、peers 公平性、navhist 配息再投入、多資產解析器、合規標注
- [x] M1-9 交易日曆 `arm/calendar.py`：由 0050 官方序列判定交易日；流程對非交易日如實標 `stale`

✓DoD（達成）：**三檔都過 100% 閘門**；**績效為 NAV 含息總報酬**；**規模＋受益人入庫並有對應想法**（FUND_INFLOW/MILESTONE/資金流想法）；**`pytest` 全綠（25）**。
> 開放項：跨家差異化引擎已完成（M2，主動度即時真實；獨門/重疊待競品 live 來源，drop-in 已可承接）；NAV「含息」的逐期配息金額待官方公告接入（機制已就緒，現以純 NAV 呈現並如實標注）；全球股/債對標基準無 TWSE 可比序列（已標 `benchmark=null`）。

---

## M2 ★ — 跨家持股差異化（獨門 / 重疊 / 主動度）　✅ 完成（競品持股已接 etfinfo）　→需:M1　（規格 §18.1）

- [x] M2-1 競品 holdings 來源決策：再次查證各投信官網皆 SPA、無單一乾淨公開 JSON。
      採 **source-agnostic** 雙軌：(a) 逐家投信 adapter slot（`connectors/issuers/`）＋ (b) **drop-in Tier B 承接層**（`config/competitor_holdings/{fund_id}.json`，落檔即生效、不改碼）。
- [x] M2-2 統一持股介面 `Holding(fund_id,date,stock_id,stock_name,weight,shares,kind)`；`arm/connectors/issuers/`（`base.py` 介面 + `__init__.py` 註冊表 `COMPETITORS`）。復華自家走 live `assetsExcel`。
- [x] M2-3 台股主力競品（統一 00981A/00403A、群益 00992A、野村 00980A/00985A、元大 00990A）持股**已接 etfinfo live**：`arm/connectors/etfinfo.py` + `scripts/fetch_etfinfo.py holdings` 落成 `config/competitor_holdings/{code}.json`（Tier B，標 as-of/source/provenance）。6 競品全數落地，00991A 獨門/偏離/重疊/領先即時真實（國巨偏離 +6.4pt 居同業之冠）。各投信官網 SPA 的逐家 adapter slot 仍保留供日後直連。
- [x] M2-4 `arm/diff_engine.py`：獨門持股 / 權重偏離(z-score) / 重疊度(Jaccard+權重重疊) / 主動度 Active Share / 領先卡位 / 獨門股事後成效。`tests/test_diff_engine.py` 9 綠。
- [x] M2-5 0050 成分快照 `config/benchmark_0050.json`（近似公開權重，標 Tier B + as-of，可一鍵覆蓋；引擎對 equity 正規化到 100% 再算）。
- [x] M2-6 新偵測器：`UNIQUE_HOLDING`、`DIVERGENT_BET`、`ACTIVE_SHARE`、`LEAD_POSITION`（缺料即不觸發，誠實降級）。
- [x] M2-7 想法引擎「持股差異化」由樁改真實：主動度 vs 0050 **已即時真實**；跨家獨門/偏離/重疊在競品 drop-in 落檔後即真實，否則保留誠實「待接」標。

✓DoD（達成）：每日想法已含「主動度 76%（vs 0050，可追溯 Active Share 公式 + 基準 as-of）」；獨門/偏離/重疊/領先**已即時真實**——competitor 持股經 etfinfo 落地後實測 00991A：重押國巨 8.9%（同業均 2.5%、偏離 +6.4pt 居同業之冠）、獨門南亞科/台灣晶技、與統一 00981A 重疊 Jaccard 40%/權重 65%、與元大 00990A 僅 15%。競品來源為 Tier B（etfinfo issuer-official 彙整，標 as-of，待投信官網核實）。

---

## M3 ★ — 籌碼分點推敲買家　✅ 完成（券商分點 Histock live + 法人籌碼 etfinfo live）　→需:M1　（規格 §18.4）

- [x] M3-1 分點買賣超來源：**Histock 已接 live**（`arm/connectors/brokers/histock.py`）——個股/ETF「分公司進出」頁把當日買超/賣超前 N 大分點放在**靜態 HTML 表**（無需 JS/API/登入），逐 `<tr>` 解析成 `BrokerFlow`（外資分點命名帶地緣字樣，對得上 `broker_map`）。證交所 `bsr`（驗證碼）、Wantgoo（會員制）保留為 `SOURCES` slot。
      採 **source-agnostic** 雙軌：(a) live adapter（Histock，`load_flows` 預設啟用）＋ (b) **drop-in 覆蓋層**（`config/broker_flows/{target_id}.json`，人工/第三方落檔即優先生效）。
- [x] M3-2 對象：(a) 復華 ETF 本身分點；(b) 重倉成分股分點——pipeline 每日對「本檔 + 前 5 大重倉股」嘗試載入分點。
- [x] M3-3 分點別名對照表 `config/broker_map.json`（外資/投信/中實戶/特定金主；先比代號 `by_id`、再比名稱關鍵字 `by_name_keyword`）。
- [x] M3-4 統一介面 `BrokerFlow(target_id,date,broker_id,broker_name,net)`＋`arm/chips.py`：關鍵分點識別、**連續買超天數**、**買超佔成交比**、身份推估。`tests/test_chips.py` 8 綠。
- [x] M3-5 `SMART_MONEY` 偵測器（`arm/signals.py`）：買家推論一律標「推估・非確認」，缺料即不觸發（誠實降級）。
- [x] M3-6 想法引擎「分點推敲」由樁改真實：`g_chip_branch` 在分點落檔後輸出本檔/重倉股關鍵分點大買（標推估），否則保留誠實「待接」intel 樁。
- [x] M3-7 **法人籌碼替代源（etfinfo）已接**：etfinfo 無券商分點，但有 `/api/active/tracking`＝主動ETF/投信『估算新進/加碼』。`arm/chips.institutional_flow`（本檔持股 ∩ 法人買盤）＋ `INSTITUTIONAL_BUY` 偵測器＋想法「聰明錢共識」；`scripts/fetch_etfinfo.py active` → `config/active_flow/{date}.json`。標 Tier B「法人層級・estimated・待核對」（≠個別券商分點）。

✓DoD（達成）：(a) **券商分點已即時真實**（Histock live）——00991A 每日輸出「本檔/重倉股關鍵分點大買 +X 張，推估為○○（標推估・非確認）」（實測 2026-06-12：本檔 00991A 港商野村 +7,899 張(外資)、重倉南亞科 台灣摩根 +5,775、國巨 摩根 +3,550、台積電 美林 +1,911，皆推估外資）；(b) **法人籌碼即時真實**（etfinfo）——「重倉○○ 同步獲 N 檔 ETF/M 家投信買盤、估算 +Z 億（聰明錢共識）」（國巨 4 ETF/3 投信、約 29 億）。兩源並存：`SMART_MONEY`(分點・推估) + `INSTITUTIONAL_BUY`(法人・Tier B)。數字皆標來源/as-of 待核對。

---

## M4 ★ — 創意情報層自動化（KOL / 社群 / 同業招數）　🟡 引擎/介面完成（live adapters + 雲端 routine 待授權）　→需:M1　（規格 §18.5, §18.6）

> 此層原由 Claude 在 session 補；本里程碑做成「落檔即生效」的引擎＋source-agnostic 介面。
> live 爬取（涉 ToS/個資/著作權）與雲端 routine 為**對外動作，待使用者授權**逐家接（slot 已備）。

- [~] M4-1 **本機 `git init` 完成**（含 `.gitignore`：`data/` 執行期快取/DB/log 不入庫；初始 commit 已建於 `main`）。**推私有 repo 待授權**（讓雲端 routine 可 clone）。
- [~] M4-2 社群/KOL 監看：`arm/connectors/social/` source-agnostic 介面 + drop-in（`config/social_mentions/{date}.json`，`_` 開頭不載入）。**live adapter slot 已備**（`SOURCES`：YouTube/PTT/Dcard/vocus/新聞；`LIVE_ADAPTERS` 待授權後逐家填入、自動納入不改呼叫端）。
- [~] M4-3 逐則分析：`social.analyze()` **確定性 baseline**（情緒、賣點命中、**疑似業配**、聲量分級）；**`analyze(m, llm=...)` 預留 Claude 逐則深析接口**（接上不動呼叫端）。
- [ ] M4-4 同業招數自動蒐集：投信官網新聞稿/活動頁 → `competitor_tactics`（爬取待授權；現由 `intel_seed.competitor_tactics` 人工維護 + `g_competitor` 每日輪換餵入）。
- [x] M4-5 話術複製庫餵想法：`g_kol` 由樁改真實——把社群賣點（最高聲量、賣點命中、情緒）餵進想法引擎；同業招數續由 `g_competitor` 餵入。
- [x] M4-6 業配偵測 → 反推同業投放：`g_kol` 產「疑似業配 N 位 KOL → 反推投放佈局」想法（**僅內部素材、標『疑似・推估』、不對外指控**）。
- [ ] M4-7 **每日雲端 routine**（跑資料 + 地毯搜尋 + 想法 + 文案推送）：待 M4-1 後半（遠端 repo）+ 使用者授權。
- [~] M4-8 法務風險事後標注：社群情報一律 Tier B、標來源/as-of；drop-in README 載明 ToS/個資/著作權鐵則；疑似業配只作內部反推。逐則法務 LLM 標注待 M4-3 LLM 接上。

✓DoD（部分達成）：社群情報「落檔即生效」——`config/social_mentions/{date}.json` 一落地，`g_kol` 即輸出「社群熱議賣點（聲量/情緒）＋疑似業配反推投放＋負評→反擊話術」，含來源與 Tier B 標記（`tests/test_social.py` 11 綠）。**未達成（待授權）：live 自動爬取、每日雲端 routine、Claude 逐則 LLM 深析**——介面/slot 全備，授權後 drop-in 不改碼。

---

## M5 ★ — 題材 / 時事引擎（動態熱點）　🟢 引擎完成（2026-06-15）　→需:M1　（規格 §8 #13, §21）

- [x] M5-1 當日強勢題材來源：`arm/themes.py` 由 `STOCK_DAY_ALL` 全市場個股漲幅彙總算題材熱度（成分股平均漲幅×強漲檔數×上漲廣度）。**母體=TWSE 上市**（上櫃如群聯/旺矽/世界先進不計熱度，仍計本檔權重，已標注）；新聞熱搜源待 M4 創意層補。
- [~] M5-2 題材對照表升級：`intel_seed.theme_map` 改 **grouped + stock_id 為鍵**（`{題材:{id:名稱}}`，跨 TWSE/復華零歧義、避開「聯電⊂群聯電子」子字串誤判），人工可維護；自動擴充待補。
- [x] M5-3 `THEME_TAILWIND` 動態偵測（`arm/signals.py`）取代靜態映射；`theme_fit` 評分改吃當日真實題材熱度。
- [x] M5-4 想法引擎「題材」綁定當日真實熱點：`g_theme` 由 `ctx["theme_tailwinds"]` 產生「重倉產業＝當日強勢題材」想法（個股↔題材↔盤面），全球型無 TWSE 市價時誠實降級。`tests/test_themes.py` 7 綠。

✓DoD（達成）：00991A 每日題材想法反映**真實盤面熱點**（實測資料日 2026-06-12：重倉【AI半導體龍頭】台積電+聯發科 19.3% 全紅順風、【AI載板/PCB/CCL】欣興 +5.6% 領軍），非固定清單；題材熱度與成分股漲幅可逐檔追溯。**待補：新聞熱搜來源、題材表自動擴充**（歸 M4 創意層）。

---

## M6 — Claude 文案層 + 合規 LLM 標注　⏳　→需:M4-1　（規格 §10）

- [ ] M6-1 `arm/copy/generator.py`：每個想法生成 line/ig/sales/punchy 多版本（數字只取自 evidence）
- [ ] M6-2 合規升級：規則層 + Claude 法遵審查層（逐句風險分級 + 合規改寫版，仍不擋）
- [ ] M6-3 文案入庫 `copy`，前端一鍵複製 + 切換合規改寫版
- [ ] M6-4 設定化禁詞/必揭露 `config/compliance.yaml`

✓DoD：每個想法附 3~4 種長度文案 + 合規標注 + 一鍵合規改寫版。

---

## M7 — 後端服務化 + Next.js 儀表板　⏳　（規格 §11, §12）

- [ ] M7-1 SQLite → PostgreSQL（SQLAlchemy + Alembic）
- [ ] M7-2 FastAPI 唯讀 API：`/daily`、`/etf/{id}`、`/signals`、`/compare`、`/differentiation`、`/health`
- [ ] M7-3 `openapi-typescript` 自動產前端型別
- [ ] M7-4 Next.js 頁面：今日想法組合 / 單檔想法卡 / 持股差異化 / 同類排名對照 / 社群聲量+招數庫
- [ ] M7-5 圖表：淨值、Alpha、資金流、命中飆股瀑布、持股異動視覺化

✓DoD：內網可開網頁看當日多元想法卡 + 差異化 + 排名 + 情報，資料新鮮度可見。

---

## M8 — 通路推播 + 命中率回饋　⏳　（規格 §9, §13）

- [ ] M8-1 通路輸出：LINE 推播 / Email 日報 / PDF 圖文日報
- [ ] M8-2 命中率/採用率記錄介面
- [ ] M8-3 回饋微調評分權重（採用率回灌 `CAT_WEIGHT`/偵測器強度）
- [ ] M8-4 A/B 文案測試

✓DoD：每天自動把想法組合推到指定通路；採用率可追蹤並回饋引擎。

---

## M9 — 維運 / 監控 / 部署　⏳　（規格 §13）

- [ ] M9-1 失敗告警（pipeline 失敗 → Slack/Email）
- [ ] M9-2 資料新鮮度監控（缺漏標示/告警，fallback 上一交易日）
- [ ] M9-3 Docker 化 + CI（lint/test）+ 部署
- [ ] M9-4 備份與稽核（原始快取、來源欄位、可回放；§20.4）
- [ ] M9-5 儀表板存取控制（SSO/內網限員工）

✓DoD：無人值守每日運行，故障有告警，資料可稽核回放。

---

## 橫切關注（持續進行）

- [ ] X-1 設定化：產品清單、權重、禁詞、來源 endpoint 全進 `config/`
- [ ] X-2 合規定位聲明：內部行銷輔助、非投顧；對外發布前經法遵核可（§16）
- [ ] X-3 資料分級維護：Tier A 走閘門、Tier B 標來源與信心（§20.1）
- [ ] X-4 文件同步：每完成一個里程碑更新本 SPEC（Part I 設計 + Part II 勾選）

---

## 建議執行順序（最順的一條路）

1. **M1** 打穩多檔 + NAV 含息 + 規模受益人（後面所有想法的養分）
2. **M2 ★** 跨家差異化（你最想要的「跟別家差在哪」）
3. **M3 ★** 分點推敲 + **M5 ★** 題材動態（獨立、可平行）
4. **M4 ★** 創意情報層自動化（需先 git）
5. **M6** 文案層 → **M7** 儀表板 → **M8** 通路/回饋 → **M9** 維運

> 進度：**M1 / M2 / M3 / M5 完成**（NAV 含息、跨家差異化＋競品持股 etfinfo live、籌碼推敲＝券商分點 Histock live＋法人籌碼 etfinfo live、題材動態）。新增 `arm/connectors/etfinfo.py`（第三方彙整：競品持股/配息/法人籌碼）＋ `arm/connectors/brokers/histock.py`（券商分點 live）。下一步建議：**M4 創意情報層**（需先 `git init` 跑雲端 routine）＋ 入息比較引擎（etfinfo 配息/殖利率已可取）＋ 分點連續天數歷史（Histock 多日）。

---

## 變更紀錄 Changelog

- **v0.12（外接最大化 + M4 live adapters + 雲端 routine，2026-06-16）**：**功能最大化** —— (1) **券商分點外接最完整源 FinMind**（`arm/connectors/brokers/finmind.py`，`TaiwanStockTradingDailyReport`：全分點+多日+量；需 `FINMIND_TOKEN` 付費），`load_flows` 優先序 drop-in > FinMind > Histock。(2) **Histock 多日歷史**（`arm/connectors/brokers/history.py` 每日落快照累積，`chips.consecutive_buy_days` 加 `all_dates` 缺席中斷→真實「連續買超天數」）。(3) **外資分點合計**（`chips.aggregate_by_identity` + `FOREIGN_BRANCH_BUY` 偵測器 + 想法「外資共識」）——實測 南亞科 6 家外資分點同步 +21,081 張。(4) **M4 社群 live adapters 全接**（`social/{news,ptt,dcard,facebook,youtube}.py`，免費源 news/ptt/dcard 永遠註冊、YouTube/FB 需金鑰才註冊；`http.get_bytes` 加 headers/cookie 支援）；Dcard 現多被 Cloudflare 擋（需 `DCARD_COOKIE`/合作金鑰）、FB 受 Graph API 限制（只讀有權限粉專）。(5) **Claude 逐則深析接上**（`social/llm.py`，`claude-opus-4-8` 結構化輸出，`analyze(m, llm=)` 經 `default_analyzer()` 注入 `g_kol`；需 `ANTHROPIC_API_KEY`）。(6) **每日雲端 routine**（`scripts/daily_routine.sh` + `.github/workflows/daily.yml`，cron 週一~五 17:40 台北，金鑰走 Actions secrets，未設則該層誠實降級）。所有外接 Tier B、缺金鑰即降級不崩。`tests/`（+chips identity/finmind/histock/broker_history/social_adapters）。
- **v0.11（M4 引擎/介面完成，2026-06-16）**：創意情報層自動化第一階段。**本機 `git init`**（`.gitignore` 讓 `data/` 執行期快取/DB/log 不入庫，初始 commit 於 `main`；推遠端待授權）。新增 **`arm/connectors/social/`** source-agnostic 社群/KOL 介面（統一 `SocialMention`，與 M2/M3 同雙軌：`LIVE_ADAPTERS` slot + drop-in `config/social_mentions/{date}.json`）；`social.analyze()` 確定性 baseline（情緒/賣點命中/**疑似業配**/聲量分級）＋預留 `analyze(m, llm=...)` LLM 深析接口。想法引擎 `g_kol` 由樁改真實（社群熱議賣點＋疑似業配反推投放＋負評→反擊話術，全標 Tier B「推估・待核實」、業配不對外指控）。**嚴格與 M3 brokers/chips 解耦、不打架**。live 爬取/雲端 routine/Claude 逐則深析為對外動作，slot 全備、待授權。`tests/` 68 passed（+11）。

- **v0.11（M3 完成：券商分點 Histock live，2026-06-16）**：新增 `arm/connectors/brokers/histock.py`——Histock「分公司進出」靜態 HTML 表逐 `<tr>` 解析成 `BrokerFlow`（無 API/登入），`brokers.load_flows` 預設 live（drop-in 可覆蓋）。**個別券商分點缺口已補**：實測 00991A 本檔港商野村 +7,899 張、重倉南亞科/國巨/台積電皆外資分點大買（經 `broker_map` 名稱關鍵字推估外資/投信/中實戶、一律標「推估・非確認」）。修掉解析錯位 bug（買/賣兩側空白欄須保留、逐列 10 欄對齊）。M3 升 ✅（`SMART_MONEY` 分點 + `INSTITUTIONAL_BUY` 法人雙源並存）。`tests/test_histock.py`（含空白欄對齊回歸），`tests/` 60 passed（+3）。
- **v0.10（etfinfo 第三方彙整源接入，2026-06-16）**：新增 `arm/connectors/etfinfo.py`（etfinfo.tw Nuxt JSON API：`/api/etf/{code}`、`/api/etf/list`、`/api/active/tracking`）＋ `scripts/fetch_etfinfo.py` 落地器。**補實 M2 競品逐日持股**（6 競品 → `config/competitor_holdings/{code}.json`，Tier B 標 as-of/source）→ 00991A 獨門/偏離/重疊/領先即時真實（國巨偏離 +6.4pt 居同業之冠、與統一重疊 Jaccard 40%）；M2 升 ✅。**補實 M3 法人籌碼替代源**（主動ETF/投信估算新進 → `arm/chips.institutional_flow` + `INSTITUTIONAL_BUY` 偵測器 + 想法「聰明錢共識」+ `config/active_flow/{date}.json`）→ 實測國巨被 4 ETF/3 投信新進約 29 億（與復華重押互證）。etfinfo **無券商分點**，個別分點仍 drop-in 待接；所有 etfinfo 數字標 Tier B「待投信官網核實」。`tests/` 57 passed（+8：institutional/active-flow/etfinfo 正規化）。
- **v0.9（M3 引擎完成，2026-06-15）**：籌碼分點推敲引擎上線（`arm/chips.py`）。統一 `BrokerFlow(target_id,date,broker_id,broker_name,net)` 介面（`arm/connectors/brokers/`，與 M2 持股同 source-agnostic 雙軌：adapter slot + drop-in `config/broker_flows/{target_id}.json`）。引擎算**關鍵分點淨買超／連續買超天數／買超佔成交比**，身份推估走 `config/broker_map.json`（代號 + 名稱關鍵字 → 外資/投信/中實戶/特定金主），**一律標「推估・非確認」**（分點僅到分公司）。新增 `SMART_MONEY` 偵測器（缺料即不觸發、誠實降級）；想法引擎 `g_chip_branch` 由樁改真實（對「本檔 + 前 5 大重倉股」推敲）。查證分點 live 無公開源（證交所驗證碼/第三方 SPA），故 drop-in 承接（已實測點亮）。`tests/` 49 passed（+8）。
- **v0.8（M5 引擎完成，2026-06-15）**：題材/時事引擎上線（`arm/themes.py`）。題材熱度由 `STOCK_DAY_ALL` 全市場個股漲幅**每日動態算出**（平均漲幅×強漲檔數×上漲廣度），取代固定清單；新增 `THEME_TAILWIND` 偵測器（`theme_fit` 評分改吃真實熱度）、想法引擎 `g_theme` 綁定「重倉產業＝當日強勢題材」。題材對照表改 **stock_id 為鍵的 grouped 格式**（跨 TWSE/復華零歧義，修掉「聯電⊂群聯電子」名稱子字串誤判；台積電 vs 台灣積體跨源對齊）；熱度母體=TWSE 上市（上櫃不計熱度、仍計權重，已標注）；全球型無 TWSE 市價時誠實降級。`tests/` 41 passed（+7）。
- **v0.7（M1 完成，2026-06-15）**：三檔主角全上線（00991A/00998A/00986D，fund_id ETF23/24/25）。績效主軸改 **NAV 含息總報酬**（`arm/navhist.py` + `nav_history`），全球股/債不依賴 TWSE 市價。解析器支援**股票(外股 ticker)/期貨(口數可負)/債券(ISIN 面額)** 多區段；品質閘門依資產類別分流仍 100% fail-loud。新增**交易日曆**(`arm/calendar.py`)、**受益人數**(集保 TDCC，`arm/connectors/tdcc.py` + `holders_history`)、**資金流偵測器**(FUND_INFLOW/MILESTONE)、多檔輪播(`run_all` + 今日主角)。SSL 強制 certifi 驗證。配息頻率官方核實並做入息亮點。`tests/` 25 passed。
- **v0.6**：整合 `todo.md` 進本文件 → 規格(Part I) + 路線圖(Part II) 合一；新增進度總覽、里程碑↔章節對應、執行順序。
- **v0.5**：多元想法組合引擎（§21，argmax→portfolio）、合規事後標注、每日 launchd 排程、`intel_seed.json`。
- **v0.4**：同類排名引擎（`arm/peers.py`）、YTD 公平性規則、`PEER_CHAMPION`/`BEAT_NAMED_PEERS`/`CONCENTRATED_PICK`。
- **v0.3**：資料正確性保證（§20）、Phase 0 可執行骨架、00991A 端到端跑通過閘門。
- **v0.2**：進階情報引擎（§18 持股差異化/多週期/量能/分點/社群KOL/同業話術）、競品情報附錄（§19）、合規改事後標注。
- **v0.1**：規格定稿（§1–§17 架構/資料源/schema/偵測器/評分/API/前端）。
