#!/usr/bin/env python3
"""昨夜美股新聞產生器（復華基金追蹤版本）。

即時新聞需「會上網查證的 LLM」→ 沿用本專案 prompt-pack 哲學，不在純 Python 裡杜撰新聞：

  python scripts/gen_usnews.py            # 產提示包 reports/usnews/prompts/{today}.md（兩版型）
  python scripts/gen_usnews.py --check    # 對最新產出跑禁用詞合規掃描

產出提示包後，兩條路皆可（兩版型都要）：
  A) 在 Claude Code 直接說「依 reports/usnews/prompts/{date}.md 上網查證，產 v1/v2 兩檔」
     → Claude 用 WebSearch 查昨夜美股、寫 reports/usnews/{date}_v1.md 與 _v2.md（本專案今日即這樣產）。
  B) 把提示包貼進你自己的 Claude（開啟聯網），回覆兩段分別存成 {date}_v1.md / _v2.md。

dashboard 會自動讀「最新一份」 {date}_v1/_v2.md 呈現並標合規燈。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, usnews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "usnews" / "prompts"


def build_prompt(today: date) -> str:
    ses = usnews.us_session_date(today)
    wk = usnews.weekend_note(today)
    xr = usnews.cross_report_note('us')
    anchor = usnews.calendar_anchor(today)
    prior = usnews.prior_block(
        usnews.prior_titles(usnews.NEWS_DIR, today, r"(\d{4}-\d{2}-\d{2})_v1\.md$"),
        "前一日昨夜美股 v1")
    return f"""你是「台灣投信公司給內外部溝通使用的公司與產業面速寫編輯」。請以繁體中文，
針對【昨夜美股交易時段】製作兩份新聞彙編。用 WebSearch/WebFetch 實際查證，勿杜撰標題、
數字、報價或引言；查不到就誠實加「資料侷限說明」。

台北日期（TST, UTC+8）：{today:%Y/%m/%d}
昨夜美股對應交易日（美東，請以實際交易日查證）：{ses:%Y/%m/%d}
{anchor}
{wk + chr(10) if wk else ''}{xr + chr(10) if xr else ''}{prior + chr(10) * 2 if prior else ''}建議關鍵字：AI, chip, semiconductor, Nvidia, AMD, TSMC, Intel, Micron, Broadcom,
Microsoft, Apple, Tesla, Meta, merger, acquisition, partnership, supply chain,
earnings, guidance, investment, capex, executive change, SEC, DOJ, lawsuit

請一次產出「兩份」，並各存成獨立檔：
  · reports/usnews/{today:%Y-%m-%d}_v1.md  ← 版型一（Top 3 速寫包，完整版）
  · reports/usnews/{today:%Y-%m-%d}_v2.md  ← 版型二（精簡版）

────────────────────────────────────────
{usnews.SPEC_V1}

────────────────────────────────────────
{usnews.SPEC_V2}

────────────────────────────────────────
【版型一末段必附之完整合規揭露段】
{usnews.DISCLOSURE}

【兩版型皆須遵守】僅為市場資訊彙編／教育用途，非投資建議或招攬；禁用詞：
{'、'.join(usnews.BANNED)}；機構觀點以「{usnews.ATTRIBUTION_HINT}」呈現；不預測報酬、不以過去績效推未來。
"""


def cmd_check() -> None:
    latest = usnews.load_latest()
    if not latest:
        print("找不到 reports/usnews/{date}_v1.md｜先產提示包再產出新聞。")
        return
    hits = latest["banned_hits"]
    print(f"[合規掃描] 最新新聞 {latest['date']}｜v1={'有' if latest['v1'] else '缺'}"
          f" v2={'有' if latest['v2'] else '缺'}")
    print("  🟢 無禁用詞" if not hits else f"  🔴 出現禁用詞：{'、'.join(hits)}（請人工修正）")


def main() -> None:
    if "--check" in sys.argv[1:]:
        cmd_check()
        return
    today = clock.today_tw()          # 台北日期（勿用 date.today()：UTC 容器會跨日錯置）
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today), encoding="utf-8")
    print(f"[昨夜美股 提示包] 已寫入 {out}")
    print(f"  昨夜美股交易日：{usnews.us_session_date(today):%Y/%m/%d}（美東，以實際交易日為準）")
    print("  下一步：在 Claude Code 說『依此提示包上網查證，產 v1/v2 兩檔』，或貼進聯網 Claude 回存兩檔。")


if __name__ == "__main__":
    main()
