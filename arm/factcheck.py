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


_US_IDX_SYM = {"sox": "^SOX", "ndq": "^IXIC", "spx": "^GSPC", "dji": "^DJI"}


def _adjacent_session(prev: date, cur: date) -> bool:
    """prev 是否確為 cur 的「前一個交易日」——日變動% 只在相鄰時才算。

    2026-07-28 踩坑：Yahoo 日線偶爾漏棒（當日 ^IXIC/^SOX 都缺 07/24 那根），
    原本無條件拿「序列前一筆」硬算，日變動就靜默變成**多日累計**，把正確的單日
    漲跌誤判成 🔴——實例：費半單日 −2.23% 被判成官方 −6.39%（實為 07/24 −4.25%
    與 07/27 −2.23% 的兩日累計）、那指單日 −0.18% 被判成 −0.82%。

    只承認「連續平日」與「週五→週一」。跨假日（如週五→週二）與漏棒在日期上
    無法區分，一律回 False，讓上層走既有的 ⚪「無前日收盤可算漲跌%」誠實跳過
    ——寧可少驗幾天，也不可對正確數字發假警報（設計原則 1「絕不誤殺」）。
    """
    gap = (cur - prev).days
    if gap == 1:                                          # 一般平日相鄰
        return True
    return gap == 3 and prev.weekday() == 4 and cur.weekday() == 0   # 週五 → 週一


def yahoo_index_series(key: str) -> dict[str, tuple[float, float | None]] | None:
    """Yahoo 圖表 API（CI 可達）→ {iso日期: (收盤, 當日漲跌%)}。
    2026-07-22 新增：費半等美股指數收盤點位媒體少登，查證代理連三日出錯
    （週跌幅誤植／誤引盤中快照／同日兩報 3.7% vs 5.21% 矛盾）——改由官方序列程式化驗證。"""
    import urllib.parse
    sym = _US_IDX_SYM.get(key)
    if not sym:
        return None
    doc = _get_json("https://query1.finance.yahoo.com/v8/finance/chart/"
                    f"{urllib.parse.quote(sym)}?range=1mo&interval=1d")
    try:
        res = doc["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
    except Exception:
        return None
    from datetime import datetime, timezone
    out: dict[str, tuple[float, float | None]] = {}
    prev: tuple[date, float] | None = None
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(t, timezone.utc).date()
        chg = (c / prev[1] - 1) * 100 if prev and _adjacent_session(prev[0], d) else None
        out[d.isoformat()] = (float(c), chg)
        prev = (d, float(c))
    return out or None


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
    qual: str = ""                                    # 「逾／近／約」限定詞——寬容差比對
    alts: list[float] = field(default_factory=list)   # 同句其他候選值（增量/前日值等）——
                                                      # 任一與官方相符即 🟢（CI 首輪實測：
                                                      # 「再增 1,736 口、升至 86,189 口」抓到
                                                      # 增量誤判 🔴，防同型誤殺）


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


_US_IDX_PAT = {"sox": r"費半|費城半導體|SOX", "ndq": r"那斯達克|那指|Nasdaq",
               "spx": r"標普|S&P ?500", "dji": r"道瓊"}

# 非現貨口徑（期貨／夜盤／盤前後）——數字對的是期貨或延長時段，拿日線現貨驗必誤判。
# 2026-07-27 起硬化：兩天內兩度誤殺（費半週跌幅、那指 100 期貨 +1.2%）。
_NON_SPOT = r"期貨|期指|夜盤|盤前|盤後"


def extract_us_index_claims(text: str, session_day: date) -> list[Claim]:
    """美股指數（費半／那指／標普／道瓊）漲跌%與收盤點位——句內常無日期，
    以報告「對應交易日」為錨。kind＝us_{key}_chg / us_{key}_close。
    CI 首輪誤判硬化（2026-07-22）：①含 markdown 連結的句子整句跳過（URL 數字與
    連結標題如「Nasdaq 100 Tops 29,000」是最大雜訊源）；②同句多指數各自以
    「指數名後 60 字視窗、遇下一個指數名截斷」定位，防個股漲幅／他指數錯掛；
    ③點位限 4,000–99,999 量級；④「逾／近／約」限定詞記入 qual、比對時放寬。"""
    claims: list[Claim] = []
    for sent in re.split(r"[。；\n]", text or ""):
        if "](" in sent:                               # 參考連結句：URL/標題數字不可當行情
            continue
        occs = []
        for key, pat in _US_IDX_PAT.items():
            for m in re.finditer(pat, sent):
                occs.append((m.end(), key))
        # 累計／區間跌幅句（自 X 高點跌逾 N%、進技術性熊市、自波段高點回落）≠ 單日漲跌，
        # 整句不抽 chg（07-24 誤殺：SOX「自 6/22 高點跌逾 20%」被當日變動）
        drawdown = bool(re.search(r"高點|波段|技術性熊市|熊市|自 ?\d{1,2}[/月]", sent))
        occs.sort()
        for i, (pos, key) in enumerate(occs):
            end = occs[i + 1][0] - 8 if i + 1 < len(occs) else pos + 60
            win = sent[pos:max(pos, end)][:60]
            m = re.search(r"^[^%]{0,25}?(?:大漲|上漲|收漲|漲|反彈|重挫|大跌|下跌|收跌|跌|挫)"
                          r"\s*(逾|近|約)?\s*([\d.]+)\s*%", win)
            # 盤中/個股口徑非收盤指數漲跌，不可拿日線驗（07-23/24 誤殺修正）：
            # ①盤中詞（盤初/盤中/早盤/日盤/殺盤/一度/最高低）②視窗內先出現個股名（英特爾/AMD…）
            # ③期貨／夜盤等非現貨口徑（07-27 誤殺：「那指 100 期貨漲 1.2%」被當那指現貨日變動）
            intraday = re.search(rf"盤初|盤中|早盤|日盤|殺盤|一度|最[高低]|{_NON_SPOT}",
                                 win[:m.end(2)]) if m else None
            stock = re.search(r"英特爾|Intel|AMD|超微|輝達|NVIDIA|美光|Micron|台積|蘋果|Apple|"
                              r"特斯拉|Tesla|Alphabet|Meta|微軟", win[:m.end(2)]) if m else None
            if m and not drawdown and not intraday and not stock:
                claims.append(Claim(f"us_{key}_chg", float(m.group(2)), session_day,
                                    sent.strip()[:160], qual=m.group(1) or ""))
            m = re.search(r"(?<!前)收[^0-9%]{0,10}([\d,]{5,}(?:\.\d+)?)", win)
            if m and not re.search(_NON_SPOT, win[:m.start()]):   # 期貨/夜盤收盤價非現貨收盤
                v = _num(m.group(1))
                if v and 4000 <= v <= 99999:
                    claims.append(Claim(f"us_{key}_close", v, session_day,
                                        sent.strip()[:160], alts=[v]))
    return claims


def extract_claims(text: str, year: int | None = None) -> list[Claim]:
    """逐句抽高風險數字；只收「句內有日期」者（跨日引用防誤殺）。"""
    year = year or clock.today_tw().year
    claims: list[Claim] = []
    for sent in re.split(r"[。；\n]", text or ""):
        d = _sent_date(sent, year)
        if not d:
            continue
        # 期貨／夜盤句（台指期夜盤收 X、期指盤前）非加權現貨收盤，整句不抽點位與漲跌點
        non_spot = bool(re.search(_NON_SPOT, sent))
        m = re.search(r"(?:加權(?:指數)?|台股)[^收。\n]{0,14}收(?:盤|約)?[^0-9%]{0,8}([\d,]+\.\d+)", sent)
        if m and _num(m.group(1)) > 5000 and not non_spot:
            claims.append(Claim("index_close", _num(m.group(1)), d, sent.strip()))
        # 美股句（含道瓊/那指/標普/費半）不可被台股加權 index_chg 撈走
        # （07-24 誤殺：「道瓊下跌 506.93 點」被當加權漲跌點）
        us_ctx = re.search(r"道瓊|那斯達克|那指|標普|費半|S&P|Nasdaq|Dow", sent)
        m = re.search(r"(?:加權|台股|大盤)?[^0-9%]{0,6}(?:下跌|大跌|漲|上漲)\s*([\d,]+\.?\d*)\s*點", sent)
        if m and _num(m.group(1)) >= 100 and not us_ctx and not non_spot:  # 小波動不核對（口語四捨五入多）
            claims.append(Claim("index_chg", _num(m.group(1)), d, sent.strip()))
        m = re.search(r"三大法人[^0-9]{0,15}[買賣]超[^0-9]{0,8}([\d,]+\.?\d*)\s*億", sent)
        if m:
            claims.append(Claim("inst_total", _num(m.group(1)), d, sent.strip()))
        m = re.search(r"外資[^0-9]{0,20}[買賣]超[^0-9]{0,8}([\d,]+\.?\d*)\s*億", sent)
        if m and "累計" not in sent and "單週" not in sent and "上週" not in sent:
            claims.append(Claim("inst_foreign", _num(m.group(1)), d, sent.strip()))
        if "淨空單" in sent:
            vals = [_num(v) for v in re.findall(r"([\d,]{4,})\s*口", sent)]
            if vals:
                claims.append(Claim("tx_net", max(vals), d, sent.strip(), alts=vals))
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
    if kind.startswith("us_") and kind.endswith("_chg"):
        return abs(a - b) <= 0.15                        # 漲跌% 絕對容差（四捨五入口徑差）
    if kind.startswith("us_") and kind.endswith("_close"):
        return abs(a - b) <= b * 0.003
    return True


def _best(c: Claim, official: float) -> float:
    """同句多候選值取「最接近官方」者比對——任一相符即算相符（防增量/前日值誤殺）。"""
    cands = c.alts or [c.value]
    return min(cands, key=lambda v: abs(abs(v) - abs(official)))


def check_claims(claims: list[Claim], fetchers: dict | None = None) -> list[Finding]:
    """逐項與官方值比對。fetchers 可注入（測試用）；官方不可得→⚪。"""
    f = {"index": twse_index_close, "flows": twse_inst_flows, "tx": taifex_tx_foreign_net,
         "us": yahoo_index_series, **(fetchers or {})}
    idx_cache: dict[date, tuple | None] = {}
    flow_cache: dict[date, dict | None] = {}
    tx_cache: dict[date, float | None] = {}
    us_cache: dict[str, dict | None] = {}
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
            out.append(Finding("🟢" if _tol_ok(c.kind, _best(c, val), val) else "🔴", c, val))
        elif c.kind in ("inst_total", "inst_foreign"):
            if c.day not in flow_cache:
                flow_cache[c.day] = f["flows"](c.day)
            off = flow_cache[c.day]
            key = "total" if c.kind == "inst_total" else "foreign"
            if not off or key not in off:
                out.append(Finding("⚪", c, note="官方法人金額不可得"))
                continue
            out.append(Finding("🟢" if _tol_ok(c.kind, _best(c, off[key]), off[key]) else "🔴",
                               c, off[key]))
        elif c.kind == "tx_net":
            if c.day not in tx_cache:
                tx_cache[c.day] = f["tx"](c.day)
            off2 = tx_cache[c.day]
            if off2 is None:
                out.append(Finding("⚪", c, note="期交所淨額不可得"))
                continue
            out.append(Finding("🟢" if _tol_ok(c.kind, _best(c, off2), off2) else "🔴", c, off2))
        elif c.kind.startswith("us_"):
            key = c.kind.split("_")[1]
            if key not in us_cache:
                us_cache[key] = f["us"](key)
            ser = us_cache[key]
            row = (ser or {}).get(c.day.isoformat())
            if not row:
                out.append(Finding("⚪", c, note=f"官方 {key} 序列不可得或無該日"))
                continue
            close, chg = row
            if c.kind.endswith("_close"):
                out.append(Finding("🟢" if _tol_ok(c.kind, _best(c, close), close) else "🔴",
                                   c, close))
            else:
                if chg is None:
                    out.append(Finding("⚪", c, note="無前日收盤可算漲跌%"))
                    continue
                a, b = c.value, abs(chg)
                if c.qual == "逾":                     # 「逾 5%」＝下限語意：官方 ≥ 標稱即合理
                    ok = (b >= a - 0.05) and (b <= a + 2.0)
                elif c.qual in ("近", "約"):
                    ok = abs(a - b) <= 0.6
                else:
                    ok = _tol_ok(c.kind, a, b)
                out.append(Finding("🟢" if ok else "🔴", c, chg))
    return out
