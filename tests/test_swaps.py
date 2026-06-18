"""換股自動偵測 _compute_swaps 的單元測試 —— 鎖住 2026-06-18 的出錯點：
零股雜訊（1 張零股出清）不可被當成換股而蓋掉真正的大換股（新進聯電 8,500 張）。
動作與張數一律由 DB 持股快照算、不手寫，這層測試保證演算法不退化。"""
from arm.firsthand import _compute_swaps, _SWAP_MIN_LOTS


def s(shares, weight, name):
    return {"name": name, "shares": shares, "weight": weight}


def test_new_add_cut_detected_and_sorted():
    # 真實情境（00991A 06-16→06-17）：新進聯電、減碼奇鋐、加碼台光電
    prev = {"3017": s(750_000, 2.30, "奇鋐科技"), "2383": s(820_000, 7.00, "台光電子")}
    cur = {"2303": s(8_500_000, 1.90, "聯華電子"),
           "3017": s(600_000, 2.27, "奇鋐科技"),
           "2383": s(850_000, 7.06, "台光電子")}
    rows = _compute_swaps(prev, cur)
    by = {r["code"]: r for r in rows}
    assert by["2303"]["move"] == "新進"
    assert by["3017"]["move"] == "減碼"
    assert by["2383"]["move"] == "加碼"
    # 張數變化最大者排第一（聯電 +8,500 張）
    assert rows[0]["code"] == "2303"
    assert by["2303"]["share_delta"] == 8_500_000


def test_zero_lot_exit_is_filtered_out():
    # 富世達 1 張零股出清 + 其餘續抱 → 視為『無實質換股』（空），不可蓋過先前的真換股
    prev = {"9999": s(1_000, 0.0, "富世達股"), "2327": s(9_670_000, 9.67, "國巨")}
    cur = {"2327": s(9_670_000, 9.67, "國巨")}
    assert _compute_swaps(prev, cur) == []


def test_no_change_returns_empty():
    h = {"2327": s(9_670_000, 9.67, "國巨"), "2330": s(7_000_000, 13.91, "台積電")}
    assert _compute_swaps(h, h) == []


def test_small_lots_but_high_weight_kept():
    # 張數變動 < 門檻，但屬高權重既有持股的微調仍應保留（_SWAP_MIN_WEIGHT 規則）
    assert _SWAP_MIN_LOTS >= 5
    prev = {"2330": s(7_000_000, 13.91, "台積電")}
    cur = {"2330": s(7_001_000, 13.92, "台積電")}   # +1 張、但權重 13.92% ≥ 0.2%
    rows = _compute_swaps(prev, cur)
    assert len(rows) == 1 and rows[0]["move"] == "加碼"
