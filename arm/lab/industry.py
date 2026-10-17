"""產業比較（docs/lab_forward_plan.md 第 3.2、3.3 節；使用者 2026-10-16：只顯示當參考，不拿來篩股）。

產業別＝證交所／櫃買中心的產業別（stockmeta.industry_map，34 類；「電子零組件業」這種類別範圍很大）。
每天建頁時用自己的資料算，和 x9t.json 同一批股票、同一天（company.market_table 裡呼叫）：

- 產業營收：最新可得的營收月（每月 10 日起才算可得，同 superx／packtest.rev_forms）。
  只用「這段期間與去年同期都有營收」的公司加總後相比——公司數會變（新上市、下市），不能直接拿總和比。
  近 3 個月合計同理；加速＝近 3 個月年增 − 再前 3 個月年增（兩段各自用兩段都有資料的公司）。
  另給公司近 3 個月年增的中位數：加總會被大公司帶著走（半導體業≈台積電），中位數看的是一般公司。
- 產業股價：成員近 20、60 個交易日漲跌（還原價）的中位數，依 60 日排名（成員有股價的不到 5 檔不排）。
- 名單：每個產業有幾檔在飆股名單裡。
個股在同業中的名次由頁面用 x9t.json 自己排（x9t 每列多一欄產業代號 ii，見 company.market_table）。
"""
from __future__ import annotations

import statistics

COLS = ["ind", "n", "ry1", "ry3", "racc", "med3", "r20", "r60", "rk", "nw"]
MIN_RANK = 5                                   # 有股價的成員少於這個數不排名


def ym_shift(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return f"{y:04d}-{m:02d}"


def _sum_yoy(members, rev, months) -> tuple[float | None, int]:
    """同一批公司（這幾個月與去年同月都有營收）加總後的年增率、公司數。"""
    num = den = 0.0
    n = 0
    prev = [ym_shift(m, -12) for m in months]
    for c in members:
        r = rev.get(c) or {}
        a = [r.get(m) for m in months]
        b = [r.get(m) for m in prev]
        if any(x is None for x in a + b) or sum(b) <= 0:
            continue
        num += sum(a)
        den += sum(b)
        n += 1
    return (num / den - 1 if den > 0 else None), n


def _co_yoy(r: dict, months) -> float | None:
    a = [r.get(m) for m in months]
    b = [r.get(ym_shift(m, -12)) for m in months]
    if any(x is None for x in a + b) or sum(b) <= 0:
        return None
    return sum(a) / sum(b) - 1


def _ret(px, i: int, n: int) -> float | None:
    if px is None or px.first is None or px.last is None or px.first > i - n or px.last < i:
        return None
    a, b = px.c[i], px.c[i - n]
    return a / b - 1 if a and b else None


def _p(x, d=1):
    return None if x is None else round(x * 100, d)


def table(codes, ind_map: dict, rev: dict, ym: str | None, pxs: dict, i: int, watch=None) -> dict:
    """→ {"ym", "cols", "rows": [[產業, 檔數, 當月營收年增%, 近3月年增%, 加速(百分點), 公司中位數%, 20日%, 60日%, 名次, 名單檔數]…]}
    依 60 日股價中位數由高到低排；沒有名次的排最後。"""
    groups: dict[str, list] = {}
    for c in codes:
        nm = ind_map.get(c)
        if nm:
            groups.setdefault(nm, []).append(c)
    m3 = [ym_shift(ym, -k) for k in range(3)] if ym else []
    p3 = [ym_shift(ym, -k) for k in range(3, 6)] if ym else []
    watch = watch or {}
    rows = []
    for nm, mem in groups.items():
        fin = "金融" in nm                                 # 金融業的月營收含投資損益，年增率沒有可比性 → 不算
        ry1 = _sum_yoy(mem, rev, [ym])[0] if ym and not fin else None
        ry3 = _sum_yoy(mem, rev, m3)[0] if ym and not fin else None
        ryp = _sum_yoy(mem, rev, p3)[0] if ym and not fin else None
        cos = [x for x in (_co_yoy(rev.get(c) or {}, m3) for c in mem) if x is not None] if ym and not fin else []
        r20 = [x for x in (_ret(pxs.get(c), i, 20) for c in mem) if x is not None]
        r60 = [x for x in (_ret(pxs.get(c), i, 60) for c in mem) if x is not None]
        rows.append([nm, len(mem), _p(ry1), _p(ry3), _p(ry3 - ryp) if ry3 is not None and ryp is not None else None,
                     _p(statistics.median(cos)) if len(cos) >= 3 else None,
                     _p(statistics.median(r20)) if len(r20) >= 3 else None,
                     _p(statistics.median(r60)) if len(r60) >= 3 else None, None,
                     sum(1 for c in mem if c in watch), len(r60)])
    ranked = sorted((r for r in rows if r[7] is not None and r[10] >= MIN_RANK), key=lambda r: -r[7])
    for k, r in enumerate(ranked, 1):
        r[8] = k
    rows.sort(key=lambda r: (r[8] is None, r[8] or 0, r[0]))
    return {"ym": ym, "cols": COLS, "rows": [r[:10] for r in rows]}


def index_codes(codes, ind_map: dict) -> tuple[list[str], dict[str, int]]:
    """x9t 用：產業名稱清單＋每檔的產業代號（清單位置）。"""
    names = sorted({ind_map[c] for c in codes if ind_map.get(c)})
    pos = {n: k for k, n in enumerate(names)}
    return names, {c: pos[ind_map[c]] for c in codes if ind_map.get(c) in pos}
