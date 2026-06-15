"""分點進出來源層（M3-1/M3-2）。

證交所分點為「逐檔 + 驗證碼」、第三方多為 SPA/付費（見 §18.4）：無單一公開 live 源。
故與 M2 競品持股同策略——先以 drop-in 檔承接（Tier B），逐家／第三方 adapter 補實後
仍回傳同一個 `BrokerFlow` 介面，籌碼引擎不動。

籌碼引擎只透過 `gather()` 取料，與來源徹底解耦。
"""
from __future__ import annotations

from . import base, finmind, histock, history
from .base import BrokerFlow, NoData, TargetFlows, broker_map, classify  # re-export

# 第三方／官方分點 adapter slot（優先序：drop-in > FinMind(付費,最完整) > Histock(免費)）。
SOURCES: dict[str, str] = {
    "finmind": "FinMind TaiwanStockTradingDailyReport（API・全分點+多日+量；需 FINMIND_TOKEN 付費）",
    "histock": "Histock 分公司進出（靜態 HTML 表・免費前 N 大，已接 histock.py）",
    "twse_bsr": "證交所 bsr.twse.com.tw（逐檔 + 驗證碼，待 OCR/人工承接）",
    "wantgoo": "Wantgoo 分點主力（SPA/會員制，待 adapter）",
}

WINDOW = 6   # 多日窗（約一個交易週）


def load_flows(target_id: str, *, live: bool = True, window: int = WINDOW) -> TargetFlows:
    """單一標的分點進出，優先序：

    1) drop-in（`config/broker_flows/{id}.json`，人工/第三方覆蓋）。
    2) **FinMind**（若設 `FINMIND_TOKEN`）：一次取全分點 + 多日 + 量 → 連續買超即時真實。
    3) **Histock**（免費）：當日前 N 大分點，**累積每日快照**成多日窗（`history`）。
    """
    curated = base.curated_flows(target_id)
    if curated is not None:
        return curated
    if not live:
        raise NoData(f"{target_id} 無分點來源（drop-in 未落檔且未啟用 live）")
    if finmind.available():                      # 付費最完整源：全分點 + 多日 + 量
        try:
            return finmind.fetch(target_id, window_days=window)
        except NoData:
            pass                                 # 該檔無 FinMind 料 → 退 Histock
    date, flows = histock.fetch_day(target_id)   # 免費源；取不到會 raise NoData
    history.record(target_id, date, flows)
    history.prune(target_id)
    return history.load_window(target_id, days=window) or TargetFlows(
        target_id, target_id, flows, {}, as_of=date, tier="B")


def gather(targets: list[tuple[str, str]]) -> list[TargetFlows]:
    """收集多個標的（本檔 + 重倉股）的分點進出，只回「實際取得到」的（取不到誠實略過）。

    targets: [(target_id, target_name), ...]。
    """
    out: list[TargetFlows] = []
    seen: set[str] = set()
    for tid, _name in targets:
        if tid in seen:
            continue
        seen.add(tid)
        try:
            out.append(load_flows(tid))
        except NoData:
            continue
    return out
