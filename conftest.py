# tw-superstock-lab 是獨立的子專案（自己的 venv、pyproject 與測試），不在本專案的 pytest 範圍：
# 在 repo 根目錄跑 `python3 -m pytest -q` 只收 tests/；子專案請進該資料夾用它自己的 venv 跑。
collect_ignore = ["tw-superstock-lab"]
