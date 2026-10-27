"""台指期早盤策略（股票期貨人生）的頁面（docs/lab_fut_plan.md 第 6 節；資料 arm/lab/futres.py、futpre.py）。

  board_rows()     配置頁・策略表「候選」一列：名稱連到研究紀錄頁、一句規則、今天＝開盤前取樣了幾天（滿 60 天看結果）
  research_body()  研究紀錄頁「台指期早盤」一段：狀態、規則、最好情況（偷看版）的成績與每一筆（可下載）、
                   期貨之後有沒有往 E 的方向走、每天的落差、開盤前取樣
配置頁照主頁面的用字（docs/lab_ia_v5_plan.md 第 8 節）；研究紀錄頁不受限。版面借用 candpage 的 cd* 樣式（研究紀錄頁已載入）。
"""
from __future__ import annotations

import html
from urllib.parse import quote

from . import futpre as FP
from . import futres as FR
from . import futspec as P
from . import store

WHY = {"stop": "停損", "trail": "移動停損", "target": "停利", "eod": "收盤前出場", "close": "最後一筆"}
SIDE = {"long": "做多", "short": "做空"}


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "")


def _hms(s) -> str:
    if s is None:
        return "—"
    s = int(s)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _pt(x, d: int = 1, sign: bool = True) -> str:
    if x is None:
        return "—"
    s = f"{abs(x):,.{d}f}"
    return (("+" if x > 0 else "−" if x < 0 else "") if sign else ("−" if x < 0 else "")) + s


def _pc(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def load() -> dict:
    R = store.read_json(FR.OUT, {}) or {}
    return {"R": R, "pre": store.dates(FP.KIND)}


def _sim(r: dict, k: str) -> dict | None:
    x = r.get(k)
    return dict(zip(FR.SIM_COLS, x)) if x else None


def board_rows(B: dict | None = None) -> list[dict]:
    """策略表一列（狀態固定「候選」：還在記錄，滿 60 天才看結果）。研究檔讀不到也列（今天寫還沒開始）。"""
    B = B or load()
    R, pre = B["R"], B["pre"]
    n_la = ((R.get("lookahead") or {}).get("n_days")) or 0
    today = f"記錄中・取樣 {len(pre)} 天" if pre else "記錄中・還沒開始取樣"
    sub = (f"台指期每一筆成交已存 {n_la} 天；" if n_la else "") + f"開盤前取樣滿 {P.JUDGE['days']} 天看結果"
    return [{"id": "tw:fut", "name": "台指期早盤（股票期貨人生）", "mk": "台股", "mkk": "tw", "type": "指數型", "st": "cand",
             "how": "開盤前用權值股的試撮估算現貨開在哪，跟台指期比；差得多就順著做多或做空一口台指期，等期貨追上",
             "href": "x9r.html#fut", "go": {}, "today": today, "sub": sub}]


def _summary(s: dict) -> str:
    if not s.get("n"):
        return "還沒有交易"
    return (f"{s['n']} 筆・扣成本後平均每筆 {_pt(s['mean'])} 點、中位數 {_pt(s['median'])} 點・賺錢 {_pc(s['win'])}・"
            f"最好 {_pt(s['best'])}、最差 {_pt(s['worst'])}")


def _csv(rows: list[dict]) -> str:
    head = "日期,契約,方向,落差E,門檻,進場時間,進場價,出場時間,出場價,出場原因,扣成本後點數,最多賺,最多賠"
    lines = [head]
    for r in rows:
        x = _sim(r, FR.SIDE_KEY[r["side"]])
        if not x:
            continue
        lines.append(",".join(str(v) for v in (r["d"], r["c"], SIDE[r["side"]], r["e"], r["th"], _hms(x["t_in"]), x["px_in"],
                                                _hms(x["t_out"]), x["px_out"], WHY.get(x["why"], x["why"]), x["net"],
                                                x["mfe"], x["mae"])))
    return "data:text/csv;charset=utf-8," + quote("﻿" + "\n".join(lines))


def _trades_html(rows: list[dict]) -> str:
    tr = [r for r in rows if r.get("side") and _sim(r, FR.SIDE_KEY[r["side"]])]
    if not tr:
        return '<p class="cdn">還沒有交易（門檻要先累積 10 天）。</p>'
    body = []
    for r in tr:
        x = _sim(r, FR.SIDE_KEY[r["side"]])
        body.append(f'<tr><td>{_md(r["d"])}</td><td>{SIDE[r["side"]]}</td><td>{_pt(r["e"])}</td><td>{_pt(r["th"], sign=False)}</td>'
                    f'<td>{_hms(x["t_in"])}・{x["px_in"]:,}</td><td>{_hms(x["t_out"])}・{x["px_out"]:,}</td>'
                    f'<td>{WHY.get(x["why"], x["why"])}</td><td>{_pt(x["net"])}</td><td>{_pt(x["mfe"], 0)}／{_pt(x["mae"], 0)}</td></tr>')
    return ('<div class="cdtw"><table class="cdt"><thead><tr><th>日期</th><th>方向</th><th>落差 E</th><th>門檻</th><th>進場</th>'
            '<th>出場</th><th>原因</th><th>扣成本後（點）</th><th>最多賺／賠</th></tr></thead><tbody>' + "".join(body)
            + f'</tbody></table></div><p class="cdn"><a download="fut_trades.csv" href="{_csv(tr)}">下載每一筆（CSV）</a></p>')


def _catch_html(C: dict, at: list[str]) -> str:
    al, td = C.get("all") or [], C.get("traded") or []
    if not al:
        return ""
    rows = []
    for i, a in enumerate(al):
        t = td[i] if i < len(td) else {}
        rows.append(f'<tr><td>{_e(a["at"])}</td><td>{_pc(a.get("agree"))}</td><td>{_pt(a.get("mean"))}</td>'
                    f'<td>{_pc(t.get("agree"))}・中位數 {_pt(t.get("median"), 0)}</td></tr>')
    return ('<div class="cdtw"><table class="cdt"><thead><tr><th>到</th><th>和 E 同方向（全部的日子）</th><th>順著 E 平均（點）</th>'
            f'<th>有做的 {td[0]["n"] if td else 0} 天</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>")


def _days_html(days: list[dict]) -> str:
    body = []
    for r in reversed(days):
        if "e" not in r:
            body.append(f'<tr><td>{_md(r["d"])}</td><td colspan="8">{_e(r.get("skip") or "")}</td></tr>')
            continue
        body.append(f'<tr><td>{_md(r["d"])}</td><td>{_e(r["c"])}</td><td>{r["f"]:,}</td><td>{r["est"]:,.1f}</td>'
                    f'<td>{_pt(r["basis"])}</td><td>{_pt(r["div"])}</td><td>{_pt(r["e"])}</td>'
                    f'<td>{_pt(r["th"], sign=False)}</td><td>{SIDE.get(r.get("side"), "不做")}</td></tr>')
    return ('<div class="cdtw"><table class="cdt"><thead><tr><th>日期</th><th>契約</th><th>08:59:30 期貨</th><th>估算的開盤</th>'
            '<th>前一天價差</th><th>除權息</th><th>落差 E</th><th>門檻</th><th>做什麼</th></tr></thead><tbody>'
            + "".join(body) + "</tbody></table></div>")


def research_body(B: dict | None = None) -> str:
    B = B or load()
    R, pre = B["R"], B["pre"]
    la = R.get("lookahead") or {}
    days = la.get("days") or []
    rows = [r for r in days if "e" in r]
    pts = rows[-1]["pts"] if rows else None
    m = la.get("main") or {}
    cmp_ = la.get("compare") or {}
    first, last = (rows[0]["d"], rows[-1]["d"]) if rows else (None, None)
    head = (f'<p class="cdn">狀態：<b>候選・記錄中</b>。台指期每一筆成交已存 {la.get("n_days", 0)} 天'
            + (f'（{_md(first)}～{_md(last)}）' if first else "")
            + f'；開盤前取樣 {len(pre)} 天' + (f'（最近 {_md(pre[-1])}）' if pre else "（每個交易日 08:58～09:00:15，從 10/28 開始）")
            + f'。即時版滿 {P.JUDGE["days"]} 個交易日、至少 {P.JUDGE["min_trades"]} 筆才判定；不放進配置（期貨是另一個帳戶）。</p>')
    rule = [
        ("想法", _e("台股現貨 09:00 才開盤、台指期 08:45 就在交易。開盤前用權值股的試撮估算現貨會開在哪，跟台指期當下的價格比（扣掉昨天的價差）；"
                    "現貨估得比期貨強就做多期貨、弱就做空，等期貨追上（作者「股票期貨人生」的說法，進場資格「格數」沒有公開）。")),
        ("落差 E", _e("估算的開盤水準 ＋（前一天 13:30 的期貨價 − 13:30 收盤指數）＋ 今天除權息讓指數少掉的點數 − 08:59:30 的期貨價；"
                      "E 是正的做多、負的做空。契約用近月，結算日（第三個星期三）改用下個月。")),
        ("什麼時候做", _e(f"今天的 |E| 排在過去 {P.TH_WINDOW} 個有算出 E 的交易日前 {P.TH_TOP_PCT}% 大才做（跟作者一樣常做）；"
                          f"過去不到 {P.TH_MIN_HIST} 天不做。一天最多一筆、一口大台。")),
        ("進出場", _e("08:59:30 之後第一筆成交進場（滑價 1 點）；停損、1 分 K 移動停損、停利照作者的點數，依指數換算"
                      + (f"（最近一天：停損 {pts[0]}、讓 {pts[1]}、移動 {pts[2]}、停利 {pts[3]} 點）" if pts else "")
                      + "；13:44 還沒出場就出。")),
        ("成本", _e("期交稅 0.002%（約 0.9 點）＋手續費 60 元（0.3 點）每邊，另加滑價。")),
        ("最好的情況", _e("即時版的試撮要每天開盤前存（從 10/28 開始）；在那之前只能用「偷看版」：假設 08:59 就知道每一檔真正的開盤價，"
                          "照前一天的市值比重算開盤水準。偷看版只是最好的情況，連它都賺不到就淘汰。")),
    ]
    kv = '<dl class="cdkv">' + "".join(f"<dt>{_e(k)}</dt><dd>{v}</dd>" for k, v in rule) + "</dl>"
    perf = [("照規則", _e(_summary(m)) + (f'；方向亂選平均不比它差的比例 {_pc(la.get("placebo_p"))}' if la.get("placebo_p") is not None else "")),
            ("作者原點數", _e(_summary(cmp_.get("raw_points") or {}))),
            ("每天都做多", _e(_summary(cmp_.get("always_long") or {}))),
            ("每天都做空", _e(_summary(cmp_.get("always_short") or {})))]
    pkv = '<dl class="cdkv">' + "".join(f"<dt>{_e(k)}</dt><dd>{v}</dd>" for k, v in perf) + "</dl>"
    ver = _e(R.get("spec_ver") or P.VER)
    span = _e(f'{la.get("n_days", 0)} 天，滿 {P.JUDGE["days"]} 天才判定')
    return (f'<div class="fzbox" id="fut-body">{head}'
            '<details class="cdcard" open><summary><span class="cdh"><b>規則</b>'
            f'<span class="cdm">futspec VER {ver}</span></span></summary><div class="cdb">{kv}</div></details>'
            '<details class="cdcard" open><summary><span class="cdh"><b>最好的情況（偷看版）</b>'
            f'<span class="cdm">{span}</span></span></summary><div class="cdb">{pkv}<h4>每一筆</h4>{_trades_html(rows)}'
            '<h4>期貨之後有沒有往 E 的方向走（只描述）</h4>'
            f'{_catch_html(la.get("catchup") or {}, R.get("catch_at") or [])}'
            '<p class="cdn">偷看版的 E 用的是 09:00 真正的開盤價，裡面已經有 08:59:30～09:00 這 30 秒的消息，所以「同方向」的比例一定高估。</p>'
            '</div></details>'
            f'<details class="cdcard"><summary><span class="cdh"><b>每天的落差</b><span class="cdm">{len(days)} 天</span></span></summary>'
            f'<div class="cdb">{_days_html(days)}</div></details></div>')


CSS = """
.fzbox{margin:4px 0 8px}
"""
