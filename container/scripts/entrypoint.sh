#!/bin/bash
set -e

echo "[cairn-vnc] Starting VNC services via supervisord..."

# ── 运行时生成 supervisord 配置 ─────────────────────────────────────
# 不在 Dockerfile 写死，而是运行时从 ENV 读取并注入到配置
# 好处：用户可通过 docker run -e 覆盖端口和 display
SUPERVISOR_CONF="/tmp/cairn-supervisord.conf"

# ── 生成 .htpasswd（HTTP Basic Auth 凭据）───────────────────────────
# 从 ENV 读取，默认使用 VNC_USER / VNC_PASS
HTPASSWD_FILE="/tmp/.htpasswd"
_AUTH_USER="${VNC_USER:-gumingyao_sx@qiyi.com}"
_AUTH_PASS="${VNC_PASS:-GMY895604@!}"
htpasswd -b -c "$HTPASSWD_FILE" "$_AUTH_USER" "$_AUTH_PASS" >/dev/null 2>&1

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

# 内部 websockify — 只监听 127.0.0.1，不直接暴露
[program:novnc]
command=websockify --web=/usr/share/novnc 127.0.0.1:6081 localhost:5900
autorestart=true
user=kali

# nginx 反向代理 — 在 :NOVNC_PORT 上提供 HTTP Basic Auth
[program:nginx]
command=nginx -c /tmp/cairn-nginx.conf -g "daemon off;"
autorestart=true
user=kali
SUPERVISOR_EOF

# ── 生成 nginx 配置 ─────────────────────────────────────────────────
# 代理到内部 websockify（127.0.0.1:6081），加上 Basic Auth
cat > /tmp/cairn-nginx.conf <<NGINX_EOF
worker_processes 1;
pid /tmp/nginx.pid;
error_log /tmp/nginx-error.log;

events {
    worker_connections 64;
}

http {
    access_log /tmp/nginx-access.log;
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
    sendfile      on;

    server {
        listen      ${NOVNC_PORT};
        server_name localhost;

        auth_basic           "Cairn VNC Desktop";
        auth_basic_user_file ${HTPASSWD_FILE};

        location / {
            proxy_pass http://127.0.0.1:6081;
            proxy_http_version 1.1;
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_read_timeout 86400s;
        }
    }
}
NGINX_EOF

# ── 启动 supervisord（后台） ────────────────────────────────────────
/usr/bin/supervisord -c "$SUPERVISOR_CONF"

# ── 等待 nginx + noVNC 就绪 ─────────────────────────────────────────
echo "[cairn-vnc] Waiting for nginx + noVNC to come up..."
for i in $(seq 1 30); do
    if /usr/bin/supervisorctl -c "$SUPERVISOR_CONF" status nginx 2>/dev/null | grep -q RUNNING; then
        echo "[cairn-vnc] ============================================="
        echo "[cairn-vnc]  VNC desktop ready!"
        echo "[cairn-vnc]  Display: ${DISPLAY}"
        echo "[cairn-vnc]  VNC port (direct): 5900 (no auth)"
        echo "[cairn-vnc]  Web access (auth required):"
        echo "[cairn-vnc]    URL:  http://<host-ip>:${NOVNC_PORT}/vnc.html"
        echo "[cairn-vnc]    User: ${_AUTH_USER}"
        echo "[cairn-vnc]    Pass: ${_AUTH_PASS}"
        echo "[cairn-vnc] ============================================="
        break
    fi
    sleep 1
done

# ── 执行 Cairn Dispatcher 传入的命令 ─────────────────────────────────
# 例如 exec sleep infinity → 容器保持运行，VNC 服务在后台持续提供
exec "$@"
