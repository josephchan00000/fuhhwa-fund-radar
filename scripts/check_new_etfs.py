#!/usr/bin/env python3
"""新 ETF 自動發現閘門（2026-08-10 使用者：「你是怎麼確保之後都抓得到的呢？」）。

抓兩層來源 → 更新首見台帳 `data/etf_seen.json` → 把「市場上有／募集頁有，但
`etfwatch` 完全沒登錄」的檔寫進 `data/etf_upcoming_gap.json`（入庫、儀表板顯示 🔴）：
  ① TWSE＋TPEx 官方每日收盤（全市場代碼，零版式風險）→ 已掛牌卻沒登錄的新檔
  ② 募集前瞻雙源（皆 fail-open）：MoneyDJ 新基金頁（代碼層）＋鉅亨 IPO 頁（名稱層，
     2026-08-10 使用者提供；cnyes 對 CI 可達已由 cnyesfund 天天證實、未派碼新檔也逮得住）

設計理由與防呆鐵則見 `arm/etfdiscover.py` docstring（baseline 首建不報警、
來源不可達不覆寫、台帳只增不減）。

**本容器（雲端 Claude）proxy 擋 twse/tpex/moneydj → 本地跑必定 0 列、跳過寫檔，
那是環境限制不是壞掉**；真正的發現在正式區 CI（daily_fund.sh 步驟 3.6）。

exit code：有缺口 → 1（供想當硬閘門處使用）；無缺口／來源不可達 → 0。
CI 端以 `|| true` 收警示、不擋發佈（同 check_holdings_intro.py）。
用法：TZ=Asia/Taipei python3 scripts/check_new_etfs.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, etfdiscover  # noqa: E402

MONEYDJ_URL = "https://www.moneydj.com/funddj/fundmarket.djhtm?a=broncho-1"
# 鉅亨 IPO 新基金頁（2026-08-10 使用者提供）：cnyes 對 CI 可達性由 cnyesfund 天天證實，
# 是前瞻層裡最可靠的一支；名稱層比對（未派碼新檔也逮得住），與 MoneyDJ 代碼層互補。
CNYES_IPO_URLS = ("https://fund.cnyes.com/IPO/index.htm", "https://fund.cnyes.com/IPO/")


def _market_etf_codes() -> dict[str, str]:
    """TWSE＋TPEx 當日全市場 → {ETF 代碼: 名稱}。單邊失敗只損失那個交易所、不中斷。"""
    out: dict[str, str] = {}
    for label, mod in (("twse", "twse"), ("tpex", "tpex")):
        try:
            from importlib import import_module
            rows = import_module(f"arm.connectors.{mod}").fetch_today_all()
        except Exception as e:                                     # noqa: BLE001
            print(f"  ⚠ {label} 每日收盤抓取失敗（{type(e).__name__}: {str(e)[:90]}）")
            continue
        n = 0
        for code, info in (rows or {}).items():
            if etfdiscover.is_etf_code(code):
                out[code] = (info or {}).get("name") or ""
                n += 1
        print(f"  · {label}：全市場 {len(rows or {})} 檔，其中 ETF 型代碼 {n} 檔")
    return out


def _fetch(url: str, label: str) -> str:
    from arm.http import get_bytes
    try:
        return get_bytes(url, cache_ttl=3600, retries=2).decode("utf-8", "ignore")
    except Exception as e:                                         # noqa: BLE001
        print(f"  ⚠ {label} 抓取失敗（{url} → {type(e).__name__}: {str(e)[:80]}）")
        return ""


def _offering_moneydj(html: str) -> tuple[set[str], list[str]]:
    """MoneyDJ 新基金頁 → (ETF 代碼, ETF 名稱)。

    2026-08-10 CI 首輪定案：**MoneyDJ 對 CI 可達**（54,564 bytes、非 WAF 空殼），但
    **掃出 0 個代碼——因為新基金募集頁本來就只列基金名稱與募集期間、還沒有代碼**
    （新檔募集期間多半尚未派碼）。所以代碼層對這一頁天生無效，改與 cnyes 同走名稱層；
    代碼掃描保留為「日後頁面若補上代碼」的免費加分項，抓 0 個不再視為版式異常。"""
    if not html:
        return set(), []
    codes = etfdiscover.parse_offering_codes(html)
    names = etfdiscover.extract_etf_names(html)
    print(f"  · MoneyDJ 新基金頁 {len(html)} bytes，代碼 {len(codes)} 個、名稱 {len(names)} 筆")
    return codes, names


def _offering_names_cnyes(html: str) -> list[str]:
    """鉅亨 IPO 頁的 ETF 名稱（fail-open：抓不到／0 筆 → 回空，僅損失名稱前瞻層）。"""
    if not html:
        return []
    names = etfdiscover.extract_etf_names(html)
    print(f"  · 鉅亨 IPO 頁 {len(html)} bytes，抽出 ETF 名稱 {len(names)} 筆"
          + (f"：{'、'.join(names[:5])}{'…' if len(names) > 5 else ''}" if names else ""))
    if not names and len(html) > 5000:
        print("    ⚠ 頁面非空但 0 名稱——版式可能已變，檢查 etfdiscover._ETF_NAME 樣式")
    return names


def _probe_context(html: str, names: list[str], label: str) -> None:
    """結構探針（僅日誌、不進資料）：印首筆名稱周邊原文片段，供日後補「募集期間」欄位。

    2026-08-10 CI 首輪修正：原本借用 `cnyesfund._objects_from_html()`，但**那支錨定
    "cnyesId" 字串**——IPO 頁沒有該鍵 → 回空 → 整輪一行探針都沒印。改印「名稱周邊
    原文」：這正是 2026-07-29 元大那輪學到的——**印次數／鍵名無法決斷結構，印上下文
    片段才能一輪定位**（看得出是 HTML 表格還是內嵌 JSON、募集期間欄長什麼樣）。"""
    if not (html and names):
        return
    i = html.find(names[0])
    if i < 0:
        return
    frag = re.sub(r"\s+", " ", html[max(0, i - 220): i + 220])
    print(f"    · [{label} 結構探針] 首筆名稱周邊原文：{frag}")


def main() -> int:
    today = clock.today_tw()
    print("[新 ETF 發現] 掃市場首見台帳＋募集頁…")
    market = _market_etf_codes()
    seen, fresh = etfdiscover.merge_seen(etfdiscover.load_seen(), market, today)
    if market:
        etfdiscover.SEEN_FP.parent.mkdir(parents=True, exist_ok=True)
        etfdiscover.SEEN_FP.write_text(
            __import__("json").dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
        if seen.get("seeded") == today.isoformat():
            print(f"  · 首次建台帳：{seen.get('n')} 檔既有 ETF 一次認列 baseline（不報缺口）")
        elif fresh:
            print(f"  · 本次市場新增代碼 {len(fresh)} 檔：{'、'.join(fresh)}")

    known = etfdiscover.known_codes()
    gaps = etfdiscover.listed_gaps(seen, known, today)

    # 前瞻雙源：兩頁都走名稱層（新檔募集期間多半尚未派碼），MoneyDJ 另撿代碼當加分
    dj_html = _fetch(MONEYDJ_URL, "MoneyDJ 新基金頁")
    cn_html = next((h for h in (_fetch(u, "鉅亨 IPO 頁") for u in CNYES_IPO_URLS) if h), "")
    dj_codes, dj_names = _offering_moneydj(dj_html)
    cn_names = _offering_names_cnyes(cn_html)
    _probe_context(cn_html, cn_names, "cnyes")
    _probe_context(dj_html, dj_names, "moneydj")
    if dj_codes:
        gaps += etfdiscover.offering_gaps(dj_codes, seen, known)
    if dj_names or cn_names:
        gaps += etfdiscover.offering_name_gaps(cn_names + dj_names, seen,
                                               etfdiscover.known_names())
    _fp, saved = etfdiscover.save_gap(gaps, sources_ok=bool(market))
    if not saved:
        # 誠實回報「沒檢查」而不是「沒問題」——把未檢查寫成 🟢 0 缺口正是靜默失敗那一型
        print("[新 ETF 發現] ⚪ 市場來源不可達，本輪未檢查（本容器 proxy 擋 twse/tpex 屬正常；"
              "真正的檢查在正式區 CI）→ 既有 gap 檔保持原樣")
        return 0
    if not gaps:
        print(f"[新 ETF 發現] 🟢 無漏網新 ETF（已追蹤／已登錄 {len(known)} 檔）")
        return 0
    print(f"[新 ETF 發現] 🔴 {len(gaps)} 檔新 ETF 不在 etfwatch 清單裡：")
    for g in gaps:
        where = (f"已掛牌・首見 {g['first_seen']}" if g["kind"] == "listed"
                 else f"募集頁候選・尚未掛牌（{g.get('src') or 'moneydj'}）")
        print(f"  ✗ {g.get('code') or '（代號未定）'} {g['name']}（{where}）")
    print("  補法：WebSearch 查證（募集期間／掛牌日／頻率，兩來源一致）後補進 "
          "arm/etfwatch.UPCOMING；策展上刻意不追蹤者填 track: False。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
