#!/bin/bash
set -e

echo "[cairn-vnc] Starting VNC services via supervisord..."

# ── 运行时生成 supervisord 配置 ─────────────────────────────────────
# 不在 Dockerfile 写死，而是运行时从 ENV 读取并注入到配置
# 好处：用户可通过 docker run -e 覆盖端口和 display
SUPERVISOR_CONF="/tmp/cairn-supervisord.conf"

cat > "$SUPERVISOR_CONF" <<SUPERVISOR_EOF
[supervisord]
nodaemon=false          # 后台运行，不阻塞 entrypoint
logfile=/tmp/supervisord.log
pidfile=/tmp/supervisord.pid
user=kali

[program:xvfb]
command=Xvfb ${DISPLAY} -screen 0 1280x720x24 -ac +extension RANDR
autorestart=true
user=kali
environment=DISPLAY=${DISPLAY}

[program:fluxbox]
command=fluxbox -display ${DISPLAY}
autorestart=true
user=kali
environment=DISPLAY=${DISPLAY}

[program:x11vnc]
command=x11vnc -display ${DISPLAY} -forever -shared -nopw -listen 0.0.0.0 -rfbport 5900 -xkb
autorestart=true
user=kali
environment=DISPLAY=${DISPLAY}

[program:novnc]
command=websockify --web=/usr/share/novnc ${NOVNC_PORT} localhost:5900
autorestart=true
user=kali
SUPERVISOR_EOF

# ── 启动 supervisord（后台） ────────────────────────────────────────
/usr/bin/supervisord -c "$SUPERVISOR_CONF"

# ── 等待 noVNC 就绪 ─────────────────────────────────────────────────
echo "[cairn-vnc] Waiting for x11vnc + noVNC to come up..."
for i in $(seq 1 30); do
    if /usr/bin/supervisorctl -c "$SUPERVISOR_CONF" status novnc 2>/dev/null | grep -q RUNNING; then
        echo "[cairn-vnc] VNC desktop ready!"
        echo "[cairn-vnc] Display: ${DISPLAY}"
        echo "[cairn-vnc] VNC port: 5900"
        echo "[cairn-vnc] noVNC web: http://<host-ip>:${NOVNC_PORT}/vnc.html"
        break
    fi
    sleep 1
done

# ── 执行 Cairn Dispatcher 传入的命令 ─────────────────────────────────
# 例如 exec sleep infinity → 容器保持运行，VNC 服务在后台持续提供
exec "$@"
