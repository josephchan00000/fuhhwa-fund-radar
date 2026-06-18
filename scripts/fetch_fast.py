#!/usr/bin/env python3
"""同日盤後求鮮：13:30 收盤後不必等 TWSE 晚間批次，直接灌當日數據（權威源優先）。

痛點：TWSE STOCK_DAY_ALL（pipeline 的價量主源）約當日晚間才更新，收盤後數小時內整條
pipeline 仍停在前一交易日（如 00991A 13:30 收了，傍晚儀表板還是昨天）。

本腳本走「同日即有」的源，**權威優先、落檔即生效、引擎不動**：
  · 市價/成分股當日漲跌 ← TWSE/TPEx 即時(MIS)（官方即時，13:30 收完即有）。
  · NAV/規模/持股權重   ← 復華 FHTrust assetsExcel（**發行商官方**，當日常已可取）；
                          取不到才退回 etfinfo（第三方彙整，Tier B）。
  · 折溢價＝(市價−NAV)/NAV 自算；受益人取自集保 TDCC（holders_history）。
落地：
  · upsert etf_daily / holdings_daily（當日）→ 既有 our_facts/儀表板立即顯示當日。
  · 寫 data/fast/{code}.json 歸因 drop-in → 儀表板「績效歸因 / 持股異動」三卡同日呈現。

數字一律標來源：fhtrust 為官方（A 級）、etfinfo 退回時標 Tier B 待核對。

用法：
  python scripts/fetch_fast.py            # 全主角求鮮（台股型另算成分股歸因）
  python scripts/fetch_fast.py 00991A     # 指定代號
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import attribution, config, db  # noqa: E402
from arm.connectors import etfinfo, fhtrust, twse_mis  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FAST_DIR = ROOT / "data" / "fast"


def _prior_snapshot(conn: sqlite3.Connection, etf: str, before: str) -> tuple[str | None, list[dict]]:
    """前一持股快照 (date, rows)：取 trade_date < 當日的最近一天（同源比較最準）。"""
    pd = conn.execute("SELECT MAX(trade_date) FROM holdings_daily WHERE etf_id=? AND trade_date<?",
                      (etf, before)).fetchone()[0]
    if not pd:
        return None, []
    rows = conn.execute(
        "SELECT stock_id,stock_name,weight,shares FROM holdings_daily WHERE etf_id=? AND trade_date=?",
        (etf, pd)).fetchall()
    return pd, [{"stock_id": r[0], "stock_name": r[1], "weight": r[2], "shares": r[3]} for r in rows]


def _vs_benchmark(holds: list[dict], etf_id: str) -> dict | None:
    """主動度 vs 基準(0050) 拆解：active_share + 基準最大持股(台積電)對比 + 差異化押注。tw_equity 用。"""
    bench = config.product(etf_id).get("benchmark")
    if not bench:
        return None
    try:
        bd = json.loads((ROOT / "config" / "benchmark_0050.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    wb = {h["stock_id"]: (h.get("weight") or 0.0) for h in bd.get("holdings", [])}
    nb = {h["stock_id"]: h.get("stock_name") for h in bd.get("holdings", [])}
    if not wb:
        return None
    tb = sum(wb.values()) or 1
    wb = {c: w / tb * 100 for c, w in wb.items()}
    wf = {h["stock_id"]: (h.get("weight") or 0.0) for h in holds}
    nf = {h["stock_id"]: h.get("stock_name") or h["stock_id"] for h in holds}
    tf = sum(wf.values()) or 1
    wf = {c: w / tf * 100 for c, w in wf.items()}
    AS = round(0.5 * sum(abs(wf.get(i, 0) - wb.get(i, 0)) for i in set(wf) | set(wb)), 1)
    top_b = max(wb, key=lambda c: wb[c])          # 基準最大持股（≈台積電）
    uniq = sorted(((c, nf.get(c, c), round(wf[c], 1)) for c in wf if c not in wb), key=lambda x: -x[2])
    return {
        "benchmark": bench, "benchmark_asof": bd.get("as_of"), "active_share": AS,
        "top_bench": {"code": top_b, "name": nb.get(top_b), "bench_w": round(wb[top_b], 1),
                      "fund_w": round(wf.get(top_b, 0), 1)},
        "unique": [{"code": c, "name": n, "weight": w} for c, n, w in uniq[:5]],
        "n_unique": len(uniq), "unique_weight": round(sum(w for _, _, w in uniq), 1),
    }


def _beneficiaries(conn: sqlite3.Connection, etf: str) -> tuple[int | None, str | None]:
    r = conn.execute("SELECT holders,data_date FROM holders_history WHERE etf_id=? "
                     "ORDER BY data_date DESC LIMIT 1", (etf,)).fetchone()
    return (r[0], r[1]) if r else (None, None)


def _authoritative_snapshot(fund_id: str, date: str):
    """復華官方當日快照（nav/aum/units/holdings）；無則 None。"""
    try:
        return fhtrust.fetch_holdings(fund_id, date)
    except fhtrust.NoData:
        return None
    except Exception:
        return None


def refresh(etf_id: str, conn: sqlite3.Connection) -> dict | None:
    p = config.product(etf_id)
    ac, fund_id = p["asset_class"], p["fund_id"]

    # ── 1) 市價：交易所即時(MIS)，官方、同日 ──
    etf_mis = twse_mis.quote(etf_id)
    date = etf_mis["date"] if etf_mis else None

    # ── 2) NAV/規模/持股：官方(FHTrust) 優先；取不到退回 etfinfo(Tier B) ──
    snap = _authoritative_snapshot(fund_id, date) if date else None
    if snap:
        nav, aum, units = snap["nav"], snap["aum"], snap["units"]
        holds = [{"stock_id": h["stock_id"], "stock_name": h["stock_name"],
                  "weight": h["weight"], "shares": h.get("shares"),
                  "market_value": h.get("market_value")}
                 for h in snap["holdings"] if h.get("kind") != "future"]
        tier, nav_src = "A", "FHTrust assetsExcel（發行商官方）"
        bene = lm = None
    else:
        try:                              # etfinfo 退路：未收錄者（00998A/00986D 上櫃）→ 軟跳過
            lm = etfinfo.latest_market(etf_id)
            hs_e, meta = etfinfo.holdings_fresh(etf_id)
        except RuntimeError as e:
            if "404" in str(e):
                print(f"  – {etf_id} {p['name']}：官方當日 NAV 未更新、etfinfo 未收錄（上櫃 NAV 型）"
                      f"→ 同日市價走 TPEx（fetch_peers 已覆蓋），NAV 維持最近交易日。")
                return None
            raise
        date = date or lm.get("date") or meta.get("as_of")
        if not date:
            print(f"  ✗ {etf_id}：無同日市況/快照，略過")
            return None
        nav, aum = lm.get("nav"), lm.get("aum")
        units = round(aum / nav) if (aum and nav) else None
        holds = [{**h, "market_value": None} for h in hs_e]
        tier, nav_src = "B", "etfinfo latestMarket（第三方彙整，Tier B 待核對）"
        bene = lm.get("beneficiaries")

    # 市價、漲跌、折溢價（折溢價以官方 NAV 自算，最準）
    price = (etf_mis or {}).get("close") or (lm.get("price") if not snap else None)
    etf_ret = (etf_mis or {}).get("change_pct")
    if etf_ret is None and not snap and lm.get("price") and lm.get("change"):
        prev = lm["price"] - lm["change"]
        etf_ret = round(lm["change"] / prev * 100, 2) if prev else None
    prem = round((price - nav) / nav * 100, 2) if (price and nav) else (None if snap else lm.get("premium"))
    vol_shares = (etf_mis["volume_lots"] * 1000) if etf_mis else None   # MIS 張 → 股

    # 受益人：集保 TDCC 官方（與「受益人」切點同源）；官方快照無附受益人時用之
    if bene is None:
        bene, _bdate = _beneficiaries(conn, etf_id)

    # ── 3) 落 etf_daily / holdings_daily（當日；close/change/prem 一律小數，與 pipeline 對齊）──
    db.upsert(conn, "etf_daily", {
        "etf_id": etf_id, "trade_date": date, "close": price,
        "change_pct": (etf_ret / 100) if etf_ret is not None else None,
        "nav": nav, "premium_disc": (prem / 100) if prem is not None else None,
        "aum": aum, "units": units, "volume": vol_shares,
        "src_price": "TWSE 即時(MIS) 官方收盤" if etf_mis else "etfinfo latestMarket",
        "src_nav": nav_src})
    prev_date, prior = _prior_snapshot(conn, etf_id, date)
    for h in holds:
        db.upsert(conn, "holdings_daily", {
            "etf_id": etf_id, "trade_date": date, "stock_id": h["stock_id"],
            "stock_name": h["stock_name"], "shares": h.get("shares"),
            "market_value": h.get("market_value"), "weight": h["weight"]})
    conn.commit()

    out = {
        "etf_id": etf_id, "name": p["name"], "as_of": date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tier": tier,
        "provenance": (f"市價/成分股漲跌＝TWSE 即時(MIS) 官方；NAV/規模/持股＝{nav_src}；"
                       f"折溢價＝(市價−NAV)/NAV 自算。"),
        "market": {"price": price, "nav": nav, "change_pct": etf_ret,
                   "premium": prem, "aum": aum, "beneficiaries": bene,
                   "volume_shares": vol_shares},
        "holdings_diff": attribution.holdings_diff(prior, [
            {"stock_id": h["stock_id"], "stock_name": h["stock_name"], "weight": h["weight"],
             "shares": h.get("shares")} for h in holds]),
        "holdings_diff_note": (f"與前一快照 {prev_date} 比較（同源）" if prior else "首次快照，明日起可比較"),
    }
    out["holdings_diff"]["prev_date"] = prev_date
    out["holdings_diff"]["date"] = date

    # ── 4) 台股型：成分股即時漲跌 → 績效歸因（貢獻度）──
    if ac == "tw_equity" and holds:
        q = twse_mis.quotes([h["stock_id"] for h in holds])
        out["attribution"] = attribution.compute(holds, q, top=10, etf_ret=etf_ret)
        out["attribution_priced"] = f"{out['attribution']['n_priced']}/{out['attribution']['n_total']}"
        out["vs_bench"] = _vs_benchmark(holds, etf_id)   # 主動度 vs 0050 拆解

    FAST_DIR.mkdir(parents=True, exist_ok=True)
    (FAST_DIR / f"{etf_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _print(o: dict) -> None:
    m = o["market"]
    cp = f"{m['change_pct']:+.2f}%" if m["change_pct"] is not None else "—"
    ben = f"　受益人 {m['beneficiaries']:,}" if m.get("beneficiaries") else ""
    tier = "官方" if o["tier"] == "A" else "Tier B(etfinfo)"
    print(f"  ✓ {o['etf_id']} {o['name']}（as-of {o['as_of']}・{tier}）")
    print(f"      市價 {m['price']} {cp}　NAV {m['nav']}　折溢價 {m['premium']}%　"
          f"規模 {(m['aum'] or 0)/1e8:.0f} 億{ben}")
    d = o["holdings_diff"]
    if d["cuts"] or d["adds"]:
        adds = "、".join(f"{x['name']} {x['delta']:+.2f}%" for x in d["adds"][:3])
        cuts = "、".join(f"{x['name']} {x['delta']:+.2f}%" for x in d["cuts"][:3])
        print(f"      持股異動：加碼[{adds or '—'}]　減碼[{cuts or '—'}]")
    a = o.get("attribution")
    if a:
        print(f"      績效歸因（成分 {o['attribution_priced']}，ETF當日 {a['etf_ret']:+.2f}%，"
              f"成分貢獻合計 {a['est_ret']:+.2f}%）推漲 Top3：")
        for r in a["up_top"]:
            print(f"        {r['code']} {r['name'][:6]} {r['change_pct']:+.2f}% ×權重{r['weight']}% "
                  f"→ 對ETF {r['contrib']:+.2f}%（佔{r['share']}%）")


def main() -> None:
    codes = sys.argv[1:] or [p["id"] for p in config.load()["fh_products"]]
    conn = db.connect()
    print(f"[同日求鮮 ← 官方即時(MIS) + FHTrust 官方 NAV/持股]　{datetime.now():%Y-%m-%d %H:%M}")
    for code in codes:
        try:
            o = refresh(code, conn)
        except Exception as e:
            print(f"  ✗ {code}：求鮮失敗（{type(e).__name__}：{e}）")
            continue
        if o:
            _print(o)
    conn.close()


if __name__ == "__main__":
    main()
