"""籌碼雷達：高股息換股的「被動買盤大小」——權重研究、事前估計、策略測試、被動買賣提醒。

2026-10-14 使用者：「你要幫我去延伸更多可能的交易策略，包含我剛剛說到的權重問題，高股息的權重就有可能會大幅拉高吧」。

量法（實際被動買賣，`realized()`）：官方投信買賣超（證交所 T86／櫃買三大法人）在被動買賣期間（`hdstudy.anchors`）
逐日加總、扣掉「平常水準」（買盤開始前第 25～6 個交易日的中位數）＝股數；× 期間均價＝金額；÷ 買盤前 20 日
平均成交金額＝「幾天的量」。投信買賣超是全體投信合計——同期別檔 ETF、一般基金的進出也在裡面，是近似值；
台積電這種每天投信進出就上百億的權值股完全被雜訊蓋過（量不出來，估計值改用單檔上限封頂）。

事前估計（`est_amt()`）：三種權重模型對照實際（2026-10-14，135 檔納入股）——
  A「市值 × f_k」（f_k＝同指數其他次審核「買進金額占市值」的中位數）誤差中位約 ±45%、無偏；
  B「規模 × 股利金額占比（市值×殖利率）」約 ±70%；C「規模 × 殖利率占比」（舊估法）高估約 1.7 倍。
  → 用 A，並以「單檔權重上限 × ETF 規模」封頂（台積電、聯發科這類權值股）。同一次審核內買進金額和市值的
  等級相關約 0.8～0.9：權重主要跟著市值走，殖利率高不會讓權重遠超過市值比例；真正「大幅拉高」的是
  **相對成交量**——ETF 規模大，冷門中型股（週轉率低）一次就是 10～30 天的量。

策略測試（`study()`，數字由頁面每次重算）：照事前估計「名單公開後買大買盤股、最後一天賣」，每次審核賺賠各半；
穩定的是「結束後」：估計 ≥5 日量的納入股，被動買盤結束後 10 個交易日多半輸大盤、也輸其他成分股（買盤小的不會）；
刪除股被賣完也沒有反彈 → 做成「被動買賣提醒」（`alerts()`）：已持有的在被動買盤最後一天收盤前出、沒持有的
結束後 10 個交易日內不追；刪除股賣完別急著撿。只做提醒，不做放空。
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from . import hdstudy as HS
from . import tw50study as TS

KEYS = HS.HD_KEYS
COST = TS.COST
BIG = 5.0              # 估計被動買賣 ≥ 5 日量 → 提醒
AFTER = 10             # 被動買賣結束後避開幾個交易日
BASE = (25, 5)         # 平常水準：買盤開始前第 25～6 個交易日的投信買賣超中位數
CAPW = {"tip_hd": 0.15, "tip_tech": 0.10, "tw_div": 0.10, "msci_esg30": 0.10}   # 單檔權重上限（封頂用）
ETF = {"tw_div": "0056", "msci_esg30": "00878", "tip_hd": "00919", "tip_tech": "00929"}
ALERT = {"key": "hd", "ver": 1, "since": "2026-10-14", "name": "高股息換股", "kind": "事件型・出場規則（每年約 8 次換股）",
         "basis": "0056、00878、00919、00929 換股時，被動 ETF 在數天內集中買進新成分股；規模大的 ETF 對成交量小的中型股，"
                  "一次常要買進 10 天以上的成交量。被動買盤結束後，這類股票多半回落；名單公開後才追買則沒有優勢。",
         "rule": [f"對象：四檔高股息 ETF 換股的納入股與刪除股，估計被動買賣 ≥ {BIG:g} 天成交量",
                  "估計：納入股＝市值 × 該 ETF 過去各次「實際買進占市值」的中位數（以單檔權重上限 × 規模封頂）；"
                  "刪除股＝ETF 目前實際持股 × 收盤；再除以 20 日平均成交金額",
                  "已持有：納入股在被動買盤最後一天收盤前賣出（日期依各 ETF 慣例，與過去官方投信買賣超推得的期間多數一致）",
                  f"未持有：納入股在被動買盤結束後 {AFTER} 個交易日內不買進",
                  f"刪除股：被動賣盤結束後 {AFTER} 個交易日內不買進",
                  "驗證：自 2026-10-14 起記錄，滿 2 次換股後檢視提醒股是否多半輸大盤"],
         "risk": ["每檔 ETF 一年只換 2～4 次，樣本少",
                  "被動買賣金額為估計值，誤差約 ±45%；實際名單以官方公告為準",
                  "0056、00878 名單公告前無法預估，公告後才列入"],
         "tried": ["名單公開後追買、被動買盤結束後、刪除股賣完後、回落後再撿等 9 種做法",
                   "依編製規則提前卡位：截止前 0／5／10／20 日 × 買盤門檻 0／3／5／10 日量 × 兩種出場"]}
ROOT = Path(__file__).resolve().parents[2]


def _tr(D, c: str, i: int) -> float:
    return HS._trust(D, c, D.cal[i]) or 0


def _flow(D, H, c: str, T0: int, T1: int) -> tuple[float, float | None] | None:
    """(被動買賣金額（元，賣為負）, 占 20 日均成交金額的天數)。"""
    base = [_tr(D, c, i) for i in range(max(T0 - BASE[0], 0), max(T0 - BASE[1], 0))]
    b = statistics.median(base) if base else 0
    sh = sum(_tr(D, c, i) - b for i in range(T0, T1 + 1))
    s = H.ser(c)
    pxs = [s["raw"][i] for i in range(T0, T1 + 1) if s["raw"][i]]
    if not pxs:
        return None
    val = sh * statistics.mean(pxs)
    adv = H.adv(c, T0 - 1, 20)
    return val, (val / adv if adv else None)


def _gx(P, c: str, i0: int, o0: bool, i1: int, o1: bool) -> tuple[float | None, float | None]:
    """(報酬, 對大盤超額)，**不扣成本**、%。"""
    if i0 is None or i1 is None or i0 < 0 or i1 >= P.D.T or i1 < i0 or (i1 == i0 and o0 == o1):
        return None, None
    r, x = P.ret(c, i0, o0, i1, o1)
    if r is None:
        return None, None
    return (r + COST) * 100, (None if x is None else (x + COST) * 100)


def est_amt(f: float | None, mc: float | None, cap_amt: float | None = None) -> float | None:
    """估計被動買進（億）＝f × 市值（億），以單檔上限 × 規模封頂。"""
    if not f or not mc:
        return None
    a = f * mc
    return min(a, cap_amt) if cap_amt else a


def est_days(H, c: str, d: str, i: int, f: float | None, cap_amt: float | None = None) -> tuple[float | None, float | None]:
    """(估計被動買進（億）, 約幾天成交量)。"""
    amt = est_amt(f, HS._cap(H, c, d), cap_amt)
    adv = H.adv(c, i, 20) if i is not None else None
    if amt is None:
        return None, None
    return round(amt, 1), (round(amt * 1e8 / adv, 1) if adv else None)


def realized(D, H, cfg: dict, P=None) -> list[dict]:
    """歷次審核每檔（納入／刪除／留任）實際被動買賣＋前後漲跌。只用投信買賣超推得出被動買賣期間（t86）的審核。
    欄位：in＝買賣開始前一天收盤 → 最後一天收盤；p5／p10＝最後一天收盤 → 5／10 日後；reb＝結束後第 10 → 30 日；
    皆為對大盤超額、不扣成本（%）；加 c 尾碼＝對留任成分股（等權）。ride＝名單公開後開盤買 → 最後一天收盤（扣成本、對大盤）。"""
    P = P or HS._px(D, H)
    out = []
    for k in KEYS:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        cons = HS.constituents(ix)
        for h in sorted(ix.get("history") or [], key=lambda x: x.get("effective") or ""):
            a = HS.anchors(D, h, k)
            if not a or not a["t86"]:
                continue
            A, T0, T1 = a["A"], a["T0"], a["T1"]
            if T0 - BASE[0] < 0:
                continue
            ba = cons.get(h.get("review"))
            codes = {c: "stay" for c in ((ba[0] & ba[1]) if ba else set())}
            codes.update({c: "add" for c in h.get("adds") or []})
            codes.update({c: "del" for c in h.get("dels") or []})
            wins = {"in": (T0 - 1, False, T1, False), "p5": (T1, False, T1 + 5, False),
                    "p10": (T1, False, T1 + 10, False), "reb": (T1 + 10, False, T1 + 30, False)}
            stays = [c for c, s in codes.items() if s == "stay" and len(c) == 4 and c.isdigit()]
            ctrl = {}
            for w, (i0, o0, i1, o1) in wins.items():
                xs = [r for r in (_gx(P, c, i0, o0, i1, o1)[0] for c in stays) if r is not None]
                ctrl[w] = statistics.mean(xs) if len(xs) >= 5 else None
            dA = D.cal[A]
            aum = h.get("aum") or HS.aum_at(ix, dA)
            for c, side in codes.items():
                if len(c) != 4 or not c.isdigit():
                    continue
                fl = _flow(D, H, c, T0, T1)
                if not fl:
                    continue
                mc = HS._cap(H, c, D.cal[T0 - 1])
                row = {"k": k, "rev": h.get("review"), "c": c, "n": D.names.get(c, c), "side": side,
                       "val": round(fl[0] / 1e8, 1), "days": None if fl[1] is None else round(fl[1], 2),
                       "mc": None if not mc else round(mc, 0), "fm": round(fl[0] / 1e8 / mc * 100, 2) if mc else None,
                       "mcA": HS._cap(H, c, dA), "advA": H.adv(c, A, 20), "capA": (CAPW.get(k, 0.1) * aum) if aum else None,
                       "A": dA, "t0": D.cal[T0], "t1": D.cal[T1]}
                for w, (i0, o0, i1, o1) in wins.items():
                    r, x = _gx(P, c, i0, o0, i1, o1)
                    row[w] = None if x is None else round(x, 2)
                    row[w + "c"] = round(r - ctrl[w], 2) if (r is not None and ctrl.get(w) is not None) else None
                rr, rx = P.ret(c, A + 1, True, T1, False) if A + 1 <= T1 < D.T else (None, None)
                row["ride"] = None if rx is None else round(rx * 100, 2)
                row["ride_r"] = None if rr is None else round(rr * 100, 2)
                g = _gx(P, c, A + 1, True, T1, False)[1]          # 名單公開後 → 最後一天（不扣成本；刪除股＝先賣掉避開的部分）
                row["ann"] = None if g is None else round(g, 2)
                out.append(row)
    return out


def fk(rows: list[dict]) -> dict:
    """{指數: {"f": 買進金額占市值中位數（小數）, "per": {審核: 中位數%}}}；只用有 2 檔以上納入、買進為正的審核。"""
    per: dict = {}
    for r in rows:
        if r["side"] == "add" and r["val"] > 0 and r.get("fm") is not None:
            per.setdefault(r["k"], {}).setdefault(r["rev"], []).append(r["fm"])
    out = {}
    for k, by in per.items():
        meds = {rev: statistics.median(v) for rev, v in by.items() if len(v) >= 2}
        if meds:
            out[k] = {"f": statistics.median(meds.values()) / 100, "per": {kk: round(v, 2) for kk, v in sorted(meds.items())}}
    return out


def _f_loo(F: dict, k: str, rev: str) -> float | None:
    """事前可用的 f：同指數「其他次」審核的中位數（不用到當次自己）。"""
    x = F.get(k) or {}
    xs = [v for r, v in (x.get("per") or {}).items() if r != rev]
    return statistics.median(xs) / 100 if xs else x.get("f")


def _with_est(rows: list[dict], F: dict) -> None:
    """事前估計天數（納入股＝買、刪除股＝賣，皆以正數表示大小；刪除股歷史沒有當時持股 → 同樣用市值 × f 近似）。"""
    for r in rows:
        if r["side"] == "stay":
            continue
        amt = est_amt(_f_loo(F, r["k"], r["rev"]), r.get("mcA"), r.get("capA"))
        r["est"] = round(amt * 1e8 / r["advA"], 2) if (amt and r.get("advA")) else None


def _st(xs: list) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0}
    return {"n": len(xs), "avg": round(statistics.mean(xs), 2), "med": round(statistics.median(xs), 2),
            "pos": sum(1 for x in xs if x > 0)}


def _per_rev(rows: list[dict], sel, field: str) -> dict:
    """每次審核等權（同一次各檔平均）→ 跨審核統計；另附逐筆統計與逐次明細。"""
    by: dict = {}
    for r in rows:
        if sel(r) and r.get(field) is not None:
            by.setdefault((r["k"], r["rev"]), []).append(r[field])
    per = {kk: statistics.mean(v) for kk, v in by.items()}
    return {"rev": _st(list(per.values())), "tr": _st([x for v in by.values() for x in v]),
            "by": [[ETF[k], rev, round(v, 2), len(by[(k, rev)])] for (k, rev), v in sorted(per.items())]}


def _units(rows: list[dict], sel, rf: str, xf: str) -> list[dict]:
    """事件型評級用：每次審核一個單位（同一次各檔等額平均）{etf, review, d, r, x, n}。"""
    by: dict = {}
    for r in rows:
        if sel(r) and r.get(rf) is not None:
            by.setdefault((r["k"], r["rev"]), []).append(r)
    out = []
    for (k, rev), rs in sorted(by.items()):
        xs = [x[xf] for x in rs if x.get(xf) is not None]
        out.append({"etf": ETF[k], "review": rev, "d": rs[0]["A"], "n": len(rs),
                    "r": round(statistics.mean(x[rf] for x in rs), 2),
                    "x": round(statistics.mean(xs), 2) if xs else None})
    return out


def _big(r) -> bool:
    return (r.get("est") or 0) >= BIG


# 頁面「策略測試」表：kind＝long（買進，扣成本）／avoid（避開或觀察：不扣成本，負＝這段在跌）
TESTS = [
    ("ride_all", "long", "名單公開後開盤買全部納入股 → 被動買盤最後一天收盤賣", lambda r: r["side"] == "add", "ride"),
    ("ride5", "long", f"同上，只買估計被動買盤 ≥{BIG:g} 日量的", lambda r: r["side"] == "add" and _big(r), "ride"),
    ("ride10", "long", "同上，只買估計 ≥10 日量的", lambda r: r["side"] == "add" and (r.get("est") or 0) >= 10, "ride"),
    ("top3", "long", "同上，每次只買估計買盤最大的 3 檔", None, "ride"),
    ("post_big", "avoid", f"估計 ≥{BIG:g} 日量的納入股：被動買盤結束後 {AFTER} 日（對大盤）",
     lambda r: r["side"] == "add" and _big(r), "p10"),
    ("post_bigc", "avoid", "同上，對其他成分股（扣掉高股息類股本身的漲跌）", lambda r: r["side"] == "add" and _big(r), "p10c"),
    ("post_smallc", "avoid", f"對照：估計 <{BIG:g} 日量的納入股，結束後 {AFTER} 日（對其他成分股）",
     lambda r: r["side"] == "add" and r.get("est") is not None and not _big(r), "p10c"),
    ("reb", "long", f"納入股回落後再撿：買盤結束後第 {AFTER} → 30 日（對大盤）", lambda r: r["side"] == "add", "reb"),
    ("del_ann", "avoid", f"估計被動賣壓 ≥{BIG:g} 日量的刪除股：名單公開後 → 被動賣完（對大盤；負＝公告後先賣掉能避開）",
     lambda r: r["side"] == "del" and _big(r), "ann"),
    ("del10", "long", f"刪除股賣完撿便宜：被動賣盤結束後 {AFTER} 日（對大盤）", lambda r: r["side"] == "del", "p10"),
]


def study(rows: list[dict], F: dict, reps: list[dict] | None = None, D=None, H=None, cfg: dict | None = None) -> dict:
    """頁面研究段：實際被動買賣天數分組、事前估計準度、策略測試（每次審核等權）、例子。"""
    _with_est(rows, F)
    adds = [r for r in rows if r["side"] == "add"]
    pr = [(r["est"], r["days"]) for r in adds if r.get("est") is not None and r.get("days") is not None]
    rho, n = TS._spearman([a for a, _ in pr], [b for _, b in pr])
    ebk = []
    for lo, hi in ((0, 2), (2, 5), (5, 10), (10, None)):
        xs = [b for a, b in pr if a >= lo and (hi is None or a < hi)]
        if xs:
            ebk.append([lo, hi, len(xs), round(statistics.median(xs), 1)])

    def bk(side, edges):
        out = []
        for lo, hi in edges:
            rs = [r for r in rows if r["side"] == side and r.get("days") is not None
                  and (lo is None or r["days"] >= lo) and (hi is None or r["days"] < hi)]
            if len(rs) >= 3:
                out.append([side, lo, hi, len(rs), _st([r["in"] for r in rs]), _st([r["p5"] for r in rs]),
                            _st([r["p10"] for r in rs]), _st([r["p10c"] for r in rs])])
        return out
    by: dict = {}
    for r in adds:
        if r.get("est") is not None:
            by.setdefault((r["k"], r["rev"]), []).append(r)
    top3 = {id(r) for v in by.values() for r in sorted(v, key=lambda r: -r["est"])[:3]}
    tests = [{"k": key, "kind": kind, "lbl": lbl, **_per_rev(rows, sel or (lambda r: id(r) in top3), field)}
             for key, kind, lbl, sel, field in TESTS]
    if reps and D is not None and H is not None and cfg:
        tests.append(_pred_del_test(D, H, cfg, reps))
    ex = sorted([r for r in adds if r.get("days") is not None and r.get("in") is not None], key=lambda r: -r["days"])[:8]
    return {"f": {k: [round(v["f"] * 100, 2), len(v["per"])] for k, v in F.items()},
            "acc": {"rho": rho, "n": n, "bk": ebk},
            "bk": bk("add", ((None, 2), (2, 5), (5, 10), (10, None))) +
                  bk("stay", ((None, -5), (-5, -2), (-2, 2), (2, 5), (5, None))) +
                  bk("del", ((None, -5), (-5, -2), (-2, None))),
            "tests": tests, "big": BIG, "after": AFTER,
            "units": {"ride5": _units(rows, lambda r: r["side"] == "add" and _big(r), "ride_r", "ride")},
            "ex": [[r["c"], r["n"], ETF[r["k"]], r["rev"], r["days"], r["val"], r["fm"], r["in"], r["p10"]] for r in ex],
            "n_rev": len({(r["k"], r["rev"]) for r in rows}), "n_add": len(adds)}


def _pred_del_test(D, H, cfg: dict, reps: list[dict]) -> dict:
    """00919／00929 預估刪除股（資料截止日重算）：截止日隔天開盤 → 公告日收盤，對大盤（不扣成本）。"""
    P = HS._px(D, H)
    rows = []
    for r in reps:
        x = (r.get("lead") or {}).get(0)
        if not x or r["key"] not in ("tip_hd", "tip_tech"):
            continue
        h = next((h for h in cfg["indexes"][r["key"]]["history"] if h.get("review") == r["review"]), None)
        a = HS.anchors(D, h, r["key"]) if h else None
        if not a or a["C"] is None:
            continue
        for c in x["pred_del"]:
            rows.append({"k": r["key"], "rev": r["review"], "v": _gx(P, c, a["C"] + 1, True, a["A"], False)[1]})
    return {"k": "pred_del", "kind": "avoid", "lbl": "00919／00929 預估刪除股先避開：資料截止日隔天 → 公告日（對大盤）",
            **_per_rev(rows, lambda r: True, "v")}


# —— 下一次／進行中的審核：估計被動買賣＋提醒

def _holdings(etf: str) -> dict[str, float]:
    try:
        d = json.loads((ROOT / "data" / "etf_holdings.json").read_text(encoding="utf-8"))
        hs = (d.get("etfs") or {}).get(etf, {}).get("holdings") or []
        return {h["stock_id"]: float(h.get("shares") or 0) for h in hs if h.get("stock_id")}
    except Exception:                                     # noqa: BLE001
        return {}


def del_est(D, H, etf: str, c: str, d: str, i: int | None) -> tuple[float | None, float | None]:
    """刪除股的被動賣出（億）＝ETF 目前實際持股 × 收盤；÷ 20 日均成交金額＝幾天的量。"""
    sh = _holdings(etf).get(c)
    p = H.ser(c)["raw"][i] if i is not None else None
    adv = H.adv(c, i, 20) if i is not None else None
    if not sh or not p:
        return None, None
    amt = sh * p / 1e8
    return round(amt, 1), (round(amt * 1e8 / adv, 1) if adv else None)


def _phase(last: str, t0: str | None, t1: str | None) -> tuple[str, str | None]:
    """('pre'|'in'|'after'|'done', 避開到哪天)。"""
    if not t0 or not t1:
        return "pre", None
    until = TS.td_shift(t1, AFTER)
    if last < t0:
        return "pre", until
    if last <= t1:
        return "in", until
    if last <= until:
        return "after", until
    return "done", until


def alerts(D, H, cfg: dict, F: dict, live: dict | None = None) -> dict:
    """進行中／即將到來的高股息換股：各股估計被動買賣（≥BIG 日量＝提醒）與階段。
    官方名單（history）優先；00919／00929 下一次另列預估名單（標「預估」）。
    rows＝[代號, 名稱, ETF, 審核, add/del, 估計金額(億), 約幾日量, 買賣首日, 最後一天, 避開到, 階段, 官方/預估]。"""
    last = D.cal[-1]
    P = HS._px(D, H)
    out, fwd = [], []
    for k in KEYS:
        ix = (cfg.get("indexes") or {}).get(k) or {}
        etf = (ix.get("etfs") or [None])[0]
        f = (F.get(k) or {}).get("f")
        aum = HS._cur_aum(etf)[1] if etf else None
        cap_amt = CAPW.get(k, 0.1) * aum if aum else None
        hist = sorted(ix.get("history") or [], key=lambda x: x.get("effective") or "")
        for h in hist[-2:]:                                # 最近兩次：還在提醒期內的才列
            if not h.get("adds") and not h.get("dels"):
                continue
            t0, t1 = HS._conv_window(D, k, h)
            a = HS.anchors(D, h, k)
            if a and t1 and t1 <= last:                    # 已結束：用官方投信買賣超推得的期間
                t0, t1 = D.cal[a["T0"]], D.cal[a["T1"]]
            ph, until = _phase(last, t0, t1)
            ann = h.get("reveal") or h.get("announce")
            dA = min(ann, last) if ann else last
            iA = TS._on_or_before(D, dA)
            for side, codes in (("add", h.get("adds") or []), ("del", h.get("dels") or [])):
                for c in codes:
                    if len(c) != 4 or not c.isdigit():
                        continue
                    amt, days = (est_days(H, c, dA, iA, f, cap_amt) if side == "add"
                                 else del_est(D, H, etf, c, dA, iA) if ph in ("pre", "in") else (None, None))
                    if ph != "done":
                        out.append([c, D.names.get(c, c), ETF[k], h.get("review"), side, amt, days, t0, t1, until, ph, "官方"])
                    if (side == "add" and ann and ann >= ALERT["since"] and days is not None and days >= BIG
                            and a and a["t86"] and a["T1"] < D.T):
                        fwd.append({"c": c, "n": D.names.get(c, c), "etf": ETF[k], "review": h.get("review"),
                                    "days": days, "t1": D.cal[a["T1"]],
                                    "x5": _gx(P, c, a["T1"], False, a["T1"] + 5, False)[1],
                                    "x10": _gx(P, c, a["T1"], False, a["T1"] + 10, False)[1]})
        lv = (live or {}).get(k) or {}
        if lv.get("err") or lv.get("review") in {h.get("review") for h in hist}:
            continue
        t0, t1 = lv.get("trade") or (None, None)
        ph, until = _phase(last, t0, t1)
        for side in ("add", "del"):
            for r in lv.get(side + "s") or []:
                out.append([r[0], r[1], ETF[k], lv.get("review"), side, r[5], r[6], t0, t1, until, ph, "預估"])
    fx = [x["x10"] for x in fwd if x.get("x10") is not None]
    return {"rows": out, "big": sum(1 for r in out if r[6] is not None and r[6] >= BIG), "fwd": fwd,
            "since": ALERT["since"], "rule": ALERT["rule"], "name": ALERT["name"], "kind": ALERT["kind"],
            "basis": ALERT["basis"], "risk": ALERT["risk"], "big_th": BIG, "after": AFTER,
            "fwd_stats": {"n": len(fx), "rev": len({(x["etf"], x["review"]) for x in fwd if x.get("x10") is not None}),
                          "avg": round(statistics.mean(fx), 2) if fx else None, "neg": sum(1 for x in fx if x < 0)}}


def run(D, H, cfg: dict, live: dict | None = None, reps: list[dict] | None = None) -> dict:
    rows = realized(D, H, cfg)
    F = fk(rows)
    return {"study": study(rows, F, reps, D, H, cfg), "alert": alerts(D, H, cfg, F, live), "F": F}


if __name__ == "__main__":                  # 研究用：python3 -m arm.lab.hdflow
    from . import analyze
    from .hdmodel import HD
    D = analyze.Data()
    H = HD(D)
    cfg = json.loads((ROOT / "config" / "index_reviews.json").read_text(encoding="utf-8"))
    out = run(D, H, cfg)
    S = out["study"]
    print("f_k：", S["f"], "估計準度：", S["acc"])
    for t in S["tests"]:
        print(f"{t['k']:12s} {t['lbl']}\n   每次：{t['rev']}  逐筆：{t['tr']}")
    for b in S["bk"]:
        print(b[:4], "期間", b[4], "後10", b[6])
