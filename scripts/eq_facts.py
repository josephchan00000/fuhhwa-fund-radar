"""個股報告的資料包（docs/lab_equity_report_plan.md 第 3 節；技能 .claude/skills/equity-report）。

    TZ=Asia/Taipei python3 scripts/eq_facts.py 4958                 # → reports/eq/tw/4958/{今天}.facts.json
    TZ=Asia/Taipei python3 scripts/eq_facts.py 4958 --peers 3037,8046,3189,2368,3044,2313
    TZ=Asia/Taipei python3 scripts/eq_facts.py --ind tw-L000         # → reports/eq/ind/tw-L000/{今天}.facts.json
    加 --out 路徑 改寫到別的地方（例如 scratchpad 試算）。

只讀 repo 裡已有的資料、不連外網；印出撰寫要用的重點（評等預設、倍數範圍、同業）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arm import clock  # noqa: E402
from arm.lab import eqfacts as E  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?")
    ap.add_argument("--ind", help="產業代號（tw-L000＝櫃買產業鏈 L000）")
    ap.add_argument("--peers", help="換過的同業，逗號分開")
    ap.add_argument("--out")
    a = ap.parse_args()
    today = clock.today_tw().isoformat()
    if a.ind:
        mk, cid = a.ind.split("-", 1)
        if mk != "tw":
            print("美股產業資料包還沒做")
            return 2
        pack = E.ind_pack_tw(cid)
        pack["made"] = today
        out = Path(a.out) if a.out else ROOT / "reports" / "eq" / "ind" / a.ind / f"{today}.facts.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{pack['name']}：{pack['n_members']} 家、市值合計 {pack['cap_total']:,} 億；本益比中位數 {(pack.get('pe') or {}).get('p50')}；"
              f"泡沫 {[(b['name'], b['level']) for b in pack['bubble']]}")
        print(f"寫入 {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
        return 0
    if not a.code:
        ap.error("要給代號或 --ind")
    peers = [c.strip() for c in a.peers.split(",")] if a.peers else None
    pack = E.tw_pack(a.code, peers=peers)
    pack["made"] = today
    out = Path(a.out) if a.out else ROOT / "reports" / "eq" / "tw" / a.code / f"{today}.facts.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    v = pack["val"]
    print(f"{pack['name']}（{a.code}）收盤 {v['px']}（{pack['asof']}）；方法 {v['method']}（{'共識法' if v.get('basis') == 'fwd' else '近四季法'}）；"
          f"基數 {v.get('base_label')} {v.get('base')}；未來 12 個月 EPS {v['f12m']}；近四季 EPS {v.get('eps4')}")
    print(f"倍數範圍怎麼取：{v.get('range_how')}；預設：{v.get('dflt_how')}")
    print(f"倍數範圍 {v.get('range')}；預設目標價 {v.get('tp_dflt')}（{v.get('rating_dflt')}，上檔 {v.get('up_dflt')}%）；"
          f"範圍換算目標價 {v.get('tp_lo')}～{v.get('tp_hi')}")
    print(f"同業（{pack['peer_how']}）：{[(p['c'], p['n']) for p in pack['peers']]}；照規則的同業：{pack['peers_auto']}")
    print(f"產業鏈：{[(c['cn'], c['nn']) for c in pack['chain']]}；預設產業報告 tw-{pack['chain_main']}")
    print(f"寫入 {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
