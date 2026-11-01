"""etfinfo.tw 第三方彙整連接器（Tier B）—— ETF 清單、單檔市況與每日持股。

etfinfo.tw 為 Nuxt SPA，資料走 JSON API（已實測）：
  - `GET /api/etf/list`            全 ETF 清單（code/name/type/managementStyle/AUM/受益人）。
  - `GET /api/etf/{code}`          單檔：info / latestMarket / holdings / dividends / trailingYield。

用在 ETF 數據追蹤（etfwatch：fetch_etf）、ETF 持股（scripts/fetch_etf_holdings.py：holdings_fresh）、
籌碼雷達擴充 ETF（arm/lab/collect.py：list_etfs、holdings_fresh）。2026-11-01 拿掉舊的本機流程時，
只有它在用的 latest_market、dividends、active_flow 一起拿掉（要看從 git 歷史找）。

⚠️ Tier B 標注鐵則：etfinfo 自述「整理自公開來源」，持股 source 多為 issuer-official
（投信官方揭露彙整）。一律帶 as-of 與來源；數字屬「先給可能值、待人工核對」，上線前須
以投信官網／公開說明書核實（§20.1 Tier B）。
"""
from __future__ import annotations

from ..http import get_json

API = "https://www.etfinfo.tw/api"


def fetch_etf(code: str, *, cache_ttl: int = 6 * 3600) -> dict:
    """單檔完整記錄（info/latestMarket/holdings/dividends/trailingYield/returnStats）。

    `cache_ttl`：同日盤後求鮮（latestMarket/holdings 當日即更新）→ 快取路徑傳短 TTL（如 600s）。
    """
    return get_json(f"{API}/etf/{code}", cache_ttl=cache_ttl)  # type: ignore[return-value]


def holdings_fresh(code: str, *, cache_ttl: int = 600) -> tuple[list[dict], dict]:
    """同 holdings()，但走短 TTL 求當日最新快照（盤後常有當日 snapshotDate）。"""
    return _holdings_from(fetch_etf(code, cache_ttl=cache_ttl))


def list_etfs() -> list[dict]:
    """全 ETF 清單（含 managementStyle=active/passive、dividendFrequency、AUM、受益人）。"""
    return (get_json(f"{API}/etf/list", cache_ttl=6 * 3600) or {}).get("items", [])  # type: ignore[union-attr]


def _holdings_from(d: dict) -> tuple[list[dict], dict]:
    h = d.get("holdings") or {}
    raw = h.get("stocks") or h.get("holdings") or []
    # 期貨列帶 kind="future"（API 的 assetType；2026-10-21 CI 探針：00986D `US202612`、
    # 00987D `UB:2026-12:B` 皆為 "future"、unit "口"）——比代號格式可靠，抓取端據此另存「期貨部位」
    out = [{"stock_id": str(r["code"]), "stock_name": r.get("name", ""),
            "weight": float(r.get("weight") or 0.0), "shares": int(r.get("shares") or 0),
            **({"kind": "future"} if str(r.get("assetType") or "").lower() == "future" else {})}
           for r in raw if r.get("code")]
    info = d.get("info") or {}
    meta = {"issuer": info.get("issuer"), "name": info.get("name"),
            "as_of": h.get("snapshotDate"), "source": h.get("source")}
    return out, meta


def holdings(code: str) -> tuple[list[dict], dict]:
    """正規化持股 → ([{stock_id,stock_name,weight,shares}], meta)。

    meta：{issuer, name, as_of(snapshotDate), source}。取不到回 ([], meta)。
    """
    return _holdings_from(fetch_etf(code))
