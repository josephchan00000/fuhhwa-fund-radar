"""位階和之後的漲跌（arm/lab/mposfwd.py；規格 arm/lab/mposfwdspec.py VER 1）＋市場頁的圖、表與研究紀錄頁的算式（arm/lab/mpos.py）。"""
import json
import re

from arm.lab import mpos as M
from arm.lab import mposfwd as F
from arm.lab import mposfwdspec as S


def test_forward_and_episodes():
    px = [100, 110, None, 121]
    assert round(F.forward(px, 0, 1), 6) == 10.0 and F.forward(px, 1, 1) is None and F.forward(px, 3, 1) is None
    assert F.episodes([1, 2, 3, 30, 31]) == 2                      # 相隔 27 > 20 天：兩段
    assert F.episodes([1, 2, 3, 20, 21]) == 1                      # 相隔 17：併成一段
    assert F.episodes([]) == 0


def _X(n=900):
    cal = [f"20{10 + i // 250:02d}-{1 + (i // 21) % 12:02d}-{1 + i % 21:02d}" for i in range(n)]
    v = [0.5 if (i // 50) % 6 == 0 else 5.0 for i in range(n)]      # 每 300 天有 50 天極端低位（共 3 段）
    px = [100.0]
    for i in range(1, n):
        px.append(px[-1] * (1.004 if v[i - 1] == 0.5 else 1.0005))   # 極端低位的時候漲得比較快
    return {"cal": cal, "v": v}, px


def test_compute_and_verdict():
    X, px = _X()
    R = F.compute(X, px)
    a, z = R["any"][21], R["z"]["極端低位"][21]
    assert z["ep"] == 3 and z["avg"] > a["avg"] and not z["ok"] and "只有 3 段" in z["why"]
    s = dict(z, ep=6)
    ok, why = F.verdict(s, a, 21)
    assert ok and why == ""
    ok, why = F.verdict(dict(s, avg=a["avg"] + 0.5), a, 21)
    assert not ok and "只差 +0.5 個百分點" in why
    ok, why = F.verdict(dict(s, h=[[a["h"][0] - 1, a["h"][0], 3], s["h"][1]]), a, 21)
    assert not ok and "前一半方向相反" in why
    assert set(R["z"]) == set(S.ZONES) and R["split"][21] in X["cal"]


def test_fwd_table_plain_words():
    X, px = _X()
    R = F.compute(X, px)
    R["z"]["極端低位"][63] = dict(R["z"]["極端低位"][63], ok=True)
    h = M.fwd_html(R, "極端低位", "2010-01-01")
    t = re.sub("<[^>]+>", " ", re.sub(r' title="[^"]*"', "", h))
    assert t.count("任一天") >= 1 and "現在" in t and "次數 3" in t and "過去在極端低位的時候，之後 3 個月平均" in t
    for w in ("看不出", "樣本", "判定", "前後兩半", "門檻", "研究", "對照", "→", "←"):
        assert w not in t
    assert 'class="mpz-ok"' in h and 'class="mpz-dim"' in h and 'title="和任一天差不多：' in h


def _B(n=1400):
    from arm.lab import mposspec as MS
    cal = [f"20{10 + i // 250:02d}-{1 + (i // 21) % 12:02d}-{1 + i % 21:02d}" for i in range(n)]
    heat = {k: [float((i * 7 + j * 13) % 100) for i in range(n)] for j, (_, ks) in enumerate(MS.GROUPS) for k in ks}
    inc = {"tech": ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T11", "T12", "T13"], "chip": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C11"]}
    return {"cal": cal, "heat": heat, "inc": inc, "comp": {}, "px": [1000.0 + i for i in range(n)]}


def test_block_chart_toggle_and_hover_data():
    B = _B()
    X = M.compute(B)
    R = F.compute(X, B["px"])
    h = M.block(B, X, log={}, mk="tw", R=R, pxname="加權指數")
    assert h.count('class="mpz-cw"') == 2 and 'data-r="all" hidden' in h and 'class="mpz-rg"' in h
    assert "位階和指數" in h and "位階和之後的漲跌" in h and 'href="x9r.html#mpos-tw"' in h
    dat = [json.loads(x) for x in re.findall(r'<script type="application/json" class="mpz-dat">(.*?)</script>', h)]
    assert len(dat) == 2 and len(dat[0]["d"]) == len(dat[0]["p"]) == len(dat[0]["v"]) and dat[0]["d"][-1] == B["cal"][-1].replace("-", "")
    assert len(dat[1]["d"]) < len(dat[0]["d"]) * 2 and dat[1]["d"][-1] == dat[0]["d"][-1]       # 全部＝每週一點，最後一天一定在
    assert ">加權指數</text>" in h and "對照" not in re.sub("<[^>]+>", " ", h)
    assert "window.__mpzOn" in M.JS and "mpz-cl" in M.JS


def test_detail_csv_and_research(tmp_path):
    B = _B()
    X = M.compute(B)
    R = F.compute(X, B["px"])
    d = M.detail(B, X, R, "tw", "加權指數")
    assert d["x"] == X["v"][-1] and round(10 * d["below"] / d["win"], 1) == d["x"]          # 算式對得回位階
    assert d["raw"] == round(sum(g["avg"] for g in d["groups"]) / 4, 2) or abs(d["raw"] - sum(g["avg"] for g in d["groups"]) / 4) < 0.02
    csv = M.csv_text(B, X)
    lines = csv.lstrip("﻿").splitlines()
    assert lines[0].startswith('"日期","指數收盤","T1 ') and lines[0].endswith('"四組平均","位階"')
    last = lines[-1].split(",")
    assert last[0] == B["cal"][-1] and float(last[-1]) == X["v"][-1]
    assert M.publish(d, csv, tmp_path / "det.json", tmp_path) and not M.publish(d, csv, tmp_path / "det.json", tmp_path)
    assert (tmp_path / "x9mpos-tw.csv").read_text(encoding="utf-8") == csv
    doc = json.loads((tmp_path / "det.json").read_text(encoding="utf-8"))
    h = M.research_body(doc)
    assert 'id="mpos-tw"' in h and "四組平均＝（" in h and f'{d["below"]:,} ÷ {d["win"]:,} × 10' in h and 'href="x9mpos-tw.csv" download' in h
    assert "看不出差別：只有" in h or "有差別" in h
