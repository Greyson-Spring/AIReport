#!/bin/bash
# 启动 微信读书采集 宿主机服务 (Xvfb + Chrome + 代理)
# 用法: bash server_start_weread.sh
# 服务器IP(改成你自己的)
SERVER_IP="10.188.26.61"
cd "$(dirname "$0")"

echo "[1/4] 启动虚拟显示器 Xvfb..."
pkill -f "Xvfb :99" 2>/dev/null || true
sleep 1
Xvfb :99 -screen 0 1280x900x24 >/dev/null 2>&1 &
sleep 2
export DISPLAY=:99

echo "[2/4] 启动 Chrome (调试口9222, 打开微信读书登录页)..."
pkill -f "remote-debugging-port=9222" 2>/dev/null || true
sleep 1
google-chrome --remote-debugging-port=9222 --remote-allow-origins=* \
  --user-data-dir="$HOME/.weread-chrome" --no-sandbox --disable-dev-shm-usage \
  "https://weread.qq.com/" >/dev/null 2>&1 &
sleep 6

echo "[3/4] 启动宿主机代理 (端口9000)..."
pkill -f "host_weread_agent.py" 2>/dev/null || true
sleep 1
python3 host_weread_agent.py >/tmp/weread_agent.log 2>&1 &
sleep 2

echo "[4/4] ✅ 启动完成!"
echo ""
echo "=============================================="
echo " 下一步: 打开下面地址, 用手机微信扫码登录微信读书"
echo "   http://$SERVER_IP:9000/qr"
echo "=============================================="
echo "扫码登录后 Chrome 会跳到微信读书首页(登录成功)。"
echo "登录成功后, 在 WeRSS 网页或手动更新脚本触发抓取即可。"
echo ""
echo "查看代理日志: tail -f /tmp/weread_agent.log"
