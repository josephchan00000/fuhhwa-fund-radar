"""個股報告官方文件包（arm/lab/eqdocs.py、scripts/fetch_eqdocs.py、scripts/eq_docs_req.py、.github/workflows/eq_docs.yml；
docs/lab_eq_docs_plan.md）。觀測站的格式用存下來的樣本（tests/fixtures/eqdocs/）＋手寫的最小表格測。"""
import re
import subprocess
from datetime import date
from pathlib import Path

from arm.lab import eqdocs as E

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "eqdocs"


def _fx(name: str) -> str:
    return E._dec((FIX / name).read_bytes())


def _pdf(pages: list[list[str]]) -> bytes:
    """最小的 PDF（Helvetica、每行一個 Tj），測抽字與拿掉範本字。"""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        body = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({ln}) Tj 0 -16 Td" for ln in lines) + " ET"
        objs.append(f"<< /Length {len(body)} >>\nstream\n{body}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    return out + f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()


CONF = ("<table><tr><td>6870</td><td>騰雲</td><td>115/09/17</td><td>14:30</td><td>國票金控大樓七樓會議廳</td>"
        "<td>本公司受邀參加國票綜合證券舉辦之法人說明會</td><td><a href='/nas/STR/687020260917M001.pdf'>687020260917M001.pdf</a></td>"
        "<td>687020260917E001.pdf</td><td>無</td><td>影音資訊網址： http://irconference.twse.com.tw/6870_16_20260917_ch.mp4</td><td>無</td></tr>"
        "<tr><td>6870</td><td>騰雲</td><td>114/03/24</td><td>14:00</td><td>線上</td><td>受邀</td><td>687020250324M001.pdf</td>"
        "<td></td><td>無</td><td>無</td><td>無</td></tr></table>")
NEWS = ("<table><tr><td>6870</td><td>騰雲</td><td>115/10/28</td><td>17:30:12</td><td>公告本公司董事會決議發放現金股利</td>"
        "<td><input type=button value='詳細資料' onclick='document.t05st01_fm.seq_no.value=\"1\";document.t05st01_fm.spoke_time.value=\"173012\";"
        "document.t05st01_fm.spoke_date.value=\"20261028\";document.t05st01_fm.co_id.value=\"6870\";document.t05st01_fm.TYPEK.value=\"otc\";"
        "openWindow(this.form,\"\");'></td></tr>"
        "<tr><td>6870</td><td>騰雲</td><td>115/08/05</td><td>19:04:41</td><td>公告取得新設合資公司股權</td><td></td></tr></table>")
DETAIL = "<table><tr><td>主旨</td><td>公告本公司董事會決議發放現金股利</td></tr><tr><td>說明</td><td>1.董事會決議日期:115/10/28<br>2.每股 2 元</td></tr></table>"
BASIC = ("<table><tr><td class='compName'>本資料由 (上櫃公司) 6870 騰雲 公司提供</td></tr></table><table>"
         "<tr><th>產業類別</th><td>數位雲端</td><th>公司名稱</th><td>騰雲科技服務股份有限公司</td></tr>"
         "<tr><th>董事長</th><td>梁基文</td><th>總經理</th><td>梁基文</td></tr>"
         "<tr><th>主要經營業務</th><td>智慧商務建置及佈署 雲端數據平台及維運服務</td></tr>"
         "<tr><th>上櫃日期</th><td>112/09/14</td><th>公司網址</th><td><a href='https://www.turn2cloud.com'>https://www.turn2cloud.com</a></td></tr></table>")
ANNUAL = ("<tr><td>6870</td><td><a href='javascript:readfile2(\"F\",\"6870\",\"2025_6870_20260606F04.pdf\");'>2025_6870_20260606F04.pdf</a></td></tr>"
          "<tr><td><a href='javascript:readfile2(\"F\",\"6870\",\"2025_6870_20260606F01.pdf\");'>開會通知</a></td></tr>")


def test_parsers_on_minimal_tables():
    cs = E.parse_confs(CONF, "6870")
    assert [c["d"] for c in cs] == ["2025-03-24", "2026-09-17"]
    assert cs[1]["pdf"] == "https://mopsov.twse.com.tw/nas/STR/687020260917M001.pdf" and cs[1]["pdf_en"].endswith("E001.pdf")
    assert cs[1]["video"].startswith("http://irconference.twse.com.tw/") and cs[1]["note"].startswith("本公司受邀")
    ns = E.parse_news_list(NEWS, "6870")
    assert [(n["d"], n["subj"]) for n in ns] == [("2026-10-28", "公告本公司董事會決議發放現金股利"), ("2026-08-05", "公告取得新設合資公司股權")]
    assert ns[0]["form"] == {"seq_no": "1", "spoke_time": "173012", "spoke_date": "20261028", "co_id": "6870", "TYPEK": "otc"}
    assert ns[1]["form"] == {} and E.parse_news_detail(DETAIL) == "1.董事會決議日期:115/10/28\n2.每股 2 元"
    b = E.parse_basic(BASIC)
    assert b["biz"].startswith("智慧商務") and b["site"] == "https://www.turn2cloud.com" and b["otc"] == "2023-09-14"
    assert b["board"] == "上櫃" and b["chair"] == "梁基文" and b["ind"] == "數位雲端"
    assert E.parse_annual_list(ANNUAL) == ["2025_6870_20260606F04.pdf"]
    assert E.parse_step9("<a href='/pdf/2025_6870_20260606F04_20261030_232834.pdf'>") == \
        "https://doc.twse.com.tw/pdf/2025_6870_20260606F04_20261030_232834.pdf"
    assert E.roc_date("115/09/17") == E.roc_date("1150917") == "2026-09-17" and E.roc_date("abc") is None


def test_real_mops_samples():
    """CI 2026-10-30 抓回來的觀測站回應（剪短；電話、email、地址、承辦人換成（略））。"""
    b = E.parse_basic(_fx("basic-7730.html"))
    assert (b["full"], b["board"], b["listed"], b["emg"]) == ("暉盛科技股份有限公司", "上市", "2025-11-04", "2024-03-18")
    assert b["site"] == "http://www.nemstek.com.tw" and b["biz"].startswith("各式電漿設備之研發") and "otc" not in b   # 網址沒寫 http
    [c] = E.parse_confs(_fx("conf-5475.html"), "5475")
    assert (c["d"], c["t"], c["note"]) == ("2025-12-03", "15:30", "辦理114年度Q3法說會") and "\n" not in c["where"]
    assert c["pdf"].endswith("/nas/STR/547520251203M001.pdf") and c["pdf_en"].endswith("/547520251203E001.pdf")
    assert c["video"] == "https://vimeo.com/1142964560"                                      # 影音放在公司自己找的網站
    cs = E.parse_confs(_fx("conf-6870.html"), "6870")
    assert [x["d"] for x in cs] == ["2025-09-18", "2025-12-24"] and cs[1]["video"].startswith("http://irconference.twse.com.tw/")
    ns = E.parse_news_list(_fx("news-6870.html"), "6870")
    assert [n["d"] for n in ns] == ["2026-01-05", "2026-01-29", "2026-03-03"]
    assert ns[2]["subj"] == "公告本公司114年第4季合併財務報告董事會預計召開日期為115年3月11日"           # 原文主旨中間斷行
    assert ns[0]["form"] == {"seq_no": "1", "spoke_time": "190441", "spoke_date": "20260105", "co_id": "6870", "TYPEK": "otc"}
    assert E.parse_news_detail(_fx("detail-6870.html")).startswith("1.主管機關核准減資日期:NA\n2.辦理資本變更登記完成日期:115/10/28")
    assert E.parse_annual_list(_fx("annual-6870.html")) == ["2025_6870_20260528F04.pdf"]          # Big5 頁；只取 F04 年報
    assert E.parse_step9(_fx("step9-6870.html")) == "https://doc.twse.com.tw/pdf/2025_6870_20260528F04_20261030_235250.pdf"


def test_annual_stops_before_employee_section_and_subject_lines_join():
    book = ["封面", "目錄", "x", "致股東", "肆、營運概況 一、業務內容 (一)業務範圍", "二、市場及產銷概況 主要客戶",
            "銷貨淨額 100.00 三、最近二年度從業員工人數 員工 120 人 四、環保支出資訊", "五、勞資關係", "六、資通安全管理", "伍、財務概況"]
    assert E.annual_section(book) == [(5, "肆、營運概況 一、業務內容 (一)業務範圍"), (6, "二、市場及產銷概況 主要客戶"),
                                      (7, "銷貨淨額 100.00")]                               # 員工、環保、勞資、資安不收
    assert E.one_line("公告本公司董事會 \n預計召開日期") == "公告本公司董事會預計召開日期"
    assert E.one_line("SEMICON Taiwan Co \nDay") == "SEMICON Taiwan Co Day"


def test_pdf_text_drops_template_and_finds_annual_chapter():
    pages = [["Header Brand", "Contents"], ["Header Brand", "Revenue up 20 pct"], ["Header Brand", "Capacity 2 lines"],
             ["Header Brand", "Outlook"], ["Header Brand"]]
    t = E.pdf_pages(_pdf(pages))
    assert t == ["Contents", "Revenue up 20 pct", "Capacity 2 lines", "Outlook", ""]       # 每頁都有的範本字拿掉；只有範本的頁＝空
    book = ["封面", "目錄 壹、致股東報告書 貳、公司簡介 參、公司治理報告 肆、營運概況 一、業務內容 伍、財務概況", "致股東", "治理",
            "肆、營運概況 一、業務內容 (一)業務範圍 營業比重 機台 90.13%", "二、市場及產銷概況 市占", "伍、財務概況 一、簡明資產負債表", "附錄"]
    assert [p for p, _ in E.annual_section(book)] == [5, 6]                                # 目錄頁跳過；到「財務概況」前一頁
    assert [p for p, _ in E.annual_section(["a", "b", "c", "d", "主要產品 營業比重 表", "e"])] == [4, 5, 6]   # 沒有章名：營業比重那頁前後


def _fake(pdfs: dict, fail: set = frozenset()):
    calls = []

    def post(ep, form):
        calls.append((ep, form.get("step"), form.get("seq_no")))
        if ep in fail:
            raise RuntimeError("觀測站 500")
        return {"t05st03": BASIC, "t100sb02_1": CONF, "t05st01": DETAIL if form.get("step") == 2 or form.get("seq_no") else NEWS}[ep]

    def get(url):
        if "step=1" in url:
            return ANNUAL.encode()
        if "step=9" in url:
            return b"<a href='/pdf/2025_6870_20260606F04_x.pdf'>"
        return pdfs[url.rsplit("/", 1)[-1]]
    return post, get, calls


def test_build_pack_index_and_markdown():
    deck = _pdf([["T", "page one about TSpace platform and smart retail"], ["T", "page two revenue mix by product line"],
                 ["T", "page three outlook capex and capacity plan"], ["T"]])
    book = _pdf([["cover"], ["toc"], ["x"], ["y"], ["Ying Yun Gai Kuang"], ["z"]])
    post, get, calls = _fake({"687020260917M001.pdf": deck, "2025_6870_20260606F04_x.pdf": book})
    import arm.lab.eqdocs as M
    orig = M.annual_section
    M.annual_section = lambda pages: [(5, pages[4])]                                      # 英文假 PDF 沒有中文章名
    try:
        pk = E.build("6870", date(2026, 10, 31), post, get, log=lambda *_: None, pause=0)
    finally:
        M.annual_section = orig
    assert pk["ok"] and pk["st"] == {"basic": "ok", "confs": "ok", "deck": "ok", "news": "ok", "annual": "ok"}
    assert pk["deck"]["d"] == "2026-09-17" and pk["deck"]["pages"][0] == "page one about TSpace platform and smart retail" and pk["deck"]["img"] == [4]
    assert [n["subj"] for n in pk["news"]][0].startswith("公告本公司董事會") and pk["news"][0]["body"].startswith("1.董事會")
    assert pk["news"][1]["body"] == ""                                                    # 沒有按鈕的不查內文
    assert pk["annual"]["fy"] == 2025 and pk["annual"]["pages"] == [(5, "Ying Yun Gai Kuang")]
    assert ("t05st01", 2, "1") in calls                                                   # 內文用按鈕帶的欄位、第二步
    ix = E.index(pk)
    assert ix["name"] == "騰雲科技服務股份有限公司"
    assert ix["deck"] == {"d": "2026-09-17", "url": "https://mopsov.twse.com.tw/nas/STR/687020260917M001.pdf", "n": 4}
    assert "body" not in str(ix) and "page one" not in str(ix) and ix["site"] == "https://www.turn2cloud.com"     # 清單不含全文
    md = E.render_md(pk)
    for s in ("## 最近一次法說會簡報（2026-09-17", "### 第 4 頁（這一頁是圖，沒有文字）", "## 重大訊息（近 6 個月", "營運概況"):
        assert s in md, s


def test_build_records_failures_and_old_conference():
    post, get, _ = _fake({}, fail={"t05st01"})
    pk = E.build("6870", date(2027, 12, 1), post, get, log=lambda *_: None, pause=0)       # 最近一場法說會超過 12 個月
    assert not pk["ok"] and pk["st"]["news"].startswith("err") and pk["st"]["deck"] == "none" and pk["deck"] is None


def test_request_formats_and_safe_extraction():
    assert E.CODE_RE.fullmatch("tw:6870") and not E.CODE_RE.fullmatch("tw:6870;rm") and not E.CODE_RE.fullmatch("us:PAYC")
    assert E.ID_RE.fullmatch("20261030-2350-6a9f01") and not E.ID_RE.fullmatch("20261030-2350-../x")
    import importlib.util
    spec = importlib.util.spec_from_file_location("eq_docs_req", ROOT / "scripts" / "eq_docs_req.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    for ok in ("index.json", "id.txt", "tw-6870.md", "tw-6870.json", "raw/001-t05st03-6870-1.html"):
        assert R.KEEP.fullmatch(ok), ok
    for bad in ("../x.md", "tw-6870.py", "raw/../../a.html", ".git/config", "eqdocs/tw-6870.md"):
        assert not R.KEEP.fullmatch(bad), bad
    r = subprocess.run(["git", "check-ignore", "-q", ".eqdocs/20261030-2350-6a9f01/tw-6870.md"], cwd=ROOT)
    assert r.returncode == 0                                                              # 全文不進 git（使用者選「不存」）


def test_workflow_never_feeds_request_text_to_a_shell():
    wf = (ROOT / ".github" / "workflows" / "eq_docs.yml").read_text("utf-8")
    assert "github.event." not in wf and "${{ inputs.codes }}" in wf and 'CODES: ${{ inputs.codes }}' in wf
    assert "paths: ['.ping/eqdocs']" in wf and "branches: ['claude/**']" in wf
    assert re.search(r"permissions:\s*\n\s*contents: write\s*\n\s*\n", wf)
    assert "grep -Eq '^[0-9]{8}-[0-9]{4}-[0-9a-f]{6}$'" in wf and "refs/heads/claude/eqdocs-tmp/$ID" in wf
    assert "git add -f eqdocs" in wf and "GIT_INDEX_FILE" in wf and "git add -A" not in wf
    assert "cron: '23 19 * * *'" in wf and wf.count("if: github.event_name != 'schedule'") == 5   # 每天只清臨時分支
    assert 'CUT=$(date +%Y%m%d)' in wf and "TZ: Asia/Taipei" in wf                               # 請求日期在今天以前的就刪


def test_fetch_log_marks_consecutive_failures_and_retry_decision():
    """D2（使用者 2026-10-30）：抓不到當天不寫、隔天重試，連兩天（不同天的連續兩次）抓不到才照寫。"""
    ok = {"ok": True, "st": {"deck": "ok"}}
    bad = {"ok": False, "st": {"deck": "ok", "news": "err: 觀測站 500"}}
    log: dict = {}
    E.log_update(log, {"at": "2026-10-29 20:50", "codes": {"tw:6870": dict(ok), "tw:7730": dict(bad)}})
    idx = {"at": "2026-10-30 20:50", "codes": {"tw:6870": dict(bad), "tw:7730": dict(bad)}}
    E.log_update(log, idx)
    assert idx["codes"]["tw:6870"]["fails"] == ["2026-10-30"] and E.d2(idx["codes"]["tw:6870"]) == "retry"
    assert idx["codes"]["tw:7730"]["fails"] == ["2026-10-30", "2026-10-29"] and E.d2(idx["codes"]["tw:7730"]) == "write"
    again = {"at": "2026-10-30 22:10", "codes": {"tw:6870": dict(ok)}}               # 同一天重抓成功：留最後一次
    E.log_update(log, again)
    assert log["codes"]["tw:6870"] == [["2026-10-29", "ok"], ["2026-10-30", "ok"]] and E.d2(again["codes"]["tw:6870"]) == "ok"
    assert log["codes"]["tw:7730"][-1][1] == "news err: 觀測站 500"
    for i in range(15):
        E.log_update(log, {"at": f"2026-11-{i + 1:02d} 20:50", "codes": {"tw:6870": dict(ok)}})
    assert len(log["codes"]["tw:6870"]) == E.LOG_KEEP
    fx = E.for_facts({"id": "20261031-2047-abcdef", "at": "2026-10-31 20:55", "codes": {"tw:6870": {"ok": True, "deck": None}}}, "6870")
    assert fx["id"] == "20261031-2047-abcdef" and fx["at"].startswith("2026-10-31") and E.for_facts({"codes": {}}, "6870") is None


def test_workflow_logs_to_main_before_pushing_the_pack():
    wf = (ROOT / ".github" / "workflows" / "eq_docs.yml").read_text("utf-8")
    i, j = wf.index("data/eq_docs_log.json 寫回 main"), wf.index("- name: 推到臨時分支")
    assert i < j                                                           # 排程拉到文件包時，main 已經有今天的紀錄、index 已標 fails
    step = wf[i:j]
    assert "continue-on-error: true" in step and "add data/eq_docs_log.json" in step and "push -q origin HEAD:main" in step
    assert "fetch_eqdocs.py --log" in step and "git add -A" not in step
    assert "--depth=1 origin +refs/heads/main" in step and not re.search(r"git( -C \S+)? pull", step)   # checkout 是淺的：只拿 main 最新一個 commit、不 rebase
