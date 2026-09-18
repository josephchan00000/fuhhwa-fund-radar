#!/usr/bin/env python3
"""台股重點產生器（復華基金追蹤版本）—— 盤前/盤後自適應。

依「現在台北時間」自動判定模式（收盤 13:30 前＝盤前，之後＝盤後），產對應提示包。
同 gen_usnews 的 prompt-pack 哲學（純 Python 不杜撰新聞）：

  python scripts/gen_twnews.py            # 自動判定模式，產提示包 reports/twnews/prompts/{today}.md
  python scripts/gen_twnews.py --pre      # 強制盤前版型
  python scripts/gen_twnews.py --post     # 強制盤後版型
  python scripts/gen_twnews.py --check    # 對最新產出跑禁用詞合規掃描

產出提示包後：
  A) 在 Claude Code 說「依 reports/twnews/prompts/{date}.md 上網查證，產台股重點」
     → 寫 reports/twnews/{date}.md。
  B) 把提示包貼進聯網的 Claude，回覆存成 {date}.md。

dashboard 會自動讀「最新一份」呈現、標合規燈、萃取加權/櫃買指數進今日重點。
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, twevents, twnews, usnews  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "reports" / "twnews" / "prompts"

_PRE_KW = ("台股盤前、台指期夜盤、台積電 ADR、費城半導體、外資期貨、"
           "盤前焦點股、法人動向、記憶體、AI 供應鏈、除權息、法說會")
_POST_KW = ("台股盤後、加權指數、櫃買指數、三大法人、外資買賣超、台積電、聯發科、"
            "台達電、鴻海、除權息、AI、半導體、機器人概念、記憶體")


def build_prompt(today: date, mode: str) -> str:
    is_pre = mode == "pre"
    role = "台股盤前速寫編輯" if is_pre else "台股盤後速寫編輯"
    kw = _PRE_KW if is_pre else _POST_KW
    when = ("針對【今日台股開盤前／盤中】彙整最新、最重要的盤前情報（市場尚未收盤，"
            "聚焦昨夜美股影響、台指期夜盤、盤前焦點個股與法人／題材預期）"
            if is_pre else
            "針對【今日台股交易日】製作一份盤後重點彙編（聚焦收盤數據與三大法人籌碼）")
    anchor = usnews.calendar_anchor(today)
    manchor = usnews.market_anchor('tw_pre' if is_pre else 'tw_post', today)
    prior = usnews.prior_block(usnews.prior_titles(twnews.NEWS_DIR, today), "前一日台股報告")
    policy = twevents.tw_policy_note(today)   # 央行季會日／隔日「必成卡」旗標＋台灣政策與房市必收（2026-09-18）
    return f"""你是「台灣投信公司給內外部溝通使用的{role}」。請以繁體中文，
{when}。用 WebSearch/WebFetch 實際查證，勿杜撰點位、漲跌幅、法人金額或個股報價；
查不到就誠實加「資料侷限說明」。

台北日期（TST, UTC+8）：{today:%Y/%m/%d}（若今日休市，改寫最近一個台股交易日並註明）
目前模式：{'盤前（開盤前／盤中）——請抓最新盤前重要新聞' if is_pre else '盤後（收盤後）'}
{anchor}
{manchor + chr(10) if manchor else ''}{usnews.weekend_note(today) + chr(10) if usnews.weekend_note(today) else ''}{usnews.lane_note('tw') + chr(10)}{policy + chr(10)}{prior + chr(10) * 2 if prior else ''}建議關鍵字（僅為搜尋起點，選題以版型內「選題流程」為準）：{kw}

請產出一份，存成：reports/twnews/{today:%Y-%m-%d}.md
（標題請用「〈台股盤前重點〉」）""" + ("" if is_pre else "（標題請用「〈台股盤後重點〉」）") + f"""

────────────────────────────────────────
{twnews.spec_for(mode)}

────────────────────────────────────────
【末段必附之完整合規揭露段】
{usnews.DISCLOSURE}

【必須遵守】僅為市場資訊彙編／教育用途，非投資建議或招攬；禁用詞：
{'、'.join(usnews.BANNED)}；不預測報酬、不以過去績效推未來{'、不對開盤漲跌作預測性喊話' if is_pre else ''}。
"""


def cmd_check() -> None:
    latest = twnews.load_latest()
    if not latest:
        print("[台股重點] 尚無產出可掃描。")
        return
    hits = latest["banned_hits"]
    print(f"[{latest['label']}] {latest['date']}：" +
          ("🟢 合規掃描通過" if not hits else f"🔴 禁用詞：{'、'.join(hits)}"))


def main() -> None:
    args = sys.argv[1:]
    if "--check" in args:
        cmd_check()
        return
    mode = "pre" if "--pre" in args else "post" if "--post" in args else twnews.session_mode()
    today = clock.today_tw()          # 台北日期（勿用 date.today()：UTC 容器會跨日錯置）
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    out = PROMPT_DIR / f"{today:%Y-%m-%d}.md"
    out.write_text(build_prompt(today, mode), encoding="utf-8")
    label = "盤前" if mode == "pre" else "盤後"
    print(f"[台股{label}] 提示包已寫入 {out}（模式依台北時間自動判定，可用 --pre/--post 覆寫）")
    print("下一步：由會上網查證的 LLM 依提示包產 reports/twnews/{date}.md")


if __name__ == "__main__":
    main()
