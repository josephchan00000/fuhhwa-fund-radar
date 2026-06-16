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
from datetime import datetime
from pathlib import Path

from . import firsthand
from .copy import baseline, parse

ROOT = Path(__file__).resolve().parents[1]
INTEL_DIR = ROOT / "reports" / "intel"

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


def _data_cuts(f: dict, etf: str) -> list[dict]:
    """本檔第一手數據 → 切點建議卡（皆來自 DB 真數字）。"""
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
    d = f.get("delta") or {}
    if d.get("adds"):
        adds = "、".join(f"{n} {w:+.2f}%" for n, w in d["adds"][:5])
        cutss = "、".join(f"{n} {w:+.2f}%" for n, w in (d.get("cuts") or [])[:3])
        cuts.append({"icon": "🔧", "label": "經理人加減碼", "type": "經理人選股理念",
            "priority": 86,
            "tldr": f"經理人加碼 {d['adds'][0][0]} 等 {len(d['adds'])} 檔",
            "fact": f"加碼：{adds}" + (f"｜減碼：{cutss}" if cutss else "") + f"（{d.get('prev_date')}→{d.get('date')}）",
            "suggest": "從加碼方向歸納題材（如 PCB/IC/記憶體）→『經理人今天做了什麼』換股快報",
            "example": f"【經理人加碼這些股！{etf} 主動換股押新動能（{d['adds'][0][0]} 領銜）】",
            "links": [_moneydj(etf), _etfinfo(etf)]})
    # signals → 切點卡（過濾退化訊號 + 用 evidence 補上實際數字）
    for s in f.get("signals", []):
        h = s.get("headline") or ""
        if "-0 張" in h or "＋0 張" in h or "+0 張" in h or "現權重 0.00" in h:
            continue
        det = s["detector"]
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
    if not key:
        return []
    try:
        from .connectors.social import youtube, base as sbase
        mentions = youtube.fetch(window_days=14)
    except Exception:
        return []
    out = []
    for m in mentions:
        if m.etfs and etf_id not in m.etfs:
            continue
        if (not m.etfs) and etf_id != "00991A":      # 泛論只掛主角，避免每頁重複
            continue
        try:
            a = sbase.analyze(m)
        except Exception:
            a = {"sentiment": "中性", "suspected_ad": False, "ad_terms": []}
        out.append({
            "source": f"YouTube · {m.author}", "kind": "KOL",
            "summary": (m.text or "")[:130],
            "intent": "YouTube 自動擷取（情緒/業配為 baseline 推估，待人工複核）",
            "sentiment": a.get("sentiment", "中性"),
            "suspected_ad": a.get("suspected_ad", False),
            "ad_reason": "、".join(a.get("ad_terms", [])) or "",
            "reusable": "", "fh_play": "", "url": m.url,
        })
    return out[:8]


def build_etf_model(etf_id: str, *, date=None) -> dict:
    doc = parse.parse_file(parse.latest_report(etf_id, date=date))
    f = firsthand.our_facts(etf_id)
    intel = _load_json(INTEL_DIR / f"{doc.date}_{doc.etf_id}.json")
    intel_src = "claude-deep" if intel else "baseline"

    data_cuts = _data_cuts(f, doc.etf_id)
    peers = firsthand.peer_table(etf_id)
    scan = firsthand.competitor_scan(etf_id)

    # 我們好在哪：signals 中的相對優勢 + drop-in edge
    edge_dets = {"BEAT_NAMED_PEERS", "PEER_CHAMPION", "UNIQUE_HOLDING", "LEAD_POSITION",
                 "ALPHA_BEAT", "BEAT_PEERS_MULTI"}
    edges = [{"point": s["headline"], "src": s["detector"]}
             for s in f.get("signals", []) if s["detector"] in edge_dets]
    edges = (intel.get("edge") or []) + edges

    # 口碑：YouTube 自動擷取（有金鑰）置頂 + Claude drop-in 深析
    voice = _youtube_voice(doc.etf_id) + (intel.get("voice") or [])

    return {
        "id": doc.etf_id, "name": doc.name, "short_name": baseline.short_name(doc.name),
        "date": doc.date, "header": doc.header, "is_nav": not f.get("volume"),
        "mkt_date": f.get("mkt_date"), "price_src": f.get("price_src"),
        "close": f.get("close"), "change_pct": f.get("change_pct"),
        "data_cuts": data_cuts, "perf": firsthand.perf_periods(doc.etf_id),
        "peers": peers, "scan": scan, "edges": edges,
        "competitor_notes": intel.get("competitor_notes") or {},
        "topic": intel.get("topic") or [], "voice": voice,
        "intel_src": intel_src, "intel_note": intel.get("note", ""),
        "stats": {"data": len(data_cuts), "peers": len(peers), "scan": len(scan),
                  "topic": len(intel.get("topic") or []), "voice": len(voice)},
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
<title>FH-ARM 每日切點素材雷達</title>
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
</style>
</head>
<body>
<div class="wrap">
  <header class="top"><h1>📡 FH-ARM 每日切點素材雷達</h1><span class="gen" id="gen"></span></header>
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
  return `<div class="dcard"><span class="type">${esc(d.type)}</span><div class="lab">${d.icon} ${esc(d.label)}</div>
    <div class="fact">${esc(d.fact)}</div>
    <div class="sug">💡 ${esc(d.suggest)}</div>${ex}
    <div class="links">${linkList(d.links)}</div></div>`;
}
function perfTable(p,me,today){
  if(!p||!p.rows||!p.rows.length) return "";
  const sg=v=>v==null?'':(v>=0?'up-pos':'dn'), pm=v=>v==null?'—':(v>=0?'+':'')+Number(v).toFixed(2)+'%';
  const bs=p.benches||[];
  const bhead=bs.map(b=>`<th>${esc((b.issuer||'')+b.label)}${b.is_index?'<small style="color:var(--mut)"> 基準</small>':''}</th>`).join("");
  const rows=p.rows.map(r=>`<tr>
    <td class="l">${esc(r.period)}</td>
    <td class="${sg(r.etf)}">${pm(r.etf)}</td>
    ${bs.map(b=>`<td style="color:var(--mut)">${pm(r.vals?r.vals[b.code]:null)}</td>`).join("")}
    <td class="${sg(r.excess)}">${pm(r.excess)}</td></tr>`).join("");
  const fresh=(today&&p.as_of===today)?`<span class="fresh">🟡 今日最新 ${esc(p.as_of)}</span>`:"";
  return `<table class="peer" style="margin-bottom:6px"><tr>
    <th class="l">期間</th><th>本檔 ${esc(me)}</th>${bhead}<th>超額 vs ${esc(p.peer_mean_label||'同類')}</th></tr>${rows}</table>
    <div style="color:var(--mut);font-size:11px;margin-bottom:16px">※ 市價報酬（含息以基金月報為準）· 超額＝本檔−主動同類均（不含 0050 基準）·　as-of ${esc(p.as_of)}${fresh}</div>`;
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
  return `<table class="peer"><tr><th class="l">同類ETF（量能高→低）</th><th>發行商</th><th>收盤(市價)</th><th>當日漲跌</th><th>成交量(股)</th></tr>${rows}</table>
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
  const voice=e.voice.length?e.voice.map(voiceRow).join(""):'<div class="empty">口碑 drop-in 待補（FB/IG/Threads/YT 抓取見對話說明）。</div>';
  return topic+`<div style="margin-top:12px">${voice}</div>`;
}

function renderETF(e){
  CUR=e;
  const s=e.stats;
  const mktFresh=(e.mkt_date&&e.mkt_date===DATA.today)
    ?`<span class="fresh">🟡 今日最新市價 ${esc(e.mkt_date)}${e.close!=null?`　收 ${e.close}${e.change_pct!=null?`（${(e.change_pct>=0?'+':'')+(e.change_pct*100).toFixed(2)}%）`:''}`:''}</span>`
    :(e.mkt_date?`<span class="badge">市價日 ${esc(e.mkt_date)}（盤後待當日更新）</span>`:'');
  const html=`
   <div class="etfhead"><h2>${esc(e.name)}（${e.id}）</h2>
     <div class="hdr">資料日 ${e.date}　·　${esc(e.header)}</div>
     <div class="badges"><span class="badge">${s.data} 數據切點</span><span class="badge">${s.scan} 競品掃描</span>
       <span class="badge">話題 ${s.topic}／口碑 ${s.voice}</span><span class="badge src">${SRC[e.intel_src]||e.intel_src}</span>${mktFresh}</div></div>

   ${e.perf?`<div class="sec">📊 多週期報酬 vs 同類主動＋0050 <span class="pill">本檔／各同類市價報酬／超額 vs 主動同類均 · 含息以月報為準</span></div>${perfTable(e.perf,e.id,DATA.today)}`:""}

   <div class="sec">⚡ 今日必看 <span class="pill">最值得先抓的重點（依重要度）· 點任一條看細節</span></div>
   ${hlStrip(e.data_cuts)}

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
