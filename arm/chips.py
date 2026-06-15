"""籌碼分點推敲引擎（§18.4, M3-4）—— 「誰在大買」的聰明錢佐證。

純計算、與資料源無關：吃統一的 `TargetFlows`（brokers 連接器提供），對每個標的算出
  - key_brokers   關鍵分點（窗內淨買超最多者，附連續買超天數、買超佔成交比）
  - top_buyer     最強買盤分點 + 買家身份『推估』（外資/投信/中實戶/特定金主）
並彙總成本檔（ETF 自身）+ 重倉成分股兩組視角。

鐵則（§18.4）：分點只到分公司層級，**真實身份無法 100% 確認** → 所有買家推論一律標
『推估・非確認』。設計原則同專案：能算的就算、缺料就誠實降級（data_status 標明缺什麼）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .connectors.brokers.base import BrokerFlow, TargetFlows, classify

ACTIVE_FLOW_DIR = Path(__file__).resolve().parent.parent / "config" / "active_flow"


def _by_broker(flows: list[BrokerFlow]) -> dict[str, dict]:
    """彙總窗內每個分點：{broker_id: {name, net_total, by_date:{date:net}}}。"""
    agg: dict[str, dict] = {}
    for f in flows:
        slot = agg.setdefault(f.broker_id, {"name": f.broker_name, "net_total": 0, "by_date": {}})
        slot["net_total"] += f.net
        slot["by_date"][f.date] = slot["by_date"].get(f.date, 0) + f.net
        if f.broker_name and not slot["name"]:
            slot["name"] = f.broker_name
    return agg


def consecutive_buy_days(by_date: dict[str, int], all_dates: list[str] | None = None) -> int:
    """從最近交易日往回數、連續『淨買超(>0)』的天數。

    給 `all_dates`（窗內所有交易日）時，分點**當日未上榜＝視為中斷**（更嚴謹的連續定義）；
    不給則只看該分點有資料的日子（向後相容）。
    """
    days = sorted(all_dates if all_dates is not None else by_date, reverse=True)
    streak = 0
    for d in days:
        if by_date.get(d, 0) > 0:
            streak += 1
        else:
            break
    return streak


def buy_ratio(net: int, day_volume: dict[str, int]) -> float | None:
    """關鍵分點窗內淨買超 佔 同期該標的總成交量比例（0~1）；無量資料回 None。"""
    tot = sum(v for v in day_volume.values() if v)
    if not tot:
        return None
    return round(net / tot, 4)


def key_brokers(tf: TargetFlows, *, top: int = 3, min_net: int = 1,
                bmap: dict | None = None) -> list[dict]:
    """窗內淨買超最多的關鍵分點（≥ min_net 張），附連續買超天數/佔比/身份推估。

    多日窗：`net` 為窗內累積淨買超、`days` 為（以窗內交易日為準的）真實連續買超天數、
    `window_days` 為窗涵蓋的交易日數。
    """
    agg = _by_broker(tf.flows)
    all_dates = sorted({f.date for f in tf.flows if f.date})
    out: list[dict] = []
    for bid, slot in agg.items():
        if slot["net_total"] < min_net:
            continue
        out.append({
            "broker_id": bid,
            "broker_name": slot["name"],
            "net": slot["net_total"],
            "days": consecutive_buy_days(slot["by_date"], all_dates),
            "window_days": len(all_dates),
            "buy_ratio": buy_ratio(slot["net_total"], tf.day_volume),
            "identity": classify(bid, slot["name"], bmap),
        })
    out.sort(key=lambda x: (-x["net"], -x["days"]))
    return out[:top]


def aggregate_by_identity(tf: TargetFlows, *, bmap: dict | None = None) -> dict:
    """把窗內買超分點按『推估身份』合計 → {kind: {net, n}}，並挑出最強身份買盤。

    『外資分點合計買超 +X 張（N 家外資分點同步）』比單一分點更有說服力（聰明錢共識）。
    """
    agg = _by_broker(tf.flows)
    by_kind: dict[str, dict] = {}
    for bid, slot in agg.items():
        if slot["net_total"] <= 0:                # 只計買超側
            continue
        kind = classify(bid, slot["name"], bmap)["kind"]
        k = by_kind.setdefault(kind, {"net": 0, "n": 0, "brokers": []})
        k["net"] += slot["net_total"]
        k["n"] += 1
        k["brokers"].append(slot["name"])
    return dict(sorted(by_kind.items(), key=lambda kv: -kv[1]["net"]))


def analyze_target(tf: TargetFlows, *, top: int = 3, min_net: int = 1,
                   bmap: dict | None = None) -> dict | None:
    """單一標的的關鍵分點推敲；無顯著買盤回 None。"""
    kb = key_brokers(tf, top=top, min_net=min_net, bmap=bmap)
    if not kb:
        return None
    ident = aggregate_by_identity(tf, bmap=bmap)
    foreign = ident.get("外資", {})
    return {"target_id": tf.target_id, "target_name": tf.target_name,
            "as_of": tf.as_of, "tier": tf.tier,
            "key_brokers": kb, "top_buyer": kb[0],
            "identity_net": ident,
            "foreign_net": foreign.get("net", 0), "foreign_n": foreign.get("n", 0)}


# ───────────────────────── 主動ETF/投信籌碼（法人層級，etfinfo 可得替代源）─────────────────────────
def _metric(item: dict, label: str) -> str | None:
    for m in item.get("metrics") or []:
        if m.get("label") == label:
            return m.get("value")
    return None


def _to_yi(val: str | None) -> float:
    """'+5.0 億' → 5.0；'+1,234 萬' → 0.1234；無法解析 → 0。"""
    if not val:
        return 0.0
    m = re.search(r"[-+]?[0-9.]+", val.replace(",", ""))
    n = float(m.group()) if m else 0.0
    return n / 10000 if "萬" in val else n


def load_active_flow() -> tuple[str | None, list[dict]]:
    """讀最新的主動ETF籌碼追蹤 drop-in（config/active_flow/{date}.json）；無則 (None, [])。"""
    if not ACTIVE_FLOW_DIR.exists():
        return None, []
    files = sorted(ACTIVE_FLOW_DIR.glob("[0-9]*.json"))
    if not files:
        return None, []
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    return data.get("as_of"), data.get("items", [])


def institutional_flow(fund_holdings: list[dict], active_items: list[dict], *, top: int = 5) -> list[dict]:
    """本檔持股 ∩ 主動ETF/投信『估算新進+加碼』清單 → 聰明錢共識（法人層級，非個別分點）。

    依「法人估算金額(億) + 本檔權重」排序：本檔重倉又被法人追買＝最強共識題材。
    """
    by_code = {str(it.get("stockCode")): it for it in (active_items or [])}
    out: list[dict] = []
    for h in fund_holdings:
        it = by_code.get(str(h.get("stock_id")))
        if not it:
            continue
        est_yi = round(_to_yi(_metric(it, "估算新進")) + _to_yi(_metric(it, "估算加碼")), 2)
        out.append({
            "stock_id": str(h.get("stock_id")), "name": h.get("stock_name"),
            "weight": h.get("weight") or 0.0, "industry": it.get("industry"),
            "n_etf": _metric(it, "新進 ETF"), "n_sitc": _metric(it, "投信"),
            "est_new": _metric(it, "估算新進"), "est_add": _metric(it, "估算加碼"),
            "est_yi": est_yi, "reason": it.get("reason"), "tags": it.get("tags") or [],
        })
    out.sort(key=lambda x: (-x["est_yi"], -(x["weight"] or 0)))
    return out[:top]


def compute(bundles: list[TargetFlows], *, fund_id: str | None = None,
            broker_map: dict | None = None, top: int = 3, min_net: int = 1,
            fund_holdings: list[dict] | None = None, active_items: list[dict] | None = None,
            active_asof: str | None = None) -> dict:
    """籌碼推敲總入口。bundles=本檔+重倉股的券商分點；缺料即降級（data_status）。

    回傳 {data_status, fund, holdings[], institutional[], active_asof, disclaimer}：
      fund          = 本檔(ETF 自身)券商分點推敲（fund_id 對應的 bundle）或 None。
      holdings      = 其餘標的（重倉成分股）的券商分點推敲，依最強買盤淨買超排序。
      institutional = 本檔持股被主動ETF/投信估算新進的清單（etfinfo 法人籌碼，非個別分點）。
    """
    fund_res, holding_res = None, []
    for tf in bundles:
        res = analyze_target(tf, top=top, min_net=min_net, bmap=broker_map)
        if res is None:
            continue
        if fund_id and tf.target_id == fund_id:
            fund_res = res
        else:
            holding_res.append(res)
    holding_res.sort(key=lambda r: -r["top_buyer"]["net"])
    inst = institutional_flow(fund_holdings or [], active_items or [])

    status = "full" if (fund_res and holding_res) else \
             "fund_only" if fund_res else \
             "holdings_only" if holding_res else "none"
    return {
        "data_status": status,
        "fund": fund_res,
        "holdings": holding_res,
        "institutional": inst,
        "active_asof": active_asof,
        "disclaimer": "券商分點身份為推估・非確認；主動ETF/投信為法人層級籌碼（etfinfo 估算，Tier B 待核對）（§18.4）",
    }
