"""個股深度報告的評等與目標價規格。

VER 2：2026-10-30（使用者：「我不要失真的數據」）。VER 1 的同業倍數是「近四季本益比」，卻乘在「未來 12 個月 EPS」上（口徑不一致），
沒有法人共識時又用營收動能自己推估 EPS。VER 2 的原則：**倍數和它乘的 EPS 一定是同一把尺，不自己做預估**。

- **共識法（fwd）**：本公司有法人共識（≥ CONS_MIN 位），而且同業有 ≥ PEER_MIN 家也有共識 →
  基數＝本公司未來 12 個月 EPS（F12M）；倍數範圍＝同業「未來 12 個月本益比」（同一個加權法算的）第 25～75 百分位，預設＝中位數。
  本公司過去的本益比是近四季口徑，只當參考、不進範圍。
- **近四季法（ttm）**：其他情況 → 基數＝已公布的近四季 EPS；倍數範圍＝本公司近 BAND_YEARS 年每月本益比（月底收盤 ÷ 當時已公布的近四季 EPS，
  只收 0～BAND_PE_MAX 倍）與同業現在本益比（近四季）的第 25～75 百分位，可用範圍＝[兩個第 25 取小, 兩個第 75 取大]，
  預設＝兩個中位數的平均（同業不到 PEER_MIN 家只用本公司）。
- **淨值比法**：金融保險、基數 ≤ 0、或現價 ÷ 基數 > PE_MAX，而且每股淨值 > 0 → 最近一季每股淨值 × 淨值比；
  範圍取法同近四季法（本公司近 5 年＋同業現在，都是最近一季淨值口徑，只收 0～BAND_PB_MAX 倍）。都不行 → 暫不評等。
- **F12M EPS**＝今年預估 × w ＋ 明年預估 ×（1 − w），w＝報告日之後今年（美股＝目前的會計年度）還剩幾個整月 ÷ 12；
  共識要 ≥ CONS_MIN 位分析師。沒有共識就不算 F12M（不用營收動能推估）。
- 撰寫者可以在範圍內選別的倍數，要寫原因。目標價進位 TICK_TP；評等：上檔空間 ≥ BUY_UP 買進、≤ SELL_DN 減碼、中間中立。
- 三個情境：悲觀＝基數 ×（1 − SCEN_EPS）× 範圍下緣；基本＝目標價；樂觀＝基數 ×（1 + SCEN_EPS）× 範圍上緣（淨值比法不加減 SCEN_EPS）。
- 法人共識目標價只當對照。要改就 VER＋1、寫進規劃文件，不在舊版本上改。

VER 1（2026-10-29）：基數＝F12M（沒有共識＝近四季 EPS × 營收動能，夾 0.7～1.5）；範圍＝本公司近 5 年本益比（近四季）＋同業現在本益比（近四季）。
臻鼎-KY 樣本（中立、目標價 560 元）照 VER 1 算，留著當評等歷史。
"""
from __future__ import annotations

from datetime import date

VER = 2
SPEC_DATE = "2026-10-30"

HORIZON_M = 12
CONS_MIN = 3
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


def year_weight(d: str, fy_end: int = 12) -> float:
    """報告日之後「今年」還剩幾個整月 ÷ 12（報告日那個月不算）；fy_end＝會計年度最後一個月（台股 12，美股看公司）。"""
    m = date.fromisoformat(d).month
    return ((fy_end - m) % 12) / 12


def f12m(d: str, eps_y: float | None, eps_y1: float | None, fy_end: int = 12) -> float | None:
    if eps_y is None or eps_y1 is None:
        return None
    w = year_weight(d, fy_end)
    return w * eps_y + (1 - w) * eps_y1


def basis(company_cons: bool, peer_fwd_n: int) -> str:
    """'fwd'＝共識法（本公司有共識、同業 ≥ PEER_MIN 家有未來本益比）；'ttm'＝近四季法。"""
    return "fwd" if company_cons and peer_fwd_n >= PEER_MIN else "ttm"


def fwd_range(peer_fwd: dict | None) -> dict | None:
    """共識法的倍數範圍：同業未來本益比第 25～75 百分位，預設＝中位數；同業不到 PEER_MIN 家 → None。"""
    if not peer_fwd or peer_fwd.get("n", 0) < PEER_MIN:
        return None
    return {"lo": peer_fwd["p25"], "hi": peer_fwd["p75"], "dflt": peer_fwd["p50"]}


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
    """近四季法與淨值比法（兩邊同一個口徑）→ {lo, hi, dflt}；同業不到 PEER_MIN 家只用本公司；本公司沒有區間只用同業。"""
    if peer and peer.get("n", 0) < PEER_MIN:
        peer = None
    if not own and not peer:
        return None
    parts = [b for b in (own, peer) if b]
    return {"lo": min(b["p25"] for b in parts), "hi": max(b["p75"] for b in parts),
            "dflt": sum(b["p50"] for b in parts) / len(parts)}


def method(eps: float | None, px: float | None, bvps: float | None, industry: str | None) -> str:
    """eps＝基數（共識法 F12M、近四季法近四季 EPS）→ 'pe'／'pb'／'none'。"""
    pb_ok = bvps is not None and bvps > 0
    if industry in PB_INDUSTRIES:
        return "pb" if pb_ok else "none"
    if eps is not None and eps > 0 and px and px / eps <= PE_MAX:
        return "pe"
    return "pb" if pb_ok else "none"


def scenarios(base_val: float | None, rng: dict | None, tp: float | None, mk: str = "tw", pe: bool = True) -> dict | None:
    """base_val＝基數 EPS（本益比法，±SCEN_EPS）或每股淨值（淨值比法，不加減）。"""
    if not base_val or not rng or not tp:
        return None
    e = SCEN_EPS if pe else 0.0
    return {"bear": round_tp(base_val * (1 - e) * rng["lo"], mk), "base": tp,
            "bull": round_tp(base_val * (1 + e) * rng["hi"], mk)}
