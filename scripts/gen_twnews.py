#!/usr/bin/env python3
"""台股盤後重點產生器（復華基金追蹤版本）。

同 gen_usnews 的 prompt-pack 哲學（純 Python 不杜撰新聞）：

  python scripts/gen_twnews.py            # 產提示包 reports/twnews/prompts/{today}.md
  python scripts/gen_twnews.py --check    # 對最新產出跑禁用詞合規掃描

產出提示包後（單版型）：
  A) 在 Claude Code 說「依 reports/twnews/prompts/{date}.md 上網查證，產台股盤後重點」
     → 寫 reports/twnews/{date}.md。
  B) 把提示包貼進聯網的 Claude，回覆存成 {date}.md。

dashboard 會自動讀「最新一份」呈現、標合規燈、萃取加權/櫃買指數進今日重點。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import twnews, usnews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "twnews" / "prompts"


def build_prompt(today: date) -> str:
    return f"""你是「台灣投信公司給內外部溝通使用的台股盤後速寫編輯」。請以繁體中文，
針對【今日台股交易日】製作一份盤後重點彙編。用 WebSearch/WebFetch 實際查證，勿杜撰
點位、漲跌幅、法人金額或個股報價；查不到就誠實加「資料侷限說明」。

台北日期（TST, UTC+8）：{today:%Y/%m/%d}（若今日休市，改寫最近一個台股交易日並註明）
建議關鍵字：台股盤後、加權指數、櫃買指數、三大法人、外資買賣超、台積電、聯發科、
台達電、鴻海、除權息、AI、半導體、機器人概念、記憶體

請產出一份，存成：reports/twnews/{today:%Y-%m-%d}.md

────────────────────────────────────────
{twnews.SPEC}

────────────────────────────────────────
【末段必附之完整合規揭露段】
{usnews.DISCLOSURE}

【必須遵守】僅為市場資訊彙編／教育用途，非投資建議或招攬；禁用詞：
{'、'.join(usnews.BANNED)}；不預測報酬、不以過去績效推未來。
"""


def cmd_check() -> None:
    latest = twnews.load_latest()
    if not latest:
        print("[台股盤後] 尚無產出可掃描。")
        return
    hits = latest["banned_hits"]
    print(f"[台股盤後] {latest['date']}：" +
          ("🟢 合規掃描通過" if not hits else f"🔴 禁用詞：{'、'.join(hits)}"))


def main() -> None:
    if "--check" in sys.argv[1:]:
        cmd_check()
        return
    today = date.today()
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today), encoding="utf-8")
    print(f"[台股盤後] 提示包已寫入 {out}")
    print("下一步：由會上網查證的 LLM 依提示包產 reports/twnews/{date}.md")


if __name__ == "__main__":
    main()
