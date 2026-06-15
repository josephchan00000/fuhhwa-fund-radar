"""資料品質閘門 —— 落實「績效 + 張數 100% 正確」的硬需求。

CRITICAL 檢查不通過 → 該指標家族不得出訊號（fail loud，寧可不報也不報錯）。
其餘情報（競品 / 社群）不走此閘門。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Check:
    name: str
    level: str   # CRITICAL / WARN
    ok: bool
    detail: str


@dataclass
class QualityReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, name, level, ok, detail=""):
        self.checks.append(Check(name, level, ok, detail))

    @property
    def critical_failed(self) -> list[Check]:
        return [c for c in self.checks if c.level == "CRITICAL" and not c.ok]

    @property
    def passed(self) -> bool:
        return not self.critical_failed

    def render(self) -> str:
        lines = []
        for c in self.checks:
            mark = "✅" if c.ok else ("❌" if c.level == "CRITICAL" else "⚠️")
            lines.append(f"  {mark} [{c.level}] {c.name} — {c.detail}")
        return "\n".join(lines)


def gate_performance(series: list[tuple[str, float, int]], expected_latest: str,
                     code: str) -> QualityReport:
    """績效資料把關：序列完整、日期吻合、收盤皆正數。"""
    r = QualityReport()
    r.add("價格序列非空", "CRITICAL", len(series) >= 2, f"{code} 取得 {len(series)} 筆")
    if series:
        dates = [d for d, _, _ in series]
        r.add("日期遞增不重複", "CRITICAL", dates == sorted(set(dates)),
              "日期序列正常" if dates == sorted(set(dates)) else "有重複/亂序")
        r.add("最新交易日吻合", "CRITICAL", series[-1][0] == expected_latest,
              f"序列最新 {series[-1][0]} / 預期 {expected_latest}")
        bad = [d for d, c, _ in series if c is None or c <= 0]
        r.add("收盤價皆為正數", "CRITICAL", not bad, f"異常筆數 {len(bad)}")
    return r


def _record_holdings(h: list[dict]) -> tuple[list[dict], str]:
    """挑出「主要持有標的」：債券基金用 bond 區段，其餘用 equity；期貨為避險疊加不計。"""
    bonds = [x for x in h if x.get("kind") == "bond"]
    if bonds:
        return bonds, "bond"
    equities = [x for x in h if x.get("kind", "equity") == "equity"]
    return equities, "equity"


def gate_holdings(snap: dict, code: str, asset_class: str | None = None) -> QualityReport:
    """張數/NAV 把關，依資產類別分流：
    NAV×單位數≈AUM（通用）、主要標的權重合計≈100%、正性檢查
    （股票檢股數>0、債券檢市值>0；期貨避險可為負故不計入正性與權重）。
    """
    r = QualityReport()
    h = snap["holdings"]
    nav, aum, units = snap["nav"], snap["aum"], snap["units"]

    if nav and aum and units:
        recon = units * nav
        diff = abs(recon - aum) / aum
        r.add("NAV×單位數≈AUM", "CRITICAL", diff < 0.005,
              f"推算 {recon:,.0f} vs 揭露 {aum:,.0f}（差 {diff:.4%}）")
    else:
        r.add("NAV/AUM/單位數齊全", "CRITICAL", False, "缺 NAV/AUM/單位數")

    record, kind = _record_holdings(h)
    label = "債券" if kind == "bond" else "持股"
    wsum = sum(x["weight"] or 0 for x in record)
    r.add(f"{label}權重合計≈100%", "CRITICAL", 95 <= wsum <= 105, f"合計 {wsum:.2f}%（{len(record)} 檔）")

    if kind == "bond":
        bad = [x for x in record if not x.get("market_value") or x["market_value"] <= 0]
        r.add("債券市值皆為正", "CRITICAL", not bad, f"{code} 共 {len(record)} 檔，異常 {len(bad)}")
    else:
        bad = [x for x in record if not x.get("shares") or x["shares"] <= 0]
        r.add("持股股數皆為正", "CRITICAL", not bad, f"{code} 共 {len(record)} 檔，異常 {len(bad)}")
    return r


def gate_premium(close: float, nav: float) -> QualityReport:
    """收盤 vs NAV 交叉驗證：折溢價在合理區間（否則疑似資料對不上）。"""
    r = QualityReport()
    pd = (close - nav) / nav
    r.add("折溢價合理(|x|<10%)", "WARN", abs(pd) < 0.10,
          f"折溢價 {pd:+.2%}（收盤 {close} / NAV {nav}）")
    return r
