#!/usr/bin/env python3
"""「整理知識庫」的體檢（docs/llm_wiki_plan.md 第 5 節；指令見 CLAUDE.md「指令：「整理知識庫」」）。

只讀、不改檔。錯（✗，exit 1）＝一定要修：
  · 頁間或目錄的連結斷了、有頁沒列進目錄、頁太長、頁首格式不對；
  · 事實比對有記號不見（scripts/wiki_facts.py）；
  · 路徑規則（.claude/rules/*.md）指到不存在的頁，或某個 paths 一個檔都對不到（規則爛掉了）。
提醒（△，不擋）＝請人看一眼：
  · 「現在怎麼運作」「不能改的規則」裡提到的檔案不存在、`模組.函式` 找不到定義（多半是改名或拿掉了，頁面該更新）；
  · 沒有任何頁連到的頁（只有目錄連到）；
  · CLAUDE.md 太長（超過 4.5 萬字＝又長回去了）。

  python3 scripts/wiki_lint.py
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wiki_facts as WF  # noqa: E402
import wiki_split as WS  # noqa: E402

ROOT = WS.ROOT
WIKI = WS.WIKI
RULES = ROOT / ".claude" / "rules"
PAGE_MAX = 15_000
INDEX_MAX = 10_000
CLAUDE_MAX = 45_000          # 第 5 段瘦身後的上限（2026-10-29 使用者選「指令一字不改」，瘦到 4.2 萬字；規劃第 15 節）
CURRENT = ("## 現在怎麼運作", "## 不能改的規則")
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")
CODE = re.compile(r"`([^`\n]+)`")
PATH = re.compile(r"^(?:arm|scripts|tests|config|data|docs|dashboard|\.github|tw-superstock-lab)/[\w./*{}\-]+$")
FUNC = re.compile(r"^([a-z][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)(?:\(.*\))?$")
EXT = {"py", "yml", "json", "md", "sh", "html", "gz", "js", "css", "txt", "csv", "tw", "com", "io", "app"}
PAST = ("拿掉", "原本", "已刪", "過時", "當時", "舊", "改成", "取代")   # 這幾個字在同一行＝本來就在講舊東西


def pages() -> dict[str, str]:
    return {f.relative_to(WIKI).as_posix(): f.read_text("utf-8") for f in sorted(WIKI.rglob("*.md"))}


def current_part(text: str) -> str:
    """「現在怎麼運作」與「不能改的規則」兩節（歷史、踩過的坑裡提到舊檔名是正常的；同一行在講舊東西的也跳過）。"""
    out, keep = [], False
    for s in text.split("\n"):
        if s.startswith("## "):
            keep = s.startswith(CURRENT)
        if keep and not any(w in s for w in PAST):
            out.append(s)
    return "\n".join(out)


def modules() -> dict[str, list[Path]]:
    m: dict[str, list[Path]] = {}
    for f in list((ROOT / "arm").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        m.setdefault(f.stem, []).append(f)
    return m


def defined(mod_files: list[Path], name: str) -> bool:
    n = re.escape(name)
    pat = re.compile(rf"^\s*(?:def|class)\s+{n}\b|^\s*{n}\s*[:=]|^\s*{n}\s*,|function\s+{n}\b|(?:const|let|var)\s+{n}\b|\b{n}\s*=\s*(?:function|\()", re.M)
    return any(pat.search(f.read_text("utf-8", errors="ignore")) for f in mod_files)


def rules() -> list[tuple[str, list[str], str]]:
    out = []
    for f in sorted(RULES.glob("*.md")) if RULES.exists() else []:
        t = f.read_text("utf-8")
        m = re.match(r"---\npaths:\n((?:  - \"[^\"]+\"\n)+)---\n(.*)", t, re.S)
        paths = re.findall(r'"([^"]+)"', m.group(1)) if m else []
        out.append((f.name, paths, m.group(2) if m else t))
    return out


def lint() -> tuple[list[str], list[str]]:
    errs, warns = [], []
    P = pages()
    idx = P.get("index.md", "")
    linked = set(LINK.findall(idx))
    for name in P:
        if name not in ("index.md", "log.md") and name not in linked:
            errs.append(f"目錄沒列：{name}")
    incoming: dict[str, int] = {}
    for name, t in P.items():
        base = (WIKI / name).parent
        for ln in LINK.findall(t):
            tgt = (base / ln).resolve()
            if not tgt.exists():
                errs.append(f"{name} 連到不存在的頁：{ln}")
            elif name != "index.md":
                rel = tgt.relative_to(WIKI.resolve()).as_posix()
                incoming[rel] = incoming.get(rel, 0) + 1
        lim = INDEX_MAX if name == "index.md" else PAGE_MAX
        if len(t) > lim:
            errs.append(f"{name} 太長：{len(t):,} 字（上限 {lim:,}）")
        if name not in ("index.md", "log.md"):
            head = t.split("\n")
            if not (head[0].startswith("# ") and len(head) > 2 and head[2].startswith("> ")):
                errs.append(f"{name} 開頭要是「# 標題」與「> 一句話摘要」")
            elif "## 現在怎麼運作" not in t:
                errs.append(f"{name} 沒有「## 現在怎麼運作」")
    for name in P:
        if name not in ("index.md", "log.md") and not incoming.get(name):
            warns.append(f"沒有任何頁連到（只有目錄）：{name}")
    # 事實比對
    R = WF.compare(sorted(WS.MIRROR))
    for pg, r in R.items():
        for t in r["missing"]:
            errs.append(f"{pg}：CLAUDE.md 的事實不見了：{t}")
    # 「現在」兩節提到的檔案與函式
    mods = modules()
    for name, t in P.items():
        for tok in CODE.findall(current_part(t)):
            tok = tok.strip()
            if PATH.match(tok) and not any(c in tok for c in "*{}"):
                if tok.startswith("data/"):
                    continue          # 資料檔由 CI 產生，可以本來就不在
                f = ROOT / tok.rstrip("/")
                mod, _, attr = tok.rpartition(".")
                if f.exists() or (ROOT / (tok + ".py")).exists():
                    continue
                if mod and (ROOT / (mod + ".py")).exists():
                    if not defined([ROOT / (mod + ".py")], attr):
                        warns.append(f"{name}：找不到定義：{tok}")
                    continue
                warns.append(f"{name}：提到的檔案不存在：{tok}")
                continue
            m = FUNC.match(tok)
            if m and m.group(2) not in EXT and m.group(1) in mods and not defined(mods[m.group(1)], m.group(2)):
                warns.append(f"{name}：找不到定義：{tok}")
    # 路徑規則
    for fname, paths, body in rules():
        if not paths:
            errs.append(f".claude/rules/{fname} 開頭沒有 paths:")
        for p in paths:
            if not glob.glob(str(ROOT / p), recursive=True):
                errs.append(f".claude/rules/{fname}：{p} 一個檔都對不到")
        for ref in re.findall(r"wiki/[\w/\-]+\.md", body):
            if not (ROOT / ref).exists():
                errs.append(f".claude/rules/{fname} 指到不存在的頁：{ref}")
        for ref in re.findall(r"`([\w\-]+\.md)`", body):
            if not list(WIKI.rglob(ref)):
                errs.append(f".claude/rules/{fname} 指到不存在的頁：{ref}")
    n = len(WS.SRC.read_text("utf-8"))
    if n > CLAUDE_MAX:
        warns.append(f"CLAUDE.md {n:,} 字，超過瘦身後的上限 {CLAUDE_MAX:,}：多的內容搬進知識庫的頁")
    return errs, warns


def main() -> int:
    errs, warns = lint()
    for e in errs:
        print("✗", e)
    for w in warns:
        print("△", w)
    print(f"{'✗' if errs else '✓'} 知識庫體檢：錯 {len(errs)}、提醒 {len(warns)}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
