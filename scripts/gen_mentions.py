#!/usr/bin/env python3
"""基金社群／廣告提及產生器 —— 提示包與驗證（基金動態雷達的人工查證源）。

PTT/Dcard/Mobile01/FB 粉專/YouTube 廣告等無免費 API，純 Python 抓不到 →
沿用 prompt-pack 哲學：

  python scripts/gen_mentions.py            # 產提示包 reports/mentions/prompts/{today}.md
  python scripts/gen_mentions.py --check    # 驗證最新 {date}.json 並列印

LLM 查證後回存 reports/mentions/{date}.json；dashboard 與自動新聞（fetch_mentions.py）
合併呈現於「基金動態雷達」。查不到的就留空陣列，不杜撰。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import config, fund_mentions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "mentions" / "prompts"


def build_prompt(today: date) -> str:
    tw = "\n".join(f"  · {f['id']}｜{f['name']}" for f in config.funds("tw"))
    gl = "\n".join(f"  · {f['id']}｜{f['name']}" for f in config.funds("global"))
    return f"""你是「台灣投信公司的品牌與輿情監測編輯」。請以 WebSearch 查找下列復華基金
近 7 天在**社群與廣告面**的公開提及（PTT、Dcard、Mobile01、Facebook 粉專貼文／廣告、
YouTube、部落格開箱…），回存 reports/mentions/{today:%Y-%m-%d}.json。
新聞面已由 Google News 自動抓取，這裡**只收社群/廣告/口碑**；查不到就給空陣列，
切勿杜撰貼文或連結；每筆必附日期與來源平台。

台北日期：{today:%Y/%m/%d}

台股清單：
{tw}
海外清單：
{gl}

JSON 結構：
{{
  "date": "{today:%Y-%m-%d}",
  "items": [
    {{"fund_id": "06", "kind": "social", "title": "Dcard 理財版：數位經濟基金定期定額心得討論串",
      "source": "Dcard", "url": "https://...", "date": "2026-07-01"}},
    {{"fund_id": "", "kind": "ad", "title": "復華投信 FB 粉專：台股基金形象廣告投放",
      "source": "Facebook", "date": "2026-06-30"}}
  ]
}}
kind ∈ {list(fund_mentions.KIND_LABEL)}；fund_id 對不到特定基金（公司/品牌層）留空字串。
合規：僅中性記錄公開提及之事實與日期，不評論內容、不摘錄績效訴求文字。
"""


def cmd_check() -> None:
    doc = fund_mentions.load_social()
    if not doc:
        print("找不到 reports/mentions/{date}.json｜先產提示包再查證回填。")
        return
    items = doc.get("items", [])
    print(f"[社群/廣告提及] 最新 {doc.get('date')}｜{len(items)} 筆")
    for it in items:
        print(f"  [{fund_mentions.KIND_LABEL.get(it.get('kind'), it.get('kind'))}] "
              f"{it.get('fund_id') or '公司層'}｜{it.get('title')}"
              f"（{it.get('source')}｜{it.get('date')}）")


def main() -> None:
    if "--check" in sys.argv[1:]:
        cmd_check()
        return
    today = date.today()
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today), encoding="utf-8")
    print(f"[社群/廣告提及 提示包] 已寫入 {out}")
    print("  下一步：在 Claude Code 說『依此提示包上網查證，回存 JSON』，或貼進聯網 Claude。")


if __name__ == "__main__":
    main()
