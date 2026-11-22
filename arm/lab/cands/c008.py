"""c008 淨發行股數低（Pontiff & Woodgate 2008，大型股）。

每季財報公布期限（packtest.deadline：5/15、8/14、11/14、隔年 3/31）當天或之後的第一個交易日收盤，
合格股票依「最近一季季底股本 ÷ q 季前季底股本 − 1」排序，增加最少（含減少）的先買（規格 pick 的 asc），抱到下一次期限。
股本是資產負債表的「股本」欄（仟元；面額不變時，股本變動＝股數變動）。
財報一律經過 F：只用那一天已過公布期限的季（F.fs_q）。兩個季底缺股本、或股本不是正數的股票不排。
原論文用調整過分割與股票股利的股數；台股的盈餘轉增資（配股）也會讓股本增加，這裡沒有調整（寫在規格的 note）。
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
        sh = (fs.get(q) or {}).get("cap")
        sh0 = (fs.get(_back(q, n)) or {}).get("cap")
        if not sh or not sh0 or sh <= 0 or sh0 <= 0:
            return None
        return sh / sh0 - 1

    return bt3s.rows_at(P, E, b, codes, _forms(P.cal), score)
