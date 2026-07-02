#!/usr/bin/env python3
"""台股新聞產生器（復華台股基金追蹤版本｜D1(b)）—— 台股盤後重點 ＋ 盤前美股影響。

即時新聞需「會上網查證的 LLM」→ 沿用 prompt-pack 哲學，不在純 Python 裡杜撰新聞：

  python scripts/gen_twnews.py            # 產提示包 reports/twnews/prompts/{today}.md（兩版型）
  python scripts/gen_twnews.py --check    # 對最新產出跑禁用詞合規掃描

產出提示包後（兩版型都要）：
  A) 在 Claude Code 說「依 reports/twnews/prompts/{date}.md 上網查證，產 v1/v2 兩檔」
     → Claude 用 WebSearch 查台股盤後與昨夜美股、寫 reports/twnews/{date}_v1.md 與 _v2.md。
  B) 把提示包貼進聯網 Claude，回存兩檔。

dashboard（台股面板）會自動讀「最新一份」呈現並標合規燈。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import twnews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "twnews" / "prompts"


def build_prompt(today: date) -> str:
    tw = twnews.tw_session_date(today)
    us = twnews.us_session_date(today)
    return f"""你是「台灣投信公司給內外部溝通使用的台股公司與產業面速寫編輯」。請以繁體中文，
製作兩份台股導向新聞彙編。用 WebSearch/WebFetch 實際查證，勿杜撰標題、數字、報價或引言；
查不到就誠實加「資料侷限說明」。

台北日期（TST, UTC+8）：{today:%Y/%m/%d}
最近台股交易日（盤後重點對象，請以實際交易日/國定假日查證）：{tw:%Y/%m/%d}
昨夜美股對應交易日（盤前影響對象，美東，請以實際交易日查證）：{us:%Y/%m/%d}
建議關鍵字：台積電, 聯發科, 鴻海, 台達電, 三大法人, 外資買賣超, 投信, AI 伺服器, CoWoS,
PCB, ABF 載板, 被動元件, 光通訊, 費城半導體, Nvidia, AMD, 台積電 ADR, 法說會, 月營收

請一次產出「兩份」，並各存成獨立檔：
  · reports/twnews/{today:%Y-%m-%d}_v1.md  ← 版型一（台股盤後重點，完整版）
  · reports/twnews/{today:%Y-%m-%d}_v2.md  ← 版型二（盤前美股影響，精簡版）

────────────────────────────────────────
{twnews.SPEC_V1}

────────────────────────────────────────
{twnews.SPEC_V2}

────────────────────────────────────────
【版型一末段必附之完整合規揭露段】
{twnews.DISCLOSURE}

【兩版型皆須遵守】僅為市場資訊彙編／教育用途，非投資建議或招攬；禁用詞：
{'、'.join(twnews.BANNED)}；機構觀點以「{twnews.ATTRIBUTION_HINT}」呈現；不預測報酬、不以過去績效推未來。
台股個股同樣受禁用詞規範（不標目標價、不建議買賣）。
"""


def cmd_check() -> None:
    latest = twnews.load_latest()
    if not latest:
        print("找不到 reports/twnews/{date}_v1.md｜先產提示包再產出新聞。")
        return
    hits = latest["banned_hits"]
    print(f"[合規掃描] 最新台股新聞 {latest['date']}｜v1={'有' if latest['v1'] else '缺'}"
          f" v2={'有' if latest['v2'] else '缺'}")
    print("  🟢 無禁用詞" if not hits else f"  🔴 出現禁用詞：{'、'.join(hits)}（請人工修正）")


def main() -> None:
    if "--check" in sys.argv[1:]:
        cmd_check()
        return
    today = date.today()
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today), encoding="utf-8")
    print(f"[台股新聞 提示包] 已寫入 {out}")
    print(f"  台股交易日：{twnews.tw_session_date(today):%Y/%m/%d}｜"
          f"昨夜美股交易日：{twnews.us_session_date(today):%Y/%m/%d}（以實際交易日為準）")
    print("  下一步：在 Claude Code 說『依此提示包上網查證，產 v1/v2 兩檔』，或貼進聯網 Claude 回存兩檔。")


if __name__ == "__main__":
    main()
