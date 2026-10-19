"""景氣頁「大跌後檢查」卡（docs/lab_crash_plan.md 第 4、13～16 節；規格 bottomspec VER 2）。

台股景氣頁、美股景氣頁（四個指數各一份）各一張卡，放在「短線大跌風險」卡下面：
  一句話          現在有沒有進行中的大跌（最近 60 個交易日內的 5 日急跌、還沒結束的「從 60 日高點跌 10%」）；
                  過去急跌隔天收盤買之後的表現；落底訊號的研究結論（VER 2：和固定等 10 天比的判定）
  這一次          進行中的事件：事件前高點、到今天最多跌多少、三個分組＋同組事件之後的表現、落底訊號出現了沒有
  急跌之後        全部事件與各組：60 日後的漲跌、20 天內再跌破低點、中間最多再跌、回到前高；分組比較的判定
  等訊號再買      固定等 10 天（對照，和事件隔天買比）；各訊號：多久出現、再跌破低點的比例與 60 日報酬（和固定等 10 天比）、
                  判定、和事件隔天買比的舊判定（VER 1，參考）；五個市場的判定
  收起            另一種事件、每一次的清單、怎麼算、主要假說
每天建頁只讀研究檔（bottom.load_research）；進行中的事件與訊號每天重算（bottom.now）。只描述過去，不寫買賣指示；用字照專案禁用詞。
"""
from __future__ import annotations

from . import bottomspec as S
from .hotddpage import _d, _e, _nan, ci, pct, ppt, spct

EVN = {"E5": "5 日急跌", "E10": "從 60 日高點跌 10%"}
VCLS = {"better": "strong", "trade": "none", "worse": "weak", "none": "none", "few": "few"}
VSHORT = {"better": "有用", "trade": "有取捨", "worse": "比較差", "none": "看不出", "few": "樣本不足"}
VLONG = {"better": "有用：比{b}少再跌破低點，60 日報酬也不輸", "trade": "比{b}少再跌破低點，但 60 日報酬也比較少",
         "worse": "比{b}差", "none": "看不出差別", "few": "次數太少，不能判定"}


def vlong(k: str, v: str) -> str:
    """判定的完整說法：固定等 10 天和事件隔天買比，訊號和固定等 10 天比（VER 2）。"""
    return VLONG.get(v, VLONG["few"]).format(b="事件隔天就買" if k == S.SIG_BASE else "固定等 10 天")
VMARK = {"better": "✓", "trade": "△", "worse": "✗", "none": "·", "few": "—"}
GV = {"up": "第一組之後較好", "down": "第一組之後較差", "none": "看不出差別", "few": "次數太少，不能判定"}


def gv_text(g: str, v: str) -> str:
    """分組比較的判定，用第一組的名字寫（「底子好之後較好」），不寫「第一組」。"""
    a = S.GROUP_NAMES[g][0]
    return {"up": f"{a}之後較好", "down": f"{a}之後較差"}.get(v, GV.get(v, GV["few"]))
GVCLS = {"up": "strong", "down": "weak", "none": "none", "few": "few"}
GTITLE = {"fund": "底子", "chip": "籌碼", "bub": "泡沫"}
SHORT = {"W10": "固定等 10 天", "C1": "VIX 回落", "C2": "融資減少", "C3": "寬度衝刺", "C4": "新低家數減半",
         "C5": "期貨淨空單減少", "C6": "P/C 回落", "C7": "跟進日", "C8": "90% 上漲日"}
TAG = {"C1": "VIX", "C2": "融資", "C3": "寬度", "C4": "新低", "C5": "期貨", "C6": "P/C", "C7": "跟進", "C8": "90%"}
MKN = {"tw": "台股", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}
LIST_MAX = 20


def sig_def(mk: str, k: str, px: str = "") -> str:
    """規則的白話定義（門檻寫在規格 bottomspec）。"""
    tw = mk == "tw"
    return {
        "W10": "不看訊號，事件後第 10 個交易日收盤買",
        "C1": ("美國 VIX（用前一個美國交易日的收盤）" if tw else "VIX") + f" 比事件以來的最高點低 {S.C1_DROP * 100:g}% 以上",
        "C2": f"上市融資金額比 {S.C2_DAYS} 個交易日前少 {S.C2_DROP * 100:g}% 以上（斷頭、減碼潮）",
        "C3": f"近 {S.C3_WIN} 個交易日上漲家數占比，從 {S.C3_LO * 100:g}% 以下衝到 {S.C3_HI * 100:g}% 以上（月底市值 40 億以上的股票）",
        "C4": f"當天創 250 日新低的家數占比，比事件以來的高峰少一半（高峰至少 {S.C4_FLOOR * 100:g}%）",
        "C5": (f"外資台指期淨空單比事件以來的高峰少 {S.C5_CUT * 100:g}% 以上（高峰至少 1 萬口）" if tw else
               f"大型投機者 S&P 500 期貨淨空單（占未平倉）比事件以來的高峰少 {S.C5_CUT * 100:g}% 以上"
               "（高峰至少 5 個百分點；週資料，晚 4 天）"),
        "C6": "臺指選擇權賣權 ÷ 買權成交量比，事件後先高於、再跌回自己的 20 日平均以下",
        "C7": f"事件以來的最低收盤之後第 {S.C7_GAP} 天起，{px.lstrip() or '指數'}單日漲 {S.C7_UP * 100:g}% 以上、"
              + ("成交金額" if tw else "成交量") + "比前一天大",
        "C8": f"當天上漲家數占上漲＋下跌的 {S.C8_UP * 100:g}% 以上",
    }[k]


def _sp(x, dec: int = 1) -> str:
    """有正負的百分點（不帶單位）：+3.4、−0.6。"""
    if _nan(x):
        return "—"
    r = round(x * 100, dec)
    return ("−" if r < 0 else ("+" if r > 0 else "")) + f"{abs(r):.{dec}f}"


def _n(x) -> str:
    return "—" if _nan(x) else f"{x:,.0f}"


# ── 每天建頁的資料 ─────────────────────────────────────────────────────────

def state(B: dict) -> dict | None:
    """景氣頁的 B（heatcalc.build／heatcalc_us.build）→ 卡片要的資料；研究檔沒有、不是這一版就回 None（不顯示卡片）。
    原始資料沿用景氣頁已經載入的 B["D"]；台股的融資 ÷ 市值（分組用）用 crash.tw_inputs 現算，泡沫等級用 bubble.market_for。"""
    from . import bottom as X
    from . import bubble as BU
    from . import crash as CR
    from . import heatdata as HD
    from . import heatpage as HP
    mk = "tw" if HP.MK["tab"] == "tw" else B.get("idx")
    R = X.load_research()
    if mk not in S.MARKETS or not R or mk not in (R.get("markets") or {}) or not B.get("cal") or B.get("D") is None:
        return None
    BX = {mk: BU.market_for(mk, B["D"])}
    if mk == "tw":
        D = dict(B["D"])
        for n in ("twcap", "twmgn", "taiex90"):
            if n not in D:
                D[n] = HD.load(n)
        D["_tsmc"] = CR._tsmc_month(None)
        I = X.inputs_tw(B=B, IT=CR.tw_inputs(D=D, B=B, BX=BX), BX=BX)
    else:
        vol = HD.load(f"us_vol_{mk}") if "C7" in S.SIG_MK[mk] else None
        I = X.inputs_us(mk, B, CR.us_inputs(mk, Bu=B, BX=BX), vol, BX)
    if not I["cal"]:
        return None
    return {"mk": mk, "px": HP.MK.get("px") or "", "now": X.now(I), "R": R["markets"][mk],
            "all": R["markets"], "primary": R.get("primary") or {}}


def _ev_main(C: dict) -> str:
    """主要看哪一種事件：進行中的事件是「只有跌 10%」就看 E10，其他看 E5。"""
    act = C["now"].get("active") or []
    return "E10" if act and all(a["ev"] == "E10" for a in act) else "E5"


def _rules(C: dict, ev: str) -> dict:
    return ((C["R"].get("ev") or {}).get(ev) or {}).get("rules") or {}


def lead(C: dict) -> list[str]:
    """三句：現在有沒有大跌、過去急跌隔天買之後、落底訊號的研究結論。全部由研究檔與今天的狀態算。"""
    N, R, mk = C["now"], C["R"], C["mk"]
    nm = C["px"].lstrip()                            # 美股指數名前後帶空白（「S&P 500 離…」），台股「加權指數」沒有
    out = []
    act = N.get("active") or []
    if act:
        parts = []
        for a in act:
            if a["ev"] == "E5":
                t = f'{_d(a["t"])} 出現 5 日急跌（5 日跌 {pct(-a["depth"])}）'
                if a.get("also") == "E10":
                    t += "，同一天也從 60 日高點跌了 10% 以上"
            else:
                t = f'{_d(a["t"])} 起從 60 日高點跌 10% 以上'
            parts.append(t)
        a = act[0]
        low = "，今天就是這一波最低收盤" if a["low"] == N["d"] else f'（最低在 {_d(a["low"])}，{spct(a["lowdd"])}）'
        out.append(f'{nm.rstrip()} {"；".join(parts)}：現在比 {_d(a["p"])} 的高點低 {pct(-a["nowdd"])}{low}，'
                   f'事件後第 {a["days"]} 個交易日。')
    else:
        last = N.get("last") or {}
        out.append(f'現在沒有大跌：{nm}離 60 日高點 {spct(N.get("dd60"))}（跌 10% 才算），最近 60 個交易日沒有 5 日急跌'
                   f'（5 日跌 {S.E5_TH[mk] * 100:g}% 以上）。最近一次：5 日急跌 {_d(last.get("E5"))}、'
                   f'從 60 日高點跌 10% {_d(last.get("E10"))}。')
    ev = _ev_main(C)
    E = (R.get("ev") or {}).get(ev) or {}
    A = E.get("all") or {}
    if E.get("n"):
        out.append(f'{(R.get("start") or "")[:4]} 年起的 {E["n"]} 次{" " if ev == "E5" else ""}{EVN[ev]}，事件隔天收盤買：'
                   '20 個交易日內再跌破這一波低點的有 '
                   f'{pct((A.get("nl") or {}).get("rate"), 0)}；60 個交易日後平均 {spct((A.get("r60") or {}).get("mean"))}'
                   f'（中位數 {spct((A.get("r60") or {}).get("med"))}），{pct((A.get("r60") or {}).get("up"), 0)} 上漲。')
    rs = _rules(C, ev)
    w = rs.get(S.SIG_BASE) or {}
    if w.get("n"):
        sig = [k for k in S.SIG_MK[mk] if ((rs.get(k) or {}).get("w10") or {}).get("n")]
        good = [k for k in sig if rs[k].get("v") == "better"]
        t = (f'等落底訊號再買，改和固定等 10 天比（不看訊號、固定等 10 天就從 {pct(w.get("nl_b1"), 0)} 降到 '
             f'{pct(w.get("nl_rule"), 0)}）。有用的條件：比固定等 10 天少再跌破低點，而且 60 日報酬全部與前後兩半都不輸；'
             + ("、".join(SHORT[k] for k in good) + "符合。" if good else "沒有一個訊號符合。"))
        nl = [k for k in sig if k not in good and rs[k]["w10"].get("nl_dir") == "down"]
        ru = [k for k in sig if k not in good and k not in nl and rs[k]["w10"].get("r_dir") == "up"]
        parts = []
        if nl:
            tr = [k for k in nl if rs[k].get("v") == "trade"]
            parts.append("、".join(SHORT[k] for k in nl) + "再跌破低點少 "
                         + "、".join(f'{abs(rs[k]["w10"]["nl_d"]) * 100:.0f}' for k in nl) + " 個百分點，但 60 日報酬那一條沒過"
                         + ("（" + "、".join(SHORT[k] for k in tr) + "的 60 日報酬還顯著比較少）" if tr else ""))
        if ru:
            parts.append("、".join(SHORT[k] for k in ru) + "的 60 日報酬多 "
                         + "、".join(f'{rs[k]["w10"]["r_d"] * 100:.1f}' for k in ru) + " 個百分點，但再跌破低點沒有比較少")
        if parts:
            t += "；".join(parts) + "。"
        elif not good:
            t += "也沒有一個訊號明顯比固定等 10 天少再跌破低點。"
        out.append(t)
    return out


# ── HTML ─────────────────────────────────────────────────────────────────

def _gtext(g: str, v, gv: dict) -> str:
    """這一次在這個分組的哪一組（含當天的值）。"""
    if v is None:
        return "沒有資料"
    nm = S.GROUP_NAMES[g][0 if v == 1 else 1]
    if g == "fund":
        return f'{nm}（基本面 {_n(gv.get("fund"))}，3 個月前 {_n(gv.get("fund0"))}）'
    if g == "chip":
        return f'{nm}（事件前 20 天最高 {_n(gv.get("chip"))}）'
    lv = gv.get("bub")
    return nm + (f"（泡沫等級 {lv}）" if lv is not None else "")


def _gstat(d: dict | None) -> str:
    """一組事件之後：次數、60 日後平均（中位數）、上漲比例、20 天內再跌破低點。"""
    d = d or {}
    r = d.get("r60") or {}
    if not r.get("n"):
        return "沒有"
    return (f'{r["n"]} 次：60 日後平均 {spct(r.get("mean"))}（中位數 {spct(r.get("med"))}），{pct(r.get("up"), 0)} 上漲；'
            f'20 天內再跌破低點 {pct((d.get("nl") or {}).get("rate"), 0)}')


def now_html(C: dict) -> str:
    """進行中的事件：事件前高點、到今天最多跌多少、分組＋同組過去、落底訊號出現了沒有。"""
    N, mk = C["now"], C["mk"]
    act = N.get("active") or []
    if not act:
        return ""
    blocks = []
    for a in act:
        ev = a["ev"]
        E = (C["R"].get("ev") or {}).get(ev) or {}
        title = f'{_d(a["t"])} {EVN[ev]}' + ("（同一天也從 60 日高點跌 10%）" if a.get("also") == "E10" else "")
        depth = f'5 日跌 {pct(-a["depth"])}' if ev == "E5" else f'離 60 日高點 {spct(a["depth"])}'
        grid = (f'<dl class="xjg"><div><dt>事件那天</dt><dd>{_e(depth)}</dd></div>'
                f'<div><dt>事件前高點</dt><dd>{_e(_d(a["p"]))}<small>{_n(a["ppx"])}</small></dd></div>'
                f'<div><dt>到今天最多跌</dt><dd>{_e(spct(a["lowdd"]))}<small>{_e(_d(a["low"]))}</small></dd></div>'
                f'<div><dt>今天</dt><dd>{_e(spct(a["nowdd"]))}<small>事件後第 {a["days"]} 個交易日</small></dd></div></dl>')
        grows = []
        for g in S.GROUPS:
            v = (a.get("g") or {}).get(g)
            st = (E.get("groups") or {}).get(g) or {}
            same = st.get("g1" if v == 1 else "g0") if v is not None else None
            other = st.get("g0" if v == 1 else "g1") if v is not None else None
            vt = st.get("v") or "few"
            grows.append(f'<tr><td class="l"><b>{_e(GTITLE[g])}</b><span class="xjsub">{_e(_gtext(g, v, a.get("gv") or {}))}</span></td>'
                         f'<td class="l" data-h="過去同一組">{_e(_gstat(same)) if same else "—"}</td>'
                         f'<td class="l" data-h="另一組">{_e(_gstat(other)) if other else "—"}</td>'
                         f'<td data-h="兩組比"><span class="vt {GVCLS[vt]}">{_e(gv_text(g, vt))}</span></td></tr>')
        gtab = ('<div class="tw"><table class="xjgt"><tr><th class="l">分組</th><th class="l">過去同一組</th>'
                f'<th class="l">另一組</th><th>兩組比（60 日後）</th></tr>{"".join(grows)}</table></div>')
        rs = (E.get("rules") or {})
        srows = []
        for k in ("W10",) + tuple(S.SIG_MK[mk]):
            s = a.get("w10") if k == "W10" else (a.get("sig") or {}).get(k) or {}
            stt = s.get("st")
            if stt == "on":
                st_txt, cls = (f'已出現 {_d(s.get("d"))}' + (f'（第 {s["after"]} 天）' if s.get("after") else "")), "xjon"
            elif stt == "wait":
                st_txt, cls = f'還沒（還有 {s.get("left")} 個交易日）', "xjwait"
            elif stt == "none":
                st_txt, cls = "60 個交易日內沒有出現", "xjno"
            else:
                st_txt, cls = "沒有資料", "xjno"
            r = rs.get(k) or {}
            vt = r.get("v") or "few"
            c, bk, bn = (r, "b1", "隔天買") if k == S.SIG_BASE else (r.get("w10") or {}, "w10", "等 10 天")
            hist = ("—" if not c.get("n") else
                    f'過去 {c["n"]} 次：再跌破低點 {bn} {pct(c.get(f"nl_{bk}"), 0)} → 這樣買 {pct(c.get("nl_rule"), 0)}，'
                    f'60 日後 {spct(c.get(f"r_{bk}"))} → {spct(c.get("r_rule"))}')
            srows.append(f'<tr class="{cls}"><td class="l"><b>{_e(SHORT[k])}</b><span class="xjsub">{_e(sig_def(mk, k, C["px"]))}</span></td>'
                         f'<td class="l" data-h="這一次">{_e(st_txt)}</td><td class="l" data-h="過去（對照 → 這樣買）">{_e(hist)}</td>'
                         f'<td data-h="判定" title="{_e(vlong(k, vt))}"><span class="vt {VCLS[vt]}">{_e(VSHORT[vt])}</span></td></tr>')
        stab = ('<div class="tw"><table class="xjst"><tr><th class="l">落底訊號</th><th class="l">這一次</th>'
                f'<th class="l">過去（對照 → 這樣買）</th><th>判定</th></tr>{"".join(srows)}</table></div>'
                '<p class="note">對照：固定等 10 天和事件隔天買比；落底訊號都和固定等 10 天比。</p>')
        blocks.append(f'<div class="xjnow"><h3 class="xjh3">這一次：{_e(title)}</h3>{grid}'
                      f'<h4 class="xjh4">屬於哪一組</h4>{gtab}<h4 class="xjh4">落底訊號出現了沒有</h4>{stab}</div>')
    return "".join(blocks)


def _drow(label: str, d: dict, cls: str = "") -> str:
    r60, r20, r120 = d.get("r60") or {}, d.get("r20") or {}, d.get("r120") or {}
    rec = d.get("rec") or {}
    med = rec.get("med")
    rtxt = ("超過 250 天" if rec.get("gt") else (f"{med:.0f} 天" if med is not None else "—"))
    return (f'<tr class="{cls}"><td class="l">{_e(label)}<span class="xjcn">{d.get("n") or 0} 次</span></td>'
            f'<td data-h="次數" class="xjhm">{d.get("n") or 0}</td>'
            f'<td data-h="60 日後"><b>{spct(r60.get("mean"))}</b><small>中位數 {spct(r60.get("med"))}</small></td>'
            f'<td data-h="上漲比例">{pct(r60.get("up"), 0)}<small>20 日 {pct(r20.get("up"), 0)}・120 日 {pct(r120.get("up"), 0)}</small></td>'
            f'<td data-h="20 天內再跌破低點">{pct((d.get("nl") or {}).get("rate"), 0)}</td>'
            f'<td data-h="中間最多再跌">{pct((d.get("mae") or {}).get("med"))}<small>最差 {pct((d.get("mae") or {}).get("max"), 0)}</small></td>'
            f'<td data-h="回到前高">{pct((rec.get("120") or {}).get("share"), 0)}<small>中位數 {rtxt}</small></td></tr>')


def study_table(C: dict, ev: str) -> str:
    """全部事件與各組之後的表現（事件隔天收盤買）；分組比較的判定。"""
    E = (C["R"].get("ev") or {}).get(ev) or {}
    if not E.get("n"):
        return '<p class="note">沒有這種事件。</p>'
    rows = [_drow("全部", E.get("all") or {}, "xjall")]
    notes = []
    for g in S.GROUPS:
        st = (E.get("groups") or {}).get(g) or {}
        a, b = S.GROUP_NAMES[g]
        rows.append(_drow(a, st.get("g1") or {}, "xjg1"))
        rows.append(_drow(b, st.get("g0") or {}, "xjg0"))
        vt = st.get("v") or "few"
        dd = (f'60 日後平均差 {ppt(st.get("d"))}（95% 區間 {ci(st.get("lo"), st.get("hi"))}；前後兩半 {_sp(st.get("h1"))}／{_sp(st.get("h2"))}）'
              if st.get("d") is not None else "")
        notes.append(f'<li><b>{_e(a)} vs {_e(b)}</b>：<span class="vt {GVCLS[vt]}">{_e(gv_text(g, vt))}</span>{_e(dd)}</li>')
    head = ('<tr><th class="l">事件</th><th>次數</th><th>60 日後<br>平均（中位數）</th><th>上漲比例</th><th>20 天內<br>再跌破低點</th>'
            '<th>中間最多再跌<br>（中位數）</th><th>120 天內<br>回到前高</th></tr>')
    return (f'<div class="tw"><table class="xjdt">{head}{"".join(rows)}</table></div>'
            f'<ul class="xjul">{"".join(notes)}</ul>'
            '<p class="note">都從事件隔天收盤買起算。再跌破低點＝買進之後 20 個交易日內，有一天收盤低於這一波（事件前高點到買進那天）的最低收盤；'
            '中間最多再跌＝之後 60 個交易日裡比買進價最多低多少；回到前高＝事件後 120 個交易日內收盤回到事件前高點的比例（中位數＝要幾個交易日）。'
            '最近幾次還沒走完 60、120 個交易日的，不算進那一欄。'
            f'兩組比的區間用 {S.BLOCK} 個交易日一塊重抽 {S.BOOT_N:,} 次；任一組不到 {S.MIN_N} 次不判定。</p>')


def base_line(C: dict, ev: str) -> str:
    """對照：固定等 10 天和事件隔天買比（判定照 VER 1）。"""
    w = _rules(C, ev).get(S.SIG_BASE) or {}
    if not w.get("n"):
        return ""
    vt = w.get("v") or "few"
    return (f'<p class="xjbase"><b>對照：固定等 10 天</b>（{_e(sig_def(C["mk"], S.SIG_BASE))}），和事件隔天買比（{w["n"]} 次）：'
            f'20 天內再跌破低點 {pct(w.get("nl_b1"), 0)} → <b>{pct(w.get("nl_rule"), 0)}</b>'
            f'（差 {_sp(w.get("nl_d"), 0)} 個百分點，95% 區間 {_sp(w.get("nl_lo"), 0)}～{_sp(w.get("nl_hi"), 0)}）；'
            f'60 日後 {spct(w.get("r_b1"))} → <b>{spct(w.get("r_rule"))}</b>；'
            f'<span class="vt {VCLS[vt]}" title="{_e(vlong(S.SIG_BASE, vt))}">{_e(VSHORT[vt])}</span></p>')


def rule_table(C: dict, ev: str) -> str:
    """各訊號和固定等 10 天比：多久出現、再跌破低點的比例與 60 日報酬（差、區間、前後兩半）、判定；和事件隔天買比（VER 1，參考）。"""
    mk = C["mk"]
    rs = _rules(C, ev)
    rows = []
    for k in S.SIG_MK[mk]:
        r = rs.get(k) or {}
        c = r.get("w10") or {}
        vt, v1 = r.get("v") or "few", r.get("v1") or "few"
        if r.get("seen"):
            dl = r.get("delay")
            when = f'{pct(r.get("cov"), 0)} 的事件有出現' + (f'<small>中位數第 {dl:.0f} 天</small>' if dl is not None else "")
        else:
            when = "—"
        if c.get("n"):
            nl = (f'{pct(c.get("nl_w10"), 0)} → <b>{pct(c.get("nl_rule"), 0)}</b>'
                  f'<small>差 {_sp(c.get("nl_d"), 0)}（{_sp(c.get("nl_lo"), 0)}～{_sp(c.get("nl_hi"), 0)}）</small>'
                  f'<small>前後兩半 {_sp(c.get("nl_h1"), 0)}／{_sp(c.get("nl_h2"), 0)}</small>')
            rr = (f'{spct(c.get("r_w10"))} → <b>{spct(c.get("r_rule"))}</b>'
                  f'<small>差 {_sp(c.get("r_d"))}（{_sp(c.get("r_lo"))}～{_sp(c.get("r_hi"))}）</small>'
                  f'<small>前後兩半 {_sp(c.get("r_h1"))}／{_sp(c.get("r_h2"))}</small>')
        else:
            nl = rr = "—"
        old = (f'{_e(VSHORT[v1])}<small>再跌破低點 {pct(r.get("nl_b1"), 0)} → {pct(r.get("nl_rule"), 0)}</small>'
               if r.get("n") else "—")
        tip = f'{c.get("n") or 0} 次（{c.get("ep") or 0} 段）'
        rows.append(f'<tr title="{_e(tip)}"><td class="l"><b>{_e(SHORT[k])}</b><span class="xjcn">{c.get("n") or 0} 次</span>'
                    f'<span class="xjsub">{_e(sig_def(mk, k, C["px"]))}</span></td>'
                    f'<td data-h="多久出現">{when}</td><td data-h="20 天內再跌破低點（等 10 天 → 這樣買）">{nl}</td>'
                    f'<td data-h="60 日後（等 10 天 → 這樣買）">{rr}</td>'
                    f'<td data-h="判定" title="{_e(vlong(k, vt))}"><span class="vt {VCLS[vt]}">{_e(VSHORT[vt])}</span></td>'
                    f'<td data-h="和隔天買比（舊判定）" class="xjv1">{old}</td></tr>')
    head = ('<tr><th class="l">落底訊號</th><th>多久出現</th><th>20 天內再跌破低點<br>等 10 天 → 這樣買</th>'
            '<th>60 日後<br>等 10 天 → 這樣買</th><th>判定</th><th>和隔天買比<br>（舊判定）</th></tr>')
    return (base_line(C, ev)
            + f'<div class="tw"><table class="xjrt">{head}{"".join(rows)}</table></div>'
            '<p class="note">每一列只比「這個訊號有出現的事件」：同一個事件，固定等 10 天（第 10 個交易日收盤買）和等這個訊號（出現的隔天收盤買）'
            '各算一次，所以每一列的「等 10 天」不一樣。訊號要在事件後 60 個交易日內出現才算。'
            '判定（事前寫定）：再跌破低點的比例比固定等 10 天少（區間不含 0、前後兩半都少、多重比較校正後 q ≤ 0.10），'
            '而且 60 日報酬不比固定等 10 天少（全部與前後兩半）＝有用；再跌破低點比較少但 60 日報酬顯著比較少＝有取捨；'
            f'不到 {S.MIN_N} 次或不到 {S.MIN_EP} 段（相隔 {S.EP_GAP} 個交易日以上算不同段）不判定。'
            '訊號比第 10 天晚出現時（看「多久出現」），再跌破低點比較少仍有一部分是晚買的效果。'
            '「和隔天買比」是第一版的比較：晚買本身就比較不容易再跌破低點，和隔天買比對訊號偏寬，只當參考。</p>')


def five_html(C: dict, ev: str) -> str:
    """每個規則在五個市場的判定（同一種事件）。"""
    A = C.get("all") or {}
    mks = [m for m in S.MARKETS if m in A and (C["mk"] == "tw" or m != "tw")]   # 美股頁只比四個美股指數
    rows = []
    for k in S.RULES:
        cells, vs = [], []
        for m in mks:
            if k != "W10" and k not in S.SIG_MK[m]:
                cells.append('<td class="xjna">不算</td>')
                continue
            r = ((((A.get(m) or {}).get("ev") or {}).get(ev) or {}).get("rules") or {}).get(k) or {}
            v = r.get("v") or "few"
            vs.append(v)
            cells.append(f'<td class="xjv{v}" title="{_e(vlong(k, v))}">{VMARK[v]}<small>{_e(VSHORT[v])}</small></td>')
        nf = [v for v in vs if v != "few"]
        agree = "一致" if len(nf) >= 2 and len(set(nf)) == 1 else ("—" if len(nf) < 2 else "不一致")
        rows.append(f'<tr><td class="l">{_e(SHORT[k])}</td>' + "".join(cells) + f'<td class="xjag">{agree}</td></tr>')
    head = ('<tr><th class="l">怎麼買</th>' + "".join(f"<th>{_e(MKN[m])}</th>" for m in mks) + "<th>方向</th></tr>")
    na = "美股沒有融資、寬度、新低家數、P/C；費半沒有成交量" if C["mk"] == "tw" else "費半沒有成交量"
    return (f'<div class="tw"><table class="xjft">{head}{"".join(rows)}</table></div>'
            f'<p class="note">{"、".join(f"{VMARK[v]} {VSHORT[v]}" for v in ("better", "trade", "worse", "none", "few"))}；'
            f'固定等 10 天這一列和事件隔天買比，落底訊號都和固定等 10 天比；'
            f'方向一致＝不是樣本不足的市場至少 2 個、判定都一樣。不算＝那個市場沒有這種資料（{na}）。</p>')


def list_html(C: dict, ev: str) -> str:
    """每一次事件（最近 LIST_MAX 次）。"""
    E = (C["R"].get("ev") or {}).get(ev) or {}
    L = list(reversed(E.get("list") or []))
    if not L:
        return ""
    rows = []
    for r in L[:LIST_MAX]:
        g = r.get("g") or {}
        tags = []
        if g.get("fund") is not None:
            tags.append("底子好" if g["fund"] else "底子轉弱")
        if g.get("chip"):
            tags.append("籌碼過熱")
        if g.get("bub"):
            tags.append("漲勢過熱")
        sig = []
        for k, v in (r.get("sig") or {}).items():
            if v == "na":
                continue
            sig.append(f'{TAG.get(k, k)} {"—" if v is None else ("…" if v == "open" else v)}')
        rec = r.get("rec")
        rtxt = "還沒回到" if rec is None else f"{rec} 天"
        depth = pct(-r["depth"]) if ev == "E5" else spct(r.get("dd"))
        rows.append(f'<tr><td class="l">{_e(_d(r["d"]))}<small>{_e("・".join(tags))}</small></td>'
                    f'<td data-h="{"5 日跌" if ev == "E5" else "離高點"}">{_e(depth)}</td>'
                    f'<td data-h="60 日後">{_e(spct(r.get("r60")))}</td>'
                    f'<td data-h="再跌破低點">{"—" if r.get("nl") is None else ("是" if r["nl"] else "否")}</td>'
                    f'<td data-h="最多再跌">{_e(pct(r.get("mae")))}</td><td data-h="回到前高">{_e(rtxt)}</td>'
                    f'<td class="l" data-h="訊號（第幾天出現）"><small>{_e("　".join(sig)) or "—"}</small></td></tr>')
    head = (f'<tr><th class="l">事件日</th><th>{"5 日跌" if ev == "E5" else "離高點"}</th><th>隔天買<br>60 日後</th><th>20 天內<br>再跌破低點</th>'
            '<th>之後最多<br>再跌</th><th>回到前高</th><th class="l">訊號（事件後第幾天出現）</th></tr>')
    more = f"（共 {len(L)} 次，列最近 {LIST_MAX} 次）" if len(L) > LIST_MAX else f"（{len(L)} 次）"
    return (f'<details class="xjmore"><summary>每一次 {_e(EVN[ev])}{_e(more)}</summary>'
            f'<div class="tw"><table class="xjlt">{head}{"".join(rows)}</table></div>'
            '<p class="note">訊號欄：事件後第幾個交易日第一次出現；— ＝ 60 個交易日內沒有出現；… ＝ 還沒滿 60 個交易日；沒有資料的訊號不列。</p></details>')


def primary_html(C: dict) -> str:
    P = C.get("primary") or {}
    n_ok = sum(1 for h in S.PRIMARY if (P.get(h) or {}).get("ok"))
    li = []
    tw = C["mk"] == "tw"
    nmk = dict(MKN, tw="台灣") if not tw else MKN
    for h, sp in S.PRIMARY.items():
        r = P.get(h) or {}
        if r.get("few") or r.get("d") is None:
            res = "樣本不足"
        else:
            nn = "；".join(f'{nmk[m]} {a}／{b} 次' for m, (a, b) in (r.get("n") or {}).items())
            res = (f'{nn}；差 {_sp(r["d"] / 100, 2)} 個標準差（95% 區間 {_sp(r["lo"] / 100, 2)}～{_sp(r["hi"] / 100, 2)}），'
                   f'前後兩半 {_sp(r.get("h1") / 100, 2)}／{_sp(r.get("h2") / 100, 2)}，Holm 校正後 p＝{r["padj"]:.3f}，'
                   f'{"成立" if r.get("ok") else "不成立"}')
        txt = sp["text"] if tw else sp["text"].replace("（台股＋S&P 500）", "（台美合併）")
        li.append(f'<li><b>{h}</b> {_e(txt)}：{_e(res)}</li>')
    pool = "台股＋S&amp;P 500 合併" if tw else "台美合併：S&amp;P 500 和台灣的急跌一起看"
    return (f'<p class="xjmh"><b>事前寫定的 {len(S.PRIMARY)} 個主要假說</b>（{pool}；60 日報酬除以「該市場日報酬標準差 × √60」'
            f'換成同一個單位；Holm 校正、單尾）：{n_ok} 個成立。</p><ul class="xjpl">{"".join(li)}</ul>')


def method_html(C: dict) -> str:
    mk = C["mk"]
    lim = ("加權指數是價格指數（不含息），從 1990 年起；分組與訊號的資料各有起點（融資 2001、P/C 2002、廣度 2013、外資期貨 2018）"
           if mk == "tw" else f'{C["px"].lstrip()}是價格指數（不含股利）；VIX 從 1990 年起、期貨部位從 1986 年起')
    n5 = (((C["R"].get("ev") or {}).get("E5") or {}).get("n")) or 0
    return ('<div class="xjmh">'
            f'<p><b>事件</b>：5 日急跌＝收盤比 5 個交易日前低 {S.E5_TH[mk] * 100:g}% 以上（'
            + ("美股各指數換算成和台股 2001 年起一樣常見的跌幅" if mk == "tw" else
               "、".join(f"{MKN[m]} {S.E5_TH[m] * 100:g}%" for m in S.MARKETS if m != "tw") + "，換算成一樣常見")
            + '；'
            f'之後 {S.E5_GAP} 個交易日內不重複算）；從 60 日高點跌 10%＝收盤比近 60 個交易日最高收盤低 10% 以上的第一天，'
            '回到只低 5% 以內才算這一段結束。</p>'
            '<p><b>分組（事件那天就知道）</b>：底子好＝基本面熱度 ≥ 50 而且不低於 3 個月前；籌碼過熱＝事件前 20 個交易日'
            + ("融資 ÷ 上市市值" if mk == "tw" else "家計部門證券融資年增率")
            + ' 有一天 ≥ 80；漲勢過熱＝泡沫頁的泡沫等級 ≥ 2。</p>'
            '<p><b>怎麼比</b>：事件、訊號都要收盤後才確定，所以一律「隔一個交易日收盤買」（事件隔天、訊號隔天；固定等 10 天＝第 10 天收盤）。'
            '同一個事件比兩種買法：固定等 10 天和事件隔天買比，落底訊號和固定等 10 天比；'
            f'差的 95% 區間用 {S.BLOCK} 個交易日一塊環狀重抽 {S.BOOT_N:,} 次。</p>'
            f'<p><b>限制</b>：{_e(lim)}；事件少（5 日急跌 {n5} 次），多數比較只能描述。'
            '規格在看結果之前寫定（bottomspec VER 1）；第二版（VER 2）是看過第一版結果之後改的：第一版訊號和事件隔天買比，'
            '但晚買本身就比較不容易再跌破低點，判定對訊號偏寬，所以改和固定等 10 天比，其他照舊。'
            '訊號比第 10 天晚出現時，仍有一部分是晚買的效果。規劃文件 docs/lab_crash_plan.md 第 13、14、16 節。</p></div>')


def card(C: dict | None) -> str:
    """整張卡；C＝state() 的結果（None＝研究檔沒有，不顯示）。"""
    if not C:
        return ""
    from .heatpage import _md
    ls = lead(C)
    lead_html = f'<p class="xjl">{_e(ls[0])}</p>' + "".join(f'<p class="xjl2">{_e(s)}</p>' for s in ls[1:])
    ev = _ev_main(C)
    other = "E10" if ev == "E5" else "E5"
    act = bool(C["now"].get("active"))
    body = (now_html(C)
            + f'<h3 class="xjh3">{_e(EVN[ev])}之後<span class="sub">事件隔天收盤買，全部與各組</span></h3>{study_table(C, ev)}'
            + f'<h3 class="xjh3">等落底訊號再買<span class="sub">{_e(EVN[ev])}；和固定等 10 天比</span></h3>'
            + rule_table(C, ev)
            + f'<details class="xjmore"><summary>{"五個市場" if C["mk"] == "tw" else "四個美股指數"}的判定（{_e(EVN[ev])}）</summary>'
            + f'{five_html(C, ev)}</details>'
            + list_html(C, ev)
            + f'<details class="xjmore"><summary>{_e(EVN[other])}的結果</summary>'
            + f'<h3 class="xjh3">{_e(EVN[other])}之後</h3>{study_table(C, other)}'
            + f'<h3 class="xjh3">等落底訊號再買</h3>{rule_table(C, other)}{five_html(C, other)}</details>'
            + list_html(C, other)
            + f'<details class="xjmore"><summary>怎麼算、主要假說</summary>{method_html(C)}{primary_html(C)}</details>')
    if not act:                                      # 沒有進行中的大跌：研究結果收起來
        body = f'<details class="xjmore xjres"><summary>研究結果（急跌之後、落底訊號、每一次）</summary>{body}</details>'
    return (f'<section class="sec xjsec" id="bottom"><div class="card xjc">'
            f'<div class="khd"><h2>大跌後檢查</h2><span class="kn">急跌之後・資料到 {_e(_md(C["now"].get("d")))}</span></div>'
            f'{lead_html}'
            '<p class="ksub">急跌之後，隔天就買、固定等 10 天、或等落底訊號出現再買，過去各是什麼結果。只描述過去，不是買賣指示。</p>'
            f'{body}</div></section>')


CSS = (
    ".xjc{padding:12px 14px;min-width:0}"
    ".xjl{font-size:15px;font-weight:700;margin:8px 0 4px;line-height:1.6}"
    ".xjl2{font-size:13.5px;color:var(--ink2);margin:0 0 4px;line-height:1.65}"
    ".xjh3{font-size:15px;margin:16px 0 4px}"
    ".xjh4{font-size:13.5px;margin:12px 0 4px;color:var(--ink2)}"
    ".xjmh,.xjmh p{font-size:12.5px;color:var(--ink2);line-height:1.7;margin:6px 0}"
    ".xjsub{display:block;font-size:11px;font-weight:400;color:var(--mut);line-height:1.45}"
    ".xjnow{border:1px solid var(--line2);border-radius:12px;padding:8px 12px;margin:10px 0;background:var(--card2)}"
    ".xjg{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px 10px;margin:6px 0}"
    ".xjg div{min-width:0}.xjg dt{font-size:11px;color:var(--mut)}.xjg dd{margin:0;font-weight:700;font-size:14px}"
    ".xjg dd small{display:block;font-weight:400;font-size:11px;color:var(--mut)}"
    "table.xjgt,table.xjst,table.xjdt,table.xjrt,table.xjft,table.xjlt{font-size:12.5px}"
    "table.xjgt th,table.xjgt td,table.xjst th,table.xjst td,table.xjdt th,table.xjdt td,table.xjrt th,table.xjrt td,"
    "table.xjft th,table.xjft td,table.xjlt th,table.xjlt td{padding:5px 6px;text-align:right;vertical-align:top}"
    "table.xjgt .l,table.xjst .l,table.xjdt .l,table.xjrt .l,table.xjft .l,table.xjlt .l{text-align:left;white-space:normal}"
    "table.xjgt td.l,table.xjst td.l,table.xjrt td.l{min-width:10em}"
    "table.xjrt td,table.xjdt td small,table.xjlt td small{white-space:normal}"
    "table.xjdt small,table.xjrt small,table.xjlt small,table.xjft small{display:block;font-size:10.5px;color:var(--mut)}"
    "table.xjdt td b,table.xjrt td b{font-variant-numeric:tabular-nums}"
    "tr.xjall td{font-weight:700;background:var(--card2)}"
    "tr.xjg0 td{border-bottom:1px solid var(--line2)}"
    "tr.xjon td.l b{color:var(--t0)}tr.xjno td{color:var(--mut)}"
    ".xjul{font-size:12.5px;color:var(--ink2);line-height:1.7;padding-left:1.2em;margin:4px 0}"
    ".xjul .vt{margin:0 6px 0 4px}"
    "table.xjft td{text-align:center}table.xjft td small{font-size:10px}"
    "td.xjvbetter{color:var(--t0);font-weight:700}td.xjvworse{color:var(--t4);font-weight:700}"
    "td.xjvnone,td.xjvfew,td.xjna,td.xjag{color:var(--mut)}td.xjvtrade{color:var(--t3);font-weight:700}"
    ".xjmore{margin-top:12px}"
    ".xjmore>summary{cursor:pointer;font-size:13px;color:var(--acc);padding:8px 0 2px;border-top:1px solid var(--line)}"
    ".xjmore[open]>summary{margin-bottom:8px}"
    ".xjres>summary{font-size:13.5px;font-weight:600}"
    ".xjpl{font-size:12.5px;color:var(--ink2);line-height:1.7;padding-left:1.2em;margin:4px 0}"
    ".xjcn{display:none;font-size:10.5px;font-weight:400;color:var(--mut);margin-left:6px}"
    ".xjbase{font-size:12.5px;color:var(--ink2);line-height:1.7;margin:6px 0 8px}.xjbase .vt{margin-left:4px}"
    "table.xjrt td.xjv1{color:var(--mut)}table.xjrt td.l{width:30%}"
    "table.xjrt td small,table.xjrt .vt{white-space:nowrap}"
    "@media (max-width:640px){"
    ".xjg{grid-template-columns:repeat(2,minmax(0,1fr))}"
    "table.xjgt,table.xjgt tbody,table.xjst,table.xjst tbody,table.xjdt,table.xjdt tbody,table.xjrt,table.xjrt tbody,"
    "table.xjlt,table.xjlt tbody{display:block}"
    "table.xjgt tr:first-child,table.xjst tr:first-child,table.xjdt tr:first-child,table.xjrt tr:first-child,"
    "table.xjlt tr:first-child{display:none}"
    "table.xjgt tr,table.xjst tr,table.xjdt tr,table.xjrt tr,table.xjlt tr{display:grid;gap:3px 8px;padding:8px 2px;"
    "border-bottom:1px solid var(--line)}"
    "table.xjgt tr,table.xjst tr{grid-template-columns:minmax(0,1fr)}"
    "table.xjdt tr{grid-template-columns:repeat(3,minmax(0,1fr))}"
    "table.xjrt tr{grid-template-columns:repeat(2,minmax(0,1fr))}"
    "table.xjlt tr{grid-template-columns:repeat(3,minmax(0,1fr))}"
    "table.xjgt td,table.xjst td,table.xjdt td,table.xjrt td,table.xjlt td{display:block;border:0;padding:0;text-align:left;"
    "font-size:12px;min-width:0!important;white-space:normal}"
    "table.xjdt td.l,table.xjrt td.l,table.xjlt td.l{grid-column:1/-1}"
    "table.xjgt td[data-h]::before,table.xjst td[data-h]::before,table.xjdt td[data-h]::before,table.xjrt td[data-h]::before,"
    "table.xjlt td[data-h]::before{content:attr(data-h);display:block;color:var(--mut);font-size:10.5px}"
    "table.xjdt td.xjhm{display:none}table.xjdt .xjcn,table.xjrt .xjcn{display:inline}"
    "table.xjrt td.l{width:auto}table.xjrt td small{white-space:normal}"
    "table.xjft{font-size:11px}table.xjft th,table.xjft td{padding:4px 2px}table.xjft td small{display:none}"
    "}"
)
