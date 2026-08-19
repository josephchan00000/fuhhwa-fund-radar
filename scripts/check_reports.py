#!/usr/bin/env python3
"""當日新聞報告「內容 QA 閘門」——結構性把關（合規掃描之外的即時正確性檢查）。

檢查（任一不過 exit 1，供每日自動更新流程擋下不完整的產出）：
  · 檔案齊全：usnews v1/v2、twnews、macronews、macrocal 皆有「今日」檔
  · 卡數下限：每報新聞卡 ≥4（macrocal 改查表格資料列 ≥10）
  · 連結：每張卡至少 1 條 markdown 可點連結 [標題](http…)
  · 詳細分析：每張卡摘要／影響分析欄位須至少一項非空（2026-07-31 踩坑：twnews 子代理
    漏加 **粗體** 標籤，extract_cards() 解析不到摘要/影響，儀表板只剩連結、詳細分析消失）
  · 漲跌分析＋深度下限（2026-08-20 起、【深度】卡豁免；2026-08-19 使用者需求）：
    每卡須有「N. **漲跌分析**：」欄（實際漲跌幅＋大漲大跌歸因）、影響分析 ≥2 條、
    摘要＋漲跌分析＋影響分析合計 ≥120 字（擋「卡多而淺」的過薄產出）
  · 徽章：每張卡標題括注可解析出重要度（≥6）與屬性（新事件/延伸/深度）
  · 正文禁流程性字句：檔名/欄位名/落檔字樣（「取自官方落檔」「series.sox」「macro_chips.json」）
    只能出現在「資料侷限說明」「合規揭露」段（2026-08-17 踩坑：總覽正文出現
    「數字取自本機官方落檔 `series.sox`」，讀者不需要知道數字從哪支檔讀）
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
# 「漲跌分析」欄＋深度下限自此日起強制（此前的舊報告不回溯——新提示包自 08-20 首輪起才會產此欄）
MOVE_SINCE = "2026-08-20"
MIN_ANALYSIS = 120        # 每卡摘要＋漲跌分析＋影響分析合計字數下限（提示包要求 150–200，此為寬鬆底線）


def _check_cards(path: Path, date: str) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return [f"缺檔：{path.relative_to(ROOT)}"]
    md = path.read_text(encoding="utf-8")
    cards = usnews.extract_cards(md)
    rel = str(path.relative_to(ROOT))
    if len(cards) < MIN_CARDS:
        errs.append(f"{rel}：卡數 {len(cards)} < {MIN_CARDS}")
    errs += _check_process_language(md, rel)
    for i, c in enumerate(cards, 1):
        if not c.get("links"):
            errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」無可點連結")
        if not c.get("summary") and not c.get("points"):
            errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」摘要／影響分析皆空"
                        "（標籤未加 **粗體**，儀表板只會顯示連結、看不到詳細分析）")
        imp, et = c.get("importance"), c.get("etype")
        if not isinstance(imp, int) or imp < 6:
            errs.append(f"{rel}：卡{i} 重要度標注缺失或 <6（{imp}）")
        if et not in ("new", "ext", "deep"):
            errs.append(f"{rel}：卡{i} 屬性標注缺失（新事件/延伸/深度）")
        # 漲跌分析＋深度下限（2026-08-20 起；【深度】精選卡豁免——它有「為什麼值得讀」自成一格）
        if date >= MOVE_SINCE and et != "deep":
            pts = c.get("points") or []
            if not c.get("move"):
                errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」缺「漲跌分析」欄"
                            "（需『N. **漲跌分析**：』標籤加粗體；寫實際漲跌幅＋大漲大跌歸因，"
                            "無明顯反應也要一句交代原因）")
            if len(pts) < 2:
                errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」影響分析僅 {len(pts)} 條（<2）"
                            "——需多視角影響欄（『N. **對…影響**：』標籤加粗體）")
            depth = (len(c.get("summary") or "") + len(c.get("move") or "")
                     + sum(len(t) for _, t in pts))
            if depth < MIN_ANALYSIS:
                errs.append(f"{rel}：卡{i}「{c['title'][:18]}…」分析內容過薄"
                            f"（{depth} 字 < {MIN_ANALYSIS}）——影響分析須寫滿"
                            "「事件→傳導機制→具體標的」因果鏈並含量化數字（深度要求見提示包）")
    return errs


# 流程性字句（正文不得出現；「資料侷限」「合規」段豁免）——檔名/欄位名/落檔字樣＋
# 08-04 那批查證過程句式。加項時保持「決定性字樣」原則，勿加會誤傷一般新聞用語的詞。
_PROCESS_RE = re.compile(
    r"官方落檔|本機落檔|series\.[a-z_]+|macro_chips|[a-z_]+\.json|"
    r"未取得兩[個項]?獨立來源|一律不列數字|依內規|見資料侷限")


def _check_process_language(md: str, rel: str) -> list[str]:
    errs, sec = [], ""
    for n, line in enumerate(md.splitlines(), 1):
        s = line.strip()
        if re.match(r"^#{1,3}\s", s):
            sec = s
        if "資料侷限" in sec or "合規" in sec:
            continue
        m = _PROCESS_RE.search(line)
        if m:
            errs.append(f"{rel}：第{n}行正文出現流程性字句「{m.group(0)}」"
                        "——檔名/欄位名/查證過程只能寫在「資料侷限說明」段")
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
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v1.md", date)
    errs += _check_cards(ROOT / f"reports/usnews/{date}_v2.md", date)
    errs += _check_cards(ROOT / f"reports/twnews/{date}.md", date)
    errs += _check_cards(ROOT / f"reports/macronews/{date}.md", date)
    errs += _check_calendar(ROOT / f"reports/macrocal/{date}.md", date)
    if errs:
        print(f"[內容 QA] 🔴 {date} 未通過（{len(errs)} 項）：")
        for e in errs:
            print(f"  ✗ {e}")
        return 1
    print(f"[內容 QA] 🟢 {date} 通過：五檔齊全、卡數/連結/重要度/行事曆結構皆合格")
    return 0


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else today_tw().strftime("%Y-%m-%d")
    sys.exit(run(d))
