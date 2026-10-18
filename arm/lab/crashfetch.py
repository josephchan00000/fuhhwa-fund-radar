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
from .heatfetch import _cbc_table, _get, _merge, _num
from .market import log

CBC_STOCK = ("EG27M01", ("上市股票-公司家數", "上市股票-總面額", "上市股票-總市值", "上市股票-總成交值",
                         "上市股票-日平均成交值", "加權平均股價指數"))
CBC_MARGIN = ("EG25M01", ("融資", "融券"))
US_VOL = {"spx": ("^GSPC", "1950-01-01"), "ixic": ("^IXIC", "1971-01-01"), "ndx": ("^NDX", "1985-01-01"),
          "sox": ("^SOX", "1994-01-01")}


def _col_index(names: list[str], want: str) -> int | None:
    i = next((k for k, n in enumerate(names) if n == want), None)
    if i is None:
        i = next((k for k, n in enumerate(names) if n.endswith(want)), None)
    return i


def parse_cbc_cols(names: list[str], width: int, rows: list, want: tuple) -> dict:
    """央行 DataAPI 表 → {YYYY-MM: [want 各欄的原始值]}；每項 width 欄（原始值、年增率…），取第 0 欄。
    欄名找不到的那一欄是 None；整列都沒有值的月份不收。"""
    idx = [_col_index(names, w) for w in want]
    out = {}
    for r in rows:
        mm = re.match(r"^(\d{4})M(\d{2})$", str(r[0] if r else ""))
        if not mm:
            continue
        vals = []
        for i in idx:
            c = None if i is None else 1 + i * width
            vals.append(_num(r[c]) if c is not None and c < len(r) else None)
        if any(v is not None for v in vals):
            out[f"{mm.group(1)}-{mm.group(2)}"] = vals
    return out


def _cbc(name: str, spec: tuple) -> int:
    code, want = spec
    names, width, rows = _cbc_table(code)
    miss = [w for w in want if _col_index(names, w) is None]
    if miss:
        log(f"[crash] 央行 {code} 找不到欄位 {miss}（全部欄名：{'、'.join(names)}）")
    return _merge(name, "cbc", parse_cbc_cols(names, width, rows, want))


def cbc_stock() -> int:
    return _cbc("twcap", CBC_STOCK)


def cbc_margin() -> int:
    return _cbc("twmgn", CBC_MARGIN)


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


def _plain(h: str) -> str:
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def _cbc_full() -> None:
    import json as _j
    from .heatfetch import CBC_API
    for code in ("EG27M01", "EG25M01", "EG27D01", "EG25D01", "EG27M02", "EG25M02", "EG27Q01", "EG27Y01"):
        try:
            doc = _j.loads(_get(CBC_API.format(f=code), timeout=60).decode("utf-8"))
        except Exception as e:                                # noqa: BLE001
            _say(code, "✗", str(e)[:80])
            continue
        data = doc.get("data") or {}
        st = data.get("structure") or {}
        names = [str((x or {}).get("data") or "") for x in (st.get("Table1") or [])]
        t2 = [str((x or {}).get("data") or "") for x in (st.get("Table2") or [])]
        ds = data.get("dataSets") or []
        meta = doc.get("meta") or {}
        _say(code, str(meta.get("title"))[:60], "｜單位", str(meta.get("unit") or meta.get("units") or "")[:60],
             "｜meta 鍵", list(meta)[:12])
        _say("   欄名", "、".join(names))
        _say("   Table2", "、".join(t2), "｜列數", len(ds))
        for r in (ds[:2] + ds[-2:]):
            _say("   ", r[:16])
        time.sleep(0.5)


def _units() -> None:
    from . import store
    cap, mgn = HD.load("twcap"), HD.load("twmgn")
    fm = HD.load("margin")
    v3 = {}
    for _, doc in store.load("v3me_tw"):
        d, s = (doc or {}).get("d"), (doc or {}).get("s") or {}
        if d:
            v3[d[:7]] = sum(float(v[0]) * float(v[1]) for v in s.values() if v and len(v) >= 2 and v[0] and v[1])
    for ym in ("2013-06", "2016-12", "2020-12", "2024-12", "2026-06", "2026-08"):
        c = (cap.get(ym) or [None] * 6)[2]
        _say(f"市值 {ym}：央行 {c}｜自算上市月底 {v3.get(ym):.4g}" if v3.get(ym) else f"市值 {ym}：央行 {c}｜自算 —",
             f"｜比 {v3[ym] / c:.4g}" if c and v3.get(ym) else "")
    for ym in ("2001-12", "2008-12", "2015-12", "2020-12", "2024-12", "2026-08"):
        last = max((d for d in fm if d[:7] == ym), default=None)
        m = (mgn.get(ym) or [None, None])[0]
        f = (fm.get(last) or [None])[0] if last else None
        _say(f"融資 {ym}：央行 {m}｜FinMind 月底 {last} {f}", f"｜比 {f / m:.4g}" if f and m else "")
    ks = sorted(cap)
    _say("央行市值月份", len(ks), ks[:1], ks[-1:], "｜融資月份", len(mgn), sorted(mgn)[:1], sorted(mgn)[-1:])
    for ym in ("1987-05", "1990-02", "1995-12", "2000-12"):
        _say(f"  {ym} 市值列 {cap.get(ym)}｜融資列 {mgn.get(ym)}")


def _fm(ds: str, did: str, a: str, z: str | None = None) -> list:
    from .heatfetch import _finmind
    return _finmind(ds, did, a, z)


def _finmind_probe() -> None:
    for ds, did, a in (("TaiwanStockTotalReturnIndex", "TAIEX", "1990-01-01"),
                       ("TaiwanStockTotalReturnIndex", "TPEx", "1990-01-01"),
                       ("TaiwanStockMarketValue", "2330", "1990-01-01")):
        try:
            rows = _fm(ds, did, a)
            _say(ds, did, "筆數", len(rows), "｜首", rows[:1], "｜末", rows[-1:])
        except Exception as e:                                # noqa: BLE001
            _say(ds, did, "✗", str(e)[:160])
        time.sleep(1)
    try:
        rows = _fm("TaiwanStockInfo", "", "1990-01-01")
        want = {"2311", "2325", "2448", "2888", "3474", "3658", "5820", "8406", "2823", "1704"}
        hit = [r for r in rows if str(r.get("stock_id")) in want]
        _say("TaiwanStockInfo 筆數", len(rows), "欄位", list(rows[0]) if rows else None, "｜樣本命中", len(hit))
        for r in hit[:12]:
            _say("   ", r)
    except Exception as e:                                    # noqa: BLE001
        _say("TaiwanStockInfo ✗", str(e)[:160])


def _delisted_probe() -> None:
    from .market import post_bytes
    for code in ("2325", "3474", "2888", "3658", "5820"):
        u = f"https://isin.twse.com.tw/isin/single_main.jsp?owncode={code}&stockname="
        try:
            b = _get(u, timeout=40)
            t = _plain(b.decode("big5", "replace") if b[:200].count(b"\x00") == 0 else b.decode("utf-8", "replace"))
            i = t.find(code)
            _say("ISIN", code, len(b), "B｜", t[max(0, i - 60):i + 260] if i >= 0 else t[:300])
        except Exception as e:                                # noqa: BLE001
            _say("ISIN", code, "✗", str(e)[:120])
        time.sleep(1.5)
    for typ, code in (("24", "2325"), ("17", "2888"), ("24", "3474")):
        u = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20140102&type={typ}&response=json"
        try:
            doc = json.loads(_get(u, timeout=40).decode("utf-8"))
            tabs = doc.get("tables") or []
            titles = [str(t.get("title"))[:40] for t in tabs]
            hit = [r[:3] for t in tabs for r in (t.get("data") or []) if r and str(r[0]).strip() == code]
            n = sum(len(t.get("data") or []) for t in tabs)
            _say(f"MI_INDEX 2014-01-02 type={typ}：stat {doc.get('stat')}｜表 {titles}｜列 {n}｜{code} {hit}")
        except Exception as e:                                # noqa: BLE001
            _say(f"MI_INDEX type={typ} ✗", str(e)[:120])
        time.sleep(3.5)
    for u in ("https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"
              "?l=zh-tw&o=json&d=103/01/02&se=24",
              "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=2014%2F01%2F02&type=24&response=json"):
        try:
            b = _get(u, timeout=40)
            t = b.decode("utf-8", "replace")
            i = t.find("3658")
            _say("櫃買 2014-01-02 半導體", u[-60:], len(b), "B｜3658", t[max(0, i - 40):i + 120] if i >= 0 else "沒有",
                 "｜開頭", t[:160])
        except Exception as e:                                # noqa: BLE001
            _say("櫃買", u[-60:], "✗", str(e)[:120])
        time.sleep(1.6)
    for code in ("2325", "3658"):
        try:
            b = post_bytes("https://mopsov.twse.com.tw/mops/web/ajax_t05st03",
                           {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "queryName": "co_id",
                            "inpuType": "co_id", "TYPEK": "all", "co_id": code}, retries=1, timeout=40)
            t = _plain(b.decode("utf-8", "replace"))
            i = t.find("產業")
            _say("公開資訊觀測站 t05st03", code, len(b), "B｜", t[max(0, i - 80):i + 200] if i >= 0 else t[:300])
        except Exception as e:                                # noqa: BLE001
            _say("公開資訊觀測站 t05st03", code, "✗", str(e)[:120])
        time.sleep(3)


def _volume_check() -> None:
    for k in US_VOL:
        d = HD.load(f"us_vol_{k}")
        ks = sorted(d)
        if not ks:
            _say("成交量", k, "沒有資料")
            continue
        by: dict[str, list] = {}
        for x in ks:
            by.setdefault(x[:4], []).append(d[x])
        med = {y: statistics.median(v) for y, v in by.items()}
        ys = sorted(med)
        jumps = [(a, b, round(med[b] / med[a], 2)) for a, b in zip(ys, ys[1:]) if med[a] and med[b] / med[a] > 2.5]
        _say("成交量", k, len(ks), "天", ks[0], "～", ks[-1], "｜每 10 年中位數",
             {y: f"{med[y]:.3g}" for y in ys if int(y) % 10 == 0}, "｜年中位數跳 2.5 倍以上", jumps)


def probe() -> int:
    for name, fn in (("央行兩張表的完整欄名", _cbc_full), ("單位核對（自算市值、FinMind 融資）", _units),
                     ("FinMind 報酬指數、台積電市值、股票清單", _finmind_probe),
                     ("下市公司產業別候選來源", _delisted_probe), ("美股成交量", _volume_check)):
        _sec(name, fn)
    return 0
