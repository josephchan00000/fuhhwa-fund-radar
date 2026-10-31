"""溫度計「過去讀數這樣的時候」（sigspec 第 5 節 ③d，VER 16、21；docs/lab_noise_plan.md 第 14.10 節、docs/lab_audit_plan.md 第 11.3 節）。

  research(F)   研究：每個市場逐年滾動（每年 1 月 1 日只用之前走完的窗口重算統計）的週末票數、和自己的過去 10 年比的位置、
                過去同一組的週之後上漲／大回撤的比例、區塊重抽判定有沒有關係 → data/lab/thermo_research.json（scripts/run_thermo.py）
  now(mk, ...)  每天建頁：今天的票數（研究檔存的今年 1 月 1 日統計 × 現在有效）→ 每支溫度計兩邊的位置與一句話

票數＝這支溫度計、這一邊，現在有效的 THERMO_X_CATS 訊號裡照第 5 節 ④c 會列出來的（VER 26：訊號自己次數 ≥ N_MIN、這個方向比平常高
THERMO_EDGE 以上，而且那天落的那一格也是；sigage 第 5.1 節）的項目數（同一個項目一票；不做同類合併）。
研究檔另存 VER 25 的票（"v25"：只看訊號自己的成績，VER 23 起的規則）：實戰模擬、期貨加碼照舊用那一套（weekly、now(rule="v25")）。
（VER 21～22：預估之後和隨便挑一天差 LIST_GAP 以上、留下來的比例用那時走完的逐年紀錄；VER 17～20：命中率門檻過了。）
只是描述，不參與任何判定。
"""
from __future__ import annotations

import bisect
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import sigcat as G
from . import sigspec as S

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "thermo_research.json"
SIDES = ("up", "warn")
GROUPS = ("lo", "mid", "hi")


# ── 每個訊號 ──────────────────────────────────────────────────────────────────

def item_of(sd: dict) -> str:
    """同一個項目（sigcat.item_key）的字串鍵。"""
    a, b = G.item_key(sd)
    return f"{a}:{b}"


def active(sd: dict, T: int, H: int) -> np.ndarray:
    """每一天這個訊號在看 H 個交易日的溫度計是不是現在有效（第 5 節 ③a，同 sigcat.now_market）：
    狀態型＝那天是樣本日而且在狀態中（月資料＝最近一個月底在狀態中，到下一個月底前都算）；
    事件型＝最近一次出現（樣本開始以後）在 H 個交易日內，而且之後還沒出現相反的讀數（VER 20）。"""
    a = np.zeros(T, dtype=bool)
    samp = np.asarray(sd["samp"], dtype=np.int64)
    if not len(samp):
        return a
    if sd["kind"] == "state":
        st = np.asarray(sd["state"], dtype=bool)
        if sd.get("monthly"):
            nxt = list(samp[1:]) + [T]
            for i in np.nonzero(st)[0]:
                a[int(samp[i]):int(nxt[i])] = True
        else:
            a[samp[st]] = True
    else:
        D = np.asarray([t for t in sd["days"] if t >= samp[0]], dtype=np.int64)
        for t, e in zip(D.tolist(), G.exp_end(sd, D, H).tolist()):   # VER 20：之後出現相反的讀數就不再算
            a[t:e] = True
    return a


def stats_before(sd: dict, cut: int, Y: tuple, H: int) -> dict | None:
    """只用窗口在 cut 之前走完的樣本日（t＋LAG＋H < cut）算的統計（成功條件、次數、平常同第 2、3.4 節）；
    這樣的樣本日少於 CAL_MIN_SAMP 天回 None（不投票）。"""
    samp = np.asarray(sd["samp"], dtype=np.int64)
    m = samp + S.LAG + H < cut
    if int(m.sum()) < S.CAL_MIN_SAMP:
        return None
    Yu, Yw, _ = Y
    if sd["kind"] == "event":
        return G.ev_stat([t for t in sd["days"] if t + S.LAG + H < cut], Yu, Yw, samp[m], H, 0)
    gap = 1 if sd.get("monthly") else S.EP_GAP
    brk = None if sd.get("brk") is None else np.asarray(sd["brk"], dtype=bool)[m]   # VER 20：遇到相反的極端就切開
    return G.st_stat(np.asarray(sd["state"], dtype=bool)[m], samp[m], Yu, Yw, gap, 0, brk=brk)


def vote(R: dict | None) -> str:
    """會投哪一邊（第 5 節 ③d，VER 23＝④b 列出來的規則）："u"＝偏多、"w"＝警示（兩邊都會就 "uw"）。
    R＝stats_before 的統計：偏多方向次數 ≥ N_MIN 而且命中率 − 平常 ≥ THERMO_EDGE → u；警示方向同一條 → w（sigcat.list_cls）。
    （VER 21～22：預估之後的差 g＝k ×（命中率 − 平常），k 用那時走完的逐年紀錄、另有偏弱；VER 17～20：命中率門檻過了。）"""
    if R is None:
        return ""
    out = set()
    for d in ("up", "warn"):
        st = R.get(d) or {}
        n, hit, base = st.get("n") or 0, st.get("hit"), st.get("base")
        if n < S.N_MIN or hit is None or base is None:
            continue
        cls = G.list_cls(d, hit - base)
        if cls:
            out.add("u" if S.LIST_SIDE[cls] == "up" else "w")
    return "".join(c for c in "uw" if c in out)


# ── 位置、分組、有沒有關係 ────────────────────────────────────────────────────

def rank(counts: list[int]) -> list[tuple[float, float] | None]:
    """每一週和之前最近 CAL_RANK_W 週（至少 CAL_RANK_MIN 週）比：(比它少的比例, 中位名次)；不夠就 None。"""
    out: list[tuple[float, float] | None] = []
    c = np.asarray(counts, dtype=float)
    for j in range(len(c)):
        prior = c[max(0, j - S.CAL_RANK_W):j]
        if len(prior) < S.CAL_RANK_MIN:
            out.append(None)
            continue
        lt = float((prior < c[j]).sum())
        eq = float((prior == c[j]).sum())
        out.append((lt / len(prior), (lt + 0.5 * eq) / len(prior)))
    return out


def group(mid: float) -> str:
    lo, hi = S.CAL_TERC
    return "lo" if mid <= lo else "hi" if mid >= hi else "mid"


def _diff(g: np.ndarray, y: np.ndarray) -> float | None:
    hi, lo = y[g == 2], y[g == 0]
    if not len(hi) or not len(lo):
        return None
    return float(hi.mean() - lo.mean())


def verdict(groups: list[str], ys: list[float]) -> dict:
    """「多」那一組減「少」那一組的比例，CAL_BLOCK 週一塊的循環區塊重抽 CAL_DRAWS 次的 95% 區間（第 5 節 ③d）。
    → {"g": {組: [比例, 週數]}, "all": [比例, 週數], "d", "ci": [下限, 上限], "v": "rel"／"rev"／"none"／"few"}。"""
    g = np.array([GROUPS.index(x) for x in groups], dtype=int)
    y = np.asarray(ys, dtype=float)
    out = {"g": {k: [float(y[g == i].mean()) if (g == i).any() else None, int((g == i).sum())] for i, k in enumerate(GROUPS)},
           "all": [float(y.mean()) if len(y) else None, int(len(y))], "d": _diff(g, y), "ci": None}
    if min(out["g"]["lo"][1], out["g"]["hi"][1]) < S.CAL_MIN_WEEKS:
        out["v"] = "few"
        return out
    rng = np.random.default_rng(S.CAL_SEED)
    n, L = len(y), S.CAL_BLOCK
    vals = []
    for _ in range(S.CAL_DRAWS):
        st = rng.integers(0, n, size=n // L + 1)
        idx = (st[:, None] + np.arange(L)[None, :]).ravel()[:n] % n
        v = _diff(g[idx], y[idx])
        if v is not None:
            vals.append(v)
    lo, hi = (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))) if vals else (None, None)
    out["ci"] = [lo, hi]
    out["v"] = "few" if lo is None else "rel" if lo > 0 else "rev" if hi < 0 else "none"
    return out


# ── 研究 ──────────────────────────────────────────────────────────────────────

def first_year(cal: list[str]) -> int:
    """從資料開始滿 CAL_WARM_Y 年的下一個 1 月 1 日（第一個交易日剛好是 1 月 1 日才不用加一年）。"""
    y = int(cal[0][:4]) + S.CAL_WARM_Y
    return y if cal[0][5:] == "01-01" else y + 1


def weekly(F: dict) -> dict:
    """逐年滾動的週末票數（第 5 節 ③d，VER 25 的票：只看訊號自己的成績）：每年 1 月 1 日只用之前走完的窗口算統計、
    決定每個訊號投哪一邊，那一年每個週末的票數。→ {"y0", "y1", "Y": {溫度計: outcomes}, "hist": {溫度計: {"t": 週末位置,
    "u": 偏多票數, "w": 警示票數}}, "votes": 今年 1 月 1 日每個訊號會投哪一邊}。實戰模擬（practsim）、期貨加碼（tilt）用這一套。"""
    return _weekly(F, age=False)


def _weekly(F: dict, age: bool) -> dict:
    """weekly 的本體；age＝True 另算 VER 26 的票（第 5.1 節：訊號自己的成績會投、而且那天落的那一格也過，格子只用 cut 之前走完的日子）：
    另有 "hist26"、"votes26"（{訊號: {"i", "v": {溫度計: {格: 邊}}}}）與新舊比較 "cmp"。"""
    from . import sigage as A
    mk, cal, px = F["mk"], F["cal"], F["px"]
    T = len(cal)
    we = np.asarray(F["we"], dtype=np.int64)
    sds = [sd for sd in G.signals(F) if sd["cat"] in S.THERMO_X_CATS]
    items = [item_of(sd) for sd in sds]
    Y = {k: G.outcomes(px, H, G.warn_th(mk, H)) for k, H in S.THERMO_H.items()}
    acts = {k: [active(sd, T, H) for sd in sds] for k, H in S.THERMO_H.items()}
    if age:
        cache: dict = {}
        cxs = [A.cond(F, sd, cache) for sd in sds]
        cday: dict = {}
        pref: dict = {}
        for k, H in S.THERMO_H.items():
            cday[k], pref[k] = [], []
            for sd, cx in zip(sds, cxs):
                Dd = A.days(sd, T, H, cx)
                c = np.full(T, -1, dtype=np.int64)
                c[Dd["t"]] = Dd["cid"]
                cday[k].append(c)
                pref[k].append(A.Prefix(Dd, Y[k][0], Y[k][1], np.asarray(sd["samp"], dtype=np.int64), H))
    y0, y1 = first_year(cal), int(cal[-1][:4])
    hist = {k: {"t": [], "u": [], "w": []} for k in S.THERMO_H}
    hist26 = {k: {"t": [], "u": [], "w": []} for k in S.THERMO_H}
    votes_now: dict = {}
    votes26: dict = {}
    for yr in range(y0, y1 + 1):
        cut = bisect.bisect_left(cal, f"{yr}-01-01")
        wk = we[(we >= cut) & (we < bisect.bisect_left(cal, f"{yr + 1}-01-01"))]
        if not len(wk) and yr != y1:
            continue
        for k, H in S.THERMO_H.items():
            on = {"u": {}, "w": {}}
            on26 = {"u": {}, "w": {}}
            for i, sd in enumerate(sds):
                v = vote(stats_before(sd, cut, Y[k], H))
                if not v:
                    continue
                if yr == y1:
                    votes_now.setdefault(sd["id"], {"i": items[i], "v": {}})["v"][k] = v
                a = acts[k][i][wk]
                for c in v:
                    on[c][items[i]] = on[c].get(items[i], np.zeros(len(wk), dtype=bool)) | a
                if not age:
                    continue
                P = pref[k][i].at(cut)
                cw = cday[k][i][wk]
                for c in v:
                    ok = A.passes(P, "up" if c == "u" else "warn")
                    a26 = a & (cw >= 0) & ok[np.maximum(cw, 0)]
                    on26[c][items[i]] = on26[c].get(items[i], np.zeros(len(wk), dtype=bool)) | a26
                    if yr == y1 and ok.any():
                        vv = votes26.setdefault(sd["id"], {"i": items[i], "v": {}})["v"].setdefault(k, {})
                        for cid in np.nonzero(ok)[0].tolist():
                            ck = A.ckey(cid)
                            vv[ck] = "".join(x for x in "uw" if x in vv.get(ck, "") + c)
            for hh, oo in ((hist, on), (hist26, on26)) if age else ((hist, on),):
                hh[k]["t"] += [int(t) for t in wk]
                for c in ("u", "w"):
                    tot = np.zeros(len(wk), dtype=int)
                    for arr in oo[c].values():
                        tot += arr
                    hh[k][c] += [int(x) for x in tot]
    out = {"y0": y0, "y1": y1, "Y": Y, "hist": hist, "votes": votes_now}
    if age:
        out.update(hist26=hist26, votes26=votes26, cmp=compare(Y, hist, hist26))
    return out


def compare(Y: dict, h25: dict, h26: dict) -> dict:
    """新舊比較（第 5.1 節，只描述）：每支溫度計、每一邊，逐年滾動的每個週末兩套規則列出來的項目（項目 × 週）之後實際的
    上漲（偏多那一邊）或大回撤（警示那一邊）比例，和所有週末比；另列「VER 25 列、VER 26 拿掉」的那一部分。
    → {溫度計: {邊: {"all": [比例, 週數], "v25": [比例, 項目週數], "v26": [...], "drop": [...]}}}。"""
    out: dict = {}
    for k in S.THERMO_H:
        Yu, Yw, _ = Y[k]
        t = np.asarray(h25[k]["t"], dtype=np.int64)
        res = {}
        for side, c, Yx in (("up", "u", Yu), ("warn", "w", Yw)):
            y = Yx[t] if len(t) else np.zeros(0)
            ok = np.isfinite(y)
            a, b = np.asarray(h25[k][c], dtype=float)[ok], np.asarray(h26[k][c], dtype=float)[ok]
            y = y[ok]

            def rate(w):
                return [float((w * y).sum() / w.sum()) if w.sum() else None, int(w.sum())]
            res[side] = {"all": [float(y.mean()) if len(y) else None, int(len(y))], "v25": rate(a), "v26": rate(b), "drop": rate(a - b)}
        out[k] = res
    return out


def _hz(mk: str, cal: list, Y: dict, hist: dict) -> dict:
    """每支溫度計：位置、過去同一組的週之後的比例、有沒有關係（第 5 節 ③d）與最後 CAL_RANK_W＋1 個週末的票數。"""
    out = {}
    for k, H in S.THERMO_H.items():
        h = hist[k]
        Yu, Yw, _ = Y[k]
        res = {"H": H, "th": G.warn_th(mk, H)}
        for side, c, Yx in (("up", "u", Yu), ("warn", "w", Yw)):
            rk = rank(h[c])
            gs, ys = [], []
            for j, t in enumerate(h["t"]):
                if rk[j] is None or np.isnan(Yx[t]):
                    continue
                gs.append(group(rk[j][1]))
                ys.append(float(Yx[t]))
            res[side] = verdict(gs, ys)
        keep = S.CAL_RANK_W + 1
        res["wk"] = [cal[t] for t in h["t"][-keep:]]
        res["u"], res["w"] = h["u"][-keep:], h["w"][-keep:]
        out[k] = res
    return out


def market(F: dict) -> dict:
    """一個市場的研究（第 5 節 ③d；VER 26：票看今天那一格，另存 VER 25 的票與新舊比較）。"""
    mk, cal = F["mk"], F["cal"]
    W = _weekly(F, age=True)
    return {"y0": W["y0"], "cut": f"{W['y1']}-01-01", "votes": W["votes26"], "hz": _hz(mk, cal, W["Y"], W["hist26"]),
            "v25": {"votes": W["votes"], "hz": _hz(mk, cal, W["Y"], W["hist"])}, "cmp": W["cmp"]}


def research(F: dict | None = None) -> dict:
    """五個市場的研究（scripts/run_thermo.py）；VER 23 起不用預估之後的研究檔。"""
    F = F if F is not None else G.frames()
    return {"ver": S.VER, "spec_date": S.SPEC_DATE, "run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "last": {mk: F[mk]["cal"][-1] for mk in F}, "mk": {mk: G._r(market(F[mk])) for mk in S.MARKETS if mk in F}}


def save(R: dict, path: Path | None = None) -> None:
    path = OUT if path is None else path
    path.write_text(json.dumps(R, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


_CACHE: dict = {}


def load(path: Path | None = None) -> dict | None:
    path = OUT if path is None else path
    if path not in _CACHE:
        try:
            R = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            R = None
        _CACHE[path] = R if R and (R.get("ver") or 0) >= S.CAL_VER else None
    return _CACHE[path]


# ── 每天：今天的位置 ─────────────────────────────────────────────────────────

def counts_now(M: dict, on: dict, xon: dict | None, rule: str = "v26") -> dict:
    """今天的票數：研究檔存的今年 1 月 1 日統計會投票、而且現在在那支溫度計有效的項目數。→ {溫度計: {"u": 票數, "w": 票數}}。
    VER 26（rule "v26"）：votes 的每支溫度計是 {格: 邊}，看今天落的那一格（on／xon 的 "ck"）；"v25"＝研究檔另存的舊票（只看訊號自己）。"""
    xon = xon or {}
    rows = {r["id"]: r for r in G.research_rows()}
    V = M.get("votes") if rule == "v26" else (M.get("v25") or {}).get("votes")
    out = {k: {"u": set(), "w": set()} for k in S.THERMO_H}
    for sid, x in (V or {}).items():
        r = rows.get(sid)
        for k, v in x["v"].items():
            H = S.THERMO_H[k]
            nat = r is not None and r.get("H") == H
            if not ((nat and sid in on) or (k in (xon.get(sid) or {}))):
                continue
            if isinstance(v, dict):
                cur = on[sid] if (nat and sid in on) else xon[sid][k]
                v = v.get(cur.get("ck"), "")
            for c in v:
                out[k][c].add(x["i"])
    return {k: {c: len(s) for c, s in d.items()} for k, d in out.items()}


def now(mk: str, on: dict, xon: dict | None, d: str | None, rule: str = "v26") -> dict | None:
    """每支溫度計兩邊：{溫度計: {"H", "th", 邊: {"n": 票數, "pct": 比它少的週的比例, "grp", "rate", "all", "v", "ci"}}}；
    研究檔沒有這個市場回 None。位置＝和研究檔最後 CAL_RANK_W 個週末（早於資料日的）比。
    rule＝"v25"：研究檔另存的舊票與舊的位置（實戰模擬的實測區用，practspec 寫的是那一套）。"""
    R = load()
    M = (R or {}).get("mk", {}).get(mk)
    if not M:
        return None
    cnt = counts_now(M, on, xon, rule)
    if rule != "v26":
        M = M.get("v25") or {}
        if not M.get("hz"):
            return None
    out = {}
    for k, h in M["hz"].items():
        wk = [i for i, w in enumerate(h["wk"]) if d is None or w < d][-S.CAL_RANK_W:]
        res = {"H": h["H"], "th": h["th"]}
        for side, c in (("up", "u"), ("warn", "w")):
            prior = np.asarray([h[c][i] for i in wk], dtype=float)
            n = cnt[k][c]
            V = h[side]
            if len(prior) < S.CAL_RANK_MIN:
                res[side] = {"n": n, "pct": None, "grp": None, "v": V["v"]}
                continue
            lt, eq = float((prior < n).sum()), float((prior == n).sum())
            g = group((lt + 0.5 * eq) / len(prior))
            res[side] = {"n": n, "pct": lt / len(prior), "grp": g, "rate": V["g"][g][0], "nw": V["g"][g][1],
                         "hi": V["g"]["hi"][0], "lo": V["g"]["lo"][0], "all": V["all"][0], "v": V["v"],
                         "ci": V.get("ci"), "d": V.get("d")}
        out[k] = res
    return out
