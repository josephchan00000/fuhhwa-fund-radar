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


def _code(row) -> str | None:
    c = _TAG.sub("", str(row[0] if row else "")).strip()
    return c if CODE_RE.match(c) else None


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


def _tpex(part: str, d: str):
    key = {"q_tp": "quotes", "i_tp": "insti", "m_tp": "margin"}[part]
    fn = {"q_tp": parse_tp_quotes, "i_tp": parse_tp_insti, "m_tp": parse_tp_margin}[part]
    last = "err:無候選"
    for tmpl in TPEX[key]:
        doc, st = _get(tmpl.format(roc=roc(d), ad=ad(d)), sleep=UA_SLEEP_TPEX)
        if st != "ok":
            last = st
            continue
        # 櫃買回應自帶資料日——與請求日不同（例：假日回最近交易日）就不收
        rd = str((doc or {}).get("date") or "") if isinstance(doc, dict) else ""
        rd = re.sub(r"\D", "", rd)
        if len(rd) == 8 and rd != ymd(d):
            last = f"nodata:回應日 {rd}≠{ymd(d)}"
            continue
        if len(rd) == 7 and f"{int(rd[:3]) + 1911}{rd[3:]}" != ymd(d):
            last = f"nodata:回應日 {rd}≠{ymd(d)}"
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

