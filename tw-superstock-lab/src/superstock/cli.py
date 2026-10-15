"""命令列入口：python -m superstock <指令>

  check       檢查 token、額度，估算要下載多久
  download    首次下載（可中斷，重跑會續傳）
  update      每日增量更新（收盤後執行）
  build       整理成研究用資料表（data/processed/）
  quality     資料品質檢查 → reports/data_quality.md
  reconcile   抽樣與官方資料對帳 → reports/reconciliation.md
  status      看下載進度與失敗清單
  probe       實測 FinMind 各資料集欄位與語意（SPEC §3.7）→ reports/live_probe.md
  replicate   P2 關卡：用回測引擎買進持有加權報酬指數，逐年與指數本身比較 → reports/replication_P2.md
  official    官方免費資料：處置股歷史（證交所、櫃買處置公告）＋集保股權分散表（最新一週，往後累積）
              download／update 結束時也會自動跑一次（失敗不影響 FinMind 下載）
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

from .config import Config, get_token, load_config
from .download import Downloader, default_today
from .finmind_client import FinMindClient, FinMindError
from .storage import Manifest, Store

log = logging.getLogger("superstock")


def setup_logging(cfg: Config, verbose: bool = False) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    fh = logging.FileHandler(cfg.log_dir / "superstock.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def _client(cfg: Config) -> FinMindClient:
    token = get_token(cfg)
    if not token:
        log.warning("沒有設定 %s：免費未註冊額度只有每小時 300 次。請在 .env 填入 token。",
                    cfg.finmind.token_env)
    return FinMindClient(token, cfg.finmind)


def _downloader(cfg: Config) -> tuple[Downloader, Manifest]:
    client = _client(cfg)
    if client.has_token:
        info = client.sync_limit()
        if info:
            log.info("FinMind 額度：本小時已用 %s / 上限 %s", info.get("user_count"),
                     info.get("api_request_limit"))
    manifest = Manifest(cfg.manifest_path)
    store = Store(cfg.raw_dir)
    return Downloader(cfg, client, store, manifest, today=default_today()), manifest


def cmd_check(cfg: Config, args: argparse.Namespace) -> int:
    dl, manifest = _downloader(cfg)
    try:
        if not dl.client.has_token:
            print("尚未設定 token，下載速度會受限（每小時 300 次）。")
        # 先把 meta（約 7 次請求）抓下來，才知道股票池多大
        dl.run(["meta"], mode="initial")
        uni = dl.universe()
        groups = args.groups or cfg.download_groups
        plan = dl.plan(groups, uni)
        per_hour = dl.client.limiter.per_hour
        numeric = pd.to_numeric(plan["pending_calls"], errors="coerce").fillna(0)
        total = int(numeric.sum())
        print(f"\n股票池：{len(uni)} 檔（下市 {int(uni['is_delisted'].sum())} 檔）")
        print(f"本機限流：每小時 {per_hour} 次（已扣安全邊際）\n")
        print(plan.to_string(index=False))
        print(f"\n確定的待下載請求約 {total:,} 次 → 約 {total / max(1, per_hour):.1f} 小時"
              "（事件類若可整批下載會更少）")
        return 0
    finally:
        manifest.close()


def _run_download(cfg: Config, args: argparse.Namespace, mode: str) -> int:
    dl, manifest = _downloader(cfg)
    try:
        for name in args.enable or []:
            manifest.enable(name)
            log.info("已重新啟用 %s", name)
        for name in args.reset_mode or []:
            manifest.set_mode(name, "")
            log.info("%s 下次會重新判斷下載方式", name)
        groups = args.groups or cfg.download_groups
        result = dl.run(groups, mode=mode, stocks=args.stocks, max_calls=args.max_calls)
        log.info("完成：%s", result)
        if result.get("stopped_reason"):
            print(f"\n已暫停：{result['stopped_reason']}。重新執行同一個指令即可從中斷處繼續。")
        elif not args.stocks and not getattr(args, "skip_official", False):
            _run_official(cfg, ("disposition", "tdcc"), refresh=False)
        return 0
    except KeyboardInterrupt:
        print("\n已中斷。進度已保存，重新執行同一個指令即可續傳。")
        return 130
    finally:
        manifest.close()


def _run_official(cfg: Config, what, refresh: bool) -> dict:
    from .official import disposition_years, update_all
    res = update_all(cfg.raw_dir, cfg.start_date, default_today(), what=what, refresh=refresh)
    if "disposition" in res:
        t = disposition_years(cfg.raw_dir)
        if not t.empty:
            print("\n處置公告（4 碼普通股，依公告日）：")
            print(t.to_string(index=False))
    if "tdcc" in res:
        print(f"\n集保股權分散表：{res['tdcc']}")
    for k in ("disposition_error", "tdcc_error"):
        if k in res:
            print(f"\n{k}：{res[k]}（下次執行會再補）")
    return res


def cmd_official(cfg: Config, args: argparse.Namespace) -> int:
    res = _run_official(cfg, tuple(args.what), args.refresh)
    return 1 if any(k.endswith("_error") for k in res) else 0


def cmd_build(cfg: Config, args: argparse.Namespace) -> int:
    from .build import build_all
    counts = build_all(cfg)
    for k, v in counts.items():
        print(f"{k:15s} {v:>12,} 列")
    return 0


def cmd_quality(cfg: Config, args: argparse.Namespace) -> int:
    from .quality import run_quality, write_report
    checks = run_quality(cfg)
    path = write_report(checks, cfg.reports_dir)
    for c in checks:
        print(f"{c.id:4s} {c.status:4s} {c.title}：{c.summary}")
    print(f"\n報告：{path}")
    return 1 if any(c.status == "FAIL" for c in checks) else 0


def cmd_reconcile(cfg: Config, args: argparse.Namespace) -> int:
    from .reconcile import reconcile
    path = reconcile(cfg, n=args.n, fetch=not args.no_fetch)
    print(f"對帳報告：{path}")
    return 0


def cmd_probe(cfg: Config, args: argparse.Namespace) -> int:
    from .probe import run_probe, user_info_shape, write_probe_report
    client = _client(cfg)
    if client.has_token and not args.offline:
        client.sync_limit()
    result = run_probe(cfg, client, default_today().isoformat(), probe_stock=args.stock,
                       extra_calls=not args.offline)
    if not args.offline:
        result["user_info"] = user_info_shape(cfg, client)
    path = write_probe_report(result, cfg.reports_dir)
    print(f"實測報告：{path}（本次請求 {result['calls']} 次）")
    return 0


def cmd_replicate(cfg: Config, args: argparse.Namespace) -> int:
    from .engine import Costs, replicate_index
    path = cfg.processed_dir / "index.parquet"
    if not path.exists():
        print("找不到 index.parquet，請先 download（meta）與 build")
        return 1
    idx = pd.read_parquet(path)
    tr = (idx[idx["index_id"].astype(str) == "TAIEX"].set_index("date")["total_return"]
          .astype(float).dropna().sort_index())
    rep = replicate_index(tr)
    rep_cost = replicate_index(tr, costs=Costs())
    worst = float(rep["diff"].abs().max())
    ok = worst <= 0.005
    lines = ["# P2 關卡：加權報酬指數買進持有複製", "",
             f"資料：TAIEX 報酬指數 {tr.index.min().date()}～{tr.index.max().date()}，{len(tr):,} 個交易日。"
             f"引擎第一天收盤下單、第二天開盤（＝當天指數）買進，零成本、可買小數股。",
             f"結果：逐年最大差距 {worst:.6%}（門檻 0.5%）→ **{'通過' if ok else '未通過'}**。"
             f"另以實際成本（只在第一年買進一次）試算，最大差距 {float(rep_cost['diff'].abs().max()):.4%}。", "",
             "| 年 | 引擎 | 指數 | 差距 | 含成本引擎 |", "| --- | --- | --- | --- | --- |"]
    for r, rc in zip(rep.itertuples(index=False), rep_cost.itertuples(index=False)):
        lines.append(f"| {r.year} | {r.engine:.4%} | {r.index:.4%} | {r.diff:.6%} | {rc.engine:.4%} |")
    out = cfg.reports_dir / "replication_P2.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"逐年最大差距 {worst:.6%} → {'通過' if ok else '未通過'}；報告：{out}")
    return 0 if ok else 1


def cmd_status(cfg: Config, args: argparse.Namespace) -> int:
    manifest = Manifest(cfg.manifest_path)
    try:
        summary = manifest.summary()
        print("下載進度（各狀態檔數）：")
        print(summary.to_string(index=False) if not summary.empty else "（尚無紀錄）")
        ds = manifest.datasets_table()
        if not ds.empty:
            print("\n資料集設定：")
            print(ds.to_string(index=False))
        fails = manifest.failures(20)
        if not fails.empty:
            print("\n最近失敗：")
            print(fails.to_string(index=False))
        return 0
    finally:
        manifest.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="superstock", description="台股飆股研究系統")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check", help="檢查 token 與額度，估算下載時間")
    p.add_argument("--groups", nargs="+")

    for name in ("download", "update"):
        p = sub.add_parser(name, help="首次下載" if name == "download" else "每日增量更新")
        p.add_argument("--groups", nargs="+", help="meta core events extended")
        p.add_argument("--stocks", nargs="+", help="只處理這些代號（測試用）")
        p.add_argument("--max-calls", type=int, help="本次最多送幾次請求")
        p.add_argument("--enable", nargs="+", help="重新啟用被自動停用的資料集")
        p.add_argument("--reset-mode", nargs="+", help="重新判斷事件資料集能否整批下載")
        p.add_argument("--skip-official", action="store_true", help="結束時不跑官方處置公告／集保更新")

    sub.add_parser("build", help="整理成研究用資料表")
    sub.add_parser("quality", help="資料品質檢查")
    p = sub.add_parser("reconcile", help="抽樣與官方資料對帳")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--no-fetch", action="store_true", help="不連證交所，只產生人工核對清單")
    sub.add_parser("status", help="下載進度")
    sub.add_parser("replicate", help="P2 關卡：加權報酬指數買進持有複製")
    p = sub.add_parser("official", help="官方處置公告（歷史）＋集保股權分散表（最新一週）")
    p.add_argument("--what", nargs="+", default=["disposition", "tdcc"], choices=["disposition", "tdcc"])
    p.add_argument("--refresh", action="store_true", help="處置公告所有年份重抓")
    p = sub.add_parser("probe", help="實測 FinMind 各資料集欄位與語意（§3.7）")
    p.add_argument("--stock", default="2330", help="本機沒有資料的資料集用哪一檔試抓")
    p.add_argument("--offline", action="store_true", help="只摘要本機資料，不送請求")

    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    setup_logging(cfg, args.verbose)
    try:
        if args.cmd == "check":
            return cmd_check(cfg, args)
        if args.cmd == "download":
            return _run_download(cfg, args, "initial")
        if args.cmd == "update":
            return _run_download(cfg, args, "update")
        if args.cmd == "build":
            return cmd_build(cfg, args)
        if args.cmd == "quality":
            return cmd_quality(cfg, args)
        if args.cmd == "reconcile":
            return cmd_reconcile(cfg, args)
        if args.cmd == "status":
            return cmd_status(cfg, args)
        if args.cmd == "probe":
            return cmd_probe(cfg, args)
        if args.cmd == "replicate":
            return cmd_replicate(cfg, args)
        if args.cmd == "official":
            return cmd_official(cfg, args)
    except FinMindError as exc:
        log.error("FinMind 錯誤：%s", exc)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
