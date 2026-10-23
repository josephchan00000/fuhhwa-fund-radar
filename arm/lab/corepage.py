"""交易計畫卡片：核心 70%＋衛星 30%（corespec VER 1；docs/lab_core70_plan.md 第 10 節）。
訊號總覽・研究結論每個市場最上面一張（台股、S&P 500、那斯達克 100；其他市場一行說明）。class 一律 pln 開頭。
版面照使用者確認過的示意圖：現在拿多少 → 接下來要做的事（含三種過熱的讀數）→ 好處 → 可以期待的報酬與風險＋1 元變多少 → 收起來的細節。
數字全部由 core.py 算（研究檔、景氣頁的現在讀數、個股頁的衛星資料），這裡只排版；只描述照規則做的過去結果。"""
from __future__ import annotations

import html
import math
from datetime import date

from . import corespec as S

WD = "一二三四五六日"
CORE_HOW = {"tw": "大盤（0050／006208）", "spx": " S&P 500（例：SPY、VOO）", "ndx": "那斯達克 100（例：QQQ）"}


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d else "—"


def _mdw(d: str | None) -> str:
    return f"{_md(d)}（{WD[date.fromisoformat(d).weekday()]}）" if d else "—"


def _ym(d: str | None) -> str:
    return f"{d[:4]}/{int(d[5:7])}" if d else "—"


def _wan(m: float | None) -> str:
    return "—" if m is None else f"{m * 100:,.0f} 萬"


def _pc(x: float | None, d: int = 1, sign: bool = True) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    v = round(x * 100, d)
    s = "−" if v < 0 else ("+" if sign and v > 0 else "")
    return f"{s}{abs(v):.{d}f}%"


def _ab(x: float | None, d: int = 0) -> str:
    return "—" if x is None else f"{abs(x) * 100:.{d}f}%"


def _px(x: float | None) -> str:
    return "—" if x is None else f"{x:,.0f}" if x >= 1000 else f"{x:,.2f}"


def _wins(plan: dict, hold: dict) -> tuple[int, int]:
    w = n = 0
    for (y, r, k), (_, rh, _) in zip(plan.get("years") or [], hold.get("years") or []):
        if k >= S.YEAR_MIN:
            n += 1
            w += r > rh
    return w, n


# ── 現在 ─────────────────────────────────────────────────────────────────────

def _next_day(mk: str, d: str) -> str | None:
    try:
        from .xstrat import future_days
        return future_days(mk, d, 1)[0]
    except Exception:                                    # noqa: BLE001
        return None


def now_html(mk: str, N: dict, stk: dict | None) -> str:
    nxt, cur = N["next"], N["now"]
    cash = nxt < 0.99
    big = f'{round(nxt * 100)}%'
    sub = f'{_e(_md(N["d"]))} 收盤後'
    bar = ('<div class="plnbar"><i class="plnbc">核心 70%</i>'
           + ('<i class="plnbx">衛星 30% 現金</i>' if cash else '<i class="plnbs">衛星 30%</i>') + '</div>')
    if mk == "tw":
        st = (stk or {}).get("st") or []
        if st:
            w = round(S.SAT / len(st) * 100)
            names = "、".join(_e(s["name"]) for s in st)
            txt = (f"核心 70% 一直抱著{_e(CORE_HOW[mk])}。衛星 30% 平分給個股策略頁的 ★：{names}，各 {w}%；"
                   "哪一條沒有部位，它那一份放大盤。") + _sat_now(stk, N["now"] < 0.99)
        else:
            txt = f"核心 70% 一直抱著{_e(CORE_HOW[mk])}。衛星 30% 平分給個股策略頁的 ★（現在讀不到名單，先放大盤）。"
    else:
        txt = (f"核心 70% 一直抱著{_e(CORE_HOW[mk])}。衛星 30% 現在也放同一個指數"
               "（美股個股策略還在補資料，做好、判定過了再換）。")
    due = ""
    if N.get("due"):
        day = _next_day(mk, N["d"])
        lit = "、".join(f["name"] for f in N["fams"] if f["lit"])
        if cash:
            due = (f'<p class="plndue"><b>{_e(_mdw(day))} 收盤：把衛星 30% 全部賣掉、換成現金</b>（{_e(lit)}同時亮），'
                   f'之後只拿 70%。</p>')
        else:
            due = (f'<p class="plndue plndok"><b>{_e(_mdw(day))} 收盤：把衛星 30% 買回</b>（過熱少於兩種）'
                   + ("，照各條策略當時應該持有的股票買、沒有部位的那一份買大盤" if mk == "tw" else "") + '。</p>')
    elif cash:
        due = '<p class="plndue">衛星現在是現金：三種過熱少於兩種的下一個交易日收盤買回。</p>'
    was = "" if abs(cur - nxt) < 0.001 else f'<small class="plnwas">今天收盤前 {round(cur * 100)}%</small>'
    return (f'<div class="plnnow"><div class="plnbig">{big}<small>{sub}</small>{was}</div>{bar}'
            f'<p class="plnnt">{txt}</p>{due}</div>')


def sat_weights(stk: dict | None) -> list[dict]:
    """台股衛星現在每一條策略手上的股票與比重（占全部資金）：定期換股＝那一份平分給每一期的名單、名單內平分；
    其他＝每一檔那一份 ÷ SLOTS；剩下的放大盤（corespec「衛星放什麼」）。"""
    st = (stk or {}).get("st") or []
    if not st:
        return []
    share = S.SAT / len(st)
    out = []
    for s in st:
        hold = ((stk or {}).get("hold") or {}).get(s["k"]) or []
        rows = []
        if s.get("kind") in S.PERIOD_KINDS:
            lists: dict = {}
            for h in hold:
                lists.setdefault(h.get("ent") or "", []).append(h)
            for ent, hs in sorted(lists.items()):
                for h in hs:
                    rows.append({"c": h.get("c"), "n": h.get("n"), "w": share / len(lists) / len(hs), "ent": ent})
        else:
            slots = S.SLOTS.get(s["k"], S.SLOTS_DEFAULT)
            for h in hold[:slots]:
                rows.append({"c": h.get("c"), "n": h.get("n"), "w": share / slots, "ent": h.get("ent")})
        idle = max(0.0, share - sum(r["w"] for r in rows))
        out.append({"k": s["k"], "name": s.get("name") or s["k"], "rows": rows, "idle": idle, "share": share})
    return out


def _wp(w: float) -> str:
    return f"{w * 100:.1f}%".replace(".0%", "%")


def _sat_now(stk: dict | None, cash: bool) -> str:
    """衛星現在拿著什麼（台股）。接在 plnnt 段落後面：先關掉段落、放清單、再開一個隱藏的空段落讓外層的 </p> 對得上。"""
    W = sat_weights(stk)
    if not W:
        return ""
    rows = ""
    for x in W:
        held = "、".join(f'{_e(r["n"] or r["c"])} {_wp(r["w"])}' for r in x["rows"])
        idle = f'大盤 {_wp(x["idle"])}' if x["idle"] > 1e-9 else ""
        body = "；".join(t for t in (held, idle) if t) or "—"
        rows += f'<div class="plnsn">{_e(x["name"])}</div><div class="plnsv">{body}</div>'
    hd = "衛星現在是現金；買回時照下面這樣買（占全部資金）" if cash else "衛星現在拿著（占全部資金）"
    return f'</p><div class="plnsat"><div class="plnsh">{hd}</div>{rows}</div><p class="plnnt plnhide">'


def _ev_line(e: dict, cash: bool, w: int) -> tuple[str, str]:
    """(何時, 做什麼)。"""
    at = e.get("at") or ""
    when = f'{_e(_mdw(e["d"]))}<small>{_e(at)}</small>'
    nm = _e(e.get("sname") or e["k"])
    names = "、".join(_e(x.get("n") or x.get("c")) for x in e.get("items") or [])
    more = f"等 {e['n_items']} 檔" if e.get("n_items", 0) > len(e.get("items") or []) else ""
    act = e.get("act") or ""
    if act == "買進" and e.get("pending"):
        what = f'<b>{nm}</b> 買新名單（{_e(_md(e.get("fix")))} 收盤產生）'
    elif act == "買進":
        what = f'<b>{nm}</b> 買進 {names}{more}'
    elif act == "賣出" and e.get("held"):
        n = e.get("n_items") or len(e.get("items") or [])
        what = f'<b>{nm}</b> 賣掉 {_e(_md(e.get("ent")))} 買的 {n} 檔' + (f'（{names}）' if names and n <= 5 else "")
    elif act == "賣出":
        what = f'<b>{nm}</b> 賣出 {names}{more}'
    else:
        what = f'<b>{nm}</b> {_e(act)}' + (f'：{_e(e["note"])}' if e.get("note") else "")
    sub = [f"衛星裡的 {w}%"]
    if e.get("how") and act == "買進" and not e.get("pending"):
        sub.append(_e(e["how"]))
    if cash and act == "買進":
        sub.append("衛星在現金：先不買")
    return when, what + f'<span class="plnsub">{"・".join(sub)}</span>'


def todo_html(mk: str, N: dict, stk: dict | None) -> str:
    cash = N["next"] < 0.99
    rows = ""
    if mk == "tw":
        ev = (stk or {}).get("ev") or []
        st = (stk or {}).get("st") or []
        w = round(S.SAT / len(st) * 100) if st else 0
        if ev:
            for e in ev:
                a, b = _ev_line(e, cash, w)
                rows += f'<div class="plnw">{a}</div><div class="plnt">{b}</div>'
        else:
            rows = '<div class="plnw">—</div><div class="plnt">接下來 45 天，衛星裡的個股策略沒有排定的買賣。</div>'
    else:
        rows = '<div class="plnw">平常</div><div class="plnt">衛星放指數，不用動；只看下面三種過熱。</div>'
    return f'<h4 class="plnh">接下來要做的事</h4>' + (f'<div class="plntodo">{rows}</div>' if rows else "") + _fam_html(mk, N)


def _fam_html(mk: str, N: dict) -> str:
    rows = ""
    near = []
    for f in N["fams"]:
        on = f["lit"]
        if f["k"] == "trend":
            pct, ma, trig = f.get("pct"), f.get("ma"), f.get("trig")
            if pct is None:
                val, bar = "年線還算不出來", '<div class="plngz"><i style="width:0"></i><b style="left:50%"></b></div>'
            else:
                w = max(0.0, min(100.0, 50.0 - pct * 2.5))     # 越長越接近亮：比年線高 20% 以上＝空、在年線上＝一半、低 20%＝滿
                val = (f'比年線{"低" if pct < 0 else "高"} {abs(pct):.1f}%' + ("（亮）" if on else "（跌破才亮）"))
                bar = (f'<div class="plngz"><i class="{"plngdn" if on else ""}" style="width:{w:.1f}%"></i>'
                       '<b style="left:50%"></b></div>')
                if not on:
                    near.append((abs(pct) / 10, f"趨勢（下一個交易日收盤低於 {_px(trig)} 就跌破年線）"))
            sub = f'{_e(f["desc"])}' + (f'；年線 {_px(ma)}' if ma else "")
        else:
            v = f.get("v")
            w = 0 if v is None else max(0.0, min(100.0, v))
            val = "沒有資料" if v is None else f'{v:.1f}' + ("（亮）" if on else "（80 以上算亮）")
            bar = f'<div class="plngz"><i class="{"plngdn" if on else ""}" style="width:{w:.1f}%"></i><b></b></div>'
            src = f.get("src")
            sub = _e(f["desc"]) + (f'；資料到 {_e(_ym(src) if len(src) <= 7 else _md(src))}' if src else "")
            if f.get("stale"):
                sub += "（過期）"
            if not on and v is not None:
                near.append(((S.HOT - v) / 20, f"{f['name']}（再升 {S.HOT - v:.1f} 到 80 就亮）"))
        rows += (f'<div class="plnn">{_e(f["name"])}<small>{sub}</small></div>{bar}'
                 f'<div class="plnv{" plnvon" if on else ""}">{_e(val)}</div>')
    n = N["n"]
    lead = f'現在亮 <b>{n} 種</b> → 拿 {round(N["next"] * 100)}%。'
    if n < S.NEED and near:
        near.sort()
        if n == S.NEED - 1:
            lead += f'<span class="plnw2">再亮一種就換現金；最接近的是{_e(near[0][1])}。</span>'
        else:
            lead += f'最接近的是{_e(near[0][1])}。'
    return ('<div class="plntrig"><div class="plnw">每天收盤看<small>三種過熱</small></div><div class="plnt">'
            '<b>三種有兩種以上同時亮 → 下一個交易日收盤把衛星 30% 換成現金、只留 70%；少於兩種 → 買回</b>'
            '<small class="plngl">長條越長越接近亮，直線＝亮的位置</small>'
            f'<div class="plnfam">{rows}</div><p class="plnsum">{lead}</p></div></div>')


# ── 過去 ─────────────────────────────────────────────────────────────────────

def _label(mk: str, s: dict) -> str:
    if mk == "tw" and s["key"] == "plan":
        return f'{_ym(s["a"])}～{_ym(s["b"])}，衛星放財報驚喜（大型股）'
    if s["key"] == "early":
        return f'{s["a"][:4]}～{s["b"][:4]}'
    return f'{s["a"][:4]} 年起'


def benefit_html(mk: str, sc: dict) -> str:
    s = sc.get("plan") if mk == "tw" and sc.get("plan") else sc.get("rule")
    if not s:
        return ""
    p, h = s["plan"], s["hold"]
    w, n = _wins(p, h)
    name = "大盤" if mk == "tw" else f" {_e(S.NAMES[mk])} "
    kp = (f'<div class="plnkpi"><div><div class="plnkl">100 萬變成</div><div class="plnkv plnkg">{_wan(p["m"])}</div><div class="plnkr">一直抱著{"大盤" if mk == "tw" else ""} {_wan(h["m"])}</div></div>'
          f'<div><div class="plnkl">最慘時從高點跌</div><div class="plnkv">{_ab(p["mdd"])}</div><div class="plnkr">一直抱著 {_ab(h["mdd"])}</div></div>'
          f'<div><div class="plnkl">贏一直抱著</div><div class="plnkv">{w}／{n} 年</div><div class="plnkr">最差一年 {_pc(p.get("worst"))}（{_pc(h.get("worst"))}）</div></div></div>')
    note = ""
    if mk == "tw" and sc.get("rule"):
        r = sc["rule"]
        note = (f'<p class="plnnote">規則本身（衛星放大盤）{r["a"][:4]} 年起：100 萬變 {_wan(r["plan"]["m"])}（一直抱著 {_wan(r["hold"]["m"])}），'
                f'最慘時跌 {_ab(r["plan"]["mdd"])}（{_ab(r["hold"]["mdd"])}）。</p>')
    elif sc.get("early"):
        e = sc["early"]
        note = (f'<p class="plnnote">規則挑選時沒有用到的更早期間（{e["a"][:4]}～{e["b"][:4]}）：100 萬變 {_wan(e["plan"]["m"])}'
                f'（一直抱著 {_wan(e["hold"]["m"])}），最慘時跌 {_ab(e["plan"]["mdd"])}（{_ab(e["hold"]["mdd"])}）。</p>')
    return f'<h4 class="plnh">好處<span>（{_e(_label(mk, s))}，和一直抱著{name}比）</span></h4>{kp}{note}'


def expect_html(mk: str, sc: dict) -> str:
    s = sc.get("plan") if mk == "tw" and sc.get("plan") else sc.get("rule")
    if not s or not s["plan"].get("q"):
        return ""
    p, h = s["plan"], s["hold"]
    q, hq = p["q"], h["q"]
    name = "大盤" if mk == "tw" else "指數"
    cells = [("運氣差（最差的一成）", _pc(q[0]), f"{name} {_pc(hq[0])}"), ("一般（中位數）", _pc(q[1]), f"{name} {_pc(hq[1])}"),
             ("運氣好（最好的一成）", _pc(q[2]), f"{name} {_pc(hq[2])}"), ("12 個月後是虧的", _ab(p["loss"]), f"{name} {_ab(h['loss'])}")]
    dist = "".join(f'<div><div class="plnkl">{a}</div><div class="plnkv">{b}</div><div class="plnkr">{c}</div></div>' for a, b, c in cells)
    ch = s["chart"]
    return ('<h4 class="plnh">可以期待的報酬與風險<span>過去任挑一天，往後 12 個月</span></h4>'
            f'<div class="plndist">{dist}</div>{chart(ch, 960, 250, 12, "plnchd")}{chart(ch, 360, 190, 12, "plnchm")}'
            '<div class="plnlg"><span><i></i>照計畫做</span><span><i class="plnlgh"></i>一直抱著</span>'
            '<span><i class="plnlgc"></i>衛星換成現金的期間</span></div>')


def chart(C: dict, W: int, H: int, fs: int, cls: str) -> str:
    pts, cash = C.get("pts") or [], C.get("cash") or []
    if len(pts) < 2:
        return ""
    pl, pr, pt, pb = (44, 58, 12, 24) if W > 500 else (34, 50, 10, 22)
    d0, d1 = pts[0][0], pts[-1][0]
    o = date.fromisoformat(d0)
    span = max(1, (date.fromisoformat(d1) - o).days)
    lo = min(min(p[1], p[2]) for p in pts) * 0.92
    hi = max(max(p[1], p[2]) for p in pts) * 1.08
    lo, hi = max(lo, 1e-6), max(hi, lo * 1.5)

    def X(d):
        return pl + (W - pl - pr) * (date.fromisoformat(d) - o).days / span

    def Y(v):
        return pt + (H - pt - pb) * (1 - (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo)))
    s = [f'<svg viewBox="0 0 {W} {H}" class="plnch {cls}" style="--fs:{fs}px" role="img" aria-label="1 元變多少：照計畫做和一直抱著">']
    for a, b in cash:
        x0, x1 = X(a), max(X(b), X(a) + 1.5)
        s.append(f'<rect class="plncash" x="{x0:.1f}" y="{pt}" width="{x1 - x0:.1f}" height="{H - pt - pb}"/>')
    ticks = [v for v in (0.5, 1, 2, 3, 5, 10, 20, 50, 100, 200) if lo <= v <= hi]
    if W <= 500 and len(ticks) > 3:
        ticks = ticks[::2]
    for v in ticks:
        s.append(f'<line class="plngr" x1="{pl}" x2="{W - pr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}"/>'
                 f'<text class="plnax" x="{pl - 6}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:g} 元</text>')
    y0, y1 = int(d0[:4]) + 1, int(d1[:4])
    step = max(1, (y1 - y0 + 1) // (6 if W > 500 else 3))
    for y in range(y0, y1 + 1, step):
        d = f"{y}-01-01"
        s.append(f'<text class="plnax" x="{X(d):.1f}" y="{H - 6}" text-anchor="middle">{y}</text>')
    for col, c in ((2, "plnhl"), (1, "plnpp")):
        path = " ".join(f'{"M" if i == 0 else "L"}{X(p[0]):.1f},{Y(p[col]):.1f}' for i, p in enumerate(pts))
        s.append(f'<path class="{c}" d="{path}"/>')
    lp, lh = pts[-1][1], pts[-1][2]
    yp, yh = Y(lp), Y(lh)
    if abs(yp - yh) < fs + 2:                           # 兩個標籤太近：上下拉開
        yp, yh = (yp - (fs + 2) / 2, yh + (fs + 2) / 2) if lp >= lh else (yp + (fs + 2) / 2, yh - (fs + 2) / 2)
    s.append(f'<text class="plnlp" x="{W - pr + 6}" y="{yp + 4:.1f}">{lp:.1f} 元</text>')
    s.append(f'<text class="plnlh" x="{W - pr + 6}" y="{yh + 4:.1f}">{lh:.1f} 元</text>')
    s.append("</svg>")
    return "".join(s)


def details_html(mk: str, sc: dict, fw: dict | None) -> str:
    s = sc.get("plan") if mk == "tw" and sc.get("plan") else sc.get("rule")
    if not s:
        return ""
    out = []
    if mk == "tw":
        why = ['訊號總覽的每一個台股市場層級訊號（517 個）都拿來試過當「衛星換現金」的規則。和美股一致的是兩種過熱：'
               '<b>通膨過熱</b>（美國 CPI 年增率在過去 10 年的高檔區）、<b>槓桿過熱</b>（融資 ÷ 上市市值）。'
               '單純跌破年線、技術面過熱就減碼，台股都少賺。']
    else:
        why = ['訊號總覽的每一個市場層級訊號（美股每個指數 333～343 個）都拿來試過當「衛星換現金」的規則。和台股一致的是兩種過熱：'
               '<b>通膨過熱</b>（美國 CPI 年增率在過去 10 年的高檔區）、<b>槓桿過熱</b>（美國家計證券融資年增率）。']
    why += ['三種放在一起投票、<b>兩種以上同時亮才換現金</b>：台股、S&amp;P 500、那斯達克 100 不論看全部期間、前一半、後一半還是近 10 年，'
            '都比一直抱著多（衛星放指數）。',
            '反過來「平常 70%、看多才拉到 100%」三個市場都比一直抱著少：平常就拿滿，只在過熱時減碼。',
            '台股多賺的部分大多來自衛星放的個股策略；換現金主要讓大跌的年份少跌。' if mk == "tw"
            else '多賺的部分來自大跌的年份：衛星換成現金，那幾年少跌。']
    out.append('<details class="plnd"><summary>為什麼這樣設計</summary><ul>' + "".join(f"<li>{x}</li>" for x in why) + "</ul></details>")
    eps = s.get("eps") or []
    if eps:
        tr = "".join(f'<tr><td class="plntl">{_e(e["d"])}</td><td>{_e(_md(e["sell"]))}</td>'
                     f'<td>{_e(_md(e["buy"])) if e.get("buy") else "還在現金"}</td><td class="plntl">{_e("、".join(e["lit"]))}</td>'
                     f'<td>{e["days"]}</td><td>{_pc(e["ix"])}</td><td>{_pc(e["diff"], 1)}</td></tr>' for e in reversed(eps))
        out.append(f'<details class="plnd"><summary>過去每一次把衛星換成現金（{len(eps)} 次）</summary><div class="plntw"><table class="plntb">'
                   '<tr><th class="plntl">決定日</th><th>賣出</th><th>買回</th><th class="plntl">亮的</th><th>天數</th><th>那段衛星資產漲跌</th><th>比一直拿著衛星</th></tr>'
                   f'{tr}</table></div><p class="plnnote">「比一直拿著衛星」＝衛星 30% 換成現金那段多賺（正）或少賺（負）帳戶的幾個百分點，'
                   '不算買賣成本。</p></details>')
    ys = list(zip(s["plan"]["years"], s["hold"]["years"]))
    if ys:
        tr = "".join(f'<tr><td class="plntl">{y}{"" if n >= S.YEAR_MIN else "（部分）"}</td><td>{_pc(r)}</td><td>{_pc(rh)}</td><td>{_pc(r - rh)}</td></tr>'
                     for (y, r, n), (_, rh, _) in reversed(ys))
        out.append('<details class="plnd"><summary>逐年報酬</summary><div class="plntw"><table class="plntb">'
                   '<tr><th class="plntl">年</th><th>照計畫做</th><th>一直抱著</th><th>差</th></tr>' + tr + "</table></div></details>")
    rows = []
    for key, nm in (("plan", "照計畫做"), ("rule", "規則本身（衛星放指數）"), ("early", "規則挑選時沒有用到的期間")):
        x = sc.get(key)
        if not x or (mk != "tw" and key == "plan"):
            continue
        h1, h2, rc = x["halves"][0], x["halves"][1], x["recent"]
        rows.append(f'<tr><td class="plntl">{_e(nm)}<small>{_e(x["a"][:7])}～{_e(x["b"][:7])}</small></td>'
                    f'<td>{_wan(x["plan"]["m"])}<small>抱著 {_wan(x["hold"]["m"])}</small></td>'
                    f'<td>{_wan(x["fixed"]["m"])}</td>'
                    f'<td>{_wan(h1["plan"]["m"])}<small>抱著 {_wan(h1["hold"]["m"])}</small></td>'
                    f'<td>{_wan(h2["plan"]["m"])}<small>抱著 {_wan(h2["hold"]["m"])}</small></td>'
                    f'<td>{_wan(rc["plan"]["m"])}<small>抱著 {_wan(rc["hold"]["m"])}</small></td>'
                    f'<td>{_ab(x["avg"])}</td><td>{x["sw"]:.1f}</td></tr>')
    if rows:
        out.append('<details class="plnd"><summary>每一段期間（前一半、後一半、近 10 年、更早的期間）</summary><div class="plntw"><table class="plntb">'
                   '<tr><th class="plntl">期間</th><th>100 萬變</th><th>每天固定拿一樣多</th><th>前一半</th><th>後一半</th><th>近 10 年</th><th>平均拿</th><th>一年動幾次</th></tr>'
                   + "".join(rows) + '</table></div><p class="plnnote">「每天固定拿一樣多」＝平均部位相同、但不看過熱一直拿著：'
                   '照計畫比它多，才表示換現金的時點本身有用。前一半、後一半、近 10 年各自從 100 萬算起。</p></details>')
    fw = fw or {}
    left = f"已記錄 {fw.get('n', 0)} 個交易日" if fw.get("n") else "還沒有紀錄"
    nxt = fw.get("next")
    out.append('<details class="plnd"><summary>上線後怎麼檢查（前瞻）</summary>'
               f'<p>{_e(_md(S.LIVE_START))} 起每天記下計畫說該拿多少、三種過熱的讀數、衛星放哪幾條（{left}）。'
               f'滿 {"、".join(str(c) for c in S.CHECKS)} 個交易日各和回測裡同樣長度的期間比一次：照做比一直抱著多或少，'
               '排在過去最差的兩成就標出來；另外每天看照做的回撤有沒有比回測最慘的一次'
               f'（{_ab(s["plan"]["mdd"])}）還深。' + (f"下一次比是第 {nxt} 個交易日。" if nxt else "")
               + ("台股衛星的實際報酬之後用各條策略自己的逐筆交易重算。" if mk == "tw" else "")
               + '出現這些會標在這裡，不會自動停用，要不要停由你決定。</p></details>')
    care = []
    if mk == "tw":
        care += ['回測裡的衛星只有財報驚喜（大型股）：臺灣50 提前卡位 2024 年底、長線投信動能 2025 年才有紀錄，上線起照規則加入。'
                 '三條都是看過成績才判定 ★ 的，真正的考驗是上線後的紀錄。',
                 '財報驚喜的資金帳戶 2026/10/23 修正過：年報那一期和第一季那一期每年重疊約一個月，之前同一筆錢算了兩次報酬；'
                 '修正後它自己的年化從 49.5% 變 30.4%。',
                 '換現金的好處多半在大跌的年份（台股主要是 2008 年）；平常的年份和一直抱著差不多。',
                 '衛星分成很多檔，100 萬的帳戶每檔約 1～2 萬，高價股要用零股。']
        if s["plan"].get("ex_best") is not None:
            care.append(f'去掉最好的一年（{_e(s["plan"].get("best_y") or "")}），年化還有 {_pc(s["plan"]["ex_best"], 1, False)}'
                        f'（一直抱著 {_pc(s["hold"].get("ex_best"), 1, False)}）。')
    else:
        e = sc.get("early")
        care += ['好處集中在大跌年（2000～2002、2008、2020、2022）；平常的年份兩邊都是 100%，和一直抱著一樣。',
                 '美股衛星現在放指數；美股個股策略做好、判定過了才會換。']
        if e:
            care.append(f'規則挑選時沒有用到的 {e["a"][:4]}～{e["b"][:4]}：100 萬變 {_wan(e["plan"]["m"])}（一直抱著 {_wan(e["hold"]["m"])}），'
                        f'最慘時跌 {_ab(e["plan"]["mdd"])}（{_ab(e["hold"]["mdd"])}）——錢{"多一點" if e["plan"]["m"] >= e["hold"]["m"] else "少一點"}、少跌。')
    care.append('這些都是過去照規則做的結果，不代表以後也會這樣。')
    out.append('<details class="plnd"><summary>要注意的事</summary><ul>' + "".join(f"<li>{x}</li>" for x in care) + "</ul></details>")
    return '<h4 class="plnh">細節</h4>' + "".join(out)


# ── 卡片 ─────────────────────────────────────────────────────────────────────

def card(mk: str, N: dict | None, R: dict | None, stk: dict | None = None, fw: dict | None = None) -> str:
    if mk not in S.MARKETS:
        return ('<div class="pln plnoff"><b>交易計畫</b>：核心 70%＋衛星 30% 目前只做台股、S&amp;P 500、那斯達克 100，'
                '在上面切換市場看。</div>')
    sc = (((R or {}).get("mk") or {}).get(mk) or {}).get("sc") or {}
    hd = ('<div class="plnhd"><h3>交易計畫：核心 70%＋衛星 30%</h3><span class="plntag">前瞻驗證中</span></div>')
    if not N:
        body = '<p class="plnnote">今天的讀數還沒算（景氣頁建頁時會算），先列過去的成績。</p>'
    else:
        body = now_html(mk, N, stk) + todo_html(mk, N, stk)
    if sc:
        body += benefit_html(mk, sc) + expect_html(mk, sc) + details_html(mk, sc, fw)
    else:
        body += '<p class="plnnote">回測還沒產生（scripts/run_core.py）。</p>'
    return f'<div class="pln" id="pln-{_e(mk)}">{hd}{body}</div>'


CSS = """
.pln{border:1px solid var(--line);border-radius:14px;padding:14px 16px;background:var(--panel);margin:0 0 14px;
 --plncore:#56698a;--plnsat:var(--acc);--plncash:rgba(180,83,9,.14);--plngood:var(--acc)}
@media (prefers-color-scheme:dark){.pln{--plncore:#5d7393;--plncash:rgba(240,162,74,.18)}}
.plnoff{font-size:13.5px;color:var(--ink2);padding:10px 14px}
.plnhd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px}
.plnhd h3{font-size:18px;margin:0}
.plntag{font-size:12px;color:var(--warn);background:var(--curbg);border-radius:999px;padding:1px 9px}
.plnnow{display:grid;grid-template-columns:auto 1fr;gap:6px 16px;align-items:center;background:var(--card2);border-radius:12px;padding:12px 14px}
.plnbig{font-size:30px;font-weight:800;line-height:1;white-space:nowrap}
.plnbig small{display:block;font-size:12.5px;font-weight:400;color:var(--mut);margin-top:6px}
.plnbig .plnwas{color:var(--warn);margin-top:2px}
.plnbar{display:flex;height:30px;border-radius:8px;overflow:hidden;font-size:12.5px;color:#fff;font-weight:600}
.plnbar i{font-style:normal;display:flex;align-items:center;padding:0 10px;white-space:nowrap;overflow:hidden}
.plnbar .plnbc{background:var(--plncore);flex:70}.plnbar .plnbs{background:var(--plnsat);flex:30}
.plnbar .plnbx{flex:30;color:var(--warn);background:repeating-linear-gradient(45deg,var(--plncash),var(--plncash) 6px,transparent 6px,transparent 11px);border:1px dashed var(--warn);border-radius:0 8px 8px 0}
.plnnt{grid-column:1/-1;font-size:13.5px;color:var(--ink2);margin:0}.plnhide{display:none}
.plnsat{grid-column:1/-1;display:grid;grid-template-columns:auto 1fr;gap:3px 12px;font-size:13px;margin:2px 0 0;padding:7px 10px;border-radius:8px;background:var(--panel)}
.plnsh{grid-column:1/-1;font-size:12px;color:var(--mut)}.plnsn{font-weight:600;white-space:nowrap}.plnsv{color:var(--ink2);min-width:0}
.plndue{grid-column:1/-1;font-size:13.5px;margin:2px 0 0;padding:7px 10px;border-radius:8px;background:var(--curbg)}
.plndue b{color:var(--warn)}.plndue.plndok b{color:var(--plngood)}
.plnh{font-size:15px;margin:16px 0 8px}.plnh span{font-weight:400;color:var(--mut);font-size:12.5px;margin-left:6px}
.plntodo{display:grid;grid-template-columns:auto 1fr;border-top:1px solid var(--line)}
.plntodo>div{padding:9px 0;border-bottom:1px solid var(--line)}
.plnw{font-weight:700;padding-right:14px;white-space:nowrap;font-size:14px}
.plnw small{display:block;font-weight:400;color:var(--mut);font-size:12px}
.plnt{font-size:14px;min-width:0}.plnt b{font-weight:600}
.plnsub{display:block;font-size:12.5px;color:var(--mut)}
.plntrig{display:grid;grid-template-columns:auto 1fr;margin-top:6px}
.plntrig>.plnw{color:var(--warn);padding-top:8px}
.plntrig>.plnt{background:var(--curbg);border-radius:8px;padding:8px 10px;margin:6px 0}
.plnfam{display:grid;grid-template-columns:minmax(8.5em,auto) minmax(60px,1fr) auto;gap:6px 12px;align-items:center;margin:8px 0 2px}
.plnn{font-size:13.5px}.plnn small{display:block;font-size:12px;color:var(--mut)}
.plngz{position:relative;height:10px;border-radius:5px;background:var(--line)}
.plngz i{position:absolute;left:0;top:0;bottom:0;border-radius:5px;background:var(--plncore)}
.plngz i.plngdn{background:var(--warn)}.plngz i.plngup{background:var(--plngood)}
.plngz b{position:absolute;left:80%;top:-4px;bottom:-4px;width:2px;background:var(--warn)}
.plnv{font-size:13px;color:var(--ink2);white-space:nowrap;text-align:right}.plnv.plnvon{color:var(--warn);font-weight:700}
.plngl{display:block;font-size:12px;color:var(--mut);font-weight:400;margin-top:2px}
.plnsum{font-size:13.5px;margin:6px 0 0}.plnsum b{color:var(--plngood)}.plnw2{color:var(--warn);margin-left:4px}
.plnkpi{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.plnkpi>div{background:var(--card2);border-radius:12px;padding:10px 12px;min-width:0}
.plnkl{font-size:12.5px;color:var(--mut)}.plnkpi .plnkv{font-size:22px;font-weight:800;line-height:1.25}
.plnkpi .plnkg{color:var(--plngood)}.plnkpi .plnkr{font-size:12.5px;color:var(--ink2)}
.plndist{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:8px}
.plndist>div{border-left:3px solid var(--line2);padding:2px 0 2px 10px;min-width:0}
.plndist .plnkv{font-size:19px;font-weight:700}.plndist .plnkr{font-size:12.5px;color:var(--mut)}
.plnch{width:100%;height:auto;display:block}.plnch.plnchm{display:none}
.plnpp{fill:none;stroke:var(--acc);stroke-width:2}.plnhl{fill:none;stroke:var(--mut);stroke-width:1.6;stroke-dasharray:4 3}
.plngr{stroke:var(--line)}.plnax{fill:var(--mut);font-size:var(--fs)}.plncash{fill:var(--plncash)}
.plnlp{fill:var(--acc);font-size:var(--fs);font-weight:700}.plnlh{fill:var(--mut);font-size:var(--fs)}
.plnlg{font-size:12.5px;color:var(--ink2);display:flex;gap:14px;flex-wrap:wrap;margin:4px 0 0}
.plnlg i{display:inline-block;width:18px;height:0;border-top:2px solid var(--acc);vertical-align:middle;margin-right:5px}
.plnlg i.plnlgh{border-top:2px dashed var(--mut)}.plnlg i.plnlgc{height:10px;border:0;background:var(--plncash);width:14px}
.plnnote{font-size:12.5px;color:var(--ink2);margin:8px 0 0;line-height:1.7}
.plnd{border-top:1px solid var(--line);padding:8px 0}.plnd:last-child{border-bottom:1px solid var(--line)}
.plnd>summary{cursor:pointer;font-size:14px;color:var(--ink2)}
.plnd p,.plnd li{font-size:13.5px;color:var(--ink2);line-height:1.7}
.plntw{overflow-x:auto;margin:6px 0 2px}
.plntb{border-collapse:collapse;width:100%;font-size:12.5px}
.plntb th,.plntb td{padding:4px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.plntb th{color:var(--ink2);font-weight:600}.plntb .plntl{text-align:left}.plntb small{display:block;font-size:11px;color:var(--mut)}
@media (max-width:560px){.plnch.plnchd{display:none}.plnch.plnchm{display:block}.plnkpi>div{padding:8px 9px}.plnkpi .plnkv{font-size:18px}
.plnkpi .plnkl,.plnkpi .plnkr{font-size:11.5px}.plndist{grid-template-columns:1fr 1fr}.plnbig{font-size:26px}.plnnow{grid-template-columns:1fr}
.plntodo,.plntrig{grid-template-columns:1fr}.plnw{padding:0}.plnw small{display:inline;margin-left:6px}.plnsat{grid-template-columns:1fr}.plnsn{margin-top:3px}.plntodo>div.plnw{border-bottom:0;padding-bottom:0}.pln{padding:12px 12px}
.plnfam{grid-template-columns:minmax(0,1fr) auto;grid-auto-flow:row dense}.plnfam .plngz{grid-column:1/-1}}
"""
