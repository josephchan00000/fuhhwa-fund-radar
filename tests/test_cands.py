"""新策略候選（arm/lab/candrun.py；規格 arm/lab/candspec.py；docs/lab_ia_v5_plan.md 第 24 節）。

① 規格檔（config/strategy_candidates.json）與程式：格式、sha、每一支程式有它那一型要的函式——合併通道（strategy_cands.yml）
   用 main 上的這一支測試把關，分支改不到。② 合併檢查：舊的一字不差、沒有刪、新的最多 MAX_NEW 條、還沒決定的最多 MAX_OPEN 條。
③ 指數型外掛和內建策略同一套算法（同樣的規則算出一模一樣的成績）；用到未來資料的程式會被抓到。
④ 台股個股：截面板、判定。⑤ 放進計畫試算的三條、試用紀錄只增不改。"""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from arm.lab import candrun as R
from arm.lab import candspec as CS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_gh_output(monkeypatch):
    """合併通道在同一步先跑 --merge-from（把新候選寫進 GITHUB_OUTPUT）再跑這支測試：測試裡呼叫 merge_from 不可以也寫進去，
    否則最後一行蓋掉這一輪真正的新候選（2026-10-24 第一次試跑：測試寫的 new=c003 讓回測那一步找不到、整輪不合併）。"""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


# ── ① 規格檔與程式（main 上的檢查） ──────────────────────────────────────────────────

def test_committed_spec_and_programs_are_valid():
    """寫進 main 的規格：格式、sha、編號不重複、程式都有規格；每一支程式有它那一型要的函式。"""
    doc = R.load_spec()
    assert R.check_spec(doc, R.PROG) == []
    need = {"trade": "trades", "dip": "dip_raw", "alloc": "pos", "per": "rows", "book": "signals"}
    for it in doc["items"]:
        if it.get("need") is None:
            assert callable(getattr(R.module(it["id"]), need[it["kind"]], None)), it["id"]
    dec = R.decisions()
    assert set(dec) <= {it["id"] for it in doc["items"]}                 # 決定的都是規格裡的候選
    assert len(R.open_ids(doc, dec)) <= CS.MAX_OPEN


def test_results_match_spec_when_present():
    """研究檔裡的每一筆都對得到規格（同一份規格才算數）；沒有結果的候選，頁面寫「沒算出來」。"""
    doc = R.load_spec()
    res = R.load_res()
    ids = {it["id"] for it in doc["items"]}
    assert set(res["items"]) <= ids
    for k, x in res["items"].items():
        assert x["v"] in CS.VERDICT, k


def _item(cid="c001", **kw):
    it = {"id": cid, "found": "2026-10-25", "name": "測試候選", "mk": "spx", "engine": "index", "kind": "alloc",
          "how": "收盤在 n 日均線上就拿", "src": [{"t": "某論文（2007）", "u": "https://example.org/x"}], "why": "規則清楚",
          "p": {"n": 200}, "grid": {"n": [150, 200, 250]}}
    it.update(kw)
    return it


PROG_MA = '''from .. import xstrat as XT


def pos(C, p, lag, now=False):
    return XT.pos_daily_ma(C.px, p["n"], lag)
'''


def _write(d: Path, cid: str, txt: str) -> str:
    p = d / f"{cid}.py"
    p.write_text(txt, encoding="utf-8")
    return R.sha_file(p)


def test_check_item_catches_bad_fields(tmp_path):
    sha = _write(tmp_path, "c001", PROG_MA)
    ok = _item(sha=sha)
    assert R.check_item(ok, tmp_path, "2026-10-25") == []
    bad = [
        (_item(id="x1", sha=sha), "編號"), (_item(sha=sha, engine="foo"), "引擎"), (_item(sha=sha, kind="per"), "型態"),
        (_item(sha=sha, mk="us"), "市場"), (_item(sha=sha, found="2026-13-01"), "寫定日期"),
        (_item(sha=sha, found="2026-10-26"), "未來"), (_item(sha=sha, src=[{"t": "x", "u": "http://a"}]), "來源"),
        (_item(sha=sha, how="保證賺錢"), "禁用詞"), (_item(sha="0" * 64), "sha"), (_item(sha=sha, grid={"m": [1]}), "grid"),
        (_item(sha=sha, grid={"n": [150, 250]}), "原本"), (_item(sha=sha, extra=1), "不認得"),
        (_item(sha=sha, grid={"n": list(range(190, 200)) + [200]}), "最多"),
        (_item(sha=sha, name="名" * 30), "名稱"),
    ]
    for it, word in bad:
        errs = R.check_item(it, tmp_path, "2026-10-25")
        assert errs and any(word in e for e in errs), (word, errs)


def test_need_data_item_has_no_program(tmp_path):
    it = {k: v for k, v in _item().items() if k not in ("p", "grid")}
    it["need"] = "需要資料：每天的融資餘額分點"
    assert R.check_item(it, tmp_path) == []
    _write(tmp_path, "c001", PROG_MA)
    assert any("不寫程式" in e for e in R.check_item(it, tmp_path))
    it["need"] = "缺資料"
    assert any("需要資料" in e for e in R.check_item(it, tmp_path))


def test_kind_specific_fields(tmp_path):
    sha = _write(tmp_path, "c002", "def rows(P, E, b, codes, p, F):\n    return []\n")
    tw = _item("c002", sha=sha, mk="tw", engine="tw_stock", kind="per", b="L", p={"look": 126},
               pick={"top": 0.0, "nmin": 5, "umin": 10}, grid={"look": [105, 126, 147], "pick": [[0.0, 3], [0.0, 5], [0.0, 8]]})
    assert R.check_item(tw, tmp_path) == []
    assert any("原本" in e for e in R.check_item({**tw, "grid": {"look": [105, 126], "pick": [[0.0, 3]]}}, tmp_path))
    assert any("b 要是" in e for e in R.check_item({**tw, "b": "S"}, tmp_path))
    sha3 = _write(tmp_path, "c003", "def signals(C, p):\n    return {}\n")
    us = _item("c003", sha=sha3, mk="us", engine="us_stock", kind="book", p={"rs": 80}, grid={"rs": [75, 80, 85]},
               ex={"slots": 8, "ma": 50})
    assert R.check_item(us, tmp_path) == []
    assert any("出場" in e for e in R.check_item({**us, "ex": {"slots": 8}}, tmp_path))
    assert any("stop" in e for e in R.check_item({**us, "ex": {"slots": 8, "stop": 0.1, "hold": 20}}, tmp_path))
    dip = _item("c001", sha=_write(tmp_path, "c001", PROG_MA), kind="dip")
    assert any("要有 H" in e for e in R.check_item(dip, tmp_path))
    assert any("H 要是" in e for e in R.check_item({**dip, "H": 0}, tmp_path))


def test_check_spec_duplicates_prev_and_stray_programs(tmp_path):
    sha = _write(tmp_path, "c001", PROG_MA)
    assert R.check_spec({"items": [_item(sha=sha), _item(sha=sha)]}, tmp_path)[0].startswith("編號重複")
    assert any("prev" in e for e in R.check_spec({"items": [_item(sha=sha, prev="c000")]}, tmp_path))
    _write(tmp_path, "c009", PROG_MA)
    assert any("沒有對應的規格" in e for e in R.check_spec({"items": [_item(sha=sha)]}, tmp_path))


# ── ② 合併檢查 ─────────────────────────────────────────────────────────────

def test_merge_check_frozen_no_delete_limits(tmp_path, monkeypatch):
    s1, s2 = (_write(tmp_path, c, PROG_MA) for c in ("c001", "c002"))
    old = {"items": [_item("c001", sha=s1)]}
    ok_new = {"items": [_item("c001", sha=s1), _item("c002", sha=s2)]}
    errs, fresh = R.merge_check(old, ok_new, tmp_path, {})
    assert errs == [] and fresh == ["c002"]
    changed = {"items": [_item("c001", sha=s1, how="改了"), _item("c002", sha=s2)]}
    assert any("不能改" in e for e in R.merge_check(old, changed, tmp_path, {})[0])
    gone = {"items": [_item("c002", sha=s2)]}
    (tmp_path / "c001.py").unlink()
    assert any("不能刪" in e for e in R.merge_check(old, gone, tmp_path, {})[0])
    _write(tmp_path, "c001", PROG_MA)
    s3 = _write(tmp_path, "c003", PROG_MA)
    three = {"items": [_item("c001", sha=s1), _item("c002", sha=s2), _item("c003", sha=s3)]}
    monkeypatch.setattr(CS, "MAX_NEW", 1)
    assert any("最多 1 條新的" in e for e in R.merge_check(old, three, tmp_path, {})[0])
    monkeypatch.setattr(CS, "MAX_NEW", 2)
    monkeypatch.setattr(CS, "MAX_OPEN", 2)
    assert any("還沒決定的最多" in e for e in R.merge_check(old, three, tmp_path, {})[0])
    assert R.merge_check(old, three, tmp_path, {"c001": {"dec": "reject", "d": "2026-10-27"}})[0] == []


def test_merge_from_copies_only_candidate_files(tmp_path, monkeypatch):
    """合併通道只拿規格與 cands/c###.py；__init__.py、其他檔案一律不拿。"""
    import scripts.run_cands as RC
    main = tmp_path / "main"
    (main / "config").mkdir(parents=True)
    prog = main / "arm" / "lab" / "cands"
    prog.mkdir(parents=True)
    (main / "config" / "strategy_candidates.json").write_text('{"items": []}', encoding="utf-8")
    br = tmp_path / "br"
    (br / "config").mkdir(parents=True)
    bp = br / "arm" / "lab" / "cands"
    bp.mkdir(parents=True)
    sha = _write(bp, "c001", PROG_MA)
    (bp / "__init__.py").write_text("BAD = 1\n", encoding="utf-8")
    (bp / "evil.py").write_text("x = 1\n", encoding="utf-8")
    (br / "config" / "strategy_candidates.json").write_text(json.dumps({"items": [_item(sha=sha, found="2026-10-24")]}),
                                                           encoding="utf-8")
    monkeypatch.setattr(R, "SPEC", main / "config" / "strategy_candidates.json")
    monkeypatch.setattr(R, "PROG", prog)
    monkeypatch.setattr(R, "BOARD", tmp_path / "none.json")
    assert RC.merge_from(str(br)) == 0
    assert sorted(p.name for p in prog.iterdir()) == ["c001.py"]
    assert R.load_spec(main / "config" / "strategy_candidates.json")["items"][0]["id"] == "c001"
    (bp / "c001.py").write_text(PROG_MA + "\n# 改了\n", encoding="utf-8")
    assert RC.merge_from(str(br)) == 1                                   # 程式改了、sha 對不上
    (bp / "c001.py").write_text(PROG_MA, encoding="utf-8")
    board = main / "config" / "strategy_board.json"
    board.write_text(json.dumps({"rows": [{"id": "x"}], "override": {"a": "use"}, "cand": {}}), encoding="utf-8")
    monkeypatch.setattr(R, "BOARD", board)
    (br / "config" / "strategy_board.json").write_text(json.dumps({"rows": [], "override": {}, "cand": {
        "c001": {"dec": "trial", "d": "2026-10-27"}}}), encoding="utf-8")
    assert RC.merge_from(str(br)) == 0                                   # 決定只拿 cand 那一段，其他照 main
    B = json.loads(board.read_text(encoding="utf-8"))
    assert B["cand"] == {"c001": {"dec": "trial", "d": "2026-10-27"}} and B["rows"] == [{"id": "x"}] and B["override"] == {"a": "use"}
    (br / "config" / "strategy_board.json").write_text(json.dumps({"cand": {"c009": {"dec": "trial", "d": "2026-10-27"}}}),
                                                     encoding="utf-8")
    assert RC.merge_from(str(br)) == 1                                   # 決定的編號不在規格裡


def test_merge_from_stale_branch_keeps_newer_main(tmp_path, monkeypatch):
    """分支比 main 舊（少了 main 上較新的候選、決定是舊的）：main 上的候選照留、不算刪掉；決定逐條併、日期新的贏。"""
    import scripts.run_cands as RC
    main = tmp_path / "main"
    (main / "config").mkdir(parents=True)
    prog = main / "arm" / "lab" / "cands"
    prog.mkdir(parents=True)
    s1, s2 = _write(prog, "c001", PROG_MA), _write(prog, "c002", PROG_MA)
    spec = main / "config" / "strategy_candidates.json"
    spec.write_text(json.dumps({"as_of": "2026-11-01", "items": [_item("c001", sha=s1, found="2026-10-24"),
                                                                  _item("c002", sha=s2, found="2026-10-24")]}), encoding="utf-8")
    board = main / "config" / "strategy_board.json"
    board.write_text(json.dumps({"rows": [], "cand": {"c002": {"dec": "adopt", "d": "2026-11-01"}}}), encoding="utf-8")
    br = tmp_path / "br"
    (br / "config").mkdir(parents=True)
    bp = br / "arm" / "lab" / "cands"
    bp.mkdir(parents=True)
    _write(bp, "c001", PROG_MA)
    s3 = _write(bp, "c003", PROG_MA)
    (br / "config" / "strategy_candidates.json").write_text(json.dumps({"as_of": "2026-10-24", "items": [
        _item("c001", sha=s1, found="2026-10-24"), _item("c003", sha=s3, found="2026-10-24")]}), encoding="utf-8")
    (br / "config" / "strategy_board.json").write_text(json.dumps({"cand": {
        "c002": {"dec": "trial", "d": "2026-10-27"}, "c001": {"dec": "reject", "d": "2026-10-28", "why": "x"}}}), encoding="utf-8")
    monkeypatch.setattr(R, "SPEC", spec)
    monkeypatch.setattr(R, "PROG", prog)
    monkeypatch.setattr(R, "BOARD", board)
    assert RC.merge_from(str(br)) == 0
    doc = R.load_spec(spec)
    assert [it["id"] for it in doc["items"]] == ["c001", "c002", "c003"] and doc["as_of"] == "2026-11-01"
    assert json.loads(board.read_text(encoding="utf-8"))["cand"] == {
        "c002": {"dec": "adopt", "d": "2026-11-01"}, "c001": {"dec": "reject", "d": "2026-10-28", "why": "x"}}
    assert R.merge_decisions({"c1": {"dec": "trial", "d": "2026-10-27"}}, {"c1": {"dec": "reject", "d": "2026-10-27"}})["c1"]["dec"] == "reject"
    assert R.merge_decisions({"c1": {"dec": "reject", "d": "2026-10-27"}}, {"c1": {"dec": "trial", "d": "2026-10-27"}})["c1"]["dec"] == "reject"


# ── ③ 指數型 ───────────────────────────────────────────────────────────────

def _fake_D(T=2600, seed=3, mk="spx"):
    rng = np.random.default_rng(seed)
    px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, T)))
    import datetime as dt
    d0 = dt.date(1989, 1, 2)
    cal, d = [], d0
    while len(cal) < T:
        if d.weekday() < 5:
            cal.append(d.isoformat())
        d += dt.timedelta(days=1)
    return {"mk": mk, "cal": cal, "px": px, "vix": np.full(T, 20.0), "vixa": np.full(T, 20.0)}


@pytest.fixture
def cand_pkg(tmp_path, monkeypatch):
    """暫時的候選程式（寫進 arm/lab/cands/，測完刪掉）。"""
    made = []

    def put(cid: str, txt: str):
        p = R.PROG / f"{cid}.py"
        p.write_text(txt, encoding="utf-8")
        made.append(p)
        import importlib
        import sys
        sys.modules.pop(f"arm.lab.cands.{cid}", None)
        importlib.invalidate_caches()
        return R.sha_file(p)
    yield put
    import sys
    for p in made:
        p.unlink(missing_ok=True)
        sys.modules.pop(f"arm.lab.cands.{p.stem}", None)


def test_index_plugin_matches_builtin_strategy(cand_pkg):
    """外掛照 200 日均線寫：成績、判定、參數鄰近、每一段、現在都和內建的 ma200 一模一樣。"""
    from arm.lab import xstrat as XT
    from arm.lab import xstratspec as XS
    cand_pkg("c998", PROG_MA)
    D = _fake_D()
    it = _item("c998", p={"n": 200}, grid={"n": [150, 200, 250]})
    out = R.run_index(it, D)
    ref = XT.strategy(XT.Ctx(D), XS.BY_KEY["ma200"])
    r = out["r"]
    assert out["peek"] == []
    for k in ("tier", "full", "rec", "grid_ok", "tr"):
        assert r[k] == ref[k], k
    assert [g["ok"] for g in r["grid"]] == [g["ok"] for g in ref["grid"]]
    assert r["now"]["st"] == ref["now"]["st"]


def test_index_peek_catches_tomorrow(cand_pkg):
    cand_pkg("c997", '''import numpy as np


def pos(C, p, lag, now=False):
    out = np.zeros(C.T)
    out[:-1] = (C.px[1:] > C.px[:-1]).astype(float)
    return out
''')
    D = _fake_D()
    out = R.run_index(_item("c997", p={"n": 1}, grid={"n": [1]}), D)
    assert out["peek"] and "部位不一樣" in out["peek"][0]


def test_index_peek_catches_monthly_one_day_ahead(cand_pkg):
    """每個月底決定、但偷看下一天收盤（截資料抓不到時，打亂之後的價格要抓得到）。"""
    cand_pkg("c992", '''import numpy as np
from .. import xstrat as XT


def pos(C, p, lag, now=False):
    px = C.px
    dec = []
    for m in C.ends:
        nx = px[m + 1] if m + 1 < C.T else px[m]
        dec.append(1.0 if nx > px[m] else 0.0)
    return XT._pos_monthly(C.T, C.ends, dec, lag)
''')
    D = _fake_D()
    out = R.run_index(_item("c992", p={"n": 1}, grid={"n": [1]}), D)
    assert any("換掉" in m for m in out["peek"]), out["peek"]


def test_index_trade_and_dip_plugins_peek_clean(cand_pkg):
    cand_pkg("c996", '''from .. import xstrat as XT


def trades(C, p, lag, now=False):
    setup = (C.px > C.ma(p["ma"])) & (C.rsi2 < p["lo"])
    return XT.sig_trades(setup, C.px > C.ma(5), C.s0, lag)
''')
    D = _fake_D()
    out = R.run_index(_item("c996", kind="trade", p={"ma": 200, "lo": 10}, grid={"lo": [5, 10]}), D)
    assert out["peek"] == [] and out["r"]["full"]["n"] > 0
    cand_pkg("c995", '''def dip_raw(C, p, now=False):
    import numpy as np
    r = np.zeros(C.T)
    r[5:] = C.px[5:] / C.px[:-5] - 1
    return [t for t in range(C.T) if r[t] <= -p["drop"]], 5
''')
    out = R.run_index(_item("c995", kind="dip", H=20, p={"drop": 0.04}, grid={"drop": [0.03, 0.04, 0.05]}), D)
    assert out["peek"] == [] and out["r"]["full"]["n"] > 0


def test_index_daily_matches_manual(cand_pkg, monkeypatch):
    """每天的報酬：前一天有部位拿含息指數、沒有拿現金，換邊那天付 ETF 成本。"""
    from arm.lab import tilt as TL
    from arm.lab import xstrat as XT
    from arm.lab import xstratspec as XS
    D = _fake_D(600)
    C = XT.Ctx(D)
    held = np.array([1.0 if (k // 37) % 2 else 0.0 for k in range(C.T)])
    tot = np.full(C.T, 0.001)
    monkeypatch.setattr(TL, "carry_inputs", lambda mk, cal, px: {"tot": tot, "rate": np.full(len(cal), 0.0365),
                                                                  "days": np.ones(len(cal))})
    out = R.index_daily("spx", C, held)
    c = XS.COST["spx"]
    for k in range(max(C.s0, 1), C.T):
        g = held[k - 1] * 0.001 + (1 - held[k - 1]) * 0.0001
        if held[k] != held[k - 1]:
            g = (1 + g) * (1 - c) - 1
        assert out[C.cal[k]] == pytest.approx(g)


# ── ④ 台股個股 ─────────────────────────────────────────────────────────────

def _tw_panel(T=400, n=24, seed=5):
    import random
    rnd = random.Random(seed)

    class _P:
        pass
    P = _P()
    import datetime as dt
    cal, d = [], dt.date(2015, 1, 1)
    while len(cal) < T:
        if d.weekday() < 5:
            cal.append(d.isoformat())
        d += dt.timedelta(days=1)
    P.cal, P.T, P.ix = cal, T, {x: i for i, x in enumerate(cal)}
    P.s, P.cap, P.liq = {}, {}, {}
    for k in range(n):
        c = f"{1101 + k}"
        x, o, cl = 50.0, [], []
        mu = (k - n / 2) * 0.0004
        for _ in range(T):
            op = x * (1 + rnd.gauss(0, 0.004))
            x = op * (1 + mu + rnd.gauss(0, 0.015))
            o.append(round(op, 2))
            cl.append(round(x, 2))
        P.s[c] = {"o": o, "c": cl, "h": [y * 1.01 for y in cl], "l": [y * 0.99 for y in cl], "v": [1.0] * T}
        P.cap[c] = [500e8] * T
        P.liq[c] = [5e8] * T
    P.codes = sorted(P.s)
    P.idx = [100.0] * T
    P.idx_o = [100.0] * T
    P.tr = [100.0 * (1.0003 ** i) for i in range(T)]
    P._el, P._win = {}, {}
    P.lock_n = 0

    def close_on_or_before(c, x, lo):
        for i in range(x, lo - 1, -1):
            if P.s[c]["c"][i]:
                return P.s[c]["c"][i]
        return None
    P.close_on_or_before = close_on_or_before
    return P


TW_MOM = '''from .. import bt3s
from .. import packtest as PT


def rows(P, E, b, codes, p, F):
    forms = [t for t in PT._month_ends(P.cal) if t >= p["look"]]
    return bt3s.rows_at(P, E, b, codes, forms, PT._mom(P, p["look"], 5))
'''


def test_tw_stock_eval_peek_and_tier(cand_pkg):
    cand_pkg("c994", TW_MOM)
    P = _tw_panel()
    it = _item("c994", mk="tw", engine="tw_stock", kind="per", b="L", p={"look": 60},
               pick={"top": 0.0, "nmin": 4, "umin": 8}, grid={"look": [40, 60, 80], "pick": [[0.0, 3], [0.0, 4], [0.0, 6]]})
    out = R.run_tw(it, P, F=object())
    assert out["peek"] == []
    assert out["n"] == len(out["per"]) and len(out["grid"]) == 9
    from arm.lab import bt3
    U = [{"r": x[1], "hd": x[4]} for x in out["per"]]
    assert out["full"]["ok"] == bt3.payoff(U)["ok"]
    want = "few" if out["n"] < CS.TW_N_MIN else ("good" if out["full"]["ok"] and out["later"]["ok"] and out["grid_ok"] >= CS.GRID_OK
                                               else "ref" if out["full"]["ok"] else "none")
    assert out["tier"] == want
    assert set(out["daily"]) <= set(out["acct"]) and out["acct"]


def test_tw_stock_peek_catches_future_price(cand_pkg):
    cand_pkg("c993", '''from .. import bt3s
from .. import packtest as PT


def rows(P, E, b, codes, p, F):
    forms = [t for t in PT._month_ends(P.cal) if t >= 20]
    def sc(c, t):
        x = P.s[c]["c"]
        return x[min(t + 5, len(x) - 1)] / x[t] - 1
    return bt3s.rows_at(P, E, b, codes, forms, sc)
''')
    P = _tw_panel()
    it = _item("c993", mk="tw", engine="tw_stock", kind="per", b="L", p={"look": 20},
               pick={"top": 0.0, "nmin": 4}, grid={"look": [20], "pick": [[0.0, 4]]})
    out = R.run_tw(it, P, F=object())
    assert out["peek"] and "分數不一樣" in out["peek"][0]


def test_cut_panel_slices_everything():
    P = _tw_panel(120)
    Q = R.cut_panel(P, 50)
    assert Q.T == 50 and len(Q.cal) == 50 and all(len(v["c"]) == 50 for v in Q.s.values())
    assert all(len(v) == 50 for v in Q.cap.values()) and len(Q.tr) == 50 and P.T == 120


# ── ⑤ 放進計畫試算、試用紀錄 ─────────────────────────────────────────────────────

def test_plan_judge_three_conditions():
    def sc(m, mdd, h):
        return {"plan": {"m": m, "mdd": mdd}, "halves": [{"plan": {"m": x}} for x in h]}
    cur = sc(10.0, 0.30, (3.0, 3.0))
    assert R.plan_judge(sc(11.0, 0.39, (3.0, 3.1)), cur)["pass"]
    assert not R.plan_judge(sc(9.9, 0.30, (3.0, 3.1)), cur)["money"]
    assert not R.plan_judge(sc(11.0, 0.30, (2.9, 3.5)), cur)["halves"]
    assert not R.plan_judge(sc(11.0, 0.41, (3.0, 3.1)), cur)["mdd"]


def test_star_n_reads_sig_stock(tmp_path):
    p = tmp_path / "s.json"
    rows = [{"id": "stk:strat:v3l", "tier": "good", "desc": "季換股"}, {"id": "stk:strat:s3", "tier": "good", "desc": "事件型"},
            {"id": "stk:strat:s1", "tier": "ref", "desc": "短線"},
            {"id": "stk:strat:b3l", "tier": "good", "desc": "回測方法 v3 研究版本（同一批股票全部買）"}]
    p.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    assert R.star_n(p) == 2
    assert R.star_n(tmp_path / "none.json") == CS.STAR_N_DEFAULT


def test_live_record_is_append_only():
    rec: dict = {}
    assert R.append_live(rec, {"2026-10-27": 0.01, "2026-10-28": -0.02, "2026-10-26": 0.5}, {"2026-10-27": 0.0}, "2026-10-27") == 2
    assert rec["start"] == "2026-10-27" and "2026-10-26" not in rec["r"]
    assert R.append_live(rec, {"2026-10-27": 9.9, "2026-10-28": 9.9, "2026-10-29": 0.03}, {}, "2026-11-01") == 1
    assert rec["r"] == {"2026-10-27": 0.01, "2026-10-28": -0.02, "2026-10-29": 0.03} and rec["start"] == "2026-10-27"
    st = R.live_stats(rec)
    assert st["n"] == 3 and st["ret"] == pytest.approx(1.01 * 0.98 * 1.03 - 1) and not st["ok"]


def test_fresh_needs_same_spec_and_version():
    it = _item(sha="a" * 64)
    R0 = {"items": {"c001": {"dig": R.digest(it), "spec": CS.VER, "v": "good"}}}
    assert R.fresh(R0, it)
    assert not R.fresh(R0, {**it, "how": "改了"})
    assert not R.fresh({"items": {"c001": {"dig": R.digest(it), "spec": CS.VER, "v": "err"}}}, it)
    assert not R.fresh({"items": {"c001": {"dig": R.digest(it), "spec": CS.VER - 1, "v": "good"}}}, it)


def test_workflow_uses_main_checks_and_only_candidate_paths():
    wf = (ROOT / ".github" / "workflows" / "strategy_cands.yml").read_text(encoding="utf-8")
    assert "config/strategy_candidates.json" in wf and "arm/lab/cands/**" in wf
    assert "ref: main" in wf and "--merge-from" in wf and "tests/test_cands.py" in wf
    assert "env -u GITHUB_OUTPUT python3 -m pytest" in wf                     # 測試不可以改到這一輪的輸出
    assert "claude/ussx-data" in wf and "sparse-checkout" in wf               # 美股候選才拿資料分支（只拿美股資料）
    assert ("git add -f config/strategy_candidates.json config/strategy_board.json data/lab/cands_research.json "
            "data/lab/cands_live.json") in wf
    assert "git add -- 'arm/lab/cands/c[0-9][0-9][0-9].py'" in wf                # 只拿程式，不要 __pycache__
    assert "add -f config/strategy_candidates.json arm/lab/cands" not in wf and 'PYTHONDONTWRITEBYTECODE: "1"' in wf
    assert "config/strategy_board.json" in wf.split("paths:")[1].split("\n")[0]     # 使用者的決定也走這個通道
    assert "daily.yml" in wf                                                  # 有新結果才重建頁面
    assert "0 11 * * 0" in wf                                                 # 每週日台北 19:00（試用紀錄、補算）
