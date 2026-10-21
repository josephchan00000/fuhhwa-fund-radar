"""台股（上市）大盤融資維持率（大神策略第三段，docs/lab_expert_plan.md 第 10 節）。

維持率＝上市證券的融資市值 ÷ 上市融資金額＝Σ(融資餘額張數 × 1000 × 當天收盤) ÷ 融資金額。
TEJ、券商說的「大盤融資維持率」是同一個算法（整體融資市值 ÷ 整體融資借款；剛買進時＝1 ÷ 融資成數 6 成＝166.7%）。
各家口徑不同（含不含上櫃、ETF，分母從哪裡來）：這裡和 TEJ 同一個算法（2020-03-19 135.80% 對 TEJ 135.73%、2025-04-09 都是 130.38%），
和證交所公布的整戶維持率也接近（2026-07-27 證交所約 175%、這裡 173.5%）；媒體常引用的 CMoney 等推估低 10～30 個百分點
（2024-08-05 CMoney 139.42%、這裡 148.04%）。所以只和自己的歷史比。
這裡含 ETF（分母的融資金額也含 ETF；2026 年 ETF 占融資張數約三成、市值約 5%）。

分母：data/lab/heat/margin（FinMind 上市融資合計，2001 起；[融資金額（元）, 融資張數, 融券張數]）。
分子：
  · 歷史（2001 ～ END）：FinMind 逐檔融資餘額（TaiwanStockMarginPurchaseShortSale）＋原始收盤（TaiwanStockPrice），
    只算在證交所掛牌的那段（上櫃轉上市的，上櫃那段不算）。每做完一檔，就把它每天的融資市值、張數加進每日合計（agg），
    代號記進 done——可以分很多輪做（未登入每小時 300 次，這裡每小時最多 PER_HOUR 個請求）。
  · END 之後：官方分片 m_tw（融資餘額張數）× q_tw（收盤）。
涵蓋率＝合計張數 ÷ 官方上市融資張數。維持率＝每張平均融資市值 × 官方張數 ÷ 融資金額（少數沒抓到的證券以平均市值補）；
涵蓋率不在 COV_OK 範圍的日子不算。
"""
from __future__ import annotations

import json
import re
import time
from bisect import bisect_right
from datetime import date

from . import heatdata as HD
from . import store
from .market import log

KIND = "mratio"                      # data/lab/mratio/{agg,done}.json.gz
SERIES = "mratio"                    # data/lab/heat/mratio.json.gz：{日期: [維持率%, 涵蓋率]}
START = "2001-01-01"                 # heat margin（分母）從 2001-01-03 起
PER_HOUR = 280                       # FinMind 未登入每小時 300 次，留一點餘裕
COV_OK = (0.95, 1.05)            # 2004-02 以前已下市公司在 FinMind 沒有收盤，涵蓋率不夠的日子不算
FM = "https://api.finmindtrade.com/api/v4/data?dataset={ds}&data_id={code}&start_date={a}&end_date={z}"


class Quota(Exception):
    """FinMind 額度用完（HTTP 402／429 或回應寫 upper limit）：這一輪先停，下一輪續做。"""


# ── 計算 ─────────────────────────────────────────────────────────────

def is_etf(code: str) -> bool:
    return code.startswith("00")


def contrib(mg: dict[str, float], px: dict[str, float], *, start: str | None, end: str | None,
            last: str) -> tuple[dict[str, tuple[float, int]], int, int]:
    """一檔證券每天的融資市值（元）與融資張數。mg＝{日期: 融資餘額張數}，px＝{日期: 收盤（原始價）}。
    只算 start ≤ 日期 ≤ min(end, last)、張數 > 0 的日子；當天沒有收盤（停牌、沒有成交）用之前最近一個收盤（stale）；
    之前完全沒有收盤就不算（miss）。回傳 ({日期: (市值, 張數)}, miss 天數, stale 天數)。"""
    hi = min(end, last) if end else last
    pd = sorted(d for d, v in px.items() if v and v > 0)
    pv = [px[d] for d in pd]
    out: dict[str, tuple[float, int]] = {}
    miss = stale = 0
    for d in sorted(mg):
        n = mg[d]
        if not n or n <= 0 or d > hi or (start and d < start):
            continue
        j = bisect_right(pd, d) - 1
        if j < 0:
            miss += 1
            continue
        if pd[j] != d:
            stale += 1
        out[d] = (n * 1000.0 * pv[j], int(n))
    return out, miss, stale


def add(agg: dict, rows: dict[str, tuple[float, int]], etf: bool) -> None:
    """加進每日合計：agg[日期]＝[股票市值, 股票張數, 股票檔數, ETF 市值, ETF 張數, ETF 檔數]。"""
    o = 3 if etf else 0
    for d, (v, n) in rows.items():
        a = agg.setdefault(d, [0.0, 0, 0, 0.0, 0, 0])
        a[o] += v
        a[o + 1] += n
        a[o + 2] += 1


def official_day(doc: dict) -> tuple[float, int, int] | None:
    """官方分片一天：Σ 融資餘額張數 × 1000 × 收盤（m_tw × q_tw）。沒有收盤的證券不算進市值、也不算進張數。"""
    m, q = doc.get("m_tw") or {}, doc.get("q_tw") or {}
    if not m or not q:
        return None
    v, n, k = 0.0, 0, 0
    for c, row in m.items():
        b = row[0] if row else None
        if not b:
            continue
        px = (q.get(c) or [None] * 4)[3]
        if not px:
            continue
        v += b * 1000.0 * px
        n += int(b)
        k += 1
    return (v, n, k) if n else None


def ratio(v: float, n: int, money: float | None, total_n: float | None) -> tuple[float, float] | None:
    """→ (維持率 %, 涵蓋率)。維持率＝每張平均市值 × 官方張數 ÷ 融資金額。"""
    if not n or not money or not total_n:
        return None
    cov = n / total_n
    if not (COV_OK[0] <= cov <= COV_OK[1]):
        return None
    return v / n * total_n / money * 100.0, cov


def build_series(agg_doc: dict, margin: dict, shards: dict[str, dict]) -> dict[str, list]:
    """{日期: [維持率 %（兩位小數）, 涵蓋率（四位）, 來源 0＝FinMind 逐檔、1＝官方分片]}。END 之前用回補的合計，之後用官方分片。"""
    end = agg_doc.get("end") or ""
    agg = agg_doc.get("d") or {}
    out: dict[str, list] = {}
    for d, row in margin.items():
        if not row or len(row) < 2:
            continue
        money, total_n = row[0], row[1]
        r = None
        src = 0
        if d <= end and d in agg:
            a = agg[d]
            r = ratio(a[0] + a[3], a[1] + a[4], money, total_n)
        elif d > end and d in shards:
            od = official_day(shards[d])
            if od:
                r = ratio(od[0], od[1], money, total_n)
                src = 1
        if r:
            out[d] = [round(r[0], 2), round(r[1], 4), src]
    return out


# ── 讀寫 ─────────────────────────────────────────────────────────────

def load_agg() -> dict:
    return store.read(KIND, "agg") or {"end": None, "d": {}}


def load_done() -> dict:
    return store.read(KIND, "done") or {"codes": {}, "skip": {}, "fail": {}}


def save(agg_doc: dict, done: dict) -> None:
    agg_doc = {"end": agg_doc.get("end"),
               "d": {d: [round(a[0]), a[1], a[2], round(a[3]), a[4], a[5]] for d, a in sorted((agg_doc.get("d") or {}).items())}}
    store.write(KIND, "agg", agg_doc)
    store.write(KIND, "done", done)


def update_series() -> int:
    """重算維持率序列寫進 heat 資料夾（mratio）。回補的合計還沒有就不動。回傳改動的筆數。"""
    agg = load_agg()
    if not agg.get("d"):
        return 0
    margin = HD.load("margin")
    end = agg.get("end") or ""
    shards = {d: doc for d, doc in store.load("mkt", since=end) if d > end} if end else {}
    new = build_series(agg, margin, shards)
    old = HD.load(SERIES)
    n = sum(1 for k, v in new.items() if old.get(k) != v) + sum(1 for k in old if k not in new)
    if n:
        HD.save(SERIES, "finmind+mkt", new)
    return n


# ── 回補（FinMind 逐檔；只在 CI 跑，本容器擋 FinMind）────────────────────

class Pacer:
    """每小時最多 per_hour 個請求：兩個請求之間至少間隔 3600 ÷ per_hour 秒（請求本身花的時間也算在內）。"""

    def __init__(self, per_hour: int = PER_HOUR, clock=time.monotonic, sleep=time.sleep):
        self.gap = 3600.0 / per_hour
        self.clock, self.sleep = clock, sleep
        self.last: float | None = None
        self.n = 0

    def wait(self) -> None:
        if self.last is not None:
            dt = self.gap - (self.clock() - self.last)
            if dt > 0:
                self.sleep(dt)
        self.last = self.clock()
        self.n += 1


def fm_rows(ds: str, code: str, a: str, z: str, pacer: Pacer, get=None) -> list[dict]:
    """FinMind 一個請求；額度用完丟 Quota，其他錯誤丟 RuntimeError（這一檔下一輪再試）。"""
    if get is None:
        from ..http import get_bytes

        def get(url):
            return get_bytes(url, retries=1, timeout=120, use_cache=False)
    pacer.wait()
    try:
        b = get(FM.format(ds=ds, code=code, a=a, z=z))
    except Exception as e:                                    # noqa: BLE001
        s = str(e)
        if "402" in s or "429" in s:
            raise Quota(s[:120]) from e
        raise RuntimeError(f"{ds} {code}：{s[:160]}") from e
    doc = json.loads(b.decode("utf-8"))
    st, msg = doc.get("status"), str(doc.get("msg") or "")
    if str(st) in ("402", "429") or "upper limit" in msg.lower():
        raise Quota(f"status={st} {msg[:80]}")
    if str(st) != "200":
        raise RuntimeError(f"{ds} {code} status={st} {msg[:80]}")
    return doc.get("data") or []


def fm_list(ds: str, pacer: Pacer, get=None) -> list[dict]:
    """不帶代號的 FinMind 清單（TaiwanStockInfo、TaiwanStockDelisting）。"""
    if get is None:
        from ..http import get_bytes

        def get(url):
            return get_bytes(url, retries=2, timeout=120, use_cache=False)
    pacer.wait()
    doc = json.loads(get(f"https://api.finmindtrade.com/api/v4/data?dataset={ds}").decode("utf-8"))
    if str(doc.get("status")) != "200":
        raise RuntimeError(f"{ds} status={doc.get('status')} {str(doc.get('msg'))[:80]}")
    return doc.get("data") or []


_CODE = re.compile(r"^(?:\d{4}|\d{6}|00\d{2,4}[A-Z]?)$")         # 股票 4 碼、存託憑證 91xxxx、ETF 00 開頭（可帶 1 個英文字母）
_DATE = re.compile(r"(\d{2,4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})")


def _iso(s: str) -> str | None:
    m = _DATE.search(str(s))
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if y < 1911:
        y += 1911                                             # 民國年
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def twse_delisted(get=None) -> dict[str, str]:
    """證交所終止上市名單 → {代號: 終止上市日}。抓不到回 {}（改用 FinMind 下市櫃表的日期）。"""
    if get is None:
        from ..http import get_bytes

        def get(url):
            return get_bytes(url, retries=2, timeout=60, use_cache=False)
    try:
        doc = json.loads(get("https://www.twse.com.tw/rwd/zh/company/suspendListing?response=json").decode("utf-8"))
    except Exception as e:                                    # noqa: BLE001
        log(f"[mratio] 證交所終止上市名單 ✗ {str(e)[:120]}")
        return {}
    rows = list(doc.get("data") or [])
    for t in doc.get("tables") or []:
        rows += (t or {}).get("data") or []
    out: dict[str, str] = {}
    for r in rows:
        cells = [re.sub(r"<[^>]+>", "", str(x)).strip() for x in (r if isinstance(r, (list, tuple)) else [])]
        code = next((c for c in cells if _CODE.match(c)), None)
        day = next((_iso(c) for c in cells if _iso(c)), None)
        if code and day:
            out[code] = max(out.get(code, day), day)
    return out


_NOT_SEC = ("Index", "大盤", "所有證券", "指數", "ETN", "受益證券")   # 這幾類沒有融資（ETN、REITs）或不是證券


def universe(info: list[dict], dl: list[dict], twse_off: dict[str, str], *, listed: dict[str, str],
             m_tw: dict[str, list], today: str, live_days: int = 10) -> dict:
    """要回補的代號：曾經在證交所上市的股票、ETF、存託憑證（2026-10-21 探針看過 FinMind 總覽之後定的規則）。
    · 上市中＝最近一天官方分片 m_tw 有的代號，或 FinMind 總覽最近 live_days 天內還有、類別 twse。
      （總覽的日期不可靠：泰金寶-DR 9105 還在上市，總覽卻停在 2024-12-04；已下市的矽品卻是 2026-07-12。）
      起日＝證交所上市日（上櫃轉上市的，上櫃那段不算；ETF、存託憑證沒有上市日＝不限）。
    · 已終止上市＝總覽類別 twse 但不在上市中，加上證交所終止上市名單：迄日＝證交所終止上市日 → FinMind 下市櫃表的日期。
    排序：上市中依現在的融資張數由大到小，已終止上市排最後。"""
    cut = date.fromisoformat(today).toordinal() - live_days
    by: dict[str, dict] = {}
    for r in info:
        c = str(r.get("stock_id") or "").strip()
        if not _CODE.match(c) or str(r.get("industry_category") or "") in _NOT_SEC:
            continue
        d = str(r.get("date") or "")[:10]
        e = by.setdefault(c, {"last": "", "types": set(), "last_type": None})
        e["types"].add(str(r.get("type") or ""))
        if d >= e["last"]:
            e["last"], e["last_type"] = d, str(r.get("type") or "")
    dl_day: dict[str, str] = {}
    for r in dl:
        c = str(r.get("stock_id") or "").strip()
        d = str(r.get("date") or "")[:10]
        if c and d:
            dl_day[c] = max(dl_day.get(c, d), d)
    live = {c for c in m_tw if _CODE.match(c)}
    for c, e in by.items():
        try:
            if e["last_type"] == "twse" and date.fromisoformat(e["last"]).toordinal() >= cut:
                live.add(c)
        except ValueError:
            pass
    off = {c for c, e in by.items() if "twse" in e["types"] and c not in live}
    off |= {c for c in twse_off if _CODE.match(c) and c not in live}
    rows_live = [[c, None if is_etf(c) else listed.get(c), None] for c in live]
    bal = {c: ((m_tw.get(c) or [0])[0] or 0) for c in live}
    rows_live.sort(key=lambda u: (-bal.get(u[0], 0), u[0]))
    rows_off = sorted([c, None, twse_off.get(c) or dl_day.get(c)] for c in off)
    return {"codes": rows_live + rows_off, "n": len(rows_live) + len(rows_off), "n_live": len(rows_live),
            "n_off": len(rows_off), "today": today}


def margin_map(rows: list[dict]) -> dict[str, float]:
    return {str(r["date"])[:10]: r.get("MarginPurchaseTodayBalance") for r in rows
            if r.get("date") and r.get("MarginPurchaseTodayBalance") is not None}


def price_map(rows: list[dict]) -> dict[str, float]:
    return {str(r["date"])[:10]: r.get("close") for r in rows if r.get("date") and r.get("close")}


def backfill(universe: list[tuple[str, str | None, str | None]], *, end: str, budget_s: float,
             per_hour: int = PER_HOUR, get=None, today: str | None = None, save_every: int = 25,
             quota_wait: float = 900.0, sleep=time.sleep) -> dict:
    """universe＝[(代號, 證交所上市起日或 None, 終止上市日或 None)]。依序做還沒做過的代號，到 budget_s 或額度用完為止；
    每做完 save_every 檔存一次（agg 與 done 同時寫，中途斷掉也不會重複加）。額度用完就等 quota_wait 秒再試，
    剩下的時間不夠等就停。回傳這一輪的統計。"""
    t0 = time.time()
    agg_doc, done = load_agg(), load_done()
    if agg_doc.get("end") and agg_doc["end"] != end:
        raise ValueError(f"回補的截止日已經是 {agg_doc['end']}，這次給 {end}")
    agg_doc["end"] = end
    agg = agg_doc.setdefault("d", {})
    pacer = Pacer(per_hour)
    z = today or date.today().isoformat()
    st = {"done": 0, "empty": 0, "fail": 0, "quota": False, "req": 0}
    todo = [u for u in universe if u[0] not in done["codes"] and u[0] not in done["skip"]]
    k = 0
    stop = False
    for code, a, e in todo:
        if stop or time.time() - t0 > budget_s:
            break
        try:
            while True:
                try:
                    mg = margin_map(fm_rows("TaiwanStockMarginPurchaseShortSale", code, START, z, pacer, get))
                    px = (price_map(fm_rows("TaiwanStockPrice", code, START, z, pacer, get))
                          if any(v for v in mg.values()) else None)
                    break
                except Quota as q:
                    st["quota"] = True
                    if time.time() - t0 + quota_wait + 60 > budget_s:
                        log(f"[mratio] 額度用完（{q}），這一輪先停")
                        stop = True
                        break
                    log(f"[mratio] 額度用完（{q}），等 {quota_wait // 60:.0f} 分鐘再試")
                    sleep(quota_wait)
            if stop:
                break
            if px is None:
                done["skip"][code] = "沒有融資"
                st["empty"] += 1
                continue
        except Exception as ex:                               # noqa: BLE001
            done["fail"][code] = done["fail"].get(code, 0) + 1
            st["fail"] += 1
            log(f"[mratio] {code} ✗ {str(ex)[:160]}")
            if done["fail"][code] >= 3:
                done["skip"][code] = f"失敗 3 次：{str(ex)[:60]}"
            continue
        rows, miss, stale = contrib(mg, px, start=a, end=e, last=end)
        add(agg, rows, is_etf(code))
        ds = sorted(rows)
        done["codes"][code] = [ds[0] if ds else None, ds[-1] if ds else None, len(rows), miss, stale]
        done["fail"].pop(code, None)
        st["done"] += 1
        k += 1
        if k % save_every == 0:
            save(agg_doc, done)
    save(agg_doc, done)
    st["req"] = pacer.n
    st["left"] = sum(1 for u in universe if u[0] not in done["codes"] and u[0] not in done["skip"])
    st["s"] = round(time.time() - t0)
    return st
