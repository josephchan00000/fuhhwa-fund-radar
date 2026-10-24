"""美股個股卡要的每天資料（docs/lab_cfg_v2_plan.md 第 3.3、4 節）：配置頁美股列的股票（手上的、要買的、名單前 5 名裡
手上沒有的；fund_intro.qm_codes 同一批，約 15 檔）——近一年日線（收盤、50 日線）＋ Yahoo 的分析師預估、目標價、下次財報日。

每天盤後那一支（scripts/fetch_ussx_watch.py）在 50 日線檢查之後跑，日線和檢查共用同一次抓取（cached）。
同一個美股收盤只抓一次：日線已經到最近收盤那天、分析師資料這個收盤抓過＝不再抓。抓不到的那一檔沿用舊的。
只在 CI（本容器擋 Yahoo）。

data/lab/ussx_card.json：
  {"ver", "made": 台北日期, "d": 最近一個已收盤的美股交易日（這一輪要的）, "codes": 這一批, "cal": [近一年的交易日],
   "s": {代號: {"c": [收盤（分割還原）], "m": [50 日線], "at": 日線最後一天, "spl": [[日期, 倍數]]（近一年的分割）,
               "an": fcst.parse_yahoo 的紀錄＋"ed"（下次財報日；兩個＝區間）＋"ede"（日期是估的）, "an_at": 抓到分析師資料時的 d,
               "err": 這一輪沒抓到的原因}}}
  c、m 和 cal 一樣長（那天沒有資料＝null）。50 日線＝最近 50 個交易日含息收盤的平均換成那天的價格（ussxqm.watch_one 判斷跌破用的同一條）。
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
VER = 1
BACK_DAYS = 440              # 日線從今天往前幾個日曆天抓（近一年＋算 50 日線要的前 50 個交易日）
SHOW_DAYS = 365              # 卡片畫最後一天往前幾個日曆天
CLOSE_AFTER = time(16, 20)   # 紐約時間這個時間以後才算今天收盤了
BUDGET_S = 150.0             # 這一段最多跑幾秒（開始抓之前看；時間到的下一輪再抓）
WORKERS = 4
MODS = "financialData,earningsTrend,recommendationTrend,calendarEvents"     # fcst.YH_MODS＋財報日
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


def chart(s: dict | None, show_days: int = SHOW_DAYS) -> dict | None:
    """Yahoo 日線（ussxdata.parse_chart）→ 最後一天往前 show_days 個日曆天：{"pts": {日期: [收盤, 50 日線]}, "spl": 近一年的分割}。
    50 日線不到 50 個交易日＝None。沒有日線＝None。"""
    from . import ussxdata as UD
    ds, cs = (s or {}).get("d") or [], (s or {}).get("c") or []
    if not ds:
        return None
    n = X.QM_EXIT["ma"]
    tr = UD.total_return_close(s)
    first = (date.fromisoformat(ds[-1]) - timedelta(days=show_days)).isoformat()
    pts = {}
    for k, d in enumerate(ds):
        if d <= first:
            continue
        m = None
        if k >= n - 1 and tr[k] > 0:
            m = round(sum(tr[k - n + 1:k + 1]) / n * cs[k] / tr[k], 2)
        pts[d] = [round(cs[k], 2), m]
    return {"pts": pts, "spl": [list(x) for x in s.get("spl") or [] if x[0] > first]}


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
    return "ok", (rec or None)


def _yahoo():
    from . import fcst
    Y = fcst._Yahoo()
    return Y if Y.login() else None


# ── 存讀 ─────────────────────────────────────────────────────────────────────

def load(path: Path | None = None) -> dict:
    """存檔；版本不同＝沒有。"""
    try:
        doc = json.loads((path or CARD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if doc.get("ver") == VER else {}


def save(doc: dict, path: Path | None = None) -> bool:
    from . import ussxqm as QM
    return QM.save(doc, path or CARD)


def points(doc: dict, c: str) -> dict:
    """存檔裡一檔的日線 → {日期: [收盤, 50 日線]}（沒有資料的日子不列）。"""
    rec = (doc.get("s") or {}).get(c) or {}
    cal = doc.get("cal") or []
    cs, ms = rec.get("c") or [], rec.get("m") or []
    return {d: [cs[i], ms[i] if i < len(ms) else None] for i, d in enumerate(cal) if i < len(cs) and cs[i] is not None}


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
        S[c] = {"pts": points(old, c), "spl": r0.get("spl") or [], "at": r0.get("at"), "an_at": r0.get("an_at")}
        if "an" in r0:
            S[c]["an"] = r0["an"]
    need_c = [c for c in codes if force or not S[c]["at"] or S[c]["at"] < want]
    need_a = [c for c in codes if force or S[c]["an_at"] != want]
    stat = {"want": want, "codes": len(codes), "chart": 0, "an": 0, "skip_n": 0, "err": []}
    if not need_c and not need_a and sorted(old.get("s") or {}) == sorted(codes):
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
            o["c"] = [(r["pts"].get(d) or [None, None])[0] for d in cal]
            o["m"] = [(r["pts"].get(d) or [None, None])[1] for d in cal]
        for k in ("at", "an_at", "err", "aerr"):
            if r.get(k):
                o[k] = r[k]
        if r.get("spl"):
            o["spl"] = r["spl"]
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
