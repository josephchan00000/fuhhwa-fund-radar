"""研究方法檢查（sigspec 第 5.9 節，VER 33；docs/lab_thermo_fair_plan.md 第 11、12 節）。

使用者：「我哪知道是不是你的研究方法有問題」——把第 5.5 節（大跌中的強落底）與第 5.6 節（強弱分級）的逐年檢查換幾種算法，
全部一次算、全部照列；頁面怎麼標不看這個結果決定（第 5.8 節已定）。scripts/run_fairchk.py → data/lab/fairchk_research.json。
落底：B1 和全部週比、B2 每一段一樣重、B3 看 1／6 個月、B4 門檻 5／15 點、B5 報酬與最大回撤中位數、B6 第二套程式。
強弱：L1 以週計、L2 門檻 15／20 點、L3 報酬與最大回撤中位數、L4 第二套程式（台股）。
"""
from __future__ import annotations

import bisect
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import bottombox as BB
from . import bottomspec as BS
from . import sigcat as G
from . import sigspec as S
from . import thermocal as TC

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "fairchk_research.json"


# ── 小工具 ────────────────────────────────────────────────────────────────────

def rate(mask: np.ndarray, t: np.ndarray, Y: np.ndarray) -> list:
    """mask 那幾週、窗口完整的比例 → [比例或 None, 週數]。"""
    y = Y[t[mask]]
    y = y[~np.isnan(y)]
    return [float(y.mean()) if len(y) else None, int(len(y))]


def seg_rate(mask: np.ndarray, t: np.ndarray, Y: np.ndarray) -> list:
    """每一段一樣重（連續的週＝一段；每段先算窗口完整的週的比例，再平均）→ [比例或 None, 有值的段數]。"""
    vals, cur = [], []
    for j in range(len(mask) + 1):
        if j < len(mask) and mask[j]:
            y = Y[t[j]]
            if not np.isnan(y):
                cur.append(float(y))
            continue
        if j > 0 and j <= len(mask) and mask[j - 1]:
            if cur:
                vals.append(sum(cur) / len(cur))
            cur = []
    return [float(np.mean(vals)) if vals else None, len(vals)]


def wmedian(vals: np.ndarray, w: np.ndarray) -> float | None:
    """權重（整數）中位數：值照權重重複後的中位數；沒有值＝None。"""
    ok = ~np.isnan(vals) & (w > 0)
    if not ok.any():
        return None
    return float(np.median(np.repeat(vals[ok], w[ok].astype(np.int64))))


def vbox(box: list, base: list, box_dd: list | None, base_dd: list | None, ep: int) -> str:
    """第 5.5 節的判定，基準換成 base：段數 < BOTTOM_MIN_EP＝few；上漲比例多 BOTTOM_GAIN 以上而且大回撤不比它多＝ok；其餘 no。
    box_dd 為 None＝只比上漲（B3）。"""
    if ep < S.BOTTOM_MIN_EP or box[0] is None or base[0] is None:
        return "few"
    if round(box[0] - base[0], 9) < S.BOTTOM_GAIN:
        return "no"
    if box_dd is not None and (box_dd[0] is None or base_dd[0] is None or box_dd[0] > base_dd[0]):
        return "no"
    return "ok"


def vlevel(s: list, w: list) -> str:
    """第 5.6 節的判定：強或弱 < CAL_MIN_WEEKS＝few；強 − 弱 ≥ LEVEL_GAIN＝ok；其餘 no。"""
    if s[0] is None or w[0] is None or min(s[1], w[1]) < S.CAL_MIN_WEEKS:
        return "few"
    return "ok" if round(s[0] - w[0], 9) >= S.LEVEL_GAIN else "no"


# ── 落底 B1～B5 ───────────────────────────────────────────────────────────────

def bottom_checks(F: dict) -> dict:
    mk = F["mk"]
    W = BB.weeks(F)
    main = BB.summary(F, W)
    px, t, b, gate = W["px"], W["t"], W["box"], W["gate"]
    g = gate[t] if len(t) else np.zeros(0, dtype=bool)
    al = np.ones(len(t), dtype=bool)
    ep = main["ep"]
    H = S.BOTTOM_CHK_H
    Yu, Yw, Yd = G.outcomes(px, H, G.warn_th(mk, H))
    out: dict = {"main": {"box": main["box"], "drop": main["drop"], "all": main["all"], "ep": ep, "v": main["v"]}}
    bu, bd, au, ad = rate(b, t, Yu), rate(b, t, Yw), rate(al, t, Yu), rate(al, t, Yw)
    out["B1"] = {"box": [bu, bd], "base": [au, ad], "v": vbox(bu, au, bd, ad, ep)}
    su, sd_, gu, gd = seg_rate(b, t, Yu), seg_rate(b, t, Yw), seg_rate(g, t, Yu), seg_rate(g, t, Yw)
    out["B2"] = {"box": [su, sd_], "base": [gu, gd], "v": vbox(su, gu, sd_, gd, ep)}
    b3 = {}
    for h in S.CHK_HS:
        u, w, _ = G.outcomes(px, h, G.warn_th(mk, h))
        x = {"box": rate(b, t, u), "base": rate(g, t, u)}
        if h == S.BOTTOM_CHK_H2:
            x["box_dd"], x["base_dd"] = rate(b, t, w), rate(g, t, w)
        x["v"] = vbox(x["box"], x["base"], None, None, ep)
        b3[str(h)] = x
    out["B3"] = b3
    b4 = {}
    for e in S.CHK_EDGES:
        Se = BB.summary(F, BB.weeks(F, e))
        b4[f"{e:g}"] = {"box": Se["box"], "drop": Se["drop"], "ep": Se["ep"], "v": Se["v"], "n_now": len(Se["strong_now"])}
    out["B4"] = b4
    R = G.fwd_ret(px, H)

    def med(m):
        return {"ret": wmedian(R[t[m]], np.ones(int(m.sum()))), "dd": wmedian(Yd[t[m]], np.ones(int(m.sum())))}
    out["B5"] = {"box": med(b), "drop": med(g), "all": med(al)}
    out["B6"] = box2_compare(F, W, main)
    return out


# ── 落底 B6：第二套程式（不用 drop_days／buy_active／stats_before；訊號、統計用 sigverify 的第二套） ──────────

def drop2(px: np.ndarray, mk: str) -> tuple[np.ndarray, list[int], list[tuple]]:
    """大跌中（bottomspec 第 2 節照字面另寫一次）→ (每一天是不是大跌中, 5 日急跌那幾天, 跌 10% 的每一段 (開始, 結束或 None))。"""
    T = len(px)
    fin = np.isfinite(px) & (px > 0)
    e5, last = [], None
    for i in range(BS.E5_DAYS, T):
        if fin[i] and fin[i - BS.E5_DAYS] and px[i] / px[i - BS.E5_DAYS] - 1.0 <= -BS.E5_TH[mk]:
            if last is None or i - last > BS.E5_GAP:
                e5.append(i)
                last = i
    segs, start = [], None
    for i in range(BS.E10_WIN - 1, T):
        w = px[i - BS.E10_WIN + 1:i + 1]
        if np.isnan(w).any() or not fin[i]:
            continue
        dd = 1.0 - px[i] / w.max()
        if start is None and dd >= BS.E10_IN:
            start = i
        elif start is not None and dd < BS.E10_OUT:
            segs.append((start, i))
            start = None
    if start is not None:
        segs.append((start, None))
    gate = np.zeros(T, dtype=bool)
    for a, z in segs:
        gate[a:T if z is None else z] = True
    for e in e5:
        gate[e:e + BS.SIG_WIN + 1] = True
    return gate, e5, segs


def _bottom_id(sd: dict) -> bool:
    """落底型（第 5.5 節照字面另寫）：從 id 拆類別、訊號、變數。"""
    p = sd["id"].split(":")
    cat, sig = p[1], p[-1]
    if cat in ("heat", "crash", "bd") and sig in ("cold", "cold_in"):
        return int(sd["H"]) <= S.H_CRASH
    if cat == "inst":
        return sig in ("sell_run5", "sell_run10")
    return cat == "scen" and p[2] == "SC3"


def box2(F: dict) -> dict:
    """第二套：每年只用之前的資料挑強的落底型訊號，每個週末框有沒有出現 → {"t", "box", "gate"}。"""
    from . import sigverify as V
    mk, cal = F["mk"], F["cal"]
    px = np.asarray(F["px"], dtype=float)
    T = len(cal)
    sds = [sd for sd in V.detect(F)[0]]
    V._expire(F, sds)
    sds = [sd for sd in sds if _bottom_id(sd)]
    gate, e5, segs = drop2(px, mk)
    _, bsd = G.buy_signals(F)                                  # 買進日由 bottom 偵測（同 sigverify.check_buy），之後全部另寫
    seg_end = {a: (T if z is None else z) for a, z in segs}
    items = []
    for sd in sds:
        H = int(sd["H"])
        items.append((V._prep(sd, H), H, V._active(sd, T, H)))
    for sd0 in bsd:
        a = np.zeros(T, dtype=bool)
        for te, bday, _, _ in sd0["buys"]:
            s = int(bday) - S.LAG
            if sd0["ev"] == "E5":
                nxt = [x for x in e5 if x > te]
                end = min(T, te + BS.SIG_WIN + 1, nxt[0] if nxt else T)
            else:
                end = seg_end.get(int(te), te + 1)
            a[s:max(s, min(T, s + S.H_BUY, end))] = True
        P = V._prep({"kind": "event", "samp": sd0["samp"], "days": sd0["days"]}, S.H_BUY)
        items.append((P, S.H_BUY, a))
    Ys = {H: V.outcomes(px, H, G.warn_th(mk, H)) for H in {h for _, h, _ in items}}
    y0 = int(cal[0][:4]) + S.CAL_WARM_Y + (0 if cal[0][5:] == "01-01" else 1)
    we = np.asarray(F["we"], dtype=np.int64)
    tw, bw = [], []
    for yr in range(y0, int(cal[-1][:4]) + 1):
        cut = bisect.bisect_left(cal, f"{yr}-01-01")
        nxt = bisect.bisect_left(cal, f"{yr + 1}-01-01")
        wk = we[(we >= cut) & (we < nxt)]
        if not len(wk):
            continue
        on = np.zeros(len(wk), dtype=bool)
        for P, H, act in items:
            st = V._pstats(P, H, cut, 0, *Ys[H], S.CAL_MIN_SAMP)
            u = (st or {}).get("up") or {}
            if u.get("n", 0) >= S.N_MIN and u.get("hit") is not None and u.get("base") is not None \
                    and round(u["hit"] - u["base"], 9) >= S.BOTTOM_EDGE:
                on |= act[wk]
        tw += wk.tolist()
        bw += (on & gate[wk]).tolist()
    return {"t": np.asarray(tw, dtype=np.int64), "box": np.asarray(bw, dtype=bool), "gate": gate}


def box2_compare(F: dict, W: dict, main: dict) -> dict:
    """第二套的週數、段數、上漲與大回撤比例和主結果比（比例差 < 1e-9、週數一樣）。"""
    from . import sigverify as V
    mk = F["mk"]
    B = box2(F)
    px = np.asarray(F["px"], dtype=float)
    Yu, Yw = V.outcomes(px, S.BOTTOM_CHK_H, G.warn_th(mk, S.BOTTOM_CHK_H))
    t, b = B["t"], B["box"]
    g = B["gate"][t]
    two = {"box": [rate(b, t, Yu), rate(b, t, Yw)], "drop": [rate(g, t, Yu), rate(g, t, Yw)], "ep": BB.episodes(b)}

    def same(x, y):
        return x[1] == y[1] and ((x[0] is None and y[0] is None) or (x[0] is not None and y[0] is not None and abs(x[0] - y[0]) < 1e-9))
    ok = (two["ep"] == main["ep"] and len(t) == len(W["t"]) and bool((t == W["t"]).all()) and bool((b == W["box"]).all())
          and same(two["box"][0], [main["box"]["up"], main["box"]["n"]]) and same(two["box"][1], [main["box"]["dd"], main["box"]["n"]])
          and same(two["drop"][0], [main["drop"]["up"], main["drop"]["n"]]) and same(two["drop"][1], [main["drop"]["dd"], main["drop"]["n"]]))
    diff = None if ok or len(t) != len(W["t"]) else [str(F["cal"][int(x)]) for x in t[b != W["box"]][:5]]
    return {"ok": bool(ok), **two, "diff_weeks": diff}


# ── 強弱 L1～L4 ───────────────────────────────────────────────────────────────

def level_checks(F: dict, second: bool = False) -> dict:
    mk = F["mk"]
    edges = (S.LEVEL_EDGE,) + tuple(S.CHK_EDGES_L)
    W = TC._weekly(F, age=True, level=edges)
    Y, h26, hs = W["Y"], W["hist26"], W["hist26s"]
    px = np.asarray(F["px"], dtype=float)
    out: dict = {"main": TC.level_compare(Y, h26, hs[S.LEVEL_EDGE])}
    for k in out["main"]:
        for side in ("up", "warn"):
            x = out["main"][k][side]
            x["v"] = vlevel(x["s"], x["w"])
    l1, l3 = {}, {}
    for k, H in S.THERMO_H.items():
        t = np.asarray(h26[k]["t"], dtype=np.int64)
        R = G.fwd_ret(px, H)
        l1[k], l3[k] = {}, {}
        for side, c, j in (("up", "u", 0), ("warn", "w", 1)):
            a = np.asarray(h26[k][c], dtype=np.int64)
            s = np.asarray(hs[S.LEVEL_EDGE][k][c], dtype=np.int64)
            st, wk = rate(s > 0, t, Y[k][j]), rate((a > 0) & (s == 0), t, Y[k][j])
            l1[k][side] = {"s": st, "w": wk, "v": vlevel(st, wk)}
            vals = R[t] if side == "up" else Y[k][2][t]
            l3[k][side] = {"s": wmedian(vals, s), "w": wmedian(vals, a - s)}
    out["L1"], out["L3"] = l1, l3
    l2 = {}
    for e in S.CHK_EDGES_L:
        C = TC.level_compare(Y, h26, hs[e])
        for k in C:
            for side in ("up", "warn"):
                C[k][side]["v"] = vlevel(C[k][side]["s"], C[k][side]["w"])
        l2[f"{e:g}"] = C
    out["L2"] = l2
    if second:
        from . import sigverify as SV
        items = {sd["id"]: TC.item_of(sd) for sd in G.signals(F)}
        B = SV.thermo2(F, items, edges=(S.LEVEL_EDGE,))
        same = B["hist26"] == h26 and B["hist26s"][S.LEVEL_EDGE] == hs[S.LEVEL_EDGE]
        out["L4"] = {"ok": bool(same), "weeks": sum(len(h26[k]["t"]) for k in S.THERMO_H)}
    return out


# ── 研究 ──────────────────────────────────────────────────────────────────────

def flips(B: dict, L: dict) -> list:
    """每一種的判定和主結果比有沒有變（分得出 ↔ 分不出；次數太少不算變）。"""
    out = []

    def chk(tag, a, b):
        if {a, b} == {"ok", "no"}:
            out.append([tag, a, b])
    for mk, x in B.items():
        m = x["main"]["v"]
        chk(f"{mk}:B1", m, x["B1"]["v"])
        chk(f"{mk}:B2", m, x["B2"]["v"])
        for h, y in x["B3"].items():
            chk(f"{mk}:B3:{h}", m, y["v"])
        for e, y in x["B4"].items():
            chk(f"{mk}:B4:{e}", m, y["v"])
    for mk, x in L.items():
        for k, sides in x["main"].items():
            for side, y in sides.items():
                chk(f"{mk}:L1:{k}:{side}", y["v"], x["L1"][k][side]["v"])
                for e, C in x["L2"].items():
                    chk(f"{mk}:L2:{e}:{k}:{side}", y["v"], C[k][side]["v"])
    return out


def research(F: dict | None = None) -> dict:
    F = F if F is not None else G.frames()
    B = {mk: bottom_checks(F[mk]) for mk in S.MARKETS if mk in F}
    L = {mk: level_checks(F[mk], second=(mk == "tw")) for mk in S.MARKETS if mk in F}
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "bottom": G._r(B), "level": G._r(L), "flips": flips(B, L)}


def tally(R: dict) -> dict:
    """研究紀錄用的總結（研究檔 → 數字）：落底每個市場幾種算法比基準高、差的範圍、幾種分得出；強弱每一邊同樣；第二套一不一致。"""
    bt = {}
    for mk, x in (R.get("bottom") or {}).items():
        m = x["main"]
        v = [(m["box"]["up"], m["drop"]["up"], m["v"]), (x["B1"]["box"][0][0], x["B1"]["base"][0][0], x["B1"]["v"]),
             (x["B2"]["box"][0][0], x["B2"]["base"][0][0], x["B2"]["v"])]
        v += [(y["box"][0], y["base"][0], y["v"]) for y in x["B3"].values()]
        v += [(y["box"]["up"], y["drop"]["up"], y["v"]) for y in x["B4"].values()]
        ds = [a - b for a, b, _ in v if a is not None and b is not None]
        bt[mk] = {"n": len(ds), "pos": sum(1 for d in ds if d > 0), "lo": min(ds) if ds else None, "hi": max(ds) if ds else None,
                  "ok": sum(1 for *_, z in v if z == "ok")}
    lv = {}
    for side in ("up", "warn"):
        ds, ok, few = [], 0, 0
        for x in (R.get("level") or {}).values():
            for k in x["main"]:
                for y in (x["main"][k][side], x["L1"][k][side], *(C[k][side] for C in x["L2"].values())):
                    if y["v"] == "few" or y["s"][0] is None or y["w"][0] is None:
                        few += 1
                        continue
                    ds.append(y["s"][0] - y["w"][0])
                    ok += y["v"] == "ok"
        lv[side] = {"n": len(ds), "pos": sum(1 for d in ds if d > 0), "ok": ok, "few": few,
                    "lo": min(ds) if ds else None, "hi": max(ds) if ds else None}
    two = {"bottom": all(x["B6"]["ok"] for x in (R.get("bottom") or {}).values()),
           "level": all(x["L4"]["ok"] for x in (R.get("level") or {}).values() if "L4" in x)}
    return {"bottom": bt, "level": lv, "second": two}


def save(R: dict, path: Path | None = None) -> None:
    path = OUT if path is None else path
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(path)


def load() -> dict | None:
    try:
        R = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return R if (R.get("ver") or 0) >= S.CHK_VER else None
