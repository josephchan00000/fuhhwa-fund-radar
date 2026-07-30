"""復華官網持股揭露連接器 —— 張數 / NAV / AUM 的權威來源。

端點：/api/assetsExcel/{fund_id}/{YYYYMMDD} 直接回傳當日官方持股 xlsx，
內含：基金每單位淨值(NAV)、基金資產淨值(AUM)、在外流通單位數、
每檔成分股的【證券代號 / 名稱 / 股數 / 金額 / 權重】。

xlsx 以標準庫 zipfile+正則解析，避免在 Python 3.14 安裝 openpyxl。
"""
from __future__ import annotations

import re
import zipfile
from io import BytesIO

from ..http import get_bytes

URL = "https://www.fhtrust.com.tw/api/assetsExcel/{fund_id}/{ymd}"


class NoData(Exception):
    """該日無持股揭露（假日 / 尚未公告）。"""


def _num(x) -> float | None:
    if x is None:
        return None
    s = str(x).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _parse_xlsx(raw: bytes) -> list[list[str]]:
    if raw[:2] != b"PK":  # 不是 zip/xlsx → 無資料
        raise NoData("回傳非 xlsx")
    z = zipfile.ZipFile(BytesIO(raw))
    ss = z.read("xl/sharedStrings.xml").decode("utf-8")
    strings = re.findall(r"<x:t[^>]*>(.*?)</x:t>", ss, re.S)
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    rows_xml = re.findall(r"<x:row[^>]*>(.*?)</x:row>", sheet, re.S)

    def cellval(c: str) -> str:
        m = re.search(r"<x:v>(.*?)</x:v>", c, re.S)
        if not m:
            return ""
        v = m.group(1)
        return strings[int(v)] if 't="s"' in c else v

    rows: list[list[str]] = []
    for r in rows_xml:
        cells = re.findall(r"<x:c[^>]*?(?:/>|>.*?</x:c>)", r, re.S)
        rows.append([cellval(c) for c in cells])
    return rows


# 各資產類別的表頭關鍵字 → 區段類型（同一張表可能含多個區段，如債券基金有期貨+債券）
_PCT_RE = re.compile(r"-?[\d][\d.,]*\s*%")
_FACE_RE = re.compile(r"\(([A-Z]{3})\)\s*([-\d.,]+)")


def _is_header(row: list[str]) -> str | None:
    """是表頭就回傳區段類型(equity/future/bond)，否則 None。"""
    if not row or not any("權重" in (c or "") for c in row):
        return None
    head = row[0] or ""
    if head == "期貨代號":
        return "future"
    if head == "證券代號":
        return "equity"
    if head == "證券代碼":     # 債券區段用「證券代碼」+面額/債券市值
        return "bond"
    return None


def _is_data_row(row: list[str], ncols: int) -> bool:
    """資料列：欄數吻合、代號為 ASCII（排除「合計/現金/其他」等中文列）、末欄是百分比。"""
    if len(row) != ncols:
        return False
    code = (row[0] or "").strip()
    if not code or not code.isascii() or not any(ch.isalnum() for ch in code):
        return False
    return bool(_PCT_RE.fullmatch((row[-1] or "").strip()))


def _parse_face(s: str) -> tuple[float | None, str | None]:
    """'(USD)4,900,000' → (4900000.0, 'USD')；無幣別則回 (num, None)。"""
    m = _FACE_RE.search(s or "")
    if m:
        return _num(m.group(2)), m.group(1)
    return _num(s), None


_DATE_TOKENS = (
    re.compile(r"(?<!\d)(20\d{2})[/\-.年](\d{1,2})[/\-.月](\d{1,2})(?!\d)"),   # 2026/07/29
    re.compile(r"(?<!\d)(1\d{2})[/\-.年](\d{1,2})[/\-.月](\d{1,2})(?!\d)"),     # 民國 115/07/29
)


def _meta_date(tokens: list[str]) -> str | None:
    """從 xlsx 單格 meta 掃出「檔案自己的資料日」→ ISO；找不到回 None。

    為什麼需要它（2026-07-30 使用者抓到 00991A 假的「本次無異動」）：本函式原本把
    **請求的日期**當成資料日回傳（`"date": iso_date`），但 assetsExcel 端點對不同 ymd
    可能回同一份檔案 → 揭露日往前跳、內容一模一樣，Δ 就全變 0。改以檔案自報的日期為準；
    掃不到時仍回退請求日期（`etfholdings.merge_one` 另有「同一份快照」防呆兜底）。
    """
    for tok in tokens:
        t = str(tok or "").strip()
        for i, rx in enumerate(_DATE_TOKENS):
            m = rx.search(t)
            if m:
                y, mo, d = (int(x) for x in m.groups())
                if i:                                   # 民國年
                    y += 1911
                if 2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31:
                    return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


def fetch_holdings(fund_id: str, iso_date: str) -> dict:
    """回傳 {date, nav, aum, units, holdings:[...]}。

    holdings 每筆統一含 stock_id / stock_name / kind / shares / market_value / weight，
    其中 kind ∈ {equity, future, bond}：
      - equity：shares=股數（外股 ticker 如 'C US'、'7167 JP' 亦支援）
      - future：shares=口數（避險可為負）
      - bond  ：shares=面額(原幣數值)、另含 face_ccy / price / accrued、market_value=債券市值(NTD)
    支援單張表多區段（債券基金含期貨+債券）。
    """
    ymd = iso_date.replace("-", "")
    raw = get_bytes(URL.format(fund_id=fund_id, ymd=ymd), cache_ttl=24 * 3600)
    rows = _parse_xlsx(raw)

    # 抽 meta（標籤與值各自為單格列，依序出現）
    flat = [r[0] for r in rows if len(r) == 1]
    meta: dict[str, str] = {}
    for i, tok in enumerate(flat):
        if tok in ("基金資產淨值", "基金在外流通單位數", "基金每單位淨值") and i + 1 < len(flat):
            meta[tok] = flat[i + 1]

    date_src = _meta_date(flat)          # 檔案自報的資料日（優先於請求日期）
    nav = _num(meta.get("基金每單位淨值"))
    if nav is None:
        raise NoData(f"{fund_id} {iso_date} 無 NAV")

    holdings: list[dict] = []
    section: str | None = None
    ncols = 0
    for r in rows:
        kind = _is_header(r)
        if kind:
            section, ncols = kind, len(r)
            continue
        if not section or not _is_data_row(r, ncols):
            continue
        if section == "bond":
            # [代碼, 名稱, 面額, 結算價格, 應收利息, 債券市值, 權重]
            face, ccy = _parse_face(r[2])
            holdings.append({
                "stock_id": r[0], "stock_name": r[1], "kind": "bond",
                "shares": int(face or 0), "face_ccy": ccy,
                "price": _num(r[3]), "accrued": _num(r[4]),
                "market_value": _num(r[5]), "weight": _num(r[6]),
            })
        else:
            # equity/future：[代號, 名稱, 股數/口數, 金額, 權重]
            holdings.append({
                "stock_id": r[0], "stock_name": r[1], "kind": section,
                "shares": int(_num(r[2]) or 0),
                "market_value": _num(r[3]), "weight": _num(r[4]),
            })

    if not holdings:
        raise NoData(f"{fund_id} {iso_date} 無持股明細")

    return {
        "date": date_src or iso_date,
        "date_src": date_src,            # None＝檔案裡掃不到日期（CI 日誌會記，供一輪收斂）
        "date_req": iso_date,
        "nav": nav,
        "aum": _num(meta.get("基金資產淨值")),
        "units": _num(meta.get("基金在外流通單位數")),
        "holdings": holdings,
    }
