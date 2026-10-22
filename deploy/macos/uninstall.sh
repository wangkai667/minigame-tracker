#!/bin/bash
set -euo pipefail
LABEL="com.minigame-tracker"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "已卸载 $LABEL"
