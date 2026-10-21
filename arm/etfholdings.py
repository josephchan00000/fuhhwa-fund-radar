"""ETF 每日持股與「當日貢獻」歸因（2026-07-29 使用者需求）。

主動式 ETF 依規定**每日揭露完整持股**（各投信申購買回清單／持股頁），被動 ETF 亦多有揭露。
本模組把它變成儀表板 ETF 列可展開的一張明細：

    持股｜權重｜Δ股數（加減碼）｜Δ權重｜個股當日漲跌｜對 ETF 當日漲跌的貢獻(pp)

貢獻 = 權重% × 個股當日漲跌% ÷ 100（單位：百分點 pp）。把全部持股的貢獻加總，
約等於該 ETF 當日淨值漲跌（差額＝現金部位／期貨／費用／揭露時點差 → 誠實列為「其他・現金」殘差，
不硬湊）。

個股漲跌／收盤一律取**最新交易日**那一天的官方值（2026-10-21 錯日事故後改；docs/etf_chg_fix_plan.md）：
detail.pd＝報價日、每列 qd＝該列報價日、pend＝海外當地還沒收盤——網頁只顯示 qd＝pd 的數字。
持股快照日（detail.date）可以早於 pd（被動式隔夜才發、來源停更），網頁兩個日期都標。

資料層 `data/etf_holdings.json`（**必須入庫**——跨日累積才有「昨天 vs 今天」可比，
同 etf_watch／macro_chips 的坑）：

    {"as_of": 抓取時戳,
     "etfs": {code: {"date": 揭露日, "prev_date": 前一揭露日, "src": 來源標記,
                     "holdings": [{"stock_id","name","shares","weight"}],
                     "prev": {stock_id: {"shares","weight"}},
                     "fut": [期貨列], "prev_fut": [前一揭露日的期貨列]}},   # 見「期貨部位」
     "diag": {code: 抓取診斷字串}}

合併鐵則（同專案慣例）：本次抓到才推進；抓不到＝原封保留既有揭露，**絕不洗成空**。
只有「本次揭露日 != 既有揭露日」時才把既有 holdings 降級為 prev（同日重抓不會把
prev 洗成今天自己、讓 Δ 全變 0）。

本容器 proxy 擋所有投信站 → 抓取只在正式區 CI 跑；容器內只讀落檔建表。
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from . import clock

ROOT = Path(__file__).resolve().parent.parent
DATA_FP = ROOT / "data" / "etf_holdings.json"

_TOP_N = 12          # 展開明細預設列出的檔數（其餘併「其他 N 檔合計」一列）


# ── 資料層 ────────────────────────────────────────────────────────────

def load() -> dict | None:
    try:
        return json.loads(DATA_FP.read_text(encoding="utf-8"))
    except Exception:
        return None


def _index(holdings: list[dict]) -> dict[str, dict]:
    return {str(h.get("stock_id")): h for h in (holdings or []) if h.get("stock_id")}


# ── 非持股列過濾（來源口徑對齊；2026-08-05 使用者抓到 00986D「全部出清」） ──────
#
# 各來源的「列宇宙」不一樣：復華 assetsExcel（fhtrust）依舊管線慣例只給證券／債券區段、
# 期貨避險列在 `_from_fhtrust` 就被剔除（另存「期貨部位」，見下），也不列現金部位；etfinfo 的 PCF 快照卻把
# **期貨、保證金(MARGIN)、應付買回款(PAYABLES FOR UNITS REDEEMED)、扣除應付證券款
# (AFTER DEDUCTING SECURITIES PURCHASES AMOUNT)** 一併給出來。
# 主來源在兩者之間切換時，這批列就會整批冒出「新增」、隔天整批「出清」——00986D
# 2026-07-30（etfinfo 頂上來）11 檔假新增 → 07-31（fhtrust 回來）11 檔假出清，
# 其中 PFUR_NTD／DA_USD／M_AUD 的前一日股數是**負數**（應付款），出清 Δ＝0−(負)＝正，
# 於是表上出現「+14,749 張」卻標「出清」的自相矛盾（使用者原話：「加碼的也出清？」）。
#
# 它們本來就不是持股，任何來源都不該進 diff。名稱與代號兩路認：
_NH_ID = re.compile(r"^(?:M|DA|PFUR|PFSP|RFSS|CASH|FX)_[A-Z]{3}$", re.I)
_NH_NAME = re.compile(
    r"MARGIN|PAYABLE|RECEIVABLE|AFTER\s+DEDUCTING|CASH|DEPOSIT|ACCRUED"
    r"|現金|存款|保證金|應付|應收|預付|其他資產|淨值|合計|期貨", re.I)
# 期貨合約代號＝年月＋商品碼（`202609US`＝2026 年 9 月美國長債期貨、`202609TY`＝10 年期）。
# 台股代號純數字、外股 etfinfo 給的是帶空格的 `TLTW US` → 不會誤殺。
_NH_FUT = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])[A-Z]{2,3}$")
# 另兩種寫法（2026-10-21 盤查）：商品碼在前 `US202612`（00986D 的 etfinfo）、帶冒號
# `UB:2026-12:B`（00987D 超長美債期貨，87 口、權重 36.55%）。ISIN 是 12 碼，不會誤殺。
_NH_FUT2 = re.compile(r"^[A-Z]{2,3}(20\d{2})(0[1-9]|1[0-2])$"
                      r"|^[A-Z0-9]{1,4}:(20\d{2})-(0[1-9]|1[0-2])(?::[A-Z0-9]{1,3})?$")


def is_non_holding(sid: str, name: str = "") -> bool:
    """現金／保證金／應付款／期貨等「非持股列」→ True（不進 diff、不算加減碼）。"""
    sid = str(sid or "").strip()
    return bool(_NH_ID.match(sid) or _NH_FUT.match(sid) or _NH_FUT2.match(sid)
                or _NH_NAME.search(str(name or "")))


def drop_non_holdings(rows: list[dict]) -> list[dict]:
    """濾掉非持股列，讓各來源的列宇宙對齊（抓取端各來源共用）。來源標明 kind="future" 的也算。"""
    return [r for r in (rows or [])
            if r.get("kind") != "future"
            and not is_non_holding(r.get("stock_id"), r.get("name") or r.get("stock_name"))]


# ── 期貨部位（2026-10-21 使用者同意另列：00987D 的期貨是量化多空策略的本體） ──────────
#
# 期貨照舊不進持股 diff，理由不變：①換月——代號一季一換，用代號比會變成「出清＋新增」；
# ②權重是名目曝險——期貨只付保證金，00987D 兩檔公債 87.41%＋期貨 36.55%＝約 124%；
# ③口數和股數／面額不能比大小。但 00987D「主動統一美國公債量化增益」看多時用期貨把美債曝險
# 拉到 120%～130%、看空時用期貨對沖——期貨口數才是經理人現在的判斷，丟掉它，持股詳情只剩
# 兩檔一直抱著的公債。所以**另存一區**：
#   entry["fut"]      ＝本次揭露的期貨列 [{"id","name","qty"(口數，空單為負),"weight"(名目%),"amt"}]
#   entry["prev_fut"] ＝前一揭露日的期貨列（揭露日推進時由 fut 降級，規則同 prev）
# fut 為 None＝主來源沒有揭露期貨（Yahoo 月度前十大）；[]＝有揭露、沒有期貨部位。
_FUT_NOT = re.compile(r"保證金|MARGIN|應付|應收|PAYABLE|RECEIVABLE|現金|存款|DEPOSIT", re.I)


def is_future(sid: str, name: str = "") -> bool:
    """期貨合約列 → True（另存「期貨部位」）。保證金、應付款等其他非持股列不算。"""
    sid, name = str(sid or "").strip(), str(name or "")
    if _NH_ID.match(sid) or _FUT_NOT.search(name):
        return False
    return bool(_NH_FUT.match(sid) or _NH_FUT2.match(sid) or "期貨" in name)


def fut_row(sid, name, qty, weight, amt=None) -> dict:
    """期貨列統一格式（各來源共用）。"""
    nm = clean_name(str(name or "").strip())
    return {"id": str(sid or "").strip(), "name": nm or None,
            "qty": (int(round(float(qty))) if qty is not None else None),
            "weight": (round(float(weight), 4) if weight is not None else None),
            "amt": (round(float(amt)) if amt is not None else None)}


def split_futures(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """→ (持股列, 期貨列)。持股列同 drop_non_holdings；期貨列轉成 fut_row 格式另存。"""
    fut = [fut_row(r.get("stock_id"), r.get("name") or r.get("stock_name"),
                   r.get("shares"), r.get("weight"), r.get("market_value"))
           for r in (rows or [])
           if r.get("kind") == "future"
           or is_future(r.get("stock_id"), r.get("name") or r.get("stock_name"))]
    return drop_non_holdings(rows), fut


# 合約代號 → (商品代號, 月份)：`UB:2026-12:B`、`US202612`、`202609TY`、彭博式 `TYZ6`
_FK_COLON = re.compile(r"^([A-Z0-9]{1,4}):(20\d{2})-(0[1-9]|1[0-2])(?::[A-Z0-9]{1,3})?$")
_FK_ROOT_YM = re.compile(r"^([A-Z]{1,4})(20\d{2})(0[1-9]|1[0-2])$")
_FK_YM_ROOT = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])([A-Z]{1,4})$")
_FK_LETTER = re.compile(r"^([A-Z]{1,4}?)([FGHJKMNQUVXZ])(\d{1,2})(?:\s+[A-Z]+)?$")
_MCODE = "FGHJKMNQUVXZ"                  # 期貨月份代碼，依序 1～12 月


def fut_key(sid) -> tuple[str, str | None]:
    """期貨代號 → (商品代號, 'YYYY-MM')。同一商品換月份＝轉倉，不算平倉再新建。
    認不出格式的代號整串當商品代號、月份 None（同代號照樣比口數，只是看不出換月）。"""
    s = str(sid or "").strip().upper()
    m = _FK_COLON.match(s) or _FK_ROOT_YM.match(s)
    if m:
        return m.group(1), f"{m.group(2)}-{m.group(3)}"
    m = _FK_YM_ROOT.match(s)
    if m:
        return m.group(3), f"{m.group(1)}-{m.group(2)}"
    m = _FK_LETTER.match(s)
    if m:
        y = int(m.group(3))
        if y >= 10:
            y += 2000
        else:                                   # 一位數年份：取最近的那一個十年
            now = clock.today_tw().year
            y += now - now % 10
            if y < now - 2:
                y += 10
        return m.group(1), f"{y:04d}-{_MCODE.index(m.group(2)) + 1:02d}"
    return s, None


def _signed_w(w, q):
    """名目曝險帶方向（空單為負）。來源可能把空單權重寫成正數，一律看口數正負。"""
    if w is None or not q:
        return w
    return abs(w) if q > 0 else -abs(w)


_FUT_NAME_YM = re.compile(r"^\s*20\d{2}(?:0[1-9]|1[0-2])\s*")    # 「202612 美國三十年期政府公債」的月份前綴


def _fut_groups(rows: list[dict] | None) -> dict[str, dict]:
    g: dict[str, dict] = {}
    for r in rows or []:
        root, ym = fut_key(r.get("id"))
        x = g.setdefault(root, {"name": None, "qty": 0, "w": 0.0, "nw": 0, "yms": set()})
        # 月份另欄顯示，名稱去掉月份前綴（同商品不同月份才合得成同一列的名稱）
        x["name"] = x["name"] or (_FUT_NAME_YM.sub("", r.get("name") or "") or None)
        x["qty"] += r.get("qty") or 0
        w = _signed_w(r.get("weight"), r.get("qty"))
        if w is not None:
            x["w"] += w
            x["nw"] += 1
        if ym:
            x["yms"].add(ym)
    return g


def _fut_act(a: dict | None, b: dict | None) -> str:
    """這次相對前一揭露日做了什麼（a＝本次、b＝前次，皆為 _fut_groups 的一項）。"""
    qa, qb = (a or {}).get("qty") or 0, (b or {}).get("qty") or 0
    side = "多單" if qa > 0 else ("空單" if qa < 0 else "")
    if not qb:
        return "新建" + side if qa else "不變"
    if not qa:
        return "平倉"
    if (qa > 0) != (qb > 0):
        return "多單轉空單" if qb > 0 else "空單轉多單"
    if qa == qb:
        return "不變"
    return side + ("加碼" if abs(qa) > abs(qb) else "減碼")


def fut_view(entry: dict | None) -> dict | None:
    """「期貨部位」區塊資料（純比較、不需網路）。主來源沒揭露期貨、或本次與前次都沒有期貨 → None。

    每個商品一列（同商品不同月份合在一起）：口數、名目曝險%（空單為負）、比前一揭露日加減幾口
    （dq＞0＝曝險變多）；月份換了＝轉倉。前一揭露日出自不同來源時，兩邊揭露範圍未必一致 →
    只比兩邊都有的商品（同持股的 xsrc 規則：新建／平倉不判定）。"""
    e = entry or {}
    fut, prev = e.get("fut"), e.get("prev_fut")
    if fut is None or not (fut or prev):
        return None
    cmp_ok = prev is not None and bool(e.get("prev_date"))
    src, psrc = e.get("src"), e.get("prev_src")
    xsrc = bool(cmp_ok and src and psrc and src != psrc)
    now, pre = _fut_groups(fut), (_fut_groups(prev) if cmp_ok else {})
    rows = []
    for root in list(now) + [k for k in pre if k not in now]:
        a, b = now.get(root), pre.get(root)
        if xsrc and not (a and b):
            if not a:
                continue
            b = None
        r = {"root": root, "name": (a or b)["name"],
             "qty": a["qty"] if a else 0,
             "w": (round(a["w"], 2) if a["nw"] else None) if a else 0.0,
             "ym": sorted(a["yms"]) if a else [], "pym": sorted(b["yms"]) if b else [],
             "dq": None, "act": None, "roll": False}
        if b is not None or (cmp_ok and not xsrc):
            r["dq"] = r["qty"] - ((b or {}).get("qty") or 0)
            r["act"] = _fut_act(a, b)
            r["roll"] = bool(a and b and a["yms"] and b["yms"] and a["yms"] != b["yms"])
            if r["roll"]:
                r["act"] = "轉倉" if r["act"] == "不變" else r["act"] + "・轉倉"
        rows.append(r)
    ws = [r["w"] for r in rows if r["qty"] and r["w"] is not None]
    return {"rows": rows, "net_w": round(sum(ws), 2) if ws else None,
            "date": e.get("date"), "prev_date": e.get("prev_date") if cmp_ok else None,
            "cmp": cmp_ok, "xsrc": [psrc, src] if xsrc else None}


def clean_name(name):
    """還原名稱裡的 HTML／XML 實體（`M&amp;G` → `M&G`）。

    復華 assetsExcel 的 sharedStrings 是 XML，2026-10-21 前解析沒還原實體，00998A 的
    `M&amp;G公開有限公司`、`MS&amp;AD保險集團控股公司` 帶著 `&amp;` 進了落檔；網頁再跳脫一次
    就顯示成字面「&amp;」。抓取端已修，這裡給讀取端與舊落檔用。"""
    return html.unescape(name) if isinstance(name, str) and "&" in name else name


def _clean_detail(det: dict | None) -> dict | None:
    """detail 裡所有名稱（完整持股、異動、報價列）還原實體；沒有要改的就原物件回傳。"""
    if not det:
        return det
    keys = ("all", "moves", "rows")
    if not any("&" in str(r.get("name") or "") for k in keys for r in (det.get(k) or [])):
        return det
    out = dict(det)
    for k in keys:
        if det.get(k):
            out[k] = [({**r, "name": clean_name(r["name"])} if "&" in str(r.get("name") or "") else r)
                      for r in det[k]]
    return out


def _snap_key(holdings: list[dict] | None) -> tuple:
    """快照指紋（代號＋股數＋權重）——用來認出「同一份檔案被標成不同揭露日」。"""
    return tuple(sorted((str(h.get("stock_id")), h.get("shares"), h.get("weight"))
                        for h in (holdings or []) if h.get("stock_id")))


def _prev_key(prev: dict | None) -> tuple:
    return tuple(sorted((str(k), v.get("shares"), v.get("weight"))
                        for k, v in (prev or {}).items()))


def merge_one(old: dict | None, new: dict | None) -> dict | None:
    """單檔 ETF 的揭露合併。

    · new 為空（本次抓不到）→ 原封回 old（絕不洗空）。
    · new 揭露日與 old 相同 → 只更新內容，**prev 保持不動**（同日重抓不可把 prev
      洗成今天自己，否則 Δ 股數全變 0、看起來像「都沒異動」）。
    · 揭露日推進 → old.holdings 降級為 prev。
    """
    if not new or not new.get("holdings"):
        return old
    old = old or {}
    # 日期倒退防呆（2026-07-30 實踩）：換來源時新來源可能給**較舊**的快照
    # （fhtrust T-1 vs 稍早 etfinfo 的當日快照）——若照常合併，較新的快照會被降級成
    # prev，儀表板出現「揭露日 07-28（對比 07-29）」的倒轉比較。舊的進不來，保留較新者。
    if old.get("date") and new.get("date") and str(new["date"]) < str(old["date"]):
        return old
    if old.get("date") and old["date"] == new.get("date"):
        return _drop_fake_prev({**new, "prev": old.get("prev") or {},
                                "prev_date": old.get("prev_date"),
                                "prev_src": old.get("prev_src"),
                                "prev_fut": old.get("prev_fut")})
    # 「同一份檔案被標成新的揭露日」防呆（2026-07-30 使用者抓到 00991A 假的「沒有變化」）：
    # 復華 assetsExcel 的資料日是**我們請求的日期**（`fhtrust.fetch_holdings` 回 iso_date），
    # 檔案本身可能還是舊的一份 → 揭露日往前跳、內容卻一模一樣，於是舊快照被降級成 prev、
    # Δ 全變 0，看板上就出現假的「本次無異動」。判準用**股數＋權重全等**：
    # 權重是市值比重，兩個不同交易日不可能 49 檔全部到小數第三位都相同（實測 00991A 就是）。
    # 遇到這種情形一律當「同一次揭露重抓」——不推進日期、不動 prev，寧可少報一天鮮度，
    # 也不假造一個「零異動日」。
    if old.get("holdings") and _snap_key(old["holdings"]) == _snap_key(new["holdings"]):
        return _drop_fake_prev({**new, "date": old["date"],
                                "prev": old.get("prev") or {},
                                "prev_date": old.get("prev_date"),
                                "prev_src": old.get("prev_src"),
                                "prev_fut": old.get("prev_fut")})
    # prev 一併存**名稱**（2026-07-30 使用者：有兩個股票代碼但沒有公司名）——
    # 出清標的今天已不在 holdings 裡，名稱只剩 prev 留得住；沒有它就只能顯示代號。
    prev = {sid: {"shares": h.get("shares"), "weight": h.get("weight"),
                  "name": h.get("name") or None}
            for sid, h in _index(old.get("holdings") or []).items()}
    # prev_src＝那份 prev 是**哪個來源**抓的。沒有它就無從得知這次的 Δ 是跨源比較
    # （見 contributions 的來源切換防呆）。prev 沿用舊 prev 時 prev_src 也一併沿用。
    # prev_fut＝前一揭露日的期貨列（見「期貨部位」）；舊落檔沒有 fut＝None，下一個揭露日起才比得出口數
    return _drop_fake_prev({**new, "prev": prev or (old.get("prev") or {}),
                            "prev_date": old.get("date") or old.get("prev_date"),
                            "prev_src": (old.get("src") if prev
                                         else old.get("prev_src")),
                            "prev_fut": (old.get("fut") if prev else old.get("prev_fut"))})


def _drop_fake_prev(entry: dict) -> dict:
    """prev 與今日 holdings 全等 → 那不是「昨天」，是同一份快照被誤標成兩天（見上方防呆）。
    留著它會讓儀表板顯示假的「本次無異動」；清掉後誠實顯示「尚無可對比的前一揭露日」。
    """
    if entry.get("prev") and _prev_key(entry["prev"]) == _snap_key(entry.get("holdings")):
        return {**entry, "prev": {}, "prev_date": None, "prev_src": None, "prev_fut": None}
    return entry


def merge(prev_doc: dict | None, fresh: dict[str, dict], diag: dict[str, str] | None = None) -> dict:
    """全體合併 → 新 doc（不落檔；落檔用 save）。"""
    old_etfs = ((prev_doc or {}).get("etfs") or {})
    etfs: dict[str, dict] = {}
    for code in set(old_etfs) | set(fresh or {}):
        merged = merge_one(old_etfs.get(code), (fresh or {}).get(code))
        if merged:
            etfs[code] = merged
    return {"as_of": clock.stamp_tw(), "etfs": etfs, "diag": diag or {}}


def save(doc: dict) -> bool:
    """落檔防呆：本次全空而既有落檔非空 → 不覆寫（回 False）。"""
    old = load()
    if not (doc.get("etfs") or {}) and (old or {}).get("etfs"):
        return False
    DATA_FP.parent.mkdir(parents=True, exist_ok=True)
    DATA_FP.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


# ── 跨源交叉驗證（2026-07-29 使用者指示：不必抓投信第一手，改彙整站＋雙重驗證） ──

_XCHK_TOP_N = 10          # 以主來源前 N 大做重合度比對
_XCHK_OVERLAP = 0.6       # 前 N 大至少 60% 也出現在副來源
_XCHK_DW_PP = 0.75        # 共同持股權重差容忍（百分點）——兩站快照時點差一天內的正常波動

def cross_check(primary: list[dict], secondary: list[dict],
                weights: bool = True) -> dict:
    """兩個來源的持股清單交叉驗證 → {"status": "match"/"mismatch", ...細節}。

    比對（依 weights 分兩級）：
      ① 主來源前 10 大有多少也出現在副來源（重合度 ≥60%）——構成比對，永遠做；
      ② weights=True 時再比共同持股權重差最大值（≤0.75pp）。
    **weights=False＝「構成驗證」**（2026-07-29 教訓）：Yahoo 的 ETF 持股是**月度基準**、
    etfinfo 是每日 PCF 快照——跨基準日比權重是方法錯誤（實測 19/21 檔被誤判 mismatch，
    權重差 1.2–4.2pp 全是時點差）。此時只驗構成、max_dw 僅供參考記錄。
    不比股數——兩站股數口徑（張/股、揭露時點）常不同，比了只會誤殺。
    副來源為空不會呼叫本函式（那是「單源」，由上層標記）。"""
    sec_ids = {str(r.get("stock_id")) for r in secondary}
    top = [str(r.get("stock_id")) for r in
           sorted(primary, key=lambda r: -(r.get("weight") or 0))[:_XCHK_TOP_N]]
    hit = sum(1 for sid in top if sid in sec_ids)
    sec_w = {str(r.get("stock_id")): r.get("weight") for r in secondary}
    dws = [abs((r.get("weight") or 0) - (sec_w.get(str(r.get("stock_id"))) or 0))
           for r in primary
           if str(r.get("stock_id")) in sec_w
           and r.get("weight") is not None and sec_w.get(str(r.get("stock_id"))) is not None]
    max_dw = round(max(dws), 2) if dws else None
    ok = hit >= max(1, int(len(top) * _XCHK_OVERLAP))
    if weights:
        ok = ok and (max_dw is None or max_dw <= _XCHK_DW_PP)
    return {"status": "match" if ok else "mismatch", "weights_compared": weights,
            "top_hit": hit, "top_n": len(top), "n_common": len(dws), "max_dw": max_dw}


# ── 當日貢獻歸因 ──────────────────────────────────────────────────────

def _chg_pct(px: dict | None) -> float | None:
    """{close, change} → 當日漲跌%。change 為金額；前收＝close − change。"""
    if not px:
        return None
    close, chg = px.get("close"), px.get("change")
    if close is None or chg is None:
        return None
    prev = close - chg
    return round(chg / prev * 100, 2) if prev else None


_MOVE_N = 40         # 異動清單上限（方塊圖＋異動表用；其餘併「其餘 N 檔」）


def _kind(d_shares, is_new: bool, is_out: bool) -> str | None:
    """異動類型：新增／加碼／減碼／出清；None＝本次無異動或無可比基準。"""
    if is_out:
        return "out"
    if is_new:
        return "new"
    if d_shares is None or d_shares == 0:
        return None
    return "add" if d_shares > 0 else "cut"


def _moves(rows: list[dict], dropped: list[dict], move_n: int = _MOVE_N) -> dict:
    """異動清單（產業方塊圖／異動表用）。

    · 新增檔的「異動量」＝整個部位（prev 沒有它，Δ股數為 None 但實際是全額買進）；
      出清檔＝前一揭露日的全部股數（負值）。其餘為 Δ股數。
    · 排序依 |金額| 由大到小；無報價（海外／債券）時退回 |股數|——面積依據由
      `amount_basis` 誠實標明，不憑空補價。
    """
    out = []
    for r in rows + dropped:
        kind = _kind(r.get("d_shares"), bool(r.get("is_new")), bool(r.get("is_out")))
        if not kind:
            continue
        m_sh = r.get("shares") if kind == "new" else r.get("d_shares")
        if m_sh in (None, 0):
            continue
        # 海外報價（帶 ccy＝外幣）**不算金額**：USD/JPY/KRW 收盤 × 股數不可與台幣金額
        # 混入同一張方塊圖比面積——面積照舊退回股數口徑（漲跌％／貢獻不受影響）。
        close = r.get("close") if not r.get("ccy") else None
        amt = round(m_sh * close) if (close is not None) else None
        out.append({"stock_id": r["stock_id"], "name": r.get("name") or r["stock_id"],
                    "industry": r.get("industry"), "kind": kind,
                    "m_shares": m_sh, "lots": round(m_sh / 1000, 1),
                    "amount": amt, "weight": r.get("weight"),
                    "d_weight": r.get("d_weight")})
    # 面積依據：**全部異動都算得出金額**時才用金額；只要有一筆沒有（全球型 ETF 的海外
    # 持股沒有台股報價），整張圖改用股數——否則那些沒金額的會被靜靜濾掉，00988A 的 6 筆
    # 異動只畫得出 1 格（2026-07-30 使用者：「海外的明明有變動但沒有顯示出來」）。
    # 跨市場的股數不宜直接比大小，但「全部看得到」遠比「只看得到一格」重要，圖註會標明口徑。
    priced = sum(1 for m in out if m["amount"] is not None)
    all_priced = bool(out) and priced == len(out)
    key = (lambda m: -abs(m["amount"] or 0)) if all_priced else (lambda m: -abs(m["m_shares"]))
    out.sort(key=key)
    shown, rest = out[:move_n], out[move_n:]
    return {"moves": shown, "moves_n": len(out), "moves_rest_n": len(rest),
            "moves_rest_amount": (round(sum(m["amount"] or 0 for m in rest)) if rest else None),
            "amount_basis": "amount" if all_priced else "shares",
            "unpriced_n": len(out) - priced}


def contributions(entry: dict | None, quotes: dict[str, dict] | None,
                  ind: dict[str, str] | None = None,
                  top_n: int = _TOP_N,
                  names: dict[str, str] | None = None,
                  pd: str | None = None,
                  pending: set[str] | None = None,
                  prior: dict | None = None) -> dict | None:
    """單檔 ETF 的展開明細資料。

    entry   ＝ data/etf_holdings.json 的 etfs[code]
    quotes  ＝ {stock_id: {"close","change","name","date"}}——**全部是報價日 pd 那一天**
               （台股 arm/dayquotes.latest、海外 yahooq.fetch_foreign_on；date≠pd 的報價一律不用）
    pd      ＝ 報價日＝最新交易日（2026-10-21 使用者決定：漲跌一律用最新交易日，搭配各 ETF 最新揭露的持股）
    pending ＝ 海外當地 pd 那天還沒收盤的代號（列上標 pend，網頁顯示「待收盤」）
    prior   ＝ 上一班的 detail：這班沒拿到報價的列，沿用其中**同一報價日**（列的 qd＝pd）的值；
               日期不同一律不沿用（寧缺勿錯）

    每列：權重、Δ股數（加減碼）、Δ權重、個股當日漲跌%、貢獻 pp（＝權重% × 漲跌% ÷ 100）、
    qd（該列報價日；沒有漲跌＝None）、pend（待收盤）。
    依 |貢獻| 由大到小排；超過 top_n 者併成一列合計，避免展開後灌爆版面。
    無報價的持股仍列出（貢獻顯示 —），但不計入合計——寧可少算，不憑空補值。
    """
    holdings = (entry or {}).get("holdings") or []
    if not holdings:
        return None
    pr = prior or {}
    prior_rows = ({str(r.get("stock_id")): r for r in (pr.get("all") or []) if r.get("stock_id")}
                  if pd else {})
    # 出清列只用得到收盤（算金額）：上一班的 detail 也是同一報價日才沿用
    prior_px = ({str(r.get("stock_id")): (r.get("close"), r.get("ccy"))
                 for r in (pr.get("all") or []) + (pr.get("dropped") or [])
                 if r.get("stock_id") and r.get("close") is not None}
                if pd and pr.get("pd") == pd else {})
    prev = (entry or {}).get("prev") or {}
    # 跨來源比較防呆（2026-08-05 使用者：00986D「全部出清？加碼的也出清？」）：
    # prev 與今日 holdings 出自**不同來源**時，「某代號今天不在清單裡」既可能是真的出清，
    # 也可能只是兩站揭露範圍不同（fhtrust 的 xlsx vs etfinfo 的 PCF）——無從分辨。
    # 此時只比共同持股的加減碼，**不判定新增／出清**，並在 detail 標 `xsrc` 誠實揭露。
    # （非持股列已在抓取端由 drop_non_holdings 濾除；這是剩餘差異的最後一道防線。）
    src, prev_src = (entry or {}).get("src"), (entry or {}).get("prev_src")
    xsrc = bool(prev and src and prev_src and src != prev_src)
    rows, total, covered_w = [], 0.0, 0.0
    for h in holdings:
        sid = str(h.get("stock_id") or "")
        w = h.get("weight")
        sh = h.get("shares")
        p = prev.get(sid) or {}
        d_sh = (sh - p["shares"]) if (sh is not None and p.get("shares") is not None) else None
        d_w = (round(w - p["weight"], 2)
               if (w is not None and p.get("weight") is not None) else None)
        q = (quotes or {}).get(sid) or {}
        if q and pd and q.get("date") not in (None, pd):
            q = {}                                        # 報價日≠pd：不混日（2026-10-21 錯日事故）
        chg = _chg_pct(q)
        close, ccy = q.get("close"), q.get("ccy")
        if chg is None and pd:
            o = prior_rows.get(sid) or {}
            if o.get("qd") == pd and o.get("chg_pct") is not None:   # 上一班同一報價日已抓到
                chg, close, ccy = o["chg_pct"], o.get("close"), o.get("ccy")
        contrib = round(w * chg / 100, 3) if (w is not None and chg is not None) else None
        if contrib is not None:
            total += contrib
            covered_w += w or 0.0
        rows.append({"stock_id": sid, "name": h.get("name") or q.get("name") or sid,
                     "weight": w, "shares": sh, "d_shares": d_sh, "d_weight": d_w,
                     "chg_pct": chg, "contrib": contrib,
                     # qd＝這列漲跌的報價日（網頁只顯示 qd＝pd 的列）；pend＝海外當地還沒收盤
                     "qd": pd if chg is not None else None,
                     "pend": bool(chg is None and sid in (pending or ())),
                     # 收盤價（金額 ＝ Δ股數 × 收盤）與產業別（方塊圖外層分組）——
                     # 兩者只有 CI 端取得到（容器 proxy 擋 twse/tpex），存進落檔供渲染。
                     # ccy＝海外報價幣別（Yahoo 補源）——_moves 據此不把外幣收盤算成金額
                     "close": close, "ccy": ccy,
                     "industry": (ind or {}).get(sid),
                     # 新進／剔除標記：prev 有整份揭露時才判定（prev 空＝首日，不亂標「新增」；
                     # 跨來源＝揭露範圍本就不同，也不判定）
                     "is_new": bool(prev) and not xsrc and sid not in prev})
    # 前一揭露日有、今日沒有的 → 已出清
    # 出清標的的公司名：prev 存的 → **上一次的 detail.all**（那時它還在持股中、名字就在裡面，
    # 對「海外出清」特別關鍵——沒有台股報價、也不在別檔持股裡）→ 當日報價 → 其他 ETF 的
    # 持股名冊 → 最後才退回代號
    prev_named = {str(r.get("stock_id")): r.get("name")
                  for r in ((entry or {}).get("detail") or {}).get("all") or []
                  if r.get("stock_id") and (r.get("name") or "").strip()
                  and r.get("name") != r.get("stock_id")}

    def _dropped_name(sid, v):
        return (v.get("name") or prev_named.get(sid)
                or ((quotes or {}).get(sid) or {}).get("name")
                or (names or {}).get(sid) or sid)

    def _dropped_px(sid):
        q = (quotes or {}).get(sid) or {}
        if q.get("close") is not None and not (pd and q.get("date") not in (None, pd)):
            return q.get("close"), q.get("ccy")
        return prior_px.get(sid, (None, None))
    dropped = [{"stock_id": sid, "name": _dropped_name(sid, v), "weight": None, "shares": 0,
                "d_shares": -(v.get("shares") or 0) if v.get("shares") else None,
                "d_weight": (round(-v["weight"], 2) if v.get("weight") is not None else None),
                "chg_pct": None, "contrib": None,
                "close": px[0], "ccy": px[1],
                "industry": (ind or {}).get(sid),
                "is_new": False, "is_out": True}
               for sid, v in prev.items() for px in (_dropped_px(sid),)
               # 既有落檔的 prev 可能還留著換源前抓進來的非持股列（現金／應付款／期貨）——
               # 那些不是「出清」，是本來就不該進 diff 的列
               if not xsrc and sid not in _index(holdings)
               and not is_non_holding(sid, v.get("name"))]
    # 「完整持股明細」（ETF 詳情第三段：搜尋＋排序＋分頁）需要**全部**持股列，
    # 不能只留貢獻前 12——依權重由大到小，與截圖預設排序一致（2026-07-30 使用者需求）
    full = sorted(rows, key=lambda r: (r.get("weight") is None, -(r.get("weight") or 0)))
    n_pend = sum(1 for r in rows if r.get("pend"))
    mv = _moves(rows, dropped)
    rows = list(rows)
    rows.sort(key=lambda r: (r["contrib"] is None, -abs(r["contrib"] or 0)))
    shown, rest = rows[:top_n], rows[top_n:]
    rest_contrib = round(sum(r["contrib"] for r in rest if r["contrib"] is not None), 3) if rest else None
    rest_weight = round(sum(r["weight"] or 0 for r in rest), 2) if rest else None
    # sum_weight＝揭露清單全體權重合計（≠covered_weight：後者只算「有報價」者）。
    # 全球型主動 ETF（如 00988A）的海外持股代號不符台股 4 碼格式、進不了本表——
    # sum_weight 遠低於 100 就是這種檔，儀表板據此標「僅台股部位」誠實揭露（2026-07-29）。
    return {"date": (entry or {}).get("date"), "prev_date": (entry or {}).get("prev_date"),
            # pd＝漲跌／收盤價的報價日（最新交易日）；date＝持股快照日——兩者可以不同，網頁兩個都標
            "pd": pd, "n_pend": n_pend,
            "src": (entry or {}).get("src"), "prev_src": prev_src,
            "xsrc": ([prev_src, src] if xsrc else None),
            "verify": (entry or {}).get("verify"),
            "rows": shown, "dropped": dropped, "all": full, **mv,
            "rest_n": len(rest), "rest_contrib": rest_contrib, "rest_weight": rest_weight,
            "total_contrib": round(total, 2), "covered_weight": round(covered_w, 1),
            "sum_weight": round(sum(h.get("weight") or 0 for h in holdings), 1),
            "n_holdings": len(holdings)}


def annotate(doc: dict, quotes: dict[str, dict] | None,
             ind: dict[str, str] | None = None, top_n: int = _TOP_N,
             pd: str | None = None, pending: set[str] | None = None,
             prior_doc: dict | None = None) -> dict:
    """在**抓取端**（CI，連得到報價）把展開明細算好存進落檔的 `detail`。

    為什麼不在儀表板端算：容器內 proxy 擋 twse/tpex，建表時取不到個股報價；
    專案慣例本就是「抓取在 CI、容器內只讀落檔建表」（同 macro_chips／etf_watch）。

    quotes 全是報價日 pd（最新交易日）那一天的（見 contributions）；所有 ETF 用同一個 pd。
    這班完全拿不到台股報價（quotes 空）→ 各檔沿用上一班的報價日與各列數值（整張表仍是同一天、
    新進持股留白），持股與異動照樣依最新揭露重算——不再整份保留舊 detail（舊 detail 的異動可能是前一次揭露的）。

    prior_doc＝合併前的上一版落檔：`merge_one` 拿到新揭露時回的是新 entry（不帶舊 detail），
    上一班的報價只剩這裡找得到——沒傳就只看 entry 自己的 detail。"""
    # 全體持股名冊：某檔 ETF 出清的股票，往往還在別檔 ETF 的持股裡——拿來補名字最直接
    names = {str(h.get("stock_id")): h.get("name")
             for e in (doc.get("etfs") or {}).values()
             for h in (e.get("holdings") or [])
             if h.get("stock_id") and (h.get("name") or "").strip()}
    if quotes and not pd:                     # 呼叫端沒給報價日：報價自帶的日期一致才採用
        ds = {v.get("date") for v in quotes.values() if v.get("date")}
        pd = ds.pop() if len(ds) == 1 else None
    old_etfs = (prior_doc or {}).get("etfs") or {}
    for code, entry in (doc.get("etfs") or {}).items():
        prior = entry.get("detail") or (old_etfs.get(code) or {}).get("detail") or {}
        if quotes:
            got = contributions(entry, quotes, ind, top_n, names, pd=pd, pending=pending, prior=prior)
        else:
            got = contributions(entry, {}, ind, top_n, names, pd=prior.get("pd"), prior=prior)
        if got:
            entry["detail"] = got
    return doc


def view(doc: dict | None, code: str) -> dict | None:
    """儀表板端取數：以落檔已算好的 detail 為主（純渲染、不連網）。

    落檔 detail 缺 `all`（舊 schema，或 CI 當次取不到報價而沿用舊值）時，就地以
    `holdings`／`prev` 補算「完整持股 + 異動」——這兩者是**純比較、不需要網路**，
    只有收盤價與當日漲跌非連網不可。補算後把舊 detail 已有的個股報價／貢獻依代號嫁接
    回來，既不憑空補價、也不會讓整個詳情區空著（同專案「降級但誠實」慣例）。
    """
    entry = ((doc or {}).get("etfs") or {}).get(code) or {}
    det = entry.get("detail")
    fv = fut_view(entry)
    if (det or {}).get("all") or not entry.get("holdings"):
        return _with_fut(_clean_detail(det), fv)
    from . import stockmeta                     # 延遲載入：避免資料層互相 import
    fresh = contributions(entry, None, stockmeta.industry_map())
    if not fresh:
        return _with_fut(det, fv)
    priced = {r["stock_id"]: r for r in ((det or {}).get("rows") or [])}
    for r in fresh["all"]:
        o = priced.get(r["stock_id"])
        if o:
            r["close"], r["chg_pct"], r["contrib"] = o.get("close"), o.get("chg_pct"), o.get("contrib")
            r["qd"], r["pend"] = o.get("qd"), bool(o.get("pend"))
    for k in ("total_contrib", "covered_weight", "verify", "src", "pd", "n_pend"):
        if (det or {}).get(k) is not None:
            fresh[k] = det[k]
    return _with_fut(_clean_detail(fresh), fv)


def _with_fut(det: dict | None, fv: dict | None) -> dict | None:
    """detail 附上「期貨部位」（不改動落檔裡的 detail 物件）。"""
    return {**det, "fut": fv} if (det and fv) else det
