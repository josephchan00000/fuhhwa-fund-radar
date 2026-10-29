#!/usr/bin/env python3
"""知識庫第二段起的事實清單比對（docs/llm_wiki_plan.md 第 4.2、10 節）。

整理過的頁（scripts/wiki_split.py 的 ORGANIZED）不再是 CLAUDE.md 的逐字切片，所以改成比「事實」：
從 CLAUDE.md 對應那幾段抽出事實記號——`程式碼片段`（檔名、路徑、函式、欄位、指令）、日期（2026-10-29、10/29）、
帶單位的數字（50.7%、1,321 萬、30 分…）、「引號裡的字」（使用者原話、頁面上的字）、run 編號、VER 幾——
每一個都要還出現在知識庫裡（比對時忽略空白與 * 號）。
  · 出現在別頁＝搬到別頁了（只列出來看，不算錯）；
  · 哪裡都沒有＝不見了（算錯），除非日誌 wiki/log.md 有一行「- 刪：`記號`——原因」。

  python3 scripts/wiki_facts.py               整理過的頁全部比
  python3 scripts/wiki_facts.py ops/deploy     只比這幾頁（也會列搬到別頁的）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_split as WS  # noqa: E402

UNITS = ("個交易日|交易日|個百分點|百分點|分鐘|小時|個月|萬字|萬|億|元|%|％|分|秒|天|檔|筆|次|口|張|倍|bp|字|行|頁|週|年|月|"
         "KB|MB|GB|px|輪|班|條|組|段|則|支|家|項|格|成")
PATS = [
    re.compile(r"`([^`\n]+)`"),
    re.compile(r"(?<![\d-])(20\d\d-\d\d-\d\d)(?![\d])"),
    re.compile(r"(?<![\d/])(\d{1,2}/\d{1,2})(?![\d/])"),
    re.compile(r"「([^」\n]{2,})」"),
    re.compile(r"(?<![\d.,])(\d[\d,]*(?:\.\d+)?\s?(?:" + UNITS + r"))"),
    re.compile(r"(?<!\d)(\d{8,})(?!\d)"),
    re.compile(r"(VER\s?\d+)"),
]
DROP = re.compile(r"^- 刪：`([^`]+)`")


def norm(s: str) -> str:
    return re.sub(r"[\s*]+", "", s)


def facts(text: str) -> list[str]:
    """一段文字裡的事實記號（去重、照出現順序；去掉空白與 * 之後太短的不算）。"""
    seen, out = set(), []
    for p in PATS:
        for m in p.finditer(text):
            t = norm(m.group(1))
            if len(t) < 2 or t in seen:
                continue
            seen.add(t)
            out.append(t)
    return out


def source(page: str, text: str | None = None) -> str:
    """CLAUDE.md 切到這一頁的那幾段原文。"""
    text = text if text is not None else WS.SRC.read_text("utf-8")
    lines = text.split("\n")
    return "\n".join("\n".join(lines[a - 1:b]) for a, b, p in WS.cut(text) if p == page)


def dropped() -> set[str]:
    log = WS.WIKI / "log.md"
    if not log.exists():
        return set()
    return {norm(m.group(1)) for s in log.read_text("utf-8").split("\n") if (m := DROP.match(s))}


def corpus() -> dict[str, str]:
    """{頁: 去掉空白與 * 的全文}（目錄、日誌不算）。"""
    out = {}
    for f in sorted(WS.WIKI.rglob("*.md")):
        rel = f.relative_to(WS.WIKI).with_suffix("").as_posix()
        if rel in ("index", "log"):
            continue
        out[rel] = norm(f.read_text("utf-8"))
    return out


def compare(pages: list[str] | None = None, text: str | None = None) -> dict[str, dict]:
    """→ {頁: {"n": 記號數, "missing": [哪裡都沒有], "moved": {記號: [在哪幾頁]}}}。"""
    text = text if text is not None else WS.SRC.read_text("utf-8")
    pages = pages or sorted(WS.ORGANIZED)
    C, gone = corpus(), dropped()
    out = {}
    for pg in pages:
        fs = facts(source(pg, text))
        here = C.get(pg, "")
        missing, moved = [], {}
        for t in fs:
            if t in here:
                continue
            where = [k for k, v in C.items() if t in v]
            if where:
                moved[t] = where
            elif t not in gone:
                missing.append(t)
        out[pg] = {"n": len(fs), "missing": missing, "moved": moved}
    return out


def main(argv: list[str]) -> int:
    pages = [a for a in argv if not a.startswith("-")] or None
    R = compare(pages)
    bad = 0
    tot = sum(r["n"] for r in R.values())
    for pg, r in R.items():
        flag = "✗" if r["missing"] else "✓"
        print(f"{flag} {pg}：{r['n']} 個記號，搬到別頁 {len(r['moved'])}、不見 {len(r['missing'])}")
        for t in r["missing"]:
            print(f"    不見：{t}")
        if pages:
            for t, w in r["moved"].items():
                print(f"    搬到 {', '.join(w)}：{t}")
        bad += len(r["missing"])
    print(f"{'✗' if bad else '✓'} 整理過的 {len(R)} 頁、{tot} 個記號，不見 {bad} 個")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
