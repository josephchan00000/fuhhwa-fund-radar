"""籌碼雷達：高股息「依編製規則提前卡位」研究與回測（2026-10-15）。

使用者（2026-10-15）：「為什麼高股息的不是用他們的指數編纂邏輯去提前試算可能加入的公司，而且可能加入的權重會很大的公司，
用這個邏輯去延伸投資架構跟回測」。規劃見 docs/hd_preposition_plan.md。

  · 名單：`hdpredict` 依規則重算（00919、00929）。0056（分析師預估股利）、00878（ESG 評級）重現不了，不做。
  · 被動買進金額＝預估權重 × ETF 規模（2026-10-15 用 ETF 實際持股校準權重公式）：
      00919 實際上接近「市值加權」（log 權重對 log 市值 R² 0.97，殖利率只是小幅傾斜；媒體寫的「股利率加權」
      對不上實際持股）→ 預估成分股裡的市值占比、單檔上限 15%（2025-05 前 10%）。
      00929 是殖利率加權 → 預估成分股裡的殖利率占比、上限 10%；2026-06 的 22 檔納入股中位誤差 15%
      （若用市值估會差 52%）。
    被動買盤天數＝預估買進金額 ÷ 20 日平均成交金額。
  · 交易（同一次審核各檔等額；扣來回成本 0.585%）：
      資料截止日前 L 個交易日收盤選股（預估納入、預估被動買盤 ≥ 門檻日量）→ 隔天開盤買；
      截止日收盤依規則重算：名單沒有的隔天開盤賣、名單有但還沒買的隔天開盤補進；
      官方公告沒有納入的 → 公告後第一個交易日開盤賣；
      其餘在被動買盤最後一天收盤賣（主規格），或被動買盤開始前一天收盤賣（比較用）。
  · 比較：加權指數（超額 x）、審核前後都在的成分股等權（c，扣掉高股息類股本身的漲跌）、完美預知名單（上限）。
"""
from __future__ import annotations

import statistics

from . import hdpredict as HP
from . import hdstudy as HS
from . import tw50study as TS

KEYS = ("tip_hd", "tip_tech")
LEADS = (0, 5, 10, 20)
THS = (0.0, 3.0, 5.0, 10.0)
EXITS = ("T1", "T0")
MAIN = {"lead": 0, "th": 5.0, "exit": "T1"}          # 主規格（看結果前寫死，見規劃文件第 3 節）


def _capped(w: dict[str, float], cap: float) -> dict[str, float]:
    """單檔上限 cap：超過的固定在 cap，剩下的權重依原比例分給其他檔（最多 n 輪就收斂）。"""
    w0, fixed = dict(w), set()
    out = dict(w)
    for _ in range(len(w) + 1):
        over = {c for c, x in out.items() if c not in fixed and x > cap + 1e-12}
        if not over:
            break
        fixed |= over
        rest = max(1.0 - cap * len(fixed), 0.0)
        tot = sum(w0[c] for c in w0 if c not in fixed)
        out = {c: cap if c in fixed else (rest * w0[c] / tot if tot else 0.0) for c in w0}
    return out


def index_weights(cx: HP.Ctx, key: str, sel: list[str], d: str, cap: float, info: dict | None = None) -> dict[str, float]:
    """依實際持股校準的權重公式（2026-10-15）：00919＝市值加權、00929＝殖利率加權；單檔上限 cap。"""
    if key == "tip_hd":
        raw = {c: HS._cap(cx.H, c, d) or 0.0 for c in sel}
    else:
        raw = {c: max(((info or {}).get(c) or {}).get("yld") or (cx.H.yld(c, d) or 0.0) * 100, 0.0) for c in sel}
    tot = sum(raw.values())
    if not tot:
        return {}
    return _capped({c: v / tot for c, v in raw.items()}, cap)


def est_amounts(cx: HP.Ctx, key: str, adds: list[str], sel: list[str], d: str, i: int | None,
                aum: float | None, cap: float, info: dict | None = None) -> dict[str, list]:
    """{代號: [預估買進(億), 占 20 日均成交金額天數]}＝權重 × 規模（預估成分股集合裡的權重）。"""
    if not aum:
        return {}
    w = index_weights(cx, key, sorted(set(sel) | set(adds)), d, cap, info)
    out = {}
    for c in adds:
        if c not in w:
            continue
        amt = w[c] * aum
        adv = cx.H.adv(c, i, 20) if i is not None else None
        out[c] = [round(amt, 1), round(amt * 1e8 / adv, 2) if adv else None]
    return out


def capw(key: str, review: str) -> float:
    """單檔權重上限：00919 2025-05 起 15%（之前 10%）、00929 10%。"""
    return 0.15 if key == "tip_hd" and review >= "2025-05" else 0.10


def events(D, H, cfg: dict, industry: dict, keys=KEYS, leads=LEADS) -> list[dict]:
    """逐次審核：時間錨點、官方名單、審核前成分股、各提前天數的預估名單與預估被動買盤。"""
    cx = HP.Ctx(D, H, industry)
    out = []
    for k in keys:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        cons = HS.constituents(ix)
        for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or ""):
            if h.get("kind") == "季審" or not h.get("adds"):
                continue
            ba = cons.get(h.get("review"))
            a = HS.anchors(D, h, k)
            if not ba or not a or not h.get("cutoff"):
                continue
            iC = TS._on_or_before(D, h["cutoff"])
            if iC is None or iC - max(leads) < 60 or a["T1"] >= D.T:
                continue
            cw = capw(k, h.get("review") or "")
            preds = {}
            for L in leads:
                d = D.cal[iC - L]
                p = HP.predict(cx, k, h, ba[0], d)
                if not p:
                    continue
                aum = h.get("aum") or HS.aum_at(ix, d)
                preds[L] = {"d": d, "adds": p["adds"],
                            "est": est_amounts(cx, k, p["adds"], p["sel"], d, iC - L, aum, cw, p.get("info"))}
            if 0 not in preds:
                continue
            dC = D.cal[iC]
            aum = h.get("aum") or HS.aum_at(ix, dC)
            act = [c for c in h.get("adds") or [] if len(c) == 4 and c.isdigit()]
            # 完美預知：官方名單＋同一套估法（成分股＝官方審核後名單）
            p0 = HP.predict(cx, k, h, ba[0], dC) or {}
            truth = est_amounts(cx, k, act, sorted(ba[1]), dC, iC, aum, cw, p0.get("info"))
            stays = sorted(c for c in ba[0] & ba[1] if len(c) == 4 and c.isdigit())
            iN = TS._on_or_before(D, h.get("announce")) if h.get("announce") else None
            out.append({"key": k, "etf": (ix.get("etfs") or [""])[0], "review": h.get("review"),
                        "C": iC, "A": a["A"], "N": iN, "T0": a["T0"], "T1": a["T1"], "t86": a["t86"], "aum": aum,
                        "act": act, "stays": stays, "preds": preds, "truth": truth})
    return out


def _ctrl(P, stays: list[str], i0: int, o0: bool, i1: int, o1: bool) -> float | None:
    """留任成分股同一時窗的平均報酬（不扣成本，小數）。"""
    xs = []
    for c in stays:
        p0, p1 = P.px(c, i0, o0), P.px(c, i1, o1)
        if p0 and p1:
            xs.append(p1 / p0 - 1)
    return statistics.mean(xs) if len(xs) >= 5 else None


def simulate(ev: dict, P, lead: int, th: float, exit_at: str = "T1", perfect: bool = False) -> list[dict]:
    """一次審核照規則做出來的交易。perfect＝完美預知（官方名單、截止日隔天開盤買）。"""
    C, A, T0, T1 = ev["C"], ev["A"], ev["T0"], ev["T1"]
    i_out = T1 if exit_at == "T1" else T0 - 1
    act = set(ev["act"])

    def pick(est: dict) -> list[str]:
        return [c for c, v in est.items() if v[1] is not None and v[1] >= th]

    if perfect:
        legs = {c: C + 1 for c in pick(ev["truth"])}
        sells: dict[str, tuple[int, bool, str]] = {}
    else:
        pr = ev["preds"].get(lead)
        if not pr:
            return []
        i_buy = C - lead + 1
        legs = {c: i_buy for c in pick(pr["est"])}
        sells = {}
        if lead > 0:                                          # 截止日校正
            fin = set(pick(ev["preds"][0]["est"]))
            for c in list(legs):
                if c not in fin:
                    sells[c] = (C + 1, True, "截止日名單沒有")
            for c in fin:
                legs.setdefault(c, C + 1)
        for c in legs:                                        # 官方沒有納入 → 公告後第一個交易日開盤賣
            if c not in act and c not in sells:
                sells[c] = (A + 1, True, "官方沒有納入")
    out = []
    for c, i0 in sorted(legs.items()):
        i1, o1, why = sells.get(c, (i_out, False, "被動買盤最後一天" if exit_at == "T1" else "被動買盤開始前一天"))
        if i1 > i_out:                                        # 出場點比官方公告還早（被動買盤開始前就賣）
            i1, o1 = i_out, False
        if i1 < i0 or (i1 == i0 and o1):
            continue
        r, x = P.ret(c, i0, True, i1, o1)
        if r is None:
            continue
        cb = _ctrl(P, ev["stays"], i0, True, i1, o1)
        est = (ev["truth"] if perfect else ev["preds"][lead]["est"]).get(c) or (ev["preds"][0]["est"].get(c) if not perfect else None) or [None, None]
        out.append({"c": c, "key": ev["key"], "review": ev["review"], "d": P.D.cal[i0], "i0": i0, "i1": i1,
                    "ent": P.D.cal[i0], "out": P.D.cal[i1], "why": why, "st": "closed",
                    "r": round(r * 100, 2), "x": None if x is None else round(x * 100, 2),
                    "xc": None if cb is None else round((r - cb) * 100, 2),
                    "amt": est[0], "days": est[1], "hit": c in act})
    return out


def simulate_ann(ev: dict, P, k: int, th: float, perfect: bool = False) -> list[dict]:
    """（看完結果後新增的變體）公告日前 k 個交易日開盤買「截止日預估名單」裡預估被動買盤 ≥ th 日量的 →
    被動買盤最後一天收盤賣；官方沒有納入的公告後第一個交易日開盤賣。公告日＝依規則事先排定（00919／00929 有時
    公告前 2～3 天就開始買，所以 k 取 2～5）。"""
    N, T1 = ev.get("N"), ev["T1"]
    if N is None:
        return []
    act = set(ev["act"])
    est = ev["truth"] if perfect else (ev["preds"].get(0) or {}).get("est") or {}
    i0 = N - k
    if i0 <= ev["C"]:
        return []
    out = []
    for c, (amt, days) in sorted(est.items()):
        if days is None or days < th:
            continue
        i1, o1, why = (T1, False, "被動買盤最後一天") if c in act else (N + 1, True, "官方沒有納入")
        if i1 < i0 or (i1 == i0 and o1):
            continue
        r, x = P.ret(c, i0, True, i1, o1)
        if r is None:
            continue
        cb = _ctrl(P, ev["stays"], i0, True, i1, o1)
        out.append({"c": c, "key": ev["key"], "review": ev["review"], "d": P.D.cal[i0], "i0": i0, "i1": i1,
                    "ent": P.D.cal[i0], "out": P.D.cal[i1], "why": why, "st": "closed",
                    "r": round(r * 100, 2), "x": None if x is None else round(x * 100, 2),
                    "xc": None if cb is None else round((r - cb) * 100, 2), "amt": amt, "days": days, "hit": c in act})
    return out


def per_review(trades: list[dict]) -> list[dict]:
    by: dict = {}
    for t in trades:
        by.setdefault((t["key"], t["review"]), []).append(t)
    out = []
    for (k, rv), ts in sorted(by.items(), key=lambda kv: min(t["d"] for t in kv[1])):
        xs = [t["x"] for t in ts if t["x"] is not None]
        cs = [t["xc"] for t in ts if t["xc"] is not None]
        out.append({"key": k, "review": f"{k}:{rv}", "d": min(t["d"] for t in ts), "n": len(ts),
                    "hit": sum(1 for t in ts if t["hit"]),
                    "r": statistics.mean(t["r"] for t in ts), "x": statistics.mean(xs) if xs else None,
                    "xc": statistics.mean(cs) if cs else None})
    return out


def grid(evs: list[dict], P) -> list[dict]:
    """提前天數 × 門檻 × 出場點：每格的每次審核平均（不挑參數，只看方向穩不穩）。"""
    from . import advice
    rows = []
    for ex in EXITS:
        for th in THS:
            for L in LEADS:
                trs = [t for ev in evs for t in simulate(ev, P, L, th, ex)]
                u = per_review(trs)
                s = advice.score(u, event=True) if u else {"n": 0}
                cs = [x["xc"] for x in u if x["xc"] is not None]
                rows.append({"exit": ex, "th": th, "lead": L, "n": s.get("n", 0), "trades": len(trs),
                             "avg": s.get("avg"), "med": s.get("med"), "x": s.get("x"), "ci": s.get("ci"),
                             "kx": s.get("kx"), "kwin": s.get("kwin"), "lo": s.get("lo"),
                             "xc": round(statistics.mean(cs), 2) if cs else None,
                             "kc": sum(1 for v in cs if v > 0), "grade": s.get("grade")})
    return rows


def run(D, H, cfg: dict, industry: dict) -> dict:
    from . import advice
    evs = events(D, H, cfg, industry)
    P = HS._px(D, H)
    main = [t for ev in evs for t in simulate(ev, P, MAIN["lead"], MAIN["th"], MAIN["exit"])]
    perf = [t for ev in evs for t in simulate(ev, P, 0, MAIN["th"], MAIN["exit"], perfect=True)]
    small = [t for ev in evs for t in simulate(ev, P, 0, 0.0, MAIN["exit"]) if (t["days"] or 0) < MAIN["th"]]
    acc = []
    for ev in evs:
        for L, pr in sorted(ev["preds"].items()):
            big = {c for c, v in pr["est"].items() if v[1] is not None and v[1] >= MAIN["th"]}
            act_big = {c for c, v in ev["truth"].items() if v[1] is not None and v[1] >= MAIN["th"]}
            acc.append({"key": ev["key"], "review": ev["review"], "lead": L, "pred": len(pr["adds"]),
                        "hit": len(set(pr["adds"]) & set(ev["act"])), "act": len(ev["act"]),
                        "pred_big": len(big), "hit_big": len(big & set(ev["act"])), "act_big": len(act_big)})
    return {"events": [{k: v for k, v in ev.items() if k not in ("preds", "stays")} for ev in evs],
            "main": main, "main_rev": per_review(main), "main_score": advice.score(per_review(main), event=True),
            "perfect_rev": per_review(perf), "perfect_score": advice.score(per_review(perf), event=True),
            "small_rev": per_review(small), "small_score": advice.score(per_review(small), event=True),
            "acc": acc, "grid": grid(evs, P), "spec": MAIN}


# —— 頁面用摘要（指數頁「高股息：依編製規則提前卡位」＋策略頁高股息段）

VARS = [  # (代號, 說明, 參數)；出場一律被動買盤最後一天收盤（官方沒納入的公告後第一個交易日開盤賣）
    ("main", "截止日收盤選股、隔天開盤買", {"kind": "sim", "lead": 0}),
    ("early20", "截止日前 20 個交易日先買、截止日校正", {"kind": "sim", "lead": 20}),
    ("ann3", "公告前 3 個交易日開盤買", {"kind": "ann", "k": 3}),
    ("perf_main", "完美預知名單・截止日隔天開盤買", {"kind": "sim", "lead": 0, "perfect": True}),
    ("perf_ann3", "完美預知名單・公告前 3 個交易日買", {"kind": "ann", "k": 3, "perfect": True}),
]
WINS = [("pre20", "截止日前 20 日"), ("c_t0", "截止日 → 被動買盤開始前"), ("in", "被動買盤期間"), ("post10", "買盤結束後 10 日")]
BKS = [("s", "<3 日", 0.0, 3.0), ("m", "3～10 日", 3.0, 10.0), ("l", "≥10 日", 10.0, 1e9)]


def _var(evs: list[dict], P, spec: dict, th: float) -> list[dict]:
    out = []
    for ev in evs:
        if spec["kind"] == "ann":
            out += simulate_ann(ev, P, spec["k"], th, spec.get("perfect", False))
        else:
            out += simulate(ev, P, spec["lead"], th, "T1", spec.get("perfect", False))
    return out


def size_windows(evs: list[dict], P) -> list[list[dict]]:
    """完美預知名單（官方納入股、事前估計的被動買盤天數分組）在各時段的表現，每筆等權平均（對大盤、對留任成分股，不扣成本）。"""
    acc: dict = {}
    for ev in evs:
        C, T0, T1 = ev["C"], ev["T0"], ev["T1"]
        wins = {"pre20": (C - 19, True, C, False), "c_t0": (C + 1, True, T0 - 1, False),
                "in": (T0 - 1, False, T1, False), "post10": (T1, False, min(T1 + 10, P.D.T - 1), False)}
        for c, (amt, days) in ev["truth"].items():
            if days is None:
                continue
            bk = next(b[0] for b in BKS if b[2] <= days < b[3])
            for wn, (i0, o0, i1, o1) in wins.items():
                if i0 < 0 or i1 >= P.D.T or i1 <= i0:
                    continue
                p0, p1 = P.px(c, i0, o0), P.px(c, i1, o1)
                b0, b1 = P.bx(i0, o0), P.bx(i1, o1)
                if not (p0 and p1 and b0 and b1):
                    continue
                r = p1 / p0 - 1
                cb = _ctrl(P, ev["stays"], i0, o0, i1, o1)
                acc.setdefault((wn, bk), []).append(((r - (b1 / b0 - 1)) * 100, None if cb is None else (r - cb) * 100))
    out = []
    for wn, _ in WINS:
        row = []
        for bk, *_ in BKS:
            xs = acc.get((wn, bk)) or []
            cs = [c for _, c in xs if c is not None]
            row.append({"n": len(xs), "x": round(statistics.mean(x for x, _ in xs), 2) if xs else None,
                        "xc": round(statistics.mean(cs), 2) if cs else None,
                        "pos": sum(1 for c in cs if c > 0), "nc": len(cs)})
        out.append(row)
    return out


def page_data(th: float = MAIN["th"]) -> dict:
    """自己載入五年日線（Data(long=True)）重算；約十幾秒。新的審核結果寫進設定檔後自動納入。"""
    import json
    from pathlib import Path
    from . import advice, analyze
    from .hdmodel import HD
    root = Path(__file__).resolve().parents[2]
    D = analyze.Data(long=True)
    H = HD(D)
    cfg = json.loads((root / "config" / "index_reviews.json").read_text(encoding="utf-8"))
    try:
        ind = json.loads((root / "data" / "stock_industry.json").read_text(encoding="utf-8")).get("industry") or {}
    except Exception:                                     # noqa: BLE001
        ind = {}
    evs = events(D, H, cfg, ind)
    P = HS._px(D, H)
    vs, revs = [], {}
    for k, lbl, spec in VARS:
        trs = _var(evs, P, spec, th)
        u = per_review(trs)
        sc = advice.score(u, event=True) if u else {"n": 0}
        cs = [x["xc"] for x in u if x["xc"] is not None]
        vs.append({"k": k, "lbl": lbl, "perfect": bool(spec.get("perfect")), "trades": len(trs),
                   "hit": sum(1 for t in trs if t["hit"]),
                   **{kk: sc.get(kk) for kk in ("n", "event", "avg", "med", "x", "xmed", "ci", "kx", "nx", "kwin", "lo",
                                                "grade", "label", "why")},
                   "xc": round(statistics.mean(cs), 2) if cs else None, "kc": sum(1 for v in cs if v > 0), "nc": len(cs)})
        if k in ("main", "perf_ann3"):
            revs[k] = [[x["review"].split(":")[0], x["review"].split(":")[1], x["n"], x["hit"], round(x["r"], 2),
                        None if x["x"] is None else round(x["x"], 2), None if x["xc"] is None else round(x["xc"], 2)]
                       for x in u]
    acc = []
    for ev in evs:
        a = {"key": ev["key"], "review": ev["review"], "act": len(ev["act"])}
        for L in (0, 10, 20):
            pr = ev["preds"].get(L)
            if pr:
                a[str(L)] = [len(set(pr["adds"]) & set(ev["act"])), len(pr["adds"])]
        acc.append(a)
    return {"th": th, "n": len(evs), "d0": D.cal[evs[0]["C"]][:7] if evs else None,
            "d1": D.cal[evs[-1]["C"]][:7] if evs else None,
            "events": [[ev["key"], ev["review"], ev["aum"] and round(ev["aum"]), len(ev["act"])] for ev in evs],
            "vars": vs, "rev": revs, "acc": acc, "win": size_windows(evs, P),
            "wins": [w[1] for w in WINS], "bks": [b[1] for b in BKS]}


if __name__ == "__main__":                  # 研究用：python3 -m arm.lab.hdpre [--long]
    import json
    import sys
    from pathlib import Path
    from . import analyze
    from .hdmodel import HD
    root = Path(__file__).resolve().parents[2]
    D = analyze.Data(long="--long" in sys.argv)
    H = HD(D)
    cfg = json.loads((root / "config" / "index_reviews.json").read_text(encoding="utf-8"))
    ind = json.loads((root / "data" / "stock_industry.json").read_text(encoding="utf-8")).get("industry") or {}
    R = run(D, H, cfg, ind)
    print("事件：", [(e["key"], e["review"], e["aum"]) for e in R["events"]])
    for lab, k in (("主規格", "main"), ("完美預知", "perfect"), ("小量（<門檻）", "small")):
        s = R[k + "_score"]
        print(f"\n{lab}：{s.get('n')} 次｜每次平均 {s.get('avg')}％、中位 {s.get('med')}％、{s.get('kwin')} 次賺｜"
              f"超額 {s.get('x')}％ CI {s.get('ci')}、{s.get('kx')} 次贏大盤｜評級 {s.get('grade')} {s.get('why')}")
        for u in R[k + "_rev"]:
            print(f"   {u['review']}: {u['n']} 檔（中 {u['hit']}）報酬 {u['r']:.2f}％、對大盤 {u['x'] if u['x'] is None else round(u['x'], 2)}％、"
                  f"對留任 {u['xc'] if u['xc'] is None else round(u['xc'], 2)}％")
    print("\n名單準度（提前天數）：")
    for a in R["acc"]:
        print(f"   {a['key']} {a['review']} L={a['lead']}: 預估 {a['pred']} 中 {a['hit']}／實際 {a['act']}｜"
              f"大量（≥{MAIN['th']} 日）預估 {a['pred_big']} 中 {a['hit_big']}／實際 {a['act_big']}")
    print("\n掃描（出場、門檻、提前天數 → 次數、每次平均、超額、對留任）：")
    for g in R["grid"]:
        print(f"   {g['exit']} th={g['th']:>4} L={g['lead']:>2}: n={g['n']:>2} 筆={g['trades']:>3} 平均 {g['avg']}％ 超額 {g['x']}％ "
              f"CI {g['ci']} 對留任 {g['xc']}％（{g['kc']} 次正）評級 {g['grade']}")
