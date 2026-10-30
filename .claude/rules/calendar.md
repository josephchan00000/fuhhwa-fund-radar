---
paths:
  - "arm/twholidays.py"
  - "arm/calendar.py"
  - "arm/calfill.py"
  - "arm/calsrc.py"
  - "scripts/run_calfill.py"
  - "scripts/probe_calsrc.py"
  - "scripts/fetch_tw_holidays.py"
  - "scripts/check_afterhours_fresh.py"
  - "config/official_schedule.json"
---
改休市表、行事曆或盤後看門狗之前，先讀 `wiki/main/calendar.md`（時點見 `wiki/ops/schedule.md`）。
- 暫代層只回「已知必休」、其餘 None 不猜；颱風日過後查證補進 `twholidays.ADHOC`，`SEED` 不動。
- 寫進 `GITHUB_OUTPUT` 的指令，stdout 只能有那個值，說明一律印 stderr。
- 排程錨只收確切日期，慣例推估不收。
