#!/usr/bin/env python3
"""儀表板煙霧測試：建表後、commit 前擋「結構性壞頁」（多人化 Phase 1，2026-08-14）。

背景：07-31 曾兩類壞版直接上線（新聞卡摘要整片消失連三回合、CSS 隱藏規則漏加導致
按鈕全失效）——pytest 守資料層與字串，但沒有任何一道防線「真的把頁面開起來看」。
100–300 人使用時壞頁直達全員，故加此測：紅 → 該輪不 commit 不部署，線上維持前一版
（靜態頁天然 last-known-good）。

定位（與既有原則的分工，勿混淆）：本測只擋「結構性壞頁」（JS 例外、關鍵區塊消失、
檔案截斷）；數字內容對錯仍走 factcheck「不擋發佈、紅章警示」——「防線不可硬到
什麼都沒更新」原則不變。

兩種模式：
· --lite FILE：零依賴結構檢查（大小／data-gen／關鍵區塊 id／__EH／檔尾完整）。
  秒級、誤報率≈0 → afterhours_refresh／etf_holdings 用，直接攔截。
· FILE（瀏覽器模式）：headless Chromium 真開頁面，驗 console 零錯誤＋關鍵元素＋
  __EH 可解析＋產表時戳新鮮。daily.yml 用。**兩段式上線**：env SMOKE_ENFORCE=0
  （觀察期）斷言失敗只 ::warning:: 不擋；=1 才 exit 1 攔截。
  瀏覽器層 infra 故障（pip/瀏覽器啟動失敗）永遠不擋——只有「確定的斷言失敗」才算紅，
  這是誤報率的第一道設計。瀏覽器來源：runner 內建 Chrome（channel=chrome）→
  env SMOKE_CHROME 指定路徑（本機 /opt/pw-browsers/...）→ playwright 預設 chromium。
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta

REQUIRED_IDS = ["overview", "etf-upcoming", "etfwatch", "etf-detail", "fundnews", "macro-data", "freshness"]
MIN_BYTES = 300_000          # 正常 ~790KB；低於此值＝疑似截斷/半成品
GEN_RE = re.compile(r'data-gen="(\d{4}/\d{2}/\d{2} \d{2}:\d{2})"')
MAX_GEN_AGE_MIN = 120        # 建表後立刻跑煙測，產表時戳理應在數分鐘內（寬限 2 小時）


def _fail(msgs: list[str], enforce: bool) -> int:
    for m in msgs:
        print(f"::{'error' if enforce else 'warning'}::[煙測] {m}")
    if enforce:
        print("[煙測] 🔴 SMOKE_ENFORCE=1：攔截本輪（不 commit 不部署，線上維持前一版）")
        return 1
    print("[煙測] ⚠ 觀察期（SMOKE_ENFORCE!=1）：以上僅告警、不攔截——誤報率歸零後改 1")
    return 0


def lite_check(path: str) -> list[str]:
    """零依賴結構檢查；回傳問題清單（空＝通過）。"""
    probs: list[str] = []
    try:
        raw = open(path, "rb").read()
    except OSError as e:
        return [f"讀不到 {path}：{e}"]
    if len(raw) < MIN_BYTES:
        probs.append(f"檔案僅 {len(raw):,} bytes（< {MIN_BYTES:,}）——疑似截斷或建表半途而廢")
    html = raw.decode("utf-8", "replace")
    if not html.rstrip().endswith("</html>"):
        probs.append("檔尾不是 </html>——檔案被截斷")
    for i in REQUIRED_IDS:
        if f'id="{i}"' not in html:
            probs.append(f'關鍵區塊 id="{i}" 消失')
    if not GEN_RE.search(html):
        probs.append('找不到 data-gen 產表時戳標記（對時哨兵與瀏覽器端逾期偵測都靠它）')
    if "window.__EH" not in html:
        probs.append("內嵌 ETF 詳情資料 window.__EH 消失")
    return probs


def browser_check(path: str) -> tuple[list[str], bool]:
    """回傳（問題清單, infra_ok）。infra_ok=False＝環境問題（不算紅、不攔截）。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[煙測] ⚠ SMOKE-INFRA-SKIP：playwright 未安裝——瀏覽器檢查跳過（lite 檢查仍有效）")
        return [], False

    probs: list[str] = []
    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = None
            for how, kw in (("channel=chrome", {"channel": "chrome"}),
                            ("SMOKE_CHROME", {"executable_path": os.environ.get("SMOKE_CHROME", "")}),
                            ("default-chromium", {})):
                if how == "SMOKE_CHROME" and not kw["executable_path"]:
                    continue
                try:
                    browser = p.chromium.launch(headless=True, **kw)
                    print(f"[煙測] 瀏覽器啟動：{how}")
                    break
                except Exception:
                    continue
            if browser is None:
                print("[煙測] ⚠ SMOKE-INFRA-SKIP：無可用 Chromium——瀏覽器檢查跳過")
                return [], False
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
            page.goto("file://" + os.path.abspath(path), wait_until="load", timeout=60_000)
            page.wait_for_timeout(1_500)  # 給 IIFE／延遲初始化一點時間

            if errors:
                probs.append(f"JS 錯誤 {len(errors)} 則：{'；'.join(errors[:3])}")
            for i in REQUIRED_IDS:
                if not page.evaluate(f"!!document.getElementById('{i}')"):
                    probs.append(f'關鍵區塊 id="{i}" 不存在')
            # 可見性用 offsetParent 判（2026-07-31 教訓：class 加對了不代表看得見）；
            # 只驗預設分頁就看得到的 freshness——其他區塊在未選分頁裡本來就隱藏。
            if not page.evaluate("(function(){var e=document.getElementById('freshness');return !!(e&&e.offsetParent!==null)})()"):
                probs.append('「網頁更新時間」區塊不可見（offsetParent=null）')
            if page.evaluate("document.body.offsetHeight") < 2_000:
                probs.append("頁面渲染高度異常（<2000px）——版面疑似崩壞")
            eh = page.evaluate("(function(){try{return Object.keys((window.__EH||{}).etfs||{}).length}catch(e){return -1}})()")
            if eh < 10:
                probs.append(f"__EH 內嵌資料異常（etfs={eh}，應 ≥10 檔）")
            gen = page.evaluate("(function(){var g=document.querySelector('[data-gen]');return g?g.dataset.gen:''})()")
            m = GEN_RE.search(f'data-gen="{gen}"')
            if not m:
                probs.append(f"data-gen 格式異常：{gen!r}")
            else:
                try:
                    dt = datetime.strptime(gen, "%Y/%m/%d %H:%M")
                    age = datetime.now() - dt  # CI 端 TZ=Asia/Taipei，與產表時戳同時區
                    if age > timedelta(minutes=int(os.environ.get("SMOKE_MAX_AGE_MIN", MAX_GEN_AGE_MIN))):
                        probs.append(f"產表時戳 {gen} 距今 {age}——建表後立跑的煙測不該看到舊時戳")
                except ValueError:
                    probs.append(f"data-gen 無法解析：{gen!r}")
            browser.close()
    except Exception as e:
        print(f"[煙測] ⚠ SMOKE-INFRA-SKIP：瀏覽器層例外 {e!r}——本輪跳過（斷言未失敗，不攔截）")
        return [], False
    return probs, True


def main() -> int:
    args = [a for a in sys.argv[1:]]
    lite = "--lite" in args
    if lite:
        args.remove("--lite")
    path = args[0] if args else "dashboard/index.html"

    lp = lite_check(path)
    if lite:
        if lp:
            for m in lp:
                print(f"::error::[煙測-lite] {m}")
            print("[煙測-lite] 🔴 結構性問題——攔截本輪（不 commit 不部署）")
            return 1
        print(f"[煙測-lite] 🟢 {path} 結構完整")
        return 0

    enforce = os.environ.get("SMOKE_ENFORCE", "0") == "1"
    if lp:  # 瀏覽器模式也先跑 lite——截斷檔連開都不用開
        return _fail([f"(lite) {m}" for m in lp], enforce=True)  # 結構截斷永遠攔截
    bp, infra_ok = browser_check(path)
    if not infra_ok:
        return 0
    if bp:
        return _fail(bp, enforce)
    print(f"[煙測] 🟢 {path} 通過（console 零錯誤、關鍵區塊齊、__EH 正常、時戳新鮮）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
