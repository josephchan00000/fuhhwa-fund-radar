"""第二層篩選：交叉比對各策略的條件，提高一年內翻倍的命中率（tw-superstock-lab/reports/W3_plan.md v1；
2026-10-16 使用者：「是要如何把選股的命中率提高」「這麼多策略是不是可以交叉比對」）。

條件與 7 族分數的定義只寫在這裡；研究（tw-superstock-lab src/superstock/layer.py）與每日頁面共用。
第一層門檻與過去成績讀 data/lab/layer_research.json（研究定案後匯出）。只列名單與過去統計，不是買賣訊號。"""
from __future__ import annotations

from . import store

RES_FILE = "layer_research.json"

# (鍵, 名稱)：W3_plan 第 2.1 節，順序固定、之後不加。A、B 規則用過 2020–2022，只列不選。
COND = [
    ("arule", "飆股候選（A 規則）"),
    ("brule", "一年翻倍規則（B 規則）"),
    ("rnha", "月營收創歷史新高"),
    ("sur20", "營收驚喜前 20%"),
    ("ry25", "近 3 月營收年增 ≥ 25%"),
    ("racc", "營收年增加速"),
    ("sue20", "財報驚喜前 20%"),
    ("ey25", "最新季 EPS 年增 ≥ 25%"),
    ("eacc", "EPS 年增加速"),
    ("c33", "Code 33"),
    ("gmd", "毛利率比去年同季高"),
    ("roe15", "近四季 ROE ≥ 15%"),
    ("rs90", "RS ≥ 90"),
    ("rsl", "RS 線創 52 週新高"),
    ("mom10", "相對強勢前 10%"),
    ("vcp", "標準 VCP"),
    ("tight", "緊密整理"),
    ("pp", "爆發型"),
    ("base12", "第 1、2 個基底"),
    ("ma200up", "200 日線上揚 ≥ 80 日"),
    ("ud12", "量價足跡 ≥ 1.2"),
    ("h10", "距 52 週高點 ≤ 10%"),
    ("dry", "量縮 ≤ 0.7"),
    ("ind2", "同產業 ≥ 2 檔在名單"),
    ("cap_s", "市值 40～100 億"),
    ("cap_m", "市值 100～300 億"),
    ("cap_l", "市值 ≥ 300 億"),
    ("vm20", "價值＋動能前 20%"),
]
CKEYS = [k for k, _ in COND]
CNAME = dict(COND)
LIST_ONLY = ("arule", "brule")
TOP = {"sur20": 0.20, "sue20": 0.20, "mom10": 0.10, "vm20": 0.20}     # 橫斷面前幾 %（同當週合格股票比）
TIGHT = (10, 0.08)                                                     # 緊密整理固定 10 日、8%（W3_plan 2.1）

# 7 族分數（W3_plan 3.1）：每族一個事前寫定的代表條件，符合 1 分、權重相同
FAMILY = [
    ("月營收", "月營收創歷史新高或營收驚喜前 20%", lambda c: c["rnha"] or c["sur20"]),
    ("獲利", "財報驚喜前 20%，或 EPS 年增 ≥ 25% 且加速", lambda c: c["sue20"] or (c["ey25"] and c["eacc"])),
    ("價格強度", "RS ≥ 90 或 RS 線創新高", lambda c: c["rs90"] or c["rsl"]),
    ("技術線型", "標準 VCP、緊密整理或爆發型", lambda c: c["vcp"] or c["tight"] or c["pp"]),
    ("階段", "第 1、2 個基底且 200 日線上揚 ≥ 80 日", lambda c: c["base12"] and c["ma200up"]),
    ("量價", "量價足跡 ≥ 1.2", lambda c: c["ud12"]),
    ("族群", "同產業 ≥ 2 檔在名單", lambda c: c["ind2"]),
]
FNAMES = [n for n, _, _ in FAMILY]


def families(cond: dict) -> list[bool]:
    return [bool(f(cond)) for _, _, f in FAMILY]


def score(cond: dict) -> int:
    return sum(families(cond))


def cap_bucket(cap) -> dict:
    """月底市值（元）→ 三個規模條件。"""
    return {"cap_s": cap is not None and 40e8 <= cap < 100e8, "cap_m": cap is not None and 100e8 <= cap < 300e8,
            "cap_l": cap is not None and cap >= 300e8}


def top_set(vals: dict, frac: float) -> set:
    """{代號: 分數} → 分數最高的 ceil(frac × 檔數) 檔（同分依代號）；同 bt3s.pick。"""
    import math
    xs = [(v, c) for c, v in vals.items() if v is not None]
    if not xs:
        return set()
    n = max(1, math.ceil(frac * len(xs)))
    return {c for _, c in sorted(xs, key=lambda x: (-x[0], x[1]))[:n]}


def load_res() -> dict | None:
    res = store.read_json(RES_FILE, None)
    return res if res and res.get("v") == 1 else None


def _ffill(xs: list) -> list:
    out, last = [], None
    for x in xs:
        last = x if x else last
        out.append(last)
    return out


def today(cal: list[str], i: int, P, pxs: dict, F: dict, hits: dict, watch: dict, idx: list,
          brules: list | None = None) -> dict:
    """今天合併名單（watch）上每檔：28 個條件、7 族分數（同研究的定義；橫斷面排名用今天的合格股票）。
    價格用 Px 的日線（只還原配股減資），RS 線用加權指數（研究用含息價與加權報酬指數）。"""
    import bisect
    from . import bt3d
    from . import packtest as PT
    from . import sepa as SP
    from . import vcp as VC
    from .. import stockmeta
    eps, rev, ind = bt3d.load_eps(), PT.load_rev(), stockmeta.industry_map()
    el = sorted(c for c, f in F.items() if f.get("el") and c in pxs)
    rf = PT.rev_forms(cal)
    k = bisect.bisect_right([t for t, _ in rf], i) - 1
    ym = rf[k][1] if k >= 0 else None
    qf = sorted((t, q) for q in {q for e in eps.values() for q in e}
                if (t := PT.form_after_deadline(cal, PT.deadline(q))) is not None)
    k = bisect.bisect_right([t for t, _ in qf], i) - 1
    q = qf[k][1] if k >= 0 else None
    sur, sue, mom, ep = {}, {}, {}, {}
    for c in el:
        cc = pxs[c].c
        if ym and "金融" not in (ind.get(c) or ""):
            sur[c] = PT.sur(rev.get(c) or {}, ym)
        if q and c in eps:
            sue[c] = PT.sue(eps[c], q)
        if i >= 126 and cc[i - 126] and cc[i - 21]:
            mom[c] = cc[i - 21] / cc[i - 126] - 1
        if c in eps and c in mom:
            e, px = PT.ttm_eps(eps[c], cal[i]), P.s[c]["c"][i]
            if e is not None and px and e / px <= 0.25:
                ep[c] = e / px

    def pr(d):
        return {c: (n + 1) / len(d) for n, c in enumerate(sorted(d, key=lambda c: (d[c], c)))}

    ra, rb = pr(ep), pr({c: mom[c] for c in ep})
    tops = {"sur20": top_set(sur, TOP["sur20"]), "sue20": top_set(sue, TOP["sue20"]), "mom10": top_set(mom, TOP["mom10"]),
            "vm20": top_set({c: (ra[c] + rb[c]) / 2 for c in ra}, TOP["vm20"])}
    cnt: dict = {}
    for c in watch:
        g = ind.get(c)
        if g:
            cnt[g] = cnt.get(g, 0) + 1
    ix = _ffill(idx)
    out = {}
    for c in sorted(watch):
        px, f = pxs.get(c), F.get(c) or {}
        if px is None:
            continue
        h, l, cc, v = px.h, px.l, px.c, px.v
        hs = [x for x in h[max(0, i - 251):i + 1] if x is not None]
        hi52 = max(hs) if len(hs) >= 200 else None
        ma, prev, up = SP.ma200_info(cc)
        bno = SP.base_counts(cc, ma, prev)[i]
        v50 = [None] * len(v)
        for t in range(max(0, i - 80), i + 1):
            v50[t] = SP.mean_last(v, t, 50, 40)
        dry = f.get("vdry")
        vc = VC.check(h, l, cc, v, i)
        rsl, _ = SP.rsl_at(cc, ix, i)
        ud = SP.ud_at(P.s[c]["c"], v, i)
        cond = {
            "arule": c in (hits or {}), "brule": any(p(f) for p in (brules or [])),
            "rnha": f.get("rnha") is True, "sur20": c in tops["sur20"],
            "ry25": f.get("ry3") is not None and f["ry3"] >= 0.25, "racc": f.get("racc") is not None and f["racc"] > 0,
            "sue20": c in tops["sue20"], "ey25": f.get("ey") is not None and f["ey"] >= 0.25,
            "eacc": f.get("eacc") is not None and f["eacc"] > 0, "c33": f.get("c33") is True,
            "gmd": f.get("gmd") is not None and f["gmd"] > 0, "roe15": f.get("roe") is not None and f["roe"] >= 0.15,
            "rs90": (f.get("rs") or 0) >= SP.RS_HI, "rsl": rsl, "mom10": c in tops["mom10"],
            "vcp": bool(vc and vc.get("ok")),
            "tight": SP.tight_at(h, l, cc, hi52, i, *TIGHT) is not None,
            "pp": SP.pp_at(h, l, cc, v, v50, P.s[c]["c"][i], dry, i) is not None,
            "base12": bno in (1, 2), "ma200up": up[i] >= SP.MA200_UP, "ud12": ud is not None and ud >= SP.UD_MIN,
            "h10": bool(hi52 and cc[i] and cc[i] / hi52 - 1 >= -0.10), "dry": dry is not None and dry <= SP.DRY,
            "ind2": cnt.get(ind.get(c), 0) >= 2, **cap_bucket(f.get("cap")), "vm20": c in tops["vm20"],
        }
        fam = families(cond)
        out[c] = {"x": [bool(cond[k]) for k in CKEYS], "fam": fam, "s": sum(fam), "base": bno}
    return out


def market_now(idx: list, i: int, cal: list[str]) -> dict:
    """今天的大盤狀態（W4 的 M2）：加權指數 50 日線 > 200 日線。idx＝加權指數（價格），None 前值補齊。"""
    ix = _ffill(idx)
    w50, w200 = [x for x in ix[max(0, i - 49):i + 1] if x], [x for x in ix[max(0, i - 199):i + 1] if x]
    if len(w50) < 50 or len(w200) < 200:
        return {}
    m50, m200 = sum(w50) / 50, sum(w200) / 200
    return {"d": cal[i], "m2": m50 > m200, "ma50": round(m50, 1), "ma200": round(m200, 1), "idx": ix[i]}


def page_data(res: dict | None, lay: dict | None) -> dict:
    """頁面用：今天名單上每檔的分數、7 族、28 條件（位元）、書上的買點與停損＋今天的大盤狀態＋研究摘要
    （價格強度子名單、大盤時機、交叉比對的判定、逐年表、照書 VCP 的查核 w5）。"""
    lay = lay or {}
    st = {}
    for c, r in (lay.get("st") or {}).items():
        st[c] = {"s": r["s"], "f": sum(1 << k for k, b in enumerate(r["fam"]) if b),
                 "x": sum(1 << k for k, b in enumerate(r["x"]) if b), "b": r.get("base"), "p": r.get("plan")}
    out = {"fam": [[n, d] for n, d, _ in FAMILY], "ck": [[k, n] for k, n in COND], "stocks": st,
           "mnow": lay.get("mnow") or {}}
    if res:
        sp = {k: {"desc": v.get("desc"), "lift": (v.get("judge") or {}).get("lift"), "pass": (v.get("judge") or {}).get("pass")}
              for k, v in (res.get("specs") or {}).items()}
        out.update({"asof": res.get("asof"), "use": res.get("use"), "specs": sp, "ps": res.get("ps"),
                    "mkt": res.get("mkt"), "years": res.get("years"), "w5": res.get("w5")})
    return out
