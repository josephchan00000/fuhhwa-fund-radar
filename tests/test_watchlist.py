"""超級飆股觀察名單（watchlist.py、vcp.py）：VCP 純 Python 版與研究版一致、名單標籤、頁面資料。"""
import sys
from pathlib import Path

import pytest

from arm.lab import vcp as VC
from arm.lab import watchlist as WL

ROOT = Path(__file__).resolve().parents[1]


def _interp(points):
    out = []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        for x in range(x0, x1):
            out.append(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    out.append(points[-1][1])
    return out


def _vcp_closes():
    """250 天往上走（100→200）；之後基底：200 → −24% → 196 → −12% → 194 → −5% → 回到 193。"""
    return _interp([(0, 100), (250, 200), (275, 152), (300, 196), (320, 172.5), (340, 194), (352, 184.3), (365, 193)])


def test_vcp_textbook_pattern():
    c = _vcp_closes()
    v = [1e6] * len(c)
    for k in range(356, len(c)):
        v[k] = 4e5                                                  # 最後一段量縮
    r = VC.check(c, c, c, v, len(c) - 1)
    assert r["ok"] and r["n"] == 3 and r["pivot"] == 194.0
    assert round(r["d1"], 3) == 0.24 and round(r["dn"], 3) == 0.05
    v2 = [1e6] * len(c)                                             # 量沒縮 → 不成立
    assert not VC.check(c, c, c, v2, len(c) - 1)["ok"]


def test_vcp_matches_research_version():
    """和 tw-superstock-lab features.vcp（VCP_V2）在同一份人造價格上逐日一致。"""
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    sys.path.insert(0, str(ROOT / "tw-superstock-lab" / "src"))
    from superstock import engine as EN
    from superstock import features as FT
    rng = np.random.default_rng(11)
    T = 700
    c = 100 * np.exp(np.cumsum(rng.normal(0.0015, 0.018, T)))
    h, l = c * (1 + np.abs(rng.normal(0, 0.008, T))), c * (1 - np.abs(rng.normal(0, 0.008, T)))
    v = rng.uniform(5e5, 2e6, T)
    m = EN.Market(pd.bdate_range("2015-01-01", periods=T), ["1234"], c[:, None], h[:, None], l[:, None], c[:, None],
                  value=(c * v)[:, None], volume=v[:, None])
    dry = FT.volume(m)["dry"]
    res = FT.vcp(m, np.ones((T, 1), dtype=bool), dry, FT.VCP_V2)
    H, L, C, V = h.tolist(), l.tolist(), c.tolist(), v.tolist()
    n_ok = n_cmp = 0
    for t in range(300, T):
        r = VC.check(H, L, C, V, t)
        if r is None or "n" not in r:
            continue
        n_cmp += 1
        assert r["n"] == res["n"][t, 0], t
        assert r["ok"] == bool(res["ok"][t, 0]), t
        if r["pivot"] is not None:
            assert abs(r["pivot"] - res["pivot"][t, 0]) < 1e-9, t
        n_ok += r["ok"]
    assert n_cmp >= 50                                             # 有基底的日子都逐日比到


class _Px:
    def __init__(self, c, v):
        self.c = self.h = self.l = c
        self.v = v


def test_tags_for_needs_eligible_and_template():
    c = _vcp_closes()
    v = [1e6] * len(c)
    for k in range(356, len(c)):
        v[k] = 4e5
    px, i = _Px(c, v), len(c) - 1
    assert WL.tags_for("1111", {"el": True, "tt_all": True, "rnha": True}, {"1111": [0]}, px, i) == ["A", "VCP", "REV"]
    assert WL.tags_for("1111", {"el": False, "tt_all": True, "rnha": True}, {"1111": [0]}, px, i) == []
    assert WL.tags_for("2222", {"el": True, "tt_all": False, "rnha": True}, {}, px, i) == []


def test_page_data_sorts_by_tag_count_then_rs():
    res = {"v": 2, "chosen": "S9", "lists": {"S9": {"ALL": {"size": 20}}}}
    watch = {"1111": ["REV"], "2222": ["A", "REV"], "3333": ["VCP"]}
    feats = {"1111": {"rs": 95}, "2222": {"rs": 70}, "3333": {"rs": 99}}
    d = WL.page_data(res, watch, feats, {"2222": "乙"})
    assert [x[0] for x in d["cand"]] == ["2222", "3333", "1111"]
    assert d["cand"][0][1] == "乙" and d["chosen"] == "S9"
    assert WL.page_data(None, watch) == {}


def test_research_file_committed_and_chosen_is_combined_list():
    res = WL.load_res()
    assert res and res["chosen"] == "S9"
    k = res["lists"]["S9"]["stock10"]
    assert k["n"] >= 100 and 0 < k["early"] <= k["hit"] <= k["n"]
    assert set(res["lists"]) >= {"S9", "S1", "S3"}


def test_watchlist_section_on_opportunity_page():
    """飆股候選與觀察名單合併成一段「飆股」（W2_plan 決定）：價格強度在前段的先列、其餘收起（W4）。"""
    from arm.lab import copage, page
    assert "function wlSec" in copage.JS and "h+=wlSec();" in page._JS
    assert "sxSec()+wlSec()" not in page._JS and "o-wl" not in copage.JS
    assert "sec('o-sx','飆股','飆股'" in copage.JS                     # 段落 id 沿用 o-sx（個股卡的連結指向它）
    assert "bit(c,'rs90')||bit(c,'mom10')" in copage.JS                   # 價格強度＝RS ≥ 90 或相對強勢前 10%
    for k in ("rs90", "mom10"):
        from arm.lab import layer as LY
        assert k in LY.CKEYS
    for g in ("書上的買點與停損", "交叉比對", "大盤 50 日線"):
        assert f"'{g}'" in copage.JS and f"gi('{g}')" in copage.JS


def test_layer_research_committed_and_no_tier():
    """W3：兩個交叉比對規格 2020–2022 都沒過關 → 頁面不分層；W4：大盤 50 日線（M2）過關。"""
    from arm.lab import layer as LY
    res = LY.load_res()
    assert res and res["use"] is None
    assert set(res["specs"]) == {"v1", "v2"} and not any(v["judge"]["pass"] for v in res["specs"].values())
    per = res["ps"]["per"]
    for k in ("IS", "VAL", "HO"):                                         # 價格強度子名單三段都比名單其餘準
        assert per[k]["t1"]["B"]["p"] > per[k]["t2"]["B"]["p"]
    assert res["mkt"]["var"] == "M2" and res["mkt"]["pass"] is True
    d = LY.page_data(res, {})
    assert d["specs"]["v1"]["pass"] is False and d["mkt"]["var"] == "M2" and d["stocks"] == {}
