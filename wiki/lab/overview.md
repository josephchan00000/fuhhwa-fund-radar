# 籌碼雷達總覽

> 入口、x9.html 兩種身分、模組、建頁、workflow 要裝 numpy。
> 原始資料：CLAUDE.md「籌碼雷達」段開頭；程式：`arm/lab/`
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

- **入口**＝主頁頁尾右下角淡色小點，連 `x9m.html`；**不進導覽列、不在任何分頁出現**（tests/test_lab.py 守）。
- **頂欄**兩格（`arm/lab/appnav.py`，不做窄欄，見[導覽與入口](nav.md)）：市場（台股 x9m.html、美股 x9mu.html）＋選股（x9.html），右邊小字「研究紀錄・名詞・查公司」。
  泡沫 x9b.html、訊號總覽 x9o.html、大神策略 x9x.html 是轉址頁（見[市場頁](market-page.md)）。
- **x9.html 一頁兩種身分**：選股（台股｜美股｜個股）與研究紀錄（個股策略｜總經策略｜交易計畫｜全部策略｜後台，從 x9r.html 進來），
  見[選股頁](pick-page.md)、[配置頁與研究紀錄](cfg-research.md)。頁面＝`dashboard/x9.html`（Vercel cleanUrls → `/x9`）。
- 範圍：券商分點暫不做（使用者：先不做）；海外持股只做 ETF 面；債券型 ETF 整檔排除。
- **模組（`arm/lab/`）**：store（日分片 gzip、決定性輸出）／market（官方全市場端點）／collect（冪等落檔）／ledger（ETF 部位帳本）／
  ta（技術指標）／analyze（逐檔彙整＋訊號）／backtest（成績單）／page（獨立頁）。
- **建頁**掛在 `scripts/gen_fund_dashboard.py` 尾端（fail-open），凡重建主頁的地方（含 push 重試迴圈）都一起重建。
  三支 workflow 的 `git add` 都有 `data/lab dashboard/x9.html`；`dashboard/x9s.json` 另起一行（缺檔時 git 整行放棄，不可連累分片；tests 守）。
- **三支都要裝 numpy**（策略判定、景氣頁、訊號總覽要它；`tests/test_lab.py::test_workflows_that_build_pages_install_numpy` 守）。

## 不能改的規則

- 入口刻意低調，**不用密語、不加密**（2026-10-14 使用者：「入口……不想要太容易被看到」「不用那麼搞剛，就沒那麼好找到就好了」）。

## 踩過的坑

- **2026-10-21 前 `etf_holdings.yml` 只裝 certifi**：每班建頁都把機會頁的策略判定洗成「次數不夠」（推薦全空），等下一班 daily／afterhours 重建才回來（10/19～10/21 合計約 2 小時）。

## 歷史

- 2026-10-14：使用者需求「把所有 ETF 持有的個股去做分析……從量、成本、加入時間、哪間看好……實務操作可以拿來賺錢的深度籌碼跟技術分析」。
- 2026-10-18：小點改連 `x9m.html`（當時叫台股景氣頁，2026-10-23 起叫市場頁；使用者：「點那個 . 之後先出現景氣頁面，個股頁面放旁邊」）。
- 2026-10-23：頂欄改成兩格；2026-10-28：「配置」改叫選股。
