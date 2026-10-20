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

CARDS: dict = {}                                   # 景氣頁建頁時放進來的研究卡（heatviz.stash_cards）：{市場: {"d", "crash", …}}
ITEMS: dict = {}                                   # 景氣頁建頁時放進來的每項現在（heatviz.sig_items）：{市場: {指標: {...}}}
CARD_ORDER = ("crash", "bottom", "hotdd", "hotch")
CARD_NAMES = {"crash": "短線大跌風險", "bottom": "大跌後檢查", "hotdd": "過熱之後 3 個月的最大回撤",
              "hotch": "反向檢查"}
MK_NAMES = {**S.NAMES, "us": "美股產業", "stk": "個股"}
MK_ORDER = ("tw", "spx", "ixic", "ndx", "sox", "us", "stk")
TODAY_MK = ("tw", "spx", "ixic", "ndx", "sox")
H_TXT = {20: "1 個月", 60: "3 個月", 250: "12 個月"}
# 依指標整理（docs/lab_sigview_plan.md）：指標的類別、走勢圖的資料檔（景氣頁對照圖同一份）、指數名稱
IND_CATS = {"heat": "景氣項目", "dim": "景氣面向", "crash": "大跌風險", "tech": "技術事件", "bub": "泡沫", "ind": "產業泡沫",
            "buy": "大跌後買點", "stock": "個股訊號", "strat": "個股策略"}
CHART = {"tw": "x9mh.json", "spx": "x9muh-spx.json", "ixic": "x9muh-ixic.json", "ndx": "x9muh-ndx.json", "sox": "x9muh-sox.json"}
PX_NAMES = {"tw": "加權指數", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}


def ind_of(r: dict) -> tuple[str, str, str, str | None]:
    """一個訊號屬於哪個指標 → (指標鍵, 類別, 名稱, 景氣頁的項目鍵)。景氣項目的水準（heat）與邊際變化（deriv）同一個指標；
    面向＝D＋面向；泡沫每個市場一個（各條件是它的訊號）；產業泡沫每組一個；大跌後買點依大跌的種類；技術事件、個股訊號、策略各自一個。"""
    cat, mk, var = r["cat"], r["mk"], r.get("var")
    if cat in ("heat", "deriv"):
        if cat == "heat" and str(var).startswith("D") and var[1:] == r.get("grp"):
            return f"{mk}:{var}", "dim", r["vn"], var
        return f"{mk}:{var}", "heat", r["vn"], var
    if cat == "multi":
        return f"{mk}:{var}", "dim", r["vn"], None
    if cat == "crash":
        return f"{mk}:{var}", "crash", r["vn"], None
    if cat == "tech":
        return f"{mk}:tech:{var}", "tech", r["vn"], None
    if cat == "bub":
        return f"{mk}:bub", "bub", "泡沫等級與條件", None
    if cat == "ind":
        return f"ind:{r.get('grp')}", "ind", r["vn"], None
    if cat == "buy":
        return f"{mk}:buy:{r.get('grp')}", "buy", r["name"].split("・")[0], None
    return r["id"], cat, r.get("vn") or r["name"], None


def indicators(rows: list[dict]) -> list[list]:
    """依指標整理：[[指標鍵, 市場, 類別, 名稱, 面向, [這個指標的訊號在 rows 的位置], 景氣頁的項目鍵], …]（照 rows 出現的順序）。
    景氣項目的面向取水準那一列的 grp（邊際變化那一列是 deriv）。"""
    out: dict = {}
    for i, r in enumerate(rows):
        k, cat, nm, it = ind_of(r)
        x = out.get(k)
        if x is None:
            x = out[k] = [k, r["mk"], cat, nm, None, [], it]
        if r["cat"] in ("heat", "multi") and x[4] is None:
            x[4] = r.get("grp")
        x[5].append(i)
    return list(out.values())


def dim_names() -> dict:
    """{市場: {面向: 名稱}}（台股、四個美股指數）。"""
    from . import heatspec as HS
    from . import heatspec_us as U
    out = {"tw": {d: L["name"] for d, L in HS.DIMS.items()}}
    for idx in U.INDEX_ORDER:
        with HS.use(U.spec_for(idx)):
            out[idx] = {d: L["name"] for d, L in HS.DIMS.items()}
    return out


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
            "last": R.get("last") or {}, "rmk": rmk, "items": {mk: ITEMS[mk] for mk in TODAY_MK if mk in ITEMS}}


def _pct(v) -> float | None:
    return None if v is None else round(100.0 * v, 1)


def _stat(st: dict | None):
    if not st:
        return 0
    out = [st.get("n") or 0, _pct(st.get("hit")), _pct(st.get("base")), st.get("n10"), _pct(st.get("hit10")),
           _pct(st.get("base10")), st.get("tier")]
    if st.get("mdd") is not None or st.get("mdd_base") is not None:          # 警示（VER 3）：最大回撤中位數、平常
        out += [_pct(st.get("mdd")), _pct(st.get("mdd_base"))]
    return out


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
           "dirs": S.DIR_NAMES, "words": S.VARIANT_NAMES, "rmk": V.get("rmk") or [], "cards": CARD_NAMES,
           "inds": indicators(V["rows"]), "icat": IND_CATS, "it": V.get("items") or {}, "dimn": dim_names(),
           "chart": CHART, "pxn": PX_NAMES,
           "hit": {d: round(100 * v) for d, v in S.HIT_MIN.items()}, "eg": round(100 * S.EDGE_GOOD), "er": round(100 * S.EDGE_REF),
           "n10": S.RECENT_N}
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
    """今天的重點一行（白話，docs/lab_sigview_plan.md 第 2.3 節）：之後上漲（或大跌）的機率、隨便挑一天、出現過幾次。"""
    d = r["d"]
    st = r[d]
    h = _hz(r)
    if d == "up":
        what = f"之後 {h}上漲的機率" if r["cat"] != "stock" else "持有 20 個交易日賺錢的機率"
    elif d == "warn":
        h = "20 個交易日" if r["cat"] == "stock" else h
        what = f"之後 {h}內大跌（最大回撤 {_th(r['th'])}% 以上）的機率" if r.get("th") else "之後大跌的機率"
    else:
        what = "買在這一波相對低點的機率"
    out = f'{what} <b>{st["hit"] * 100:.0f}%</b>（隨便挑一天 {st["base"] * 100:.0f}%）・出現過 {st["n"]} 次'
    if d == "warn" and st.get("mdd") is not None and st.get("mdd_base") is not None:
        out += f'・回撤中位數 {st["mdd"] * 100:.0f}%（隨便挑一天 {st["mdd_base"] * 100:.0f}%）'
    return out


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
        d = r["dir"][0]
        st = r[d]
        if r["cat"] == "strat":
            p = r.get("pay") or {}
            ln = f'每筆賺錢的比例 <b>{st["hit"] * 100:.0f}%</b>'
            if p.get("path") == "上漲空間大" and p.get("ratio") is not None and p["ratio"] != float("inf"):
                ln += f'・賺賠比 {p["ratio"]:.1f}'
            ln += f'・每月平均 {p.get("m") or 0:+.1f}%・{st["n"]} 筆' + ("（次數少）" if r.get("few") else "")
        else:
            ln = _line({**r, "d": d})
        lis.append(f'<li><a class="sgi" href="#s={_e(r["id"])}"><span class="sgtk sgtk-good">★</span>'
                   f'<span class="sgnm">{_e(r["name"])}</span><span class="sgd sgd-{d}">{"策略" if r["cat"] == "strat" else _e(S.DIR_NAMES[d])}</span>'
                   f'<span class="sgln">{ln}</span></a></li>')
    stk_body = ('<ul class="sgl">' + "".join(lis) + "</ul>") if lis else '<p class="sgnone">目前沒有判定為好策略的個股策略。</p>'
    cards.append(f'<div class="sgk"><h3>個股<span class="sub">資料到 {_e(_d(V["asof"].get("stk")))}</span></h3>{stk_body}'
                 '<p class="note">策略現在持有什麼、下一批什麼時候買，看<a href="x9.html">個股頁</a>機會分頁。</p></div>')
    return ('<section class="sec" id="today"><h2>今天有效的好訊號<span class="sub">同一個項目只列一種；依「比隨便挑一天多幾個百分點」排序；點一列看那個指標</span></h2>'
            f'<div class="sgt">{"".join(cards)}</div></section>')


METHOD = ('<section class="sec" id="mth"><details class="sgmth"><summary>名詞與判定方式</summary>'
          '<p>每個指標有幾種訊號（例：RSI 的「過冷中」「進入過熱」）。每一種都寫清楚「怎樣算出現」「怎樣算中了」「看多久」，'
          '數過去出現之後中了幾成，和同一段期間「隨便挑一天」比。只描述過去發生的比例。</p><dl class="sgdl2">'
          '<dt>之後上漲的機率</dt><dd>偏多訊號：出現的隔天收盤買，過了「看多久」之後收盤比買價高的比例。例：台股 RSI 過冷中，之後 1 個月上漲的機率 81%。</dd>'
          '<dt>之後大跌的機率</dt><dd>警示訊號：出現的隔天收盤算起，「看多久」之內出現一段最大回撤到門檻的比例（最大回撤＝期間最高收盤到之後最低收盤的跌幅，'
          '先漲再跌也算）。門檻：台股 1 個月 8%、3 個月 10%；美股換算成和台股一樣常見；12 個月一律 20%。另列每一次最大回撤的中位數。</dd>'
          '<dt>買在相對低點的機率</dt><dd>大跌之後的買點：買進價落在這一波（事件前高點到之後最低收盤）下三分之一的比例。</dd>'
          '<dt>隨便挑一天</dt><dd>同一段期間裡隨便挑一天、用同樣算法的比例。訊號要比它高才有用——美股隨便挑一天，3 個月後上漲的機率就有六成多。</dd>'
          '<dt>多幾個百分點</dt><dd>機率減掉隨便挑一天。</dd>'
          f'<dt>近 10 年也成立嗎</dt><dd>只看最近 10 年：✓ 也達到好訊號的門檻；△ 比隨便挑一天多 {S.EDGE_REF * 100:.0f} 個百分點以上、但沒到好訊號的門檻；'
          f'✗ 沒有；— 近 10 年不到 {S.RECENT_N} 次，不看。</dd>'
          '<dt>出現過幾次</dt><dd>事件型（例：跌破季線）出現那天算一次，之後看多久的期間內再出現不算新的一次；狀態型（例：過熱中）'
          '連續的一段算一次，機率是每一段先算、再平均。</dd>'
          f'<dt>判定</dt><dd><b>★ 好訊號</b>：至少 {S.N_MIN} 次、機率 ≥ {S.HIT_MIN["up"] * 100:.0f}%（警示 ≥ {S.HIT_MIN["warn"] * 100:.0f}%）、'
          f'多 {S.EDGE_GOOD * 100:.0f} 個百分點以上、近 10 年也成立。<b>● 可參考</b>：至少 {S.N_MIN} 次、多 {S.EDGE_REF * 100:.0f} 個百分點以上。'
          f'<b>○</b>：沒有比隨便挑一天好。<b>—</b>：不到 {S.N_MIN} 次，照列數字但不判定。</dd>'
          '<dt>看多久</dt><dd>技術面與技術事件 1 個月；籌碼、資金、大跌風險、面向事件、邊際變化 3 個月；基本面與泡沫 12 個月。</dd></dl>'
          '<p><b>個股訊號</b>：同一檔 5 個交易日內重複只算一次，隔天開盤買、持有 20 個交易日，扣來回成本後賺錢算中；'
          '隨便挑一天＝同一段期間加權指數上漲的比例（資料從 2026 年 7 月起，大多是上漲行情）。'
          f'集體撤退是警示：之後 20 個交易日內最大回撤 {S.STOCK_MDD * 100:.0f}% 以上算中，隨便挑一天＝同一段期間所有 ETF 持股的同樣比例。'
          f'<b>個股策略</b>：至少 {S.STRAT_N_MIN} 筆（不到 {S.STRAT_FEW} 筆標「次數少」，照樣判定），報酬型態過（賺錢比例 ≥ 60% 而且每月平均 ≥ 1%，'
          '或賺錢比例 ≥ 40%、賺賠比 ≥ 2.5、每月平均 ≥ 2%）＝★；平均每筆賺錢但沒過＝●。個股頁「機會」的推薦用這個判定。</p>'
          f'<p class="note">規格寫在 arm/lab/sigspec.py（VER {S.VER}），在算機率之前寫定；改規格要升版本。</p>'
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
<div class="vbar"><details class="purp"><summary>這頁怎麼看</summary><p>上面是今天有效的好訊號；下面依指標列出全部
（例：RSI、融資餘額水位），點一個指標看它現在的數值、走勢，和它每一種訊號過去出現之後「上漲（或大跌）的機率」，
跟同一段期間「隨便挑一天」比。★ 好訊號＝至少 10 次、機率夠高、比隨便挑一天多 10 個百分點以上、近 10 年也成立。
名詞滑過 ⓘ 或看最下面「名詞與判定方式」。</p></details></div>
<main>{{BODY}}</main>{{PANEL}}
<script type="application/json" id="sgd">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

def _ii(k: str) -> str:
    """名詞旁的 ⓘ（滑過或點一下看一句說明；說明文字在 JS 的 TIP）。"""
    return f'<span class="sgq" tabindex="0" role="button" aria-label="說明" data-tip="{k}">ⓘ</span>'


TABLE = ('<section class="sec" id="all"><h2>全部指標<span class="sub" id="sgcnt"></span></h2>'
         '<p class="note">一列一個指標（例：RSI、融資餘額水位）；點一列看它現在的數值、走勢，和它每一種訊號過去出現之後的結果。</p>'
         '<div class="sgbar"><input id="sgq" type="search" placeholder="搜尋：指標名稱（例：融資、RSI、季線）" autocomplete="off">'
         '<div class="sgchips" data-k="mk"></div><div class="sgchips" data-k="cat"></div>'
         '<div class="sgchips" data-k="tier"></div><div class="sgchips" data-k="dir"></div>'
         '<div class="sgopt"><label><input type="checkbox" id="sgnow"> 只看現在有訊號的</label>'
         '<button type="button" id="sgcsv">下載 CSV（每一種訊號）</button></div></div>'
         '<div class="sgwrap"><table class="sgtb sgit"><thead><tr>'
         f'<th data-s="tier">判定 {_ii("tnow")}</th><th data-s="name" class="l">指標</th>'
         f'<th data-s="h" class="dsk">現在 {_ii("now")}</th><th class="dsk">近一年 {_ii("spark")}</th>'
         f'<th class="l dsk">現在成立的訊號 {_ii("p")}</th>'
         '</tr></thead><tbody id="sgbody"></tbody></table></div>'
         '<p class="sgmore"><button type="button" id="sgmore" hidden></button></p></section>')

PANEL = ('<div class="sgpv" id="sgpv" hidden><div class="sgpb" id="sgpb"></div>'
         '<aside class="sgp" id="sgp" role="dialog" aria-labelledby="sgpt" tabindex="-1"></aside></div>'
         '<div class="sgtip" id="sgtip" role="tooltip" hidden></div>')


def research_html(V: dict) -> str:
    """研究細節：原本在景氣頁的四張研究卡（2026-10-19 起搬到這裡，docs/lab_signal_plan.md 第 10 節 Q3），每個市場一個檔、點了才載入。"""
    rmk = V.get("rmk") or []
    if not rmk:
        return ""
    chips = "".join(f'<button type="button" class="sgch" data-r="{mk}">{_e(MK_NAMES[mk])}</button>' for mk in rmk)
    names = "、".join(CARD_NAMES[c] for c in CARD_ORDER)
    return ('<section class="sec" id="research"><h2>研究細節<span class="sub">' + _e(names) + '</span></h2>'
            f'<div class="sgchips" id="rmk">{chips}</div>'
            '<div id="rbox"><p class="note">選一個市場，載入那個市場的研究卡。訊號點開之後的「相關研究」也會連到這裡。</p></div></section>')


def card_json(mk: str, c: dict) -> str:
    """一個市場的研究卡，各自收在一個 <details>（點開才展開；#r=市場:卡 會打開那一張）。"""
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
            .replace("{{DATA}}", page_json(V)).replace("{{PANEL}}", PANEL).replace("{{JS}}", JS))


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
/* 依指標整理（docs/lab_sigview_plan.md） */
.sgit td.l .sgm{display:block}.sgin{font-weight:600;font-size:14px}
.sgit td{vertical-align:middle}.sgit td.ss{font-size:12.5px;color:var(--ink2);line-height:1.6;min-width:280px}.sgit td.ss b{color:var(--ink)}
.sgit .sgs{display:block;margin-left:0;font-size:11.5px}
.sgit td.nv{text-align:left;white-space:nowrap}.sgnv{display:block;font-size:13px;color:var(--ink)}.sgnz{display:block;font-size:12px;font-weight:600}
.sgsp{display:block;flex:none}.spk .sgsp{width:110px;height:26px}.sgmn .sgsp{width:76px;height:20px}.sgsp path{fill:none;stroke:var(--ink2);stroke-width:1.4}.sgsp line{stroke:var(--line2);stroke-dasharray:2 2}
.sgmob{display:none}
.sgq{display:inline-block;margin-left:2px;color:var(--acc);font-weight:400;font-size:12px;cursor:help;outline:none}
.sgq:focus-visible{outline:2px solid var(--acc);border-radius:4px}
.sgtip{position:fixed;z-index:80;background:var(--panel);color:var(--ink);border:1px solid var(--line2);border-radius:9px;padding:8px 10px;
 font-size:12.5px;line-height:1.6;box-shadow:0 6px 20px rgba(0,0,0,.18);pointer-events:none}
.sgpv{position:fixed;inset:0;z-index:60;pointer-events:none}
.sgpb{position:absolute;inset:0;background:rgba(10,14,22,.32);pointer-events:auto}
.sgp{position:absolute;top:0;right:0;bottom:0;width:min(700px,100%);background:var(--panel);box-shadow:-10px 0 28px rgba(0,0,0,.2);
 overflow-y:auto;pointer-events:auto;padding:0 16px 28px;outline:none;-webkit-overflow-scrolling:touch}
.sgph{position:sticky;top:0;z-index:3;background:var(--panel);display:flex;justify-content:space-between;align-items:flex-start;gap:10px;
 padding:12px 0 8px;border-bottom:1px solid var(--line)}
.sgph h3{margin:2px 0 0;font-size:18px}.sgkick{margin:0;font-size:12px;color:var(--mut)}
.sgx{font:inherit;font-size:22px;line-height:1;width:36px;height:36px;border-radius:9px;border:1px solid var(--line2);background:var(--bg);color:var(--ink);cursor:pointer;flex:none}
.sgpc h4{font-size:14.5px;margin:16px 0 6px}
.sgnow{display:flex;flex-wrap:wrap;gap:8px}
.sgnc{flex:1 1 120px;border:1px solid var(--line);border-radius:10px;padding:7px 10px;background:var(--card2);display:flex;flex-direction:column}
.sgnc .k{font-size:11.5px;color:var(--mut)}.sgnc .v{font-size:17px;font-weight:600}.sgnc .s{font-size:11.5px;color:var(--ink2)}
.sgonl{list-style:none;margin:8px 0 0;padding:0;font-size:13px;line-height:1.6}.sgonl li+li{margin-top:4px}.sgonl .sgs{display:block;margin-left:20px}
.sgcb{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 6px}
.sgseg{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.sgseg button{font:inherit;font-size:12.5px;padding:3px 10px;border:0;background:var(--bg);color:var(--ink2);cursor:pointer}
.sgseg button+button{border-left:1px solid var(--line2)}.sgseg button.on{background:var(--accbg);color:var(--ink);font-weight:600}
.sgcv{min-height:120px}.sgchart{display:block;max-width:100%;touch-action:pan-y}
.sgchart .lv{fill:none;stroke:var(--acc);stroke-width:1.6}.sgchart .lp{fill:none;stroke:var(--ink2);stroke-width:1.2}
.sgchart .tl{stroke:var(--line2);stroke-dasharray:4 3}.sgchart .ax{font-size:10.5px;fill:var(--mut)}
.sgchart .bd{fill:var(--acc)}.sgchart .bdn{fill:var(--acc);fill-opacity:.12;stroke:var(--acc);stroke-dasharray:3 3;stroke-width:1}
.sgchart .mk{fill:var(--panel);stroke:var(--t3);stroke-width:1.6}.sgchart .mk.y{fill:var(--t3)}
.sgchart .mk.now{fill:none;stroke:var(--ink);stroke-width:2}
.sgchart .hv{stroke:var(--ink2);stroke-width:1;stroke-dasharray:2 2}.sgchart .hit{fill:transparent;cursor:crosshair}
.sgread{font-size:12.5px;margin:4px 0 0;min-height:1.4em;color:var(--ink2)}.sgread b{color:var(--ink)}
.sgsw{overflow-x:auto}
.sgst2,.sgrt{width:100%;border-collapse:collapse;font-size:12.5px}
.sgst2 th,.sgrt th{font-weight:600;color:var(--ink2);text-align:right;padding:4px 5px;border-bottom:1px solid var(--line2);font-size:12px;line-height:1.3;vertical-align:bottom}
.sgst2 th{white-space:normal;min-width:3.2em}.sgrt th{white-space:nowrap}
.sgst2 td,.sgrt td{padding:4px 5px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:middle}
.sgst2 th.l,.sgst2 td.l,.sgrt th.l,.sgrt td.l{text-align:left}
.sgst2 td.nm{white-space:normal;min-width:84px}.sgst2 td small,.sgrt td small{display:block;font-size:11px;color:var(--mut);font-weight:400}
.sgst2 .sgd small{display:block;color:inherit;font-size:10.5px;line-height:1.2}.sgst2 .sgd{display:inline-block;border-radius:7px;padding:1px 6px;line-height:1.3}
.sgsb{cursor:pointer}.sgsb:hover td{background:var(--card2)}.sgsb.on td.nm{box-shadow:inset 3px 0 0 var(--acc)}
.sgsb.sel td{background:var(--accbg)}.sgon{color:var(--acc);font-weight:600}
.sgst2 td.r10{text-align:center}
.sgrt td.up{color:var(--t4)}.sgrt td.dn{color:var(--t0)}
.sghow{margin-top:12px}.sghow summary{cursor:pointer;color:var(--acc);font-size:13px}
.sgdl2{margin:6px 0;font-size:13.5px;line-height:1.7}.sgdl2 dt{font-weight:600;margin-top:6px}.sgdl2 dd{margin:0 0 2px 0;color:var(--ink2)}
body.sgopen{overflow:hidden}
.sgtb tr.sgr.open td{background:var(--accbg)}
@media (min-width:1100px){.sgpb{background:transparent;pointer-events:none}body.sgopen{overflow:auto}}
@media (max-width:900px){.sgt{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.sgt{grid-template-columns:minmax(0,1fr)}.sgtb .dsk{display:none}.sgln{padding-left:0}
 .sgtb td.l{min-width:150px}.sgwrap{overflow-x:visible}.sgtb td.l .sgm{display:block}
 .sgsw{overflow-x:auto}
 .sgmob{display:block;margin-top:4px}.sgmn{display:flex;align-items:center;gap:10px}.sgmn .sgnv,.sgmn .sgnz{display:inline;white-space:nowrap}
 .sgms{font-size:12.5px;color:var(--ink2);line-height:1.55;margin-top:3px}.sgms b{color:var(--ink)}.sgms .sgs{display:block;font-size:11.5px}
 .sgp{width:100%;padding:0 12px 28px}
 .sgst2,.sgst2 tbody{display:block}.sgst2 thead{display:none}.sgsw{overflow-x:visible}
 .sgst2 tbody{border-bottom:1px solid var(--line2);padding:4px 0}
 .sgst2 tr{display:grid;grid-template-columns:minmax(0,1.6fr) repeat(6,minmax(0,1fr));align-items:center;column-gap:2px}
 .sgst2 td{border-bottom:0;padding:3px 2px;text-align:center;white-space:normal}
 .sgst2 td.nm{grid-column:1/-1;text-align:left;padding:4px 2px 0}.sgst2 td.nm small{display:inline;margin-left:6px}
 .sgst2 td.wt{text-align:left}.sgst2 td[data-h]::before{content:attr(data-h);display:block;font-size:10px;color:var(--mut);line-height:1.2}
 .sgst2 td.r10 small{font-size:10px}.sgst2 .sgd{white-space:normal;max-width:100%}.sgst2 .sgd small{font-size:10px}
 .sgchips{flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px}.sgch{flex:0 0 auto}}
"""

JS = r"""
(function(){
const SG = JSON.parse(document.getElementById('sgd').textContent);
const ROWS = SG.rows, ON = SG.on, IT = SG.it || {};
const I = {id:0,mk:1,cat:2,grp:3,name:4,kind:5,H:6,th:7,tier:8,dir:9,up:10,warn:11,buy:12,a:13,z:14,x:15};
const TORD = {good:0, ref:1, none:2, few:3};
const MKO = ['tw','spx','ixic','ndx','sox','us','stk'];
const HT = {20:'1 個月',60:'3 個月',250:'12 個月'};
const st = {q:'', mk:'', cat:'', tier:'', dir:'', now:false, sort:'def', asc:false, limit:80};
let OCC = null, OCCP = null;
const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pc = v => v == null ? '—' : Math.round(v) + '%';
const md = d => d ? (+d.slice(5,7)) + '/' + (+d.slice(8,10)) : '';
const YR = Object.values(SG.asof || {}).filter(Boolean).sort().pop() || '';
const mdy = d => d ? (d.slice(0,4) === YR.slice(0,4) ? md(d) : d.slice(0,4) + '/' + md(d)) : '';
const ymd = d => !d ? '' : d.length === 7 ? d.slice(0,4) + '/' + (+d.slice(5,7)) : d.slice(0,4) + '/' + (+d.slice(5,7)) + '/' + (+d.slice(8,10));
const p1 = v => v == null || isNaN(v) ? '—' : (v * 100).toFixed(1) + '%';
const sp1 = v => v == null || isNaN(v) ? '—' : (v >= 0 ? '+' : '−') + Math.abs(v * 100).toFixed(1) + '%';
function stat(r, d){ return r[d === 'up' ? I.up : d === 'warn' ? I.warn : I.buy] || null; }
function dEdge(s){ return s && s[1] != null && s[2] != null ? s[1] - s[2] : null; }
function sd(r){ const d = r[I.dir][0]; return [d, stat(r, d)]; }
function edge(r){ return dEdge(sd(r)[1]); }
function dirsOf(r){ const c = r[I.cat]; return c === 'buy' ? ['buy'] : (c === 'stock' || c === 'strat') ? [r[I.dir][0]] : ['up', 'warn']; }
function hz(r){ const c = r[I.cat]; if (c === 'buy') return '這一波'; if (c === 'ind') return '12 個月';
  if (c === 'strat') return '照規則'; if (c === 'stock') return '20 個交易日'; return HT[r[I.H]] || (r[I.H] + ' 個交易日'); }
function nowTxt(r){ const n = ON[r[I.id]]; if (!n) return '';
  if (n.live != null) return '今天 ' + n.live + ' 檔';
  if (n.left != null) return mdy(n.since) + ' 出現・還看 ' + n.left + ' 天';
  if (n.event) return mdy(n.since) + ' 出現';
  return mdy(n.since) + ' 起'; }
function label(r){ const nm = r[I.name];
  if (['heat','deriv','crash','buy','ind'].includes(r[I.cat])) { const i = nm.lastIndexOf('・'); return i >= 0 ? nm.slice(i + 1) : nm; }
  return nm; }
function what(r, d){ const c = r[I.cat];
  if (c === 'strat') return '每筆賺錢';
  if (d === 'buy') return '買在相對低點';
  if (d === 'up') return c === 'stock' ? '持有 20 天賺錢' : '之後上漲';
  return '之後大跌'; }
function phr(r, d){ const s = stat(r, d); if (!s) return ''; const c = r[I.cat], h = hz(r);
  let w;
  if (c === 'strat') w = '每筆賺錢的比例';
  else if (d === 'buy') w = '買在這一波相對低點的機率';
  else if (d === 'up') w = c === 'stock' ? '持有 20 天賺錢的機率' : '之後 ' + h + '上漲的機率';
  else w = '之後 ' + h + '內大跌（最大回撤 ' + r[I.th] + '% 以上）的機率';
  return w + ' <b>' + pc(s[1]) + '</b>' + (s[2] != null ? '（隨便挑一天 ' + pc(s[2]) + '）' : ''); }
function mark(t){ const x = SG.tiers[t] || ['', '']; return '<span class="sgtk sgtk-' + t + '" title="' + esc(x[1]) + '">' + x[0] + '</span>'; }
function sent(r){ const [d, s] = sd(r); return mark(s ? s[6] : r[I.tier]) + ' <b>' + esc(label(r)) + '</b>：' + phr(r, d); }
function zi(h){ return h == null ? 'x' : h >= 80 ? '4' : h >= 60 ? '3' : h >= 40 ? '2' : h >= 20 ? '1' : '0'; }

// ── 依指標整理（docs/lab_sigview_plan.md）
const INDS = SG.inds.map(x => { const sig = x[5].map(i => ROWS[i]);
  const rk = r => TORD[r[I.tier]] * 1000 - (edge(r) ?? -99);
  const srt = a => a.slice().sort((p, q) => rk(p) - rk(q) || (p[I.id] < q[I.id] ? -1 : 1));
  const on = srt(sig.filter(r => ON[r[I.id]])), best = srt(sig)[0], ds = new Set();
  sig.forEach(r => dirsOf(r).forEach(d => { const s = stat(r, d); if (s && (s[6] === 'good' || s[6] === 'ref')) ds.add(d); }));
  const it = x[6] && IT[x[1]] ? IT[x[1]][x[6]] || null : null;
  return {k: x[0], mk: x[1], cat: x[2], name: x[3], grp: x[4], sig, on, best, ds, it, ik: x[6],
    hay: (x[3] + ' ' + x[0] + ' ' + (SG.mk[x[1]] || '') + ' ' + SG.icat[x[2]] + ' ' + sig.map(r => r[I.name]).join(' ')).toLowerCase()}; });
const BYK = {}, SIG2 = {};
INDS.forEach(x => { BYK[x.k] = x; x.sig.forEach(r => { SIG2[r[I.id]] = x; }); });
function grpName(x){ return x.grp && SG.dimn[x.mk] ? SG.dimn[x.mk][x.grp] || '' : ''; }
function meta(x){ return [SG.mk[x.mk], x.cat === 'heat' ? grpName(x) : SG.icat[x.cat]].filter(Boolean).join('・'); }
function pass(x, skip){
  if (st.q && !st.q.split(/\s+/).every(w => x.hay.includes(w))) return false;
  if (skip !== 'mk' && st.mk && x.mk !== st.mk) return false;
  if (skip !== 'cat' && st.cat && x.cat !== st.cat) return false;
  if (skip !== 'tier' && st.tier && x.best[I.tier] !== st.tier) return false;
  if (skip !== 'dir' && st.dir && !x.ds.has(st.dir)) return false;
  if (st.now && !x.on.length) return false;
  return true; }
function score(x){ const o = x.on[0], b = x.best;
  return (o ? (4 - TORD[o[I.tier]]) * 1e5 + (edge(o) ?? 0) * 100 : 0) + (4 - TORD[b[I.tier]]) * 1000 + Math.max(-9, edge(b) ?? -9); }
function key(x){
  switch (st.sort) {
    case 'name': return x.name;
    case 'h': return x.it && x.it.h != null ? x.it.h : -1;
    case 'tier': return (4 - TORD[x.best[I.tier]]) * 1000 + (edge(x.best) ?? -99);
    default: return score(x); } }
function sorted(list){
  const dir = st.asc ? 1 : -1;
  return list.slice().sort((a, b) => { const ka = key(a), kb = key(b);
    if (ka < kb) return -dir; if (ka > kb) return dir; return a.k < b.k ? -1 : 1; }); }
const TCH = {good: '★ 有好訊號', ref: '● 最好是可參考', none: '○ 沒有比隨便挑一天好', few: '— 次數不夠'};
function chips(){
  const defs = {mk: MKO.map(k => [k, SG.mk[k]]), cat: Object.entries(SG.icat), tier: Object.entries(TCH),
    dir: [['up','有偏多訊號'],['warn','有警示訊號'],['buy','有買點訊號']]};
  document.querySelectorAll('.sgchips[data-k]').forEach(box => {
    const k = box.dataset.k, cnt = {};
    INDS.forEach(x => { if (!pass(x, k)) return;
      const vs = k === 'dir' ? [...x.ds] : k === 'tier' ? [x.best[I.tier]] : [x[k]]; vs.forEach(v => { cnt[v] = (cnt[v] || 0) + 1; }); });
    box.innerHTML = '<button type="button" class="sgch' + (st[k] ? '' : ' on') + '" data-v="">全部</button>' +
      defs[k].filter(([v]) => cnt[v] || st[k] === v).map(([v, nm]) => '<button type="button" class="sgch' + (st[k] === v ? ' on' : '') +
        '" data-v="' + v + '">' + esc(nm) + '<i>' + (cnt[v] || 0) + '</i></button>').join('');
    box.onclick = e => { const b = e.target.closest('.sgch'); if (!b) return; st[k] = b.dataset.v; st.limit = 80; draw(); }; }); }
function spark(sp, w, h){
  if (!sp || !sp.some(v => v != null)) return '';
  const n = sp.length, X = i => (n > 1 ? i / (n - 1) : 0) * (w - 4) + 2, Y = v => h - 2 - (v / 100) * (h - 4);
  let d = '', pen = false, last = -1;
  sp.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; last = i; });
  return '<svg class="sgsp" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" aria-hidden="true">' +
    '<line class="th" x1="0" x2="' + w + '" y1="' + Y(80).toFixed(1) + '" y2="' + Y(80).toFixed(1) + '"/>' +
    '<line class="tc" x1="0" x2="' + w + '" y1="' + Y(20).toFixed(1) + '" y2="' + Y(20).toFixed(1) + '"/>' +
    '<path d="' + d + '"/><circle class="zt' + zi(sp[last]) + '" cx="' + X(last).toFixed(1) + '" cy="' + Y(sp[last]).toFixed(1) + '" r="2.6"/></svg>'; }
function nowCell(x){ const it = x.it;
  if (it && (it.v || it.h != null)) return (it.v ? '<span class="sgnv">' + esc(it.v) + '</span>' : '') +
    (it.h != null ? '<span class="sgnz zt' + zi(it.h) + '">' + Math.round(it.h) + ' ' + esc(it.band || '') + '</span>' : '');
  const o = x.on[0]; return o ? '<span class="sgnv">' + esc(nowTxt(o)) + '</span>' : '<span class="mu">—</span>'; }
function sigCell(x){
  if (x.on.length) { const o = x.on[0];
    return sent(o) + '<span class="sgs">' + esc(nowTxt(o)) + (x.on.length > 1 ? '・另 ' + (x.on.length - 1) + ' 個也成立' : '') + '</span>'; }
  const b = x.best, t = b[I.tier];
  return '<span class="mu">現在沒有成立的訊號' + ((t === 'good' || t === 'ref') ? '；最好的是「' + esc(label(b)) + '」' + SG.tiers[t][0] : '') + '</span>'; }
function rowHtml(x){ const t = x.on.length ? x.on[0][I.tier] : null, sp = x.it && x.it.sp;
  return '<tr class="sgr" data-k="' + esc(x.k) + '"><td class="tk">' + (t ? mark(t) : '<span class="sgtk mu">·</span>') + '</td>' +
    '<td class="l"><b class="sgin">' + esc(x.name) + '</b><span class="sgm">' + esc(meta(x)) + '</span>' +
    '<div class="sgmob"><div class="sgmn">' + nowCell(x) + spark(sp, 76, 20) + '</div><div class="sgms">' + sigCell(x) + '</div></div></td>' +
    '<td class="dsk nv">' + nowCell(x) + '</td><td class="dsk spk">' + spark(sp, 110, 26) + '</td>' +
    '<td class="l dsk ss">' + sigCell(x) + '</td></tr>'; }
function draw(){
  chips();
  const list = sorted(INDS.filter(x => pass(x)));
  document.getElementById('sgcnt').textContent = '共 ' + list.length + ' 個指標' + (list.length > st.limit ? '，先列前 ' + st.limit + ' 個' : '');
  document.getElementById('sgbody').innerHTML = list.slice(0, st.limit).map(rowHtml).join('');
  const mb = document.getElementById('sgmore');
  mb.hidden = list.length <= st.limit; mb.textContent = '再列 ' + Math.min(200, list.length - st.limit) + ' 個（還有 ' + (list.length - st.limit) + ' 個）';
  document.querySelectorAll('.sgtb th[data-s]').forEach(th => { th.classList.toggle('sorted', th.dataset.s === st.sort); th.classList.toggle('asc', th.dataset.s === st.sort && st.asc); });
  if (CUR) { const tr = document.querySelector('tr.sgr[data-k="' + CSS.escape(CUR.k) + '"]'); if (tr) tr.classList.add('open'); } }

// ── 說明（ⓘ）
const TIP = {
  tnow: '這個指標現在成立的訊號裡，判定最好的那一個：★ 好訊號、● 可參考、○ 沒有比隨便挑一天好、— 次數不夠；· 現在沒有成立的訊號。',
  tier: '★ 好訊號：至少 10 次、機率 ≥ ' + SG.hit.up + '%（警示 ≥ ' + SG.hit.warn + '%）、比隨便挑一天多 ' + SG.eg + ' 個百分點以上、近 10 年也成立。● 可參考：多 ' + SG.er + ' 個百分點以上。○ 沒有比隨便挑一天好。— 不到 10 次。',
  now: '現在的數值，和它的 0～100（100 最熱、0 最冷；和這個指標自己過去比）。',
  spark: '近一年每週的 0～100；上下兩條虛線是 80（過熱）和 20（過冷）。',
  p: '偏多：訊號出現的隔天收盤買，過了看多久之後收盤比買價高的比例。警示：看多久之內出現一段最大回撤到門檻的比例（期間最高收盤到之後最低收盤，先漲再跌也算）。括號是同一段期間隨便挑一天的比例。',
  what: '偏多看「之後上漲」，警示看「之後大跌」（最大回撤到門檻），買點看「買在這一波相對低點」。每一種訊號兩個方向各算一次。',
  prob: '這個訊號過去出現之後，「看什麼」那一欄成立的比例。',
  base: '同一段期間裡隨便挑一天、用同樣算法的比例。訊號要比它高才有用。',
  edge: '機率減掉隨便挑一天，單位是百分點。',
  r10: '只看最近 10 年：✓ 也達到好訊號的門檻；△ 比隨便挑一天多 ' + SG.er + ' 個百分點以上，但沒到好訊號的門檻；✗ 沒有；— 近 10 年不到 ' + SG.n10 + ' 次，不看。',
  n: '事件型（例：跌破季線）出現那天算一次，看多久的期間內再出現不算新的一次；狀態型（例：過熱中）連續的一段算一次。',
  dd: '期間最高收盤到之後最低收盤的跌幅（先漲再跌也算）。狀態型是這一段每一天的平均。'};
function ii(k){ return '<span class="sgq" tabindex="0" role="button" aria-label="說明" data-tip="' + k + '">ⓘ</span>'; }
const TB = document.getElementById('sgtip');
function showTip(el){ TB.textContent = TIP[el.dataset.tip] || ''; TB.hidden = false;
  const r = el.getBoundingClientRect(), w = Math.min(290, window.innerWidth - 24);
  TB.style.width = w + 'px'; TB.style.left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - w - 12)) + 'px';
  TB.style.top = (r.bottom + 6) + 'px';
  if (r.bottom + 6 + TB.offsetHeight > window.innerHeight - 8) TB.style.top = Math.max(8, r.top - TB.offsetHeight - 6) + 'px'; }
document.addEventListener('mouseover', e => { const q = e.target.closest && e.target.closest('.sgq'); if (q) showTip(q); });
document.addEventListener('mouseout', e => { if (e.target.closest && e.target.closest('.sgq')) TB.hidden = true; });
document.addEventListener('focusin', e => { const q = e.target.closest && e.target.closest('.sgq'); if (q) showTip(q); });
document.addEventListener('focusout', e => { if (e.target.closest && e.target.closest('.sgq')) TB.hidden = true; });
document.addEventListener('click', e => { const q = e.target.closest && e.target.closest('.sgq');
  if (q) { e.stopPropagation(); e.preventDefault(); showTip(q); return; } if (!TB.hidden) TB.hidden = true; }, true);

// ── 怎樣算（沿用第一版的說明）
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
  if (c === 'stock') return d === 'up' ? '隔天開盤買、持有 20 個交易日收盤賣，扣來回成本後賺錢；隨便挑一天＝同一段期間加權指數上漲的比例'
    : '隔天開盤算起 20 個交易日內的最大回撤（期間最高到之後最低，先漲再跌也算）' + th + '% 以上；隨便挑一天＝同一段期間所有 ETF 持股每一天的同樣比例';
  if (c === 'strat') return '每一筆扣成本後賺錢的比例；判定看報酬型態（賺錢比例 ≥ 60% 而且每月平均 ≥ 1%，或賺錢比例 ≥ 40%、賺賠比 ≥ 2.5、每月平均 ≥ 2%）';
  if (c === 'buy') return '買在這一波的相對低點（事件前高點到之後最低收盤的下三分之一）；隨便挑一天＝同一批事件「' + ((r[I.x] || {}).base_name || '') + '」';
  if (c === 'ind') return d === 'up' ? '訊號那個月底買，12 個月後的月底比買價高' : '訊號那個月底算起，12 個月內的最大回撤（月底最高到之後月底最低）20% 以上';
  return d === 'up' ? '觸發隔天收盤買，' + h + '後收盤比買價高' : '觸發隔天收盤算起，' + h + '內的最大回撤（期間最高收盤到之後最低收盤，先漲再跌也算）' + th + '% 以上'; }
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
  if (c === 'stock') { const nm = (OCC && OCC.names) || {};
    title = '每一次（最近 60 次；共 ' + oc.length + ' 次）' + (d === 'warn' ? '：隔天開盤買、持有 20 個交易日的報酬・這 20 天內的最大回撤' : '：持有 20 個交易日的報酬');
    items = oc.slice(-60).reverse().map(o => '<li class="' + (o[2] ? 'y' : '') + '">' + md(o[0]) + ' ' + esc(o[1]) + ' ' + esc(nm[o[1]] || '') + ' <span class="x">' + (o[4] >= 0 ? '+' : '') + o[4] + '%' +
      (d === 'warn' && o[5] != null ? '・回撤 ' + Math.round(o[5]) + '%' : '') + '</span></li>'); }
  else if (r[I.kind] === 'state' && c !== 'buy') {
    const j = d === 'warn' ? 4 : 3, k = c === 'ind' ? 6 : 5;
    title = '每一段（最近 40 段；共 ' + oc.length + ' 段）：起訖、天數、這一段中了的比例' + (d === 'warn' ? '、段內每一天之後最大回撤的平均' : '');
    items = oc.slice(-40).reverse().map(o => '<li class="' + (o[j] >= 0.5 ? 'y' : '') + '">' + ymd(o[0]) + (o[1] !== o[0] ? '～' + ymd(o[1]) : '') + ' <span class="x">' + o[2] + (r[I.x] && r[I.x].monthly ? ' 個月' : ' 天') + '</span> ' + Math.round(o[j] * 100) + '%' +
      (d === 'warn' && o[k] != null ? ' <span class="x">回撤 ' + Math.round(o[k] * 100) + '%</span>' : '') + '</li>'); }
  else { const j = c === 'buy' ? 1 : (d === 'warn' ? 2 : 1);
    title = '每一次（最近 60 次；共 ' + oc.length + ' 次）：' + (c === 'buy' ? '✓＝買在相對低點' : '✓＝中了');
    items = oc.slice(-60).reverse().map(o => '<li class="' + (o[j] ? 'y' : '') + '">' + ymd(o[0]) + ' ' + (o[j] ? '✓' : '<span class="x">✗</span>') + '</li>'); }
  return '<div class="sgoc"><p class="note">' + title + '</p><ul class="sgol">' + items.join('') + '</ul></div>'; }
function loadOcc(){ if (OCCP) return OCCP;
  OCCP = fetch('x9oh.json').then(x => x.json()).then(j => { OCC = j; return j; }).catch(() => { OCCP = null; return null; });
  return OCCP; }

// ── 指標頁（右側面板；手機全螢幕）
const PV = document.getElementById('sgpv'), PB = document.getElementById('sgp');
let CUR = null, SEL = null, PUSHED = false;
const VIEW = {span: '1y', raw: false};
function ckOf(x){ return !x.ik || !SG.chart[x.mk] ? null : x.cat === 'dim' ? x.ik.slice(1) : x.ik; }
function cell(k, v, sub){ return '<div class="sgnc"><span class="k">' + k + '</span><span class="v">' + v + '</span>' + (sub ? '<span class="s">' + sub + '</span>' : '') + '</div>'; }
function nowHtml(x){ const it = x.it; let h = '<div class="sgnow">';
  if (it) {
    if (it.v) h += cell('現值', esc(it.v), it.d ? '資料 ' + esc(ymd(it.d)) : '');
    if (it.h != null || it.v) h += cell('0～100', it.h == null ? '—' : '<span class="zt' + zi(it.h) + '">' + Math.round(it.h) + ' ' + esc(it.band || '') + '</span>',
      it.hot === 1 ? '數值越高越熱' : it.hot === -1 ? '數值越低越熱' : '和自己過去比');
  }
  h += cell('現在成立的訊號', x.on.length ? x.on.length + ' 個' : '沒有', x.on.length ? '' : '過去的訊號見下表');
  h += '</div>';
  if (it && it.pos) h += '<p class="sgdl">' + esc(it.pos) + '</p>';
  if (it && it.dv) h += '<p class="sgdl">邊際變化：<b>' + esc(it.dv) + '</b></p>';
  if (it && it.why) h += '<p class="warn">' + esc(it.why) + '</p>';
  if (x.on.length) h += '<ul class="sgonl">' + x.on.map(r => '<li>' + sent(r) + '<span class="sgs">' + esc(nowTxt(r)) + '</span></li>').join('') + '</ul>';
  return h; }
function r10(s, d){ if (!s || !s[3] || s[3] < SG.n10) return '<span class="mu">—</span>' + (s && s[3] ? '<small>' + s[3] + ' 次</small>' : '');
  const e = s[4] - s[5], ok = s[4] >= SG.hit[d] && e >= SG.eg ? '✓' : e >= SG.er ? '△' : '✗';
  return ok + '<small>' + s[3] + ' 次・' + pc(s[4]) + '</small>'; }
function sigTable(x){
  const head = '<thead><tr><th class="l">訊號</th><th class="l">看什麼 ' + ii('what') + '</th><th>機率 ' + ii('prob') + '</th><th>隨便挑一天 ' + ii('base') + '</th>' +
    '<th>多幾個百分點 ' + ii('edge') + '</th><th>近 10 年也成立嗎 ' + ii('r10') + '</th><th>出現過幾次 ' + ii('n') + '</th><th>判定 ' + ii('tier') + '</th></tr></thead>';
  const body = x.sig.map(r => { const ds = dirsOf(r), on = ON[r[I.id]];
    return '<tbody class="sgsb' + (on ? ' on' : '') + (SEL === r ? ' sel' : '') + '" data-id="' + esc(r[I.id]) + '">' + ds.map((d, i) => { const s = stat(r, d), e = dEdge(s);
      const w = what(r, d) + (d === 'warn' ? '<small>最大回撤 ' + r[I.th] + '% 以上</small>' : '');
      return '<tr>' + (i ? '' : '<td class="l nm" rowspan="' + ds.length + '"><b>' + esc(label(r)) + '</b><small>看 ' + esc(hz(r)) +
          (on ? '・<span class="sgon">現在成立</span>' : '') + '</small></td>') +
        '<td class="l wt"><span class="sgd sgd-' + d + '">' + w + '</span></td><td data-h="機率"><b>' + (s ? pc(s[1]) : '—') + '</b></td><td data-h="隨便挑一天">' + (s ? pc(s[2]) : '—') + '</td>' +
        '<td data-h="多幾個百分點">' + (e == null ? '—' : (e >= 0 ? '+' : '−') + Math.abs(Math.round(e))) + '</td><td class="r10" data-h="近 10 年">' + r10(s, d) + '</td><td data-h="出現">' + (s ? s[0] : '—') + '</td>' +
        '<td data-h="判定">' + mark(s ? s[6] : 'few') + '</td></tr>'; }).join('') + '</tbody>'; }).join('');
  return '<div class="sgwrap sgsw"><table class="sgst2">' + head + body + '</table></div>'; }
function panelHtml(x){
  const ck = ckOf(x);
  let h = '<div class="sgph"><div><p class="sgkick">' + esc(meta(x)) + '</p><h3 id="sgpt">' + esc(x.name) + '</h3></div>' +
    '<button type="button" class="sgx" id="sgx" aria-label="關閉">×</button></div><div class="sgpc">';
  h += '<h4>現在</h4>' + nowHtml(x);
  if (ck) h += '<h4>走勢</h4><div class="sgcb"><div class="sgseg" data-g="span"><button type="button" data-v="1y">近 1 年</button>' +
    '<button type="button" data-v="5y">近 5 年</button><button type="button" data-v="all">全部</button></div>' +
    (x.cat === 'heat' ? '<div class="sgseg" data-g="raw"><button type="button" data-v="0">0～100</button><button type="button" data-v="1">原始值</button></div>' : '') +
    '</div><div class="sgcv" id="sgcv"><p class="note">走勢載入中…</p></div><p class="sgread" id="sgread"></p><p class="note" id="sgleg"></p>';
  h += '<h4>這個指標的訊號</h4><p class="note">每一種訊號都分偏多、警示兩個方向各算一次。點一列，' + (ck ? '走勢圖的打點和' : '') + '下面的「最近幾次」換成那個訊號。</p>' + sigTable(x);
  h += '<h4>最近幾次：<span id="sgsel"></span></h4><div id="sgrec"></div>';
  h += '<details class="sghow"><summary>怎樣算出現、怎樣算中了</summary><div id="sghow"></div></details>';
  return h + '</div>'; }
function segSync(){ PB.querySelectorAll('.sgseg').forEach(g => g.querySelectorAll('button').forEach(b =>
  b.classList.toggle('on', g.dataset.g === 'span' ? b.dataset.v === VIEW.span : b.dataset.v === (VIEW.raw ? '1' : '0')))); }
function openInd(x, sid, push){
  const first = PV.hidden;
  CUR = x; SEL = (sid && x.sig.find(r => r[I.id] === sid)) || x.on[0] || x.best;
  if (push) { const u = '#i=' + encodeURIComponent(x.k);
    if (first && !PUSHED) { history.pushState({sg: 1}, '', u); PUSHED = true; } else history.replaceState(history.state, '', u); }
  if (x.cat !== 'heat') VIEW.raw = false;
  PB.innerHTML = panelHtml(x); segSync();
  PV.hidden = false; document.body.classList.add('sgopen');
  PB.scrollTop = 0; if (first) PB.focus({preventScroll: true});
  document.querySelectorAll('tr.sgr.open').forEach(e => e.classList.remove('open'));
  const tr = document.querySelector('tr.sgr[data-k="' + CSS.escape(x.k) + '"]'); if (tr) tr.classList.add('open');
  fillSel(); drawChart(); }
function closeP(fromHash){
  if (PV.hidden) return;
  PV.hidden = true; document.body.classList.remove('sgopen'); CUR = null; TB.hidden = true;
  document.querySelectorAll('tr.sgr.open').forEach(e => e.classList.remove('open'));
  if (!fromHash) { if (PUSHED) { PUSHED = false; history.back(); } else history.replaceState(null, '', location.pathname + location.search); }
  else PUSHED = false; }
function howHtml(r){ const x = r[I.x] || {};
  let h = '<p class="sgdl"><b>怎樣算出現</b>：' + esc(trig(r)) + '</p>';
  h += dirsOf(r).map(d => '<p class="sgdl"><b>' + (r[I.cat] === 'strat' ? '怎樣算中了' : what(r, d) + '：怎樣算中了') + '</b>：' + esc(succ(r, d)) + '</p>').join('');
  const w = stat(r, 'warn');
  if (w && w[7] != null) h += '<p class="sgdl">每一次之後最大回撤的中位數 ' + pc(w[7]) + '（隨便挑一天 ' + pc(w[8]) + '，只當參考）。</p>';
  if (x.pay) h += '<p class="sgdl">' + esc(payTxt(x)) + (x.old ? '（後台的 A／B／C 評級：' + esc(x.old) + '；機會頁的推薦用這裡的判定）' : '') + '</p>';
  if (x.up60 != null) h += '<p class="sgdl">另列：之後 60 日收盤比買價高的比例 ' + pc(x.up60) + '。</p>';
  if (r[I.a]) h += '<p class="sgdl note">資料期間 ' + ymd(r[I.a]) + '～' + ymd(r[I.z]) + '。</p>';
  const rl = rel(r); if (rl) h += '<p class="sgdl"><b>相關研究</b>：' + rl + '</p>';
  const mk = r[I.mk];
  if (['heat', 'deriv', 'multi', 'crash', 'tech'].includes(r[I.cat]) && SG.chart[mk])
    h += '<p class="sgdl"><a href="' + (mk === 'tw' ? 'x9m.html' : 'x9mu.html#ix=' + mk) + '">在景氣頁看' + esc(SG.mk[mk]) + ' →</a></p>';
  return h; }
function valAt(J, ck, d){ if (!J || !ck || !J.s[ck]) return null;
  const at = (s, k) => { if (k < 0 || !s) return null; const i = k - s.o; return i >= 0 && i < s.v.length ? s.v[i] : null; };
  if (J.d && J.d.d.length && d >= J.d.d[0]) { const v = at(J.s[ck].hd, idxOf(J.d.d, d)); if (v != null) return v; }   // 近一年：那一天
  const w = J.w.d; let k = idxOf(w, d); if (k >= 0 && w[k] < d) k += 1;                                         // 更早：那一週（含那一天的週末）
  return k < w.length ? at(J.s[ck].h, k) : null; }
function recHtml(r, oc){
  if (r[I.cat] === 'strat') return '<p class="note">逐筆交易在<a href="x9.html">個股頁</a>的策略說明卡（每一筆的買進、賣出與報酬）。</p>';
  if (!oc || !oc.length) return '<p class="note">沒有每一次的清單（窗口還沒走完的不列）。</p>';
  const c = r[I.cat];
  if (!['heat', 'deriv', 'crash', 'multi', 'tech', 'bub'].includes(c)) return occHtml(r, oc);
  const d = r[I.dir][0], x = CUR, J = x ? CJ[x.mk] : null, ck = x ? ckOf(x) : null, ev = r[I.kind] === 'event';
  const mo = (r[I.x] || {}).monthly, h = hz(r), list = oc.slice(-12).reverse();
  const vv = dt => { const v = valAt(J, ck, dt); return v == null ? '<span class="mu">—</span>' : '<span class="zt' + zi(v) + '">' + Math.round(v) + '</span>'; };
  const cls = v => v == null || isNaN(v) ? '' : v >= 0 ? ' class="up"' : ' class="dn"';
  const head = '<thead><tr><th class="l">' + (ev ? '出現日' : '期間') + '</th>' + (ck ? '<th>當時 0～100</th>' : '') + '<th>之後 ' + esc(h) + '漲跌</th>' +
    '<th>期間最大回撤 ' + ii('dd') + '</th><th>' + (ev ? (d === 'warn' ? '大跌' : '上漲') : (d === 'warn' ? '大跌的比例' : '上漲的比例')) + '</th></tr></thead>';
  const body = list.map(o => {
    if (ev) { const hit = d === 'warn' ? o[2] : o[1];
      return '<tr><td class="l">' + ymd(o[0]) + '</td>' + (ck ? '<td>' + vv(o[0]) + '</td>' : '') + '<td' + cls(o[4]) + '>' + sp1(o[4]) + '</td><td>' + p1(o[3]) + '</td>' +
        '<td>' + (hit ? '✓' : '<span class="mu">✗</span>') + '</td></tr>'; }
    const j = d === 'warn' ? 4 : 3;
    return '<tr><td class="l">' + ymd(o[0]) + (o[1] !== o[0] ? '～' + ymd(o[1]) : '') + '<small>' + o[2] + (mo ? ' 個月' : ' 天') + '</small></td>' +
      (ck ? '<td>' + vv(o[0]) + '</td>' : '') + '<td' + cls(o[6]) + '>' + sp1(o[6]) + '</td><td>' + p1(o[5]) + '</td><td>' + Math.round(o[j] * 100) + '%</td></tr>'; }).join('');
  return '<div class="sgwrap"><table class="sgrt">' + head + '<tbody>' + body + '</tbody></table></div>' +
    '<p class="note">共 ' + oc.length + (ev ? ' 次，列最近 12 次；還在觀察期內的不列' : ' 段，列最近 12 段；漲跌、最大回撤、比例是這一段每一天的平均，還在觀察期內的日子不算') + '。' +
    (ck ? '「當時 0～100」是' + (ev ? '出現' : '開始') + '那一天的值（一年以前的用那一週）。' : '') + '</p>'; }
function fillSel(){ const r = SEL, box = document.getElementById('sgrec'); if (!r || !box) return;
  document.getElementById('sgsel').textContent = label(r);
  document.getElementById('sghow').innerHTML = howHtml(r);
  PB.querySelectorAll('.sgsb').forEach(b => b.classList.toggle('sel', b.dataset.id === r[I.id]));
  if (OCC) { box.innerHTML = recHtml(r, OCC.occ[r[I.id]]); return; }
  box.innerHTML = '<p class="note">載入中…</p>';
  loadOcc().then(j => { if (SEL !== r) return; box.innerHTML = j ? recHtml(r, j.occ[r[I.id]]) : '<p class="note">載入失敗，請重新整理。</p>'; drawChart(); }); }

// ── 走勢圖（景氣頁對照圖的資料：近一年每天、1997 起每週）
const CJ = {}, CPR = {};
function loadChart(mk){ if (CJ[mk]) return Promise.resolve(CJ[mk]); if (!SG.chart[mk]) return Promise.resolve(null);
  if (!CPR[mk]) CPR[mk] = fetch(SG.chart[mk]).then(r => r.json()).then(j => { CJ[mk] = j; return j; }).catch(() => { CPR[mk] = null; return null; });
  return CPR[mk]; }
function unpack(o, n){ const out = new Array(n).fill(null); if (o && o.v) o.v.forEach((v, i) => { if (o.o + i < n) out[o.o + i] = v; }); return out; }
function series(J, ck){ const s = J.s && J.s[ck]; if (!s) return null;
  const raw = VIEW.raw && (VIEW.span === '1y' ? s.rd : s.r);
  if (VIEW.span === '1y') { const d = J.d.d; return {d, px: J.d.px, v: unpack(raw ? s.rd : s.hd, d.length), raw: !!raw}; }
  const d = J.w.d, n = d.length, a = VIEW.span === '5y' ? Math.max(0, n - 261) : 0, v = unpack(raw ? s.r : s.h, n);
  return {d: d.slice(a), px: J.w.px.slice(a), v: v.slice(a), raw: !!raw}; }
function idxOf(ds, d){ let lo = 0, hi = ds.length - 1, k = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (ds[m] <= d) { k = m; lo = m + 1; } else hi = m - 1; } return k; }
function fmtV(x, v, raw){ if (v == null) return '—'; if (!raw) return String(Math.round(v)); const it = x.it || {}, u = it.u || '';
  return (+v).toLocaleString('en-US', {minimumFractionDigits: it.dec ?? 2, maximumFractionDigits: it.dec ?? 2}) + (u === '%' ? '%' : u ? ' ' + u : ''); }
function pathOf(xs, X, Y){ let d = '', pen = false; xs.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; }); return d; }
function drawChart(){
  const x = CUR, box = document.getElementById('sgcv'); if (!x || !box) return; const ck = ckOf(x); if (!ck) return;
  loadChart(x.mk).then(J => {
    if (CUR !== x || !box.isConnected) return;
    const S = J && series(J, ck);
    if (!S) { box.innerHTML = '<p class="note">這一項沒有走勢資料。</p>'; return; }
    const rb = document.getElementById('sgrec');                                // 走勢資料到了：最近幾次補上「當時 0～100」
    if (rb && OCC && SEL) rb.innerHTML = recHtml(SEL, OCC.occ[SEL[I.id]]);
    const W = Math.max(280, Math.round(box.clientWidth || 520)), L = 40, R = 8, T = 8, H1 = 150, G = 20, H2 = 72, BH = 18;
    const n = S.d.length, X = i => L + (n > 1 ? i / (n - 1) : 0) * (W - L - R);
    const vs = S.v.filter(v => v != null);
    let lo = 0, hi = 100; if (S.raw && vs.length) { lo = Math.min(...vs); hi = Math.max(...vs); const pd = (hi - lo) * 0.06 || 1; lo -= pd; hi += pd; }
    const Y1 = v => T + (1 - (v - lo) / (hi - lo)) * H1;
    const ps = S.px.filter(p => p != null && p > 0), pl = Math.log(Math.min(...ps)), ph = Math.log(Math.max(...ps)) + 1e-9;
    const Y2 = p => T + H1 + G + (1 - (Math.log(p) - pl) / (ph - pl)) * H2;
    const Ht = T + H1 + G + H2 + BH;
    let g = '';
    // 訊號：狀態型畫色帶、事件型打點（實心＝之後中了、空心＝沒中）
    const r = SEL, oc = OCC && r ? OCC.occ[r[I.id]] : null, d0 = r ? r[I.dir][0] : 'up', ev = r && r[I.kind] === 'event';
    if (oc && !ev) oc.forEach(o => { const a = idxOf(S.d, o[0]), z = idxOf(S.d, o[1]); if (z < 0 || a >= n - 1 && S.d[n - 1] < o[0]) return;
      const sh = d0 === 'warn' ? o[4] : o[3], xa = X(Math.max(0, a)), xz = X(Math.max(0, z)) + 1.5;
      g += '<rect class="bd" x="' + xa.toFixed(1) + '" y="' + T + '" width="' + Math.max(2, xz - xa).toFixed(1) + '" height="' + H1 + '" style="opacity:' + (0.10 + 0.35 * sh).toFixed(2) + '"/>'; });
    const on = r && ON[r[I.id]];
    if (on && !ev && on.since) { const a = idxOf(S.d, on.since); if (a < n) g += '<rect class="bdn" x="' + X(Math.max(0, a)).toFixed(1) + '" y="' + T + '" width="' + (X(n - 1) - X(Math.max(0, a)) + 1.5).toFixed(1) + '" height="' + H1 + '"/>'; }
    if (!S.raw) [[80, '80 過熱'], [20, '20 過冷']].forEach(([v, t]) => { g += '<line class="tl" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y1(v).toFixed(1) + '" y2="' + Y1(v).toFixed(1) + '"/>'; });
    const ticks = S.raw ? [lo + (hi - lo) * 0.06, (lo + hi) / 2, hi - (hi - lo) * 0.06] : [0, 20, 50, 80, 100];
    ticks.forEach(v => { g += '<text class="ax" x="' + (L - 4) + '" y="' + (Y1(v) + 4).toFixed(1) + '" text-anchor="end">' + (S.raw ? fmtV(x, v, true).replace(/ .*$/, '') : v) + '</text>'; });
    g += '<path class="lv" d="' + pathOf(S.v, X, Y1) + '"/>';
    g += '<path class="lp" d="' + pathOf(S.px.map(p => p > 0 ? p : null), X, Y2) + '"/>';
    g += '<text class="ax" x="' + (L + 2) + '" y="' + (T + H1 + G - 5) + '">' + esc(SG.pxn[x.mk] || '') + '</text>';
    if (oc && ev) oc.forEach(o => { const i = idxOf(S.d, o[0]); if (i < 0 || (i === n - 1 && S.d[n - 1] < o[0]) || o[0] < S.d[0]) return;
      const v = S.v[i], hit = d0 === 'warn' ? o[2] : o[1], cy = v != null ? Y1(v) : Y2(S.px[i]);
      g += '<circle class="mk' + (hit ? ' y' : '') + '" cx="' + X(i).toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="3.6"/>'; });
    if (on && ev && on.since) { const i = idxOf(S.d, on.since); if (i >= 0 && on.since >= S.d[0]) { const v = S.v[i];
      g += '<circle class="mk now" cx="' + X(i).toFixed(1) + '" cy="' + (v != null ? Y1(v) : Y2(S.px[i])).toFixed(1) + '" r="4.2"/>'; } }
    const nt = Math.min(6, Math.max(2, Math.floor(W / 110)));
    for (let k = 0; k < nt; k++) { const i = Math.round(k * (n - 1) / (nt - 1)), dt = S.d[i] || '';
      const t = VIEW.span === '1y' ? (+dt.slice(5, 7)) + '月' : dt.slice(0, 4); const anc = k === 0 ? 'start' : k === nt - 1 ? 'end' : 'middle';
      g += '<text class="ax" x="' + X(i).toFixed(1) + '" y="' + (Ht - 4) + '" text-anchor="' + anc + '">' + t + '</text>'; }
    g += '<line class="hv" id="sghv" x1="0" x2="0" y1="' + T + '" y2="' + (T + H1 + G + H2) + '" style="display:none"/>';
    g += '<rect class="hit" x="' + L + '" y="0" width="' + (W - L - R) + '" height="' + Ht + '"/>';
    box.innerHTML = '<svg class="sgchart" viewBox="0 0 ' + W + ' ' + Ht + '" width="' + W + '" height="' + Ht + '" role="img" aria-label="' + esc(x.name) + '的走勢">' + g + '</svg>';
    const svg = box.querySelector('svg'), hv = svg.querySelector('#sghv'), rd = document.getElementById('sgread');
    const show = i => { const xx = X(i).toFixed(1); hv.setAttribute('x1', xx); hv.setAttribute('x2', xx); hv.style.display = '';
      rd.innerHTML = '<b>' + ymd(S.d[i]) + '</b>　' + esc(x.name) + ' ' + fmtV(x, S.v[i], S.raw) + '　' + esc(SG.pxn[x.mk] || '') + ' ' +
        (S.px[i] == null ? '—' : Math.round(S.px[i]).toLocaleString('en-US')); };
    const mv = e => { const b = svg.getBoundingClientRect(), cx = (e.touches ? e.touches[0].clientX : e.clientX) - b.left;
      show(Math.max(0, Math.min(n - 1, Math.round((cx * W / b.width - L) / ((W - L - R) / Math.max(1, n - 1)))))); };
    svg.addEventListener('mousemove', mv); svg.addEventListener('touchmove', mv, {passive: true}); svg.addEventListener('touchstart', mv, {passive: true});
    svg.addEventListener('mouseleave', () => { hv.style.display = 'none'; show(n - 1); hv.style.display = 'none'; });
    show(n - 1); hv.style.display = 'none';
    const lab = r ? label(r) : '';
    document.getElementById('sgleg').textContent = '上＝' + x.name + (S.raw ? '（原始值）' : '（0～100，虛線＝80 過熱、20 過冷）') + '；下＝' + (SG.pxn[x.mk] || '') + '（對數）。' +
      (r ? (ev ? '點＝「' + lab + '」出現的日子：實心＝之後' + (d0 === 'warn' ? '大跌' : '上漲') + '（中了）、空心＝沒中' + (on ? '、大點＝這一次（還在觀察）' : '') + '。'
        : '色帶＝「' + lab + '」的期間，越深＝那一段之後' + (d0 === 'warn' ? '大跌' : '上漲') + '的比例越高' + (on ? '；虛線框＝現在這一段（還在觀察）' : '') + '。') : '') +
      (OCC ? '' : '（訊號的日子載入中）'); }); }
let rzT = null;
window.addEventListener('resize', () => { clearTimeout(rzT); rzT = setTimeout(() => { if (CUR) drawChart(); }, 200); });
PB.addEventListener('click', e => {
  if (e.target.closest('#sgx')) { closeP(); return; }
  const sb = e.target.closest('.sgseg button');
  if (sb) { const g = sb.closest('.sgseg').dataset.g; if (g === 'span') VIEW.span = sb.dataset.v; else VIEW.raw = sb.dataset.v === '1'; segSync(); drawChart(); fillSel(); return; }
  const tb = e.target.closest('tbody.sgsb');
  if (tb && CUR) { const r = CUR.sig.find(q => q[I.id] === tb.dataset.id); if (r && r !== SEL) { SEL = r; fillSel(); drawChart(); } } });
document.getElementById('sgpb').addEventListener('click', () => closeP());
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !PV.hidden) closeP(); });

// ── 清單
document.getElementById('sgbody').addEventListener('click', e => { const tr = e.target.closest('tr.sgr'); if (tr && BYK[tr.dataset.k]) openInd(BYK[tr.dataset.k], null, true); });
document.querySelectorAll('.sgtb th[data-s]').forEach(th => th.addEventListener('click', () => {
  const s = th.dataset.s; if (st.sort === s) st.asc = !st.asc; else { st.sort = s; st.asc = s === 'name'; } draw(); }));
let qt = null;
document.getElementById('sgq').addEventListener('input', e => { clearTimeout(qt); qt = setTimeout(() => { st.q = e.target.value.trim().toLowerCase(); st.limit = 80; draw(); }, 150); });
document.getElementById('sgnow').addEventListener('change', e => { st.now = e.target.checked; st.limit = 80; draw(); });
document.getElementById('sgmore').addEventListener('click', () => { st.limit += 200; draw(); });
document.getElementById('sgcsv').addEventListener('click', () => {
  const list = sorted(INDS.filter(x => pass(x)));
  const head = ['指標','市場','類別','訊號','看多久','現在成立','方向','看什麼','機率%','隨便挑一天%','多幾個百分點','近10年次數','近10年機率%','近10年隨便挑一天%',
    '出現過幾次','判定','最大回撤中位數%','隨便挑一天最大回撤中位數%','大跌門檻%','代號'];
  const lines = [head];
  list.forEach(x => x.sig.forEach(r => dirsOf(r).forEach(d => { const s = stat(r, d), e = dEdge(s);
    lines.push([x.name, SG.mk[x.mk], SG.icat[x.cat], label(r), hz(r), nowTxt(r), SG.dirs[d] || d, what(r, d), s ? s[1] : '', s ? s[2] : '', e == null ? '' : e.toFixed(1),
      s ? (s[3] ?? '') : '', s ? (s[4] ?? '') : '', s ? (s[5] ?? '') : '', s ? s[0] : '', s ? (SG.tiers[s[6]] || ['', ''])[1] : '',
      d === 'warn' && s ? (s[7] ?? '') : '', d === 'warn' && s ? (s[8] ?? '') : '', d === 'warn' ? (r[I.th] ?? '') : '', r[I.id]]); })));
  const csv = '﻿' + lines.map(l => l.map(v => { const t = String(v == null ? '' : v); return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; }).join(',')).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'})); a.download = '訊號總覽.csv'; a.click(); });

// ── 研究細節（研究卡，點了才載入）
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

// ── 網址：#i=指標（#s=訊號 也會打開那個指標、選那個訊號），#r=市場:研究卡
function fromHash(ev){
  const h = location.hash;
  let m = h.match(/^#r=(\w+)(?::(\w+))?$/);
  if (m) { closeP(true); loadR(m[1], m[2]); const sec = document.getElementById('research'); if (sec && !m[2]) sec.scrollIntoView({block: 'start'}); return; }
  m = h.match(/^#i=([^&]+)$/);
  if (m) { const x = BYK[decodeURIComponent(m[1])]; if (x) { if (ev) PUSHED = true; if (CUR !== x) openInd(x, null, false); return; } }
  m = h.match(/^#s=(.+)$/);
  if (m) { const id = decodeURIComponent(m[1]), x = SIG2[id]; if (x) { if (ev) PUSHED = true; openInd(x, id, false); return; } }
  closeP(true); }
window.addEventListener('hashchange', fromHash);
draw(); fromHash();
})();
"""
