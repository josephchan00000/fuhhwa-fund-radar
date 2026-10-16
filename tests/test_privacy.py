"""公開 repo 前的個資防呆（2026-10-16 使用者：「把我的名字跟email拿掉」）。

當天改寫了整段 git 歷史：早期 commit 作者欄的姓名、Gmail 換成 GitHub 的 noreply 地址，
檔案裡的本機使用者路徑與兩個 email 也一併換掉。這裡守住程式、設定、文件不再出現個人 email
或本機使用者路徑（data／reports／dashboard 是抓取與產出的內容，不在範圍內）。"""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = ("data/", "reports/", "dashboard/")
SKIP_EXT = (".gz", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".xlsx", ".xls", ".zip", ".parquet", ".ico")
OK_DOMAINS = ("users.noreply.github.com", "example.com", "anthropic.com")
EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@([A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,4}\.[A-Za-z]{2,12})\b")
HOME = re.compile(r"/Users/[A-Za-z0-9._-]+|/home/(?!user\b|runner\b)[A-Za-z0-9._-]+")


def _tracked() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("沒有 git")
    return [p for p in out.decode("utf-8").split("\0")
            if p and not p.startswith(SKIP_DIRS) and not p.lower().endswith(SKIP_EXT)]


def test_no_personal_email_or_home_path_in_tracked_files():
    bad = []
    for p in _tracked():
        try:
            txt = (ROOT / p).read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        bad += [f"{p}: {m.group(0)}" for m in EMAIL.finditer(txt) if not m.group(1).lower().endswith(OK_DOMAINS)]
        bad += [f"{p}: {m.group(0)}" for m in HOME.finditer(txt)]
    assert not bad, bad
