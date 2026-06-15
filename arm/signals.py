"""賣點偵測器庫 + 評分（MVP：6 個跑得動的偵測器，皆吃權威資料）。

score = 0.40*strength + 0.25*novelty + 0.20*theme_fit + 0.15*audience_fit
MVP 先把 novelty/theme_fit/audience_fit 用合理預設，待 P1 接歷史與題材表再精算。
"""
from __future__ import annotations

from dataclasses import dataclass

PERIOD_ZH = {"1d": "近1日", "3d": "近3日", "1w": "近1週", "2w": "近2週",
             "1m": "近1月", "3m": "近3月", "ytd": "年初以來", "si": "成立以來"}


@dataclass
class Signal:
    detector: str
    strength: float
    headline: str
    evidence: dict
    novelty: float = 100.0
    theme_fit: float = 65.0
    audience_fit: float = 60.0

    @property
    def score(self) -> float:
        return round(0.40 * self.strength + 0.25 * self.novelty
                     + 0.20 * self.theme_fit + 0.15 * self.audience_fit, 1)


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def d_alpha_beat(ctx: dict) -> Signal | None:
    alpha = {k: v for k, v in ctx["alpha"].items() if v is not None}
    pos = {k: v for k, v in alpha.items() if v > 0}
    if not pos:
        return None
    best = max(pos, key=pos.get)
    a = pos[best]
    return Signal("ALPHA_BEAT", _clamp(a * 500),
                  f"{PERIOD_ZH.get(best, best)}超額報酬 +{a:.2%}，跑贏 {ctx['benchmark']}",
                  {"period": best, "alpha": round(a, 4),
                   "etf_ret": round(ctx['ret'][best], 4),
                   "bench": ctx['benchmark']})


def d_multi_win(ctx: dict) -> Signal | None:
    wins = [k for k, v in ctx["alpha"].items() if v is not None and v > 0]
    if len(wins) < 2:
        return None
    return Signal("BEAT_PEERS_MULTI", _clamp(len(wins) * 18),
                  f"在 {len(wins)} 個觀察週期都贏過 {ctx['benchmark']}（{'、'.join(PERIOD_ZH.get(w, w) for w in wins)}）",
                  {"win_periods": wins})


def d_price_high(ctx: dict) -> Signal | None:
    # 用 NAV 序列（含息總報酬骨幹）判定淨值新高，跨資產類別通用
    series = ctx.get("nav_series") or ctx.get("price_series") or []
    vals = [c for _, c, _ in series]
    if len(vals) < 5 or series[-1][1] < max(vals):
        return None
    span = len(vals)
    return Signal("NAV_HIGH", _clamp(40 + span / 3),
                  f"淨值(NAV)創成立以來新高（{series[-1][1]}）",
                  {"nav": series[-1][1], "since": series[0][0]})


def d_fund_inflow(ctx: dict) -> Signal | None:
    chg = ctx.get("aum_chg_1w")
    if chg is None or chg <= 0.02:          # 規模週增 >2% 才算明顯淨流入
        return None
    now = (ctx.get("aum") or 0) / 1e8
    return Signal("FUND_INFLOW", _clamp(chg * 300),
                  f"近一週規模成長 {chg:+.1%}（現約 {now:,.0f} 億），資金持續流入",
                  {"aum_chg_1w": round(chg, 4), "aum_now": ctx.get("aum")})


_AUM_MILESTONES = [10, 20, 30, 50, 80, 100, 150, 200, 300, 500]  # 億元關卡


def d_milestone(ctx: dict) -> Signal | None:
    now, prev = ctx.get("aum"), ctx.get("aum_prev")
    if not now or not prev:
        return None
    now_y, prev_y = now / 1e8, prev / 1e8
    crossed = [t for t in _AUM_MILESTONES if prev_y < t <= now_y]
    if not crossed:
        return None
    t = max(crossed)
    return Signal("MILESTONE", _clamp(50 + t / 10),
                  f"規模一週內突破 {t} 億元關卡（現約 {now_y:,.0f} 億）",
                  {"threshold_yi": t, "aum_now": now})


def d_volume_spike(ctx: dict) -> Signal | None:
    series = ctx.get("price_series") or []
    vols = [v for _, _, v in series[-21:-1]]
    if len(vols) < 10 or not ctx.get("volume"):
        return None
    ma20 = sum(vols) / len(vols)
    if ma20 <= 0:
        return None
    ratio = ctx["volume"] / ma20
    if ratio < 1.5:
        return None
    return Signal("VOLUME_SPIKE", _clamp((ratio - 1) * 60),
                  f"成交爆量達 20 日均量 {ratio:.1f} 倍，人氣噴發",
                  {"volume": ctx["volume"], "ma20": int(ma20), "ratio": round(ratio, 2)})


def d_manager_add(ctx: dict) -> Signal | None:
    add = ctx["diff"]["add"]
    new = ctx["diff"]["new"]
    cand = (new or []) + (add or [])
    if not cand:
        return None
    top = max(cand, key=lambda x: abs(x["delta_shares"]))
    unit, div = ctx.get("qty_unit", "張"), ctx.get("qty_div", 1000)
    lots = top["delta_shares"] / div
    kind = "新建倉" if top in new else "加碼"
    return Signal("MANAGER_ADD", _clamp(40 + (top["weight"] or 0) * 3),
                  f"經理人{kind} {top['stock_name']}（{top['stock_id']}）{lots:+,.0f} {unit}，現權重 {top['weight']:.2f}%",
                  {"stock": top["stock_id"], "name": top["stock_name"],
                   "delta_qty": round(lots), "unit": unit, "weight": top["weight"], "kind": kind})


def d_hit_hot_stock(ctx: dict) -> Signal | None:
    contrib = ctx.get("top_contrib") or []
    pos = [c for c in contrib if c["change_pct"] is not None and c["change_pct"] > 0]
    if not pos:
        return None
    top = max(pos, key=lambda x: x["contrib"])
    return Signal("HIT_HOT_STOCK", _clamp(top["contrib"] * 40),
                  f"重倉 {top['name']}（{top['stock_id']}，權重 {top['weight']:.1f}%）今日漲 {top['change_pct']:.2%}，直接拉抬淨值",
                  {"stock": top["stock_id"], "name": top["name"],
                   "weight": top["weight"], "chg": round(top["change_pct"], 4),
                   "contrib_pct": round(top["contrib"], 3)})


def d_theme_tailwind(ctx: dict) -> Signal | None:
    # M5(§8 #13)：重倉產業=當日強勢題材；題材熱度由 STOCK_DAY_ALL 全市場漲幅動態算出
    tw = ctx.get("theme_tailwinds") or []
    if not tw:
        return None
    t = tw[0]
    up = sum(1 for h in t["holdings"] if (h["pct"] or 0) > 0)
    n = len(t["holdings"])
    sig = Signal("THEME_TAILWIND",
                 _clamp(t["market_heat"] * 0.5 + t["fund_weight"]),
                 f"重倉【{t['theme']}】題材今日順風：本檔 {n} 檔成分股 {up} 檔翻紅、"
                 f"合計權重 {t['fund_weight']:.1f}%（市場同題材 {t['market_n_strong']}/"
                 f"{t['market_n_total']} 檔強漲、平均 {t['market_avg_pct']:+.1%}）",
                 {"theme": t["theme"], "fund_weight": t["fund_weight"],
                  "market_heat": t["market_heat"],
                  "holdings": [h["stock_id"] for h in t["holdings"][:5]]})
    sig.theme_fit = _clamp(t["market_heat"])      # 真實題材熱度取代靜態預設
    return sig


def d_peer_champion(ctx: dict) -> Signal | None:
    ranks = ctx.get("peer_ranks") or {}
    cand = [(k, r, n) for k, (r, n) in ranks.items() if r is not None and n >= 3]
    if not cand:
        return None
    # 取名次最前者（同名次取週期較長者）
    order = list(PERIOD_ZH)
    best = min(cand, key=lambda x: (x[1], -order.index(x[0]) if x[0] in order else 0))
    period, rank, n = best
    if rank > 5:
        return None
    return Signal("PEER_CHAMPION", _clamp(100 - (rank - 1) * 12),
                  f"{PERIOD_ZH.get(period, period)}報酬在 {n} 檔台股主動ETF排名第 {rank}",
                  {"period": period, "rank": rank, "universe": n})


def d_beat_named(ctx: dict) -> Signal | None:
    beaten = ctx.get("peer_beaten") or {}
    for period in ("3m", "ytd", "1m", "1w"):
        items = [b for b in beaten.get(period, []) if b["issuer"]]
        if len(items) >= 2:
            names = "、".join(f"{b['issuer']}{b['code']}" for b in items[:4])
            return Signal("BEAT_NAMED_PEERS", _clamp(40 + len(items) * 10),
                          f"{PERIOD_ZH.get(period, period)}把 {names} 等同業比下去",
                          {"period": period,
                           "beaten": [{"code": b["code"], "gap": round(b["gap"], 4)} for b in items[:6]]})
    return None


def d_concentration(ctx: dict) -> Signal | None:
    h = sorted(ctx.get("record_holdings") or ctx.get("holdings") or [],
               key=lambda x: x["weight"] or 0, reverse=True)
    if len(h) < 10:
        return None
    top10 = sum(x["weight"] or 0 for x in h[:10])
    if top10 < 55:
        return None
    names = "、".join(x["stock_name"] for x in h[:3])
    return Signal("CONCENTRATED_PICK", _clamp((top10 - 40) * 1.5),
                  f"前十大持股集中 {top10:.0f}%（{names}…），精準卡位不分散火力",
                  {"top10_weight": round(top10, 1)})


# ───────────────────────── 跨家持股差異化（M2, §18.1）─────────────────────────
def d_active_share(ctx: dict) -> Signal | None:
    dx = ctx.get("diff_x") or {}
    a = dx.get("active_share")
    if a is None or a < 35:                  # 主動度太低貼著大盤 → 不主打
        return None
    return Signal("ACTIVE_SHARE", _clamp(a),
                  f"主動度 {a:.0f}%（vs {dx['benchmark_label']}），真的在主動選股、非換包裝的指數",
                  {"active_share": a, "benchmark": dx["benchmark_label"],
                   "benchmark_asof": dx.get("benchmark_asof")})


def d_unique_holding(ctx: dict) -> Signal | None:
    dx = ctx.get("diff_x") or {}
    uq = dx.get("unique") or []
    if not uq:
        return None
    cand = sorted(uq, key=lambda x: -x["weight"])[:3]
    names = "、".join(f"{u['name']}({u['weight']:.1f}%)" for u in cand)
    return Signal("UNIQUE_HOLDING", _clamp(40 + sum(u["weight"] for u in cand) * 2),
                  f"獨門卡位 {names}，{dx['n_peers']} 檔同業主動ETF多數未持有",
                  {"unique": [u["stock_id"] for u in cand], "n_peers": dx["n_peers"]})


def d_divergent_bet(ctx: dict) -> Signal | None:
    dx = ctx.get("diff_x") or {}
    dv = [d for d in (dx.get("divergent") or []) if d["diff"] > 3 and d.get("z", 0) >= 1]
    if not dv:
        return None
    d = dv[0]
    return Signal("DIVERGENT_BET", _clamp(40 + d["diff"] * 3),
                  f"重押 {d['name']} {d['w_fund']:.1f}%，同業平均僅 {d['w_peer_mean']:.1f}%（偏離 +{d['diff']:.1f}pt）",
                  {"stock": d["stock_id"], "diff": d["diff"], "z": d["z"]})


def d_lead_position(ctx: dict) -> Signal | None:
    dx = ctx.get("diff_x") or {}
    leads = dx.get("leads") or []
    if not leads:
        return None
    t = leads[0]
    return Signal("LEAD_POSITION", _clamp(45 + (t["weight"] - t["peer_max"]) * 3),
                  f"{t['name']} 配置居同業之冠（復華 {t['weight']:.1f}% vs 同業最高 {t['peer_max']:.1f}%）",
                  {"stock": t["stock_id"], "w_fund": t["weight"], "peer_max": t["peer_max"]})


# ───────────────────────── 籌碼分點推敲（M3, §18.4）─────────────────────────
def d_smart_money(ctx: dict) -> Signal | None:
    chips = ctx.get("chips") or {}
    # 優先本檔自身券商分點，否則取重倉股最強買盤（缺券商分點即不觸發，誠實降級）
    res = chips.get("fund") or (chips.get("holdings") or [None])[0]
    if not res:
        return None
    b = res["top_buyer"]
    who = b["identity"]["label"]
    streak = f"連 {b['days']} 日" if b["days"] >= 2 else "單日"
    ratio = f"、佔成交 {b['buy_ratio']:.0%}" if b.get("buy_ratio") is not None else ""
    return Signal("SMART_MONEY", _clamp(35 + abs(b["net"]) / 50 + b["days"] * 5),
                  f"{res['target_name']} 出現關鍵分點{streak}大買 {b['net']:+,} 張"
                  f"{ratio}（推估為{who}・非確認）",
                  {"target": res["target_id"], "broker": b["broker_id"],
                   "broker_name": b["broker_name"], "net_lots": b["net"],
                   "consecutive_days": b["days"], "buy_ratio": b.get("buy_ratio"),
                   "inferred": b["identity"]["kind"], "confidence": "推估", "as_of": res.get("as_of")})


def d_institutional_buy(ctx: dict) -> Signal | None:
    # M3 替代源：主動ETF/投信『估算新進+加碼』（etfinfo 法人籌碼，非個別券商分點）
    inst = (ctx.get("chips") or {}).get("institutional") or []
    if not inst:
        return None
    t = inst[0]
    return Signal("INSTITUTIONAL_BUY", _clamp(35 + t["est_yi"] * 2.5 + (t["weight"] or 0) * 1.5),
                  f"重倉 {t['name']} 同步獲法人買盤：{t['reason']}"
                  f"（估算新進+加碼約 {t['est_yi']:.1f} 億，本檔權重 {t['weight']:.1f}%）",
                  {"stock": t["stock_id"], "n_etf": t["n_etf"], "n_sitc": t["n_sitc"],
                   "est_new": t["est_new"], "est_add": t["est_add"], "est_yi": t["est_yi"],
                   "weight": t["weight"], "source": "etfinfo 主動ETF籌碼追蹤（法人層級・Tier B 待核對）"})


def d_foreign_branch(ctx: dict) -> Signal | None:
    # 外資分點合計買超（多家外資分點同步＝聰明錢共識，比單一分點更有說服力）
    chips = ctx.get("chips") or {}
    cands = ([chips["fund"]] if chips.get("fund") else []) + (chips.get("holdings") or [])
    cands = [c for c in cands if c.get("foreign_net", 0) > 0 and c.get("foreign_n", 0) >= 2]
    if not cands:
        return None
    t = max(cands, key=lambda c: c["foreign_net"])
    return Signal("FOREIGN_BRANCH_BUY", _clamp(40 + t["foreign_net"] / 200 + t["foreign_n"] * 4),
                  f"{t['target_name']} 今日 {t['foreign_n']} 家外資分點同步買超、合計 +{t['foreign_net']:,} 張"
                  f"（推估外資・非確認）",
                  {"target": t["target_id"], "foreign_net": t["foreign_net"],
                   "foreign_n": t["foreign_n"], "confidence": "推估"})


DETECTORS = [d_alpha_beat, d_multi_win, d_peer_champion, d_beat_named,
             d_price_high, d_volume_spike, d_manager_add, d_hit_hot_stock,
             d_theme_tailwind, d_concentration, d_fund_inflow, d_milestone,
             d_active_share, d_unique_holding, d_divergent_bet, d_lead_position,
             d_smart_money, d_institutional_buy, d_foreign_branch]


def run_all(ctx: dict) -> list[Signal]:
    sigs = [s for d in DETECTORS if (s := d(ctx)) is not None]
    return sorted(sigs, key=lambda s: s.score, reverse=True)
