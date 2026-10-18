"""大跌風險研究（docs/lab_crash_plan.md 第 3、10 節）的資料抓取。只在 CI 跑（本容器的 proxy 擋這些站）。

  twcap     央行統計資料庫 EG27M01（上市股票，月）  {YYYY-MM: [公司家數, 總面額, 總市值, 總成交值, 日平均成交值, 加權平均股價指數]}  1987-05 起
  twmgn     央行統計資料庫 EG25M01（融資融券，月）  {YYYY-MM: [融資, 融券]}                                                     1987-05 起
  us_vol_*  Yahoo 指數日成交量                      {日期: 成交量}（0 或沒有的日子不收）

央行兩張表的代碼、欄名是 2026-10-17 景氣頁第四版探針列舉 EG01～40 時看到的（CI 日誌；當時只印前 6 個欄名）。
單位以原始值存（央行表的單位另由探針核對，計算時再換算），抓不到保留既有的檔。
probe() 只印不寫：央行表完整欄名、單位核對、報酬指數、台積電市值、下市公司產業別的候選來源（docs/lab_crash_plan.md Q3、Q9）。
"""
from __future__ import annotations

import json
import re
import statistics
import time
import urllib.parse
from datetime import datetime, timezone

from . import heatdata as HD
from .heatfetch import _get, _merge, _num
from .market import log

CBC_STOCK = ("EG27M01", tuple((n, None) for n in ("上市股票-公司家數", "上市股票-總面額", "上市股票-總市值", "上市股票-總成交值",
                                                  "上市股票-日平均成交值", "加權平均股價指數")))
CBC_MARGIN = ("EG25M01", (("融資", "餘額-金額"), ("融資", "餘額-股數"), ("融券", "餘額-股數"), ("融券", "餘額-金額")))
US_VOL = {"spx": ("^GSPC", "1950-01-01"), "ixic": ("^IXIC", "1971-01-01"), "ndx": ("^NDX", "1985-01-01")}


def _col_index(names: list[str], want: str) -> int | None:
    i = next((k for k, n in enumerate(names) if n == want), None)
    if i is None:
        i = next((k for k, n in enumerate(names) if n.endswith(want)), None)
    return i


def parse_cbc_cube(names1: list[str], names2: list[str], rows: list, want: tuple) -> dict:
    """央行 DataAPI 表 → {YYYY-MM: [want 各格的原始值]}。
    每列＝期別＋（Table1 項目 × Table2 名稱 × 最內層 [原始值, 年增率…]）展平；每個 Table1 項目佔 ncol ÷ len(Table1) 欄，
    再平均分給 Table2 的每個名稱（EG27M01 的 Table2 就是 [原始值, 年增率]，EG25M01 的 Table2 是新增／償還／餘額六欄、
    每欄再各有原始值與年增率）。want＝[(Table1 名稱, Table2 名稱或 None)]，None＝該項目的第一欄；取最內層第一個（原始值）。
    名稱找不到的那一格是 None；整列都沒有值的月份不收。"""
    ncol = max((len(r) for r in rows), default=1) - 1
    block = ncol // max(1, len(names1))
    stride = max(1, block // max(1, len(names2)))
    cols = []
    for a, b in want:
        i = _col_index(names1, a)
        m = 0 if b is None else _col_index(names2, b)
        cols.append(None if i is None or m is None else 1 + i * block + m * stride)
    out = {}
    for r in rows:
        mm = re.match(r"^(\d{4})M(\d{2})$", str(r[0] if r else ""))
        if not mm:
            continue
        vals = [_num(r[c]) if c is not None and c < len(r) else None for c in cols]
        if any(v is not None for v in vals):
            out[f"{mm.group(1)}-{mm.group(2)}"] = vals
    return out


def _cbc_struct(code: str) -> tuple[list[str], list[str], list, dict]:
    from .heatfetch import CBC_API
    doc = json.loads(_get(CBC_API.format(f=code), timeout=90).decode("utf-8"))
    data = doc.get("data") or {}
    st = data.get("structure") or {}
    nm = lambda t: [str((x or {}).get("data") or "").replace(" ", "") for x in (st.get(t) or [])]  # noqa: E731
    return nm("Table1"), nm("Table2"), data.get("dataSets") or [], st


def _cbc(name: str, spec: tuple) -> int:
    code, want = spec
    n1, n2, rows, _ = _cbc_struct(code)
    miss = [w for w in want if _col_index(n1, w[0]) is None or (w[1] is not None and _col_index(n2, w[1]) is None)]
    if miss:
        log(f"[crash] 央行 {code} 找不到欄位 {miss}（Table1：{'、'.join(n1)}；Table2：{'、'.join(n2)}）")
    return _merge(name, "cbc", parse_cbc_cube(n1, n2, rows, want))


def cbc_stock() -> int:
    return _cbc("twcap", CBC_STOCK)


def cbc_margin() -> int:
    """融資餘額金額（百萬元）、融資餘額股數（百萬股）、融券餘額股數、融券餘額金額。第一版誤取「新增-股數」，這一版整檔重寫。"""
    from .heatfetch import _replace
    code, want = CBC_MARGIN
    n1, n2, rows, _ = _cbc_struct(code)
    return _replace("twmgn", "cbc", parse_cbc_cube(n1, n2, rows, want))


def parse_yahoo_volume(doc: dict, now: float) -> dict:
    """chart API → {日期: 成交量}：和 heatfetch_us.parse_yahoo 同一套日期規則（還沒收盤的當天、週末不收），0 不收。"""
    from .heatfetch_us import CLOSE_MARGIN_S
    res = (((doc or {}).get("chart") or {}).get("result") or [None])[0]
    if not res:
        return {}
    meta = res.get("meta") or {}
    off = int(meta.get("gmtoffset") or -18000)
    reg = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    open_day = None
    if reg.get("start") and reg.get("end") and reg["start"] <= now < reg["end"] + CLOSE_MARGIN_S:
        open_day = datetime.fromtimestamp(int(reg["start"]) + off, timezone.utc).date()
    today = datetime.fromtimestamp(now + off, timezone.utc).date()
    ts = res.get("timestamp") or []
    vols = ((((res.get("indicators") or {}).get("quote") or [{}])[0]) or {}).get("volume") or []
    out = {}
    for t, v in zip(ts, vols):
        if not v or v <= 0:
            continue
        d = datetime.fromtimestamp(int(t) + off, timezone.utc).date()
        if d.weekday() >= 5 or d > today or d == open_day:
            continue
        out[d.isoformat()] = float(v)
    return out


def yahoo_volume(name: str, sym: str, start: str) -> int:
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1={p1}&period2={p2}&interval=1d")
    doc = json.loads(_get(url, timeout=60).decode("utf-8"))
    return _merge(name, "yahoo", parse_yahoo_volume(doc, time.time()))


def us_volume_all() -> int:
    n = 0
    for k, (sym, start) in US_VOL.items():
        try:
            m = yahoo_volume(f"us_vol_{k}", sym, start)
            log(f"[crash] 成交量 {k}（{sym}）：{m} 筆新增或改動")
            n += m
        except Exception as e:                                # noqa: BLE001 —— 每個指數各自失敗
            log(f"[crash] 成交量 {k}（{sym}）✗ {type(e).__name__}: {str(e)[:160]}")
        time.sleep(1)
    return n


# ── 探針（只印不寫；合併前刪掉呼叫處） ─────────────────────────────────────

def _say(*a) -> None:
    print("[crash探針]", *a, flush=True)


def _sec(name: str, fn) -> None:
    _say(f"===== {name} =====")
    t0 = time.time()
    try:
        fn()
    except Exception as e:                                    # noqa: BLE001
        _say(f"✗ {type(e).__name__}: {str(e)[:300]}")
    _say(f"（{time.time() - t0:.0f}s）")


def _margin_check() -> None:
    """央行融資餘額 vs FinMind（證交所上市）月底：比值穩定在 1＝只有上市；比值隨時間變大＝含上櫃。"""
    n1, n2, rows, st = _cbc_struct(CBC_MARGIN[0])
    _say("EG25M01 structure 鍵", list(st), "｜Table1", n1, "｜Table2", n2,
         "｜其他表", {k: [str((x or {}).get('data'))[:12] for x in (v or [])][:8] for k, v in st.items()
                       if k not in ("Table1", "Table2") and isinstance(v, list)})
    cb, fm = HD.load("twmgn"), HD.load("margin")
    for ym in [f"{y}-12" for y in range(1990, 2026)] + ["2026-07", "2026-08"]:
        c = cb.get(ym) or [None] * 4
        last = max((d for d in fm if d[:7] == ym), default=None)
        f = fm.get(last) if last else None
        fa = f[0] / 1e6 if f and f[0] else None                # 元 → 百萬元
        fs = f[1] / 1e3 if f and f[1] else None                # 張 → 百萬股
        _say(f"{ym} 央行 融資金額 {c[0]} 股數 {c[1]}｜FinMind {fa and round(fa)} {fs and round(fs)}"
             + (f"｜比 金額 {c[0] / fa:.3f} 股數 {c[1] / fs:.3f}" if c[0] and fa and c[1] and fs else ""))


def _tpex_margin() -> None:
    from .market import TPEX
    for d in ("2026-08-31", "2024-12-31", "2014-12-31", "2005-12-30"):
        y, m, dd = d.split("-")
        roc, ad = f"{int(y) - 1911}/{m}/{dd}", f"{y}/{m}/{dd}"
        for tmpl in TPEX["margin"]:
            u = tmpl.format(roc=roc, ad=ad)
            try:
                doc = json.loads(_get(u, timeout=40).decode("utf-8"))
            except Exception as e:                            # noqa: BLE001
                _say("櫃買融資", d, u[-50:], "✗", str(e)[:100])
                continue
            tabs = doc.get("tables") or []
            _say("櫃買融資", d, u[-50:], "｜鍵", list(doc)[:12], "｜日期", doc.get("date"), "｜表", len(tabs))
            for t in tabs[:3]:
                data = t.get("data") or []
                _say("   表", str(t.get("title"))[:40], "｜欄", t.get("fields"), "｜列", len(data))
                for r in data[-3:]:
                    _say("     末列", r)
                for k in ("summary", "notes", "total"):
                    if t.get(k):
                        _say(f"     {k}", str(t.get(k))[:600])
            if doc.get("aaData") or doc.get("tfootData_one"):
                _say("   舊版 tfoot", doc.get("tfootData_one"), doc.get("tfootData_two"), "｜列", len(doc.get("aaData") or []))
            break
        time.sleep(1.6)


def probe() -> int:
    for name, fn in (("融資：央行 vs 證交所上市", _margin_check), ("櫃買融資餘額合計", _tpex_margin)):
        _sec(name, fn)
    return 0
