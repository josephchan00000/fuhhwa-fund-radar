"""新策略候選（規格 arm/lab/candspec.py；docs/lab_ia_v5_plan.md 第 24 節）。

  load_spec()、check_spec()   規格檔（config/strategy_candidates.json）與程式（arm/lab/cands/{編號}.py）的格式與 sha
  merge_check(old, new, …)    合併通道（strategy_cands.yml）：舊的一字不差、沒有刪、新的最多 MAX_NEW 條、還沒決定的最多 MAX_OPEN 條
  evaluate(it, ctx)           一條候選：回測、判定、用到未來資料的檢查、放進計畫試算、現在
  compute()、forward()        算還沒有結果的候選（→ data/lab/cands_research.json）；試用中的補每週紀錄（→ cands_live.json，只增不改）
回測只在 CI 跑（scripts/run_cands.py；.github/workflows/strategy_cands.yml）。tests/test_cands.py 和直接算的版本比對。
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import itertools
import json
import math
import re
from datetime import date
from pathlib import Path

import numpy as np

from . import candspec as CS

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / CS.SPEC_FILE
PROG = ROOT / CS.PROG_DIR
RES = ROOT / "data" / "lab" / CS.RES_FILE
LIVE = ROOT / "data" / "lab" / CS.LIVE_FILE
BOARD = ROOT / "config" / "strategy_board.json"
SIGSTK = ROOT / "data" / "lab" / "sig_stock.json"
BANNED = ("保證", "穩賺", "必賺", "包賺", "必漲", "必跌", "一定會", "唯一", "建議買賣", "建議買", "建議賣", "目標價",
          "零風險", "無風險", "穩賺不賠")


def _r(v, k: int = 4):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, k) if math.isfinite(f) else None


# ── 規格 ─────────────────────────────────────────────────────────────────────

def load_spec(path: Path | None = None) -> dict:
    try:
        doc = json.loads((path or SPEC).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": []}
    if not isinstance(doc, dict):
        return {"items": []}
    doc.setdefault("items", [])
    return doc


def dumps(x) -> str:
    """比對用（同一筆規格一字不差＝這個字串相同）。"""
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(it: dict) -> str:
    return hashlib.sha256(dumps(it).encode("utf-8")).hexdigest()[:16]


def sha_file(p: Path) -> str | None:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return None


def combos(grid: dict) -> list[dict]:
    ks = sorted(grid)
    return [dict(zip(ks, v)) for v in itertools.product(*(grid[k] for k in ks))]


def _tw_grid(it: dict) -> tuple[str, list, list[tuple]]:
    """台股個股的參數鄰近：一個規則參數 × pick 的幾種（[買進比例, 至少幾檔]）。"""
    gk = next(k for k in it["grid"] if k != "pick")
    return gk, list(it["grid"][gk]), [tuple(x) for x in it["grid"]["pick"]]


def _allowed(it: dict) -> set:
    return set(CS.FIELDS) | set(CS.PROGRAM) | set(CS.OPTIONAL) | {f for fs in CS.NEED_BY.values() for f in fs}


def check_item(it: dict, prog_dir: Path = PROG, today: str | None = None) -> list[str]:
    """一筆規格的格式與程式的 sha（不跑程式）。→ 錯誤說明（空＝通過）。"""
    if not isinstance(it, dict):
        return ["規格的每一筆要是物件"]
    cid = str(it.get("id") or "?")
    err = lambda m: f"{cid}：{m}"
    out = []
    if not re.match(CS.ID_RE, cid):
        out.append(err("編號要是 c＋三位數"))
    for f in CS.FIELDS:
        if it.get(f) in (None, "", [], {}):
            out.append(err(f"缺 {f}"))
    extra = set(it) - _allowed(it)
    if extra:
        out.append(err(f"不認得的欄位 {sorted(extra)}"))
    eng, kind, mk = it.get("engine"), it.get("kind"), it.get("mk")
    if eng not in CS.ENGINES:
        out.append(err(f"引擎要是 {list(CS.ENGINES)}"))
    else:
        if kind not in CS.ENGINES[eng]:
            out.append(err(f"{eng} 的型態要是 {CS.ENGINES[eng]}"))
        if mk not in CS.MARKETS[eng]:
            out.append(err(f"{eng} 的市場要是 {CS.MARKETS[eng]}"))
    fd = str(it.get("found") or "")
    try:
        if date.fromisoformat(fd).isoformat() != fd:
            raise ValueError
        if today and fd > today:
            out.append(err("寫定日期在未來"))
    except ValueError:
        out.append(err("寫定日期要是 YYYY-MM-DD"))
    nm = it.get("name")
    if not isinstance(nm, str) or not (0 < len(nm) <= CS.NAME_MAX):
        out.append(err(f"名稱要 1～{CS.NAME_MAX} 個字"))
    src = it.get("src")
    if not isinstance(src, list) or not src or not all(isinstance(s, dict) and str(s.get("t") or "").strip()
                                                       and str(s.get("u") or "").startswith("https://") for s in src):
        out.append(err("來源要至少一條 {t: 標題, u: https 連結}"))
    txt = " ".join(str(it.get(f) or "") for f in ("name", "how", "why", "need", "note")) + " " + \
        " ".join(str(s.get("t") or "") for s in (src or []) if isinstance(s, dict))
    for w in BANNED:
        if w in txt:
            out.append(err(f"用了禁用詞「{w}」"))
    if it.get("prev") is not None and not re.match(CS.ID_RE, str(it["prev"])):
        out.append(err("prev 要是另一條候選的編號"))
    path = prog_dir / f"{cid}.py"
    if it.get("need") is not None:
        if not str(it["need"]).startswith("需要資料"):
            out.append(err("need 要寫成「需要資料：…」"))
        if it.get("sha") or path.exists():
            out.append(err("需要資料的候選不寫程式"))
        return out
    for f in CS.PROGRAM:
        if f not in it:
            out.append(err(f"缺 {f}"))
    for f in CS.NEED_BY.get(kind, ()):
        if f not in it:
            out.append(err(f"{kind} 型要有 {f}"))
    if out:
        return out
    p, grid = it["p"], it["grid"]
    if not isinstance(p, dict) or not isinstance(grid, dict) or not grid:
        return out + [err("p 與 grid 要是物件")]
    if not re.match(r"^[0-9a-f]{64}$", str(it.get("sha") or "")):
        out.append(err("sha 要是 64 位十六進位"))
    elif sha_file(path) != it["sha"]:
        out.append(err(f"程式 {path.name} 不在、或 sha 對不上（寫定之後不能改，要改就用新的編號）"))
    if kind == "per":
        if it.get("b") not in CS.TW_BUCKETS:
            out.append(err(f"b 要是 {CS.TW_BUCKETS}"))
        pk = it.get("pick") or {}
        if not isinstance(pk, dict) or set(pk) - set(CS.PICK_KEYS) or "top" not in pk or "nmin" not in pk:
            out.append(err(f"pick 要有 top、nmin（可以再有 {CS.PICK_KEYS}）"))
        elif not (0 <= float(pk["top"]) < 1) or int(pk["nmin"]) < 1:
            out.append(err("pick 的 top 要在 0～1、nmin ≥ 1"))
        ks = [k for k in grid if k != "pick"]
        if "pick" not in grid or len(ks) != 1 or ks[0] not in p:
            out.append(err("台股個股的 grid＝一個規則參數（p 裡的）＋pick"))
        else:
            gk, av, pv = _tw_grid(it)
            if p[gk] not in av or (pk.get("top"), pk.get("nmin")) not in [tuple(x) for x in pv]:
                out.append(err("grid 要包含原本那一組"))
            if len(av) * len(pv) > CS.GRID_MAX:
                out.append(err(f"參數鄰近最多 {CS.GRID_MAX} 組"))
        return out
    if kind == "dip" and not (isinstance(it.get("H"), int) and 1 <= it["H"] <= 1000):
        out.append(err("H 要是 1～1000 的整數（買進後抱幾個交易日）"))
    if kind == "book":
        ex = it.get("ex") or {}
        if not isinstance(ex, dict) or set(ex) - set(CS.US_EX_KEYS) or not isinstance(ex.get("slots"), int) \
                or not 1 <= ex["slots"] <= 20 or not any(ex.get(k) for k in ("hold", "ma", "trail", "stop")):
            out.append(err(f"ex 要有 slots（1～20）與至少一種出場（{CS.US_EX_KEYS}）"))
        elif ex.get("stop") and ex.get("hold"):
            out.append(err("ex 有 stop 時不能有 hold（停損的寫法沒有時間上限）"))
    bad = [k for k in grid if k not in p]
    if bad:
        out.append(err(f"grid 的參數 {bad} 不在 p 裡"))
    elif any(not isinstance(v, list) or p[k] not in v for k, v in grid.items()):
        out.append(err("grid 每個參數要是清單、而且包含原本的值"))
    elif len(combos(grid)) > CS.GRID_MAX:
        out.append(err(f"參數鄰近最多 {CS.GRID_MAX} 組"))
    return out


def check_spec(doc: dict, prog_dir: Path = PROG, today: str | None = None) -> list[str]:
    items = doc.get("items")
    if not isinstance(items, list):
        return ["items 要是清單"]
    out = []
    ids = [str(it.get("id")) for it in items if isinstance(it, dict)]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        out.append(f"編號重複：{dup}")
    for it in items:
        out += check_item(it, prog_dir, today)
    for it in items:
        if isinstance(it, dict) and it.get("prev") and it["prev"] not in ids:
            out.append(f"{it.get('id')}：prev {it['prev']} 不在規格裡")
    have = {p.stem for p in prog_dir.glob("c*.py")}
    stray = sorted(have - {i for i, it in zip(ids, items) if isinstance(it, dict) and it.get("need") is None})
    if stray:
        out.append(f"程式沒有對應的規格：{stray}")
    return out


def load_board(path: Path | None = None) -> dict:
    try:
        return json.loads((path or BOARD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def decisions(conf: dict | None = None) -> dict:
    """{編號: {dec: trial／adopt／reject, d: 日期, why: 原因}}（config/strategy_board.json 的 cand）。"""
    C = conf if conf is not None else load_board()
    out = {}
    for k, v in (C.get("cand") or {}).items():
        if isinstance(v, dict) and v.get("dec") in CS.DECISIONS:
            out[k] = v
    return out


def open_ids(doc: dict, dec: dict) -> list[str]:
    """還沒決定的候選。"""
    return [it["id"] for it in doc.get("items") or [] if isinstance(it, dict) and it.get("id") not in dec]


def merge_check(old: dict, new: dict, prog_dir: Path, dec: dict, today: str | None = None) -> tuple[list[str], list[str]]:
    """合併通道：new＝分支上的規格（程式已經放在 prog_dir）；old＝main 上的。→ (錯誤, 新的編號)。"""
    errs = check_spec(new, prog_dir, today)
    o = {it["id"]: it for it in old.get("items") or [] if isinstance(it, dict) and it.get("id")}
    n = {it["id"]: it for it in new.get("items") or [] if isinstance(it, dict) and it.get("id")}
    for k, it in o.items():
        if k not in n:
            errs.append(f"{k}：不能刪掉（不納入的寫在 strategy_board.json）")
        elif dumps(n[k]) != dumps(it):
            errs.append(f"{k}：寫定之後不能改（要改就用新的編號）")
    fresh = [k for k in n if k not in o]
    if len(fresh) > CS.MAX_NEW:
        errs.append(f"一次最多 {CS.MAX_NEW} 條新的（這次 {len(fresh)} 條）")
    op = open_ids(new, dec)
    if len(op) > CS.MAX_OPEN:
        errs.append(f"還沒決定的最多 {CS.MAX_OPEN} 條（合併後 {len(op)} 條）")
    return errs, fresh


def module(cid: str):
    """候選的程式（arm.lab.cands.{編號}）。"""
    return importlib.import_module(f"arm.lab.cands.{cid}")


# ── 指數型（xstrat 外掛） ───────────────────────────────────────────────────────

def ix_spec(it: dict) -> dict:
    return {"k": f"cand_{it['id']}", "kind": it["kind"], "p": it["p"], "grid": it["grid"], "grp": "cand", "H": it.get("H")}


def cut_data(D: dict, n: int) -> dict:
    """指數型的資料截在第 n 天之前（陣列與日曆都截）。"""
    T = len(D["cal"])
    out = {}
    for k, v in D.items():
        if k == "cal":
            out[k] = list(v)[:n]
        elif isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == T:
            out[k] = v[:n].copy()
        else:
            out[k] = v
    return out


def _week_end(cal: list[str], i: int) -> bool:
    return date.fromisoformat(cal[i]).isocalendar()[:2] != date.fromisoformat(cal[i + 1]).isocalendar()[:2]


def check_days(cal: list[str]) -> list[int]:
    """打亂之後的價格（candspec VER 2）：每個 CUTS 位置的那一天、之後最近的月底、最近的週末。"""
    from . import xstrat as XT
    T = len(cal)
    ends = XT.month_ends(cal)
    out = set()
    for f in CS.CUTS:
        b = int(T * f)
        out.add(b)
        m = next((e for e in ends if e >= b), None)
        if m is not None:
            out.add(m)
        w = next((i for i in range(b, T - 1) if _week_end(cal, i)), None)
        if w is not None:
            out.add(w)
    return sorted(i for i in out if 10 <= i < T - 2)


def perturb_data(D: dict, t: int, seed: int) -> dict:
    """指數型的資料：第 t 天以後的每一個序列乘上亂數（每天不同）。"""
    rng = np.random.default_rng(seed)
    T = len(D["cal"])
    out = dict(D)
    for k in sorted(D):
        v = D[k]
        if k != "cal" and isinstance(v, np.ndarray) and v.ndim == 1 and len(v) == T:
            f = np.ones(T)
            f[t + 1:] = np.exp(rng.normal(0.0, CS.PEEK_SIGMA, T - t - 1))
            out[k] = v * f
    return out


def _ix_upto(C, sp: dict, t: int):
    """第 t 天（含）以前就決定好的東西：進出型＝部位（到 t＋lag，因為第 t 天的決定在 t＋lag 才照做）；
    交易型＝訊號在 t 以前的每一筆（出場訊號在 t 以後的只比進場）；落底型＝t 以前的訊號日。"""
    from . import xstratspec as XS
    k, kind, p = sp["k"], sp["kind"], sp["p"]
    if kind == "alloc":
        return [None if x != x else float(x) for x in np.asarray(C.pos(k, p, XS.LAG), dtype=float)[:t + 1 + XS.LAG]]
    if kind == "trade":
        return [(a, e, x if x <= t else None, q if x <= t else None) for a, e, x, q in C.trades(k, p, XS.LAG)[0] if a <= t]
    raw, first = C.dip_raw(k, p)
    return [d for d in raw if d <= t], (first if first <= t else None)


def peek_index(sp: dict, D: dict) -> list[str]:
    """用到未來的資料（candspec 第二節）：① 把資料截在 CUTS 三個位置，截點以前的部位／交易／訊號要和完整資料一模一樣；
    ② VER 2：檢查日（check_days）以後的序列打亂，檢查日以前就決定好的要一模一樣。"""
    from . import xstrat as XT
    from . import xstratspec as XS
    k, kind, p = sp["k"], sp["kind"], sp["p"]
    C = XT.Ctx(D)
    msgs = []
    for f in CS.CUTS:
        n = int(C.T * f)
        if n < 10:
            continue
        C2 = XT.Ctx(cut_data(D, n))
        day = C.cal[n - 1]
        if kind == "alloc":
            a, b = np.asarray(C.pos(k, p, XS.LAG), dtype=float)[:n], np.asarray(C2.pos(k, p, XS.LAG), dtype=float)
            if len(b) != n or not np.array_equal(a, b, equal_nan=True):
                bad = next((i for i in range(min(len(a), len(b))) if not (a[i] == b[i] or (a[i] != a[i] and b[i] != b[i]))), None)
                msgs.append(f"資料截在 {day}：{C.cal[bad] if bad is not None else day} 的部位不一樣")
        elif kind == "trade":
            ta = [t for t in C.trades(k, p, XS.LAG)[0] if t[3] < n]
            tb = C2.trades(k, p, XS.LAG)[0]
            if [tuple(x) for x in ta] != [tuple(x) for x in tb]:
                msgs.append(f"資料截在 {day}：之前的交易不一樣")
        else:
            ra, fa = C.dip_raw(k, p)
            rb, fb = C2.dip_raw(k, p)
            if [t for t in ra if t < n] != list(rb) or (fa < n and fa != fb):
                msgs.append(f"資料截在 {day}：之前的訊號日不一樣")
    for j, t in enumerate(check_days(C.cal)):
        C3 = XT.Ctx(perturb_data(D, t, CS.PEEK_SEED + j))
        if _ix_upto(C, sp, t) != _ix_upto(C3, sp, t):
            msgs.append(f"{C.cal[t]} 以後的價格換掉，{C.cal[t]} 以前就該決定好的不一樣")
    return msgs


def index_daily(mk: str, C, held: np.ndarray) -> dict:
    """指數型每天的報酬（放進計畫、試用紀錄用）：前一天收盤後有部位＝含息指數，沒有＝現金利息，換邊那天付 ETF 成本。"""
    from . import tilt as TL
    from . import xstratspec as XS
    Cy = TL.carry_inputs(mk, C.cal, C.px)
    tot = np.nan_to_num(np.asarray(Cy["tot"], dtype=float))
    rf = np.nan_to_num(np.asarray(Cy["rate"], dtype=float) * np.asarray(Cy["days"], dtype=float) / 365.0)
    h = np.nan_to_num(np.asarray(held, dtype=float))
    c = XS.COST[mk]
    out = {}
    for k in range(max(C.s0, 1), C.T):
        g = h[k - 1] * tot[k] + (1 - h[k - 1]) * rf[k]
        if h[k] != h[k - 1]:
            g = (1 + g) * (1 - c) - 1
        out[C.cal[k]] = float(g)
    return out


def run_index(it: dict, D: dict | None = None, peek: bool = True) -> dict:
    from . import xstrat as XT
    mod = module(it["id"])
    sp = ix_spec(it)
    XT.PLUGINS[sp["k"]] = mod
    D = D if D is not None else XT.data(it["mk"])
    C = XT.Ctx(D)
    r = XT.strategy(C, sp)
    held = XT.held_pos(C, sp)
    return {"r": r, "peek": peek_index(sp, D) if peek else [], "daily": index_daily(it["mk"], C, held), "C": C}


def index_summary(r: dict) -> dict:
    """研究檔要留的：判定、全部與近 10 年、參數鄰近、打亂測試、現在、淨值（月底）、每一筆（或每一段）。"""
    keep = ("k", "mk", "kind", "a", "z", "r0", "cost", "lag", "H", "tier", "grid_ok", "p", "rec_ok")
    out = {k: r.get(k) for k in keep if k in r}
    for k in ("full", "rec", "bh", "bh_r", "ref", "b1", "curve"):
        if isinstance(r.get(k), dict):
            out[k] = {kk: (_r(v, 6) if isinstance(v, (int, float)) else v) for kk, v in r[k].items() if not isinstance(v, (list, dict))}
    out["grid"] = r.get("grid")
    out["now"] = r.get("now")
    out["eq"] = r.get("eq")
    out["tr"] = r.get("tr")
    return out


# ── 台股個股（回測方法 v3 的長歷史面板與資金帳戶） ──────────────────────────────────

def cut_panel(P, n: int):
    """Px 介面的面板截在第 n 天之前（價量、市值、成交值、指數都截；快取重來）。"""
    Q = copy.copy(P)
    Q.cal = list(P.cal[:n])
    Q.T = n
    Q.ix = {d: i for i, d in enumerate(Q.cal)}
    for a in ("idx", "idx_o", "tr"):
        if hasattr(P, a) and getattr(P, a) is not None:
            setattr(Q, a, list(getattr(P, a))[:n])
    Q.s = {c: {k: list(v)[:n] for k, v in d.items()} for c, d in P.s.items()}
    Q.cap = {c: list(v)[:n] for c, v in P.cap.items()}
    Q.liq = {c: list(v)[:n] for c, v in P.liq.items()}
    Q._el, Q._win = {}, {}
    return Q


def perturb_panel(P, t: int, seed: int):
    """Px 介面的面板：第 t 天以後的價量、市值、成交值、指數乘上亂數（每天、每檔不同；candspec VER 2）。"""
    import random
    rnd = random.Random(seed)
    Q = copy.copy(P)
    n = P.T - t - 1

    def tail(v, g):
        v = list(v)
        return v[:t + 1] + [None if x is None else x * gg for x, gg in zip(v[t + 1:], g)]
    Q.s, Q.cap, Q.liq = {}, {}, {}
    for c in sorted(P.s):
        g = [math.exp(rnd.gauss(0.0, CS.PEEK_SIGMA)) for _ in range(n)]
        Q.s[c] = {k: tail(v, g) for k, v in P.s[c].items()}
        if c in P.cap:
            Q.cap[c] = tail(P.cap[c], g)
        if c in P.liq:
            Q.liq[c] = tail(P.liq[c], g)
    g = [math.exp(rnd.gauss(0.0, CS.PEEK_SIGMA)) for _ in range(n)]
    for a in ("idx", "idx_o", "tr"):
        if getattr(P, a, None) is not None:
            setattr(Q, a, tail(getattr(P, a), g))
    Q._el, Q._win = {}, {}
    return Q


def peek_tw(it: dict, mod, P, F, rows_full: list) -> list[str]:
    """用到未來的資料：① 截在 CUTS 三個位置；② VER 2：每個 CUTS 位置之後最近的形成日以後的價量打亂，那一期（含）以前的分數要一樣。"""
    from . import bt3
    full = {t: sc for t, _, sc in rows_full}
    forms = sorted(full)
    msgs = []
    for f in CS.CUTS:
        n = int(P.T * f)
        if n < 10:
            continue
        Q = cut_panel(P, n)
        got = {t: sc for t, _, sc in mod.rows(Q, bt3.Elig(Q), it["b"], Q.codes, it["p"], F)}
        day = P.cal[n - 1]
        for t, sc in full.items():
            if t >= n - 1:
                continue
            if t not in got:
                msgs.append(f"資料截在 {day}：{P.cal[t]} 那一期不見了")
                break
            if got[t] != sc:
                msgs.append(f"資料截在 {day}：{P.cal[t]} 那一期的分數不一樣")
                break
        extra = sorted(t for t in got if t < n - 1 and t not in full)
        if extra:
            msgs.append(f"資料截在 {day}：多了 {P.cal[extra[0]]} 那一期")
    pts = sorted({next((t for t in forms if t >= int(P.T * f)), None) for f in CS.CUTS} - {None})
    for j, t0 in enumerate(pts):
        if t0 >= P.T - 2:
            continue
        Q = cut_panel(P, P.T)
        Q = perturb_panel(Q, t0, CS.PEEK_SEED + j)
        got = {t: sc for t, _, sc in mod.rows(Q, bt3.Elig(Q), it["b"], Q.codes, it["p"], F)}
        bad = next((t for t in forms if t <= t0 and got.get(t) != full[t]), None)
        if bad is not None:
            msgs.append(f"{P.cal[t0]} 以後的價格換掉，{P.cal[bad]} 那一期的分數不一樣")
    return msgs


def _curve_stats(vals: list, cal: list) -> dict:
    """[(日索引, 淨值)] → 年化、最慘時跌多少（小數）。"""
    if len(vals) < 2:
        return {}
    (i0, v0), (i1, v1) = vals[0], vals[-1]
    yrs = (date.fromisoformat(cal[i1]) - date.fromisoformat(cal[i0])).days / 365.25
    pk, mdd = vals[0][1], 0.0
    for _, v in vals:
        pk = max(pk, v)
        mdd = max(mdd, 1 - v / pk if pk > 0 else 0)
    return {"a": cal[i0], "b": cal[i1], "m": v1 / v0 if v0 else None,
            "cagr": (v1 / v0) ** (1 / yrs) - 1 if yrs > 0 and v0 > 0 and v1 > 0 else None, "mdd": mdd}


def tw_eval(it: dict, mod, P, F) -> dict:
    from . import bt3, bt3s
    E = bt3.Elig(P)
    b, pk = it["b"], it["pick"]
    gk, avals, pvals = _tw_grid(it)
    a0, base = it["p"][gk], (pk["top"], pk["nmin"])
    asc, umin = bool(pk.get("asc")), pk.get("umin")
    cache: dict = {}

    def rows(a):
        if a not in cache:
            cache[a] = mod.rows(P, E, b, P.codes, {**it["p"], gk: a}, F)
        return cache[a]

    def run(a, top, nmin, log=None):
        rr = rows(a)
        done = [r for r in rr if r[1] is not None]
        sel = bt3s.pick(done, top, nmin, asc, umin)
        acc = bt3.account(P, sel, b, log=log)
        ew = bt3s._ew(P, b, done, sel)
        return done, sel, acc, ew, sorted(bt3.vs_ew(acc, ew), key=lambda u: u["d"])

    done, sel, acc, ew, U = run(a0, *base)
    full = bt3.payoff(U)
    later = bt3.payoff(U[len(U) // 2:])
    cells = []
    for a in avals:
        for tv in pvals:
            Uc = U if (a == a0 and tuple(tv) == base) else run(a, tv[0], tv[1])[4]
            pc = bt3.payoff(Uc)
            cells.append({"a": a, "pick": list(tv), "ok": bool(pc.get("ok")), "n": pc.get("n"), "win": _r(pc.get("win"), 2),
                          "m": _r(pc.get("m"), 3), "avg": _r(pc.get("avg"), 3)})
    share = sum(c["ok"] for c in cells) / len(cells) if cells else 0.0
    n = len(U)
    tier = "few" if n < CS.TW_N_MIN else ("good" if full.get("ok") and later.get("ok") and share >= CS.GRID_OK
                                          else "ref" if full.get("ok") else "none")
    cv = acc["curve"]
    st = _curve_stats(cv, P.cal)
    ews = _curve_stats(ew["curve"], P.cal)
    trv = [(i, P.tr[i]) for i, _ in cv if getattr(P, "tr", None) and P.tr[i]]
    tr = _curve_stats(trv, P.cal) if len(trv) > 1 else {}
    active = set()
    for t, x, _ in sel:
        active.update(range(t + 1, x + 1))
    daily, acct = {}, {}
    for (i0, v0), (i1, v1) in zip(cv, cv[1:]):
        if v0 > 0:
            acct[P.cal[i1]] = float(v1 / v0 - 1)
            if i1 in active:
                daily[P.cal[i1]] = acct[P.cal[i1]]
    now = None
    rr = rows(a0)
    if rr and rr[-1][1] is None:
        cur = bt3s.pick([rr[-1]], base[0], base[1], asc, umin)
        if cur:
            now = {"d": P.cal[rr[-1][0]], "picks": list(cur[0][2]), "n_uni": len(rr[-1][2])}
    pay = lambda p: {k: (_r(v, 3) if isinstance(v, float) else v) for k, v in p.items()}
    return {"tier": tier, "n": n, "full": pay(full), "later": pay(later), "grid": cells, "grid_ok": _r(share, 4),
            "acc": {k: _r(v, 6) if isinstance(v, float) else v for k, v in st.items()},
            "ew": {k: _r(v, 6) if isinstance(v, float) else v for k, v in ews.items()},
            "tr": {k: _r(v, 6) if isinstance(v, float) else v for k, v in tr.items()},
            "xe": _r(sum(u["xe"] for u in U if u.get("xe") is not None) / max(1, sum(1 for u in U if u.get("xe") is not None)), 3),
            "per": [[u["d"], _r(u.get("r"), 3), _r(u.get("xe"), 3), u.get("n"), u.get("hd")] for u in U],
            "now": now, "daily": daily, "acct": acct, "rows": rr, "b": b}


def run_tw(it: dict, P=None, F=None, peek: bool = True) -> dict:
    from . import bt3d
    from .cands import Fin
    mod = module(it["id"])
    P = P if P is not None else bt3d.Panel()
    F = F or Fin()
    out = tw_eval(it, mod, P, F)
    out["peek"] = peek_tw(it, mod, P, F, out.pop("rows")) if peek else []
    if not peek:
        out.pop("rows", None)
    return out


# ── 美股個股（資料分支的面板與 ussxbook） ──────────────────────────────────────────

def us_run(C: dict, it: dict, mod, p: dict) -> tuple[dict, dict]:
    from . import ussxbook as BK
    from . import ussxfeat as UF
    from . import ussxqm as Q
    from . import ussxspec as UX
    ex = it["ex"]
    slots = int(ex["slots"])
    sig = mod.signals(C, p)
    a = Q.a_of(C["cal"], CS.US_Y0)
    exd = {k: ex[k] for k in ("hold", "trail", "stop") if ex.get(k)}
    MA = None
    if ex.get("ma"):
        exd["ma"] = ex["ma"]
        MA = C["MA"] if ex["ma"] == UX.QM_EXIT["ma"] else UF.roll_mean(C["Cf"], int(ex["ma"]))
    ir, _ = Q.idle_of(C, "spx", "cash")
    P = C["P"]
    r = BK.run(P["O"], C["Cf"], P["C"], P["last"], sig, a, C["T"], ir, ex=exd, style="w8" if ex.get("stop") else "trend",
               MA=MA, D20=C["D20"], DIV=C["DIV"], weight=1.0 / slots, max_pos=slots,
               max_weight=max(1.0 / slots, UX.TRADE["max_weight"]), c_stk=UX.COST["stk"], c_idx=0.0)
    r["a"] = a
    return r, sig


def us_eval(it: dict, mod, C: dict) -> dict:
    from . import ussxbook as BK
    from . import ussxqm as Q
    cal, T = C["cal"], C["T"]
    a14 = Q.a_of(cal, CS.US_EVAL)
    spx = BK.curve_stats(cal, C["PQ"]["spx"]["idle"], a14, T)

    def beats(st):
        return st.get("cagr") is not None and spx.get("cagr") is not None and st["cagr"] > spx["cagr"]

    r, sig = us_run(C, it, mod, it["p"])
    rr = Q.rets(C, r)
    st = BK.curve_stats(cal, rr, a14, T)
    later = st["halves"][1] if st.get("halves") else {}
    cells = []
    for q in combos(it["grid"]):
        pp = {**it["p"], **q}
        s2 = st if pp == it["p"] else BK.curve_stats(cal, Q.rets(C, us_run(C, it, mod, pp)[0]), a14, T)
        cells.append({"p": q, "ok": bool(beats(s2)), "cagr": _r(s2.get("cagr"), 6), "mdd": _r(s2.get("mdd"), 6)})
    share = sum(c["ok"] for c in cells) / len(cells) if cells else 0.0
    yrs = (date.fromisoformat(cal[T - 1]) - date.fromisoformat(cal[a14])).days / 365.25
    ok_full = beats(st)
    ok_later = later.get("cagr") is not None and len(spx.get("halves") or []) > 1 and later["cagr"] > spx["halves"][1]["cagr"]
    tier = "few" if yrs < CS.US_YEARS_MIN else ("good" if ok_full and ok_later and share >= CS.GRID_OK
                                                else "ref" if ok_full else "none")
    stk = Q.stk_share(C, r)
    last = max(sig) if sig else None
    now = None
    if last is not None:
        now = {"d": cal[last], "picks": [Q._sym(C, j) for j, _ in sig[last][:int(it["ex"]["slots"])]],
               "held": [Q._sym(C, j) for j in (r.get("state") or {}).get("pos", {})]}
    brief = lambda s: {k: _r(s.get(k), 6) for k in ("cagr", "mdd", "m")} | {"a": s.get("a"), "b": s.get("b")}
    return {"tier": tier, "yrs": _r(yrs, 2), "full": brief(st), "later": brief(later) if later else None,
            "spx": brief(spx), "spx_later": brief(spx["halves"][1]) if spx.get("halves") else None,
            "grid": cells, "grid_ok": _r(share, 4), "exposure": _r(float(np.mean(stk[a14:])), 4), "now": now,
            "daily": {cal[k]: float(rr[k]) for k in range(r["a"] + 1, T)}, "stk": stk, "rr": rr}


def run_us(it: dict, C: dict | None = None) -> dict:
    from . import ussxqm as Q
    mod = module(it["id"])
    C = C if C is not None else Q.context()
    out = us_eval(it, mod, C)
    out["peek"] = []                                   # 美股面板太大，截資料重算不做（candspec 第二節只對指數型與台股個股）
    return out


# ── 放進計畫試算 ───────────────────────────────────────────────────────────────

def _brief_sc(sc: dict) -> dict:
    keep = ("m", "cagr", "mdd", "worst")
    return {"a": sc["a"], "b": sc["b"], "plan": {k: _r(sc["plan"].get(k), 6) for k in keep},
            "hold": {k: _r(sc["hold"].get(k), 6) for k in keep},
            "halves": [{"a": h["a"], "b": h["b"], "plan": {k: _r(h["plan"].get(k), 6) for k in keep}} for h in sc["halves"]]}


def plan_judge(new: dict, cur: dict) -> dict:
    """三條（candspec 第四節）：100 萬比較多、前半後半都不比較少、最慘時跌得不比現在深超過 PLAN_MDD_MORE。"""
    m = new["plan"]["m"] > cur["plan"]["m"]
    hv = all(a["plan"]["m"] >= b["plan"]["m"] for a, b in zip(new["halves"], cur["halves"]))
    dd = new["plan"]["mdd"] <= cur["plan"]["mdd"] + CS.PLAN_MDD_MORE
    return {"money": bool(m), "halves": bool(hv), "mdd": bool(dd), "pass": bool(m and hv and dd)}


def star_n(path: Path | None = None) -> int:
    """現在台股機動裡的 ★ 條數：sig_stock.json 裡有逐筆交易的個股策略判定 good 的條數（讀不到＝STAR_N_DEFAULT）。"""
    try:
        doc = json.loads((path or SIGSTK).read_text(encoding="utf-8"))
        n = sum(1 for r in doc.get("rows") or [] if str(r.get("id", "")).startswith("stk:strat:") and r.get("tier") == "good"
                and not str(r.get("desc") or "").startswith("回測方法 v3 研究版本"))
        return n or CS.STAR_N_DEFAULT
    except (OSError, ValueError, AttributeError):
        return CS.STAR_N_DEFAULT


def tw_plan_parts() -> dict | None:
    """台股交易計畫（core.research 的 plan 那一段，同一套寫法）的輸入：日曆、含息、利率、警訊、★ 那一半、新飆股、期間。"""
    from . import core as CO
    from . import corespec as S
    M = CO.market_inputs("tw")
    cal, px, tot, rf = M["cal"], M["px"], M["tot"], M["rf"]
    T = len(cal)
    F = CO.families(px, M["inf"], M["lev"], CO.macro_flat("tw", cal), "tw")
    st = CO.stk_sleeve(cal, tot, rf=rf)
    star = S.STAR_ACTIVE * st["sl"] + (1 - S.STAR_ACTIVE) * rf
    bm = CO.boom_sleeve(cal, rf)
    if not bm:
        return None
    pb = next(k for k, d in enumerate(cal) if d >= st["b"]) + 1
    pa = next(k for k, d in enumerate(cal) if d >= max(S.PLAN4_START, bm["a"]))
    return {"cal": cal, "px": px, "tot": tot, "rf": rf, "F": F, "star": star, "boom": bm["r"], "g": S.BOOM_SHARE["tw"],
            "pa": pa, "pb": pb, "T": T}


def plan_tw(daily: dict, parts: dict | None = None) -> dict | None:
    """台股：★ 那一半平分給 N＋1 條（這條候選是第 N＋1 條），新飆股那一半不動；和現在的計畫同一段比。"""
    from . import core as CO
    from . import corespec as S
    X = parts if parts is not None else tw_plan_parts()
    if not X:
        return None
    cal, T, rf = X["cal"], X["T"], X["rf"]
    g, zero = X["g"], np.zeros(X["T"])

    def sc(star):
        return CO.scenario("plan", "tw", cal, X["px"], X["tot"], rf, X["F"], X["pa"], X["pb"], S.COST["tw"],
                           sl=g * X["boom"] + (1 - g) * star, inpos=np.ones(T, dtype=bool), swc=zero, c_stk=S.COST["tw_stk"])
    cur = sc(X["star"])
    n = star_n()
    x = np.array([daily.get(d, rf[k]) for k, d in enumerate(cal)])
    new = sc(n / (n + 1) * X["star"] + x / (n + 1))
    nb, cb = _brief_sc(new), _brief_sc(cur)
    return {"mk": "tw", "n": n, "cur": cb, "new": nb, "judge": plan_judge(nb, cb)}


def plan_us(C: dict, daily: dict, stk: np.ndarray | None = None) -> dict:
    """美股（spx、ndx）：機動一半照原本（美股強勢品質股判定過＝它，否則指數）、一半這條候選；期間＝美股強勢品質股的計畫那一段。"""
    from . import ussxqm as Q
    from . import ussxspec as UX
    R = Q.load() or {}
    sw = R.get("switch") or {}
    cal, T = C["cal"], C["T"]
    a14 = Q.a_of(cal, UX.QM_EVAL)
    out = {}
    qm_sig = None
    for mk in ("spx", "ndx"):
        cash = C["PQ"][mk]["cash"]
        rc = np.array([daily.get(d, cash[k]) for k, d in enumerate(cal)])
        st_c = np.asarray(stk, dtype=float) if stk is not None else np.zeros(T)
        if sw.get(mk):
            if qm_sig is None:
                qm_sig = Q.signals(C, Q.qm_mask(C["cols"]["f"]))
            rq = Q.run(C, qm_sig, mk, UX.COST["stk"])
            base, st_b = Q.rets(C, rq), Q.stk_share(C, rq)
            cur = Q.plan_scenarios(C, mk, base, st_b, a14, T, UX.COST["stk"])[0]
        else:
            base, st_b = np.asarray(C["PQ"][mk]["idle"], dtype=float), np.zeros(T)
            cur = Q.plan_scenarios(C, mk, rc, st_c, a14, T, UX.COST["stk"])[1]
        new = Q.plan_scenarios(C, mk, 0.5 * base + 0.5 * rc, np.maximum(st_b, st_c), a14, T, UX.COST["stk"])[0]
        nb, cb = _brief_sc(new), _brief_sc(cur)
        out[mk] = {"mk": mk, "qm": bool(sw.get(mk)), "cur": cb, "new": nb, "judge": plan_judge(nb, cb)}
    return out


# ── 一條候選 ─────────────────────────────────────────────────────────────────

class Ctx:
    """一次 compute 共用的資料（要用到才載入）：台股長歷史面板、財務、美股面板、台股計畫的輸入。"""

    def __init__(self, us: dict | None = None, P=None):
        self._P, self._us, self._tw = P, us, None
        self.F = None

    def panel(self):
        if self._P is None:
            from . import bt3d
            self._P = bt3d.Panel()
        return self._P

    def fin(self):
        if self.F is None:
            from .cands import Fin
            self.F = Fin()
        return self.F

    def us(self) -> dict | None:
        """美股面板（要 USSX_DIR 指到資料分支；沒有＝None）。"""
        if self._us is None:
            import os
            if not os.environ.get("USSX_DIR"):
                return None
            from . import ussxqm as Q
            self._us = Q.context()
        return self._us

    def tw_parts(self):
        if self._tw is None:
            self._tw = tw_plan_parts() or {}
        return self._tw or None


def evaluate(it: dict, X: Ctx | None = None, today: str | None = None) -> dict:
    """一條候選 → 研究檔的一筆（v＝判定或 need／err／peek）。"""
    X = X or Ctx()
    base = {"id": it["id"], "spec": CS.VER, "sha": it.get("sha"), "dig": digest(it), "made": today or date.today().isoformat(),
            "engine": it["engine"], "mk": it["mk"], "kind": it["kind"]}
    if it.get("need") is not None:
        return {**base, "v": "need"}
    eng, mk = it["engine"], it["mk"]
    if eng == "index":
        R = run_index(it)
        res = {"x": index_summary(R["r"]), "tier": R["r"]["tier"]}
        daily, stk = R["daily"], None
    elif eng == "tw_stock":
        R = run_tw(it, X.panel(), X.fin())
        res = {"x": {k: v for k, v in R.items() if k not in ("daily", "acct", "peek")}, "tier": R["tier"]}
        daily, stk = R["daily"], None
    else:
        C = X.us()
        if C is None:
            return {**base, "v": "err", "err": "美股資料不在（USSX_DIR 沒有指到資料分支）"}
        R = run_us(it, C)
        res = {"x": {k: v for k, v in R.items() if k not in ("daily", "peek", "stk", "rr")}, "tier": R["tier"]}
        daily, stk = R["daily"], R["stk"]
    out = {**base, **res, "v": "peek" if R["peek"] else res["tier"], "peek": R["peek"]}
    plans = {}
    for pm in CS.PLAN_OF.get(mk, ()):
        try:
            if pm == "tw":
                p = plan_tw(daily, X.tw_parts())
                if p:
                    plans["tw"] = p
            else:
                C = X.us()
                if C is None:
                    plans[pm] = {"err": "美股資料不在"}
                    continue
                if pm not in plans:
                    if eng == "index":
                        daily_us = {d: daily[d] for d in C["cal"] if d in daily}
                        plans.update(plan_us(C, daily_us))
                    else:
                        plans.update(plan_us(C, daily, stk))
        except Exception as e:                            # noqa: BLE001 —— 試算算不出來不影響判定
            plans[pm] = {"err": f"{type(e).__name__}: {e}"}
    out["plan"] = {k: v for k, v in plans.items() if k in CS.PLAN_OF.get(mk, ())}
    return out


# ── 研究檔、試用紀錄 ─────────────────────────────────────────────────────────────

def load_res(path: Path | None = None) -> dict:
    try:
        R = json.loads((path or RES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"items": {}}
    R.setdefault("items", {})
    return R


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return round(f, 6) if math.isfinite(f) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


def save_res(R: dict, path: Path | None = None) -> bool:
    p = path or RES
    txt = json.dumps(_clean(R), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True


def fresh(R: dict, it: dict) -> bool:
    """研究檔已經有這一筆、而且是同一份規格與程式、同一版框架算的。"""
    x = (R.get("items") or {}).get(it["id"])
    return bool(x) and x.get("dig") == digest(it) and x.get("spec") == CS.VER and x.get("v") != "err"


def compute(ids: list[str] | None = None, *, force: bool = False, X: Ctx | None = None, log=print,
            spec_path: Path | None = None, res_path: Path | None = None) -> tuple[dict, list[str]]:
    """算還沒有結果（或規格變了、框架改版、上次沒算出來）的候選。→ (研究檔, 這次算的編號)。"""
    doc = load_spec(spec_path)
    R = load_res(res_path)
    X = X or Ctx()
    done = []
    for it in doc["items"]:
        if ids is not None and it.get("id") not in ids:
            continue
        if not force and fresh(R, it):
            continue
        try:
            res = evaluate(it, X)
        except Exception as e:                            # noqa: BLE001
            res = {"id": it["id"], "spec": CS.VER, "sha": it.get("sha"), "dig": digest(it), "made": date.today().isoformat(),
                   "engine": it.get("engine"), "mk": it.get("mk"), "kind": it.get("kind"), "v": "err",
                   "err": f"{type(e).__name__}: {e}"}
        R["items"][it["id"]] = res
        done.append(it["id"])
        log(f"[候選] {it['id']} {it.get('name')}：{CS.VERDICT.get(res['v'], res['v'])}"
            + (f"（{res.get('err')}）" if res.get("err") else "") + (f"；{res['peek'][0]}" if res.get("peek") else ""))
    R["ver"], R["made"] = CS.VER, date.today().isoformat()
    return R, done


def load_live(path: Path | None = None) -> dict:
    try:
        L = json.loads((path or LIVE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"v": 1, "items": {}}
    L.setdefault("items", {})
    return L


def append_live(rec: dict, daily: dict, hold: dict, start: str) -> int:
    """試用紀錄只增不改：只加在最後一天之後、起點以後的日子。→ 加了幾天。"""
    rec.setdefault("start", start)
    r, h = rec.setdefault("r", {}), rec.setdefault("h", {})
    last = max(r) if r else None
    n = 0
    for d in sorted(daily):
        if d < rec["start"] or (last is not None and d <= last):
            continue
        r[d] = round(float(daily[d]), 6)
        if d in hold:
            h[d] = round(float(hold[d]), 6)
        n += 1
    return n


def live_stats(rec: dict) -> dict:
    """試用到現在：交易日數、照做與一直抱著的累積報酬。"""
    r = rec.get("r") or {}
    h = rec.get("h") or {}
    ds = sorted(r)
    a = float(np.prod([1 + r[d] for d in ds])) - 1 if ds else None
    b = float(np.prod([1 + h[d] for d in ds if d in h])) - 1 if ds else None
    return {"n": len(ds), "a": ds[0] if ds else None, "z": ds[-1] if ds else None, "ret": a, "hold": b,
            "ok": len(ds) >= CS.TRIAL_CHECK}


def _hold_daily(mk: str) -> dict:
    """一直抱著（含息指數）每天的報酬：台股加權報酬指數、美股 S&P 500 含息（試用紀錄的對照）。"""
    from . import tilt as TL
    from . import xstrat as XT
    D = XT.data("tw" if mk == "tw" else ("spx" if mk == "us" else mk))
    Cy = TL.carry_inputs(D["mk"], list(D["cal"]), D["px"])
    tot = np.nan_to_num(np.asarray(Cy["tot"], dtype=float))
    return {d: float(tot[k]) for k, d in enumerate(D["cal"]) if k}


def current_daily(it: dict, X: Ctx) -> dict:
    """試用中的候選用現在的資料照規則做：每天的報酬（指數型＝有部位拿指數、沒有拿現金；個股型＝帳戶淨值）。"""
    eng = it["engine"]
    if eng == "index":
        return run_index(it, peek=False)["daily"]
    if eng == "tw_stock":
        from .analyze import Data
        from .cands import Fin
        from . import v3live
        P = v3live.live_panel(Data(long=True))
        return tw_eval(it, module(it["id"]), P, Fin())["acct"]
    C = X.us()
    if C is None:
        raise RuntimeError("美股資料不在（USSX_DIR 沒有指到資料分支）")
    return us_eval(it, module(it["id"]), C)["daily"]


def forward(X: Ctx | None = None, *, log=print, live_path: Path | None = None, spec_path: Path | None = None,
            board: dict | None = None) -> tuple[dict, list[str]]:
    """試用中的候選補紀錄（candspec 第五節）：決定日之後第一個交易日起，只加在最後一天之後（只增不改）。"""
    X = X or Ctx()
    dec = decisions(board)
    items = {it["id"]: it for it in load_spec(spec_path)["items"] if isinstance(it, dict)}
    L = load_live(live_path)
    touched = []
    for cid in sorted(dec):
        d = dec[cid]
        it = items.get(cid)
        if d.get("dec") != "trial" or not it or it.get("need") is not None:
            continue
        try:
            daily = current_daily(it, X)
            hold = _hold_daily(it["mk"])
        except Exception as e:                            # noqa: BLE001
            log(f"[候選試用] {cid} 算不出來：{type(e).__name__}: {e}")
            continue
        days = sorted(x for x in daily if x > str(d.get("d") or ""))
        if not days:
            continue
        rec = L["items"].setdefault(cid, {})
        n = append_live(rec, daily, hold, days[0])
        if n:
            touched.append(cid)
            log(f"[候選試用] {cid} 多記 {n} 天（從 {rec['start']} 起共 {len(rec['r'])} 天）")
    return L, touched


def save_live(L: dict, path: Path | None = None) -> bool:
    p = path or LIVE
    L = {"v": 1, "items": L.get("items") or {}}
    txt = json.dumps(_clean(L), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if p.exists() and p.read_text(encoding="utf-8") == txt:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")
    return True
