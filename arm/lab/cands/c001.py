"""c001 毛利÷總資產（Novy-Marx 2013，大型股）。

每季財報公布期限（packtest.deadline：5/15、8/14、11/14、隔年 3/31）當天或之後的第一個交易日收盤，
合格股票依「近 q 季營業毛利的平均 ÷ 最近一季季底總資產」排序，分數高的先買（規格的 pick），抱到下一次期限。
財報一律經過 F：只用那一天已過公布期限的季（F.fs_q）。缺任何一季毛利、或沒有總資產的股票不排（金融業沒有營業毛利，自然不排）。
"""
from .. import bt3s
from .. import packtest as PT

QE = ("03-31", "06-30", "09-30", "12-31")


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


def rows(P, E, b, codes, p, F):
    n = int(p["q"])

    def score(c, t):
        q = F.fs_q(P.cal[t])
        if q is None:
            return None
        fs = F.fs(c)
        ta = (fs.get(q) or {}).get("ta")
        gps = [(fs.get(_back(q, k)) or {}).get("gp") for k in range(n)]
        if not ta or ta <= 0 or any(g is None for g in gps):
            return None
        return sum(gps) / n / ta

    return bt3s.rows_at(P, E, b, codes, _forms(P.cal), score)
