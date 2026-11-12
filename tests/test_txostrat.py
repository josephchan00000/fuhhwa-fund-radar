"""選擇權頁的分頁與「策略」分頁（arm/lab/txopage.py、arm/lab/txostrat.py；docs/lab_txo_plan.md 第 20 節）。"""
from arm.lab import txopage, txostrat

RES = {"O2": {"judge": {"verdict": "沒過"}, "main": {"n": 220, "mean": -1349.5, "win": 0.1727, "final": 703105.5, "maxdd": 0.3059},
              "compare": {"short": {"mean": -1515.0}}},
       "O3": {"judge": {"verdict": "過關"}, "main": {"n": 49, "mean": 16777.4, "win": 0.5714, "final": 1822090.6, "maxdd": 0.0894,
                                                    "mean_ex_top3": 9422.5, "years_ok": 0.68, "worst_ret": -0.7554},
              "compare": {"index": {"mean_ret": 0.012}}}}
SET = {"asof": "2026-11-10",
       "o1": {"judge": {"verdict": "沒過"}, "oos": {"n": 387, "mean": -2246.8, "win": 0.0879, "final": 130478.2, "maxdd": 0.8695},
              "compare": {"two": {"mean": -1489.6}, "hold": {"mean": -2222.0}, "seller": {"mean": 1037.1}}},
       "o4": {"judge": {"verdict": "只列、不判定（筆數不夠）"}, "metrics": {"n": 1, "mean": 2204.6, "win": 1.0, "final": 1002204.6, "maxdd": 0.0},
              "days": [{"d": "2026-09-18"}] * 15,
              "trades": [{"d": "2026-11-06", "kx": 39600.0, "cp": "C", "p0": 175.0, "pnl": 2204.6}]}}


def test_strategy_tab_lists_all_four_with_honest_verdicts():
    h = txostrat.block(RES, SET)
    assert h.count('class="ts-c"') == 4 and 'class="ts-c ts-case"' in h                # 四條＋11/11 案例
    assert "過關 <b>1</b>" in h and "沒過 <b>2</b>" in h and "筆數不夠、還在記 <b>1</b>" in h
    for name in ("O3 節慶前買買權", "O1 結算日順勢", "O4 結算均價", "O2 大事件前買跨式"):
        assert name in h
    assert "＝你 11/11 報告的 A" in h and "＝你 11/11 報告的 B" in h                      # 使用者給的策略看得到
    assert "−2,247 元" in h and "+16,777 元" in h and "13 萬" in h and "182 萬" in h
    assert "同時買兩檔 −1,490 元" in h and "抱到結算 −2,222 元" in h and "+1,037 元" in h
    assert "11/6 買 39,600 買權 175 點" in h and "15 個結算日" in h and "資料到 11/10" in h
    assert h.index("O3 節慶前買買權") < h.index("O1 結算日順勢")                         # 過關的排最前面


def test_strategy_tab_without_files_says_no_results():
    h = txostrat.block({}, {})
    assert h.count("還沒有成績") >= 4 and "ts-kv" not in h


def test_options_page_has_four_tabs_and_lazy_stock_frame(tmp_path):
    out = tmp_path / "x9op.html"
    txopage.build(out=out, data=None, pm=None)
    h = out.read_text(encoding="utf-8")
    nav = h.split('<nav class="optab"', 1)[1].split("</nav>", 1)[0]
    assert [x.split('"')[0] for x in nav.split('data-t="')[1:]] == ["pm", "st", "calc", "stk"]
    assert ">盤前<" in nav and ">策略<" in nav and ">計算機<" in nav and ">個股<" in nav
    for k in ("pm", "st", "calc", "stk"):
        assert f'id="{k}" role="tabpanel"' in h
    assert '<iframe id="stkf" title="選股" data-src="x9.html">' in h and ' src="x9.html"' not in h  # 點到才載入
    assert "測過的選擇權策略" in h and 'id="opapp"' in h and "還沒準備好" in h
    assert 'class="opcalc"' not in h                                                 # 計算機不再收在折疊裡
    assert 'class="opq"' not in h                                                    # 選擇權頁自己不放「.」入口
