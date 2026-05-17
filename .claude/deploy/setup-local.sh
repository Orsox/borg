#!/bin/bash
# Install heartbeat and reflection as systemd user timers.
# Run once after cloning the repo or when unit files change.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

mkdir -p "$SYSTEMD_USER_DIR"

echo "Installing systemd user units…"
for unit in heartbeat.service heartbeat.timer reflection.service reflection.timer; do
    cp "$DEPLOY_DIR/$unit" "$SYSTEMD_USER_DIR/$unit"
    echo "  Installed: $unit"
done

systemctl --user daemon-reload

echo "Enabling timers…"
systemctl --user enable heartbeat.timer reflection.timer
systemctl --user start  heartbeat.timer reflection.timer

echo ""
echo "Done. Timer status:"
systemctl --user status heartbeat.timer reflection.timer --no-pager

echo ""
echo "Next heartbeat run:"
systemctl --user list-timers heartbeat.timer --no-pager

echo ""
echo "To watch heartbeat logs live:"
echo "  journalctl --user -u heartbeat.service -f"
