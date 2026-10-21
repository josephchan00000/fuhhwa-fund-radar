"""籌碼雷達：官方全市場端點（證交所／櫃買／集保）抓取與解析。

原則（同專案慣例）：
  · **一次請求拿全市場**，不逐檔打——每個交易日每個端點 1 個請求。
  · 解析走「表頭關鍵字定位」而非寫死欄序；表頭不在時才退回已知欄序。
  · 解析 0 列時把表頭與首列印進日誌（本容器 proxy 擋 twse/tpex，CI 日誌是唯一除錯管道）。
  · 抓不到＝回 None（呼叫端保留既有分片），**絕不把既有資料洗成空**。

日分片 `data/lab/mkt/{date}.json.gz` 的各部件（part）：
  q_tw  上市收盤  {code: [開, 高, 低, 收, 成交股數, 成交金額]}         ← MI_INDEX
  idx   指數      {"taiex": 收盤}                                       ← MI_INDEX
  q_tp  上櫃收盤  {code: [開, 高, 低, 收, 成交股數, 成交金額, 發行股數]} ← dailyQuotes
  i_tw  上市法人  {code: [外資(不含外資自營商), 投信, 自營商]} 股      ← T86
  i_tp  上櫃法人  同上                                                  ← 三大法人日報
  m_tw  上市信用  {code: [融資餘額, 融券餘額]} 張                       ← MI_MARGN
  m_tp  上櫃信用  同上                                                  ← 融資融券餘額
  l_tw  上市借券  {code: 借券賣出餘額(股)}                              ← TWT93U
  x_tw  上市外資  {code: [外資持股比率%, 發行股數]}                     ← MI_QFIIS
"""
from __future__ import annotations

import csv
import json
import re
import time

from ..http import get_bytes

UA_SLEEP_TWSE = 3.5      # 證交所 www 端有頻率限制（約每 5 秒 3 次），保守間隔
UA_SLEEP_TPEX = 1.6

TWSE = {
    "mi_index": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json",
    "t86": "https://www.twse.com.tw/rwd/zh/fund/T86?date={ymd}&selectType=ALLBUT0999&response=json",
    "margn": "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={ymd}&selectType=ALL&response=json",
    "sbl": "https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={ymd}&response=json",
    "qfii": "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date={ymd}&selectType=ALLBUT0999&response=json",
}
# 櫃買 2024 改版後新舊兩套網址並存——新站優先、舊站備援（日期民國／西元都試）
TPEX = {
    "quotes": [
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={roc}&type=EW&response=json",
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={ad}&type=EW&response=json",
    ],
    "insti": [
        "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={roc}&response=json",
        "https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={ad}&response=json",
        "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={roc}",
    ],
    "margin": [
        "https://www.tpex.org.tw/www/zh-tw/margin/balance?date={roc}&response=json",
        "https://www.tpex.org.tw/www/zh-tw/margin/balance?date={ad}&response=json",
        "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=json&d={roc}",
    ],
}
TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"

# 個股＋ETF 代號（排除權證 6 碼純數字、牛熊證等）
CODE_RE = re.compile(r"^(\d{4}[A-Z]?|00\d{2,4}[A-Z]?)$")
_TAG = re.compile(r"<[^>]+>")

LOG: list[str] = []      # 本輪診斷（呼叫端可整批印）
NAMES: dict[str, str] = {}  # 本輪解析價量時順手收的官方名稱（collect 併入 data/lab/names_mkt.json）


def log(msg: str) -> None:
    LOG.append(msg)
    print(f"  [lab] {msg}", flush=True)


# ── 共用小工具 ─────────────────────────────────────────────────────────

def num(x) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = _TAG.sub("", str(x)).replace(",", "").replace("+", "").strip()
    if s in ("", "--", "---", "-", "X", "除權息", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int(x) -> int | None:
    v = num(x)
    return None if v is None else int(round(v))


def tables(doc) -> list[tuple[list[str], list[list]]]:
    """rwd 回應的所有表 → [(表頭, 列)]。新版 tables 包裝、舊版頂層 fields/data、
    櫃買舊站 aaData（無表頭）都收。"""
    out: list[tuple[list[str], list[list]]] = []
    if not isinstance(doc, dict):
        return out
    cands = list(doc.get("tables") or []) + [doc]
    for t in cands:
        if not isinstance(t, dict):
            continue
        rows = t.get("data") or t.get("aaData") or []
        if not isinstance(rows, list) or not rows:
            continue
        fields = [str(f) for f in (t.get("fields") or [])]
        out.append((fields, rows))
    return out


def col(fields: list[str], *keys: str, nth: int = 0, excl: tuple[str, ...] = (),
        start: bool = False) -> int | None:
    """第 nth 個「含所有 keys、不含 excl」的欄位索引；start=True 時第一個 key 須為字首。"""
    hit = -1
    for i, f in enumerate(fields):
        f2 = f.replace(" ", "")
        if start and not f2.startswith(keys[0]):
            continue
        if all(k in f2 for k in keys) and not any(e in f2 for e in excl):
            hit += 1
            if hit == nth:
                return i
    return None


def _probe(name: str, fields, rows) -> None:
    head = "/".join(fields[:18]) if fields else "（無表頭）"
    first = json.dumps(rows[0], ensure_ascii=False)[:260] if rows else "（無列）"
    log(f"{name} 解析 0 列——表頭={head}｜首列={first}")


_BLOCK_STREAK = [0]


def _is_block_page(b: bytes) -> bool:
    """證交所頻率限制回的 611B XHTML 擋頁（2026-10-14 回補實測：144/564 請求中招）。"""
    return len(b) < 3000 and b.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))


def _get(url: str, *, sleep: float, timeout: int = 25):
    """GET → (doc, status)。status：ok／nodata（官方明示查無）／err。
    遇證交所擋頁：等 45 秒重試一次；連 3 次擋頁再多等 2 分鐘（讓 IP 冷卻，不硬撞）。"""
    b = b""
    for attempt in range(2):
        try:
            b = get_bytes(url, retries=2, timeout=timeout, use_cache=False)
        except Exception as e:                            # noqa: BLE001
            time.sleep(sleep)
            return None, f"err:{str(e)[:120]}"
        time.sleep(sleep)
        if not _is_block_page(b):
            _BLOCK_STREAK[0] = 0
            break
        _BLOCK_STREAK[0] += 1
        if _BLOCK_STREAK[0] >= 3:
            log(f"連續 {_BLOCK_STREAK[0]} 次擋頁，冷卻 120 秒")
            time.sleep(120)
        elif attempt == 0:
            time.sleep(45)
    txt = b.decode("utf-8", "replace").strip()
    if not txt.startswith("{") and not txt.startswith("["):
        return None, f"err:非 JSON（{len(b)}B 開頭 {txt[:60]!r}）"
    try:
        doc = json.loads(txt)
    except ValueError as e:
        return None, f"err:JSON 解析失敗 {e}"
    stat = str(doc.get("stat", "OK")) if isinstance(doc, dict) else "OK"
    if isinstance(doc, dict) and stat.upper() not in ("OK",) and "沒有" in stat:
        return doc, "nodata"
    if isinstance(doc, dict) and doc.get("stat") not in (None, "OK", "ok") and not tables(doc):
        return doc, "nodata"
    return doc, "ok"


def ymd(d: str) -> str:
    return d.replace("-", "")


def roc(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{int(y) - 1911}/{m}/{dd}"


def ad(d: str) -> str:
    return d.replace("-", "/")


# ── 證交所 ───────────────────────────────────────────────────────────

def parse_mi_index(doc) -> tuple[dict, dict]:
    """MI_INDEX → (q_tw, idx)。"""
    q: dict[str, list] = {}
    idx: dict[str, float] = {}
    for fields, rows in tables(doc):
        if col(fields, "收盤指數") is not None:
            ic = col(fields, "收盤指數")
            for r in rows:
                name = _TAG.sub("", str(r[0])).strip()
                if name == "發行量加權股價指數":
                    v = num(r[ic])
                    if v:
                        idx["taiex"] = v
        ci = col(fields, "證券代號")
        cc = col(fields, "收盤價")
        if ci is None or cc is None:
            continue
        co, ch, cl = col(fields, "開盤價"), col(fields, "最高價"), col(fields, "最低價")
        cv, cval = col(fields, "成交股數"), col(fields, "成交金額")
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if not CODE_RE.match(c):
                continue
            close = num(r[cc])
            if close is None:
                continue
            cn = col(fields, "證券名稱")
            if cn is not None:
                NAMES[c] = _TAG.sub("", str(r[cn])).strip()
            q[c] = [num(r[co]) if co is not None else None,
                    num(r[ch]) if ch is not None else None,
                    num(r[cl]) if cl is not None else None,
                    close,
                    _int(r[cv]) if cv is not None else None,
                    _int(r[cval]) if cval is not None else None]
    if not q:
        tb = tables(doc)
        if tb:
            _probe("MI_INDEX", *max(tb, key=lambda t: len(t[1])))
    return q, idx


def parse_t86(doc) -> dict:
    out: dict[str, list] = {}
    for fields, rows in tables(doc):
        ci = col(fields, "證券代號")
        if ci is None:
            continue
        cf = col(fields, "外陸資買賣超") if col(fields, "外陸資買賣超") is not None \
            else col(fields, "外資", "買賣超", "不含")
        ct = col(fields, "投信買賣超")
        cd = col(fields, "自營商買賣超", start=True)
        if cf is None or ct is None:
            _probe("T86", fields, rows)
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if CODE_RE.match(c):
                out[c] = [_int(r[cf]), _int(r[ct]), _int(r[cd]) if cd is not None else None]
    return out


def parse_margn(doc) -> dict:
    out: dict[str, list] = {}
    for fields, rows in tables(doc):
        ci = col(fields, "代號")
        cm = col(fields, "今日餘額", nth=0)
        cs = col(fields, "今日餘額", nth=1)
        if ci is None or cm is None or cs is None:
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if CODE_RE.match(c):
                out[c] = [_int(r[cm]), _int(r[cs])]
    if not out:
        tb = tables(doc)
        if tb:
            _probe("MI_MARGN", *max(tb, key=lambda t: len(t[1])))
    return out


def parse_sbl(doc) -> dict:
    """TWT93U：借券賣出「當日餘額」（融券那組叫「今日餘額」，以用字區分）。"""
    out: dict[str, int] = {}
    for fields, rows in tables(doc):
        ci = col(fields, "代號")
        cb = col(fields, "當日餘額")
        if cb is None:                    # 用字若改成兩組皆「今日餘額」→ 取第二組
            cb = col(fields, "今日餘額", nth=1)
        if ci is None or cb is None:
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            v = _int(r[cb])
            if CODE_RE.match(c) and v is not None:
                out[c] = v
    if not out:
        tb = tables(doc)
        if tb:
            _probe("TWT93U", *max(tb, key=lambda t: len(t[1])))
    return out


def parse_qfii(doc) -> dict:
    out: dict[str, list] = {}
    for fields, rows in tables(doc):
        ci = col(fields, "證券代號")
        cp = col(fields, "持股比率", excl=("尚可", "上限"))
        cs = col(fields, "發行股數")
        if ci is None or cp is None:
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if CODE_RE.match(c):
                out[c] = [num(r[cp]), _int(r[cs]) if cs is not None else None]
    if not out:
        tb = tables(doc)
        if tb:
            _probe("MI_QFIIS", *max(tb, key=lambda t: len(t[1])))
    return out


# ── 櫃買 ─────────────────────────────────────────────────────────────

def parse_tp_quotes(doc) -> dict:
    out: dict[str, list] = {}
    for fields, rows in tables(doc):
        if fields:
            ci, cc = col(fields, "代號"), col(fields, "收盤")
            co, ch, cl = col(fields, "開盤"), col(fields, "最高"), col(fields, "最低")
            cv = col(fields, "成交股數")
            cval = col(fields, "成交金額")
            ciss = col(fields, "發行股數")
        else:                       # 已知欄序：代號,名稱,收盤,漲跌,開盤,最高,最低,均價,成交股數,成交金額,…
            ci, cc, co, ch, cl, cv, cval, ciss = 0, 2, 4, 5, 6, 8, 9, None
        if ci is None or cc is None:
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if not CODE_RE.match(c):
                continue
            close = num(r[cc])
            if close is None:
                continue
            if len(r) > 1:
                NAMES[c] = _TAG.sub("", str(r[1])).strip()
            g = (lambda k: (num(r[k]) if k is not None and k < len(r) else None))
            out[c] = [g(co), g(ch), g(cl), close,
                      _int(r[cv]) if cv is not None and cv < len(r) else None,
                      _int(r[cval]) if cval is not None and cval < len(r) else None,
                      _int(r[ciss]) if ciss is not None and ciss < len(r) else None]
    if not out:
        tb = tables(doc)
        if tb:
            _probe("TPEx dailyQuotes", *max(tb, key=lambda t: len(t[1])))
    return out


def parse_tp_insti(doc) -> dict:
    out: dict[str, list] = {}
    for fields, rows in tables(doc):
        if fields:
            ci = col(fields, "代號")
            cf = col(fields, "外資及陸資", "不含", "買賣超")
            if cf is None:
                cf = col(fields, "外資", "買賣超", excl=("自營商",))
            ct = col(fields, "投信", "買賣超")
            cd = col(fields, "自營商", "買賣超", excl=("自行", "避險", "外資"))
        else:
            ci = cf = ct = cd = None
        # 2026-10-14 CI 實測：新站表頭把分組前綴拿掉了（只剩 7 組重複的「買進/賣出/買賣超股數」）
        # → 依已驗證欄序：外資(不含外資自營商) 4、投信 13、自營商合計 22、三大法人合計 23
        #   （樣本 00411A：-2,009,900＋-6,522,904＝-8,532,804 自洽）
        if cf is None and ((not fields) or sum("買賣超" in f for f in fields) >= 7):
            ci, cf, ct, cd = 0, 4, 13, 22
        if ci is None or cf is None or ct is None:
            _probe("TPEx 三大法人", fields, rows)
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if CODE_RE.match(c) and max(cf, ct) < len(r):
                out[c] = [_int(r[cf]), _int(r[ct]),
                          _int(r[cd]) if cd is not None and cd < len(r) else None]
    return out


def parse_tp_margin(doc) -> dict:
    out: dict[str, list] = {}
    for fields, rows in tables(doc):
        if fields:
            ci = col(fields, "代號")
            cm = col(fields, "資餘額", start=True)
            cs = col(fields, "券餘額", start=True)
        else:
            ci, cm, cs = 0, 6, 14
        if ci is None or cm is None or cs is None:
            _probe("TPEx 融資融券", fields, rows)
            continue
        for r in rows:
            c = _TAG.sub("", str(r[ci])).strip()
            if CODE_RE.match(c) and max(cm, cs) < len(r):
                out[c] = [_int(r[cm]), _int(r[cs])]
    return out


# ── 抓取入口 ─────────────────────────────────────────────────────────

MIN_ROWS = {"q_tw": 600, "i_tw": 500, "m_tw": 500, "l_tw": 300, "x_tw": 500,
            "q_tp": 300, "i_tp": 200, "m_tp": 200}


def _twse(part: str, d: str):
    key = {"q_tw": "mi_index", "i_tw": "t86", "m_tw": "margn", "l_tw": "sbl", "x_tw": "qfii"}[part]
    doc, st = _get(TWSE[key].format(ymd=ymd(d)), sleep=UA_SLEEP_TWSE)
    if st != "ok":
        return None, st, None
    if part == "q_tw":
        q, idx = parse_mi_index(doc)
        return q, "ok", idx
    fn = {"i_tw": parse_t86, "m_tw": parse_margn, "l_tw": parse_sbl, "x_tw": parse_qfii}[part]
    return fn(doc), "ok", None


def tpex_date_mismatch(doc, d: str) -> str | None:
    """櫃買回應自帶資料日——與請求日不同（例：假日或尚未公布時回最近交易日）→ 回 nodata 狀態字；
    相同或回應沒帶日期 → None。（籌碼雷達分片與 ETF 持股的指定日期報價共用，arm/dayquotes.py）"""
    rd = str((doc or {}).get("date") or "") if isinstance(doc, dict) else ""
    rd = re.sub(r"\D", "", rd)
    if len(rd) == 8 and rd != ymd(d):
        return f"nodata:回應日 {rd}≠{ymd(d)}"
    if len(rd) == 7 and f"{int(rd[:3]) + 1911}{rd[3:]}" != ymd(d):
        return f"nodata:回應日 {rd}≠{ymd(d)}"
    return None


def _tpex(part: str, d: str):
    key = {"q_tp": "quotes", "i_tp": "insti", "m_tp": "margin"}[part]
    fn = {"q_tp": parse_tp_quotes, "i_tp": parse_tp_insti, "m_tp": parse_tp_margin}[part]
    last = "err:無候選"
    for tmpl in TPEX[key]:
        doc, st = _get(tmpl.format(roc=roc(d), ad=ad(d)), sleep=UA_SLEEP_TPEX)
        if st != "ok":
            last = st
            continue
        bad = tpex_date_mismatch(doc, d)
        if bad:
            last = bad
            continue
        out = fn(doc)
        if out:
            return out, "ok", None
        last = "err:解析 0 列"
    return None, ("nodata" if last.startswith("nodata") else last), None


def fetch_part(part: str, d: str):
    """抓單一部件 → (資料或 None, 狀態, 附加)。資料列數低於門檻視為異常、不收。"""
    try:
        data, st, extra = (_twse if part.endswith("_tw") else _tpex)(part, d)
    except Exception as e:                                # noqa: BLE001
        return None, f"err:{type(e).__name__}: {str(e)[:100]}", None
    if data is not None and len(data) < MIN_ROWS.get(part, 1):
        return None, f"err:列數 {len(data)} 低於門檻 {MIN_ROWS.get(part)}", None
    return data, st, extra


ALL_PARTS = ("q_tw", "q_tp", "i_tw", "i_tp", "m_tw", "m_tp", "l_tw", "x_tw")
PX_PARTS = ("q_tw", "q_tp")
FLOW_PARTS = ("i_tw", "i_tp", "m_tw", "m_tp", "l_tw", "x_tw")


# ── 集保股權分散表（每週） ───────────────────────────────────────────

def parse_tdcc(txt: str) -> tuple[str | None, dict]:
    """→ (資料日 ISO, {code: [千張大戶%, 400張以上%, 總人數]})。
    分級：12=400,001-600,000 股…15=1,000,001 股以上；17＝合計。"""
    acc: dict[str, list] = {}
    ddate = None
    for r in csv.DictReader(txt.splitlines()):
        code = (r.get("證券代號") or "").strip()
        if not CODE_RE.match(code):
            continue
        lvl = (r.get("持股分級") or "").strip()
        k = next((k for k in r if k and "比例" in k), None)
        pct = num(r.get(k)) if k else None
        ddate = ddate or (r.get("資料日期") or "").strip()
        a = acc.setdefault(code, [0.0, 0.0, None])
        if lvl in ("12", "13", "14", "15") and pct is not None:
            a[1] += pct
            if lvl == "15":
                a[0] = pct
        elif lvl == "17":
            a[2] = _int(r.get("人數"))
    iso = f"{ddate[:4]}-{ddate[4:6]}-{ddate[6:8]}" if ddate and len(ddate) == 8 else None
    out = {c: [round(v[0], 2), round(v[1], 2), v[2]] for c, v in acc.items()}
    return iso, out


def fetch_tdcc() -> tuple[str | None, dict]:
    from ..connectors import tdcc
    txt = tdcc._fetch_csv(ttl=6 * 3600)                   # 沿用既有連接器（含憑證怪癖處理）
    if not txt:
        log("TDCC 1-5 取不到")
        return None, {}
    iso, out = parse_tdcc(txt)
    if len(out) < 1000:
        log(f"TDCC 解析偏少：{len(out)} 檔（資料日 {iso}）")
    return iso, out


# ── 第二階段資料源探針（00919／00929 預測需股利、EPS；2026-10-14） ──────────
# 只印可達性與表頭，不落檔。結果用來決定第二階段要接哪幾支端點。
PROBE2 = {
    "TWSE 除權息計算結果（區間）": "https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate={y0}&endDate={ymd}&response=json",
    "TWSE 本益比殖利率（單日）": "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json",
    "TWSE openapi 本益比殖利率": "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "TWSE openapi 綜合損益表(一般業)": "https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci",
    "TWSE openapi 股利分派": "https://openapi.twse.com.tw/v1/opendata/t187ap45_L",
    "TPEx openapi 本益比殖利率": "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
    "TPEx openapi 除權息": "https://www.tpex.org.tw/openapi/v1/tpex_exright_daily",
    "TPEx openapi 綜合損益表(一般業)": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci",
}


def probe2(d: str) -> None:
    y0 = f"{int(d[:4]) - 1}{d[5:7]}{d[8:10]}"
    for name, tmpl in PROBE2.items():
        url = tmpl.format(ymd=ymd(d), y0=y0)
        try:
            b = get_bytes(url, retries=1, timeout=20, use_cache=False)
        except Exception as e:                            # noqa: BLE001
            print(f"[probe2] {name}: ✗ {str(e)[:120]}")
            continue
        time.sleep(UA_SLEEP_TWSE)
        try:
            doc = json.loads(b.decode("utf-8", "replace"))
        except ValueError:
            print(f"[probe2] {name}: 非 JSON {len(b)}B {b[:80]!r}")
            continue
        if isinstance(doc, list):
            first = doc[0] if doc else {}
            print(f"[probe2] {name}: list {len(doc)} 列；鍵名={list(first)[:20] if isinstance(first, dict) else type(first).__name__}；"
                  f"首列={json.dumps(first, ensure_ascii=False)[:260]}")
            continue
        tb = tables(doc)
        if not tb:
            print(f"[probe2] {name}: stat={doc.get('stat') if isinstance(doc, dict) else '?'} 無表；鍵={list(doc)[:10] if isinstance(doc, dict) else ''}")
            continue
        f, rows = max(tb, key=lambda t: len(t[1]))
        print(f"[probe2] {name}: {len(rows)} 列；表頭={'/'.join(f[:20])}；首列={json.dumps(rows[0], ensure_ascii=False)[:260]}")


# ── 歷史價量備援：Yahoo 逐檔日線（2026-10-14） ─────────────────────────────
# 證交所 MI_INDEX 逐日回補被頻率限制卡死（兩輪 100 分鐘只補到 6/3），改以 Yahoo 逐檔
# 一次取兩年日線，只補「官方分片沒有的日子」。Yahoo 對台股偶有不可能的 bar（2026-09-20
# 週日 bar 事件）與盤中未收盤 bar → 週末與今日以後一律丟掉。

def yahoo_hist(sym: str, *, rng: str = "2y") -> dict[str, list]:
    import urllib.parse
    from datetime import datetime

    from .. import clock
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range={rng}&interval=1d"
    try:
        doc = json.loads(get_bytes(url, retries=2, timeout=20, use_cache=False).decode("utf-8"))
    except Exception as e:                                # noqa: BLE001
        log(f"Yahoo {sym} ✗ {str(e)[:80]}")
        return {}
    res = (((doc or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    today = clock.today_tw().isoformat()
    out = {}
    for i, t in enumerate(ts):
        d = datetime.fromtimestamp(int(t), clock.TW_TZ).date()
        if d.weekday() >= 5 or d.isoformat() >= today:
            continue

        def g(k):
            arr = q.get(k) or []
            v = arr[i] if i < len(arr) else None
            return None if v is None else round(float(v), 4)
        c = g("close")
        if c:
            v = g("volume")
            out[d.isoformat()] = [g("open"), g("high"), g("low"), c, None if v is None else int(v)]
    return out



# 長線成長股所需資料源探針（2026-10-14：月營收、投信歷史、財報歷史）
PROBE3 = {
    "TWSE openapi 月營收": "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
    "TPEx openapi 月營收": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",
    "TWSE T86 兩年前": "https://www.twse.com.tw/rwd/zh/fund/T86?date={y2}&selectType=ALLBUT0999&response=json",
    "FinMind 法人買賣（2330 兩年）": "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id=2330&start_date={y2d}&end_date={dd}",
    "FinMind 月營收（2330）": "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id=2330&start_date=2023-01-01&end_date={dd}",
    "FinMind 綜合損益（2330）": "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=2330&start_date=2023-01-01&end_date={dd}",
}


def probe3(d: str) -> None:
    y2 = f"{int(d[:4]) - 2}{d[5:7]}{d[8:10]}"
    for name, tmpl in PROBE3.items():
        url = tmpl.format(y2=y2, y2d=f"{int(d[:4]) - 2}{d[4:]}", dd=d)
        try:
            b = get_bytes(url, retries=1, timeout=30, use_cache=False)
        except Exception as e:                            # noqa: BLE001
            print(f"[probe3] {name}: ✗ {str(e)[:140]}")
            continue
        time.sleep(UA_SLEEP_TWSE)
        try:
            doc = json.loads(b.decode("utf-8", "replace"))
        except ValueError:
            print(f"[probe3] {name}: 非 JSON {len(b)}B {b[:80]!r}")
            continue
        if isinstance(doc, dict) and isinstance(doc.get("data"), list) and "msg" in doc:   # FinMind
            rows = doc["data"]
            print(f"[probe3] {name}: msg={doc.get('msg')} status={doc.get('status')} {len(rows)} 列；"
                  f"首列={json.dumps(rows[0], ensure_ascii=False)[:220] if rows else '—'}；"
                  f"末列={json.dumps(rows[-1], ensure_ascii=False)[:160] if rows else '—'}")
            continue
        if isinstance(doc, list):
            first = doc[0] if doc else {}
            print(f"[probe3] {name}: list {len(doc)} 列；鍵名={list(first)[:22] if isinstance(first, dict) else ''}；"
                  f"首列={json.dumps(first, ensure_ascii=False)[:300]}")
            continue
        tb = tables(doc)
        print(f"[probe3] {name}: stat={doc.get('stat') if isinstance(doc, dict) else '?'} "
              f"{(len(max(tb, key=lambda t: len(t[1]))[1]) if tb else 0)} 列")


# ── 月營收（官方 openapi，上市＋上櫃各一請求；2026-10-14 探針確認可達） ─────────
REV_URLS = ("https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O")


def parse_revenue(rows) -> tuple[str | None, dict]:
    """→ (資料年月 YYYY-MM, {code: [當月營收(千元), 年增%, 累計年增%]})。"""
    out, ym = {}, None
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        code = str(r.get("公司代號") or "").strip()
        if not CODE_RE.match(code):
            continue
        k = str(r.get("資料年月") or "").strip()
        if len(k) == 5 and k.isdigit():
            ym = ym or f"{int(k[:3]) + 1911:04d}-{k[3:]}"
        rev = num(r.get("營業收入-當月營收"))
        yoy = num(r.get("營業收入-去年同月增減(%)"))
        cy = num(r.get("累計營業收入-前期比較增減(%)"))
        out[code] = [rev, None if yoy is None else round(yoy, 2), None if cy is None else round(cy, 2)]
    return ym, out


def fetch_revenue() -> tuple[str | None, dict]:
    ym, out = None, {}
    for url in REV_URLS:
        try:
            rows = json.loads(get_bytes(url, retries=2, timeout=30, use_cache=False).decode("utf-8"))
        except Exception as e:                            # noqa: BLE001
            log(f"月營收 ✗ {url[:60]} {str(e)[:80]}")
            continue
        y, o = parse_revenue(rows)
        ym = ym or y
        out.update(o)
    return ym, out


# ── 月營收全市場歷史（S26，2026-10-15）：MOPS 營業收入彙總表（上市／上櫃 × 國內／國外 KY），一個月一個市場一請求 ─────
MOPS_REV = "https://{host}/nas/t21/{mkt}/t21sc03_{roc}_{m}_{k}.html"
MOPS_HOSTS = ("mopsov.twse.com.tw", "mops.twse.com.tw")
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def _decode(b: bytes) -> str:
    for enc in ("utf-8", "cp950", "big5"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def parse_mops_rev(html: str) -> dict[str, list]:
    """MOPS 營業收入彙總表 → {code: [當月營收(千元), 去年同月增減%, 累計增減%]}（同 parse_revenue 的格式）。
    欄序：公司代號｜公司名稱｜當月營收｜上月營收｜去年當月營收｜上月比較%｜去年同月%｜當月累計｜去年累計｜前期比較%｜備註。"""
    out = {}
    for row in _TR.findall(html):
        cells = [_TAG.sub("", c).replace("&nbsp;", "").strip() for c in _TD.findall(row)]
        if len(cells) < 10 or not re.fullmatch(r"\d{4}", cells[0] or ""):
            continue
        rev = num(cells[2])
        if rev is None:
            continue
        yoy, cy = num(cells[6]), num(cells[9])
        out[cells[0]] = [rev, None if yoy is None else round(yoy, 2), None if cy is None else round(cy, 2)]
    return out


_MOPS_HOST_OK: list[str] = []


def fetch_mops_rev(mkt: str, y: int, m: int, k: int = 0) -> dict[str, list] | None:
    """MOPS 營業收入彙總表一頁（mkt＝sii 上市／otc 上櫃；k＝0 國內、1 國外）。抓不到回 None；能用的主機記下來先試。"""
    hosts = list(dict.fromkeys(_MOPS_HOST_OK + list(MOPS_HOSTS)))
    for host in hosts:
        url = MOPS_REV.format(host=host, mkt=mkt, roc=y - 1911, m=m, k=k)
        try:
            b = get_bytes(url, retries=2, timeout=25, use_cache=False)
        except Exception as e:                            # noqa: BLE001
            log(f"MOPS 月營收 ✗ {url} {str(e)[:120]}")
            continue
        d = parse_mops_rev(_decode(b))
        if d or k == 1:                                   # 國外（KY）頁可能本來就很少
            if host not in _MOPS_HOST_OK:
                _MOPS_HOST_OK.insert(0, host)
            return d
        log(f"MOPS 月營收 解析 0 檔 {url}（{len(b)}B）開頭 {_decode(b)[:120]!r}")
    return None


def probe_rev() -> None:
    """探針：MOPS 彙總表（兩個主機 × 上市／上櫃、新舊兩個月份）與 FinMind（不帶代號一次拿全市場；單檔）。只印不寫。"""
    for y, m in ((2024, 9), (2020, 1)):
        for host in MOPS_HOSTS:
            for mkt in ("sii", "otc"):
                url = MOPS_REV.format(host=host, mkt=mkt, roc=y - 1911, m=m, k=0)
                try:
                    b = get_bytes(url, retries=1, timeout=20, use_cache=False)
                    h = _decode(b)
                    d = parse_mops_rev(h)
                    smp = {k: d[k] for k in ("2330", "2454", "3105", "6488") if k in d}
                    log(f"[revprobe] {url} → {len(b)}B、解析 {len(d)} 檔、樣本 {smp}、開頭 {h[:160]!r}")
                except Exception as e:                    # noqa: BLE001
                    log(f"[revprobe] {url} ✗ {str(e)[:200]}")
                time.sleep(1.5)
    for url in ("https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&start_date=2024-10-01&end_date=2024-10-31",):
        try:
            doc = json.loads(get_bytes(url, retries=1, timeout=40, use_cache=False).decode("utf-8"))
            rows = doc.get("data") or [] if isinstance(doc, dict) else []
            log(f"[revprobe] FinMind 全市場 status={doc.get('status') if isinstance(doc, dict) else '?'} "
                f"msg={str(doc.get('msg') if isinstance(doc, dict) else '')[:120]} 列數 {len(rows)} "
                f"檔數 {len({r.get('stock_id') for r in rows})} 首列 {rows[:1]}")
        except Exception as e:                            # noqa: BLE001
            log(f"[revprobe] FinMind 全市場 ✗ {str(e)[:200]}")
    rows = finmind("TaiwanStockMonthRevenue", "2330", "2020-01-01")
    if isinstance(rows, list):
        log(f"[revprobe] FinMind 2330 單檔 {len(rows)} 列 首 {rows[:1]} 末 {rows[-1:]}")
    else:
        log(f"[revprobe] FinMind 2330 單檔 → {rows}")



def finmind_revenue(code: str, start: str = "2023-01-01") -> dict[str, float]:
    """FinMind 月營收歷史（第三方整理官方數字；只用在回測）→ {YYYY-MM: 營收(元)}。"""
    from .. import clock
    url = ("https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue"
           f"&data_id={code}&start_date={start}&end_date={clock.today_tw().isoformat()}")
    try:
        doc = json.loads(get_bytes(url, retries=2, timeout=30, use_cache=False).decode("utf-8"))
    except Exception as e:                                # noqa: BLE001
        log(f"FinMind 月營收 {code} ✗ {str(e)[:80]}")
        return {}
    if not isinstance(doc, dict) or doc.get("status") not in (200, "200"):
        log(f"FinMind 月營收 {code} status={doc.get('status') if isinstance(doc, dict) else '?'} "
            f"msg={str(doc.get('msg') if isinstance(doc, dict) else '')[:80]}")
        return {}
    out = {}
    for r in doc.get("data") or []:
        y, m, v = r.get("revenue_year"), r.get("revenue_month"), r.get("revenue")
        if y and m and v:
            out[f"{int(y):04d}-{int(m):02d}"] = float(v)
    return out


# ── 高股息研究資料（2026-10-14 使用者：「幫我套用在高股息ETF」）───────────────────
# 證交所除權息計算結果表：區間查詢一次回整年所有除權息事件（2026-10-14 probe2 實測 1 年 1,490 列）。
# 表頭：資料日期（民國「114年10月13日」）/股票代號/股票名稱/除權息前收盤價/除權息參考價/權值+息值/權/息/…
# 「息」＝現金股利；「權息」只有合計值（配股另計），先照記、用的時候標示。上櫃股與 EPS 走 FinMind（同日 probe3 實測可達）。

def _roc_date(s) -> str | None:
    m = re.search(r"(\d{2,3})\D+(\d{1,2})\D+(\d{1,2})", str(s or ""))
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    return f"{y + 1911:04d}-{mo:02d}-{d:02d}"


def parse_twt49u(doc) -> list[list]:
    """→ [[除權息日 ISO, 代號, 權值+息值, 權/息, 除權息前收盤價, 除權息參考價]]。
    前收盤價是「當時」每股價格——用來把股利換算到價量序列的口徑（面額變更、配股後 Yahoo 歷史價會被還原）。"""
    out = []
    for fields, rows in tables(doc):
        cd, cc = col(fields, "資料日期"), col(fields, "股票代號")
        cv, ct = col(fields, "權值+息值", "權值"), col(fields, "權/息")
        cp, cr = col(fields, "前收盤"), col(fields, "參考價", excl=("減除",))
        if None in (cd, cc, cv, ct):
            continue
        for r in rows:
            c = _TAG.sub("", str(r[cc])).strip()
            d = _roc_date(r[cd])
            v = num(r[cv])
            if CODE_RE.match(c) and d and v is not None:
                out.append([d, c, v, _TAG.sub("", str(r[ct])).strip(),
                            num(r[cp]) if cp is not None else None, num(r[cr]) if cr is not None else None])
    if not out:
        tb = tables(doc)
        if tb:
            _probe("TWT49U", *max(tb, key=lambda t: len(t[1])))
    return out


def twse_exright_year(y: int) -> list[list]:
    url = (f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate={y}0101&endDate={y}1231&response=json")
    try:
        doc = json.loads(get_bytes(url, retries=2, timeout=30, use_cache=False).decode("utf-8", "replace"))
    except Exception as e:                                # noqa: BLE001
        log(f"TWT49U {y} ✗ {str(e)[:100]}")
        return []
    return parse_twt49u(doc)


# ── 回測 v3 資料探針（docs/backtest_v3_plan.md 第 2、7 節；只印不寫） ──────────────────
def _peek(name: str, url: str, *, timeout: int = 40) -> object:
    """抓一次、印狀態與內容摘要；回傳解析後的 JSON（或原始文字）。"""
    try:
        b = get_bytes(url, retries=1, timeout=timeout, use_cache=False)
    except Exception as e:                                # noqa: BLE001
        log(f"[v3探針] {name} ✗ {str(e)[:160]}")
        return None
    txt = _decode(b).strip()
    try:
        doc = json.loads(txt)
    except ValueError:
        log(f"[v3探針] {name} 非 JSON {len(b)}B 開頭 {txt[:160]!r}")
        return txt
    if isinstance(doc, dict):
        keys = list(doc)[:12]
        info = {k: (doc[k] if isinstance(doc[k], (str, int, float)) else type(doc[k]).__name__) for k in keys}
        rows = doc.get("data") or doc.get("aaData") or doc.get("tables") or []
        n = len(rows) if isinstance(rows, list) else "?"
        log(f"[v3探針] {name} OK {len(b)}B 鍵 {info} 列數 {n}")
        if isinstance(rows, list) and rows:
            log(f"[v3探針]   首列 {str(rows[0])[:300]}")
            log(f"[v3探針]   末列 {str(rows[-1])[:300]}")
        for k in ("fields", "title"):
            if doc.get(k):
                log(f"[v3探針]   {k} {str(doc[k])[:300]}")
    else:
        log(f"[v3探針] {name} OK {len(b)}B list {len(doc)} 首筆 {str(doc[:1])[:300]}")
    return doc


def probe_v3() -> None:
    from .. import clock
    today = clock.today_tw().isoformat()
    fm = "https://api.finmindtrade.com/api/v4/data?dataset={ds}{cid}&start_date={a}&end_date=" + today
    # 1) 加權報酬指數（含息）
    for d in ("20140101", "20240101"):
        _peek(f"證交所加權報酬指數 MFI94U {d}", f"https://www.twse.com.tw/rwd/zh/TAIEX/MFI94U?date={d}&response=json")
        time.sleep(3)
    # 2) 歷史發行股數：證交所外資持股表（全市場一日一請求）、櫃買日收盤
    doc = _peek("證交所 MI_QFIIS 2014-01-02", "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date=20140102&selectType=ALLBUT0999&response=json")
    if isinstance(doc, dict):
        for f_, rows in tables(doc):
            log(f"[v3探針]   MI_QFIIS 欄位 {f_[:12]}")
            for r in rows:
                if str(r[0]).strip() == "2330":
                    log(f"[v3探針]   MI_QFIIS 2330 {r[:12]}")
    time.sleep(3)
    for d in ("2014-01-02", "2019-01-02"):
        try:
            res, st = fetch_part("q_tp", d)
            log(f"[v3探針] 櫃買日收盤 {d} 狀態 {st} 檔數 {len(res or {})} 樣本 {str(list((res or {}).items())[:2])[:200]}")
        except Exception as e:                            # noqa: BLE001
            log(f"[v3探針] 櫃買日收盤 {d} ✗ {str(e)[:160]}")
        time.sleep(2)
    # 3) 上櫃除權息
    _peek("櫃買除權息（舊站）2024", "https://www.tpex.org.tw/web/stock/exright/dailyquo/exDailyQ_result.php?l=zh-tw&d=113/01/01&ed=113/12/31&o=json")
    _peek("櫃買除權息（新站）2024", "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ?startDate=2024/01/01&endDate=2024/12/31&response=json")
    _peek("FinMind 除權息結果 5347", fm.format(ds="TaiwanStockDividendResult", cid="&data_id=5347", a="2013-01-01"))
    # 4) 月營收彙總表 2012／2013
    for y in (2012, 2013):
        for mkt, smp in (("sii", "2330"), ("otc", "5347")):
            d = fetch_mops_rev(mkt, y, 1, 0)
            log(f"[v3探針] MOPS 月營收 {y}-01 {mkt}：{len(d or {})} 檔 {smp}={None if d is None else d.get(smp)}")
            time.sleep(2)
    # 5) Yahoo 長歷史與已下市股票
    for sym in ("2330.TW", "2311.TW", "2325.TW", "3474.TW", "2448.TW", "5347.TWO"):
        h = yahoo_hist(sym, rng="max")
        ks = sorted(h)
        log(f"[v3探針] Yahoo {sym}：{len(ks)} 日 {ks[:1]}～{ks[-1:]}")
        time.sleep(1)
    # 6) FinMind：已下市股價、下市清單、單季 EPS 起點、歷史發行股數
    _peek("FinMind 股價 2311（已下市）", fm.format(ds="TaiwanStockPrice", cid="&data_id=2311", a="2014-01-01"))
    _peek("FinMind 下市清單", fm.format(ds="TaiwanStockDelisting", cid="", a="2013-01-01"))
    doc = _peek("FinMind 綜合損益 2330（2012 起）", fm.format(ds="TaiwanStockFinancialStatements", cid="&data_id=2330", a="2012-01-01"))
    if isinstance(doc, dict) and doc.get("data"):
        eps = [r for r in doc["data"] if r.get("type") == "EPS"]
        log(f"[v3探針]   EPS {len(eps)} 季 首 {eps[:1]} 末 {eps[-1:]}")
    doc = _peek("FinMind 外資持股（含發行股數）2330", fm.format(ds="TaiwanStockShareholding", cid="&data_id=2330", a="2014-01-01"))
    # 7) 證交所除權息 2014
    rows = twse_exright_year(2014)
    log(f"[v3探針] TWT49U 2014：{len(rows)} 列 樣本 {rows[:2]}")


def yahoo_hist_from(sym: str, start: str, *, adj: bool = False) -> dict[str, list]:
    """Yahoo 日線（指定起日，period1／period2；range=max 會被降成月線）。格式同 yahoo_hist；
    adj＝True 時每列多一欄還原收盤（adjclose：還原現金股利；Yahoo 的 o／h／l／c 已還原股票股利與分割）。"""
    import urllib.parse
    from datetime import datetime, timezone

    from .. import clock
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.now(timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1={p1}&period2={p2}&interval=1d")
    try:
        doc = json.loads(get_bytes(url, retries=2, timeout=30, use_cache=False).decode("utf-8"))
    except Exception as e:                                # noqa: BLE001
        log(f"Yahoo {sym} ✗ {str(e)[:80]}")
        return {}
    res = (((doc or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    aj = ((((res.get("indicators") or {}).get("adjclose") or [{}])[0]) or {}).get("adjclose") or []
    today = clock.today_tw().isoformat()
    out = {}
    for i, t in enumerate(ts):
        d = datetime.fromtimestamp(int(t), clock.TW_TZ).date()
        if d.weekday() >= 5 or d.isoformat() >= today:
            continue

        def g(k):
            arr = q.get(k) or []
            v = arr[i] if i < len(arr) else None
            return None if v is None else round(float(v), 4)
        c = g("close")
        if c:
            v = g("volume")
            row = [g("open"), g("high"), g("low"), c, None if v is None else int(v)]
            if adj:
                a = aj[i] if i < len(aj) else None
                row.append(None if a is None else round(float(a), 6))
            out[d.isoformat()] = row
    return out


def parse_mfi94u(doc) -> dict[str, float]:
    """證交所發行量加權股價報酬指數（月表）→ {日期: 指數}。"""
    out = {}
    for fields, rows in tables(doc):
        for r in rows:
            d = _roc_date(r[0]) if r else None
            v = num(r[1]) if len(r) > 1 else None
            if d and v:
                out[d] = v
    return out


def twse_tr_month(y: int, m: int) -> dict[str, float] | None:
    """一個月的加權報酬指數；抓不到回 None（呼叫端下一輪再試）。"""
    doc, st = _get(f"https://www.twse.com.tw/rwd/zh/TAIEX/MFI94U?date={y:04d}{m:02d}01&response=json",
                   sleep=UA_SLEEP_TWSE)
    if st == "nodata":
        return {}
    return parse_mfi94u(doc) if st == "ok" else None


def parse_tp_exright(doc) -> list[list]:
    """櫃買除權息計算結果表 → [[除權息日 ISO, 代號, 除權息前收盤價, 除權息參考價, 現金股利, 每仟股無償配股]]。"""
    out = []
    for fields, rows in tables(doc):
        cd, cc = col(fields, "除權息日期"), col(fields, "代號")
        cp, cr = col(fields, "前收盤"), col(fields, "參考價", excl=("減除",))
        cs, ck = col(fields, "現金股利"), col(fields, "無償配股")
        if None in (cd, cc, cp, cr):
            continue
        for r in rows:
            c = _TAG.sub("", str(r[cc])).strip()
            d = _roc_date(r[cd])
            if CODE_RE.match(c) and d:
                out.append([d, c, num(r[cp]), num(r[cr]), num(r[cs]) if cs is not None else None,
                            num(r[ck]) if ck is not None else None])
    if not out:
        tb = tables(doc)
        if tb:
            _probe("櫃買除權息", *max(tb, key=lambda t: len(t[1])))
    return out


def tpex_exright_year(y: int) -> list[list] | None:
    r = y - 1911
    url = (f"https://www.tpex.org.tw/web/stock/exright/dailyquo/exDailyQ_result.php?l=zh-tw"
           f"&d={r}/01/01&ed={r}/12/31&o=json")
    doc, st = _get(url, sleep=UA_SLEEP_TPEX, timeout=40)
    if st != "ok":
        log(f"櫃買除權息 {y} {st}")
        return None
    return parse_tp_exright(doc)


def probe_fs() -> None:
    """公司財報分析（docs/lab_company_plan.md）資料源探針：MOPS 彙總表（資產負債、綜合損益、現金流量候選、營益分析）
    每張表的欄名、列數、樣本列。只印不寫；總時間上限 9 分鐘、每個請求印耗時（2026-10-16 第一版卡 30 分鐘才改）。"""
    import functools
    pr = functools.partial(print, flush=True)
    t_all = time.time()
    eps = [("t163sb05", "資產負債", "sii"), ("t163sb04", "綜合損益", "sii"), ("t163sb20", "候選：現金流量", "sii"),
           ("t163sb06", "營益分析", "sii"), ("t163sb05", "資產負債", "otc"), ("t163sb04", "綜合損益", "otc")]
    for ep, nm, mkt in eps:
        if time.time() - t_all > 540:
            pr("[probe-fs] 超過時間上限，停")
            break
        t0 = time.time()
        try:
            b = post_bytes(f"https://mopsov.twse.com.tw/mops/web/ajax_{ep}",
                           {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "isQuery": "Y",
                            "TYPEK": mkt, "year": 115, "season": "02"}, retries=1, timeout=40)
        except Exception as e:                            # noqa: BLE001
            pr(f"[probe-fs] {ep} {mkt} ✗ {time.time() - t0:.0f}s {str(e)[:160]}")
            continue
        h = _decode(b)
        tbs = re.findall(r"<table[^>]*>(.*?)</table>", h, re.S | re.I)
        pr(f"[probe-fs] {ep}（{nm}）{mkt}：{len(b)}B、{time.time() - t0:.0f}s、表 {len(tbs)} 張、"
           f"開頭 {_TAG.sub(' ', h[:300]).split()[:12]}")
        for k, tb in enumerate(tbs):
            rows = [[_TAG.sub("", c).replace("&nbsp;", "").strip() for c in _TD.findall(tr)] for tr in _TR.findall(tb)]
            head = next((r for r in rows if any("公司代號" in c for c in r)), None)
            if not head:
                continue
            data = [r for r in rows if r and re.fullmatch(r"\d{4}", r[0] or "")]
            smp = next((r for r in data if r[0] in ("2330", "1301", "2881", "6488", "2882")), data[0] if data else None)
            pr(f"  表{k}：{len(data)} 列｜欄 {len(head)}：{' | '.join(head)}")
            if smp:
                pr(f"     樣本：{' | '.join(smp)}")
        time.sleep(3)
    pr(f"[probe-fs] 結束，共 {time.time() - t_all:.0f}s")


def probe_v3b() -> None:
    """回測 v3 第二輪探針：櫃買歷史日收盤（含發行股數）、Yahoo 指定起日的日線、FinMind 不帶代號的整批查詢、
    櫃買 2013 年除權息、FinMind 外資持股欄位。只印不寫。"""
    from .. import clock
    today = clock.today_tw().isoformat()
    for d in ("2014-01-02", "2019-01-02", "2024-01-02"):
        data, st, _ = fetch_part("q_tp", d)
        smp = {k: (data or {}).get(k) for k in ("5347", "8299", "6488")}
        log(f"[v3探針b] 櫃買日收盤 {d}：狀態 {st} 檔數 {len(data or {})} 樣本 {smp}")
        time.sleep(2)
    for sym in ("2330.TW", "5347.TWO", "^TWII"):
        h = yahoo_hist_from(sym, "2013-01-01")
        ks = sorted(h)
        log(f"[v3探針b] Yahoo 日線 {sym} 2013 起：{len(ks)} 日 {ks[:2]}～{ks[-1:]} 首筆 {h.get(ks[0]) if ks else None}")
        time.sleep(1)
    fm = "https://api.finmindtrade.com/api/v4/data?dataset={ds}&start_date={a}&end_date={z}"
    _peek("FinMind 綜合損益 不帶代號 2014Q1", fm.format(ds="TaiwanStockFinancialStatements", a="2014-03-31", z="2014-03-31"))
    _peek("FinMind 股價 不帶代號 2014-01-02", fm.format(ds="TaiwanStockPrice", a="2014-01-02", z="2014-01-02"))
    _peek("FinMind 股票清單", "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo")
    _peek("櫃買除權息（舊站）2013", "https://www.tpex.org.tw/web/stock/exright/dailyquo/exDailyQ_result.php?l=zh-tw&d=102/01/01&ed=102/12/31&o=json")
    doc = _peek("FinMind 外資持股 6488（2014-01）", "https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockShareholding"
                f"&data_id=6488&start_date=2014-01-01&end_date=2014-01-10")
    if isinstance(doc, dict) and doc.get("data"):
        log(f"[v3探針b]   外資持股欄位 {list(doc['data'][0])}")
    log(f"[v3探針b] 完成 {today}")


def post_bytes(url: str, form: dict, *, timeout: int = 60, retries: int = 2) -> bytes:
    """表單 POST（公開資訊觀測站 ajax 查詢用）。"""
    import ssl
    import urllib.parse
    import urllib.request

    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    data = urllib.parse.urlencode(form).encode()
    err = None
    for k in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={
                "User-Agent": "Mozilla/5.0 (FH-ARM research bot; contact: marketing)",
                "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read()
        except Exception as e:                            # noqa: BLE001
            err = e
            time.sleep(2 * (k + 1))
    raise RuntimeError(f"POST 失敗 {url}: {err}")


def parse_mops_is(html: str) -> dict[str, float]:
    """公開資訊觀測站「綜合損益表彙總」（t163sb04）→ {代號: 基本每股盈餘（元）}（該季報表的累計值）。"""
    out: dict[str, float] = {}
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows = [[_TAG.sub("", c).replace("&nbsp;", "").strip() for c in _TD.findall(tr)] for tr in _TR.findall(tb)]
        head = next((r for r in rows if any("公司代號" in c for c in r)), None)
        if not head:
            continue
        ci = next((i for i, c in enumerate(head) if "公司代號" in c), None)
        ce = next((i for i, c in enumerate(head) if "基本每股盈餘" in c), None)
        if ci is None or ce is None:
            continue
        for r in rows:
            if len(r) > max(ci, ce) and re.fullmatch(r"\d{4}", r[ci] or ""):
                v = num(r[ce])
                if v is not None:
                    out[r[ci]] = v
    return out


# 公司財報分析（docs/lab_company_plan.md 第 3.2 節）：彙總表全部科目 → 統一欄位。
# 各產業格式（一般業、金融、證券、保險、金控、異業）欄名不同 → 依序比對，先中先贏；欄名先去空白、半形括號改全形。
FS_MAP = {
    "is": [("rev", ("營業收入", "淨收益", "收益", "收入")),
           ("cogs", ("營業成本",)),
           ("gp", ("營業毛利（毛損）淨額", "營業毛利（毛損）")),
           ("opex", ("營業費用",)),
           ("op", ("營業利益（損失）", "營業利益")),
           ("nonop", ("營業外收入及支出", "營業外損益")),
           ("pti", ("稅前淨利（淨損）", "繼續營業單位稅前淨利（淨損）", "繼續營業單位稅前損益", "繼續營業單位稅前純益（純損）")),
           ("tax", ("所得稅費用（利益）", "所得稅（費用）利益")),
           ("ni", ("本期淨利（淨損）", "本期稅後淨利（淨損）")),
           ("nip", ("淨利（淨損）歸屬於母公司業主", "淨利（損）歸屬於母公司業主")),
           ("eps", ("基本每股盈餘（元）", "基本每股盈餘"))],
    "bs": [("ca", ("流動資產",)),
           ("ta", ("資產總計", "資產總額")),
           ("cl", ("流動負債",)),
           ("tl", ("負債總計", "負債總額")),
           ("cap", ("股本",)),
           ("eqp", ("歸屬於母公司業主之權益合計", "歸屬於母公司業主權益合計", "歸屬於母公司業主之權益")),
           ("eq", ("權益總計", "權益總額")),
           ("bvps", ("每股參考淨值",))],
    # 現金流量彙總（t163sb20，2026-10-16 探針：六種產業格式欄名一致；當年累計）
    "cf": [("ocf", ("營業活動之淨現金流入（流出）",)),
           ("icf", ("投資活動之淨現金流入（流出）",)),
           ("ffc", ("籌資活動之淨現金流入（流出）",)),
           ("cash", ("期末現金及約當現金餘額",))],
}
# 銀行格式沒有收入合計欄：營收＝利息淨收益＋利息以外淨損益（2026-10-16 探針：表頭只有這兩欄）
FS_SUM = {"is": {"rev": ("利息淨收益", ("利息以外淨損益", "利息以外淨收益"))}}
FS_EP = {"is": "t163sb04", "bs": "t163sb05", "cf": "t163sb20"}


def _norm_head(s: str) -> str:
    return re.sub(r"\s+", "", s).replace("(", "（").replace(")", "）")


def parse_mops_fs(html: str, kind: str) -> dict[str, dict[str, float]]:
    """MOPS 綜合損益（is）／資產負債（bs）／現金流量（cf）彙總表 → {代號: {統一欄位: 數值}}。金額單位仟元；
    損益與現金流量是當年累計。"""
    out: dict[str, dict] = {}
    for tb in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S | re.I):
        rows = [[_TAG.sub("", c).replace("&nbsp;", "").strip() for c in _TD.findall(tr)] for tr in _TR.findall(tb)]
        head = next((r for r in rows if any("公司代號" in c for c in r)), None)
        if not head:
            continue
        hs = [_norm_head(h) for h in head]
        ci = next(i for i, c in enumerate(hs) if "公司代號" in c)
        col = {}
        for key, names in FS_MAP[kind]:
            for nm in names:
                if nm in hs:
                    col[key] = hs.index(nm)
                    break
        sums = []
        for key, (a, bs) in (FS_SUM.get(kind) or {}).items():
            if key in col or a not in hs:
                continue
            b = next((x for x in bs if x in hs), None)
            if b:
                sums.append((key, hs.index(a), hs.index(b)))
        if not col and not sums:
            continue
        for r in rows:
            if len(r) > ci and re.fullmatch(r"\d{4}", r[ci] or ""):
                d = {k: num(r[i]) for k, i in col.items() if i < len(r)}
                for key, i, j in sums:
                    x, y = (num(r[i]) if i < len(r) else None), (num(r[j]) if j < len(r) else None)
                    if x is not None and y is not None:
                        d[key] = x + y
                d = {k: v for k, v in d.items() if v is not None}
                if d:
                    out[r[ci]] = d
    return out


def mops_fs(kind: str, mkt: str, y: int, q: int, timeout: int = 60) -> dict[str, dict] | None:
    """一季、一市場的綜合損益（is）或資產負債（bs）彙總；抓不到回 None。"""
    for host in MOPS_HOSTS:
        try:
            b = post_bytes(f"https://{host}/mops/web/ajax_{FS_EP[kind]}",
                           {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "isQuery": "Y",
                            "TYPEK": mkt, "year": y - 1911, "season": f"{q:02d}"}, timeout=timeout, retries=1)
        except Exception as e:                            # noqa: BLE001
            log(f"MOPS {kind} {y}Q{q} {mkt} {host} ✗ {str(e)[:120]}")
            continue
        d = parse_mops_fs(_decode(b), kind)
        if d:
            return d
        log(f"MOPS {kind} {y}Q{q} {mkt} {host} 解析 0 檔（{len(b)}B）")
    return None


def mops_is(mkt: str, y: int, q: int) -> dict[str, float] | None:
    """一季、一個市場（sii 上市／otc 上櫃）的基本每股盈餘累計值；抓不到回 None。"""
    for host in MOPS_HOSTS:
        try:
            b = post_bytes(f"https://{host}/mops/web/ajax_t163sb04",
                           {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "isQuery": "Y",
                            "TYPEK": mkt, "year": y - 1911, "season": f"{q:02d}"})
        except Exception as e:                            # noqa: BLE001
            log(f"MOPS 綜合損益 {y}Q{q} {mkt} {host} ✗ {str(e)[:120]}")
            continue
        h = _decode(b)
        d = parse_mops_is(h)
        if d:
            return d
        log(f"MOPS 綜合損益 {y}Q{q} {mkt} {host} 解析 0 檔（{len(b)}B）開頭 {h[:160]!r}")
    return None


FINMIND_LIMIT = "finmind_limit"


def finmind(dataset: str, code: str, start: str = "2021-01-01"):
    """FinMind 單檔資料集 → list[dict]；被限流回 FINMIND_LIMIT（呼叫端停下來，下一輪續補）。"""
    from .. import clock
    url = (f"https://api.finmindtrade.com/api/v4/data?dataset={dataset}&data_id={code}"
           f"&start_date={start}&end_date={clock.today_tw().isoformat()}")
    try:
        doc = json.loads(get_bytes(url, retries=1, timeout=30, use_cache=False).decode("utf-8"))
    except Exception as e:                                # noqa: BLE001
        msg = str(e)
        log(f"FinMind {dataset} {code} ✗ {msg[:100]}")
        return FINMIND_LIMIT if ("402" in msg or "429" in msg) else None
    if not isinstance(doc, dict):
        return None
    st, msg = doc.get("status"), str(doc.get("msg") or "")
    if st not in (200, "200"):
        log(f"FinMind {dataset} {code} status={st} msg={msg[:100]}")
        return FINMIND_LIMIT if (str(st) in ("402", "429") or "limit" in msg.lower() or "upper" in msg.lower()) else None
    return doc.get("data") or []


def fm_eps(rows) -> dict[str, float]:
    """FinMind 綜合損益 → {季底日期: 基本每股盈餘}（單季）。"""
    out = {}
    for r in rows or []:
        if r.get("type") == "EPS" or "每股盈餘" in str(r.get("origin_name") or ""):
            v = r.get("value")
            if r.get("date") and v is not None:
                out[str(r["date"])[:10]] = float(v)
    return out


_FM_DIV_KEYS: set = set()


def fm_div(rows) -> list[list]:
    """FinMind 股利政策 → [[現金除息日, 現金股利, 配股除權日, 配股(元), 所屬年度, 公告日]]；鍵名第一次印出供核對。"""
    out = []
    for r in rows or []:
        if not _FM_DIV_KEYS:
            _FM_DIV_KEYS.update(r)
            log(f"FinMind 股利政策鍵名：{sorted(r)[:30]}")
        cash = sum(float(r.get(k) or 0) for k in ("CashEarningsDistribution", "CashStatutorySurplus"))
        stock = sum(float(r.get(k) or 0) for k in ("StockEarningsDistribution", "StockStatutorySurplus"))
        ex_c, ex_s = r.get("CashExDividendTradingDate") or None, r.get("StockExDividendTradingDate") or None
        if cash or stock:
            out.append([ex_c, round(cash, 6), ex_s, round(stock, 6), str(r.get("year") or ""),
                        str(r.get("AnnouncementDate") or r.get("date") or "")[:10] or None])
    return out

