"""鉅亨網基金（fund.cnyes.com）連接器 —— 每日基準多期報酬覆蓋層（Tier B）。

為什麼需要：復華官網 /api/fund 的多期報酬（roiY2D/roi3m/roi1y…）為**月底基準**
——2026-07-15 以 git 歷史實測：NAV 天天動、YTD/3m/1y 十四天紋風不動（皆 06/30 值）。
使用者要「最新每日」的績效 → 以鉅亨基金搜尋 API 的每日更新欄位覆蓋；
鉅亨缺值時儀表板逐欄回退官網值，整層失敗則完全不影響既有流程（同 etfinfo 慣例）。

端點（正式區 CI 驗證；本 Claude 容器 proxy 擋 cnyes、只能離線測 parser）：
  GET https://fund.api.cnyes.com/fund/api/v2/search/funds?keyword=復華&page=N
回傳格式**防禦式解析**：items 位置與欄位名逐候選嘗試；解析不到時把首筆 keys
印進 stdout——CI 日誌即真實 schema，供下輪迭代（get_job_logs 可讀）。

名稱對映：以正規化名稱（去空白、統一連字號）比對官網基金名；比對結果落
data/cnyes_fund_map.json（入庫）供稽核與手動覆寫（該檔某 fund_id 若已填
cnyesId 則優先採用、不再名稱比對）。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from ..http import get_json

ROOT = Path(__file__).resolve().parent.parent.parent
MAP_PATH = ROOT / "data" / "cnyes_fund_map.json"

# 候選端點（2026-07-15 CI 實測 v2/search/funds 404 → 改探測電池：逐一試、
# 用第一個回傳可解析 items 者；勝出者與各候選狀態都印進 CI 日誌供收斂）
URL_CANDIDATES = (
    "https://fund.api.cnyes.com/fund/api/v1/search/funds?keyword={kw}&page={page}",
    "https://fund.api.cnyes.com/fund/api/v2/funds/search?keyword={kw}&page={page}",
    "https://fund.api.cnyes.com/fund/api/v1/funds?keyword={kw}&page={page}",
    "https://fund.api.cnyes.com/fund/api/v2/funds?keyword={kw}&page={page}",
    "https://gfe-fund.cnyes.com/api/v2/search/funds?keyword={kw}&page={page}",
    "https://gfe-fund.cnyes.com/fund/api/v2/search/funds?keyword={kw}&page={page}",
    "https://fund.cnyes.com/api/v2/search/funds?keyword={kw}&page={page}",
    "https://fund.api.cnyes.com/fund/api/v2/search/funds?keyword={kw}&page={page}",
)
# cnyes API 可能擋非瀏覽器 UA／缺 Referer 的請求
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://fund.cnyes.com/",
    "Accept": "application/json, text/plain, */*",
}

_TW = timezone(timedelta(hours=8))

# 我方鍵 → 來源候選鍵（依序取第一個非 None；cnyes 命名不確定，寧多列勿漏）
_RET_KEYS: dict[str, tuple[str, ...]] = {
    "1w": ("return1W", "return1w", "returnWeek", "return7D", "return7d"),
    "1m": ("return1M", "return1m", "returnMonth"),
    "3m": ("return3M", "return3m"),
    "6m": ("return6M", "return6m"),
    "ytd": ("returnYTD", "returnYtd", "returnY2D", "returnThisYear"),
    "1y": ("return1Y", "return1y"),
    "2y": ("return2Y", "return2y"),
    "3y": ("return3Y", "return3y"),
}
_ID_KEYS = ("cnyesId", "cnyesID", "fundId", "fundID", "id")
_NAME_KEYS = ("displayNameLocal", "displayNameLocalWithKwd", "displayName",
              "nameLocal", "fundName", "name")
_NAV_KEYS = ("nav", "latestNav", "navPrice", "price")
_NAVDATE_KEYS = ("navDate", "navdate", "priceDate", "lastUpdate", "updateDate")
_CHG_KEYS = ("changePercent", "changePct", "navChangePercent", "change_pct")


def _pick(d: dict, keys: tuple[str, ...]):
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


def _num(v) -> float | None:
    """'12.34%' / '12.34' / 12.34 → 12.34；None/怪值 → None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+\.?\d*", str(v).replace(",", ""))
    return float(m.group()) if m else None


def _date(v) -> str | None:
    """epoch 秒 / 'YYYY-MM-DD' / 'YYYY/MM/DD'（含時間尾綴）→ 'YYYY/MM/DD'。"""
    if v is None:
        return None
    if isinstance(v, (int, float)) and v > 1e8:            # epoch 秒
        return datetime.fromtimestamp(int(v), tz=_TW).strftime("%Y/%m/%d")
    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", str(v))
    return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}" if m else None


def _items(payload) -> list[dict]:
    """在常見包裝（items.data / items / data.data / data）裡找出第一個 dict 清單。"""
    def as_list(x):
        if isinstance(x, list) and (not x or isinstance(x[0], dict)):
            return x
        return None
    if not isinstance(payload, dict):
        return as_list(payload) or []
    for path in (("items", "data"), ("items",), ("data", "data"), ("data",)):
        node = payload
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
            if node is None:
                break
        got = as_list(node)
        if got is not None:
            return got
    return []


def norm_name(s: str | None) -> str:
    """基金名稱正規化：去空白、統一各式連字號為 '-'、全形轉半形括號。"""
    s = (s or "").strip()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[‐‑–—―−﹣－]", "-", s)
    return s.replace("（", "(").replace("）", ")")


def _probe(keyword: str) -> tuple[str, list[dict]] | None:
    """逐一試候選端點（第 1 頁），回 (勝出模板, items)；全滅回 None。
    每個候選的失敗原因都印進日誌——CI 一輪即可收斂正確端點。"""
    for tmpl in URL_CANDIDATES:
        url = tmpl.format(kw=quote(keyword), page=1)
        try:
            payload = get_json(url, retries=1, cache_ttl=3600, headers=_HEADERS)
        except Exception as e:
            print(f"  [cnyes 探測] ✗ {url.split('?')[0]}（{e}）")
            continue
        items = _items(payload)
        if items:
            print(f"  [cnyes 探測] ✓ 勝出端點 {tmpl.split('?')[0]}")
            return tmpl, items
        top = sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        print(f"  [cnyes 探測] △ {url.split('?')[0]} 回應無 items；頂層＝{top}")
    return None


def search_all(keyword: str = "復華", max_pages: int = 10) -> list[dict]:
    """探測可用端點後逐頁掃到空頁為止；回原始 item 清單。schema 不符時印診斷。"""
    hit = _probe(keyword)
    if hit is None:
        return []
    tmpl, out = hit
    for page in range(2, max_pages + 1):
        try:
            payload = get_json(tmpl.format(kw=quote(keyword), page=page),
                               retries=1, cache_ttl=3600, headers=_HEADERS)
        except Exception:
            break
        items = _items(payload)
        if not items:
            break
        out.extend(items)
        if len(items) < 10:                                 # 末頁（頁大小通常 ≥10）
            break
    if out and _pick(out[0], _NAME_KEYS) is None:
        print(f"  [cnyes 診斷] item keys＝{sorted(out[0].keys())}")
    return out


def overlay_from_item(item: dict) -> dict:
    """單筆搜尋結果 → 覆蓋層欄位（值可能為 None，呼叫端逐欄判斷）。"""
    rets = {k: _num(_pick(item, cands)) for k, cands in _RET_KEYS.items()}
    return {
        "cnyes_id": _pick(item, _ID_KEYS),
        "cnyes_name": _pick(item, _NAME_KEYS),
        "nav": _num(_pick(item, _NAV_KEYS)),
        "nav_date": _date(_pick(item, _NAVDATE_KEYS)),
        "chg_pct": _num(_pick(item, _CHG_KEYS)),
        "returns_daily": {k: v for k, v in rets.items() if v is not None},
    }


def _load_map() -> dict:
    if not MAP_PATH.exists():
        return {}
    try:
        d = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def apply_overlay(docs: list[dict], out_dir: Path) -> int:
    """對每檔基金 doc 覆蓋鉅亨每日欄位並重寫 JSON。回傳成功覆蓋檔數。

    覆蓋規則（防清史、逐欄）：
      · returns_daily／returns_daily_asof：鉅亨有值才寫（儀表板逐欄回退官網 returns）
      · nav/nav_date/nav_change_pct：僅當鉅亨 NAV 日**較新**才覆蓋並標 nav_src="cnyes"
    """
    if not docs:
        return 0
    items = search_all()
    if not items:
        print("  [cnyes] 搜尋無結果，跳過覆蓋（沿用官網值）")
        return 0
    by_name = {norm_name(_pick(it, _NAME_KEYS)): it for it in items}
    by_id = {str(_pick(it, _ID_KEYS)): it for it in items if _pick(it, _ID_KEYS)}
    fmap = _load_map()
    n = 0
    for doc in docs:
        fid = str(doc.get("fund_id"))
        pin = (fmap.get(fid) or {}).get("cnyesId")
        item = by_id.get(str(pin)) if pin else None
        if item is None:
            item = by_name.get(norm_name(doc.get("name"))) \
                or by_name.get(norm_name(doc.get("short_name")))
        if item is None:
            continue
        ov = overlay_from_item(item)
        if not ov["returns_daily"] and ov["nav"] is None:
            continue
        if ov["returns_daily"]:
            doc["returns_daily"] = ov["returns_daily"]
            doc["returns_daily_asof"] = ov["nav_date"]
        newer = (ov["nav"] is not None and ov["nav_date"] and
                 str(ov["nav_date"]) > str(doc.get("nav_date") or ""))
        if newer:
            doc["nav"], doc["nav_date"], doc["nav_src"] = ov["nav"], ov["nav_date"], "cnyes"
            if ov["chg_pct"] is not None:
                doc["nav_change_pct"] = f"{ov['chg_pct']:+.2f}%"
        fmap[fid] = {"cnyesId": ov["cnyes_id"], "name": ov["cnyes_name"]}
        (out_dir / f"{fid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        n += 1
    if n:
        MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        MAP_PATH.write_text(json.dumps(fmap, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    print(f"  [cnyes] 每日報酬覆蓋 {n}/{len(docs)} 檔"
          + ("" if n else "（名稱比對零命中——檢查 data/cnyes_fund_map.json 或日誌診斷）"))
    return n
