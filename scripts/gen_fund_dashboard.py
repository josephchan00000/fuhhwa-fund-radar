#!/usr/bin/env python3
"""產復華基金追蹤版本儀表板（零安裝、雙擊即開）。

讀 data/{market.data}/*.json（持股介紹）＋ config/holding_profiles.json（重點標的簡介）
＋ reports/usnews|twnews/{最新}_v1/_v2.md（昨夜美股／台股新聞）。

D2(b)：預設產「整合頁」dashboard/index.html —— 同一頁上層「海外／台股」切換。
也可用 --market 產單一市場獨立頁（相容 CI 單市場 artifact）。

用法：
  python scripts/gen_fund_dashboard.py [--open]        # 整合頁（海外＋台股）→ dashboard/index.html
  python scripts/gen_fund_dashboard.py --market global # 只出海外版 → dashboard/index.html
  python scripts/gen_fund_dashboard.py --market tw     # 只出台股版 → dashboard/tw.html
"""
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import fund_dashboard, markets  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _arg(name: str) -> str | None:
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def main() -> None:
    market = _arg("--market")
    out_dir = ROOT / "dashboard"
    out_dir.mkdir(parents=True, exist_ok=True)
    if market:
        out = out_dir / markets.get(market)["out"]
        out.write_text(fund_dashboard.render(market), encoding="utf-8")
        print(f"[儀表板｜單一市場 {market}] 已寫入 {out}")
    else:
        out = out_dir / "index.html"       # 整合頁（海外＋台股上層切換）
        out.write_text(fund_dashboard.render_combined(("global", "tw")), encoding="utf-8")
        print(f"[儀表板｜整合頁 海外＋台股] 已寫入 {out}")
    if "--open" in sys.argv[1:]:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
