"""泡沫頁（dashboard/x9b.html；docs/lab_risk_plan.md 第 7、8 節；規格 bubspec VER 1）。

五個市場（台股、S&P 500、那斯達克、那斯達克 100、費半）的泡沫等級 0～4：
  頁首等級磚 → 各市場一張卡（歷史等級圖、現在的五個條件、等級 ≥ 3 的泡沫段、驗證）→ 條件說明 → 方法與資料。
現在的狀態每天重算（bubble.market_for；同一個程序裡景氣頁先算、這裡沿用），驗證讀研究檔 data/lab/bub_research.json
（scripts/run_bub.py，資料或規格改了才重跑）。只描述位置，不是買賣訊號。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import bubble as BU
from . import bubspec as BS
from .heatpage import _e, _md, _ymd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9b.html"

COND_ORDER = ("P1", "P2", "P3", "V", "F")
SHORT = BU.SHORT
TEST_NAMES = {"P1": "價格爆發（PSY）", "P2": "兩年翻倍而且在高點", "P3": "偏離長期趨勢 2 個標準差", "V": "估值歷史前 5%",
              "F": "槓桿歷史前 10%", "L2": "等級 ≥ 2（漲勢過熱以上）", "L3": "等級 ≥ 3（泡沫警戒以上）", "L4": "等級 4（嚴重泡沫）"}
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
    return {"asof": asof, "M": M, "R": R}


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
    conds = [SHORT[c] for c in COND_ORDER if n.get(c)]
    s = f'{_sp(m["name"])}現在是等級 {lv}「{BS.LEVELS[lv]}」'
    s += f'：{"、".join(conds)}同時成立' if len(conds) >= 2 else (f"：只有{conds[0]}成立" if conds else "")
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
    return s + "。" + ("；".join(tail) + "。" if tail else "")


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

def tiles(V: dict) -> str:
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
        out.append(f'<a class="bt bt{n["L"]}" href="#{mk}"><span class="btn">{_e(m["name"])}<i>{_e(m["index"])}</i></span>'
                   f'<span class="btv"><b class="btl">{n["L"]}</b><span class="btt">{_e(BS.LEVELS[n["L"]])}</span></span>'
                   f'<span class="bcs">{chips}</span><span class="btk">{_e("・".join(key))}</span></a>')
    return ('<section class="sec" id="lv"><h2>五個市場的泡沫等級<span class="sub">0 沒有跡象・1 偏貴・2 漲勢過熱・3 泡沫警戒・4 嚴重泡沫</span></h2>'
            f'<div class="btg">{"".join(out)}</div>'
            '<p class="note">至少兩種不同類型的條件同時成立才到「泡沫警戒」。紅色＝成立，虛線＝這個市場沒有資料判定。</p></section>')


def _now_table(mk: str, m: dict) -> str:
    n, ref = m["now"], m.get("ref") or {}
    rows = [("P1", "價格爆發（PSY）", _p1_text(n), f"超過 95% 臨界值，連續 {BS.PSY_RUN} 個月"),
            ("P2", "兩年翻倍而且在高點", _p2_text(n), f"兩年漲 ≥ {BS.RUN2_PCT:.0f}%，離最高 {100 * BS.RUN2_ATH:.0f}% 以內"),
            ("P3", "偏離長期趨勢", _p3_text(n), f"≥ {BS.TREND_Z:.0f} 個標準差"),
            ("V", "估值", _v_text(mk, n, ref), f"至少 {BS.VAL_NEED} 項 ≥ 第 {BS.VAL_PCT:.0f} 百分位"),
            ("F", "槓桿", _f_text(mk, n), f"≥ 第 {BS.FUEL_PCT:.0f} 百分位")]
    tr = "".join(f'<tr><td class="l" data-h="條件">{_e(nm)}</td><td class="l" data-h="現在">{txt}</td>'
                 f'<td class="l" data-h="門檻">{_e(th)}</td><td data-h="成立">{_mark(n.get(c))}</td></tr>' for c, nm, txt, th in rows)
    return ('<h3>現在的五個條件</h3><div class="tw"><table class="stk bnow"><tr><th class="l">條件</th><th class="l">現在</th>'
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
    return f'<p class="note">參考讀數（不進等級）：{_e("；".join(xs))}。</p>' if xs else ""


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


def _valid_table(R: dict, tests=BS.TESTS) -> str:
    if not R:
        return '<p class="warn">驗證結果還沒產生。</p>'
    tr = []
    for t in tests:
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
        return "等級 ≥ 3 還沒有走完一年的歷史樣本"
    return (f'等級 ≥ 3 之後一年內跌 20%：{100 * e["p_hot"]:.0f}%，全部月份 {100 * e["p_all"]:.0f}%'
            f'（{e["n_hot"]} 個月、{e["n_epi"]} 段，{VERDICT.get(e.get("verdict"), "—")}）')


def _valid(mk: str, R: dict) -> str:
    rr = (R or {}).get(mk) or {}
    main = rr.get("main") or {}
    if not main:
        return '<h3>驗證：成立之後比較容易大跌嗎？</h3><p class="warn">驗證結果還沒產生（scripts/run_bub.py）。</p>'
    ext = rr.get("ext") or {}
    head = _valid_head(main) + (f'；延伸樣本（含 1987–1990）：{_valid_head(ext)}' if ext else "")
    out = [f'<details class="bvd"><summary><b>驗證：成立之後比較容易大跌嗎？</b><span class="bvh">{_e(head)}</span></summary>',
           f'<p class="note">樣本 {_e(_ymd(main["a"]))}～{_e(_ymd(main["z"]))}，每月一個樣本，共 {main["n"]:,} 個月。</p>',
           _valid_table(main)]
    rb = rr.get("robust") or {}
    if rb.get("L3"):
        e1, e2 = (rb["L3"].get("252") or {}), (rb["L3"].get("504") or {})
        if e1.get("n_hot"):
            out.append(f'<p class="note">1950 年起另算一次（穩健度）：等級 ≥ 3 之後一年內跌 20% {_cell(e1).replace("<em>", "（").replace("</em>", "）")}；'
                       f'兩年內跌 40% {_cell(e2).replace("<em>", "（").replace("</em>", "）")}。</p>')
    if ext:
        out.append(f'<h4>延伸樣本：國發會月平均 {_e(_ymd(ext["a"]))}～{_e(_ymd(ext["z"]))}（含 1987–1990）</h4>'
                   + _valid_table(ext, ("P1", "P2", "P3", "L2", "L3"))
                   + '<p class="note">只當穩健度：訊號用當月讀數，跌幅用之後 12、24 個月的月平均；兩年翻倍改用 24 個月月平均漲幅。</p>')
    out.append('<p class="note">判定：成立月份 ≥ 12 個月、≥ 4 段，差的 95% 區間（12 個月一塊重抽）不含 0、而且前後兩半同方向，'
               '才寫「較容易大跌」或「反而較少大跌」。平均報酬只描述，不判定。</p></details>')
    return "".join(out)


def market_card(mk: str, m: dict, R: dict) -> str:
    n = m["now"]
    ext = ((R or {}).get("tw") or {}).get("ext") if mk == "tw" else None
    rg = "".join(f'<button type="button" class="tb{" on" if y == 0 else ""}" data-br="{y}" data-mk="{mk}" '
                 f'aria-pressed="{"true" if y == 0 else "false"}">{"全部" if y == 0 else f"近 {y} 年"}</button>' for y in (0, 30, 10))
    return (f'<section class="sec cd bm" id="{mk}"><div class="ch"><h2>{_e(m["name"])}<span class="sub">{_e(m["index"])}</span></h2>'
            f'<div class="sv"><b class="sc bl{n["L"]}">{n["L"]}</b><span class="bn bl{n["L"]}">{_e(BS.LEVELS[n["L"]])}</span></div></div>'
            f'<p class="bsum">{_e(summary(mk, m))}</p>'
            f'<div class="seg brg" role="group" aria-label="期間">{rg}</div>'
            f'<div class="bh" id="h-{mk}"><p class="note">歷史等級載入中…</p></div><div class="tip" id="t-{mk}" hidden></div>'
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
     "（美股長期漲得快，沒考慮的話很容易誤報）。它只說明漲勢不正常，不告訴你什麼時候結束。"),
    ("P2", "兩年翻倍而且在高點（Greenwood、Shleifer、You 2019）",
     "美國與國際的產業資料：兩年漲一倍以上之後，兩年內跌 40% 的機率明顯變高，但之後的平均報酬不一定變差。"
     "大跌之後的反彈（還沒回到前高）不算，所以要求收盤離歷史最高 5% 以內。"),
    ("P3", "偏離長期趨勢 2 個標準差（GMO）",
     "實質股價離長期趨勢線多遠；GMO 把 2 個標準差定為泡沫門檻。長期趨勢本身也會改變，所以只當其中一個條件。"),
    ("V", "估值歷史前 5%（只有 S&P 500）",
     "CAPE、巴菲特指標、Tobin's Q 和全部歷史比。估值高可以維持很多年，主要影響的是之後 10 年的報酬，不是短期會不會崩，"
     "所以只有估值高只算「偏貴」。台股本益比只有 2013 年起、其他三個美股指數沒有自己的長歷史估值，不判定。"),
    ("F", "槓桿歷史前 10%",
     "推升漲勢的錢是不是借來的。美股＝家計部門證券融資年增率（四個指數共用）；台股＝融資 ÷ 市值（融資金額會跟著市值長大，"
     "要看比例；2013 年起，滿 10 年才判定）。"),
)


def types_sec(V: dict) -> str:
    out = []
    for c, nm, txt in TYPES:
        on = [V["M"][mk]["name"] for mk in BS.MARKETS if mk in V["M"] and V["M"][mk]["now"].get(c)]
        st = f'現在成立：{"、".join(on)}' if on else "現在沒有市場成立"
        out.append(f'<div class="bty"><h3>{_e(nm)}</h3><p>{_e(txt)}</p><p class="note">{_e(st)}</p></div>')
    return ('<section class="sec" id="types"><h2>五種條件代表什麼</h2>' + "".join(out)
            + '<p class="note">參考讀數（LPPLS、上漲加速度、集中度、本益比、超額 CAPE 殖利率）只列數字，不進等級：'
              '我們的 LPPLS 是網格近似，歷史上很少亮燈；其他項目沒有公認的泡沫門檻。</p></section>')


METHOD = (
    '<section class="sec" id="mth"><details class="cd"><summary><b>方法與資料</b></summary>'
    '<p>等級只看「幾種不同類型的條件同時成立」：0＝沒有價格條件也不是偏貴；1＝只有估值；2＝1 個價格條件；'
    '3＝2～3 個價格條件，或 1 個價格條件＋估值或槓桿；4＝2～3 個價格條件＋估值或槓桿。資料不夠長、算不出來的條件當作不成立。</p>'
    '<p>價格爆發：實質股價（月平均 ÷ 前一個月 CPI）取對數，算 BSADF（視窗至少 60 個月）。臨界值用「有長期漲勢的隨機漫步」模擬，'
    '漲勢＝到當月為止每月變化的平均 ÷ 標準差，8 檔各 2,000 次、相鄰兩檔內插。CPI 缺月（2025-10 美國政府停擺）用前後兩個月的幾何平均補上。</p>'
    '<p>每個條件只用當時拿得到的資料：月資料下個月 1 日起才用，家計證券融資季資料晚 3 個月半。驗證用每個月最後一個交易日，'
    '看之後一年內跌 20%、兩年內跌 40%（期間內收盤高點到之後低點）的比例，和所有月份比。</p>'
    '<p>資料：加權指數（證交所、國發會月平均）、S&P 500（Yahoo、Shiller）、那斯達克、那斯達克 100、費半（Yahoo）、'
    'CPI（主計總處、勞工統計局、Shiller）、Z.1 家計證券融資與股票市值（聯準會）、GDP（BEA）、融資金額（FinMind 轉載證交所）、上市櫃市值（自算）。</p>'
    '<p class="note">門檻都取自文獻，不用結果去調；規格寫在 arm/lab/bubspec.py（VER 1），改規格要升版本。只描述位置，不是買賣訊號。</p>'
    '</details></section>')


def page_json(V: dict) -> str:
    out = {}
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


def render(V: dict) -> str:
    from . import appnav
    from .heatpage import _CSS as HCSS
    nav = "".join(f'<a href="#{mk}">{_e(BS.NAMES[mk])}</a>' for mk in BS.MARKETS if mk in V["M"])
    body = (tiles(V) + f'<nav class="snav bnav" aria-label="段落">{nav}<a href="#types">條件說明</a><a href="#mth">方法</a></nav>'
            + "".join(market_card(mk, V["M"][mk], V["R"]) for mk in BS.MARKETS if mk in V["M"]) + types_sec(V) + METHOD)
    if not V["M"]:
        body = '<p class="warn">泡沫等級還算不出來（缺 PSY 臨界值表：scripts/run_bub.py --cv）。</p>'
    return (_HTML.replace("{{APPTAB}}", appnav.bar("bub")).replace("{{CSS}}", HCSS + appnav.CSS + CSS)
            .replace("{{ASOF}}", _e(_md(V["asof"]))).replace("{{BODY}}", body).replace("{{DATA}}", page_json(V) if V["M"] else "{}")
            .replace("{{JS}}", JS))


def build(out: Path = OUT) -> bool:
    text = render(view())
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return True


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<link rel="icon" href="data:,">
<title>泡沫等級</title>
<style>{{CSS}}</style></head>
<body>
<div class="top">{{APPTAB}}<span class="asof">資料到 {{ASOF}}</span><a class="back" href="./">返回主頁</a></div>
<div class="vbar"><details class="purp"><summary>這頁怎麼看</summary><p>泡沫等級 0～4：五個條件（價格爆發、兩年翻倍、偏離長期趨勢、估值、槓桿）裡，
至少兩種不同類型同時成立才到「泡沫警戒」。門檻取自文獻，不用結果去調。每個市場下面有歷史等級、現在的讀數、過去的泡沫段，
以及「成立之後比較容易大跌嗎」的驗證。只描述位置，不是買賣訊號。</p></details></div>
<main>{{BODY}}</main>
<script type="application/json" id="bubd">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

CSS = """
:root{--lv0:#e4e8ef;--lv1:#b9c4d4;--lv2:#f1c25a;--lv3:#ea8a3a;--lv4:#d33a34}
@media (prefers-color-scheme:dark){:root{--lv0:#243047;--lv1:#4a5a76;--lv2:#b98f2e;--lv3:#d9782f;--lv4:#f15b50}}
.btg{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}
.bt{display:flex;flex-direction:column;gap:6px;border:1px solid var(--line);border-radius:12px;padding:10px 12px;color:var(--ink);background:var(--panel)}
.bt:hover{border-color:var(--line2)}
.btn{font-weight:700;font-size:14.5px}.btn i{display:block;font-style:normal;color:var(--mut);font-size:11.5px;font-weight:400}
.btv{display:flex;align-items:baseline;gap:6px}.btl{font-size:30px;line-height:1;font-weight:800}.btt{font-weight:700;font-size:13.5px}
.bt0 .btl,.bt1 .btl,.bt0 .btt,.bt1 .btt,.bl0,.bl1{color:var(--ink2)}.bt2 .btl,.bt2 .btt,.bl2{color:var(--t3)}
.bt3 .btl,.bt4 .btl,.bt3 .btt,.bt4 .btt,.bl3,.bl4{color:var(--t4)}.bt3,.bt4{border-color:var(--c4)}
.bcs{display:flex;flex-wrap:wrap;gap:4px}.bcs i{font-style:normal;font-size:11.5px;padding:0 7px;border-radius:999px;border:1px solid var(--line2);color:var(--mut)}
.bcs i.on{background:var(--sbg);border-color:var(--c4);color:var(--t4);font-weight:600}.bcs i.na{border-style:dashed}
.btk{font-size:12px;color:var(--ink2);line-height:1.5}
.vbar{max-width:1080px;margin:2px auto 6px;padding:0 16px}
.bnav{margin-top:18px}
.bvd{margin:14px 0 0;border-top:1px solid var(--line);padding-top:10px}.bvd>summary{cursor:pointer;list-style:none;font-size:14px}
.bvd>summary::-webkit-details-marker{display:none}.bvd>summary::before{content:"▸ ";color:var(--mut)}.bvd[open]>summary::before{content:"▾ "}
.bvh{display:block;font-size:12.5px;color:var(--ink2);margin:2px 0 0 14px}
.bsum{font-size:14px;line-height:1.75;margin:6px 0 8px}
.brg{margin:0 0 6px}
.bh{position:relative;min-height:120px}.bh svg{touch-action:pan-y}
.bh .gd{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}.bh .px{fill:none;stroke:var(--ink);stroke-width:1.5}
.bh .pxx{fill:none;stroke:var(--ink2);stroke-width:1.4;stroke-dasharray:4 3}.hint{border-bottom:1px dotted var(--line2);cursor:help}
.bh .ax{font-size:11px;fill:var(--mut)}.bh .gl{stroke:var(--line);stroke-width:1}
.lv0{fill:var(--lv0)}.lv1{fill:var(--lv1)}.lv2{fill:var(--lv2)}.lv3{fill:var(--lv3)}.lv4{fill:var(--lv4)}.lvx{opacity:.55}
.blg{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--mut);margin:4px 0 10px}
.blg i{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.lvk0{background:var(--lv0)}.lvk1{background:var(--lv1)}.lvk2{background:var(--lv2)}.lvk3{background:var(--lv3)}.lvk4{background:var(--lv4)}
.blg i.lvx{background:repeating-linear-gradient(45deg,var(--lv3),var(--lv3) 2px,var(--panel) 2px,var(--panel) 4px);opacity:1}
.yes{color:var(--t4);font-weight:700}.no{color:var(--mut)}.na{color:var(--mut);border-bottom:1px dashed var(--line2)}
table.bnow td:nth-child(2){white-space:normal;min-width:240px}table.bnow td:nth-child(3){white-space:normal;min-width:150px}
table.bval td em{display:block;font-style:normal;font-size:11.5px;color:var(--mut)}
table.bepi td:last-child{white-space:normal}
.bty{border-left:3px solid var(--line2);padding:2px 0 2px 12px;margin:0 0 12px}.bty h3{margin:4px 0 4px;font-size:14.5px}
.bty p{margin:0 0 4px;font-size:13.5px;line-height:1.75;color:var(--ink2)}
#mth details>summary{cursor:pointer}#mth p{font-size:13px;line-height:1.75;color:var(--ink2)}
@media (max-width:900px){.btg{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width:640px){table.bnow td:nth-child(2),table.bnow td:nth-child(3){min-width:0}.btl{font-size:26px}}
"""

JS = r"""
(function(){
const D = JSON.parse(document.getElementById('bubd').textContent || '{}');
const LV = ['沒有泡沫跡象','偏貴（不是泡沫）','漲勢過熱','泡沫警戒','嚴重泡沫'];
const CN = {'1':'價格爆發','2':'兩年翻倍','3':'偏離趨勢','v':'估值','f':'槓桿'};
const RG = {}, LW = {};
const NS = 'http://www.w3.org/2000/svg';
function el(t, a){ const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; }
function ym(d){ return (+d.slice(0,4)) + '/' + (+d.slice(5,7)); }
function fmt(x){ return x >= 1000 ? Math.round(x).toLocaleString() : x.toFixed(1); }
function rows(mk){
  const H = D[mk]; const out = [];
  if (!H) return out;
  const yrs = RG[mk] || 0;
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
    tip.innerHTML = `<b>${ym(r.d)}${r.x ? '（月平均）' : ''}</b>等級 ${r.L} ${LV[r.L]}` + (cs.length ? `<br>成立：${cs.join('、')}` : '') + (r.p ? `<br>${r.x ? '月平均' : '月底收盤'} ${fmt(r.p)}` : '');
    tip.hidden = false;
    const bw = box.clientWidth, px = (X(i) + dx / 2) * bw / W;
    tip.style.left = Math.min(bw - 170, Math.max(0, px + 10)) + 'px'; tip.style.top = (BH + 4) + 'px';
  };
  svg.addEventListener('pointermove', show);
  svg.addEventListener('pointerdown', show);
  svg.addEventListener('pointerleave', () => { tip.hidden = true; gd.setAttribute('visibility', 'hidden'); });
  box.innerHTML = ''; box.appendChild(svg);
}
function all(){ Object.keys(D).forEach(draw); }
document.addEventListener('click', e => {
  const b = e.target.closest('[data-br]');
  if (!b) return;
  const mk = b.dataset.mk; RG[mk] = +b.dataset.br;
  b.parentElement.querySelectorAll('[data-br]').forEach(x => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); });
  draw(mk);
});
let rz = 0;
addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { Object.keys(D).forEach(mk => { const box = document.getElementById('h-' + mk); if (box && Math.abs((box.clientWidth || 0) - (LW[mk] || 0)) >= 40) draw(mk); }); }, 150); });
all();
})();
"""
