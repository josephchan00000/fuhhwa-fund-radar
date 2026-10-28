"""新策略候選的頁面（docs/lab_ia_v5_plan.md 第 24.7 節；資料 arm/lab/candrun.py）。

  board_rows()     配置頁・策略表的「候選」分組（決定之後換到觀察中或淘汰）：名稱、來源、一句規則、成績一行、今天（等你決定…）
  research_body()  研究紀錄頁「策略候選」一段：每一條一張卡（來源、為什麼挑、規則與參數、判定依據、放進計畫試算、試用紀錄、決定）
配置頁照主頁面的用字（docs 第 8 節；不寫判定、研究、門檻……）；研究紀錄頁不受限。
"""
from __future__ import annotations

import html

from . import candrun as CR
from . import candspec as CS

TYPE_OF = {"index": "指數型", "tw_stock": "個股", "us_stock": "個股"}
MKK = {"tw": "tw", "spx": "us", "ixic": "us", "ndx": "us", "sox": "us", "us": "us"}
PLAN_NAME = {"tw": "台股", "spx": "S&P 500", "ndx": "那斯達克 100"}


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _pc(x, d: int = 1, sign: bool = False, frac: bool = True) -> str:
    """frac＝小數（0.123＝12.3%）；否則已經是 %。"""
    if x is None:
        return "—"
    v = x * 100 if frac else x
    s = f"{abs(v):.{d}f}%"
    if sign:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return ("−" if v < 0 else "") + s


def _wan(m) -> str:
    return "—" if m is None else f"{m * 100:,.0f} 萬"


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else (d or "")


def load() -> dict:
    doc = CR.load_spec()
    return {"items": [it for it in doc.get("items") or [] if isinstance(it, dict) and it.get("id")],
            "res": CR.load_res().get("items") or {}, "live": CR.load_live().get("items") or {}, "dec": CR.decisions()}


# ── 成績一行（配置頁；白話） ─────────────────────────────────────────────────────

def perf(it: dict, x: dict | None) -> dict:
    """→ {"perf", "ref", "mdd", "mddr", "sub"}（年化、最慘跌，括號一直抱著；交易型與落底型另寫每筆或每次）。"""
    if not x or x.get("v") in ("need", "err", None):
        return {"perf": "—", "mdd": "—"}
    X = x.get("x") or {}
    eng, kind = it["engine"], it["kind"]
    if eng == "index":
        f, bh, cv = X.get("full") or {}, X.get("bh") or {}, X.get("curve") or {}
        st = cv if kind == "dip" else f
        out = {"perf": f"年化 {_pc(st.get('cagr'))}", "ref": f"一直抱著 {_pc(bh.get('cagr'))}",
               "mdd": _pc(st.get("mdd"), 0), "mddr": _pc(bh.get("mdd"), 0)}
        if kind == "trade" and f.get("n"):
            out["sub"] = f"每筆 {_pc(f.get('avg'), 2, True)}・賺錢 {_pc(f.get('win'), 0)}（任一天 {_pc(f.get('base'), 0)}）"
        elif kind == "dip" and f.get("n"):
            out["sub"] = f"{f['n']} 次・抱完賺錢 {_pc(f.get('win'), 0)}（任一天 {_pc(f.get('base'), 0)}）"
        return out
    if eng == "tw_stock":
        a, tr, fu = X.get("acc") or {}, X.get("tr") or {}, X.get("full") or {}
        out = {"perf": f"年化 {_pc(a.get('cagr'))}", "ref": f"大盤 {_pc(tr.get('cagr'))}",
               "mdd": _pc(a.get("mdd"), 0), "mddr": _pc(tr.get("mdd"), 0)}
        if fu.get("n"):
            out["sub"] = f"{fu['n']} 期・每期 {_pc(fu.get('avg'), 1, True, frac=False)}・賺錢 {_pc(fu.get('win'), 0, frac=False)}"
        return out
    f, sp = X.get("full") or {}, X.get("spx") or {}
    return {"perf": f"年化 {_pc(f.get('cagr'))}", "ref": f"S&P 500 含息 {_pc(sp.get('cagr'))}",
            "mdd": _pc(f.get("mdd"), 0), "mddr": _pc(sp.get("mdd"), 0)}


def plan_line(it: dict, x: dict | None) -> str:
    """放進計畫試算一行：「放進計畫：100 萬變 X 萬（現在 Y 萬）」；沒有計畫的市場或算不出來＝空字串。"""
    ps = (x or {}).get("plan") or {}
    pm = next((m for m in CS.PLAN_OF.get(it.get("mk"), ()) if (ps.get(m) or {}).get("new")), None)
    if not pm:
        return ""
    p = ps[pm]
    nm = "" if len([m for m in CS.PLAN_OF.get(it["mk"], ()) if (ps.get(m) or {}).get("new")]) < 2 else f"{PLAN_NAME[pm]}"
    return (f"放進{nm}計畫：100 萬變 {_wan(p['new']['plan']['m'])}（現在 {_wan(p['cur']['plan']['m'])}）"
            + ("" if p["judge"]["pass"] else "，沒有比較好"))


def verdict(x: dict | None) -> str:
    v = (x or {}).get("v")
    return CS.VERDICT.get(v, "還沒算") if v else "還沒算"


def today(it: dict, x: dict | None, dec: dict | None, live: dict | None) -> str:
    d = dec or {}
    if it.get("need") is not None:
        return str(it["need"])
    if d.get("dec") == "trial":
        st = CR.live_stats(live or {})
        if not st["n"]:
            return f"試用中（{_md(d.get('d'))} 起，還沒有紀錄）"
        if not st["ok"]:
            return f"試用中・記了 {st['n']} 天"
        return f"試用中・{st['n']} 天照做 {_pc(st['ret'], 1, True)}（一直抱著 {_pc(st['hold'], 1, True)}）"
    if d.get("dec") == "adopt":
        return "納入，等放上選股頁"
    v = verdict(x)
    return f"{v}，等你決定" if (x or {}).get("v") in CS.TIERS else v


def board_rows(B: dict | None = None) -> list[dict]:
    """策略表的列（board.build 併進去）：沒決定＝候選；試用、納入＝觀察中；不納入＝淘汰（原因＝使用者說的，沒說就寫成績）。"""
    B = B or load()
    out = []
    for it in B["items"]:
        cid = it["id"]
        x = B["res"].get(cid)
        d = B["dec"].get(cid) or {}
        st = CS.DEC_STATUS.get(d.get("dec"), "cand")
        src = (it.get("src") or [{}])[0]
        row = {"id": f"cand:{cid}", "name": it["name"], "mk": CS.MK_NAMES.get(it["mk"], it["mk"]), "mkk": MKK.get(it["mk"], "us"),
               "ix": it["mk"] if it["engine"] == "index" else None, "type": TYPE_OF.get(it["engine"], "個股"), "st": st,
               "how": it.get("how") or "", "href": f"x9r.html#cand-{cid}", "src": src.get("u"), "go": {},
               "today": today(it, x, d, B["live"].get(cid))}
        row.update(perf(it, x))
        pl = plan_line(it, x)
        if pl:
            row["sub"] = (row.get("sub") + "；" if row.get("sub") else "") + pl
        if st == "out":
            row["why"] = d.get("why") or f"新找的策略，回測{verdict(x)}；{_md(d.get('d'))} 決定不納入"
        out.append(row)
    return out


# ── 研究紀錄頁 ─────────────────────────────────────────────────────────────────

def _kv(rows: list[tuple[str, str]]) -> str:
    return '<dl class="cdkv">' + "".join(f"<dt>{_e(k)}</dt><dd>{v}</dd>" for k, v in rows if v) + "</dl>"


def _ok(b) -> str:
    return "✓" if b else "✗"


def _index_detail(it: dict, X: dict) -> str:
    f, rec, bh, cv = X.get("full") or {}, X.get("rec") or {}, X.get("bh") or {}, X.get("curve") or {}
    kind = it["kind"]
    rows = [("評估期間", _e(f"{X.get('a')}～{X.get('z')}（近 10 年從 {X.get('r0')} 起）"))]
    if kind == "trade":
        rows += [("全部", _e(f"{f.get('n', 0)} 筆・賺錢 {_pc(f.get('win'), 1)}（任一天抱一樣久 {_pc(f.get('base'), 1)}）・"
                             f"每筆平均 {_pc(f.get('avg'), 2, True)}・中位 {_pc(f.get('med'), 2, True)}・照做年化 {_pc(f.get('cagr'))}、"
                             f"最慘跌 {_pc(f.get('mdd'), 0)}")),
                 ("近 10 年", _e(f"{rec.get('n', 0)} 筆・賺錢 {_pc(rec.get('win'), 1)}（任一天 {_pc(rec.get('base'), 1)}）・"
                                 f"每筆 {_pc(rec.get('avg'), 2, True)}"))]
    elif kind == "dip":
        rows += [("全部", _e(f"{f.get('n', 0)} 次・抱 {it.get('H')} 天賺錢 {_pc(f.get('win'), 1)}（任一天 {_pc(f.get('base'), 1)}）・"
                             f"中位 {_pc(f.get('med'), 1, True)}（任一天 {_pc(f.get('bmed'), 1, True)}）・排除極端的平均 "
                             f"{_pc(f.get('trim'), 1, True)}・全部資金照做年化 {_pc(cv.get('cagr'))}、最慘跌 {_pc(cv.get('mdd'), 0)}")),
                 ("近 10 年", _e(f"{rec.get('n', 0)} 次・賺錢 {_pc(rec.get('win'), 1)}"))]
    else:
        rows += [("全部", _e(f"年化 {_pc(f.get('cagr'))}、最慘跌 {_pc(f.get('mdd'), 0)}、每年換邊 {f.get('sw') or 0:.1f} 次・"
                             f"一直抱著 {_pc(bh.get('cagr'))}、{_pc(bh.get('mdd'), 0)}")),
                 ("近 10 年", _e(f"年化 {_pc(rec.get('cagr'))}、最慘跌 {_pc(rec.get('mdd'), 0)}"))]
    g = X.get("grid") or []
    if g:
        rows.append(("參數鄰近", _e(f"{sum(1 for c in g if c.get('ok'))}／{len(g)} 組過關（要 ≥ 2/3）：")
                     + "、".join(_e("＋".join(f"{k}={v}" for k, v in (c.get("p") or {}).items()) + _ok(c.get("ok"))) for c in g)))
    rows.append(("判定依據", _e(f"總經策略同一套（xstratspec VER 6）：全部 {_ok(f.get('ok'))}・近 10 年 "
                               f"{'—' if X.get('rec_ok') is None else _ok(X.get('rec_ok'))}・參數鄰近 {_pc(X.get('grid_ok'), 0)}")))
    return _kv(rows)


def _tw_detail(it: dict, X: dict) -> str:
    fu, la, a, tr, ew = (X.get(k) or {} for k in ("full", "later", "acc", "tr", "ew"))
    pay = lambda p: f"{p.get('n', 0)} 期・賺錢 {_pc(p.get('win'), 0, frac=False)}・每月 {_pc(p.get('m'), 2, True, frac=False)}・賺賠比 " \
                    f"{'—' if p.get('ratio') is None else format(p['ratio'], '.2f')}・{'過' if p.get('ok') else '沒過'}"
    g = X.get("grid") or []
    rows = [("範圍", _e(f"{'大型股' if X.get('b') == 'L' else '中型股'}・{a.get('a')}～{a.get('b')}")),
            ("報酬型態（全部）", _e(pay(fu))), ("報酬型態（後一半）", _e(pay(la))),
            ("資金帳戶", _e(f"年化 {_pc(a.get('cagr'))}、最慘跌 {_pc(a.get('mdd'), 0)}・加權報酬指數 {_pc(tr.get('cagr'))}、"
                            f"{_pc(tr.get('mdd'), 0)}・同一批股票等權 {_pc(ew.get('cagr'))}・平均每期贏同一批 {_pc(X.get('xe'), 2, True, frac=False)}")),
            ("參數鄰近", _e(f"{sum(1 for c in g if c.get('ok'))}／{len(g)} 組報酬型態過（要 ≥ 2/3）：")
             + "、".join(_e(f"{c.get('a')}・前 {c['pick'][1]} 檔{_ok(c.get('ok'))}") for c in g))]
    return _kv(rows)


def _us_detail(it: dict, X: dict) -> str:
    f, la, sp, sl = (X.get(k) or {} for k in ("full", "later", "spx", "spx_later"))
    g = X.get("grid") or []
    rows = [("全部", _e(f"{f.get('a')}～{f.get('b')}：年化 {_pc(f.get('cagr'))}、最慘跌 {_pc(f.get('mdd'), 0)}・S&P 500 含息 "
                        f"{_pc(sp.get('cagr'))}、{_pc(sp.get('mdd'), 0)}・平均持股 {_pc(X.get('exposure'), 0)}")),
            ("後一半", _e(f"{la.get('a')} 起：年化 {_pc(la.get('cagr'))}・S&P 500 含息 {_pc(sl.get('cagr'))}")),
            ("參數鄰近", _e(f"{sum(1 for c in g if c.get('ok'))}／{len(g)} 組贏 S&P 500 含息（要 ≥ 2/3）：")
             + "、".join(_e("＋".join(f"{k}={v}" for k, v in (c.get("p") or {}).items()) + _ok(c.get("ok"))) for c in g))]
    return _kv(rows)


def _plan_detail(it: dict, x: dict) -> str:
    out = []
    for pm, p in ((x.get("plan") or {}).items()):
        if p.get("err"):
            out.append(f'<p class="cdn">{_e(PLAN_NAME.get(pm, pm))}：沒算出來（{_e(p["err"])}）</p>')
            continue
        j, c, n = p["judge"], p["cur"], p["new"]
        hv = "、".join(f"{h['a'][:4]}～{h['b'][:4]} {_wan(h['plan']['m'])}（現在 {_wan(hc['plan']['m'])}）" for h, hc in zip(n["halves"], c["halves"]))
        how = (f"★ 那一半平分給 {p.get('n')}＋1 條" if pm == "tw" else ("機動一半美股強勢品質股、一半這條" if p.get("qm") else "機動一半指數、一半這條"))
        out.append(f'<p class="cdn"><b>{_e(PLAN_NAME.get(pm, pm))}</b>（{_e(how)}；{_e(c["a"])}～{_e(c["b"])}）：100 萬變 {_wan(n["plan"]["m"])}'
                   f'（現在 {_wan(c["plan"]["m"])}）{_ok(j["money"])}・最慘跌 {_pc(n["plan"]["mdd"], 0)}（現在 {_pc(c["plan"]["mdd"], 0)}，'
                   f'最多深 10 點）{_ok(j["mdd"])}・前半後半 {_e(hv)} {_ok(j["halves"])}'
                   f'・<b>{"有幫助" if j["pass"] else "沒有比較好"}</b></p>')
    return "".join(out)


def _now(it: dict, x: dict) -> str:
    X = x.get("x") or {}
    n = X.get("now") or {}
    if it["engine"] == "index":
        if not n:
            return ""
        st = {"buy": "下一個交易日收盤買", "hold": "持有中", "sell": "下一個交易日收盤賣", "wait": "沒有訊號", "in": "拿著",
              "out": "空手", "turn_in": "下一個交易日收盤買回", "turn_out": "下一個交易日收盤賣"}.get(n.get("st"), n.get("st"))
        return _e(f"{n.get('d')} 收盤：{st}" + (f"（{n.get('ed')} 買進，{_pc(n.get('ret'), 1, True)}）" if n.get("ed") else ""))
    if not n:
        return ""
    return _e(f"{n.get('d')} 的名單：" + "、".join(n.get("picks") or []) + (f"；手上 {'、'.join(n['held'])}" if n.get("held") else ""))


def card(it: dict, x: dict | None, dec: dict | None, live: dict | None) -> str:
    cid = it["id"]
    x = x or {}
    d = dec or {}
    src = "".join(f'<li><a href="{_e(s["u"])}" target="_blank" rel="noopener">{_e(s["t"])}</a></li>' for s in it.get("src") or [])
    head = (f'<div class="cdh"><span class="cdid">{_e(cid)}</span><b>{_e(it["name"])}</b>'
            f'<span class="cdv cdv-{_e(x.get("v") or "none")}">{_e(verdict(x) if it.get("need") is None else "需要資料")}</span>'
            f'<span class="cdm">{_e(CS.MK_NAMES.get(it["mk"], it["mk"]))}・{_e(CS.ENGINE_NAMES.get(it["engine"], it["engine"]))}'
            f'・{_e(it.get("found"))} 寫定</span></div>')
    rows = [("一句規則", _e(it.get("how"))), ("為什麼挑", _e(it.get("why"))),
            ("參數", _e("、".join(f"{k}={v}" for k, v in (it.get("p") or {}).items()))
             + ("" if not it.get("H") else _e(f"；抱 {it['H']} 個交易日"))
             + ("" if not it.get("pick") else _e("；" + "、".join(f"{k}={v}" for k, v in it["pick"].items())))
             + ("" if not it.get("ex") else _e("；" + "、".join(f"{k}={v}" for k, v in it["ex"].items())))),
            ("參數鄰近", _e("；".join(f"{k}: {v}" for k, v in (it.get("grid") or {}).items()))),
            ("程式", f'<code>{_e(CS.PROG_DIR)}/{_e(cid)}.py</code>（sha256 {_e(str(it.get("sha") or "")[:12])}…）' if it.get("sha") else ""),
            ("前一版", _e(it.get("prev")))]
    if it.get("need") is not None:
        rows.append(("需要資料", _e(it["need"])))
    body = _kv(rows)
    if x.get("v") == "err":
        body += f'<p class="cdn">沒算出來：{_e(x.get("err"))}</p>'
    elif x.get("v") == "peek":
        body += '<p class="cdn"><b>用到未來的資料</b>（不判定）：' + "；".join(_e(m) for m in x.get("peek") or []) + "</p>"
    if x.get("v") in CS.TIERS or x.get("v") == "peek":
        X = x.get("x") or {}
        body += '<h4>判定依據</h4>' + {"index": _index_detail, "tw_stock": _tw_detail, "us_stock": _us_detail}[it["engine"]](it, X)
        pl = _plan_detail(it, x)
        if pl:
            body += "<h4>放進計畫試算</h4>" + pl
        nw = _now(it, x)
        if nw:
            body += f'<h4>算的時候的狀態</h4><p class="cdn">{nw}（{_e(x.get("made"))} 算的）</p>'
    st = CR.live_stats(live or {})
    if d.get("dec") == "trial":
        body += ('<h4>試用紀錄</h4><p class="cdn">' + _e(f"{_md(d.get('d'))} 決定試用；" + (
            f"{st['a']}～{st['z']} 共 {st['n']} 個交易日：照做 {_pc(st['ret'], 1, True)}、一直抱著 {_pc(st['hold'], 1, True)}"
            + ("" if st["ok"] else f"（滿 {CS.TRIAL_CHECK} 個交易日再看）") if st["n"] else "還沒有紀錄（每週日記一次）")) + "</p>")
    if d.get("dec"):
        body += f'<h4>決定</h4><p class="cdn">{_e(_md(d.get("d")))}：{_e(CS.DECISIONS[d["dec"]])}' + (f"（{_e(d['why'])}）" if d.get("why") else "") + "</p>"
    return f'<details class="cdcard" id="cand-{_e(cid)}"><summary>{head}</summary><div class="cdb"><ul class="cdsrc">{src}</ul>{body}</div></details>'


def research_body(B: dict | None = None) -> str:
    B = B or load()
    items = B["items"]
    rows = []
    for it in items:
        cid = it["id"]
        x = B["res"].get(cid)
        d = B["dec"].get(cid) or {}
        state = CS.DECISIONS.get(d.get("dec"), "等你決定")
        pl = plan_line(it, x)
        rows.append(f'<tr><td><a href="#cand-{_e(cid)}">{_e(cid)}</a></td><td>{_e(it["name"])}</td>'
                    f'<td>{_e(CS.MK_NAMES.get(it["mk"], it["mk"]))}</td><td>{_e(verdict(x) if it.get("need") is None else "需要資料")}</td>'
                    f'<td>{_e(pl.replace("放進計畫：", "").replace("放進", "") or "—")}</td><td>{_e(state)}</td></tr>')
    open_n = len(CR.open_ids({"items": items}, B["dec"]))
    intro = (f'<p class="rnote">每週日晚上從論文、量化部落格、投信券商報告找新策略（每週最多 {CS.MAX_NEW} 條），先寫規則與程式'
             f'（寫定之後不能改）再回測；判定和頁面上同一類的策略一樣（指數型＝總經策略、台股個股＝報酬型態、美股個股＝贏 S&amp;P 500 含息），'
             f'另外試算放進交易計畫會不會比較好。用到未來資料的程式會被兩道檢查抓出來、不判定。你在對話回「試用／納入／不納入」，'
             f'決定記在 config/strategy_board.json。還沒決定的現在 {open_n} 條（到 {CS.MAX_OPEN} 條週報先停）。</p>')
    if not items:
        return intro + '<p class="cdn">目前沒有候選；第一批在每週日新找之後出現。</p>'
    tbl = ('<div class="cdtw"><table class="cdt"><thead><tr><th>編號</th><th>名稱</th><th>市場</th><th>過去成績</th><th>放進計畫</th><th>狀態</th></tr></thead>'
           f'<tbody>{"".join(rows)}</tbody></table></div>')
    cards = "".join(card(it, B["res"].get(it["id"]), B["dec"].get(it["id"]), B["live"].get(it["id"])) for it in items)
    return intro + tbl + cards


CSS = """
.cdtw{overflow-x:auto}.cdt{border-collapse:collapse;font-size:13px;width:100%;margin:6px 0 10px}
.cdt th,.cdt td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
.cdt th{color:var(--mut);font-weight:500;font-size:12px}
.cdcard{border:1px solid var(--line);border-radius:10px;margin:8px 0;background:var(--card,transparent)}
.cdcard>summary{cursor:pointer;list-style:none;padding:10px 12px}.cdcard>summary::-webkit-details-marker{display:none}
.cdh{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;font-size:14px}
.cdid{font-family:ui-monospace,monospace;color:var(--mut);font-size:12px}
.cdv{font-size:12px;padding:1px 8px;border-radius:999px;background:var(--line);color:var(--ink2)}
.cdv-good{background:rgba(220,60,50,.14);color:var(--up,#c0392b)}.cdv-ref{background:rgba(200,140,40,.16)}
.cdv-peek,.cdv-err{background:rgba(120,120,120,.18)}
.cdm{color:var(--mut);font-size:12px}
.cdb{padding:0 12px 12px;font-size:13.5px;line-height:1.7}
.cdb h4{font-size:13.5px;margin:12px 0 4px}
.cdsrc{margin:0 0 6px;padding-left:18px;font-size:13px}
.cdkv{display:grid;grid-template-columns:minmax(7em,9em) minmax(0,1fr);gap:2px 12px;margin:0}
.cdkv dt{color:var(--mut)}.cdkv dd{margin:0}
.cdn{margin:4px 0;font-size:13px}
@media (max-width:640px){.cdkv{grid-template-columns:1fr}.cdkv dt{margin-top:6px}}
"""
