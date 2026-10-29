# 資料包策略測試與回測紀律

> P1～P6、存活者偏誤、成本加倍與參數鄰近、成交檢查、效能。
> 原始資料：CLAUDE.md「籌碼雷達」段的資料包策略測試與回測紀律；規劃 `docs/strategy_pack_plan.md`；程式：`arm/lab/packtest.py`
> 最後更新：2026-10-29
> 第 5 段瘦身之前 CLAUDE.md 仍是正本：那幾段改了，這一頁也要跟著改（`python3 scripts/wiki_facts.py` 會檢查）。

## 現在怎麼運作

2026-10-15 使用者附上策略資料包：「把能用的拿來用就好」。能用＝現有資料能回測。

- **新策略五條**（`arm/lab/packtest.py`，主規格回測前寫定並先 commit，`tests/test_lab.py::test_pack_main_specs_are_fixed` 守）：P1 相對強勢月換股（S11）、P2 趨勢樣板＋突破（S09 Minervini）、
  P3 財報驚喜 SUE（S10，法定公告期限次一交易日進場）、P4 價值＋動能（S16）、P5 短期反轉週換股（S13）；P6＝CAN SLIM 的 C／M 加在長線策略上當對照（`growth.s5_trades` 的 `alt`，S5 規則不變）。
  結果全部 C（P2 平均 +2.3% 但 74% 輸大盤、去掉最好一筆轉負；P3 對同一批股票 +3.0% 但只贏加權 +0.6%），只放在策略頁「資料包策略測試」表，不進本期操作。
- **存活者偏誤**：Yahoo 五年宇宙是「目前市值前約 600 名」。形成日另要求市值 ≥300 億（只漏掉之後跌超過三分之二的），並對「同一批股票的等權平均」算 xe；
  `advice.score(..., xe_rule=True)`（S5、P1–P5）平均沒贏同一批股票 → C。
- **回測紀律（全部策略）**：`advice.robust()` 算成本加倍、去掉最好一筆、最大累計回落、最長連虧、大盤年線上／下（`packtest.regime_map`，五年日線算 200 日均線）；
  參數鄰近＝主規格兩個參數各 ±1 檔共 9 組（`packtest.grid`；S1 持有天數×ATR、臺灣50 提前天數×檔數 `tw50study.early_grid`、S5 初始停損×回落、P1–P5 各自）。
  **評級加嚴**：A 另需成本加倍後 >0 且鄰近 9 組 ≥6 組為正；鄰近不到一半為正 → C。套用後現有評級都沒變（S1、臺灣50 鄰近 9／9、成本加倍仍正）。
- **成交檢查（D1）**：`backtest.limit_up_open`（開盤 ≥ 前收 × 1.095）／`locked_down`（開＝高＝低＝收且 ≤ 前收 × 0.905）／`exit_day`（鎖跌停順延賣出）。
  臺灣50 漲停開盤順延進場最多 3 天；S1、S5、P2、P1–P5 出場遇鎖跌停順延。歷史上 S1／S5／臺灣50 都是 0 筆。
- **效能**：`analyze.run` 只載一次 `Data(long=True)`，`hdpre.page_data(D=DL)`、v3 策略、公司分析小表、大盤年線共用；`packtest.Px` 快取合格名單（`elig`）與區間報酬（`_win`），參數鄰近重跑不重算。
  P1–P7 的 `packtest.run` 2026-10-16 起不在每次建頁重跑（頁面只用長線 P6 對照列與 `SKIPPED`，P1–P7 列本來就被 `bt3Sec` 濾掉，每次白算約 17 秒）；
  成績留在 docs/strategy_pack_plan.md，要重看手動跑 `packtest.summary(packtest.run(Data(long=True)), reg)`。
- **頁面**：各策略「歷史績效」下的「穩健度檢查」（`robTbl`，✓／✗ 三項＝A 級條件，可展開 9 組參數表）＋「樣本內比較過的做法」（`tried` 欄，STRATEGIES／TW50_VERS／S5／hdflow.ALERT）；
  風控段「總部位」（`totPos`）。沒採用的項目與原因在 `packtest.SKIPPED`（不放目標價類內容）。

## 踩過的坑

- **2026-07 動能股崩跌是真實行情**（華新科、中探針、禾伸堂等月跌 40～60%、連續跌停）：P1 那個月輸大盤 28%，別當成資料錯誤去修。

## 歷史

- 2026-10-15：原 `packSec()`（`st-pack`，5 年資料、對加權指數）由[回測方法 v3](backtest-v3.md) 的全部策略總表 `bt3Sec()`（`st-bt3`）取代。
