"""配置頁・策略總覽（docs/lab_ia_v5_plan.md 第 15.4、18 節）：全部策略一張表，狀態只有四種。

使用者 2026-10-23：「妳可以有專門一個區是把所有的策略列過去，可以專門去看總策略的狀況」「沒用的策略那些全部拿掉毫無意義」。
- 使用中＝在配置裡（交易計畫本身、台股機動的新飆股與 ★ 個股策略、美股機動的強勢品質股）。
- 觀察中＝回測過、沒有放進配置（個股策略 ●、總經策略 ★／●、期貨加碼、紙上記錄中的飆股）；要用的話在對話裡說「納入」。
- 候選＝每週新找、先寫規則再回測的（docs 第 6、24 節；candpage.board_rows，決定之後換到觀察中或淘汰）。
- 淘汰＝試過沒有用的，一列一句原因，讓人知道試過什麼、不重複。

自動列的狀態來自研究檔的判定（advice、xsadvice、core、ussxqm、tilt），不重算任何回測；
沒有研究檔判定的列與使用者的決定寫在 config/strategy_board.json（override 可以蓋過自動列的狀態）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONF = ROOT / "config" / "strategy_board.json"

STATUS = ("use", "obs", "cand", "out")
ST_NAMES = {"use": "使用中", "obs": "觀察中", "cand": "候選", "out": "淘汰"}
ST_NOTE = {"use": "在上面的配置裡", "obs": "回測過、沒有放進配置；要用就在對話說「納入」",
           "cand": "每週新找、先寫規則再回測；回「試用／納入／不納入」", "out": "試過沒有用"}
MK_NAMES = {"tw": "台股", "spx": "S&P 500", "ixic": "那斯達克", "ndx": "那斯達克 100", "sox": "費半"}
MK_GROUP = {"tw": "tw", "spx": "us", "ixic": "us", "ndx": "us", "sox": "us"}
TYPES = ("配置", "個股", "指數型")
OBS_SHOW = 8                                  # 觀察中先列幾條，其餘收起


def _pc(x, d: int = 1, sign: bool = False) -> str:
    if x is None:
        return "—"
    s = f"{abs(x):.{d}f}%"
    if sign:
        s = ("+" if x > 0 else "−" if x < 0 else "") + s
    elif x < 0:
        s = "−" + s
    return s


def _wan(m) -> str:
    return "—" if m is None else f"{m * 100:,.0f} 萬"


def _plain(s: str | None) -> str:
    """策略總覽用字：對照一律寫「任一天」（docs 第 8 節第 3 條）。"""
    return (s or "").replace("隨便挑同樣天數", "任一天").replace("隨便挑一天", "任一天").replace("隨便挑", "任一天")


def load_conf(path: Path | None = None) -> dict:
    try:
        C = json.loads((path or CONF).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rows": [], "override": {}}
    C.setdefault("rows", [])
    C.setdefault("override", {})
    return C


# ── 自動列 ─────────────────────────────────────────────────────────────────────

def _plan_name(mk: str) -> str:
    """「兩成長抱＋警訊（台股）」；長抱 0%＝「全部機動＋警訊（美股）」（比例照 corespec 的 core_of）。"""
    from . import corepage as CPG
    c = CPG.core_w(mk)
    return ("全部機動" if c <= 0 else f"{CPG.cheng(c)}長抱") + ("＋警訊（台股）" if mk == "tw" else "＋警訊（美股）")


def _plan_how(mk: str, stk: dict, qm_on: bool) -> str:
    from . import corepage as CPG
    c, w = CPG.core_w(mk), CPG.sat_w(mk)
    head = "" if c <= 0 else f'{"0050" if mk == "tw" else "S&P 500"} {CPG.cheng(c)}一直抱著；'
    part = "全部" if c <= 0 else CPG.cheng(w)
    if mk == "tw":
        n = len(stk.get("st") or [])
        return (head + f"{part}一半買新飆股、一半跟著" + (f" {n} 條" if n else "") + "個股策略，沒有部位的放現金；"
                f"兩個以上警訊就把{part}換成現金")
    what = "買美股強勢品質股（最多 8 檔，空位放現金）" if qm_on else "買 S&P 500"
    return head + f"{part}{what}；兩個以上警訊或總經策略全部空手就把{part}換成現金"


def plan_rows(bundle: dict | None) -> list[dict]:
    """交易計畫本身（台股、美股）：使用中。成績＝研究檔的「照計畫做」對「一直抱著」；今天＝股票占全部資金（空位放現金）。"""
    from . import corepage as CPG
    B = bundle or {}
    R, nows, qm, stk = B.get("R") or {}, B.get("now") or {}, B.get("qm"), B.get("stk") or {}
    out = []
    for mk, gid in (("tw", "tw"), ("spx", "us")):
        on = mk == "spx" and CPG.qm_on("spx", qm)
        sc = (((R.get("mk") or {}).get(mk) or {}).get("sc") or {})
        s = sc.get("plan") or sc.get("rule")
        if on:
            p = CPG._qm_plan("spx", qm).get("new")
            if p:
                s = p
        row = {"id": f"{gid}:plan", "name": _plan_name(mk), "mk": MK_NAMES["tw"] if mk == "tw" else "美股", "mkk": gid, "type": "配置",
               "st": "use", "how": _plan_how(mk, stk, on), "go": {"go": gid}}
        if s:
            row.update({"perf": f"年化 {_pc((s['plan'].get('cagr') or 0) * 100)}", "ref": f"一直抱著 {_pc((s['hold'].get('cagr') or 0) * 100)}",
                        "mdd": _pc(s["plan"]["mdd"] * 100, 0), "mddr": _pc(s["hold"]["mdd"] * 100, 0),
                        "sub": f"{s['a'][:4]} 年起 100 萬變 {_wan(s['plan']['m'])}（一直抱著 {_wan(s['hold']['m'])}）"})
        N = nows.get(mk)
        if N:
            sw = CPG.stock_w(mk, N, stk if mk == "tw" else None, qm if mk != "tw" else None)[1]
            row["today"] = f"股票 {CPG.pct0(sw)}" + ("・要調整" if N.get("due") else "") + f"・警訊 {N['n']}／{len(N['fams'])}"
        out.append(row)
    return out


def boom_rows(bundle: dict | None) -> list[dict]:
    """台股機動的一半：新飆股（corespec VER 4；飆股前瞻記錄的 R60 那本帳）。成績＝那本帳的回測（2019 起每年只用以前的資料找條件）。"""
    from . import corepage as CPG
    B = bundle or {}
    R, stk = B.get("R") or {}, B.get("stk") or {}
    plan = ((((R.get("mk") or {}).get("tw") or {}).get("sc") or {}).get("plan")) or {}
    bm = plan.get("boom") or {}
    if not bm and stk.get("boom") is None:
        return []
    P = stk.get("boom") or {}
    held, buys = len(P.get("hold") or []), len([x for x in P.get("buy") or [] if x.get("fill")])
    today = (f"持有 {held} 檔" if held else "空手") + (f"・{int(P['next'][5:7])}/{int(P['next'][8:10])} 買 {buys} 檔" if buys and P.get("next") else "") \
        + ("" if held or buys or not P.get("next_wk") else f"・名單 {int(P['next_wk'][5:7])}/{int(P['next_wk'][8:10])} 收盤產生")
    row = {"id": "tw:boom", "name": "新飆股（台股機動的一半）", "mk": "台股", "mkk": "tw", "type": "個股", "st": "use",
           "how": f"每週五收盤用之前幾年找出來的條件挑股票、依強勢排；下一個交易日開盤買，每檔約占全部資金 {CPG._wp(CPG._boom_slot(stk))}，抱 60 個交易日",
           "go": {"go": "tw", "at": "cf-tw-sx"}, "today": today}
    if bm.get("cagr") is not None:
        h = bm.get("hold") or {}
        row.update({"perf": f"年化 {_pc(bm['cagr'] * 100)}", "mdd": _pc(bm["mdd"] * 100, 0),
                    "sub": f"{bm['a'][:4]} 年起那本帳本身"})
        if h.get("cagr") is not None:
            row.update({"ref": f"大盤 {_pc(h['cagr'] * 100)}", "mddr": _pc(h["mdd"] * 100, 0)})
    return [row]


def _stk_today(k: str, A: dict) -> str:
    """個股策略今天：持有幾檔、下一件事（日期＋動作）。"""
    held = sum(len(e.get("items") or []) for c in (A.get("opp") or {}).get("cards") or [] if c.get("k") == k for e in c.get("held") or [])
    ev = sorted((e for e in A.get("cal") or [] if e.get("k") == k and e.get("d")), key=lambda e: (e["d"], 0 if e.get("at") == "開盤" else 1))
    bits = [f"持有 {held} 檔"] if held else []
    if ev:
        e = ev[0]
        n = len(e.get("items") or [])
        what = e.get("act") or ""
        if what == "買進" and n:
            what = f"買 {n} 檔"
        elif what == "買進" and e.get("pending"):
            what = "買新名單"
        elif what == "賣出":
            what = "賣"
        bits.append(f"{int(e['d'][5:7])}/{int(e['d'][8:10])} {what}")
    return "・".join(bits) or "空手"


def stk_rows(A: dict | None, stk: dict | None) -> list[dict]:
    """個股策略（advice.book）：在台股機動裡的＝使用中；其他 ★／●＝觀察中；○／—＝淘汰。高股息只當避開清單（觀察中）。"""
    A = A or {}
    use = {s["k"] for s in (stk or {}).get("st") or []}
    out = []
    for b in A.get("book") or []:
        k, t = b["k"], b.get("tier")
        e, al = b.get("exp") or {}, b.get("all") or {}
        st = "use" if k in use else "obs" if t in ("good", "ref") else "out"
        u = b.get("unit") or "次"
        row = {"id": f"tw:{k}", "name": b.get("name") or k, "mk": "台股", "mkk": "tw", "type": "個股", "st": st,
               "how": b.get("how") or "", "go": {"go": "st", "at": f"st-{k}"}, "today": _stk_today(k, A)}
        if k == "hd":
            row.update({"name": "高股息換股・避開清單", "how": "高股息 ETF 換股期間，估計被動買賣很大的股票先避開", "today": "—",
                        "perf": "—", "mdd": "—"})
        elif al.get("cagr") is not None:
            row.update({"perf": f"年化 {_pc(al['cagr'])}", "ref": f"大盤 {_pc(al.get('tr_cagr'))}",
                        "mdd": _pc(al.get("mdd"), 0), "mddr": _pc(al.get("tr_mdd"), 0),
                        "sub": f"每{u}平均 {_pc(e.get('avg'), 1, True)}・{e.get('win')}% 賺錢" if e.get("n") else ""})
        elif e.get("n"):
            row.update({"perf": f"每{u} {_pc(e.get('avg'), 1, True)}", "ref": f"大盤 {_pc(e.get('mk'), 1, True)}",
                        "mdd": f"最差一{('檔' if u == '檔' else '次')} {_pc(e.get('lo'), 1, True)}",
                        "sub": f"{e.get('n')} {u}・{e.get('win')}% 賺錢"})
        if st == "out":
            j = b.get("j") or {}
            row["why"] = "次數不夠" if t == "few" else f"每一筆賺錢的比例 {j.get('win', 0):.0f}%，賺錢的比例和幅度都不夠"
        out.append(row)
    return out


def qm_rows(bundle: dict | None) -> list[dict]:
    """美股機動：美股強勢品質股（ussx_qm.json 判定過了＝使用中）。"""
    from . import corepage as CPG
    qm = (bundle or {}).get("qm")
    R = (qm or {}).get("R") or {}
    if not R:
        return []
    on = CPG.qm_on("spx", qm)
    sl = ((R.get("sleeve") or {}).get("main")) or {}
    bm = ((R.get("bench") or {}).get("spx_tr")) or {}
    n = CPG._qm_now(qm)
    held = len(n.get("hold") or [])
    buys = len(n.get("buy") or [])
    today = (f"持有 {held} 檔" if held else "空手") + (f"・{int(n['next'][5:7])}/{int(n['next'][8:10])} 買 {buys} 檔" if buys and n.get("next") else "")
    row = {"id": "us:qm", "name": "美股強勢品質股（美股機動）", "mk": "美股", "mkk": "us", "type": "個股", "st": "use" if on else "obs",
           "how": "每週五挑強勢、賺錢的中大型股，最多 8 檔；收盤跌破 50 日線就賣", "go": {"go": "us"}, "today": today}
    if sl.get("cagr") is not None:
        row.update({"perf": f"年化 {_pc(sl['cagr'] * 100)}", "ref": f"S&P 500 含息 {_pc((bm.get('cagr') or 0) * 100)}",
                    "mdd": _pc(sl.get("mdd", 0) * 100, 0), "mddr": _pc((bm.get("mdd") or 0) * 100, 0),
                    "sub": f"{(sl.get('a') or '')[:4]} 年起這套規則本身"})
    return [row]


def mac_rows(MAC: dict | None) -> list[dict]:
    """總經策略（指數型，xsadvice.build 的 book）：★／●＝觀察中；○／—＝淘汰（原因＝沒過的那一條）。"""
    M = MAC or {}
    out = []
    for mk in M.get("mks") or []:
        for b in ((M.get("m") or {}).get(mk) or {}).get("book") or []:
            k, t, e = b["k"], b.get("tier"), b.get("exp") or {}
            st = "obs" if t in ("good", "ref") else "out"
            row = {"id": f"{mk}:{k}", "name": b.get("name") or k, "mk": MK_NAMES.get(mk, mk), "mkk": MK_GROUP.get(mk, "us"),
                   "ix": mk, "type": "指數型", "st": st, "how": _plain(b.get("how")), "today": b.get("tag") or "",
                   "go": {"go": "macst", "at": f"ms-{k}", "gm": mk},
                   "perf": f"年化 {_pc(e.get('cagr'))}", "ref": f"買進持有 {_pc(e.get('bcagr'))}",
                   "mdd": _pc(e.get("mdd"), 0), "mddr": _pc(e.get("bmdd"), 0)}
            if b.get("kind") == "trade" and e.get("n"):
                row["sub"] = f"每筆 {_pc(e.get('avg'), 2, True)}・勝率 {e.get('win')}%（任一天 {e.get('base')}%）"
            elif b.get("kind") == "dip" and e.get("n"):
                row["sub"] = f"{e.get('n')} 次・抱完賺錢 {e.get('win')}%（任一天 {e.get('base')}%）"
            if st == "out":
                row["why"] = _plain(b.get("fail")) or "沒有過判定"
            out.append(row)
    return out


def tilt_rows() -> list[dict]:
    """期貨加碼（tilt 研究檔）：放上網頁的規則＝觀察中，其他＝淘汰。成績寫台股。"""
    try:
        from . import findings as FD
        from . import tilt as TL
        from . import tiltspec as TS
        R = TL.load()
    except Exception:                                    # noqa: BLE001 —— 研究檔讀不到就不列
        return []
    if not R:
        return []
    T = FD.tilt(R, "tw", live=False)
    if not T:
        return []
    page = R.get("page") or {}
    ok_mk = [MK_NAMES[m] for m in TS.JUDGED if ((((R.get("mk") or {}).get(m) or {}).get("rules") or {}).get("K4") or {}).get("v") == "better"]
    out = []
    for k in TS.PAGE_RULES + tuple(x for x in TS.RULES if x not in TS.PAGE_RULES):
        x = T["rows"].get(k)
        if not x:
            continue
        ok = bool((page.get(k) or {}).get("ok"))
        nm = TS.RULES[k]["name"]
        row = {"id": f"all:tilt:{k}", "name": f"期貨加碼：{nm}" if not nm.startswith("200") else "200 日線上用期貨多拿 5 成",
               "mk": "、".join(ok_mk) if ok and ok_mk else "台股", "mkk": "all", "type": "指數型", "st": "obs" if ok else "out",
               "how": "平常照樣抱著；訊號成立時另外用期貨多拿 5 成，訊號沒了就平掉",
               "perf": f"年化 {_pc((x.get('cagr') or 0) * 100)}", "ref": f"一直抱著 {_pc((T['bh'].get('cagr') or 0) * 100)}",
               "mdd": _pc(x["dd"] * 100, 0), "mddr": _pc(T["bh"]["dd"] * 100, 0),
               "sub": f"台股 {(T.get('start') or '')[:4]} 年起 100 萬變 {_wan(x['m'])}（固定多拿同樣多 {_wan(x['fm'])}）",
               "today": "", "go": {}}
        if not ok:
            row["why"] = "多賺的部分來自多拿股票，訊號本身沒有比固定多拿同樣多好"
        out.append(row)
    return out


def _sxlive_today() -> str:
    try:
        L = json.loads((ROOT / "data" / "lab" / "sxlive.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "還沒有紀錄"
    wk = L.get("weeks") or L.get("w") or {}
    n = len(wk) if isinstance(wk, (dict, list)) else 0
    return f"已記 {n} 週" if n else "還沒有紀錄"


def cand_rows() -> list[dict]:
    """新策略候選（candpage.board_rows）：沒決定＝候選；試用、納入＝觀察中；不納入＝淘汰。讀不到就不列。"""
    try:
        from . import candpage
        return candpage.board_rows()
    except Exception as e:                               # noqa: BLE001 —— 候選讀不到不影響其他列
        print(f"[策略] 候選讀不到：{type(e).__name__}: {e}")
        return []


def conf_rows(C: dict) -> list[dict]:
    out = []
    for r in C.get("rows") or []:
        x = {k: v for k, v in r.items() if k != "today"}
        x["mk"] = {"tw": "台股", "us": "美股", "all": "台股・美股"}.get(r.get("mkk"), r.get("mkk") or "")
        x["today"] = _sxlive_today() if r.get("today") == "sxlive" else (r.get("today") or "")
        x.setdefault("go", {})
        out.append(x)
    return out


# ── 組起來 ─────────────────────────────────────────────────────────────────────

def build(data: dict | None, bundle: dict | None, conf: dict | None = None) -> dict:
    """→ {"rows": [...], "n": {狀態: 條數}, "nm": {市場群組: {狀態: 條數}}}；排序：狀態 → 類型（配置、個股、指數型）→ 市場 → 原本的順序。"""
    data = data or {}
    C = conf if conf is not None else load_conf()
    rows = plan_rows(bundle) + boom_rows(bundle) + stk_rows(data.get("adv"), (bundle or {}).get("stk")) + qm_rows(bundle) \
        + tilt_rows() + mac_rows(data.get("mac")) + cand_rows() + conf_rows(C)
    ov = C.get("override") or {}
    for r in rows:
        if r["id"] in ov and ov[r["id"]] in STATUS:
            r["st"] = ov[r["id"]]
    seen, uniq = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    mko = {"tw": 0, "us": 1, "all": 2}
    ixo = {"tw": 0, "spx": 1, "ndx": 2, "ixic": 3, "sox": 4}
    order = {r["id"]: i for i, r in enumerate(uniq)}
    uniq.sort(key=lambda r: (STATUS.index(r["st"]), TYPES.index(r["type"]) if r["type"] in TYPES else 9,
                             mko.get(r.get("mkk"), 9), ixo.get(r.get("ix"), 0), order[r["id"]]))
    n = {s: sum(1 for r in uniq if r["st"] == s) for s in STATUS}
    nm = {g: {s: sum(1 for r in uniq if r["st"] == s and r.get("mkk") in (g, "all")) for s in STATUS} for g in ("tw", "us")}
    return {"rows": uniq, "n": n, "nm": nm}
