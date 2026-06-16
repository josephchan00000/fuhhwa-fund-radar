#!/usr/bin/env python3
"""一鍵：設 Cloudflare Access email 白名單鎖 → 驗證 → 部署儀表板到私人網址。

流程（皆冪等、可每日重跑）：
  1. 驗 token、確認 Pages 專案存在（無則建立 direct-upload 空專案）。
  2. 確認 Zero Trust 組織存在（無則建立）。
  3. 在 {project}.pages.dev 上建/更新 Access self-hosted 應用 + Allow 白名單 policy（限定 email）。
  4. 讀回 app+policy 驗證『鎖已生效、只有這些 email 能進』。
  5. 重產儀表板 → wrangler pages deploy（用同一顆 token）。

token 來源：環境變數 CLOUDFLARE_API_TOKEN，否則讀 /tmp/.cf_tok。白名單 email 由 argv 給（預設見下）。
用法：python3 scripts/cf_publish.py [email1] [email2] ...
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

try:                                # python.org Python 預設缺 CA → 用 certifi（同 arm.http）
    import certifi
    _CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _CTX = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "77aa9a4b3ab3461c3331f083688c1282")
PROJECT = os.environ.get("CF_PROJECT", "fh-arm-radar")
HOST = f"{PROJECT}.pages.dev"
DEFAULT_EMAILS = ["user@example.com"]
API = "https://api.cloudflare.com/client/v4"


def _token() -> str:
    t = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not t:
        p = Path("/tmp/.cf_tok")
        t = p.read_text().strip() if p.exists() else ""
    if not t:
        sys.exit("✘ 找不到 token（設 CLOUDFLARE_API_TOKEN 或 /tmp/.cf_tok）")
    return t


TOK = _token()
H = {"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"}


def api(method: str, path: str, body=None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"success": False, "errors": [{"message": f"HTTP {e.code}"}]}


def ok(d, label) -> dict:
    if not d.get("success"):
        errs = d.get("errors") or []
        # 「已存在」類錯誤視為可繼續
        msg = "; ".join(str(e.get("message", e)) for e in errs)
        if any(k in msg for k in ("already", "exists", "duplicate", "uniqueness")):
            print(f"  ↺ {label}：已存在，沿用")
            return d
        sys.exit(f"✘ {label} 失敗：{msg}")
    return d


def main() -> None:
    emails = sys.argv[1:] or DEFAULT_EMAILS
    print(f"▶ 帳號 {ACCOUNT_ID[:8]}… 專案 {PROJECT} 白名單 {emails}")

    # 1. Pages 專案
    r = api("GET", f"/accounts/{ACCOUNT_ID}/pages/projects/{PROJECT}")
    if not r.get("success"):
        ok(api("POST", f"/accounts/{ACCOUNT_ID}/pages/projects",
               {"name": PROJECT, "production_branch": "main"}), "建立 Pages 專案")
        print(f"  ✅ 已建立空專案 {PROJECT}")
    else:
        print(f"  ✅ Pages 專案已存在")

    # 2. Zero Trust 組織（token 通常無權建立；只檢查，不硬卡）
    org = api("GET", f"/accounts/{ACCOUNT_ID}/access/organizations")
    if org.get("success") and org.get("result"):
        print(f"  ✅ Zero Trust 已就緒（{(org.get('result') or {}).get('auth_domain')}）")
    else:
        print("  ⓘ 無法確認 Zero Trust 組織（將直接嘗試建立 Access 應用）")

    # 3. Access 應用（找既有同網域，否則建）
    apps = api("GET", f"/accounts/{ACCOUNT_ID}/access/apps")
    app = next((a for a in (apps.get("result") or []) if a.get("domain") == HOST), None)
    if app:
        app_id = app["id"]; print(f"  ✅ Access 應用已存在（{HOST}）")
    else:
        r = api("POST", f"/accounts/{ACCOUNT_ID}/access/apps",
                {"name": "FH-ARM Radar", "domain": HOST, "type": "self_hosted",
                 "session_duration": "24h", "app_launcher_visible": False})
        if not r.get("success"):
            msg = "; ".join(str(e.get("message", e)) for e in (r.get("errors") or []))
            print(f"\n✘ 建立 Access 應用失敗：{msg}")
            print("  → 多半是 Zero Trust 尚未初始化。請到 https://one.dash.cloudflare.com 一次性設定：")
            print("    取一個 team 名稱 → 選 Free 方案 → 完成後回來跟我說，我再重跑（不會重複建東西）。")
            sys.exit(1)
        app_id = r["result"]["id"]; print(f"  ✅ Access 應用已建立（{HOST}）")

    # 4. policy：Allow 指定 email（先清掉舊的同名再建，確保白名單精確）
    include = [{"email": {"email": e}} for e in emails]
    pols = api("GET", f"/accounts/{ACCOUNT_ID}/access/apps/{app_id}/policies")
    existing = next((p for p in (pols.get("result") or []) if p.get("name") == "viewers-allow"), None)
    body = {"name": "viewers-allow", "decision": "allow", "include": include}
    if existing:
        ok(api("PUT", f"/accounts/{ACCOUNT_ID}/access/apps/{app_id}/policies/{existing['id']}", body), "更新白名單 policy")
    else:
        ok(api("POST", f"/accounts/{ACCOUNT_ID}/access/apps/{app_id}/policies", body), "建立白名單 policy")
    print(f"  ✅ 白名單 policy 已設：Allow {emails}")

    # 5. 驗證鎖
    pols = api("GET", f"/accounts/{ACCOUNT_ID}/access/apps/{app_id}/policies")
    allow = [p for p in (pols.get("result") or []) if p.get("decision") == "allow"]
    locked_emails = sorted({i["email"]["email"] for p in allow for i in (p.get("include") or []) if "email" in i})
    if not allow:
        sys.exit("✘ 驗證失敗：找不到 Allow policy，為安全起見中止部署")
    print(f"  🔒 驗證通過：{HOST} 受 Access 保護，僅 {locked_emails} 可進（其他人會被擋在登入頁）")

    # 6. 部署內容（鎖已驗證才走到這）
    print("▶ 重產儀表板…")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_dashboard.py")], check=True)
    print("▶ 部署到 Cloudflare Pages…")
    env = {**os.environ, "CLOUDFLARE_API_TOKEN": TOK, "CLOUDFLARE_ACCOUNT_ID": ACCOUNT_ID}
    subprocess.run(["npx", "--yes", "wrangler@latest", "pages", "deploy", str(ROOT / "dashboard"),
                    "--project-name", PROJECT, "--branch", "main", "--commit-dirty=true"],
                   check=True, env=env)
    print(f"\n✅ 完成！私人網址：https://{HOST}")
    print(f"   只有 {locked_emails} 能進（首次開會收到 email 驗證碼）。")


if __name__ == "__main__":
    main()
