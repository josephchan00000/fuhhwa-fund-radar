"""美股財報季的資料（arm/lab/earnusdata.py；規格 arm/lab/ernusspec.py 第 2 點）。只在 CI 跑（本容器擋 Yahoo、那斯達克）。

afterhours_refresh.yml 每一班都叫；同一個美股收盤抓過就跳過。
用法：python3 scripts/fetch_earn_us.py [--force]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    from arm.lab import earnusdata as D
    st = D.update(force="--force" in sys.argv)
    err = st.pop("err", [])
    print(f"[美股財報季] {st}")
    for e in err[:20]:
        print(f"  ⚠ {e}")
    if len(err) > 20:
        print(f"  …另外 {len(err) - 20} 則")


if __name__ == "__main__":
    main()
