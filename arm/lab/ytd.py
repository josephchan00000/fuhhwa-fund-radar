"""今年逐月、逐筆表（ytdspec VER 1；docs/lab_review_plan.md 第 9.2 節）：配置頁「現在的錢」下面，台股、美股各一張。

  tw(D, plan, names)  台股：不偷看（0050 兩成＋新飆股四成＋現金四成）、一直抱著（0050 含息）、上線後（每天收盤的持股比例）
  us(qm_live)         美股：不偷看（固定那一種挑法；data/lab/ytd_us.json，每週六重算）、一直抱著（S&P 500 含息）、上線後（強勢品質股每週紀錄）
  record_tw(day, pos) 上線後：每天收盤的持股比例（只有 CI 寫回 data/lab/ytd_live.json）
  html(mk, Y)         配置頁的表
只呈現，不改任何規則。"""
from __future__ import annotations

import html as _h
import json
import os
from datetime import date

from . import store
from . import ytdspec as S

LIVE_FILE = "ytd_live.json"
MONTHS = list(range(1, 13))


def _e(x) -> str:
    return _h.escape(str(x), quote=True)


def load(name: str) -> dict | None:
    doc = store.read_json(name, None)
    if not isinstance(doc, dict) or doc.get("ver") != S.VER or doc.get("year") != S.YEAR:
        return None
    return doc


# ── 共同 ─────────────────────────────────────────────────────────────────────

def month_rows(days: list[str], cols: dict[str, list[float | None]]) -> list[dict]:
    """days[0]＝去年最後一個交易日（＝起點）；cols＝{欄: 每天的淨值（起點＝1，沒有＝None）}。
    → 每個月一列：{"m", "to"（這個月最後一天；沒走完＝最新那天）, "full", 欄: [那個月的報酬, 今年累計]}。"""
    out = []
    last = days[-1]
    for m in MONTHS:
        ks = [k for k, d in enumerate(days) if k > 0 and int(d[5:7]) == m and d[:4] == str(S.YEAR)]
        if not ks:
            continue
        k1 = ks[-1]
        k_prev = ks[0] - 1
        row = {"m": m, "to": days[k1], "full": not (days[k1] == last and not _month_done(last))}
        for c, v in cols.items():
            a, b, z = v[k_prev], v[k1], v[0]
            if b is None:
                row[c] = None
                continue
            mr = (b / a - 1) if a not in (None, 0) else None
            row[c] = [mr, (b / z - 1) if z else None]
        out.append(row)
    return out


def _month_done(d: str) -> bool:
    """d 是不是那個月最後一個平日以後（月底已過）——只用來標「這個月還沒走完」。"""
    x = date.fromisoformat(d)
    nxt = date(x.year + (x.month == 12), x.month % 12 + 1, 1)
    from datetime import timedelta
    k = nxt - timedelta(days=1)
    while k.weekday() >= 5:
        k -= timedelta(days=1)
    return x >= k


def live_col(days: list[str], live: dict[str, float]) -> list[float | None]:
    """上線後那一欄：起點以前＝None；起點＝1。live＝{日期: 淨值（起點＝1）}。"""
    out, cur = [], None
    for d in days:
        if d in live:
            cur = live[d]
        out.append(cur)
    return out


# ── 台股 ─────────────────────────────────────────────────────────────────────

def _adj_closes(D, codes: list[str], days: list[str]) -> dict[str, list[float | None]]:
    """官方收盤 × 除權息還原倍數（含息）；那天沒有收盤＝往前找。"""
    from . import bt3d
    ev = bt3d.events()
    cal = list(D.cal)
    ix = {d: i for i, d in enumerate(cal)}
    out = {}
    for c in codes:
        F = bt3d.factor_events(cal, sorted((d, f) for d, f, _ in ev.get(c) or []))
        vals = []
        for d in days:
            i = ix.get(d)
            v = None
            j = i
            while j is not None and j >= 0 and v is None:
                q = D.quote(c, cal[j])
                if q and q[3]:
                    v = q[3] * F[j]
                j -= 1
                if i is not None and j is not None and i - j > 10:
                    break
            vals.append(v)
        out[c] = vals
    return out


def tw(D, plan: dict | None, names: dict | None = None, live: dict | None = None) -> dict | None:
    """→ {"days", "rows"（每月）, "trades", "last", "w": TW_W, ...}；靜態檔或接手後的帳缺了＝None。"""
    st = load(S.FILE_TW)
    yp = (plan or {}).get("ytd")
    if not st or not yp or D is None:
        return None
    d0, e0 = st["d0"], float(st["e_d0"])
    eq = {d: float(v) for d, v in st["eq"].items()}
    eq.update({d: float(v) for d, v in (yp.get("eq") or {}).items() if d > st["take"]})
    days = sorted(d for d in eq if d >= d0)
    px = _adj_closes(D, ["0050"], days)["0050"]
    while days and px[-1] is None:                       # 0050 還沒有這天的收盤：表停在前一天
        days.pop()
        px.pop()
    if not days or px[0] is None:
        return None
    p0 = px[0]
    w = S.TW_W
    nolook = [w["0050"] * p / p0 + w["R60"] * eq[d] / e0 + w["cash"] if p is not None else None for d, p in zip(days, px)]
    hold = [p / p0 if p is not None else None for p in px]
    live = live or load_live()
    lv = live_tw(D, live, days)
    lfrom = min((d for d in (live.get("tw") or {}) if d >= S.TW_LIVE_FROM), default=S.TW_LIVE_FROM)
    rows = month_rows(days, {S.NOLOOK: nolook, S.HOLD: hold, S.LIVE: live_col(days, lv)})
    nm = names or {}

    def eq_before(d: str) -> float:
        ks = [x for x in days if x < d]
        return eq[ks[-1]] if ks else e0
    trades = [{"k": "0050", "c": "0050", "n": nm.get("0050", "元大台灣50"), "ent": d0, "exit": None, "ret": hold[-1] - 1,
               "w": w["0050"], "pnl": w["0050"] * (hold[-1] - 1), "carry": True}]
    for t in st["closed"]:
        trades.append({"k": "R60", "c": t["c"], "n": nm.get(t["c"], t["c"]), "ent": t["ent"], "exit": t["exit"], "ret": t["ret"],
                       "bpx": t.get("bpx"), "spx": t.get("spx"), "w": _m(t.get("w"), w["R60"]), "pnl": _m(t.get("pnl"), w["R60"]),
                       "carry": t["carry"]})
    tk = {p["c"]: p for p in st["open_take"]}
    hold_px = {h["c"]: h for h in (plan or {}).get("hold") or []}
    for c, ent, ex, r, why, pnl, sh, since in yp.get("closed") or []:
        p = tk.get(c)
        if p and since is not None:
            pnl26, ww, carry = since + p["vt"] - p["base"], p.get("w"), p["carry"]
        else:
            cin = pnl / r if r else None
            pnl26, ww, carry = pnl, (cin / eq_before(ent) if cin else None), False
        trades.append({"k": "R60", "c": c, "n": nm.get(c, c), "ent": ent, "exit": ex, "ret": r, "w": _m(ww, w["R60"]),
                       "pnl": _m(pnl26 / e0, w["R60"]), "carry": carry, "bpx": (p or {}).get("bpx")})
    for c, ent, cin, v0, val, sh in yp.get("open") or []:
        p = tk.get(c)
        if p:
            base, ww, carry = p["base"], p.get("w"), p["carry"]
        else:
            base, ww, carry = cin, cin / eq_before(ent), False
        hp = hold_px.get(c) or {}
        trades.append({"k": "R60", "c": c, "n": nm.get(c, c), "ent": ent, "exit": None, "ret": val / cin - 1 if cin else None,
                       "w": _m(ww, w["R60"]), "pnl": _m((val - base) / e0, w["R60"]), "carry": carry,
                       "bpx": hp.get("epx") if hp else (p or {}).get("bpx"), "spx": hp.get("px")})
    trades.sort(key=lambda t: (t["ent"], t["c"]))
    return {"mk": "tw", "days": [days[0], days[-1]], "rows": rows, "trades": trades, "w": w, "take": st["take"],
            "live_from": lfrom, "tot": {S.NOLOOK: nolook[-1] - 1, S.HOLD: hold[-1] - 1,
                                                 S.LIVE: (lv[days[-1]] - 1) if days[-1] in lv else None}}


def _m(x, k):
    return None if x is None else x * k


def load_live() -> dict:
    doc = store.read_json(LIVE_FILE, {}) or {}
    return doc if isinstance(doc, dict) and doc.get("ver") == S.VER else {"ver": S.VER, "tw": {}}


def weights_of(pos: dict | None, core: float) -> dict[str, float]:
    """配置頁台股的持股（cfgpage.pos_map：{代號: [{w, h…}]}，只算持有中 h＝1）＋長抱的 0050 → {代號: 占全部資金}。"""
    w: dict[str, float] = {}
    for c, xs in (pos or {}).items():
        v = round(float(sum(x["w"] for x in xs if x.get("h"))), 6)
        if v > 0:
            w[c] = v
    if core > 0:
        w["0050"] = round(w.get("0050", 0.0) + core, 6)
    return w


def record_tw(day: str | None, pos: dict | None, core: float, path=None, force: bool = False) -> bool:
    """上線後：day 收盤的持股比例（{代號: 占全部資金}；其餘＝現金）。只有 CI 寫回（force＝補第一筆用）；同一天覆蓋；
    TW_LIVE_FROM 以前不記。"""
    if (os.environ.get("GITHUB_ACTIONS") != "true" and not force) or not day or day < S.TW_LIVE_FROM or not pos:
        return False
    L = load_live()
    w = weights_of(pos, core)
    if L["tw"].get(day) == w:
        return False
    L["tw"][day] = w
    p = path or (store.LAB / LIVE_FILE)
    rows = ",\n".join(json.dumps(d, ensure_ascii=False) + ":" + json.dumps(v, ensure_ascii=False, sort_keys=True)
                      for d, v in sorted(L["tw"].items()))
    p.write_text('{"ver":' + str(S.VER) + ',"tw":{\n' + rows + "\n}}\n", encoding="utf-8")
    return True


def live_tw(D, live: dict | None, days: list[str]) -> dict[str, float]:
    """紀錄的持股比例 × 之後每天的漲跌（含息、不含成本）＝上線後每天的淨值（TW_LIVE_FROM 以後第一筆紀錄那天＝1）。"""
    rec = (live or load_live()).get("tw") or {}
    first = min((d for d in rec if d >= S.TW_LIVE_FROM), default=None)   # 第一筆紀錄那天收盤＝1
    ds = [d for d in days if first and d >= first]
    if not ds or ds[0] != first:
        return {}
    codes = sorted({c for v in rec.values() for c in v})
    px = _adj_closes(D, codes, ds)
    out, v, cur = {ds[0]: 1.0}, 1.0, rec[ds[0]]
    for k in range(1, len(ds)):
        r = 0.0
        for c, w in cur.items():
            a, b = px[c][k - 1], px[c][k]
            if a and b:
                r += w * (b / a - 1)
        v *= 1 + r
        out[ds[k]] = v
        cur = rec.get(ds[k], cur)
    return out


# ── 美股 ─────────────────────────────────────────────────────────────────────

def us(qm_live: dict | None) -> dict | None:
    doc = load(S.FILE_US)
    if not doc:
        return None
    yp = doc["year_part"]
    days, nav, hold = yp["days"], yp["nav"], yp["hold"]
    cv = (qm_live or {}).get("curve") or {}
    lv = {d: x for d, x in zip(cv.get("d") or [], cv.get("nav") or []) if x is not None}
    rows = month_rows(days, {S.NOLOOK: nav, S.HOLD: hold, S.LIVE: live_col(days, lv)})
    wf = doc["wf"][doc["chosen"]]
    nms = {**(doc.get("names") or {}), **((qm_live or {}).get("names") or {})}
    trades = [{"k": t["m"].split("｜")[0], "m": t["m"], "c": t["c"], "nm": nms.get(t["c"]), "ent": t["ei"], "exit": t.get("xi"),
               "bpx": t.get("bpx"), "spx": t.get("spx"), "ret": t.get("ret"), "w": t.get("w"), "pnl": t.get("pnl"),
               "carry": t.get("carry"), "why": t.get("why")} for t in yp["trades"]]
    return {"mk": "us", "days": [days[0], days[-1]], "rows": rows, "trades": trades, "chosen": doc["chosen"],
            "rank": [r[0] for r in doc["rank"]].index(doc["chosen"]) + 1, "n_wf": len(doc["rank"]), "picks": yp["picks"],
            "k": wf["k"], "L": wf["L"], "pool": wf["pool"], "cagr": wf["cagr"], "range": yp["range"],
            "live_from": S.US_LIVE_FROM, "data_last": doc["data_last"],
            "tot": {S.NOLOOK: nav[-1] - 1, S.HOLD: hold[-1] - 1,
                    S.LIVE: (lv[max(lv)] - 1) if lv else None}}
