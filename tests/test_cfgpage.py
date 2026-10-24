"""配置頁（arm/lab/cfgpage.py；docs/lab_ia_v5_plan.md 第 18 節）：台股、美股各一張「時程與水位」卡（四格 → 水位長條 → 警訊
→ 規則 → 成績 → 細節 → 下一個交易日 → 時間軸）、持股細節表（比重合計 100%）、策略一行；策略頁一張表；
x9.html 的分頁、兩次建頁（finish）、用字。"""
import re

import pytest

from arm.lab import board as BD
from arm.lab import cfgpage as CF
from arm.lab import core as CO
from arm.lab import corepage as CPG
from arm.lab import corespec as S
from arm.lab import page
from arm.lab import sigpage as SG
from test_corepage import BANNED, JARGON, NOT_PLAIN, STK, _now, _text, _us


@pytest.fixture(scope="module")
def R():
    R = CO.load()
    assert R is not None, "研究檔 data/lab/core_research.json 要先跑 scripts/run_core.py"
    return R


@pytest.fixture(scope="module")
def QMX():
    from arm.lab import ussxqm as QM
    R = QM.load()
    assert R is not None, "研究檔 data/lab/ussx_qm.json 要先跑 scripts/run_ussx.py --qm"
    return {"R": R, "L": QM.load_live(), "W": None}


def _data():
    cal = [dict(e) for e in STK["ev"]]
    book = [{"k": s["k"], "name": s["name"], "tier": "good", "how": "規則一句", "unit": "次",
             "exp": {"n": 30, "avg": 2.5, "win": 61, "mk": 0.8, "lo": -12.0}, "all": {}} for s in STK["st"]]
    return {"adv": {"last": "2026-10-22", "cal": cal, "book": book,
                    "opp": {"cards": [{"k": "v3l", "name": "財報驚喜（大型股）", "hold": "60 個交易日",
                                       "held": [], "buy": [], "next": None, "adj": []}]}},
            "mac": {"mks": ["tw", "spx"], "m": {"tw": {"cal": [], "cards": [], "book": []}, "spx": {"cal": [], "cards": [], "book": []}}}}


def _bundle(R, qm=None, tw=None, spx=None):
    return {"R": R, "now": {"tw": tw if tw is not None else _now(), "spx": spx if spx is not None else _us()},
            "stk": STK, "fw": {}, "qm": qm}


def _ws(h: str) -> list[float]:
    return [float(x) for x in re.findall(r'<td class="w">(?:約 )?([0-9.]+)%</td>', h)]


def test_tw_card_blocks_in_order_and_tiles(R):
    X = CF.tw_parts(_data(), _bundle(R))
    c = X["card"]
    order = [c.index(x) for x in ('class="cftiles"', 'class="cfstack"', 'class="cfwarn"', 'class="cfrule"', 'class="cfperf"',
                                  'class="cfdet"', 'class="cfnext"', 'id="cftl-tw"')]
    assert order == sorted(order)                                                 # 上半＝現在的狀態，下半＝接下來要做的事
    t = _text(c)
    for w in ("待買進", "持有中", "股票水位", "警訊", "時程與水位"):
        assert w in t, w
    assert "63%" in t and "現金 37%" in t and "1／3" in t                          # 一個警訊、不用換現金；股票＝長抱＋機動裡有股票的（空位放現金）
    assert "11/9（一） 開盤・新飆股" in t                                          # 待買進：新飆股下一個交易日開盤要買的比財報驚喜的名單早
    sc = R["mk"]["tw"]["sc"]
    s = sc.get("plan") or sc.get("rule")
    assert "100 萬變" in t and CPG._wan(s["plan"]["m"]) in t and f'0050 抱著 {CPG._wan(s["hold"]["m"])}' in t
    assert "長抱 20%" in t and "0050" in t and "機動 80%：新飆股 40%" in t
    assert {k: X["tl"][k] for k in ("use", "obs", "mm")} == {"use": ["v3l", "s3", "s5"], "obs": [], "mm": "tw"}
    assert X["tl"]["boom"]["k"] == "boom" and X["nx"] and X["d"] == "2026-10-22"


def test_tw_hold_table_adds_to_100(R):
    h = CF.tw_parts(_data(), _bundle(R))["hold"]
    w = _ws(h)
    assert w and abs(sum(w) - 100) < 0.6, w                                       # 比重＝占全部資金、合計 100%
    t = _text(h)
    assert "台積電" in t and "8/17 買" in t and "11/12 收盤賣" in t                 # 每一檔：哪天買、到哪天賣
    assert "8/17 買・+3.1%" in t                                                   # 買進後漲跌（advice 的 now_r 是百分比）
    assert t.count("這一期沒有部位") == 2                                           # 沒部位的那一份放現金（VER 4；VER 1～3 放 0050）
    assert "機動 80%：新飆股 40%（每檔約 5%）＋個股策略 40%（3 條各 13.3%），沒有部位的那一份放現金" in t
    assert '奇鋐 <span class="cd">3017</span>' in h and "11/2 買・+10.0%・2/3 開盤賣（2/2 收盤滿 60 個交易日）" in t   # 新飆股每一檔
    assert '金像電 <span class="cd">2368</span>' in h and "11/9 開盤買（11/6 的名單）" in t and "台燿" not in t   # 現金不夠的那一檔不列
    assert "0050／006208" in t and "長抱 20%" in t


def test_tw_due_cash_and_buy_back(R):
    X = CF.tw_parts(_data(), _bundle(R, tw=_now(n_lit_extra=True, held=True)))   # 兩個警訊、還拿著 → 下一個交易日收盤換現金
    t = _text(X["card"])
    assert "收盤：把機動 80% 賣掉換成現金" in t and "機動 80% 換成現金" in t and "2／3" in t
    assert "機動 80% 放現金" in t and "20%" in t and "現金 80%（機動 80% 放現金中）" in t   # 水位長條整段標現金；股票只剩長抱
    X = CF.tw_parts(_data(), _bundle(R, tw=_now(held=False)))                    # 警訊解除、機動在現金 → 買回
    assert "把機動 80% 買回來" in _text(X["card"])


def test_us_card_uses_qm_and_qqq_line(R, QMX):
    X = CF.us_parts(_data(), _bundle(R, qm=QMX))
    c, h = X["card"], X["hold"]
    t = _text(c + h)
    assert 'class="cfsc"' not in c and "長抱" not in _text(h) and S.core_of("spx") == 0   # VER 4：美股不留長抱（長條沒有長抱段、持股沒有長抱列）
    if not CPG.qm_on("spx", QMX):
        assert "SPY／VOO" in t and "全部持股：S&amp;P 500" in t and "全部持股放 S&amp;P 500" in t
    if CPG.qm_on("spx", QMX):
        n = CPG._qm_now(QMX)
        for x in n.get("hold") or []:
            assert f'<span class="cd">{x["c"]}</span>' in h or f'<td>{x["c"]}</td>' in h, x["c"]
        assert X["tl"]["qm"] and X["tl"]["qm"]["k"] == "qm"
        w = _ws(h.split('class="cfh3"')[0])                                    # 名單前幾名那張表沒有比重
        assert abs(sum(w) - 100) < 1.0, w
    if CPG.qm_on("ndx", QMX):
        assert "警訊改看那斯達克 100：同一套規則 100 萬變" in t and "配置照 S&amp;P 500" in c   # 長抱 0%：差別只在看哪個指數的警訊


def test_us_rows_show_company_name_and_business(R, QMX, monkeypatch):
    """2026-10-24 使用者：「美股那些公司誰知道你是什麼公司…台股不都有列嗎？比照著做」——美股每一列＝公司名＋代號、下一行本業；
    名單前幾名（手上沒有的）一張表；名稱也進「接下來要做的事」與時間軸。"""
    from arm import fund_intro as FI
    monkeypatch.setattr(CPG, "_US_INTRO", {"INSW": "美國 International Seaways，油輪航運公司；船隊…",
                                           "VLO": "美國瓦萊羅能源（Valero Energy），大型煉油商；…"})
    qm = {"R": QMX["R"], "W": None, "L": {"names": {"CDNA": "CareDx, Inc."}, "now": {
        "d": "2026-10-22", "wk": "2026-10-22", "wk_done": False, "next": "2026-10-23", "idle": 0.25, "n_list": 58,
        "hold": [{"c": "INSW", "ent": "2026-07-20", "epx": 88.0, "px": 108.4, "ma": 105.0, "r": 0.29, "w": 0.4, "sell": False},
                 {"c": "VLO", "ent": "2026-08-31", "epx": 360.0, "px": 426.0, "ma": 391.0, "r": 0.18, "w": 0.35, "sell": False}],
        "buy": [], "sell": [],
        "list": [{"c": c, "rs": 99.0 - i} for i, c in enumerate(["VLO", "CDNA", "PAYC", "QLYS", "HALO", "NTAP", "CON", "CAI"])]}}}
    monkeypatch.setattr(CPG, "qm_on", lambda mk, q: True)
    X = CF.us_parts(_data(), _bundle(R, qm=qm))
    h = X["hold"]
    assert "全部持股：強勢品質股最多 8 檔，空位放現金" in _text(h)                     # VER 4：空位放現金、比重＝三成本身的比重 × 100%
    assert '<td class="idx">現金</td><td class="w">25%</td>' in h and '<td class="w">40%</td>' in h
    assert abs(sum(_ws(h.split('class="cfh3"')[0])) - 100) < 0.6
    assert "75%" in _text(X["card"]) and "現金 25%" in _text(X["card"])          # 股票水位＝1 − 空位
    assert 'International Seaways <span class="cd">INSW</span><div class="cfin">油輪航運公司</div>' in h
    assert '瓦萊羅能源 <span class="cd">VLO</span><div class="cfin">大型煉油商</div>' in h
    top, cand = h.split('class="cfh3"')
    assert "有空位時依序買：名單前 5 名（手上沒有的）" in _text(cand) and "名單共 58 檔" in _text(cand)
    got = re.findall(r'<span class="cd">(\w+)</span>', cand) + re.findall(r"<td>(\w+)</td>", cand)
    assert set(got) == {"CDNA", "PAYC", "QLYS", "HALO", "NTAP"} and FI.US_QM_SHOW == 5     # VLO 手上有，不列；只列前 5
    assert 'CareDx, Inc. <span class="cd">CDNA</span>' in cand                    # 沒有中文簡介：用每週紀錄的英文名
    lane = X["tl"]["qm"]
    its = lane["held"][0]["items"]                                                # 時間軸的條上寫代號（短）、提示框寫公司名
    assert [i["n"] for i in its] == ["INSW", "VLO"] and [i["nm"] for i in its] == ["International Seaways（INSW）", "瓦萊羅能源（VLO）"]
    assert "esc(i.nm||i.n)" in CF.JS


def test_us_label_parses_intro_first_clause(monkeypatch):
    monkeypatch.setattr(CPG, "_US_INTRO", {"AMD": "美國超微（AMD），CPU、GPU 設計廠；EPYC…",
                                           "FTNT": "美國 Fortinet，網路資安業者；產品…", "XX": "美國 某公司"})
    assert CPG.us_label("AMD") == ("超微", "CPU、GPU 設計廠")
    assert CPG.us_label("FTNT") == ("Fortinet", "網路資安業者") and CPG.us_name("FTNT") == "Fortinet（FTNT）"
    assert CPG.us_label("XX") == ("某公司", "")
    assert CPG.us_label("ZZ", {"ZZ": "Zz Corp"}) == ("Zz Corp", "") and CPG.us_label("ZZ") == ("ZZ", "")
    assert CPG.us_name("ZZ") == "ZZ"


def test_tw_page_has_boom_book_section(R):
    """2026-10-24 使用者：「換成新飆股」——台股配置頁的飆股名單換成新飆股（機動的一半）那本帳：每週名單、這一週的試算、
    下一份名單；持股在持股細節。原本的到買點／快到買點名單留在研究紀錄。"""
    X = CF.tw_parts(_data(), _bundle(R))
    b = X["boom"]
    assert 'id="cf-tw-sx" data-nav="新飆股"' in b
    t = _text(b)
    assert "占全部資金 40%" in t and "每檔約占全部資金 5%" in t and "抱 60 個交易日" in t
    assert "11/6（五） 收盤的名單（3 檔）" in t
    rows = re.findall(r"<tr><td>([^<]+) <span", b)
    assert rows == ["金像電", "台燿", "奇鋐"]
    assert "11/9 開盤買" in t and "現金不夠" in t and "已經有" in t                    # 名單裡：要買的、錢不夠的、手上有的
    bm = R["mk"]["tw"]["sc"]["plan"].get("boom") or {}
    if bm.get("cagr") is not None:
        assert f'每年賺 {CPG._pc(bm["cagr"]).lstrip("+")}' in t and f'最慘時跌 {bm["mdd"] * 100:.0f}%' in t
    assert 'data-go="opp" data-at="o-sx"' in b                                    # 舊的飆股名單在研究紀錄
    js = CF.JS
    assert "(C.boom||'')" in js and "function cfSx()" not in js and "cfSx" not in js
    assert "if(T.boom)L.push(Object.assign({},T.boom,{_src:'boom',_st:'use'}));" in js and "c._src==='boom'" in js
    lane = X["tl"]["boom"]                                                        # 時間軸：持有中依買進日、明天要買、下一次看名單
    assert lane["held"][0]["ent"] == "2026-11-02" and {i["c"] for i in lane["held"][0]["items"]} == {"3017", "2383"}
    assert lane["buy"][0]["d"] == "2026-11-09" and [i["c"] for i in lane["buy"][0]["items"]] == ["2368"]
    assert lane["next"]["fix"] == "2026-11-13"
    stk = dict(STK, boom=None)                                                    # 讀不到新飆股：不出這一段、時間軸沒有那一列
    X = CF.tw_parts(_data(), dict(_bundle(R), stk=stk))
    assert X["boom"] == "" and X["tl"]["boom"] is None


def test_us_without_qm_keeps_index(R):
    X = CF.us_parts(_data(), _bundle(R, qm=None))
    t = _text(X["hold"])
    assert "全部持股：S&amp;P 500" in t and "有警訊時換成現金" in t and X["tl"]["qm"] is None
    assert abs(sum(_ws(X["hold"])) - 100) < 0.6


def test_build_shapes_and_survives_missing_pieces(R, QMX):
    out = CF.build(_data(), _bundle(R, qm=QMX))
    assert set(out) >= {"now", "use", "board", "tw", "us"} and out["use"] == ["v3l", "s3", "s5"]
    for mk in ("tw", "us"):
        assert out[mk]["card"] and out[mk]["hold"] and "看全部策略" in out[mk]["line"], mk
    assert out["board"]["n"]["use"] >= 5 and 'class="btbl"' in out["board"]["html"]
    bare = CF.build({}, None)                                                     # 研究檔、讀數都沒有：不出錯、頁面寫還沒算出來
    assert bare["use"] == [] and "tw" in bare and "us" in bare
    assert "今天的讀數還沒算出來" in (bare["tw"].get("card") or "") or bare["tw"].get("err")


def test_cfg_text_is_plain(R, QMX):
    out = CF.build(_data(), _bundle(R, qm=QMX))
    for mk in ("tw", "us"):
        t = _text(out[mk]["card"] + out[mk]["hold"])
        for w in BANNED + JARGON + NOT_PLAIN:
            assert w not in t, (mk, w)
        for w in BANNED + NOT_PLAIN:                                              # 策略一行可以寫「候選 0」
            assert w not in _text(out[mk]["line"]), (mk, w)
    tb = _text(out["board"]["html"])
    for w in BANNED + NOT_PLAIN + ("隨便挑", "★", "●", "好策略", "可參考"):
        assert w not in tb, w
    for s in BD.STATUS:
        assert BD.ST_NAMES[s] in tb, s


def test_board_html_groups_and_filters():
    B = {"rows": [{"id": "tw:plan", "name": "兩成長抱＋警訊（台股）", "mk": "台股", "mkk": "tw", "type": "配置", "st": "use", "how": "h",
                   "go": {"go": "tw"}, "perf": "年化 18.0%", "ref": "一直抱著 12.0%", "mdd": "23%", "mddr": "29%", "today": "拿 100%"}]
         + [{"id": f"tw:o{i}", "name": f"觀察 {i}", "mk": "台股", "mkk": "tw", "type": "個股", "st": "obs", "how": "h", "go": {}}
            for i in range(BD.OBS_SHOW + 2)]
         + [{"id": "us:x", "name": "淘汰的", "mk": "美股", "mkk": "us", "type": "個股", "st": "out", "why": "原因一句", "go": {}}],
         "n": {"use": 1, "obs": BD.OBS_SHOW + 2, "cand": 0, "out": 1}, "nm": {}}
    h = CF.board_html(B)
    assert f'<table class="btbl" data-n="{BD.OBS_SHOW}">' in h and 'data-bx="obs"' in h   # 觀察中先列 8 條：依篩選在瀏覽器算
    assert h.count('<tr class="br" data-st="obs" data-mk="tw">') == BD.OBS_SHOW + 2
    assert "目前沒有；第一批在每週日新找之後出現" in h                                  # 候選分組先空著
    assert '<td class="bw" colspan="4">原因一句</td>' in h                           # 淘汰一列一句原因
    assert '<a data-go="tw">兩成長抱＋警訊（台股）</a>' in h
    assert '<a data-bst="out">淘汰 1</a>' in h and '<a data-bst="use" class=on>使用中 1</a>' in h   # 淘汰預設收起


def test_page_tabs_personas_and_script_order():
    html = page.render({"etfs": {}, "asof": {}, "cfg": {"use": []}})
    assert 'id="purp"' not in html and "{{" not in html
    for t in ("tw", "us", "strat", "tool"):
        assert f'data-t="{t}" data-p="cfg"' in html, t
    for t in ("stg", "mac", "bo"):
        assert f'data-t="{t}" data-p="r" hidden' in html, t
    assert '<a class="rbk" href="x9r.html" data-p="r" hidden>‹ 研究紀錄</a>' in html
    from arm.lab import appnav, copage, macpage
    assert appnav.bar("cfg", search=copage.SEARCH_HTML) in html and CF.CSS in html
    from arm.lab import corepage
    assert corepage.CSS.split("\n", 1)[0] in html                                   # 「細節」用 corepage 的圖表與表格，樣式要一起載入
    js = html[html.index("<script>"):]
    i_mac, i_cf, i_co, i_init = js.index("const MAC=D.mac||{}"), js.index("const CFG=D.cfg||{}"), js.index(copage.JS[:200]), js.index("go(v,at);")
    assert i_mac < i_cf < i_co < i_init                                            # 配置的 JS 在初始化之前（頂層 const 已經初始化）
    J = page._JS
    assert "const VIEWS={tw:vCfgTw,us:vCfgUs,strat:vCfgSt,stk:vStk,chip:vChip,idx:vIdx,opp:vOpp,st:vSt,mac:vMac,macst:vMacSt,bo:vBo};" in J
    assert "const LAST={cfg:'tw',r:'bo',tool:'stk',mac:'mac',stg:'opp'};" in J
    assert "if(!VIEWS[v])v=/^#((s|co)=|q$)/.test(location.hash)?'stk':'tw';" in J   # 預設台股；舊的個股卡連結、查公司（#q）先到個股表
    assert "if(d.gm)S.mmk=d.gm;if(d.bmk)S.bmk=d.bmk;" in J
    for v in ("vStk", "vChip", "vIdx"):                                            # 個股（工具）三頁最上面切換
        seg = J[J.index(f"function {v}("):]
        assert "toolSeg('" in seg[:seg.index("\n}\n")], v
    assert "sec('c-sig'" not in J and "sec('c-risk'" not in J and "function sigTodaySec(" not in J   # 籌碼頁的今日訊號、風險提醒拿掉
    assert "function stCardSec(c){const P=PKU[c];" in J and "CFU.has(p.k)" in J    # 個股卡只列配置裡的策略
    assert "S.sig==='sx'?SXC.has(r.c)" in J and "<option value=sx" in J               # 個股表留一個「飆股候選」篩選


def test_cfg_js_names_prefixed():
    names = re.findall(r"^function (\w+)\(|^(?:const|let) (\w+)", CF.JS, re.M)
    flat = [a or b for a, b in names]
    assert flat and all(n.startswith(("cf", "vCfg", "toolSeg", "CF")) for n in flat), flat


def test_finish_rebuilds_with_todays_readings(tmp_path, monkeypatch, R):
    out = tmp_path / "x9.html"
    data = {"etfs": {}, "asof": {}, "adv": _data()["adv"], "mac": _data()["mac"]}
    monkeypatch.setattr(page, "_LAST", {})
    assert page.finish(out) is False                                              # build() 沒跑過：不動
    page._LAST.update(data=data, out=out, ser_v="x")
    monkeypatch.setattr(SG, "CARDS", {})
    assert page.finish() is False and not out.exists()                             # 景氣頁沒有留下讀數：不動
    monkeypatch.setattr(SG, "CARDS", {"tw": {"core": _now(n_lit_extra=True)}, "spx": {"core": _us()}})
    monkeypatch.setattr(CO, "STK", dict(STK))
    assert page.finish() is True and out.exists()
    assert data["cfg"]["now"]["tw"]["n"] == 2                                     # 用今天的讀數
    assert page.finish() is False                                                 # 內容一樣：不改寫
