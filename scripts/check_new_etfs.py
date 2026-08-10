#!/usr/bin/env python3
"""新 ETF 自動發現閘門（2026-08-10 使用者：「你是怎麼確保之後都抓得到的呢？」）。

抓兩層來源 → 更新首見台帳 `data/etf_seen.json` → 把「市場上有／募集頁有，但
`etfwatch` 完全沒登錄」的檔寫進 `data/etf_upcoming_gap.json`（入庫、儀表板顯示 🔴）：
  ① TWSE＋TPEx 官方每日收盤（全市場代碼，零版式風險）→ 已掛牌卻沒登錄的新檔
  ② MoneyDJ 新基金募集頁（前瞻）→ 未掛牌又沒登錄的募集候選（fail-open）

設計理由與防呆鐵則見 `arm/etfdiscover.py` docstring（baseline 首建不報警、
來源不可達不覆寫、台帳只增不減）。

**本容器（雲端 Claude）proxy 擋 twse/tpex/moneydj → 本地跑必定 0 列、跳過寫檔，
那是環境限制不是壞掉**；真正的發現在正式區 CI（daily_fund.sh 步驟 3.6）。

exit code：有缺口 → 1（供想當硬閘門處使用）；無缺口／來源不可達 → 0。
CI 端以 `|| true` 收警示、不擋發佈（同 check_holdings_intro.py）。
用法：TZ=Asia/Taipei python3 scripts/check_new_etfs.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, etfdiscover  # noqa: E402

MONEYDJ_URL = "https://www.moneydj.com/funddj/fundmarket.djhtm?a=broncho-1"


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


def _offering_codes() -> set[str]:
    """MoneyDJ 新基金募集頁的 ETF 代碼（fail-open：抓不到／解析 0 筆 → 回空集）。"""
    try:
        from arm.http import get_bytes
        html = get_bytes(MONEYDJ_URL, cache_ttl=3600, retries=2).decode("utf-8", "ignore")
    except Exception as e:                                         # noqa: BLE001
        print(f"  ⚠ MoneyDJ 新基金頁抓取失敗（{type(e).__name__}: {str(e)[:90]}）"
              f"——僅損失募集前瞻層，掛牌層不受影響")
        return set()
    codes = etfdiscover.parse_offering_codes(html)
    print(f"  · MoneyDJ 新基金頁 {len(html)} bytes，掃出 ETF 型代碼 {len(codes)} 個")
    if not codes and len(html) > 5000:      # 頁面拿到了卻掃不到＝版式可能改了，留線索供收斂
        print("    ⚠ 頁面非空但 0 代碼——版式可能已變，請檢查 parse_offering_codes 的樣式")
    return codes


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
    offering = _offering_codes()
    if offering:
        gaps += etfdiscover.offering_gaps(offering, seen, known)
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
        where = f"已掛牌・首見 {g['first_seen']}" if g["kind"] == "listed" else "募集頁候選・尚未掛牌"
        print(f"  ✗ {g['code']} {g['name']}（{where}）")
    print("  補法：WebSearch 查證（募集期間／掛牌日／頻率，兩來源一致）後補進 "
          "arm/etfwatch.UPCOMING；策展上刻意不追蹤者填 track: False。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
