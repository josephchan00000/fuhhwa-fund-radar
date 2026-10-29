"""選股頁（arm/lab/pickpage.py；docs/lab_pick_page_plan.md）：台股｜美股＝進場行事曆＋每條策略一張卡；原本的配置搬到研究紀錄。"""
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import page
from arm.lab import pickpage as PP
from test_corepage import BANNED, _text

# 主頁面用字（CLAUDE.md「主頁面用字」；test_plain 用瀏覽器掃整頁，這裡先擋 Python 組的卡片）
PLAIN_BAD = ("判定", "樣本", "研究", "注意", "門檻", "VER", "★", "●", "○", "◆", "核心", "衛星", "警訊", "占全部資金", "配置", "→")


def _P():
    return {"d": "2026-10-28", "next": "2026-10-29", "next_wk": "2026-10-30", "wk": "2026-10-22", "hold_n": 60, "take": "2026-10-22",
            "n_list": 30, "list": [{"c": "2454", "n": "聯發科", "rs": 97.0, "why": ["符合：強度 97（要 90 以上）"]},
                                   {"c": "2330", "n": "台積電", "rs": 95.0, "why": []}],
            "hold": [{"c": "2330", "n": "台積電", "ent": "2026-08-24", "epx": 1100.0, "px": 1210.0, "r": 0.1, "w": 0.12, "due": "2026-11-23",
                      "out": "2026-11-24", "sell": False, "bt": True, "rl": 0.02, "why": ["8/21 那週名單第 1 名"]}],
            "buy": [{"c": "2454", "n": "聯發科", "rs": 97.0, "fill": True, "why": []}], "trial": []}


def _A():
    book = [{"k": "s3", "name": "臺灣50 提前卡位", "tier": "good", "rank": 1, "unit": "次",
             "exp": {"n": 8, "avg": 11.6, "med": 11.9, "win": 88, "lo": -3.6, "mk": 6.3, "d0": "2024-10", "d1": "2026-07"}},
            {"k": "v3l", "name": "財報驚喜（大型股）", "tier": "good", "rank": 2, "unit": "次",
             "exp": {"n": 49, "avg": 13.0, "med": 6.9, "win": 65, "lo": -28.2, "mk": 6.4, "d0": "2014-05", "d1": "2026-05"},
             "all": {"cagr": 30.4, "tr_cagr": 19.1, "mdd": 52.0, "tr_mdd": 29.0}},
            {"k": "v7l", "name": "月營收驚喜（大型股）", "tier": "ref", "rank": 5, "unit": "次", "exp": {"n": 158, "avg": 2.1, "win": 58, "lo": -20}},
            {"k": "hd", "name": "高股息換股", "tier": "ref", "rank": None},
            {"k": "s1", "name": "共識加碼", "tier": "none", "rank": None}]
    picks = [{"k": "v3l", "c": "2303", "n": "聯電", "act": "持有中", "ent": "2026-08-17", "entry": 121.5, "now": 128.0, "now_r": 5.35,
              "out": "2026-11-13", "bt": True, "rl": -0.041, "why": ["EPS 成長"]},
             {"k": "v7l", "c": "2345", "n": "智邦", "act": "持有中", "ent": "2026-10-13", "entry": 2090.0, "now": 1815.0, "now_r": -13.2,
              "out": "2026-11-10", "why": []}]
    cal = [{"d": "2026-11-13", "at": "收盤", "k": "v3l", "act": "賣出", "items": [{"c": "2303", "n": "聯電"}], "note": "8/17 買進的"},
           {"d": "2026-11-17", "at": "開盤", "k": "v3l", "act": "買進", "items": [], "pending": True, "fix": "2026-11-16"},
           {"d": "2026-11-10", "at": "收盤", "k": "v7l", "act": "換股", "items": [{"c": "2345", "n": "智邦"}]}]
    live = {"v3l": {"next": {"d": "2026-11-16", "ent": "2026-11-17", "q": "2026-09-30"}},
            "v7l": {"next": {"d": "2026-11-10", "ent": "2026-11-11"}}}
    return {"last": "2026-10-28", "book": book, "picks": picks, "cal": cal, "v3": {"live": live}}


def test_keys_boom_first_then_good_by_rank_others_folded():
    main, other = PP.tw_keys(_A(), _P())
    assert main == ["boom", "s3", "v3l"] and other == ["v7l"]                      # 高股息只當避開清單、○／— 不列
    assert PP.tw_keys(_A(), None)[0] == ["s3", "v3l"]                                 # 沒有新飆股那本帳


def test_tw_view_cards_calendar_and_positions():
    V = PP.tw_view({"adv": _A(), "n8": _P()}, {"R": {}}, today="2026-10-28")
    assert [k[0] for k in V["ks"]] == ["boom", "s3", "v3l", "v7l"] and [k[3] for k in V["ks"]] == [1, 1, 1, 0]
    assert [k[2] for k in V["ks"]] == [1, 2, 3, 0]                                    # 主要的有身分色、其他的灰色
    for k in ("boom", "s3", "v3l"):
        assert f'id="pk-{k}"' in V["cards"], k
    assert 'id="pk-v7l"' in V["others"] and "pk-v7l" in V["olist"]
    order = [V["cards"].index(x) for x in ("選什麼", "什麼時候", "怎麼分錢", "過去照做", "現在拿著")]
    assert order == sorted(order)
    assert 'data-c="2303" data-co="2303"' in V["cards"]                              # 每一檔點了開個股卡
    assert "11/13 收盤賣" in V["cards"] and "8/17 買（回測）" in V["cards"]
    assert "每次買進用這條策略 12.5% 的錢" in V["cards"] and "5 檔等額" in V["cards"]
    ev = V["ev"]
    assert all(len(e) == 7 for e in ev)
    keys = [(e[0], {"開盤": 0, "": 1, "收盤": 2}[e[1]]) for e in ev]
    assert keys == sorted(keys)
    assert ["2026-10-29", "開盤", "boom", "買進", [["2454", "聯發科"]], "10/22 那週的名單", 0] in ev
    assert any(e[2] == "boom" and e[3] == "名單" and e[0] == "2026-10-30" and e[6] == 1 for e in ev)
    assert V["pos"]["2330"][0]["k"] == "boom" and V["pos"]["2330"][0]["h"] == 1 and V["pos"]["2454"][0]["h"] == 0
    assert "2026-10-23" in V["hol"] and V["end"] == "2027-01-31"                      # 颱風休市、第三個月底


def test_cards_use_plain_words():
    V = PP.tw_view({"adv": _A(), "n8": _P()}, {"R": {}}, today="2026-10-28")
    t = _text(V["cards"] + V["others"] + V["olist"]).replace("研究紀錄", "")      # 連到研究紀錄頁的小字（同 test_plain 的 ALLOW）
    for w in BANNED + PLAIN_BAD:
        assert w not in t, w


def test_us_view_without_weekly_record_says_so():
    V = PP.us_view({}, {"qm": None}, today="2026-10-28")
    assert V.get("err") and V["ev"] == [] and V["ks"] == []


def test_build_survives_errors():
    out = PP.build({"adv": "壞掉"}, {"stk": {"boom": _P()}}, today="2026-10-28")
    assert set(out) == {"tw", "us"} and ("err" in out["tw"] or out["tw"].get("cards") is not None)


def test_js_names_prefixed_and_page_wiring():
    names = re.findall(r"^function (\w+)\(|^(?:const|let) (\w+)", PP.JS, re.M)
    flat = [a or b for a, b in names]
    assert flat and all(n.startswith(("pk", "PK", "vPk", "vPick", "PICK")) for n in flat), flat
    html = page.render({"etfs": {}, "asof": {}, "pick": {"tw": {"err": "x"}}})
    assert "const PICK=D.pick||{};" in html and PP.CSS.split("\n", 2)[1] in html
    assert "if(at&&/^cf-(tw|us)/.test(at)" in page._JS                               # 原本配置頁的段落 → 研究紀錄・交易計畫
    css_cls = set(re.findall(r"\.(pk[\w-]*)", PP.CSS))
    assert css_cls and all(c.startswith("pk") for c in css_cls)


_STUB = """globalThis.document={addEventListener(){},documentElement:{}};globalThis.addEventListener=()=>{};globalThis.innerWidth=400;
globalThis.matchMedia=()=>({matches:false});globalThis.$$=()=>[];globalThis.$=()=>null;
globalThis.esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;');globalThis.D={pick:%s};globalThis.S={tab:'tw'};"""


def _node(body: str, pick: dict):
    prog = (_STUB % json.dumps(pick, ensure_ascii=False)) + PP.JS + "\n" + body
    r = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_calendar_month_agenda_and_phone_start():
    V = PP.tw_view({"adv": _A(), "n8": _P()}, {"R": {}}, today="2026-10-28")
    pick = {"tw": {k: V[k] for k in ("d", "end", "ev", "ks", "hol", "names")}}
    out = _node("""const S0=pkState('tw'),ms=pkMonths('tw'),evs=pkEvs('tw');
console.log(JSON.stringify({m:S0.m,ms,left:pkLeft(PICK.tw),on:[...S0.on],
  nov:pkMonth('tw','2026-11',evs),oct:pkMonth('tw','2026-10',evs),ag:pkAgenda('tw',evs),day:pkDay('tw','2026-11-13',evs)}));""", pick)
    assert out["ms"] == ["2026-10", "2026-11", "2026-12", "2027-01"] and out["left"] == 2
    assert out["m"] == "2026-11"                                                     # 手機：這個月剩 2 個交易日，從 11 月開始
    assert out["on"] == ["boom", "s3", "v3l"]                                         # 其他策略預設不顯示
    nov = out["nov"]
    assert nov.count('class="pkd') == 21 and 'data-pkd="2026-11-02"' in nov          # 11 月 21 個平日（11/1 週日不排）
    assert "2026-11-10" in nov and "營收大型" not in nov                              # 其他策略預設關掉
    assert "休市" in out["oct"] and 'data-pkd="2026-10-23"' in out["oct"]
    assert out["ag"].count("class=pkagd") == PP.JS.count("PKAG=6") * 6 and "再看" in out["ag"]
    assert "財報驚喜" in out["day"] and "聯電" in out["day"] and 'data-c="2303"' in out["day"]
