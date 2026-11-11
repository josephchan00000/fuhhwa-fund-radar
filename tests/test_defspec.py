"""個股策略防守研究的規格 defspec VER 1 鎖定（docs/lab_stock_page_plan.md 第 4.2、9 節）：算任何結果之前寫定，改任何常數都要 VER＋1。"""
from arm.lab import defspec as D


def test_locked():
    assert D.VER == 1 and D.SPEC_DATE == "2026-11-11"
    assert D.fingerprint() == "df8523a2c990ad01"


def test_user_decisions_and_plan():
    # 使用者 2026-11-11：三種都研究；判定照規劃第 4.2 節（年報酬少不超過 2 點、最大跌幅淺 5 點以上、前後兩半都成立）
    assert D.SLICES == ("boom", "v3l", "qm")
    assert (D.D1_MA, D.D2_K, D.D3_MULT) == (60, 2, 1.0)
    assert (D.MAX_CAGR_LOSS, D.MIN_DD_GAIN) == (0.02, 0.05)


def test_judge():
    base = {k: {"cagr": 0.30, "mdd": 0.50} for k in ("all", "h1", "h2")}
    good = {k: {"cagr": 0.285, "mdd": 0.44} for k in ("all", "h1", "h2")}
    assert D.judge(base, good)["verdict"] == "過關"
    bad_half = {**good, "h2": {"cagr": 0.27, "mdd": 0.40}}                 # 後半年報酬少 3 點
    assert D.judge(base, bad_half)["verdict"] == "沒過" and not D.judge(base, bad_half)["ok"]["h2"]["cagr"]
    shallow = {k: {"cagr": 0.31, "mdd": 0.47} for k in ("all", "h1", "h2")}  # 跌幅只淺 3 點
    assert D.judge(base, shallow)["verdict"] == "沒過"
    edge = {k: {"cagr": 0.28, "mdd": 0.45} for k in ("all", "h1", "h2")}    # 剛好在線上算過
    assert D.judge(base, edge)["verdict"] == "過關"
