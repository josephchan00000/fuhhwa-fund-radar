"""回測 v3 策略的每日名單與前瞻紀錄（docs/backtest_v3_plan.md 第 13 節；使用者：每條策略只取最強前 5 檔）。

列入本期操作（前 5 檔版本達 B）：中型／大型月營收驚喜、大型財報驚喜；中型財報驚喜前 5 檔是 C，只列觀察。
評級與樣本內外成績讀 data/lab/bt3_research.json（長歷史研究；資料或規則改了才重跑 scripts/run_bt3.py）。
名單、進出場日、前瞻成績用每日資料（官方分片＋Yahoo）算——價格不含息，名單只用分數、市值、成交值，不受影響。
前瞻起算 SINCE：之後形成的每一期都記（同一套資金帳戶算法，對同一批股票等權）。
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

from . import bt3, bt3d, bt3s, store
from . import packtest as PT

SINCE = "2026-10-15"
N = 5
HOLD3 = 60
UMIN = {"p7": 10, "p3": 20}
LIVE = [  # 鍵、來源、範圍、名稱、單位
    ("v7m", "p7", "M", "月營收驚喜（中型股）", "月"), ("v3l", "p3", "L", "財報驚喜（大型股）", "季"),
    ("v7l", "p7", "L", "月營收驚喜（大型股）", "月"), ("v3m", "p3", "M", "財報驚喜（中型股）", "季")]


def _td_on_or_after(d: str) -> str:
    from .strategy import trading_days_after
    return trading_days_after((date.fromisoformat(d) - timedelta(days=1)).isoformat(), 1)[0]


def _td_after(d: str, n: int) -> str:
    from .strategy import trading_days_after
    return trading_days_after(d, n)[-1]


def next_rev_form(after: str) -> str:
    """下一個月營收形成日＝下個月 10 日當天或之後的第一個交易日（遇假日順延）。"""
    y, m = int(after[:4]), int(after[5:7]) + 1
    if m > 12:
        y, m = y + 1, 1
    return _td_on_or_after(f"{y:04d}-{m:02d}-10")


def next_eps_form(last_q: str) -> tuple[str, str]:
    """最新一季的下一季 → (季底, 形成日＝法定期限當天或之後的第一個交易日)。"""
    y, m = int(last_q[:4]), int(last_q[5:7])
    y, m = (y + 1, 3) if m == 12 else (y, m + 3)
    q = f"{y:04d}-{m:02d}-{ {3: 31, 6: 30, 9: 30, 12: 31}[m]:02d}"
    return q, _td_on_or_after(PT.deadline(q))


def _why(src: str, c: str, sc: float, ym: str | None, rev: dict, eps: dict, q: str | None) -> list[str]:
    if src == "p7":
        x = ((store.read("rev", ym) or {}).get("s") or {}).get(c) if ym else None
        out = [f"{int(ym[5:7])} 月營收年增 {x[1]:.0f}%" if x and x[1] is not None else None,
               f"比過去一年的變化幅度高出 {sc:.1f} 個標準差"]
    else:
        e = eps.get(c) or {}
        py = PT._prev_year(q) if q else None
        out = [f"{q[:4]} 年第 {int(q[5:7]) // 3} 季 EPS {e[q]:.2f} 元（去年同季 {e[py]:.2f} 元）" if q and q in e and py in e else None,
               f"比過去兩年的變化幅度高出 {sc:.1f} 個標準差"]
    return [x for x in out if x]


def run(DL, names: dict | None = None) -> dict:
    """→ {鍵: {名單、進出場日、前瞻成績、研究成績與評級}}；研究檔不存在時回 {}（頁面不顯示這幾條）。"""
    res = store.read_json("bt3_research.json", {}) or {}
    R = {r["k"]: r for r in res.get("rows") or []}
    if not R:
        return {}
    from .collect import yh_codes, yhl_codes
    names = names or DL.names
    iss = DL.issued()
    stock = lambda c: len(c) == 4 and c.isdigit() and not c.startswith("0")
    P = PT.Px(DL, [c for c in sorted(set(yh_codes()) | set(yhl_codes())) if stock(c)], iss)
    # 市值口徑同研究：最近一個月底（含當天）的官方收盤 × 發行股數（每日官方分片補快照，不發請求）
    from . import v3data
    try:
        v3data.me_from_mkt()
    except Exception:                                     # noqa: BLE001 —— 補不到就用既有快照
        pass
    snaps = bt3d.month_end_caps()
    sd = [d for d, _ in snaps]
    import bisect
    kof = [bisect.bisect_right(sd, d) - 1 for d in P.cal]
    for c in P.codes:
        P.cap[c] = [snaps[k][1].get(c) if k >= 0 else None for k in kof]
    P._el = {}
    E = bt3.Elig(P)
    rev = PT.load_rev()
    eps = bt3d.load_eps()
    cal, T = P.cal, P.T
    trq = (store.read_json("v3_tr.json", {}) or {}).get("q") or {}
    out = {}
    for k, src, b, name, unit in LIVE:
        r = R.get(k)
        if not r:
            continue
        rows = (bt3s.p7_rows(P, E, b, P.codes, rev) if src == "p7" else bt3s.p3_rows(P, E, b, P.codes, eps, HOLD3))
        ym_of = dict(PT.rev_forms(cal)) if src == "p7" else {}
        qs = sorted({q for e in eps.values() for q in e}) if src == "p3" else []
        q_of = {}
        for q in qs:
            t = PT.form_after_deadline(cal, PT.deadline(q))
            if t is not None:
                q_of[t] = q
        # 前瞻：起算日之後形成、已到出場日的各期
        fwd_rows = [x for x in rows if x[1] is not None and cal[x[0]] >= SINCE]
        pk = bt3s.pick(fwd_rows, 0.0, N, False, UMIN[src])
        fu = bt3.vs_ew(bt3.account(P, pk, b), bt3s._ew(P, b, fwd_rows, pk)) if pk else []
        fs = bt3.sel_stats(fu) if fu else {"n": 0}
        fwd = {"n": fs.get("n", 0), "xe": fs.get("xe"),
               "units": [{"d": u["d"], "out": cal[u["x"]] if u.get("x") is not None and u["x"] < T else None,
                          "r": round(u["r"], 2), "xe": round(u["xe"], 2), "mk": _tr_ret(trq, cal, u.get("t"), u.get("x"))}
                         for u in fu if u.get("xe") is not None]}
        # 本期：最後一個還沒出場的形成日
        cur = next((x for x in reversed(rows) if x[1] is None), None)
        now = None
        if cur:
            t, _, sc = cur
            got = bt3s.pick([cur], 0.0, N, False, UMIN[src])
            if got:
                ent = cal[t + 1] if t + 1 < T else _td_after(cal[t], 1)
                if src == "p7":
                    out_d = next_rev_form(cal[t])
                else:
                    out_d = _td_after(ent, HOLD3 - 1)
                picks = []
                for c in got[0][2]:
                    s = P.s[c]
                    o = s["o"][t + 1] if t + 1 < T else None
                    last = P.close_on_or_before(c, T - 1, t)
                    picks.append({"c": c, "n": names.get(c, c), "sc": round(sc[c], 2), "entry": o, "now": last,
                                  "now_r": round((last / o - 1) * 100, 2) if o and last else None,
                                  "cap": round((P.cap[c][t] or 0) / 1e8), "why": _why(src, c, sc[c], ym_of.get(t), rev, eps,
                                                                                     q_of.get(t))})
                now = {"d": cal[t], "ent": ent, "out": out_d, "n_uni": len(sc), "picks": picks,
                       "entered": t + 1 < T, "ym": ym_of.get(t), "q": q_of.get(t)}
        nxt = None
        if src == "p7":
            nf = next_rev_form(cal[-1]) if not now else now["out"]
            nxt = {"d": nf, "ent": _td_after(nf, 1)}
        elif qs:
            q, nf = next_eps_form(qs[-1])
            nxt = {"d": nf, "ent": _td_after(nf, 1), "q": q}
        out[k] = {"k": k, "src": src, "b": b, "name": name, "unit": unit, "since": SINCE, "res": r, "fwd": fwd,
                  "now": now, "next": nxt, "due": _due(src, cal, rows)}
    out["_ctx"] = (P, E)                                  # 給 existing() 用，呼叫端取出後丟掉（不進頁面）
    return out


def _due(src: str, cal: list, rows: list) -> dict | None:
    """後台驗證「該出名單沒出」：最近一個「已過一個交易日以上」的形成日（月營收＝每月 10 日、財報＝季報期限，
    遇假日順延），以及那天有沒有產生名單。名單要等資料（營收、EPS）到齊才產生，資料沒進來就會缺這一期。"""
    T = len(cal)
    if T < 2:
        return None
    if src == "p7":
        fs = [t for t, _ in PT.rev_forms(cal) if t <= T - 2]
    else:
        y = int(cal[-1][:4])
        qs = [f"{yy:04d}-{mm:02d}-{dd:02d}" for yy in (y - 1, y) for mm, dd in ((3, 31), (6, 30), (9, 30), (12, 31))]
        fs = [t for q in qs if (t := PT.form_after_deadline(cal, PT.deadline(q))) is not None and t <= T - 2]
    if not fs:
        return None
    f = max(fs)
    return {"d": cal[f], "ok": any(x[0] == f for x in rows)}


def _tr_ret(q: dict, cal: list, t: int | None, x: int | None) -> float | None:
    """前瞻每期的同期大盤：加權報酬指數（含息）從決定日收盤到出場日收盤（%，同研究檔「過去照做」的口徑）；
    缺值往前找 10 個交易日，找不到回 None。"""
    def v(i):
        for k in range(i, max(i - 10, -1), -1):
            if k < len(cal) and q.get(cal[k]):
                return q[cal[k]]
        return None
    if t is None or x is None:
        return None
    a, b = v(t), v(x)
    return round((b / a - 1) * 100, 2) if a and b else None


def _sel(s: dict) -> dict:
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items() if k in ("n", "xe", "t", "pos", "drop5")}


def _pay(p: dict) -> dict:
    r = p.get("ratio")
    return {"n": p.get("n"), "win": None if p.get("win") is None else round(p["win"]), "m": None if p.get("m") is None else round(p["m"], 2),
            "ratio": None if r is None else (99.0 if r == float("inf") else round(r, 1)), "ok": bool(p.get("ok")), "path": p.get("path")}


def existing(ctx, strat: dict, grow: dict) -> dict:
    """既有策略（共識加碼、臺灣50 提前卡位、長線成長）用回測方法 v3 評級：新成本、對同一批股票、報酬型態。
    這幾條的資料從 2024～2025 才有，沒有樣本外；參數鄰近沿用原本（對加權指數）的 9 格（頁面標示）。"""
    P, E = ctx
    EWb = {b: bt3.ew_index(P, E, b) for b in bt3.BUCKET}
    ex = bt3s.existing_eval(P, EWb, {"strat": strat, "grow": grow})
    out = {}
    for k, r in ex.items():
        nb = r.get("nb_old") or None
        nb = nb if nb and nb.get("n") else None
        fw = r.get("fwd") or {"n": 0}
        g = bt3.grade3(r["sel"], r["pay"], r["x2"], nb, event=(k == "s3e"), fwd=fw)
        out["s3" if k == "s3e" else k] = {
            "sel": _sel(r["sel"]), "pay": _pay(r["pay"]), "x2": None if r.get("x2") is None else round(r["x2"], 2),
            "nb": {"n": nb.get("n"), "pos": nb.get("pos")} if nb else None, "grade": g["grade"],
            "why": [w for w in g["why"] if w != "樣本外尚未驗證"] +
                   (["沒有樣本外資料（資料從 2024～2025 開始；前瞻達標後代替）"] if "樣本外尚未驗證" in g["why"] else []),
            "fwd": _sel(fw), "by_b": r.get("by_b"), "unit": "次" if k == "s3e" else "筆"}
    return out
