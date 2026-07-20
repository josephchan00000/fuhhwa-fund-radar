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
    hits = []
    for fid in range(95, 170):
        url = f"https://www.fhtrust.com.tw/funds/funds_detail/{fid}"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                head = r.read(20000).decode("utf-8", errors="replace")
            m = re.search(r"<title>([^<]+)</title>", head)
            title = (m.group(1).strip() if m else "")[:60]
            for t in TARGETS:
                if t in title:
                    hits.append((fid, title))
                    print(f"[find_fund_ids] ✅ id={fid} → {title}")
        except Exception:
            continue
    if not hits:
        print("[find_fund_ids] 掃描 95–169 無命中（頁面結構或 id 區間可能不同）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
