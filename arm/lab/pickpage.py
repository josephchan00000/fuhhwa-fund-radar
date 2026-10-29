"""選股頁（x9.html 的「選股」身分：台股｜美股｜個股；docs/lab_pick_page_plan.md）。

使用者 2026-10-28：「你的投資組合太不成熟了，幫我重新設計直接把配置那頁拿掉，然後把現有的選股策略做好妥善的規劃呈現出來單獨一頁，
我要分成台股跟美股，有不同策略建議進場的時程行事曆…本來的配置回測那些丟到研究紀錄裡面」。
- 每個市場：進場行事曆（pickcal 的事件；月曆與接下來 4 週在瀏覽器畫）→ 每條策略一張卡（Python 組好的 HTML）→ 其他策略（收起）。
- 每條策略自己一份錢：卡片寫同時幾檔、每檔多少，不寫占全部資金幾 %（投資組合層級的比例、警訊換現金在研究紀錄・交易計畫）。
- 只整理既有的資料（advice、新飆股那本帳、美股強勢品質股的每週紀錄與每天檢查），不改任何規則、不重算回測。
用字照主頁面的規則（CLAUDE.md「主頁面用字」；tests/test_plain.py 掃畫面）。CSS class、JS 函式一律 pk 開頭。
"""
from __future__ import annotations

import html
import json

from . import cfgpage as CFP
from . import corepage as CPG
from . import pickcal as PC

MAIN_TIER = "good"                     # 判定好的個股策略＝主要；ref＝其他（收起、行事曆預設不顯示）
OTHER_TIER = "ref"

# 每條策略：選什麼、時程、怎麼分錢（文字照 advice 的規則；數字寫死的只有規則本身的參數）
META = {
    "boom": {"what": "強勢股：每年用之前幾年的資料，找出「之後 60 個交易日容易大漲」的條件，每週挑出符合的股票、依強度排",
             "when": "每週最後一個交易日收盤出名單，下一個交易日開盤買（有空位、現金夠才買）；買進後第 60 個交易日收盤到期，隔天開盤賣",
             "money": "每次買進用這條策略 12.5% 的錢（現金不夠就買少一點），最多 20 檔", "freq": "每週"},
    "s3": {"what": "可能被納入臺灣50 的股票：審核資料截止日前 25 個交易日，依當天的市值排名，挑漲勢最強的 4 檔",
           "when": "選股日收盤選、隔天開盤買；資料截止日隔天開盤照截止日的名單調整（名單沒有的賣、補到 4 檔）；"
                   "公告沒被納入的隔天開盤賣，其餘在生效前一天收盤賣",
           "money": "4 檔等額", "freq": "每季審核"},
    "v3l": {"what": "季報 EPS 比去年同季成長得最出乎意料的 5 檔大型股（月底市值 300 億以上、20 日均成交值 5,000 萬以上）",
            "when": "季報公布期限（5/15、8/14、11/14、3/31，遇假日順延）收盤選，隔天開盤買（開盤漲停買不到就不買）；抱 60 個交易日後收盤賣",
            "money": "5 檔等額", "freq": "每季"},
    "s5": {"what": "投信連續買超、月營收成長、股價走強、市值 50～1,500 億的成長股（四項條件都要符合）",
           "when": "每月最後一個交易日收盤篩選，隔天開盤買（開盤比前一天收盤高 3% 以上不買）；收盤跌破買進價 20% 停損，"
                   "之後從買進後最高收盤回落 30% 賣（最長抱 250 個交易日）",
           "money": "每檔等額，同時常見最多 16 檔", "freq": "每月"},
    "s1": {"what": "3 家以上投信的主動 ETF 同時加碼的股票",
           "when": "每天收盤出名單，隔天開盤價低於前一天收盤才買；抱 3 個交易日收盤賣（收盤跌破停損價提前賣）",
           "money": "每天最多 5 檔、每檔等額", "freq": "每天"},
    "v7l": {"what": "上個月營收成長得最出乎意料的 5 檔大型股（月底市值 300 億以上、20 日均成交值 5,000 萬以上）",
            "when": "每月 10 日（遇假日順延）收盤換股：不在新名單的賣、隔天開盤買新的，仍在新名單的續抱",
            "money": "5 檔等額", "freq": "每月"},
    "v3m": {"what": "季報 EPS 比去年同季成長得最出乎意料的 5 檔中型股（月底市值 50～300 億、20 日均成交值 5,000 萬以上）",
            "when": "季報公布期限（5/15、8/14、11/14、3/31，遇假日順延）收盤選，隔天開盤買；抱 60 個交易日後收盤賣",
            "money": "5 檔等額", "freq": "每季"},
    "v7m": {"what": "上個月營收成長得最出乎意料的 5 檔中型股（月底市值 50～300 億、20 日均成交值 5,000 萬以上）",
            "when": "每月 10 日（遇假日順延）收盤換股：不在新名單的賣、隔天開盤買新的，仍在新名單的續抱",
            "money": "5 檔等額", "freq": "每月"},
    "qm": {"what": "強勢、賺錢的中大型美股：漲勢勝過 80% 的美股、離 52 週高點 25% 以內、單季營益率 10% 以上、近四季 ROE 15% 以上、市值 20 億美元以上",
           "when": "每週五收盤出名單，下週一開盤照名單順序補空位；收盤跌破 50 日線，下一個交易日開盤賣",
           "money": "最多 8 檔、每檔 12.5%，空的位子放現金", "freq": "每週"},
}
NAMES = {"boom": "新飆股", "qm": "美股強勢品質股"}


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


_md, _mdw, _tp = CFP._md, CFP._mdw, CFP._tp


def _pc(x, d: int = 1) -> str:
    return CPG._pc(x, d)


def _pp(x, d: int = 1) -> str:
    """百分比數字（已經是 %）→ ±x.x%。"""
    return "—" if x is None else CPG._pc(x / 100.0, d)


def _w(x) -> str:
    """占這條策略的錢：很小但不是 0 寫「不到 1%」。"""
    if x is None:
        return ""
    return "不到 1%" if 0 < x < 0.005 else f"{x * 100:.0f}%"


# ── 台股 ───────────────────────────────────────────────────────────────────

def tw_keys(A: dict, P: dict | None) -> tuple[list[str], list[str]]:
    """→ (主要, 其他)：新飆股（有那本帳）＋判定好的個股策略照推薦順序；判定普通的另列。高股息換股只當避開清單，不列。"""
    book = [b for b in A.get("book") or [] if b.get("k") != "hd"]
    book.sort(key=lambda b: (b.get("rank") is None, b.get("rank") or 0))
    main = (["boom"] if P else []) + [b["k"] for b in book if b.get("tier") == MAIN_TIER]
    other = [b["k"] for b in book if b.get("tier") == OTHER_TIER]
    return main, other


def _next_buys(evs: list[dict], k: str, n: int = 3) -> str:
    """下幾次進場：「10/30 名單・11/2（一）開盤買」。"""
    out = []
    for e in evs:
        if e["k"] != k or e["act"] not in ("買進",):
            continue
        fix = next((x["d"] for x in evs if x["k"] == k and x["act"] in ("名單", "換股") and x["d"] < e["d"]
                    and not any(y["k"] == k and y["act"] == "買進" and x["d"] < y["d"] < e["d"] for y in evs)), None)
        t = (f"{_md(fix)} 收盤名單・" if fix else "") + f"{_mdw(e['d'])}{e['at']}買" + (f" {len(e['items'])} 檔" if e["items"] else "")
        out.append(t)
        if len(out) >= n:
            break
    return "｜".join(_e(x) for x in out)


def _row(c: str, n: str, line2: str, r: float | None = None, tag: str = "", w: str = "", why: str = "", us: bool = False,
         G: dict | None = None) -> str:
    """一檔（整列可以點：台股開個股卡、美股開美股個股卡）。r＝漲跌（小數）。"""
    att = CFP._ua(c, G) if us and G is not None else CFP._ck(c)
    rr = "" if r is None else f'<span class="r {"up" if r >= 0 else "dn"}">{_pc(r)}</span>'
    return (f'<a class="cfrow{" todo" if tag else ""}" {att}><span class="cfra"><b>{_e(n)}</b>'
            + ("" if us else f'<span class="cd">{_e(c)}</span>')
            + (f'<span class="cftag">{_e(tag)}</span>' if tag else "") + '<span class="go">›</span>'
            + (f'<span class="w">{_e(w)}</span>' if w else "") + f'{rr}</span><span class="cfrb">{line2}</span>'
            + (f'<span class="cfrc">為什麼：{_e(why)}</span>' if why else "") + "</a>")


def _held_line(ent, epx, px, bt: bool, rl, sell: str) -> str:
    b = f'{_md(ent)} 買' + ("（回測）" if bt else "")
    if epx is not None and px is not None:
        b += f' {_e(_tp(epx))}，現在 {_e(_tp(px))}'
    if bt and rl is not None:
        b += f'・上線以來 {_pc(rl)}'
    return b + (f'・{_e(sell)}' if sell else "")


def adv_rows(A: dict, k: str) -> tuple[list[str], list[str]]:
    """advice 這條策略持有中、待買進的每一檔 → (持有中 HTML 列, 待買進 HTML 列)。"""
    held, todo = [], []
    for p in A.get("picks") or []:
        if p.get("k") != k:
            continue
        why = "；".join(p.get("why") or [])
        if p.get("act") == "持有中":
            r = None if p.get("now_r") is None else p["now_r"] / 100.0
            sell = (f'{_md(p["out"])} 收盤' + ("換股" if (k or "").startswith("v7") else "賣")) if p.get("out") else \
                (f'停損 {_tp(p["stop"])}' if p.get("stop") is not None else "")
            held.append(_row(p["c"], p.get("n") or p["c"], _held_line(p.get("ent"), p.get("entry"), p.get("now"),
                                                                      bool(p.get("bt")), p.get("rl"), sell), r, why=why))
        else:
            line = f'{_mdw(p.get("ent"))}開盤買' if p.get("ent") else "待買進"
            if p.get("px") is not None:
                line += f'・參考價 {_tp(p["px"])}'
            if p.get("stop") is not None:
                line += f'・停損 {_tp(p["stop"])}'
            if p.get("tent"):
                line += f'・名單 {_md(p.get("fix"))} 收盤定案'
            todo.append(_row(p["c"], p.get("n") or p["c"], _e(line), tag="待買進", why=why))
    return held, todo


def boom_rows(P: dict) -> tuple[list[str], list[str]]:
    hn = P.get("hold_n") or 60
    held, todo = [], []
    for h in P.get("hold") or []:
        sell = f'{_md(h.get("out"))} 開盤賣' + (f"（已滿 {hn} 個交易日）" if h.get("sell") else f'（{_md(h.get("due"))} 收盤滿 {hn} 個交易日）')
        held.append(_row(h["c"], h.get("n") or h["c"], _held_line(h.get("ent"), h.get("epx"), h.get("px"), bool(h.get("bt")), h.get("rl"), sell),
                         h.get("r"), w=_w(h.get("w")), why="；".join(h.get("why") or [])))
    for x in P.get("buy") or []:
        if not x.get("fill"):
            continue
        why = ([f'強度 {x["rs"]:.0f}（漲勢勝過 {x["rs"]:.0f}% 的股票）'] if x.get("rs") is not None else []) + (x.get("why") or [])
        todo.append(_row(x["c"], x.get("n") or x["c"], _e(f'{_mdw(P.get("next"))}開盤買（{_md(P.get("wk"))} 的名單）'),
                         tag="待買進", w="約 12.5%", why="；".join(why)))
    return held, todo


def _past_adv(b: dict) -> str:
    e, al, u = b.get("exp") or {}, b.get("all") or {}, b.get("unit") or "次"
    if not e.get("n"):
        return "還沒有已經賣掉的交易。"
    one = "檔" if u == "檔" else "次"
    t = (f'{_e(e.get("d0"))}～{_e(e.get("d1"))} 照做 {e["n"]} {u}：每{u}平均 <b>{_pp(e.get("avg"))}</b>、中位 {_pp(e.get("med"))}，'
         f'{e.get("win")}% 賺錢，最差一{one} {_pp(e.get("lo"))}（同一段大盤每{u} {_pp(e.get("mk"))}）。')
    if al.get("cagr") is not None:
        t += (f'全部資金照做一年 <b>{_pp(al["cagr"])}</b>、最慘時跌 {_pp(-abs(al.get("mdd") or 0), 0).lstrip("−")}'
              f'（大盤一年 {_pp(al.get("tr_cagr"))}、最慘時跌 {_pp(-abs(al.get("tr_mdd") or 0), 0).lstrip("−")}）。')
    return t


def _notes_adv(k: str, b: dict) -> list[str]:
    e = b.get("exp") or {}
    out = []
    n = e.get("n") or 0
    if k == "s3":
        out.append(f"過去只有 {n} 次審核可以照做；資料截止日以前名單還會變。")
    elif k == "s5":
        out.append(f"跌 20% 才停損，盤整的時候常被洗出場（{e.get('win', '—')}% 賺錢，靠少數大漲的股票）。")
    elif k == "s1":
        out.append("只抱 3 天，手續費和價差吃掉不少。")
    elif n and n < 30:
        out.append(f"過去只照做 {n} {b.get('unit') or '次'}。")
    if e.get("lo") is not None:
        out.append(f"最差一{'檔' if (b.get('unit') or '次') == '檔' else '次'} {_pp(e['lo'])}。")
    return out


def _card(k: str, name: str, col: int | None, held: list[str], todo: list[str], evs: list[dict], past: str, notes: list[str],
          extra: str = "", link: str = "", empty: str = "") -> str:
    m = META.get(k) or {}
    sty = f' style="--pkc:var(--cfc{col})"' if col else ""
    nx = _next_buys(evs, k)
    dl = (f'<dl class="pkdl"><dt>選什麼</dt><dd>{_e(m.get("what"))}</dd>'
          f'<dt>什麼時候</dt><dd>{_e(m.get("when"))}' + (f'<span class="pknx">下幾次進場：{nx}</span>' if nx else "") + '</dd>'
          f'<dt>怎麼分錢</dt><dd>{_e(m.get("money"))}</dd><dt>過去照做</dt><dd>{past}</dd>'
          + (f'<dt>風險</dt><dd>{"<br>".join(_e(x) for x in notes)}</dd>' if notes else "") + '</dl>')
    body = ""
    if held:
        hint = "右邊兩個數字＝占這條策略的錢、買進後漲跌；" if any('class="w"' in x for x in held) else ""
        body += (f'<h3 class="cfh3">現在拿著 {len(held)} 檔<span class="sub">{hint}點股票看走勢、籌碼、財報</span></h3>'
                 f'<div class="cfgr pkgr">{"".join(held)}</div>')
    if todo:
        body += f'<h3 class="cfh3">待買進 {len(todo)} 檔</h3><div class="cfgr pkgr">{"".join(todo)}</div>'
    if not held and not todo:
        body += f'<div class="pkempty">{_e(empty or "現在沒有部位，也沒有已經出來的名單。")}</div>'
    return (f'<section class="sec pkcard{" pkc" if col else " pkcx"}" id="pk-{_e(k)}" data-nav="{_e(PC.SHORT.get(k, name))}"{sty}>'
            f'<h2 class="pkh"><i class="pkdot"></i>{_e(name)}<span class="sub">{_e(m.get("freq") or "")}</span></h2>'
            f'{dl}{body}{extra}' + (f'<div class="pklk">{link}</div>' if link else "") + '</section>')


def boom_card(P: dict, evs: list[dict], bundle: dict, pos: dict | None, col: int) -> str:
    """新飆股：那本帳現在的持股與要買的、最新一週的名單（＋位置圖）、原本的飆股名單（收起，打開才畫）。"""
    held, todo = boom_rows(P)
    R = (bundle or {}).get("R") or {}
    bm = ((((R.get("mk") or {}).get("tw") or {}).get("sc") or {}).get("plan") or {}).get("boom") or {}
    if bm.get("cagr") is not None:
        h = bm.get("hold") or {}
        past = (f'{CPG.yr0(bm["a"])} 年起照做一年 <b>{_pc(bm["cagr"])}</b>、最慘時跌 {bm["mdd"] * 100:.0f}%'
                + (f'（同一段大盤一年 {_pc(h.get("cagr"))}、最慘時跌 {(h.get("mdd") or 0) * 100:.0f}%）' if h.get("cagr") is not None else "")
                + "。每一年只用之前幾年的資料找條件，沒有用到之後的資料。")
    else:
        past = "還沒有回測的數字。"
    tk = P.get("take")
    notes = ["回測從 2019 年起，大多是上漲的年份；最慘時跌得比大盤深很多。"]
    if tk:
        notes.append(f"{_md(tk)} 收盤照回測那本帳的持股接手，之後每週照規則記錄；標「回測」的是接手前照規則買的。")
    lst = ""
    if P.get("wk") and P.get("list"):
        have = {x["c"] for x in P.get("hold") or []}
        buy = {x["c"]: x for x in P.get("buy") or []}
        rows = []
        for x in P["list"]:
            tag = "已經有" if x["c"] in have else ((f'{_md(P.get("next"))} 開盤買' if buy[x["c"]].get("fill") else "現金不夠")
                                                if x["c"] in buy else "")
            wy = "；".join(x.get("why") or [])
            rows.append(f'<tr><td><a {CFP._ck(x["c"])}>{_e(x.get("n") or x["c"])}</a> <span class="cd">{_e(x["c"])}</span>'
                        + (f'<div class="cfin">{_e(wy)}</div>' if wy else "") + f'</td><td class="w">{x["rs"]:.0f}</td><td class="st">{_e(tag)}</td></tr>')
        lst = (f'<details class="cfdet pkdet"><summary>{_e(_mdw(P["wk"]))}收盤的名單（{P.get("n_list", 0)} 檔）・位置圖</summary>'
               + CFP.boom_spot(P, pos)
               + '<table class="cfht cfql"><tr><th>標的</th><th title="漲幅勝過多少比例的股票（1～99）">強度</th><th>現況</th></tr>'
               + "".join(rows) + "</table></details>")
    if P.get("trial"):
        tr = P["trial"]
        lst += (f'<div class="cfsxl pktr">這一週到 {_e(_md(P.get("d")))} 收盤為止符合的（{len(tr)} 檔，{_e(_mdw(P.get("next_wk")))}收盤才定案）：'
                + "、".join(f'<a {CFP._ck(x["c"])}>{_e(x.get("n") or x["c"])}</a>' for x in tr[:12]) + (f" 等 {len(tr)} 檔" if len(tr) > 12 else "") + "</div>")
    lst += ('<details class="cfdet cfsxo"><summary>另一份飆股名單（到買點、快到買點；只看，不照規則買）</summary>'
            '<div class="cfsxob"></div></details>')
    nw = P.get("next_wk")
    empty = f'下一份名單 {_mdw(nw)}收盤出來。' if nw else "還沒有名單。"
    return _card("boom", NAMES["boom"], col, held, todo, evs, past, notes, extra=lst,
                 link='<a data-go="plan" data-pm="tw" data-at="cf-tw-y">今年每一筆（研究紀錄）</a>', empty=empty)


def adv_card(k: str, b: dict, A: dict, evs: list[dict], col: int | None) -> str:
    held, todo = adv_rows(A, k)
    nxt = next((e for e in evs if e["k"] == k and e["act"] in ("買進", "調整", "賣出", "換股")), None)
    empty = "這一期沒有部位" + (f'；下一件：{_mdw(nxt["d"])}{nxt["at"]}{nxt["act"]}' if nxt else "") + "。"
    return _card(k, b.get("name") or k, col, held, todo, evs, _past_adv(b), _notes_adv(k, b),
                 link=f'<a data-go="st" data-at="st-{_e(k)}">規則、逐年報酬與每一筆（研究紀錄）</a>', empty=empty)


def other_line(k: str, b: dict, evs: list[dict], A: dict) -> str:
    held, todo = adv_rows(A, k)
    nx = _next_buys(evs, k, 1)
    e = b.get("exp") or {}
    bits = [f"拿著 {len(held)} 檔" if held else "沒有部位"]
    if todo:
        bits.append(f"待買進 {len(todo)} 檔")
    if nx:
        bits.append(f"下次 {nx}")
    perf = f'每{b.get("unit") or "次"}平均 {_pp(e.get("avg"))}、{e.get("win")}% 賺錢' if e.get("n") else ""
    return (f'<li><a data-to="pk-{_e(k)}"><b>{_e(b.get("name") or k)}</b></a><span>{_e((META.get(k) or {}).get("freq") or "")}</span>'
            f'<em>{"・".join(bits)}</em>' + (f'<i>{_e(perf)}</i>' if perf else "") + '</li>')


def s3_plan(data: dict) -> dict | None:
    for s in ((data.get("strat") or {}).get("list") or []):
        if s.get("key") == "s3":
            return s.get("plan")
    return None


def boom_pos(P: dict | None) -> dict:
    """個股卡最上面「策略」段、個股表「策略選到的」要的新飆股持股與待買進：{代號: [{k, n, h, t, y}]}。"""
    out: dict = {}
    if not P:
        return out
    hn = P.get("hold_n") or 60
    for h in P.get("hold") or []:
        t = (f'{_md(h.get("ent"))} 買' + ("（回測）" if h.get("bt") else "")
             + (f' {_tp(h["epx"])}，現在 {_tp(h["px"])}' if h.get("epx") is not None and h.get("px") is not None else "")
             + f'；{_md(h.get("out"))} 開盤賣（抱滿 {hn} 個交易日）')
        out.setdefault(h["c"], []).append({"k": "boom", "n": h.get("n") or h["c"], "h": 1, "t": t, "y": "；".join(h.get("why") or [])})
    for x in P.get("buy") or []:
        if x.get("fill"):
            out.setdefault(x["c"], []).append({"k": "boom", "n": x.get("n") or x["c"], "h": 0,
                                               "t": f'{_md(P.get("next"))} 開盤買（{_md(P.get("wk"))} 的名單）', "y": "；".join(x.get("why") or [])})
    return out


def tw_view(data: dict, bundle: dict, today: str | None = None) -> dict:
    A = data.get("adv") or {}
    P = data.get("n8")                                    # sxlivespec VER 4：選股頁看 8 格那一本（交易計畫照舊看 R60）
    main, other = tw_keys(A, P)
    book = {b["k"]: b for b in A.get("book") or []}
    cal = PC.tw_events(A, P, s3_plan(data), main + other, today)
    evs = cal["ev"]
    col = {k: i + 1 for i, k in enumerate(main[:8])}
    cards = []
    for k in main:
        if k == "boom":
            cards.append(boom_card(P, evs, bundle, data.get("sx_pos"), col[k]))
        elif k in book:
            cards.append(adv_card(k, book[k], A, evs, col[k]))
    others = [adv_card(k, book[k], A, evs, None) for k in other if k in book]
    olist = "".join(other_line(k, book[k], evs, A) for k in other if k in book)
    ks = [[k, PC.SHORT.get(k, k), col.get(k, 0), 1] for k in main] + [[k, PC.SHORT.get(k, k), 0, 0] for k in other]
    return {"d": cal["d"], "end": cal["end"], "ev": _pack(evs), "ks": ks, "hol": holidays("tw", cal["d"], cal["end"]),
            "cards": "".join(cards), "others": "".join(others), "olist": olist, "pos": boom_pos(P),
            "names": {k: (NAMES.get(k) or (book.get(k) or {}).get("name") or k) for k in main + other}}


# ── 美股 ───────────────────────────────────────────────────────────────────

def us_card(G: dict, evs: list[dict], qm: dict | None) -> str:
    nms = G.get("nms") or {}
    held, todo = [], []
    for r in G.get("rows") or []:
        if r.get("sell"):
            sell = f'{_mdw(r["sell"])}開盤賣（{_md(r.get("trig"))} 收盤跌破 50 日線）'
        elif r.get("pct") is not None:
            sell = f'收盤比 50 日線{"高" if r["pct"] >= 0 else "低"} {abs(r["pct"]) * 100:.1f}%'
        else:
            sell = ""
        if r.get("new"):
            line = f'{_mdw(r["ent"])}開盤買進；買進價和漲跌等這週六的紀錄'
        else:
            line = f'{_md(r.get("ent"))} 買' + ("（回測）" if r.get("bt") else "")
            if r.get("bt") and r.get("rl") is not None:
                line += f'・上線以來 {_pc(r["rl"])}'
            line = _e(line)
        if sell:
            line += f'・{_e(sell)}'
        rk = f'這週名單第 {r["rk"]} 名' if r.get("rk") else ""
        held.append(_row(r["c"], CFP._uname(r["c"], nms), line, r.get("r"), w=_w(r.get("w")), why=rk, us=True, G=G))
    for x in G.get("todo") or []:
        if (x.get("w") or 0) <= 1e-3:
            continue
        todo.append(_row(x["c"], CFP._uname(x["c"], nms), _e(f'{_mdw(x["d"])}開盤買'), tag="待買進", w=f'約 {_w(x["w"])}',
                         why=f'這週名單第 {x["rk"]} 名' if x.get("rk") else "", us=True, G=G))
    for x in G.get("gone") or []:
        held.append(_row(x["c"], CFP._uname(x["c"], nms), _e(f'{_mdw(x["on"])}開盤賣掉了（{_md(x.get("trig"))} 收盤跌破 50 日線）'),
                         tag="已賣", us=True, G=G))
    R = (qm or {}).get("R") or {}
    sl = ((R.get("sleeve") or {}).get("main")) or {}
    bm = ((R.get("bench") or {}).get("spx_tr")) or {}
    if sl.get("cagr") is not None:
        past = (f'{CPG.yr0(sl.get("a"))} 年起照做一年 <b>{_pc(sl["cagr"])}</b>、最慘時跌 {sl["mdd"] * 100:.0f}%，100 萬變 {sl["m"] * 100:,.0f} 萬'
                + (f'（S&amp;P 500 含息一年 {_pc(bm.get("cagr"))}、最慘時跌 {(bm.get("mdd") or 0) * 100:.0f}%，100 萬變 {(bm.get("m") or 0) * 100:,.0f} 萬）'
                   if bm.get("cagr") is not None else "") + "。")
    else:
        past = "還沒有回測的數字。"
    notes = ["這套規則是看過 2014 年以來的結果才挑的；2026/10/23 起每週照規則記錄。"]
    d8 = ((R.get("desc") or {}).get("drop") or {}).get("8") or {}
    if d8.get("cagr") is not None:
        notes.append(f"賺的集中在少數大漲的股票：拿掉賺最多的 8 檔，一年剩 {_pc(d8['cagr'])}。")
    extra = CFP._qm_cands(G)
    if extra:
        extra = f'<details class="cfdet pkdet"><summary>有空位時依序買：名單前幾名</summary>{extra}</details>'
    nf = G.get("nf")
    empty = f'下一份名單 {_mdw(nf)}收盤出來。' if nf else "還沒有每週紀錄。"
    return _card("qm", NAMES["qm"], 1, held, todo, evs, past, notes, extra=extra, empty=empty)


def us_view(data: dict, bundle: dict, today: str | None = None) -> dict:
    G = CFP.us_state(bundle or {})
    qm = (bundle or {}).get("qm") or {}
    if not G.get("on") or not G.get("n"):
        return {"err": G.get("why") or "美股強勢品質股的每週紀錄還沒產生", "ks": [], "ev": []}
    cal = PC.us_events(G, qm.get("C"), today)
    uc = None
    try:
        from . import uscardpage as UCP
        uc = UCP.build(G, qm.get("C") or {}, cash=False, fin=qm.get("F"))
    except Exception as e:                                # noqa: BLE001 —— 卡片算不出來：股票照舊連 Yahoo Finance
        print(f"[選股] 美股個股卡算不出來：{type(e).__name__}: {e}")
    G["uc"] = set((uc or {}).get("s") or ())
    return {"d": cal["d"], "end": cal["end"], "ev": _pack(cal["ev"]), "ks": [["qm", PC.SHORT["qm"], 1, 1], ["ern", PC.SHORT["ern"], 0, 1]],
            "hol": holidays("spx", cal["d"], cal["end"]), "cards": us_card(G, cal["ev"], qm), "uc": uc,
            "names": {"qm": NAMES["qm"], "ern": "持股的財報日"}}


# ── 共用 ───────────────────────────────────────────────────────────────────

def _pack(evs: list[dict]) -> list:
    """事件 → 頁面的緊湊陣列：[日期, 開盤/收盤, 策略, 動作, [[代號, 名稱]], 說明, 推算(1/0)]。"""
    return [[e["d"], e["at"], e["k"], e["act"], [[i["c"], i["n"]] for i in e["items"]], e.get("note") or "", 1 if e.get("proj") else 0]
            for e in evs]


def holidays(mk: str, a: str | None, b: str | None) -> list[str]:
    """月曆範圍內休市的平日（a 那個月的 1 日到 b）。"""
    if not a or not b:
        return []
    from datetime import date, timedelta
    x, end, out = date.fromisoformat(a[:8] + "01"), date.fromisoformat(b), []
    while x <= end:
        if x.weekday() < 5 and PC._closed(mk, x):
            out.append(x.isoformat())
        x += timedelta(days=1)
    return out


def build(data: dict, bundle: dict | None, today: str | None = None) -> dict:
    """→ D.pick：{"tw": {...}, "us": {...}}；每個市場各自 try，算不出來只寫那一頁「還沒算出來」。"""
    from ..clock import today_tw
    today = today or today_tw().isoformat()
    out: dict = {}
    for mk, fn in (("tw", tw_view), ("us", us_view)):
        try:
            out[mk] = fn(data, bundle or {}, today)
        except Exception as e:                            # noqa: BLE001
            print(f"[選股] {mk} 算不出來：{type(e).__name__}: {e}")
            out[mk] = {"err": f"{type(e).__name__}: {e}", "ks": [], "ev": []}
    return out


CSS = r"""
/* 選股頁（pickpage.py；docs/lab_pick_page_plan.md）：策略身分色＝--cfc1～8（page.py 的 :root，深色另一組） */
.pkcalw{border:1px solid var(--line);border-radius:14px;padding:12px 14px 14px;margin:0 0 14px}
.pkct{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:0 0 10px}
.pkks{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.pkk{display:inline-flex;align-items:center;gap:6px;font:inherit;font-size:13px;padding:3px 10px;border-radius:999px;border:1px solid var(--line2);background:var(--bg);color:var(--ink2);cursor:pointer;white-space:nowrap;flex:none;line-height:1.5}
.pkk i{flex:none;width:9px;height:9px;border-radius:50%;background:var(--c,var(--mut2))}
.pkk.off{opacity:.45}.pkk.off i{background:none;box-shadow:inset 0 0 0 1.5px var(--c,var(--mut2))}
.pkk.pkmo{border-style:dashed}
.pkmn{display:flex;align-items:center;gap:6px;margin-left:auto}
.pkmn button{font:inherit;font-size:16px;width:30px;height:30px;border-radius:8px;border:1px solid var(--line2);background:var(--bg);color:var(--ink);cursor:pointer}
.pkmn button:disabled{opacity:.35;cursor:default}.pkmn b{font-size:15px;min-width:7.5em;text-align:center}
.pkms{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
@media (max-width:899px){.pkms{grid-template-columns:minmax(0,1fr)}.pkms>.pkm+.pkm{display:none}}
.pkm h4{font-size:14px;margin:0 0 4px;color:var(--ink2)}
.pkg{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:3px}
.pkg .pkw{font-size:12px;color:var(--mut);text-align:center;padding:2px 0}
.pkd{min-height:74px;border-radius:8px;background:var(--card2);padding:3px 4px;font-size:12px;cursor:pointer;border:1.5px solid transparent;min-width:0;overflow:hidden}
.pkd.blank{background:none;cursor:default}.pkd.past{opacity:.45;cursor:default}
.pkd.hol{background:repeating-linear-gradient(135deg,var(--line) 0 2px,transparent 2px 7px);cursor:default}
.pkd.today{border-color:var(--ink2)}.pkd.sel{border-color:var(--acc);background:var(--hlcol)}
.pkd .pkn{font-weight:700;font-size:12.5px;color:var(--ink2);display:flex;justify-content:space-between;gap:2px}
.pkd .pkn span{font-weight:400;font-size:11px;color:var(--mut)}
.pke{display:flex;align-items:center;gap:3px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.pke b{flex:none;color:var(--c,var(--mut));font-size:11px;width:11px;text-align:center}
.pke span{overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.pke.proj span{color:var(--ink2)}.pke.ern span{color:var(--mut)}
.pke.pkplus{color:var(--mut);font-size:11px;padding-left:14px}
@media (max-width:520px){.pkd{min-height:56px;padding:2px 3px}.pke span{display:none}.pke{display:inline-flex;margin-right:1px}.pke.pkplus{padding-left:0;display:inline-flex}
 .pkd .pkev{display:flex;flex-wrap:wrap;gap:0 1px}.pke b{font-size:12px;width:12px}}
.pkday{margin:12px 0 0;border-top:1px solid var(--line);padding-top:10px}
.pkday h4{font-size:14.5px;margin:0 0 6px}
.pkdl2{list-style:none;margin:0;padding:0}
.pkdl2 li{display:grid;grid-template-columns:3.2em 1.2em minmax(0,1fr);gap:2px 6px;align-items:baseline;font-size:13.5px;padding:4px 0;border-top:1px solid var(--line)}
.pkdl2 li:first-child{border-top:0}
.pkdl2 .at{color:var(--mut);font-size:12.5px}.pkdl2 .sy{color:var(--c,var(--mut));font-weight:700;text-align:center}
.pkdl2 .tx b{font-weight:700;margin-right:4px}.pkdl2 .tx a{color:var(--acc);cursor:pointer}.pkdl2 .tx .nt{color:var(--mut);font-size:12.5px}
.pkag{margin:14px 0 0}.pkag h4{font-size:14.5px;margin:0 0 4px}
.pkagd{margin:8px 0 0}.pkagd>b{font-size:13.5px}.pkagd>b span{font-weight:400;color:var(--mut);font-size:12.5px;margin-left:4px}
.pklg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--mut);margin:8px 0 0}
.pklg b{color:var(--ink2);margin-right:3px}
.pkcard{border:1px solid var(--line);border-left:4px solid var(--pkc,var(--line2));border-radius:14px;padding:12px 14px 14px;margin:0 0 14px}
.pkh{font-size:18px;margin:2px 0 8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.pkh .pkdot{width:11px;height:11px;border-radius:50%;background:var(--pkc,var(--mut2))}
.pkh .sub{font-size:12.5px;font-weight:400;color:var(--mut)}
.pkdl{display:grid;grid-template-columns:5.2em minmax(0,1fr);gap:6px 12px;margin:0 0 6px;font-size:13.5px;line-height:1.65;max-width:880px}
.pkdl dt{color:var(--mut);font-size:12.5px;padding-top:2px}.pkdl dd{margin:0;color:var(--ink2)}.pkdl dd b{color:var(--ink)}
.pknx{display:block;color:var(--ink);font-size:13px;margin-top:2px}
.pkgr{max-width:880px}.pkempty{font-size:13.5px;color:var(--ink2);background:var(--card2);border-radius:10px;padding:8px 12px;margin:8px 0;max-width:880px}
.pkdet{margin:10px 0 0}.pkdet>summary,.pkox>summary,.pkcard .cfsxo>summary{width:auto}.pkagm{margin:10px 0 0}.pktr{margin:8px 0 0;max-width:880px}
.pklk{margin:10px 0 0;font-size:13px}.pklk a{color:var(--acc);cursor:pointer}
.pkol{list-style:none;margin:0 0 10px;padding:0;max-width:880px}
.pkol li{display:grid;grid-template-columns:minmax(0,11em) 4.5em minmax(0,1fr);gap:2px 10px;font-size:13.5px;padding:7px 0;border-top:1px solid var(--line)}
.pkol li a{color:var(--ink);cursor:pointer}.pkol li span{color:var(--mut);font-size:12.5px}.pkol li em{font-style:normal;color:var(--ink2)}
.pkol li i{grid-column:3;font-style:normal;color:var(--mut);font-size:12.5px}
.pkox>summary{cursor:pointer;font-size:15px;font-weight:700;margin:6px 0 8px}
.pkox .pkcard{margin-top:10px}
@media (max-width:640px){.pkdl{grid-template-columns:minmax(0,1fr);gap:0}.pkdl dt{padding-top:6px}
 .pkol li{grid-template-columns:minmax(0,1fr) auto}.pkol li em,.pkol li i{grid-column:1/-1}}
"""

JS = r"""
/* ---------- 選股（pickpage.py；docs/lab_pick_page_plan.md）：台股｜美股＝進場行事曆＋每條策略一張卡；個股＝工具。
   行事曆：事件 [日期, 開盤/收盤, 策略, 動作, [[代號, 名稱]], 說明, 推算] 在這裡畫成月曆（只排週一到週五）、點一天看那天、接下來 4 週清單。 ---------- */
const PICK=D.pick||{};
const PKSY={'名單':'◇','買進':'▲','賣出':'▼','換股':'◆','調整':'●','財報':'○'};
const PKST={};
function pkWd(d){return '日一二三四五六'[new Date(d+'T00:00:00Z').getUTCDay()];}
function pkMd(d){return `${+d.slice(5,7)}/${+d.slice(8,10)}`;}
function pkMdw(d){return `${pkMd(d)}（${pkWd(d)}）`;}
/* 一次只看一個月（手機）而這個月剩不到 5 個交易日：從下個月開始（剩下的幾天在「接下來」清單） */
function pkLeft(P){const d=P.d||'',hol=new Set(P.hol||[]);if(!d)return 0;let n=0,t=Date.UTC(+d.slice(0,4),+d.slice(5,7)-1,+d.slice(8,10));
  for(;;){t+=864e5;const x=new Date(t),ds=x.toISOString().slice(0,10);if(ds.slice(0,7)!==d.slice(0,7))break;const w=x.getUTCDay();if(w&&w<6&&!hol.has(ds))n++;}return n;}
function pkState(mk){const P=PICK[mk]||{};if(!PKST[mk]){const on=new Set((P.ks||[]).filter(x=>x[3]).map(x=>x[0]));
  const d=P.d||'',ms=pkMonths(mk);let m0=d.slice(0,7);if(!matchMedia('(min-width:900px)').matches&&pkLeft(P)<5&&ms[1])m0=ms[1];
  PKST[mk]={on,more:false,m:m0,sel:null,ag:false};}return PKST[mk];}
function pkCol(mk,k){const x=((PICK[mk]||{}).ks||[]).find(y=>y[0]===k);return x&&x[2]?`var(--cfc${x[2]})`:'var(--mut)';}
function pkShort(mk,k){const x=((PICK[mk]||{}).ks||[]).find(y=>y[0]===k);return x?x[1]:k;}
function pkEvs(mk){const P=PICK[mk]||{},S=pkState(mk);return (P.ev||[]).filter(e=>S.on.has(e[2]));}
function pkMonths(mk){const P=PICK[mk]||{};if(!P.d||!P.end)return [];const out=[];let y=+P.d.slice(0,4),m=+P.d.slice(5,7);
  const ey=+P.end.slice(0,4),em=+P.end.slice(5,7);while(y<ey||(y===ey&&m<=em)){out.push(`${y}-${String(m).padStart(2,'0')}`);m++;if(m>12){m=1;y++;}}return out;}
function pkItems(mk,its,n){const us=mk==='us';const a=(its||[]).slice(0,n||8).map(([c,nm])=>us?`<a href="#us=${encodeURIComponent(c)}" data-us="${esc(c)}">${esc(nm)}</a>`:`<a data-c="${esc(c)}" data-co="${esc(c)}">${esc(nm)}</a>`);
  return a.join('、')+((its||[]).length>(n||8)?` 等 ${its.length} 檔`:'');}
function pkLine(mk,e){const nm=(((PICK[mk]||{}).names)||{})[e[2]]||pkShort(mk,e[2]);
  const its=e[4]&&e[4].length?`：${pkItems(mk,e[4])}`:'';
  return `<li style="--c:${pkCol(mk,e[2])}"><span class=at>${esc(e[1]||'')}</span><span class=sy>${PKSY[e[3]]||'·'}</span><span class=tx><b>${esc(nm)}</b>${esc(e[3])}${its}${e[5]?` <span class=nt>${esc(e[5])}</span>`:''}</span></li>`;}
function pkMonth(mk,ym,evs){const P=PICK[mk]||{},S=pkState(mk),hol=new Set(P.hol||[]),by={};evs.forEach(e=>{(by[e[0]]=by[e[0]]||[]).push(e);});
  const y=+ym.slice(0,4),m=+ym.slice(5,7),n=new Date(Date.UTC(y,m,0)).getUTCDate();let cells='',lead=null;
  for(let d=1;d<=n;d++){const ds=`${ym}-${String(d).padStart(2,'0')}`,wd=new Date(ds+'T00:00:00Z').getUTCDay();if(wd===0||wd===6)continue;
    if(lead===null){lead=wd-1;for(let i=0;i<lead;i++)cells+='<div class="pkd blank"></div>';}
    const es=by[ds]||[],past=ds<=P.d,isH=hol.has(ds);let cls='pkd'+(past?' past':'')+(isH?' hol':'')+(ds===P.d?' today':'')+(S.sel===ds?' sel':'');
    let h=`<div class="${cls}" data-pkd="${ds}"><div class=pkn>${d}${isH?'<span>休市</span>':ds===P.d?'<span>資料日</span>':''}</div><div class=pkev>`;
    es.slice(0,3).forEach(e=>{h+=`<div class="pke${e[6]?' proj':''}${e[2]==='ern'?' ern':''}" style="--c:${pkCol(mk,e[2])}" title="${esc(pkShort(mk,e[2])+' '+e[3]+(e[4].length?' '+e[4].length+' 檔':''))}"><b>${PKSY[e[3]]||'·'}</b><span>${esc(pkShort(mk,e[2]))}${e[4].length?' '+e[4].length:''}</span></div>`;});
    if(es.length>3)h+=`<div class="pke pkplus">+${es.length-3}</div>`;
    cells+=h+'</div></div>';}
  return `<div class=pkm><h4>${y} 年 ${m} 月</h4><div class=pkg>${'一二三四五'.split('').map(w=>`<div class=pkw>${w}</div>`).join('')}${cells}</div></div>`;}
function pkDay(mk,ds,evs){const es=evs.filter(e=>e[0]===ds);
  return `<h4>${pkMdw(ds)}</h4>`+(es.length?`<ul class=pkdl2>${es.map(e=>pkLine(mk,e)).join('')}</ul>`:'<div class=st>這一天沒有排定的事。</div>');}
const PKAG=6;   /* 「接下來」先列 6 天，其餘點「再看」 */
function pkAgenda(mk,evs){const S=pkState(mk),all=[...new Set(evs.map(e=>e[0]))].sort(),days=all.slice(0,S.ag?40:PKAG);
  if(!days.length)return '<div class=st>接下來沒有排定的事。</div>';
  return days.map(d=>`<div class=pkagd><b>${pkMdw(d)}</b><ul class=pkdl2>${evs.filter(e=>e[0]===d).map(e=>pkLine(mk,e)).join('')}</ul></div>`).join('')+
    (all.length>days.length?`<button type=button class="pkk pkmo pkagm" data-pkag=1>再看 ${Math.min(40,all.length)-days.length} 天</button>`:'');}
function pkCalDraw(mk){const box=$('#pkcal-'+mk);if(!box)return;const P=PICK[mk]||{},S=pkState(mk),ms=pkMonths(mk);if(!ms.length){box.innerHTML='<div class=st>行事曆還沒算出來。</div>';return;}
  if(!ms.includes(S.m))S.m=ms[0];const i=ms.indexOf(S.m),two=matchMedia('(min-width:900px)').matches,step=two?2:1;
  const evs=pkEvs(mk),main=(P.ks||[]).filter(x=>x[3]),oth=(P.ks||[]).filter(x=>!x[3]);
  const chip=x=>`<button type=button class="pkk${S.on.has(x[0])?'':' off'}" data-pkk="${esc(x[0])}" style="--c:${x[2]?`var(--cfc${x[2]})`:'var(--mut)'}" aria-pressed="${S.on.has(x[0])}"><i></i>${esc(x[1])}</button>`;
  let h=`<div class=pkct><div class=pkks>${main.map(chip).join('')}${oth.length?(S.more?oth.map(chip).join(''):`<button type=button class="pkk pkmo" data-pkmore=1>＋其他 ${oth.length} 條</button>`):''}</div>`+
    `<div class=pkmn><button type=button data-pkm="-1" ${i<=0?'disabled':''} aria-label="上一個月">‹</button><b>${+S.m.slice(5,7)} 月${two&&ms[i+1]?`～${+ms[i+1].slice(5,7)} 月`:''}</b><button type=button data-pkm="1" ${i+step>=ms.length?'disabled':''} aria-label="下一個月">›</button></div></div>`;
  h+=`<div class=pkms>${pkMonth(mk,ms[i],evs)}${ms[i+1]?pkMonth(mk,ms[i+1],evs):''}</div>`;
  h+=`<div class=pklg>${Object.entries(PKSY).filter(([a])=>mk==='us'||a!=='財報').map(([a,s])=>`<span><b>${s}</b>${a}</span>`).join('')}<span>灰字＝照規則排的日子，名單還沒出來</span></div>`;
  if(S.sel)h+=`<div class=pkday>${pkDay(mk,S.sel,evs)}</div>`;
  box.innerHTML=h;
  const ag=$('#pkag-'+mk);if(ag){ag.innerHTML=pkAgenda(mk,evs);ag.querySelectorAll('[data-pkag]').forEach(b=>b.onclick=()=>{S.ag=true;pkCalDraw(mk);});}
  box.querySelectorAll('[data-pkk]').forEach(b=>b.onclick=()=>{const k=b.dataset.pkk;if(S.on.has(k))S.on.delete(k);else S.on.add(k);pkCalDraw(mk);});
  box.querySelectorAll('[data-pkmore]').forEach(b=>b.onclick=()=>{S.more=true;(P.ks||[]).filter(x=>!x[3]).forEach(x=>S.on.add(x[0]));pkCalDraw(mk);});
  box.querySelectorAll('[data-pkm]').forEach(b=>b.onclick=()=>{const j=Math.max(0,Math.min(ms.length-1,i+(+b.dataset.pkm)*step));S.m=ms[j];pkCalDraw(mk);});
  box.querySelectorAll('[data-pkd]').forEach(c=>{if(c.classList.contains('past')||c.classList.contains('hol')||c.classList.contains('blank'))return;
    c.onclick=()=>{S.sel=S.sel===c.dataset.pkd?null:c.dataset.pkd;pkCalDraw(mk);};});}
function vPick(mk){const P=PICK[mk]||{};let h='';
  if(P.err)h+=`<div class=st>${esc(P.err)}。</div>`;
  else{h+=`<section class="sec" id="pk-${mk}-cal" data-nav="行事曆"><h2 class=cfh>${mk==='tw'?'台股':'美股'}進場行事曆<span class=sub>${P.d?`${pkMd(P.d)} 收盤`:''}${mk==='us'?'・美國當地日期':''}</span></h2>`+
    `<div class=pkcalw><div id="pkcal-${mk}"></div><div class=pkag><h4>接下來</h4><div id="pkag-${mk}"></div></div></div></section>`;
    h+=P.cards||'';
    if(P.olist)h+=`<section class=sec id="pk-${mk}-o" data-nav="其他策略"><details class=pkox><summary>其他策略（${(P.ks||[]).filter(x=>!x[3]).length} 條，過去成績比上面普通）</summary><ul class=pkol>${P.olist}</ul>${P.others||''}</details></section>`;}
  $('#main').innerHTML=h+`<footer class=cffoot><a data-go="strat">全部策略</a>・<a data-go="plan" data-pm="${mk}">原本的配置</a>・<a href="x9r.html">研究紀錄</a></footer>`;
  pkCalDraw(mk);
  $$('#main [data-to]').forEach(a=>a.onclick=e=>{e.preventDefault();const t=document.getElementById(a.dataset.to);const d=t&&t.closest('details');if(d)d.open=true;jump(a.dataset.to);});
  const so=$('#main .cfsxo');if(so)so.addEventListener('toggle',()=>{if(!so.open)return;   /* 另一份飆股名單（只看）：打開才組、才畫 */
    if(!so.dataset.done){so.querySelector('.cfsxob').innerHTML=typeof wlCfg==='function'?wlCfg():'';so.dataset.done=1;}spotDraw();});
  $$('#main .pkdet').forEach(d=>d.addEventListener('toggle',()=>{if(d.open)cfSpot();}));}
function vPkTw(){vPick('tw');}
function vPkUs(){vPick('us');}
let PKR=0,PKW=innerWidth;addEventListener('resize',()=>{clearTimeout(PKR);PKR=setTimeout(()=>{if((S.tab==='tw'||S.tab==='us')&&(innerWidth>=900)!==(PKW>=900))pkCalDraw(S.tab);PKW=innerWidth;},200);});
"""
