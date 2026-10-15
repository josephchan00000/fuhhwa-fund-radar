# 資料品質報告（Phase 1）

產生時間：2026-10-15 20:15（台北）　結論：**有條件通過（請看 WARN）**　FAIL 0／WARN 5／共 11 項

| 編號 | 檢查 | 結果 | 摘要 |
| --- | --- | --- | --- |
| C1 | 下載完成度 | WARN | 15 個資料集；停用 5 個 |
| C2 | 股票池 | WARN | 共 2225 檔（下市 81 檔）；疑似代號重複使用 238 個 |
| C3 | 價格完整性 | PASS | 12,140 列；重複 0、高<低 0、收盤超出高低範圍 0 |
| C4 | 未解釋的大漲跌（缺還原事件？） | WARN | 3 筆（占 0.0247%） |
| C5 | 交易日對齊 | PASS | 非交易日資料 0 列；資料稀少的交易日 0 天；整天缺資料 0 天 |
| C6 | 長期缺漏（停牌或資料缺） | PASS | 0 段超過 30 天的空白（0 檔） |
| C7 | 還原事件 | PASS | 111 個事件；純現金股利一致性檢查 53 筆、不一致 0 筆 |
| C8 | 自算還原價 vs FinMind 還原價 | PASS | 沒有下載 FinMind 還原價（extended 群組），略過 |
| C9 | 月營收 | WARN | 3 檔（覆蓋 0.1%）；最新 2026-09；區間內缺 0 個月 |
| C10 | 綜合損益表 | PASS | 3 檔；非季底日期 0 列；有 EPS 欄位 |
| C11 | 籌碼資料覆蓋 | WARN | 三大法人覆蓋 0.1%、融資融券覆蓋 0.1%（部分股票不能信用交易屬正常） |

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

## C2 股票池：WARN

共 2225 檔（下市 81 檔）；疑似代號重複使用 238 個

```json
{
  "total": 2225,
  "by_market": {
    "twse": 1214,
    "tpex": 930,
    "unknown": 81
  },
  "delisted": 81,
  "reused_codes": [
    "0054",
    "0058",
    "0059",
    "0060",
    "00649",
    "00658L",
    "00659R",
    "00667",
    "00672L",
    "00677U",
    "00691R",
    "00698L",
    "00699R",
    "00704L",
    "00705R",
    "00716R",
    "00718B",
    "00721B",
    "00729R",
    "00732",
    "00742",
    "00743",
    "00744B",
    "00745B",
    "00747B",
    "00748B",
    "00765B",
    "00766L",
    "00767",
    "00774B",
    "00774C",
    "00776",
    "00784B",
    "00790B",
    "00794B",
    "00796B",
    "00798B",
    "0080",
    "0081",
    "008201",
    "00831B",
    "00832B",
    "00833B",
    "00835B",
    "00837B",
    "00838B",
    "00839B",
    "00843B",
    "00854B",
    "00855B"
  ]
}
```

## C3 價格完整性：PASS

12,140 列；重複 0、高<低 0、收盤超出高低範圍 0

```json
{
  "rows": 12140,
  "stocks": 3,
  "first_date": "2008-01-02",
  "last_date": "2026-10-15",
  "duplicates": 0,
  "high_below_low": 0,
  "close_outside_range": 0,
  "zero_volume_share": 0.0
}
```

## C4 未解釋的大漲跌（缺還原事件？）：WARN

3 筆（占 0.0247%）

```json
{
  "count": 3,
  "share": 0.000247,
  "stocks": 1
}
```

範例（最多 20 筆）：

```json
[
  {
    "stock_id": "6488",
    "date": "2015-02-02",
    "ret": 0.1086
  },
  {
    "stock_id": "6488",
    "date": "2014-11-24",
    "ret": 0.0863
  },
  {
    "stock_id": "6488",
    "date": "2014-12-15",
    "ret": 0.0823
  }
]
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
