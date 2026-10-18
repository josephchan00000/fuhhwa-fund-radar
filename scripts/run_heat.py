#!/usr/bin/env python3
"""景氣溫度頁研究檔：五個面向的分數、每一項的驗證、16 種技術事件的事件研究，
第五版再加單項分析（領先落後、Granger、滾動相關、五區、進入過熱過冷事件）與核心 13 項的邊際變化驗證，
第六版再加邊際變化的多層回歸（延遲反應、增量、交互、跨訊號、綜合模型、轉折事件、樣本外；arm/lab/heatreg.py）
→ data/lab/heat_research.json（docs/lab_heat_plan.md 第 12、13、14、15 節）。

規格（heatspec VER 6）與實作細節（規劃文件第 12.7、13.9、14.14、15.11 節）都在跑之前寫定。資料或規格改了才重跑：
  TZ=Asia/Taipei python3 scripts/run_heat.py
每天建頁只讀這個檔（過去的分區統計與判定，只當資訊），當天的分數用同一套算法重算。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arm.lab import heatcalc as C  # noqa: E402
from arm.lab import heatspec as S  # noqa: E402

OUT = ROOT / "data" / "lab" / "heat_research.json"


def _r(x) -> str:
    return "  —  " if x is None else f"{x:+.3f}"


def _p(x) -> str:
    return "  —  " if x is None else f"{100 * x:+.2f}%"


def line(name: str, first: str | None, e: dict) -> str:
    ref = e.get("ref") or [{}, {}]
    return (f"  {name:8s} 起 {first or '—':10s} n={e['n']:5d} ρ={_r(e['rho'])} [{_r(e['lo'])}, {_r(e['hi'])}]"
            f"  前半 {_r(e['h1']['rho'])}  後半 {_r(e['h2']['rho'])}  → {S.VERDICT[e['verdict']]:8s}"
            f"  對照 {_r(ref[0].get('rho'))}／{_r(ref[1].get('rho'))}")


def main() -> None:
    t0 = time.time()
    res = C.research()
    OUT.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")
    print(f"資料日曆 {res['cal']}")
    for dim, R in res["dims"].items():
        L = S.DIMS[dim]
        for h in L["fwd"]:
            print(f"\n■ {L['name']}：之後 {h} 個交易日（{'每月' if L['freq'] == 'm' else '每天'}一個樣本）")
            print(line("面向分數", R["comp_first"], R["comp"][h]))
            for k in S.ITEMS[dim]:
                print(line(k, R["first"][k], R["items"][k][h]))
    print("\n■ 技術事件（之後 10／60 個交易日，和所有日子比）")
    for k, nm in S.EVENTS.items():
        cells = []
        for h in S.EV_FWD:
            e = res["events"][k][str(h)]
            if not e["n"]:
                cells.append(f"{h} 日 —")
                continue
            h1, h2 = (e.get("h1") or {}).get("diff"), (e.get("h2") or {}).get("diff")
            cells.append(f"{h} 日 n={e['n']:3d} 平均 {_p(e['avg'])} 差 {_p(e['diff'])} [{_p(e['lo'])}, {_p(e['hi'])}]"
                         f" 兩半 {_p(h1)}／{_p(h2)} → {S.EV_VERDICT[e['verdict']]}")
        print(f"  {nm:14s} " + "｜".join(cells))
    rel_report(res)
    deriv_report(res)
    m6_report(res)
    print(f"\n寫 {OUT}（{OUT.stat().st_size // 1024} KB），{time.time() - t0:.0f} 秒")


VERD = {"weak": "較弱", "strong": "較強", "none": "看不出", "few": "樣本不足"}


def rel_report(res: dict) -> None:
    """第五版單項分析：領先落後、Granger、進入過熱過冷事件（只當參考）。"""
    rel = res.get("rel") or {}
    print("\n■ 單項分析（每週樣本；之前 5／20／60／120／250 日的相關｜之後的相關［區間］判定｜Granger A、B）")
    for sid in list(S.DIMS) + list(S.KEYS):
        a = rel.get(sid)
        if not a:
            continue
        ll = a["ll"]
        past = " ".join(_r(ll["past"][str(h)]["rho"] if str(h) in ll["past"] else ll["past"][h]["rho"]) for h in S.LL_H)
        fut = []
        for h in S.LL_H:
            e = ll["fut"].get(str(h)) or ll["fut"].get(h)
            fut.append(f"{_r(e['rho'])}{'*' if e['verdict'] in ('weak', 'strong') else ' '}")
        tag = ("跟著走" if ll["follow"] else "") + (f" 領先{ll['lead']}日" if ll["lead"] else "")
        g = a.get("gr") or {}
        ga, gb = g.get("A") or {}, g.get("B") or {}
        gs = (f"A p={ga.get('p')} q={ga.get('q')} {VERD.get(ga.get('verdict'), '—')}｜"
              f"B p={gb.get('p')} q={gb.get('q')} {VERD.get(gb.get('verdict'), '—')}")
        print(f"  {sid:5s} 起 {a['first'] or '—':10s} 之前 {past}｜之後 {' '.join(fut)} {tag:10s}｜{gs}")
    print("\n■ 進入過熱／過冷事件（之後 20／60 日，和這一項有 0～100 的日子比）")
    for sid in list(S.DIMS) + list(S.KEYS):
        a = rel.get(sid)
        if not a:
            continue
        cells = []
        for kind, nm in (("hot", "過熱"), ("cold", "過冷")):
            ev = a["evt"][kind]
            parts = []
            for h in S.EVT_FWD:
                e = ev[str(h)]
                parts.append(f"{h}日 差 {_p(e['diff'])} [{_p(e['lo'])}, {_p(e['hi'])}] {S.EV_VERDICT[e['verdict']]}")
            cells.append(f"{nm} {ev[str(S.EVT_FWD[0])]['n']:3d} 次 " + "、".join(parts))
        print(f"  {sid:5s} " + "｜".join(cells))


def deriv_report(res: dict) -> None:
    dv = res.get("deriv") or {}
    print("\n■ 邊際變化（核心 13 項；每週樣本）")
    for k, a in dv.items():
        for h, e in a["h"].items():
            st = " ".join(f"{s}:{e['states'][s]['n']}週/{e['states'][s]['runs']}段 {_p(e['states'][s]['diff'])} "
                          f"{VERD[e['states'][s]['verdict']]}" for s in ("1", "2", "3", "4"))
            ac, pc = e["acc"], e["pc"]
            print(f"  {k:4s} {h:>3s}日 二階 ρ={_r(ac['rho'])} [{_r(ac['lo'])}, {_r(ac['hi'])}] {VERD[ac['verdict']]}｜"
                  f"偏相關 {_r(pc['r'])} [{_r(pc['lo'])}, {_r(pc['hi'])}] p={pc['p']} q={pc['q']} {VERD[pc['verdict']]}｜{st}")


V6 = {"pred": "有預測性", "in_only": "內有外無", "in_untested": "內有(未測外)", "none": "看不出", "few": "樣本不足"}


def _pp(x, k: int = 2) -> str:
    return "—" if x is None else f"{100 * x:+.{k}f}"


def _b(e: dict) -> str:
    """係數（百分點）、Newey–West t、重抽區間、q、前後兩半、判定。"""
    if not e:
        return "—"
    if e.get("b") is None:
        return f"n={e.get('n', 0):3d} 樣本不足"
    t, q = e.get("t"), e.get("q")
    return (f"n={e['n']:3d} b={_pp(e['b'])} t={'—' if t is None else f'{t:+.2f}'} [{_pp(e.get('lo'))}, {_pp(e.get('hi'))}] "
            f"q={'—' if q is None else f'{q:.3f}'} 半 {_pp(e.get('h1'))}/{_pp(e.get('h2'))} {V6.get(e.get('v'), '')}")


def m6_report(res: dict) -> None:
    """第六版（第 15.11 節）：主要假說、各項延遲反應與樣本外、組、狀態、轉折事件、延伸樣本。"""
    m6 = res.get("m6")
    if not m6:
        return
    print(f"\n■ 第六版：每月樣本 {m6['sample']['a']}～{m6['sample']['z']}（{m6['sample']['T']} 個月），樣本外 {m6['sample']['oos_start']} 起")
    print("  主要假說（重抽 p、Holm 校正後 p、是否通過）")
    for h, e in m6["primary"].items():
        b = e.get("b")
        bs = "—" if b is None else (f"{[round(100 * x, 2) for x in b]}" if isinstance(b, list) else f"{100 * b:+.2f}")
        print(f"   {h} n={e['n']} b={bs} p={e.get('p')} holm={e.get('holm')} 通過={e.get('pass')}  {e['what']}")
    for k, e in m6["items"].items():
        print(f"\n  ◆ {k}（X2 起 {e['first']}；L2 放 X1＝{e['x1']}）摘要 {e['sum']}")
        for part, nm in (("d", "延遲"), ("c", "累積")):
            for ws, r in e["l1"][part].items():
                oo = e["oos"].get(ws)
                os_ = ""
                if oo:
                    c = oo["cw"].get("m2>m1") or {}
                    os_ = f"｜外 n={oo['n']} R²={c.get('r2')} CWp={c.get('p')}"
                print(f"    L1 {nm} {ws:6s} {_b(r)}{os_}")
        for ws, r in e["l2"].items():
            print(f"    L2 {ws:6s} {_b(r)}")
        for ws, r in e["l3a"].items():
            print(f"    L3a {ws:6s} {_b(r)}")
        for zn in ("bull", "hike"):
            for ws, r in e["l3c"][zn].items():
                print(f"    L3c {zn} {ws:6s} {_b(r)}")
        st = e["l3b"]["12"]
        print("    L3b 12 個月 " + "｜".join(f"{s}:{v['n']}月/{v['runs']}段 差{_p(v['diff'])} {VERD[v['verdict']]}" for s, v in st.items()))
        l6 = e["l6"]
        print(f"    L6 事件 {l6['n']} 次（一階 0：{l6['flat']}）" + "｜".join(
            f" {kd}:{v['n']}次 12月差{_p(v['h']['12']['diff'])} {VERD[v['h']['12']['verdict']]}" for kd, v in l6["kinds"].items()))
    for nm, e in m6["groups"].items():
        print(f"\n  ◆ 組 {nm}（起 {e['first']}）摘要 {e['sum']}")
        for part in ("d", "c"):
            for ws, r in e["l1"][part].items():
                print(f"    L4 {ws:6s} {_b(r)}")
    for part in ("d", "c"):
        for ws, r in m6["l4"]["inter"][part].items():
            print(f"    L4 交互 {ws:6s} {_b(r)}")
    for h, tab in m6["l4"]["states"].items():
        print(f"    L4 四狀態 {h} 個月 " + "｜".join(f"{s}:{v['n']}月/{v['runs']}段 差{_p(v['diff'])} {VERD[v['verdict']]}"
                                             for s, v in tab.items()))
    print("\n  組的樣本外（R² 對過去平均／對 M1；Clark–West p）")
    for ws, g in m6["goos"].items():
        mm = g["models"]
        cells = " ".join(f"{mo}:{mm[mo].get('r2_0')}/{mm[mo].get('r2_1', '')}" for mo in mm if mo != "m0")
        cw = " ".join(f"{k}:{v['p']}" for k, v in g["cw"].items())
        print(f"   {ws:6s} n={g['n']} {cells}｜CW {cw}｜λ {g.get('lam')}")
    ext = m6.get("ext")
    if ext:
        print(f"\n  延伸樣本 {ext['a']}～{ext['z']}：H1 {_b(ext['H1'])}｜H4 {_b(ext['H4'])}")
        for nm, e in ext["l1"].items():
            print(f"   {nm:8s} " + "｜".join(f"{ws} {100 * r['b']:+.2f} p={r['p']}" if r.get("b") is not None else f"{ws} —"
                                          for ws, r in e["d"].items()))


if __name__ == "__main__":
    main()
