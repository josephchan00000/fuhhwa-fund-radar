#!/usr/bin/env python3
"""抓同類ETF + 基準當日價量 → arm.db 的 peer_quotes 表（第一手競品數據源）。

來源（兩個交易所合併，皆官方、免金鑰、走 arm.http certifi 驗證）：
  · TWSE openapi STOCK_DAY_ALL  —— 上市股票/ETF（00991A 台股同類、0050、高股息ETF…）。
  · TPEx openapi 上櫃每日收盤    —— 上櫃 ETF（00998A/00986D 復華自家 + 債券競品 00679B…）。
上櫃優先覆蓋（自家兩檔與債券ETF僅上櫃有），同代號以 TWSE 為主、TPEx 補缺。
僅存價量（收盤/漲跌/漲跌幅/成交量）；競品 AUM/規模兩所皆無，持股待 etfinfo 另接。
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm.connectors import tpex, twse  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "arm.db"

# 各主角的競品清單 + 發行商，集中在 config/peer_groups.json（各檔各比各的）
_pg = json.loads((ROOT / "config" / "peer_groups.json").read_text(encoding="utf-8"))
ISSUER = _pg.get("issuer", {})
# 要抓的全部代號＝本家 3 檔 + 各群競品（去重）
PEERS = {c: ISSUER.get(c, "") for c in ["00991A", "00998A", "00986D"]}
for grp in (_pg.get("groups") or {}).values():
    for c in grp:
        PEERS.setdefault(c, ISSUER.get(c, ""))

DDL = """CREATE TABLE IF NOT EXISTS peer_quotes(
  code TEXT, trade_date TEXT, name TEXT, issuer TEXT,
  close REAL, change REAL, change_pct REAL, volume INTEGER,
  PRIMARY KEY(code, trade_date))"""


def _merged_quotes() -> dict[str, dict]:
    """合併 TWSE（上市）+ TPEx（上櫃）當日價量；TWSE 為主、TPEx 補缺。

    上櫃端取不到（網路/維護）不致命 → 印警告續跑，上市資料照灌。
    """
    allt = twse.fetch_today_all()
    try:
        tpx = tpex.fetch_today_all()
    except Exception as e:
        print(f"  ⚠ TPEx 上櫃價量取得失敗（{type(e).__name__}）→ 僅用 TWSE；改由即時(MIS) 補上櫃")
        tpx = {}
    for code, d in tpx.items():           # 上市沒有的（上櫃 ETF）才補
        allt.setdefault(code, d)
    return allt


def _mis_topup(allt: dict, codes: list[str]) -> int:
    """官方批次(STOCK_DAY_ALL/TPEx)傍晚才更新；收盤後先用即時(MIS) 把 PEERS 補到當日。

    對每個 peer 代號：若 allt 無資料或日期落後 MIS 當日 → 以 MIS（官方即時收盤）覆蓋。
    回傳補了幾檔。MIS 量為『張』→ 轉股數 ×1000，與 STOCK_DAY 對齊。
    """
    from arm.connectors import twse_mis
    try:
        q = twse_mis.quotes(codes)
    except Exception as e:
        print(f"  ⚠ 即時(MIS) 補值失敗（{type(e).__name__}）→ 沿用官方批次（可能仍為前一交易日）")
        return 0
    n = 0
    for code, m in q.items():
        cur = allt.get(code)
        if (not cur) or (cur.get("date") or "") < (m["date"] or ""):   # MIS 較新才覆蓋
            allt[code] = {"date": m["date"], "name": m["name"], "close": m["close"],
                          "change": m["change"], "volume": (m["volume_lots"] or 0) * 1000}
            n += 1
    return n


def main() -> None:
    allt = _merged_quotes()
    topped = _mis_topup(allt, list(PEERS))      # 收盤後即時補當日（含上市/上櫃 peer）
    if topped:
        print(f"  ⚡ 即時(MIS) 補當日 {topped} 檔（官方批次未更新時，peer 仍到當日）")
    conn = sqlite3.connect(DB)
    conn.execute(DDL)
    n = 0
    for code, issuer in PEERS.items():
        d = allt.get(code)
        if not d or d["close"] is None:
            print(f"  ⚠ {code}：當日無資料，略過")
            continue
        chg = d.get("change")
        prev = (d["close"] or 0) - (chg or 0)
        pct = round((chg / prev) * 100, 2) if (chg is not None and prev) else None
        conn.execute(
            "INSERT OR REPLACE INTO peer_quotes VALUES(?,?,?,?,?,?,?,?)",
            (code, d["date"], d["name"], issuer, d["close"], chg, pct, d["volume"]))
        n += 1
    conn.commit()
    date = max(v["date"] for v in allt.values())
    # 各代號取自己最新一筆（上市/上櫃日期可不同）→ 量能排行，並標各自交易日。
    rows = conn.execute(
        "SELECT code,name,issuer,close,change_pct,volume,trade_date FROM peer_quotes pq "
        "WHERE trade_date=(SELECT MAX(trade_date) FROM peer_quotes WHERE code=pq.code) "
        "ORDER BY volume DESC").fetchall()
    conn.close()
    print(f"✅ peer_quotes 已更新 {n} 檔（最新交易日 {date}）　量能排行：")
    for i, (c, nm, iss, cl, pct, vol, td) in enumerate(rows, 1):
        flag = " ★今日" if td == date else f" ({td})"
        ps = f"{pct:+.2f}%" if pct is not None else "  —  "
        print(f"  {i:2}. {c} {nm}（{iss}） 收{cl} {ps} 量{vol:,}{flag}")


if __name__ == "__main__":
    main()
