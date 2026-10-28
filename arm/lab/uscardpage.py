"""美股個股卡（配置頁 v2 第 4 步；docs/lab_cfg_v2_plan.md 第 3.3 節）：配置頁美股列的股票（手上的、要買的、名單前 5 名裡
手上沒有的）點了打開的卡片——配置、為什麼選它、走勢、成長、獲利、估值、分析師、公司。
走勢可切 6 個月／1 年／3 年／5 年、有成交量與 52 週高點；成長、獲利、估值是 2026-10-28 補的（docs/lab_review_plan.md 第 4 節 (a)(b)(c)）：
SEC 季報（usfin.py，每週六）配上每天的股價，本益比、淨值比和自己過去 5 年比。

資料：每週紀錄（ussx_qm_live.json：持股、名單、met／met0＝五個條件）＋每天的 50 日線檢查（ussx_qm_watch.json）＋
每天的卡片資料（ussx_card.json：近一年收盤與 50 日線、Yahoo 分析師預估、財報日；uscard.py）＋簡介庫。
配置、為什麼選它、公司三段在這裡組好（持股、比重、賣出日都用 cfgpage.us_state 的結果，和配置頁那一列一致）；
走勢、分析師兩段由瀏覽器畫（JS 函式一律 uc 開頭；「目標價」只准出現在 ucAn，引述分析師的數字、附 Yahoo 的來源連結，
同台股公司卡「法人預估」的例外，tests/test_uscardpage.py 守）。
頁面資料：D.cfg.us.uc＝{"o": [代號（配置頁的順序）], "cal": [近一年交易日], "d": 卡片資料要的美股收盤日, "s": {代號: {...}}}。
網址 #us=代號。
"""
from __future__ import annotations

import html
import math

from datetime import date, timedelta

from .. import fund_intro as FI
from . import corepage as CPG
from . import usfin as UF
from . import ussxspec as QX

YF = "https://finance.yahoo.com/quote/"
SEC = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&owner=include&count=40&CIK="


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def ysym(c: str) -> str:
    """Yahoo 的代號寫法（BRK.B → BRK-B）。"""
    return str(c).replace(".", "-").replace("/", "-")


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _px(x: float | None) -> str:
    """美股股價：兩位小數、千分位。"""
    return "—" if x is None else f"{x:,.2f}"


# ── 為什麼選它：五個條件（順序同 ussxqm.KEYS） ──────────────────────────────────

def five_rows() -> list[tuple[str, str, str]]:
    """[(鍵, 名稱, 要多少)]；要多少照 ussxspec.QM 寫（規則改了這裡跟著改）。"""
    q = QX.QM
    return [("rs", "強度", f"要 {q['rs']:.0f} 以上"),
            ("d52h", "離 52 週高點", f"要在 {-q['d52h'] * 100:.0f}% 以內"),
            ("om", "營益率", f"要 {q['om'] * 100:.0f}% 以上"),
            ("roe", "近四季 ROE", f"要 {q['roe'] * 100:.0f}% 以上"),
            ("cap", "市值", f"要 {q['cap'] / 1e8:,.0f} 億美元以上")]


def five_ok(k: str, v: float | None) -> bool | None:
    """這一個數字有沒有過（沒有值＝None）。"""
    if v is None:
        return None
    q = QX.QM
    return v >= q[k]


def five_txt(k: str, v: float | None) -> str:
    if v is None:
        return "—"
    if k == "rs":
        return f"{v:.0f}"
    if k == "d52h":
        return "在高點" if v >= -0.0005 else f"低 {-v * 100:.1f}%"
    if k == "cap":                                            # 單位寫在「要 20 億美元以上」那一行（手機 320px 表格才放得下）
        b = v / 1e8
        return f"{b:,.0f} 億" if b >= 100 else f"{b:.1f} 億"
    return f"{v * 100:.1f}%"


def _vals(v) -> dict[str, float | None]:
    keys = [k for k, _, _ in five_rows()]
    v = list(v or [])
    return {k: _num(v[i]) if i < len(v) else None for i, k in enumerate(keys)}


def _cell(k: str, v: float | None) -> str:
    ok = five_ok(k, v)
    mk = "" if ok is None else ('<i class="ucok">✓</i>' if ok else '<i class="ucno">✗</i>')
    return f"<td>{mk}{_e(five_txt(k, v))}</td>"


def why_html(c: str, n: dict, rank: tuple | None, hold: bool) -> str:
    """為什麼選它：五個條件的數字和要多少。拿著的股票兩欄＝買進那一週（met0，帳戶記的訊號日，那時五個都過）與這一週（met）；
    還沒買的只有這一週。下面一行講每個數字是什麼、買進以後只看 50 日線。"""
    met, met0 = (n.get("met") or {}).get(c), (n.get("met0") or {}).get(c)
    wk = n.get("wk")
    cols = []
    if hold and met0:
        cols.append((f'買進時<span>{_e(CPG._md(met0.get("wk")))} 那週</span>', _vals(met0.get("v"))))
    if met or not cols:
        cols.append((f'{"現在" if hold else "這週"}<span>{_e(CPG._md(wk))} 那週</span>', _vals(met)))
    if rank:
        sub = f'{CPG._md(wk)} 那週的名單第 {rank[0]} 名（共 {n.get("n_list", 0)} 檔）'
    elif hold:
        sub = f'{CPG._md(wk)} 那週不在名單上（拿著的只看 50 日線）'
    else:
        sub = ""
    head = "<tr><th></th>" + "".join(f"<th>{h}</th>" for h, _ in cols) + "</tr>"
    body = "".join(f'<tr><td class="l"><b>{_e(nm)}</b><span>{_e(req)}</span></td>' + "".join(_cell(k, v[k]) for _, v in cols) + "</tr>"
                   for k, nm, req in five_rows())
    empty = not met and not met0
    note = ("強度＝近 3、6、9、12 個月的漲幅（近 3 個月算兩倍）勝過幾 % 的美股（1～99）；營益率＝最近一季的營業利益 ÷ 營收；"
            "近四季 ROE＝近四季淨利 ÷ 股東權益；市值＝那週最後一個交易日的收盤 × 流通股數。")
    if QX.QM_OM_FIX:
        fx = QX.QM_OM_FIX["spike"] * 100
        note += (f"上一季營益率不到 {QX.QM['om'] * 100:.0f}%、這一季比上一季和去年同一季都高 {fx:.0f} 個百分點以上，"
                 "而且營業利益增加的比營收增加的多（賣資產這類一次性收入撐起來的），那一季不算。")
    if hold:
        note += "買進以後只看 50 日線，這幾個數字變差也照樣拿著。"
    return (f'<h3>為什麼選它' + (f'<span class="sub">{_e(sub)}</span>' if sub else "") + "</h3>"
            + ('<p class="st">這週的五個數字還沒有（每週六更新）。</p>' if empty else
               f'<div class="tw"><table class="ucfv">{head}{body}</table></div><p class="note">{_e(note)}</p>'))


# ── 配置 ─────────────────────────────────────────────────────────────────────

def _last_px(cs: list) -> tuple[float | None, float | None]:
    """卡片資料的最後一個收盤與漲跌（%）。"""
    xs = [x for x in cs or [] if x is not None]
    if not xs:
        return None, None
    return xs[-1], (xs[-1] / xs[-2] - 1) * 100 if len(xs) > 1 and xs[-2] else None


def cfg_html(c: str, G: dict, h0: dict | None, W0: dict | None, px: float | None, cash: bool, rank: tuple | None = None) -> str:
    """配置：持有中（哪天買、買進價、現在、占全部資金、跌破 50 日線就賣；已經跌破＝哪天開盤賣）、待買進、這週賣掉了、
    名單上手上沒有的（有空位時照名單順序買）。數字都用 us_state 的結果（G），和配置頁那一列一樣。"""
    rows = {r["c"]: r for r in G["rows"]}
    todo = {x["c"]: x for x in G["todo"]}
    gone = {x["c"]: x for x in G["gone"]}
    lines = []
    if cash:
        lines.append("警訊：全部持股放現金中；下面是照規則該有的股票，警訊解除後照這樣買回。")
    if c in rows:
        r = rows[c]
        if r.get("new"):
            lines.append(f'持有中：{CPG._mdw(r["ent"])}開盤買進；買進價和漲跌等這週六的持股紀錄。占全部資金約 {CPG._wp(r["w"])}。')
        else:
            epx = _num((h0 or {}).get("epx"))
            rr = r.get("r")
            hp = _num((h0 or {}).get("px"))
            if px is not None and hp and (h0 or {}).get("r") is not None:   # 漲跌照卡片的最新收盤（和標題的股價一致）
                rr = (1 + h0["r"]) * px / hp - 1
            now = f'，現在 <b>{_px(px)}</b>（<span class="{"up" if (rr or 0) >= 0 else "dn"}">{CPG._pc(rr)}</span>）' if px is not None and rr is not None else ""
            bt, p0 = bool(r.get("bt")), _num(r.get("p0"))
            rl = (px / p0 - 1) if bt and px is not None and p0 else r.get("rl")
            live = (f'；上線以來（{CPG._md(QX.QM_LIVE)} 收盤起）<span class="{"up" if rl >= 0 else "dn"}">{CPG._pc(rl)}</span>'
                    if bt and rl is not None else "")
            lines.append(f'持有中：{CPG._mdw(r["ent"])}買進 {_px(epx)}' + ("（回測）" if bt else "") + f'{now}{live}；占全部資金 {CPG._wp(r["w"])}。')
        if r.get("sell"):
            lines.append(f'<b>{CPG._mdw(r["sell"])}開盤賣</b>（{CPG._md(r["trig"])} 收盤跌破 50 日線）。')
        else:
            ma, pct = _num((W0 or {}).get("ma")), _num((W0 or {}).get("pct"))
            if ma is None:
                ma, pct = _num((h0 or {}).get("ma")), r.get("pct")
            t = "收盤跌破 50 日線，就在下一個交易日開盤賣"
            if ma is not None:
                t += f"：50 日線現在 <b>{_px(ma)}</b>"
                if pct is not None:
                    t += f'（收盤比它{"高" if pct >= 0 else "低"} {abs(pct) * 100:.1f}%）'
            lines.append(t + "。")
    elif c in todo:
        x = todo[c]
        if x["w"] > 1e-3:
            lines.append(f'待買進：<b>{CPG._mdw(x["d"])}開盤買</b>，約占全部資金 {CPG._wp(x["w"])}。')
        else:
            lines.append(f'排在名單上，但現金不夠，{CPG._mdw(x["d"])}先不買。')
        lines.append("買了以後，收盤跌破 50 日線就在下一個交易日開盤賣。")
    elif c in gone:
        x = gone[c]
        lines.append(f'{CPG._mdw(x["on"])}開盤賣掉了' + (f'（{CPG._md(x["trig"])} 收盤跌破 50 日線）' if x.get("trig") else "") + "。")
    else:
        nf = G.get("nf")
        wk = (G.get("n") or {}).get("wk")
        lines.append("手上沒有" + (f"：{CPG._md(wk)} 那週名單第 {rank[0]} 名" if rank and wk else "") + "。有空位時照名單順序買。")
        if G.get("free"):
            lines.append(f'現在有 {G["free"]} 個空位' + (f'，{CPG._mdw(nf)}收盤看下一份名單，下一個交易日開盤買' if nf else "") + "。")
        else:
            lines.append(f'現在 {QX.QM_SLOTS} 個位子都滿，有空位才買' + (f'（{CPG._mdw(nf)}收盤看下一份名單）' if nf else "") + "。")
    return (f'<h3>配置<span class="sub">{_e(CPG.QM_NAME)}</span></h3>'
            + "".join(f'<p class="ucl">{t}</p>' for t in lines))


# ── 公司 ─────────────────────────────────────────────────────────────────────

def co_html(c: str, intro: str) -> str:
    y = ysym(c)
    return ('<h3>公司</h3>' + (f'<p class="ucl">{_e(intro)}</p>' if intro else '<p class="st">簡介還沒有（每天下午補）。</p>')
            + f'<p class="uclk"><a href="{YF}{_e(y)}" target="_blank" rel="noopener">Yahoo Finance</a>'
            f'<a href="{SEC}{_e(y)}" target="_blank" rel="noopener">SEC 申報文件</a></p>')


# ── 分析師（數字給瀏覽器排；文字在 JS 的 ucAn） ──────────────────────────────────

def _an(a: dict | None) -> dict | None:
    """uscard 的分析師紀錄 → 頁面用的精簡版：家數、tp＝分析師的價位 [平均, 中位, 最高, 最低]、評等 5 格、
    今年／明年 {end, e: [平均, 家數, 去年], t90: 90 天前, r: [營收, 去年營收]（億美元）}、財報日、
    eh＝近 4 季實際 vs 預估 EPS、ud＝最近的評等調整（第 4 節 (d)）。"""
    if not a:
        return None
    out = {"n": a.get("n"), "tp": a.get("tp"), "rc": a.get("rc"), "ed": a.get("ed"), "ede": a.get("ede"),
           "eh": a.get("eh"), "ud": [r[:7] for r in (a.get("ud") or [])[:8]] or None}
    for k in ("y0", "y1"):
        y = a.get(k)
        if not y:
            continue
        e, r, t = y.get("e") or [], y.get("r") or [], y.get("t") or []
        out[k] = {"end": y.get("end"),
                  "e": [e[0], e[3], e[4]] if len(e) >= 5 else None,
                  "t90": t[4] if len(t) >= 5 else None,
                  "r": [r[0], r[4]] if len(r) >= 5 else None}
    return {k: v for k, v in out.items() if v is not None}


# ── 籌碼：做空、法人與內部人持股、內部人買賣（Yahoo；第 4 節 (d)） ──────────────────────

_TX = [(r"^Sale at price ([\d.,]+)(?: - ([\d.,]+))? per share\.?$", "賣出"),
       (r"^Purchase at price ([\d.,]+)(?: - ([\d.,]+))? per share\.?$", "買進"),
       (r"^Conversion of Exercise of derivative security at price ([\d.,]+)(?: - ([\d.,]+))? per share\.?$", "執行選擇權"),
       (r"^Stock Award\(Grant\) at price ([\d.,]+)(?: - ([\d.,]+))? per share\.?$", "公司給股"),
       (r"^Stock Gift at price ([\d.,]+)(?: - ([\d.,]+))? per share\.?$", "贈與")]


def tx_text(t: str) -> str:
    """Yahoo 的內部人交易說明 → 中文（認不得的照原文）。"""
    import re
    t = (t or "").strip()
    if not t:
        return "（沒有說明）"
    for pat, zh in _TX:
        m = re.match(pat, t)
        if m:
            a, b = m.group(1), m.group(2)
            if zh in ("公司給股", "贈與") or (a and float(a.replace(",", "")) == 0):
                return zh
            return f"{zh}，每股 {a}" + (f"～{b}" if b else "")
    return t


def chips(a: dict | None) -> dict | None:
    """uscard 的分析師紀錄 → 籌碼段：{"sh": [做空占流通股, 回補天數, 做空股數, 上個月, 資料日], "mh": [內部人, 法人, 法人家數],
    "ns": [期間, 買筆數, 買股數, 賣筆數, 賣股數, 淨買股數, 淨買占內部人持股], "tx": [[日期, 姓名, 職稱, 中文說明, 股數, 金額]]}；都沒有＝None。"""
    if not a:
        return None
    out = {k: a[k] for k in ("sh", "mh", "ns") if a.get(k)}
    if a.get("tx"):
        out["tx"] = [[r[0], r[1], r[2], tx_text(r[3]), r[4], r[5]] for r in a["tx"][:8]]
    return out or None


# ── 飆股檢查＋技術面（《超級績效》的條件換成美股資料；第 4 節 (f)） ─────────────────────

def _ma(xs: list, n: int, k: int) -> float | None:
    """第 k 天往前 n 天收盤的平均（中間有缺的就不算）。"""
    if k - n + 1 < 0:
        return None
    w = xs[k - n + 1:k + 1]
    return None if any(v is None for v in w) else sum(w) / n


def sx_check(g: list | None, rec: dict, cal: list, rs: float | None) -> dict:
    """g＝growth_rows（近 12 季）；rec＝卡片資料（每天收盤 c、50 日線 m、52 週高點 hi）；rs＝這週的強度（名單上的才有）。
    → {"ck": [[鍵, 條件, 符合（None＝資料不夠）]], "tt": [[條件, 符合]]（趨勢樣板 8 項）, "tech": {…}}。"""
    g = g or []

    def at(i, k):
        return g[i][k] if -len(g) <= i < len(g) else None

    def yoy_row(i):                                            # 去年同一季那一列（季底差 350～380 天）
        if not g or abs(i) > len(g):
            return None
        e = _d(g[i][0])
        for j in range(len(g) + i - 1, -1, -1):
            n = (e - _d(g[j][0])).days
            if 350 <= n <= 380:
                return g[j]
            if n > 380:
                break
        return None

    gt = (lambda a, b: None if a is None or b is None else a > b)
    ge = (lambda a, b: None if a is None else a >= b)
    ey0, ey1, ey2 = at(-1, 8), at(-2, 8), at(-3, 8)
    ry0, ry1, ry2 = at(-1, 3), at(-2, 3), at(-3, 3)
    gm0, gm1, gm2 = at(-1, 4), at(-2, 4), at(-3, 4)
    ly = yoy_row(-1)
    c33 = None
    if None not in (ey0, ey1, ey2, ry0, ry1, ry2, gm0, gm1, gm2):
        c33 = ey0 > ey1 > ey2 and ry0 > ry1 > ry2 and gm0 > gm1 > gm2
    ck = [["ey25", "最新一季 EPS 比去年同一季多 25% 以上", ge(ey0, 0.25)],
          ["eacc", "EPS 成長在加速（這一季的年增比上一季高）", gt(ey0, ey1)],
          ["ry25", "最新一季營收比去年同一季多 25% 以上", ge(ry0, 0.25)],
          ["racc", "營收成長在加速（這一季的年增比上一季高）", gt(ry0, ry1)],
          ["gmd", "毛利率比去年同一季高", gt(gm0, ly[4] if ly else None)],
          ["c33", "連三季變好：EPS 年增、營收年增、毛利率都一季比一季高", c33],
          ["roe15", "近四季 ROE 15% 以上", ge(at(-1, 9), 0.15)]]
    cs = rec.get("c") if len(rec.get("c") or []) == len(cal) else []
    ms = rec.get("m") if len(rec.get("m") or []) == len(cal) else []
    k = max((i for i, v in enumerate(cs) if v is not None), default=None)
    tech: dict = {}
    tt: list = []
    if k is not None:
        px = cs[k]
        m20, m150, m200 = _ma(cs, 20, k), _ma(cs, 150, k), _ma(cs, 200, k)
        m50 = ms[k] if k < len(ms) and ms[k] is not None else _ma(cs, 50, k)
        m200p = _ma(cs, 200, k - 20) if k >= 20 else None
        win = [v for v in cs[max(0, k - 251):k + 1] if v is not None]
        lo = min(win) if win else None
        hi = (rec.get("hi") or [None, None])[1] or (max(win) if win else None)
        tech = {"px": px, "m20": m20, "m50": m50, "m150": m150, "m200": m200, "hi": hi, "lo": lo, "rs": rs}
        both = (lambda a, b: None if a is None or b is None else a and b)
        tt = [["股價在 150 日與 200 日線之上", both(gt(px, m150), gt(px, m200))],
              ["150 日線高於 200 日線", gt(m150, m200)],
              ["200 日線上揚（比 20 個交易日前高）", gt(m200, m200p)],
              ["50 日線高於 150、200 日線", both(gt(m50, m150), gt(m50, m200))],
              ["股價在 50 日線之上", gt(px, m50)],
              ["股價比 52 週低點高 30% 以上", None if not lo else px >= lo * 1.3],
              ["股價在 52 週高點 25% 以內", None if not hi else px >= hi * 0.75],
              ["強度 70 以上", ge(rs, 70)]]
        tech = {k2: (None if v is None else round(v, 2)) for k2, v in tech.items()}
    return {"ck": ck, "tt": tt, "tech": tech}


# ── 成長、獲利、估值（SEC 季報＋股價；docs/lab_review_plan.md 第 4 節 (b)(c)） ─────────────────────

NQ_SHOW = 12          # 成長、獲利畫近幾季
PE_MAX = 300          # 本益比超過這個不算進自己的歷史（獲利接近 0 的那幾季）
PE_MIN_N = 104        # 和自己比至少要幾週（兩年）
PE_YEARS = 5


def _d(x: str) -> date:
    return date.fromisoformat(x)


def _monday(d: str) -> str:
    x = _d(d)
    return (x - timedelta(days=x.weekday())).isoformat()


def weekly_px(rec: dict, cal: list) -> list[tuple[str, float]]:
    """卡片資料的一檔 → 每週一點 [(那週最後一個交易日, 收盤)]：更早的每週點（wk）＋近一年每天的收盤併成每週；同一週併成一點。"""
    out: dict[str, list] = {}
    for w in rec.get("wk") or []:
        if w and w[1] is not None:
            out[_monday(w[0])] = [w[0], float(w[1])]
    cs = rec.get("c") or []
    for i, d in enumerate(cal):
        c = cs[i] if i < len(cs) else None
        if c is not None:
            out[_monday(d)] = [d, float(c)]
    return [(v[0], v[1]) for _, v in sorted(out.items())]


def _split_after(spl: list, fd: str) -> float:
    """公布日以後的分割倍數（之後的股價都已經換算成分割後，公布的 EPS、股數要跟著換算）。"""
    f = 1.0
    for d, r in spl or []:
        if d > fd and r and r > 0:
            f *= float(r)
    return f


_yoy, _four, _roe = UF.yoy, UF.four, UF.roe                 # 單季算法和同產業比較共用（usfin）


def _r(x, n=4):
    return None if x is None else round(x, n)


def growth_rows(F: dict) -> list[list]:
    """近 NQ_SHOW 季：[季底, 公布日, 營收（億美元）, 營收年增, 毛利率, 營益率, 淨利率, EPS, EPS 年增, 近四季 ROE]。"""
    q = F.get("q") or []
    out = []
    for i in range(max(0, len(q) - NQ_SHOW), len(q)):
        e, fd, rev, gp, oi, ni, eps, eq = q[i]
        mg = (lambda v: None if v is None or not rev or rev <= 0 else v / rev)
        out.append([e, fd, _r(rev / 100 if rev is not None else None, 2), _r(_yoy(q, 2, i)), _r(mg(gp)), _r(mg(oi)), _r(mg(ni)),
                    eps, _r(_yoy(q, 6, i)), _r(_roe(q, i))])
    return out


def _ttm_at(q: list, spl: list, t: str) -> float | None:
    """t 那天拿得到的近四季 EPS（公布日不晚於 t 的最後四季、要連續；換算成現在的股數）。"""
    ok = [i for i, r in enumerate(q) if r[1] <= t]
    if len(ok) < 4:
        return None
    i = ok[-1]
    ix = _four(q, i)
    if not ix or any(j not in ok for j in ix):
        return None
    es = [q[j][6] for j in ix]
    if None in es:
        return None
    return sum(e / _split_after(spl, q[j][1]) for e, j in zip(es, ix))


def _bvps_at(q: list, sh: list, spl: list, t: str) -> float | None:
    """t 那天拿得到的每股淨值：最新一季的股東權益 ÷ 最新的流通股數（都換算成現在的股數）。"""
    qe = [r for r in q if r[1] <= t and r[7]]
    se = [r for r in sh if r[1] <= t and r[2]]
    if not qe or not se:
        return None
    eq, n = qe[-1], se[-1]
    shares = n[2] * _split_after(spl, n[1])
    return eq[7] / shares if shares > 0 else None


def _pct_below(xs: list[float], x: float) -> int:
    return round(100 * sum(1 for v in xs if v < x) / len(xs))


def _q(xs: list[float], p: float) -> float:
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(len(s) - 1, int(k) + 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def valuation(F: dict, rec: dict, cal: list, px: float | None, an: dict | None = None) -> dict:
    """本益比（股價 ÷ 近四季 EPS）、淨值比、市值、殖利率（近 12 個月配息 ÷ 股價），本益比和淨值比和自己近 5 年每週比。
    股價是分割還原的，所以公布在分割以前的 EPS、股數都換算成分割後。"""
    q, sh = F.get("q") or [], F.get("sh") or []
    spl = rec.get("spl") or []
    wk = weekly_px(rec, cal)
    out: dict = {}
    if not wk or px is None:
        return out
    last = wk[-1][0]
    ttm = _ttm_at(q, spl, last)
    bv = _bvps_at(q, sh, spl, last)
    out["ttm"] = _r(ttm, 3)
    if ttm and ttm > 0:
        out["pe"] = round(px / ttm, 2)
    if bv and bv > 0:
        out["bvps"] = round(bv, 2)
        out["pb"] = round(px / bv, 2)
    se = [r for r in sh if r[2]]
    if se:
        out["cap"] = round(px * se[-1][2] * _split_after(spl, se[-1][1]) / 100, 1)       # 億美元（股數是百萬股）
    first = (_d(last) - timedelta(days=PE_YEARS * 365 + 2)).isoformat()
    pes, pbs, mon = [], [], {}
    for d, c in wk:
        if d <= first:
            continue
        t = _ttm_at(q, spl, d)
        if t and t > 0 and c / t < PE_MAX:
            pes.append(c / t)
            mon[d[:7]] = round(c / t, 2)
        b = _bvps_at(q, sh, spl, d)
        if b and b > 0:
            pbs.append(c / b)
    if len(pes) >= PE_MIN_N and out.get("pe") and out["pe"] < PE_MAX:
        out["peh"] = {"n": len(pes), "from": next(d for d, _ in wk if d > first)[:7], "pct": _pct_below(pes, out["pe"]),
                      "p20": round(_q(pes, .2), 2), "p50": round(_q(pes, .5), 2), "p80": round(_q(pes, .8), 2),
                      "lo": round(min(pes), 2), "hi": round(max(pes), 2)}
        out["pem"] = sorted(mon.items())
    if len(pbs) >= PE_MIN_N and out.get("pb"):
        out["pbh"] = {"pct": _pct_below(pbs, out["pb"]), "p50": round(_q(pbs, .5), 2)}
    # 殖利率：近 12 個月的配息（Yahoo，分割還原）÷ 股價；每年的配息
    divs = rec.get("div") or []
    c12 = (_d(last) - timedelta(days=365)).isoformat()
    d12 = [a for d, a in divs if d > c12]
    out["div12"] = round(sum(d12), 4)
    out["ndiv"] = len(d12)
    out["yld"] = round(sum(d12) / px, 5) if px else None
    yrs: dict[str, float] = {}
    y0 = int(wk[0][0][:4]) + 1                                 # 每年配息：只列走勢涵蓋整年的年份（第一年只有一部分），今年寫到幾月
    for d, a in divs:
        if int(d[:4]) >= y0:
            yrs[d[:4]] = yrs.get(d[:4], 0.0) + a
    if divs or yrs:
        for y in range(y0, int(last[:4]) + 1):
            yrs.setdefault(str(y), 0.0)
    out["dy"] = [[y, round(v, 4)] for y, v in sorted(yrs.items())]
    out["dym"] = int(last[5:7])
    if "wk" not in rec:
        out["short"] = True                                    # 只有近一年的股價（VER 1 的卡片資料）：自己的歷史還沒有
    # 用分析師今年度 EPS 預估算的本益比
    y0 = ((an or {}).get("y0") or {})
    e0 = (y0.get("e") or [None])[0]
    if e0 and e0 > 0:
        out["fpe"] = round(px / e0, 2)
        out["fend"] = y0.get("end")
    return out


def fin_view(F: dict | None, rec: dict, cal: list, px: float | None, an: dict | None, src: dict) -> dict | None:
    """→ 卡片的 "fin"：{"g": growth_rows, "v": valuation, "src": {"sec": SEC 資料日, "end": 最新一季季底, "fd": 公布日},
    "peer": 同產業（usfin.peers＋"nm": {代號: 公司名}、"d": GICS 的日期）}；沒有季報＝None。"""
    if not F or not F.get("q"):
        return None
    q = F["q"]
    out = {"g": growth_rows(F), "v": valuation(F, rec, cal, px, an), "src": {"sec": src.get("sec"), "end": q[-1][0], "fd": q[-1][1]}}
    pr = F.get("peer")
    if pr and pr.get("rows"):
        nm = src.get("names") or {}
        out["peer"] = {**pr, "nm": {r[0]: nm[r[0]] for r in pr["rows"] if nm.get(r[0])}, "d": src.get("gics")}
    return out


# ── 組起來 ─────────────────────────────────────────────────────────────────────

def order(G: dict) -> list[str]:
    """配置頁的順序：持有中、待買進、這週賣掉的、名單前幾名（手上沒有的，同 cfgpage._qm_cands）。"""
    n = G.get("n") or {}
    out = [r["c"] for r in G["rows"]] + [x["c"] for x in G["todo"]] + [x["c"] for x in G["gone"]]
    have = set(out)
    out += [x["c"] for x in n.get("list") or [] if x["c"] not in have][:FI.US_QM_SHOW]
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def build(G: dict, card: dict | None, cash: bool = False, fin: dict | None = None) -> dict | None:
    """→ D.cfg.us.uc；美股強勢品質股沒有在用（判定沒過、還沒有每週紀錄）＝None（配置頁的列照舊連 Yahoo Finance）。
    card＝uscard.load()（沒有＝走勢、分析師兩段寫「還沒有」）；fin＝usfin.load()（沒有＝成長、獲利、估值寫「還沒有」）。"""
    if not G.get("on") or not G.get("n"):
        return None
    n, W, nms = G["n"], G.get("W") or {}, G.get("nms") or {}
    card = card or {}
    cal = card.get("cal") or []
    S = card.get("s") or {}
    hold0 = {h["c"]: h for h in n.get("hold") or []}
    W0 = {h["c"]: h for h in W.get("hold") or []}
    rank = {x["c"]: (i + 1, x.get("rs")) for i, x in enumerate(n.get("list") or [])}
    held = {r["c"] for r in G["rows"]} | {x["c"] for x in G["gone"]}
    intros = CPG._us_intros()
    rows = {r["c"]: r for r in G["rows"]}
    out = {}
    for c in order(G):
        s = S.get(c) or {}
        cs = s.get("c") if len(s.get("c") or []) == len(cal) else None
        ms = s.get("m") if len(s.get("m") or []) == len(cal) else None
        px, ch = _last_px(cs or [])
        if px is None:                                         # 卡片資料還沒有這一檔：股價用每天的檢查或每週紀錄
            px = _num((W0.get(c) or {}).get("px")) or _num((hold0.get(c) or {}).get("px"))
        nm, what = CPG.us_label(c, nms)
        h0 = hold0.get(c)
        ent = None
        if c in rows and not rows[c].get("new") and h0 and h0.get("ent"):
            ent = [h0["ent"], _num(h0.get("epx"))]
        elif c in rows and rows[c].get("new"):
            ent = [rows[c]["ent"], None]
        g = next((x for x in G["gone"] if x["c"] == c), None)
        if g and h0 and h0.get("ent"):
            ent = [h0["ent"], _num(h0.get("epx"))]
        x = {"nm": nm, "en": str(nms.get(c) or ""), "what": what,
             "st": cfg_html(c, G, h0, W0.get(c), px, cash, rank.get(c)),
             "why": why_html(c, n, rank.get(c), c in held),
             "co": co_html(c, intros.get(c.upper(), "")),
             "px": px, "ch": None if ch is None else round(ch, 2), "pd": s.get("at") or (W0.get(c) or {}).get("d") or n.get("d"),
             "an": _an(s.get("an")), "an_at": s.get("an_at"), "ent": ent,
             "out": (g or {}).get("on") or (rows.get(c) or {}).get("sell")}
        if cs:
            x["c"], x["m"] = cs, ms
            vs = s.get("v")
            if vs and len(vs) == len(cal):
                x["v"] = vs
            for k in ("spl", "wk", "hi"):
                if s.get(k):
                    x[k] = s[k]
        F = ((fin or {}).get("s") or {}).get(c)
        try:
            fv = fin_view(F, s, cal, px, s.get("an"), fin or {})
        except Exception as e:                                 # noqa: BLE001 —— 算不出來只少這三段
            print(f"[美股個股卡] {c} 季報算不出來：{type(e).__name__}: {e}")
            fv = None
        if fv:
            x["fin"] = fv
        ch_ = chips(s.get("an"))
        if ch_:
            x["chip"] = ch_
        met = (n.get("met") or {}).get(c) or []               # 這週的五個條件（順序同 five_rows；強度在第一個）
        try:
            x["sx"] = sx_check((fv or {}).get("g"), {**s, "c": cs or [], "m": ms or []}, cal, _num(met[0]) if met else None)
        except Exception as e:                                 # noqa: BLE001
            print(f"[美股個股卡] {c} 飆股檢查算不出來：{type(e).__name__}: {e}")
        out[c] = x
    return {"o": list(out), "cal": cal if any("c" in v for v in out.values()) else [], "d": card.get("d"), "s": out}


JS = r"""
/* ---------- 美股個股卡（uscardpage.py；docs/lab_cfg_v2_plan.md 第 3.3 節）：配置頁美股列點了打開，網址 #us=代號。
   配置、為什麼選它、公司三段是 Python 組好的；走勢、分析師兩段在這裡畫。用同一個右側面板（#dv；電腦右側、手機全螢幕）。 ---------- */
const UCD=((CFG.us||{}).uc)||null;
function ucOn(){return !!(UCD&&UCD.s);}
function ucOpen(c){if(!ucOn()||!UCD.s[c])return false;if(!$('#dv').hidden&&/^#us=/.test(location.hash)){history.replaceState(null,'','#us='+encodeURIComponent(c));ucRender(c);return true;}
  PUSHED=true;location.hash='us='+encodeURIComponent(c);return true;}
function ucCur(){return decodeURIComponent((location.hash.match(/^#us=(.+)$/)||[])[1]||'');}
function ucStep(d){if(!ucOn())return;const o=UCD.o||[],i=o.indexOf(ucCur()),t=o[i+d];if(i>=0&&t)ucOpen(t);}
function ucMd(d){return d?`${+d.slice(5,7)}/${+d.slice(8,10)}`:'—';}
function ucPx(x){return x==null?'—':x.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function ucRender(c,keep){const S=ucOn()&&UCD.s[c];if(!S){hideStock();return;}
  const dv=$('#dv'),pane=isPane(),st0=keep?dv.scrollTop:0;
  dv.classList.toggle('pane',pane);document.body.classList.toggle('pane',pane);dv.hidden=false;lockBody(!pane);
  const o=UCD.o||[],i=o.indexOf(c),pv=i>0,nx=i>=0&&i<o.length-1;
  const secs=[['uc-st','配置'],['uc-why','為什麼選它'],['uc-px','走勢'],['uc-sx','飆股檢查'],['uc-gr','成長'],['uc-pf','獲利'],['uc-val','估值'],['uc-ind','同產業'],['uc-ch','籌碼'],['uc-an','分析師'],['uc-co','公司']];
  const sub=[`${i+1}／${o.length}`,c].concat(S.what?[S.what]:[]);
  let h=`<div class=dvh><div class=dvt><a class="nv${pv?'':' off'}" id=pv title="上一檔（←）">‹</a>`+
   `<div class=ttl><b>${esc(S.nm)}</b><span class=cd>${sub.map(esc).join(' · ')}</span></div>`+
   `<div class=pxw><b>${ucPx(S.px)}</b>${S.ch!=null?sgn(S.ch,2,'%'):''}</div><a class="nv${nx?'':' off'}" id=nx title="下一檔（→）">›</a><a class=x id=x title="關閉（Esc）">×</a></div>`+
   `<nav class=cnav>${secs.map(([id,t])=>`<a data-cto=${id}>${t}</a>`).join('')}</nav></div>`;
  h+=`<section class="csec uc" id=uc-st>${S.st}</section><section class="csec uc" id=uc-why>${S.why}</section>`;
  h+=`<section class="csec uc" id=uc-px>${ucPxSec(c,S)}</section><section class="csec uc" id=uc-sx>${ucSx(S)}</section><section class="csec uc" id=uc-gr>${ucGr(S)}</section>`;
  h+=`<section class="csec uc" id=uc-pf>${ucPf(S)}</section><section class="csec uc" id=uc-val>${ucVal(S)}</section>`;
  h+=`<section class="csec uc" id=uc-ind>${ucInd(c,S)}</section><section class="csec uc" id=uc-ch>${ucCh(S)}</section><section class="csec uc" id=uc-an>${ucAn(c,S)}</section>`;
  h+=`<section class="csec uc" id=uc-co>${S.co}</section>`;
  $('#dvin').innerHTML=h;dv.scrollTop=st0;
  $('#x').onclick=closeStock;$('#pv').onclick=()=>ucStep(-1);$('#nx').onclick=()=>ucStep(1);
  $$('#dvin [data-cto]').forEach(a=>a.onclick=()=>{const t=document.getElementById(a.dataset.cto);if(t)dv.scrollTo({top:dv.scrollTop+t.getBoundingClientRect().top-dv.getBoundingClientRect().top-$('#dvin .dvh').offsetHeight+2,behavior:'smooth'});});
  $$('#dvin [data-ucrg]').forEach(b=>b.onclick=()=>{if(b.disabled)return;UCRG=b.dataset.ucrg;$$('#dvin [data-ucrg]').forEach(x=>x.classList.toggle('on',x===b));ucDraw(S);});
  ucDraw(S);cspy();}
/* 走勢：6 個月、1 年＝每天（收盤、50 日線、成交量）；3 年、5 年＝每週一點（更早的每週點＋近一年每天併成每週，那週最後一個交易日的收盤）。
   52 週高點（橫虛線）、買進點 ▲、賣出點 ▼；游標移上去看那天（那週）的數字 */
const UCRGS=[['6m','6 個月',183],['1y','1 年',365],['3y','3 年',1096],['5y','5 年',1828]];
let UCRG='1y';
function ucDay(d){return Date.UTC(+d.slice(0,4),+d.slice(5,7)-1,+d.slice(8,10));}
function ucIso(t){return new Date(t).toISOString().slice(0,10);}
function ucMon(d){const t=ucDay(d);return ucIso(t-((new Date(t).getUTCDay()+6)%7)*864e5);}
function ucDt(d){return d?`${d.slice(0,4)}/${+d.slice(5,7)}/${+d.slice(8,10)}`:'—';}
function ucSeries(S,rg){const cal=UCD.cal||[],R=UCRGS.find(x=>x[0]===rg)||UCRGS[1],last=cal[cal.length-1]||'',st=last?ucIso(ucDay(last)-R[2]*864e5):'';
  const P={d:[],c:[],m:[],v:[],wk:R[2]>365};
  if(!P.wk){cal.forEach((d,i)=>{if(d<=st||S.c[i]==null)return;P.d.push(d);P.c.push(S.c[i]);P.m.push(S.m?S.m[i]:null);P.v.push(S.v?S.v[i]:null);});return P;}
  const W=new Map();(S.wk||[]).forEach(w=>W.set(ucMon(w[0]),[w[0],w[1],w[2]]));
  cal.forEach((d,i)=>{if(S.c[i]==null)return;const k=ucMon(d),v=S.v?S.v[i]:null,o=W.get(k);
    if(!o)W.set(k,[d,S.c[i],v]);else if(o[0]<d){o[0]=d;o[1]=S.c[i];o[2]=o[2]==null||v==null?null:o[2]+v;}});
  [...W.keys()].sort().forEach(k=>{const o=W.get(k);if(o[0]<=st)return;P.d.push(o[0]);P.c.push(o[1]);P.m.push(null);P.v.push(o[2]);});
  return P;}
function ucIdx(P,d){if(!d)return -1;if(P.wk){const k=ucMon(d);return P.d.findIndex(x=>ucMon(x)===k);}return P.d.indexOf(d);}
function ucPxSec(c,S){if(!S.c)return `<h3>走勢</h3><p class=st>走勢資料還沒有（每天美股收盤後更新）。</p>`;
  const lw=!!S.wk;if(!lw&&(UCRG==='3y'||UCRG==='5y'))UCRG='1y';
  const bt=UCRGS.map(([k,t])=>`<button type=button data-ucrg=${k} class="${k===UCRG?'on':''}"${!lw&&(k==='3y'||k==='5y')?' disabled title="更早的走勢還沒有（每天美股收盤後更新）"':''}>${t}</button>`).join('');
  return `<h3>走勢<span class=sub>${ucMd((UCD.cal||[]).slice(-1)[0])} 收盤</span></h3><div class=ucrg role=group aria-label="期間">${bt}</div><div class=ucw id=ucw></div><div id=uclg></div>`;}
function ucDraw(S){const w=$('#ucw');if(!w||!S.c)return;const W=Math.max(280,Math.floor($('#dvin').clientWidth-32));
  const P=ucSeries(S,UCRG);if(!P.d.length){w.innerHTML='<p class=st>這段期間沒有股價。</p>';$('#uclg').innerHTML='';return;}
  w.innerHTML=ucSvg(S,P,W)+'<div class=uctip id=uctip hidden></div>';
  const first=P.d[0],last=P.d[P.d.length-1],hasM=P.m.some(v=>v!=null),hasV=P.v.some(v=>v!=null);
  const lg=`<div class=lg><span><i style="background:#2563c9"></i>收盤</span>`+(hasM?`<span><i class=ucdsh></i>50 日線</span>`:'')+
    (S.hi?`<span><i class=uchi></i>52 週高點 ${ucPx(S.hi[1])}（${ucMd(S.hi[0])}）</span>`:'')+
    (hasV?`<span><i style="background:#9aa5b1"></i>${P.wk?'每週':'每天'}成交量</span>`:'')+
    (S.ent&&S.ent[0]>=first?`<span><b class=up>▲</b>${ucMd(S.ent[0])} 買進</span>`:'')+(S.out&&S.out<=last&&S.out>=first?`<span><b class=dn>▼</b>${ucMd(S.out)} 賣出</span>`:'')+`</div>`;
  const sp=(S.spl||[]).filter(x=>x[0]>first);
  $('#uclg').innerHTML=lg+(sp.length?`<p class=note>這段期間有分割（${sp.map(x=>`${ucDt(x[0])} 一股變 ${x[1]} 股`).join('、')}），之前的股價已經換算成分割後的價格。</p>`:'');
  ucBind(S,P);}
function ucSvg(S,P,W){const n=P.d.length,pl=6,pr=48,pt=10,ph=196,hasV=P.v.some(v=>v!=null),vg=hasV?10:0,vh=hasV?46:0,HH=ph+vg+vh+20;
  const vs=[...P.c,...P.m].filter(v=>v!=null);if(S.ent&&S.ent[1]!=null&&S.ent[0]>=P.d[0])vs.push(S.ent[1]);if(S.hi)vs.push(S.hi[1]);
  let lo=Math.min(...vs),hi=Math.max(...vs);const pad=(hi-lo)*.06||hi*.05;lo-=pad;hi+=pad;
  const x=i=>pl+(W-pl-pr)*(n>1?i/(n-1):.5),y=v=>pt+(ph-pt)*(1-(v-lo)/(hi-lo));
  const st=(()=>{const r=(hi-lo)/4,p=Math.pow(10,Math.floor(Math.log10(r))),m=r/p;return (m<1.5?1:m<3?2:m<7?5:10)*p;})();
  let s='';for(let t=Math.ceil(lo/st)*st;t<=hi;t+=st){const yy=y(t).toFixed(1);
    s+=`<line x1=${pl} x2=${W-pr} y1=${yy} y2=${yy} stroke="#e3e7ec"/><text x=${W-pr+6} y=${(+yy+4).toFixed(0)} font-size=11 fill="#727e8c">${t.toLocaleString('en-US',{maximumFractionDigits:st<1?2:0})}</text>`;}
  const lab=(i,t)=>`<text x=${x(i).toFixed(1)} y=${HH-5} font-size=11 fill="#727e8c" text-anchor=middle>${t}</text>`;
  if(!P.wk){let pm='';const ev=n>160?3:1;P.d.forEach((d,i)=>{const m=+d.slice(5,7);if(d.slice(0,7)===pm)return;pm=d.slice(0,7);
      if(i>4&&i<n-6&&(m-1)%ev===0)s+=lab(i,m===1?`${d.slice(0,4)} 年`:`${m} 月`);});}
  else{let py='';P.d.forEach((d,i)=>{const yr=d.slice(0,4);if(yr===py)return;py=yr;if(i>2&&i<n-4)s+=lab(i,yr);});}
  const path=a=>{let p='',up=false;a.forEach((v,i)=>{if(v==null){up=false;return;}p+=`${up?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`;up=true;});return p;};
  if(S.hi){const yy=y(S.hi[1]).toFixed(1);s+=`<line class=uchl x1=${pl} x2=${W-pr} y1=${yy} y2=${yy} stroke="#727e8c" stroke-width=1 stroke-dasharray="2 3"/>`;}
  if(P.m.some(v=>v!=null))s+=`<path d="${path(P.m)}" fill=none stroke="#f59e0b" stroke-width=1.5 stroke-dasharray="4 3"/>`;
  s+=`<path d="${path(P.c)}" fill=none stroke="#2563c9" stroke-width=${P.wk?1.5:1.8} />`;
  s+=`<circle cx=${x(n-1).toFixed(1)} cy=${y(P.c[n-1]).toFixed(1)} r=3 fill="#2563c9"/>`;
  if(hasV){const vm=Math.max(...P.v.filter(v=>v!=null),1),y0=ph+vg+vh,bw=Math.max(1,(W-pl-pr)/Math.max(1,n)*.7);
    P.v.forEach((v,i)=>{if(v==null)return;const h=Math.max(.5,v/vm*vh),upd=i===0||P.c[i]>=P.c[i-1];
      s+=`<rect x=${(x(i)-bw/2).toFixed(1)} y=${(y0-h).toFixed(1)} width=${bw.toFixed(1)} height=${h.toFixed(1)} fill="${upd?'#d33a34':'#1f9d57'}" fill-opacity=.45 />`;});}
  const tri=(d,v,up)=>{const i=ucIdx(P,d);if(i<0)return '';const xx=x(i),yy=y(v!=null&&!P.wk?v:P.c[i]);if(!isFinite(yy))return '';
    return up?`<path d="M${xx.toFixed(1)},${(yy+4).toFixed(1)}l-5,9h10z" fill="#d33a34"/>`:`<path d="M${xx.toFixed(1)},${(yy-4).toFixed(1)}l-5,-9h10z" fill="#1f9d57"/>`;};
  if(S.ent)s+=tri(S.ent[0],S.ent[1],true);
  if(S.out)s+=tri(S.out,null,false);
  return `<svg width=${W} height=${HH} viewBox="0 0 ${W} ${HH}" data-pl=${pl} data-pr=${pr}>${s}<line class=uccx x1=0 x2=0 y1=${pt} y2=${ph+vg+vh} stroke="#9aa5b1" stroke-dasharray="2 2" visibility=hidden /></svg>`;}
function ucBind(S,P){const w=$('#ucw');if(!w)return;const sv=w.querySelector('svg'),tip=$('#uctip');if(!sv||!tip)return;const cx=sv.querySelector('.uccx');
  const n=P.d.length,pl=+sv.dataset.pl,pr=+sv.dataset.pr,W=+sv.getAttribute('width');
  const show=ev=>{const r=sv.getBoundingClientRect(),px=(ev.touches?ev.touches[0].clientX:ev.clientX)-r.left;
    let i=Math.round((px-pl)/(W-pl-pr)*(n-1));i=Math.max(0,Math.min(n-1,i));
    const xx=pl+(W-pl-pr)*(n>1?i/(n-1):.5);cx.setAttribute('x1',xx);cx.setAttribute('x2',xx);cx.setAttribute('visibility','visible');
    const m=P.m[i],v=P.v[i];tip.innerHTML=`<b>${P.wk?ucDt(P.d[i])+' 那週':mdw(P.d[i])}</b><div>收盤 ${ucPx(P.c[i])}</div>`+
      (m!=null?`<div>50 日線 ${ucPx(m)}（收盤${P.c[i]>=m?'高':'低'} ${Math.abs(P.c[i]/m*100-100).toFixed(1)}%）</div>`:'')+
      (v!=null?`<div>${P.wk?'那週':''}成交 ${f(v/10,0)} 萬股</div>`:'');
    tip.hidden=false;const tw=tip.offsetWidth;tip.style.left=Math.max(0,Math.min(W-tw,xx+(xx>W/2?-tw-8:8)))+'px';};
  const hide=()=>{tip.hidden=true;cx.setAttribute('visibility','hidden');};
  sv.addEventListener('mousemove',show);sv.addEventListener('mouseleave',hide);sv.addEventListener('touchstart',show,{passive:true});sv.addEventListener('touchmove',show,{passive:true});}
/* 成長、獲利、估值（SEC 季報＋股價；uscardpage.fin_view 算好的數字） */
function ucQ(e){return `${e.slice(2,4)}/${+e.slice(5,7)}`;}
function ucWd(){const w=Math.max(260,Math.floor($('#dvin').clientWidth-32));return {w,w2:isPane()||w>700?Math.floor((w-12)/2):w};}
function ucYi(v){return v==null?'—':f(v,v>=100?0:v>=10?1:2)+' 億';}
function ucPc(v,d=1){return v==null?'—':f(v*100,d)+'%';}
function ucYoY(v){return v==null?'':`年增 ${pctT(v*100,0)}`;}
function ucFinNo(t){return `<h3>${t}</h3><p class=st>季報還沒有（每週六更新）。</p>`;}
function ucFinSub(F){return `SEC 季報・最新一季到 ${ucDt(F.src.end)}（${ucMd(F.src.fd)} 公布）`;}
function ucGr(S){const F=S.fin;if(!F||!F.g.length)return ucFinNo('成長');
  const {w2}=ucWd(),g=F.g,L=g.map(r=>ucQ(r[0])),l=g[g.length-1];
  const r4=g.length>=8?[g.slice(-4),g.slice(-8,-4)].map(a=>a.every(r=>r[2]!=null)?a.reduce((t,r)=>t+r[2],0):null):[null,null];
  let h=`<h3>成長<span class=sub>${esc(ucFinSub(F))}</span></h3><div class="kpis kps k3">`+
    kp('最新一季營收','',ucYi(l[2]),ucYoY(l[3]),cls(l[3]))+kp('最新一季 EPS','',l[7]==null?'—':f(l[7],2),ucYoY(l[8]),cls(l[8]))+
    kp('近四季營收','',ucYi(r4[0]),r4[0]!=null&&r4[1]?`比前四季 ${pctT((r4[0]/r4[1]-1)*100,0)}`:'',r4[0]!=null&&r4[1]?cls(r4[0]-r4[1]):'')+`</div><div class=cgrid style="margin-top:10px">`;
  h+=`<div class=cbox><h4>季營收（億美元）・年增</h4>${svgBars(g.map(r=>r[2]),L,{W:w2,H:120,col:()=>'#8fa6c8',fmt:v=>f(v,v>=100?0:1),al:'季營收'})}`+
    `${svgLines([{v:g.map(r=>r[3]==null?null:r[3]*100),c:'#2563c9',n:'營收年增'}],L,{W:w2,H:100,zero:1,fmt:v=>f(v,0)+'%'})}${lg([['#2563c9','營收年增（比去年同一季）']])}</div>`;
  h+=`<div class=cbox><h4>單季 EPS（美元）・年增</h4>${svgBars(g.map(r=>r[7]),L,{W:w2,H:120,fmt:v=>f(v,2),al:'單季 EPS'})}`+
    `${svgLines([{v:g.map(r=>r[8]==null?null:Math.max(-100,Math.min(300,r[8]*100))),c:'#d33a34',n:'EPS 年增'}],L,{W:w2,H:100,zero:1,fmt:v=>f(v,0)+'%'})}${lg([['#d33a34','EPS 年增（上限 300%；去年同一季虧損的不算）']])}</div></div>`;
  h+=`<details class=mr><summary>近 ${g.length} 季明細</summary><div class=tw><table class=qt><thead><tr><th>季底</th><th>營收（億美元）</th><th>年增</th><th>毛利率</th><th>營益率</th><th>淨利率</th><th>EPS</th><th>EPS 年增</th></tr></thead><tbody>`+
    g.slice().reverse().map(r=>`<tr><td>${ucDt(r[0])}</td><td>${r[2]==null?'—':f(r[2],r[2]>=100?0:2)}</td><td>${r[3]==null?'—':pctT(r[3]*100,1)}</td><td>${ucPc(r[4])}</td><td>${ucPc(r[5])}</td><td>${ucPc(r[6])}</td><td>${r[7]==null?'—':f(r[7],2)}</td><td>${r[8]==null?'—':pctT(r[8]*100,0)}</td></tr>`).join('')+
    `</tbody></table></div></details><p class=note>單季數字；第四季＝全年減前三季（EPS 可能和公司公布的差一點）。季底照公司自己的會計年度。</p>`;
  return h;}
function ucPf(S){const F=S.fin;if(!F||!F.g.length)return ucFinNo('獲利');
  const {w2}=ucWd(),g=F.g,L=g.map(r=>ucQ(r[0])),l=g[g.length-1],lr=[...g].reverse().find(r=>r[9]!=null);
  const ms=[[4,'#a16207','毛利率'],[5,'#2563c9','營益率'],[6,'#d33a34','淨利率']].filter(([k])=>g.some(r=>r[k]!=null));
  let h=`<h3>獲利<span class=sub>三率與近四季 ROE</span></h3><div class="kpis kps${ms.length===3?' k4':''}">`+
    ms.map(([k,,t])=>kp(t,'',ucPc(l[k]),'最新一季')).join('')+kp('近四季 ROE','',lr?ucPc(lr[9]):'—','淨利 ÷ 股東權益')+`</div>`;
  if(ms.length)h+=`<div class=cgrid style="margin-top:10px"><div class=cbox><h4>${ms.map(m=>m[2]).join('・')}（單季）</h4>${svgLines(ms.map(([k,c,n])=>({v:g.map(r=>r[k]==null?null:r[k]*100),c,n})),L,{W:w2,H:140,zero:1,fmt:v=>f(v,0)+'%'})}${lg(ms.map(([,c,t])=>[c,t]))}</div>`+
    `<div class=cbox><h4>近四季 ROE</h4>${svgLines([{v:g.map(r=>r[9]==null?null:r[9]*100),c:'#d33a34',n:'ROE'}],L,{W:w2,H:140,zero:1,fmt:v=>f(v,0)+'%'})}${lg([['#d33a34','近四季淨利 ÷ 期初期末股東權益的平均']])}</div></div>`;
  if(!g.some(r=>r[4]!=null))h+=`<p class=note>這家公司的季報沒有列毛利。</p>`;
  if(lr&&lr[9]>1)h+=`<p class=note>ROE 很高是因為股東權益很小（多半是公司一直買回自己的股票）。</p>`;
  return h;}
function ucVal(S){const F=S.fin;if(!F)return ucFinNo('估值');const V=F.v||{},px=S.px;let h=`<h3>估值<span class=sub>和自己近 5 年比</span></h3>`;
  h+=`<div class="kpis kps k4">`+kp('本益比','',V.pe==null?'—':f(V.pe,1)+' 倍',V.ttm!=null?`近四季 EPS ${f(V.ttm,2)}`:'')+
    kp('淨值比','',V.pb==null?'—':f(V.pb,1)+' 倍',V.bvps!=null?`每股淨值 ${f(V.bvps,2)}`:'')+
    kp('殖利率','',V.ndiv?ucPc(V.yld,2):'沒有配息',V.ndiv?`近 12 個月 ${f(V.div12,2)} 美元`:'近 12 個月')+
    kp('市值','',V.cap==null?'—':f(V.cap,V.cap>=100?0:1)+' 億美元','')+`</div>`;
  const ph=V.peh;
  if(V.ttm!=null&&V.ttm<=0)h+=`<p class=ucl>近四季 EPS 是虧損，本益比不適用。</p>`;
  else if(ph&&V.pe!=null){const tt=V.ttm,a=ph.p20*tt,b=ph.p80*tt,m=ph.p50*tt,lo=Math.min(a,px)*0.85,hi=Math.max(b,px)*1.1,pos=v=>Math.max(0,Math.min(100,(v-lo)/(hi-lo)*100));
    h+=`<div class=colead style="margin-top:10px">本益比 ${f(V.pe,1)} 倍，比自己近 5 年 ${ph.pct}% 的日子高${ph.pct>=80?'（偏貴）':ph.pct<=20?'（偏便宜）':''}。</div>`+
      `<div class=vband><div class=bg></div><div class=bd style="left:${pos(a)}%;width:${Math.max(1,pos(b)-pos(a))}%"></div><div class=md style="left:${pos(m)}%"></div><div class=now style="left:${pos(px)}%" title="現價 ${ucPx(px)}"></div></div>`+
      `<div class=vlab><span>${ucPx(lo)}</span><span>現價 ${ucPx(px)}</span><span>${ucPx(hi)}</span></div>`+
      `<p class=st style="margin-top:6px">近 5 年有 6 成的日子本益比在 ${f(ph.p20,1)}～${f(ph.p80,1)} 倍（中間 ${f(ph.p50,1)} 倍；最低 ${f(ph.lo,1)}、最高 ${f(ph.hi,1)}），乘上近四季 EPS ${f(tt,2)}，股價是 <b>${ucPx(a)}</b>～<b>${ucPx(b)}</b>（中間 ${ucPx(m)}）。獲利變了，這個位置也會跟著變。</p>`;
    const pm=V.pem||[];if(pm.length>=12){const {w}=ucWd(),L=pm.map(x=>`${x[0].slice(2,4)}/${+x[0].slice(5,7)}`),k=pm.length;
      h+=`<div class=cbox style="margin-top:10px"><h4>本益比（每月）</h4>${svgLines([{v:pm.map(x=>x[1]),c:'#2563c9',n:'本益比'},{v:Array(k).fill(ph.p20),c:'#9aa5b1',n:'6 成的日子以內',dash:1,w:1},{v:Array(k).fill(ph.p80),c:'#9aa5b1',n:'6 成的日子以內',dash:1,w:1}],L,{W:w,H:130,fmt:v=>f(v,0)+' 倍'})}${lg([['#2563c9','本益比'],['#9aa5b1','6 成的日子在兩條虛線之間',1]])}</div>`;}}
  else if(V.pe!=null)h+=`<p class=st>本益比和自己的過去比，要至少兩年有獲利的資料。</p>`;
  if(V.pbh&&V.pb!=null)h+=`<p class=ucl>淨值比 ${f(V.pb,1)} 倍，比自己近 5 年 ${V.pbh.pct}% 的日子高（中間 ${f(V.pbh.p50,1)} 倍）。</p>`;
  if(V.fpe!=null)h+=`<p class=ucl>用分析師${V.fend&&+V.fend.slice(5,7)!==12?`到 ${+V.fend.slice(0,4)} 年 ${+V.fend.slice(5,7)} 月的年度`:'今年'}的 EPS 預估算：本益比 ${f(V.fpe,1)} 倍。</p>`;
  const dy=(V.dy||[]).slice(-6),cy=(UCD.cal||[]).slice(-1)[0];if(dy.some(x=>x[1]>0))h+=`<p class=st>每年配息（美元／股）：${dy.map(([y,v])=>`${y}${cy&&y===cy.slice(0,4)&&V.dym<12?`（到 ${V.dym} 月）`:''} <b>${f(v,2)}</b>`).join('　')}</p>`;
  if(V.short)h+=`<p class=note>更早的股價還沒有（每天美股收盤後更新），本益比先只和近一年比。</p>`;
  return h;}
/* 飆股檢查＋技術面（uscardpage.sx_check 算好的）、同產業（usfin.peers）、籌碼（Yahoo：做空、持股、內部人） */
function ucMark(v,t){return `<span class=${v===true?'ok':v===false?'no':'na'}>${v===true?(t?'✓ 符合':'✓'):v===false?'✗':'—'}</span>`;}
function ucSx(S){const X=S.sx;if(!X)return `<h3>飆股檢查</h3><p class=st>資料還沒有。</p>`;
  const ck=X.ck||[],tt=X.tt||[],T=X.tech||{},tok=tt.filter(x=>x[1]===true).length,tno=tt.filter(x=>x[1]===false).length,tn=tt.filter(x=>x[1]!=null).length;
  const rows=ck.concat(tt.length?[['tt',`趨勢樣板 8 項都符合（${tok}／8）`,tno?false:(tn===8?true:null)]]:[]);
  const ok=rows.filter(r=>r[2]===true).length,av=rows.filter(r=>r[2]!=null).length;
  let h=`<h3>飆股檢查<span class=sub>符合 ${ok}／${av} 項</span></h3><div class=tw><table class=chkt><thead><tr><th class=l>條件</th><th>這檔</th></tr></thead><tbody>`+
    rows.map(r=>`<tr><td class=l>${esc(r[1])}</td><td>${ucMark(r[2],1)}</td></tr>`).join('')+`</tbody></table></div>`;
  if(tt.length)h+=`<details class=mr><summary>趨勢樣板 8 項明細（${tok}／8）</summary><ul class=chk>${tt.map(x=>`<li>${ucMark(x[1])}<span>${esc(x[0])}</span><span></span></li>`).join('')}</ul></details>`;
  if(T.px!=null){const dd=a=>a==null?'—':`${ucPx(a)}<span class=st>（收盤${T.px>=a?'高':'低'} ${f(Math.abs(T.px/a*100-100),1)}%）</span>`;
    h+=`<h4 class=uch4>技術面</h4><div class=tw><table class="qt ucqt"><tbody>`+[['20 日線',T.m20],['50 日線',T.m50],['150 日線',T.m150],['200 日線',T.m200]].map(([n,v])=>`<tr><td class=l>${n}</td><td>${dd(v)}</td></tr>`).join('')+
      (T.hi!=null?`<tr><td class=l>52 週高點</td><td>${ucPx(T.hi)}<span class=st>（收盤低 ${f(Math.max(0,100-T.px/T.hi*100),1)}%）</span></td></tr>`:'')+
      (T.lo!=null?`<tr><td class=l>52 週低點</td><td>${ucPx(T.lo)}<span class=st>（收盤高 ${f(T.px/T.lo*100-100,1)}%）</span></td></tr>`:'')+
      (T.rs!=null?`<tr><td class=l>強度</td><td>${f(T.rs,0)}<span class=st>（這週，勝過幾 % 的美股）</span></td></tr>`:'')+`</tbody></table></div>`;
    const m=[T.m20,T.m50,T.m150,T.m200],bull=m.every(v=>v!=null)&&T.px>T.m20&&T.m20>T.m50&&T.m50>T.m150&&T.m150>T.m200;
    h+=`<p class=st>${bull?'均線多頭排列：收盤高於 20 日線，20、50、150、200 日線由上到下排好。':'均線沒有完整的多頭排列（收盤、20、50、150、200 日線由上到下）。'}</p>`;}
  return h+`<p class=note>條件照《超級績效》（Minervini）找飆股看的：獲利與營收高成長而且在加速、毛利率變好、股價在長期上升趨勢、強度高。季報用 SEC 的數字；強度只有這週名單上的股票才有。</p>`;}
function ucInd(c,S){const P=(S.fin||{}).peer;if(!P)return `<h3>同產業</h3><p class=st>${S.fin?'這家公司不在 S&amp;P 500／400／600 裡，沒有同產業的分類可以比。':'季報還沒有（每週六更新）。'}</p>`;
  const pc=v=>v==null?'—':pctT(v*100,0);
  let h=`<h3>同產業<span class=sub>GICS：${esc(P.ind)}</span></h3><p class=st>S&amp;P 1500 裡這個細產業有 ${P.n} 家，${esc(c)} 市值排第 ${P.rk}；下面是市值最接近的幾家。</p>`;
  h+=`<div class=tw><table class="qt ucpeer"><thead><tr><th class=l>公司</th><th>市值<span>億美元</span></th><th>營收年增</th><th>營益率</th><th>ROE</th><th>本益比</th><th>近一年<span>股價</span></th></tr></thead><tbody>`+
    P.rows.map(r=>`<tr${r[0]===c?' class=ucme':''}><td class=l><b>${esc(r[0])}</b>${P.nm&&P.nm[r[0]]?`<span class=st>${esc(P.nm[r[0]])}</span>`:''}</td><td>${r[1]==null?'—':f(r[1],r[1]>=100?0:1)}</td><td>${pc(r[2])}</td><td>${r[3]==null?'—':f(r[3]*100,1)+'%'}</td><td>${r[4]==null?'—':f(r[4]*100,0)+'%'}</td><td>${r[5]==null?'—':f(r[5],1)}</td><td>${pc(r[6])}</td></tr>`).join('')+`</tbody></table></div>`;
  return h+`<p class=note>營收年增＝最新一季比去年同一季；營益率＝近四季營業利益 ÷ 營收；ROE＝近四季；本益比＝市值 ÷ 近四季淨利（虧損的不算）。產業分類是維基百科上 S&amp;P 500／400／600 成分股表的 GICS 細產業${P.d?`（${ucMd(P.d)} 抓的）`:''}。</p>`;}
function ucCh(S){const C=S.chip;if(!C)return `<h3>籌碼</h3><p class=st>資料還沒有（每天美股收盤後更新）。</p>`;
  const sh=C.sh,mh=C.mh,ns=C.ns,tx=C.tx||[],w=v=>f(v/1e4,v>=1e6?0:1)+' 萬股';
  let h=`<h3>籌碼<span class=sub>Yahoo Finance</span></h3><div class="kpis kps k4">`+
    kp('做空占流通股','',sh&&sh[0]!=null?ucPc(sh[0],1):'—',sh&&sh[1]!=null?`回補要 ${f(sh[1],1)} 天`:'')+
    kp('做空股數','',sh&&sh[2]!=null?w(sh[2]):'—',sh&&sh[2]!=null&&sh[3]?`比上個月 ${pctT((sh[2]/sh[3]-1)*100,0)}`:'')+
    kp('法人持股','',mh&&mh[1]!=null?ucPc(mh[1],1):'—',mh&&mh[2]?`${f(mh[2],0)} 家`:'')+
    kp('內部人持股','',mh&&mh[0]!=null?ucPc(mh[0],1):'—','董事、主管、大股東')+`</div>`;
  if(sh&&sh[4])h+=`<p class=st>做空資料到 ${ucDt(sh[4])}（每月公布兩次）；回補要幾天＝做空股數 ÷ 平常一天的成交量。</p>`;
  if(mh&&mh[1]!=null&&mh[1]>1)h+=`<p class=note>法人持股超過 100%：借出去放空的股票，被別的法人買走後又算一次。</p>`;
  if(ns)h+=`<p class=ucl>內部人近 ${ns[0]==='6m'?'6 個月':esc(ns[0])}：取得 ${ns[1]==null?'—':f(ns[1],0)} 筆、${ns[2]==null?'—':w(ns[2])}（含執行選擇權、公司給股），賣出 ${ns[3]==null?'—':f(ns[3],0)} 筆、${ns[4]==null?'—':w(ns[4])}`+
    (ns[5]!=null?`；淨${ns[5]>=0?'增加':'減少'} ${w(Math.abs(ns[5]))}${ns[6]!=null?`（內部人持股的 ${ucPc(Math.abs(ns[6]),1)}）`:''}`:'')+`。</p>`;
  if(tx.length)h+=`<details class=mr><summary>最近的內部人交易（${tx.length} 筆）</summary><div class=tw><table class="qt ucpeer uctx"><thead><tr><th>日期</th><th class=l>誰</th><th class="l ucdk">內容</th><th>股數</th><th>金額<span>萬美元</span></th></tr></thead><tbody>`+
    tx.map(r=>`<tr><td>${ucMd(r[0])}</td><td class=l>${esc(r[1])}<span class=st>${esc(r[2])}</span><span class="ucmb">${esc(r[3])}</span></td><td class="l ucdk">${esc(r[3])}</td><td>${r[4]==null?'—':f(r[4],0)}</td><td>${r[5]?f(r[5]/1e4,1):'—'}</td></tr>`).join('')+`</tbody></table></div></details>`;
  return h;}
/* 分析師（Yahoo Finance）：今年、明年 EPS 預估與 90 天前、營收預估、分析師的價位（引述分析師的數字，附 Yahoo 的來源連結）、評等、財報日 */
function ucAn(c,S){const A=S.an,src=`https://finance.yahoo.com/quote/${encodeURIComponent(c.replace(/[./]/g,'-'))}/analysis/`;
  if(!A)return `<h3>分析師</h3><p class=st>分析師資料還沒有（每天美股收盤後更新）。</p>`;
  const fy=y=>{if(!y||!y.end)return '';const m=+y.end.slice(5,7),yr=+y.end.slice(0,4);return m===12?`${yr} 年`:`到 ${yr} 年 ${m} 月的年度`;};
  const L=[];
  [['y0',null],['y1','y0']].forEach(([k,pk])=>{const y=A[k];if(!y||!y.e||y.e[0]==null)return;const e=y.e[0],nn=y.e[1],ya=y.e[2],t=y.t90;
    let s=`${fy(y)} EPS 預估 <b>${f(e,2)}</b>（${nn?nn+' 位':''}`;
    const p=[];if(t!=null&&t!==0&&Math.abs(e-t)/Math.abs(t)>=0.005)p.push(`90 天前 ${f(t,2)}，<span class=${e>t?'up':'dn'}>${e>t?'上修':'下修'}</span>`);
    else if(t!=null)p.push('和 90 天前差不多');
    const yl=pk?'前一年':'去年';
    if(ya!=null&&ya>0)p.push(`比${yl} ${sgn((e/ya-1)*100,0,'%')}`);
    else if(ya!=null&&ya<0)p.push(e>=0?`${yl}虧損、轉盈`:e>ya?'虧損縮小':'虧損擴大');
    s+=(nn&&p.length?'；':'')+p.join('；')+'）';
    if(y.r&&y.r[0]!=null)s+=`<div class=st>營收預估 ${f(y.r[0],y.r[0]>=100?0:1)} 億美元${y.r[1]?`（${pk?'比前一年':'比去年'} ${sgn((y.r[0]/y.r[1]-1)*100,0,'%')}）`:''}</div>`;
    L.push(`<p class=ucl>${s}</p>`);});
  const tp=A.tp;if(tp&&(tp[1]!=null||tp[0]!=null)){const v=tp[1]!=null?tp[1]:tp[0],pr=S.px?(v/S.px-1)*100:null;
    L.push(`<p class=ucl>目標價 <b>${ucPx(v)}</b>${pr!=null?`，比現價${pr>=0?'高':'低'} ${f(Math.abs(pr),1)}%`:''}（${A.n?A.n+' 位分析師的':''}${tp[1]!=null?'中位數':'平均'}）`+
      (tp[2]!=null&&tp[3]!=null?`<span class="st ucb">最高 ${ucPx(tp[2])}、最低 ${ucPx(tp[3])}</span>`:'')+`</p>`);}
  const rc=A.rc;if(rc&&rc.some(v=>v)){const nm=['強力看好','看好','中立','看淡','強力看淡'];
    L.push(`<p class=st>評等：${rc.map((v,i)=>v?`${nm[i]} ${v}`:'').filter(Boolean).join('、')}</p>`);}
  const ud=A.ud||[];if(ud.length){const AC={up:'調升',down:'調降',init:'首次給評等',main:'維持',reit:'維持'};
    L.push(`<p class=ucl>最近的評等調整</p><ul class=ucud>`+ud.slice(0,6).map(r=>{const g=r[2]==='up'||r[2]==='down'?`${esc(r[3])} 改成 ${esc(r[4])}`:esc(r[4]);
      const tp=r[5]&&r[6]&&r[5]!==r[6]?`，目標價 ${ucPx(r[5])} 調到 ${ucPx(r[6])}`:r[6]?`，目標價 ${ucPx(r[6])}`:'';
      return `<li>${ucMd(r[0])} ${esc(r[1])}：${AC[r[2]]||esc(r[2])} ${g}${tp}</li>`;}).join('')+`</ul>`);}
  const eh=A.eh||[];if(eh.length)L.push(`<p class=ucl>近 ${eh.length} 季 EPS：實際和預估<span class=st>（公司調整後的 EPS，和成長段的 SEC 數字算法不同）</span></p><div class=tw><table class="qt ucqt"><thead><tr><th>季底</th><th>實際</th><th>預估</th><th>超出</th></tr></thead><tbody>`+
    eh.slice().reverse().map(r=>`<tr><td>${ucDt(r[0])}</td><td>${r[1]==null?'—':f(r[1],2)}</td><td>${r[2]==null?'—':f(r[2],2)}</td><td>${r[1]!=null&&r[2]?sgn((r[1]-r[2])/Math.abs(r[2])*100,0,'%'):'—'}</td></tr>`).join('')+`</tbody></table></div>`);
  const ed=A.ed||[],last=(UCD.cal||[]).slice(-1)[0]||'';
  if(ed.length){const d0=ed[0],d1=ed[ed.length-1];
    if(d1<=last)L.push(`<p class=ucl>上次財報 ${mdw(d1)}（下次的日期還沒公布）</p>`);
    else L.push(`<p class=ucl>下次財報 <b>${ed.length>1?`${ucMd(d0)}～${ucMd(d1)}`:mdw(d0)}</b>${A.ede?'（公司還沒公布，Yahoo 估的日期）':''}</p>`);}
  return `<h3>分析師<span class=sub><a href="${src}" target=_blank rel=noopener>Yahoo Finance</a>${S.an_at?`・${ucMd(S.an_at)} 收盤後`:''}</span></h3>${L.join('')||'<p class=st>沒有分析師的預估。</p>'}`;}
/* 配置頁美股列、名單、接下來的買賣裡的股票名：點了開卡片（data-us） */
document.addEventListener('click',e=>{if(e.defaultPrevented)return;const a=e.target.closest&&e.target.closest('[data-us]');if(!a||!ucOn())return;
  if(ucOpen(a.dataset.us))e.preventDefault();});
window.addEventListener('hashchange',()=>{const c=ucCur();if(c)ucRender(c);});
let UCR=0;addEventListener('resize',()=>{clearTimeout(UCR);UCR=setTimeout(()=>{const c=ucCur();if(c&&!$('#dv').hidden)ucRender(c,true);},250);});
"""

CSS = r"""
/* 美股個股卡（uscardpage.py） */
.csec.uc h3 .sub a{color:var(--acc)}
.ucl{margin:4px 0;font-size:14px;line-height:1.7}.ucl b{font-weight:700}.ucl .ucb{display:block;line-height:1.5}
.uclk{display:flex;flex-wrap:wrap;gap:6px 18px;margin:8px 0 0;font-size:13.5px}.uclk a{color:var(--acc)}
.ucfv{border-collapse:collapse;font-size:13.5px;min-width:0}
.ucfv th{font-weight:600;color:var(--ink2);font-size:12px;padding:4px 10px 4px 0;text-align:left;white-space:nowrap}
.ucfv th span{display:block;font-weight:400;color:var(--mut)}
.ucfv td{padding:5px 10px 5px 0;border-top:1px solid var(--line);text-align:left;white-space:nowrap;font-variant-numeric:tabular-nums}
.ucfv td.l{white-space:normal}.ucfv td.l b{font-weight:600;margin-right:6px}.ucfv td.l span{font-size:12px;color:var(--mut);white-space:nowrap}
.ucfv i{font-style:normal;font-weight:700;margin-right:5px}.ucfv i.ucok{color:var(--loss)}.ucfv i.ucno{color:var(--gain)}
.ucw{position:relative;margin-top:4px}
.uctip{position:absolute;top:4px;background:var(--ink);color:var(--bg);font-size:12px;line-height:1.5;padding:5px 8px;border-radius:6px;pointer-events:none;white-space:nowrap;z-index:2}
.lg .ucdsh{width:16px;height:0;border-top:2px dashed var(--amber);background:none}
.lg .uchi{width:16px;height:0;border-top:1px dashed var(--mut);background:none}
.ucrg{display:flex;gap:6px;margin:2px 0 6px}
.csec.uc .kps.k4{grid-template-columns:repeat(4,minmax(0,1fr))}
.uch4{font-size:13.5px;margin:14px 0 4px;color:var(--ink2)}
.ucud{margin:2px 0 8px;padding-left:18px;font-size:13.5px;line-height:1.7}
.qt.ucqt{width:auto;min-width:0}
.qt.ucpeer th span{display:block;font-weight:400;color:var(--mut);font-size:11px}
.qt.ucpeer td.l .st{display:block;font-size:11.5px;white-space:normal;max-width:15em}
.qt tr.ucme td{background:var(--hlcol)}
@media (max-width:640px){.csec.uc .kps.k4{grid-template-columns:repeat(2,minmax(0,1fr))}}
.qt.uctx .ucmb{display:none}
@media (max-width:560px){.qt.ucpeer td,.qt.ucpeer th{padding:5px 4px;font-size:12px}.qt.ucpeer td.l .st{max-width:9em}
.qt.uctx .ucdk{display:none}.qt.uctx .ucmb{display:block;font-size:12px;white-space:normal;margin-top:2px}.qt.uctx td.l{white-space:normal}}
.ucrg button{font:inherit;font-size:12.5px;padding:3px 10px;border-radius:999px;border:1px solid var(--line);background:var(--card);color:var(--ink2);cursor:pointer}
.ucrg button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.ucrg button:disabled{opacity:.4;cursor:default}
"""
