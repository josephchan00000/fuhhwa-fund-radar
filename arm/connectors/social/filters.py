"""社群情報相關性過濾（M4）—— 只留與復華主角/競品/主動ETF 有關的貼文，去雜訊。

各 live adapter 共用：判斷一則內容是否相關、抽出文中提及的復華 ETF 代號。
"""
from __future__ import annotations

# 復華主角：代號 → 別名（名稱片段）
FH = {
    "00991A": ["00991a", "未來50", "未來五十"],
    "00998A": ["00998a", "全球金融股", "金融股票入息"],
    "00986D": ["00986d", "全球金融債", "金融債券入息"],
}
FH_BRAND = ["復華"]
# 競品（監看用，對齊 issuers.COMPETITORS + 熱門高股息）
COMPETITORS = ["00981a", "00403a", "00992a", "00980a", "00985a", "00990a",
               "00929", "00939", "00940", "00946"]
GENERIC = ["主動式etf", "主動etf", "主動 etf", "主動型etf"]


def extract_etfs(text: str) -> tuple[str, ...]:
    """文中提及的復華 ETF 代號（大寫）。"""
    tl = (text or "").lower()
    return tuple(code for code, alias in FH.items()
                 if code.lower() in tl or any(a in tl for a in alias))


def is_relevant(text: str) -> bool:
    """是否與復華主角/競品/主動ETF 相關（當素材庫 + 競品監測）。"""
    tl = (text or "").lower()
    if extract_etfs(text):
        return True
    if any(b in (text or "") for b in FH_BRAND) and ("etf" in tl or "主動" in text):
        return True
    return any(c in tl for c in COMPETITORS) or any(g in tl for g in GENERIC)
