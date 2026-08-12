# 新增基金 SOP —— 把一檔復華基金完整接進「基金雷達」

> **用途**：之後要加基金，照本文由上而下做一遍即可，不需要重新研究程式碼。
> 全部做完＝新基金與既有邏輯**全部**結合：總覽表、詳情卡、NAV 1週/1月自算、
> 鉅亨每日多期報酬、基金新聞關聯、持股簡介、群組平均、篩選 chip、鮮度警示。
>
> **實例**：2026-08-12 依本文加入 `27` 復華全球原物料基金（global_equity）與
> `22` 復華奧林匹克全球優勢組合基金-新臺幣A（global_fof，本 repo 首檔全球組合型）。
>
> **設計原則（為什麼只要改這麼少）**：`config/funds.json` 是唯一事實來源；
> 抓取（CI）、索引順序、儀表板分組、新聞關聯、NAV 序列全部**吃這份清單自動跟上**。
> 只有「顯示標籤」（新分組時）與「外部對照」（鉅亨 cnyesId）需要人手補。

---

## 流程總覽（30 秒版）

| # | 動作 | 檔案 | 何時需要 |
|---|------|------|----------|
| 1 | WebSearch 查證 id／全名／cnyesId | —（查證） | **每次** |
| 2 | 加追蹤條目 | `config/funds.json` | **每次** |
| 3 | 釘鉅亨 cnyesId | `data/cnyes_fund_map.json` | **每次** |
| 4 | 新分組標籤 | `arm/fund_intro.py` `GROUP_LABEL` | 僅新 group |
| 5 | 更新追蹤清單 | `README.md` | **每次** |
| 6 | 本地驗證 | pytest＋重建儀表板看 ⏳ 卡 | **每次** |
| 7 | commit → push → **merge 進 main** | — | **每次**（config 不會自動併，見 §7） |
| 8 | 觸發／等待 CI 抓真實資料 | `daily.yml` | **每次** |
| 9 | 入庫後驗證＋補持股簡介 | `config/holding_profiles.json` | 快照入 main 後 |

---

## 1. 事前查證（每筆資料兩來源一致才寫；查不到就留空、不猜）

要查三件事：

1. **復華官網 fundID**：搜 `復華〇〇基金 fhtrust funds_detail`。
   官網詳情頁 `https://www.fhtrust.com.tw/funds/funds_detail/{id}` 的 `{id}` 就是它
   （同站 `fund_intro_brief.aspx?QueryFund={id}` 的 id 相同，可互為佐證）。
2. **官網正式全名**：以官網頁面標題為準，**含幣別／類別尾綴**（如「-新臺幣A」）。
   config 名稱與官網 `/api/fund` 回傳名不符（正規化後互為前綴也不算）時，
   `fetch_holdings.py` 的 `_name_matches` 防呆會**整檔跳過不落檔**——這是擋
   「fundID 推錯、抓成別檔」用的，名稱寫對就不會踩。
3. **鉅亨 cnyesId**：搜 `fund.cnyes.com 復華〇〇基金`。詳情頁 URL 尾段即是
   （`fund.cnyes.com/detail/{中文名}/{cnyesId}/`，舊基金多為 `A23xxx`、新基金為
   `A3Q…` 之類亂碼型）。**編號與官網 fundID 沒有換算公式，一定要逐檔查**。

注意事項：

- **每個級別＝獨立一檔**：新臺幣A／新臺幣B／美元／TISA 各有自己的 fundID 與
  cnyesId（例：奧林匹克全球優勢 新臺幣A=22/A23021、新臺幣B=80/A3QIEAC）。
  使用者沒指明時預設收**新臺幣（A）**；要多收級別就各加一條。
- 本 repo 慣例只追蹤新臺幣級別（美元級別一律不收）。
- 本 Claude 容器 proxy 擋 fhtrust／cnyes 原頁——**用 WebSearch 的結果摘要查證即可**，
  不要嘗試 WebFetch 原頁。

## 2. `config/funds.json` —— 加追蹤條目（單一事實來源）

```json
{
 "id": "27",
 "name": "復華全球原物料基金",
 "group": "global_equity"
}
```

- **id**：字串（保留前導零，如 `"01"`）。
- **name**：官網正式全名（見 §1；`fetch_holdings.py` 會以 API 回傳覆寫成權威值，
  但這裡要寫到「互為前綴」程度，否則被防呆擋下）。
- **group** 現有枚舉（決定分組與視圖，`_note` 內也有一份）：

  | group | 顯示標籤 | 視圖 |
  |-------|---------|------|
  | `global_equity` | 全球股票型 | 全球 |
  | `global_balanced` | 全球平衡型 | 全球 |
  | `global_fof` | 全球組合型 | 全球 |
  | `tw_equity` | 國內股票型 | 台股 |
  | `tw_balanced` | 國內平衡型 | 台股 |
  | `tw_fof` | 台灣智能（組合型） | 台股 |

  兩條機制規則（改壞會出現在錯的視圖／錯的訊息）：
  - **視圖切分**＝`group` 是否以 `tw` 開頭（`fund_dashboard._mof()`）：
    `tw*`→台股視圖，其餘→全球視圖。**新 group 命名不要讓台股基金不以 tw 開頭**。
  - **組合型一律以 `_fof` 結尾**：儀表板兩處 FOF 特殊處理（詳情卡「官網不揭露
    十大持有標的」說明、待抓取卡註記）認 `group.endswith("_fof")`。
- **檔內順序＝儀表板顯示順序**（總覽各分組內的列序、詳情卡序、分組出現順序都
  跟第一次出現的位置走）。慣例：插在**同 group 既有條目的最後一筆之後**。

## 3. `data/cnyes_fund_map.json` —— 釘鉅亨 cnyesId

```json
"27": {
 "cnyesId": "A23026",
 "name": "復華全球原物料基金"
}
```

- 這層是「**每日基準**多期報酬」的來源（官網 `/api/fund` 的 YTD/1y 是**月底基準**，
  十幾天不動）。**忘了釘的後果**：鉅亨連接器退回搜尋頁名稱比對——實測必零命中
  （搜尋頁 SSR 不吃 query），該檔多期報酬長期停在官網月底值。儀表板不會壞，
  但總覽「報酬欄＝鉅亨每日基準」對這檔不成立。
- 鍵＝官網 fundID（字串）；檔內鍵序照字串排序插入即可（純為可讀性，程式不依賴）。

## 4. 新分組才要做：`arm/fund_intro.py` 的 `GROUP_LABEL`

```python
GROUP_LABEL = {..., "global_fof": "全球組合型", ...}
```

- 沿用既有 group 的話**跳過本節**。
- 漏加的症狀：該檔在「待抓取」狀態沒有分組標籤——
  `tests/test_insights.py::test_pending_funds_have_group_label` 會直接紅，跑 §6 就會抓到。
- 標籤命名要讓詳情區篩選 chip 對得上：chip 靠 `group_label` **包含**「股票」／「平衡」／
  「組合」字樣篩選（`data-g` includes 比對），新標籤取名時帶上對應字。
- 已抓到快照的基金若 group 打錯字，標籤會回退成官網 `category` 文字——看到分組
  標籤變成「跨國投資股票型」這種官網原文＝group 拼錯了。

## 5. `README.md` —— 追蹤清單同步

「追蹤清單（N 檔）」：總數 +1、把新檔以「短名(id)」補進對應分組行。
（歷史教訓：2026-07 加了 4 檔指數基金沒更新 README，數量一路錯到 08-12 才修。）

## 6. 本地驗證（容器內可完成的部分）

```bash
pip install -q pytest          # 容器預設沒有
python3 -m pytest -q           # 必須全綠
TZ=Asia/Taipei python3 scripts/gen_fund_dashboard.py
```

- 重建後打開／grep `dashboard/index.html`：新基金應以「**⏳ 數據待抓取**」出現在
  正確視圖的正確分組（總覽表尾＋詳情 pending 卡）；組合型 pending 卡另有
  「官網揭露結構不同」註記。這是 §2–4 全部接對的證明。
- **驗完務必丟棄本地重建**（同每日 SOP 步驟 4 的理由——本地版帶舊快照，絕不 commit）：

  ```bash
  git checkout -- dashboard/index.html
  ```

- ⚠ **不要在容器跑 `fetch_holdings.py`**：proxy 擋 fhtrust，31 檔全 403 純空轉。
  抓取一律交給正式區 CI（§8）。

## 7. commit → push → **merge 進 main**（新增基金唯一的人工 merge 點）

```bash
git add config/funds.json data/cnyes_fund_map.json arm/fund_intro.py README.md
git commit -m "feat: 新增追蹤基金 〇〇(id)"
git push -u origin <本次會話分支>
```

- ⚠ **與每日新聞流程的關鍵差異**：`daily.yml` 只自動併入分支上的
  `reports/*.md` 與 `data/etf_upcoming.json`；**config／程式碼一律不自動併**
  （防注入設計）。所以新增基金**必須把分支 merge 進 main** 才會生效——
  開 PR 合併（repo 慣例）或請使用者按下 merge。
- merge 前 push 分支雖會觸發 daily.yml（若同分支動過 reports/**），但那輪 CI
  checkout 的是 **main**，讀不到新 config——**不要以為 push 完就會開始抓新基金**。

## 8. merge 後：讓 CI 抓第一份真實資料

任一條即可（不動手也會自癒，只是慢）：

- **主動**：`mcp__github__actions_run_trigger`（method=run_workflow、
  workflow_id=`daily.yml`、ref=`main`、`news_ref` 留空＝只用 main 現有新聞重刷資料）。
- **被動**：等下一班排程（06:35 Routine／07:15 cron；18:58 晚間 NAV Routine 的
  afterhours 班次也會抓基金 NAV，但**持股快照與鉅亨覆蓋以 daily.yml 為準**）。

CI 端全自動發生的事（不需人工）：`data/funds/{id}.json`＋`_index.json` 建檔、
`fund_nav_history.json` 官方 NAV 史**自動回填近 90 天**（`fundnav.backfill_official`，
1週/1月報酬立刻可算）、鉅亨每日報酬覆蓋（`returns_daily`）、基金新聞關聯查詢
自動納入新檔。

## 9. 入庫後驗證＋補持股簡介（完成定義）

```bash
git fetch origin main
git show origin/main:data/funds/_index.json | python3 -c "import json,sys; d=json.load(sys.stdin); print([f for f in d['funds'] if f['id'] in ('22','27')])"
git show origin/main:data/holdings_intro_gap.json
```

驗收清單：

1. `_index.json` 有新檔且 `nav`／`nav_date` 非空（NAV 常見 T+1，日期到昨日屬正常）。
2. `data/funds/{id}.json` 存在；股票／平衡型應有 `top_holdings`（月度基準，顯示上月底）；
   **組合型 `top_holdings=[]` 是正常**，不是抓失敗。
3. `data/fund_nav_history.json` 有該 id 序列（跨度 ≥35 天，1月報酬才算得出；
   回填首日就該滿足）。
4. **`holdings_intro_gap.json` 的 `count` 必須歸 0**：新檔前十大帶進新標的時，
   count>0＋儀表板紅章＋`tests/test_holdings_intro.py` 紅。處置＝WebSearch 查證後把
   缺的標的補進 `config/holding_profiles.json`（`profiles` 下
   `{持股原字串: {intro, ticker, country, verified}}`；**key＝快照內 `top_holdings[].name`
   原字串**（含 `*` 等後綴）；intro 純事實、非投資建議、避開禁用詞）→ 重推 → merge。
5. 總覽表出現實際數字（不再 ⏳）；「1月」欄若顯示 — 且序列跨度不足，等史料自然補齊，
   不是壞掉。

## 10. 常見坑速查

| 症狀 | 根因 | 修法 |
|------|------|------|
| CI 日誌「官網名稱與 config 名稱不符…跳過不落檔」 | fundID 錯置或名稱寫錯 | 回 §1 重查，修 `funds.json` |
| 多期報酬長期停在月底值 | cnyesId 沒釘 | 補 §3 |
| pending 卡沒有分組標籤／pytest `test_pending_funds_have_group_label` 紅 | 新 group 沒加 `GROUP_LABEL` | 補 §4 |
| 台股基金跑到全球視圖（或反之） | group 前綴不對（`tw` 開頭＝台股） | 修 §2 group |
| 組合型顯示「十大持有標的暫無資料」而非 FOF 說明 | group 沒以 `_fof` 結尾 | 修 §2 group |
| 分組標籤顯示成官網 category 原文 | group 拼錯（查無標籤回退） | 修 §2／§4 |
| push 完 CI 跑了但沒抓新基金 | 分支 config 未 merge 進 main（§7） | merge 後再觸發 §8 |
| 儀表板紅章「N 檔缺簡介」 | 新檔前十大有新標的 | 補 §9-4 |
| 新基金 1月報酬 — | NAV 史跨度 <35 天且回填失敗 | 查 CI 日誌 `官方淨值史回填`；必要時 `scripts/backfill_fund_nav.py` |

## 11. 移除基金（順帶備忘）

從 `config/funds.json` 刪條目即可：儀表板、新聞關聯、抓取立即跟上。
`data/funds/{id}.json` 與 `_index.json` 內的舊條目會保留（`_write_index` 對移出
清單者不清檔）——要完全下架就一併刪快照檔；`cnyes_fund_map.json` 條目留著無害。

---

*本文由 2026-08-12「新增全球原物料＋奧林匹克全球優勢組合」會話建立；
機制變更（分組規則、抓取管線、防呆）時請同步更新本文與 `CLAUDE.md`。*
