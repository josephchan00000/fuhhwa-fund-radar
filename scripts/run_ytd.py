#!/usr/bin/env python3
"""今年逐月、逐筆表（ytdspec VER 1；docs/lab_review_plan.md 第 9.2 節）。

  USSX_DIR=<資料分支>/data/lab/ussx TZ=Asia/Taipei python3 scripts/run_ytd.py --us-grid   母體 2,016 種＋24 種挑法＋固定那一種（一年一次，約 30 分鐘）
  USSX_DIR=… TZ=Asia/Taipei python3 scripts/run_ytd.py --us-week                           只重跑今年挑到的做法（每週六）
  TZ=Asia/Taipei python3 scripts/run_ytd.py --tw                                            台股新飆股那本帳：年初到接手那天（只算一次）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from arm import clock  # noqa: E402
from arm.lab import store  # noqa: E402
from arm.lab import ytdspec as S  # noqa: E402

OUT_US = store.LAB / S.FILE_US
OUT_TW = store.LAB / S.FILE_TW


def log(*a):
    print(*a, flush=True)


def _J(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _r(x, d=6):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


# ── 美股 ─────────────────────────────────────────────────────────────────────

def us_context():
    from arm.lab import ussxgrid as G
    from arm.lab import ussxpanel as UP
    from arm.lab import ussxqm as QM
    t0 = time.time()
    C = QM.context(UP.load(), UP.earnings(), log=log)
    cx = G.ctx(C)
    sels = G.selections(cx)
    sig = G.signals_all(cx, sels)
    log(f"[ytd] 美股資料與訊號 {time.time() - t0:.0f}s，資料到 {cx['cal'][-1]}")
    return cx, sig


def us_year_part(cx: dict, sig: dict, chosen: dict, all_picks: dict[str, list]) -> dict:
    """今年：固定那一種挑法今年挑到的 k 種做法（年初等分、年中不調）每天的淨值與每一筆；24 種挑法今年的報酬範圍。
    all_picks＝{挑法: [今年挑到的做法]}（含固定那一種）。"""
    from arm.lab import ussxgrid as G
    cal, P = cx["cal"], cx["P"]
    y0i = next(i for i, d in enumerate(cal) if d >= f"{S.YEAR}-01-01")
    d0 = y0i - 1                                             # 去年最後一個交易日（＝100）
    need = sorted({m for v in all_picks.values() for m in v})
    runs = {m: G.run_one(cx, m, sig) for m in need}
    cum = {}
    for m, r in runs.items():
        eq = r["eq"]
        e0 = eq[d0 - r["a"]]
        cum[m] = eq[d0 - r["a"]:] / e0                          # d0＝1
    spx = np.asarray(cx["PQ"]["spx"]["idle"], dtype=float)
    hold = np.concatenate([[1.0], np.cumprod(1 + np.nan_to_num(spx[d0 + 1:]))])

    def path(ms: list[str], cost: float) -> np.ndarray:
        if not ms:
            return hold.copy()
        return np.mean([cum[m] for m in ms], axis=0) * (1 - cost)

    rng = {}
    for nm, ms in all_picks.items():
        rng[nm] = float(path(ms, chosen["cost_of"].get(nm, 0.0))[-1] - 1)
    ms = all_picks[chosen["name"]]
    nav = path(ms, chosen["cost_of"].get(chosen["name"], 0.0))
    days = cal[d0:]
    # 每一筆（今年買進或今年賣出、還拿著的）
    Cf = cx["Cf"]
    from arm.lab import ussxfeat as UF
    from arm.lab import ussxspec as X
    Sx = UF.ffill(P["CS"].astype(float))
    cs = X.COST["stk"]
    k = len(ms)
    trades = []
    for m in ms:
        r = runs[m]
        a, eq = r["a"], r["eq"]
        e0 = eq[d0 - a]
        for j, si, ei, xi, ret, why, cin in r["trades"]:
            if xi < y0i:
                continue
            o = P["O"][ei, j]
            sh = cin / (1 + cs) / o if np.isfinite(o) and o > 0 else None
            if ei <= d0:
                v0 = sh * Cf[d0, j] if sh else None                # 年初的市值
                pnl = cin * (1 + ret) - v0 if v0 else None
                w = v0 / e0 / k if v0 else None
            else:
                pnl = cin * ret
                w = cin / (1 + cs) / eq[ei - 1 - a] / k
            def raw(i, adj):                                      # 含息價格換回當時的價格（只做顯示）
                with np.errstate(invalid="ignore", divide="ignore"):
                    x = adj * Sx[i, j] / Cf[i, j]
                return _r(x, 2)
            bpx = raw(ei, o)
            if why == "open":
                spx_ = raw(xi, Cf[xi, j])
            elif why == "delisted":
                lj = int(P["last"][j])
                spx_ = raw(lj, Cf[lj, j])
            else:
                spx_ = raw(xi, P["O"][xi, j])
            trades.append({"m": m, "c": P["sym"][j], "si": cal[si], "ei": cal[ei], "xi": None if why == "open" else cal[xi],
                           "bpx": bpx, "spx": spx_, "ret": _r(ret), "why": why, "w": _r(w), "pnl": _r(pnl / e0 / k if pnl is not None else None),
                           "carry": bool(ei <= d0)})
    trades.sort(key=lambda t: (t["ei"], t["c"]))
    vals = sorted(rng.values())
    return {"d0": cal[d0], "last": cal[-1], "days": days, "nav": [_r(x) for x in nav], "hold": [_r(x) for x in hold],
            "picks": ms, "trades": trades, "range": {"min": _r(vals[0]), "med": _r(float(np.median(vals))), "max": _r(vals[-1]),
                                                     "by": {n: _r(v) for n, v in sorted(rng.items())}}}


def us_grid() -> int:
    from arm.lab import ussxgrid as G
    t0 = time.time()
    cx, sig = us_context()
    cal = cx["cal"]
    pools = G.names()
    yr = {}
    y_last = int(cal[-1][:4])
    for n, m in enumerate(pools["全部"], 1):
        r = G.run_one(cx, m, sig)
        yr[m] = G.yearly(cal, G.daily(cx, r), S.US_Y0, y_last)
        if n % 100 == 0:
            log(f"[ytd] 母體 {n}／{len(pools['全部'])}，{time.time() - t0:.0f}s")
    spx_yr = G.yearly(cal, np.asarray(cx["PQ"]["spx"]["idle"], dtype=float), S.US_Y0, y_last)
    wf = {}
    for p in S.US_POOLS:
        for L in S.US_L:
            for k in S.US_K:
                wf[f"{p}｜過去{L}年最好{k}種"] = G.walk(yr, pools[p], L, k, y_last, spx_yr) | {"pool": p, "L": L, "k": k}
    assert list(wf) == S.wf_names()
    name, table = G.choose(wf)
    log(f"[ytd] 24 種挑法排名（{S.US_RANK_Y0}～{S.US_RANK_Y1} 年化）：第 {S.US_RANK} 名＝{name}")
    all_picks = {n: w["pick"][S.YEAR] for n, w in wf.items()}
    cost_of = {n: w["cost"][S.YEAR] for n, w in wf.items()}
    part = us_year_part(cx, sig, {"name": name, "cost_of": cost_of}, all_picks)
    doc = {"ver": S.VER, "spec": S.SPEC_DATE, "year": S.YEAR, "made": clock.today_tw().isoformat(), "data_last": cal[-1],
           "n_grid": len(pools["全部"]), "chosen": name, "rank": table,
           "wf": {n: {"pool": w["pool"], "L": w["L"], "k": w["k"], "cagr": _r(G.cagr(w["yr"], S.US_RANK_Y0, S.US_RANK_Y1)),
                      "yr": {str(y): _r(v) for y, v in w["yr"].items()}, "pick": w["pick"][S.YEAR],
                      "prev": w["pick"].get(S.YEAR - 1) or [], "cost": _r(w["cost"][S.YEAR])} for n, w in wf.items()},
           "spx_yr": {str(y): _r(v) for y, v in spx_yr.items()},
           "grid_yr": {m: {str(y): _r(v, 5) for y, v in d.items()} for m, d in yr.items()},
           "year_part": part}
    write_us(doc)
    log(f"[ytd] 寫好 {OUT_US}（{time.time() - t0:.0f}s）")
    return 0


def us_week() -> int:
    """只重跑今年挑到的做法（每週六資料分支更新後）。"""
    doc = json.loads(OUT_US.read_text(encoding="utf-8"))
    if doc.get("ver") != S.VER or doc.get("year") != S.YEAR:
        log("[ytd] ytd_us.json 的版本或年份不同：要先跑 --us-grid（一年一次）")
        return 1
    t0 = time.time()
    cx, sig = us_context()
    all_picks = {n: w["pick"] for n, w in doc["wf"].items()}
    cost_of = {n: w["cost"] or 0.0 for n, w in doc["wf"].items()}
    doc["year_part"] = us_year_part(cx, sig, {"name": doc["chosen"], "cost_of": cost_of}, all_picks)
    doc["data_last"] = cx["cal"][-1]
    doc["made"] = clock.today_tw().isoformat()
    write_us(doc)
    log(f"[ytd] 每週重算好 {OUT_US}（資料到 {doc['data_last']}，{time.time() - t0:.0f}s）")
    return 0


def _us_names(doc: dict) -> dict:
    """今年每一筆的英文公司名（配置頁的後備；中文簡介在 config/holding_profiles.json）。容器內不連網：只看資料夾裡的篩選器檔。"""
    from arm.lab import ussxdata as UD
    codes = sorted({t["c"] for t in doc["year_part"]["trades"]})
    fetch = None if os.environ.get("GITHUB_ACTIONS") == "true" else (lambda: {})
    try:
        return UD.names_for(codes, old=doc.get("names"), fetch=fetch)
    except Exception as e:                                   # noqa: BLE001 —— 名稱只是顯示
        log(f"[ytd] 公司名沒有更新：{type(e).__name__}: {e}")
        return {c: v for c, v in (doc.get("names") or {}).items() if c in codes}


def write_us(doc: dict) -> None:
    doc["names"] = _us_names(doc)
    yp = doc["year_part"]
    lines = ["{"] + [_J(k) + ":" + _J(doc[k]) + "," for k in ("ver", "spec", "year", "made", "data_last", "n_grid", "chosen")]
    lines.append(_J("rank") + ":[\n" + ",\n".join(_J(r) for r in doc["rank"]) + "\n],")
    lines.append(_J("wf") + ":{\n" + ",\n".join(_J(n) + ":" + _J(w) for n, w in doc["wf"].items()) + "\n},")
    lines.append(_J("names") + ":" + _J(doc["names"]) + ",")
    lines.append(_J("spx_yr") + ":" + _J(doc["spx_yr"]) + ",")
    lines.append(_J("grid_yr") + ":{\n" + ",\n".join(_J(m) + ":" + _J(v) for m, v in sorted(doc["grid_yr"].items())) + "\n},")
    head = {k: yp[k] for k in ("d0", "last", "picks", "range")}
    lines.append(_J("year_part") + ":{" + ",".join(_J(k) + ":" + _J(v) for k, v in head.items()) + ",")
    lines.append(_J("days") + ":" + _J(yp["days"]) + ",")
    lines.append(_J("nav") + ":" + _J(yp["nav"]) + ",")
    lines.append(_J("hold") + ":" + _J(yp["hold"]) + ",")
    lines.append(_J("trades") + ":[\n" + ",\n".join(_J(t) for t in yp["trades"]) + "\n]}")
    lines.append("}")
    OUT_US.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tw_bench() -> int:
    """0050 今年的每天收盤（Yahoo 0050.TW，分割已調整、配息沒調整，同證交所收盤）→ data/lab/ytd_0050.json。
    官方全市場分片 2026-06-03 以前沒有 ETF，表的「一直抱著 0050」與不偷看那兩成要用它；配息照 bt3d 的除權息表另外還原。
    只在 CI 跑（本容器擋 Yahoo）：.ping/lab 第一行寫 ytd0050。"""
    from datetime import datetime, timezone
    from urllib.parse import quote
    from arm.lab.heatfetch import _get
    p1 = int(datetime(S.YEAR - 1, 11, 1, tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{quote('0050.TW')}"
           f"?period1={p1}&period2={int(time.time())}&interval=1d")
    doc = json.loads(_get(url, timeout=60).decode("utf-8"))
    res = (((doc.get("chart") or {}).get("result")) or [None])[0] or {}
    off = int((res.get("meta") or {}).get("gmtoffset") or 28800)
    reg = ((res.get("meta") or {}).get("currentTradingPeriod") or {}).get("regular") or {}
    now = time.time()
    open_day = (datetime.fromtimestamp(int(reg["start"]) + off, timezone.utc).date().isoformat()
                if reg.get("start") and reg.get("end") and reg["start"] <= now < reg["end"] + 1800 else None)
    q = (((res.get("indicators") or {}).get("quote")) or [{}])[0] or {}
    out = {}
    for t, c in zip(res.get("timestamp") or [], q.get("close") or []):
        d = datetime.fromtimestamp(int(t) + off, timezone.utc).date()
        if c and d.weekday() < 5 and d.isoformat() != open_day:
            out[d.isoformat()] = round(float(c), 2)
    if len(out) < 100:
        log(f"[ytd] 0050 收盤只有 {len(out)} 天，不寫檔")
        return 1
    try:                                                     # 和官方分片同一天的收盤要一樣（2026-06-03 起）
        from arm.lab import analyze
        D = analyze.Data()
        diff = [(d, v, D.quote("0050", d)[3]) for d, v in out.items() if D.quote("0050", d)]
        bad = [x for x in diff if abs(x[1] - x[2]) > 0.051]
        log(f"[ytd] 0050 和官方收盤同一天的 {len(diff)} 天，差超過 0.05 元的 {len(bad)} 天：{bad[:5]}")
    except Exception as e:                                   # noqa: BLE001
        log(f"[ytd] 0050 沒有和官方收盤比對：{type(e).__name__}: {e}")
    (store.LAB / "ytd_0050.json").write_text(
        '{"src":"yahoo 0050.TW close","close":{\n' + ",\n".join(f'"{d}":{v}' for d, v in sorted(out.items())) + "\n}}\n",
        encoding="utf-8")
    log(f"[ytd] 寫好 ytd_0050.json：{min(out)}～{max(out)} {len(out)} 天")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--us-grid", action="store_true")
    ap.add_argument("--us-week", action="store_true")
    ap.add_argument("--tw", action="store_true")
    ap.add_argument("--tw-bench", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.us_grid:
        return us_grid()
    if a.us_week:
        return us_week()
    if a.tw_bench:
        return tw_bench()
    if a.tw:
        return tw_static(a.force)
    ap.print_help()
    return 1


def tw_static(force: bool = False) -> int:
    """台股新飆股那四成（ytdspec 二②）：去年最後一個交易日到 sxlivespec.TAKE 那本帳每天的總資產、今年賣出的每一筆、
    TAKE 收盤還拿著的每一檔今年的起算市值（只算一次；之後接每天記錄的那本帳）。"""
    if OUT_TW.exists() and not force:
        log(f"{OUT_TW} 已經有了（只算一次）；要重算加 --force")
        return 0
    import pandas as pd
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_sxlive_seed as SD
    from arm.lab import sxlivespec as SS
    t0 = time.time()
    sim, res, m, sig, rows, FO = SD.w7_book()
    chk = SD.check_curve(res)
    eq = res.equity.dropna()
    ds = [str(x.date()) for x in eq.index]
    d0 = max(d for d in ds if d < f"{S.YEAR}-01-01")
    k0 = ds.index(d0)
    e_d0 = float(eq.iloc[k0])
    eqd = {d: float(eq.iloc[k]) for k, d in enumerate(ds) if k >= k0}
    mi = {str(pd.Timestamp(x).date()): i for i, x in enumerate(m.dates)}
    i_d0 = mi[d0]
    B = SD.bridge(sim, m)
    bk, cal = B["bk"], B["cal"]
    eqd.update({d: float(v) for d, v in B["eqs"].items()})
    log(f"[ytd] W7 帳 {chk['days']} 天和接手的檔相同；{d0} 收盤 {e_d0:,.0f}，{SS.TAKE} 收盤 {eqd[SS.TAKE]:,.0f}（{time.time() - t0:.0f}s）")

    def base_of(c: str, ent: str, sh: float, cin: float) -> tuple[float, bool]:
        """今年的起算市值：去年就拿著＝去年最後一個交易日收盤的市值（W7 的還原價）；今年才買＝買進成本。"""
        if ent <= d0:
            s_ = m.col[c]
            return float(sh / m.f[mi[ent], s_] * m.c[i_d0, s_]), True
        return float(cin), False

    def eq_before(d: str) -> float:
        prev = [x for x in eqd if x < d]
        return eqd[max(prev)] if prev else e_d0

    closed = []
    for t in res.trades.itertuples():
        xd = str(pd.Timestamp(t.exit_date).date())
        if xd < f"{S.YEAR}-01-01":
            continue
        ed = str(pd.Timestamp(t.entry_date).date())
        s_ = m.col[str(t.stock_id)]
        base, carry = base_of(str(t.stock_id), ed, float(t.shares), float(t.cost_in))
        closed.append({"c": str(t.stock_id), "ent": ed, "exit": xd, "bpx": _r(t.entry_px / m.f[mi[ed], s_], 2),
                       "spx": _r(t.exit_px / m.f[mi[xd], s_], 2), "ret": _r(t.ret), "why": str(t.reason),
                       "w": _r(base / (e_d0 if carry else eq_before(ed))), "pnl": _r((float(t.proceeds) - base) / e_d0),
                       "carry": carry, "src": "w7"})
    w7 = {p["c"]: p for p in B["w7pos"]}
    for c, si, ei, xi, r, why, sh, pnl, *_ in bk.trades:   # 接到 TAKE 這幾天賣掉的（都是 W7 帶過來的）
        p = w7[c]
        base, carry = base_of(c, p["ent"], p["sh"], p["cin"])
        net = p["cin"] + pnl
        closed.append({"c": c, "ent": p["ent"], "exit": cal[xi], "bpx": _r(p["epx"], 2), "spx": None, "ret": _r(r), "why": why,
                       "w": _r(base / (e_d0 if carry else eq_before(p["ent"]))), "pnl": _r((net - base) / e_d0), "carry": carry,
                       "src": "bridge"})
    it = cal.index(SS.TAKE)
    opens = []
    for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0])):
        ent = cal[q["ei"]]
        base, carry = base_of(c, ent, q["sh"], q["cin"]) if c in w7 else (float(q["cin"]), False)
        pxc = B["px"][c]
        vt = q["k"] * (pxc["c"][it] if np.isfinite(pxc["c"][it]) else pxc["cff"][it])
        opens.append({"c": c, "ent": ent, "base": round(base, 2), "carry": carry, "vt": round(float(vt), 2),
                      "w": _r(base / (e_d0 if carry else eq_before(ent))), "bpx": _r(q.get("epx"), 2)})
    doc = {"ver": S.VER, "spec": S.SPEC_DATE, "year": S.YEAR, "made": clock.today_tw().isoformat(), "book": SS.TAKE_BOOK,
           "d0": d0, "take": SS.TAKE, "e_d0": round(e_d0, 2), "eq": {d: round(v, 2) for d, v in sorted(eqd.items())},
           "closed": sorted(closed, key=lambda x: (x["exit"], x["c"])), "open_take": opens,
           "check": {"w7_days": chk["days"], "w7_max_err": chk["max_err"], "eq_take": round(eqd[SS.TAKE], 2)}}
    lines = ["{"] + [_J(k) + ":" + _J(doc[k]) + "," for k in ("ver", "spec", "year", "made", "book", "d0", "take", "e_d0", "check")]
    lines.append(_J("eq") + ":{\n" + ",\n".join(_J(d) + ":" + _J(v) for d, v in doc["eq"].items()) + "\n},")
    lines.append(_J("closed") + ":[\n" + ",\n".join(_J(t) for t in doc["closed"]) + "\n],")
    lines.append(_J("open_take") + ":[\n" + ",\n".join(_J(t) for t in opens) + "\n]")
    lines.append("}")
    OUT_TW.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"[ytd] 寫好 {OUT_TW}：今年賣出 {len(closed)} 筆、{SS.TAKE} 收盤拿著 {len(opens)} 檔（{time.time() - t0:.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
