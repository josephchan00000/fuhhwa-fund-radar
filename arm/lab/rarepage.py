"""少見但勝率高的策略的頁面（docs/lab_rare_plan.md 第 8 節；成績＝研究檔 data/lab/rare_research.json，現在＝每天建頁時算）。

使用者 2026-10-27 選「放上網頁＋觸發前提醒」、「可以觀察的 5 條一起列」：
  board_rows()     配置頁・策略表「觀察中」九列（主要市場）：名稱連到研究紀錄頁那張卡、一句規則、成績、今天（下一次買賣的日子）
  research_body()  研究紀錄頁「少見但勝率高的策略」一段：總表＋每條一張卡（原說法與出處、規則、各市場成績、另外看的期間、每一次、現在）
  reminders()      06:35 推播（valog.rare_state）：建議試用的規則在主要市場接下來 REMIND_DAYS 個交易日內要買或賣的
配置頁照主頁面的用字（docs/lab_ia_v5_plan.md 第 8 節）；研究紀錄頁不受限。版面借用 candpage 的 cd* 樣式（研究紀錄頁已載入）。
"""
from __future__ import annotations

import html
from datetime import date
from urllib.parse import quote

from . import rare as RA
from . import rarespec as S

REMIND_DAYS = 2                 # 推播提醒：接下來幾個交易日內要買或賣（11/2 與 11/3 早上都會提到 11/3 收盤買）
MKK = {"tw": "tw", "spx": "us", "ixic": "us", "ndx": "us", "sox": "us"}
FREQ = {"mid": "四年一次", "santa": "每年 7 個交易日", "jan": "一月漲的年份", "ath": "幾年一次",
        "bull": "幾年一次", "vixinv": "一年一兩次", "lnypre": "每年 5 個交易日", "lnypost": "每年 20 個交易日", "nsf": "幾年一次"}
HOW = {
    "mid": "美國期中選舉那天收盤買，抱一年（250 個交易日）",
    "santa": "12 月最後 5 個交易日的前一天收盤買，抱到隔年 1 月第 2 個交易日收盤",
    "jan": "一月漲了，2 月第一個交易日收盤買，抱到 12 月最後一個交易日收盤",
    "ath": "隔一年以上才又創歷史新高，隔天收盤買，抱一年",
    "bull": "從熊市低點（跌兩成以上）漲回兩成，隔天收盤買，抱一年",
    "vixinv": "VIX 第一次高過三個月期的 VIX3M（之前 60 個交易日都沒有），隔天收盤買，抱 3 個月",
    "lnypre": "農曆年封關日往前 5 個交易日收盤買，封關日收盤賣",
    "lnypost": "農曆年封關日收盤買，抱 20 個交易日（開紅盤後約 4 週）",
    "nsf": "國安基金宣布護盤，它第一天進場的隔天收盤買，抱一年",
}
REC_NAMES = S.REC_NAMES


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "—")


def _ymd(d: str | None) -> str:
    return f"{int(d[:4])}/{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "—")


def _wd(d: str) -> str:
    return "一二三四五六日"[date.fromisoformat(d).weekday()]


def _pc(x, d: int = 0, sign: bool = False) -> str:
    if x is None:
        return "—"
    v = x * 100
    s = f"{abs(v):.{d}f}%"
    if sign:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return ("−" if v < 0 else "") + s


def load() -> dict:
    """→ {"res": 研究檔（版本不同＝None）, "now": {規則: {市場: 現在}}}。"""
    res = RA.load()
    return {"res": res, "now": RA.now_all() if res else {}}


def _x(B: dict, k: str, mk: str) -> dict:
    return (((B.get("res") or {}).get("rules") or {}).get(k) or {}).get(mk) or {}


def _n(B: dict, k: str, mk: str) -> dict:
    return ((B.get("now") or {}).get(k) or {}).get(mk) or {}


def now_text(k: str, n: dict, short: bool = True) -> str:
    """現在的狀態一句（策略表「今天」、研究卡「現在」）。日期是那個市場的交易日（美股寫美國的日子）。"""
    st = n.get("st")
    if not st:
        return "—"
    approx = "（日期約略，等證交所公布明年休市表）" if n.get("approx") and not short else ("（約）" if n.get("approx") else "")
    if st == "hold":
        return f"持有中・{_md(n.get('qd'))} 收盤賣{approx}" if short else \
            f"持有中：{_ymd(n.get('bd'))} 收盤買進，{_ymd(n.get('qd'))} 收盤賣出{approx}" + \
            (f"；到現在 {_pc(n.get('chg'), 1, True)}" if n.get("chg") is not None else "")
    if st in ("buy", "wait") and n.get("bd"):
        bd = n["bd"]
        if short:
            return f"{_md(bd)}（{_wd(bd)}）收盤買{approx}"
        return f"下一次：{_ymd(bd)}（{_wd(bd)}）收盤買進，{_ymd(n.get('qd'))} 收盤賣出{approx}"
    if k == "jan":
        return f"{_md(n.get('check'))} 收盤看一月漲跌" if short else f"{_ymd(n.get('check'))} 收盤看一月有沒有漲（漲了 2 月第一個交易日收盤買）"
    if k == "ath":
        if n.get("since") is not None and n.get("need") is not None and n["since"] >= n["need"]:
            return f"再創新高就買（已經 {n['since']} 天沒有新高）"
        return f"沒有觸發（{_md(n.get('ath'))} 才創新高）" if short else \
            f"沒有觸發：{_ymd(n.get('ath'))} 才創新高，要先隔 {n.get('need')} 個交易日以上沒有新高（現在離高點 {_pc(n.get('off'), 1, True)}）"
    if k == "bull":
        if n.get("bear"):
            return f"熊市中：漲到 {n['confirm']:,.0f} 就買" if short else \
                f"熊市中：低點 {n['low']:,.0f}，收盤漲到 {n['confirm']:,.0f} 以上就是訊號（現在 {n.get('px'):,.0f}）"
        return f"沒有觸發（跌到 {n['bear_at']:,.0f} 才算熊市）" if short else \
            f"沒有觸發：還沒進入熊市（收盤跌到 {n['bear_at']:,.0f} 以下才算，高點 {n['high']:,.0f}，現在 {n.get('px'):,.0f}）"
    if k == "vixinv":
        r = n.get("ratio")
        return (f"沒有觸發（VIX ÷ VIX3M＝{r:.2f}）" if r is not None else "沒有觸發") if short else \
            (f"沒有觸發：{_ymd(n.get('rd'))} VIX ÷ VIX3M＝{r:.2f}（1.00 以上、之前 60 天都沒有才算）" if r is not None else "沒有觸發")
    if k == "nsf":
        return "等國安基金下一次進場"
    return "沒有觸發"


# ── 配置頁・策略表 ───────────────────────────────────────────────────────────────

def board_rows(B: dict | None = None) -> list[dict]:
    """九列（主要市場），狀態「觀察中」；成績欄＝賺錢比例（任一天），次數、中位數、建議；最慘跌欄＝抱的期間最大跌幅（最差一次；2026-10-28 起和大跌同一個算法）。"""
    B = B or load()
    if not B.get("res"):
        return []
    out = []
    for R in S.RULES:
        k, mk = R["k"], R["home"]
        x = _x(B, k, mk)
        f = x.get("full") or {}
        if not f.get("n"):
            continue
        lab = REC_NAMES.get(x.get("rec_v") or "no", "")
        out.append({"id": f"{mk}:rare:{k}", "name": R["name"], "mk": S.NAMES[mk], "mkk": MKK[mk], "ix": mk, "type": "指數型",
                    "st": "obs", "how": HOW[k], "href": f"x9r.html#rare-{k}", "go": {},
                    "perf": f"賺錢 {_pc(f.get('win'))}", "ref": f"任一天 {_pc(f.get('base'))}",
                    "sub": f"{f['n']} 次・每次中位數 {_pc(f.get('med'), 1, True)}・{lab}",
                    "mdd": _pc(f.get("mddw", f.get("mae_max")), 0), "today": now_text(k, _n(B, k, mk))})
    return out


# ── 推播提醒 ─────────────────────────────────────────────────────────────────

def reminders(B: dict | None = None) -> list[list]:
    """建議試用的規則（研究檔 rec_v＝rec）在主要市場接下來 REMIND_DAYS 個交易日內要買或賣的：[[日期, 買／賣, 市場, 規則, 賣出日（買才有）]]。"""
    from . import xstrat as XT
    B = B or load()
    out = []
    for R in S.RULES:
        k, mk = R["k"], R["home"]
        if _x(B, k, mk).get("rec_v") != "rec":
            continue
        n = _n(B, k, mk)
        if not n.get("st"):
            continue
        nxt = set(XT.future_days(mk, n["last"], REMIND_DAYS))
        if n["st"] in ("wait", "buy") and n.get("bd") in nxt:
            out.append([n["bd"], "買", mk, k, n.get("qd")])
        if n["st"] == "hold" and n.get("qd") in nxt:
            out.append([n["qd"], "賣", mk, k, None])
    return sorted(out)


def remind_line(td: list) -> str | None:
    """推播一行：少見機會：11/3（二）收盤 S&P 500 買進（期中選舉後抱一年，抱到 2027/11/2）。"""
    if not td:
        return None
    parts = []
    for d, act, mk, k, qd in td:
        nm = S.BY_KEY[k]["name"] if k in S.BY_KEY else k
        tail = f"，抱到 {_ymd(qd)}" if act == "買" and qd else ""
        parts.append(f"{_md(d)}（{_wd(d)}）收盤 {S.NAMES.get(mk, mk)} {act}{'進' if act == '買' else '出'}（{nm}{tail}）")
    return "少見機會：" + "；".join(parts) + "。"


# ── 研究紀錄頁 ───────────────────────────────────────────────────────────────

RULE_FULL = {
    "mid": "選舉日＝11 月第一個星期一之後的星期二（每四年一次）。那天（或之前最後一個交易日，1968 年以前選舉日休市）收盤買，抱 250 個交易日收盤賣。",
    "santa": "12 月最後 5 個交易日加隔年 1 月前 2 個交易日：最後 5 個交易日的前一天收盤買，1 月第 2 個交易日收盤賣。",
    "jan": "1 月最後一個交易日收盤比前一年 12 月最後一個交易日高（漲幅 ＞ 0），隔天（2 月第一個交易日）收盤買，抱到同年 12 月最後一個交易日收盤。",
    "ath": "收盤比之前所有日子都高，而且上一次創新高是 250 個交易日以前或更早；隔天收盤買，抱 250 個交易日。",
    "bull": "從最高收盤跌兩成以上＝熊市；之後收盤比熊市裡的最低收盤高兩成＝新多頭確認，隔天收盤買，抱 250 個交易日；之後從那天的收盤重新記高點、等下一次熊市。",
    "vixinv": "VIX ÷ VIX3M ≥ 1（近月恐慌高過三個月期），而且之前 60 個交易日都 ＜ 1；隔天收盤買，抱 60 個交易日。台股用收盤時已經知道的前一個美股交易日。",
    "lnypre": "封關日＝每年 1/10～2/28 之間、和下一個交易日相隔最多天的那一個交易日（農曆年休市）。封關日往前第 5 個交易日收盤買，封關日收盤賣。",
    "lnypost": "封關日收盤買，抱 20 個交易日（含開紅盤）收盤賣。",
    "nsf": "國安基金每一次護盤的起始日之後第一個交易日收盤買（比國安基金第一天進場晚一天），抱 250 個交易日。",
}
BOM = "\ufeff"                  # Excel 直接開才認得 UTF-8
ROW_COLS = ("訊號日", "買進日", "買進", "賣出日", "賣出", "天數", "扣成本後", "最大跌幅")


def _summary_row(B: dict, R: dict) -> str:
    k, mk = R["k"], R["home"]
    x = _x(B, k, mk)
    f = x.get("full") or {}
    t = x.get("tier") or "few"
    return (f'<tr><td><a href="#rare-{k}">{_e(R["name"])}</a></td><td>{_e(S.NAMES[mk])}</td><td>{_e(FREQ[k])}</td>'
            f'<td>{f.get("n", 0)}</td><td>{_pc(f.get("win"))}（{_pc(f.get("base"))}）</td>'
            f'<td>{_pc(f.get("med"), 1, True)}</td><td>{_pc(f.get("worst"), 1, True)}</td>'
            f'<td>{S.TIER_MARK[t]} {_e(S.TIER_NAMES[t])}</td><td><b>{_e(REC_NAMES.get(x.get("rec_v") or "no", ""))}</b></td>'
            f'<td>{_e(now_text(k, _n(B, k, mk)))}</td></tr>')


def _mk_row(B: dict, k: str, mk: str) -> str:
    x = _x(B, k, mk)
    f = x.get("full") or {}
    r = x.get("rec") or {}
    t = x.get("tier") or "few"
    rec = f'{r.get("n", 0)} 次 {_pc(r.get("win"))}（{_pc(r.get("base"))}）' if r.get("n") else "—"
    return (f'<tr><td>{_e(S.NAMES[mk])}</td><td>{S.TIER_MARK[t]}</td><td>{f.get("n", 0)}</td>'
            f'<td>{_pc(f.get("win"))}（{_pc(f.get("base"))}）</td><td>{_pc(f.get("med"), 1, True)}</td>'
            f'<td>{_pc(f.get("trim"), 1, True)}</td><td>{_pc(f.get("worst"), 1, True)}</td>'
            f'<td>{_pc(f.get("mddw", f.get("mae_max")), 1)}</td><td>{rec}</td>'
            f'<td>{_pc(x.get("grid_ok"))}</td><td>{_pc(x.get("luck"), 1)}</td>'
            f'<td>{_bn(x.get("binom"))}</td></tr>')


def _bn(v) -> str:
    return "—" if v is None else f"{v:.3f}"


def _outs(x: dict) -> str:
    rows = []
    names = {"pub": "來源發表之後", "early": "S&P 500 1950 年以前（來源沒用到）"}
    for key, o in (x.get("outs") or {}).items():
        span = f'{o.get("from")} 年起' if key == "pub" else f'{o.get("from")}～{o.get("to")}'
        if not o.get("n"):
            rows.append(f'<tr><td>{_e(names[key])}</td><td>{_e(span)}</td><td colspan="3">沒有發生</td></tr>')
            continue
        rows.append(f'<tr><td>{_e(names[key])}</td><td>{_e(span)}</td><td>{o["n"]}</td>'
                    f'<td>{_pc(o.get("win"))}（{_pc(o.get("base"))}）</td><td>{_pc(o.get("med"), 1, True)}</td></tr>')
    for i, h in enumerate(x.get("halves") or []):
        rows.append(f'<tr><td>{"前一半" if i == 0 else "後一半"}</td><td>{_e((h.get("a") or "")[:4])}～{_e((h.get("z") or "")[:4])}</td>'
                    f'<td>{h["n"]}</td><td>{_pc(h.get("win"))}</td><td>{_pc(h.get("med"), 1, True)}</td></tr>')
    if not rows:
        return ""
    return ('<div class="cdtw"><table class="cdt"><thead><tr><th>期間</th><th>買進日在</th><th>次數</th><th>賺錢（任一天）</th>'
            '<th>中位數</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def _events(x: dict) -> str:
    tr = x.get("tr") or []
    if not tr:
        return '<p class="cdn">還沒有完整的一次。</p>'
    body = "".join(f'<tr><td>{_e(r[0]) if r[0] != r[1] else "—"}</td><td>{_e(r[1])}</td><td>{r[2]:,}</td><td>{_e(r[3])}</td>'
                   f'<td>{r[4]:,}</td><td>{r[5]}</td><td>{_pc(r[6], 1, True)}</td><td>{_pc(r[7], 1)}</td></tr>' for r in reversed(tr))
    return ('<div class="cdtw rztr"><table class="cdt"><thead><tr>' + "".join(f"<th>{c}</th>" for c in ROW_COLS)
            + "</tr></thead><tbody>" + body + "</tbody></table></div>")


def _csv(B: dict) -> str:
    """每一次（全部規則、全部市場）。規則、市場寫代號（中文每個字編碼後是 9 個字元，全部寫中文頁面會多 100KB 以上），代號對照寫在第二行。"""
    lines = ["規則,市場,訊號日,買進日,買進價,賣出日,賣出價,天數,扣成本後報酬%,最大跌幅%",
             "# " + " ".join(f"{R['k']}={R['name']}" for R in S.RULES) + " / " + " ".join(f"{m}={S.NAMES[m]}" for m in S.MARKETS)]
    for R in S.RULES:
        for mk in R["mk"]:
            for r in _x(B, R["k"], mk).get("tr") or []:
                lines.append(",".join(str(v) for v in (R["k"], mk, r[0], r[1], r[2], r[3], r[4], r[5],
                                                       round(r[6] * 100, 2), round(r[7] * 100, 2))))
    return "data:text/csv;charset=utf-8," + quote(BOM + "\n".join(lines))


def _card(B: dict, R: dict) -> str:
    k, mk = R["k"], R["home"]
    x = _x(B, k, mk)
    t = x.get("tier") or "few"
    lab = REC_NAMES.get(x.get("rec_v") or "no", "")
    src = "、".join(f'<a href="{_e(u)}" target="_blank" rel="noopener">{i + 1}</a>' for i, u in enumerate(R["src"]))
    cv, bh = x.get("curve") or {}, x.get("bh") or {}
    kv = [("原說法", _e(R["claim"])), ("出處", _e(R["who"]) + f"（原文：{src}）"), ("為什麼可能有用", _e(R["logic"])),
          ("規則", _e(RULE_FULL[k])), ("現在", _e(now_text(k, _n(B, k, mk), short=False)))]
    if cv.get("cagr") is not None:
        kv.append(("全部資金只照這一條", _e(f"{(x.get('a') or '')[:4]} 年起年化 {_pc(cv.get('cagr'), 1, True)}、最大回撤 {_pc(cv.get('mdd'))}、"
                                            f"在場 {_pc(cv.get('expo'))} 的時間；一直抱著年化 {_pc(bh.get('cagr'), 1, True)}、最大回撤 {_pc(bh.get('mdd'))}"
                                            "（其他時間空手、不算利息；這些規則適合當加碼的時機，不適合全部的錢只照一條）")))
    kvh = '<dl class="cdkv">' + "".join(f"<dt>{_e(a)}</dt><dd>{b}</dd>" for a, b in kv) + "</dl>"
    mks = "".join(_mk_row(B, k, m) for m in R["mk"])
    mtab = ('<div class="cdtw"><table class="cdt"><thead><tr><th>市場</th><th>判定</th><th>次數</th><th>賺錢（任一天）</th>'
            '<th>中位數</th><th>排除極端</th><th>最差</th><th>最大跌幅（最差一次）</th><th>近 10 年</th><th>參數鄰近</th>'
            '<th>亂排</th><th>二項</th></tr></thead><tbody>' + mks + "</tbody></table></div>")
    return (f'<details class="cdcard" id="rare-{k}"><summary><span class="cdh"><b>{_e(R["name"])}</b>'
            f'<span class="cdm">{_e(S.NAMES[mk])}・{S.TIER_MARK[t]}・{_e(lab)}</span></span></summary><div class="cdb">{kvh}'
            f'<h4>各市場（主要市場＝{_e(S.NAMES[mk])}）</h4>{mtab}'
            f'<h4>另外看的期間（{_e(S.NAMES[mk])}）</h4>{_outs(x) or "<p class=cdn>—</p>"}'
            f'<h4>每一次（{_e(S.NAMES[mk])}）</h4>{_events(x)}</div></details>')


def research_body(B: dict | None = None) -> str:
    B = B or load()
    res = B.get("res")
    if not res:
        return '<p class="rnote">研究檔還沒產生（TZ=Asia/Taipei python3 scripts/run_rare.py）。</p>'
    asof = res.get("asof") or {}
    head = ('<p class="cdn">九條「一年頂多出現一兩次、出現之後勝率高」的規則，參數照原作者的說法，規則在算報酬之前寫定'
            f'（規格 rarespec VER {S.VER}，{S.SPEC_DATE}）。S&amp;P 500 從 1950 年、其他市場從資料第一天之後滿一年算到 '
            f'{_e(asof.get("spx") or "")}（台股 {_e(asof.get("tw") or "")}）；指數不含息、扣 ETF 成本。'
            '判定同總經策略落底型：至少 5 次、賺錢的比例 60% 以上而且不低於任一天、中位數與排除極端的平均都大於 0；'
            '★＝近 10 年與參數鄰近也過，●＝只有全期間過。<b>建議試用</b>＝主要市場 ★，而且來源發表之後、S&amp;P 500 1950 年以前'
            '（各有 3 次以上的話）也不低於任一天；<b>可以觀察</b>＝主要市場 ●，或 ★ 但另外那段沒過。'
            '9 條規則 × 最多 5 個市場共 33 組，碰巧好看的一定有幾組，所以只看主要市場。'
            f'<a download="rare_trades.csv" href="{_csv(B)}">下載每一次（CSV，全部市場）</a></p>')
    summ = ('<div class="cdtw"><table class="cdt"><thead><tr><th>規則</th><th>主要市場</th><th>多久一次</th><th>次數</th>'
            '<th>賺錢（任一天）</th><th>每次中位數</th><th>最差一次</th><th>判定</th><th>建議</th><th>現在</th></tr></thead><tbody>'
            + "".join(_summary_row(B, R) for R in S.RULES) + "</tbody></table></div>")
    note = ('<p class="cdn">欄位：任一天＝評估期間每一天都當買進日、抱一樣多天、扣一樣的成本；排除極端＝去掉最好和最差各 5%'
            '（次數少於 20 時各去掉一次）；最大跌幅＝抱的期間從最高收盤跌到之後最低收盤（和大跌同一個算法），列最差的那一次；亂排＝把買進日整段挪動 400 次，賺錢比例不比實際差的比例；'
            '二項＝如果每次賺錢的機率等於任一天，出現這麼多次賺錢的機率。美股的日子是美國的交易日。</p>')
    return f'<div class="rzbox" id="rare-body">{head}{summ}{note}' + "".join(_card(B, R) for R in S.RULES) + "</div>"


CSS = """
.rzbox{margin:4px 0 8px}
.rzbox .rztr{max-height:420px;overflow:auto}
"""
