#!/usr/bin/env python3
"""美股飆股研究（ussxspec VER 2、VER 3；docs/lab_us_sleeve_plan.md 第 9、10.5、13 節）。資料在資料分支 claude/ussx-data：

  git worktree add --detach <資料夾> origin/claude/ussx-data
  USSX_DIR=<資料夾>/data/lab/ussx TZ=Asia/Taipei python3 scripts/run_ussx.py --surv   # A 存活偏誤 → data/lab/ussx_surv.json
  USSX_DIR=… python3 scripts/run_ussx.py --swap                                        # B 換一個指數 → data/lab/ussx_swap.json
  USSX_DIR=… python3 scripts/run_ussx.py --books                                       # C 美股飆股 → data/lab/ussx_books.json
                                                                                       # （規格要 SEC 財報：資料夾沒有 sec/ 就不跑）
  USSX_DIR=… python3 scripts/run_ussx.py --qm                                          # VER 3 美股三成規則 QM → data/lab/ussx_qm.json
  USSX_DIR=… python3 scripts/run_ussx.py --qm-live                                     # 每週紀錄（ussx_weekly.yml）→ data/lab/ussx_qm_live.json
  USSX_DIR=… python3 scripts/run_ussx.py --omfix                                       # 一次性收入修法研究（omfixspec）→ data/lab/ussx_omfix.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import ussxdata as UD  # noqa: E402
from arm.lab import ussxpanel as UP  # noqa: E402
from arm.lab import ussxsurv as SV  # noqa: E402
from arm.lab import ussxswap as SW  # noqa: E402

OUT = ROOT / "data" / "lab"


def _clean(x):
    """nan／inf → None（跑很久的研究不要在最後寫檔時因為一個 nan 整個丟掉）。"""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "item") and not isinstance(x, (str, bytes)):          # numpy 純量
        return _clean(x.item())
    return x


def _save(name: str, doc: dict) -> None:
    p = OUT / name
    p.write_text(json.dumps(_clean(doc), ensure_ascii=False, sort_keys=True, indent=1, allow_nan=False), encoding="utf-8")
    print(f"[ussx] 寫入 {p.relative_to(ROOT)}")


def _pct(x, d=2):
    return "—" if x is None else f"{x * 100:+.{d}f}"


def surv(P) -> None:
    R = SV.research(P)
    _save("ussx_surv.json", R)
    print(f"[ussx] 存活偏誤 {R['a']}～{R['b']}（{R['months']} 個月）")
    for g, r in R["groups"].items():
        h = r["halves"]
        print(f"  {g:<4} vs {r['etf']:<4} 組 {_pct(r['cagr'])}% ETF {_pct(r['etf_cagr'])}% 差 {_pct(r['gap'])} 個百分點"
              f"（前半 {_pct(h[0]['gap'])}、後半 {_pct(h[1]['gap'])}；檔數 {r['n']['first']}→{r['n']['last']}，最少 {r['n']['min']}）")
    print(f"[ussx] G＝max(PIT, S, R)＝{_pct(R['G'])} 個百分點 → {'先停下來討論' if R['stop'] else '小於門檻'}")


def swap(P) -> None:
    R = SW.research(P)
    _save("ussx_swap.json", R)
    for mk, row in R["plans"].items():
        c = row["cur"]
        print(f"[ussx] {mk} 計畫 {c['a']}～{c['b']}：現在 100 萬 → {c['plan']['m'] * 100:,.0f} 萬、最慘 {c['plan']['mdd'] * 100:.0f}%"
              f"（兩半 {c['halves'][0]['plan']['m'] * 100:,.0f}／{c['halves'][1]['plan']['m'] * 100:,.0f} 萬）")
        for e, r in row["swap"].items():
            j = r["judge"]
            print(f"  三成放 {e:<5} → {r['plan']['m'] * 100:,.0f} 萬、最慘 {r['plan']['mdd'] * 100:.0f}%"
                  f"（兩半 {r['halves'][0]['plan']['m'] * 100:,.0f}／{r['halves'][1]['plan']['m'] * 100:,.0f} 萬）"
                  f" 錢 {'✓' if j['money'] else '✗'} 兩半 {'✓' if j['halves'] else '✗'} 最慘 {'✓' if j['mdd'] else '✗'}")
            for nm, lg in (row["long"].get(e) or {}).items():
                print(f"      長歷史 {nm} {lg['cur']['a']}～{lg['cur']['b']}：現在 {lg['cur']['plan']['m'] * 100:,.0f} 萬 vs "
                      f"{lg['swap']['plan']['m'] * 100:,.0f} 萬、最慘 {lg['cur']['plan']['mdd'] * 100:.0f}% vs "
                      f"{lg['swap']['plan']['mdd'] * 100:.0f}%；方向{'相同' if lg['same_dir'] else '相反'}")


def books(P, force: bool = False) -> None:
    from arm.lab import secfin as SF
    from arm.lab import ussxrun as UR
    if not SF.load_meta().get("asof") and not force:
        print("[ussx] 還沒有 SEC 財報（規格要用）：先建 secret SEC_CONTACT_EMAIL、跑 ussxfill；不跑")
        return
    R = UR.books(P)
    _save("ussx_books.json", R)
    for b, r in R["books"].items():
        v = r["verdict"]
        print(f"[ussx] {b}：三成本身 {_pct(r['sleeve_main']['cagr'], 1)}%（S&P 500 {_pct(r['spx_tr']['cagr'], 1)}%、"
              f"同一批 {_pct(r['ew']['cagr'], 1)}%）；判定 {v['pass']}")


def qm(P) -> None:
    from arm.lab import ussxqm as QM
    R = QM.research(QM.context(P))
    QM.save(R)
    print(f"[ussx] 寫入 {QM.RES.relative_to(ROOT)}")
    rp, v = R["repro"], R["verdict"]
    print(f"[ussx] QM 三成本身 {R['eval']} 起 {_pct(R['sleeve']['main']['cagr'])}%（第 12 節 {_pct(rp['ref']['cagr'])}%）、"
          f"計畫 {rp['plan_m'] * 100:,.1f} 萬（第 12 節 {rp['ref']['plan_m'] * 100:,.1f} 萬）→ 重現 {'✓' if rp['ok'] else '✗'}")
    for mk in ("spx", "ndx"):
        pl, j = R["plans"][f"{mk}_main"], R["plans"][f"{mk}_main"]["judge"]
        b = pl.get("base") or pl["cur"]
        print(f"  {mk}：現在在用的計畫 {b['plan']['m'] * 100:,.0f} 萬（最慘 {b['plan']['mdd'] * 100:.1f}%）→ QM {pl['new']['plan']['m'] * 100:,.0f} 萬"
              f"（最慘 {pl['new']['plan']['mdd'] * 100:.1f}%；機動也買指數 {pl['cur']['plan']['m'] * 100:,.0f} 萬）；"
              f"錢 {'✓' if j['money'] else '✗'} 兩半 {'✓' if j['halves'] else '✗'} 最慘 {'✓' if j['mdd'] else '✗'}；"
              f"判定 {'過' if v['pass'][mk] else '沒過'}、換 {'✓' if R['switch'][mk] else '✗'}")


def qm_live(P) -> None:
    from arm.lab import ussxqm as QM
    C = QM.context(P)
    sig = QM.signals(C, QM.qm_mask(C["cols"]["f"]))
    r = QM.run(C, sig, "spx")
    try:                                                     # 名稱跟版本無關：規則升版（紀錄從頭記）時也沿用舊檔的名稱
        old_names = json.loads(QM.LIVE.read_text(encoding="utf-8")).get("names") or {}
    except (OSError, ValueError, AttributeError):
        old_names = {}
    L = QM.live_update(C, r, sig)
    n0 = L.get("now") or {}                                  # 配置頁美股列的股票的英文名稱（中文簡介在 holding_profiles）
    codes = [h["c"] for h in n0.get("hold") or []] + list(n0.get("buy") or []) + [x["c"] for x in n0.get("list") or []]
    L["names"] = UD.names_for(codes, old={**old_names, **(L.get("names") or {})})
    ch = QM.save_live(L)
    n = L.get("now") or {}
    print(f"[ussx] 美股三成紀錄（{'有更新' if ch else '沒有變'}）：起點 {L.get('start')}、已記 {len(L.get('weeks') or {})} 週、"
          f"資料到 {n.get('d')}（這一週{'已結束' if n.get('wk_done') else '還沒結束'}）")
    print(f"  持股 {len(n.get('hold') or [])} 檔：{'、'.join(h['c'] for h in n.get('hold') or [])}；"
          f"下一個交易日 {n.get('next')} 開盤賣 {n.get('sell') or '—'}、買 {n.get('buy') or '—'}")
    for x in (L.get("diff") or [])[-3:]:
        print(f"  ⚠ {x['d']} {x['what']}")


def omfix(P) -> None:
    """一次性收入修法研究（omfixspec VER 1）→ data/lab/ussx_omfix.json（研究用，頁面不讀）。"""
    from arm.lab import omfixspec as OS
    from arm.lab import ussxomfix as OF
    from arm.lab import ussxqm as QM
    R = OF.research(QM.context(P, extra=OS.KEYS))
    OF.save(R)
    print(f"[ussx] 寫入 {OF.RES.relative_to(ROOT)}；建議 {R['pick']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surv", action="store_true")
    ap.add_argument("--swap", action="store_true")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--qm", action="store_true")
    ap.add_argument("--qm-live", action="store_true")
    ap.add_argument("--omfix", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    P = UP.load()
    print(f"[ussx] 面板 {len(P['cal'])} 天 × {len(P['sym'])} 檔（{time.time() - t0:.0f}s）")
    if a.surv:
        surv(P)
    if a.swap:
        swap(P)
    if a.books:
        books(P)
    if a.qm:
        qm(P)
    if a.qm_live:
        qm_live(P)
    if a.omfix:
        omfix(P)
    print(f"[ussx] 完成（{time.time() - t0:.0f}s）")


if __name__ == "__main__":
    main()
