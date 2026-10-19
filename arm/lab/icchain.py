"""櫃買中心產業鏈平台（ic.tpex.org.tw）的節點與公司名單（細分族群用；docs/lab_crash_plan.md 第 21.4～21.6 節）。

平台只有「現在」的名單，沒有歷史。抓取只在 CI（本容器 proxy 擋 ic.tpex.org.tw）：
  scripts/backfill_lab.py --ic-chain（.ping/lab 第一行 icfill）；每天 scripts/fetch_heat.py 只在落檔超過 REFRESH_DAYS 天才重抓。
落檔 data/lab/icchain.json：
  {"d": 抓取日, "chains": {產業鏈代碼: {"n": 名稱, "nodes": [[節點代碼, 節點名稱, [[段落標籤, 標示家數, [代號…]], …]], …]}}}
  段落＝節點裡每個 <b> 標籤之後到下一個 <b> 之前（本國上市公司、本國上櫃公司、外國上市公司、本國興櫃公司、知名外國企業，
  半導體 IC 設計節點另有 IC 類別分頁，例「LED驅動IC」）。原樣存段落，族群怎麼取由 bubindspec 決定（groups_tw）。
"""
from __future__ import annotations

import html as _html
import re
import time

from . import store

HOME = "https://ic.tpex.org.tw/"
CHAIN_URL = "https://ic.tpex.org.tw/introduce.php?ic={ic}"
FILE = "icchain.json"
REFRESH_DAYS = 30
SLEEP = 1.5

_TAG = re.compile(r"<[^>]+>")
_CHAIN = re.compile(r'href="introduce\.php\?ic=(\w+)"[^>]*>(.*?)</a>', re.S)
_NODE = re.compile(r'<div id="companyList_(\w+)" title="([^"]*)"')
_STK = re.compile(r"stk_code=(\d{4})(?!\d)")
_CNT = re.compile(r"[（(]\s*(\d+)\s*家\s*[)）]\s*$")
_B = re.compile(r"<b(?:\s[^>]*)?>")
MKT = ("本國上市公司", "本國上櫃公司", "外國上市公司", "外國上櫃公司", "本國興櫃公司", "外國興櫃公司", "創櫃公司", "知名外國企業")


def _log(msg: str) -> None:
    print(f"  [icchain] {msg}", flush=True)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub("", s)).replace("\xa0", " ")).strip()


def parse_home(h: str) -> list[tuple[str, str]]:
    """首頁 → [(產業鏈代碼, 名稱)]（依出現順序、去重）。"""
    out: list[tuple[str, str]] = []
    for ic, t in _CHAIN.findall(h):
        if ic not in [c for c, _ in out]:
            out.append((ic, _clean(t)))
    return out


def _label(seg: str) -> tuple[str, int | None]:
    """<b> 之後的片段 → (標籤去掉「(N家)」, N)。"""
    k = seg.find("</b>")
    lab = _clean(seg[:k] if k >= 0 else seg[:60])
    m = _CNT.search(lab)
    n = int(m.group(1)) if m else None
    return (_CNT.sub("", lab).strip() if m else lab), n


def parse_chain(h: str) -> list[list]:
    """產業鏈頁 → [[節點代碼, 節點名稱, [[標籤, 標示家數, [代號…]], …]], …]。
    節點在頁面裡出現兩次（圖與清單），同一個節點代碼只留第一次；段落裡的代號依出現順序去重。
    <b> 帶屬性的也算（半導體 IC 設計節點的 IC 類別分頁標題是 <b class=…>）。"""
    parts = re.split(r'(?=<div id="companyList_)', h)
    out: list[list] = []
    seen: set[str] = set()
    for part in parts[1:]:
        m = _NODE.match(part)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        segs = []
        for seg in _B.split(part)[1:]:
            lab, n = _label(seg)
            codes: list[str] = []
            for c in _STK.findall(seg):
                if c not in codes:
                    codes.append(c)
            segs.append([lab, n, codes])
        out.append([m.group(1), _clean(m.group(2)), segs])
    return out


def tabs(node: list) -> dict[str, set[str]] | None:
    """有分頁的節點（IC 設計）→ {分頁名稱: 代號}；沒有分頁＝None。
    版式：先列全部分頁標題（不是市場別、沒有代號，標示 N 家），之後依序是各分頁的市場別段落；
    每個分頁依序取段落，直到段落標示家數加起來等於分頁的 N 家。對不上（版式變了）＝None，並印日誌。"""
    segs = node[2]
    heads = [(lab, n) for lab, n, cs in segs if lab not in MKT and not cs]
    if not heads:
        return None
    body = [x for x in segs if x[0] in MKT]
    out: dict[str, set[str]] = {}
    k = 0
    for lab, n in heads:
        got, cs = 0, set()
        while k < len(body) and n is not None and got < n:
            got += body[k][1] or 0
            cs |= set(body[k][2])
            k += 1
        if n is None or got != n:
            _log(f"{node[0]} {node[1]} 分頁「{lab}」家數對不上（標示 {n}、段落合計 {got}），不用分頁")
            return None
        out[lab] = cs
    if k != len(body):
        _log(f"{node[0]} {node[1]} 分頁之後還有 {len(body) - k} 個段落，不用分頁")
        return None
    return out


def load() -> dict:
    return store.read_json(FILE, {}) or {}


def node_codes(node: list, labels: tuple[str, ...] | None = None) -> set[str]:
    """節點裡的代號（labels＝只取這些段落標籤；None＝全部段落）。"""
    return {c for lab, _, cs in node[2] if labels is None or lab in labels for c in cs}


def stale(doc: dict | None = None, today: str | None = None) -> bool:
    from datetime import date
    from arm import clock
    doc = doc if doc is not None else load()
    d = doc.get("d")
    if not d or not doc.get("chains"):
        return True
    t = date.fromisoformat(today or clock.today_tw().isoformat())
    return (t - date.fromisoformat(d)).days >= REFRESH_DAYS


def fetch(force: bool = False) -> dict:
    """抓全部產業鏈（約 41 個請求）。任何一條抓不到＝不寫檔（不拿殘缺的名單蓋掉前一版）。"""
    from arm import clock
    from arm.http import get_bytes
    from .market import _decode
    old = load()
    if not force and not stale(old):
        _log(f"落檔 {old.get('d')} 還在 {REFRESH_DAYS} 天內，不重抓")
        return {"skip": True, "d": old.get("d")}
    try:
        chains = parse_home(_decode(get_bytes(HOME, retries=2, timeout=30, use_cache=False)))
    except Exception as e:                                # noqa: BLE001
        _log(f"首頁 ✗ {str(e)[:160]}")
        return {"err": "home"}
    if len(chains) < 20:
        _log(f"首頁只解析到 {len(chains)} 條產業鏈，不寫檔")
        return {"err": "home", "n": len(chains)}
    out: dict = {}
    for ic, name in chains:
        try:
            h = _decode(get_bytes(CHAIN_URL.format(ic=ic), retries=2, timeout=30, use_cache=False))
        except Exception as e:                            # noqa: BLE001
            _log(f"{ic} {name} ✗ {str(e)[:120]}")
            return {"err": ic}
        nodes = parse_chain(h)
        if not nodes:
            _log(f"{ic} {name} 解析到 0 個節點，不寫檔（片段 {h[:200]!r}）")
            return {"err": ic}
        out[ic] = {"n": name, "nodes": nodes}
        n_codes = len({c for nd in nodes for c in node_codes(nd)})
        _log(f"{ic} {name}：節點 {len(nodes)}、代號 {n_codes}")
        _debug_tabs(ic, h, nodes)
        time.sleep(SLEEP)
    doc = {"d": clock.today_tw().isoformat(), "chains": out}
    changed = store.write_json(FILE, doc)
    _log(f"產業鏈 {len(out)} 條、寫檔 {'是' if changed else '否（內容相同）'}")
    return {"d": doc["d"], "n": len(out), "changed": changed}


def _debug_tabs(ic: str, h: str, nodes: list) -> None:
    """節點裡有不是市場別的段落標籤（IC 設計的 IC 類別分頁）→ 印各分頁的代號數；分頁對不上才印頁面片段。"""
    for nid, title, segs in nodes:
        odd = [(lab, n, len(cs)) for lab, n, cs in segs if lab not in MKT]
        if not odd:
            continue
        t = tabs([nid, title, segs])
        if t is None:
            _log(f"{ic} {nid} {title}：非市場別段落 {odd}，分頁對不上")
            k = h.find(f'id="companyList_{nid}"')
            _log(f"  片段 {h[k:k + 2500]!r}")
        else:
            _log(f"{ic} {nid} {title}：分頁 " + "；".join(f"{a}({len(b)})" for a, b in t.items()))
