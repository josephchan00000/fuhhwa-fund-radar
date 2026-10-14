"""籌碼雷達：被動 ETF 指數調整（2026-10-14 使用者：「被動預計換的時間、依選股邏輯可能加入或踢除的個股」）。

兩條線：
  1. **公告前預測**——只對做得準的指數做。第一階段＝臺灣50（只看總市值排名，資料已在 mkt 分片）。
     00919／00929（中信心）、0056 代理（中低）為後續階段；00878（ESG 付費）不預測。
  2. **公告後／換股中追蹤**——所有被動 ETF（含擴充檔）：從每日持股揭露看新進／出清與真加減碼，
     彙整成「被動資金正在買賣什麼」；不依賴任何規則推測。

審核時程與歷次結果在 `config/index_reviews.json`（人工查證、兩來源一致才寫）。
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date

from . import ledger as LG
from . import store, ta

CFG = store.ROOT / "config" / "index_reviews.json"
TW50_IN, TW50_OUT, TW50_N = 40, 61, 50


def load_cfg() -> dict:
    try:
        return json.loads(CFG.read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return {}


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _common_tw(code: str) -> bool:
    """上市普通股：4 碼純數字、非 ETF（00 開頭）、非 TDR（91xx）。"""
    return len(code) == 4 and code.isdigit() and not code.startswith("00") and not code.startswith("91")


def _issued_twse(D) -> dict[str, int]:
    _, xt = D.latest("x_tw")
    return {c: q[1] for c, q in xt.items() if q and len(q) > 1 and q[1]}


def caps_at(D, d: str, issued: dict[str, int]) -> list[tuple[str, float, float]]:
    """某日上市普通股總市值排名 [(code, 市值, 收盤)]（發行股數用最新值——審核日前後股本變動極少）。
    排除創新板（名稱以「-創」結尾；2026-10-14 回測 9 月審核時 6949 被誤列納入）。"""
    doc = D.mkt.get(d) or {}
    q = dict(doc.get("q_tw") or {})
    if not q:                                    # 官方缺這天 → Yahoo 備援（只取上市檔）
        for c, ser in D.yh.items():
            y = ser.get(d)
            if y and D.yh_m.get(c) == "tw":
                q[c] = [y[0], y[1], y[2], y[3], y[4], None]
    xt = doc.get("x_tw") or {}
    out = []
    for c, row in q.items():
        if not _common_tw(c) or not row or not row[3]:
            continue
        if str(D.names.get(c, "")).endswith("-創"):
            continue
        iss = (xt.get(c) or [None, None])[1] or issued.get(c)
        if iss:
            out.append((c, row[3] * iss, row[3]))
    out.sort(key=lambda x: -x[1])
    return out


def _nearest_mkt_on_or_before(D, d: str) -> str | None:
    ds = [x for x in sorted(D.mkt) if x <= d and (D.mkt[x] or {}).get("q_tw")]
    yi = [x for x in (D.yh.get("TWII") or {}) if x <= d]
    best = max(ds[-1:] + sorted(yi)[-1:], default=None)
    return best


def listing_dates(ix: dict) -> dict[str, str]:
    """{代號: 上市日}：證交所基本資料落檔（CI 抓）＋設定檔人工註記（有來源，優先）。"""
    out = {}
    try:
        from .. import stockmeta
        out.update(stockmeta.listing_dates())
    except Exception:                                     # noqa: BLE001
        pass
    for c, v in (ix.get("listing") or {}).items():
        if isinstance(v, dict) and v.get("date"):
            out[c] = v["date"]
    return out


def not_listed(ranked: list[tuple], cons: set[str], listed: dict[str, str], cutoff: str) -> set[str]:
    """資料截止日時還沒在證交所上市的非成分股（興櫃轉上市要等上市後才有資格）。
    2026-10-14 回測：鴻勁 2025-11-27 才轉上市，2025-09／12 兩次都被誤列預估納入；排除後 8 次全對。"""
    return {c for c, _, _ in ranked[:TW50_OUT] if c not in cons and (listed.get(c) or "") > cutoff}


def tw50_select(ranked: list[tuple], cons: set[str], skip: set[str] | None = None) -> tuple[list[str], list[str]]:
    """依規則推出 (納入, 刪除)。固定 50 檔：納入多於刪除時，剔除排名最後的留任成分股；反之由最高排名非成分股遞補。
    skip＝不具資格的非成分股（例：截止日時尚未上市），排名照算、但不會被選入。"""
    if skip:
        ranked = [r for r in ranked if r[0] not in skip]
    rank = {c: i + 1 for i, (c, _, _) in enumerate(ranked)}
    adds = [c for c, _, _ in ranked[:TW50_IN] if c not in cons]
    dels = [c for c in cons if rank.get(c, 10 ** 6) >= TW50_OUT]
    keep = [c for c in cons if c not in dels]
    n_after = len(keep) + len(adds)
    if n_after > TW50_N:
        extra = sorted(keep, key=lambda c: -rank.get(c, 10 ** 6))[:n_after - TW50_N]
        dels += extra
    elif n_after < TW50_N:
        pool = [c for c, _, _ in ranked if c not in cons and c not in adds]
        adds += pool[:TW50_N - n_after]
    return adds, dels


def _sigma(D, code: str) -> float:
    c = [((D.mkt.get(d) or {}).get("q_tw") or {}).get(code) for d in D.cal[-61:]]
    px = [r[3] for r in c if r and r[3]]
    rets = [math.log(b / a) for a, b in zip(px, px[1:]) if a and b]
    s = statistics.pstdev(rets) if len(rets) >= 20 else 0.03
    return max(s, 0.008) * math.sqrt(2)          # 相對門檻股的波動 ≈ √2 倍個股波動


def _trading_days_between(a: date, b: date) -> int:
    from .. import twholidays
    n, d = 0, a
    while d < b:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5 and twholidays.is_closed(d) is not True:
            n += 1
    return n


def _etf_equity(D, etf: str) -> tuple[float, dict]:
    """ETF 股票部位總值（股數×收盤）與持股 {code: shares}——以最新揭露為準。"""
    for d, doc in reversed(D.pos):
        ent = (doc.get("etf") or {}).get(etf)
        if ent:
            h = {c: v[0] for c, v in (ent.get("h") or {}).items() if v and v[0]}
            tot = 0.0
            for c, s in h.items():
                p = D.price(c, d)
                if p and p[1]:
                    tot += s * p[1]
            return tot, h
    return 0.0, {}


def tw50(D, cfg: dict, today: date, names: dict) -> dict:
    ix = (cfg.get("indexes") or {}).get("tw50") or {}
    nxt = ix.get("next") or {}
    etfs = ix.get("etfs") or ["0050", "006208"]
    issued = _issued_twse(D)
    last = _nearest_mkt_on_or_before(D, today.isoformat())
    cutoff = nxt.get("cutoff")
    # 截止日已過且有該日資料 → 用截止日排名（就是指數公司用的那天），結果近乎確定
    use = last
    frozen = False
    if cutoff and last and last >= cutoff:
        cd = _nearest_mkt_on_or_before(D, cutoff)
        if cd:
            use, frozen = cd, True
    if not use:
        return {"ok": False, "why": "尚無價量分片"}
    ranked = caps_at(D, use, issued)
    _, h0050 = _etf_equity(D, etfs[0])
    cons = {c for c in h0050 if _common_tw(c) or (len(c) == 4 and c.isdigit())}
    if len(ranked) < 200 or len(cons) < 40:
        return {"ok": False, "why": f"資料不足（排名 {len(ranked)} 檔、成分股 {len(cons)} 檔）"}
    listed = listing_dates(ix)
    skip = not_listed(ranked, cons, listed, cutoff or use)
    ranked = [r for r in ranked if r[0] not in skip]
    rank = {c: i + 1 for i, (c, _, _) in enumerate(ranked)}
    cap = {c: v for c, v, _ in ranked}
    px = {c: p for c, _, p in ranked}
    adds, dels = tw50_select(ranked, cons)
    ui = D.ix.get(use)
    top = top_half(adds, {c: momentum(D, c, ui) for c in adds} if ui is not None else {})
    n_days = 0 if frozen or not cutoff else _trading_days_between(today, date.fromisoformat(cutoff))
    cap40 = ranked[TW50_IN - 1][1]
    cap60 = ranked[TW50_OUT - 2][1]

    # 被動部位（各追蹤 ETF 現值）與自由流通代理：成分股 權重/市值 的中位數
    eq = {}
    held = {}
    for e in etfs:
        tot, h = _etf_equity(D, e)
        eq[e] = tot
        held[e] = h
    wts = {}
    for d, doc in reversed(D.pos):
        ent = (doc.get("etf") or {}).get(etfs[0])
        if ent:
            wts = {c: (v[1] or 0) for c, v in (ent.get("h") or {}).items() if v}
            break
    ffk = [wts[c] / cap[c] for c in cons if c in cap and wts.get(c) and 25 <= rank.get(c, 0) <= 55]
    ff_med = statistics.median(ffk) if ffk else None
    avgv = {}

    def _avgvol(c):
        if c not in avgv:
            v = [((D.mkt.get(d) or {}).get("q_tw") or {}).get(c) for d in D.cal[-20:]]
            v = [r[4] for r in v if r and r[4]]
            avgv[c] = sum(v) / len(v) if v else None
        return avgv[c]

    def row(c: str, side: str) -> list:
        r = rank.get(c)
        need = None
        if side == "add" and c in cap:
            need = cap40 / cap[c] - 1 if r and r > TW50_IN else 0.0
        elif side == "del" and c in cap:
            need = cap60 / cap[c] - 1 if r and r < TW50_OUT else 0.0
        prob = None
        if need is not None:
            if n_days == 0:
                prob = 1.0 if ((side == "add" and need <= 0) or (side == "del" and need >= 0)) else 0.0
            else:
                z = math.log(1 + need) / (_sigma(D, c) * math.sqrt(n_days)) if need > -1 else -99
                prob = (1 - _phi(z)) if side == "add" else _phi(z)
        if side == "add":
            w = cap.get(c, 0) * ff_med if ff_med else None
            sh = sum(eq[e] * w / 100 / px[c] for e in etfs) if w and px.get(c) else None
        else:
            sh = sum(held[e].get(c, 0) for e in etfs)
            sh = -sh if sh else None
        av = _avgvol(c)
        mo = momentum(D, c, ui) if ui is not None else None
        ld = listed.get(c)
        recent = ld if ld and cutoff and ld > _days_before(cutoff, 92) else None
        return [c, names.get(c, c), r, round(cap.get(c, 0) / 1e8), None if need is None else round(need * 100, 1),
                None if prob is None else round(prob * 100), None if sh is None else round(sh / 1000),
                round(abs(sh) / av, 1) if sh and av else None, px.get(c),
                None if mo is None else round(mo * 100, 1), recent, int(c in top)]

    watch_in = [c for c, _, _ in ranked[TW50_IN:TW50_IN + 12] if c not in cons and c not in adds]
    watch_out = [c for c in sorted(cons, key=lambda c: rank.get(c, 10 ** 6))
                 if TW50_N - 2 <= rank.get(c, 0) < TW50_OUT and c not in dels]
    return {
        "ok": True, "asof": use, "frozen": frozen, "n_days": n_days, "cutoff": cutoff,
        "adds": [row(c, "add") for c in adds], "dels": [row(c, "del") for c in dels],
        "watch_in": [row(c, "add") for c in watch_in[:8]],
        "watch_out": [row(c, "del") for c in watch_out[:8]],
        "eq": {e: round(v / 1e8) for e, v in eq.items()},
        "replay": tw50_replay(D, ix, h0050, issued),
        "skip": sorted(skip),
    }


def _days_before(d: str, n: int) -> str:
    return date.fromordinal(date.fromisoformat(d).toordinal() - n).isoformat()


def momentum(D, code: str, t: int | None, n: int = 40) -> float | None:
    """t 日收盤相對 n 個交易日前的漲幅（2026-10-14 歸因：同次審核裡，截止前 40 日漲最多的納入股，
    公告後也漲最多——4 次有 2 檔以上納入的審核全都如此）。"""
    if t is None or t < n:
        return None
    c = D.series(code)["c"]
    return c[t] / c[t - n] - 1 if c[t] and c[t - n] else None


def top_half(codes: list[str], mom: dict) -> set[str]:
    """漲勢前一半（無條件進位；只有 1 檔就是它）——2026-10-14 使用者定案的選股規則。"""
    if not codes:
        return set()
    ranked = sorted(codes, key=lambda c: -(mom.get(c) if mom.get(c) is not None else -9e9))
    return set(ranked[:(len(codes) + 1) // 2])


def tw50_pre_sets(D, ix: dict, h0050: dict) -> dict[str, set]:
    """各次審核「審核前」成分股：最近一次＝0050 生效日前一天的揭露持股；更早的以實際結果往回推
    （本次審核前 − 更早那次的納入 ＋ 其刪除）。揭露史晚於最近一次生效日時，從最新成分股一路往回推。"""
    hist = sorted((h for h in ix.get("history") or [] if h.get("effective") and (h.get("adds") or h.get("dels"))),
                  key=lambda h: h["effective"], reverse=True)
    out: dict[str, set] = {}
    pre = None
    for i, h in enumerate(hist):
        if pre is None:
            snap = None
            for d, doc in D.pos:
                ent = (doc.get("etf") or {}).get("0050")
                if ent and d < h["effective"]:  # 揭露日＝收盤後部位；生效日當天已換完，取前一個揭露
                    snap = {c for c in (ent.get("h") or {}) if len(c) == 4 and c.isdigit()}
            if not snap:
                snap = {c for c in h0050 if len(c) == 4 and c.isdigit()}
                for later in hist[:i]:
                    snap = (snap - set(later.get("adds") or [])) | set(later.get("dels") or [])
                snap = (snap - set(h.get("adds") or [])) | set(h.get("dels") or [])
            pre = snap
        out[h["review"]] = set(pre)
        nxt = hist[i + 1] if i + 1 < len(hist) else None
        if nxt:
            pre = (pre - set(nxt.get("adds") or [])) | set(nxt.get("dels") or [])
    return out


def tw50_predict_at(D, h: dict, pre: set, issued: dict, listed: dict, d: str | None = None):
    """以 d（預設＝該次資料截止日）的市值排名重跑規則 → (資料日, 預測納入, 預測刪除)；資料不足回 None。"""
    cd = _nearest_mkt_on_or_before(D, d or h.get("cutoff") or "")
    if not cd or not pre or len(pre) < 45:
        return None
    ranked = caps_at(D, cd, issued)
    if len(ranked) < 200:
        return None
    pa, pd = tw50_select(ranked, pre, not_listed(ranked, pre, listed, h.get("cutoff") or cd))
    return cd, pa, pd


def tw50_replay(D, ix: dict, h0050: dict, issued: dict) -> list[dict]:
    """用歷次審核的截止日價量重跑規則，對照實際結果（上線前先看命中率）。"""
    listed = listing_dates(ix)
    pres = tw50_pre_sets(D, ix, h0050)
    out = []
    for h in sorted(ix.get("history") or [], key=lambda h: h.get("effective") or "", reverse=True):
        if h.get("review") not in pres:
            continue
        rec = {"review": h.get("review"), "cutoff": h.get("cutoff"),
               "data": _nearest_mkt_on_or_before(D, h.get("cutoff") or ""),
               "act_add": h.get("adds") or [], "act_del": h.get("dels") or []}
        got = tw50_predict_at(D, h, pres[h["review"]], issued, listed)
        if got:
            _, pa, pd = got
            rec.update({"pred_add": pa, "pred_del": pd,
                        "hit_add": len(set(pa) & set(rec["act_add"])),
                        "hit_del": len(set(pd) & set(rec["act_del"]))})
        out.append(rec)
    return out


def passive_flows(D, L, meta: dict, names: dict, *, days: int = 10) -> list[list]:
    """所有被動 ETF 近 N 個交易日的「真加減碼＋新進／出清」，依個股彙整（張、占 20 日均量倍數）。"""
    recent = set(D.cal[-days:])
    agg: dict[str, dict] = {}
    for ev in L.events:
        m = meta.get(ev.etf) or {}
        if m.get("k") != "p" or ev.date not in recent or not LG.is_tw(ev.code):
            continue
        if ev.kind == LG.HOLD:
            continue
        a = agg.setdefault(ev.code, {"sh": 0.0, "etfs": set(), "new": set(), "exit": set()})
        a["sh"] += ev.conv if ev.kind != LG.EXIT else -ev.s0
        a["etfs"].add(ev.etf)
        if ev.kind == LG.NEW:
            a["new"].add(ev.etf)
        if ev.kind == LG.EXIT:
            a["exit"].add(ev.etf)
    out = []
    for c, a in agg.items():
        vs = [((D.mkt.get(d) or {}).get("q_tw") or (D.mkt.get(d) or {}).get("q_tp") or {}).get(c) for d in D.cal[-20:]]
        vs = [r[4] for r in vs if r and r[4]]
        av = sum(vs) / len(vs) if vs else None
        out.append([c, names.get(c, c), round(a["sh"] / 1000), round(a["sh"] / av, 2) if av else None,
                    sorted(a["new"]), sorted(a["exit"]), sorted(a["etfs"])])
    out.sort(key=lambda x: -abs(x[2]))
    return out[:40]


def calendar(cfg: dict, today: date) -> list[list]:
    rows = []
    for key, ix in (cfg.get("indexes") or {}).items():
        n = ix.get("next") or {}
        eff = n.get("effective")
        dd = (date.fromisoformat(eff) - today).days if eff else None
        rows.append([key, ix.get("short") or ix.get("name"), ix.get("etfs"), n.get("review"), n.get("cutoff"), n.get("announce"),
                     eff, n.get("transition"), n.get("status"), ix.get("conf"), dd, ix.get("rule"),
                     bool(ix.get("predict")), (ix.get("history") or [])[:1]])
    rows.sort(key=lambda r: r[6] or "9999")
    return rows


def run(D, L, meta: dict, today: date) -> dict:
    cfg = load_cfg()
    names = D.names
    out = {"cal": calendar(cfg, today), "pflow": passive_flows(D, L, meta, names)}
    try:
        out["tw50"] = tw50(D, cfg, today, names)
    except Exception as e:                                # noqa: BLE001
        out["tw50"] = {"ok": False, "why": f"{type(e).__name__}: {e}"}
    try:                                                  # 臺灣50 換股研究（預測準度、進場時點、歸因）
        from . import tw50study
        out["study"] = tw50study.run(D, cfg)
    except Exception as e:                                # noqa: BLE001
        out["study"] = {"n": 0, "err": f"{type(e).__name__}: {e}"}
    return out
