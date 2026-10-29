"""知識庫 wiki/（docs/llm_wiki_plan.md）。

第一段（2026-10-29 起）：各頁由 scripts/wiki_split.py 從 CLAUDE.md 逐字切出來，CLAUDE.md 是正本；
改了 CLAUDE.md 卻沒重產 wiki/，這裡會紅。
第二段（2026-10-29 起）：整理過的頁（WS.ORGANIZED）不再逐字，改比事實清單（scripts/wiki_facts.py）——
CLAUDE.md 那幾段的每個事實記號都要還在知識庫裡。"""
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "wiki"
_SPEC = importlib.util.spec_from_file_location("_wiki_split", ROOT / "scripts" / "wiki_split.py")
WS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(WS)
_SPEC2 = importlib.util.spec_from_file_location("_wiki_facts", ROOT / "scripts" / "wiki_facts.py")
WF = importlib.util.module_from_spec(_SPEC2)
_SPEC2.loader.exec_module(WF)

TEXT = (ROOT / "CLAUDE.md").read_text("utf-8")
PAGE_MAX = 25_000          # 逐字頁：一頁一次讀得完
ORG_MAX = 15_000           # 整理過的頁（規劃第 3.3 節）
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


def _verbatim_heading():
    """一個還是逐字切片的頁的段標題（改那一段，wiki/ 沒重產要被抓到）。"""
    lines = TEXT.split("\n")
    for a, b, p in WS.cut(TEXT):
        if p and p not in WS.ORGANIZED and lines[a - 1].startswith("## "):
            return a - 1
    raise AssertionError("找不到還是逐字的段")


def test_any_edit_to_claude_md_is_caught():
    lines = TEXT.split("\n")
    i = _verbatim_heading() + 3
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


def _organized():
    """整理過的頁＋新寫的頁（不是 CLAUDE.md 切出來的）。"""
    return sorted(set(WS.ORGANIZED) | set(WS.EXTRA))


def test_page_sizes():
    org = {p + ".md" for p in _organized()}
    big = {}
    for f in WIKI.rglob("*.md"):
        rel = f.relative_to(WIKI).as_posix()
        lim = ORG_MAX if rel in org else PAGE_MAX
        if len(f.read_text("utf-8")) > lim:
            big[rel] = len(f.read_text("utf-8"))
    assert not big, f"頁太長（整理過的 > {ORG_MAX:,}、逐字的 > {PAGE_MAX:,} 字）：{big}"


def test_facts_of_organized_pages_are_all_kept():
    R = WF.compare()
    bad = {pg: r["missing"] for pg, r in R.items() if r["missing"]}
    assert not bad, f"整理過的頁有事實不見了：{bad}\n→ 補回去，或在 wiki/log.md 記一行「- 刪：`記號`——原因」"


def test_new_fact_in_organized_section_is_caught():
    lines = TEXT.split("\n")
    pg = sorted(WS.ORGANIZED)[0]
    a = next(a for a, b, p in WS.cut(TEXT) if p == pg)
    edited = "\n".join(lines[:a] + ["- 新加的規則：`brand_new_fn_20991231()`"] + lines[a:])
    R = WF.compare([pg], edited)
    assert "brand_new_fn_20991231()" in R[pg]["missing"], "整理過的段多了一個事實，比對卻沒抓到"


def test_organized_pages_format():
    for pg in _organized():
        t = (WIKI / (pg + ".md")).read_text("utf-8")
        head = t.split("\n")
        assert head[0].startswith("# "), pg
        assert head[2].startswith("> "), f"{pg}：第 3 行要是一句話摘要"
        top = "\n".join(head[:8])
        assert "> 原始資料：" in top and "> 最後更新：" in top, f"{pg}：開頭要寫原始資料與最後更新"
        h2 = [s for s in head if s.startswith("## ")]
        assert h2 and h2[0] == "## 現在怎麼運作", f"{pg}：第一個 ## 標題要是「現在怎麼運作」"
        assert "<!-- CLAUDE.md 第" not in t, f"{pg}：整理過的頁不該留逐字切片的行號標記"


def test_links_between_pages_resolve():
    bad = []
    for f in WIKI.rglob("*.md"):
        for ln in re.findall(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)", f.read_text("utf-8")):
            if ln.startswith(("http:", "https:")):
                continue
            if not (f.parent / ln).resolve().exists():
                bad.append(f"{f.relative_to(WIKI)} → {ln}")
    assert not bad, f"連到不存在的頁：{bad}"


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
