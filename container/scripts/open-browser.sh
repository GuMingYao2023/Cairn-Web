#!/bin/bash
# Open Chromium on the VNC desktop so you can manually log in.
# Run this inside the container:  /home/kali/scripts/open-browser.sh [URL]
# Then open http://<host-ip>:6080/vnc.html on your local machine.

set -e

BROWSER="chromium"
PROFILE="${CHROMIUM_USER_DATA_DIR:-/home/kali/.config/chromium-vnc}"
URL="${1:-about:blank}"

echo "[cairn-vnc] Starting Chromium on display ${DISPLAY}..."
echo "[cairn-vnc] Profile: ${PROFILE}"
echo "[cairn-vnc] CDP remote-debugging-port: ${CDP_PORT:-9222}"
echo "[cairn-vnc] Opening URL: ${URL}"

# 先杀已有同 profile 的 chromium 进程，避免 lockfile 冲突
pkill -f "chromium.*${PROFILE}" 2>/dev/null || true
sleep 1

DISPLAY="${DISPLAY:-:99}" \
    "$BROWSER" \
    --no-first-run \
    --no-default-browser-check \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-dev-shm-usage \
    --disable-sync \
    --no-sandbox \
    --window-size=1280,720 \
    --window-position=0,0 \
    --user-data-dir="$PROFILE" \
    --remote-debugging-port="${CDP_PORT:-9222}" \
    --remote-debugging-address=0.0.0.0 \
    "$URL" &

CHROMIUM_PID=$!
echo "[cairn-vnc] Chromium started (PID: ${CHROMIUM_PID})"
echo "[cairn-vnc]"
echo "[cairn-vnc] ▲ Machine B: open http://<host-ip>:${NOVNC_PORT:-6080}/vnc.html to see the desktop"
echo "[cairn-vnc] ▲ CDP endpoint: http://<host-ip>:${CDP_PORT:-9222}"
