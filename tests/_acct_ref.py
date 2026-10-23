"""舊版資金帳戶（2026-10-23 修正前的 bt3.account／optim.account_v 原封複本），只給測試比對：
兩期不重疊時，新版必須和舊版逐位相同（每期報酬、淨值曲線、逐筆紀錄）。重疊時舊版會「用後一期賣出的錢買前一天的股票」，
不再當基準。"""
from __future__ import annotations

from arm.lab.backtest import LIMIT_UP, exit_day, locked_down
from arm.lab.bt3 import side_cost


def account_ref(P, periods: list, b: str, *, mult: float = 1.0, limit: bool = True, gap: float | None = None,
              stop: float | None = None, log: list | None = None) -> dict:
    """bt3.account 的複本＋兩個候選旋鈕（gap、stop 皆為 None 時逐行等同 bt3.account）：
    gap＝不在原持股的新名單股票，開盤 ≥ 前一日收盤 ×（1＋gap）當期不買（資金留現金）；
    stop＝當期第一天開盤為參考價（續抱股也是），收盤跌破參考價 ×（1 − stop）當天收盤賣出（鎖跌停順延）、持有現金到期末。"""
    S, T, cal = P.s, P.T, P.cal
    cash = 1.0
    hold: dict[str, float] = {}
    last: dict[str, float] = {}
    curve, units = [], []

    def px(c: str, i: int) -> float | None:
        v = S[c]["c"][i]
        if v:
            last[c] = v
        return v or last.get(c)

    def value(i: int) -> float:
        return cash + sum(sh * (px(c, i) or 0.0) for c, sh in hold.items())

    for k, (t, x, picks) in enumerate(periods):
        j = t + 1
        if j > x or j >= T or not picks:
            continue
        V0 = value(t)
        if not curve:
            curve.append((t, V0))
        cost = 0.0
        lim = lock = ngap = nstop = 0
        pend: dict[str, int] = {}
        tgt = set(picks)
        for c in [c for c in hold if c not in tgt]:
            s = S[c]
            if limit and locked_down(s, j):
                pend[c] = exit_day(s, j, T)
                lock += 1
                continue
            p = s["o"][j] or px(c, t)
            amt = hold.pop(c) * p
            cash += amt * (1 - side_cost(b, True, mult))
            cost += amt * side_cost(b, True, mult)
            if log is not None:
                log.append(("s", k, c, j, p, True, "drop"))
        Vo = cash + sum(sh * ((S[c]["o"][j] or px(c, t)) or 0.0) for c, sh in hold.items())
        tv = Vo * (1 - side_cost(b, False, mult)) / len(picks)
        buy = 0.0
        for c in picks:
            s = S[c]
            o = s["o"][j]
            if not o:
                if log is not None and c not in hold:
                    log.append(("x", k, c, j, "noopen"))
                continue
            cur = hold.get(c, 0.0) * o
            diff = tv - cur
            if diff > 0:
                if limit and o >= (s["c"][t] or px(c, t) or o) * LIMIT_UP:
                    lim += c not in hold
                    if log is not None and c not in hold:
                        log.append(("x", k, c, j, "lim"))
                    continue
                if gap is not None and c not in hold and o >= (s["c"][t] or px(c, t) or o) * (1 + gap):
                    ngap += 1
                    if log is not None:
                        log.append(("x", k, c, j, "gap"))
                    continue
                if log is not None and c not in hold:
                    log.append(("b", k, c, j, o))
                cash -= diff * (1 + side_cost(b, False, mult))
                cost += diff * side_cost(b, False, mult)
                hold[c] = hold.get(c, 0.0) + diff / o
                buy += diff
            elif diff < 0:
                cash += -diff * (1 - side_cost(b, True, mult))
                cost += -diff * side_cost(b, True, mult)
                hold[c] = hold.get(c, 0.0) + diff / o
        ref = {c: S[c]["o"][j] for c in hold if S[c]["o"][j]} if stop is not None else {}
        for i in range(j, x + 1):
            for c in [c for c, d2 in pend.items() if d2 == i]:
                p = px(c, i) or 0.0
                amt = hold.pop(c) * p
                cash += amt * (1 - side_cost(b, True, mult))
                cost += amt * side_cost(b, True, mult)
                del pend[c]
                if log is not None:
                    log.append(("s", k, c, i, p, False, "lock"))
            if stop is not None:
                for c in [c for c in hold if c not in pend and ref.get(c)]:
                    cl = S[c]["c"][i]
                    if not cl or cl >= ref[c] * (1 - stop):
                        continue
                    nstop += 1
                    i2 = exit_day(S[c], i, T)
                    if i2 != i:
                        pend[c] = i2                      # 鎖跌停賣不掉：順延（超過期末就留給期末處理）
                        continue
                    amt = hold.pop(c) * cl
                    cash += amt * (1 - side_cost(b, True, mult))
                    cost += amt * side_cost(b, True, mult)
                    if log is not None:
                        log.append(("s", k, c, i, cl, False, "stop"))
            curve.append((i, value(i)))
        nxt = periods[k + 1][0] if k + 1 < len(periods) else None
        if nxt != x:
            for c in list(hold):
                s = S[c]
                i2 = exit_day(s, x, T) if limit else x
                lock += i2 != x
                p = px(c, i2) or px(c, x) or 0.0
                amt = hold.pop(c) * p
                cash += amt * (1 - side_cost(b, True, mult))
                cost += amt * side_cost(b, True, mult)
                if log is not None:
                    log.append(("s", k, c, i2, p, False, "end" if i2 == x else "endlock"))
            curve[-1] = (x, cash)
        V1 = curve[-1][1]
        units.append({"d": cal[t], "t": t, "x": x, "r": (V1 / V0 - 1) * 100 if V0 > 0 else None, "hd": x - t,
                      "to": buy / Vo if Vo > 0 else None, "cost": cost / V0 * 100 if V0 > 0 else None,
                      "n": len(picks), "lim": lim, "lock": lock, "gap": ngap, "stop": nstop})
    return {"units": units, "curve": curve}
