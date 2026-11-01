"""落檔的讀寫小工具（docs/code_ponytail_audit.md 第 3 條）。

write_text／write_bytes：先寫到同一個資料夾的暫存檔（.{檔名}.{行程編號}.tmp），寫完再換名（os.replace 一次換掉）。
  CI 的 timeout 剛好在寫檔時砍掉程式，原本的檔還是完整的，不會留下寫到一半的檔被 commit 進 main。
  被砍時可能留下暫存檔：.gitignore 擋 *.tmp；workflow 用 `git add -f data/lab` 整個資料夾加時仍會被加進去（沒有人讀、看到可以刪）。
read_json：沒有檔＝default。檔案在但讀不起來：一般讀（頁面顯示）回 default；strict（要寫回的前瞻紀錄）停下報錯，
  不當成空的從頭記——壞掉的檔留著，從 git 歷史還原。
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _tmp(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    return p.with_name(f".{p.name}.{os.getpid()}.tmp")


def write_text(path, txt: str) -> None:
    p = Path(path)
    t = _tmp(p)
    t.write_text(txt, encoding="utf-8")
    os.replace(t, p)


def write_bytes(path, data: bytes) -> None:
    p = Path(path)
    t = _tmp(p)
    t.write_bytes(data)
    os.replace(t, p)


def read_json(path, default=None, strict: bool = False):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        if not strict:
            return default
        msg = f"{p} 讀不起來（{type(e).__name__}: {e}）：不寫回，以免紀錄從頭記；請從 git 歷史還原這個檔"
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::{msg}")
        raise RuntimeError(msg) from e
