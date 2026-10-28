"""選股頁的進場行事曆（docs/lab_pick_page_plan.md 第 2.2 節）：每個市場一份事件清單。

使用者 2026-10-28：「把現有的選股策略做好妥善的規劃呈現出來單獨一頁，我要分成台股跟美股，有不同策略建議進場的時程行事曆」。
- 事件＝(日期, 開盤／收盤, 策略, 動作, 股票)；動作：名單（收盤產生）、買進、賣出、換股、調整；美股另有持股的財報日（不是買賣）。
- 已經知道的（現在的持股、已出的名單、已排定的賣出）用真的股票；之後的名單日與買進日照每條策略的規則往後推到 horizon（第三個月底），
  寫「新名單」（proj＝True）。休市照證交所／NYSE 官方表（xstrat.future_days）。
- 只整理既有的資料（advice 的行事曆與本期名單、新飆股那本帳、美股強勢品質股的每週紀錄與每天檢查），不重算任何回測、不改任何規則。
"""
from __future__ import annotations

from datetime import date, timedelta

# 台股策略：主要的（新飆股＋判定好的）照這個順序；其他（判定普通）收起、行事曆預設不顯示。
TW_ORDER = ("boom", "s3", "v3l", "s5", "s1", "v7l", "v3m", "v7m")
SHORT = {"boom": "新飆股", "s3": "臺灣50 卡位", "v3l": "財報驚喜", "s5": "長線", "s1": "共識加碼",
         "v7l": "營收大型", "v3m": "財報中型", "v7m": "營收中型", "qm": "強勢品質股", "ern": "財報"}
ACTS = ("名單", "買進", "賣出", "換股", "調整", "財報")
V3_HOLD = 60                       # 財報驚喜：持有 60 個交易日（含買進那天；advice V3_RULES）


def horizon(today: str, months: int = 3) -> str:
    """today 那個月之後第 months 個月的最後一天（例：10/28 → 隔年 1/31）。"""
    d = date.fromisoformat(today)
    y, m = d.year, d.month + months + 1
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return (date(y, m, 1) - timedelta(days=1)).isoformat()


def _closed(mk: str, d: date) -> bool:
    from .xstrat import _closed as C
    return C(mk, d)


def next_days(mk: str, d: str, n: int = 1) -> list[str]:
    from .xstrat import future_days
    return future_days(mk, d, n)


def next_day(mk: str, d: str) -> str:
    return next_days(mk, d, 1)[0]


def nth_day(mk: str, d: str, n: int) -> str:
    """d 之後第 n 個交易日（n ≥ 1）。"""
    return next_days(mk, d, n)[-1]


def on_or_after(mk: str, d: str) -> str:
    x = date.fromisoformat(d)
    return d if not _closed(mk, x) else next_day(mk, d)


def week_ends(mk: str, a: str, b: str) -> list[str]:
    """(a, b] 之間每週的最後一個交易日（那一週的交易日都還在 b 之前或當天）。"""
    out, x = [], date.fromisoformat(a) + timedelta(days=1)
    end = date.fromisoformat(b)
    while x <= end:
        w0 = x - timedelta(days=x.weekday())
        days = [w0 + timedelta(k) for k in range(5) if not _closed(mk, w0 + timedelta(k))]
        if days and x <= days[-1] <= end and days[-1].isoformat() not in out:
            out.append(days[-1].isoformat())
        x = w0 + timedelta(days=7)
    return out


def month_ends(mk: str, a: str, b: str) -> list[str]:
    """(a, b] 之間每個月的最後一個交易日。"""
    out, x = [], date.fromisoformat(a)
    end = date.fromisoformat(b)
    y, m = x.year, x.month
    while True:
        last = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        if last.replace(day=1) > end:
            break
        d = last
        while _closed(mk, d):
            d -= timedelta(days=1)
        if x < d <= end:
            out.append(d.isoformat())
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def ev(d: str, at: str, k: str, act: str, items=None, note: str = "", proj: bool = False, **kw) -> dict:
    e = {"d": d, "at": at, "k": k, "act": act, "items": [{"c": i.get("c"), "n": i.get("n") or i.get("c")} for i in (items or [])],
         "note": note, "proj": bool(proj)}
    e.update({x: y for x, y in kw.items() if y is not None})
    return e


def _sort(evs: list[dict], order: tuple) -> list[dict]:
    at = {"開盤": 0, "": 1, "收盤": 2}
    act = {a: i for i, a in enumerate(ACTS)}
    ko = {k: i for i, k in enumerate(order)}
    return sorted(evs, key=lambda e: (e["d"], at.get(e["at"], 1), ko.get(e["k"], 99), act.get(e["act"], 9)))


def _dedupe(evs: list[dict]) -> list[dict]:
    """同一天、同一時點、同一策略、同一動作只留一筆（有股票的優先）；同一天已經有換股（名單同時產生）就不另列名單。"""
    best: dict[tuple, dict] = {}
    for e in evs:
        key = (e["d"], e["at"], e["k"], e["act"])
        if key not in best or (not best[key]["items"] and e["items"]):
            best[key] = e
    swap = {(e["d"], e["k"]) for e in best.values() if e["act"] == "換股"}
    return [e for e in best.values() if not (e["act"] == "名單" and (e["d"], e["k"]) in swap)]


# ── 台股 ───────────────────────────────────────────────────────────────────

def boom_events(P: dict | None, end: str) -> list[dict]:
    """新飆股（sxlive.plan_state）：持股的賣出日（到期隔天開盤；明天要賣的＝明天）、明天開盤要買的、之後每週的名單日與買進日。"""
    P = P or {}
    last, nx = P.get("d"), P.get("next")
    if not last:
        return []
    out = []
    by: dict[str, list] = {}
    for h in P.get("hold") or []:
        if h.get("out"):
            by.setdefault(h["out"], []).append(h)
    for d, hs in by.items():
        out.append(ev(d, "開盤", "boom", "賣出", hs, note=f"{_mdl(sorted({h['ent'] for h in hs if h.get('ent')}))} 買的，抱滿 60 個交易日"))
    buys = [x for x in P.get("buy") or [] if x.get("fill")]
    if buys and nx:
        out.append(ev(nx, "開盤", "boom", "買進", buys, note=f"{_md(P.get('wk') or last)} 那週的名單"))
    for w in week_ends("tw", last, end):
        b = next_day("tw", w)
        out.append(ev(w, "收盤", "boom", "名單", note="這一週的名單（依強度排）", proj=True))
        if not (buys and b == nx):
            out.append(ev(b, "開盤", "boom", "買進", note="新名單，有空位才買", proj=True))
    return out


def adv_events(A: dict, keys: set) -> list[dict]:
    """advice 的行事曆（★、● 個股策略已知的買賣）→ 事件；名單還沒產生的買進另加名單日。"""
    out = []
    for e in A.get("cal") or []:
        k = e.get("k")
        if k not in keys or not e.get("d"):
            continue
        its = e.get("items") or []
        act = e.get("act") or ""
        if act == "買進" and e.get("pending"):
            if e.get("fix"):
                out.append(ev(e["fix"], "收盤", k, "名單", note=e.get("note") or "", proj=True))
            out.append(ev(e["d"], e.get("at") or "開盤", k, "買進", note="新名單", proj=True, out=e.get("out")))
            continue
        note = e.get("note") or ""
        if act == "買進" and e.get("tent"):
            note = f"名單 {_md(e.get('fix'))} 收盤定案，可能變動"
        out.append(ev(e["d"], e.get("at") or "開盤", k, act, its, note=note, out=e.get("out")))
    return out


def v3_events(k: str, live: dict, last: str, end: str, have: list[dict]) -> list[dict]:
    """財報驚喜：下一次（advice 已列）之後每季的名單日（法定期限當天或之後第一個交易日）與隔天買進，以及買進後第 60 個交易日收盤賣出。"""
    from .v3live import next_eps_form
    L = live.get(k) or {}
    nx = L.get("next") or {}
    out = []
    q = nx.get("q")
    forms = []
    if nx.get("d"):
        forms.append(nx["d"])
    while q:
        q, f = next_eps_form(q)
        if f > end:
            break
        forms.append(f)
    known = {(e["d"], e["act"]) for e in have if e["k"] == k}
    for f in forms:
        if f <= last:
            continue
        b = next_day("tw", f)
        if (f, "名單") not in known:
            out.append(ev(f, "收盤", k, "名單", note="季報公布期限", proj=True))
        if (b, "買進") not in known:
            out.append(ev(b, "開盤", k, "買進", note="新名單", proj=True))
        s = nth_day("tw", b, V3_HOLD - 1)
        if s <= end:
            out.append(ev(s, "收盤", k, "賣出", note=f"{_md(b)} 買的，抱滿 60 個交易日", proj=True))
    return out


def v7_events(k: str, live: dict, last: str, end: str, have: list[dict]) -> list[dict]:
    """月營收驚喜：每月 10 日（遇假日順延）收盤換股（名單同時產生），隔天開盤買新名單。"""
    from .v3live import next_rev_form
    L = live.get(k) or {}
    f = (L.get("next") or {}).get("d")
    out = []
    known = {(e["d"], e["act"]) for e in have if e["k"] == k}
    while f and f <= end:
        if f > last:
            b = next_day("tw", f)
            if (f, "換股") not in known and (f, "名單") not in known:
                out.append(ev(f, "收盤", k, "換股", note="不在新名單的賣出，仍在新名單的續抱", proj=True))
            if (b, "買進") not in known:
                out.append(ev(b, "開盤", k, "買進", note="新名單", proj=True))
        f = next_rev_form(f)
    return out


def s5_events(last: str, end: str, have: list[dict]) -> list[dict]:
    """長線：每月最後一個交易日收盤篩選，隔天開盤買（四項條件都符合的才買）。"""
    known = {(e["d"], e["act"]) for e in have if e["k"] == "s5"}
    out = []
    for m in month_ends("tw", last, end):
        b = next_day("tw", m)
        out.append(ev(m, "收盤", "s5", "名單", note="四項條件篩選", proj=True))
        if (b, "買進") not in known:
            out.append(ev(b, "開盤", "s5", "買進", note="符合四項條件的才買", proj=True))
    return out


def s3_events(plan: dict | None, last: str, end: str, have: list[dict]) -> list[dict]:
    """臺灣50 提前卡位：選股日（已列在 advice 的就不重複）、資料截止日（收盤定案調整名單）、公告日；買進、調整、賣出由 advice 行事曆列。"""
    p = plan or {}
    out = []
    known = {(e["d"], e["act"]) for e in have if e["k"] == "s3"}
    if p.get("e_sig") and last < p["e_sig"] <= end and (p["e_sig"], "名單") not in known:
        out.append(ev(p["e_sig"], "收盤", "s3", "名單", note="以當天排名選漲勢最強 4 檔", proj=True))
    if p.get("cutoff") and last < p["cutoff"] <= end:
        out.append(ev(p["cutoff"], "收盤", "s3", "名單", note="資料截止日：照這天的排名調整", proj=True))
    if p.get("announce") and last < p["announce"] <= end:
        out.append(ev(p["announce"], "收盤", "s3", "名單", note="指數公司公告名單；沒被納入的隔天開盤賣", proj=True))
    return out


def tw_events(A: dict, P: dict | None, s3plan: dict | None, keys: list[str], today: str | None = None) -> dict:
    """台股事件：keys＝要放的策略（主要＋其他）。→ {d: 資料日, end, ev: [...]}。"""
    last = A.get("last") or (P or {}).get("d") or today
    end = horizon(today or last)
    ks = set(keys)
    base = adv_events(A, ks - {"boom"})
    evs = list(base)
    if "boom" in ks:
        evs += boom_events(P, end)
    live = ((A.get("v3") or {}).get("live")) or {}
    for k in ("v3l", "v3m"):
        if k in ks:
            evs += v3_events(k, live, last, end, base)
    for k in ("v7l", "v7m"):
        if k in ks:
            evs += v7_events(k, live, last, end, base)
    if "s5" in ks:
        evs += s5_events(last, end, base)
    if "s3" in ks:
        evs += s3_events(s3plan, last, end, base)
    evs = [e for e in _dedupe(evs) if last < e["d"] <= end]
    return {"d": last, "end": end, "ev": _sort(evs, TW_ORDER)}


# ── 美股 ───────────────────────────────────────────────────────────────────

def us_events(G: dict, card: dict | None, today: str | None = None) -> dict:
    """美股強勢品質股（cfgpage.us_state 的 G）：排定的賣出（跌破 50 日線的隔天開盤）、要買的、之後每週五的名單日與下週一買進；
    持股與待買進的財報日（Yahoo；不是買賣）。日期是美國當地的交易日。"""
    last = G.get("d")
    if not last:
        return {"d": None, "end": None, "ev": []}
    end = horizon(today or last)
    nm = G.get("nms") or {}
    item = lambda c: {"c": c, "n": _usn(c, nm)}             # noqa: E731
    evs = []
    sells: dict[str, list] = {}
    for r in G.get("rows") or []:
        if r.get("sell") and r["sell"] > last:
            sells.setdefault(r["sell"], []).append(item(r["c"]))
    for d, its in sells.items():
        evs.append(ev(d, "開盤", "qm", "賣出", its, note="收盤跌破 50 日線"))
    buys: dict[str, list] = {}
    for t in G.get("todo") or []:
        if t.get("d") and t["d"] > last and (t.get("w") or 0) > 1e-3:
            buys.setdefault(t["d"], []).append(item(t["c"]))
    for d, its in buys.items():
        evs.append(ev(d, "開盤", "qm", "買進", its, note="這一週的名單，補空位"))
    for w in week_ends("spx", last, end):
        b = next_day("spx", w)
        evs.append(ev(w, "收盤", "qm", "名單", note="這一週的名單（強勢、賺錢的中大型股）", proj=True))
        if b not in buys:
            evs.append(ev(b, "開盤", "qm", "買進", note="新名單，有空位才買", proj=True))
    held = [r["c"] for r in G.get("rows") or [] if not (r.get("sell") and r["sell"] <= last)] + [t["c"] for t in G.get("todo") or []]
    S = (card or {}).get("s") or {}
    ern: dict[str, list] = {}
    for c in held:
        an = (S.get(c) or {}).get("an") or {}
        for d in an.get("ed") or []:
            if last < d <= end:
                ern.setdefault(d, []).append((c, bool(an.get("ede"))))
                break
    for d, xs in ern.items():
        evs.append(ev(d, "", "ern", "財報", [item(c) for c, _ in xs],
                      note="財報公布日" + ("（Yahoo 估的日期）" if any(e for _, e in xs) else "")))
    evs = [e for e in _dedupe(evs) if last < e["d"] <= end]
    return {"d": last, "end": end, "ev": _sort(evs, ("qm", "ern"))}


def _usn(c: str, nms: dict) -> str:
    try:
        from . import corepage as CPG
        return CPG.us_label(c, nms)[0]
    except Exception:                                    # noqa: BLE001
        return c


def _md(d: str | None) -> str:
    d = str(d or "")
    return f"{int(d[5:7])}/{int(d[8:10])}" if len(d) >= 10 else "—"


def _mdl(ds: list[str]) -> str:
    return "、".join(_md(d) for d in ds) or "—"
