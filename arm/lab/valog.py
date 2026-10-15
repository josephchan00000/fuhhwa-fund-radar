"""籌碼雷達後台自我驗證紀錄（版面 v4，2026-10-15；docs/lab_ia_v4_plan.md 第 5 節）。

每次重建頁面都算一次今天的紀錄與事件（後台頁顯示）；只有 CI（GITHUB_ACTIONS）才寫回 data/lab/val_log.json，
容器本機重建只讀不寫（本機檔不混進 commit）。檔案以資料日為鍵、一天一行，同一天後面的班次覆蓋；保留 KEEP 天。

每條策略記：評級、推薦順序、前瞻（規則起算後已出場）筆數、平均報酬、同期大盤、平均贏同一批股票多少、
持有中檔數與平均報酬、待買進檔數。

事件（事前寫定；改規則＝改這裡＋改文件）：
  grade  評級變動：和前一個資料日的評級不同。
  full   前瞻滿額：已出場筆數第一次達到 A 級門檻（逐筆 10、事件型 2）。
  lag    前瞻落後：已出場 ≥ 門檻一半，且平均沒贏同一批股票（狀態第一次出現時記）。
  deep   持有中虧損超過歷史最差：逐檔計的策略看每一檔、其餘看同一批的平均，跌得比過去最差的一次還多（第一次出現時記）。
  miss   該出名單沒出：月營收、財報驚喜的形成日已過一個交易日以上，那一期沒有產生名單（第一次出現時記）。
  stale  資料過期：最新資料日之後已有 2 個以上交易日收盤卻沒有資料（每天都記，直到恢復）。
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import date, datetime, timedelta

from . import store

FP = "val_log.json"
KEEP = 250                 # 保留最近幾個資料日
STALE_TD = 2               # 落後幾個交易日算過期
CLOSE_HM = (14, 30)        # 這個時間之後，今天算已收盤
EVENT = {"s3"}             # 事件型（以「次」計、A 級門檻 2 次）；財報驚喜另由 src＝p3 判斷
TYPES = {"grade": "評級變動", "full": "前瞻滿額", "lag": "前瞻落後", "deep": "虧損超過歷史最差",
         "miss": "該出名單沒出", "stale": "資料過期"}


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "—")


def _wd(d: str) -> str:
    return "一二三四五六日"[date.fromisoformat(d).weekday()]


def _pct(x, d: int = 1) -> str:
    if x is None:
        return "—"
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.{d}f}%"


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else None


def _event(k: str, live: dict) -> bool:
    return k in EVENT or (live.get(k) or {}).get("src") == "p3"


# ── 今天的紀錄 ──────────────────────────────────────────────────────────

def snapshot(adv: dict) -> dict:
    """→ {鍵: 當天狀態}。只看有評級的策略（含 C 級，評級變動也要記）；高股息換股不是選股策略，不記。"""
    live = (adv.get("v3") or {}).get("live") or {}
    old = {g["k"]: g for g in adv.get("grades") or []}
    cards = {c["k"]: c for c in (adv.get("opp") or {}).get("cards") or []}
    bk = {b["k"]: b for b in adv.get("book") or []}
    last = adv.get("last")
    out = {}
    for g in adv.get("grades3") or []:
        k = g["k"]
        if k == "hd":
            continue
        ev = _event(k, live)
        f = g.get("fwd") or {}
        L = live.get(k)
        if L:
            us = (L.get("fwd") or {}).get("units") or []
            fr, fmk = _mean([u.get("r") for u in us]), _mean([u.get("mk") for u in us])
        else:
            of = (old.get(k) or {}).get("fwd") or {}
            fr = of.get("avg")
            fmk = None if of.get("avg") is None or of.get("x") is None else round(of["avg"] - of["x"], 2)
        c = cards.get(k) or {}
        held = [i for e in c.get("held") or [] for i in e.get("items") or []]
        lo = ((bk.get(k) or {}).get("exp") or {}).get("lo")
        unit = (bk.get(k) or {}).get("unit") or "次"
        deep = []
        if lo is not None:
            if unit == "檔":
                deep = [[i["n"], i["now_r"]] for i in held if i.get("now_r") is not None and i["now_r"] < lo]
            else:
                for e in c.get("held") or []:
                    a = _mean([i.get("now_r") for i in e.get("items") or []])
                    if a is not None and a < lo:
                        deep.append([f"{_md(e.get('ent'))} 買進的 {len(e['items'])} 檔平均", a])
        due = (L or {}).get("due") or {}
        out[k] = {"name": g.get("name") or (bk.get(k) or {}).get("name") or k, "g": g.get("grade"), "r": g.get("rank"),
                  "u": unit, "fn": f.get("n") or 0, "need": 2 if ev else 10, "fxe": f.get("xe"), "fr": fr, "fmk": fmk,
                  "hn": len(held), "hr": _mean([i.get("now_r") for i in held]),
                  "bn": sum(len(e.get("items") or []) for e in c.get("buy") or []), "lo": lo, "deep": deep,
                  "miss": due["d"] if due.get("d") and not due.get("ok") and due["d"] < (last or "") else None,
                  "why": (g.get("why") or [None])[0], "since": g.get("since")}
    return out


def lag_days(last: str | None, now: datetime) -> int | None:
    """最新資料日之後、到最新收盤日（今天 14:30 後算今天）為止，有幾個交易日。"""
    if not last:
        return None
    from .. import twholidays
    years = twholidays.load()
    end = now.date() if (now.hour, now.minute) >= CLOSE_HM else now.date() - timedelta(days=1)
    d, n = date.fromisoformat(last), 0
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and not twholidays.is_closed(d, years):
            n += 1
    return n


def todo(adv: dict) -> dict:
    """下一個交易日要做的事（行事曆上那一天的買賣）：06:35 推播用。"""
    d = adv.get("nxt")
    its = []
    for e in adv.get("cal") or []:
        if e.get("d") != d:
            continue
        nm = [i.get("n") for i in e.get("items") or [] if i.get("n")]
        its.append({"at": e.get("at"), "act": e.get("act"), "k": e.get("k"), "s": e.get("sname"), "n": nm,
                    "fix": e.get("fix") if e.get("pending") else None, "tent": bool(e.get("tent"))})
    return {"d": d, "items": its}


def events(cur: dict, prev: dict | None, last: str | None, lag: int | None) -> list[dict]:
    """事件規則見檔頭。prev＝前一個資料日的 st（沒有就當空的：當天的狀態都算新出現；評級變動要有前一天才記）。"""
    P = prev or {}
    out = []
    for k, s in cur.items():
        p = P.get(k) or {}
        nm, u = s["name"], s["u"]
        if p.get("g") and s.get("g") and p["g"] != s["g"]:
            out.append({"k": k, "ty": "grade", "txt": f"{nm}：評級 {p['g']} → {s['g']}" + (f"（{s['why']}）" if s.get("why") else "")})
        if s["fn"] >= s["need"] > (p.get("fn") or 0):
            vs = "" if s.get("fxe") is None else f"，比同一批股票{'高' if s['fxe'] >= 0 else '低'} {abs(s['fxe']):.2f}%"
            out.append({"k": k, "ty": "full", "txt": f"{nm}：規則起算後已出場 {s['fn']} {u}，達到 A 級門檻；"
                        f"平均每{u}報酬 {_pct(s['fr'])}（同期大盤 {_pct(s['fmk'])}）{vs}"})
        lag_now = s["fn"] * 2 >= s["need"] and s["fn"] > 0 and s.get("fxe") is not None and s["fxe"] < 0
        lag_pre = (p.get("fn") or 0) * 2 >= p.get("need", s["need"]) and (p.get("fn") or 0) > 0 and \
            p.get("fxe") is not None and p["fxe"] < 0
        if lag_now and not lag_pre:
            out.append({"k": k, "ty": "lag", "txt": f"{nm}：規則起算後已出場 {s['fn']} {u}，平均比同一批股票低 {abs(s['fxe']):.2f}%"
                        f"（平均報酬 {_pct(s['fr'])}、同期大盤 {_pct(s['fmk'])}）"})
        seen = {x[0] for x in p.get("deep") or []}
        new = [x for x in s.get("deep") or [] if x[0] not in seen]
        if new:
            out.append({"k": k, "ty": "deep", "txt": f"{nm}：持有中 " + "、".join(f"{x[0]} {_pct(x[1])}" for x in new) +
                        f"，跌得比過去最差的一{u}（{_pct(s['lo'])}）還多"})
        if s.get("miss") and s["miss"] != p.get("miss"):
            out.append({"k": k, "ty": "miss", "txt": f"{nm}：{_md(s['miss'])} 應產生名單，到 {_md(last)} 仍沒有（營收或財報資料可能沒進來）"})
    if lag is not None and lag >= STALE_TD:
        out.append({"k": None, "ty": "stale", "txt": f"資料過期：最新資料 {_md(last)}，之後已有 {lag} 個交易日收盤沒有資料"})
    return out


def push_lines(rec: dict) -> list[str]:
    """06:35 推播多帶的兩行：那一天開盤（與收盤）要做的事；有驗證事件才加第二行。"""
    T = rec.get("todo") or {}
    d, its = T.get("d"), T.get("items") or []
    if not d:
        a = "下一個交易日不確定（休市表讀不到）。"
    elif not its:
        a = f"{_md(d)}（{_wd(d)}）沒有排定的買賣。"
    else:
        parts = []
        for at in ("開盤", "收盤"):
            xs = [i for i in its if i.get("at") == at]
            if xs:
                parts.append(f"{at}" + "；".join(
                    f"{i['act']} {i['s']} " + ("、".join(i["n"][:5]) + (f" 等 {len(i['n'])} 檔" if len(i["n"]) > 5 else "")
                                               if i["n"] else f"（名單 {_md(i['fix'])} 收盤產生）") +
                    ("（試算名單）" if i.get("tent") else "") for i in xs))
        a = f"{_md(d)}（{_wd(d)}）" + "；".join(parts) + "。"
    out = [a]
    ev = rec.get("ev") or []
    if ev:
        out.append("策略驗證：" + "；".join(e["txt"] for e in ev) + "。")
    return out


# ── 讀寫 ────────────────────────────────────────────────────────────────

def read() -> dict:
    doc = store.read_json(FP, {}) or {}
    days = doc.get("days") if isinstance(doc, dict) else None
    return {"v": 1, "days": days if isinstance(days, dict) else {}}


def _dump(log: dict) -> str:
    """一天一行（決定性）：每天只改最後一行，git diff 小。"""
    days = log.get("days") or {}
    rows = [json.dumps(k) + ":" + json.dumps(days[k], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for k in sorted(days)]
    return '{"v":1,"days":{\n' + ",\n".join(rows) + "\n}}\n"


def write(log: dict) -> bool:
    p = store.LAB / FP
    txt = _dump(log)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True


def update(data: dict, write_file: bool | None = None, now: datetime | None = None) -> dict:
    """算今天的紀錄與事件；write_file（預設＝在 CI 裡）時寫回檔案。→ 頁面「後台」用的資料。"""
    from .. import clock
    adv = data.get("adv") or {}
    if adv.get("err") or not adv.get("last"):
        return {"err": adv.get("err") or "沒有評級資料"}
    if write_file is None:
        write_file = os.environ.get("GITHUB_ACTIONS") == "true"
    now = now or clock.now_tw()
    last = adv["last"]
    log = read()
    days = log["days"]
    prev_d = max((d for d in days if d < last), default=None)
    prev = (days.get(prev_d) or {}).get("st") if prev_d else None
    st = snapshot(adv)
    try:
        lag = lag_days(last, now)
    except Exception:                                     # noqa: BLE001 —— 休市表讀不到：不判過期
        lag = None
    rec = {"st": st, "lag": lag, "todo": todo(adv)}
    rec["ev"] = events(st, prev, last, lag)
    rec["push"] = push_lines(rec)
    old = days.get(last) or {}
    if {k: v for k, v in old.items() if k != "t"} != rec:   # 內容沒變就不動檔（時間戳也不改）
        days[last] = {**rec, "t": now.strftime("%Y-%m-%d %H:%M")}
    else:
        rec = old
    for d in sorted(days)[:-KEEP]:
        days.pop(d, None)
    if write_file:
        write(log)
    return view(days, last)


def view(days: dict, last: str) -> dict:
    """頁面「後台」：今天的紀錄、近 60 個資料日的事件、評級變動史、紀錄起點。"""
    ds = sorted(days)
    hist = [[d, days[d].get("ev")] for d in ds[-60:] if days[d].get("ev")]
    gh: dict[str, list] = {}
    pv: dict[str, str] = {}
    for d in ds:
        for k, s in (days[d].get("st") or {}).items():
            if s.get("g") and pv.get(k) != s["g"]:
                gh.setdefault(k, []).append([d, s["g"]])
                pv[k] = s["g"]
    return {"today": days.get(last) or {}, "d": last, "since": ds[0] if ds else None, "n": len(ds),
            "hist": list(reversed(hist)), "gh": gh}
