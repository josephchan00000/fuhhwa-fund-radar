#!/bin/zsh
# 每日自動跑想法引擎（由 launchd 於交易日傍晚觸發）
cd "$HOME/Desktop/ETF資料抓取" || exit 1
PY="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
mkdir -p data
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 開始 =====" >> data/daily.log
# M1：跑全部主角（00991A/00998A/00986D），含今日輪播主角
"$PY" scripts/run_daily.py all >> data/daily.log 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') 結束 =====" >> data/daily.log
