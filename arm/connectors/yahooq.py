"""Yahoo Finance 海外個股報價（ETF 持股「當日漲跌／貢獻」的海外補源，2026-08-05 使用者需求）。

全球型 ETF（00402A 美股、00988A/00990A 全球、00998A 全球金融股）的海外持股原本沒有
報價來源，當日漲跌與貢獻整片顯示 —（誠實降級）。本連接器以 Yahoo v8 chart API
（與 factcheck.yahoo_index_series／etfwatch 報酬序列同一端點，CI 可達性已被證實數月）
逐檔補上「最近收盤、與前一交易日的漲跌」。

輸出格式對齊 twse/tpex.fetch_today_all（close/change/…），可直接併入 annotate 的
quotes——但**多帶 `ccy` 幣別欄**：外幣收盤 × 股數不可與台幣金額混入同一張方塊圖
比面積（USD/JPY/KRW 不同幣別根本不可比），`etfholdings._moves` 據此欄不算海外金額，
面積照舊退回股數口徑；漲跌％與貢獻（pp）是比率、跨市場可比，照補。

代號為彭博式「TICKER 交易所碼」（'NVDA US'／'6981 JP'／'009150 KS'）——對照表
`_BBG2Y` 轉 Yahoo 尾碼；不在表上的交易所跳過（寧缺勿錯，顯示 — 不補假值）。
債券 ISIN（US83368TBT43，無空格）不符樣式、自然跳過（Yahoo 無公司債逐檔報價）。

本容器 proxy 擋 Yahoo —— 只在正式區 CI 有意義；容器內呼叫全數快速失敗、回空 dict。
"""
from __future__ import annotations

import re
import urllib.parse

from ..http import get_json

# 彭博交易所碼 → Yahoo 尾碼（只列實際出現過＋常見者；未知碼跳過、不猜）
_BBG2Y = {
    "US": "", "UN": "", "UW": "", "UQ": "", "UA": "",     # 美國（NYSE/Nasdaq 等合併碼）
    "JP": ".T", "JT": ".T",                                # 東京
    "KS": ".KS", "KP": ".KS",                              # 韓國（彭博 KP＝KOSPI；KOSDAQ 為 .KQ，見補試）
    "GY": ".DE", "GR": ".DE",                              # 德國（Xetra）
    "LN": ".L",                                            # 倫敦
    "FP": ".PA",                                           # 巴黎
    "NA": ".AS",                                           # 阿姆斯特丹
    "GA": ".AT",                                           # 雅典
    "HK": ".HK",                                           # 香港
    "SW": ".SW", "SE": ".SW",                              # 瑞士
    "IM": ".MI",                                           # 米蘭
    "SM": ".MC",                                           # 馬德里
    "SS": ".ST",                                           # 斯德哥爾摩（彭博 SS＝瑞典）
    "NO": ".OL",                                           # 奧斯陸
    "DC": ".CO",                                           # 哥本哈根
    "FH": ".HE",                                           # 赫爾辛基
    "AV": ".VI",                                           # 維也納
    "BB": ".BR",                                           # 布魯塞爾
    "PL": ".LS",                                           # 里斯本
    "ID": ".IR",                                           # 都柏林
    "AU": ".AX", "AT": ".AX",                              # 澳洲
    "SP": ".SI",                                           # 新加坡
    "CN": ".TO", "CT": ".TO",                              # 加拿大（TSX）
}

_FOREIGN_RE = re.compile(r"^([A-Z0-9/.\-]+)\s+([A-Z]{2})$")


def to_yahoo(sid: str) -> str | None:
    """'NVDA US'→'NVDA'、'6981 JP'→'6981.T'、'BRK/B US'→'BRK-B'、'AV/ LN'→'AV.L'、
    '300408 CH'→'300408.SZ'；不符樣式／未知交易所回 None。"""
    m = _FOREIGN_RE.match(str(sid or "").strip())
    if not m:
        return None
    tick, exch = m.groups()
    # 尾斜線＝彭博的普通股類別記號（Aviva 'AV/'）——Yahoo 不帶，直接剝掉；
    # 中段斜線＝股份類別（'BRK/B'）——Yahoo 用 '-'
    tick = tick.rstrip("/").replace("/", "-").replace(".", "-")
    if not tick:
        return None
    # 中國 A 股（彭博 CH 綜合／CG 深圳／CS 上海）：Yahoo 依市場分 .SS／.SZ——
    # 6/9 開頭＝上海、其餘（0/3 開頭）＝深圳
    if exch in ("CH", "CG", "CS"):
        return tick + (".SS" if tick[:1] in "69" else ".SZ")
    suf = _BBG2Y.get(exch)
    if suf is None:
        return None
    return tick + suf


def _last_two_closes(sym: str) -> tuple[float, float, str | None] | None:
    """→ (最近收盤, 前一交易日收盤, 幣別)；資料不足回 None。"""
    try:
        doc = get_json("https://query1.finance.yahoo.com/v8/finance/chart/"
                       f"{urllib.parse.quote(sym)}?range=5d&interval=1d", cache_ttl=1800)
        res = doc["chart"]["result"][0]          # type: ignore[index]
        closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
        ccy = (res.get("meta") or {}).get("currency")
    except Exception:
        return None
    if len(closes) < 2:
        return None
    return float(closes[-1]), float(closes[-2]), ccy


def fetch_foreign_quotes(sids: set[str]) -> dict[str, dict]:
    """海外持股報價 → {原始代號: {close, change, ccy, name, volume}}（與 fetch_today_all 同構）。

    change＝最近收盤 − 前一交易日收盤（Yahoo 序列自算，同一來源口徑一致）。
    抓不到的檔跳過（該持股維持 —）；KS 抓不到時補試 .KQ（KOSDAQ）。
    ⚠ 不看日期、會收到盤中價（見 fetch_foreign_on）——ETF 持股詳情已改用 fetch_foreign_on。
    """
    out: dict[str, dict] = {}
    for sid in sorted(sids):
        sym = to_yahoo(sid)
        if not sym:
            continue
        got = _last_two_closes(sym)
        if got is None and sym.endswith(".KS"):           # 韓股兩板：KOSPI 抓不到試 KOSDAQ
            got = _last_two_closes(sym[:-3] + ".KQ")
        if got is None:
            continue
        close, prev, ccy = got
        out[sid] = {"close": round(close, 4), "change": round(close - prev, 4),
                    "ccy": ccy or "USD", "name": "", "volume": 0}
    return out


# ── 指定日期、已收盤（ETF 持股詳情；2026-10-21 使用者：「漲跌幅是錯的」） ──────────────
#
# 舊做法（fetch_foreign_quotes）取「最後兩個非空收盤」相減，盤查 83 版落檔發現三個錯：
#   · 22:30 以後（美股盤中）拿到的是盤中價；19:00 歐股、早上 8～10 點日韓股也是盤中；
#   · 美股剛收盤那晚（台北隔天早上），日線最後一根的收盤是空值、被跳過 → 拿到前兩個交易日的漲跌
#     （10/21 08:36 NVDA 顯示 +1.38%，那是 10/19 的漲跌）；
#   · 完全不看日期，與台股報價日無從對齊。
# 使用者決定（2026-10-21）：海外只用**已收盤**的價格、對齊台股最新交易日 T；還沒收盤標「待收盤」。

def _local_date(ts, gmt: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(float(ts) + gmt, timezone.utc).date().isoformat()


def close_on(res: dict, day: str, now_ts: float) -> tuple[str, float | None, float | None]:
    """Yahoo chart result → 當地 `day` 那天的 (狀態, 收盤, 前收)。狀態：
      ok   ＝當地 day 已收盤（前收＝緊鄰前一根；那根空值時前收為 None）；
      pend ＝當地 day 還沒收盤（時段還沒開始或正在交易）；
      none ＝已過收盤時間仍查無 day（當地休市或資料缺）。

    日期一律以交易所當地時區（meta.gmtoffset）換算——澳洲夏令開盤是 UTC 前一天，用 UTC 日期會錯一天。
    正在交易的那天整根不收（同 macrochips._CLOSE_ONLY 的修法）。那天時段已結束、那根收盤卻是空值時，
    用 meta.regularMarketPrice——只在最後成交時戳落在當地 day 那天才用（正規時段的最後成交＝收盤價；
    盤後交易另有欄位，不會寫進這裡）。"""
    meta = res.get("meta") or {}
    gmt = int(meta.get("gmtoffset") or 0)
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    closes = q.get("close") or []
    bars: dict[str, float | None] = {}
    for t, c in zip(ts, closes):                       # 同一天多根（偶見即時 bar 另列）→ 取最後一根
        if t is not None:
            bars[_local_date(t, gmt)] = c
    order = sorted(bars)
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    st, en = reg.get("start"), reg.get("end")
    has_reg = isinstance(st, (int, float)) and isinstance(en, (int, float))
    reg_day = _local_date(st, gmt) if has_reg else None

    def prev_of(d: str) -> float | None:
        before = [x for x in order if x < d]
        return bars[before[-1]] if before else None

    if has_reg:
        if day > reg_day or (day == reg_day and now_ts < en):
            return "pend", None, None                  # 當地這天的正規時段還沒結束
    elif day >= _local_date(now_ts, gmt):
        return "pend", None, None                      # 沒有時段資訊：當地今天以後一律視為未收盤
    c = bars.get(day)
    if c is None:
        # 剛收盤那根收盤是空值：美股台北早上（美東前一晚）、歐股到隔天中午都還是空值
        # （2026-10-21 CI 探針實測 ABN.AS／SDLF.L，且時段資訊已換到隔天）。走到這裡代表 day 的時段已結束
        # （還在交易的情形上面已回 pend）→ 最後成交時戳就在當地 day 那天的話，最後成交價就是收盤價。
        rmt, rmp = meta.get("regularMarketTime"), meta.get("regularMarketPrice")
        if (isinstance(rmt, (int, float)) and isinstance(rmp, (int, float))
                and _local_date(rmt, gmt) == day):
            c = float(rmp)
    if c is None:
        return "none", None, None
    return "ok", float(c), prev_of(day)


def _chart(sym: str) -> dict | None:
    try:
        doc = get_json("https://query1.finance.yahoo.com/v8/finance/chart/"
                       f"{urllib.parse.quote(sym)}?range=1mo&interval=1d", cache_ttl=1800)
        return doc["chart"]["result"][0]               # type: ignore[index]
    except Exception:
        return None


def fetch_foreign_on(sids: set[str], day: str, now_ts: float | None = None
                     ) -> tuple[dict[str, dict], set[str], dict[str, int]]:
    """海外持股在**當地 day 那天、已收盤**的報價 → ({代號: {close, change, ccy, date, …}}, 待收盤代號, 統計)。

    與 fetch_today_all 同構（多帶 ccy 幣別與 date）；前收缺時 change 為 None（只給收盤）。
    統計 {ok, pend, none, fail}：fail＝Yahoo 抓不到（KS 抓不到補試 .KQ）。"""
    import time
    now_ts = time.time() if now_ts is None else now_ts
    out: dict[str, dict] = {}
    pend: set[str] = set()
    stat = {"ok": 0, "pend": 0, "none": 0, "fail": 0}
    for sid in sorted(sids):
        sym = to_yahoo(sid)
        if not sym:
            continue
        res = _chart(sym)
        if res is None and sym.endswith(".KS"):           # 韓股兩板：KOSPI 抓不到試 KOSDAQ
            res = _chart(sym[:-3] + ".KQ")
        if res is None:
            stat["fail"] += 1
            continue
        state, c, p = close_on(res, day, now_ts)
        stat[state] += 1
        if state == "pend":
            pend.add(sid)
        elif state == "ok":
            ccy = (res.get("meta") or {}).get("currency")
            out[sid] = {"close": round(c, 4), "change": (round(c - p, 4) if p is not None else None),
                        "ccy": ccy or "USD", "name": "", "volume": 0, "date": day}
    return out, pend, stat


def describe_bars(sym: str, now_ts: float | None = None) -> str:
    """探針：一檔的最後三根日線（當地日期、收盤）與正規時段／最後成交時間——CI 日誌驗證用。"""
    import time
    res = _chart(sym)
    if res is None:
        return f"{sym}：抓不到"
    now_ts = time.time() if now_ts is None else now_ts
    meta = res.get("meta") or {}
    gmt = int(meta.get("gmtoffset") or 0)
    ts = res.get("timestamp") or []
    cl = (((res.get("indicators") or {}).get("quote") or [{}])[0] or {}).get("close") or []
    tail = [f"{_local_date(t, gmt)}={c}" for t, c in list(zip(ts, cl))[-3:] if t is not None]
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}

    def hm(x):
        if not isinstance(x, (int, float)):
            return "—"
        from datetime import datetime, timezone
        return datetime.fromtimestamp(float(x) + gmt, timezone.utc).strftime("%m-%d %H:%M")
    return (f"{sym}：末三根 {tail}｜正規時段 {hm(reg.get('start'))}～{hm(reg.get('end'))}"
            f"｜最後成交 {hm(meta.get('regularMarketTime'))} 價 {meta.get('regularMarketPrice')}"
            f"｜現在 {hm(now_ts)}（當地）")
