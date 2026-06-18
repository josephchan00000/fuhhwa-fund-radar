"""TWSE / TPEx 即時報價（MIS）連接器 —— 同日盤後即有，補 STOCK_DAY_ALL 晚間批次的時間差。

STOCK_DAY_ALL（openapi）約當日晚間才更新，13:30 收盤後數小時內仍停在前一交易日；
本連接器走交易所即時行情站 `mis.twse.com.tw`（上市/上櫃同一站，前綴 tse_/otc_），
13:30 收盤後即帶當日收盤，讓「貢獻度歸因／同日漲跌」不必等晚間批次。

只回價量（同日收盤 z、昨收 y、開高低、量），純官方即時源；持股權重仍由 etfinfo 提供。
唯讀、盡力而為：取不到的代號回缺、不丟例外。
"""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request

API = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
REFERER = "https://mis.twse.com.tw/stock/index.jsp"
UA = "Mozilla/5.0 (FH-ARM research bot; contact: marketing)"


def _ctx() -> ssl.SSLContext:
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


_CTX = _ctx()


def _num(x) -> float | None:
    try:
        x = str(x).replace(",", "").strip()
        if x in ("", "-"):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _fetch(channels: list[str]) -> list[dict]:
    url = f"{API}?ex_ch={urllib.parse.quote('|'.join(channels))}&json=1&delay=0"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=25, context=_CTX) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return d.get("msgArray", []) or []


def _row(m: dict) -> dict:
    """MIS 單檔 → 正規化價量。z=最近成交(收盤後即收盤價)、y=昨收；z 缺時退回開盤估。"""
    close = _num(m.get("z"))
    if close is None:                       # 尾盤無成交時 z='-' → 退回當日均價/開盤（盡力）
        close = _num(m.get("o"))
    prev = _num(m.get("y"))
    chg = (close - prev) if (close is not None and prev is not None) else None
    pct = round(chg / prev * 100, 2) if (chg is not None and prev) else None
    d = m.get("d")                          # 'YYYYMMDD'
    iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d and len(d) == 8 else None
    return {"code": m.get("c"), "name": (m.get("n") or "").strip(),
            "close": close, "prev_close": prev, "change": chg, "change_pct": pct,
            "volume_lots": int(_num(m.get("v")) or 0),   # MIS v＝累積成交「張」；轉股數需 ×1000
            "date": iso, "time": m.get("t")}


def quotes(codes: list[str], *, chunk: int = 45) -> dict[str, dict]:
    """一批代號 → {code: 正規化價量}。先試上市(tse_)、缺的再試上櫃(otc_)。

    分批請求避免單次 channel 數過多；任一批失敗只略過該批、不影響其餘（盡力而為）。
    """
    out: dict[str, dict] = {}
    uniq = list(dict.fromkeys(c for c in codes if c))
    for pref in ("tse_", "otc_"):
        miss = [c for c in uniq if c not in out]
        if not miss:
            break
        for i in range(0, len(miss), chunk):
            batch = miss[i:i + chunk]
            try:
                rows = _fetch([f"{pref}{c}.tw" for c in batch])
            except Exception:
                continue
            for m in rows:
                r = _row(m)
                if r["code"] and r["close"] is not None:
                    out[r["code"]] = r
    return out


def quote(code: str) -> dict | None:
    return quotes([code]).get(code)
