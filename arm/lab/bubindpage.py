"""泡沫頁的「產業」段（docs/lab_risk_plan.md 第 12.5 節；規格 bubindspec VER 1）。

台股產業表、美股類股表（點一列看歷史等級與指數）、美股 49 細產業表（收起來）、驗證（收起來）。
現在的狀態每天重算（bubind.compute，約 5 秒），驗證讀 data/lab/bubind_research.json（scripts/run_bubind.py）。
只描述位置，不是買賣訊號。
"""
from __future__ import annotations

from . import bubindspec as BI
from .heatpage import _e, _ymd

COND = ("P1", "P2", "P3", "E", "G", "F")
SHORT = {"P1": "價格爆發", "P2": "兩年翻倍", "P3": "偏離趨勢", "E": "漲得比營收快", "G": "未來獲利跟不上", "F": "換手率"}
SHORT_FF = {**SHORT, "F": "新公司"}
GRP_COND = {"tw": ("P1", "P2", "P3", "E", "G", "F"), "us": ("P1", "P2", "P3", "G"), "ff": ("P1", "P2", "P3", "F")}
MAX_LV = {"tw": 4, "us": 3, "ff": 2}
TEST_NAMES = {"P1": "價格爆發（PSY）", "P2": "兩年翻倍、比大盤多漲而且在高點", "P3": "偏離長期趨勢 2 個標準差",
              "E": "價格漲得比營收快（市值 ÷ 營收的比值爆發）", "G": "未來獲利跟不上（營收替代）", "F": "燃料（換手率／新公司）",
              "PX": "價格過熱（任一價格條件）", "P2F": "兩年翻倍，而且新公司大量進來", "L3": "等級 ≥ 3"}
VERDICT = {"crash": "成立後較容易大跌", "calm": "成立後反而較少大跌", "none": "看不出差別", "few": "樣本不足"}
LV = BI.LEVELS


def name_of(grp: str, k: str) -> str:
    if grp == "us":
        return f"{BI.US_ETF.get(k, k)}（{k}）"
    if grp == "ff":
        return f"{BI.FF_NAMES.get(k, k)}（{k}）"
    return k


def _pct(x, dec=0, sign=True) -> str:
    """百分比文字；四捨五入後是 0 就寫 0%（不寫 -0%）。"""
    if x is None:
        return "—"
    v = round(x, dec)
    if v == 0:
        return f"{0:.{dec}f}%"
    return (f"{v:+.{dec}f}" if sign else f"{v:.{dec}f}") + "%"


def _dist(x) -> str:
    """離最高點：0 寫「在最高點」。"""
    if x is None:
        return "—"
    return "在最高點" if round(x, 1) == 0 else _pct(x, 1)


def _chips(grp: str, n: dict) -> str:
    """成立的條件（只列成立的；都沒有就寫 —）。"""
    sh = SHORT_FF if grp == "ff" else SHORT
    xs = "".join(f'<i class="on">{sh[c]}</i>' for c in GRP_COND[grp] if n.get(c))
    return xs or '<i class="nil">—</i>'


def _g_cell(n: dict) -> tuple[str, float | None]:
    """未來獲利欄：分析師預估（今年→明年、明年預估 3 個月修正）或營收替代資料；回傳 (文字, 排序值)。"""
    g = n.get("g") or {}
    if n.get("gsrc") == "est" or (g and g.get("g0") is not None and "y12" not in g):
        if g.get("g0") is None or g.get("g1") is None:
            return "—", None
        s = f'{_pct(100 * g["g0"])} → {_pct(100 * g["g1"])}'
        if g.get("rev") is not None:
            s += f'｜{"上修" if g["rev"] >= 0 else "下修"} {abs(100 * g["rev"]):.0f}%'
        return s, 100 * g["g1"]
    if n.get("gsrc") == "proxy" and g.get("y12") is not None:
        b = "" if g.get("y12b") is None else f'（半年前 {_pct(100 * g["y12b"])}）'
        return f'營收年增 {_pct(100 * g["y12"])}{b}', 100 * g["y12"]
    return "—", None


def sentence(grp: str, name: str, n: dict) -> str:
    """一個產業的一句話：等級、成立的條件、兩年漲幅與比大盤、離高點、未來獲利、燃料。"""
    sh = SHORT_FF if grp == "ff" else SHORT
    lv = n["L"]
    on = [sh[c] for c in GRP_COND[grp] if n.get(c)]
    hot = any(n.get(c) for c in ("P1", "P2", "P3"))
    s = f'{name}：等級 {lv}「{LV[lv]}」' + (f'（{"、".join(on)}）' if on else "")
    if on and not hot:
        s += "，價格沒有過熱，所以不升級"
    p2 = n.get("p2") or {}
    xs = []
    if p2.get("ru") is not None:
        x = f'兩年 {_pct(p2["ru"])}'
        if p2.get("net") is not None:
            x += f'，比大盤{"多" if p2["net"] >= 0 else "少"} {abs(p2["net"]):.0f} 個百分點'
        if p2.get("dist") is not None:
            x += "，在最高點" if round(p2["dist"], 1) == 0 else f'，離最高點 {abs(p2["dist"]):.1f}%'
        xs.append(x)
        if not n.get("P2") and p2["ru"] >= BI.RUN2_PCT:
            why = []
            if p2.get("net") is not None and p2["net"] < BI.NET_PP:
                why.append(f'比大盤多漲不到 {BI.NET_PP:.0f} 個百分點')
            if p2.get("dist") is not None and p2["dist"] < -100 * BI.RUN2_ATH:
                why.append(f'離最高點超過 {100 * BI.RUN2_ATH:.0f}%')
            if why:
                xs.append("兩年已經翻倍，但" + "、".join(why) + "，不算「兩年翻倍」")
    p1 = n.get("p1") or {}
    if p1.get("run"):
        xs.append(f'價格爆發讀數連 {p1["run"]} 個月超過臨界值')
    g = n.get("g") or {}
    if grp in ("tw", "us"):
        if n.get("gsrc") == "est" and g.get("g0") is not None and g.get("g1") is not None:
            t = (f'分析師預估（{g.get("n")} 家、涵蓋 {100 * (g.get("cov") or 0):.0f}% 市值）：今年 {_pct(100 * g["g0"])}、明年 {_pct(100 * g["g1"])}'
                 f'，{"成長減速" if g["g1"] < g["g0"] else "成長沒有減速"}')
            if g.get("rev") is not None:
                t += f'；明年預估近 3 個月{"上修" if g["rev"] >= 0 else "下修"} {abs(100 * g["rev"]):.1f}%'
                if g.get("px3") is not None:
                    t += f'，價格近 3 個月 {_pct(g["px3"], 1)}'
            xs.append(t)
        elif n.get("gsrc") == "proxy" and g.get("y12") is not None:
            xs.append(f'營收（替代資料，{_ymd(g["per"])}）近 12 個月年增 {_pct(100 * g["y12"])}'
                      + ("" if g.get("y12b") is None else f'，半年前 {_pct(100 * g["y12b"])}'))
        elif grp == "tw" and name in BI.E_SKIP:
            xs.append("營收含投資損益，營收比值與未來獲利不判定")
    if grp == "tw" and n.get("f") is not None:
        xs.append(f'換手率第 {n["f"]:.0f} 百分位')
    if grp == "ff" and n.get("f") is not None:
        xs.append(f'家數 12 個月增加率第 {n["f"]:.0f} 百分位')
    return s + "。" + ("；".join(xs) + "。" if xs else "")


def _row(grp: str, k: str, n: dict, key: str | None, mem: int | None = None) -> str:
    p2 = n.get("p2") or {}
    gtxt, gv = _g_cell(n)
    nm = name_of(grp, k)
    sub = f'<span class="sub">{mem} 檔</span>' if mem else ""
    net = p2.get("net")
    nt = ("" if net is None else
          f'比大盤 <span class="nw">{"+" if round(net) > 0 else ("-" if round(net) < 0 else "")}{abs(net):.0f} 個百分點</span>')
    chips = _chips(grp, n)
    cells = [f'<td class="l bnm" data-v="{_e(nm)}">{_e(nm)}{sub}<span class="bcs mob">{chips}</span></td>',
             f'<td data-v="{n["L"]}"><b class="bl{n["L"]}">{n["L"]}</b> <span class="bl{n["L"]} lvn">{_e(LV[n["L"]])}</span></td>',
             f'<td class="l bcc dsk"><span class="bcs">{chips}</span></td>',
             f'<td data-v="{"" if p2.get("ru") is None else round(p2["ru"], 2)}">{_pct(p2.get("ru"))}<em>{nt}</em></td>',
             f'<td class="dsk" data-v="{"" if p2.get("dist") is None else round(p2["dist"], 2)}">{_dist(p2.get("dist"))}</td>']
    if grp in ("tw", "us"):
        cells.append(f'<td class="l dsk" data-v="{"" if gv is None else round(gv, 2)}">{_e(gtxt)}</td>')
    if grp == "ff":
        fv = n.get("f")
        ft = "—" if fv is None else f"第 {fv:.0f} 百分位"
        cells.append(f'<td class="dsk" data-v="{"" if fv is None else round(fv, 1)}">{ft}</td>')
    if key is None:
        return f'<tr>{"".join(cells)}</tr>'
    span = len(cells)
    return (f'<tr class="bir" data-k="{key}" tabindex="0">{"".join(cells)}</tr>'
            f'<tr class="bid" hidden><td colspan="{span}" class="l"><p class="bsum">{_e(sentence(grp, name_of(grp, k), n))}</p>'
            f'<div class="bhw"><div class="bh" id="h-{key}"><p class="note">歷史等級載入中…</p></div><div class="tip" id="t-{key}" hidden></div></div>'
            '<p class="note">上面色塊＝每個月的等級，線＝產業指數（月底，對數座標）。</p></td></tr>')


def _head(grp: str) -> str:
    ths = ['<th class="l" data-si="0">產業</th>', '<th data-si="1">等級</th>', '<th class="l dsk">成立的條件</th>',
           '<th data-si="3">兩年漲幅</th>', '<th class="dsk" data-si="4">離最高點</th>']
    if grp in ("tw", "us"):
        ths.append('<th class="l dsk" data-si="5">未來獲利：今年→明年｜明年預估近 3 個月</th>')
    if grp == "ff":
        ths.append('<th class="dsk" data-si="5">家數增加（百分位）</th>')
    return f'<thead><tr>{"".join(ths)}</tr></thead>'


def _order(G: dict) -> list:
    """等級高的在前，同等級依兩年漲幅（高到低）。"""
    return sorted(G, key=lambda k: (-G[k]["now"]["L"], -((G[k]["now"].get("p2") or {}).get("ru") or -1e9), k))


def table(grp: str, G: dict, keys: dict | None) -> str:
    rows = []
    for k in _order(G):
        n = G[k]["now"]
        mem = n.get("mem") if grp == "tw" else None
        rows.append(_row(grp, k, n, (keys or {}).get(k), mem))
    return f'<div class="tw"><table class="bind bsort">{_head(grp)}<tbody>{"".join(rows)}</tbody></table></div>'


def _count(G: dict) -> dict:
    out: dict = {}
    for k, x in G.items():
        out.setdefault(x["now"]["L"], []).append(k)
    return out


def headline(I: dict) -> str:
    parts = []
    for grp, label in (("tw", "台股"), ("us", "美股"), ("ff", "美股")):
        G = I.get(grp) or {}
        if not G:
            continue
        c = _count(G)
        unit = {"tw": "個產業", "us": "個類股", "ff": "個細產業"}[grp]
        lab = f'{label} {len(G)} {unit}'
        if grp == "ff" and I.get("ff_last"):
            lab += f'（月資料到 {_ymd(I["ff_last"])}）'
        xs = []
        for lv in (4, 3, 2):
            ks = c.get(lv) or []
            if not ks:
                continue
            nm = "、".join(name_of(grp, k).split("（")[0] for k in sorted(ks)[:4])
            xs.append(f'{len(ks)} 個在等級 {lv}（{nm}{"等" if len(ks) > 4 else ""}）')
        parts.append(f'{lab}：' + ("、".join(xs) if xs else "沒有等級 2 以上"))
    return "；".join(parts) + "。"


def _vcell(e: dict | None) -> str:
    if not e or not e.get("n_hot"):
        return "—"
    return (f'{100 * e["p_hot"]:.0f}% ／ {100 * e["p_all"]:.0f}%<em>{_e(VERDICT.get(e.get("verdict"), "—"))}</em>')


def vtable(grp: str, R: dict, judge: bool) -> str:
    G = (R or {}).get(grp) or {}
    T = G.get("tests") or {}
    if not T:
        return '<p class="warn">驗證結果還沒產生（scripts/run_bubind.py）。</p>'
    tr = []
    for t in BI.TESTS[grp]:
        r = T.get(t) or {}
        e1, e2 = r.get("12") or {}, r.get("24") or {}
        if not e1.get("n_hot"):
            tr.append(f'<tr><td class="l" data-h="條件">{_e(TEST_NAMES[t])}</td><td data-h="成立的樣本">0</td>'
                      '<td data-h="一年內跌 20%">—</td><td data-h="兩年內跌 40%">—</td><td data-h="之後一年平均">—</td></tr>')
            continue
        ret = f'{_pct(e1.get("ret_hot"))} ／ {_pct(e1.get("ret_all"))}'
        c1, c2 = _vcell(e1), _vcell(e2)
        if not judge:
            c1, c2 = c1.split("<em>")[0], c2.split("<em>")[0]
        tr.append(f'<tr><td class="l" data-h="條件">{_e(TEST_NAMES[t])}</td>'
                  f'<td data-h="成立的樣本">{e1["n_hot"]:,}（{e1["n_epi"]} 段）</td>'
                  f'<td data-h="一年內跌 20%">{c1}</td><td data-h="兩年內跌 40%">{c2}</td><td data-h="之後一年平均">{_e(ret)}</td></tr>')
    return ('<div class="tw"><table class="stk bval"><tr><th class="l">條件</th><th>成立的樣本（時間段數）</th>'
            '<th>一年內跌 20%：成立 ／ 全部</th><th>兩年內跌 40%：成立 ／ 全部</th><th>之後一年平均報酬：成立 ／ 全部</th></tr>'
            f'{"".join(tr)}</table></div>')


def h1_line(R: dict) -> str:
    """主要假說 H1 一句話（美股 49 細產業 P2、兩年內跌 40%）。"""
    e = ((((R or {}).get("ff") or {}).get("tests") or {}).get("P2") or {}).get("24") or {}
    if not e.get("n_hot"):
        return ""
    return (f'美股 49 細產業 {_ymd(R["ff"]["a"])}～{_ymd(R["ff"]["z"])}：「兩年翻倍、比大盤多漲而且在高點」之後兩年內跌 40% 的比例 '
            f'{100 * e["p_hot"]:.0f}%，所有產業月份 {100 * e["p_all"]:.0f}%（{e["n_hot"]:,} 個產業月份、{e["n_epi"]} 段，'
            f'{VERDICT.get(e.get("verdict"), "—")}）。')


def valid_sec(R: dict) -> str:
    if not R:
        return ('<details class="bvd"><summary><b>驗證：產業條件成立之後比較容易大跌嗎？</b></summary>'
                '<p class="warn">驗證結果還沒產生（scripts/run_bubind.py）。</p></details>')
    ff, tw, us = R.get("ff") or {}, R.get("tw") or {}, R.get("us") or {}
    out = [f'<details class="bvd" id="indv"><summary><b>驗證：產業條件成立之後比較容易大跌嗎？</b><span class="bvh">{_e(h1_line(R))}</span></summary>']
    if ff:
        out.append(f'<h4>美股 49 細產業（Ken French，{_e(_ymd(ff["a"]))}～{_e(_ymd(ff["z"]))}，{ff.get("n_ind")} 個產業；判定）</h4>'
                   + vtable("ff", R, True))
    if tw:
        out.append(f'<h4>台股產業（{_e(_ymd(tw["a"]))}～{_e(_ymd(tw["z"]))}，{tw.get("n_ind")} 個產業；樣本太短，只描述）</h4>'
                   + vtable("tw", R, False))
    if us:
        out.append(f'<h4>美股類股 ETF（{_e(_ymd(us["a"]))}～{_e(_ymd(us["z"]))}，{us.get("n_ind")} 檔；樣本太短，只描述）</h4>'
                   + vtable("us", R, False))
    out.append('<p class="note">每個產業每個月一個樣本；跌幅用月底收盤（之後 12、24 個月內，高點到之後低點）。'
               '判定：成立的樣本 ≥ 12、時間上 ≥ 4 段（同一段時間好幾個產業一起熱只算一段），差的 95% 區間'
               '（以月份為單位、12 個月一塊重抽，那幾個月所有產業一起抽）不含 0，而且前後兩半同方向。平均報酬只描述。</p></details>')
    return "".join(out)


NOTE = ('產業泡沫看的是「這個產業比整個市場熱」：兩年翻倍另外要比大盤多漲 50 個百分點（整個市場熱看上面的市場等級）。'
        '各組能判定的條件不同，最高等級也不同：台股產業 4（價格、營收比值、未來獲利、換手率）、'
        '美股類股 3（價格、未來獲利）、美股 49 細產業 2（只有價格與家數）。「成立的條件」只列現在成立的；點一列看說明、歷史等級與指數。')


def section(I: dict, R: dict | None, keys: dict) -> str:
    """keys＝{"tw": {產業: 圖的鍵}, "us": {ETF: 鍵}}。"""
    if not I or not (I.get("tw") or I.get("us") or I.get("ff")):
        return ('<section class="sec" id="ind"><h2>產業泡沫</h2><p class="warn">產業泡沫還算不出來'
                + (f'（{_e(I.get("tw_err"))}）' if I and I.get("tw_err") else "") + '。</p></section>')
    sub = "・".join(x for x in (f'台股 {len(I["tw"])} 個產業' if I.get("tw") else "",
                                 f'美股 {len(I["us"])} 個類股' if I.get("us") else "",
                                 f'美股 {len(I["ff"])} 個細產業' if I.get("ff") else "") if x)
    out = [f'<section class="sec cd" id="ind"><div class="ch"><h2>產業泡沫<span class="sub">{_e(sub)}</span></h2></div>',
           f'<p class="bsum">{_e(headline(I))}</p><p class="note">{_e(NOTE)}</p>']
    if I.get("tw"):
        out.append('<h3>台股產業</h3>' + table("tw", I["tw"], keys.get("tw")))
        out.append('<p class="note">產業指數＝前一個月底市值 40 億以上的股票、依前月底市值加權、含息；產業別用證交所／櫃買中心現在的分類（「其他」不算）；已下市公司用它下市前最後一次的官方分類（2013 年起每年第一個交易日的分類行情）。'
                   '價格漲得比營收快＝產業市值 ÷ 近 12 個月營收的比值也在爆發；未來獲利有分析師預估的用預估（Yahoo），'
                   '沒有的用產業營收（替代資料）；換手率要 2023 年起才有 10 年歷史可比。</p>')
    elif I.get("tw_err"):
        out.append(f'<p class="warn">台股產業還算不出來（{_e(I["tw_err"])}）。</p>')
    if I.get("us"):
        out.append('<h3>美股類股</h3>' + table("us", I["us"], keys.get("us")))
        out.append('<p class="note">SPDR 類股 ETF 收盤（不含股利）、比大盤用 SPY；未來獲利＝S&amp;P 500 成分股依 GICS 類別加總分析師預估。'
                   '半導體看上面的費半。</p>')
    if I.get("ff"):
        out.append(f'<details class="bvd"><summary><b>美股 49 細產業（Ken French，月資料到 {_e(_ymd(I["ff_last"]))}）</b>'
                   f'<span class="bvh">價格與家數；最高到等級 2。</span></summary>' + table("ff", I["ff"], None)
                   + '<p class="note">Ken French 49 產業的價值加權報酬（不含股利）；比大盤用 49 個產業依市值加權；'
                     '新公司＝家數 12 個月增加率在自己過去的第 90 百分位以上。資料約晚一個半月。</p></details>')
    out.append(valid_sec(R))
    out.append('</section>')
    return "".join(out)


def hist_data(I: dict) -> tuple[dict, dict]:
    """→ (圖的資料 {鍵: {d, L, c, p}}, keys {"tw": {產業: 鍵}, "us": {...}})。燃料的條件碼改成 h（換手率），不和市場層級的槓桿混。"""
    data, keys = {}, {"tw": {}, "us": {}}
    for grp, pre in (("tw", "@t"), ("us", "@u")):
        for j, k in enumerate(sorted(I.get(grp) or {})):
            h = (I[grp][k] or {}).get("hist")
            if not h or not h.get("d"):
                continue
            key = f"{pre}{j}"
            keys[grp][k] = key
            data[key] = {"d": h["d"], "L": h["L"], "c": [c.replace("f", "h") for c in h["c"]], "p": h["p"]}
    return data, keys


CSS = """
table.bind td em{display:block;font-style:normal;font-size:11.5px;color:var(--mut)}
table.bind .lvn{font-size:12px}table.bind td .sub{display:block;font-size:11.5px;color:var(--mut);margin:0}
table.bind tr.bir{cursor:pointer}table.bind tr.bir:hover td{background:var(--sbg)}
table.bind tr.bir td:first-child::before{content:"▸ ";color:var(--mut)}table.bind tr.bir.open td:first-child::before{content:"▾ "}
table.bind tr.bid td{background:var(--panel);white-space:normal}table.bind tr.bid .bsum{font-size:13px;margin:2px 0 6px}
table.bind th[data-si]{cursor:pointer}
table.bind th[data-si].asc::after{content:" ▲";font-size:10px}table.bind th[data-si].desc::after{content:" ▼";font-size:10px}
table.bind .bcs i{white-space:nowrap}table.bind .bcs i.nil{border:0;padding:0}
table.bind .nw{white-space:nowrap}table.bind .bcs.mob{display:none}table.bind td.bcc .bcs{flex-wrap:nowrap}
@media (max-width:640px){
 table.bind .dsk{display:none}
 table.bind th,table.bind td{padding:6px 5px}
 table.bind td.bnm{white-space:normal;min-width:7em}table.bind td.bnm .bcs.mob{display:flex;margin-top:3px}
 table.bind .lvn{display:block}
 table.bind td.bcc,table.bind td em{white-space:normal}
}
"""

JS = r"""
(function(){
function sortTable(th){
  const table = th.closest('table'), tb = table.tBodies[0], i = +th.dataset.si;
  const dir = th.classList.contains('desc') ? 1 : -1;
  table.querySelectorAll('th[data-si]').forEach(x => x.classList.remove('asc', 'desc'));
  th.classList.add(dir === 1 ? 'asc' : 'desc');
  const rows = [...tb.rows].filter(r => !r.classList.contains('bid'));
  const val = r => { const c = r.cells[i]; const v = c ? c.dataset.v : ''; if (v === undefined || v === '') return null; const x = +v; return isNaN(x) ? v : x; };
  rows.sort((a, b) => { const x = val(a), y = val(b);
    if (x === null && y === null) return 0; if (x === null) return 1; if (y === null) return -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'zh-Hant') : x - y) * dir; });
  rows.forEach(r => { const d = r.nextElementSibling && r.nextElementSibling.classList.contains('bid') ? r.nextElementSibling : null;
    tb.appendChild(r); if (d) tb.appendChild(d); });
}
function toggle(tr){
  const d = tr.nextElementSibling;
  if (!d || !d.classList.contains('bid')) return;
  d.hidden = !d.hidden; tr.classList.toggle('open', !d.hidden);
  if (!d.hidden && window.bubDraw) window.bubDraw(tr.dataset.k);
}
document.addEventListener('click', e => {
  const th = e.target.closest('table.bsort th[data-si]');
  if (th){ sortTable(th); return; }
  const tr = e.target.closest('tr.bir');
  if (tr) toggle(tr);
});
document.addEventListener('keydown', e => {
  const tr = e.target.closest && e.target.closest('tr.bir');
  if (tr && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); toggle(tr); }
});
})();
"""
