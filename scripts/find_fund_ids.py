#!/usr/bin/env python3
"""一次性：掃描復華官網 funds_detail id 區間，找出新基金的官網 id（CI 專用）。

背景（2026-07-21）：使用者新增「復華全球AI動力成長指數基金」「復華台灣菁英50指數基金」，
兩檔為 2026/06 新募——搜尋引擎尚未索引其官網頁、本 Claude 容器 proxy 又擋 fhtrust，
只能靠正式區（CI，完整網路）掃 id。找到後把 id 填進 config/funds.json、刪除本腳本與
daily.yml 的暫時步驟。輸出只進 CI log、不落檔、永不 fail。
"""
import re
import sys
import urllib.request

TARGETS = ["AI動力成長", "台灣菁英50", "全球創新金融", "已開發國家300"]
UA = {"User-Agent": "Mozilla/5.0 (fund-id-probe)"}


def main():
    # 首輪掃 funds_detail 網頁無命中（頁面 JS 渲染、title 不含基金名）——改掃官網 API
    # （與 fetch_holdings 同一支 /api/fund，回 JSON 內含基金名）。
    hits = []
    for fid in range(95, 170):
        url = f"https://www.fhtrust.com.tw/api/fund?fundID={fid}"
        try:
            import json as _json
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                doc = _json.loads(r.read().decode("utf-8", errors="replace"))
            blob = _json.dumps(doc, ensure_ascii=False)[:3000]
            m = re.search(r'"fundName"\s*:\s*"([^"]+)"', blob) or \
                re.search(r'"name"\s*:\s*"([^"]+)"', blob)
            name = m.group(1) if m else ""
            for t in TARGETS:
                if t in name or t in blob:
                    hits.append((fid, name or "(名稱鍵未識別，見 blob)"))
                    print(f"[find_fund_ids] ✅ id={fid} → {name or blob[:120]}")
        except Exception:
            continue
    if not hits:
        print("[find_fund_ids] API 掃描 95–169 無命中——改印 150–169 原始回應頭 300 字供人工判讀：")
        for fid in range(150, 170):
            try:
                req = urllib.request.Request(
                    f"https://www.fhtrust.com.tw/api/fund?fundID={fid}", headers=UA)
                with urllib.request.urlopen(req, timeout=10) as r:
                    print(f"  id={fid}:", r.read(300).decode("utf-8", errors="replace").replace("\n", " "))
            except Exception as e:
                print(f"  id={fid}: ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
