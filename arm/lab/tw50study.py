"""籌碼雷達：臺灣50 換股研究——公告前能不能預測、什麼時候進場、哪些納入股漲最多。

2026-10-14 使用者：「0050 那個交易不能在公告前就先預估可能納進去的嗎……也幫我去歸因哪些股票會漲最多，
是納入張數嗎還是市值還是什麼」。樣本＝`config/index_reviews.json` 的歷次官方結果（2024-12 起，價量資料只到兩年前）。
頁面的數字全部由這裡即時重算，不寫死：

  · 預測準度：用「資料截止日」的上市普通股總市值排名重跑規則（排除截止日時還沒上市的股票），
    對照官方名單；另看截止日前 5／10／20 個交易日就預測會差多少。
  · 進場時點：同一批納入股，比較「截止日隔天開盤／公告日收盤／公告後開盤」進場、「生效前一天／生效日」出場。
  · 歸因：截止前 40 日漲幅、估計權重、被動買盤（張數、占日均量天數）、日週轉率，對公告後漲幅的
    Spearman 相關；另看同一次審核裡漲最多的是不是「漲勢最強」或「權重最大」的那檔。
  · 提前幾天建倉：同一套「最多 4 檔、截止日校正＋補位」規則，從截止前 35 個交易日到截止日逐日回測（early_scan）。

口徑：進場用開盤或收盤（各列寫明）、出場用收盤；報酬扣來回成本 0.585%；超額＝減去加權指數同一時窗。
個股生效日可能延後（處置股依基本規則 3.4.1 延後，例：南亞科 2025-12-30）→ 以 `eff_override` 為準。
被動買盤為估計：0050＋006208 規模 ÷ 前 50 大市值＝被動持有比例，乘上發行股數（不含自由流通調整）。
"""
from __future__ import annotations

import math
import statistics
from datetime import date, timedelta

from . import indexes as IX

COST = 0.00585
MOM_N = 40
LEADS = (5, 10, 20)


def _on_or_before(D, d: str | None) -> int | None:
    if not d:
        return None
    i = None
    for k, x in enumerate(D.cal):
        if x <= d:
            i = k
        else:
            break
    return i


def _pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _spearman(a: list, b: list) -> tuple[float | None, int]:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if n < 6:
        return None, n

    def rk(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:                                   # 同值取平均名次
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    ra, rb = rk([p[0] for p in pairs]), rk([p[1] for p in pairs])
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return (round(cov / va / vb, 2) if va and vb else None), n


class _Px:
    """價格與指數的小工具（進場可用開盤或收盤、出場用收盤或開盤）。"""

    def __init__(self, D):
        self.D = D
        self.idx = D.taiex()
        self.io = D.taiex_open()
        self.cache: dict[str, dict] = {}

    def s(self, code):
        if code not in self.cache:
            self.cache[code] = self.D.series(code)
        return self.cache[code]

    def px(self, code, i, opn):
        s = self.s(code)
        if i is None or i < 0 or i >= self.D.T:
            return None
        return (s["o"][i] or None) if opn else s["c"][i]

    def bx(self, i, opn):
        if i is None or i < 0 or i >= self.D.T:
            return None
        if opn:
            return self.io[i] or (self.idx[i - 1] if i > 0 else None)
        return self.idx[i]

    def ret(self, code, i0, o0, i1, o1):
        """(扣成本報酬, 超額)；資料不足回 (None, None)。"""
        p0, p1 = self.px(code, i0, o0), self.px(code, i1, o1)
        if not p0 or not p1:
            return None, None
        r = p1 / p0 - 1 - COST
        b0, b1 = self.bx(i0, o0), self.bx(i1, o1)
        x = r - (b1 / b0 - 1) if b0 and b1 else None
        return r, x


def _aum_at(points: list[dict], cur: dict, d: str) -> float | None:
    """0050＋006208 規模（億）：設定檔已知點＋今日持股市值，逐檔線性內插（估計）。"""
    tot = 0.0
    for etf in ("0050", "006208"):
        pts = sorted((p["date"], p[etf]) for p in points if p.get(etf))
        if cur.get(etf):
            pts.append((cur["date"], cur[etf]))
        pts.sort()
        if not pts:
            return None
        if d <= pts[0][0]:
            v = pts[0][1]
        elif d >= pts[-1][0]:
            v = pts[-1][1]
        else:
            v = None
            for (d0, a0), (d1, a1) in zip(pts, pts[1:]):
                if d0 <= d <= d1:
                    t0, t1, t = (date.fromisoformat(x).toordinal() for x in (d0, d1, d))
                    v = a0 + (a1 - a0) * (t - t0) / max(t1 - t0, 1)
                    break
        tot += v or 0
    return tot or None


def events(D, cfg: dict) -> list[dict]:
    """逐次審核：日期索引、審核前成分股、截止日預測、各前置天數預測、每檔納入股的報酬與因子。"""
    ix = (cfg.get("indexes") or {}).get("tw50") or {}
    issued = IX._issued_twse(D)
    tot_now, h0050 = IX._etf_equity(D, "0050")
    tot_208, _ = IX._etf_equity(D, "006208")
    cur = {"date": D.cal[-1] if D.cal else "", "0050": tot_now / 1e8 if tot_now else None,
           "006208": tot_208 / 1e8 if tot_208 else None}
    listed = IX.listing_dates(ix)
    pres = IX.tw50_pre_sets(D, ix, h0050)
    P = _Px(D)
    out = []
    for h in sorted(ix.get("history") or [], key=lambda h: h.get("effective") or ""):
        rv = h.get("review")
        pre = pres.get(rv)
        ic, ia, ie = (_on_or_before(D, h.get(k)) for k in ("cutoff", "announce", "effective"))
        if not pre or ic is None or ia is None or ie is None:
            continue
        got = IX.tw50_predict_at(D, h, pre, issued, listed)
        if not got:
            continue
        cd, pa, pd = got
        caps = IX.caps_at(D, cd, issued)
        skip = IX.not_listed(caps, pre, listed, h.get("cutoff") or cd)
        ranked = [r for r in caps if r[0] not in skip]
        rank = {c: i + 1 for i, (c, _, _) in enumerate(ranked)}
        top50 = sum(v for _, v, _ in ranked[:50])
        aum = _aum_at(ix.get("aum") or [], cur, D.cal[ic])
        s_t = aum * 1e8 / top50 if aum and top50 else None
        leads = {}
        for k in LEADS:
            if ic - k >= 0:
                g = IX.tw50_predict_at(D, h, pre, issued, listed, D.cal[ic - k])
                if g:
                    leads[k] = g[1]
        mom = {c: IX.momentum(D, c, ic, MOM_N) for c in set(h.get("adds") or []) | set(pa)}
        top = IX.top_half(h.get("adds") or [], mom)
        adds = []
        for c in h.get("adds") or []:
            je = _on_or_before(D, (h.get("eff_override") or {}).get(c) or h["effective"])
            s = P.s(c)
            px, sh = s["c"][ic], issued.get(c)
            vs = [x for x in s["v"][max(ic - 19, 0):ic + 1] if x]
            adv = sum(vs) / len(vs) if vs else None
            dem = s_t * sh if s_t and sh else None
            row = {"c": c, "n": D.names.get(c, c), "rank": rank.get(c),
                   "cap": round(px * sh / 1e8) if px and sh else None,
                   # 估計權重＝市值 ÷ 前 50 大市值（未做自由流通調整）。不用原始市值比較：2026 年市值整體變大、
                   # 那兩次又剛好大漲，原始市值和漲幅的相關會被時間灌高（0.49 → 換成權重只剩 0.1）
                   "w": round(px * sh / top50 * 100, 2) if px and sh and top50 else None,
                   "mom": None if mom.get(c) is None else round(mom[c] * 100, 1),
                   "turn": round(adv / sh * 100, 2) if adv and sh else None,
                   "dem_lots": round(dem / 1000) if dem else None,
                   "dem_days": round(dem / adv, 2) if dem and adv else None,
                   "top": int(c in top), "eff_d": D.cal[je] if je is not None else None}
            # 各時窗（扣成本報酬 r、超額 x）
            for key, (i0, o0, i1, o1) in {
                    "pre": (ic + 1, True, ia, False),            # 截止日隔天開盤 → 公告日收盤
                    "cut": (ic + 1, True, je - 1, False),        # 截止日隔天開盤 → 生效前一天收盤（公告前卡位）
                    "fri": (ia, False, je - 1, False),           # 公告日收盤 → 生效前一天收盤
                    "post": (ia + 1, True, je - 1, False),       # 公告後開盤 → 生效前一天收盤（公告後進場）
                    "eff": (ia + 1, True, je, False),            # 公告後開盤 → 生效日收盤（原官方名單做法）
                    "aft": (je, False, je + 5, False)}.items():  # 生效日收盤 → 5 日後
                if i1 is None or i1 >= D.T or i1 <= i0 - (0 if o0 else 1):
                    row[key] = row[key + "x"] = None
                    continue
                r, x = P.ret(c, i0, o0, i1, o1)
                row[key] = None if r is None else round(r * 100, 2)
                row[key + "x"] = None if x is None else round(x * 100, 2)
            adds.append(row)
        out.append({"review": rv, "cutoff": D.cal[ic], "announce": D.cal[ia], "effective": D.cal[ie],
                    "pred": pa, "pred_del": pd, "act": h.get("adds") or [], "act_del": h.get("dels") or [],
                    "leads": leads, "s": None if s_t is None else round(s_t * 100, 2), "adds": adds})
    return out


def _stat(xs: list) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "avg": round(statistics.mean(xs), 1), "med": round(statistics.median(xs), 1),
            "win": round(sum(1 for x in xs if x > 0) / len(xs) * 100)}


ENTRY = [("cut", "截止日隔天開盤 → 生效前一天收盤", "截止日才買"),
         ("post", "公告後開盤 → 生效前一天收盤", "公告後進場"),
         ("eff", "公告後開盤 → 生效日收盤", "原官方名單做法"),
         ("fri", "公告日收盤（消息出來前）→ 生效前一天收盤", ""),
         ("pre", "截止日隔天開盤 → 公告日收盤", "只抱到公告")]

FACTORS = [("mom", "截止前 40 日漲幅"), ("w", "估計權重"), ("dem_lots", "被動買盤張數"),
           ("dem_days", "被動買盤 ÷ 日均量（天）"), ("turn", "日週轉率")]


def run(D, cfg: dict) -> dict:
    out = _run(D, cfg)
    if out.get("n"):
        try:
            out["early"] = early_scan(D, cfg)
        except Exception as e:                            # noqa: BLE001 —— 掃描壞掉不連累研究頁其他段
            out["early"] = {"err": f"{type(e).__name__}: {e}"}
    return out


def _run(D, cfg: dict) -> dict:
    ev = events(D, cfg)
    rows = [dict(a, review=e["review"]) for e in ev for a in e["adds"]]
    if not rows:
        return {"n": 0}
    # 預測準度：截止日＋前置 5／10／20 個交易日
    acc = []
    tot = sum(len(e["act"]) for e in ev)
    acc.append({"k": 0, "hit": sum(len(set(e["pred"]) & set(e["act"])) for e in ev), "tot": tot,
                "fp": sum(len(set(e["pred"]) - set(e["act"])) for e in ev)})
    for k in LEADS:
        es = [e for e in ev if k in e["leads"]]
        acc.append({"k": k, "hit": sum(len(set(e["leads"][k]) & set(e["act"])) for e in es),
                    "tot": sum(len(e["act"]) for e in es),
                    "fp": sum(len(set(e["leads"][k]) - set(e["act"])) for e in es)})
    # 進場時點表：全部納入股 vs 漲勢前一半（扣成本報酬 %）
    entry = [{"key": k, "lbl": lbl, "tag": tag, "all": _stat([r[k] for r in rows]),
              "top": _stat([r[k] for r in rows if r["top"]]),
              "all_x": _stat([r[k + "x"] for r in rows]), "top_x": _stat([r[k + "x"] for r in rows if r["top"]])}
             for k, lbl, tag in ENTRY]
    # 歸因：因子對「公告後進場」超額的等級相關；同次審核內前一半 vs 後一半
    fac = []
    for k, lbl in FACTORS:
        rho, n = _spearman([r[k] for r in rows], [r["postx"] for r in rows])
        rho2, _ = _spearman([r[k] for r in rows], [r["cutx"] for r in rows])
        fac.append({"k": k, "lbl": lbl, "rho": rho, "rho_cut": rho2, "n": n})
    within = []
    for e in ev:
        if len(e["adds"]) < 2:
            continue
        hi = [a["postx"] for a in e["adds"] if a["top"] and a["postx"] is not None]
        lo = [a["postx"] for a in e["adds"] if not a["top"] and a["postx"] is not None]
        best = max((a for a in e["adds"] if a["postx"] is not None), key=lambda a: a["postx"], default=None)
        strongest = max((a for a in e["adds"] if a["mom"] is not None), key=lambda a: a["mom"], default=None)
        heavy = max((a for a in e["adds"] if a["w"] is not None), key=lambda a: a["w"], default=None)
        within.append({"review": e["review"], "n": len(e["adds"]),
                       "hi": round(statistics.mean(hi), 1) if hi else None,
                       "lo": round(statistics.mean(lo), 1) if lo else None,
                       "best": best and best["n"], "best_x": best and best["postx"],
                       "strongest": strongest and strongest["n"], "strongest_x": strongest and strongest["postx"],
                       "heavy": heavy and heavy["n"], "heavy_x": heavy and heavy["postx"], "heavy_w": heavy and heavy["w"],
                       "same": bool(best and strongest and best["c"] == strongest["c"]),
                       "heavy_same": bool(best and heavy and best["c"] == heavy["c"])})
    return {"n": len(rows), "n_rev": len(ev), "first": ev[0]["review"], "last": ev[-1]["review"],
            "acc": acc, "entry": entry, "fac": fac, "within": within,
            "rows": [[r["review"], r["c"], r["n"], r["rank"], r["w"], r["mom"], r["turn"], r["dem_lots"],
                      r["dem_days"], r["top"], r["pre"], r["post"], r["postx"], r["cut"], r["eff"], r["aft"]]
                     for r in rows],
            "rev": [[e["review"], e["cutoff"], e["announce"], e["effective"], e["s"],
                     [D.names.get(c, c) for c in e["act"]], [D.names.get(c, c) for c in e["pred"]]] for e in ev]}


# ── 策略版本 ─────────────────────────────────────────────────────────────────────────────
# early＝提前卡位（2026-10-14 使用者：「不用一檔可以 3-4 檔，然後能越早卡位越好」）：資料截止日前第 EARLY_K 個
#      交易日收盤，從「當天排名的預估納入股＋第 41～EARLY_W 名非成分股」挑 40 日漲最多的 EARLY_N 檔，隔天開盤買；
#      截止日收盤名單沒有的 → 隔天開盤賣；名單上有、還沒買到的 → 依漲勢補到 EARLY_N 檔（隔天開盤買）；
#      全部抱到生效前一天收盤（官方沒納入 → 公告後第一天開盤賣）。
#      EARLY_K＝25 是逐日回測（0～35 日）後選的：18～25 日每次平均都在 +9%～+12%、8 次賺 7 次；
#      30 日以上最差一次跌到 −15% 以上，再早就會碰到上一次審核還沒生效。看過資料才定的，樣本內只能參考。
# post＝公告後進場：官方公告的納入股裡挑漲勢前一半（截止日的 40 日漲幅），公告後第一個交易日開盤買、生效前一天收盤賣。
# 兩版都不設停損——進出日期事先就定好，這是事件型交易。
# （原「公告前卡位・漲勢前一半」＝截止日隔天開盤進，同日改為上面的 early，沒有任何前瞻交易。）
EARLY_K, EARLY_N, EARLY_W = 25, 4, 45


def td_shift(d: str, n: int) -> str:
    """d 往後（n>0）或往前（n<0）第 |n| 個台股交易日（週末＋證交所官方休市表；表未涵蓋的平日視為開市）。"""
    from .. import twholidays
    years = twholidays.load()
    x = date.fromisoformat(d)
    step, k = (1 if n > 0 else -1), abs(n)
    while k:
        x += timedelta(days=step)
        if x.weekday() < 5 and twholidays.is_closed(x, years) is not True:
            k -= 1
    return x.isoformat()


def _pre_next(D, eff: str | None) -> set:
    """下一次審核的「審核前成分股」＝生效日之前最後一次 0050 揭露（生效日當天已換完）。"""
    snap = set()
    for d, doc in D.pos:
        ent = (doc.get("etf") or {}).get("0050")
        if ent and (not eff or d < eff):
            snap = {c for c in (ent.get("h") or {}) if len(c) == 4 and c.isdigit()}
    return snap


class _Ctx:
    """排名快取（同一天的市值排名只算一次）與審核前成分股、上市日。"""

    def __init__(self, D, cfg: dict):
        self.D = D
        self.ix = (cfg.get("indexes") or {}).get("tw50") or {}
        self.issued = IX._issued_twse(D)
        _, self.h0050 = IX._etf_equity(D, "0050")
        self.listed = IX.listing_dates(self.ix)
        self.pres = IX.tw50_pre_sets(D, self.ix, self.h0050)
        self.P = _Px(D)
        self._caps: dict[str, list] = {}

    def ranked(self, d: str, pre: set, cutoff: str) -> list:
        if d not in self._caps:
            self._caps[d] = IX.caps_at(self.D, d, self.issued)
        caps = self._caps[d]
        skip = IX.not_listed(caps, pre, self.listed, cutoff)
        return [r for r in caps if r[0] not in skip]

    def pool(self, d: str, pre: set, cutoff: str, watch: int = EARLY_W):
        """d 日收盤排名的預估納入股（含遞補）＋第 41～watch 名非成分股，依排名順；資料不足回 (None, [])。"""
        cd = IX._nearest_mkt_on_or_before(self.D, d)
        if not cd or not pre or len(pre) < 45:
            return None, []
        ranked = self.ranked(cd, pre, cutoff)
        if len(ranked) < 200:
            return None, []
        adds, _ = IX.tw50_select(ranked, pre)
        near = [c for c, _, _ in ranked[IX.TW50_IN:watch] if c not in pre and c not in adds] if watch else []
        return cd, adds + near

    def mom(self, c: str, t: int | None, n: int = MOM_N) -> float | None:
        if t is None or t < n:
            return None
        cs = self.P.s(c)["c"]
        return cs[t] / cs[t - n] - 1 if cs[t] and cs[t - n] else None

    def top(self, codes: list, t: int | None, n: int) -> list:
        """依 t 日的 40 日漲幅由高到低取前 n 檔（沒有漲幅的排最後、維持原順序）。"""
        m = {c: self.mom(c, t) for c in codes}
        return sorted(codes, key=lambda c: -(m[c] if m[c] is not None else -9e9))[:n]


def early_picks(ctx: _Ctx, p: dict, pre: set, k: int = EARLY_K, n: int = EARLY_N) -> dict:
    """提前卡位：截止前第 k 個交易日的選股＋截止日補位。k＝0 即截止日當天（只從截止日名單挑）。"""
    D = ctx.D
    last = D.cal[-1] if D.cal else ""
    e_sig = td_shift(p["cutoff"], -k) if k else p["cutoff"]
    out = {"e_sig": e_sig, "e_in": td_shift(e_sig, 1), "e_t": None, "pick_e": [], "pick_t": []}
    if last >= e_sig and pre:
        if k:
            cd, pool = ctx.pool(e_sig, pre, p["cutoff"])
        else:
            cd, pool = (IX._nearest_mkt_on_or_before(D, e_sig), list(p["pred"] or []))
        if cd:                                       # 候選是空的也算到了建倉日（之後照樣截止日補位）
            out["e_t"] = D.ix.get(cd)
            out["pick_e"] = ctx.top(pool, out["e_t"], n) if pool else []
    if p["frozen"] and p["pred"]:
        kept = [c for c in out["pick_e"] if c in p["pred"]]
        rest = [c for c in ctx.top(list(p["pred"]), p["ic"], len(p["pred"])) if c not in out["pick_e"]]
        out["pick_t"] = rest[:max(0, n - len(kept))]
    return out


def plans(D, cfg: dict, ctx: _Ctx | None = None) -> list[dict]:
    """歷次＋下一次審核的交易計畫：提前卡位名單（截止前選股＋截止日補位）、截止日預測名單、官方名單與漲勢前一半、各版本進出日期。"""
    ctx = ctx or _Ctx(D, cfg)
    ix, issued, listed = ctx.ix, ctx.issued, ctx.listed
    hs = sorted((h for h in ix.get("history") or [] if h.get("cutoff") and h.get("effective")),
                key=lambda h: h["effective"])
    items = [(h, ctx.pres.get(h.get("review")), True) for h in hs]
    nxt = ix.get("next") or {}
    if nxt.get("cutoff") and nxt.get("effective") and nxt.get("review") not in {h.get("review") for h in hs}:
        items.append((nxt, _pre_next(D, nxt.get("effective")), False))
    last = D.cal[-1] if D.cal else ""
    out = []
    for h, pre, official in items:
        cut, ann, eff = h["cutoff"], h.get("announce"), h["effective"]
        effo = h.get("eff_override") or {}
        p = {"review": h.get("review"), "cutoff": cut, "announce": ann, "effective": eff,
             "official": official, "status": h.get("status"), "frozen": last >= cut,
             "a_in": td_shift(cut, 1), "b_in": td_shift(ann, 1) if ann else None, "out": td_shift(eff, -1),
             "out_c": {c: td_shift(v, -1) for c, v in effo.items() if v}, "pred": None,
             "act": (h.get("adds") or []) if official else None, "pick_b": [], "mom": {},
             "act_del": (h.get("dels") or []) if official else None, "pred_del": None, "rank": {}, "pick_now": []}
        cd = IX._nearest_mkt_on_or_before(D, cut) if p["frozen"] else None
        ic = D.ix.get(cd) if cd else None
        p["ic"] = ic
        if ic is not None and pre:
            got = IX.tw50_predict_at(D, h, pre, issued, listed)
            if got:
                p["pred"], p["pred_del"] = got[1], got[2]
        p.update(early_picks(ctx, p, pre))
        if p["e_t"] is None and not p["frozen"] and pre and last:      # 還沒到建倉日：用最新一天試算（預覽）
            cdn, pool = ctx.pool(last, pre, cut)
            if pool:
                p["pick_now"] = ctx.top(pool, D.ix.get(cdn), EARLY_N)
        codes = set(p["pred"] or []) | set(p["act"] or []) | set(p["pick_e"]) | set(p["pick_now"])
        rd = cd or IX._nearest_mkt_on_or_before(D, last)          # 截止後看截止日排名、之前看最新排名
        if rd and codes and pre:
            rk = {c: i + 1 for i, (c, _, _) in enumerate(ctx.ranked(rd, pre, cut))}
            p["rank"] = {c: rk.get(c) for c in codes}
        p["mom"] = {c: ctx.mom(c, ic) for c in codes} if ic is not None else {}
        t_e = p["e_t"] if p["e_t"] is not None else D.ix.get(IX._nearest_mkt_on_or_before(D, last) or "")
        p["mom_e"] = {c: ctx.mom(c, t_e) for c in set(p["pick_e"]) | set(p["pick_now"])}
        byrank = lambda xs: sorted(xs, key=lambda c: -(p["mom"].get(c) if p["mom"].get(c) is not None else -9e9))
        if p["act"]:
            p["pick_b"] = byrank(IX.top_half(p["act"], p["mom"]))
        out.append(p)
    return out


def _first_after(D, d: str) -> int | None:
    return next((i for i, x in enumerate(D.cal) if x > d), None)


def _trade(D, P: _Px, c: str, i0: int | None, ent_d: str, out_d: str, out_open: bool, why: str, base: dict) -> dict:
    """單筆：i0 開盤進場；out_d（交易日）收盤出場（out_open＝開盤出）。資料還沒到進場日＝待進場、還沒到出場日＝持有中。"""
    last = D.cal[-1] if D.cal else ""
    if i0 is None or last < ent_d:
        return {**base, "st": "cand", "ent": ent_d, "out": out_d}
    s = P.s(c)
    p0 = s["o"][i0]
    if not p0:
        return {**base, "st": "skip", "why": "進場日無開盤價"}
    from .backtest import exit_day, limit_up_open
    k = 0
    while limit_up_open(s, i0):                           # 回測紀律 D1：漲停開盤買不到，順延到下一個交易日開盤，最多 3 天
        k += 1
        if k > 3 or i0 + 1 >= D.T or not s["o"][i0 + 1]:
            return {**base, "st": "skip", "why": "連續漲停開盤買不到"}
        i0 += 1
        p0 = s["o"][i0]
    if k:
        base = {**base, "lim": k}
    if last < out_d:
        li = max((i for i in range(i0, D.T) if s["c"][i]), default=None)
        r = s["c"][li] / p0 - 1 if li is not None else None
        return {**base, "st": "open", "entry": p0, "now": None if li is None else s["c"][li],
                "held": None if li is None else li - i0 + 1, "r": None if r is None else round(r * 100, 2),
                "ent": ent_d, "out": out_d}
    i1 = _on_or_before(D, out_d)
    if i1 is not None and not out_open and i1 >= i0:
        i2 = exit_day(s, i1, D.T)                         # 整天鎖跌停賣不掉，順延到下一個交易日收盤
        if i2 != i1:
            base = {**base, "lock": i2 - i1}
            i1 = i2
    r, x = P.ret(c, i0, True, i1, out_open)
    if r is None or i1 is None or i1 < i0:
        return {**base, "st": "skip", "why": "出場日無價格"}
    return {**base, "st": "closed", "entry": p0, "exit": P.px(c, i1, out_open), "why": why,
            "held": i1 - i0 + (0 if out_open else 1), "r": round(r * 100, 2),
            "x": None if x is None else round(x * 100, 2), "ent": ent_d, "out": out_d}


def _pct1(x):
    return None if x is None else round(x * 100, 1)


def early_trades(D, P: _Px, p: dict, names: dict, picks: dict | None = None, mom_c: dict | None = None) -> list[dict]:
    """提前卡位版的交易：早買名單（截止日名單沒有的隔天開盤賣）＋截止日補位；其餘抱到生效前一天收盤。"""
    pk = picks or p
    mom_c = p.get("mom") if mom_c is None else mom_c
    out = []
    if pk.get("e_t") is not None:
        i0 = pk["e_t"] + 1 if pk["e_t"] + 1 < D.T else None
        for c in pk["pick_e"]:
            base = {"c": c, "n": names.get(c, c), "d": pk["e_sig"], "review": p["review"], "tag": "早",
                    "mom": _pct1((p.get("mom_e") or {}).get(c))}
            if p["frozen"] and c not in (p["pred"] or []):
                out.append(_trade(D, P, c, i0, pk["e_in"], p["a_in"], True, "截止日名單沒有・隔天開盤出", base))
            elif p["official"] and c not in (p["act"] or []):
                out.append(_trade(D, P, c, i0, pk["e_in"], p["b_in"], True, "公告未納入・隔日開盤出", base))
            else:
                out.append(_trade(D, P, c, i0, pk["e_in"], p["out_c"].get(c) or p["out"], False, "生效前一天出", base))
    for c in pk["pick_t"]:
        i0 = p["ic"] + 1 if p["ic"] is not None and p["ic"] + 1 < D.T else None
        base = {"c": c, "n": names.get(c, c), "d": p["cutoff"], "review": p["review"], "tag": "補",
                "mom": _pct1((mom_c or {}).get(c))}
        if p["official"] and c not in (p["act"] or []):
            out.append(_trade(D, P, c, i0, p["a_in"], p["b_in"], True, "公告未納入・隔日開盤出", base))
        else:
            out.append(_trade(D, P, c, i0, p["a_in"], p["out_c"].get(c) or p["out"], False, "截止日補位・生效前一天出", base))
    return out


def version_trades(D, cfg: dict, names: dict, pl: list[dict] | None = None) -> dict[str, list[dict]]:
    """兩個版本的交易（樣本內＋前瞻同一套規則）。d＝訊號日：提前卡位＝建倉選股日（補位＝截止日）、公告後版＝公告日。"""
    pl = plans(D, cfg) if pl is None else pl
    P = _Px(D)
    out = {"early": [], "post": []}
    for p in pl:
        out["early"] += early_trades(D, P, p, names)
        for c in p["pick_b"]:
            out_d = p["out_c"].get(c) or p["out"]
            base = {"c": c, "n": names.get(c, c), "d": p["announce"], "review": p["review"], "side": "add",
                    "mom": _pct1(p["mom"].get(c))}
            i0 = _first_after(D, p["announce"]) if p["announce"] else None
            out["post"].append(_trade(D, P, c, i0, p["b_in"], out_d, False, "生效前一天出", base))
    return out


def early_scan(D, cfg: dict, ks=range(35, -1, -1), ctx: _Ctx | None = None, pl: list[dict] | None = None) -> dict:
    """提前幾個交易日建倉最好？同一套規則（最多 EARLY_N 檔、截止日校正＋補位），逐日回測歷次審核。
    只算建倉日在上一次審核生效之後的（更早會和上一次審核重疊）。單位＝每次審核的平均報酬（每筆平均分配）。"""
    ctx = ctx or _Ctx(D, cfg)
    pl = [p for p in (pl or plans(D, cfg, ctx)) if p["official"]]
    prev = {b["review"]: a["effective"] for a, b in zip(pl, pl[1:])}
    res = {"k": [], "avg": [], "med": [], "win": [], "n": [], "lo": [], "pick": EARLY_K, "N": EARLY_N}
    for k in ks:
        per = []
        for p in pl:
            pre = ctx.pres.get(p["review"])
            pk = early_picks(ctx, p, pre, k)
            if pk["e_t"] is None or (prev.get(p["review"]) and pk["e_sig"] <= prev[p["review"]]):
                continue
            rs = [t["r"] for t in early_trades(D, ctx.P, p, {}, pk, {}) if t.get("st") == "closed"]
            if rs:
                per.append(statistics.mean(rs))
        res["k"].append(k)
        res["n"].append(len(per))
        res["avg"].append(round(statistics.mean(per), 1) if per else None)
        res["med"].append(round(statistics.median(per), 1) if per else None)
        res["win"].append(sum(1 for x in per if x > 0))
        res["lo"].append(round(min(per), 1) if per else None)
    return res


def early_grid(D, cfg: dict, ks=(EARLY_K - 5, EARLY_K, EARLY_K + 5), ns=(EARLY_N - 1, EARLY_N, EARLY_N + 1),
               ctx: _Ctx | None = None, pl: list[dict] | None = None) -> dict:
    """參數鄰近（D5，docs/strategy_pack_plan.md）：建倉提前天數 × 檔數各 ±1 檔，各組「每次審核平均超額」的平均
    （樣本內、已出場、同 early_scan 的排除規則：建倉日早於上一次審核生效日者不算）。"""
    from .packtest import grid
    ctx = ctx or _Ctx(D, cfg)
    pl = [p for p in (pl or plans(D, cfg, ctx)) if p["official"]]
    prev = {b["review"]: a["effective"] for a, b in zip(pl, pl[1:])}

    def f(k, n):
        per = []
        for p in pl:
            pre = ctx.pres.get(p["review"])
            pk = early_picks(ctx, p, pre, k, n)
            if pk["e_t"] is None or (prev.get(p["review"]) and pk["e_sig"] <= prev[p["review"]]):
                continue
            xs = [t["x"] for t in early_trades(D, ctx.P, p, {}, pk, {}) if t.get("st") == "closed" and t.get("x") is not None]
            if xs:
                per.append(statistics.mean(xs))
        return statistics.mean(per) if per else None
    return grid(f, ks, ns, ("截止前幾個交易日建倉", "買進檔數"))
