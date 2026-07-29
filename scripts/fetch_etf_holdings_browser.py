#!/usr/bin/env python3
"""ETF 每日持股 —— 無頭瀏覽器抓取（Playwright）。

**為什麼要用瀏覽器**（2026-07-29，逐家逆向 6 輪後的結論）：
主動式 ETF 依法每日揭露完整持股，資料一定在投信官網頁面上，但各家幾乎都是 SPA
（Angular／React），持股由 XHR 動態載入 —— 靜態 HTTP 抓到的只有文案與公告內文
（元大 1MB 頁面的「成分股」是費率表說明、群益的「證券代號」是基金公告）。
逐家逆向 API 是長尾：10 家投信各自是獨立的謎題，且改版就會再壞一次。
渲染一次就全部解決，且不怕改版。

**兩路取數，取先通過驗證者**：
  ① **攔截 XHR 回應**：SPA 載入持股時打的 API，回應直接餵 pcf.parse_json。
     這一路順便**把真正的 API URL 記進日誌**——日後若要退回純 HTTP（更省資源），
     直接照著補進 pcf._cands() 即可。
  ② **解析渲染後的 DOM**：page.content() 餵 pcf.parse_html。

解析、假陽性驗證（is_plausible）、合併鐵則、貢獻歸因全部重用既有模組，不另立一套。

**為什麼獨立成一支腳本／workflow**：瀏覽器安裝與渲染要 1–3 分鐘，放進 daily.yml 會
壓縮「早上 07:03 前線上可看」的目標。本腳本由 .github/workflows/etf_holdings.yml
自行排程、只更新 data/etf_holdings.json 並 commit；儀表板下一次建表自然吃到最新持股
（資料層本就是「抓取在 CI、建表只讀落檔」）。此 job 失敗不影響任何現有功能——
該 ETF 就是沒有展開明細而已。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import etfholdings, etfwatch                    # noqa: E402
from arm.connectors.issuers import pcf                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_ISSUER_FP = ROOT / "config" / "peer_groups.json"

_KINDS = ("active", "other", "passive")     # 主動式優先（使用者需求的重點）
_NAV_TIMEOUT = 45_000                       # ms：SPA 首次載入偏慢
_SETTLE_MS = 3_500                          # 渲染後再等一下，讓 XHR 回來


def _issuer_map() -> dict[str, str]:
    try:
        return json.loads(_ISSUER_FP.read_text(encoding="utf-8")).get("issuer") or {}
    except Exception:
        return {}


def _capture(page, bag: list[tuple[str, bytes]]):
    """把每個 JSON/文字回應收進 bag（含 URL）——持股 API 就藏在其中一筆。"""
    def on_response(resp):
        try:
            ct = (resp.headers or {}).get("content-type", "")
            if "json" not in ct and "text" not in ct:
                return
            if resp.request.resource_type in ("image", "font", "stylesheet", "media"):
                return
            bag.append((resp.url, resp.body()))
        except Exception:                                 # noqa: BLE001 —— 攔截失敗不影響主流程
            pass

    page.on("response", on_response)


def _from_page(page, url: str) -> tuple[list[dict], str, list[str]]:
    """開一個頁面 → (持股列, 來源標記, 日誌)。抓不到回 ([], "", 日誌)。"""
    log: list[str] = []
    bag: list[tuple[str, bytes]] = []
    _capture(page, bag)
    try:
        page.goto(url, timeout=_NAV_TIMEOUT, wait_until="domcontentloaded")
        page.wait_for_timeout(_SETTLE_MS)
    except Exception as e:                                # noqa: BLE001
        log.append(f"導頁失敗 {type(e).__name__}: {str(e)[:90]}")
        return [], "", log

    # ① 攔截到的 XHR 回應（順便記下真正的 API URL 供日後退回純 HTTP）
    best, best_url = [], ""
    for u, body in bag:
        rows = pcf._normalize(pcf.parse_json(body))
        if len(rows) > len(best):
            best, best_url = rows, u
    if pcf.is_plausible(best):
        log.append(f"✓ XHR 命中：{best_url[:150]}（{len(best)} 檔）"
                   f" ← 可補進 pcf._cands() 改用純 HTTP")
        return best, f"xhr:{best_url[:120]}", log

    # ② 渲染後的 DOM
    try:
        rows = pcf._normalize(pcf.parse_html(page.content().encode("utf-8")))
    except Exception as e:                                # noqa: BLE001
        log.append(f"取 DOM 失敗 {type(e).__name__}: {str(e)[:90]}")
        rows = []
    if pcf.is_plausible(rows):
        return rows, "dom", log

    log.append(f"XHR {len(bag)} 筆回應（最佳 {len(best)} 檔）、DOM {len(rows)} 檔，"
               f"皆未通過持股驗證")
    return [], "", log


def main() -> int:
    probe_only = "--probe" in sys.argv
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠ 未安裝 playwright（pip install playwright && playwright install chromium）"
              "——跳過，既有落檔原封保留")
        return 0

    issuers = _issuer_map()
    targets = [(c, k) for c, _n, k, _cat, _i in etfwatch.WATCHLIST if k in _KINDS]
    targets.sort(key=lambda t: _KINDS.index(t[1]))
    print(f"[ETF 每日持股・瀏覽器] 渲染 {len(targets)} 檔"
          f"{'（--probe 不落檔）' if probe_only else ''}…")

    fresh: dict[str, dict] = {}
    diag: dict[str, str] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--disable-dev-shm-usage"])
        for code, _kind in targets:
            issuer = issuers.get(code, "")
            logs: list[str] = []
            got: list[dict] = []
            src = ""
            for name, url in pcf._cands(code, issuer):
                ctx = browser.new_context(user_agent=pcf._UA["User-Agent"],
                                          viewport={"width": 1280, "height": 900})
                page = ctx.new_page()
                rows, how, log = _from_page(page, url)
                ctx.close()
                logs += [f"[{name}] {x}" for x in log]
                if rows:
                    got, src = rows, f"{name}/{how}"
                    break
            if got:
                fresh[code] = {"date": None, "src": src, "holdings": got}
                print(f"  ✓ {code}（{issuer or '?'}）{src}：{len(got)} 檔持股")
            else:
                diag[code] = "；".join(logs)[:600]
                print(f"  ⚠ {code}（{issuer or '?'}）無可用來源")
                for x in logs:
                    print(f"      · {x}")
        browser.close()

    if probe_only:
        print(f"[探針] 成功 {len(fresh)}／{len(targets)} 檔；未落檔。")
        return 0

    asof = _latest_trade_date()
    for v in fresh.values():
        v["date"] = asof
    doc = etfholdings.merge(etfholdings.load(), fresh, diag)
    quotes = _quotes()
    if quotes:
        etfholdings.annotate(doc, quotes)
        print(f"  ✓ 當日貢獻歸因：個股報價 {len(quotes)} 檔")
    else:
        print("  ⚠ 個股報價不可得 → 沿用既有貢獻明細（不覆寫成空）")
    ok = etfholdings.save(doc)
    print(f"{'✓ 落檔' if ok else '⚠ 本次全空、保留既有落檔'} {etfholdings.DATA_FP}"
          f"（{len(doc.get('etfs') or {})} 檔有揭露；本次新抓 {len(fresh)} 檔，基準日 {asof}）")
    return 0


def _quotes() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mod in ("twse", "tpex"):
        try:
            from importlib import import_module
            out.update(import_module(f"arm.connectors.{mod}").fetch_today_all())
        except Exception as e:                            # noqa: BLE001
            print(f"  ⚠ {mod} 個股報價不可得：{type(e).__name__}: {str(e)[:80]}")
    return out


def _latest_trade_date() -> str | None:
    try:
        from arm.connectors import twse
        return twse.latest_trade_date()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
