#!/usr/bin/env python3
"""每日賣點 / 多元想法產生器 CLI（M1：多檔主角）。

用法：
  python scripts/run_daily.py            # 跑全部主角（含今日輪播主角）
  python scripts/run_daily.py all        # 同上
  python scripts/run_daily.py 00991A     # 只跑單一檔
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arm import db, pipeline  # noqa: E402

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg.lower() == "all":
        pipeline.run_all()
    else:
        conn = db.connect()
        pipeline.run(arg, conn=conn)
        conn.close()
