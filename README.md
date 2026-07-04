# 復華基金追蹤版本 · Fuh Hwa Fund Radar

追蹤 **復華投信共同基金**（全球股票型／全球平衡型）的每日情報工具。每天做兩件事：

1. 🧾 **持股介紹** — 每檔基金的基本資料 / NAV / 多期報酬 / 國家・產業配置 / **十大持有標的＋重點標的簡介**（月度官方揭露快照）。
2. 🗞️ **昨夜美股重大新聞** — 聚焦 Nasdaq／費城半導體／S&P500 的**公司與產業面**事件（AI／晶片／雲端／併購／財報／供應鏈…），兩種版型（Top 3 速寫包＋精簡版），附來源、台北時間戳與合規燈。

> 本版本刻意**不做「每天持股變化」**：共同基金僅月底揭露前十大持股、無逐日持股張數，故改以「持股介紹」呈現。（此為由主動式 ETF 行銷雷達改建的追蹤版本，ETF 專用的逐日換股/籌碼/文案引擎已非本版本主軸。）

---

## 追蹤清單（25 檔，見 `config/funds.json`）

**全球股票型**：復華美國新星(47)、全球大趨勢(23)、全球物聯網科技(77)、華人世紀(24)、亞太成長(18)、亞太神龍科技(82)、中國新經濟A股(57)、大中華中小策略(29)
**全球平衡型**：全球平衡(12)、中國新經濟平衡(53)、亞太平衡(16)
**國內股票型**：復華復華(01)、高成長(03)、數位經濟(06)、中小精選(08)、全方位A(15)、全方位TISA(125)、台灣好收益(117)、台灣科技高股息A(122)、台灣科技高股息B(123)
**國內平衡型**：傳家(04)、傳家二號(07)、人生目標(11)、神盾(13)
**台灣智能**：台灣智能(79)（組合型；官網無十大持股表，成分見月報）

（括號內為 `fhtrust.com.tw/funds/funds_detail/{id}` 的 id；要增減基金只需改 `config/funds.json`。）

---

## 快速開始（零安裝，純標準庫 + certifi TLS）

```bash
# 1) 抓 25 檔基金的持股介紹（海外＋台股）→ data/funds/{id}.json
python3 scripts/fetch_holdings.py
python3 scripts/fetch_holdings.py 47 12        # 只抓指定 fundID

# 2) 產昨夜美股新聞「提示包」（兩版型規格已內建、自動帶今日/昨夜美股交易日）
python3 scripts/gen_usnews.py
#    → 產 reports/usnews/prompts/{date}.md
#    新聞內容需「會上網查證的 LLM」產出（純 Python 不杜撰新聞），兩條路擇一：
#      A) Claude Code：說「依此提示包上網查證，產 v1/v2 兩檔」→ 產 reports/usnews/{date}_v1.md、_v2.md
#      B) 貼進聯網的 Claude，回存兩檔
python3 scripts/gen_usnews.py --check          # 對最新產出跑禁用詞合規掃描

# 3) 產台股盤後重點「提示包」（單版型：指數速覽＋Top 3 盤後卡）
python3 scripts/gen_twnews.py
#    → 產 reports/twnews/prompts/{date}.md；同上由 LLM 查證產出 reports/twnews/{date}.md
python3 scripts/gen_twnews.py --check          # 合規掃描

# 4) 產儀表板（今日重點 + 總覽 + 新聞連動 + 台股/美股新聞 + 持股介紹）→ dashboard/index.html
python3 scripts/gen_fund_dashboard.py --open

# 或一次跑完（新聞內容步驟仍由 LLM 補）：
bash scripts/daily_fund.sh
```

**新聞內容：半自動・用訂閱額度（非計量 API）**。雲端 GitHub Actions 每日 07:00（台北）自動刷新
NAV／持股快照／提示包＋重建儀表板並部署；**新聞「內容」由會上網查證的 Claude（你的訂閱額度）** 依當日
提示包產出——每天早上請 Claude「依 `reports/usnews/prompts/{date}.md`、`reports/twnews/prompts/{date}.md`
上網查證，回存 `reports/usnews/{date}_v1|_v2.md` 與 `reports/twnews/{date}.md`」即可，補完儀表板會自動帶入
（未補當日新聞時退回最近一份、標合規燈）。

> 為何不放 CI 全自動？訂閱制 OAuth 權杖（`claude setup-token`）不適合無人值守的排程：官方
> `claude-code-action` 有已知標頭 bug、且權杖約一天過期。若日後要「新聞也全自動」，需改用**計量 API
> 金鑰** `ANTHROPIC_API_KEY`（每月約 US$10–30，依模型與查證次數）——這是唯一「設定一次、永遠自動」的路。

儀表板為**單一 `dashboard/index.html`**（vanilla JS、零外部請求、雙擊即開，無 npm/node），業務優先架構（見 `docs/REDESIGN_PLAN.md`）：🕒 資料更新時間（各資料來源鮮度一覽，台北時間）→ 今日重點 → 新聞（公司/產業面，逐則收合、事件屬性【新事件/延伸】＋重要度徽章、只留 ≥6 分依重要度排序）→ 🏛️ 總經・政策（川普政策/Fed/國際政策，全球共用不隨台股/全球切換）→ 當日焦點個股（新聞×持股連動）→ 基金總覽表（可排序、紅漲綠跌）→ 逐檔持股介紹。台股/全球以左上角切換；🟢/🔴 合規燈。

---

## 資料來源與正確性

| 資料 | 來源 | 端點 | 頻率 |
|---|---|---|---|
| 基本資料 / NAV / 多期報酬 / 經理人 / 月報 / 投資策略 | 復華投信官網 | `GET /api/fund?fundID={id}`（JSON） | 每日 NAV |
| 十大持有標的（含產業）/ 國家配置 / 產業配置 / 資料日期 | 復華投信官網 | `/funds/funds_detail/{id}`（SSR HTML／SVG 解析） | 月底 |
| 重點標的簡介 | 人工／查證後落檔 | `config/holding_profiles.json` | 靜態，可增修 |
| 昨夜美股新聞 | Reuters/Bloomberg/WSJ/FT/CNBC/富途牛牛等公開來源 | Claude（訂閱額度）依提示包上網查證 → `reports/usnews/{date}_v*.md` | 每日（半自動） |
| 台股盤前/盤後重點 | 中央社/經濟日報/鉅亨網等公開來源（指數以證交所/櫃買中心為準） | Claude（訂閱額度）依提示包上網查證 → `reports/twnews/{date}.md` | 每交易日（半自動） |
| 總經／政策面（川普政策/Fed/國際政策） | Reuters/Bloomberg/WSJ/FT＋官方（whitehouse.gov/federalreserve.gov） | Claude（訂閱額度）依提示包上網查證 → `reports/macronews/{date}.md` | 每日（半自動） |

持股為**月度**官方揭露（如 2026/05/31），NAV 為每日；儀表板皆標「持股基準日」與「NAV 日」以免混淆。連接器純標準庫正則解析（`arm/connectors/fhfund.py`），缺任一端點即該欄留空、不整批崩。

---

## 程式骨架（追蹤版本新增／核心）

```
config/funds.json              追蹤清單（id / name / group）— 單一事實來源
config/holding_profiles.json   重點標的簡介（中性事實敘述、非投資建議）
config/holding_aliases.json    持股別名表（新聞×持股連動比對用；新增持股時同步維護）
arm/connectors/fhfund.py       復華共同基金連接器（meta+NAV+報酬 / 十大持股 / 國家・產業配置）
arm/fund_intro.py              持股介紹組裝（掛簡介、摘要句、集中度、待抓取清單）
arm/fund_insights.py           跨基金洞察層（總覽表 / 最強最弱 / 同組平均 / 新聞連動引擎 / 話術）
arm/usnews.py                  昨夜美股：兩版型規格常數 + 產出讀取 + 禁用詞合規掃描 + 指數/新聞卡萃取（含事件屬性/重要度）
arm/twnews.py                  台股盤前/盤後重點：版型規格 + 產出讀取 + 加權/櫃買指數萃取
arm/macronews.py               總經／政策面（川普政策/Fed/國際政策）：版型規格 + 產出讀取
arm/fund_dashboard.py          零安裝儀表板（業務優先三層架構，SSR + 極簡 Markdown 渲染）
scripts/fetch_holdings.py      抓 25 檔持股介紹 → data/funds/{id}.json
scripts/gen_usnews.py          產昨夜美股提示包 / --check 合規掃描
scripts/gen_twnews.py          產台股盤前/盤後提示包 / --check 合規掃描
scripts/gen_macronews.py       產總經／政策面提示包 / --check 合規掃描
scripts/gen_fund_dashboard.py  產 dashboard/index.html
scripts/daily_fund.sh          每日 routine 單一進入點
tests/test_fund_tracker.py     新模組單測（fhfund 解析 / usnews / fund_intro）
tests/test_insights.py         洞察層/台股新聞/儀表板單測
```

`arm/http.py`（certifi TLS）、`arm/config.py`（設定載入）沿用。ETF 版遺留的行銷/籌碼/文案模組仍在庫中但非本版本主軸。

---

## 合規（重要）

- 本工具為**市場資訊彙編／教育用途，非投資建議或招攬**；對外發布前建議經法遵核可。
- 禁用詞（`arm/usnews.BANNED`，內建掃描）：保證／穩賺／唯一／建議買賣／目標價 等；機構觀點以「該機構表示／認為／估測（日期）」呈現；不預測報酬、不以過去績效推未來。
- 揭露：投資人申購本基金係持有基金受益憑證，非本文提及之投資資產或標的；過去績效不代表未來表現，淨值可能因市場變動而上下；境外基金涉及匯率與國際市場風險；申購前應詳閱公開說明書／投資人須知。
- 新聞若查無足量或無法查證，一律誠實加「資料侷限說明」，切勿杜撰標題、數字或引言。

---

## 測試

```bash
python3 -m pytest -q          # 全綠
```
