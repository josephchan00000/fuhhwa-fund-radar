"""美股飆股研究：找規則（superx VER 2 的 feature_table／candidate_conds／mine_rules／select_final 同一套算法；ussxspec VER 1）。

superx 的版本吃「一列一個 dict」，美股一本帳一百多萬列、二十幾個條件，dict 太占記憶體；這裡改吃欄（每個條件一個 numpy 陣列），
位元集合、門檻、四捨五入、排序與同分的順序都照 superx（tests/test_ussxmine.py 用同一份資料逐項比對兩邊的輸出）。

Cols：{"d": 日期（字串陣列）, "c": 代號（字串陣列）, "f": {條件: 陣列（數值 nan＝沒有；是／否 1、0、nan）},
       "y": {帳: {"y": int8（1、0、−1＝還不知道）, "mx", "dd", "fr": 陣列}}}
"""
from __future__ import annotations

import bisect
from itertools import combinations

import numpy as np

from . import ussxspec as X


def _r(x, d=4):
    return None if x is None or (isinstance(x, float) and x != x) else round(x, d)


def pack(mask: np.ndarray) -> int:
    """布林陣列 → 位元集合（第 j 位＝第 j 列；同 superx.pack）。"""
    b = np.packbits(np.asarray(mask, dtype=bool), bitorder="little").tobytes()
    return int.from_bytes(b, "little")


def ones(x: int, n: int) -> np.ndarray:
    """位元集合裡為 1 的位置（由小到大）。"""
    if not x:
        return np.zeros(0, dtype=np.int64)
    b = np.frombuffer(x.to_bytes((n + 7) // 8, "little"), dtype=np.uint8)
    return np.nonzero(np.unpackbits(b, bitorder="little")[:n])[0]


class Bits:
    """一組列（Cols 的子集合，用索引表示）對某本帳的位元集合（superx.Bits 同一套）。"""

    def __init__(self, cols: dict, idx: np.ndarray, lab: str, feats=None):
        self.cols, self.idx, self.lab, self.n = cols, np.asarray(idx), lab, len(idx)
        self.feats = feats or X.FEATS
        y = cols["y"][lab]["y"][self.idx]
        self.valid = pack(y >= 0)
        self.y = pack(y == 1)
        self._c: dict = {}

    def cond(self, cond) -> int:
        key = tuple(cond)
        if key not in self._c:
            k, op, v = key
            x = self.cols["f"][k][self.idx]
            with np.errstate(invalid="ignore"):
                if op == ">=":
                    m = x >= v
                elif op == "<=":
                    m = x <= v
                elif op == ">":
                    m = x > v
                else:
                    m = x == 1
            self._c[key] = pack(m)
        return self._c[key]

    def rule(self, conds) -> int:
        m = self.valid
        for c in conds:
            m &= self.cond(c)
        return m

    def period(self, rng) -> int:
        key = ("_p",) + tuple(rng)
        if key not in self._c:
            d = self.cols["d"][self.idx]
            self._c[key] = pack((d >= rng[0]) & (d <= rng[1]))
        return self._c[key]

    def count(self, m: int) -> tuple[int, int]:
        m &= self.valid
        return m.bit_count(), (m & self.y).bit_count()


def deciles(vals: np.ndarray) -> list[float]:
    xs = np.sort(vals)
    n = len(xs)
    return [float(xs[min(n - 1, int(n * k / 10))]) for k in range(1, 10)] if n >= 10 else []


def feature_table(B: Bits) -> dict:
    """每個條件：十等分（或是／否）的樣本數、命中率、提升倍數（superx.feature_table，不含逐年）。"""
    n_all, p_all = B.count(B.valid)
    br = p_all / n_all if n_all else 0
    vd = ones(B.valid, B.n)
    out = {}
    for k, nm, typ, _ in B.feats:
        x = B.cols["f"][k][B.idx]
        if typ == "bool":
            names = ["否", "是"]
            cuts = None
            grp = np.where(np.isnan(x), -1, np.where(x == 1, 1, 0))
        else:
            xv = x[vd]
            vals = xv[~np.isnan(xv)]
            cuts = deciles(vals)
            if not cuts:
                continue
            names = [f"D{j + 1}" for j in range(10)]
            grp = np.where(np.isnan(x), -1, np.searchsorted(np.array(cuts), np.nan_to_num(x), side="right"))
        g_out = []
        for j, gn in enumerate(names):
            n, pos = B.count(pack(grp == j))
            p_ = pos / n if n else None
            g_out.append({"g": gn, "n": n, "pos": pos, "p": _r(p_), "lift": _r(p_ / br) if p_ is not None and br else None})
        nv = int(np.sum(~np.isnan(x[vd])))
        out[k] = {"name": nm, "type": typ, "cuts": [_r(c, 4) for c in cuts] if cuts else None, "groups": g_out, "n": nv}
    return {"base": _r(br), "feats": out}


def candidate_conds(ftab: dict, rule: dict | None = None, qs=None) -> list[tuple]:
    """superx.candidate_conds：樣本內提升倍數最高的 top_feats 個條件 → 數值取較強那一端的 10／20／30% 切點、是／否取「是」。"""
    rule = rule or X.RULE
    qs = qs or X.QS
    rank = []
    for k, t in ftab["feats"].items():
        gs = t["groups"]
        if t["type"] == "bool":
            g = next((x for x in gs if x["g"] == "是"), None)
            if g and g["lift"] and g["n"] >= rule["n"]:
                rank.append((g["lift"], k, "bool"))
        else:
            top, bot = gs[-1], gs[0]
            best = max((top["lift"] or 0, "hi"), (bot["lift"] or 0, "lo"))
            rank.append((best[0], k, best[1]))
    rank.sort(reverse=True)
    conds = []
    for lift, k, side in rank[:rule["top_feats"]]:
        if side == "bool":
            conds.append((k, "=", True))
            continue
        cuts = ftab["feats"][k]["cuts"]                  # superx 用的是四捨五入到小數 4 位的切點
        for q in qs:
            j = int(round(q * 10))
            conds.append((k, ">=", cuts[9 - j]) if side == "hi" else (k, "<=", cuts[j - 1]))
    return conds


def mine_rules(B: Bits, conds: list[tuple], subs, rule: dict | None = None) -> tuple[list[dict], int]:
    """superx.mine_rules：2～3 個條件（同一特徵不重複）→ 樣本內門檻。"""
    rule = rule or X.RULE
    n_all, p_all = B.count(B.valid)
    br = p_all / n_all if n_all else 0
    sm = [B.period(s) for s in subs]
    br_s = []
    for m in sm:
        n, pos = B.count(m)
        br_s.append(pos / n if n else 0)
    cm = [B.cond(c) & B.valid for c in conds]
    out, tried = [], 0
    for k in (2, 3):
        for combo in combinations(range(len(conds)), k):
            if len({conds[j][0] for j in combo}) < k:
                continue
            tried += 1
            m = cm[combo[0]]
            for j in combo[1:]:
                m &= cm[j]
            n, pos = B.count(m)
            if n < rule["n"] or pos < rule["pos"] or not br:
                continue
            lift = pos / n / br
            sl = []
            for s, m_s in enumerate(sm):
                ns, ps = B.count(m & m_s)
                sl.append(ps / ns / br_s[s] if ns and br_s[s] else 0)
            if lift >= rule["lift"] and min(sl) >= rule["sub_lift"]:
                out.append({"conds": [conds[j] for j in combo],
                            "is": {"n": n, "pos": pos, "p": _r(pos / n), "lift": _r(lift), "sub": [_r(x) for x in sl]}})
    return out, tried


def dist(B: Bits, m: int) -> dict:
    """superx.dist：一組列之後的最高漲幅、最大跌幅、到期報酬的中位數與平均、股票數。"""
    ii = B.idx[ones(m & B.valid, B.n)]
    L = B.cols["y"][B.lab]
    mx = sorted(L["mx"][ii].tolist())
    dd = sorted(x for x in L["dd"][ii].tolist() if x == x)
    fr = sorted(x for x in L["fr"][ii].tolist() if x == x)
    med = lambda xs: xs[len(xs) // 2] if xs else None
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    return {"mx_med": _r(med(mx)), "dd_med": _r(med(dd)), "fr_med": _r(med(fr)), "fr_avg": _r(avg(fr)),
            "fr_win": _r(sum(1 for x in fr if x > 0) / len(fr)) if fr else None,
            "codes": len(set(B.cols["c"][ii].tolist()))}


def eval_rule(B: Bits, conds, full: bool = True) -> dict:
    n_all, p_all = B.count(B.valid)
    br = p_all / n_all if n_all else 0
    m = B.rule(conds)
    n, pos = B.count(m)
    out = {"n": n, "pos": pos, "p": _r(pos / n) if n else None, "base": _r(br), "lift": _r(pos / n / br) if n and br else None}
    if full:
        out.update(dist(B, m))
    return out


def select_final(rules: list, B: Bits, rule: dict | None = None) -> list[dict]:
    """superx.select_final：挑規則期間提升倍數 ≥ val_lift（而且 ≥ 50 列）才留；依命中率排序、重疊超過 OVERLAP_MAX 的只留一條。"""
    rule = rule or X.RULE
    keep = []
    for r in rules:
        v = eval_rule(B, r["conds"], full=False)
        r["val"] = v
        if v["lift"] is not None and v["lift"] >= rule["val_lift"] and v["n"] >= 50:
            keep.append(r)
    keep.sort(key=lambda r: (-(r["val"]["p"] or 0), -(r["is"]["lift"] or 0)))
    final, sets = [], []
    for r in keep:
        s = B.rule(r["conds"])
        sc = s.bit_count()
        if any((s & t).bit_count() / max(1, min(sc, t.bit_count())) > X.OVERLAP_MAX for t in sets):
            continue
        r["val"] = eval_rule(B, r["conds"])
        final.append(r)
        sets.append(s)
        if len(final) >= X.KEEP_FINAL:
            break
    return final


def mine_fold(cols: dict, lab: str, y: int, ix_of: dict | None = None, cal: list[str] | None = None) -> dict:
    """交易年 y 那一本帳的規則（ussxspec.fold_periods；主門檻沒有就用 FALLBACK）。ix_of＝{日期: 交易日索引}，用來挑
    「訊號日＋n ≤ y−1 年最後一個交易日」的 VAL 樣本。"""
    f = X.fold_periods(y, lab)
    n = X.hold_of(lab)
    d = cols["d"]
    di = cols["di"]
    i_last = max(i for i, dd in enumerate(cal) if dd <= f["known"])
    is_idx = np.nonzero((d >= f["is"][0]) & (d <= f["is"][1]))[0]
    val_idx = np.nonzero((d >= f["val"][0]) & (d <= f["val"][1]) & (di + n <= i_last))[0]
    Bi, Bv = Bits(cols, is_idx, lab), Bits(cols, val_idx, lab)
    nb_i, pb_i = Bi.count(Bi.valid)
    nb_v, pb_v = Bv.count(Bv.valid)
    out = {"lab": lab, "y": y, "thr": None, "rules": [], "n_is": int(len(is_idx)), "n_val": int(len(val_idx)),
           "base_is": _r(pb_i / nb_i) if nb_i else None, "base_val": _r(pb_v / nb_v) if nb_v else None, "try": []}
    for nm, thr in (("main", {}), ("fallback", X.FALLBACK)):
        rule = {**X.RULE, **thr}
        ft = feature_table(Bi)
        conds = candidate_conds(ft, rule)
        rules, tried = mine_rules(Bi, conds, f["subs"], rule)
        fin = select_final(rules, Bv, rule)
        out["try"].append({"thr": nm, "conds": len(conds), "tried": tried, "is_pass": len(rules), "final": len(fin)})
        if fin:
            out["thr"] = nm
            out["rules"] = [{"conds": [list(c) for c in r["conds"]], "is": r["is"],
                             "val": {k: r["val"].get(k) for k in ("n", "pos", "p", "base", "lift", "fr_med", "fr_avg", "fr_win", "codes")}}
                            for r in fin]
            break
    return out


def rule_mask(cols: dict, rules: list, idx: np.ndarray | None = None) -> np.ndarray:
    """符合任一條規則的列（布林陣列；idx＝只看這些列）。"""
    n = len(cols["d"]) if idx is None else len(idx)
    out = np.zeros(n, dtype=bool)
    for r in rules:
        m = np.ones(n, dtype=bool)
        for k, op, v in r["conds"]:
            x = cols["f"][k] if idx is None else cols["f"][k][idx]
            with np.errstate(invalid="ignore"):
                m &= (x >= v) if op == ">=" else (x <= v) if op == "<=" else (x > v) if op == ">" else (x == 1)
        out |= m
    return out
