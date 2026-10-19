"""已下市公司的產業別（arm/lab/indhist.py；bubindspec VER 2 第 1b 節）。"""
from arm.lab import bubind, indhist
from arm.lab import store


def test_parse_twse_and_tpex_codes():
    tw = {"stat": "OK", "tables": [{"data": [["半導體類指數", "100"]]},
                                   {"data": [["2330", "台積電"], ["2311", "日月光"], ["0050", "x"], ["2330", "重複"]]}]}
    assert indhist.codes_twse(tw) == ["2311", "2330"]
    tp = {"tables": [{"data": [["3582", "凌耀"], ["小計", ""], ["5326", "x"]]}]}
    assert indhist.codes_tpex(tp) == ["3582", "5326"]
    assert indhist.codes_tpex({"aaData": [["6286", "立錡"]]}) == ["6286"]
    assert indhist.codes_twse(None) == [] and indhist.codes_tpex({}) == []


def test_calendar_helpers():
    cal = ["2012-12-28", "2013-01-02", "2013-01-03", "2013-12-31", "2014-01-02", "2014-02-27", "2014-03-03"]
    assert indhist.year_firsts(cal) == ["2013-01-02", "2014-01-02"]
    assert indhist.month_before_last(cal, "2014-03-03") == "2014-02-27"
    assert indhist.month_before_last(cal, "2012-12-28") is None


def test_delisted_map_uses_last_snapshot_and_keeps_current(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write_json("indsnap.json", {
        "twse": {"2014-01-02": {"24": ["2311", "2330"], "26": ["2448"]},
                 "2018-01-02": {"24": ["2311"], "26": []}},
        "tpex": {"2014-01-02": {"28": ["3144"], "99": ["9999"]}}})
    m = indhist.delisted_map({"2330": "半導體業"})
    assert m == {"2311": "半導體業", "2448": "光電業", "3144": "電子零組件業"}      # 未知代碼 99 不收；現在的公司不覆蓋
    assert indhist.seen_codes() == {"2311", "2330", "2448", "3144", "9999"}


def test_last_appearance_wins(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "LAB", tmp_path)
    store.write_json("indsnap.json", {"twse": {"2013-01-02": {"13": ["1234"]}, "2016-01-04": {"28": ["1234"]}},
                                      "tpex": {"2015-01-05": {"24": ["1234"]}}})
    assert indhist.delisted_map({}) == {"1234": "電子零組件業"}


def test_tw_ind_map_current_first(monkeypatch):
    from arm import stockmeta
    monkeypatch.setattr(stockmeta, "industry_map", lambda: {"2330": "半導體業", "2448": "其他電子業"})
    monkeypatch.setattr(indhist, "delisted_map", lambda cur: {"2311": "半導體業", "2448": "光電業"})
    assert bubind.tw_ind_map() == {"2330": "半導體業", "2311": "半導體業", "2448": "其他電子業"}
