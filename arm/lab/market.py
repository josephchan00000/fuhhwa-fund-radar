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

UA_SLEEP_TWSE = 2.4      # 證交所 www 端有頻率限制（約每 5 秒 3 次），保守間隔
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


def _get(url: str, *, sleep: float, timeout: int = 25):
    """GET → (doc, status)。status：ok／nodata（官方明示查無）／err。"""
    try:
        b = get_bytes(url, retries=2, timeout=timeout, use_cache=False)
    except Exception as e:                                # noqa: BLE001
        time.sleep(sleep)
        return None, f"err:{str(e)[:120]}"
    time.sleep(sleep)
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
        else:                       # 舊站 aaData 欄序（2024 前格式）
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
