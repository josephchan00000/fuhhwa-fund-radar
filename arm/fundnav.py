"""共同基金 NAV 歷史（data/fund_nav_history.json）——總覽表「近一週／近一月」報酬資料層。

官網 /api/fund 的多期報酬只有 ytd/3m/6m/1y/2y/3y/since、**沒有 1週/1月**，故自建
NAV 時間序列自算（與舊 ETF 管線的 arm/navhist.py〔sqlite〕無關，勿混用）：
  · 結構：{fund_id: {"YYYY/MM/DD": nav, ...}}（日期＝官網 NAV 日、非抓取日）
  · 累積：scripts/fetch_holdings.py 每日抓完呼叫 record() 追加當日 NAV；
    首次由 scripts/backfill_fund_nav.py 走 git 歷史回填（_index.json 每日快照）。
  · 計算：ret_pct() 以最新 NAV 日回推 7/30 個「日曆日」前的最後一筆 NAV 為基準，
    並有「基準日須接近目標日」防呆（tol 天內）——序列稀疏寧回 None 也不算錯值
    （同 arm/etfwatch 報酬計算慣例）。史料未滿 30 天前「1月」欄自然顯示 —，
    CI 每日累積後自動補齊。

⚠ data/fund_nav_history.json 必須入庫（.gitignore 已加例外）：它是跨日累積的
  持久層，CI 從零開始會讓 1週/1月整片變 —（同 etf_watch.json 踩過的坑）。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data" / "fund_nav_history.json"


def _parse_date(s: str | None) -> date | None:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def load() -> dict[str, dict[str, float]]:
    if not PATH.exists():
        return {}
    try:
        d = json.loads(PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(hist: dict[str, dict[str, float]]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {fid: dict(sorted(ser.items())) for fid, ser in sorted(hist.items())}
    PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


def record(docs: list[dict]) -> int:
    """把基金 doc（含 fund_id/nav/nav_date）的當日 NAV 併入歷史並落檔。
    回傳新增筆數；全空輸入不動既有落檔（防呆：抓取全失敗時不得清史）。"""
    added = 0
    hist = load()
    for d in docs or []:
        fid, nav = str(d.get("fund_id") or d.get("id") or ""), d.get("nav")
        dt = _parse_date(d.get("nav_date"))
        if not fid or nav is None or dt is None:
            continue
        key = dt.strftime("%Y/%m/%d")
        ser = hist.setdefault(fid, {})
        if ser.get(key) != nav:
            ser[key] = float(nav)
            added += 1
    if added:
        save(hist)
    return added


def ret_pct(series: dict[str, float] | None, ref_date: str | None,
            ref_nav: float | None, days: int, tol: int) -> float | None:
    """近 N 日報酬%：ref_nav 對「ref_date − days（日曆日）」前最後一筆 NAV。
    基準日早於目標日超過 tol 天（序列稀疏／史料不足）→ 回 None 不硬算。"""
    ref = _parse_date(ref_date)
    if not series or ref is None or not ref_nav:
        return None
    target = ref - timedelta(days=days)
    base_d, base_v = None, None
    for k, v in series.items():
        d = _parse_date(k)
        if d is None or d > target or not v:
            continue
        if base_d is None or d > base_d:
            base_d, base_v = d, v
    if base_d is None or (target - base_d).days > tol:
        return None
    return round((float(ref_nav) / float(base_v) - 1.0) * 100.0, 2)
