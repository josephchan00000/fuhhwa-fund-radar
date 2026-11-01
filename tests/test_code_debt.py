"""債務帳（docs/code_debt.md）和程式裡的 shortcut 註解要對得上（ponytail 第四段）。

每一行 shortcut 註解都要寫「升級：」（什麼時候、怎麼升）；每個檔的註解數要等於債務帳表格裡那個檔的列數。
修好一條就把註解和那一列一起拿掉，新增一條就兩邊一起加。
"""
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "docs" / "code_debt.md"
MARK = re.compile(r"(#|//|/\*) ?shortcut:")
SCAN = ("arm", "scripts", ".github/workflows")


def _marks() -> list[tuple[str, int, str]]:
    out = []
    for top in SCAN:
        for p in sorted((ROOT / top).rglob("*")):
            if p.is_file() and p.suffix in (".py", ".yml", ".yaml"):
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if MARK.search(line):
                        out.append((p.relative_to(ROOT).as_posix(), i, line))
    return out


def _ledger_rows() -> list[str]:
    """表格每一列第一格的檔案路徑（`位置` 欄）。"""
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*`([^`]+)`\s*\|", line)
        if m:
            rows.append(m.group(1))
    return rows


def test_every_shortcut_names_its_upgrade():
    bad = [f"{f}:{i}" for f, i, line in _marks() if "升級：" not in line]
    assert not bad, f"shortcut 註解要在同一行寫「升級：什麼時候、怎麼升」：{bad}"


def test_ledger_matches_shortcut_comments():
    code = Counter(f for f, _, _ in _marks())
    ledger = Counter(_ledger_rows())
    assert code, "程式裡找不到任何 shortcut 註解（掃描範圍或寫法變了？）"
    assert code == ledger, (f"程式裡的 shortcut 註解（每檔幾行）{dict(code)} 和 docs/code_debt.md 表格（每檔幾列）"
                            f"{dict(ledger)} 對不上：新增或修好一條時，註解和債務帳要一起改")


def test_mark_pattern_catches_both_comment_styles():
    assert MARK.search("    # shortcut: 上限。升級：…")
    assert MARK.search("  // shortcut: 上限。升級：…")
    assert not MARK.search("寫成 shortcut 註解的說明文字")
