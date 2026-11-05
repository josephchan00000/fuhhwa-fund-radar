"""盤前作戰圖（docs/lab_premarket_plan.md）：以加權指數為基準，每天盤前一張圖——預估開盤、正常波動範圍、上下的壓力支撐帶
（每個價位寫出來源、好幾個來源擠在一起＝共振）、籌碼期貨指標的事實、幾個情境的風險報酬試算（小台與選擇權買方）。

第 2 段只放公式與事實，不放「偏多偏空」與「碰到的機率」：那些要第 3 段先寫規格、驗證過才加（使用者 2026-11-05 決定 D4）。
本模組只讀已存的資料、不連網；夜盤由 scripts/fetch_night.py（CI）先抓進 data/lab/fut/night.json。

  build() → data/lab/premkt.json（scripts/run_premkt.py 寫）；頁面在 txopage（選擇權頁最上面），推播一行在 valog.pm_line。
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "lab" / "premkt.json"
NIGHT = ROOT / "data" / "lab" / "fut" / "night.json"
CALC = ROOT / "data" / "lab" / "txo_calc.json"
MACRO = ROOT / "data" / "macro_chips.json"

VER = 1
CLUSTER = 0.0025        # 價位相差 0.25% 以內併成一帶
NEAR = 3                # 預估開盤上下各列幾帶
FAR = 2.0               # 超過 2 倍正常波動的價位不列
ROUND = 500             # 整數關卡
VP_BIN = 10             # 期貨成交量分布的價格格子（台指期點數）
VP_AREA = 0.70          # 價值區＝包住 70% 成交量
BUF_EM = 0.1            # 停損緩衝＝0.1 倍正常波動
STOP_EM = 0.5           # 找不到下一帶時，目標＝進場 ± 0.5 倍正常波動
OPT_AT_MIN = 105        # 選擇權估價時點＝08:45 後 105 分（10:30）
MTX = 50                # 小台每點 50 元
MTX_FEE = 25            # 小台每口每邊手續費（假設，同選擇權）
FUT_TAX = 0.00002       # 期交稅（期貨）＝契約價值 × 十萬分之二
TRADING_YEAR = 252
KINDS = {"price": "昨天價格", "night": "夜盤", "pivot": "樞紐點", "ma": "均線通道", "opt": "選擇權未平倉", "vol": "期貨成交量",
         "round": "整數關卡"}


# ── 小工具 ──────────────────────────────────────────────────────────────────

def md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def wd(d: str) -> str:
    return "一二三四五六日"[date.fromisoformat(d).weekday()]


def _r(x, n=0):
    return None if x is None else (round(x) if n == 0 else round(x, n))


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _last2(series: dict | None, upto: str):
    """序列裡 upto 當天或之前最後兩筆 → ((日, 值), (日, 值))；沒有＝None。"""
    if not series:
        return None, None
    ks = sorted(k for k in series if k <= upto and series[k] is not None)
    a = (ks[-1], series[ks[-1]]) if ks else None
    b = (ks[-2], series[ks[-2]]) if len(ks) > 1 else None
    return a, b


# ── 指標 ────────────────────────────────────────────────────────────────────

def pivots(h: float, l: float, c: float) -> dict:
    p = (h + l + c) / 3
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l)}


def rsi(cs: list[float], n: int = 14) -> float | None:
    if len(cs) < n + 1:
        return None
    up = dn = 0.0
    for a, b in zip(cs[:n], cs[1:n + 1]):
        up += max(0, b - a)
        dn += max(0, a - b)
    up, dn = up / n, dn / n
    for a, b in zip(cs[n:-1], cs[n + 1:]):
        up = (up * (n - 1) + max(0, b - a)) / n
        dn = (dn * (n - 1) + max(0, a - b)) / n
    return 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)


def ema(xs: list[float], n: int) -> list[float]:
    k, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else out[-1] + k * (x - out[-1]))
    return out


def macd(cs: list[float]) -> tuple[float, float] | None:
    """MACD 柱（12、26、9）今天與前一天。"""
    if len(cs) < 60:
        return None
    dif = [a - b for a, b in zip(ema(cs, 12), ema(cs, 26))]
    sig = ema(dif, 9)
    h = [a - b for a, b in zip(dif, sig)]
    return h[-1], h[-2]


def kd(hl: list[tuple[float, float, float]], n: int = 9) -> tuple[float, float] | None:
    """台灣常用 KD（9 日 RSV，K、D 各用 1/3 平滑，起點 50）；hl＝[(高, 低, 收)]，至少 n＋5 天。"""
    if len(hl) < n + 5:
        return None
    k = d = 50.0
    for i in range(n - 1, len(hl)):
        w = hl[i - n + 1:i + 1]
        hi, lo = max(x[0] for x in w), min(x[1] for x in w)
        rsv = 50.0 if hi == lo else (hl[i][2] - lo) / (hi - lo) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
    return k, d


def vprofile(ticks: list[tuple[int, int, int, bool]], step: int = VP_BIN, area: float = VP_AREA) -> dict | None:
    """台指期一般時段每筆成交 → 成交量最多的價位（POC）與包住 area 成交量的上下緣（台指期點數）。"""
    vol: dict[int, float] = {}
    for _, px, q, _ in ticks:
        b = int(px // step * step)
        vol[b] = vol.get(b, 0) + q / 2
    if not vol:
        return None
    tot = sum(vol.values())
    poc = max(vol, key=lambda b: (vol[b], -b))
    lo = hi = poc
    acc = vol[poc]
    while acc < area * tot:
        a, b = vol.get(lo - step, 0), vol.get(hi + step, 0)
        if a == 0 and b == 0:
            break
        if b >= a:
            hi += step
            acc += b
        else:
            lo -= step
            acc += a
    half = step / 2
    return {"poc": poc + half, "vah": hi + step, "val": lo, "lots": round(tot)}


# ── 價位與共振帶 ─────────────────────────────────────────────────────────────

def cluster(levels: list[dict], ref: float, thr: float = CLUSTER) -> list[dict]:
    """價位 → 帶：由低往高，和這一帶最低價相差 thr × ref 以內的併進來；強度＝不同類別數。"""
    out: list[dict] = []
    for lv in sorted(levels, key=lambda x: x["px"]):
        if out and lv["px"] - out[-1]["lo"] <= thr * ref:
            b = out[-1]
            b["hi"] = lv["px"]
            b["src"].append(lv)
        else:
            out.append({"lo": lv["px"], "hi": lv["px"], "src": [lv]})
    for b in out:
        b["mid"] = (b["lo"] + b["hi"]) / 2
        b["kinds"] = sorted({s["kind"] for s in b["src"]}, key=list(KINDS).index)
        b["n"] = len(b["kinds"])
    return out


def pick_bands(bands: list[dict], est: float, em: float | None) -> list[dict]:
    """預估開盤上下各 NEAR 帶（FAR 倍正常波動以內），加上包住預估開盤的那一帶。"""
    lim = FAR * em if em else float("inf")
    up = sorted((b for b in bands if b["lo"] > est and b["lo"] - est <= lim), key=lambda b: b["lo"])[:NEAR]
    dn = sorted((b for b in bands if b["hi"] < est and est - b["hi"] <= lim), key=lambda b: -b["hi"])[:NEAR]
    at = [b for b in bands if b["lo"] <= est <= b["hi"]]
    for b in up:
        b["side"] = "up"
    for b in dn:
        b["side"] = "dn"
    for b in at:
        b["side"] = "at"
    return sorted(up + at + dn, key=lambda b: -b["mid"])


# ── 風險報酬試算 ─────────────────────────────────────────────────────────────

def fut_cost(px: float) -> float:
    """小台一口一邊：手續費＋期交稅＋1 點滑價（元）。"""
    return MTX_FEE + FUT_TAX * px * MTX + 1 * MTX


def _opt(entry: float, stop: float, target: float, cp: str, exp: dict, close: float, atm_iv: float | None) -> dict | None:
    """買一口選擇權（履約價＝進場價最近的 50 點）：用今天的波動率與到期時間（10:30）估進場、停損、目標時的權利金。"""
    from . import txocalc as TC
    from . import txospec as S
    k = round(entry / S.STRIKE_STEP) * S.STRIKE_STEP
    row = next((r for r in exp.get("rows") or [] if r[0] == k), None)
    iv = (row[2] if cp == "C" else row[4]) if row else None
    iv = iv or atm_iv
    n = exp.get("n") or 0
    if not iv or n <= 0:
        return None
    rem = max(n - OPT_AT_MIN / 300, 0.01)
    t = rem / TRADING_YEAR
    basis = (exp.get("f") or close) - close

    def price(s):
        return TC.bs(cp, s + basis * rem / n, k, t, iv)
    pe, ps, pt = price(entry), price(stop), price(target)
    loss = (pe - ps) * S.MULT + S.side_cost(pe) + S.side_cost(ps)
    gain = (pt - pe) * S.MULT - S.side_cost(pe) - S.side_cost(pt)
    return {"cp": cp, "k": k, "exp": exp["code"], "xd": exp["date"], "iv": round(iv, 4), "pe": round(pe, 1), "ps": round(ps, 1),
            "pt": round(pt, 1), "loss": round(loss), "gain": round(gain), "rr": round(gain / loss, 2) if loss > 0 else None,
            "max": round(pe * S.MULT + S.side_cost(pe))}


def scenarios(bands: list[dict], est: float, em: float | None, calc: dict | None, close: float) -> list[dict]:
    up = sorted((b for b in bands if b.get("side") == "up"), key=lambda b: b["lo"])
    dn = sorted((b for b in bands if b.get("side") == "dn"), key=lambda b: -b["hi"])
    em = em or 0.0
    buf = BUF_EM * em
    exp = next((e for e in (calc or {}).get("exps") or [] if (e.get("n") or 0) >= 2), None)
    atm_iv = (calc or {}).get("atm_iv")
    out = []

    def add(key, name, entry, stop, target, cp, why):
        risk, rew = abs(entry - stop), abs(target - entry)
        if risk <= 0 or rew <= 0:
            return
        loss = risk * MTX + fut_cost(entry) + fut_cost(stop)
        gain = rew * MTX - fut_cost(entry) - fut_cost(target)
        out.append({"k": key, "name": name, "why": why, "entry": round(entry), "stop": round(stop), "target": round(target),
                    "risk": round(risk), "reward": round(rew), "rr": round(rew / risk, 2),
                    "mtx": {"loss": round(loss), "gain": round(gain)},
                    "opt": _opt(entry, stop, target, cp, exp, close, atm_iv) if exp else None})

    def nxt_up(x):
        """x 以上第一個壓力帶的下緣（沒有＝None）。"""
        return next((b["lo"] for b in up if b["lo"] > x), None)

    def nxt_dn(x):
        return next((b["hi"] for b in dn if b["hi"] < x), None)

    if dn:
        s = dn[0]
        tgt = nxt_up(s["hi"]) or s["hi"] + STOP_EM * em
        add("long", "回測支撐做多", s["hi"], s["lo"] - buf, tgt, "C",
            f"支撐帶 {s['lo']:,.0f}～{s['hi']:,.0f}，跌破下緣 {buf:,.0f} 點就停損，目標" + ("上方第一個壓力帶" if nxt_up(s["hi"]) else "半個正常波動"))
    if up:
        r = up[0]
        tgt = nxt_dn(r["lo"]) or r["lo"] - STOP_EM * em
        add("short", "反彈壓力做空", r["lo"], r["hi"] + buf, tgt, "P",
            f"壓力帶 {r['lo']:,.0f}～{r['hi']:,.0f}，站上上緣 {buf:,.0f} 點就停損，目標" + ("下方第一個支撐帶" if nxt_dn(r["lo"]) else "半個正常波動"))
    if up:
        r = up[0]
        e = r["hi"] + buf
        nx = nxt_up(e)
        add("break", "突破壓力追多", e, r["mid"], nx or e + STOP_EM * em, "C",
            f"站上壓力帶上緣 {buf:,.0f} 點才進，回到帶子中間就停損，目標" + ("再上一個壓力帶" if nx else "半個正常波動"))
    if dn:
        s = dn[0]
        e = s["lo"] - buf
        nx = nxt_dn(e)
        add("breakdown", "跌破支撐追空", e, s["mid"], nx or e - STOP_EM * em, "P",
            f"跌破支撐帶下緣 {buf:,.0f} 點才進，回到帶子中間就停損，目標" + ("再下一個支撐帶" if nx else "半個正常波動"))
    return out


# ── 事實表 ──────────────────────────────────────────────────────────────────

def _chg(a, b):
    return None if a is None or b is None else a[1] - b[1]


def facts(d: str, close: float, tx1330: float | None, night: dict | None, txclose: float | None, closes: list[float],
          hl: list[tuple[float, float, float]], macro: dict, heat: dict) -> list[dict]:
    out = []

    def add(k, t, v, day=None, note=None):
        out.append({"k": k, "t": t, "v": v, "d": day, "note": note})
    S = macro.get("series") or {}
    a, b = _last2(S.get("tx_foreign_net"), d)
    if a:
        c = _chg(a, b)
        side = "淨空" if a[1] < 0 else "淨多"
        tail = ""
        if c:
            what = ("空單" if a[1] < 0 else "多單") + ("多了" if (c < 0) == (a[1] < 0) else "少了")
            tail = f"，{what} {abs(c):,.0f} 口"
        add("fx_fut", "外資台指期", f"{side} {abs(a[1]):,.0f} 口{tail}", a[0])
    futi, mtxoi = heat.get("futi") or {}, heat.get("mtxoi") or {}
    fk = max((k for k in futi if k <= d), default=None)
    if fk and fk in mtxoi and (futi[fk].get("MTX")):
        inst = sum(v[0] - v[1] for v in futi[fk]["MTX"].values())
        tot = mtxoi[fk]
        if tot:
            add("retail", "散戶小台", f"{'淨多' if -inst > 0 else '淨空'} {abs(inst):,.0f} 口（小台未平倉的 {abs(inst) / tot * 100:.0f}%）", fk,
                "＝法人小台淨部位的反向")
    opti = heat.get("opti") or {}
    ok = max((k for k in opti if k <= d), default=None)
    if ok:
        o = opti[ok]
        try:
            c_net = (o["買權"]["外資"][0] - o["買權"]["外資"][1]) / 1e5
            p_net = (o["賣權"]["外資"][0] - o["賣權"]["外資"][1]) / 1e5
            add("fx_opt", "外資選擇權", f"買權{'淨買' if c_net >= 0 else '淨賣'} {abs(c_net):,.1f} 億、賣權{'淨買' if p_net >= 0 else '淨賣'} {abs(p_net):,.1f} 億", ok,
                "未平倉金額，買方減賣方")
        except (KeyError, IndexError, TypeError):
            pass
    pcr = heat.get("pcr") or {}
    pk = sorted(k for k in pcr if k <= d)
    if pk:
        cur = pcr[pk[-1]][5]
        past = [pcr[k][5] for k in pk[-251:-1] if pcr[k][5] is not None]
        rank = sum(1 for x in past if x < cur) / len(past) * 100 if past else None
        r = None if rank is None else round(rank)
        pos = None if r is None else ("接近過去一年最低" if r <= 1 else "接近過去一年最高" if r >= 99 else f"過去一年 {r}% 的日子比現在低")
        add("pcr", "P/C 比（未平倉）", f"{cur:.1f}%" + (f"，{pos}" if pos else ""), pk[-1], "賣權未平倉 ÷ 買權未平倉；越高＝賣權相對越多")
    for key, name in (("inst_total", "三大法人現貨"), ("inst_foreign", "外資現貨")):
        a, _ = _last2(S.get(key), d)
        if a:
            add(key, name, f"{'買超' if a[1] >= 0 else '賣超'} {abs(a[1]):,.1f} 億", a[0])
    a, b = _last2(S.get("margin_bal"), d)
    if a and b:
        add("margin", "融資餘額", f"{a[1]:,.0f} 億（{'+' if a[1] >= b[1] else '−'}{abs(a[1] - b[1]):,.1f} 億）", a[0])
    if tx1330 is not None:
        bs = tx1330 - close
        add("basis", "期現價差", f"台指期 13:30 比加權指數{'高' if bs >= 0 else '低'} {abs(bs):,.0f} 點", d, "用同一時刻，不用台指期 13:45 收盤")
    if night and night.get("c") is not None:
        ref = night.get("ref") or txclose
        ch = night["c"] - ref if ref else None
        add("night", "夜盤", f"收 {night['c']:,.0f}" + (f"（比日盤收{'漲' if ch >= 0 else '跌'} {abs(ch):,.0f}）" if ch is not None else "") +
            f"，高 {night['h']:,.0f}、低 {night['l']:,.0f}" + ("" if night.get("done") else f"，進行中（截至 {night.get('t')}）"), d)
    for key, name, pct in (("sox", "費城半導體", True), ("tsm_adr", "台積電 ADR", True), ("vix", "VIX", False)):
        a, b = _last2(S.get(key), "9999")
        if a and b:
            ch = (a[1] / b[1] - 1) * 100 if pct else a[1] - b[1]
            add(key, name, f"{a[1]:,.2f}（{'+' if ch >= 0 else '−'}{abs(ch):.2f}{'%' if pct else ' 點'}）", a[0], "美國日期")
    if closes:
        c = closes[-1]
        parts = []
        r = rsi(closes)
        if r is not None:
            parts.append(f"RSI {r:.0f}")
        k = kd(hl)
        if k:
            parts.append(f"K {k[0]:.0f}／D {k[1]:.0f}")
        m = macd(closes)
        if m:
            parts.append(f"MACD 柱 {'正' if m[0] >= 0 else '負'}、{'變大' if abs(m[0]) > abs(m[1]) else '縮小'}")
        for n in (5, 20, 60):
            if len(closes) >= n:
                ma = sum(closes[-n:]) / n
                parts.append(f"{'站上' if c >= ma else '跌破'} {n} 日線（{(c / ma - 1) * 100:+.1f}%）".replace("-", "−"))
        add("tech", "技術指標", "、".join(parts), d)
    return out


# ── 主程式 ──────────────────────────────────────────────────────────────────

def _idx_days() -> list[str]:
    return sorted(p.name[:10] for p in (ROOT / "data/lab/fut/idx").glob("*.json.gz"))


def _tx1330(F, d: str) -> float | None:
    ticks = F.load_day(d) or {}
    near = F.near(d, ticks) if ticks else None
    return next((p for s, p, _, _ in reversed(ticks.get(near) or []) if s <= 13 * 3600 + 30 * 60), None)


def checks(days: list[str], cl: dict, night: dict, n: int = 5) -> list[dict]:
    """最近幾天「用夜盤估的開盤」和實際開盤（5 秒指數 09:00:05 那一點）差多少；只算夜盤、逐筆、隔天 5 秒指數都有的日子。"""
    from . import futdata as F
    out = []
    for a, b in zip(days[:-1], days[1:]):
        nt = night.get(a)
        if not nt or nt.get("c") is None or a not in cl:
            continue
        t = _tx1330(F, a)
        v = F.load_idx(b)
        if t is None or not v or len(v) < 2:
            continue
        out.append({"d": b, "est": round(float(cl[a]) + nt["c"] - t), "open": round(v[1])})
    return out[-n:]


def build(asof: str | None = None) -> dict | None:
    from .. import clock
    from . import futdata as F
    from . import heatbubble as BB
    from . import heatdata as HD
    from . import txocalc as TC
    cl = dict(BB.taiex_daily())
    days = [x for x in _idx_days() if asof is None or x <= asof]
    if not days:
        return None
    d = days[-1]
    idx = F.load_idx(d) or []
    if len(idx) < 2:
        return None
    if d not in cl:                                       # 收盤指數檔還沒更新（盤後那班的步驟順序）：用 13:30 那個 5 秒指數
        cl[d] = idx[-1]
    days = [x for x in days if x in cl]
    hi, lo, close = max(idx[1:]), min(idx[1:]), float(cl[d])
    ds = sorted(k for k in cl if k <= d)
    closes = [float(cl[k]) for k in ds]
    hl = []
    for x in days[-40:]:
        v = F.load_idx(x)
        if v and len(v) > 1 and x in cl:
            hl.append((max(v[1:]), min(v[1:]), float(cl[x])))
    nxt = TC.next_trading(date.fromisoformat(d)).isoformat()
    warn = []
    # 台指期：13:30 那一刻（期現價差）、13:45 收盤、成交量分布
    ticks = F.load_day(d) or {}
    near = F.near(d, ticks) if ticks else None
    tx = ticks.get(near) or []
    tx1330 = next((p for s, p, _, _ in reversed(tx) if s <= 13 * 3600 + 30 * 60), None)
    txclose = tx[-1][1] if tx else None
    basis = (tx1330 - close) if tx1330 is not None else 0.0
    if tx1330 is None:
        warn.append("台指期逐筆還沒存，期現價差當 0")
    night = (_read(NIGHT, {}) or {}).get(d)
    if night and night.get("c") is not None and tx1330 is not None:
        est, src = close + night["c"] - tx1330, "夜盤收盤" if night.get("done") else f"夜盤到 {night.get('t')}"
    elif txclose is not None and tx1330 is not None:
        est, src = close + txclose - tx1330, "夜盤未更新，用台指期 13:45 收盤"
        warn.append("夜盤還沒抓到（清晨 05:10 更新）")
    else:
        est, src = close, "夜盤未更新，用加權指數收盤"
    calc = _read(CALC)
    if not calc or calc.get("asof") != d:
        warn.append("選擇權資料還沒更新（每晚 18:35 後）")
        calc_ok = None
    else:
        calc_ok = calc
    iv = (calc_ok or {}).get("atm_iv")
    if iv:
        em, em_src = close * iv * math.sqrt(1 / TRADING_YEAR), "選擇權"
    else:
        rets = [math.log(b / a) for a, b in zip(closes[-21:-1], closes[-20:])]
        sd = (sum(r * r for r in rets) / len(rets)) ** 0.5 if rets else None
        em, em_src = (close * sd if sd else None), "過去 20 天"
    # 價位
    L: list[dict] = []

    def lv(px, kind, name):
        if px is not None and math.isfinite(px):
            L.append({"px": round(px, 1), "kind": kind, "name": name})
    prev = idx[0]
    lv(hi, "price", "昨天最高")
    lv(lo, "price", "昨天最低")
    lv(close, "price", "昨天收盤")
    if night and night.get("h") is not None:
        lv(night["h"] - basis, "night", "夜盤最高（換算）")
        lv(night["l"] - basis, "night", "夜盤最低（換算）")
    pv = pivots(hi, lo, close)
    for k in ("R2", "R1", "P", "S1", "S2"):
        lv(pv[k], "pivot", {"P": "樞紐中心", "R1": "樞紐壓力 1", "R2": "樞紐壓力 2", "S1": "樞紐支撐 1", "S2": "樞紐支撐 2"}[k])
    for n in (5, 20, 60):
        if len(closes) >= n:
            lv(sum(closes[-n:]) / n, "ma", f"{n} 日均線")
    if len(closes) >= 20:
        w = closes[-20:]
        m = sum(w) / 20
        sd = (sum((x - m) ** 2 for x in w) / 20) ** 0.5
        lv(m + 2 * sd, "ma", "布林上緣")
        lv(m - 2 * sd, "ma", "布林下緣")
        lv(max(w), "ma", "近 20 日收盤最高")
        lv(min(w), "ma", "近 20 日收盤最低")
    oi_note = []
    if calc_ok and em:
        for e in [x for x in calc_ok.get("exps") or [] if x["date"] > d][:2]:
            tag = f"{md(e['date'])} 到期"
            band = [r for r in e.get("oi") or [] if abs(r[0] - est) <= FAR * em]
            ca = max((r for r in band if r[0] > est), key=lambda r: r[1], default=None)
            pu = max((r for r in band if r[0] < est), key=lambda r: r[2], default=None)
            if ca and ca[1]:
                lv(ca[0], "opt", f"{tag}買權未平倉最多（{ca[1]:,} 口）")
            if pu and pu[2]:
                lv(pu[0], "opt", f"{tag}賣權未平倉最多（{pu[2]:,} 口）")
            if e.get("pain") and abs(e["pain"] - est) <= FAR * em:
                lv(e["pain"], "opt", f"{tag}最大痛點")
            allc = max(e.get("oi") or [], key=lambda r: r[1], default=None)
            allp = max(e.get("oi") or [], key=lambda r: r[2], default=None)
            if allc and allp:
                oi_note.append(f"{tag}：買權未平倉最多在 {allc[0]:,}（{allc[1]:,} 口）、賣權最多在 {allp[0]:,}（{allp[2]:,} 口）")
    vp = vprofile(tx) if tx else None
    if vp:
        lv(vp["poc"] - basis, "vol", "台指期成交量最多（換算）")
        lv(vp["vah"] - basis, "vol", "成交量 70% 區上緣（換算）")
        lv(vp["val"] - basis, "vol", "成交量 70% 區下緣（換算）")
    if em:
        k0 = math.floor((est - FAR * em) / ROUND) * ROUND
        while k0 <= est + FAR * em:
            if abs(k0 - est) <= FAR * em:
                lv(float(k0), "round", "整數關卡")
            k0 += ROUND
    bands = pick_bands(cluster(L, est), est, em)
    sc = scenarios(bands, est, em, calc_ok, close)
    heat = {n: HD.load(n) or {} for n in ("futi", "opti", "pcr", "mtxoi")}
    fx = facts(d, close, tx1330, night, txclose, closes, hl, _read(MACRO, {}) or {}, heat)
    out = {
        "ver": VER, "made": clock.now_tw().strftime("%Y-%m-%d %H:%M"),
        "d": d, "next": nxt, "close": round(close, 2), "hi": round(hi, 2), "lo": round(lo, 2), "prev": round(prev, 2),
        "tx": {"c1330": tx1330, "close": txclose, "basis": round(basis, 1), "sym": near},
        "night": night, "est": round(est), "est_src": src, "em": _r(em), "em_src": em_src, "iv": iv,
        "bands": [{"lo": round(b["lo"]), "hi": round(b["hi"]), "mid": round(b["mid"]), "n": b["n"], "side": b["side"],
                   "kinds": b["kinds"], "src": [[s["name"], round(s["px"])] for s in sorted(b["src"], key=lambda s: -s["px"])]}
                  for b in bands],
        "oi_note": oi_note, "sc": sc, "facts": fx, "warn": warn, "check": checks(days, cl, _read(NIGHT, {}) or {}),
    }
    out["push"] = push_line(out)
    return out


def push_line(pm: dict) -> str:
    up = sorted((b for b in pm["bands"] if b["side"] == "up"), key=lambda b: b["lo"])
    dn = sorted((b for b in pm["bands"] if b["side"] == "dn"), key=lambda b: -b["hi"])

    def rng(b):
        return f"{b['lo']:,}" if b["lo"] == b["hi"] else f"{b['lo']:,}～{b['hi']:,}"
    s = f"盤前 {md(pm['next'])}（{wd(pm['next'])}）：預估開 {pm['est']:,}（{pm['est_src']}）"
    if up:
        s += f"｜壓力 {rng(up[0])}"
    if dn:
        s += f"｜支撐 {rng(dn[0])}"
    if pm.get("em"):
        s += f"｜正常波動 ±{pm['em']:,}"
    return s + "。"


def write(out: Path = OUT, asof: str | None = None) -> dict | None:
    from .. import fileio
    pm = build(asof)
    if pm is None:
        return None
    old = _read(out)
    if old and {k: v for k, v in old.items() if k != "made"} == {k: v for k, v in pm.items() if k != "made"}:
        return old                                        # 內容沒變就不動檔（盤後那班的「沒有新資料就早退」才不會被時間戳騙）
    fileio.write_text(out, json.dumps(pm, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
    return pm
