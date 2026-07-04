#!/usr/bin/env python3
"""總經／政策面速寫產生器（復華基金追蹤版本）。

同 gen_usnews 的 prompt-pack 哲學（純 Python 不杜撰新聞）：
  python scripts/gen_macronews.py          # 產提示包 reports/macronews/prompts/{today}.md
  python scripts/gen_macronews.py --check   # 對最新產出跑禁用詞合規掃描

產出提示包後，由會上網查證的 Claude（訂閱額度）依提示包產 reports/macronews/{date}.md。
dashboard 會自動讀「最新一份」呈現「總經・政策」區塊、標合規燈。
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, macronews, usnews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "macronews" / "prompts"
CAL_PROMPT_DIR = ROOT / "reports" / "macrocal" / "prompts"


def build_cal_prompt(today: date) -> str:
    return f"""你是「台灣投信公司政策面速寫編輯」。請以繁體中文、用 WebSearch/WebFetch 實際查證，
產出【本週美國重點經濟數據行事曆】，存成：reports/macrocal/{today:%Y-%m-%d}.md
（台北今日 {today:%Y/%m/%d}；以今日所在整週週一~週五為範圍）。

────────────────────────────────────────
{macronews.SPEC_CAL}

【必守】數字勿杜撰、查不到填「—」；狀態只填「已公布／未公布／休市」；僅資訊彙編、非投資建議、不含禁用詞。
"""


def build_prompt(today: date) -> str:
    ses = macronews.us_session_date(today)
    return f"""你是「台灣投信公司給內外部溝通使用的政策面速寫編輯」。請以繁體中文，用 WebSearch/WebFetch
實際查證，勿杜撰標題、數字或引言；查不到或跨來源矛盾就只留方向並誠實加「資料侷限說明」。

台北日期（TST, UTC+8）：{today:%Y/%m/%d}
昨夜美股對應交易日（美東，請以實際交易日查證）：{ses:%Y/%m/%d}
建議關鍵字：White House, executive order, tariff, China, sanction, foreign policy, Trump,
Federal Reserve, Powell, Jefferson, FOMC, statement, minutes, rate, export control,
Gaza, Ukraine, semiconductor, energy；投行＋(policy/Fed/tariff)。

請產出一份，存成：reports/macronews/{today:%Y-%m-%d}.md

────────────────────────────────────────
{macronews.SPEC_MACRO}

────────────────────────────────────────
【末段必附之完整合規揭露段】
{usnews.DISCLOSURE}

【必須遵守】僅為市場資訊彙編／教育用途，非投資建議或招攬；禁用詞：
{'、'.join(usnews.BANNED)}；不預測報酬、不以過去績效推未來。
"""


def cmd_check() -> None:
    latest = macronews.load_latest()
    if not latest:
        print("[總經政策] 尚無產出可掃描。")
        return
    hits = latest["banned_hits"]
    print(f"[總經政策] {latest['date']}：" +
          ("🟢 合規掃描通過" if not hits else f"🔴 禁用詞：{'、'.join(hits)}"))


def main() -> None:
    if "--check" in sys.argv[1:]:
        cmd_check()
        return
    today = clock.today_tw()          # 台北日期（勿用 date.today()：UTC 容器會跨日錯置）
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    CAL_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today), encoding="utf-8")
    cal_out = CAL_PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    cal_out.write_text(build_cal_prompt(today), encoding="utf-8")
    print(f"[總經政策 提示包] 已寫入 {out}")
    print(f"[本週行事曆 提示包] 已寫入 {cal_out}")
    print(f"  昨夜美股交易日：{macronews.us_session_date(today):%Y/%m/%d}（美東，以實際交易日為準）")
    print("  下一步：由會上網查證的 Claude 依提示包產 reports/macronews/{date}.md 與 reports/macrocal/{date}.md")


if __name__ == "__main__":
    main()
