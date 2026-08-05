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
