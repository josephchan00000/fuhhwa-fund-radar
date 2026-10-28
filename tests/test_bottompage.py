"""景氣頁「大跌後檢查」卡（arm/lab/bottompage.py；docs/lab_crash_plan.md 第 13～16 節）：
一句話、進行中的事件、急跌之後的表現、等訊號再買（VER 3：買在相對低點的比例，和固定等 10 天比）、五個市場、每一次、主要假說、用字、class 前綴。
研究數字只讀研究檔，不在頁面重算。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from arm.lab import bottom as X
from arm.lab import bottompage as BP
from arm.lab import bottomspec as S

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatpage import BANNED  # noqa: E402


def _text(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'title="[^"]*"', "", h)))


def _R() -> dict:
    R = X.load_research()
    assert R and R["ver"] == S.VER, "研究檔要先跑：TZ=Asia/Taipei python3 scripts/run_bottom.py"
    return R


def _active(mk: str, ev: str = "E5", also: bool = True, fired: str | None = "C1") -> dict:
    sig = {k: {"st": "wait", "left": 40} for k in S.SIG_MK[mk]}
    if fired and fired in sig:
        sig[fired] = {"st": "on", "d": "2026-10-20", "after": 4}
    a = {"ev": ev, "t": "2026-10-14", "p": "2026-10-06", "ppx": 13217.8, "days": 4, "depth": -0.106 if ev == "E5" else -0.11,
         "low": "2026-10-16", "lowdd": -0.157, "nowdd": -0.12, "pos_now": 0.2, "g": {"fund": 1, "chip": 0, "bub": 1},
         "gv": {"fund": 70.4, "fund0": 59.5, "chip": 75.0, "bub": 2}, "sig": sig, "w10": {"st": "wait", "left": 6}}
    if also and ev == "E5":
        a["also"] = "E10"
    return a


def _C(mk: str = "tw", active: list | None = None) -> dict:
    R = _R()
    now = {"d": "2026-10-20", "dd60": -0.054, "active": active or [], "last": {"E5": "2026-06-10", "E10": "2026-07-17"}}
    px = "加權指數" if mk == "tw" else f' {BP.MKN[mk]} '
    return {"mk": mk, "px": px, "now": now, "R": R["markets"][mk], "all": R["markets"], "primary": R["primary"]}


def test_lead_inactive_uses_research_numbers():
    for mk in S.MARKETS:
        C = _C(mk)
        ls = BP.lead(C)
        assert len(ls) == 3
        assert ls[0].startswith("現在沒有大跌：") and f"5 日跌 {S.E5_TH[mk] * 100:g}% 以上" in ls[0]
        E = C["R"]["ev"]["E5"]
        A = E["all"]
        assert f'{E["n"]} 次 5 日急跌' in ls[1] and f'相對低點（跌幅的下三分之一）的有 {BP.pct(A["lp"]["rate"], 0)}' in ls[1]
        assert BP.spct(A["r60"]["mean"]) in ls[1] and "再跌破" not in ls[1]
        rs = E["rules"]
        w = rs["W10"]["lp"]
        assert f'固定等 10 天有 {BP.pct(w["lp_rule"], 0)}（事件隔天買 {BP.pct(w["lp_base"], 0)}）' in ls[2]
        good = [k for k in S.SIG_MK[mk] if rs[k]["v"] == "better"]
        if good:
            assert "、".join(BP.SHORT[k] for k in good) + "符合" in ls[2]
        else:
            assert "沒有一個訊號符合" in ls[2]
        trade = [k for k in S.SIG_MK[mk] if rs[k]["v"] == "trade"]
        lean = [k for k in S.SIG_MK[mk] if rs[k]["v"] not in ("better", "trade") and not rs[k]["lp"]["few"]
                and (rs[k]["lp"].get("lp_lo") or 0) > 0]
        low = [k for k in S.SIG_MK[mk] if rs[k]["lp"].get("lp_dir") == "down"]
        for k in lean:
            c = rs[k]["lp"]
            assert f'{BP.SHORT[k]}有 {BP.pct(c["lp_rule"], 0)} 買在相對低點（同一批事件固定等 10 天 {BP.pct(c["lp_base"], 0)}）' in ls[2]
        for k in low:
            c = rs[k]["lp"]
            assert f'{BP.SHORT[k]}只有 {BP.pct(c["lp_rule"], 0)} 買在相對低點（同一批事件固定等 10 天 {BP.pct(c["lp_base"], 0)}）' in ls[2]
            assert f'已經比當時的最低收盤高 {BP.pct(c["reb_rule"])}' in ls[2]
        if not (good or trade or lean or low):
            assert "其他訊號和固定等 10 天沒有明顯差別" in ls[2]
        assert "再跌破低點" not in ls[2]                                 # 第三版：看相對低點，不看再跌破低點
    us = BP.lead(_C("spx"))[0]
    assert "S&P 500 離 60 日高點" in us                           # 英文名後面要有空白


def test_lead_active_event():
    C = _C("sox", [_active("sox")])
    l0 = BP.lead(C)[0]
    assert l0.startswith("費半 2026/10/14 出現 5 日急跌（5 日跌 10.6%），同一天也從 60 日高點跌了 10% 以上")
    assert "現在比 2026/10/6 的高點低 12.0%" in l0 and "事件後第 4 個交易日" in l0
    C = _C("tw", [_active("tw", "E10", also=False)])
    assert BP._ev_main(C) == "E10"
    ls = BP.lead(C)
    assert "2026/10/14 起從 60 日高點跌 10% 以上" in ls[0] and "次從 60 日高點跌 10%" in ls[1]


def test_card_structure_and_banned_words():
    for mk in S.MARKETS:
        for act in (None, [_active(mk)]):
            C = _C(mk, act)
            h = BP.card(C)
            t = _text(h)
            assert h.count('id="bottom"') == 1 and "大跌後檢查" in t and "只描述過去，不是買賣指示" in t
            n_rules = 1 + len(S.SIG_MK[mk])
            assert h.count('<table class="xjrt">') == 2 and h.count('<table class="xjdt">') == 2   # 兩種事件各一張
            rt = h[h.index('<table class="xjrt">'):h.index("</table>", h.index('<table class="xjrt">'))]
            assert rt.count("<tr") == 1 + len(S.SIG_MK[mk])               # 表裡只有訊號；固定等 10 天是表上面那一行對照
            assert h.count('class="xjbase"') == 2 and "對照：固定等 10 天" in t
            ft = h[h.index('<table class="xjft">'):h.index("</table>", h.index('<table class="xjft">'))]
            assert ft.count("<tr") == 1 + len(S.RULES)
            dt = h[h.index('<table class="xjdt">'):h.index("</table>", h.index('<table class="xjdt">'))]
            assert dt.count("<tr") == 1 + 1 + 2 * len(S.GROUPS)
            if act:                                           # 進行中：展開這一次，研究結果不收起來
                assert "這一次：2026/10/14 5 日急跌" in t and 'class="xjmore xjres"' not in h
                st = h[h.index('<table class="xjst">'):h.index("</table>", h.index('<table class="xjst">'))]
                assert st.count("<tr") == 1 + n_rules
                assert ("已出現 2026/10/20（第 4 天）" in t) == ("C1" in S.SIG_MK[mk])
                assert "還沒（還有 6 個交易日）" in t       # 固定等 10 天
                assert "目前這一波的位置 20%（下三分之一內）" in t and "買在相對低點 隔天買" in t
                assert "隔天買在相對低點" in t
                assert t.count("再跌破低點") == t.count("第一版看「20 天內再跌破低點」")   # 只剩方法裡講版本沿革那一句
            else:
                assert 'class="xjmore xjres"' in h and "這一次：" not in t
            for w in BANNED:
                assert w not in h, (mk, w)


def test_rule_numbers_come_from_research():
    C = _C("tw")
    h = BP.rule_table(C, "E5")
    r = C["R"]["ev"]["E5"]["rules"]["C7"]
    c = r["lp"]                                                         # 判定依據：買在相對低點，和固定等 10 天比
    assert c["base"] == "W10"
    assert f'{BP.pct(c["lp_base"], 0)} → <b>{BP.pct(c["lp_rule"], 0)}</b>' in h
    assert f'{BP.spct(c["r_base"])} → <b>{BP.spct(c["r_rule"])}</b>' in h
    assert f'前後兩半 {BP._sp(c["lp_h1"], 0)}／{BP._sp(c["lp_h2"], 0)}' in h
    assert f'前後兩半 {BP._sp(c["r_h1"])}／{BP._sp(c["r_h2"])}' in h
    assert f'{BP.pct(c["reb_base"])} → <b>{BP.pct(c["reb_rule"])}</b>' in h
    assert f'隔天買 {BP.pct(c["lp_b1"], 0)}' in h
    assert BP.VSHORT[r["v"]] in _text(h) and r["v"] == c["v"]
    assert "再跌破低點" not in _text(h)
    b = C["R"]["ev"]["E5"]["rules"]["W10"]["lp"]                        # 對照那一行：固定等 10 天 vs 事件隔天買
    bl = BP.base_line(C, "E5")
    assert b["base"] == "b1" and f'{BP.pct(b["lp_base"], 0)} → <b>{BP.pct(b["lp_rule"], 0)}</b>' in bl
    assert BP.VSHORT[C["R"]["ev"]["E5"]["rules"]["W10"]["v"]] in _text(bl)
    assert BP.vlong("W10", "worse").startswith("比事件隔天就買差") and BP.vlong("C7", "worse").startswith("比固定等 10 天差")
    assert BP.vlong("C7", "better") == "有用：比固定等 10 天更常買在相對低點，60 日報酬沒有明顯比較少"


def test_position_cells():
    assert BP._pos_now(None) == "" and "已回到事件前高點" in BP._pos_now(1.02)
    assert "目前這一波的位置 45%<" in BP._pos_now(0.45) and "下三分之一內" in BP._pos_now(0.33)
    assert BP._lpcell({"pos": 0.2, "lp": 1}) == "20%<small>相對低點</small>"
    assert BP._lpcell({"pos": 0.6, "lp": 0}) == "60%" and BP._lpcell({}) == "—"
    L = _R()["markets"]["tw"]["ev"]["E5"]["list"]
    h = BP.list_html(_C("tw"), "E5")
    if any(x.get("lp") for x in L[-BP.LIST_MAX:]):
        assert "<small>相對低點</small>" in h


def test_five_markets_and_lists():
    C = _C("spx")
    f = _text(BP.five_html(C, "E5"))
    assert f.count("不算") >= 4 * 4                           # 美股四個指數沒有融資、新低、P/C、融資維持率（VER 4 起有寬度、90% 上漲日）
    assert "S&P 500 成分股的家數" in f
    for k in S.RULES:
        vs = [((C["all"][m]["ev"]["E5"]["rules"].get(k) or {}).get("v")) for m in S.MARKETS
              if k == "W10" or k in S.SIG_MK[m]]
        nf = [v for v in vs if v != "few"]
        if len(nf) >= 2 and len(set(nf)) == 1:
            assert re.search(BP.SHORT[k] + r".*一致", f)
    h = BP.list_html(_C("tw"), "E5")
    L = _R()["markets"]["tw"]["ev"]["E5"]["list"]
    assert h.count("<tr") == 1 + min(len(L), BP.LIST_MAX) and f"共 {len(L)} 次" in _text(h)


def test_primary_html():
    C = _C("tw")
    t = _text(BP.primary_html(C))
    P = C["primary"]
    assert f'{sum(1 for h in S.PRIMARY if P[h].get("ok"))} 個成立' in t
    for h in S.PRIMARY:
        assert h in t
        if not P[h].get("few"):
            assert f'Holm 校正後 p＝{P[h]["padj"]:.3f}' in t


def test_card_is_wired_into_both_heat_pages_and_classes_are_prefixed():
    viz = (ROOT / "arm/lab/heatviz.py").read_text(encoding="utf-8")
    # 2026-10-19 起四張研究卡搬到訊號總覽（docs/lab_signal_plan.md 第 10 節 Q3）：景氣頁照樣算、不放進頁面，存給訊號總覽
    assert "stash_cards(V)" in viz and "{face_html(V)}{SPG.block_html()}" in viz and "{today_html(V)}</div></div>{moves_html(V)}" in viz and 'href="#bottom"' not in viz
    sp = (ROOT / "arm/lab/sigpage.py").read_text(encoding="utf-8")
    assert "BP.CSS" in sp and '"bottom"' in sp
    hp = (ROOT / "arm/lab/heatpage.py").read_text(encoding="utf-8")
    assert '"bottom": bottom_now(B) if T else None' in hp
    css = set(re.findall(r"\.([a-zA-Z][\w-]*)", BP.CSS))
    from arm.lab import appnav
    from arm.lab import crashpage as CP
    from arm.lab import heatpage as HP
    from arm.lab import heatpage_us as HU
    from arm.lab import heatviz as VZ
    from arm.lab import hotchpage as QP
    from arm.lab import hotddpage as XP
    other = set(re.findall(r"\.([a-zA-Z][\w-]*)", HP._CSS + VZ.CSS + appnav.CSS + CP.CSS + XP.CSS + QP.CSS))
    shared = {"l", "vt"}                                # 景氣頁現成的 class，只在 .xj… 底下調整
    assert css - shared == {c for c in css if c.startswith("xj")} and not (css - shared) & other, \
        "卡片的 class 一律 xj 開頭、不和景氣頁撞名"
    assert re.search(r"\.xjul \.vt\b", BP.CSS)
    for c in ("l",):
        assert re.search(r"table\.xj\w+ \." + c + r"\b", BP.CSS), c


def test_committed_research_file_matches_spec():
    R = _R()
    assert set(R["markets"]) == set(S.MARKETS) and set(R["primary"]) == set(S.PRIMARY)
    for mk in S.MARKETS:
        M = R["markets"][mk]
        assert M["th"] == S.E5_TH[mk] and set(M["ev"]) == set(S.EVENTS)
        for ev in S.EVENTS:
            E = M["ev"][ev]
            assert set(E["rules"]) == {"W10", *S.SIG_MK[mk]} and set(E["groups"]) == set(S.GROUPS)
            assert all(st[v] in S.VERDICT for st in E["rules"].values() for v in ("v", "v1", "v2"))
            assert all(st["v"] == st["lp"]["v"] for st in E["rules"].values())        # 現行判定＝VER 3（買在相對低點）
            assert "w10" not in E["rules"]["W10"] and E["rules"]["W10"]["v2"] == E["rules"]["W10"]["v1"]
            assert E["rules"]["W10"]["lp"]["base"] == "b1"
            for k in S.SIG_MK[mk]:                                      # 訊號：VER 2 的判定留在 v2，VER 3 和固定等 10 天比
                assert E["rules"][k]["v2"] == E["rules"][k]["w10"]["v"] and E["rules"][k]["lp"]["base"] == "W10"
            assert E["all"]["lp"]["n"] > 0 and 0 <= E["all"]["lp"]["rate"] <= 1
            assert all(st["v"] in S.GVERDICT for st in E["groups"].values())
            assert len(E["list"]) == E["n"]


def test_group_verdict_names_the_group():
    assert BP.gv_text("fund", "up") == "底子好之後較好" and BP.gv_text("chip", "down") == "籌碼過熱後的急跌之後較差"
    assert BP.gv_text("bub", "none") == "看不出差別" and BP.gv_text("fund", "few") == "次數太少，不能判定"
    C = _C("ndx")
    t = _text(BP.study_table(C, "E5"))
    assert "第一組" not in t
    if C["R"]["ev"]["E5"]["groups"]["fund"]["v"] == "up":
        assert "底子好之後較好" in t


def test_ver4_signals_on_card():
    """VER 4（docs/lab_crash_plan.md 第 22 節）：台股多融資維持率回升（這一次另寫今天與事件以來最低的維持率）；
    美股多寬度衝刺、90% 上漲日（註明 S&P 500 成分股與存活偏誤）。"""
    a = _active("tw", fired="C9")
    a["mr"] = {"now": 152.3, "now_d": "2026-10-20", "min": 136.4, "min_d": "2026-10-16"}
    t = _text(BP.now_html(_C("tw", [a])))
    assert "融資維持率回升" in t and "維持率 152.3%（2026/10/20），事件以來最低 136.4%（2026/10/16）" in t
    assert "跌到 140% 以下，之後回到 150% 以上" in t
    for mk in ("spx", "sox"):
        rt = _text(BP.rule_table(_C(mk), "E5"))
        assert "寬度衝刺" in rt and "90% 上漲日" in rt and "S&P 500 成分股，1996 年起" in rt
        assert "融資維持率" not in rt
    assert "月底市值 40 億以上的股票" in BP.sig_def("tw", "C3") and "S&P 500" not in BP.sig_def("tw", "C8")
