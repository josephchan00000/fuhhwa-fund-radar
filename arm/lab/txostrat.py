"""選擇權頁 x9op.html 的「策略」分頁：測過的四條選擇權策略（docs/lab_txo_plan.md 第 18、19、20 節）。

使用者 2026-11-12：「我加給你新的策略怎麼沒看到？」——11/11 上傳的「台指週選結算日交易逆向拆解」，
A（Gamma 動能）＝O1 結算日順勢、B（結算均價偏離）＝O4，成績都算好了（第 19.8 節），卻只寫在規劃文件、沒有放上頁面。
這一頁把四條都照實列出來：過關的、沒過的、筆數還不夠的；沒過的也照列，並寫為什麼沒過。

資料：data/lab/txo_research.json（O2、O3；scripts/run_txobt.py）、data/lab/txo_settle.json（O1、O4；scripts/run_txo1.py）。
只讀檔、純呈現；讀不到的那一條顯示「還沒有成績」。CSS class 一律 ts 開頭。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "data" / "lab" / "txo_research.json"
SET = ROOT / "data" / "lab" / "txo_settle.json"

CSS = (".ts-sum{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 14px}"
       ".ts-sum span{padding:4px 11px;border-radius:99px;font-size:13px;font-weight:600;background:var(--card2);color:var(--ink2)}"
       ".ts-sum b{font-variant-numeric:tabular-nums}"
       ".ts-grid{display:grid;grid-template-columns:1fr;gap:12px}"
       ".ts-c{border:1px solid var(--line);border-radius:14px;padding:14px 15px;background:var(--card)}"
       ".ts-c h3{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin:0 0 4px;font-size:16.5px}"
       ".ts-v{padding:2px 9px;border-radius:7px;font-size:12.5px;font-weight:700}"
       ".ts-v.ok{background:rgba(22,163,74,.14);color:#15803d}.ts-v.no{background:rgba(220,38,38,.12);color:#b91c1c}"
       ".ts-v.wait{background:rgba(217,119,6,.14);color:#b45309}"
       ".ts-src{font-size:12px;color:var(--mut);font-weight:500}"
       ".ts-how{margin:2px 0 10px;font-size:13.5px;color:var(--ink2);line-height:1.7}"
       ".ts-kv{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:0 0 10px}"
       ".ts-kv div{padding:7px 9px;border-radius:10px;background:var(--card2)}"
       ".ts-kv b{display:block;font-size:17px;font-variant-numeric:tabular-nums}.ts-kv span{font-size:12px;color:var(--mut)}"
       ".ts-why{margin:0;padding-left:18px;font-size:13.5px;line-height:1.75;color:var(--ink2)}.ts-why li{margin:0 0 3px}"
       ".ts-next{margin:8px 0 0;font-size:13.5px;line-height:1.7}"
       ".ts-case{border-style:dashed}"
       ".ts-fine{margin:12px 0 0;font-size:12.5px;color:var(--mut);line-height:1.7}"
       "@media (min-width:760px){.ts-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ts-kv{grid-template-columns:repeat(4,minmax(0,1fr))}}"
       "@media (prefers-color-scheme:dark){.ts-v.ok{color:#4ade80}.ts-v.no{color:#f87171}.ts-v.wait{color:#fbbf24}}")


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _yuan(x) -> str:
    if x is None:
        return "—"
    return ("−" if x < 0 else "+" if x > 0 else "") + f"{abs(x):,.0f} 元"


def _pct(x, d: int = 0) -> str:
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _wan(x) -> str:
    return "—" if x is None else f"{x / 10000:,.0f} 萬"


def _md(d: str | None) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 else "—"


def _kv(m: dict, label_n: str = "筆數") -> str:
    items = [(f"{m.get('n', 0):,}", label_n), (_yuan(m.get("mean")), "平均每筆（扣成本）"),
             (_pct(m.get("win")), "賺錢的比例"), (_wan(m.get("final")), f"100 萬變成（最大回落 {_pct(m.get('maxdd'))}）")]
    return '<div class="ts-kv">' + "".join(f"<div><b>{html.escape(a)}</b><span>{html.escape(b)}</span></div>" for a, b in items) + "</div>"


def _card(title: str, verdict: tuple[str, str], src: str, how: str, m: dict | None, why: list[str], nxt: str, label_n: str = "筆數") -> str:
    cls, word = verdict
    return (f'<article class="ts-c"><h3>{html.escape(title)}<span class="ts-v {cls}">{html.escape(word)}</span>'
            f'<span class="ts-src">{html.escape(src)}</span></h3><p class="ts-how">{how}</p>'
            + (_kv(m, label_n) if m else "")
            + ('<ul class="ts-why">' + "".join(f"<li>{w}</li>" for w in why) + "</ul>" if why else "")
            + (f'<p class="ts-next">{nxt}</p>' if nxt else "") + "</article>")


def _verdict(j: dict | None, n: int | None) -> tuple[str, str]:
    v = (j or {}).get("verdict") or ""
    if v == "過關":
        return ("ok", "過關")
    if v == "沒過":
        return ("no", "沒過")
    if v:
        return ("wait", "筆數不夠、還在記")
    return ("wait", "還沒有成績")


def cards(res: dict | None = None, st: dict | None = None) -> list[str]:
    res = _read(RES) if res is None else res
    st = _read(SET) if st is None else st
    out = []
    o3 = res.get("O3") or {}
    m3, c3 = o3.get("main"), o3.get("compare") or {}
    out.append(_card(
        "O3 節慶前買買權", _verdict(o3.get("judge"), (m3 or {}).get("n")), "已驗證的少見策略，改用選擇權做",
        "聖誕行情（12 月最後幾個交易日到隔年 1 月初）、農曆年封關前 5 天：同樣的日子不買指數，改買價平附近的買權，每筆最多押 5%。",
        m3,
        [f"一年只有 2 次。扣掉最賺的 3 筆，平均每筆仍 {_yuan((m3 or {}).get('mean_ex_top3'))}；"
         f"{_pct((m3 or {}).get('years_ok'))} 的年份不虧。",
         f"直接買指數同一段，平均 {_pct(((c3.get('index') or {}).get('mean_ret')), 1)}；改用選擇權放大了報酬，也放大了單筆風險（最差一筆 {_pct((m3 or {}).get('worst_ret'))}）。",
         "這些進出場日子之前已經用 1991 年起的指數驗過；這裡驗的是「同樣的日子改買買權，扣成本後划不划算」。"] if m3 else [],
        "下一次：12 月下旬的聖誕行情。照規格先記紙上紀錄，成績在回測範圍內才放進「今天要做的事」。"))
    o1 = st.get("o1") or {}
    m1, c1 = o1.get("oos"), o1.get("compare") or {}
    out.append(_card(
        "O1 結算日順勢", _verdict(o1.get("judge"), (m1 or {}).get("n")), "＝你 11/11 報告的 A（Gamma 動能）",
        "結算日只買當天到期的那一批：指數跑出平常的波動範圍，就順勢買價平附近；回到範圍裡就停損，13:00 前全部出場。",
        m1,
        [f"便宜的選擇權被成本吃掉：進場價中位數約 22 點，一進一出成本約占 18%。",
         "停損太快：指數剛跑出範圍就在邊緣來回，387 筆裡 166 筆 1 分鐘內就停損。",
         "結算日的時間價值掉得很快：就算指數不動，價外的也會掉六成以上。",
         f"你報告裡的兩種買法也試了：同時買兩檔 {_yuan((c1.get('two') or {}).get('mean'))}／筆、抱到結算 {_yuan((c1.get('hold') or {}).get('mean'))}／筆，都還是虧。",
         f"反過來賣同一個選擇權（只列、我們不做賣方）平均 {_yuan((c1.get('seller') or {}).get('mean'))}／筆——結算日的錢在賣方。"] if m1 else [],
        "可以試的下一步（要另寫新版本規格）：停損改成每 1～5 分鐘才檢查、只買 10 點以上的；或改研究「買方價差」（買一口、賣一口更價外的）。"))
    o4 = st.get("o4") or {}
    m4 = o4.get("metrics")
    t4 = (o4.get("trades") or [{}])[0] if o4.get("trades") else {}
    nd = len(o4.get("days") or [])
    out.append(_card(
        "O4 結算均價", _verdict(o4.get("judge"), (m4 or {}).get("n")), "＝你 11/11 報告的 B（結算均價偏離）",
        "結算價＝到期日 13:00～13:30 指數的平均。13:05 起每 5 分鐘算一次「結算時最少值多少」，成交價比最少值低 2 點以上才買、抱到結算。",
        m4,
        [f"只能用盤中真實成交價驗，我們只有 9/17 起的分 K：{nd} 個結算日、符合的只有 {(m4 or {}).get('n', 0)} 筆"
         + (f"（{_md(t4['d'])} 買 {int(t4['kx']):,} {'買權' if t4.get('cp') == 'C' else '賣權'} {t4.get('p0', 0):g} 點，"
            f"結算 {_yuan(t4.get('pnl'))}／口）" if t4.get("d") and isinstance(t4.get("kx"), (int, float)) else "") + "。",
         "13:00 以後的成交價已經很接近結算價，便宜貨很少；規格要 40 筆、15 個結算日以上才判定。"] if m4 is not None else [],
        f"資料到 {_md(st.get('asof'))}；結算日每週 2 個，筆數到了才判定。", label_n="符合的筆數"))
    o2 = res.get("O2") or {}
    m2 = o2.get("main")
    out.append(_card(
        "O2 大事件前買跨式", _verdict(o2.get("judge"), (m2 or {}).get("n")), "美國 CPI、聯準會會議前",
        "大事件前一天收盤，同時買價平的買權和賣權（不管漲跌、只賭大波動），隔天收盤賣。",
        m2,
        ["隔夜的事件波動已經被價格算進去：買貴了。",
         f"連反過來賣同一組也虧（{_yuan(((o2.get('compare') or {}).get('short') or {}).get('mean'))}／筆）——兩邊都被成本吃掉。"] if m2 else [],
        "目前所有對照都是負的，先不做。"))
    out.append('<article class="ts-c ts-case"><h3>你 11/11 那個案例<span class="ts-src">只是事實，不是成績</span></h3>'
               '<p class="ts-how">那天賺錢的 10 口，是 13:00 以後 5 分鐘指數急漲、權利金幾分鐘內翻 2.5～3.5 倍。'
               'O1 照規則 13:00 前就出場、那天兩次都 5 秒內停損；O4 那天 120 個候選一筆都不便宜。兩條都吃不到那一段。</p>'
               '<p class="ts-next">要研究「12:55～13:00 買、13:00 後幾分鐘內出」得另寫新規則；哪幾天會急漲事前不知道，'
               '9/17 起的真實分 K 只有十幾個結算日，要判定得等很久。要不要做由你決定。</p></article>')
    return out


def block(res: dict | None = None, st: dict | None = None) -> str:
    res = _read(RES) if res is None else res
    st = _read(SET) if st is None else st
    cs = cards(res, st)
    vs = [(res.get("O3") or {}).get("judge"), (st.get("o1") or {}).get("judge"),
          (st.get("o4") or {}).get("judge"), (res.get("O2") or {}).get("judge")]
    words = [_verdict(j, None)[1] for j in vs]
    n_ok, n_no = words.count("過關"), words.count("沒過")
    n_wait = len(words) - n_ok - n_no
    return ('<h2>測過的選擇權策略</h2><p class="oplead">只做買方。每條都是先寫好規則才算成績；沒過的也照列，寫清楚為什麼。</p>'
            f'<div class="ts-sum"><span>過關 <b>{n_ok}</b></span><span>沒過 <b>{n_no}</b></span><span>筆數不夠、還在記 <b>{n_wait}</b></span></div>'
            '<div class="ts-grid">' + "".join(cs) + "</div>"
            '<p class="ts-fine">成績都扣兩倍成本（手續費＋稅＋一檔滑價）。規劃與完整數字：docs/lab_txo_plan.md 第 18、19 節。這裡只是研究紀錄，不是買賣建議。</p>')
