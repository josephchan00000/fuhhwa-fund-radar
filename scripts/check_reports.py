#!/usr/bin/env python3
"""當日新聞報告「內容 QA 閘門」——結構性把關（合規掃描之外的即時正確性檢查）。

檢查（任一不過 exit 1，供每日自動更新流程擋下不完整的產出）：
  · 檔案齊全：usnews v1/v2、twnews、macronews、macrocal 皆有「今日」檔
  · 卡數下限：每報新聞卡 ≥4（macrocal 改查表格資料列 ≥10）
  · 連結：每張卡至少 1 條 markdown 可點連結 [標題](http…)
  · 詳細分析：每張卡摘要／影響分析欄位須至少一項非空（2026-07-31 踩坑：twnews 子代理
    漏加 **粗體** 標籤，extract_cards() 解析不到摘要/影響，儀表板只剩連結、詳細分析消失）
  · 徽章：每張卡標題括注可解析出重要度（≥6）與屬性（新事件/延伸/深度）
  · 行事曆：表頭「更新：」需為今日

用法：TZ=Asia/Taipei python3 scripts/check_reports.py [YYYY-MM-DD]（預設今日台北）
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import usnews  # noqa: E402
from arm.clock import today_tw  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIN_CARDS = 4


def _check_cards(path: Path, date: str, brief_re: str | None = None) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return [f"缺檔：{path.relative_to(ROOT)}"]
    md = path.read_text(encoding="utf-8")
    cards = usnews.extract_cards(md)
    rel = str(path.relative_to(ROOT))
    if len(cards) < MIN_CARDS:
        errs.append(f"{rel}：卡數 {len(cards)} < {MIN_CARDS}")
    # 保底要點卡（2026-08-17 使用者需求）：台股報須有「盤前/盤後要點」卡、美股報須有
    # 「盤後要點」卡——這張是每天的下限保證，缺了就是版型沒照 BRIEF_RULE 走
    if brief_re and not any(re.search(brief_re, c["title"]) and c.get("etype") == "brief"
                            for c in cards):
        errs.append(f"{rel}：缺保底要點卡（標題含「{brief_re}」且屬性標【要點】，"
                    "見 usnews.BRIEF_RULE）")
    for i, c in enumerate(cards, 1):
        if not c.get("links"):
            errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」無可點連結")
        if not c.get("summary") and not c.get("points"):
            errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」摘要／影響分析皆空"
                        "（標籤未加 **粗體**，儀表板只會顯示連結、看不到詳細分析）")
        imp, et = c.get("importance"), c.get("etype")
        if not isinstance(imp, int) or imp < 6:
            errs.append(f"{rel}：卡{i} 重要度標注缺失或 <6（{imp}）")
        if et not in ("brief", "new", "ext", "deep"):
            errs.append(f"{rel}：卡{i} 屬性標注缺失（要點/新事件/延伸/深度）")
    return errs


def _check_calendar(path: Path, date: str) -> list[str]:
    if not path.exists():
        return [f"缺檔：{path.relative_to(ROOT)}"]
    md = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(ROOT))
    errs: list[str] = []
    rows = [l for l in md.splitlines()
            if l.strip().startswith("|") and not re.match(r"^\|\s*[-:]+", l.strip())
            and "日期" not in l]
    if len(rows) < 10:
        errs.append(f"{rel}：行事曆資料列 {len(rows)} < 10")
    d_slash = date.replace("-", "/")
    if f"更新：{d_slash}" not in md and f"更新：{date}" not in md:
        errs.append(f"{rel}：表頭「更新：」非今日（{d_slash}）")
    return errs


def run(date: str) -> int:
    errs: list[str] = []
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v1.md", date, brief_re=r"盤後要點")
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v2.md", date, brief_re=r"盤後要點")
    errs += _check_cards(ROOT / f"reports/twnews/{date}.md", date, brief_re=r"盤[前後]要點")
    errs += _check_cards(ROOT / f"reports/macronews/{date}.md", date)
    errs += _check_calendar(ROOT / f"reports/macrocal/{date}.md", date)
    if errs:
        print(f"[內容 QA] 🔴 {date} 未通過（{len(errs)} 項）：")
        for e in errs:
            print(f"  ✗ {e}")
        return 1
    print(f"[內容 QA] 🟢 {date} 通過：五檔齊全、卡數/保底要點卡/連結/重要度/行事曆結構皆合格")
    return 0


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else today_tw().strftime("%Y-%m-%d")
    sys.exit(run(d))
