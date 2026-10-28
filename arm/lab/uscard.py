"""美股個股卡要的每天資料（docs/lab_cfg_v2_plan.md 第 3.3、4 節；VER 2＝docs/lab_review_plan.md 第 4 節 (a)）：配置頁美股列的股票
（手上的、要買的、名單前 5 名裡手上沒有的；fund_intro.qm_codes 同一批，約 15 檔）——近 5 年走勢（近一年每天的收盤、50 日線、成交量，
更早的每週一點）、配息、分割、52 週高點＋ Yahoo 的分析師預估、目標價、下次財報日。

每天盤後那一支（scripts/fetch_ussx_watch.py）在 50 日線檢查之後跑，日線和檢查共用同一次抓取（cached）。
同一個美股收盤只抓一次：日線已經到最近收盤那天、分析師資料這個收盤抓過＝不再抓。抓不到的那一檔沿用舊的。
只在 CI（本容器擋 Yahoo）。

data/lab/ussx_card.json：
  {"ver", "made": 台北日期, "d": 最近一個已收盤的美股交易日（這一輪要的）, "codes": 這一批, "cal": [近一年的交易日],
   "s": {代號: {"c": [收盤（分割還原）], "m": [50 日線], "v": [成交量（千股）], "at": 日線最後一天,
               "wk": [[那週最後一個交易日, 收盤, 那週成交量（千股）]]（近一年以前、5 年以內，每週一點）,
               "spl": [[日期, 倍數]]、"div": [[除息日, 每股配息（美元，分割還原）]]（都是 5 年以內）,
               "hi": [日期, 最高價]（近 252 個交易日的最高價＝52 週高點；選股條件「離 52 週高點」用的同一個）,
               "an": fcst.parse_yahoo 的紀錄＋"ed"（下次財報日；兩個＝區間）＋"ede"（日期是估的）, "an_at": 抓到分析師資料時的 d,
               "err": 這一輪沒抓到的原因}}}
  c、m、v 和 cal 一樣長（那天沒有資料＝null）。50 日線＝最近 50 個交易日含息收盤的平均換成那天的價格（ussxqm.watch_one 判斷跌破用的同一條）。
  wk 的最後一週可能和 cal 的第一週是同一週（那一週跨過近一年的起點）：頁面依週一的日期併成一點。
  VER 1（只有近一年的收盤與 50 日線）的檔照樣讀得到；沒有 wk 的代號下一輪一定重抓日線。
"""
from __future__ import annotations

import json
import time as _time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from .. import fund_intro as FI
from . import ussxspec as X

ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "data" / "lab" / "ussx_card.json"
VER = 2
VERS_OK = (1, 2)             # 讀得到的版本（VER 1 的檔沒有 wk、v、div、hi，下一輪重抓日線補上）
YEARS = 5
LONG_DAYS = YEARS * 365 + 2  # 走勢最長畫最後一天往前幾個日曆天（5 年）
BACK_DAYS = LONG_DAYS + 80   # 日線從今天往前幾個日曆天抓（5 年＋算 50 日線要的前 50 個交易日）
SHOW_DAYS = 365              # 每天一點的部分：最後一天往前幾個日曆天（更早的每週一點）
HI_N = 252                   # 52 週高點＝近幾個交易日的最高價
CLOSE_AFTER = time(16, 20)   # 紐約時間這個時間以後才算今天收盤了
BUDGET_S = 150.0             # 這一段最多跑幾秒（開始抓之前看；時間到的下一輪再抓）
WORKERS = 4
MODS = ("financialData,earningsTrend,recommendationTrend,calendarEvents,"     # fcst.YH_MODS＋財報日
        "earningsHistory,upgradeDowngradeHistory,defaultKeyStatistics,majorHoldersBreakdown,"
        "netSharePurchaseActivity,insiderTransactions")                          # 2026-10-28 第 4 步 (d)：實際 vs 預估、評等調整、做空、持股、內部人
EXTRA_DAYS = 183          # 評等調整、內部人交易只留近幾天
EXTRA_N = 10              # 各留幾筆
QS_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}?modules={mods}&crumb={crumb}"


def _ny():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except Exception:                                        # noqa: BLE001 —— 沒有時區資料：用美東標準時間（夏令時只會晚一小時才算收盤）
        return timezone(timedelta(hours=-5))


def last_close(now: datetime | None = None) -> str:
    """最近一個已經收盤的美股交易日：紐約時間 CLOSE_AFTER 以後才算今天（NYSE 休市表，xstrat._closed）。now 要帶時區。"""
    from . import xstrat as XT
    ny = (now or datetime.now(timezone.utc)).astimezone(_ny())
    d = ny.date()
    if XT._closed("spx", d) or ny.time() < CLOSE_AFTER:
        d -= timedelta(days=1)
        while XT._closed("spx", d):
            d -= timedelta(days=1)
    return d.isoformat()


# ── 日線 ─────────────────────────────────────────────────────────────────────

def cached(fetch=None, today: date | None = None, back_days: int = BACK_DAYS):
    """同一輪共用的日線抓取（ussxqm.watch 與 update 都用它）：開始日至少從 today − back_days 起（50 日線檢查要的更早就照它的），
    同一檔只抓一次（沒抓到的下一次再試）。回傳 f(代號, 開始日) → (代號, 日線, 訊息)，和 ussxqm.watch 的 fetch 一樣。
    fetch(Yahoo 代號, 開始日) 預設 ussxdata.fetch_since（一個請求最多等 20 秒）。"""
    from . import ussxdata as UD
    fetch = fetch or (lambda sym, st: UD.fetch_since(sym, st, timeout=20))
    floor = ((today or date.today()) - timedelta(days=back_days)).isoformat()
    memo: dict[str, tuple] = {}

    def f(c: str, start: str):
        st = min(start, floor)
        got = memo.get(c)
        if got is None or got[0] > st:
            _, s, msg = fetch(UD.ysym(c), st)
            if s is None:
                return c, None, msg
            memo[c] = got = (st, (c, s, msg))
        return got[1]

    f.floor = floor
    return f


def _monday(d: str) -> str:
    x = date.fromisoformat(d)
    return (x - timedelta(days=x.weekday())).isoformat()


def chart(s: dict | None, show_days: int = SHOW_DAYS, long_days: int = LONG_DAYS) -> dict | None:
    """Yahoo 日線（ussxdata.parse_chart）→ {"pts": {日期: [收盤, 50 日線, 成交量（千股）]}（最後一天往前 show_days 個日曆天）,
    "wk": [[那週最後一個交易日, 收盤, 那週成交量（千股）]]（更早、long_days 以內）, "spl"、"div"（long_days 以內）,
    "hi": [日期, 最高價]（近 HI_N 個交易日）}。50 日線不到 50 個交易日＝None。沒有日線＝None。"""
    from . import ussxdata as UD
    ds, cs = (s or {}).get("d") or [], (s or {}).get("c") or []
    if not ds:
        return None
    vs = s.get("v") or [None] * len(ds)
    hs = s.get("h") or cs
    n = X.QM_EXIT["ma"]
    tr = UD.total_return_close(s)
    last = date.fromisoformat(ds[-1])
    first = (last - timedelta(days=show_days)).isoformat()
    lfirst = (last - timedelta(days=long_days)).isoformat()

    def vk(k):
        v = vs[k] if k < len(vs) else None
        return int(round(v / 1000)) if isinstance(v, (int, float)) and v >= 0 else None

    pts, wk = {}, []
    for k, d in enumerate(ds):
        if d <= lfirst:
            continue
        if d <= first:                                          # 近一年以前：每週一點（那週最後一個交易日的收盤、成交量加總）
            m0, v0 = _monday(d), vk(k)
            if wk and wk[-1][3] == m0:
                w = wk[-1]
                w[0], w[1] = d, round(cs[k], 2)
                w[2] = None if w[2] is None or v0 is None else w[2] + v0
            else:
                wk.append([d, round(cs[k], 2), v0, m0])
            continue
        m = None
        if k >= n - 1 and tr[k] > 0:
            m = round(sum(tr[k - n + 1:k + 1]) / n * cs[k] / tr[k], 2)
        pts[d] = [round(cs[k], 2), m, vk(k)]
    h0 = max(0, len(ds) - HI_N)
    kh = max(range(h0, len(ds)), key=lambda k: (hs[k] if k < len(hs) and hs[k] is not None else cs[k], k))
    hi = [ds[kh], round(hs[kh] if kh < len(hs) and hs[kh] is not None else cs[kh], 2)]
    return {"pts": pts, "wk": [w[:3] for w in wk], "hi": hi,
            "spl": [list(x) for x in s.get("spl") or [] if x[0] > lfirst],
            "div": [[x[0], round(float(x[1]), 4)] for x in s.get("div") or [] if x[0] > lfirst]}


# ── 分析師與財報日 ───────────────────────────────────────────────────────────

def parse_cal(o: dict) -> dict:
    """quoteSummary 的 calendarEvents → {"ed": [下次財報日；兩個＝公司還沒公布、Yahoo 估的區間], "ede": 日期是不是估的}；沒有＝{}。"""
    try:
        res = ((o.get("quoteSummary") or {}).get("result") or [None])[0] or {}
    except Exception:                                        # noqa: BLE001
        return {}
    ce = (res.get("calendarEvents") or {}).get("earnings") or {}
    ds = []
    for x in ce.get("earningsDate") or []:
        fmt = x.get("fmt") if isinstance(x, dict) else None
        raw = x.get("raw") if isinstance(x, dict) else x
        d = None
        if isinstance(fmt, str) and len(fmt) == 10 and fmt[4] == "-" and fmt[7] == "-":
            d = fmt
        elif isinstance(raw, (int, float)) and raw > 0:
            d = datetime.fromtimestamp(raw, _ny()).date().isoformat()
        if d and d not in ds:
            ds.append(d)
    if not ds:
        return {}
    out = {"ed": sorted(ds)}
    est = ce.get("isEarningsDateEstimate")
    est = est.get("raw") if isinstance(est, dict) else est
    if isinstance(est, bool):
        out["ede"] = est
    return out


def _rv(x):
    """Yahoo 的 {"raw": 數字} 或數字 → 數字（不是有限的數字＝None）。"""
    import math
    if isinstance(x, dict):
        x = x.get("raw")
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def _dt(x) -> str | None:
    """Yahoo 的日期（{"raw": 時間戳, "fmt": "YYYY-MM-DD"}、時間戳或日期字串）→ 紐約的日期。"""
    fmt = x.get("fmt") if isinstance(x, dict) else x
    if isinstance(fmt, str) and len(fmt) >= 10 and fmt[4] == "-" and fmt[7] == "-":
        return fmt[:10]
    raw = _rv(x)
    if raw and raw > 0:
        return datetime.fromtimestamp(raw, _ny()).date().isoformat()
    return None


def _s(x, n: int = 60) -> str:
    return str(x or "").strip()[:n]


def parse_extra(o: dict, today: str | None = None) -> dict:
    """quoteSummary 的其他模組（docs/lab_review_plan.md 第 4 節 (d)）→ 緊湊紀錄（沒有的鍵不放）：
    "eh": [[季底, 實際 EPS, 預估 EPS]]（近 4 季，舊到新）、
    "ud": [[日期, 券商, 動作, 原評等, 新評等, 原目標價, 新目標價]]（近 EXTRA_DAYS 天、新到舊、最多 EXTRA_N 筆）、
    "sh": [做空占流通股, 回補天數, 做空股數, 上個月做空股數, 資料日]、"mh": [內部人持股, 法人持股, 法人家數]、
    "ns": [期間, 買進筆數, 買進股數, 賣出筆數, 賣出股數, 淨買股數, 淨買占內部人持股]、
    "tx": [[日期, 姓名, 職稱, 內容, 股數, 金額]]（近 EXTRA_DAYS 天、新到舊、最多 EXTRA_N 筆）。"""
    try:
        res = ((o.get("quoteSummary") or {}).get("result") or [None])[0] or {}
    except Exception:                                        # noqa: BLE001
        return {}
    today = today or datetime.now(_ny()).date().isoformat()
    cut = (date.fromisoformat(today) - timedelta(days=EXTRA_DAYS)).isoformat()
    out: dict = {}
    eh = []
    for x in (res.get("earningsHistory") or {}).get("history") or []:
        q, a, e = _dt(x.get("quarter")), _rv(x.get("epsActual")), _rv(x.get("epsEstimate"))
        if q and (a is not None or e is not None):
            eh.append([q, None if a is None else round(a, 4), None if e is None else round(e, 4)])
    if eh:
        out["eh"] = sorted(eh)[-4:]
    ud = []
    for x in (res.get("upgradeDowngradeHistory") or {}).get("history") or []:
        d = _dt(x.get("epochGradeDate"))
        if not d or d < cut:
            continue
        ud.append([d, _s(x.get("firm")), _s(x.get("action"), 12), _s(x.get("fromGrade"), 30), _s(x.get("toGrade"), 30),
                   _rv(x.get("priorPriceTarget")), _rv(x.get("currentPriceTarget"))])
    if ud:
        out["ud"] = sorted(ud, key=lambda r: r[0], reverse=True)[:EXTRA_N]
    ks = res.get("defaultKeyStatistics") or {}
    sh = [_rv(ks.get("shortPercentOfFloat")), _rv(ks.get("shortRatio")), _rv(ks.get("sharesShort")),
          _rv(ks.get("sharesShortPriorMonth")), _dt(ks.get("dateShortInterest"))]
    if any(v is not None for v in sh[:4]):
        out["sh"] = sh
    mh = res.get("majorHoldersBreakdown") or {}
    m = [_rv(mh.get("insidersPercentHeld")), _rv(mh.get("institutionsPercentHeld")), _rv(mh.get("institutionsCount"))]
    if m[0] is None:
        m[0] = _rv(ks.get("heldPercentInsiders"))
    if m[1] is None:
        m[1] = _rv(ks.get("heldPercentInstitutions"))
    if any(v is not None for v in m):
        out["mh"] = m
    ns = res.get("netSharePurchaseActivity") or {}
    n = [_s(ns.get("period"), 8)] + [_rv(ns.get(k)) for k in ("buyInfoCount", "buyInfoShares", "sellInfoCount", "sellInfoShares",
                                                            "netInfoShares", "netPercentInsiderShares")]
    if any(v is not None for v in n[1:]):
        out["ns"] = n
    tx = []
    for x in (res.get("insiderTransactions") or {}).get("transactions") or []:
        d = _dt(x.get("startDate"))
        if not d or d < cut:
            continue
        tx.append([d, _s(x.get("filerName"), 40), _s(x.get("filerRelation"), 40), _s(x.get("transactionText"), 80),
                   _rv(x.get("shares")), _rv(x.get("value"))])
    if tx:
        out["tx"] = sorted(tx, key=lambda r: r[0], reverse=True)[:EXTRA_N]
    return out


def dump(Y, c: str) -> str:
    """CI 探針：一檔 quoteSummary 新加的那幾個模組長什麼樣子（每個模組前 1,500 字）。"""
    from . import ussxdata as UD
    url = QS_URL.format(sym=urllib.parse.quote(UD.ysym(c)), mods=MODS, crumb=urllib.parse.quote(Y.crumb or ""))
    st, b = Y.get(url)
    lines = [f"[美股個股卡探針] {c} HTTP {st}，{len(b or b'')} bytes"]
    try:
        res = ((json.loads((b or b"{}").decode("utf-8")).get("quoteSummary") or {}).get("result") or [None])[0] or {}
    except Exception as e:                                   # noqa: BLE001
        return lines[0] + f"；解析失敗 {type(e).__name__}"
    for k in MODS.split(",")[4:]:
        lines.append(f"  {k}: {json.dumps(res.get(k), ensure_ascii=False)[:1500]}")
    lines.append("  解析：" + json.dumps(parse_extra({"quoteSummary": {"result": [res]}}), ensure_ascii=False)[:1500])
    return "\n".join(lines)


def analyst(Y, c: str) -> tuple[str, dict | None]:
    """一檔的 Yahoo quoteSummary → ("ok"|"none"|"err"|"429"|"401", 紀錄)；紀錄＝fcst.parse_yahoo＋parse_cal，
    ok 但什麼都沒有（沒有分析師、沒有財報日）＝None。Y＝fcst._Yahoo（已經 login）。"""
    from . import fcst
    from . import ussxdata as UD
    url = QS_URL.format(sym=urllib.parse.quote(UD.ysym(c)), mods=MODS, crumb=urllib.parse.quote(Y.crumb or ""))
    st, b = Y.get(url)
    if st in (429, 401):
        return str(st), None
    if st == 404:
        return "none", None
    if st != 200:
        return "err", None
    try:
        o = json.loads(b.decode("utf-8"))
    except Exception:                                        # noqa: BLE001
        return "err", None
    rec = fcst.parse_yahoo(o) or {}
    rec.update(parse_cal(o))
    rec.update(parse_extra(o))
    return "ok", (rec or None)


def _yahoo():
    from . import fcst
    Y = fcst._Yahoo()
    return Y if Y.login() else None


# ── 存讀 ─────────────────────────────────────────────────────────────────────

def load(path: Path | None = None) -> dict:
    """存檔；版本不是 VERS_OK＝沒有。"""
    try:
        doc = json.loads((path or CARD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if doc.get("ver") in VERS_OK else {}


def save(doc: dict, path: Path | None = None) -> bool:
    from . import ussxqm as QM
    return QM.save(doc, path or CARD)


def points(doc: dict, c: str) -> dict:
    """存檔裡一檔的日線 → {日期: [收盤, 50 日線, 成交量]}（沒有資料的日子不列；VER 1 的檔沒有成交量＝None）。"""
    rec = (doc.get("s") or {}).get(c) or {}
    cal = doc.get("cal") or []
    cs, ms, vs = rec.get("c") or [], rec.get("m") or [], rec.get("v") or []
    return {d: [cs[i], ms[i] if i < len(ms) else None, vs[i] if i < len(vs) else None]
            for i, d in enumerate(cal) if i < len(cs) and cs[i] is not None}


LONG_KEYS = ("wk", "div", "hi")                               # VER 2 才有的（沒有＝要重抓日線）


# ── 每天 ─────────────────────────────────────────────────────────────────────

def update(L: dict | None = None, *, fetch=None, force: bool = False, budget_s: float = BUDGET_S, now: datetime | None = None,
           Y=None, path: Path | None = None, today: date | None = None, made: str | None = None) -> dict:
    """抓這一批還沒有最近收盤的日線與分析師資料、寫 data/lab/ussx_card.json；回統計。force＝全部重抓（CI 探針）。
    L＝每週紀錄（預設讀 data/lab/ussx_qm_live.json）；fetch＝cached() 回的函式（和 50 日線檢查共用）；Y＝fcst._Yahoo（測試用）。"""
    t0 = _time.time()
    if L is None:
        from . import ussxqm as QM
        L = QM.load_live()
    codes, _ = FI.qm_codes(L)
    if not codes:
        return {"skip": "還沒有每週紀錄"}
    want = last_close(now)
    old = load(path)
    S = {}
    for c in codes:
        r0 = (old.get("s") or {}).get(c) or {}
        S[c] = {"pts": points(old, c), "spl": r0.get("spl") or [], "at": r0.get("at"), "an_at": r0.get("an_at"),
                "long": all(k in r0 for k in LONG_KEYS)}
        for k in LONG_KEYS + ("an",):
            if k in r0:
                S[c][k] = r0[k]
    need_c = [c for c in codes if force or not S[c]["at"] or S[c]["at"] < want or not S[c]["long"]]
    need_a = [c for c in codes if force or S[c]["an_at"] != want]
    stat = {"want": want, "codes": len(codes), "chart": 0, "an": 0, "skip_n": 0, "err": []}
    if not need_c and not need_a and sorted(old.get("s") or {}) == sorted(codes) and old.get("ver") == VER:
        stat["skip"] = f"已經有 {want} 收盤的資料"
        return stat
    fetch = fetch or cached(today=today)
    start = getattr(fetch, "floor", None) or ((today or date.today()) - timedelta(days=BACK_DAYS)).isoformat()
    if need_a and Y is None:
        Y = _yahoo()
        if Y is None:
            stat["err"].append("分析師：拿不到 Yahoo 的 crumb，這一輪不抓")
            need_a = []

    def work(t):
        kind, c = t
        if _time.time() - t0 > budget_s:
            return kind, c, "skip", None
        if kind == "c":
            try:
                _, s, msg = fetch(c, start)
            except Exception as e:                           # noqa: BLE001 —— 抓不到只少那一檔
                return kind, c, f"{type(e).__name__}: {e}", None
            return kind, c, msg, s
        for k in range(3):
            st, rec = analyst(Y, c)
            if st == "429":
                _time.sleep(4 * (k + 1))
                continue
            if st == "401" and k == 0:
                Y.login()
                continue
            return kind, c, st, rec
        return kind, c, "429", None

    tasks = [("c", c) for c in need_c] + [("a", c) for c in need_a]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for kind, c, st, x in ex.map(work, tasks):
            r = S[c]
            if st == "skip":
                stat["skip_n"] += 1
                continue
            if kind == "c":
                ch = chart(x) if x is not None else None
                if ch and ch["pts"]:
                    r["pts"], r["spl"], r["at"] = ch["pts"], ch["spl"], max(ch["pts"])
                    r.update({k: ch[k] for k in LONG_KEYS})
                    stat["chart"] += 1
                else:
                    r["err"] = "查不到日線" if x is not None else f"日線：{st}"
                    stat["err"].append(f"{c} {r['err']}")
                continue
            if st in ("ok", "none"):
                r["an"], r["an_at"] = x, want
                stat["an"] += 1
            else:
                r["aerr"] = st
                stat["err"].append(f"{c} 分析師：{st}")
    cut = (date.fromisoformat(want) - timedelta(days=SHOW_DAYS)).isoformat()
    cal = sorted({d for c in codes for d in S[c]["pts"] if d > cut})
    out = {}
    for c in codes:
        r = S[c]
        o = {}
        if any(d in r["pts"] for d in cal):
            for j, k in enumerate(("c", "m", "v")):
                o[k] = [(r["pts"].get(d) or [None, None, None])[j] for d in cal]
        for k in ("at", "an_at", "err", "aerr"):
            if r.get(k):
                o[k] = r[k]
        if r.get("spl"):
            o["spl"] = r["spl"]
        for k in LONG_KEYS:
            if k in r:
                o[k] = r[k]
        if "an" in r:
            o["an"] = r["an"]
        out[c] = o
    if made is None:
        from ..clock import today_tw
        made = today_tw().isoformat()
    doc = {"ver": VER, "made": made, "d": want, "codes": codes, "cal": cal, "s": out}
    stat["saved"] = save(doc, path)
    stat["s"] = round(_time.time() - t0, 1)
    return stat


def summary(st: dict) -> str:
    if st.get("skip") and "chart" not in st:
        return f"[美股個股卡] {st['skip']}"
    if st.get("skip"):
        return f"[美股個股卡] {st['skip']}（{st['codes']} 檔）"
    s = (f"[美股個股卡] {st['want']} 收盤：{st['codes']} 檔、日線 {st['chart']} 檔、分析師 {st['an']} 檔"
         f"（{'有更新' if st.get('saved') else '沒有變'}，{st.get('s')} 秒）")
    if st.get("skip_n"):
        s += f"；時間到沒抓 {st['skip_n']} 項，下一輪再抓"
    return s + "".join(f"\n  ⚠ {e}" for e in st.get("err") or [])
