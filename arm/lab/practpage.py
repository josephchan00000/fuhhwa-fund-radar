"""實測區（訊號總覽「研究細節」最上面一塊；docs/lab_practice_page_plan.md；規則與判定 practspec VER 1）。

把網頁的用法當成一套操作方法來驗證：照溫度計調整股票部位、照總經策略做，每年 1 月 1 日只用當時拿得到的資料決定，
和「每天固定拿一樣多的股票」與「一直持有」比。研究檔 data/lab/practsim_research.json（scripts/run_practsim.py），
前瞻紀錄 data/lab/practsim_live.json（practlive，只有 CI 寫回）。

  payload(R, live, fw, since)   頁面裡的小份資料（總表、候選與門檻、今天該拿幾成、前瞻紀錄）→ SG.pr
  market_json(R, mk)            一個市場的細節與每週序列 → dashboard/x9pr-{市場}.json（點到那個市場才下載）
  html(P)                       實測區的骨架（總表與重點在伺服器端畫好；每一格的細節由 JS 畫）
class 一律 pr 開頭；JS 函式一律 pr 開頭（插在訊號總覽 JS 的初始化之前，和它共用 SG、esc、ymd）。
"""
from __future__ import annotations

import html as _h
import json

from . import practspec as S
from . import xstratspec as XS

MK_SHORT = {"tw": "台股", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}
MK_TINY = {"tw": "台股", "spx": "S&P", "ixic": "那指", "ndx": "那100", "sox": "費半"}
SHORT = {"A1": "短線警示多 → 一半", "A2": "中線警示多 → 一半", "A3": "長線警示多 → 一半", "A4": "兩支以上警示多 → 一半",
         "B1": "短線偏多多 → 加碼", "D1": "偏多全部照做", "M1": "總經策略 ★ 照做", "M2": "總經策略 ★＋● 照做"}
DESC = {
    "A1": "每週最後一個交易日看景氣頁的短線溫度計（看 1 個月）：警示那一邊的票數比過去 10 年三分之二的週多，下一個交易日收盤把股票降到一半，其他時候拿滿。",
    "A2": "同 A1，看中線溫度計（看 3 個月）。",
    "A3": "同 A1，看長線溫度計（看 12 個月）。",
    "A4": "同 A1，但要短線、中線、長線三支溫度計裡至少兩支警示票數都「多」才降到一半。",
    "B1": "反過來用偏多那一邊：短線偏多的票數比過去 10 年三分之二的週多就拿滿，其他時候拿一半。",
    "D1": "今天的重點偏多那一邊只要有東西就拿滿，一個都沒有就空手（＝「好訊號全部照做」）。",
    "M1": "每年 1 月 1 日只用之前的資料重新判定每一條總經策略，那一年照當時判定為 ★ 的策略做：每一條一份、平均分，各自照規則持有或空手。",
    "M2": "同 M1，★ 與 ● 都做（＝策略頁「這一期」列出來的）。",
}
GROUPS = (("t", "溫度計調部位", ("A1", "A2", "A3", "A4", "B1", "D1")), ("x", "總經策略照做", ("M1", "M2")))
VIDX = {"better": 0, "same": 1, "worse": 2}


def _e(s) -> str:
    return _h.escape(str(s), quote=True)


def _p(x, k: int = 1):
    return None if x is None else round(100.0 * float(x), k)


def _ymd(d: str | None) -> str:
    """2026-10-21 → 2026/10/21（同頁面 JS 的 ymd）。"""
    if not d:
        return ""
    y, m, dd = str(d)[:10].split("-")
    return f"{int(y)}/{int(m)}/{int(dd)}"


def _role(k: str, page: dict) -> str:
    """cand_ok 候選・過門檻／cand_no 候選・沒過／ctrl 對照。"""
    if k not in S.PAGE_RULES:
        return "ctrl"
    return "cand_ok" if (page.get(k) or {}).get("ok") else "cand_no"


# ── 頁面裡的小份資料 ───────────────────────────────────────────────────────────

def payload(R: dict | None, live: dict | None = None, fw: dict | None = None, since: dict | None = None) -> dict:
    """since＝{市場: 開始記的資料日}。"""
    if not R or not R.get("mk"):
        return {"ok": False}
    page = R.get("page") or {}
    g: dict = {}
    for mk in S.MARKETS:
        M = (R["mk"].get(mk) or {}).get("rules") or {}
        for k, x in M.items():
            f = x["full"]
            g.setdefault(k, {})[mk] = [VIDX[x["v"]], _p(f["rule"]["cagr"]), _p(f["fix"]["cagr"]), _p(f["bh"]["cagr"]),
                                       _p(f["rule"]["mdd"], 0), _p(f["fix"]["mdd"], 0), _p(f["bh"]["mdd"], 0), _p(f["wbar"], 0)]
    rules = [{"k": k, "s": SHORT[k], "n": (S.THERMO_RULES.get(k) or S.STRAT_RULES.get(k))["name"], "d": DESC[k], "g": gk,
              "r": _role(k, page)} for gk, _, ks in GROUPS for k in ks]
    return {"ok": True, "spec": S.SPEC_DATE, "run": R.get("run"), "mks": list(S.MARKETS), "mkn": MK_SHORT,
            "rules": rules, "g": g, "page": page, "pmin": S.PAGE_MIN_BETTER, "pmax": S.PAGE_MAX_WORSE,
            "vn": [S.VERDICT_NAMES[v] for v in S.VERDICTS], "live": live or {}, "fw": fw or {}, "since": since,
            "sn": {s["k"]: s["name"] for s in XS.STRATS}, "dmin": 63}


# ── 一個市場的細節與每週序列 ─────────────────────────────────────────────────────

def _per(c: dict) -> dict:
    """一段期間：起訖、平均部位、照做／固定持有／一直持有的 [年化, 最大回撤, 夏普, 最差一年]（照做多一年調整幾次）。"""
    def four(x):
        return [_p(x["cagr"]), _p(x["mdd"]), None if x.get("sharpe") is None else round(x["sharpe"], 2), _p(x.get("worst"))]
    return {"a": c["rule"]["a"], "z": c["rule"]["z"], "w": _p(c["wbar"]), "r": four(c["rule"]) + [round(c["rule"].get("adj") or 0, 1)],
            "f": four(c["fix"]), "b": four(c["bh"])}


def market_json(R: dict, mk: str) -> str:
    M = R["mk"].get(mk) or {}
    det = {}
    for k, x in (M.get("rules") or {}).items():
        f = x["full"]
        fy, by = dict(f["fix"]["yearly"]), dict(f["bh"]["yearly"])
        det[k] = {"v": VIDX[x["v"]], "ci": None if not x.get("ci") else [round(v, 2) for v in x["ci"]], "now": round(x["now"], 3),
                  "p": {h: _per(x[h]) for h in ("full", "h1", "h2", "rec")},
                  "y": [[y, _p(v), _p(fy.get(y)), _p(by.get(y))] for y, v in f["rule"]["yearly"]],
                  "b": [[b["pk"], b["tr"], _p(b["bh"]), _p(b["rule"]), _p(b["fix"]), 1 if b.get("open") else 0] for b in x.get("bears") or []],
                  "empty": x.get("empty") or []}
    out = {"mk": mk, "det": det, "t": M.get("t_series"), "x": M.get("x_series"), "sel": M.get("x_sel"), "tiers": M.get("x_tiers"),
           "held": M.get("x_held"), "last": M.get("t_last"), "ta": M.get("t_a"), "xa": M.get("x_a")}
    return json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ── 骨架 ──────────────────────────────────────────────────────────────────────

def _key_points(P: dict) -> str:
    """三句重點（全部由資料算）。"""
    if not P.get("ok"):
        return ""
    page, g = P["page"], P["g"]
    out = []
    ok = [k for k in S.PAGE_RULES if (page.get(k) or {}).get("ok")]
    no = [k for k in S.PAGE_RULES if k not in ok]
    rule = f"至少 {S.PAGE_MIN_BETTER} 個市場比固定持有好、{S.PAGE_MAX_WORSE} 個比較差"
    if ok:
        out.append("事前選的 3 個候選裡，過門檻（" + rule + "）的只有："
                   + "、".join(f"<b>{_e(SHORT[k])}</b>（{page[k]['better']} 好 {page[k]['worse']} 差）" for k in ok) + "。")
    else:
        out.append(f"事前選的 3 個候選都沒有過門檻（{rule}）。")
    if no:
        out.append("沒過的：" + "、".join(f"{_e(SHORT[k])}（{page[k]['better']} 好 {page[k]['worse']} 差）" for k in no if k in page)
                   + "；8 種用法全部列在下面，沒過的照樣可以研究。")
    m = g.get("M2") or {}
    if m:
        mdd = [v[4] for v in m.values() if v[4] is not None]
        bmdd = [v[6] for v in m.values() if v[6] is not None]
        w = [v[7] for v in m.values() if v[7] is not None]
        ratio = [v[1] / v[3] for v in m.values() if v[1] is not None and v[3]]
        if mdd and bmdd and w and ratio:
            out.append(f"總經策略 ★＋● 照做：最慘跌 {min(mdd):.0f}%～{max(mdd):.0f}%（一直持有 {min(bmdd):.0f}%～{max(bmdd):.0f}%），"
                       f"但平均只拿 {min(w):.0f}%～{max(w):.0f}% 的股票，年化是一直持有的 {min(ratio) * 100:.0f}%～{max(ratio) * 100:.0f}%——"
                       "<b>少賠很多、也賺得比較少</b>。")
    return '<ul class="prkey">' + "".join(f"<li>{x}</li>" for x in out) + "</ul>"


def _grid(P: dict) -> str:
    if not P.get("ok"):
        return ""
    head = "".join(f'<th scope="col"><span class="prl">{_e(MK_SHORT[m])}</span><span class="prs">{_e(MK_TINY[m])}</span></th>'
                   for m in P["mks"])
    rows = []
    rl = {r["k"]: r for r in P["rules"]}
    role_txt = {"cand_ok": "候選・過門檻", "cand_no": "候選・沒過", "ctrl": "對照"}
    for gk, gname, ks in GROUPS:
        rows.append(f'<tr class="prgh"><th colspan="{1 + len(P["mks"])}" scope="rowgroup">{_e(gname)}</th></tr>')
        for k in ks:
            r = rl[k]
            cells = []
            for mk in P["mks"]:
                v = (P["g"].get(k) or {}).get(mk)
                if not v:
                    cells.append('<td class="prc0">—</td>')
                    continue
                vn = S.VERDICT_NAMES[S.VERDICTS[v[0]]]
                lab = f"{MK_SHORT[mk]}・{k} {SHORT[k]}：{vn}，年化 {v[1]}%、最大回撤 {v[4]:.0f}%（固定持有 {v[2]}%、{v[5]:.0f}%）"
                cells.append(f'<td><button type="button" class="prc prv{v[0]}" data-r="{k}" data-m="{mk}" aria-label="{_e(lab)}">'
                             f'<span class="prvt">{_e(("好", "差不多", "差")[v[0]])}</span>'
                             f'<span class="prvn">{v[1]:.1f}%｜{v[4]:.0f}%</span></button></td>')
            rows.append(f'<tr><th scope="row" class="prrn"><span class="prk">{k}</span>{_e(SHORT[k])}'
                        f'<span class="prro prro-{r["r"]}">{_e(role_txt[r["r"]])}</span></th>' + "".join(cells) + "</tr>")
    return ('<div class="prgw"><table class="prg"><thead><tr><th scope="col" class="prrn">用法</th>' + head + "</tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>"
            '<p class="prgn">每一格：和「每天固定拿一樣多的股票」比的判定，下面是<b>年化｜最大回撤</b>。點一格看那一格的細節。'
            "候選＝事前選來決定能不能照做的；對照＝一起算來比較的。</p>")


def _since_txt(since: dict) -> str:
    """{市場: 日期} → 「2026/10/22」或「台股 2026/10/22、美股 2026/10/21」（美股的資料日是前一個美股交易日）。"""
    tw = since.get("tw")
    us = sorted({d for mk, d in since.items() if mk != "tw"})
    if tw and us and us != [tw]:
        return f"台股 {_ymd(tw)}、美股 {'／'.join(_ymd(d) for d in us)}"
    return "／".join(_ymd(d) for d in sorted(set(since.values())))


def _forward(P: dict) -> str:
    """前瞻紀錄：每一格上面＝目前照規則該拿幾成，下面＝開始記以來照做的報酬（和固定持有、一直持有比）。"""
    fw = P.get("fw") or {}
    live = P.get("live") or {}
    since = P.get("since") or {}
    if not since:
        return ('<div class="prfw" id="prfw"><h4>前瞻紀錄</h4><p class="note">還沒有紀錄：上線之後，每次建頁都會記下每種用法、每個市場那天該拿幾成，'
                "從那天起算真的照做的成績（不到 3 個月只寫「累積中」，不下結論）。</p></div>")
    head = "".join(f'<th scope="col"><span class="prl">{_e(MK_SHORT[m])}</span><span class="prs">{_e(MK_TINY[m])}</span></th>' for m in P["mks"])
    any_ret = any(x.get("ret") is not None for m in fw.values() for x in m.values())
    body = []
    for gk, gname, ks in GROUPS:
        body.append(f'<tr class="prgh"><th colspan="{1 + len(P["mks"])}" scope="rowgroup">{_e(gname)}</th></tr>')
        for k in ks:
            tds = []
            for mk in P["mks"]:
                x = (fw.get(mk) or {}).get(k) or {}
                lt = ((live.get(mk) or {}).get("t") or {}).get(k)
                now = x.get("now") if x.get("now") is not None else lt
                if now is None:
                    tds.append('<td class="prc0">—</td>')
                    continue
                h = f'<b><span class="prfx">拿 </span>{100 * now:.0f}%</b>'
                if x.get("ret") is not None:
                    h += (f'<span class="prfr">照做 {100 * x["ret"]:+.1f}%</span>'
                          f'<span class="prfs">固定 {100 * x["fix"]:+.1f}%・一直 {100 * x["bh"]:+.1f}%</span>')
                    if not x.get("ok"):
                        h += f'<span class="prfa">累積中・{x["n"]} 天</span>'
                tds.append(f"<td>{h}</td>")
            body.append(f'<tr><th scope="row" class="prrn"><span class="prk">{k}</span>{_e(SHORT[k])}</th>' + "".join(tds) + "</tr>")
    first = "" if any_ret else '<p class="prfn">今天是開始記的第一天：下一個交易日起才算得出照做的報酬。</p>'
    return (f'<div class="prfw" id="prfw"><h4>前瞻紀錄<span class="sub">{_e(_since_txt(since))} 開始記</span></h4>'
            '<p class="prgn">每一格上面是<b>目前照規則該拿幾成</b>，下面是開始記以來照做的報酬（固定＝每天固定拿一樣多、一直＝一直持有）。</p>'
            + first + '<div class="prgw"><table class="prg prft"><thead><tr><th scope="col" class="prrn">用法</th>' + head + "</tr></thead><tbody>"
            + "".join(body) + '</tbody></table></div><p class="note">溫度計的用法照規則只在每週最後一個交易日決定、下一個交易日收盤調整；'
            "總經策略每天照各策略的部位。沒有建頁的日子沿用前一筆。不到 3 個月（63 個交易日）只寫「累積中」，不下結論。</p></div>")


METHOD = ('<details class="prm"><summary>怎麼算、要注意什麼</summary><div class="prmb">'
          "<p><b>怎麼算</b>：每年 1 月 1 日只用「之後的結果在那天以前已經走完」的資料，決定那一年溫度計每個訊號投哪一邊、"
          "總經策略每一條是 ★、●、○ 還是 —；那一年就照那時的決定操作，看之後真的會怎樣。溫度計每週最後一個交易日收盤看一次、"
          "下一個交易日收盤調整；成本台股每一邊 0.1%、美股 0.025%（總經策略各用自己的成本）。</p>"
          "<p><b>和誰比</b>：一直持有，以及<b>每天固定拿一樣多的股票</b>（例：規則平均拿 4 成，就和每天固定拿 4 成比）。"
          "部位低本來就會少賠、也少賺；和固定持有比，才看得出用法本身有沒有幫助。</p>"
          "<p><b>判定</b>：比固定持有好＝全期間「報酬 ÷ 波動」（夏普）比較高、最大回撤沒有比較大，而且前後兩半的夏普都比較高；"
          "比固定持有差＝全期間與前後兩半都比較低；其他＝差不多。空手的部分沒有利息，所以固定持有的夏普和一直持有一樣。</p>"
          f"<p><b>能不能照做</b>：事前只選 A1、B1、M2 三個候選，門檻是至少 {S.PAGE_MIN_BETTER} 個市場好、{S.PAGE_MAX_WORSE} 個差；"
          f"規則與門檻在算任何結果之前寫定（practspec VER {S.VER}，{S.SPEC_DATE}）。A2、A4 看起來比 A1 好，但它們是對照，不能看到結果再換。</p>"
          "<p><b>要注意</b>：①總經策略的規則是今年從文獻挑的，逐年重新判定只去掉我們自己偷看，去不掉原作者用過那段資料，2008 年以後比較乾淨；"
          "②價格不含股息、空手沒有利息（一直持有少算股息，台股每年約 3%～4%）；③美股漲跌家數是 S&P 500 歷史成分股自算，2010 年以前有存活偏誤；"
          "④台股的溫度計票數會隨著有資料的指標變多而變多，長線警示「多」的週比較多；⑤溫度計規則的類似版本在設計時看過，只能靠前瞻紀錄證明。</p>"
          "<p><b>圖</b>以每週最後一個交易日畫；表與數字用每天的資料算，所以圖上的最大回撤可能比數字小一點。</p></div></details>")


def html(P: dict) -> str:
    if not P.get("ok"):
        return ""
    return ('<div class="pr" id="pr"><div class="prhd"><h3>實測：照網頁的用法實際做</h3>'
            f'<span class="sub">每年 1 月 1 日只用當時拿得到的資料決定（practspec VER {S.VER}，{_e(S.SPEC_DATE)} 寫定）</span></div>'
            '<p class="prlead">把網頁的用法當成一套操作方法：看溫度計調整股票部位，或照策略頁的總經策略做。'
            "每一種都和「每天固定拿一樣多的股票」比，才知道用法本身有沒有幫助。</p>"
            + _key_points(P) + _grid(P) + '<div class="prd" id="prd" aria-live="polite"><p class="note">點總表的一格，看那一格的數字、圖和逐年成績。</p></div>'
            + _forward(P) + METHOD + "</div>")


CSS = """
.pr{border:1px solid var(--line);border-radius:14px;padding:14px 16px 12px;background:var(--panel);margin:0 0 18px}
.prhd{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 10px}.prhd h3{margin:0;font-size:16.5px}
.prhd .sub{font-size:12px;color:var(--mut)}
.prlead{margin:6px 0 4px;font-size:13.5px;color:var(--ink2);line-height:1.7}
.prkey{margin:6px 0 10px;padding-left:18px;font-size:13.5px;line-height:1.75}.prkey li{margin:2px 0}
.prgw{overflow-x:auto;margin:6px 0 2px}
.prg{border-collapse:separate;border-spacing:3px;width:100%;font-size:13px}
.prg th{font-weight:600;color:var(--ink2);text-align:center;padding:3px 4px;white-space:nowrap}
.prg th.prrn{text-align:left;font-weight:500;color:var(--ink);white-space:normal;min-width:150px;padding-right:8px}
.prg tr.prgh th{text-align:left;font-size:12px;color:var(--mut);font-weight:600;padding-top:8px;border-bottom:1px solid var(--line)}
.prk{display:inline-block;min-width:24px;font-weight:700;color:var(--ink2);margin-right:4px;font-variant-numeric:tabular-nums}
.prro{display:inline-block;margin-left:6px;font-size:11px;padding:0 6px;border-radius:999px;border:1px solid var(--line2);color:var(--mut);white-space:nowrap}
.prro-cand_ok{border-color:var(--acc);color:var(--acc);font-weight:600}.prro-cand_no{color:var(--ink2)}
.prg td{padding:0;text-align:center}
.prc{font:inherit;width:100%;min-width:74px;padding:5px 4px;border-radius:9px;border:1px solid var(--line2);background:var(--bg);color:var(--ink);
cursor:pointer;display:flex;flex-direction:column;align-items:center;gap:1px;line-height:1.25}
.prc:hover{border-color:var(--acc)}.prc:focus-visible{outline:2px solid var(--acc);outline-offset:1px}
.prc.on{box-shadow:0 0 0 2px var(--acc) inset;border-color:var(--acc)}
.prvt{font-weight:700;font-size:13.5px}.prvn{font-size:11.5px;color:var(--ink2);font-variant-numeric:tabular-nums}
.prv0{background:var(--accbg);border-color:var(--acc)}.prv0 .prvt{color:var(--acc)}
.prv2{background:rgba(180,83,9,.08);border-color:var(--warn)}.prv2 .prvt{color:var(--warn)}
.prc0{color:var(--mut);font-size:12px}
.prgn{font-size:12px;color:var(--mut);margin:4px 0 8px;line-height:1.7}
.prs{display:none}
.prd{margin:12px 0 4px;padding-top:12px;border-top:1px solid var(--line)}
.prdh{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px}.prdh h4{margin:0;font-size:15.5px}
.prdv{font-size:12.5px;padding:1px 9px;border-radius:999px;border:1px solid var(--line2);font-weight:600}
.prdv.prv0{color:var(--acc)}.prdv.prv2{color:var(--warn)}
.prmk{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0 2px}
.prmk button,.prsp button,.prmore{font:inherit;font-size:12.5px;padding:2px 10px;border-radius:999px;border:1px solid var(--line2);background:var(--bg);color:var(--ink2);cursor:pointer}
.prmk button.on,.prsp button.on{background:var(--accbg);border-color:var(--acc);color:var(--ink);font-weight:600}
.prdesc{font-size:13px;color:var(--ink2);margin:8px 0 2px;line-height:1.7}
.prsum{font-size:14px;margin:8px 0;line-height:1.75}
.prkp{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:10px 0}
.prt{border:1px solid var(--line);border-radius:10px;padding:7px 9px;min-width:0}
.prt .lb{font-size:12px;color:var(--mut)}.prt .vl{font-size:20px;font-weight:600;line-height:1.3}
.prt .cp{font-size:11.5px;color:var(--ink2);line-height:1.55;font-variant-numeric:tabular-nums}
.prt .cp i{font-style:normal;color:var(--mut)}
.prsp{display:flex;gap:4px;align-items:center;margin:10px 0 4px;flex-wrap:wrap}.prsp .lbx{font-size:12px;color:var(--mut);margin-right:4px}
.prrd{font-size:12.5px;color:var(--ink2);min-height:22px;line-height:1.7;font-variant-numeric:tabular-nums}
.prrd b{color:var(--ink)}.prrd .lk{display:inline-block;width:14px;height:0;border-top:2px solid;vertical-align:middle;margin:0 3px 0 8px}
.prfig{margin:4px 0 6px}.prfig .cap{font-size:12px;color:var(--mut);margin:6px 0 0}
.prcv svg text{font-size:11px;fill:var(--mut)}.prcv .prpt{font-size:11.5px;fill:var(--ink2);font-weight:600}
.prcv .cap{font-size:11.5px;color:var(--mut);margin:2px 0 0}
.prcv .gl{stroke:var(--line);stroke-width:1}.prcv .bz{fill:var(--card2)}
.prcv .lr{fill:none;stroke:var(--acc);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.prcv .prlp{stroke-width:1.4}
.prcv .lf{fill:none;stroke:var(--ink2);stroke-width:1.6;stroke-dasharray:5 3;stroke-linejoin:round}
.prcv .lb2{fill:none;stroke:var(--mut);stroke-width:1.6;stroke-linejoin:round;opacity:.85}
.prcv .ar{fill:var(--acc);opacity:.10}
.prcv .hv{stroke:var(--ink2);stroke-width:1}.prcv .hit{fill:transparent;cursor:crosshair}
.prlg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink2);margin:2px 0 4px}
.prlg span::before{content:"";display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin-right:5px}
.prlg .r::before{border-color:var(--acc)}.prlg .f::before{border-top:2px dashed var(--ink2)}.prlg .b::before{border-color:var(--mut)}
.prlg .z::before{border:0;height:10px;width:14px;background:var(--card2);border-radius:2px;vertical-align:-1px}
.prtb{width:100%;border-collapse:collapse;font-size:13px;margin:4px 0}
.prtb th{font-weight:600;color:var(--ink2);text-align:right;padding:4px 6px;border-bottom:1px solid var(--line2);white-space:nowrap}
.prtb td{padding:4px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.prtb th.l,.prtb td.l{text-align:left;white-space:normal}.prtb .ng{color:var(--warn)}.prtb .mu{color:var(--mut)}
.prsec{margin:12px 0 2px}.prsec h5{font-size:13.5px;margin:0 0 4px}
.prcols{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 18px}
.prnow{border-left:3px solid var(--acc);padding:6px 10px;margin:10px 0;background:var(--accbg);border-radius:0 8px 8px 0;font-size:13.5px;line-height:1.75}
.prfw{margin:14px 0 4px;padding-top:12px;border-top:1px solid var(--line)}.prfw h4{font-size:14.5px;margin:0 0 4px}
.prfw h4 .sub{font-weight:400;font-size:12px;color:var(--mut);margin-left:8px}
.prfn{font-size:12.5px;color:var(--ink2);margin:2px 0 4px}
.prft td{font-size:12.5px;line-height:1.4;padding:5px 3px;border:1px solid var(--line);border-radius:8px;vertical-align:top}
.prft td b{display:block}.prfr{display:block;font-size:11.5px;color:var(--ink2);font-variant-numeric:tabular-nums}
.prfs{display:block;font-size:11px;color:var(--mut);font-variant-numeric:tabular-nums}
.prfa{display:inline-block;font-size:10.5px;padding:0 5px;border-radius:999px;border:1px solid var(--line2);color:var(--mut);margin-top:2px}
.prm{margin:10px 0 0}.prm>summary{cursor:pointer;font-size:13px;color:var(--acc)}.prmb{font-size:12.5px;color:var(--ink2);line-height:1.75}
@media (max-width:760px){.prkp{grid-template-columns:repeat(2,minmax(0,1fr))}.prcols{grid-template-columns:1fr}}
@media (max-width:640px){.pr{padding:12px 10px}.prl{display:none}.prs{display:inline}.prvn{display:none}
.prg{border-spacing:2px;font-size:12px;table-layout:fixed}.prg th{padding:3px 1px}.prg th.prrn{width:31%;min-width:0;padding-right:2px}
.prc{min-width:0;padding:6px 1px}.prvt{font-size:12px}.prro{display:block;margin:2px 0 0;width:max-content;font-size:10.5px}
.prft td{padding:4px 1px;font-size:11.5px}.prfs,.prfx{display:none}
.prstk thead{display:none}.prstk tr{display:grid;grid-template-columns:1fr 1fr;gap:2px 10px;padding:6px 0;border-bottom:1px solid var(--line)}
.prstk td{border:0;padding:1px 0;text-align:left;white-space:normal}.prstk td.l{grid-column:1/-1}
.prstk td[data-h]::before{content:attr(data-h);display:block;font-size:11px;color:var(--mut)}
.prsel td{font-size:12px}}
"""


JS = r"""
// ── 實測區（practpage.py；docs/lab_practice_page_plan.md）
const PR = SG.pr || {ok: false}, PRC = {};
let PRSEL = null, PRSPAN = 'all';
const prRule = k => (PR.rules || []).find(r => r.k === k);
const prPc = (v, k) => v == null ? '—' : (+v).toFixed(k == null ? 1 : k) + '%';
const prSg = v => v == null ? '—' : (v > 0 ? '+' : '') + (+v).toFixed(1) + '%';
function prLoad(mk){
  if (PRC[mk]) return Promise.resolve(PRC[mk]);
  return fetch('x9pr-' + mk + '.json').then(x => x.json()).then(j => (PRC[mk] = j)); }
function prOpen(k, mk, scroll){
  if (!PR.ok || !prRule(k) || !(PR.g[k] || {})[mk]) return;
  PRSEL = [k, mk];
  document.querySelectorAll('#pr .prc').forEach(b => b.classList.toggle('on', b.dataset.r === k && b.dataset.m === mk));
  const box = document.getElementById('prd');
  if (!box) return;
  box.innerHTML = '<p class="note">' + esc(PR.mkn[mk]) + ' 的資料載入中…</p>';
  if (scroll) box.scrollIntoView({block: 'start'});
  prLoad(mk).then(J => { if (!PRSEL || PRSEL[0] !== k || PRSEL[1] !== mk) return; box.innerHTML = prDetail(J, k, mk); prCharts(J, k, mk); })
    .catch(() => { box.innerHTML = '<p class="note">載入失敗，請重新整理。</p>'; }); }
function prSent(D, R, mk){
  const f = D.p.full, w = prPc(f.w, 0);
  const nm = mk === 'tw' ? PR.mkn[mk] : ' ' + PR.mkn[mk] + ' ';
  return '照這個用法在' + esc(nm) + '平均拿 <b>' + w + '</b> 股票：年化 <b>' + prPc(f.r[0]) + '</b>、最慘跌 <b>' + prPc(f.r[1], 0) + '</b>、最差一年 ' + prPc(f.r[3]) +
    '。每天固定拿 ' + w + '：' + prPc(f.f[0]) + '、' + prPc(f.f[1], 0) + '、' + prPc(f.f[3]) + '；一直持有：' + prPc(f.b[0]) + '、' + prPc(f.b[1], 0) + '、' + prPc(f.b[3]) + '。'; }
function prTile(lb, r, f, b, fmt){
  return '<div class="prt"><div class="lb">' + lb + '</div><div class="vl">' + fmt(r) + '</div><div class="cp"><i>固定</i> ' + fmt(f) + (b === undefined ? '' : '　<i>一直</i> ' + fmt(b)) + '</div></div>'; }
function prDetail(J, k, mk){
  const R = prRule(k), D = J.det[k];
  if (!D) return '<p class="note">這個市場沒有這種用法的結果。</p>';
  const vn = PR.vn[D.v], f = D.p.full, role = {cand_ok: '候選・過門檻・前瞻驗證中', cand_no: '候選・沒過門檻', ctrl: '對照'}[R.r];
  const mks = PR.mks.map(m => '<button type="button" data-m="' + m + '"' + (m === mk ? ' class="on"' : '') + (PR.g[k] && PR.g[k][m] ? '' : ' disabled') + '>' + esc(PR.mkn[m]) + '</button>').join('');
  const sh = x => x == null ? '—' : (+x).toFixed(2);
  let h = '<div class="prdh"><h4>' + esc(PR.mkn[mk]) + '・' + esc(k) + ' ' + esc(R.n) + '</h4><span class="prdv prv' + D.v + '">' + esc(vn) + '</span><span class="prro prro-' + R.r + '">' + esc(role) + '</span></div>' +
    '<div class="prmk" data-r="' + esc(k) + '">' + mks + '</div>' +
    '<p class="prdesc"><b>怎麼做</b>：' + esc(R.d) + '</p><p class="prsum">' + prSent(D, R, mk) + '</p>' +
    '<div class="prkp">' + prTile('年化', f.r[0], f.f[0], f.b[0], prPc) + prTile('最大回撤', f.r[1], f.f[1], f.b[1], v => prPc(v, 0)) +
    prTile('最差一年', f.r[3], f.f[3], f.b[3], prPc) + prTile('報酬 ÷ 波動', f.r[2], f.f[2], f.b[2], sh) +
    '<div class="prt"><div class="lb">平均拿幾成</div><div class="vl">' + prPc(f.w, 0) + '</div><div class="cp"><i>一直持有</i> 100%</div></div>' +
    '<div class="prt"><div class="lb">一年調整</div><div class="vl">' + (f.r[4] == null ? '—' : f.r[4].toFixed(0) + ' 次') + '</div><div class="cp">' + esc(ymd(f.a)) + ' 起</div></div></div>';
  h += prNow(J, k, mk);
  h += '<div class="prsp"><span class="lbx">期間</span><button type="button" data-sp="all"' + (PRSPAN === 'all' ? ' class="on"' : '') + '>全部</button>' +
    '<button type="button" data-sp="10y"' + (PRSPAN === '10y' ? ' class="on"' : '') + '>近 10 年</button></div>' +
    '<div class="prlg"><span class="r">照做</span><span class="f">每天固定拿 ' + prPc(f.w, 0) + '</span><span class="b">一直持有</span><span class="z">指數跌 20% 以上的期間</span></div>' +
    '<div class="prrd" id="prrd"></div><div class="prcv" id="prcv"></div>';
  h += '<div class="prcols"><div class="prsec"><h5>逐年報酬</h5>' + prYears(D) + '</div><div class="prsec"><h5>每一段大跌（指數跌 20% 以上）</h5>' + prBears(D) + '</div></div>';
  h += '<div class="prsec"><h5>成績會不會只靠某一段</h5>' + prSplit(D) + '</div>';
  if (R.g === 'x') h += '<div class="prsec"><h5>每年選了哪些策略（每年 1 月 1 日只用之前的資料判定）</h5>' + prSel(J, k) + '</div>';
  if (D.ci) h += '<p class="note">報酬 ÷ 波動比一直持有多 ' + sh(f.r[2] - f.b[2]) + '（95% 區間 ' + sh(D.ci[0]) + '～' + sh(D.ci[1]) + '；區間含 0＝差距可能只是運氣）。</p>';
  return h; }
function prNow(J, k, mk){
  const R = prRule(k), L = (PR.live || {})[mk], t = L && L.t ? L.t[k] : null;
  if (R.g === 'x') {
    const ks = L && L.sel ? L.sel[k] || [] : [], held = L && L.held ? L.held : {};
    if (t == null) return '';
    const on = ks.filter(s => held[s] > 0).map(s => esc(PR.sn[s] || s)), off = ks.length - on.length;
    return '<div class="prnow"><b>現在照做：拿 ' + prPc(100 * t, 0) + '</b>（' + esc(ymd(L.xd)) + ' 收盤後）。今年選到 ' + ks.length + ' 條' +
      (on.length ? '：' + on.join('、') + ' 持有中' : '，都空手') + (off && on.length ? '，其他 ' + off + ' 條空手' : '') + '。</div>'; }
  if (t == null || !L.cal) return '';
  const RR = {A1: ['short', 'warn'], A2: ['mid', 'warn'], A3: ['long', 'warn'], B1: ['short', 'up'], D1: ['short', 'up']}[k];
  const HZ = {short: '短線', mid: '中線', long: '長線'}, SD = {warn: '警示', up: '偏多'}, GN = {hi: '多', mid: '中間', lo: '少'};
  let why = '';
  if (k === 'A4') why = ['short', 'mid', 'long'].map(z => HZ[z] + (L.cal[z] && L.cal[z].warn.grp === 'hi' ? '多' : '不多')).join('、');
  else if (k === 'D1') why = '今天的重點偏多那一邊' + (t > 0 ? '有東西' : '是空的');
  else if (RR) { const c = (L.cal[RR[0]] || {})[RR[1]] || {};
    why = HZ[RR[0]] + SD[RR[1]] + '票數 ' + (c.n == null ? '—' : c.n) + '，比過去 10 年 ' + (c.pct == null ? '—' : Math.round(100 * c.pct) + '%') + ' 的週多，算「' + (GN[c.grp] || '—') + '」'; }
  const fw = ((PR.fw || {})[mk] || {})[k], cur = fw && fw.now != null ? '前瞻紀錄目前的部位是 ' + prPc(100 * fw.now, 0) + '。' : '';
  const when = L.wend && L.wend !== L.d
    ? '規則只看每週最後一個交易日的讀數（這週是 ' + esc(ymd(L.wend)) + '），在那之前沿用上一次的決定。'
    : esc(ymd(L.d)) + ' 是這週最後一個交易日，照規則在下一個交易日（' + esc(ymd(L.nx)) + '）收盤調整。';
  return '<div class="prnow"><b>照 ' + esc(ymd(L.d)) + ' 的讀數：拿 ' + prPc(100 * t, 0) + '</b>（' + esc(why) + '）。' + when + cur + '</div>'; }
function prYears(D){
  const ys = D.y.slice().reverse(), n = ys.length, cut = 10;
  const row = y => '<tr' + (y.i >= cut ? ' class="prhid" hidden' : '') + '><td class="l">' + y[0] + '</td>' + [1, 2, 3].map(j => '<td' + (y[j] < 0 ? ' class="ng"' : '') + '>' + prSg(y[j]) + '</td>').join('') + '</tr>';
  ys.forEach((y, i) => { y.i = i; });
  return '<table class="prtb"><thead><tr><th class="l">年</th><th>照做</th><th>固定持有</th><th>一直持有</th></tr></thead><tbody>' + ys.map(row).join('') + '</tbody></table>' +
    (n > cut ? '<button type="button" class="prmore" data-more="1">看全部 ' + n + ' 年</button>' : ''); }
function prBears(D){
  if (!D.b.length) return '<p class="note">這段期間指數沒有跌 20% 以上。</p>';
  return '<table class="prtb"><thead><tr><th class="l">高點 → 低點</th><th>指數</th><th>照做</th><th>固定持有</th></tr></thead><tbody>' +
    D.b.slice().reverse().map(b => '<tr><td class="l">' + esc(ymd(b[0])) + ' → ' + esc(ymd(b[1])) + (b[5] ? ' <span class="mu">（還沒結束）</span>' : '') + '</td><td class="ng">' + prSg(b[2]) + '</td><td' + (b[3] < 0 ? ' class="ng"' : '') + '>' + prSg(b[3]) + '</td><td' + (b[4] < 0 ? ' class="ng"' : '') + '>' + prSg(b[4]) + '</td></tr>').join('') + '</tbody></table>'; }
function prSplit(D){
  const nm = {full: '全期間', h1: '前半', h2: '後半', rec: '近 10 年'}, sh = x => x == null ? '—' : (+x).toFixed(2);
  const H = ['平均部位', '年化：照做／固定／一直', '最大回撤：照做／固定／一直', '報酬 ÷ 波動：照做／一直'];
  return '<table class="prtb prstk"><thead><tr><th class="l">期間</th>' + H.map(h => '<th>' + h + '</th>').join('') + '</tr></thead><tbody>' +
    ['full', 'h1', 'h2', 'rec'].map(h => { const p = D.p[h];
      const v = [prPc(p.w, 0), prPc(p.r[0]) + '／' + prPc(p.f[0]) + '／' + prPc(p.b[0]), prPc(p.r[1], 0) + '／' + prPc(p.f[1], 0) + '／' + prPc(p.b[1], 0), sh(p.r[2]) + '／' + sh(p.b[2])];
      return '<tr><td class="l"><b>' + nm[h] + '</b><span class="mu">（' + esc(ymd(p.a)) + '～' + esc(ymd(p.z)) + '）</span></td>' + v.map((x, i) => '<td data-h="' + H[i] + '">' + x + '</td>').join('') + '</tr>'; }).join('') +
    '</tbody></table>'; }
function prSel(J, k){
  const sel = (J.sel || {})[k] || {}, tiers = J.tiers || {}, ys = Object.keys(sel).sort().reverse(), cut = 8;
  const nm = s => esc(PR.sn[s] || s);
  return '<div class="prgw"><table class="prtb prsel"><thead><tr><th class="l">年</th><th class="l">★ 好策略</th>' + (k === 'M2' ? '<th class="l">● 可參考</th>' : '') + '<th>條數</th></tr></thead><tbody>' +
    ys.map((y, i) => { const t = tiers[y] || {}, ks = sel[y] || [], st = ks.filter(s => t[s] === 'good'), rf = ks.filter(s => t[s] === 'ref');
      return '<tr' + (i >= cut ? ' class="prhid" hidden' : '') + '><td class="l">' + y + '</td><td class="l">' + (st.map(nm).join('、') || '<span class="mu">—</span>') + '</td>' + (k === 'M2' ? '<td class="l">' + (rf.map(nm).join('、') || '<span class="mu">—</span>') + '</td>' : '') + '<td>' + ks.length + '</td></tr>'; }).join('') +
    '</tbody></table></div>' + (ys.length > cut ? '<button type="button" class="prmore">看全部 ' + ys.length + ' 年</button>' : ''); }
function prCharts(J, k, mk){
  const box = document.getElementById('prcv'), rd = document.getElementById('prrd'); if (!box) return;
  const R = prRule(k), G = R.g === 'x' ? J.x : J.t, Sr = G && G.r ? G.r[k] : null, D = J.det[k];
  if (!Sr) { box.innerHTML = '<p class="note">沒有圖的資料。</p>'; return; }
  let i0 = 0;
  if (PRSPAN === '10y') { const z = G.d[G.d.length - 1], cut = (+z.slice(0, 4) - 10) + z.slice(4); i0 = Math.max(0, G.d.findIndex(d => d >= cut)); }
  const d = G.d.slice(i0), n = d.length, b0 = G.bh[i0], r0 = Sr.nav[i0], f0 = Sr.fix[i0];
  const nav = Sr.nav.slice(i0).map(v => v / r0), fix = Sr.fix.slice(i0).map(v => v / f0), bh = G.bh.slice(i0).map(v => v / b0), pos = Sr.pos.slice(i0);
  const dd = a => { let pk = -Infinity; return a.map(v => { pk = Math.max(pk, v); return v / pk - 1; }); };
  const dr = dd(nav), dfx = dd(fix), db = dd(bh);
  const W = Math.max(300, Math.round(box.clientWidth || 640)), L = 44, Rm = 10, H1 = 190, H2 = 104, H3 = 66, TH = 18, BT = 18;
  const X = i => L + (n > 1 ? i / (n - 1) : 0) * (W - L - Rm);
  const y1a = TH, y2a = y1a + H1 + TH + 6, y3a = y2a + H2 + TH + 6, Ht = y3a + H3 + BT;
  const lo = Math.log(Math.min(...nav, ...fix, ...bh)), hi = Math.log(Math.max(...nav, ...fix, ...bh)) + 1e-9;
  const Y1 = v => y1a + (1 - (Math.log(v) - lo) / (hi - lo)) * H1;
  const dmin = Math.min(...dr, ...dfx, ...db, -0.05), Y2 = v => y2a + (v / dmin) * H2, Y3 = v => y3a + (1 - v) * H3;
  const path = (a, Y) => a.map((v, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1)).join('');
  // 部位：點太密（每週不到 2px）時，相鄰幾週畫成一段的平均（滑過看到的仍是那一週的部位）
  const pw = (W - L - Rm) / Math.max(1, n - 1), bk = pw < 2 ? Math.ceil(2 / pw) : 1;
  const posd = bk === 1 ? pos : pos.map((_, i) => { const a = Math.floor(i / bk) * bk, z = Math.min(n, a + bk); let t = 0; for (let j = a; j < z; j++) t += pos[j]; return t / (z - a); });
  let g = '';
  (D.b || []).forEach(b => { const a = d.findIndex(x => x >= b[0]); let z = d.findIndex(x => x >= b[1]); if (a < 0 && z < 0) return; if (z < 0) z = n - 1;
    const xa = X(Math.max(0, a)), xz = X(z); [[y1a, H1], [y2a, H2], [y3a, H3]].forEach(([y, h]) => { g += '<rect class="bz" x="' + xa.toFixed(1) + '" y="' + y + '" width="' + Math.max(1.5, xz - xa).toFixed(1) + '" height="' + h + '"/>'; }); });
  const t1 = []; for (let q = Math.ceil(lo / Math.LN2); q <= Math.floor(hi / Math.LN2); q++) t1.push(Math.pow(2, q));
  const tk1 = t1.length > 5 ? t1.filter((_, i) => i % Math.ceil(t1.length / 5) === 0) : t1;
  const gl = (y, lab) => '<line class="gl" x1="' + L + '" x2="' + (W - Rm) + '" y1="' + y + '" y2="' + y + '"/><text x="' + (L - 5) + '" y="' + (+y + 4) + '" text-anchor="end">' + lab + '</text>';
  tk1.forEach(v => { g += gl(Y1(v).toFixed(1), v >= 1 ? v : v.toFixed(2)); });
  const st2 = dmin < -0.6 ? 0.2 : dmin < -0.3 ? 0.1 : 0.05;
  for (let v = 0; v >= dmin - 1e-9; v -= st2) g += gl(Y2(v).toFixed(1), Math.round(100 * v) + '%');
  [0, 0.5, 1].forEach(v => { g += gl(Y3(v).toFixed(1), Math.round(100 * v) + '%'); });
  g += '<text class="prpt" x="' + L + '" y="' + (y1a - 6) + '">1 塊錢變多少（對數座標）</text><text class="prpt" x="' + L + '" y="' + (y2a - 6) + '">從最高點跌了多少</text>' +
    '<text class="prpt" x="' + L + '" y="' + (y3a - 6) + '">拿幾成股票（照做）</text>';
  g += '<path class="lb2" d="' + path(bh, Y1) + '"/><path class="lf" d="' + path(fix, Y1) + '"/><path class="lr" d="' + path(nav, Y1) + '"/>';
  g += '<path class="ar" d="' + path(dr, Y2) + 'L' + X(n - 1).toFixed(1) + ' ' + Y2(0).toFixed(1) + 'L' + X(0).toFixed(1) + ' ' + Y2(0).toFixed(1) + 'Z"/>';
  g += '<path class="lb2" d="' + path(db, Y2) + '"/><path class="lf" d="' + path(dfx, Y2) + '"/><path class="lr" d="' + path(dr, Y2) + '"/>';
  const sp = posd.map((v, i) => (i ? 'H' + X(i).toFixed(1) + 'V' : 'M' + X(0).toFixed(1) + ' ') + Y3(v).toFixed(1)).join('');
  g += '<path class="ar" d="' + sp + 'V' + Y3(0).toFixed(1) + 'H' + X(0).toFixed(1) + 'Z"/><path class="lr prlp" d="' + sp + '"/>';
  const nt = Math.min(7, Math.max(3, Math.floor(W / 100)));
  for (let q = 0; q < nt; q++) { const i = Math.round(q * (n - 1) / (nt - 1)), anc = q === 0 ? 'start' : q === nt - 1 ? 'end' : 'middle';
    g += '<text x="' + X(i).toFixed(1) + '" y="' + (Ht - 4) + '" text-anchor="' + anc + '">' + d[i].slice(0, 4) + '</text>'; }
  g += '<line class="hv" id="prhv" x1="0" x2="0" y1="' + y1a + '" y2="' + (y3a + H3) + '" style="display:none"/><rect class="hit" x="' + L + '" y="0" width="' + (W - L - Rm) + '" height="' + Ht + '"/>';
  box.innerHTML = '<svg viewBox="0 0 ' + W + ' ' + Ht + '" width="' + W + '" height="' + Ht + '" role="img" aria-label="' + esc(PR.mkn[mk] + '・' + R.n) + '：淨值、回撤與部位">' + g + '</svg>' +
    (bk > 1 ? '<p class="cap">期間太長、點太密：部位圖每 ' + bk + ' 週畫成一段的平均；滑過看到的是那一週的部位。</p>' : '');
  const svg = box.querySelector('svg'), hv = svg.querySelector('#prhv');
  const show = i => { const x = X(i).toFixed(1); hv.setAttribute('x1', x); hv.setAttribute('x2', x);
    rd.innerHTML = '<b>' + esc(ymd(d[i])) + '</b>' +
      '<span class="lk" style="border-color:var(--acc)"></span>照做 <b>' + nav[i].toFixed(2) + '</b>（' + prPc(100 * dr[i], 0) + '）' +
      '<span class="lk" style="border-top-style:dashed;border-color:var(--ink2)"></span>固定 <b>' + fix[i].toFixed(2) + '</b>（' + prPc(100 * dfx[i], 0) + '）' +
      '<span class="lk" style="border-color:var(--mut)"></span>一直持有 <b>' + bh[i].toFixed(2) + '</b>（' + prPc(100 * db[i], 0) + '）' +
      '　部位 <b>' + prPc(100 * pos[i], 0) + '</b>'; };
  const mv = e => { const bb = svg.getBoundingClientRect(), cx = (e.touches ? e.touches[0].clientX : e.clientX) - bb.left;
    const i = Math.max(0, Math.min(n - 1, Math.round((cx * W / bb.width - L) / ((W - L - Rm) / Math.max(1, n - 1))))); hv.style.display = ''; show(i); };
  svg.addEventListener('mousemove', mv); svg.addEventListener('touchstart', mv, {passive: true}); svg.addEventListener('touchmove', mv, {passive: true});
  svg.addEventListener('mouseleave', () => { hv.style.display = 'none'; show(n - 1); });
  show(n - 1); }
(function(){
  const root = document.getElementById('pr'); if (!root || !PR.ok) return;
  root.addEventListener('click', e => {
    const c = e.target.closest('.prc'); if (c) { prOpen(c.dataset.r, c.dataset.m, false); history.replaceState(null, '', '#p=' + c.dataset.r + ':' + c.dataset.m); return; }
    const m = e.target.closest('.prmk button'); if (m && PRSEL) { prOpen(PRSEL[0], m.dataset.m, false); history.replaceState(null, '', '#p=' + PRSEL[0] + ':' + m.dataset.m); return; }
    const s = e.target.closest('.prsp button'); if (s && PRSEL) { PRSPAN = s.dataset.sp; root.querySelectorAll('.prsp button').forEach(b => b.classList.toggle('on', b === s)); prLoad(PRSEL[1]).then(J => prCharts(J, PRSEL[0], PRSEL[1])); return; }
    const mo = e.target.closest('.prmore'); if (mo) { const t = mo.previousElementSibling; if (t) t.querySelectorAll('.prhid').forEach(r => { r.hidden = false; }); mo.remove(); } });
  let rz = null;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (PRSEL && PRC[PRSEL[1]]) prCharts(PRC[PRSEL[1]], PRSEL[0], PRSEL[1]); }, 150); });
})();
"""
