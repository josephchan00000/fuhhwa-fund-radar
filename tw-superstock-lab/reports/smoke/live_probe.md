# FinMind 實測（SPEC §3.7）

產生時間：2026-10-15 20:38（台北）　token：無（每小時 300 次）　本次請求 5 次

| 資料集 | 群組 | 方式 | 結果 | 筆數 | 日期範圍 | 欄位 |
| --- | --- | --- | --- | --- | --- | --- |
| TaiwanStockInfo | meta | global | 有資料 | 4339 | 2020-06-03～2026-10-15 | industry_category, stock_id, stock_name, type, date |
| TaiwanStockDelisting | meta | global | 有資料 | 726 | 1995-09-23～2026-10-01 | date, stock_id, stock_name |
| TaiwanStockTradingDate | meta | global | 有資料 | 4613 | 2008-01-02～2026-10-15 | date |
| IndexPrice | meta | per_index | 有資料 | 9226 | 2008-01-02～2026-10-15 | date, stock_id, Trading_Volume, Trading_money, open, max, min, close, spread, Trading_turnover |
| TaiwanStockTotalReturnIndex | meta | per_index | 有資料 | 9226 | 2008-01-02～2026-10-15 | price, stock_id, date |
| TaiwanStockPrice | core | per_stock | 有資料 | 12145 | 2008-01-02～2026-10-15 | date, stock_id, Trading_Volume, Trading_money, open, max, min, close, spread, Trading_turnover |
| TaiwanStockMonthRevenue | core | per_stock | 有資料 | 597 | 2008-01-01～2026-10-01 | date, stock_id, country, revenue, revenue_month, revenue_year, create_time |
| TaiwanStockFinancialStatements | core | per_stock | 有資料 | 3452 | 2008-03-31～2026-06-30 | date, stock_id, type, value, origin_name |
| TaiwanStockInstitutionalInvestorsBuySell | core | per_stock | 有資料 | 44706 | 2012-05-02～2026-10-15 | date, stock_id, buy, name, sell |
| TaiwanStockMarginPurchaseShortSale | core | per_stock | 有資料 | 11797 | 2008-01-02～2026-10-14 | date, stock_id, MarginPurchaseBuy, MarginPurchaseCashRepayment, MarginPurchaseLimit, MarginPurchaseSell, MarginPurchaseTodayBalance, MarginPurchaseYesterdayBalance, Note, OffsetLoanAndShort, ShortSaleBuy, ShortSaleCashRepayment, ShortSaleLimit, ShortSaleSell |
| TaiwanStockDividendResult | events | per_stock | 有資料 | 78 | 2008-07-16～2026-09-16 | date, stock_id, before_price, after_price, stock_and_cache_dividend, stock_or_cache_dividend, max_price, min_price, open_price, reference_price |
| TaiwanStockCapitalReductionReferencePrice | events | per_stock | 已下載、皆無資料 |  |  |  |
| TaiwanStockSplitPrice | events | global | 有資料 | 35 | 2019-09-09～2026-09-07 | date, stock_id, type, before_price, after_price, max_price, min_price, open_price |
| TaiwanStockParValueChange | events | global | 有資料 | 16 | 2019-09-09～2025-08-25 | date, stock_id, stock_name, before_close, after_ref_close, after_ref_max, after_ref_min, after_ref_open |
| TaiwanStockDispositionSecuritiesPeriod | events | per_stock | 停用：連續 3 檔失敗，可能需付費或參數不符：TaiwanStockDispositionSecuritiesPeriod 6 |  |  |  |
| TaiwanStockHoldingSharesPer | extended | per_stock | 失敗：TaiwanStockHoldingSharesPer 2330: HTTP 400 Your level is free. Please update you |  |  |  |
| TaiwanStockBalanceSheet | extended | per_stock | 有資料 | 1109 | 2023-12-31～2026-06-30 | date, stock_id, type, value, origin_name |
| TaiwanStockShareholding | extended | per_stock | 有資料 | 728 | 2023-10-16～2026-10-14 | date, stock_id, stock_name, InternationalCode, ForeignInvestmentRemainingShares, ForeignInvestmentShares, ForeignInvestmentRemainRatio, ForeignInvestmentSharesRatio, ForeignInvestmentUpperLimitRatio, ChineseInvestmentUpperLimitRatio, NumberOfSharesIssued, RecentlyDeclareDate, note |
| TaiwanStockPriceAdj | extended | per_stock | 失敗：TaiwanStockPriceAdj 2330: HTTP 400 Your level is free. Please update your user l |  |  |  |
| TaiwanStockSecuritiesLending | extended | per_stock | 有資料 | 6763 | 2023-10-16～2026-10-15 | date, stock_id, transaction_type, volume, fee_rate, close, original_return_date, original_lending_period |

## 類別值

- TaiwanStockInfo：type: twse(2403)、tpex(1379)、emerging(557)；industry_category: 電子工業(545)、生技醫療業(303)、半導體業(296)、ETF(272)、電子零組件業(262)、其他(194)、光電業(178)、電腦及週邊設備業(148)、電機機械(141)、上櫃ETF(125)、上櫃指數股票型基金(ETF)(125)、通信網路業(119)
- TaiwanStockFinancialStatements：type: EPS(196)、TAX(196)、CostOfGoodsSold(196)、Revenue(196)、GrossProfit(196)、OperatingIncome(196)、OperatingExpenses(196)、IncomeFromContinuingOperations(196)、OtherComprehensiveIncome(156)、IncomeAfterTaxes(156)、TotalConsolidatedProfitForThePeriod(156)、EquityAttributableToOwnersOfParent(156)
- TaiwanStockInstitutionalInvestorsBuySell：name: Foreign_Investor(9936)、Investment_Trust(9936)、Dealer_self(8477)、Dealer_Hedging(8477)、Foreign_Dealer_Self(6421)、Dealer(1459)
- TaiwanStockDividendResult：stock_or_cache_dividend: 息(53)、除息(17)、權息(7)、權(1)
- TaiwanStockSplitPrice：type: 面額變更(24)、反分割(6)、分割(4)、(1)
- TaiwanStockBalanceSheet：type: CashAndCashEquivalents(11)、CashAndCashEquivalents_per(11)、CurrentFinancialAssetsAtFairvalueThroughProfitOrLoss(11)、CurrentFinancialAssetsAtFairvalueThroughProfitOrLoss_per(11)、NonCurrentFinancialAssetsAtFairvalueThroughProfitOrLoss(11)、NonCurrentFinancialAssetsAtFairvalueThroughProfitOrLoss_per(11)、FinancialAssetsAtFairvalueThroughOtherComprehensiveIncome(11)、FinancialAssetsAtFairvalueThroughOtherComprehensiveIncome_per(11)、FinancialAssetsAtFairvalueThroughOtherComprehensiveIncomeNonCurrent(11)、FinancialAssetsAtFairvalueThroughOtherComprehensiveIncomeNonCurrent_per(11)、FinancialAssetsAtAmortizedCost(11)、FinancialAssetsAtAmortizedCost_per(11)

## 語意檢查

```json
{
  "IndexPrice": {
    "TAIEX": {
      "rows": 4613,
      "first_date": "2008-01-02",
      "last_date": "2026-10-15"
    },
    "TPEx": {
      "rows": 4613,
      "first_date": "2008-01-02",
      "last_date": "2026-10-15"
    }
  },
  "TaiwanStockTotalReturnIndex": {
    "TAIEX": {
      "rows": 4613,
      "first_date": "2008-01-02",
      "last_date": "2026-10-15"
    },
    "TPEx": {
      "rows": 4613,
      "first_date": "2008-01-02",
      "last_date": "2026-10-15"
    }
  },
  "revenue": {
    "checked": 597,
    "date_is_first_of_next_month": 1.0,
    "date_is_first_of_same_month": 0.0,
    "date_day_values": {
      "1": 597
    }
  },
  "financials": {
    "checked": 3452,
    "quarter_end_share": 1.0,
    "types": [
      "-",
      "ComprehensiveIncomeConsolidatedNetIncomeAttributedNonControllingInterest",
      "CostOfGoodsSold",
      "CumulativeEffectOfChangesInAccountingPrinciple",
      "EPS",
      "EquityAttributableToOwnersOfParent",
      "ExtraordinaryItems",
      "GrossProfit",
      "IncomeAfterTaxes",
      "IncomeBeforeIncomeTax",
      "IncomeBeforeTaxFromContinuingOperations",
      "IncomeFromContinuingOperations",
      "IncomeLossFromDiscontinuedOperation",
      "NetIncome",
      "NoncontrollingInterests",
      "OTHNOE",
      "OperatingExpenses",
      "OperatingIncome",
      "OtherComprehensiveIncome",
      "PreTaxIncome",
      "RealizedGain",
      "RealizedGainFromInterAffiliateAccounts",
      "Revenue",
      "TAX",
      "TotalConsolidatedProfitForThePeriod",
      "TotalNonbusinessIncome",
      "TotalNonoperatingIncomeAndExpense",
      "TotalnonbusinessExpenditure",
      "UnrealizedGain",
      "UnrealizedGainFromInterAffiliateAccounts"
    ],
    "n_types": 30
  },
  "dividend": {
    "checked": 53,
    "after_eq_before_minus_cash_share": 1.0
  },
  "universe": {
    "total": 2225,
    "listed": 1977,
    "delisted": 248,
    "listed_by_market": {
      "twse": 1084,
      "tpex": 893
    },
    "delisted_by_year": {
      "2008": 11,
      "2009": 6,
      "2010": 1,
      "2011": 1,
      "2012": 5,
      "2013": 6,
      "2014": 2,
      "2015": 3,
      "2016": 13,
      "2017": 9,
      "2018": 9,
      "2019": 8,
      "2020": 11,
      "2021": 4,
      "2022": 5,
      "2023": 6,
      "2024": 78,
      "2025": 9,
      "2026": 61
    },
    "reused_codes": 0
  }
}
```

## 額度查詢回應

```json
{
  "without_token": {
    "http": 200,
    "keys": [
      "msg",
      "status"
    ]
  }
}
```
