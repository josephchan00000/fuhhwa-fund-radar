"""高風險數字事實核對（2026-07-20 使用者指示：數字必須確保正確）。

從新聞報告抽出「可被官方資料驗證」的高風險數字，與證交所（TWSE）／期交所（TAIFEX）
官方 API 比對：
  · 加權指數收盤價／漲跌點數（TWSE FMTQIK）
  · 三大法人合計買賣超金額、外資（及陸資）買賣超金額（TWSE BFI82U）
  · 外資臺股期貨(TX)多空淨額口數（TAIFEX 官方下載端點）

設計原則（務必維持）：
  1. **絕不誤殺**：官方資料抓不到（本 Claude 容器 proxy 會擋 twse/taifex——正常）、
     解析不了、日期對不上 → 一律 ⚪ skip，只有「官方值確實可得且超出容差」才 🔴。
  2. 句內日期錨定：數字所在句若含「M/D」日期（如 7/17 收 42,671），以該日期查官方值；
     無日期則不猜、跳過（報告常跨日引用，猜日期會誤殺）。
  3. 容差：口數 max(2%, 200 口)；金額 max(2%, 3 億)；指數點位 0.15%；漲跌點數 0.5%＋2 點。
  4. 純標準庫（urllib），經 arm.http 的逾時保護；單次請求 timeout 短（12s），失敗即 skip。
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date

from . import clock

_TIMEOUT = 12
_UA = {"User-Agent": "Mozilla/5.0 (factcheck; fuhhwa-fund-radar)"}


# ── 官方資料層（每源獨立降級；回 None＝不可得） ─────────────────────────

def _get_json(url: str) -> dict | list | None:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def twse_index_close(d: date) -> tuple[float, float] | None:
    """TWSE FMTQIK（市場成交資訊，月表）→ (加權收盤, 漲跌點數)。民國年日期比對。"""
    doc = _get_json(f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK"
                    f"?date={d:%Y%m%d}&response=json")
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        return None
    want = f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
    for row in doc.get("data") or []:
        try:
            if str(row[0]).strip() == want:
                close = float(str(row[4]).replace(",", ""))
                chg = float(str(row[5]).replace(",", ""))
                return close, chg
        except Exception:
            continue
    return None


def twse_inst_flows(d: date) -> dict | None:
    """TWSE BFI82U（三大法人買賣金額統計）→ {'total': 合計買賣差(億), 'foreign': 外資及陸資(億)}。
    官方單位為元；轉億元。"""
    doc = _get_json(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U"
                    f"?type=day&dayDate={d:%Y%m%d}&response=json")
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        return None
    out: dict[str, float] = {}
    try:
        for row in doc.get("data") or []:
            name = str(row[0])
            diff_e8 = float(str(row[3]).replace(",", "")) / 1e8
            if "外資及陸資" in name and "自營" not in name:
                out["foreign"] = out.get("foreign", 0.0) + diff_e8
            if name.strip() == "合計":
                out["total"] = diff_e8
        return out or None
    except Exception:
        return None


def taifex_tx_foreign_net(d: date) -> float | None:
    """期交所「三大法人—區分各期貨契約」臺股期貨(TX) 外資多空淨額口數（空方為負）。
    官方下載端點（CSV，POST）；欄位名歷有變動，以「外資」列＋倒數欄位群組解析。"""
    try:
        body = (f"queryStartDate={d:%Y/%m/%d}&queryEndDate={d:%Y/%m/%d}"
                "&commodityId=TXF").encode()
        req = urllib.request.Request(
            "https://www.taifex.com.tw/cht/3/futContractsDateDown",
            data=body, headers={**_UA, "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            text = r.read().decode("big5", errors="replace")
        for line in text.splitlines():
            cells = [c.strip().strip('"') for c in line.split(",")]
            if len(cells) > 12 and any("外資" in c and "自營" not in c for c in cells[:4]):
                # 版式：…多方口數,多方金額,空方口數,空方金額,多空淨額口數,多空淨額金額,…（未平倉組在後半）
                nums = [c.replace(",", "") for c in cells if re.fullmatch(r"-?\d+", c.replace(",", ""))]
                if len(nums) >= 2:
                    return float(nums[-2])   # 未平倉多空淨額口數（倒數第 2 個整數欄）
    except Exception:
        return None
    return None


# ── 報告端抽取（句內日期錨定；抽不到日期＝不檢查） ────────────────────────

@dataclass
class Claim:
    kind: str          # index_close / index_chg / inst_total / inst_foreign / tx_net
    value: float       # 報告聲稱值（正規化：金額→億、口數→口、點位→點）
    day: date
    sentence: str = ""


@dataclass
class Finding:
    status: str        # 🟢 / 🔴 / ⚪
    claim: Claim | None
    official: float | None = None
    note: str = ""


_DATE = re.compile(r"(\d{1,2})/(\d{1,2})")


def _sent_date(sent: str, year: int) -> date | None:
    m = _DATE.search(sent)
    if not m:
        return None
    try:
        return date(year, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def extract_claims(text: str, year: int | None = None) -> list[Claim]:
    """逐句抽高風險數字；只收「句內有日期」者（跨日引用防誤殺）。"""
    year = year or clock.today_tw().year
    claims: list[Claim] = []
    for sent in re.split(r"[。；\n]", text or ""):
        d = _sent_date(sent, year)
        if not d:
            continue
        m = re.search(r"(?:加權(?:指數)?|台股)[^收。\n]{0,14}收(?:盤|約)?[^0-9%]{0,8}([\d,]+\.\d+)", sent)
        if m and _num(m.group(1)) > 5000:
            claims.append(Claim("index_close", _num(m.group(1)), d, sent.strip()))
        m = re.search(r"(?:下跌|大跌|跌|漲|上漲)\s*([\d,]+\.?\d*)\s*點", sent)
        if m and _num(m.group(1)) >= 100:      # 小波動不核對（口語四捨五入多）
            claims.append(Claim("index_chg", _num(m.group(1)), d, sent.strip()))
        m = re.search(r"三大法人[^0-9]{0,15}[買賣]超[^0-9]{0,8}([\d,]+\.?\d*)\s*億", sent)
        if m:
            claims.append(Claim("inst_total", _num(m.group(1)), d, sent.strip()))
        m = re.search(r"外資[^0-9]{0,20}[買賣]超[^0-9]{0,8}([\d,]+\.?\d*)\s*億", sent)
        if m and "累計" not in sent and "單週" not in sent and "上週" not in sent:
            claims.append(Claim("inst_foreign", _num(m.group(1)), d, sent.strip()))
        m = re.search(r"淨空單[^口。\n]{0,20}?([\d,]{4,})\s*口", sent)
        if m:
            claims.append(Claim("tx_net", _num(m.group(1)), d, sent.strip()))
    return claims


# ── 比對 ─────────────────────────────────────────────────────────

def _tol_ok(kind: str, claimed: float, official: float) -> bool:
    a, b = abs(claimed), abs(official)
    if kind == "index_close":
        return abs(a - b) <= b * 0.0015
    if kind == "index_chg":
        return abs(a - b) <= b * 0.005 + 2
    if kind in ("inst_total", "inst_foreign"):
        return abs(a - b) <= max(b * 0.02, 3)
    if kind == "tx_net":
        return abs(a - b) <= max(b * 0.02, 200)
    return True


def check_claims(claims: list[Claim], fetchers: dict | None = None) -> list[Finding]:
    """逐項與官方值比對。fetchers 可注入（測試用）；官方不可得→⚪。"""
    f = {"index": twse_index_close, "flows": twse_inst_flows, "tx": taifex_tx_foreign_net,
         **(fetchers or {})}
    idx_cache: dict[date, tuple | None] = {}
    flow_cache: dict[date, dict | None] = {}
    tx_cache: dict[date, float | None] = {}
    out: list[Finding] = []
    for c in claims:
        if c.kind in ("index_close", "index_chg"):
            if c.day not in idx_cache:
                idx_cache[c.day] = f["index"](c.day)
            off = idx_cache[c.day]
            if off is None:
                out.append(Finding("⚪", c, note="官方指數不可得"))
                continue
            val = off[0] if c.kind == "index_close" else off[1]
            out.append(Finding("🟢" if _tol_ok(c.kind, c.value, val) else "🔴", c, val))
        elif c.kind in ("inst_total", "inst_foreign"):
            if c.day not in flow_cache:
                flow_cache[c.day] = f["flows"](c.day)
            off = flow_cache[c.day]
            key = "total" if c.kind == "inst_total" else "foreign"
            if not off or key not in off:
                out.append(Finding("⚪", c, note="官方法人金額不可得"))
                continue
            out.append(Finding("🟢" if _tol_ok(c.kind, c.value, off[key]) else "🔴", c, off[key]))
        elif c.kind == "tx_net":
            if c.day not in tx_cache:
                tx_cache[c.day] = f["tx"](c.day)
            off2 = tx_cache[c.day]
            if off2 is None:
                out.append(Finding("⚪", c, note="期交所淨額不可得"))
                continue
            out.append(Finding("🟢" if _tol_ok(c.kind, c.value, off2) else "🔴", c, off2))
    return out
