"""分點進出來源層（M3-1/M3-2）。

證交所分點為「逐檔 + 驗證碼」、第三方多為 SPA/付費（見 §18.4）：無單一公開 live 源。
故與 M2 競品持股同策略——先以 drop-in 檔承接（Tier B），逐家／第三方 adapter 補實後
仍回傳同一個 `BrokerFlow` 介面，籌碼引擎不動。

籌碼引擎只透過 `gather()` 取料，與來源徹底解耦。
"""
from __future__ import annotations

from . import base, histock
from .base import BrokerFlow, NoData, TargetFlows, broker_map, classify  # re-export

# 第三方／官方分點 adapter slot。
SOURCES: dict[str, str] = {
    "histock": "Histock 分公司進出（靜態 HTML 表，已接 arm/connectors/brokers/histock.py）",
    "twse_bsr": "證交所 bsr.twse.com.tw（逐檔 + 驗證碼，待 OCR/人工承接）",
    "wantgoo": "Wantgoo 分點主力（SPA/會員制，待 adapter）",
}


def load_flows(target_id: str, *, live: bool = True) -> TargetFlows:
    """單一標的分點進出：先 drop-in（可人工覆蓋），無則 Histock live，再無則 NoData。"""
    curated = base.curated_flows(target_id)
    if curated is not None:
        return curated
    if live:
        return histock.fetch(target_id)        # 取不到會自己 raise NoData
    raise NoData(f"{target_id} 無分點來源（drop-in 未落檔且未啟用 live）")


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
