"""績效歸因（同日）—— 用『持股權重 × 成分股當日漲跌』算每檔對 ETF 的貢獻度。

對應儀表板三張同日卡：
  · 推漲 Top3 / 下跌 Top3   ：當日貢獻最大的正/負成分股（含「佔當日漲幅 %」）。
  · 貢獻度排行（前 N）       ：依貢獻度大小排序的成分股長條。
  · 最新持股異動            ：兩日持股快照的權重差（減碼/加碼/新進）。

貢獻度（百分點）＝ 權重% × 個股漲跌% ÷ 100；ETF 當日估算漲幅＝各成分貢獻度加總
（僅以成分股估、未計現金/折溢價/成分異動，故標『估算』）。資料源：etfinfo 權重（Tier B）
＋ TWSE/TPEx 即時(MIS) 當日漲跌（官方即時）。純計算、無 I/O。
"""
from __future__ import annotations


def _contrib(weight: float | None, pct: float | None) -> float | None:
    if weight is None or pct is None:
        return None
    return round(weight * pct / 100.0, 4)


def compute(holdings: list[dict], quotes: dict[str, dict], *,
            top: int = 10, etf_ret: float | None = None) -> dict:
    """holdings:[{stock_id,stock_name,weight,...}] + quotes:{code:{change_pct,close,...}} → 歸因。

    `etf_ret`：ETF 當日實際漲跌%（etfinfo/即時市價）；給了就用它當「佔當日漲幅」分母與頭條淨報酬，
    否則退回成分股貢獻合計（est_ret）。回傳 {as_of, etf_ret, est_ret, n_priced, n_total,
    rows[], up_top[], down_top[], ranking[]}。rows/ranking 依貢獻度排序。
    """
    rows = []
    for h in holdings:
        code = h.get("stock_id")
        q = quotes.get(code) or {}
        pct = q.get("change_pct")
        w = h.get("weight")
        c = _contrib(w, pct)
        rows.append({
            "code": code, "name": h.get("stock_name") or q.get("name") or code,
            "weight": round(w, 2) if w is not None else None,
            "change_pct": pct, "close": q.get("close"),
            "contrib": c, "priced": pct is not None,
        })
    priced = [r for r in rows if r["contrib"] is not None]
    raw_sum = sum(r["contrib"] for r in priced) if priced else None
    est_ret = round(raw_sum, 2) if raw_sum is not None else None
    # 「佔當日漲幅」分母：優先用 ETF 實際當日報酬（截圖口徑），無則退回成分股貢獻合計（未取整，避免單檔>100%）。
    denom = etf_ret if (etf_ret not in (None, 0)) else raw_sum
    for r in priced:
        r["share"] = (round(r["contrib"] / denom * 100) if denom else None)
    by_contrib = sorted(priced, key=lambda r: r["contrib"], reverse=True)
    up_top = [r for r in by_contrib if r["contrib"] > 0][:3]
    down_top = [r for r in reversed(by_contrib) if r["contrib"] < 0][:3]
    # 貢獻度排行：正貢獻前 top + 負貢獻最低數檔（與截圖一致，正多負少）
    pos = [r for r in by_contrib if r["contrib"] > 0][:top]
    neg = [r for r in by_contrib if r["contrib"] < 0][-2:]
    ranking = pos + [r for r in neg if r not in pos]
    return {
        "as_of": next((q.get("date") for q in quotes.values() if q.get("date")), None),
        "etf_ret": etf_ret, "est_ret": est_ret,
        "n_priced": len(priced), "n_total": len(rows),
        "rows": rows, "up_top": up_top, "down_top": down_top, "ranking": ranking,
    }


def holdings_diff(prev: list[dict], cur: list[dict], *,
                  add_floor: float = 0.05, new_floor: float = 0.3) -> dict:
    """兩快照差異 → {adds, cuts, new, exits}。每筆帶『權重昨→今(+變化pp)』與『張數昨→今(+變化)』。

    prev/cur:[{stock_id,stock_name,weight,shares}]；shares 為股數（張＝股/1000）。
    分類仍以權重變化(百分點)為準（與原口徑一致）；另附 prev_shares/shares/share_delta 供顯示實際部位。
    %（pp）＝今日權重−昨日權重，含『價格漲跌』與『張數加減碼』兩種因素。
    """
    pmap = {h["stock_id"]: h for h in prev}
    moves, new = [], []
    seen = set()

    def _rec(sid, nm, w, pw, sh, psh):
        return {"code": sid, "name": nm, "delta": round(w - pw, 2),
                "weight": round(w, 2), "prev_weight": round(pw, 2),
                "shares": sh, "prev_shares": psh,
                "share_delta": (sh - psh) if (sh is not None and psh is not None) else None}

    for h in cur:
        sid, nm = h["stock_id"], h.get("stock_name") or h["stock_id"]
        w, sh = (h.get("weight") or 0.0), h.get("shares")
        seen.add(sid)
        if sid in pmap:
            moves.append(_rec(sid, nm, w, (pmap[sid].get("weight") or 0.0), sh, pmap[sid].get("shares")))
        elif w >= new_floor:
            new.append(_rec(sid, nm, w, 0.0, sh, 0))
    exits = [_rec(h["stock_id"], h.get("stock_name") or h["stock_id"], 0.0,
                  (h.get("weight") or 0.0), 0, h.get("shares"))
             for h in prev if h["stock_id"] not in seen and (h.get("weight") or 0.0) >= new_floor]
    adds = sorted([m for m in moves if m["delta"] >= add_floor], key=lambda x: -x["delta"])
    cuts = sorted([m for m in moves if m["delta"] <= -add_floor], key=lambda x: x["delta"])
    return {"adds": adds, "cuts": cuts,
            "new": sorted(new, key=lambda x: -x["delta"]),
            "exits": sorted(exits, key=lambda x: x["delta"])}
