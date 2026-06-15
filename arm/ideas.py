"""多元想法組合引擎 —— 每天不是給「一個冠軍」，而是跨面向給「各種想法」。

涵蓋面向（對應需求清單）：
  績效(多週期) / 籌碼經理人動作 / 題材時事 / 同類排名誰被比下去 /
  成交量突出 / 持股差異化(自體+跨家待接) / 配息時程 / 分點推敲(待接) /
  社群KOL / 同業招數複製 / 逆向誠實 / 內容創意

機制：分類產生 → 加權(使用者偏好) → 主題日加成 → 防重複 → 多樣性挑選 + wildcard。
合規：放手發想，事後 annotate 標注（不擋）。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date

from . import themes
from .connectors import social

# 類別權重（使用者加重：籌碼/題材/內容創意）
CAT_WEIGHT = {
    "績效": 1.0, "籌碼": 1.5, "題材": 1.5, "內容創意": 1.4, "同類排名": 1.1,
    "成交量": 1.0, "持股差異化": 1.0, "配息時程": 1.0, "分點推敲": 0.8,
    "社群KOL": 1.0, "同業招數": 1.0, "逆向誠實": 1.1, "資金流": 1.2,
}
# 主題日：當天該類別額外加成
THEME_OF_DAY = {0: "績效", 1: "籌碼", 2: "題材", 3: "同業招數", 4: "逆向誠實", 5: "內容創意", 6: "社群KOL"}

FORMAT_POOL = {
    "績效": "vs 0050 對比動圖 / 多週期戰報卡",
    "籌碼": "「經理人今天做了什麼」換股快報",
    "題材": "題材連連看資訊圖（持股↔熱門題材）",
    "內容創意": "梗圖 / 15 秒短影音",
    "同類排名": "排行榜長條動畫",
    "成交量": "爆量 K 棒標記圖",
    "持股差異化": "獨門股 vs 大盤對照表",
    "配息時程": "配息倒數限動",
    "分點推敲": "聰明錢進場示意圖",
    "社群KOL": "KOL 開箱 / 業配腳本",
    "同業招數": "對手招數→復華改良版對照卡",
    "逆向誠實": "「空方怎麼打、我們怎麼回」問答卡",
    "資金流": "規模/受益人成長曲線 + 人氣里程碑卡",
}

BANNED = ["保證", "穩賺", "必漲", "完勝", "最強", "包賺", "穩賺不賠", "零風險", "絕對", "鐵定", "翻倍賺"]


@dataclass
class Idea:
    category: str
    headline: str
    evidence: str = ""
    strength: float = 60.0
    status: str = "real"          # real / intel(待情報層補)
    fmt: str = ""
    compliance: list = field(default_factory=list)
    score: float = 0.0

    def __post_init__(self):
        if not self.fmt:
            self.fmt = FORMAT_POOL.get(self.category, "")


# ───────────────────────── 合規事後標注 ─────────────────────────
_NEG = ("非", "不", "無", "未", "免")     # 「非保證/不保證」等揭露語 ≠ 違規


def _violates(text: str, w: str) -> bool:
    """w 是否以「非揭露語」形式出現（排除『非保證』這類合規免責用法）。"""
    i = text.find(w)
    while i != -1:
        if (text[i - 1] if i > 0 else "") not in _NEG:
            return True
        i = text.find(w, i + 1)
    return False


def annotate(text: str) -> list[dict]:
    notes = []
    for w in BANNED:
        if _violates(text, w):
            notes.append({"span": w, "risk": "高", "rule": "絕對化/保證用語",
                          "note": f"『{w}』公會廣告規範禁用", "fix": "改相對/中性描述"})
    if any(k in text for k in ["報酬", "Alpha", "漲", "贏", "%", "翻倍", "領先"]) and "過去績效" not in text:
        notes.append({"span": "(績效陳述)", "risk": "中", "rule": "未附免責",
                      "note": "績效訴求需附『過去績效不代表未來』", "fix": "句尾補免責"})
    return notes


# ───────────────────────── 各面向想法產生器 ─────────────────────────
PERIOD_ZH = {"1d": "近1日", "3d": "近3日", "1w": "近1週", "2w": "近2週",
             "1m": "近1月", "3m": "近3月", "ytd": "年初以來", "si": "成立以來"}


def g_performance(ctx, intel):
    out = []
    alpha = {k: v for k, v in (ctx.get("alpha") or {}).items() if v is not None}
    pos = {k: v for k, v in alpha.items() if v > 0}
    if pos:
        k = max(pos, key=pos.get)
        out.append(Idea("績效", f"{PERIOD_ZH[k]}超額報酬 +{pos[k]:.1%}，主動贏 {ctx['benchmark']}",
                        f"本檔 {ctx['ret'][k]:+.1%} / 基準 {ctx['ret'][k]-pos[k]:+.1%}", 50 + pos[k] * 400))
    si = ctx["ret"].get("si")
    if si and si > 0.5:
        out.append(Idea("績效", f"成立以來淨值含息大漲 {si:.0%}，身價翻倍故事",
                        f"成立來 NAV 總報酬 {si:+.0%}", 70))
    elif si is not None:                     # 入息型：穩健正報酬也是賣點
        label = "穩中求進" if 0 <= si < 0.2 else ("逆勢守住" if si < 0 else "穩健成長")
        out.append(Idea("績效", f"成立以來 NAV 含息總報酬 {si:+.1%}（{label}）",
                        f"以淨值含息計、非市價；資料日 {ctx['trade_date']}", 52 + max(0, si) * 200))
    return out


def g_flow(ctx, intel):
    out = []
    chg = ctx.get("aum_chg_1w")
    now = (ctx.get("aum") or 0) / 1e8
    if chg is not None and chg > 0.02:
        out.append(Idea("資金流", f"近一週規模成長 {chg:+.1%}，資金用腳投票",
                        f"現規模約 {now:,.0f} 億元", 55 + chg * 250))
    hch = ctx.get("holders_chg")
    if hch and hch > 0:
        h_now = ctx.get("holders")
        out.append(Idea("資金流", f"受益人一週淨增 {hch:+,} 人，X 萬人選擇復華的社會認同",
                        f"現受益人約 {h_now:,} 人", 58))
    cross = ctx.get("aum_milestone")
    if cross:
        out.append(Idea("資金流", f"規模突破 {cross} 億元關卡，可比照同業『破紀錄』新聞操作",
                        f"現規模約 {now:,.0f} 億元", 66))
    return out


def g_chips(ctx, intel):
    out = []
    diff = ctx["diff"]
    new, add, cut = diff["new"], diff["add"], diff["cut"]
    unit, div = ctx.get("qty_unit", "張"), ctx.get("qty_div", 1000)
    if new:
        t = new[0]
        out.append(Idea("籌碼", f"經理人新建倉 {t['stock_name']} {t['delta_shares']/div:+,.0f}{unit}，押注新動能",
                        f"權重 {t['weight']:.2f}%", 75))
    if cut and (add or new):
        a = (new + add)[0]; c = cut[0]
        out.append(Idea("籌碼", f"汰弱留強：加碼 {a['stock_name']}、減碼 {c['stock_name']}，主動換馬",
                        f"{a['delta_shares']/div:+,.0f}{unit} / {c['delta_shares']/div:+,.0f}{unit}", 72))
    return out


def g_theme(ctx, intel):
    # M5：題材綁定當日「真實盤面熱度」（個股↔題材↔時事），由 STOCK_DAY_ALL 動態算出
    tw = ctx.get("theme_tailwinds")
    if tw:
        out = []
        for t in tw[:2]:
            ups = [h for h in t["holdings"] if (h["pct"] or 0) > 0]
            lead = max(t["holdings"], key=lambda x: (x["pct"] or 0))
            out.append(Idea("題材",
                f"搭【{t['theme']}】當日熱題：本檔押 {t['fund_weight']:.1f}%，"
                f"{len(ups)}/{len(t['holdings'])} 檔成分股翻紅"
                f"（{lead['name']} {(lead['pct'] or 0):+.1%} 領軍）",
                f"市場同題材 {t['market_n_strong']}/{t['market_n_total']} 檔強漲、"
                f"平均 {t['market_avg_pct']:+.1%}；題材熱度 {t['market_heat']:.0f}", 62 + t["score"]))
        return out
    # 後援（無盤面題材資料，如全球型無 TWSE 市價）：沿用重倉股↔題材對照表
    t2 = themes.id_to_theme(intel.get("theme_map", {}))
    out = []
    pos = [c for c in (ctx.get("top_contrib") or []) if (c["change_pct"] or 0) > 0]
    for c in sorted(pos, key=lambda x: x["contrib"], reverse=True)[:2]:
        theme = t2.get(str(c["stock_id"]))
        if theme:
            out.append(Idea("題材", f"搭【{theme}】題材：重倉 {c['name']} 今日 {c['change_pct']:+.1%}",
                            f"權重 {c['weight']:.1f}%，貢獻淨值 {c['contrib']:+.2f}pt", 65 + c["contrib"] * 20))
    return out


def g_peer(ctx, intel):
    out = []
    ranks = ctx.get("peer_ranks") or {}
    best = min(((k, r, n) for k, (r, n) in ranks.items() if r), key=lambda x: x[1], default=None)
    if best and best[1] <= 5:
        k, r, n = best
        out.append(Idea("同類排名", f"{PERIOD_ZH[k]}同類排名第 {r}/{n}，台股主動ETF前段班",
                        f"全市場 {n} 檔比較", 90 - (r - 1) * 12))
    beaten = ctx.get("peer_beaten") or {}
    for period in ("ytd", "3m", "1w"):
        named = [b for b in beaten.get(period, []) if b["issuer"]][:3]
        if len(named) >= 2:
            txt = "、".join(f"{b['issuer']}{b['code']}" for b in named)
            out.append(Idea("同類排名", f"{PERIOD_ZH[period]}指名把 {txt} 比下去",
                            f"領先幅度最大 {named[0]['gap']:+.1%}", 70))
            break
    return out


def g_volume(ctx, intel):
    series = ctx["price_series"]
    vols = [v for _, _, v in series[-21:-1]]
    if len(vols) >= 10 and ctx["volume"]:
        ma = sum(vols) / len(vols)
        if ma > 0 and ctx["volume"] / ma >= 1.3:
            return [Idea("成交量", f"成交爆量 {ctx['volume']/ma:.1f} 倍均量，人氣題材",
                         f"今量 {ctx['volume']:,} / 均量 {int(ma):,}", 60 + (ctx['volume']/ma - 1) * 40)]
    return []


def g_diff(ctx, intel):
    h = sorted(ctx.get("record_holdings") or ctx.get("holdings") or [],
               key=lambda x: x["weight"] or 0, reverse=True)
    ref = "vs 0050 分散" if ctx.get("asset_class") == "tw_equity" else "全球標的中集中精選"
    out = []
    if len(h) >= 10:
        top10 = sum(x["weight"] or 0 for x in h[:10])
        out.append(Idea("持股差異化", f"前十大集中 {top10:.0f}%，重兵精選 {ref}",
                        f"前3大：{('、'.join(x['stock_name'] for x in h[:3]))}", 55 + (top10 - 40)))

    dx = ctx.get("diff_x") or {}
    a = dx.get("active_share")
    if a is not None:                        # M2 真實主動度（vs 0050）
        out.append(Idea("持股差異化",
            f"主動度 {a:.0f}%（vs {dx['benchmark_label']}）——不是換包裝的指數，是真的在選股",
            f"Active Share=0.5×Σ|w_復華−w_{dx['benchmark_label']}|；基準 as-of "
            f"{dx.get('benchmark_asof') or 'n/a'}（近似公開權重）", 60 + a * 0.3))
    uq = dx.get("unique") or []
    if uq:                                   # 跨家獨門（取到競品才有）
        names = "、".join(u["name"] for u in uq[:3])
        out.append(Idea("持股差異化", f"獨門卡位：{names} 等 {len(uq)} 檔，同業多數沒押",
                        f"對照 {dx['n_peers']} 檔同業主動ETF；最高獨門度 {uq[0]['uniqueness']:.0%}", 72))
    big = [d for d in (dx.get("divergent") or []) if d["diff"] > 3]
    if big:
        d = big[0]
        out.append(Idea("持股差異化", f"重押 {d['name']} {d['w_fund']:.1f}%，同業平均僅 {d['w_peer_mean']:.1f}%",
                        f"權重偏離 +{d['diff']:.1f}pt（z={d.get('z')}）", 66))
    ov = dx.get("overlaps") or []
    if ov:
        lo = ov[0]
        out.append(Idea("持股差異化", f"與 {lo['peer']} 重疊僅 {lo['jaccard']:.0%}，互補配置不撞單",
                        f"權重重疊 {lo['weight_overlap']:.0f}%、共同持股 {lo['n_common']} 檔", 60))

    if not uq:                               # 仍缺競品 → 誠實標 intel（但介面已就緒）
        out.append(Idea("持股差異化", "跨家獨門股/重疊熱圖：競品逐日持股待接（drop-in 或逐家 adapter）",
                        "Holding 統一介面 + 差異化引擎已就緒，落入 config/competitor_holdings/ 即生效",
                        48, status="intel"))
    return out


def g_dividend(ctx, intel):
    sch = intel.get("dividend_schedule", {}).get(ctx["etf_id"])
    if not sch:
        return []
    out = []
    hl = sch.get("highlight")
    if hl:                                   # 入息型主打：把配息亮點當賣點（合規事後標注）
        out.append(Idea("配息時程", f"入息亮點：{hl}", sch.get("note", ""), 66))
    if not sch.get("eval_months"):
        return out
    today = date.fromisoformat(ctx["trade_date"])
    # 找最近的評價日
    cands = []
    for m in sch["eval_months"]:
        for y in (today.year, today.year + 1):
            try:
                d = date(y, m, sch["eval_day"])
                if d >= today:
                    cands.append(d)
            except ValueError:
                pass
    if not cands:
        return []
    if cands:
        nd = min(cands); days = (nd - today).days
        if days <= 45:
            out.append(Idea("配息時程", f"距配息評價日剩 {days} 天（{nd}），最後布局期倒數",
                            sch["note"], 60 + (45 - days)))
    return out


def g_chip_branch(ctx, intel):
    # M3：分點推敲由樁改真實（drop-in 落檔即生效）；買家身份一律標『推估・非確認』
    chips = ctx.get("chips") or {}
    out = []
    if chips.get("data_status") not in (None, "none"):
        fund = chips.get("fund")
        if fund:
            b = fund["top_buyer"]
            streak = f"連 {b['days']} 日" if b["days"] >= 2 else "單日"
            out.append(Idea("分點推敲",
                f"本檔出現關鍵分點{streak}大買 {b['net']:+,} 張，聰明錢進場（推估為{b['identity']['label']}・非確認）",
                f"分點僅到分公司、身份推估；as-of {fund.get('as_of') or 'n/a'}", 58 + b["days"] * 4))
        for h in (chips.get("holdings") or [])[:1]:
            b = h["top_buyer"]
            streak = f"連 {b['days']} 日" if b["days"] >= 2 else "單日"
            out.append(Idea("分點推敲",
                f"重倉 {h['target_name']} 關鍵分點{streak}買超 {b['net']:+,} 張，籌碼面佐證（推估為{b['identity']['label']}・非確認）",
                f"命中飆股的籌碼面；身份推估、as-of {h.get('as_of') or 'n/a'}", 56 + b["days"] * 4))
    # 法人籌碼替代源（etfinfo 主動ETF/投信估算新進，非個別券商分點）
    for t in (chips.get("institutional") or [])[:2]:
        out.append(Idea("分點推敲",
            f"聰明錢共識：重倉 {t['name']} 同步被法人追買（{t['reason']}），估算新進+加碼約 {t['est_yi']:.1f} 億",
            f"主動ETF/投信層級籌碼（非個別分點）；本檔權重 {t['weight']:.1f}%；"
            f"etfinfo as-of {chips.get('active_asof') or 'n/a'}・Tier B 待核對", 56 + t["est_yi"] * 2))
    if not out:                              # 仍缺分點/法人籌碼來源 → 誠實標 intel（介面已就緒）
        out.append(Idea("分點推敲", "關鍵分點大買→推估買家（外資/中實戶/特定金主）",
                        "分點推敲引擎 + 別名對照表已就緒，落入 config/broker_flows/ 即生效（標『推估』）",
                        50, status="intel"))
    return out


def g_kol(ctx, intel):
    # M4：社群/KOL 由樁改真實（drop-in 落檔即生效）；聲量/情緒/業配為推估、Tier B
    etf = ctx.get("etf_id")
    mentions = social.recent_mentions(as_of=ctx.get("trade_date"), window_days=7)
    rel = [m for m in mentions if (not m.etfs) or (etf in m.etfs)]
    if rel:
        out = []
        analyzed = [(m, social.analyze(m)) for m in rel]
        top_m, top_a = max(analyzed, key=lambda x: x[0].reach)
        sp = "、".join(top_a["selling_points"][:3]) if top_a["selling_points"] else "未對齊標準賣點"
        ad = "・疑似業配" if top_a["suspected_ad"] else ""
        out.append(Idea("社群KOL",
            f"社群熱議賣點：{top_m.author}（{top_m.platform}）主打「{sp}」，聲量約 {top_m.reach:,}{ad}",
            f"當週 {len(rel)} 則提及、情緒偏{top_a['sentiment']}；可直接當素材庫。Tier B（聲量/業配推估、待核實）", 60))
        ads = sorted({m.author for m, a in analyzed if a["suspected_ad"]})
        if ads:
            out.append(Idea("社群KOL",
                f"疑似業配 {len(ads)} 位 KOL → 反推同業投放佈局，可借力打力或補位空缺",
                f"含 {('、'.join(ads))[:40]}…；僅內部素材、標『疑似・推估』，不對外指控", 58))
        neg = [m for m, a in analyzed if a["sentiment"] == "負面"]
        if neg:
            out.append(Idea("社群KOL",
                f"社群有 {len(neg)} 則負評（費用率/集中/估值）→ 先備反擊話術、轉成誠實溝通",
                "把質疑當FAQ，反向建立信任（對齊逆向誠實面向）", 54))
        return out
    # 後援：仍無社群 drop-in → 誠實標 intel（介面已就緒）
    seed = intel.get("social_seed", [])
    msg = seed[0] if seed else "地毯搜尋 KOL/社群當日揭露的賣點與聲量"
    return [Idea("社群KOL", f"社群情報：{msg}",
                 "社群情報引擎已就緒，落入 config/social_mentions/{date}.json 即生效"
                 "（YouTube/PTT/Dcard/RSS adapter 待授權後接）", 58, status="intel")]


def g_competitor(ctx, intel):
    tactics = intel.get("competitor_tactics", [])
    if not tactics:
        return []
    t = tactics[date.fromisoformat(ctx["trade_date"]).toordinal() % len(tactics)]  # 每日輪換
    return [Idea("同業招數", f"複製{t['competitor']}招：{t['tactic']}",
                 f"復華改法：{t['reuse']}", 62)]


def g_contrarian(ctx, intel):
    out = []
    worst = min(((k, v) for k, v in ctx["ret"].items() if v is not None and k in ("3d", "1w", "1d")),
                key=lambda x: x[1], default=None)
    if worst and worst[1] < 0:
        out.append(Idea("逆向誠實", f"誠實面對：{PERIOD_ZH[worst[0]]} 拉回 {worst[1]:.1%}，逢回正是定期定額時機",
                        "不遮短線弱勢，轉成進場理由", 60))
    out.append(Idea("逆向誠實", "空方視角：費用率偏高/科技股集中/半年配 → 預備反擊話術",
                    "先想好對手怎麼打我們", 55))
    return out


GENERATORS = [g_performance, g_chips, g_theme, g_peer, g_volume, g_diff,
              g_dividend, g_flow, g_chip_branch, g_kol, g_competitor, g_contrarian]


# ───────────────────────── 組合與挑選 ─────────────────────────
def build_portfolio(ctx, intel, recent_headlines=None, n=9, seed=None) -> list[Idea]:
    recent = set(recent_headlines or [])
    rng = random.Random(seed if seed is not None else ctx["trade_date"])
    theme_cat = THEME_OF_DAY[date.fromisoformat(ctx["trade_date"]).weekday()]

    pool: list[Idea] = []
    for g in GENERATORS:
        try:
            pool += g(ctx, intel)
        except Exception:
            continue
    for idea in pool:
        w = CAT_WEIGHT.get(idea.category, 1.0)
        if idea.category == theme_cat:
            w *= 1.3
        if idea.headline in recent:
            w *= 0.4                       # 防重複
        idea.compliance = annotate(idea.headline + " " + idea.evidence)
        idea.score = round(min(100, idea.strength) * w, 1)
    pool.sort(key=lambda x: x.score, reverse=True)

    # 多樣性挑選：每類先取 1，湊不滿再放寬
    picked, seen = [], {}
    for idea in pool:
        if len(picked) >= n:
            break
        if seen.get(idea.category, 0) < 1:
            picked.append(idea); seen[idea.category] = 1
    for idea in pool:
        if len(picked) >= n:
            break
        if idea not in picked and seen.get(idea.category, 0) < 2:
            picked.append(idea); seen[idea.category] = seen.get(idea.category, 0) + 1
    # wildcard：剩餘隨機塞 1 個冷門角度
    rest = [i for i in pool if i not in picked]
    if rest:
        picked.append(rng.choice(rest))
    return picked


def render_markdown(picked, ctx) -> str:
    prem = ctx.get("premium")
    px = ctx.get("close")
    bar = f"NAV {ctx.get('nav')}" if px is None else f"收盤 {px}　折溢價 {prem:+.2%}" if prem is not None else f"收盤 {px}"
    star = "　★今日輪播主角" if ctx.get("is_star_of_day") else ""
    L = [f"# 每日想法組合 — {ctx['name']}（{ctx['etf_id']}）  資料日 {ctx['trade_date']}{star}",
         f"> 主題日加重：{THEME_OF_DAY[date.fromisoformat(ctx['trade_date']).weekday()]}　|　"
         f"{bar}　AUM {ctx['aum']/1e8:.0f}億　績效基準：NAV 含息總報酬\n"]
    for i, idea in enumerate(picked, 1):
        tag = "🟢" if not idea.compliance else ("🔴" if any(c["risk"] == "高" for c in idea.compliance) else "🟡")
        stat = "" if idea.status == "real" else " 〔情報層待補〕"
        L.append(f"### {i}. [{idea.category}]{stat} {tag}\n"
                 f"- **想法**：{idea.headline}\n"
                 f"- 佐證：{idea.evidence or '—'}\n"
                 f"- 內容形式：{idea.fmt}")
        if idea.compliance:
            for c in idea.compliance:
                L.append(f"  - ⚠️合規[{c['risk']}] `{c['span']}`：{c['note']} → 建議{c['fix']}")
        L.append("")
    L.append("---\n*想法引擎自動產出；合規為事後標注、不擋發想。情報層(獨門/分點/KOL/同業)由 Claude 每日補實。*")
    return "\n".join(L)
