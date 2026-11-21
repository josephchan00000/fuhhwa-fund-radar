"""大盤修正中的領導股觀察名單（規格 arm/lab/leadspec.py VER 1；docs/lab_crash_leaders_plan.md）。只讀 repo 裡的資料、不連網。

  market(idx, i)        → 加權指數的狀態：離 52 週高點多少、50／200 日線、是不是修正中（規格第 1、6 點）
  screen(DL, keep)      → 今天的名單（規格第 2～5 點）：{"d", "mkt", "rows": [{代號, 名稱, 收盤, 離高點, RS, 樣板 n/8, 照書三關, 位置…}]}
特徵與合格股票和飆股候選、W9 同一套（arm/lab/superx.feats_on、company.market_table）；位置用 arm/lab/sepa.plan_today。
"""
from __future__ import annotations

from . import leadspec as S


def _mean(xs: list, i: int, n: int):
    v = [x for x in xs[max(0, i - n + 1):i + 1] if x is not None]
    return sum(v) / len(v) if len(v) >= int(n * 0.9) else None


def market(idx: list, i: int) -> dict:
    """規格第 1、6 點。"""
    win = [x for x in idx[max(0, i - 251):i + 1] if x is not None]
    p = idx[i]
    if not win or p is None:
        return {}
    hi = max(win)
    ma50, ma200 = _mean(idx, i, 50), _mean(idx, i, 200)
    dd = p / hi - 1
    return {"close": p, "hi": hi, "dd": dd, "corr": dd <= -S.CORR_MIN, "ma50": ma50, "ma200": ma200,
            "vs50": None if not ma50 else p / ma50 - 1, "vs200": None if not ma200 else p / ma200 - 1,
            "below200": bool(ma200 and p < ma200)}


def three_gates(f: dict) -> bool | None:
    """W9 的照書三關：EPS 年增 ≥ 25%、近 3 月營收年增 ≥ 25%、其中一個在加速；缺值＝None。"""
    ey, ry3, ea, ra = f.get("ey"), f.get("ry3"), f.get("eacc"), f.get("racc")
    if ey is None or ry3 is None:
        return None
    return ey >= 0.25 and ry3 >= 0.25 and ((ea or 0) > 0 or (ra or 0) > 0)


def passes(f: dict, mk: dict) -> bool:
    """規格第 3 點（VER 2 加 (d) 成長）。"""
    if not f.get("el") or not mk.get("corr"):
        return False
    tt = f.get("tt") or []
    d = f.get("d52h")
    grow = any(x is not None and x >= S.GROWTH for x in (f.get("ey"), f.get("ry3")))      # VER 2：成長
    return (d is not None and d >= S.HOLD * mk["dd"] and (f.get("rs") or 0) >= S.RS_MIN
            and len(tt) > max(S.TT_LONG) and all(tt[k] for k in S.TT_LONG) and grow)


def screen(DL=None, keep: dict | None = None, today_ix: int | None = None) -> dict:
    from . import company
    from . import sepa as SP
    from . import superx as SX
    from .analyze import Data
    DL = DL or Data()
    k = keep if keep is not None else {}
    if "P" not in k:
        company.market_table(DL, today_ix=today_ix, keep=k)
    P, pxs = k["P"], k["pxs"]
    cal = P.cal
    i = len(cal) - 1 if today_ix is None else today_ix
    while i > 0 and not any((P.s[c]["c"][i] for c in P.codes[:200])):
        i -= 1
    F = SX.feats_on(i, P, pxs, k["funds"], k["qitems"], k["rf"], all_rows=True)
    idx = DL.taiex()
    dix = {d: j for j, d in enumerate(DL.cal)}
    mk = market(idx, dix[cal[i]]) if cal[i] in dix else {}
    names = getattr(DL, "names", None) or {}
    from . import market as MKT
    rows = []
    for c, f in F.items():
        if not passes(f, mk):
            continue
        px = pxs[c]
        pl = SP.plan_today(px.h, px.l, px.c, px.v, P.s[c]["c"], i)
        rows.append({"c": c, "n": (names.get(c) if isinstance(names, dict) else None) or MKT.NAMES.get(c) or c,
                     "px": P.s[c]["c"][i], "d52h": f.get("d52h"), "rs": f.get("rs"), "tt_n": f.get("tt_n"),
                     "gates": three_gates(f), "ey": f.get("ey"), "ry3": f.get("ry3"), "rnh12": f.get("rnh12"),
                     "st": SP.ST.get(pl.get("st"), ""), "piv": pl.get("piv"), "stop": pl.get("stop"), "r120": f.get("r120")})
    rows.sort(key=lambda r: (-(r["d52h"] or -9), -(r["rs"] or 0), r["c"]))
    return {"ver": S.VER, "d": cal[i], "mkt": mk, "n_el": sum(1 for f in F.values() if f.get("el")), "rows": rows}
