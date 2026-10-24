"""飆股研究（docs/lab_company_plan.md 第 4 節；規格事前寫定，跑結果之前先 commit）。

使用者 2026-10-16：「我的重點是要能找到飆股，超級績效最大的重點是要找到飆股」。
和 tw-superstock-lab/SPEC.md 第 5 節同一套定義（Mac 上的完整版之後可以直接對照），只用 repo 裡已有的官方資料：
  · 價格：v3 長歷史面板（bt3d.Panel，含息還原、含已下市）
  · 月營收：rev（2012-01 起）
  · 財報：MOPS 綜合損益／資產負債彙總（fsq，2013Q1 起；舊資料只有 EPS 的 v3isq 為備援）

流程：每週最後一個交易日、合格股票 → 特徵（當天收盤已知）＋標籤（只有標籤用未來）
→ 樣本內十等分命中率與提升倍數 → 2～3 個條件的規則 → 驗證期選規則 → 保留期只看一次。
同一支 feats() 也給每日「飆股候選」用（只算最新一天）。
"""
from __future__ import annotations

import bisect
import math
from itertools import combinations

# ── 事前寫定（docs/lab_company_plan.md 第 4 節；改任何一個數字＝新版本，日期與原因寫進文件） ──────────
VER = 2                                           # v2（2026-10-16，還沒看任何結果）：加 CAP_MIN 與 CHECKS，原因見文件第 4.2 節
LABELS = {"A": (60, 0.5), "B": (250, 1.0)}        # 之後 N 個交易日內最高價（還原）≥ 收盤 × (1+g)
LIQ_MIN = 1e7                                     # 近 20 日平均成交值（元）
AGE_MIN = 60                                      # 上市滿幾個交易日
CAP_MIN = 40e8                                    # 最近月底市值（元）：v3px 只收「曾經月底市值 ≥40 億」的股票，
                                                  # 低於這個的小股票只有日後長大的才在資料裡（用未來挑樣本）
IS = ("2014-01-01", "2019-12-31")
VAL = ("2020-01-01", "2022-12-31")
HO = ("2023-01-01", "9999-12-31")
SUBS = (("2014-01-01", "2016-12-31"), ("2017-01-01", "2019-12-31"))
RULE = {"lift": 2.0, "n": 300, "pos": 50, "sub_lift": 1.5, "val_lift": 1.5, "max_k": 3, "top_feats": 12}
QS = (0.1, 0.2, 0.3)                              # 條件門檻：前／後 10%、20%、30% 的切點
KEEP_FINAL = 5                                    # 每個標籤最後最多留幾條（驗證期依命中率選，避免同一群股票的重複規則）
OVERLAP_MAX = 0.8                                 # 兩條規則命中的股票週重疊超過這個比例，只留驗證期命中率較高的

# (鍵, 名稱, 型態)：num＝數值（十等分）、bool＝是／否
FEATS = [
    ("tt_n", "趨勢樣板通過幾項（0–8）", "num"),
    ("tt_all", "趨勢樣板 8 項全過", "bool"),
    ("rs", "RS 百分位", "num"),
    ("d52h", "距 52 週高點", "num"),
    ("r120", "近 120 日報酬", "num"),
    ("lu20", "近 20 日漲停次數", "num"),
    ("vdry", "量縮（10 日 ÷ 50 日均量）", "num"),
    ("ry", "最新月營收年增", "num"),
    ("ry3", "近 3 月營收年增", "num"),
    ("racc", "營收加速（近 3 月年增 − 前 3 月年增）", "num"),
    ("rnh12", "月營收創 12 個月新高", "bool"),
    ("rnha", "月營收創歷史新高", "bool"),
    ("ey", "最新季 EPS 年增", "num"),
    ("eacc", "EPS 加速（本季年增 − 上季年增）", "num"),
    ("gm", "毛利率", "num"),
    ("gmd", "毛利率年變化", "num"),
    ("om", "營益率", "num"),
    ("omd", "營益率年變化", "num"),
    ("c33", "連三季變好（EPS 成長率、營收成長率、毛利率都一季比一季高）", "bool"),
    ("roe", "近四季 ROE", "num"),
    ("cap", "市值", "num"),
    ("liq", "20 日平均成交值", "num"),
]
# 飆股體質檢查：《超級績效》的固定條件（不是從資料挑的），頁面 copage.SXCK 同一份（tests 守）。
# 研究只算「過去符合時之後變飆股的比例」與「符合幾項」各組的比例，不拿來選規則。
CHECKS = [
    ("ey25", "最新一季 EPS 比去年同季多 25% 以上", "ey", ">=", 0.25),
    ("eacc", "EPS 成長在加速（這一季的成長率比上一季高）", "eacc", ">", 0),
    ("ry25", "近 3 個月營收比去年同期多 25% 以上", "ry3", ">=", 0.25),
    ("racc", "營收成長在加速（近 3 個月的成長率比前 3 個月高）", "racc", ">", 0),
    ("rnh", "月營收創 12 個月新高", "rnh12", "=", True),
    ("gmd", "毛利率比去年同季高", "gmd", ">", 0),
    ("c33", "連三季變好：EPS 成長率、營收成長率、毛利率都一季比一季高", "c33", "=", True),
    ("roe15", "近四季 ROE（股東權益報酬率）15% 以上", "roe", ">=", 0.15),
    ("tt8", "股價趨勢 8 項全過（長期上升趨勢）", "tt_all", "=", True),
    ("rs80", "股價強度 RS 80 以上（近一年漲幅勝過八成股票）", "rs", ">=", 80),
    ("h25", "股價離 52 週高點 25% 以內", "d52h", ">=", -0.25),
]
FK = [k for k, _, _ in FEATS]
FTYPE = {k: t for k, _, t in FEATS}
FNAME = {k: n for k, n, _ in FEATS}


# ── 小工具 ──────────────────────────────────────────────────────────────────
def week_ends(cal: list[str]) -> list[int]:
    """每週最後一個交易日的索引（ISO 週）。"""
    from datetime import date
    out = []
    for i, d in enumerate(cal):
        w = date.fromisoformat(d).isocalendar()[:2]
        if i + 1 == len(cal) or date.fromisoformat(cal[i + 1]).isocalendar()[:2] != w:
            out.append(i)
    return out


def ffill(xs: list) -> list:
    out, last = [], None
    for x in xs:
        if x is not None:
            last = x
        out.append(last)
    return out


def prefix(xs: list) -> tuple[list, list]:
    s, n = [0.0], [0]
    for x in xs:
        s.append(s[-1] + (x or 0.0))
        n.append(n[-1] + (1 if x is not None else 0))
    return s, n


def wmean(S, N, i: int, w: int, k_min: float = 0.8):
    a = i + 1 - w
    if a < 0:
        return None
    k = N[i + 1] - N[a]
    return (S[i + 1] - S[a]) / k if k >= w * k_min else None


def ratio(a, b, lo=-1.0, hi=5.0):
    if a is None or b is None or b <= 0:
        return None
    return max(lo, min(hi, a / b - 1))


def limit_pct(d: str) -> float:
    return 0.10 if d >= "2015-06-01" else 0.07


# ── 財報（單季）與月營收 ─────────────────────────────────────────────────────
def qprev(q: str, k: int = 1) -> str:
    """季底日往前 k 季（'2026-06-30' → '2026-03-31'）。"""
    ends = ("03-31", "06-30", "09-30", "12-31")
    y, j = int(q[:4]), ends.index(q[5:])
    j -= k
    while j < 0:
        j += 4
        y -= 1
    return f"{y:04d}-{ends[j]}"


class Fund:
    """一家公司的單季財報與月營收 → 某個「可得的最新季／月」的特徵（同一季／月只算一次）。"""

    def __init__(self, fq: dict | None, rv: dict | None):
        self.fq = fq or {}        # {季底: {rev, gp, op, nip, eps, eqp}}（損益為單季）
        self.rv = rv or {}        # {YYYY-MM: 營收(千元)}
        self._q: dict = {}
        self._m: dict = {}

    def _g(self, q, k):
        return (self.fq.get(q) or {}).get(k)

    def ey(self, q):
        e, b = self._g(q, "eps"), self._g(qprev(q, 4), "eps")
        if e is None or b is None:
            return None
        if b > 0.05:
            return max(-1.0, min(3.0, e / b - 1))
        return 3.0 if e > 0.05 else None            # 去年同季虧損或接近零：轉盈記 300%，續虧不算

    def sy(self, q):
        return ratio(self._g(q, "rev"), self._g(qprev(q, 4), "rev"), -1.0, 3.0)

    def gm(self, q):
        r, g = self._g(q, "rev"), self._g(q, "gp")
        return g / r if r and g is not None and r > 0 else None

    def om(self, q):
        r, o = self._g(q, "rev"), self._g(q, "op")
        return o / r if r and o is not None and r > 0 else None

    def q_feats(self, q: str | None) -> dict:
        if q is None:
            return {}
        if q in self._q:
            return self._q[q]
        f: dict = {}
        ey0, ey1, ey2 = self.ey(q), self.ey(qprev(q)), self.ey(qprev(q, 2))
        f["ey"] = ey0
        f["eacc"] = ey0 - ey1 if ey0 is not None and ey1 is not None else None
        g0, g4 = self.gm(q), self.gm(qprev(q, 4))
        f["gm"] = g0
        f["gmd"] = g0 - g4 if g0 is not None and g4 is not None else None
        o0, o4 = self.om(q), self.om(qprev(q, 4))
        f["om"] = o0
        f["omd"] = o0 - o4 if o0 is not None and o4 is not None else None
        s0, s1, s2 = self.sy(q), self.sy(qprev(q)), self.sy(qprev(q, 2))
        g1, g2 = self.gm(qprev(q)), self.gm(qprev(q, 2))
        vals = (ey0, ey1, ey2, s0, s1, s2, g0, g1, g2)
        f["c33"] = (None if any(v is None for v in vals)
                    else bool(ey0 > ey1 > ey2 and s0 > s1 > s2 and g0 > g1 > g2))
        ni = [self._g(qprev(q, k), "nip") for k in range(4)]
        e0, e4 = self._g(q, "eqp"), self._g(qprev(q, 4), "eqp")
        f["roe"] = (sum(ni) / ((e0 + e4) / 2) if all(x is not None for x in ni) and e0 and e4 and e0 > 0 and e4 > 0
                    else None)
        self._q[q] = f
        return f

    def m_feats(self, ym: str | None) -> dict:
        if ym is None:
            return {}
        if ym in self._m:
            return self._m[ym]
        from .packtest import ym_shift
        r = self.rv
        cur = r.get(ym)
        f: dict = {"ry": ratio(cur, r.get(ym_shift(ym, -12)))}

        def s3(m):
            xs = [r.get(ym_shift(m, -k)) for k in range(3)]
            ys = [r.get(ym_shift(m, -12 - k)) for k in range(3)]
            if any(x is None for x in xs + ys):
                return None
            return ratio(sum(xs), sum(ys))
        a, b = s3(ym), s3(ym_shift(ym, -3))
        f["ry3"] = a
        f["racc"] = a - b if a is not None and b is not None else None
        prev = [r.get(ym_shift(ym, -k)) for k in range(1, 12)]
        f["rnh12"] = (None if cur is None or any(x is None for x in prev) else bool(cur >= max(prev)))
        before = [v for m, v in r.items() if m < ym and v is not None]
        f["rnha"] = (None if cur is None or len(before) < 24 else bool(cur >= max(before)))
        self._m[ym] = f
        return f


def avail_index(cal: list[str]):
    """(季底 → 可得的第一個交易日索引, [(索引, 營收月)])：財報＝法定期限當天或之後第一個交易日；營收＝每月 10 日起。"""
    from . import packtest as PT
    qs = {}
    y0, y1 = int(cal[0][:4]) - 1, int(cal[-1][:4]) + 1
    for y in range(y0, y1 + 1):
        for e in ("03-31", "06-30", "09-30", "12-31"):
            q = f"{y}-{e}"
            t = PT.form_after_deadline(cal, PT.deadline(q))
            if t is not None:
                qs[q] = t
    rf = PT.rev_forms(cal)
    return qs, rf


def latest_q(qs_items: list[tuple[int, str]], i: int) -> str | None:
    """qs_items＝依可得索引排序的 [(索引, 季底)] → 第 i 天收盤時可得的最新季。"""
    k = bisect.bisect_right([t for t, _ in qs_items], i) - 1
    return qs_items[k][1] if k >= 0 else None


# ── 價格特徵與標籤 ───────────────────────────────────────────────────────────
class Px:
    """一檔股票的還原日線 → 任一天的技術特徵、之後的標籤。"""

    def __init__(self, s: dict, cal: list[str]):
        self.cal = cal
        self.c, self.h, self.l = ffill(s["c"]), ffill(s["h"]), ffill(s["l"])
        self.v = s["v"]
        self.first = next((i for i, x in enumerate(s["c"]) if x is not None), None)
        last = None
        for i in range(len(s["c"]) - 1, -1, -1):
            if s["c"][i] is not None:
                last = i
                break
        self.last = last
        self.S, self.N = prefix(self.c)
        self.VS, self.VN = prefix(self.v)

    def raw(self, i: int) -> dict | None:
        """RS 排名前的原始技術數值；資料不夠回 None。"""
        c = self.c
        if self.first is None or i - self.first < 252 or c[i] is None or self.last is None or i > self.last:
            return None
        ma50, ma150, ma200 = (wmean(self.S, self.N, i, w) for w in (50, 150, 200))
        ma200p = wmean(self.S, self.N, i - 20, 200)
        hs = [x for x in self.h[i - 251:i + 1] if x is not None]
        ls = [x for x in self.l[i - 251:i + 1] if x is not None]
        if not hs or not ls or None in (ma50, ma150, ma200, ma200p):
            return None
        hi, lo = max(hs), min(ls)
        r = {n: (c[i] / c[i - n] - 1 if c[i - n] else None) for n in (63, 120, 126, 189, 252)}
        if any(r[n] is None for n in (63, 126, 189, 252)):
            return None
        lim = limit_pct(self.cal[i]) - 0.005
        lu = sum(1 for k in range(i - 19, i + 1) if c[k - 1] and c[k] and c[k] / c[k - 1] - 1 >= lim)
        v10, v50 = wmean(self.VS, self.VN, i, 10), wmean(self.VS, self.VN, i, 50)
        tt = [c[i] > ma150 and c[i] > ma200, ma150 > ma200, ma200 > ma200p, ma50 > ma150 and ma50 > ma200,
              c[i] > ma50, c[i] >= 1.3 * lo, c[i] >= 0.75 * hi]
        return {"score": 0.4 * r[63] + 0.2 * r[126] + 0.2 * r[189] + 0.2 * r[252], "tt7": tt,
                "d52h": c[i] / hi - 1, "r120": r[120], "lu20": lu, "vdry": v10 / v50 if v10 and v50 else None}

    def label(self, i: int, n: int, g: float) -> dict | None:
        """之後 n 個交易日（資料尾端不夠且沒下市 → None）；下市股用到下市為止。"""
        c0 = self.c[i]
        if c0 is None or self.last is None:
            return None
        end = i + n
        T = len(self.cal)
        if end >= T:                                  # 面板尾端：未來還沒發生
            return None
        hi = [x for x in self.h[i + 1:min(end, self.last) + 1] if x is not None]
        lo = [x for x in self.l[i + 1:min(end, self.last) + 1] if x is not None]
        if not hi:
            return None
        cx = self.c[min(end, self.last)]
        mx = max(hi) / c0 - 1
        return {"y": mx >= g, "mx": mx, "dd": min(lo) / c0 - 1 if lo else None, "fr": cx / c0 - 1 if cx else None}


def rs_pct(scores: dict[str, float]) -> dict[str, int]:
    """當天全體排名 → 1～99。"""
    ks = sorted(scores, key=lambda c: scores[c])
    n = len(ks)
    return {c: max(1, min(99, int(round(100 * (j + 1) / (n + 1))))) for j, c in enumerate(ks)}


def feats_on(i: int, P, pxs: dict, funds: dict, qitems, rf_items, codes=None, all_rows: bool = False) -> dict[str, dict]:
    """第 i 天收盤時的特徵 {代號: {特徵}}（同一套給研究與每日候選用）。
    合格（近 20 日均成交值 ≥ LIQ_MIN、最近月底市值 ≥ CAP_MIN、上市滿 AGE_MIN 天）的股票互相排 RS；all_rows＝True 時不合格的也算，
    RS 以合格股票的分布換算、特徵多一欄 el＝False（規則只看合格的）。"""
    raw, el = {}, set()
    for c in (codes or pxs):
        px = pxs[c]
        r = px.raw(i)
        if r is None:
            continue
        lq = (P.liq.get(c) or [None] * (i + 1))[i]
        cp = (P.cap.get(c) or [None] * (i + 1))[i]
        ok = (lq is not None and lq >= LIQ_MIN and cp is not None and cp >= CAP_MIN
              and px.first is not None and i - px.first >= AGE_MIN)
        if not ok and not all_rows:
            continue
        raw[c] = r
        if ok:
            el.add(c)
    rs = rs_pct({c: raw[c]["score"] for c in el})
    if all_rows and el:
        sc = sorted(raw[c]["score"] for c in el)
        n = len(sc)
        for c in raw:
            if c not in el:
                rs[c] = max(1, min(99, int(round(100 * (bisect.bisect_left(sc, raw[c]["score"]) + 1) / (n + 1)))))
    q = latest_q(qitems, i)
    k = bisect.bisect_right([t for t, _ in rf_items], i) - 1
    ym = rf_items[k][1] if k >= 0 else None
    out = {}
    for c, r in raw.items():
        if c not in rs:
            continue
        tt = r["tt7"] + [rs[c] >= 70]
        f = {"tt_n": sum(1 for x in tt if x), "tt_all": all(tt), "rs": rs[c], "d52h": r["d52h"], "r120": r["r120"],
             "lu20": r["lu20"], "vdry": r["vdry"], "cap": (P.cap.get(c) or [None] * (i + 1))[i],
             "liq": (P.liq.get(c) or [None] * (i + 1))[i]}
        if all_rows:
            f["el"] = c in el
            f["tt"] = [bool(x) for x in tt]
        fd = funds.get(c)
        if fd is not None:
            f.update(fd.m_feats(ym if ym and ym in fd.rv else _last_le(fd.rv, ym)))
            f.update(fd.q_feats(q if q and q in fd.fq else _last_q_le(fd.fq, q)))
        out[c] = f
    return out


def _last_le(rv: dict, ym: str | None):
    """營收月：可得月份那家公司沒有（晚報、停牌）→ 不往回找（避免拿舊資料當新的）。"""
    return None


def _last_q_le(fq: dict, q: str | None):
    return None


# ── 研究：十等分、規則、驗證 ───────────────────────────────────────────────────
# 樣本列＝{"c": 代號, "d": 日期, "f": {特徵}, "y": {標籤: {"y", "mx", "dd", "fr"} 或 None}}。
# 條件、標籤、期間都換成「整數位元集合」（第 j 位＝第 j 列），組合用 AND、計數用 bit_count——
# 六十萬列 × 數千個條件組合在純 Python 逐列算要好幾個小時，位元集合幾秒鐘。
def in_rng(d: str, rng) -> bool:
    return rng[0] <= d <= rng[1]


def deciles(vals: list[float]) -> list[float]:
    """樣本內的 10%～90% 切點。"""
    xs = sorted(vals)
    n = len(xs)
    return [xs[min(n - 1, int(n * k / 10))] for k in range(1, 10)] if n >= 10 else []


def bucket(x, cuts):
    return bisect.bisect_right(cuts, x)


def pack(flags) -> int:
    """[真假…] → 位元集合（線性時間；逐位 |= 會是平方時間）。"""
    ba = bytearray((len(flags) + 7) // 8)
    for j, x in enumerate(flags):
        if x:
            ba[j >> 3] |= 1 << (j & 7)
    return int.from_bytes(ba, "little")


def ones(x: int):
    """位元集合裡為 1 的位置（由小到大）。"""
    b = x.to_bytes((x.bit_length() + 7) // 8, "little")
    for bi, byte in enumerate(b):
        if byte:
            for k in range(8):
                if byte >> k & 1:
                    yield bi * 8 + k


class Bits:
    """一組樣本列對某個標籤的位元集合：有標籤的列（valid）、標籤為真的列（y）、條件與期間（快取）。"""

    def __init__(self, rows: list, lab: str):
        self.rows, self.lab = rows, lab
        ys = [r["y"].get(lab) for r in rows]
        self.valid = pack([t is not None for t in ys])
        self.y = pack([t is not None and bool(t["y"]) for t in ys])
        self._c: dict = {}

    def cond(self, cond) -> int:
        if cond not in self._c:
            pr = cond_pred(cond)
            self._c[cond] = pack([pr(r["f"]) for r in self.rows])
        return self._c[cond]

    def rule(self, conds) -> int:
        m = self.valid
        for c in conds:
            m &= self.cond(tuple(c))
        return m

    def period(self, rng) -> int:
        key = ("_p",) + tuple(rng)
        if key not in self._c:
            self._c[key] = pack([in_rng(r["d"], rng) for r in self.rows])
        return self._c[key]

    def year(self, y: str) -> int:
        return self.period((f"{y}-01-01", f"{y}-12-31"))

    def count(self, m: int) -> tuple[int, int]:
        """(樣本數, 飆股數)。"""
        m &= self.valid
        return m.bit_count(), (m & self.y).bit_count()


_BITS: dict = {}


def bits(rows: list, lab: str) -> Bits:
    """同一組列、同一個標籤只建一次（快取存列本身，確認是同一個物件）。"""
    k = (id(rows), lab)
    b = _BITS.get(k)
    if b is None or b.rows is not rows or len(b.rows) != len(rows):
        b = _BITS[k] = Bits(rows, lab)
    return b


def stats(rows: list, lab: str, pred) -> dict:
    B = bits(rows, lab)
    n, pos = B.count(pack([bool(pred(r["f"])) for r in rows]))
    return {"n": n, "pos": pos, "p": pos / n if n else None}


def base_rate(rows: list, lab: str) -> float | None:
    if not rows:
        return None
    B = bits(rows, lab)
    n, pos = B.count(B.valid)
    return pos / n if n else None


def cond_pred(cond):
    """cond＝(特徵, '>=', 門檻) 或 (特徵, '<=', 門檻) 或 (特徵, '>', 門檻) 或 (特徵, '=', True)。"""
    k, op, v = cond
    if op == ">=":
        return lambda f: f.get(k) is not None and f[k] >= v
    if op == "<=":
        return lambda f: f.get(k) is not None and f[k] <= v
    if op == ">":
        return lambda f: f.get(k) is not None and f[k] > v
    return lambda f: f.get(k) is True


def rule_pred(conds):
    ps = [cond_pred(c) for c in conds]
    return lambda f: all(p(f) for p in ps)


def feature_table(rows_is: list, lab: str) -> dict:
    """每個特徵：十等分（或是／否）的樣本數、命中率、提升倍數、逐年提升倍數。"""
    B = bits(rows_is, lab)
    n_all, p_all = B.count(B.valid)
    br = p_all / n_all if n_all else 0
    years = sorted({r["d"][:4] for r in rows_is})
    ym = {y: B.year(y) for y in years}
    br_y = {}
    for y in years:
        n, pos = B.count(ym[y])
        br_y[y] = pos / n if n else None
    vd = list(ones(B.valid))
    out = {}
    for k, nm, typ in FEATS:
        vals = [rows_is[j]["f"][k] for j in vd if rows_is[j]["f"].get(k) is not None]
        if typ == "bool":
            names = ["否", "是"]
            cuts = None
            idx = [None if r["f"].get(k) is None else (1 if r["f"][k] is True else 0) for r in rows_is]
        else:
            cuts = deciles(vals)
            if not cuts:
                continue
            names = [f"D{j + 1}" for j in range(10)]
            idx = [None if r["f"].get(k) is None else bucket(r["f"][k], cuts) for r in rows_is]
        g_out = []
        for j, gn in enumerate(names):
            m = pack([x == j for x in idx])
            n, pos = B.count(m)
            ly = {}
            for y in years:
                ny, py = B.count(m & ym[y])
                if ny >= 30 and br_y[y]:
                    ly[y] = round(py / ny / br_y[y], 2)
            p_ = pos / n if n else None
            g_out.append({"g": gn, "n": n, "pos": pos, "p": _r(p_), "lift": _r(p_ / br) if p_ is not None and br else None,
                          "ly": ly})
        out[k] = {"name": nm, "type": typ, "cuts": [_r(x, 4) for x in cuts] if cuts else None, "groups": g_out,
                  "n": len(vals)}
    return {"base": _r(br), "base_y": {y: _r(v) for y, v in br_y.items()}, "feats": out}


def _r(x, d=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x, d)


def candidate_conds(ftab: dict) -> list[tuple]:
    """樣本內提升倍數最高的特徵 → 條件（數值取較強那一端的 10／20／30% 切點；是／否取「是」）。"""
    rank = []
    for k, t in ftab["feats"].items():
        gs = t["groups"]
        if t["type"] == "bool":
            g = next((x for x in gs if x["g"] == "是"), None)
            if g and g["lift"] and g["n"] >= RULE["n"]:
                rank.append((g["lift"], k, "bool"))
        else:
            top, bot = gs[-1], gs[0]
            best = max((top["lift"] or 0, "hi"), (bot["lift"] or 0, "lo"))
            rank.append((best[0], k, best[1]))
    rank.sort(reverse=True)
    conds = []
    for lift, k, side in rank[:RULE["top_feats"]]:
        if side == "bool":
            conds.append((k, "=", True))
            continue
        cuts = ftab["feats"][k]["cuts"]
        for q in QS:
            j = int(round(q * 10))                     # 1、2、3
            conds.append((k, ">=", cuts[9 - j]) if side == "hi" else (k, "<=", cuts[j - 1]))
    return conds


def mine_rules(rows_is: list, lab: str, conds: list[tuple]) -> tuple[list[dict], int]:
    """2～3 個條件的組合（同一特徵不重複）→ 樣本內門檻（RULE）。回傳（通過的規則, 試了幾個組合）。"""
    B = bits(rows_is, lab)
    n_all, p_all = B.count(B.valid)
    br = p_all / n_all if n_all else 0
    sm = [B.period(s) for s in SUBS]
    br_s = []
    for m in sm:
        n, pos = B.count(m)
        br_s.append(pos / n if n else 0)
    cm = [B.cond(tuple(c)) & B.valid for c in conds]
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
            if n < RULE["n"] or pos < RULE["pos"] or not br:
                continue
            lift = pos / n / br
            sl = []
            for s, m_s in enumerate(sm):
                ns, ps = B.count(m & m_s)
                sl.append(ps / ns / br_s[s] if ns and br_s[s] else 0)
            if lift >= RULE["lift"] and min(sl) >= RULE["sub_lift"]:
                out.append({"conds": [conds[j] for j in combo],
                            "is": {"n": n, "pos": pos, "p": _r(pos / n), "lift": _r(lift), "sub": [_r(x) for x in sl]}})
    return out, tried


def eval_rule(rows: list, lab: str, conds, full: bool = True) -> dict:
    """一段期間的命中率、提升倍數；full＝True 另算符合後的最大漲幅／最大跌幅／期末報酬（中位）與股票數。"""
    B = bits(rows, lab)
    n_all, p_all = B.count(B.valid)
    br = p_all / n_all if n_all else 0
    m = B.rule(conds)
    n, pos = B.count(m)
    out = {"n": n, "pos": pos, "p": _r(pos / n) if n else None, "base": _r(br),
           "lift": _r(pos / n / br) if n and br else None}
    if full:
        out.update(dist([rows[j] for j in ones(m & B.valid)], lab))
    return out


def dist(sel: list, lab: str) -> dict:
    """一組樣本列之後的路徑：最高漲幅、最大跌幅、到期報酬的中位數與平均、股票數（只描述，不參與選規則）。"""
    mx = sorted(r["y"][lab]["mx"] for r in sel)
    dd = sorted(r["y"][lab]["dd"] for r in sel if r["y"][lab]["dd"] is not None)
    fr = sorted(r["y"][lab]["fr"] for r in sel if r["y"][lab]["fr"] is not None)
    med = lambda xs: xs[len(xs) // 2] if xs else None
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    return {"mx_med": _r(med(mx)), "dd_med": _r(med(dd)), "fr_med": _r(med(fr)), "fr_avg": _r(avg(fr)),
            "fr_win": _r(sum(1 for x in fr if x > 0) / len(fr)) if fr else None, "codes": len({r["c"] for r in sel})}


def select_final(rules: list, rows_val: list, lab: str) -> list[dict]:
    """驗證期提升倍數 ≥ RULE['val_lift'] 才留；依驗證期命中率排序，命中重疊超過 OVERLAP_MAX 的只留一條。"""
    B = bits(rows_val, lab)
    keep = []
    for r in rules:
        v = eval_rule(rows_val, lab, r["conds"], full=False)
        r["val"] = v
        if v["lift"] is not None and v["lift"] >= RULE["val_lift"] and v["n"] >= 50:
            keep.append(r)
    keep.sort(key=lambda r: (-(r["val"]["p"] or 0), -(r["is"]["lift"] or 0)))
    final, sets = [], []
    for r in keep:
        s = B.rule(r["conds"])
        sc = s.bit_count()
        if any((s & t).bit_count() / max(1, min(sc, t.bit_count())) > OVERLAP_MAX for t in sets):
            continue
        r["val"] = eval_rule(rows_val, lab, r["conds"])
        final.append(r)
        sets.append(s)
        if len(final) >= KEEP_FINAL:
            break
    return final


def check_pred(ck):
    _, _, k, op, v = ck
    return cond_pred((k, op, v))


def check_stats(rows: list, labs=("A", "B")) -> dict:
    """飆股體質檢查每一項：符合時之後變飆股的比例（p）、全體比例（base）；以及「符合幾項」各組的比例。"""
    hit = {ck[0]: pack([check_pred(ck)(r["f"]) for r in rows]) for ck in CHECKS}
    cnt = [0] * len(rows)
    for m in hit.values():
        for j in ones(m):
            cnt[j] += 1
    out: dict = {"items": {}, "count": {}}
    for ck in CHECKS:
        out["items"][ck[0]] = {"name": ck[1]}
    for lab in labs:
        B = bits(rows, lab)
        n_all, p_all = B.count(B.valid)
        base = p_all / n_all if n_all else None
        for ck in CHECKS:
            n, pos = B.count(hit[ck[0]])
            out["items"][ck[0]][lab] = {"n": n, "pos": pos, "p": _r(pos / n) if n else None, "base": _r(base),
                                        "lift": _r(pos / n / base) if n and base else None}
        rowsc = []
        for k in range(len(CHECKS) + 1):
            n, pos = B.count(pack([x == k for x in cnt]))
            rowsc.append({"k": k, "n": n, "pos": pos, "p": _r(pos / n) if n else None,
                          "lift": _r(pos / n / base) if n and base else None})
        out["count"][lab] = {"base": _r(base), "rows": rowsc}
    return out


# 頁面上的條件寫法（只影響顯示，不影響規則）
SHORT = {"tt_n": "趨勢樣板通過項數", "tt_all": "趨勢樣板 8 項全過", "rs": "RS", "d52h": "距 52 週高點", "r120": "近 120 日漲幅",
         "lu20": "近 20 日漲停次數", "vdry": "10 日均量 ÷ 50 日均量", "ry": "月營收年增", "ry3": "近 3 月營收年增",
         "racc": "營收年增加速", "rnh12": "月營收創 12 個月新高", "rnha": "月營收創歷史新高", "ey": "最新季 EPS 年增",
         "eacc": "EPS 年增加速", "gm": "毛利率", "gmd": "毛利率比去年同季", "om": "營益率", "omd": "營益率比去年同季",
         "c33": "連三季變好（EPS、營收、毛利率）", "roe": "近四季 ROE", "cap": "市值", "liq": "20 日均成交值"}
PCT_PT = ("racc", "eacc", "gmd", "omd")             # 百分點


def cond_text(cond) -> str:
    k, op, v = cond
    nm = SHORT.get(k, FNAME.get(k, k))
    if op == "=":
        return nm
    if k == "tt_n" and op == ">=":
        return "趨勢樣板 8 項全過" if v >= 8 else f"趨勢樣板至少 {v:g} 項"
    if k == "lu20" and op == ">=":
        return "近 20 日有漲停" if v <= 1 else f"近 20 日漲停至少 {v:g} 次"
    if k == "roe" and op == "<=" and v <= 0:
        return "近四季 ROE ≤ 0%（近一年沒賺錢）"
    if k == "cap":
        val = f"{v / 1e8:,.0f} 億"
    elif k == "liq":
        val = f"{v / 1e8:,.1f} 億"
    elif k in PCT_PT:
        val = f"{v * 100:+.0f} 個百分點" if abs(v) >= 0.01 else f"{v * 100:+.1f} 個百分點"
    elif k in ("ry", "ry3", "ey", "d52h", "r120"):
        val = f"{v * 100:+.0f}%"
    elif k in ("gm", "om", "roe"):
        val = f"{v * 100:.0f}%"
    elif k == "vdry":
        val = f"{v:.2f} 倍"
    elif k in ("rs", "tt_n", "lu20"):
        val = f"{v:g}"
    else:
        val = f"{v:g}"
    return f"{nm} {'≥' if op == '>=' else '≤' if op == '<=' else '>'} {val}"


def cond_value_text(cond, v) -> str:
    """那一檔的實際數字＋規則要多少（只影響顯示；例「強度 96（要 90 以上）」「近 20 日漲停 2 次」）。沒有數字＝cond_text。"""
    k, op, thr = cond
    nm = SHORT.get(k, FNAME.get(k, k))
    if op == "=":
        return nm
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        return cond_text(cond)
    if k == "lu20" and op == ">=" and thr <= 1:
        return f"近 20 日漲停 {v:.0f} 次"
    if k == "rs":
        nm = "強度"

    def fmt(x):
        if k == "cap":
            return f"{x / 1e8:,.0f} 億"
        if k == "liq":
            return f"{x / 1e8:,.1f} 億"
        if k in PCT_PT:
            return f"{x * 100:+.0f} 個百分點"
        if k in ("ry", "ry3", "ey", "d52h", "r120"):
            return f"{x * 100:+.0f}%"
        if k in ("gm", "om", "roe"):
            return f"{x * 100:.0f}%"
        if k == "vdry":
            return f"{x:.2f} 倍"
        return f"{x:.0f}" if k in ("rs", "tt_n", "lu20") else f"{x:g}"
    side = "以上" if op in (">=", ">") else "以下"
    t = fmt(thr)
    return f"{nm} {fmt(v)}（要 {t}{' ' if t[-1].isdigit() or t[-1] == '%' else ''}{side}）"


# ── 頁面：研究結果檔 → 頁面資料 ────────────────────────────────────────────────
RES_FILE = "super_research.json"


def load_res() -> dict | None:
    from . import store
    res = store.read_json(RES_FILE, None)
    return res if res and res.get("ver") == VER else None


# 2026-10-16 保留期結果出來之後決定（docs/lab_company_plan.md 第 7 節）：「一年翻倍」（B）的 5 條規則 2023 年起轉弱
# （命中只有全體 1.4 倍、一年後中位數 −16%、只有三分之一賺錢）→ 不放進候選，頁面只列出成績。規則本身不改。
USE_LABELS = ("A",)


def live_rules(res: dict | None) -> list[tuple[str, list]]:
    """研究定案、而且保留期仍有效的規則 → [(標籤, 條件)]（頁面的規則序號照這個順序）。"""
    out = []
    for L in USE_LABELS:
        for r in (((res or {}).get("labels") or {}).get(L) or {}).get("rules") or []:
            out.append((L, [tuple(c) for c in r["conds"]]))
    return out


def page_data(res: dict | None, hits: dict | None, feats: dict | None = None, names: dict | None = None) -> dict:
    """頁面用：體質檢查各項與「符合幾項」的過去比例、規則（文字與三段期間成績）、今天符合規則的股票。
    feats＝{代號: x9t 列（dict）} 給候選清單帶幾個數字。"""
    if not res:
        return {}
    ch = (res.get("checks") or {}).get("all") or {}
    ck = {k: {L: {x: v[L].get(x) for x in ("p", "base", "n", "lift")} for L in LABELS if v.get(L)}
          for k, v in (ch.get("items") or {}).items()}
    rules = []
    for L in USE_LABELS:
        lab = (res.get("labels") or {}).get(L) or {}
        for r in lab.get("rules") or []:
            rules.append({"lab": L, "txt": "、".join(cond_text(tuple(c)) for c in r["conds"]), "is": r.get("is"),
                          "val": r.get("val"), "ho": r.get("ho"), "ex": r.get("ex")})
    labs = {L: {**{k: ((res.get("labels") or {}).get(L) or {}).get(k)
                   for k in ("base", "base_dist", "tried", "is_pass", "val_pass", "union", "yearly")},
                "n_rules": len((((res.get("labels") or {}).get(L)) or {}).get("rules") or []), "use": L in USE_LABELS}
            for L in LABELS}
    cand = []
    for c, ix in sorted((hits or {}).items()):
        r = (feats or {}).get(c) or {}
        cand.append([c, (names or {}).get(c, c), ix, r.get("px"), r.get("rs"), r.get("ry3"), r.get("ey"), r.get("d52h"),
                     r.get("cap")])
    cand.sort(key=lambda x: (-len(x[2]), -(x[4] or 0)))
    return {"v": res.get("ver"), "asof": res.get("asof"), "last": res.get("last"), "n": res.get("n"),
            "codes": res.get("codes"), "ck": ck, "cnt": ch.get("count"), "rules": rules, "labs": labs,
            "hits": {c: ix for c, ix in (hits or {}).items()}, "cand": cand,
            "spec": {"labels": LABELS, "cap_min": CAP_MIN, "is": IS, "val": VAL, "ho": HO, "use": list(USE_LABELS)}}
