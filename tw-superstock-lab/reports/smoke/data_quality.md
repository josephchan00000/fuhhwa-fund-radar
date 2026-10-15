# 資料品質報告（Phase 1）

產生時間：2026-10-15 20:38（台北）　結論：**有條件通過（請看 WARN）**　FAIL 0／WARN 3／共 12 項

| 編號 | 檢查 | 結果 | 摘要 |
| --- | --- | --- | --- |
| C1 | 下載完成度 | WARN | 15 個資料集；停用 5 個 |
| C2 | 股票池 | PASS | 共 2225 檔（下市 248 檔）；疑似代號重複使用 0 個 |
| C3 | 價格完整性 | PASS | 11,916 列；重複 0、高<低 0、收盤超出高低範圍 0 |
| C4 | 未解釋的大漲跌（缺還原事件？） | PASS | 0 筆（占 0.0000%） |
| C5 | 交易日對齊 | PASS | 非交易日資料 0 列；資料稀少的交易日 0 天；整天缺資料 0 天 |
| C6 | 長期缺漏（停牌或資料缺） | PASS | 0 段超過 30 天的空白（0 檔） |
| C7 | 還原事件 | PASS | 111 個事件；純現金股利一致性檢查 53 筆、不一致 0 筆 |
| C8 | 自算還原價 vs FinMind 還原價 | PASS | 沒有下載 FinMind 還原價（extended 群組），略過 |
| C9 | 月營收 | WARN | 3 檔（覆蓋 0.1%）；最新 2026-09；區間內缺 0 個月 |
| C10 | 綜合損益表 | PASS | 3 檔；非季底日期 0 列；有 EPS 欄位 |
| C11 | 籌碼資料覆蓋 | WARN | 三大法人覆蓋 0.1%、融資融券覆蓋 0.1%（部分股票不能信用交易屬正常） |
| C12 | 掛牌前（興櫃）與下市後日 K | PASS | 1 檔切掉興櫃前段共 225 筆；0 檔切掉下市後 0 筆；疑似漏判 0 檔 |

## C1 下載完成度：WARN

15 個資料集；停用 5 個

```json
{
  "datasets": [
    {
      "dataset": "IndexPrice",
      "done": 2,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockCapitalReductionReferencePrice",
      "done": 0,
      "empty": 3,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockDelisting",
      "done": 1,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockDispositionSecuritiesPeriod",
      "done": 0,
      "empty": 0,
      "failed": 3,
      "failed_pct": 100.0
    },
    {
      "dataset": "TaiwanStockDividendResult",
      "done": 3,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockFinancialStatements",
      "done": 3,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockInfo",
      "done": 1,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockInstitutionalInvestorsBuySell",
      "done": 3,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockMarginPurchaseShortSale",
      "done": 3,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockMonthRevenue",
      "done": 3,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockParValueChange",
      "done": 6,
      "empty": 13,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockPrice",
      "done": 3,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockSplitPrice",
      "done": 7,
      "empty": 12,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockTotalReturnIndex",
      "done": 2,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    },
    {
      "dataset": "TaiwanStockTradingDate",
      "done": 1,
      "empty": 0,
      "failed": 0,
      "failed_pct": 0.0
    }
  ],
  "disabled": [
    {
      "dataset": "TaiwanStockCapitalReductionReferencePrice",
      "reason": NaN
    },
    {
      "dataset": "TaiwanStockDispositionSecuritiesPeriod",
      "reason": "連續 3 檔失敗，可能需付費或參數不符：TaiwanStockDispositionSecuritiesPeriod 6488: HTTP 400 Your level is free. Please update your user level. Detail information:https://finmindtrade.com/analysis/#/Sponsor/sponsor"
    },
    {
      "dataset": "TaiwanStockDividendResult",
      "reason": NaN
    },
    {
      "dataset": "TaiwanStockParValueChange",
      "reason": NaN
    },
    {
      "dataset": "TaiwanStockSplitPrice",
      "reason": NaN
    }
  ]
}
```

## C2 股票池：PASS

共 2225 檔（下市 248 檔）；疑似代號重複使用 0 個

```json
{
  "total": 2225,
  "by_market": {
    "twse": 1214,
    "tpex": 930,
    "unknown": 81
  },
  "delisted": 248,
  "reused_codes": []
}
```

## C3 價格完整性：PASS

11,916 列；重複 0、高<低 0、收盤超出高低範圍 0

```json
{
  "rows": 11916,
  "stocks": 3,
  "first_date": "2008-01-02",
  "last_date": "2026-10-15",
  "duplicates": 0,
  "high_below_low": 0,
  "close_outside_range": 0,
  "zero_volume_share": 0.0
}
```

## C4 未解釋的大漲跌（缺還原事件？）：PASS

0 筆（占 0.0000%）

```json
{
  "count": 0,
  "share": 0.0,
  "stocks": 0
}
```

## C5 交易日對齊：PASS

非交易日資料 0 列；資料稀少的交易日 0 天；整天缺資料 0 天

```json
{
  "rows_not_in_calendar": 0,
  "thin_days": 0,
  "calendar_days_without_prices": 0
}
```

## C6 長期缺漏（停牌或資料缺）：PASS

0 段超過 30 天的空白（0 檔）

```json
{
  "gaps": 0,
  "stocks": 0
}
```

## C7 還原事件：PASS

111 個事件；純現金股利一致性檢查 53 筆、不一致 0 筆

```json
{
  "events": 111,
  "by_source": {
    "TaiwanStockDividendResult": 78,
    "TaiwanStockSplitPrice": 17,
    "TaiwanStockParValueChange+TaiwanStockSplitPrice": 16
  },
  "factor_quantiles": {
    "0.01": 0.01,
    "0.5": 0.9678,
    "0.99": 5.8956
  },
  "cash_dividend_checked": 53,
  "cash_dividend_mismatch": 0
}
```

## C8 自算還原價 vs FinMind 還原價：PASS

沒有下載 FinMind 還原價（extended 群組），略過

## C9 月營收：WARN

3 檔（覆蓋 0.1%）；最新 2026-09；區間內缺 0 個月

```json
{
  "rows": 597,
  "stocks": 3,
  "coverage": 0.0013,
  "latest_period": "2026-09-01",
  "duplicates": 0,
  "negative": 0,
  "missing_months_inside_range": 0
}
```

## C10 綜合損益表：PASS

3 檔；非季底日期 0 列；有 EPS 欄位

```json
{
  "rows": 3452,
  "stocks": 3,
  "non_quarter_end_rows": 0,
  "has_EPS": true,
  "top_types": {
    "EPS": 196,
    "TAX": 196,
    "CostOfGoodsSold": 196,
    "Revenue": 196,
    "GrossProfit": 196,
    "OperatingIncome": 196,
    "OperatingExpenses": 196,
    "IncomeFromContinuingOperations": 196,
    "OtherComprehensiveIncome": 156,
    "IncomeAfterTaxes": 156,
    "TotalConsolidatedProfitForThePeriod": 156,
    "EquityAttributableToOwnersOfParent": 156,
    "TotalNonoperatingIncomeAndExpense": 156,
    "PreTaxIncome": 156,
    "NoncontrollingInterests": 145
  }
}
```

## C11 籌碼資料覆蓋：WARN

三大法人覆蓋 0.1%、融資融券覆蓋 0.1%（部分股票不能信用交易屬正常）

```json
{
  "institutional_coverage": 0.0013,
  "margin_coverage": 0.0013,
  "institutional_first": "2012-05-02"
}
```

## C12 掛牌前（興櫃）與下市後日 K：PASS

1 檔切掉興櫃前段共 225 筆；0 檔切掉下市後 0 筆；疑似漏判 0 檔

```json
{
  "stocks": 3,
  "with_emerging_prefix": 1,
  "rows_dropped_pre": 225,
  "with_rows_after_delisting": 0,
  "rows_dropped_post": 0,
  "suspect_not_switched": 0
}
```
