"""切掉掛牌前（興櫃）與下市後的日 K（2026-10-15 實測發現，SPEC §3.7 沒預料到）。

FinMind TaiwanStockPrice 把同一代號在興櫃的交易也放進來：17 檔近年掛牌股裡 16 檔在官方上市櫃日之前
有 200–1,800 筆興櫃日 K（例：6488 環球晶 2014-10-28 起有日 K，官方 2015-09-25 才上櫃）。興櫃沒有
漲跌幅限制、流動性差，規格的股票池明訂排除興櫃——標籤、特徵與回測都不能用這一段。

判斷只用 FinMind 自己的欄位：主板的「漲跌價差」是對前一日收盤（除權息日對參考價），所以
「收盤 − 漲跌價差 ＝ 前一日收盤」幾乎天天成立（實測掛牌後 97–99.8%）；興櫃的價差對的是前一日均價，
只有 0–33% 成立。掛牌日＝符合率由低轉高、而且爆量的轉換點（沒成交的列不算證據）：
  前 20 筆符合率 ≤ 60%（至少 5 筆）、隔天符合、後 20 筆符合率 ≥ 90%、當天成交量 ≥ 前 20 筆中位數 3 倍；
  候選連成一群時取最後一群的第一天（興櫃期間偶有假轉換）。
CI 實測 62 檔（2008–2026 掛牌）第一版：59 檔需要切，52 檔與官方日相差 ≤1 個交易日、3 檔偵測到的是
上櫃日（後來轉上市，正確）、2 檔偏早（3661 興櫃中段假轉換、6901 掛牌前幾天沒成交的列）、0 檔漏判——
後兩條規則就是為這 2 檔加的。
找不到轉換點＝資料一開始就在主板（2008 年以前掛牌，或從上櫃轉上市，例如 2059 川湖）。

官方上市櫃日（證交所、櫃買 openapi）只拿來對帳（reconcile），不拿來切資料：上櫃轉上市的公司官方日期是
轉上市那天，拿它切會把上櫃時期的真實交易丟掉；已下市公司也查不到官方日期，兩種口徑混用會偏。
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

WIN = 20
MIN_PRE = 5
PRE_MAX = 0.6
POST_MIN = 0.9
VOL_MULT = 3.0

OFFICIAL_URLS = {"twse": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
                 "tpex": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"}
_LIST_KEY = re.compile(r"上市日期|上櫃日期|ListingDate|Listing_Date|DateOfListing", re.I)
_CODE_KEY = re.compile(r"代號|代碼|Code|code")
_CODE_RE = re.compile(r"^\d{4}[A-Z]?$")


def match_series(close, spread) -> np.ndarray:
    """每一列「收盤 − 漲跌價差 ＝ 前一筆有價收盤」是否成立（1／0；沒有價格的列為 NaN）。"""
    c = pd.to_numeric(pd.Series(close), errors="coerce").to_numpy(float)
    s = pd.to_numeric(pd.Series(spread), errors="coerce").to_numpy(float)
    ok = c > 0
    prev = pd.Series(np.where(ok, c, np.nan)).ffill().shift(1).to_numpy(float)
    tol = np.maximum(0.011, 1e-4 * np.abs(np.nan_to_num(prev)))
    good = ok & ~np.isnan(prev) & ~np.isnan(s)
    out = np.full(len(c), np.nan)
    out[good] = (np.abs(c[good] - s[good] - prev[good]) <= tol[good]).astype(float)
    return out


def _window(x: np.ndarray, forward: bool) -> tuple[np.ndarray, np.ndarray]:
    """前（不含當天）或後（不含當天）WIN 筆裡的有效筆數與符合筆數。"""
    valid = (~np.isnan(x)).astype(float)
    hit = np.nan_to_num(x)
    if forward:
        valid, hit = valid[::-1], hit[::-1]
    cv = np.concatenate([[0.0], np.cumsum(valid)])
    ch = np.concatenate([[0.0], np.cumsum(hit)])
    n = len(x)
    i = np.arange(n)
    lo = np.maximum(0, i - WIN)
    cnt, h = cv[i] - cv[lo], ch[i] - ch[lo]
    if forward:
        cnt, h = cnt[::-1], h[::-1]
    return cnt, h


def main_board_start(dates, close, spread, volume) -> pd.Timestamp | None:
    """一檔股票（依日期排序）的主板第一個交易日；資料一開始就在主板回 None。"""
    n = len(close)
    if n < MIN_PRE + 2:
        return None
    m = match_series(close, spread)
    vol = pd.to_numeric(pd.Series(volume), errors="coerce").astype(float)
    m[~(vol.to_numpy(float) > 0)] = np.nan       # 沒成交的列（價格沿用前一天、價差 0）不算證據
    pre_n, pre_h = _window(m, forward=False)
    post_n, post_h = _window(m, forward=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        pre_rate = pre_h / pre_n
        post_rate = post_h / post_n
    med = vol.where(vol > 0).rolling(WIN, min_periods=1).median().shift(1).to_numpy(float)
    nxt = np.append(m[1:], np.nan)
    v = vol.to_numpy(float)
    spike = np.isnan(med) | (v >= VOL_MULT * med)
    cand = (pre_n >= MIN_PRE) & (pre_rate <= PRE_MAX) & (nxt == 1.0) & (post_rate >= POST_MIN) & spike
    idx = np.flatnonzero(cand)
    if not len(idx):
        return None
    # 掛牌日之後幾天，前 20 筆仍以興櫃為主，所以候選會連成一群；興櫃期間偶有「價格不動＋爆量」的假轉換
    # （3661 世芯 2012-12）會形成更早的一群。相鄰候選差距 ≤20 筆算同一群，取最後一群的第一天。
    breaks = np.flatnonzero(np.diff(idx) > WIN)
    first = idx[breaks[-1] + 1] if len(breaks) else idx[0]
    return pd.Timestamp(pd.Series(dates).iloc[first])


def main_board_end(dates, close, spread, volume, after: pd.Timestamp | None = None) -> pd.Timestamp | None:
    """主板最後一個交易日（之後轉回興櫃型態：前 20 筆符合率 ≥90%、後 20 筆 ≤60%）；一路都是主板回 None。
    下市後改在興櫃交易的公司，FinMind 會接著給興櫃日 K——用資料本身判斷，不靠下市日（股票清單的下市判斷可能有誤）。"""
    n = len(close)
    if n < 2 * MIN_PRE:
        return None
    m = match_series(close, spread)
    vol = pd.to_numeric(pd.Series(volume), errors="coerce").astype(float).to_numpy(float)
    m[~(vol > 0)] = np.nan
    pre_n, pre_h = _window(m, forward=False)
    post_n, post_h = _window(m, forward=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        pre_rate, post_rate = pre_h / pre_n, post_h / post_n
    d = pd.to_datetime(pd.Series(dates)).to_numpy()
    ok = np.ones(n, dtype=bool) if after is None else d >= np.datetime64(after)
    cand = ok & (pre_n >= MIN_PRE) & (pre_rate >= POST_MIN) & (post_n >= MIN_PRE) & (post_rate <= PRE_MAX) & (m == 1.0)
    idx = np.flatnonzero(cand)
    if not len(idx):
        return None
    # 和掛牌日相反：主板最後幾天的「後 20 筆」已混進興櫃，候選連成一群——取第一群的最後一天
    breaks = np.flatnonzero(np.diff(idx) > WIN)
    last = idx[breaks[0]] if len(breaks) else idx[-1]
    return pd.Timestamp(d[last])


def trim(prices: pd.DataFrame, universe: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """prices＝原始日 K 長表（date, stock_id, close, spread, volume）。
    回傳（只留主板期間的日 K, 每檔紀錄：first_raw/last_raw 原始首末日、main_start/main_end 偵測到的主板首末日、
    delist_date 股票池的下市日（只記錄、不拿來切）、dropped_pre/dropped_post 切掉幾筆）。"""
    if prices.empty:
        return prices, pd.DataFrame(columns=["stock_id", "first_raw", "main_start", "main_end", "last_raw",
                                             "delist_date", "dropped_pre", "dropped_post", "kept", "head_match"])
    p = prices.sort_values(["stock_id", "date"], kind="stable").reset_index(drop=True)
    p["date"] = pd.to_datetime(p["date"])
    delist = {}
    if universe is not None and not universe.empty and "delist_date" in universe:
        u = universe[universe["is_delisted"].astype(bool)]
        delist = dict(zip(u["stock_id"].astype(str), pd.to_datetime(u["delist_date"])))
    vol_col = "volume" if "volume" in p.columns else "Trading_Volume"
    keep = np.ones(len(p), dtype=bool)
    rows = []
    sid = p["stock_id"].astype(str).to_numpy()
    bounds = np.flatnonzero(sid[1:] != sid[:-1]) + 1
    for s, e in zip(np.concatenate([[0], bounds]), np.concatenate([bounds, [len(p)]])):
        g = p.iloc[s:e]
        start = main_board_start(g["date"].to_numpy(), g["close"].to_numpy(), g["spread"].to_numpy(),
                                 g[vol_col].to_numpy()) if "spread" in g.columns else None
        d = g["date"].to_numpy()
        end = main_board_end(d, g["close"].to_numpy(), g["spread"].to_numpy(), g[vol_col].to_numpy(),
                             after=start) if "spread" in g.columns else None
        pre = (d < np.datetime64(start)) if start is not None else np.zeros(len(g), dtype=bool)
        post = (d > np.datetime64(end)) if end is not None else np.zeros(len(g), dtype=bool)
        dd = delist.get(sid[s])
        keep[s:e] = ~(pre | post)
        head = match_series(g["close"].to_numpy(), g["spread"].to_numpy())[:WIN + 1] \
            if "spread" in g.columns else np.array([np.nan])
        rows.append({"stock_id": sid[s], "first_raw": pd.Timestamp(d[0]), "main_start": start, "main_end": end,
                     "last_raw": pd.Timestamp(d[-1]),
                     "delist_date": dd, "dropped_pre": int(pre.sum()), "dropped_post": int(post.sum()),
                     "kept": int((~(pre | post)).sum()),
                     "head_match": float(np.nanmean(head)) if np.isfinite(head).any() else np.nan})
    info = pd.DataFrame(rows)
    info["main_start"] = pd.to_datetime(info["main_start"])
    info["main_end"] = pd.to_datetime(info["main_end"])
    info["delist_date"] = pd.to_datetime(info["delist_date"])
    return p[keep].reset_index(drop=True), info


# ---------------------------------------------------------------------------------------------- 官方日期（對帳用）
def iso_date(v) -> str | None:
    """'19620209'／'0510209'（民國）／'2025/11/27'／'114/11/27' → ISO；無法解析回 None。"""
    s = re.sub(r"[^\d/.-]", "", str(v or "").strip())
    m = re.match(r"^(\d{2,4})[/.-](\d{1,2})[/.-](\d{1,2})$", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
    elif s.isdigit() and len(s) in (7, 8):
        y, mo, d = int(s[:-4]), int(s[-4:-2]), int(s[-2:])
    else:
        return None
    if y < 1911:
        y += 1911
    if not (1950 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def parse_official(rows, market: str) -> pd.DataFrame:
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = next((str(v).strip() for k, v in r.items()
                     if _CODE_KEY.search(str(k)) and _CODE_RE.match(str(v or "").strip())), None)
        d = next((iso_date(v) for k, v in r.items() if _LIST_KEY.search(str(k))), None)
        if code and d:
            out.append({"stock_id": code, "listing_date": pd.Timestamp(d), "market": market})
    return pd.DataFrame(out, columns=["stock_id", "listing_date", "market"])


def fetch_official(session, timeout: int = 30) -> pd.DataFrame:
    frames = []
    for market, url in OFFICIAL_URLS.items():
        resp = session.get(url, timeout=timeout)
        frames.append(parse_official(resp.json(), market))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def compare_official(info: pd.DataFrame, official: pd.DataFrame, calendar: pd.Series) -> dict:
    """偵測到的主板首日 vs 官方上市櫃日（只比現在掛牌、官方有日期、FinMind 日 K 從官方日之前就有的股票）。"""
    if info.empty or official.empty:
        return {"compared": 0}
    cal = pd.DatetimeIndex(sorted(pd.to_datetime(calendar)))
    m = info.merge(official, on="stock_id", how="inner")
    m = m[m["first_raw"] < m["listing_date"]]          # FinMind 日 K 在官方日之前就有＝應該切掉一段
    if m.empty:
        return {"compared": 0}
    pos = cal.searchsorted(m["listing_date"])
    got = cal.searchsorted(m["main_start"].fillna(pd.Timestamp("1900-01-01")))
    gap = np.where(m["main_start"].isna(), np.nan, got - pos)
    m = m.assign(gap=gap)
    exact = m["gap"].abs() <= 1
    # 沒偵測到、而且資料開頭就符合主板規則＝一開始就在主板（上櫃轉上市、或 2008 年前掛牌），不算漏
    board = m["main_start"].isna() & (m["head_match"] >= POST_MIN)
    missed = m["main_start"].isna() & ~board
    out = {"compared": int(len(m)), "within_1_day": int(exact.sum()), "main_board_from_start": int(board.sum()),
           "missed": int(missed.sum()), "earlier": int((m["gap"] < -1).sum()), "later": int((m["gap"] > 1).sum()),
           "examples": [{"stock_id": r.stock_id, "official": str(r.listing_date.date()), "market": r.market,
                         "detected": None if pd.isna(r.main_start) else str(r.main_start.date())}
                        for r in m[~exact & ~board].head(20).itertuples(index=False)]}
    return out
