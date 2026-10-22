#!/bin/bash
# 用 systemd 用户定时器安装每日任务。用法：./deploy/linux/install.sh [HH:MM]，默认 09:30
# Persistent=true：关机期间错过的任务开机后补跑。没有 systemd 的系统请改用 crontab（见 README）。
set -euo pipefail

TIME="${1:-09:30}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$(command -v python3)"
DIR="$HOME/.config/systemd/user"

"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python 3.9+"'
[ -f "$ROOT/config.json" ] || { echo "先复制 config.example.json 为 config.json 并填写推送 key"; exit 1; }
mkdir -p "$DIR"

cat > "$DIR/minigame-tracker.service" <<EOF
[Unit]
Description=Mini-game rank tracker

[Service]
Type=oneshot
WorkingDirectory=$ROOT
ExecStart=$PY -m tracker run
EOF

cat > "$DIR/minigame-tracker.timer" <<EOF
[Unit]
Description=Daily mini-game rank tracker

[Timer]
OnCalendar=*-*-* $TIME:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now minigame-tracker.timer
# 用户未登录时也运行
loginctl enable-linger "$USER" 2>/dev/null || echo "提示：执行 sudo loginctl enable-linger $USER 以便未登录时运行"
systemctl --user list-timers minigame-tracker.timer
echo "立即试跑：systemctl --user start minigame-tracker.service"
