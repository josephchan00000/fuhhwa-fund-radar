"""arm/treemap.py：squarified treemap 佈局（ETF 持股異動方塊圖）。"""
from arm import treemap


def _overlap(a, b) -> bool:
    return (a["x"] < b["x"] + b["w"] - 1e-6 and b["x"] < a["x"] + a["w"] - 1e-6
            and a["y"] < b["y"] + b["h"] - 1e-6 and b["y"] < a["y"] + a["h"] - 1e-6)


def test_layout_面積與值成比例():
    rects = treemap.layout([("a", 50), ("b", 30), ("c", 20)], w=100, h=100)
    area = {r["key"]: r["w"] * r["h"] for r in rects}
    assert abs(area["a"] - 5000) < 1
    assert abs(area["b"] - 3000) < 1
    assert abs(area["c"] - 2000) < 1


def test_layout_不重疊且不出界():
    items = [(f"s{i}", v) for i, v in enumerate([40, 25, 15, 10, 6, 3, 1])]
    rects = treemap.layout(items, w=100, h=60)
    for r in rects:
        assert r["x"] >= -1e-6 and r["y"] >= -1e-6
        assert r["x"] + r["w"] <= 100 + 1e-6
        assert r["y"] + r["h"] <= 60 + 1e-6
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert not _overlap(a, b), f"{a['key']} 與 {b['key']} 重疊"


def test_layout_依值由大到小():
    rects = treemap.layout([("小", 1), ("大", 100), ("中", 10)])
    assert [r["key"] for r in rects] == ["大", "中", "小"]


def test_layout_剔除非正值與空輸入():
    assert treemap.layout([]) == []
    assert treemap.layout([("a", 0), ("b", None), ("c", -5)]) == []
    assert [r["key"] for r in treemap.layout([("a", 0), ("b", 7)])] == ["b"]


def test_layout_零尺寸容器不炸():
    assert treemap.layout([("a", 5)], w=0, h=10) == []
    assert treemap.layout([("a", 5)], w=10, h=0) == []


def test_layout_單一項目填滿容器():
    r = treemap.layout([("a", 9)], w=80, h=40)[0]
    assert abs(r["w"] - 80) < 1e-6 and abs(r["h"] - 40) < 1e-6


def test_grouped_外層依群組合計_內層在群組內():
    groups = [("半導體業", [("2330", 60), ("2337", 20)]),
              ("塑膠工業", [("1303", 20)])]
    gs = treemap.grouped(groups, w=100, h=100, gap=1.0, head=6.0)
    assert [g["key"] for g in gs] == ["半導體業", "塑膠工業"]
    assert abs(gs[0]["w"] * gs[0]["h"] - 8000) < 1
    for g in gs:
        for it in g["items"]:
            assert it["x"] >= g["x"] - 1e-6
            assert it["y"] >= g["y"] + g["head"] - 1e-6
            assert it["x"] + it["w"] <= g["x"] + g["w"] + 1e-6
            assert it["y"] + it["h"] <= g["y"] + g["h"] + 1e-6


def test_grouped_矮群組不留標題空間():
    # 一個極小群組 → 高度不足，head 應為 0（否則內層被壓成細線）
    gs = treemap.grouped([("大", [("a", 1000)]), ("小", [("b", 1)])],
                         w=100, h=100, head=7.0, head_min_h=18.0)
    small = [g for g in gs if g["key"] == "小"][0]
    if small["h"] < 18.0:
        assert small["head"] == 0.0


def test_grouped_群組間不重疊():
    groups = [(f"g{i}", [(f"i{i}", v)]) for i, v in enumerate([50, 30, 12, 5, 3])]
    gs = treemap.grouped(groups, w=100, h=70)
    for i, a in enumerate(gs):
        for b in gs[i + 1:]:
            assert not _overlap(a, b)


def test_keep_order_保留呼叫端順序():
    items = [("小", 1), ("大", 100), ("中", 10)]
    assert [r["key"] for r in treemap.layout(items, keep_order=True)] == ["小", "大", "中"]
    assert [r["key"] for r in treemap.layout(items)] == ["大", "中", "小"]


def test_keep_order_最後一項落在右下角():
    """squarify 由左上往右下逐段填滿 → 最後排入者的矩形一定含右下角 (100,100)。
    「想把某幾格塞到右下角」就靠這個性質（ETF 異動圖的『其他 N 檔』）。"""
    items = [("a", 40), ("b", 25), ("c", 15), ("d", 12), ("其他", 8)]
    rects = treemap.layout(items, keep_order=True)
    last = rects[-1]
    assert last["key"] == "其他"
    assert last["x"] + last["w"] > 99.9 and last["y"] + last["h"] > 99.9


def test_keep_order_面積仍與值成比例():
    rects = treemap.layout([("a", 50), ("b", 30), ("其他", 20)], keep_order=True)
    area = {r["key"]: r["w"] * r["h"] for r in rects}
    assert abs(area["a"] - 5000) < 1 and abs(area["其他"] - 2000) < 1
