"""訊號總覽頁（dashboard/x9o.html＋每一次的清單 x9oh.json；docs/lab_signal_plan.md 第 5 節、規格 sigspec VER 1）。

由上而下：今天有效的好訊號（五個市場＋個股）→ 全部訊號與策略（搜尋、篩選、排序、點開看每一次、下載 CSV）→ 判定方式。
命中率讀研究檔（市場：data/lab/sig_research.json，scripts/run_sig.py；個股：data/lab/sig_stock.json，籌碼雷達建頁時寫）；
現在有沒有效每天算（景氣頁建頁時 sigcat.now_for_B 存進程序裡，這裡沿用；沒有就自己算）。只描述過去發生的比例。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import sigcat as G
from . import sigspec as S
from .heatpage import _e

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9o.html"
OUT_DATA = ROOT / "dashboard" / "x9oh.json"

CARDS: dict = {}                                   # 景氣頁建頁時放進來的四張研究卡（heatviz.stash_cards）：{市場: {"d", "crash", …}}
CARD_ORDER = ("crash", "bottom", "hotdd", "hotch")
CARD_NAMES = {"crash": "短線大跌風險", "bottom": "大跌後檢查", "hotdd": "過熱之後 3 個月的最大回撤", "hotch": "反向檢查"}
MK_NAMES = {**S.NAMES, "us": "美股產業", "stk": "個股"}
MK_ORDER = ("tw", "spx", "ixic", "ndx", "sox", "us", "stk")
TODAY_MK = ("tw", "spx", "ixic", "ndx", "sox")
H_TXT = {20: "1 個月", 60: "3 個月", 250: "12 個月"}


# ── 資料 ───────────────────────────────────────────────────────────────────

def _fallback_now(missing: list[str]) -> None:
    """景氣頁沒有在這個程序裡先建（例如單獨建這一頁）：自己載入景氣資料算現在的狀態。"""
    from . import heatcalc as HC
    from . import heatcalc_us as HU
    from . import heatspec as HS
    from . import heatspec_us as U
    if "tw" in missing:
        G.now_for_B(HC.build())
    us = [m for m in missing if m != "tw"]
    if us:
        D = HU.load()
        SH = HU.shared(D)
        for idx in us:
            B = HU.build(idx, D, SH)
            with HS.use(U.spec_for(idx)):
                G.now_for_B(B)


def view() -> dict:
    R = G.load_research() or {}
    ST = G.load_stock() or {}
    missing = [mk for mk in TODAY_MK if mk not in G.NOW]
    if missing and R:
        try:
            _fallback_now(missing)
        except Exception as e:                            # noqa: BLE001 —— 現在的狀態算不出來就只列研究結果
            print(f"[訊號總覽] 現在的狀態算不出來：{type(e).__name__}: {e}")
    rows = list(R.get("rows") or []) + list(ST.get("rows") or [])
    on: dict = {}
    asof: dict = {}
    for mk in TODAY_MK:
        n = G.NOW.get(mk)
        if n:
            on.update(n["on"])
            asof[mk] = n["d"]
    today = {mk: G.today(rows, on, mk) for mk in TODAY_MK if mk in asof}
    for r in ST.get("rows") or []:
        if r["cat"] == "stock" and r.get("live"):
            on[r["id"]] = {"live": r["live"]}
    stk = [r for r in ST.get("rows") or [] if r["tier"] == "good"
           and ((r["cat"] == "strat" and "ins" not in (r.get("pay") or {})) or r["id"] in on)]   # 整組研究版本只列在表裡
    if ST.get("d"):
        asof["stk"] = ST["d"]
    rmk = [mk for mk in TODAY_MK if mk in CARDS or (OUT_DATA.parent / f"x9or-{mk}.json").exists()]
    return {"rows": rows, "on": on, "today": today, "stk": stk, "asof": asof, "run": R.get("run"),
            "last": R.get("last") or {}, "rmk": rmk}


def _pct(v) -> float | None:
    return None if v is None else round(100.0 * v, 1)


def _stat(st: dict | None):
    if not st:
        return 0
    return [st.get("n") or 0, _pct(st.get("hit")), _pct(st.get("base")), st.get("n10"), _pct(st.get("hit10")),
            _pct(st.get("base10")), st.get("tier")]


def _row(r: dict) -> list:
    x = {"vn": r.get("vn"), "sig": r.get("sig"), "var": r.get("var")}
    for k in ("desc", "base_name", "old", "unit", "monthly", "few"):
        if r.get(k) is not None:
            x[k] = r[k]
    if r.get("pay"):
        x["pay"] = G._r(r["pay"])
    if r.get("up60") is not None:
        x["up60"] = _pct(r["up60"])
    if r.get("avg") is not None:
        x["avg"] = round(r["avg"], 2)
    th = r.get("th")
    return [r["id"], r["mk"], r["cat"], r.get("grp"), r["name"], r.get("kind"), r.get("H"),
            None if th is None else round(100 * th, 1), r["tier"], r["dir"], _stat(r.get("up")), _stat(r.get("warn")),
            _stat(r.get("buy")), r.get("a"), r.get("z"), x]


def page_json(V: dict) -> str:
    on = {}
    for k, v in V["on"].items():
        if "live" in v:
            on[k] = {"live": len(v["live"])}
        else:
            on[k] = {kk: v[kk] for kk in ("since", "n", "left", "event") if kk in v}
    out = {"rows": [_row(r) for r in V["rows"]], "on": on, "mk": MK_NAMES, "cat": G.CAT_NAMES,
           "asof": V["asof"], "tiers": {t: [S.TIER_MARK[t], S.TIER_NAMES[t]] for t in S.TIERS},
           "dirs": S.DIR_NAMES, "words": S.VARIANT_NAMES, "rmk": V.get("rmk") or [], "cards": CARD_NAMES}
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def detail_json(V: dict) -> str:
    """每一次的清單（點開才下載）＋個股代號的名稱。"""
    from . import store
    occ = {r["id"]: r.get("occ") or [] for r in V["rows"]}
    codes = {o[1] for r in V["rows"] if r["cat"] == "stock" for o in (r.get("occ") or [])}
    for r in V["rows"]:
        if r.get("live"):
            codes |= set(r["live"])
    nm = {**(store.read_json("names_hist.json", {}) or {}), **(store.read_json("names_mkt.json", {}) or {}),
          **(store.read_json("names.json", {}) or {})}
    live = {r["id"]: r["live"] for r in V["rows"] if r.get("live")}
    return json.dumps({"occ": occ, "names": {c: nm[c] for c in sorted(codes) if c in nm}, "live": live},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ── 頁面 ───────────────────────────────────────────────────────────────────

def _hz(r: dict) -> str:
    if r["cat"] == "buy":
        return "這一波"
    if r["cat"] == "ind":
        return "12 個月"
    return H_TXT.get(r.get("H"), f"{r.get('H')} 個交易日")


def _line(r: dict) -> str:
    """今天的重點一行：方向、命中率、平常、次數。"""
    d = r["d"]
    st = r[d]
    h = _hz(r)
    if d == "up":
        what = f"之後 {h}上漲" if r["cat"] != "stock" else "持有 20 個交易日賺錢"
    elif d == "warn":
        what = f"之後 {h}內跌 {_th(r['th'])}% 以上" if r.get("th") else "之後下跌"
    else:
        what = "買在這一波的相對低點"
    return (f'{what} <b>{st["hit"] * 100:.0f}%</b>（平常 {st["base"] * 100:.0f}%）・{st["n"]} 次')


def _d(d: str | None) -> str:
    """M/D（不帶星期，放在句子裡）。"""
    return f"{int(d[5:7])}/{int(d[8:10])}" if d else ""


def _th(th: float) -> str:
    v = th * 100
    return f"{v:.0f}" if abs(v - round(v)) < 1e-9 else f"{v:.1f}"


def _dy(d: str | None, ref: str | None) -> str:
    """M/D；和參考日不同年就加年份（2025/10/22）。"""
    if not d:
        return ""
    return _d(d) if ref and d[:4] == ref[:4] else f"{d[:4]}/{_d(d)}"


def _since(n: dict, ref: str | None = None) -> str:
    if n.get("left") is not None:
        return f'{_dy(n["since"], ref)} 出現，還看 {n["left"]} 天'
    if n.get("event"):
        return f'{_dy(n["since"], ref)} 出現'
    return f'{_dy(n["since"], ref)} 起'


def today_html(V: dict) -> str:
    cards = []
    for mk in TODAY_MK:
        T = V["today"].get(mk)
        if T is None:
            continue
        items = T["good"] or T["ref"]
        head = f'<h3>{_e(MK_NAMES[mk])}<span class="sub">資料到 {_e(_d(V["asof"].get(mk)))}</span></h3>'
        if not items:
            body = '<p class="sgnone">今天沒有判定為好訊號或可參考的訊號出現。</p>'
        else:
            pre = "" if T["good"] else '<p class="sgnone">今天沒有好訊號，以下是可參考的：</p>'
            lis = []
            for r in items:
                mark = S.TIER_MARK[r["tier"]]
                lis.append(f'<li><a class="sgi" href="#s={_e(r["id"])}"><span class="sgtk sgtk-{r["tier"]}">{mark}</span>'
                           f'<span class="sgnm">{_e(r["name"])}</span><span class="sgd sgd-{r["d"]}">{_e(S.DIR_NAMES[r["d"]])}</span>'
                           f'<span class="sgln">{_line(r)}<span class="sgs">{_e(_since(r["now"], V["asof"].get(mk)))}</span></span></a></li>')
            body = pre + '<ul class="sgl">' + "".join(lis) + "</ul>"
        cards.append(f'<div class="sgk">{head}{body}</div>')
    lis = []
    for r in V["stk"]:
        st = r["up"]
        if r["cat"] == "strat":
            p = r.get("pay") or {}
            ln = f'賺錢比例 <b>{st["hit"] * 100:.0f}%</b>'
            if p.get("path") == "上漲空間大" and p.get("ratio") is not None and p["ratio"] != float("inf"):
                ln += f'・賺賠比 {p["ratio"]:.1f}'
            ln += f'・每月平均 {p.get("m") or 0:+.1f}%・{st["n"]} 筆' + ("（次數少）" if r.get("few") else "")
        else:
            ln = f'持有 20 個交易日賺錢 <b>{st["hit"] * 100:.0f}%</b>・{st["n"]} 次'
        lis.append(f'<li><a class="sgi" href="#s={_e(r["id"])}"><span class="sgtk sgtk-good">★</span>'
                   f'<span class="sgnm">{_e(r["name"])}</span><span class="sgd sgd-up">{"策略" if r["cat"] == "strat" else "偏多"}</span>'
                   f'<span class="sgln">{ln}</span></a></li>')
    stk_body = ('<ul class="sgl">' + "".join(lis) + "</ul>") if lis else '<p class="sgnone">目前沒有判定為好策略的個股策略。</p>'
    cards.append(f'<div class="sgk"><h3>個股<span class="sub">資料到 {_e(_d(V["asof"].get("stk")))}</span></h3>{stk_body}'
                 '<p class="note">策略現在持有什麼、下一批什麼時候買，看<a href="x9.html">個股頁</a>機會分頁。</p></div>')
    return ('<section class="sec" id="today"><h2>今天有效的好訊號<span class="sub">同一個項目只列一種；依「比平常高多少」排序</span></h2>'
            f'<div class="sgt">{"".join(cards)}</div></section>')


METHOD = ('<section class="sec" id="mth"><details class="sgmth"><summary>判定方式</summary>'
          f'<p>每一個訊號都寫清楚「怎樣算出現」「怎樣算中了」「看多久」，算過去中了幾成（命中率），和「隨便哪一天」的比例（平常）比。</p>'
          f'<p><b>★ 好訊號</b>：至少 {S.N_MIN} 次；命中率 ≥ {S.HIT_MIN["up"] * 100:.0f}%（警示 ≥ {S.HIT_MIN["warn"] * 100:.0f}%）；'
          f'比平常高 {S.EDGE_GOOD * 100:.0f} 個百分點以上；近 {S.RECENT_YEARS} 年有 {S.RECENT_N} 次以上時，近 {S.RECENT_YEARS} 年也要過同樣的門檻。'
          f'<b>● 可參考</b>：至少 {S.N_MIN} 次、比平常高 {S.EDGE_REF * 100:.0f} 個百分點以上，但沒有全部達到。'
          f'<b>○</b>：沒有比平常好。<b>—</b>：不到 {S.N_MIN} 次，照列數字但不判定。</p>'
          '<p><b>偏多</b>：觸發隔天收盤買，看多久之後收盤比買價高。<b>警示</b>：觸發隔天收盤算起，看多久之內任一天收盤比那天低到門檻'
          '（台股 1 個月 8%、3 個月 10%；美股換算成和台股一樣常見；12 個月一律 20%）。<b>買點</b>：大跌之後，買在這一波的相對低點'
          '（事件前高點到之後最低收盤的下三分之一）。市場的訊號偏多、警示兩個方向都算，取比較好的那一個。</p>'
          '<p><b>看多久</b>：技術面與技術事件 1 個月；籌碼、資金、大跌風險、面向事件、邊際變化 3 個月；基本面與泡沫 12 個月。</p>'
          '<p><b>次數</b>：事件型（例：跌破季線）出現那天算一次，之後看多久的期間內再出現不算新的一次；狀態型（例：過熱中）'
          '狀態中的每一天都算，但同一段連續狀態只算 1 次，命中率是每一段先算、再平均。</p>'
          '<p><b>個股訊號</b>：同一檔 5 個交易日內重複只算一次，隔天開盤買、持有 20 個交易日，扣來回成本後賺錢算中；'
          '平常＝同一段期間加權指數上漲的比例（資料從 2026 年 7 月起，大多是上漲行情）。'
          f'<b>個股策略</b>：至少 {S.STRAT_N_MIN} 筆（不到 {S.STRAT_FEW} 筆標「次數少」，照樣判定），報酬型態過（賺錢比例 ≥ 60% 而且每月平均 ≥ 1%，'
          '或賺錢比例 ≥ 40%、賺賠比 ≥ 2.5、每月平均 ≥ 2%）＝★；平均每筆賺錢但沒過＝●。個股頁「機會」的推薦用這個判定。</p>'
          f'<p class="note">規格寫在 arm/lab/sigspec.py（VER {S.VER}），在算命中率之前寫定；改規格要升版本。只描述過去發生的比例。</p>'
          '</details></section>')

_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>訊號總覽</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<span class="asof">{{ASOF}}</span><a class="back" href="./">返回主頁</a></div>
<div class="vbar"><details class="purp"><summary>這頁怎麼看</summary><p>所有訊號與策略：出現之後，「中了」的比例（命中率）和隨便哪一天（平常）比。
★ 好訊號＝至少 10 次、命中率 ≥ 60%（警示 ≥ 50%）、比平常高 10 個百分點以上，近 10 年也成立。上面是今天有效的好訊號；
下面的表可以搜尋、篩選、排序，點一列看每一次的結果。</p></details></div>
<main>{{BODY}}</main>
<script type="application/json" id="sgd">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

TABLE = ('<section class="sec" id="all"><h2>全部訊號與策略<span class="sub" id="sgcnt"></span></h2>'
         '<div class="sgbar"><input id="sgq" type="search" placeholder="搜尋：名稱、代號（例：融資、RSI、季線）" autocomplete="off">'
         '<div class="sgchips" data-k="mk"></div><div class="sgchips" data-k="cat"></div>'
         '<div class="sgchips" data-k="tier"></div><div class="sgchips" data-k="dir"></div>'
         '<div class="sgopt"><label><input type="checkbox" id="sgnow"> 只看現在有效</label>'
         '<button type="button" id="sgcsv">下載 CSV</button></div></div>'
         '<div class="sgwrap"><table class="sgtb"><thead><tr>'
         '<th data-s="tier">判定</th><th data-s="name" class="l">訊號</th><th data-s="mk" class="dsk">市場</th>'
         '<th class="dsk">方向</th><th class="dsk">看多久</th><th data-s="n">次數</th><th data-s="hit">命中率</th>'
         '<th class="dsk">平常</th><th data-s="edge">差</th><th class="dsk">近 10 年</th><th data-s="now" class="dsk">現在</th>'
         '</tr></thead><tbody id="sgbody"></tbody></table></div>'
         '<p class="sgmore"><button type="button" id="sgmore" hidden></button></p></section>')


def research_html(V: dict) -> str:
    """研究細節：原本在景氣頁的四張研究卡（2026-10-19 起搬到這裡，docs/lab_signal_plan.md 第 10 節 Q3），每個市場一個檔、點了才載入。"""
    rmk = V.get("rmk") or []
    if not rmk:
        return ""
    chips = "".join(f'<button type="button" class="sgch" data-r="{mk}">{_e(MK_NAMES[mk])}</button>' for mk in rmk)
    names = "、".join(CARD_NAMES[c] for c in CARD_ORDER)
    return ('<section class="sec" id="research"><h2>研究細節<span class="sub">原本在景氣頁的研究卡：' + _e(names) + '</span></h2>'
            f'<div class="sgchips" id="rmk">{chips}</div>'
            '<div id="rbox"><p class="note">選一個市場，載入那個市場的四張研究卡。訊號點開之後的「相關研究」也會連到這裡。</p></div></section>')


def card_json(mk: str, c: dict) -> str:
    """一個市場的四張卡，各自收在一個 <details>（點開才展開；#r=市場:卡 會打開那一張）。"""
    html = "".join(f'<details class="sgrc" id="rc-{k}"><summary>{_e(CARD_NAMES[k])}</summary>{c[k]}</details>'
                   for k in CARD_ORDER if c.get(k))
    return json.dumps({"mk": mk, "d": c.get("d"), "html": html}, ensure_ascii=False, separators=(",", ":"))


def render(V: dict) -> str:
    from . import appnav
    from . import bottompage as BP
    from . import crashpage as CP
    from . import heatviz as VZ
    from . import hotchpage as QP
    from . import hotddpage as XP
    from .heatpage import _CSS as HCSS
    grp: dict = {}
    for mk, d in V["asof"].items():
        if d:
            grp.setdefault("台股" if mk == "tw" else ("個股" if mk == "stk" else "美股"), set()).add(d)
    asof = "、".join(f'{k} {"／".join(_d(x) for x in sorted(v))}' for k, v in grp.items())
    body = today_html(V) + TABLE + research_html(V) + METHOD
    if not V["rows"]:
        body = '<p class="warn">還沒有研究結果（scripts/run_sig.py）。</p>'
    return (_HTML.replace("{{APPTAB}}", appnav.bar("sig")).replace("{{CSS}}", HCSS + appnav.CSS + VZ.CSS + CP.CSS + XP.CSS + QP.CSS + BP.CSS + CSS)
            .replace("{{ASOF}}", _e(("資料到 " + asof) if asof else "")).replace("{{BODY}}", body)
            .replace("{{DATA}}", page_json(V)).replace("{{JS}}", JS))


def build(out: Path = OUT, data_out: Path = OUT_DATA) -> bool:
    V = view()
    changed = False
    files = [(data_out.parent / f"x9or-{mk}.json", card_json(mk, c)) for mk, c in sorted(CARDS.items())]
    for path, text in files + [(data_out, detail_json(V)), (out, render(V))]:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        changed = True
    return changed


CSS = """
.vbar{max-width:1080px;margin:2px auto 6px;padding:0 16px}
.sgt{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.sgk{border:1px solid var(--line);border-radius:12px;padding:10px 12px;background:var(--panel);min-width:0}
.sgk h3{margin:0 0 6px;font-size:15.5px}.sgk h3 .sub{font-weight:400;font-size:12px;color:var(--mut);margin-left:6px}
.sgl{list-style:none;margin:0;padding:0}.sgl li+li{border-top:1px solid var(--line)}
.sgi{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 6px;padding:6px 0;color:var(--ink);text-decoration:none}
.sgi:hover .sgnm{text-decoration:underline}
.sgnm{font-weight:600;font-size:14px}.sgln{flex:1 1 100%;font-size:12.5px;color:var(--ink2);padding-left:20px}
.sgln b{color:var(--ink)}.sgs{color:var(--mut);margin-left:6px}
.sgnone{font-size:13px;color:var(--ink2);margin:4px 0}
.sgtk{display:inline-block;width:14px;text-align:center;font-weight:700}
.sgtk-good{color:var(--acc)}.sgtk-ref{color:var(--ink2)}.sgtk-none,.sgtk-few{color:var(--mut)}
.sgd{font-size:11.5px;padding:0 7px;border-radius:999px;border:1px solid var(--line2);white-space:nowrap}
.sgd-up{color:var(--t4);border-color:var(--t4)}.sgd-warn{color:var(--t3);border-color:var(--t3)}.sgd-buy{color:var(--p0);border-color:var(--p0)}
.sgbar{display:flex;flex-direction:column;gap:6px;margin:6px 0 10px}
#sgq{font:inherit;font-size:14.5px;padding:7px 10px;border:1px solid var(--line2);border-radius:9px;background:var(--bg);color:var(--ink);max-width:420px}
.sgchips{display:flex;flex-wrap:wrap;gap:4px}
.sgch{font:inherit;font-size:12.5px;padding:2px 9px;border-radius:999px;border:1px solid var(--line2);background:var(--bg);color:var(--ink2);cursor:pointer}
.sgch.on{background:var(--accbg);border-color:var(--acc);color:var(--ink);font-weight:600}
.sgch i{font-style:normal;color:var(--mut);margin-left:3px;font-size:11.5px}
.sgopt{display:flex;gap:14px;align-items:center;font-size:13px;flex-wrap:wrap}
.sgopt button,.sgmore button{font:inherit;font-size:13px;padding:3px 10px;border:1px solid var(--line2);border-radius:8px;background:var(--bg);color:var(--ink);cursor:pointer}
.sgwrap{overflow-x:auto}
.sgtb{width:100%;border-collapse:collapse;font-size:13px}
.sgtb th{font-weight:600;color:var(--ink2);text-align:right;padding:5px 6px;border-bottom:1px solid var(--line2);white-space:nowrap}
.sgtb th[data-s]{cursor:pointer}.sgtb th.sorted::after{content:" ↓";color:var(--acc)}.sgtb th.sorted.asc::after{content:" ↑"}
.sgtb td{padding:5px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}
.sgtb th.l,.sgtb td.l{text-align:left;white-space:normal}
.sgtb tr.sgr{cursor:pointer}.sgtb tr.sgr:hover td{background:var(--card2)}.sgtb tr.sgr.open td{background:var(--card2)}
.sgtb td.l .sgm{display:none;font-size:11.5px;color:var(--mut)}
.sgtb td.tk{text-align:center;font-size:14px}
.sgtb td.now{color:var(--acc);font-size:12px}
.sgtb tr.sgdet td{white-space:normal;text-align:left;background:var(--panel);padding:8px 10px 14px}
.sgdl{font-size:13px;line-height:1.7;margin:0 0 6px}.sgdl b{font-weight:600}
.sgst{list-style:none;margin:4px 0 8px;padding:0;font-size:13px;line-height:1.7}.sgst li+li{margin-top:2px}
.sgoc{font-size:12.5px;margin:4px 0 0}.sgoc h4{font-size:13px;margin:6px 0 4px}
.sgol{display:flex;flex-wrap:wrap;gap:3px 6px;margin:0;padding:0;list-style:none}
.sgol li{padding:1px 6px;border-radius:6px;background:var(--card2);white-space:nowrap}
.sgol li.y{background:var(--accbg)}.sgol li .x{color:var(--mut)}
.sgmore{text-align:center}
.sgrc{border:1px solid var(--line);border-radius:12px;margin:8px 0;background:var(--panel)}
.sgrc>summary{cursor:pointer;padding:10px 14px;font-weight:600;font-size:15px;list-style:none}
.sgrc>summary::-webkit-details-marker{display:none}.sgrc>summary::before{content:"▸ ";color:var(--mut)}.sgrc[open]>summary::before{content:"▾ "}
.sgrc>section{margin:0;padding:0 4px 4px}
#rmk{margin:4px 0 8px}
.sgmth p{font-size:13.5px;line-height:1.75}
@media (max-width:900px){.sgt{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.sgt{grid-template-columns:minmax(0,1fr)}.sgtb .dsk{display:none}.sgln{padding-left:0}
 .sgtb td.l{min-width:150px}.sgwrap{overflow-x:visible}.sgtb td.l .sgm{display:block}
 .sgchips{flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px}.sgch{flex:0 0 auto}}
"""

JS = r"""
(function(){
const SG = JSON.parse(document.getElementById('sgd').textContent);
const ROWS = SG.rows, ON = SG.on;
const I = {id:0,mk:1,cat:2,grp:3,name:4,kind:5,H:6,th:7,tier:8,dir:9,up:10,warn:11,buy:12,a:13,z:14,x:15};
const TORD = {good:0, ref:1, none:2, few:3};
const MKO = ['tw','spx','ixic','ndx','sox','us','stk'];
const HT = {20:'1 個月',60:'3 個月',250:'12 個月'};
const st = {q:'', mk:'', cat:'', tier:'', dir:'', now:false, sort:'tier', asc:false, limit:100};
let OCC = null, OCCP = null;
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pc = v => v == null ? '—' : Math.round(v) + '%';
const md = d => d ? (+d.slice(5,7)) + '/' + (+d.slice(8,10)) : '';
const YR = Object.values(SG.asof || {}).filter(Boolean).sort().pop() || '';
const mdy = d => d ? (d.slice(0,4) === YR.slice(0,4) ? md(d) : d.slice(0,4) + '/' + md(d)) : '';
const ymd = d => d ? d.slice(0,4) + '/' + (+d.slice(5,7)) + '/' + (+d.slice(8,10)) : '';
function sd(r){ const d = r[I.dir][0]; return [d, r[d === 'up' ? I.up : d === 'warn' ? I.warn : I.buy]]; }
function edge(r){ const s = sd(r)[1]; return s && s[1] != null && s[2] != null ? s[1] - s[2] : null; }
function hz(r){ const c = r[I.cat]; if (c === 'buy') return '這一波'; if (c === 'ind') return '12 個月';
  if (c === 'strat') return '照規則'; return HT[r[I.H]] || (r[I.H] + ' 個交易日'); }
function nowTxt(r){ const n = ON[r[I.id]]; if (!n) return '';
  if (n.live != null) return '今天 ' + n.live + ' 檔';
  if (n.left != null) return mdy(n.since) + ' 出現・還看 ' + n.left + ' 天';
  if (n.event) return mdy(n.since) + ' 出現';
  return '有效・' + mdy(n.since) + ' 起'; }
function dirName(r){ return r[I.dir].map(d => r[I.cat] === 'strat' ? '策略' : SG.dirs[d]).join('、'); }
function hay(r){ const x = r[I.x] || {}; return (r[I.name] + ' ' + r[I.id] + ' ' + (x.vn || '') + ' ' + (x.var || '') + ' ' +
  SG.mk[r[I.mk]] + ' ' + SG.cat[r[I.cat]]).toLowerCase(); }
const HAY = ROWS.map(hay);
function pass(r, i, skip){
  if (st.q && !st.q.split(/\s+/).every(w => HAY[i].includes(w))) return false;
  if (skip !== 'mk' && st.mk && r[I.mk] !== st.mk) return false;
  if (skip !== 'cat' && st.cat && r[I.cat] !== st.cat) return false;
  if (skip !== 'tier' && st.tier && r[I.tier] !== st.tier) return false;
  if (skip !== 'dir' && st.dir && !r[I.dir].includes(st.dir)) return false;
  if (st.now && !ON[r[I.id]]) return false;
  return true; }
function key(r){
  switch (st.sort) {
    case 'name': return r[I.name];
    case 'mk': return MKO.indexOf(r[I.mk]);
    case 'n': return (sd(r)[1] || [0])[0];
    case 'hit': return (sd(r)[1] || [])[1] ?? -1;
    case 'edge': return edge(r) ?? -999;
    case 'now': return ON[r[I.id]] ? 1 : 0;
    default: return -TORD[r[I.tier]] * 1000 + (edge(r) ?? -99); } }
function sorted(list){
  const dir = st.asc ? 1 : -1;
  return list.slice().sort((a, b) => { const ka = key(a), kb = key(b);
    if (ka < kb) return -dir; if (ka > kb) return dir; return a[I.id] < b[I.id] ? -1 : 1; }); }
function chips(){
  const defs = {mk: MKO.map(k => [k, SG.mk[k]]), cat: Object.entries(SG.cat), tier: Object.entries(SG.tiers).map(([k, v]) => [k, v[0] + ' ' + v[1]]),
    dir: [['up','偏多'],['warn','警示'],['buy','買點']]};
  document.querySelectorAll('.sgchips[data-k]').forEach(box => {
    const k = box.dataset.k;
    const cnt = {}; ROWS.forEach((r, i) => { if (!pass(r, i, k)) return;
      const vs = k === 'dir' ? r[I.dir] : [r[I[k]]]; vs.forEach(v => { cnt[v] = (cnt[v] || 0) + 1; }); });
    const all = Object.values(cnt).reduce((a, b) => a + b, 0);
    box.innerHTML = '<button type="button" class="sgch' + (st[k] ? '' : ' on') + '" data-v="">全部</button>' +
      defs[k].filter(([v]) => cnt[v] || st[k] === v).map(([v, nm]) => '<button type="button" class="sgch' + (st[k] === v ? ' on' : '') +
        '" data-v="' + v + '">' + esc(nm) + '<i>' + (cnt[v] || 0) + '</i></button>').join('');
    box.onclick = e => { const b = e.target.closest('.sgch'); if (!b) return; st[k] = b.dataset.v; st.limit = 100; draw(); }; }); }
function statCell(s){ return s ? pc(s[1]) : '—'; }
function rowHtml(r){
  const [d, s] = sd(r), e = edge(r), t = SG.tiers[r[I.tier]];
  const x = r[I.x] || {}, n = s ? s[0] : 0;
  const r10 = s && s[3] ? pc(s[4]) + '／' + pc(s[5]) + '（' + s[3] + '）' : '—';
  const meta = SG.mk[r[I.mk]] + '・' + SG.cat[r[I.cat]] + '・' + dirName(r) + '・' + hz(r) + (nowTxt(r) ? '・' + nowTxt(r) : '');
  return '<tr class="sgr" data-id="' + esc(r[I.id]) + '"><td class="tk"><span class="sgtk sgtk-' + r[I.tier] + '" title="' + t[1] + '">' + t[0] + '</span></td>' +
    '<td class="l">' + esc(r[I.name]) + '<span class="sgm">' + esc(meta) + '</span></td><td class="dsk">' + esc(SG.mk[r[I.mk]]) + '</td>' +
    '<td class="dsk">' + r[I.dir].map(dd => '<span class="sgd sgd-' + dd + '">' + (r[I.cat] === 'strat' ? '策略' : SG.dirs[dd]) + '</span>').join(' ') + '</td>' +
    '<td class="dsk">' + hz(r) + '</td><td>' + n + '</td><td>' + statCell(s) + '</td><td class="dsk">' + (s ? pc(s[2]) : '—') + '</td>' +
    '<td>' + (e == null ? '—' : (e >= 0 ? '+' : '') + Math.round(e)) + '</td><td class="dsk">' + r10 + '</td>' +
    '<td class="dsk now">' + esc(nowTxt(r)) + '</td></tr>'; }
function draw(){
  chips();
  const list = sorted(ROWS.filter((r, i) => pass(r, i)));
  document.getElementById('sgcnt').textContent = '共 ' + list.length + ' 個' + (list.length > st.limit ? '，先列前 ' + st.limit + ' 個' : '');
  document.getElementById('sgbody').innerHTML = list.slice(0, st.limit).map(rowHtml).join('');
  const mb = document.getElementById('sgmore');
  mb.hidden = list.length <= st.limit; mb.textContent = '再列 ' + Math.min(200, list.length - st.limit) + ' 個（還有 ' + (list.length - st.limit) + ' 個）';
  document.querySelectorAll('.sgtb th[data-s]').forEach(th => { th.classList.toggle('sorted', th.dataset.s === st.sort); th.classList.toggle('asc', th.dataset.s === st.sort && st.asc); });
  if (OPEN) { const tr = document.querySelector('tr.sgr[data-id="' + CSS.escape(OPEN) + '"]'); if (tr) openRow(tr, true); } }
let OPEN = null;
const TRIG = {hot:'0～100 在 80 以上的每一天（同一段連續過熱算 1 次）', hot13:'已連續 13 週以上在 80 以上的每一天（同一段算 1 次）',
  hot_in:'從低於 80 升到 80 以上那一天（前 20 個交易日都低於 80）', hot_out:'連續過熱 4 週以上之後，第一個低於 80 的週末',
  cold:'0～100 低於 20 的每一天（同一段連續過冷算 1 次）', cold_in:'從 20 以上降到低於 20 那一天（前 20 個交易日都在 20 以上）'};
function trig(r){ const c = r[I.cat], x = r[I.x] || {}, nm = r[I.name];
  if (c === 'heat' || c === 'crash') return x.vn + '：' + TRIG[x.sig];
  if (c === 'multi') return x.sig === 'hot' ? '景氣頁的面向裡，同時 2 個以上在 80 以上的每一天（至少 3 個面向有值；同一段算 1 次）' : '從不到 2 個面向過熱，變成 2 個以上那一天';
  if (c === 'tech') return nm + '出現那一天（用指數收盤；轉折與均線的定義同景氣頁）';
  if (c === 'deriv') return x.vn + '的邊際變化是「' + nm.split('・').pop() + '」的每一天（看一階、二階的方向；同一段算 1 次）';
  if (c === 'bub') return '泡沫頁每月判定「' + nm + '」成立的月份（每個月最後一個交易日算一天；連續的月份算 1 次）';
  if (c === 'ind') return x.vn + '裡任何一個產業「' + nm.split('・').pop() + '」成立的月份（每個產業各自算，再合併）';
  if (c === 'buy') return nm.split('・')[0] + '之後，' + x.vn + '出現，隔天收盤買';
  return x.desc || ''; }
function succ(r, d){ const c = r[I.cat], h = hz(r), th = r[I.th];
  if (c === 'stock') return d === 'up' ? '隔天開盤買、持有 20 個交易日收盤賣，扣來回成本後賺錢；平常＝同一段期間加權指數上漲的比例'
    : '隔天開盤買，20 個交易日後收盤比買價低；平常＝同一段期間加權指數下跌的比例';
  if (c === 'strat') return '每一筆扣成本後賺錢的比例；判定看報酬型態（賺錢比例 ≥ 60% 而且每月平均 ≥ 1%，或賺錢比例 ≥ 40%、賺賠比 ≥ 2.5、每月平均 ≥ 2%）';
  if (c === 'buy') return '買在這一波的相對低點（事件前高點到之後最低收盤的下三分之一）；平常＝同一批事件「' + ((r[I.x] || {}).base_name || '') + '」';
  if (c === 'ind') return d === 'up' ? '訊號那個月底買，12 個月後的月底比買價高' : '訊號那個月底算起，12 個月內任一個月底比那時低 20% 以上';
  return d === 'up' ? '觸發隔天收盤買，' + h + '後收盤比買價高' : '觸發隔天收盤算起，' + h + '內任一天收盤比那天低 ' + th + '% 以上'; }
function statRows(r){
  const ds = r[I.cat] === 'buy' ? ['buy'] : (r[I.cat] === 'stock' || r[I.cat] === 'strat') ? [r[I.dir][0]] : ['up', 'warn'];
  return ds.map(d => { const s = r[d === 'up' ? I.up : d === 'warn' ? I.warn : I.buy]; if (!s) return '';
    const e = s[1] != null && s[2] != null ? s[1] - s[2] : null, t = SG.tiers[s[6]] || ['', ''];
    return '<li><span class="sgd sgd-' + d + '">' + (r[I.cat] === 'strat' ? '策略' : SG.dirs[d]) + '</span> <b>' + t[0] + ' ' + t[1] + '</b>：' +
      s[0] + ' 次，命中率 <b>' + pc(s[1]) + '</b>' + (s[2] != null ? '（平常 ' + pc(s[2]) + '，差 ' + (e >= 0 ? '+' : '') + Math.round(e) + ' 個百分點）' : '') +
      (s[3] ? '；近 10 年 ' + s[3] + ' 次，' + pc(s[4]) + '（平常 ' + pc(s[5]) + '）' : '') + '</li>'; }).join(''); }
function payTxt(x){ const p = x.pay; if (!p) return '';
  if (p.ins) { const f = (n, q) => q && q.n ? n + ' ' + q.n + ' 期：賺錢 ' + q.win + '%、賺賠比 ' + q.ratio + '、每期平均 ' + q.m + '%' + (q.pay_ok ? '（過）' : '（沒過）') : '';
    return [f('樣本內', p.ins), f('樣本外', p.oos)].filter(Boolean).join('；'); }
  const r1 = v => v == null ? '—' : (+v).toFixed(1);
  return '賺錢比例 ' + r1(p.win) + '%、賺賠比 ' + (p.ratio == null ? '—' : r1(p.ratio)) + '、平均每筆 ' + r1(p.avg) + '%、每月平均 ' + r1(p.m) + '%、平均持有 ' + r1(p.hm) + ' 個月' +
    (p.ok ? '（報酬型態過，' + (p.path || '') + '）' : '（報酬型態沒過）') + (x.few ? '；次數少（不到 30 筆，照樣判定）' : ''); }
function occHtml(r, oc){
  if (!oc || !oc.length) return '<p class="note">沒有每一次的清單。</p>';
  const c = r[I.cat], d = r[I.dir][0];
  let items, title;
  if (c === 'stock') { const nm = OCC.names || {};
    title = '每一次（最近 60 次；共 ' + oc.length + ' 次）';
    items = oc.slice(-60).reverse().map(o => '<li class="' + (o[2] ? 'y' : '') + '">' + md(o[0]) + ' ' + esc(o[1]) + ' ' + esc(nm[o[1]] || '') + ' <span class="x">' + (o[4] >= 0 ? '+' : '') + o[4] + '%</span></li>'); }
  else if (r[I.kind] === 'state' && c !== 'buy') {
    const j = d === 'warn' ? 4 : 3;
    title = '每一段（最近 40 段；共 ' + oc.length + ' 段）：起訖、天數、這一段中了的比例';
    items = oc.slice(-40).reverse().map(o => '<li class="' + (o[j] >= 0.5 ? 'y' : '') + '">' + ymd(o[0]) + (o[1] !== o[0] ? '～' + ymd(o[1]) : '') + ' <span class="x">' + o[2] + (r[I.x] && r[I.x].monthly ? ' 個月' : ' 天') + '</span> ' + Math.round(o[j] * 100) + '%</li>'); }
  else { const j = c === 'buy' ? 1 : (d === 'warn' ? 2 : 1);
    title = '每一次（最近 60 次；共 ' + oc.length + ' 次）：' + (c === 'buy' ? '✓＝買在相對低點' : '✓＝中了');
    items = oc.slice(-60).reverse().map(o => '<li class="' + (o[j] ? 'y' : '') + '">' + ymd(o[0]) + ' ' + (o[j] ? '✓' : '<span class="x">✗</span>') + '</li>'); }
  return '<div class="sgoc"><h4>' + title + '</h4><ul class="sgol">' + items.join('') + '</ul></div>'; }
function detHtml(r){
  const x = r[I.x] || {}, d = r[I.dir][0];
  let h = '<p class="sgdl"><b>怎樣算出現</b>：' + esc(trig(r)) + '</p>';
  const ds = r[I.cat] === 'buy' ? ['buy'] : (r[I.cat] === 'stock' || r[I.cat] === 'strat') ? [d] : ['up', 'warn'];
  h += ds.map(dd => '<p class="sgdl"><b>' + (r[I.cat] === 'strat' ? '怎樣算中了' : SG.dirs[dd] + '：怎樣算中了') + '</b>：' + esc(succ(r, dd)) + '</p>').join('');
  h += '<ul class="sgst">' + statRows(r) + '</ul>';
  if (x.pay) h += '<p class="sgdl">' + esc(payTxt(x)) + (x.old ? '（後台的 A／B／C 評級：' + esc(x.old) + '；機會頁的推薦用這裡的判定）' : '') + '</p>';
  if (x.up60 != null) h += '<p class="sgdl">另列：之後 60 日收盤比買價高的比例 ' + pc(x.up60) + '。</p>';
  if (r[I.a]) h += '<p class="sgdl note">資料期間 ' + ymd(r[I.a]) + '～' + ymd(r[I.z]) + '。</p>';
  const rl = rel(r); if (rl) h += '<p class="sgdl"><b>相關研究</b>：' + rl + '</p>';
  h += '<div class="sgocw">' + (OCC ? occHtml(r, OCC.occ[r[I.id]]) : '<p class="note">每一次的清單載入中…</p>') + '</div>';
  return h; }
function loadOcc(){ if (OCCP) return OCCP;
  OCCP = fetch('x9oh.json').then(x => x.json()).then(j => { OCC = j; return j; }).catch(() => { OCCP = null; return null; });
  return OCCP; }
function openRow(tr, keep){
  const id = tr.dataset.id, nx = tr.nextElementSibling;
  if (nx && nx.classList.contains('sgdet')) { if (keep) return; nx.remove(); tr.classList.remove('open'); OPEN = null; return; }
  document.querySelectorAll('tr.sgdet').forEach(e => e.remove()); document.querySelectorAll('tr.sgr.open').forEach(e => e.classList.remove('open'));
  const r = ROWS.find(x => x[I.id] === id); if (!r) return;
  OPEN = id; tr.classList.add('open');
  const det = document.createElement('tr'); det.className = 'sgdet'; det.innerHTML = '<td colspan="11">' + detHtml(r) + '</td>';
  tr.after(det);
  if (!OCC) loadOcc().then(j => { if (j && det.isConnected) det.querySelector('.sgocw').innerHTML = occHtml(r, j.occ[id]); }); }
document.getElementById('sgbody').addEventListener('click', e => { const tr = e.target.closest('tr.sgr'); if (tr) openRow(tr); });
document.querySelectorAll('.sgtb th[data-s]').forEach(th => th.addEventListener('click', () => {
  const s = th.dataset.s; if (st.sort === s) st.asc = !st.asc; else { st.sort = s; st.asc = s === 'name' || s === 'mk'; } draw(); }));
let qt = null;
document.getElementById('sgq').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { st.q = e.target.value.trim().toLowerCase(); st.limit = 100; draw(); }, 150); });
document.getElementById('sgnow').addEventListener('change', e => { st.now = e.target.checked; st.limit = 100; draw(); });
document.getElementById('sgmore').addEventListener('click', () => { st.limit += 200; draw(); });
document.getElementById('sgcsv').addEventListener('click', () => {
  const list = sorted(ROWS.filter((r, i) => pass(r, i)));
  const head = ['判定','訊號','市場','類別','方向','看多久','次數','命中率','平常','差','近10年次數','近10年命中率','近10年平常','現在','代號'];
  const lines = [head].concat(list.map(r => { const [d, s] = sd(r), e = edge(r);
    return [SG.tiers[r[I.tier]][1], r[I.name], SG.mk[r[I.mk]], SG.cat[r[I.cat]], dirName(r), hz(r), s ? s[0] : '', s ? s[1] : '', s ? s[2] : '',
      e == null ? '' : e.toFixed(1), s ? (s[3] ?? '') : '', s ? (s[4] ?? '') : '', s ? (s[5] ?? '') : '', nowTxt(r), r[I.id]]; }));
  const csv = '﻿' + lines.map(l => l.map(v => { const t = String(v == null ? '' : v); return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; }).join(',')).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'})); a.download = '訊號總覽.csv'; a.click(); });
const RMK = SG.rmk || [], RCACHE = {};
function loadR(mk, card){
  const box = document.getElementById('rbox'); if (!box || !RMK.includes(mk)) return;
  document.querySelectorAll('#rmk .sgch').forEach(b => b.classList.toggle('on', b.dataset.r === mk));
  const show = h => { box.innerHTML = h; if (card) { const el = document.getElementById('rc-' + card); if (el) { el.open = true; el.scrollIntoView({block: 'start'}); } } };
  if (RCACHE[mk]) { show(RCACHE[mk]); return; }
  box.innerHTML = '<p class="note">' + esc(SG.mk[mk]) + ' 的研究卡載入中…</p>';
  fetch('x9or-' + mk + '.json').then(x => x.json()).then(j => { RCACHE[mk] = j.html || '<p class="note">這個市場沒有研究卡。</p>'; show(RCACHE[mk]); })
    .catch(() => { box.innerHTML = '<p class="note">載入失敗，請重新整理。</p>'; }); }
const rm = document.getElementById('rmk');
if (rm) rm.addEventListener('click', e => { const b = e.target.closest('.sgch'); if (b) loadR(b.dataset.r); });
function rel(r){ const c = r[I.cat], x = r[I.x] || {}, mk = r[I.mk], out = [];
  if (c === 'bub') return '<a href="x9b.html#' + mk + '">泡沫頁（' + esc(SG.mk[mk]) + '）</a>';
  if (c === 'ind') return '<a href="x9b.html#ind">泡沫頁・產業</a>';
  if (!RMK.includes(mk)) return '';
  if (c === 'crash') out.push('crash'); else if (c === 'buy') out.push('bottom'); else if (c === 'multi') out.push('hotdd');
  else if (c === 'tech') out.push('hotch');
  else if (c === 'heat') { if (['hot_in', 'hot_out', 'hot13'].includes(x.sig)) out.push('hotdd');
    if (x.sig === 'hot13' && ['chip', 'sent'].includes(r[I.grp])) out.push('hotch'); }
  return out.map(k => '<a href="#r=' + mk + ':' + k + '">' + esc(SG.cards[k]) + '（' + esc(SG.mk[mk]) + '）</a>').join('、'); }
function fromHash(){ const rr = location.hash.match(/^#r=(\w+)(?::(\w+))?$/);
  if (rr) { loadR(rr[1], rr[2]); const sec = document.getElementById('research'); if (sec && !rr[2]) sec.scrollIntoView({block: 'start'}); return; }
  const m = location.hash.match(/^#s=(.+)$/); if (!m) return;
  const id = decodeURIComponent(m[1]); const r = ROWS.find(x => x[I.id] === id); if (!r) return;
  st.q = ''; document.getElementById('sgq').value = ''; st.mk = r[I.mk]; st.cat = r[I.cat]; st.tier = ''; st.dir = ''; st.now = false;
  document.getElementById('sgnow').checked = false; OPEN = id; st.limit = 100;
  const list = sorted(ROWS.filter((x, i) => pass(x, i))); const k = list.indexOf(r); if (k >= st.limit) st.limit = k + 1;
  draw(); const tr = document.querySelector('tr.sgr[data-id="' + CSS.escape(id) + '"]'); if (tr) tr.scrollIntoView({block: 'center'}); }
window.addEventListener('hashchange', fromHash);
draw(); fromHash();
})();
"""
