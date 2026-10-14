"""籌碼雷達：高股息 ETF 換股研究（0056／00878／00919／00929）——什麼時候卡位、什麼時候賣、誰漲最多。

2026-10-14 使用者：「幫我套用在高股息ETF」（承接臺灣50 的提前卡位研究）。和臺灣50 最大的不同：
  · 被動買賣不是生效日收盤一次做完，而是**過渡期分好幾天**（00919／00929 約 8 個交易日、0056 約 5 個交易日；
    00878 在生效日、但投信常提前分批）→ 出場要看「被動買盤開始前」還是「過渡期中／結束」。
  · 規模大、納入股多是中型股 → 被動買盤常是好幾天的成交量，價格衝擊可能比臺灣50 大。
  · 選股看殖利率（0056 用分析師預估、00878 要 ESG 評分）→ 事前預測比臺灣50 難，先用「已知名單」量出
    各時窗的空間（完美預知的上限），再決定值不值得做預測。

時間錨點（交易日索引，`anchors()`）：
  · A＝名單公開前最後一個收盤（00878 的名單不公布、ETF 開始換股後從每日持股揭露才看得到 → 用 reveal）
  · C＝資料截止日（有規則可重算的指數：截止日收盤後名單其實已定、只是還沒公布）
  · T0／T1＝被動買賣第一天／最後一天（過渡期；沒有過渡期＝生效日）

時窗（納入股；扣來回成本 0.585%，超額＝減去加權指數同一時窗）：
  · e{k}：A 往前 k 個交易日開盤買（完美預知）→ 被動買盤開始前一天收盤賣
  · c_T0：截止日隔天開盤買 → 被動買盤開始前一天收盤（規則可重算時，這是「不用猜」的最早時點）
  · ann_T0：公告後第一個交易日開盤買 → 被動買盤開始前一天收盤
  · ann_mid／ann_T1：公告後開盤買 → 過渡期中間／最後一天收盤（賣給被動買盤）
  · in_T：被動買盤開始前一天收盤 → 過渡期最後一天收盤（過渡期本身漲不漲）
  · T1_5／T1_10：過渡期最後一天收盤 → 5／10 個交易日後（換股結束後的走勢）
刪除股：公告前 25 日 → 公告日、公告後 → 過渡期結束、過渡期結束後 5／10 日（被賣完後會不會反彈）。

被動買盤估計（`_weights()`）：審核後成分股＝目前 ETF 持股往回推（加回歷次刪除、拿掉歷次納入），
權重＝近 12 個月殖利率占比（各指數上限見 `CAP`）；推不回來時退回等權。規模用設定檔 `aum`（億）。
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date
from pathlib import Path

from . import tw50study as TS

COST = TS.COST
HD_KEYS = ("tw_div", "msci_esg30", "tip_hd", "tip_tech")      # 0056／00878／00919／00929
EARLY = (30, 25, 20, 15, 10, 5)
CAP = {"tw_div": 0.10, "msci_esg30": 0.10, "tip_hd": 0.10, "tip_tech": 0.10}
ROOT = Path(__file__).resolve().parents[2]


def _idx(D, d: str | None) -> int | None:
    return TS._on_or_before(D, d) if d else None


def _trust(D, c: str, d: str):
    doc = D.mkt.get(d) or {}
    for part in ("i_tw", "i_tp"):
        v = (doc.get(part) or {}).get(c)
        if v and len(v) > 1 and v[1] is not None:
            return v[1]
    return None


def trade_window(D, h: dict, iA: int, thr: float = 0.3) -> tuple[int, int] | None:
    """被動 ETF 實際換股的日子（官方投信買賣超推得）：納入股每天的投信買超 ÷ 該檔區間最大值，平均 ≥ thr 的連續交易日
    （容許中間 1 天低於門檻）；沒有納入股就看刪除股的賣超。實測（2026-10-14）：00919 常在公告前 2～3 天就開始買
    （2024-05、2024-12、2025-05）、0056 在生效日（第三個週五）收盤起 5 天、00929 從公告當天收盤起 8 天。"""
    codes, sign = (h.get("adds") or []), 1
    if not codes:
        codes, sign = (h.get("dels") or []), -1
    lo, hi = max(iA - 12, 0), min(iA + 22, D.T - 1)
    mx = {}
    for c in codes:
        xs = [abs(_trust(D, c, D.cal[j]) or 0) for j in range(lo, hi + 1)]
        if max(xs or [0]) > 0:
            mx[c] = max(xs)
    if not mx:
        return None
    hit = []
    for i in range(lo, hi + 1):
        xs = [(_trust(D, c, D.cal[i]) or 0) / m * sign for c, m in mx.items()]
        hit.append(statistics.mean(xs) >= thr if xs else False)
    best, cur = None, None
    gap = 0
    for k, ok in enumerate(hit):
        if ok:
            cur = [cur[0] if cur else k, k]
            gap = 0
        elif cur:
            gap += 1
            if gap > 1:
                best = cur if not best or cur[1] - cur[0] > best[1] - best[0] else best
                cur, gap = None, 0
    if cur:
        best = cur if not best or cur[1] - cur[0] > best[1] - best[0] else best
    if not best or best[1] - best[0] < 2:
        return None
    return lo + best[0], lo + best[1]


def _conv_window(D, key: str, h: dict) -> tuple[str | None, str | None]:
    """沒有投信買賣超可推（未來的審核）時的慣例：0056 生效日（第三個週五）收盤起到過渡期最後一天前一日；
    00919／00929 公告當天收盤起到過渡期最後一天前一日；00878 依設定檔（約生效日前 6 天到生效後幾天）。"""
    te = h.get("trans_end")
    te1 = TS.td_shift(te, -1) if te else None
    if key == "tw_div":
        return h.get("effective"), te1
    if key in ("tip_hd", "tip_tech"):
        return h.get("announce"), te1
    return h.get("trans_start") or h.get("effective"), te or h.get("effective")


def anchors(D, h: dict, key: str | None = None) -> dict | None:
    """一次審核的時間錨點（交易日索引）。A＝名單變得「看得到」的那天收盤（公告日、00878 的 reveal、
    或 ETF 公告前就開始換股時的第一天——每日持股揭露當晚就看得到）。"""
    ann, eff = h.get("reveal") or h.get("announce"), h.get("effective")   # reveal＝名單實際曝光日（00878 看持股揭露）
    if not ann or not eff:
        return None
    iA = _idx(D, ann)
    if iA is None or iA < 0:
        return None
    tw = trade_window(D, h, iA)
    if tw:
        i0, i1 = tw
    else:
        t0, t1 = _conv_window(D, key or "", h)
        i0, i1 = _idx(D, t0), _idx(D, t1)
    if i0 is None or i1 is None or i1 < i0:
        return None
    iA = min(iA, i0)
    iC = _idx(D, h.get("cutoff")) if h.get("cutoff") else None
    mid = (max(i0, iA + 1) + i1) // 2
    return {"A": iA, "C": iC if iC is not None and iC <= iA else None, "T0": i0, "T1": i1,
            "mid": mid if mid > iA else None, "t86": bool(tw)}


def _r(P: TS._Px, c: str, i0, o0: bool, i1, o1: bool):
    if i0 is None or i1 is None or i1 < i0 or (i1 == i0 and o0 == o1) or i1 >= P.D.T or i0 < 0:
        return None, None
    r, x = P.ret(c, i0, o0, i1, o1)
    return (None, None) if r is None else (round(r * 100, 2), None if x is None else round(x * 100, 2))


# —— 成分股往回推＋殖利率權重（被動買盤估計用）

def _cur_holdings(etf: str) -> set[str]:
    try:
        d = json.loads((ROOT / "data" / "etf_holdings.json").read_text(encoding="utf-8"))
        hs = (d.get("etfs") or {}).get(etf, {}).get("holdings") or []
        return {h.get("stock_id") for h in hs if h.get("stock_id")}
    except Exception:
        return set()


def constituents(ix: dict) -> dict[str, tuple[set, set] | None]:
    """{review: (審核前, 審核後)}：目前持股往回推。中間若有臨時異動（合併下市）會對不上檔數 → 那一次回 None。"""
    etf = (ix.get("etfs") or [None])[0]
    cur = _cur_holdings(etf) if etf else set()
    n = ix.get("n")
    out: dict = {}
    after = set(cur)
    for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or "", reverse=True):
        for c, d in (h.get("renames") or {}).items():          # 合併改代號（例：新光金併入台新新光金）
            if d in after:
                after = (after - {d}) | {c}
        adds, dels = set(h.get("adds") or []), set(h.get("dels") or [])
        before = (after - adds) | dels
        nn = h.get("n") or n
        ok = bool(after) and adds <= after and not (dels & after) and (not h.get("n") or len(after) == nn)
        out[h.get("review")] = (set(before), set(after)) if ok else None
        after = before
    return out


def _weights(H, codes: set, d: str, cap: float) -> dict[str, float]:
    """近 12 個月殖利率占比、單檔上限 cap（超過的部分依比例分給其他檔）。"""
    ys = {c: max(H.yld(c, d) or 0.0, 0.0) for c in codes}
    if not any(ys.values()):
        return {c: 1 / len(codes) for c in codes} if codes else {}
    w = {c: y / sum(ys.values()) for c, y in ys.items()}
    for _ in range(20):
        over = {c for c, x in w.items() if x > cap + 1e-9}
        if not over:
            break
        free = sum(x for c, x in w.items() if c not in over)
        extra = sum(w[c] - cap for c in over)
        for c in w:
            w[c] = cap if c in over else w[c] + (extra * w[c] / free if free else 0)
    return w


def _demand(D, H, c: str, i: int, aum: float | None, w: float | None) -> tuple[float | None, float | None]:
    """被動買盤（億元）與占 20 日均量天數。"""
    if not aum or not w:
        return None, None
    s = D.series(c)
    px = s["c"][i] if 0 <= i < D.T else None
    vs = [x for x in s["v"][max(i - 19, 0):i + 1] if x]
    if not px or not vs:
        return None, None
    amt = aum * w
    return round(amt, 1), round(amt * 1e8 / px / (sum(vs) / len(vs)), 2)


def _cur_aum(etf: str) -> tuple[str | None, float | None]:
    try:
        w = json.loads((ROOT / "data" / "etf_watch.json").read_text(encoding="utf-8"))
        items = w.get("items") or w.get("etfs") or w
        items = list(items.values()) if isinstance(items, dict) else items
        for e in items:
            if isinstance(e, dict) and e.get("code") == etf and e.get("aum_e8"):
                return e.get("as_of"), float(e["aum_e8"])
    except Exception:
        pass
    return None, None


def aum_at(ix: dict, d: str) -> float | None:
    """規模（億）：歷次報導值＋今日規模，依日期線性內插、兩端持平（估計）。"""
    pts = sorted((h.get("announce") or h.get("effective"), float(h["aum"])) for h in ix.get("history") or []
                 if h.get("aum") and (h.get("announce") or h.get("effective")))
    cd, ca = _cur_aum((ix.get("etfs") or [None])[0] or "")
    if cd and ca:
        pts.append((cd, ca))
    pts.sort()
    if not pts:
        return None
    if d <= pts[0][0]:
        return pts[0][1]
    for (d0, a0), (d1, a1) in zip(pts, pts[1:]):
        if d0 <= d <= d1:
            span = max((date.fromisoformat(d1) - date.fromisoformat(d0)).days, 1)
            t = (date.fromisoformat(d) - date.fromisoformat(d0)).days / span
            return a0 + (a1 - a0) * t
    return pts[-1][1]


def _cap(H, c: str, d: str) -> float | None:
    p = H.px(c, d)
    sh = H.iss_tw.get(c) or H.iss_tp.get(c)
    return p * sh / 1e8 if p and sh else None


WINS = ("e30", "e25", "e20", "e15", "e10", "e5", "c_T0", "ann_T0", "ann_mid", "ann_T1", "in_T", "pre", "T1_5", "T1_10")


def _wins(P: TS._Px, c: str, a: dict) -> dict:
    """一檔股票在一次審核的各時窗（報酬, 超額）；時窗定義見檔頭。"""
    A, C, T0, T1 = a["A"], a["C"], a["T0"], a["T1"]
    w = {f"e{kk}": _r(P, c, A - kk + 1, True, T0 - 1, False) for kk in EARLY}
    w["c_T0"] = _r(P, c, C + 1, True, T0 - 1, False) if C is not None else (None, None)
    w["ann_T0"] = _r(P, c, A + 1, True, T0 - 1, False)
    w["ann_mid"] = _r(P, c, A + 1, True, a["mid"], False) if a["mid"] is not None else (None, None)
    w["ann_T1"] = _r(P, c, A + 1, True, T1, False)
    w["in_T"] = _r(P, c, T0 - 1, False, T1, False)
    w["pre"] = _r(P, c, A - 24, True, A, False)
    w["T1_5"] = _r(P, c, T1, False, T1 + 5, False)
    w["T1_10"] = _r(P, c, T1, False, T1 + 10, False)
    return w


def events(D, cfg: dict, H=None, keys=HD_KEYS) -> list[dict]:
    """逐次審核的納入／刪除股各時窗表現。超額有兩種：對加權指數（x）、對留任成分股等權平均（c，扣掉高股息風格本身的漲跌）。"""
    P = TS._Px(D)
    out = []
    for k in keys:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        cons = constituents(ix)
        for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or ""):
            a = anchors(D, h, k)
            if not a:
                continue
            A, C, T0, T1 = a["A"], a["C"], a["T0"], a["T1"]
            dA = D.cal[A]
            ba = cons.get(h.get("review"))
            n = ix.get("n") or 1
            wts = _weights(H, ba[1], dA, CAP.get(k, 0.1)) if (H and ba) else {}
            ctrl = {}
            if ba:                                          # 留任成分股（審核前後都在）等權平均
                stay = [_wins(P, c, a) for c in sorted(ba[0] & ba[1]) if len(c) == 4 and c.isdigit()]
                for wn in WINS:
                    xs = [s[wn][0] for s in stay if s[wn][0] is not None]      # 已是 %
                    ctrl[wn] = statistics.mean(xs) if len(xs) >= 5 else None
            rows = []
            for side, codes in (("add", h.get("adds") or []), ("del", h.get("dels") or [])):
                for c in codes:
                    if len(c) != 4 or not c.isdigit():
                        continue
                    m = TS.IX.momentum(D, c, A)
                    row = {"c": c, "n": D.names.get(c, c), "side": side, "mom": None if m is None else round(m * 100, 1)}
                    if side == "add":
                        row["w"] = round(wts[c] * 100, 2) if c in wts else None
                        row["dem"], row["dem_days"] = _demand(D, H, c, A, h.get("aum") or aum_at(ix, dA), wts.get(c) or (1 / n))
                        row["yld"] = round((H.yld(c, dA) or 0) * 100, 2) if H else None
                        row["cap"] = _cap(H, c, dA) if H else None
                    for wn, (r, x) in _wins(P, c, a).items():
                        row[wn], row[wn + "x"] = r, x
                        row[wn + "c"] = round(r - ctrl[wn], 2) if (r is not None and ctrl.get(wn) is not None) else None
                    rows.append(row)
            out.append({"key": k, "etf": "／".join(ix.get("etfs") or []), "review": h.get("review"),
                        "announce": dA, "cutoff": D.cal[C] if C is not None else None,
                        "t0": D.cal[T0], "t1": D.cal[T1], "aum": h.get("aum") or aum_at(ix, dA),
                        "cons_ok": ba is not None, "rows": rows,
                        "ctrl": {wn: (None if v is None else round(v, 2)) for wn, v in ctrl.items()}})
    # 同一檔在 ±40 個交易日內被幾檔高股息 ETF 同時納入
    adds = [(e["key"], D.cal.index(e["announce"]), r) for e in out for r in e["rows"] if r["side"] == "add"]
    for k, i, r in adds:
        r["ovl"] = sum(1 for k2, i2, r2 in adds if k2 != k and r2["c"] == r["c"] and abs(i2 - i) <= 40)
    return out


def _stat(xs: list) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "avg": round(statistics.mean(xs), 1), "med": round(statistics.median(xs), 1),
            "win": round(sum(1 for x in xs if x > 0) / len(xs) * 100), "lo": round(min(xs), 1), "hi": round(max(xs), 1)}


ADD_WIN = [("e25", "公告前 25 日開盤 → 被動買盤前一天收盤（完美預知）"),
           ("e10", "公告前 10 日開盤 → 被動買盤前一天收盤（完美預知）"),
           ("c_T0", "資料截止日隔天開盤 → 被動買盤前一天收盤"),
           ("ann_T0", "公告後開盤 → 被動買盤前一天收盤"),
           ("ann_mid", "公告後開盤 → 過渡期中間收盤"),
           ("ann_T1", "公告後開盤 → 過渡期最後一天收盤"),
           ("in_T", "被動買盤前一天收盤 → 過渡期最後一天收盤"),
           ("T1_5", "過渡期結束收盤 → 5 日後"),
           ("T1_10", "過渡期結束收盤 → 10 日後")]
DEL_WIN = [("pre", "公告前 25 日 → 公告日"), ("ann_T1", "公告後開盤 → 過渡期最後一天"),
           ("T1_5", "過渡期結束收盤 → 5 日後"), ("T1_10", "過渡期結束收盤 → 10 日後")]
FACTORS = [("mom", "公告前 40 日漲幅"), ("dem_days", "被動買盤 ÷ 日均量（天）"), ("dem", "被動買盤（億）"),
           ("w", "估計權重"), ("yld", "近 12 個月殖利率"), ("cap", "市值"), ("ovl", "同期被其他高股息 ETF 納入")]


def _rev_rows(es: list[dict]) -> list[dict]:
    out = []
    for e in es:
        ad = [r for r in e["rows"] if r["side"] == "add"]
        dl = [r for r in e["rows"] if r["side"] == "del"]
        avg = lambda rs, f: (round(statistics.mean([r[f] for r in rs if r.get(f) is not None]), 1)
                             if any(r.get(f) is not None for r in rs) else None)
        out.append({"review": e["review"], "announce": e["announce"], "t0": e["t0"], "t1": e["t1"],
                    "n_add": len(ad), "n_del": len(dl),
                    **{f"a_{w}": avg(ad, w + "x") for w, _ in ADD_WIN},
                    **{f"ac_{w}": avg(ad, w + "c") for w, _ in ADD_WIN},
                    **{f"d_{w}": avg(dl, w + "x") for w, _ in DEL_WIN},
                    **{f"dc_{w}": avg(dl, w + "c") for w, _ in DEL_WIN}})
    return out


def run(D, cfg: dict, H=None) -> dict:
    ev = events(D, cfg, H)
    if not ev:
        return {"n": 0}
    by = {}
    for k in HD_KEYS:
        es = [e for e in ev if e["key"] == k]
        if not es:
            continue
        adds = [r for e in es for r in e["rows"] if r["side"] == "add"]
        dels = [r for e in es for r in e["rows"] if r["side"] == "del"]
        fac = []
        for f, lbl in FACTORS:
            rho, nn = TS._spearman([r.get(f) for r in adds], [r.get("ann_T1x") for r in adds])
            rho2, _ = TS._spearman([r.get(f) for r in adds], [r.get("e25x") for r in adds])
            fac.append({"k": f, "lbl": lbl, "rho": rho, "rho_e": rho2, "n": nn})
        by[k] = {"etf": es[0]["etf"], "n_rev": len(es), "n_add": len(adds), "n_del": len(dels),
                 "add": {w: {"r": _stat([r.get(w) for r in adds]), "x": _stat([r.get(w + "x") for r in adds]),
                             "c": _stat([r.get(w + "c") for r in adds])} for w, _ in ADD_WIN},
                 "early": {kk: _stat([r.get(f"e{kk}x") for r in adds]) for kk in EARLY},
                 "del": {w: {"r": _stat([r.get(w) for r in dels]), "x": _stat([r.get(w + "x") for r in dels]),
                             "c": _stat([r.get(w + "c") for r in dels])} for w, _ in DEL_WIN},
                 "revs": _rev_rows(es), "fac": fac}
    allx = [r for e in ev for r in e["rows"] if r["side"] == "add"]
    fac = []
    for f, lbl in FACTORS:
        rho, n = TS._spearman([r.get(f) for r in allx], [r.get("ann_T1x") for r in allx])
        rho2, _ = TS._spearman([r.get(f) for r in allx], [r.get("e25x") for r in allx])
        fac.append({"k": f, "lbl": lbl, "rho": rho, "rho_e": rho2, "n": n})
    return {"n": len(allx), "by": by, "fac": fac, "add_win": ADD_WIN, "del_win": DEL_WIN, "early": list(EARLY),
            "ev": [{k: e[k] for k in ("key", "etf", "review", "announce", "cutoff", "t0", "t1", "aum")} |
                   {"rows": [[r["c"], r["n"], r["side"], r.get("mom"), r.get("dem_days"), r.get("e25x"), r.get("ann_T0x"),
                              r.get("ann_T1x"), r.get("T1_5x"), r.get("prex"), r.get("w"), r.get("ovl")]
                             for r in e["rows"]]} for e in ev]}


def _fmt(s: dict) -> str:
    return "—" if not s.get("n") else f"{s['avg']:+.1f}%（中位 {s['med']:+.1f}%，勝 {s['win']}%，n={s['n']}）"


if __name__ == "__main__":                  # 研究用：python3 -m arm.lab.hdstudy
    from . import analyze
    from .hdmodel import HD
    D = analyze.Data()
    cfg = json.loads((ROOT / "config" / "index_reviews.json").read_text(encoding="utf-8"))
    out = run(D, cfg, HD(D))
    for k, b in (out.get("by") or {}).items():
        print(f"\n== {k} {b['etf']}：{b['n_rev']} 次、納入 {b['n_add']}、刪除 {b['n_del']}")
        for w, lbl in ADD_WIN:
            print(f"  納入 {lbl}：對大盤 {_fmt(b['add'][w]['x'])}｜對留任股 {_fmt(b['add'][w]['c'])}")
        for w, lbl in DEL_WIN:
            print(f"  刪除 {lbl}：對大盤 {_fmt(b['del'][w]['x'])}｜對留任股 {_fmt(b['del'][w]['c'])}")
        for r in b["revs"]:
            print("   ", r)
        print("  因子：", [(f["k"], f["rho"], f["rho_e"], f["n"]) for f in b["fac"]])
    print("\n全部：", [(f["k"], f["rho"], f["rho_e"], f["n"]) for f in out["fac"]])


# —— 頁面用（指數頁「高股息換股」研究段）
PAGE_WIN = [("e10", "公告前 10 日買 → 被動買盤前一天賣"), ("c_T0", "資料截止日隔天買 → 被動買盤前一天賣"),
            ("ann_T1", "名單公開後買 → 被動買盤最後一天賣"), ("in_T", "被動買盤前一天買 → 被動買盤最後一天賣"),
            ("T1_5", "被動買盤結束 → 5 日後"), ("T1_10", "被動買盤結束 → 10 日後")]
PAGE_DEL = [("pre", "公告前 25 日 → 公告日"), ("ann_T1", "名單公開後 → 被動賣盤最後一天"), ("T1_10", "被動賣盤結束 → 10 日後")]


def page_data(D, cfg: dict, H=None) -> dict:
    out = run(D, cfg, H)
    if not out.get("n"):
        return {"n": 0}
    by = {}
    for k, b in (out.get("by") or {}).items():
        by[k] = {"etf": b["etf"], "n_rev": b["n_rev"], "n_add": b["n_add"], "n_del": b["n_del"],
                 "add": {w: b["add"][w] for w, _ in PAGE_WIN}, "del": {w: b["del"][w] for w, _ in PAGE_DEL},
                 "revs": [{kk: r.get(kk) for kk in ("review", "announce", "t0", "t1", "n_add", "n_del",
                                                    "a_e10", "ac_e10", "a_in_T", "ac_in_T", "a_ann_T1", "ac_ann_T1",
                                                    "a_T1_5", "ac_T1_5", "d_pre", "dc_pre")} for r in b["revs"]]}
    return {"n": out["n"], "by": by, "win": PAGE_WIN, "dwin": PAGE_DEL,
            "fac": [f for f in out.get("fac") or [] if f["k"] in ("mom", "dem_days", "yld", "ovl")]}
