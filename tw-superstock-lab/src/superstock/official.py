"""官方免費資料：處置股（證交所／櫃買處置公告）、集保股權分散表（每週）。

FinMind 的處置股期間、股權分散表都是贊助會員才有（§3.7 實測），2026-10-15 使用者同意改抓官方網站
（CI 實測 scripts/probe_official.py）：
- 處置股：證交所 rwd/announcement/punish、櫃買 www/bulletin/disposal，都能一次查一整年
  （2024 年：證交所 176 筆、櫃買 415 筆，含權證、可轉債，這裡只留 4 碼普通股）。
  證交所查得到 2008 年；查詢以處置期間跟區間重疊為準，所以跨年的處置會在兩年都出現（去重）。
  櫃買的日期要用西元（民國年兩位數時會被當成查詢失敗、回傳今天的資料——用 date 欄位核對）。
- 集保股權分散表：開放資料只有「最新一週」全市場一份；歷史要逐檔逐週查（集保網站只留約一年），
  所以這裡每次執行存下當週、往後累積。大戶指標（S14）沒有免費的長歷史。

原始檔放 data/raw/official/（不進 git）；build 時整理成 disposition.parquet、tdcc.parquet。
"""

from __future__ import annotations

import io
import json
import logging
import re
import ssl
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (research; superstock-lab)", "Accept": "application/json,text/csv,*/*"}
STOCK_RE = re.compile(r"^[1-9]\d{3}$")
SPACING_SEC = 3.0   # 證交所對連續請求有頻率限制（會回 HTML 擋頁），每次至少間隔 3 秒

# ── 處置股 ───────────────────────────────────────────────────

TWSE_PUNISH = "https://www.twse.com.tw/rwd/zh/announcement/punish?startDate={a}&endDate={b}&response=json"
TPEX_DISPOSAL = "https://www.tpex.org.tw/www/zh-tw/bulletin/disposal?startDate={a}&endDate={b}&response=json"
DISP_COLS = ["date", "stock_id", "stock_name", "market", "period_start", "period_end",
             "measure", "level", "reason", "match_minutes", "times"]
MARKETS = ("twse", "tpex")

_CN = {"零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_FW = str.maketrans("０１２３４５６７８９", "0123456789")


def roc_date(s) -> pd.Timestamp:
    """民國日期「113/01/11」「96/12/28」→ Timestamp；解析不了回 NaT。"""
    m = re.match(r"^\s*(\d{2,3})[/.-](\d{1,2})[/.-](\d{1,2})\s*$", str(s or "").translate(_FW))
    if not m:
        return pd.NaT
    try:
        return pd.Timestamp(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))
    except ValueError:
        return pd.NaT


def period(s) -> tuple[pd.Timestamp, pd.Timestamp]:
    """處置起迄「113/01/12～113/01/29」（證交所全形～）或「113/12/31~114/01/14」（櫃買半形~）。"""
    parts = re.split(r"\s*[～~〜]\s*", str(s or "").strip())
    if len(parts) != 2:
        return pd.NaT, pd.NaT
    return roc_date(parts[0]), roc_date(parts[1])


def cn_int(s: str) -> int | None:
    """「五」「二十」「二十五」「十」「2」「20」→ 整數。"""
    s = (s or "").strip().translate(_FW)
    if s.isdigit():
        return int(s)
    if not s or any(ch not in _CN and ch != "十" for ch in s):
        return None
    if "十" in s:
        a, _, b = s.partition("十")
        return (_CN[a] if a else 1) * 10 + (_CN[b] if b else 0)
    return _CN[s] if len(s) == 1 else None


def match_minutes(text: str) -> int | None:
    """處置內容裡的「約每五分鐘撮合一次」「約每20分鐘」→ 分鐘數（分盤集合競價的間隔）。"""
    m = re.search(r"每\s*([0-9０-９一二兩三四五六七八九十]+)\s*分鐘", str(text or ""))
    return cn_int(m.group(1)) if m else None


def _level(measure: str) -> int:
    """1＝第一次處置；2＝第二次（證交所）／再次處置（櫃買）。2008 年前後的「收足五成款券」等算 1。"""
    m = str(measure or "")
    return 2 if ("第二次" in m or "再次" in m) else 1


def _clean_name(s) -> str:
    # 櫃買的名稱後面帶連結：「新門(../../mainboard/listed/company-detail.html?code=5432)」
    return re.sub(r"\((?:\.\./|https?:).*?\)\s*$", "", str(s or "")).strip()


def _rows_to_frame(fields: list, rows: list, market: str) -> pd.DataFrame:
    """依欄名（不寫死欄序）取出需要的欄位，只留 4 碼普通股。"""
    f = [str(x).strip() for x in fields]

    def col(*names):
        for n in names:
            if n in f:
                return f.index(n)
        return None

    i_date, i_id, i_name = col("公布日期"), col("證券代號"), col("證券名稱")
    i_cnt, i_per = col("累計"), col("處置起迄時間", "處置起訖時間")
    i_reason, i_meas, i_body = col("處置條件", "處置原因"), col("處置措施"), col("處置內容")
    if None in (i_date, i_id, i_per):
        raise ValueError(f"{market} 處置公告欄位不符：{f}")
    out = []
    for r in rows:
        r = list(r)
        code = str(r[i_id] if i_id < len(r) else "").strip()
        if not STOCK_RE.match(code):
            continue   # 權證、可轉債、「本日無處置資料」列
        a, b = period(r[i_per])
        body = r[i_body] if i_body is not None and i_body < len(r) else ""
        meas = str(r[i_meas]).strip() if i_meas is not None else ""
        out.append({
            "date": roc_date(r[i_date]), "stock_id": code,
            "stock_name": _clean_name(r[i_name]) if i_name is not None else "",
            "market": market, "period_start": a, "period_end": b, "measure": meas, "level": _level(meas),
            "reason": str(r[i_reason]).strip() if i_reason is not None else "",
            "match_minutes": match_minutes(body),
            "times": pd.to_numeric(r[i_cnt], errors="coerce") if i_cnt is not None else None,
        })
    df = pd.DataFrame(out, columns=DISP_COLS)
    return df.dropna(subset=["date", "period_start", "period_end"]).reset_index(drop=True)


def parse_twse(j: dict) -> tuple[pd.DataFrame, int]:
    """證交所處置公告 JSON → (表, 官方 total)。查無資料回空表。"""
    stat = str(j.get("stat", ""))
    if stat != "OK":
        if "沒有符合" in stat or "查無" in stat:
            return pd.DataFrame(columns=DISP_COLS), 0
        raise ValueError(f"證交所處置公告回應異常：stat={stat[:80]}")
    rows = j.get("data") or []
    return _rows_to_frame(j.get("fields") or [], rows, "twse"), int(j.get("total") or len(rows))


def parse_tpex(j: dict, expect: str | None = None) -> pd.DataFrame:
    """櫃買處置公告 JSON → 表。expect＝「20240101~20241231」：核對回應的查詢區間（查詢失敗時會回傳今天）。"""
    if str(j.get("stat", "")).lower() != "ok":
        raise ValueError(f"櫃買處置公告回應異常：stat={str(j.get('stat'))[:80]}")
    if expect and str(j.get("date", "")) != expect:
        raise ValueError(f"櫃買處置公告查詢區間不符：要 {expect}，回 {j.get('date')}")
    tables = j.get("tables") or []
    if not tables:
        return pd.DataFrame(columns=DISP_COLS)
    t = tables[0]
    return _rows_to_frame(t.get("fields") or [], t.get("data") or [], "tpex")


def _get_json(session: requests.Session, url: str, retries: int = 4, sleep=time.sleep) -> dict:
    last = None
    for i in range(retries):
        try:
            r = session.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            return r.json()   # 證交所限流時回 HTML 擋頁 → JSON 解析失敗 → 等一下再試
        except (requests.RequestException, ValueError) as e:
            last = e
            sleep(min(120, 10 * 3 ** i))
    raise RuntimeError(f"{url[:90]}… 抓取失敗：{last}")


def fetch_disposition(session: requests.Session, market: str, start: pd.Timestamp, end: pd.Timestamp,
                      sleep=time.sleep) -> pd.DataFrame:
    """一段期間（通常一整年）的處置公告。證交所筆數對不上 total 時改逐月查。"""
    if market == "twse":
        j = _get_json(session, TWSE_PUNISH.format(a=start.strftime("%Y%m%d"), b=end.strftime("%Y%m%d")), sleep=sleep)
        df, total = parse_twse(j)
        if total > len(j.get("data") or []):
            log.warning("證交所處置公告 %s～%s 回傳 %s 筆、total %s：改逐月查", start.date(), end.date(),
                        len(j.get("data") or []), total)
            parts = []
            for m0 in pd.date_range(start, end, freq="MS"):
                m1 = min(end, m0 + pd.offsets.MonthEnd(0))
                sleep(SPACING_SEC)
                parts.append(parse_twse(_get_json(session, TWSE_PUNISH.format(
                    a=m0.strftime("%Y%m%d"), b=m1.strftime("%Y%m%d")), sleep=sleep))[0])
            df = pd.concat(parts, ignore_index=True) if parts else df
        return df
    if market == "tpex":
        a, b = start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")
        j = _get_json(session, TPEX_DISPOSAL.format(a=a, b=b), sleep=sleep)
        return parse_tpex(j, expect=f"{start:%Y%m%d}~{end:%Y%m%d}")
    raise ValueError(market)


def _disp_dir(raw_dir: Path) -> Path:
    return Path(raw_dir) / "official" / "disposition"


def _final(year: int, fetched_at: str | None) -> bool:
    """這一年的檔案是在隔年 1/15 之後抓的＝完整（年底前幾天的公告都已收錄），之後不再重抓。"""
    return bool(fetched_at) and pd.Timestamp(fetched_at) >= pd.Timestamp(year + 1, 1, 15)


def update_disposition(raw_dir: Path, start_date: str, today: pd.Timestamp, session: requests.Session | None = None,
                       refresh: bool = False, sleep=time.sleep) -> dict:
    """逐市場、逐年抓處置公告存成 {market}_{year}.parquet；已完整的年份跳過。回傳每市場每年筆數。"""
    session = session or requests.Session()
    d = _disp_dir(raw_dir)
    d.mkdir(parents=True, exist_ok=True)
    meta_path = d / "_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    today = pd.Timestamp(today).normalize()
    out: dict = {m: {} for m in MARKETS}
    first = True
    for market in MARKETS:
        for year in range(pd.Timestamp(start_date).year, today.year + 1):
            key = f"{market}_{year}"
            path = d / f"{key}.parquet"
            if not refresh and path.exists() and _final(year, meta.get(key)):
                out[market][year] = None
                continue
            if not first:
                sleep(SPACING_SEC)
            first = False
            end = min(pd.Timestamp(year, 12, 31), today)
            df = fetch_disposition(session, market, pd.Timestamp(year, 1, 1), end, sleep=sleep)
            df.to_parquet(path, index=False)
            meta[key] = today.date().isoformat()
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True))
            out[market][year] = len(df)
            log.info("處置公告 %s %s：%s 筆（4 碼普通股）", market, year, len(df))
    return out


def build_disposition(raw_dir: Path) -> pd.DataFrame:
    files = sorted(_disp_dir(raw_dir).glob("*_*.parquet"))
    if not files:
        return pd.DataFrame(columns=DISP_COLS)
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.drop_duplicates(["market", "stock_id", "date", "period_start", "period_end"])
    return df.sort_values(["date", "stock_id"]).reset_index(drop=True)


def disposition_years(raw_dir: Path) -> pd.DataFrame:
    """每市場每年筆數（依公告日；品質檢查與 CI 日誌用）。"""
    df = build_disposition(raw_dir)
    if df.empty:
        return pd.DataFrame(columns=["year", "twse", "tpex"])
    t = df.assign(year=pd.to_datetime(df["date"]).dt.year).groupby(["year", "market"]).size().unstack(fill_value=0)
    return t.reindex(columns=list(MARKETS), fill_value=0).reset_index()


# ── 集保股權分散表 ───────────────────────────────────────────────

TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
# 持股分級：1＝1–999 股 … 12＝400,001–600,000、13＝600,001–800,000、14＝800,001–1,000,000、
# 15＝1,000,001 股以上（＝超過 1,000 張）、16＝差異數調整、17＝合計
TDCC_BIG400 = (12, 13, 14, 15)
TDCC_BIG1000 = 15
TDCC_TOTAL = 17


def _lenient_tls_session() -> requests.Session:
    """集保的憑證缺 Subject Key Identifier，OpenSSL 嚴格模式會拒絕。仍驗證憑證鏈與主機名，只關掉 X509 嚴格檢查。"""
    import certifi
    from requests.adapters import HTTPAdapter

    class _Adapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            ctx = ssl.create_default_context(cafile=certifi.where())
            if hasattr(ssl, "VERIFY_X509_STRICT"):
                ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
            kwargs["ssl_context"] = ctx
            return super().init_poolmanager(*args, **kwargs)

    s = requests.Session()
    s.mount("https://", _Adapter())
    return s


def parse_tdcc(content: bytes | str) -> pd.DataFrame:
    """集保 1-5 CSV → 長表：date, stock_id, level, holders, shares, pct。只留 4 碼普通股代號。"""
    txt = content.decode("utf-8-sig", "replace") if isinstance(content, bytes) else content.lstrip("﻿")
    df = pd.read_csv(io.StringIO(txt), dtype=str)
    df.columns = [c.strip() for c in df.columns]
    pct_col = next((c for c in df.columns if "比例" in c), None)
    need = {"資料日期", "證券代號", "持股分級", "人數", "股數"}
    if not need <= set(df.columns) or pct_col is None:
        raise ValueError(f"集保欄位不符：{list(df.columns)}")
    out = pd.DataFrame({
        "date": pd.to_datetime(df["資料日期"].str.strip(), format="%Y%m%d", errors="coerce"),
        "stock_id": df["證券代號"].str.strip(),
        "level": pd.to_numeric(df["持股分級"], errors="coerce"),
        "holders": pd.to_numeric(df["人數"].str.replace(",", ""), errors="coerce"),
        "shares": pd.to_numeric(df["股數"].str.replace(",", ""), errors="coerce"),
        "pct": pd.to_numeric(df[pct_col].str.replace(",", ""), errors="coerce"),
    })
    out = out[out["stock_id"].str.fullmatch(r"[1-9]\d{3}") & out["date"].notna() & out["level"].notna()]
    out["level"] = out["level"].astype(int)
    return out.reset_index(drop=True)


def tdcc_summary(long: pd.DataFrame) -> pd.DataFrame:
    """長表 → 每週每檔一列：big1000_pct（超過 1,000 張）、big400_pct（超過 400 張）、holders（總人數）、shares（集保總股數）。"""
    cols = ["date", "stock_id", "big1000_pct", "big400_pct", "holders", "shares"]
    if long.empty:
        return pd.DataFrame(columns=cols)
    idx = long.groupby(["date", "stock_id"]).size().index
    big1000 = long[long["level"] == TDCC_BIG1000].set_index(["date", "stock_id"])["pct"]
    big400 = long[long["level"].isin(TDCC_BIG400)].groupby(["date", "stock_id"])["pct"].sum()
    tot = long[long["level"] == TDCC_TOTAL].set_index(["date", "stock_id"])
    out = pd.DataFrame(index=idx)
    out["big1000_pct"] = big1000.reindex(idx).fillna(0.0)
    out["big400_pct"] = big400.reindex(idx).fillna(0.0)
    out["holders"] = tot["holders"].reindex(idx)
    out["shares"] = tot["shares"].reindex(idx)
    return out.reset_index()[cols]


def fetch_tdcc(session: requests.Session | None = None, retries: int = 3, sleep=time.sleep) -> pd.DataFrame:
    """抓最新一週（全市場）。預設連線驗不過集保憑證時，改用只關掉 X509 嚴格檢查的連線（仍驗證憑證）。"""
    last = None
    for i in range(retries):
        for s in ([session] if session is not None else [requests.Session()]) + [None]:
            try:
                r = (s or _lenient_tls_session()).get(TDCC_URL, headers=UA, timeout=120)
                r.raise_for_status()
                return parse_tdcc(r.content)
            except requests.exceptions.SSLError as e:
                last = e
                continue
            except (requests.RequestException, ValueError) as e:
                last = e
                break
        sleep(5 * (i + 1))
    raise RuntimeError(f"集保股權分散表抓取失敗：{last}")


def _tdcc_dir(raw_dir: Path) -> Path:
    return Path(raw_dir) / "official" / "tdcc"


def save_tdcc(long: pd.DataFrame, raw_dir: Path) -> tuple[Path | None, bool]:
    """存成 data/raw/official/tdcc/{資料日}.parquet；回傳 (路徑, 是否新的一週)。同一週已存過就不重寫。"""
    if long.empty:
        return None, False
    d = pd.Timestamp(long["date"].max()).date().isoformat()
    path = _tdcc_dir(raw_dir) / f"{d}.parquet"
    if path.exists():
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    long.to_parquet(path, index=False)
    return path, True


def update_tdcc(raw_dir: Path, session: requests.Session | None = None, sleep=time.sleep) -> dict:
    long = fetch_tdcc(session, sleep=sleep)
    path, new = save_tdcc(long, raw_dir)
    weeks = len(list(_tdcc_dir(raw_dir).glob("*.parquet")))
    info = {"date": path.stem if path else None, "new_week": new, "stocks": int(long["stock_id"].nunique()),
            "weeks_stored": weeks}
    log.info("集保股權分散表：資料日 %s（%s）、%s 檔、已累積 %s 週", info["date"],
             "新的一週" if new else "已存過", info["stocks"], weeks)
    return info


def build_tdcc(raw_dir: Path, calendar: pd.Series | None = None) -> pd.DataFrame:
    """所有已累積的週 → 每週每檔一列，加 available_date（資料日的下一個交易日，§1.4）。"""
    files = sorted(_tdcc_dir(raw_dir).glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    s = tdcc_summary(pd.concat([pd.read_parquet(f) for f in files], ignore_index=True))
    s = s.sort_values(["stock_id", "date"]).drop_duplicates(["date", "stock_id"], keep="last")
    s["available_date"] = next_trading_day(s["date"], calendar)
    return s.reset_index(drop=True)


def next_trading_day(dates: pd.Series, calendar=None) -> pd.Series:
    d = pd.to_datetime(pd.Series(dates)).reset_index(drop=True)
    if calendar is None or len(calendar) == 0:
        return d + pd.offsets.BDay(1)
    cal = pd.DatetimeIndex(sorted(pd.to_datetime(pd.Series(calendar)).unique()))
    pos = cal.searchsorted(d.values, side="right")
    ok = pos < len(cal)
    # 交易日曆還沒涵蓋到的（最新一週），用下一個平日
    fallback = d + pd.offsets.BDay(1)
    vals = [cal[p] if k else f for p, k, f in zip(pos, ok, fallback)]
    return pd.Series(pd.to_datetime(vals), index=d.index)


# ── 一次更新兩項（download／update 結束時、official 指令） ─────────────────────

def update_all(raw_dir: Path, start_date: str, today, what=("disposition", "tdcc"), refresh: bool = False,
               session: requests.Session | None = None, sleep=time.sleep) -> dict:
    """失敗只記錄、不中斷（官方網站偶爾維護）。"""
    session = session or requests.Session()
    res: dict = {}
    if "disposition" in what:
        try:
            res["disposition"] = update_disposition(raw_dir, start_date, today, session, refresh, sleep)
        except Exception as e:   # noqa: BLE001
            log.warning("處置公告更新失敗（下次再補）：%s", e)
            res["disposition_error"] = str(e)[:300]
    if "tdcc" in what:
        try:
            res["tdcc"] = update_tdcc(raw_dir, session, sleep)
        except Exception as e:   # noqa: BLE001
            log.warning("集保股權分散表更新失敗（下週再補）：%s", e)
            res["tdcc_error"] = str(e)[:300]
    return res
