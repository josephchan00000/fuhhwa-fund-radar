"""台股股市位階（規格 arm/lab/mposspec.py VER 1；docs/lab_earnings_plan.md 第 8、9 節）：只描述現在在哪裡。

  compute(B)        → 每天的四組分數、原值、位階（B＝arm/lab/heatcalc.build() 的結果）
  peaks(d, v)       → 近 CHART_YEARS 年的高點、低點
  record(X, log)    → 每天第一次算出來的數字記下來（只增不改；data/lab/heat/mpos_log.json）
  block(B)          → 市場頁（x9m.html）最上面那一塊 HTML（伺服器端畫好、含 SVG；CSS class 一律 mpz- 開頭）
heatpage.build 建正式頁（寫到預設的 x9m.html）時才記 log；測試建到別的地方不寫。
"""
from __future__ import annotations

import bisect
import html
import json
from pathlib import Path

from . import mposspec as S

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data" / "lab" / "heat" / "mpos_log.json"


def log_path(mk: str = "tw") -> Path:
    """公布的數字：台股 mpos_log.json、美股每個指數 mpos_log_{指數}.json（VER 3）。"""
    return LOG if mk == "tw" else LOG.with_name(f"mpos_log_{mk}.json")


def groups(inc: dict, defs=None) -> list[tuple[str, list[str]]]:
    """規格第 1 點：清單和現在有算分的項目取交集（defs＝S.GROUPS 台股、S.GROUPS_US 美股）。"""
    on = {k for ks in (inc or {}).values() for k in ks}
    return [(name, [k for k in ks if k in on]) for name, ks in (defs or S.GROUPS)]


def compute(B: dict, defs=None) -> dict:
    cal, heat = B["cal"], B["heat"]
    T = len(cal)
    G = groups(B.get("inc") or {}, defs)
    gs = {}
    for name, ks in G:
        need = min(S.MIN_ITEMS, len(ks)) if ks else 1          # VER 2（VER 1＝一半，無條件進位）
        col = []
        for i in range(T):
            vs = [heat[k][i] for k in ks if k in heat and heat[k][i] is not None]
            col.append(sum(vs) / len(vs) if ks and len(vs) >= need else None)
        gs[name] = col
    raw = []
    for i in range(T):
        vs = [gs[n][i] for n, ks in G if ks]               # VER 3：沒有算分項目的組不放進平均（台股四組都有）
        raw.append(sum(vs) / len(vs) if all(v is not None for v in vs) else None)
    v, win = [], []                                       # win＝過去 WIN 天（含當天）有值的原值，排好序
    q = []                                                # 照日期的佇列，滑出視窗時從 win 拿掉
    for i in range(T):
        if raw[i] is not None:
            bisect.insort(win, raw[i])
            q.append((i, raw[i]))
        while q and q[0][0] <= i - S.WIN:
            win.pop(bisect.bisect_left(win, q.pop(0)[1]))
        if raw[i] is None or len(win) < S.MIN_DAYS:
            v.append(None)
            continue
        v.append(round(10 * bisect.bisect_left(win, raw[i]) / len(win), 1))
    return {"cal": cal, "g": gs, "raw": raw, "v": v, "items": {n: ks for n, ks in G}}


def label(x: float) -> str:
    return ("極端低位" if x <= S.X_LOW else "低位" if x <= S.LOW else "極端高位" if x >= S.X_HIGH
            else "高位" if x >= S.HIGH else "中間")


def peaks(d: list[str], v: list) -> list[tuple[str, float, str]]:
    """規格第 6 點：前後 PEAK_GAP 個交易日內最高（≥ HIGH）／最低（≤ LOW）；同一種點相隔 < PEAK_GAP 只留比較極端的。"""
    G = S.PEAK_GAP
    out: list[list] = []
    for i, x in enumerate(v):
        if x is None:
            continue
        win = [y for y in v[max(0, i - G):i + G + 1] if y is not None]
        kind = "hi" if x >= S.HIGH and x == max(win) else "lo" if x <= S.LOW and x == min(win) else None
        if not kind:
            continue
        if out and out[-1][2] == kind and i - out[-1][3] < G:
            if (kind == "hi" and x > out[-1][1]) or (kind == "lo" and x < out[-1][1]):
                out[-1] = [d[i], x, kind, i]
            continue
        out.append([d[i], x, kind, i])
    return [(a, b, c) for a, b, c, _ in out]


def read_log(path: Path | None = None) -> dict:
    try:
        return json.loads((path or LOG).read_text(encoding="utf-8")).get("days") or {}
    except (OSError, ValueError, AttributeError):
        return {}


def record(X: dict, log: dict, path: Path | None = None) -> bool:
    """每天第一次算出來的數字記下來，之後不改（規格第 7 點）。"""
    i = len(X["v"]) - 1
    d, x = X["cal"][i], X["v"][i]
    if x is None or d in log:
        return False
    path = path or LOG
    log[d] = {"v": x, "raw": round(X["raw"][i], 2), "g": [None if X["g"][n][i] is None else round(X["g"][n][i], 1) for n in X["g"]]}
    rows = [json.dumps(k) + ":" + json.dumps(log[k], ensure_ascii=False, separators=(",", ":")) for k in sorted(log)]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text('{"ver":' + str(S.VER) + ',"days":{\n' + ",\n".join(rows) + "\n}}\n", encoding="utf-8")
    tmp.replace(path)
    return True


# ── 怎麼算（研究紀錄頁）與每天的數字（CSV） ─────────────────────────────────

DETAIL = ROOT / "data" / "lab" / "heat" / "mpos_detail.json"
DASH = ROOT / "dashboard"


def csv_name(mk: str) -> str:
    return f"x9mpos-{mk}.csv"


def _names() -> dict:
    from . import heatspec as HS                         # 美股在 heatspec.use(美股規格) 底下叫，名稱是美股的
    return {k: nm for k, _, nm, *_ in HS.IND}


def detail(B: dict, X: dict, R: dict | None, mk: str, name: str) -> dict:
    """最新一天的實際算式（mposfwdspec 第 7 點）：每一項的分數、每組平均、四組平均、過去 10 年有幾天比它低。"""
    cal, v, raw = X["cal"], X["v"], X["raw"]
    idx = [k for k, x in enumerate(v) if x is not None]
    if not idx:
        return {}
    i = idx[-1]
    nm = _names()
    gs = []
    for g, ks in X["items"].items():
        its = [[k, nm.get(k, k), None if B["heat"].get(k) is None or B["heat"][k][i] is None else round(B["heat"][k][i], 1)] for k in ks]
        gv = X["g"][g][i]
        gs.append({"name": g, "items": its, "avg": None if gv is None else round(gv, 2), "empty": not ks})
    lo = max(0, i - S.WIN + 1)
    win = [raw[k] for k in range(lo, i + 1) if raw[k] is not None]
    below = sum(1 for r in win if r < raw[i])
    return {"mk": mk, "name": name, "d": cal[i], "x": v[i], "lv": label(v[i]), "raw": round(raw[i], 2), "groups": gs,
            "win": len(win), "below": below, "from": cal[lo], "first": cal[idx[0]], "csv": csv_name(mk),
            "px": (B.get("px") or [None] * len(cal))[i], "fwd": R or {}}


def csv_text(B: dict, X: dict) -> str:
    """每天的數字：日期、指數收盤、每一項的分數、四組、四組平均、位階（從有四組平均的第一天起）。"""
    cal, raw, v = X["cal"], X["raw"], X["v"]
    nm = _names()
    px = B.get("px") or [None] * len(cal)
    items = [(g, k) for g, ks in X["items"].items() for k in ks]
    head = (["日期", "指數收盤"] + [f"{k} {nm.get(k, k)}" for _, k in items] + [f"{g}（組平均）" for g, ks in X["items"].items() if ks]
            + ["四組平均", "位階"])
    rows = [",".join('"' + h.replace('"', "'") + '"' for h in head)]

    def f(x, n=1):
        return "" if x is None else f"{x:.{n}f}"
    for i in range(len(cal)):
        if raw[i] is None:
            continue
        r = [cal[i], f(px[i], 2)] + [f(B["heat"][k][i] if k in B["heat"] else None) for _, k in items]
        r += [f(X["g"][g][i], 2) for g, ks in X["items"].items() if ks] + [f(raw[i], 2), f(v[i])]
        rows.append(",".join(r))
    return "﻿" + "\n".join(rows) + "\n"                 # BOM：Excel 直接打開中文不亂碼


def publish(det: dict, csv: str, detail_path: Path | None = None, dash: Path | None = None) -> bool:
    """正式建頁時：寫 CSV（dashboard/x9mpos-{市場}.csv）、把這個市場的算式併進 data/lab/heat/mpos_detail.json；內容沒變不改寫。"""
    if not det:
        return False
    dpath, dash = detail_path or DETAIL, dash or DASH
    changed = False
    cp = dash / det["csv"]
    if not cp.exists() or cp.read_text(encoding="utf-8") != csv:
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(csv, encoding="utf-8")
        changed = True
    try:
        doc = json.loads(dpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    det = json.loads(json.dumps(det, ensure_ascii=False))     # 之後漲跌的鍵（21、63、126）存成 JSON 是字串：先轉一次再比
    if doc.get(det["mk"]) != det:
        doc[det["mk"]] = det
        dpath.parent.mkdir(parents=True, exist_ok=True)
        tmp = dpath.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        tmp.replace(dpath)
        changed = True
    return changed


# ── 研究紀錄頁：股市位階怎麼算（mposfwdspec 第 7 點） ──────────────────────────

ORDER = ("tw", "spx", "ixic", "ndx", "sox")
R_CSS = (
    ".mpr-steps{font-size:13.5px;line-height:1.75;padding-left:1.4em;margin:6px 0 12px}.mpr-steps b{font-variant-numeric:tabular-nums}"
    ".mpr-m{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin:10px 0}"
    ".mpr-m h3{margin:0 0 6px;font-size:16px}.mpr-m h4{margin:12px 0 4px;font-size:14px}"
    ".mpr-eq{font-size:13.5px;line-height:1.7;margin:4px 0;font-variant-numeric:tabular-nums}"
    ".mpr-t{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}"
    ".mpr-t th,.mpr-t td{padding:4px 6px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:top}"
    ".mpr-t th:first-child,.mpr-t td:first-child{text-align:left}.mpr-t thead th{color:var(--mut);font-weight:500}"
    ".mpr-t td.mpr-ok{color:var(--acc);font-weight:700}.mpr-t td.mpr-no{color:var(--mut)}.mpr-w{overflow-x:auto}"
    ".mpr-dl{display:inline-block;margin:6px 0;font-size:13px}"
)


def _f(x, n=1) -> str:
    return "—" if x is None else f"{x:,.{n}f}".replace("-", "−")


def _get(d: dict, h):
    """JSON 存過的鍵是字串（"21"），剛算好的是數字（21）。"""
    return (d or {}).get(str(h)) or (d or {}).get(h)


def research_body(doc: dict | None = None) -> str:
    """研究紀錄頁「股市位階」一節：步驟、每個市場最新一天的實際算式、之後漲跌的完整表與判定、每天的數字下載。"""
    from . import mposfwdspec as F
    if doc is None:
        try:
            doc = json.loads(DETAIL.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {}
    if not doc:
        return '<p class="rnote">股市位階的算式還沒準備好（每天建市場頁時更新）。</p>'
    e = html.escape
    steps = (
        "<ol class=\"mpr-steps\">"
        "<li><b>每一項的分數（0～100）</b>：市場頁景氣的每一項，都和自己的過去比，排在第幾百分位就是幾分（熱＝高；冷的方向會反過來）。"
        "日資料和過去 750 個交易日比、月資料和過去 120 個月比，只用當天以前、而且當時已經公布的數字；少數項目例外（例如均線排列直接換算、"
        "美股家計部門融資用過去 40 期），每一項的定義與來源在景氣的研究畫面。</li>"
        f"<li><b>每組分數</b>＝那一組裡今天有分數的項目取平均；至少要有 {S.MIN_ITEMS} 項有分數（項目比 {S.MIN_ITEMS} 少的組要全部有），不然那一組今天沒有分數。</li>"
        "<li><b>四組平均</b>＝四組分數的平均（四組都要有）；美股那斯達克、那斯達克 100、費半沒有算分的廣度項目，用三組平均。</li>"
        f"<li><b>位階</b>＝過去 {S.WIN:,} 個交易日（約 10 年，含今天）裡，四組平均比今天低的天數 ÷ 有四組平均的天數 × 10，四捨五入到小數一位；"
        f"有四組平均的天數不到 {S.MIN_DAYS:,} 天就不算。</li>"
        f"<li><b>字</b>：{S.X_LOW:g} 以下極端低位、{S.LOW:g} 以下低位、{S.X_HIGH:g} 以上極端高位、{S.HIGH:g} 以上高位，其他中間。</li>"
        f"<li><b>之後的漲跌</b>：那一天之後第 {'／'.join(str(h) for h in F.HORIZONS)} 個交易日（約 1、3、6 個月）的指數收盤 ÷ 那天收盤 − 1（不含息）。"
        f"每一區的「次數」＝段數：連續在這一區的日子算一段，離開不到 {F.GAP} 個交易日又回來併成同一段。"
        f"判定（三個都要過才算有差別）：段數 ≥ {F.MIN_EP}；和任一天平均差 ≥ "
        f"{'／'.join(f'{F.MIN_DIFF[h]:g}' for h in F.HORIZONS)} 個百分點；把日子照日期切成前後兩半，兩半和那一半的任一天比，方向都和全期一樣。"
        "日子一天一天算、窗互相重疊，同一段行情會被算很多次，所以看段數不看天數。</li>"
        "<li><b>已知的偏差</b>：哪些項目有算分，是景氣研究用全期資料驗過之後定的；台股位階 2019-11 才有，段數少。"
        "規格：<code>arm/lab/mposspec.py</code>（位階）、<code>arm/lab/mposfwdspec.py</code>（之後的漲跌）。</li></ol>")
    out = [f'<div id="mpos">{steps}']
    for mk in ORDER:
        d = doc.get(mk)
        if not d:
            continue
        gl = []
        for g in d["groups"]:
            if g.get("empty"):
                gl.append(f'<tr><td>{e(g["name"])}</td><td colspan="2">這個指數沒有算分的項目，不放進平均</td></tr>')
                continue
            its = "、".join(f'{e(k)} {e(n)} {_f(x)}' for k, n, x in g["items"])
            gl.append(f'<tr><td>{e(g["name"])}</td><td style="text-align:left;white-space:normal">{its}</td><td><b>{_f(g["avg"], 2)}</b></td></tr>')
        avgs = [g["avg"] for g in d["groups"] if not g.get("empty")]
        eq = (f'四組平均＝（{" ＋ ".join(_f(a, 2) for a in avgs)}）÷ {len(avgs)}＝<b>{_f(d["raw"], 2)}</b>。'
              f'過去 {S.WIN:,} 個交易日（{d["from"]}～{d["d"]}）有四組平均的 {d["win"]:,} 天裡，比 {_f(d["raw"], 2)} 低的有 {d["below"]:,} 天：'
              f'{d["below"]:,} ÷ {d["win"]:,} × 10＝<b>{10 * d["below"] / d["win"]:.2f}</b>，四捨五入＝<b>{d["x"]:g}</b>（{e(d["lv"])}）。')
        fw = d.get("fwd") or {}
        hs = [h for h in F.HORIZONS if _get(fw.get("any"), h)]
        rows = []
        for z in ("任一天",) + F.ZONES:
            for h in hs:
                s = _get(fw.get("any"), h) if z == "任一天" else _get((fw.get("z") or {}).get(z), h)
                if not s or not s.get("n"):
                    rows.append(f'<tr><td>{z}</td><td>{h}</td><td colspan="9">沒有這一區的日子</td></tr>')
                    continue
                if z == "任一天":
                    half = "／".join(_f(x, 2) for x in s.get("h") or [])
                    rows.append(f'<tr><td>{z}</td><td>{h}</td><td>{s["n"]:,}</td><td>—</td><td>{_f(s["avg"], 2)}</td><td>{_f(s["med"], 2)}</td>'
                                f'<td>{_f(s["up"])}%</td><td>{_f(s["min"], 1)}</td><td colspan="2">兩半的任一天：{half}</td><td>—</td></tr>')
                    continue
                hh = s.get("h") or [[None, None, 0], [None, None, 0]]
                ok = s.get("ok")
                rows.append(f'<tr><td>{z}</td><td>{h}</td><td>{s["n"]:,}</td><td>{s["ep"]}</td><td>{_f(s["avg"], 2)}</td><td>{_f(s["med"], 2)}</td>'
                            f'<td>{_f(s["up"])}%</td><td>{_f(s["min"], 1)}</td>'
                            f'<td>{_f(hh[0][0], 2)}（{hh[0][2]} 段）</td><td>{_f(hh[1][0], 2)}（{hh[1][2]} 段）</td>'
                            f'<td class="{"mpr-ok" if ok else "mpr-no"}">{"有差別" if ok else "看不出差別：" + e(s.get("why") or "")}</td></tr>')
        sp = "、".join(f'{h} 天：{_get(fw.get("split"), h)}' for h in hs if _get(fw.get("split"), h))
        out.append(
            f'<section class="mpr-m" id="mpos-{mk}"><h3>{e(d["name"])}：{d["d"]} 位階 {d["x"]:g}（{e(d["lv"])}）</h3>'
            f'<p class="mpr-eq">指數收盤 {_f(d.get("px"), 2)}；位階 {d["first"]} 起有數字。</p>'
            f'<h4>最新一天的算式</h4><div class="mpr-w"><table class="mpr-t"><thead><tr><th>組</th><th style="text-align:left">每一項的分數（代號 名稱 分數）</th><th>組平均</th></tr></thead>'
            f'<tbody>{"".join(gl)}</tbody></table></div><p class="mpr-eq">{eq}</p>'
            f'<a class="mpr-dl" href="{e(d["csv"])}" download>下載每天的數字（CSV：日期、指數收盤、每一項、四組、四組平均、位階）</a>'
            f'<h4>位階在各區之後的漲跌（%）</h4><div class="mpr-w"><table class="mpr-t"><thead><tr><th>區</th><th>之後幾個交易日</th><th>天數</th><th>段數</th>'
            f'<th>平均</th><th>中位數</th><th>上漲</th><th>最差</th><th>前一半平均</th><th>後一半平均</th><th>判定</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div><p class="mpr-eq">前後兩半的分界：{sp}。</p></section>')
    out.append("</div>")
    return "".join(out)


# ── 頁面 ─────────────────────────────────────────────────────────────────────

CSS = (
    ".mpz{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:0 0 14px}"
    ".mpz-top{display:block}"
    ".mpz-h{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}.mpz-h h2{margin:0;font-size:17px}.mpz-h small{color:var(--mut)}"
    ".mpz-big{font-size:34px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}.mpz-big small{font-size:14px;color:var(--mut);font-weight:400}"
    ".mpz-lv{font-weight:700;font-size:16px}.mpz-lv.lo{color:var(--t0)}.mpz-lv.hi{color:var(--t4)}.mpz-lv.mid{color:var(--ink2)}"
    ".mpz-sl{position:relative;height:8px;border-radius:4px;margin:12px 0 2px;"
    "background:linear-gradient(90deg,var(--c0) 0 30%,var(--line2) 30% 80%,var(--c4) 80%)}"
    ".mpz-sl b{position:absolute;top:-5px;width:18px;height:18px;margin-left:-9px;border-radius:50%;background:var(--ink);border:3px solid var(--panel)}"
    ".mpz-sl i{position:absolute;top:-4px;width:16px;height:16px;margin-left:-8px;border-radius:50%;border:2px solid var(--mut)}"
    ".mpz-sll{display:flex;justify-content:space-between;font-size:11px;color:var(--mut)}"
    ".mpz-sub{font-size:12.5px;color:var(--ink2);margin:6px 0 0}.mpz-fix{font-size:12px;color:var(--warn);margin:4px 0 0}"
    ".mpz-gs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px 10px;margin-top:10px;align-items:start}"
    "@media (max-width:1000px){.mpz-gs{grid-template-columns:1fr 1fr}}"
    ".mpz-g{display:grid;grid-template-columns:5.5em 1fr 4.5em;align-items:center;gap:8px;background:var(--card2);border-radius:8px;padding:6px 10px;font-size:13px}"
    ".mpz-g .hb{background:var(--line)}.mpz-g em{font-style:normal;font-size:12px;color:var(--mut);text-align:right}"
    ".mpz-m{display:flex;align-items:baseline;gap:8px;padding:6px 0;border-bottom:1px solid var(--line);font-size:13.5px}"
    ".mpz-m span{flex:1}.mpz-m b{font-size:18px;font-variant-numeric:tabular-nums}.mpz-m small{color:var(--mut);min-width:6.5em;text-align:right}"
    ".mpz-ct{font-size:14px;margin:14px 0 4px}.mpz-ct small{font-weight:400;color:var(--mut);font-size:12px;margin-left:6px}"
    ".mpz-svg{display:block;width:100%;height:auto}.mpz-svg .br{fill:var(--zh)}.mpz-svg .bg{fill:var(--zc)}"
    ".mpz-svg .ln{fill:none;stroke:var(--acc);stroke-width:1.4}.mpz-svg .gl{stroke:var(--line);stroke-dasharray:3 4}"
    ".mpz-svg text{font-size:11px;fill:var(--mut)}.mpz-svg .pl{fill:var(--ink2);font-weight:600}"
    ".mpz-svg .ph{fill:var(--c4);stroke:var(--panel);stroke-width:2}.mpz-svg .pg{fill:var(--c0);stroke:var(--panel);stroke-width:2}"
    ".mpz-cw{position:relative;overflow-x:auto;-webkit-overflow-scrolling:touch}"
    ".mpz-svg .mpz-lp{fill:none;stroke:var(--ink2);stroke-width:1.3}.mpz-svg .mpz-pn{fill:var(--ink2);font-weight:700;font-size:12px}"
    ".mpz-svg .mpz-hit{fill:transparent;pointer-events:all;cursor:crosshair}.mpz-svg .mpz-cl{stroke:var(--ink);stroke-width:1;stroke-dasharray:2 3;pointer-events:none}"
    ".mpz-tip{position:absolute;top:2px;z-index:2;background:var(--panel);border:1px solid var(--line2);border-radius:8px;padding:4px 8px;"
    "font-size:12px;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.12);pointer-events:none}.mpz-tip b{margin-right:8px}"
    ".mpz-rg{display:inline-flex;gap:2px;margin-left:10px;border:1px solid var(--line2);border-radius:999px;padding:1px;vertical-align:middle}"
    ".mpz-rg button{border:0;background:none;font:inherit;font-size:12px;font-weight:400;padding:2px 10px;border-radius:999px;color:var(--ink2);cursor:pointer}"
    ".mpz-rg button.on{background:var(--accbg);color:var(--acc);font-weight:700}"
    ".mpz-fs{font-size:13px;color:var(--ink2);margin:2px 0 6px;line-height:1.6}.mpz-tw{overflow-x:auto}"
    ".mpz-ft{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}"
    ".mpz-ft th,.mpz-ft td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}"
    ".mpz-ft th:first-child{text-align:left;font-weight:600}.mpz-ft thead th{color:var(--mut);font-weight:500}"
    ".mpz-ft th small,.mpz-ft td small{display:block;font-size:11px;color:var(--mut);font-weight:400}"
    ".mpz-ft td b{font-size:14px}.mpz-ft td.mpz-ok{background:var(--accbg);box-shadow:inset 3px 0 0 var(--acc)}.mpz-ft td.mpz-ok b{color:var(--acc)}"
    ".mpz-ft tr.mpz-zr{cursor:pointer}.mpz-ft tr.mpz-zr:hover th .mpz-zn{color:var(--acc)}"
    ".mpz-zn:after{content:' ▸';color:var(--mut);font-weight:400}.mpz-zr[aria-expanded=true] .mpz-zn:after{content:' ▾'}"
    ".mpz-ft tr.mpz-epr>td{padding:4px 0 10px;text-align:left;white-space:normal;background:var(--card2)}"
    ".mpz-ew{overflow-x:auto;max-height:340px;overflow-y:auto}"
    ".mpz-et{border-collapse:collapse;width:100%;font-size:12.5px;font-variant-numeric:tabular-nums}"
    ".mpz-et th,.mpz-et td{padding:4px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}"
    ".mpz-et th:first-child,.mpz-et td:first-child{text-align:left}.mpz-et thead th{color:var(--mut);font-weight:500;position:sticky;top:0;background:var(--card2)}"
    ".mpz-et td small{display:inline;margin-left:6px;color:var(--mut);font-size:11px}"
    ".mpz-et td.mpz-up{color:var(--t4)}.mpz-et td.mpz-dn{color:var(--t0)}.mpz-none{font-size:12.5px;color:var(--mut);margin:4px 8px}"
    ".mpz-ft tr.mpz-any{background:var(--card2)}.mpz-ft tr.mpz-cur>th,.mpz-ft tr.mpz-cur>td:not(.mpz-ok){background:var(--panel2,var(--card2))}"
    ".mpz-ft tr.mpz-cur th .mpz-zn{color:var(--acc)}"
    ".mpz-now{font-style:normal;font-size:11px;background:var(--accbg);color:var(--acc);border-radius:6px;padding:0 5px;margin-left:6px}"
    ".mpz-lk{font-size:12.5px;margin:8px 0 0}"
    ".mpz-gd>summary{list-style:none;cursor:pointer}.mpz-gd>summary::-webkit-details-marker{display:none}"
    ".mpz-gd>summary .mpz-g em:after{content:' ▸';color:var(--mut)}.mpz-gd[open]>summary .mpz-g em:after{content:' ▾'}"
    ".mpz-gd[open]>summary .mpz-g{border-bottom-left-radius:0;border-bottom-right-radius:0}"
    ".mpz-gl{background:var(--card2);border-radius:0 0 8px 8px;padding:2px 10px 6px;border-top:1px solid var(--line)}"
    ".mpz-it{display:grid;grid-template-columns:minmax(0,1fr) 60px 5.2em;align-items:center;gap:8px;width:100%;border:0;background:none;"
    "font:inherit;font-size:12.5px;color:var(--ink);text-align:left;padding:4px 0;cursor:pointer;border-bottom:1px dashed var(--line)}"
    ".mpz-it:last-child{border-bottom:0}.mpz-it span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
    ".mpz-it span:first-child:after{content:' ›';color:var(--mut)}.mpz-it em{font-style:normal;font-size:12px;color:var(--mut);text-align:right}"
    ".mpz-it .hb{height:6px;border-radius:3px;background:var(--line);overflow:hidden;display:block}.mpz-it .hb i{display:block;height:100%}"
    ".mpz-it:hover span:first-child{color:var(--acc)}"
    ".mpz-more{margin-top:12px;border-top:1px solid var(--line);padding-top:8px}"
    ".mpz-more>summary{cursor:pointer;font-size:14px;color:var(--acc);list-style:none;line-height:1.6}"
    ".mpz-more>summary::-webkit-details-marker{display:none}.mpz-more>summary:before{content:'▸ ';color:var(--mut)}"
    ".mpz-more[open]>summary:before{content:'▾ '}.mpz-more>summary small{display:block;color:var(--ink2);font-size:12.5px;margin-left:1.1em}"
    "@media (max-width:640px){.mpz-ft th,.mpz-ft td{padding:5px 4px}.mpz-ft td small{white-space:normal}.mpz-ft td b{font-size:13px}"
    ".mpz-gs{gap:6px}.mpz-g{grid-template-columns:minmax(0,1fr) auto;padding:6px 8px}.mpz-g .hb{display:none}"
    ".mpz-it{grid-template-columns:minmax(0,1fr) auto}.mpz-it .hb{display:none}.mpz-gd[open]{grid-column:1/-1}}"
    "@media (max-width:760px){.mpz-top{grid-template-columns:1fr}}"
    "@media (max-width:640px){.mpz-cw .mpz-svg{min-width:780px}}"
)


def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _nice(lo: float, hi: float) -> list[float]:
    """指數刻度：lo～hi 之間 2～4 個整齊的數（1、2、2.5、5 × 10 的次方）。"""
    import math
    span = max(hi - lo, 1e-9)
    for step in sorted({m * 10 ** e for e in range(int(math.log10(span)) - 2, int(math.log10(span)) + 2) for m in (1, 2, 2.5, 5)}):
        ts = [k * step for k in range(math.ceil(lo / step), math.floor(hi / step) + 1)]
        if 2 <= len(ts) <= 4:
            return ts
    return [lo, hi]


def _chart(d: list[str], v: list, pk: list, p: list | None = None, name: str = "指數", every: int = 1) -> str:
    """上面指數（對數刻度）、下面位階（0～10），同一條時間軸（不用兩個縱軸）。p＝指數收盤（和 d 一樣長）；
    every＝年份標示每幾年一個。滑過的資料放在後面的 <script type="application/json" class="mpz-dat">（JS 在 JS 常數）。"""
    import math
    W, L, R = 1000, 52, 14
    n = len(d)
    if n < 2:
        return ""
    T1, B1 = 14, 138                                    # 指數那一格
    T2, B2 = 170, 382                                   # 位階那一格
    H = B2 + 30
    pw = W - L - R
    xs = lambda i: L + i * pw / (n - 1)                 # noqa: E731
    ys = lambda x: T2 + (10 - x) / 10 * (B2 - T2)       # noqa: E731
    o = [f'<svg class="mpz-svg" viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(name)}和股市位階" '
         f'data-l="{L}" data-pw="{pw}" data-t="{T1}" data-b="{B2}">']
    pv = [x for x in (p or []) if x]
    if pv:
        lo, hi = math.log(min(pv)), math.log(max(pv))
        hi = hi if hi > lo else lo + 1e-6
        yp = lambda x: B1 - (math.log(x) - lo) / (hi - lo) * (B1 - T1)   # noqa: E731
        for t in _nice(min(pv), max(pv)):
            o.append(f'<line x1="{L}" x2="{W - R}" y1="{yp(t):.1f}" y2="{yp(t):.1f}" class="gl"/>'
                     f'<text x="{L - 6}" y="{yp(t) + 4:.1f}" text-anchor="end">{t:,.0f}</text>')
        seg, segs = [], []
        for i, x in enumerate(p):
            if not x:
                if seg:
                    segs.append(seg)
                seg = []
                continue
            seg.append(f"{xs(i):.1f},{yp(x):.1f}")
        if seg:
            segs.append(seg)
        for sg in segs:
            o.append(f'<polyline points="{" ".join(sg)}" class="mpz-lp"/>')
        o.append(f'<text x="{L + 4}" y="{T1 + 10}" class="mpz-pn">{html.escape(name)}</text>')
    o += [f'<rect x="{L}" y="{ys(10)}" width="{pw}" height="{ys(S.HIGH) - ys(10):.1f}" class="br"/>',
          f'<rect x="{L}" y="{ys(S.LOW)}" width="{pw}" height="{ys(0) - ys(S.LOW):.1f}" class="bg"/>',
          f'<text x="{L + 4}" y="{T2 + 11}" class="mpz-pn">股市位階</text>']
    for k in (0, S.LOW, 5, S.HIGH, 10):
        o.append(f'<text x="{L - 6}" y="{ys(k) + 4:.1f}" text-anchor="end">{k:g}</text>')
    for i in range(1, n):
        if d[i][:4] != d[i - 1][:4]:
            lab = int(d[i][:4]) % every == 0
            o.append(f'<line x1="{xs(i):.1f}" x2="{xs(i):.1f}" y1="{T1}" y2="{B2}" class="gl"/>'
                     + (f'<text x="{xs(i):.1f}" y="{H - 8}" text-anchor="middle">{d[i][:4]}</text>' if lab else ""))
    seg, segs = [], []
    for i, x in enumerate(v):
        if x is None:
            if seg:
                segs.append(seg)
            seg = []
            continue
        seg.append(f"{xs(i):.1f},{ys(x):.1f}")
    if seg:
        segs.append(seg)
    for sg in segs:
        o.append(f'<polyline points="{" ".join(sg)}" class="ln"/>')
    pos = {x: i for i, x in enumerate(d)}
    last = {"hi": [], "lo": []}                         # 同一種點的字太近就錯開一行（不重疊）
    for day, x, kind in pk:
        i = pos.get(day)
        if i is None:
            continue
        up = kind == "hi"
        cx = xs(i)
        tx = min(max(cx, L + 30), W - R - 30)             # 最左、最右的字往內收，不被邊界切掉
        lift = 13 if any(abs(tx - t) < 64 and not k for t, k in last[kind]) else 0
        last[kind].append((tx, lift))
        ty = ys(x) - 9 - lift if up else ys(x) + 17 + lift
        o.append(f'<circle cx="{cx:.1f}" cy="{ys(x):.1f}" r="4.5" class="{"ph" if up else "pg"}"/>'
                 f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" class="pl">{day[2:4]}/{day[5:7]} {x:.1f}</text>')
    o.append(f'<rect x="{L}" y="{T1}" width="{pw}" height="{B2 - T1}" class="mpz-hit"/>')
    dat = {"d": [x.replace("-", "") for x in d], "p": [None if not x else round(x, 2) for x in (p or [None] * n)], "v": v}
    return "".join(o) + "</svg>" + f'<script type="application/json" class="mpz-dat">{json.dumps(dat, separators=(",", ":"))}</script>'


def _weekly(idx: list[int], cal: list[str], v: list | None = None) -> list[int]:
    """每一週一點：那一週最後一個有位階的交易日（那一週都沒有就用最後一天）；最後一天一定留。"""
    from datetime import date
    out, wk = [], []
    for k, i in enumerate(idx):
        wk.append(i)
        if k + 1 == len(idx) or date.fromisoformat(cal[idx[k + 1]]).isocalendar()[:2] != date.fromisoformat(cal[i]).isocalendar()[:2]:
            ok = [j for j in wk if v is None or v[j] is not None]
            out.append(ok[-1] if ok else wk[-1])
            wk = []
    return out


def _pct(x) -> str:
    return "—" if x is None else f"{x:+.1f}%".replace("-", "−")


def fwd_msg(R: dict) -> str:
    """之後漲跌那一句（市場頁收起的摘要也用）：過關的格子照寫，其他各區和任一天差不多。"""
    from . import mposfwdspec as F
    name = {21: "1 個月", 63: "3 個月", 126: "6 個月"}
    by: dict = {}
    for z in F.ZONES:
        for h in F.HORIZONS:
            s = ((R.get("z") or {}).get(z) or {}).get(h) or {}
            a = (R.get("any") or {}).get(h) or {}
            if s.get("ok"):
                by.setdefault(z, []).append(f'{name[h]}平均 {_pct(s["avg"])}（任一天 {_pct(a.get("avg"))}）')
    if not by:
        return "過去各區之後的漲跌，和任一天差不多。"
    return "；".join(f"過去在{z}的時候，之後 {'、'.join(v)}" for z, v in by.items()) + "；其他各區和任一天差不多。"


def _ymd(d: str) -> str:
    return d.replace("-", "/")


def _ep_rows(eps: list, hs: list) -> str:
    """一區的每一段（規格 VER 2 第 6 點）：期間、天數、進入那天的位階與指數、從進入那天算之後的漲跌。"""
    if not eps:
        return '<p class="mpz-none">沒有這一區的日子</p>'
    name = {21: "1 個月", 63: "3 個月", 126: "6 個月"}
    trs = []
    for r in eps:
        per = _ymd(r["f"]) if r["f"] == r["t"] else f'{_ymd(r["f"])}～{_ymd(r["t"])}'
        cs = "".join(f'<td class="{_pcls(r.get(str(h)))}">{"還沒到" if r.get(str(h)) is None else _pct(r.get(str(h)))}</td>' for h in hs)
        trs.append(f'<tr><td>{per}<small>{r["n"]} 天</small></td><td>{r["x"]:g}<small>{_n0(r.get("p"))}</small></td>{cs}</tr>')
    return ('<table class="mpz-et"><thead><tr><th>每一次（進入那天～最後一天）</th><th>進入時的位階・指數</th>'
            + "".join(f"<th>之後 {name[h]}</th>" for h in hs) + f'</tr></thead><tbody>{"".join(trs)}</tbody></table>')


def _pcls(x) -> str:
    return "" if x is None else "mpz-up" if x > 0 else "mpz-dn" if x < 0 else ""


def _n0(x) -> str:
    return "—" if x is None else f"{x:,.0f}"


def fwd_html(R: dict, now_zone: str, since: str) -> str:
    """位階和之後的漲跌（規格 mposfwdspec VER 2 第 6 點）：每一區之後 1、3、6 個月；任一天寫一次；
    有差別的格子標出來（其他照常、滑過寫原因）；每一區點開列出每一次。"""
    from . import mposfwdspec as F
    hs = [h for h in F.HORIZONS if h in R.get("any", {})]
    if not hs:
        return ""
    name = {21: "之後 1 個月", 63: "3 個月", 126: "6 個月"}

    def cell(s, cls="", tip=""):
        if not s or not s.get("n"):
            return '<td class="mpz-na">—</td>'
        t = f' title="{html.escape(tip)}"' if tip else ""
        return (f'<td class="{cls}"{t}><b>{_pct(s["avg"])}</b><small>上漲 {s["up"]:.0f}%・最差 {_pct(s["min"])}</small></td>')
    rows = ['<tr class="mpz-any"><th>任一天</th>' + "".join(cell(R["any"][h]) for h in hs) + "</tr>"]
    eps = R.get("ep") or {}
    for z in F.ZONES:
        zs = R["z"].get(z) or {}
        n_ep = len(eps.get(z) or [])
        cells = []
        for h in hs:
            s = zs.get(h) or {}
            if s.get("ok"):
                cells.append(cell(s, "mpz-ok", "這一格過去和任一天不一樣"))
            else:
                cells.append(cell(s, "", "和任一天差不多：" + (s.get("why") or "")))
        now = '<em class="mpz-now">現在</em>' if z == now_zone else ""
        rows.append(f'<tr class="mpz-zr{" mpz-cur" if now else ""}" tabindex="0" role="button" aria-expanded="false">'
                    f'<th><span class="mpz-zn">{z}</span>{now}<small>次數 {n_ep}</small></th>{"".join(cells)}</tr>'
                    f'<tr class="mpz-epr" hidden><td colspan="{len(hs) + 1}"><div class="mpz-ew">{_ep_rows(eps.get(z) or [], hs)}</div></td></tr>')
    msg = fwd_msg(R)
    return (f'<h3 class="mpz-ct">位階和之後的漲跌<small>{since[:4]} 起・指數漲跌、不含息・點一區看每一次</small></h3>'
            f'<p class="mpz-fs">{msg}</p><div class="mpz-tw"><table class="mpz-ft"><thead><tr><th></th>'
            + "".join(f"<th>{name[h]}</th>" for h in hs) + f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


JS = r"""
(function () {                                             // 股市位階：滑過看那一天的指數與位階、切換近 5 年／全部（arm/lab/mpos.py；換內容之後照樣有效）
  if (window.__mpzOn) return;
  window.__mpzOn = 1;
  function dat(w) {
    if (!w.__d) { const s = w.querySelector('.mpz-dat'); try { w.__d = s ? JSON.parse(s.textContent) : null; } catch (e) { w.__d = null; } }
    return w.__d;
  }
  function num(x) { return x == null ? '—' : Math.round(x).toLocaleString('en-US'); }
  function hide(w) {
    const t = w && w.querySelector('.mpz-tip'), c = w && w.querySelector('.mpz-svg .mpz-cl');
    if (t) t.hidden = true;
    if (c) c.style.display = 'none';
  }
  function move(e) {
    const svg = e.target && e.target.closest ? e.target.closest('.mpz-svg') : null;
    if (!svg) return;
    const w = svg.closest('.mpz-cw'), D = w ? dat(w) : null;
    if (!D || !D.d.length) return;
    const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal, sx = vb.width / r.width;
    const L = +svg.dataset.l, PW = +svg.dataset.pw, n = D.d.length;
    let k = Math.round(((e.clientX - r.left) * sx - L) / PW * (n - 1));
    k = Math.max(0, Math.min(n - 1, k));
    const cx = L + k * PW / (n - 1);
    let ln = svg.querySelector('.mpz-cl');
    if (!ln) {
      ln = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      ln.setAttribute('class', 'mpz-cl'); ln.setAttribute('y1', svg.dataset.t); ln.setAttribute('y2', svg.dataset.b);
      svg.appendChild(ln);
    }
    ln.setAttribute('x1', cx); ln.setAttribute('x2', cx); ln.style.display = '';
    const t = w.querySelector('.mpz-tip'), d = D.d[k], v = D.v[k];
    t.innerHTML = '<b>' + d.slice(0, 4) + '/' + d.slice(4, 6) + '/' + d.slice(6) + '</b>指數 ' + num(D.p[k]) + '・位階 ' + (v == null ? '—' : v.toFixed(1));
    t.hidden = false;
    const wr = w.getBoundingClientRect(), x = cx / sx + r.left - wr.left + w.scrollLeft, tw = t.offsetWidth || 160;
    t.style.left = Math.max(w.scrollLeft + 4, Math.min(x - tw / 2, w.scrollLeft + wr.width - tw - 4)) + 'px';
  }
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerdown', move);
  document.addEventListener('pointerout', function (e) {
    const svg = e.target && e.target.closest ? e.target.closest('.mpz-svg') : null;
    if (svg && !(e.relatedTarget && svg.contains(e.relatedTarget))) hide(svg.closest('.mpz-cw'));
  });
  function endAll(root) { (root || document).querySelectorAll('.mpz-cw:not([hidden])').forEach(function (c) { c.scrollLeft = c.scrollWidth; }); }
  window.mpzInit = function () {
    let on = false;
    try { on = localStorage.getItem('mpzMore') === '1'; } catch (e) { on = false; }
    document.querySelectorAll('.mpz-more').forEach(function (d) { if (on) d.open = true; });
    endAll();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', window.mpzInit); else window.mpzInit();
  document.addEventListener('toggle', function (e) {
    const d = e.target;
    if (!d || !d.classList || !d.classList.contains('mpz-more')) return;
    try { localStorage.setItem('mpzMore', d.open ? '1' : '0'); } catch (err) { /* 存不了就不記 */ }
    if (d.open) endAll(d);
  }, true);
  function zr(tr) {
    const nx = tr.nextElementSibling;
    if (!nx || !nx.classList.contains('mpz-epr')) return;
    nx.hidden = !nx.hidden;
    tr.setAttribute('aria-expanded', nx.hidden ? 'false' : 'true');
  }
  document.addEventListener('keydown', function (e) {
    const tr = e.target && e.target.closest ? e.target.closest('.mpz-zr') : null;
    if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); zr(tr); }
  });
  document.addEventListener('click', function (e) {
    const tr = e.target && e.target.closest ? e.target.closest('.mpz-zr') : null;
    if (tr) { zr(tr); return; }
    const b = e.target && e.target.closest ? e.target.closest('.mpz-rg button') : null;
    if (!b) return;
    const box = b.closest('.mpz');
    box.querySelectorAll('.mpz-rg button').forEach(function (x) { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on ? 'true' : 'false'); });
    box.querySelectorAll('.mpz-cw').forEach(function (c) { c.hidden = c.dataset.r !== b.dataset.r; hide(c); });
    const c = box.querySelector('.mpz-cw:not([hidden])');
    if (c) c.scrollLeft = c.scrollWidth;
  });
})();
"""


def block(B: dict, X: dict | None = None, log: dict | None = None, mk: str = "tw", R: dict | None = None, pxname: str = "") -> str:
    """市場頁最上面一塊（規格第 4～8 點；mk＝tw 或美股指數代號）。"""
    from . import heatspec as HS
    from .heatpage import n0
    e = html.escape
    _NM = {k: nm for k, _, nm, *_ in HS.IND}
    X = X or compute(B, S.GROUPS if mk == "tw" else S.GROUPS_US)
    v, cal = X["v"], X["cal"]
    idx = [i for i, x in enumerate(v) if x is not None]
    if not idx:
        return ""
    i = idx[-1]
    d, x = cal[i], v[i]
    prev = next((v[j] for j in range(i - 1, -1, -1) if v[j] is not None), None)
    w4 = v[i - 20] if i >= 20 else None
    log = read_log(log_path(mk)) if log is None else log
    fix = ""
    if prev is not None:
        pd = cal[max(j for j in idx if j < i)]
        pub = (log.get(pd) or {}).get("v")
        if pub is not None and abs(pub - prev) >= 0.1:
            fix = f'<p class="mpz-fix">昨天公布 {pub:g}，用今天的資料重算是 {prev:g}（之前幾天的資料補進來了）。</p>'
    lv = label(x)
    cls = "lo" if x <= S.LOW else "hi" if x >= S.HIGH else "mid"
    below = round(x * 10)
    sub = [f"昨天 {prev:g}" if prev is not None else "", f"20 個交易日前 {w4:g}" if w4 is not None else ""]
    how = "四組（價格位置、部位與籌碼、情緒、廣度）平均之後，和過去 10 年每一天比；0＝最低、10＝最高。"
    miss = [n for n, ks in X["items"].items() if not ks]
    if miss:
        how += f"這個指數的{'、'.join(miss)}沒有算分的項目，不放進平均。"
    gs = []
    for name, ks in X["items"].items():
        g = X["g"][name][i]
        if not ks:
            gs.append(f'<div class="mpz-g"><span>{name}</span><span class="hb"><i class="na"></i></span><em>沒有算分的項目</em></div>')
            continue
        if g is None:
            gs.append(f'<div class="mpz-g"><span>{name}</span><span class="hb"><i class="na"></i></span><em>—</em></div>')
            continue
        b = HS.band(g)
        its = []
        for k in ks:
            hv = (B["heat"].get(k) or [None] * (i + 1))[i] if k in B["heat"] else None
            hb = HS.band(hv) if hv is not None else ""
            its.append(f'<button type="button" class="mpz-it" data-open="item:{e(k)}" aria-haspopup="dialog"><span>{e(_NM.get(k, k))}</span>'
                       f'<span class="hb"><i class="{_band_cls(hb) if hv is not None else "na"}" style="width:{(hv or 0):.0f}%"></i></span>'
                       f'<em>{"—" if hv is None else f"{n0(hv)} {hb}"}</em></button>')
        gs.append(f'<details class="mpz-gd"><summary><div class="mpz-g"><span>{name}</span><span class="hb"><i class="{_band_cls(b)}" style="width:{g:.0f}%"></i></span>'
                  f'<em>{n0(g)} {b}</em></div></summary><div class="mpz-gl">{"".join(its)}</div></details>')
    y0 = f"{int(d[:4]) - S.CHART_YEARS}{d[4:]}"
    c0 = next((j for j, dd in enumerate(cal) if dd >= y0), 0)
    px = B.get("px") or [None] * len(cal)
    cd, cv, cp = cal[c0:i + 1], v[c0:i + 1], px[c0:i + 1]
    pk = [p for p in peaks(cal[:i + 1], v[:i + 1]) if p[0] >= cal[c0]]     # 整段算、只畫近 5 年（圖的左邊界不會冒出假的高低點）
    f0 = idx[0]
    wk = _weekly(list(range(f0, i + 1)), cal, v)
    nm = pxname or ("加權指數" if mk == "tw" else mk.upper())
    every = 1 if len({cal[j][:4] for j in wk}) <= 12 else 2
    fw = fwd_html(R, lv, cal[f0]) if R is not None else ""
    link = f'<p class="mpz-lk"><a href="x9r.html#mpos-{mk}">怎麼算、每天的數字（研究紀錄）</a></p>'
    return (f'<section class="mpz" id="mpz"><div class="mpz-top"><div>'
            f'<div class="mpz-h"><h2 title="{e(how)}">股市位階</h2><small>{_md(d)} 收盤</small></div>'
            f'<div class="mpz-h" style="margin-top:6px"><span class="mpz-big">{x:g}<small> /10</small></span>'
            f'<span class="mpz-lv {cls}">{lv}</span><small>{"・".join(s for s in sub if s)}</small></div>'
            f'<div class="mpz-sl"><i style="left:{(prev if prev is not None else x) * 10:.0f}%"></i><b style="left:{x * 10:.0f}%"></b></div>'
            f'<div class="mpz-sll"><span>低（{S.LOW:g} 以下）</span><span>高（{S.HIGH:g} 以上）</span></div>'
            f'<p class="mpz-sub">過去 10 年有 {below}% 的日子比現在低。空心圈＝昨天。</p>{fix}'
            f'<div class="mpz-gs">{"".join(gs)}</div></div></div>'
            f'<details class="mpz-more"><summary><b>位階和指數、之後的漲跌</b><small>{e(fwd_msg(R)) if R is not None else ""}</small></summary>'
            f'<h3 class="mpz-ct">位階和指數<span class="mpz-rg" role="group" aria-label="期間">'
            f'<button type="button" data-r="5y" class="on" aria-pressed="true">近 {S.CHART_YEARS} 年</button>'
            f'<button type="button" data-r="all" aria-pressed="false">全部（{cal[f0][:4]} 起）</button></span>'
            f'<small>藍帶＝低（{S.LOW:g} 以下）、紅帶＝高（{S.HIGH:g} 以上）；點＝每一段的高低點</small></h3>'
            f'<div class="mpz-cw" data-r="5y">{_chart(cd, cv, pk, cp, nm)}<div class="mpz-tip" hidden></div></div>'
            f'<div class="mpz-cw" data-r="all" hidden>{_chart([cal[j] for j in wk], [v[j] for j in wk], [], [px[j] for j in wk], nm, every)}'
            f'<div class="mpz-tip" hidden></div></div>{fw}</details>{link}'
            '<script>if(window.mpzInit)window.mpzInit();</script></section>')


def _band_cls(b: str) -> str:
    from .heatpage import BAND_CLS
    return BAND_CLS.get(b, "b2")
