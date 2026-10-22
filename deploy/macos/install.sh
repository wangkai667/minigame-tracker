#!/bin/bash
# 用 launchd 安装每日定时任务。用法：./deploy/macos/install.sh [HH:MM]，默认 09:30
# 机器睡眠时错过的任务会在唤醒后补跑；关机期间的不会补。
set -euo pipefail

TIME="${1:-09:30}"
HOUR=$((10#${TIME%%:*}))
MINUTE=$((10#${TIME##*:}))
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$(command -v python3)"
LABEL="com.minigame-tracker"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python 3.9+"'
[ -f "$ROOT/config.json" ] || { echo "先复制 config.example.json 为 config.json 并填写推送 key"; exit 1; }
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string><string>-m</string><string>tracker</string><string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/logs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "已安装：每天 $TIME 运行（$PLIST）"
echo "立即试跑：launchctl kickstart gui/$(id -u)/$LABEL"
echo "建议关闭自动睡眠：sudo pmset -a sleep 0 disksleep 0"
