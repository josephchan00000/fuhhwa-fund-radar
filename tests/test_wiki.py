"""知識庫 wiki/（docs/llm_wiki_plan.md）。

第一段（2026-10-29 起）：各頁由 scripts/wiki_split.py 從 CLAUDE.md 逐字切出來，CLAUDE.md 是正本；
改了 CLAUDE.md 卻沒重產 wiki/，這裡會紅。"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"
_SPEC = importlib.util.spec_from_file_location("_wiki_split", ROOT / "scripts" / "wiki_split.py")
WS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(WS)

TEXT = (ROOT / "CLAUDE.md").read_text("utf-8")
PAGE_MAX = 25_000          # 一頁一次讀得完；第二段整理後會再收緊到 15,000（規劃第 3.3 節）
INDEX_MAX = 10_000         # 之後會跟著 CLAUDE.md 一起載入，要短
LOG = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (搬家|收錄|整理|查詢) \| .+")


def test_wiki_matches_claude_md():
    errs = WS.check(TEXT)
    assert not errs, "\n".join(errs) + "\n→ 改了 CLAUDE.md 就跑 `python3 scripts/wiki_split.py` 重產 wiki/"


def test_cuts_cover_every_line_exactly_once():
    ranges = WS.cut(TEXT)
    n = len(TEXT.split("\n"))
    assert ranges[0][0] == 1 and ranges[-1][1] == n
    for (a, b, _), (c, _, _) in zip(ranges, ranges[1:]):
        assert a <= b and c == b + 1
    assert [p for _, _, p in ranges if p is None] == [None]      # 只有檔案標題留在 CLAUDE.md


def test_any_edit_to_claude_md_is_caught():
    lines = TEXT.split("\n")
    i = next(k for k, s in enumerate(lines) if s.startswith("## 「市場頁」")) + 3
    edited = "\n".join(lines[:i] + ["- 新加的一行"] + lines[i:])
    assert WS.check(edited), "CLAUDE.md 多了一行，wiki/ 沒重產卻沒被抓到"
    assert any("新加的一行" in t for t in WS.build(edited).values())


def test_anchor_must_match_exactly_one_line():
    first = WS.CUTS[5][0]
    with pytest.raises(ValueError):
        WS.cut(TEXT + "\n" + first)
    with pytest.raises(ValueError):
        WS.cut(TEXT.replace(first, "（改名）" + first, 1))


def test_index_lists_every_page_and_links_resolve():
    idx = (WIKI / "index.md").read_text("utf-8")
    links = set(re.findall(r"\]\(([^)#]+\.md)\)", idx))
    for ln in links:
        assert (WIKI / ln).exists(), f"目錄連到不存在的頁：{ln}"
    pages = {f.relative_to(WIKI).as_posix() for f in WIKI.rglob("*.md")} - {"index.md"}
    assert pages <= links, f"目錄沒列：{sorted(pages - links)}"
    assert len(idx) <= INDEX_MAX


def test_page_sizes():
    big = {f.relative_to(WIKI).as_posix(): len(f.read_text("utf-8"))
           for f in WIKI.rglob("*.md") if len(f.read_text("utf-8")) > PAGE_MAX}
    assert not big, f"頁太長（> {PAGE_MAX:,} 字）：{big}"


def test_every_page_starts_with_title_and_summary():
    for f in WIKI.rglob("*.md"):
        head = f.read_text("utf-8").split("\n")
        assert head[0].startswith("# "), f
        if f.name not in ("index.md",):
            assert head[2].startswith("> "), f"{f}：第 3 行要是一句話摘要"


def test_log_format_and_dates_in_order():
    rows = [s for s in (WIKI / "log.md").read_text("utf-8").split("\n") if s.startswith("## ")]
    assert rows
    dates = []
    for s in rows:
        m = LOG.match(s)
        assert m, f"日誌格式不對：{s}"
        dates.append(m.group(1))
    assert dates == sorted(dates), "日誌只往後加，日期要由舊到新"
