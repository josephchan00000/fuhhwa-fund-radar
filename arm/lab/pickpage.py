"""選股頁（x9.html 的「選股」身分：台股｜美股｜個股；docs/lab_pick_page_plan.md）。

使用者 2026-10-28：「你的投資組合太不成熟了，幫我重新設計直接把配置那頁拿掉，然後把現有的選股策略做好妥善的規劃呈現出來單獨一頁，
我要分成台股跟美股，有不同策略建議進場的時程行事曆…本來的配置回測那些丟到研究紀錄裡面」。
- 每個市場：進場行事曆（pickcal 的事件；月曆與接下來 4 週在瀏覽器畫）→ 每條策略一張卡（Python 組好的 HTML）→ 其他策略（收起）。
- 每條策略自己一份錢：卡片寫同時幾檔、每檔多少，不寫占全部資金幾 %（投資組合層級的比例、警訊換現金在研究紀錄・交易計畫）。
- 只整理既有的資料（advice、新飆股那本帳、美股強勢品質股的每週紀錄與每天檢查），不改任何規則、不重算回測。
用字照主頁面的規則（wiki/lab/plain-words.md；tests/test_plain.py 掃畫面）。CSS class、JS 函式一律 pk 開頭。
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
    "boom": {"what": "強勢股：每年用之前幾年的資料，找出「之後 60 個交易日容易大漲」的條件，每週挑出符合的股票",
             "when": "每週最後一個交易日收盤出名單，下一個交易日開盤買：新上名單的先買，同一週上名單的依強度；"
                     "買進後第 60 個交易日收盤到期，隔天開盤賣",
             "money": "分 8 格：有空格時把手上的現金平分給空格（一格不到總資金 1/16 就不買），最多 8 檔", "freq": "每週",
             "cond": "開盤直接買，不等買點", "exit": "抱 60 個交易日"},
    "s3": {"what": "可能被納入臺灣50 的股票：審核資料截止日前 25 個交易日，依當天的市值排名，挑漲勢最強的 4 檔",
           "when": "選股日收盤選、隔天開盤買；資料截止日隔天開盤照截止日的名單調整（名單沒有的賣、補到 4 檔）；"
                   "公告沒被納入的隔天開盤賣，其餘在生效前一天收盤賣",
           "money": "4 檔等額", "freq": "每季審核", "cond": "開盤直接買", "exit": "沒被納入隔天賣，納入的生效前一天收盤賣"},
    "v3l": {"what": "季報 EPS 比去年同季成長得最出乎意料的 5 檔大型股（月底市值 300 億以上、20 日均成交值 5,000 萬以上）",
            "when": "季報公布期限（5/15、8/14、11/14、3/31，遇假日順延）收盤選，隔天開盤買（開盤漲停買不到就不買）；抱 60 個交易日後收盤賣",
            "money": "5 檔等額", "freq": "每季", "cond": "開盤漲停買不到就不買", "exit": "抱 60 個交易日"},
    "s5": {"what": "投信連續買超、月營收成長、股價走強、市值 50～1,500 億的成長股（四項條件都要符合）",
           "when": "每月最後一個交易日收盤篩選，隔天開盤買（開盤比前一天收盤高 3% 以上不買）；收盤跌破買進價 20% 停損，"
                   "之後從買進後最高收盤回落 30% 賣（最長抱 250 個交易日）",
           "money": "每檔等額，同時常見最多 16 檔", "freq": "每月", "cond": "開盤比前一天收盤高 3% 以上不買",
           "exit": "跌破買進價 20% 停損，從最高回落 30% 賣"},
    "s1": {"what": "3 家以上投信的主動 ETF 同時加碼的股票",
           "when": "每天收盤出名單，隔天開盤價低於前一天收盤才買；抱 3 個交易日收盤賣（收盤跌破停損價提前賣）",
           "money": "每天最多 5 檔、每檔等額", "freq": "每天", "cond": "開盤低於前一天收盤才買", "exit": "抱 3 個交易日，跌破停損價提前賣"},
    "v7l": {"what": "上個月營收成長得最出乎意料的 5 檔大型股（月底市值 300 億以上、20 日均成交值 5,000 萬以上）",
            "when": "每月 10 日（遇假日順延）收盤換股：不在新名單的賣、隔天開盤買新的，仍在新名單的續抱",
            "money": "5 檔等額", "freq": "每月", "cond": "開盤直接買", "exit": "下個月 10 日不在名單上就賣"},
    "v3m": {"what": "季報 EPS 比去年同季成長得最出乎意料的 5 檔中型股（月底市值 50～300 億、20 日均成交值 5,000 萬以上）",
            "when": "季報公布期限（5/15、8/14、11/14、3/31，遇假日順延）收盤選，隔天開盤買；抱 60 個交易日後收盤賣",
            "money": "5 檔等額", "freq": "每季", "cond": "開盤直接買", "exit": "抱 60 個交易日"},
    "v7m": {"what": "上個月營收成長得最出乎意料的 5 檔中型股（月底市值 50～300 億、20 日均成交值 5,000 萬以上）",
            "when": "每月 10 日（遇假日順延）收盤換股：不在新名單的賣、隔天開盤買新的，仍在新名單的續抱",
            "money": "5 檔等額", "freq": "每月", "cond": "開盤直接買", "exit": "下個月 10 日不在名單上就賣"},
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
          extra: str = "", link: str = "", empty: str | None = "", lead: str = "") -> str:
    """lead＝放在規則說明之前（新飆股：這週要做的事、我的、名單）；empty＝None 不寫「沒有部位」。"""
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
    if not held and not todo and empty is not None:
        body += f'<div class="pkempty">{_e(empty or "現在沒有部位，也沒有已經出來的名單。")}</div>'
    if lead:
        dl = f'<details class="cfdet pkdet pkrule"><summary>規則、過去照做、風險</summary>{dl}</details>'
    return (f'<section class="sec pkcard{" pkc" if col else " pkcx"}" id="pk-{_e(k)}" data-nav="{_e(PC.SHORT.get(k, name))}"{sty}>'
            f'<h2 class="pkh"><i class="pkdot"></i>{_e(name)}<span class="sub">{_e(m.get("freq") or "")}</span></h2>'
            f'{lead}{dl}{body}{extra}' + (f'<div class="pklk">{link}</div>' if link else "") + '</section>')


W9_FILE = "tw-superstock-lab/reports/W9_results.json"     # 書上的選股＋書上的買點（W9 主規格；新飆股不等買點的理由）
W10_FILE = "tw-superstock-lab/reports/W10_results.json"   # 新飆股買法（8 格、新上名單先）的回測（sxfixspec；docs/lab_boom_v2_plan.md 第 9 節）


def w10() -> dict:
    """W10 回測摘要：{"pick": 換成的做法, "cur": 原本的做法, "tr": 加權報酬指數}，每個 {cagr: {all,h1,h2}, mdd, yearly, cap}。讀不到＝{}。"""
    from pathlib import Path
    try:
        d = json.loads((Path(__file__).resolve().parents[2] / W10_FILE).read_text(encoding="utf-8"))
    except Exception:                                    # noqa: BLE001
        return {}
    R = d.get("runs") or {}
    if d.get("verdict") != "換" or d.get("pick") not in R:
        return {}
    out = {"pick": R[d["pick"]], "cur": R.get(d.get("current")) or {}, "tr": d.get("bench_tr") or {}, "last": d.get("last"),
           "skip": R.get(d["pick"].replace("-off-", "-on-")) or {}}      # 同一組、只差「漲太遠先不買」
    try:
        w9 = json.loads((Path(__file__).resolve().parents[2] / W9_FILE).read_text(encoding="utf-8"))
        out["book"] = (w9.get("runs") or {}).get(w9.get("main")) or {}
    except Exception:                                    # noqa: BLE001
        out["book"] = {}
    return out


def nowait_txt(W: dict) -> str:
    """新飆股為什麼不等買點（docs/lab_pick_arch_plan.md 第 2 節）：同一份名單試過的兩種等法都比較差。讀不到數字＝只寫做法。"""
    a, sk, bk = (W.get("pick") or {}).get("cagr") or {}, (W.get("skip") or {}).get("cagr") or {}, (W.get("book") or {}).get("cagr") or {}
    y22 = ((W.get("pick") or {}).get("yearly") or {}).get("2022")
    s = "這條不等買點：名單出來，下一個交易日開盤就買。"
    if a.get("all") is not None and sk.get("all") is not None and bk.get("all") is not None:
        s += (f'2019 年起試過的兩種等法都比較差：同一份名單漲太遠先不買，一年 {_pc(sk["all"])}；照書上的選股和買點，一年 {_pc(bk["all"])}；'
              f'現在的做法一年 {_pc(a["all"])}' + (f'（2022 年 {_pc(y22)}）' if y22 is not None else "") + "。")
    return s + "之後會試「到條件才買」（開低、拉回、創新高），比較好才換。"


def _tw_days(a: str, b: str) -> tuple[str, str, list[str]]:
    """台股交易日（頁面算「照規則哪天賣」用）：範圍＋範圍內休市的平日（週末不列）。"""
    from datetime import date, timedelta
    x, end, hol = date.fromisoformat(a), date.fromisoformat(b), []
    while x <= end:
        if x.weekday() < 5 and PC._closed("tw", x):
            hol.append(x.isoformat())
        x += timedelta(days=1)
    return a, b, hol


def boom_box(P: dict) -> dict | None:
    """新飆股卡片在瀏覽器畫的部分（名單篩選、自己標的觀察／已買、名單位置圖）：
    rows＝[代號, 名稱, 強度, 上名單週數, 符合哪一條, 收盤, 現況]（照規則買的順序），現況 h＝拿著、b＝照規則會買、w＝等空位。
    只放這條策略自己用的東西（docs/lab_pick_arch_plan.md）：書上的買點、離 52 週高點不放——新飆股不等買點，
    放在一起就變成「說要買、又說還沒到」。位置圖用上名單週數與強度畫（就是先買誰的順序）。"""
    K = (P or {}).get("pick") or {}
    if not K.get("rows"):
        return None
    held = {h["c"] for h in P.get("hold") or []}
    sell = {h["c"] for h in P.get("hold") or [] if h.get("sell")}
    slots = P.get("slots") or 8
    rec = not K.get("trial") and P.get("wk") == K.get("d") and P.get("buy")   # 正式名單、那本帳已經照它排好要買的
    fill = {x["c"] for x in P.get("buy") or [] if x.get("fill")}
    free = slots - (len(held) - len(sell))
    rows, k = [], 0
    for r in K["rows"]:
        c = r["c"]
        if c in held:
            stt = "h"
        elif rec:
            stt = "b" if c in fill else "w"
        else:
            stt = "b" if k < free else "w"
            k += 1
        rows.append([c, r.get("n") or c, r.get("rs"), r.get("wk") or 1, "；".join(r.get("why") or []), r.get("px"), stt])
    from datetime import date, timedelta
    last = K.get("last") or P.get("d")
    d0 = (date.fromisoformat(last) - timedelta(days=240)).isoformat()
    d1 = (date.fromisoformat(last) + timedelta(days=200)).isoformat()
    a, b, hol = _tw_days(d0, d1)
    nx = PC.next_day("tw", K["d"]) if K.get("d") else None
    return {"d": K.get("d"), "last": last, "trial": bool(K.get("trial")), "fix": P.get("next_wk") if K.get("trial") else None,
            "buyd": PC.next_day("tw", P["next_wk"]) if K.get("trial") and P.get("next_wk") else nx, "top": slots, "free": free,
            "rows": rows, "px": K.get("px") or {}, "td": [a, b, hol], "hn": P.get("hold_n") or 60}


def _todo_box(P: dict, X: dict | None) -> str:
    """這週要做的事（照新飆股的規則，從現金開始）：要賣的、要買的、下一份名單。"""
    lines = []
    sells = [h for h in P.get("hold") or [] if h.get("sell")]
    if sells and P.get("next"):
        lines.append((f'{_mdw(P["next"])}開盤', f'<b class="dn">賣 {len(sells)} 檔</b>：' + "、".join(_e(h.get("n") or h["c"]) for h in sells)
                      + f'（滿 {P.get("hold_n") or 60} 個交易日）'))
    if X:
        b = [r for r in X["rows"] if r[6] == "b"]
        if X["trial"]:
            if X.get("fix"):
                lines.append((f'{_mdw(X["fix"])}收盤', "名單定案（這一週到現在還在變）"))
            if b and X.get("buyd"):
                lines.append((f'{_mdw(X["buyd"])}開盤', f'<b class="up">買 {len(b)} 檔</b>（照 {_md(X["last"])} 收盤試算）：'
                              + "、".join(_e(r[1]) for r in b)))
        elif b and X.get("buyd"):
            lines.append((f'{_mdw(X["buyd"])}開盤', f'<b class="up">買 {len(b)} 檔</b>（{_md(X["d"])} 的名單）：' + "、".join(_e(r[1]) for r in b)))
        elif X.get("free", 0) <= 0:
            lines.append(("", "8 格都滿了：等有股票到期賣掉才買新的"))
    if not X or not X["trial"]:
        nw = P.get("next_wk")
        if nw:
            lines.append((f'{_mdw(nw)}收盤', "下一份名單"))
    if not lines:
        return ""
    return ('<div class="pktodo"><h3>接下來<span class="sub">照規則、從現金開始</span></h3>'
            + "".join(f'<div class="pktl"><span>{_e(a)}</span><span>{b}</span></div>' for a, b in lines) + "</div>")


def boom_card(P: dict, evs: list[dict], bundle: dict, X: dict | None, col: int) -> str:
    """新飆股（docs/lab_boom_v2_plan.md 第 8、9 節；docs/lab_pick_arch_plan.md 第一段）：接下來 → 我的（觀察／已買，存在這台裝置）→
    這週名單（篩選、強度、上名單幾週、照規則會不會買、標自己的狀態）→ 為什麼不等買點 → 名單位置圖（上名單幾週×強度）→
    照規則的紀錄（8 格那一本、原本每檔 12.5% 那一本）收起。書上的買點不放在這張卡（原本的飆股名單在研究紀錄）。
    名單與位置圖在瀏覽器畫（pkBoomDraw）；X＝boom_box（tw_view 算一次）。"""
    W = w10()
    if W.get("pick"):
        a, c, t = W["pick"], W.get("cur") or {}, W.get("tr") or {}
        past = (f'2019 年起照做一年 <b>{_pc(a["cagr"]["all"])}</b>、最慘時跌 {a["mdd"]["all"] * 100:.0f}%'
                f'（同一段大盤一年 {_pc((t.get("cagr") or {}).get("all"))}、最慘時跌 {(t.get("mdd") or {}).get("all", 0) * 100:.0f}%；'
                f'原本每檔 12.5%、最多 20 檔的買法一年 {_pc((c.get("cagr") or {}).get("all"))}、最慘時跌 {(c.get("mdd") or {}).get("all", 0) * 100:.0f}%）。'
                "每一年只用之前幾年的資料找條件。")
        y = (a.get("yearly") or {}).get("2026")
        yc = (c.get("yearly") or {}).get("2026")
        notes = ["8 格、新上名單先買，是用 2019–2022 年的成績挑的；2023 年起只比原本的買法多 "
                 f'{((a["cagr"]["h2"] - (c.get("cagr") or {}).get("h2", 0)) * 100):.1f} 個百分點'
                 + (f'，今年到 {_md(W.get("last"))} {_pc(y)}（原本的買法 {_pc(yc)}）' if y is not None and yc is not None else "") + "。",
                 "最多 8 檔：每年漲最多的股票買到的次數比原本少一半，但每一檔都放到一格的錢。",
                 "為什麼抱 60 天：條件是用「買進後 60 個交易日」的漲幅找出來的；到期還在名單上就續抱，試過多半比較差。",
                 "回測從 2019 年起，大多是上漲的年份；最慘時跌得比大盤深很多。"]
    else:
        past, notes = "還沒有回測的數字。", []
    notes.append(f'{_md(sx_start())} 起照 8 格的規則記錄，還沒有上線後的成績。')
    held, todo = boom_rows(P)
    lead = _todo_box(P, X) + '<div class="pkmine" id="pkmine"></div>'
    if X:
        lead += (f'<h3 class="cfh3" id="pkbxh">這週名單<span class="sub">'
                  + (f'{_e(_md(X["last"]))} 收盤試算・{_e(_md(X["fix"]))} 收盤定案' if X["trial"] else f'{_e(_md(X["d"]))} 收盤')
                  + '</span></h3><div class="pkbx" id="pkbx"></div>'
                  + f'<p class="pknw">{_e(nowait_txt(W))}</p>'
                  '<details class="cfdet pkdet pksd" open><summary>名單位置圖：為什麼是這幾檔</summary>'
                  '<div class="pksdn">先買新上名單的，同一週上名單的比強度，8 格滿了的等空位。</div>'
                  '<div class="spotx cfspx"><div class="spotbox" id="pkspot"></div><div class="vztip" id="pkspottip" hidden></div></div>'
                  '<div class="pkskey" id="pkspotk"></div>'
                  '<div class="vzlg cfsplg pkslg"><span><i class="b"></i>照規則會買（數字＝買的順序）</span><span><i class="h"></i>拿著</span>'
                  '<span><i class="w"></i>等空位</span><span>點一下打開個股卡</span></div></details>'
                  '<div class="pkrl">原本的飆股名單（書上的買點）移到<a data-go="plan" data-pm="tw" data-at="cf-tw-sx">研究紀錄</a>。</div>')
    else:
        nw = P.get("next_wk")
        lead += f'<div class="pkempty">{_e(f"下一份名單 {_mdw(nw)}收盤出來。" if nw else "還沒有名單。")}</div>'
    rec = ""
    if held or todo:
        rec += (f'<h4 class="pkrh">8 格那一本：拿著 {len(held)} 檔</h4><div class="cfgr pkgr">{"".join(held)}</div>' if held else "") \
            + (f'<h4 class="pkrh">待買進 {len(todo)} 檔</h4><div class="cfgr pkgr">{"".join(todo)}</div>' if todo else "")
    else:
        rec += f'<div class="pkempty">8 格那一本從現金開始，{_e(_mdw(P.get("next_wk") or ""))}收盤的名單起照規則買。</div>'
    R6 = ((bundle or {}).get("stk") or {}).get("boom") or {}
    if R6.get("hold"):
        rec += (f'<div class="pkrl">原本每檔 12.5%、最多 20 檔的那一本（{_md(R6.get("take"))} 從回測接手）拿著 {len(R6["hold"])} 檔：'
                + "、".join(f'<a {CFP._ck(h["c"])}>{_e(h.get("n") or h["c"])}</a>' for h in R6["hold"])
                + '。<a data-go="plan" data-pm="tw" data-at="cf-tw-h">每一檔（研究紀錄）</a></div>')
    extra = f'<details class="cfdet pkdet pkrec"><summary>照規則的紀錄</summary>{rec}</details>'
    return _card("boom", NAMES["boom"], col, [], [], evs, past, notes, extra=extra, lead=lead,
                 link='<a data-go="plan" data-pm="tw" data-at="cf-tw-y">今年每一筆（研究紀錄）</a>', empty=None)


def sx_start() -> str:
    from . import sxlivespec as SS
    return PC.week_ends("tw", SS.START4, PC.horizon(SS.START4, 1))[0]


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


WEEK_N = 5                              # 「這週要做的事」：接下來幾個交易日
_ACT = {"買進": "買", "賣出": "賣", "換股": "換股", "調整": "調整"}


def week_rows(evs: list[dict], d: str | None, main: list[str], n: int = WEEK_N) -> dict:
    """台股頁最上面「這週要做的事」（docs/lab_pick_arch_plan.md 第 3 節、使用者 D4）：主要策略接下來 n 個交易日要做的買賣，
    和行事曆同一份事件（pickcal）。買的那幾列帶這條策略自己的條件與什麼時候賣（META），不放別的方法的價位；
    還不知道是哪幾檔的（照規則會出新名單的日子）另外一行。
    → {"a", "b"（第一天、最後一天）, "rows": [{d, at, k, act, items, note, cond, exit}], "fix": [[策略, [[日期, 開盤/收盤]]]]}。"""
    if not d:
        return {"rows": [], "fix": []}
    days = PC.next_days("tw", d, n)
    a, b = days[0], days[-1]
    ks = set(main)
    rows, fix = [], {}
    for e in evs:
        if e["k"] not in ks or not a <= e["d"] <= b:
            continue
        if e.get("proj") and not e["items"]:
            if e["act"] in ("名單", "換股"):
                fix.setdefault(e["k"], []).append([e["d"], e["at"]])
            continue
        if e["act"] not in _ACT:
            continue
        m = META.get(e["k"]) or {}
        buy = e["act"] != "賣出"
        rows.append({"d": e["d"], "at": e["at"], "k": e["k"], "act": e["act"], "items": [[i["c"], i["n"]] for i in e["items"]],
                     "note": e.get("note") or "", "cond": m.get("cond", "") if buy else "", "exit": m.get("exit", "") if buy else ""})
    return {"a": a, "b": b, "rows": rows, "fix": [[k, v] for k, v in fix.items()]}


def week_box(W: dict, col: dict) -> str:
    """week_rows → 一張表（手機變成一列一張）。股票可以點（開個股卡）。"""
    if not W.get("a"):
        return ""
    def its(L):
        a = [f'<a {CFP._ck(c)}>{_e(n)}</a>' for c, n in L[:10]]
        return "、".join(a) + (f" 等 {len(L)} 檔" if len(L) > 10 else "")
    tr = []
    for r in W["rows"]:
        k = r["k"]
        c = f' style="--c:var(--cfc{col[k]})"' if col.get(k) else ""
        what = (f'<b class="a {"buy" if r["act"] == "買進" else "sell" if r["act"] == "賣出" else ""}">{_ACT[r["act"]]}</b>'
                + (f' {its(r["items"])}' if r["items"] else "") + (f'<div class="nt">{_e(r["note"])}</div>' if r["note"] else ""))
        tr.append(f'<tr{c}><td class="pkwd">{_e(_mdw(r["d"]))}{_e(r["at"])}</td>'
                  f'<td class="pkwk"><a class="tg" data-to="pk-{_e(k)}">{_e(PC.SHORT.get(k, k))}</a></td><td class="pkwm">{what}</td>'
                  f'<td class="pkwc"><span class="pkwl">條件</span>{_e(r["cond"] or "—")}</td>'
                  f'<td class="pkwx"><span class="pkwl">什麼時候賣</span>{_e(r["exit"] or "—")}</td></tr>')
    body = ('<div class="tw"><table class="sxt pkwt"><thead><tr><th class="l">哪一天</th><th>策略</th><th>做什麼</th><th>條件</th>'
            f'<th>什麼時候賣</th></tr></thead><tbody>{"".join(tr)}</tbody></table></div>') if tr else \
        f'<div class="pkempty">{_e(_md(W["a"]))}～{_e(_md(W["b"]))} 沒有已經知道是哪幾檔的買賣。</div>'
    fx = "".join(f'<span style="--c:var(--cfc{col[k]})"><i></i>{_e(PC.SHORT.get(k, k))} '
                 + "、".join(_e(f"{_mdw(d)}{at}") for d, at in v) + "</span>"
                 for k, v in W["fix"] if col.get(k))
    return (f'<section class="sec" id="pk-tw-todo" data-nav="這週要做的事"><h2 class="cfh">這週要做的事<span class="sub">'
            f'{_e(_mdw(W["a"]))}～{_e(_mdw(W["b"]))}，主要 {len(col)} 條策略合併</span></h2>{body}'
            + (f'<div class="pknx2"><b>會出新名單的日子</b>{fx}</div>' if fx else "")
            + '<div class="pkwn">條件和什麼時候賣都是那條策略自己的規則；名單上的股票不用等別的買點。</div></section>')


def boom_pos(P: dict | None, X: dict | None = None) -> dict:
    """個股卡最上面「策略」段、個股表「策略選到的」要的新飆股持股與待買進：{代號: [{k, n, h, t, y}]}。
    X＝boom_box：這一週還在試算時，照規則會買的也列（寫試算、哪天定案）。"""
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
    if X and X.get("trial"):
        for r in X.get("rows") or []:
            if r[6] == "b" and r[0] not in out:
                out[r[0]] = [{"k": "boom", "n": r[1], "h": 0, "y": r[4],
                              "t": f'照 {_md(X["last"])} 收盤試算，{_md(X.get("buyd"))} 開盤會買（{_md(X.get("fix"))} 收盤名單定案）'}]
    return out


def tw_view(data: dict, bundle: dict, today: str | None = None) -> dict:
    A = data.get("adv") or {}
    P = data.get("n8")                                    # sxlivespec VER 4：選股頁看 8 格那一本（交易計畫照舊看 R60）
    main, other = tw_keys(A, P)
    book = {b["k"]: b for b in A.get("book") or []}
    cal = PC.tw_events(A, P, s3_plan(data), main + other, today)
    evs = cal["ev"]
    X = boom_box(P) if P else None
    col = {k: i + 1 for i, k in enumerate(main[:8])}
    cards = []
    for k in main:
        if k == "boom":
            cards.append(boom_card(P, evs, bundle, X, col[k]))
        elif k in book:
            cards.append(adv_card(k, book[k], A, evs, col[k]))
    others = [adv_card(k, book[k], A, evs, None) for k in other if k in book]
    olist = "".join(other_line(k, book[k], evs, A) for k in other if k in book)
    ks = [[k, PC.SHORT.get(k, k), col.get(k, 0), 1] for k in main] + [[k, PC.SHORT.get(k, k), 0, 0] for k in other]
    return {"d": cal["d"], "end": cal["end"], "ev": _pack(evs), "ks": ks, "hol": holidays("tw", cal["d"], cal["end"]),
            "todo": week_box(week_rows(evs, cal["d"], main), col),
            "cards": "".join(cards), "others": "".join(others), "olist": olist, "pos": boom_pos(P, X), "bx": X,
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
.pkd .pkn{font-weight:700;font-size:12.5px;color:var(--ink2);display:flex;align-items:center;gap:3px}
.pkd .pkn span{font-weight:400;font-size:11px;color:var(--mut)}
.pkdots{display:inline-flex;gap:2px;margin-left:auto}.pkdots i{width:7px;height:7px;border-radius:50%;background:var(--c,var(--mut));opacity:.85}
.pke{display:flex;align-items:flex-start;gap:3px;line-height:1.35;margin-top:2px;border-left:3px solid var(--c,var(--mut));padding-left:3px;min-width:0}
.pke b{flex:none;font-size:11.5px;color:var(--ink)}
.pke span{color:var(--ink);overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-all}
.pke.ern span{color:var(--mut)}.pke.mine{border-left-style:dashed}
.pke.pkplus{color:var(--mut);font-size:11px;border:0}
@media (max-width:520px){.pkd{min-height:56px;padding:2px 3px}.pke{margin-top:1px;padding-left:2px;border-left-width:2px}.pke b{font-size:11px}
 .pke span{-webkit-line-clamp:1;font-size:11px;white-space:nowrap;text-overflow:ellipsis;display:block}.pkdots i{width:6px;height:6px}}
.pkday{margin:12px 0 0;border-top:1px solid var(--line);padding-top:10px}
.pkday h4{font-size:14.5px;margin:0 0 6px}
.pkdl2{list-style:none;margin:0;padding:0}
.pkdl2 li{display:grid;grid-template-columns:3.2em auto minmax(0,1fr);gap:2px 8px;align-items:baseline;font-size:13.5px;padding:5px 0;border-top:1px solid var(--line)}
.pkdl2 li:first-child{border-top:0}
.pkdl2 .at{color:var(--mut);font-size:12.5px}
.pkdl2 .tg{font-size:12px;padding:0 7px;border-radius:999px;border:1px solid var(--c,var(--mut));color:var(--c,var(--mut));white-space:nowrap}
.pkdl2 .tx b.a{font-weight:700;margin-right:4px}.pkdl2 .tx b.buy{color:var(--gain)}.pkdl2 .tx b.sell{color:var(--loss)}
.pkdl2 .tx a{color:var(--ink);cursor:pointer}.pkdl2 .tx a:hover{color:var(--acc)}.pkdl2 .tx .nt{color:var(--mut);font-size:12.5px}
.pknx2{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--ink2);margin:10px 0 0;padding-top:8px;border-top:1px solid var(--line)}
.pknx2 b{color:var(--ink);font-weight:700;margin-right:2px}.pknx2 i{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--c,var(--mut));margin-right:4px}
@media (max-width:520px){.pkdl2 li{grid-template-columns:3em minmax(0,1fr)}.pkdl2 .tg{grid-column:2;justify-self:start}.pkdl2 .tx{grid-column:2}}
.pkag{margin:14px 0 0}.pkag h4{font-size:14.5px;margin:0 0 4px}
.pkagd{margin:8px 0 0}.pkagd>b{font-size:13.5px}.pkagd>b span{font-weight:400;color:var(--mut);font-size:12.5px;margin-left:4px}
.pklg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--mut);margin:8px 0 0}
.pklg i.pkdl{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--mut);margin-right:5px}
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
/* 這週要做的事（week_box；docs/lab_pick_arch_plan.md 第 3 節）：手機一列一張 */
.pkwt{max-width:980px}.pkwt td{vertical-align:top;text-align:left;white-space:normal;font-size:13.5px;line-height:1.6}
.pkwt td.pkwd{white-space:nowrap;font-weight:700;color:var(--ink)}.pkwt .pkwl{display:none}
.pkwt .tg{font-size:12px;padding:0 7px;border-radius:999px;border:1px solid var(--c,var(--mut));color:var(--c,var(--mut));white-space:nowrap;cursor:pointer}
.pkwt th{text-align:left}.pkwt .pkwm a{color:var(--ink);cursor:pointer;white-space:nowrap}.pkwt .pkwm a:hover{color:var(--acc)}.pkwt b.a{margin-right:2px}
.pkwt b.buy{color:var(--gain)}.pkwt b.sell{color:var(--loss)}.pkwt .nt{color:var(--mut);font-size:12.5px}
.pkwt td.pkwc,.pkwt td.pkwx{color:var(--ink2);min-width:8em}
.pkwn{font-size:12.5px;color:var(--mut);margin:8px 0 0;max-width:880px}
@media (max-width:640px){.sxt.pkwt,.sxt.pkwt tbody{display:block;width:100%}.sxt.pkwt thead{display:none}
 .sxt.pkwt tr{display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;padding:9px 2px;border-top:1px solid var(--line)}
 .sxt.pkwt td{display:block;padding:0;border:0;min-width:0}
 .sxt.pkwt td.pkwd{grid-column:1}.sxt.pkwt td.pkwk{grid-column:2;justify-self:start}
 .sxt.pkwt td.pkwm,.sxt.pkwt td.pkwc,.sxt.pkwt td.pkwx{grid-column:1 / -1}
 .pkwt .pkwl{display:inline;color:var(--mut);font-size:12px;margin-right:6px}}
/* 新飆股卡片 v2（docs/lab_boom_v2_plan.md 第 8 節） */
.pktodo{background:var(--card2);border-radius:12px;padding:10px 14px;margin:2px 0 12px;max-width:880px}
.pktodo h3{font-size:15px;margin:0 0 6px}.pktodo h3 .sub{font-size:12.5px;font-weight:400;color:var(--mut);margin-left:6px}
.pktl{display:grid;grid-template-columns:8.6em minmax(0,1fr);gap:2px 10px;font-size:13.5px;padding:3px 0;line-height:1.6}
.pktl span:first-child{color:var(--ink2);white-space:nowrap}.pktl b.up{color:var(--gain)}.pktl b.dn{color:var(--loss)}
.pkmine{max-width:880px;margin:0 0 10px}.pkmh{font-size:13px;color:var(--mut);margin:0 0 8px}
.pkmr{border-top:1px solid var(--line);padding:7px 0;font-size:13.5px}.pkmr:first-of-type{border-top:0}
.pkma{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.pkma a{color:var(--ink);cursor:pointer}
.pkma .r{margin-left:auto;font-weight:700;font-variant-numeric:tabular-nums}.pkma .r.up{color:var(--gain)}.pkma .r.dn{color:var(--loss)}
.pkrm{font:inherit;font-size:12px;border:1px solid var(--line2);background:var(--bg);color:var(--mut);border-radius:8px;padding:1px 8px;cursor:pointer}
.pkmb2{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;margin-top:3px;font-size:12.5px;color:var(--ink2)}
.pkmb2 label{display:inline-flex;align-items:center;gap:4px;color:var(--mut)}
.pkin{font:inherit;font-size:13px;padding:2px 6px;border:1px solid var(--line2);border-radius:6px;background:var(--bg);color:var(--ink);width:9.5em}
.pkin[type=number]{width:6.5em}.pkms2{color:var(--ink2)}
.pkfs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px}
.pkbn{font-size:13px;color:var(--ink2);margin:0 0 6px;max-width:880px}
.pkt{max-width:880px}.pkt td{vertical-align:top}.pkt .pkwhy{max-width:420px}
.pkst{display:inline-block;padding:0 7px;border-radius:8px;font-size:12px;white-space:nowrap;background:var(--card2);color:var(--ink2)}
.pkst.b{background:var(--gainbg);color:var(--gain);font-weight:700}.pkst.h{background:var(--hlbg);color:var(--accd);font-weight:700}.pkst.w{color:var(--mut)}
.pknew{color:var(--acc);font-weight:700;white-space:nowrap}
.pkmk{display:inline-flex;gap:4px}
.pkmb{font:inherit;font-size:12px;padding:2px 8px;border-radius:8px;border:1px solid var(--line2);background:var(--bg);color:var(--ink2);cursor:pointer;white-space:nowrap}
.pkmb.on{background:var(--acc);border-color:var(--acc);color:#fff}.pkmb.b.on{background:var(--gain);border-color:var(--gain)}
.pksp circle{stroke:var(--bg);stroke-width:2;cursor:pointer}.pksp:hover circle{stroke:var(--ink);stroke-width:2}
.pksp.b circle{fill:var(--gain)}.pksp.h circle{fill:var(--acc)}.pksp.w circle{fill:var(--mut2);fill-opacity:.6}
.pkspn{fill:#fff;font-size:10.5px;font-weight:700;pointer-events:none}.pksd .spotx{max-width:880px}
.pkskey{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;font-size:13px;color:var(--ink2);margin:6px 2px 0;max-width:880px;line-height:1.6}
.pkskey span{white-space:nowrap}.pkskey b{display:inline-block;min-width:18px;height:18px;line-height:18px;text-align:center;border-radius:50%;background:var(--gain);color:#fff;font-size:11px;margin-right:4px}
.pkskey a{color:var(--ink);cursor:pointer}.pkskey a:hover{color:var(--acc)}.pkskey .pkskh{color:var(--mut)}
.pkslg i.b{background:var(--gain)}.pkslg i.h{background:var(--acc)}.pkslg i.w{background:var(--mut2)}
.pkcl{stroke:var(--line);stroke-dasharray:2 4}.pksdn{font-size:12.5px;color:var(--mut);margin:0 0 6px}
.pknw{font-size:13px;color:var(--ink2);background:var(--card2);border-radius:10px;padding:8px 12px;margin:10px 0 0;max-width:880px;line-height:1.7}
.pkrh{font-size:14px;margin:8px 0 4px}.pkrl{font-size:13px;color:var(--ink2);margin:8px 0 0;max-width:880px;line-height:1.7}
.pkrl a{color:var(--acc);cursor:pointer}.pkrule{margin:10px 0 0}
@media (max-width:640px){.pktl{grid-template-columns:minmax(0,1fr);gap:0}.pktl span:first-child{font-size:12.5px;color:var(--mut)}
 .sxt.pkt,.sxt.pkt tbody{display:block;width:100%}.sxt.pkt thead{display:none}
 .sxt.pkt tr{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 10px;padding:9px 2px;border-top:1px solid var(--line)}
 .sxt.pkt td{display:block;padding:0;border:0;min-width:0;text-align:left;white-space:normal}
 .sxt.pkt td.l{grid-column:1;grid-row:1 / span 2}
 .sxt.pkt td.pkstc{grid-column:2;grid-row:1;text-align:right}.sxt.pkt td.pkmc{grid-column:2;grid-row:2;align-self:start}
 .sxt.pkt td.hm{display:none}.pkt .pkwhy{max-width:none}.pkmk{flex-direction:column}}
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
  const d=P.d||'',ms=pkMonths(mk);let m0=d.slice(0,7);if(pkLeft(P)<5&&ms[1])m0=ms[1];
  PKST[mk]={on,more:false,m:m0,sel:null,ag:false};}return PKST[mk];}
function pkCol(mk,k){if(k==='mine')return 'var(--ink)';const x=((PICK[mk]||{}).ks||[]).find(y=>y[0]===k);return x&&x[2]?`var(--cfc${x[2]})`:'var(--mut)';}
function pkShort(mk,k){if(k==='mine')return '我的';const x=((PICK[mk]||{}).ks||[]).find(y=>y[0]===k);return x?x[1]:k;}
/* 自己標「已買」的台股：照新飆股的規則（買進後第 60 個交易日收盤到期、隔天開盤賣）排賣出日（只在這台裝置） */
function pkMineEvs(mk){if(mk!=='tw'||typeof pkMine!=='function')return [];const P=PICK.tw||{},M=pkMine(),out=[];
  Object.entries(M).forEach(([c,m])=>{if(m.s!=='b'||!m.d)return;const s=pkSell(m.d);if(s.out&&s.out>P.d)out.push([s.out,'開盤','mine','賣出',[[c,m.n||c]],`${pkMd(m.d)} 買的，照規則滿 ${(pkBx()||{}).hn||60} 個交易日`,0]);});
  return out;}
function pkEvs(mk){const P=PICK[mk]||{},S=pkState(mk);const A=(P.ev||[]).concat(S.on.has('mine')?pkMineEvs(mk):[]);
  const at={'開盤':0,'':1,'收盤':2};return A.filter(e=>S.on.has(e[2])).sort((a,b)=>a[0]<b[0]?-1:a[0]>b[0]?1:(at[a[1]]??1)-(at[b[1]]??1));}
function pkMonths(mk){const P=PICK[mk]||{};if(!P.d||!P.end)return [];const out=[];let y=+P.d.slice(0,4),m=+P.d.slice(5,7);
  const ey=+P.end.slice(0,4),em=+P.end.slice(5,7);while(y<ey||(y===ey&&m<=em)){out.push(`${y}-${String(m).padStart(2,'0')}`);m++;if(m>12){m=1;y++;}}return out;}
function pkItems(mk,its,n){const us=mk==='us';const a=(its||[]).slice(0,n||8).map(([c,nm])=>us?`<a href="#us=${encodeURIComponent(c)}" data-us="${esc(c)}">${esc(nm)}</a>`:`<a data-c="${esc(c)}" data-co="${esc(c)}">${esc(nm)}</a>`);
  return a.join('、')+((its||[]).length>(n||8)?` 等 ${its.length} 檔`:'');}
const PKAC={'買進':'買','賣出':'賣','換股':'換','調整':'調','財報':'財報','名單':'名單'};
function pkLine(mk,e){const nm=pkShort(mk,e[2]);
  const its=e[4]&&e[4].length?` ${pkItems(mk,e[4])}`:'';
  return `<li style="--c:${pkCol(mk,e[2])}"><span class=at>${esc(e[1]||'')}</span><span class=tg>${esc(nm)}</span><span class=tx><b class="a ${e[3]==='買進'?'buy':e[3]==='賣出'?'sell':''}">${esc(PKAC[e[3]]||e[3])}</b>${its}${e[5]?` <span class=nt>${esc(e[5])}</span>`:''}</span></li>`;}
function pkMonth(mk,ym,evs){const P=PICK[mk]||{},S=pkState(mk),hol=new Set(P.hol||[]),by={};evs.forEach(e=>{(by[e[0]]=by[e[0]]||[]).push(e);});
  const y=+ym.slice(0,4),m=+ym.slice(5,7),n=new Date(Date.UTC(y,m,0)).getUTCDate();let cells='',lead=null;
  for(let d=1;d<=n;d++){const ds=`${ym}-${String(d).padStart(2,'0')}`,wd=new Date(ds+'T00:00:00Z').getUTCDay();if(wd===0||wd===6)continue;
    if(lead===null){lead=wd-1;for(let i=0;i<lead;i++)cells+='<div class="pkd blank"></div>';}
    const es=by[ds]||[],past=ds<=P.d,isH=hol.has(ds);let cls='pkd'+(past?' past':'')+(isH?' hol':'')+(ds===P.d?' today':'')+(S.sel===ds?' sel':'');
    const co=es.filter(e=>e[4].length),dots=[...new Set(es.filter(e=>!e[4].length).map(e=>e[2]))];   /* 有公司的寫公司名；還不知道是哪幾檔的縮成小點 */
    let h=`<div class="${cls}" data-pkd="${ds}"><div class=pkn>${d}${isH?'<span>休市</span>':ds===P.d?'<span>資料日</span>':''}`+
      (dots.length?`<i class=pkdots>${dots.map(k=>`<i style="--c:${pkCol(mk,k)}" title="${esc(pkShort(mk,k))}：照規則會出新名單或換股（還不知道是哪幾檔）"></i>`).join('')}</i>`:'')+`</div><div class=pkev>`;
    co.slice(0,3).forEach(e=>{const n=e[4].map(x=>x[1]),t=n.slice(0,3).join('、')+(n.length>3?` 等 ${n.length} 檔`:'');
      h+=`<div class="pke${e[2]==='ern'?' ern':''}${e[2]==='mine'?' mine':''}" style="--c:${pkCol(mk,e[2])}" title="${esc(pkShort(mk,e[2])+' '+e[3]+'：'+n.join('、'))}"><b>${esc(PKAC[e[3]]||e[3])}</b><span>${esc(t)}</span></div>`;});
    if(co.length>3)h+=`<div class="pke pkplus">+${co.length-3}</div>`;
    cells+=h+'</div></div>';}
  return `<div class=pkm><h4>${y} 年 ${m} 月</h4><div class=pkg>${'一二三四五'.split('').map(w=>`<div class=pkw>${w}</div>`).join('')}${cells}</div></div>`;}
function pkDay(mk,ds,evs){const es=evs.filter(e=>e[0]===ds);
  return `<h4>${pkMdw(ds)}</h4>`+(es.length?`<ul class=pkdl2>${es.map(e=>pkLine(mk,e)).join('')}</ul>`:'<div class=st>這一天沒有排定的事。</div>');}
const PKAG=6;   /* 「接下來」先列 6 天，其餘點「再看」 */
function pkAgenda(mk,evs){const S=pkState(mk),co=evs.filter(e=>e[4].length),all=[...new Set(co.map(e=>e[0]))].sort(),days=all.slice(0,S.ag?40:PKAG);
  /* 只列已經知道是哪幾檔的買賣；還不知道的（照規則會出名單的日子）縮成最下面一行 */
  const fx={};evs.filter(e=>!e[4].length&&(e[3]==='名單'||e[3]==='換股')).forEach(e=>{(fx[e[2]]=fx[e[2]]||[]).push(e[0]);});
  const nx=Object.entries(fx).map(([k,ds])=>`<span style="--c:${pkCol(mk,k)}"><i></i>${esc(pkShort(mk,k))} ${ds.slice(0,3).map(pkMd).join('、')}${ds.length>3?' …':''}</span>`).join('');
  let h=days.length?days.map(d=>`<div class=pkagd><b>${pkMdw(d)}</b><ul class=pkdl2>${co.filter(e=>e[0]===d).map(e=>pkLine(mk,e)).join('')}</ul></div>`).join(''):'<div class=st>接下來還沒有排定要買賣的公司。</div>';
  if(all.length>days.length)h+=`<button type=button class="pkk pkmo pkagm" data-pkag=1>再看 ${Math.min(40,all.length)-days.length} 天</button>`;
  if(nx)h+=`<div class=pknx2><b>會出新名單的日子</b>${nx}</div>`;
  return h;}
function pkCalDraw(mk){const box=$('#pkcal-'+mk);if(!box)return;const P=PICK[mk]||{},S=pkState(mk),ms=pkMonths(mk);if(!ms.length){box.innerHTML='<div class=st>行事曆還沒算出來。</div>';return;}
  if(!ms.includes(S.m))S.m=ms[0];const i=ms.indexOf(S.m),two=matchMedia('(min-width:900px)').matches,step=two?2:1;
  const evs=pkEvs(mk),main=(P.ks||[]).filter(x=>x[3]),oth=(P.ks||[]).filter(x=>!x[3]);
  const chip=x=>`<button type=button class="pkk${S.on.has(x[0])?'':' off'}" data-pkk="${esc(x[0])}" style="--c:${x[0]==='mine'?'var(--ink)':x[2]?`var(--cfc${x[2]})`:'var(--mut)'}" aria-pressed="${S.on.has(x[0])}"><i></i>${esc(x[1])}</button>`;
  const mine=mk==='tw'&&typeof pkMine==='function'&&Object.values(pkMine()).some(m=>m.s==='b');
  if(mine&&S.mineInit!==1){S.on.add('mine');S.mineInit=1;}
  let h=`<div class=pkct><div class=pkks>${main.map(chip).join('')}${mine?chip(['mine','我標已買的',0,1]):''}${oth.length?(S.more?oth.map(chip).join(''):`<button type=button class="pkk pkmo" data-pkmore=1>＋其他 ${oth.length} 條</button>`):''}</div>`+
    `<div class=pkmn><button type=button data-pkm="-1" ${i<=0?'disabled':''} aria-label="上一個月">‹</button><b>${+S.m.slice(5,7)} 月${two&&ms[i+1]?`～${+ms[i+1].slice(5,7)} 月`:''}</b><button type=button data-pkm="1" ${i+step>=ms.length?'disabled':''} aria-label="下一個月">›</button></div></div>`;
  h+=`<div class=pkms>${pkMonth(mk,ms[i],evs)}${ms[i+1]?pkMonth(mk,ms[i+1],evs):''}</div>`;
  h+=`<div class=pklg><span><i class=pkdl></i>小點＝照規則會出新名單或換股的日子（還不知道是哪幾檔），點日子看</span><span>格子裡＝已經知道是哪幾檔的買賣</span></div>`;
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
  else{h+=P.todo||'';
    h+=`<section class="sec" id="pk-${mk}-cal" data-nav="行事曆"><h2 class=cfh>${mk==='tw'?'台股':'美股'}進場行事曆<span class=sub>${P.d?`${pkMd(P.d)} 收盤`:''}${mk==='us'?'・美國當地日期':''}</span></h2>`+
    `<div class=pkcalw><div id="pkcal-${mk}"></div><div class=pkag><h4>接下來</h4><div id="pkag-${mk}"></div></div></div></section>`;
    h+=P.cards||'';
    if(P.olist)h+=`<section class=sec id="pk-${mk}-o" data-nav="其他策略"><details class=pkox><summary>其他策略（${(P.ks||[]).filter(x=>!x[3]).length} 條，過去成績比上面普通）</summary><ul class=pkol>${P.olist}</ul>${P.others||''}</details></section>`;}
  $('#main').innerHTML=h+`<footer class=cffoot><a data-go="strat">全部策略</a>・<a data-go="plan" data-pm="${mk}">原本的配置</a>・<a href="x9r.html">研究紀錄</a></footer>`;
  pkCalDraw(mk);
  $$('#main [data-to]').forEach(a=>a.onclick=e=>{e.preventDefault();const t=document.getElementById(a.dataset.to);const d=t&&t.closest('details');if(d)d.open=true;jump(a.dataset.to);});
  const so=$('#main .cfsxo');if(so)so.addEventListener('toggle',()=>{if(!so.open)return;   /* 另一份飆股名單（只看）：打開才組、才畫 */
    if(!so.dataset.done){so.querySelector('.cfsxob').innerHTML=typeof wlCfg==='function'?wlCfg():'';so.dataset.done=1;}spotDraw();});
  $$('#main .pkdet').forEach(d=>d.addEventListener('toggle',()=>{if(!d.open)return;if(d.classList.contains('pksd'))pkSpot();else cfSpot();}));
  if(mk==='tw')pkBoomDraw();}
/* ---------- 新飆股卡片（docs/lab_boom_v2_plan.md 第 8 節；docs/lab_pick_arch_plan.md 第一段）：這週名單（篩選、強度、上名單幾週、照規則會不會買）、
   自己標的觀察／已買（存在這台裝置的瀏覽器 localStorage，不會上傳）、「我的」、名單位置圖。資料＝PICK.tw.bx（pickpage.boom_box）。
   列＝[代號, 名稱, 強度, 上名單週數, 符合哪一條, 收盤, 現況 b/h/w]；書上的買點不放（新飆股不等買點）。 ---------- */
const PKMK='labPickMine',PKBS={f:'b'};
function pkBx(){return (PICK.tw||{}).bx||null;}
function pkMine(){try{const m=JSON.parse(localStorage.getItem(PKMK)||'{}');return m&&typeof m==='object'?m:{};}catch(e){return {};}}
function pkMineSave(m){try{localStorage.setItem(PKMK,JSON.stringify(m));}catch(e){}}
/* 台股交易日（週末＋證交所休市表）：照規則的賣出日＝買進後第 hn 個交易日收盤到期、隔天開盤賣 */
function pkTd(){const X=pkBx()||{},T=X.td||[];if(pkTd.c)return pkTd.c;const out=[],hol=new Set(T[2]||[]);if(!T[0])return out;
  for(let t=Date.parse(T[0]+'T00:00:00Z'),e=Date.parse(T[1]+'T00:00:00Z');t<=e;t+=864e5){const x=new Date(t),w=x.getUTCDay(),ds=x.toISOString().slice(0,10);if(w&&w<6&&!hol.has(ds))out.push(ds);}
  return pkTd.c=out;}
function pkSell(d){const td=pkTd(),hn=(pkBx()||{}).hn||60,i=td.findIndex(x=>x>=d);return i<0?{}:{due:td[i+hn]||null,out:td[i+hn+1]||null};}
function pkToday(){return new Date(Date.now()+8*3600e3).toISOString().slice(0,10);}
function pkLastTd(d){let r=null;for(const x of pkTd()){if(x<=d)r=x;else break;}return r;}
function pkPx(c){const X=pkBx()||{};const v=(X.px||{})[c];return v==null?null:v;}
function pkMarkBtns(c,n){const m=pkMine()[c]||{};
  return `<span class=pkmk><button type=button class="pkmb${m.s==='w'?' on':''}" data-pkmk="w" data-c2="${esc(c)}" data-n2="${esc(n)}" aria-pressed="${m.s==='w'}">觀察</button>`+
    `<button type=button class="pkmb b${m.s==='b'?' on':''}" data-pkmk="b" data-c2="${esc(c)}" data-n2="${esc(n)}" aria-pressed="${m.s==='b'}">已買</button></span>`;}
function pkMark(c,n,s){const M=pkMine(),X=pkBx()||{};
  if(M[c]&&M[c].s===s)delete M[c];
  else M[c]={s,n,d:s==='b'?(pkLastTd(pkToday())||X.last):X.last,p:pkPx(c)};
  pkMineSave(M);pkBoomDraw();if(typeof pkCalDraw==='function')pkCalDraw('tw');}
function pkSt(r){const X=pkBx()||{};return r[6]==='h'?'<span class="pkst h">拿著</span>':r[6]==='b'?`<span class="pkst b">${pkMd(X.buyd)} 開盤${X.trial?'會':''}買</span>`:'<span class="pkst w">等空位</span>';}
function pkWk(w){return w<=1?'<span class=pknew>新上名單</span>':`第 ${w} 週`;}
function pkRows(L){return L.map(r=>`<tr><td class=l><a data-c="${esc(r[0])}" data-co="${esc(r[0])}"><b>${esc(r[1])}</b></a> <span class=cd>${esc(r[0])}</span>`+
    `<div class="sm2 pkwhy">${esc(r[4]||'')}</div><div class="sm2 mo">強度 ${f(r[2],0)}・${r[3]<=1?'新上名單':`上名單第 ${r[3]} 週`}・收盤 ${fp(r[5])}</div></td>`+
    `<td class=hm>${f(r[2],0)}</td><td class=hm>${pkWk(r[3])}</td><td class=hm>${fp(r[5])}</td><td class=pkstc>${pkSt(r)}</td><td class=pkmc>${pkMarkBtns(r[0],r[1])}</td></tr>`).join('');}
function pkBxDraw(){const box=$('#pkbx'),X=pkBx();if(!box||!X)return;const R=X.rows||[],B=R.filter(r=>r[6]==='b'),N=R.filter(r=>r[3]<=1);
  const F=[['b',`${X.trial?'照規則會買':'會買'}的 ${B.length} 檔`,B],['n',`新上名單 ${N.length}`,N],['a',`全部 ${R.length}`,R]];
  if(!F.some(x=>x[0]===PKBS.f)||(!B.length&&PKBS.f==='b'))PKBS.f='a';
  const L=F.find(x=>x[0]===PKBS.f)[2];
  box.innerHTML=`<div class=pkfs role=group aria-label="名單篩選">${F.map(([k,t])=>`<button type=button class="pkk${PKBS.f===k?'':' off'}" data-pkf="${k}" aria-pressed="${PKBS.f===k}">${esc(t)}</button>`).join('')}</div>`+
    (PKBS.f==='b'?`<div class=pkbn>${X.trial?`照 ${pkMd(X.last)} 收盤試算：`:''}${X.free>=X.top?'從現金開始，':`空 ${X.free} 格，`}這幾檔照規則 ${pkMdw(X.buyd)}開盤買（新上名單的先、同一週上名單的依強度），每檔約 1/${X.top} 的錢。</div>`:'')+
    (L.length?`<div class=tw><table class="sxt pkt"><thead><tr><th class=l>股票・符合哪一條</th><th class=hm>強度</th><th class=hm>上名單</th><th class=hm>收盤</th><th>現況</th><th>我的</th></tr></thead><tbody>${pkRows(L)}</tbody></table></div>`:'<div class=st>沒有。</div>');
  box.querySelectorAll('[data-pkf]').forEach(b=>b.onclick=()=>{PKBS.f=b.dataset.pkf;pkBxDraw();});}
function pkMineDraw(){const box=$('#pkmine'),X=pkBx();if(!box)return;const M=pkMine(),ks=Object.keys(M);
  if(!ks.length){box.innerHTML=`<div class=pkmh>在名單上按「觀察」或「已買」，會列在這裡（只存在這台裝置的瀏覽器）。</div>`;return;}
  const on=new Set(((X||{}).rows||[]).map(r=>r[0]));
  const L=ks.map(c=>[c,M[c]]).sort((a,b)=>(a[1].s===b[1].s?0:a[1].s==='b'?-1:1)||String(a[1].d).localeCompare(String(b[1].d)));
  const row=([c,m])=>{const px=pkPx(c),r=px!=null&&m.p?px/m.p-1:null,rr=r==null?'':`<span class="r ${r>=0?'up':'dn'}">${pctT(r*100,1)}</span>`;
    let l2='';
    if(m.s==='b'){const s=pkSell(m.d||'');
      l2=`<label>買進日 <input type=date class=pkin data-pkd2="${esc(c)}" value="${esc(m.d||'')}"></label><label>買進價 <input type=number step=any min=0 class=pkin data-pkp2="${esc(c)}" value="${m.p==null?'':m.p}"></label>`+
        `<span class=pkms2>現在 ${fp(px)}${s.out?`・照規則 ${pkMdw(s.out)}開盤賣（${pkMd(s.due)} 收盤滿 ${(X||{}).hn||60} 個交易日）`:''}</span>`;}
    else l2=`<span class=pkms2>${pkMd(m.d)} 標觀察 ${fp(m.p)}，現在 ${fp(px)}・${on.has(c)?'這週還在名單上':'這週不在名單上'}</span>`;
    return `<div class="pkmr ${m.s}"><div class=pkma><a data-c="${esc(c)}" data-co="${esc(c)}"><b>${esc(m.n||c)}</b></a> <span class=cd>${esc(c)}</span>`+
      `<span class="pkst ${m.s==='b'?'b':'w'}">${m.s==='b'?'已買':'觀察'}</span>${rr}<button type=button class=pkrm data-pkrm="${esc(c)}" aria-label="移除">移除</button></div><div class=pkmb2>${l2}</div></div>`;};
  box.innerHTML=`<h3 class=cfh3>我的<span class=sub>只存在這台裝置的瀏覽器・換手機或清除瀏覽資料就不見</span></h3>${L.map(row).join('')}`;
  box.querySelectorAll('[data-pkrm]').forEach(b=>b.onclick=()=>{const M2=pkMine();delete M2[b.dataset.pkrm];pkMineSave(M2);pkBoomDraw();pkCalDraw('tw');});
  box.querySelectorAll('[data-pkd2]').forEach(i=>i.onchange=()=>{const M2=pkMine(),m=M2[i.dataset.pkd2];if(m&&/^\d{4}-\d{2}-\d{2}$/.test(i.value)){m.d=i.value;pkMineSave(M2);pkBoomDraw();pkCalDraw('tw');}});
  box.querySelectorAll('[data-pkp2]').forEach(i=>i.onchange=()=>{const M2=pkMine(),m=M2[i.dataset.pkp2],v=parseFloat(i.value);if(m&&v>0){m.p=v;pkMineSave(M2);pkBoomDraw();}});}
/* 名單位置圖（使用者 2026-10-30：改成新飆股自己的圖）：橫軸＝上名單第幾週（6 欄）、縱軸＝強度、顏色＝照規則會買／拿著／等空位。
   就是照規則先買誰的順序：新上名單的（最左欄）先，同一欄比強度，8 格滿了的等空位。同一欄強度相近的左右錯開；
   會買的點裡寫買的順序，名字在圖下面一行（同一欄強度相近的名字放在圖裡一定互撞）。 */
const PKWB=[[1,1,'新上名單'],[2,2,'第 2 週'],[3,3,'第 3 週'],[4,8,'4～8 週'],[9,26,'9～26 週'],[27,1e9,'27 週以上']];
function pkSpot(){const box=$('#pkspot'),X=pkBx();if(!box||!X)return;const P=X.rows||[];if(!P.length){box.innerHTML='';return;}
  const W=box.clientWidth||720,mob=W<560,H=mob?300:330,ml=mob?30:40,mr=6,mt=26,mb=40,cw=(W-ml-mr)/PKWB.length,R=mob?{b:7,h:6.5,w:4}:{b:8,h:7,w:4.5};
  let nb=0,nq=0;const rk=P.map(o=>o[6]==='b'?++nb:0),qp=P.map(o=>o[6]==='h'?0:++nq);   /* rk＝第幾個買、qp＝排第幾（拿著的不排） */
  const y0=Math.min(60,Math.max(0,Math.floor((Math.min(...P.map(o=>o[2]==null?100:o[2]))-3)/10)*10));
  const Yv=v=>mt+(100-Math.max(y0,Math.min(100,v==null?y0:v)))/(100-y0)*(H-mt-mb);
  const col=w=>Math.max(0,PKWB.findIndex(b=>w>=b[0]&&w<=b[1]));
  let s='';
  for(let v=y0;v<=100;v+=10)s+=`<line class=spot-grid x1=${ml} x2=${W-mr} y1=${Yv(v).toFixed(1)} y2=${Yv(v).toFixed(1)} /><text class=spot-at x=${ml-6} y=${(Yv(v)+4).toFixed(1)} text-anchor=end>${v}</text>`;
  PKWB.forEach((b,i)=>{if(i)s+=`<line class=pkcl x1=${(ml+cw*i).toFixed(1)} x2=${(ml+cw*i).toFixed(1)} y1=${mt} y2=${H-mb} />`;
    s+=`<text class=spot-at x=${(ml+cw*(i+.5)).toFixed(1)} y=${H-mb+16} text-anchor=middle>${esc(b[2])}</text>`;});
  s+=`<text class=spot-al x=${W-mr} y=${H-4} text-anchor=end>上名單第幾週</text><text class=spot-al x=4 y=${mt-10}>強度</text>`;
  const at=[],byc={};P.forEach((o,i)=>{(byc[col(o[3])]=byc[col(o[3])]||[]).push(i);});
  /* 先放會買、拿著的（照強度），再放等空位的；都放不下就放在重疊最少的地方（手機一欄不到 50px） */
  Object.entries(byc).forEach(([c,ix])=>{const cx=ml+cw*(+c+.5),done=[];
    ix.sort((a,b)=>(P[a][6]==='w')-(P[b][6]==='w')||(P[b][2]||0)-(P[a][2]||0)).forEach(i=>{const y=Yv(P[i][2]),r=R[P[i][6]]||5;let x=cx,best=-1e9;
      for(let k=0;k<=30;k++){const dx=k?Math.ceil(k/2)*(r+1)*(k%2?1:-1):0;if(Math.abs(dx)>cw/2-2)break;
        const gap=Math.min(1e9,...done.map(p=>Math.hypot(p[0]-(cx+dx),p[1]-y)-p[2]-r-1));
        if(gap>=0){x=cx+dx;break;}if(gap>best){best=gap;x=cx+dx;}}
      done.push([x,y,r]);at[i]=[x,y];});});
  const ord={w:0,h:1,b:2};
  P.map((o,i)=>[o,i]).sort((a,b)=>ord[a[0][6]]-ord[b[0][6]]).forEach(([o,i])=>{
    const [x,y]=at[i];s+=`<g class="pksp ${o[6]}" data-pksp=${i} data-c="${esc(o[0])}" data-co="${esc(o[0])}"><circle cx=${x.toFixed(1)} cy=${y.toFixed(1)} r=${R[o[6]]} />`+
      (rk[i]?`<text class=pkspn x=${x.toFixed(1)} y=${(y+3.6).toFixed(1)} text-anchor=middle>${rk[i]}</text>`:'')+'</g>';});
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" width=${W} height=${H} role=img aria-label="新飆股名單位置圖：上名單第幾週和強度">${s}</svg>`;
  const ky=$('#pkspotk'),nm=o=>`<a data-c="${esc(o[0])}" data-co="${esc(o[0])}">${esc(o[1])}</a>`,H2=P.filter(o=>o[6]==='h');
  if(ky)ky.innerHTML=(nb?`照規則買的順序：${P.filter(o=>o[6]==='b').map((o,j)=>`<span><b>${j+1}</b>${nm(o)}</span>`).join('')}`:'這週沒有要買的。')+
    (H2.length?`<span class=pkskh>拿著：${H2.map(nm).join('、')}</span>`:'');
  const tip=$('#pkspottip');if(tip)tip.hidden=true;
  const KN=i=>{const o=P[i];return o[6]==='h'?'拿著':o[6]==='b'?`${X.trial?'照規則會買':`${pkMd(X.buyd)} 開盤買`}（第 ${rk[i]} 個買）`:`等空位（排第 ${qp[i]}，空 ${X.free} 格）`;};
  if(tip&&typeof vzBind==='function')vzBind(box,tip,box.closest('.spotx'),'data-pksp',el=>{const i=+el.dataset.pksp,o=P[i];
    return `<b>${esc(o[1])}</b> <span class=vzs>${esc(o[0])}</span><div>${KN(i)}</div><div>${o[3]<=1?'新上名單':`上名單第 ${o[3]} 週`}・強度 ${f(o[2],0)}</div>`+
      (o[4]?`<div class=vzs>${esc(o[4])}</div>`:'')+`<div class=vzs>點一下打開個股卡</div>`;},()=>{});}
function pkBoomDraw(){pkMineDraw();pkBxDraw();const sd=$('#main .pksd');if(sd&&sd.open)pkSpot();}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('[data-pkmk]');if(!b)return;e.preventDefault();e.stopPropagation();pkMark(b.dataset.c2,b.dataset.n2,b.dataset.pkmk);},true);
function vPkTw(){vPick('tw');}
function vPkUs(){vPick('us');}
let PKR=0,PKW=innerWidth;addEventListener('resize',()=>{clearTimeout(PKR);PKR=setTimeout(()=>{if((S.tab==='tw'||S.tab==='us')&&(innerWidth>=900)!==(PKW>=900))pkCalDraw(S.tab);PKW=innerWidth;if(S.tab==='tw')pkSpot();},200);});
addEventListener('labtheme',()=>{if(S.tab==='tw')pkSpot();});
"""
