"""景氣頁「反向檢查：籌碼連續過熱、技術面轉空」卡（docs/lab_hotdd_plan.md 第 7.5.9、9 節；規格 hotchspec VER 1）。

台股景氣頁、美股景氣頁（四個指數各一份）各一張卡，放在「過熱之後 3 個月的最大回撤」卡下面：
  一句話        籌碼（現在過熱的項目與對應狀態的結果）、技術面（轉空之後的判定、最近 3 個月的轉空訊號）、大跌時跌破季線的位置
  籌碼表        列＝籌碼項目、欄＝平常／不熱／已過熱／4、13、26 週以上：之後 3 個月最大回撤中位數、跌 10% 以上的比例、判定
  每一段        連續過熱 4 週以上的每一段：從滿 4 週到結束後 3 個月最多跌多少、比同樣長度的期間大還是小（收起）
  技術面表      12 種轉空事件＋3 種空頭狀態＋技術面進入過熱（對照）
  大跌時        跌 20% 以上的大跌：各種轉空訊號在低點前出現的次數、高點後幾天、那時已跌、之後還跌
  收起          每一段大跌的細項、怎麼算、主要假說
每天建頁只讀研究檔（hotch.load_research）；現在的狀態每天重算（hotch.now）。只描述過去，不寫買賣指示；用字照專案禁用詞。
"""
from __future__ import annotations

from . import hotchspec as S
from .hotddpage import _d, _e, _nan, ci, pct, ppt

VCLS = {"up": "weak", "down": "strong", "none": "none", "few": "few"}     # 同景氣頁：紅＝回撤較大、藍＝回撤較小
MARK = {"up": "▲", "down": "▼", "none": "·", "few": "—"}
SHORT = {"up": "較大", "down": "較小", "none": "看不出", "few": "樣本不足"}
ORDER = {"tw": ("C1", "C3", "W1", "W2", "C2", "C7", "C5", "C6", "C4", "C8", "Dchip"),
         "us": ("S5", "S2", "S1", "S3", "S4", "Dsent")}
RUN_VARS = 2                    # 「每一段」固定列出排在最前面的幾項（另加現在連續過熱 4 週以上的）
SNAME = {"H0": "不熱", "H1": "已過熱", "H4": "4 週以上", "H13": "13 週以上", "H26": "26 週以上"}


def _sign(x, dec: int = 1) -> str:
    """有正負的百分點，不帶單位：+3.4、−0.6；接近 0 也標正負（區間下緣 +0.0 表示大於 0）。"""
    if _nan(x):
        return "—"
    r = round(x * 100, dec)
    sg = "−" if (r < 0 or (r == 0 and x < 0)) else ("+" if (r > 0 or (r == 0 and x > 0)) else "")
    return sg + f"{abs(r):.{dec}f}"


# ── 每天建頁的資料 ─────────────────────────────────────────────────────────

def state(B: dict) -> dict | None:
    """景氣頁的 B（heatcalc.build／heatcalc_us.build；美股要在 heatspec.use(該指數) 裡呼叫）→ 卡片要的資料；
    研究檔沒有、不是這一版就回 None（不顯示卡片）。台股的融資 ÷ 市值（W1、W2）用 crash.tw_inputs 現算（0.1 秒）。"""
    from . import heatpage as HP
    from . import heatspec as HS
    from . import hotch as X
    mk = "tw" if HP.MK["tab"] == "tw" else B.get("idx")
    R = X.load_research()
    if mk not in S.MARKETS or not R or mk not in (R.get("markets") or {}) or not B.get("cal"):
        return None
    if mk == "tw":
        from . import crash as CR
        from . import heatdata as HD
        D = dict(B.get("D") or {})
        for n in ("twcap", "twmgn", "taiex90"):
            if n not in D:
                D[n] = HD.load(n)
        D["_tsmc"] = CR._tsmc_month(None)
        I = X.inputs_tw(B=B, I=CR.tw_inputs(D=D, B=B, BX={}))
    else:
        I = X.inputs_us(mk, B)
    N = X.now(I)
    names = {r[0]: r[2] for r in HS.IND}
    names.update(S.VAR_NAMES)
    return {"mk": mk, "px": (HP.MK.get("px") or "").strip(), "R": R["markets"][mk], "now": N,
            "primary": R.get("primary") or {}, "names": names, "order": ORDER["tw" if mk == "tw" else "us"]}


def _A(C: dict, k: str, key: str) -> dict:
    return ((((C["R"].get("A") or {}).get(k) or {}).get("st") or {}).get(key)) or {}


def _B(C: dict, k: str) -> dict:
    B = C["R"].get("B") or {}
    return ((B.get("ev") or {}).get(k) or (B.get("st") or {}).get(k)) or {}


def matched(C: dict, k: str) -> str | None:
    """今天的狀態對應到哪一列研究結果：已連續週數到得了的最高狀態；那一列樣本不足就往下一層找（都不足就用最高的）。"""
    key = (C["now"]["chip"].get(k) or {}).get("key")
    if not key or key == "H0":
        return key
    keys = [s for s in S.STATES_A[:S.STATES_A.index(key) + 1]]
    for s in reversed(keys):
        if (_A(C, k, s).get("v") or "few") != "few":
            return s
    return key


def _cmp(st: dict) -> str:
    ev, b = st.get("ev") or {}, st.get("base") or {}
    return (f'之後 3 個月最大回撤中位數 {pct(ev.get("med"))}（平常 {pct(b.get("med"))}），'
            f'跌 10% 以上 {pct(ev.get("q10"), 0)}（平常 {pct(b.get("q10"), 0)}）')


def _vtxt(st: dict) -> str:
    v, vv = st.get("v") or "few", st.get("vv") or "few"
    if v == "few":
        return "次數太少，不能判定"
    t = {"up": "比平常大", "down": "比平常小", "none": "和平常看不出差別"}[v]
    if v in ("up", "down"):
        t += {"up": "，扣掉波動也比較大", "down": "，扣掉波動也比較小"}.get(vv, "，扣掉波動之後看不出")
    return t


def lead(C: dict) -> list[str]:
    """三句：籌碼、技術面、大跌時跌破季線的位置；全部由研究檔與今天的狀態算。"""
    N, nm = C["now"], C["names"]
    out = []
    lab = "籌碼" if C["mk"] == "tw" else "情緒籌碼"
    hot = [k for k in C["order"] if ((N["chip"].get(k) or {}).get("w") or 0) >= 1]
    if hot:
        lst = "、".join(f'{nm.get(k, k)}已連續 {N["chip"][k]["w"]} 週' for k in hot[:3]) + ("等" if len(hot) > 3 else "")
        s = f"{lab}：現在 {len(hot)} 項過熱（{lst}）。"
        pick = next((k for k in hot if (_A(C, k, matched(C, k)).get("v") or "few") in ("up", "down")), hot[0])
        key = matched(C, pick)
        st = _A(C, pick, key)
        if st.get("n"):
            s += f'過去{nm.get(pick, pick)}「{S.STATE_NAMES[key]}」的日子，{_cmp(st)}——{_vtxt(st)}。'
    else:
        s = f"{lab}：現在沒有{lab}項目過熱。"
        k = next((k for k in C["order"] if any(_A(C, k, x).get("v") == "up" for x in S.STATES_A)), None)
        if k:                                       # 排在最前面、有判定較大的那一項，取它最高的「較大」狀態
            key = [x for x in S.STATES_A if _A(C, k, x).get("v") == "up"][-1]
            st = _A(C, k, key)
            s += f'過去{nm.get(k, k)}「{S.STATE_NAMES[key]}」的日子，{_cmp(st)}——{_vtxt(st)}。'
        else:
            dn = [k for k in C["order"] if any(_A(C, k, x).get("v") == "down" for x in S.STATES_A)]
            s += (f"過去{lab}項目已連續過熱的日子，之後 3 個月的最大回撤沒有一項判定比平常大"
                  + (f"（{'、'.join(nm.get(k, k) for k in dn)}反而比平常小）" if dn else "") + "。")
    out.append(s)
    B = C["R"].get("B") or {}
    ev = B.get("ev") or {}
    ups = [k for k in S.TECH_EVENTS if (ev.get(k) or {}).get("v") == "up"]
    upv = [k for k in ups if (ev.get(k) or {}).get("vv") == "up"]
    dn = [k for k in S.TECH_EVENTS if (ev.get(k) or {}).get("v") == "down"]
    t = f"技術面：{len(S.TECH_EVENTS)} 種轉空訊號，之後 3 個月最大回撤比平常大的 {len(ups)} 種"
    if ups:
        t += f"（{'、'.join(S.EVENT_NAMES[k].split('（')[0] for k in ups)}），扣掉波動仍比較大的 {len(upv)} 種"
    if dn:
        t += f"；比平常小的 {len(dn)} 種"
    t += f"；其他 {len(S.TECH_EVENTS) - len(ups) - len(dn)} 種看不出差別。"
    rec = [(k, ds[-1]) for k, ds in (N.get("recent") or {}).items() if ds]
    if rec:
        rec.sort(key=lambda r: r[1], reverse=True)
        t += "最近 3 個月出現：" + "、".join(f'{S.EVENT_NAMES[k].split("（")[0]}（{_d(d)}）' for k, d in rec[:4]) \
            + ("等" if len(rec) > 4 else "") + "。"
    else:
        t += "最近 3 個月沒有出現轉空訊號。"
    out.append(t)
    d = ((B.get("dsum") or {}).get("20") or {}).get("ma60_dn") or {}
    e = ev.get("ma60_dn") or {}
    if d.get("n"):
        u = (f'跌 20% 以上的 {d["n"]} 次大跌，跌破季線在 {d["hit"]} 次的低點之前出現'
             + (f'：中位數在高點後 {int(d["days"])} 個交易日，那時已跌 {pct(d["lost"])}，之後到低點還跌 {pct(d["rem"])}'
                if d.get("hit") else "")
             + f'；但平常跌破季線之後 3 個月再跌 10% 以上的比例 {pct((e.get("ev") or {}).get("dq10"), 0)}，'
             f'任挑一天 {pct((e.get("base") or {}).get("dq10"), 0)}。')
        out.append(u)
    return out


# ── HTML ─────────────────────────────────────────────────────────────────

def _cell(st: dict, cur: bool, desc: bool = False) -> str:
    """籌碼表一格：中位數、跌 10% 以上的比例、判定（原始＋扣掉波動）。"""
    if not st or not st.get("n"):
        return f'<td class="xqe{" xqnow" if cur else ""}"><span class="xqn">沒有</span></td>'
    ev = st.get("ev") or {}
    tip = f'{st["n"]:,} 天、{st.get("ep") or 0} 段'
    if desc:
        body = f'<b>{pct(ev.get("med"))}</b><small>≥10% {pct(ev.get("q10"), 0)}</small>'
        return f'<td class="xqd{" xqnow" if cur else ""}" title="{_e(tip)}">{body}</td>'
    v, vv = st.get("v") or "few", st.get("vv") or "few"
    tip += f'；平均差 {ppt(st.get("d"))}（95% 區間 {ci(st.get("lo"), st.get("hi"))}）；扣掉波動 {ppt(st.get("dv"))}'
    lo = st.get("loo")
    if lo:
        tip += f'；拿掉一段 {_sign(lo[0])}～{_sign(lo[1])}'
    vtag = "" if v == "few" else f'<i class="xqvv xqm{vv}">扣 {MARK[vv]}</i>'
    body = (f'<b>{pct(ev.get("med"))}</b><small>≥10% {pct(ev.get("q10"), 0)}</small>'
            f'<em class="xqm{v}">{MARK[v]} {SHORT[v]}</em>{vtag}')
    return f'<td class="xq{v}{" xqnow" if cur else ""}" title="{_e(tip)}">{body}</td>'


def all_few(C: dict, k: str) -> bool:
    """這個項目每一種狀態都樣本不足（多半是 2019 年以後才有資料的）。"""
    return all((_A(C, k, s).get("v") or "few") == "few" for s in S.STATES_A)


def chip_table(C: dict) -> str:
    head = ('<tr><th class="l">項目</th><th>平常</th>'
            + "".join(f"<th>{_e(SNAME[s])}</th>" for s in ("H0",) + S.STATES_A) + "</tr>")
    A = C["R"].get("A") or {}
    main = [k for k in C["order"] if k in A and not all_few(C, k)] + [k for k in S.CONTRAST_VARS if k in A]
    few = [k for k in C["order"] if k in A and all_few(C, k)]
    rows, frows = _chip_rows(C, main), _chip_rows(C, few)
    lg = "　".join(f"{MARK[v]} {SHORT[v]}" for v in ("up", "down", "none", "few"))
    more = ""
    if few:
        nm = "、".join(C["names"].get(k, k) for k in few)
        more = (f'<details class="xqmore"><summary>樣本不足的 {len(few)} 項（{_e(nm)}；多半 2019 年以後才有資料）</summary>'
                f'<div class="tw"><table class="xqat">{head}{"".join(frows)}</table></div></details>')
    return (f'<div class="tw"><table class="xqat">{head}{"".join(rows)}</table></div>{more}'
            f'<p class="note">每一格＝那種狀態的日子之後 3 個月最大回撤的中位數，下面是跌 10% 以上的比例；判定和「平常」（同一個項目有資料以來的全部日子）比：'
            f'{_e(lg)}；「扣」＝依當時 20 日波動分三組、在組內比之後的判定。框起來的是今天的狀態。'
            f'已連續幾週＝每週最後一個交易日都在 80 以上（今天算最後一個週末）。樣本不足＝不到 {S.MIN_STATE_DAYS} 天或不到 '
            f'{S.MIN_EPISODES} 段（相隔 {S.EP_GAP} 個交易日以內算同一段）。滑過格子看天數、段數、平均差與區間、拿掉一段之後的範圍。</p>')


def _chip_rows(C: dict, keys: list[str]) -> list[str]:
    from .heatpage import n0
    rows = []
    for k in keys:
        row = (C["R"].get("A") or {}).get(k)
        if not row:
            continue
        n = C["now"]["chip"].get(k) or {}
        key = n.get("key")
        b = (row["st"].get("H1") or {}).get("base") or (row["st"].get("H0") or {}).get("base") or {}
        tv = n.get("v")
        if tv is None:
            today = "今天沒有值"
        elif (n.get("w") or 0) >= 1:
            today = f'今天 {n0(tv)}・已連續 {n["w"]} 週'
        else:
            today = f"今天 {n0(tv)}"
        con = "（對照）" if k in S.CONTRAST_VARS else ""
        cells = [_cell(row["st"].get("H0") or {}, key == "H0", desc=True)]
        cells += [_cell(row["st"].get(s) or {}, key == s) for s in S.STATES_A]
        rows.append(f'<tr{" class=\"xqcon\"" if con else ""}><td class="l"><b>{_e(con + C["names"].get(k, k))}</b>'
                    f'<span class="xqsub">{_e((row.get("first") or "")[:4])} 年起・{_e(today)}</span></td>'
                    f'<td class="xqd" data-h="平常"><b>{pct(b.get("med"))}</b><small>≥10% {pct(b.get("q10"), 0)}</small></td>'
                    + "".join(c.replace("<td ", f'<td data-h="{_e(SNAME[s])}" ', 1)
                              for c, s in zip(cells, ("H0",) + S.STATES_A)) + "</tr>")
    return rows


def runs_html(C: dict) -> str:
    """每一段連續過熱（≥ 4 週）：排在最前面的 RUN_VARS 項＋現在連續過熱 4 週以上的項目。"""
    A = C["R"].get("A") or {}
    N = C["now"]["chip"]
    ks = [k for k in C["order"] if (A.get(k) or {}).get("runs")]
    pick = ks[:RUN_VARS] + [k for k in ks[RUN_VARS:] if ((N.get(k) or {}).get("w") or 0) >= S.RUN_MIN]
    if not pick:
        return ""
    blocks = []
    for k in pick:
        runs = A[k]["runs"]
        ps = [r["pct"] for r in runs if r.get("pct") is not None and not r.get("open")]
        n_hi = sum(1 for p in ps if p >= 0.5)
        n10 = sum(1 for r in runs if (r.get("mdd") or 0) >= 0.10 and not r.get("open"))
        rows = []
        cur = (N.get(k) or {}).get("run")
        for r in sorted(runs, key=lambda r: r["a"], reverse=True):
            op = r.get("open")
            if op and cur and cur.get("s4") == r["s4"]:
                mdd, pk, tr, days = cur.get("mdd"), cur.get("pk"), cur.get("tr"), cur.get("days")
            else:
                mdd, pk, tr, days = r.get("mdd"), r.get("pk"), r.get("tr"), r.get("days")
            tag = "<small>還在過熱</small>" if op else ""
            rows.append(f'<tr{" class=\"xqcur\"" if op else ""}><td>{_e(_d(r["a"]))} → {_e(_d(r["z"]))}{tag}</td>'
                        f'<td>{r["wk"]}</td><td>{pct(mdd)}<small>{_e(_d(pk))} → {_e(_d(tr))}</small></td>'
                        f'<td>{"—" if op else pct(r.get("pct"), 0)}</td></tr>')
        cap = (f'{C["names"].get(k, k)}：{len(runs)} 段'
               + (f'，已結束的 {len(ps)} 段裡 {n_hi} 段比同樣長度的期間跌得多、{n10} 段跌超過 10%' if ps else ""))
        blocks.append(f'<details class="xqrun"><summary>{_e(cap)}</summary><div class="tw"><table class="xqrt">'
                      '<tr><th>第一個 → 最後一個過熱週末</th><th>週數</th><th>滿 4 週之後到結束後 3 個月最多跌</th>'
                      '<th>同樣長度的期間，比它少的比例</th></tr>' + "".join(rows) + "</table></div></details>")
    return ('<h3 class="xqh3">每一段連續過熱，最後有沒有大跌？<span class="sub">連續過熱 4 週以上的每一段</span></h3>'
            '<p class="xqmh">從滿 4 週那個週末的隔天起，到最後一個過熱週末之後 60 個交易日，指數最多從高點跌多少；'
            '右欄＝同樣長度、任挑起點的期間裡，跌得比它少的比例（越接近 100%＝這一段跌得越多；50% 上下＝和平常差不多）。'
            '還在過熱的這一段算到今天。</p>' + "".join(blocks))


def tech_table(C: dict) -> str:
    N = C["now"]
    B = C["R"].get("B") or {}
    head = ('<tr><th class="l">轉空訊號</th><th>次數</th><th>3 個月最大回撤<br>中位數（平常）</th><th>跌 10% 以上<br>（平常）</th>'
            '<th>判定</th><th>扣掉波動</th><th>訊號那天<br>已跌</th><th>之後再跌<br>10% 以上（平常）</th></tr>')
    rows = []

    def row(label, st, extra, n_unit="次", pre=True, sub="", judge=True):
        ev, b = st.get("ev") or {}, st.get("base") or {}
        v, vv = st.get("v") or "few", st.get("vv") or "few"
        if not judge:                                # 對照列只列數字、不判定（規格第 4 節）
            return (f'<tr class="{extra}"><td class="l">{_e(label)}<span class="xqcn">{st.get("n") or 0} 次</span>{sub}</td>'
                    f'<td data-h="次數" class="xqhm">{st.get("n") or 0} 次<small>{st.get("ep") or 0} 段</small></td>'
                    f'<td data-h="中位數（平常）">{pct(ev.get("med"))}<small>平常 {pct(b.get("med"))}</small></td>'
                    f'<td data-h="跌 10% 以上">{pct(ev.get("q10"), 0)}<small>平常 {pct(b.get("q10"), 0)}</small></td>'
                    '<td data-h="判定" class="xqmnone">對照，不判定</td><td data-h="扣掉波動" class="xqvc xqmnone">—</td>'
                    f'<td data-h="已跌" class="xqhm">{pct(st.get("pre"))}</td>'
                    f'<td data-h="再跌 10% 以上" class="xqhm">{pct(ev.get("dq10"), 0)}<small>平常 {pct(b.get("dq10"), 0)}</small></td></tr>')
        tip = (f'平均差 {ppt(st.get("d"))}（95% 區間 {ci(st.get("lo"), st.get("hi"))}）；扣掉波動 {ppt(st.get("dv"))}'
               f'（{ci(st.get("lov"), st.get("hiv"))}）；{(st.get("a") or "")[:4]}～{(st.get("z") or "")[:4]}')
        n = st.get("n") or 0
        cnt = f'{n:,} {n_unit}・{st.get("ep") or 0} 段'
        return (f'<tr class="{extra}" title="{_e(tip)}"><td class="l">{_e(label)}<span class="xqcn">{_e(cnt)}</span>{sub}</td>'
                f'<td data-h="次數" class="xqhm">{n:,} {n_unit}<small>{st.get("ep") or 0} 段</small></td>'
                f'<td data-h="中位數（平常）">{pct(ev.get("med"))}<small>平常 {pct(b.get("med"))}</small></td>'
                f'<td data-h="跌 10% 以上">{pct(ev.get("q10"), 0)}<small>平常 {pct(b.get("q10"), 0)}</small></td>'
                f'<td data-h="判定" class="xqm{v}">{MARK[v]} {SHORT[v]}<i class="xqmv xqm{vv}">扣掉波動 {MARK[vv]} {SHORT[vv]}</i></td>'
                f'<td data-h="扣掉波動" class="xqvc xqm{vv}">{MARK[vv]} {SHORT[vv]}</td>'
                f'<td data-h="已跌" class="xqhm">{pct(st.get("pre")) if pre else "—"}</td>'
                f'<td data-h="再跌 10% 以上" class="xqhm">{pct(ev.get("dq10"), 0)}<small>平常 {pct(b.get("dq10"), 0)}</small></td></tr>')
    for k in S.TECH_EVENTS:
        rec = (N.get("recent") or {}).get(k) or []
        sub = f'<span class="xqrc">最近 {_e(_d(rec[-1]))}</span>' if rec else ""
        rows.append(row(S.EVENT_NAMES[k], (B.get("ev") or {}).get(k) or {}, "xqrec" if rec else "", sub=sub))
    for k in S.TECH_STATES:
        s0 = (N.get("states") or {}).get(k)
        sub = ""
        if s0 and s0.get("on"):
            sub = f'<span class="xqrc">現在是（{_e(_d(s0.get("since")))} 起）</span>'
        rows.append(row(S.TECH_STATE_NAMES[k] + "（狀態）", (B.get("st") or {}).get(k) or {},
                        "xqst" + (" xqrec" if sub else ""), n_unit="天", pre=False, sub=sub))
    rows.append(row("（對照）技術面熱度進入過熱", B.get("hot") or {}, "xqcon", judge=False))
    vs = B.get("vs") or {}
    big = [k for k in S.TECH_EVENTS if (vs.get(k) or {}).get("lo") is not None and vs[k]["lo"] > 0]
    small = [k for k in S.TECH_EVENTS if (vs.get(k) or {}).get("hi") is not None and vs[k]["hi"] < 0]
    hot = B.get("hot") or {}
    vtxt = (f'和「技術面熱度進入過熱」之後（{hot.get("n") or 0} 次，中位數 {pct((hot.get("ev") or {}).get("med"))}）比：'
            f'{len(S.TECH_EVENTS)} 種轉空訊號之後的平均最大回撤比較大、而且區間不含 0 的有 {len(big)} 種'
            + (f'（{"、".join(S.EVENT_NAMES[k].split("（")[0] for k in big)}）' if big else "")
            + (f'；比較小的 {len(small)} 種' if small else "；沒有一種比較小") + "。")
    return (f'<div class="tw"><table class="xqbt">{head}{"".join(rows)}</table></div>'
            f'<p class="xqmh">{_e(vtxt)}</p>'
            '<p class="note">訊號那天已跌＝事件那天收盤比之前 60 個交易日的最高收盤低多少（中位數）；之後再跌 10% 以上＝從隔天收盤起 3 個月內，'
            '有一天比隔天收盤低 10% 以上的比例（訊號之後真的再跌的比例）。狀態列＝那種狀態的每一天。滑過列看平均差與區間。'
            '均線類從第 251 個交易日起；技術面熱度類從它有值的日子起。</p>')


def decl_html(C: dict) -> str:
    B = C["R"].get("B") or {}
    ds = (B.get("dsum") or {}).get("20") or {}
    dl = (B.get("decl") or {}).get("20") or []
    if not dl:
        return ""
    rows = []
    for k in S.TECH_EVENTS:
        d = ds.get(k) or {}
        if not d.get("n"):
            continue
        rows.append(f'<tr><td class="l">{_e(S.EVENT_NAMES[k].split("（")[0])}</td>'
                    f'<td data-h="低點前出現">{d["hit"]}／{d["n"]}</td>'
                    f'<td data-h="高點後">{"—" if d.get("days") is None else str(int(d["days"])) + " 天"}</td>'
                    f'<td data-h="那時已跌">{pct(d.get("lost"))}</td><td data-h="之後還跌">{pct(d.get("rem"))}</td></tr>')
    d10 = ((B.get("dsum") or {}).get("10") or {}).get("ma60_dn") or {}
    ten = (f'跌 10% 以上的 {d10.get("n") or 0} 次：跌破季線在 {d10.get("hit") or 0} 次的低點前出現，那時已跌 {pct(d10.get("lost"))}、'
           f'之後還跌 {pct(d10.get("rem"))}（中位數）。' if d10.get("n") else "")
    dr = (B.get("drows") or {}).get("20") or {}
    det = []
    for j, e in enumerate(dl):
        cells = []
        for k in ("ma60_dn", "x_dead", "pv_dn"):
            r = (dr.get(k) or [None] * len(dl))[j]
            if r is None:
                cells.append('<td class="xqe">還沒有資料</td>')
            elif r[0] is None:
                cells.append('<td>低點前沒有出現</td>')
            else:
                cells.append(f'<td>{_e(_d(r[0]))}<small>已跌 {pct(r[2])}・之後還跌 {pct(r[3])}</small></td>')
        op = "<small>還沒反彈</small>" if e.get("open") else ""
        det.append(f'<tr><td>{_e(_d(e["pk"]))} → {_e(_d(e["tr"]))}{op}</td><td>{pct(e["dd"], 0)}</td>{"".join(cells)}</tr>')
    return ('<h3 class="xqh3">大跌時，轉空訊號出現在哪裡？<span class="sub">跌 20% 以上的大跌</span></h3>'
            '<p class="xqmh">大跌段＝從最高收盤跌 20% 以上、從低點反彈 20% 才算結束。每一種訊號：高點之後、低點以前的第一次；'
            '那時已跌＝隔天收盤（賣出價）比高點低多少，之後還跌＝從賣出價到低點又跌多少（都是中位數）。'
            '分母＝那種訊號算得出來的大跌次數（均線類要有 240 天收盤，技術面熱度類要從它有值的時候起）。</p>'
            '<div class="tw"><table class="xqdt"><tr><th class="l">訊號</th><th>低點前出現</th><th>高點後</th><th>那時已跌</th>'
            f'<th>之後還跌</th></tr>{"".join(rows)}</table></div>'
            + (f'<p class="note">{_e(ten)}</p>' if ten else "")
            + f'<details class="xqmore"><summary>每一次大跌（{len(dl)} 次）：跌破季線、死亡交叉、跌破前波低點各在哪一天</summary>'
            '<div class="tw"><table class="xqrt"><tr><th>高點 → 低點</th><th>跌幅</th><th>跌破季線</th><th>月線季線死亡交叉</th>'
            f'<th>跌破前波低點</th></tr>{"".join(det)}</table></div></details>')


def primary_html(C: dict) -> str:
    P = C.get("primary") or {}
    n_ok = sum(1 for h in S.PRIMARY if (P.get(h) or {}).get("ok"))
    li = []
    for h, sp in S.PRIMARY.items():
        if sp["mk"] != C["mk"]:
            continue
        r = P.get(h) or {}
        unit = "天" if sp["part"] == "A" else "次"
        if r.get("few") or r.get("d") is None:
            res = f'樣本不足（{r.get("n") or 0} {unit}、{r.get("ep") or 0} 段）'
        else:
            res = (f'{r["n"]:,} {unit}（{r.get("ep") or 0} 段），平均差 {ppt(r["d"])}（95% 區間 {ci(r["lo"], r["hi"])}），'
                   f'前後兩半 {_sign(r.get("h1"))}／{_sign(r.get("h2"))}，Holm 校正後 p＝{r["padj"]:.3f}，{"成立" if r.get("ok") else "不成立"}')
        li.append(f'<li><b>{h}</b> {_e(sp["text"])}：{_e(res)}</li>')
    tail = "下面是和這個市場有關的。" if li else "沒有一個是針對這個指數的。"
    return (f'<p class="xqmh"><b>事前寫定的 {len(S.PRIMARY)} 個主要假說</b>（都是「之後 3 個月的平均最大回撤比全部日子大」；'
            f'Holm 校正、單尾）：{n_ok} 個成立；{tail}</p>' + (f'<ul class="xqpl">{"".join(li)}</ul>' if li else ""))


def method_html(C: dict) -> str:
    px = C.get("px") or ""
    lim = "加權指數是價格指數（不含息），台股從 1990 年起" if C["mk"] == "tw" else f"{px} 是價格指數（不含股利）"
    return ('<div class="xqmh">'
            '<p><b>為什麼要再看一次</b>：上一張卡只看「進入過熱」「滿 N 週」那一天，次數少、一天的雜訊大；'
            '這裡看已經連續過熱的每一天（狀態），並另外檢查技術面轉空之後。</p>'
            '<p><b>怎麼算</b>：每一天之後，從隔天收盤起 60 個交易日（約 3 個月）的最大回撤，和同一個項目有資料以來的全部日子比。'
            '平均差的 95% 區間用 60 個交易日一塊重抽 2,000 次；區間不含 0、前後兩半方向一樣、同一組比較一起做多重比較校正後 q ≤ 0.10，'
            '才寫「較大」或「較小」。「扣掉波動」另做一次同樣的判定。</p>'
            '<p><b>事後檢查</b>：狀態只有 5～20 段，每一格另算「拿掉其中一段之後的平均差」（滑過格子看），'
            '這是看過結果才加的，不影響判定。</p>'
            f'<p><b>限制</b>：{_e(lim)}；籌碼項目多半 2002 年以後才有，結論靠的是少數幾段；沒有做樣本外。'
            '規格在看結果之前寫定（hotchspec VER 1），規劃文件 docs/lab_hotdd_plan.md 第 7、8 節。</p></div>')


def card(C: dict | None) -> str:
    """整張卡；C＝state() 的結果（None＝研究檔沒有，不顯示）。"""
    if not C:
        return ""
    from .heatpage import _md
    ls = lead(C)
    lead_html = f'<p class="xql">{_e(ls[0])}</p>' + "".join(f'<p class="xql2">{_e(s)}</p>' for s in ls[1:])
    return (f'<section class="sec xqsec" id="hotch"><div class="card xqc">'
            f'<div class="khd"><h2>反向檢查：籌碼連續過熱、技術面轉空</h2>'
            f'<span class="kn">之後 60 個交易日・資料到 {_e(_md(C["now"].get("d")))}</span></div>'
            f'{lead_html}'
            '<p class="ksub">上一張卡看「進入過熱」「滿 N 週」那一天；這裡看已經連續過熱的每一天，以及技術面轉空之後，'
            '之後 3 個月最多從高點跌多少。只描述過去，不是買賣指示。</p>'
            '<h3 class="xqh3">籌碼連續過熱的日子<span class="sub">之後 3 個月的最大回撤</span></h3>'
            f'{chip_table(C)}{runs_html(C)}'
            '<h3 class="xqh3">技術面轉空之後<span class="sub">之後 3 個月的最大回撤</span></h3>'
            f'{tech_table(C)}{decl_html(C)}'
            f'<details class="xqmore"><summary>怎麼算、主要假說</summary>{method_html(C)}{primary_html(C)}</details>'
            '</div></section>')


def hotdd_note(C: dict | None) -> str | None:
    """給上一張卡（過熱之後 3 個月的最大回撤）的一句提示：這個市場有哪些籌碼項目在「已連續過熱」狀態下判定回撤較大。"""
    if not C:
        return None
    ups = [k for k in C["order"] if any((_A(C, k, s).get("v")) == "up" for s in S.STATES_A)]
    if not ups:
        return "看已經連續過熱的每一天（下一張「反向檢查」），籌碼項目之後的回撤也沒有一項判定比平常大。"
    return (f'看已經連續過熱的每一天（下一張「反向檢查」），{"、".join(C["names"].get(k, k) for k in ups)}'
            '之後 3 個月的回撤判定比平常大——上面的事件只看一天，次數太少看不出來。')


CSS = (
    ".xqc{padding:12px 14px;min-width:0}"
    ".xql{font-size:15px;font-weight:700;margin:8px 0 4px;line-height:1.6}"
    ".xql2{font-size:13.5px;color:var(--ink2);margin:0 0 4px;line-height:1.65}"
    ".xqh3{font-size:15px;margin:16px 0 4px}"
    ".xqmh,.xqmh p{font-size:12.5px;color:var(--ink2);line-height:1.7;margin:6px 0}"
    ".xqsub{display:block;font-size:11px;font-weight:400;color:var(--mut);line-height:1.45}"
    "table.xqat{font-size:12.5px}"
    "table.xqat th,table.xqat td{padding:5px 6px;text-align:center;vertical-align:top}"
    "table.xqat td.l,table.xqat th.l{text-align:left;white-space:normal;min-width:9em}"
    "table.xqat td b{display:block;font-size:13.5px;font-variant-numeric:tabular-nums}"
    "table.xqat td small{display:block;font-size:10.5px;color:var(--mut)}"
    "table.xqat td em{display:block;font-style:normal;font-size:11px;margin-top:1px}"
    ".xqvv{display:block;font-style:normal;font-size:10.5px}"
    "table.xqat td.xqnow{box-shadow:inset 0 0 0 2px var(--ink);border-radius:6px}"
    "table.xqat td.xqup{background:color-mix(in srgb,var(--t4) 12%,transparent)}"
    "table.xqat td.xqdown{background:color-mix(in srgb,var(--t0) 12%,transparent)}"
    "table.xqat td.xqfew b,table.xqat td.xqe{color:var(--mut)}"
    ".xqn{font-size:11px;color:var(--mut)}"
    "tr.xqcon td{background:var(--card2)}"
    ".xqmup{color:var(--t4);font-weight:700}.xqmdown{color:var(--t0);font-weight:700}.xqmnone,.xqmfew{color:var(--mut)}"
    ".xqrun{border-top:1px solid var(--line);padding:6px 0}"
    ".xqrun>summary,.xqmore>summary{cursor:pointer;font-size:13px;color:var(--acc)}"
    ".xqmore{margin-top:12px}"
    ".xqmore>summary{padding:8px 0 2px;border-top:1px solid var(--line)}"
    ".xqmore[open]>summary{margin-bottom:8px}"
    "table.xqrt{font-size:12px;margin-top:4px}"
    "table.xqrt th,table.xqrt td{padding:4px 6px;text-align:right;vertical-align:top}"
    "table.xqrt th:first-child,table.xqrt td:first-child{text-align:left}"
    "table.xqrt small{display:block;font-size:10.5px;color:var(--mut)}"
    "tr.xqcur td{font-weight:700}"
    "table.xqbt,table.xqdt{font-size:12.5px}"
    "table.xqbt th,table.xqbt td,table.xqdt th,table.xqdt td{padding:5px 6px;text-align:right;vertical-align:top}"
    "table.xqbt td.l,table.xqbt th.l,table.xqdt td.l,table.xqdt th.l{text-align:left;white-space:normal;min-width:9em}"
    "table.xqbt small{display:block;font-size:10.5px;color:var(--mut)}"
    "tr.xqst td{background:var(--card2)}"
    "tr.xqrec td.l{font-weight:700}"
    ".xqrc{display:block;font-size:10.5px;font-weight:400;color:var(--t4)}"
    ".xqpl{font-size:12.5px;color:var(--ink2);line-height:1.7;padding-left:1.2em;margin:4px 0}"
    ".xqmv{display:none;font-style:normal}"
    ".xqcn{display:none;font-size:10.5px;font-weight:400;color:var(--mut);margin-left:6px}"
    "@media (max-width:640px){"
    "table.xqbt td.xqvc,table.xqbt td.xqhm{display:none}"
    "table.xqbt .xqcn{display:inline}"
    "table.xqbt td .xqmv{display:block;font-size:10.5px}"
    "table.xqat,table.xqat tbody,table.xqbt,table.xqbt tbody,table.xqdt,table.xqdt tbody{display:block}"
    "table.xqat tr:first-child,table.xqbt tr:first-child,table.xqdt tr:first-child{display:none}"
    "table.xqat tr{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px 6px;padding:8px 2px;"
    "border-bottom:1px solid var(--line)}"
    "table.xqat td{display:block;border:0;padding:3px 4px;min-width:0!important}"
    "table.xqat td.l{grid-column:1/-1}"
    "table.xqat td[data-h]::before{content:attr(data-h);display:block;color:var(--mut);font-size:10.5px}"
    "table.xqbt tr,table.xqdt tr{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:2px 8px;padding:8px 2px;"
    "border-bottom:1px solid var(--line)}"
    "table.xqdt tr{grid-template-columns:repeat(4,minmax(0,1fr))}"
    "table.xqbt td,table.xqdt td{display:block;border:0;padding:0;text-align:left;font-size:12px;min-width:0!important}"
    "table.xqbt td.l,table.xqdt td.l{grid-column:1/-1}"
    "table.xqbt td[data-h]::before,table.xqdt td[data-h]::before{content:attr(data-h);display:block;color:var(--mut);font-size:10.5px}"
    "}"
)
