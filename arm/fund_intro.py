"""持股介紹（復華基金追蹤版本核心）—— 把 data/funds/{id}.json ＋ config/holding_profiles.json
合成一份『可讀的持股介紹』給 dashboard／報告使用。純讀取、可單測，缺檔即回空、不崩。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

ROOT = Path(__file__).resolve().parent.parent
FUNDS_DIR = ROOT / "data" / "funds"
PROFILES = ROOT / "config" / "holding_profiles.json"

GROUP_LABEL = {"global_equity": "全球股票型", "global_balanced": "全球平衡型",
               "tw_equity": "國內股票型", "tw_balanced": "國內平衡型",
               "tw_fof": "台灣智能（組合型）"}


_prof_cache: tuple[float, dict] | None = None   # (mtime, profiles)——render 全程重讀 50 次的熱點


def _profiles() -> dict:
    """holding_profiles.json 以 mtime 快取（審查 2026-07-18：每檔基金 load() 都重解析一次，
    render 一輪約 50 次重複 I/O；檔案變更時 mtime 失效自動重讀，行為不變）。"""
    global _prof_cache
    if not PROFILES.exists():
        return {}
    try:
        mt = PROFILES.stat().st_mtime
        if _prof_cache is not None and _prof_cache[0] == mt:
            return _prof_cache[1]
        d = json.loads(PROFILES.read_text(encoding="utf-8")).get("profiles", {})
        _prof_cache = (mt, d)
        return d
    except Exception:
        return {}


def load(fund_id: str) -> dict | None:
    """讀一檔基金快照，並把每檔持股的『重點標的簡介』掛上去（依原字串精確對應）。"""
    fp = FUNDS_DIR / f"{fund_id}.json"
    if not fp.exists():
        return None
    try:                                    # 空檔/半寫入的壞 JSON 視同缺檔，跳過該檔、不讓整份儀表板崩
        doc = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None
    profs = _profiles()
    for h in doc.get("top_holdings", []):
        p = profs.get(h.get("name")) or {}
        h["intro"] = p.get("intro")
        h["ticker"] = p.get("ticker")
        h["country"] = p.get("country")
    doc["group_label"] = GROUP_LABEL.get(doc.get("group"), doc.get("category") or "")
    return doc


def all_funds() -> list[dict]:
    """依 config/funds.json 的順序回傳所有已抓到的基金持股介紹。"""
    out = []
    for f in config.funds():
        doc = load(str(f["id"]))
        if doc:
            out.append(doc)
    return out


def pending_funds() -> list[dict]:
    """已列入 config 追蹤、但 data/funds 尚無（或壞損）快照的基金——例如新加入的
    台股清單，待本機執行 fetch_holdings 後才有數據。回 [{fund_id, name, group, group_label}]。"""
    out = []
    for f in config.funds():
        if load(str(f["id"])) is None:
            out.append({"fund_id": str(f["id"]), "name": f.get("name") or "",
                        "group": f.get("group"),
                        "group_label": GROUP_LABEL.get(f.get("group"), "")})
    return out


def uncovered_top_holdings(n: int = 10) -> list[dict]:
    """掃所有已抓到的基金快照，回傳「前 n 大持股缺重點標的簡介」的清單
    （2026-07-23 使用者需求：前十大簡介一再漏掉，做成每次可查的防呆）。

    根因：持股在正式區 CI 抓（容器 proxy 擋），每月換持股時新標的名只會出現在
    CI 產出，容器端看不到 → 本地檢查抓不到、漏的簡介直接上線。故此函式供 CI 端
    （daily.yml 建表後）與每日 SOP 兩邊呼叫，任何新標的缺 intro 立刻現形。

    回 [{fund_id, short_name, name, weight, sector}, …]，依「跨幾檔基金出現」排序。
    """
    profs = _profiles()
    have = {k for k, v in profs.items() if (v or {}).get("intro")}
    seen: dict[str, dict] = {}
    for f in config.funds():
        doc = load(str(f["id"]))
        if not doc:
            continue
        short = doc.get("short_name") or doc.get("name") or str(f["id"])
        for h in (doc.get("top_holdings") or [])[:n]:
            name = h.get("name")
            if not name or name in have:
                continue
            slot = seen.setdefault(name, {"name": name, "sector": h.get("sector"),
                                          "funds": [], "count": 0})
            slot["count"] += 1
            if len(slot["funds"]) < 6:
                slot["funds"].append({"fund_id": str(doc.get("fund_id")),
                                      "short_name": short, "weight": h.get("weight")})
    return sorted(seen.values(), key=lambda s: -s["count"])


def top_concentration(doc: dict, n: int = 10) -> float | None:
    """前 n 大持股權重合計（%）。"""
    hs = doc.get("top_holdings") or []
    if not hs:
        return None
    return round(sum(h.get("weight") or 0 for h in hs[:n]), 1)

def norm_ticker(s) -> str:
    """代號正規化：大寫、去空白，並剝掉彭博式交易所字尾（`AMD US`→`AMD`、`8035 JP`→`8035`）。

    ETF 持股快照的海外代號帶交易所碼（US／LN／JP／FP／GR／IM／NA／KS…），
    簡介庫存的是純代號——不正規化的話 `AMD US` 永遠對不到已建好的 `AMD`
    （2026-07-31 實測：光這一條就讓數十檔海外持股的簡介白白落空）。
    """
    t = str(s or "").strip().upper()
    if " " in t:
        head, _, tail = t.rpartition(" ")
        if head and tail.isalpha() and len(tail) <= 3:
            return head.strip()
    return t


def intro_lookup() -> tuple[dict, dict]:
    """→ ({ticker: intro}, {name: intro})：供 ETF 持股明細掛標的簡介用。

    簡介庫（`config/holding_profiles.json`）原本是為「基金前十大」而建，鍵是持股原字串；
    ETF 持股用的是股票代號，所以另外以 profile 裡的 `ticker` 建一份索引，兩邊都查。
    代號索引同時收「原樣大寫」與「剝掉交易所字尾」兩種鍵（見 `norm_ticker`），
    查詢端兩種都試一次即可。名稱索引另收一份大寫鍵（同名不同大小寫也對得上）。

    覆蓋率有限——有就顯示、沒有就不留空位，儀表板另標「N 檔附標的簡介」誠實揭露。
    """
    profs = _profiles()
    by_tk, by_nm = {}, {}
    for name, v in profs.items():
        intro = (v or {}).get("intro")
        if not intro:
            continue
        by_nm.setdefault(name.strip(), intro)
        by_nm.setdefault(name.strip().upper(), intro)
        tk = str((v or {}).get("ticker") or "").strip()
        if tk:
            by_tk.setdefault(tk, intro)
            by_tk.setdefault(tk.upper(), intro)
            by_tk.setdefault(norm_ticker(tk), intro)
    return by_tk, by_nm
