#!/usr/bin/env python3
"""新飆股接手（sxlivespec VER 3；docs/lab_review_plan.md 第 9.1 節）→ data/lab/sxlive_seed.json（只算一次）。

① W7 的 R60 帳：tw-superstock-lab 的引擎照原樣（scripts/run_sx_curve.py 同一套），跑到 TAKE_V3 收盤、最後一天不平倉；
   每天的淨值要和 data/lab/sx_r60_curve.json 相同（那個檔最後一天是平倉後的值，不比），對不上就不寫檔。
② TAKE_V3 收盤的狀態接到 sxlive.Book（頁面的價格）：TAKE_V3 之後、TAKE 之前的週末照規則出名單、下一個交易日開盤買，
   走到 TAKE 收盤（那天收盤照樣標到期、不下單）。
③ 存 TAKE 收盤的持股（股數、買進日、訊號日、買進成本、待賣出）、現金、用到的幾週名單（依 RS 高到低＋符合哪幾條）、核對數字。
  TZ=Asia/Taipei python3 scripts/run_sxlive_seed.py          （約 4 分鐘）
  --force   已經有檔也重寫（規格說只算一次；只在程式錯了要重算時用，commit 訊息寫原因）"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import run_w7 as W  # noqa: E402
from superstock import combos as CB  # noqa: E402
from superstock import engine as EN  # noqa: E402
from superstock import features as FT  # noqa: E402
from superstock import labpanel as LP  # noqa: E402

from arm import clock  # noqa: E402
from arm.lab import corespec as CS  # noqa: E402
from arm.lab import store  # noqa: E402
from arm.lab import sxlive as L  # noqa: E402
from arm.lab import sxlivespec as S  # noqa: E402

X, SX = W.X, W.SX
OUT = store.LAB / S.SEED_FILE
CURVE = store.LAB / CS.SX_CURVE_FILE


def w7_book():
    """W7 的 R60 帳跑到 TAKE_V3 收盤（combos.run 同一套，只差最後一天不平倉）→ (引擎, 結果, 市場, 訊號表, 樣本, 每年的規則)。"""
    lab = S.TAKE_BOOK
    R = json.loads((W.REPORTS / "W7_results.json").read_text(encoding="utf-8"))
    FO = {(f["lab"], f["y"]): f for f in R["folds"]}
    rows = W.samples(None)
    m, extra = LP.load(codes=None)
    F = FT.compute(m, extra["cap"], FT.VCP_V2)
    fund = LP.fundamentals(extra["cal"], m.stocks)
    el = F["elig"]
    cal = list(extra["cal"])
    mix = {pd.Timestamp(d): i for i, d in enumerate(m.dates)}
    mi = {d: mix.get(pd.Timestamp(d)) for d in {r["d"] for r in rows}}
    by_year: dict[int, list] = {}
    for r in rows:
        by_year.setdefault(int(r["d"][:4]), []).append(r)
    mk = np.zeros(m.c.shape, dtype=bool)
    for y in X.FOLDS:
        preds = [SX.rule_pred([tuple(c) for c in r["conds"]]) for r in FO[(lab, y)]["rules"]]
        for r in by_year.get(y, []) if preds else []:
            if any(p(r["f"]) for p in preds):
                i, j = mi[r["d"]], m.col.get(r["c"])
                if i is not None and j is not None:
                    mk[i, j] = True
    ctx = CB.Ctx(m, F, fund, [], CB.rev_days(cal))
    sig = CB.signals_from(ctx, mk & el, 0.08, f"W7_{lab}")
    # combos.run（market=False、ma_exit=None、breakeven_r=None、固定權重）同一套；只改 liquidate_at_end，留著引擎看最後的持股
    cfg = replace(EN.EngineConfig(costs=EN.Costs()), breakeven_r=None, market_filter=False, block_disposition=False,
                  max_hold_days=X.hold_of(lab), liquidate_at_end=False)
    by_day: dict[int, list] = {}
    ix = {d: i for i, d in enumerate(m.dates)}
    for d, c, sc in zip(sig["date"], sig["stock_id"], sig["score"]):
        i, s = ix.get(pd.Timestamp(d)), m.col.get(str(c))
        if i is None or s is None:
            continue
        by_day.setdefault(i, []).append(EN.Order(s, "open", weight=X.TRADE["weight"], score=float(sc)))

    def decide(i: int, _sim) -> list:
        return [EN.Order(o.s, o.kind, stop_pct=o.stop_pct, weight=o.weight, score=o.score) for o in by_day.get(i, [])]

    sim = EN.Simulator(m, cfg, exit_flags=CB.exit_flags(ctx, None), mf=np.ones(m.n, dtype=bool))
    res = sim.run(decide, X.OOS_START, S.TAKE_V3)
    return sim, res, m, sig, rows, FO


def check_curve(res) -> dict:
    """W7 帳每天的淨值（以第一天為 1）和 SX_CURVE_FILE 相同（最後一天除外）。"""
    doc = json.loads(CURVE.read_text(encoding="utf-8"))
    eq = res.equity.dropna()
    d = [str(x.date()) for x in eq.index]
    nav = (eq / float(eq.iloc[0])).to_numpy()
    if d != doc["d"]:
        raise SystemExit(f"日期和 {CS.SX_CURVE_FILE} 對不上：{d[0]}～{d[-1]}（{len(d)}）vs {doc['d'][0]}～{doc['d'][-1]}（{len(doc['d'])}）")
    err = float(np.max(np.abs(nav[:-1] - np.asarray(doc["nav"][:-1], dtype=float))))
    if err > 1e-6:
        raise SystemExit(f"淨值和 {CS.SX_CURVE_FILE} 對不上：最大差 {err:.2e}")
    return {"days": len(d), "max_err": err, "cagr_file": doc.get("cagr")}


def w7_week(d: str, sig, rows_dc: dict, rules: list, need: set) -> dict:
    """W7 那一週的名單（RS 高到低、同分依代號）＋符合哪幾條（前 WHY_MAX 檔與 need 裡的股票）。"""
    sub = sig[sig["date"] == pd.Timestamp(d)]
    lst = sorted(((str(c), float(s)) for c, s in zip(sub["stock_id"], sub["score"])), key=lambda x: (-x[1], x[0]))
    preds = [SX.rule_pred(r) for r in rules]
    why = {}
    for c, _ in lst:
        if len(why) >= L.WHY_MAX and c not in need:
            continue
        f = rows_dc.get((d, c))
        if f is None:
            continue
        ks = [k for k, p in enumerate(preds) if p(f)]
        feats = sorted({cond[0] for k in ks for cond in rules[k]})
        why[c] = {"k": ks, "v": {x: L._jv(f.get(x)) for x in feats}}
    return {"R60": [[c, round(s, 4)] for c, s in lst], "why": {"R60": why}, "src": "w7"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if OUT.exists() and not a.force:
        print(f"{OUT} 已經有了（規格：只算一次）；要重算加 --force")
        return 0
    t0 = time.time()
    sim, res, m, sig, rows, FO = w7_book()
    last = str(res.equity.index[-1].date())
    if last != S.TAKE_V3:
        raise SystemExit(f"W7 的帳跑到 {last}，不是 TAKE_V3 {S.TAKE_V3}")
    chk = check_curve(res)
    print(f"W7 帳 {chk['days']} 天和 {CS.SX_CURVE_FILE} 相同（最大差 {chk['max_err']:.1e}），{time.time() - t0:.0f}s", flush=True)
    w7pos = [{"c": m.stocks[p.s], "sh": float(p.shares), "ent": str(m.dates[p.entry_i].date()),
              "sig": str(m.dates[p.signal_i].date()), "cin": float(p.cost_in), "pend": p.exit_pending,
              "epx": float(p.entry_px / m.f[p.entry_i, p.s])} for p in sim.pos.values()]
    w7cash, w7eq = float(sim.cash), float(sim.eq_prev)
    dropped = [m.stocks[o.s] for o in sim.orders]           # TAKE_V3 不是週末：那天收盤不下單（規格 ①）

    # ② 接到 TAKE：頁面的價格、每天記錄的引擎
    from arm.lab.analyze import Data
    DL = Data(long=True)
    ctx = L.context(DL)
    cal = ctx["P"].cal
    if S.TAKE not in cal or S.TAKE_V3 not in cal:
        raise SystemExit("頁面的日曆沒有 TAKE 或 TAKE_V3")
    iv, it = cal.index(S.TAKE_V3), cal.index(S.TAKE)
    R = L.load_rules()
    rules = L.rules_for(int(S.TAKE[:4]), S.TAKE_BOOK, R)
    if not rules:
        raise SystemExit("沒有今年的規則")
    sigs, whys = {}, {}
    for d in L.week_ends(S.TAKE_V3, S.TAKE):
        if not L.complete(DL, d):
            raise SystemExit(f"{d} 的官方收盤不齊")
        wy: dict = {}
        sigs[d] = L.day_signals(cal.index(d), ctx, {S.TAKE_BOOK: rules}, why=wy)[S.TAKE_BOOK]
        whys[d] = wy.get(S.TAKE_BOOK) or {}
    codes = sorted({p["c"] for p in w7pos} | {c for d in sigs for c, _ in sigs[d]})
    px = L.panel(ctx, codes)
    miss = [p["c"] for p in w7pos if p["c"] not in px]
    if miss:
        raise SystemExit(f"頁面的價格沒有這幾檔：{miss}")
    bk = L.Book(px, it + 1, ctx["listed"])
    bk.cash = w7cash
    for p in w7pos:
        c = p["c"]
        ei, si = cal.index(p["ent"]), cal.index(p["sig"])
        bk.pos[c] = {"k": p["sh"] / px[c]["f"][ei], "sh": p["sh"], "ei": ei, "si": si, "epx": p["epx"], "cin": p["cin"],
                     "pend": p["pend"]}
    eqv = bk.cash + bk.value(iv)
    bk.eq_prev = eqv
    eqs = {}
    for i in range(iv + 1, it + 1):
        eqs[cal[i]] = bk.step(i, sigs.get(cal[i]) if cal[i] != S.TAKE else None)
    print(f"接到 {S.TAKE}：{len(bk.pos)} 檔、現金 {bk.cash / bk.eq_prev:.1%}，{time.time() - t0:.0f}s", flush=True)

    # ③ 存
    rows_dc = {(r["d"], r["c"]): r["f"] for r in rows}
    need = {}
    for c, q in bk.pos.items():
        need.setdefault(cal[q["si"]], set()).add(c)
    weeks = {}
    for d, cs in sorted(need.items()):
        if d <= S.TAKE_V3:
            weeks[d] = w7_week(d, sig, rows_dc, [[tuple(x) for x in r["conds"]] for r in FO[(S.TAKE_BOOK, int(d[:4]))]["rules"]], cs)
    for d, lst in sigs.items():
        weeks[d] = {"R60": [[c, round(float(rs), 4)] for c, rs in lst], "why": {"R60": whys[d]},
                    "src": "take" if d == S.TAKE else "bridge"}
    pos = [{"c": c, "sh": q["sh"], "ent": cal[q["ei"]], "sig": cal[q["si"]], "cin": round(q["cin"], 2), "pend": q["pend"],
            "epx": None if q.get("epx") is None else round(float(q["epx"]), 4)}
           for c, q in sorted(bk.pos.items(), key=lambda x: (x[1]["ei"], x[0]))]
    doc = {"ver": S.VER, "spec": S.SPEC_DATE, "book": S.TAKE_BOOK, "take": S.TAKE, "v3_end": S.TAKE_V3,
           "made": clock.today_tw().isoformat(), "cash": round(bk.cash, 2), "eq": round(bk.eq_prev, 2), "pos": pos,
           "weeks": weeks,
           "check": {"w7_days": chk["days"], "w7_max_err": chk["max_err"], "w7_eq_v3": round(w7eq, 2), "w7_cash_v3": round(w7cash, 2),
                     "w7_pos_v3": len(w7pos), "live_eq_v3": round(eqv, 2), "dropped_orders_v3": dropped,
                     "eq_bridge": {d: round(v, 2) for d, v in eqs.items()},
                     "bridge_trades": [[c, cal[si], cal[ei], cal[xi], round(r * 100, 2), why] for c, si, ei, xi, r, why, _, _ in bk.trades]}}
    J = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))  # noqa: E731
    lines = ["{"] + [J(k) + ":" + J(doc[k]) + "," for k in ("ver", "spec", "book", "take", "v3_end", "made", "cash", "eq")]
    lines.append(J("pos") + ":[\n" + ",\n".join(J(p) for p in pos) + "\n],")
    lines.append(J("weeks") + ":{\n" + ",\n".join(J(d) + ":" + J(w) for d, w in sorted(weeks.items())) + "\n},")
    lines.append(J("check") + ":" + J(doc["check"]))
    lines.append("}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已寫入 {OUT}（{len(pos)} 檔、{len(weeks)} 週），{time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
