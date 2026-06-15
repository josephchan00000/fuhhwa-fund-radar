"""數字不得杜撰（M6 設計決策 ②）。

文案層的數字**只能來自證據**（報告的想法 / 佐證 / 表頭脈絡）。本模組：
  1. `extract(text)`  → 文本中所有數值 token（標準化：去千分位逗號、保留小數）。
  2. `allowed_set(...)` → 一則想法允許出現的數字集合（headline + evidence + header）。
  3. `check(copy, allowed)` → 文案中**不在允許集**的數字（→ 疑似杜撰，標 🔴）。

baseline 文案逐字沿用證據、不自創數字，故恆 0 違規；本檢查主要用來把關 LLM 覆寫層。
"""
from __future__ import annotations

import re

# 最大連續數值 token：整數可帶千分位逗號，後可接小數（19.05 / 2,000 / 97 / 29.1 / 0.21）
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract(text: str) -> set[str]:
    """回傳文本中所有標準化數值字串（去逗號）。"""
    out: set[str] = set()
    for m in _NUM.finditer(text or ""):
        tok = m.group(0).replace(",", "").rstrip(".")
        if tok:
            out.add(_norm(tok))
    return out


def _norm(tok: str) -> str:
    """標準化：'97.0'→'97'、'29.10'→'29.1'，整數去尾零小數，以利比對。"""
    if "." in tok:
        tok = tok.rstrip("0").rstrip(".")
    return tok or "0"


def allowed_set(*texts: str) -> set[str]:
    """聚合多段證據文本的允許數字集。"""
    out: set[str] = set()
    for t in texts:
        out |= extract(t)
    return out


def check(copy_text: str, allowed: set[str]) -> list[str]:
    """回傳文案中出現、但不在允許集內的數字（疑似杜撰）。順序保留、去重。"""
    bad: list[str] = []
    seen: set[str] = set()
    for m in _NUM.finditer(copy_text or ""):
        tok = _norm(m.group(0).replace(",", "").rstrip("."))
        if tok not in allowed and tok not in seen:
            bad.append(tok)
            seen.add(tok)
    return bad
