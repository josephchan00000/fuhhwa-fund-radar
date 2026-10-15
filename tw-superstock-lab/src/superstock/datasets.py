"""要下載的 FinMind 資料集清單。

資料集名稱與欄位依 FinMind 2.0.11 套件原始碼（FinMind/schema/data.py、data/data_loader.py）。
mode 說明：
  global     一次請求拿全部（股票清單、下市清單、交易日）
  per_index  依指數代號逐一請求（TAIEX、TPEx）
  per_stock  依股票代號逐一請求（免費帳號不能一次拿全市場，只能逐檔）
try_global=True 的資料集（事件類，資料量小）會先試「不帶股票代號、按年份整批下載」，
若免費帳號不允許，自動改回逐檔。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    name: str                       # FinMind dataset 名稱
    mode: str                       # global | per_index | per_stock
    group: str                      # meta | core | events | extended
    key_cols: tuple[str, ...] = ()  # 去重鍵（per_stock 會自動加上 stock_id）；空 = 整列完全相同才去重
    ids: tuple[str, ...] = ()       # per_index 的代號
    use_dates: bool = True          # API 是否帶 start_date / end_date
    overlap_days: int = 10          # 增量更新時往回重抓幾天（處理補登、更正）
    try_global: bool = False
    alias: str | None = None        # 本機儲存名稱（同一個 dataset 用在不同用途時區分）
    note: str = ""

    @property
    def store_name(self) -> str:
        return self.alias or self.name


REGISTRY: tuple[DatasetSpec, ...] = (
    # ---- meta：先下載，用來決定股票池與交易日 ----
    DatasetSpec("TaiwanStockInfo", "global", "meta", ("stock_id", "type", "industry_category"),
                use_dates=False, note="股票清單、產業別、市場別"),
    DatasetSpec("TaiwanStockDelisting", "global", "meta", ("stock_id", "date"),
                use_dates=False, note="下市櫃清單（消除倖存者偏差）"),
    DatasetSpec("TaiwanStockTradingDate", "global", "meta", ("date",), note="交易日曆"),
    DatasetSpec("TaiwanStockPrice", "per_index", "meta", ("date", "stock_id"),
                ids=("TAIEX", "TPEx"), alias="IndexPrice", note="加權指數、櫃買指數"),
    DatasetSpec("TaiwanStockTotalReturnIndex", "per_index", "meta", ("date", "stock_id"),
                ids=("TAIEX", "TPEx"), note="報酬指數（比較基準）"),
    # ---- core：每檔股票各一次請求 ----
    DatasetSpec("TaiwanStockPrice", "per_stock", "core", ("date",), note="日 K（原始價）"),
    DatasetSpec("TaiwanStockMonthRevenue", "per_stock", "core", ("revenue_year", "revenue_month"),
                overlap_days=400, note="月營收"),
    DatasetSpec("TaiwanStockFinancialStatements", "per_stock", "core", ("date", "type"),
                overlap_days=500, note="綜合損益表（EPS、毛利、營益）"),
    DatasetSpec("TaiwanStockInstitutionalInvestorsBuySell", "per_stock", "core", ("date", "name"),
                note="三大法人買賣超"),
    DatasetSpec("TaiwanStockMarginPurchaseShortSale", "per_stock", "core", ("date",),
                note="融資融券"),
    # ---- events：還原價與可交易性所需的事件 ----
    DatasetSpec("TaiwanStockDividendResult", "per_stock", "events", ("date",),
                overlap_days=60, try_global=True, note="除權除息結果（還原價）"),
    DatasetSpec("TaiwanStockCapitalReductionReferencePrice", "per_stock", "events", ("date",),
                overlap_days=60, try_global=True, note="減資恢復買賣參考價（還原價）"),
    DatasetSpec("TaiwanStockSplitPrice", "per_stock", "events", ("date",),
                overlap_days=60, try_global=True, note="分割後參考價（還原價）"),
    DatasetSpec("TaiwanStockParValueChange", "per_stock", "events", ("date",),
                overlap_days=60, try_global=True, note="變更面額參考價（還原價）"),
    DatasetSpec("TaiwanStockDispositionSecuritiesPeriod", "per_stock", "events",
                ("date", "period_start", "period_end"), overlap_days=60, try_global=True,
                note="處置股期間"),
    # ---- extended：之後的 Phase 會用到，第一輪可先不抓 ----
    DatasetSpec("TaiwanStockHoldingSharesPer", "per_stock", "extended", ("date", "HoldingSharesLevel"),
                note="集保股權分散表（千張大戶）"),
    DatasetSpec("TaiwanStockBalanceSheet", "per_stock", "extended", ("date", "type"),
                overlap_days=500, note="資產負債表"),
    DatasetSpec("TaiwanStockShareholding", "per_stock", "extended", ("date",), note="外資持股、發行股數"),
    DatasetSpec("TaiwanStockPriceAdj", "per_stock", "extended", ("date",),
                note="FinMind 還原價（只用來交叉驗證自算還原價）"),
    DatasetSpec("TaiwanStockSecuritiesLending", "per_stock", "extended", (), note="借券成交明細"),
)

GROUP_ORDER = ("meta", "core", "events", "extended")


def specs_for_groups(groups: list[str] | tuple[str, ...]) -> list[DatasetSpec]:
    unknown = set(groups) - set(GROUP_ORDER)
    if unknown:
        raise ValueError(f"未知的下載群組：{sorted(unknown)}，可用：{GROUP_ORDER}")
    ordered = [g for g in GROUP_ORDER if g in groups]
    return [s for g in ordered for s in REGISTRY if s.group == g]


def get_spec(store_name: str) -> DatasetSpec:
    for spec in REGISTRY:
        if spec.store_name == store_name:
            return spec
    raise KeyError(store_name)
