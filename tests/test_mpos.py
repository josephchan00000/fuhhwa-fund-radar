"""股市位階（arm/lab/mpos.py；規格 arm/lab/mposspec.py VER 3：台股＋美股四個指數）。"""
import json

from arm.lab import mpos as M
from arm.lab import mposspec as S


def _B(n=1400, **over):
    cal = [f"D{i:05d}" for i in range(n)]
    heat = {k: [50.0] * n for _, ks in S.GROUPS for k in ks}
    heat.update(over)
    inc = {"tech": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T11", "T12", "T13"],
           "chip": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C11"]}
    return {"cal": cal, "heat": heat, "inc": inc, "comp": {}}


def test_groups_follow_scored_items():
    g = dict(M.groups({"tech": ["T1", "T9"], "chip": ["C7"]}))
    assert g["價格位置"] == ["T1"] and g["情緒"] == ["T9", "C7"] and g["廣度"] == []
    g = dict(M.groups(_B()["inc"]))
    assert "T10" not in g["情緒"]                                      # 台指隱含波動率沒有算分 → 不放


def test_min_items_and_rank():
    n = 1400
    rising = [float(i % 100) for i in range(n)]
    B = _B(n, T1=rising, T2=rising)
    B["heat"]["C4"] = [None] * n                                       # 部位與籌碼少一項也照算（至少 2 項）
    X = M.compute(B)
    assert X["g"]["部位與籌碼"][0] == 50.0 and X["v"][S.MIN_DAYS - 2] is None and X["v"][S.MIN_DAYS] is not None
    B2 = _B(n)
    for k in ("T5", "T6"):
        B2["heat"][k] = [None] * n                                     # 廣度只剩 1 項 → 那一組沒分數 → 沒有原值
    assert all(x is None for x in M.compute(B2)["raw"])
    # 比當天低的天數 ÷ 有值的天數 × 10
    const = M.compute(_B(n))
    assert const["v"][-1] == 0.0 and M.label(0.0) == "極端低位" and M.label(8.0) == "高位" and M.label(5) == "中間"


def test_peaks_merge_same_kind():
    d = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(300)]
    v = [5.0] * 300
    v[50], v[80], v[200] = 9.0, 9.5, 1.0                               # 50 和 80 相隔 < 60 天 → 只留 9.5
    pk = M.peaks(d, v)
    assert [(p[1], p[2]) for p in pk] == [(9.5, "hi"), (1.0, "lo")]


def test_record_only_first_value(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "LOG", tmp_path / "mpos_log.json")
    X = {"cal": ["2026-11-18", "2026-11-19"], "v": [0.5, 0.4], "raw": [29.0, 28.7], "g": {n: [1.0, 2.0] for n, _ in S.GROUPS}}
    log = {}
    assert M.record(X, log) and not M.record(dict(X, v=[0.5, 0.9]), log)
    assert json.loads((tmp_path / "mpos_log.json").read_text())["days"]["2026-11-19"]["v"] == 0.4


def test_block_text_and_revision_line():
    n = 1400
    B = _B(n, T1=[float(i % 100) for i in range(n)])
    B["cal"] = [f"20{20 + i // 250:02d}-{1 + (i // 21) % 12:02d}-{1 + i % 21:02d}" for i in range(n)]
    X = M.compute(B)
    prev_day = B["cal"][-2]
    h = M.block(B, X, log={prev_day: {"v": round(X["v"][-2] + 0.3, 1)}})
    assert 'id="mpz"' in h and "股市位階" in h and "/10" in h and "過去 10 年有" in h and "空心圈＝昨天" in h
    assert f"昨天公布 {round(X['v'][-2] + 0.3, 1):g}，用今天的資料重算是 {X['v'][-2]:g}" in h
    assert "藍帶＝低（3 以下）、紅帶＝高（8 以上）" in h and 'class="mpz-svg"' in h
    for w in ("判定", "樣本外", "門檻", "規格", "VER", "百分位"):
        assert w not in h
    assert M.block(B, X, log={}).count("昨天公布") == 0


def _BU(n=1400, breadth=True):
    """美股一個指數：breadth=False 像那斯達克、費半（廣度沒有算分的項目）。"""
    cal = [f"20{20 + i // 250:02d}-{1 + (i // 21) % 12:02d}-{1 + i % 21:02d}" for i in range(n)]
    heat = {k: [50.0] * n for _, ks in S.GROUPS_US for k in ks}
    heat["T1"] = [float(i % 100) for i in range(n)]
    tech = ["T1", "T2", "T3", "T4", "T8", "T9", "T11", "T12", "T13"] + (["T15"] if breadth else ["T14"])
    inc = {"tech": tech, "sent": ["S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10"]}
    return {"cal": cal, "heat": heat, "inc": inc, "comp": {"fund": [60.0] * n, "liq": [30.0] * n}}


def test_us_empty_group_left_out():
    B = _BU(breadth=False)
    X = M.compute(B, S.GROUPS_US)
    assert X["items"]["廣度"] == [] and X["v"][-1] is not None              # 廣度沒有項目 → 其他三組照算
    i = len(B["cal"]) - 1
    want = sum(X["g"][n][i] for n in ("價格位置", "部位與籌碼", "情緒")) / 3
    assert abs(X["raw"][i] - want) < 1e-9
    Xs = M.compute(_BU(breadth=True), S.GROUPS_US)
    assert Xs["items"]["廣度"] == ["T15"] and Xs["g"]["廣度"][-1] == 50.0   # 只有 T15 一項 → 照第 2 點，min(2, 1)＝1 項就算


def test_us_block_and_log_path():
    from arm.lab import heatspec as HS, heatspec_us as U
    B = _BU(breadth=False)
    with HS.use(U.spec_for("sox")):                                          # 美股頁在美股規格底下產生（heatpage_us.index_page）
        h = M.block(B, M.compute(B, S.GROUPS_US), log={}, mk="sox")
    assert 'id="mpz"' in h and "沒有算分的項目" in h and "這個指數的廣度沒有算分的項目，不放進平均" in h
    assert "基本面" in h and "資金寬裕度" in h
    assert M.log_path("tw").name == "mpos_log.json" and M.log_path("sox").name == "mpos_log_sox.json"
    BT = _B(T1=[float(i % 100) for i in range(1400)])
    BT["cal"] = B["cal"]
    th = M.block(BT, log={})
    assert "沒有算分的項目" not in th                                      # 台股四組都有項目
