"""「部位參考」卡（訊號總覽「研究細節」；docs/lab_crash_plan.md 第 18～19 節）＋景氣頁狀態列的一格。

景氣頁建頁時 state_now(...) 算今天的部位（訊號用訊號總覽算好的「現在有效」），研究檔 data/lab/pos_research.json 給過去回測；
卡片照樣由 heatviz.stash_cards 存給訊號總覽。class 一律 xv 開頭。只描述規則算出的部位與回測，不寫買賣指示。
"""
from __future__ import annotations

import math
from html import escape

from . import posspec as S

_e = lambda x: escape(str(x), quote=True)
SHOW = ("full", "v", S.MAIN)                  # 圖與一句話用的三個版本
LINE = {"full": "xvl0", "v": "xvl1", S.MAIN: "xvl2"}


def _p(x, d: int = 1) -> str:
    return "—" if x is None else f"{100 * x:.{d}f}%"


def _sg(x, d: int = 1) -> str:
    if x is None:
        return "—"
    v = 100 * x
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.{d}f}%"


def _ym(d: str | None) -> str:
    return "—" if not d else f"{d[:4]}-{d[5:7]}"


def _md(d: str | None) -> str:
    return "—" if not d or len(d) < 10 else f"{int(d[5:7])}/{int(d[8:10])}"


def state_now(signow: dict | None) -> dict | None:
    """景氣頁用：signow＝sigcat.now_for_B 的結果。研究檔或今天的資料缺一樣就回 None（卡片與狀態列都不顯示）。"""
    from . import pos as P
    from . import sigcat as G
    if not signow:
        return None
    mk = signow["mk"]
    R = P.load()
    M = ((R or {}).get("mk") or {}).get(mk)
    fr = G.FR.get(mk)
    if not M or not fr:
        return None
    rows = G.research_rows()
    ids = P.star_ids(rows, mk)
    now = P.now(mk, fr["cal"], fr["px"], signow.get("on") or {}, ids)
    names = {r["id"]: r["name"] for r in rows if r.get("mk") == mk}
    return {"mk": mk, "M": M, "now": now, "names": names}


def chip(C: dict | None) -> str:
    """景氣頁狀態列的一格：主要版本今天的部位參考，點了到訊號總覽那張卡。"""
    if not C or not C.get("now"):
        return ""
    n, M = C["now"], C["M"]
    m, f = M["m"][S.MAIN], M["m"]["full"]
    tip = (f'{S.VERSION_NAMES[S.MAIN]}算出的部位，下一個交易日收盤調整；過去（{_ym(M["d0"])} 起）最大回落 {_p(m["mdd"], 0)}'
           f'（一直滿倉 {_p(f["mdd"], 0)}）、年化 {_p(m["cagr"])}（{_p(f["cagr"])}）。只描述規則，不是買賣指示。')
    return (f'<a class="stc" href="x9o.html#r={_e(C["mk"])}:pos" title="{_e(tip)}"><b>部位參考</b>{100 * n["pos"][S.MAIN]:.0f}%'
            f'<i>回測{_e(S.VERDICT_NAMES[M["verdict"][S.MAIN]])}</i></a>')


def lead(C: dict) -> list[str]:
    n, M = C["now"], C["M"]
    nm = C.get("names") or {}
    out = []
    if n:
        p = n["pos"]
        parts = [f'近 20 日波動 {_p(n["vol"])}，長期平均 {_p(n["tgt_vol"])} → 只看波動 {100 * p["v"]:.0f}%']
        if n["warn"]:
            parts.append(f'★ 警示有效（{"、".join(nm.get(k, k) for k in n["warn"])}）→ 最多 {100 * S.WARN_CAP:.0f}%')
        if n["buy"]:
            parts.append(f'★ 買點有效（{"、".join(nm.get(k, k) for k in n["buy"])}）→ 100%')
        if not n["warn"] and not n["buy"]:
            parts.append("沒有 ★ 警示或買點在有效期間")
        out.append(f'今天的部位參考 {100 * p[S.MAIN]:.0f}%（{_md(n["d"])} 收盤算，下一個交易日收盤調整）：' + "；".join(parts) + "。")
    m, f, v = M["m"][S.MAIN], M["m"]["full"], M["m"]["v"]
    out.append(f'過去（{_ym(M["d0"])}～{_ym(M["d1"])}）照這個規則：年化 {_p(m["cagr"])}、最大回落 {_p(m["mdd"])}；'
               f'一直滿倉 {_p(f["cagr"])}、{_p(f["mdd"])}（{S.VERDICT_NAMES[M["verdict"][S.MAIN]]}）。'
               f'只看波動：{_p(v["cagr"])}、{_p(v["mdd"])}（{S.VERDICT_NAMES[M["verdict"]["v"]]}）。')
    return out


def chart(M: dict) -> str:
    """月底淨值（對數刻度）：一直滿倉、只看波動、主要版本。"""
    c = M.get("curve") or {}
    ds = c.get("d") or []
    if len(ds) < 3:
        return ""
    vals = [x for k in SHOW for x in c.get(k) or [] if x and x > 0]
    lo, hi = math.log(min(vals)), math.log(max(vals))
    rg = max(hi - lo, 1e-9)
    n = len(ds)
    lines = []
    for k in SHOW:
        pts = " ".join(f'{1000 * i / (n - 1):.1f},{300 * (1 - (math.log(x) - lo) / rg):.1f}'
                       for i, x in enumerate(c[k]) if x and x > 0)
        lines.append(f'<polyline class="{LINE[k]}" points="{pts}" vector-effect="non-scaling-stroke"/>')
    y0, y1 = int(ds[0][:4]), int(ds[-1][:4])
    step = 10 if y1 - y0 > 30 else 5
    ticks = []
    for y in range((y0 // step + 1) * step, y1 + 1, step):
        i = next((j for j, d in enumerate(ds) if d >= f"{y}-01"), None)
        if i is not None:
            ticks.append(f'<span style="left:{100 * i / (n - 1):.1f}%">{y}</span>')
    leg = "".join(f'<span><i class="{LINE[k]}"></i>{_e(S.VERSION_NAMES[k])} 1 元 → {c[k][-1]:,.1f} 元</span>' for k in SHOW)
    return (f'<div class="xvch"><svg viewBox="0 0 1000 300" preserveAspectRatio="none" role="img" '
            f'aria-label="月底淨值（對數刻度）">{"".join(lines)}</svg><div class="xvax">{"".join(ticks)}</div></div>'
            f'<div class="xvlg">{leg}</div><p class="xvn">對數刻度；{_ym(ds[0])} 起，空出來的部位不計利息。</p>')


def table(M: dict) -> str:
    """各版本：年化、最大回落、夏普、平均部位、一年調整、判定、近 10 年。手機只留版本（判定寫在名稱下面）、年化、最大回落、近 10 年。"""
    head = ('<tr><th class="l">版本</th><th>年化</th><th>最大回落</th><th class="xvo">夏普</th><th class="xvo">平均部位</th>'
            '<th class="xvo">一年調整</th><th class="l xvo">和一直滿倉比</th><th>近 10 年<small>年化／最大回落</small></th></tr>')
    rows = []
    for k in S.VERSIONS:
        m, r = M["m"][k], M["mr"][k]
        vd = "—" if k == "full" else S.VERDICT_NAMES[M["verdict"][k]]
        vr = "" if k == "full" else f'<small>{_e(S.VERDICT_NAMES[M["verdict_r"][k]])}</small>'
        cls = ' class="xvm"' if k == S.MAIN else ""
        rows.append(f'<tr{cls}><td class="l"><b>{_e(S.VERSION_NAMES[k])}</b>'
                    f'{"" if k == "full" else f"<small class=xvmo>{_e(vd)}</small>"}</td>'
                    f'<td>{_p(m["cagr"])}</td><td>{_p(m["mdd"])}</td>'
                    f'<td class="xvo">{m["sharpe"]:.2f}</td><td class="xvo">{100 * m["avg_w"]:.0f}%</td>'
                    f'<td class="xvo">{m["tr_y"]:.1f} 次</td><td class="l xvo">{_e(vd)}</td>'
                    f'<td>{_p(r["cagr"])}／{_p(r["mdd"])}{vr}</td></tr>')
    return f'<div class="tw"><table class="xvt">{head}{"".join(rows)}</table></div>'


def bears(M: dict) -> str:
    B = M.get("bears") or []
    if not B:
        return ""
    rows = "".join(f'<tr><td class="l">{_ym(b["pk"])}～{_ym(b["tr"])}{"<small>還沒反彈 20%</small>" if b.get("open") else ""}</td>'
                   f'<td>{_sg(-b["dd"], 0)}</td><td>{_sg(b["full"], 0)}</td>'
                   f'<td>{_sg(b["v"], 0)}</td><td>{_sg(b[S.MAIN], 0)}</td></tr>' for b in reversed(B))
    return (f'<details class="xvmore"><summary>每一段大跌（跌 {100 * S.BEAR:.0f}% 以上，{len(B)} 段）</summary>'
            '<div class="tw"><table class="xvt xvb"><tr><th class="l">高點～低點</th><th>指數</th><th>一直滿倉</th>'
            f'<th>只看波動</th><th>主要版本</th></tr>{rows}</table></div>'
            '<p class="xvn">主要版本＝波動＋警示降檔＋落底回補。一直滿倉含股利時（S&amp;P 500）和指數跌幅會有一點差別。</p></details>')


def method(C: dict) -> str:
    M = C["M"]
    nm = C.get("names") or {}
    ids = M.get("ids") or {}
    sh = M.get("share") or {}
    w = "、".join(nm.get(k, k) for k in ids.get("warn") or []) or "沒有"
    b = "、".join(nm.get(k, k) for k in ids.get("buy") or []) or "沒有"
    tr = ""
    if M.get("tr"):
        t = M["tr"]["m"]
        tr = (f'<p>台股 {_ym(M["tr"]["d0"])} 起改用加權報酬指數（含息）重算：一直滿倉 {_p(t["full"]["cagr"])}／{_p(t["full"]["mdd"])}、'
              f'只看波動 {_p(t["v"]["cagr"])}／{_p(t["v"]["mdd"])}、主要版本 {_p(t[S.MAIN]["cagr"])}／{_p(t[S.MAIN]["mdd"])}。</p>')
    return ('<div class="xvmh">'
            f'<p><b>只看波動</b>：部位＝100% 和「長期平均波動 ÷ 近 {S.VOL_N} 日波動」取小的；長期平均＝到前一天為止所有近 {S.VOL_N} 日波動的平均'
            f'（只用當時拿得到的資料，不挑參數；先累積 {S.VOL_WARM:,} 個交易日）。</p>'
            f'<p><b>警示降檔</b>：訊號總覽判定 ★ 的警示訊號在有效期間，部位最多 {100 * S.WARN_CAP:.0f}%。這個市場：{_e(w)}'
            f'（有效的日子 {_p(sh.get("warn"), 0)}）。</p>'
            f'<p><b>落底回補</b>：★ 買點訊號出現後 {S.BUY_DAYS} 個交易日，部位 100%。這個市場：{_e(b)}。</p>'
            f'<p><b>再加偏多訊號回補（對照）</b>：★ 偏多訊號有效也 100%（有效的日子 {_p(sh.get("up"), 0)}，幾乎一直有效）。</p>'
            f'<p><b>交易</b>：收盤算出部位，隔一個交易日收盤調整；和現在相差不到 {100 * S.BAND:.0f} 個百分點不調整；'
            f'成本＝調整比例 × 單邊 {100 * S.COST[C["mk"]]:.2f}%；不用槓桿、不放空，空出來的部位不計利息。</p>'
            f'<p><b>判定</b>（和一直滿倉比）：最大回落少 {100 * S.MDD_GAIN:.0f} 個百分點以上、年化少不到 {100 * S.CAGR_TOL:.0f} 個百分點＝少跌、也沒少賺；'
            f'最大回落少 {100 * S.MDD_GAIN:.0f} 個百分點以上、年化少更多＝少跌但少賺；其餘＝沒有少跌。</p>'
            '<p>⚠ 警示、買點用的 ★ 是用同一段資料判定的，這兩條規則的回測是樣本內，會偏好看；只看波動沒有挑參數。</p>'
            f'{tr}<p class="xvn">規格 arm/lab/posspec.py VER {S.VER}（{S.SPEC_DATE}，在算回測之前寫定）。</p></div>')


def card(C: dict | None) -> str:
    if not C:
        return ""
    ls = lead(C)
    lead_html = f'<p class="xvl">{_e(ls[0])}</p>' + "".join(f'<p class="xvl3">{_e(s)}</p>' for s in ls[1:])
    d = (C.get("now") or {}).get("d") or C["M"]["d1"]
    return (f'<section class="sec xvsec" id="pos"><div class="card xvc"><div class="khd"><h2>部位參考</h2>'
            f'<span class="kn">規則算出的部位・資料到 {_e(_md(d))}</span></div>{lead_html}'
            '<p class="ksub">依波動、★ 警示與 ★ 買點算出的持股比例，以及同樣的規則過去照做的結果。只描述規則與回測，不是買賣指示。</p>'
            f'{chart(C["M"])}{table(C["M"])}{bears(C["M"])}'
            f'<details class="xvmore"><summary>怎麼算</summary>{method(C)}</details></div></section>')


CSS = (
    ".xvc{padding:12px 14px;min-width:0}"
    ".xvl{font-size:15px;font-weight:700;margin:8px 0 4px;line-height:1.6}"
    ".xvl3{font-size:13.5px;color:var(--ink2);margin:0 0 4px;line-height:1.65}"
    ".xvch{position:relative;margin:10px 0 2px}"
    ".xvch svg{display:block;width:100%;height:180px;background:var(--card2);border-radius:8px}"
    ".xvch polyline{fill:none;stroke-width:2}"
    ".xvl0{stroke:var(--mut);stroke-dasharray:5 4}.xvl1{stroke:var(--acc)}.xvl2{stroke:var(--dchip)}"
    ".xvax{position:relative;height:16px;font-size:11px;color:var(--mut)}"
    ".xvax span{position:absolute;transform:translateX(-50%);top:2px}"
    ".xvlg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;margin:4px 0}"
    ".xvlg span{white-space:nowrap}.xvlg i{display:inline-block;width:18px;height:0;border-top:2px solid;vertical-align:4px;margin-right:5px}"
    ".xvlg i.xvl0{border-color:var(--mut);border-top-style:dashed}.xvlg i.xvl1{border-color:var(--acc)}.xvlg i.xvl2{border-color:var(--dchip)}"
    ".xvn{font-size:12px;color:var(--mut);margin:2px 0 6px;line-height:1.6}"
    "table.xvt{font-size:12.5px}table.xvt th,table.xvt td{padding:5px 6px;text-align:right;vertical-align:top}"
    "table.xvt td.l,table.xvt th.l{text-align:left;white-space:normal}"
    "table.xvt small{display:block;font-size:11px;color:var(--mut)}table.xvt tr.xvm td{background:var(--accbg)}"
    "table.xvt small.xvmo{display:none;font-weight:400}"
    "@media (max-width:640px){table.xvt .xvo{display:none}table.xvt small.xvmo{display:block}"
    "table.xvt{font-size:12px}table.xvt th,table.xvt td{padding:5px 4px}table.xvb td.l{white-space:nowrap}}"
    ".xvmore{margin:10px 0 0}.xvmore summary{cursor:pointer;font-size:13.5px;color:var(--acc)}"
    ".xvmh p{font-size:12.5px;color:var(--ink2);line-height:1.7;margin:6px 0}"
)
