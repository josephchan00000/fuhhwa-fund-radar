"""總經・籌碼數據「市場溫度計」（2026-07-23 使用者需求）—— 總經分頁的官方數據層。

兩組指標、各自獨立降級：
  · 全球市場溫度計 ← Yahoo 圖表 API（^VIX／^TNX／DXY／TWD=X／BZ=F／GC=F；CI 可達，
    factcheck.yahoo_index_series 同一端點）——每次抓近 1 個月日線整段合併。
  · 台股籌碼 ← TWSE／TAIFEX 官方 API（三大法人買賣超＝本層 _twse_inst_all 單一實作，
    factcheck.twse_inst_flows 反向重用它＋落檔（2026-08-05 起，核對基準＝落檔優先）；
    融資融券餘額＝MI_MARGN；外資台指期淨部位／選擇權 P/C 比＝期交所下載端點，
    支援日期區間、一次補齊近兩週史料）。

資料層 data/macro_chips.json（**必須入庫**當 fallback——同 etf_watch 的坑）：
  {"as_of": 抓取時戳, "series": {key: {ISO日期: 值}}, "src": {key: {...}}}
合併鐵則（同專案慣例）：本次抓到的「非 None」值才寫入；某指標整段抓不到 → 保留既有
序列原封不動，**絕不把非空序列洗成空**。序列每指標保留最近 _KEEP 筆。

本 Claude 容器 proxy 擋 twse/taifex/yahoo —— 抓取只在正式區 CI 跑（daily_fund.sh）；
容器內只讀落檔（含 WebSearch 查證的種子值）建儀表板。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from . import clock, factcheck

ROOT = Path(__file__).resolve().parent.parent
DATA_FP = ROOT / "data" / "macro_chips.json"

_TIMEOUT = 12
_UA = {"User-Agent": "Mozilla/5.0 (macrochips; fuhhwa-fund-radar)"}
_KEEP = 45            # 每指標保留筆數（30 日走勢圖＋緩衝）
_BACKFILL_DAYS = 14   # TWSE 逐日端點往回補抓的日曆日窗
# 第三方頁面會擋非瀏覽器 UA → 備援抓取用近似瀏覽器的標頭（官方端點仍用 _UA）
_BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
               "Accept-Language": "zh-TW,zh;q=0.9"}
# 三大法人身份別名稱（官方與第三方頁面共用的辨識詞）
_INST_NAME_RE = re.compile(r"外資及陸資\(不含外資自營商\)|外資及陸資|外資自營商|投信|"
                           r"自營商\(自行買賣\)|自營商\(避險\)|自營商|合計")

# ── 指標規格（key, 中文名, 來源, Yahoo 代碼或 None） ─────────────────────
#   group: gl=全球溫度計 / tw=台股籌碼
GLOBAL_SPECS: list[tuple[str, str, str]] = [
    ("vix",    "VIX 恐慌指數",          "^VIX"),
    ("us10y",  "美國 10 年期公債殖利率", "^TNX"),      # ^TNX：Yahoo chart 有時回百分比本身(4.66)、
                                                      # 有時×10(46.6)——_norm_yield 依量級自動正規化
    ("dxy",    "美元指數 DXY",          "DX-Y.NYB"),
    ("usdtwd", "美元兌新台幣",          "TWD=X"),
    ("brent",  "布蘭特原油",            "BZ=F"),
    ("gold",   "黃金期貨",              "GC=F"),
    # 2026-08-04 使用者需求（「費半／台積電 ADR 收盤數字查不到兩來源一致」的根治）：
    # 收盤值改由官方序列入庫，新聞報告直接讀落檔、不再依賴媒體收盤稿互相印證。
    # 僅入資料層供報告引用；儀表板「全球市場溫度計」未加列（_MD_GLOBAL_ROWS 未同步，如需展示再加）。
    ("sox",     "費城半導體指數",        "^SOX"),
    ("tsm_adr", "台積電 ADR",           "TSM"),
]
# 「收盤口徑」序列：報告引用時視為收盤值 → 交易中的當日盤中 bar 一律不入檔
# （2026-08-05 踩坑，機制見 _yahoo_series close_only）。溫度計類（VIX／匯率／油金）
# 顯示「最新值」本就要盤中快照，不在此列。
_CLOSE_ONLY = {"sox", "tsm_adr"}
TW_KEYS = ("inst_total", "inst_foreign", "inst_trust", "inst_dealer", "tx_foreign_net",
           "margin_bal", "short_bal", "pc_ratio")
ALL_KEYS = tuple(k for k, *_ in GLOBAL_SPECS) + TW_KEYS


# ── 來源層（每源獨立；回 {} ＝不可得，上層沿用既有序列） ────────────────

def _norm_yield(v: float) -> float:
    """^TNX 殖利率正規化：Yahoo chart 端點有時回百分比本身（如 4.66），有時回 ×10（46.6）。
    10 年期殖利率合理量級 0–20%，>20 一律視為 ×10 → ÷10。防 2026-07-23 踩的坑：
    寫死 ÷10 讓 4.657 變 0.4657（線上顯示 0.47%）。"""
    return round(v / 10.0, 4) if v > 20 else round(v, 4)


def _yahoo_series(sym: str, norm=None, close_only: bool = False) -> dict[str, float]:
    """Yahoo 圖表 API 近 1 個月日線 → {ISO日期: 收盤}。norm＝逐值正規化函式（如殖利率）。失敗回 {}。

    close_only（_CLOSE_ONLY 的 sox／tsm_adr 用）：**正在交易中的當日 bar 是盤中快照，
    不入檔**。2026-08-05 踩坑：22:05 班 cron 遲到 ~2h、台北 00:14（美東 12:13 盤中）才跑，
    把費半／ADR 的盤中值以當日 bar 之姿寫進落檔；晨報依「收盤優先讀落檔」規則整批引成
    收盤，三份報告事後只能改標盤中口徑。判定用 Yahoo 回應自帶的 meta
    （regularMarketTime < currentTradingPeriod.regular.end ＝該 session 尚未收盤），
    不看本機時鐘——免推美東 DST 與感恩節等提早收盤日。丟棄只是晚一班入檔
    （美股收盤後場次／翌晨 daily 會補上最終收盤），寧缺勿錯。"""
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(sym)}?range=1mo&interval=1d")
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            doc = json.loads(r.read().decode("utf-8"))
        res = doc["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
    except Exception:
        return {}
    from datetime import datetime, timezone
    out: dict[str, float] = {}
    for t, c in zip(ts, closes):
        if c is None:
            continue
        iso = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
        val = float(c)
        out[iso] = norm(val) if norm else round(val, 4)
    return _drop_open_bar(res, out) if close_only else out


def _drop_open_bar(res: dict, out: dict[str, float]) -> dict[str, float]:
    """去掉「進行中 session」的當日 bar。meta 缺漏／格式不明時保守保留（維持既有行為）；
    已收盤（regularMarketTime ≥ regular.end，收盤價印出後必然成立）全部保留；
    盤前時段 regular.end 指向尚未開盤的 session、序列裡沒有那天的 bar → pop 無作用，安全。"""
    try:
        meta = res.get("meta") or {}
        end = int(meta["currentTradingPeriod"]["regular"]["end"])
        mkt = int(meta["regularMarketTime"])
    except Exception:
        return out
    if mkt >= end:
        return out
    from datetime import datetime, timezone
    cur = datetime.fromtimestamp(end, timezone.utc).date().isoformat()
    if out.pop(cur, None) is not None:
        print(f"      · {cur} bar 為盤中快照（session 未收盤）——不入檔，待收盤後場次補上")
    return out


def _http(url: str, timeout: int = 20) -> tuple[str, str]:
    """回 (內文, 狀態描述)。狀態描述供 CI 日誌判讀「被擋 vs 回空 vs 解析失敗」，
    這是 2026-08-03 的教訓：官方抓不到時舊碼只沉默回 None，無從得知是哪一種。"""
    try:
        req = urllib.request.Request(url, headers=_BROWSER_UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return body, f"HTTP {r.status}／{len(body)}B"
    except urllib.error.HTTPError as e:
        return "", f"HTTPError {e.code}"
    except Exception as e:
        return "", f"{type(e).__name__}: {str(e)[:60]}"


def _inst_rows_to_flows(rows) -> dict | None:
    """把 [(名稱, 買賣差額元)] 轉成 {'foreign','trust','dealer','total'}（億元）。
    officially／第三方來源共用同一套歸戶邏輯，避免各寫一份而口徑分歧。"""
    out = {"foreign": None, "trust": 0.0, "dealer": 0.0, "total": None}
    got_dealer = got_trust = False
    for name, diff_yuan in rows:
        name = str(name)
        diff = float(diff_yuan) / 1e8                         # 元 → 億
        # 外資列名為「外資及陸資(不含外資自營商)」——含「自營」字樣，故以獨有的「陸資」二字辨識，
        # 不可用「自營 not in name」（會誤殺，factcheck 舊版同坑）。「外資自營商」不含「陸資」→ 不誤收。
        if "陸資" in name:
            out["foreign"] = round((out["foreign"] or 0.0) + diff, 2)
        elif "投信" in name:
            out["trust"] = round(out["trust"] + diff, 2); got_trust = True
        elif "自營商" in name and "外資" not in name:          # 自行買賣＋避險兩列（不含外資自營商）
            out["dealer"] = round(out["dealer"] + diff, 2); got_dealer = True
        elif name.strip() == "合計":
            out["total"] = round(diff, 2)
    if not got_trust:
        out["trust"] = None
    if not got_dealer:
        out["dealer"] = None
    return out if any(v is not None for v in out.values()) else None


def _inst_from_openapi(d: date, diag: list) -> dict | None:
    """官方備援：TWSE OpenAPI（openapi.twse.com.tw）——與 rwd 不同主機，
    專案既有連接器（stockmeta／connectors.twse）已證實 CI 可達。只提供「最新一日」，
    故僅在 d 為最近交易日時可用；日期不符即放棄（不可把別日的值寫成 d 的值）。"""
    body, st = _http("https://openapi.twse.com.tw/v1/exchangeReport/BFI82U")
    diag.append(f"openapi BFI82U → {st}")
    if not body:
        return None
    try:
        arr = json.loads(body)
    except Exception:
        diag.append(f"  openapi 非 JSON、開頭 {body[:60]!r}")
        return None
    if not isinstance(arr, list) or not arr:
        return None
    keys = list(arr[0].keys())
    diag.append(f"  openapi 欄位={keys}")
    # 日期欄位名歷有變動 → 以「值長得像日期」找，不寫死鍵名（同 stockmeta 慣例）
    dstr = f"{d:%Y%m%d}"
    roc = f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
    hit_date = any(dstr in str(v) or roc in str(v) for v in arr[0].values())
    if not hit_date:
        sample = {k: arr[0][k] for k in keys[:3]}
        diag.append(f"  openapi 日期不符（要 {dstr}／{roc}），首列 {sample} → 放棄")
        return None
    rows = []
    for it in arr:
        name = next((str(v) for k, v in it.items() if _INST_NAME_RE.search(str(v))), "")
        num = next((str(v) for k, v in it.items()
                    if "差額" in k or "買賣差" in k), "")
        if name and num:
            try:
                rows.append((name, float(num.replace(",", ""))))
            except ValueError:
                pass
    return _inst_rows_to_flows(rows) if rows else None


def _inst_from_thirdparty(d: date, diag: list) -> dict | None:
    """第三方備援（2026-08-03 使用者指示「官方抓不到就抓其他來源」）：
    Yahoo 股市法人買賣超頁 → 玩股網。**僅在官方兩個端點都失敗時才用**，
    且來源會標成非官方（見 fetch() 的 src 標記），因為專案鐵則是官方優先。

    註：玩股網 2026-07-30 為 ETF 成分股探針時回 403（WAF 擋機房 IP），
    此處仍列為候選是因為不同路徑不一定同策略；真正可用與否以 CI 日誌為準。"""
    # 這兩頁只揭露「最新一日」，補抓歷史日時不可用（否則會把今日值寫成別日的值）
    today = clock.today_tw()
    latest = today
    while latest.weekday() >= 5:
        latest -= timedelta(days=1)
    if d != latest:
        return None
    for label, url in (("yahoo", "https://tw.stock.yahoo.com/institutional-trading"),
                       ("wantgoo", "https://www.wantgoo.com/stock/institutional-investors"
                                   "/three-trade-for-trading-amount")):
        body, st = _http(url)
        diag.append(f"{label} → {st}")
        if not body:
            continue
        hits = {k: body.count(k) for k in ("外資", "投信", "自營商", "買賣超", "陸資")}
        diag.append(f"  {label} 關鍵字命中={hits}")
        rows = _scrape_inst_rows(body)
        if rows:
            flows = _inst_rows_to_flows(rows)
            if flows:
                diag.append(f"  {label} 解析成功：{flows}")
                return flows
        diag.append(f"  {label} 解析 0 列——需依上方命中數調整解析（片段 {body[:120]!r}）")
    return None


def _scrape_inst_rows(html: str) -> list:
    """從法人買賣超頁面刮出 [(身份別, 買賣差額元)]。頁面結構未知且會改版 →
    以「身份別關鍵字 + 其後最近的帶符號金額」配對，並同時支援『億元』與純數字（元）。"""
    rows = []
    for m in _INST_NAME_RE.finditer(html):
        name = m.group(0)
        tail = re.sub(r"<[^>]+>", " ", html[m.end():m.end() + 400])
        num = re.search(r"(-?[\d,]+(?:\.\d+)?)\s*(億)?", tail)
        if not num:
            continue
        try:
            v = float(num.group(1).replace(",", ""))
        except ValueError:
            continue
        rows.append((name, v * 1e8 if num.group(2) else v))
    return rows


def _twse_inst_all(d: date, diag: list | None = None) -> tuple[dict | None, str]:
    """三大法人買賣金額 → ({'foreign','trust','dealer','total'}（億元，買超為正）, 來源標籤)。

    來源順序（2026-08-03 起）：官方 rwd → 官方 OpenAPI → 第三方（Yahoo／玩股網）。
    **官方永遠優先**；第三方值會被標成非官方，供儀表板與事實核對辨識。"""
    diag = diag if diag is not None else []
    doc = factcheck._get_json(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U"
                              f"?type=day&dayDate={d:%Y%m%d}&response=json")
    if isinstance(doc, dict) and doc.get("stat") == "OK":
        rows = []
        for row in doc.get("data") or []:
            try:
                rows.append((str(row[0]), float(str(row[3]).replace(",", ""))))
            except (IndexError, ValueError):
                continue
        flows = _inst_rows_to_flows(rows)
        if flows:
            return flows, "twse:BFI82U"
    diag.append(f"{d} rwd BFI82U 不可得（stat={doc.get('stat') if isinstance(doc, dict) else 'n/a'}）")
    flows = _inst_from_openapi(d, diag)
    if flows:
        return flows, "twse:OpenAPI(BFI82U)"
    flows = _inst_from_thirdparty(d, diag)
    if flows:
        return flows, "第三方(非官方)"
    return None, ""


def _twse_inst_all_legacy(d: date) -> dict | None:
    """（保留舊簽名供既有測試／呼叫端使用）"""
    doc = factcheck._get_json(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U"
                              f"?type=day&dayDate={d:%Y%m%d}&response=json")
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        return None
    out = {"foreign": None, "trust": 0.0, "dealer": 0.0, "total": None}
    got_dealer = got_trust = False
    try:
        for row in doc.get("data") or []:
            name = str(row[0])
            diff = float(str(row[3]).replace(",", "")) / 1e8      # 官方單位元 → 億
            # 外資列名為「外資及陸資(不含外資自營商)」——含「自營」字樣，故以獨有的「陸資」二字辨識，
            # 不可用「自營 not in name」（會誤殺，factcheck 舊版同坑）。「外資自營商」不含「陸資」→ 不誤收。
            if "陸資" in name:
                out["foreign"] = round((out["foreign"] or 0.0) + diff, 2)
            elif "投信" in name:
                out["trust"] = round(out["trust"] + diff, 2); got_trust = True
            elif "自營商" in name and "外資" not in name:          # 自行買賣＋避險兩列（不含外資自營商）
                out["dealer"] = round(out["dealer"] + diff, 2); got_dealer = True
            elif name.strip() == "合計":
                out["total"] = round(diff, 2)
    except Exception:
        return None
    if not got_trust:
        out["trust"] = None
    if not got_dealer:
        out["dealer"] = None
    return out if any(v is not None for v in out.values()) else None


def _twse_margin(d: date) -> tuple[float, float] | None:
    """TWSE MI_MARGN（上市信用交易統計，selectType=MS）→ (融資餘額(億), 融券餘額(張))。
    官方融資金額單位＝仟元 → ÷1e5 轉億；融券單位＝交易單位（張）。"""
    doc = factcheck._get_json(
        "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
        f"?date={d:%Y%m%d}&selectType=MS&response=json")
    if not isinstance(doc, dict) or doc.get("stat") != "OK":
        return None
    tables = doc.get("tables") or [doc]          # RWD 端點歷有 tables 包裝與否兩版
    fin = short = None
    for t in tables:
        for row in (t.get("data") or []):
            try:
                name = str(row[0])
                nums = [float(str(c).replace(",", "")) for c in row[1:]
                        if re.fullmatch(r"-?[\d,]+(?:\.\d+)?", str(c).strip())]
                if not nums:
                    continue
                # 欄序：買進/賣出/償還/前日餘額/今日餘額 → 今日餘額＝最後一欄
                if "融資金額" in name:
                    fin = round(nums[-1] / 1e5, 1)
                elif name.strip().startswith("融券") and "金額" not in name:
                    short = round(nums[-1])
            except Exception:
                continue
    if fin is None and short is None:
        return None
    return fin, short


def _taifex_csv(url: str, body: str, diag: list[str] | None = None) -> list[list[str]]:
    """期交所下載端點（POST → CSV，big5）→ 逐列 cells。失敗回 []。

    diag＝診斷收集器（非 None 時把 HTTP 狀態／例外／回應首段記進去）——本容器 proxy 擋期交所、
    只能靠 CI 日誌除錯，沉默失敗會讓「序列凍結」查不出原因（2026-07-29 踩坑：tx_foreign_net
    自 7/23 起靜默停更 6 天，日誌只有一行「不可得」）。"""
    try:
        req = urllib.request.Request(
            url, data=body.encode(),
            headers={**_UA, "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            status = getattr(r, "status", None)
            text = r.read().decode("big5", errors="replace")
        rows = [[c.strip().strip('"') for c in line.split(",")]
                for line in text.splitlines() if line.strip()]
        if diag is not None and not rows:
            diag.append(f"HTTP {status} 但 0 列（body={body[:80]}）")
        return rows
    except Exception as e:                                    # noqa: BLE001 —— 每源獨立降級
        if diag is not None:
            diag.append(f"{type(e).__name__}: {str(e)[:120]}（body={body[:80]}）")
        return []


_ROW_DATE = re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$")


def _cell_date(cell: str) -> str | None:
    m = _ROW_DATE.match(cell.strip())
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


_TX_URL = "https://www.taifex.com.tw/cht/3/futContractsDateDown"

# 「臺股期貨（大台 TX）」商品名比對——**口徑鎖定用，不可放寬**。
# 使用者回報的數字落差（彙整站常見的『大台＋小台＋微台合計』）就出在這裡：若期交所忽略
# commodityId、整批回全商品，舊版只認「列中有外資」會安靜讀到小台／電子期的數字（2026-07-29 檢討）。
_TX_PROD = re.compile(r"^(臺|台)股期貨$|^TX$")
_MTX_HINT = re.compile(r"小型|微型|電子|金融|半導體")


def _tx_rows_to_series(rows: list[list[str]]) -> dict[str, float]:
    """期交所「三大法人—區分各期貨契約」CSV 列 → {ISO日期: 外資臺股期貨未平倉多空淨額口數}。

    欄序（官方）：日期,商品名稱,身份別,…多方/空方/淨額「交易」組…,…多方/空方/淨額「未平倉」組…
    → 倒數第 2 個整數欄＝多空淨額未平倉口數（最後一欄是契約金額）。

    兩道防呆：
      ① **商品鎖定**：只取臺股期貨(TX) 列。商品名在 HTML 表是 rowspan、CSV 有時只出現在該商品
         第一列（自營商），其餘列留空 → 以「最後見到的非空商品名」延續（cur_prod），否則
         外資列會因商品名空白被全數丟棄。
      ② **身份別鎖定**：外資／外資及陸資，但排除「外資自營商」。
    值為 0 一律跳過（0＝盤中未結算的哨兵，2026-07-23 踩過）。"""
    out: dict[str, float] = {}
    cur_prod = ""
    for cells in rows:
        if len(cells) <= 12:
            continue
        di = next((i for i, c in enumerate(cells[:3]) if _cell_date(c)), None)
        if di is None:
            continue
        iso = _cell_date(cells[di])
        # 商品名在日期後一欄；空白＝沿用上一列（rowspan 展平）
        prod = cells[di + 1].strip() if len(cells) > di + 1 else ""
        if prod:
            cur_prod = prod
        if not _TX_PROD.match(cur_prod or "") or _MTX_HINT.search(cur_prod or ""):
            continue
        ident = next((c for c in cells[di + 1:di + 4] if "外資" in c or "投信" in c
                      or "自營商" in c), "")
        if "外資" not in ident or "外資自營商" in ident:
            continue
        nums = [c.replace(",", "") for c in cells
                if re.fullmatch(r"-?\d+", c.replace(",", ""))]
        if len(nums) >= 2:
            val = float(nums[-2])
            if val != 0:
                out[iso] = val
    return out


def _last_settled(today: date, now_hour: int) -> date:
    """期交所盤後結算日：平日 15:00 後才有當日資料；否則往前找最近平日。
    2026-07-29 檢討：futContractsDateDown 的 queryEndDate 帶到「尚未結算的當日」時整批回空
    （同時段 pcRatioDown 仍正常），是序列自 7/24 起停更的最可疑主因——夾到已結算日再查。"""
    d = today if now_hour >= 15 else today - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _taifex_tx_foreign(start: date, end: date, now_hour: int = 23,
                       diag: list[str] | None = None) -> dict[str, float]:
    """外資臺股期貨(TX)未平倉多空淨額口數 → {ISO日期: 口數（淨空為負）}。

    韌性策略（2026-07-29 重寫，因舊版單一參數組合失效後靜默回空、序列凍結 6 天）：
      ① queryEndDate 夾到「最近已結算交易日」（見 _last_settled）。
      ② 依序試多組 POST 參數變體（期交所表單欄位歷有增修），第一組解析出資料就用。
      ③ 全部落空 → 逐日單日查詢兜底（單日端點與區間端點驗證邏輯不同，曾各自可用）。
      ④ 每一步的 HTTP 狀態／例外寫進 diag，由 CI 日誌印出——本容器 proxy 擋期交所，
         這是唯一能定位下次失效原因的管道。
    """
    end = min(end, _last_settled(end, now_hour))
    if start > end:
        start = end
    sd, ed = f"{start:%Y/%m/%d}", f"{end:%Y/%m/%d}"
    variants = [
        f"queryStartDate={sd}&queryEndDate={ed}&commodityId=TXF",
        f"firstDate=&lastDate=&queryStartDate={sd}&queryEndDate={ed}&commodityId=TXF",
        f"queryType=2&goDay=&doQuery=1&dateaddcnt=&queryStartDate={sd}"
        f"&queryEndDate={ed}&commodityId=TXF",
        f"queryStartDate={sd}&queryEndDate={ed}&commodityId=TX",
        f"queryStartDate={sd}&queryEndDate={ed}",          # 不帶商品：靠 _tx_rows_to_series 鎖 TX
    ]
    for i, body in enumerate(variants, 1):
        rows = _taifex_csv(_TX_URL, body, diag)
        got = _tx_rows_to_series(rows)
        if got:
            if diag is not None and i > 1:
                diag.append(f"變體 #{i} 成功（{len(got)} 筆）")
            return got
        if diag is not None and rows:
            diag.append(f"變體 #{i}：{len(rows)} 列但無 TX 外資列"
                        f"（首列={','.join(rows[0][:4])[:60]}）")
    # 逐日兜底（區間查詢整組失效時仍可能可用）
    out: dict[str, float] = {}
    d = end
    while d >= start:
        if d.weekday() < 5:
            got = _tx_rows_to_series(_taifex_csv(
                _TX_URL, f"queryDate={d:%Y/%m/%d}&commodityId=TXF", diag))
            out.update(got)
        d -= timedelta(days=1)
    if out and diag is not None:
        diag.append(f"逐日兜底成功（{len(out)} 筆）")
    return out


def _taifex_pc_ratio(start: date, end: date) -> dict[str, float]:
    """台指選擇權「買賣權未平倉量比率%」（P/C ratio，區間一次抓）→ {ISO日期: %}。
    官方 CSV 欄序：日期,賣權成交量,買權成交量,成交量比率%,賣權未平倉,買權未平倉,未平倉量比率% 。"""
    rows = _taifex_csv(
        "https://www.taifex.com.tw/cht/3/pcRatioDown",
        f"queryStartDate={start:%Y/%m/%d}&queryEndDate={end:%Y/%m/%d}")
    out: dict[str, float] = {}
    for cells in rows:
        iso = _cell_date(cells[0]) if cells else None
        if not iso or len(cells) < 7:
            continue
        try:
            val = float(cells[6].replace(",", ""))
        except ValueError:
            continue
        if val != 0:                                      # 0＝未結算，跳過（P/C 比不會為 0）
            out[iso] = val
    return out


# ── 資料層（載入／欄位級合併／存檔） ─────────────────────────────────

def load() -> dict | None:
    try:
        return json.loads(DATA_FP.read_text(encoding="utf-8"))
    except Exception:
        return None


def _merge(old: dict[str, float], new: dict[str, float]) -> dict[str, float]:
    """序列合併：新值（官方）覆蓋同日舊值（種子），整段抓不到＝保留舊序列；
    只留最近 _KEEP 筆。值為 None 一律不寫入（絕不洗空）。"""
    s = {k: v for k, v in (old or {}).items() if v is not None}
    s.update({k: v for k, v in (new or {}).items() if v is not None})
    return dict(sorted(s.items())[-_KEEP:])


def _missing_weekdays(series: dict[str, float], today: date,
                      now_hour: int | None = None,
                      today_after: int | None = None) -> list[date]:
    """近 _BACKFILL_DAYS 內、序列缺的平日（TWSE 逐日端點補抓用；假日端點會快速回非 OK）。

    today_after＝「今日資料的公布時點（台北整點）」：now_hour 已過該時點才把**今天**納入。
    2026-08-03 踩坑：舊版從 i=1 起算，**今天永遠被排除**——盤後場次（15:40／22:05）
    因此從不抓當日三大法人與融資融券，當日值要等隔天早上那班才補上，看起來就像
    「證交所抓不到」。實際上我們根本沒對今天發過請求。None＝維持只補歷史日。"""
    out = []
    start = 1
    if today_after is not None and now_hour is not None and now_hour >= today_after:
        start = 0                      # 已過公布時點 → 今天也納入
    for i in range(start, _BACKFILL_DAYS + 1):
        d = today - timedelta(days=i)
        if d.weekday() < 5 and d.isoformat() not in (series or {}):
            out.append(d)
    return out


def fetch() -> dict:
    """全指標抓取＋欄位級合併 → 新 doc（不落檔；落檔用 save）。每來源獨立降級。"""
    prev = load() or {}
    series: dict[str, dict] = {k: dict((prev.get("series") or {}).get(k) or {})
                               for k in ALL_KEYS}
    src: dict[str, dict] = dict(prev.get("src") or {})
    today = clock.today_tw()
    stamp = clock.stamp_tw()

    def _note(key, n, name):
        if n:
            src[key] = {"src": name, "fetched": stamp, "n": n}
        print(f"  {'✓' if n else '⚠'} {key}: {name} {'+' + str(n) + ' 筆' if n else '不可得（沿用既有序列）'}")

    # ① 全球溫度計 ← Yahoo（^TNX 為殖利率×10；sox/tsm_adr 收盤口徑、盤中 bar 不入檔）
    for key, _label, sym in GLOBAL_SPECS:
        new = _yahoo_series(sym, norm=_norm_yield if key == "us10y" else None,
                            close_only=key in _CLOSE_ONLY)
        series[key] = _merge(series[key], new)
        _note(key, len(new), f"yahoo:{sym}")

    # ② 三大法人買賣超（TWSE BFI82U，逐日補缺）：合計＋外資／投信／自營商分項
    n_flow = 0
    inst_src, inst_diag = "twse:BFI82U", []
    # 三大法人：證交所約 15:00 後公布 → 15 點後才把今天納入（盤後 15:40 場次即可抓到當日）
    for d in _missing_weekdays(series["inst_total"], today,
                               now_hour=clock.now_tw().hour, today_after=15):
        flows, used = _twse_inst_all(d, inst_diag)
        if flows:
            iso = d.isoformat()
            for key, fk in (("inst_total", "total"), ("inst_foreign", "foreign"),
                            ("inst_trust", "trust"), ("inst_dealer", "dealer")):
                if flows.get(fk) is not None:
                    series[key] = _merge(series[key], {iso: round(flows[fk], 1)})
            n_flow += 1
            inst_src = used          # 記實際生效的來源（官方／第三方）供 src 標記
    _note("inst_total", n_flow, inst_src)
    for line in inst_diag[:10]:      # 官方不可得時把各候選的 HTTP 狀態印進 CI 日誌
        print(f"      · {line}")
    if n_flow:                                            # 分項與合計同源
        for k in ("inst_foreign", "inst_trust", "inst_dealer"):
            src[k] = src["inst_total"]

    # ③ 融資融券餘額（TWSE MI_MARGN，逐日補缺）
    n_mar = 0
    # 融資融券：證交所晚間公布 → 21 點後才把今天納入（盤後 22:05 場次即可抓到當日）
    for d in _missing_weekdays(series["margin_bal"], today,
                               now_hour=clock.now_tw().hour, today_after=21):
        m = _twse_margin(d)
        if m:
            iso = d.isoformat()
            fin, short = m
            if fin is not None:
                series["margin_bal"] = _merge(series["margin_bal"], {iso: fin})
            if short is not None:
                series["short_bal"] = _merge(series["short_bal"], {iso: short})
            n_mar += 1
    _note("margin_bal", n_mar, "twse:MI_MARGN")
    if n_mar:
        src["short_bal"] = src["margin_bal"]

    # ④ 外資台指期淨部位＋選擇權 P/C 比（期交所，區間一次抓）
    start = today - timedelta(days=_BACKFILL_DAYS)
    diag: list[str] = []
    new = _taifex_tx_foreign(start, today, now_hour=clock.now_tw().hour, diag=diag)
    series["tx_foreign_net"] = _merge(series["tx_foreign_net"], new)
    _note("tx_foreign_net", len(new), "taifex:futContractsDate")
    for line in diag[:6]:                                 # 抓不到時把實際原因印進 CI 日誌
        print(f"      · {line}")
    new = _taifex_pc_ratio(start, today)
    series["pc_ratio"] = _merge(series["pc_ratio"], new)
    _note("pc_ratio", len(new), "taifex:pcRatio")

    return {"as_of": stamp, "series": series, "src": src}


def save(doc: dict) -> None:
    """落檔防呆：新 doc 某指標序列為空而既有落檔非空 → 不可能（_merge 保舊），
    但仍守「絕不把非空落檔洗成全空」的最後防線。"""
    old = load()
    if old and not any((doc.get("series") or {}).get(k) for k in ALL_KEYS) \
            and any((old.get("series") or {}).get(k) for k in ALL_KEYS):
        print("  ⚠ 本次全指標皆空、既有落檔非空 → 不覆寫")
        return
    DATA_FP.parent.mkdir(parents=True, exist_ok=True)
    DATA_FP.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


# ── 儀表板取數（最新值／日變化／N 日變化・累計／走勢點列） ─────────────

def _sorted_items(doc: dict | None, key: str) -> list[tuple[str, float]]:
    s = ((doc or {}).get("series") or {}).get(key) or {}
    return sorted((k, v) for k, v in s.items() if v is not None)

def latest(doc: dict | None, key: str) -> tuple[str, float] | None:
    items = _sorted_items(doc, key)
    return items[-1] if items else None


def day_change(doc: dict | None, key: str) -> float | None:
    """最新值 − 前一筆值（相鄰交易日）。序列不足 2 筆回 None。"""
    items = _sorted_items(doc, key)
    return round(items[-1][1] - items[-2][1], 4) if len(items) >= 2 else None


def change_n(doc: dict | None, key: str, n: int = 5) -> float | None:
    """最新值 − 往回第 n 筆值（近 n 個交易日變化）。史料不足回 None。"""
    items = _sorted_items(doc, key)
    return round(items[-1][1] - items[-1 - n][1], 4) if len(items) > n else None


def sum_n(doc: dict | None, key: str, n: int = 5) -> float | None:
    """最近 n 筆合計（買賣超金額「近 5 日累計」用）。不足 n 筆回 None（不以偏概全）。"""
    items = _sorted_items(doc, key)
    return round(sum(v for _, v in items[-n:]), 1) if len(items) >= n else None


def points(doc: dict | None, key: str, n: int = 30) -> list[float]:
    """走勢圖點列（最近 n 筆、依日期序）。"""
    return [v for _, v in _sorted_items(doc, key)[-n:]]


def vix_level(v: float | None) -> tuple[str, str] | None:
    """VIX 狀態標籤（中性敘述、非多空建議）→ (文字, css class)。"""
    if v is None:
        return None
    if v < 15:
        return "平靜", "calm"
    if v < 20:
        return "正常", "norm"
    if v < 30:
        return "偏高", "elev"
    return "恐慌", "panic"
