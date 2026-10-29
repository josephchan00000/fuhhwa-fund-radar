---
paths:
  - "arm/lab/ussx*.py"
  - "arm/lab/us*.py"
  - "arm/lab/secfin.py"
  - "arm/lab/omfixspec.py"
  - "scripts/run_ussx.py"
  - "scripts/run_usfin.py"
  - "scripts/run_usstrat.py"
  - "scripts/fetch_ussx_watch.py"
  - "scripts/backfill_ussx.py"
  - "scripts/backfill_usstk.py"
---
改美股強勢品質股或美股個股卡之前，先讀 `wiki/lab/us-qm.md`（個股卡見 `wiki/lab/cfg-research.md`）。
- 資料分支 `claude/ussx-data` 絕不合併進 main；SEC 聯絡 email 只從 secret `SEC_CONTACT_EMAIL` 讀。
- 研究期間 ussxspec 不動；改 `_sec_ctx` 或 `sec_quarters` 要確認 `tests/test_ussxfeat.py` 仍綠。
- 「目標價」只准在 `uscardpage.py` 的 `ucAn`。
