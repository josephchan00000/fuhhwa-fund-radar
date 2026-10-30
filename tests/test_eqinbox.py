"""個股報告申請收件匣（arm/lab/eqinbox.py、scripts/eq_inbox.py、.github/workflows/eq_inbox.yml；docs/lab_eq_request_plan.md 第 3.2 節）。"""
import json
import re
from pathlib import Path

from arm.lab import eqinbox as I

ROOT = Path(__file__).resolve().parents[1]


def _root(tmp_path):
    (tmp_path / "dashboard" / "co").mkdir(parents=True)
    for c, n in (("4958", "臻鼎-KY"), ("2330", "台積電"), ("3008", "大立光")):
        (tmp_path / "dashboard" / "co" / f"{c}.json").write_text(json.dumps({"n": n}), encoding="utf-8")
    lab = tmp_path / "data" / "lab"
    lab.mkdir(parents=True)
    (lab / "ussx_fin.json").write_text(json.dumps({"s": {"PAYC": {}, "XYZ": {}}, "names": {"PAYC": "Paycom Software"}}), encoding="utf-8")
    (lab / "ussx_card.json").write_text(json.dumps({"s": {"PAYC": {}}}), encoding="utf-8")
    return tmp_path


def _iss(n, code, who="u1", assoc="NONE", at="2026-10-30T12:00:00Z", label=True):
    body = f"從網頁按…\n\n### 代號\n\n{code}\n"
    return {"number": n, "body": body, "user": {"login": who}, "author_association": assoc, "created_at": at,
            "labels": [{"name": I.LABEL}] if label else []}


def _run(issues, state, root, reports=None, fresh=()):
    reports = reports or {}
    lr = lambda mk, c: reports.get((mk, c))                                     # noqa: E731
    need = lambda mk, c, today: ((mk, c) not in fresh, "")                      # noqa: E731
    return I.reconcile(issues, state, "2026-10-31", "2026-10-31 20:00", root, lr, need)


def test_parse_only_takes_the_code_line():
    assert I.parse("### 代號\n\n4958\n") == ("tw", "4958")
    assert I.parse("### 代號\n\n４９５８ 臻鼎\n") == ("tw", "4958")                  # 全形數字、後面多寫名字
    assert I.parse("### 代號\n\npayc\n") == ("us", "PAYC")
    assert I.parse("### 代號\n\nBRK.B\n") == ("us", "BRK.B")
    for bad in (None, "", "4958", "### 代號\n\n00878\n", "### 代號\n\n$(rm -rf /)\n", "### 代號\n\n" + "A" * 6000):
        assert I.parse(bad) is None


def test_known_and_is_request(tmp_path):
    r = _root(tmp_path)
    assert I.known("tw", "4958", r) == "臻鼎-KY" and I.known("tw", "9999", r) is None
    assert I.known("us", "PAYC", r) == "Paycom Software" and I.known("us", "XYZ", r) is None      # 沒有個股卡資料做不了報告
    assert I.is_request(_iss(1, "4958")) and I.is_request(_iss(2, "4958", label=False))
    assert not I.is_request({"number": 3, "body": "隨便聊聊", "labels": []})
    assert not I.is_request(dict(_iss(4, "4958"), pull_request={}))


def test_queue_order_caps_duplicates_and_bad_requests(tmp_path):
    r = _root(tmp_path)
    issues = [_iss(1, "4958", "a", at="2026-10-30T01:00:00Z"),
              _iss(2, "4958", "b", at="2026-10-30T02:00:00Z"),                   # 同一家：一起等 #1
              _iss(3, "2330", "a", at="2026-10-30T03:00:00Z"),
              _iss(4, "3008", "a", at="2026-10-30T04:00:00Z"),                   # a 的第 3 件：超過每人 2 件
              _iss(5, "PAYC", "boss", "OWNER", at="2026-10-30T05:00:00Z"),       # 站長：排最前面
              _iss(6, "9999", "c"), _iss(7, "台積電", "c", label=False)]                  # 寫名字不寫代號＝看不懂
    st, acts = _run(issues, None, r)
    assert [(x["code"], x["issue"]) for x in st["items"]] == [("PAYC", 5), ("4958", 1), ("2330", 3)]
    assert "boss" not in json.dumps(st) and "a" not in {k for x in st["items"] for k in x.values() if isinstance(k, str)}
    closed = {a[1]: a[2] for a in acts if a[0] == "close"}
    assert closed == {2: "not_planned", 4: "not_planned", 6: "not_planned", 7: "not_planned"}
    said = {a[1]: a[2] for a in acts if a[0] == "comment"}
    assert "#1" in said[2] and "最多 2 件" in said[4] and "沒有 9999" in said[6] and "看不懂代號" in said[7]
    assert "第 1 位" in said[5] and "第 2 位" in said[1] and "第 3 位" in said[3]
    assert ("label", 7) in acts


def test_fresh_report_done_and_idempotent(tmp_path):
    r = _root(tmp_path)
    issues = [_iss(1, "4958", at="2026-10-30T01:00:00Z"), _iss(2, "2330", at="2026-10-30T02:00:00Z")]
    st, acts = _run(issues, None, r, reports={("tw", "2330"): ("2026-10-01", "2026-06-30")}, fresh={("tw", "2330")})
    assert [x["code"] for x in st["items"]] == ["4958"]
    assert ("close", 2, "completed") in acts and "先不重做" in [a for a in acts if a[:2] == ("comment", 2)][0][2]
    st2, acts2 = _run(issues[:1], st, r)                                       # 再跑一次：沒有新動作、檔案不用改
    assert acts2 == [] and I.same(st, st2)
    st3, acts3 = _run(issues[:1], st2, r, reports={("tw", "4958"): ("2026-10-31", "2026-09-30")})
    assert st3["items"] == [] and st3["done"][0]["code"] == "4958" and st3["done"][0]["made"] == "2026-10-31"
    assert ("close", 1, "completed") in acts3 and "/rp/tw-4958" in [a for a in acts3 if a[0] == "comment"][0][2]
    st4, acts4 = _run([], st, r)                                                 # 單被人關掉：離開佇列、不留言
    assert st4["items"] == [] and acts4 == []
    old = dict(st3, done=[dict(st3["done"][0], made="2026-09-01")])
    assert _run([], old, r)[0]["done"] == []                                    # 完成超過 30 天就不列


def test_workflow_and_template_never_feed_issue_text_to_a_shell():
    wf = (ROOT / ".github" / "workflows" / "eq_inbox.yml").read_text("utf-8")
    assert "github.event" not in wf and "python3 scripts/eq_inbox.py" in wf
    assert re.search(r"permissions:\s*\n\s*contents: write\s*\n\s*issues: write\s*\n", wf)
    assert "git add data/eq_requests.json" in wf and "git add -A" not in wf
    tpl = (ROOT / ".github" / "ISSUE_TEMPLATE" / "eq-report.yml").read_text("utf-8")
    assert "id: code" in tpl and "label: 代號" in tpl and I.LABEL in tpl and I.HEADING == "### 代號"
