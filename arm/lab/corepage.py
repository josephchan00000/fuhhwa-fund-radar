"""交易計畫卡片：核心 70%＋衛星 30%（corespec VER 1；docs/lab_core70_plan.md 第 10、11 節）。
訊號總覽・研究結論每個市場最上面一張（台股、S&P 500、那斯達克 100；其他市場一行說明）。class 一律 pln 開頭。
版面照使用者確認過的示意圖：現在拿多少 → 接下來要做的事（含三個警訊的分數）→ 過去照做的結果 → 照做一年會怎樣＋1 元變多少 → 收起來的細節。
用字（2026-10-23 使用者：「白話文一點不要那麼AI」）：頁面上說「七成長抱、三成機動」「警訊（通膨偏高、融資偏多、跌破年線）」，
不說核心／衛星／三種過熱／亮；規格與程式裡照舊叫核心、衛星、通膨／槓桿／趨勢（PLAIN 對照）。
數字全部由 core.py 算（研究檔、景氣頁的現在讀數、個股頁的衛星資料），這裡只排版；只描述照規則做的過去結果。
corespec VER 3（2026-10-23）：美股三成換成「美股強勢品質股」（ussxspec VER 3 的規則 QM；ussxqm.json 判定那個計畫過了才換）——
現在的持股、要買賣的、過去的成績讀 qm＝{"R": ussx_qm.json, "L": ussx_qm_live.json, "W": ussx_qm_watch.json}。
頁面不說「前瞻」，說「新規則驗證中」。"""
from __future__ import annotations

import html
import math
from datetime import date

from . import corespec as S
from . import ussxspec as QX

WD = "一二三四五六日"
CORE_HOW = {"tw": "大盤 ETF（0050 或 006208）", "spx": " S&P 500 ETF（例如 SPY、VOO）", "ndx": "那斯達克 100 ETF（例如 QQQ）"}
# 三個警訊的白話名稱（頁面只用這些，不用「通膨／槓桿／趨勢」「亮」）
PLAIN = {"tw": {"inf": "通膨偏高", "lev": "融資偏多", "trend": "跌破年線"},
         "spx": {"inf": "通膨偏高", "lev": "融資增加太快", "trend": "跌破年線", "flat": "總經策略全部空手"},
         "ndx": {"inf": "通膨偏高", "lev": "融資增加太快", "trend": "跌破年線", "flat": "總經策略全部空手"}}
SUB = {"tw": {"inf": "美國 CPI 年增率，跟過去 10 年比", "lev": "融資 ÷ 上市股票總市值，跟過去 3 年比"},
       "spx": {"inf": "美國 CPI 年增率，跟過去 10 年比", "lev": "美國家計部門證券融資年增率，跟過去 10 年比"},
       "ndx": {"inf": "美國 CPI 年增率，跟過去 10 年比", "lev": "美國家計部門證券融資年增率，跟過去 10 年比"}}
IDX = {"tw": "加權指數", "spx": "S&P 500", "ndx": "那斯達克 100"}
US = ("spx", "ndx")
QM_NAME = "美股強勢品質股"


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


def plain(mk: str, k: str) -> str:
    return PLAIN.get(mk, PLAIN["tw"]).get(k, k)


def _plain_names(mk: str, names) -> str:
    """研究檔記的是規格裡的名稱（通膨、槓桿、趨勢），頁面換成白話。"""
    by = {name: plain(mk, k) for k, name, *_ in S.FAMS.get(mk, S.FAMS["tw"])}
    return "、".join(by.get(n, n) for n in names)


# ── 現在 ─────────────────────────────────────────────────────────────────────

def _next_day(mk: str, d: str) -> str | None:
    try:
        from .xstrat import future_days
        return future_days(mk, d, 1)[0]
    except Exception:                                    # noqa: BLE001
        return None


def _next_day_n(mk: str, d: str, n: int) -> str | None:
    """d 之後第 n 個交易日（休市表）。"""
    try:
        from .xstrat import future_days
        return future_days(mk, d, n)[-1]
    except Exception:                                    # noqa: BLE001
        return None


# ── 美股三成：美股強勢品質股（corespec VER 3；ussxspec QM）──────────────────────────

def qm_on(mk: str, qm: dict | None) -> bool:
    """美股三成換成 QM：研究檔判定那個計畫過了（ussx_qm.json 的 switch）。"""
    R = (qm or {}).get("R") or {}
    return mk in US and bool((R.get("switch") or {}).get(mk))


def _ixn(mk: str) -> str:
    """接在中文後面的指數名（英文開頭前面空一格，同 CORE_HOW 的寫法）。"""
    n = IDX.get(mk, "指數")
    return _e((" " if n[:1].isascii() else "") + n)


def _qm_now(qm: dict | None) -> dict:
    return (((qm or {}).get("L") or {}).get("now")) or {}


def _qm_watch(qm: dict | None) -> dict:
    """每天的 50 日線檢查（只認對得上最新一週紀錄的那一份）。"""
    W = (qm or {}).get("W") or {}
    return W if W.get("base") and W.get("base") == _qm_now(qm).get("d") else {}


def _qm_per() -> str:
    return f"{S.SAT / QX.QM_SLOTS * 100:.2f}".rstrip("0").rstrip(".") + "%"


def _qm_rule() -> str:
    q = QX.QM
    return (f"每週五（休市就看那一週最後一個交易日）收盤，挑股價強勢（漲幅在美股前 {100 - q['rs']:.0f}%、離一年高點 {-q['d52h'] * 100:.0f}% 以內）、"
            f"本業賺錢（營益率 {q['om'] * 100:.0f}% 以上、股東權益報酬率 {q['roe'] * 100:.0f}% 以上）、市值 {q['cap'] / 1e8:.0f} 億美元以上的公司，"
            f"依強勢程度排；有空位就在下一個交易日開盤買，最多 {QX.QM_SLOTS} 檔、每檔約占全部資金 {_qm_per()}；"
            f"收盤跌破 50 日線，就在下一個交易日開盤賣。")


def _qm_pct_ma(h: dict, w: dict) -> float | None:
    if w.get("pct") is not None:
        return w["pct"]
    return h["px"] / h["ma"] - 1 if h.get("px") and h.get("ma") else None


def _qm_hold(mk: str, qm: dict | None, cash: bool) -> str:
    """美股三成現在拿著什麼。接在 plnnt 段落後面（同 _sat_now 的寫法）。"""
    n, W = _qm_now(qm), _qm_watch(qm)
    if not n:
        return '</p><p class="plnnt">每週紀錄還沒產生（每週六更新），先照上面的規則挑。'
    wl = {w["c"]: w for w in W.get("hold") or []}
    sold = {x["c"]: x for x in W.get("sell") or []}
    rows = ""
    for h in n.get("hold") or []:
        bits = [f'{_md(h["ent"])} 買，到 {_md(n["d"])} {_pc(h.get("r"))}']
        pct = _qm_pct_ma(h, wl.get(h["c"]) or {})
        if h["c"] in sold:
            x = sold[h["c"]]
            bits.append(f'{_md(x["trig"])} 收盤跌破 50 日線，{_md(x["on"])} 開盤賣')
        elif h.get("sell"):
            bits.append(f'{_md(n["d"])} 收盤跌破 50 日線，{_md(n.get("next"))} 開盤賣')
        elif pct is not None:
            bits.append(f'比 50 日線{"高" if pct >= 0 else "低"} {abs(pct) * 100:.1f}%')
        rows += (f'<div class="plnsn">{_e(h["c"])} {_wp((h.get("w") or 0) * S.SAT)}</div>'
                 f'<div class="plnsv">{"；".join(bits)}</div>')
    buys = n.get("buy") or []
    for c in buys:
        rows += (f'<div class="plnsn">{_e(c)} 約 {_qm_per()}</div>'
                 f'<div class="plnsv">{_md(n.get("next"))} 開盤買（{_md(n.get("wk"))} 的名單）</div>')
    idle = max(0.0, (n.get("idle") or 0.0) - len(buys) / QX.QM_SLOTS)
    if idle > 1e-3:
        rows += f'<div class="plnsn">{_e(IDX[mk])} {_wp(idle * S.SAT)}</div><div class="plnsv">空的位子先買指數</div>'
    hd = (f"三成現在放現金；買回時照這樣買（占全部資金，{_md(n['d'])} 收盤的比重）" if cash
          else f"三成現在買了這些（占全部資金，{_md(n['d'])} 收盤的比重）")
    return f'</p><div class="plnsat"><div class="plnsh">{hd}</div>{rows}</div><p class="plnnt plnhide">'


def _qm_next_week_end(d: str) -> str | None:
    from . import ussxqm as QM
    if not d:
        return None
    x = QM.next_day(d)
    while not QM.week_done(x):
        x = QM.next_day(x)
    return x


def _qm_todo(mk: str, qm: dict | None, cash: bool) -> str:
    n, W = _qm_now(qm), _qm_watch(qm)
    if not n:
        return ('<div class="plnw">—</div><div class="plnt">美股三成的每週紀錄還沒產生；每週六更新之後，這裡會列出要買賣的股票。</div>')
    last = W.get("d") or n.get("d")
    ev = []
    for x in W.get("sell") or []:
        done = bool(last and x["on"] <= last)
        ev.append((x["on"], "開盤", f'<b>賣掉 {_e(x["c"])}</b>' + ("（已經賣了）" if done else ""), f'{_md(x["trig"])} 收盤跌破 50 日線'))
    for c in n.get("sell") or []:
        ev.append((n["next"], "開盤", f'<b>賣掉 {_e(c)}</b>', f'{_md(n["d"])} 收盤跌破 50 日線'))
    if n.get("buy"):
        sub = f'{_md(n["wk"])} 的名單裡最前面、手上沒有的；每檔約占全部資金 {_qm_per()}' + ("；三成放現金中，先不買" if cash else "")
        ev.append((n["next"], "開盤", f'<b>買進 {"、".join(_e(c) for c in n["buy"])}</b>', sub))
    nf = _qm_next_week_end(last)
    sold0 = {x["c"] for x in W.get("sell") or []} | set(n.get("sell") or [])
    held = [h["c"] for h in n.get("hold") or [] if h["c"] not in sold0]
    free = max(0, QX.QM_SLOTS - len(held) - len(n.get("buy") or []))
    have = set(held) | set(n.get("buy") or [])
    cand = [x["c"] for x in n.get("list") or [] if x["c"] not in have][:3]
    if nf:
        sub = (f'現在有 {free} 個空位' if free else "現在沒有空位，有股票賣掉才會買") + (
            f'；{_md(n.get("wk"))} 的名單（{n.get("n_list", 0)} 檔）裡手上沒有的前幾名：{"、".join(_e(c) for c in cand)}'
            + ("（這一週還沒結束，名單會變）" if not n.get("wk_done") else "") if cand else "")
        ev.append((nf, "收盤", "<b>看這一週的新名單</b>：有空位就在下一個交易日開盤買", sub))
    ev.sort(key=lambda e: (e[0] or "", 0 if e[1] == "開盤" else 1))
    rows = "".join(f'<div class="plnw">{_e(_mdw(d))}<small>{_e(at)}</small></div><div class="plnt">{what}'
                   + (f'<span class="plnsub">{sub}</span>' if sub else "") + '</div>' for d, at, what, sub in ev)
    sold = {x["c"] for x in W.get("sell") or []} | set(n.get("sell") or [])
    wl = {w["c"]: w for w in W.get("hold") or []}
    near = sorted((p, h["c"]) for h in n.get("hold") or [] if h["c"] not in sold
                  for p in [_qm_pct_ma(h, wl.get(h["c"]) or {})] if p is not None)
    sub = f'最接近的是 {_e(near[0][1])}（比 50 日線高 {near[0][0] * 100:.1f}%）' if near and near[0][0] >= 0 else ""
    rows += ('<div class="plnw">每天收盤</div><div class="plnt">拿著的股票收盤跌破 50 日線，就在下一個交易日開盤賣'
             + (f'<span class="plnsub">{sub}</span>' if sub else "") + '</div>')
    return rows


def _qm_why_not(mk: str, qm: dict | None) -> str:
    """研究檔在、但那個計畫判定沒過：一句話說哪一條沒過（三成照舊放指數）。"""
    R = (qm or {}).get("R") or {}
    if mk not in US or not R:
        return ""
    if not (R.get("repro") or {}).get("ok"):
        return f"{QM_NAME}的規則重算和研究對不上，先不換（三成照舊買指數）。"
    v = R.get("verdict") or {}
    miss = [t for k, t in (("c1", "三成本身沒有贏 S&amp;P 500"), ("c2", "放進計畫的錢沒有比較多"), ("c3", "用複委託的手續費不成立"),
                           ("c4", "已下市公司缺資料的影響太大")) if not (v.get(k) if k in ("c1", "c4") else (v.get(k) or {}).get(mk))]
    if k_c1 := v.get("c1"):
        if isinstance(k_c1, dict) and all(k_c1.values()):
            miss = [m for m in miss if not m.startswith("三成本身")]
    return f"{QM_NAME}放進這個計畫的判定沒過（{'、'.join(miss) or '—'}），三成照舊買指數。" if miss else ""


def now_html(mk: str, N: dict, stk: dict | None, qm: dict | None = None) -> str:
    nxt, cur = N["next"], N["now"]
    cash = nxt < 0.99
    day = _next_day(mk, N["d"]) if N.get("due") else None
    big = f'{round(nxt * 100)}%'
    sub = f'{_e(_mdw(day))} 收盤要調成這樣' if day else f'目前該拿的部位（依 {_e(_md(N["d"]))} 收盤）'
    bar = ('<div class="plnbar"><i class="plnbc">長抱 70%</i>'
           + ('<i class="plnbx">機動 30% 放現金</i>' if cash else '<i class="plnbs">機動 30%</i>') + '</div>')
    if mk == "tw":
        st = (stk or {}).get("st") or []
        if st:
            w = round(S.SAT / len(st) * 100)
            names = "、".join(_e(s["name"]) for s in st)
            txt = (f"七成買{_e(CORE_HOW[mk])}一直抱著。另外三成分成 {len(st)} 份、每份 {w}%，"
                   f"跟著個股策略頁打 ★ 的策略買賣：{names}。哪個策略手上沒有股票，那一份就先買大盤。") + _sat_now(stk, cur < 0.99)
        else:
            txt = f"七成買{_e(CORE_HOW[mk])}一直抱著。另外三成跟著個股策略頁打 ★ 的策略買賣（現在讀不到名單，先買大盤）。"
    elif qm_on(mk, qm):
        txt = (f"七成買{_e(CORE_HOW[mk])}一直抱著。另外三成買<b>{QM_NAME}</b>（2026/10/23 換上的新規則，驗證中）：{_qm_rule()}"
               f"空的位子先買{_ixn(mk)}。") + _qm_hold(mk, qm, cur < 0.99)
    else:
        why = _qm_why_not(mk, qm)
        txt = (f"七成買{_e(CORE_HOW[mk])}一直抱著。另外三成現在也買同一個指數；" + (why or "美股的個股策略資料還在補，做好、驗證過再換。"))
    due = ""
    names = "、".join(plain(mk, f["k"]) for f in N["fams"] if f["lit"])
    need = N.get("need") or 1
    if day and cash:
        due = (f'<p class="plndue"><b>{_e(_mdw(day))} 收盤：把機動的三成全部賣掉，改放現金</b>'
               f'（{_e(names)}），之後只留七成。</p>')
    elif day:
        why = f"警訊少於兩個滿 {need} 個交易日" if need > 1 else "警訊解除"
        due = (f'<p class="plndue plndok"><b>{_e(_mdw(day))} 收盤：把機動的三成買回來</b>（{why}）'
               + ("。照各策略當時該有的股票買，沒有股票的那一份買大盤" if mk == "tw" else
                  "。照美股強勢品質股當時拿著的股票買，空的位子買指數" if qm_on(mk, qm) else "") + '。</p>')
    elif cash and N.get("ok") and need > 1:
        c = N.get("clear") or 0
        buy = _next_day_n(mk, N["d"], need - c + 1)
        due = (f'<p class="plndue">機動的三成現在放現金。警訊已經少於兩個（第 {c} 天），要滿 {need} 個交易日才買回：'
               f'接下來都沒有警訊的話，最快 {_e(_mdw(buy))} 收盤買回。</p>')
    elif cash:
        due = ('<p class="plndue">機動的三成現在放現金。'
               + (f"等警訊少於兩個、而且連續 {need} 個交易日都這樣，下一個交易日收盤再買回來。</p>" if need > 1
                  else "等警訊解除，下一個交易日收盤再買回來。</p>"))
    was = "" if abs(cur - nxt) < 0.001 else f'<small class="plnwas">現在手上 {round(cur * 100)}%</small>'
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
    hd = "三成現在放現金；買回時照這樣買（占全部資金）" if cash else "三成現在買了這些（占全部資金）"
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
    sub = [f"這個策略占 {w}%"]
    if e.get("how") and act == "買進" and not e.get("pending"):
        sub.append(_e(e["how"]))
    if cash and act == "買進":
        sub.append("三成放現金中，先不買")
    return when, what + f'<span class="plnsub">{"・".join(sub)}</span>'


def todo_html(mk: str, N: dict, stk: dict | None, qm: dict | None = None) -> str:
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
            rows = '<div class="plnw">—</div><div class="plnt">接下來 45 天，三成裡的個股策略沒有排定的買賣。</div>'
    elif qm_on(mk, qm):
        rows = _qm_todo(mk, qm, cash)
    else:
        rows = '<div class="plnw">平常</div><div class="plnt">三成也買同一個指數，不用動，只要注意下面四個警訊。</div>'
    return f'<h4 class="plnh">接下來要做的事</h4>' + (f'<div class="plntodo">{rows}</div>' if rows else "") + _fam_html(mk, N)


def _fam_html(mk: str, N: dict) -> str:
    rows = ""
    near = []
    for f in N["fams"]:
        on, nm = f["lit"], plain(mk, f["k"])
        if f["k"] == "trend":
            pct, ma, trig = f.get("pct"), f.get("ma"), f.get("trig")
            if pct is None:
                val, bar = "年線還算不出來", '<div class="plngz"><i style="width:0"></i><b style="left:50%"></b></div>'
            else:
                w = max(0.0, min(100.0, 50.0 - pct * 2.5))     # 越長越接近警訊：比年線高 20% 以上＝空、在年線上＝一半、低 20%＝滿
                val = f'比年線{"低" if pct < 0 else "高"} {abs(pct):.1f}%' + ("（警訊）" if on else "")
                bar = (f'<div class="plngz"><i class="{"plngdn" if on else ""}" style="width:{w:.1f}%"></i>'
                       '<b style="left:50%"></b></div>')
                if not on:
                    near.append((abs(pct) / 10, f"跌破年線（下一個交易日收盤低於 {_px(trig)} 點就算）"))
            sub = f'{IDX.get(mk, "指數")}收盤 vs 年線' + (f'（200 日均線 {_px(ma)}）' if ma else "")
        elif f["k"] == "flat":
            held, na = f.get("held") or [], f.get("n_all") or 0
            w = 100.0 * (1 - len(held) / na) if na else (100.0 if on else 0.0)   # 越長越接近警訊：全部空手＝滿
            val = "全部空手（警訊）" if on else f"{len(held)} 條有部位"
            bar = (f'<div class="plngz"><i class="{"plngdn" if on else ""}" style="width:{w:.1f}%"></i>'
                   '<b style="left:calc(100% - 2px)"></b></div>')
            sub = ("有部位的：" + "、".join(_e(x) for x in held)) if held else "所有總經策略都沒有部位"
            if not on and len(held) == 1:
                near.append((0.4, f"總經策略全部空手（只剩{held[0]}有部位）"))
        else:
            v = f.get("v")
            w = 0 if v is None else max(0.0, min(100.0, v))
            val = "沒有資料" if v is None else f'{v:.1f} 分' + ("（警訊）" if on else "")
            bar = f'<div class="plngz"><i class="{"plngdn" if on else ""}" style="width:{w:.1f}%"></i><b></b></div>'
            src = f.get("src")
            sub = _e(SUB.get(mk, SUB["tw"]).get(f["k"], f["desc"])) + (f'；資料到 {_e(_ym(src) if len(src) <= 7 else _md(src))}' if src else "")
            if f.get("stale"):
                sub += "（資料過期）"
            if not on and v is not None:
                near.append(((S.HOT - v) / 20, f"{nm}（再 {S.HOT - v:.1f} 分就到）"))
        rows += (f'<div class="plnn">{_e(nm)}<small>{sub}</small></div>{bar}'
                 f'<div class="plnv{" plnvon" if on else ""}">{_e(val)}</div>')
    n = N["n"]
    flat = any(f["k"] == "flat" and f["lit"] for f in N["fams"])
    lit = "、".join(plain(mk, f["k"]) for f in N["fams"] if f["lit"] and f["k"] != "flat")
    cut = n >= S.NEED or flat
    if cut:
        parts = ([f"{n} 個警訊（{lit}）"] if n else []) + (["總經策略全部空手"] if flat else [])
        lead = f"現在{'，而且'.join(parts)}，只拿 <b>70%</b>。"
    else:
        hold = N["next"] >= 0.99
        lead = "現在沒有警訊，" if n == 0 else f"現在有 {n} 個警訊（{_e(lit)}），"
        lead += ("拿 <b>100%</b>。" if n == 0 else "還是拿 <b>100%</b>。") if hold else \
            f"三成還在等買回（警訊少於兩個第 {N.get('clear') or 0} 天，要滿 {N.get('need') or 1} 天），現在拿 <b>70%</b>。"
    if not cut:
        if near:
            near.sort()
            if n == S.NEED - 1:
                lead += f'<span class="plnw2">再多一個就要賣掉三成；最接近的是{_e(near[0][1])}。</span>'
            else:
                lead += f'最接近的是{_e(near[0][1])}。'
    need = N.get("need") or 1
    if mk in S.FLAT:
        rule = ("<b>兩個以上同時出現，或總經策略全部空手：下一個交易日收盤把機動的三成賣掉換現金，只留七成。"
                "都解除了，下一個交易日收盤再買回來。</b>")
        head = "看四個警訊"
    else:
        rule = ("<b>兩個以上同時出現：下一個交易日收盤把機動的三成賣掉換現金，只留七成。"
                + (f"之後警訊少於兩個滿 {need} 個交易日（約兩週），下一個交易日收盤再買回來。</b>" if need > 1
                   else "警訊少於兩個，下一個交易日收盤再買回來。</b>"))
        head = "看三個警訊"
    return (f'<div class="plntrig"><div class="plnw">每天收盤後<small>{head}</small></div><div class="plnt">{rule}'
            '<small class="plngl">分數＝跟自己過去比的高低（0～100），到 80 分算警訊；長條碰到直線就是警訊。</small>'
            f'<div class="plnfam">{rows}</div><p class="plnsum">{lead}</p></div></div>')


# ── 過去 ─────────────────────────────────────────────────────────────────────

def _label(mk: str, s: dict) -> str:
    if mk == "tw" and s["key"] == "plan":
        return f'{_ym(s["a"])}～{_ym(s["b"])}；這段時間三成放財報驚喜（大型股）'
    if mk in US and s["key"] == "plan":
        return f'{QX.QM_EVAL}/1～{_ym(s["b"])}；這段時間三成放{QM_NAME}'
    if s["key"] == "early":
        return f'{s["a"][:4]}～{s["b"][:4]}'
    return f'{s["a"][:4]} 年起'


def _qm_plan(mk: str, qm: dict | None, ck: str = "main") -> dict:
    """研究檔裡那個計畫的摘要：{"new": 三成放 QM, "cur": 三成也買指數（同一段期間）, "judge"}。"""
    return ((((qm or {}).get("R") or {}).get("plans") or {}).get(f"{mk}_{ck}")) or {}


def benefit_html(mk: str, sc: dict, qm: dict | None = None) -> str:
    s = sc.get("plan") or sc.get("rule")
    if not s:
        return ""
    p, h = s["plan"], s["hold"]
    w, n = _wins(p, h)
    kp = (f'<div class="plnkpi"><div><div class="plnkl">100 萬變成</div><div class="plnkv plnkg">{_wan(p["m"])}</div><div class="plnkr">一直抱著{"大盤" if mk == "tw" else ""} {_wan(h["m"])}</div></div>'
          f'<div><div class="plnkl">最慘時從高點跌</div><div class="plnkv">{_ab(p["mdd"])}</div><div class="plnkr">一直抱著 {_ab(h["mdd"])}</div></div>'
          f'<div><div class="plnkl">比一直抱著多賺的年份</div><div class="plnkv">{w}／{n} 年</div><div class="plnkr">最差的一年 {_pc(p.get("worst"))}（一直抱著 {_pc(h.get("worst"))}）</div></div></div>')
    note = ""
    cur = _qm_plan(mk, qm).get("cur") if mk in US and s["key"] == "plan" else None
    if cur:
        note = (f'<p class="plnnote">同一段時間，如果三成也買{_ixn(mk)}、只靠警訊進出：100 萬變 {_wan(cur["plan"]["m"])}'
                f'（一直抱著 {_wan(cur["hold"]["m"])}），最慘時跌 {_ab(cur["plan"]["mdd"])}。'
                '多出來的錢是三成買的股票賺的。</p>')
    elif mk == "tw" and sc.get("rule"):
        r = sc["rule"]
        note = (f'<p class="plnnote">如果三成也買大盤、只靠警訊進出：{r["a"][:4]} 年起 100 萬變 {_wan(r["plan"]["m"])}（一直抱著 {_wan(r["hold"]["m"])}），'
                f'最慘時跌 {_ab(r["plan"]["mdd"])}（一直抱著 {_ab(r["hold"]["mdd"])}）。</p>')
    elif sc.get("early"):
        e = sc["early"]
        note = (f'<p class="plnnote">更早的 {e["a"][:4]}～{e["b"][:4]} 年（訂規則時沒有看這段）：100 萬變 {_wan(e["plan"]["m"])}'
                f'（一直抱著 {_wan(e["hold"]["m"])}），最慘時跌 {_ab(e["plan"]["mdd"])}（一直抱著 {_ab(e["hold"]["mdd"])}）。</p>')
    return f'<h4 class="plnh">過去照做的結果<span>{_e(_label(mk, s))}</span></h4>{kp}{note}'


def expect_html(mk: str, sc: dict) -> str:
    s = sc.get("plan") or sc.get("rule")
    if not s or not s["plan"].get("q"):
        return ""
    p, h = s["plan"], s["hold"]
    q, hq = p["q"], h["q"]
    cells = [("運氣不好（10 次裡最差那次）", _pc(q[0]), f"一直抱著 {_pc(hq[0])}"), ("一般", _pc(q[1]), f"一直抱著 {_pc(hq[1])}"),
             ("運氣好（10 次裡最好那次）", _pc(q[2]), f"一直抱著 {_pc(hq[2])}"), ("一年後虧錢的機會", _ab(p["loss"]), f"一直抱著 {_ab(h['loss'])}")]
    dist = "".join(f'<div><div class="plnkl">{a}</div><div class="plnkv">{b}</div><div class="plnkr">{c}</div></div>' for a, b, c in cells)
    ch = s["chart"]
    return ('<h4 class="plnh">照做一年會怎樣<span>從過去每一天開始算，往後 12 個月</span></h4>'
            f'<div class="plndist">{dist}</div>{chart(ch, 960, 250, 12, "plnchd")}{chart(ch, 360, 190, 12, "plnchm")}'
            '<div class="plnlg"><span><i></i>照計畫做</span><span><i class="plnlgh"></i>一直抱著</span>'
            '<span><i class="plnlgc"></i>三成放現金的期間</span></div>')


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


def _qm_wins(R: dict, base: str = "spx_tr") -> tuple[int, int]:
    """三成本身贏 base 的年份（研究檔逐年；起算那一年不算）。"""
    sy = ((R.get("sleeve") or {}).get("main") or {}).get("years") or {}
    by = ((R.get("bench") or {}).get(base) or {}).get("years") or {}
    ys = [y for y in sorted(sy) if y > R.get("eval", "")[:4] and y in by]
    return sum(1 for y in ys if sy[y] > by[y]), len(ys)


def _qm_why(qm: dict | None) -> list[str]:
    R = (qm or {}).get("R") or {}
    sl = ((R.get("sleeve") or {}).get("main")) or {}
    bn = R.get("bench") or {}
    w, n = _qm_wins(R)
    r3 = ((R.get("desc") or {}).get("roll3")) or []
    out = [f'三成買<b>{QM_NAME}</b>（2026/10/23 起）：只挑漲得兇的股票，會買到很多不賺錢、上下震盪很大的公司，2014 年起反而輸大盤；'
           '加上「本業賺錢」（營益率、股東權益報酬率）和「市值夠大」之後才穩定贏。',
           '這套是 2,016 種做法裡挑的（21 類條件 × 檔數 × 賣法 × 看不看大盤）。同一類條件的 96 種做法有 82% 在 2014～2019、2020 以後兩段都贏 S&amp;P 500；'
           '只用 2010～2017 年（或 2010～2019 年）的成績替 21 類條件排名，排第 1 的也都是這一類，之後一年也多賺約 4 個百分點。']
    if sl.get("cagr") is not None and (bn.get("spx_tr") or {}).get("cagr") is not None:
        t = (f'三成本身 {QX.QM_EVAL} 年起一年賺 {_pc(sl["cagr"], 1, False)}（S&amp;P 500 含息 {_pc(bn["spx_tr"]["cagr"], 1, False)}'
             + (f'、QQQ {_pc(bn["qqq"]["cagr"], 1, False)}' if (bn.get("qqq") or {}).get("cagr") is not None else "") + '）'
             + (f'，{n} 年裡 {w} 年贏 S&amp;P 500' if n else "")
             + (f'；從任一個月起算的三年，{r3[1]} 次裡 {r3[0]} 次贏' if len(r3) == 2 and r3[1] else "") + '。')
        out.append(t)
    out.append('多賺的錢大部分是三成買的股票賺的；有警訊時換現金，主要是讓大跌那幾年少賠。')
    return out


def _qm_check(qm: dict | None) -> str:
    """上線後怎麼檢查（美股三成那一段）。"""
    from . import ussxqm as QM
    L, R = (qm or {}).get("L") or {}, (qm or {}).get("R") or {}
    nw = len(L.get("weeks") or {})
    t = (f'{QM_NAME}另外每週六記一次（{_md(QX.QM_LIVE)} 起；' + (f"已記 {nw} 週" if nw else "還沒有紀錄") + '）：那一週的名單、買賣、週末的持股和三成的淨值。'
         f'滿 {"、".join(str(k) for k in QX.QM_REVIEW)} 個交易日時，三成本身比 S&amp;P 500 含息多賺多少，跟回測裡同樣長度的期間比，'
         f'落在最差的 {round(QX.QM_P_LOW * 100)}% 就標「比回測差」。回測裡也有落後大盤的年份，只看幾個月不準，一年那一次比較有參考價值。'
         '不會自動換回指數，要不要換回由你決定。')
    try:
        rv = [x for x in QM.review_now(L, R) if x.get("d")]
    except Exception:                                    # noqa: BLE001
        rv = []
    for x in rv:
        t += (f'第 {x["k"]} 個交易日（{_md(x["d"])}）：三成比 S&amp;P 500 含息{"多" if x["ex"] >= 0 else "少"}賺 {abs(math.expm1(x["ex"])) * 100:.1f}%'
              + (f'，在回測同樣長度的期間裡排在最差的 {x["pct"] * 100:.0f}%' if x.get("pct") is not None else "")
              + ('（比回測差）' if x.get("low") else "") + '。')
    return f'<p>{t}</p>'


def _qm_care(mk: str, qm: dict | None) -> list[str]:
    R = (qm or {}).get("R") or {}
    out = ['這套規則是看過 2014 年以後的成績才挑的，回測的數字會比以後實際做的好；真正的考驗是 2026/10/23 起的紀錄。']
    top = [c for c, _ in (R.get("top") or [])[:5]]
    tv = [v for _, v in (R.get("top") or [])[:5] if v is not None]
    dr = ((R.get("desc") or {}).get("drop") or {})
    kk = max((int(k) for k in dr), default=0)
    spx = ((R.get("bench") or {}).get("spx_tr") or {}).get("cagr")
    if top:
        t = f'賺的錢集中在少數幾檔大飆股（賺最多的是 {"、".join(_e(c) for c in top)}'
        t += f'，每檔占淨賺的 {min(tv) * 100:.0f}%～{max(tv) * 100:.0f}%）' if tv else "）"
        if kk and dr.get(str(kk), {}).get("cagr") is not None:
            t += (f'。拿掉賺最多的 {kk} 檔（當它們不存在），三成本身一年剩 {_pc(dr[str(kk)]["cagr"], 1, False)}'
                  + (f'（S&amp;P 500 含息 {_pc(spx, 1, False)}）' if spx is not None else ""))
        out.append(t + '。')
    tr = R.get("trades") or {}
    if tr.get("n"):
        yrs = max(1e-9, (date.fromisoformat(R["last"]) - date.fromisoformat(R["a"])).days / 365.25)
        out.append(f'{QX.QM_Y0} 年起 {tr["n"]:,} 筆交易（一年約 {tr["n"] / yrs:.0f} 筆），'
                   f'賺錢的 {_ab(tr.get("win"))}、每筆中位數 {_pc(tr.get("med"))}：很多小賠、少數大賺。')
    ys = ((R.get("desc") or {}).get("years")) or {}
    lag = [(y, v[0], v[1]) for y, v in sorted(ys.items()) if y > R.get("eval", "")[:4] and v[0] is not None and v[1] is not None and v[0] < v[1]]
    if lag:
        out.append('輸 S&amp;P 500 的年份：' + "、".join(f'{y} 年 {_pc(a)}（S&amp;P 500 含息 {_pc(b)}）' for y, a, b in lag) + '。')
    pm, pa = _qm_plan(mk, qm).get("new") or {}, _qm_plan(mk, qm, "alt").get("new") or {}
    sa = ((R.get("sleeve") or {}).get("alt") or {}).get("cagr")
    if pm.get("plan") and pa.get("plan"):
        out.append(f'用複委託的手續費（每邊 {QX.COST["stk_alt"] * 100:.2f}%）算：'
                   + (f'三成本身一年 {_pc(sa, 1, False)}，' if sa is not None else "")
                   + f'放進計畫 100 萬變 {_wan(pa["plan"]["m"])}（海外券商每邊 {QX.COST["stk"] * 100:.2f}% 是 {_wan(pm["plan"]["m"])}）。')
    G = (R.get("verdict") or {}).get("surv_G")
    out.append((f'已下市公司的資料有缺：全市場量過，一年約多算 {G * 100:.1f} 個百分點。' if G is not None else "已下市公司的資料有缺。")
               + '財報資料 2009 年才有，沒有經歷過 2008 年那種崩盤；那種時候靠警訊把三成換成現金。')
    amt = f"{S.SAT / QX.QM_SLOTS * 100:.2f}".rstrip("0").rstrip(".")
    out.append(f'每檔約占全部資金 {_qm_per()}：100 萬的帳戶每檔約 {amt} 萬台幣，股價高的要買零股。')
    if mk != "spx":
        out.append(f'三成本身的數字和現在拿的比重，是照 S&amp;P 500 計畫的帳算的（空的位子放 S&amp;P 500）；{_e(IDX[mk])} 計畫拿的股票一樣，'
                   f'空的位子改買{_ixn(mk)}，數字差一點點。')
    return out


def details_html(mk: str, sc: dict, fw: dict | None, qm: dict | None = None) -> str:
    s = sc.get("plan") or sc.get("rule")
    if not s:
        return ""
    qmo = mk in US and s["key"] == "plan"
    out = []
    if mk == "tw":
        why = ['訊號總覽上的台股訊號（517 個），每一個都試過「出現就把三成換成現金」。台股和美股都有用的只有兩個：'
               '<b>通膨偏高</b>（美國 CPI 年增率在過去 10 年的高檔）、<b>融資偏多</b>（融資 ÷ 上市股票總市值）。'
               '只看跌破年線或技術面過熱就賣，台股反而少賺。']
    else:
        why = ['訊號總覽上的美股訊號（每個指數 333～343 個），每一個都試過「出現就把三成換成現金」。台股和美股都有用的只有兩個：'
               '<b>通膨偏高</b>（美國 CPI 年增率在過去 10 年的高檔）、<b>融資增加太快</b>（美國家計部門證券融資年增率）。']
    why += ['三個警訊一起看，<b>兩個以上同時出現才賣</b>：台股、S&amp;P 500、那斯達克 100 不管看全部期間、前一半、後一半還是最近 10 年，'
            '都比一直抱著賺得多（三成也買大盤時）。',
            '「看多」就是沒有兩個以上警訊：要等到有明確的看多訊號（站上年線、12 個月是漲的、總經策略多數有部位……）才加到十成，'
            '三個市場都比一直抱著少賺——沒看多的日子市場平均還是在漲，只拿七成就把那段漲幅讓掉了。']
    if mk == "tw":
        why += ['賣掉之後要<b>警訊少於兩個滿兩週（10 個交易日）才買回</b>（2026/10/23 起）：台股常在年線附近上下穿，原本 5 天內就買回的有 23 次、'
                '合計少賺 3.7 個百分點；改成等兩週之後，一年買賣從 3.9 次降到 1.4 次。同樣的做法用在那斯達克 100 會少賺（V 型反彈買太晚），所以只用在台股。',
                '台股多賺的錢，大部分是三成買的個股策略賺的；有警訊時換現金，主要是讓大跌那幾年少賠。']
    else:
        why += ['<b>總經策略全部空手時也賣</b>（2026/10/23 起）：RSI(2)、月底月初、Halloween、10 個月均線、200 日均線、12 個月動能、'
                '各種落底策略全部都沒有部位，通常是空頭行情裡的 5～10 月。加了之後 2000 年起和訂規則時沒看的更早期間都比較好，但這種情況次數不多'
                '（那斯達克 100 1986 年起只有 6 次，主要在 1990、2001 年）。']
        why += _qm_why(qm) if qmo else ['多賺的錢來自大跌那幾年：三成換成現金，那幾年少賠。']
    out.append('<details class="plnd"><summary>為什麼這樣設計</summary><ul>' + "".join(f"<li>{x}</li>" for x in why) + "</ul></details>")
    eps = s.get("eps") or []
    if eps:
        tr = "".join(f'<tr><td class="plntl">{_e(e["d"])}</td><td>{_e(_md(e["sell"]))}</td>'
                     f'<td>{_e(_md(e["buy"])) if e.get("buy") else "還放現金"}</td><td class="plntl">{_e(_plain_names(mk, e["lit"]))}</td>'
                     f'<td>{e["days"]}</td><td>{_pc(e["ix"])}</td><td>{_pc(e["diff"], 1)}</td></tr>' for e in reversed(eps))
        out.append(f'<details class="plnd"><summary>過去每一次賣掉三成（{len(eps)} 次）</summary><div class="plntw"><table class="plntb">'
                   '<tr><th class="plntl">看到警訊</th><th>賣出</th><th>買回</th><th class="plntl">當時的警訊</th><th>天數</th>'
                   f'<th>這段期間{"大盤" if mk == "tw" else "指數"}漲跌</th><th>對整個帳戶</th></tr>'
                   f'{tr}</table></div><p class="plnnote">「對整個帳戶」＝這段期間三成放現金，比繼續拿著多賺（正）或少賺（負）整個帳戶的幾 %，'
                   '沒算買賣手續費。</p></details>')
    ys = list(zip(s["plan"]["years"], s["hold"]["years"]))
    if ys:
        tr = "".join(f'<tr><td class="plntl">{y}{"" if n >= S.YEAR_MIN else "（不滿一年）"}</td><td>{_pc(r)}</td><td>{_pc(rh)}</td><td>{_pc(r - rh)}</td></tr>'
                     for (y, r, n), (_, rh, _) in reversed(ys))
        out.append('<details class="plnd"><summary>每一年的報酬</summary><div class="plntw"><table class="plntb">'
                   '<tr><th class="plntl">年</th><th>照計畫做</th><th>一直抱著</th><th>差</th></tr>' + tr + "</table></div></details>")
    rows = []
    idx = "大盤" if mk == "tw" else "指數"
    for key, nm in (("plan", "照計畫做"), ("rule", f"只靠警訊進出（三成也買{idx}）"), ("early", "訂規則時沒有看的期間")):
        x = sc.get(key)
        if not x:
            continue
        h1, h2, rc = x["halves"][0], x["halves"][1], x["recent"]
        rows.append(f'<tr><td class="plntl">{_e(nm)}<small>{_e(x["a"][:7])}～{_e(x["b"][:7])}</small></td>'
                    f'<td>{_wan(x["plan"]["m"])}<small>一直抱著 {_wan(x["hold"]["m"])}</small></td>'
                    f'<td>{_wan(x["fixed"]["m"])}</td>'
                    f'<td>{_wan(h1["plan"]["m"])}<small>一直抱著 {_wan(h1["hold"]["m"])}</small></td>'
                    f'<td>{_wan(h2["plan"]["m"])}<small>一直抱著 {_wan(h2["hold"]["m"])}</small></td>'
                    f'<td>{_wan(rc["plan"]["m"])}<small>一直抱著 {_wan(rc["hold"]["m"])}</small></td>'
                    f'<td>{_ab(x["avg"])}</td><td>{x["sw"]:.1f}</td></tr>')
    if rows:
        out.append('<details class="plnd"><summary>拆成不同期間看</summary><div class="plntw"><table class="plntb">'
                   '<tr><th class="plntl">期間</th><th>100 萬變成</th><th>一樣多的錢一直拿著</th><th>前一半</th><th>後一半</th><th>最近 10 年</th>'
                   '<th>平均拿</th><th>一年買賣幾次</th></tr>'
                   + "".join(rows) + '</table></div><p class="plnnote">「一樣多的錢一直拿著」＝平均拿的部位跟計畫一樣，但不管警訊、一直拿著。'
                   '計畫要比它多，才代表賣掉和買回的時間點真的有用。前一半、後一半、最近 10 年各自從 100 萬算起。</p></details>')
    fw = fw or {}
    left = f"已記錄 {fw.get('n', 0)} 個交易日" if fw.get("n") else "還沒有紀錄"
    nxt = fw.get("next")
    out.append('<details class="plnd"><summary>上線後怎麼檢查</summary>'
               f'<p>{_e(_md(S.LIVE_START))} 起每天記下：計畫該拿多少、三個警訊的分數、三成放了哪些策略（{left}）。'
               f'滿 {"、".join(str(c) for c in S.CHECKS)} 個交易日時，各跟過去同樣長度的期間比一次：照做比一直抱著多賺還是少賺，'
               '如果落在過去最差的兩成就標出來。每天也會看照做的跌幅有沒有比過去最慘的一次'
               f'（{_ab(s["plan"]["mdd"])}）還深。' + (f"下一次比是第 {nxt} 個交易日。" if nxt else "")
               + ("台股三成的實際報酬，之後會用各策略自己的每一筆交易重算。" if mk == "tw" else "")
               + '有狀況會標在這裡，不會自動停掉，要不要停由你決定。</p>' + (_qm_check(qm) if qmo else "") + '</details>')
    care = []
    if mk == "tw":
        care += ['回測裡的三成只有財報驚喜（大型股）：臺灣50 提前卡位 2024 年底、長線投信動能 2025 年才有紀錄，上線後才照規則加進來。'
                 '這三個策略都是看過成績才挑的，真正的考驗是上線後的紀錄。',
                 '財報驚喜的帳 2026/10/23 修正過：年報那一期和第一季那一期每年重疊約一個月，之前同一筆錢算了兩次報酬；'
                 '修正後它自己的年化從 49.5% 變 30.4%。',
                 '換現金賺到的多半在大跌的年份（台股 2008 年那一次最多）；平常的年份跟一直抱著差不多。',
                 '三成分成很多檔，100 萬的帳戶每檔大約 1～2 萬，高價股要買零股。']
        if s["plan"].get("ex_best") is not None:
            care.append(f'去掉最好的一年（{_e(s["plan"].get("best_y") or "")}），年化還有 {_pc(s["plan"]["ex_best"], 1, False)}'
                        f'（一直抱著 {_pc(s["hold"].get("ex_best"), 1, False)}）。')
    else:
        e = sc.get("early")
        if qmo:
            care += _qm_care(mk, qm)
            care.append('警訊換現金賺到的多半在大跌的年份（2000～2002、2008、2020、2022）。')
        else:
            care += ['賺到的多半在大跌的年份（2000～2002、2008、2020、2022）；平常的年份兩邊都拿 100%，跟一直抱著一樣。',
                     '美股的三成現在買指數；美股個股策略做好、驗證過才會換。']
        if e:
            care.append(('警訊的規則（三成也買指數）在' if qmo else "") + f'訂規則時沒有看的 {e["a"][:4]}～{e["b"][:4]} 年：100 萬變 {_wan(e["plan"]["m"])}（一直抱著 {_wan(e["hold"]["m"])}），'
                        f'最慘時跌 {_ab(e["plan"]["mdd"])}（一直抱著 {_ab(e["hold"]["mdd"])}）：錢{"多一點" if e["plan"]["m"] >= e["hold"]["m"] else "少一點"}、跌得比較少。')
    care.append('以上都是過去照規則做的結果，不代表以後也會一樣。')
    out.append('<details class="plnd"><summary>要注意的事</summary><ul>' + "".join(f"<li>{x}</li>" for x in care) + "</ul></details>")
    return '<h4 class="plnh">細節</h4>' + "".join(out)


# ── 卡片 ─────────────────────────────────────────────────────────────────────

def card(mk: str, N: dict | None, R: dict | None, stk: dict | None = None, fw: dict | None = None,
         qm: dict | None = None) -> str:
    if mk not in S.MARKETS:
        return '<div class="pln plnoff"><b>交易計畫</b>目前只做台股、S&amp;P 500、那斯達克 100，請在上面切換市場。</div>'
    sc = (((R or {}).get("mk") or {}).get(mk) or {}).get("sc") or {}
    on = qm_on(mk, qm)
    if on and ((qm["R"].get("sc") or {}).get(mk)):
        sc = {**sc, "plan": qm["R"]["sc"][mk]}
    hd = ('<div class="plnhd"><h3>交易計畫：七成長抱，三成機動</h3><span class="plntag">上線觀察中</span>'
          + ('<span class="plntag">美股三成：新規則驗證中</span>' if on else "") + '</div>')
    if not N:
        body = '<p class="plnnote">今天的分數還沒算出來（景氣頁建頁時會算），先列過去的成績。</p>'
    else:
        body = now_html(mk, N, stk, qm) + todo_html(mk, N, stk, qm)
    if sc:
        body += benefit_html(mk, sc, qm) + expect_html(mk, sc) + details_html(mk, sc, fw, qm)
    else:
        body += '<p class="plnnote">過去的成績還沒算出來。</p>'
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
