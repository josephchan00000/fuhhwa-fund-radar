"""M7 零安裝情報儀表板 v3 —— 第一手數據驅動切點 + 競品比較 + 競品切點掃描 + 本檔話題口碑。

四段（前三段全自動算自 arm.db / TWSE，第四段用 Claude drop-in 補話題口碑）：
  1. 🔎 本檔第一手數據切點：成交量/漲跌/規模/受益人/持股加減碼/signals → 每筆配『建議切點(官方分類)+參考標題+🔗連結』。
  2. 🥊 競品操作比較·我們好在哪：同類量能漲跌排行 + 我們的相對優勢（signals + drop-in）。
  3. 📊 競品切點掃描：各競品今日價量(排名) + 重壓/集中度/獨門題材（持股快照）。
  4. 💬 本檔話題＋口碑：話題型切點 + KOL/社群口碑意圖（drop-in；附查證連結）。

資料源：arm.db（etf_daily/holdings_daily/nav_history/holders_history/signals/peer_quotes）、
config/competitor_holdings、reports/intel/{date}_{etf}.json（Claude 話題口碑 drop-in）。
先跑 scripts/fetch_peers.py 灌競品價量。連結皆真實查證入口。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import firsthand
from .copy import baseline, parse


def _clean_header(h: str) -> str:
    """移除報告標題列裡的舊市況數字（收盤/折溢價/NAV/AUM），改由『價格基準日』大字與績效歸因區呈現，
    避免報告日(舊)市況與同日求鮮(新)市況並列造成矛盾。保留主題與績效基準等敘述。"""
    left = h.split("　|　")[0]
    m = re.search(r"績效基準.*", h)
    return f"{left}　·　{m.group(0)}" if m else left

ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "reports" / "intel"
FAST_DIR = ROOT / "data" / "fast"   # scripts/fetch_fast.py 同日求鮮 drop-in（市況/績效歸因/持股異動）

# signal detector → (切點官方分類, icon)
DET_MAP = {
    "ALPHA_BEAT": ("短期績效出色", "🏆"), "BEAT_PEERS_MULTI": ("短期績效出色", "🏆"),
    "BEAT_NAMED_PEERS": ("對標比較，幫投資人分析", "🥊"), "PEER_CHAMPION": ("對標比較，幫投資人分析", "🥇"),
    "UNIQUE_HOLDING": ("持股亮點／新題材", "💎"), "LEAD_POSITION": ("經理人選股理念", "📌"),
    "THEME_TAILWIND": ("持股亮點／新題材", "🔥"), "MANAGER_ADD": ("經理人選股理念", "🔧"),
    "SMART_MONEY": ("籌碼／分點推敲", "🧠"), "FOREIGN_BRANCH_BUY": ("籌碼／分點推敲", "🌐"),
    "INSTITUTIONAL_BUY": ("籌碼／分點推敲", "🏦"), "AUM_MILESTONE": ("規模增幅高／創掛牌新高", "📈"),
}

# 切點官方分類 → 大分類（group_key, 大分類名, icon）。供儀表板「依分類」折疊與燈號用。
GROUP_MAP = {
    "單日成交量爆量": ("hot", "熱度與績效", "🔥"),
    "短期績效出色": ("hot", "熱度與績效", "🔥"),
    "規模增幅高／創掛牌新高": ("hot", "熱度與績效", "🔥"),
    "受益人數突破門檻": ("hot", "熱度與績效", "🔥"),
    "對標比較，幫投資人分析": ("vs", "競品對比·我們好在哪", "🥊"),
    "持股亮點／新題材": ("hold", "持股與操作亮點", "💎"),
    "經理人選股理念": ("hold", "持股與操作亮點", "💎"),
    "籌碼／分點推敲": ("hold", "持股與操作亮點", "🧠"),
}
GROUP_ORDER = ["hold", "hot", "vs"]   # 持股與操作亮點（策略亮點）置頂、為主打

# signal detector → 重要度（決定「今日必看」排序；越高越先露出）。
# 持股與操作亮點（獨門/領先/經理人換股/籌碼）為主打 → 調高，確保擠進今日必看。
SIG_PRI = {
    "ALPHA_BEAT": 92, "UNIQUE_HOLDING": 91, "BEAT_PEERS_MULTI": 88, "LEAD_POSITION": 87,
    "PEER_CHAMPION": 85, "MANAGER_ADD": 85, "BEAT_NAMED_PEERS": 84, "THEME_TAILWIND": 82,
    "AUM_MILESTONE": 76, "SMART_MONEY": 72, "FOREIGN_BRANCH_BUY": 68, "INSTITUTIONAL_BUY": 68,
}


def _enrich(cuts: list[dict]) -> list[dict]:
    """為每張切點卡補上 大分類 與 priority 預設，供前端分組／排序。"""
    for c in cuts:
        gk, gl, gi = GROUP_MAP.get(c["type"], ("hold", "持股與操作亮點", "✨"))
        c["group"], c["group_label"], c["group_icon"] = gk, gl, gi
        c.setdefault("priority", 50)
        c.setdefault("tldr", c.get("fact", ""))
    return cuts


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# 真實深層連結（直達該檔資料頁，非首頁）
def _yahoo(id): return {"label": f"Yahoo {id}", "url": f"https://tw.stock.yahoo.com/quote/{id}"}
def _etfinfo(id): return {"label": "etfinfo 基金頁", "url": f"https://www.etfinfo.tw/etf/{id}"}
def _moneydj(id): return {"label": "MoneyDJ 基本/績效", "url": f"https://www.moneydj.com/etf/x/basic/basic0004.xdjhtm?etfid={id}.TW"}


def _excess0050(perf: dict | None, period: str) -> float | None:
    """多週期報酬表中某期間『本檔 − 0050』超額(％)；取不到回 None。"""
    for r in (perf or {}).get("rows", []):
        if r.get("period") == period:
            e, b = r.get("etf"), (r.get("vals") or {}).get("0050")
            return round(e - b, 1) if (e is not None and b is not None) else None
    return None


def _perf_superiority(perf: dict | None, etf: str) -> dict | None:
    """從多週期報酬表萃取『超級績效重點』：本檔對 0050／同類主動均的『實際領先幅度』(％)。

    取代舊的 BEAT_PEERS_MULTI 卡（只標贏/輸、不講贏多少、又跟上方圖表重複）。數字直接引自
    perf_periods() 的列，故與圖表完全一致。無 perf 或無任一週期贏 0050 → 回 None。
    """
    rows = (perf or {}).get("rows") or []
    items = []
    for r in rows:
        e = r.get("etf")
        if e is None:
            continue
        b = (r.get("vals") or {}).get("0050")
        items.append({"period": r["period"], "ret": e,
                      "gap0050": (round(e - b, 1) if b is not None else None),
                      "excess": r.get("excess")})
    wins = [it for it in items if it["gap0050"] is not None and it["gap0050"] > 0]
    if not wins:
        return None
    n_cmp = sum(1 for it in items if it["gap0050"] is not None)
    margins = [it["gap0050"] for it in wins]
    lo, hi = min(margins), max(margins)
    sweep = len(wins) == n_cmp
    si = next((it for it in items if it["period"].endswith("成立以來")), None)
    ytd = next((it for it in items if it["period"] == "年初以來"), None)
    flag = next((it for it in (si, ytd) if it and it["gap0050"] is not None), None) \
        or max(wins, key=lambda x: x["gap0050"])
    big = max(wins, key=lambda x: x["gap0050"])

    def line(it):
        s = f"本檔 {it['ret']:+.1f}%"
        if it["gap0050"] is not None:
            s += f"，贏 0050 {it['gap0050']:+.1f}％"
        if it["excess"] is not None:
            s += f"、贏同類主動均 {it['excess']:+.1f}％"
        return s

    bullets = []
    if si:
        bullets.append({"k": si["period"].replace(etf, "").strip() or "成立以來", "v": line(si)})
    if ytd and ytd is not si:
        bullets.append({"k": "年初以來", "v": line(ytd)})
    bullets.append({"k": ("全勝 0050" if sweep else "領先 0050"),
                    "v": f"{len(wins)}/{n_cmp} 個週期贏 0050，領先 +{lo:.1f}～+{hi:.1f}％"})
    if big["period"] != flag["period"]:
        bullets.append({"k": "最大領先",
                        "v": f"{big['period']} 贏 0050 +{big['gap0050']:.1f}％（本檔 {big['ret']:+.1f}%）"})

    tldr = (f"{flag['period']} +{flag['ret']:.1f}%、贏 0050 +{flag['gap0050']:.1f}％；"
            f"{'全' if sweep else ''}{len(wins)} 個週期勝 0050（領先 +{lo:.1f}～+{hi:.1f}％）")
    example = (f"【主動就是強！{etf} 成立以來 +{si['ret']:.0f}%，大贏 0050 約 {si['gap0050']:.0f} 個百分點】"
               if (si and si["gap0050"] is not None)
               else f"【{etf} {flag['period']} 領先 0050 約 {flag['gap0050']:.0f} 個百分點，主動選股實力獲驗證】")
    return {"icon": "🏆", "label": "績效超車 vs 0050", "type": "短期績效出色",
            "priority": 93,
            "tldr": tldr,
            "fact": f"{etf} 多週期市價報酬對 0050／同類主動均的實際領先幅度（含息以月報為準）",
            "bullets": bullets,
            "suggest": "用『實際領先幾個百分點』打績效，比『贏 N 個週期』更有說服力；數字與上方多週期報酬表一致。",
            "example": example,
            "links": [_yahoo(etf), _moneydj(etf)]}


def _data_cuts(f: dict, etf: str, fast: dict | None = None, perf: dict | None = None) -> list[dict]:
    """本檔第一手數據 → 切點建議卡（皆來自 DB 真數字）。fast＝同日求鮮 drop-in；perf＝多週期報酬。"""
    cuts = []
    vol = f.get("volume")
    if vol:
        rank, n = f.get("vol_rank"), f.get("peer_n")
        hot = rank and rank <= 3
        cuts.append({"icon": "📊", "label": "單日成交量", "type": "單日成交量爆量",
            "priority": 95 if hot else 45,
            "tldr": (f"單日爆量·同類量能第 {rank}/{n}" if hot
                     else (f"成交 {vol/1e8:.1f} 億股·量能中段（第 {rank}/{n}）" if rank
                           else f"成交 {vol/1e8:.1f} 億股")),
            "fact": f"今日成交 {vol:,} 股" + (f"，同類主動ETF量能第 {rank}/{n}" if rank else ""),
            "suggest": ("量能同類前段，可直接打『單日成交量爆量／人氣王』切點" if hot
                        else "量能中段；搭配績效/題材切點更有力，或等爆量日再打量能切點"),
            "example": f"【主動ETF人氣盤！{etf} 單日成交 {vol/1e8:.1f} 億股、買氣不墜】" if hot
                       else f"【量能穩定有撐！{etf} 人氣維持（爆量日可改打成交量切點）】",
            "links": [_yahoo(etf), _etfinfo(etf)]})
    cp = f.get("change_pct")
    if cp is not None:
        up = cp > 0
        cuts.append({"icon": "📈", "label": "當日漲跌", "type": "短期績效出色",
            "priority": 90 if up else 58,
            "tldr": f"今日 {cp*100:+.2f}%、收 {f.get('close')}",
            "fact": f"今日 {cp*100:+.2f}%，收 {f.get('close')}",
            "suggest": ("短線翻紅可接『多週期戰報』；勿單押一日，搭成立以來/年初以來更耐看" if up
                        else "今日收黑，不建議打漲幅切點；改走『逢回定期定額』或長期績效角度"),
            "example": (f"【{etf} 今日 {cp*100:+.1f}%！主動選股題材續強】" if up
                        else f"【{etf} 今日回檔 {cp*100:.1f}%——逢回正是定期定額時機】"),
            "links": [_yahoo(etf), _moneydj(etf)]})
    aum = f.get("aum")
    if aum:
        chg = f.get("aum_chg_1w")
        grew = chg is None or chg >= 0
        cuts.append({"icon": "💰", "label": "規模變化", "type": "規模增幅高／創掛牌新高",
            "priority": (87 if (chg is not None and chg > 0) else 76) if grew else 38,
            "tldr": (f"規模 {aum/1e8:.0f} 億·近一週 {chg:+.1f}%" if chg is not None
                     else f"規模約 {aum/1e8:.0f} 億"),
            "fact": f"AUM 約 {aum/1e8:.0f} 億元" + (f"、近一週 {chg:+.1f}%" if chg is not None else ""),
            "suggest": ("規模成長可寫『淨流入/里程碑』；半年內衝上此規模是主動ETF亮點" if grew
                        else f"⚠ 規模近一週縮水 {abs(chg):.1f}%，本日不建議打規模切點；改走配息/績效角度"),
            "example": (f"【規模站上 {aum/1e8:.0f} 億！{etf} 資金加速流入（週 {chg:+.1f}%）】" if (grew and chg is not None and chg > 0)
                        else (f"【規模衝 {aum/1e8:.0f} 億！{etf} 人氣里程碑】" if grew else "")),
            "links": [_etfinfo(etf), _moneydj(etf)]})
    hold = f.get("holders")
    if hold:
        cuts.append({"icon": "👥", "label": "受益人數", "type": "受益人數突破門檻",
            "priority": 83,
            "tldr": f"受益人約 {hold/1e4:.1f} 萬人",
            "fact": f"受益人約 {hold:,} 人（{f.get('holders_date','')}）",
            "suggest": f"用『{hold/1e4:.0f} 萬人選擇』打社會認同；對比競品人數更有力",
            "example": f"【逾 {hold/1e4:.0f} 萬人相信主動！{etf} 受益人持續成長】",
            "links": [_etfinfo(etf), _moneydj(etf)]})
    # 經理人加減碼：與上方「最新持股異動」一致，以『張數變化(實際買賣)』為準（非權重，避免把股價漲跌誤判成加碼）。
    hd = (fast or {}).get("holdings_diff") or {}
    _allm = (hd.get("cuts") or []) + (hd.get("adds") or []) + (hd.get("new") or [])
    _has_sh = any(x.get("share_delta") is not None for x in _allm)
    _lot = lambda v: f"{int(round(v / 1000)):+,} 張"
    if _has_sh:                                   # 有官方張數（00991A）→ 用實際買賣
        buys = sorted([x for x in _allm if (x.get("share_delta") or 0) > 0], key=lambda x: -x["share_delta"])
        sells = sorted([x for x in _allm if (x.get("share_delta") or 0) < 0], key=lambda x: x["share_delta"])
        if buys or sells:
            bt = "、".join(f"{x['name']} {_lot(x['share_delta'])}" for x in buys[:4])
            st = "、".join(f"{x['name']} {_lot(x['share_delta'])}" for x in sells[:4])
            lead = (buys or sells)[0]["name"]
            cuts.append({"icon": "🔧", "label": "經理人實際加減碼（張數）", "type": "經理人選股理念",
                "priority": 86,
                "tldr": f"經理人{'加碼' if buys else '減碼'} {lead} 等 {len(buys) + len(sells)} 檔（依張數）",
                "fact": (f"加碼：{bt}" if bt else "") + ("｜" if bt and st else "") + (f"減碼：{st}" if st else "")
                        + f"（{hd.get('prev_date')}→{hd.get('date')}，依實際張數變化）",
                "suggest": "用實際張數寫『經理人今天買賣了什麼』換股快報（張數＝真買賣；權重變化含股價漲跌、不等於買賣）",
                "example": f"【經理人換股快報！{etf} {'加碼' if buys else '減碼'} {lead}（依官方張數）】",
                "links": [_moneydj(etf), _etfinfo(etf)]})
        else:                                     # 有權重變化但張數全未變 → 純股價，不算加減碼
            cuts.append({"icon": "🔧", "label": "經理人加減碼", "type": "經理人選股理念",
                "priority": 38,
                "tldr": f"本日未實際加減碼（{hd.get('prev_date')}→{hd.get('date')}）",
                "fact": "本日成分股張數未變動；權重變化純由個股股價漲跌造成（非加減碼）。",
                "suggest": "今日無換股題材，改打績效/題材切點。", "example": "",
                "links": [_moneydj(etf), _etfinfo(etf)]})
    else:                                         # 無官方張數（00998A/00986D 海外成分）→ 退回權重變化
        d = f.get("delta") or {}
        if d.get("adds"):
            adds = "、".join(f"{n} {w:+.2f}%" for n, w in d["adds"][:5])
            cutss = "、".join(f"{n} {w:+.2f}%" for n, w in (d.get("cuts") or [])[:3])
            cuts.append({"icon": "🔧", "label": "經理人加減碼（權重）", "type": "經理人選股理念",
                "priority": 80,
                "tldr": f"權重加碼 {d['adds'][0][0]} 等 {len(d['adds'])} 檔",
                "fact": f"加碼：{adds}" + (f"｜減碼：{cutss}" if cutss else "") + f"（{d.get('prev_date')}→{d.get('date')}，權重變化含股價）",
                "suggest": "海外成分無官方張數→以權重變化推估；發布前以投信官網核對。",
                "example": f"【{etf} 持股權重異動：{d['adds'][0][0]} 領銜】",
                "links": [_moneydj(etf), _etfinfo(etf)]})
    # 主動度 vs 0050（💎 策略亮點主打）：重點化拆解——公式/台積電對比/差異化押注/贏0050幅度
    vb = (fast or {}).get("vs_bench")
    if vb:
        tb = vb.get("top_bench") or {}
        uqs = "、".join(f"{u['name']} {u['weight']}%" for u in (vb.get("unique") or [])[:4])
        ytd_x, m3_x = _excess0050(perf, "年初以來"), _excess0050(perf, "近3月")
        xtxt = "、".join(t for t in [(f"年初以來 +{ytd_x:.0f}%" if ytd_x else ""),
                                     (f"近3月 +{m3_x:.0f}%" if m3_x else "")] if t)
        AS = vb["active_share"]
        bullets = [
            {"k": "主動度", "v": f"{AS:.0f}%（投組有 {AS:.0f}% 跟 0050 不一樣）"},
            {"k": "台積電", "v": f"0050 押 {tb.get('bench_w')}%、本檔只 {tb.get('fund_w')}% → 0050 其實≈台積電 ETF"},
            {"k": "怎麼贏", "v": f"壓低台積電、把 {vb.get('unique_weight')}% 押在排名 51~150 的中型成長股"},
            {"k": "押哪些", "v": f"{uqs}（這些 0050 都沒有）"},
        ]
        if xtxt:
            bullets.append({"k": "贏 0050", "v": xtxt})
        cuts.append({"icon": "💎", "label": "主動度 vs 0050", "type": "經理人選股理念",
            "priority": 93,
            "tldr": f"主動度 {AS:.0f}%（vs 0050）·{('贏 0050 ' + xtxt) if xtxt else '真的在選股、非換包裝指數'}",
            "fact": "", "bullets": bullets,
            "suggest": "主打『不是換包裝指數、是真的在選股』；用『台積電權重差＋贏 0050 幅度』當鐵證。",
            "example": f"【0050 其實是台積電 ETF！{etf} 主動度 {AS:.0f}%"
                       + (f"、年初以來贏 0050 近 {abs(ytd_x):.0f}%】" if ytd_x else "、真的在主動選股】"),
            "links": [_etfinfo(etf), _moneydj(etf)]})
    # 績效超車（🏆 從多週期報酬表萃取實際領先幅度）：取代僅標贏/輸的 BEAT_PEERS_MULTI
    ps = _perf_superiority(perf, etf)
    if ps:
        cuts.append(ps)
    # signals → 切點卡（過濾退化訊號 + 用 evidence 補上實際數字）
    for s in f.get("signals", []):
        h = s.get("headline") or ""
        if "-0 張" in h or "＋0 張" in h or "+0 張" in h or "現權重 0.00" in h:
            continue
        det = s["detector"]
        if det == "ACTIVE_SHARE" and vb:          # 已用上面重點化卡取代，避免重複
            continue
        if det in ("BEAT_PEERS_MULTI", "ALPHA_BEAT") and ps:   # 已用 🏆 績效超車卡（含實際領先幅度、與圖表同源）取代
            continue
        ev = {}
        try:
            ev = json.loads(s.get("evidence") or "{}")
        except Exception:
            ev = {}
        # 補實際績效數字（DB evidence 有存者）
        if det == "ALPHA_BEAT" and ev.get("etf_ret") is not None:
            er, al = ev["etf_ret"], ev.get("alpha", 0)
            h = f"{h}：本檔 {er*100:+.2f}% vs {ev.get('bench', '0050')} {(er - al) * 100:+.2f}%"
        elif det == "BEAT_NAMED_PEERS" and ev.get("beaten"):
            tops = "、".join(f"{b['code']} +{b['gap'] * 100:.2f}%" for b in ev["beaten"][:4])
            h = f"{h}（{ev.get('period', '')}領先：{tops}）"
        elif det == "BEAT_PEERS_MULTI":
            h = f"{h}　※各期實際報酬率未存於資料庫，僅標贏/輸"
        elif det == "PEER_CHAMPION":
            h = f"{h}　※同類各檔實際報酬率本機未留存，無法逐檔列示"
        t, icon = DET_MAP.get(det, ("持股亮點／新題材", "✨"))
        cuts.append({"icon": icon, "label": det, "type": t,
            "priority": SIG_PRI.get(det, 55),
            "tldr": h,
            "fact": h, "suggest": "可直接轉成此分類切點素材",
            "example": "", "evidence": s.get("evidence", ""),
            "links": [_yahoo(etf), _etfinfo(etf)]})
    return _enrich(cuts)


def _youtube_voice(etf_id: str) -> list[dict]:
    """有 YOUTUBE_API_KEY（env 或 ~/.fh_youtube_key）→ 自動擷取 YouTube 提及，baseline 分析後當口碑。

    無金鑰 → 回 []（不影響 drop-in 口碑）。情緒/業配為 baseline 推估，標待人工複核。
    """
    import os
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        kp = Path.home() / ".fh_youtube_key"
        if kp.exists():
            key = kp.read_text().strip()
            if key:
                os.environ["YOUTUBE_API_KEY"] = key
    # 持久化：API 額度有限/偶發失敗時，沿用上次保存的近一週影片（避免區塊忽然空白）。
    yf = FAST_DIR / f"youtube_{etf_id}.json"
    _cached = lambda: (_load_json(yf).get("items") or [])
    if not key:
        return _cached()
    try:
        from .connectors.social import youtube, base as sbase
        mentions = youtube.fetch(window_days=7)   # 本檔話題+口碑限近一週
    except Exception:
        return _cached()
    from datetime import date as _d, timedelta as _td
    cutoff = (_d.today() - _td(days=7)).isoformat()
    out = []
    for m in mentions:
        if m.etfs and etf_id not in m.etfs:
            continue
        if (not m.etfs) and etf_id != "00991A":      # 泛論只掛主角，避免每頁重複
            continue
        if m.date and m.date < cutoff:               # 嚴格限近一週（標發文日）
            continue
        try:
            a = sbase.analyze(m)
        except Exception:
            a = {"sentiment": "中性", "suspected_ad": False, "ad_terms": []}
        out.append({
            "source": f"YouTube · {m.author}　{m.date or ''}", "kind": "KOL",
            "summary": (m.text or "")[:130],
            "intent": "YouTube 自動擷取（情緒/業配為 baseline 推估，待人工複核）",
            "sentiment": a.get("sentiment", "中性"),
            "suspected_ad": a.get("suspected_ad", False),
            "ad_reason": "、".join(a.get("ad_terms", [])) or "",
            "reusable": "", "fh_play": "", "url": m.url,
        })
    out = out[:12]
    if out:                                          # 有抓到 → 保存供下次 API 失敗時沿用
        try:
            FAST_DIR.mkdir(parents=True, exist_ok=True)
            yf.write_text(json.dumps({"items": out, "as_of": datetime.now().strftime("%Y-%m-%d %H:%M")},
                                     ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return out
    return _cached()                                 # API 額度用盡/查無 → 沿用上次保存的


def _news_voice(etf_id: str) -> list[dict]:
    """data/fast/news_{etf}.json（fetch_news 自動擷取，近7天）→ 口碑區的新聞列（標發文時間）。"""
    doc = _load_json(FAST_DIR / f"news_{etf_id}.json")
    out = []
    for it in (doc.get("items") or []):
        out.append({
            "source": f"{it.get('source', '新聞')}　{it.get('date', '')}", "kind": "新聞",
            "summary": it.get("title", ""),
            "intent": "Google News 自動擷取・近一週（標發文時間）；點連結看原文，發布前自行查證。",
            "sentiment": "中性", "suspected_ad": False, "ad_reason": "",
            "reusable": "", "fh_play": "", "url": it.get("url", ""),
        })
    return out


def build_etf_model(etf_id: str, *, date=None) -> dict:
    doc = parse.parse_file(parse.latest_report(etf_id, date=date))
    f = firsthand.our_facts(etf_id)
    intel = _load_json(INTEL_DIR / f"{doc.date}_{doc.etf_id}.json")
    intel_src = "claude-deep" if intel else "baseline"

    fast = _load_json(FAST_DIR / f"{doc.etf_id}.json")   # 同日求鮮：市況/績效歸因/持股異動
    # 載入該檔最新一份 intel（檔名為 {date}_{etf}.json）→ 不必每天改名也能取到最新分析
    _ic = sorted(INTEL_DIR.glob(f"*_{doc.etf_id}.json"))
    if _ic:
        intel = _load_json(_ic[-1])
        intel_src = "claude-deep" if intel else "baseline"
    perf = firsthand.perf_periods(doc.etf_id)
    data_cuts = _data_cuts(f, doc.etf_id, fast, perf)
    peers = firsthand.peer_table(etf_id)
    scan = firsthand.competitor_scan(etf_id)

    # 我們好在哪：signals 中的相對優勢 + drop-in edge
    edge_dets = {"BEAT_NAMED_PEERS", "PEER_CHAMPION", "UNIQUE_HOLDING", "LEAD_POSITION",
                 "ALPHA_BEAT", "BEAT_PEERS_MULTI"}
    edges = [{"point": s["headline"], "src": s["detector"]}
             for s in f.get("signals", []) if s["detector"] in edge_dets]
    edges = (intel.get("edge") or []) + edges

    # 口碑：自動新聞（近7天，最即時）置頂 + Claude drop-in 深析（皆標日期）；YouTube 另成獨立區塊。
    voice = _news_voice(doc.etf_id) + (intel.get("voice") or [])
    youtube = _youtube_voice(doc.etf_id)

    return {
        "id": doc.etf_id, "name": doc.name, "short_name": baseline.short_name(doc.name),
        "date": doc.date, "header": _clean_header(doc.header), "is_nav": not f.get("volume"),
        # 市價新鮮度：同日求鮮(fast)有當日就用它；否則用 peer_quotes(TPEx) 的市價日。
        "mkt_date": (fast.get("as_of") if fast.get("as_of") else f.get("mkt_date")),
        "price_src": f.get("price_src"),
        "close": (fast.get("market", {}).get("price") if fast.get("as_of") else f.get("close")),
        "change_pct": (fast["market"]["change_pct"] / 100 if (fast.get("as_of") and fast.get("market", {}).get("change_pct") is not None) else f.get("change_pct")),
        "fast": fast,   # 同日求鮮：市況/績效歸因/持股異動
        "data_cuts": data_cuts, "perf": perf,
        "peers": peers, "scan": scan, "edges": edges,
        "competitor_notes": intel.get("competitor_notes") or {},
        "topic": intel.get("topic") or [], "voice": voice, "youtube": youtube,
        # 🆕 今日新變化＋最該打的新賣點 drop-in（每次更新由 Claude 親填；置頂卡，無則不顯示）
        "whatsnew": intel.get("whatsnew") or None,
        # 配息率/配息比較/稅賦優惠/海外持股(中文對照) drop-in（NAV 型海外入息檔專用，無則不顯示）
        "income": intel.get("income") or None,
        # 經理人持股操作＋為什麼（換股快報式）drop-in：放進績效歸因、常駐顯示（續抱日也標）；無則不顯示
        "swaps": intel.get("swaps") or None,
        "intel_src": intel_src, "intel_note": intel.get("note", ""),
        "stats": {"data": len(data_cuts), "peers": len(peers), "scan": len(scan),
                  "topic": len(intel.get("topic") or []), "voice": len(voice), "youtube": len(youtube)},
    }


# 分頁顯示順序（主角在左、00986D 放最右）；未列入者依代號排在其後。
TAB_ORDER = ["00991A", "00998A", "00986D"]


def build_model(*, date=None) -> dict:
    ids = sorted(parse.list_etf_ids(),
                 key=lambda x: (TAB_ORDER.index(x) if x in TAB_ORDER else len(TAB_ORDER), x))
    etfs = []
    for etf_id in ids:
        try:
            etfs.append(build_etf_model(etf_id, date=date))
        except FileNotFoundError:
            continue
    # today＝產出當下日期；前端用來判斷某筆報價是否「當日最新」→ 黃字標註。
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "today": datetime.now().strftime("%Y-%m-%d"), "etfs": etfs}


def render_html(model: dict) -> str:
    data = json.dumps(model, ensure_ascii=False).replace("</", "<\\/")
    return _SHELL.replace("/*__DATA__*/", data)


_SHELL = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FH主動式ETF雷達</title>
<style>
:root{--bg:#0f1220;--card:#1a1f33;--card2:#222942;--ink:#eef1f8;--mut:#9aa3bd;
--acc:#6ea8fe;--teal:#4fd1c5;--amber:#f6c453;--red:#ff6b6b;--green:#51cf66;--purple:#b197fc;--line:#2c3350}
*{box-sizing:border-box}
body{margin:0;font-family:"PingFang TC","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;
background:linear-gradient(180deg,#0b0e1a,#0f1220);color:var(--ink);line-height:1.55}
.wrap{max-width:1180px;margin:0 auto;padding:18px 20px 60px}
header.top{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px 16px;margin-bottom:6px}
header.top h1{font-size:20px;margin:0;letter-spacing:.5px}
header.top .gen{color:var(--mut);font-size:12px}
.tabs{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 6px}
.tab{padding:8px 16px;border:1px solid var(--line);border-radius:999px;background:var(--card);
color:var(--mut);cursor:pointer;font-size:14px;font-weight:600}
.tab:hover{color:var(--ink);border-color:var(--acc)}
.tab.on{background:var(--acc);color:#0b0e1a;border-color:var(--acc)}
.etfhead{margin:14px 0 4px}
.etfhead h2{margin:0 0 4px;font-size:22px}
.etfhead .hdr{color:var(--mut);font-size:13px;margin-bottom:8px}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:6px}
.badge{font-size:12px;padding:3px 10px;border-radius:8px;background:var(--card2);color:var(--mut);border:1px solid var(--line)}
.badge.src{color:var(--teal)}
.sec{margin:30px 0 8px;font-size:16px;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px;
border-left:3px solid var(--teal);padding-left:10px}
.sec.c2{border-color:var(--amber)} .sec.c3{border-color:var(--purple)} .sec.c4{border-color:var(--green)}
.sec .pill{font-size:11px;color:var(--mut);font-weight:500}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:13px}
.dcard{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px}
.dcard .lab{font-size:12px;color:var(--mut);font-weight:700;letter-spacing:.5px}
.dcard .type{float:right;font-size:11px;color:var(--teal);border:1px solid var(--line);border-radius:6px;padding:1px 7px}
.dcard .fact{font-size:14px;font-weight:600;margin:8px 0}
.kvlist{margin:9px 0;padding:0;list-style:none;font-size:13px}
.kvlist li{padding:6px 0;border-bottom:1px solid var(--line);line-height:1.55}
.kvlist li:last-child{border-bottom:0}
.kvlist li b{color:var(--teal);margin-right:7px;white-space:nowrap}
.dcard .sug{font-size:12.5px;color:var(--amber);margin-bottom:7px}
.dcard .ex{font-size:12.5px;background:linear-gradient(90deg,#1f2742,#1a1f33);border-left:3px solid var(--amber);
padding:7px 10px;border-radius:6px;margin-bottom:8px}
.links{display:flex;flex-wrap:wrap;gap:6px}
a.lnk{font-size:11px;color:var(--acc);text-decoration:none;border:1px solid var(--line);border-radius:7px;padding:2px 8px;background:var(--card2)}
a.lnk:hover{border-color:var(--acc)}
.copybtn{font-size:11px;color:var(--acc);background:none;border:1px solid var(--line);border-radius:6px;padding:1px 8px;cursor:pointer;margin-left:6px}
table.peer{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}
table.peer th,table.peer td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right}
table.peer th{color:var(--mut);font-weight:600;font-size:12px} table.peer td.l,table.peer th.l{text-align:left}
tr.me{background:#1c2746} tr.me td{color:var(--teal);font-weight:700}
.up-pos{color:var(--green)} .dn{color:var(--red)}
/* 多週期報酬：本檔 vs 該檔差距小膠囊（綠=本檔贏、紅=本檔輸，跟灰色對手報酬區隔、好辨別） */
.gp{font-size:11px;font-weight:800;border-radius:5px;padding:1px 5px;margin-left:4px;white-space:nowrap;font-variant-numeric:tabular-nums}
.gp.w{color:var(--green);background:rgba(81,207,102,.14)}
.gp.l{color:var(--red);background:rgba(255,107,107,.14)}
.gp.e{color:var(--mut);background:var(--card2)}
.fresh{color:var(--amber);font-weight:800;font-size:11px;border:1px solid var(--amber);border-radius:6px;padding:1px 7px;margin-left:7px;white-space:nowrap}
td .fresh,th .fresh{padding:0 5px;margin-left:5px;border-radius:5px}
.edge{background:#14241b;border:1px solid #265037;border-radius:9px;padding:9px 12px;margin-bottom:8px;font-size:13px}
.edge b{color:var(--green)}
.scard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px;margin-bottom:10px}
.scard .top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:5px}
.scard .nm{font-size:14px;font-weight:700} .chip{font-size:11px;padding:2px 8px;border-radius:6px;background:var(--card2);color:var(--mut)}
.scard .h{font-size:12.5px;color:var(--mut);margin:3px 0}
.kv{font-size:13px;margin:5px 0;display:flex;gap:7px}.kv .k{flex:0 0 64px;color:var(--mut);font-size:12px}.kv .v{flex:1}
.kv .v.intent{color:var(--amber)}.kv .v.play{color:var(--teal)}
.crow{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px;margin-bottom:10px}
.crow .top{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:5px}
.chip.ad{color:var(--red);border:1px solid var(--red)}.chip.pos{color:var(--green)}.chip.neg{color:var(--red)}
.note{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--line);padding-top:14px}
.up{background:#172033;border:1px solid var(--line);border-radius:12px;padding:14px;margin:16px 0;font-size:13px;color:var(--mut)}
.up b{color:var(--teal)} .up code{background:#0b0e1a;padding:1px 6px;border-radius:4px;color:var(--acc)}
.empty{color:var(--mut);font-size:13px;padding:8px 0}
/* —— 🆕 今日新變化 ＋ 最該打的新賣點（置頂卡・預設收合的折疊） —— */
.acc.wnacc{margin:12px 0 6px;border-left:4px solid var(--amber);background:linear-gradient(180deg,#221d12,#1a1f33)}
.acc.wnacc>.ah>span:first-child{color:var(--amber);font-weight:800;font-size:15px}
.wnsub{font-size:11.5px;color:var(--mut);font-weight:500}
.wnplays{display:flex;flex-direction:column;gap:8px}
.wnplay{background:#1a1f33;border:1px solid var(--line);border-radius:10px;padding:9px 12px}
.wnph{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:14.5px}
.wnph b{color:var(--ink)}
.wnrk{flex:0 0 20px;height:20px;line-height:20px;text-align:center;border-radius:6px;background:var(--amber);color:#0b0e1a;font-size:12px;font-weight:800}
.wnstars{font-size:11px;letter-spacing:-1px}
.wnwhy{font-size:12.5px;color:var(--mut);margin-top:4px;line-height:1.55}
.wncon{font-size:12.5px;color:var(--teal);margin-top:3px;font-weight:600}
.wnchanges{margin-top:11px;border-top:1px dashed var(--line);padding-top:9px}
.wnclab{font-size:11.5px;color:var(--mut);font-weight:700;margin-bottom:5px}
.wnrow{display:flex;align-items:flex-start;gap:8px;padding:4px 0;font-size:13px;line-height:1.5}
.wnrow .wncat{flex:0 0 auto;font-size:11px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:1px 6px;background:var(--card2)}
.wnrow .wndir{flex:0 0 auto;font-weight:800;width:16px;text-align:center}
.wnrow.u .wndir{color:var(--green)} .wnrow.d .wndir{color:var(--red)} .wnrow.n .wndir{color:var(--acc)} .wnrow.f .wndir{color:var(--mut)}
.wnrow .wntext{flex:1;min-width:0}
/* —— 配息率／配息比較／稅賦／海外持股(中文) —— */
.incsub{font-size:13.5px;font-weight:700;color:var(--ink);margin:16px 0 6px;display:flex;align-items:center;gap:7px}
.incsub .t{font-size:11px;color:var(--mut);font-weight:500}
.inchero{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:baseline;background:linear-gradient(90deg,#1d2742,#1a1f33);
border:1px solid #2c3a5e;border-left:3px solid var(--green);border-radius:12px;padding:13px 16px;margin:6px 0}
.inchero .big{font-size:26px;font-weight:800;color:var(--green);font-variant-numeric:tabular-nums}
.inchero .lab{font-size:12px;color:var(--mut)} .inchero .sub{font-size:13px;color:var(--ink)}
table.divtbl{width:100%;border-collapse:collapse;font-size:13px;margin-top:4px}
table.divtbl th,table.divtbl td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right}
table.divtbl th{color:var(--mut);font-weight:600;font-size:12px}
table.divtbl td.l,table.divtbl th.l{text-align:left}
.dyield{font-weight:800;color:var(--amber);font-variant-numeric:tabular-nums}
.taxcard{background:#14241b;border:1px solid #265037;border-radius:11px;padding:11px 13px;margin-bottom:9px}
.taxcard .tp{font-size:13.5px;font-weight:700;color:var(--green);margin-bottom:3px}
.taxcard .td{font-size:12.5px;color:var(--mut);line-height:1.6}
.taxedge{background:linear-gradient(90deg,#1d2742,#1a1f33);border-left:3px solid var(--green);border-radius:8px;padding:9px 12px;margin-bottom:10px;font-size:13.5px;color:var(--ink);font-weight:600}
.wtag{font-size:10.5px;color:var(--mut);border:1px solid var(--line);border-radius:5px;padding:0 5px;margin-left:5px;white-space:nowrap}
.cdisc{color:var(--mut);font-size:11.5px;margin-top:6px;line-height:1.55}
/* 持股變化卡（加碼/減碼/新進）+ 國外新聞 */
.hncard{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--line);border-radius:11px;padding:11px 13px;margin-bottom:9px}
.hncard.add{border-left-color:var(--green)} .hncard.new{border-left-color:var(--acc)} .hncard.cut{border-left-color:var(--red)}
.hncard .hntop{display:flex;flex-wrap:wrap;align-items:center;gap:7px;font-size:14px}
.hncard .hnwhy{font-size:12.5px;color:var(--mut);line-height:1.6;margin-top:5px}
.mv{font-size:11px;font-weight:800;border-radius:6px;padding:1px 8px;white-space:nowrap}
.mv.add{color:var(--green);background:rgba(81,207,102,.14)} .mv.new{color:var(--acc);background:rgba(110,168,254,.16)} .mv.cut{color:var(--red);background:rgba(255,107,107,.14)}
/* 稅務相關文章列 */
.artrow{border-bottom:1px solid var(--line);padding:8px 0}
.artrow:last-child{border-bottom:0}
.artt{font-size:13.5px;color:var(--acc);text-decoration:none;font-weight:600}
.artt:hover{text-decoration:underline}
.arts{font-size:11px;color:var(--mut);margin-left:7px}
.artsum{font-size:12px;color:var(--mut);line-height:1.55;margin-top:3px}
/* —— 今日必看：一行摘要 + 點開細節 —— */
.hl{display:flex;flex-direction:column;gap:8px;margin:8px 0 4px}
.hlrow{display:flex;align-items:center;gap:11px;background:var(--card);border:1px solid var(--line);
border-left:4px solid var(--line);border-radius:11px;padding:11px 14px;cursor:pointer;transition:border-color .15s}
.hlrow:hover{border-color:var(--acc)}
.hlrow.g-hot{border-left-color:var(--red)}.hlrow.g-vs{border-left-color:var(--amber)}.hlrow.g-hold{border-left-color:var(--purple)}
.hlrow .rk{flex:0 0 22px;text-align:center;font-size:13px;font-weight:800;color:var(--mut)}
.hlrow .hi{font-size:18px;flex:0 0 auto}
.hlrow .htype{font-size:11px;color:var(--teal);border:1px solid var(--line);border-radius:6px;padding:1px 7px;white-space:nowrap;flex:0 0 auto}
.hlrow .htldr{font-size:14.5px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hlrow .caret{font-size:11px;color:var(--acc);flex:0 0 auto;white-space:nowrap}
.hlrow.open{border-color:var(--acc);border-bottom-left-radius:0;border-bottom-right-radius:0}
.hlrow.open .caret{color:var(--mut)}
.hldetail{display:none}
.hldetail.open{display:block;margin:-9px 0 2px;border:1px solid var(--acc);border-top:0;border-radius:0 0 11px 11px;padding:10px 12px 12px;background:var(--card)}
.hldetail .dcard{border:0;background:transparent;padding:0}
/* —— 分類折疊 —— */
.acc{border:1px solid var(--line);border-radius:12px;margin:10px 0;overflow:hidden;background:var(--card)}
.acc .ah{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:13px 16px;cursor:pointer;
font-weight:700;font-size:15px;user-select:none}
.acc .ah:hover{background:var(--card2)}
.acc .ah .cnt{font-size:12px;color:var(--mut);font-weight:500;white-space:nowrap}
.acc .abody{display:none;padding:2px 14px 15px}
.acc.open>.abody{display:block}
.acc.open>.ah{border-bottom:1px solid var(--line)}
.acc.open>.ah .cnt{color:var(--acc)}
.acc .ah .glamp{flex:0 0 8px;width:8px;height:8px;border-radius:50%;background:var(--mut)}
.acc.g-hot>.ah .glamp{background:var(--red)}.acc.g-vs>.ah .glamp{background:var(--amber)}.acc.g-hold>.ah .glamp{background:var(--purple)}
/* —— 價格基準日：大字、明顯 —— */
.asof{display:flex;align-items:center;flex-wrap:wrap;gap:10px 14px;margin:10px 0 6px;padding:12px 16px;
border:1px solid var(--line);border-radius:13px;background:linear-gradient(90deg,#18203a,#1a1f33)}
.asof.on{border-color:var(--amber);background:linear-gradient(90deg,#2a2616,#1a1f33)}
.asof .lab{font-size:13px;color:var(--mut);font-weight:700}
.asof .d{font-size:26px;font-weight:800;letter-spacing:.5px;color:var(--ink);line-height:1}
.asof.on .d{color:var(--amber)}
.asof .today{font-size:12px;font-weight:800;color:#0b0e1a;background:var(--amber);border-radius:8px;padding:3px 10px}
.asof .stale{font-size:12px;color:var(--mut);border:1px solid var(--line);border-radius:8px;padding:3px 10px}
.asof .px{margin-left:auto;font-size:14px;color:var(--mut)}.asof .px b{font-size:18px;color:var(--ink)}
/* —— 績效歸因（同日最新）：市況 + 持股異動 + 推漲/下跌 Top3 + 貢獻度排行 —— */
.mkline{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 14px;font-size:13.5px;color:var(--mut);margin:8px 0}
.mkline b{color:var(--ink);font-size:15px}
.acard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:10px 0}
.alab{font-size:13.5px;font-weight:700;color:var(--ink);margin-bottom:8px}.alab small{color:var(--mut);font-weight:500;font-size:11.5px}
.hchips{display:flex;flex-wrap:wrap;gap:7px}
.hchip{font-size:12.5px;padding:4px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card2);color:var(--ink)}
.hchip b{margin-left:3px}.hchip.cut{border-color:#5b2730}.hchip.cut b{color:var(--red)}
.hchip.add{border-color:#1f4a32}.hchip.add b{color:var(--green)}.hchip.new{border-color:#3a3560}.hchip.new b{color:var(--purple)}
.hchip.px{border-color:var(--line);color:var(--mut)}
.hchip .tg{color:var(--mut);font-size:11px;margin-right:4px}
.difwrap{overflow-x:auto;margin-top:8px}
.difftbl{width:100%;border-collapse:collapse;font-size:12.5px}
.difftbl th,.difftbl td{padding:6px 9px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
.difftbl th{color:var(--mut);font-weight:600;font-size:11.5px}
.difftbl th.num,.difftbl td.num{text-align:right;font-variant-numeric:tabular-nums}
.difftbl td small{color:var(--mut)}
.difftbl .hchip{padding:2px 8px;font-size:11.5px}
.attgrid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}
@media(max-width:640px){.attgrid{grid-template-columns:1fr}}
/* 寬表格在手機改水平捲動，避免整頁橫向溢出 */
.tblscroll{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0 -2px}
/* —— YouTube 分享：卡片式 —— */
.ytgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.ytcard{display:block;text-decoration:none;background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:11px 12px;color:var(--ink)}
.ytcard:hover{border-color:var(--red)}
.ytcard .yttop{display:flex;align-items:center;gap:7px;margin-bottom:5px;flex-wrap:wrap}
.ytcard .ytbadge{background:var(--red);color:#fff;font-size:11px;border-radius:5px;padding:1px 7px;font-weight:700}
.ytcard .ytsrc{font-size:12px;color:var(--mut);font-weight:600}
.ytcard .ytsum{font-size:13px;line-height:1.5;color:var(--ink);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.ytcard .ytgo{display:inline-block;margin-top:7px;font-size:12px;color:var(--red);font-weight:600}
@media(max-width:560px){.ytgrid{grid-template-columns:1fr}}
/* YouTube 收合列：紅色點綴 + 與今日必看間距，讀起來是刻意的小區塊、不突兀 */
.acc.g-yt{border-color:#4a2228;border-left:3px solid var(--red);margin-top:16px;background:linear-gradient(90deg,#1e1416,var(--card))}
.acc.g-yt>.ah .cnt{color:var(--red)}
.acc.g-yt.open>.ah{border-bottom-color:#4a2228}
/* —— 手機排版優化（使用者主要用手機）—— */
@media(max-width:560px){
  .wrap{padding:12px 12px 48px}
  header.top h1{font-size:16px} header.top{gap:6px 10px}
  .tabs{gap:6px;margin:12px 0 4px} .tab{padding:6px 11px;font-size:13px}
  .tab small{display:none}
  .etfhead h2{font-size:18px} .etfhead .hdr{font-size:12px}
  .sec{display:block;font-size:14.5px;margin:22px 0 6px;line-height:1.4} .sec .pill{display:block;margin-top:3px}
  .grid{grid-template-columns:1fr;gap:10px}
  .dcard,.scard,.crow,.acard,.mkline{padding:11px 12px}
  .asof{padding:10px 12px;gap:6px 10px} .asof .d{font-size:21px} .asof .px{margin-left:0;flex-basis:100%}
  .asof .px b{font-size:16px}
  table.peer th,table.peer td{padding:6px 7px;font-size:12px}
  .difftbl th,.difftbl td{padding:5px 7px;font-size:11.5px}
  .hlrow{padding:10px 11px;gap:8px} .hlrow .htldr{font-size:13.5px} .hlrow .htype{display:none}
  .acc .ah{padding:11px 13px;font-size:14px}
  .barrow .bcode{flex-basis:96px} .barrow .bval{flex-basis:56px}
  .mvtop{font-size:13px} .badges{gap:6px}
  .note{font-size:11.5px}
}
.mvcard{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:10px 12px;margin-bottom:8px;border-left:4px solid var(--line)}
.mvcard.u{border-left-color:var(--green)}.mvcard.d{border-left-color:var(--red)}
.mvtop{font-size:13.5px;font-weight:700}.mvtop b{color:var(--acc);margin-right:5px}
.mvmid{font-size:12.5px;color:var(--mut);margin:3px 0}.mvbot{font-size:12.5px}.mvbot small{color:var(--mut)}
.bars{margin-top:6px}
.barrow{display:flex;align-items:center;gap:9px;font-size:12.5px;margin:5px 0}
.barrow .bcode{flex:0 0 120px;color:var(--ink)}.barrow .bcode small{color:var(--mut)}
.barrow .bwrap{flex:1;height:11px;background:rgba(255,255,255,.04);border-radius:6px;overflow:hidden;position:relative}
.barrow .bar{display:block;height:100%;border-radius:6px}
.barrow .bar.bp{background:linear-gradient(90deg,#2a6b46,var(--green))}.barrow .bar.bn{background:linear-gradient(90deg,#6b2a2f,var(--red))}
.barrow .bval{flex:0 0 64px;text-align:right;font-weight:700}
.attnote{color:var(--mut);font-size:11.5px;margin-top:10px;line-height:1.5}
.upn{color:var(--green)}
</style>
</head>
<body>
<div class="wrap">
  <header class="top"><h1>📡 FH主動式ETF雷達 · 每日切點素材</h1><span class="gen" id="gen"></span></header>
  <div class="tabs" id="tabs"></div>
  <div id="panel"></div>
  <div class="note" id="note"></div>
</div>
<script>
const DATA = /*__DATA__*/;
const SRC={"claude-deep":"Claude 深析（話題口碑 drop-in）","baseline":"純數據（待話題口碑 drop-in）"};
const esc=s=>(s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const nf=n=>(n==null?"—":Number(n).toLocaleString());
let cur=0;
function copyText(t,b){navigator.clipboard&&navigator.clipboard.writeText(t).then(()=>{b.textContent="已複製✓";setTimeout(()=>b.textContent="複製",1200)});}
function linkList(ls){return (ls||[]).map(l=>`<a class="lnk" href="${esc(l.url)}" target="_blank" rel="noopener">🔗 ${esc(l.label)}</a>`).join("");}

function dataCard(d){
  const ex=d.example?`<div class="ex">📝 ${esc(d.example)}<button class="copybtn" data-c="${esc(d.example)}">複製</button></div>`:"";
  const bl=(d.bullets&&d.bullets.length)?`<ul class="kvlist">`+d.bullets.map(b=>
    (typeof b==='string')?`<li>${esc(b)}</li>`:`<li><b>${esc(b.k)}</b>${esc(b.v)}</li>`).join("")+`</ul>`:"";
  return `<div class="dcard"><span class="type">${esc(d.type)}</span><div class="lab">${d.icon} ${esc(d.label)}</div>
    ${d.fact?`<div class="fact">${esc(d.fact)}</div>`:""}${bl}
    <div class="sug">💡 ${esc(d.suggest)}</div>${ex}
    <div class="links">${linkList(d.links)}</div></div>`;
}
function perfTable(p,me,today){
  if(!p||!p.rows||!p.rows.length) return "";
  const sg=v=>v==null?'':(v>=0?'up-pos':'dn'), pm=v=>v==null?'—':(v>=0?'+':'')+Number(v).toFixed(2)+'%';
  // 括號＝本檔(me)−該檔（以本檔為基準去扣）：正＝本檔贏(綠)、負＝本檔輸(紅)，方便一眼分辨
  const gap=(self,peer)=>{
    if(self==null||peer==null) return '';
    const d=self-peer, cls=d>0?'w':(d<0?'l':'e');
    return ` <span class="gp ${cls}">${(d>0?'+':'')+d.toFixed(2)}％</span>`;
  };
  const bs=p.benches||[];
  const bhead=bs.map(b=>`<th>${esc((b.issuer||'')+b.label)}${b.is_index?'<small style="color:var(--mut)"> 基準</small>':''}</th>`).join("");
  const rows=p.rows.map(r=>`<tr>
    <td class="l">${esc(r.period)}</td>
    <td class="${sg(r.etf)}">${pm(r.etf)}</td>
    ${bs.map(b=>{const v=r.vals?r.vals[b.code]:null;return `<td style="color:var(--mut)">${pm(v)}${gap(r.etf,v)}</td>`;}).join("")}
    <td class="${sg(r.excess)}">${pm(r.excess)}</td></tr>`).join("");
  const fresh=(today&&p.as_of===today)?`<span class="fresh">🟡 今日最新 ${esc(p.as_of)}</span>`:"";
  return `<div class="tblscroll"><table class="peer" style="margin-bottom:6px"><tr>
    <th class="l">期間</th><th>本檔 ${esc(me)}</th>${bhead}<th>超額 vs ${esc(p.peer_mean_label||'同類')}</th></tr>${rows}</table></div>
    <div style="color:var(--mut);font-size:11px;margin-bottom:16px">※ 市價報酬（含息以基金月報為準）·　括號＝本檔(${esc(me)})vs 該檔之差距(％)，<span class="gp w">＋綠＝本檔贏</span> <span class="gp l">－紅＝本檔輸</span>·　超額＝本檔−主動同類均（不含 0050 基準）·「${esc(me)} 成立以來」自本檔成立日起算、各同類為同期間（非各自成立日）·　as-of ${esc(p.as_of)}${fresh}</div>`;
}
function peerTable(peers,me,today){
  if(!peers.length) return '<div class="empty">尚無同類量能資料（跑 scripts/fetch_peers.py）。</div>';
  const rows=peers.map((p,i)=>{
    const fresh=(today&&p.trade_date===today)?'<span class="fresh">今日</span>':(p.trade_date?`<small style="color:var(--mut)"> ${esc(p.trade_date.slice(5))}</small>`:'');
    return `<tr class="${p.code===me?'me':''}">
    <td class="l">${i+1}. ${esc(p.name)}<small style="color:var(--mut)"> ${p.code}</small></td>
    <td>${esc(p.issuer)}</td><td>${p.close??'—'}${fresh}</td>
    <td class="${p.change_pct>=0?'up-pos':'dn'}">${p.change_pct==null?'—':(p.change_pct>=0?'+':'')+p.change_pct+'%'}</td>
    <td>${nf(p.volume)}</td></tr>`;}).join("");
  return `<div class="tblscroll"><table class="peer"><tr><th class="l">同類ETF（量能高→低）</th><th>發行商</th><th>收盤(市價)</th><th>當日漲跌</th><th>成交量(股)</th></tr>${rows}</table></div>
    <div style="color:var(--mut);font-size:11px;margin-top:5px">※ 收盤為交易所市價（非淨值）。<span class="fresh">今日</span>＝該檔已更新至產表當日；無標示者為前一交易日盤後（上市約晚間才更新、上櫃約 16:00）。</div>`;
}
function scanCard(x,notes){
  const t3=(x.top3||[]).map(h=>`${esc(h.name.slice(0,6))} ${h.w}%`).join("、");
  const note=notes[x.code]?`<div class="kv"><div class="k">我們的接法</div><div class="v play">${esc(notes[x.code])}</div></div>`:"";
  const quote=x.no_quote
    ? `<span class="chip" style="color:var(--mut)">TWSE 無價量(債券ETF)</span>`
    : `<span class="chip">量排 ${x.vol_rank??'—'}</span>`+
      `<span class="chip ${x.change_pct>=0?'pos':'neg'}">${x.change_pct==null?'—':(x.change_pct>=0?'+':'')+x.change_pct+'%'}</span>`+
      `<span class="chip">收 ${x.close??'—'}</span><span class="chip">量 ${nf(x.volume)}</span>`;
  const holds=x.n_holdings
    ? `重壓前3：${t3}　·　前十大集中 ${x.top10_conc}%　·　共 ${x.n_holdings} 檔（as-of ${esc(x.as_of)}・Tier B）`
    : `<span style="color:var(--mut)">持股明細待補（落 config/competitor_holdings 即顯示）</span>`;
  return `<div class="scard"><div class="top"><span class="chip">${esc(x.issuer)}</span><span class="nm">${esc(x.code)}</span>`+
    `<span style="color:var(--mut);font-size:12px">${esc(x.name||'')}</span>${quote}</div>
    <div class="h">${holds}</div>${note}</div>`;
}
function topicCard(t){
  const ex=t.example?`<div class="ex">📝 ${esc(t.example)}<button class="copybtn" data-c="${esc(t.example)}">複製</button></div>`:"";
  return `<div class="dcard"><div class="lab">🗣 ${esc(t.type)}</div><div class="fact" style="font-weight:500">${esc(t.status)}</div>${ex}<div class="links">${linkList(t.links)}</div></div>`;
}
function voiceRow(k){
  const sent=k.sentiment==="正面"?"pos":(k.sentiment==="負面"?"neg":"");
  const link=k.url?`<div class="links" style="margin-top:6px">${linkList([{label:"來源/查證",url:k.url}])}</div>`:"";
  return `<div class="crow"><div class="top"><span class="chip">${esc(k.kind)}</span><span class="nm" style="font-weight:700">${esc(k.source)}</span>
    ${k.sentiment?`<span class="chip ${sent}">${esc(k.sentiment)}</span>`:""}${k.suspected_ad?'<span class="chip ad">疑似業配</span>':''}</div>
    ${k.summary?`<div class="h" style="color:var(--mut)">「${esc(k.summary)}」</div>`:""}
    <div class="kv"><div class="k">意圖</div><div class="v intent">${esc(k.intent)}</div></div>
    ${k.suspected_ad&&k.ad_reason?`<div class="kv"><div class="k">業配依據</div><div class="v" style="color:var(--mut)">${esc(k.ad_reason)}</div></div>`:""}
    ${k.reusable?`<div class="kv"><div class="k">可借用</div><div class="v">${esc(k.reusable)}</div></div>`:""}
    ${k.fh_play?`<div class="kv"><div class="k">復華接法</div><div class="v play">${esc(k.fh_play)}<button class="copybtn" data-c="${esc(k.fh_play)}">複製</button></div></div>`:""}${link}</div>`;
}

const GLABEL={hold:"💎 持股與操作亮點 · 策略亮點【主打】",hot:"🔥 數據型 · 人氣／績效／成長幅度",vs:"🥊 話題型 · 引戰／對比"};
const GORDER=["hold","hot","vs"];
let CUR=null;  // 目前顯示的 ETF model，供點開細節時取卡片

// 折疊區塊：標題 + 計數 + 內容（open=true 則預設展開）
function acc(title,cnt,body,cls,open){
  return `<div class="acc ${cls||''}${open?' open':''}" data-acc><div class="ah"><span>${title}</span>`+
    `<span class="cnt">${esc(cnt)} ▾</span></div><div class="abody">${body}</div></div>`;
}

// ① 今日必看：全切點按 priority 取前 N，一行摘要，點開看完整卡片
function hlStrip(cuts){
  const ranked=cuts.map((c,i)=>({c,i})).sort((a,b)=>(b.c.priority||0)-(a.c.priority||0)).slice(0,6);
  if(!ranked.length) return '<div class="empty">今日尚無數據切點。</div>';
  return `<div class="hl">`+ranked.map(({c,i},n)=>
    `<div class="hlrow g-${c.group}" data-hl="${i}"><span class="rk">${n+1}</span>`+
    `<span class="hi">${c.icon}</span><span class="htype">${esc(c.type)}</span>`+
    `<span class="htldr">${esc(c.tldr||c.fact)}</span><span class="caret">看細節 ▸</span></div>`+
    `<div class="hldetail" data-hld="${i}"></div>`).join("")+`</div>`;
}

// ② 依分類折疊：把切點按大分類分組，各組可展開看全部卡片
function groupAcc(cuts){
  const g={};
  cuts.forEach(c=>{(g[c.group]=g[c.group]||{lab:GLABEL[c.group]||(c.group_icon+' '+c.group_label),items:[]}).items.push(c)});
  const keys=GORDER.filter(k=>g[k]).concat(Object.keys(g).filter(k=>!GORDER.includes(k)));
  return keys.map((k,i)=>acc(g[k].lab,`${g[k].items.length} 項`,
    `<div class="grid">${g[k].items.map(dataCard).join("")}</div>`,`g-${k}`,i===0)).join("");
}

function peerBlock(e){
  const edges=e.edges.length?e.edges.map(x=>`<div class="edge">✅ <b>${esc(x.point)}</b></div>`).join("")
    :'<div class="empty">尚無相對優勢 signals。</div>';
  return peerTable(e.peers,e.id,DATA.today)+`<div style="margin-top:12px">${edges}</div>`;
}
function scanBlock(e){
  const note=e.is_nav?'<div class="empty">本檔為 NAV 型（無交易所量能）；下列量能/競品比較以台股主動ETF（00991A）為主，本檔聚焦 NAV/規模/配息數據與話題口碑。</div>':'';
  return note+`<div>${e.scan.length?e.scan.map(x=>scanCard(x,e.competitor_notes)).join(""):'<div class="empty">尚無競品掃描。</div>'}</div>`;
}
function voiceBlock(e){
  const topic=e.topic.length?`<div class="grid">${e.topic.map(topicCard).join("")}</div>`:'<div class="empty">話題型 drop-in 待補。</div>';
  const voice=e.voice.length?e.voice.map(voiceRow).join(""):'<div class="empty">口碑 drop-in 待補。</div>';
  return topic+`<div style="margin-top:12px">${voice}</div>`;
}
// 🆕 今日新變化 ＋ 最該打的新賣點（置頂卡・預設收合）：上半=⭐賣點潛力排序，下半=分類異動清單。drop-in whatsnew，無則不顯示。
function whatsnewBlock(e){
  const W=e.whatsnew; if(!W) return "";
  const star=n=>'⭐'.repeat(Math.max(1,Math.min(3,n||1)));
  const plays=(W.top_plays||[]).map((p,i)=>
    `<div class="wnplay"><div class="wnph"><span class="wnrk">${i+1}</span><span class="wnstars">${star(p.stars)}</span><b>${esc(p.title)}</b></div>`+
    (p.why?`<div class="wnwhy">${esc(p.why)}</div>`:'')+
    (p.concept?`<div class="wncon">→ 可搭概念：${esc(p.concept)}</div>`:'')+`</div>`).join("");
  const dicon={up:'▲',down:'▼',new:'🆕',flat:'•'}, dcls={up:'u',down:'d',new:'n',flat:'f'};
  const chg=(W.changes||[]).map(c=>
    `<div class="wnrow ${dcls[c.dir]||'f'}"><span class="wncat">${esc(c.cat||'')}</span>`+
    `<span class="wndir">${dicon[c.dir]||'•'}</span><span class="wntext">${esc(c.text)}</span></div>`).join("");
  const body=(plays?`<div class="wnplays">${plays}</div>`:'')+
    (chg?`<div class="wnchanges"><div class="wnclab">本次所有異動</div>${chg}</div>`:'');
  const title=`🆕 今日新變化 ＋ 最該打的新賣點`+(W.prev_date?` <span class="wnsub">vs 上次 ${esc(W.prev_date)}</span>`:'');
  const cnt=`${(W.top_plays||[]).length} 賣點／${(W.changes||[]).length} 異動 · 點開`;
  return acc(title, cnt, body, 'wnacc', false);   // 預設收合
}
// 💰 配息率／配息比較／稅賦優惠／海外持股(中文對照) —— 海外入息檔(00998A/00986D)專用，無 income drop-in 即不顯示。
function incomeBlock(e){
  const I=e.income; if(!I) return "";
  let h="";
  const hero=I.hero;
  if(hero) h+=`<div class="inchero"><div><div class="big">${esc(hero.big)}</div><div class="lab">${esc(hero.lab||'')}</div></div>`+
    (hero.sub?`<div class="sub">${esc(hero.sub)}</div>`:'')+`</div>`;
  if(I.yield_line) h+=`<div class="cdisc" style="font-size:13px;color:var(--ink)">${esc(I.yield_line)}</div>`;
  // 配息比較表
  const C=I.compare;
  if(C&&C.rows&&C.rows.length){
    const rows=C.rows.map(r=>`<tr class="${r.ours?'me':''}">`+
      `<td class="l">${esc(r.name)}<small style="color:var(--mut)"> ${esc(r.code||'')}</small>${r.ours?' <span class="fresh">本檔</span>':''}</td>`+
      `<td>${esc(r.freq||'—')}</td><td class="dyield">${esc(r.yield||'—')}</td>`+
      `<td class="l" style="color:var(--mut);font-size:12px">${esc(r.tag||'')}</td></tr>`).join("");
    h+=`<div class="incsub">📊 配息率比較<span class="t">${esc(C.title||'同類入息ETF')}</span></div>`+
      `<div class="tblscroll"><table class="divtbl"><tr><th class="l">ETF</th><th>配息頻率</th><th>參考殖利率</th><th class="l">定位</th></tr>${rows}</table></div>`+
      (C.note?`<div class="cdisc">※ ${esc(C.note)}</div>`:'');
  }
  // 🔄 持股變化 ＋ 國外新聞（取代靜態前15大持股；focus 在『經理人怎麼動 + 為什麼』）
  const H=I.holdings_news;
  if(H&&H.rows&&H.rows.length){
    const mvcls=m=>m==='減碼'?'cut':(m==='加碼'?'add':'new');
    const rows=H.rows.map(r=>{
      const news=(r.news||[]).map(n=>`<a class="lnk" href="${esc(n.url)}" target="_blank" rel="noopener">📰 ${esc(n.source||'來源')}${n.date?' '+esc(n.date):''}：${esc(n.title||'')}</a>`).join("");
      return `<div class="hncard ${mvcls(r.move)}"><div class="hntop">`+
        `<span class="mv ${mvcls(r.move)}">${esc(r.move)} ${esc(r.delta||'')}</span>`+
        `<b>${esc(r.name_zh)}</b>${r.name_en?`<small style="color:var(--mut)"> ${esc(r.name_en)}</small>`:''}${r.country?`<span class="wtag">${esc(r.country)}</span>`:''}</div>`+
        (r.why?`<div class="hnwhy">${esc(r.why)}</div>`:'')+
        (news?`<div class="links" style="margin-top:6px">${news}</div>`:'')+`</div>`;
    }).join("");
    h+=`<div class="incsub">🔄 持股變化 ＋ 國外新聞<span class="t">${esc(H.title||'')}</span></div>`+
      (H.intro?`<div class="cdisc" style="margin-bottom:6px">${esc(H.intro)}</div>`:'')+rows+
      (H.disclosure?`<div class="cdisc">⚠ ${esc(H.disclosure)}</div>`:'');
  }
  // 🧾 稅賦優勢 ＋ 相關文章（預設收起的折疊區）
  const T=I.tax;
  if(T&&((T.points&&T.points.length)||(T.articles&&T.articles.length))){
    const pts=(T.points||[]).map(c=>`<div class="taxcard"><div class="tp">✅ ${esc(c.point)}</div><div class="td">${esc(c.detail)}</div></div>`).join("");
    const arts=(T.articles||[]).map(a=>`<div class="artrow"><a class="artt" href="${esc(a.url)}" target="_blank" rel="noopener">📄 ${esc(a.title)}</a>`+
      `<span class="arts">${esc(a.source||'')}${a.date?' · '+esc(a.date):''}</span>`+
      (a.summary?`<div class="artsum">${esc(a.summary)}</div>`:'')+
      (a.fh_play?`<div class="kv" style="margin-top:4px"><div class="k">怎麼用</div><div class="v play">${esc(a.fh_play)}</div></div>`:'')+`</div>`).join("");
    const body=(T.edge_line?`<div class="taxedge">💡 ${esc(T.edge_line)}</div>`:'')+pts+
      (arts?`<div class="incsub" style="margin-top:12px">📚 相關稅務文章<span class="t">點標題看原文</span></div>${arts}`:'')+
      (T.disclosure?`<div class="cdisc">⚠ ${esc(T.disclosure)}</div>`:'');
    h+=acc(`🧾 ${esc(T.title||'稅賦優勢')} ＋ 相關文章`, `${(T.points||[]).length} 點優勢／${(T.articles||[]).length} 篇文章 · 點開`, body, '', false);
  }
  return h;
}
// YouTube 分享：近一週影片提及，卡片式、可點看影片（預設收起）
function ytBlock(e){
  if(!e.youtube||!e.youtube.length) return '<div class="empty">近一週無 YouTube 提及。</div>';
  return `<div class="ytgrid">`+e.youtube.map(k=>`<a class="ytcard" href="${esc(k.url)}" target="_blank" rel="noopener">`+
    `<div class="yttop"><span class="ytbadge">▶</span><span class="ytsrc">${esc(k.source)}</span>${k.suspected_ad?'<span class="chip ad">疑似業配</span>':''}</div>`+
    `${k.summary?`<div class="ytsum">「${esc(k.summary)}」</div>`:''}<span class="ytgo">看影片 →</span></a>`).join("")+
    `</div><div class="note" style="margin-top:10px;border:0;padding:0">※ 近一週 YouTube 自動擷取（標發文日）；情緒/業配為推估，非指控，發布前自行查證。</div>`;
}

// 績效歸因（同日最新）：市況 + 持股異動 + 推漲/下跌 Top3 + 貢獻度排行（資料 ← fetch_fast 同日求鮮）
const sgn=v=>v==null?'':(v>=0?'up-pos':'dn'), pm=v=>v==null?'—':(v>=0?'+':'')+Number(v).toFixed(2)+'%';
function attribBlock(e){
  const fx=e.fast; if(!fx||(!fx.attribution&&!fx.holdings_diff&&!fx.market)) return "";
  const a=fx.attribution, hd=fx.holdings_diff, m=fx.market||{};
  const fresh=(fx.as_of&&fx.as_of===DATA.today)
    ?`<span class="fresh">🟡 同日最新 ${esc(fx.as_of)}</span>`
    :(fx.as_of?`<span class="badge">as-of ${esc(fx.as_of)}</span>`:'');
  const mline=(m.price!=null)?`<div class="mkline">市價 <b>${m.price}</b> <span class="${sgn(m.change_pct)}">${pm(m.change_pct)}</span>`+
    ` · NAV ${m.nav??'—'} · 折溢價 ${m.premium!=null?(m.premium>=0?'+':'')+m.premium+'%':'—'}`+
    ` · 規模 ${m.aum?(m.aum/1e8).toFixed(0)+' 億':'—'}${m.beneficiaries?' · 受益人 '+nf(m.beneficiaries)+' 人':''}</div>`:'';
  // ① 最新持股異動
  let diff="";
  const all=hd?[...(hd.cuts||[]),...(hd.adds||[]),...(hd.new||[])]:[];
  if(all.length){
    const lots=v=>(v==null?'—':Math.round(v/1000).toLocaleString());   // 股 → 張
    const wq=v=>(v==null?'—':Number(v).toFixed(2)+'%');
    const wcol=x=>`${wq(x.prev_weight)} → ${wq(x.weight)} <b class="${x.delta>=0?'up-pos':'dn'}">(${x.delta>=0?'+':''}${Number(x.delta).toFixed(2)}%)</b>`;
    // 真實買賣：張數有變動（經理人實際加減碼）
    const traded=all.filter(x=>x.share_delta!=null&&x.share_delta!==0)
                    .sort((a,b)=>Math.abs(b.share_delta)-Math.abs(a.share_delta));
    // 純價格帶動：張數未變、權重卻變（個股當日漲跌造成）
    const priced=all.filter(x=>x.share_delta===0)
                    .sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta)).slice(0,10);
    const trow=x=>{const sd=x.share_delta, isNew=(x.prev_shares===0||x.prev_shares==null)&&x.shares;
      const tg=isNew?['新進','new']:(sd>0?['加碼','add']:['減碼','cut']);
      return `<tr><td><span class="hchip ${tg[1]}">${tg[0]}</span></td>`+
        `<td class="l">${esc(x.name)} <small>${esc(x.code)}</small></td>`+
        `<td class="num">${lots(x.prev_shares)} → <b>${lots(x.shares)}</b> 張 <span class="${sd>=0?'up-pos':'dn'}">(${sd>=0?'+':''}${lots(sd)})</span></td>`+
        `<td class="num">${wcol(x)}</td></tr>`;};
    const prow=x=>`<tr><td><span class="hchip px">價格</span></td>`+
        `<td class="l">${esc(x.name)} <small>${esc(x.code)}</small></td>`+
        `<td class="num">${lots(x.shares)} 張（未變）</td><td class="num">${wcol(x)}</td></tr>`;
    const thead=`<tr><th>動作</th><th class="l">個股</th><th class="num">張數（昨→今）</th><th class="num">權重（昨→今）</th></tr>`;
    const tradedTbl=traded.length
      ? `<div class="alab" style="margin:8px 0 2px">🧑‍💼 經理人實際買賣（張數有變動）</div><div class="difwrap"><table class="difftbl">${thead}${traded.map(trow).join("")}</table></div>`
      : `<div class="empty" style="padding:6px 0">本日成分股張數未見變動（無實際加減碼，權重變化皆來自股價）。</div>`;
    const pricedTbl=priced.length
      ? acc('📈 純價格帶動的權重變化（張數未變）', `${priced.length} 檔 · 點開`,
            `<div class="difwrap"><table class="difftbl">${thead}${priced.map(prow).join("")}</table></div>`, '', false)
      : '';
    diff=`<div class="acard"><div class="alab">🔄 最新持股異動 <small>${esc(hd.prev_date||'')} → ${esc(hd.date||fx.as_of||'')} 快照比較</small></div>`+
      tradedTbl+pricedTbl+
      `<div class="attnote"><b>權重變化(%)＝今日權重−昨日權重</b>（為占 ETF 權重的百分點差）。權重同時受『張數加減碼（經理人買賣）』與『個股當日漲跌』影響：『經理人實際買賣』看<b>張數</b>（1 張＝1,000 股）；張數未變者，權重變動純由股價造成（例：南亞科今日 +7.46% 推升權重，但張數未動，非加碼）。</div></div>`;
  }
  // ①b 經理人持股操作 ＋ 為什麼（intel 編輯・換股快報式，常駐；續抱日也標、有實際換股時上方張數異動表並存）
  let swaps="";
  const SW=e.swaps;
  if(SW&&SW.rows&&SW.rows.length){
    const mvc=m=>m==='減碼'?'cut':(m==='加碼'?'add':'new');
    const srows=SW.rows.map(r=>{
      const news=(r.news||[]).map(n=>`<a class="lnk" href="${esc(n.url)}" target="_blank" rel="noopener">📰 ${esc(n.source||'來源')}${n.date?' '+esc(n.date):''}：${esc(n.title||'')}</a>`).join("");
      return `<div class="hncard ${mvc(r.move)}"><div class="hntop">`+
        `<span class="mv ${mvc(r.move)}">${esc(r.move)} ${esc(r.delta||'')}</span>`+
        `<b>${esc(r.name_zh)}</b>${r.name_en?`<small style="color:var(--mut)"> ${esc(r.name_en)}</small>`:''}${r.sector?`<span class="wtag">${esc(r.sector)}</span>`:''}</div>`+
        (r.why?`<div class="hnwhy">${esc(r.why)}</div>`:'')+
        (news?`<div class="links" style="margin-top:6px">${news}</div>`:'')+`</div>`;
    }).join("");
    swaps=`<div class="acard"><div class="alab">🔄 經理人持股操作 ＋ 為什麼這樣動 <small>${esc(SW.title||'')}</small></div>`+
      (SW.intro?`<div class="cdisc" style="margin-bottom:6px">${esc(SW.intro)}</div>`:'')+srows+
      (SW.disclosure?`<div class="attnote">⚠ ${esc(SW.disclosure)}</div>`:'')+`</div>`;
  }
  // ② 推漲/下跌 Top3 + 貢獻度排行
  let att="";
  if(a){
    const card=(r,dir)=>`<div class="mvcard ${dir}"><div class="mvtop"><b>${esc(r.code)}</b>${esc(r.name)}</div>`+
      `<div class="mvmid"><span class="${sgn(r.change_pct)}">${pm(r.change_pct)}</span> · 持股 ${r.weight}%</div>`+
      `<div class="mvbot">→ 對 ETF <b class="${sgn(r.contrib)}">${pm(r.contrib)}</b>${r.share!=null?` <small>（佔當日 ${r.share}%）</small>`:''}</div></div>`;
    const up=(a.up_top||[]).map(r=>card(r,'u')).join("")||'<div class="empty">—</div>';
    const dn=(a.down_top||[]).map(r=>card(r,'d')).join("")||'<div class="empty">—</div>';
    const rk=a.ranking||[], mx=Math.max(...rk.map(r=>Math.abs(r.contrib||0)),0.0001);
    const bars=rk.map(r=>{const w=Math.abs(r.contrib||0)/mx*100, p=(r.contrib||0)>=0;
      return `<div class="barrow"><span class="bcode">${esc(r.code)} <small>${esc((r.name||'').slice(0,5))}</small></span>`+
        `<span class="bwrap"><span class="bar ${p?'bp':'bn'}" style="width:${w.toFixed(0)}%"></span></span>`+
        `<span class="bval ${p?'up-pos':'dn'}">${pm(r.contrib)}</span></div>`;}).join("");
    const note=`<div class="attnote">ℹ️ 以 ${esc(fx.as_of||'')} 持股權重 × 成分股當日漲跌估算；ETF 當日 ${pm(a.etf_ret)}（成分貢獻合計 ${pm(a.est_ret)}，計入 ${a.n_priced}/${a.n_total} 檔）。實際 ETF 變動另受現金部位/折溢價/成分異動影響，僅供參考。</div>`;
    // 推漲/下跌 Top3 為主打（直接露出）；貢獻度排行（明細較長）收進可點開的折疊，預設收合。
    att=`<div class="attgrid"><div><div class="alab">📈 推漲 Top3</div>${up}</div>`+
      `<div><div class="alab">📉 下跌 Top3</div>${dn}</div></div>`+
      acc(`📊 貢獻度排行（前 ${rk.length} 檔）`, `${rk.length} 檔 · 點開看明細`, `<div class="bars">${bars}</div>${note}`, '', false);
  }
  const src=(fx.tier==='A')
    ? '官方即時(MIS)市價 + FHTrust 官方 NAV/持股，13:30 收盤後即更新（不必等晚間批次）'
    : 'etfinfo 第三方彙整 + 交易所即時(MIS)，Tier B 待核對';
  return `<div class="sec" style="border-color:var(--red)">⚡ 績效歸因 · 同日最新 ${fresh}`+
    `<span class="pill">${esc(src)}</span></div>${mline}${diff}${swaps}${att}`;
}

function renderETF(e){
  CUR=e;
  const s=e.stats;
  const asofToday=(e.mkt_date&&e.mkt_date===DATA.today);
  const chg=(e.change_pct!=null)?`<span class="${e.change_pct>=0?'up-pos':'dn'}" style="font-weight:800">${(e.change_pct>=0?'+':'')+(e.change_pct*100).toFixed(2)}%</span>`:'';
  const asof=e.mkt_date?`<div class="asof ${asofToday?'on':''}"><span class="lab">📅 價格基準日</span><span class="d">${esc(e.mkt_date)}</span>`+
    `${asofToday?'<span class="today">🟡 今日最新</span>':'<span class="stale">盤後待當日更新</span>'}`+
    `<span class="px">收 <b>${e.close??'—'}</b> ${chg}</span></div>`:'';
  const html=`
   <div class="etfhead"><h2>${esc(e.name)}（${e.id}）</h2>
     <div class="hdr">分析基準日 ${e.date}${(e.mkt_date&&e.date&&e.mkt_date>e.date)?`<span style="color:var(--amber)">（市價已更新至 ${esc(e.mkt_date)}；官方淨值最新為 ${esc(e.date)}、今日尚未公布）</span>`:''}　·　${esc(e.header)}</div></div>

   ${whatsnewBlock(e)}

   ${asof}

   ${e.income?`<div class="sec c4">💰 配息率 · 配息比較 · 持股變化＋國外新聞 · 稅賦優勢 <span class="pill">本檔為海外入息型，聚焦現金流／換股動向／稅務</span></div>${incomeBlock(e)}`:''}

   ${attribBlock(e)}

   ${e.perf?`<div class="sec">📊 多週期報酬 vs 同類主動＋0050 <span class="pill">本檔／各同類市價報酬／超額 vs 主動同類均 · 含息以月報為準</span></div>${perfTable(e.perf,e.id,DATA.today)}`:""}

   <div class="sec">⚡ 今日必看 <span class="pill">最值得先抓的重點（依重要度）· 點任一條看細節</span></div>
   ${hlStrip(e.data_cuts)}
   ${(e.youtube&&e.youtube.length)?acc('📺 YouTube 近一週討論',`${e.youtube.length} 部影片 · 點開觀看`,ytBlock(e),'g-yt',false):''}

   <div class="sec c2" style="margin-top:26px">📂 全部切點 · 依分類展開 <span class="pill">想看細節再點開</span></div>
   ${groupAcc(e.data_cuts)}
   ${acc('🥊 競品對比 · 我們好在哪','排行＋優勢',peerBlock(e),'g-vs')}
   ${acc('📊 競品切點掃描',`${e.scan.length} 檔`,scanBlock(e))}
   ${acc('💬 本檔話題 ＋ 口碑',`話題 ${s.topic}／口碑 ${s.voice}`,voiceBlock(e))}

   <div class="up">💡 <b>每天更新：</b>對話框輸入 <code>更新 ${e.id}</code> → 我會跑 fetch_peers 抓競品價量、讀 DB 第一手數據、做競品/口碑深析、重產本頁。${e.intel_note?'<br>⚠ '+esc(e.intel_note):''}</div>`;
  document.getElementById("panel").innerHTML=html;
  wire();
}

function bindCopy(root){root.querySelectorAll(".copybtn").forEach(b=>{if(b.dataset.b)return;b.dataset.b="1";b.onclick=()=>copyText(b.dataset.c,b);});}
function wire(){
  const panel=document.getElementById("panel");
  panel.querySelectorAll(".hlrow").forEach(r=>r.onclick=()=>{
    const i=r.dataset.hl, d=panel.querySelector('.hldetail[data-hld="'+i+'"]');
    const open=r.classList.toggle("open"); d.classList.toggle("open",open);
    if(open&&!d.dataset.filled){d.innerHTML=dataCard(CUR.data_cuts[i]);d.dataset.filled="1";bindCopy(d);}
  });
  panel.querySelectorAll(".acc>.ah").forEach(h=>h.onclick=()=>h.parentElement.classList.toggle("open"));
  bindCopy(panel);
}
function init(){
  document.getElementById("gen").textContent="產出時間 "+DATA.generated_at;
  if(!DATA.etfs.length){document.getElementById("panel").innerHTML="<p>尚無報告。</p>";return;}
  document.getElementById("tabs").innerHTML=DATA.etfs.map((e,i)=>`<div class="tab${i===0?' on':''}" data-i="${i}">${esc(e.short_name)}<small> ${e.id}</small></div>`).join("");
  document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{cur=+t.dataset.i;document.querySelectorAll(".tab").forEach(x=>x.classList.remove("on"));t.classList.add("on");renderETF(DATA.etfs[cur]);});
  document.getElementById("note").innerHTML="數據切點源於 TWSE 官方價量＋FHTrust 持股＋pipeline signals（第一手、可回溯）；競品 as-of/聲量/業配為 Tier B 推估，業配僅『疑似・推估』非指控；連結為查證入口，發布前請法遵複核。";
  renderETF(DATA.etfs[0]);
}
init();
</script>
</body>
</html>"""
