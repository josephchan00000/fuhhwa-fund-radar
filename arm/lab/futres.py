"""台指期早盤策略的研究（規格 arm/lab/futspec.py VER 1；docs/lab_fut_plan.md 第 4、5、9 節）。

逐日照規格算：落差 E、門檻（同一版本過去 20 個有算出 E 的交易日 |E| 前 45%）、要不要做、做多或做空、模擬進出場。
每一天先算好「做多」「做空」兩個結果（換算點數）與作者原點數的兩個結果；方向亂選的對照、每天都做多／做空的對照
都從這幾個結果取，不用重跑。另列（不判定）「期貨之後有沒有追上」：決定時間的期貨價到幾個時點的漲跌，和 E 的方向比。
全部寫進 data/lab/fut_research.json（每天 CI 重算；逐筆資料只增不改，所以結果只會變長）。

每一天一列（days）：
  d 日期、dp 前一個交易日、c 契約、f 決定時間（含）以前最後一筆期貨價、est 估算的開盤水準、basis 前一天的價差、
  div 除權息點數、ip 前一天收盤指數、e 落差、th 門檻（None＝過去不到 10 天）、side 做多／做空／None、
  pts [停損, 讓, 移動, 停利]（換算後點數）、L／S 做多／做空的模擬、Lr／Sr 作者原點數的做多／做空、
  mv 決定時間的期貨價到 CATCH 各時點的漲跌（點）；skip＝這天為什麼沒算。
  模擬一筆＝SIM_COLS 順序的陣列（沒有成交＝None）。
"""
from __future__ import annotations

import random
import statistics as st
from datetime import date, timedelta

from .. import twholidays as H
from . import futdata as F
from . import futsig as G
from . import futsim as S
from . import futspec as P
from . import store

OUT = "fut_research.json"
SIM_COLS = ("t_in", "px_in", "t_out", "px_out", "why", "net", "mfe", "mae", "moves")
SIDE_KEY = {"long": "L", "short": "S"}
# 只列、不判定：決定時間的期貨價到這幾個時點（含以前最後一筆）漲跌多少，方向和 E 一不一致
CATCH = (("09:00:30", 9 * 3600 + 30), ("09:01:00", 9 * 3600 + 60), ("09:05:00", 9 * 3600 + 300),
         ("09:30:00", 9 * 3600 + 1800), ("13:30:00", 13 * 3600 + 1800))


def prev_trading_day(d: str) -> str:
    """證交所官方休市表的前一個交易日（含颱風臨時休市）。"""
    x = date.fromisoformat(d) - timedelta(days=1)
    yrs = H.load()
    while x.weekday() >= 5 or H.is_closed(x, yrs):
        x -= timedelta(days=1)
    return x.isoformat()


def _sim(ticks, side: str, pts: dict) -> list | None:
    tr = S.simulate(ticks, side, P.DECIDE_S, stop=pts["stop"], buf=pts["buf"], clear=pts["clear"],
                    target=pts["target"], slip=P.SLIP, exit_s=P.EXIT_S, cost_side=P.cost_side)
    if tr is None:
        return None
    return [tr.t_in, tr.px_in, tr.t_out, tr.px_out, tr.why, round(tr.net, 2), tr.mfe, tr.mae, len(tr.moves)]


def net(sim: list | None) -> float | None:
    return None if sim is None else sim[SIM_COLS.index("net")]


def days_lookahead() -> list[dict]:
    """偷看版：每個存了逐筆與 5 秒指數、前一個交易日也存了的日子。"""
    out = []
    have = set(store.dates(F.KIND_TX)) & set(store.dates(F.KIND_IDX))
    past: list[float] = []
    for d in sorted(have):
        dp = prev_trading_day(d)
        row = {"d": d, "dp": dp}
        if dp not in have:
            row["skip"] = "前一個交易日沒有資料"
            out.append(row)
            continue
        inp = G.day_inputs(d, dp)
        if not inp:
            row["skip"] = "缺逐筆或指數"
            out.append(row)
            continue
        est = G.open_full(d, dp, inp["i_close"], P.COVER_MIN)
        T = inp["ticks"]
        f_dec = S.last_le(T, P.DECIDE_S)
        if est is None or f_dec is None:
            row["skip"] = "缺個股開盤價" if est is None else "決定時間以前沒有成交"
            out.append(row)
            continue
        e = G.edge(inp, f_dec, est)
        th = P.threshold(past)
        pts = P.points(inp["i_close"])
        raw = P.points(inp["i_close"], raw=True)
        side = None
        if th is not None and abs(e) >= th and e != 0:
            side = "long" if e > 0 else "short"
        mv = []
        for _, s in CATCH:
            x = S.last_le(T, s)
            mv.append(None if x is None else x - f_dec)
        row.update({"c": inp["c"], "f": f_dec, "est": round(est, 2), "basis": round(inp["basis"], 2),
                    "div": round(inp["div"], 2), "ip": round(inp["i_close"], 2), "e": round(e, 2),
                    "th": None if th is None else round(th, 2), "side": side,
                    "pts": [pts[k] for k in ("stop", "buf", "clear", "target")],
                    "L": _sim(T, "long", pts), "S": _sim(T, "short", pts),
                    "Lr": _sim(T, "long", raw), "Sr": _sim(T, "short", raw), "mv": mv})
        past.append(abs(e))
        out.append(row)
    return out


def nets(rows: list[dict], key) -> list[float]:
    """依日期順序取每一天的淨點數；key(row) 回模擬欄名（L／S／Lr／Sr）或 None（那天不做）。"""
    out = []
    for r in rows:
        k = key(r)
        x = net(r.get(k)) if k else None
        if x is not None:
            out.append(x)
    return out


def summarize(xs: list[float]) -> dict:
    """扣成本後每筆淨點數（依日期順序）。half1／half2＝依日期分前後兩半的平均。"""
    if not xs:
        return {"n": 0}
    h = len(xs) // 2
    return {"n": len(xs), "mean": round(st.mean(xs), 2), "median": round(st.median(xs), 2),
            "win": round(sum(x > 0 for x in xs) / len(xs), 4), "sum": round(sum(xs), 2),
            "best": round(max(xs), 2), "worst": round(min(xs), 2),
            "half1": round(st.mean(xs[:h]), 2) if h else None, "half2": round(st.mean(xs[h:]), 2)}


def placebo(rows: list[dict], actual_mean: float, n: int = P.JUDGE["placebo_n"], seed: int = P.SEED) -> float | None:
    """同樣的日子、同樣的進出場規則，只是方向亂選（每天多空各半）：亂選的平均 ≥ 實際平均的比例。"""
    pairs = [(net(r["L"]), net(r["S"])) for r in rows
             if r.get("side") and net(r.get("L")) is not None and net(r.get("S")) is not None]
    if not pairs:
        return None
    rng = random.Random(seed)
    hit = 0
    for _ in range(n):
        m = sum(a if rng.random() < 0.5 else b for a, b in pairs) / len(pairs)
        if m >= actual_mean - 1e-9:
            hit += 1
    return hit / n


def catchup(rows: list[dict], only_traded: bool = False) -> list[dict]:
    """期貨之後有沒有往 E 的方向走（只列、不判定）：每個時點的天數、方向一致的比例（不算 0）、順著 E 方向的平均與中位數。"""
    out = []
    for i, (lab, _) in enumerate(CATCH):
        xs = [(r["e"], r["mv"][i]) for r in rows
              if r.get("mv") and r["mv"][i] is not None and r["e"] != 0 and (r.get("side") or not only_traded)]
        nz = [(e, m) for e, m in xs if m != 0]
        along = [m if e > 0 else -m for e, m in xs]
        out.append({"at": lab, "n": len(xs),
                    "agree": round(sum((e > 0) == (m > 0) for e, m in nz) / len(nz), 4) if nz else None,
                    "mean": round(st.mean(along), 2) if along else None,
                    "median": round(st.median(along), 2) if along else None})
    return out


def judge_lookahead(n_days: int, s: dict) -> str:
    """wait＝還沒滿 60 天；out＝連最好的情況都賺不到（淘汰）；upper_ok＝最好的情況賺得到（還要看即時版）。"""
    if n_days < P.JUDGE["days"]:
        return "wait"
    return "out" if s.get("n", 0) == 0 or s["mean"] <= 0 else "upper_ok"


def judge_realtime(n_days: int, s: dict, p: float | None) -> str:
    """wait＝不到 60 天或不到 30 筆；pass＝三條都過；fail＝至少一條沒過。"""
    if n_days < P.JUDGE["days"] or s.get("n", 0) < P.JUDGE["min_trades"]:
        return "wait"
    ok = s["mean"] > 0 and p is not None and p <= P.JUDGE["placebo_p"] and s["half1"] > 0 and s["half2"] > 0
    return "pass" if ok else "fail"


def run() -> dict:
    la = days_lookahead()
    rows = [r for r in la if "e" in r]
    main = nets(rows, lambda r: SIDE_KEY.get(r.get("side")))
    s = summarize(main)
    p = placebo(rows, st.mean(main)) if main else None      # 實際平均用沒進位的（亂選出同一組時要算「不比它差」）
    return {
        "spec_ver": P.VER, "asof": rows[-1]["d"] if rows else None, "cols": list(SIM_COLS),
        "catch_at": [lab for lab, _ in CATCH],
        "lookahead": {
            "days": la, "n_days": len(rows), "main": s, "placebo_p": p,
            "verdict": judge_lookahead(len(rows), s),
            "compare": {"raw_points": summarize(nets(rows, lambda r: SIDE_KEY[r["side"]] + "r" if r.get("side") else None)),
                        "always_long": summarize(nets(rows, lambda r: "L")),
                        "always_short": summarize(nets(rows, lambda r: "S"))},
            "catchup": {"all": catchup(rows), "traded": catchup(rows, only_traded=True)},
        },
        "realtime": {"days": [], "n_days": 0, "verdict": "wait", "note": "等即時版開始取樣（futspec VER 2）"},
    }


def write(doc: dict) -> bool:
    return store.write_json(OUT, doc)
