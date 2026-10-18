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
    if "--open" in sys.argv[1:]:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
