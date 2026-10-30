"""選股頁（arm/lab/pickpage.py；docs/lab_pick_page_plan.md）：台股｜美股＝進場行事曆＋每條策略一張卡；原本的配置搬到研究紀錄。
台股推薦架構（docs/lab_pick_arch_plan.md 第 3 節）：買不買只看那條策略自己的規則，「買」的旁邊不放別的方法的價位。"""
import json
import re
import shutil
import subprocess

import pytest

from arm.lab import page
from arm.lab import pickpage as PP
from test_corepage import BANNED, _text

# 主頁面用字（wiki/lab/plain-words.md；test_plain 用瀏覽器掃整頁，這裡先擋 Python 組的卡片）
PLAIN_BAD = ("判定", "樣本", "研究", "注意", "門檻", "VER", "★", "●", "○", "◆", "核心", "衛星", "警訊", "占全部資金", "配置", "→")
# 書上（《超級績效》）的位置與參考價位：新飆股不等買點，「買」的旁邊不准出現（使用者 2026-10-30：「明明很多都還沒有到買點，這樣為什麼會買」）
BOOK = ("突破", "才算", "等拉回", "還差", "52 週高點", "參考買點", "打底中", "漲太遠")      # 「停損」不算：長線自己的出場規則有


def _P():
    return {"d": "2026-10-28", "next": "2026-10-29", "next_wk": "2026-10-30", "wk": "2026-10-22", "hold_n": 60, "take": "2026-10-22",
            "n_list": 30, "list": [{"c": "2454", "n": "聯發科", "rs": 97.0, "why": ["符合：強度 97（要 90 以上）"]},
                                   {"c": "2330", "n": "台積電", "rs": 95.0, "why": []}],
            "hold": [{"c": "2330", "n": "台積電", "ent": "2026-08-24", "epx": 1100.0, "px": 1210.0, "r": 0.1, "w": 0.12, "due": "2026-11-23",
                      "out": "2026-11-24", "sell": False, "bt": True, "rl": 0.02, "why": ["8/21 那週名單第 1 名"]}],
            "buy": [{"c": "2454", "n": "聯發科", "rs": 97.0, "fill": True, "why": []}], "trial": []}


def _P8():
    """N8（8 格那一本）還沒有部位、這一週到 10/28 收盤的試算名單 4 檔（sxlive.pick_state 的格式：沒有書上的買點）。"""
    rows = [{"c": "6870", "n": "騰雲", "rs": 92.0, "wk": 1, "why": ["符合：強度 92（要 90 以上）"], "px": 391.5},
            {"c": "5351", "n": "鈺創", "rs": 90.0, "wk": 1, "why": [], "px": 114.0},
            {"c": "3008", "n": "大立光", "rs": 95.0, "wk": 3, "why": [], "px": 6335.0},
            {"c": "3605", "n": "宏致", "rs": 95.0, "wk": 3, "why": [], "px": 171.5}]
    pick = {"d": "2026-10-28", "last": "2026-10-28", "trial": True, "n": 4, "top": 8, "rows": rows,
            "px": {r["c"]: r["px"] for r in rows}}
    return {"d": "2026-10-28", "next": "2026-10-29", "next_wk": "2026-10-30", "wk": None, "hold_n": 60, "slots": 8, "take": None,
            "n_list": 0, "list": [], "hold": [], "buy": [], "trial": [], "pick": pick}


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
    s3 = V["cards"][V["cards"].index('id="pk-s3"'):]
    order = [s3.index(x) for x in ("選什麼", "什麼時候", "怎麼分錢", "過去照做", "現在拿著")]
    assert order == sorted(order)
    assert 'data-c="2303" data-co="2303"' in V["cards"]                              # 每一檔點了開個股卡
    assert "11/13 收盤賣" in V["cards"] and "8/17 買（回測）" in V["cards"]
    assert "分 8 格" in V["cards"] and "5 檔等額" in V["cards"]
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
    co = sorted({e[0] for e in pick["tw"]["ev"] if e[4] and e[2] in out["on"]})   # 接下來只列已經知道是哪幾檔的買賣
    assert out["ag"].count("class=pkagd") == min(6, len(co)) and ("再看" in out["ag"]) == (len(co) > 6)
    assert "會出新名單的日子" in out["ag"] and "新飆股 10/30" in out["ag"]
    assert "聯電" in nov and "class=pkdots" in nov                                     # 格子寫公司名、還不知道是哪幾檔的縮成小點
    assert "財報驚喜" in out["day"] and "聯電" in out["day"] and 'data-c="2303"' in out["day"]


def test_boom_box_trial_statuses_and_card_sections():
    """新飆股（N8，從現金開始）：試算名單照規則會買前 8 格；列只有這條策略自己的欄（沒有書上的位置與參考價位）；
    卡片＝接下來 → 我的 → 這週名單 → 為什麼不等買點 → 名單位置圖 → 規則（收起）→ 照規則的紀錄；原本的飆股名單只留一行連到研究紀錄。"""
    P = _P8()
    X = PP.boom_box(P)
    assert [r[6] for r in X["rows"]] == ["b", "b", "b", "b"] and X["trial"] and X["buyd"] == "2026-11-02" and X["fix"] == "2026-10-30"
    assert X["rows"][0] == ["6870", "騰雲", 92.0, 1, "符合：強度 92（要 90 以上）", 391.5, "b"]
    assert "old" not in X and "spot" not in X and X["td"][0] < "2026-10-28" < X["td"][1]
    P2 = dict(P, hold=[{"c": f"{9000 + i}", "n": "x", "sell": False} for i in range(7)])     # 7 格滿了：只剩 1 格
    assert [r[6] for r in PP.boom_box(P2)["rows"]] == ["b", "w", "w", "w"]
    V = PP.tw_view({"adv": _A(), "n8": P}, {"R": {}}, today="2026-10-28")
    c = V["cards"][V["cards"].index('id="pk-boom"'):V["cards"].index('id="pk-s3"')]
    order = [c.index(x) for x in ("接下來", 'id="pkmine"', 'id="pkbx"', "不等買點", "名單位置圖", "規則、過去照做、風險", "照規則的紀錄")]
    assert order == sorted(order)
    assert "買 4 檔" in c and "騰雲" in c and "11/2（一）開盤" in c
    assert 'id="pkold"' not in c and 'data-at="cf-tw-sx"' in c                              # 原本的飆股名單在研究紀錄
    c2 = re.sub(r'<p class="pknw">.*?</p>', "", c)                                         # 「為什麼不等買點」那段在講回測結果
    for w in BOOK:
        assert w not in c2, w
    assert V["pos"]["6870"][0]["k"] == "boom" and "試算" in V["pos"]["6870"][0]["t"]          # 個股卡也看得到「照規則會買」
    if PP.w10():
        assert "2019 年起照做一年" in c and "原本每檔 12.5%" in c


def test_calendar_lists_trial_buys_with_names():
    from arm.lab import pickcal as PC
    ev = PC.boom_events(_P8(), "2026-12-31")
    b = [e for e in ev if e["d"] == "2026-11-02" and e["act"] == "買進"]
    assert len(b) == 1 and [i["n"] for i in b[0]["items"]] == ["騰雲", "鈺創", "大立光", "宏致"] and "試算" in b[0]["note"]
    assert any(e["d"] == "2026-10-30" and e["act"] == "名單" and e["proj"] for e in ev)


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_mine_sell_date_and_calendar_events():
    """自己標「已買」的：照規則買進後第 60 個交易日收盤到期、隔天開盤賣（證交所休市表）；行事曆多一列「我的」。"""
    P = _P8()
    V = PP.tw_view({"adv": _A(), "n8": P, "sx_pos": {}}, {"R": {}}, today="2026-10-28")
    pick = {"tw": {k: V[k] for k in ("d", "end", "ev", "ks", "hol", "names", "bx")}}
    out = _node("""globalThis.localStorage={_:{labPickMine:JSON.stringify({'6870':{s:'b',n:'騰雲',d:'2026-10-29',p:391.5},'5351':{s:'w',n:'鈺創',d:'2026-10-28',p:114}})},getItem(k){return this._[k]||null;},setItem(k,v){this._[k]=v;}};
const s=pkSell('2026-10-29'),m=pkMineEvs('tw');console.log(JSON.stringify({s,m,lt:pkLastTd('2026-11-01')}));""", pick)
    from arm.lab import pickcal as PC
    assert out["s"]["due"] == PC.nth_day("tw", "2026-10-29", 60) and out["s"]["out"] == PC.nth_day("tw", "2026-10-29", 61)
    assert len(out["m"]) == 1 and out["m"][0][0] == out["s"]["out"] and out["m"][0][2] == "mine" and out["m"][0][4] == [["6870", "騰雲"]]
    assert out["lt"] == "2026-10-30"


def test_week_rows_main_strategies_with_their_own_rules():
    """最上面「這週要做的事」：接下來 5 個交易日、只有主要策略；買的每一列都有策略、日期、開盤／收盤、條件、什麼時候賣；
    還不知道是哪幾檔的（會出新名單的日子）另一行。"""
    V = PP.tw_view({"adv": _A(), "n8": _P8()}, {"R": {}}, today="2026-10-28")
    from arm.lab import pickcal as PC
    evs = PC.tw_events(_A(), _P8(), None, ["boom", "s3", "v3l", "v7l"], "2026-10-28")["ev"]
    W = PP.week_rows(evs, "2026-10-28", ["boom", "s3", "v3l"])
    assert (W["a"], W["b"]) == ("2026-10-29", "2026-11-04")                             # 10/29～11/4（週末不算）
    assert [(r["d"], r["at"], r["k"], r["act"]) for r in W["rows"]] == [("2026-11-02", "開盤", "boom", "買進")]
    r = W["rows"][0]
    assert [i[1] for i in r["items"]] == ["騰雲", "鈺創", "大立光", "宏致"] and "試算" in r["note"]
    assert r["cond"] == "開盤直接買，不等買點" and r["exit"] == "抱 60 個交易日"
    assert W["fix"] == [["boom", [["2026-10-30", "收盤"]]]]
    t = V["todo"]
    assert 'id="pk-tw-todo"' in t and "這週要做的事" in t and "10/29（四）～11/4（三）" in t
    assert 'data-c="6870" data-co="6870"' in t and 'data-to="pk-boom"' in t and "會出新名單的日子" in t
    for w in BOOK + PLAIN_BAD:
        assert w not in _text(t), w


def test_buy_rows_agree_everywhere():
    """一份動作表、處處一致（第 3.1 節第 4 條）：最上面的表、新飆股名單「會買」、個股卡的策略段是同一批股票。"""
    from arm.lab import pickcal as PC
    for P in (_P8(), _P()):
        V = PP.tw_view({"adv": _A(), "n8": P}, {"R": {}}, today="2026-10-28")
        evs = PC.tw_events(_A(), P, None, ["boom", "s3", "v3l"], "2026-10-28")["ev"]
        W = PP.week_rows(evs, "2026-10-28", ["boom", "s3", "v3l"])
        top = {c for r in W["rows"] if r["k"] == "boom" and r["act"] == "買進" for c, _ in r["items"]}
        card = {c for c, v in V["pos"].items() if any(q["k"] == "boom" and not q["h"] for q in v)}
        assert top and top == card, (top, card)
        if V["bx"]:
            assert top == {r[0] for r in V["bx"]["rows"] if r[6] == "b"}
        for r in W["rows"]:
            assert r["d"] and r["at"] in ("開盤", "收盤") and r["k"] in PC.SHORT
            if r["act"] != "賣出":
                assert r["cond"] and r["exit"], r


def test_every_strategy_states_its_entry_condition_and_exit():
    for k, m in PP.META.items():
        if k != "qm":
            assert m.get("cond") and m.get("exit"), k
            for w in BOOK:
                assert w not in m["cond"], (k, w)


def test_nowait_text_from_the_backtests():
    W = PP.w10()
    t = PP.nowait_txt(W)
    assert t.startswith("這條不等買點：名單出來，下一個交易日開盤就買。") and "到條件才買" in t
    if W.get("pick") and W.get("skip") and W.get("book"):
        assert "漲太遠先不買，一年" in t and "照書上的選股和買點，一年" in t and "2022 年" in t
    assert PP.nowait_txt({}) == "這條不等買點：名單出來，下一個交易日開盤就買。之後會試「到條件才買」（開低、拉回、創新高），比較好才換。"


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_boom_list_and_chart_in_browser():
    """瀏覽器畫的名單（7 欄、沒有位置・參考買點欄）與名單位置圖（橫軸上名單第幾週、縱軸強度、同一欄強度一樣的錯開）。"""
    V = PP.tw_view({"adv": _A(), "n8": _P8()}, {"R": {}}, today="2026-10-28")
    pick = {"tw": {k: V[k] for k in ("d", "end", "ev", "ks", "hol", "names", "bx")}}
    out = _node("""globalThis.f=(x,d)=>String(Math.round(x));globalThis.fp=x=>String(x);
const mk=()=>({clientWidth:360,innerHTML:'',closest(){return null;},querySelectorAll(){return [];}}),bx=mk(),sp=mk(),ky=mk();
globalThis.$=s=>s==='#pkbx'?bx:s==='#pkspot'?sp:s==='#pkspotk'?ky:null;
pkBxDraw();const b=bx.innerHTML;PKBS.f='a';pkBxDraw();pkSpot();
console.log(JSON.stringify({b,a:bx.innerHTML,sp:sp.innerHTML,ky:ky.innerHTML}));""", pick)
    assert out["b"].count("<tr><td class=l>") == 4 and "11/2（一）開盤買" in out["b"] and "11/2 開盤會買" in out["b"]
    assert "<th class=hm>上名單</th>" in out["a"] and "位置" not in out["a"]
    for w in BOOK:
        assert w not in out["b"] and w not in out["a"], w
    sp = out["sp"]
    assert sp.count("<circle") == 4 and "新上名單" in sp and "第 3 週" in sp and "27 週以上" in sp and "上名單第幾週" in sp
    xy = re.findall(r"cx=([\d.]+) cy=([\d.]+)", sp)
    assert len(set(xy)) == 4                                                            # 大立光、宏致同一欄同強度：左右錯開
    assert re.findall(r"<text class=pkspn[^>]*>(\d)</text>", sp) == ["1", "2", "3", "4"]     # 會買的點裡寫買的順序
    assert re.findall(r'<b>(\d)</b><a data-c="\d+" data-co="\d+">([^<]+)</a>', out["ky"]) == \
        [("1", "騰雲"), ("2", "鈺創"), ("3", "大立光"), ("4", "宏致")]                          # 名字在圖下面一行，照順序
