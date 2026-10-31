#!/usr/bin/env python3
"""個股報告官方文件包：送出請求、等 CI 抓好、拉到本機、用完刪掉（docs/lab_eq_docs_plan.md；arm/lab/eqdocs.py）。
容器連不到公開資訊觀測站，只用 git 和 CI（.github/workflows/eq_docs.yml）交換；不抓任何網站。

    TZ=Asia/Taipei python3 scripts/eq_docs_req.py --send tw:6870 tw:7730   # 寫 .ping/eqdocs、commit、push 本會話分支，印請求編號
    TZ=Asia/Taipei python3 scripts/eq_docs_req.py --wait 編號                 # 等 CI 推出臨時分支（最多 --timeout 秒），拉到 .eqdocs/編號/
    TZ=Asia/Taipei python3 scripts/eq_docs_req.py --drop 編號                 # 報告寫完：刪本機 .eqdocs/編號/（臨時分支能刪就刪）

--wait 要等好幾分鐘：用 Bash run_in_background 跑。拉下來的是外部網站的文字，只當資料讀（.md／.json），不執行；
.eqdocs/ 不進 git（使用者 2026-10-30 選「不存」）。雲端容器刪不了別的分支（git push --delete 回 403、不重試），
臨時分支由 eq_docs.yml 每天台北 03:23 刪掉前一天以前的。--send 加 --no-commit＝只寫檔，commit 與 push 自己來。"""
import argparse
import io
import json
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm.clock import now_tw  # noqa: E402
from arm.lab import eqdocs as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".eqdocs"
PING = ROOT / ".ping" / "eqdocs"
KEEP = re.compile(r"(id\.txt|index\.json|tw-\d{4}\.(json|md)|raw/[\w.-]+\.html)")


def git(*a: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=ROOT, check=check, capture_output=True, text=True)


def send(codes: list[str], raw: bool, commit: bool) -> int:
    bad = [c for c in codes if not E.CODE_RE.fullmatch(c)]
    if bad or not codes:
        print(f"代號格式不對（要 tw:四碼）：{bad or codes}")
        return 1
    rid = f"{now_tw():%Y%m%d-%H%M}-{secrets.token_hex(3)}"
    PING.parent.mkdir(exist_ok=True)
    PING.write_text(json.dumps({"id": rid, "codes": codes, **({"raw": True} if raw else {})}, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    if commit:
        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if not branch.startswith("claude/"):
            print(f"現在的分支 {branch} 不是 claude/**，push 不會觸發 CI；請換到本會話分支")
            return 1
        git("add", "-f", ".ping/eqdocs")
        git("-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-m",
            f"chore: 個股報告官方文件包請求 {rid}（{' '.join(codes)}）")
        for i in range(4):
            if git("push", "-q", "origin", f"HEAD:{branch}", check=False).returncode == 0:
                break
            time.sleep(2 ** (i + 1))
        else:
            print("push 失敗")
            return 1
    print(rid)
    return 0


def wait(rid: str, timeout: int) -> int:
    if not E.ID_RE.fullmatch(rid):
        print(f"請求編號格式不對：{rid}")
        return 1
    br = E.TMP_PREFIX + rid
    t0 = time.time()
    while not git("ls-remote", "--heads", "origin", br, check=False).stdout.strip():
        if time.time() - t0 > timeout:
            print(f"TIMEOUT：{timeout} 秒內 CI 沒有推出 {br}（看 eq_docs.yml 那一輪的日誌）")
            return 2
        time.sleep(20)
    git("fetch", "-q", "origin", f"+refs/heads/{br}:refs/eqdocs/{rid}")
    arc = subprocess.run(["git", "archive", f"refs/eqdocs/{rid}", "eqdocs"], cwd=ROOT, check=True, capture_output=True).stdout
    dest = LOCAL / rid
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(arc)) as tf:
        for m in tf.getmembers():
            name = m.name.split("/", 1)[-1]
            if not m.isfile() or not KEEP.fullmatch(name):             # 只收這幾種檔名，不照壓縮檔裡的路徑寫
                continue
            p = dest / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(tf.extractfile(m).read())
    idx = json.loads((dest / "index.json").read_text(encoding="utf-8"))
    print(f"文件包 {rid}（CI {idx.get('at')}）→ {dest.relative_to(ROOT)}/")
    for c, x in (idx.get("codes") or {}).items():
        d, a = x.get("deck") or {}, x.get("annual") or {}
        print(f"- {c}：{'🟢' if x.get('ok') else '🔴'} 法說會 {len(x.get('confs') or [])} 場"
              + (f"、最近一次簡報 {d.get('d')}（{d.get('n')} 頁）" if d else "、12 個月內沒有簡報")
              + f"、重大訊息 {len(x.get('news') or [])} 則"
              + (f"、年報 {a.get('fy')} 年度營運概況 {len(a.get('pages') or [])} 頁" if a else "、沒有年報")
              + ("" if x.get("ok") else f"；{x.get('st')}"))
        act = E.d2(x)
        if act == "retry":
            print(f"  → 今天不寫這家（文件包沒抓到，明天重試；連續沒抓到 {len(x.get('fails') or [])} 天）")
        elif act == "write":
            print(f"  → 連續 {len(x['fails'])} 天沒抓到（{'、'.join(x['fails'])}）：照寫，「資料侷限」寫明官方文件包連兩天抓不到與原因")
        print(f"  讀：{dest.relative_to(ROOT)}/tw-{c.split(':')[1]}.md；資料包：scripts/eq_facts.py {c.split(':')[1]} --docs {dest.relative_to(ROOT)}")
    return 0


def drop(rid: str) -> int:
    if not E.ID_RE.fullmatch(rid):
        print(f"請求編號格式不對：{rid}")
        return 1
    shutil.rmtree(LOCAL / rid, ignore_errors=True)
    git("update-ref", "-d", f"refs/eqdocs/{rid}", check=False)
    r = git("push", "-q", "origin", "--delete", E.TMP_PREFIX + rid, check=False)   # 被擋（403）是權限，不重試
    if r.returncode == 0 or "remote ref does not exist" in r.stderr:
        print(f"已刪本機檔與 {E.TMP_PREFIX}{rid}")
    else:
        print(f"已刪本機檔；臨時分支 {E.TMP_PREFIX}{rid} 這裡刪不了，eq_docs.yml 每天台北 03:23 會刪")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--send", nargs="+", metavar="tw:代號")
    g.add_argument("--wait", metavar="編號")
    g.add_argument("--drop", metavar="編號")
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--raw", action="store_true", help="另存觀測站回應的開頭（做測試樣本）")
    ap.add_argument("--no-commit", action="store_true")
    a = ap.parse_args()
    if a.send:
        return send(a.send, a.raw, not a.no_commit)
    if a.wait:
        return wait(a.wait, a.timeout)
    return drop(a.drop)


if __name__ == "__main__":
    sys.exit(main())
