#!/usr/bin/env python3
"""M7 零安裝靜態儀表板 CLI —— 讀每日報告 + 文案層 → 產單一 dashboard/index.html。

用法：
  python scripts/gen_dashboard.py            # 全主角，用各檔最新報告
  python scripts/gen_dashboard.py --date 2026-06-15
  python scripts/gen_dashboard.py --open     # 產完用瀏覽器開（macOS）

純標準庫、無 npm/node/server。產物 dashboard/index.html 雙擊即開。
"""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import dashboard  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"


def main() -> None:
    ap = argparse.ArgumentParser(description="M7 靜態儀表板")
    ap.add_argument("--date", default=None, help="指定報告日期 YYYY-MM-DD（預設各檔最新）")
    ap.add_argument("--open", action="store_true", help="產完用瀏覽器開（macOS open）")
    args = ap.parse_args()

    model = dashboard.build_model(date=args.date)
    if not model["etfs"]:
        print("⚠ 尚無報告，請先跑 scripts/run_daily.py 與 scripts/gen_copy.py。")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(dashboard.render_html(model), encoding="utf-8")
    n_ideas = sum(e["stats"]["ideas"] for e in model["etfs"])
    fab = sum(e["stats"]["fabricated"] for e in model["etfs"])
    print(f"✅ 儀表板 → {OUT.relative_to(OUT.parent.parent)}"
          f"（{len(model['etfs'])} 檔 / {n_ideas} 想法 / 疑似杜撰 {fab}）")
    print(f"   雙擊開啟：{OUT}")
    if args.open:
        try:
            subprocess.run(["open", str(OUT)], check=False)
        except Exception:
            pass


if __name__ == "__main__":
    main()
