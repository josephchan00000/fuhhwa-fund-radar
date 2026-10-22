"""訊號總覽頁（dashboard/x9o.html＋每一次的清單 x9oh.json；docs/lab_signal_plan.md 第 5 節、規格 sigspec VER 1）。

由上而下：今天有效的好訊號（五個市場＋個股）→ 全部訊號與策略（搜尋、篩選、排序、點開看每一次、下載 CSV）→ 判定方式。
命中率讀研究檔（市場：data/lab/sig_research.json，scripts/run_sig.py；個股：data/lab/sig_stock.json，籌碼雷達建頁時寫）；
現在有沒有效每天算（景氣頁建頁時 sigcat.now_for_B 存進程序裡，這裡沿用；沒有就自己算）。只描述過去發生的比例。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import sigcat as G
from . import sigoos as OOS
from . import sigspec as S
from . import xstratpage as XSP
from . import xstratspec as XS
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
IND_CATS = {"heat": "景氣項目", "dim": "景氣面向", "scen": "情境", "inst": "法人買賣超", "crash": "大跌風險", "tech": "技術事件", "bub": "泡沫", "ind": "產業泡沫",
            "buy": "大跌後買點", "xs": "總經策略", "stock": "個股訊號", "strat": "個股策略"}
# 篩選用的分類（2026-10-21 起，docs/lab_nav_plan.md 第 2.2 節）：第一層照景氣頁的面向分（景氣頁看到哪個面向熱，就點哪一類），
# 籌碼、技術、策略再分第二層。IND_CATS（資料從哪裡來）照留，搜尋時用得到。
FACETS = {"fund": "基本面", "chip": "籌碼", "liq": "資金", "tech": "技術", "scen": "情境", "bub": "泡沫", "buy": "大跌後買點",
          "strat": "策略", "stock": "個股訊號"}
SUBS = {"chip": {"margin": "融資・期貨・選擇權", "inst": "法人買賣超", "dim": "面向分數"},
        "tech": {"ind": "指標", "ev": "價位事件", "dim": "面向分數"},
        "strat": {"short": "總經・短線", "bottom": "總經・落底", "season": "總經・季節性", "risk": "總經・風險控制", "stk": "個股策略"}}
FACE_OF = {"fund": "fund", "chip": "chip", "sent": "chip", "gliq": "liq", "tliq": "liq", "liq": "liq", "tech": "tech"}
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
    if cat == "scen":
        return f"{mk}:scen:{var}", "scen", r["vn"], None
    if cat == "crash":
        return f"{mk}:{var}", "crash", r["vn"], var
    if cat == "inst":                                     # 法人買賣超：一個期間一個指標（單日極端與連續同一個）
        return f"{mk}:inst:{var}", "inst", r["vn"], var
    if cat == "tech":
        return f"{mk}:tech:{var}", "tech", r["vn"], None
    if cat == "bub":
        return f"{mk}:bub", "bub", "泡沫等級與條件", None
    if cat == "ind":
        return f"ind:{r.get('grp')}", "ind", r["vn"], None
    if cat == "buy":
        return f"{mk}:buy:{r.get('grp')}", "buy", r["name"].split("・")[0], None
    return r["id"], cat, r.get("vn") or r["name"], None


def facet_of(cat: str, grp: str | None, item: str | None) -> tuple[str, str | None]:
    """指標的分類 → (第一層, 第二層)；見 FACETS、SUBS。cat、grp、item＝indicators() 的類別、面向、景氣頁的項目鍵。"""
    if cat in ("heat", "dim"):
        if grp == "multi":                                 # 同時兩個面向過熱：和情境放一起
            return "scen", None
        f = FACE_OF.get(grp or "", "fund")
        if cat == "dim":
            return f, ("dim" if f in ("chip", "tech") else None)
        return f, {"chip": "margin", "tech": "ind"}.get(f)
    if cat == "crash":                                     # 融資 ÷ 市值是籌碼，換手率、成交量能是資金
        return ("chip", "margin") if item in ("W1", "W2", "W3") else ("liq", None)
    if cat == "inst":
        return "chip", "inst"
    if cat == "tech":
        return "tech", "ev"
    if cat in ("bub", "ind"):
        return "bub", None
    if cat == "strat":
        return "strat", "stk"
    return cat, None                                       # scen、buy、stock


def indicators(rows: list[dict]) -> list[list]:
    """依指標整理：[[指標鍵, 市場, 類別, 名稱, 面向, [這個指標的訊號在 rows 的位置], 景氣頁的項目鍵, 第一層, 第二層], …]
    （照 rows 出現的順序）。景氣項目的面向取水準那一列的 grp（邊際變化那一列是 deriv）；第一層、第二層見 facet_of。"""
    out: dict = {}
    for i, r in enumerate(rows):
        k, cat, nm, it = ind_of(r)
        x = out.get(k)
        if x is None:
            x = out[k] = [k, r["mk"], cat, nm, None, [], it]
        if r["cat"] in ("heat", "multi") and x[4] is None:
            x[4] = r.get("grp")
        x[5].append(i)
    for x in out.values():
        x.extend(facet_of(x[2], x[4], x[6]))
    return list(out.values())


def ind_names() -> dict:
    """產業泡沫每一段的產業代碼 → 中文（美股 49 細產業、美股類股 ETF；台股本來就是中文）。"""
    from . import bubindspec as BIS
    return {**BIS.FF_NAMES, **{k: f"{v}（{k}）" for k, v in BIS.US_ETF.items()}}


def scen_meta() -> dict:
    """情境（sigspec 第 4.10 節）：{代號: [名稱, 條件（白話）, 想看的事, 用到的面向]}。"""
    out = {}
    for key, name, cond, why in S.SCENARIOS:
        if cond in ("many_hi", "many_lo"):
            lab = f"{S.SCEN_HI} 以上" if cond == "many_hi" else f"未滿 {S.SCEN_LO}"
            txt = (f"四個面向（{'、'.join(S.SCEN_DIM_NAMES[g] for g in S.SCEN_DIMS)}）至少 {S.SCEN_MIN_DIMS} 個有值，"
                   f"其中 {S.SCEN_MANY} 個以上{lab}")
            dims = list(S.SCEN_DIMS)
        else:
            txt = "、".join(f"{S.SCEN_DIM_NAMES[g]} {f'{S.SCEN_HI} 以上' if o == 'hi' else f'未滿 {S.SCEN_LO}'}" for g, o in cond)
            dims = [g for g, _ in cond]
        out[key] = [name, txt, why, dims]
    return out


def scen_values(items: dict) -> dict:
    """{市場: {共通面向: 現在的分數}}（景氣頁的面向分數；台股資金＝全球與台灣資金平均，兩個都有值才算）。"""
    out = {}
    for mk, it in items.items():
        src = S.SCEN_SRC["tw" if mk == "tw" else "us"]
        v = {}
        for g, ds in src.items():
            hs = [((it.get("D" + d) or {}).get("h")) for d in ds]
            v[g] = round(sum(hs) / len(hs), 1) if hs and all(h is not None for h in hs) else None
        out[mk] = v
    return out


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
    today = {mk: G.board(rows, on, mk, (G.NOW.get(mk) or {}).get("acts"), (G.NOW.get(mk) or {}).get("xon"))
             for mk in TODAY_MK if mk in asof}                       # VER 23：和景氣頁同一個溫度計＋清單
    for r in ST.get("rows") or []:
        if r["cat"] == "stock" and r.get("live"):
            on[r["id"]] = {"live": r["live"]}
    stk = [r for r in ST.get("rows") or [] if r["tier"] == "good"
           and ((r["cat"] == "strat" and "ins" not in (r.get("pay") or {})) or r["id"] in on)]   # 整組研究版本只列在表裡
    if ST.get("d"):
        asof["stk"] = ST["d"]
    rmk = [mk for mk in TODAY_MK if mk in CARDS or (OUT_DATA.parent / f"x9or-{mk}.json").exists()]
    return {"rows": rows, "on": on, "today": today, "stk": stk, "asof": asof, "run": R.get("run"), "bases": R.get("bases") or {},
            "last": R.get("last") or {}, "rmk": rmk, "items": {mk: ITEMS[mk] for mk in TODAY_MK if mk in ITEMS},
            "luck": R.get("luck"), "xs": XSP.results(), "pr": practice(), "find": find_data()}


def find_data(dirpath: Path | None = None) -> dict:
    """研究結論（findings）第 2～6 則的資料：景氣頁在同一個程序裡建頁時放在 CARDS[市場]["find"]；
    單獨建這一頁時讀上一版的 x9or-{市場}.json（沒有就只有第 1、7 則）。"""
    d = dirpath or OUT_DATA.parent
    out = {}
    for mk in TODAY_MK:
        f = (CARDS.get(mk) or {}).get("find")
        if f is None:
            path = d / f"x9or-{mk}.json"
            try:
                f = json.loads(path.read_text(encoding="utf-8")).get("find") if path.exists() else None
            except (OSError, ValueError):
                f = None
        if f:
            out[mk] = f
    return out


def practice() -> dict:
    """實測區（practpage；docs/lab_practice_page_plan.md）：研究檔＋今天每種用法該拿幾成（記進前瞻紀錄，只有 CI 寫回）＋前瞻成績。
    算不出來只印日誌、不擋訊號總覽。→ {"P": SG.pr, "R": 研究檔}。"""
    from . import practlive as PL
    from . import practpage as PP
    from . import practsim as PS
    from . import xstrat as XT
    R = PS.load()
    if not R:
        return {"P": {"ok": False}, "R": None}
    live, fw = {}, {}
    try:
        data = {mk: XT.data(mk) for mk in PS.S.MARKETS}
        for mk in PS.S.MARKETS:
            x = PL.targets(mk, G.NOW.get(mk), R, data[mk])
            if x:
                live[mk] = x
        L = PL.update(live)
        for mk, lg in (L.get("mk") or {}).items():
            if mk in data and lg:
                fw[mk] = PL.forward(lg, data[mk])
        since = {mk: min(lg) for mk, lg in (L.get("mk") or {}).items() if lg}
    except Exception as e:                                # noqa: BLE001
        print(f"[實測] 今天的部位或前瞻紀錄算不出來：{type(e).__name__}: {e}")
        since = {}
    return {"P": PP.payload(R, live, fw, since), "R": R}


def _pct(v) -> float | None:
    return None if v is None else round(100.0 * v, 1)


def _stat(st: dict | None):
    """→ [次數, 機率, 平常, 近 10 年次數, 近 10 年機率, 近 10 年平常, 判定, 回撤中位數, 平常的回撤中位數, 打亂測試 p]（%；
    回撤只有警示〔VER 3〕、p 只有算過的〔VER 9〕，尾端沒有的不列）。"""
    if not st:
        return 0
    p = st.get("p")
    out = [st.get("n") or 0, _pct(st.get("hit")), _pct(st.get("base")), st.get("n10"), _pct(st.get("hit10")),
           _pct(st.get("base10")), st.get("tier"), _pct(st.get("mdd")), _pct(st.get("mdd_base")),
           None if p is None else round(100.0 * p, 2)]
    while out[-1] is None:
        out.pop()
    return out


def _fe_pack(r: dict, keys: dict) -> tuple[dict, dict]:
    """預估之後（sigspec 第 4.14 節）→ ({方向: [預估機率%（整數）, k%, 格子, 預估多賺%（一位小數）, k_r%, k_r 的格子]},
    {方向: [年數, 當時過去多幾點, 之後多幾點]}＝這個訊號自己的逐年樣本外)。格子＝keys（鍵 → 編號，頁面的 SG.fwd.keys）；
    尾端沒有的不列（警示只有前三個）。不在範圍、次數不夠的方向不列。"""
    fe, ow = {}, {}

    def ki(k):
        if k is None:
            return None
        return keys.setdefault(k, len(keys))
    for d in (("buy",) if r.get("cat") == "buy" else ("up", "warn")):
        try:
            e = OOS.est(r, d)
        except Exception as ex:                                     # 只影響這一列的預估
            print(f"[sigpage] 預估之後算不出來 {r.get('id')}：{type(ex).__name__}: {ex}", flush=True)
            e = None
        if not e:
            continue
        v = [round(100 * e["fh"]), round(100 * e["k"]), ki(e.get("key"))]
        if e.get("fx") is not None:
            v += [round(100 * e["fx"], 1) + 0.0, round(100 * e["kr"]), ki(e.get("keyr") or e.get("key"))]   # + 0.0：不寫成 −0.0
        fe[d] = v
        o = e.get("own")
        if o:
            ow[d] = [o[0], round(100 * o[1], 1) + 0.0, round(100 * o[2], 1) + 0.0]
    return fe, ow


def fwd_meta(keys: dict) -> dict:
    """頁面解讀衰退表格子用的名稱（sigoos）＋這一頁用到的格子（編號 → 鍵）。"""
    return {"nb": list(OOS.NB_NAMES), "eb": list(OOS.EB_NAMES), "sg": OOS.SIGN_NAMES,
            "keys": [k for k, _ in sorted(keys.items(), key=lambda kv: kv[1])], "omin": S.FWD_OWN_MIN, "ok": OOS.load() is not None}


def _row(r: dict, keys: dict | None = None) -> list:
    x = {"vn": r.get("vn"), "sig": r.get("sig"), "var": r.get("var")}
    for k in ("desc", "base_name", "old", "unit", "monthly", "few"):
        if r.get(k) is not None:
            x[k] = r[k]
    if r.get("pay"):
        x["pay"] = G._r(r["pay"])
    b = r.get("buy") or {}
    if r.get("cat") == "buy":
        if b.get("lp") is not None:
            x["lp"], x["lpn"] = _pct(b["lp"]), b.get("lp_n")
        if b.get("b1") is not None:
            x["b1"] = _pct(b["b1"])
    if r.get("avg") is not None:
        x["avg"] = round(r["avg"], 2)
    q = r.get("ret") or {}
    c = G.ret_at(q, r.get("H") or 0, monthly=bool(q.get("hm")))    # VER 17：自己看多久那一期的報酬中位數、排除極端（%）
    if c and len(c) > 3 and c[3] is not None:
        x["med"] = _pct(c[3])
        if len(c) > 9 and c[9] is not None:
            x["trm"] = _pct(c[9])
    fe, ow = _fe_pack(r, {} if keys is None else keys)              # VER 18～19：預估之後（逐年樣本外校正）
    if fe:
        x["fe"] = fe
    if ow:
        x["ow"] = ow
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
            on[k] = {kk: v[kk] for kk in ("since", "n", "left", "event", "buy", "sell", "rem") if kk in v}
    keys: dict = {}
    out = {"rows": [_row(r, keys) for r in V["rows"]], "on": on, "mk": MK_NAMES, "cat": G.CAT_NAMES,
           "asof": V["asof"], "tiers": {t: [S.TIER_MARK[t], S.TIER_NAMES[t]] for t in S.TIERS},
           "stiers": {t: [S.TIER_MARK[t], S.STRAT_TIER_NAMES[t]] for t in S.TIERS if t in S.STRAT_TIER_NAMES},
           "dirs": S.DIR_NAMES, "words": S.VARIANT_NAMES, "rmk": V.get("rmk") or [], "cards": CARD_NAMES,
           "inds": indicators(V["rows"]), "icat": IND_CATS, "fac": FACETS, "sub": SUBS, "it": V.get("items") or {}, "dimn": dim_names(),
           "chart": CHART, "pxn": PX_NAMES, "inm": ind_names(), "scen": scen_meta(),
           "scnv": scen_values(V.get("items") or {}), "scdn": S.SCEN_DIM_NAMES,
           "hit": {d: round(100 * v) for d, v in S.HIT_MIN.items()}, "eg": round(100 * S.EDGE_GOOD), "er": round(100 * S.EDGE_REF),
           "fwd": fwd_meta(keys), "n10": S.RECENT_N, "nmin": S.N_MIN, "sn": S.STAR_N, "lp": round(100 * S.LUCK_P), "lfn": S.LUCK_FEW_N, "lpf": round(100 * S.LUCK_P_FEW), "ld": S.LUCK_DRAWS, "rh": list(S.RET_H), "pd": list(S.PATH_D), "rhm": list(S.RET_H_M), "rmin": S.RET_N_MIN}
    out["xs"] = XSP.payload(V.get("xs") or {})          # 總經策略（xstratspec；點開的淨值與每一筆在 x9xh.json）
    out["pr"] = (V.get("pr") or {}).get("P") or {"ok": False}   # 實測區（practpage；每一格的細節在 x9pr-{市場}.json）
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _rcell(c):
    """報酬一格 → [次數, 平均, 25%, 中位數, 75%, 上漲比例, 中途最多跌中位數, 最差 10%, 最差一次, 排除極端, 去掉最好一次]
    （後面都是 %，一位小數；最後兩個 VER 17 起才有）。"""
    return None if c is None else [c[0]] + [None if v is None else round(100.0 * v, 1) for v in c[1:]]


def ret_pack(q: dict) -> dict:
    out = {"s": [_rcell(c) for c in q.get("s") or []],
           "p": [None if p is None else [round(100.0 * v, 1) for v in p] for p in q.get("p") or []]}
    if q.get("hm"):
        out["hm"] = 1
    return out


def ret_json(V: dict) -> tuple[dict, dict]:
    """訊號觸發後的報酬（sigspec 第 4.11 節）：{訊號: {s, p, b＝平常的鍵}}、{平常的鍵: {s, p}}。"""
    bases = V.get("bases") or {}
    ret, rb = {}, {}
    for r in V["rows"]:
        q = r.get("ret")
        if not q:
            continue
        o = ret_pack(q)
        bk = q.get("bk")
        if bk and bk in bases:
            rb.setdefault(bk, ret_pack(bases[bk]))
            o["b"] = bk
        elif q.get("base"):
            bk = r["id"] + ":b"
            rb[bk] = ret_pack(q["base"])
            o["b"] = bk
        ret[r["id"]] = o
    return ret, rb


def detail_json(V: dict) -> str:
    """每一次的清單（點開才下載）＋個股代號的名稱＋訊號觸發後的報酬（VER 5）。總經策略的淨值與每一筆在 x9xh.json（xspage）。"""
    from . import store
    occ = {r["id"]: r.get("occ") or [] for r in V["rows"]}
    ret, rb = ret_json(V)
    codes = {o[1] for r in V["rows"] if r["cat"] == "stock" for o in (r.get("occ") or [])}
    for r in V["rows"]:
        if r.get("live"):
            codes |= set(r["live"])
    nm = {**(store.read_json("names_hist.json", {}) or {}), **(store.read_json("names_mkt.json", {}) or {}),
          **(store.read_json("names.json", {}) or {})}
    live = {r["id"]: r["live"] for r in V["rows"] if r.get("live")}
    skip = {r["id"]: r["skip"] for r in V["rows"] if r.get("skip")}   # 出現了但沒算進次數的（docs/lab_audit_plan.md 第 3.4 節）
    return json.dumps({"occ": occ, "names": {c: nm[c] for c in sorted(codes) if c in nm}, "live": live, "ret": ret, "rb": rb,
                       "skip": skip}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ── 頁面 ───────────────────────────────────────────────────────────────────

def _hz(r: dict) -> str:
    if r["cat"] == "buy":
        return "3 個月"
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
        what = f"買進之後 {h}上漲的機率"
    fe = _fe(r)
    if fe:                                            # VER 18～19：預估之後（逐年樣本外校正）；VER 21 起今天的清單每一列都有
        out = (f'{what}：過去 {st["hit"] * 100:.0f}% → 預估之後 <b>{fe["fh"] * 100:.0f}%</b>'
               f'（隨便挑一天 {st["base"] * 100:.0f}%）')
    else:
        out = f'{what} <b>{st["hit"] * 100:.0f}%</b>（隨便挑一天 {st["base"] * 100:.0f}%）'
    med = _med(r) if d != "warn" and not r.get("xk") else None      # 跨期間的列只有機率（報酬是訊號自己看多久的）
    if med is not None:
        out += f'・報酬中位數 {_sgn(med)}'
        if fe and fe.get("fx") is not None:
            out += f'，預估之後比隨便挑一天{_more(fe["fx"])}'
    out += f'・出現過 {st["n"]} 次' + ("（次數少）" if st["n"] < S.STAR_N and r.get("cat") not in ("stock", "strat") else "")
    if d == "warn" and st.get("mdd") is not None and st.get("mdd_base") is not None:
        out += f'・回撤中位數 {st["mdd"] * 100:.0f}%（隨便挑一天 {st["mdd_base"] * 100:.0f}%）'
    return out


def tq_stats(r: dict) -> str:
    """今天的重點一列的數字（sigspec 第 5 節 ④b，VER 23；看什麼寫在清單標題）：過去的機率（隨便挑一天）、報酬中位數（偏多、買點，
    訊號自己的看多久才有）或回撤中位數（警示）、出現過幾次。"""
    d = r["d"]
    st = r.get("st") or r[d]
    out = f'<b>{st["hit"] * 100:.0f}%</b>（隨便挑一天 {st["base"] * 100:.0f}%）'
    if d != "warn":
        med = _med(r) if not r.get("xk") else None                  # 跨期間的列只有機率（報酬是訊號自己看多久的）
        if med is not None:
            out += f'・報酬中位數 {_sgn(med)}'
    elif st.get("mdd") is not None and st.get("mdd_base") is not None:
        out += f'・回撤中位數 {st["mdd"] * 100:.0f}%（隨便挑一天 {st["mdd_base"] * 100:.0f}%）'
    return out + f'・出現過 {st["n"]} 次' + ("（次數少）" if st["n"] < S.STAR_N else "")


def _fe(r: dict) -> dict | None:
    """預估之後（sigspec 第 4.14 節）：今天的清單（第 5 節 ④，VER 21）每一列都帶好了（"fe"；跨期間的是 sigoos.est_x）；
    沒帶的★、◆ 列才在這裡算（VER 18～20 的用法）。研究檔沒有、不在範圍＝None。"""
    if "fe" in r:
        return r["fe"]
    if r.get("tier") not in ("good", "rare") or r.get("xk") or not r.get("d"):
        return None
    try:
        return OOS.est(r, r["d"])
    except Exception as ex:                           # 只影響這一行的預估，不擋頁面
        print(f"[sigpage] 預估之後算不出來 {r.get('id')}：{type(ex).__name__}: {ex}", flush=True)
        return None


def _more(v: float) -> str:
    """多賺（0～1）→「多 0.9%」／「少 0.2%」／「差不多」（一位小數）。"""
    x = round(100.0 * v, 1)
    return f"多 {x:.1f}%" if x > 0 else f"少 {abs(x):.1f}%" if x < 0 else "差不多"


def _med(r: dict) -> float | None:
    """這個訊號自己看多久那一期的報酬中位數（VER 17 的主要數字，第 4.11 節；個股訊號、策略沒有就 None）。"""
    q = r.get("ret") or {}
    c = G.ret_at(q, r.get("H") or 0, monthly=bool(q.get("hm")))
    return None if not c or len(c) < 4 or c[3] is None else c[3]


def _sgn(v: float) -> str:
    """報酬（0～1）→ +3.1%／−0.4%。"""
    x = round(100.0 * v, 1)
    return f'{"+" if x > 0 else "−" if x < 0 else ""}{abs(x):.1f}%'


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
    """現在成立的那一筆（docs/lab_audit_plan.md 第 3.5 節）：哪天出現（成立）、照規則哪天收盤進場、持有到哪天
    （sigcat.trade_dates；成績就是這樣算的：事件型＝出現隔天收盤進場，狀態型＝今天看到、下一個交易日收盤進場）。"""
    tr = f'・{_dy(n["buy"], ref)} 收盤進場、持有到 {_dy(n["sell"], ref)}' if n.get("buy") and n.get("sell") else ""
    if n.get("left") is not None:
        if not tr:
            return f'{_dy(n["since"], ref)} 出現，還看 {n["left"]} 天'
        rem = f'（還有 {n["rem"]} 個交易日）' if n.get("rem") is not None else ""
        return f'{_dy(n["since"], ref)} 出現{tr}{rem}'
    if n.get("event"):
        return f'{_dy(n["since"], ref)} 出現{tr}'
    return f'{_dy(n["since"], ref)} 起成立{tr}'


def today_html(V: dict) -> str:
    """今天有效的訊號（sigspec 第 5 節 ④b，VER 23）：每個市場一張卡＝和景氣頁同一個溫度計＋短線｜中線｜長線切換的偏多、警示清單
    （heatviz.today_core；點一列看這一頁的指標）＋總經策略一行；最後個股。"""
    from . import heatviz as VZ
    cards = []
    for mk in TODAY_MK:
        T = V["today"].get(mk)
        if T is None:
            continue
        head = f'<h3>{_e(MK_NAMES[mk])}<span class="sub">資料到 {_e(_d(V["asof"].get(mk)))}</span></h3>'
        xl = XSP.today_line(mk, V["xs"]) if V.get("xs") else ""          # 總經策略縮成一行，連到策略頁
        xl = f'<p class="sgxs">{xl}</p>' if xl else ""
        body = VZ.today_core(T, mk, V["asof"].get(mk), panel=False, cal=False)
        cards.append(f'<div class="sgk">{head}{body}{xl}</div>')
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
                 '<p class="note">個股是另一套判定（★ 好訊號、好策略），沒有預估之後；策略現在持有什麼、下一批什麼時候買，看'
                 '<a href="x9.html#v=opp">策略頁的個股策略</a>。</p></div>')
    return ('<section class="sec" id="today"><h2>今天有效的訊號<span class="sub">現在成立、過去之後的機率比隨便挑一天高 5 點以上的'
            '（和景氣頁的溫度計同一套）；偏多（含大跌後買點）、警示兩邊；同一個項目同一段只列一種；過去常一起出現的併成一列；'
            '點溫度計的一列切換持有多久，點清單的一列看那個指標；總經策略每個市場一行，點了到策略頁</span></h2>'
            f'<div class="sgt">{"".join(cards)}</div></section>')


FWD_ROWS = (("偏多・看 1 個月", "up", S.H_TECH), ("偏多・看 3 個月", "up", S.H_CRASH), ("偏多・看 12 個月", "up", S.H_BUB),
            ("警示・看 1 個月", "warn", S.H_TECH), ("警示・看 3 個月", "warn", S.H_CRASH), ("警示・看 12 個月", "warn", S.H_BUB),
            ("大跌後買點・看 3 個月", "buy", S.H_BUY))


def _kp(c: dict | None, f: str = "k") -> str:
    return "—" if not c or c.get(f) is None else f"{c[f] * 100:.0f}%"


def fwd_html() -> str:
    """預估之後怎麼算（sigspec 第 4.14 節，VER 18～19）：衰退表（次數合併的 L2 格、留下來的比例）＋一句結論，數字都由研究檔算；
    研究檔沒有就不列。"""
    T = OOS.load()
    if not T:
        return ""
    C = T.get("cells") or {}

    def c(d, H, b, g):
        return C.get(OOS.key(d, H, b, g))

    def tbl(rows, f):
        head = ('<tr><th class="l">過去比隨便挑一天</th>' + "".join(f"<th>{_e(n)}</th>" for n in OOS.EB_NAMES)
                + "<th>不比平常低（全部）</th></tr>")
        body = "".join(f'<tr><td class="l">{_e(nm)}</td>' + "".join(f"<td>{_kp(c(d, H, None, g), f)}</td>" for g in range(5))
                       + f"<td><b>{_kp(c(d, H, None, 'p'), f)}</b></td></tr>" for nm, d, H in rows)
        return f'<div class="sgfwr"><table class="sgfw"><thead>{head}</thead><tbody>{body}</tbody></table></div>'

    def pk(d, H, f="k"):
        return _kp(c(d, H, None, "p"), f)

    def px(d, H):                                     # 跨期間（第 4.14 節 ⑧，VER 21）：x 的 L3 格
        return _kp(C.get(OOS.key(d, H, None, "p", x=True)), "k")
    up = [(nm, d, H) for nm, d, H in FWD_ROWS if d != "warn"]
    big = [_kp(c("up", S.H_TECH, b, 4)) for b in range(3)]
    txt = (f'偏多的優勢看 1 個月留下 {pk("up", S.H_TECH)}、3 個月 {pk("up", S.H_CRASH)}、12 個月 {pk("up", S.H_BUB)}；'
           f'警示看 1 個月 {pk("warn", S.H_TECH)}、3 個月 {pk("warn", S.H_CRASH)}、12 個月 {pk("warn", S.H_BUB)}。'
           f'報酬多賺（比隨便挑一天多賺的部分）偏多看 1 個月留下 {pk("up", S.H_TECH, "kr")}、3 個月 {pk("up", S.H_CRASH, "kr")}、'
           f'12 個月 {pk("up", S.H_BUB, "kr")}。次數越多留越多（偏多看 1 個月、過去高 20 點以上：'
           + "、".join(f"{n} {k}" for n, k in zip(OOS.NB_NAMES, big)) + "）。")
    return ('<dt>預估之後</dt><dd>上面的機率與報酬都是「過去」的成績；之後通常會往下修。做法：每年 1 月 1 日只用之前的資料算每個訊號的機率與報酬，'
            '再看那一年訊號出現之後實際的結果，和同一年隨便哪天買比（五個市場、所有訊號合併，'
            f'{(T.get("nrec") or 0) - (T.get("nrec_x") or 0):,} 筆「訊號 × 年」）。過去比隨便挑一天多 X 個百分點的訊號，之後平均只多「留下來的比例 × X」。'
            f'<b>{_e(txt)}</b>'
            '預估之後的機率＝隨便挑一天 ＋ 留下來的比例 ×（過去 − 隨便挑一天）；預估之後多賺＝報酬留下來的比例 ×（過去的報酬中位數 − 隨便挑一天的報酬中位數）。'
            f'每個訊號用和它同一類的格子（方向、看多久、出現過幾次：{"、".join(OOS.NB_NAMES)}、過去比平常高幾點）；'
            f'一格至少 {S.FWD_MIN_N} 筆、{S.FWD_MIN_CL} 個「市場 × 年」才算，不夠就把次數合併、再不夠只分比平常高或低；'
            '留下來的比例截在 0～100%（之後沒有優勢＝跟隨便挑一天一樣）。這是所有訊號平均下來的修正，個別訊號之後可能更好或更差；'
            '產業泡沫、個股訊號、策略沒有預估之後。下面兩張表是次數合併後的比例。'
            + (f'原本看別的期間的訊號放到另外兩段期間（今天的清單「原本看…」那幾列），另外一套逐年檢查（{T["nrec_x"]:,} 筆，'
               f'不借上面的比例）：偏多看 1 個月留下 {px("up", S.H_TECH)}、3 個月 {px("up", S.H_CRASH)}、12 個月 {px("up", S.H_BUB)}；'
               f'警示看 1 個月 {px("warn", S.H_TECH)}、3 個月 {px("warn", S.H_CRASH)}、12 個月 {px("warn", S.H_BUB)}。'
               if T.get("nrec_x") else "")
            + f'<p class="sgfwh">上漲（或大跌）的機率，優勢留下多少</p>{tbl(FWD_ROWS, "k")}'
            f'<p class="sgfwh">報酬多賺留下多少（偏多、大跌後買點）</p>{tbl(up, "kr")}</dd>')


def method_html(luck: dict | None = None) -> str:
    """名詞與判定方式（sigspec 第 3、3.5 節；VER 17）；luck＝研究檔的「運氣會產生幾個 ★、◆」
    （{市場: {方向: [實際 ★, 運氣會產生的 ★, 實際 ◆, 運氣會產生的 ◆]}}）。"""
    lk = ""
    if luck:
        tot = {d: [sum(m[d][i] for m in luck.values() if len(m[d]) > i) for i in range(4)] for d in ("up", "warn")}
        lk = (f'<dt>運氣會產生幾個 ★、◆</dt><dd>把每一個訊號出現的日子亂排過、當成真的，用同一套判定再算一次（只用機率那幾條，報酬那兩條沒算，'
              f'所以運氣的個數會略多）：五個市場的偏多（含大跌後買點）★ {tot["up"][0]} 個，運氣大約也會產生 {tot["up"][1]:.0f} 個；'
              f'◆ {tot["up"][2]} 個，運氣大約 {tot["up"][3]:.0f} 個。警示 ★ {tot["warn"][0]} 個、運氣大約 {tot["warn"][1]:.0f} 個；'
              f'◆ {tot["warn"][2]} 個、運氣大約 {tot["warn"][3]:.0f} 個。'
              '意思是：<b>絕對成績好的訊號，大部分是大盤本身就會給的</b>——指數長期往上，隨便哪天買，之後上漲的機率本來就高。'
              '要找「這個時機比平常好」的，看「多幾個百分點」與「亂排 X%」：多得越多、亂排越難做到，越不像只是大盤本身。'
              '（不含產業泡沫、個股。）</dd>')
    cost = f'台股 {S.ABS_COST["tw"] * 200:g}%、美股 {S.ABS_COST["spx"] * 200:g}%'
    return ('<section class="sec" id="mth"><details class="sgmth"><summary>名詞與判定方式</summary>'
            '<p>每個指標有幾種訊號（例：RSI 的「過冷中」「進入過熱」）。每一種都寫清楚「怎樣算出現」「怎樣算中了」「看多久」，'
            '數過去出現之後中了幾成，和同一段期間「隨便挑一天」比，再看進場之後的報酬。只描述過去發生的比例。</p><dl class="sgdl2">'
            '<dt>之後上漲的機率</dt><dd>偏多訊號：出現的隔天收盤買，過了「看多久」之後收盤比買價高的比例。'
            '狀態型（例：過冷中）＝狀態中的每一天都當成買進一次、每一天一樣重。</dd>'
            '<dt>之後大跌的機率</dt><dd>警示訊號：出現的隔天收盤算起，「看多久」之內出現一段最大回撤到門檻的比例（最大回撤＝期間最高收盤到之後最低收盤的跌幅，'
            '先漲再跌也算）。門檻：台股 1 個月 8%、3 個月 10%；美股換算成和台股一樣常見；12 個月一律 20%。另列每一次最大回撤的中位數。</dd>'
            '<dt>買進之後上漲的機率（大跌後買點）</dt><dd>大跌（5 日急跌、從 60 日高點跌 10%）之後，照規則（隔天就買、固定等 10 天、等落底訊號）買進，'
            '3 個月後收盤比買價高的比例，和隨便挑一天比（2026-10-21 起；之前看「買進價落在這一波的下三分之一」，那個比例照列在每一列的說明裡）。</dd>'
            '<dt>隨便挑一天</dt><dd>同一段期間裡隨便挑一天、用同樣算法的比例。好訊號至少不能比它差（2026-10-22 起；之前要多 10 個百分點）。'
            '美股隨便挑一天，3 個月後上漲的機率就有六成多，所以機率高不一定是時機好。</dd>'
            '<dt>多幾個百分點</dt><dd>機率減掉隨便挑一天。多得越多，越代表這個時機比平常好；差不多＝大盤本身的表現。</dd>'
            f'<dt>報酬中位數、排除極端、去掉最好一次</dt><dd>進場之後持有「看多久」的報酬（指數本身、不含股息）。中位數＝一半比它好、一半比它差，'
            f'是主要的數字；排除極端＝去掉最好和最差各 {S.TRIM_Q * 100:.0f}%（不到 {S.TRIM_N} 次時各去掉一次）之後的平均；'
            '去掉最好一次＝去掉最好的那一次之後的平均。去掉最好一次之後的平均剩不到原本的一半，代表成績靠少數幾次撐起來，頁面會標出來。'
            '狀態型（例：過熱中）狀態中的每一天一樣重；排除極端、去掉最好一次以「一段」為單位、照天數加權。點開一個指標看 1 天～1 年的表。</dd>'
            f'<dt>近 10 年也成立嗎</dt><dd>只看最近 10 年：✓ 機率過了門檻（偏多 ≥ {S.HIT_MIN["up"] * 100:.0f}%、警示 ≥ {S.HIT_MIN["warn"] * 100:.0f}%），'
            f'也不比近 10 年隨便挑一天差；△ 兩條只過一條；✗ 都沒過；— 近 10 年不到 {S.RECENT_N} 次，不看。'
            f'個股訊號照舊：✓ 多 {S.EDGE_GOOD * 100:.0f} 個百分點以上、△ 多 {S.EDGE_REF * 100:.0f} 個百分點以上。</dd>'
            '<dt>出現過幾次</dt><dd>事件型（例：跌破季線）出現那天算一次，之後看多久的期間內再出現不算新的一次（之後的漲跌和前一次重疊，'
            '算同一次；指標頁的「最近幾次」與走勢圖用灰色標出這些沒算進去的）；狀態型（例：過熱中）連續的一段算一次，'
            '中間短暫中斷（不到 20 個交易日）還算同一段，但中斷時如果到過相反的極端（例：過冷中間變過熱）就是兩段。'
            '機率是狀態中的每一天一樣重（2026-10-22 起）：之前是每一段先算、再平均，但一段的長短取決於之後的價格'
            '（過冷的一段結束，多半是價格反彈了），每一段一樣重會把「之後很快反轉」的短段放大、高估過冷之後上漲的機率。</dd>'
            '<dt>持有多久、哪天進場</dt><dd>機率與報酬都是「訊號出現隔一個交易日收盤進場、持有看多久那麼久（1 個月＝20 個交易日、'
            '3 個月＝60、12 個月＝250）」算的。現在成立的訊號寫出照規則的那一筆：事件型＝出現隔天收盤進場、持有到哪一天；'
            '狀態型＝今天看到、下一個交易日收盤進場、持有到哪一天。事件出現幾天之後才進場，不是這筆成績。</dd>'
            '<dt>現在成立</dt><dd>狀態型＝最新一天還在狀態中；事件型＝出現之後還在看多久的期間內，而且同一個項目之後沒有出現相反的讀數'
            '（例：RSI 進入過熱之後又變過冷，進入過熱就不算現在成立；站回月線之後又跌破月線，站回月線就不算）。'
            '資料停住沒更新的項目（照公布時程應該已經有新資料卻沒有）不算現在成立。</dd>'
            f'<dt>打亂日子測試（亂排 X%）</dt><dd>把這個訊號出現的日子整段挪到別的時間（保留它自己出現的節奏，只打斷和之後漲跌的對應），亂排 {S.LUCK_DRAWS} 次，'
            '看有多少比例做得到一樣高的機率——比例越小，越不像運氣。2026-10-22 起只當參考、不參與判定（個股訊號照舊參與）。'
            '大跌後買點與個股偏多訊號是和同一批事件的對照比，改成在每一次事件裡隨機對調「訊號」和「對照」的結果。'
            f'次數少的訊號就算每次都中，亂排做得到一樣準的比例也常超過 {S.LUCK_P * 100:.0f}%（例：8 次、平常 59%，每次都中時亂排也有約 2.5% 做得到）。</dd>'
            f'{lk}{fwd_html()}'
            f'<dt>今天有效的訊號（景氣頁今天的重點、溫度計也一樣）</dt><dd>現在成立、出現過 {S.N_MIN} 次以上、而且過去出現之後的機率比隨便挑一天高 '
            f'{S.THERMO_EDGE * 100:g} 個百分點以上的就列（使用者 2026-10-21 定的寬鬆規則：溫度計是看現在整體偏哪邊），★／◆ 判定不決定列不列。'
            '三類：<b>偏多</b>＝之後上漲的機率高；<b>買點</b>＝大跌後照規則買進、之後 3 個月上漲的機率高；'
            '<b>大跌風險</b>＝之後出現大回撤的機率高。上漲機率比平常低的不列：逐年檢查看，這種訊號之後反而比平常容易漲。'
            '同一個項目同一段（持有 1／3／12 個月）只留差最多的一個，偏多和大跌風險同時有的標「震盪」；過去常一起出現的併成一列。'
            '原本看別的期間的訊號也用它過去在另外兩段期間的機率算一次（標「原本看…」）。'
            f'<b>之後也成立</b>＝預估之後（上一段的逐年檢查）仍比隨便挑一天高 {S.LIST_GAP * 100:g} 點以上，排在前面；沒有標的只代表過去的成績。'
            f'出現不到 {S.STAR_N} 次的標「次數少」。（2026-10-22 白天曾改成只列預估之後仍差 {S.LIST_GAP * 100:g} 點以上的，偏多那一邊幾乎全空，同日改回。）</dd>'
            f'<dt>判定</dt><dd><b>★ 好訊號</b>（2026-10-22 起看絕對成績）：至少 {S.STAR_N} 次、機率 ≥ {S.HIT_MIN["up"] * 100:.0f}%（警示 ≥ {S.HIT_MIN["warn"] * 100:.0f}%）、'
            f'不比隨便挑一天差、近 10 年也成立（近 10 年有 {S.RECENT_N} 次以上時）；偏多與大跌後買點另外要報酬中位數與排除極端的平均都比來回成本高（{cost}）。'
            f'<b>◆ 難得機會</b>：同樣的門檻都過了，但只出現 {S.N_MIN}～{S.STAR_N - 1} 次；不算 ★（次數少的機率，之後通常會往下修不少，只當參考）。'
            f'<b>○</b>：沒有過門檻。<b>—</b>：不到 {S.N_MIN} 次，照列數字但不判定。'
            f'個股訊號照舊：比隨便挑一天多 {S.EDGE_GOOD * 100:.0f} 個百分點以上、近 10 年也成立，而且亂排做得到一樣準的不到 {S.LUCK_P * 100:.0f}%'
            f'（次數少於 {S.LUCK_FEW_N} 次的不到 {S.LUCK_P_FEW * 100:.0f}%）＝★；門檻過了但亂排也常做得到＝<b>● 可能是運氣</b>。'
            '警示類過去的事後驗證比偏多弱（用 2016 年以前選出來的警示，2016 年以後多數沒有比平常準），只當提醒。</dd>'
            '<dt>看多久</dt><dd>技術面與技術事件 1 個月；籌碼、資金、大跌風險、面向事件、邊際變化 3 個月；基本面與泡沫 12 個月。</dd>'
            f'<dt>總經策略</dt><dd>照原作者的規則與參數（RSI(2)、VIX 衝刺、月底月初；Coppock 曲線、VIX 衝上 40、Zweig 寬度衝刺、跟進日、季線乖離 −15%；'
            f'Halloween、10 個月均線、200 日均線、12 個月動能）'
            f'在指數上做一遍，看交易成績（使用者 2026-10-20 選定：成績過關就算，打亂測試只標示）。交易型＝至少 {XS.TR_N_MIN} 筆、'
            f'勝率 ≥ {XS.TR_WIN * 100:.0f}%、比「隨便挑一天、抱一樣多天」高 {XS.TR_EDGE * 100:.0f} 個百分點以上、扣成本後平均每筆賺錢；'
            '進出型＝最大回撤比買進持有少三分之一以上，而且年化 ÷ 最大回撤不輸買進持有。'
            f'落底型＝訊號出現隔天收盤買、抱原作者說的期間（1 個月～1 年），至少 {XS.DIP_N_MIN} 次、抱完賺錢的比例 ≥ {XS.DIP_WIN * 100:.0f}% 而且不比隨便挑一天差、'
            '扣成本後的報酬中位數與排除極端的平均都賺錢（2026-10-22 起看絕對成績；落底訊號一年只有幾次，交易型的 30 筆用不上）。'
            '★ 好策略＝全期間、近 10 年、參數鄰近（換附近的參數，三分之二以上也過）都過；● 可參考＝全期間過、後兩項沒過。'
            '看收盤才知道的訊號一律隔天收盤買賣（看網頁做得到的最早時點），原作者的當天收盤另列參考；'
            '台股 RSI(2) 例外：用台指期在訊號當天收盤前買賣（現貨 13:30 收盤、台指期 13:45 收盤），頁面每天寫下一個交易日的買進、出場價位，'
            '隔天收盤另列參考。台股 RSI(2)、月底月初用台指期的成本（使用者 2026-10-21 選定）。'
            f'規格 arm/lab/xstratspec.py（VER {XS.VER}），在算正式成績之前寫定。'
            '全部策略現在的狀態、每一條的細節在<a href="x9.html#v=mac">策略頁的總經策略</a>。</dd></dl>'
            '<p><b>個股訊號</b>：同一檔 5 個交易日內重複只算一次，隔天開盤買、持有 20 個交易日，扣來回成本後賺錢算中；'
            '隨便挑一天＝同一段期間加權指數上漲的比例（資料從 2026 年 7 月起，大多是上漲行情）。'
            f'集體撤退是警示：之後 20 個交易日內最大回撤 {S.STOCK_MDD * 100:.0f}% 以上算中，隨便挑一天＝同一段期間所有 ETF 持股的同樣比例。'
            f'<b>個股策略</b>：至少 {S.STRAT_N_MIN} 筆（不到 {S.STRAT_FEW} 筆標「次數少」，照樣判定），報酬型態過（賺錢比例 ≥ 60% 而且每月平均 ≥ 1%，'
            '或賺錢比例 ≥ 40%、賺賠比 ≥ 2.5、每月平均 ≥ 2%）＝★；平均每筆賺錢但沒過＝●。策略頁個股策略的推薦用這個判定。</p>'
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
跟同一段期間「隨便挑一天」比，以及進場之後報酬的中位數。★ 好訊號＝出現過 15 次以上、機率夠高、不比隨便挑一天差、近 10 年也成立，
偏多的報酬中位數扣掉成本也賺錢；◆ 難得機會＝門檻都過了、但只出現 5～14 次。機率高不一定是時機好（大盤本身長期往上），比隨便挑一天多幾個百分點才是。
照書上的規則買賣大盤指數的「總經策略」在頂欄的<a href="x9.html#v=mac">策略頁</a>（這裡的「策略」一類也查得到），★ 好策略＝交易成績過關、近 10 年與附近的參數也成立。
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
         '<p class="note">一列一個指標（例：RSI、融資餘額水位）；分類和景氣頁的面向一樣（基本面、籌碼、資金、技術），景氣頁看到哪個面向熱，就點哪一類。'
         '點一列看它現在的數值、走勢，和它每一種訊號過去出現之後的結果。照書上的規則買賣大盤指數的總經策略，全部的狀態在<a href="x9.html#v=mac">策略頁</a>。</p>'
         '<div class="sgbar"><input id="sgq" type="search" placeholder="搜尋：指標名稱（例：融資、RSI、季線）" autocomplete="off">'
         '<div class="sgchips" data-k="mk"></div><div class="sgchips" data-k="c1"></div><div class="sgchips sgc2" data-k="c2" hidden></div>'
         '<details class="sgadv"><summary>更多篩選<span id="sgadvn"></span></summary><div class="sgadvb">'
         '<div class="sgchips" data-k="tier"></div><div class="sgchips" data-k="dir"></div>'
         '<div class="sgopt"><label><input type="checkbox" id="sgnow"> 只看現在有訊號的</label>'
         '<button type="button" id="sgcsv">下載 CSV（每一種訊號）</button></div></div></details></div>'
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
    """研究結論（2026-10-22 改版，docs/lab_research_v2_plan.md）：每個市場七則白話問答（findings），最上面「現在適用」；
    原本的實測細節與四張研究卡（每個市場一個檔、點了才載入）收在最下面的「完整研究表」。"""
    from . import findings as FD
    from . import practpage as PP
    rmk = V.get("rmk") or []
    PRV = V.get("pr") or {}
    P = PRV.get("P") or {"ok": False}
    R = PRV.get("R")
    find = V.get("find") or {}
    mks = [mk for mk in TODAY_MK if mk in find or mk in rmk or (R and mk in (R.get("mk") or {}))]
    if not mks:
        return ""
    kp = None
    try:
        kp = FD.keep()
    except Exception as e:                                # noqa: BLE001
        print(f"[研究結論] 第 7 則算不出來：{type(e).__name__}: {e}", flush=True)
    first = mks[0]
    chips = "".join(f'<button type="button" class="sgch{" on" if mk == first else ""}" data-r="{mk}">{_e(MK_NAMES[mk])}</button>'
                    for mk in mks)
    blocks = []
    for mk in mks:
        try:
            mx = FD.money(R, mk, P) if R else None
        except Exception as e:                            # noqa: BLE001 —— 第 1 則算不出來只少那一則
            print(f"[研究結論] {mk} 第 1 則算不出來：{type(e).__name__}: {e}", flush=True)
            mx = None
        blocks.append(FD.market_html(mk, find.get(mk), mx, kp, show=(mk == first)))
    pr = PP.html(P)
    full = ""
    if pr or rmk:
        full = ('<details class="rffull" id="rfull"><summary><b>完整研究表</b>：每週走勢、逐年成績、四張研究卡的全部數字（要核對時再打開）</summary>'
                '<div class="rffb">'
                + (f'<h3 class="sgrh">照網頁做：每週走勢與逐年成績</h3>{pr}' if pr else "")
                + (f'<h3 class="sgrh">研究卡<span class="sub">{_e("、".join(CARD_NAMES[c] for c in CARD_ORDER))}；跟著上面選的市場</span></h3>'
                   '<div id="rbox"><p class="note">打開這一區時載入上面選的市場的研究卡。</p></div>' if rmk else "")
                + "</div></details>")
    return ('<section class="sec" id="research"><h2>研究結論<span class="sub">研究過的 7 個問題：答案、和平常比、現在是不是這樣</span></h2>'
            f'<div class="sgchips" id="rmk">{chips}</div>' + "".join(blocks)
            + '<p class="rffoot">數字都是過去發生的比例，不是買賣指示。每一則下面的「過去每一次」列出每次發生的日期與之後的結果，可以自己核對。</p>'
            + full + "</section>")


def card_json(mk: str, c: dict) -> str:
    """一個市場的研究卡，各自收在一個 <details>（點開才展開；#r=市場:卡 會打開那一張）；find＝研究結論第 2～6 則的資料
    （單獨建訊號總覽時從這裡讀回來）。"""
    html = "".join(f'<details class="sgrc" id="rc-{k}"><summary>{_e(CARD_NAMES[k])}</summary>{c[k]}</details>'
                   for k in CARD_ORDER if c.get(k))
    out = {"mk": mk, "d": c.get("d"), "html": html}
    if c.get("find"):
        out["find"] = c["find"]
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


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
    body = today_html(V) + TABLE + research_html(V) + method_html(V.get("luck"))
    if not V["rows"]:
        body = '<p class="warn">還沒有研究結果（scripts/run_sig.py）。</p>'
    from . import findings as FD
    from . import practpage as PP
    return appnav.finish(_HTML.replace("{{APPTAB}}", appnav.bar("sig")).replace("{{CSS}}", HCSS + appnav.CSS + VZ.CSS + CP.CSS + XP.CSS + QP.CSS + BP.CSS + CSS + PP.CSS + FD.CSS)
            .replace("{{ASOF}}", _e(("資料到 " + asof) if asof else "")).replace("{{BODY}}", body)
            .replace("{{DATA}}", page_json(V)).replace("{{PANEL}}", PANEL).replace("{{JS}}", JS))


def build(out: Path = OUT, data_out: Path = OUT_DATA) -> bool:
    V = view()
    changed = False
    files = [(data_out.parent / f"x9or-{mk}.json", card_json(mk, c)) for mk, c in sorted(CARDS.items())]
    PR = (V.get("pr") or {}).get("R")
    if PR:                                                # 實測區每個市場的細節與每週序列（點到那個市場才下載）
        from . import practpage as PP
        files += [(data_out.parent / f"x9pr-{mk}.json", PP.market_json(PR, mk)) for mk in S.MARKETS if mk in (PR.get("mk") or {})]
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
.sgnm{font-weight:600;font-size:14px;flex:0 1 auto;min-width:0}.sgln{flex:1 1 100%;font-size:12.5px;color:var(--ink2);padding-left:20px}
.sgln b{color:var(--ink)}.sgs{color:var(--mut);margin-left:6px}
.sgnone{font-size:13px;color:var(--ink2);margin:4px 0}
.sgxs{margin:6px 0 0;padding-top:6px;border-top:1px dashed var(--line2);font-size:12.5px;line-height:1.6}
.sgtk{display:inline-block;width:14px;text-align:center;font-weight:700}
.sgtk-good{color:var(--acc)}.sgtk-rare,.sgtk-ref{color:var(--ink2)}.sgtk-none,.sgtk-few{color:var(--mut)}
.sgd{font-size:11.5px;padding:0 7px;border-radius:999px;border:1px solid var(--line2);white-space:nowrap}
.sgd-up{color:var(--t4);border-color:var(--t4)}.sgd-warn{color:var(--t3);border-color:var(--t3)}.sgd-buy{color:var(--p0);border-color:var(--p0)}
.sgbar{display:flex;flex-direction:column;gap:6px;margin:6px 0 10px}
#sgq{font:inherit;font-size:14.5px;padding:7px 10px;border:1px solid var(--line2);border-radius:9px;background:var(--bg);color:var(--ink);max-width:420px}
.sgchips{display:flex;flex-wrap:wrap;gap:4px}
.sgch{font:inherit;font-size:12.5px;padding:2px 9px;border-radius:999px;border:1px solid var(--line2);background:var(--bg);color:var(--ink2);cursor:pointer}
.sgch.on{background:var(--accbg);border-color:var(--acc);color:var(--ink);font-weight:600}
.sgch i{font-style:normal;color:var(--mut);margin-left:3px;font-size:11.5px}
.sgopt{display:flex;gap:14px;align-items:center;font-size:13px;flex-wrap:wrap}
.sgc2{padding-left:10px;border-left:2px solid var(--acc)}
.sgadv>summary{cursor:pointer;font-size:13px;color:var(--acc);width:max-content}.sgadv>summary span{color:var(--ink2)}
.sgadvb{display:flex;flex-direction:column;gap:6px;margin-top:6px}
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
.sgchart .mk.sk{fill:none;stroke:var(--mut);stroke-width:1.2;stroke-dasharray:2 1.5}
.sgrt tr.sk td{color:var(--mut);font-size:12px;white-space:normal}
.sgchart .hv{stroke:var(--ink2);stroke-width:1;stroke-dasharray:2 2}.sgchart .hit{fill:transparent;cursor:crosshair}
.sghint{display:block;color:var(--ink);font-weight:600;margin-bottom:2px}
.sgmore2{font:inherit;font-size:12px;margin-left:6px;padding:1px 8px;border:1px solid var(--acc);border-radius:7px;background:var(--accbg);color:var(--ink);cursor:pointer}
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
/* 進場之後的報酬（VER 5） */
.sgrr{width:100%;border-collapse:collapse;font-size:12.5px}
.sgrr th{font-weight:600;color:var(--ink2);text-align:right;padding:4px 5px;border-bottom:1px solid var(--line2);font-size:12px;line-height:1.3;vertical-align:bottom;white-space:nowrap}
.sgrr td{padding:4px 5px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:middle}
.sgrr th.l,.sgrr td.l{text-align:left}.sgrr td small{display:block;font-size:11px;color:var(--mut);font-weight:400}
.sgrr tr.own td{background:var(--accbg)}.sgrr tr.own td.l small{color:var(--acc)}.sgrr tr[data-few] td{color:var(--ink2)}
.sgrr td.up b{color:var(--t4)}.sgrr td.dn b{color:var(--t0)}.sgrr tr.na td{color:var(--mut)}
.sgrcv{min-height:60px;margin-top:6px}
.sgrch .z0{stroke:var(--line2)}.sgrch .rb1{fill:var(--acc);fill-opacity:.18}.sgrch .rm1{fill:none;stroke:var(--acc);stroke-width:2}
.sgrch .rb0{fill:var(--ink2);fill-opacity:.09}.sgrch .rm0{fill:none;stroke:var(--ink2);stroke-width:1.3;stroke-dasharray:4 3}
.sgrch .rp{fill:var(--acc)}
.sghow{margin-top:12px}.sghow summary{cursor:pointer;color:var(--acc);font-size:13px}
.sgdl2{margin:6px 0;font-size:13.5px;line-height:1.7}.sgdl2 dt{font-weight:600;margin-top:6px}.sgdl2 dd{margin:0 0 2px 0;color:var(--ink2)}
.sgfw{border-collapse:collapse;font-size:12.5px;margin:2px 0 8px}.sgfw th,.sgfw td{padding:3px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}.sgfw th{font-weight:600;color:var(--ink2);font-size:12px}.sgfw .l{text-align:left}
.sgfwh{margin:8px 0 2px;font-weight:600;color:var(--ink)}.sgfwr{overflow-x:auto;max-width:100%}
.sgfe{margin:4px 0 6px;font-size:13.5px;line-height:1.7}.sgfe p{margin:2px 0}.sgfe .mu{color:var(--mut)}
/* 總經策略（xstratspec；2026-10-22 前叫大神策略） */
.xsv{font-size:14px;line-height:1.6;margin:10px 0 0;padding:8px 10px;border-radius:10px;background:var(--card2)}
.xsr{margin:4px 0 6px;padding-left:20px;font-size:13px;line-height:1.7}
.xsw{list-style:none;margin:4px 0;padding:0;font-size:13px;line-height:1.65}.xsw li{display:flex;gap:6px}.xsw li+li{margin-top:3px}
.xsw li span{flex:none;width:14px;text-align:center;font-weight:700}.xsw li.y span{color:var(--acc)}.xsw li.n span{color:var(--t3)}.xsw li.m{color:var(--ink2)}
.xsg{border-collapse:collapse;font-size:12.5px;margin:2px 0}.xsg caption{caption-side:top;text-align:left;font-size:12px;color:var(--ink2);padding:0 0 4px}
.xsg th{font-weight:600;color:var(--ink2);padding:4px 6px;border-bottom:1px solid var(--line2);text-align:center;white-space:nowrap;font-size:12px}
.xsg th.l{text-align:left}.xsg td{padding:4px 6px;border:1px solid var(--line);text-align:center;white-space:nowrap}
.xsg td i{font-style:normal;font-weight:700;margin-right:3px}.xsg td.y i{color:var(--acc)}.xsg td.n{color:var(--ink2)}.xsg td.n i{color:var(--t3)}
.xsg td small{display:block;font-size:10.5px;color:var(--mut)}.xsg td.mn{outline:2px solid var(--ink);outline-offset:-2px}
.xsseg{display:inline-flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.xsseg button{font:inherit;font-size:12.5px;padding:3px 10px;border:0;background:var(--bg);color:var(--ink2);cursor:pointer}
.xsseg button+button{border-left:1px solid var(--line2)}.xsseg button.on{background:var(--accbg);color:var(--ink);font-weight:600}
.xseq .xss{fill:none;stroke:var(--acc);stroke-width:2}.xseq .xsb{fill:none;stroke:var(--ink2);stroke-width:1.3;stroke-dasharray:4 3}
.xst td.up b{color:var(--t4)}.xst td.dn,.xst td.dn b{color:var(--t0)}.xstr td small{display:block;font-size:11px;color:var(--mut)}
.xstr td.up b{color:var(--t4)}.xstr td.dn b{color:var(--t0)}
.sgd-none{color:var(--ink2)}
body.sgopen{overflow:hidden}
.sgtb tr.sgr.open td{background:var(--accbg)}
@media (min-width:1100px){.sgpb{background:transparent;pointer-events:none}body.sgopen{overflow:auto}}
@media (max-width:900px){.sgt{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){.xsg td,.xsg th{padding:3px 4px}.xsg td small{font-size:10px}.sgt{grid-template-columns:minmax(0,1fr)}.sgtb .dsk{display:none}.sgln{padding-left:0}
 .sgtb td.l{min-width:150px}.sgwrap{overflow-x:visible}.sgtb td.l .sgm{display:block}
 .sgsw{overflow-x:auto}
 .sgmob{display:block;margin-top:4px}.sgmn{display:flex;flex-wrap:wrap;align-items:center;gap:2px 10px}.sgmn .sgnv,.sgmn .sgnz{display:inline;white-space:nowrap}
 .sgms{font-size:12.5px;color:var(--ink2);line-height:1.55;margin-top:3px}.sgms b{color:var(--ink)}.sgms .sgs{display:block;font-size:11.5px}
 .sgp{width:100%;padding:0 12px 28px}
 .sgst2,.sgst2 tbody{display:block}.sgst2 thead{display:none}.sgsw{overflow-x:visible}
 .sgst2 tbody{border-bottom:1px solid var(--line2);padding:4px 0}
 .sgst2 tr{display:grid;grid-template-columns:minmax(0,1.6fr) repeat(6,minmax(0,1fr));align-items:center;column-gap:2px}
 .sgst2 td{border-bottom:0;padding:3px 2px;text-align:center;white-space:normal}
 .sgst2 td.nm{grid-column:1/-1;text-align:left;padding:4px 2px 0}.sgst2 td.nm small{display:inline;margin-left:6px}
 .sgst2 td.wt{text-align:left}.sgst2 td[data-h]::before{content:attr(data-h);display:block;font-size:10px;color:var(--mut);line-height:1.2}
 .sgst2 td.r10 small{font-size:10px}.sgst2 .sgd{white-space:normal;max-width:100%}.sgst2 .sgd small{font-size:10px}
 .sgchips{flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px}.sgch{flex:0 0 auto}
 .sgpc .sgwrap{overflow-x:auto}.sgpc .sgwrap.sgrw{overflow-x:visible}.sgrr,.sgrr tbody{display:block}.sgrr thead{display:none}
 .sgrr tr.own{background:var(--accbg)}.sgrr tr.own td{background:transparent}
 .sgrr tr{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));column-gap:4px;border-bottom:1px solid var(--line2);padding:3px 0}
 .sgrr td{border-bottom:0;padding:2px 2px;text-align:center;white-space:normal}
 .sgrr td.l{grid-column:1/-1;text-align:left;font-weight:600}.sgrr td.l small{display:inline;margin-left:6px}
 .sgrr td[data-h]::before{content:attr(data-h);display:block;font-size:10px;color:var(--mut);line-height:1.2}
 .sgrr tr.na td.mu{grid-column:1/-1;text-align:left}}
"""

JS = r"""
(function(){
const SG = JSON.parse(document.getElementById('sgd').textContent);
const ROWS = SG.rows, ON = SG.on, IT = SG.it || {};
const I = {id:0,mk:1,cat:2,grp:3,name:4,kind:5,H:6,th:7,tier:8,dir:9,up:10,warn:11,buy:12,a:13,z:14,x:15};
const TORD = {good:0, rare:1, ref:2, none:3, few:4};
const MKO = ['tw','spx','ixic','ndx','sox','us','stk'];
const HT = {20:'1 個月',60:'3 個月',250:'12 個月'};
const st = {q:'', mk:'', c1:'', c2:'', tier:'', dir:'', now:false, sort:'def', asc:false, limit:80};
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
function hz(r){ const c = r[I.cat]; if (c === 'buy') return '3 個月'; if (c === 'ind') return '12 個月';
  if (c === 'strat') return '照規則'; if (c === 'stock') return '20 個交易日'; return HT[r[I.H]] || (r[I.H] + ' 個交易日'); }
function nowTxt(r){ const n = ON[r[I.id]]; if (!n) return '';
  if (n.xs != null) return n.xs;
  if (n.live != null) return '今天 ' + n.live + ' 檔';
  const tr = n.buy && n.sell ? '・' + mdy(n.buy) + ' 收盤進場、持有到 ' + mdy(n.sell) : '';
  if (n.left != null) return mdy(n.since) + ' 出現' + (tr ? tr + (n.rem != null ? '（還有 ' + n.rem + ' 個交易日）' : '') : '・還看 ' + n.left + ' 天');
  if (n.event) return mdy(n.since) + ' 出現' + tr;
  return mdy(n.since) + ' 起成立' + tr; }
function nowShort(r){ const n = ON[r[I.id]]; if (!n) return '';   // 「現在」欄只寫哪天出現（進場、持有到哪天寫在訊號那一欄）
  if (n.xs != null) return n.xs;
  if (n.live != null) return '今天 ' + n.live + ' 檔';
  return mdy(n.since) + (n.left != null || n.event ? ' 出現' : ' 起成立'); }
function label(r){ const nm = r[I.name];
  if (['heat','deriv','crash','buy','ind','inst'].includes(r[I.cat])) { const i = nm.lastIndexOf('・'); return i >= 0 ? nm.slice(i + 1) : nm; }
  return nm; }
function what(r, d){ const c = r[I.cat];
  if (c === 'strat') return '每筆賺錢';
  if (d === 'buy') return '買進之後上漲';
  if (d === 'up') return c === 'stock' ? '持有 20 天賺錢' : '之後上漲';
  return '之後大跌'; }
function phr(r, d){ if (r[I.cat] === 'xs') { const x = SIG2[r[I.id]]; return x ? esc(x.xs.line) : ''; }
  const s = stat(r, d); if (!s) return ''; const c = r[I.cat], h = hz(r);
  let w;
  if (c === 'strat') w = '每筆賺錢的比例';
  else if (d === 'buy') w = '買進之後 ' + h + '上漲的機率';
  else if (d === 'up') w = c === 'stock' ? '持有 20 天賺錢的機率' : '之後 ' + h + '上漲的機率';
  else w = '之後 ' + h + '內大跌（最大回撤 ' + r[I.th] + '% 以上）的機率';
  const m = d !== 'warn' && c !== 'strat' ? (r[I.x] || {}).med : null;       // VER 17：報酬中位數
  const f = feOf(r, d);                                                         // VER 18～19：預估之後
  return w + (f ? ' 過去 ' + pc(s[1]) + ' → 預估之後 <b>' + pc(f[0]) + '</b>' : ' <b>' + pc(s[1]) + '</b>') + (s[2] != null ? '（隨便挑一天 ' + pc(s[2]) + '）' : '') +
    (m != null ? '・報酬中位數 ' + (m > 0 ? '+' : m < 0 ? '−' : '') + Math.abs(m).toFixed(1) + '%' + (f && f[3] != null ? '，預估之後比隨便挑一天' + moreTxt(f[3]) : '') : ''); }
function feOf(r, d){ const f = ((r[I.x] || {}).fe || {})[d]; return f || null; }
function moreTxt(v){ const x = Math.round(v * 10) / 10; return x > 0 ? '多 ' + x.toFixed(1) + '%' : x < 0 ? '少 ' + Math.abs(x).toFixed(1) + '%' : '差不多'; }
function cellTxt(key){                                 // 衰退表的格子（sigoos.key）→ 白話：偏多・看 1 個月・出現過 15～39 次・過去比平常高 10～20 點
  if (!key) return ''; const [d, H, b, g] = key.split('|'), F = SG.fwd;
  const parts = [d === 'buy' ? '大跌後買點' : (SG.dirs[d] || d), '看 ' + (HT[+H] || H + ' 個交易日')];
  if (b !== '*') parts.push('出現過 ' + F.nb[+b]);
  parts.push(g === 'p' || g === 'n' ? '過去' + F.sg[g] : +g === 0 ? '過去比平常低' : '過去比平常' + F.eb[+g]);
  return parts.join('・'); }
function feHtml(r){
  const c = r[I.cat];
  if (['ind', 'stock', 'strat', 'xs'].includes(c)) return '<p class="note">產業泡沫、個股訊號、策略沒有預估之後（逐年樣本外只做市場層級的訊號與大跌後買點）。</p>';
  if (!SG.fwd || !SG.fwd.ok) return '<p class="note">預估之後的研究檔還沒產生。</p>';
  const x = r[I.x] || {}, O = x.ow || {}, out = [];
  dirsOf(r).forEach(d => { const s = stat(r, d), f = feOf(r, d); if (!s) return;
    const tag = '<span class="sgd sgd-' + d + '">' + esc(SG.dirs[d] || d) + '</span> ';
    if (!f) { out.push('<p>' + tag + '出現不到 ' + SG.nmin + ' 次，不估。</p>'); return; }
    const w = d === 'warn' ? '之後 ' + hz(r) + '內大跌的機率' : d === 'buy' ? '買進之後 ' + hz(r) + '上漲的機率' : '之後 ' + hz(r) + '上漲的機率';
    let h = '<p>' + tag + w + '：過去 ' + pc(s[1]) + ' → 預估之後 <b>' + pc(f[0]) + '</b>（隨便挑一天 ' + pc(s[2]) + '）';
    if (f[3] != null) h += '；報酬中位數預估之後比隨便挑一天<b>' + moreTxt(f[3]) + '</b>';
    const K = SG.fwd.keys || [];
    h += '。<br><span class="mu">依據：' + (f[2] == null ? '同一類的格子筆數都不夠，當作之後沒有優勢' :
      '同一類的訊號（' + esc(cellTxt(K[f[2]])) + '）每年 1 月 1 日只用之前的資料看、之後那一年，優勢平均留下 ' + f[1] + '%') +
      (f[3] != null && f[4] != null ? '，報酬多賺留下 ' + f[4] + '%' + (f[5] != null && f[5] !== f[2] ? '（' + esc(cellTxt(K[f[5]])) + '）' : '') : '') + '。</span>';
    const o = O[d];
    if (o) h += '<br><span class="mu">這個訊號自己：' + o[0] + ' 年有出現，那些年之後平均比隨便挑一天' + (o[2] >= 0 ? '多 ' : '少 ') +
      Math.abs(o[2]).toFixed(1) + ' 個百分點（當時看過去是' + (o[1] >= 0 ? '多 ' : '少 ') + Math.abs(o[1]).toFixed(1) + '）' +
      (o[0] < SG.fwd.omin ? '，年數少，只當參考' : '') + '。</span>';
    out.push(h + '</p>'); });
  return out.join('') || '<p class="note">沒有預估之後。</p>'; }
function mark(t, r){ const x = ((r && (r[I.cat] === 'strat' || r[I.cat] === 'xs')) ? SG.stiers : SG.tiers)[t] || ['', ''];
  return '<span class="sgtk sgtk-' + t + '" title="' + esc(x[1]) + '">' + x[0] + '</span>'; }
function sent(r){ const [d, s] = sd(r); return mark(s ? s[6] : r[I.tier], r) + ' <b>' + esc(label(r)) + '</b>：' + phr(r, d); }
function zi(h){ return h == null ? 'x' : h >= 80 ? '4' : h >= 60 ? '3' : h >= 40 ? '2' : h >= 20 ? '1' : '0'; }

// ── 依指標整理（docs/lab_sigview_plan.md）
const INDS = SG.inds.map(x => { const sig = x[5].map(i => ROWS[i]);
  const rk = r => TORD[r[I.tier]] * 1000 - (edge(r) ?? -99);
  const srt = a => a.slice().sort((p, q) => rk(p) - rk(q) || (p[I.id] < q[I.id] ? -1 : 1));
  const on = srt(sig.filter(r => ON[r[I.id]])), best = srt(sig)[0], ds = new Set();
  sig.forEach(r => dirsOf(r).forEach(d => { const s = stat(r, d); if (s && (s[6] === 'good' || s[6] === 'rare' || s[6] === 'ref')) ds.add(d); }));
  const it = x[6] && IT[x[1]] ? IT[x[1]][x[6]] || null : null;
  return {k: x[0], mk: x[1], cat: x[2], name: x[3], grp: x[4], sig, on, best, ds, it, ik: x[6], c1: x[7], c2: x[8] || '',
    hay: (x[3] + ' ' + x[0] + ' ' + (SG.mk[x[1]] || '') + ' ' + SG.icat[x[2]] + ' ' + (SG.fac[x[7]] || '') + ' ' +
      (x[8] && SG.sub[x[7]] ? SG.sub[x[7]][x[8]] : '') + ' ' + sig.map(r => r[I.name]).join(' ')).toLowerCase()}; });
const BYK = {}, SIG2 = {};
INDS.forEach(x => { BYK[x.k] = x; x.sig.forEach(r => { SIG2[r[I.id]] = x; }); });
// 總經策略（xstratspec；文字由 arm/lab/xstratpage.py 產生）：每個市場每個策略一列，判定照交易成績
const XS = SG.xs || {spec: {}, m: {}, grp: {}, sn: {}};
const XSV = {span: 'all', all: false};
Object.entries(XS.m || {}).forEach(([mk, M]) => Object.entries(M).forEach(([k, r]) => {
  const sp = XS.spec[k], id = 'xs:' + mk + ':' + k, d = sp.kind === 'alloc' ? 'warn' : 'up';
  const row = [id, mk, 'xs', sp.grp, sp.name, sp.kind, null, null, r.t, [d], null, null, null, r.a, r.z, {xs: 1}];
  if (r.side) ON[id] = {xs: XS.sn[r.st] || ''};
  const x = {k: id, mk, cat: 'xs', name: sp.name, grp: sp.grp, sig: [row], on: r.side ? [row] : [], best: row,
    ds: new Set(r.t === 'good' || r.t === 'ref' ? [d] : []), it: null, ik: null, xs: r, sp, xk: k, c1: 'strat', c2: sp.grp,
    hay: (sp.name + ' ' + id + ' ' + (SG.mk[mk] || '') + ' 策略 總經策略 大神策略 ' + (XS.grp[sp.grp] || '') + ' ' + sp.who + ' ' + sp.src).toLowerCase()};
  INDS.push(x); BYK[id] = x; SIG2[id] = x; }));
function grpName(x){ return x.grp && SG.dimn[x.mk] ? SG.dimn[x.mk][x.grp] || '' : ''; }
function facName(x){ return (SG.fac[x.c1] || '') + (x.c2 && SG.sub[x.c1] ? '・' + SG.sub[x.c1][x.c2] : ''); }
function meta(x){ const f = SG.fac[x.c1] || '', g = x.cat === 'heat' ? grpName(x) : '';      // 市場・第一層・第二層（景氣項目寫面向）
  if (x.c1 === 'strat') return x.c2 === 'stk' ? [SG.mk[x.mk], '個股策略'].join('・')               // 策略：市場・總經策略・短線
    : [SG.mk[x.mk], '總經策略', (SG.sub.strat[x.c2] || '').replace('總經・', '')].filter(Boolean).join('・');
  let t = x.c2 && SG.sub[x.c1] ? SG.sub[x.c1][x.c2] : (g && g !== f ? g : '');
  if (x.grp === 'sent' && g) t = g;                                                              // 美股的籌碼面向叫情緒籌碼
  return [SG.mk[x.mk], f, t].filter(Boolean).join('・'); }
function pass(x, skip){
  if (st.q && !st.q.split(/\s+/).every(w => x.hay.includes(w))) return false;
  if (skip !== 'mk' && st.mk && x.mk !== st.mk) return false;
  if (skip !== 'c1' && st.c1 && x.c1 !== st.c1) return false;
  if (skip !== 'c1' && skip !== 'c2' && st.c2 && x.c2 !== st.c2) return false;
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
const TCH = {good: '★ 有好訊號', rare: '◆ 難得機會（次數少）', ref: '● 可能是運氣（個股訊號）', none: '○ 沒過門檻', few: '— 次數不夠'};
function chips(){
  const sub = SG.sub[st.c1] || null;                                            // 第二層：選了有第二層的第一層才出現
  const defs = {mk: MKO.map(k => [k, SG.mk[k]]), c1: Object.entries(SG.fac), c2: sub ? Object.entries(sub) : [], tier: Object.entries(TCH),
    dir: [['up','有偏多訊號'],['warn','有警示訊號'],['buy','有買點訊號']]};
  document.querySelectorAll('.sgchips[data-k]').forEach(box => {
    const k = box.dataset.k, cnt = {};
    if (k === 'c2') { box.hidden = !sub; if (!sub) { box.innerHTML = ''; return; } }
    INDS.forEach(x => { if (!pass(x, k)) return;
      const vs = k === 'dir' ? [...x.ds] : k === 'tier' ? [x.best[I.tier]] : [x[k]]; vs.forEach(v => { cnt[v] = (cnt[v] || 0) + 1; }); });
    box.innerHTML = '<button type="button" class="sgch' + (st[k] ? '' : ' on') + '" data-v="">全部' + (k === 'c2' ? esc(SG.fac[st.c1]) : '') + '</button>' +
      defs[k].filter(([v]) => cnt[v] || st[k] === v).map(([v, nm]) => '<button type="button" class="sgch' + (st[k] === v ? ' on' : '') +
        '" data-v="' + v + '">' + esc(nm) + '<i>' + (cnt[v] || 0) + '</i></button>').join('');
    box.onclick = e => { const b = e.target.closest('.sgch'); if (!b) return; st[k] = b.dataset.v; if (k === 'c1') st.c2 = ''; st.limit = 80; draw(); }; });
  const n = (st.tier ? 1 : 0) + (st.dir ? 1 : 0) + (st.now ? 1 : 0), an = document.getElementById('sgadvn');
  if (an) an.textContent = n ? '（已選 ' + n + ' 項）' : ''; }
function spark(sp, w, h){
  if (!sp || !sp.some(v => v != null)) return '';
  const n = sp.length, X = i => (n > 1 ? i / (n - 1) : 0) * (w - 4) + 2, Y = v => h - 2 - (v / 100) * (h - 4);
  let d = '', pen = false, last = -1;
  sp.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; last = i; });
  return '<svg class="sgsp" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" aria-hidden="true">' +
    '<line class="th" x1="0" x2="' + w + '" y1="' + Y(80).toFixed(1) + '" y2="' + Y(80).toFixed(1) + '"/>' +
    '<line class="tc" x1="0" x2="' + w + '" y1="' + Y(20).toFixed(1) + '" y2="' + Y(20).toFixed(1) + '"/>' +
    '<path d="' + d + '"/><circle class="zt' + zi(sp[last]) + '" cx="' + X(last).toFixed(1) + '" cy="' + Y(sp[last]).toFixed(1) + '" r="2.6"/></svg>'; }
function scenNow(x){ const q = SG.scen[x.k.split(':').pop()], v = SG.scnv[x.mk];
  if (!q || !v) return '';
  return q[3].map(g => esc(SG.scdn[g]) + ' ' + (v[g] == null ? '—' : '<span class="zt' + zi(v[g]) + '">' + Math.round(v[g]) + '</span>')).join('・'); }
function nowCell(x){ const it = x.it;
  if (x.cat === 'xs') return '<span class="sgnv">' + esc(x.xs.nv) + '</span><span class="sgnz">' + esc(XS.sn[x.xs.st] || '') + '</span>';
  if (x.cat === 'scen') { const t = scenNow(x); return t ? '<span class="sgnv">' + t + '</span>' : '<span class="mu">—</span>'; }
  if (it && (it.v || it.h != null)) return (it.v ? '<span class="sgnv">' + esc(it.v) + '</span>' : '') +
    (it.h != null ? '<span class="sgnz zt' + zi(it.h) + '">' + Math.round(it.h) + ' ' + esc(it.band || '') + '</span>' : '');
  const o = x.on[0]; return o ? '<span class="sgnv">' + esc(nowShort(o)) + '</span>' : '<span class="mu">—</span>'; }
function sigCell(x){
  if (x.cat === 'xs') return mark(x.xs.t, x.best) + ' ' + esc(x.xs.line) + '<span class="sgs">' + esc(x.xs.now) + '</span>';
  if (x.on.length) { const o = x.on[0];
    return sent(o) + '<span class="sgs">' + esc(nowTxt(o)) + (x.on.length > 1 ? '・另 ' + (x.on.length - 1) + ' 個也成立' : '') + '</span>'; }
  const b = x.best, t = b[I.tier];
  return '<span class="mu">現在沒有成立的訊號' + ((t === 'good' || t === 'rare' || t === 'ref') ? '；最好的是「' + esc(label(b)) + '」' + SG.tiers[t][0] : '') + '</span>'; }
function rowHtml(x){ const t = x.cat === 'xs' ? x.xs.t : x.on.length ? x.on[0][I.tier] : null, sp = x.it && x.it.sp;
  return '<tr class="sgr" data-k="' + esc(x.k) + '"><td class="tk">' + (t ? mark(t, x.on[0]) : '<span class="sgtk mu">·</span>') + '</td>' +
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
  tnow: '這個指標現在成立的訊號裡，判定最好的那一個：★ 好訊號、◆ 難得機會（次數少）、○ 沒過門檻、— 次數不夠（個股訊號另有 ● 可能是運氣）；· 現在沒有成立的訊號。',
  tier: '★ 好訊號（2026-10-22 起看絕對成績）：至少 ' + SG.sn + ' 次、機率 ≥ ' + SG.hit.up + '%（警示 ≥ ' + SG.hit.warn + '%）、不比隨便挑一天差、近 10 年也成立；偏多另外要報酬中位數與排除極端的平均扣掉買賣成本後都賺錢。◆ 難得機會：門檻都過了，但只出現 ' + SG.nmin + '～' + (SG.sn - 1) + ' 次。○ 沒過門檻。— 不到 ' + SG.nmin + ' 次。個股訊號照舊：比隨便挑一天多 ' + SG.eg + ' 個百分點以上，而且亂排 ' + SG.ld + ' 次做得到一樣準的不到 ' + SG.lp + '%（次數少於 ' + SG.lfn + ' 次的不到 ' + SG.lpf + '%），● 可能是運氣＝門檻過了、亂排也常做得到。小字是亂排也做得到的比例（個股訊號以外只當參考）。',
  now: '現在的數值，和它的 0～100（100 最熱、0 最冷；和這個指標自己過去比）。',
  spark: '近一年每週的 0～100；上下兩條虛線是 80（過熱）和 20（過冷）。',
  p: '偏多：訊號出現的隔天收盤買，過了看多久之後收盤比買價高的比例。警示：看多久之內出現一段最大回撤到門檻的比例（期間最高收盤到之後最低收盤，先漲再跌也算）。括號是同一段期間隨便挑一天的比例。',
  what: '偏多看「之後上漲」，警示看「之後大跌」（最大回撤到門檻），買點看「照規則買進之後 3 個月有沒有漲」。每一種訊號兩個方向各算一次。',
  prob: '這個訊號過去出現之後，「看什麼」那一欄成立的比例。',
  base: '同一段期間裡隨便挑一天、用同樣算法的比例。好訊號至少不能比它差；比它高越多，越代表這個時機比平常好，差不多就等於大盤本身的表現。',
  edge: '機率減掉隨便挑一天，單位是百分點。',
  r10: '只看最近 10 年：✓ 機率過了門檻、也不比近 10 年隨便挑一天差；△ 兩條只過一條；✗ 都沒過；— 近 10 年不到 ' + SG.n10 + ' 次，不看。',
  rtrim: '去掉最好和最差各 5%（次數少於 20 次時各去掉一次）之後的平均：排除極端狀況的一般表現。',
  rlbo: '去掉最好的那一次之後的平均：看成績是不是靠一兩次撐起來。',
  n: '事件型（例：跌破季線）出現那天算一次，看多久的期間內再出現不算新的一次；狀態型（例：過熱中）連續的一段算一次。',
  dd: '期間最高收盤到之後最低收盤的跌幅（先漲再跌也算）。狀態型是這一段每一天的平均。',
  rup: '持有到這一天收盤，比進場價高的比例。',
  rmed: '持有到這一天收盤的報酬，由小到大排在正中間的那一個（一半比它好、一半比它差）。',
  fwd: '上面的機率是過去的成績，之後通常會往下修。每年 1 月 1 日只用之前的資料看，同一類訊號（方向、看多久、出現過幾次、過去比平常高幾點）之後那一年平均留下多少優勢；預估之後＝隨便挑一天 ＋ 留下來的比例 ×（過去 − 隨便挑一天）。報酬多賺同樣算。只當參考。',
  rhalf: '報酬由小到大排，中間一半落在這個範圍（25%～75%）。',
  rmae: '進場之後到這一天之間，最低收盤比進場價低多少（比進場價低才算，沒跌過＝0）。中位數＝一半的時候跌得比這少。',
  rmae10: '中途最多跌由差到好排，最差的一成跌超過這個數字。'};
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
const ITRIG = {hot:'0～100 在 80 以上的每一天（大賣超：賣超占成交金額的比例，和自己過去 3 年比，賣超越多越高；同一段算 1 次）',
  hot_in:'0～100 從低於 80 升到 80 以上那一天（前 20 個交易日都低於 80）', hot_out:'連續 4 週以上的週末都在 80 以上之後，第一個低於 80 的週末',
  cold:'0～100 低於 20 的每一天（大買超；同一段算 1 次）', cold_in:'0～100 從 20 以上降到低於 20 那一天（前 20 個交易日都在 20 以上）',
  cold_out:'連續 4 週以上的週末都低於 20 之後，第一個 20 以上的週末',
  day_sell:'當天賣超占成交金額的比例，在過去 3 年裡賣超最多的 5%（0～100 在 95 以上）',
  day_buy:'當天買超占成交金額的比例，在過去 3 年裡買超最多的 5%（0～100 在 5 以下）'};
function itrig(x){ const m = /^(sell|buy)_run(\d+)$/.exec(x.sig || '');
  if (m) return '連續 ' + m[2] + ' 個交易日' + (m[1] === 'sell' ? '賣超' : '買超') + '的第 ' + m[2] + ' 天（當天沒有資料或剛好 0 算中斷；同一段連續只算 1 次）';
  return ITRIG[x.sig] || ''; }
function trig(r){ const c = r[I.cat], x = r[I.x] || {}, nm = r[I.name];
  if (c === 'heat' || c === 'crash') return x.vn + '：' + TRIG[x.sig];
  if (c === 'inst') return x.vn + '：' + itrig(x);
  if (c === 'scen') { const q = SG.scen[x.var] || []; return '在「' + (q[0] || nm) + '」情境裡的每一天：' + (q[1] || '') + (r[I.mk] === 'tw' ? '（資金＝全球資金與台灣資金的平均）' : '') + '；同一段算 1 次'; }
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
  if (c === 'buy') return '照規則的買進日收盤買，3 個月（60 個交易日）後收盤比買價高；隨便挑一天＝同一段期間每一天買、抱 3 個月上漲的比例（2026-10-21 起；之前看「買在這一波的相對低點」，照列在下面）';
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
    items = oc.slice(-40).reverse().map(o => '<li class="' + (o[j] >= 0.5 ? 'y' : '') + '">' + (c === 'ind' ? '<b>' + esc((SG.inm || {})[o[5]] || o[5]) + '</b> ' : '') +
      ymd(o[0]) + (o[1] !== o[0] ? '～' + ymd(o[1]) : '') + ' <span class="x">' + o[2] + (r[I.x] && r[I.x].monthly ? ' 個月' : ' 天') + '</span> ' + Math.round(o[j] * 100) + '%' +
      (d === 'warn' && o[k] != null ? ' <span class="x">回撤 ' + Math.round(o[k] * 100) + '%</span>' : '') + '</li>'); }
  else { const j = c === 'buy' ? 1 : (d === 'warn' ? 2 : 1);
    title = '每一次（最近 60 次；共 ' + oc.length + ' 次）：' + (c === 'buy' ? '買進日，✓＝3 個月後上漲' : '✓＝中了');
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
const PXC = ['tech', 'crash', 'dim', 'scen', 'inst', 'bub', 'buy'];                     // 沒有自己的 0～100 走勢的，畫指數＋打點
function chartable(x){ return !!SG.chart[x.mk] && (!!x.ik || PXC.includes(x.cat)); }
function sck(x){ const J = CJ[x.mk], ck = ckOf(x); return ck && J && J.s && J.s[ck] ? ck : null; }
function cell(k, v, sub){ return '<div class="sgnc"><span class="k">' + k + '</span><span class="v">' + v + '</span>' + (sub ? '<span class="s">' + sub + '</span>' : '') + '</div>'; }
function nowHtml(x){ const it = x.it; let h = '<div class="sgnow">';
  if (it) {
    if (it.v) h += cell('現值', esc(it.v), it.d ? '資料 ' + esc(ymd(it.d)) : '');
    if (it.h != null || it.v) h += cell('0～100', it.h == null ? '—' : '<span class="zt' + zi(it.h) + '">' + Math.round(it.h) + ' ' + esc(it.band || '') + '</span>',
      it.hot === 1 ? '數值越高越熱' : it.hot === -1 ? '數值越低越熱' : '和自己過去比');
  }
  if (x.cat === 'scen') { const q = SG.scen[x.k.split(':').pop()];
    if (q) h += cell('條件', esc(q[1]), esc('想看的事：' + q[2])) + cell('現在的面向', scenNow(x) || '—', x.mk === 'tw' && q[3].includes('liq') ? '資金＝全球與台灣資金平均' : ''); }
  h += cell('現在成立的訊號', x.on.length ? x.on.length + ' 個' : '沒有', x.on.length ? '' : '過去的訊號見下表');
  h += '</div>';
  if (it && it.pos) h += '<p class="sgdl">' + esc(it.pos) + '</p>';
  if (it && it.dv) h += '<p class="sgdl">邊際變化：<b>' + esc(it.dv) + '</b></p>';
  if (it && it.why) h += '<p class="warn">' + esc(it.why) + '</p>';
  if (x.on.length) h += '<ul class="sgonl">' + x.on.map(r => '<li>' + sent(r) + '<span class="sgs">' + esc(nowTxt(r)) + '</span></li>').join('') + '</ul>';
  return h; }
function r10(s, d, stk){ if (!s || !s[3] || s[3] < SG.n10) return '<span class="mu">—</span>' + (s && s[3] ? '<small>' + s[3] + ' 次</small>' : '');
  let ok;
  if (stk) { const e = s[4] - s[5]; ok = e >= SG.eg ? '✓' : e >= SG.er ? '△' : '✗'; }          // 個股訊號照 VER 14
  else { const a = s[4] >= SG.hit[d], b = s[4] >= s[5]; ok = a && b ? '✓' : a || b ? '△' : '✗'; }    // sigspec VER 17
  return ok + '<small>' + s[3] + ' 次・' + pc(s[4]) + '</small>'; }
function medCell(r, d, s){                                   // VER 17：報酬中位數（偏多、買點）／回撤中位數（警示）
  const x = r[I.x] || {};
  if (d === 'warn') return s && s[7] != null ? '<span class="mu">回撤</span> ' + dn1(s[7]) : '—';
  if (x.med == null) return '—';
  const f = feOf(r, d);
  return '<b class="' + (x.med > 0 ? 'up' : x.med < 0 ? 'dn' : '') + '">' + sr1(x.med) + '</b>' + (x.trm != null ? '<small>排除極端 ' + sr1(x.trm) + '</small>' : '') +
    (f && f[3] != null ? '<small>預估之後' + moreTxt(f[3]) + '</small>' : ''); }
function luckTxt(s, r){ if (!s || s[9] == null || (s[6] !== 'good' && s[6] !== 'rare' && s[6] !== 'ref')) return '';
  const stk = r && r[I.cat] === 'stock', pair = stk && r[I.dir][0] === 'up';
  const t = pair ? '在每一次事件裡隨機對調「訊號」和「對照」的結果，做得到一樣好的比例' : '把出現的日子隨便亂排，做得到一樣準的比例';
  const few = s[0] < SG.lfn, th = few ? SG.lpf : SG.lp;            // sigspec VER 14：個股訊號次數少於 15 次的門檻 10%
  const note = stk ? '（' + th + '% 以下才算好訊號' + (few ? '；次數少於 ' + SG.lfn + ' 次的門檻' : '') + '）' : '（只當參考；2026-10-22 起不參與判定）';
  return '<small title="' + t + note + '">亂排 ' + (s[9] < 1 ? s[9].toFixed(1) : Math.round(s[9])) + '%</small>'; }
function sigTable(x){
  const head = '<thead><tr><th class="l">訊號</th><th class="l">看什麼 ' + ii('what') + '</th><th>機率 ' + ii('prob') + '</th><th>隨便挑一天 ' + ii('base') + '</th>' +
    '<th>多幾個百分點 ' + ii('edge') + '</th><th>報酬中位數 ' + ii('rmed') + '</th><th>近 10 年也成立嗎 ' + ii('r10') + '</th><th>出現過幾次 ' + ii('n') + '</th><th>判定 ' + ii('tier') + '</th></tr></thead>';
  const body = x.sig.map(r => { const ds = dirsOf(r), on = ON[r[I.id]];
    return '<tbody class="sgsb' + (on ? ' on' : '') + (SEL === r ? ' sel' : '') + '" data-id="' + esc(r[I.id]) + '">' + ds.map((d, i) => { const s = stat(r, d), e = dEdge(s);
      const w = what(r, d) + (d === 'warn' ? '<small>最大回撤 ' + r[I.th] + '% 以上</small>' : '');
      return '<tr>' + (i ? '' : '<td class="l nm" rowspan="' + ds.length + '"><b>' + esc(label(r)) + '</b><small>看 ' + esc(hz(r)) +
          (on ? '・<span class="sgon">現在成立</span>' : '') + '</small></td>') +
        '<td class="l wt"><span class="sgd sgd-' + d + '">' + w + '</span></td><td data-h="機率"><b>' + (s ? pc(s[1]) : '—') + '</b>' + (feOf(r, d) ? '<small>預估之後 ' + pc(feOf(r, d)[0]) + '</small>' : '') + '</td><td data-h="隨便挑一天">' + (s ? pc(s[2]) : '—') + '</td>' +
        '<td data-h="多幾個百分點">' + (e == null ? '—' : (e >= 0 ? '+' : '−') + Math.abs(Math.round(e))) + '</td>' +
        '<td data-h="報酬中位數">' + (r[I.cat] === 'strat' ? '—' : medCell(r, d, s)) + '</td>' +
        '<td class="r10" data-h="近 10 年">' + r10(s, d, r[I.cat] === 'stock') + '</td><td data-h="出現">' + (s ? s[0] : '—') + '</td>' +
        '<td data-h="判定">' + mark(s ? s[6] : 'few', r) + luckTxt(s, r) + '</td></tr>'; }).join('') + '</tbody>'; }).join('');
  return '<div class="sgwrap sgsw"><table class="sgst2">' + head + body + '</table></div>'; }
function panelHtml(x){
  const ck = chartable(x);
  let h = '<div class="sgph"><div><p class="sgkick">' + esc(meta(x)) + '</p><h3 id="sgpt">' + esc(x.name) + '</h3></div>' +
    '<button type="button" class="sgx" id="sgx" aria-label="關閉">×</button></div><div class="sgpc">';
  h += '<h4>現在</h4>' + nowHtml(x);
  if (ck) h += '<h4>走勢</h4><div class="sgcb"><div class="sgseg" data-g="span"><button type="button" data-v="1y">近 1 年</button>' +
    '<button type="button" data-v="5y">近 5 年</button><button type="button" data-v="all">全部</button></div>' +
    (x.cat === 'heat' ? '<div class="sgseg" data-g="raw"><button type="button" data-v="0">0～100</button><button type="button" data-v="1">原始值</button></div>' : '') +
    '</div><div class="sgcv" id="sgcv"><p class="note">走勢載入中…</p></div><p class="sgread" id="sgread"></p><p class="note" id="sgleg"></p>';
  h += '<h4>這個指標的訊號</h4><p class="note">每一種訊號都分偏多、警示兩個方向各算一次。點一列，' + (ck ? '走勢圖的打點和' : '') + '下面的「最近幾次」換成那個訊號。</p>' + sigTable(x);
  h += '<h4>預估之後：<span id="sgfsel"></span> ' + ii('fwd') + '</h4><div id="sgfe" class="sgfe"></div>';
  h += '<h4>進場之後：<span id="sgrsel"></span></h4><div id="sgret"></div>';
  h += '<h4>最近幾次：<span id="sgsel"></span></h4><div id="sgrec"></div>';
  h += '<details class="sghow"><summary>怎樣算出現、怎樣算中了</summary><div id="sghow"></div></details>';
  return h + '</div>'; }
function segSync(){ PB.querySelectorAll('.sgseg').forEach(g => g.querySelectorAll('button').forEach(b =>
  b.classList.toggle('on', g.dataset.g === 'span' ? b.dataset.v === VIEW.span : b.dataset.v === (VIEW.raw ? '1' : '0')))); }
function openInd(x, sid, push){
  if (x.cat === 'xs') { xsOpen(x, push); return; }
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
  if (x.pay) h += '<p class="sgdl">' + esc(payTxt(x)) + (x.old ? '（後台的 A／B／C 評級：' + esc(x.old) + '；個股策略的推薦用這裡的判定）' : '') + '</p>';
  if (r[I.cat] === 'buy' && (x.b1 != null || x.lp != null)) h += '<p class="sgdl">另列（不判定）：' +
    [x.b1 != null ? '同一批大跌「隔天就買」3 個月後上漲 ' + pc(x.b1) : '', x.lp != null ? '買在這一波相對低點（事件前高點到之後最低收盤的下三分之一）' + pc(x.lp) + '（' + x.lpn + ' 次，這一波已經結束的）' : '']
      .filter(Boolean).join('；') + '。</p>';
  if (r[I.a]) h += '<p class="sgdl note">資料期間 ' + ymd(r[I.a]) + '～' + ymd(r[I.z]) + '。</p>';
  const rl = rel(r); if (rl) h += '<p class="sgdl"><b>相關研究</b>：' + rl + '</p>';
  const mk = r[I.mk];
  if (['heat', 'deriv', 'multi', 'crash', 'tech'].includes(r[I.cat]) && SG.chart[mk])
    h += '<p class="sgdl"><a href="' + (mk === 'tw' ? 'x9m.html' : 'x9mu.html#ix=' + mk) + '">在景氣頁看' + esc(SG.mk[mk]) + ' →</a></p>';
  if (r[I.cat] === 'scen' && SG.chart[mk])
    h += '<p class="sgdl"><a href="' + (mk === 'tw' ? 'x9m.html#o=scen' : 'x9mu.html#ix=' + mk + '&o=scen') + '">在景氣頁看' + esc(SG.mk[mk]) + '的全部情境 →</a></p>';
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
  if (!['heat', 'deriv', 'crash', 'multi', 'scen', 'tech', 'bub'].includes(c)) return occHtml(r, oc);
  const d = r[I.dir][0], x = CUR, J = x ? CJ[x.mk] : null, ck = x ? sck(x) : null, ev = r[I.kind] === 'event';
  const sk = ev && OCC && OCC.skip ? OCC.skip[r[I.id]] || [] : [];
  const mo = (r[I.x] || {}).monthly, h = hz(r);
  const list = (ev ? oc.map(o => ({o})).concat(sk.map(k => ({k}))).sort((a, b) => (a.o ? a.o[0] : a.k[0]) < (b.o ? b.o[0] : b.k[0]) ? -1 : 1)
    : oc.map(o => ({o}))).slice(-12).reverse();
  const vv = dt => { const v = valAt(J, ck, dt); return v == null ? '<span class="mu">—</span>' : '<span class="zt' + zi(v) + '">' + Math.round(v) + '</span>'; };
  const cls = v => v == null || isNaN(v) ? '' : v >= 0 ? ' class="up"' : ' class="dn"';
  const head = '<thead><tr><th class="l">' + (ev ? '出現日' : '期間') + '</th>' + (ck ? '<th>當時 0～100</th>' : '') + '<th>之後 ' + esc(h) + '漲跌</th>' +
    '<th>期間最大回撤 ' + ii('dd') + '</th><th>' + (ev ? (d === 'warn' ? '大跌' : '上漲') : (d === 'warn' ? '大跌的比例' : '上漲的比例')) + '</th></tr></thead>';
  const body = list.map(e => { const o = e.o;
    if (e.k) return '<tr class="sk"><td class="l">' + ymd(e.k[0]) + '</td><td colspan="' + (ck ? 4 : 3) + '" class="l">' +
      (e.k[1] === 'd' ? '沒算進次數：和 ' + ymd(e.k[2]) + ' 那次相隔不到' + esc(h) + '（之後的漲跌重疊，算同一次）' : '之後' + esc(h) + '還沒走完，還沒算') + '</td></tr>';
    if (ev) { const hit = d === 'warn' ? o[2] : o[1];
      return '<tr><td class="l">' + ymd(o[0]) + '</td>' + (ck ? '<td>' + vv(o[0]) + '</td>' : '') + '<td' + cls(o[4]) + '>' + sp1(o[4]) + '</td><td>' + p1(o[3]) + '</td>' +
        '<td>' + (hit ? '✓' : '<span class="mu">✗</span>') + '</td></tr>'; }
    const j = d === 'warn' ? 4 : 3;
    return '<tr><td class="l">' + ymd(o[0]) + (o[1] !== o[0] ? '～' + ymd(o[1]) : '') + '<small>' + o[2] + (mo ? ' 個月' : ' 天') + '</small></td>' +
      (ck ? '<td>' + vv(o[0]) + '</td>' : '') + '<td' + cls(o[6]) + '>' + sp1(o[6]) + '</td><td>' + p1(o[5]) + '</td><td>' + Math.round(o[j] * 100) + '%</td></tr>'; }).join('');
  const nd = sk.filter(k => k[1] === 'd').length, ni = sk.length - nd;
  const cnt = ev ? '<p class="note">一共出現 ' + (oc.length + sk.length) + ' 次，算進次數 ' + oc.length + ' 次' +
    (nd ? '；' + nd + ' 次和前一次算進去的相隔不到' + esc(h) + '（之後的漲跌和那一次重疊，算同一次，灰色）' : '') +
    (ni ? '；' + ni + ' 次之後' + esc(h) + '還沒走完（灰色）' : '') + '。</p>' : '';
  return cnt + '<div class="sgwrap"><table class="sgrt">' + head + '<tbody>' + body + '</tbody></table></div>' +
    '<p class="note">' + (ev ? '列最近 12 次（含沒算進次數的）' : '共 ' + oc.length + ' 段，列最近 12 段；漲跌、最大回撤、比例是這一段每一天的平均，還在觀察期內的日子不算') + '。' +
    (ck ? '「當時 0～100」是' + (ev ? '出現' : '開始') + '那一天的值（一年以前的用那一週）。' : '') + '</p>'; }
function fillSel(){ const r = SEL, box = document.getElementById('sgrec'); if (!r || !box) return;
  document.getElementById('sgsel').textContent = label(r);
  document.getElementById('sgrsel').textContent = label(r);
  document.getElementById('sghow').innerHTML = howHtml(r);
  const fe = document.getElementById('sgfe'); if (fe) { document.getElementById('sgfsel').textContent = label(r); fe.innerHTML = feHtml(r); }
  PB.querySelectorAll('.sgsb').forEach(b => b.classList.toggle('sel', b.dataset.id === r[I.id]));
  const rt = document.getElementById('sgret');
  if (OCC) { box.innerHTML = recHtml(r, OCC.occ[r[I.id]]); rt.innerHTML = retHtml(r, OCC); drawRet(r, OCC); return; }
  box.innerHTML = rt.innerHTML = '<p class="note">載入中…</p>';
  loadOcc().then(j => { if (SEL !== r) return;
    box.innerHTML = j ? recHtml(r, j.occ[r[I.id]]) : '<p class="note">載入失敗，請重新整理。</p>';
    rt.innerHTML = j ? retHtml(r, j) : ''; if (j) drawRet(r, j); drawChart(); }); }

// ── 進場之後的報酬（sigspec 第 4.11 節，VER 5；只呈現，判定不變）
const RHN = {1:'1 天', 5:'1 週', 10:'2 週', 20:'1 個月', 60:'3 個月', 120:'6 個月', 250:'12 個月'};
const sr1 = v => v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + '%';
const dn1 = v => v == null ? '—' : (v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + '%';
function retSpec(r, j){ const q = j && j.ret ? j.ret[r[I.id]] : null; if (!q) return null;
  const mo = !!q.hm, c = r[I.cat];
  return {q, b: q.b && j.rb ? j.rb[q.b] || null : null, mo, hs: mo ? SG.rhm : SG.rh, ps: mo ? SG.rhm : SG.pd,
    bn: '隨便挑一天',
    own: c === 'buy' ? 60 : c === 'ind' ? 12 : c === 'stock' ? 20 : r[I.H],
    entry: c === 'buy' ? '照規則的買進日收盤進場' : c === 'stock' ? '訊號隔天開盤進場' : c === 'ind' ? '那個月底進場' : '訊號出現隔一個交易日收盤進場',
    hn: h => mo ? h + ' 個月' : RHN[h] || h + ' 天'}; }
// 報酬的穩健數字（sigspec 第 4.11 節 VER 17）：c＝[次數, 平均, 25%, 中位數, 75%, 上漲比例, 中途最多跌中位數, 最差 10%, 最差一次, 排除極端, 去掉最好一次]
function carried(c){ return c && c[1] != null && c[10] != null && c[1] > 0 && c[10] < c[1] / 2; }   // 去掉最好一次，平均剩不到一半
function robustTxt(c){ if (!c || c[9] == null) return '';
  return '<br>排除極端（去掉最好和最差幾次）的平均 <b>' + sr1(c[9]) + '</b>' + (c[10] != null ? '、去掉最好一次的平均 ' + sr1(c[10]) : '') +
    '（平均 ' + sr1(c[1]) + '）' + (carried(c) ? '：<b class="dn">成績靠少數幾次撐起來</b>' : '') + '。'; }
function retHtml(r, j){
  if (r[I.cat] === 'strat') return '<p class="note">策略照自己的規則買賣，每一筆的報酬在<a href="x9.html">個股頁</a>的策略說明卡；逐筆沒有每天的價格，不算中途最多跌。</p>';
  const R = retSpec(r, j); if (!R) return '<p class="note">沒有進場之後的報酬資料。</p>';
  const {q, b, hs, bn} = R, oi = hs.indexOf(R.own), os = oi >= 0 ? q.s[oi] : null, ob = oi >= 0 && b ? b.s[oi] : null;
  let h = '';
  if (os) h += '<p class="sgdl">' + esc(R.entry) + '，持有 <b>' + esc(R.hn(R.own)) + '</b>：報酬中位數 <b>' + sr1(os[3]) + '</b>' +
    (ob ? '（' + esc(bn) + ' ' + sr1(ob[3]) + '）' : '') + '，一半落在 ' + sr1(os[2]) + '～' + sr1(os[4]) + '；上漲的機率 ' + Math.round(os[5]) + '%' +
    (ob ? '（' + Math.round(ob[5]) + '%）' : '') + '。<br>進場之後中途最多跌：一半的時候在 <b>' + dn1(os[6]) + '</b> 以內、最差的一成跌超過 <b>' + dn1(os[7]) + '</b>' +
    (ob ? '（' + esc(bn) + ' ' + dn1(ob[6]) + '、' + dn1(ob[7]) + '）' : '') + '，最差一次 ' + dn1(os[8]) + '。' +
    (os[0] < SG.rmin ? '<span class="mu">（只有 ' + os[0] + ' 次，只當參考）</span>' : '') + robustTxt(os) + '</p>';
  const sub = (v, f) => b && v != null ? '<small>' + f(v) + '</small>' : '';
  const head = '<thead><tr><th class="l">持有</th><th>上漲的機率 ' + ii('rup') + '</th><th>報酬中位數 ' + ii('rmed') + '</th>' +
    '<th>排除極端 ' + ii('rtrim') + '</th><th>去掉最好一次 ' + ii('rlbo') + '</th><th>一半落在 ' + ii('rhalf') + '</th>' +
    '<th>中途最多跌<br>中位數 ' + ii('rmae') + '</th><th>中途最多跌<br>最差 10% ' + ii('rmae10') + '</th><th>次數</th></tr></thead>';
  const body = hs.map((hh, i) => { const s = q.s[i], z = b ? b.s[i] : null;
    if (!s) return '<tr class="na"><td class="l">' + esc(R.hn(hh)) + '</td><td colspan="8" class="mu">資料不夠（窗口還沒走完）</td></tr>';
    return '<tr' + (hh === R.own ? ' class="own"' : '') + (s[0] < SG.rmin ? ' data-few="1"' : '') + '><td class="l">' + esc(R.hn(hh)) +
      (hh === R.own ? '<small>判定看這一期</small>' : R.mo ? '' : '<small>' + hh + ' 個交易日</small>') + '</td>' +
      '<td data-h="上漲的機率"><b>' + Math.round(s[5]) + '%</b>' + sub(z && z[5], v => Math.round(v) + '%') + '</td>' +
      '<td data-h="報酬中位數" class="' + (s[3] > 0 ? 'up' : s[3] < 0 ? 'dn' : '') + '"><b>' + sr1(s[3]) + '</b>' + sub(z && z[3], sr1) + '</td>' +
      '<td data-h="排除極端">' + (s[9] == null ? '—' : sr1(s[9])) + sub(z && z[9], sr1) + '</td>' +
      '<td data-h="去掉最好一次">' + (s[10] == null ? '—' : sr1(s[10])) + (carried(s) ? '<small class="dn">靠少數幾次</small>' : '') + '</td>' +
      '<td data-h="一半落在">' + sr1(s[2]) + '～' + sr1(s[4]) + (z ? '<small>' + sr1(z[2]) + '～' + sr1(z[4]) + '</small>' : '') + '</td>' +
      '<td data-h="中途最多跌・中位數">' + dn1(s[6]) + sub(z && z[6], dn1) + '</td>' +
      '<td data-h="中途最多跌・最差 10%">' + dn1(s[7]) + sub(z && z[7], dn1) + '</td>' +
      '<td data-h="次數">' + s[0] + (s[0] < SG.rmin ? '<small>次數少</small>' : '') + '</td></tr>'; }).join('');
  return h + '<div class="sgwrap sgrw"><table class="sgrr">' + head + '<tbody>' + body + '</tbody></table></div>' +
    '<p class="note">' + (b ? '每格下面的小字＝' + esc(bn) + '（同一段期間、同樣算法）。' : '') +
    (r[I.kind] === 'state' ? '狀態型：狀態中的每一天都算進場一次，每一天一樣重。' : '') +
    '價格是指數本身、不含股息。' + (r[I.cat] === 'stock' ? '個股訊號的判定（★／●）照上表（比隨便挑一天多幾個百分點、打亂測試）；這張表只呈現。' : '偏多與買點的判定（★／◆）看「判定看這一期」那一列：上漲的機率、報酬中位數與排除極端的平均；警示看上表大回撤的機率；其他期間只呈現。') + '</p><div class="sgrcv" id="sgrcv"></div><p class="sgread" id="sgrrd"></p>' +
    '<p class="note">實線＝進場之後的報酬中位數、色帶＝一半落在的範圍' + (b ? '；虛線與灰色帶＝' + esc(bn) : '') + '。橫軸＝進場之後經過' + (R.mo ? '幾個月' : '幾個交易日') + '。</p>'; }
function drawRet(r, j){
  const box = document.getElementById('sgrcv'), R = retSpec(r, j); if (!box || !R) return;
  const {q, b, ps} = R, mo = R.mo;
  const pts = (src) => [[0, [0, 0, 0]]].concat(ps.map((d, i) => [d, src && src.p ? src.p[i] : null]));
  const P1 = pts(q), P0 = b ? pts(b) : null;
  const all = P1.concat(P0 || []).filter(p => p[1]).flatMap(p => p[1]);
  if (all.length < 6) { box.innerHTML = ''; return; }
  const W = Math.max(280, Math.round(box.clientWidth || 520)), L = 44, Rr = 10, T = 10, H = 170, BH = 18;
  const dmax = ps[ps.length - 1], X = d => L + Math.sqrt(d / dmax) * (W - L - Rr);
  let lo = Math.min(0, ...all), hi = Math.max(0, ...all); const pd = (hi - lo) * 0.08 || 1; lo -= pd; hi += pd;
  const Y = v => T + (1 - (v - lo) / (hi - lo)) * H;
  const line = (P, k) => { let d = '', pen = false; P.forEach(p => { if (!p[1]) { pen = false; return; } d += (pen ? 'L' : 'M') + X(p[0]).toFixed(1) + ' ' + Y(p[1][k]).toFixed(1); pen = true; }); return d; };
  const band = P => { const a = P.filter(p => p[1]); if (a.length < 2) return '';
    return 'M' + a.map(p => X(p[0]).toFixed(1) + ' ' + Y(p[1][2]).toFixed(1)).join('L') + 'L' + a.slice().reverse().map(p => X(p[0]).toFixed(1) + ' ' + Y(p[1][0]).toFixed(1)).join('L') + 'Z'; };
  let g = '<line class="z0" x1="' + L + '" x2="' + (W - Rr) + '" y1="' + Y(0).toFixed(1) + '" y2="' + Y(0).toFixed(1) + '"/>';
  const step = (hi - lo) > 40 ? 20 : (hi - lo) > 16 ? 10 : (hi - lo) > 8 ? 5 : 2;
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) g += '<text class="ax" x="' + (L - 4) + '" y="' + (Y(v) + 4).toFixed(1) + '" text-anchor="end">' + (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v) + '%</text>';
  if (P0) g += '<path class="rb0" d="' + band(P0) + '"/><path class="rm0" d="' + line(P0, 1) + '"/>';
  g += '<path class="rb1" d="' + band(P1) + '"/><path class="rm1" d="' + line(P1, 1) + '"/>';
  P1.forEach(p => { if (p[1] && p[0]) g += '<circle class="rp" cx="' + X(p[0]).toFixed(1) + '" cy="' + Y(p[1][1]).toFixed(1) + '" r="2.4"/>'; });
  const tk = mo ? [[1, '1月'], [3, '3月'], [6, '6月'], [12, '12月']] : [[5, '1週'], [20, '1月'], [60, '3月'], [120, '6月'], [250, '12月']];
  tk.forEach(([d, t], k) => { g += '<text class="ax" x="' + X(d).toFixed(1) + '" y="' + (T + H + BH - 4) + '" text-anchor="' + (k === tk.length - 1 ? 'end' : 'middle') + '">' + t + '</text>'; });
  g += '<line class="hv" id="sgrhv" x1="0" x2="0" y1="' + T + '" y2="' + (T + H) + '" style="display:none"/><rect class="hit" x="' + L + '" y="0" width="' + (W - L - Rr) + '" height="' + (T + H + BH) + '"/>';
  box.innerHTML = '<svg class="sgchart sgrch" viewBox="0 0 ' + W + ' ' + (T + H + BH) + '" width="' + W + '" height="' + (T + H + BH) + '" role="img" aria-label="進場之後的報酬">' + g + '</svg>';
  const svg = box.querySelector('svg'), hv = svg.querySelector('#sgrhv'), rd = document.getElementById('sgrrd');
  const show = i => { const p = P1[i], z = P0 ? P0[i] : null; if (!p || !p[0]) { hv.style.display = 'none'; rd.textContent = ''; return; }
    const xx = X(p[0]).toFixed(1); hv.setAttribute('x1', xx); hv.setAttribute('x2', xx); hv.style.display = '';
    rd.innerHTML = '<b>持有 ' + esc(R.hn(p[0])) + '</b>　' + (p[1] ? '中位數 ' + sr1(p[1][1]) + '（一半落在 ' + sr1(p[1][0]) + '～' + sr1(p[1][2]) + '）' : '—') +
      (z && z[1] ? '　' + esc(R.bn) + ' ' + sr1(z[1][1]) : ''); };
  const mv = e => { const bb = svg.getBoundingClientRect(), cx = ((e.touches ? e.touches[0].clientX : e.clientX) - bb.left) * W / bb.width;
    let k = 1, dm = 1e9; P1.forEach((p, i) => { if (!i) return; const dd = Math.abs(X(p[0]) - cx); if (dd < dm) { dm = dd; k = i; } }); show(k); };
  svg.addEventListener('mousemove', mv); svg.addEventListener('touchmove', mv, {passive: true}); svg.addEventListener('touchstart', mv, {passive: true});
  svg.addEventListener('mouseleave', () => { hv.style.display = 'none'; rd.textContent = ''; }); }

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
function pxSeries(J){ const span = VIEW.span;
  if (span === '1y') return {d: J.d.d, px: J.d.px, v: null, raw: false, po: true};
  const d = J.w.d, n = d.length, a = span === '5y' ? Math.max(0, n - 261) : 0;
  return {d: d.slice(a), px: J.w.px.slice(a), v: null, raw: false, po: true}; }
function drawChart(){
  const x = CUR, box = document.getElementById('sgcv'); if (!x || !box || !chartable(x)) return; const ck = ckOf(x);
  loadChart(x.mk).then(J => {
    if (CUR !== x || !box.isConnected) return;
    const S = J && (ck && J.s && J.s[ck] ? series(J, ck) : (J.d && J.w ? pxSeries(J) : null));
    if (!S) { box.innerHTML = '<p class="note">這一項沒有走勢資料。</p>'; return; }
    const rb = document.getElementById('sgrec');                                // 走勢資料到了：最近幾次補上「當時 0～100」
    if (rb && OCC && SEL) rb.innerHTML = recHtml(SEL, OCC.occ[SEL[I.id]]);
    const po = !!S.po;                                                           // 只有指數（技術事件、大跌風險、泡沫、買點…）
    const W = Math.max(280, Math.round(box.clientWidth || 520)), L = po ? 50 : 40, R = 8, T = 8, H1 = po ? 190 : 150, G = po ? 0 : 20, H2 = po ? 0 : 72, BH = 18;
    const n = S.d.length, X = i => L + (n > 1 ? i / (n - 1) : 0) * (W - L - R);
    const ps = S.px.filter(p => p != null && p > 0), pl = Math.log(Math.min(...ps)), ph = Math.log(Math.max(...ps)) + 1e-9;
    let lo = 0, hi = 100;
    if (!po && S.raw) { const vs = S.v.filter(v => v != null); if (vs.length) { lo = Math.min(...vs); hi = Math.max(...vs); const pd = (hi - lo) * 0.06 || 1; lo -= pd; hi += pd; } }
    const Y1 = po ? (p => T + (1 - (Math.log(p) - pl) / (ph - pl)) * H1) : (v => T + (1 - (v - lo) / (hi - lo)) * H1);
    const Y2 = p => T + H1 + G + (1 - (Math.log(p) - pl) / (ph - pl)) * H2;
    const ypx = i => po ? Y1(S.px[i]) : Y2(S.px[i]);
    const Ht = T + H1 + G + H2 + BH;
    let g = '';
    // 訊號：狀態型畫色帶、事件型打點（實心＝之後中了、空心＝沒中）
    const r = SEL, oc = OCC && r ? OCC.occ[r[I.id]] : null, d0 = r ? r[I.dir][0] : 'up', ev = r && r[I.kind] === 'event';
    if (oc && !ev) oc.forEach(o => { const a = idxOf(S.d, o[0]), z = idxOf(S.d, o[1]); if (z < 0 || a >= n - 1 && S.d[n - 1] < o[0]) return;
      const sh = d0 === 'warn' ? o[4] : o[3], xa = X(Math.max(0, a)), xz = X(Math.max(0, z)) + 1.5;
      g += '<rect class="bd" x="' + xa.toFixed(1) + '" y="' + T + '" width="' + Math.max(2, xz - xa).toFixed(1) + '" height="' + H1 + '" style="opacity:' + (0.10 + 0.35 * sh).toFixed(2) + '"/>'; });
    const on = r && ON[r[I.id]];
    if (on && !ev && on.since) { const a = idxOf(S.d, on.since); if (a < n) g += '<rect class="bdn" x="' + X(Math.max(0, a)).toFixed(1) + '" y="' + T + '" width="' + (X(n - 1) - X(Math.max(0, a)) + 1.5).toFixed(1) + '" height="' + H1 + '"/>'; }
    if (po) {
      [Math.exp(pl + (ph - pl) * 0.05), Math.exp((pl + ph) / 2), Math.exp(ph - (ph - pl) * 0.05)].forEach(p => {
        g += '<text class="ax" x="' + (L - 4) + '" y="' + (Y1(p) + 4).toFixed(1) + '" text-anchor="end">' + Math.round(p).toLocaleString('en-US') + '</text>'; });
      g += '<path class="lv" d="' + pathOf(S.px.map(p => p > 0 ? p : null), X, Y1) + '"/>';
      g += '<text class="ax" x="' + (L + 2) + '" y="' + (T + 11) + '">' + esc(SG.pxn[x.mk] || '') + '（對數）</text>';
    } else {
      if (!S.raw) [80, 20].forEach(v => { g += '<line class="tl" x1="' + L + '" x2="' + (W - R) + '" y1="' + Y1(v).toFixed(1) + '" y2="' + Y1(v).toFixed(1) + '"/>'; });
      const ticks = S.raw ? [lo + (hi - lo) * 0.06, (lo + hi) / 2, hi - (hi - lo) * 0.06] : [0, 20, 50, 80, 100];
      ticks.forEach(v => { g += '<text class="ax" x="' + (L - 4) + '" y="' + (Y1(v) + 4).toFixed(1) + '" text-anchor="end">' + (S.raw ? fmtV(x, v, true).replace(/ .*$/, '') : v) + '</text>'; });
      g += '<path class="lv" d="' + pathOf(S.v, X, Y1) + '"/>';
      g += '<path class="lp" d="' + pathOf(S.px.map(p => p > 0 ? p : null), X, Y2) + '"/>';
      g += '<text class="ax" x="' + (L + 2) + '" y="' + (T + H1 + G - 5) + '">' + esc(SG.pxn[x.mk] || '') + '</text>';
    }
    const skl = ev && r && OCC && OCC.skip ? OCC.skip[r[I.id]] || [] : [];
    skl.forEach(k => { const i = idxOf(S.d, k[0]); if (i < 0 || (i === n - 1 && S.d[n - 1] < k[0]) || k[0] < S.d[0]) return;
      const v = po ? null : S.v[i], cy = v != null ? Y1(v) : ypx(i);
      g += '<circle class="mk sk" cx="' + X(i).toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="2.6"/>'; });
    if (oc && ev) oc.forEach(o => { const i = idxOf(S.d, o[0]); if (i < 0 || (i === n - 1 && S.d[n - 1] < o[0]) || o[0] < S.d[0]) return;
      const v = po ? null : S.v[i], hit = d0 === 'warn' ? o[2] : o[1], cy = v != null ? Y1(v) : ypx(i);
      g += '<circle class="mk' + (hit ? ' y' : '') + '" cx="' + X(i).toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="3.6"/>'; });
    if (on && ev && on.since) { const i = idxOf(S.d, on.since); if (i >= 0 && on.since >= S.d[0]) { const v = po ? null : S.v[i];
      g += '<circle class="mk now" cx="' + X(i).toFixed(1) + '" cy="' + (v != null ? Y1(v) : ypx(i)).toFixed(1) + '" r="4.2"/>'; } }
    const nt = Math.min(6, Math.max(2, Math.floor(W / 110)));
    for (let k = 0; k < nt; k++) { const i = Math.round(k * (n - 1) / (nt - 1)), dt = S.d[i] || '';
      const t = VIEW.span === '1y' ? (+dt.slice(5, 7)) + '月' : VIEW.span === '5y' ? dt.slice(0, 4) + '/' + (+dt.slice(5, 7)) : dt.slice(0, 4); const anc = k === 0 ? 'start' : k === nt - 1 ? 'end' : 'middle';
      g += '<text class="ax" x="' + X(i).toFixed(1) + '" y="' + (Ht - 4) + '" text-anchor="' + anc + '">' + t + '</text>'; }
    g += '<line class="hv" id="sghv" x1="0" x2="0" y1="' + T + '" y2="' + (T + H1 + G + H2) + '" style="display:none"/>';
    g += '<rect class="hit" x="' + L + '" y="0" width="' + (W - L - R) + '" height="' + Ht + '"/>';
    box.innerHTML = '<svg class="sgchart" viewBox="0 0 ' + W + ' ' + Ht + '" width="' + W + '" height="' + Ht + '" role="img" aria-label="' + esc(x.name) + '的走勢">' + g + '</svg>';
    const svg = box.querySelector('svg'), hv = svg.querySelector('#sghv'), rd = document.getElementById('sgread');
    const pxt = i => S.px[i] == null ? '—' : Math.round(S.px[i]).toLocaleString('en-US');
    const show = i => { const xx = X(i).toFixed(1); hv.setAttribute('x1', xx); hv.setAttribute('x2', xx); hv.style.display = '';
      rd.innerHTML = '<b>' + ymd(S.d[i]) + '</b>　' + (po ? '' : esc(x.name) + ' ' + fmtV(x, S.v[i], S.raw) + '　') + esc(SG.pxn[x.mk] || '') + ' ' + pxt(i); };
    const mv = e => { const b = svg.getBoundingClientRect(), cx = (e.touches ? e.touches[0].clientX : e.clientX) - b.left;
      show(Math.max(0, Math.min(n - 1, Math.round((cx * W / b.width - L) / ((W - L - R) / Math.max(1, n - 1)))))); };
    svg.addEventListener('mousemove', mv); svg.addEventListener('touchmove', mv, {passive: true}); svg.addEventListener('touchstart', mv, {passive: true});
    svg.addEventListener('mouseleave', () => { show(n - 1); hv.style.display = 'none'; });
    show(n - 1); hv.style.display = 'none';
    const lab = r ? label(r) : '', hitw = d0 === 'warn' ? '大跌' : '上漲';
    const evw = r && r[I.cat] === 'buy' ? '照「' + esc(lab) + '」買進的那天' : '「' + lab + '」出現的日子';
    const lastO = oc && oc.length ? oc[oc.length - 1][ev ? 0 : 1] : null, lastD = on && on.since && (!lastO || on.since > lastO) ? on.since : lastO;
    const hint = r && lastD && lastD < S.d[0] ? '<span class="sghint">這段期間沒有出現；最近一次 ' + ymd(lastD) + '。' +
      (VIEW.span !== 'all' ? '<button type="button" class="sgmore2" data-span="' + (VIEW.span === '1y' ? '5y' : 'all') + '">看' + (VIEW.span === '1y' ? '近 5 年' : '全部') + '</button>' : '') + '</span>' : '';
    document.getElementById('sgleg').innerHTML = hint + esc((po ? '線＝' + (SG.pxn[x.mk] || '') + '（對數）。' :
      '上＝' + x.name + (S.raw ? '（原始值）' : '（0～100，虛線＝80 過熱、20 過冷）') + '；下＝' + (SG.pxn[x.mk] || '') + '（對數）。') +
      (r ? (ev ? '點＝' + evw + '：實心＝之後' + hitw + '（中了）、空心＝沒中' + (skl.length ? '、灰色小虛線圈＝出現了但沒算進次數（和前一次相隔太近，或還沒走完）' : '') + (on ? '、大圈＝這一次（還在觀察）' : '') + '。'
        : '色帶＝「' + lab + '」的期間，越深＝那一段之後' + hitw + '的比例越高' + (on ? '；虛線框＝現在這一段（還在觀察）' : '') + '。') : '') +
      (OCC ? '' : '（訊號的日子載入中）')); }); }
let rzT = null;
window.addEventListener('resize', () => { clearTimeout(rzT); rzT = setTimeout(() => { if (!CUR) return;
  if (CUR.cat === 'xs') { xsEq(CUR); return; } drawChart(); if (OCC && SEL) drawRet(SEL, OCC); }, 200); });
PB.addEventListener('click', e => {
  if (e.target.closest('#sgx')) { closeP(); return; }
  if (CUR && CUR.cat === 'xs') { xsClick(e); return; }
  const mb = e.target.closest('.sgmore2');
  if (mb) { VIEW.span = mb.dataset.span; segSync(); drawChart(); fillSel(); return; }
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
    '出現過幾次','判定','亂排也做得到%','最大回撤中位數%','隨便挑一天最大回撤中位數%','大跌門檻%','報酬中位數%','排除極端的平均%','預估之後的機率%','預估之後比隨便挑一天多賺%','代號'];
  const lines = [head];
  list.forEach(x => x.cat !== 'xs' && x.sig.forEach(r => dirsOf(r).forEach(d => { const s = stat(r, d), e = dEdge(s);
    lines.push([x.name, SG.mk[x.mk], facName(x), label(r), hz(r), nowTxt(r), SG.dirs[d] || d, what(r, d), s ? s[1] : '', s ? s[2] : '', e == null ? '' : e.toFixed(1),
      s ? (s[3] ?? '') : '', s ? (s[4] ?? '') : '', s ? (s[5] ?? '') : '', s ? s[0] : '', s ? (SG.tiers[s[6]] || ['', ''])[1] : '',
      s ? (s[9] ?? '') : '', d === 'warn' && s ? (s[7] ?? '') : '', d === 'warn' && s ? (s[8] ?? '') : '', d === 'warn' ? (r[I.th] ?? '') : '',
      (r[I.x] || {}).med ?? '', (r[I.x] || {}).trm ?? '', feOf(r, d) ? feOf(r, d)[0] : '', feOf(r, d) && feOf(r, d)[3] != null ? feOf(r, d)[3] : '', r[I.id]]); })));
  const csv = '﻿' + lines.map(l => l.map(v => { const t = String(v == null ? '' : v); return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; }).join(',')).join('\n');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'})); a.download = '訊號總覽.csv'; a.click(); });


// ── 總經策略的面板（xstratpage.PANEL_JS，建頁時接在這裡）
/*@@XSPANEL@@*/
function xsOpen(x, push){
  const first = PV.hidden;
  CUR = x; SEL = x.best; XSV.all = false;
  if (push) { const u = '#i=' + encodeURIComponent(x.k);
    if (first && !PUSHED) { history.pushState({sg: 1}, '', u); PUSHED = true; } else history.replaceState(history.state, '', u); }
  PB.innerHTML = xsPanel(x); xsSeg();
  PV.hidden = false; document.body.classList.add('sgopen');
  PB.scrollTop = 0; if (first) PB.focus({preventScroll: true});
  document.querySelectorAll('tr.sgr.open').forEach(e => e.classList.remove('open'));
  const tr = document.querySelector('tr.sgr[data-k="' + CSS.escape(x.k) + '"]'); if (tr) tr.classList.add('open');
  xsFill(x); }

// ── 研究結論（findings）：選市場切換七則問答；最下面「完整研究表」打開時才載入那個市場的研究卡
const RMK = SG.rmk || [], RCACHE = {};
let RSEL = (document.querySelector('#rmk .sgch.on') || {dataset: {}}).dataset.r || null;
function rfShow(mk){
  if (!document.querySelector('.rfm[data-mk="' + mk + '"]')) return false;
  RSEL = mk;
  document.querySelectorAll('#rmk .sgch').forEach(b => b.classList.toggle('on', b.dataset.r === mk));
  document.querySelectorAll('.rfm').forEach(el => { el.hidden = el.dataset.mk !== mk; });
  const f = document.getElementById('rfull'); if (f && f.open) loadR(mk);
  return true; }
let RPEND = null;                                    // 要打開的研究卡（載入完才打開）
function rcOpen(mk){
  if (!RPEND || RPEND[0] !== mk) return;
  const el = document.getElementById('rc-' + RPEND[1]); RPEND = null;
  if (el) { el.open = true; el.scrollIntoView({block: 'start'}); } }
function loadR(mk, card){
  const box = document.getElementById('rbox'); if (!box || !RMK.includes(mk)) return;
  if (card) { RPEND = [mk, card]; const f = document.getElementById('rfull'); if (f && !f.open) f.open = true; }
  if (box.dataset.mk === mk) { if (!box.dataset.ld) rcOpen(mk); return; }
  box.dataset.mk = mk;
  const show = h => { if (box.dataset.mk !== mk) return; delete box.dataset.ld; box.innerHTML = h; rcOpen(mk); };
  if (RCACHE[mk]) { show(RCACHE[mk]); return; }
  box.dataset.ld = '1';
  box.innerHTML = '<p class="note">' + esc(SG.mk[mk]) + ' 的研究卡載入中…</p>';
  fetch('x9or-' + mk + '.json').then(x => x.json()).then(j => { RCACHE[mk] = j.html || '<p class="note">這個市場沒有研究卡。</p>'; show(RCACHE[mk]); })
    .catch(() => { if (box.dataset.mk === mk) { box.innerHTML = '<p class="note">載入失敗，請重新整理。</p>'; delete box.dataset.mk; delete box.dataset.ld; } }); }
const rm = document.getElementById('rmk');
if (rm) rm.addEventListener('click', e => { const b = e.target.closest('.sgch'); if (b) rfShow(b.dataset.r); });
const rfl = document.getElementById('rfull');
if (rfl) rfl.addEventListener('toggle', () => { if (rfl.open && RSEL) loadR(RSEL); });
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
  let m = h.match(/^#p=(\w+):(\w+)$/);                                     // 實測區的一格（practpage）
  if (m) { closeP(true); prOpen(m[1], m[2], true); return; }
  m = h.match(/^#r=(\w+)(?::(\w+))?$/);
  if (m) { closeP(true); rfShow(m[1]); if (m[2]) loadR(m[1], m[2]); else { const sec = document.getElementById('research'); if (sec) sec.scrollIntoView({block: 'start'}); } return; }
  m = h.match(/^#i=([^&]+)$/);
  if (m) { const x = BYK[decodeURIComponent(m[1])]; if (x) { if (ev) PUSHED = true; if (CUR !== x) openInd(x, null, false); return; } }
  m = h.match(/^#s=(.+)$/);
  if (m) { const id = decodeURIComponent(m[1]), x = SIG2[id]; if (x) { if (ev) PUSHED = true; openInd(x, id, false); return; } }
  closeP(true); }
/*@@PRACTICE@@*/
window.addEventListener('hashchange', fromHash);
draw(); fromHash();
})();
"""
JS = JS.replace("/*@@XSPANEL@@*/", XSP.PANEL_JS)


def _practice_js() -> str:
    from . import practpage as PP
    return PP.JS


JS = JS.replace("/*@@PRACTICE@@*/", _practice_js())
