FROM --platform=amd64 kalilinux/kali-rolling:latest

RUN apt update && \
    apt -y install kali-linux-headless && \
    apt clean && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash kali && \
    echo "kali ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER kali

# ── Phase 1: Slimmed apt/pip install ─────────────────────────────────────────
# Removed: sshpass, ncat, rlwrap, bloodyad, coercer, enum4linux-ng, pwncat,
#          chisel-common-binaries, krb5-user, netexec, adb, pwntools
RUN sudo apt update && \
    sudo apt install -y bsdextrautils npm jq iputils-ping \
    dirsearch yq gitleaks naabu nikto && \
    sudo apt clean && \
    sudo rm -rf /var/lib/apt/lists/* && \
    pip3 install pymongo --break-system-packages && \
    sudo npm install -g @playwright/cli@latest && \
    cd /tmp && playwright-cli install

# ── Phase 1: Slimmed binary downloads ────────────────────────────────────────
# Removed: nuclei, dalfox, kerbrute, nuclei-templates (git clone + update)
RUN cd /tmp && \
    wget -q "https://github.com/projectdiscovery/katana/releases/download/v1.5.0/katana_1.5.0_linux_amd64.zip" -O katana.zip && \
    wget -q "https://github.com/BishopFox/cloudfox/releases/download/v2.0.1/cloudfox-linux-amd64.zip" -O cloudfox.zip && \
    unzip -q katana.zip katana && sudo mv katana /usr/local/bin/ && \
    unzip -q cloudfox.zip cloudfox/cloudfox && sudo mv cloudfox/cloudfox /usr/local/bin/ && \
    sudo rm -rf /tmp/*

# ── Phase 1: ripgrep & fd ────────────────────────────────────────────────────
RUN cd /tmp && \
    wget -q "https://github.com/BurntSushi/ripgrep/releases/download/15.1.0/ripgrep_15.1.0-1_amd64.deb" -O ripgrep.deb && \
    wget -q "https://github.com/sharkdp/fd/releases/download/v10.4.2/fd_10.4.2_amd64.deb" -O fd.deb && \
    sudo apt install ./ripgrep.deb ./fd.deb && \
    sudo rm -rf /tmp/* && \
    sudo apt clean && \
    sudo rm -rf /var/lib/apt/lists/*

# ── Cloud CLIs ───────────────────────────────────────────────────────────────
RUN pip3 install tccli awscli --break-system-packages && \
    sudo bash -c "$(curl -fsSL https://aliyuncli.alicdn.com/install.sh)"

# ── AI Coding Agents ─────────────────────────────────────────────────────────
RUN sudo npm install -g @openai/codex@0.118.0
RUN sudo npm install -g @anthropic-ai/claude-code@2.1.98
RUN sudo npm install -g @mariozechner/pi-coding-agent@0.73.0

# ── Phase 2: VNC Remote Desktop for Manual Login ─────────────────────────────
#  See docs/vnc-remote-desktop.md for full design rationale.
#  Packages: supervisor (process mgmt), xvfb (virtual framebuffer),
#            x11vnc (VNC server), novnc + websockify (Web VNC client),
#            fluxbox (window manager), chromium (desktop browser)
RUN sudo apt update && \
    sudo apt install -y supervisor xvfb x11vnc novnc websockify fluxbox chromium && \
    sudo apt clean && \
    sudo rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/kali/scripts /home/kali/.config/chromium-vnc

# ── Phase 2: Environment variables for VNC ───────────────────────────────────
ENV DISPLAY=:99
ENV CHROMIUM_USER_DATA_DIR=/home/kali/.config/chromium-vnc
ENV CDP_PORT=9222
ENV NOVNC_PORT=6080

# ── System cleanup ───────────────────────────────────────────────────────────
RUN sudo rm -rf /usr/lib/llvm-*/build && \
    sudo chmod o+rx /usr/lib/mysql/plugin/auth_pam_tool_dir /etc/ssl/private

# ── Shell & workspace setup ──────────────────────────────────────────────────
RUN printf '%s\n' 'PS1="${PS1%\\n*} \[\033[0;36m\]\D{%y-%m-%d} - \t\[\033[;32m\]\n${PS1##*\\n}"' >> /home/kali/.bashrc && \
    mkdir -p /home/kali/workspace && cd /home/kali/workspace && git init

ENV TZ=Asia/Shanghai
ENV PLAYWRIGHT_MCP_BROWSER=chromium
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
ENV PYTHONUNBUFFERED=1

# ── Agent config ─────────────────────────────────────────────────────────────
COPY ./.agents /home/kali/workspace/.agents
COPY ./.agents /home/kali/workspace/.claude
COPY ./AGENTS.md /home/kali/workspace/AGENTS.md
COPY ./AGENTS.md /home/kali/workspace/CLAUDE.md

# ── Phase 2: VNC scripts & entrypoint ────────────────────────────────────────
#  entrypoint.sh starts supervisord (Xvfb → fluxbox → x11vnc → noVNC),
#  then exec the CMD (sleep infinity) from Cairn Dispatcher.
#  open-browser.sh launches Chromium on the VNC desktop with CDP enabled.
COPY ./scripts /home/kali/scripts
RUN sudo chmod +x /home/kali/scripts/*.sh

ENTRYPOINT ["/home/kali/scripts/entrypoint.sh"]
CMD ["sleep", "infinity"]

WORKDIR /home/kali/workspace
