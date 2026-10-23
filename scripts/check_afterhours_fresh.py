#!/usr/bin/env python3
"""盤後數據「當日完整性」看門狗（2026-08-03 使用者需求：三大法人沒更新、沒人通知）。

背景（同日兩個坑，缺的都是「可見性」）：
① `_missing_weekdays` 從 i=1 起算 → 盤後場次從不抓當日籌碼（已修：today_after 門檻）；
② GitHub cron 系統性遲到 1~3 小時、偶爾整班消失（實測 afterhours 15:40 班遲 3h16m、
   22:05 班當晚根本沒來）——兩者疊加時 run 全綠、無 commit、無任何警示，
   使用者要到自己打開網頁才發現當日數據沒上。本腳本把「時間到了、當日數據該在而不在」
   變成看得見的失敗，是「不要再犯」的最後防線。

三種模式（皆台北時間；非交易日一律無缺口）：
  --guard   盤後場次抓取前守門：目標數據已是今日／30 分鐘內剛抓過 → 印 SKIP（零請求早退，
            重複場次不放大對 TWSE/etfinfo 的請求量）；否則印 RUN。永遠 exit 0。
  --write   計算缺口 → 寫/清 data/afterhours_alert.json（儀表板紅章資料源；內容
            只含 date+missing、無時戳，健康且已清空時不重寫——避免每場次空 commit）。
            永遠 exit 0（記錄不擋發佈）。
  --assert  缺口非空 → exit 1（放在 workflow 最後一步：run 標 ❌、GitHub 寄 failure 信）。

時窗規則（交易日才斷言；15:05 前與時窗間為 grace 不斷言）：
  16:30 後：inst_total（三大法人）序列須含今日（證交所 ~15:00 公布、15:33 Routine 觸發）。
  22:45 後：margin_bal（融資融券，~21:30 公布）須含今日；全基金最新 nav_date
            不得早於上一交易日（境內 NAV 傍晚公布、海外 T+1——只驗「沒有連兩天斷更」，
            避免對正常 T+1 誤報）。

交易日判定：週一~五 且 **證交所官方休市表**（arm/twholidays；2026-10-13 起）未列為休市
（含 twholidays.ADHOC 颱風停止交易；年度表沒有颱風日，還沒補進 ADHOC 的另認市況段「M/D 因颱風休市」）。
舊版只讀 reports/macrocal/{today}.md 市況段——那是子代理每天依搜尋摘要重寫的文字，漏寫或誤寫
都會讓看門狗誤報或靜默放行；現僅在官方表未涵蓋該年時退回讀它（兩者不一致時印日誌）。
官方表與行事曆皆缺＝視為交易日：寧可誤報一次，也不要在「連新聞都沒產」的壞日子靜默。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from arm import clock, twholidays  # noqa: E402

ALERT_FP = ROOT / "data" / "afterhours_alert.json"
CHIPS_FP = ROOT / "data" / "macro_chips.json"
INDEX_FP = ROOT / "data" / "funds" / "_index.json"
MACROCAL_DIR = ROOT / "reports" / "macrocal"

_TW_STAT_RE = re.compile(r"台股\s*[：:]?\s*([^｜|；;。]+)")
_GUARD_FRESH_MIN = 30      # as_of 在 N 分鐘內＝剛有場次跑完，重複場次零請求早退
_HHMM = lambda h, m: h * 60 + m  # noqa: E731


def _load(fp: Path) -> dict | None:
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_trading_day(d: date, macrocal_text: str | None) -> bool:
    """台股今日是否交易。**證交所官方休市表優先**（arm/twholidays，2026-10-13 起）——
    舊版只看子代理寫的行事曆市況段，漏寫休市＝當天誤報紅燈、誤寫休市＝缺資料靜默放行。
    官方表未涵蓋該年才退回行事曆文字（缺檔視為交易日）；兩者不一致時印日誌、以官方為準。"""
    if d.weekday() >= 5:
        return False
    seg = next((p for p in re.split(r"[；;]", macrocal_text or "") if "市況" in p), "")
    m = _TW_STAT_RE.search(seg)
    text_closed = False
    if m and "休市" in m.group(1):
        # 市況段常預告「明天」休市（2026-09-24「台股 9/25 因中秋節休市」曾讓當日被判非交易日、
        # 看門狗整晚失明）→ 有寫日期就只認今天那一天；沒寫日期才視為當日休市。
        days = {(int(a), int(b)) for a, b in re.findall(r"(\d{1,2})/(\d{1,2})", m.group(1))}
        text_closed = not days or (d.month, d.day) in days
    official = twholidays.is_closed(d)
    if official is None:
        return not text_closed
    # 說明一律印 stderr：--guard 的 stdout 會整段寫進 GITHUB_OUTPUT，多一行就讓整班當掉
    # （2026-10-23 薔琵颱風：這一行警告混進判定，afterhours 第 24 秒就失敗）
    if official is False and m and twholidays.typhoon_said(m.group(1), d):
        print(f"  ⚠ 行事曆市況寫 {d} 因颱風休市，證交所年度表沒有（颱風停止交易不在年度表上）——當作休市；"
              "查證後請補進 arm/twholidays.ADHOC", file=sys.stderr)
        return False
    if macrocal_text is not None and text_closed != official:
        print(f"  ⚠ 行事曆市況與證交所官方休市表不一致：{d} 官方＝{'休市' if official else '交易日'}"
              f"、行事曆＝{'休市' if text_closed else '交易'}（以官方為準）", file=sys.stderr)
    return not official


def _macrocal_text(d: date) -> str | None:
    fp = MACROCAL_DIR / f"{d.isoformat()}.md"
    try:
        return fp.read_text(encoding="utf-8")
    except Exception:
        return None


def _prev_weekday(d: date) -> date:
    p = d - timedelta(days=1)
    while p.weekday() >= 5:
        p -= timedelta(days=1)
    return p


def _max_nav_date(index_doc: dict | None) -> date | None:
    """全基金最新 nav_date（格式 2026/07/31）。"""
    best = None
    for f in (index_doc or {}).get("funds") or []:
        raw = (f.get("nav_date") or "").replace("/", "-")
        try:
            d = date.fromisoformat(raw)
        except ValueError:
            continue
        best = d if (best is None or d > best) else best
    return best


def compute_missing(now: datetime, chips: dict | None, index_doc: dict | None,
                    trading: bool) -> list[str]:
    """回傳目前時點「該在而不在」的當日數據清單（人話，直接進儀表板紅章）。"""
    if not trading:
        return []
    hm = _HHMM(now.hour, now.minute)
    today_iso = now.date().isoformat()
    series = (chips or {}).get("series") or {}
    missing: list[str] = []
    if hm >= _HHMM(16, 30) and today_iso not in (series.get("inst_total") or {}):
        missing.append("當日三大法人買賣超")
    if hm >= _HHMM(22, 45):
        if today_iso not in (series.get("margin_bal") or {}):
            missing.append("當日融資融券餘額")
        nav = _max_nav_date(index_doc)
        if nav is None or nav < _prev_weekday(now.date()):
            missing.append(f"基金 NAV（最新僅到 {nav or '—'}）")
    return missing


def _parse_asof(chips: dict | None) -> datetime | None:
    raw = (chips or {}).get("as_of") or ""
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=clock.TW_TZ)
    except ValueError:
        return None


def guard_decision(now: datetime, chips: dict | None, trading: bool) -> str:
    """盤後場次抓取前守門：SKIP＝目標數據已到位／剛抓過，本場次零請求早退。"""
    hm = _HHMM(now.hour, now.minute)
    series = (chips or {}).get("series") or {}
    if trading and _HHMM(15, 5) <= hm < _HHMM(18, 0) \
            and now.date().isoformat() in (series.get("inst_total") or {}):
        return "SKIP"                      # 午後窗：當日籌碼已在（15:33 場次已成功）
    asof = _parse_asof(chips)
    if hm >= _HHMM(18, 0) and asof and (now - asof) <= timedelta(minutes=_GUARD_FRESH_MIN):
        return "SKIP"                      # 晚間窗：30 分鐘內剛有場次跑完（如 18:58 dispatch）
    return "RUN"


def write_alert(missing: list[str], today: date) -> bool:
    """寫/清警示檔；回傳是否有寫。健康且檔案本來就乾淨 → 不動檔（避免空 commit）。"""
    old = _load(ALERT_FP)
    doc = {"date": today.isoformat(), "missing": missing}
    if not missing and (old is None or not old.get("missing")):
        return False
    if old == doc:
        return False
    ALERT_FP.parent.mkdir(parents=True, exist_ok=True)
    ALERT_FP.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--guard", action="store_true")
    mode.add_argument("--assert", dest="assert_", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = ap.parse_args()

    now = clock.now_tw()
    today = now.date()
    chips = _load(CHIPS_FP)
    trading = is_trading_day(today, _macrocal_text(today))

    if args.guard:
        print(guard_decision(now, chips, trading))
        return 0

    missing = compute_missing(now, chips, _load(INDEX_FP), trading)
    if args.assert_:
        if missing:
            print(f"🔴 當日盤後數據未到（{now:%H:%M}）：{'、'.join(missing)}")
            return 1
        print(f"🟢 當日盤後數據完整性 OK（{now:%H:%M}；交易日={trading}）")
        return 0

    wrote = write_alert(missing, today)
    state = f"🔴 缺 {len(missing)} 項：{'、'.join(missing)}" if missing else "🟢 無缺口"
    print(f"盤後完整性 {state}（{'已更新' if wrote else '未動'} {ALERT_FP.name}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
