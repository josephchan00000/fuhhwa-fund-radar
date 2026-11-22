"""c009 Piotroski F 分數（Piotroski 2000，大型股）。

每季財報公布期限（packtest.deadline：5/15、8/14、11/14、隔年 3/31）當天或之後的第一個交易日收盤，
合格股票依分數排序，高的先買，抱到下一次期限。
Q＝那一天已過公布期限的最新一季（F.fs_q）；「這一期」＝Q 往前 q 季（含 Q），「前一期」＝再往前 q 季。
流量（淨利、營業現金流量、營收、毛利）是那一期 q 季的合計；期初總資產＝那一期開始前一季的季底總資產；
負債比、流動比率、股本用那一期最後一季的季底值。F 分數＝下面九項各 1 分：
  獲利：① 這一期淨利 > 0　② 這一期營業現金流量 > 0　③ 資產報酬率（淨利 ÷ 期初總資產）比前一期高
        ④ 這一期營業現金流量 > 淨利
  槓桿與流動性：⑤ 負債比（總負債 ÷ 總資產）比前一期低　⑥ 流動比率（流動資產 ÷ 流動負債）比前一期高
        ⑦ 股本沒有比前一期多
  經營效率：⑧ 毛利率（毛利 ÷ 營收）比前一期高　⑨ 資產週轉率（營收 ÷ 期初總資產）比前一期高
分數＝F＋帳面市值比 ÷ (1＋帳面市值比)：後面那一項在 0～1 之間，只決定同分時的先後（帳面市值比高的先買，和原論文只看
價值股的方向一致）；帳面市值比＝Q 季底歸屬母公司權益（仟元 × 1000）÷ 第 t 天的市值（P.cap，月底快照），拿不到或不是正數就當 0。
財報一律經過 F。任何一項要用的數字缺、總資產或流動負債或營收不是正數的股票不排；
金融業（Q 季沒有營業毛利）不排：沒有流動資產負債的分類，和一般公司不能比。
"""
from .. import bt3s
from .. import packtest as PT

QE = ("03-31", "06-30", "09-30", "12-31")
FLOW = ("ni", "ocf", "rev", "gp")


def _back(q: str, k: int) -> str:
    """季底 q 往前第 k 季的季底。"""
    y, i = int(q[:4]), QE.index(q[5:]) - k
    while i < 0:
        i += 4
        y -= 1
    return f"{y}-{QE[i]}"


def _forms(cal: list[str]) -> list[int]:
    """每一季公布期限當天或之後的第一個交易日（期限早於資料第一天的不算）。"""
    out = set()
    for y in range(int(cal[0][:4]) - 1, int(cal[-1][:4]) + 1):
        for md in QE:
            dl = PT.deadline(f"{y}-{md}")
            if dl < cal[0]:
                continue
            t = PT.form_after_deadline(cal, dl)
            if t is not None:
                out.add(t)
    return sorted(out)


def _period(fs: dict, end: str, n: int) -> dict | None:
    """以季底 end 結束的 n 季：流量合計、期初總資產、end 季底的資產負債欄位；缺任何一項回 None。"""
    s = dict.fromkeys(FLOW, 0.0)
    for k in range(n):
        v = fs.get(_back(end, k)) or {}
        for f in FLOW:
            if v.get(f) is None:
                return None
            s[f] += v[f]
    last = fs.get(end) or {}
    ta0 = (fs.get(_back(end, n)) or {}).get("ta")
    bal = {f: last.get(f) for f in ("ta", "tl", "ca", "cl", "cap")}
    if ta0 is None or any(x is None for x in bal.values()):
        return None
    if ta0 <= 0 or bal["ta"] <= 0 or bal["cl"] <= 0 or s["rev"] <= 0:
        return None
    s.update(bal, ta0=ta0)
    return s


def rows(P, E, b, codes, p, F):
    n = int(p["q"])

    def score(c, t):
        q = F.fs_q(P.cal[t])
        if q is None:
            return None
        fs = F.fs(c)
        cur = fs.get(q) or {}
        if cur.get("gp") is None:
            return None
        a, z = _period(fs, q, n), _period(fs, _back(q, n), n)
        if a is None or z is None:
            return None
        roa, roa0 = a["ni"] / a["ta0"], z["ni"] / z["ta0"]
        f = sum((
            a["ni"] > 0,
            a["ocf"] > 0,
            roa > roa0,
            a["ocf"] > a["ni"],
            a["tl"] / a["ta"] < z["tl"] / z["ta"],
            a["ca"] / a["cl"] > z["ca"] / z["cl"],
            a["cap"] <= z["cap"],
            a["gp"] / a["rev"] > z["gp"] / z["rev"],
            a["rev"] / a["ta0"] > z["rev"] / z["ta0"],
        ))
        bm = 0.0
        eqp = cur.get("eqp")
        caps = P.cap.get(c)
        mv = caps[t] if caps else None
        if eqp and mv and eqp > 0 and mv > 0:
            bm = eqp * 1000 / mv
        return f + bm / (1 + bm)

    return bt3s.rows_at(P, E, b, codes, _forms(P.cal), score)
