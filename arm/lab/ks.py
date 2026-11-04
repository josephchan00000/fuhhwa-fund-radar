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


# ── 前瞻：每天量落後多少、熔斷與恢復（valog.update 在 CI 每天建頁時呼叫，寫 data/lab/ks_live.json）─────────────

LIVE_FILE = "ks_live.json"
NAMES = {"tw_boom": "台股新飆股", "tw_v3l": "財報驚喜（大型股）", "us_qm": "美股強勢品質股"}
PICK = {"tw_boom": "boom", "tw_v3l": "v3l", "us_qm": "qm"}     # 選股頁、行事曆用的策略鍵
LIVE: dict = {}          # 同一個建頁程序裡別的模組先算好的前瞻淨值：{"tw_v3l": (日期, 淨值)}（v3live.run 放）


def nav_from_account(P, periods: list, b: str, since: str) -> tuple[list[str], list[float]]:
    """財報驚喜（大型股）前瞻：起算日以後形成的各期（還沒出場的那一期出場日＝最後一天）用 bt3.account 算資金帳戶，
    since 以後每一天的淨值（第一期以前、各期之間沒有部位＝淨值不動）。還沒出場那一期的最後一天照收盤賣出算（含賣出成本）。"""
    from . import bt3
    cal = P.cal
    i0 = next((i for i, d in enumerate(cal) if d >= since), None)
    if i0 is None:
        return [], []
    pts = dict(bt3.account(P, periods, b)["curve"]) if periods else {}
    ds, nav, last = [], [], 1.0
    for i in range(i0, len(cal)):
        if i in pts:
            last = pts[i]
        ds.append(cal[i])
        nav.append(float(last))
    return ds, nav


def load_live() -> dict:
    from . import store
    return store.read_json(LIVE_FILE, {}) or {}


def live_series(k: str, old: dict | None = None) -> tuple[list[str], list[float], list[float]] | None:
    """每一份的前瞻（日期、策略淨值、大盤淨值）：起點＝前瞻紀錄起算的那一天（紀錄裡起算日前最後一筆是基準日就從它開始）。"""
    from . import store
    start = K.LIVE_FROM[k]
    if k == "tw_boom":                                    # 飆股前瞻記錄：每天一列，第 4 欄＝加權報酬指數、第 6 欄＝N8（都從 100 起）
        nav = (store.read_json("sxlive.json", {}) or {}).get("nav") or {}
        ds = sorted(nav)
        base = [d for d in ds if d < start][-1:]
        ds = base + [d for d in ds if d >= start]
        rows = [(d, nav[d][5], nav[d][3]) for d in ds if len(nav[d]) > 5 and nav[d][5] and nav[d][3]]
    elif k == "us_qm":                                    # 美股強勢品質股的資金帳戶（每週紀錄＋每天盤後檢查）與 S&P 500 含息
        c = (store.read_json("ussx_qm_live.json", {}) or {}).get("curve") or {}
        rows = [(d, s, b) for d, s, b in zip(c.get("d") or [], c.get("nav") or [], c.get("spx") or []) if d >= start and s and b]
    elif k == "tw_v3l":
        if LIVE.get(k):
            ds, nav = LIVE[k]
        else:                                             # 這一次建頁沒有重算：用上一次存下來的
            s = ((old or {}).get("ser") or {}).get(k) or {}
            ds, nav = s.get("d") or [], s.get("s") or []
        bench = tw_bench()
        rows = [(d, v, bench[d]) for d, v in zip(ds, nav) if d >= start and v and bench.get(d)]
    else:
        return None
    if len(rows) < 2:
        return None
    return [r[0] for r in rows], [float(r[1]) for r in rows], [float(r[2]) for r in rows]


def status(ds: list[str], s: list[float], b: list[float], bd: dict) -> dict:
    """前瞻 → 現在的狀態（ksspec.walk 的事件推出來，和規格同一套）：
    st＝on／pause；lag、uw＝現在落後多少、幾天沒追上（恢復過＝從恢復那天重新量）；暫停中另給觸發那天與要追回多少。"""
    rel = K.rel_series(s, b)
    ev = K.walk(rel, bd)
    pr = [e for e in ev if e["k"] in ("pause", "resume")]
    paused = bool(pr) and pr[-1]["k"] == "pause"
    seg = 0
    for e in pr:
        if e["k"] == "resume":
            seg = e["i"]
    j = max(i for i, x in enumerate(rel) if x is not None)
    dd, uw = K.lag(rel[seg:j + 1])
    out = {"a": ds[0], "d": ds[j], "n": j + 1, "lag": dd[-1], "uw": uw[-1], "dd": bd["dd"], "uwb": bd["uw"],
           "dd_bt": bd.get("dd_bt"), "uw_bt": bd.get("uw_bt"), "st": "pause" if paused else "on",
           "ev": [[ds[e["i"]], e["k"]] for e in ev]}
    if paused:
        t = pr[-1]["i"]
        s0 = max((e["i"] for e in pr[:-1] if e["k"] == "resume"), default=0)
        out["trig"] = {"d": ds[t], "lag": K.lag(rel[s0:t + 1])[0][-1]}
        out["need"] = rel[t] / rel[j] - 1 if rel[j] else None          # 要比大盤多賺多少才回到暫停那天
        dd2, uw2 = K.lag(rel[s0:j + 1])
        out["lag"], out["uw"] = dd2[-1], uw2[-1]
    out["slow"] = (not paused) and out["uw"] > bd["uw"]
    return out


def daily(record: bool, made: str) -> dict:
    """每一份：前瞻 → 狀態；record（CI）時寫回 ks_live.json。門檻檔沒有的那一份不算。"""
    from . import store
    B = load_bounds().get("slices") or {}
    old = load_live()
    out = {"ver": K.VER, "made": made, "slices": {}, "ser": dict(old.get("ser") or {})}
    for k in K.SLICES:
        if not B.get(k):
            continue
        try:
            ser = live_series(k, old)
        except Exception as e:                            # noqa: BLE001 —— 讀不到就這一份不算
            print(f"[ks] {k} 前瞻讀不到：{type(e).__name__}: {e}")
            ser = None
        if ser:
            out["slices"][k] = status(*ser, B[k])
    if LIVE.get("tw_v3l"):
        ds, nav = LIVE["tw_v3l"]
        out["ser"]["tw_v3l"] = {"d": list(ds), "s": [round(x, 6) for x in nav]}
    if record:
        store.write_json(LIVE_FILE, out)
    return out


def paused() -> set[str]:
    """暫停中的那幾份（選股頁鍵：boom／v3l／qm）。檔案讀不到＝空的（不擋任何東西）。"""
    sl = (load_live().get("slices") or {})
    return {PICK[k] for k, v in sl.items() if v.get("st") == "pause" and k in PICK}
