"""籌碼雷達：落檔驅動（ETF 部位快照＋官方市場分片＋集保週表）。

冪等：每輪只抓「缺的部件」，資料齊的日子零請求——多班次重跑不放大來源站請求。
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import date, timedelta

from .. import clock, twholidays
from . import market, store

HOLD_FP = store.ROOT / "data" / "etf_holdings.json"
NODATA = "mkt_nodata.json"         # {date: [part,…]}：官方明示查無（休市／早於資料起點）→ 不再重試


# ── ETF 部位快照（pos） ─────────────────────────────────────────────

def _bond_etfs() -> set[str]:
    try:
        from .. import etfwatch
        return {t[0] for t in etfwatch.watch_tuples() if "債" in (t[3] or "")}
    except Exception:                                     # noqa: BLE001
        return {"00986D", "00987D"}


def snaps_from_holdings(doc: dict, *, skip: set[str] | None = None) -> dict:
    """etf_holdings.json → {date: {etf: {"src", "h": {code: [股數, 權重]}, "px": {code: [收盤, 幣別]}}}}。
    當期快照記 cur=True；前一揭露日（prev）只用來補缺、不覆蓋（cur=False）。"""
    skip = skip if skip is not None else _bond_etfs()
    out: dict[str, dict] = {}
    for etf, e in (doc.get("etfs") or {}).items():
        if etf in skip or not isinstance(e, dict):
            continue
        d = e.get("date")
        if d and e.get("holdings"):
            h = {}
            for r in e["holdings"]:
                sid = str(r.get("stock_id") or "").strip()
                if sid and r.get("shares") is not None:
                    h[sid] = [r.get("shares"), r.get("weight")]
            px = {}
            det = e.get("detail") or {}
            # 收盤要是「揭露當天」的：2026-10-21 起明細的收盤是報價日 pd（最新交易日）那天的，
            # 持股快照較舊時 pd≠d → 不收（舊格式沒有 pd，照舊）。docs/etf_chg_fix_plan.md
            if det.get("date") == d and det.get("pd", d) == d:
                for r in det.get("all") or []:
                    sid = str(r.get("stock_id") or "").strip()
                    if sid and r.get("close") is not None:
                        px[sid] = [r.get("close"), r.get("ccy")]
            if h:
                out.setdefault(d, {})[etf] = {"src": e.get("src"), "h": h, "px": px, "cur": True}
        pd, prev = e.get("prev_date"), e.get("prev") or {}
        if pd and prev:
            h = {sid: [v.get("shares"), v.get("weight")] for sid, v in prev.items()
                 if isinstance(v, dict) and v.get("shares") is not None}
            if h:
                out.setdefault(pd, {}).setdefault(etf, {"src": e.get("prev_src"), "h": h,
                                                        "px": {}, "cur": False})
    return out


def names_from_holdings(doc: dict) -> dict[str, str]:
    out = {}
    for e in (doc.get("etfs") or {}).values():
        for r in (e or {}).get("holdings") or []:
            sid, nm = str(r.get("stock_id") or "").strip(), r.get("name")
            if sid and nm and nm != sid:
                out[sid] = nm
        for sid, v in ((e or {}).get("prev") or {}).items():
            if isinstance(v, dict) and v.get("name") and sid not in out:
                out[sid] = v["name"]
    return out


def merge_snaps(snaps: dict) -> int:
    """寫進 pos 分片：當期快照覆蓋同日同 ETF；prev 只補缺。回傳變動分片數。"""
    n = 0
    for d, etfs in sorted(snaps.items()):
        doc = store.read("pos", d) or {"date": d, "etf": {}}
        cur = doc.setdefault("etf", {})
        for etf, ent in etfs.items():
            is_cur = ent.pop("cur", False)
            if is_cur or etf not in cur:
                if not ent.get("px") and etf in cur and cur[etf].get("px"):
                    ent["px"] = cur[etf]["px"]            # 重抓時沒報價 → 沿用既有
                cur[etf] = ent
        if store.write("pos", d, doc):
            n += 1
    return n


def merge_names(new: dict[str, str]) -> None:
    old = store.read_json("names.json", {}) or {}
    old.update(new)
    store.write_json("names.json", old)


def update_pos_from_current() -> int:
    try:
        doc = json.loads(HOLD_FP.read_text(encoding="utf-8"))
    except Exception as e:                                # noqa: BLE001
        market.log(f"讀 etf_holdings.json 失敗：{e}")
        return 0
    merge_names(names_from_holdings(doc))
    return merge_snaps(snaps_from_holdings(doc))


def backfill_pos_from_git() -> int:
    """走 git 歷史裡每一版 etf_holdings.json 回補 pos 分片（CI 需 fetch-depth: 0）。"""
    try:
        shas = subprocess.run(["git", "log", "--reverse", "--format=%H", "--",
                               "data/etf_holdings.json"], cwd=store.ROOT, check=True,
                              capture_output=True, text=True).stdout.split()
    except Exception as e:                                # noqa: BLE001
        market.log(f"git log 失敗：{e}")
        return 0
    market.log(f"git 歷史 etf_holdings.json 共 {len(shas)} 版")
    acc: dict[str, dict] = {}
    names: dict[str, str] = {}
    skip = _bond_etfs()
    for sha in shas:
        try:
            txt = subprocess.run(["git", "show", f"{sha}:data/etf_holdings.json"],
                                 cwd=store.ROOT, check=True, capture_output=True,
                                 text=True).stdout
            doc = json.loads(txt)
        except Exception:                                 # noqa: BLE001
            continue
        names.update(names_from_holdings(doc))
        for d, etfs in snaps_from_holdings(doc, skip=skip).items():
            slot = acc.setdefault(d, {})
            for etf, ent in etfs.items():
                if ent["cur"] or etf not in slot:
                    if not ent.get("px") and etf in slot and slot[etf].get("px"):
                        ent["px"] = slot[etf]["px"]
                    slot[etf] = ent
    merge_names(names)
    n = merge_snaps(acc)
    market.log(f"pos 回補：{len(acc)} 個揭露日、更新 {n} 個分片")
    return n


# ── 官方市場分片（mkt） ─────────────────────────────────────────────

def candidate_days(today: date, n_cal: int) -> list[str]:
    """往回 n_cal 個日曆天內的「可能交易日」（平日、且官方表沒判休市）。新到舊。"""
    out = []
    for i in range(n_cal + 1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        if twholidays.is_closed(d) is True:
            continue
        out.append(d.isoformat())
    return out


def fill_market(days: list[str], parts_for, *, budget_s: float, today: date,
                verbose: bool = False) -> dict:
    """逐日補缺部件。parts_for(day)->要的部件清單。回傳統計。"""
    t0 = time.time()
    nod = store.read_json(NODATA, {}) or {}
    stat = {"fetched": 0, "nodata": 0, "err": 0, "days": 0}
    recent_cut = (today - timedelta(days=3)).isoformat()   # 近 3 天的查無＝可能尚未公布，不登記
    for d in days:
        if time.time() - t0 > budget_s:
            market.log(f"時間預算用完，停在 {d}（下輪續補）")
            break
        if "q_tw" in (nod.get(d) or []):                     # 主檔查無＝休市日，整天跳過
            continue
        want = [p for p in parts_for(d) if p not in (nod.get(d) or [])]
        doc = store.read("mkt", d) or {"date": d}
        miss = [p for p in want if p not in doc]
        if not miss:
            continue
        stat["days"] += 1
        changed = False
        for p in miss:
            data, st, extra = market.fetch_part(p, d)
            if data:
                doc[p] = data
                if extra:
                    doc.setdefault("idx", {}).update(extra)
                changed = True
                stat["fetched"] += 1
                if verbose:
                    market.log(f"{d} {p} ✓ {len(data)} 檔")
            elif st.startswith("nodata"):
                stat["nodata"] += 1
                if d < recent_cut:
                    nod.setdefault(d, [])
                    if p not in nod[d]:
                        nod[d].append(p)
                if verbose:
                    market.log(f"{d} {p} 查無（{st}）")
                # 主檔查無＝當天休市（或尚未公布）→ 同日其他部件不必再打
                if p in ("q_tw", "i_tw"):
                    break
            else:
                stat["err"] += 1
                market.log(f"{d} {p} ✗ {st}")
        if changed:
            store.write("mkt", d, doc)
    store.write_json(NODATA, {k: sorted(v) for k, v in sorted(nod.items())})
    if market.NAMES:
        nm = store.read_json("names_mkt.json", {}) or {}
        nm.update({k: v for k, v in market.NAMES.items() if v})
        store.write_json("names_mkt.json", nm)
    return stat


def update_tdcc() -> bool:
    last = store.dates("tdcc")
    if last and (clock.today_tw() - date.fromisoformat(last[-1])).days < 6:
        return False
    iso, data = market.fetch_tdcc()
    if not iso or len(data) < 1000:
        return False
    store.write("tdcc", iso, {"date": iso, "s": data})
    market.log(f"TDCC 股權分散表 {iso}：{len(data)} 檔")
    return True


def prune_all(today: date) -> None:
    for k in ("mkt", "pos", "tdcc"):
        store.prune(k, today=today)


# ── 擴充 ETF（2026-10-14 使用者：「別的規模大的 ETF 也可以納入」） ─────────
# 只進籌碼雷達（pos 分片＋data/lab/extra_etfs.json），**不碰主頁策展的 ETF 追蹤表**。
# 每輪自 etfinfo 全清單依規模挑台股權益型（主動＋被動）前 N 大，未追蹤者才抓持股。

EXTRA_FP = "extra_etfs.json"
EXTRA_TOP = 45          # 依規模取前 45 名候選（含已追蹤者），篩完通常剩 20～30 檔
EXTRA_MAX = 30
EXTRA_TW_SHARE = 0.7    # 台股權重 ≥70% 才算台股權益型（排除海外指數、債券、期貨型）
STALE_DAYS = 10         # 擴充檔快照比已追蹤 ETF 最新揭露日舊超過 10 天 → 不收
_BAD_SUFFIX = ("B", "L", "R", "U", "K", "D", "C")   # 債券／槓桿／反向／期貨／海外等字尾


def _pick(d: dict, *keys):
    for k in keys:
        for kk, v in d.items():
            if kk.lower() == k.lower() and v not in (None, ""):
                return v
    return None


def _aum(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def extra_candidates(items: list[dict], tracked: set[str]) -> list[dict]:
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        code = str(_pick(it, "code", "symbol", "stockId", "id") or "").strip()
        if not market.CODE_RE.match(code) or not code.startswith("00"):
            continue
        if code[-1].isalpha() and code[-1] in _BAD_SUFFIX:
            continue
        # 2026-10-14 正式環境首輪：etfinfo 清單的規模在 latestMarket.aum（頂層沒有 aum）→ 全部讀成 0、
        # 退化成依代碼排序，挑到 0051～0059 這批小型／已下市檔
        lm = it.get("latestMarket") if isinstance(it.get("latestMarket"), dict) else {}
        aum = _aum(_pick(it, "aum", "AUM", "fundSize", "size") or _pick(lm, "aum", "AUM"))
        style = str(_pick(it, "managementStyle", "style") or "").lower()
        out.append({"code": code, "aum": aum, "name": _pick(it, "name", "shortName") or code,
                    "style": "a" if style.startswith("act") or code.endswith("A") else "p",
                    "issuer": _pick(it, "issuer", "company")})
    out.sort(key=lambda x: -x["aum"])
    return [x for x in out[:EXTRA_TOP] if x["code"] not in tracked]


def update_extra_etfs(ref_date: str | None) -> int:
    """抓擴充 ETF 持股寫進 pos 分片。ref_date＝已追蹤 ETF 的最新揭露日；擴充檔已到此日就跳過。"""
    from ..connectors import etfinfo
    try:
        from .. import etfwatch
        tracked = {t[0] for t in etfwatch.watch_tuples()}
    except Exception:                                     # noqa: BLE001
        tracked = set()
    try:
        items = etfinfo.list_etfs()
    except Exception as e:                                # noqa: BLE001
        market.log(f"etfinfo 全清單失敗：{e}")
        return 0
    if items:
        market.log(f"etfinfo 全清單 {len(items)} 檔；首筆鍵名={list(items[0])[:16]}")
    cands = extra_candidates(items, tracked)
    if not cands:
        market.log("擴充 ETF 候選 0 檔（清單鍵名不符？見上行）")
        return 0
    meta = store.read_json(EXTRA_FP, {}) or {}
    etfs = meta.setdefault("etfs", {})
    last_pos = {}
    for d, doc in store.load("pos", last=12):
        for e in (doc.get("etf") or {}):
            last_pos[e] = d
    n = 0
    kept = 0
    for c in cands:
        if kept >= EXTRA_MAX:
            break
        code = c["code"]
        old = etfs.get(code)
        if old and old.get("skip"):
            continue                                       # 已判定非台股權益型
        if ref_date and last_pos.get(code, "") >= ref_date:
            kept += 1
            continue
        try:
            rows, m = etfinfo.holdings_fresh(code)
        except Exception as e:                            # noqa: BLE001
            market.log(f"擴充 {code} 持股失敗：{str(e)[:80]}")
            continue
        h = {r["stock_id"]: [r["shares"], r["weight"]] for r in rows if r.get("shares")}
        tot = sum(v[1] or 0 for v in h.values()) or 1
        tw = sum(v[1] or 0 for k, v in h.items() if k[:4].isdigit() and " " not in k) / tot
        d = str(m.get("as_of") or "")[:10]
        if len(h) < 10 or tw < EXTRA_TW_SHARE or not d:
            etfs[code] = {"n": c["name"], "skip": True, "why": f"{len(h)} 檔、台股權重 {tw:.0%}"}
            continue
        # 快照過舊＝停止揭露或已下市（首輪踩到 2019 年的快照被寫成分片）→ 不寫、下輪再看
        if ref_date and (date.fromisoformat(ref_date) - date.fromisoformat(d)).days > STALE_DAYS:
            market.log(f"擴充 {code} 快照 {d} 過舊，略過")
            continue
        etfs[code] = {"n": m.get("name") or c["name"], "k": c["style"],
                      "is": m.get("issuer") or c.get("issuer"), "aum": c["aum"]}
        merge_names({r["stock_id"]: r["stock_name"] for r in rows if r.get("stock_name")})
        n += merge_snaps({d: {code: {"src": "etfinfo", "h": h, "px": {}, "cur": True}}})
        kept += 1
    meta["as_of"] = ref_date
    store.write_json(EXTRA_FP, meta)
    market.log(f"擴充 ETF：候選 {len(cands)}、納入 {sum(1 for v in etfs.values() if not v.get('skip'))}、"
               f"本輪更新分片 {n}")
    return n


# ── 歷史價量備援（Yahoo，逐檔） ───────────────────────────────────────

def yh_codes() -> list[str]:
    d = store.LAB / "yh"
    return sorted(p.name.split(".json")[0] for p in d.glob("*.json.gz")) if d.exists() else []


def backfill_yahoo(*, top: int = 250, budget_s: float = 900, min_cap: float | None = None) -> int:
    """宇宙＝最新上市市值前 top＋所有 ETF 曾持有台股＋臺灣50 歷次異動股＋加權指數。已有者跳過。
    min_cap（元）有給時，另把上市櫃所有市值 ≥ min_cap 的普通股納入（長線成長股回測用）。"""
    import json as _json
    t0 = time.time()
    mk = dict(store.load("mkt", last=15))
    q_tw, q_tp, iss = {}, {}, {}
    for d in sorted(mk):
        q_tw.update(mk[d].get("q_tw") or {})
        q_tp.update(mk[d].get("q_tp") or {})
        for c, x in (mk[d].get("x_tw") or {}).items():
            if x and len(x) > 1 and x[1]:
                iss[c] = x[1]
    caps = sorted(((c, q[3] * iss[c]) for c, q in q_tw.items() if c in iss and q and q[3]
                   and len(c) == 4 and c.isdigit() and not c.startswith("00")), key=lambda x: -x[1])
    uni = {c for c, _ in caps[:top]}
    if min_cap:
        uni |= {c for c, v in caps if v >= min_cap}
        for c, q in q_tp.items():                      # 上櫃：發行股數在日收盤表第 7 欄
            if len(c) == 4 and c.isdigit() and q and q[3] and len(q) > 6 and q[6] \
                    and q[3] * q[6] >= min_cap:
                uni.add(c)
    for _, doc in store.load("pos"):
        for ent in (doc.get("etf") or {}).values():
            uni |= {c for c in (ent.get("h") or {}) if len(c) == 4 and c.isdigit()}
    try:
        cfg = _json.loads((store.ROOT / "config" / "index_reviews.json").read_text(encoding="utf-8"))
        for ix in (cfg.get("indexes") or {}).values():
            for h in ix.get("history") or []:
                uni |= set(h.get("adds") or []) | set(h.get("dels") or []) | set(h.get("reserve") or [])
    except Exception:                                     # noqa: BLE001
        pass
    have = set(yh_codes())
    todo = ["TWII"] + sorted(uni)
    n = 0
    for c in todo:
        if c in have:
            continue
        if time.time() - t0 > budget_s:
            market.log(f"Yahoo 時間預算用完（已補 {n} 檔，下輪續補）")
            break
        if c == "TWII":
            sufs = [("^TWII", "idx")]
        elif c in q_tp and c not in q_tw:
            sufs = [(c + ".TWO", "tp")]
        else:
            sufs = [(c + ".TW", "tw"), (c + ".TWO", "tp")]
        for sym, mkt in sufs:
            h = market.yahoo_hist(sym)
            time.sleep(0.6)
            if len(h) >= 20:
                store.write("yh", c, {"m": mkt, "q": h})
                n += 1
                break
    market.log(f"Yahoo 歷史日線：宇宙 {len(todo)} 檔、本輪新增 {n} 檔")
    return n


# ── 月營收（官方，每月一次）與營收歷史（FinMind，只抓長線候選股） ───────────

def update_revenue() -> bool:
    last = store.dates("rev")
    if last and (clock.today_tw() - date.fromisoformat(last[-1] + "-01")).days < 35:
        # 已有最近一個月；每月 10 日後才可能有新月份
        if clock.today_tw().day < 10 or last[-1] >= (clock.today_tw().replace(day=1) - timedelta(days=1)).strftime("%Y-%m"):
            return False
    ym, data = market.fetch_revenue()
    if not ym or len(data) < 1000:
        market.log(f"月營收解析偏少：{len(data)} 檔（{ym}）")
        return False
    store.write("rev", ym, {"ym": ym, "s": data})
    market.log(f"月營收 {ym}：{len(data)} 檔")
    return True


def _last_rev_month(today) -> tuple[int, int]:
    """今天可得的最新月營收月份：11 日起才有上個月（法定公告期限 10 日）。"""
    first = today.replace(day=1)
    last = first - timedelta(days=1)
    if today.day < 11:
        last = last.replace(day=1) - timedelta(days=1)
    return last.year, last.month


def backfill_rev_mops(start: str = "2020-01", *, budget_s: float = 1500, workers: int = 4) -> int:
    """全市場月營收歷史（S26，2026-10-15）：MOPS 營業收入彙總表，一個月四頁（上市／上櫃 × 國內／國外 KY），
    寫進同一個 rev 分片（{ym, s: {代號: [營收(千元), 年增%, 累計年增%]}}）。已有 ≥1000 檔的月份跳過，可重跑續補。
    彙總表一頁約 45 秒（伺服器傳得慢），同時抓 2 個月、4 個連線。"""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    have = {}
    for ym in store.dates("rev"):
        have[ym] = len((store.read("rev", ym) or {}).get("s") or {})
    ly, lm = _last_rev_month(clock.today_tw())
    y, m = int(start[:4]), int(start[5:7])
    todo = []
    while (y, m) <= (ly, lm):
        if have.get(f"{y:04d}-{m:02d}", 0) < 1000:
            todo.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    n = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), 2):
            if time.time() - t0 > budget_s:
                market.log(f"月營收歷史：時間預算用完，停在 {todo[i][0]:04d}-{todo[i][1]:02d}（本輪補 {n} 個月）")
                break
            grp = todo[i:i + 2]
            jobs = {(y, m, mkt, k): ex.submit(market.fetch_mops_rev, mkt, y, m, k)
                    for y, m in grp for k in (0, 1) for mkt in ("sii", "otc")}
            for y, m in grp:
                ym = f"{y:04d}-{m:02d}"
                data, ok = {}, True
                for mkt in ("sii", "otc"):
                    for k in (0, 1):
                        d = jobs[(y, m, mkt, k)].result()
                        if d is None and k == 0:
                            ok = False
                        data.update(d or {})
                if ok and len(data) >= 1000:
                    store.write("rev", ym, {"ym": ym, "s": data, "src": "mops"})
                    n += 1
                else:
                    market.log(f"月營收歷史 {ym}：解析 {len(data)} 檔，不寫入")
            time.sleep(1.0)
    market.log(f"月營收歷史（MOPS）：本輪新增 {n} 個月、累計 {len(store.dates('rev'))} 個月、"
               f"{time.time() - t0:.0f} 秒")
    return n


def backfill_rev_finmind(codes: list[str], *, start: str = "2020-01-01", budget_s: float = 2400) -> int:
    """全市場月營收歷史的備援（MOPS 彙總表抓不到時）：FinMind 逐檔，存 revf/{代號}（{r: {YYYY-MM: 營收(元)}}）。
    未登入每小時約 300 次，限流就停、下一輪續補；已有的跳過。"""
    t0 = time.time()
    d = store.LAB / "revf"
    have = {p.name.split(".json")[0] for p in d.glob("*.json.gz")} if d.exists() else set()
    n = 0
    for c in codes:
        if c in have:
            continue
        if time.time() - t0 > budget_s:
            market.log(f"月營收歷史（FinMind）：時間預算用完，停在 {c}")
            break
        rows = market.finmind("TaiwanStockMonthRevenue", c, start)
        time.sleep(1.2)
        if rows == market.FINMIND_LIMIT:
            market.log(f"月營收歷史（FinMind）：被限流，停在 {c}（本輪補 {n} 檔）")
            break
        r = {f"{int(x['revenue_year']):04d}-{int(x['revenue_month']):02d}": float(x["revenue"])
             for x in rows or [] if x.get("revenue_year") and x.get("revenue_month") and x.get("revenue")}
        store.write("revf", c, {"r": r})                 # 空的也寫：代表查過、沒有資料，下一輪不重打
        n += 1
    market.log(f"月營收歷史（FinMind）：候選 {len(codes)} 檔、本輪新增 {n}、累計 {len(have) + n}")
    return n


def backfill_rev_hist(codes: list[str], *, budget_s: float = 1200) -> int:
    t0 = time.time()
    have = set()
    d = store.LAB / "revh"
    if d.exists():
        have = {p.name.split(".json")[0] for p in d.glob("*.json.gz")}
    n = fail = 0
    for c in codes:
        if c in have:
            continue
        if time.time() - t0 > budget_s or fail >= 5:
            market.log(f"營收歷史：停在 {c}（已補 {n} 檔；失敗 {fail}）")
            break
        r = market.finmind_revenue(c)
        time.sleep(1.2)
        if r:
            store.write("revh", c, {"r": r})
            n += 1
            fail = 0
        else:
            fail += 1
    market.log(f"營收歷史（FinMind）：候選 {len(codes)} 檔、本輪新增 {n}")
    return n


# ── 高股息研究資料：股利（證交所逐年＋上櫃 FinMind）與單季 EPS（FinMind），可重跑續補 ───────────

def hd_universe(n: int = 320) -> list[str]:
    """最新一天上市＋上櫃普通股市值前 n 名（高股息指數母體都在這裡面：00919 前 300、00929 科技前 200、0056 前 150）。
    上市發行股數（MI_QFIIS）不是每天都有 → 往前找最近一份。"""
    q_tw = q_tp = x_tw = None
    for d in reversed(store.dates("mkt")):
        doc = store.read("mkt", d) or {}
        q_tw = q_tw or doc.get("q_tw")
        q_tp = q_tp or doc.get("q_tp")
        x_tw = x_tw or doc.get("x_tw")
        if q_tw and q_tp and x_tw:
            break
    caps = {}
    for c, r in (q_tw or {}).items():
        iss = ((x_tw or {}).get(c) or [None, None])[1]
        if r and r[3] and iss:
            caps[c] = r[3] * iss
    for c, r in (q_tp or {}).items():
        if r and r[3] and len(r) > 6 and r[6]:
            caps[c] = r[3] * r[6]
    ok = [c for c in caps if len(c) == 4 and c.isdigit() and not c.startswith("00") and not c.startswith("91")]
    return sorted(ok, key=lambda c: -caps[c])[:n]


def _hd_cfg_codes() -> set[str]:
    """設定檔裡高股息指數歷次納入／刪除過的股票（小型股可能掉出市值前 N，回放時仍要有資料）。"""
    try:
        cfg = json.loads((store.ROOT / "config" / "index_reviews.json").read_text(encoding="utf-8"))
    except Exception:                                     # noqa: BLE001
        return set()
    out = set()
    for k in ("tw_div", "msci_esg30", "tip_hd", "tip_tech"):
        for h in ((cfg.get("indexes") or {}).get(k) or {}).get("history") or []:
            out |= {c for c in (h.get("adds") or []) + (h.get("dels") or []) if len(c) == 4 and c.isdigit()}
    return out


def yhl_codes() -> list[str]:
    d = store.LAB / "yhl"
    return sorted(p.name.split(".json")[0] for p in d.glob("*.json.gz")) if d.exists() else []


def backfill_yahoo_long(*, n: int = 600, rng: str = "5y", budget_s: float = 2400) -> int:
    """高股息「提前卡位」研究用的長歷史日線（2026-10-15）：另存 yhl、不併入 yh——併進去會讓其他策略
    （長線成長股的篩選月份、各訊號成績單）的回測期間跟著變。宇宙＝上市櫃市值前 n＋高股息四檔指數歷次異動股＋加權指數。
    已有者跳過（可重跑續補）。"""
    t0 = time.time()
    have = set(yhl_codes())
    doc = store.read("mkt", store.dates("mkt")[-1]) if store.dates("mkt") else {}
    tp = set((doc or {}).get("q_tp") or {})
    todo = ["TWII"] + [c for c in hd_universe(n) + sorted(_hd_cfg_codes()) if c != "TWII"]
    todo = list(dict.fromkeys(todo))
    k = 0
    for c in todo:
        if c in have:
            continue
        if time.time() - t0 > budget_s:
            market.log(f"Yahoo 長歷史時間預算用完（已補 {k} 檔，下輪續補）")
            break
        sufs = ([("^TWII", "idx")] if c == "TWII" else [(c + ".TWO", "tp")] if c in tp
                else [(c + ".TW", "tw"), (c + ".TWO", "tp")])
        for sym, mkt in sufs:
            h = market.yahoo_hist(sym, rng=rng)
            time.sleep(0.6)
            if len(h) >= 20:
                store.write("yhl", c, {"m": mkt, "q": h})
                k += 1
                break
    market.log(f"Yahoo 長歷史（{rng}）：宇宙 {len(todo)} 檔、本輪新增 {k} 檔、累計 {len(yhl_codes())} 檔")
    return k


def backfill_divtw(years: tuple) -> int:
    """證交所除權息計算結果表（一年一請求）；已有的年度不重抓。"""
    n = 0
    for y in years:
        if (store.read("divtw", str(y)) or {}).get("rows"):
            continue
        rows = market.twse_exright_year(y)
        time.sleep(market.UA_SLEEP_TWSE)
        if rows:
            store.write("divtw", str(y), {"rows": rows})
            n += len(rows)
    market.log(f"證交所除權息補年度 {years}：{n} 列")
    return n


def backfill_hd(*, budget_s: float = 2700, years: tuple = (2021, 2022, 2023, 2024, 2025, 2026), n: int = 460) -> dict:
    """高股息研究資料：① 證交所除權息（一年一請求）② FinMind 單季 EPS（市值前 n＋設定檔歷次異動股）
    ③ 上櫃股與有「權息」紀錄的上市股抓 FinMind 股利政策（現金部分）。EPS／股利各自記抓取日（asof／div_asof），20 天內抓過的跳過；限流就停、下一輪續補。"""
    t0 = time.time()
    st = {"twt49u": 0, "eps": 0, "div": 0, "skip": 0, "limit": False}
    this_year = clock.today_tw().year
    for y in years:                                       # ① 證交所除權息（過去年度有檔就不重抓；今年每輪重抓）
        old_rows = (store.read("divtw", str(y)) or {}).get("rows") or []
        if old_rows and y < this_year and len(old_rows[0]) >= 6:   # 舊格式（沒有前收盤價）→ 重抓
            continue
        rows = market.twse_exright_year(y)
        time.sleep(market.UA_SLEEP_TWSE)
        if rows:
            store.write("divtw", str(y), {"rows": rows})
            st["twt49u"] += len(rows)
    uni = hd_universe(n)
    uni += sorted(_hd_cfg_codes() - set(uni))
    doc = store.read("mkt", store.dates("mkt")[-1]) if store.dates("mkt") else {}
    tp = set((doc or {}).get("q_tp") or {})
    # 上市股有「權息」（配股＋現金）紀錄的，證交所表只有合計值 → 也抓 FinMind 股利政策拿現金部分
    qx = {r[1] for y in store.dates("divtw") for r in (store.read("divtw", y) or {}).get("rows") or [] if r[3] == "權息"}
    today = clock.today_tw()

    def stale(d):
        return not d or (today - date.fromisoformat(d)).days >= 20

    for c in uni:                                         # ② FinMind：EPS（全部）＋股利（上櫃）
        if time.time() - t0 > budget_s:
            break
        old = store.read("fin", c) or {}
        div_asof = old.get("div_asof") or (old.get("asof") if old.get("div") else None)
        need_eps, need_div = stale(old.get("asof")), ((c in tp or c in qx) and stale(div_asof))
        if not need_eps and not need_div:
            st["skip"] += 1
            continue
        new = dict(old)
        if need_eps:
            r = market.finmind("TaiwanStockFinancialStatements", c)
            time.sleep(1.2)
            if r == market.FINMIND_LIMIT:
                st["limit"] = True
                break
            if r is not None:
                new["eps"] = market.fm_eps(r) or old.get("eps") or {}
                new["asof"] = today.isoformat()
                st["eps"] += 1
        if need_div:
            r2 = market.finmind("TaiwanStockDividend", c)
            time.sleep(1.2)
            if r2 == market.FINMIND_LIMIT:
                st["limit"] = True
                if new != old:
                    store.write("fin", c, new)
                break
            if r2 is not None:
                new["div"] = market.fm_div(r2) or old.get("div") or []
                new["div_asof"] = today.isoformat()
                st["div"] += 1
        if new != old:
            store.write("fin", c, new)
    market.log(f"高股息資料：證交所除權息 {st['twt49u']} 列、EPS {st['eps']} 檔、FinMind 股利 {st['div']} 檔、"
               f"跳過（20 天內抓過）{st['skip']}；母體 {len(uni)} 檔{'；FinMind 限流，下一輪續補' if st['limit'] else ''}")
    return st