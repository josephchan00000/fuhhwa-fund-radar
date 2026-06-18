#!/usr/bin/env python3
"""非互動部署儀表板到 Vercel 私人網址（API token、免瀏覽器登入）；部署前驗證『存取保護已開』。

與 cf_publish 同安全精神：先用 Vercel API 確認專案已開 Deployment Protection
（Vercel Authentication 或 Password Protection，需 Pro），驗證通過才推 --prod；
未保護則中止，避免把競品/Tier B 敏感情報推到公開網址。

token 來源（依序）：env VERCEL_TOKEN → data/.vercel_tok（持久、gitignore 內）→ ~/.fh_vercel_token。

一次性設定（人工做一次，之後本腳本即可非互動重跑）：
  1. Vercel 建一顆 API token（Account Settings → Tokens），存進 data/.vercel_tok（不入庫）。
  2. Vercel 後台建專案（名稱預設 fh-arm-radar），到 Settings → Deployment Protection
     開 Vercel Authentication 或 Password Protection（需 Pro 方案）。
  3. 在本專案跑一次 `npx vercel link --yes --project fh-arm-radar`（產 dashboard/.vercel 連結，
     讓之後的 deploy 對到正確專案；此步會問一次登入，之後就免）。
用法：python3 scripts/vercel_publish.py [project-name]
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:                                # python.org Python 預設缺 CA → 用 certifi
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent.parent
PROJECT = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VERCEL_PROJECT", "fh-arm-radar")
API = "https://api.vercel.com"


def _token() -> str:
    t = os.environ.get("VERCEL_TOKEN") or ""
    for p in (ROOT / "data" / ".vercel_tok", Path.home() / ".fh_vercel_token"):
        if not t and p.exists():
            t = p.read_text().strip()
    if not t:
        sys.exit("✘ 找不到 Vercel token（設 VERCEL_TOKEN 或 data/.vercel_tok）")
    return t


def main() -> None:
    tok = _token()
    headers = {"Authorization": f"Bearer {tok}"}

    # 1. 查專案 + 驗證存取保護（沒開就中止，絕不把敏感資料推上公開網址）
    req = urllib.request.Request(f"{API}/v9/projects/{PROJECT}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
            proj = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            sys.exit(f"✘ 專案 {PROJECT} 不存在。請先在 Vercel 後台建專案並開 Deployment Protection。")
        sys.exit(f"✘ 查詢專案失敗：HTTP {e.code}（token 權限或專案名是否正確？）")

    sso = proj.get("ssoProtection")            # Vercel Authentication
    pwd = proj.get("passwordProtection")       # Password Protection
    if not sso and not pwd:
        sys.exit(
            f"✘ 專案 {PROJECT} 未開存取保護（Deployment Protection）。為免競品/Tier B 情報公開，已中止。\n"
            "  → Vercel 後台 → 該專案 → Settings → Deployment Protection，\n"
            "    開 Vercel Authentication 或 Password Protection（需 Pro），再重跑本腳本。")
    kinds = "+".join(k for k, v in (("Authentication", sso), ("Password", pwd)) if v)
    print(f"🔒 驗證通過：{PROJECT} 已開存取保護（{kinds}）→ 非名單內看不到內容。")

    # 2. 重產儀表板（確保上線的是最新版）
    print("▶ 重產儀表板…")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_dashboard.py")], check=True)

    # 3. 非互動 token 部署（需先 vercel link 過；見檔頭一次性設定）
    print(f"▶ 部署 dashboard/ → Vercel（--prod，token）…")
    subprocess.run(["npx", "--yes", "vercel@latest", "deploy", str(ROOT / "dashboard"),
                    "--prod", "--yes", "--token", tok], check=True, cwd=str(ROOT / "dashboard"))
    print("✅ 完成。私人網址見上方 Vercel 輸出；只有 Deployment Protection 名單/密碼可進。")


if __name__ == "__main__":
    main()
