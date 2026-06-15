"""題材 / 時事引擎（M5, §8 #13, §21）—— 用 STOCK_DAY_ALL 算「當日真實題材熱度」。

不再用固定題材清單；每天由「該題材成分股**今天實際漲多少、幾檔在漲**」決定熱度，
再對照本檔重倉，找出『重倉產業 = 當日強勢題材』的順風賣點。

資料源：
  - 個股漲跌：TWSE `STOCK_DAY_ALL`（官方收盤，Tier A；**僅上市**，上櫃/TPEx 個股不在此熱度母體）。
  - 題材對照：`config/intel_seed.json` 的 `theme_map`（Tier B 人工維護/可擴充）。

**用 stock_id 當鍵，不用名稱**：TWSE 與復華持股對同一檔的名稱常不同
（台積電 vs 台灣積體、國巨* vs 國巨股份），且名稱子字串易誤判（「聯電」⊂「群聯電子」）。
ticker 跨源一致且唯一，分類零歧義。

題材對照表格式（grouped，可讀又精確）：
  {題材: {stock_id: 名稱, ...}}     ← 建議
  {題材: [stock_id, ...]}           ← 亦可
"""
from __future__ import annotations


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def pct_of(rec: dict) -> float | None:
    """STOCK_DAY_ALL 單筆 {close,change} → 當日漲跌幅（prev=close-change）。"""
    c, ch = rec.get("close"), rec.get("change")
    if c is None or ch is None:
        return None
    prev = c - ch
    return (ch / prev) if prev else None


def normalize_map(theme_map: dict) -> dict[str, list[str]]:
    """一律回傳 {題材: [stock_id, ...]}，吃 {id:name} 或 [id] 兩種成分表。"""
    out: dict[str, list[str]] = {}
    for theme, members in (theme_map or {}).items():
        ids = list(members.keys()) if isinstance(members, dict) else list(members)
        out[theme] = [str(i) for i in ids]
    return out


def id_to_theme(theme_map: dict) -> dict[str, str]:
    """stock_id → 題材（首個歸屬者勝）。"""
    out: dict[str, str] = {}
    for theme, ids in normalize_map(theme_map).items():
        for i in ids:
            out.setdefault(i, theme)
    return out


def theme_heat(all_today: dict, theme_map: dict, *, strong: float = 0.03) -> dict:
    """每個題材的當日熱度（成分股實際漲跌彙總），依 heat 由大到小。

    回傳 {題材: {members, n_total, n_up, n_strong, avg_pct, max_pct, heat}}，
    members=[{stock_id,name,pct}]（已依漲幅排序）。
    heat = 漲幅強度(平均漲幅) + 強漲檔數 + 上漲廣度，clamp 0~100。
    """
    t2 = id_to_theme(theme_map)
    buckets: dict[str, list] = {}
    for code, rec in all_today.items():
        theme = t2.get(code)
        if theme is None:
            continue
        pct = pct_of(rec)
        if pct is None:
            continue
        buckets.setdefault(theme, []).append(
            {"stock_id": code, "name": rec.get("name"), "pct": pct})

    out: dict[str, dict] = {}
    for theme, members in buckets.items():
        members.sort(key=lambda x: x["pct"], reverse=True)
        n_total = len(members)
        n_up = sum(1 for m in members if m["pct"] > 0)
        n_strong = sum(1 for m in members if m["pct"] >= strong)
        avg = sum(m["pct"] for m in members) / n_total
        breadth = n_up / n_total
        heat = round(_clamp(1000 * max(0.0, avg) + 10 * n_strong + 30 * breadth), 1)
        out[theme] = {"members": members, "n_total": n_total, "n_up": n_up,
                      "n_strong": n_strong, "avg_pct": round(avg, 4),
                      "max_pct": round(members[0]["pct"], 4), "heat": heat}
    return dict(sorted(out.items(), key=lambda kv: kv[1]["heat"], reverse=True))


def hot_themes(heat: dict, *, top: int = 5, min_heat: float = 25.0) -> list[tuple[str, dict]]:
    """市場當日最熱題材（已過 min_heat 門檻）。"""
    return [(t, h) for t, h in heat.items() if h["heat"] >= min_heat][:top]


def fund_tailwinds(holdings: list, all_today: dict, theme_map: dict, *,
                   min_heat: float = 25.0, min_weight: float = 3.0) -> list[dict]:
    """本檔『重倉產業 = 當日強勢題材』的順風清單（依 heat×權重排序）。

    每筆：{theme, fund_weight, holdings:[{stock_id,name,weight,pct}],
           market_heat, market_n_strong, market_n_total, market_avg_pct, score}。
    fund_weight 以 FHTrust 權威持股計（含上櫃）；market_* 為 TWSE 上市母體熱度。
    """
    t2 = id_to_theme(theme_map)
    heat = theme_heat(all_today, theme_map)

    by_theme: dict[str, dict] = {}
    for h in holdings:
        theme = t2.get(str(h.get("stock_id")))
        if theme is None:
            continue
        rec = all_today.get(str(h.get("stock_id")))
        slot = by_theme.setdefault(theme, {"theme": theme, "fund_weight": 0.0, "holdings": []})
        slot["fund_weight"] += h.get("weight") or 0.0
        slot["holdings"].append({"stock_id": h.get("stock_id"), "name": h.get("stock_name"),
                                 "weight": h.get("weight") or 0.0,
                                 "pct": pct_of(rec) if rec else None})

    out: list[dict] = []
    for theme, slot in by_theme.items():
        mh = heat.get(theme)
        if not mh:
            continue
        slot["fund_weight"] = round(slot["fund_weight"], 2)
        slot["holdings"].sort(key=lambda x: (x["pct"] or 0), reverse=True)
        slot["market_heat"] = mh["heat"]
        slot["market_n_strong"] = mh["n_strong"]
        slot["market_n_total"] = mh["n_total"]
        slot["market_avg_pct"] = mh["avg_pct"]
        slot["score"] = round(mh["heat"] * slot["fund_weight"] / 100.0, 2)
        out.append(slot)

    out = [s for s in out if s["market_heat"] >= min_heat and s["fund_weight"] >= min_weight]
    out.sort(key=lambda s: s["score"], reverse=True)
    return out
