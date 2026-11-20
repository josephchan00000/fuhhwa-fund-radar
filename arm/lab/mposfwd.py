"""股市位階和之後漲跌的關係（規格 arm/lab/mposfwdspec.py VER 1；docs/lab_earnings_plan.md 第 12 節）。只讀已經算好的位階與指數收盤。

  forward(px, i, H)   → 第 i 天之後 H 個交易日的漲跌（%）
  episodes(idx)       → 一串交易日的位置 → 幾段（規格第 4 點）
  compute(X, px)      → {"any": {H: 統計}, "z": {區: {H: 統計＋判定}}, "split": 前後兩半的分界日}
統計＝{"n": 天數, "ep": 段數, "avg", "med", "up": 上漲比例 %, "min": 最差, "h": [[前一半平均, 那一半任一天平均, 段數], [後一半…]], "ok": 判定, "why": 沒過的原因}
"""
from __future__ import annotations

import statistics as st

from . import mposfwdspec as S


def zone(x: float) -> str:
    from .mpos import label
    return label(x)


def forward(px: list, i: int, H: int):
    j = i + H
    if j >= len(px) or not px[i] or not px[j]:
        return None
    return (px[j] / px[i] - 1) * 100


def episodes(idx: list[int]) -> int:
    """規格第 4 點：連續在這一區的日子算一段；離開不到 GAP 個交易日又回來，併成同一段。idx＝交易日的位置（排好）。"""
    n, last = 0, None
    for i in idx:
        if last is None or i - last > S.GAP:
            n += 1
        last = i
    return n


def _st(rs: list[float], idx: list[int]) -> dict:
    if not rs:
        return {"n": 0, "ep": 0}
    return {"n": len(rs), "ep": episodes(idx), "avg": round(st.mean(rs), 2), "med": round(st.median(rs), 2),
            "up": round(sum(1 for r in rs if r > 0) / len(rs) * 100, 1), "min": round(min(rs), 2)}


def compute(X: dict, px: list) -> dict:
    """X＝mpos.compute 的結果（cal、v 與 px 同一條日期）。"""
    v, cal = X["v"], X["cal"]
    out: dict = {"any": {}, "z": {z: {} for z in S.ZONES}, "split": {}}
    for H in S.HORIZONS:
        days = [(i, r) for i in range(len(v)) if v[i] is not None for r in [forward(px, i, H)] if r is not None]
        if not days:
            continue
        mid = days[len(days) // 2][0]
        out["split"][H] = cal[mid]
        halves = [[d for d in days if d[0] < mid], [d for d in days if d[0] >= mid]]
        a = _st([r for _, r in days], [i for i, _ in days])
        a["h"] = [round(st.mean(r for _, r in h), 2) if h else None for h in halves]
        out["any"][H] = a
        for z in S.ZONES:
            zd = [(i, r) for i, r in days if zone(v[i]) == z]
            s = _st([r for _, r in zd], [i for i, _ in zd])
            hs = []
            for k, h in enumerate(halves):
                hz = [(i, r) for i, r in h if zone(v[i]) == z]
                hs.append([round(st.mean(r for _, r in hz), 2) if hz else None, a["h"][k], episodes([i for i, _ in hz])])
            s["h"] = hs
            s["ok"], s["why"] = verdict(s, a, H)
            out["z"][z][H] = s
    return out


def verdict(s: dict, a: dict, H: int) -> tuple[bool, str]:
    """規格第 5 點：三個條件都過才算有差別；回 (過不過, 沒過的原因)。"""
    if s.get("ep", 0) < S.MIN_EP:
        return False, f"只有 {s.get('ep', 0)} 段（至少要 {S.MIN_EP} 段）"
    d = s["avg"] - a["avg"]
    if abs(d) < S.MIN_DIFF[H]:
        return False, f"和任一天只差 {d:+.1f}".replace("-", "−") + f" 個百分點（至少要 {S.MIN_DIFF[H]:g}）"
    for k, (zh, ah, ep) in enumerate(s["h"]):
        part = "前" if k == 0 else "後"
        if zh is None or ep < 1:
            return False, f"{part}一半沒有這一區"
        if (zh - ah) * d <= 0:
            return False, f"{part}一半方向相反（這一區 {zh:+.1f}%、任一天 {ah:+.1f}%）"
    return True, ""
