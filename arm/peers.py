"""全市場主動式 ETF 同類排名引擎（純 TWSE 官方價，100% 正確）。

回答「同類排名 / 誰被比下去」。持股差異化（獨門/重疊）需競品持股，
無乾淨公開來源 → 見 diff_engine.py 的 adapter 介面（下一個資料工程任務）。
"""
from __future__ import annotations

from . import metrics
from .connectors import twse

FOREIGN_KW = ("美國", "全球", "美股", "日本", "ARK", "海外", "中國", "印度", "歐", "印")
BOND_KW = ("非投", "複合", "債", "收息")

# 同類排名用的可比週期（跨檔成立日不同，故不含 si）
PEER_PERIODS = {"1d": 1, "3d": 3, "1w": 5, "2w": 10, "1m": 20, "3m": 60, "ytd": None}

NOTABLE = {  # 重點競品（行銷對打名單）
    "00981A": "統一", "00403A": "統一", "00992A": "群益", "00980A": "野村",
    "00985A": "野村", "00982A": "群益", "00990A": "元大", "00405A": "富邦",
    "00993A": "安聯", "00995A": "中信",
}


def discover_active(all_today: dict[str, dict]) -> list[tuple[str, str]]:
    """名稱以「主動」開頭者 = 主動式 ETF。"""
    return sorted((c, v["name"]) for c, v in all_today.items() if v["name"].startswith("主動"))


def is_tw_equity(name: str, code: str) -> bool:
    if not code.endswith("A"):           # D 多為債/入息
        return False
    if any(k in name for k in FOREIGN_KW):
        return False
    if any(k in name for k in BOND_KW):
        return False
    return True


def tw_equity_peers(all_today: dict[str, dict]) -> list[tuple[str, str]]:
    return [(c, n) for c, n in discover_active(all_today) if is_tw_equity(n, c)]


def peer_returns(peers: list[tuple[str, str]], start_iso: str, latest: str,
                 year: int) -> dict[str, dict]:
    """{code: {name, ret:{period:val}}}；逐檔抓官方歷史（有快取）。"""
    out: dict[str, dict] = {}
    for code, name in peers:
        series = twse.fetch_history(code, start_iso, latest)
        if len(series) < 2:
            continue
        out[code] = {"name": name, "ret": metrics.multi_period(series, PEER_PERIODS, year)}
    return out


def rank_of(target: str, table: dict[str, dict], period: str) -> tuple[int | None, int]:
    """target 在某週期的名次與該週期有效樣本數。"""
    vals = [(c, d["ret"].get(period)) for c, d in table.items() if d["ret"].get(period) is not None]
    if target not in dict(vals):
        return None, len(vals)
    tv = dict(vals)[target]
    rank = 1 + sum(1 for _, v in vals if v > tv)
    return rank, len(vals)


def beaten(target: str, table: dict[str, dict], period: str) -> list[dict]:
    """某週期被 target 比下去的競品（報酬較低者），重點競品優先。"""
    tv = table.get(target, {}).get("ret", {}).get(period)
    if tv is None:
        return []
    out = []
    for c, d in table.items():
        v = d["ret"].get(period)
        if c != target and v is not None and v < tv:
            out.append({"code": c, "name": d["name"], "ret": v,
                        "gap": tv - v, "issuer": NOTABLE.get(c, "")})
    out.sort(key=lambda x: (x["issuer"] == "", -x["gap"]))  # 重點競品 + 差距大者優先
    return out
