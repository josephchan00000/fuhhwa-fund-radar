"""c004 低總資產成長（Cooper, Gulen & Schill 2008，大型股）。

每季財報公布期限（packtest.deadline：5/15、8/14、11/14、隔年 3/31）當天或之後的第一個交易日收盤，
合格股票依「最近一季季底總資產 ÷ q 季前同一欄位 − 1」排序，成長最低的先買（規格 pick 的 asc），抱到下一次期限。
財報一律經過 F：只用那一天已過公布期限的季（F.fs_q）。缺其中任何一季總資產、或總資產不是正數的股票不排。
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
        ta0 = (fs.get(_back(q, n)) or {}).get("ta")
        if not ta or not ta0 or ta <= 0 or ta0 <= 0:
            return None
        return ta / ta0 - 1

    return bt3s.rows_at(P, E, b, codes, _forms(P.cal), score)
