#!/bin/bash
# Close Chromium launched by open-browser.sh, freeing CPU/memory.
# Uses the PID from /tmp/chromium.pid for precise targeting,
# then falls back to pkill for any remaining chromium processes.
#
# Intended to be called at the end of every AI task that used
# open-browser.sh — regardless of success, timeout, or failure.

set -e

PID_FILE="/tmp/chromium.pid"
PROFILE="${CHROMIUM_USER_DATA_DIR:-/home/kali/.config/chromium-vnc}"
GRACE_PERIOD_SEC=3

echo "[cairn-vnc] Closing Chromium..."

# ── 精确 PID 清理 ────────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "[cairn-vnc] Sending SIGTERM to Chromium PID=${PID}..."
        kill "$PID"

        # 等待最多 GRACE_PERIOD_SEC 秒让进程优雅退出
        for i in $(seq 1 $((GRACE_PERIOD_SEC * 10))); do
            kill -0 "$PID" 2>/dev/null || break
            sleep 0.1
        done

        # 若还活着，强杀
        if kill -0 "$PID" 2>/dev/null; then
            echo "[cairn-vnc] Chromium still alive, sending SIGKILL..."
            kill -9 "$PID" 2>/dev/null || true
        fi

        echo "[cairn-vnc] Chromium PID=${PID} stopped."
    else
        echo "[cairn-vnc] PID ${PID} no longer running."
    fi
    rm -f "$PID_FILE"
else
    echo "[cairn-vnc] No PID file found at ${PID_FILE}."
fi

# ── 兜底清理 ──────────────────────────────────────────────────────────
# 按 profile 路径关键字清理所有残余 chromium
REMAINING=$(pgrep -f "chromium.*${PROFILE}" 2>/dev/null || true)
if [ -n "$REMAINING" ]; then
    echo "[cairn-vnc] Cleaning up remaining Chromium processes: $REMAINING"
    pkill -f "chromium.*${PROFILE}" 2>/dev/null || true
    sleep 0.5
    pkill -9 -f "chromium.*${PROFILE}" 2>/dev/null || true
fi

# ── 清理信号文件 ──────────────────────────────────────────────────────
rm -f /tmp/waiting-login /tmp/login-done

echo "[cairn-vnc] Browser cleanup complete."
