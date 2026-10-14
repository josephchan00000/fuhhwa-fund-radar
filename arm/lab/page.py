"""籌碼雷達獨立頁 → dashboard/x9.html（主頁頁尾右下角小點進入；刻意不放導覽列）。

全頁由內嵌 JSON 在瀏覽器端渲染（表格排序／篩選、個股卡、SVG K 線）。輸出決定性：
不寫入任何牆鐘時間，資料沒變時位元組相同 → git 無 diff、不產生空 commit。
個股走勢序列（約占九成體積）另存 dashboard/x9s.json，開個股卡才載入（電腦閒置時預先抓）。

版面（2026-10-14 改版，規劃與定案見 docs/lab_ui_plan.md）：
今日｜個股｜投信｜訊號｜策略｜指數 六個分頁，一打開是「今日」重點；每頁頂端先給白話結論，
分頁內各段全部展開、第二排是跳段目錄（同主頁慣例）。術語旁的 ⓘ 讀同一份辭典 GL，
原「說明」分頁改為頂欄「ⓘ 名詞」。
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path

from . import analyze

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dashboard" / "x9.html"
OUT_SER = ROOT / "dashboard" / "x9s.json"      # 個股走勢序列；三支 workflow 的 git add 要跟 x9.html 一起帶
SLUG = "x9.html"


def build(out: Path = OUT, out_ser: Path = OUT_SER) -> bool:
    data = analyze.run()
    sj = ser_json(data)
    changed = False
    for path, text in ((out_ser, sj), (out, render(data, ser_v=_ver(sj)))):
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        changed = True
    return changed


def _slim(x):
    """整數值的浮點數輸出成整數（2490.0 → 2490），價量序列可省約兩成體積。"""
    if isinstance(x, float):
        return int(x) if x.is_integer() and abs(x) < 1e15 else x
    if isinstance(x, list):
        return [_slim(v) for v in x]
    if isinstance(x, dict):
        return {k: _slim(v) for k, v in x.items()}
    return x


def _dump(x) -> str:
    return json.dumps(_slim(x), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _ver(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def ser_json(data: dict) -> str:
    """個股走勢序列（x9s.json）。自帶日期軸：檔案若比頁面舊（推送觸發的排程用了沒 add 它的舊 workflow），
    圖照樣畫到它自己的日期並標註，不會錯位。"""
    return _dump({"dates": data.get("dates") or [], "ser": data.get("ser") or {}})


def _md(d) -> str:
    """'2026-10-13' → '10/13'。"""
    d = str(d or "")
    return f"{int(d[5:7])}/{int(d[8:10])}" if len(d) >= 10 and d[5:7].isdigit() and d[8:10].isdigit() else "—"


def asof_line(data: dict) -> str:
    """頂欄資料日：多數來源同一天只寫一次，落後的另外標；集保是週資料；ETF 揭露未到齊時標檔數。"""
    a = data.get("asof") or {}
    keys = (("ETF 持股", "pos"), ("價量", "px"), ("法人", "chip"), ("融資券", "margin"))
    ds = [a[k] for _, k in keys if a.get(k)]
    if not ds:
        return "尚無資料"
    main = max(sorted(set(ds), reverse=True), key=ds.count)     # 同票數取較新的一天
    parts = [f"資料日 {_md(main)}"]
    parts += [f"{lbl} {_md(a[k])}" for lbl, k in keys if a.get(k) and a[k] != main]
    if a.get("tdcc"):
        parts.append(f"集保 {_md(a['tdcc'])}（每週）")
    etfs = data.get("etfs") or {}
    if etfs and a.get("pos"):
        n = sum(1 for m in etfs.values() if m.get("d") == a["pos"])
        if n < len(etfs):
            parts.append(f"ETF 揭露 {n}/{len(etfs)} 檔到 {_md(a['pos'])}")
    return " · ".join(html.escape(p) for p in parts)


def render(data: dict, ser_v: str | None = None) -> str:
    main = {k: v for k, v in data.items() if k != "ser"}
    main["serv"] = ser_v or _ver(ser_json(data))
    blob = _dump(main).replace("</", "<\\/")
    return (_HTML.replace("{{SUB}}", asof_line(data)).replace("{{CSS}}", _CSS)
            .replace("{{DATA}}", blob).replace("{{JS}}", _JS))


_HTML = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>籌碼雷達</title>
<style>{{CSS}}</style></head>
<body>
<div class="top"><b>籌碼雷達</b><span class="asof">{{SUB}}</span><a class="back" href="./">返回主頁</a></div>
<header class="hd"><div class="hdi">
  <nav class="tabs" id="tabs">
    <a data-t="today">今日</a><a data-t="stk">個股</a><a data-t="iss">投信</a><a data-t="sig">訊號</a><a data-t="st">策略</a><a data-t="idx">指數</a>
    <a class="glb" id="glb"><i class="gi">i</i>名詞</a>
  </nav>
  <nav class="snav" id="snav"></nav>
</div></header>
<main id="main"></main>
<div id="dv" class="dv" hidden><div class="dvin" id="dvin"></div></div>
<div id="gl" class="dv" hidden><div class="dvin" id="glin"></div></div>
<div id="pop" class="pop" hidden></div>
<script type="application/json" id="labdata">{{DATA}}</script>
<script>{{JS}}</script>
</body></html>
"""

_CSS = """
:root{--bg:#fff;--card2:#f4f6fa;--ink:#1f2733;--ink2:#44505f;--mut:#727e8c;--line:#e8ebf1;--acc:#2563c9;
--accd:#1c4fa8;--gain:#d33a34;--loss:#1f9d57;--gold:#a16207;--inset:#eef2f8;--warn:#b45309;--hlbg:#dce7fa;
--gainbg:#fdecea;--lossbg:#e6f5ec}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"PingFang TC","Noto Sans TC",Segoe UI,sans-serif;-webkit-text-size-adjust:100%}
a{color:var(--acc);text-decoration:none;cursor:pointer}
table,.fv,.num{font-variant-numeric:tabular-nums}
.top{display:flex;align-items:baseline;gap:4px 12px;flex-wrap:wrap;padding:10px 16px 4px;max-width:1180px;margin:0 auto}
.top b{font-size:18px}.asof{color:var(--mut);font-size:12.5px;flex:1;min-width:0}
.back{font-size:13px;color:var(--mut);white-space:nowrap}
.hd{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--line)}
.hdi{max-width:1180px;margin:0 auto;padding:0 16px}
.tabs{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar,.snav::-webkit-scrollbar{display:none}
.tabs a{padding:9px 12px 7px;color:var(--mut);font-weight:700;white-space:nowrap;border-bottom:3px solid transparent}
.tabs a.on{color:var(--ink);border-bottom-color:var(--acc)}
.tabs .glb{margin-left:auto;font-weight:600;color:var(--accd);display:inline-flex;align-items:center;gap:2px}
.tabs .glb .gi{margin:0 2px 0 0;border-color:var(--acc);color:var(--acc)}
.snav{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding:6px 0 7px;border-top:1px solid var(--line)}
.snav:empty{display:none}
.snav a{padding:2px 10px;border-radius:12px;color:var(--ink2);font-size:13px;white-space:nowrap}
.snav a.on{background:var(--hlbg);color:var(--accd);font-weight:700}
main{padding:16px 16px 90px;max-width:1180px;margin:0 auto}
.sec{margin:0 0 34px}
.sec>h2{display:flex;align-items:baseline;flex-wrap:wrap;gap:2px 10px;font-size:17px;margin:0 0 10px;line-height:1.45}
.sec>h2 .sub{font-size:12.5px;font-weight:400;color:var(--mut)}
.sec>h2 .rt{margin-left:auto;font-size:13px;font-weight:600}
.intro{color:var(--ink2);font-size:13.5px;margin:0 0 18px;line-height:1.8}
.lead{background:var(--card2);border-radius:12px;padding:10px 16px 10px 12px}
.lead ul{margin:0;padding-left:20px}.lead li{margin:7px 0;line-height:1.75}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:14px 32px}
.g2 h3{font-size:14px;margin:0 0 2px;padding-bottom:4px;border-bottom:2px solid var(--line)}
.fl,.nb{display:grid;grid-template-columns:minmax(0,1.15fr) 64px minmax(36px,1fr) 74px;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid var(--line);cursor:pointer}
.nb{grid-template-columns:minmax(0,1fr) minmax(0,2.2fr) 70px}
.fl:hover,.nb:hover{background:#f8fafd}
.fn{min-width:0;display:flex;flex-direction:column;line-height:1.3}
.fn b{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fn i{font-style:normal;color:var(--mut);font-size:12px}
.fv{text-align:right;font-weight:700;white-space:nowrap}
.fb{height:8px;background:var(--inset);border-radius:4px;overflow:hidden}
.fb i{display:block;height:100%;border-radius:4px}.fb .bu{background:var(--gain)}.fb .bd{background:var(--loss)}
.fi{font-size:12px;color:var(--mut);text-align:right;white-space:nowrap}
.flh{cursor:default;padding:2px 4px;border-bottom:0;font-size:11.5px;color:var(--mut)}.flh:hover{background:none}
.flh span:nth-child(2),.flh span:nth-child(4){text-align:right}
.nbs{display:grid;grid-auto-flow:column;grid-template-columns:1fr 1fr;column-gap:32px}
.cr{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1.4fr) 110px;gap:2px 14px;align-items:center;padding:8px 4px;border-bottom:1px solid var(--line);cursor:pointer}
.cr:hover{background:#f8fafd}.crc{font-weight:600}.crs{text-align:right;line-height:1.35}.crs .st{display:block;font-size:11.5px}
.rk2{padding:10px 0;border-bottom:1px solid var(--line)}.rk2>b{font-size:14.5px}.rk2>.st{margin-left:8px}.rk2 .inl{margin-top:4px}
.tg{display:inline-block;font-size:12px;padding:0 7px;border-radius:9px;background:var(--card2);color:var(--ink2);margin:1px 4px 1px 0;line-height:1.75;white-space:nowrap}
.tg.hot{background:var(--hlbg);color:var(--accd)}.tg.rk{background:var(--gainbg);color:var(--gain)}
.evs{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.ev{border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.ev .cdn{font-size:24px;font-weight:800;color:var(--accd);line-height:1.2}.ev .cdn small{font-size:13px;font-weight:600;margin-left:2px}
.ev .evn{font-weight:700;margin-top:2px}.ev .evm{font-size:12.5px;color:var(--mut)}
.sgs{display:flex;flex-wrap:wrap;gap:8px}
.sgc{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border-radius:10px;background:var(--card2);color:var(--ink);font-size:14px}
.sgc b{color:var(--accd)}.sgc.rk{background:var(--gainbg)}.sgc.rk b{color:var(--gain)}.sgc.z{opacity:.55}
.gi{display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;border:1px solid #b6bfcb;color:var(--mut);font:italic 700 10px/1 Georgia,"Times New Roman",serif;margin:0 2px 0 4px;cursor:help;vertical-align:1px;user-select:none;flex:0 0 auto}
.gi:hover{border-color:var(--acc);color:var(--acc)}
.pop{position:fixed;z-index:80;background:#1f2733;color:#fff;font-size:13px;line-height:1.7;padding:9px 12px;border-radius:10px;box-shadow:0 6px 24px rgba(15,23,42,.25)}
.pop b{display:block;margin-bottom:2px;font-size:13.5px}
.bar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 10px}
.bar input[type=search]{flex:1 1 180px;min-width:150px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;font:inherit;background:var(--card2)}
.ch{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:14px;background:var(--card2);color:var(--ink);font-size:13px;cursor:pointer;user-select:none;border:0}
.ch.on{background:var(--acc);color:#fff}.ch.rk{background:var(--gainbg);color:var(--gain)}.ch.rk.on{background:var(--gain);color:#fff}
.ch i{font-style:normal;opacity:.7;font-size:12px}
.fbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 10px}
.fbar input[type=search]{flex:1 1 220px;min-width:160px;padding:8px 12px;border:1px solid var(--line);border-radius:10px;font:inherit;background:var(--card2)}
.fbar select{padding:7px 30px 7px 10px;border:1px solid var(--line);border-radius:10px;font:inherit;font-size:14px;color:var(--ink);background:var(--bg) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23727e8c'/%3E%3C/svg%3E") no-repeat right 11px center;-webkit-appearance:none;appearance:none;max-width:100%}
.tgl{display:inline-flex;align-items:center;gap:6px;font-size:14px;color:var(--ink2);cursor:pointer;user-select:none;white-space:nowrap}
.tgl input{width:16px;height:16px;margin:0;accent-color:var(--acc)}
.vbar{display:flex;align-items:center;gap:10px;margin:0 0 8px;flex-wrap:wrap}
.seg{display:inline-flex;background:var(--card2);border-radius:10px;padding:3px}
.seg a{padding:5px 14px;border-radius:8px;color:var(--ink2);font-size:14px;font-weight:600;white-space:nowrap}
.seg a.on{background:var(--bg);color:var(--accd);box-shadow:0 1px 3px rgba(15,23,42,.14)}
.cnt{margin-left:auto;color:var(--mut);font-size:13px}
th small{font-weight:400;margin-left:2px;font-size:11px}
.db{display:block;position:relative;height:5px;margin:4px 0 1px;min-width:64px;background:linear-gradient(var(--line),var(--line)) center/1px 100% no-repeat}
.db i{position:absolute;top:0;height:100%;border-radius:3px}.db .bu{left:50%;background:var(--gain)}.db .bd{right:50%;background:var(--loss)}
.stk td:first-child{min-width:104px;max-width:170px;white-space:normal}
.stk .nm,.stk .cd{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px}
a.sm{font-size:12.5px;font-weight:600;margin-left:6px}
.tw{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap;vertical-align:middle}
th{background:var(--card2);color:var(--mut);font-weight:600;font-size:12.5px}
th[data-k]{cursor:pointer}th.on{color:var(--accd)}
td:first-child,th:first-child{text-align:left;position:sticky;left:0;background:var(--bg);z-index:1}
th:first-child{background:var(--card2);z-index:2}
td.l,th.l{text-align:left}td.wr{white-space:normal;min-width:120px;max-width:220px}
tr[data-c]{cursor:pointer}tr[data-c]:hover td{background:#f8fafd}
.nm{display:block;font-weight:600}.cd{color:var(--mut);font-size:12px}
.up{color:var(--gain)}.dn{color:var(--loss)}.mu{color:var(--mut)}
.sg{display:inline-block;font-size:11.5px;padding:1px 7px;border-radius:9px;background:rgba(37,99,201,.1);color:var(--accd);margin:1px 2px 1px 0}
.sg.rk{background:var(--gainbg);color:var(--gain)}
.more{display:block;margin:12px auto;padding:8px 18px;border:0;border-radius:8px;background:var(--card2);font:inherit;cursor:pointer}
details.mr{margin:8px 0 0}
details.mr>summary{cursor:pointer;color:var(--acc);font-size:13.5px;list-style:none;padding:4px 0}
details.mr>summary::-webkit-details-marker{display:none}
details.mr>summary:before{content:"▸ "}details.mr[open]>summary:before{content:"▾ "}
.inl{line-height:2;font-size:14px}.inl .mu{font-size:12px;margin-left:2px}.inl .it{white-space:nowrap}
.bdg{display:flex;flex-wrap:wrap;align-items:center;gap:4px 14px;font-size:13px;color:var(--ink2);margin:0 0 10px}
.rls{margin:2px 0 10px}.rl{display:grid;grid-template-columns:4.5em minmax(0,1fr);gap:8px;padding:3px 0;font-size:13.5px;line-height:1.7}
.rl.nl{grid-template-columns:1fr}.rl .rlk{color:var(--mut);font-weight:600;white-space:nowrap}
h4.sh{font-size:14px;margin:14px 0 6px;color:var(--ink)}
.ish{margin:0 0 8px}.tg.mu{color:var(--mut)}
.isr{display:grid;grid-template-columns:96px minmax(0,1fr);gap:4px 12px;padding:7px 0;border-top:1px solid var(--line)}
.isk{font-weight:700;font-size:13.5px;white-space:nowrap}.isk i{font-style:normal;font-weight:400;color:var(--mut);font-size:12px;margin-left:5px}
.isc .inl{line-height:1.9}.eit{margin-right:14px;white-space:nowrap}.evl .xh{display:none}.evl.open .xh{display:inline}a.xm{font-size:13px;white-space:nowrap}
.card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:0 0 16px}
.card h4{margin:0 0 4px;font-size:15.5px}
.st{font-size:12.5px;color:var(--mut)}
.pill{display:inline-block;font-size:11.5px;padding:0 6px;border-radius:7px;background:var(--card2);color:var(--mut);font-weight:600}
.k-new{color:var(--gain);font-weight:700}.k-add{color:var(--gain)}.k-cut{color:var(--loss)}.k-exit{color:var(--loss);font-weight:700}
.grey td{color:#a0a8b3}
.stc{padding:6px 14px 10px}
.sq{display:grid;grid-template-columns:5.6em minmax(0,1fr);gap:4px 12px;padding:10px 0;border-top:1px solid var(--line)}
.sq:first-child{border-top:0}
.sqk{font-weight:700;color:var(--accd);font-size:13.5px;white-space:nowrap;padding-top:1px}
.sq>div{font-size:14px;line-height:1.75;min-width:0}
.sqe{margin-top:5px;font-size:13px;color:var(--ink2);background:var(--card2);border-radius:8px;padding:6px 10px}
.fxs{display:flex;flex-wrap:wrap;gap:2px 16px}.fx{font-size:13.5px;color:var(--ink2)}
.pcs{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.pcn{font-size:13.5px;color:var(--ink2);margin:0 0 8px}
.pc{border:1px solid var(--line);border-radius:10px;padding:8px 12px 9px}
.pch{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:3px}.pch a b{font-size:15px}.pk{color:var(--ink)}
.pcr{display:grid;grid-template-columns:4.8em minmax(0,1fr);gap:8px;font-size:13px;line-height:1.7}.pcr>span:first-child{color:var(--mut)}
.pcw{font-size:12.5px;line-height:1.65;margin-top:5px;color:var(--ink2)}.pcw b{margin-right:6px;color:var(--mut);font-weight:600}
.pcx{font-size:12.5px;line-height:1.6;margin-top:4px;color:var(--warn)}
.tvs{display:grid;gap:8px}.tv{border:1px solid var(--line);border-radius:10px;padding:7px 12px 8px}.tv.ctl{background:var(--card2);border-color:transparent}
.tvh{display:flex;justify-content:space-between;align-items:baseline;gap:4px 8px;flex-wrap:wrap}.tvh b{font-size:14.5px}
.tvm{font-size:13px;color:var(--ink2);margin-top:1px}.tvt{font-size:13px;line-height:1.7}.sm2{font-size:12px;color:var(--mut);line-height:1.5}
.crb{display:inline-block;position:relative;width:64px;height:8px;background:var(--card2);border-radius:4px;vertical-align:middle;margin-right:8px}
.crb::after{content:'';position:absolute;left:50%;top:-2px;bottom:-2px;border-left:1px solid #b6bfcb}
.crb i{position:absolute;top:0;bottom:0;background:var(--acc);border-radius:4px}
.dv{position:fixed;inset:0;z-index:50;background:rgba(15,23,42,.35);overflow-y:auto;overscroll-behavior:contain}
h3{font-size:14.5px;margin:18px 0 6px;color:var(--accd)}
.dvin{background:var(--bg);max-width:980px;margin:0 auto;min-height:100%;padding:0 16px 60px}
.dvh{position:sticky;top:0;z-index:3;background:var(--bg);border-bottom:1px solid var(--line);margin:0 -16px;padding:10px 16px 0}
.dvt{display:flex;align-items:center;gap:10px;padding-bottom:6px}
.dvt .ttl{flex:1;min-width:0}.dvt .ttl b{display:block;font-size:19px;line-height:1.3}
.dvt .ttl .cd{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pxw{text-align:right;line-height:1.3;white-space:nowrap}.pxw b{display:block;font-size:18px}
.nv{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:9px;background:var(--card2);color:var(--accd);font-size:22px;line-height:1;user-select:none;flex:0 0 auto}
.nv.off{opacity:.3;pointer-events:none}
.x{font-size:26px;line-height:1;color:var(--mut);padding:0 2px 2px 6px;flex:0 0 auto}
.cnav{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding:2px 0 8px}.cnav::-webkit-scrollbar{display:none}
.cnav a{padding:2px 10px;border-radius:12px;color:var(--ink2);font-size:13px;white-space:nowrap}
.cnav a.on{background:var(--hlbg);color:var(--accd);font-weight:700}
.csec{padding:16px 0 4px}
.csec>h3{font-size:16px;color:var(--ink);margin:0 0 10px}.csec>h3 .sub{font-size:12px;color:var(--mut);font-weight:400;margin-left:8px}
.sgrow{margin:0 0 2px}
.sum{margin:6px 0 14px;padding-left:20px}.sum li{margin:6px 0;line-height:1.75}
.kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.kp{background:var(--card2);border-radius:10px;padding:8px 11px;min-width:0}
.kp>span{display:flex;align-items:center;color:var(--mut);font-size:12px;white-space:nowrap}
.kp>b{display:block;font-size:18px;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kp>em{display:block;font-style:normal;font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kps .kp>b{font-size:15px}
.hdt td,.hdt th{padding:6px 7px}

.pasl{margin:10px 0 0;font-size:13.5px;line-height:1.8}.nw{white-space:nowrap}
.sgi{padding:8px 0;border-bottom:1px solid var(--line)}
.lg{margin-top:6px}.lg .dsh{width:16px;height:0;border-top:2px dashed #a16207;background:none}.lg b{font-size:11px;margin-right:3px}
.ld{padding:44px 12px;text-align:center;color:var(--mut);font-size:13.5px;background:var(--card2);border-radius:10px}
.tip{position:absolute;pointer-events:none;background:rgba(31,39,51,.94);color:#fff;font-size:12px;line-height:1.6;padding:6px 9px;border-radius:8px;max-width:min(380px,94%);z-index:2}
.note{color:var(--mut);font-size:12px;margin:4px 0}
svg{display:block;width:100%;height:auto}
.lg{display:flex;flex-wrap:wrap;gap:10px;font-size:12px;color:var(--mut)}.lg i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}
ul.doc{padding-left:18px}ul.doc li{margin:4px 0}
.cw{position:relative}
.glh{font-size:15px;color:var(--accd);margin:20px 0 6px}
.gll{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:0 22px}
.gll div{padding:8px 0;border-bottom:1px solid var(--line)}
.gll b{display:block;font-size:14px}.gll span{font-size:13px;color:var(--ink2);line-height:1.7}
@media(min-width:760px){.dvin{margin:24px auto;min-height:auto;border-radius:12px}}
@media(min-width:1100px){
 .dv.pane{left:auto;width:min(640px,46vw);background:var(--bg);border-left:1px solid var(--line);box-shadow:-10px 0 30px rgba(15,23,42,.10)}
 .dv.pane .dvin{margin:0;max-width:none;min-height:100%;border-radius:0}
 body.pane .top,body.pane .hdi,body.pane main{margin-right:calc(min(640px,46vw) + 12px);margin-left:20px;max-width:none}
}
@media(max-width:760px){.g2{grid-template-columns:1fr}.nbs{grid-auto-flow:row;grid-template-columns:1fr;grid-template-rows:none!important}}
@media(max-width:600px){
 .top{padding:8px 12px 2px}.asof{flex-basis:100%;order:3;font-size:12px}
 .hdi{padding:0 6px}.tabs a{padding:9px 9px 7px;font-size:14.5px}
 main{padding:14px 12px 90px}
 .fl{grid-template-columns:minmax(0,1fr) 58px 52px 62px;gap:6px}
 .nb{grid-template-columns:minmax(0,1fr) minmax(0,1.6fr) 56px;gap:6px}
 .cr{grid-template-columns:minmax(0,1fr) 96px}.cr .crc{grid-column:1/-1;grid-row:2}.cr .crs{grid-column:2;grid-row:1}
 .rk2>.st{display:block;margin:2px 0 0}
 .fbar input[type=search]{flex-basis:100%}.fbar select{flex:1 1 0;min-width:0}
 .seg a{padding:5px 11px}
 .stk td:first-child{min-width:92px;max-width:118px}.stk .nm,.stk .cd{max-width:108px}
 .hm{display:none}
 .isr{grid-template-columns:1fr;gap:2px}.rl{grid-template-columns:4em minmax(0,1fr)}
 .sq{grid-template-columns:1fr;gap:3px}.stc{padding:4px 12px 8px}
 .kp>b{font-size:16px}.kps{grid-template-columns:repeat(2,minmax(0,1fr))}.kps.k3{grid-template-columns:repeat(3,minmax(0,1fr))}
 .dvt{gap:8px}.dvt .ttl b{font-size:17px}.pxw b{font-size:16px}
}
"""

_JS = r"""
const D=JSON.parse(document.getElementById('labdata').textContent);
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const E=D.etfs||{},SD=D.sigdef||{},RISK=new Set(D.risk||[]);
const ROWS=D.rows||[],BY={};ROWS.forEach(r=>BY[r.c]=r);
const KN={new:'新建倉',add:'加碼',cut:'減碼',exit:'出清',hold:'—'};
function f(x,d=1){if(x===null||x===undefined||Number.isNaN(x))return '—';const v=Number(x);return v.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});}
function sgn(x,d=1,suf=''){if(x===null||x===undefined)return '<span class=mu>—</span>';const c=x>0?'up':x<0?'dn':'mu';return `<span class=${c}>${x>0?'+':''}${f(x,d)}${suf}</span>`;}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function md(d){d=String(d||'');return d.length>=10?esc(`${+d.slice(5,7)}/${+d.slice(8,10)}`):(d?esc(d):'—');}
function fp(x){return x==null?'—':f(x,x>=500?0:x>=50?1:2);}
function sgChips(arr){return (arr||[]).map(k=>`<span class="sg${RISK.has(k)?' rk':''}">${esc((SD[k]||[k])[0])}</span>`).join('');}
function issOf(etfs){return [...new Set((etfs||[]).map(e=>(E[e]||{}).is||e))];}
function sec(id,nav,title,sub,body,rt=''){return `<section class=sec id="${id}" data-nav="${esc(nav)}"><h2>${title}${sub?`<span class=sub>${sub}</span>`:''}${rt?`<span class=rt>${rt}</span>`:''}</h2>${body}</section>`;}
const MK={tw:'上市',tp:'上櫃',os:'海外'};const MKF={twall:'台股',tw:'上市',tp:'上櫃',os:'海外',all:'全部'};
const S={tab:'today',q:'',mk:'twall',sig:'',liq:false,sort:'a5v',dir:-1,n:60,vw:'etf'};let STK=[];
try{const z=JSON.parse(localStorage.getItem('lab.s')||'{}');for(const k of ['mk','sort','dir','liq','vw'])if(k in z)S[k]=z[k];}catch(e){}
if(!({etf:1,chip:1,ta:1})[S.vw])S.vw='etf';
function save(){try{localStorage.setItem('lab.s',JSON.stringify({mk:S.mk,sort:S.sort,dir:S.dir,liq:S.liq,vw:S.vw}));}catch(e){}}

/* ---------- 名詞辭典（ⓘ 與「名詞」頁共用） ---------- */
const GL={
'真加碼':'ETF 有人申購時，所有持股會照比例一起增加，那不代表看好。扣掉這個「申購帶來的等比例增加」後剩下的部分，才算經理人主動加碼（真減碼同理）。',
'申贖倍率':'同一檔 ETF 兩次揭露之間，共同持股股數比值的中位數；大於 1＝有申購、小於 1＝有贖回。',
'主動 5 日淨買':'近 5 個交易日，所有主動式 ETF 對這檔的真加碼減掉真減碼，乘以現價換算成金額（億元）。正＝淨買、負＝淨賣。',
'加碼／減碼家數':'近 5 個交易日有真加碼或新建倉的投信家數／有真減碼或出清的投信家數。同一家投信旗下不同 ETF 方向相反時，兩邊都會算到。',
'持有 ETF':'目前持有這檔股票的追蹤 ETF 檔數（主動式／被動式）。',
'新建倉':'主動 ETF 在觀測期內第一次持有這檔股票。',
'建倉日':'觀測期內第一次出現在該 ETF 持股的日期；標「≤」代表觀測起點前就已持有。',
'主動成本':'近期新建倉的主動 ETF 平均買在多少：只算開始追蹤（7/27 起）之後才新建倉的部位——建倉、加碼按當天成交均價入帳，減碼按平均成本扣除，再把各檔 ETF 合起來平均。追蹤前就持有的舊部位，網路上查不到真正的買價，所以不計。未計配息與手續費。',
'成本乖離':'現價比主動 ETF 新建倉成本高（正）或低（負）多少 %。沒有近期新建倉的股票不計算。',

'超配':'主動 ETF 給這檔的平均權重，減去它占台股（上市＋上櫃普通股）總市值的比重，單位百分點。正＝比市值權重更看好。台積電在主動 ETF 約占一成、市值占比卻近四成，所以是負的。',
'ETF 持股率':'所有追蹤 ETF 合計持股 ÷ 發行股數。',
'消化天數':'ETF 合計持股 ÷ 20 日均量：如果這些 ETF 一起出清，大約要賣幾天。',
'投信 5 日':'官方三大法人資料：投信近 5 個交易日買賣超（張）。',
'外資 5 日':'官方三大法人資料：外資近 5 個交易日買賣超（張）。',
'連買':'連續買超（正）或連續賣超（負）的天數。',
'60 日買超均價':'近 60 個交易日中，該法人買超那幾天的成交均價（以買超張數加權），可當作它近期進場成本的參考。',
'融資':'融資餘額的變化：增加代表散戶用槓桿買進的部位變多。',
'借券賣出':'借券賣出餘額（張），屬放空部位的一種；只有上市股票有資料。',
'千張大戶':'集保股權分散表中持有超過 1,000 張的股東，合計持股占比；每週公布一次。',
'趨勢':'依收盤價與 5／20／60 日均線排列：收盤＞5 日＞20 日＞60 日線＝多頭，反過來＝空頭，其餘＝整理。',
'乖離':'收盤價比 20 日（或 60 日）均線高出或低於多少 %。',
'量比':'今日成交量 ÷ 20 日均量；大於 1.5 代表明顯放量。',
'RSI':'14 日相對強弱指標，0～100；70 以上偏熱、30 以下偏冷。',
'KD':'9 日隨機指標，0～100；80 以上偏熱、20 以下偏冷。',
'MACD':'MACD 柱狀體：正＝短期動能強於長期；「剛翻正／翻負」代表剛轉向。',
'一年區間位置':'現價落在近一年最低價到最高價之間的哪裡：0%＝一年低點、100%＝一年高點。',
'相對大盤':'近 20 日漲跌減去加權指數同期漲跌（百分點）。',
'ATR':'平均真實區間（14 日）÷ 股價：每天正常的波動幅度。停損常設在 2～3 倍 ATR。',
'日均成交':'近 20 日平均成交金額（億元）。',
'超額':'報酬減去同期加權指數報酬；正＝贏大盤。成績已扣來回交易成本 0.585%。',
'勝率':'超額報酬為正的次數比例。',
'隔夜跳空':'訊號出現後隔天的開盤價，相對訊號日收盤的漲跌。跟單的人多時，好處常在隔夜就被反映掉。',
'樣本':'歷史上符合條件的次數。少於 30 次時結果容易受單一段行情左右，只能當參考。',
'紙上交易':'照寫死的規則自動記帳、不實際下單，用來驗證策略在「規則訂好之後」的真實表現。',
'樣本內':'規則訂定前的歷史資料。規則本來就是看這段資料挑出來的，成績會偏好看，只能當參考。',
'前瞻':'規則起算日之後才發生的訊號；這部分的成績才算數。',
'驗證期滿':'累積 30 筆交易或 30 個交易日（先到者）。平均超額＞0 且勝率＞50% 才算達標。',
'資料截止日':'指數公司用來排名的那一天收盤資料（臺灣50：生效日前約 4 週的週一）。截止日之後股價再怎麼變，都不影響這一次的名單。',
'漲勢前一半':'同一次審核的納入股，依資料截止日前 40 個交易日的漲幅排序，取前一半（無條件進位；只有 1 檔就是它）。',
'被動買盤':'0050＋006208 規模 ÷ 前 50 大市值＝被動資金持有比例，乘上發行股數，估計生效日要買進的張數；沒有做自由流通調整，是估計值。',
'週轉率':'20 日平均成交股數 ÷ 發行股數（%）；越高代表市場越熱衷交易這檔。',
'估計權重':'新納入股在臺灣50 的權重估計＝個股市值 ÷ 前 50 大市值合計（未做自由流通調整）。被動買盤金額約＝0050＋006208 規模 × 權重。新進的股票都剛擠進前 40 名，彼此權重差不多。',
'被動買賣期間':'被動 ETF 實際買進新成分股、賣出刪除股的那幾個交易日，依官方「投信買賣超」推得：0056 在生效日（第三個週五）收盤起 5 天；00919、00929 從公告當天收盤起約 8 天（00919 有幾次提前 2～3 天）；00878 約生效日前 5～6 天到生效後幾天。',
'對其他成分股':'和同一次審核前後都留在指數裡的成分股（等權平均）比，扣掉高股息類股整體的漲跌，剩下的才是「被納入／被刪除」本身的影響。',
'被動買賣日量':'被動 ETF 換股要買（賣）的金額 ÷ 該股 20 日平均成交金額＝要用掉幾天的正常成交量。高股息 ETF 規模大，冷門中型股一次常是 10 天以上的量；台積電這類權值股不到 1 天。',
'被動買賣提醒':'高股息換股的納入股估計被動買盤 ≥5 日量：被動買盤結束後 10 個交易日，過去多半輸大盤、也輸其他成分股 → 已持有的在最後一天收盤前出、沒持有的不追；刪除股被賣完後也沒有反彈。只是提醒，不做放空。',
'等級相關':'兩組數字的排序有多一致，−1～+1：+1＝排序完全相同、0＝看不出關係、負＝反方向。這裡樣本只有十幾檔，看方向與大小就好。',
};
const GLG=[['ETF 面',['真加碼','申贖倍率','主動 5 日淨買','加碼／減碼家數','持有 ETF','新建倉','建倉日','主動成本','成本乖離','超配','ETF 持股率','消化天數']],
 ['法人籌碼',['投信 5 日','外資 5 日','連買','60 日買超均價','融資','借券賣出','千張大戶']],
 ['技術面',['趨勢','乖離','量比','RSI','KD','MACD','一年區間位置','相對大盤','ATR','日均成交']],
 ['成績與策略',['超額','勝率','隔夜跳空','樣本','紙上交易','樣本內','前瞻','驗證期滿']],
 ['指數換股',['資料截止日','漲勢前一半','估計權重','被動買盤','週轉率','等級相關','被動買賣期間','對其他成分股','被動買賣日量','被動買賣提醒']]];
function gi(k){return (GL[k]||SD[k])?`<i class=gi data-g="${esc(k)}" role=button tabindex=0 aria-label="說明">i</i>`:'';}
const POP=$('#pop');let popFor=null,popPin=false;
function showPop(el,pin){const k=el.dataset.g;const t=GL[k]||(SD[k]||[])[1];if(!t)return;
  POP.innerHTML=`<b>${esc(SD[k]?SD[k][0]:k)}</b>${esc(t)}`;POP.hidden=false;popFor=el;popPin=!!pin;
  const r=el.getBoundingClientRect(),w=Math.min(300,innerWidth-24);POP.style.width=w+'px';
  POP.style.left=Math.min(Math.max(12,r.left+r.width/2-w/2),innerWidth-w-12)+'px';POP.style.top=(r.bottom+8)+'px';
  const ph=POP.offsetHeight;if(r.bottom+8+ph>innerHeight-8)POP.style.top=Math.max(8,r.top-ph-8)+'px';}
function hidePop(){POP.hidden=true;popFor=null;popPin=false;}
document.addEventListener('click',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');
  if(g){e.stopPropagation();e.preventDefault();if(popFor===g&&popPin)hidePop();else showPop(g,true);return;}
  if(!e.target.closest||!e.target.closest('#pop'))hidePop();},true);
document.addEventListener('keydown',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');if(g&&(e.key==='Enter'||e.key===' ')){e.preventDefault();showPop(g,true);}});
if(matchMedia('(hover:hover)').matches){
  document.addEventListener('mouseover',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');if(g&&!popPin)showPop(g,false);});
  document.addEventListener('mouseout',e=>{const g=e.target.closest&&e.target.closest('.gi[data-g]');if(g&&!popPin)hidePop();});}
addEventListener('scroll',()=>{if(!POP.hidden)hidePop();},true);

/* ---------- 共用：點代號開個股卡 ---------- */
document.addEventListener('click',e=>{if(e.defaultPrevented)return;const a=e.target.closest&&e.target.closest('[data-c]');
  if(a&&BY[a.dataset.c]){e.preventDefault();if(!a.closest('#dv'))CTX=ctxOf(a);openStock(a.dataset.c);}});

/* ---------- 今日 ---------- */
function nmL(r){return `<a data-c="${esc(r.c)}">${esc(r.n)}</a>`;}
function cntGroup(list){const out=[];let i=0;while(i<list.length){let j=i;while(j+1<list.length&&list[j+1][1]===list[i][1])j++;
  out.push(list.slice(i,j+1).map(x=>x[0]).join('、')+`（${j>i?'各 ':''}${list[i][1]} 家）`);i=j+1;}return out.join('、');}
function allCands(){const out=[];
  for(const s of ((D.strat||{}).list||[]))for(const c of (s.cands||[]))out.push({...c,st:s.name,cond:c.gap_max===0?`開盤低於 ${f(c.px,2)} 才進`:'隔日開盤價進場'});
  const s5=(D.grow||{}).s5;if(s5)for(const t of (s5.fwd||[]))if(t.st==='cand')out.push({c:t.c,n:t.n,d:t.d,st:s5.name,cond:'隔日開盤買；開高 ≥3% 不追（最多等 5 日）',stop:null});
  const s3=((D.strat||{}).list||[]).find(s=>s.key==='s3');
  if(s3)for(const [k,nm] of [['early','臺灣50・提前卡位'],['post','臺灣50・公告後進場']])for(const i of s3Cands(s3,k)){const t=k==='early'?i.ta:i.tb;
    out.push({c:i.c,n:i.n,d:k==='early'?(i.t?s3.plan.cutoff:s3.plan.e_sig):s3.plan.announce,st:nm,cond:`開盤買，${md(t.out)} 收盤賣（生效前一天）${k==='early'&&!i.t?'；截止日名單沒有就隔天開盤賣':''}`,stop:null});}
  return out;}
function idxEvents(){const out=[];for(const r of ((D.idx||{}).cal||[])){if(r[6]&&r[10]!=null&&r[10]>=0)out.push({n:r[1],etf:(r[2]||[]).join(' '),cut:r[4],ann:r[5],eff:r[6],tr:r[7],stt:r[8],conf:r[9],days:r[10],pred:r[12]});}
  return out.sort((a,b)=>a.days-b.days);}
function chgI(x){return x==null?'':` · <span class=${x>0?'up':x<0?'dn':''}>${x>0?'+':''}${f(x,1)}%</span>`;}
function flowRows(rs,m,side){if(!rs.length)return '<div class=st>無</div>';
  return `<div class="fl flh"><span>股票・今日漲跌</span><span>億元</span><span></span><span>投信家數${gi('加碼／減碼家數')}</span></div>`+rs.map(r=>{const w=Math.max(3,Math.abs(r.a5v)/m*100);
  return `<div class=fl data-c="${esc(r.c)}"><span class=fn><b>${esc(r.n)}</b><i>${esc(r.c)}${chgI(r.ch)}</i></span><span class="fv ${r.a5v>0?'up':'dn'}">${r.a5v>0?'+':''}${f(r.a5v,1)}</span><span class=fb><i class=${r.a5v>0?'bu':'bd'} style="width:${w.toFixed(0)}%"></i></span><span class=fi>${side==='sell'?`${(r.ic5||[]).length} 減・${(r.ia5||[]).length} 加`:`${(r.ia5||[]).length} 加・${(r.ic5||[]).length} 減`}</span></div>`;}).join('');}
function candRows(cs){return cs.map(c=>`<div class=cr data-c="${esc(c.c)}"><div class=fn><b>${esc(c.n)}</b><i>${esc(c.c)} · ${esc(c.st)} · 訊號日 ${md(c.d)}</i></div><div class=crc>${esc(c.cond)}</div><div class=crs><span class=st>停損參考</span><b>${c.stop==null?'—':f(c.stop,2)}</b></div></div>`).join('');}
function vToday(){
  const tw=ROWS.filter(r=>r.m!=='os');
  const buys=tw.filter(r=>r.a5v>0).sort((a,b)=>b.a5v-a.a5v),sells=tw.filter(r=>r.a5v<0).sort((a,b)=>a.a5v-b.a5v);
  const bs=buys.reduce((s,r)=>s+r.a5v,0),ss=-sells.reduce((s,r)=>s+r.a5v,0),net=bs-ss;
  const has=k=>ROWS.filter(r=>(r.sg||[]).includes(k));
  const cons=has('cons').sort((a,b)=>(b.ia5||[]).length-(a.ia5||[]).length||(b.a5v||0)-(a.a5v||0));
  const exits=has('exit').filter(r=>r.m!=='os').sort((a,b)=>(a.a5v||0)-(b.a5v||0));
  const nbAll=ROWS.filter(r=>(r.nb10||[]).length).map(r=>({r,is:issOf(r.nb10)}));
  const nbs=nbAll.filter(x=>x.r.m!=='os').sort((a,b)=>b.is.length-a.is.length||(b.r.a5v||0)-(a.r.a5v||0));
  const nbOs=nbAll.length-nbs.length;
  const cands=allCands(),evs=idxEvents(),t50=(D.idx||{}).tw50||{};
  const d5=(D.dates||[]).slice(-5);const win=d5.length?`${md(d5[0])}～${md(d5[d5.length-1])}`:'';
  const L=[];
  if(bs||ss){const tone=Math.abs(net)<=0.15*Math.max(bs,ss)?'買賣金額相近，以換股為主':net>0?'整體偏向加碼':'整體偏向減碼';
    L.push(`主動 ETF 近 5 日：淨買的股票合計 <b class=up>${f(bs,0)} 億</b>、淨賣的合計 <b class=dn>${f(ss,0)} 億</b>——${tone}。${gi('主動 5 日淨買')}`);}
  if(cons.length)L.push(`<b>${cons.length} 檔</b>有 3 家以上投信同時加碼${gi('cons')}，最多的是 ${cntGroup(cons.slice(0,3).map(r=>[nmL(r),(r.ia5||[]).length]))}。`);
  if(exits.length)L.push(`<b>${exits.length} 檔</b>被 3 家以上投信同時減碼${gi('exit')}，賣最多的是 ${exits.slice(0,3).map(r=>`${nmL(r)}（${f(r.a5v,1)} 億）`).join('、')}。`);
  if(nbs.length)L.push(`10 日內主動 ETF 新建倉的台股 <b>${nbs.length} 檔</b>${gi('新建倉')}，最多家同時進場的是 ${cntGroup(nbs.slice(0,3).map(x=>[nmL(x.r),x.is.length]))}。`);
  L.push(cands.length?`明日開盤前候選 <b>${cands.length} 檔</b>：${cands.map(c=>`${BY[c.c]?nmL(c):esc(c.n)}（${esc(c.st)}）`).join('、')}。`:'明日開盤前沒有策略候選。');
  if(evs.length){const e=evs[0];L.push(`最近的指數換股：<b>${esc(e.n)}</b>（${esc(e.etf)}）${md(e.eff)} 生效，還有 ${e.days} 天${e.stt==='推算'?'（日期為推算）':''}。`);}
  const s3p=(((D.strat||{}).list||[]).find(s=>s.key==='s3')||{}).plan,dl=(D.dates||[]).slice(-1)[0];
  if(s3p&&dl){const it=s3p.items||[],nm=xs=>xs.map(i=>BY[i.c]?nmL(i):esc(i.n)).join('、'),dd=(new Date(s3p.e_sig)-new Date(dl))/864e5;
    if(s3p.stage==='watch'&&dd>=0&&dd<=10)L.push(`臺灣50 提前卡位：${md(s3p.e_sig)} 收盤選股、${md(s3p.e_in)} 開盤建倉${it.length?`；以今天排名試算會買 ${nm(it)}`:''}。<a data-go="st" data-at="st-s3">看計畫 →</a>`);
    else if(s3p.stage==='early'||s3p.stage==='frozen'){const h=it.filter(i=>(i.e||i.t)&&i.ta&&(i.ta.st==='open'||i.ta.st==='cand')&&i.pred!==false);
      if(h.length)L.push(`臺灣50 提前卡位持有 ${nm(h)}，${md(s3p.out)} 收盤賣${s3p.stage==='early'?`（${md(s3p.cutoff)} 截止日校正）`:''}。<a data-go="st" data-at="st-s3">看計畫 →</a>`);}}
  let h=sec('t-lead','重點','今日重點','',`<div class=lead><ul>${L.map(x=>`<li>${x}</li>`).join('')}</ul></div>`);
  const m=Math.max(1,...buys.slice(0,8).map(r=>r.a5v),...sells.slice(0,8).map(r=>-r.a5v));
  h+=sec('t-flow','買賣',`主動 ETF 買最多／賣最多${gi('主動 5 日淨買')}`,`近 5 個交易日（${win}）淨買金額・已扣申贖${gi('真加碼')}`,
    `<div class=g2><div><h3 class=up>淨買最多</h3>${flowRows(buys.slice(0,8),m,'buy')}</div><div><h3 class=dn>淨賣最多</h3>${flowRows(sells.slice(0,8),m,'sell')}</div></div>`,
    `<a data-go="stk" data-fsig="" data-sort="a5v">看全部 →</a>`);
  const nbTop=nbs.slice(0,10);
  h+=sec('t-new','新建倉',`新建倉${gi('新建倉')}`,`10 個交易日內主動 ETF 第一次買進的台股，依同時進場的投信家數排序；右側＝主動 5 日淨買（億）${nbOs?`。另有海外股 ${nbOs} 檔`:''}`,
    (nbTop.length?`<div class=nbs style="grid-template-rows:repeat(${Math.ceil(nbTop.length/2)},auto)">${nbTop.map(x=>`<div class=nb data-c="${esc(x.r.c)}"><span class=fn><b>${esc(x.r.n)}</b><i>${esc(x.r.c)}</i></span><span>${x.is.map(i=>`<span class="tg${x.is.length>=2?' hot':''}">${esc(i)}</span>`).join('')}</span><span class=fv>${x.r.a5v==null?'':sgn(x.r.a5v,1)}</span></div>`).join('')}</div>`:'<div class=st>10 日內無新建倉</div>')+
    (nbs.length>10?`<details class=mr><summary>其餘 ${nbs.length-10} 檔</summary><div class=inl>${nbs.slice(10).map(x=>`<span class=it><a data-c="${esc(x.r.c)}">${esc(x.r.n)}</a><span class=mu>${x.is.map(esc).join(' ')}</span></span>`).join('　')}</div></details>`:''),
    nbs.length?`<a data-go="stk" data-fsig="nb" data-sort="a5v">全部 ${nbs.length} 檔 →</a>`:'');
  h+=sec('t-cand','候選','明日開盤前候選','策略規則寫死、照規則自動記紙上交易',
    cands.length?candRows(cands):'<div class=st>今日沒有策略候選。</div>',`<a data-go="st">看策略 →</a>`);
  const al=(D.strat||{}).alerts||[];
  h+=sec('t-risk','風險',`風險提醒`,'',
    `<div class=rk2><b>集體撤退 ${exits.length} 檔</b>${gi('exit')}${exits.length?` <a class=sm data-go="stk" data-fsig="exit" data-sort="a5v" data-dir="1">看表格 →</a>`:''}<span class=st>近 5 日 3 家以上投信同時減碼、主動合計淨賣（億元）</span><div class=inl>`+
      (exits.length?exits.map(r=>`<span class=it><a data-c="${esc(r.c)}">${esc(r.n)}</a>${r.a5v!=null?`<span class=dn> ${f(r.a5v,1)}</span>`:''}</span>`).join('　'):'<span class=st>今日無</span>')+`</div></div>`+
    `<div class=rk2><b>跳空減碼提醒</b><span class=st>前一日「共識加碼」、今日開盤跳空 ≥3%：樣本內之後每個持有期平均都輸大盤</span><div class=inl>`+
      (al.length?al.map(a=>`<span class=it><a data-c="${esc(a.c)}">${esc(a.n)}</a> <span class=mu>開盤</span> ${sgn(a.gap,1,'%')}</span>`).join('　'):'<span class=st>今日無</span>')+`</div></div>`+hdRisk());
  const tw50=t50.ok?`<div class=lead style="margin-top:12px"><b>臺灣50 預測</b>：預估納入 ${(t50.adds||[]).length?(t50.adds||[]).map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a>`).join('、'):'無'}；預估刪除 ${(t50.dels||[]).length?(t50.dels||[]).map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a>`).join('、'):'無'}<span class=st>（排名基準 ${md(t50.asof)}${t50.frozen?'＝資料截止日，結果近乎確定':`，距資料截止 ${md(t50.cutoff)} 還有 ${t50.n_days} 個交易日`}）</span></div>`:'';
  const HL=((D.idx||{}).hd||{}).live||{},hdl=['tip_hd','tip_tech'].filter(k=>HL[k]&&!HL[k].err&&(HL[k].adds||[]).length)
    .map(k=>`${HDE[k]} ${HL[k].adds.slice(0,4).map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a>`).join('、')}${HL[k].adds.length>4?` 等 ${HL[k].adds.length} 檔`:''}<span class=st>（${HL[k].frozen?'資料截止日已過':'截止 '+md(HL[k].cutoff)}）</span>`);
  const hdLine=hdl.length?`<div class=lead style="margin-top:8px"><b>高股息預估納入</b>：${hdl.join('；')} <a data-go="idx" data-at="idx-hd">看全部 →</a></div>`:'';
  h+=sec('t-ev','事件','近期指數換股','被動 ETF 追蹤的指數定期換股，生效日被動資金集中買賣',
    (evs.length?`<div class=evs>${evs.map(e=>`<div class=ev><div class=cdn>${e.days}<small>天後</small></div><div class=evn>${esc(e.n)} <span class=mu style="font-weight:400">${esc(e.etf)}</span></div><div class=evm>${e.ann?`公告 ${md(e.ann)}・`:''}生效 ${md(e.eff)}${e.tr?`・分 ${e.tr} 日`:''}${e.stt==='推算'?'・日期推算':''}</div></div>`).join('')}</div>`:'<div class=st>尚無排定</div>')+tw50+hdLine,
    `<a data-go="idx">看指數 →</a>`);
  const cnt={};ROWS.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  h+=sec('t-sig','訊號','今日訊號','點一下看名單與歷史成績',
    `<div class=sgs>${Object.keys(SD).map(k=>`<a class="sgc${RISK.has(k)?' rk':''}${cnt[k]?'':' z'}" data-sg="${k}">${esc(SD[k][0])}<b>${cnt[k]||0}</b></a>`).join('')}</div>`,
    `<a data-go="sig">看訊號 →</a>`);
  $('#main').innerHTML=h;
  $$('#main [data-sg]').forEach(e=>e.onclick=()=>go('sig','sig-'+e.dataset.sg));
}

function hdRows2(){const HA=((D.idx||{}).hd||{}).alert||{},hb=HA.big_th||HDB;return {HA,hb,rs:(HA.rows||[]).filter(r=>r[6]!=null&&r[6]>=hb)};}
function hdRisk(){const {hb,rs}=hdRows2(),act=rs.filter(r=>r[10]==='in'||r[10]==='after'),pre=rs.filter(r=>r[10]==='pre');
  const nx=[...new Set(pre.map(r=>r[2]))].map(e=>{const xs=pre.filter(r=>r[2]===e);return `${esc(e)} ${md(xs[0][7])}～${md(xs[0][8])}（${esc(xs[0][11])}名單 ${xs.length} 檔）`;});
  return `<div class=rk2><b>高股息換股提醒</b>${gi('被動買賣提醒')}<span class=st>估計被動買賣 ≥${hb} 日量：納入股買盤結束後過去多半回落、刪除股賣完沒有反彈</span><div class=inl>`+
    (act.length?act.map(r=>`<span class=it><a data-c="${esc(r[0])}">${esc(r[1])}</a> <span class=mu>${esc(r[2])}・${r[4]==='add'?'被買':'被賣'}約 ${f(r[6],0)} 日量・${r[10]==='in'?`${r[4]==='add'?'買':'賣'}到 ${md(r[8])}`:`避開到 ${md(r[9])}`}</span></span>`).join('　'):
     nx.length?`<span class=st>目前沒有進行中的；下一次 ${nx.join('、')} <a data-go="st" data-at="st-hd">看名單 →</a></span>`:'<span class=st>今日無</span>')+`</div></div>`;}
function hdAlertCard(){const {HA,hb,rs}=hdRows2(),S=((D.idx||{}).hd||{}).flow||{},T={};(S.tests||[]).forEach(t=>T[t.k]=t);const aft=HA.after||10;
  const st=t=>t&&t.rev&&t.rev.n?`${t.rev.n} 次審核平均 ${pctT(t.rev.avg)}、${t.rev.pos} 次為正`:'—';
  const ev=`樣本內：估計 ≥${hb} 日量的納入股，被動買盤結束後 ${aft} 個交易日對大盤 ${st(T.post_big)}；對其他成分股 ${st(T.post_bigc)}。刪除股被賣完後 ${aft} 日 ${st(T.del10)}。追買（名單公開後買、最後一天賣）${st(T.ride5)}——所以只做提醒，給已持有的人參考，不做放空。`;
  const G=[...new Set(rs.map(r=>[r[2],r[3],r[11]].join('|')))];
  const lst=G.map(g=>{const [e,rv,src]=g.split('|'),xs=rs.filter(r=>r[2]===e&&r[3]===rv&&r[11]===src).sort((a,b)=>b[6]-a[6]),x0=xs[0];
    const ph={pre:`${md(x0[7])}～${md(x0[8])} 被動買賣`,in:`被動買賣中，最後一天 ${md(x0[8])}`,after:`已結束，避開到 ${md(x0[9])}`}[x0[10]]||'';
    const it=(sd,lb)=>{const ys=xs.filter(r=>r[4]===sd);return ys.length?`<div class=st style="margin-top:2px">${lb}：${ys.map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a><span class=mu>（${f(r[5],0)} 億・${f(r[6],0)} 日量）</span>`).join('、')}</div>`:'';};
    return `<div class=st style="margin-top:6px"><b>${esc(e)} ${esc(rv)}</b>（${esc(src)}名單・${ph}）</div>`+it('add','納入（買盤結束後避開 '+aft+' 日）')+it('del','刪除（賣完別急著撿）');}).join('');
  const fs=HA.fwd_stats||{};
  const fw=fs.n?`前瞻（${md(HA.since)} 起）：${fs.rev} 次審核、${fs.n} 檔，結束後 ${aft} 日對大盤平均 ${pctT(fs.avg)}、${fs.neg} 檔下跌。`:`前瞻紀錄從 ${md(HA.since)} 起算（第一次是 11～12 月的換股），滿 2 次審核再看。`;
  return `<div class=card id=st-hd><h4>${esc(HA.name||'高股息換股・被動買賣提醒')} <span class=pill>${rs.length}</span></h4><div class=st>${ev}</div>`+
    (lst||`<div class=st style="margin-top:4px">目前沒有估計 ≥${hb} 日量的換股股票</div>`)+
    `<div class=note>${fw} <a data-go="idx" data-at="idx-hdw">完整研究 →</a></div><details class=mr><summary>規則</summary><div class=rls>${ruleRows(HA.rule||[])}</div></details></div>`;}

/* ---------- 個股（篩選表：三個視角） ---------- */
const VW={etf:'ETF 動向',chip:'法人籌碼',ta:'技術面'},VW0={etf:'a5v',chip:'t5',ta:'rs20'};
const MKF2={twall:'台股（上市＋上櫃）',tw:'上市',tp:'上櫃',os:'海外',all:'全部市場'};
let AMX=1;const HASBD=ROWS.some(r=>r.bigd!=null);
function dbar(v){if(v==null||!AMX)return '';const w=Math.min(50,Math.abs(v)/AMX*50);return `<span class=db><i class=${v>0?'bu':'bd'} style="width:${w.toFixed(1)}%"></i></span>`;}
function streak(x){return !x?'<span class=mu>—</span>':x>0?`<span class=up>買 ${x}</span>`:`<span class=dn>賣 ${-x}</span>`;}
function tcd(r){return r.tc&&r.px?(r.px/r.tc-1)*100:null;}
function trend(r){const b=r.h60?'創 60 日高':r.h20?'創 20 日高':r.l20?'破 20 日低':'';
  return (r.al?`<span class=${r.al==='多頭'?'up':r.al==='空頭'?'dn':'mu'}>${r.al}</span>`:'—')+(b?`<br><span class="sg${r.l20&&!r.h20&&!r.h60?' rk':''}">${b}</span>`:'');}
function sigScore(r){const s=r.sg||[];return s.filter(k=>!RISK.has(k)).length-2*s.filter(k=>RISK.has(k)).length;}
function sgShort(arr){const s=(arr||[]).slice().sort((a,b)=>RISK.has(b)-RISK.has(a));return s.slice(0,2).map(k=>`<span class="sg${RISK.has(k)?' rk':''}">${esc((SD[k]||[k])[0])}</span>`).join('')+(s.length>2?`<span class=mu> +${s.length-2}</span>`:'');}
const C0=[
 {k:'c',t:'股票',l:1,v:r=>r.c,h:r=>`<span class=nm>${esc(r.n)}</span><span class=cd>${esc(r.c)}${r.m==='tp'?' · 櫃':r.m==='os'?' · 海外':''}${r.ind?' · '+esc(r.ind):''}</span>`},
 {k:'ch',t:'收盤',v:r=>r.ch,h:r=>`${fp(r.px)}<br>${sgn(r.ch,2,'%')}`},
];
const CV={
 etf:[
  {k:'a5v',t:'主動 5 日淨買',u:'億',g:'主動 5 日淨買',v:r=>r.a5v,h:r=>r.a5v==null?'<span class=mu>—</span>':`${sgn(r.a5v,1)}${dbar(r.a5v)}`},
  {k:'iac',t:'加／減家數',g:'加碼／減碼家數',v:r=>(r.ia5||[]).length-(r.ic5||[]).length,h:r=>`<span class=up>${(r.ia5||[]).length}</span><span class=mu>／</span><span class=dn>${(r.ic5||[]).length}</span>`},
  {k:'ne',t:'持有 ETF',u:'檔',g:'持有 ETF',v:r=>r.ne,h:r=>`${r.ne}<br><span class=mu>主動 ${r.na}</span>`},
  {k:'dev',t:'成本乖離',g:'成本乖離',v:r=>r.dev,h:r=>sgn(r.dev,1,'%')},
  {k:'ow',t:'超配',u:'pp',g:'超配',v:r=>r.ow,h:r=>sgn(r.ow,2)},
  {k:'hp',t:'ETF 持股率',g:'ETF 持股率',v:r=>r.hp,h:r=>r.hp==null?'<span class=mu>—</span>':f(r.hp,2)+'%'},
  {k:'sg',t:'訊號',l:1,v:sigScore,h:r=>sgShort(r.sg)},
 ],
 chip:[
  {k:'t5',t:'投信 5 日',u:'張',g:'投信 5 日',v:r=>r.t5,h:r=>sgn(r.t5,0)},
  {k:'ts',t:'投信連續',u:'日',g:'連買',v:r=>r.ts,h:r=>streak(r.ts)},
  {k:'f5',t:'外資 5 日',u:'張',g:'外資 5 日',v:r=>r.f5,h:r=>sgn(r.f5,0)},
  {k:'fs',t:'外資連續',u:'日',g:'連買',v:r=>r.fs,h:r=>streak(r.fs)},
  {k:'tcd',t:'現價 vs 投信成本',g:'60 日買超均價',v:tcd,h:r=>sgn(tcd(r),1,'%')},
  {k:'mb5',t:'融資 5 日',g:'融資',v:r=>r.mb5,h:r=>sgn(r.mb5,1,'%')},
  {k:'big',t:'千張大戶',g:'千張大戶',v:r=>HASBD?r.bigd:r.big,h:r=>r.big==null?'<span class=mu>—</span>':`${f(r.big,1)}%${r.bigd!=null?`<br>${sgn(r.bigd,2,'pp')}`:''}`},
 ],
 ta:[
  {k:'al',t:'趨勢',l:1,g:'趨勢',v:r=>({多頭:2,整理:1,空頭:0}[r.al]??-1)+(r.h60?.2:r.h20?.1:0),h:trend},
  {k:'b20',t:'20 日乖離',g:'乖離',v:r=>r.b20,h:r=>sgn(r.b20,1,'%')},
  {k:'vr',t:'量比',u:'倍',g:'量比',v:r=>r.vr,h:r=>r.vr==null?'<span class=mu>—</span>':f(r.vr,2)},
  {k:'rsi',t:'RSI',g:'RSI',v:r=>r.rsi,h:r=>r.rsi==null?'<span class=mu>—</span>':`<span class=${r.rsi>=70?'up':r.rsi<=30?'dn':''}>${f(r.rsi,0)}</span>`},
  {k:'p52',t:'一年位置',g:'一年區間位置',v:r=>r.p52,h:r=>r.p52==null?'<span class=mu>—</span>':f(r.p52,0)+'%'},
  {k:'rs20',t:'20 日相對大盤',u:'pp',g:'相對大盤',v:r=>r.rs20,h:r=>sgn(r.rs20,1)},
  {k:'liq',t:'日均成交',u:'億',g:'日均成交',v:r=>r.liq,h:r=>r.liq==null?'<span class=mu>—</span>':f(r.liq,1)},
 ]};
function cols(){return [...C0,...CV[S.vw]];}
function rowsFiltered(){
  const q=S.q.trim().toLowerCase();
  let rs=ROWS.filter(r=>(S.mk==='all'||r.m===S.mk||(S.mk==='twall'&&r.m!=='os'))&&(!S.sig||(S.sig==='nb'?(r.nb10||[]).length>0:(r.sg||[]).includes(S.sig)))&&(!S.liq||(r.liq||0)>=1)
    &&(!q||r.c.toLowerCase().includes(q)||String(r.n).toLowerCase().includes(q)||String(r.ind||'').includes(q)));
  const col=cols().find(c=>c.k===S.sort)||cols().find(c=>c.k===VW0[S.vw]);
  rs.sort((a,b)=>{const x=col.v(a),y=col.v(b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return (x<y?-1:x>y?1:0)*S.dir;});
  return rs;
}
function vStk(){
  if(!cols().some(c=>c.k===S.sort)){S.sort=VW0[S.vw];S.dir=-1;}
  const cnt={};ROWS.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  const nbN=ROWS.filter(r=>(r.nb10||[]).length&&r.m!=='os').length;
  $('#main').innerHTML=`<div class=fbar><input type=search id=q placeholder="搜尋代號、名稱或產業" value="${esc(S.q)}">`+
   `<select id=mk aria-label="市場">${Object.entries(MKF2).map(([m,t])=>`<option value=${m}${S.mk===m?' selected':''}>${t}</option>`).join('')}</select>`+
   `<select id=sgf aria-label="訊號"><option value="">全部訊號</option>${Object.keys(SD).filter(k=>cnt[k]).map(k=>`<option value=${k}${S.sig===k?' selected':''}>${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}（${cnt[k]}）</option>`).join('')}<option value=nb${S.sig==='nb'?' selected':''}>10 日內新建倉（台股 ${nbN}）</option></select>`+
   `</div><div class=vbar><span class=seg>${Object.entries(VW).map(([k,t])=>`<a data-vw=${k} class="${S.vw===k?'on':''}">${t}</a>`).join('')}</span>`+
   `<label class=tgl title="20 日平均成交金額 ≥ 1 億元"><input type=checkbox id=liq${S.liq?' checked':''}>成交 ≥1 億</label><span class=cnt id=cnt></span></div><div id=stkt></div>`;
  $('#q').oninput=e=>{S.q=e.target.value;S.n=60;drawStk();};
  $('#mk').onchange=e=>{S.mk=e.target.value;S.n=60;save();drawStk();};
  $('#sgf').onchange=e=>{S.sig=e.target.value;S.n=60;drawStk();};
  $('#liq').onchange=e=>{S.liq=e.target.checked;S.n=60;save();drawStk();};
  $$('[data-vw]').forEach(a=>a.onclick=()=>{S.vw=a.dataset.vw;if(!cols().some(c=>c.k===S.sort)){S.sort=VW0[S.vw];S.dir=-1;}
    $$('[data-vw]').forEach(x=>x.classList.toggle('on',x===a));save();drawStk();});
  drawStk();
}
function drawStk(){
  const rs=rowsFiltered(),cs=cols();STK=rs.map(r=>r.c);
  AMX=Math.max(1,...rs.map(r=>Math.abs(r.a5v||0)));
  $('#cnt').textContent=`共 ${rs.length} 檔`;
  $('#stkt').innerHTML=(S.mk==='os'&&S.vw!=='etf'?'<div class=note>海外持股只有 ETF 面資料，法人籌碼與技術面無官方資料。</div>':'')+
   `<div class="tw stk"><table><thead><tr>`+cs.map(c=>`<th data-k=${c.k} class="${S.sort===c.k?'on':''}${c.l?' l':''}">${c.t}${c.u?`<small>${c.u}</small>`:''}${c.g?gi(c.g):''}${S.sort===c.k?(S.dir<0?' ↓':' ↑'):''}</th>`).join('')+`</tr></thead><tbody>`+
   (rs.slice(0,S.n).map(r=>`<tr data-c="${esc(r.c)}">`+cs.map(c=>`<td${c.l?' class=l':''}>${c.h(r)}</td>`).join('')+`</tr>`).join('')||`<tr><td colspan=${cs.length} class=l><span class=st>沒有符合條件的股票</span></td></tr>`)+`</tbody></table></div>`+
   (rs.length>S.n?`<button class=more id=more>再顯示 ${Math.min(60,rs.length-S.n)} 檔（剩 ${rs.length-S.n}）</button>`:'');
  $$('#stkt th[data-k]').forEach(e=>e.onclick=()=>{if(S.sort===e.dataset.k)S.dir*=-1;else{S.sort=e.dataset.k;S.dir=e.dataset.k==='c'?1:-1;}save();drawStk();});
  const m=$('#more');if(m)m.onclick=()=>{S.n+=60;drawStk();};
}

/* ---------- 訊號 ---------- */
function statLine(k){const st=(D.stats||{})[k];if(!st)return '<span class=st>尚無歷史樣本</span>';
  const a=st['5']||{},b=st['20']||{};if(!a.n)return '<span class=st>尚無歷史樣本</span>';
  return `<span class=st>${st.ok?'':'⚠ 樣本不足 · '}5 日：平均超額 ${sgn(a.x,2,'%')}、勝率 ${f(a.w,0)}%、隔夜跳空 ${sgn(a.g,2,'%')}（${a.n} 次）`+(b.n?` · 20 日：超額 ${sgn(b.x,2,'%')}、勝率 ${f(b.w,0)}%（${b.n} 次）`:'')+`</span>`;}
function readSig(st){const a=st['5']||{},b=st['20']||{};if(!a.n)return '<span class=mu>尚無樣本</span>';
  const p=[];p.push(`5 日${a.x<0?'輸':'贏'}大盤`);if(b.n)p.push(`20 日${b.x<0?'輸':'贏'}大盤`);
  return (st.ok?'':'<span class="tg">樣本不足</span>')+`<span class=${a.x<0&&(!b.n||b.x<0)?'mu':''}>${p.join('、')}</span>`;}
function sigBadges(k){const st=(D.stats||{})[k]||{};const a=st['5']||{},b=st['20']||{};if(!a.n)return '<div class=bdg><span class=mu>尚無歷史樣本</span></div>';
  return `<div class=bdg>${st.ok?'':'<span class=tg>樣本不足</span>'}<span>5 日超額 <b>${sgn(a.x,2,'%')}</b></span><span>勝率 <b>${f(a.w,0)}%</b></span><span>隔夜跳空 <b>${sgn(a.g,2,'%')}</b></span>${b.n?`<span>20 日超額 <b>${sgn(b.x,2,'%')}</b></span>`:''}<span class=mu>歷史 ${a.n} 次</span></div>`;}
function sigRow(r){const ia=r.ia5||[],ic=r.ic5||[];return `<tr data-c="${esc(r.c)}"><td><span class=nm>${esc(r.n)}</span><span class=cd>${esc(r.c)}${r.m==='tp'?' · 櫃':r.m==='os'?' · 海外':''}</span></td><td>${fp(r.px)}<br>${sgn(r.ch,2,'%')}</td><td>${r.a5v!=null?sgn(r.a5v,1)+'<span class=mu> 億</span>':sgn(r.a5,0)+'<span class=mu> 股</span>'}</td>`+
  `<td class="l wr">${ia.length?`<span class=up>加</span> ${esc(nameList(ia,2))}`:''}${ic.length?`${ia.length?'<br>':''}<span class=dn>減</span> ${esc(nameList(ic,2))}`:''}</td><td>${sgn(r.dev,1,'%')}</td><td>${sgn(r.t5,0)}</td></tr>`;}
function vSig(){
  const ks=Object.keys(SD),cnt={};ROWS.forEach(r=>(r.sg||[]).forEach(k=>cnt[k]=(cnt[k]||0)+1));
  const neg=ks.filter(k=>(((D.stats||{})[k]||{})['5']||{}).x<0).length;
  let h=`<div class=intro>訊號＝系統每天收盤後自動標記的現象（例如 3 家以上投信同時加碼）。歷史成績的算法：訊號隔日開盤進場、扣來回成本、和加權指數比。<b>目前 ${ks.length} 種訊號中有 ${neg} 種「隔日開盤跟進、持有 5 日」平均輸大盤</b>——把它們當觀察線索、不是買點；加上條件的版本在「策略」頁驗證。</div>`;
  h+=sec('sig-all','總覽','訊號總覽',`樣本期 ${md((D.asof||{}).start)} 起・同一檔 5 日內重複只算一次`,
    `<div class=tw><table><thead><tr><th>訊號</th><th>今日</th><th>5 日平均超額${gi('超額')}</th><th>勝率${gi('勝率')}</th><th>隔夜跳空${gi('隔夜跳空')}</th><th>樣本${gi('樣本')}</th><th>20 日平均超額</th><th>勝率</th><th>樣本</th><th class=l>判讀</th></tr></thead><tbody>`+
    ks.map(k=>{const st=(D.stats||{})[k]||{};const x=st['5']||{},y=st['20']||{};
      return `<tr class="${st.ok?'':'grey'}"><td><a data-to="sig-${k}">${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}</a>${gi(k)}</td><td><b>${cnt[k]||0}</b></td><td>${sgn(x.x,2,'%')}</td><td>${x.n?f(x.w,0)+'%':'—'}</td><td>${sgn(x.g,2,'%')}</td><td>${x.n||0}</td><td>${sgn(y.x,2,'%')}</td><td>${y.n?f(y.w,0)+'%':'—'}</td><td>${y.n||0}</td><td class=l>${readSig(st)}</td></tr>`;}).join('')+
    `</tbody></table></div><div class=note>灰字＝樣本不足 30 次，不宜採信。</div>`);
  const head=`<thead><tr><th>股票</th><th>收盤</th><th>主動 5 日${gi('主動 5 日淨買')}</th><th class=l>投信（5 日）${gi('加碼／減碼家數')}</th><th>成本乖離${gi('成本乖離')}</th><th>投信 5 日${gi('投信 5 日')}</th></tr></thead>`;
  for(const k of ks){
    const risk=RISK.has(k);const rs=ROWS.filter(r=>(r.sg||[]).includes(k));
    rs.sort((a,b)=>((a.m==='os')-(b.m==='os'))||(risk?(a.a5v??a.a5??0)-(b.a5v??b.a5??0):(b.a5v??b.a5??0)-(a.a5v??a.a5??0)));
    h+=sec('sig-'+k,SD[k][0],`${risk?'⚠ ':''}${esc(SD[k][0])} <span class=pill>${rs.length} 檔</span>`,esc(SD[k][1]),
      sigBadges(k)+(rs.length?`<div class=tw><table>${head}<tbody>${rs.slice(0,8).map(sigRow).join('')}</tbody></table></div>`:'<div class=st>今日無</div>'),
      rs.length>8?`<a data-go="stk" data-fsig="${k}" data-sort="a5v"${risk?' data-dir="1"':''}>全部 ${rs.length} 檔 →</a>`:'');
  }
  $('#main').innerHTML=h;
  $$('#main [data-to]').forEach(a=>a.onclick=()=>jump(a.dataset.to));
}

/* ---------- 投信 ---------- */
const ISTW=c=>/^\d{4,6}[A-Z]?$/.test(c);
function aggEv(ev){const g={new:new Map(),add:new Map(),cut:new Map(),exit:new Map()};
  for(const e of ev){const m=g[e[1]];if(!m)continue;const o=m.get(e[2])||{c:e[2],n:e[3],l:0};o.l+=e[5]||0;m.set(e[2],o);}
  const out={};for(const k in g)out[k]=[...g[k].values()].sort((a,b)=>(ISTW(b.c)-ISTW(a.c))||Math.abs(b.l)-Math.abs(a.l));return out;}
function evItems(items,max=8){const one=(o,i)=>{const t=esc(ISTW(o.c)?o.n:o.c);return `<span class="it eit${i>=max?' xh':''}">${BY[o.c]?`<a data-c="${esc(o.c)}">${t}</a>`:t}${ISTW(o.c)?` <span class=mu>${pm(o.l,0)}</span>`:''}</span>`;};
  return `<span class=evl>${items.map(one).join('')}${items.length>max?`<a class=xm>＋其餘 ${items.length-max} 檔</a>`:''}</span>`;}
function vIss(){
  const iss={};for(const [c,m] of Object.entries(E)){(iss[m.is]=iss[m.is]||[]).push([c,m]);}
  const act=nm=>(iss[nm]||[]).filter(([c,m])=>m.k==='a');
  const names=Object.keys(iss).filter(nm=>act(nm).length).sort((a,b)=>((D.iev||{})[b]||[]).length-((D.iev||{})[a]||[]).length);
  const d5=(D.dates||[]).slice(-5);const win=d5.length?`${md(d5[0])}～${md(d5[d5.length-1])}`:'';
  const G={};names.forEach(nm=>G[nm]=aggEv((D.iev||{})[nm]||[]));
  const cnts=nm=>{const g=G[nm];if(!g)return '<span class=mu>—</span>';const p=[['new','新'],['add','加'],['cut','減'],['exit','清']].filter(([k])=>g[k].length).map(([k,l])=>`<span class=k-${k}>${l} ${g[k].length}</span>`);return p.length?p.join(' '):'<span class=mu>無</span>';};
  let h=`<div class=intro>每家投信旗下主動 ETF 近 5 個交易日（${win}）的真加減碼${gi('真加碼')}，依股票彙整，數字是張數；「超配最多」是相對台股市值權重最看好的個股${gi('超配')}。總覽是各家「新建倉後」的歷史表現。</div>`;
  const ist=Object.entries(D.iss||{}).sort((a,b)=>((b[1]['20']||{}).x??-99)-((a[1]['20']||{}).x??-99));
  h+=sec('iss-all','總覽','投信總覽','近 5 日動作＝新建倉／加碼／減碼／出清的股票檔數；選股成績＝主動 ETF 新建倉後的表現（對加權指數）',
    `<div class=tw><table><thead><tr><th>投信</th><th>主動 ETF</th><th class=l>近 5 日動作</th><th>新建倉次數</th><th>5 日超額${gi('超額')}</th><th>20 日超額</th><th>勝率${gi('勝率')}</th><th>樣本${gi('樣本')}</th><th>先買／跟進</th></tr></thead><tbody>`+
    ist.map(([nm,st])=>{const x=st['5']||{},y=st['20']||{};return `<tr class="${(y.n||0)>=30?'':'grey'}"><td>${G[nm]?`<a data-to="iss-${esc(nm)}">${esc(nm)}</a>`:esc(nm)}</td><td>${act(nm).length}</td><td class=l>${cnts(nm)}</td><td>${st.new||0}</td><td>${sgn(x.x,2,'%')}</td><td>${sgn(y.x,2,'%')}</td><td>${y.n?f(y.w,0)+'%':'—'}</td><td>${y.n||0}</td><td>${st.lead||0}／${st.follow||0}</td></tr>`;}).join('')+
    `</tbody></table></div><div class=note>先買＝同一檔股票由這家最先建倉的次數；跟進＝別家先建倉、這家後來才買的次數。灰字＝20 日樣本不足 30 次。</div>`);
  for(const nm of names){
    const ev=(D.iev||{})[nm]||[];const ow=(D.iow||{})[nm]||[];const st=(D.iss||{})[nm]||{};const s20=st['20']||{};const g=G[nm];
    let b=`<div class=ish>${(iss[nm]||[]).map(([c,m])=>`<span class="tg${m.k==='a'?'':' mu'}">${esc(c)}${m.k==='p'?'・被動':''}</span>`).join('')}</div>`;
    for(const [k,l] of [['new','新建倉'],['add','加碼'],['cut','減碼'],['exit','出清']])if(g[k].length)b+=`<div class=isr><span class="isk k-${k}">${l}<i>${g[k].length} 檔</i></span><div class=inl>${evItems(g[k])}</div></div>`;
    if(!ev.length)b+='<div class=isr><span class=isk>近 5 日</span><div class=st>沒有主動真加減碼</div></div>';
    if(ow.length)b+=`<div class=isr><span class=isk>超配最多</span><div class=inl>${ow.slice(0,6).map(o=>`<span class=it><a data-c="${esc(o[0])}">${esc(o[1])}</a> <span class=mu>${pm(o[4],2)}pp</span></span>`).join('　')}</div></div>`;
    const stt=s20.n?`新建倉後 20 日：超額 ${sgn(s20.x,2,'%')}、勝率 ${f(s20.w,0)}%（${s20.n} 次${s20.n<30?'，樣本不足':''}）`:'新建倉後 20 日：尚無樣本';
    h+=sec('iss-'+nm,nm,esc(nm),stt,`<div class="card isc">${b}</div>`);
  }
  $('#main').innerHTML=h;
  $$('#main [data-to]').forEach(a=>a.onclick=()=>jump(a.dataset.to));
  $$('#main .xm').forEach(a=>a.onclick=()=>{a.parentNode.classList.add('open');a.remove();});
}

/* ---------- 指數調整 ---------- */
function nmOf(c){const r=BY[c];return r?r.n:(((D.idx||{}).names||{})[c]||c);}
function idxTbl(title,rows,side){
  if(!rows||!rows.length)return '';
  return `<h4 class=sh>${esc(title)}</h4><div class=tw><table><thead><tr><th>股票</th><th>市值排名</th><th>市值(億)</th><th>${side==='add'?'距第 40 名':'距跌出 60 名'}</th><th>機率</th><th>40 日漲幅</th><th>被動${side==='add'?'買進':'賣出'}(張)${gi('被動買盤')}</th><th>約幾日量</th><th>收盤</th></tr></thead><tbody>`+
   rows.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}${r[11]?' · <b class=up>漲勢前一半</b>':''}${r[10]?` · ${md(r[10])} 上市`:''}</span></td><td>${r[2]??'—'}</td><td>${f(r[3],0)}</td><td>${r[4]==null?'—':(r[4]===0?'已跨線':sgn(r[4],1,'%'))}</td><td>${r[5]==null?'—':r[5]+'%'}</td><td>${r[9]==null?'—':sgn(r[9],1,'%')}</td><td>${sgn(r[6],0)}</td><td>${r[7]==null?'—':f(r[7],1)}</td><td>${fp(r[8])}</td></tr>`).join('')+`</tbody></table></div>`;}
/* 臺灣50 換股研究（預測準度、進場時點、歸因；數字由 tw50study 每次建表重算） */
function crb(v){return v==null?'—':`<span class=crb><i style="${v>=0?'left':'right'}:50%;width:${(Math.min(1,Math.abs(v))*50).toFixed(0)}%"></i></span>${v>0?'+':v<0?'−':''}${f(Math.abs(v),2)}`;}
function stScatter(S){const R=(S.rows||[]).filter(r=>r[5]!=null&&r[12]!=null);if(R.length<4)return '';
  const W=stW(),H=W<500?260:220,pl=42,pr=12,pt=12,pb=26,xs=R.map(r=>r[5]),ys=R.map(r=>r[12]);
  const x1=Math.max(...xs)*1.08,x0=Math.min(0,...xs),ya=Math.max(5,...ys.map(Math.abs))*1.12;
  const X=v=>pl+(v-x0)/(x1-x0)*(W-pl-pr),Y=v=>pt+(H-pt-pb)/2*(1-v/ya),st=x1>120?50:25;
  let s=`<line x1=${pl} x2=${W-pr} y1=${Y(0).toFixed(1)} y2=${Y(0).toFixed(1)} stroke="#c9d0da"/>`;
  for(const v of [ya,-ya])s+=`<text x=${pl-5} y=${(Y(v)+4).toFixed(0)} font-size=11 fill="#727e8c" text-anchor=end>${v>0?'+':'−'}${f(Math.abs(v),0)}%</text>`;
  for(let v=0;v<=x1;v+=st)s+=`<text x=${X(v).toFixed(1)} y=${H-8} font-size=11 fill="#727e8c" text-anchor=middle>${v}%</text>`;
  // 標籤避讓：依序試右／左／上／下，挑第一個不壓到其他點與已放標籤的位置
  const P=R.map(r=>({r,x:X(r[5]),y:Y(r[12])})),occ=P.map(q=>({x0:q.x-5,y0:q.y-5,x1:q.x+5,y1:q.y+5}));
  const tw=t=>[...t].reduce((a,ch)=>a+(ch.charCodeAt(0)>255?10.5:6),0),ov=(b,c)=>!(b.x1<c.x0||b.x0>c.x1||b.y1<c.y0||b.y0>c.y1);
  for(const q of P.slice().sort((a,b)=>a.x-b.x)){const w=tw(q.r[2]);
    const opts=[[q.x+7,q.y+4,'start',q.x+7,q.x+7+w],[q.x-7,q.y+4,'end',q.x-7-w,q.x-7],[q.x,q.y-8,'middle',q.x-w/2,q.x+w/2],[q.x,q.y+16,'middle',q.x-w/2,q.x+w/2]];
    let pick=null;for(const o of opts){const b={x0:o[3],x1:o[4],y0:o[1]-9,y1:o[1]+2};
      if(b.x0<pl||b.x1>W-2||b.y0<0||b.y1>H-pb)continue;if(!occ.some(c=>ov(b,c)&&!(c.x0===q.x-5&&c.y0===q.y-5))){pick=o;break;}}
    if(pick)occ.push({x0:pick[3],x1:pick[4],y0:pick[1]-9,y1:pick[1]+2});q.l=pick;}
  for(const q of P.slice().sort((a,b)=>a.r[9]-b.r[9])){const r=q.r;
    s+=`<circle cx=${q.x.toFixed(1)} cy=${q.y.toFixed(1)} r=4.5 fill="${r[9]?'#d33a34':'#9aa5b4'}"><title>${esc(r[0])} ${esc(r[2])}：40 日 ${f(r[5],1)}%、公告後超額 ${f(r[12],1)}%</title></circle>`+
      (q.l?`<text x=${q.l[0].toFixed(1)} y=${q.l[1].toFixed(1)} font-size=10.5 fill="#44505f" text-anchor=${q.l[2]}>${esc(r[2])}</text>`:'');}
  return `<svg width=${W} height=${H} viewBox="0 0 ${W} ${H}" style="max-width:${W}px">${s}</svg><div class=lg><span><i style="background:#d33a34"></i>漲勢前一半</span><span><i style="background:#9aa5b4"></i>後一半</span><span>橫軸＝截止前 40 日漲幅；縱軸＝公告後進場、生效前一天賣的超額</span></div>`;}
/* 提前幾天建倉：柱＝每次平均報酬、點＝最差的一次；藍底＝採用的天數（右邊＝截止日當天） */
function earlyChart(E){const K=E.k||[];if(!K.length)return '';const vals=[...E.avg,...E.lo].filter(v=>v!=null);if(!vals.length)return '';
  const W=stW(),HH=170,pl=40,pr=8,pt=12,pb=22,n=K.length,mx=Math.max(5,...vals.map(Math.abs));
  const y=v=>pt+(HH-pt-pb)/2*(1-v/mx),z=y(0),cw=(W-pl-pr)/n,bw=Math.max(2,Math.min(12,cw*.68));
  let s='';const pi=K.indexOf(E.pick);
  if(pi>=0)s+=`<rect x=${(pl+pi*cw).toFixed(1)} y=${pt-8} width=${cw.toFixed(1)} height=${HH-pt-pb+14} fill="#e8effb" rx=3 />`;
  s+=`<line x1=${pl} x2=${W-pr} y1=${z.toFixed(1)} y2=${z.toFixed(1)} stroke="#c9d0da"/>`;
  for(const t of [mx,-mx])s+=`<text x=${pl-5} y=${(y(t)+4).toFixed(0)} font-size=11 fill="#727e8c" text-anchor=end>${t>0?'+':'−'}${f(Math.abs(t),0)}%</text>`;
  K.forEach((k,i)=>{const cx=pl+(i+.5)*cw,v=E.avg[i],lo=E.lo[i];
    if(v!=null)s+=`<rect x=${(cx-bw/2).toFixed(1)} y=${Math.min(y(v),z).toFixed(1)} width=${bw.toFixed(1)} height=${Math.max(1,Math.abs(y(v)-z)).toFixed(1)} fill="${v>=0?'#d33a34':'#1f9d57'}"><title>提前 ${k} 日：每次平均 ${pctT(v)}、${E.n[i]} 次賺 ${E.win[i]} 次、最差 ${pctT(lo)}</title></rect>`;
    if(lo!=null)s+=`<circle cx=${cx.toFixed(1)} cy=${y(lo).toFixed(1)} r=2.4 fill="#44505f"/>`;
    if(k%5===0||k===E.pick)s+=`<text x=${cx.toFixed(1)} y=${HH-5} font-size=11 fill="${k===E.pick?'#1c4fa8':'#727e8c'}" font-weight="${k===E.pick?700:400}" text-anchor=middle>${k}</text>`;});
  return `<svg width=${W} height=${HH} viewBox="0 0 ${W} ${HH}" style="max-width:${W}px">${s}</svg><div class=lg><span><i style="background:#d33a34"></i>每次平均報酬（扣成本）</span><span><i style="background:#44505f;width:6px;height:6px;border-radius:50%"></i>最差的一次</span><span>橫軸＝截止前幾個交易日建倉（最右＝截止日當天）；藍底＝採用 ${E.pick} 日</span></div>`;}
function studySec(S){
  if(!S||!S.n)return S&&S.err?sec('idx-study','換股研究','臺灣50 換股研究','',`<div class=st>研究區塊錯誤：${esc(S.err)}</div>`):'';
  const A=k=>(S.acc||[]).find(a=>a.k===k),E=k=>(S.entry||[]).find(e=>e.key===k)||{},F=k=>(S.fac||[]).find(x=>x.k===k)||{},W=S.within||[];
  const a0=A(0),a20=A(20),pre=E('pre'),post=E('post'),L=[];
  if(a0)L.push(`<b>名單：</b>資料截止日${gi('資料截止日')}收盤後照規則重算，${a0.hit}／${a0.tot} 檔${a0.hit===a0.tot?'全對':'命中'}${a0.fp?`、多猜 ${a0.fp} 檔`:'、沒有多猜'}${a20?`；提前 20 個交易日只對 ${a20.hit} 檔`:''}。`);
  if(pre.all&&pre.all.n&&post.all&&post.all.n)L.push(`<b>時點：</b>截止日到公告這兩週，納入股平均 ${pctT(pre.all.avg)}（${pre.all.win}% 上漲）；公告後才進場、生效前一天賣，平均 ${pctT(post.all.avg)}（${post.all.win}% 賺）。`);
  if(W.length)L.push(`<b>選股：</b>同一次審核裡漲最多的，${W.filter(w=>w.same).length}／${W.length} 次是截止前漲勢最強的那檔，權重${gi('估計權重')}最大的只有 ${W.filter(w=>w.heavy_same).length}／${W.length} 次；權重和漲幅的相關只有 ${f(F('w').rho,2)}——新進的股票都剛擠進前 40 名，權重本來就差不多。`);
  let b=`<div class=lead><ul>${L.map(x=>`<li>${x}</li>`).join('')}</ul></div>`;
  b+=`<h4 class=sh>名單什麼時候就準了</h4><div class=tw><table><thead><tr><th>用哪天的排名</th><th>命中</th><th>多猜</th></tr></thead><tbody>`+
    (S.acc||[]).map(a=>`<tr><td>${a.k?`截止前 ${a.k} 個交易日`:'資料截止日當天'}</td><td>${a.hit}／${a.tot}</td><td>${a.fp}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>命中＝官方納入股有被預估到；多猜＝預估納入、官方沒納入。截止前的排名之後還會變，越早越不準。</div>`;
  const cell=g=>g&&g.n?`<td><b>${sgn(g.avg,1,'%')}</b><div class=sm2>中位 ${pctT(g.med)}・${g.win}% 賺</div></td>`:'<td>—</td>';
  b+=`<h4 class=sh>什麼時候買、什麼時候賣</h4><div class=tw><table><thead><tr><th>買 → 賣</th><th>全部納入股<br><span class=mu>平均</span></th><th>漲勢前一半${gi('漲勢前一半')}<br><span class=mu>平均</span></th></tr></thead><tbody>`+
    (S.entry||[]).map(e=>`<tr><td class=wr>${esc(e.lbl)}${e.tag?`<br><span class=pill>${esc(e.tag)}</span>`:''}</td>${cell(e.all)}${cell(e.top)}</tr>`).join('')+
    `</tbody></table></div><div class=note>報酬已扣來回成本 0.585%；開盤進場用當天開盤價、收盤賣用收盤價。全部 ${S.n} 筆、漲勢前一半 ${(post.top||{}).n||0} 筆。</div>`;
  const EA=S.early||{},e1=eAt(EA,EA.pick),e0=eAt(EA,0);
  if(e1&&e0)b+=`<h4 class=sh>提前幾天建倉？</h4><div class=st>同一套規則（候選＝預估納入＋第 41～45 名、挑 40 日漲最多的 ${EA.N} 檔、截止日名單沒有的隔天賣、有但沒買到的補進、生效前一天全賣），只改建倉日：`+
    `提前 ${EA.pick} 日每次平均 <b>${pctT(e1.avg)}</b>、${e1.n} 次賺 ${e1.win} 次、最差一次 ${pctT(e1.lo)}；截止日當天才買每次平均 ${pctT(e0.avg)}、最差一次 ${pctT(e0.lo)}。</div>${earlyChart(EA)}`+
    `<div class=note>只算建倉日在上一次審核生效之後的（更早會和上一次審核重疊）。柱子高低會跟著哪幾檔剛好被選到而跳動，看一段區間的整體高低，不要看單一天。</div>`;
  b+=`<h4 class=sh>哪些納入股漲最多</h4><div class=st>各項數字和「公告後進場、生效前一天賣」超額報酬的等級相關${gi('等級相關')}（${S.n} 檔）：</div><div class=tw><table><thead><tr><th>數字</th><th class=l>和公告後表現</th><th class=l>和卡位表現</th></tr></thead><tbody>`+
    (S.fac||[]).map(x=>`<tr><td>${esc(x.lbl)}</td><td class=l>${crb(x.rho)}</td><td class=l>${crb(x.rho_cut)}</td></tr>`).join('')+`</tbody></table></div>`;
  b+=stScatter(S);
  const wc=(nm,x,ok)=>`<td class=l>${esc(nm||'—')}${ok?' <b class=up>✓</b>':''}<div class=sm2>${x==null?'—':pctT(x)}</div></td>`;
  if(W.length)b+=`<div class=tw style="margin-top:8px"><table><thead><tr><th>審核</th><th class=l>漲最多的</th><th class=l>截止前漲勢最強</th><th class=l>權重最大</th></tr></thead><tbody>`+
    W.map(w=>`<tr><td>${esc(w.review)}<div class=sm2>${w.n} 檔納入</div></td>${wc(w.best,w.best_x,false)}${wc(w.strongest,w.strongest_x,w.same)}${wc(w.heavy,w.heavy_x,w.heavy_same)}</tr>`).join('')+
    `</tbody></table></div><div class=note>只列有 2 檔以上納入的審核；✓＝就是漲最多的那檔。小字＝公告後第一個交易日開盤買、生效前一天收盤賣的超額（減去同期加權指數）。權重＝市值 ÷ 前 50 大市值（未做自由流通調整）。</div>`;
  const R=(S.rows||[]).slice().reverse();
  b+=`<details class=mr><summary>逐次明細（${R.length} 檔）</summary><div class=tw><table><thead><tr><th>股票</th><th>審核</th><th>估計權重</th><th>40 日漲幅</th><th>週轉率${gi('週轉率')}</th><th>被動買盤(張)</th><th>約幾日量</th><th>卡位</th><th>公告後</th><th>生效後 5 日</th></tr></thead><tbody>`+
    R.map(r=>`<tr data-c="${esc(r[1])}"><td><span class=nm>${esc(r[2])}</span><span class=cd>${esc(r[1])}${r[9]?' · <b class=up>前一半</b>':''}</span></td><td>${esc(r[0])}</td><td>${r[4]==null?'—':f(r[4],2)+'%'}</td><td>${r[5]==null?'—':sgn(r[5],1,'%')}</td><td>${r[6]==null?'—':f(r[6],2)+'%'}</td><td>${r[7]==null?'—':f(r[7],0)}</td><td>${r[8]==null?'—':f(r[8],2)}</td><td>${sgn(r[13],1,'%')}</td><td>${sgn(r[11],1,'%')}</td><td>${sgn(r[15],1,'%')}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>報酬扣成本。卡位＝截止日隔天開盤買、生效前一天收盤賣；公告後＝公告後第一個交易日開盤買、生效前一天收盤賣；生效後 5 日＝生效日收盤到 5 個交易日後收盤。個股生效日延後時以個股為準。被動買盤為估計（0050＋006208 規模 ÷ 前 50 大市值 × 發行股數，未做自由流通調整）。</div></details>`;
  return sec('idx-study','換股研究','臺灣50 換股研究',`過去 ${S.n_rev} 次審核（${esc(S.first)}～${esc(S.last)}）、${S.n} 檔納入股`,b);}
/* 高股息四檔（0056／00878／00919／00929）：下一次預估名單＋換股研究（數字由 hdpredict／hdstudy 每次建表重算） */
const HDK=['tip_hd','tip_tech','tw_div','msci_esg30'],HDP=['tip_hd','tip_tech'],HDB=5;
const HDN={tw_div:'0056 臺灣高股息',msci_esg30:'00878 MSCI ESG 高息30',tip_hd:'00919 精選高息',tip_tech:'00929 科技優息'};
const HDE={tw_div:'0056',msci_esg30:'00878',tip_hd:'00919',tip_tech:'00929'};
const HDNOTE={tip_hd:'規則公開，照規則重算（股利、EPS 用公開資料近似）',tip_tech:'規則公開，照規則重算（流動性門檻、本益比差距指標未公開，略過）',
  tw_div:'官方用分析師預估股利（付費資料）排名，這裡用「近四季 EPS × 去年配發率」近似，名單準度低',msci_esg30:'ESG 評級是付費資料、母體不公開，這裡只排股利分數，名單準度低'};
function hdAcc(a){const x=(a||{})[0];if(!x||!x.tot)return '';
  return `過去 ${x.n_rev} 次用資料截止日重算：官方納入 ${x.tot} 檔中 ${x.hit} 檔、多猜 ${x.fp} 檔；官方刪除 ${x.tot_del} 檔中 ${x.hit_del} 檔。`;}
function hdRows(rows,side){if(!rows||!rows.length)return `<div class=st>${side==='add'?'預估納入：無':'預估刪除：無'}</div>`;
  return `<h4 class=sh>${side==='add'?'預估納入':'預估刪除'}</h4><div class=tw><table><thead><tr><th>股票</th><th>殖利率名次</th><th>殖利率</th><th>40 日漲幅</th><th>估計被動${side==='add'?'買進':'賣出'}(億)${gi('被動買賣期間')}</th><th>約幾日量</th><th>收盤</th></tr></thead><tbody>`+
   rows.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}</span></td><td>${r[2]??'<span class=mu>不合格</span>'}</td><td>${r[3]==null?'—':f(r[3],2)+'%'}</td><td>${r[4]==null?'—':sgn(r[4],1,'%')}</td><td>${r[5]==null?'—':f(r[5],1)}</td><td>${r[6]==null?'—':f(r[6],1)}${r[6]!=null&&r[6]>=HDB?' <span class="sg rk">提醒</span>':''}</td><td>${fp(r[7])}</td></tr>`).join('')+`</tbody></table></div>`;}
function hdPredSec(H){const L=(H||{}).live||{};let b='';
  for(const k of HDK){const v=L[k];if(!v)continue;
    if(v.err){b+=`<div class=card><h4>${esc(HDN[k])}</h4><div class=st>預測錯誤：${esc(v.err)}</div></div>`;continue;}
    const tl=[v.cutoff?`資料截止 ${md(v.cutoff)}${k==='msci_esg30'?'（估計）':''}`:'',v.announce?`${k==='msci_esg30'?'MSCI 公布':'公告'} ${md(v.announce)}`:'',
      v.reveal?`名單約 ${md(v.reveal)} 起從持股揭露看得到`:'',v.trade&&v.trade[0]?`被動買賣約 ${md(v.trade[0])}～${md(v.trade[1])}`:''].filter(Boolean).join('・');
    if(v.nopred){b+=`<div class=card><h4>${esc(HDN[k])} <span class=pill>${esc(v.review||'')}</span>${v.status==='推算'?' <span class=mu style="font-weight:400">日期推算</span>':''}</h4>`+
      `<div class=st>${tl}</div><div class=st>規模 ${f(v.aum,0)} 億・審核前 ${v.n_pre} 檔</div><div class=st><b>不做公告前預測</b>：${esc(v.nopred)}。</div>`+
      (hdAcc(v.acc)?`<div class=note>試算過的近似方法：${hdAcc(v.acc)}</div>`:'')+`</div>`;continue;}
    b+=`<div class=card><h4>${esc(HDN[k])} <span class=pill>${esc(v.review||'')}</span>${v.status==='推算'?' <span class=mu style="font-weight:400">日期推算</span>':''}</h4>`+
      `<div class=st>${tl}</div><div class=st>排名基準 ${md(v.asof)}${v.frozen?'（＝資料截止日，名單已定）':'（資料截止前每天重算）'}・規模 ${f(v.aum,0)} 億・審核前 ${v.n_pre} 檔${v.max_chg?`・最多換 ${v.max_chg} 檔`:''}</div>`+
      `<div class=st>${esc(HDNOTE[k])}</div>`+hdRows(v.adds,'add')+
      (v.max_chg&&(v.adds||[]).length>v.max_chg?`<div class=note>預估納入 ${v.adds.length} 檔，超過一次最多換 ${v.max_chg} 檔：前 20 名直接納入與市值配額會讓名單超過上限，實際由指數公司依完整規則取捨，這裡照名次全列。</div>`:'')+
      ((v.dels||[]).length?`<div class=st style="margin-top:6px"><b>預估刪除</b>：${v.dels.map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a><span class=mu>（${r[2]==null?'不合格':`第 ${r[2]} 名`}${r[5]!=null?`・賣 ${f(r[5],0)} 億`:''}${r[6]!=null?`・${f(r[6],0)} 日量`:''}）</span>`).join('、')}</div>`:'')+
      `<div class=note>${hdAcc(v.acc)}估計被動買進＝市值 × ${HDE[k]} 過去各次「實際買進占市值」的中位數${v.fk!=null?`（${f(v.fk,2)}%）`:''}，以單檔權重上限 × 規模封頂；刪除股＝ETF 目前實際持股 × 收盤。「提醒」＝≥${HDB} 日量${gi('被動買賣日量')}：被動買盤結束後過去多半回落（見下方「被動買盤大小」）。</div></div>`;}
  return b?sec('idx-hd','高股息','高股息 ETF 下一次換股（預估）','0056、00878、00919、00929；資料截止前每天用最新資料重算，過了截止日就固定',b):'';}
function hdStudySec(H){const S=(H||{}).study||{};if(!S.n)return '';
  const B=S.by||{},ks=HDK.filter(k=>B[k]),g=(k,w,t)=>(((B[k].add||{})[w]||{})[t]||{}),gd=(k,w,t)=>(((B[k].del||{})[w]||{})[t]||{});
  const lst=(fn)=>ks.map(k=>{const x=fn(k);return x&&x.n?`${HDE[k]} ${pctT(x.avg)}`:null;}).filter(Boolean).join('、');
  const L=[],avg=(fn)=>{const xs=ks.map(fn).filter(x=>x&&x.n);return xs.length?xs.reduce((a,x)=>a+x.avg,0)/xs.length:null;};
  const inT=avg(k=>g(k,'in_T','c')),e10=avg(k=>g(k,'e10','c')),dp=avg(k=>gd(k,'pre','c')),pos=ks.filter(k=>(g(k,'e10','c').avg||0)>1);
  L.push(`<b>被動買盤${gi('被動買賣期間')}那幾天</b>：納入股對其他成分股${gi('對其他成分股')} ${lst(k=>g(k,'in_T','c'))}${inT!=null&&inT>0?'，普遍多漲':''}；買盤結束後 10 個交易日，對大盤 ${lst(k=>g(k,'T1_10','x'))}。`);
  L.push(`<b>提前卡位</b>：被動買盤開始前 10 個交易日就買（假設名單事先完全知道），對其他成分股 ${lst(k=>g(k,'e10','c'))}${e10!=null&&e10<=1?'——平均沒有比較好。高股息是用殖利率選股，股價跌了殖利率才會變高，納入股常是剛跌過的股票':''}${pos.length?`；有超額的是 ${pos.map(k=>HDE[k]).join('、')}${pos.includes('tw_div')?'（0056 用分析師預估股利選股，名單事先猜不準）':''}`:''}。`);
  L.push(`<b>刪除股</b>：公告前 25 個交易日，對其他成分股 ${lst(k=>gd(k,'pre','c'))}${dp!=null&&dp<0?'，公告前就先跌':''}；被賣完之後 10 個交易日 ${lst(k=>gd(k,'T1_10','c'))}。`);
  L.push(`樣本只有每檔 3～5 次審核，單次行情影響很大（例：2026 年 6 月 00919 換股期間，富邦媒、來億-KY 連續漲停），數字看方向就好。`);
  let b=`<div class=lead><ul>${L.map(x=>`<li>${x}</li>`).join('')}</ul></div>`;
  const cell=(k,w,del)=>{const c=del?gd(k,w,'c'):g(k,w,'c'),x=del?gd(k,w,'x'):g(k,w,'x');
    return c.n?`<td><b>${sgn(c.avg,1,'%')}</b><div class=sm2>中位 ${pctT(c.med)}・${c.win}% 贏</div><div class=sm2>對大盤 ${pctT(x.avg)}</div></td>`:'<td>—</td>';};
  b+=`<h4 class=sh>納入股：什麼時候買、什麼時候賣</h4><div class=tw><table><thead><tr><th>買 → 賣</th>${ks.map(k=>`<th>${HDE[k]}<br><span class=mu>${B[k].n_add} 檔・${B[k].n_rev} 次</span></th>`).join('')}</tr></thead><tbody>`+
    (S.win||[]).map(([w,lbl])=>`<tr><td class=wr>${esc(lbl)}</td>${ks.map(k=>cell(k,w,false)).join('')}</tr>`).join('')+
    `</tbody></table></div><div class=note>粗體＝對其他成分股（審核前後都在的成分股等權平均）的超額，扣掉高股息類股本身的漲跌；小字＝對加權指數。報酬扣來回成本 0.585%。被動買盤期間依官方投信買賣超推得（00919 有幾次在公告前 2～3 天就開始買；0056 在第三個週五收盤起 5 天；00878 名單不公布，ETF 開始換股後從每日持股揭露才看得到）。</div>`;
  b+=`<h4 class=sh>刪除股</h4><div class=tw><table><thead><tr><th>時段</th>${ks.map(k=>`<th>${HDE[k]}<br><span class=mu>${B[k].n_del} 檔</span></th>`).join('')}</tr></thead><tbody>`+
    (S.dwin||[]).map(([w,lbl])=>`<tr><td class=wr>${esc(lbl)}</td>${ks.map(k=>cell(k,w,true)).join('')}</tr>`).join('')+`</tbody></table></div>`;
  b+=`<details class=mr><summary>逐次明細</summary><div class=tw><table><thead><tr><th>ETF・審核</th><th>被動買賣</th><th>納入</th><th>買盤前 10 日</th><th>被動買盤期間</th><th>公開後買</th><th>買盤後 5 日</th><th>刪除股公告前</th></tr></thead><tbody>`+
    ks.flatMap(k=>(B[k].revs||[]).map(r=>`<tr><td>${HDE[k]}<div class=sm2>${esc(r.review)}</div></td><td>${md(r.t0)}～${md(r.t1)}</td><td>${r.n_add}／${r.n_del}</td><td>${pctT(r.ac_e10)}</td><td>${pctT(r.ac_in_T)}</td><td>${pctT(r.ac_ann_T1)}</td><td>${pctT(r.ac_T1_5)}</td><td>${pctT(r.dc_pre)}</td></tr>`)).join('')+
    `</tbody></table></div><div class=note>各欄＝當次納入（刪除）股對其他成分股的平均超額。季審只有刪除（隨母指數剔除）時納入欄是 —。</div></details>`;
  return sec('idx-hds','高股息研究','高股息 ETF 換股研究',`0056、00878、00919、00929 過去審核（2024-11 起，價量資料只到兩年前）`,b);}
/* 高股息：被動買盤大小（權重）與策略測試（hdflow；數字每次建表重算） */
function hdVerdict(t){const s=t.rev||{};if(!s.n)return '—';const p=s.pos/s.n;
  if(t.kind==='long')return p>=.7&&s.avg>0?'<b class=up>多半賺</b>':p<=.3?'<span class=dn>多半賠</span>':'<span class=mu>賺賠各半，看行情</span>';
  return p<=.3?'<b class=dn>多半下跌</b>':p>=.7?'<span class=up>多半上漲</span>':'<span class=mu>方向不一致</span>';}
function hdTestRow(t){const s=t.rev||{},r=t.tr||{};
  return `<tr><td class="l wr">${esc(t.lbl)}</td><td>${s.n?pctT(s.avg):'—'}</td><td>${s.n?pctT(s.med):'—'}</td><td>${s.n?`${s.pos}／${s.n}`:'—'}</td><td>${r.n?`${r.n} 筆・平均 ${pctT(r.avg)}・${Math.round(r.pos/r.n*100)}% 為正`:'—'}</td><td>${hdVerdict(t)}</td></tr>`;}
function bkLbl(b){const [sd,lo,hi]=b,S={add:'納入',stay:'留任',del:'刪除'}[sd];
  if(lo==null)return `${S}・${hi<=0?`被賣 ≥${f(-hi,0)}`:`被買 <${f(hi,0)}`} 日量`;
  if(hi==null)return `${S}・${lo<0?`被賣 <${f(-lo,0)}`:`被買 ≥${f(lo,0)}`} 日量`;
  if(hi<=0)return `${S}・被賣 ${f(-hi,0)}～${f(-lo,0)} 日量`;
  if(lo<0)return `${S}・±${f(hi,0)} 日量內`;
  return `${S}・被買 ${f(lo,0)}～${f(hi,0)} 日量`;}
function bkCell(x){return x&&x.n?`${pctT(x.avg)}<div class=sm2>${x.pos}／${x.n} 為正</div>`:'—';}
function hdFlowSec(H){const S=(H||{}).flow||{};if(!S.tests)return '';
  const T={};S.tests.forEach(t=>T[t.k]=t);const big=S.big||HDB,aft=S.after||10,R=t=>(t&&t.rev)||{};
  const fk=Object.entries(S.f||{}).map(([k,v])=>`${HDE[k]} ${f(v[0],1)}%`).join('、'),ex=(S.ex||[])[0],A=S.acc||{};
  const B=(sd,lo)=>(S.bk||[]).find(b=>b[0]===sd&&b[1]===lo),b10=B('add',10),sCut=B('stay',null),sUp=B('stay',2);
  const e10=(A.bk||[]).find(x=>x[0]===10);
  const L=[];
  L.push(`<b>權重跟著市值走</b>：同一次換股，被動 ETF 買進每檔納入股的金額約是它市值的固定比例（過去各次中位數：${fk}），殖利率高不會讓權重遠超過市值比例。真正被「拉高」的是<b>相對成交量</b>${gi('被動買賣日量')}：規模大、冷門中型股平常成交少${ex?`，一次被買進最多約 ${f(ex[4],0)} 天的成交量（${esc(ex[1])}・${esc(ex[2])} ${esc(ex[3])}）`:''}。`);
  if(A.rho!=null)L.push(`<b>事前估得出來</b>：市值 × 上面的比例 ÷ 20 日均成交，和實際的等級相關${gi('等級相關')} ${f(A.rho,2)}（${A.n} 檔）${e10?`；估計 ≥10 天的，實際中位 ${f(e10[3],1)} 天`:''}。`);
  if(b10)L.push(`<b>大買盤期間確實漲比較多</b>：實際被買 ≥10 日量的納入股，被動買盤期間對大盤平均 ${pctT(b10[4].avg)}（${b10[4].pos}／${b10[4].n} 檔為正）。但事前只能照估計做——名單公開後開盤買、最後一天賣，估計 ≥${big} 日量的每次審核平均 ${pctT(R(T.ride5).avg)}、${R(T.ride5).n} 次 ${R(T.ride5).pos} 次賺：公告隔天開盤就先反映一部分，而且和當時高股息類股整體漲跌綁在一起。`);
  L.push(`<b>穩定的是買盤結束之後</b>：估計 ≥${big} 日量的納入股，被動買盤結束後 ${aft} 個交易日對大盤平均 ${pctT(R(T.post_big).avg)}、${R(T.post_big).n} 次只有 ${R(T.post_big).pos} 次為正；對其他成分股${gi('對其他成分股')} ${pctT(R(T.post_bigc).avg)}（${R(T.post_bigc).pos}／${R(T.post_bigc).n} 次為正）。買盤小的（<${big} 日量）對其他成分股 ${pctT(R(T.post_smallc).avg)}——回落集中在大買盤股 → 做成「被動買賣提醒」${gi('被動買賣提醒')}（策略頁「其他觀察」）。`);
  L.push(`<b>刪除股被賣完沒有反彈</b>：被動賣盤結束後 ${aft} 日對大盤 ${pctT(R(T.del10).avg)}（${R(T.del10).n} 次 ${R(T.del10).pos} 次為正）；估計賣壓 ≥${big} 日量的，名單公開後到被動賣完對大盤 ${pctT(R(T.del_ann).avg)}（${R(T.del_ann).n} 次 ${R(T.del_ann).n-R(T.del_ann).pos} 次下跌）。`);
  if(sCut)L.push(`<b>留任股的權重調整</b>：被調降（被賣 ≥5 日量）的，被動賣盤期間對大盤 ${pctT(sCut[4].avg)}（${sCut[4].pos}／${sCut[4].n} 檔為正）${sUp?`；被調升（被買 2～5 日量）的 ${pctT(sUp[4].avg)}`:''}。留任股的權重變化事前算不出來（要用指數公司的權重公式與當天價格），換股第一天的投信買賣超出來才看得到。`);
  let b=`<div class=lead><ul>${L.map(x=>`<li>${x}</li>`).join('')}</ul></div>`;
  b+=`<h4 class=sh>實際被動買賣 vs 漲跌</h4><div class=tw><table><thead><tr><th class=l>分組（實際被動買賣 ÷ 20 日均量）</th><th>檔數</th><th>被動買賣期間</th><th>結束後 5 日</th><th>結束後 ${aft} 日</th><th>結束後 ${aft} 日<br><span class=mu>對其他成分股</span></th></tr></thead><tbody>`+
    (S.bk||[]).map(x=>`<tr><td class=l>${bkLbl(x)}</td><td>${x[3]}</td><td>${bkCell(x[4])}</td><td>${bkCell(x[5])}</td><td>${bkCell(x[6])}</td><td>${bkCell(x[7])}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>對大盤超額、不扣成本。被動買賣＝官方投信買賣超在被動買賣期間的合計，扣掉平常水準（之前第 25～6 個交易日的中位數）；投信買賣超是全體投信合計，含其他基金進出，是近似值。這張表用的是「事後」實際量，下面的策略測試只用事前估計。</div>`;
  b+=`<h4 class=sh>策略測試（樣本內）</h4><div class=tw><table><thead><tr><th class=l>做法</th><th>每次平均</th><th>中位</th><th>幾次為正</th><th>逐筆</th><th>判讀</th></tr></thead><tbody>${S.tests.map(hdTestRow).join('')}</tbody></table></div>`+
    `<div class=note>「每次」＝同一次審核的各檔平均（一次審核算一筆，避免某次檔數多就主導結果）；買進類扣來回成本 0.585%，避開／觀察類不扣。只用事前估計：估計比例用同一檔 ETF「其他次」審核算，不用到當次自己。樣本只有十幾次審核、集中在 2025～2026 年，數字看方向就好。</div>`;
  const rv=t=>(T[t]||{}).by||[];
  b+=`<details class=mr><summary>逐次明細：追買 vs 結束後</summary><div class=tw><table><thead><tr><th>ETF・審核</th><th>追買（估計 ≥${big} 日量）</th><th>結束後 ${aft} 日（估計 ≥${big} 日量）</th><th>刪除股賣完後 ${aft} 日</th></tr></thead><tbody>`+
    [...new Set([...rv('ride5'),...rv('post_big'),...rv('del10')].map(x=>x[0]+'|'+x[1]))].sort().map(kk=>{const [e,r]=kk.split('|'),g=t=>{const x=rv(t).find(y=>y[0]===e&&y[1]===r);return x?`${pctT(x[2])}<div class=sm2>${x[3]} 檔</div>`:'—';};
      return `<tr><td>${esc(e)}<div class=sm2>${esc(r)}</div></td><td>${g('ride5')}</td><td>${g('post_big')}</td><td>${g('del10')}</td></tr>`;}).join('')+`</tbody></table></div></details>`;
  if((S.ex||[]).length)b+=`<details class=mr><summary>例子：被買最多天量的納入股</summary><div class=tw><table><thead><tr><th>股票</th><th>ETF・審核</th><th>被買(億)</th><th>占市值</th><th>幾天的量</th><th>買盤期間</th><th>結束後 ${aft} 日</th></tr></thead><tbody>`+
    S.ex.map(x=>`<tr data-c="${esc(x[0])}"><td><span class=nm>${esc(x[1])}</span><span class=cd>${esc(x[0])}</span></td><td>${esc(x[2])}<div class=sm2>${esc(x[3])}</div></td><td>${f(x[5],1)}</td><td>${x[6]==null?'—':f(x[6],1)+'%'}</td><td>${f(x[4],1)}</td><td>${sgn(x[7],1,'%')}</td><td>${sgn(x[8],1,'%')}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>報酬為對大盤超額、不扣成本。</div></details>`;
  return sec('idx-hdw','買盤大小','高股息：被動買盤大小（權重）與策略測試',`過去 ${S.n_rev} 次換股、${S.n_add} 檔納入股`,b);}
function calCard(r){const d=r[10];
  return `<div class=ev><div class=cdn>${d!=null&&d>=0?`${d}<small>天後生效</small>`:'<small>日期未定</small>'}</div><div class=evn>${esc(r[1])} <span class=mu style="font-weight:400">${esc((r[2]||[]).join(' '))}</span></div>`+
   `<div class=evm>${r[4]?`資料截止 ${md(r[4])}・`:''}${r[5]?`公告 ${md(r[5])}・`:''}${r[6]?`生效 ${md(r[6])}`:'生效日未定'}${r[7]?`・分 ${r[7]} 日買賣`:r[7]===0?'・一次買賣':''}</div>`+
   `<div class=evm>${r[8]==='推算'?'日期為推算（官方未公告）':esc(r[8]||'')}・${r[12]||HDP.includes(r[0])?`<b class=up>有公告前預測</b>（信心 ${esc(r[9]||'')}）`:`未預測（信心 ${esc(r[9]||'')}）`}</div></div>`;}
function vIdx(){
  const X=D.idx||{};
  let h=`<div class=intro>被動 ETF 追蹤的指數定期換股，生效日前後被動資金會集中買賣。<b>公告前預測</b>：臺灣50、00919、00929 照公開規則重算；0056、00878 的選股資料（分析師預估、ESG 評級）要付費，不做預測、只列時程。</div>`;
  if(X.err)h+=`<div class=st>指數區塊錯誤：${esc(X.err)}</div>`;
  const cal=(X.cal||[]).slice().sort((a,b)=>(a[10]??1e9)-(b[10]??1e9));
  h+=sec('idx-cal','時程','審核時程','依生效日排序',cal.length?`<div class=evs>${cal.map(calCard).join('')}</div>`:'<div class=st>尚無排定</div>');
  const t=X.tw50||{};let b='';
  if(!t.ok)b+=`<div class=st>${esc(t.why||'尚無資料')}</div>`;
  else{
    const nl=a=>(a||[]).length?(a||[]).map(r=>`<a data-c="${esc(r[0])}">${esc(r[1])}</a>`).join('、'):'無';
    const tp=(t.adds||[]).filter(r=>r[11]);
    b+=`<div class=lead><b>預估納入：</b>${nl(t.adds)}${tp.length&&tp.length<(t.adds||[]).length?`（漲勢前一半${gi('漲勢前一半')}：${nl(tp)}）`:''}　<b>預估刪除：</b>${nl(t.dels)}<div class=st style="margin-top:2px">排名基準 ${md(t.asof)}${t.frozen?'（＝資料截止日，指數公司用的就是這天，結果近乎確定）':`；距資料截止 ${md(t.cutoff)} 還有 ${t.n_days} 個交易日，機率依個股 60 日波動估計`}</div></div>`;
    b+=idxTbl('預估納入',t.adds,'add')+idxTbl('預估刪除',t.dels,'del')+idxTbl('邊緣觀察：可能升入前 40 名',t.watch_in,'add')+idxTbl('邊緣觀察：可能跌出 60 名',t.watch_out,'del');
    b+=`<div class=note>被動部位：${Object.entries(t.eq||{}).map(([e,v])=>esc(e)+' '+f(v,0)+' 億').join('、')}。刪除股的賣出量＝兩檔 ETF 目前實際持股；納入股的買進量＝規模 × 預估權重（以現有成分股反推自由流通比例）。</div>`;
    const rp=t.replay||[];
    if(rp.length){const hit=rp.reduce((s,r)=>s+(r.pred_add?r.hit_add+r.hit_del:0),0),tot=rp.reduce((s,r)=>s+(r.pred_add?(r.act_add||[]).length+(r.act_del||[]).length:0),0);
      b+=`<details class=mr><summary>規則回測：歷次審核命中 ${hit}／${tot}</summary><div class=tw><table><thead><tr><th>審核</th><th>資料日</th><th class=l>實際納入</th><th class=l>預測納入</th><th>命中</th><th class=l>實際刪除</th><th class=l>預測刪除</th><th>命中</th></tr></thead><tbody>`+
      rp.map(r=>`<tr><td>${esc(r.review)}</td><td>${md(r.data)}</td><td class="l wr">${(r.act_add||[]).map(nmOf).map(esc).join('、')}</td><td class="l wr">${r.pred_add?(r.pred_add.map(nmOf).map(esc).join('、')||'—'):'<span class=mu>資料不足</span>'}</td><td>${r.pred_add?`${r.hit_add}／${(r.act_add||[]).length}`:'—'}</td><td class="l wr">${(r.act_del||[]).map(nmOf).map(esc).join('、')}</td><td class="l wr">${r.pred_del?(r.pred_del.map(nmOf).map(esc).join('、')||'—'):'—'}</td><td>${r.pred_del?`${r.hit_del}／${(r.act_del||[]).length}`:'—'}</td></tr>`).join('')+`</tbody></table></div><div class=note>用當次資料截止日的價量重跑規則。發行股數用最新值（股本變動會造成少量誤差）；臺灣50 實際依富時自由流通與流動性細則，邊界 ±2 名內可能不同。</div></details>`;}
  }
  h+=sec('idx-tw50','臺灣50','臺灣50（0050／006208）換股預測','',b);
  h+=studySec(X.study);
  h+=hdPredSec(X.hd)+hdStudySec(X.hd)+hdFlowSec(X.hd);
  if((X.hd||{}).err)h+=`<div class=st>高股息區塊錯誤：${esc(X.hd.err)}</div>`;
  const pf=X.pflow||[];
  h+=sec('idx-pf','被動換股','被動 ETF 近 10 個交易日換股動作','所有被動 ETF（含規模前段擴充檔）已發生的新進、出清與真加減碼，依個股彙整；換股期間這裡會先反映',
    pf.length?`<div class=tw><table><thead><tr><th>股票</th><th>被動淨買賣(張)</th><th>約幾日量</th><th class=l>新進</th><th class=l>出清</th><th class=l>涉及 ETF</th></tr></thead><tbody>`+pf.map(r=>`<tr data-c="${esc(r[0])}"><td><span class=nm>${esc(r[1])}</span><span class=cd>${esc(r[0])}</span></td><td>${sgn(r[2],0)}</td><td>${r[3]==null?'—':sgn(r[3],2)}</td><td class=l>${esc((r[4]||[]).join(' '))}</td><td class=l>${esc((r[5]||[]).join(' '))}</td><td class="l mu">${esc((r[6]||[]).join(' '))}</td></tr>`).join('')+`</tbody></table></div>`:'<div class=st>近 10 日無被動換股動作</div>');
  let o='';
  for(const r of (X.cal||[])){if(r[12]||HDK.includes(r[0]))continue;const hi=(r[13]||[])[0];
    o+=`<div class=card><h4>${esc(r[1])} <span class=pill>${esc((r[2]||[]).join(' '))}</span></h4><div class=st>${esc(r[11]||'')}</div>`+
     (hi?`<div class=st style="margin-top:4px">上次（${esc(hi.review||'')}）納入：${esc((hi.adds_names||(hi.adds||[]).map(nmOf)).join('、')||'—')}；刪除：${esc((hi.dels_names||(hi.dels||[]).map(nmOf)).join('、')||'—')}</div>`:'')+
     `<div class=st style="margin-top:4px">公告前預測：${r[0]==='msci_esg30'?'ESG 評分為付費資料，不做；公告後看持股揭露追蹤提前建倉':r[0]==='tw_div'?'第三階段（以公開殖利率代理分析師預估，信心中低）':'第二階段（需股利、EPS 資料）'}</div></div>`;}
  if(o)h+=sec('idx-oth','其他指數','其他指數的規則與上次結果','',o);
  $('#main').innerHTML=h;
}

/* ---------- 策略＋紙上交易（每條一張卡、四個小標：在賭什麼／為什麼有效／候選／會失效；細節收在展開） ---------- */
const STYPE={s1:'短線・持有 3 天',s4:'短線・持有 10 天',s3:'事件・臺灣50 換股',s5:'長線・每月選股'};
function stStat(g){return g&&g.n?`平均超額 ${sgn(g.x,2,'%')}、中位 ${sgn(g.xm,2,'%')}、勝率 ${f(g.w,0)}%（${g.n} 筆）`:'尚無已出場交易';}
function stShort(g,s5){return g&&g.n?(s5?`平均 ${sgn(g.avg,1,'%')}・勝率 ${g.win}%（${g.n} 筆）`:`超額 ${sgn(g.x,2,'%')}・勝率 ${f(g.w,0)}%（${g.n} 筆）`):'<span class=mu>尚無</span>';}
function st5(g){return g&&g.n?`平均 ${sgn(g.avg,1,'%')}、中位 ${sgn(g.med,1,'%')}、勝率 ${g.win}%、翻倍 ${f(g.dbl,1)}%、平均超額 ${sgn(g.x,1,'%')}（${g.n} 筆${g.open?`，持有中 ${g.open}`:''}）`:'尚無已出場交易';}
function ruleRows(rules){return rules.map(x=>{const i=x.indexOf('：');const lab=i>0&&i<=8?x.slice(0,i):'';return `<div class="rl${lab?'':' nl'}">${lab?`<span class=rlk>${esc(lab)}</span>`:''}<span>${esc(lab?x.slice(i+1):x)}</span></div>`;}).join('');}
function stBadge(s,P){return s.status==='達標'?'<span class=pill style="background:#fdecea;color:#d33a34">達標</span>':s.status==='不達標'?'<span class=pill>不達標</span>':`<span class=pill style="background:rgba(37,99,201,.1);color:#1c4fa8">驗證中 ${s.event?`${s.days}／2 次審核`:`${(s.fwd_stats||{}).n||0}／${P[0]} 筆`}</span>`;}
function tradeTbl(rows,monthly){const gp=!monthly&&rows.some(t=>t.gap!=null);
  return `<div class=tw><table><thead><tr><th>股票</th><th>${monthly?'篩選月':'訊號日'}</th><th class=l>狀態</th>${gp?'<th>跳空</th>':''}<th>進場</th><th>出場／現價</th><th>持有</th><th>報酬</th><th>超額${gi('超額')}</th></tr></thead><tbody>`+
  rows.map(t=>`<tr data-c="${esc(t.c)}" class="${t.st==='skip'?'grey':''}"><td><span class=nm>${esc(t.n)}</span><span class=cd>${esc(t.c)}</span></td><td>${monthly?esc((t.d||'').slice(0,7)):md(t.d)}</td><td class=l>${t.st==='skip'?'放棄：'+esc(t.why||''):t.st==='open'?'持有中':t.st==='cand'?'待進場':esc(t.why||'')}${t.side?` <span class=pill>${t.side==='add'?'納入':'刪除'}</span>`:''}</td>${gp?`<td>${t.gap==null?'—':sgn(t.gap,1,'%')}</td>`:''}<td>${t.entry==null?'—':fp(t.entry)}</td><td>${t.exit!=null?fp(t.exit):t.now!=null?fp(t.now):'—'}</td><td>${t.held==null?'—':t.held+' 日'}</td><td>${sgn(t.r,1,'%')}</td><td>${t.x==null?'—':sgn(t.x,1,'%')}</td></tr>`).join('')+`</tbody></table></div>`;}
function pctT(x,d=1){return x==null?'—':(x>0?'+':x<0?'−':'')+f(Math.abs(x),d)+'%';}
function lv(px,p){return px*(1+p/100);}
function sq(k,v){return `<div class=sq><span class=sqk>${k}</span><div>${v}</div></div>`;}
function failRow(xs){return (xs||[]).map((x,i)=>`<span class=fx>${'①②③④'[i]||'・'} ${esc(x)}</span>`).join('');}
function stW(){return Math.max(280,Math.min(760,($('#main').clientWidth||360)-34));}
/* 持有天數掃描：每根柱子＝第 N 天收盤出場的平均超額；本策略紅綠、對照組灰；藍底＝採用的天數 */
function scanChart(sc,hold){if(!sc||!(sc.grp||[]).length)return '';const H=sc.h,g=sc.grp,W=stW(),HH=150,pl=40,pr=6,pt=12,pb=22;
  const vals=g.flatMap(x=>x.x).filter(v=>v!=null);if(!vals.length)return '';const mx=Math.max(1,...vals.map(Math.abs));
  const y=v=>pt+(HH-pt-pb)/2*(1-v/mx),z=y(0),cw=(W-pl-pr)/H,bw=Math.max(2,Math.min(14,cw/(g.length+.8)));
  let s='';if(hold&&hold<=H){const cx=pl+(hold-.5)*cw;s+=`<rect x=${(cx-cw/2).toFixed(1)} y=${pt-8} width=${cw.toFixed(1)} height=${HH-pt-pb+14} fill="#e8effb" rx=3 />`;}
  s+=`<line x1=${pl} x2=${W-pr} y1=${z.toFixed(1)} y2=${z.toFixed(1)} stroke="#c9d0da"/>`;
  for(const t of [mx,-mx])s+=`<text x=${pl-5} y=${(y(t)+4).toFixed(0)} font-size=11 fill="#727e8c" text-anchor=end>${t>0?'+':'−'}${f(Math.abs(t),1)}%</text>`;
  s+=`<text x=${pl-5} y=${(z+4).toFixed(0)} font-size=11 fill="#727e8c" text-anchor=end>0</text>`;
  for(let h=1;h<=H;h++){const cx=pl+(h-.5)*cw;
    g.forEach((gr,k)=>{const v=gr.x[h-1];if(v==null)return;const x0=cx+(k-(g.length-1)/2)*bw*1.1-bw/2,hh=Math.max(1,Math.abs(y(v)-z));
      s+=`<rect x=${x0.toFixed(1)} y=${Math.min(y(v),z).toFixed(1)} width=${bw.toFixed(1)} height=${hh.toFixed(1)} fill="${k?'#b6bfcb':v>=0?'#d33a34':'#1f9d57'}"/>`;});
    if(H<=10||h%2===1||h===hold)s+=`<text x=${cx.toFixed(1)} y=${HH-6} font-size=11 fill="${h===hold?'#1c4fa8':'#727e8c'}" font-weight="${h===hold?700:400}" text-anchor=middle>${h}</text>`;}
  return `<svg width=${W} height=${HH} viewBox="0 0 ${W} ${HH}">${s}</svg><div class=lg><span><i style="background:#d33a34"></i>${esc(g[0].lbl)}（紅＝贏大盤、綠＝輸）</span>${g[1]?`<span><i style="background:#b6bfcb"></i>${esc(g[1].lbl)}</span>`:''}<span>橫軸＝持有天數；藍底＝採用 ${hold} 天</span></div>`;}
function scanLine(s){const sc=s.scan;if(!sc||!(sc.grp||[]).length)return '';const H=sc.h,h=Math.min(s.hold||1,H);
  const win=gr=>gr.x.filter(v=>v!=null&&v>0).length,nm=gr=>esc(gr.lbl.replace(/（.*?）/g,''));const a=sc.grp[0],b=sc.grp[1];
  return `樣本內，${nm(a)}的 ${a.n[h-1]} 筆：持有 1～${H} 天中 <b>${win(a)} 個</b>天數平均贏大盤`+(b?`；${nm(b)}的 ${b.n[h-1]} 筆只有 <b>${win(b)} 個</b>`:'')+'。';}
function distTxt(ds,net){if(!ds||!ds.n||!ds.p)return '';const p=ds.p;
  return `${ds.n} 筆的出場價相對進場價：一成 ≤ ${pctT(p[0])}、四分之一 ≤ ${pctT(p[1])}、中位 ${pctT(p[2])}、四分之一 ≥ ${pctT(p[3])}、一成 ≥ ${pctT(p[4])}。`+
    (net!==false&&ds.aw!=null?`扣成本後賺的平均 ${pctT(ds.aw)}、賠的平均 ${pctT(ds.al)}`:'')+(ds.stop!=null&&net!==false?`；停損 ${ds.stop} 次。`:'');}
function moTxt(ds){return ds&&(ds.mo||[]).length?'逐月平均超額：'+ds.mo.map(m=>`${+m[0].slice(5)} 月 ${m[1]} 筆 ${pctT(m[2])}`).join('｜'):'';}
/* 候選的交易計畫：進場／停損／出場／過去同類（歷史分布換算的價位，非預測）＋入選理由 */
function pcRow(k,v){return `<div class=pcr><span>${k}</span><span>${v}</span></div>`;}
function pcHead(c,px){const t=`<b>${esc(c.n)}</b> <span class=cd>${esc(c.c)}</span>`;return `<div class=pch>${BY[c.c]?`<a data-c="${esc(c.c)}">${t}</a>`:`<span>${t}</span>`}<span class=mu>收 <b class=pk>${fp(px)}</b></span></div>`;}
function pastRow(ds,px){const p=ds&&ds.p;return p&&px?pcRow('過去同類',`中位 <b>${fp(lv(px,p[2]))}</b>，一半落在 ${fp(lv(px,p[1]))}～${fp(lv(px,p[3]))}`):'';}
function pastNote(ds){return ds&&ds.n?`「過去同類」＝同一條規則過去 ${ds.n} 筆交易的出場價（相對進場價），換算到這檔今天的收盤。`:'';}
function whyS(k,c,r){const L=[];
  if(k==='s1'){const ia=r.ia5||[];if(ia.length)L.push(`5 日內 ${ia.length} 家投信加碼（${esc(ia.slice(0,3).join('、'))}${ia.length>3?'等':''}）`);if(r.a5v!=null)L.push(`主動 ETF 淨買 ${f(r.a5v,1)} 億`);}
  if(k==='s4'){const nb=(r.hd||[]).filter(x=>(E[x[0]]||{}).is==='群益'&&x[3]===c.d).map(x=>x[0]);L.push(nb.length?`群益 ${esc(nb.join('、'))} 新建倉`:'群益主動 ETF 新建倉');}
  return L.join('；');}
function refS(r){const L=[];if(r.cost!=null&&r.dev!=null)L.push(`比新建倉成本${r.dev>=0?'高':'低'} ${f(Math.abs(r.dev),1)}%`);
  if(r.t5!=null)L.push(`投信 5 日 ${pm(r.t5)} 張`);if(r.f5!=null)L.push(`外資 5 日 ${pm(r.f5)} 張`);return L.join('、');}
function warnS(r){const W=[];if((r.sg||[]).some(x=>RISK.has(x)))W.push('同時有集體撤退訊號');
  if(r.b20!=null&&r.b20>=15)W.push(`離 20 日線已 +${f(r.b20,0)}%`);if(r.liq!=null&&r.liq<1)W.push(`日均成交僅 ${f(r.liq,2)} 億`);return W.join('；');}
function planS(s,c){const r=BY[c.c]||{},px=c.px,ds=s.dist||{};
  let b=s.key==='s1'?pcRow('進場',`開盤<b>低於 ${fp(px)}</b>`):'';
  if(c.stop!=null)b+=pcRow('停損',`<b>${fp(c.stop)}</b>（${pctT((c.stop/px-1)*100)}）`);
  b+=pastRow(ds,px);
  const w=whyS(s.key,c,r),rf=refS(r),wn=warnS(r);
  return `<div class=pc>${pcHead(c,px)}${b}${w?`<div class=pcw><b>入選</b>${w}</div>`:''}${rf?`<div class=pcw><b>參考</b>${rf}</div>`:''}${wn?`<div class=pcx>注意：${wn}</div>`:''}</div>`;}
function stCard(s,P,cand,ev,more){
  let b=sq('在賭什麼',esc(s.bet||''))+sq('為什麼有效',`${esc(s.why||'')}${ev?`<div class=sqe>${ev}</div>`:''}`)+cand+sq('會失效',`<div class=fxs>${failRow(s.fail)}</div>`);
  b+=`<details class=mr><summary>證據圖、完整規則與交易明細</summary>${more}</details>`;
  return sec('st-'+s.key,s.nav||s.name.split(/[（・(]/)[0],`${esc(s.name)} ${stBadge(s,P)}`,esc(STYPE[s.key]||''),`<div class="card stc">${b}</div>`);}
function moreS(s){const sc=s.scan,ins=(s.ins||[]).slice().reverse(),fw=(s.fwd||[]).slice().reverse();
  let m='';if(sc)m+=`<h4 class=sh>持有 1～${sc.h} 天的平均超額（樣本內）</h4>${scanChart(sc,s.hold)}<div class=note>每根柱子＝在第 N 天收盤出場時，平均比大盤多賺（紅）或少賺（綠）多少——用來確認結論不是只在某個持有天數才成立。</div>`;
  const ds=s.dist||{};if(ds.n)m+=`<h4 class=sh>照規則做的結果（樣本內，含停損、扣成本）</h4><div class=st>${stStat(s.ins_stats)}。${distTxt(ds)}</div><div class=st>${moTxt(ds)}</div>`;
  if((s.more||[]).length)m+=`<div class=st style="margin-top:6px">${(s.more||[]).map(esc).join('<br>')}</div>`;
  m+=`<h4 class=sh>完整規則 <span class=pill>v${s.ver}・${md(s.since)} 起算</span></h4><div class=rls>${ruleRows(s.rule||[])}</div>`;
  if(fw.length)m+=`<h4 class=sh>紙上交易紀錄（${fw.length} 筆）</h4>${tradeTbl(fw,false)}`;
  if(ins.length)m+=`<details class=mr><summary>樣本內交易 ${ins.length} 筆</summary>${tradeTbl(ins,false)}</details>`;
  return m;}
function candS(s){const cs=s.cands||[],lbl='明日候選',c0=cs[0];
  if(!cs.length)return sq(lbl,`<span class=mu>今天沒有${s.key==='s4'?'（群益今天沒有新建倉）':'（今天沒有新亮燈的股票）'}</span>`);
  const how=`${c0.ent?md(c0.ent)+' ':''}${s.key==='s1'?'開盤價低於今天收盤才買（8:59 看試撮），開平或開高就放棄':'開盤買'}；${c0.out?md(c0.out)+' ':'第 '+s.hold+' 個交易日'}收盤賣出，期間收盤跌破停損價就提早出。`;
  return sq(lbl,`<div class=pcn>${how}</div><div class=pcs>${cs.map(c=>planS(s,c)).join('')}</div><div class=note>${pastNote(s.dist)}</div>`);}
/* 臺灣50 換股：三個版本並列（公告前卡位／公告後進場＝兩個新版本、官方名單全部＝對照） */
function evS(g){return g&&g.n?`每次平均 <b>${pctT(g.avg)}</b>、中位 ${pctT(g.med)}、${g.n} 次賺 ${g.win} 次、最差一次 ${pctT(g.lo)}${g.x!=null?`；平均贏大盤 ${pctT(g.x)}（${g.xw} 次贏）`:''}（共 ${g.trades} 筆）`:'<span class=mu>尚無已出場交易</span>';}
function evShort(g){return g&&g.n?`每次超額 ${sgn(g.x,2,'%')}・${g.xw}／${g.n} 次贏大盤`:'<span class=mu>尚無</span>';}
function vBadge(v){return v.status==='達標'?'<span class=pill style="background:#fdecea;color:#d33a34">達標</span>':v.status==='不達標'?'<span class=pill>不達標</span>':`<span class=pill style="background:rgba(37,99,201,.1);color:#1c4fa8">驗證中 ${v.days}／2 次審核</span>`;}
function eAt(E,k){const i=(E.k||[]).indexOf(k);return i<0||E.avg[i]==null?null:{avg:E.avg[i],med:E.med[i],win:E.win[i],n:E.n[i],lo:E.lo[i]};}
function s3Ev(s){const S=(D.idx||{}).study||{},p5=s.post5||{},L=[];
  if(S.n){const a0=(S.acc||[]).find(a=>a.k===0),W=S.within||[],E=S.early||{},e=eAt(E,E.pick),z=eAt(E,0),
      M=(S.fac||[]).find(x=>x.k==='mom')||{},F=(S.fac||[]).find(x=>x.k==='w')||{};
    if(a0)L.push(`過去 ${S.n_rev} 次審核，資料截止日照規則重算的名單 ${a0.hit}／${a0.tot} 檔${a0.hit===a0.tot&&!a0.fp?'全對':'命中'}`);
    if(e&&z)L.push(`截止前 ${E.pick} 個交易日就先建倉（最多 ${E.N} 檔、截止日校正）每次平均 ${pctT(e.avg)}、${e.n} 次賺 ${e.win} 次；等到截止日才買只有 ${pctT(z.avg)}——漲幅有一大段在截止日之前`);
    if(W.length)L.push(`同一次審核裡漲最多的，${W.filter(w=>w.same).length}／${W.length} 次是截止前漲勢最強的那檔，權重最大的只有 ${W.filter(w=>w.heavy_same).length}／${W.length} 次（漲勢和漲幅的相關 ${f(M.rho,2)}，權重只有 ${f(F.rho,2)}）`);}
  if(p5.n)L.push(`納入股生效後續抱 5 天平均 ${pctT(p5.r)}（${p5.w}% 賺），所以生效前就賣`);
  return L.length?L.join('；')+'。':'';}
function s3Vers(s){const V=s.vers||[];if(!V.length)return '';
  return sq('三個版本',`<div class=tvs>${V.map(v=>`<div class="tv${v.k==='all'?' ctl':''}"><div class=tvh><b>${esc(v.name)}</b>${vBadge(v)}</div>`+
    `<div class=tvm>${esc(v.buy)}買 → ${esc(v.sell)}賣${v.k==='early'?'；截止日名單沒有的隔天開盤賣、有但沒買到的補進（最多 4 檔）':''}</div>`+
    `<div class=tvt>過去：${evS(v.rev_stats)}</div>`+
    `${(v.fwd_rev||{}).n?`<div class=tvt>紙上：${evS(v.fwd_rev)}</div>`:''}</div>`).join('')}</div>`+
    `${s3Sens(s)}<div class=note>報酬已扣來回成本 0.585%；「每次」＝同一次審核買的幾檔平均分配資金算一個報酬。兩個新版本從 ${md((V[0]||{}).since)} 起並列紙上記帳，各滿 2 次審核再看哪個留下。</div>`);}
/* 成績集中在少數幾次：扣掉兩版差距最大的 2 次後各剩多少（資料即時算，不寫死） */
function s3Sens(s){const z=s.sens;if(!z||z.early==null||z.post==null||z.early_all==null||z.post_all==null)return '';
  const g=(z.gaps||[]).map(x=>x==null?'—':pctT(x)),gd=(z.gaps||[]).every(x=>x!=null&&x<=-3);
  const d0=z.post_all-z.early_all,d1=z.post-z.early,lead=d0>0?'公告後版':'提前卡位版';
  return `<div class=sqe>兩版差距最大的 2 次是 ${z.revs.map(esc).join('、')}${gd?`：公告後第一天開盤，納入股平均 ${g.join('、')}（公告後版剛好買在大跌後的低點）`:''}。扣掉這 2 次，其他 ${z.n_left} 次提前卡位版每次平均 ${pctT(z.early)}、公告後版 ${pctT(z.post)}`+
    `${Math.sign(d1)!==Math.sign(d0)||Math.abs(d1)<Math.abs(d0)/2?`——${lead}的領先主要來自這 2 次。`:'。'}</div>`;}
function trTxt(t){if(!t)return '—';if(t.st==='cand')return `${md(t.ent)} 開盤買`;
  if(t.st==='open')return `${fp(t.entry)} 買進，現 ${fp(t.now)}（${pctT(t.r)}）`;
  if(t.st==='closed')return `${fp(t.entry)} → ${fp(t.exit)}（${pctT(t.r)}，${esc(t.why||'')}）`;return esc(t.why||'—');}
function s3Item(it,p){const px=it.px!=null?it.px:(BY[it.c]||{}).px,st=p.stage,cut=st==='frozen'||st==='announced';
  let b=pcRow('排名',it.rank?`第 ${it.rank} 名${cut?'（截止日）':'（目前）'}`:'—')+pcRow('40 日漲幅',it.mom==null?'—':pctT(it.mom));
  const a=st==='watch'?`${md(p.e_in)} 開盤買（以今天排名試算）`:it.e||it.t?trTxt(it.ta)+(it.t&&it.ta&&it.ta.st!=='closed'?'（截止日補位）':''):`<span class=mu>不買（排在前 ${p.N} 檔之外）</span>`;
  b+=pcRow('提前卡位',a);
  if(st==='frozen')b+=pcRow('公告後版',it.b?'官方名單相同就公告後買':'<span class=mu>不買</span>');
  if(st==='announced')b+=pcRow('公告後版',it.b?trTxt(it.tb):it.act?'<span class=mu>不買（漲勢後一半）</span>':'<span class=mu>官方沒納入</span>');
  const nt=cut&&it.e&&it.pred===false?`截止日名單沒有：${md(p.a_in)} 開盤賣`:st==='announced'&&it.act===false&&(it.e||it.t)?'官方沒有納入：公告後第一天開盤賣':'';
  return `<div class=pc>${pcHead(it,px)}${b}${nt?`<div class=pcx>${nt}</div>`:''}</div>`;}
function s3Plan(s){const p=s.plan;if(!p)return sq('下一次','等下一次審核時程公布。');
  const it=p.items||[],st=p.stage;
  let h=`<div class=pcn>${esc(p.review)} 審核${p.status==='推算'?'（日期為推算）':''}：<b>${md(p.e_sig)}</b> 收盤選股、<b>${md(p.e_in)}</b> 開盤建倉（截止前 ${p.K} 個交易日）→ ${md(p.cutoff)} 資料截止、${md(p.a_in)} 開盤校正 → ${md(p.announce)} 公告、公告後版 ${md(p.b_in)} 開盤買 → 全部在 <b>${md(p.out)}</b> 收盤賣（${md(p.effective)} 生效前一天）。</div>`;
  h+=`<div class=pcn>${st==='watch'?`還沒到建倉日。用今天的排名試算，會買這 ${it.length} 檔（${md(p.e_sig)} 收盤才定案，名單還會變）：`:
    st==='early'?`已選定 ${it.length} 檔；${md(p.cutoff)} 收盤照規則重算名單，名單沒有的隔天開盤賣、有但沒買到的補進（最多 ${p.N} 檔）。`:
    st==='frozen'?`截止日名單已定：預估納入 ${it.filter(i=>i.pred).length} 檔，提前卡位版持有 ${it.filter(i=>(i.e||i.t)&&i.pred).length} 檔；公告後版等官方公告。`:
    `官方公告納入 ${it.filter(i=>i.act).length} 檔。`}</div>`;
  h+=it.length?`<div class=pcs>${it.map(i=>s3Item(i,p)).join('')}</div>`:`<span class=mu>${st==='watch'?'目前排名前 45 名裡沒有非成分股，到建倉日若還是沒有，就等截止日名單再補位':'這次沒有要買的股票'}</span>`;
  if((p.dels||[]).length)h+=`<div class=note>${st==='announced'?'官方':'預估'}刪除：${p.dels.map(d=>esc(d[1])).join('、')}（只有對照版會在生效日收盤承接）。</div>`;
  return sq('下一次',h+`<div class=note><a data-go="idx" data-at="idx-tw50">指數頁看完整排名 →</a></div>`);}
function moreS3(s){let m='';
  if(((D.idx||{}).study||{}).n)m+=`<div class=st>完整研究（名單準度、提前幾天建倉、哪些納入股漲最多）：<a data-go="idx" data-at="idx-study">指數頁「換股研究」→</a></div>`;
  const br=(s.by_rev||[]).slice().reverse();
  if(br.length)m+=`<h4 class=sh>逐次比較（樣本內，每次的平均報酬、扣成本）</h4><div class=tw><table><thead><tr><th>審核</th><th>提前卡位</th><th>公告後版</th><th>對照</th><th>公告後第一天開盤</th></tr></thead><tbody>`+
    br.map(r=>`<tr><td>${esc(r[0])}</td><td>${sgn(r[1],1,'%')}</td><td>${sgn(r[2],1,'%')}</td><td>${sgn(r[3],1,'%')}</td><td>${r[4]==null?'—':sgn(r[4],1,'%')}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>「公告後第一天開盤」＝公告後版買進那天，買進股票的開盤價相對公告日收盤；負的越多，公告後版買得越便宜。</div>`;
  if((s.more||[]).length)m+=`<div class=st style="margin-top:6px">${s.more.map(esc).join('<br>')}</div>`;
  for(const v of (s.vers||[])){const fw=(v.fwd||[]).slice().reverse(),ins=(v.ins||[]).slice().reverse();
    m+=`<h4 class=sh>${esc(v.name)} <span class=pill>v${v.ver}・${md(v.since)} 起算</span></h4><div class=rls>${ruleRows(v.rule||[])}</div>`;
    if(fw.length)m+=`<div class=st>紙上交易 ${fw.length} 筆</div>${tradeTbl(fw,false)}`;
    if(ins.length)m+=`<details class=mr><summary>樣本內交易 ${ins.length} 筆</summary>${tradeTbl(ins,false)}</details>`;}
  if(!(s.vers||[]).length){const ins=(s.ins||[]).slice().reverse();
    m+=`<h4 class=sh>完整規則 <span class=pill>v${s.ver}・${md(s.since)} 起算</span></h4><div class=rls>${ruleRows(s.rule||[])}</div>`+
      (ins.length?`<details class=mr><summary>樣本內交易 ${ins.length} 筆</summary>${tradeTbl(ins,false)}</details>`:'');}
  return m;}
function s3Cands(s,k){const p=s.plan,nx=((D.strat||{}).next||[])[0];if(!p||!nx)return [];
  return (p.items||[]).filter(i=>k==='early'?(i.e||i.t)&&i.ta&&i.ta.st==='cand'&&i.ta.ent===nx:i.b&&i.tb&&i.tb.st==='cand'&&i.tb.ent===nx);}
function vSt(){
  const X=D.strat||{};const P=X.pass||[30,30];const L=X.list||[];const G=D.grow||{};const S5=G.s5;
  let h=`<div class=intro>每條策略＝一套寫死的買賣規則。每天收盤後自動列出明天的候選，附上進場條件、停損與出場日；起算日（${md((L[0]||{}).since)}）之後的訊號自動記入紙上交易${gi('紙上交易')}，滿 ${P[0]} 筆再看成績決定採不採用。「過去同類」是把歷史上同一條規則的交易結果換算成價位，只是統計參考、不是預測${gi('樣本內')}。</div>`;
  if(X.err)h+=`<div class=st>策略區塊錯誤：${esc(X.err)}</div>`;
  const ovRow=s=>s.vers?s.vers.map(v=>`<tr><td><a data-to="st-s3">臺灣50・${esc(v.name.split('・')[0].replace('（對照）',''))}</a>${v.k==='all'?' <span class=mu>對照</span>':''}</td><td class="l hm">${STYPE.s3}</td><td>${vBadge(v)}</td><td class=l>${evShort(v.rev_stats)}</td><td><b>${v.k==='all'?0:s3Cands(s,v.k).length}</b></td></tr>`).join(''):
    `<tr><td><a data-to="st-${s.key}">${esc(s.name)}</a></td><td class="l hm">${esc(STYPE[s.key]||'')}</td><td>${stBadge(s,P)}</td><td class=l>${stShort(s.ins_stats)}</td><td><b>${(s.cands||[]).length}</b></td></tr>`;
  const ov=[...L.map(ovRow),
    ...(S5?[`<tr><td><a data-to="st-s5">${esc(S5.name)}</a></td><td class="l hm">${STYPE.s5}</td><td><span class=pill style="background:rgba(37,99,201,.1);color:#1c4fa8">驗證中</span></td><td class=l>${stShort(S5.ins_stats,1)}</td><td><b>${(G.screen||[]).filter(x=>x.pass).length}</b></td></tr>`]:[])];
  h+=sec('st-all','總覽','策略總覽','點策略名稱跳到該卡',`<div class=tw><table><thead><tr><th>策略</th><th class="l hm">類型</th><th>驗證進度</th><th class=l>樣本內（照規則）${gi('樣本內')}</th><th>候選</th></tr></thead><tbody>${ov.join('')}</tbody></table></div>`);
  for(const s of L){
    if(s.key==='s3'){h+=stCard(s,P,s3Vers(s)+s3Plan(s),s3Ev(s),moreS3(s));continue;}
    const ev=scanLine(s)+(s.ins_stats&&s.ins_stats.n?` 照規則做（含停損、扣成本）${s.ins_stats.n} 筆：平均每筆贏大盤 ${pctT(s.ins_stats.x)}、${f(s.ins_stats.w,0)}% 贏大盤。`:'');
    h+=stCard(s,P,candS(s),ev,moreS(s));
  }
  h+=vGrow(P);
  const al=X.alerts||[],ag=((X.alert_scan||{}).grp||[])[0];
  const agT=ag?`樣本內 ${ag.n[0]} 筆：之後持有 1～${ag.x.length} 天，${ag.x.filter(v=>v!=null&&v<0).length} 個天數平均輸大盤（${pctT(Math.max(...ag.x.filter(v=>v!=null)))}～${pctT(Math.min(...ag.x.filter(v=>v!=null)))}）。`:'';
  h+=sec('st-obs','其他觀察','其他觀察','',`<div class=card><h4>跳空減碼提醒 <span class=pill>${al.length}</span></h4><div class=st>前一交易日「共識加碼」、今天開盤跳空 ≥3% 的股票：好處已在開盤被搶走。${agT}給已持有的人參考，不做放空。</div>`+
    (al.length?`<div class=inl style="margin-top:6px">${al.map(a=>`<span class=it><a data-c="${esc(a.c)}">${esc(a.n)}</a> <span class=mu>${md(a.d)} 開盤</span> ${sgn(a.gap,1,'%')}</span>`).join('　')}</div>`:'<div class=st style="margin-top:4px">今天沒有</div>')+`</div>`+
    hdAlertCard());
  h+=`<div class=note>部位與風控（所有策略共用）：單筆虧損（停損距離×張數）≤ 總資金 0.5%、單筆 ≤ 5%；只做 20 日均成交值 ≥1 億、張數 ≤ 20 日均量 2%；同時 ≤8 檔、同產業 ≤3 檔；注意股／處置股不碰。持有少於 3 天時優勢容易被成本吃掉。</div>`;
  $('#main').innerHTML=h;
  $$('#main [data-to]').forEach(a=>a.onclick=()=>jump(a.dataset.to));
}

/* ---------- 長線：投信動能成長股（S5） ---------- */
function gRow(lbl,g){if(!g||!g.n)return `<tr><td>${lbl}</td><td colspan=8 class=mu>無樣本</td></tr>`;
  const r=(x)=>x&&x[0]!=null?`${f(x[0],1)}%<span class=mu>（${x[1]}）</span>`:'—';
  return `<tr><td>${lbl}</td><td>${g.n}</td><td>${r(g.dbl6)}</td><td>${r(g.dbl12)}</td><td>${g.end6&&g.end6[0]!=null?sgn(g.end6[0],1,'%')+'／'+sgn(g.end6[1],1,'%'):'—'}</td><td>${g.rule?sgn(g.rule[0],1,'%')+'／'+sgn(g.rule[1],1,'%'):'—'}</td><td>${g.rule_w==null?'—':g.rule_w+'%'}</td><td>${g.rule_aw==null?'—':sgn(g.rule_aw,1,'%')+'／'+sgn(g.rule_al,1,'%')}</td><td>${g.rule_big==null?'—':f(g.rule_big,1)+'%'}</td></tr>`;}
function planS5(S5,x,scr){const ds=S5.dist||{},px=x.px;
  let b=(px?pcRow('停損',`約 <b>${fp(px*0.8)}</b>（−20%）`):'')+pastRow(ds,px);
  const w=[];if(x.trust!=null)w.push(`投信 20 日買超占股本 ${f(x.trust,2)}%${x.tdays!=null?`（買 ${x.tdays} 天）`:''}${x.etf2?'、主動 ETF 多家建倉':''}`);
  if(x.yoy!=null)w.push(`營收年增 ${f(x.yoy,0)}%、累計 ${f(x.cyoy,0)}%`);if(x.rs!=null)w.push(`半年漲幅強於 ${x.rs}% 的股票`);
  return `<div class=pc>${pcHead(x,px)}${b}${w.length?`<div class=pcw><b>入選</b>${w.join('；')}</div>`:''}</div>`;}
function vGrow(P){
  const G=D.grow||{};if(G.err)return sec('st-s5','長線','長線：投信動能成長股','',`<div class=card><div class=st>錯誤：${esc(G.err)}</div></div>`);
  const B=G.bt||{};const ms=B.months||[];const S5=G.s5;if(!S5)return '';
  const sc=G.screen||[];const ok=sc.filter(x=>x.pass),near=sc.filter(x=>!x.pass);const scr=S5.screen_d;
  const dd=k=>(B[k]||{}).dbl6,pc=x=>x&&x[0]!=null?`${f(x[0],0)}%`:'—';
  const ym=d=>`${d.slice(0,4)}/${+d.slice(5,7)}`;
  const ev=(dd('trust_mom')?`回測（${ms.length?`${ym(ms[0])}～${ym(ms[ms.length-1])} `:'近兩年'}每月篩一次）：投信＋動能篩出的股票，6 個月內曾翻倍 <b>${pc(dd('trust_mom'))}</b>（${(dd('trust_mom')||[])[1]} 檔次）；只看動能 ${pc(dd('mom'))}、全部股票 ${pc(dd('base'))}。`:'')+
    (S5.ins_stats&&S5.ins_stats.n?`照規則做的 ${S5.ins_stats.n} 筆：平均 ${pctT(S5.ins_stats.avg)}、中位 ${pctT(S5.ins_stats.med)}、${S5.ins_stats.win}% 賺錢。`:'');
  const how=`${scr?`${md(scr[0])}（本月最後一個交易日）收盤後仍四關全過才進場，${md(scr[1])} 開盤買`:'月底收盤後仍四關全過才進場，隔天開盤買'}（開高 ≥3% 不追）；跌破進場價 −20% 停損，之後從最高收盤回落 30% 出場。以下是今天的篩選結果：`;
  const cand=sq('本月候選',`<div class=pcn>${how}</div>`+(ok.length?`<div class=pcs>${ok.map(x=>planS5(S5,x,scr)).join('')}</div><div class=note>${pastNote(S5.dist)}</div>`:'<span class=mu>今天沒有四關全過的股票</span>'));
  const ck=v=>v?'<span class=up>✓</span>':'<span class=mu>✗</span>';
  const scRow=x=>`<tr data-c="${esc(x.c)}" class="${x.pass?'':'grey'}"><td><span class=nm>${esc(x.n)}</span><span class=cd>${esc(x.c)}</span></td><td class=l>${ck(x.g_trust)} ${x.trust==null?'':f(x.trust,2)+'% 股本'}${x.tdays!=null?'・買 '+x.tdays+' 日':''}${x.etf2?' <span class=sg>主動 ETF 多家建倉</span>':''}</td><td class=l>${ck(x.g_grow)} ${x.yoy==null?'':'年增 '+f(x.yoy,0)+'%'}${x.cyoy==null?'':'・累計 '+f(x.cyoy,0)+'%'}</td><td class=l>${ck(x.g_mom)} ${x.rs==null?'':'強度前 '+(100-x.rs)+'%'}</td><td>${f(x.cap,0)}</td><td>${f(x.liq,1)}</td></tr>`;
  const scHead=`<thead><tr><th>股票</th><th class=l>投信關</th><th class=l>成長關</th><th class=l>動能關</th><th>市值(億)</th><th>日均成交(億)</th></tr></thead>`;
  let m=`<h4 class=sh>四關定義</h4><ul class=doc style="margin:4px 0">
<li class=st><b>投信關</b>：投信 20 日買超 ≥ 股本 0.5%，且 20 天中 ≥12 天買超（今日篩選另認：主動 ETF 20 日內 ≥2 家投信新建倉、且投信整體 20 日未淨賣）</li>
<li class=st><b>成長關</b>：最新月營收年增 ≥20%、累計年增 ≥15%</li>
<li class=st><b>動能關</b>：收盤 > 60 日線 > 120 日線、60 日線上揚、距 120 日高點 20% 內、比低點高 30% 以上、120 日報酬全市場前 30%</li>
<li class=st><b>空間關</b>：市值 50～1,500 億、20 日均成交值 ≥1 億</li></ul>`;
  const ds=S5.dist||{};if(ds.n)m+=`<h4 class=sh>照規則做的結果（樣本內 ${ds.n} 筆已出場）</h4><div class=st>${distTxt(ds,false)}</div><div class=st>${moTxt(ds)}</div>`;
  if((S5.more||[]).length)m+=`<div class=st style="margin-top:6px">${S5.more.map(esc).join('<br>')}</div>`;
  m+=`<h4 class=sh>完整規則 <span class=pill>v${S5.ver}・${md(S5.since)} 起算</span></h4><div class=rls>${ruleRows(S5.rule||[])}<div class=rl><span class=rlk>驗證</span><span>${esc(S5.pass)}</span></div></div>`;
  if(near.length)m+=`<details class=mr><summary>今日篩選：差一關 ${near.length} 檔</summary><div class=tw><table>${scHead}<tbody>${near.map(scRow).join('')}</tbody></table></div></details>`;
  const fw=(S5.fwd||[]).slice().reverse(),ins=(S5.ins||[]).slice().reverse();
  if(fw.length)m+=`<h4 class=sh>紙上交易紀錄（${fw.length} 筆）</h4>${tradeTbl(fw,true)}`;
  if(ins.length)m+=`<details class=mr><summary>樣本內交易 ${ins.length} 筆：${st5(S5.ins_stats)}</summary><div class=note>成績集中在趨勢明確的月份，盤整月份多為 −20% 停損——這是動能策略的常態。</div>${tradeTbl(ins,true)}</details>`;
  let bt=`<div class=note>「曾翻倍」＝進場後 6／12 個月內最高價曾達進場價 2 倍（括號＝前瞻期完整的樣本數）；「照規則」＝照舊版停損／移動出場做出來的報酬（已扣成本）。基準＝同期所有通過「空間關」的股票。宇宙只含現存上市櫃股，結果偏樂觀；兩年資料大致是多頭。</div>
<div class=tw><table><thead><tr><th>組別</th><th>篩出檔次</th><th>6 個月內曾翻倍</th><th>12 個月內曾翻倍</th><th>6 個月期末 平均／中位</th><th>照規則 平均／中位</th><th>勝率</th><th>平均賺／平均賠</th><th>照規則翻倍比例</th></tr></thead><tbody>`+
    gRow('基準（空間關）',B.base)+gRow('只看動能',B.mom)+gRow('只看投信',B.trust)+gRow('投信＋動能',B.trust_mom)+gRow('四關全過',B.all4)+`</tbody></table></div>`;
  const EX=B.exits||{},EL=B.exit_lbl||{};
  if(EX.trust_mom){bt+=`<h4 class=sh>出場方式比較</h4><div class=note>同一檔 6 個月內只算一次、只計前瞻滿 6 個月者</div><div class=tw><table><thead><tr><th>出場方式</th><th>組別</th><th>筆數</th><th>平均</th><th>中位</th><th>勝率</th><th>平均賺／賠</th><th>翻倍比例</th><th>平均持有</th></tr></thead><tbody>`;
    for(const ek of Object.keys(EL)){for(const [gk,gl] of [['trust_mom','投信＋動能'],['mom','只看動能'],['base','基準']]){const x=(EX[gk]||{})[ek]||{};if(!x.n)continue;
      bt+=`<tr class="${gk==='trust_mom'?'':'grey'}"><td>${gk==='trust_mom'?esc(EL[ek]):''}</td><td>${gl}</td><td>${x.n}</td><td>${sgn(x.avg,1,'%')}</td><td>${sgn(x.med,1,'%')}</td><td>${x.win}%</td><td>${x.aw==null?'—':sgn(x.aw,1,'%')}／${x.al==null?'—':sgn(x.al,1,'%')}</td><td>${f(x.dbl,1)}%</td><td>${x.days} 日</td></tr>`;}}
    bt+=`</tbody></table></div>`;}
  if((B.top||[]).length)bt+=`<div class=st style="margin-top:6px">歷史篩出、漲最多的：`+B.top.slice(0,8).map(x=>`${esc(x[1])}（${md(x[2])} 篩出，最高 +${x[3]}%${x[4]!=null?'，照規則 '+(x[4]>0?'+':'')+x[4]+'%':''}）`).join('、')+`</div>`;
  m+=`<details class=mr><summary>回測細節：翻倍比較、出場方式</summary>${bt}</details>`;
  return stCard({...S5,nav:'長線',status:'驗證中',fwd_stats:S5.fwd_stats||{}},P||[30,30],cand,ev,m).replace(/驗證中 \d+／\d+ 筆/,'驗證中');
}

/* ---------- 個股走勢序列（x9s.json：開個股卡才載入，電腦閒置時預先抓） ---------- */
let SER=null,SERD=[],SERST='idle',SERP=null;
function loadSer(){if(SERP)return SERP;SERST='loading';
  SERP=fetch('x9s.json?v='+encodeURIComponent(D.serv||'')).then(r=>{if(!r.ok)throw new Error('HTTP '+r.status);return r.json();})
    .then(j=>{SER=j.ser||{};SERD=j.dates||[];SERST='ok';return SER;},e=>{SERST='err';SERP=null;throw e;});
  return SERP;}
function reStock(c){if(!$('#dv').hidden&&decodeURIComponent((location.hash.match(/^#s=(.+)$/)||[])[1]||'')===c)renderStock(c,true);}

/* ---------- 個股卡（電腦：右側面板、不遮表格；手機：全螢幕） ---------- */
let CTX=[],PUSHED=false;
function isPane(){return matchMedia('(min-width:1100px)').matches;}
function ctxOf(a){if(a.closest('#stkt'))return STK.slice();const box=a.closest('.sec')||a.closest('.card')||$('#main');const out=[];
  box.querySelectorAll('[data-c]').forEach(e=>{const c=e.dataset.c;if(BY[c]&&!out.includes(c))out.push(c);});return out;}
function openStock(c){if(!$('#dv').hidden){history.replaceState(null,'','#s='+encodeURIComponent(c));renderStock(c);return;}
  PUSHED=true;location.hash='s='+encodeURIComponent(c);}
function lockBody(on){document.body.style.overflow=on?'hidden':'';}
function hideStock(){$('#dv').hidden=true;$('#dv').classList.remove('pane');document.body.classList.remove('pane');lockBody(!$('#gl').hidden);}
function closeStock(){if(PUSHED&&location.hash.startsWith('#s=')){PUSHED=false;history.back();}else{history.replaceState(null,'',location.pathname+location.search);hideStock();}}
function stepStock(d){const c=decodeURIComponent((location.hash.match(/^#s=(.+)$/)||[])[1]||'');const i=CTX.indexOf(c);const t=CTX[i+d];if(i>=0&&t)openStock(t);}
window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#s=(.+)$/);if(m)renderStock(decodeURIComponent(m[1]));else hideStock();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!POP.hidden){hidePop();return;}if(!$('#gl').hidden)closeGl();else if(!$('#dv').hidden)closeStock();return;}
  if($('#dv').hidden||!$('#gl').hidden||/INPUT|SELECT|TEXTAREA/.test((e.target||{}).tagName||''))return;
  if(e.key==='ArrowLeft'){e.preventDefault();stepStock(-1);}else if(e.key==='ArrowRight'){e.preventDefault();stepStock(1);}});
$('#dv').addEventListener('click',e=>{if(e.target.id==='dv'&&!$('#dv').classList.contains('pane'))closeStock();});
let RSZ=0;addEventListener('resize',()=>{clearTimeout(RSZ);RSZ=setTimeout(()=>{const m=location.hash.match(/^#s=(.+)$/);if(m&&!$('#dv').hidden)renderStock(decodeURIComponent(m[1]),true);},250);});

function gp(k,t='。'){return `<span class=nw>${gi(k)}${t}</span>`;}
function nameList(a,n=4){return a.length<=n?a.join('、'):a.slice(0,n).join('、')+` 等 ${a.length} 家`;}
function cls(x){return x>0?'up':x<0?'dn':'';}
function pm(x,d=0){return x==null?'—':(x>0?'+':'')+f(x,d);}
function sumLines(r){const tw=r.m!=='os',u=tw?'張':'股',L=[];const ia=r.ia5||[],ic=r.ic5||[],nb=issOf(r.nb10);
  L.push(r.ne?`<b>${r.ne} 檔 ETF</b> 持有（主動 ${r.na}、被動 ${r.np}）${tw&&r.hp!=null?`，合計占發行股數 <b>${f(r.hp,2)}%</b>`:''}${tw&&r.dx!=null?`，約等於 ${f(r.dx,1)} 天成交量${gp('消化天數')}`:'。'}`:'目前沒有追蹤中的 ETF 持有。');
  L.push((r.a5||ia.length||ic.length?`主動 ETF 近 5 日<b class=${cls(r.a5)}>淨${(r.a5||0)>=0?'買':'賣'} ${f(Math.abs(r.a5||0),0)} ${u}</b>${gi('真加碼')}${r.a5v!=null?`（約 ${f(Math.abs(r.a5v),1)} 億）`:''}${ia.length?`：${esc(nameList(ia))}加碼`:''}${ic.length?`${ia.length?'；':'：'}${esc(nameList(ic))}減碼`:''}。`:'主動 ETF 近 5 日沒有真加減碼。')+
    (nb.length?`10 日內新建倉：<b>${esc(nb.join('、'))}</b>。`:''));
  if(r.cost!=null&&r.dev!=null)L.push(`近期新建倉的主動 ETF（${r.cn} 檔）平均買在 <b>${fp(r.cost)}</b>${gp('主動成本','，')}現價${r.dev>=0?'高':'低'} <b class=${cls(r.dev)}>${f(Math.abs(r.dev),1)}%</b>`+
    (tw&&r.ow!=null?`；平均權重比市值權重${r.ow>=0?'高':'低'} ${f(Math.abs(r.ow),2)} 個百分點${r.now!=null?`（${r.now}／${r.nact} 家投信超配）`:''}${gp('超配')}`:'。'));
  if(tw&&r.t5!==undefined)L.push(`法人：投信${r.ts?`連${r.ts>0?'買':'賣'} ${Math.abs(r.ts)} 日、`:''}5 日 ${sgn(r.t5,0)} 張；外資${r.fs?`連${r.fs>0?'買':'賣'} ${Math.abs(r.fs)} 日、`:''}5 日 ${sgn(r.f5,0)} 張${r.mb5!=null&&Math.abs(r.mb5)>=10?`；融資 5 日 ${sgn(r.mb5,1,'%')}`:''}。`);
  if(tw&&r.al)L.push(`技術面<b>${r.al}</b>${r.h60?'、創 60 日新高':r.h20?'、創 20 日新高':r.l20?'、跌破 20 日低點':''}${r.p52!=null?`；在一年區間的 ${f(r.p52,0)}% 位置`:''}${r.rs20!=null?`，近 20 日${r.rs20>=0?'強於':'弱於'}大盤 ${f(Math.abs(r.rs20),1)} 個百分點`:''}。`);
  return L;}
function kp(lbl,g,val,sub,c=''){return `<div class=kp><span>${lbl}${g?gi(g):''}</span><b class="${c}">${val}</b>${sub?`<em>${sub}</em>`:''}</div>`;}
function kpis(r){const tw=r.m!=='os';const k=[
  kp('持有 ETF','持有 ETF',`${r.ne} 檔`,`主動 ${r.na}・被動 ${r.np}`),
  kp('主動 5 日淨買','主動 5 日淨買',tw&&r.a5v!=null?`${pm(r.a5v,1)} 億`:`${pm(r.a5)} ${tw?'張':'股'}`,`${(r.ia5||[]).length} 家加・${(r.ic5||[]).length} 家減`,cls(r.a5)),
  kp('成本乖離','成本乖離',r.dev==null?'—':pm(r.dev,1)+'%',r.cost==null?'無近期新建倉':`新建倉成本 ${fp(r.cost)}`,cls(r.dev))];
  if(tw&&r.t5!==undefined)k.push(kp('投信 5 日','投信 5 日',pm(r.t5)+' 張',r.ts?`連${r.ts>0?'買':'賣'} ${Math.abs(r.ts)} 日`:'',cls(r.t5)),
    kp('外資 5 日','外資 5 日',pm(r.f5)+' 張',r.fs?`連${r.fs>0?'買':'賣'} ${Math.abs(r.fs)} 日`:'',cls(r.f5)),
    kp('技術','趨勢',r.al||'—',r.rsi!=null?`RSI ${f(r.rsi,0)}`:'',r.al==='多頭'?'up':r.al==='空頭'?'dn':''));
  return k.join('');}
function holdTbl(rows,tw){const u=tw?'張':'股';
  return `<div class=tw><table class=hdt><thead><tr><th>ETF</th><th>權重</th><th>${u}數</th><th>建倉${gi('建倉日')}</th><th>成本・損益${gi('主動成本')}</th><th>5 日真加減${gi('真加碼')}</th><th class=l>最近動作</th></tr></thead><tbody>`+
   rows.map(x=>{const m=E[x[0]]||{};return `<tr><td><span class=nm>${esc(x[0])}</span><span class=cd>${esc(m.is||'')}${m.k==='p'?' · 被動':''}${m.x?' · 擴充':''}</span></td><td>${f(x[1],2)}%</td><td>${f(x[2],tw?0:0)}</td><td>${x[3]?(x[4]?'':'≤')+md(x[3]):'—'}<br><span class=mu>${x[5]==null?'':x[5]+' 日'}</span></td><td>${x[6]==null?`<span class=mu>${x[12]==='B'?'舊部位':'—'}</span>`:fp(x[6])+'<br>'+sgn(x[7],1,'%')}</td><td>${sgn(x[8],0)}</td><td class=l>${x[9]?`<span class="k-${x[9]}">${KN[x[9]]}</span> <span class=mu>${md(x[10])}</span>${Math.abs(x[11])>=2?` <span class=pill>連 ${Math.abs(x[11])}</span>`:''}`:'<span class=mu>—</span>'}</td></tr>`;}).join('')+`</tbody></table></div>`;}
function idxHits(c){
  const t=(D.idx||{}).tw50||{};const hits=[];
  const lab={adds:'預估納入臺灣50',dels:'預估自臺灣50 刪除',watch_in:'臺灣50 邊緣（可能升入）',watch_out:'臺灣50 邊緣（可能跌出）'};
  for(const k of Object.keys(lab)){const r=(t[k]||[]).find(x=>x[0]===c);if(r)hits.push(kp(lab[k],'',`第 ${r[2]} 名`,`${r[4]===0?'已跨線':'還差 '+f(r[4],1)+'%'}${r[5]!=null?'・機率 '+r[5]+'%':''}${r[6]!=null?'・被動 '+pm(r[6])+' 張（'+f(r[7],1)+' 日量）':''}`));}
  const HL=((D.idx||{}).hd||{}).live||{};
  for(const k of HDK){const v=HL[k];if(!v||v.err)continue;
    const a=(v.adds||[]).find(x=>x[0]===c),d=(v.dels||[]).find(x=>x[0]===c);
    if(a)hits.push(kp(`預估納入 ${HDE[k]}`,'被動買賣期間',a[2]?`殖利率第 ${a[2]} 名`:'—',`${v.review||''} 換股${a[5]!=null?`・估計被動買 ${f(a[5],1)} 億`:''}${a[6]!=null?`（${f(a[6],1)} 日量）`:''}`,'up'));
    if(d)hits.push(kp(`預估自 ${HDE[k]} 刪除`,'被動買賣期間',d[2]?`殖利率第 ${d[2]} 名`:'不合格',`${v.review||''} 換股`,'dn'));}
  const HA=((D.idx||{}).hd||{}).alert||{};
  for(const r of (HA.rows||[]))if(r[0]===c&&r[11]==='官方'&&r[6]!=null)hits.push(kp(`${esc(r[2])} 換股${r[4]==='add'?'納入':'刪除'}`,'被動買賣提醒',`約 ${f(r[6],0)} 日量`,`被動${r[4]==='add'?'買':'賣'} ${f(r[5],0)} 億・${md(r[7])}～${md(r[8])}${r[6]>=(HA.big_th||HDB)?`・之後避開到 ${md(r[9])}`:''}`,r[4]==='add'?'up':'dn'));
  const pf=((D.idx||{}).pflow||[]).find(x=>x[0]===c);
  if(pf)hits.push(kp('被動 ETF 近 10 日淨買賣','',pm(pf[2])+' 張',`${pf[3]!=null?'約 '+f(pf[3],2)+' 日量':''}${(pf[4]||[]).length?'・新進 '+pf[4].join(' '):''}${(pf[5]||[]).length?'・出清 '+pf[5].join(' '):''}`,cls(pf[2])));
  return hits.join('');}

function renderStock(c,keep){
  const r=BY[c];if(!r){hideStock();return;}const s=SER?(SER[c]||{}):null;const tw=r.m!=='os';const u=tw?'張':'股';
  if(!SER&&SERST!=='err')loadSer().then(()=>reStock(c),()=>reStock(c));
  const dv=$('#dv'),pane=isPane(),st0=keep?dv.scrollTop:0;
  dv.classList.toggle('pane',pane);document.body.classList.toggle('pane',pane);dv.hidden=false;lockBody(!pane);
  const W=Math.max(300,Math.floor($('#dvin').clientWidth-32));
  const i=CTX.indexOf(c),pv=i>0,nx=i>=0&&i<CTX.length-1;
  const secs=[['c-sum','重點'],['c-chart','走勢'],['c-hold','ETF 持有'],...(tw&&r.t5!==undefined?[['c-chip','籌碼'],['c-ta','技術']]:[]),['c-sig','訊號']];
  let h=`<div class=dvh><div class=dvt><a class="nv${pv?'':' off'}" id=pv title="上一檔（←）">‹</a>`+
   `<div class=ttl><b>${esc(r.n)}</b><span class=cd>${i>=0?`${i+1}／${CTX.length} · `:''}${esc(r.c)} · ${MK[r.m]||''}${r.ind?' · '+esc(r.ind):''}</span></div>`+
   `<div class=pxw><b>${fp(r.px)}</b>${sgn(r.ch,2,'%')}</div><a class="nv${nx?'':' off'}" id=nx title="下一檔（→）">›</a><a class=x id=x title="關閉（Esc）">×</a></div>`+
   `<nav class=cnav>${secs.map(([id,t])=>`<a data-cto=${id}>${t}</a>`).join('')}</nav></div>`;
  h+=`<section class=csec id=c-sum><div class=sgrow>${sgChips(r.sg)||'<span class=st>今日無觸發訊號</span>'}</div><ul class=sum>${sumLines(r).map(x=>`<li>${x}</li>`).join('')}</ul><div class=kpis>${kpis(r)}</div></section>`;
  const lastD=(D.dates||[]).slice(-1)[0],serD=SERD.slice(-1)[0];
  if(!s)h+=`<section class=csec id=c-chart><h3>走勢</h3><div class=ld>${SERST==='err'?'走勢資料暫時無法載入　<a id=serr>重試</a>':'走勢載入中…'}</div></section>`;
  else if(s.c&&s.c.some(x=>x!=null))h+=`<section class=csec id=c-chart><h3>走勢<span class=sub>近 ${s.c.length} 個交易日・游標移到圖上看每日數字</span></h3>${serD&&lastD&&serD<lastD?`<div class=note>走勢資料到 ${md(serD)}（尚未更新到最新）</div>`:''}<div class=cw id=kc>${chart(s,r,W)}</div>`+
   `<div class=lg><span><i style="background:#2563c9"></i>20 日線</span><span><i style="background:#f59e0b"></i>60 日線</span><span><i class=dsh></i>主動 ETF 新建倉成本</span><span><b class=up>▲</b> 主動 ETF 新建倉</span><span><b class=dn>▼</b> 出清</span>${s.qa?'<span>下方長條＝主動 ETF 每日真加減碼（已扣申贖）</span>':''}</div></section>`;
  const act=(r.hd||[]).filter(x=>(E[x[0]]||{}).k==='a').sort((a,b)=>(b[1]||0)-(a[1]||0));
  const pas=(r.hd||[]).filter(x=>(E[x[0]]||{}).k!=='a').sort((a,b)=>(b[1]||0)-(a[1]||0));
  h+=`<section class=csec id=c-hold><h3>ETF 持有<span class=sub>主動 ${act.length}・被動 ${pas.length}・合計 ${f(r.sh,0)} ${u}</span></h3>`+
   (act.length?holdTbl(act.slice(0,10),tw)+(act.length>10?`<details class=mr><summary>其餘主動 ${act.length-10} 檔</summary>${holdTbl(act.slice(10),tw)}</details>`:''):'<div class=st>沒有主動 ETF 持有</div>')+
   (pas.length?`<div class=pasl><b>被動 ${pas.length} 檔：</b>${pas.slice(0,8).map(x=>`${esc(x[0])} <span class=mu>${f(x[1],2)}%</span>`).join('、')}${pas.length>8?' 等':''}</div><details class=mr><summary>被動明細</summary>${holdTbl(pas,tw)}</details>`:'')+
   ((r.ex||[]).length?`<div class=st style="margin-top:6px">近期出清：${r.ex.map(x=>`${esc(x[0])}（${md(x[1])}）`).join('、')}</div>`:'')+`</section>`;
  if(tw&&r.f5!==undefined){
    h+=`<section class=csec id=c-chip><h3>籌碼</h3><div class="kpis kps">`+
     kp('外資 5 日','外資 5 日',pm(r.f5)+' 張',`1 日 ${pm(r.f1)}・20 日 ${pm(r.f20)}${r.fs?`・連${r.fs>0?'買':'賣'} ${Math.abs(r.fs)} 日`:''}`,cls(r.f5))+
     kp('投信 5 日','投信 5 日',pm(r.t5)+' 張',`1 日 ${pm(r.t1)}・20 日 ${pm(r.t20)}${r.ts?`・連${r.ts>0?'買':'賣'} ${Math.abs(r.ts)} 日`:''}`,cls(r.t5))+
     kp('自營商 5 日','',pm(r.d5)+' 張','',cls(r.d5))+
     kp('投信 60 日買超均價','60 日買超均價',r.tc==null?'—':fp(r.tc),r.tc&&r.px?`現價 ${pm((r.px/r.tc-1)*100,1)}%`:'')+
     kp('外資 60 日買超均價','60 日買超均價',r.fc==null?'—':fp(r.fc),r.fc&&r.px?`現價 ${pm((r.px/r.fc-1)*100,1)}%`:'')+
     kp('投信 20 日買超占股本','',r.t20p==null?'—':pm(r.t20p,3)+'%','',cls(r.t20p))+
     (r.fp!=null?kp('外資持股比','',f(r.fp,2)+'%',`20 日 ${pm(r.fpd,2)}pp`):'')+
     kp('融資餘額','融資',r.mb==null?'—':f(r.mb,0)+' 張',`5 日 ${pm(r.mb5,1)}%・20 日 ${pm(r.mb20,1)}%`)+
     kp('融券餘額','',r.sb==null?'—':f(r.sb,0)+' 張',r.sr!=null?`券資比 ${f(r.sr,1)}%`:'')+
     (r.lb!=null?kp('借券賣出餘額','借券賣出',f(r.lb,0)+' 張',`5 日 ${pm(r.lb5)}`):'')+
     (r.big!=null?kp('千張大戶','千張大戶',f(r.big,2)+'%',r.bigd!=null?`週變化 ${pm(r.bigd,2)}pp`:'每週公布'):'')+
     (r.hold!=null?kp('股東人數','',f(r.hold,0),r.holdd!=null?`週 ${pm(r.holdd)}`:''):'')+`</div>`;
    if(s&&s.qf)h+=`<div class=note style="margin-top:10px">每日買賣超（張），近 ${s.qf.length} 個交易日</div>${bars(s.qf,W,'外資')}${bars(s.qt,W,'投信')}`;
    h+=`</section>`;
  }
  if(tw&&r.al!==undefined){const ma=r.ma||{};
    h+=`<section class=csec id=c-ta><h3>技術面</h3><div class="kpis kps k3">`+
     kp('均線排列','趨勢',r.al||'—',['5','20','60'].filter(k=>ma[k]!=null).map(k=>`${k} 日 ${fp(ma[k])}`).join('・'),r.al==='多頭'?'up':r.al==='空頭'?'dn':'')+
     kp('20 日乖離','乖離',pm(r.b20,1)+'%',`60 日 ${pm(r.b60,1)}%`,cls(r.b20))+
     kp('量比','量比',r.vr==null?'—':f(r.vr,2)+' 倍','今日 ÷ 20 日均量')+
     kp('KD(9)','KD',`${f(r.k,0)}／${f(r.d,0)}`)+kp('RSI(14)','RSI',f(r.rsi,0))+
     kp('MACD 柱','MACD',pm(r.mh,2),r.mx===1?'剛翻正':r.mx===-1?'剛翻負':'',cls(r.mh))+
     kp('突破','',[r.h20?'創 20 日高':'',r.h60?'創 60 日高':'',r.l20?'破 20 日低':''].filter(Boolean).join('、')||'—')+
     kp('一年區間位置','一年區間位置',r.p52==null?'—':f(r.p52,0)+'%',r.n52<240?`僅 ${r.n52} 日資料`:'')+
     kp('20 日相對大盤','相對大盤',pm(r.rs20,1)+'pp','',cls(r.rs20))+
     kp('ATR 波動','ATR',r.atrp==null?'—':f(r.atrp,2)+'%')+
     kp('日均成交','日均成交',r.liq==null?'—':f(r.liq,2)+' 億','20 日')+`</div></section>`;}
  const ih=idxHits(c);
  h+=`<section class=csec id=c-sig><h3>訊號與指數</h3>`+((r.sg||[]).length?(r.sg||[]).map(k=>`<div class=sgi><b>${RISK.has(k)?'⚠ ':''}${esc((SD[k]||[k])[0])}</b><div class=st>${esc((SD[k]||['',''])[1])}</div>${statLine(k)}</div>`).join(''):'<div class=st>今日沒有觸發訊號。</div>')+
   (ih?`<div class="kpis kps" style="margin-top:10px">${ih}</div>`:'')+`</section>`;
  $('#dvin').innerHTML=h;dv.scrollTop=st0;
  $('#x').onclick=closeStock;$('#pv').onclick=()=>stepStock(-1);$('#nx').onclick=()=>stepStock(1);
  const rb=$('#serr');if(rb)rb.onclick=()=>{SERST='idle';renderStock(c,true);};
  $$('#dvin [data-cto]').forEach(a=>a.onclick=()=>{const t=document.getElementById(a.dataset.cto);if(t)dv.scrollTo({top:dv.scrollTop+t.getBoundingClientRect().top-dv.getBoundingClientRect().top-$('#dvin .dvh').offsetHeight+2,behavior:'smooth'});});
  cspy();bindTip(c);
}
function cspy(){const dv=$('#dv');if(dv.hidden)return;const hh=$('#dvin .dvh');if(!hh)return;const y=hh.getBoundingClientRect().bottom+8;let cur=null;
  $$('#dvin .csec').forEach(s=>{if(s.getBoundingClientRect().top<=y)cur=s.id;});if(!cur){const f0=$('#dvin .csec');cur=f0&&f0.id;}
  if(dv.scrollTop+dv.clientHeight>=dv.scrollHeight-4){const all=$$('#dvin .csec');cur=all.length?all[all.length-1].id:cur;}
  $$('#dvin [data-cto]').forEach(a=>a.classList.toggle('on',a.dataset.cto===cur));}
$('#dv').addEventListener('scroll',()=>requestAnimationFrame(cspy),{passive:true});

/* ---------- 圖（以實際像素寬繪製，手機字不會縮小） ---------- */
function rng(arrs){let lo=Infinity,hi=-Infinity;arrs.forEach(a=>(a||[]).forEach(v=>{if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v);}}));if(lo===Infinity)return [0,1];if(lo===hi){lo*=.98;hi*=1.02;}return [lo,hi];}
function sma(a,n){const o=[];let s=0,q=[];for(const v of a){if(v==null){o.push(null);continue;}q.push(v);s+=v;if(q.length>n)s-=q.shift();o.push(q.length===n?s/n:null);}return o;}
function path(a,x,y){let d='',pen=false;a.forEach((v,i)=>{if(v==null){pen=false;return;}d+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);pen=true;});return d;}
function mkrs(r,n){const ds=SERD.slice(-n),ix={},M={};ds.forEach((d,i)=>ix[d]=i);
  for(const x of (r.hd||[])){const m=E[x[0]]||{};if(m.k!=='a'||!x[4]||!x[3]||ix[x[3]]==null)continue;(M[ix[x[3]]]=M[ix[x[3]]]||{n:[],x:[]}).n.push(x[0]);}
  for(const x of (r.ex||[])){const m=E[x[0]]||{};if(m.k!=='a'||ix[x[1]]==null)continue;(M[ix[x[1]]]=M[ix[x[1]]]||{n:[],x:[]}).x.push(x[0]);}
  return M;}
function qaOf(s){if(!s.qa||!s.c)return null;const n=s.c.length,off=n-s.qa.length;return Array.from({length:n},(_,i)=>i<off?null:s.qa[i-off]);}
let CH=null;
function chart(s,r,W){
  const n=s.c.length,pl=4,pr=50,G=10;const c=s.c,o=s.o||c,hi=s.h||c,lo=s.l||c;const qa=qaOf(s);
  const HA=W<520?190:230,HB=s.v?42:0,HC=qa?64:0,HX=18;const yB=HA+G,yC=yB+HB+(HB?G:0),H=yC+HC+HX;
  const x=i=>pl+(i+.5)*(W-pl-pr)/n,cw=Math.max(1,(W-pl-pr)/n*.62);
  const [a,b]=rng([hi,lo,s.ac]);const ya=v=>8+(HA-22)*(1-(v-a)/(b-a));
  let g='';
  for(const t of [a,(a+b)/2,b]){const yy=ya(t).toFixed(1);g+=`<line x1=${pl} x2=${W-pr} y1=${yy} y2=${yy} stroke="#eef1f5"/><text x=${W-pr+6} y=${(+yy+4).toFixed(0)} font-size=11 fill="#727e8c">${fp(t)}</text>`;}
  for(let i=0;i<n;i++){if(c[i]==null)continue;const up=c[i]>=(o[i]??c[i]);const col=up?'#d33a34':'#1f9d57';
    g+=`<line x1=${x(i).toFixed(1)} x2=${x(i).toFixed(1)} y1=${ya(hi[i]??c[i]).toFixed(1)} y2=${ya(lo[i]??c[i]).toFixed(1)} stroke="${col}" stroke-width=1 />`;
    const t=ya(Math.max(o[i]??c[i],c[i])),bt=ya(Math.min(o[i]??c[i],c[i]));g+=`<rect x=${(x(i)-cw/2).toFixed(1)} y=${t.toFixed(1)} width=${cw.toFixed(1)} height=${Math.max(1,bt-t).toFixed(1)} fill="${col}"/>`;}
  g+=`<path d="${path(sma(c,20),x,ya)}" fill=none stroke="#2563c9" stroke-width=1.4 /><path d="${path(sma(c,60),x,ya)}" fill=none stroke="#f59e0b" stroke-width=1.4 />`;
  if(s.ac)g+=`<path d="${path(s.ac,x,ya)}" fill=none stroke="#a16207" stroke-width=1.8 stroke-dasharray="5 4" />`;
  const M=mkrs(r,n);
  for(const [k,m] of Object.entries(M)){const xx=x(+k);if(m.n.length)g+=`<path d="M${(xx-5).toFixed(1)} ${HA-3} L${(xx+5).toFixed(1)} ${HA-3} L${xx.toFixed(1)} ${HA-11} Z" fill="#d33a34"/>`;
    if(m.x.length)g+=`<path d="M${(xx-5).toFixed(1)} ${HA-13} L${(xx+5).toFixed(1)} ${HA-13} L${xx.toFixed(1)} ${HA-5} Z" fill="#1f9d57"/>`;}
  if(s.v){const vm=Math.max(...s.v.filter(v=>v!=null),1);s.v.forEach((v,i)=>{if(v==null)return;const up=c[i]!=null&&c[i]>=(o[i]??c[i]);const hh=(HB-4)*v/vm;g+=`<rect x=${(x(i)-cw/2).toFixed(1)} y=${(yB+HB-hh).toFixed(1)} width=${cw.toFixed(1)} height=${hh.toFixed(1)} fill="${up?'#d33a34':'#1f9d57'}" opacity=.4 />`;});
    g+=`<text x=${pl+2} y=${yB+11} font-size=11 fill="#727e8c">成交量</text>`;}
  if(qa){const qm=Math.max(1,...qa.filter(v=>v!=null).map(Math.abs)),z=yC+HC/2,i0=qa.findIndex(v=>v!=null),bw=Math.max(1.5,cw);
    g+=`<rect x=${(x(i0)-cw).toFixed(1)} y=${yC} width=${(x(n-1)-x(i0)+2*cw).toFixed(1)} height=${HC} fill="#f7f9fc"/><line x1=${(x(i0)-cw).toFixed(1)} x2=${W-pr} y1=${z} y2=${z} stroke="#dfe4ec"/>`;
    qa.forEach((v,i)=>{if(!v)return;const hh=Math.max(1,(HC/2-4)*Math.abs(v)/qm);g+=`<rect x=${(x(i)-bw/2).toFixed(1)} y=${(v>0?z-hh:z).toFixed(1)} width=${bw.toFixed(1)} height=${hh.toFixed(1)} fill="${v>0?'#d33a34':'#1f9d57'}"/>`;});
    g+=`<text x=${pl+2} y=${yC+11} font-size=11 fill="#727e8c">主動 ETF 真加減碼（${r.m!=='os'?'張':'股'}・近 ${s.qa.length} 日）</text><text x=${W-pr+6} y=${yC+11} font-size=11 fill="#727e8c">+${f(qm,0)}</text><text x=${W-pr+6} y=${yC+HC-2} font-size=11 fill="#727e8c">−${f(qm,0)}</text>`;}
  const ds=SERD.slice(-n);
  for(const i of [0,Math.round((n-1)/3),Math.round(2*(n-1)/3),n-1])g+=`<text x=${x(i).toFixed(0)} y=${H-4} font-size=11 fill="#727e8c" text-anchor=${i===0?'start':i===n-1?'end':'middle'}>${md(ds[i]||'')}</text>`;
  CH={n,pl,pr,W,M,x};
  return `<svg width=${W} height=${H} viewBox="0 0 ${W} ${H}">${g}<line id=xh x1=0 x2=0 y1=0 y2=${H-HX} stroke="#94a3b8" stroke-dasharray="3 3" visibility=hidden /><rect class=hit x=0 y=0 width=${W} height=${H-HX} fill=transparent /></svg>`;
}
function bars(a,W,lbl){if(!a)return '';const n=a.length,H=64,pl=4,pr=50;const m=Math.max(...a.filter(v=>v!=null).map(Math.abs),1);const z=H/2,bw=Math.max(1,(W-pl-pr)/n*.7);
  let g=`<line x1=${pl} x2=${W-pr} y1=${z} y2=${z} stroke="#e8ebf1"/>`;a.forEach((v,i)=>{if(v==null||v===0)return;const hh=(H/2-3)*Math.abs(v)/m;const xx=pl+(i+.5)*(W-pl-pr)/n-bw/2;g+=`<rect x=${xx.toFixed(1)} y=${(v>0?z-hh:z).toFixed(1)} width=${bw.toFixed(1)} height=${hh.toFixed(1)} fill="${v>0?'#d33a34':'#1f9d57'}"/>`;});
  return `<svg width=${W} height=${H} viewBox="0 0 ${W} ${H}">${g}<text x=${pl+2} y=12 font-size=12 font-weight=600 fill="#44505f">${esc(lbl)}</text><text x=${W-pr+6} y=12 font-size=11 fill="#727e8c">+${f(m,0)}</text><text x=${W-pr+6} y=${H-3} font-size=11 fill="#727e8c">−${f(m,0)}</text></svg>`;}
function bindTip(code){const kc=document.getElementById('kc');if(!kc||!CH)return;const svg=kc.querySelector('svg');
  let tip=kc.querySelector('.tip');if(!tip){tip=document.createElement('div');tip.className='tip';tip.hidden=true;kc.appendChild(tip);}
  const s=(SER||{})[code]||{};const qa=qaOf(s);const ds=SERD.slice(-CH.n);const xh=svg.querySelector('#xh');const {n,pl,pr,W,M,x}=CH;
  const mv=e=>{const rc=svg.getBoundingClientRect();const px=((e.touches?e.touches[0].clientX:e.clientX)-rc.left);const i=Math.max(0,Math.min(n-1,Math.floor((px-pl)/((W-pl-pr)/n))));
    if(s.c[i]==null){tip.hidden=true;return;}const m=M[i];
    xh.setAttribute('x1',x(i));xh.setAttribute('x2',x(i));xh.setAttribute('visibility','visible');
    tip.innerHTML=`<b>${esc(ds[i]||'')}</b>　收 ${fp(s.c[i])}${s.o?`　開 ${fp(s.o[i])}　高 ${fp(s.h[i])}　低 ${fp(s.l[i])}`:''}${s.v?`<br>量 ${f(s.v[i],0)} 張`:''}${s.ac&&s.ac[i]?`　新建倉成本 ${fp(s.ac[i])}`:''}${qa&&qa[i]?`<br>主動 ETF 真${qa[i]>0?'加':'減'}碼 ${f(Math.abs(qa[i]),0)} ${s.o?'張':'股'}`:''}`+
      (m&&m.n.length?`<br><span style="color:#fca5a5">▲ 新建倉：${m.n.map(e=>esc(e)+' '+esc((E[e]||{}).is||'')).join('、')}</span>`:'')+(m&&m.x.length?`<br><span style="color:#86efac">▼ 出清：${m.x.map(e=>esc(e)+' '+esc((E[e]||{}).is||'')).join('、')}</span>`:'');
    tip.hidden=false;const left=Math.min(rc.width-tip.offsetWidth-4,Math.max(0,px+12));tip.style.left=left+'px';tip.style.top='4px';};
  const out=()=>{tip.hidden=true;xh.setAttribute('visibility','hidden');};
  svg.onmousemove=mv;svg.ontouchstart=mv;svg.ontouchmove=mv;svg.onmouseleave=out;}

/* ---------- 名詞頁 ---------- */
function openGl(){
  const st=(D.asof||{}).start;
  let h=`<div class=dvh><div class=dvt><div class=ttl><b>名詞與方法</b></div><a class=x id=glx>×</a></div></div>`;
  for(const [g,ks] of GLG)h+=`<div class=glh>${esc(g)}</div><div class=gll>${ks.map(k=>`<div><b>${esc(k)}</b><span>${esc(GL[k])}</span></div>`).join('')}</div>`;
  h+=`<div class=glh>訊號</div><div class=gll>${Object.keys(SD).map(k=>`<div><b>${RISK.has(k)?'⚠ ':''}${esc(SD[k][0])}</b><span>${esc(SD[k][1])}</span></div>`).join('')}</div>`;
  h+=`<div class=glh>方法</div><ul class=doc>
<li>把追蹤中 ETF（被動 6 檔＋主動式＋規模前段擴充檔；債券型除外）持有的所有個股，逐檔建「ETF 部位帳本」，再疊上官方籌碼與技術面。</li>
<li><b>時點</b>：ETF 揭露日的持股＝當日收盤後部位（成交在當日）；任何訊號最早只能在次一交易日開盤進場，成績一律以此計算。</li>
<li><b>公司行動</b>：減資、股票股利、面額變更造成的股數跳動，若股價同步反向變動，視為公司行動、不當成交易。</li>
<li><b>法人成本</b>：投信／外資「60 日買超均價」＝近 60 日買超日的買超股數 × 當日均價加權。</li></ul>
<div class=glh>限制</div><ul class=doc>
<li>ETF 持股史自 ${md(st)} 起，樣本短、行情單一；成績會隨每日累積自動更新，樣本 &lt;30 的結果不宜採信。</li>
<li>主動 ETF 持股每日公開，抄作業的人多時，效果可能已反映在隔夜跳空——成績把「隔夜跳空」與「進場後」分開列。</li>
<li>海外持股只有 ETF 面（無官方籌碼、技術面）；櫃買無借券與外資持股比欄位。</li>
<li>資料：ETF 持股＝etfinfo／復華官網；價量與籌碼＝證交所、櫃買中心、集保結算所公開資料。本頁為資料整理與統計，不構成任何投資建議。</li></ul>`;
  $('#glin').innerHTML=h;$('#gl').hidden=false;lockBody(true);$('#gl').scrollTop=0;$('#glx').onclick=closeGl;}
function closeGl(){$('#gl').hidden=true;lockBody(!$('#dv').hidden&&!$('#dv').classList.contains('pane'));}
$('#glb').onclick=e=>{e.preventDefault();openGl();};
$('#gl').addEventListener('click',e=>{if(e.target.id==='gl')closeGl();});

/* ---------- 分頁＋跳段目錄 ---------- */
const VIEWS={today:vToday,stk:vStk,iss:vIss,sig:vSig,st:vSt,idx:vIdx};
function hdh(){return $('.hd').offsetHeight;}
function jump(id){const t=document.getElementById(id);if(t)window.scrollTo({top:t.getBoundingClientRect().top+scrollY-hdh()-8,behavior:'smooth'});}
function buildNav(){const secs=$$('#main .sec[data-nav]');
  $('#snav').innerHTML=secs.length>1?secs.map(s=>`<a data-to="${s.id}">${esc(s.dataset.nav)}</a>`).join(''):'';
  $$('#snav a').forEach(a=>a.onclick=()=>jump(a.dataset.to));spy();}
let spyRaf=0;
function spy(){const secs=$$('#main .sec[data-nav]');const nav=$('#snav');if(secs.length<2)return;const y=hdh()+16;let cur=secs[0].id;
  for(const s of secs){if(s.getBoundingClientRect().top<=y)cur=s.id;else break;}
  if(innerHeight+scrollY>=document.documentElement.scrollHeight-4)cur=secs[secs.length-1].id;
  nav.querySelectorAll('a').forEach(a=>{const on=a.dataset.to===cur;if(on===a.classList.contains('on'))return;a.classList.toggle('on',on);
    if(on){const l=a.offsetLeft-nav.offsetLeft;if(l<nav.scrollLeft||l+a.offsetWidth>nav.scrollLeft+nav.clientWidth)nav.scrollLeft=Math.max(0,l-24);}});}
addEventListener('scroll',()=>{if(!spyRaf)spyRaf=requestAnimationFrame(()=>{spyRaf=0;spy();});},{passive:true});
function go(t,anchor){S.tab=t;$$('#tabs a[data-t]').forEach(a=>a.classList.toggle('on',a.dataset.t===t));VIEWS[t]();buildNav();
  $$('#main [data-go]').forEach(a=>a.onclick=e=>{e.preventDefault();const d=a.dataset;
    if(d.fsig!==undefined){S.sig=d.fsig;S.q='';S.n=60;}if(d.sort){S.vw='etf';S.sort=d.sort;S.dir=+(d.dir||-1);}go(d.go,d.at);});
  window.scrollTo(0,0);if(anchor)requestAnimationFrame(()=>jump(anchor));}
$$('#tabs a[data-t]').forEach(a=>a.onclick=()=>go(a.dataset.t));
go('today');
if(isPane())setTimeout(()=>{loadSer().catch(()=>{});},1500);
{const m=location.hash.match(/^#s=(.+)$/);if(m)renderStock(decodeURIComponent(m[1]));}
"""
