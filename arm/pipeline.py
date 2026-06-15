"""端到端日更流程：抓資料 → 品質閘門 → 算指標 → 出賣點 → 多元想法。

M1 後的關鍵變更：
  - 績效主軸改為 NAV 含息總報酬（arm/navhist），三檔資產類別通用；
    台股型(00991A)額外保留 TWSE 市價作交叉驗證與量能偵測。
  - 多檔主角輪播（run_all），每日指定一檔「今日輪播主角」。
  - 規模/受益人資金流（AUM 來自 nav_history，受益人來自 TDCC）。
  - 交易日曆守門（非交易日如實標 stale）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import (calendar as cal, chips, config, db, diff_engine, ideas as ideas_mod,
               metrics, navhist, peers as peers_mod, signals, themes)
from .connectors import brokers, fhtrust, issuers, tdcc, twse
from .quality import gate_holdings, gate_performance, gate_premium

INTEL = Path(__file__).resolve().parent.parent / "config" / "intel_seed.json"
REPORTS = Path(__file__).resolve().parent.parent / "reports"


def _today_pct(rec: dict) -> float | None:
    if rec.get("close") is None or rec.get("change") is None:
        return None
    prev = rec["close"] - rec["change"]
    return rec["change"] / prev if prev else None


def _find_prior_snapshot(fund_id: str, trade_dates: list[str], back: int = 5):
    """從最新往前找一個可解析的持股快照，用來做張數 diff。"""
    idx = len(trade_dates) - 1 - back
    for i in range(max(0, idx), -1, -1):
        try:
            return fhtrust.fetch_holdings(fund_id, trade_dates[i])
        except fhtrust.NoData:
            continue
    return None


def _aum_change(aum_rows: list[tuple[str, float]], n: int = 5):
    """回傳 (週增率, 現值, n日前值)。"""
    if len(aum_rows) <= n:
        return None, (aum_rows[-1][1] if aum_rows else None), None
    now, prev = aum_rows[-1][1], aum_rows[-1 - n][1]
    chg = (now / prev - 1) if prev else None
    return chg, now, prev


def build_context(etf_id: str, *, all_today=None, conn=None) -> dict:
    """組出單檔 ctx（含品質報告），供偵測器 / 想法引擎 / 報告共用。"""
    cfg = config.load()
    p = config.product(etf_id)
    ac = p["asset_class"]
    all_today = all_today if all_today is not None else twse.fetch_today_all()
    latest = cal.latest_trading_day(all_today)
    conn = conn or db.connect()
    year = int(latest[:4])

    # ── 績效主軸：NAV 含息總報酬（先增量回補到最新交易日）──
    days = cal.trading_days(p["inception"], latest)
    navhist.backfill(conn, etf_id, p["fund_id"], days)
    nav_rows = navhist.load_nav(conn, etf_id)
    tr = navhist.total_return_series(nav_rows, config.distributions(etf_id))
    nav_series = [(d, v, 0) for d, v in nav_rows]
    ret = metrics.multi_period(tr, cfg["periods"], year)

    # ── 最新持股快照 + 前一快照（部位 diff；排除期貨避險/轉倉，不算行銷題材）──
    snap = fhtrust.fetch_holdings(p["fund_id"], latest)
    prior = _find_prior_snapshot(p["fund_id"], [d for d, _ in nav_rows], back=5)
    _norec = lambda hs: [h for h in hs if h.get("kind") != "future"]
    diff = metrics.holdings_diff(_norec(prior["holdings"]) if prior else [], _norec(snap["holdings"]))
    qty_unit, qty_div = {"tw_equity": ("張", 1000), "global_equity": ("股", 1),
                         "global_bond": ("面額", 1)}.get(ac, ("張", 1000))

    # ── 台股型才有的：TWSE 市價、量能、命中飆股、同類排名、Alpha vs 0050 ──
    today_px = all_today.get(etf_id) if p.get("price_source") == "twse" else None
    px_series = twse.fetch_history(etf_id, p["inception"], latest) if today_px else []
    pd_val = metrics.premium_discount(today_px["close"], snap["nav"]) if today_px else None

    alpha, bench = {}, p.get("benchmark")
    if bench:
        bret = metrics.multi_period(twse.fetch_history(bench, p["inception"], latest),
                                    cfg["periods"], year)
        alpha = metrics.alpha_vs(ret, bret)

    top_contrib, peer_ranks, peer_beaten, peer_n = [], {}, {}, 0
    theme_heat_map, hot_t, tailwinds = {}, [], []
    if ac == "tw_equity":
        for h in sorted(snap["holdings"], key=lambda x: x["weight"] or 0, reverse=True)[:10]:
            rec = all_today.get(h["stock_id"])
            pct = _today_pct(rec) if rec else None
            top_contrib.append({"stock_id": h["stock_id"], "name": h["stock_name"],
                                "weight": h["weight"], "change_pct": pct,
                                "contrib": (h["weight"] or 0) * (pct or 0)})

        # 題材/時事引擎（§8 #13, M5）：當日題材熱度由全市場個股漲幅彙總動態算出
        tmap = json.loads(INTEL.read_text(encoding="utf-8")).get("theme_map", {})
        theme_heat_map = themes.theme_heat(all_today, tmap)
        hot_t = themes.hot_themes(theme_heat_map)
        tailwinds = themes.fund_tailwinds(snap["holdings"], all_today, tmap)

        tw_peers = peers_mod.tw_equity_peers(all_today)
        ptable = peers_mod.peer_returns(tw_peers, f"{year}-01-01", latest, year)
        ptable[etf_id] = {"name": p["name"],
                          "ret": metrics.multi_period(tr, peers_mod.PEER_PERIODS, year)}
        peer_ranks = {pr: peers_mod.rank_of(etf_id, ptable, pr) for pr in peers_mod.PEER_PERIODS}
        peer_beaten = {pr: peers_mod.beaten(etf_id, ptable, pr) for pr in peers_mod.PEER_PERIODS}
        peer_n = len(ptable)

    # ── 跨家持股差異化（§18.1, M2）：台股型才對標 0050 + 同類競品 ──
    diff_x = None
    if ac == "tw_equity":
        fund_h = issuers.base.from_fhtrust_dict(etf_id, latest, snap["holdings"])
        bench_h, bench_asof = issuers.benchmark_holdings()
        peers_h = issuers.competitor_peers(latest)        # 競品 live 多為 SPA → 取到才用
        plk = {h["stock_id"]: (_today_pct(all_today[h["stock_id"]]) if all_today.get(h["stock_id"]) else None)
               for h in snap["holdings"]}
        diff_x = diff_engine.compute(fund_h, benchmark=bench_h or None,
                                     benchmark_asof=bench_asof, peers=peers_h, price_lookup=plk)

    # ── 籌碼分點推敲（§18.4, M3）：本檔 + 重倉成分股券商分點（drop-in）＋主動ETF/投信法人籌碼 ──
    chips_x = None
    if ac == "tw_equity":
        targets = [(etf_id, p["name"])] + [(c["stock_id"], c["name"]) for c in top_contrib[:5]]
        bundles = brokers.gather(targets)                 # 券商分點 live 為驗證碼/SPA → 取到才用
        af_asof, af_items = chips.load_active_flow()       # 主動ETF/投信籌碼（etfinfo drop-in）
        if bundles or af_items:
            chips_x = chips.compute(bundles, fund_id=etf_id, broker_map=brokers.broker_map(),
                                    fund_holdings=snap["holdings"], active_items=af_items,
                                    active_asof=af_asof)

    # ── 資金流：規模週增（nav_history）+ 受益人（TDCC，盡力）──
    aum_rows = navhist.load_aum(conn, etf_id)
    aum_chg, aum_now, aum_prev = _aum_change(aum_rows, 5)
    milestone = None
    if aum_now and aum_prev:
        crossed = [t for t in signals._AUM_MILESTONES if aum_prev / 1e8 < t <= aum_now / 1e8]
        milestone = max(crossed) if crossed else None
    holders, holders_chg = tdcc.holders_change(conn, etf_id)

    # ── 品質閘門：NAV 序列 + 持股（依資產類別）──
    q_perf = gate_performance(nav_series, latest, f"{etf_id} NAV")
    q_hold = gate_holdings(snap, etf_id, ac)
    q_prem = gate_premium(today_px["close"], snap["nav"]) if today_px else None

    ctx = {
        "etf_id": etf_id, "name": p["name"], "asset_class": ac, "benchmark": bench,
        "trade_date": latest, "year": year,
        "nav": snap["nav"], "aum": snap["aum"], "units": snap["units"],
        "close": today_px["close"] if today_px else None,
        "change_pct": _today_pct(today_px) if today_px else None,
        "premium": pd_val, "volume": today_px["volume"] if today_px else None,
        "ret": ret, "alpha": alpha,
        "nav_series": nav_series, "price_series": px_series,
        "diff": diff, "prior": prior, "holdings": snap["holdings"],
        "record_holdings": _norec(snap["holdings"]), "top_contrib": top_contrib,
        "qty_unit": qty_unit, "qty_div": qty_div,
        "peer_ranks": peer_ranks, "peer_beaten": peer_beaten, "peer_n": peer_n,
        "theme_heat": theme_heat_map, "hot_themes": hot_t, "theme_tailwinds": tailwinds,
        "aum_chg_1w": aum_chg, "aum_prev": aum_prev, "aum_milestone": milestone,
        "holders": holders, "holders_chg": holders_chg,
        "diff_x": diff_x, "chips": chips_x,
        "_quality": {"perf": q_perf, "hold": q_hold, "prem": q_prem},
        "_conn": conn,
    }
    return ctx


def run(etf_id: str = "00991A", *, all_today=None, conn=None, star=False) -> dict | None:
    p = config.product(etf_id)
    if all_today is None:
        all_today = twse.fetch_today_all()
    rc = cal.run_context(all_today)
    print(f"\n{'='*72}\n  FH-ARM 每日賣點 ── {p['name']}（{etf_id}）"
          f"{'　★今日輪播主角' if star else ''}\n{'='*72}")
    if rc["stale"]:
        print(f"  ⚠️ 今日 {rc['today']} 非交易日／盤後資料未更新 → 採最近交易日 {rc['latest']} 資料。")

    ctx = build_context(etf_id, all_today=all_today, conn=conn)
    ctx["is_star_of_day"] = star
    conn = ctx["_conn"]
    latest = ctx["trade_date"]
    q = ctx["_quality"]

    # 落地
    db.upsert(conn, "etf_daily", {
        "etf_id": etf_id, "trade_date": latest, "close": ctx["close"],
        "change_pct": ctx["change_pct"], "nav": ctx["nav"], "premium_disc": ctx["premium"],
        "aum": ctx["aum"], "units": ctx["units"], "volume": ctx["volume"],
        "src_price": "TWSE STOCK_DAY_ALL" if ctx["close"] is not None else "—（NAV-only）",
        "src_nav": "FHTrust assetsExcel"})
    for h in ctx["holdings"]:
        db.upsert(conn, "holdings_daily", {
            "etf_id": etf_id, "trade_date": latest, "stock_id": h["stock_id"],
            "stock_name": h["stock_name"], "shares": h["shares"],
            "market_value": h["market_value"], "weight": h["weight"]})
    conn.commit()

    # 品質閘門
    print("\n[資料品質閘門]")
    for r in (q["perf"], q["hold"], q["prem"]):
        if r:
            print(r.render())
    if not (q["perf"].passed and q["hold"].passed):
        print("\n❌ 關鍵資料未通過品質閘門 → 依規定不產出賣點（寧缺勿錯）。")
        return None
    print("\n✅ NAV 含息績效與持股資料通過 100% 正確性閘門。")

    # 偵測 + 評分
    sigs = signals.run_all(ctx)

    # 報告
    _print_report(ctx, sigs)

    # 多元想法組合
    intel = json.loads(INTEL.read_text(encoding="utf-8"))
    portfolio = ideas_mod.build_portfolio(ctx, intel, recent_headlines=_recent_headlines())
    _print_portfolio(portfolio)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / f"{latest}_{etf_id}.md").write_text(
        ideas_mod.render_markdown(portfolio, ctx), encoding="utf-8")
    print(f"  📄 已存每日想法報告 → reports/{latest}_{etf_id}.md")

    for s in sigs:
        db.upsert(conn, "signals", {
            "etf_id": etf_id, "trade_date": latest, "detector": s.detector,
            "strength": round(s.strength, 1), "score": s.score,
            "headline": s.headline, "evidence": json.dumps(s.evidence, ensure_ascii=False)})
    conn.commit()
    return {"etf_id": etf_id, "n_signals": len(sigs), "n_ideas": len(portfolio)}


def run_all(star_id: str | None = None) -> None:
    """M1-3：跑全部主角；指定（或依日期輪播）一檔為今日主角。"""
    cfg = config.load()
    prods = cfg["fh_products"]
    all_today = twse.fetch_today_all()
    conn = db.connect()
    latest = cal.latest_trading_day(all_today)
    if star_id is None:                       # 依交易日序數輪播主角
        from datetime import date
        star_id = prods[date.fromisoformat(latest).toordinal() % len(prods)]["id"]
    print(f"\n{'#'*72}\n#  FH-ARM 多主角日更（資料日 {latest}）　今日輪播主角：{star_id}\n{'#'*72}")
    done = []
    for p in prods:
        res = run(p["id"], all_today=all_today, conn=conn, star=(p["id"] == star_id))
        done.append((p["id"], res))
    conn.close()
    print(f"\n{'#'*72}\n#  完成 {sum(1 for _, r in done if r)}/{len(done)} 檔："
          f"{'、'.join(i for i, r in done if r)}\n{'#'*72}")


def _recent_headlines(days: int = 5) -> list[str]:
    if not REPORTS.exists():
        return []
    out = []
    for f in sorted(REPORTS.glob("*.md"))[-days:]:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("- **想法**："):
                out.append(line.split("：", 1)[1].strip())
    return out


def _print_portfolio(picked):
    print(f"\n{'='*72}\n  ★ 今日多元想法組合（共 {len(picked)} 個不同角度）\n{'='*72}")
    for i, idea in enumerate(picked, 1):
        tag = "🟢" if not idea.compliance else ("🔴" if any(c["risk"] == "高" for c in idea.compliance) else "🟡")
        stat = "" if idea.status == "real" else " 〔情報層待補〕"
        print(f"  {i}. [{idea.category}]{stat} {tag} {idea.headline}")
        if idea.evidence:
            print(f"       佐證：{idea.evidence}")
        for c in idea.compliance:
            print(f"       ⚠️合規[{c['risk']}] {c['span']}：{c['note']}")
    print(f"{'='*72}")


def _pct(x):
    return f"{x:+.2%}" if x is not None else "—"


def _print_report(ctx, sigs):
    latest, snap_nav = ctx["trade_date"], ctx["nav"]
    px = f"收盤 {ctx['close']}  漲跌 {_pct(ctx['change_pct'])}  折溢價 {ctx['premium']:+.2%}  " if ctx["close"] is not None else ""
    print(f"\n[基本面 ── 資料日 {latest}]")
    print(f"  {px}NAV {snap_nav}  AUM {ctx['aum']/1e8:,.1f} 億"
          f"{f'  成交量 {ctx['volume']:,} 股' if ctx['volume'] else ''}")

    print(f"\n[多週期 NAV 含息總報酬{('  vs ' + ctx['benchmark']) if ctx['benchmark'] else '（無 TWSE 可比基準）'}]")
    print(f"  {'週期':<8}{'本檔':>10}" + (f"{'基準':>10}{'Alpha':>10}" if ctx["benchmark"] else ""))
    for k in ctx["ret"]:
        line = f"  {signals.PERIOD_ZH.get(k,k):<8}{_pct(ctx['ret'][k]):>10}"
        if ctx["benchmark"]:
            a = ctx["alpha"].get(k)
            b = (ctx["ret"][k] - a) if (ctx["ret"][k] is not None and a is not None) else None
            line += f"{_pct(b):>10}{_pct(a):>10}"
        print(line)

    prior = ctx["prior"]
    unit, div = ctx["qty_unit"], ctx["qty_div"]
    print(f"\n[持股異動 vs 前一快照{'（'+prior['date']+'）' if prior else '（無）'}]")
    for label, key in (("新建倉", "new"), ("加碼", "add"), ("減碼", "cut"), ("出清", "exit")):
        items = ctx["diff"][key][:3]
        if items:
            txt = "，".join(f"{x['stock_name']}{x['delta_shares']/div:+,.0f}{unit}" for x in items)
            print(f"  {label}: {txt}")

    if ctx.get("aum_chg_1w") is not None or ctx.get("holders"):
        h = ""
        if ctx.get("holders"):
            chg = ctx.get("holders_chg")
            h = f"；受益人 {ctx['holders']:,} 人" + (f"（週{chg:+,}）" if chg is not None else "（首次入庫）")
        print(f"\n[資金流] 規模週增 {_pct(ctx.get('aum_chg_1w'))}{h}")

    if ctx["peer_ranks"]:
        print(f"\n[同類排名 ── 全市場 {ctx['peer_n']} 檔台股主動ETF]")
        for k, (rank, n) in ctx["peer_ranks"].items():
            if rank is not None:
                print(f"  {signals.PERIOD_ZH.get(k,k):<8}第 {rank:>2}/{n} 名")
        for period in ("ytd", "3m"):
            named = [b for b in ctx["peer_beaten"].get(period, []) if b["issuer"]][:5]
            if named:
                txt = "，".join(f"{b['issuer']}{b['code']}(+{b['gap']:.1%})" for b in named)
                print(f"  └ {signals.PERIOD_ZH.get(period,period)}比下去: {txt}")
                break

    dx = ctx.get("diff_x")
    if dx and (dx.get("active_share") is not None or dx.get("unique")):
        print(f"\n[跨家持股差異化 ── vs {dx['benchmark_label']}"
              f"{f' + {dx['n_peers']} 競品' if dx['n_peers'] else ''}]")
        if dx.get("active_share") is not None:
            print(f"  主動度 Active Share {dx['active_share']:.0f}%"
                  f"（基準 {dx['benchmark_label']} as-of {dx.get('benchmark_asof')}，近似公開權重）")
        if dx.get("style_tags"):
            print(f"  選股風格：{'　'.join(dx['style_tags'])}")
        if dx.get("unique"):
            uq = "、".join(f"{u['name']}({u['weight']:.1f}%)" for u in dx["unique"][:5])
            print(f"  獨門卡位（同業多數未持有）：{uq}")
            for o in dx.get("overlaps", [])[:3]:
                print(f"  └ 與 {o['peer']} 重疊 Jaccard {o['jaccard']:.0%}、權重重疊 {o['weight_overlap']:.0f}%")
        else:
            print("  獨門/重疊/領先：競品逐日持股待接（drop-in → config/competitor_holdings/，引擎已就緒）")

    cx = ctx.get("chips")
    rows = ((([("本檔", cx["fund"])] if cx.get("fund") else []) +
             [("重倉", h) for h in (cx.get("holdings") or [])[:3]]) if cx else [])
    inst = (cx.get("institutional") or []) if cx else []
    if rows or inst:
        print("\n[籌碼推敲 ── 券商分點(推估・非確認) + 主動ETF/投信法人籌碼(etfinfo・Tier B 待核對)]")
        for tag, r in rows:
            b = r["top_buyer"]
            ratio = f"、佔成交 {b['buy_ratio']:.0%}" if b.get("buy_ratio") is not None else ""
            print(f"  [分點/{tag}] {r['target_name']}：{b['broker_name']} 買超 {b['net']:+,} 張"
                  f"（連 {b['days']} 日{ratio}）→ 推估 {b['identity']['kind']}")
        for t in inst[:5]:
            print(f"  [法人] {t['name']}（權重 {t['weight']:.1f}%）：{t['reason']}"
                  f"，估算新進+加碼約 {t['est_yi']:.1f} 億")
        print(f"  └ {cx['disclaimer']}")

    hot = ctx.get("hot_themes") or []
    tw = ctx.get("theme_tailwinds") or []
    if hot or tw:
        print("\n[當日題材熱度 ── 由 STOCK_DAY_ALL 全市場個股漲幅彙總（非固定清單）]")
        for theme, h in hot[:5]:
            print(f"  {theme:<14} 熱度 {h['heat']:>5.0f}  強漲 {h['n_strong']}/{h['n_total']} 檔"
                  f"  平均 {h['avg_pct']:+.1%}")
        if tw:
            t = tw[0]
            print(f"  └ 本檔順風：重倉【{t['theme']}】合計 {t['fund_weight']:.1f}%"
                  f"（市場題材熱度 {t['market_heat']:.0f}）")

    print(f"\n[今日賣點榜 ── 共 {len(sigs)} 個訊號]")
    for i, s in enumerate(sigs, 1):
        print(f"  {i}. ★{s.score:>5}  〔{s.detector}〕{s.headline}")
    print(f"\n{'='*72}")
    print("  ※ 績效=NAV 含息總報酬（復華官網揭露）；台股型另以 TWSE 官方收盤交叉驗證。")
    print("  ※ 文案合規採事後標注（見 docs/SPEC.md §10）。")
    print(f"{'='*72}\n")
