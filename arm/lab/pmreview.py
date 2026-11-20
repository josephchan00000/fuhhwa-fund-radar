"""盤前自我檢討（規格 arm/lab/pmrevspec.py VER 1；docs/lab_premarket_plan.md 第 17 節）。全部在 CI 算、不連網、不花 token。

  record(log, pm, now)  → premkt.json 這一版記成「下一個交易日公布的那一版」（那一天 08:45 以前才記，之後不改）
  update(log, today)    → 有實際（那一天的 5 秒指數）的日子算檢討、近 N 天統計、警示、影子版本 R1
  push_line(log, last)  → 06:35 推播一行（arm/lab/valog.py 帶進 push 欄）；檢討的日子不是 last 就不帶
  noise5(days)          → 開盤第一小時任一個 5 分鐘的高低差（中位數、八成）；參考點位實話版那一句用
LOG＝data/lab/fut/pmreview.json：{"ver", "fp", "pub": {日: 公布的那一版}, "rev": {日: 檢討}, "sum": 近 N 天統計}
scripts/run_premkt.py 寫完 premkt.json 之後叫 run()；第一次的紀錄由 scripts/run_pmreview.py --backfill 從 git 歷史補。
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime
from pathlib import Path

from . import pmrevspec as S

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "data" / "lab" / "fut" / "pmreview.json"


def read() -> dict:
    try:
        doc = json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    return {"ver": S.VER, "fp": S.fingerprint(), "pub": doc.get("pub") or {}, "rev": doc.get("rev") or {}, "sum": doc.get("sum") or {}}


def write(log: dict) -> bool:
    """內容沒變不改寫（git diff 小）；一天一行。"""
    def block(d):
        return "{\n" + ",\n".join(json.dumps(k) + ":" + json.dumps(d[k], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                                  for k in sorted(d)) + "\n}"
    txt = ('{"ver":' + json.dumps(log["ver"]) + ',"fp":' + json.dumps(log["fp"]) + ',\n"pub":' + block(log["pub"]) +
           ',\n"rev":' + block(log["rev"]) + ',\n"sum":' + json.dumps(log["sum"], ensure_ascii=False, sort_keys=True) + "}\n")
    if LOG.exists() and LOG.read_text(encoding="utf-8") == txt:
        return False
    LOG.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOG.with_suffix(".tmp")
    tmp.write_text(txt, encoding="utf-8")
    tmp.replace(LOG)
    return True


def snap(pm: dict) -> dict | None:
    """premkt.json → 公布的那一版要記的欄位；沒有預估或正常波動就不記。"""
    v = pm.get("v") or {}
    if pm.get("est") is None or not pm.get("em"):
        return None
    bands = [[round(b["lo"]), round(b["hi"]), round(b["touch"], 3)] for b in pm.get("bands") or []
             if b.get("touch") is not None and b.get("side") in ("up", "dn")]
    return {"est": round(pm["est"]), "em": round(pm["em"]), "typ": v.get("typ"), "p80": v.get("p80"), "src": pm.get("est_src") or "",
            "made": pm.get("made") or "", "bands": bands}


def record(log: dict, pm: dict, now: datetime) -> bool:
    """那一天 FREEZE 以前才記（之後的重算不改公布的那一版）。"""
    d = pm.get("next")
    if not d or now.strftime("%Y-%m-%d %H:%M") >= f"{d} {S.FREEZE}":
        return False
    s = snap(pm)
    if s is None or log["pub"].get(d) == s:
        return False
    log["pub"][d] = s
    return True


def actual(d: str) -> dict | None:
    """那一天 09:01 的 5 秒指數、09:00:05 起最高最低（和 premkt.checks 同一個口徑）。"""
    from . import futdata as F
    from .premktspec import OPEN_T
    v = F.load_idx(d)
    if not v or len(v) <= OPEN_T:
        return None
    return {"open": round(v[OPEN_T]), "hi": round(max(v[1:])), "lo": round(min(v[1:]))}


def one(p: dict, a: dict, e850: dict | None) -> dict:
    """一天的檢討（規格第 3 點）。"""
    err = a["open"] - p["est"]
    r = {"est": p["est"], "open": a["open"], "hi": a["hi"], "lo": a["lo"], "em": p["em"], "p80": p["p80"],
         "err": err, "x": round(abs(err) / p["em"], 3), "rng": round((a["hi"] - a["lo"]) / p["em"], 3)}
    r["in"] = None if not p.get("p80") else abs(err) <= p["p80"]
    if e850 and e850.get("est") is not None:
        r["e850"] = round(e850["est"])
        r["seg"] = [r["e850"] - p["est"], a["open"] - r["e850"]]          # 夜盤收盤後到 08:45、08:45 到 09:01
    r["touch"] = [[b[2], a["lo"] <= b[1] and a["hi"] >= b[0]] for b in p.get("bands") or []]
    return r


def _r1(prior: list[dict]) -> float | None:
    rng = [r["rng"] for r in prior if r.get("rng") is not None]
    if not rng:
        return None
    lo, hi = S.R1_CLAMP
    return min(max(st.median(rng) / S.RANGE_NORM, lo), hi)


def update(log: dict, e850log: dict | None = None, act=actual) -> bool:
    """有實際的日子算檢討（已經算過、輸入沒變就不動），再算近 N 天統計與警示。"""
    e850log = e850log or {}
    days = sorted(log["pub"])
    changed = False
    for d in days:
        a = act(d)
        if not a:
            continue
        r = one(log["pub"][d], a, e850log.get(d))
        prior = [log["rev"][k] for k in sorted(log["rev"]) if k < d][-S.N:]
        f = _r1(prior)
        if f is not None and r.get("p80"):
            r["r1"] = round(r["p80"] * f)
            r["r1_in"] = abs(r["err"]) <= r["r1"]
        if log["rev"].get(d) != r:
            log["rev"][d] = r
            changed = True
    s = summary(log)
    if log["sum"] != s:
        log["sum"] = s
        changed = True
    return changed


def summary(log: dict) -> dict:
    ks = sorted(log["rev"])[-S.N:]
    rs = [log["rev"][k] for k in ks]
    if not rs:
        return {}
    ins = [r["in"] for r in rs if r.get("in") is not None]
    tch = [t for r in rs for t in r.get("touch") or []]
    out = {"n": len(rs), "from": ks[0], "to": ks[-1], "in": sum(ins), "n_in": len(ins),
           "x_med": round(st.median(r["x"] for r in rs), 3), "rng_med": round(st.median(r["rng"] for r in rs), 3),
           "touch_n": len(tch), "touch_said": round(st.mean(t[0] for t in tch), 3) if tch else None,
           "touch_got": round(sum(t[1] for t in tch) / len(tch), 3) if tch else None}
    r1 = [r for r in rs if r.get("r1") is not None]
    if r1:
        out["r1"] = {"n": len(r1), "in": sum(r["r1_in"] for r in r1), "w": round(st.mean(r["r1"] / r["p80"] for r in r1), 3)}
    warn = []
    if len(rs) >= S.MIN_DAYS and ins:
        c = sum(ins) / len(ins)
        if c < S.COVER_LO:
            warn.append(f"範圍太窄（八成範圍只包住 {c:.0%}）")
        elif c > S.COVER_HI:
            warn.append(f"範圍太寬（八成範圍包住 {c:.0%}）")
        if out["rng_med"] > S.RANGE_WARN:
            warn.append(f"最近實際晃得比正常波動大（當天高低差是正常波動的 {out['rng_med']:.1f} 倍，常態約 {S.RANGE_NORM} 倍）")
        if len(tch) >= S.TOUCH_MIN and abs(out["touch_got"] - out["touch_said"]) > S.TOUCH_WARN:
            warn.append(f"碰到的比例失準（頁面說 {out['touch_said']:.0%}、實際 {out['touch_got']:.0%}）")
    out["warn"] = warn[:2]
    out["switch"] = switch_ok(out)
    return out


def switch_ok(s: dict) -> bool:
    """影子版本 R1 的換版條件（規格第 6 點）；過了也只寫「可以考慮換」。"""
    r1 = s.get("r1") or {}
    if r1.get("n", 0) < S.SWITCH_MIN or not s.get("n_in"):
        return False
    c1, c0 = r1["in"] / r1["n"], s["in"] / s["n_in"]
    return (S.SWITCH_R1[0] <= c1 <= S.SWITCH_R1[1] and not (S.SWITCH_LIVE_OK[0] <= c0 <= S.SWITCH_LIVE_OK[1])
            and r1["w"] <= S.SWITCH_WIDTH)


def _n(x) -> str:
    return f"{x:,.0f}"


def _sg(x) -> str:
    return f"+{x:,.0f}" if x > 0 else f"−{abs(x):,.0f}" if x < 0 else "0"


def reason(r: dict) -> str:
    """主因（規格第 3 點）：拆兩段時寫大的那一段；沒有重估就只寫差多少。"""
    seg = r.get("seg")
    if not seg:
        return "沒有 08:46 重估，拆不出是哪一段"
    a, b = seg
    if abs(a) >= abs(b):
        return f"夜盤收盤後到 08:45 台指期又{'漲' if a > 0 else '跌'} {_n(abs(a))} 點"
    return f"08:45 到 09:01 又{'漲' if b > 0 else '跌'} {_n(abs(b))} 點"


def push_line(log: dict, last: str) -> str | None:
    """06:35 推播一行；最新的檢討日不是 last（最新資料日）就不帶。"""
    if not log["rev"]:
        return None
    d = max(log["rev"])
    if d != last:
        return None
    r, s = log["rev"][d], log["sum"]
    m = f"{int(d[5:7])}/{int(d[8:10])}"
    where = "在八成範圍內" if r.get("in") else "超出八成範圍" if r.get("in") is False else ""
    txt = (f"盤前檢討（{m}）：估 {_n(r['est'])}、實際 {_n(r['open'])}，差 {_sg(r['err'])}（{r['x']:.2f} 倍正常波動" +
           (f"，{where}" if where else "") + f"）；主因：{reason(r)}。")
    if s.get("n_in"):
        txt += f"近 {s['n']} 天八成範圍包住 {s['in']} 天"
        txt += ("；" + "；".join(s["warn"]) if s.get("warn") else "") + "。"
    if s.get("switch"):
        txt += "範圍放大版達到換版條件，可以考慮換，回「好」才換。"
    return txt


def noise5(days: list[str]) -> dict | None:
    """最近這幾天開盤第一小時（09:01～10:00），任一個 5 分鐘的高低差（每分鐘起算一次）：中位數、八成。"""
    from . import futdata as F
    from .premktspec import OPEN_T
    rs = []
    for d in days:
        v = F.load_idx(d)
        if not v or len(v) < OPEN_T + 12 * 60:
            continue
        p = v[OPEN_T:OPEN_T + 12 * 60]
        rs += [max(p[i:i + 60]) - min(p[i:i + 60]) for i in range(0, len(p) - 60, 12)]
    if not rs:
        return None
    rs.sort()
    return {"n": len(days), "med": round(st.median(rs)), "p80": round(rs[int(0.8 * (len(rs) - 1))])}


def run(pm: dict | None, now: datetime) -> dict:
    """scripts/run_premkt.py 寫完 premkt.json 之後叫：記公布的那一版＋算檢討；回傳 LOG。"""
    from . import pm850
    log = read()
    if pm:
        record(log, pm, now)
    try:
        e850 = json.loads(pm850.LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        e850 = {}
    update(log, e850)
    write(log)
    return log
