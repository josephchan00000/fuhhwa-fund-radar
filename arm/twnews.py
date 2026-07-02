"""台股盤後重點（復華基金追蹤版本）—— 版型規格 ＋ 產出讀取 ＋ 合規掃描。

與 usnews 同一套 prompt-pack 哲學：
  · scripts/gen_twnews.py 產「可貼進 Claude 的提示包」（reports/twnews/prompts/{date}.md）；
  · 會上網查證的 LLM 產一份 markdown 回存 reports/twnews/{date}.md（單版型：盤後重點）；
  · dashboard 讀「最新一份」呈現、跑合規掃描、萃取加權／櫃買指數進今日重點。

讀取器／萃取／禁用詞掃描皆沿用 arm/usnews（純函式、可單測）。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import usnews

ROOT = Path(__file__).resolve().parent.parent
NEWS_DIR = ROOT / "reports" / "twnews"

# 台股指數標籤（給 usnews.extract_indices 用）；brief 取前兩項
IDX_LABELS = [(("加權指數", "TAIEX", "集中市場"), "加權指數"),
              (("櫃買", "OTC", "上櫃"), "櫃買指數")]

SPEC = """【版型：台股盤後重點】
範圍：當日台股（集中＋櫃買）之「公司與產業動因」＋盤面結構（權值/中小型輪動、
三大法人動向、除權息與重大公司事件）。聚焦：半導體/AI 供應鏈、電子權值、
題材族群輪動、法人籌碼；排除純技術線型喊盤與個股目標價。
版面：
  🔹指數速覽（加權指數、櫃買指數各 1 句：收盤點位＋漲跌幅；可補電子/金融類股；
     末加 1 句市場解析：權值 vs 中小型、輪動或避險）
  🔹Top 3 盤後卡（每則 100–160 字）：
     標題（來源＋日期｜消息屬性）
     1. 新聞摘要 2. 一句話重點 3. 對持股／族群影響 4. 對市場情緒影響
  🔹資料侷限說明（指數/法人數字以證交所、櫃買中心官方為準）
  I. 合規揭露（附完整揭露段）
用語合規：僅市場資訊彙編/教育用途、非投資建議；禁用詞同 usnews.BANNED；
不預測報酬、不以過去績效推未來；勿杜撰數字，查不到誠實註明。"""


def load_latest() -> dict | None:
    """dashboard 用：最新一份台股盤後重點 {date, md, banned_hits}。"""
    if not NEWS_DIR.exists():
        return None
    dates = sorted({m.group(1) for f in NEWS_DIR.glob("*.md")
                    if (m := re.match(r"(\d{4}-\d{2}-\d{2})\.md$", f.name))}, reverse=True)
    if not dates:
        return None
    d = dates[0]
    md = (NEWS_DIR / f"{d}.md").read_text(encoding="utf-8")
    return {"date": d, "md": md, "banned_hits": usnews.compliance_scan(md)}


def extract_indices(md: str) -> list[dict]:
    """台股加權／櫃買指數速覽（沿用 usnews 萃取器、換台股標籤）。"""
    return usnews.extract_indices(md, labels=IDX_LABELS)
