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
td.l,th.l{text-align:left}td.wr{white-space:normal;min-width:120px;max-width:220px}td.wr2{white-space:normal;min-width:180px}
tr.v3r td{border-bottom:0;padding-bottom:2px}tr.v3w td{white-space:normal;text-align:left;font-size:12px;color:var(--mut);padding-top:0;line-height:1.55}
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
.rbl{max-width:860px;margin:0 0 6px}.rbr{display:grid;grid-template-columns:13em minmax(0,1fr);gap:4px 12px;padding:6px 0;border-top:1px solid var(--line);font-size:13.5px;line-height:1.6}
.rbr:first-child{border-top:0}.rbk{color:var(--ink2)}.rbk .ck{display:inline-block;width:1.3em}
table.nbg{width:auto;font-size:12.5px;margin:4px 0}table.nbg td,table.nbg th{padding:4px 10px}table.nbg th:first-child{white-space:normal;max-width:9em}
.pkn{font-size:12px;color:var(--mut);white-space:normal;max-width:260px;line-height:1.5;margin-top:2px}
table.skt td{white-space:normal;width:50%;min-width:0}
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
.pcs{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.pcn{font-size:13.5px;color:var(--ink2);margin:0 0 8px}
.pc{border:1px solid var(--line);border-radius:10px;padding:8px 12px 9px}
.pch{display:flex;justify-content:space-between;align-items:baseline;gap:8px;margin-bottom:3px}.pch a b{font-size:15px}.pk{color:var(--ink)}
.pcr{display:grid;grid-template-columns:4.8em minmax(0,1fr);gap:8px;font-size:13px;line-height:1.7}.pcr>span:first-child{color:var(--mut)}
.pcw{font-size:12.5px;line-height:1.65;margin-top:5px;color:var(--ink2)}.pcw b{margin-right:6px;color:var(--mut);font-weight:600}
.pcx{font-size:12.5px;line-height:1.6;margin-top:4px;color:var(--warn)}
.sm2{font-size:12px;color:var(--mut);line-height:1.5}
.gd{display:inline-block;font-size:12px;font-weight:700;padding:0 8px;border-radius:7px;white-space:nowrap;line-height:1.75;vertical-align:1px}
.gA{background:var(--hlbg);color:var(--accd)}.gB{background:#fdf1dc;color:var(--warn)}.gC{background:var(--card2);color:var(--mut)}
h2 .gd{margin-left:2px}
.pcg{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;font-size:12.5px;margin:0 0 5px}
.ccl{font-size:14.5px}
.kvt{max-width:560px}.kvt td{white-space:normal;text-align:left;padding:5px 8px}.kvt td:first-child{color:var(--mut);width:7.5em;white-space:nowrap;position:static}
.rkl{margin:0;padding-left:20px}.rkl li{margin:2px 0}
.wgh{margin:10px 0 4px;font-size:13.5px}
.xg{padding:9px 0;border-bottom:1px solid var(--line)}.xg>b{font-size:14.5px}.xg>.st{display:block;margin-top:1px}.xr{font-size:13.5px;margin-top:4px}.xg .inl{font-size:13.5px;line-height:1.8}
.tl ol{margin:4px 0 6px;padding-left:20px}.tl li{margin:1px 0}
.pgp{border:1px solid var(--line);border-radius:12px;padding:10px 12px 12px;margin:0 0 12px}
.pgh{font-size:15px;font-weight:700;margin:0 0 4px}.pgh .st{font-weight:400}
.pgb{margin:0 0 10px;max-width:860px}.pgb .pcr{grid-template-columns:5.2em minmax(0,1fr);font-size:13.5px}
.sgd{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;max-width:860px}
.sgd .kp>b{font-size:15px}.sgd .kp>em{white-space:normal}
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
 .hm{display:none}.pkr{display:none}
 table.g3t td:first-child{white-space:normal;min-width:96px;max-width:118px}table.g3t .cd{white-space:normal}
 .rbr{grid-template-columns:1fr;gap:1px}
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
'超額':'報酬減去比較基準同期的報酬；正＝贏。評級與月營收驚喜、財報驚喜用「同一批股票的平均」當基準；共識加碼、臺灣50、長線、高股息的舊表格對加權指數。成績已扣來回成本（大型股 0.48%、中型股 0.68%；舊表格 0.585%）。',
'勝率':'超額報酬為正的次數比例。',
'獲利比例':'扣除來回成本後報酬為正的交易比例。',
'贏大盤':'報酬高於加權指數同期報酬（超額報酬為正）的交易比例。',
'信賴區間':'把歷史交易重新抽樣 2,000 次，平均超額報酬有 95% 的機會落在這個範圍。下限大於 0，代表贏大盤不太可能只是運氣；區間含 0，代表樣本還不足以下結論。',
'評級':'看三件事（都扣成本後）：①選股：平均贏同一批股票；②報酬型態：賺錢機率 ≥60% 且每月平均 ≥+1%，或賺錢機率 ≥40%、賺賠比 ≥2.5、每月平均 ≥+2%；③穩健度：成本加倍、參數鄰近 9 組 ≥6 組為正、去掉最好 5% 後仍贏。A 可執行：三項全過、t 值樣本內 ≥2 且樣本外同方向 t ≥1、前瞻滿 10 期（事件型 2 次）也贏，每檔 ≤ 總資金 5%。B 小部位試行：選股與報酬型態過、樣本外沒有反向、穩健度最多一項未過，每檔 ≤ 2%。C 不推薦：其餘（參數鄰近不到一半為正、或樣本外反向，一律 C），只列觀察。',
'每 10 萬預估':'投入 10 萬元時，依同一規則過去已出場交易的中位報酬與最差一筆換算的損益（已扣成本）。是歷史統計，不是預測。',
'隔夜跳空':'訊號出現後隔天的開盤價，相對訊號日收盤的漲跌。跟單的人多時，好處常在隔夜就被反映掉。',
'樣本':'歷史上符合條件的次數。少於 30 次時結果容易受單一段行情左右，只能當參考。',
'紙上交易':'照寫死的規則自動記帳、不實際下單，用來驗證策略在「規則訂好之後」的真實表現。',
'樣本內':'規則發想與調整時看過的資料（月營收驚喜、財報驚喜：2021-10 起；其餘策略：2024～2025 起的全部歷史）。規則本來就是看這段資料挑出來的，成績會偏好看。',
'樣本外':'規則寫定之後才第一次拿來跑的歷史資料：2013～2021-09，含之後下市的公司。樣本外也贏，才不只是從資料裡挑出來的巧合。共識加碼、臺灣50、長線、高股息的資料從 2024～2025 才有，沒有樣本外。',
't 值':'平均超額 ÷ 它的標準誤差（Newey-West 法，處理相鄰期間的相關）。約 2 以上＝贏的幅度不太像運氣；1 左右＝方向對但證據弱；負的＝輸。',
'賺錢機率':'扣成本後報酬大於 0 的期數（或筆數）比例；月營收驚喜、財報驚喜以「同一期 5 檔等額平均」為一期。',
'每月平均':'平均報酬 ÷ 平均持有月數（一個月＝21 個交易日），讓持有 3 天和持有 3 個月的策略可以比。持有很短的策略數字會很大，不代表一個月真的能做那麼多次。',
'賺賠比':'賺錢那幾期（筆）的平均報酬 ÷ 賠錢那幾期（筆）的平均虧損。',
'報酬型態':'評級條件之一：賺錢機率 ≥60% 且每月平均 ≥+1%；或「上漲空間大」的例外：賺錢機率 ≥40%、賺賠比 ≥2.5、每月平均 ≥+2%。樣本內、樣本外都要過。',
'前 5 檔':'每期只買訊號最強的 5 檔、等額。檔數少，波動與最大回落比買整組（最強 10%～20%）大。',
'大型股':'月底市值 ≥300 億、20 日均成交值 ≥5,000 萬。',
'中型股':'月底市值 50～300 億、20 日均成交值 ≥5,000 萬。',
'因子檢定':'不看交易規則、只看訊號本身：每期依訊號把股票分 5 組，最強組減最弱組（選端−另端，未扣成本）。各組由弱到強依序遞增、t 值夠大，代表訊號有用；這和「只買最強 5 檔能不能賺」是兩個問題。',
'資金帳戶':'把每期報酬依時間順序連乘：同一時間只有一組部位、換股時賣舊買新、扣成本、沒持股的期間放現金。年化報酬與最大回落用這條線算。',
'最大回落':'資金曲線從前一個高點往下跌的最大幅度。',
'去掉最好 5%':'把報酬最好的 5% 期數（或筆數）拿掉後，平均是否仍贏同一批股票；只靠一兩次大賺撐起來的策略過不了。',
'前瞻':'規則起算日之後才發生的訊號；這部分的成績才算數。',
'前瞻驗證':'規則起算日之後才發生的交易。短線策略滿 10 筆、事件型滿 2 次審核，且平均超額大於 0，才可能評為 A 級。',
'資料截止日':'指數公司用來排名的那一天收盤資料（臺灣50：生效日前約 4 週的週一）。截止日之後股價再怎麼變，都不影響這一次的名單。',
'漲勢前一半':'同一次審核的納入股，依資料截止日前 40 個交易日的漲幅排序，取前一半（無條件進位；只有 1 檔就是它）。',
'被動買盤':'0050＋006208 規模 ÷ 前 50 大市值＝被動資金持有比例，乘上發行股數，估計生效日要買進的張數；沒有做自由流通調整，是估計值。',
'週轉率':'20 日平均成交股數 ÷ 發行股數（%）；越高代表市場越熱衷交易這檔。',
'估計權重':'新納入股在臺灣50 的權重估計＝個股市值 ÷ 前 50 大市值合計（未做自由流通調整）。被動買盤金額約＝0050＋006208 規模 × 權重。新進的股票都剛擠進前 40 名，彼此權重差不多。',
'被動買賣期間':'被動 ETF 實際買進新成分股、賣出刪除股的那幾個交易日，依官方「投信買賣超」推得：0056 在生效日（第三個週五）收盤起 5 天；00919、00929 從公告當天收盤起約 8 天（00919 有幾次提前 2～3 天）；00878 約生效日前 5～6 天到生效後幾天。',
'對其他成分股':'和同一次審核前後都留在指數裡的成分股（等權平均）比，扣掉高股息類股整體的漲跌，剩下的才是「被納入／被刪除」本身的影響。',
'被動買賣日量':'被動 ETF 換股要買（賣）的金額 ÷ 該股 20 日平均成交金額＝要用掉幾天的正常成交量。高股息 ETF 規模大，冷門中型股一次常是 10 天以上的量；台積電這類權值股不到 1 天。',
'被動買賣提醒':'高股息換股的納入股估計被動買盤 ≥5 日量：被動買盤結束後 10 個交易日，過去多半輸大盤、也輸其他成分股 → 已持有的在最後一天收盤前出、沒持有的不追；刪除股被賣完後也沒有反彈。只是提醒，不做放空。',
'等級相關':'兩組數字排序的一致程度，−1～+1：+1＝排序完全相同、0＝沒有關係、負＝方向相反。這裡樣本只有十幾檔，數值僅供參考。',
'穩健度檢查':'同一份歷史成績換幾種角度再算一次：成本加倍、參數稍微改動、去掉最好的 5%、大盤多頭與空頭分開、買不到或賣不掉的情況。打 ✓ 的三項（成本加倍、參數鄰近、去掉最好 5%）是 A 級的條件。',
'成本加倍':'每筆交易再多扣一次來回成本（大型股 0.48%、中型股 0.68%；舊表格 0.585%）。實際滑價、零股或流動性差時成本會更高；成本加倍後還贏，優勢才不只是成本算得太樂觀。',
'參數鄰近':'把策略的兩個關鍵參數各往上、往下調一檔，共 9 組，看有幾組平均還贏（月營收驚喜、財報驚喜對同一批股票；共識加碼、臺灣50、長線沿用原本對加權指數的 9 組）。只有剛好那一組賺錢的策略，多半是從歷史資料挑出來的巧合。',
'同一批股票的平均':'同一段期間、同一個範圍（大型股或中型股）所有股票的等權平均報酬。策略要贏過它，才算選股有效。月營收驚喜、財報驚喜的清單含之後下市的公司；共識加碼、臺灣50、長線的清單（2024 起）只含目前還上市的公司，整批股票偏強（存活者偏誤）。',
'存活者偏誤':'只用現在還存在的公司做回測：失敗、下市、縮水的公司不在資料裡，歷史成績因此偏好看。',
'大盤年線':'加權指數 200 個交易日均線。指數在年線之上大致是多頭、之下大致是空頭；兩組分開看，才知道策略是否只在多頭有效。',
'成交檢查':'開盤就漲停時，開盤價通常買不到；整天鎖在跌停時，收盤賣不掉。回測遇到這兩種情況：買進順延或放棄、賣出順延到下一個交易日。',
'相對強勢':'依過去一段期間的漲幅在全部股票中的排名選股（例：約 6 個月前到 1 個月前漲最多的前 10%）。學術上稱動能效應。',
'趨勢樣板':'Mark Minervini 的選股條件：股價在 50／150／200 日線之上且均線依序向上、離一年低點 30% 以上、離一年高點 25% 以內、強度排名前 30%。這裡另要求整理後帶量突破才買。',
'SUE':'標準化盈餘驚喜＝（當季 EPS − 去年同季 EPS）÷ 過去幾季這個差距的波動。數字越大代表這季成長越出乎意料。學術上發現驚喜大的股票，之後幾個月常繼續走強（財報後漂移）。',
'月營收驚喜':'（上個月營收 − 去年同月營收）÷ 過去 12 個月這個差距的標準差。數字越大代表這個月的成長越出乎意料，用法同 SUE，只是改用每月 10 日前公告的月營收。金融保險業不算（營收口徑不同，金控可延到 15 日申報）。',
'CAN SLIM':'William O’Neil 的成長股選股法，七個字母代表當季盈餘成長、年度成長、新產品或新高、股數供需、領先股、法人認養、大盤方向。這裡測試其中的 C（當季 EPS 年增 ≥25%）與 M（大盤在年線上）。',
};
const GLG=[['ETF 面',['真加碼','申贖倍率','主動 5 日淨買','加碼／減碼家數','持有 ETF','新建倉','建倉日','主動成本','成本乖離','超配','ETF 持股率','消化天數']],
 ['法人籌碼',['投信 5 日','外資 5 日','連買','60 日買超均價','融資','借券賣出','千張大戶']],
 ['技術面',['趨勢','乖離','量比','RSI','KD','MACD','一年區間位置','相對大盤','ATR','日均成交']],
 ['成績與策略',['評級','同一批股票的平均','t 值','賺錢機率','每月平均','賺賠比','報酬型態','樣本外','樣本內','前瞻','前瞻驗證','前 5 檔','大型股','中型股','超額','信賴區間','獲利比例','贏大盤','勝率','每 10 萬預估','隔夜跳空','樣本','紙上交易']],
 ['回測方法與策略',['穩健度檢查','成本加倍','參數鄰近','去掉最好 5%','因子檢定','資金帳戶','最大回落','存活者偏誤','大盤年線','成交檢查','月營收驚喜','SUE','相對強勢','趨勢樣板','CAN SLIM']],
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
function idxEvents(){const out=[];for(const r of ((D.idx||{}).cal||[])){if(r[6]&&r[10]!=null&&r[10]>=0)out.push({n:r[1],etf:(r[2]||[]).join(' '),cut:r[4],ann:r[5],eff:r[6],tr:r[7],stt:r[8],conf:r[9],days:r[10],pred:r[12]});}
  return out.sort((a,b)=>a.days-b.days);}
function chgI(x){return x==null?'':` · <span class=${x>0?'up':x<0?'dn':''}>${x>0?'+':''}${f(x,1)}%</span>`;}
function flowRows(rs,m,side){if(!rs.length)return '<div class=st>無</div>';
  return `<div class="fl flh"><span>股票・今日漲跌</span><span>億元</span><span></span><span>投信家數${gi('加碼／減碼家數')}</span></div>`+rs.map(r=>{const w=Math.max(3,Math.abs(r.a5v)/m*100);
  return `<div class=fl data-c="${esc(r.c)}"><span class=fn><b>${esc(r.n)}</b><i>${esc(r.c)}${chgI(r.ch)}</i></span><span class="fv ${r.a5v>0?'up':'dn'}">${r.a5v>0?'+':''}${f(r.a5v,1)}</span><span class=fb><i class=${r.a5v>0?'bu':'bd'} style="width:${w.toFixed(0)}%"></i></span><span class=fi>${side==='sell'?`${(r.ic5||[]).length} 減・${(r.ia5||[]).length} 加`:`${(r.ia5||[]).length} 加・${(r.ic5||[]).length} 減`}</span></div>`;}).join('');}
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
  const PK=(D.adv||{}).picks||[],evs=idxEvents(),t50=(D.idx||{}).tw50||{};
  const d5=(D.dates||[]).slice(-5);const win=d5.length?`${md(d5[0])}～${md(d5[d5.length-1])}`:'';
  const L=[];
  if(bs||ss){const tone=Math.abs(net)<=0.15*Math.max(bs,ss)?'買賣金額相近，以換股為主':net>0?'整體偏向加碼':'整體偏向減碼';
    L.push(`主動 ETF 近 5 日：淨買的股票合計 <b class=up>${f(bs,0)} 億</b>、淨賣的合計 <b class=dn>${f(ss,0)} 億</b>——${tone}。${gi('主動 5 日淨買')}`);}
  if(cons.length)L.push(`<b>${cons.length} 檔</b>有 3 家以上投信同時加碼${gi('cons')}，最多的是 ${cntGroup(cons.slice(0,3).map(r=>[nmL(r),(r.ia5||[]).length]))}。`);
  if(exits.length)L.push(`<b>${exits.length} 檔</b>被 3 家以上投信同時減碼${gi('exit')}，賣最多的是 ${exits.slice(0,3).map(r=>`${nmL(r)}（${f(r.a5v,1)} 億）`).join('、')}。`);
  if(nbs.length)L.push(`10 日內主動 ETF 新建倉的台股 <b>${nbs.length} 檔</b>${gi('新建倉')}，最多家同時進場的是 ${cntGroup(nbs.slice(0,3).map(x=>[nmL(x.r),x.is.length]))}。`);
  const PN=PK.filter(p=>p.act!=='持有中'),PH=PK.filter(p=>p.act==='持有中');
  L.push(PK.length?`本期操作 <b>${PK.length} 檔</b>：${PN.length?`新佈局 ${pickGroups(PN).join('；')}`:'沒有新佈局'}${PH.length?`；持有中 ${PH.length} 檔（${[...new Set(PH.map(p=>esc(p.sname)))].join('、')}）`:''}。<a data-go="st" data-at="st-now">看操作清單 →</a>`:'本期沒有 A、B 級策略產生的標的。');
  if(evs.length){const e=evs[0];L.push(`最近的指數換股：<b>${esc(e.n)}</b>（${esc(e.etf)}）${md(e.eff)} 生效，還有 ${e.days} 天${e.stt==='推算'?'（日期為推算）':''}。`);}
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
  h+=sec('t-cand','操作','本期操作','評級 A、B 的策略產生的標的；預估報酬與部位見策略頁',
    (PN.length?pickRows(PN):'<div class=st>本期沒有新佈局。</div>')+(PH.length?`<div class=st style="margin-top:8px">${pickGroups(PH).join('；')}。</div>`:''),`<a data-go="st" data-at="st-now">看策略 →</a>`);
  const al=(D.strat||{}).alerts||[];
  h+=sec('t-risk','風險',`風險提醒`,'',
    `<div class=rk2><b>集體撤退 ${exits.length} 檔</b>${gi('exit')}${exits.length?` <a class=sm data-go="stk" data-fsig="exit" data-sort="a5v" data-dir="1">看表格 →</a>`:''}<span class=st>近 5 日 3 家以上投信同時減碼、主動合計淨賣（億元）</span><div class=inl>`+
      (exits.length?exits.map(r=>`<span class=it><a data-c="${esc(r.c)}">${esc(r.n)}</a>${r.a5v!=null?`<span class=dn> ${f(r.a5v,1)}</span>`:''}</span>`).join('　'):'<span class=st>今日無</span>')+`</div></div>`+
    `<div class=rk2><b>跳空減碼提醒</b><span class=st>前一日「共識加碼」、今日開盤跳空 ≥3%：過去這類股票之後 1～10 個交易日平均都輸大盤</span><div class=inl>`+
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
  L.push(`<b>穩定的是買盤結束之後</b>：估計 ≥${big} 日量的納入股，被動買盤結束後 ${aft} 個交易日對大盤平均 ${pctT(R(T.post_big).avg)}、${R(T.post_big).n} 次只有 ${R(T.post_big).pos} 次為正；對其他成分股${gi('對其他成分股')} ${pctT(R(T.post_bigc).avg)}（${R(T.post_bigc).pos}／${R(T.post_bigc).n} 次為正）。買盤小的（<${big} 日量）對其他成分股 ${pctT(R(T.post_smallc).avg)}——回落集中在大買盤股 → 做成「被動買賣提醒」${gi('被動買賣提醒')}（策略頁「高股息換股」）。`);
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
/* 高股息：依編製規則提前卡位（回測）——使用者 2026-10-15：「用指數編纂邏輯提前試算可能加入、權重會很大的公司」 */
function hdPreSec(H){const R=(H||{}).pre||{};
  if(R.err)return sec('idx-hdpre','提前卡位','高股息：依編製規則提前卡位（回測）','',`<div class=st>資料錯誤：${esc(R.err)}</div>`);
  if(!R.n)return '';
  const V={};(R.vars||[]).forEach(v=>V[v.k]=v);const m=V.main||{},a3=V.ann3||{},pa=V.perf_ann3||{},th=R.th||5,W=R.win||[];
  const hit=(R.acc||[]).reduce((s,a)=>s+((a['0']||[0])[0]||0),0),tot=(R.acc||[]).reduce((s,a)=>s+(a.act||0),0);
  const ex=(v)=>v&&v.n?`${v.x>=0?'贏':'輸'}大盤 ${f(Math.abs(v.x),1)}%（95% 信賴區間 ${ciT(v.ci)}），${v.n} 次中 ${v.kx} 次贏大盤`:'—';
  const L=[];
  L.push(`<b>結論：評級 ${esc(m.grade||'—')}${m.grade==='C'?'，不列推薦':''}</b>。依 00919、00929 的編製規則，在資料截止日試算納入股，買進預估被動買盤 ≥${th} 天成交量的，在被動買盤最後一天賣出：過去 ${m.n} 次審核（${esc(R.d0||'')}～${esc(R.d1||'')}）平均每次${ex(m)}。`);
  const inR=W[2]||[],post=W[3]||[],pre=W[1]||[];
  if(inR[2])L.push(`<b>權重大的確實漲比較多，但只在被動買盤那幾天</b>：以事後確定的名單計算，預估被動買盤 ≥10 天成交量的納入股，被動買盤期間平均贏大盤 ${pctT(inR[2].x)}，不到 3 天的只有 ${pctT((inR[0]||{}).x)}；買盤結束後 10 個交易日又輸大盤 ${pctT((post[2]||{}).x)}。`);
  L.push(`<b>實際做不到的原因</b>：① 名單會猜錯，截止日當天 ${tot} 檔實際納入股猜中 ${hit} 檔（2025 年規則改版前更差）；② 截止日到被動買盤開始前，大買盤股平均${(pre[2]||{}).x>=0?'贏':'輸'}大盤 ${f(Math.abs((pre[2]||{}).x||0),1)}%；③ 00919、00929 常在公告前幾天就開始買，起跑日不固定。`+
    `改成公告前 3 個交易日才買：平均每次${ex(a3)}。就算名單完全猜對，公告前 3 天買也只有平均每次${ex(pa)}。`);
  L.push(`<b>可以用的部分</b>：持有這類大買盤股的，在被動買盤最後一天前賣出；買盤結束後 10 個交易日內不買。這兩條已列在策略頁「高股息換股」的出場規則。`);
  let b=`<div class=lead><ul>${L.map(x=>`<li>${x}</li>`).join('')}</ul></div>`;
  b+=`<h4 class=sh>做法比較（每次審核等額平均、扣成本）</h4><div class=tw><table><thead><tr><th class=l>做法</th><th>次數</th><th>筆數（猜中）</th><th>每次平均</th><th>平均超額${gi('信賴區間')}</th><th>贏大盤</th><th>對其他成分股${gi('對其他成分股')}</th><th class=l>評級</th></tr></thead><tbody>`+
    (R.vars||[]).map(v=>`<tr class="${v.perfect?'grey':''}"><td class=l>${esc(v.lbl)}</td><td>${v.n||'—'}</td><td>${v.trades}（${v.hit}）</td><td>${pctT(v.avg)}</td><td>${pctT(v.x)}<div class=sm2>${ciT(v.ci)}</div></td><td>${v.n?`${v.kx}／${v.n}`:'—'}</td><td>${pctT(v.xc)}<div class=sm2>${v.kc}／${v.nc} 次為正</div></td><td class=l>${gBadge(v.grade)}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>出場一律在被動買盤最後一天收盤；官方名單沒有的，公告後第一個交易日開盤賣出。灰色兩列用事後確定的正確名單，只是上限、實際做不到。「公告前 3 天」是看過其他結果後才加的做法，要看前瞻成績。</div>`;
  b+=`<h4 class=sh>預估被動買盤大小 × 時段（正確名單，每筆平均）</h4><div class=tw><table><thead><tr><th class=l>時段</th>${(R.bks||[]).map(x=>`<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>`+
    W.map((row,i)=>`<tr><td class=l>${esc((R.wins||[])[i]||'')}</td>${row.map(c=>`<td>${c&&c.n?`${pctT(c.x)}<div class=sm2>對其他成分股 ${pctT(c.xc)}・${c.n} 檔</div>`:'—'}</td>`).join('')}</tr>`).join('')+
    `</tbody></table></div><div class=note>欄＝預估被動買進金額 ÷ 20 日平均成交金額（幾天的量）。上排數字＝對大盤超額、不扣成本。</div>`;
  b+=`<details class=mr><summary>名單準度與逐次結果</summary><div class=tw><table><thead><tr><th>ETF・審核</th><th>實際納入</th><th>截止日猜中／預估</th><th>截止前 10 日</th><th>截止前 20 日</th></tr></thead><tbody>`+
    (R.acc||[]).map(a=>`<tr><td>${HDE[a.key]||esc(a.key)}<div class=sm2>${esc(a.review)}</div></td><td>${a.act}</td>${['0','10','20'].map(k=>`<td>${a[k]?`${a[k][0]}／${a[k][1]}`:'—'}</td>`).join('')}</tr>`).join('')+`</tbody></table></div>`+
    `<div class=tw><table><thead><tr><th>ETF・審核</th><th>截止日買（檔數・猜中）</th><th>報酬</th><th>對大盤</th><th>完美預知・公告前 3 天</th></tr></thead><tbody>`+
    ((R.rev||{}).main||[]).map(r=>{const q=((R.rev||{}).perf_ann3||[]).find(x=>x[0]===r[0]&&x[1]===r[1]);return `<tr><td>${HDE[r[0]]||esc(r[0])}<div class=sm2>${esc(r[1])}</div></td><td>${r[2]}・${r[3]}</td><td>${pctT(r[4])}</td><td>${pctT(r[5])}</td><td>${q?pctT(q[5]):'—'}</td></tr>`;}).join('')+`</tbody></table></div>`+
    `<div class=note>權重公式用 ETF 實際持股校準：00919 實際上接近市值加權（媒體寫的股利率加權與實際持股對不上），00929 為殖利率加權；預估買進金額與官方投信買賣超推得的實際買進相比，中位誤差約四成。0056（分析師預估股利）、00878（ESG 評級）名單重現不了，不在測試內；00919 2023-12 名單查得到、但換股日期查不到，未納入。</div></details>`;
  return sec('idx-hdpre','提前卡位','高股息：依編製規則提前卡位（回測）',`${R.n} 次審核・00919／00929`,b);}
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
  h+=hdPredSec(X.hd)+hdStudySec(X.hd)+hdFlowSec(X.hd)+hdPreSec(X.hd);
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

/* ---------- 策略（v2）：本期操作清單 → 策略評級 → 各策略（結論／操作規則／歷史績效／本期名單／風險）→ 部位與風控 ---------- */
const ADV=D.adv||{},GDN={A:'可執行',B:'小部位試行',C:'不推薦'},GCAP={A:'每檔 ≤ 總資金 5%',B:'每檔 ≤ 總資金 2%',C:'不列推薦，只列觀察'};
function gBadge(g,t){return g?`<span class="gd g${g}">${t||`${g}・${GDN[g]}`}</span>`:'';}
function wd(d){if(!d||d.length<10)return '';const t=new Date(Date.UTC(+d.slice(0,4),+d.slice(5,7)-1,+d.slice(8,10)));return `（${'日一二三四五六'[t.getUTCDay()]}）`;}
function mdw(d){return d?md(d)+wd(d):'—';}
function ciT(ci){return ci?`${pctT(ci[0])}～${pctT(ci[1])}`:'—';}
function gOf(k){return (ADV.grades||[]).find(g=>g.k===k);}
/* 回測方法 v3（2026-10-15）：評級看「對同一批股票」、報酬型態、穩健度；月營收驚喜、財報驚喜另有 2013～2021 樣本外 */
function g3Of(k){return (ADV.grades3||[]).find(g=>g.k===k);}
const LV=(ADV.v3||{}).live||{},V3M=(ADV.v3||{}).meta||{};
function tT(x){return x==null?'—':(x<0?'−':'')+f(Math.abs(x),2);}
function p2(x){return x==null?'—':pctT(x,Math.abs(x)>=10?1:2);}
function bw(x){return x==null?'—':`${x>=0?'贏':'輸'} ${f(Math.abs(x),Math.abs(x)>=10?1:2)}%`;}
function hiLo(x){return x==null?'—':`${x>=0?'高':'低'} ${f(Math.abs(x),Math.abs(x)>=10?1:2)}%`;}
function ym(d){return d?esc(String(d).slice(0,7)):'—';}
function qTxt(q){return q?`${q.slice(0,4)} 年第 ${Math.round(+q.slice(5,7)/3)} 季`:'';}
function wan(x){return x==null?'—':(x>0?'+':x<0?'−':'')+f(Math.abs(x),0)+' 元';}
function stOf(k){return ((D.strat||{}).list||[]).find(s=>s.key===k);}
function nmA(x){return BY[x.c]?`<a data-c="${esc(x.c)}">${esc(x.n)}</a>`:esc(x.n);}
function ruleRows(rules){return rules.map(x=>{const i=x.indexOf('：');const lab=i>0&&i<=8?x.slice(0,i):'';return `<div class="rl${lab?'':' nl'}">${lab?`<span class=rlk>${esc(lab)}</span>`:''}<span>${esc(lab?x.slice(i+1):x)}</span></div>`;}).join('');}
function riskList(xs){return (xs||[]).length?`<ol class=rkl>${xs.map(x=>`<li>${esc(x)}</li>`).join('')}</ol>`:'—';}
function tradeTbl(rows,monthly){const gp=!monthly&&rows.some(t=>t.gap!=null);
  return `<div class=tw><table><thead><tr><th>股票</th><th>${monthly?'篩選月':'訊號日'}</th><th class=l>狀態</th>${gp?'<th>跳空</th>':''}<th>進場</th><th>出場／現價</th><th>持有</th><th>報酬</th><th>超額${gi('超額')}</th></tr></thead><tbody>`+
  rows.map(t=>`<tr data-c="${esc(t.c)}" class="${t.st==='skip'?'grey':''}"><td><span class=nm>${esc(t.n)}</span><span class=cd>${esc(t.c)}</span></td><td>${monthly?esc((t.d||'').slice(0,7)):md(t.d)}</td><td class=l>${t.st==='skip'?'未進場：'+esc(t.why||''):t.st==='open'?'持有中':t.st==='cand'?'待進場':esc(t.why||'')}${t.side?` <span class=pill>${t.side==='add'?'納入':'刪除'}</span>`:''}</td>${gp?`<td>${t.gap==null?'—':sgn(t.gap,1,'%')}</td>`:''}<td>${t.entry==null?'—':fp(t.entry)}</td><td>${t.exit!=null?fp(t.exit):t.now!=null?fp(t.now):'—'}</td><td>${t.held==null?'—':t.held+' 日'}</td><td>${sgn(t.r,1,'%')}</td><td>${t.x==null?'—':sgn(t.x,1,'%')}</td></tr>`).join('')+`</tbody></table></div>`;}
function tradeLists(s,monthly){const fw=(s.fwd||[]).slice().reverse(),ins=(s.ins||[]).slice().reverse();
  let m=`<h4 class=sh>前瞻交易（${md(s.since)} 起算，${fw.length} 筆）</h4>`+(fw.length?tradeTbl(fw,monthly):'<div class=st>尚無。</div>');
  if(ins.length)m+=`<details class=mr><summary>歷史交易 ${ins.length} 筆（規則訂定前）</summary>${tradeTbl(ins,monthly)}</details>`;
  return m;}
function pctT(x,d=1){return x==null?'—':(x>0?'+':x<0?'−':'')+f(Math.abs(x),d)+'%';}
function sq(k,v){return `<div class=sq><span class=sqk>${k}</span><div>${v}</div></div>`;}
function stW(){return Math.max(280,Math.min(760,($('#main').clientWidth||360)-34));}
/* 持有天數比較：每根柱子＝第 N 個交易日收盤出場的平均超額；本策略紅綠、對照組灰；藍底＝採用的天數 */
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
function scanTxt(sc){if(!sc||!(sc.grp||[]).length)return '';const H=sc.h,a=sc.grp[0],b=sc.grp[1];
  const nm=gr=>esc(gr.lbl.replace(/（.*?）/g,'')),t=gr=>{const k=gr.x.filter(v=>v!=null&&v>0).length;return k===H?`${H} 個持有天數全部贏大盤`:k===0?`${H} 個持有天數全部輸大盤`:`${H} 個持有天數中 ${k} 個贏大盤`;};
  return `同一訊號依隔日開盤分兩組，持有 1～${H} 個交易日：${nm(a)}，${t(a)}`+(b?`；${nm(b)}，${t(b)}`:'')+'。';}
function moTxt(ds){return ds&&(ds.mo||[]).length?'逐月平均超額：'+ds.mo.map(m=>`${+m[0].slice(5)} 月 ${m[1]} 筆 ${pctT(m[2])}`).join('｜'):'';}
function eAt(E,k){const i=(E.k||[]).indexOf(k);return i<0||E.avg[i]==null?null:{avg:E.avg[i],med:E.med[i],win:E.win[i],n:E.n[i],lo:E.lo[i]};}

/* 本期操作：依策略分組。共同的時間、條件、預估報酬放組頭；個股卡只放各檔不同的進場價、停損、部位與依據 */
function pcRow(k,v){return `<div class=pcr><span>${k}</span><span>${v}</span></div>`;}
function pickCard(p){const px=p.px,z=p.size,t=`<b>${esc(p.n)}</b> <span class=cd>${esc(p.c)}</span>`;
  let b=`<div class=pch>${BY[p.c]?`<a data-c="${esc(p.c)}">${t}</a>`:`<span>${t}</span>`}<span class=mu>${p.act==='持有中'?'現價':'收'} <b class=pk>${fp(px)}</b></span></div>`;
  if(p.act==='持有中')b+=pcRow('持有',`${md(p.ent)} 買進${p.entry!=null?`，成本 ${fp(p.entry)}`:''}${p.now_r!=null?`，目前 ${sgn(p.now_r,1,'%')}`:''}`);
  else if(p.cond)b+=pcRow('進場',`<b>${esc(p.cond)}</b>`);
  if(p.stop!=null&&px)b+=pcRow('停損',`收盤跌破 <b>${fp(p.stop)}</b>（${pctT((p.stop/px-1)*100)}）`);
  if(z)b+=pcRow('部位',`每 100 萬資金 ${f(z.amt/1e4,z.amt%1e4?1:0)} 萬元，約 ${z.sh>=1000?f(z.sh/1000,1)+' 張':f(z.sh,0)+' 股（零股）'}`);
  if((p.why||[]).length)b+=`<div class=pcw><b>依據</b>${p.why.map(esc).join('；')}</div>`;
  return `<div class=pc>${b}</div>`;}
function expRows(e){if(!e||!e.n)return '';const ev=e.event,u=ev?(e.grp||'次'):'筆';
  return pcRow('預估報酬',`${ev?`每${u}（各檔平均）`:'每筆'}中位 <b>${pctT(e.med)}</b>，一半落在 ${pctT(e.p25)}～${pctT(e.p75)}；${ev?`${e.n} ${u}中 ${e.kwin} ${u}獲利`:`${e.win}% 獲利`}，最差一${u} ${pctT(e.lo)}（過去 ${e.n} ${u}）`)+
    pcRow('每 10 萬',`${ev?'整組投入，':''}中位 <b>${wan(e.per10)}</b>；最差 ${wan(e.lo10)}`);}
function pickBlocks(P){const G=new Map();for(const p of P){const k=[p.act,p.k,p.act==='持有中'?p.out:p.ent].join('|');if(!G.has(k))G.set(k,[]);G.get(k).push(p);}
  return [...G.values()].map(xs=>{const p=xs[0],cap=(ADV.caps||{})[p.grade],hold=p.act==='持有中',L=LV[p.k],nx=L&&L.next;
    const when=hold?`持有中，<b>${mdw(p.out)} 收盤</b>${L&&L.src==='p7'?'換股':'出場'}`:`<b>${mdw(p.ent)} 開盤</b>進場 → ${p.out?`<b>${mdw(p.out)} 收盤</b>出場`:'依停損與回落出場'}`;
    return `<div class=pgp><div class=pgh><a data-to="st-${esc(p.k)}">${esc(p.sname)}</a> ${gBadge(p.grade)} <span class=st>${xs.length} 檔</span>${p.oos?' <span class=sg>有樣本外驗證</span>':' <span class=pill>沒有樣本外驗證</span>'}</div><div class=pgb>`+
      pcRow('時間',`${when}${p.hold?`（${esc(p.hold)}）`:''}`)+(hold?'':pcRow('進場條件',esc(p.ent_how||'')))+pcRow('出場條件',esc(p.out_how||'—'))+
      pcRow('停損',esc(p.stop_how||'—'))+expRows(p.exp)+(p.oos_txt?pcRow('驗證',esc(p.oos_txt)):'')+
      (cap?pcRow('部位上限',`每檔 ≤ 總資金 ${f(cap*100,0)}%（每 100 萬 ${f(cap*100,0)} 萬元）${p.stop!=null?'；有停損時另限停損虧損 ≤ 總資金 0.5%':''}`):'')+
      (p.tent?`<div class=pcx>名單以今天排名試算，${md(p.fix)} 收盤定案前可能變動。</div>`:'')+
      (hold&&nx?`<div class=pcx>這一期 ${md(p.ent)} 開盤已買進。回測只計決定日隔天開盤進場，沒跟上的等下一期：${mdw(nx.d)} 收盤決定、${mdw(nx.ent)} 開盤買進。</div>`:'')+
      `</div><div class=pcs>${xs.map(pickCard).join('')}</div></div>`;}).join('');}
function pickGroups(ps){const G=new Map();for(const p of ps){const k=[p.act,p.act==='持有中'?p.out:p.ent,p.sname,p.grade].join('|');if(!G.has(k))G.set(k,[]);G.get(k).push(p);}
  return [...G.values()].map(xs=>{const p=xs[0],nm=xs.map(nmA).join('、');
    return p.act==='持有中'?`持有中 ${nm}（${esc(p.sname)}・${p.grade} 級，${md(p.out)} 收盤${(LV[p.k]||{}).src==='p7'?'換股':'賣出'}）`:
      `${md(p.ent)} 開盤 ${nm}（${esc(p.sname)}・${p.grade} 級${p.tent?`；${md(p.fix)} 收盤定案`:''}）`;});}
function pickRows(ps){return ps.map(p=>`<div class=cr data-c="${esc(p.c)}"><div class=fn><b>${esc(p.n)}</b><i>${esc(p.c)} · ${esc(p.sname)} · ${p.grade} 級</i></div>`+
  `<div class=crc>${p.act==='持有中'?`持有中，${md(p.out)} 收盤${(LV[p.k]||{}).src==='p7'?'換股':'賣出'}`:`${md(p.ent)} ${p.cond?esc(p.cond):'開盤買進'} → ${p.out?md(p.out)+' 收盤賣出':'依停損與回落出場'}`}${p.tent?'<span class=st>（名單試算中）</span>':''}</div>`+
  `<div class=crs><span class=st>停損</span><b>${p.stop==null?'不設':fp(p.stop)}</b></div></div>`).join('');}

/* 出場與避開：高股息換股、共識加碼後開高 */
function hdGroups(full){const xs=(ADV.exits||[]).filter(x=>x.k==='hd'),HA=((D.idx||{}).hd||{}).alert||{},aft=HA.after||10;
  if(!xs.length)return `<div class=st>目前沒有估計被動買賣 ≥${HA.big_th||5} 日量的換股股票。</div>`;
  const G=[...new Set(xs.map(x=>[x.etf,x.review,x.src].join('|')))];
  return G.map(k=>{const [e,rv,src]=k.split('|'),ys=xs.filter(x=>x.etf===e&&x.review===rv&&x.src===src).sort((a,b)=>b.days-a.days),x0=ys[0];
    const ad=ys.filter(x=>x.side==='add'),de=ys.filter(x=>x.side==='del'),done=x0.phase==='after';
    const win=x0.phase==='pre'?`被動買賣 ${md(x0.t0)}～${md(x0.t1)}`:x0.phase==='in'?`被動買賣中，最後一天 ${md(x0.t1)}`:`被動買賣已於 ${md(x0.t1)} 結束`;
    const nm=x=>nmA(x)+(full?`<span class=mu>（${f(x.amt,0)} 億・${f(x.days,0)} 日量）</span>`:'');
    const ym=rv.replace(/^(\d{4})-0?(\d+)$/,'$1 年 $2 月');
    return `<div class=xg><b>${esc(e)} ${esc(ym)}換股</b> <span class=pill>${esc(src)}名單</span><span class=st>${win}${src==='預估'?'；名單以官方公告為準':''}</span>`+
      (ad.length?`<div class=xr><b>納入 ${ad.length} 檔</b>：${done?'':`持有者 ${md(x0.t1)} 收盤前賣出；`}未持有者 ${md(x0.until)} 前不買。</div><div class=inl>${ad.map(nm).join('、')}</div>`:'')+
      (de.length?`<div class=xr><b>刪除 ${de.length} 檔</b>：${md(x0.until)} 前不買。</div><div class=inl>${de.map(nm).join('、')}</div>`:'')+`</div>`;}).join('');}
function gapList(){const al=(ADV.exits||[]).filter(x=>x.k==='gap'),ag=(((D.strat||{}).alert_scan||{}).grp||[])[0];
  const xs=ag?ag.x.filter(v=>v!=null):[];
  const ev=xs.length?`過去 ${ag.n[0]} 筆，開高當天開盤進場，持有 1～${xs.length} 個交易日的平均超額 ${pctT(Math.max(...xs))}～${pctT(Math.min(...xs))}${xs.every(v=>v<0)?'，全部輸大盤':''}。`:'';
  return `<div class=xg><b>共識加碼後隔日開高 ≥3%</b><span class=st>${ev}未持有者不追；已持有者可趁開高減碼。</span><div class=inl>`+
    (al.length?al.map(a=>`<span class=it>${nmA(a)} <span class=mu>${md(a.d)} 訊號、開盤</span> ${sgn(a.gap,1,'%')}</span>`).join('　'):'<span class=st>今天沒有</span>')+`</div></div>`;}

function nowSec(){const P=ADV.picks||[],W=ADV.watch||[];
  let b=P.length?`<div class=st style="margin-bottom:8px">依證據強弱排序：有 2013～2021 樣本外驗證的策略在前，其次依 t 值${gi('t 值')}。</div>`+pickBlocks(P):'<div class=st>本期沒有 A、B 級策略產生的標的。</div>';
  b+=`<div class=note>預估報酬＝同一規則過去的分布（月營收驚喜、財報驚喜以同一期 5 檔等額平均為一期），已扣成本，不是對個股的預測。部位計算見「部位與風控」。</div>`;
  if(W.length){const G=[...new Set(W.map(p=>p.k))];
    b+=`<h4 class=sh>觀察名單（C 級，不下單）</h4>`+G.map(k=>{const ws=W.filter(p=>p.k===k),g=g3Of(k)||gOf(k)||{},L=LV[k];
      return `<div class=wgh><a data-to="st-${esc(k)}">${esc(ws[0].sname)}</a> ${gBadge(g.grade)} <span class=st>${esc((g.why||[]).slice(0,2).join('；'))}</span></div>`+
        `<div class=tw><table><thead><tr><th>股票</th><th>${L?'現價':'收盤'}</th><th class=l>入選依據</th><th class=l>${L?'紙上記錄':'最快進場'}</th></tr></thead><tbody>`+
        ws.map(p=>`<tr data-c="${esc(p.c)}"><td><span class=nm>${esc(p.n)}</span><span class=cd>${esc(p.c)}</span></td><td>${fp(p.px)}</td><td class="l wr">${(p.why||[]).map(esc).join('；')}</td><td class=l>${L?`${md(p.ent)} 進場${p.now_r!=null?`，目前 ${sgn(p.now_r,1,'%')}`:''}`:mdw(p.ent)}</td></tr>`).join('')+`</tbody></table></div>`;}).join('');}
  b+=`<h4 class=sh>出場與避開</h4><div class=st>持有中的股票遇到以下情況，依規則處理。</div>${hdGroups(false)}${gapList()}`;
  return sec('st-now','本期','本期操作清單',`${md(ADV.last)} 收盤後產生`,b);}

function gradeSec(){const G=ADV.grades3||[];if(!G.length)return '';
  const cnt=k=>{const p=(ADV.picks||[]).filter(x=>x.k===k).length,w=(ADV.watch||[]).filter(x=>x.k===k).length,x=(ADV.exits||[]).filter(x=>x.k===k).length;
    return p?`${p} 檔`:w?`${w} 檔觀察`:x?`${x} 檔出場・避開`:'—';};
  const side=(x,u)=>x&&x.n?`${p2(x.xe)}<span class=mu>／${u}</span><div class=sm2>t ${tT(x.t)}・${x.n} ${u}</div>`:'<span class=mu>沒有</span>';
  const row=g=>{const i=g.ins||{},o=g.oos||{},u=g.unit||'筆',old=gOf(g.k)||{};
    const bd=g.k==='hd'?`${gBadge(g.grade,'追買 '+g.grade)}${old.exit&&old.exit.ok?'<div style="margin-top:3px">'+gBadge('A','出場有效')+'</div>':''}`:gBadge(g.grade,`${g.grade}<span class=hm>・${GDN[g.grade]}</span>`);
    return `<tr><td><a data-to="st-${esc(g.k)}"><span class=nm>${esc(g.name||g.k)}</span></a><span class=cd>${esc(g.kind||'')}</span></td><td class=l>${bd}</td>`+
      (g.k==='hd'?`<td colspan=4 class="l mu">追買沒有贏大盤；有效的是出場時點（見下方高股息換股）</td>`:
      `<td>${side(o,u)}</td><td>${side(i,u)}</td><td>${i.win==null?'—':i.win+'%'}${o.n?`<div class=sm2>樣本外 ${o.win}%</div>`:''}</td><td>${p2(i.m)}${o.n?`<div class=sm2>樣本外 ${p2(o.m)}</div>`:''}</td>`)+
      `<td class=hm>${cnt(g.k)}</td><td class="l wr hm">${esc((g.why||[]).slice(0,3).join('；'))}${(g.why||[]).length>3?'…':''}</td></tr>`;};
  return sec('st-grade','評級','策略評級','評級規則見「部位與風控」',`<div class=tw><table class=g3t><thead><tr><th>策略</th><th class=l>評級${gi('評級')}</th><th>樣本外選股${gi('樣本外')}</th><th>樣本內選股${gi('樣本內')}</th><th>賺錢機率${gi('賺錢機率')}</th><th>每月平均${gi('每月平均')}</th><th class=hm>本期</th><th class="l hm">評級理由</th></tr></thead><tbody>${G.map(row).join('')}</tbody></table></div>`+
    `<div class=note>選股＝扣成本後平均每期（或每筆）贏同一批股票${gi('同一批股票的平均')}多少，下方為 t 值${gi('t 值')}與樣本數。樣本外＝2013～2021-09，規則寫定後才第一次跑；樣本內＝月營收驚喜、財報驚喜 2021-10 起，其餘策略 2024～2025 起（沒有樣本外）。</div>`);}

/* 各策略固定五段 */
function stSec(k,nav,title,kind,parts,more,badge){const g=g3Of(k)||gOf(k)||{};
  return sec('st-'+k,nav,`${esc(title)} ${badge||gBadge(g.grade)}`,esc(kind||''),`<div class="card stc">${parts.map(([a,b])=>sq(a,b)).join('')}${more&&more[1]?`<details class=mr><summary>${more[0]}</summary>${more[1]}</details>`:''}</div>`);}
function keyLine(g){const u=g.event?'次':'筆';if(g.x==null)return `過去 ${g.n} ${u}，報酬中位 ${pctT(g.med)}。`;
  const xm=g.xmed!=null&&Math.sign(g.xmed)!==Math.sign(g.x)?`，但中位${g.xmed>=0?'贏':'輸'}大盤 ${f(Math.abs(g.xmed),1)}%`:'';
  return `過去 ${g.n} ${u}平均每${u}${g.x>=0?'贏':'輸'}大盤 ${f(Math.abs(g.x),1)}%（95% 信賴區間 ${ciT(g.ci)}）${xm}；報酬中位 ${pctT(g.med)}，${g.event?`${g.n} 次中 ${g.kwin} 次獲利`:`${g.win}% 獲利`}。`;}
function cclS(g,extra,k){const g3=k?g3Of(k):null;
  if(g3&&g3.ins&&g3.ins.n){const x=g3.ins,u=g3.unit||'筆';
    return `<div class=ccl><b>${g3.grade}・${GDN[g3.grade]}</b>（${GCAP[g3.grade]}）</div>`+
      `<div>過去 ${x.n} ${u}，每${u}平均報酬比同一批股票${gi('同一批股票的平均')}${hiLo(x.xe)}（t ${tT(x.t)}）；扣成本後賺錢機率 ${x.win}%、每月平均 ${p2(x.m)}${gi('每月平均')}。</div>`+
      (g&&g.n?`<div class=sm2>對加權指數（成本 0.585%）：${keyLine(g)}</div>`:'')+
      `<div class=sm2>${g3.grade==='A'?'A 級條件全部符合。':`${g3.grade==='B'?'未達 A 級':'評級原因'}：${esc((g3.why||[]).join('；'))}。`}</div>`+(extra||'');}
  if(!g||!g.n)return '<span class=mu>尚無已出場交易。</span>';
  return `<div class=ccl><b>${g.grade}・${esc(g.label)}</b>（${GCAP[g.grade]}）</div><div>${keyLine(g)}</div>`+
    `<div class=sm2>${g.grade==='A'?'A 級條件全部符合。':`${g.grade==='B'?'未達 A 級':'評級原因'}：${esc((g.why||[]).join('；'))}。`}</div>`+(extra||'');}
/* 評級依據（新成本、對同一批股票）：共識加碼、臺灣50、長線沒有樣本外，只有樣本內 */
function v3Grid(k){const g3=g3Of(k);if(!g3||!g3.ins||!g3.ins.n)return '';const x=g3.ins,u=g3.unit||'筆',N=g3.nb||{},need=Math.ceil((N.n||9)*2/3),cl=v=>v>0?'up':v<0?'dn':'';
  const T=[kp('選股','同一批股票的平均',`${p2(x.xe)}／${u}`,`t ${tT(x.t)}・${x.n} ${u}`,cl(x.xe)),
    kp('賺錢機率','賺錢機率',`${x.win}%`,x.ratio!=null?`賺賠比 ${f(x.ratio,1)}`:''),kp('每月平均','每月平均',p2(x.m),''),
    kp(`${x.x2>0?'✓':'✗'} 成本加倍`,'成本加倍',p2(x.x2),'選股平均',cl(x.x2)),kp(`${x.drop5>0?'✓':'✗'} 去掉最好 5%`,'去掉最好 5%',p2(x.drop5),'選股平均',cl(x.drop5)),
    ...(N.n?[kp(`${N.pos>=need?'✓':'✗'} 參數鄰近`,'參數鄰近',`${N.pos}／${N.n}`,`沿用對加權指數的 9 組；A 級需 ≥${need}`)]:[]),
    kp('前瞻驗證','前瞻驗證',`${(g3.fwd||{}).n||0}／${u==='次'?2:10} ${u}`,(g3.fwd||{}).n?`平均${bw(g3.fwd.xe)}`:'沒有樣本外，前瞻達標後代替')];
  return `<h4 class=sh style="margin-top:0">評級依據（扣新成本、對同一批股票）</h4><div class=sgd>${T.join('')}</div>`+
    `<h4 class=sh>對加權指數（參考）</h4>`;}
function perfTbl(g,v3){if(!g||!g.n)return '<span class=mu>尚無已出場交易。</span>';const u=g.event?'次':'筆',F=g.fwd||{},nf=g.event?2:10,cl=x=>x>0?'up':x<0?'dn':'';
  const T=[kp('樣本','',`${g.n} ${u}`,`${esc(g.d0||'')}～${esc(g.d1||'')}`),
    kp('獲利比例','獲利比例',`${g.win}%`,`${g.kwin}／${g.n} ${u}`),
    kp('平均／中位','',`${pctT(g.avg)}／${pctT(g.med)}`,`一半落在 ${pctT(g.p25)}～${pctT(g.p75)}`),
    kp('最差／最好','',`${pctT(g.lo)}／${pctT(g.hi)}`,''),
    kp('平均超額','信賴區間',pctT(g.x),g.ci?`95% 區間 ${ciT(g.ci)}`:'樣本不足',cl(g.x)),
    kp('贏大盤','贏大盤',g.xwin==null?'—':`${g.xwin}%`,g.kx!=null?`${g.kx}／${g.nx||g.n} ${u}`:''),
    ...(g.conc?[kp('最集中月份','',esc(g.conc[0]),`占 ${g.conc[1]}%`)]:[]),
    kp('前瞻驗證','前瞻驗證',`${F.n||0}／${nf} ${u}`,F.n?`平均超額 ${pctT(F.x)}`:'起算後的交易')];
  return `<div class=sgd>${T.join('')}</div><div class=note>報酬已扣來回成本 0.585%；超額＝減去加權指數同期報酬${g.event?'；每次＝同一次審核各檔等額平均':''}。</div>`+robTbl(g,v3);}
/* 穩健度檢查（資料包回測紀律 D1–D7，2026-10-15）：打 ✓／✗ 的三項是 A 級條件 */
function nbGrid(N){if(!N||!N.cells)return '';const L=N.lbl||['',''],ad=N.ad||N.a||[],bd=N.bd||N.b||[],c=N.cells;
  let h=`<table class=nbg><thead><tr><th>${esc(L[0])}＼${esc(L[1])}</th>${bd.map(b=>`<th>${esc(b)}</th>`).join('')}</tr></thead><tbody>`;
  ad.forEach((a,i)=>{h+=`<tr><td>${esc(a)}</td>${bd.map((b,j)=>{const v=(c[i*bd.length+j]||[])[2];return `<td class="${v>0?'up':v<0?'dn':''}">${v==null?'—':pctT(v)}</td>`;}).join('')}</tr>`;});
  return h+`</tbody></table>`;}
function robTbl(g,v3){const R=g&&g.rb;if(!R||R.x2==null)return '';const N=g.nb||{},F=g.fill,u=g.event?'次':'筆',cl=x=>x>0?'up':x<0?'dn':'',need=Math.ceil((N.n||9)*2/3);
  const ck=ok=>ok==null?'<span class=ck></span>':ok?'<span class="ck up">✓</span>':'<span class="ck dn">✗</span>';
  const row=(k,gk,v,c,ok)=>`<div class=rbr><div class=rbk>${ck(ok)}${k}${gk?gi(gk):''}</div><div class="${c||''}">${v}</div></div>`;
  /* v3＝評級改看上方「評級依據」：這裡只留對加權指數的參考，不打 ✓／✗ */
  let h=v3?'':row(`成本加倍（每${u}再扣 0.585%）`,'成本加倍',`平均超額 ${pctT(R.x2)}`,cl(R.x2),R.x2>0);
  if(N.n)h+=row(v3?'參數鄰近 9 組':'參數鄰近','參數鄰近',`鄰近 ${N.n} 組參數中 ${N.pos} 組贏大盤${v3?'':`（A 級需 ≥${need}）`}<details class=mr><summary>看 ${N.n} 組</summary>${nbGrid(N)}</details>`,'',v3?null:N.pos>=need);
  if(R.xe!=null&&!v3)h+=row('對同一批股票的平均','同一批股票的平均',`平均${R.xe>=0?'贏':'輸'} ${f(Math.abs(R.xe),1)}%（${R.kxe}／${R.nxe} ${u}贏）`,cl(R.xe),R.xe>0);
  if(R.drop1!=null)h+=row(`去掉最好的一${u}`,'',`平均超額 ${pctT(R.drop1)}`,cl(R.drop1),null);
  if(R.up||R.dn){const U=R.up||[0,null],Dn=R.dn||[0,null];
    h+=row('大盤在年線上／下','大盤年線',`年線上 ${U[0]} ${u}，平均超額 ${pctT(U[1])}；年線下 ${Dn[0]?`${Dn[0]} ${u}，平均超額 ${pctT(Dn[1])}`:'沒有樣本，空頭時的表現未經檢驗'}`,'',null);}
  h+=row('最大累計回落','',`依時間順序累加每${u}超額，最多回落 ${f(R.mdd,1)} 個百分點；最長連續 ${R.streak} ${u}輸大盤`,'',null);
  if(F)h+=row('成交檢查','成交檢查',`漲停開盤買不到 ${F.lim} ${u}、整天鎖跌停順延賣出 ${F.lock} ${u}`,'',null);
  return `<h4 class=sh>${v3?'穩健度（對加權指數，參考）':'穩健度檢查'}${gi('穩健度檢查')}</h4><div class=rbl>${h}</div>`+
    ((g.tried||[]).length?`<div class=note>樣本內比較過的做法：${g.tried.map(esc).join('；')}。成績是從這些做法裡挑出來的，會偏樂觀。</div>`:'');}
function listOf(k){const P=(ADV.picks||[]).filter(p=>p.k===k);
  return P.length?`${pickGroups(P).join('；')}。<div class=st>進出場日期、停損與部位見 <a data-to="st-now">本期操作清單</a>。</div>`:'<span class=mu>本期沒有。</span>';}

function s1Sec(){const s=stOf('s1');if(!s)return '';const g=gOf('s1'),sc=s.scan,ds=s.dist||{},ev=scanTxt(sc);
  let m='';if(sc)m+=`<h4 class=sh>持有天數比較（規則訂定前）</h4>${scanChart(sc,s.hold)}<div class=note>每根柱子＝第 N 個交易日收盤出場時的平均超額；灰＝平盤或開高時進場的對照組。</div>`;
  if(ds.n)m+=`<div class=st>${moTxt(ds)}</div>`;
  m+=tradeLists(s,false);
  return stSec('s1','共識加碼',s.name,s.kind,[['結論',cclS(g,ev?`<div class=sqe>${ev}</div>`:'','s1')],['操作規則',`<div class=rls>${ruleRows(s.rule||[])}</div>`],
    ['歷史績效',v3Grid('s1')+perfTbl(g,!!g3Of('s1'))],['本期名單',listOf('s1')],['風險',riskList(s.risk)]],['持有天數比較、逐月成績與交易明細',m]);}

/* 臺灣50：只列提前卡位一條策略；公告後進場、官方名單全部收在比較表 */
function trTxt(t){if(!t)return '—';if(t.st==='cand')return `${md(t.ent)} 開盤買進`;
  if(t.st==='open')return `${fp(t.entry)} 買進，現價 ${fp(t.now)}（${pctT(t.r)}）`;
  if(t.st==='closed')return `${fp(t.entry)} → ${fp(t.exit)}（${pctT(t.r)}，${esc(t.why||'')}）`;return esc(t.why||'—');}
function s3Now(s){const p=s.plan;if(!p)return '<span class=mu>等下一次審核時程公布。</span>';const it=p.items||[],st=p.stage;
  let h=`<div class=tl><b>${esc(p.review.replace(/^(\d{4})-0?(\d+)$/,'$1 年 $2 月'))}審核${p.status==='推算'?'（日期為推算）':''}</b>`+
    `<ol><li>${mdw(p.e_sig)} 收盤選股，${mdw(p.e_in)} 開盤買進</li><li>${mdw(p.cutoff)} 資料截止，收盤後校正名單；${mdw(p.a_in)} 開盤賣出或補進</li>`+
    `<li>${mdw(p.announce)} 官方公告</li><li>${mdw(p.out)} 收盤全部賣出（${md(p.effective)} 生效前一天）</li></ol></div>`;
  if(st==='watch')h+=`<div>${it.length?`以今天排名試算，會買進 ${it.map(i=>`${nmA(i)}（第 ${i.rank} 名、40 日漲幅 ${pctT(i.mom)}）`).join('、')}。${md(p.e_sig)} 收盤才定案。`:'以今天排名，候選中沒有符合條件的股票。'}</div>`;
  else{const b=it.filter(i=>i.e||i.t);h+=b.length?`<div>${b.map(i=>`${nmA(i)}：${trTxt(i.ta)}${(st==='frozen'||st==='announced')&&i.e&&i.pred===false?'（截止日名單沒有）':''}`).join('<br>')}</div>`:'<div class=mu>這一次沒有買進的股票。</div>';}
  if((p.dels||[]).length)h+=`<div class=note>${st==='announced'?'官方':'預估'}刪除：${p.dels.map(d=>esc(d[1])).join('、')}。</div>`;
  return h+`<div class=note><a data-go="idx" data-at="idx-tw50">指數頁看完整排名 →</a></div>`;}
function verCmp(s){const V=(s.vers||[]).filter(v=>v.score);if(!V.length)return '';
  const row=v=>{const g=v.score||{},mk=v.k==='early'?' <span class=pill>本策略</span>':v.k==='all'?' <span class=mu>對照</span>':'';
    return `<tr><td><span class=nm>${esc(v.name.replace('（對照）',''))}${mk}</span></td><td class=l>${esc(v.buy)}</td><td class=l>${esc(v.sell)}</td><td>${g.n||'—'}</td><td>${pctT(g.avg)}</td><td>${pctT(g.med)}</td><td>${g.n?`${g.kwin}／${g.n}`:'—'}</td><td>${pctT(g.lo)}</td><td>${pctT(g.x)}<div class=sm2>${ciT(g.ci)}</div></td><td>${g.n?`${g.kx}／${g.nx||g.n}`:'—'}</td><td class=l>${gBadge(g.grade)}</td></tr>`;};
  return `<div class=tw><table><thead><tr><th>做法</th><th class=l>進場</th><th class=l>出場</th><th>次數</th><th>每次平均</th><th>中位</th><th>獲利次數</th><th>最差一次</th><th>平均超額${gi('信賴區間')}</th><th>贏大盤次數</th><th class=l>評級</th></tr></thead><tbody>${V.map(row).join('')}</tbody></table></div>`+
    `<div class=st style="margin-top:6px">${verWhy(V)}</div>`;}
function verWhy(V){const E=V.find(v=>v.k==='early'),P=V.find(v=>v.k==='post');if(!E||!P||!E.score.n||!P.score.n)return '';const e=E.score,p=P.score,a=[],b=[];
  [['中位報酬',e.med,p.med],['獲利次數',e.kwin,p.kwin],['最差一次',e.lo,p.lo],['平均超額',e.x,p.x],['贏大盤次數',e.kx,p.kx]].forEach(([k,x,y])=>{if(x==null||y==null)return;if(x>y)a.push(k);else if(x<y)b.push(k);});
  let t=`同樣 ${e.n} 次審核，提前卡位在${a.join('、')||'—'}較好${b.length?`，公告後進場在${b.join('、')}較好`:''}。`;
  if(e.x!=null&&p.x!=null)t+=`提前卡位持有約 2 個月，每次報酬中約 ${pctT(e.avg-e.x)} 來自同期大盤上漲；公告後進場持有約 2 週，約 ${pctT(p.avg-p.x)}。`;
  return t+`本頁以提前卡位為操作策略（進場最早）；公告後進場同步記錄前瞻成績，各滿 2 次審核後再比較。`;}
function s3More(s){const E=(s.vers||[]).find(v=>v.k==='early')||{},br=(s.by_rev||[]).slice().reverse();let m='';
  if(br.length)m+=`<h4 class=sh>逐次比較（每次的平均報酬，已扣成本）</h4><div class=tw><table><thead><tr><th>審核</th><th>提前卡位</th><th>公告後進場</th><th>官方名單全部</th><th>公告後第一天開盤</th></tr></thead><tbody>`+
    br.map(r=>`<tr><td>${esc(r[0])}</td><td>${sgn(r[1],1,'%')}</td><td>${sgn(r[2],1,'%')}</td><td>${sgn(r[3],1,'%')}</td><td>${r[4]==null?'—':sgn(r[4],1,'%')}</td></tr>`).join('')+
    `</tbody></table></div><div class=note>「公告後第一天開盤」＝公告後進場買進股票的開盤價相對公告日收盤；負值越大，公告後進場買得越便宜。</div>`;
  if(((D.idx||{}).study||{}).n)m+=`<div class=st>名單準度、提前幾天建倉、哪些納入股漲最多：<a data-go="idx" data-at="idx-study">指數頁「換股研究」→</a></div>`;
  return m+(E.k?tradeLists(E,false):'');}
function s3Sec(){const s=stOf('s3');if(!s)return '';const g=gOf('s3'),E=(s.vers||[]).find(v=>v.k==='early')||{};
  return stSec('s3','臺灣50',s.name,s.kind,[['結論',cclS(g,'','s3')],['操作規則',`<div class=rls>${ruleRows(E.rule||s.rule||[])}</div>`],['歷史績效',v3Grid('s3')+perfTbl(g,!!g3Of('s3'))],
    ['本期名單',s3Now(s)],['風險',riskList(s.risk)]],['三種做法比較、逐次成績與交易明細',verCmp(s)+s3More(s)]);}

/* 高股息換股：追買評級 C；有效的是出場時點 */
function hdSec(){const g=gOf('hd');if(!g)return '';const HA=((D.idx||{}).hd||{}).alert||{},ef=g.exit||{},dl=g.del||{},aft=HA.after||10,bt=HA.big_th||5;
  const cc=`<div class=ccl><b>追買：${g.grade}・${esc(g.label)}</b></div><div>名單公開後買進估計被買 ≥${bt} 日量的納入股、被動買盤最後一天賣出：${keyLine(g)}</div>`+
    (ef.n?`<div class=ccl style="margin-top:8px"><b>出場：${ef.ok?'規則有效':'證據不足'}</b></div><div>同一批股票在被動買盤結束後 ${aft} 個交易日，平均超額 ${pctT(ef.avg)}（95% 信賴區間 ${ciT(ef.ci)}），${ef.n} 次中 ${ef.neg} 次輸大盤。`+
      `${dl.n?`刪除股被動賣盤結束後 ${aft} 個交易日，平均超額 ${pctT(dl.avg)}（95% 信賴區間 ${ciT(dl.ci)}），${dl.n} 次中 ${dl.neg} 次輸大盤。`:''}</div>`:'')+
    `<div class=sm2>用法：持有納入股者，在被動買盤最後一天收盤前賣出；被動買賣結束後 ${aft} 個交易日內，納入股與刪除股都不買。</div>`+
    (()=>{const PV={};((((D.idx||{}).hd||{}).pre||{}).vars||[]).forEach(v=>PV[v.k]=v);const m=PV.main;
      return m&&m.n?`<div class=ccl style="margin-top:8px"><b>提前卡位（依編製規則試算名單）：${esc(m.grade)}・${esc(m.label||'')}</b></div><div>資料截止日買進預估被動買盤 ≥${((D.idx||{}).hd||{}).pre.th||5} 天成交量的預估納入股、被動買盤最後一天賣：${keyLine(m)}${(()=>{const c=((((D.idx||{}).hd||{}).pre||{}).win||[])[1];const x=c&&c[2]&&c[2].x;return x==null?'':`名單會猜錯；截止日到被動買盤開始前，大買盤股平均${x>=0?'贏':'輸'}大盤 ${f(Math.abs(x),1)}%。`;})()}<a data-go="idx" data-at="idx-hdpre">完整研究 →</a></div>`:'';})();
  const S=((D.idx||{}).hd||{}).flow||{},T={};(S.tests||[]).forEach(t=>T[t.k]=t);
  const pr=(lbl,t,ci)=>{const r=(t||{}).rev||{};return r.n?`<tr><td>${lbl}</td><td>${r.n} 次</td><td>${pctT(r.avg)}${ci?`<div class=sm2>${ciT(ci)}</div>`:''}</td><td>${r.n-r.pos}／${r.n}</td></tr>`:'';};
  const perf=`<div class=tw><table><thead><tr><th>情境</th><th>次數</th><th>平均超額${gi('信賴區間')}</th><th>輸大盤次數</th></tr></thead><tbody>`+
    pr('追買：名單公開後買、最後一天賣',T.ride5,g.ci)+pr(`納入股：被動買盤結束後 ${aft} 日`,T.post_big,ef.ci)+pr(`刪除股：被動賣盤結束後 ${aft} 日`,T.del10,dl.ci)+
    ((((D.idx||{}).hd||{}).pre||{}).vars||[]).filter(v=>v.k==='main'||v.k==='ann3').map(v=>v.n?`<tr><td>提前卡位：${esc(v.lbl)}、最後一天賣</td><td>${v.n} 次</td><td>${pctT(v.x)}<div class=sm2>${ciT(v.ci)}</div></td><td>${v.n-v.kx}／${v.n}</td></tr>`:'').join('')+
    `</tbody></table></div><div class=note>每次＝同一檔 ETF 同一次換股的提醒股等額平均；期間 ${esc(g.d0||'')}～${esc(g.d1||'')}，四檔高股息 ETF 合計。提前卡位兩列只含名單算得出來的 00919、00929（${esc(((((D.idx||{}).hd||{}).pre||{}).d0)||'')} 起）。</div>`+robTbl(g);
  const by=(t,lbl)=>(t&&(t.by||[]).length)?`<h4 class=sh>${lbl}</h4><div class=tw><table><thead><tr><th>ETF</th><th>換股</th><th>檔數</th><th>平均超額</th></tr></thead><tbody>`+
    t.by.map(b=>`<tr><td>${esc(b[0])}</td><td>${esc(b[1])}</td><td>${b[3]}</td><td>${sgn(b[2],1,'%')}</td></tr>`).join('')+`</tbody></table></div>`:'';
  const fs=HA.fwd_stats||{};
  const m=by(T.post_big,`納入股（估計 ≥${bt} 日量）被動買盤結束後 ${aft} 日，逐次`)+by(T.del10,`刪除股被動賣盤結束後 ${aft} 日，逐次`)+
    `<div class=st style="margin-top:6px">${fs.n?`前瞻（${md(HA.since)} 起）：${fs.rev} 次換股、${fs.n} 檔，結束後 ${aft} 日平均超額 ${pctT(fs.avg)}，${fs.neg} 檔輸大盤。`:`前瞻紀錄從 ${md(HA.since)} 起算，第一批是 2026 年 12 月的換股。`} <a data-go="idx" data-at="idx-hdw">完整研究 →</a></div>`;
  const badge=gBadge(g.grade,'追買 '+g.grade)+(ef.ok?' '+gBadge('A','出場規則有效'):'');
  return stSec('hd','高股息',HA.name||'高股息換股',HA.kind||'',[['結論',cc],['操作規則',`<div class=rls>${ruleRows(HA.rule||[])}</div>`],['歷史績效',perf],
    ['本期名單',hdGroups(true)],['風險',riskList(HA.risk)]],['逐次成績與前瞻紀錄',m],badge);}

/* 長線：投信動能成長股（S5） */
function gRow(lbl,g){if(!g||!g.n)return `<tr><td>${lbl}</td><td colspan=8 class=mu>無樣本</td></tr>`;
  const r=(x)=>x&&x[0]!=null?`${f(x[0],1)}%<span class=mu>（${x[1]}）</span>`:'—';
  return `<tr><td>${lbl}</td><td>${g.n}</td><td>${r(g.dbl6)}</td><td>${r(g.dbl12)}</td><td>${g.end6&&g.end6[0]!=null?sgn(g.end6[0],1,'%')+'／'+sgn(g.end6[1],1,'%'):'—'}</td><td>${g.rule?sgn(g.rule[0],1,'%')+'／'+sgn(g.rule[1],1,'%'):'—'}</td><td>${g.rule_w==null?'—':g.rule_w+'%'}</td><td>${g.rule_aw==null?'—':sgn(g.rule_aw,1,'%')+'／'+sgn(g.rule_al,1,'%')}</td><td>${g.rule_big==null?'—':f(g.rule_big,1)+'%'}</td></tr>`;}
function s5Sec(){const G=D.grow||{};if(G.err)return sec('st-s5','長線','長線：投信動能成長股','',`<div class=card><div class=st>資料錯誤：${esc(G.err)}</div></div>`);
  const S5=G.s5;if(!S5)return '';const g=gOf('s5')||{},B=G.bt||{},ms=B.months||[],sc=G.screen||[],ok=sc.filter(x=>x.pass),near=sc.filter(x=>!x.pass),scr=S5.screen_d;
  const ex=g.n&&g.avg!=null&&g.med!=null&&g.avg-g.med>=10?`<div class=sqe>平均 ${pctT(g.avg)} 遠高於中位 ${pctT(g.med)}：成績來自少數大漲的交易（最好一筆 ${pctT(g.hi)}），多數交易小賺小賠或停損出場。</div>`:'';
  const now=`${scr?`下次篩選：${mdw(scr[0])} 收盤，符合者 ${mdw(scr[1])} 開盤買進。`:''}${ok.length?`以今天資料，四項條件全部符合 ${ok.length} 檔：${ok.map(nmA).join('、')}（C 級，只列觀察）。`:'以今天資料，沒有四項條件全部符合的股票。'}`;
  const ck=v=>v?'<span class=up>✓</span>':'<span class=mu>✗</span>';
  const scRow=x=>`<tr data-c="${esc(x.c)}" class="${x.pass?'':'grey'}"><td><span class=nm>${esc(x.n)}</span><span class=cd>${esc(x.c)}</span></td><td class=l>${ck(x.g_trust)} ${x.trust==null?'':f(x.trust,2)+'% 股本'}${x.tdays!=null?'・買 '+x.tdays+' 日':''}${x.etf2?' <span class=sg>主動 ETF 多家建倉</span>':''}</td><td class=l>${ck(x.g_grow)} ${x.yoy==null?'':'年增 '+f(x.yoy,0)+'%'}${x.cyoy==null?'':'・累計 '+f(x.cyoy,0)+'%'}</td><td class=l>${ck(x.g_mom)} ${x.rs==null?'':'強度前 '+(100-x.rs)+'%'}</td><td>${f(x.cap,0)}</td><td>${f(x.liq,1)}</td></tr>`;
  const scHead=`<thead><tr><th>股票</th><th class=l>投信</th><th class=l>成長</th><th class=l>動能</th><th>市值(億)</th><th>日均成交(億)</th></tr></thead>`;
  const rules=`<div class=rls>${ruleRows(S5.rule||[])}</div><div class=st>四項條件：投信 20 日買超 ≥ 股本 0.5%，且 20 天中 ≥12 天買超（另認：主動 ETF 20 日內 ≥2 家投信新建倉、投信 20 日未淨賣）；最新月營收年增 ≥20%、累計年增 ≥15%；收盤 > 60 日線 > 120 日線、60 日線上揚、距 120 日高點 20% 內、比低點高 30% 以上、120 日報酬全市場前 30%；市值 50～1,500 億、20 日均成交值 ≥1 億。</div>`;
  let m=sc.length?`<h4 class=sh>今日篩選（四項條件）</h4><div class=tw><table>${scHead}<tbody>${[...ok,...near].map(scRow).join('')}</tbody></table></div>`:'';
  let bt=`<div class=note>「曾翻倍」＝進場後 6／12 個月內最高價曾達進場價 2 倍（括號＝樣本數）；「照規則」＝依停損與回落出場的報酬（已扣成本）。基準＝同期所有市值與成交值符合條件的股票。只含目前仍上市的公司。</div>
<div class=tw><table><thead><tr><th>組別</th><th>篩出檔次</th><th>6 個月內曾翻倍</th><th>12 個月內曾翻倍</th><th>6 個月期末 平均／中位</th><th>照規則 平均／中位</th><th>獲利比例</th><th>平均賺／平均賠</th><th>照規則翻倍比例</th></tr></thead><tbody>`+
    gRow('基準',B.base)+gRow('只看動能',B.mom)+gRow('只看投信',B.trust)+gRow('投信＋動能',B.trust_mom)+gRow('四項全符合',B.all4)+`</tbody></table></div>`;
  const EX=B.exits||{},EL=B.exit_lbl||{};
  if(EX.trust_mom){bt+=`<h4 class=sh>出場方式比較</h4><div class=note>同一檔 6 個月內只算一次、只計進場滿 6 個月者。</div><div class=tw><table><thead><tr><th>出場方式</th><th>組別</th><th>筆數</th><th>平均</th><th>中位</th><th>獲利比例</th><th>平均賺／賠</th><th>翻倍比例</th><th>平均持有</th></tr></thead><tbody>`;
    for(const ek of Object.keys(EL)){for(const [gk,gl] of [['trust_mom','投信＋動能'],['mom','只看動能'],['base','基準']]){const x=(EX[gk]||{})[ek]||{};if(!x.n)continue;
      bt+=`<tr class="${gk==='trust_mom'?'':'grey'}"><td>${gk==='trust_mom'?esc(EL[ek]):''}</td><td>${gl}</td><td>${x.n}</td><td>${sgn(x.avg,1,'%')}</td><td>${sgn(x.med,1,'%')}</td><td>${x.win}%</td><td>${x.aw==null?'—':sgn(x.aw,1,'%')}／${x.al==null?'—':sgn(x.al,1,'%')}</td><td>${f(x.dbl,1)}%</td><td>${x.days} 日</td></tr>`;}}
    bt+=`</tbody></table></div>`;}
  m+=`<h4 class=sh>回測（${ms.length?`${ms[0].slice(0,7)}～${ms[ms.length-1].slice(0,7)}，`:''}每月篩一次）</h4>${bt}`+tradeLists(S5,true);
  return stSec('s5','長線',S5.name,S5.kind,[['結論',cclS(g,ex,'s5')],['操作規則',rules],['歷史績效',v3Grid('s5')+perfTbl(g,!!g3Of('s5'))],['本期名單',now],['風險',riskList(S5.risk)]],['今日篩選、回測與交易明細',m]);}

/* 月營收驚喜、財報驚喜（回測方法 v3，前 5 檔）：2013 起含已下市公司、價格含息；樣本外 2013～2021-09、樣本內 2021-10 起 */
const V3NAV={v7m:'營收中型',v7l:'營收大型',v3l:'財報大型',v3m:'財報中型'};
function subTxt(S,u){return (S||[]).map((x,i)=>{const nx=S[i+1];const lb=nx?`${x[0].slice(0,4)}～${(()=>{const y=+nx[0].slice(0,4),m=+nx[0].slice(5,7)-1;return m?`${y}-${String(m).padStart(2,'0')}`:`${y-1}`;})()}`:`${x[0].slice(0,7)} 起`;
  return `${esc(lb)} ${pctT(x[2],2)}（${x[1]} ${u}）`;}).join('｜');}
/* 資金曲線：本策略與同一批股票（同一段期間等權），對數刻度；虛線＝樣本外與樣本內分界 */
function curveChart(C,oe){if(!C||!(C.d||[]).length)return '';const n=C.d.length,W=stW(),HH=180,pl=46,pr=8,pt=14,pb=22;
  const vs=[...C.s,...C.e].filter(v=>v>0);if(!vs.length)return '';const lo=Math.log(Math.min(...vs)),hi=Math.log(Math.max(...vs)),rg=Math.max(.2,hi-lo);
  const x=i=>pl+(W-pl-pr)*(n>1?i/(n-1):.5),y=v=>pt+(HH-pt-pb)*(1-(Math.log(v)-lo)/rg);let s='';
  for(const t of [0.2,0.5,1,2,5,10,20,50,100,200,500]){const lt=Math.log(t);if(lt<lo-1e-9||lt>hi+1e-9)continue;const yy=y(t).toFixed(1);
    s+=`<line x1=${pl} x2=${W-pr} y1=${yy} y2=${yy} stroke="#e3e7ec"/><text x=${pl-5} y=${(+yy+4).toFixed(0)} font-size=11 fill="#727e8c" text-anchor=end>${t} 倍</text>`;}
  let ly='';C.d.forEach((d,i)=>{const yr=d.slice(0,4);if(yr!==ly){ly=yr;if(+yr%2===0)s+=`<text x=${x(i).toFixed(1)} y=${HH-6} font-size=11 fill="#727e8c" text-anchor=middle>${yr}</text>`;}});
  const k=oe?C.d.findIndex(d=>d>=oe):-1;
  if(k>0){const xx=x(k-.5).toFixed(1);s+=`<line x1=${xx} x2=${xx} y1=${pt-4} y2=${HH-pb} stroke="#9aa5b1" stroke-dasharray="3 3"/><text x=${(+xx-4).toFixed(0)} y=${pt+6} font-size=11 fill="#727e8c" text-anchor=end>樣本外</text><text x=${(+xx+4).toFixed(0)} y=${pt+6} font-size=11 fill="#727e8c">樣本內</text>`;}
  const path=a=>a.map((v,i)=>`${i?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  s+=`<path d="${path(C.e)}" fill=none stroke="#9aa5b1" stroke-width=1.5 /><path d="${path(C.s)}" fill=none stroke="#2563c9" stroke-width=2 />`;
  return `<svg width=${W} height=${HH} viewBox="0 0 ${W} ${HH}">${s}</svg><div class=lg><span><i style="background:#2563c9"></i>本策略（扣成本，期末 ${f(C.s[n-1],1)} 倍）</span><span><i style="background:#9aa5b1"></i>同一批股票（同一段期間等權，${f(C.e[n-1],1)} 倍）</span><span>縱軸為對數刻度</span></div>`;}
function v3Ccl(L,g){const R=L.res||{},o=R.oos||{},i=R.ins||{},u=L.unit;
  return `<div class=ccl><b>${g.grade}・${GDN[g.grade]}</b>（${GCAP[g.grade]}）</div>`+
    `<div>樣本外（${ym(o.d0)}～${ym(o.d1)}，${o.n} ${u}）每${u}平均報酬比同一批股票${hiLo(o.xe)}（t ${tT(o.t)}）；樣本內（${ym(i.d0)} 起，${i.n} ${u}）${hiLo(i.xe)}（t ${tT(i.t)}）。`+
    `扣成本後賺錢機率 ${o.win}%／${i.win}%、每月平均 ${p2(o.m)}／${p2(i.m)}（樣本外／樣本內）。</div>`+
    `<div class=sm2>${g.grade==='A'?'A 級條件全部符合。':`${g.grade==='B'?'未達 A 級':'評級原因'}：${esc((g.why||[]).join('；'))}。`}</div>`;}
function v3Perf(L){const R=L.res||{},o=R.oos||{},i=R.ins||{},u=L.unit,F=L.fwd||{},need=L.src==='p3'?2:10,cl=x=>x>0?'up':x<0?'dn':'';
  const N=R.nb||{},No=R.nb_oos||{},nd=Math.ceil((N.n||9)*2/3),ok=v=>v?'✓':'✗';
  const T=[kp('樣本外選股','樣本外',`${p2(o.xe)}／${u}`,`t ${tT(o.t)}・${o.n} ${u}・${ym(o.d0)}～${ym(o.d1)}`,cl(o.xe)),
    kp('樣本內選股','樣本內',`${p2(i.xe)}／${u}`,`t ${tT(i.t)}・${i.n} ${u}・${ym(i.d0)} 起`,cl(i.xe)),
    kp('賺錢機率','賺錢機率',`${o.win}%／${i.win}%`,'樣本外／樣本內'),
    kp('每月平均','每月平均',`${p2(o.m)}／${p2(i.m)}`,`賺賠比 ${o.ratio==null?'—':f(o.ratio,1)}／${i.ratio==null?'—':f(i.ratio,1)}`),
    kp('年化報酬','資金帳戶',`${pctT(o.cagr)}／${pctT(i.cagr)}`,`同一批股票 ${pctT(o.ew_cagr)}／${pctT(i.ew_cagr)}`),
    kp('最大回落','最大回落',`${o.mdd}%／${i.mdd}%`,`同一批股票 ${o.ew_mdd}%／${i.ew_mdd}%`),
    kp(`${ok(i.x2>0)} 成本加倍`,'成本加倍',`${p2(o.x2)}／${p2(i.x2)}`,'選股平均（外／內）',cl(i.x2)),
    kp(`${ok(N.pos>=nd)} 參數鄰近`,'參數鄰近',`${No.pos}／${No.n}・${N.pos}／${N.n}`,`贏同一批股票的組數（外・內）；A 級需 ≥${nd}`),
    kp(`${ok(i.drop5>0)} 去掉最好 5%`,'去掉最好 5%',`${p2(o.drop5)}／${p2(i.drop5)}`,'選股平均（外／內）',cl(i.drop5)),
    kp('前瞻驗證','前瞻驗證',`${F.n||0}／${need} ${u}`,F.n?`平均${bw(F.xe)}`:`${md(L.since)} 起算`)];
  return `<div class=sgd>${T.join('')}</div>`+
    `<div class=note>年化報酬與最大回落用資金帳戶${gi('資金帳戶')}計算；選股與賺錢機率以「同一期 5 檔等額平均」為一期，已扣成本（${L.b==='L'?'大型股來回 0.48%':'中型股來回 0.68%'}）。打 ✓／✗ 的三項是 A 級條件（看樣本內）。</div>`+
    `<div class=st style="margin-top:6px">分期（每${u}平均贏同一批股票）：${subTxt(R.sub,u)}。</div>`+
    `<h4 class=sh>資金曲線</h4>${curveChart(R.curve,V3M.oos_end)}`;}
function v3Now(L){const N=L.now,X=L.next,g=g3Of(L.k)||{};let h='';
  if(N&&(N.picks||[]).length){const per=L.src==='p7'?(N.ym?`${+N.ym.slice(5,7)} 月營收`:''):(N.q?`${qTxt(N.q)}財報`:'');
    h+=`<div class=tl><b>這一期${per?`（${esc(per)}）`:''}${g.grade==='C'?'：C 級，只做紙上記錄':''}</b><ol><li>${mdw(N.d)} 收盤決定：${N.n_uni} 檔有訊號，取最強 5 檔</li><li>${mdw(N.ent)} 開盤買進</li><li>${mdw(N.out)} 收盤${L.src==='p7'?'換股':'賣出'}</li></ol></div>`+
      `<div class=tw><table><thead><tr><th>股票</th><th>訊號${gi(L.src==='p7'?'月營收驚喜':'SUE')}</th><th>進場價</th><th>現價</th><th>報酬</th><th class=hm>市值(億)</th></tr></thead><tbody>`+
      N.picks.map(p=>`<tr class=v3r data-c="${esc(p.c)}"><td><span class=nm>${esc(p.n)}</span><span class=cd>${esc(p.c)}</span></td><td>${f(p.sc,1)}</td><td>${fp(p.entry)}</td><td>${fp(p.now)}</td><td>${p.now_r==null?'—':sgn(p.now_r,1,'%')}</td><td class=hm>${f(p.cap,0)}</td></tr>`+
        `<tr class=v3w data-c="${esc(p.c)}"><td colspan=6>${(p.why||[]).map(esc).join('；')}</td></tr>`).join('')+
      `</tbody></table></div><div class=note>報酬＝進場開盤價到最新收盤，未扣成本、不含息。</div>`;}
  else h+='<div class=mu>目前沒有持股。</div>';
  if(X){const per=L.src==='p7'?`${(+X.d.slice(5,7)+10)%12+1} 月營收`:(X.q?`${qTxt(X.q)}財報`:'');
    h+=`<div class=st style="margin-top:6px">下一期${per?`（${esc(per)}）`:''}：${mdw(X.d)} 收盤決定、${mdw(X.ent)} 開盤買進。前瞻紀錄從 ${md(L.since)} 起算${(L.fwd||{}).n?`，已記 ${L.fwd.n} 期`:'，下一期是第一期'}。</div>`;}
  return h;}
function v3Risk(L){const R=L.res||{},o=R.oos||{},i=R.ins||{},S=R.sub||[],u=L.unit,ev=L.src==='p3';
  const xs=[`只買 5 檔、等額：最大回落樣本外 ${o.mdd}%、樣本內 ${i.mdd}%（同一批股票 ${o.ew_mdd}%／${i.ew_mdd}%）`];
  const a=S.map(x=>x[2]).filter(v=>v!=null);
  if(a.length>1&&Math.max(...a)>0&&Math.min(...a)<Math.max(...a)/3)xs.push(`各期間差異大（每${u}贏同一批股票）：${subTxt(S,u)}`);
  xs.push(ev?`一年只有 4 期：樣本外 ${o.n} 期、樣本內 ${i.n} 期；每期持有約 3 個月，期間不設停損`:'月營收是單月數字：大訂單、匯率、去年同月基期都會讓單月跳動；多數公司在 10 日前公布，決定日當天股價可能已反映一部分');
  if(L.b==='M')xs.push('中型股成交量較小：買進張數 ≤ 20 日均量 2%；滑價以每邊 0.15% 估計');
  xs.push('回測的已下市公司只補「曾經月底市值 ≥40 億」者；股票股利的還原用 Yahoo 的數字');
  return xs;}
function v3Sec(k){const L=LV[k];if(!L)return '';const g=g3Of(k)||{grade:L.grade,why:L.why},R=L.res||{},N=R.nb||{};
  const rules=`<div class=rls>${ruleRows([`範圍：${L.bucket}`,...(L.rules||[]),ADV.cost3||''].filter(Boolean))}</div>`;
  const more=`<h4 class=sh>參數鄰近（樣本內，每${L.unit}贏同一批股票）</h4>${nbGrid(N)}`+
    (((R.ins||{}).q||[]).length?`<h4 class=sh>因子檢定${gi('因子檢定')}（依訊號分 5 組，各組每${L.unit}平均報酬、未扣成本，由弱到強）</h4><div class=st>樣本外：${(R.oos.q||[]).map(v=>pctT(v,2)).join('／')}（最強−最弱 ${pctT(R.oos.sp,2)}，t ${tT(R.oos.sp_t)}）<br>樣本內：${(R.ins.q||[]).map(v=>pctT(v,2)).join('／')}（最強−最弱 ${pctT(R.ins.sp,2)}，t ${tT(R.ins.sp_t)}）</div>`:'');
  return stSec(k,V3NAV[k]||L.name,L.name,`${L.src==='p7'?'每月換股':'每季換股'}・每期最強 5 檔・${L.b==='L'?'大型股':'中型股'}`,[['結論',v3Ccl(L,g)],['操作規則',rules],['歷史績效',v3Perf(L)],['本期名單',v3Now(L)],['風險',riskList(v3Risk(L))]],
    ['參數鄰近與因子檢定',more],gBadge(g.grade));}

/* 回測方法 v3：全部策略總表（docs/backtest_v3_plan.md 第 12、13 節）。舊的「資料包策略測試」（5 年資料、對加權指數）已由此取代 */
function bt3Sec(){const V=ADV.v3||{},B=V.basket||[],M=V.meta||{},P=ADV.pack||{};if(!B.length&&!Object.keys(LV).length)return '';
  const GK={p7:'月營收驚喜',p3:'SUE',p1:'相對強勢',p2:'趨勢樣板'};
  const side=(x,u)=>x&&x.n?`${p2(x.xe)}<span class=mu>／${u}</span><div class=sm2>t ${tT(x.t)}</div>`:'—';
  const row=(r,lbl)=>{const o=r.oos||{},i=r.ins||{},u=r.unit,N=r.nb||{},No=r.nb_oos||{};
    return `<tr><td class=l><span class=nm>${esc(lbl)}${GK[r.src]?gi(GK[r.src]):''}</span><span class=cd>${r.b==='L'?'大型股':'中型股'}・${r.ver==='top5'?'前 5 檔':'整組'}</span></td>`+
      `<td>${side(o,u)}</td><td>${side(i,u)}</td><td>${o.win==null?'—':o.win+'%'}／${i.win==null?'—':i.win+'%'}</td><td>${p2(o.m)}／${p2(i.m)}</td>`+
      `<td class=hm>${No.n?`${No.pos}／${No.n}・${N.pos}／${N.n}`:'—'}</td><td class=hm>${o.sp==null?'—':`${pctT(o.sp,2)}（t ${tT(o.sp_t)}）／${pctT(i.sp,2)}（t ${tT(i.sp_t)}）`}</td>`+
      `<td class=l>${gBadge(r.grade)}</td></tr>`;};
  const head=`<thead><tr><th class=l>策略</th><th>樣本外選股${gi('樣本外')}</th><th>樣本內選股${gi('樣本內')}</th><th>賺錢機率${gi('賺錢機率')}<div class=sm2>外／內</div></th><th>每月平均${gi('每月平均')}<div class=sm2>外／內</div></th><th class=hm>參數鄰近${gi('參數鄰近')}<div class=sm2>外・內</div></th><th class=hm>因子檢定${gi('因子檢定')}<div class=sm2>最強−最弱 外／內</div></th><th class=l>評級</th></tr></thead>`;
  const T5=Object.values(LV).map(L=>({...L.res,k:L.k,src:L.src,b:L.b,unit:L.unit,grade:L.grade,why:L.why,ver:'top5',name:L.name.replace(/（.*?）/,'')}));
  const only=r=>(r.why||[]).length===1&&/^前瞻/.test(r.why[0]);
  const all=[...T5,...B],nAB=all.filter(r=>r.grade==='A'||r.grade==='B'),near=all.filter(only),SO=['p7','p3','p1','p4','p2','p5'];
  const ord=all.slice().sort((a,b)=>(a.b===b.b?0:a.b==='M'?-1:1)||SO.indexOf(a.src)-SO.indexOf(b.src)||(a.ver==='top5'?-1:1)-(b.ver==='top5'?-1:1));
  const lb=r=>`${r.name}（${r.b==='L'?'大型股':'中型股'}${r.ver==='top5'?'・前 5 檔':'・整組'}）`,nA=all.filter(r=>r.grade==='A').length,L0=Object.values(LV)[0];
  let cc=nA?`${all.length} 個版本中 ${nA} 個 A 級、${nAB.length-nA} 個 B 級。`:`${all.length} 個版本中 ${nAB.length} 個達 B 級、沒有 A 級（A 級需要前瞻驗證${L0?`，從 ${md(L0.since)} 起算`:''}）。`;
  if(near.length)cc+=`只差前瞻驗證的：${near.map(r=>esc(lb(r))).join('、')}。`;
  const bad=B.filter(r=>(r.oos||{}).xe<0&&(r.ins||{}).xe<0);
  if(bad.length)cc+=`樣本內外都輸同一批股票：${[...new Set(bad.map(r=>r.name))].map(esc).join('、')}。`;
  const notes=[`資料：${ym(M.d0)}～${ym(M.d1)}，${f(M.n_codes,0)} 檔（含 ${f(M.n_finmind,0)} 檔之後下市），價格含息；市值用當時月底的官方收盤 × 發行股數；EPS 用公開資訊觀測站當時公布的數字；月營收 ${M.rev_m||'—'} 個月。`,
    `樣本外＝${ym(M.oos_end)} 之前，規則寫定後才第一次跑；樣本內＝${ym(M.oos_end)} 起。主規格在回測前寫定，結果出來後沒有改規則。`,
    `選股＝扣成本後對同一批股票（同一段期間、同一個範圍、含之後下市的公司）等權平均的超額，t 值用 Newey-West；${ADV.cost3||''}。`,
    '整組＝每期買訊號最強的 10%（財報驚喜 20%）；前 5 檔＝每期只買最強 5 檔，是本期操作用的版本。',
    '多重檢定：整組版本測了 12 組（6 種策略 × 2 個範圍）。只靠運氣時，12 組中至少一組 t ≥2.8 的機率約 6%。'];
  const alt=(P.rows||[]).filter(r=>!/^p\d$/.test(r.k));
  const altRow=r=>{const rb=r.rb||{},N=r.nb||{};return `<tr><td class=l><span class=nm>${esc(r.name)}${gi('CAN SLIM')}</span><div class="pkn pkr">${esc(r.rule)}</div></td><td>${r.n?`${r.n} ${r.unit}`:'—'}</td><td>${pctT(r.x)}<div class=sm2>${ciT(r.ci)}</div></td><td>${r.xwin==null?'—':r.xwin+'%'}</td><td class=hm>${pctT(rb.xe)}</td><td class=hm>${N.n?`${N.pos}／${N.n}`:'—'}</td><td class=l>${gBadge(r.grade)}</td></tr>`;};
  const S=(P.skipped||[]).map(x=>`<tr><td class=l>${esc(x[0])}</td><td class=l>${esc(x[1])}</td></tr>`).join('');
  return sec('st-bt3','總表','全部策略總表','2013 起、含已下市公司、樣本外驗證',`<div class=card><div class=ccl><b>結論</b></div><div>${cc}</div>`+
    `<div class=tw style="margin-top:8px"><table>${head}<tbody>${ord.map(r=>row(r,r.name)).join('')}</tbody></table></div>`+
    `<ol class=rkl style="margin-top:8px">${notes.map(x=>`<li class=note>${esc(x)}</li>`).join('')}</ol>`+
    (alt.length?`<details class=mr><summary>長線策略加上 CAN SLIM 兩項條件（對照，舊方法：對加權指數、2024 起）</summary><div class=tw><table><thead><tr><th class=l>做法</th><th>樣本</th><th>平均超額${gi('信賴區間')}</th><th>贏大盤</th><th class=hm>對同一批股票</th><th class=hm>參數鄰近</th><th class=l>評級</th></tr></thead><tbody>${alt.map(altRow).join('')}</tbody></table></div></details>`:'')+
    (S?`<details class=mr><summary>沒有採用的項目與原因</summary><div class=tw><table class=skt><tbody>${S}</tbody></table></div></details>`:'')+`</div>`);}

function riskSec(){const R=(ADV.rule||[]).filter(r=>r&&r.g);
  return sec('st-risk','風控','部位與風控','',`<div class=card><h4 class=sh style="margin-top:0">評級${gi('評級')}</h4>`+
    `<div class=tw><table><thead><tr><th>評級</th><th class=l>條件</th><th class=l>部位上限</th></tr></thead><tbody>${R.map(r=>`<tr><td>${gBadge(r.g)}</td><td class="l wr2">${esc(r.cond)}</td><td class=l>${esc(r.cap)}</td></tr>`).join('')}</tbody></table></div>`+
    `<div class=note>${esc(ADV.pay3||'')}${gi('報酬型態')}</div><div class=note>${esc(ADV.cost3||'')}</div><div class=note>選股＝平均贏同一批股票${gi('同一批股票的平均')}；t 值${gi('t 值')}樣本內看 2021-10 起，樣本外看 2013～2021-09。</div>`+
    `<h4 class=sh>部位與交易限制</h4><div class=rls>${ruleRows([totPos(),'部位：A 級每檔 ≤ 總資金 5%、B 級 ≤ 2%、C 級不下單；有停損價時，部位另以「停損時虧損 ≤ 總資金 0.5%」計算，取較小者',
      '檔數：每條策略每期最多 5 檔（依各自規則的排序）；同一檔被兩條以上策略選到時不重複加碼',
      '流動性：買進張數 ≤ 20 日均量 2%','排除：注意股、處置股不買進',
      '資料：月營收驚喜、財報驚喜有 2013～2021 的樣本外驗證；共識加碼、臺灣50、長線、高股息只有 2024～2025 起的資料。規則起算後的交易另記前瞻成績，A 級須前瞻驗證達標'])}</div></div>`);}
function totPos(){const P=(ADV.picks||[]).filter(p=>p.size&&p.size.pct);const t=P.reduce((a,p)=>a+p.size.pct,0),h=P.filter(p=>p.act==='持有中').length;
  return P.length?`總部位：本期操作清單 ${P.length} 檔（新佈局 ${P.length-h} 檔、持有中 ${h} 檔），全部照做合計約占總資金 ${f(t,0)}%`:'總部位：本期操作清單沒有部位';}
const SECF={s1:()=>s1Sec(),s3:()=>s3Sec(),s5:()=>s5Sec(),hd:()=>hdSec()};
/* 各策略段落的順序＝評級總表的順序（評級、證據強弱） */
function stSecs(){const done=new Set();let h='';
  for(const g of (ADV.grades3||[])){const k=g.k;if(done.has(k))continue;done.add(k);h+=LV[k]?v3Sec(k):SECF[k]?SECF[k]():'';}
  for(const k of Object.keys(LV))if(!done.has(k)){done.add(k);h+=v3Sec(k);}
  for(const k of ['s1','s3','hd','s5'])if(!done.has(k))h+=SECF[k]();
  return h;}
function vSt(){
  const X=D.strat||{};
  let h=`<div class=intro>每天收盤後依固定規則產生名單。評級看三件事，都扣成本後算：平均有沒有贏同一批股票${gi('同一批股票的平均')}、賺錢機率與每月平均夠不夠${gi('報酬型態')}、成本加倍與參數稍微改動後還在不在${gi('穩健度檢查')}；有 2013～2021 樣本外資料${gi('樣本外')}的策略另看樣本外是否同方向。A 可執行、B 小部位試行、C 不推薦${gi('評級')}。</div>`;
  if(X.err)h+=`<div class=st>策略資料錯誤：${esc(X.err)}</div>`;
  if(ADV.err)h+=`<div class=st>評級資料錯誤：${esc(ADV.err)}</div>`;
  if((D.adv||{}).v3err)h+=`<div class=st>月營收驚喜、財報驚喜資料錯誤：${esc(D.adv.v3err)}</div>`;
  h+=nowSec()+gradeSec()+stSecs()+bt3Sec()+riskSec();
  $('#main').innerHTML=h;
  $$('#main [data-to]').forEach(a=>a.onclick=e=>{e.preventDefault();jump(a.dataset.to);});
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
