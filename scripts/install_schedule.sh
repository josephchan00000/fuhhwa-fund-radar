#!/usr/bin/env bash
# 由你「手動執行一次」來啟用每天盤後自動上線（安裝 macOS LaunchAgent）。
# 用法：bash scripts/install_schedule.sh          # 安裝＋啟用
#       bash scripts/install_schedule.sh --remove  # 移除排程
#
# 排程：週一～週五 14:30 與 18:00 各跑一次 scripts/publish_public.sh（抓最新→產表→公開上線）。
#   · 14:30：收盤(13:30)後即出同日市價/績效歸因（00991A 官方MIS市價）。
#   · 18:00：補官方 NAV（FHTrust 傍晚才出）＋ 上櫃 TPEx 收盤，最完整。
# 注意：LaunchAgent 只在「Mac 開機且登入」時會觸發；睡眠/關機時段的排程會在喚醒後補跑一次。
# 日誌：data/publish_cron.log。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.fharm.publish.plist"
LABEL="com.fharm.publish"

if [ "${1:-}" = "--remove" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✅ 已移除排程（$LABEL）。"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"
times=""
for wd in 1 2 3 4 5; do
  times="$times        <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>14</integer><key>Minute</key><integer>30</integer></dict>
"
done
for wd in 1 2 3 4 5; do
  times="$times        <dict><key>Weekday</key><integer>$wd</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
"
done

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>cd "$ROOT" &amp;&amp; bash scripts/publish_public.sh &gt;&gt; data/publish_cron.log 2&gt;&amp;1</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
$times    </array>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$ROOT/data/publish_cron.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/data/publish_cron.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✅ 已啟用每天盤後自動上線（週一～五 14:30 + 18:00）。"
echo "   日誌：data/publish_cron.log；移除：bash scripts/install_schedule.sh --remove"
launchctl list | grep "$LABEL" >/dev/null && echo "   launchctl 已載入 $LABEL ✓" || echo "   ⚠ 未在 launchctl 清單看到，請確認權限。"
