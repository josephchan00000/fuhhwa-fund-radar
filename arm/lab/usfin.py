"""美股個股卡的季報（docs/lab_review_plan.md 第 4 節 (b)(c)）：配置頁美股會出現的股票（手上的、要買的、名單前 20 名），
每一季的營收、毛利、營業利益、淨利、EPS、股東權益，以及流通股數——都是 SEC 第一次公布的數字（資料分支 secfin 存的那一份）。

每週六資料分支的 SEC 財報更新以後跑（.github/workflows/ussx_weekly.yml：USSX_DIR 指到資料分支），寫 data/lab/ussx_fin.json 進 main；
每天建頁時 uscardpage 讀它，配上每天的股價算成長、三率、ROE、本益比、淨值比（只是描述這家公司，不參與選股）。

單季的算法和選股用的同一套（ussxfeat.sec_quarters、first_filed：第四季＝全年 − 前三季，營收取最早公布的項目），
所以第四季的 EPS 是全年減前三季，可能和公司公布的第四季 EPS 差一點。

同產業比較（第 4 節 (e)）：GICS 細產業（維基百科的 S&P 500／400／600 成分股表，約 1,500 家，每週六抓一次 → data/lab/ussx_gics.json；
那斯達克篩選器的分類太粗、常歸錯，例：煉油公司被歸到天然氣配送、液化石油氣運輸和郵輪公司同一類，不用），同一個細產業裡市值最接近的
幾家（市值＝資料分支篩選器）配上它們自己的 SEC 季報算最新一季營收年增、近四季營益率、近四季 ROE、本益比（市值 ÷ 近四季淨利）、
近一年股價漲跌（資料分支的日線）。不在 S&P 1500 的公司沒有分類，不比。

data/lab/ussx_gics.json：{"d": 抓的日期, "s": {代號: [指數（500／400／600）, GICS 大類, GICS 細產業, 公司名]}}（某一頁抓不到就沿用那一頁舊的）

data/lab/ussx_fin.json：
  {"ver", "made": 台北日期, "sec": 資料分支 SEC 財報抓的日期, "scr": 篩選器的日期, "gics": GICS 的日期, "codes": [這一批], "names": {代號: 公司名},
   "s": {代號: {"q": [[季底, 營收公布日, 營收, 毛利, 營業利益, 淨利, EPS, 股東權益]]（金額單位百萬美元；沒有＝null；依季底排）,
               "sh": [[日期, 公布日, 流通股數（百萬股）]],
               "peer": {"ind": GICS 細產業, "sec": GICS 大類, "n": 同細產業的家數（S&P 1500 裡）, "rk": 這一檔的市值名次,
                        "rows": [[代號, 市值（億美元）, 最新一季營收年增, 近四季營益率, 近四季 ROE, 本益比, 近一年股價漲跌]]}}}}
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import fund_intro as FI
from . import ussxspec as X

ROOT = Path(__file__).resolve().parents[2]
FIN = ROOT / "data" / "lab" / "ussx_fin.json"
GICS = ROOT / "data" / "lab" / "ussx_gics.json"
VER = 2
WIKI = {"500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"}
WIKI_MIN = {"500": 450, "400": 350, "600": 500}          # 一頁解析到的家數少於這個＝表格改版，沿用舊的
NQ = 28              # 留近幾季（本益比和自己過去 5 年比：每一天要近四季 EPS → 20 季＋3 季，多留一年）
LIST_N = 20          # 名單前幾名也算（配置頁每週只列前 5 名，但名單一週內不會變；多算幾檔省得換人時缺）
PEER_N = 6           # 同產業比較列幾家（含這一檔）：同細產業裡市值最接近的 5 家
PEER_MIN = 3         # 同細產業（含這一檔）有季報的不到幾家就不比


def _m(v) -> float | None:
    return None if v is None else round(float(v) / 1e6, 3)


def summary(doc: dict) -> dict | None:
    """一家公司的 secfin 存檔 → {"q": [...], "sh": [...]}（見檔頭）；沒有任何一季的營收＝None。"""
    from . import ussxfeat as F
    Q = F.sec_quarters((doc or {}).get("f") or {})
    rev = F.first_filed(Q, X.REV_TAGS, X.REV_EXTRA)
    if not rev:
        return None
    cost = F.first_filed(Q, X.COST_TAGS)
    gp = dict(Q.get("GrossProfit") or {})
    for e, (r, fd) in rev.items():
        if e not in gp and e in cost:
            gp[e] = (r - cost[e][0], max(fd, cost[e][1]))
    M = {k: d for k, d in (("gp", gp), ("oi", Q.get("OperatingIncomeLoss") or {}), ("ni", Q.get("NetIncomeLoss") or {}),
                           ("eps", Q.get("EarningsPerShareDiluted") or {}), ("eq", Q.get("StockholdersEquity") or {}))}
    K = {k: F._ko(d) for k, d in M.items()}

    def val(k: str, e: str):
        d = M[k]
        if e in d:
            return d[e][0]
        from datetime import date
        kk = F._near_o(K[k], date.fromisoformat(e).toordinal(), X.SEC_TOL_D)
        return d[kk][0] if kk is not None else None

    q = []
    for e in sorted(rev)[-NQ:]:
        eps = val("eps", e)
        q.append([e, rev[e][1], _m(rev[e][0]), _m(val("gp", e)), _m(val("oi", e)), _m(val("ni", e)),
                  None if eps is None else round(float(eps), 4), _m(val("eq", e))])
    sh = sorted([e, fd, _m(v)] for e, (v, fd) in (Q.get("EntityCommonStockSharesOutstanding") or {}).items() if v)
    return {"q": q, "sh": sh[-NQ:]}


# ── 單季數字的共用算法（uscardpage 也用） ─────────────────────────────────────────

def _d(x: str):
    from datetime import date
    return date.fromisoformat(x)


def yoy(q: list, k: int, i: int, pos_only: bool = True) -> float | None:
    """第 i 季的第 k 欄比去年同一季（季底差 350～380 天）；去年那一季要是正的。"""
    e = _d(q[i][0])
    for j in range(i - 1, max(-1, i - 7), -1):
        n = (e - _d(q[j][0])).days
        if 350 <= n <= 380:
            a, b = q[i][k], q[j][k]
            if a is None or b is None or (pos_only and b <= 0) or b == 0:
                return None
            return a / b - 1
        if n > 380:
            break
    return None


def four(q: list, i: int) -> list[int] | None:
    """第 i 季往前連續四季（第一季和第四季的季底差 250～300 天）的位置。"""
    if i < 3:
        return None
    n = (_d(q[i][0]) - _d(q[i - 3][0])).days
    return [i - 3, i - 2, i - 1, i] if 250 <= n <= 300 else None


def ttm(q: list, i: int, k: int) -> float | None:
    """第 i 季往前連續四季第 k 欄的合計（有一季沒有＝None）。"""
    ix = four(q, i)
    if not ix:
        return None
    xs = [q[j][k] for j in ix]
    return None if None in xs else sum(xs)


def roe(q: list, i: int) -> float | None:
    """近四季淨利 ÷ 期初期末股東權益的平均（期初＝四季以前那一季的季底；和選股的近四季 ROE 同一個算法）。"""
    ni = ttm(q, i, 5)
    if ni is None or i < 4:
        return None
    e0, e1 = q[i][7], q[i - 4][7]
    if not e0 or not e1 or e0 <= 0 or e1 <= 0:
        return None
    return ni / ((e0 + e1) / 2)


def peer_row(code: str, F: dict | None, cap: float | None, px: dict | None) -> list:
    """同產業比較的一列：[代號, 市值（億美元）, 最新一季營收年增, 近四季營益率, 近四季 ROE, 本益比, 近一年股價漲跌]。"""
    q = (F or {}).get("q") or []
    i = len(q) - 1
    g = om = r = pe = None
    if q:
        g = yoy(q, 2, i)
        rv, oi, ni = ttm(q, i, 2), ttm(q, i, 4), ttm(q, i, 5)
        om = oi / rv if rv and oi is not None and rv > 0 else None
        r = roe(q, i)
        pe = cap / (ni * 1e6) if cap and ni and ni > 0 else None
    r1 = None
    ds, cs = (px or {}).get("d") or [], (px or {}).get("c") or []
    if ds:
        from datetime import timedelta
        t = (_d(ds[-1]) - timedelta(days=365)).isoformat()
        k = max((j for j, d in enumerate(ds) if d <= t), default=None)
        if k is not None and cs[k] > 0:
            r1 = cs[-1] / cs[k] - 1
    rd = (lambda x, n=4: None if x is None else round(x, n))
    return [code, None if cap is None else round(cap / 1e8, 1), rd(g), rd(om), rd(r), rd(pe, 1), rd(r1)]


def peers(code: str, gics: dict, scr: dict, sec_of, px_of) -> dict | None:
    """同 GICS 細產業裡市值最接近的幾家（含這一檔；市值＝篩選器）。sec_of(代號) → summary；px_of(代號) → 日線。"""
    import math
    g = gics.get(code)
    me = scr.get(code) or []
    if not g or len(me) < 6 or not me[5]:
        return None
    sub = g[2]
    grp = [(k, (scr.get(k) or [None] * 6)[5]) for k, v in gics.items() if v[2] == sub]
    grp = [(k, c) for k, c in grp if c]
    grp.sort(key=lambda x: -x[1])
    rk = next((i + 1 for i, (k, _) in enumerate(grp) if k == code), None)
    lc = math.log(me[5])
    cand = sorted((x for x in grp if x[0] != code), key=lambda x: abs(math.log(x[1]) - lc))
    rows = [peer_row(code, sec_of(code), me[5], px_of(code))]
    for k, cap in cand:
        if len(rows) >= PEER_N:
            break
        F = sec_of(k)
        if F:
            rows.append(peer_row(k, F, cap, px_of(k)))
    if len(rows) < PEER_MIN:
        return None
    rows.sort(key=lambda x: -(x[1] or 0))
    return {"ind": sub, "sec": g[1], "n": len(grp), "rk": rk, "rows": rows}


# ── GICS 細產業（維基百科；只在 CI，本容器擋 wikipedia） ─────────────────────────────

def _cell(x: str) -> str:
    import html as H
    import re
    x = re.sub(r"<sup[^>]*>.*?</sup>", "", x, flags=re.S)
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", x))).strip()


def parse_wiki(html: str) -> dict[str, list]:
    """維基百科 S&P 成分股頁 → {代號（Yahoo 寫法）: [GICS 大類, GICS 細產業, 公司名]}。用表頭找欄位（Symbol／Ticker、Security／Company、
    GICS Sector、GICS Sub-Industry），找第一個有這幾欄的表格。"""
    import re
    for t in re.findall(r"<table[^>]*>.*?</table>", html or "", re.S):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
        if not rows:
            continue
        hd = [_cell(x).lower() for x in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S)]
        col = lambda *ws: next((i for i, h in enumerate(hd) if any(w in h for w in ws)), None)
        ci, cn, cs, cu = col("symbol", "ticker"), col("security", "company"), col("gics sector"), col("sub-industry", "sub industry")
        if None in (ci, cs, cu):
            continue
        out = {}
        for r in rows[1:]:
            cells = [_cell(x) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
            if len(cells) <= max(ci, cs, cu):
                continue
            sym = cells[ci].upper().replace(".", "-").replace("/", "-")
            if re.match(r"^[A-Z][A-Z\-]{0,6}$", sym) and cells[cu]:
                out[sym] = [cells[cs], cells[cu], cells[cn] if cn is not None and cn < len(cells) else ""]
        if out:
            return out
    return {}


def load_gics(path: Path | None = None) -> dict:
    try:
        return json.loads((path or GICS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def update_gics(fetch=None, path: Path | None = None, today: str | None = None) -> dict:
    """三頁各抓一次；解析到的家數夠才換掉那一頁的舊資料。回 {"500": 家數或錯誤, ...}；有變才寫檔。fetch(url) → HTML 文字。"""
    from .heatfetch import BROWSER, _get
    fetch = fetch or (lambda u: _get(u, timeout=90, headers={"User-Agent": BROWSER}).decode("utf-8", "replace"))
    old = load_gics(path)
    cur = {k: v for k, v in (old.get("s") or {}).items()}
    st = {}
    for ix, url in WIKI.items():
        try:
            got = parse_wiki(fetch(url))
        except Exception as e:                               # noqa: BLE001
            st[ix] = f"{type(e).__name__}"
            continue
        if len(got) < WIKI_MIN[ix]:
            st[ix] = f"只有 {len(got)} 家，沿用舊的"
            continue
        cur = {k: v for k, v in cur.items() if v[0] != ix}
        for k, v in got.items():
            cur.setdefault(k, [ix] + v)
        st[ix] = len(got)
    if cur and cur != (old.get("s") or {}):
        if today is None:
            from ..clock import today_tw
            today = today_tw().isoformat()
        p = path or GICS
        p.write_text(json.dumps({"d": today, "s": dict(sorted(cur.items()))}, ensure_ascii=False, separators=(",", ":")) + "\n",
                     encoding="utf-8")
        st["saved"] = True
    return st


def codes_for(L: dict) -> list[str]:
    """這一批：配置頁美股會出現的（fund_intro.qm_codes）＋名單前 LIST_N 名。"""
    a, _ = FI.qm_codes(L)
    b = [str(x.get("c") or "") for x in ((L or {}).get("now") or {}).get("list") or []][:LIST_N]
    return list(dict.fromkeys(c for c in a + b if c))


def build(L: dict, made: str | None = None, name_fetch=None) -> dict:
    """每週紀錄 L → 存檔內容（讀 ussxdata.data_dir() 的 sec/、screen、px/，USSX_DIR 指到資料分支）。
    name_fetch＝ussxdata.names_for 的 fetch（本容器擋那斯達克：傳 lambda: {}）。"""
    from . import secfin as SF
    from . import ussxdata as UD
    memo: dict = {}

    def sec_of(k):
        if k not in memo:
            try:
                memo[k] = summary(SF.load(k))
            except Exception:                                # noqa: BLE001 —— 一家讀不到只少那一家
                memo[k] = None
        return memo[k]

    def px_of(k):
        try:
            return UD.load_px(k)
        except Exception:                                    # noqa: BLE001
            return None

    try:
        scr = UD.load_screen() or {}
    except Exception:                                        # noqa: BLE001
        scr = {}
    G = load_gics()
    gics = G.get("s") or {}
    out = {}
    for c in codes_for(L):
        x = sec_of(c)
        if x:
            x = dict(x)
            pr = peers(c, gics, scr, sec_of, px_of) if scr and gics else None
            if pr:
                x["peer"] = pr
            out[c] = x
    if made is None:
        from ..clock import today_tw
        made = today_tw().isoformat()
    pc = sorted({r[0] for x in out.values() for r in (x.get("peer") or {}).get("rows") or []})
    names = {k: gics[k][3] for k in pc if (gics.get(k) or [None] * 4)[3]}
    miss = [k for k in pc if k not in names]
    if miss:
        names.update(UD.names_for(miss, old=(load() or {}).get("names") or {}, fetch=name_fetch))
    return {"ver": VER, "made": made, "sec": (SF.load_meta() or {}).get("asof"), "scr": (UD.load_meta() or {}).get("screen"),
            "gics": G.get("d"), "codes": codes_for(L), "names": names, "s": out}


def load(path: Path | None = None) -> dict:
    """存檔；版本不同＝沒有。"""
    try:
        doc = json.loads((path or FIN).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if doc.get("ver") == VER else {}


def save(doc: dict, path: Path | None = None) -> bool:
    """內容沒變（made 不算）就不寫；回有沒有寫。"""
    p = path or FIN
    old = load(p)
    if old and {k: v for k, v in old.items() if k != "made"} == {k: v for k, v in doc.items() if k != "made"}:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return True
