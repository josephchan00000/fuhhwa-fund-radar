"""美股財報季的資料（規格 arm/lab/ernusspec.py 第 2 點；docs/lab_earnings_plan.md 第 11.2 節）。只在 CI 跑（本容器擋 Yahoo、那斯達克）。

每個美股收盤抓一次（afterhours_refresh.yml 的 scripts/fetch_earn_us.py；同一個收盤抓過就跳過，抓不到的那一家沿用舊的）：
  Yahoo quoteSummary（earnings、earningsHistory、earningsTrend、calendarEvents、incomeStatementHistoryQuarterly）
  ＋ Yahoo 季資料（fundamentals-timeseries：更早幾季的營收、淨利）＋ Yahoo 日線（近 PX_DAYS 個日曆天）
  ＋ 那斯達克財報行事曆（清單內公司公布的那幾天，每一天抓一次）。
data/lab/earn_us_raw.json：
  {"ver", "made": 台北日期, "at": 這一輪要的美股收盤日, "codes": 清單,
   "s": {代號: {"at": 抓到 Yahoo 資料時的收盤日,
               "q": {期末日: {"rt": 公布時間（美東 YYYY-MM-DDTHH:MM）, "ea": 實際 EPS, "ee": 當時預估 EPS, "rev": 營收, "ni": 淨利}}（最多 KEEP_Q 季）,
               "q0": {"end": 目前這一季期末日, "e": 預估 EPS, "en": 家數, "r": 預估營收, "rn": 家數},
               "snap": {期末日: {"e", "en", "r", "rn", "d": 記下的收盤日}}（公布前最後一版；公布時間過了就不改）,
               "ed": [下次財報日], "ede": 日期是不是估的,
               "ev": {期末日: [[日期, 收盤], ...]}（公布日前後各 EV_N 個交易日；後面湊齊就不再改）,
               "p1m": [[最近收盤日, 收盤], [PX1M 個交易日前, 收盤]], "err": 這一輪沒抓到的原因}},
   "nq": {日期: {代號: [實際 EPS, 預估 EPS, 家數, 會計季]}}（只留清單內）, "nq_done": [抓過的日期]}
"""
from __future__ import annotations

import json
import time as _time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..clock import today_tw
from . import ernusspec as S

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "lab" / "earn_us_raw.json"
VER = 1
MODS = "earnings,earningsHistory,earningsTrend,calendarEvents,incomeStatementHistoryQuarterly"
QS_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={mods}&crumb={crumb}"
TS_URL = ("https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{sym}"
          "?type=quarterlyTotalRevenue,quarterlyNetIncome&period1={p1}&period2={p2}")
KEEP_Q = 12            # 每家留幾季
TS_DAYS = 800          # 季資料往回抓幾個日曆天（含去年同季）
PX_DAYS = 150          # 日線往回抓幾個日曆天
EV_N = 3               # 公布日前後各留幾個交易日的收盤
NQ_BACK = 120          # 那斯達克只補這幾天內公布的
NQ_RETRY = 3           # 公布後幾天內，清單內公司那天還沒有實際 EPS 就再抓
BUDGET_S = 200.0
WORKERS = 4


def _ny():
    from .uscard import _ny as ny
    return ny()


def _rv(x):
    from .uscard import _rv as rv
    return rv(x)


def _dt(x):
    from .uscard import _dt as dt
    return dt(x)


def _ts_et(x) -> str | None:
    """Yahoo 的時間戳（{"raw": 秒}）→ 美東 YYYY-MM-DDTHH:MM。"""
    raw = _rv(x)
    if not raw or raw <= 0:
        return None
    return datetime.fromtimestamp(raw, _ny()).strftime("%Y-%m-%dT%H:%M")


def _r(x, n=4):
    return None if x is None else round(x, n)


# ── 解析 ─────────────────────────────────────────────────────────────────────

def parse_qs(o: dict) -> dict:
    """quoteSummary → {"q": {期末日: {...}}, "q0": {...}, "ed", "ede"}（沒有的鍵不放）。"""
    try:
        res = ((o.get("quoteSummary") or {}).get("result") or [None])[0] or {}
    except Exception:                                        # noqa: BLE001
        return {}
    q: dict[str, dict] = {}
    lab: dict[str, str] = {}                                 # earningsChart 的季別（例 3Q2026）→ 期末日
    ern = res.get("earnings") or {}
    for x in (ern.get("earningsChart") or {}).get("quarterly") or []:
        end = _dt(x.get("periodEndDate"))
        if not end:
            continue
        r = q.setdefault(end, {})
        r["rt"] = _ts_et(x.get("reportedDate"))
        r["ea"], r["ee"] = _r(_rv(x.get("actual"))), _r(_rv(x.get("estimate")))
        if x.get("date"):
            lab[str(x["date"])] = end
    for x in (res.get("earningsHistory") or {}).get("history") or []:      # earningsChart 少的季用這裡補
        end = _dt(x.get("quarter"))
        if not end:
            continue
        r = q.setdefault(end, {})
        if r.get("ea") is None:
            r["ea"] = _r(_rv(x.get("epsActual")))
        if r.get("ee") is None:
            r["ee"] = _r(_rv(x.get("epsEstimate")))
    for x in (ern.get("financialsChart") or {}).get("quarterly") or []:
        end = lab.get(str(x.get("date") or ""))
        if end:
            rev, ni = _rv(x.get("revenue")), _rv(x.get("earnings"))
            if rev:
                q[end]["rev"] = rev
            if ni is not None:
                q[end]["ni"] = ni
    for x in (res.get("incomeStatementHistoryQuarterly") or {}).get("incomeStatementHistory") or []:
        end, rev = _dt(x.get("endDate")), _rv(x.get("totalRevenue"))
        if end and rev:                                      # 其他欄位 Yahoo 現在都給 0，只拿營收
            q.setdefault(end, {}).setdefault("rev", rev)
    out: dict = {"q": {k: {kk: vv for kk, vv in v.items() if vv is not None} for k, v in q.items()}}
    for t in (res.get("earningsTrend") or {}).get("trend") or []:
        if t.get("period") != "0q" or not t.get("endDate"):
            continue
        ee, re_ = t.get("earningsEstimate") or {}, t.get("revenueEstimate") or {}
        q0 = {"end": str(t["endDate"])[:10], "e": _r(_rv(ee.get("avg"))), "en": _rv(ee.get("numberOfAnalysts")),
              "r": _rv(re_.get("avg")), "rn": _rv(re_.get("numberOfAnalysts"))}
        out["q0"] = {k: (int(v) if k in ("en", "rn") and v is not None else v) for k, v in q0.items() if v is not None}
    from .uscard import parse_cal
    out.update(parse_cal(o))
    return out


def parse_ts(o: dict) -> dict:
    """fundamentals-timeseries → {期末日: {"rev", "ni"}}（只收三個月的）。"""
    out: dict[str, dict] = {}
    try:
        rs = ((o.get("timeseries") or {}).get("result")) or []
    except Exception:                                        # noqa: BLE001
        return {}
    for r in rs:
        k = ((r.get("meta") or {}).get("type") or [None])[0]
        key = {"quarterlyTotalRevenue": "rev", "quarterlyNetIncome": "ni"}.get(k)
        if not key:
            continue
        for x in r.get(k) or []:
            if not x or x.get("periodType") not in (None, "3M"):
                continue
            v = _rv((x.get("reportedValue") or {}))
            d = str(x.get("asOfDate") or "")[:10]
            if v is not None and len(d) == 10:
                out.setdefault(d, {})[key] = v
    return out


def merge_q(old: dict, new: dict, ts: dict | None = None) -> dict:
    """舊的季＋這一輪的季（這一輪有的值蓋過舊的）＋季資料只補缺的；留最新 KEEP_Q 季。"""
    out = {k: dict(v) for k, v in (old or {}).items()}
    for k, v in (new or {}).items():
        out.setdefault(k, {}).update(v)
    for k, v in (ts or {}).items():
        r = out.setdefault(k, {})
        for kk, vv in v.items():
            r.setdefault(kk, vv)
    return {k: out[k] for k in sorted(out)[-KEEP_Q:]}


def snapshot(snap: dict, q: dict, q0: dict | None, at: str, now_et: str) -> dict:
    """規格第 5 點：目前這一季的預估每天記，那一季公布時間過了就不再改。"""
    snap = dict(snap or {})
    if not q0 or not q0.get("end") or (q0.get("e") is None and q0.get("r") is None):
        return snap
    end = q0["end"]
    rt = (q.get(end) or {}).get("rt")
    if rt and rt <= now_et:
        return snap
    snap[end] = {"e": q0.get("e"), "en": q0.get("en"), "r": q0.get("r"), "rn": q0.get("rn"), "d": at}
    return {k: snap[k] for k in sorted(snap)[-KEEP_Q:]}


def events(old: dict, q: dict, ds: list, cs: list) -> dict:
    """公布日前後的收盤（規格第 7 點用）：日線涵蓋得到、後面還沒湊齊 EV_N 天的季才重寫。"""
    ev = {k: v for k, v in (old or {}).items() if k in q}
    if not ds:
        return ev
    for end, r in q.items():
        rt = r.get("rt")
        if not rt:
            continue
        d = rt[:10]
        have = ev.get(end) or []
        if sum(1 for x in have if x[0] > d) >= EV_N:
            continue
        if d < ds[0] or d > ds[-1] and not have:
            continue
        i = next((k for k, x in enumerate(ds) if x >= d), len(ds))
        lo = max(0, i - EV_N)
        if i - lo < 1:                                       # 日線沒有公布日以前的收盤：等不到前一天，不記
            continue
        hi = min(len(ds), i + EV_N + (1 if i < len(ds) and ds[i] == d else 0))
        ev[end] = [[ds[k], round(cs[k], 4)] for k in range(lo, hi)]
    return ev


def p1m(ds: list, cs: list) -> list | None:
    if len(ds) <= S.PX1M:
        return None
    return [[ds[-1], round(cs[-1], 4)], [ds[-1 - S.PX1M], round(cs[-1 - S.PX1M], 4)]]


# ── 那斯達克 ─────────────────────────────────────────────────────────────────

def nq_need(S_: dict, nq: dict, done: list, today: str) -> list[str]:
    """要抓的那斯達克日期：清單內公司公布的那一天（美東日期）＋隔一天（NQ_DAYS），NQ_BACK 天內、還沒抓過；
    公布後 NQ_RETRY 天內那天清單內有公司還沒有實際 EPS＝再抓一次。"""
    cut = (date.fromisoformat(today) - timedelta(days=NQ_BACK)).isoformat()
    want = set()
    for c, r in S_.items():
        for end, x in (r.get("q") or {}).items():
            d = (x.get("rt") or "")[:10]
            if d and cut <= d <= today:
                want.add(d)
                d1 = (date.fromisoformat(d) + timedelta(days=S.NQ_DAYS)).isoformat()
                if d1 <= today:
                    want.add(d1)
    dn = set(done or [])
    out = []
    for d in sorted(want):
        if d not in dn:
            out.append(d)
            continue
        recent = (date.fromisoformat(today) - date.fromisoformat(d)).days <= NQ_RETRY
        if recent and any(v[0] is None for v in (nq.get(d) or {}).values()):
            out.append(d)
    return out


def nq_keep(rows: list, codes: set) -> dict:
    """那斯達克一天的列 → {代號: [實際, 預估, 家數, 會計季]}（只留清單內；代號照 Yahoo 的寫法）。"""
    out = {}
    for r in rows or []:
        sym = str(r[0]).upper().replace("/", ".")
        for k in (sym, sym.replace(".", "-")):
            if k in codes:
                out[k] = list(r[1:5])
    return out


# ── 存讀 ─────────────────────────────────────────────────────────────────────

def load(path: Path | None = None) -> dict:
    try:
        doc = json.loads((path or RAW).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if doc.get("ver") == VER else {}


def save(doc: dict, path: Path | None = None) -> bool:
    """一家一行（git diff 小）；內容沒變不改寫。"""
    path = path or RAW
    head = {k: v for k, v in doc.items() if k not in ("s", "nq")}

    def block(d):
        return "{\n" + ",\n".join(json.dumps(k) + ":" + json.dumps(d[k], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                                  for k in sorted(d)) + "\n}"
    txt = (json.dumps(head, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:-1]
           + ',\n"s":' + block(doc.get("s") or {}) + ',\n"nq":' + block(doc.get("nq") or {}) + "}\n")
    if path.exists() and path.read_text(encoding="utf-8") == txt:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(txt, encoding="utf-8")
    tmp.replace(path)
    return True


# ── 每天 ─────────────────────────────────────────────────────────────────────

def _yget(Y, url: str):
    for k in range(3):
        st, b = Y.get(url)
        if st == 429:
            _time.sleep(4 * (k + 1))
            continue
        if st == 401 and k == 0:
            Y.login()
            continue
        return st, b
    return 429, b""


def fetch_one(Y, c: str, at: str, now: datetime) -> tuple[str, dict | None, str]:
    """一家：quoteSummary＋季資料＋日線 → (代號, {"qs", "ts", "ds", "cs"}, 訊息)。"""
    from .ussxdata import fetch_since, ysym
    sym = ysym(c)
    st, b = _yget(Y, QS_URL.format(sym=urllib.parse.quote(sym), mods=MODS, crumb=urllib.parse.quote(Y.crumb or "")))
    if st == 404:
        return c, None, "Yahoo 查不到"
    if st != 200:
        return c, None, f"quoteSummary HTTP {st}"
    try:
        qs = parse_qs(json.loads(b.decode("utf-8")))
    except Exception as e:                                   # noqa: BLE001
        return c, None, f"quoteSummary 解析失敗 {type(e).__name__}"
    p2 = int(now.timestamp())
    st2, b2 = _yget(Y, TS_URL.format(sym=urllib.parse.quote(sym), p1=p2 - TS_DAYS * 86400, p2=p2))
    try:
        ts = parse_ts(json.loads(b2.decode("utf-8"))) if st2 == 200 else {}
    except Exception:                                        # noqa: BLE001
        ts = {}
    start = (now.astimezone(_ny()).date() - timedelta(days=PX_DAYS)).isoformat()
    _, s, msg = fetch_since(sym, start, timeout=20)
    ds, cs = (s or {}).get("d") or [], (s or {}).get("c") or []
    ok = [(d, x) for d, x in zip(ds, cs) if d <= at and x]
    return c, {"qs": qs, "ts": ts, "ds": [d for d, _ in ok], "cs": [x for _, x in ok]}, "ok" if ok else f"日線：{msg}"


def update(codes: list[str] | None = None, *, now: datetime | None = None, force: bool = False, budget_s: float = BUDGET_S,
           Y=None, fetch=None, nq_fetch=None, path: Path | None = None, made: str | None = None) -> dict:
    """抓這一輪、寫 data/lab/earn_us_raw.json；回統計。fetch(Y, 代號, 收盤日, now)、nq_fetch(日期) 測試用。"""
    from .uscard import last_close
    t0 = _time.time()
    now = now or datetime.now(timezone.utc)
    if codes is None:
        from .earnus import members
        codes = sorted(members())
    want = last_close(now)
    now_et = now.astimezone(_ny()).strftime("%Y-%m-%dT%H:%M")
    old = load(path)
    stat = {"want": want, "codes": len(codes), "ok": 0, "nq": 0, "skip_n": 0, "err": []}
    S_ = {c: dict((old.get("s") or {}).get(c) or {}) for c in codes}
    need = [c for c in codes if force or S_[c].get("at") != want]
    if not need and old.get("at") == want and sorted(old.get("s") or {}) == sorted(codes) and not force:
        stat["skip"] = f"已經有 {want} 收盤的資料"
        return stat
    if need and Y is None:
        from .uscard import _yahoo
        Y = _yahoo()
        if Y is None:
            stat["err"].append("拿不到 Yahoo 的 crumb，這一輪不抓 Yahoo")
            need = []
    fetch = fetch or fetch_one

    def work(c):
        if _time.time() - t0 > budget_s:
            return c, "skip", None
        try:
            _, x, msg = fetch(Y, c, want, now)
        except Exception as e:                               # noqa: BLE001 —— 抓不到只少那一家
            return c, f"{type(e).__name__}: {str(e)[:120]}", None
        return c, msg, x

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for c, msg, x in ex.map(work, need):
            r = S_[c]
            if msg == "skip":
                stat["skip_n"] += 1
                continue
            if x is None:
                r["err"] = msg
                stat["err"].append(f"{c} {msg}")
                continue
            qs = x["qs"]
            r["q"] = merge_q(r.get("q"), qs.get("q"), x.get("ts"))
            if qs.get("q0"):
                r["q0"] = qs["q0"]
            r["snap"] = snapshot(r.get("snap"), r["q"], qs.get("q0"), want, now_et)
            for k in ("ed", "ede"):
                if k in qs:
                    r[k] = qs[k]
                else:
                    r.pop(k, None)
            r["ev"] = events(r.get("ev"), r["q"], x["ds"], x["cs"])
            pm = p1m(x["ds"], x["cs"])
            if pm:
                r["p1m"] = pm
            r["at"] = want
            r.pop("err", None)
            if msg != "ok":
                r["err"] = msg
            stat["ok"] += 1
    nq, done = dict(old.get("nq") or {}), list(old.get("nq_done") or [])
    todo = nq_need(S_, nq, done, now.astimezone(_ny()).date().isoformat())
    if todo:
        if nq_fetch is None:
            from .usstk import fetch_earn_day as nq_fetch
        cs_ = set(codes)
        for d in todo:
            if _time.time() - t0 > budget_s + 60:
                stat["err"].append("那斯達克：時間到，下一輪再補")
                break
            _, rows, msg = nq_fetch(d)
            if rows is None:
                stat["err"].append(f"那斯達克 {d}：{msg}")
                continue
            keep = nq_keep(rows, cs_)
            if keep:
                nq[d] = keep
            else:
                nq.pop(d, None)
            if d not in done:
                done.append(d)
            stat["nq"] += 1
    cut = (date.fromisoformat(want) - timedelta(days=400)).isoformat()
    doc = {"ver": VER, "made": made or today_tw().isoformat(), "at": want,
           "codes": sorted(codes), "s": {c: S_[c] for c in sorted(codes)},
           "nq": {d: v for d, v in nq.items() if d >= cut}, "nq_done": sorted(d for d in set(done) if d >= cut)}
    stat["changed"] = save(doc, path)
    return stat
