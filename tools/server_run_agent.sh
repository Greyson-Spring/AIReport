#!/bin/bash
# 供 systemd 调用的包装脚本: 启动 Xvfb + Chrome(后台), 前台运行代理(由systemd监控, 崩溃自动重启)
set -e
export DISPLAY=:99

# 1. Xvfb (若没跑)
if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  rm -f /tmp/.X99-lock
  nohup Xvfb :99 -screen 0 1280x900x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi

# 2. Chrome (若没跑)
if ! pgrep -f "remote-debugging-port=9222" >/dev/null 2>&1; then
  nohup google-chrome --remote-debugging-port=9222 --remote-allow-origins=* \
    --user-data-dir="$HOME/.weread-chrome" --no-sandbox --disable-dev-shm-usage \
    "https://weread.qq.com/" >/tmp/chrome.log 2>&1 &
  sleep 6
fi

# 3. 前台运行代理 (exec 让 systemd 直接监控这个进程)
cd "$(dirname "$0")"
exec python3 host_weread_agent.py
