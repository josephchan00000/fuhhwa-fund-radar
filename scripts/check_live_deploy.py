#!/usr/bin/env python3
"""對時哨兵：部署後驗證「線上頁 = main 最新建表」（多人化 Phase 1，2026-08-14）。

背景：2026-08-13 型事故——資料準時進 main、CI 全綠，線上卻停舊版（deploy hook
secret 失效／Vercel 自動偵測漏接），要等使用者隔天回報才發現。100–300 人使用時
這類「靜默失敗」的代價放大百倍，因此在三支 workflow 的部署步驟之後加這一步：
GitHub Actions 的網路可達 vercel.app（與被 proxy 擋的 Claude 容器不同），
直接輪詢線上頁，比對 data-gen 產表時戳是否已追上 main。

判準：線上 data-gen >= 期望 data-gen（格式 YYYY/MM/DD HH:MM 台北時間，字典序即時序；
取 >= 是因為並行 workflow 可能又推了更新的版本——更新不算失敗）。
輪詢至多 --timeout-min 分鐘（Vercel 靜態建置通常 <60 秒；含 CDN 傳播餘裕），
逾時＝部署未生效 → exit 1（run ❌ → GitHub 寄 failure 信）。

順帶（僅記錄、不影響結果）：印出回應的 Cache-Control / ETag，並在成功時帶
If-None-Match 重打一次驗證 304 是否生效——no-cache 快取改版的線上驗證就看這裡。

用法：
  check_live_deploy.py --expected-file /tmp/main_dashboard.html [--url URL] [--timeout-min 4]
  check_live_deploy.py --parse-only dashboard/index.html   # 只印該檔的 data-gen（本機/測試用）
"""
from __future__ import annotations

import argparse
import re
import ssl
import sys
import time
import urllib.request

DEFAULT_URL = "https://fuhhwa-fund-radar.vercel.app/"
_GEN_RE = re.compile(r'data-gen="(\d{4}/\d{2}/\d{2} \d{2}:\d{2})"')
UA = "fuhhwa-fund-radar deploy-sentinel (github-actions)"


def extract_gen(html: str) -> str | None:
    """抽 data-gen 產表時戳；同頁多處標記時取字典序最大（＝最新）。"""
    hits = _GEN_RE.findall(html or "")
    return max(hits) if hits else None


def _ctx() -> ssl.SSLContext:
    try:
        import certifi  # CI 慣例：pip install certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch(url: str, etag: str | None = None) -> tuple[int, dict, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ctx()) as resp:
            return resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # 304 走 HTTPError 路徑
        return e.code, dict(e.headers or {}), ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--expected-file", help="權威版 dashboard/index.html（main 最新）")
    ap.add_argument("--timeout-min", type=float, default=4.0)
    ap.add_argument("--interval-sec", type=float, default=20.0)
    ap.add_argument("--parse-only", metavar="FILE", help="只印該檔 data-gen 後結束")
    a = ap.parse_args()

    if a.parse_only:
        gen = extract_gen(open(a.parse_only, encoding="utf-8").read())
        print(gen or "（找不到 data-gen 標記）")
        return 0 if gen else 1

    if not a.expected_file:
        print("::error::--expected-file 必填（或用 --parse-only）")
        return 2
    expected = extract_gen(open(a.expected_file, encoding="utf-8").read())
    if not expected:
        print("::error::[對時哨兵] main 版 dashboard 找不到 data-gen 標記——建表產物異常，請先查渲染端")
        return 1
    print(f"[對時哨兵] 期望線上 data-gen >= {expected}（來源：main 最新建表）")

    deadline = time.time() + a.timeout_min * 60
    last_seen, last_err, attempt = None, None, 0
    while True:
        attempt += 1
        try:
            status, headers, body = fetch(a.url)
            if status == 200:
                live = extract_gen(body)
                last_seen = live
                if live and live >= expected:
                    print(f"[對時哨兵] ✅ 第 {attempt} 次檢查：線上 {live} >= 期望 {expected}——部署已生效")
                    cc = headers.get("Cache-Control", "?")
                    etag = headers.get("ETag")
                    print(f"[對時哨兵] （記錄）Cache-Control: {cc}｜ETag: {etag or '（無）'}")
                    if etag:  # 順帶驗 304（no-cache 快取的線上驗證；僅記錄）
                        st2, _h2, _b2 = fetch(a.url, etag=etag)
                        print(f"[對時哨兵] （記錄）帶 If-None-Match 重打 → HTTP {st2}"
                              f"{'＝304 條件式快取生效' if st2 == 304 else '（非 304——瀏覽器端將每次全量下載）'}")
                    return 0
                print(f"[對時哨兵] 第 {attempt} 次：線上 {live or '無標記'} < 期望 {expected}，等部署傳播…")
            else:
                last_err = f"HTTP {status}"
                print(f"[對時哨兵] 第 {attempt} 次：{last_err}")
        except Exception as e:  # 網路抖動→當一次失敗繼續輪詢
            last_err = repr(e)
            print(f"[對時哨兵] 第 {attempt} 次：連線失敗 {last_err}")
        if time.time() >= deadline:
            break
        time.sleep(a.interval_sec)

    if last_seen is None:
        print(f"::error::[對時哨兵] 線上頁 {a.url} 於 {a.timeout_min} 分鐘內完全不可達（{last_err}）——"
              "可能 Vercel 平台異常；資料已在 main、不受影響")
    else:
        print(f"::error::[對時哨兵] 線上頁停在 {last_seen}、未追上 main 的 {expected}（等了 {a.timeout_min} 分鐘）——"
              "疑似部署漏接：依 CLAUDE.md 步驟 9 診斷順序，先讀本 run『觸發 Vercel 部署』步驟日誌"
              "（印『未設…跳過』＝secret 失效；HTTP 2xx 仍舊版＝查 Vercel Deployments）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
