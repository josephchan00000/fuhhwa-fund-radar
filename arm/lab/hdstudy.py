"""籌碼雷達：高股息 ETF 換股研究（0056／00878／00919／00929）——什麼時候卡位、什麼時候賣、誰漲最多。

2026-10-14 使用者：「幫我套用在高股息ETF」（承接臺灣50 的提前卡位研究）。和臺灣50 最大的不同：
  · 被動買賣不是生效日收盤一次做完，而是**過渡期分好幾天**（00919／00929 約 8 個交易日、0056 約 5 個交易日；
    00878 在生效日、但投信常提前分批）→ 出場要看「被動買盤開始前」還是「過渡期中／結束」。
  · 規模大、納入股多是中型股 → 被動買盤常是好幾天的成交量，價格衝擊可能比臺灣50 大。
  · 選股看殖利率（0056 用分析師預估、00878 要 ESG 評分）→ 事前預測比臺灣50 難，先用「已知名單」量出
    各時窗的空間（完美預知的上限），再決定值不值得做預測。

時窗（納入股；扣來回成本 0.585%，超額＝減去加權指數同一時窗）：
  · early_k：公告日前第 k 個交易日開盤買（完美預知）→ 被動買盤開始前一天收盤賣
  · ann_T0：公告後第一個交易日開盤買 → 被動買盤開始前一天收盤賣
  · ann_mid／ann_T1：公告後開盤買 → 過渡期中間／最後一天收盤賣（賣給被動買盤）
  · T1_5：過渡期最後一天收盤買 → 5 個交易日後收盤（換股結束後的走勢）
刪除股：公告前 25 日 → 公告日、公告後 → 過渡期結束、過渡期結束後 5／10 日（被賣完後會不會反彈）。
"""
from __future__ import annotations

import statistics

from . import tw50study as TS

COST = TS.COST
HD_KEYS = ("tw_div", "msci_esg30", "tip_hd", "tip_tech")      # 0056／00878／00919／00929
EARLY = (30, 25, 20, 15, 10, 5)


def _idx(D, d: str | None) -> int | None:
    return TS._on_or_before(D, d) if d else None


def anchors(D, h: dict) -> dict | None:
    """一次審核的時間錨點（交易日索引）：A＝名單公開前最後一個收盤、T0／T1＝被動買賣第一天／最後一天。"""
    ann, eff = h.get("announce"), h.get("effective")
    if not ann or not eff:
        return None
    iA = _idx(D, ann)
    if h.get("ann_pre_open"):            # 台灣開盤前就公布（MSCI 美東收盤後）→ 名單在 A 當天開盤前已知
        iA = iA - 1 if iA else None
    t0, t1 = h.get("trans_start") or eff, h.get("trans_end") or h.get("trans_start") or eff
    i0, i1 = _idx(D, t0), _idx(D, t1)
    if iA is None or i0 is None or i1 is None or i0 <= iA:
        return None
    return {"A": iA, "T0": i0, "T1": i1, "mid": (i0 + i1) // 2}


def _r(P: TS._Px, c: str, i0: int, o0: bool, i1: int, o1: bool):
    if i0 is None or i1 is None or i1 < i0 or (i1 == i0 and o0 == o1) or i1 >= P.D.T or i0 < 0:
        return None, None
    r, x = P.ret(c, i0, o0, i1, o1)
    return (None, None) if r is None else (round(r * 100, 2), None if x is None else round(x * 100, 2))


def _demand(D, c: str, i: int, aum: float | None, n: int | None) -> tuple[float | None, float | None]:
    """被動買盤估計（等權近似：規模 ÷ 成分股數，億元）與占 20 日均量天數。"""
    if not aum or not n:
        return None, None
    s = D.series(c)
    px = s["c"][i] if 0 <= i < D.T else None
    vs = [x for x in s["v"][max(i - 19, 0):i + 1] if x]
    if not px or not vs:
        return None, None
    sh = aum * 1e8 / n / px
    return round(aum / n, 1), round(sh / (sum(vs) / len(vs)), 2)


def events(D, cfg: dict, keys=HD_KEYS) -> list[dict]:
    P = TS._Px(D)
    out = []
    for k in keys:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or ""):
            a = anchors(D, h)
            if not a:
                continue
            A, T0, T1 = a["A"], a["T0"], a["T1"]
            n = ix.get("n")
            rows = []
            for side, codes in (("add", h.get("adds") or []), ("del", h.get("dels") or [])):
                for c in codes:
                    if len(c) != 4 or not c.isdigit():
                        continue
                    row = {"c": c, "n": D.names.get(c, c), "side": side,
                           "mom": None if TS.IX.momentum(D, c, A) is None else round(TS.IX.momentum(D, c, A) * 100, 1)}
                    row["dem"], row["dem_days"] = _demand(D, c, A, h.get("aum"), n)
                    if side == "add":
                        for kk in EARLY:
                            row[f"e{kk}"], row[f"e{kk}x"] = _r(P, c, A - kk + 1, True, T0 - 1, False)
                        row["ann_T0"], row["ann_T0x"] = _r(P, c, A + 1, True, T0 - 1, False)
                        row["ann_mid"], row["ann_midx"] = _r(P, c, A + 1, True, a["mid"], False)
                        row["ann_T1"], row["ann_T1x"] = _r(P, c, A + 1, True, T1, False)
                        row["pre"], row["prex"] = _r(P, c, A - 24, True, A, False)
                        row["T1_5"], row["T1_5x"] = _r(P, c, T1, False, T1 + 5, False)
                    else:
                        row["pre"], row["prex"] = _r(P, c, A - 24, True, A, False)
                        row["ann_T1"], row["ann_T1x"] = _r(P, c, A + 1, True, T1, False)
                        row["T1_5"], row["T1_5x"] = _r(P, c, T1, False, T1 + 5, False)
                        row["T1_10"], row["T1_10x"] = _r(P, c, T1, False, T1 + 10, False)
                    rows.append(row)
            out.append({"key": k, "etf": "／".join(ix.get("etfs") or []), "review": h.get("review"),
                        "announce": D.cal[A], "t0": D.cal[T0], "t1": D.cal[T1], "aum": h.get("aum"), "rows": rows})
    return out


def _stat(xs: list) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "avg": round(statistics.mean(xs), 1), "med": round(statistics.median(xs), 1),
            "win": round(sum(1 for x in xs if x > 0) / len(xs) * 100), "lo": round(min(xs), 1)}


ADD_WIN = [("e25", "公告前 25 日開盤 → 被動買盤前一天收盤（完美預知）"),
           ("e10", "公告前 10 日開盤 → 被動買盤前一天收盤（完美預知）"),
           ("ann_T0", "公告後開盤 → 被動買盤前一天收盤"),
           ("ann_mid", "公告後開盤 → 過渡期中間收盤"),
           ("ann_T1", "公告後開盤 → 過渡期最後一天收盤"),
           ("T1_5", "過渡期結束收盤 → 5 日後")]
DEL_WIN = [("pre", "公告前 25 日 → 公告日"), ("ann_T1", "公告後開盤 → 過渡期最後一天"),
           ("T1_5", "過渡期結束收盤 → 5 日後"), ("T1_10", "過渡期結束收盤 → 10 日後")]


def run(D, cfg: dict) -> dict:
    ev = events(D, cfg)
    if not ev:
        return {"n": 0}
    by = {}
    for k in HD_KEYS:
        es = [e for e in ev if e["key"] == k]
        if not es:
            continue
        adds = [r for e in es for r in e["rows"] if r["side"] == "add"]
        dels = [r for e in es for r in e["rows"] if r["side"] == "del"]
        by[k] = {"etf": es[0]["etf"], "n_rev": len(es), "n_add": len(adds), "n_del": len(dels),
                 "add": {w: {"r": _stat([r.get(w) for r in adds]), "x": _stat([r.get(w + "x") for r in adds])}
                         for w, _ in ADD_WIN},
                 "early": {kk: _stat([r.get(f"e{kk}") for r in adds]) for kk in EARLY},
                 "del": {w: {"r": _stat([r.get(w) for r in dels]), "x": _stat([r.get(w + "x") for r in dels])}
                         for w, _ in DEL_WIN}}
    allx = [r for e in ev for r in e["rows"] if r["side"] == "add"]
    fac = []
    for f, lbl in (("mom", "公告前 40 日漲幅"), ("dem_days", "被動買盤 ÷ 日均量（天，等權估計）"), ("dem", "被動買盤（億，等權估計）")):
        rho, n = TS._spearman([r.get(f) for r in allx], [r.get("ann_T1x") for r in allx])
        rho2, _ = TS._spearman([r.get(f) for r in allx], [r.get("e25x") for r in allx])
        fac.append({"k": f, "lbl": lbl, "rho": rho, "rho_e": rho2, "n": n})
    return {"n": len(allx), "by": by, "fac": fac, "add_win": ADD_WIN, "del_win": DEL_WIN, "early": list(EARLY),
            "ev": [{k: e[k] for k in ("key", "etf", "review", "announce", "t0", "t1", "aum")} |
                   {"rows": [[r["c"], r["n"], r["side"], r.get("mom"), r.get("dem_days"), r.get("e25"), r.get("ann_T0"),
                              r.get("ann_T1"), r.get("T1_5"), r.get("pre")] for r in e["rows"]]} for e in ev]}
