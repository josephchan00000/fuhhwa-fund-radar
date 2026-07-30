#!/usr/bin/env python3
"""ETF 每日持股 —— 多源抓取（本家＝復華官網第一手優先；其餘 etfinfo 主＋Yahoo 構成驗證）。

**路線沿革（2026-07-29 定案）**：投信官網逐家逆向 7 輪＋無頭瀏覽器 3 輪後，
使用者指示「不必抓官網第一手，彙整站即可、找第二站雙重驗證」；本家三檔例外——
舊管線（arm/pipeline.py）本就以 assetsExcel 第一手抓 00991A/00998A/00986D，沿用：
  · **主來源 etfinfo.tw**（Tier B）：`GET /api/etf/{code}` 的 holdings 欄位＝完整每日快照
    （stock_id／weight／shares＋snapshotDate）。既有連接器 `arm/connectors/etfinfo.py`
    早已封裝（`holdings_fresh`），且 CI 每天抓規模／殖利率就在打同一 API——可達性已被證實數週。
  · **副來源 Yahoo 股市持股頁**（Tier B）：SSR 內嵌 JSON（parse_embedded_json）。
    注意 Yahoo 持股為**月度基準前十大**、etfinfo 為每日 PCF 快照——只做「構成驗證」
    （前十大重合度），**不比權重**（跨基準日比權重是方法錯誤，實測 19/21 檔被誤判）。
    MoneyDJ 已移除：basic0007 頁 table×0（改 JS 渲染，SSR 表格已不存在，2026-07-29 實測）。

**雙重驗證（etfholdings.cross_check）**：兩源皆得 → 比「主來源前十大重合度 ≥60%」＋
「共同持股權重差 ≤0.75pp」→ 🟢 match；僅一源 → 標 single；不符 → 標 mismatch
（照用主來源但儀表板掛 ⚠，差異細節入日誌）。不比股數——兩站股數口徑常不同，比了誤殺。

假陽性驗證（is_plausible）、合併鐵則（merge）、貢獻歸因（annotate）全部重用既有模組。
無頭瀏覽器版（fetch_etf_holdings_browser.py）保留為備援、不再排程。

本容器 proxy 擋 etfinfo/yahoo —— 只在正式區 CI 有意義；容器內跑會全數失敗（屬正常，
既有落檔原封保留）。
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import clock, config as prodcfg, etfholdings, etfwatch, stockmeta   # noqa: E402
from arm.connectors import etfinfo, fhtrust              # noqa: E402
from arm.connectors.issuers import pcf                   # noqa: E402

_KINDS = ("active", "other", "passive")

# 本家 ETF（products.json 有 fund_id 對映者：00991A/00998A/00986D）＝**復華官網第一手優先**
# ——舊管線 arm/pipeline.py 三檔全走 assetsExcel（含前後快照 diff、排除期貨避險），能力本就存在。
# 順序：fhtrust（Tier A 第一手）→ etfinfo（Tier B，同為每日 PCF 基準 → 可做**同基準日權重驗證**，
# 這是唯一能亮真正「🟢 雙源相符」的組合）→ Yahoo（月度基準，只驗構成）。
# fhtrust.fetch_holdings 原生支援外股 ticker（'C US'）與債券（面額/幣別）；期貨避險列排除
#（同舊管線慣例：轉倉/避險不是持股變化）。
# 2026-07-29 教訓：曾誤標 00998A/00986D「結構性不支援」——限制在我的 schema，不在資料。
_TIMEOUT = 20
_UA = {"User-Agent": "Mozilla/5.0 (fuhhwa-fund-radar; etf-holdings)"}


# ── 主來源：etfinfo ──────────────────────────────────────────────────

def _from_etfinfo(code: str) -> tuple[list[dict], str | None, str]:
    """→ (持股列, 快照日, 診斷)。抓不到／不像持股回 ([], None, 原因)。"""
    try:
        raw, meta = etfinfo.holdings_fresh(code)
    except Exception as e:                                # noqa: BLE001 —— 每源獨立降級
        return [], None, f"etfinfo ✗ {type(e).__name__}: {str(e)[:90]}"
    rows = [{"stock_id": str(r["stock_id"]), "name": r.get("stock_name") or "",
             "shares": (int(r["shares"]) if r.get("shares") else None),
             "weight": (float(r["weight"]) if r.get("weight") else None)}
            for r in raw]
    rows = pcf._drop_value_like_shares(
        sorted(rows, key=lambda h: -(h.get("weight") or 0)))
    why = pcf.implausible_reason(rows)
    if why:
        return [], None, f"etfinfo {len(rows)} 檔未過驗證（{why}）"
    asof = (str(meta.get("as_of"))[:10] or None) if meta.get("as_of") else None
    return rows, asof, f"etfinfo ✓ {len(rows)} 檔（快照日 {asof or '未標'}）"




def _get_raw(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return r.read()



# ── 本家來源：復華官網 assetsExcel（Tier A 第一手；外股/債券原生支援） ──

def _from_fhtrust(code: str) -> tuple[list[dict], str | None, str]:
    """→ (持股列, 資料日, 診斷)。products.json 無對映的檔回 ([], None, "")。

    與基金管線同一支 API（fhtrust.fetch_holdings）：外股列 stock_id 是 ticker
    （'C US'/'7167 JP'）、債券列 shares＝面額——Δ 比較照樣成立；台股報價對不到
    → 當日貢獻顯示 —（誠實降級）。資料日常為 T-1，往回試最多 5 個平日。"""
    try:
        fid = prodcfg.product(code)["fund_id"]
    except Exception:
        return [], None, ""
    from datetime import timedelta
    d, tried, last = clock.today_tw(), 0, ""
    while tried < 5:
        if d.weekday() < 5:
            tried += 1
            iso = d.isoformat()
            try:
                snap = fhtrust.fetch_holdings(fid, iso)
                rows = []
                for h in snap.get("holdings") or []:
                    if h.get("kind") == "future":         # 期貨避險/轉倉不算持股變化（舊管線慣例）
                        continue
                    sid = str(h.get("stock_id") or "").strip() or str(h.get("stock_name") or "").strip()
                    if not sid:
                        continue
                    name = str(h.get("stock_name") or "").strip()
                    rows.append({"stock_id": sid, "name": ("" if name == sid else name),
                                 "shares": h.get("shares"), "weight": h.get("weight")})
                # 外股/債券不套 pcf 的台股 4 碼驗證：改驗「≥5 檔且過半帶權重」
                with_w = sum(1 for r in rows if r.get("weight") is not None)
                if len(rows) >= 5 and with_w * 2 >= len(rows):
                    # 資料日以**檔案自報**為準；掃不到才回退請求日期（並在日誌標明，
                    # 供一輪 CI 收斂——2026-07-30 的假「無異動」就是誤用請求日期造成）
                    asof = snap.get("date") or iso
                    src_note = ("檔案自報" if snap.get("date_src")
                                else f"⚠ 檔案未見日期、沿用請求日 {iso}")
                    return rows, asof, f"fhtrust ✓ {len(rows)} 檔（{fid}，{asof}・{src_note}）"
                last = f"fhtrust {iso} 解析 {len(rows)} 檔/帶權重 {with_w}（未過驗證）"
            except Exception as e:                        # noqa: BLE001 —— 換前一平日再試
                last = f"fhtrust ✗ {type(e).__name__}: {str(e)[:80]}"
        d -= timedelta(days=1)
    return [], None, last


# ── 副來源：Yahoo 股市持股頁（SSR 內嵌 JSON、月度基準 → 只做構成驗證） ──

_YH_URL = "https://tw.stock.yahoo.com/quote/{sym}/holding"


def _from_yahoo(code: str) -> tuple[list[dict], str]:
    last = ""
    for suffix in (".TW", ".TWO"):
        try:
            raw = _get_raw(_YH_URL.format(sym=code + suffix))
        except Exception as e:                            # noqa: BLE001
            last = f"yahoo ✗ {type(e).__name__}: {str(e)[:80]}"
            continue
        rows = pcf._normalize(pcf.parse_embedded_json(raw) or pcf.parse_html(raw))
        why = pcf.implausible_reason(rows)
        if not why:
            return rows, f"yahoo ✓ {len(rows)} 檔（{suffix}）"
        last = (f"yahoo {len(rows)} 檔未過驗證（{why}）｜"
                + "；".join(pcf._key_hits(raw))[:180])
    return [], last


# ── 主流程 ───────────────────────────────────────────────────────────

def main() -> int:
    probe_only = "--probe" in sys.argv
    targets = [(c, k) for c, _n, k, _cat, _i in etfwatch.WATCHLIST if k in _KINDS]
    targets.sort(key=lambda t: _KINDS.index(t[1]))
    print(f"[ETF 每日持股・多源] 本家＝fhtrust 第一手優先；其餘 etfinfo 主＋Yahoo 構成驗證"
          f"（{len(targets)} 檔{'；--probe 不落檔' if probe_only else ''}）…")

    fresh: dict[str, dict] = {}
    diag: dict[str, str] = {}
    n_match = n_single = n_mismatch = n_weak = 0
    fallback_date = _latest_trade_date()
    for code, _kind in targets:
        # 本家檔（products.json 有對映）＝第一手優先；其餘 etfinfo 主
        f_rows, f_asof, log0 = _from_fhtrust(code)
        e_rows, e_asof, log1 = _from_etfinfo(code)
        y_rows, log3 = ([], "")
        if not (f_rows and e_rows):                       # 已有兩源就不必再打 Yahoo（節流）
            y_rows, log3 = _from_yahoo(code)
        got = [(s, r) for s, r in (("fhtrust", f_rows), ("etfinfo", e_rows),
                                   ("yahoo", y_rows)) if r]
        asof = f_asof if f_rows else e_asof
        if not got:
            diag[code] = "；".join(x for x in (log1, log0, log3) if x)
            print(f"  ⚠ {code} 全部來源皆不可得")
            for x in (log1, log0, log3):
                if x:
                    print(f"      · {x}")
            continue
        src, rows = got[0]
        pri, sec = rows, (got[1][1] if len(got) > 1 else [])
        if pri and sec:
            sec_src = got[1][0]
            # 權重只在「同基準日的每日 PCF 對每日 PCF」時比（fhtrust vs etfinfo 且日期相同）；
            # Yahoo 是月度基準、或兩源快照日不同 → 只驗構成（跨時點比權重是方法錯誤）
            same_day = (src == "fhtrust" and sec_src == "etfinfo"
                        and f_asof and e_asof and f_asof == e_asof)
            verify = etfholdings.cross_check(pri, sec, weights=bool(same_day))
            verify["other"] = sec_src
            if verify["status"] == "match":
                n_match += 1
            else:
                # 構成重合過低＝副源基準過舊、無法據以驗證——**不是**主來源錯誤的證據
                # （00929 月度重合 3/10 即此類：月內調倉大，Yahoo 舊快照對不上每日 PCF）
                verify["status"] = "weak"
                n_weak += 1
                print(f"  ◐ {code} 副源基準過舊、未能交叉驗證"
                      f"（構成重合 {verify['top_hit']}/{verify['top_n']}）")
        else:
            verify = {"status": "single", "other": None}
            n_single += 1
        fresh[code] = {"date": (asof if src == "etfinfo" and asof else fallback_date),
                       "src": src, "verify": verify, "holdings": rows}
        mark = {"match": "🟢", "single": "◯", "mismatch": "⚠", "weak": "◐"}[verify["status"]]
        logs = "｜".join(x for x in (log0, log1, log3) if x)
        print(f"  {mark} {code}：{len(rows)} 檔（{src}）｜{logs}")

    if probe_only:
        print(f"[探針] 成功 {len(fresh)}/{len(targets)}（🟢 構成相符 {n_match}、"
              f"◯ 單源 {n_single}、◐ 副源過舊 {n_weak}、⚠ 不符 {n_mismatch}）；未落檔。")
        return 0

    doc = etfholdings.merge(etfholdings.load(), fresh, diag)
    quotes = _quotes()
    ind = _industry()
    if quotes:
        etfholdings.annotate(doc, quotes, ind)
        print(f"  ✓ 當日貢獻歸因：個股報價 {len(quotes)} 檔｜產業別 {len(ind)} 檔")
    else:
        print("  ⚠ 個股報價不可得 → 沿用既有貢獻明細（不覆寫成空）")
    ok = etfholdings.save(doc)
    print(f"{'✓ 落檔' if ok else '⚠ 本次全空、保留既有落檔'} {etfholdings.DATA_FP}"
          f"（{len(doc.get('etfs') or {})} 檔有揭露；本次 {len(fresh)} 檔：🟢 {n_match}"
          f"／◯ {n_single}／◐ {n_weak}／⚠ {n_mismatch}）")
    return 0


def _industry() -> dict[str, str]:
    """個股產業別（持股異動方塊圖的外層分組）：上市＋上櫃 openapi → 落檔累積。

    產業別半年才動一次，落檔入庫後容器端建表也有分組可用（proxy 擋 twse/tpex）；
    抓不到就沿用既有落檔（`stockmeta.merge` 保證不洗成空）。
    """
    rows: list[dict] = []
    for mod in ("twse", "tpex"):
        try:
            from importlib import import_module
            got = import_module(f"arm.connectors.{mod}").fetch_basic_rows()
            rows += got
            print(f"  · {mod} 基本資料 {len(got)} 列")
        except Exception as e:                            # noqa: BLE001
            print(f"  ⚠ {mod} 基本資料不可得：{type(e).__name__}: {str(e)[:80]}")
    fresh = stockmeta.rows_to_map(rows)
    if rows and not fresh:                                # 鍵名改過 → 印出實際鍵名，一輪收斂
        print(f"  ⚠ 基本資料解析 0 筆：{stockmeta.sample_keys(rows)}")
    doc = stockmeta.merge(fresh)
    if stockmeta.save(doc):
        print(f"  ✓ 產業別落檔 {stockmeta.DATA_FP}（本次 {len(fresh)}／累計 "
              f"{len(doc.get('industry') or {})} 檔）")
    return doc.get("industry") or {}


def _quotes() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for mod in ("twse", "tpex"):
        try:
            from importlib import import_module
            out.update(import_module(f"arm.connectors.{mod}").fetch_today_all())
        except Exception as e:                            # noqa: BLE001
            print(f"  ⚠ {mod} 個股報價不可得：{type(e).__name__}: {str(e)[:80]}")
    return out


def _latest_trade_date() -> str | None:
    try:
        from arm.connectors import twse
        return twse.latest_trade_date()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
