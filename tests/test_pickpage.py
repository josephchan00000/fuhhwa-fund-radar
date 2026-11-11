"""選股頁（arm/lab/pickpage.py；docs/lab_pick_page_plan.md）：台股｜美股＝成績單＋這週要做的事＋進場行事曆＋每條策略一張卡（同一個模板，
docs/lab_stock_page_plan.md 第 4.1 節）；原本的配置搬到研究紀錄。
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
              "out": "2026-11-13", "bt": True, "rl": -0.041, "since": "2026-10-15", "why": ["EPS 成長"]},
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
    v3 = V["cards"][V["cards"].index('id="pk-v3l"'):]
    order = [v3.index(x) for x in ("現在拿著", "pkht", "接下來", "規則、過去照做、風險", "<dt>選什麼", "<dt>什麼時候", "<dt>怎麼分錢", "<dt>過去照做")]
    assert order == sorted(order)                                                    # 先看手上的與接下來，規則收起來
    assert 'data-c="2303" data-co="2303"' in V["cards"]                              # 每一檔點了開個股卡
    assert "11/13 收盤賣" in V["cards"] and '8/17 121.5<span class="pkbt">回測</span>' in V["cards"] and "上線以來 −4.1%" in V["cards"]
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
    卡片＝（現在拿著）→ 接下來 → 我的 → 這週名單（8 格＋排隊）→ 為什麼不等買點 → 規則（收起）；原本的飆股名單只留一行連到研究紀錄。
    名單位置圖 2026-10-30 拿掉（使用者：「完全看不懂」；docs/lab_pick_arch_plan.md 第 9 節）。"""
    P = _P8()
    X = PP.boom_box(P)
    assert [r[6] for r in X["rows"]] == ["b", "b", "b", "b"] and X["trial"] and X["buyd"] == "2026-11-02" and X["fix"] == "2026-10-30"
    assert X["rows"][0] == ["6870", "騰雲", 92.0, 1, "符合：強度 92（要 90 以上）", 391.5, "b"]
    assert "old" not in X and "spot" not in X and X["td"][0] < "2026-10-28" < X["td"][1] and X["hold"] == []
    P2 = dict(P, hold=[{"c": f"{9000 + i}", "n": "x", "sell": False, "out": "2026-12-01"} for i in range(7)])     # 7 格滿了：只剩 1 格
    X2 = PP.boom_box(P2)
    assert [r[6] for r in X2["rows"]] == ["b", "w", "w", "w"] and X2["hold"][0] == ["9000", "x", "2026-12-01", False] and len(X2["hold"]) == 7
    V = PP.tw_view({"adv": _A(), "n8": P}, {"R": {}}, today="2026-10-28")
    from arm.lab import eqqueue as Q                    # 個股報告每天晚上那班讀同一份事件（10/30 名單改 7 欄時，舊的讀法漏改過一次）
    page = "const D=" + json.dumps({"pick": {"tw": V}}, ensure_ascii=False, separators=(",", ":")) + ";"
    assert [c["code"] for c in Q.upcoming("2026-10-30", page, {})] == [r[0] for r in X["rows"] if r[6] == "b"]
    c = V["cards"][V["cards"].index('id="pk-boom"'):V["cards"].index('id="pk-s3"')]
    order = [c.index(x) for x in ("接下來", 'id="pkmine"', 'id="pkbx"', "不等買點", "規則、過去照做、風險")]
    assert order == sorted(order) and "名單位置圖" not in c and "pkspot" not in c
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


def _P8h():
    """拿著 6 檔（台積電這次賣、聯發科還在名單上）、試算名單 10 檔：空 3 格。列已經照 N8 的順序（上名單週數少的先、週數一樣比強度）。"""
    P = _P8()
    L = [("6870", "騰雲", 92, 1), ("5351", "鈺創", 90, 1), ("2330", "台積電", 99, 2), ("3008", "大立光", 95, 3), ("3605", "宏致", 95, 3),
         ("2454", "聯發科", 88, 3), ("2317", "鴻海", 99, 5), ("1101", "台泥", 97, 9), ("2603", "長榮", 80, 9), ("2002", "中鋼", 70, 12)]
    rows = [{"c": c, "n": n, "rs": float(rs), "wk": w, "why": [], "px": 100.0} for c, n, rs, w in L]
    hold = [{"c": c, "n": n, "out": o, "due": o, "sell": c == "2330"} for c, n, o in
            (("2330", "台積電", "2026-11-02"), ("2454", "聯發科", "2026-12-01"), ("9001", "甲", "2026-11-20"),
             ("9002", "乙", "2026-11-10"), ("9003", "丙", "2026-12-15"), ("9004", "丁", "2026-11-25"))]
    return dict(P, hold=hold, pick=dict(P["pick"], rows=rows, n=len(rows), px={r["c"]: r["px"] for r in rows}))


def _queue(P):
    out = _node("""globalThis.f=(x,d)=>String(Math.round(x));globalThis.fp=x=>String(x);
const bx={innerHTML:'',querySelectorAll(){return [];}};globalThis.$=s=>s==='#pkbx'?bx:null;
pkBxDraw();const a=bx.innerHTML;PKBS.all=true;pkBxDraw();console.log(JSON.stringify({a,b:bx.innerHTML}));""", {"tw": {"bx": PP.boom_box(P)}})
    num = lambda h: re.findall(r'<span class="pkno( b)?">(\d+)</span><a data-c="(\w+)"', h)     # noqa: E731
    grp = lambda h: re.findall(r"<tr class=pkgh><td colspan=5>([^<]+)<span>([^<]+)</span>", h)  # noqa: E731
    return out, num, grp


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_boom_queue_from_cash_in_browser():
    """從現金開始（試算 4 檔、8 格）：8 格＝4 檔會買＋4 格空；排隊依上名單週數分段、前面寫排第幾；全部都買就沒有虛線、沒有「看後面」。"""
    out, num, grp = _queue(_P8())
    a = out["a"]
    assert a.count('class="pkslot b"') == 4 and a.count('class="pkslot e"') == 4 and "pkslot h" not in a
    assert "從現金開始</b>：11/2（一）開盤會買 4 檔，每檔約 1/8 的錢。" in a and "為什麼是這幾檔</b>：照規則排隊" in a
    assert num(a) == [(" b", "1", "6870"), (" b", "2", "5351"), (" b", "3", "3008"), (" b", "4", "3605")]
    assert grp(a) == [("新上名單", "2 檔"), ("上名單第 3 週", "2 檔")]
    assert "pkcut" not in a and "data-pkqm" not in a and out["b"] == a
    for w in BOOK + ("位置",):
        assert w not in a, w


@pytest.mark.skipif(shutil.which("node") is None, reason="沒有 node")
def test_boom_queue_cut_line_held_and_slots_in_browser():
    """拿著 6 檔、1 檔這次賣：空 3 格買排隊前 3 檔；虛線在第 3 檔後面；拿著、還在名單上的放最上面、不占號碼；
    收起時列到虛線下 3 檔；強度比買進的還高、排在後面的寫出來；8 格＝拿著 5＋買 3。"""
    out, num, grp = _queue(_P8h())
    a, b = out["a"], out["b"]
    assert num(a) == [(" b", "1", "6870"), (" b", "2", "5351"), (" b", "3", "3008"), ("", "4", "3605"), ("", "5", "2317"), ("", "6", "1101")]
    assert [n for _, n, _ in num(b)] == [str(i) for i in range(1, 9)] and [c for _, _, c in num(b)][6:] == ["2603", "2002"]
    assert a.index('data-c="3008"') < a.index("class=pkcut") < a.index('data-c="3605"')
    assert "空的 3 格買滿：以下照試算這次不買。</b>等拿著的股票抱滿 60 個交易日賣掉、空出格子，下一份名單重新排。" in a
    assert "比較久的有 3 檔，所以排在後面：鴻海（強度 99、第 5 週）、台泥（強度 97、第 9 週）、宏致（強度 95、第 3 週）。" in a
    assert grp(a) == [("拿著，還在這週名單上", "2 檔・不用再買"), ("新上名單", "2 檔"), ("上名單第 3 週", "2 檔"),
                      ("上名單第 5 週", "1 檔"), ("上名單第 9 週", "2 檔")]
    assert grp(b)[-1] == ("上名單第 12 週", "1 檔")
    held = a[a.index("拿著，還在這週名單上"):a.index("<tr class=pkgh><td colspan=5>新上名單")]
    assert "11/2 開盤賣" in held and "pkst h" in held and "pkno" not in held           # 台積電這次賣、聯發科拿著
    assert 'data-pkqm=1>看後面 2 檔</button>' in a and 'data-pkqm=0>收起</button>' in b
    assert a.count('class="pkslot h"') == 5 and a.count('class="pkslot b"') == 3 and "pkslot e" not in a
    assert re.findall(r'class="pkslot h"><b><a data-c="(\w+)"', a) == ["9002", "9001", "9004", "2454", "9003"]   # 先到期的在前面
    assert '乙</a></b><span>11/10 賣</span>' in a and '騰雲</a></b><span>11/2 會買</span>' in a              # 手機一格約 70px：字要短
    assert "拿著 5 檔</b>・11/2（一）開盤賣 台積電（抱滿 60 個交易日）・<b>空 3 格</b>：11/2（一）開盤會買 3 檔。" in a
    assert "下一次有空格：11/10（二）開盤賣 乙（抱滿 60 個交易日）。" in a
    for w in BOOK + ("位置",):
        assert w not in b, w


# ── 台美同一個骨架（2026-11-11，docs/lab_stock_page_plan.md 第 4.1 節）：成績單、同期大盤、同一個模板的策略卡、美股這週要做的事 ──

def _B():
    """大盤（測試用）：10/1 起每個平日一個值，前 10 天 100、之後每天少 1。"""
    from datetime import date, timedelta
    q, d, v = {}, date(2026, 8, 3), 100.0
    while d <= date(2026, 11, 10):
        if d.weekday() < 5:
            q[d.isoformat()] = v
            if d >= date(2026, 10, 15):
                v -= 1.0
        d += timedelta(days=1)
    return PP.Bench(q)


def test_bench_same_period_and_curve_from_first_buy():
    B = _B()
    assert B.ret("2026-08-17", "2026-10-14") == 0.0                                    # 買進前一個交易日收盤 → 最新收盤
    assert round(B.ret("2026-10-16", "2026-10-20"), 4) == round(97 / 100 - 1, 4)       # 10/15 收盤 100 → 10/20 收盤 97
    assert round(B.cc("2026-10-15", "2026-10-20"), 4) == round(97 / 100 - 1, 4) and B.cc("2026-10-20", "2026-10-20") is None
    assert B.ret(None, "2026-10-20") is None and PP.Bench({}).ret("2026-10-16", "2026-10-20") is None
    # 那本帳前三天還沒買（淨值不動）：從最後一個不動的日子起算，那幾天大盤跌的不算
    L = PP.curve_stat(["a", "b", "c", "d", "e"], [100, 100, 100, 110, 99], [100, 95, 90, 99, 81])
    assert L["a"] == "c" and L["d"] == "e" and round(L["s"], 4) == -0.01 and round(L["b"], 4) == -0.1 and round(L["mdd"], 4) == 0.1
    assert PP.curve_stat(["a", "b"], [100, 100], [1, 2]) is None and PP.curve_stat(["a"], [1], [1]) is None


def test_score_row_average_benchmark_gap_and_tags():
    held = [{"r": -0.20, "bm": -0.05}, {"r": -0.10, "bm": -0.05}, {"r": None, "bm": None}]          # 第三檔剛買、還沒有漲跌
    sc = PP.score_of(held)
    assert sc["n"] == 3 and sc["new"] == 1 and round(sc["avg"], 4) == -0.15 and round(sc["bm"], 4) == -0.05 and round(sc["diff"], 2) == -10.0
    assert "落後大盤" in PP.score_tags(sc) and "領先大盤" in PP.score_tags(dict(sc, diff=PP.LAG_PT))
    assert PP.score_tags(dict(sc, diff=-PP.LAG_PT + 0.1)) == "" and "空手" in PP.score_tags(PP.score_of([]))
    assert "暫停中" in PP.score_tags(dict(sc, halt=True)) and "比過去最差還差" in PP.score_tags(dict(sc, worse=True))
    assert PP.score_of([{"r": -0.1, "bm": None}])["diff"] is None                                   # 少一檔沒有大盤就不比
    b = {"unit": "次", "exp": {"n": 8, "lo": -3.6}}
    assert PP.past_cmp_adv(b, held) == ("這一次平均 −15.0%；過去最差一次 −3.6%（8 次）", True)
    assert PP.past_cmp_adv(dict(b, unit="檔", exp={"n": 33, "lo": -22.8}), held) == ("這次最差一檔 −20.0%；過去最差一檔 −22.8%（33 檔）", False)
    assert PP.past_cmp_curve({"mdd": 0.167}, 0.424, 2019) == ("這次最深跌 16.7%；過去最深跌 42%（2019 年起）", False)
    assert PP.past_cmp_curve({"mdd": 0.5}, 0.424, None)[1] is True and PP.past_cmp_curve(None, 0.4, 2019) == ("", False)


def test_tw_scoreboard_rows_follow_the_cards(monkeypatch):
    """成績單每條主要策略一列，數字和策略卡上的同一批；空手的寫下一次什麼時候。"""
    monkeypatch.setattr(PP, "bench", lambda mk: _B())
    P = dict(_P(), curve={"d": ["2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27", "2026-10-28"],
                         "nav": [100, 100, 104, 96, 98], "tr": [100, 99, 98, 97, 96]})
    V = PP.tw_view({"adv": _A(), "n8": P}, {"R": {}}, today="2026-10-28")
    t = V["score"]
    assert 'id="pk-tw-score"' in t and t.count('class="l pkscn"') == 3
    for k in ("boom", "s3", "v3l"):
        assert f'data-to="pk-{k}"' in t
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)[1:]
    boom, s3, v3 = [re.sub(r"\s+", "", _text(r)) for r in rows]
    assert "1檔" in boom and "+10.0%" in boom and "10/23起−2.0%（大盤−3.0%）" in boom              # 10/22 還沒買，從 10/23 收盤算
    assert "這次最深跌7.7%" in boom or not PP.w10()                                               # 104 → 96
    assert "空手" in s3 and "—" in s3
    assert "+5.3%" in v3 or "+5.4%" in v3                                                          # 聯電 +5.35%
    assert "8/17起" not in v3 and "10/15起−4.1%（大盤−9.0%）" in v3                                                  # 回測買的：開始照做以來另外算（上線以來）
    card = V["cards"][V["cards"].index('id="pk-v3l"'):]
    assert '<span class="pkst">拿著 1 檔</span>' in card and "平均 +5." in card and "同期大盤" in card
    assert '<span class="pkst w">空手</span>' in V["cards"][V["cards"].index('id="pk-s3"'):V["cards"].index('id="pk-v3l"')]
    for w in BANNED + PLAIN_BAD:
        assert w not in _text(t), w


def _G():
    """美股強勢品質股（cfgpage.us_state 的格式）：1 檔回測買的、1 檔要賣、1 檔剛買、1 檔待買進、1 檔剛賣掉。"""
    return {"on": True, "d": "2026-11-10", "nf": "2026-11-13", "sw": 1.0, "c0": 0.0, "idle": 0.0, "free": 0, "uc": {"ANF", "QLYS"},
            "nms": {}, "W": {},
            "n": {"d": "2026-11-06", "list": [], "hold": [{"c": "ANF", "epx": 154.5, "px": 149.5, "r": -0.03},
                                                          {"c": "QLYS", "epx": 224.1, "px": 190.4, "r": -0.15},
                                                          {"c": "PAYC", "epx": 274.6, "px": 237.3, "r": -0.136}]},
            "rows": [{"c": "ANF", "ent": "2026-10-19", "r": -0.003, "pct": 0.042, "sell": None, "trig": None, "rk": 4, "rs": 97.0,
                      "bt": True, "rl": -0.012, "w": 0.144},
                     {"c": "QLYS", "ent": "2026-11-02", "r": -0.219, "pct": -0.082, "sell": "2026-11-11", "trig": "2026-11-10", "rk": 18,
                      "rs": 93.0, "bt": False, "rl": None, "w": 0.031},
                     {"c": "SEZL", "ent": "2026-11-09", "r": None, "pct": None, "sell": None, "trig": None, "new": True, "rk": 1, "rs": 98.0,
                      "w": 0.12}],
            "todo": [{"c": "SN", "d": "2026-11-16", "rk": 2, "rs": 98.0, "w": 0.125}],
            "gone": [{"c": "PAYC", "on": "2026-11-10", "trig": "2026-11-09"}]}


def test_us_rows_same_columns_as_tw():
    held, todo, gone = PP.us_rows(_G(), _B())
    anf, qlys, sezl = held
    assert anf["epx"] == 154.5 and round(anf["px"], 2) == round(154.5 * 0.997, 2) and anf["bt"] and anf["rl"] == -0.012
    assert round(anf["bm"], 4) == round(82 / 99 - 1, 4)                                # 10/16 收盤 99 → 11/10 收盤 82
    assert "收盤跌破 50 日線才賣（現在比 50 日線高 4.2%）" == anf["sell"] and "11/11（三）開盤賣（11/10 收盤跌破 50 日線）" == qlys["sell"]
    assert sezl["new"] and sezl["r"] is None and sezl["bm"] is None
    assert "這週名單第 4 名、強度 97" in anf["why"] and anf["w"] == "占這條策略的錢 14%"
    assert todo == [{"c": "SN", "n": todo[0]["n"], "att": todo[0]["att"], "when": "11/16（一）開盤買", "note": "約 12%", "why": "這週名單第 2 名"}]
    assert gone[0]["c"] == "PAYC" and gone[0]["r"] == -0.136 and gone[0]["rd"] == "2026-11-06"
    g = PP.gone_line(gone)
    assert "最近賣掉的" in g and "11/10（二）開盤賣（11/9 收盤跌破 50 日線；11/6 收盤時 −13.6%）" in g
    t = PP.hold_table(held)
    assert t.count("<tr") == 4 and 'href="#us=ANF" data-us="ANF"' in t and "上線以來 −1.2%" in t and "買進價等這週六的紀錄" in t
    tw = PP.hold_table(PP.adv_rows(_A(), "v3l", _B(), "2026-10-28")[0])
    head = lambda x: re.findall(r"<th(?: [^>]*)?>(.*?)</th>", x)                             # noqa: E731
    assert head(t) == head(tw) == ["股票", "買進", "現價", "漲跌", "同期大盤", "什麼時候賣"]   # 台美同樣的欄


def test_cards_share_one_template_across_markets(monkeypatch):
    """新飆股、財報驚喜、美股強勢品質股三張卡：同一組段落、同一個順序（標題 → 現在拿著 → 接下來 → 規則收起）。"""
    monkeypatch.setattr(PP, "bench", lambda mk: _B())
    V = PP.tw_view({"adv": _A(), "n8": _P()}, {"R": {}}, today="2026-10-28")
    G = _G()
    evs = [{"d": "2026-11-11", "at": "開盤", "k": "qm", "act": "賣出", "items": [{"c": "QLYS", "n": "Qualys"}], "note": "收盤跌破 50 日線"},
           {"d": "2026-11-13", "at": "收盤", "k": "qm", "act": "名單", "items": [], "note": "這一週的名單", "proj": True},
           {"d": "2026-11-16", "at": "開盤", "k": "qm", "act": "買進", "items": [{"c": "SN", "n": "SharkNinja"}], "note": ""},
           {"d": "2026-11-12", "at": "", "k": "ern", "act": "財報", "items": [{"c": "ANF", "n": "Abercrombie & Fitch"}], "note": "財報公布日"}]
    held, todo, gone = PP.us_rows(G, _B())
    us = PP.us_card(G, evs, {}, held, todo, gone, PP.score_of(held))
    c = V["cards"]
    boom, v3 = c[c.index('id="pk-boom"'):c.index('id="pk-s3"')], c[c.index('id="pk-v3l"'):]
    marks = ('class="pkh"', 'class="pkst"', "現在拿著", 'class="sxt pkht"', 'class="pktodo"', "接下來", 'class="cfdet pkdet pkrule"', "<dt>選什麼",
             "<dt>什麼時候", "<dt>怎麼分錢", "<dt>過去照做", "<dt>風險")
    for name, card in (("boom", boom), ("v3l", v3), ("qm", us)):
        order = [card.index(m) for m in marks]
        assert order == sorted(order), name
    assert "待買進 1 檔" in us and 'class="sxt pkht pktd"' in us and us.index("接下來") < us.index("待買進 1 檔") < us.index("pkrule")
    assert "賣 1 檔</b>：<a " in us and "出新名單</b>：這一週的名單" in us and "財報公布日" not in us     # 財報日只在行事曆與這週要做的事
    assert "最近賣掉的" in us and us.index("pkht") < us.index("最近賣掉的") < us.index("pktodo")
    for w in BANNED + PLAIN_BAD:
        assert w not in _text(us), w
    # 美股「這週要做的事」：和台股同一張表（哪一天｜策略｜做什麼｜條件｜什麼時候賣），股票開美股個股卡，持股公布財報另外一行
    W = PP.week_rows(evs, "2026-11-10", ["qm"], mk="spx")
    assert (W["a"], W["b"]) == ("2026-11-11", "2026-11-17") and [(r["d"], r["act"]) for r in W["rows"]] == [("2026-11-11", "賣出"), ("2026-11-16", "買進")]
    assert W["rows"][1]["cond"] == PP.META["qm"]["cond"] and W["rows"][1]["exit"] == PP.META["qm"]["exit"] and W["rows"][0]["cond"] == ""
    assert W["fix"] == [["qm", [["2026-11-13", "收盤"]]]] and W["ern"] == [["2026-11-12", [["ANF", "Abercrombie & Fitch"]]]]
    t = PP.week_box(W, {"qm": 1}, None, mk="us", att=lambda x: PP.CFP._ua(x, G))
    tw = V["todo"]
    head = lambda x: re.findall(r"<th(?: [^>]*)?>(.*?)</th>", x)                             # noqa: E731
    assert 'id="pk-us-todo"' in t and head(t) == head(tw) and 'data-us="QLYS"' in t and 'data-to="pk-qm"' in t
    assert "持股公布財報" in t and "會出新名單的日子" in t and "美國當地日期" in t and "pkeq" not in t
    for w in BANNED + PLAIN_BAD + BOOK:
        assert w not in _text(t), w


def test_slots_show_change_since_buy_in_browser():
    """8 格：拿著的那幾格多一行買進後的漲跌（docs/lab_stock_page_plan.md 第 4.1 節）。"""
    if not shutil.which("node"):
        pytest.skip("沒有 node")
    P = dict(_P8(), hold=[{"c": "9001", "n": "甲", "sell": False, "out": "2026-11-10", "r": 0.0449},
                          {"c": "9002", "n": "乙", "sell": False, "out": "2026-11-12", "r": -0.174}])
    X = PP.boom_box(P)
    assert X["hr"] == {"9001": 0.0449, "9002": -0.174} and X["hold"][0] == ["9001", "甲", "2026-11-10", False]
    out = _node("globalThis.pctT=(x,d)=>(x>=0?'+':'−')+Math.abs(x).toFixed(d)+'%';console.log(JSON.stringify({a:pkSlots(pkBx())}));",
                {"tw": {"bx": X}})
    assert '<span>11/10 賣</span><span class="pkslr up">+4.5%</span>' in out["a"] and '<span class="pkslr dn">−17.4%</span>' in out["a"]

