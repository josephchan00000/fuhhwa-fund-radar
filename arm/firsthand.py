"""第一手數據讀取層 —— 直接讀 arm.db + config/competitor_holdings，供儀表板算『數據驅動切點』。

提供三組事實（皆來自第一手：TWSE 官方價量、FHTrust 持股、pipeline signals）：
  · our_facts(etf)        本檔今日 收/漲跌%/量/AUM/週增/受益人 + 持股加減碼 delta + signals。
  · peer_table(date)      同類主動ETF + 0050 當日量能/漲跌排行（peer_quotes，scripts/fetch_peers.py 灌）。
  · competitor_scan()     各競品 issuer + 今日價量(rank) + 重壓/獨門題材（持股快照）。

唯讀；缺資料就回 None/空，不丟例外。數字皆第一手、可回溯；競品 AUM TWSE 無→標待補。
"""
from __future__ import annotations

import bisect
import sqlite3
from datetime import date as _date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "arm.db"
CHOLD = ROOT / "config" / "competitor_holdings"

ISSUER_OF = {
    "00980A": "野村", "00985A": "野村", "00981A": "統一", "00403A": "統一",
    "00982A": "群益", "00992A": "群益", "00990A": "元大", "0050": "元大",
    "00991A": "復華", "00998A": "復華", "00986D": "復華",
}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _q(c, sql, args=()):
    try:
        return list(c.execute(sql, args))
    except sqlite3.Error:
        return []


def _holdings_delta(c, etf: str) -> dict:
    ds = [r[0] for r in _q(c, "SELECT DISTINCT trade_date FROM holdings_daily "
                              "WHERE etf_id=? ORDER BY trade_date", (etf,))]
    if len(ds) < 2:
        return {"adds": [], "cuts": [], "new": [], "prev_date": None, "date": ds[-1] if ds else None}
    a, b = ds[-2], ds[-1]
    prev = {r["stock_name"]: r["weight"] for r in _q(c,
            "SELECT stock_name,weight FROM holdings_daily WHERE etf_id=? AND trade_date=?", (etf, a))}
    cur = _q(c, "SELECT stock_name,weight FROM holdings_daily WHERE etf_id=? AND trade_date=?", (etf, b))
    moves, new = [], []
    for r in cur:
        nm, w = r["stock_name"], r["weight"]
        if nm in prev:
            moves.append((nm, round(w - prev[nm], 2)))
        elif w >= 0.3:
            new.append((nm, round(w, 2)))
    adds = sorted([m for m in moves if m[1] >= 0.05], key=lambda x: -x[1])[:6]
    cuts = sorted([m for m in moves if m[1] <= -0.05], key=lambda x: x[1])[:4]
    return {"adds": adds, "cuts": cuts, "new": sorted(new, key=lambda x: -x[1])[:4],
            "prev_date": a, "date": b}


def our_facts(etf: str) -> dict:
    c = _conn()
    out: dict = {"etf": etf}
    row = _q(c, "SELECT * FROM etf_daily WHERE etf_id=? ORDER BY trade_date DESC LIMIT 1", (etf,))
    if row:
        r = row[0]
        out.update(date=r["trade_date"], close=r["close"], change_pct=r["change_pct"],
                   volume=r["volume"], aum=r["aum"], units=r["units"], premium=r["premium_disc"])
    # 市價優先：00998A/00986D 為上櫃，pipeline 走 TWSE 抓不到 → 用 peer_quotes 的 TPEx 當日市價補。
    # （change_pct 在 peer_quotes 存「百分比數」，etf_daily 存「小數」→ 補進時除 100 對齊。）
    mq = _q(c, "SELECT trade_date,close,change_pct,volume FROM peer_quotes "
               "WHERE code=? ORDER BY trade_date DESC LIMIT 1", (etf,))
    if mq and mq[0]["close"] is not None:
        out["mkt_date"] = mq[0]["trade_date"]
        if out.get("close") is None:              # pipeline 無市價（上櫃檔）→ 以 TPEx 市價為準
            out["close"] = mq[0]["close"]
            out["change_pct"] = (mq[0]["change_pct"] / 100) if mq[0]["change_pct"] is not None else None
            out["volume"] = mq[0]["volume"]
            out["price_src"] = "TPEx 上櫃市價"
    # 規模週增（nav_history AUM）
    aum_rows = _q(c, "SELECT trade_date,aum FROM nav_history WHERE etf_id=? ORDER BY trade_date", (etf,))
    if len(aum_rows) >= 6 and aum_rows[-1]["aum"] and aum_rows[-6]["aum"]:
        now, prev = aum_rows[-1]["aum"], aum_rows[-6]["aum"]
        out["aum_chg_1w"] = round((now / prev - 1) * 100, 1) if prev else None
    # 受益人
    h = _q(c, "SELECT data_date,holders FROM holders_history WHERE etf_id=? ORDER BY data_date DESC LIMIT 1", (etf,))
    if h:
        out["holders"] = h[0]["holders"]; out["holders_date"] = h[0]["data_date"]
    # 持股加減碼
    out["delta"] = _holdings_delta(c, etf)
    # signals（最新交易日）
    sd = _q(c, "SELECT MAX(trade_date) d FROM signals WHERE etf_id=?", (etf,))
    if sd and sd[0]["d"]:
        out["signals"] = [{"detector": s["detector"], "headline": s["headline"], "evidence": s["evidence"]}
                          for s in _q(c, "SELECT detector,headline,evidence FROM signals "
                                         "WHERE etf_id=? AND trade_date=? ORDER BY score DESC", (etf, sd[0]["d"]))]
    else:
        out["signals"] = []
    # 同類量能排名（限本檔的競品群）
    pt = peer_table_conn(c, etf)
    if pt:
        ranks = {p["code"]: i for i, p in enumerate(pt, 1)}
        out["vol_rank"] = ranks.get(etf)
        out["peer_n"] = len(pt)
    c.close()
    return out


def _peer_groups() -> dict:
    import json
    try:
        return json.loads((ROOT / "config" / "peer_groups.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def peer_group(etf: str) -> list[str]:
    """該主角的競品代號清單（含 0050 基準）；未定義回 []。"""
    return ((_peer_groups().get("groups") or {}).get(etf)) or []


def peer_table_conn(c, etf: str | None = None) -> list[dict]:
    """各檔取「自己最新的一筆」報價（上市/上櫃更新時點不同 → 各代號日期可不同）。

    上櫃(TPEx)當日約 16:00 就有、上市(TWSE)要等晚間；若用全表單一 MAX(date) 會把
    尚停在前一交易日的上市檔整批濾掉。故改成 per-code 最新，並帶 trade_date 供前端標當日。
    """
    rows = _q(c, "SELECT code,name,issuer,close,change_pct,volume,trade_date FROM peer_quotes pq "
                 "WHERE trade_date=(SELECT MAX(trade_date) FROM peer_quotes WHERE code=pq.code) "
                 "ORDER BY volume DESC")
    out = [{"code": r["code"], "name": r["name"], "issuer": r["issuer"],
            "close": r["close"], "change_pct": r["change_pct"], "volume": r["volume"],
            "trade_date": r["trade_date"]} for r in rows]
    if etf:                                       # 只留本檔 + 其競品群
        keep = set(peer_group(etf)) | {etf}
        out = [p for p in out if p["code"] in keep]
    return out


def peer_table(etf: str | None = None) -> list[dict]:
    c = _conn(); out = peer_table_conn(c, etf); c.close(); return out


def _load_competitor_holdings() -> dict:
    import json
    out = {}
    for f in sorted(CHOLD.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("holdings"):
            out[d.get("fund_id", f.stem)] = d
    return out


def competitor_scan(etf: str | None = None) -> list[dict]:
    """該主角各競品：issuer + 今日價量(同群排名) + 重壓前3/集中度（持股有才有）。"""
    issuer_map = _peer_groups().get("issuer", {})
    pt_rows = peer_table(etf)
    pt = {p["code"]: p for p in pt_rows}
    rank = {p["code"]: i for i, p in enumerate(pt_rows, 1)}
    holds = _load_competitor_holdings()
    codes = peer_group(etf) if etf else list(holds.keys())
    out = []
    for code in codes:
        if code == "0050" or code == etf:         # 基準/本檔不列為競品卡
            continue
        q = pt.get(code)
        h = holds.get(code)
        top3 = [{"name": x["stock_name"], "w": x["weight"]} for x in h["holdings"][:3]] if h else []
        top10 = round(sum(x["weight"] for x in h["holdings"][:10]), 1) if h else None
        out.append({
            "code": code, "name": q["name"] if q else "",
            "issuer": (h.get("issuer") if h else None) or issuer_map.get(code, ISSUER_OF.get(code, "")),
            "as_of": (h.get("as_of") if h else "") or "",
            "close": q["close"] if q else None,
            "change_pct": q["change_pct"] if q else None,
            "volume": q["volume"] if q else None,
            "vol_rank": rank.get(code),
            "top3": top3, "top10_conc": top10, "n_holdings": (len(h["holdings"]) if h else 0),
            "no_quote": q is None,
        })
    out.sort(key=lambda x: (x["volume"] or 0), reverse=True)
    return out


def _perf_bench(etf: str) -> list[str]:
    """多週期報酬要對打的同類清單（config/peer_groups.json:perf_bench）；未設定回 []。

    只有明確設定 perf_bench 的主角（目前 00991A）才出多週期對打表；其餘（如上櫃 NAV/
    價量序列僅數日的 00998A/00986D）不硬湊一張薄表。
    """
    return ((_peer_groups().get("perf_bench") or {}).get(etf)) or []


def _close_at(dates: list[str], cmap: dict[str, float], target: str, tol_days: int = 6):
    """回傳 target 當日或之前最近一筆收盤；若最近一筆距 target > tol_days（資料有斷層）回 None。

    用「日期對位」而非位置位移：跨檔成立日不同、且 TWSE 單檔 STOCK_DAY 對部分新檔近月會缺，
    位置位移會把「上一筆」誤當成「N 日前」。日期對位 + 容差能在缺料時誠實降級成 None。
    """
    i = bisect.bisect_right(dates, target) - 1
    if i < 0:
        return None
    d = dates[i]
    if (_date.fromisoformat(target) - _date.fromisoformat(d)).days > tol_days:
        return None
    return cmap[d]


def perf_periods(etf: str = "00991A") -> dict | None:
    """多週期市價報酬：本檔 vs 多個同類（不只 0050）vs 超額（本檔−主動同類均）。

    對手清單來自 peer_groups.json:perf_bench（如 00991A → 0050 + 統一00981A/00403A + 群益00992A）。
    序列＝price_history ∪ 累積的 peer_quotes（STOCK_DAY_ALL 每日快照，可靠且逐日累積），
    深層歷史不足再以 TWSE 單檔逐日回補。報酬一律以「本檔交易日曆」為基準、按日期對位計算，
    對手在某期間無對應資料即誠實顯示「—」。僅有價格歷史的台股檔可算；NAV 型回 None。含息以月報為準。
    """
    from .connectors import twse
    benches = _perf_bench(etf)
    if not benches:                  # 未設 perf_bench 的主角不出多週期對打表
        return None
    c = _conn()
    issuer_map = _peer_groups().get("issuer", {})

    def db_series(code) -> list[tuple[str, float]]:
        m: dict[str, float] = {}
        for r in _q(c, "SELECT trade_date,close FROM price_history WHERE code=? ORDER BY trade_date", (code,)):
            if r["close"] is not None:
                m[r["trade_date"]] = r["close"]
        for r in _q(c, "SELECT trade_date,close FROM peer_quotes WHERE code=? ORDER BY trade_date", (code,)):
            if r["close"] is not None:
                m.setdefault(r["trade_date"], r["close"])    # 已有(price_history)優先，否則用 peer_quotes
        return sorted(m.items())

    a = db_series(etf)
    if len(a) < 2:
        c.close()
        return None
    a_dates = [d for d, _ in a]
    a_map = dict(a)
    start, latest = a_dates[0], a_dates[-1]

    series: dict[str, tuple[list[str], dict[str, float]]] = {}
    last_chg: dict[str, tuple[str, float]] = {}      # 各對手最新一筆官方當日漲跌率(%)，供近1日斷層補值
    for b in benches:
        s = db_series(b)
        if not s or s[0][0] > "2026-01-05":          # 深層歷史不足 → TWSE 單檔逐日回補過去（近月以快照為準）
            try:
                m = {d: px for d, px, _ in twse.fetch_history(b, start, latest)}
            except Exception:
                m = {}
            for d, px in s:                            # peer_quotes/price_history 覆蓋（較新、可靠）
                m[d] = px
            s = sorted(m.items())
        s = [(d, p) for d, p in s if d >= start and p]
        if len(s) >= 2:
            series[b] = ([d for d, _ in s], dict(s))
        pq = _q(c, "SELECT trade_date,change_pct FROM peer_quotes WHERE code=? "
                   "ORDER BY trade_date DESC LIMIT 1", (b,))
        if pq and pq[0]["change_pct"] is not None:
            last_chg[b] = (pq[0]["trade_date"], pq[0]["change_pct"])
    c.close()

    def period_ret(dates, cmap, end_d, start_d):
        e = _close_at(dates, cmap, end_d)
        b0 = _close_at(dates, cmap, start_d)
        return (e / b0 - 1) if (e and b0) else None

    def n_back(n):
        return a_dates[-1 - n] if len(a_dates) > n else None

    # 年初以來(YTD)：以前一年最後交易日（≤ {year-1}-12-31）收盤為基準（標準 YTD 口徑）
    year = int(latest[:4])
    ytd_base = next((d for d in reversed(a_dates) if d <= f"{year - 1}-12-31"), None)
    specs = [("近1日", n_back(1)), ("近1週", n_back(5)), ("近1月", n_back(20)),
             ("近3月", n_back(60)), ("年初以來", ytd_base), (f"{etf} 成立以來", start)]
    pct = lambda v: round(v * 100, 2) if v is not None else None
    rows = []
    for label, sd in specs:
        if sd is None:
            continue
        ea = period_ret(a_dates, a_map, latest, sd)
        if ea is None:
            continue
        vals = {b: pct(period_ret(dts, cm, latest, sd)) for b, (dts, cm) in series.items()}
        if label == "近1日":                          # 連續序列有斷層(如00981A六月缺)→ 用當日官方漲跌率補
            for b in series:
                d_chg = last_chg.get(b)
                if vals.get(b) is None and d_chg and d_chg[0] == latest:  # 須為本檔近1日同一收盤日，口徑才一致
                    vals[b] = round(d_chg[1], 2)
        actives = [vals[b] for b in series if b != "0050" and vals[b] is not None]
        pm = round(sum(actives) / len(actives), 2) if actives else None
        rows.append({"period": label, "etf": pct(ea), "vals": vals,
                     "peer_mean": pm, "excess": (round(pct(ea) - pm, 2) if pm is not None else None)})
    benches_meta = [{"code": b, "label": b, "issuer": issuer_map.get(b, ""), "is_index": b == "0050"}
                    for b in benches if b in series]
    return {"as_of": latest, "benches": benches_meta, "rows": rows, "peer_mean_label": "主動同類均"}
