"""TWSE OpenAPI 基金基本資料彙總表（t187ap47_L）——已發行單位數，ETF 規模第二來源交叉驗證。

2026-07-27 使用者反映 etfinfo 規模已連續 3 天（含實際交易日）未更新——原架構 etfinfo 為
單一來源、無 fallback，etfinfo 自己停滯我們也只能照單全收。此表為官方揭露的基金基本資料，
含「已發行單位數」——申贖時才變動、平時不逐日改變，但配合每日更新的 NAV（來自 etfinfo
latestMarket.nav）可自算 AUM＝已發行單位數 × NAV，作為 etfinfo 規模的獨立交叉驗證／備援：
即使 etfinfo 的規模欄位停滯不動，只要它的 NAV 還在動，這個自算值仍能反映當下規模。

此容器 proxy 擋 twse——抓取只在正式區 CI；容器內測試需靠 CI 日誌驗證與迭代（同 macrochips／
cnyesfund 慣例）。欄位以「關鍵字」比對而非精確鍵值——TWSE 官方表頭常見括號/直線混排寫法
（如「發行單位數|轉換數」），精確字串比對一有出入就整段抓空，關鍵字比對較不脆弱。
"""
from __future__ import annotations

from ..http import get_json

API = "https://openapi.twse.com.tw/v1/opendata/t187ap47_L"

_CODE_KEY_HINTS = ("代號", "代碼")
_UNIT_KEY_HINTS = ("發行單位數", "受益權單位數")


def fetch_units(*, cache_ttl: int = 6 * 3600) -> dict[str, float]:
    """{基金代號: 已發行單位數} 全表；抓不到／格式異常回空字典（呼叫端須自行 fallback）。"""
    try:
        rows = get_json(API, cache_ttl=cache_ttl)
    except Exception:
        return {}
    out: dict[str, float] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        code = next((str(v).strip() for k, v in row.items()
                     if isinstance(v, str) and any(h in k for h in _CODE_KEY_HINTS)), None)
        if not code:
            continue
        for k, v in row.items():
            if any(h in k for h in _UNIT_KEY_HINTS):
                try:
                    units = float(str(v).replace(",", "").strip())
                except (TypeError, ValueError):
                    continue
                if units > 0:
                    out[code] = units
                break
    return out
