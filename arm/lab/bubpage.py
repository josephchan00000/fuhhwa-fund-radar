"""泡沫（docs/lab_risk_plan.md 第 7～9 節；規格 bubspec VER 4；2026-10-23 起 docs/lab_ia_v5_plan.md 第 3 節③、第 15.1 節）。

五個市場（台股、S&P 500、那斯達克、那斯達克 100、費半）的泡沫等級 0～4。原本的泡沫頁 x9b.html 拆成兩處、x9b.html 留成轉址頁（REDIRECT）：
- 市場頁最下面的「泡沫」一塊（block_html／block_data）：等級、七個條件 ✓／✗、歷史等級圖（預設近 30 年）、等級 ≥ 2 的產業一行、全部產業表（收起）。
- 研究紀錄頁（research_body／research_data）：原本泡沫頁的全部內容——每個市場一張卡（一句話、歷史等級、現在的七個條件與兩年拆解、
  等級 ≥ 3 的泡沫段、驗證）、產業（含驗證）、七種條件代表什麼、方法與資料；段落 id 加 bub- 前綴。
VER 2：價格過熱而且價格漲得比基本面快（E）才到等級 3；只有價格過熱最多到 2。
現在的狀態每天重算（bubble.market_for；同一個程序裡景氣頁先算、這裡沿用），產業 bubind.compute 同一個程序只算一次（industries）；
驗證讀研究檔 data/lab/bub_research.json（scripts/run_bub.py，資料或規格改了才重跑）。只描述位置，不是買賣訊號。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import bubble as BU
from . import bubspec as BS
from .heatpage import _e, _ymd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9b.html"

COND_ORDER = BU.CONDS
P_ORDER = ("P1", "P2", "P3")
SHORT = BU.SHORT
TEST_NAMES = {"P1": "價格爆發（PSY）", "P2": "兩年翻倍而且在高點", "P3": "偏離長期趨勢 2 個標準差",
              "E": "價格漲得比基本面快（比值爆發）", "V": "估值歷史前 5%", "F": "槓桿歷史前 10%",
              "PF": "價格過熱，而且漲得比基本面快", "PN": "價格過熱，但基本面有跟上",
              "L2": "等級 ≥ 2（漲勢過熱以上）", "L3": "等級 ≥ 3（泡沫警戒以上）", "L4": "等級 4（嚴重泡沫）",
              "L3v1": "對照：VER 1（只看價格）等級 ≥ 3",
              "G1": "成長減速（明年預估成長比今年低）", "G2": "預估下修，股價還在漲",
              "G": "未來獲利跟不上（兩個都成立）", "PG": "價格過熱，而且未來獲利跟不上", "PnG": "價格過熱，未來獲利還跟得上",
              "L3v3": "對照：VER 3（沒有未來獲利）等級 ≥ 3", "L3v2": "對照：VER 2 等級 ≥ 3",
              "Gr": "對照：用實際獲利算的未來獲利跟不上", "PGr": "對照：價格過熱，而且實際獲利跟不上"}
VALID_TESTS = ("P1", "P2", "P3", "E", "V", "G1", "G2", "G", "F", "PF", "PN", "PG", "PnG", "L2", "L3", "L4", "L3v3", "L3v1")
VALID_SPX = VALID_TESTS + ("Gr", "PGr")
EXT_TESTS = ("P1", "P2", "P3", "E", "G1", "G2", "G", "PF", "PN", "PG", "PnG", "L2", "L3", "L3v3", "L3v1")
DEC_NAMES = {"pe": ("股價", "近 12 個月盈餘"), "pe_tw": ("有盈餘公司的市值", "近四季淨利"), "ex": ("實質加權指數", "實質出口"),
             "wsts": ("費半", "全球半導體銷售額"), "cp": ("指數", "美國企業稅後獲利"), "tech": ("指數", "美國科技業獲利")}
CYC_NAMES = {"pe": "S&P 500 盈餘", "ex": "台灣實質出口", "wsts": "全球半導體銷售額", "cp": "美國企業稅後獲利",
             "tech": "美國科技業獲利"}
EST_NAMES = {"tw": "台股有分析師預估的上市櫃公司", "spx": "S&P 500 成分股", "ixic": "那斯達克市值前 300 大",
             "ndx": "那斯達克 100 成分股", "sox": "費半成分股"}
CYC_HI = 2.0                                       # 景氣高峰參考：比長期趨勢高 2 個標準差以上就在一句話裡提醒
VERDICT = {"crash": "成立後較容易大跌", "calm": "成立後反而較少大跌", "none": "看不出差別", "few": "樣本不足"}
VAL_NAMES = {"X6": "CAPE", "X8": "巴菲特指標", "X9": "Tobin's Q"}
NO_VAL = {"tw": "台股本益比只有 2013 年起，歷史太短", "ixic": "沒有自己的長歷史估值", "ndx": "沒有自己的長歷史估值",
          "sox": "沒有自己的長歷史估值"}


# ── 資料 ───────────────────────────────────────────────────────────────────

def view() -> dict:
    """各市場的現在狀態、歷史等級、泡沫段（沿用這個程序裡景氣頁算好的；沒有就自己載入資料算）＋研究檔。"""
    M: dict = {}
    need = [mk for mk in BS.MARKETS if BU.last(mk) is None]
    if need:
        T = BU.load_cv_table()
        if T:
            if "tw" in need:
                M["tw"] = BU.market("tw", BU.tw_inputs(BU.load_tw()), T)
            us = [mk for mk in need if mk != "tw"]
            if us:
                D = BU.load_us()
                S = BU.us_inputs(D)
                for mk in us:
                    M[mk] = BU.market(mk, BU.us_index_inputs(D, S, mk), T)
    for mk in BS.MARKETS:
        if mk not in M and BU.last(mk) is not None:
            M[mk] = BU.last(mk)
    R = BU.load_research() or {}
    asof = max((m["now"]["d"] for m in M.values()), default=None)
    from . import bubind
    return {"asof": asof, "M": M, "R": R, "I": industries(), "IR": bubind.load_research() or {}}


_IND: dict = {}


def industries() -> dict:
    """產業泡沫的現在狀態（bubind.compute，約 5～9 秒）：同一個程序只算一次——市場頁（台股、美股兩個檔）的泡沫那一塊
    與研究紀錄頁共用。算不出來就回 {"tw_err": …}，不擋市場層級。"""
    if "I" not in _IND:
        from . import bubind
        try:
            _IND["I"] = bubind.compute()
        except Exception as e:                                # noqa: BLE001 —— 產業段失敗不影響市場層級
            _IND["I"] = {"tw_err": f"{type(e).__name__}: {e}"}
    return _IND["I"]


def clear_cache() -> None:
    _IND.clear()


# ── 文字小工具 ───────────────────────────────────────────────────────────────

def _pct(x, dec=0, sign=False) -> str:
    if x is None:
        return "—"
    s = f"{x:+.{dec}f}" if sign else f"{x:.{dec}f}"
    return s + "%"


def _num(x, dec=2) -> str:
    return "—" if x is None else f"{x:,.{dec}f}"


def _mark(v) -> str:
    if v is None:
        return '<span class="na">不判定</span>'
    return '<span class="yes">成立</span>' if v else '<span class="no">沒有</span>'


def _sp(s: str) -> str:
    """英數字結尾的名字後面接中文時補一個空格（「S&P 500 現在是」「Tobin's Q 比長期趨勢高」）。"""
    return s + " " if s and s[-1].isascii() and s[-1].isalnum() else s


def summary(mk: str, m: dict) -> str:
    """一句話：等級、哪些條件同時成立；估值、槓桿的狀況。"""
    n = m["now"]
    lv = n["L"]
    pc = [SHORT[c] for c in P_ORDER if n.get(c)]
    s = f'{_sp(m["name"])}現在是等級 {lv}「{BS.LEVELS[lv]}」'
    if pc:
        s += f'：{"、".join(pc)}成立'
        hits = []
        if n.get("E"):
            hit = [BS.FUND_NAMES4[k] for k, e in (n.get("e") or {}).items() if e.get("on")]
            hits.append(f'價格漲得比基本面快（{"、".join(hit)}爆發）')
        if n.get("V"):
            hits.append("估值在歷史前 5%")
        if n.get("G"):
            hits.append(f'未來獲利跟不上（{_g_short(n)}）')
        if hits:
            s += "，而且" + "、".join(hits)
        else:
            s += "，但價格沒有漲得比基本面快" if n.get("E") is False else "，基本面無法判定"
            d = _dec_short(n)
            if d:
                s += f"（{d}）"
            g = _g_short(n)
            if n.get("G") is False and g:
                s += f"，未來獲利也還跟得上（{g}）"
    elif n.get("V"):
        s += "：估值在歷史前 5%，但價格沒有過熱"
    tail = []
    p2 = n.get("p2") or {}
    if (not n.get("P2") and (p2.get("ru") or 0) >= BS.RUN2_PCT and p2.get("dist") is not None
            and p2["dist"] < -100 * BS.RUN2_ATH):        # 兩年已經翻倍、只差在離最高點太遠：講清楚為什麼沒算
        tail.append(f'兩年已經漲 {p2["ru"]:.0f}%，但收盤離最高點 {abs(p2["dist"]):.1f}%（要在 {100 * BS.RUN2_ATH:.0f}% 以內才算兩年翻倍）')
    if n.get("V") is None:
        tail.append(f'估值不判定（{NO_VAL.get(mk, "沒有資料")}）')
    elif not n.get("V"):                                # 估值沒成立：有幾項已在歷史前 5% 也講出來
        vv = n.get("v") or {}
        hot = [VAL_NAMES[k] for k in BS.VAL_ITEMS if (vv.get(k) or {}).get("pct") is not None and vv[k]["pct"] >= BS.VAL_PCT]
        if hot:
            h = "、".join(hot)
            h = (" " if h[0].isascii() else "") + _sp(h)
            tail.append(f'估值只有{h}在歷史前 {100 - BS.VAL_PCT:.0f}%（要 {BS.VAL_NEED} 項才算）')
    f = n.get("f") or {}
    if f.get("pct") is not None and not n.get("F"):
        tail.append(f'槓桿不在歷史高檔（第 {f["pct"]:.0f} 百分位）')
    for k, e in (n.get("e") or {}).items():
        c = e.get("cyc") or {}
        if c.get("z") is not None and c["z"] >= CYC_HI:
            tail.append(f'{CYC_NAMES[k]}比長期趨勢高 {c["z"]:.1f} 個標準差，基本面本身可能在景氣高峰')
    return s + "。" + ("；".join(tail) + "。" if tail else "")


def _g_src(n: dict) -> dict:
    g = n.get("g") or {}
    return g.get(g.get("src") or "") or {}


def _g_short(n: dict) -> str:
    """一句話裡的未來獲利：哪一半成立、哪一半沒有（分析師預估；沒有就用專業預測者調查）。"""
    g = n.get("g") or {}
    e = g.get("est") or {}
    src = "預估"
    if e.get("g0") is None or e.get("g1") is None:
        p = g.get("proxy") or {}
        if p.get("src") != "spf" or p.get("g0") is None or p.get("g1") is None:
            return ""
        e, src = p, "專業預測者預估"
    a, b = _pct(100 * e["g1"], 0, True), _pct(100 * e["g0"], 0, True)
    x = f"明年{src}成長 {a}，{'比' if e.get('G1') else '不比'}今年 {b} 低"
    r = e.get("rev")
    if e.get("G1") and r is not None:
        if e.get("G2"):
            x += f"，明年預估近 3 個月下修 {abs(100 * r):.1f}%、股價還在漲"
        elif r < 0:
            x += f"，明年預估近 3 個月下修 {abs(100 * r):.1f}%，但股價沒有漲"
        else:
            x += f"，但明年預估近 3 個月上修 {100 * r:.1f}%"
    return x


def _top(n: dict, mk: str) -> str:
    e = (n.get("g") or {}).get("est") or {}
    top = [t for t in (e.get("top") or []) if t[2] is not None][:3]
    if not top:
        return ""
    nm = _tw_names() if mk == "tw" else {}
    xs = [f'{t[0]}{" " + nm[t[0]] if nm.get(t[0]) else ""} {_pct(100 * t[2], 0, True)}' for t in top]
    return "修正影響最大：" + "、".join(xs)


_NAMES: dict = {}


def _tw_names() -> dict:
    if not _NAMES:
        try:
            from .company import names
            _NAMES.update(names())
        except Exception:                                 # noqa: BLE001 —— 名稱只是顯示用
            _NAMES["_"] = ""
    return _NAMES


def _g_text(mk: str, n: dict) -> str:
    """未來獲利：分析師預估（等級用）＋過去驗證用的替代資料（並列當對照）。"""
    g = n.get("g") or {}
    out = []
    e = g.get("est")
    if e:
        cov = "" if e.get("cov") is None else f'、涵蓋 {100 * e["cov"]:.0f}% 市值'
        hd = f'分析師預估（{_e(EST_NAMES.get(mk, ""))} {e.get("n") or 0} 家{cov}，{int(e["d"][5:7])}/{int(e["d"][8:10])}）'
        if e.get("g0") is None or e.get("g1") is None:
            out.append(f'<span class="rat">{hd}：算不出成長率</span>')
        else:
            x = (f'{hd}：今年 {_pct(100 * e["g0"], 1, True)}、明年 {_pct(100 * e["g1"], 1, True)}'
                 f' → {"成長減速" if e.get("G1") else "成長沒有減速"}')
            if e.get("rev") is not None:
                px = "" if e.get("px3") is None else f'，股價近 3 個月 {_pct(e["px3"], 1, True)}'
                x += (f'；明年預估近 3 個月{"上修" if e["rev"] >= 0 else "下修"} {abs(100 * e["rev"]):.1f}%{px}'
                      f' → {"預估下修、股價還在漲" if e.get("G2") else "沒有「下修而股價漲」"}')
            t = _top(n, mk)
            if t:
                x += f'<span class="dec">{_e(t)}</span>'
            out.append(f'<span class="rat">{x}</span>')
    p = g.get("proxy")
    if p:
        nm = BS.PROXY_NAMES.get(p["src"], p["src"])
        if p["src"] == "spf":
            body = (f'今年 {_pct(None if p.get("g0") is None else 100 * p["g0"], 1, True)}、'
                    f'明年 {_pct(None if p.get("g1") is None else 100 * p["g1"], 1, True)}、'
                    f'明年預估比上一季調查 {_pct(None if p.get("rev") is None else 100 * p["rev"], 1, True)}')
            per = p["per"].replace("-Q", " 年第 ") + " 季調查"
        else:
            body = f'近 {4 if p["src"] == "tech" else 12} {"季" if p["src"] == "tech" else "個月"}年增率 {_pct(None if p.get("g") is None else 100 * p["g"], 1, True)}'
            per = _ymd(p["per"])
        lab = "過去驗證用" if e else "替代資料（等級用，分析師預估還沒有）"
        yn = lambda v: "不判定" if v is None else ("成立" if v else "沒有")  # noqa: E731
        x = (f'{lab}：{_e(nm)}（{_e(per)}）：{body} → 成長減速：{yn(p.get("G1"))}；'
             f'{"預估下修" if p["src"] == "spf" else "實際下滑"}而股價漲：{yn(p.get("G2"))}')
        out.append(f'<span class="rat">{x}</span>')
    return "".join(out) if out else "沒有預估資料"


def _dec_short(n: dict) -> str:
    """一句話裡的兩年拆解：第一條算得出來的比值。"""
    for k, e in (n.get("e") or {}).items():
        d = e.get("dec")
        if d:
            a, b = DEC_NAMES[k]
            return f'兩年{a} {_pct(d["p"], 0, True)}、{b} {_pct(d["f"], 0, True)}'
    return ""


def _e_text(n: dict) -> str:
    """每條比值一段：讀數、PSY、兩年拆解。"""
    out = []
    for k, e in (n.get("e") or {}).items():
        nm = BS.FUND_NAMES4[k]
        if k in ("pe", "pe_tw"):
            nm += f' {e["r"]:.1f} 倍'
        ym = _e(_ymd(e["ym"]))
        run = f'{ym} 為止連續 {e["run"]} 個月超過' if e["run"] else f"{ym} 沒有超過"
        tip = f'長期漲勢（每月變化的平均 ÷ 標準差）{e["g"]:.3f}'
        x = (f'{_e(nm)}：BSADF {e["s"]:.2f}，95% 臨界值 {e["q95"]:.2f}'
             f'<span class="hint" title="{_e(tip)}">（已依長期漲勢調整）</span>；{run}')
        d = e.get("dec")
        if d:
            a, b = DEC_NAMES[k]
            x += (f'<span class="dec">兩年（{_e(_ymd(d["a"]))}→{ym}）：{_e(a)} {_pct(d["p"], 0, True)}、'
                  f'{_e(b)} {_pct(d["f"], 0, True)} → 比值 {_pct(d["r"], 1 if abs(d["r"]) < 1 else 0, True)}</span>')
        out.append(f'<span class="rat">{x}</span>')
    return "".join(out) if out else "沒有基本面資料"


def _p1_text(n: dict) -> str:
    p = n.get("p1")
    if not p:
        return "歷史還不夠（要 60 個月）"
    ym = _e(_ymd(p["ym"]))
    run = f'{ym} 為止連續 {p["run"]} 個月超過' if p["run"] else f"{ym} 沒有超過"
    tip = f'長期漲勢（每月變化的平均 ÷ 標準差）{p["g"]:.3f}'
    return (f'BSADF {p["s"]:.2f}，95% 臨界值 {p["q95"]:.2f}'
            f'<span class="hint" title="{_e(tip)}">（已依長期漲勢調整）</span>；{run}')


def _p2_text(n: dict) -> str:
    p = n.get("p2") or {}
    if p.get("ru") is None:
        return "還不到兩年的資料"
    return f'兩年漲 {_pct(p["ru"], 1, True)}，離歷史最高收盤 {_pct(p["dist"], 1, True)}'


def _p3_text(n: dict) -> str:
    p = n.get("p3") or {}
    if p.get("z") is None:
        return "歷史還不夠（要 20 年）"
    return f'{p["z"]:.2f} 個標準差（{_e(_ymd(p["ym"]))}）'


def _v_text(mk: str, n: dict, ref: dict) -> str:
    it = n.get("v") or {}
    if not it:
        x = f'不判定：{NO_VAL.get(mk, "沒有資料")}'
        if mk == "tw" and ref.get("pe"):
            x += f'（現在本益比 {ref["pe"]["v"]:.1f} 倍）'
        return x
    parts = []
    for k in BS.VAL_ITEMS:
        if k in it:
            v = it[k]
            r = v.get("raw")
            if r is None:
                raw = VAL_NAMES[k]
            elif k == "X6":
                raw = f"{VAL_NAMES[k]} {r:.1f}"
            else:
                raw = f'{_sp(VAL_NAMES[k])}比長期趨勢{"高" if r >= 0 else "低"} {abs(r):.0f}%'
            parts.append(f'{_e(raw)}，第 {v["pct"]:.0f} 百分位')
    return "；".join(parts) + "（和有資料以來比）"


def _f_text(mk: str, n: dict) -> str:
    f = n.get("f") or {}
    if not f:
        return "沒有資料"
    raw = f.get("raw")
    nm = "融資 ÷ 市值" if mk == "tw" else "家計部門證券融資年增率"
    rv = "—" if raw is None else (f"{raw:.2f}%" if mk == "tw" else _pct(raw, 1, True))
    if f.get("pct") is None:
        return f"{nm} {rv}（歷史未滿 {BS.FUEL_MIN_MONTHS['tw' if mk == 'tw' else 'us'] // 12} 年，不判定）"
    return f'{nm} {rv}，第 {f["pct"]:.0f} 百分位（{_e(_ymd(f["ym"]))}）'


# ── 區塊 ───────────────────────────────────────────────────────────────────

def tiles(V: dict, pre: str = "") -> str:
    out = []
    for mk in BS.MARKETS:
        m = V["M"].get(mk)
        if not m:
            continue
        n = m["now"]
        chips = "".join(f'<i class="{"on" if n.get(c) else ("na" if n.get(c) is None else "")}">{SHORT[c]}</i>' for c in COND_ORDER)
        key = []
        if (n.get("p2") or {}).get("ru") is not None:
            key.append(f'兩年 {_pct(n["p2"]["ru"], 0, True)}')
        if n.get("p1"):
            key.append(f'PSY 連 {n["p1"]["run"]} 個月超過臨界值' if n["p1"]["run"] else "PSY 沒超過臨界值")
        if (n.get("p3") or {}).get("z") is not None:
            key.append(f'偏離趨勢 {n["p3"]["z"]:.1f}σ')
        out.append(f'<a class="bt bt{n["L"]}" href="#{pre}{mk}"><span class="btn">{_e(m["name"])}<i>{_e(m["index"])}</i></span>'
                   f'<span class="btv"><b class="btl">{n["L"]}</b><span class="btt">{_e(BS.LEVELS[n["L"]])}</span></span>'
                   f'<span class="bcs">{chips}</span><span class="btk">{_e("・".join(key))}</span></a>')
    return (f'<section class="sec" id="{pre}lv"><h2>五個市場的泡沫等級<span class="sub">0 沒有跡象・1 偏貴・2 漲勢過熱・3 泡沫警戒・4 嚴重泡沫</span></h2>'
            f'<div class="btg">{"".join(out)}</div>'
            '<p class="note">價格過熱，而且「漲得比基本面快」「估值在歷史前 5%」「未來獲利跟不上」至少一個成立，才到「泡沫警戒」；'
            '只有價格過熱最多到「漲勢過熱」。紅色＝成立，虛線＝這個市場沒有資料判定。</p></section>')


def _now_table(mk: str, m: dict) -> str:
    n, ref = m["now"], m.get("ref") or {}
    rows = [("P1", "價格爆發（PSY）", _p1_text(n), f"超過 95% 臨界值，連續 {BS.PSY_RUN} 個月"),
            ("P2", "兩年翻倍而且在高點", _p2_text(n), f"兩年漲 ≥ {BS.RUN2_PCT:.0f}%，離最高 {100 * BS.RUN2_ATH:.0f}% 以內"),
            ("P3", "偏離長期趨勢", _p3_text(n), f"≥ {BS.TREND_Z:.0f} 個標準差"),
            ("E", "價格漲得比基本面快", _e_text(n), f"比值超過 95% 臨界值，連續 {BS.E_RUN} 個月"),
            ("V", "估值", _v_text(mk, n, ref), f"至少 {BS.VAL_NEED} 項 ≥ 第 {BS.VAL_PCT:.0f} 百分位"),
            ("G", "未來獲利跟不上", _g_text(mk, n), "明年預估成長低於今年，而且明年預估比 3 個月前低、股價比 3 個月前高"),
            ("F", "槓桿", _f_text(mk, n), f"≥ 第 {BS.FUEL_PCT:.0f} 百分位")]
    tr = "".join(f'<tr><td class="l" data-h="條件">{_e(nm)}</td><td class="l" data-h="現在">{txt}</td>'
                 f'<td class="l" data-h="門檻">{_e(th)}</td><td data-h="成立">{_mark(n.get(c))}</td></tr>' for c, nm, txt, th in rows)
    return ('<h3>現在的七個條件</h3><div class="tw"><table class="stk bnow"><tr><th class="l">條件</th><th class="l">現在</th>'
            f'<th class="l">門檻</th><th>成立</th></tr>{tr}</table></div>')


def _ref_line(mk: str, m: dict) -> str:
    r = m.get("ref") or {}
    xs = []
    if r.get("lppls"):
        xs.append(f'LPPLS 泡沫信心 {r["lppls"]["v"]:+.0f}%')
    if r.get("acc"):
        xs.append(f'上漲加速度 {r["acc"]["v"]:+.1f} 個百分點')
    if r.get("tsmc"):
        xs.append(f'台積電占市值 {r["tsmc"]["v"]:.1f}%')
    if r.get("ecy"):
        xs.append(f'超額 CAPE 殖利率 {r["ecy"]["v"]:.2f} 個百分點')
    if r.get("rsp"):
        xs.append(f'等權 ÷ 市值加權一年變化 {r["rsp"]["v"]:+.1f}%')
    cy = []
    hi = False
    for k, e in (((m.get("now") or {}).get("e")) or {}).items():
        c = e.get("cyc") or {}
        if c.get("z") is not None:
            cy.append(f'{CYC_NAMES[k]}比長期趨勢高 {c["z"]:.1f} 個標準差（{_ymd(c["per"])}）')
            hi = hi or c["z"] >= CYC_HI
    out = f'<p class="note">參考讀數（不進等級）：{_e("；".join(xs))}。</p>' if xs else ""
    if cy:
        out += (f'<p class="note{" cyc" if hi else ""}">景氣高峰參考（不進等級）：{_e("；".join(cy))}。'
                '循環性的基本面在高峰時，比值會看起來偏低。</p>')
    return out


def _epi_table(m: dict, ext: dict | None = None) -> str:
    rows = list(m.get("epi") or [])
    tr = []

    def row(e, monthly=False):
        per = f'{_ymd(e["a"])}～{_ymd(e["z"])}（{e["n"]} 個月）' + ("・月平均" if monthly else "")
        cond = "、".join(SHORT[c] for c in e["cond"])
        pk = f'{_ymd(e["peak"]["d"])}：{_num(e["peak"]["px"], 0)}'
        if e["open"]:
            dd = f'還沒滿兩年，到現在最多跌 {abs(e["dd"]):.0f}%' if e["dd"] < -0.5 else "還沒滿兩年，還沒明顯回落"
        else:
            dd = f'{abs(e["dd"]):.0f}%（{_ymd(e["low"]["d"])} 低點）'
        return (f'<tr><td class="l" data-h="期間">{_e(per)}</td><td data-h="最高等級">{e["max"]}</td>'
                f'<td class="l" data-h="條件">{_e(cond)}</td><td data-h="段內高點">{_e(pk)}</td><td class="l" data-h="之後兩年最大跌幅">{_e(dd)}</td></tr>')
    if ext:
        first = rows[0]["a"] if rows else "9999-99"
        for e in ext.get("epi") or []:
            if e["z"] < first:
                tr.append(row(e, True))
    tr += [row(e) for e in rows]
    if not tr:
        return '<h3>等級 ≥ 3 的泡沫段</h3><p class="note">有資料以來沒有出現過。</p>'
    return ('<h3>等級 ≥ 3 的泡沫段</h3><div class="tw"><table class="stk bepi"><tr><th class="l">期間</th><th>最高等級</th>'
            f'<th class="l">條件</th><th>段內高點</th><th class="l">之後兩年最大跌幅</th></tr>{"".join(tr)}</table></div>'
            '<p class="note">段＝等級 ≥ 3 的月份，中間隔 6 個月以上才算新的一段，括號是段內等級 ≥ 3 的月數；跌幅＝段內最高收盤到之後兩年（504 個交易日）內最低收盤。</p>')


def _cell(e: dict | None) -> str:
    if not e or not e.get("n"):
        return '<td data-h="—">—</td>'
    ph = "—" if e.get("p_hot") is None else f'{100 * e["p_hot"]:.0f}%'
    pa = "—" if e.get("p_all") is None else f'{100 * e["p_all"]:.0f}%'
    return f'{ph} ／ {pa}<em>{_e(VERDICT.get(e.get("verdict"), "—"))}</em>'


def _valid_table(R: dict, tests=VALID_TESTS) -> str:
    if not R:
        return '<p class="warn">驗證結果還沒產生。</p>'
    tr = []
    for t in tests:
        if t not in R:
            continue
        r = R.get(t) or {}
        e1, e2 = r.get("252") or {}, r.get("504") or {}
        if not e1.get("n_hot"):
            tr.append(f'<tr><td class="l" data-h="條件">{_e(TEST_NAMES[t])}</td><td data-h="成立的月份">0</td>'
                      '<td data-h="一年內跌 20%">—</td><td data-h="兩年內跌 40%">—</td><td data-h="之後一年平均">—</td></tr>')
            continue
        ret = f'{_pct(e1.get("ret_hot"), 0, True)} ／ {_pct(e1.get("ret_all"), 0, True)}'
        tr.append(f'<tr><td class="l" data-h="條件">{_e(TEST_NAMES[t])}</td>'
                  f'<td data-h="成立的月份">{e1["n_hot"]}（{e1["n_epi"]} 段，{r.get("share", 0):.0f}%）</td>'
                  f'<td data-h="一年內跌 20%">{_cell(e1)}</td><td data-h="兩年內跌 40%">{_cell(e2)}</td>'
                  f'<td data-h="之後一年平均">{_e(ret)}</td></tr>')
    return ('<div class="tw"><table class="stk bval"><tr><th class="l">條件</th><th>成立的月份（段數，占比）</th>'
            '<th>一年內跌 20%：成立 ／ 全部</th><th>兩年內跌 40%：成立 ／ 全部</th><th>之後一年平均報酬：成立 ／ 全部</th></tr>'
            f'{"".join(tr)}</table></div>')


def _valid_head(R: dict) -> str:
    """驗證收起來時的一句話：等級 ≥ 3 之後一年內跌 20% 的比例（成立 ／ 全部）與判定。"""
    e = (R.get("L3") or {}).get("252") or {}
    if not e.get("n_hot"):
        never = "share" not in (R.get("L3") or {})
        return ("沒有出現過等級 ≥ 3" if never else "等級 ≥ 3 還沒有走完一年的歷史樣本") + _pfpn(R)
    s = (f'等級 ≥ 3 之後一年內跌 20%：{100 * e["p_hot"]:.0f}%，全部月份 {100 * e["p_all"]:.0f}%'
         f'（{e["n_hot"]} 個月、{e["n_epi"]} 段，{VERDICT.get(e.get("verdict"), "—")}）')
    return s + _pfpn(R)


def _pgpn(R: dict) -> str:
    """價格過熱時：未來獲利跟不上（PG）vs 還跟得上（PnG），之後一年內跌 20% 的比例。"""
    a, b = (R.get("PG") or {}).get("252") or {}, (R.get("PnG") or {}).get("252") or {}
    if not a.get("n_hot") and not b.get("n_hot"):
        return ""

    def f(e):
        return "—" if not e.get("n_hot") else f'{100 * e["p_hot"]:.0f}%（{e["n_hot"]} 個月）'
    return f"；未來獲利跟不上 {f(a)}、還跟得上 {f(b)}"


def _pfpn(R: dict) -> str:
    """價格過熱時：漲得比基本面快（PF）vs 基本面有跟上（PN），之後一年內跌 20% 的比例。"""
    a, b = (R.get("PF") or {}).get("252") or {}, (R.get("PN") or {}).get("252") or {}
    if not a.get("n_hot") and not b.get("n_hot"):
        return ""

    def f(e):
        return "—" if not e.get("n_hot") else f'{100 * e["p_hot"]:.0f}%（{e["n_hot"]} 個月）'
    return f"；價格過熱時，漲得比基本面快 {f(a)}、基本面有跟上 {f(b)}" + _pgpn(R)



def _valid(mk: str, R: dict) -> str:
    rr = (R or {}).get(mk) or {}
    main = rr.get("main") or {}
    if not main:
        return '<h3>驗證：成立之後比較容易大跌嗎？</h3><p class="warn">驗證結果還沒產生（scripts/run_bub.py）。</p>'
    ext = rr.get("ext") or {}
    head = _valid_head(main) + (f'；延伸樣本（含 1987–1990）：{_valid_head(ext)}' if ext else "")
    out = [f'<details class="bvd"><summary><b>驗證：成立之後比較容易大跌嗎？</b><span class="bvh">{_e(head)}</span></summary>',
           f'<p class="note">樣本 {_e(_ymd(main["a"]))}～{_e(_ymd(main["z"]))}，每月一個樣本，共 {main["n"]:,} 個月。</p>',
           _valid_table(main, VALID_SPX if mk == "spx" else VALID_TESTS)]
    rb = rr.get("robust") or {}
    if rb.get("L3"):
        e1, e2 = (rb["L3"].get("252") or {}), (rb["L3"].get("504") or {})
        if e1.get("n_hot"):
            out.append(f'<p class="note">1950 年起另算一次（穩健度）：等級 ≥ 3 之後一年內跌 20% {_cell(e1).replace("<em>", "（").replace("</em>", "）")}；'
                       f'兩年內跌 40% {_cell(e2).replace("<em>", "（").replace("</em>", "）")}。</p>')
    if ext:
        out.append(f'<h4>延伸樣本：國發會月平均 {_e(_ymd(ext["a"]))}～{_e(_ymd(ext["z"]))}（含 1987–1990）</h4>'
                   + _valid_table(ext, EXT_TESTS)
                   + '<p class="note">只當穩健度：訊號用當月讀數，跌幅用之後 12、24 個月的月平均；兩年翻倍改用 24 個月月平均漲幅；'
                     '比值只有加權指數 ÷ 出口（本益比 2013 年起）；未來獲利用外銷訂單。</p>')
    gp = BS.PROXY_NAMES.get(BS.PROXY.get(mk, ""), "")
    out.append('<p class="note">「價格過熱，而且漲得比基本面快」和「價格過熱，但基本面有跟上」兩列的差別，就是基本面有沒有跟上；'
               '「未來獲利跟不上」幾列的過去用' + _e(gp) + '算'
               + ('（專業預測者的預估，1981 年起）' if mk == "spx" else '（實際值，不是預估）') + '。'
               '判定：成立月份 ≥ 12 個月、≥ 4 段，差的 95% 區間（12 個月一塊重抽）不含 0、而且前後兩半同方向，'
               '才寫「較容易大跌」或「反而較少大跌」。平均報酬只描述，不判定。</p></details>')
    return "".join(out)


def sig_line(mk: str, n: dict) -> str:
    """市場卡的實務判定一行（docs/lab_signal_plan.md 第 6.2 節）：現在的等級（≥ 3 看「3 以上」，其餘看「2 以上」）過去之後
    12 個月內最大回撤 20% 以上的比例／平常（sigspec VER 3），判定同訊號總覽；研究檔沒有就不顯示。"""
    try:
        from . import sigcat as G
        from . import sigspec as SS
        rows = {r["id"]: r for r in G.research_rows()}
    except Exception:                                         # noqa: BLE001 —— 訊號總覽的問題不擋泡沫頁
        return ""
    lv = 3 if n["L"] >= 3 else 2
    r = rows.get(f"{mk}:bub:L{lv}")
    st = (r or {}).get("warn")
    if not st:
        return ""
    pc = lambda x: "—" if x is None else f"{100 * x:.0f}%"
    body = (f'過去 {st["n"]} 段，之後 12 個月內最大回撤 20% 以上 <b>{pc(st["hit"])}</b>（平常 {pc(st["base"])}）' if st["n"]
            else "過去沒有出現過")
    if st["n"] and st.get("mdd") is not None and st.get("mdd_base") is not None:
        body += f'，回撤中位數 {pc(st["mdd"])}（平常 {pc(st["mdd_base"])}）'
    now = "" if n["L"] >= lv else f'（現在等級 {n["L"]}）'
    return (f'<p class="bsig">泡沫等級 {lv} 以上的時候{now}：{body}・<b>{SS.TIER_MARK[st["tier"]]} {_e(SS.TIER_NAMES[st["tier"]])}</b>'
            f'<a href="#s={_e(r["id"])}">全部指標 →</a></p>')


def market_card(mk: str, m: dict, R: dict, pre: str = "") -> str:
    n = m["now"]
    ext = ((R or {}).get("tw") or {}).get("ext") if mk == "tw" else None
    rg = "".join(f'<button type="button" class="tb{" on" if y == 0 else ""}" data-br="{y}" data-mk="{mk}" '
                 f'aria-pressed="{"true" if y == 0 else "false"}">{"全部" if y == 0 else f"近 {y} 年"}</button>' for y in (0, 30, 10))
    return (f'<section class="sec cd bm" id="{pre}{mk}"><div class="ch"><h2>{_e(m["name"])}<span class="sub">{_e(m["index"])}</span></h2>'
            f'<div class="sv"><b class="sc bl{n["L"]}">{n["L"]}</b><span class="bn bl{n["L"]}">{_e(BS.LEVELS[n["L"]])}</span></div></div>'
            f'<p class="bsum">{_e(summary(mk, m))}</p>{sig_line(mk, n)}'
            f'<div class="seg brg" role="group" aria-label="期間">{rg}</div>'
            f'<div class="bhw"><div class="bh" id="h-{mk}"><p class="note">歷史等級載入中…</p></div><div class="tip" id="t-{mk}" hidden></div></div>'
            + _legend(bool(ext and (ext.get("hist") or {}).get("d"))) + _now_table(mk, m) + _ref_line(mk, m) + _epi_table(m, ext) + _valid(mk, R) + '</section>')


def _legend(ext: bool) -> str:
    """等級色塊圖例；台股另列延伸樣本（1990 年以前：國發會月平均，等級色塊斜線、指數虛線）。"""
    xs = "".join(f'<span><i class="lvk{lv}"></i>{lv} {_e(nm)}</span>' for lv, nm in BS.LEVELS.items())
    if ext:
        xs += '<span><i class="lvx"></i>1990 年以前：國發會月平均（指數為虛線）</span>'
    return f'<div class="blg">{xs}</div>'

TYPES = (
    ("P1", "價格爆發（PSY 檢定，Phillips、Shi、Yu 2015）",
     "看價格是不是在「越漲越快」：用統計檢定判斷漲勢有沒有超過一般隨機波動能解釋的範圍。臨界值依各指數本來的長期漲勢模擬"
     "（美股長期漲得快，沒考慮的話很容易誤報）。急跌也可能超過臨界值，所以另外要求近 12 個月實質價格是上漲的。"
     "它只說明漲勢不正常，不告訴你什麼時候結束。"),
    ("P2", "兩年翻倍而且在高點（Greenwood、Shleifer、You 2019）",
     "美國與國際的產業資料：兩年漲一倍以上之後，兩年內跌 40% 的機率明顯變高，但之後的平均報酬不一定變差。"
     "大跌之後的反彈（還沒回到前高）不算，所以要求收盤離歷史最高 5% 以內。"),
    ("P3", "偏離長期趨勢 2 個標準差（GMO）",
     "實質股價離長期趨勢線多遠；GMO 把 2 個標準差定為泡沫門檻。長期趨勢本身也會改變，所以只當其中一個條件。"),
    ("E", "價格漲得比基本面快（價格 ÷ 基本面的比值爆發）",
     "把指數除以它的基本面，看這個比值是不是也在爆發（同一套 PSY）：S&P 500 用盈餘，台股用盈餘與出口，費半用全球半導體銷售額，"
     "那斯達克兩檔用美國科技業獲利（BEA；2001 年以前用舊產業分類的一般機械、電子電機、通訊接上，是近似）。"
     "提出 PSY 的論文檢定的就是 S&P 500 的股價 ÷ 股利。比值在盈餘崩落時也會爆發，所以另外要求近 12 個月價格上漲、"
     "而且比值上升。基本面本身在景氣高峰時（半導體、出口），比值會看起來偏低，所以另列「景氣高峰參考」。"),
    ("V", "估值歷史前 5%（只有 S&P 500）",
     "CAPE、巴菲特指標、Tobin's Q 和全部歷史比。估值高可以維持很多年，主要影響的是之後 10 年的報酬，不是短期會不會崩，"
     "所以只有估值高只算「偏貴」。台股本益比只有 2013 年起、其他三個美股指數沒有自己的長歷史估值，不判定。"),
    ("G", "未來獲利跟不上",
     "股價反應的是未來獲利。明年的預估成長比今年低（成長減速），而且明年的預估比 3 個月前低、股價卻比 3 個月前高"
     "（估值靠股價撐上去），兩個都成立才算。現在用分析師預估：台股是 Yahoo 有預估的上市櫃公司，美股是各指數的成分股，"
     "依股數加總成整個市場的今年、明年獲利。過去沒有免費的指數預估歷史，驗證用替代資料：S&P 500 用費城聯準銀行的專業預測者調查"
     "（美國企業獲利預測，1981 年起，真的預估）；那斯達克用美國科技業實際獲利、費半用全球半導體銷售額、台股用外銷訂單"
     "（這三個是實際值：年增率比半年前低＝成長減速，近 12 個月合計比 3 個月前低＝下滑）。實際值下滑比預估下修少見，"
     "所以現在的條件比過去的驗證容易成立。"),
    ("F", "槓桿歷史前 10%",
     "推升漲勢的錢是不是借來的。美股＝家計部門證券融資年增率（四個指數共用）；台股＝融資 ÷ 市值（融資金額會跟著市值長大，"
     "要看比例；2013 年起，滿 10 年才判定）。"),
)


def types_sec(V: dict, pre: str = "") -> str:
    out = []
    for c, nm, txt in TYPES:
        on = [V["M"][mk]["name"] for mk in BS.MARKETS if mk in V["M"] and V["M"][mk]["now"].get(c)]
        st = f'現在成立：{"、".join(on)}' if on else "現在沒有市場成立"
        out.append(f'<div class="bty"><h3>{_e(nm)}</h3><p>{_e(txt)}</p><p class="note">{_e(st)}</p></div>')
    return (f'<section class="sec" id="{pre}types"><h2>七種條件代表什麼</h2>' + "".join(out)
            + '<p class="note">參考讀數（LPPLS、上漲加速度、集中度、本益比、超額 CAPE 殖利率）只列數字，不進等級：'
              '我們的 LPPLS 是網格近似，歷史上很少亮燈；其他項目沒有公認的泡沫門檻。</p></section>')


METHOD = (
    '<section class="sec" id="mth"><details class="cd"><summary><b>方法與資料</b></summary>'
    '<p>等級（VER 4）：價格過熱＝價格爆發、兩年翻倍、偏離長期趨勢任一成立。0＝價格沒過熱、估值也沒在歷史前 5%；'
    '1＝只有估值在歷史前 5%；2＝價格過熱，但「漲得比基本面快」「估值」「未來獲利跟不上」都沒成立（或無法判定）；'
    '3＝價格過熱，而且這三個至少一個成立；4＝價格過熱，而且這三個加上「槓桿」至少兩個成立。'
    '資料不夠長、算不出來的條件當作不成立。VER 3（沒有未來獲利）、VER 1（只看價格）的等級留在驗證表當對照。</p>'
    '<p>方向條件（VER 3 起）：價格爆發要近 12 個月實質價格上漲；漲得比基本面快要近 12 個月價格上漲、而且比值上升。</p>'
    '<p>價格 ÷ 基本面：每個月的月平均價格 ÷ 那個月月底拿得到的最新基本面（S&P 500 盈餘晚 6 個月、出口晚 2 個月、'
    '全球半導體銷售額晚 2 個月、美國科技業獲利季底後 3 個月），基本面停更超過 12 個月就不算。</p>'
    '<p>未來獲利：分析師預估每天加總（每家公司的今年、明年預估與 90 天前的明年預估乘股數；外幣預估換成美元；'
    '加總用到的公司要占市值 50% 以上、資料在 7 天內）。有預估的月份用預估，之前用替代資料；'
    '專業預測者調查第 q 季在第 3q−1 個月月底才算拿得到。</p>'
    '<p>價格爆發：實質股價（月平均 ÷ 前一個月 CPI）取對數，算 BSADF（視窗至少 60 個月）。臨界值用「有長期漲勢的隨機漫步」模擬，'
    '漲勢＝到當月為止每月變化的平均 ÷ 標準差，8 檔各 2,000 次、相鄰兩檔內插。CPI 缺月（2025-10 美國政府停擺）用前後兩個月的幾何平均補上。</p>'
    '<p>每個條件只用當時拿得到的資料：月資料下個月 1 日起才用，家計證券融資季資料晚 3 個月半。驗證用每個月最後一個交易日，'
    '看之後一年內跌 20%、兩年內跌 40%（期間內收盤高點到之後低點）的比例，和所有月份比。</p>'
    '<p>資料：加權指數（證交所、國發會月平均）、S&P 500（Yahoo、Shiller）、那斯達克、那斯達克 100、費半（Yahoo）、'
    'CPI（主計總處、勞工統計局、Shiller）、Z.1 家計證券融資與股票市值（聯準會）、GDP 與產業別企業獲利（BEA，經 DBnomics）、'
    '專業預測者調查（費城聯準銀行）、全球半導體銷售額（WSTS）、外銷訂單（經濟部）、分析師預估（Yahoo；成分股來自維基百科、那斯達克）、'
    '融資金額（FinMind 轉載證交所）、上市櫃市值（自算）。</p>'
    '<p class="note">門檻都取自文獻，不用結果去調；規格寫在 arm/lab/bubspec.py（VER 4），改規格要升版本。只描述位置，不是買賣訊號。</p>'
    '</details></section>')


def page_json(V: dict, extra: dict | None = None) -> str:
    out = dict(extra or {})
    for mk, m in V["M"].items():
        h = dict(m["hist"])
        if mk == "tw":
            ext = (((V.get("R") or {}).get("tw") or {}).get("ext") or {}).get("hist") or {}
            first = h["d"][0] if h["d"] else "9999-99"
            nd = len(ext.get("d") or [])
            xc, xp = ext.get("c") or [""] * nd, ext.get("p") or [None] * nd
            pre = [(d, lv, c, px) for d, lv, c, px in zip(ext.get("d") or [], ext.get("L") or [], xc, xp) if d < first]
            if pre:
                h["xd"] = [x[0] for x in pre]
                h["xL"] = [x[1] for x in pre]
                h["xc"] = [x[2] for x in pre]
                h["xp"] = [x[3] for x in pre]
        out[mk] = h
    return json.dumps(out, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def render(V: dict | None = None) -> str:
    """x9b.html：轉址頁（見 REDIRECT；docs/lab_ia_v5_plan.md 第 9.2 節）。"""
    return REDIRECT


def build(out: Path = OUT) -> bool:
    """泡沫頁改成轉址頁：等級與產業在市場頁最下面（block_html），驗證與方法在研究紀錄頁（research_body）。"""
    text = render()
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True


# 舊網址：#tw、#spx…→ 那個市場頁的泡沫那一塊；#lv、#ind、#indv、#types、#mth → 研究紀錄頁的同一段；沒有＝台股市場頁。
REDIRECT = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="robots" content="noindex,nofollow"><link rel="icon" href="data:,">
<title>泡沫</title>
<script>(function(){var h=(location.hash||"").replace(/^#/,""),MK={tw:1,spx:1,ixic:1,ndx:1,sox:1},RS={lv:1,ind:1,indv:1,types:1,mth:1},u;
if(RS[h])u="x9r.html#bub-"+h;else{var k=MK[h]?h:"tw";u=k==="tw"?"x9m.html#at=bub":"x9mu.html#ix="+k+"&at=bub";}
location.replace(u);})();</script>
<noscript><meta http-equiv="refresh" content="0;url=x9m.html#at=bub"></noscript></head>
<body><p><a href="x9m.html#at=bub">泡沫等級在市場頁最下面 →</a></p></body></html>
"""


# ── 研究紀錄頁的泡沫（原本泡沫頁的全部內容；段落 id 加 bub- 前綴，免得和訊號研究撞名）──────────────────────

RES_PRE = "bub-"


def research_body(V: dict) -> str:
    """五個市場的等級、每個市場一張卡（一句話、歷史等級、七個條件、泡沫段、驗證）、產業（含驗證）、七種條件代表什麼、方法與資料。"""
    if not V["M"]:
        return '<p class="warn">泡沫等級還算不出來（缺 PSY 臨界值表：scripts/run_bub.py --cv）。</p>'
    from . import bubindpage as IP
    I = V.get("I") or {}
    _, ikeys = IP.hist_data(I)
    pre = RES_PRE
    nav = "".join(f'<a href="#{pre}{mk}">{_e(BS.NAMES[mk])}</a>' for mk in BS.MARKETS if mk in V["M"])
    return (tiles(V, pre) + f'<nav class="snav bnav" aria-label="段落">{nav}<a href="#{pre}ind">產業</a>'
            f'<a href="#{pre}types">條件說明</a><a href="#{pre}mth">方法</a></nav>'
            + "".join(market_card(mk, V["M"][mk], V["R"], pre) for mk in BS.MARKETS if mk in V["M"])
            + IP.section(I, V.get("IR") or {}, ikeys, pre) + types_sec(V, pre) + METHOD.replace('id="mth"', f'id="{pre}mth"'))


def research_data(V: dict) -> str:
    """研究紀錄頁的 <script type="application/json" id="bubd">：五個市場（台股含 1990 年以前的延伸樣本）＋產業的歷史等級。"""
    from . import bubindpage as IP
    idata, _ = IP.hist_data(V.get("I") or {})
    return page_json(V, idata) if V["M"] else "{}"


def research_css() -> str:
    from . import bubindpage as IP
    return CSS + IP.CSS


# ── 市場頁最下面的泡沫那一塊（docs/lab_ia_v5_plan.md 第 3 節③、第 13 節其他細項 2、第 15.1 節）────────────────
# 等級、七個條件 ✓／✗、歷史等級圖（預設近 30 年）、等級 ≥ 2 的產業一行、全部產業表（收起）。方法與驗證在研究紀錄頁。

BLOCK_GROUPS = {"tw": (("tw", "台股產業"), ("tg", "細分族群")), "us": (("us", "美股類股"), ("ff", "美股細產業"))}
BLOCK_RANGE = 30                                       # 歷史等級圖預設的期間（年；0＝全部）
BLOCK_TOP = 8                                          # 等級 ≥ 2 的產業一組最多列幾個


def _ind_name(grp: str, k: str) -> str:
    from . import bubindspec as BI
    if grp == "us":
        return BI.US_ETF.get(k, k)
    if grp == "ff":
        return BI.FF_NAMES.get(k, k)
    if grp == "tg":
        return BI.TG_NAMES.get(k, k)
    return k


def _hot_line(grp: str, label: str, I: dict) -> str:
    """一組產業裡等級 ≥ 2 的（等級高的在前）；等級 ≥ 3 的另寫成立的條件。"""
    from . import bubindpage as IP
    G = I.get(grp) or {}
    if not G:
        return ""
    hot = [k for k in IP._order(G) if G[k]["now"]["L"] >= 2]
    sh = IP.SHORT_FF if grp == "ff" else IP.SHORT
    xs = []
    for k in hot[:BLOCK_TOP]:
        n = G[k]["now"]
        cs = "、".join(sh[c] for c in IP.GRP_COND[grp] if n.get(c)) if n["L"] >= 3 else ""
        xs.append(f'<span class="mbn">{_e(_ind_name(grp, k))} <b class="bl{n["L"]}">{n["L"]}</b>'
                  + (f'<em>{_e(cs)}</em>' if cs else "") + '</span>')
    if len(hot) > BLOCK_TOP:
        xs.append(f'<span class="mbn">等 {len(hot)} 個</span>')
    lab = label + (f'（到 {_ymd(I["ff_last"])}）' if grp == "ff" and I.get("ff_last") else "")
    return f'<li><b>{_e(lab)}</b>' + ("".join(xs) if xs else '<span class="mbn">沒有等級 2 以上</span>') + '</li>'


def _ind_tables(side: str, I: dict, keys: dict) -> str:
    from . import bubindpage as IP
    out = []
    if side == "tw":
        if I.get("tw"):
            out.append('<h3>台股產業</h3>' + IP.table("tw", I["tw"], keys.get("tw")))
        if I.get("tg"):
            names = {}
            try:
                from .company import names as _names
                names = _names()
            except Exception:                              # noqa: BLE001 —— 名稱只是顯示用
                pass
            out.append('<h3>細分族群</h3>' + IP.table("tg", I["tg"], keys.get("tg"), I.get("tg_list"), names))
    else:
        if I.get("us"):
            out.append('<h3>美股類股</h3>' + IP.table("us", I["us"], keys.get("us")))
        if I.get("ff"):
            out.append('<h3>美股細產業</h3>' + IP.table("ff", I["ff"], None))
    return "".join(out)


def block_html(mk: str) -> str:
    """市場頁的泡沫那一塊（mk＝tw／spx／ixic／ndx／sox）；這個程序裡景氣頁算過的等級（bubble.last）沒有就不顯示。"""
    m = BU.last(mk)
    if not m:
        return ""
    n = m["now"]
    lv = n["L"]
    side = "tw" if mk == "tw" else "us"

    def chip(c):
        v = n.get(c)
        cls, mark = ("on", "✓") if v else (("na", "—") if v is None else ("", "✗"))
        return f'<i class="{cls}">{_e(SHORT[c])} {mark}</i>'
    rg = "".join(f'<button type="button" class="tb{" on" if y == BLOCK_RANGE else ""}" data-br="{y}" data-mk="{mk}" '
                 f'aria-pressed="{"true" if y == BLOCK_RANGE else "false"}">{"全部" if y == 0 else f"近 {y} 年"}</button>' for y in (0, 30, 10))
    from . import bubindpage as IP
    I = industries()
    _, keys = IP.hist_data(I)
    lines = "".join(_hot_line(g, lab, I) for g, lab in BLOCK_GROUPS[side])
    tbl = _ind_tables(side, I, keys)
    ind = (f'<ul class="mbi">{lines}</ul>' if lines else "") + (f'<details class="mfx mbt"><summary>全部產業</summary>{tbl}</details>' if tbl else "")
    return (f'<section class="cd mbub" id="bub"><div class="ch"><h2>泡沫</h2>'
            f'<div class="sv"><b class="sc bl{lv}">{lv}</b><span class="bn bl{lv}">{_e(BS.LEVELS[lv])}</span></div></div>'
            f'<div class="bcs mbc">{"".join(chip(c) for c in COND_ORDER)}</div>'
            f'<div class="seg brg" role="group" aria-label="期間">{rg}</div>'
            f'<div class="bhw"><div class="bh" id="h-{mk}"><p class="note">歷史等級載入中…</p></div><div class="tip" id="t-{mk}" hidden></div></div>'
            + _legend(False) + ind + '</section>')


def block_data(mks) -> str:
    """市場頁的 <script type="application/json" id="bubd">：這幾個市場的歷史等級（不含延伸樣本）＋同一邊產業的歷史等級。"""
    from . import bubindpage as IP
    M = {mk: BU.last(mk) for mk in mks if BU.last(mk)}
    data, _ = IP.hist_data(industries())
    pre = ("@t", "@g") if "tw" in mks else ("@u",)
    return page_json({"M": M, "R": {}}, {k: v for k, v in data.items() if k.startswith(pre)})



# 歷史等級圖、條件小章、等級色塊與圖例（泡沫頁、市場頁的泡沫那一塊共用；docs/lab_ia_v5_plan.md 第 3 節③）
CHART_CSS = """
:root{--lv0:#e4e8ef;--lv1:#b9c4d4;--lv2:#f1c25a;--lv3:#ea8a3a;--lv4:#d33a34}
@media (prefers-color-scheme:dark){:root{--lv0:#243047;--lv1:#4a5a76;--lv2:#b98f2e;--lv3:#d9782f;--lv4:#f15b50}}
.bcs{display:flex;flex-wrap:wrap;gap:4px}.bcs i{font-style:normal;font-size:11.5px;padding:0 7px;border-radius:999px;border:1px solid var(--line2);color:var(--mut)}
.bcs i.on{background:var(--sbg);border-color:var(--c4);color:var(--t4);font-weight:600}.bcs i.na{border-style:dashed}
.brg{margin:0 0 6px}
.bhw{position:relative}.bh{position:relative;min-height:120px}.bh svg{touch-action:pan-y}
.bh .gd{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}.bh .px{fill:none;stroke:var(--ink);stroke-width:1.5}
.bh .pxx{fill:none;stroke:var(--ink2);stroke-width:1.4;stroke-dasharray:4 3}.hint{border-bottom:1px dotted var(--line2);cursor:help}
.bh .ax{font-size:11px;fill:var(--mut)}.bh .gl{stroke:var(--line);stroke-width:1}
.lv0{fill:var(--lv0)}.lv1{fill:var(--lv1)}.lv2{fill:var(--lv2)}.lv3{fill:var(--lv3)}.lv4{fill:var(--lv4)}.lvx{opacity:.55}
.blg{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--mut);margin:4px 0 10px}
.blg i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.lvk0{background:var(--lv0)}.lvk1{background:var(--lv1)}.lvk2{background:var(--lv2)}.lvk3{background:var(--lv3)}.lvk4{background:var(--lv4)}
.blg i.lvx{background:repeating-linear-gradient(45deg,var(--lv3),var(--lv3) 2px,var(--panel) 2px,var(--panel) 4px);opacity:1}
.bl0,.bl1{color:var(--ink2)}.bl2{color:var(--t3)}.bl3,.bl4{color:var(--t4)}
"""

CSS = CHART_CSS + """
.btg{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.bt{display:flex;flex-direction:column;gap:6px;border:1px solid var(--line);border-radius:12px;padding:10px 12px;color:var(--ink);background:var(--panel)}
.bt:hover{border-color:var(--line2)}
.btn{font-weight:700;font-size:14.5px}.btn i{display:block;font-style:normal;color:var(--mut);font-size:11.5px;font-weight:400}
.btv{display:flex;align-items:baseline;gap:6px}.btl{font-size:30px;line-height:1;font-weight:800}.btt{font-weight:700;font-size:13.5px}
.bt0 .btl,.bt1 .btl,.bt0 .btt,.bt1 .btt{color:var(--ink2)}.bt2 .btl,.bt2 .btt{color:var(--t3)}
.bt3 .btl,.bt4 .btl,.bt3 .btt,.bt4 .btt{color:var(--t4)}.bt3,.bt4{border-color:var(--c4)}
.btk{font-size:12px;color:var(--ink2);line-height:1.5}
.bnav{margin-top:18px}
.bvd{margin:14px 0 0;border-top:1px solid var(--line);padding-top:10px}.bvd>summary{cursor:pointer;list-style:none;font-size:14px}
.bvd>summary::-webkit-details-marker{display:none}.bvd>summary::before{content:"▸ ";color:var(--mut)}.bvd[open]>summary::before{content:"▾ "}
.bvh{display:block;font-size:12.5px;color:var(--ink2);margin:2px 0 0 14px}
.bsum{font-size:14px;line-height:1.75;margin:6px 0 8px}
.bsig{font-size:13px;line-height:1.7;color:var(--ink2);margin:-2px 0 10px}.bsig a{margin-left:8px;white-space:nowrap}
.rat{display:block}.rat+.rat{margin-top:8px}.dec{display:block;color:var(--ink2);font-size:12.5px;margin-top:2px}.note.cyc{color:var(--ink);font-weight:600}
.bm .yes{color:var(--t4);font-weight:700}.bm .no{color:var(--mut)}.bm .na{color:var(--mut);border-bottom:1px dashed var(--line2)}
table.bnow td:nth-child(2){white-space:normal;min-width:240px}table.bnow td:nth-child(3){white-space:normal;min-width:150px}
table.bval td em{display:block;font-style:normal;font-size:11.5px;color:var(--mut)}
table.bepi td:last-child{white-space:normal}
.bty{border-left:3px solid var(--line2);padding:2px 0 2px 12px;margin:0 0 12px}.bty h3{margin:4px 0 4px;font-size:14.5px}
.bty p{margin:0 0 4px;font-size:13.5px;line-height:1.75;color:var(--ink2)}
#bub-mth details>summary{cursor:pointer}#bub-mth p{font-size:13px;line-height:1.75;color:var(--ink2)}
@media (max-width:900px){.btg{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){table.bnow td:nth-child(2),table.bnow td:nth-child(3){min-width:0}.btl{font-size:26px}}
"""

BLOCK_CSS = CHART_CSS + """
.mbub .ch{margin-bottom:4px}.mbc{margin:2px 0 8px}
.mbi{list-style:none;margin:6px 0 0;padding:0;font-size:13.5px;line-height:1.7}
.mbi li{display:flex;flex-wrap:wrap;gap:0 12px;padding:4px 0;border-top:1px solid var(--line)}
.mbi li>b{flex:0 0 7em;color:var(--ink2);font-weight:600}
.mbn{white-space:nowrap}.mbn b{font-weight:800}.mbn em{font-style:normal;font-size:12px;color:var(--mut);margin-left:4px;white-space:normal}
.mbt{margin-top:10px}.mbt h3{font-size:14.5px;margin:12px 0 6px}
@media (max-width:640px){.mbi li>b{flex-basis:100%}}
"""

JS = r"""
(function(){
const D = JSON.parse(document.getElementById('bubd').textContent || '{}');
const LV = ['沒有泡沫跡象','偏貴（不是泡沫）','漲勢過熱','泡沫警戒','嚴重泡沫'];
const CN = {'1':'價格爆發','2':'兩年翻倍','3':'偏離趨勢','e':'漲得比基本面快','v':'估值','g':'未來獲利跟不上','f':'槓桿','h':'換手率'};
const RG = {}, LW = {};
const NS = 'http://www.w3.org/2000/svg';
function el(t, a){ const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; }
function ym(d){ return (+d.slice(0,4)) + '/' + (+d.slice(5,7)); }
function fmt(x){ return x >= 1000 ? Math.round(x).toLocaleString() : x.toFixed(1); }
function defRg(mk){ const b = document.querySelector('[data-br].on[data-mk="' + mk + '"]'); return b ? +b.dataset.br : 0; }
function rows(mk){
  const H = D[mk]; const out = [];
  if (!H) return out;
  const yrs = mk in RG ? RG[mk] : defRg(mk);
  const last = H.d.length ? +H.d[H.d.length - 1].slice(0,4) : 0;
  const keep = d => !yrs || +d.slice(0,4) > last - yrs;
  if (!yrs && H.xd) H.xd.forEach((d, i) => out.push({d, L: H.xL[i], c: H.xc ? H.xc[i] : '', p: H.xp ? H.xp[i] : null, x: true}));
  H.d.forEach((d, i) => { if (keep(d)) out.push({d, L: H.L[i], c: H.c[i], p: H.p[i], x: false}); });
  return out;
}
function draw(mk){
  const box = document.getElementById('h-' + mk);
  if (!box) return;
  const R = rows(mk);
  if (!R.length){ box.innerHTML = '<p class="note">歷史等級還算不出來。</p>'; return; }
  const W = Math.max(280, box.clientWidth || 600), mob = W < 560;
  LW[mk] = W;
  const L = mob ? 6 : 8, Rp = mob ? 46 : 52, BH = 16, top = BH + 8, PH = mob ? 120 : 160, H = top + PH + 22;
  const svg = el('svg', {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: 'img', 'aria-label': '歷史泡沫等級與指數'});
  const n = R.length, dx = (W - L - Rp) / n;
  const X = i => L + i * dx;
  R.forEach((r, i) => svg.appendChild(el('rect', {x: X(i).toFixed(2), y: 0, width: Math.max(1, dx + 0.6).toFixed(2), height: BH,
    class: 'lv' + r.L + (r.x ? ' lvx' : '')})));
  const ps = R.map(r => r.p).filter(p => p);
  if (ps.length > 1){
    const lo = Math.log(Math.min(...ps)), hi = Math.log(Math.max(...ps)), sp = (hi - lo) || 1;
    const Y = p => top + (hi - Math.log(p)) / sp * PH;
    const path = ext => { let d = '', pen = false;
      R.forEach((r, i) => { if (!r.p || r.x !== ext){ pen = false; return; } d += (pen ? 'L' : 'M') + (X(i) + dx / 2).toFixed(1) + ' ' + Y(r.p).toFixed(1); pen = true; });
      return d; };
    const dpath = path(false), xpath = path(true);
    [Math.max(...ps), Math.min(...ps)].forEach(v => {
      const y = Y(v);
      svg.appendChild(el('line', {x1: L, x2: W - Rp, y1: y, y2: y, class: 'gl'}));
      const t = el('text', {x: W - Rp + 4, y: y + 4, class: 'ax'}); t.textContent = fmt(v); svg.appendChild(t);
    });
    if (xpath) svg.appendChild(el('path', {d: xpath, class: 'pxx'}));
    svg.appendChild(el('path', {d: dpath, class: 'px'}));
  }
  const y0 = +R[0].d.slice(0,4), y1 = +R[n - 1].d.slice(0,4), span = y1 - y0;
  const step = span > 60 ? 20 : span > 30 ? 10 : span > 12 ? 5 : span > 5 ? 2 : 1;
  for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step){
    const i = R.findIndex(r => +r.d.slice(0,4) === y);
    if (i < 0) continue;
    const t = el('text', {x: X(i).toFixed(1), y: H - 6, class: 'ax'}); t.textContent = y; svg.appendChild(t);
  }
  const gd = el('line', {x1: 0, x2: 0, y1: 0, y2: top + PH, class: 'gd', visibility: 'hidden'});
  svg.appendChild(gd);
  const tip = document.getElementById('t-' + mk);
  const at = e => { const b = svg.getBoundingClientRect(); const x = (e.clientX - b.left) * W / b.width; return Math.max(0, Math.min(n - 1, Math.floor((x - L) / dx))); };
  const show = e => {
    const i = at(e), r = R[i];
    const cs = r.c.split('').map(c => CN[c]).filter(Boolean);
    gd.setAttribute('x1', X(i) + dx / 2); gd.setAttribute('x2', X(i) + dx / 2); gd.setAttribute('visibility', 'visible');
    tip.innerHTML = `<b>${ym(r.d)}${r.x ? '（月平均）' : ''}</b>等級 ${r.L} ${LV[r.L]}` + (cs.length ? `<br>成立：${cs.join('、')}` : '') + (r.p ? `<br>${mk[0] === '@' ? '產業指數' : (r.x ? '月平均' : '月底收盤')} ${fmt(r.p)}` : '');
    tip.hidden = false;
    const bw = box.clientWidth, px = (X(i) + dx / 2) * bw / W;
    tip.style.left = Math.min(bw - 170, Math.max(0, px + 10)) + 'px'; tip.style.top = (BH + 4) + 'px';
  };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerdown', show);
  svg.addEventListener('pointerleave', () => { tip.hidden = true; gd.setAttribute('visibility', 'hidden'); });
  box.innerHTML = ''; box.appendChild(svg);
}
function all(){ Object.keys(D).filter(k => k[0] !== '@').forEach(draw); }
window.bubDraw = draw;
document.addEventListener('click', e => {
  const b = e.target.closest('[data-br]');
  if (!b) return;
  const mk = b.dataset.mk; RG[mk] = +b.dataset.br;
  b.parentElement.querySelectorAll('[data-br]').forEach(x => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  draw(mk);
});
let rz = 0;
addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { Object.keys(D).forEach(mk => { const box = document.getElementById('h-' + mk); if (box && box.offsetParent !== null && Math.abs((box.clientWidth || 0) - (LW[mk] || 0)) >= 40) draw(mk); }); }, 150); });
all();
})();
"""
