# 訊號計算核對與參數鄰近

> 訊號算得對不對（第二套算法、截斷重建、資料來源比對、手算案例、每週核對）與參數會不會只是剛好（參數鄰近檢查）；EMA 與頁面是後面的段落。
> 原始資料：規劃 `docs/lab_signal_quality_plan.md`；程式：`arm/lab/sigverify.py`、`arm/lab/truncheck.py`、`arm/lab/srccheck.py`、`arm/lab/nbrspec.py`、`arm/lab/sigrobust.py`
> 最後更新：2026-11-01（C 段）

## 現在怎麼運作

### 計算核對（A 段，2026-10-31）

- 第二套算法 `arm/lab/sigverify.py`（不呼叫網頁用的函式）、截斷重建 `arm/lab/truncheck.py`（原始資料截到某天，整條重算 0～100、邊際變化、訊號）、
  資料來源比對 `arm/lab/srccheck.py`，由 `scripts/run_verify.py` 一起跑 → `data/lab/verify_status.json`；手算固定案例 `tests/test_golden.py`。
- 每週六 13:17 `verify.yml`（main 上）先更新官方公布日表再核對；不一致標紅、推播、不擋發佈——見[籌碼雷達介面](chip-ui.md)「每週計算核對」。
- 月／季資料照官方實際公布日（`arm/lab/reldates.py`）——見[台股景氣頁](heat-tw.md)、[美股景氣頁](heat-us.md)。

### 參數鄰近檢查（B 段，2026-11-01；還沒接上頁面）

- 規格 `arm/lab/nbrspec.py`（VER 1，`tests/test_nbrspec.py` 鎖住）；程式 `arm/lab/sigrobust.py`；研究檔 `data/lab/robust_research.json`＝
  `TZ=Asia/Taipei python3 scripts/run_robust.py`（約 6 分鐘，只讀落檔；跟著 `run_sig.py` 重跑）。
- 每一組過列出門檻的（訊號, 方向, 看多久）一次動一個參數、往上往下各一個值；次數 ≥ 5 的鄰近至少一半也比平常高 5 點＝那個參數穩定；
  全部參數穩定＝穩定，有一個不穩定＝只在這個參數成立，一個都算不出來＝看不出來。
- 鄰近一律用正式程式重算：暫時換規格常數（`sigrobust.patched`；百分位比較期間 `sigrobust.windows`）；技術事件的參數是 heattech 函式的預設值，
  換常數沒有用，另外明寫傳參（`sigrobust.tech_events`）。
- 原本參數重算要和 `data/lab/sig_research.json` 一模一樣（`sigrobust.selfcheck`＋每一組的次數、命中率、平常），不一樣就停、不出結果。
- 2026-11-01：2,794 組穩定 74%；自營商連續 10 天賣超穩定，三大法人連續 10 天賣超只在這個參數成立。使用者的決定 D2 a（不穩定的不列）第 D 段才接上頁面。

### EMA 賣壓與天數衰減（C 段，2026-11-01；都沒有比現在好，照規則不換）

- EMA 賣壓：規格 `arm/lab/emaspec.py`（VER 1），程式 `arm/lab/sigema.py`，研究檔 `data/lab/ema_research.json`＝`scripts/run_ema.py`（約 1 分鐘）。
  法人買賣超與成交金額各做指數平均（天數 5、20、60，和現在的合計平均落後天數一樣）；逐年用那時的成績比列出來之後準不準（sigoos.walk 的紀錄），
  和合計、連續買賣超都差不多（區間碰到 0）。三種法人訊號列出來之後的下一年平均都沒有比平常好。
- 天數衰減：規格 `arm/lab/decayspec.py`（VER 1），程式 `arm/lab/sigdecay.py`，研究檔 `data/lab/decay_research.json`＝`scripts/run_decay.py`（約 6 分鐘）。
  自己的成績 × 0.5^(第幾天 ÷ 半衰期)，半衰期同一類一起估；和第 26 版的格子比（同 thermocal.compare），列得多 44% 但平均準度低 0.5 點，維持格子。
- 第 26 版（`claude/signal-listing` 第一、二段）已併進這個分支；`sigverify.check_thermo` 改和 thermocal 另存的 VER 25 票比，
  第 26 版的格子與新票的第二套算法第 D 段上線前補。

## 不能改的規則

- 規格先寫、commit 才算結果；原本的參數永遠不換、不挑鄰近裡最好的（使用者 2026-10-31：「為什麼選10天而不是11，12結果發現只是剛好10天的時候運氣好過度耦合的現象」）。
- 核對不一致只標紅、推播，不擋發佈（使用者決定 D4）。

## 歷史

- 2026-10-31 A 段（A-1～A-3）；2026-11-01 B 段。順序（使用者決定 D1）：先正確性、再參數鄰近與 EMA、最後頁面（第 D 段），之後整理程式（ponytail）。
