"""etfinfo.tw 第三方彙整連接器（Tier B）—— 補實 M2 競品持股 / 配息 / 主動ETF籌碼追蹤。

etfinfo.tw 為 Nuxt SPA，資料走 JSON API（已實測）：
  - `GET /api/etf/list`            全 ETF 清單（code/name/type/managementStyle/AUM/受益人）。
  - `GET /api/etf/{code}`          單檔：info / latestMarket / holdings / dividends / trailingYield。
  - `GET /api/active/tracking`     主動ETF「估算新進/加碼」籌碼追蹤（誰在被法人大買）。

本連接器把它正規化成專案既有格式：
  - holdings  → `config/competitor_holdings/{code}.json` 的 Holding（M2 競品逐日持股來源）。
  - dividends / trailingYield → 入息比較引擎素材（待 income_peers）。
  - active_flow → 主動ETF/投信估算新進，§18.4「聰明錢」的**可得替代源**（非券商分點）。

⚠️ Tier B 標注鐵則：etfinfo 自述「整理自公開來源」，持股 source 多為 issuer-official
（投信官方揭露彙整）。一律帶 as-of 與來源；數字屬「先給可能值、待人工核對」，上線前須
以投信官網／公開說明書核實（§20.1 Tier B）。**etfinfo 無券商分點(分點)資料**——分點仍需
玩股網/Wantgoo/證交所 bsr（見 §18.4）；本連接器提供的是「主動ETF/投信」層級的籌碼。
"""
from __future__ import annotations

from ..http import get_json

API = "https://www.etfinfo.tw/api"


def fetch_etf(code: str, *, cache_ttl: int = 6 * 3600) -> dict:
    """單檔完整記錄（info/latestMarket/holdings/dividends/trailingYield/returnStats）。

    `cache_ttl`：同日盤後求鮮（latestMarket/holdings 當日即更新）→ 快取路徑傳短 TTL（如 600s）。
    """
    return get_json(f"{API}/etf/{code}", cache_ttl=cache_ttl)  # type: ignore[return-value]


def latest_market(code: str, *, cache_ttl: int = 600) -> dict:
    """單檔同日最新市況 → {date, price, nav, change, premium, aum, beneficiaries}。

    etfinfo `latestMarket` 13:30 收盤後即帶當日（早於 TWSE STOCK_DAY_ALL 晚間批次）；
    用短 TTL 求鮮。取不到回 {}。Tier B：上線前以投信官網/公開資訊核對。
    """
    lm = (fetch_etf(code, cache_ttl=cache_ttl).get("latestMarket") or {})
    return {"date": lm.get("date"), "price": lm.get("price"), "nav": lm.get("nav"),
            "change": lm.get("change"), "premium": lm.get("premium"),
            "aum": lm.get("aum"), "beneficiaries": lm.get("beneficiaries")}


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


def dividends(code: str) -> tuple[list[dict], float | None]:
    """配息紀錄 [{ex_date, amount}] + 近12月殖利率（trailingYield, %）。入息比較用。"""
    d = fetch_etf(code)
    divs = [{"ex_date": x.get("exDate"), "amount": x.get("amount")}
            for x in (d.get("dividends") or []) if x.get("exDate")]
    return divs, d.get("trailingYield")


def active_flow(side: str = "buy") -> tuple[dict, list[dict]]:
    """主動ETF/投信「估算新進/加碼」籌碼追蹤 → (meta, items)。

    item 例：{stockCode, stockName, industry, reason:'5 檔 ETF / 4 家投信新進…',
              metrics:[{label:'估算新進',value:'+1.2 億'},…], tags, side}。
    §18.4 聰明錢的**法人層級**替代源（非券商分點，身份為主動ETF/投信集合，非個別買家）。
    """
    url = f"{API}/active/tracking" + (f"?side={side}" if side and side != "buy" else "")
    d = get_json(url, cache_ttl=3 * 3600) or {}
    meta = {k: v for k, v in d.items() if k != "items"}  # type: ignore[union-attr]
    return meta, d.get("items", [])  # type: ignore[union-attr]
