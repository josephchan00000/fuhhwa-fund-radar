#!/usr/bin/env python3
"""產復華基金追蹤版本儀表板 → dashboard/index.html（零安裝、雙擊即開）。

讀 data/funds/*.json（持股介紹）＋ config/holding_profiles.json（重點標的簡介）
＋ reports/usnews/{最新}_v1/_v2.md（昨夜美股新聞）。

用法：
  python scripts/fetch_holdings.py        # 先更新持股快照
  python scripts/gen_usnews.py            # 產昨夜美股提示包 → 由 Claude 產出兩檔
  python scripts/gen_fund_dashboard.py [--open]
"""
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import fund_dashboard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dashboard" / "index.html"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(fund_dashboard.render(), encoding="utf-8")
    print(f"[儀表板] 已寫入 {OUT}")
    # 籌碼雷達獨立頁（dashboard/x9.html＋個股走勢序列 x9s.json；主頁頁尾右下角小點進入）。失敗不影響主頁。
    try:
        from arm.lab import page as lab_page
        changed = lab_page.build()
        print(f"[籌碼雷達] {'已更新' if changed else '無變更'} {lab_page.OUT}（＋{lab_page.OUT_SER.name}）")
    except Exception as e:                                # noqa: BLE001
        print(f"[籌碼雷達] 建頁失敗（不影響主頁）：{type(e).__name__}: {e}")
    # 景氣溫度頁（dashboard/x9m.html；籌碼雷達頂欄「景氣」進入，docs/lab_heat_plan.md）。和籌碼雷達分開建、分開失敗。
    try:
        from arm.lab import heatpage
        changed = heatpage.build()
        print(f"[景氣溫度] {'已更新' if changed else '無變更'} {heatpage.OUT}")
    except Exception as e:                                # noqa: BLE001
        print(f"[景氣溫度] 建頁失敗（不影響主頁與籌碼雷達）：{type(e).__name__}: {e}")
    # 美股景氣頁（dashboard/x9mu.html＋各指數對照圖資料 x9muh-*.json；docs/lab_heat_us_plan.md）。分開建、分開失敗。
    try:
        from arm.lab import heatpage_us
        changed = heatpage_us.build()
        print(f"[美股景氣] {'已更新' if changed else '無變更'} {heatpage_us.OUT}")
    except Exception as e:                                # noqa: BLE001
        print(f"[美股景氣] 建頁失敗（不影響其他頁）：{type(e).__name__}: {e}")
    # 泡沫頁 dashboard/x9b.html：2026-10-23 起是轉址頁（泡沫在市場頁最下面、驗證與方法在研究紀錄頁；docs/lab_ia_v5_plan.md）。分開建、分開失敗。
    try:
        from arm.lab import bubpage
        changed = bubpage.build()
        print(f"[泡沫] {'已更新' if changed else '無變更'} {bubpage.OUT}（轉址頁）")
    except Exception as e:                                # noqa: BLE001
        print(f"[泡沫] 建頁失敗（不影響其他頁）：{type(e).__name__}: {e}")
    # 訊號：每一次的清單 x9oh-{市場}.json（市場頁的全部指標點開才下載）、研究卡 x9or-*.json、實測區 x9pr-*.json，
    # 以及轉址頁 x9o.html（2026-10-23 起；docs/lab_ia_v5_plan.md）。沿用上面景氣頁算好的「現在有沒有效」；分開建、分開失敗。
    try:
        from arm.lab import sigpage
        changed = sigpage.build()
        print(f"[訊號] {'已更新' if changed else '無變更'} {sigpage.OUT.parent}/x9oh-*.json、x9or-*.json、x9o.html（轉址頁）")
    except Exception as e:                                # noqa: BLE001
        print(f"[訊號總覽] 建頁失敗（不影響其他頁）：{type(e).__name__}: {e}")
    # 配置頁（x9.html；docs/lab_ia_v5_plan.md 第 18 節）要用三種警訊今天的讀數，那是上面景氣頁算的：
    # 籌碼雷達建頁時先用上一版的讀數，這裡換成今天的重建一次（讀數沒變就不改寫）。分開失敗。
    try:
        from arm.lab import page as lab_page
        changed = lab_page.finish()
        print(f"[配置] {'用今天的警訊讀數重建' if changed else '警訊讀數沒變，不改寫'} {lab_page.OUT}")
    except Exception as e:                                # noqa: BLE001
        print(f"[配置] 重建失敗（保留第一次建的版本）：{type(e).__name__}: {e}")
    # 總經策略的淨值與每一筆 x9xh.json（訊號總覽點開策略讀它）＋舊大神策略頁 x9x.html（轉址到策略頁；docs/lab_strategy_ia_plan.md）。
    # 總經策略本身在 x9.html 的研究紀錄身分（上面籌碼雷達建）。分開建、分開失敗。
    try:
        from arm.lab import xspage
        changed = xspage.build()
        print(f"[總經策略] {'已更新' if changed else '無變更'} {xspage.OUT_DATA}")
    except Exception as e:                                # noqa: BLE001
        print(f"[總經策略] 建檔失敗（不影響其他頁）：{type(e).__name__}: {e}")
    # 個股報告與產業報告（dashboard/rp/*.html；docs/lab_equity_report_plan.md 第 11 節）：reports/eq 每家最新一版一頁，
    # 頁首「最新收盤」讀上面籌碼雷達寫好的 x9t.json；沒有報告的舊頁拿掉。研究紀錄頁的報告清單在下面那一頁。分開建、分開失敗。
    try:
        from arm.lab import eqsite
        r = eqsite.build()
        print(f"[個股報告] 個股 {len(r['companies'])} 份、產業 {len(r['industries'])} 份，改寫 {r['wrote']} 頁 {eqsite.OUT}")
    except Exception as e:                                # noqa: BLE001
        print(f"[個股報告] 建頁失敗（不影響其他頁）：{type(e).__name__}: {e}")
    # 研究紀錄頁（x9r.html；docs/lab_ia_v5_plan.md 第 7 節；不在頂欄，配置頁頁尾小字進）。分開建、分開失敗。
    try:
        from arm.lab import research_page
        changed = research_page.build()
        print(f"[研究紀錄] {'已更新' if changed else '無變更'} {research_page.OUT}")
    except Exception as e:                                # noqa: BLE001
        print(f"[研究紀錄] 建頁失敗（不影響其他頁）：{type(e).__name__}: {e}")
    if "--open" in sys.argv[1:]:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
