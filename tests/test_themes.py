"""題材/時事引擎單元測試（M5）：題材熱度由當日真實漲幅彙總，而非固定清單。

關鍵設計：以 stock_id 分類（非名稱），避免「聯電」⊂「群聯電子」這類子字串誤判，
且 TWSE 與復華對同一檔的名稱不同（台積電 vs 台灣積體）時仍能對齊。
"""
from arm import signals, themes


def _rec(name, close, change):
    return {"name": name, "close": close, "change": change, "volume": 1000}


# 記憶體：三檔皆強漲；被動元件：持平/小跌（非熱題）。代號為鍵。
ALL_TODAY = {
    "2408": _rec("南亞科", 110.0, 10.0),    # +10%
    "2344": _rec("華邦電", 53.0, 3.0),      # +6%
    "2337": _rec("旺宏", 26.0, 1.0),        # +4%
    "2327": _rec("國巨*", 402.0, 2.0),      # +0.5%（名稱帶 * 也不影響，靠代號）
    "2492": _rec("華新科", 99.0, -1.0),     # -1%
    "3026": _rec("禾伸堂", 100.2, 0.2),     # +0.2%
    "8299": _rec("群聯", 600.0, 30.0),      # +5.3%（NAND，驗證不會被當晶圓代工）
    "9999": _rec("某隨機股", 50.0, 5.0),    # 不在題材表內 → 忽略
}

THEME_MAP = {
    "記憶體循環反轉": {"2408": "南亞科", "2344": "華邦電", "2337": "旺宏"},
    "被動元件回升": {"2327": "國巨", "2492": "華新科", "3026": "禾伸堂"},
    "晶圓代工/成熟製程": {"2303": "聯電", "5347": "世界先進"},
    "NAND控制IC": {"8299": "群聯"},
}


def test_normalize_map_dict_and_list():
    g = themes.normalize_map(THEME_MAP)
    assert g["記憶體循環反轉"] == ["2408", "2344", "2337"]
    assert themes.normalize_map({"X": ["1101", "1102"]})["X"] == ["1101", "1102"]


def test_id_to_theme_no_substring_collision():
    t2 = themes.id_to_theme(THEME_MAP)
    # 群聯(8299) 必須是 NAND，而非被「聯電」名稱子字串誤分到晶圓代工
    assert t2["8299"] == "NAND控制IC"
    assert t2["2303"] == "晶圓代工/成熟製程"


def test_pct_of():
    assert abs(themes.pct_of(_rec("x", 110.0, 10.0)) - 0.10) < 1e-9
    assert themes.pct_of({"close": None, "change": 1.0}) is None


def test_theme_heat_ranks_real_movers_first():
    heat = themes.theme_heat(ALL_TODAY, THEME_MAP)
    assert list(heat)[0] == "記憶體循環反轉"
    assert heat["記憶體循環反轉"]["heat"] > heat["被動元件回升"]["heat"]
    mem = heat["記憶體循環反轉"]
    assert mem["n_total"] == 3 and mem["n_strong"] == 3 and mem["n_up"] == 3
    assert mem["members"][0]["stock_id"] == "2408"        # 漲最多者排第一
    # 晶圓代工兩檔今日皆無資料（2303/5347 不在 ALL_TODAY）→ 不應出現
    assert "晶圓代工/成熟製程" not in heat


def test_hot_themes_threshold_excludes_cold():
    heat = themes.theme_heat(ALL_TODAY, THEME_MAP)
    names = [t for t, _ in themes.hot_themes(heat, min_heat=25.0)]
    assert "記憶體循環反轉" in names
    assert "被動元件回升" not in names                    # 沒在漲 → 不算熱題


def test_fund_tailwinds_picks_hot_and_heavy():
    holdings = [
        {"stock_id": "2408", "stock_name": "南亞科技", "weight": 12.0},
        {"stock_id": "2344", "stock_name": "華邦電子", "weight": 8.0},
        {"stock_id": "2327", "stock_name": "國巨股份", "weight": 15.0},   # 重倉但題材沒漲
    ]
    tw = themes.fund_tailwinds(holdings, ALL_TODAY, THEME_MAP)
    assert tw, "應至少有一個順風題材"
    top = tw[0]
    assert top["theme"] == "記憶體循環反轉"
    assert abs(top["fund_weight"] - 20.0) < 1e-9          # 12 + 8
    assert all(s["theme"] != "被動元件回升" for s in tw)   # 冷題被排除


def test_theme_tailwind_detector_fires_with_real_heat():
    holdings = [
        {"stock_id": "2408", "stock_name": "南亞科技", "weight": 12.0},
        {"stock_id": "2344", "stock_name": "華邦電子", "weight": 8.0},
    ]
    tw = themes.fund_tailwinds(holdings, ALL_TODAY, THEME_MAP)
    sig = signals.d_theme_tailwind({"theme_tailwinds": tw})
    assert sig is not None and sig.detector == "THEME_TAILWIND"
    assert "記憶體循環反轉" in sig.headline
    assert sig.theme_fit == tw[0]["market_heat"]          # theme_fit 改吃真實熱度
    assert signals.d_theme_tailwind({"theme_tailwinds": []}) is None
