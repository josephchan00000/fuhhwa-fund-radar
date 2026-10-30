"""個股報告每週名單（arm/lab/eqqueue.py）：買進名單先、做過又沒有新財報的不做、每週最多 4 家。"""
import json

from arm.lab import eqqueue as Q


def _report(src, mk, code, made, q):
    d = src / mk / code
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{made}.facts.json").write_text(json.dumps({"q": [{"q": q}]}), encoding="utf-8")
    (d / f"{made}.md").write_text("x", encoding="utf-8")


def test_queue_order_cap_and_skips(tmp_path, monkeypatch):
    src = tmp_path / "eq"
    _report(src, "tw", "1111", "2026-10-01", "2026-06-30")          # 做過、沒有新財報 → 不做
    _report(src, "tw", "2222", "2026-06-01", "2026-03-31")          # 做過、出了新財報 → 季更新
    monkeypatch.setattr(Q, "latest_quarter", lambda mk, c: {"1111": "2026-06-30", "2222": "2026-06-30"}.get(c, "2026-06-30"))
    cands = [{"mk": "us", "code": "AAA", "why": "美股"}, {"mk": "tw", "code": "1111", "why": "新飆股"}] + \
            [{"mk": "tw", "code": c, "why": "新飆股"} for c in ("3333", "4444", "5555", "6666")]
    r = Q.queue("2026-10-31", 4, src, cands)
    assert [c["code"] for c in r["todo"]] == ["AAA", "3333", "4444", "5555"]
    sk = {c["code"]: c["skip"] for c in r["skip"]}
    assert "還沒有新一季財報" in sk["1111"] and "排不到" in sk["6666"] and "排不到" in sk["2222"]
    assert Q.need("tw", "2222", "2026-10-31", src)[0] and "財報" in Q.need("tw", "2222", "2026-10-31", src)[1]


def test_candidates_reads_pick_rows():
    html = 'const D={"bx":{"buyd":"2026-11-02","rows":[["6870","騰雲",93,1,"w","打底中",[],0,"b"],["3008","大立光",93,3,"w","打底中",[],0,"w"]]}};'
    qm = {"now": {"buy": ["PAYC"], "next": "2026-10-26"}}
    c = Q.candidates(html, qm)
    assert [(x["mk"], x["code"]) for x in c] == [("us", "PAYC"), ("tw", "6870")]
