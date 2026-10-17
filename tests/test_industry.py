"""產業比較（arm/lab/industry.py；docs/lab_forward_plan.md 第 3.2、3.3 節）。"""
from arm.lab import industry as IND


class _Px:
    def __init__(self, c, first=0):
        self.c, self.first, self.last = c, first, len(c) - 1


def _rev(base, g, months=("2025-04", "2025-05", "2025-06", "2025-07", "2025-08", "2025-09")):
    """去年同月 base、今年 base×(1+g)。"""
    out = {}
    for m in months:
        out[m] = base * (1 + g)
        out[IND.ym_shift(m, -12)] = base
    return out


def test_ym_shift():
    assert IND.ym_shift("2026-01", -1) == "2025-12" and IND.ym_shift("2025-12", 1) == "2026-01"
    assert IND.ym_shift("2026-09", -12) == "2025-09"


def test_table_sums_same_companies_and_ranks():
    imap = {"1": "甲", "2": "甲", "3": "甲", "4": "乙", "5": "乙", "6": "乙", "7": "金融保險"}
    rev = {"1": _rev(100, 0.5), "2": _rev(900, 0.1), "3": _rev(50, 0.2), "4": _rev(10, -0.1), "5": _rev(10, 0.0),
           "6": _rev(10, 0.1), "7": _rev(10, 1.0)}
    rev["3"].pop("2024-09")                                   # 少一個去年同月 → 不進「當月」比較
    up = [100.0] * 40 + [100 + k for k in range(21)]          # 近 20 日漲
    dn = [100.0] * 40 + [100 - k for k in range(21)]
    pxs = {c: _Px(up if c in "123" else dn) for c in "1234567"}
    t = IND.table(list("1234567"), imap, rev, "2025-09", pxs, 60, watch={"1": ["A"]})
    rows = {r[0]: dict(zip(IND.COLS, r)) for r in t["rows"]}
    a = rows["甲"]
    assert a["n"] == 3 and a["nw"] == 1
    assert a["ry1"] == round(((100 * 1.5 + 900 * 1.1) / 1000 - 1) * 100, 1)   # 「3」缺去年 9 月，不算
    assert a["ry3"] == 14.0                                    # 近 3 月：同一批（1、2）加總 1140／1000
    assert a["racc"] == round((14.0 - (1200 / 1050 - 1) * 100), 1)  # 前 3 月三家都有資料 → 各段各自用齊全的公司
    assert a["med3"] is None                                   # 近 3 月只有 2 家齊全，中位數至少要 3 家
    assert rows["乙"]["ry3"] == 0.0 and rows["乙"]["r20"] < 0
    assert rows["金融保險"]["ry3"] is None                     # 金融業不算營收年增
    assert a["rk"] is None                                     # 有股價的成員不到 5 檔不排名
    assert t["ym"] == "2025-09" and [r[0] for r in t["rows"]][-1] in ("甲", "乙", "金融保險")


def test_rank_needs_five_members():
    imap = {str(k): "丙" for k in range(6)} | {str(k): "丁" for k in range(6, 12)}
    up = [100.0] * 40 + [100 + 2 * k for k in range(61)]
    flat = [100.0] * 101
    pxs = {str(k): _Px(up if k < 6 else flat) for k in range(12)}
    t = IND.table([str(k) for k in range(12)], imap, {}, None, pxs, 100)
    assert [(r[0], r[8]) for r in t["rows"]] == [("丙", 1), ("丁", 2)]


def test_index_codes():
    names, ii = IND.index_codes(["1", "2", "3"], {"1": "乙", "2": "甲"})
    assert names == ["乙", "甲"] or names == sorted(["乙", "甲"])
    assert names[ii["1"]] == "乙" and names[ii["2"]] == "甲" and "3" not in ii
