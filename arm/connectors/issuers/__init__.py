"""跨家持股來源註冊表（M2-2/M2-3）。

- 復華自家 → live assetsExcel（權威，Tier A）。
- 競品 → 各投信官網為 SPA、無乾淨公開 JSON（見 §18.1）：先以 drop-in 檔承接（Tier B），
  逐家 adapter 補實後仍回傳同一個 `Holding` 介面，引擎不動。

差異化引擎只透過 `competitor_peers()` / `benchmark_holdings()` 取料，與來源徹底解耦。
"""
from __future__ import annotations

from ... import config
from .. import fhtrust
from . import base
from .base import Holding, NoData, benchmark_holdings  # re-export

# 主力台股競品（issuer 命名與 peers.NOTABLE 一致）。live 多為 SPA → 先吃 drop-in。
COMPETITORS: dict[str, str] = {
    "00981A": "統一", "00403A": "統一", "00992A": "群益",
    "00980A": "野村", "00985A": "野村", "00990A": "元大",
}


def load_holdings(fund_id: str, iso_date: str) -> list[Holding]:
    """統一取單檔持股。復華自家=live；競品=drop-in；皆無→NoData。"""
    try:                                       # 復華自家走 live assetsExcel
        p = config.product(fund_id)
        snap = fhtrust.fetch_holdings(p["fund_id"], iso_date)
        return base.from_fhtrust_dict(fund_id, iso_date, snap["holdings"])
    except KeyError:
        pass
    curated = base.curated_holdings(fund_id)   # 競品 drop-in
    if curated is not None:
        return curated
    raise NoData(f"{fund_id} 無持股來源（競品 live 為 SPA，待 adapter 或 drop-in）")


def competitor_peers(iso_date: str, universe: set[str] | None = None
                     ) -> list[tuple[str, list[Holding]]]:
    """回傳 [(label, holdings)]，只含「實際取得到」的競品（取不到的誠實略過）。"""
    out: list[tuple[str, list[Holding]]] = []
    for code, issuer in COMPETITORS.items():
        if universe and code not in universe:
            continue
        try:
            out.append((f"{issuer}{code}", load_holdings(code, iso_date)))
        except NoData:
            continue
    return out
