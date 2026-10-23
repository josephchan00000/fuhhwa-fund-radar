"""景氣頁「反向檢查：籌碼連續過熱、技術面轉空」卡（arm/lab/hotchpage.py；docs/lab_hotdd_plan.md 第 7.5.9、9 節）：
一句話、籌碼表（今天的狀態框起來）、每一段、技術面表、大跌時訊號的位置、主要假說、用字、class 前綴。
研究數字只讀研究檔，不在頁面重算。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from arm.lab import hotch as X
from arm.lab import hotchpage as QP
from arm.lab import hotchspec as S

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_heatpage import BANNED  # noqa: E402


def _text(h: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r'title="[^"]*"', "", h)))


def _now(mk: str, R: dict, w: dict | None = None, recent: dict | None = None, states: dict | None = None) -> dict:
    """假的「今天」：w＝{項目: 已連續週數}，其他項目今天 50（不熱）。"""
    w = w or {}
    chip = {}
    for k in R["A"]:
        n = w.get(k, 0)
        chip[k] = {"v": 90.0 if n else 50.0, "w": n, "key": X.state_key(n), "run": None}
    return {"d": R["end"], "chip": chip, "recent": {k: (recent or {}).get(k, []) for k in S.TECH_EVENTS},
            "states": states or {k: {"on": False} for k in S.TECH_STATES}, "tech": 50.0}


def _C(mk: str = "tw", **kw) -> dict:
    R = X.load_research()
    assert R and R["ver"] == S.VER, "研究檔要先跑：TZ=Asia/Taipei python3 scripts/run_hotch.py"
    RM = R["markets"][mk]
    names = {k: k for k in RM["A"]}
    names.update({"C1": "融資餘額水位", "C3": "券資比"})
    return {"mk": mk, "px": "", "R": RM, "now": _now(mk, RM, **kw), "primary": R["primary"], "names": names,
            "order": QP.ORDER["tw" if mk == "tw" else "us"]}


def test_matched_state_falls_back_when_top_state_is_few():
    C = _C("tw", w={"C1": 46})
    assert C["now"]["chip"]["C1"]["key"] == "H26"
    top = QP._A(C, "C1", "H26").get("v")
    m = QP.matched(C, "C1")
    if top == "few":                                    # 26 週以上樣本不足 → 往下一層（13 週以上）
        assert m == "H13"
    else:
        assert m == "H26"
    assert QP.matched(_C("tw", w={"C1": 0}), "C1") == "H0"


def test_lead_reports_hot_chip_state_and_tech_counts():
    C = _C("tw", w={"C1": 46, "C2": 2}, recent={"ma60_dn": ["2026-10-01"]})
    ls = QP.lead(C)
    assert len(ls) == 3
    assert ls[0].startswith("籌碼：現在 2 項過熱") and "融資餘額水位已連續 46 週" in ls[0]
    key = QP.matched(C, "C1")
    st = QP._A(C, "C1", key)
    assert S.STATE_NAMES[key] in ls[0] and QP.pct(st["ev"]["med"]) in ls[0]
    ev = C["R"]["B"]["ev"]
    n_up = sum(1 for k in S.TECH_EVENTS if ev[k].get("v") == "up")
    assert f"比平常大的 {n_up} 種" in ls[1] and "最近 3 個月出現：跌破季線（2026/10/1）" in ls[1]
    d = C["R"]["B"]["dsum"]["20"]["ma60_dn"]
    assert f'跌 20% 以上的 {d["n"]} 次大跌，跌破季線在 {d["hit"]} 次' in ls[2]
    l0 = QP.lead(_C("tw"))[0]
    assert l0.startswith("籌碼：現在沒有籌碼項目過熱。")
    C2 = _C("spx")
    l2 = QP.lead(C2)[0]
    assert l2.startswith("情緒籌碼：現在沒有情緒籌碼項目過熱。")
    if not any(QP._A(C2, k, s).get("v") == "up" for k in C2["order"] for s in S.STATES_A):
        assert "沒有一項判定比平常大" in l2


def test_card_structure_numbers_and_banned_words():
    for mk in S.MARKETS:
        C = _C(mk, w={C0: 5 for C0 in list(QP.ORDER["tw" if mk == "tw" else "us"])[:1]},
               states={"below60": {"on": True, "since": "2026-09-01", "days": 30}, "below240": {"on": False}, "cold": None})
        h = QP.card(C)
        t = _text(h)
        assert h.count('id="hotch"') == 1 and "反向檢查：籌碼連續過熱、技術面轉空" in t
        n_rows = sum(1 for k in C["order"] + S.CONTRAST_VARS if k in C["R"]["A"])
        assert h.count('<td class="l"><b>') == n_rows                   # 籌碼表一個項目一列
        few = [k for k in C["order"] if k in C["R"]["A"] and QP.all_few(C, k)]
        if few:                                                          # 全部狀態都樣本不足的項目收在後面
            assert f"樣本不足的 {len(few)} 項" in t
            head = h[:h.index("樣本不足的 ")]
            assert all(f'<b>{C["names"].get(k, k)}</b>' not in head for k in few)
        tb = h[h.index('class="xqbt"'):h.index("</table>", h.index('class="xqbt"'))]
        assert tb.count("<tr") == 1 + len(S.TECH_EVENTS) + len(S.TECH_STATES) + 1
        assert h.count("xqnow") == n_rows                                # 每一列都有一格是今天的狀態
        assert "現在是（2026/9/1 起）" in t
        assert t.count("對照，不判定") == 1                              # 對照列只列數字（規格第 4 節）
        k0 = C["order"][0]
        st = QP._A(C, k0, "H1")
        if st.get("n"):
            assert QP.pct(st["ev"]["med"]) in t
        for w in BANNED:
            assert w not in h, (mk, w)
        assert ("HX1" in t) == (mk == "tw") and ("HX5" in t) == (mk == "spx")


def test_runs_list_includes_current_run_and_counts():
    C = _C("tw", w={"C1": 46})
    C["now"]["chip"]["C1"]["run"] = {"a": "2025-11-28", "s4": "2025-12-19", "wk": 46, "mdd": 0.164, "pk": "2026-06-22",
                                     "tr": "2026-07-30", "days": 200}
    h = QP.runs_html(C)
    t = _text(h)
    runs = C["R"]["A"]["C1"]["runs"]
    assert f"融資餘額水位：{len(runs)} 段" in t and "還在過熱" in t and "16.4%" in t
    ps = [r["pct"] for r in runs if not r.get("open") and r.get("pct") is not None]
    n_hi = sum(1 for p in ps if p >= 0.5)
    assert f"結束後已滿 3 個月的 {len(ps)} 段裡，{n_hi} 段比同樣長度的期間跌得多" in t


def _row(a, s4, z, wk, op, hot=None, mdd=0.1, pct_=0.5):
    r = {"a": a, "s4": s4, "z": z, "wk": wk, "open": op, "mdd": mdd, "pk": a, "tr": z, "days": 80}
    if hot is not None:
        r["hot"] = hot
    if not op:
        r["pct"] = pct_
    return r


def test_runs_tags_follow_today_not_the_research_file():
    """研究檔不常重跑：段的狀態以每天算的為準。結束了但還沒滿 3 個月的段不可寫「還在過熱」（2026-10-19 券資比 6/12→8/7）。"""
    C = _C("tw", w={"C1": 46})
    C["now"]["runs"] = {
        "C1": [_row("2025-11-28", "2025-12-19", "2026-10-16", 46, True, hot=True, mdd=0.164),
               _row("2024-03-15", "2024-04-05", "2025-03-28", 54, False, hot=False, mdd=0.287, pct_=0.86)],
        "C3": [_row("2026-06-12", "2026-07-03", "2026-08-07", 9, True, hot=False, mdd=0.142),
               _row("2026-03-06", "2026-03-27", "2026-05-29", 13, False, hot=False, mdd=0.164, pct_=0.8)]}
    t = _text(QP.runs_html(C))
    c1, c3 = t[t.index("融資餘額水位："):t.index("券資比：")], t[t.index("券資比："):]
    assert "還在過熱" in c1 and "結束未滿 3 個月" not in c1
    assert "結束未滿 3 個月" in c3 and "還在過熱" not in c3
    assert "融資餘額水位：2 段；結束後已滿 3 個月的 1 段裡，1 段比同樣長度的期間跌得多、1 段跌超過 10%" in t
    # 只有研究檔的段（沒有 hot）：今天正在進行的那一段才算還在過熱，其他 open 的段＝結束未滿 3 個月
    cur = {"s4": "2025-12-19"}
    assert QP.run_tag({"open": True, "s4": "2025-12-19"}, cur) == "還在過熱"
    assert QP.run_tag({"open": True, "s4": "2026-07-03"}, cur) == "結束未滿 3 個月"
    assert QP.run_tag({"open": True, "s4": "2026-07-03"}, None) == "結束未滿 3 個月"
    assert QP.run_tag({"open": False, "s4": "2024-04-05"}, cur) == ""


def test_run_keys_top_items_plus_items_hot_four_weeks():
    A = {"C1": {"runs": [1]}, "C3": {"runs": [1]}, "W1": {"runs": [1]}, "C2": {}}
    chip = {"C2": {"w": 5}, "W1": {"w": 3}, "C3": {"w": 9}}
    assert QP.run_keys(("C1", "C3", "W1", "W2", "C2"), A, chip) == ["C1", "C3", "C2"]
    assert QP.run_keys(("C1", "C3"), {}, {}) == []


def test_hotdd_note_names_chip_items_with_bigger_drawdowns():
    C = _C("tw")
    note = QP.hotdd_note(C)
    ups = [k for k in C["order"] if any(QP._A(C, k, s).get("v") == "up" for s in S.STATES_A)]
    if ups:
        assert all(C["names"][k] in note for k in ups) and "判定比平常大" in note
    assert QP.hotdd_note(None) is None


def test_card_is_wired_into_both_heat_pages_and_classes_are_prefixed():
    viz = (ROOT / "arm/lab/heatviz.py").read_text(encoding="utf-8")
    # 2026-10-19 起四張研究卡搬到訊號總覽（docs/lab_signal_plan.md 第 10 節 Q3）：景氣頁照樣算、不放進頁面，存給訊號總覽
    assert "stash_cards(V)" in viz and "{face_html(V)}{today_html(V)}{SPG.block_html()}" in viz and 'href="#hotch"' not in viz
    sp = (ROOT / "arm/lab/sigpage.py").read_text(encoding="utf-8")
    assert "QP.CSS" in sp and '"hotch"' in sp
    assert "note=QP.hotdd_note(V.get(\"hotch\")) if hotch else None" in viz
    hp = (ROOT / "arm/lab/heatpage.py").read_text(encoding="utf-8")
    assert '"hotch": hotch_now(B) if T else None' in hp
    css = set(re.findall(r"\.([a-zA-Z][\w-]*)", QP.CSS))
    from arm.lab import appnav
    from arm.lab import crashpage as CP
    from arm.lab import heatpage as HP
    from arm.lab import heatpage_us as HU
    from arm.lab import heatviz as VZ
    from arm.lab import hotddpage as XP
    other = set(re.findall(r"\.([a-zA-Z][\w-]*)", HP._CSS + VZ.CSS + appnav.CSS + CP.CSS + XP.CSS))
    shared = {"l"}                                   # 景氣頁現成的 class，只在 table.xq… 底下調整
    assert css - shared == {c for c in css if c.startswith("xq")} and not (css - shared) & other, \
        "卡片的 class 一律 xq 開頭、不和景氣頁撞名"
    for c in shared:
        assert re.search(r"table\.xq\w+ td\." + c + r"\b", QP.CSS), c


def test_committed_research_file_matches_spec():
    R = X.load_research()
    assert R and R["ver"] == S.VER and set(R["markets"]) == set(S.MARKETS) and set(R["primary"]) == set(S.PRIMARY)
    tw = R["markets"]["tw"]
    assert tw["start"] == S.TW_START and set(tw["A"]) == set(S.CHIP_VARS["tw"]) | set(S.CONTRAST_VARS)
    for mk in S.MARKETS:
        B = R["markets"][mk]["B"]
        assert set(B["ev"]) == set(S.TECH_EVENTS) and set(B["st"]) == set(S.TECH_STATES)
        for st in list(B["ev"].values()) + list(B["st"].values()):
            assert st["v"] in S.VERDICT and st["vv"] in S.VERDICT
