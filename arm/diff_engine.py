"""跨家持股差異化引擎（§18.1, M2-4）—— 量化「復華選股跟別家差在哪」。

純計算、與資料源無關：吃統一的 `Holding` 列表（issuers 提供），產出
  - active_share  主動度（vs 基準 0050）
  - unique        獨門持股（同業多數沒持有）
  - divergent     權重偏離（復華權重 − 同業平均，含 z-score）
  - leads         領先卡位（復華權重居持有該股的同業之冠）
  - overlaps      與各競品的重疊（Jaccard + 權重重疊）
  - bets          獨門股事後表現（需 price_lookup）
  - style_tags    選股風格一句話

設計原則同專案：能算的就算、缺料就誠實降級（data_status 標明缺什麼）。
權重一律對 equity 正規化到合計 100% 再比，排除現金/期貨造成的合計偏差。
"""
from __future__ import annotations

from .connectors.issuers.base import Holding

Peers = list[tuple[str, list[Holding]]]


def _weights(holdings: list[Holding], normalize: bool = True) -> dict[str, float]:
    """{stock_id: weight%}，只取 equity；normalize→合計 100%。"""
    w: dict[str, float] = {}
    for h in holdings:
        if h.kind != "equity":
            continue
        w[h.stock_id] = w.get(h.stock_id, 0.0) + (h.weight or 0.0)
    if normalize:
        tot = sum(w.values())
        if tot > 0:
            w = {k: v / tot * 100 for k, v in w.items()}
    return w


def _names(holdings: list[Holding]) -> dict[str, str]:
    return {h.stock_id: h.stock_name for h in holdings}


def active_share(fund: list[Holding], bench: list[Holding]) -> float | None:
    """0.5 × Σ|w_fund,i − w_bench,i|（%）。需雙方皆有 equity。"""
    wf, wb = _weights(fund), _weights(bench)
    if not wf or not wb:
        return None
    ids = set(wf) | set(wb)
    return round(0.5 * sum(abs(wf.get(i, 0.0) - wb.get(i, 0.0)) for i in ids), 1)


def unique_holdings(fund: list[Holding], peers: Peers,
                    max_peer_ratio: float = 0.34, top: int | None = None) -> list[dict]:
    """復華持有、但 ≤ max_peer_ratio 比例的同業才持有 → 獨門。"""
    wf = _weights(fund, normalize=False)
    names = _names(fund)
    peer_ids = [set(_weights(ph, normalize=False)) for _, ph in peers]
    n = len(peers)
    out = []
    for sid, w in wf.items():
        held = sum(1 for pid in peer_ids if sid in pid)
        ratio = held / n if n else 0.0
        if ratio <= max_peer_ratio:
            out.append({"stock_id": sid, "name": names.get(sid, sid), "weight": round(w, 2),
                        "peers_holding": held, "n_peers": n,
                        "uniqueness": round(1 - ratio, 2)})
    out.sort(key=lambda x: (-x["uniqueness"], -x["weight"]))
    return out[:top] if top else out


def divergence(fund: list[Holding], peers: Peers) -> list[dict]:
    """每檔復華持股的 (權重 − 同業平均權重)；未持有的同業以 0 計，再算 z-score。"""
    wf = _weights(fund, normalize=False)
    names = _names(fund)
    peer_w = [_weights(ph, normalize=False) for _, ph in peers]
    rows = []
    for sid, w in wf.items():
        present = [pw.get(sid, 0.0) for pw in peer_w]
        mean = sum(present) / len(present) if present else 0.0
        rows.append({"stock_id": sid, "name": names.get(sid, sid),
                     "w_fund": round(w, 2), "w_peer_mean": round(mean, 2),
                     "diff": round(w - mean, 2)})
    diffs = [r["diff"] for r in rows]
    if diffs:
        mu = sum(diffs) / len(diffs)
        sd = (sum((d - mu) ** 2 for d in diffs) / len(diffs)) ** 0.5
        for r in rows:
            r["z"] = round((r["diff"] - mu) / sd, 2) if sd else 0.0
    rows.sort(key=lambda x: -x["diff"])
    return rows


def lead_positions(fund: list[Holding], peers: Peers, min_weight: float = 3.0) -> list[dict]:
    """復華權重 > 所有持有該股的同業 → 在該股「居同業之冠」（領先卡位）。"""
    wf = _weights(fund, normalize=False)
    names = _names(fund)
    peer_w = [_weights(ph, normalize=False) for _, ph in peers]
    out = []
    for sid, w in wf.items():
        held = [pw[sid] for pw in peer_w if sid in pw]
        if held and w >= min_weight and w > max(held):
            out.append({"stock_id": sid, "name": names.get(sid, sid), "weight": round(w, 2),
                        "peer_max": round(max(held), 2), "n_peers_hold": len(held)})
    out.sort(key=lambda x: -x["weight"])
    return out


def overlap_with(fund: list[Holding], peer: list[Holding]) -> dict | None:
    """單一競品的重疊：Jaccard(成分) + 權重重疊 Σmin(w_f,w_p)（%）。"""
    wf, wp = _weights(fund), _weights(peer)
    sf, sp = set(wf), set(wp)
    if not sf or not sp:
        return None
    inter, union = sf & sp, sf | sp
    return {"jaccard": round(len(inter) / len(union), 3),
            "weight_overlap": round(sum(min(wf[i], wp[i]) for i in inter), 1),
            "n_common": len(inter), "n_union": len(union)}


def overlaps(fund: list[Holding], peers: Peers) -> list[dict]:
    out = []
    for label, ph in peers:
        o = overlap_with(fund, ph)
        if o:
            out.append({"peer": label, **o})
    out.sort(key=lambda x: x["jaccard"])   # 重疊最低（最互補）在前
    return out


def bet_performance(stocks: list[dict], price_lookup: dict[str, float | None]) -> list[dict]:
    """獨門/偏離股的事後表現；price_lookup: stock_id → 漲跌幅(小數，如 0.03)。"""
    out = []
    for s in stocks:
        pct = (price_lookup or {}).get(s["stock_id"])
        if pct is None:
            continue
        out.append({**s, "today_pct": round(pct, 4)})
    out.sort(key=lambda x: -x["today_pct"])
    return out


def style_tags(fund: list[Holding], active: float | None = None) -> list[str]:
    vals = sorted(_weights(fund, normalize=False).values(), reverse=True)
    tags: list[str] = []
    if len(vals) >= 10:
        top10 = sum(vals[:10])
        band = "高度集中" if top10 >= 60 else "適度集中" if top10 >= 45 else "分散"
        tags.append(f"前十大集中 {top10:.0f}%（{band}）")
    if vals:
        tags.append(f"持股 {len(vals)} 檔")
    if active is not None:
        band = "極高" if active >= 80 else "高" if active >= 60 else "中" if active >= 40 else "偏低"
        tags.append(f"主動度{band}（{active:.0f}%）")
    return tags


def compute(fund: list[Holding], *, benchmark: list[Holding] | None = None,
            benchmark_label: str = "0050", benchmark_asof: str | None = None,
            peers: Peers | None = None,
            price_lookup: dict[str, float | None] | None = None) -> dict:
    """差異化總入口。缺料即降級：benchmark→主動度；peers→獨門/偏離/重疊/領先。"""
    peers = peers or []
    res: dict = {
        "benchmark_label": benchmark_label, "benchmark_asof": benchmark_asof,
        "active_share": active_share(fund, benchmark) if benchmark else None,
        "n_peers": len(peers), "peers_used": [l for l, _ in peers],
        "unique": [], "divergent": [], "leads": [], "overlaps": [], "bets": [],
    }
    if peers:
        res["unique"] = unique_holdings(fund, peers)
        res["divergent"] = divergence(fund, peers)
        res["leads"] = lead_positions(fund, peers)
        res["overlaps"] = overlaps(fund, peers)
        if price_lookup:
            res["bets"] = bet_performance(res["unique"][:8], price_lookup)
    res["style_tags"] = style_tags(fund, res["active_share"])
    res["data_status"] = ("full" if (peers and benchmark) else
                          "peers_only" if peers else
                          "benchmark_only" if benchmark else "none")
    return res
