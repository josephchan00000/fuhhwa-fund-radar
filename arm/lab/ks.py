"""策略熔斷（ksspec；docs/lab_killswitch_plan.md）：回測門檻、前瞻落後、事件。

門檻（bounds）：每一份照 ksspec.BT_SRC 拿回測的逐日淨值，對大盤（台股＝加權報酬指數、美股＝S&P 500 含息）算相對淨值，
回測期間（起點到 SPEC_DATE 以前最後一天）落後最深 × DD_MULT、最久沒創新高 × UW_MULT，寫進 data/lab/ks_bounds.json（scripts/run_ks.py）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import ksspec as K

ROOT = Path(__file__).resolve().parents[2]


def tw_bench() -> dict[str, float]:
    """加權報酬指數（含息）{日期: 值}。"""
    from . import store
    q = (store.read_json("v3_tr.json", {}) or {}).get("q") or {}
    return {d: float(v) for d, v in q.items() if v}


def worst(dates: list[str], rel: list) -> dict:
    """相對淨值 → 落後最深那次（從哪一天的高點、跌到哪一天）與最久沒創新高那段（從哪一天到哪一天）。"""
    dd, uw = K.lag(rel)
    i_dd = max((i for i, x in enumerate(dd) if x is not None), key=lambda i: dd[i], default=None)
    i_uw = max((i for i, x in enumerate(uw) if x is not None), key=lambda i: uw[i], default=None)

    def peak_before(i):
        best, at = None, None
        for j in range(i + 1):
            if rel[j] is not None and (best is None or rel[j] >= best * (1 - K.EPS)):
                best, at = max(rel[j], best or rel[j]), j
        return at
    out = {}
    if i_dd is not None:
        out["dd_at"] = [dates[peak_before(i_dd)], dates[i_dd]]
    if i_uw is not None:
        j = peak_before(i_uw)
        out["uw_at"] = [dates[j], dates[i_uw]]
    return out


def bounds_of(dates: list[str], nav: list, bench: dict[str, float], end: str = K.SPEC_DATE) -> dict:
    """回測逐日淨值＋大盤 → 門檻（ksspec.bounds）＋期間與最差那次的日子。只用兩邊都有值、而且不晚於 end 的日子。"""
    ds, s, b = [], [], []
    for d, v in zip(dates, nav):
        if d <= end and v and bench.get(d):
            ds.append(d)
            s.append(float(v))
            b.append(bench[d])
    if len(ds) < 2:
        return {}
    rel = K.rel_series(s, b)
    out = K.bounds(rel)
    out.update(a=ds[0], b=ds[-1], n=len(ds), **worst(ds, rel))
    return out


def bt_boom() -> tuple[list[str], list[float]]:
    """tw_boom：W10 挑出的 N8 做法的回測淨值（data/lab/sx_n8_curve.json）。"""
    doc = json.loads((ROOT / "data" / "lab" / "sx_n8_curve.json").read_text(encoding="utf-8"))
    return list(doc["d"]), [float(x) for x in doc["nav"]]


def bt_v3l(P=None) -> tuple[list[str], list[float]]:
    """tw_v3l：財報驚喜（大型股）的資金帳戶（bt3.account，和 core.stk_sleeve 同一份名單）逐日淨值；沒有部位的日子淨值不動。"""
    from . import bt3, bt3d, core
    P = P or bt3d.Panel()
    pk = core.sleeve_periods(P)
    pts = dict(bt3.account(P, pk, "L")["curve"])
    i0, i1 = min(pts), max(pts)
    ds, nav, last = [], [], None
    for i in range(i0, i1 + 1):
        if i in pts:
            last = pts[i]
        ds.append(P.cal[i])
        nav.append(last)
    return ds, nav


def bt_qm(C: dict) -> tuple[list[str], list[float], dict[str, float]]:
    """us_qm（資料分支）：ussxqm 規則 QM 的照做淨值（S&P 500 那個計畫、主要成本、閒置放現金）與 S&P 500 含息，
    都從 QM_EVAL（成績起算）那天＝1 起。"""
    import numpy as np
    from . import ussxqm as QM
    from . import ussxspec as X
    cal = C["cal"]
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    rr = QM.rets(C, QM.run(C, sig, "spx", X.COST["stk"]))
    sp = np.asarray(C["PQ"]["spx"]["idle"], dtype=float)
    a = QM.a_of(cal, X.QM_EVAL)
    nav = np.cumprod(1 + np.nan_to_num(rr[a:]))
    bn = np.cumprod(1 + np.nan_to_num(sp[a:]))
    ds = list(cal[a:])
    return ds, [float(x) for x in nav], dict(zip(ds, (float(x) for x in bn)))


def load_bounds() -> dict:
    from . import store
    return store.read_json(K.BOUNDS_FILE, {}) or {}


def save_bounds(new: dict, made: str) -> dict:
    """門檻只增不改：同一份已經有、而且規格版本相同 → 不覆蓋（數字算出來就鎖住，ksspec）；規格改版才重算。"""
    from . import store
    doc = load_bounds()
    sl = doc.setdefault("slices", {})
    for k, v in new.items():
        if k in sl and sl[k].get("ver") == K.VER:
            continue
        sl[k] = {**v, "ver": K.VER, "made": made, "src": K.BT_SRC[k], "bench": K.BENCH[K.SLICE_MK[k]]}
    doc.update(spec=K.SPEC_DATE, ver=K.VER)
    store.write_json(K.BOUNDS_FILE, doc)
    return doc
