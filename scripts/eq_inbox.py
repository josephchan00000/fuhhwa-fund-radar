"""個股報告申請的收件匣（.github/workflows/eq_inbox.yml 跑；docs/lab_eq_request_plan.md 第 3.2 節）。

    python3 scripts/eq_inbox.py            # 讀開著的申請單 → 回覆、關單、寫 data/eq_requests.json（要 GH_TOKEN、REPO）
    python3 scripts/eq_inbox.py --dry      # 只印要做的事，不回覆、不寫檔

只用 workflow 自帶的 GITHUB_TOKEN；單上的文字只交給 arm/lab/eqinbox.parse 取代號。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm.lab import eqinbox as I  # noqa: E402

API = "https://api.github.com"
MAX_PAGES = 5                                   # 一次最多看 500 張開著的單


def _call(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "fuhhwa-eq-inbox"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def open_issues(repo: str, token: str) -> list[dict]:
    out = []
    for page in range(1, MAX_PAGES + 1):
        got = _call("GET", f"/repos/{repo}/issues?state=open&per_page=100&page={page}", token) or []
        out += got
        if len(got) < 100:
            break
    return out


def ensure_label(repo: str, token: str) -> None:
    try:
        _call("GET", f"/repos/{repo}/labels/{I.LABEL}", token)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        _call("POST", f"/repos/{repo}/labels", token, {"name": I.LABEL, "color": "1f6feb", "description": "個股報告申請"})


def main() -> int:
    dry = "--dry" in sys.argv[1:]
    repo, token = os.environ.get("REPO", ""), os.environ.get("GH_TOKEN", "")
    if not repo or not token:
        print("[eq_inbox] 沒有 REPO／GH_TOKEN，跳過")
        return 0
    if not dry:
        ensure_label(repo, token)
    issues = open_issues(repo, token)
    old = I._read(I.FILE, None)
    new, acts = I.reconcile(issues, old, clock.today_tw().isoformat(), clock.stamp_tw())
    for a in acts:
        print("[eq_inbox]", a[0], f"#{a[1]}", (a[2] if len(a) > 2 else ""))
        if dry:
            continue
        try:
            if a[0] == "comment":
                _call("POST", f"/repos/{repo}/issues/{a[1]}/comments", token, {"body": a[2]})
            elif a[0] == "close":
                _call("PATCH", f"/repos/{repo}/issues/{a[1]}", token, {"state": "closed", "state_reason": a[2]})
            elif a[0] == "label":
                _call("POST", f"/repos/{repo}/issues/{a[1]}/labels", token, {"labels": [I.LABEL]})
        except urllib.error.HTTPError as e:                     # 一張單失敗不擋其他單
            print(f"[eq_inbox] #{a[1]} {a[0]} 失敗：HTTP {e.code}")
    print(f"[eq_inbox] 佇列 {len(new['items'])} 件、最近完成 {len(new['done'])} 件、開著的單 {len(issues)} 張")
    if dry or I.same(old, new):
        return 0
    I.FILE.parent.mkdir(parents=True, exist_ok=True)
    I.FILE.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
