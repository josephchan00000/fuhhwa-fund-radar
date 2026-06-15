"""統一分點進出介面（M3-1/M3-2）—— 籌碼推敲引擎與資料源解耦的接縫。

券商分點買賣超（§18.4）無單一乾淨公開 live 源：證交所 `bsr.twse.com.tw` 為「逐檔 +
驗證碼」、第三方（玩股網/Wantgoo/Histock/XQ）多為 SPA 或付費。故比照 M2 競品持股，採
**source-agnostic** 設計——不論證交所、第三方彙整、或未來逐家 adapter，全部歸一成
`BrokerFlow(target_id, date, broker_id, broker_name, net)`，籌碼引擎只吃這個。

對象（M3-2）：(a) 復華 ETF 本身的分點進出；(b) 重倉成分股的分點進出。
落檔即生效：把分點資料放成 `config/broker_flows/{target_id}.json` 引擎立即計算、不改碼。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CFG = Path(__file__).resolve().parents[3] / "config"
DROP_DIR = CFG / "broker_flows"
BROKER_MAP_FILE = CFG / "broker_map.json"


class NoData(Exception):
    """該標的當前無可用分點來源（證交所逐檔驗證碼／第三方 SPA，待 adapter 或 drop-in）。"""


@dataclass(frozen=True)
class BrokerFlow:
    target_id: str          # 這筆分點進出針對誰（個股/ETF 代號）
    date: str               # 交易日 ISO
    broker_id: str          # 分點代號（券商分公司層級）
    broker_name: str
    net: int                # 當日買賣超（張；買超為正、賣超為負）


@dataclass(frozen=True)
class TargetFlows:
    target_id: str
    target_name: str
    flows: list[BrokerFlow]            # 窗內逐日 × 各分點
    day_volume: dict[str, int]         # {date: 該標的當日總成交張數}（算買超佔比；可空）
    as_of: str | None = None
    tier: str = "B"


def broker_map() -> dict:
    """分點別名對照表（config/broker_map.json）；無檔回 {}。"""
    if not BROKER_MAP_FILE.exists():
        return {}
    return json.loads(BROKER_MAP_FILE.read_text(encoding="utf-8"))


def classify(broker_id: str, broker_name: str, bmap: dict | None = None) -> dict:
    """分點 → 買家身份『推估』。先比代號、再比名稱關鍵字，皆不中歸『不明/中實戶』。

    回傳 {label, kind, confidence}，confidence 一律 '推估'（分點只到分公司，非實名）。
    """
    bmap = bmap if bmap is not None else broker_map()
    hit = (bmap.get("by_id") or {}).get(broker_id)
    if hit:
        return {"label": hit["label"], "kind": hit["kind"], "confidence": "推估"}
    name = broker_name or ""
    for kw, kind in (bmap.get("by_name_keyword") or {}).items():
        if kw in name:
            return {"label": f"{name}（{kind}）", "kind": kind, "confidence": "推估"}
    return {"label": name or broker_id, "kind": "中實戶", "confidence": "推估"}


def curated_flows(target_id: str) -> TargetFlows | None:
    """分點 drop-in（config/broker_flows/{target_id}.json）；無則 None。

    格式（見該目錄 README）：
      {target_id, target_name, as_of, tier, provenance,
       day_volume:{date:張}, flows:[{date,broker_id,broker_name,net}, ...]}
    """
    path = DROP_DIR / f"{target_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    flows = [BrokerFlow(target_id, f["date"], str(f["broker_id"]),
                        f.get("broker_name", ""), int(f.get("net") or 0))
             for f in data.get("flows", [])]
    day_volume = {k: int(v) for k, v in (data.get("day_volume") or {}).items()}
    return TargetFlows(target_id, data.get("target_name", target_id), flows,
                       day_volume, data.get("as_of"), data.get("tier", "B"))
