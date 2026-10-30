"""個股報告頁（docs/lab_equity_report_plan.md 第 4、11 節）：報告文字（eqreport.parse）＋資料包（eqfacts）→ 一頁 HTML。

撰寫者只寫文字；評等框、圖、表、方法、免責聲明由這裡依資料包放進去，所以每一份報告的版面、圖號、算法說明都一樣。
頁面放 dashboard/rp/{tw|us}-{代號}.html，用 <base href="../"> 讓頂欄與其他連結照樣指到網站根目錄。
列印：A4、每段從新頁開始的地方事先排好；存 PDF＝瀏覽器「列印 → 儲存為 PDF」。
「目標價」「評等」只准出現在個股報告（wiki/ops/content-rules.md 第三個例外；tests/test_eqpage.py 守）。
"""
from __future__ import annotations

import re
from html import escape
from urllib.parse import quote

from . import eqchart as C
from . import eqreport as R
from . import eqspec as S

DISCLAIMER = ("本報告由程式依公開資料與本站固定規則產生，文字由 AI 協助撰寫並經程式檢查數字；評等與目標價依本站規則"
              "（每股盈餘或每股淨值 × 同一把尺的目標倍數，評等依上檔空間）計算，僅供研究參考，不構成任何投資建議或買賣邀約。"
              "股價可能大幅波動，過去的成績不代表未來，請自行判斷並承擔風險。")
RATING_CLS = {"買進": "rb", "中立": "rn", "減碼": "rs", "暫不評等": "rx"}
SEC_ID = {"投資論點": "thesis", "風險": "risk", "公司概況": "co", "產業與競爭": "ind", "財務分析": "fin", "同業比較": "peer",
          "估值": "val", "催化劑與籌碼": "cat", "為什麼被選上": "why", "資料來源": "src"}
MK_NAME = {"tw": "台股", "us": "美股"}


# ── 小工具 ───────────────────────────────────────────────────────────────

def f(v, d=None, unit=""):
    if v is None:
        return "—"
    return C.fmt(v, d) + unit


def sg(v, d=1, unit="%"):
    if v is None:
        return "—"
    return ("+" if v > 0 else "") + C.fmt(v, d) + unit


def md(text: str) -> str:
    """撰寫者的文字 → HTML：### 小標、■ 重點、- 條列、段落、**粗體**、[連結](網址)。先跳脫再套格式。"""
    def inline(s: str) -> str:
        s = escape(s, quote=False)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                   lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}" target="_blank" rel="noopener">{m.group(1)}</a>', s)   # 網址已跳脫過一次（& → &amp;），不再跳脫
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return s
    out, ul = [], False
    for para in R.paragraphs(text):
        if para.startswith("### "):
            if ul:
                out.append("</ul>")
                ul = False
            out.append(f"<h3>{inline(para[4:])}</h3>")
        elif para.startswith("- ") or para.startswith("* "):
            if not ul:
                out.append("<ul>")
                ul = True
            out.append(f"<li>{inline(para[2:])}</li>")
        elif para.startswith("■"):
            if ul:
                out.append("</ul>")
                ul = False
            out.append(f'<p class="hl"><span class="sq" aria-hidden="true">■</span>{inline(para[1:].strip())}</p>')
        else:
            if ul:
                out.append("</ul>")
                ul = False
            out.append(f"<p>{inline(para)}</p>")
    if ul:
        out.append("</ul>")
    return "".join(out)


class Figs:
    def __init__(self):
        self.n = 0

    def fig(self, title: str, svg: str, src: str, cls: str = "") -> str:
        if not svg:
            return ""
        self.n += 1
        return (f'<figure class="fig {cls}" id="fig{self.n}"><figcaption><b>圖 {self.n}</b>　{escape(title)}</figcaption>'
                f'{svg}<div class="fsrc">資料來源：{escape(src)}</div></figure>')

    def tab(self, title: str, html: str, src: str, extra: str = "") -> str:
        self.n += 1
        return (f'<figure class="fig tbl" id="fig{self.n}"><figcaption><b>表 {self.n}</b>　{escape(title)}{extra}</figcaption>'
                f'<div class="tw">{html}</div><div class="fsrc">資料來源：{escape(src)}</div></figure>')


def _ql(q: str) -> str:
    return f"{q[2:4]}Q{(int(q[5:7]) - 1) // 3 + 1}"


def _safe_url(u) -> str:
    """只放行 http(s) 網址（資料包的連結來自外部，javascript:／data: 一律不當連結；2026-10-30 資安檢查）。"""
    u = str(u or "").strip()
    return u if re.match(r"https?://", u, re.I) else ""


def _table(head: list[str], rows: list[list[str]], cls: str = "") -> str:
    h = "".join(f"<th>{escape(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="dt {cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'


# ── 各區塊 ───────────────────────────────────────────────────────────────

SRC_CO = "公開資訊觀測站財報（每季）、證交所與櫃買中心"
SRC_MO = "公開資訊觀測站月營收"
SRC_PX = "證交所、櫃買中心每日收盤"
SRC_FC = "FactSet（鉅亨網台股預估）、Yahoo Finance"
US_SRC = {"co": "SEC 財報（第一次公布；第四季＝全年 − 前三季）", "px": "Yahoo Finance 收盤（最近一年每天、更早每週）",
          "fc": "Yahoo Finance 分析師（多為調整後 EPS）", "mo": ""}


def _us(pack: dict) -> bool:
    return pack.get("mk") == "us"


def _cu(pack: dict) -> tuple[str, str]:
    """（股價單位, 金額單位）。"""
    return ("美元", "億美元") if _us(pack) else ("元", "億元")


def _src(pack: dict, k: str) -> str:
    return US_SRC[k] if _us(pack) else {"co": SRC_CO, "mo": SRC_MO, "px": SRC_PX, "fc": SRC_FC}[k]


def rating_box(pack: dict, val: dict) -> str:
    px = pack.get("px") or {}
    cons = pack.get("cons") or {}
    ct = cons.get("tp") or {}
    cu, am = _cu(pack)
    pd = 2 if _us(pack) else None                     # 美股股價寫到美分
    rows = [("收盤價", f"{f(px.get('c'), pd)} {cu}（{(px.get('d') or '')[5:].replace('-', '/')}）"),
            ("上檔空間", sg(val.get("up"))),
            ("52 週收盤區間" if px.get("close52") else "52 週區間", f"{f(px.get('lo52'), pd)}～{f(px.get('hi52'), pd)} {cu}"),
            ("市值", f"{f(pack.get('cap'), 0)} {am}"),
            ("目標價 ÷ " + ("未來 12 個月 EPS" if val.get("basis") == "fwd" else "每股近四季淨利" if _us(pack) else "近四季 EPS"),
             f"{f(val.get('tp_pe'), 1)} 倍" if val.get("tp_pe") else "—"),
            ("法人共識目標價" + (f"（{cons.get('stat')}）" if cons.get("stat") else ""),
             f"{f(ct.get('v'), pd)} {cu}（{ct.get('n') or '—'} 位）" if ct.get("v") else "—")]
    r = val.get("rating") or "暫不評等"
    tp = val.get("tp")
    body = "".join(f"<div><dt>{escape(a)}</dt><dd>{escape(b)}</dd></div>" for a, b in rows)
    return (f'<aside class="rbox"><div class="rt {RATING_CLS.get(r, "rx")}"><span>評等</span><b>{escape(r)}</b></div>'
            f'<div class="tpb"><span>目標價（12 個月）</span><b>{f(tp)} {cu}</b></div><dl>{body}</dl></aside>')


def summary_table(pack: dict) -> str:
    ys = (pack.get("y") or [])[-3:]
    cons = pack.get("cons") or {}
    px = (pack.get("px") or {}).get("c")
    cy = int((pack.get("asof") or "2000")[:4])
    cols = [(y["y"] + "A", y, None) for y in ys]
    prev_rev = ys[-1]["rev"] if ys else None
    for yy in (cy, cy + 1):
        e = (cons.get("eps") or {}).get(str(yy))
        if e and str(yy) not in {y["y"] for y in ys}:
            cols.append((f"{yy}E", None, e))
    head = ["", *[c[0] for c in cols]]
    rows = []

    def row(name, fa, fe):
        rows.append([escape(name)] + [fa(a) if a else fe(e) for _, a, e in cols])
    pe_rev = {}
    last = prev_rev
    for lab, a, e in cols:
        if e and e.get("rev") is not None:
            pe_rev[lab] = (e["rev"] / last - 1) * 100 if last else None
            last = e["rev"]
    row("營收（億元）", lambda a: f(a["rev"], 0), lambda e: f(e.get("rev"), 0))
    rows[-1] = rows[-1]
    rows.append(["營收年增"] + [sg(a["rev_yoy"]) if a else sg(pe_rev.get(lab)) for lab, a, e in cols])
    row("毛利率", lambda a: f(a["gm"], 1, "%"), lambda e: "—")
    row("營益率", lambda a: f(a["om"], 1, "%"), lambda e: "—")
    row("稅後淨利（億元）", lambda a: f(a["nip"], 1), lambda e: "—")
    row("EPS（元）", lambda a: f(a["eps"], 2), lambda e: f(e.get("med"), 2))
    ye = {r[0][:4]: r[1] for r in ((pack.get("val") or {}).get("band") or {}).get("rows") or [] if r[0].endswith("-12") and r[1]}
    row("本益比（倍）", lambda a: f(ye[a["y"]] / a["eps"], 1) if a["eps"] and a["eps"] > 0 and ye.get(a["y"]) else "—",
        lambda e: f(px / e["med"], 1) if e.get("med") and e["med"] > 0 and px else "—")
    row("ROE", lambda a: f(a["roe"], 1, "%"), lambda e: "—")
    row("每股現金股利（元）", lambda a: f(a["dps"], 2), lambda e: "—")
    note = (f"A＝實際；E＝法人共識（{escape(cons.get('src') or '')}，{cons.get('n') or '—'} 位，{escape(cons.get('d') or '')}）。"
            "本益比：實際年度＝當年 12 月底收盤 ÷ 當年 EPS，預估年度＝報告日收盤 ÷ 共識 EPS。股利＝當年除息。") if any(e for _, _, e in cols) \
        else "A＝實際。本益比＝當年 12 月底收盤 ÷ 當年 EPS。股利＝當年除息。"
    return _table(head, rows, "sum") + f'<p class="tn">{note}</p>'


def summary_table_us(pack: dict) -> str:
    """美股：財報（SEC）和法人預估（Yahoo，多為調整後）分兩列寫，不放在同一列比。"""
    ys = (pack.get("y") or [])[-3:]
    cons = pack.get("cons") or {}
    px = (pack.get("px") or {}).get("c")
    fe = int(pack.get("fy_end") or 12)
    cols = [(f"FY{y['y']}A", y, None) for y in ys]
    for yy, e in sorted((cons.get("eps") or {}).items()):
        if yy not in {y["y"] for y in ys}:
            cols.append((f"FY{yy}E", None, e))
    ye = {r[0][:4]: r[1] for r in ((pack.get("val") or {}).get("band") or {}).get("rows") or [] if r[0][5:7] == f"{fe:02d}" and r[1]}
    rows = []

    def row(name, fa, fe_=lambda e: "—"):
        rows.append([escape(name)] + [fa(a) if a else fe_(e) for _, a, e in cols])
    last = ys[-1]["rev"] if ys else None
    gr = {}
    for lab, a, e in cols:
        if e and e.get("rev") is not None:
            gr[lab] = (e["rev"] / last - 1) * 100 if last else None
            last = e["rev"]
    row("營收（億美元）", lambda a: f(a["rev"], 2), lambda e: f(e.get("rev"), 1))
    rows.append(["營收年增"] + [sg(a["rev_yoy"]) if a else sg(gr.get(lab)) for lab, a, e in cols])
    row("毛利率", lambda a: f(a["gm"], 1, "%"))
    row("營益率", lambda a: f(a["om"], 1, "%"))
    row("稅後淨利（億美元）", lambda a: f(a["nip"], 2))
    row("EPS（財報，美元）", lambda a: f(a["eps"], 2))
    row("EPS（法人預估，美元）", lambda a: "—", lambda e: f(e.get("med"), 2))
    row("本益比（財報 EPS，年度最後一個月收盤）", lambda a: f(ye[a["y"]] / a["eps"], 1) if a["eps"] and a["eps"] > 0 and ye.get(a["y"]) else "—")
    row("本益比（法人預估 EPS，報告日收盤）", lambda a: "—", lambda e: f(px / e["med"], 1) if e.get("med") and e["med"] > 0 and px else "—")
    row("ROE", lambda a: f(a["roe"], 1, "%"))
    row("每股現金股利（美元）", lambda a: f(a["dps"], 3) if a.get("dps") else "—")
    head = ["", *[c[0] for c in cols]]
    note = (f"A＝SEC 財報（第一次公布）；E＝{escape(cons.get('src') or '')} 分析師{escape(cons.get('stat') or '')}（{cons.get('n') or '—'} 位，"
            f"{escape(cons.get('d') or '')}），多為調整後 EPS，和財報 EPS 不能直接比。會計年度到 {fe} 月。股利＝那個會計年度除息的合計。")
    return _table(head, rows, "sum") + f'<p class="tn">{note}</p>'


def fin_section(pack: dict, F: Figs) -> str:
    qs = pack.get("q") or []
    mo = pack.get("mo") or []
    ys = pack.get("y") or []
    out = []
    us = _us(pack)
    cu, am = _cu(pack)
    sco = _src(pack, "co")
    ql = [_ql(q["q"]) for q in qs]
    # 圖兩欄排（列印也是），表另外整寬；沒有資料的圖不放（美股沒有月營收與現金流）
    out.append(F.fig("每季營收與年增率", C.bars_yoy(ql, [q["rev"] for q in qs], [q["rev_yoy"] for q in qs], unit=am,
                                              label="每季營收"), sco))
    if mo:
        ml = [o["ym"][2:].replace("-", "/") for o in mo]
        out.append(F.fig("每月營收與年增率", C.bars_yoy(ml, [o["rev"] for o in mo], [o["rev_yoy"] for o in mo], label="每月營收"), SRC_MO))
    out.append(F.fig("毛利率、營益率、淨利率", C.lines(ql, [("k1", "毛利率", [q["gm"] for q in qs]), ("k2", "營益率", [q["om"] for q in qs]),
                                                ("k3", "淨利率" if us else "淨利率（歸屬母公司）", [q["nm"] for q in qs])], label="三率"), sco))
    l4 = "近四季淨利 ÷ 當時流通股數" if us else "近四季 EPS"
    out.append(F.fig("每季 EPS 與" + l4, C.bars_line(ql, ("k1", "每季 EPS（財報）" if us else "每季 EPS", [q["eps"] for q in qs]),
                                                  ("k2", l4, [q.get("eps4") for q in qs]), unit=cu, label="EPS"), sco))
    yl = [("FY" if us else "") + y["y"] for y in ys]
    out.append(F.fig("年度 EPS 與每股現金股利", C.grouped_bars(yl, [("k1", "EPS", [y["eps"] for y in ys]),
                                                              ("k2", "現金股利（會計年度內除息）" if us else "現金股利（當年除息）", [y["dps"] for y in ys])],
                                                       unit=cu, label="年度 EPS"), sco + ("；股利：Yahoo Finance" if us else "；股利：證交所、櫃買中心除權息")))
    if any(y.get("fcf") is not None for y in ys):
        out.append(F.fig("年度現金流", C.grouped_bars(yl, [("k1", "營業現金流", [y["ocf"] for y in ys]), ("k2", "投資現金流", [y["icf"] for y in ys]),
                                                    ("k3", "營業＋投資", [y["fcf"] for y in ys])], unit=am, label="現金流"), sco))
    if us:
        out.append(F.fig("流通股數", C.grouped_bars(ql, [("k1", "流通股數（百萬股）", [q.get("sh") for q in qs])], unit="百萬股", label="流通股數"),
                         "SEC 財報封面的流通股數（第一次公布）"))
    out = ['<div class="fgrid">' + "".join(out) + "</div>"]
    head = ["", *ql[-8:]]
    q8 = qs[-8:]
    rows = [[f"營收（{am}）", *[f(q["rev"], 2 if us else 1) for q in q8]], ["年增", *[sg(q["rev_yoy"]) for q in q8]],
            ["毛利率", *[f(q["gm"], 1, "%") for q in q8]], ["營益率", *[f(q["om"], 1, "%") for q in q8]],
            ["淨利率", *[f(q["nm"], 1, "%") for q in q8]], [f"EPS（{cu}）", *[f(q["eps"], 2) for q in q8]],
            ["EPS 年增", *[sg(q["eps_yoy"]) for q in q8]], ["近四季 ROE", *[f(q.get("roe4"), 1, "%") for q in q8]]]
    if us:
        rows += [["近四季淨利（億美元）", *[f(q.get("ni4"), 2) for q in q8]], ["流通股數（百萬股）", *[f(q.get("sh"), 2) for q in q8]],
                 ["每股淨值（美元）", *[f(q.get("bvps"), 2) for q in q8]]]
    else:
        rows += [["營業現金流（億元）", *[f(q["ocf"], 1) for q in q8]], ["營業＋投資（億元）", *[f(q["fcf"], 1) for q in q8]],
                 ["負債比", *[f(q["dr"], 1, "%") for q in q8]], ["流動比", *[f(q["cr"], 0, "%") for q in q8]]]
    out.append(F.tab("最近 8 季損益" + ("與股數" if us else "與現金流"), _table(head, rows, "q8"), sco))
    return "".join(out)


def peer_section(pack: dict, F: Figs) -> str:
    ps = pack.get("peers") or []
    me = pack.get("peer_me") or {}
    us = _us(pack)
    if us:
        cols = [("cap", "市值（億美元）", 0), ("r1y", "近一年漲跌", "pct"), ("pe", "本益比（市值 ÷ 近四季淨利）", 1),
                ("fpe", "未來 12 個月本益比", 1), ("rq", "最新一季營收年增", "pct1"), ("om", "營益率（近四季）", "p1"), ("roe", "ROE（近四季）", "p1")]
    else:
        cols = [("cap", "市值（億元）", 0), ("px", "股價（元）", None), ("r1y", "近一年漲跌", "pct"), ("pe", "本益比（近四季）", 1),
                ("fpe", "預估本益比", 1), ("pb", "淨值比", 2), ("yld", "殖利率", "p2"), ("ry3", "近 3 月營收年增", "pct"),
                ("gm", "毛利率", "p1"), ("om", "營益率", "p1"), ("roe", "ROE（近四季）", "p1")]

    def cell(v, d):
        if d == "pct":
            return sg(v, 0)
        if d == "pct1":
            return sg(v, 1)
        if d == "p1":
            return f(v, 1, "%")
        if d == "p2":
            return f(v, 2, "%")
        return f(v, d)
    head = ["公司", *[c[1] for c in cols]]
    rows = []
    for p in [me] + ps:
        nm = f"<b>{escape(p.get('n') or '')}</b>" if p is me else escape(p.get("n") or "")
        rows.append([f'{nm} <span class="cd">{escape(p.get("c") or "")}</span>'] + [cell(p.get(k), d) for k, _, d in cols])
    def med(k):                                       # 本益比不含虧損或超過 BAND_PE_MAX 倍（和倍數範圍同一個規則；舊報告也照這樣顯示）
        v = sorted(p[k] for p in ps if p.get(k) is not None and (k not in ("pe", "fpe") or 0 < p[k] <= S.BAND_PE_MAX))
        return round(S.pctl(v, 0.5), 2) if v else None
    rows.append(["同業中位數"] + [cell(med(k), d) for k, _, d in cols])
    csv = ["代號,公司," + ",".join(c[1] for c in cols)]
    for p in [me] + ps:
        csv.append(",".join([str(p.get("c") or ""), str(p.get("n") or "")] + ["" if p.get(k) is None else str(p.get(k)) for k, _, _ in cols]))
    href = "data:text/csv;charset=utf-8," + quote("﻿" + "\n".join(csv))
    dl = f' <a class="csv" href="{href}" download="{escape(pack.get("code") or "")}-同業比較.csv">下載 CSV</a>'
    how = pack.get("peer_how") or ""
    sd = pack.get("src_d") or {}
    if us:
        note = (f"同業：S&P 1500 裡和本公司同一個 GICS 細產業（{pack.get('ind') or ''}，{pack.get('peer_n') or '—'} 家）中市值最接近的。"
                f"同業的市值、本益比、營收年增是 {sd.get('scr') or ''} 那一週的（SEC 財報＋篩選器市值）；本公司那一列用報告日收盤。"
                "未來 12 個月本益比＝股價 ÷ Yahoo 分析師未來 12 個月 EPS（3 位以上才列，多為調整後）。"
                f"同業中位數的本益比不含虧損或超過 {int(S.BAND_PE_MAX)} 倍的公司（和倍數範圍同一個規則）。")
        srcs = f"{US_SRC['co']}、{US_SRC['fc']}、維基百科 S&P 1500 成分股表"
    else:
        note = ("同業：" + ("櫃買中心產業鏈同一節點的上市櫃公司，市值最大的兩家加上共同節點多、市值接近的" if how == "產業鏈"
                           else "證交所產業別裡市值最接近的") + "。預估本益比＝收盤 ÷ 法人共識未來 12 個月 EPS（3 位以上才列）。"
                f"同業中位數的本益比不含虧損或超過 {int(S.BAND_PE_MAX)} 倍的公司（和倍數範圍同一個規則）。")
        srcs = f"{SRC_PX}、{SRC_CO}、{SRC_FC}"
    out = [F.tab("同業比較", _table(head, rows, "peer"), srcs, dl) + f'<p class="tn">{escape(note)}</p>']
    fwd = (pack.get("val") or {}).get("basis") == "fwd"
    key, ylab = ("fpe", "未來 12 個月本益比（法人共識）") if fwd else ("pe", "本益比（市值 ÷ 近四季淨利）" if us else "本益比（近四季）")
    xk, xlab = ("rq", "最新一季營收年增（%）") if us else ("ry3", "近 3 個月營收年增（%）")
    pts, miss = [], []
    for p in ps + [me]:
        y = p.get(key)
        if y is not None and p.get(xk) is not None and 0 < y <= S.BAND_PE_MAX:
            pts.append((p.get("n"), p.get(xk), y, "k2" if p is me else "k1"))
        else:
            miss.append(p.get("n") or p.get("c") or "")
    src = (f"{US_SRC['co']}、{US_SRC['fc']}" if us else (f"{SRC_MO}、{SRC_FC}" if fwd else f"{SRC_MO}、{SRC_CO}、{SRC_PX}"))
    if miss:
        src += "；沒畫：" + "、".join(miss) + ("（沒有 3 位以上分析師的共識）" if fwd else f"（虧損或超過 {int(S.BAND_PE_MAX)} 倍）")
    out.append(F.fig("同業：營收成長與本益比", C.scatter(pts, xlab, ylab, label="同業散佈"), src))
    return "".join(out)


def val_section(pack: dict, val: dict, fm: dict, F: Figs) -> str:
    v = pack.get("val") or {}
    us = _us(pack)
    cu, am = _cu(pack)
    e4lab = "每股近四季淨利" if us else "近四季 EPS"
    band = v.get("band") or {}
    rows = band.get("rows") or []
    out = []
    labs = [r[0][2:].replace("-", "/") for r in rows]
    tp = val.get("tp")
    rv = []
    meth = v.get("method")                            # 只畫實際用的那把尺（本益比法不畫淨值比，反之亦然）
    if meth == "pe" and band.get("pe", {}).get("n"):
        b = band["pe"]
        rv.append(F.fig(f"本益比區間（近 {S.BAND_YEARS} 年，" + ("市值 ÷ 近四季淨利）" if us else "近四季 EPS）"),
                         C.river(labs, [r[1] for r in rows], [r[2] for r in rows], [b["p25"], b["p50"], b["p75"]], unit=cu, label="本益比區間", name="本益比", tp=tp),
                         _src(pack, "co") + "、月底收盤"))
    if meth == "pb" and band.get("pb", {}).get("n"):
        b = band["pb"]
        rv.append(F.fig(f"淨值比區間（近 {S.BAND_YEARS} 年）",
                         C.river(labs, [r[1] for r in rows], [r[3] for r in rows], [b["p25"], b["p50"], b["p75"]], unit=cu, label="淨值比區間", name="淨值比", tp=tp),
                         _src(pack, "co") + "、月底收盤"))
    out += rv
    base = v.get("base")
    fb = []
    pe_b, pp, pf = band.get("pe") or {}, v.get("peer_pe") or {}, v.get("peer_fpe") or {}
    bv = v.get("bvps")
    e4, f12e = v.get("eps4"), (v.get("f12m") or {}).get("eps")
    # 每一條都是「同一把尺的倍數 × 同一把尺的 EPS」（eqspec VER 2）；倍數寫在圖下的說明
    mults = []
    if meth == "pe" and f12e and f12e > 0 and pf.get("n", 0) >= S.PEER_MIN:
        fb.append(("同業未來本益比 × 未來 12 個月 EPS", f12e * pf["p25"], f12e * pf["p75"], f12e * pf["p50"]))
        mults.append(f"同業未來本益比 {f(pf['p25'], 1)}～{f(pf['p75'], 1)} 倍")
    if meth == "pe" and e4 and e4 > 0 and pe_b.get("n"):
        fb.append((f"本公司本益比 × {e4lab}", e4 * pe_b["p25"], e4 * pe_b["p75"], e4 * pe_b["p50"]))
        mults.append(f"本公司近 {S.BAND_YEARS} 年本益比 {f(pe_b['p25'], 1)}～{f(pe_b['p75'], 1)} 倍")
    if meth == "pe" and e4 and e4 > 0 and pp.get("n", 0) >= S.PEER_MIN:
        fb.append((f"同業本益比 × {e4lab}", e4 * pp["p25"], e4 * pp["p75"], e4 * pp["p50"]))
        mults.append(f"同業本益比（近四季）{f(pp['p25'], 1)}～{f(pp['p75'], 1)} 倍")
    pb_b, ppb = band.get("pb") or {}, v.get("peer_pb") or {}
    if meth == "pb" and bv and pb_b.get("n"):
        fb.append(("本公司淨值比 × 每股淨值", bv * pb_b["p25"], bv * pb_b["p75"], bv * pb_b["p50"]))
        mults.append(f"本公司淨值比 {f(pb_b['p25'], 2)}～{f(pb_b['p75'], 2)} 倍")
    if meth == "pb" and bv and ppb:
        fb.append(("同業淨值比 × 每股淨值", bv * ppb["p25"], bv * ppb["p75"], bv * ppb["p50"]))
        mults.append(f"同業淨值比 {f(ppb['p25'], 2)}～{f(ppb['p75'], 2)} 倍")
    ct = (pack.get("cons") or {}).get("tp") or {}
    if ct.get("lo") and ct.get("hi"):
        fb.append(("法人目標價（最低～最高）", ct["lo"], ct["hi"], ct.get("v")))
    px = pack.get("px") or {}
    fb.append(("52 週收盤" if px.get("close52") else "52 週股價", px.get("lo52"), px.get("hi52"), None))
    sc = val.get("scen")
    if sc:
        fb.append(("本報告情境（悲觀～樂觀）", sc["bear"], sc["bull"], sc["base"]))
    out.append(F.fig("估值區間", C.football(fb, px.get("c"), tp, unit=cu),
                     "本站整理（區間＝第 25～75 百分位，直線＝中位數）" + ("；" + "、".join(mults) if mults else "")))
    f12 = v.get("f12m") or {}
    rng = val.get("range") or {}
    nm = "本益比" if meth == "pe" else "淨值比"
    why_ttm = f"沒有 {S.CONS_MIN} 位以上分析師的共識，或同業有共識的不到 {S.PEER_MIN} 家"
    lq = (pack.get("q") or [{}])[-1]
    if meth == "pe" and v.get("basis") == "ttm" and us:
        brow = [["近四季淨利 ÷ 最新流通股數", f"{f(base, 2)} 美元",
                 f"近四季淨利 {f(lq.get('ni4'), 2)} 億美元 ÷ {f(pack.get('shares'), 3)} 百萬股（財報到 {escape(_ql(v.get('eps4_q') or ''))}）；{why_ttm}"]]
    elif meth == "pe" and v.get("basis") == "ttm":
        brow = [["近四季 EPS", f"{f(base, 2)} 元", f"已公布的最近四季（到 {escape(_ql(v.get('eps4_q') or ''))}）；{why_ttm}"]]
    elif meth == "pe":
        how = (f"法人共識：{f12.get('y')} 年 {f(f12.get('eps_y'), 2)} 元 × {f((f12.get('w') or 0) * 12, 0)}/12 ＋ "
               f"{(f12.get('y') or 0) + 1} 年 {f(f12.get('eps_y1'), 2)} 元 × {f((1 - (f12.get('w') or 0)) * 12, 0)}/12（{f12.get('n')} 位）")
        brow = [["未來 12 個月 EPS", f"{f(base, 2)} {cu}", escape(how) + ("；多為調整後 EPS" if us else "")]]
    else:
        brow = [["每股淨值（最近一季）", f"{f(base, 2)} {cu}", "最新一季財報"]]
    t_rows = brow + [
        [f"可用{nm}範圍", f"{f(rng.get('lo'), 2)}～{f(rng.get('hi'), 2)} 倍",
         escape(v.get("range_how") or "本公司近 5 年與同業現在的第 25～75 百分位，取最寬")],
        [f"預設{nm}", f"{f(rng.get('dflt'), 2)} 倍", escape(v.get("dflt_how") or "本公司中位數與同業中位數的平均")],
        [f"本報告採用{nm}", f"<b>{f(val.get('mult'), 2)} 倍</b>", escape(str(fm.get("mult_why") or "照預設"))],
        ["目標價", f"<b>{f(tp)} {cu}</b>", f"{f(base, 2)} × {f(val.get('mult'), 2)}，依價位進位"],
        ["上檔空間", sg(val.get("up")), f"報告日收盤 {f(px.get('c'), 2 if us else None)} {cu}"],
        ["評等", f"<b>{escape(val.get('rating') or '')}</b>", f"上檔空間 ≥ {int(S.BUY_UP * 100)}% 買進、≤ {int(S.SELL_DN * 100)}% 減碼、中間中立"],
        ["和法人共識比", sg(val.get("vs_cons")) if val.get("vs_cons") is not None else "—",
         f"共識目標價 {f(ct.get('v'), 2 if us else None)} {cu}" if ct.get("v") else "沒有共識目標價"]]
    out.append(F.tab("目標價怎麼算", _table(["項目", "數字", "說明"], t_rows, "tpc"), f"本站規則（評等與目標價規格第 {pack.get('spec') or 1} 版）"))
    if sc:
        su = val.get("scen_up") or {}
        srows = [["悲觀", f"{f(sc['bear'])} {cu}", sg(su.get("bear")), (f"{'每股淨利' if us and v.get('basis') == 'ttm' else 'EPS'} 少 {int(S.SCEN_EPS * 100)}%、" if meth == "pe" else "") + f"{nm}用範圍下緣 {f(rng.get('lo'), 2)} 倍"],
                 ["基本", f"{f(sc['base'])} {cu}", sg(su.get("base")), "目標價"],
                 ["樂觀", f"{f(sc['bull'])} {cu}", sg(su.get("bull")), (f"{'每股淨利' if us and v.get('basis') == 'ttm' else 'EPS'} 多 {int(S.SCEN_EPS * 100)}%、" if meth == "pe" else "") + f"{nm}用範圍上緣 {f(rng.get('hi'), 2)} 倍"]]
        out.append(F.tab("三個情境", _table(["情境", "價格", "和報告日收盤比", "假設"], srows, "scen"), "本站規則"))
    return "".join(out)


RC_NAME = ("強力看好", "看好", "中立", "看淡", "強力看淡")


def cat_section_us(pack: dict, F: Figs) -> str:
    """美股：分析師評等與目標價、最近的評等變動、做空、法人與內部人（Yahoo Finance）。"""
    uc = pack.get("us_chips") or {}
    cons = pack.get("cons") or {}
    ct = cons.get("tp") or {}
    out = []
    rc = uc.get("rc") or []
    if rc:
        rows = [[RC_NAME[i], f(n, 0)] for i, n in enumerate(rc)]
        rows.append(["平均評等（1＝強力看好、5＝強力看淡）", f(uc.get("rm"), 2)])
        if ct.get("v"):
            rows.append(["目標價：平均／中位／最高／最低", f"{f(ct.get('v'))}／{f(ct.get('med'))}／{f(ct.get('hi'))}／{f(ct.get('lo'))} 美元"])
        out.append(F.tab("分析師評等與目標價", _table(["項目", "數字"], rows, "rc"), f"Yahoo Finance（{escape(cons.get('d') or '')}）"))
    ev = cons.get("ev") or []
    if ev:
        rr = [[escape(str(x["d"] or "")), escape(x["firm"] or ""), escape(f"{x['from'] or ''} → {x['to'] or ''}"),
               f"{f(x['tp_from'])} → {f(x['tp_to'])}" if x.get("tp_to") else "—"] for x in ev[:10]]
        out.append(F.tab("最近的評等與目標價變動", _table(["日期", "券商", "評等", "目標價（美元）"], rr, "rev"), "Yahoo Finance"))
    rows = []
    sh, mh, ns = uc.get("sh") or [], uc.get("mh") or [], uc.get("ns") or []
    if mh:
        rows += [["法人持股占流通股", f(mh[1] * 100 if mh[1] is not None else None, 1, "%")], ["持股法人家數", f(mh[2], 0)],
                 ["內部人持股", f(mh[0] * 100 if mh[0] is not None else None, 2, "%")]]
    if sh:
        rows += [["做空股數占流通股", f(sh[0] * 100 if sh[0] is not None else None, 2, "%") + (f"（{escape(sh[4])}）" if len(sh) > 4 and sh[4] else "")],
                 ["做空回補天數", f(sh[1], 2)], ["做空股數與上個月比", sg((sh[2] / sh[3] - 1) * 100 if sh[2] and sh[3] else None)]]
    if ns:
        rows += [[f"內部人近 {escape(str(ns[0]).replace('m', ' 個月'))}：買進／賣出筆數", f"{f(ns[1], 0)}／{f(ns[3], 0)}"],
                 ["內部人淨買股數", sg(ns[5], 0, " 股")]]
    if rows:
        out.append(F.tab("籌碼摘要", _table(["項目", "數字"], rows, "chip"), "Yahoo Finance（做空資料每半個月更新）"))
    return "".join(out)


def cat_section(pack: dict, F: Figs) -> str:
    if _us(pack):
        return cat_section_us(pack, F)
    ch = pack.get("chips") or {}
    out = []
    if ch.get("d"):
        def cum(xs):
            s, o = 0, []
            for x in xs:
                s += x or 0
                o.append(s)
            return o
        labs = [d[2:7].replace("-", "/") for d in ch["d"]]
        out.append(F.fig("三大法人累計買賣超（近一年，張）",
                         C.lines(labs, [("k1", "外資", cum(ch["f"])), ("k2", "投信", cum(ch["t"])), ("k3", "自營商", cum(ch["dl"]))],
                                 unit="張", label="法人累計買賣超", zero=True, dots=False), "證交所、櫃買中心三大法人買賣超"))
    cs = pack.get("chip_sum") or {}
    fp, mb = pack.get("fp") or {}, pack.get("mb") or {}
    rows = [["外資", sg(cs.get("f5"), 0, ""), sg(cs.get("f20"), 0, ""), sg(cs.get("f60"), 0, "")],
            ["投信", sg(cs.get("t5"), 0, ""), sg(cs.get("t20"), 0, ""), sg(cs.get("t60"), 0, "")],
            ["自營商", sg(cs.get("dl5"), 0, ""), sg(cs.get("dl20"), 0, ""), sg(cs.get("dl60"), 0, "")]]
    t = _table(["買賣超（張）", "近 5 日", "近 20 日", "近 60 日"], rows, "chip")
    extra = []
    if fp.get("now") is not None:
        extra.append(f"外資持股比 {f(fp['now'], 2)}%（{(fp.get('then_d') or '')[5:].replace('-', '/')} 是 {f(fp.get('then'), 2)}%）")
    if mb.get("now") is not None:
        extra.append(f"融資餘額 {f(mb['now'], 0)} 張（{(mb.get('then_d') or '')[5:].replace('-', '/')} 是 {f(mb.get('then'), 0)} 張）")
    e = pack.get("etf") or {}
    if e.get("n"):
        extra.append(f"{e['n']} 檔 ETF 持有（{(e.get('d') or '')[5:].replace('-', '/')}），其中主動式 {e.get('n_act')} 檔合計 {f(e.get('act_sh'), 0)} 張"
                     f"（{(e.get('d_20') or '')[5:].replace('-', '/')} 是 {f(e.get('act_sh_20'), 0)} 張）")
    out.append(F.tab("籌碼摘要", t + "".join(f'<p class="tn">{escape(x)}</p>' for x in extra), "證交所、櫃買中心、各 ETF 每日持股"))
    if e.get("top"):
        er = [[escape(x["etf"]), f(x["w"], 2, "%"), f(x["sh"], 0)] for x in e["top"]]
        out.append(F.tab("持有比重最高的 ETF", _table(["ETF", "占該 ETF", "張數"], er, "etf"), "各 ETF 每日持股揭露"))
    ev = (pack.get("cons") or {}).get("ev") or []
    if ev:
        rr = []
        for x in ev[:8]:
            if x["k"] == "EPS":
                what = f"{x['y']} 年 EPS 從 {f(x['from'], 2)} 元改為 {f(x['to'], 2)} 元"
            else:
                what = f"目標價中位數從 {f(x['from'])} 元改為 {f(x['to'])} 元"
            u = _safe_url(x.get("url"))
            rr.append([escape(str(x["d"] or "")),
                       f'<a href="{escape(u)}" target="_blank" rel="noopener">{escape(what)}</a>' if u else escape(what)])
        out.append(F.tab("法人共識最近的修正", _table(["日期", "修正"], rr, "rev"), "FactSet（鉅亨網台股預估）"))
    return "".join(out)


def why_box(pack: dict) -> str:
    pk = pack.get("pick") or {}
    if not pk:
        return ""
    if _us(pack):
        r = pk.get("rule") or {}
        conds = (f"強度 {f(pk.get('rs'), 0)}（要 {f(r.get('rs'), 0)} 以上）、離 52 週高點 {sg(pk.get('d52h'))}（要 {f(r.get('d52h'), 0)}% 以內）、"
                 f"營益率 {f(pk.get('om'), 1)}%（要 {f(r.get('om'), 0)}% 以上）、ROE {f(pk.get('roe'), 1)}%（要 {f(r.get('roe'), 0)}% 以上）、"
                 f"市值 {f(pk.get('cap'), 1)} 億美元（要 {f(r.get('cap'), 0)} 億美元以上）")
        act = (f"{(pk.get('buyd') or '')[5:].replace('-', '/')} 開盤買進" if pk.get("buy") else ("持有中" if pk.get("hold") else "名單上、沒有空位"))
        return (f'<div class="why"><b>{escape(pk.get("list") or "")}名單（{escape((pk.get("d") or "")[5:].replace("-", "/"))} 收盤）</b>'
                f'：第 {pk.get("rank")} 名（共 {pk.get("n") or "—"} 檔），{escape(act)}。五個條件：{escape(conds)}。'
                f'最多拿 {pk.get("slots") or "—"} 檔，收盤跌破 {pk.get("exit_ma") or "—"} 日線賣出。</div>')
    plan = "，".join(pk.get("plan") or [])
    return (f'<div class="why"><b>{escape(pk.get("list") or "")}名單（{escape((pk.get("d") or "")[5:].replace("-", "/"))} 收盤試算）</b>'
            f'：第 {pk.get("rank")} 名，強度 {pk.get("rs")}，連續 {pk.get("weeks")} 週在名單上。{escape(pk.get("why") or "")}。'
            f'位置：{escape(pk.get("spot") or "")}（{escape(plan)}）。</div>')


def co_box(pack: dict) -> str:
    if _us(pack):
        return (f'<div class="chain"><b>產業分類</b>（GICS）<ul><li>{escape(pack.get("sector") or "")}・{escape(pack.get("ind") or "")}'
                f'（S&amp;P {escape(str(pack.get("index") or ""))} 成分股；同細產業 {pack.get("peer_n") or "—"} 家）</li></ul></div>')
    ch = pack.get("chain") or []
    if not ch:
        return ""
    items = "".join(f"<li>{escape(c['cn'])}・{escape(c['nn'])}（台灣上市櫃 {c['n']} 家）</li>" for c in ch)
    return f'<div class="chain"><b>產業鏈位置</b>（櫃買中心產業價值鏈）<ul>{items}</ul></div>'


def _data_list(pack: dict) -> str:
    sd = pack.get("src_d") or {}
    if _us(pack):
        items = [f"財報：SEC 第一次公布的 10-Q／10-K（第四季＝全年 − 前三季；更新到 {sd.get('sec') or ''}）",
                 f"股價：Yahoo Finance（到 {pack.get('asof') or ''}）；S&P 500：Yahoo Finance",
                 f"分析師預估、目標價、評等、做空、法人與內部人：Yahoo Finance（到 {sd.get('an') or ''}；EPS 預估多為調整後）",
                 f"同業：維基百科 S&P 500／400／600 成分股表的 GICS 細產業（{sd.get('gics') or ''}），市值與本益比是 {sd.get('scr') or ''} 那一週的",
                 "本益比：美股一律用市值 ÷ 近四季淨利（目前流通股數），和每股盈餘（加權股數）在大量買回股票時會不一樣"]
    else:
        items = [f"財報與月營收：公開資訊觀測站（最新一季 {(sd.get('co') or {}).get('q') or ''}、月營收到 {(sd.get('co') or {}).get('mo') or ''}）",
                 f"股價、法人、融資、外資持股：證交所、櫃買中心（到 {pack.get('asof') or ''}）",
                 f"法人預估：FactSet（鉅亨網台股預估）、Yahoo Finance（到 {sd.get('x9f') or ''}）",
                 "同業：櫃買中心產業價值鏈平台、證交所產業別", "ETF 持股：各 ETF 每日揭露"]
    return "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>"


def appendix(pack: dict, ctx: dict) -> str:
    sd = pack.get("src_d") or {}
    hist = ctx.get("hist") or []
    hrows = [[h["made"], escape(h.get("rating") or ""), f(h.get("tp")), f(h.get("px")),
              sg(h.get("since")) if h.get("since") is not None else "—", f"第 {h.get('spec') or 1} 版"] for h in hist]
    ht = (_table(["報告日", "評等", "目標價", "當時收盤", "到最新收盤", "評等規格"], hrows, "hist")
          + ('<p class="tn">評等規格第 1 版的同業倍數用近四季本益比、卻乘在未來 12 個月 EPS 上（口徑不一致），第 2 版起改成同一把尺。</p>'
             if any((h.get("spec") or 1) == 1 for h in hist) else "")
          if hrows else "<p>這是第一份報告。</p>")
    return (f'<section class="sec app" id="app"><h2>附錄</h2>'
            f'<h3>評等與目標價</h3><p>看 12 個月。倍數和它乘的 EPS 一定用同一把尺，本站不自己預估 EPS。'
            f'本公司有 {S.CONS_MIN} 位以上分析師的共識、同業也有 {S.PEER_MIN} 家以上有共識：目標價＝未來 12 個月 EPS（今年和明年的共識依今年還剩幾個月加權）'
            f'× 同業未來 12 個月本益比（第 25～75 百分位內，預設中位數）。其他情況：目標價＝已公布的近四季 EPS × 本益比'
            f'（本公司近 {S.BAND_YEARS} 年與同業現在的近四季本益比，第 25～75 百分位內，預設兩個中位數的平均）。'
            f'金融業、虧損或超過 {int(S.PE_MAX)} 倍的公司用每股淨值 × 淨值比。不用預設倍數時寫明原因。'
            f'評等：上檔空間 ≥ {int(S.BUY_UP * 100)}% 買進、≤ {int(S.SELL_DN * 100)}% 減碼、中間中立。</p>'
            f'<h3>評等歷史</h3>{ht}'
            f'<h3>本站資料</h3>{_data_list(pack)}'
            f'<h3>免責聲明</h3><p class="disc">{escape(DISCLAIMER)}</p></section>')


# ── 整頁 ─────────────────────────────────────────────────────────────────

def render(text: str, pack: dict, ctx: dict | None = None) -> str:
    """ctx：live＝{"px","d"} 最新收盤；hist＝舊版評等；ind＝{"href","name","made"} 產業報告。"""
    from . import appnav
    ctx = ctx or {}
    p = R.parse(text)
    fm, sec = p["fm"], p["sec"]
    val = R.valuation(pack, fm)
    F = Figs()
    px = pack.get("px") or {}
    tp = val.get("tp")
    ser = pack.get("ser") or {}
    ixn = ser.get("ix_name") or "加權指數"
    cu, am = _cu(pack)
    p1 = F.fig(f"股價與{ixn}（近 2 年，指數換算成同一起點）",
               C.price_chart(ser.get("d") or [], ser.get("c") or [], ser.get("ix") or [], tp=tp, label="股價", unit=cu, ix_name=ixn),
               _src(pack, "px"), "p1f")
    live = ctx.get("live") or {}
    live_html = ""
    if live.get("px") and live.get("d") and live["d"] > (px.get("d") or ""):
        gap = (tp / live["px"] - 1) * 100 if tp else None
        live_html = (f'<p class="live">報告日 {escape(px.get("d", "")[5:].replace("-", "/"))} 收盤 {f(px.get("c"))} {cu}、目標價 {f(tp)} {cu}；'
                     f'最新收盤 {f(live["px"])} {cu}（{escape(live["d"][5:].replace("-", "/"))}）{"，距目標價 " + sg(gap) if gap is not None else ""}。</p>')
    who = f"{escape(pack.get('name') or '')}（{escape(pack.get('code') or '')}）・{escape(pack.get('ind') or '')}・{MK_NAME.get(pack.get('mk'), '')}"
    ind = ctx.get("ind") or {}
    toc = "".join(f'<a href="{_self(pack)}#{SEC_ID[s]}">{escape(s)}</a>' for s in R.SECTIONS if s in SEC_ID and s != "資料來源")
    parts = [f'<header class="eqh"><div class="kick">個股報告・{escape(str(fm.get("made") or ""))}（資料到 {escape(pack.get("asof") or "")} 收盤）</div>'
             f'<h1>{escape(str(fm.get("title") or ""))}</h1><div class="who">{who}</div></header>', live_html,
             f'<section class="p1">{rating_box(pack, val)}<div class="p1m"><div class="hls">{md(sec.get("重點", ""))}</div>{p1}</div></section>',
             F.tab("財務與估值摘要", summary_table_us(pack) if _us(pack) else summary_table(pack), f"{_src(pack, 'co')}、{_src(pack, 'fc')}"),
             f'<nav class="toc" aria-label="目錄">{toc}<a href="{_self(pack)}#app">附錄</a></nav>']
    blocks = {"財務分析": lambda: fin_section(pack, F), "同業比較": lambda: peer_section(pack, F),
              "估值": lambda: val_section(pack, val, fm, F), "催化劑與籌碼": lambda: cat_section(pack, F),
              "為什麼被選上": lambda: why_box(pack), "公司概況": lambda: co_box(pack)}
    for s in R.SECTIONS:
        if s == "重點":
            continue
        extra = blocks.get(s, lambda: "")()
        if s == "產業與競爭" and ind.get("href"):
            extra = (f'<p class="indl">產業報告：<a href="{escape(ind["href"])}">{escape(ind.get("name") or "")}'
                     f'（{escape(ind.get("made") or "")}）</a></p>') + extra
        parts.append(f'<section class="sec s-{SEC_ID[s]}" id="{SEC_ID[s]}"><h2>{escape(s)}</h2>{md(sec.get(s, ""))}{extra}</section>')
    parts.append(appendix(pack, ctx))
    body = "".join(parts)
    title = f"{pack.get('name')} 個股報告"
    html = (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><base href="../">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">'
            f'<link rel="icon" href="data:,"><title>{escape(title)}</title><style>{CSS}{appnav.CSS}</style></head><body>'
            f'<div class="top">{appnav.bar("r")}{appnav.BACK}</div><main class="eq">{body}'
            f'<p class="disc foot">{escape(DISCLAIMER)}</p></main></body></html>')
    return appnav.finish(html)


def _self(pack: dict) -> str:
    return f"rp/{pack.get('mk')}-{pack.get('code')}.html"


CSS = """
:root{color-scheme:light dark;--bg:#fff;--card2:#f4f6fa;--ink:#1f2733;--ink2:#44505f;--mut:#67727f;--line:#e8ebf1;--line2:#d3dae4;
--acc:#2563c9;--k1:#2a78d6;--k2:#eb6834;--k3:#1baf7a;--up:#d33a34;--dn:#1f8f4e;--mu:#8a94a3;--rb:#c8322c;--rn:#6b7684;--rs:#1f7a45}
@media (prefers-color-scheme:dark){:root{--bg:#0b111c;--card2:#182234;--ink:#e8eef8;--ink2:#aab6c9;--mut:#8392a8;--line:#223049;
--line2:#30425f;--acc:#6aa8ff;--k1:#3987e5;--k2:#d95926;--k3:#199e70;--up:#f15b50;--dn:#2fbf71;--mu:#7d8aa0;--rb:#f0584b;--rn:#8b96a8;--rs:#2fbf71}}
*{box-sizing:border-box}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.top{display:flex;align-items:center;gap:4px 12px;flex-wrap:wrap;padding:10px 16px 4px;max-width:1080px;margin:0 auto}
.back{font-size:13px;color:var(--mut);white-space:nowrap}
.eq{max-width:1000px;margin:0 auto;padding:6px 16px 60px}
.eqh .kick{font-size:12.5px;color:var(--mut);letter-spacing:.02em}
.eqh h1{font-size:25px;line-height:1.35;margin:4px 0 4px}.eqh .who{color:var(--ink2);font-size:14px}
.live{background:var(--card2);border-radius:8px;padding:6px 12px;font-size:13.5px;color:var(--ink2)}
.p1{display:grid;grid-template-columns:250px 1fr;gap:18px;margin:14px 0 6px;align-items:start}
.rbox{border:1px solid var(--line2);border-radius:12px;padding:12px 14px;background:var(--card2)}
.rbox .rt{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line2);padding-bottom:6px}
.rbox .rt span,.rbox .tpb span{font-size:12.5px;color:var(--mut)}
.rbox .rt b{font-size:26px}.rt.rb b{color:var(--rb)}.rt.rn b{color:var(--rn)}.rt.rs b{color:var(--rs)}.rt.rx b{color:var(--mut)}
.rbox .tpb{display:flex;justify-content:space-between;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--line2)}
.rbox .tpb b{font-size:20px}
.rbox dl{margin:6px 0 0}.rbox dl div{display:flex;justify-content:space-between;gap:8px;font-size:13px;padding:2px 0}
.rbox dt{color:var(--mut)}.rbox dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}
.hls p.hl{margin:0 0 9px}.hl .sq{color:var(--acc);margin-right:6px;font-size:12px}
.toc{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:7px 0;margin:14px 0}
.sec{margin-top:26px}.sec h2{font-size:20px;border-left:4px solid var(--acc);padding-left:9px;margin:0 0 10px}
.sec h3{font-size:16px;margin:16px 0 6px}.sec p{margin:0 0 10px}.sec ul{margin:0 0 10px;padding-left:22px}.sec li{margin:3px 0}
.fig{margin:14px 0 18px;break-inside:avoid}.fig figcaption{font-size:13.5px;margin-bottom:4px}
.fsrc{font-size:11.5px;color:var(--mut);margin-top:2px}
.ch{width:100%;height:auto;display:block;font-family:inherit}
.ch .g{stroke:var(--line);stroke-width:1}.ch .g0{stroke:var(--line2);stroke-width:1.2}
.ch text{font-size:12.5px;fill:var(--mut)}.ch .tp{fill:var(--ink2);font-size:13px}.ch .tl{font-size:13px;font-weight:600}
.ch .tv{font-size:12.5px;fill:var(--ink2)}
.fgrid{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}.fgrid .fig{margin:10px 0 14px}
.fgrid .ch text{font-size:16px}.fgrid .ch .tl,.fgrid .ch .tp{font-size:16px}
.fig:not(.tbl)>.ch{max-width:780px}
.ch .ln{fill:none;stroke-linejoin:round;stroke-linecap:round}
.ch .ln.k1,.ch .hl.k1{stroke:var(--k1)}.ch .ln.k2,.ch .hl.k2{stroke:var(--k2)}.ch .ln.k3{stroke:var(--k3)}.ch .ln.mu,.ch .hl.mu{stroke:var(--mu)}
.ch rect.k1,.ch circle.k1{fill:var(--k1)}.ch rect.k2,.ch circle.k2{fill:var(--k2)}.ch rect.k3,.ch circle.k3{fill:var(--k3)}
.ch rect.up{fill:var(--up)}.ch rect.dn{fill:var(--dn)}.ch .dt{stroke:var(--bg);stroke-width:1.5}
.ch .tl.k2{fill:var(--k2)}.ch .tl.mu{fill:var(--ink2)}.ch .hl{stroke-width:1.5}
.ch .fb{opacity:.75}.ch .fbm{stroke:var(--ink);stroke-width:2}
.lgs{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);margin-top:2px}
.lg{display:inline-flex;align-items:center;gap:5px}.sw{display:inline-block;width:14px;height:3px;border-radius:2px}
.sw.bar{height:10px;width:10px;border-radius:2px}.sw.dash{background:none!important;border-top:2px dashed;height:0}
.sw.k1{background:var(--k1);border-color:var(--k1)}.sw.k2{background:var(--k2);border-color:var(--k2)}.sw.k3{background:var(--k3);border-color:var(--k3)}
.sw.mu{background:var(--mu);border-color:var(--mu)}
.tw{overflow-x:auto}
.dt{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
.dt th,.dt td{padding:5px 7px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}.dt thead th{white-space:normal;vertical-align:bottom}
.dt th:first-child,.dt td:first-child{text-align:left}.dt thead th{color:var(--mut);font-weight:600;border-bottom:1px solid var(--line2)}
.dt.tpc td:nth-child(3),.dt.rev td:nth-child(2),.dt.scen td:nth-child(4){text-align:left;white-space:normal}
.dt.peer:not(.mem) tbody tr:first-child td{background:var(--card2)}.dt.peer:not(.mem) tbody tr:last-child td{font-weight:600}
.cd{color:var(--mut);font-size:11.5px}.tn{font-size:12px;color:var(--mut);margin:4px 0 0}
.csv{font-size:12px;margin-left:8px}
.why,.chain,.indl{background:var(--card2);border-radius:10px;padding:9px 13px;font-size:14px;margin:10px 0}.chain ul{margin:4px 0 0}
.disc{font-size:12px;color:var(--mut)}.foot{border-top:1px solid var(--line);padding-top:10px;margin-top:30px}
@media (max-width:860px){.fgrid{grid-template-columns:1fr}}
@media (max-width:760px){.p1{grid-template-columns:1fr}.eqh h1{font-size:21px}body{font-size:15px}.dt{font-size:12px}.dt th,.dt td{padding:4px 5px}}
@media (max-width:640px){.ch text,.fgrid .ch text,.ch .tp,.ch .tl,.ch .tv,.fgrid .ch .tl,.fgrid .ch .tp{font-size:21px}}
@media print{
 @page{size:A4;margin:12mm 11mm}
 body{font-size:10pt;line-height:1.6;background:#fff;color:#000}.top,.toc,.live,.csv{display:none!important}
 .eq{max-width:none;padding:0}.p1{grid-template-columns:62mm 1fr;gap:5mm}
 .s-fin,.s-peer,.s-val,.s-cat,.app{break-before:page}
 .sec h2{font-size:14pt}.fig{break-inside:avoid}.dt{font-size:8.5pt}.dt th,.dt td{padding:2px 5px}
 a{color:#000}
}
"""


# ── 產業報告頁 ───────────────────────────────────────────────────────────

IND_SEC_ID = {"產業定義與產業鏈": "def", "市場規模與成長": "size", "供需與價格": "sup", "主要廠商": "play",
              "台灣成員營收與估值": "tw", "接下來要看的": "next", "風險": "risk", "資料來源": "src", "美股成員與估值": "mem"}
BUB_NAME = {0: "沒有跡象", 1: "偏貴", 2: "漲勢過熱", 3: "泡沫警戒", 4: "嚴重泡沫"}


def ind_box_us(ip: dict) -> str:
    pe, fpe = ip.get("pe") or {}, ip.get("fpe") or {}
    rows = [("S&P 1500 成員", f"{ip.get('n_members')} 家"), ("GICS 大類", ip.get("sector") or ""),
            ("有市值的成員市值合計", f"{f(ip.get('cap_total'), 0)} 億美元（{ip.get('n_cap')} 家）"),
            ("本益比中位數（市值 ÷ 近四季淨利）", f"{f(pe.get('p50'), 1)} 倍（{pe.get('n')} 家）" if pe else "—"),
            ("未來 12 個月本益比中位數", f"{f(fpe.get('p50'), 1)} 倍（{fpe.get('n')} 家）" if fpe else "—")]
    body = "".join(f"<div><dt>{escape(a)}</dt><dd>{escape(b)}</dd></div>" for a, b in rows)
    return f'<aside class="rbox"><div class="tpb"><span>產業報告</span><b>{escape(ip.get("name") or "")}</b></div><dl>{body}</dl></aside>'


def ind_box(ip: dict) -> str:
    if ip.get("mk") == "us":
        return ind_box_us(ip)
    agg = ip.get("rev_agg") or []
    last = agg[-1] if agg else {}
    pe = ip.get("pe") or {}
    rows = [("台灣上市櫃成員", f"{ip.get('n_members')} 家"), ("市值合計", f"{f(ip.get('cap_total'), 0)} 億元"),
            ("成員合計月營收", f"{f(last.get('rev'), 0)} 億元（{(last.get('ym') or '')[2:].replace('-', '/')}）"),
            ("月營收年增", sg(last.get("yoy"))), ("本益比中位數", f"{f(pe.get('p50'), 1)} 倍" if pe else "—")]
    for b in ip.get("bubble") or []:
        rows.append((f"泡沫等級・{b['name']}", f"{b['level']}（{BUB_NAME.get(b['level'], '')}）"))
    body = "".join(f"<div><dt>{escape(a)}</dt><dd>{escape(b)}</dd></div>" for a, b in rows)
    return f'<aside class="rbox"><div class="tpb"><span>產業報告</span><b>{escape(ip.get("name") or "")}</b></div><dl>{body}</dl></aside>'


def ind_render(text: str, ip: dict, ctx: dict | None = None) -> str:
    from . import appnav
    ctx = ctx or {}
    p = R.parse(text)
    fm, sec = p["fm"], p["sec"]
    F = Figs()
    if ip.get("mk") == "us":
        sd = ip.get("src_d") or {}
        mrows = [[f'{escape(m["n"])} <span class="cd">{escape(m["c"])}</span>', f"S&amp;P {escape(str(m.get('ix') or ''))}",
                  f(m["cap"], 0) + ("＊" if m.get("cap_src") == "fwd" else ""), f(m["pe"], 1), f(m["fpe"], 1), sg(m.get("rq"), 1),
                  f(m.get("om"), 1, "%"), f(m.get("roe"), 1, "%"), sg(m.get("r1y"), 0)] for m in ip.get("members") or []]
        mem_t = F.tab("S&P 1500 的同細產業成員", _table(["公司", "指數", "市值（億美元）", "本益比（市值 ÷ 近四季淨利）", "未來 12 個月本益比",
                                                       "最新一季營收年增", "營益率（近四季）", "ROE（近四季）", "近一年漲跌"], mrows, "peer mem"),
                      f"維基百科 S&P 1500 成分股表（{sd.get('gics') or ''}）、SEC 財報與篩選器市值（{sd.get('scr') or ''}）、"
                      f"Yahoo Finance 預估（{sd.get('fwd') or ''}）；＊＝篩選器沒有、用 Yahoo 的市值；空白＝本站沒有這家的資料")
        pe, fpe = ip.get("pe") or {}, ip.get("fpe") or {}
        vrows = [["本益比（市值 ÷ 近四季淨利）", f(pe.get("p25"), 1), f(pe.get("p50"), 1), f(pe.get("p75"), 1), f(pe.get("n"), 0)],
                 ["未來 12 個月本益比", f(fpe.get("p25"), 1), f(fpe.get("p50"), 1), f(fpe.get("p75"), 1), f(fpe.get("n"), 0)]]
        val_t = F.tab("成員的估值分布", _table(["", "第 25 百分位", "中位數", "第 75 百分位", "家數"], vrows, "vd"), "同上")
        extra = {"主要廠商": mem_t, "美股成員與估值": val_t}
    else:
        agg = ip.get("rev_agg") or []
        labs = [a["ym"][2:].replace("-", "/") for a in agg]
        fig_rev = F.fig("台灣成員合計月營收與年增率（同一批公司）", C.bars_yoy(labs, [a["rev"] for a in agg], [a["yoy"] for a in agg], label="成員合計月營收"),
                        SRC_MO)
        nrows = [[escape(n["nn"]), f(n["n"], 0), f(n.get("foreign"), 0), f(n["cap"], 0), escape("、".join(t[1] for t in n["top"][:5]))]
                 for n in ip.get("nodes") or []]
        chain_t = F.tab("產業鏈節點與台灣成員", _table(["節點", "台灣上市櫃", "知名外國企業", "市值合計（億元）", "市值最大的公司"], nrows, "chainx"),
                        "櫃買中心產業價值鏈平台、證交所、櫃買中心")
        mem = (ip.get("members") or [])[:20]
        mrows = [[f'{escape(m["n"])} <span class="cd">{escape(m["c"])}</span>', f(m["cap"], 0), f(m["pe"], 1), f(m["pb"], 2), sg(m["ry3"], 0),
                  f(m["gm"], 1, "%"), f(m["om"], 1, "%"), f(m["roe"], 1, "%"), escape("、".join(m["nodes"][:2]))] for m in mem]
        mem_t = F.tab("市值最大的 20 家", _table(["公司", "市值（億元）", "本益比", "淨值比", "近 3 月營收年增", "毛利率", "營益率", "ROE", "節點"], mrows, "peer mem"),
                      f"{SRC_PX}、{SRC_CO}")
        pe, pb, ry = ip.get("pe") or {}, ip.get("pb") or {}, ip.get("ry3") or {}
        vrows = [["本益比（近四季）", f(pe.get("p25"), 1), f(pe.get("p50"), 1), f(pe.get("p75"), 1), f(pe.get("n"), 0)],
                 ["淨值比", f(pb.get("p25"), 2), f(pb.get("p50"), 2), f(pb.get("p75"), 2), f(pb.get("n"), 0)],
                 ["近 3 月營收年增（%）", f(ry.get("p25"), 1), f(ry.get("p50"), 1), f(ry.get("p75"), 1), f(ry.get("n"), 0)]]
        val_t = F.tab("成員的估值與成長分布", _table(["", "第 25 百分位", "中位數", "第 75 百分位", "家數"], vrows, "vd"), f"{SRC_PX}、{SRC_CO}")
        brows = [[escape(b["name"]), f"{b['level']}（{BUB_NAME.get(b['level'], '')}）", sg(b.get("run2"), 0), sg(b.get("net2"), 0),
                  sg(b.get("from_hi"), 1), "、".join(k for k in ("P1", "P2", "P3", "E", "G", "F") if b.get(k))] for b in ip.get("bubble") or []]
        bub_t = F.tab("細分族群泡沫等級", _table(["族群", "等級", "兩年漲幅", "比大盤多漲（個百分點）", "離高點", "成立的條件"], brows, "bub"),
                      "本站泡沫頁（細分族群，市值加權含息指數）") if brows else ""
        extra = {"產業定義與產業鏈": chain_t, "主要廠商": mem_t, "台灣成員營收與估值": fig_rev + val_t + bub_t}
    parts = [f'<header class="eqh"><div class="kick">產業報告・{escape(str(fm.get("made") or ""))}（資料到 {escape(ip.get("asof") or "")}）</div>'
             f'<h1>{escape(str(fm.get("title") or ""))}</h1><div class="who">{escape(ip.get("name") or "")}・'
             f'{"美股 GICS 細產業" if ip.get("mk") == "us" else "台股產業鏈"}</div></header>',
             f'<section class="p1">{ind_box(ip)}<div class="p1m"><div class="hls">{md(sec.get("重點", ""))}</div></div></section>']
    cos = ctx.get("cos") or []
    if cos:
        parts.append('<p class="indl">本產業的個股報告：' + "、".join(
            f'<a href="{escape(c["href"])}">{escape(c["name"])}（{escape(c.get("rating") or "")}）</a>' for c in cos) + "</p>")
    for s in R.ind_sections(ip.get("mk")):
        if s == "重點":
            continue
        parts.append(f'<section class="sec" id="{IND_SEC_ID[s]}"><h2>{escape(s)}</h2>{md(sec.get(s, ""))}{extra.get(s, "")}</section>')
    app = ("成員＝S&amp;P 500／400／600 裡同一個 GICS 細產業的公司（不含沒有在這三個指數裡的公司）。本益比一律是市值 ÷ 近四季淨利（SEC 第一次公布）；"
           "未來 12 個月本益比＝股價 ÷ Yahoo 分析師未來 12 個月 EPS（3 位以上才算，多為調整後）。"
           if ip.get("mk") == "us" else
           "成員＝櫃買中心產業價值鏈平台這條鏈的上市、上櫃、外國上市公司。合計月營收每個月只算當月與去年同月都有營收的公司（同一批公司）。泡沫等級見研究紀錄頁的泡沫研究。")
    parts.append(f'<section class="sec app" id="app"><h2>附錄</h2><p>{app}</p>'
                 f'<h3>免責聲明</h3><p class="disc">{escape(DISCLAIMER)}</p></section>')
    title = f"{ip.get('name')} 產業報告"
    html = (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><base href="../">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">'
            f'<link rel="icon" href="data:,"><title>{escape(title)}</title><style>{CSS}{appnav.CSS}</style></head><body>'
            f'<div class="top">{appnav.bar("r")}{appnav.BACK}</div><main class="eq">{"".join(parts)}'
            f'<p class="disc foot">{escape(DISCLAIMER)}</p></main></body></html>')
    return appnav.finish(html)
