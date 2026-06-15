"""社群 / KOL 情報來源層（M4-2/M4-3）。

各平台爬取涉 ToS / 個資 / 著作權（M4-8），且多為登入/SPA：無單一公開 live 源。
故與 M2 競品持股 / M3 分點同策略——先以 drop-in 檔承接（Tier B），逐家 adapter
（YouTube/PTT/Dcard/vocus/新聞）授權後補實，仍回傳同一個 `SocialMention`，創意引擎不動。

創意引擎只透過 `recent_mentions()` 取料，與來源徹底解耦。
"""
from __future__ import annotations

from . import base
from .base import (NoData, SocialMention, analyze, curated_mentions)  # re-export

# 逐家 live adapter slot（授權後在此註冊；簽名 (as_of, window_days)->list[SocialMention]）。
# 例：LIVE_ADAPTERS["youtube"] = youtube.fetch —— 接上後 recent_mentions 自動納入、不改呼叫端。
SOURCES: dict[str, str] = {
    "youtube": "YouTube Data API（需 API key；M4-2，待授權 adapter）",
    "ptt": "PTT 股票板/股票公社（公開頁 / RSS；待 adapter）",
    "dcard": "Dcard 股票看板（公開 API/頁；待 adapter）",
    "vocus": "方格子 vocus（RSS；待 adapter）",
    "news": "鉅亨/MoneyDJ/Yahoo股市 等新聞（RSS；待 adapter）",
}
LIVE_ADAPTERS: dict[str, callable] = {}        # 預留：授權後逐家填入


def recent_mentions(as_of: str | None = None, window_days: int = 7) -> list[SocialMention]:
    """窗內社群情報：先 live adapters（目前無，待授權接），再 drop-in；依日期新→舊、聲量大→小。"""
    out: list[SocialMention] = []
    for name, fetch in LIVE_ADAPTERS.items():
        try:
            out += fetch(as_of, window_days) or []
        except Exception:
            continue                           # 單一來源失敗不影響其他（誠實略過）
    out += curated_mentions(as_of, window_days)
    return sorted(out, key=lambda m: (m.date, m.reach), reverse=True)
