"""個股深度報告的評等與目標價規格。VER 1：2026-10-29，寫在看任何一份報告的估值結果之前（docs/lab_equity_report_plan.md 第 6 節）。

使用者 2026-10-29 選「照投行給評等與目標價」：看 12 個月；目標價＝未來 12 個月 EPS（F12M）× 目標本益比
（淨值比法＝最近一季每股淨值 × 目標淨值比）；評等由上檔空間機械決定。

F12M EPS：有法人共識（≥ CONS_MIN 位、資料在 fcst.STALE_DAYS 天內）＝今年預估 × w ＋ 明年預估 ×（1 − w），
  w＝報告日之後今年還剩幾個月 ÷ 12（10/29 → 11、12 月 → 2/12）；
  沒有＝近四季 EPS × 營收動能（最近 3 個月營收 ÷ 去年同期；美股用最近一季營收年增），倍數夾在 MOM_CLIP。
方法：F12M > 0 而且現價 ÷ F12M ≤ PE_MAX → 本益比法；金融保險、F12M ≤ 0、或倍數 > PE_MAX 而且每股淨值 > 0 → 淨值比法；
  都不行 → 暫不評等。
目標倍數的範圍：本公司近 BAND_YEARS 年每月的本益比（近四季 EPS，只收 0～BAND_PE_MAX 倍）第 25、50、75 百分位，
  和同業（≥ PEER_MIN 家）現在本益比的第 25、50、75 百分位；可用範圍＝[兩個第 25 取小, 兩個第 75 取大]；
  預設＝兩個中位數的平均（同業不夠只用本公司）。撰寫者可以在範圍內選別的倍數，要寫原因。淨值比法同樣做法（BAND_PB_MAX）。
目標價進位：TICK_TP；評等：上檔空間 ≥ BUY_UP 買進、≤ SELL_DN 減碼、中間中立。
三個情境：悲觀＝F12M × (1 − SCEN_EPS) × 範圍下緣；基本＝目標價；樂觀＝F12M × (1 + SCEN_EPS) × 範圍上緣
  （淨值比法用每股淨值、不加減 SCEN_EPS）。
法人共識目標價只當對照。要改就 VER＋1、寫進規劃文件，不在舊版本上改。
"""
from __future__ import annotations

from datetime import date

VER = 1
SPEC_DATE = "2026-10-29"

HORIZON_M = 12
CONS_MIN = 3
MOM_CLIP = (0.7, 1.5)
PE_MAX = 80.0
BAND_YEARS = 5
BAND_PE_MAX = 100.0
BAND_PB_MAX = 20.0
PEER_MIN = 3
PB_INDUSTRIES = ("金融保險",)
BUY_UP = 0.15
SELL_DN = -0.10
RATINGS = ("買進", "中立", "減碼", "暫不評等")
SCEN_EPS = 0.15
# 目標價進位：(上限, 單位)；台股以元、美股以美元；最後一列的上限＝無窮大
TICK_TP = {"tw": ((50, 0.5), (100, 1.0), (500, 5.0), (1000, 10.0), (float("inf"), 50.0)),
           "us": ((50, 0.5), (float("inf"), 1.0))}
PEER_N = 6
PEER_LEADERS = 2
PEER_SWAP_MAX = 3


def rating(tp: float | None, px: float | None) -> str:
    if not tp or not px or tp <= 0 or px <= 0:
        return "暫不評等"
    up = tp / px - 1
    if up >= BUY_UP - 1e-9:
        return "買進"
    if up <= SELL_DN + 1e-9:
        return "減碼"
    return "中立"


def round_tp(x: float, mk: str = "tw") -> float:
    for top, unit in TICK_TP[mk]:
        if x < top:
            return round(round(x / unit) * unit, 2)
    raise ValueError(x)


def year_weight(d: str) -> float:
    """報告日之後今年還剩幾個月 ÷ 12（報告日那個月不算）。"""
    m = date.fromisoformat(d).month
    return (12 - m) / 12


def f12m(d: str, eps_y: float | None, eps_y1: float | None) -> float | None:
    if eps_y is None or eps_y1 is None:
        return None
    w = year_weight(d)
    return w * eps_y + (1 - w) * eps_y1


def mom_factor(r3: float | None, r3_ly: float | None) -> float | None:
    if not r3 or not r3_ly or r3_ly <= 0:
        return None
    lo, hi = MOM_CLIP
    return min(max(r3 / r3_ly, lo), hi)


def pctl(xs: list, q: float) -> float | None:
    """線性內插百分位（同 numpy 預設）。"""
    v = sorted(x for x in xs if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    i = int(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * (k - i)


def band(xs: list) -> dict | None:
    v = [x for x in xs if x is not None]
    if not v:
        return None
    return {"p25": pctl(v, 0.25), "p50": pctl(v, 0.5), "p75": pctl(v, 0.75), "n": len(v)}


def mult_range(own: dict | None, peer: dict | None) -> dict | None:
    """→ {lo, hi, dflt}；同業不到 PEER_MIN 家只用本公司；本公司沒有區間只用同業。"""
    if peer and peer.get("n", 0) < PEER_MIN:
        peer = None
    if not own and not peer:
        return None
    parts = [b for b in (own, peer) if b]
    return {"lo": min(b["p25"] for b in parts), "hi": max(b["p75"] for b in parts),
            "dflt": sum(b["p50"] for b in parts) / len(parts)}


def method(f12m_eps: float | None, px: float | None, bvps: float | None, industry: str | None) -> str:
    """→ 'pe'／'pb'／'none'。"""
    pb_ok = bvps is not None and bvps > 0
    if industry in PB_INDUSTRIES:
        return "pb" if pb_ok else "none"
    if f12m_eps is not None and f12m_eps > 0 and px and px / f12m_eps <= PE_MAX:
        return "pe"
    return "pb" if pb_ok else "none"


def scenarios(base_val: float | None, rng: dict | None, tp: float | None, mk: str = "tw", pe: bool = True) -> dict | None:
    """base_val＝F12M EPS（本益比法，±SCEN_EPS）或每股淨值（淨值比法，不加減）。"""
    if not base_val or not rng or not tp:
        return None
    e = SCEN_EPS if pe else 0.0
    return {"bear": round_tp(base_val * (1 - e) * rng["lo"], mk), "base": tp,
            "bull": round_tp(base_val * (1 + e) * rng["hi"], mk)}
