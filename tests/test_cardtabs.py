"""個股卡台美同一組頁籤、同一個順序（docs/lab_stock_page_plan.md 第 4.1 節、B 段，2026-11-11）：
台股個股卡（page.renderStock）、公司卡（copage.renderCo）、美股個股卡（uscardpage.ucRender）；
美股補「重點」（uscardpage.sum_html）、台股新飆股補「買進時／現在」（sxlive.hold_cmp → pickpage.boom_pos 的 m → page.whySec）。"""
import re

from arm.lab import copage, page, pickpage as PP, superx as SX, sxlive as SL, uscardpage as UCP

SHARED = ["策略", "重點", "走勢", "為什麼選它", "成長", "獲利", "估值", "同產業", "籌碼", "分析師", "公司"]


def test_tw_and_us_cards_share_tab_names_and_order():
    tw = page._JS[page._JS.index("const secs=[...(PKU[c]?[['c-st','策略']]:[])"):]
    tw = tw[:tw.index("];") + 2]
    tw_labels = re.findall(r"'([^'\[\],]+)'\]", tw)
    tw_labels = ["為什麼選它" if x in ("為什麼選它", "飆股檢查") else x for x in tw_labels]
    us = UCP.JS[UCP.JS.index("const secs=[['uc-st','策略']"):]
    us = us[:us.index("];") + 2]
    us_labels = re.findall(r"'([^'\[\],]+)'\]", us)
    assert us_labels == SHARED
    assert [x for x in tw_labels if x in SHARED] == SHARED                 # 同樣的名字、同樣的順序
    assert [x for x in tw_labels if x not in SHARED] == ["ETF 持有", "訊號"]     # 台股才有的放在籌碼後面
    assert tw_labels.index("ETF 持有") == tw_labels.index("籌碼") + 1
    for old in ("'法人預估']", "'產業']", "['co-sum','公司分析']", "'飆股檢查'],['uc-gr'"):
        assert old not in tw + us + copage.JS[copage.JS.index("function coNav"):copage.JS.index("function coParts")], old


def test_section_titles_match_across_markets():
    js = copage.JS
    assert "<h3>分析師<span class=sub>" in js and "<h3>同產業<span class=sub>" in js and "<h3>獲利<span class=sub>" in js
    assert "<h3>法人預估" not in js and "<h3>產業比較" not in js and "<h3>獲利能力" not in js
    assert "h4 class=sh>飆股體質檢查" in UCP.JS and "<h3>飆股體質檢查<span class=sub>" in page._JS and "h4 class=sh>飆股體質檢查" in page._JS
    assert "function ucTa(S)" in UCP.JS and "id=uc-ta" in UCP.JS                # 美股技術面和台股一樣在走勢後面
    i = UCP.JS.index("function ucRender(")
    body = UCP.JS[i:UCP.JS.index("\nfunction ", i + 1)]
    order = [body.index(x) for x in ("id=uc-st", "id=uc-sum", "id=uc-px", "id=uc-ta", "id=uc-why", "id=uc-sx", "id=uc-gr", "id=uc-an", "id=uc-co")]
    assert order == sorted(order)
    i = page._JS.index("function renderStock(")
    body = page._JS[i:page._JS.index("\nfunction ", i + 1)]
    assert "h+=hTa+whySec(c,X)+coMid(X)+hChip+hHold+hSig+(X.fc||'')+(X.sum||'');" in body   # 走勢 → 技術面 → 為什麼選它 → … → 分析師 → 公司


def test_from_company_search_only_jumps_to_a_named_section():
    js = copage.JS
    i = js.index("function coAfterStock(")
    f = js[i:js.index("\n/*", i)]
    assert "if(!COSEC){COJ=null;return;}" in f and "'co-sum'" not in f       # 公司那段搬到最下面：沒指定段落就停在最上面


def test_condition_head_and_cells():
    assert SX.cond_head(("rs", ">=", 90)) == ("強度", "要 90 以上")
    assert SX.cond_head(("lu20", ">=", 1)) == ("近 20 日漲停次數", "要至少 1 次")
    assert SX.cond_head(("liq", ">=", 6.5e8)) == ("20 日均成交值", "要 6.5 億以上")
    assert SX.cond_head(("rnha", "=", True)) == ("月營收創歷史新高", "要符合")
    assert SX.cond_cell(("rs", ">=", 90), 93.0) == ("93", True) and SX.cond_cell(("rs", ">=", 90), 85) == ("85", False)
    assert SX.cond_cell(("lu20", ">=", 1), 0) == ("0 次", False) and SX.cond_cell(("liq", ">=", 6.5e8), 1.139e10) == ("113.9 億", True)
    assert SX.cond_cell(("c33", "=", True), False) == ("否", False) and SX.cond_cell(("rnha", "=", True), None) == ("—", None)
    assert SX.cond_cell(("rs", ">=", 90), None) == ("—", None) and SX.cond_cell(("rs", ">=", 90), True) == ("—", None)
    assert SX.cond_value_text(("rs", ">=", 90), 96) == "強度 96（要 90 以上）"     # 原本的寫法不變


class _P:
    cal = ["2026-10-30", "2026-11-02", "2026-11-10"]


def test_hold_cmp_buy_week_versus_now(monkeypatch):
    rules = {2026: [[("rs", ">=", 95)], [("lu20", ">=", 1), ("liq", ">=", 6.5e8), ("rnha", "=", True)]]}
    W = {"2026-10-30": {"why": {"R60": {"1815": {"k": [1], "v": {"lu20": 3, "liq": 1.318e10, "rnha": True}}}}}}
    monkeypatch.setattr(SL, "feats_at", lambda ctx, j: {"1815": {"lu20": 0, "liq": 1.607e10, "rnha": None}})
    hold = [{"c": "1815", "sig": "2026-10-30"}, {"c": "9999", "sig": "2026-10-30"}]
    SL.hold_cmp(hold, W, rules, {"P": _P}, 2)
    assert hold[0]["cmp"] == {"d": "2026-10-30", "now": "2026-11-10",
                              "rows": [["近 20 日漲停次數", "要至少 1 次", "3 次", True, "0 次", False],
                                       ["20 日均成交值", "要 6.5 億以上", "131.8 億", True, "160.7 億", True],
                                       ["月營收創歷史新高", "要符合", "是", True, "—", None]]}
    assert "cmp" not in hold[1]                                              # 那週沒有記符合哪一條＝不畫表
    P = {"d": "2026-11-10", "next": "2026-11-11", "hold_n": 60,
         "hold": [dict(hold[0], n="富喬", ent="2026-11-02", epx=122.5, px=128.0, out="2027-01-28", why=["符合：…"])]}
    pos = PP.boom_pos(P)
    assert pos["1815"][0]["m"] == hold[0]["cmp"] and pos["1815"][0]["h"] == 1


def test_why_section_moves_reasons_out_of_strategy_section():
    js = page._JS
    i = js.index("function stCardSec(")
    st = js[i:js.index("\n/*", i)]
    assert "為什麼：" not in st                                               # 理由搬到「為什麼選它」（和美股一樣）
    i = js.index("function whySec(")
    w = js[i:js.index("\n/*", i)]
    assert "id=c-why><h3>為什麼選它</h3>" in w and "cmpTbl(q.m)" in w and "h4 class=sh>飆股體質檢查" in w
    i = js.index("function cmpTbl(")
    t = js[i:js.index("\nfunction ", i + 1)]
    assert "class=ucfv" in t and "買進時" in t and "現在" in t and "照樣拿著" in t   # 和美股「為什麼選它」同一張表（ucfv）


def _us(**kw):
    x = {"pd": "2026-11-10", "px": 154.0, "ch": 0.78, "c": [100.0] * 30 + [146.0] + [150.0] * 20 + [154.0],
         "m": [147.78] * 52, "hi": ["2026-11-05", 172.0],
         "fin": {"g": [["2026-08-01", "2026-09-04", 12.7, 0.048, 0.6, 0.2, 0.1, 2.3, 0.4, 0.405]],
                 "v": {"pe": 13.2, "peh": {"pct": 55, "p50": 11.9}, "cap": 65.0, "ttm": 11.6}},
         "an": {"n": 11, "rc": [3, 6, 6, 0, 0], "ed": ["2026-11-24"], "ede": False, "tp": [165.8, 140.0, 190.0, 11]}}
    x.update(kw)
    return x


def test_us_key_points_sentences_and_numbers():
    t = re.sub(r"<[^>]+>", "", UCP.sum_html(_us()))
    assert t.startswith("重點11/10 收盤 154.00，比 50 日線高 4.2%，離 52 週高點 −10.5%（11/5 創高）；近 1 個月 +5.5%。")
    assert "最近一季（8/1 季底、9/4 公布）營收 12.7 億美元、年增 +4.8%；營益率 20.0%；近四季 ROE 40.5%。" in t
    assert "本益比 13.2 倍，近 5 年有 55% 的時候比現在低（中間值 11.9 倍）；市值 65 億美元。" in t
    assert "下次財報 11/24；分析師評等：看好 9、中立 6、看淡 0。" in t
    assert t.count("<div") == 0 and UCP.sum_html(_us()).count('class="kp"') == 6
    assert "目標價" not in t and "165.8" not in t                             # 分析師的價位只在「分析師」那一段
    t2 = re.sub(r"<[^>]+>", "", UCP.sum_html(_us(an={"ed": ["2026-11-04"], "rc": [0, 0, 0, 0, 0]})))
    assert "下次財報" not in t2 and "分析師評等" not in t2                     # 已經過了的財報日、沒有評等都不寫
    t3 = re.sub(r"<[^>]+>", "", UCP.sum_html(_us(an={"ed": ["2026-11-20", "2026-11-25"], "ede": True})))
    assert "下次財報 11/20～11/25（Yahoo 估的日期）" in t3
    t4 = re.sub(r"<[^>]+>", "", UCP.sum_html(_us(fin={"v": {"ttm": -1.2}}, hi=[None, None], c=[], m=[])))
    assert "近四季賺的錢是負的，本益比不能比" in t4 and "比 50 日線" in t4    # 缺的寫「—」、不壞
    for w in ("門檻", "判定", "研究", "樣本", "VER", "→"):
        assert w not in t + t2 + t3 + t4, w
