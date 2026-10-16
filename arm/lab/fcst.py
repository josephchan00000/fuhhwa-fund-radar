"""法人預估（docs/lab_forward_plan.md；使用者 2026-10-16：只顯示當參考，不拿來篩股）。

兩個來源，都只在 CI 抓（本容器 proxy 擋 cnyes／yahoo）：

1. 鉅亨網「台股預估」分類（tw_forecast）＝FactSet 調查快訊：分析師的共識預估有變動才發一則。
   - EPS 快訊：家數、主要年度 EPS 中位數（前值→新值、最高、最低）、預估股價中位數，
     內文兩張表＝未來三年 EPS 與營收（千元）的最高／最低／平均／中位數；
   - 預估股價快訊：中位數（前值→新值、幅度）、最高、最低、評等（積極樂觀／保持中立／保守悲觀）。
   新聞清單 API 吃 startAt／endAt（unix 秒），一頁 30 則 → 每天補「上次讀到之後」的，回補時一週一窗往回抓。
   存 data/lab/fcst/factset.json：{代號: [事件…]}（依時間排序、以 newsId 去重）。
2. Yahoo Finance quoteSummary（financialData、earningsTrend、recommendationTrend；要先拿 cookie＋crumb）：
   分析師家數、預估股價（平均、中位、最高、最低）、今年與明年 EPS／營收預估、30／90 天前的 EPS 預估、
   近 30 天上修下修家數、評等分布。一天一次，存最新一份 data/lab/fcst/yahoo.json；
   每週一份封存到 data/lab/fcst_y/{日期}.json.gz（留作日後要驗證時的歷史）。
   有分析師的公司（cover）平日只抓這些，每週一（或 cover 空了）重掃全部上市櫃。

頁面用字一律寫「法人預估股價」：「目標價」是專案禁用字（使用者 2026-10-16 決定）。
"""
from __future__ import annotations

import html as _html
import http.cookiejar
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import store

TZ = timezone(timedelta(hours=8))
FS_FILE = "fcst/factset.json"
YH_FILE = "fcst/yahoo.json"
YH_ARCH = "fcst_y"                     # 每週封存（gz 分片）
FS_KEEP_DAYS = 3650                    # FactSet 事件全留（鉅亨「台股預估」大約 2023 年才開始，量不大）
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CNYES_LIST = "https://api.cnyes.com/media/api/v1/newslist/category/tw_forecast?startAt={a}&endAt={b}&limit=30&page={p}"
YH_MODS = "financialData,earningsTrend,recommendationTrend"


# ── 共用 ──────────────────────────────────────────────────────────────────────
def _ctx() -> ssl.SSLContext:
    import certifi
    return ssl.create_default_context(cafile=certifi.where())


def _num(s) -> float | None:
    if s is None:
        return None
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def _day(ts) -> str:
    return datetime.fromtimestamp(int(ts), TZ).date().isoformat()


# ── FactSet 快訊（鉅亨網）────────────────────────────────────────────────────
_RE_E = re.compile(r"共(\d+)位分析師，對(.+?)\(([0-9A-Z]{4,6})-TW\)做出(\d{4})年EPS預估：中位數由(-?[\d,.]+)元(上修|下修)至"
                   r"(-?[\d,.]+)元，其中最高估值(-?[\d,.]+)元，最低估值(-?[\d,.]+)元(?:，預估目標價為([\d,.]+)元)?")
_RE_T = re.compile(r"共(\d+)位分析師，對(.+?)\(([0-9A-Z]{4,6})-TW\)提出目標價估值：中位數由([\d,.]+)元(上修|下修)至([\d,.]+)元"
                   r"，調(?:升|降)幅度([\d,.]+)%。其中最高估值([\d,.]+)元，最低估值([\d,.]+)元")
_RE_R = re.compile(r"積極樂觀(\d+)位、保持中立(\d+)位、保守悲觀(\d+)位")
_ROWS = {"最高值": 0, "最低值": 1, "平均值": 2, "中位數": 3}


def _text(x: str) -> str:
    return re.sub(r"<[^>]+>", "", x).strip()


def _table_after(h: str, title: str) -> list[list]:
    """內文中標題 title 之後的第一張表 → [[年度, 最高, 最低, 平均, 中位數], …]（只取當前值，括號內前值不要）。"""
    i = h.find(title)
    if i < 0:
        return []
    m = re.search(r"<table>(.*?)</table>", h[i:], re.S)
    if not m:
        return []
    rows = [re.findall(r"<td>(.*?)</td>", r, re.S) for r in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S)]
    if not rows:
        return []
    years = []
    for c in rows[0][1:]:
        y = re.search(r"(\d{4})年", _text(c))
        years.append(int(y.group(1)) if y else None)
    out = [[y, None, None, None, None] for y in years]
    for r in rows[1:]:
        k = _ROWS.get(_text(r[0]) if r else "")
        if k is None:
            continue
        for j, c in enumerate(r[1:len(years) + 1]):
            out[j][k + 1] = _num(re.sub(r"\(.*?\)", "", _text(c)))
    return [x for x in out if x[0] is not None and any(v is not None for v in x[1:])]


def parse_article(item: dict) -> dict | None:
    """鉅亨「台股預估」一則 → 事件 dict；認不得的格式回 None。
    EPS：{"k":"e","d","id","n","y","o","v","hi","lo","tp","eps":[[年,高,低,均,中]…],"rev":[[年,高,低,均,中]…]}（營收單位：億元）
    預估股價：{"k":"t","d","id","n","o","v","pct","hi","lo","rt":[樂觀,中立,悲觀]}"""
    h = _html.unescape(str(item.get("content") or ""))
    d = _day(item.get("publishAt")) if item.get("publishAt") else None
    nid = item.get("newsId")
    m = _RE_E.search(h)
    if m:
        ev = {"k": "e", "c": m.group(3), "nm": m.group(2), "d": d, "id": nid, "n": int(m.group(1)),
              "y": int(m.group(4)), "o": _num(m.group(5)), "v": _num(m.group(7)), "hi": _num(m.group(8)),
              "lo": _num(m.group(9)), "tp": _num(m.group(10))}
        ev["eps"] = _table_after(h, "市場預估EPS")
        rev = _table_after(h, "市場預估營收")             # 千元 → 億元
        ev["rev"] = [[r[0]] + [None if v is None else round(v / 1e5, 1) for v in r[1:]] for r in rev]
        return ev
    m = _RE_T.search(h)
    if m:
        ev = {"k": "t", "c": m.group(3), "nm": m.group(2), "d": d, "id": nid, "n": int(m.group(1)),
              "o": _num(m.group(4)), "v": _num(m.group(6)), "pct": _num(m.group(7)),
              "hi": _num(m.group(8)), "lo": _num(m.group(9))}
        if m.group(5) == "下修" and ev["pct"] is not None:
            ev["pct"] = -ev["pct"]
        r = _RE_R.search(h)
        ev["rt"] = [int(r.group(1)), int(r.group(2)), int(r.group(3))] if r else None
        return ev
    return None


def _ev_row(e: dict) -> list:
    """事件 → 存檔用的緊湊陣列（欄位順序見 EV_COLS）。"""
    if e["k"] == "e":
        return [e["d"], "e", e["id"], e["n"], e["y"], e["o"], e["v"], e["hi"], e["lo"], e.get("tp"),
                e.get("eps") or [], e.get("rev") or []]
    return [e["d"], "t", e["id"], e["n"], e["o"], e["v"], e["pct"], e["hi"], e["lo"], e.get("rt")]


EV_COLS = {"e": ["d", "k", "id", "n", "y", "o", "v", "hi", "lo", "tp", "eps", "rev"],
           "t": ["d", "k", "id", "n", "o", "v", "pct", "hi", "lo", "rt"]}


class _Http:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj),
                                              urllib.request.HTTPSHandler(context=_ctx()))

    def get(self, url: str, timeout: int = 20, accept: str = "application/json") -> tuple[int | None, bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept,
                                                   "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"})
        try:
            with self.op.open(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read()
            except Exception:                             # noqa: BLE001
                return e.code, b""
        except Exception as e:                            # noqa: BLE001
            return None, str(e).encode()


def _fs_window(H: _Http, a: int, b: int, log: list) -> list[dict] | None:
    """[a, b] 時窗內「台股預估」全部快訊；HTTP 失敗回 None。"""
    out, p = [], 1
    while p <= 60:
        st, body = H.get(CNYES_LIST.format(a=a, b=b, p=p))
        try:
            o = json.loads(body.decode("utf-8"))
            it = o["items"]
        except Exception:                                 # noqa: BLE001
            log.append(f"HTTP {st} {body[:120]!r}")
            return None
        data = it.get("data") or []
        out += [x for x in data if a <= int(x.get("publishAt") or 0) <= b]
        if p >= int(it.get("last_page") or 1) or not data:
            break
        p += 1
        time.sleep(0.25)
    return out


def _write_lines(name: str, doc: dict, key: str) -> bool:
    """JSON 一檔股票一行（git 差異只在變動的那幾行）；內容沒變不改寫。"""
    head = {k: v for k, v in doc.items() if k != key}
    body = doc.get(key) or {}
    lines = [json.dumps(c, ensure_ascii=False) + ":" + json.dumps(body[c], ensure_ascii=False, separators=(",", ":"))
             for c in sorted(body)]
    txt = (json.dumps(head, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:-1]
           + (',' if head else '') + json.dumps(key) + ":{\n" + ",\n".join(lines) + "\n}}\n")
    p = store.LAB / name
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True


def load_fs() -> dict:
    return store.read_json(FS_FILE, None) or {"v": 1, "upto": 0, "from": None, "floor": False, "ev": {}}


def _merge_fs(doc: dict, items: list[dict], stat: dict) -> None:
    ev = doc.setdefault("ev", {})
    seen = {r[2] for rows in ev.values() for r in rows}
    for it in items:
        if it.get("newsId") in seen:
            continue
        e = parse_article(it)
        if e is None:
            stat["bad"] = stat.get("bad", 0) + 1
            if stat["bad"] <= 3:
                print(f"[fcst] 認不得的快訊格式：{it.get('newsId')} {str(it.get('title'))[:80]}")
            continue
        ev.setdefault(e["c"], []).append(_ev_row(e))
        seen.add(it.get("newsId"))
        stat["new"] = stat.get("new", 0) + 1
    for c in ev:
        ev[c].sort(key=lambda r: (r[0], r[2]))
        es = [r for r in ev[c] if r[1] == "e"]
        for r in es[:-1]:
            if len(r) > 10:
                del r[10:]                               # 舊的 EPS 快訊不留三年表格


def _prune_fs(doc: dict, today: date) -> None:
    cut = (today - timedelta(days=FS_KEEP_DAYS)).isoformat()
    for c in list(doc.get("ev", {})):
        doc["ev"][c] = [r for r in doc["ev"][c] if r[0] >= cut]
        if not doc["ev"][c]:
            del doc["ev"][c]


def update_factset(*, backfill_weeks: int = 0, budget_s: float = 120, now: datetime | None = None) -> dict:
    """補「上次讀到之後」的快訊（往前重疊一天，以 newsId 去重）；backfill_weeks>0 時再一週一窗往回補，
    連續 8 週都沒有快訊就認定到底（floor），之後不再往回。"""
    t0 = time.time()
    now = now or datetime.now(TZ)
    H = _Http()
    doc = load_fs()
    stat: dict = {"new": 0, "req_fail": 0}
    log: list[str] = []
    b = int(now.timestamp())
    a = max(int(doc.get("upto") or 0) - 86400, b - 14 * 86400)
    items = _fs_window(H, a, b, log)
    if items is None:
        stat["req_fail"] += 1
    else:
        _merge_fs(doc, items, stat)
        doc["upto"] = b                                   # 這個時窗整段讀完了
        if not doc.get("from"):
            doc["from"] = _day(a)
    empty = 0
    wk = 0
    while backfill_weeks and wk < backfill_weeks and not doc.get("floor") and time.time() - t0 < budget_s:
        end = datetime.fromisoformat(doc["from"]).replace(tzinfo=TZ)
        a2, b2 = int((end - timedelta(days=7)).timestamp()), int(end.timestamp()) - 1
        got = _fs_window(H, a2, b2, log)
        if got is None:
            stat["req_fail"] += 1
            break
        _merge_fs(doc, got, stat)
        doc["from"] = _day(a2)
        empty = empty + 1 if not got else 0
        if empty >= 8:
            doc["floor"] = True
        wk += 1
    _prune_fs(doc, now.date())
    _write_lines(FS_FILE, doc, "ev")
    stat.update({"codes": len(doc.get("ev", {})), "from": doc.get("from"), "floor": doc.get("floor"),
                 "weeks": wk, "s": round(time.time() - t0)})
    if log:
        stat["log"] = log[:3]
    return stat


# ── Yahoo Finance ───────────────────────────────────────────────────────────
def _raw(x):
    if isinstance(x, dict):
        return x.get("raw")
    return x if isinstance(x, (int, float)) else None


def _r(x, n=3):
    x = _raw(x)
    return None if x is None else round(float(x), n)


def parse_yahoo(o: dict) -> dict | None:
    """quoteSummary 回應 → 緊湊紀錄；沒有分析師資料回 None。
    {"n": 家數, "tp": [平均, 中位, 最高, 最低], "rc": [強力看好, 看好, 中立, 看淡, 強力看淡], "rm": 評等平均,
     "y0"/"y1": {"end", "e": [平均, 最低, 最高, 家數, 去年], "eg", "r": [平均, 最低, 最高, 家數, 去年]（億元）, "rg",
                 "t": [現在, 7, 30, 60, 90 天前], "rv": [7 天上修, 30 天上修, 7 天下修, 30 天下修]}}"""
    try:
        res = ((o.get("quoteSummary") or {}).get("result") or [None])[0]
    except Exception:                                     # noqa: BLE001
        return None
    if not res:
        return None
    fd = res.get("financialData") or {}
    rec: dict = {"n": _raw(fd.get("numberOfAnalystOpinions")),
                 "tp": [_r(fd.get(k), 2) for k in ("targetMeanPrice", "targetMedianPrice", "targetHighPrice",
                                                   "targetLowPrice")],
                 "rm": _r(fd.get("recommendationMean"), 2)}
    if fd.get("financialCurrency") and fd.get("financialCurrency") != "TWD":
        rec["cur"] = fd.get("financialCurrency")
    rt = [t for t in ((res.get("recommendationTrend") or {}).get("trend") or []) if t.get("period") == "0m"]
    if rt:
        rec["rc"] = [int(rt[0].get(k) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")]
    b = 1e8
    for t in ((res.get("earningsTrend") or {}).get("trend") or []):
        key = {"0y": "y0", "+1y": "y1"}.get(t.get("period"))
        if not key:
            continue
        ee, re_ = t.get("earningsEstimate") or {}, t.get("revenueEstimate") or {}
        et, er = t.get("epsTrend") or {}, t.get("epsRevisions") or {}
        y = {"end": t.get("endDate"),
             "e": [_r(ee.get("avg")), _r(ee.get("low")), _r(ee.get("high")), _raw(ee.get("numberOfAnalysts")),
                   _r(ee.get("yearAgoEps"))],
             "eg": _r(ee.get("growth"), 4),
             "r": [None if _raw(re_.get(k)) is None else round(_raw(re_.get(k)) / b, 1)
                   for k in ("avg", "low", "high")] + [_raw(re_.get("numberOfAnalysts")),
                                                      None if _raw(re_.get("yearAgoRevenue")) is None
                                                      else round(_raw(re_.get("yearAgoRevenue")) / b, 1)],
             "rg": _r(re_.get("growth"), 4),
             "t": [_r(et.get(k)) for k in ("current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo")],
             "rv": [_raw(er.get(k)) for k in ("upLast7days", "upLast30days", "downLast7Days", "downLast30days")]}
        if y["rv"][2] is None:
            y["rv"][2] = _raw(er.get("downLast7days"))
        en, rn = y["e"][3] or 0, y["r"][3] or 0
        if rn <= 0 or not y["r"][0]:
            y["r"] = None                                # 沒有營收預估（Yahoo 回 0）
            y["rg"] = None
        if en > 0 or y["r"]:
            if en <= 0:
                y["e"] = None
            rec[key] = y
    if not rec.get("n") and "y0" not in rec and "y1" not in rec:
        return None
    if not any(v is not None for v in rec["tp"]):
        rec["tp"] = None
    return rec


class _Yahoo(_Http):
    def __init__(self):
        super().__init__()
        self.crumb = None

    def login(self) -> bool:
        self.get("https://fc.yahoo.com", accept="text/html")
        for host in ("query2", "query1"):
            st, b = self.get(f"https://{host}.finance.yahoo.com/v1/test/getcrumb", accept="*/*")
            if st == 200 and b and len(b) < 40 and not b.startswith(b"{") and not b.startswith(b"<"):
                self.crumb = b.decode().strip()
                return True
        return False

    def one(self, sym: str) -> tuple[str, dict | None]:
        """回 ("ok"|"none"|"err"|"429"|"401", 紀錄)。"""
        url = (f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={YH_MODS}"
               f"&crumb={urllib.parse.quote(self.crumb or '')}")
        st, b = self.get(url)
        if st == 429:
            return "429", None
        if st == 401:
            return "401", None
        if st == 404:
            return "none", None
        if st != 200:
            return "err", None
        try:
            return ("ok", parse_yahoo(json.loads(b.decode("utf-8"))))
        except Exception:                                 # noqa: BLE001
            return "err", None


def yahoo_sym(c: str, mk: str) -> str:
    return f"{c}.TW" if mk == "tw" else f"{c}.TWO"


def load_yahoo() -> dict:
    return store.read_json(YH_FILE, None) or {"v": 1, "d": None, "full": None, "cover": [], "s": {}}


def update_yahoo(listed: dict[str, str], *, full: bool = False, budget_s: float = 300, workers: int = 4,
                 today: date | None = None, force: bool = False) -> dict:
    """一天一次。full、每週一或 cover 空 → 全部上市櫃；否則只抓 cover（有分析師的公司）。
    這次查到「沒有分析師」（200 但沒資料、或 404）的拿掉；請求失敗的保留舊紀錄（fail-open）。"""
    t0 = time.time()
    today = today or datetime.now(TZ).date()
    doc = load_yahoo()
    if doc.get("d") == today.isoformat() and not doc.get("part") and not (full or force):
        return {"skip": "今天已抓過"}
    full = full or not doc.get("cover") or (today.weekday() == 0 and doc.get("full") != today.isoformat())
    codes = sorted(listed) if full else sorted(c for c in doc.get("cover", []) if c in listed)
    Y = _Yahoo()
    if not Y.login():
        return {"err": "拿不到 crumb"}
    state = {"stop": False}

    def work(c):
        if state["stop"] or time.time() - t0 > budget_s:
            return c, "skip", None
        for k in range(3):
            st, rec = Y.one(yahoo_sym(c, listed[c]))
            if st == "429":
                time.sleep(4 * (k + 1))
                continue
            if st == "401" and k == 0:
                Y.login()
                continue
            return c, st, rec
        return c, "429", None

    res: dict[str, tuple] = {}
    n429 = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for c, st, rec in ex.map(work, codes):
            res[c] = (st, rec)
            n429 = n429 + 1 if st == "429" else 0
            if n429 >= 20:
                state["stop"] = True                     # 連續被限流：這一輪到此為止，下一輪再補
    s = dict(doc.get("s") or {})
    stat = {"ok": 0, "none": 0, "err": 0, "429": 0, "401": 0, "skip": 0}
    for c, (st, rec) in res.items():
        if st == "ok" and rec:
            s[c] = rec
            stat["ok"] += 1
        elif st in ("ok", "none"):
            s.pop(c, None)                               # 查到沒有分析師
            stat["none"] += 1
        else:
            stat[st] = stat.get(st, 0) + 1               # 失敗：保留舊值
    s = {c: s[c] for c in sorted(s) if c in listed}
    doc.update({"d": today.isoformat(), "s": s, "cover": sorted(s),
                "part": bool(stat["skip"] or stat["429"] >= 20)})   # 沒抓完 → 同一天下一輪再補
    if full and stat["skip"] == 0 and stat["429"] < 20:
        doc["full"] = today.isoformat()
    _write_lines(YH_FILE, doc, "s")
    wk = today.isocalendar()[:2]
    if s and not any(date.fromisoformat(x).isocalendar()[:2] == wk for x in store.dates(YH_ARCH)):
        store.write(YH_ARCH, today.isoformat(), {"d": today.isoformat(), "s": s})
    stat.update({"codes": len(codes), "cover": len(s), "full": full, "s": round(time.time() - t0)})
    return stat


# ── 頁面用（docs/lab_forward_plan.md 第 3 節）────────────────────────────────
def view(fs_rows: list | None, yh: dict | None) -> dict | None:
    """一檔 → x9f.json：最新 EPS 快訊（三年 EPS／營收）、最新預估股價快訊、最近 8 則調整（新到舊）、Yahoo 紀錄。
    ev：EPS ["日期","e",前值,新值,年度]；預估股價 ["日期","t",前值,新值,幅度%]。"""
    out: dict = {}
    if fs_rows:
        E = [r for r in fs_rows if r[1] == "e"]
        T = [r for r in fs_rows if r[1] == "t"]
        if E:
            r = E[-1]
            out["e"] = {"d": r[0], "n": r[3], "y": r[4], "tp": r[9], "eps": r[10], "rev": r[11]}
        if T:
            r = T[-1]
            out["t"] = {"d": r[0], "n": r[3], "v": r[5], "hi": r[7], "lo": r[8], "rt": r[9]}
        out["ev"] = [[r[0], "e", r[5], r[6], r[4]] if r[1] == "e" else [r[0], "t", r[4], r[5], r[6]]
                     for r in fs_rows[-8:][::-1]]
    if yh:
        out["y"] = yh
    return out or None


def page_doc(listed: dict | None = None, today: date | None = None) -> dict:
    """dashboard/x9f.json：每檔的法人預估（公司卡點進去才下載）。"""
    fs, yh = load_fs(), load_yahoo()
    ev, ys = fs.get("ev") or {}, yh.get("s") or {}
    codes = sorted(set(ev) | set(ys))
    if listed is not None:
        codes = [c for c in codes if c in listed]
    s = {}
    for c in codes:
        v = view(ev.get(c), ys.get(c))
        if v:
            s[c] = v
    return {"d": (today or datetime.now(TZ).date()).isoformat(), "fs_from": fs.get("from"), "yd": yh.get("d"), "s": s}


def target_price(v: dict) -> tuple[float | None, str | None]:
    """最新的法人預估股價中位數與日期：預估股價快訊與 EPS 快訊（內文也寫當時的預估股價）取較新者，沒有再用 Yahoo 中位數。"""
    e, t = v.get("e") or {}, v.get("t") or {}
    cand = [(t.get("d"), t.get("v")), (e.get("d"), e.get("tp"))]
    cand = [x for x in cand if x[0] and x[1]]
    if cand:
        d, p = max(cand)
        return p, d
    y = v.get("y") or {}
    tp = y.get("tp") or [None, None]
    p = tp[1] if tp[1] is not None else tp[0]
    return p, (None if p is None else "Yahoo")


def brief(v: dict | None, px: float | None, ye: dict | None, today: date) -> list | None:
    """機會頁飆股段每檔一行小字：[分析師家數, 今年 EPS 年增%, 近 30 天方向(1 上修/-1 下修/0), 預估股價比現價%]。"""
    if not v:
        return None
    e, y = v.get("e") or {}, v.get("y") or {}
    yr = today.year
    n = e.get("n") or y.get("n")
    est = next((r[4] if r[4] is not None else r[3] for r in e.get("eps") or [] if r[0] == yr), None)
    y0 = y.get("y0") or {}
    if est is None and str(y0.get("end") or "")[:4] == str(yr):
        est = (y0.get("e") or [None])[0]
    last = (ye or {}).get(str(yr - 1))
    eg = round((est / last - 1) * 100, 1) if est is not None and last and last > 0.05 else None
    # 近 30 天方向：FactSet 今年 EPS 的調整（30 天內第一則的前值 → 最新值）；沒有再看 Yahoo 30 天前的平均
    cut = (today - timedelta(days=30)).isoformat()
    rec = [x for x in (v.get("ev") or []) if x[1] == "e" and x[4] == yr and x[0] >= cut]
    dr = None
    if rec and rec[-1][2] and rec[0][3] is not None:
        ch = rec[0][3] / rec[-1][2] - 1
        dr = 1 if ch > 0.005 else -1 if ch < -0.005 else 0
    elif y0.get("t") and y0["t"][0] and y0["t"][2]:
        ch = y0["t"][0] / y0["t"][2] - 1
        dr = 1 if ch > 0.005 else -1 if ch < -0.005 else 0
    tp, _ = target_price(v)
    up = round((tp / px - 1) * 100, 0) if tp and px else None
    if n is None and eg is None and up is None:
        return None
    return [n, eg, dr, up]


def briefs(codes, px: dict, ye: dict, today: date | None = None) -> dict:
    today = today or datetime.now(TZ).date()
    fs, yh = load_fs(), load_yahoo()
    out = {}
    for c in codes:
        b = brief(view((fs.get("ev") or {}).get(c), (yh.get("s") or {}).get(c)), px.get(c), ye.get(c), today)
        if b:
            out[c] = b
    return out
