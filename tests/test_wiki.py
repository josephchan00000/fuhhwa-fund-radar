"""知識庫 wiki/（docs/llm_wiki_plan.md）。

2026-10-29 第五段瘦身後：頁面就是正本；CLAUDE.md 只留開頭、知識庫用法、鐵則與五個指令。
指令段落在 wiki/ops/ 的整理版要和 CLAUDE.md 一致：比事實清單（scripts/wiki_facts.py，WS.MIRROR 那幾頁）。
（第一～四段的逐字切片、整理、路徑規則見規劃第 11～14 節。）"""
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
PAGE_MAX = 15_000          # 一頁一次讀得完（規劃第 3.3 節）
CLAUDE_MAX = 45_000        # 瘦身後的上限（規劃第 15 節；scripts/wiki_lint.py 同一個數）
INDEX_MAX = 10_000         # 之後會跟著 CLAUDE.md 一起載入，要短
LOG = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (搬家|收錄|整理|查詢) \| .+")


def test_wiki_matches_claude_md():
    errs = WS.check(TEXT)
    assert not errs, "\n".join(errs) + "\n→ 跑 `python3 scripts/wiki_split.py` 重產目錄"


def test_cuts_cover_every_line_exactly_once():
    ranges = WS.cut(TEXT)
    n = len(TEXT.split("\n"))
    assert ranges[0][0] == 1 and ranges[-1][1] == n
    for (a, b, _), (c, _, _) in zip(ranges, ranges[1:]):
        assert a <= b and c == b + 1
    assert [p for _, _, p in ranges if p is None] == [None]      # 只有開頭（知識庫用法、鐵則）沒有對應頁


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
    """全部的頁（目錄、日誌除外）。"""
    return sorted(set(WS.PAGES) | set(WS.EXTRA))


def test_page_sizes():
    big = {}
    for f in WIKI.rglob("*.md"):
        rel = f.relative_to(WIKI).as_posix()
        if rel != "index.md" and len(f.read_text("utf-8")) > PAGE_MAX:
            big[rel] = len(f.read_text("utf-8"))
    assert not big, f"頁太長（> {PAGE_MAX:,} 字）：{big}"


def test_facts_of_organized_pages_are_all_kept():
    R = WF.compare()
    bad = {pg: r["missing"] for pg, r in R.items() if r["missing"]}
    assert not bad, f"CLAUDE.md 指令段落的事實在對應的頁上不見了：{bad}\n→ 補回去，或在 wiki/log.md 記一行「- 刪：`記號`——原因」"


def test_new_fact_in_organized_section_is_caught():
    lines = TEXT.split("\n")
    pg = sorted(WS.MIRROR)[0]
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
        assert "<!-- CLAUDE.md 第" not in t, f"{pg}：不該留逐字切片的行號標記"
        if pg in WS.MIRROR:
            assert "CLAUDE.md 仍留著對應的指令段落" in top, f"{pg}：CLAUDE.md 有對應段落，開頭要寫兩邊要一致"
        elif pg in WS.PAGES:
            assert "正本就是這一頁" in top, f"{pg}：開頭要寫這一頁就是正本"


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


# 第四段（2026-10-29 起）：路徑規則、體檢、程式註解指向知識庫
_SPEC3 = importlib.util.spec_from_file_location("_wiki_lint", ROOT / "scripts" / "wiki_lint.py")
WL = importlib.util.module_from_spec(_SPEC3)
_SPEC3.loader.exec_module(WL)
RULE_MAX = 1_500           # 規劃第 3.4 節：一份規則 1～1.5 千字
CODE_DIRS = ("arm", "scripts", "tests", ".github", "config")
CLAUDE_REF_OK = {          # 講知識庫本身的程式，本來就要提 CLAUDE.md
    "scripts/wiki_split.py", "scripts/wiki_facts.py", "scripts/wiki_lint.py", "tests/test_wiki.py",
    "config/index_reviews.json",   # note 指到 CLAUDE.md 的「ETF 募集週掃」，那一段還在（改它會觸發 daily.yml 整輪重跑）
}


def test_path_rules_load_and_point_to_pages():
    R = WL.rules()
    assert len(R) >= 15, "規劃第 3.4 節：約 15 份"
    for name, paths, body in R:
        assert paths, f".claude/rules/{name} 開頭要有 paths:"
        for p in paths:
            assert list(ROOT.glob(p)), f".claude/rules/{name}：{p} 一個檔都對不到"
        refs = re.findall(r"wiki/[\w/\-]+\.md", body)
        names = re.findall(r"`([\w\-]+\.md)`", body)          # 同一個資料夾的頁可以只寫檔名
        assert refs or names, f".claude/rules/{name} 要寫先讀哪一頁"
        for ref in refs:
            assert (ROOT / ref).exists(), f".claude/rules/{name} 指到不存在的頁：{ref}"
        for n in names:
            assert list(WIKI.rglob(n)), f".claude/rules/{name} 指到不存在的頁：{n}"
        assert len((ROOT / ".claude" / "rules" / name).read_text("utf-8")) <= RULE_MAX, name


def test_lint_has_no_errors():
    errs, _ = WL.lint()
    assert not errs, "\n".join(errs) + "\n→ 跑 `python3 scripts/wiki_lint.py` 看細節"


def test_lint_catches_broken_rule(tmp_path, monkeypatch):
    d = tmp_path / "rules"
    d.mkdir()
    (d / "x.md").write_text('---\npaths:\n  - "arm/nope_*.py"\n---\n先讀 `wiki/lab/' + 'nope.md`。\n', "utf-8")
    monkeypatch.setattr(WL, "RULES", d)
    errs, _ = WL.lint()
    assert any("一個檔都對不到" in e for e in errs) and any("不存在的頁" in e for e in errs)


def test_code_comments_point_to_wiki_not_claude_md():
    for top in CODE_DIRS:
        for f in (ROOT / top).rglob("*"):
            if not f.is_file() or f.suffix not in (".py", ".yml", ".yaml", ".sh", ".json", ".md"):
                continue
            rel = f.relative_to(ROOT).as_posix()
            t = f.read_text("utf-8", errors="ignore")
            if rel not in CLAUDE_REF_OK:
                assert "CLAUDE.md" not in t, f"{rel} 提到 CLAUDE.md：改成指向 wiki/ 的頁"
            for ref in re.findall(r"wiki/[\w/\-]+\.md", t):
                assert (ROOT / ref).exists(), f"{rel} 指到不存在的頁：{ref}"


# 第五段（2026-10-29 起）：CLAUDE.md 瘦身
def test_claude_md_is_slim_and_imports_index():
    assert len(TEXT) <= CLAUDE_MAX, f"CLAUDE.md {len(TEXT):,} 字，超過 {CLAUDE_MAX:,}：多的內容搬進知識庫的頁"
    assert CLAUDE_MAX == WL.CLAUDE_MAX
    assert "\n@wiki/index.md\n" in TEXT, "CLAUDE.md 要把目錄一起載入"
    assert "## 鐵則" in TEXT


def test_routine_prompts_targets_still_in_claude_md():
    """七個排程 prompt 指名引用的指令與步驟（排程搬家照抄原文，改不了 prompt）。"""
    prompts = [s for s in TEXT.split("\n") if s.startswith("> （排程自動觸發）")]
    assert len(prompts) == 7
    for n in "①②③④⑤⑥⑦":
        assert f"Routine prompt 原文{n}" in TEXT
    for f in (".claude/skills/equity-report/SKILL.md", "scripts/eq_queue.py", "scripts/eq_facts.py", "scripts/check_eq.py"):
        assert f in "\n".join(prompts) and (ROOT / f).exists(), f"⑦ 引用的 {f} 不見了"
    need = {
        "CLAUDE.md「指令：全部更新」": "## 指令：「全部更新」／「資料更新」",
        "CLAUDE.md 步驟 9⑤": "   - **⑤ 前十大簡介缺口",
        "CLAUDE.md「已知環境限制與防呆」-32003 條": "## 已知環境限制與防呆",
        "CLAUDE.md「指令：ETF 募集週掃」": "## 指令：「ETF 募集週掃」",
        "CLAUDE.md 週掃步驟 2.5": "2.5 **指數審核維護",
        "CLAUDE.md「指令：策略探勘週報」": "## 指令：「策略探勘週報」",
    }
    allp = "\n".join(prompts)
    for ref, anchor in need.items():
        assert ref in allp, f"prompt 不再引用 {ref}：更新這支測試"
        assert any(s.startswith(anchor) for s in TEXT.split("\n")), f"prompt 引用的 {ref} 在 CLAUDE.md 找不到"
    assert "MCP error -32003" in TEXT
    assert "   - **⑨ 籌碼雷達推播行" in TEXT          # Routine prompt ① 的推播行
