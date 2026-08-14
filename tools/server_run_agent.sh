#!/bin/bash
# 供 systemd 调用的包装脚本: 启动 Xvfb + 多个Chrome(账号池) + 前台运行代理(由systemd监控)
set -e
export DISPLAY=:99
# 账号池端口(可环境变量覆盖), 每个端口=一个微信读书账号
WEREAD_PORTS="${WEREAD_PORTS:-9222,9223}"
export WEREAD_PORTS

# 1. Xvfb (若没跑)
if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
  rm -f /tmp/.X99-lock
  nohup Xvfb :99 -screen 0 1280x900x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi

# 2. 每个账号启动一个 Chrome (若没跑)
for port in $(echo "$WEREAD_PORTS" | tr ',' ' '); do
  if ! pgrep -f "remote-debugging-port=$port" >/dev/null 2>&1; then
    echo "[weread] 启动Chrome 端口 $port"
    nohup google-chrome --remote-debugging-port=$port --remote-allow-origins=* \
      --user-data-dir="$HOME/.weread-chrome-$port" --no-sandbox --disable-dev-shm-usage \
      "https://weread.qq.com/" >/tmp/chrome-$port.log 2>&1 &
  fi
done
sleep 6

# 3. 前台运行代理 (exec 让 systemd 直接监控)
cd "$(dirname "$0")"
exec python3 host_weread_agent.py
