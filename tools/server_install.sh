#!/bin/bash
# 服务器安装 微信读书采集 所需环境: Xvfb虚拟显示器 + Google Chrome + Python依赖
# 用法: bash server_install.sh
set -e

echo "===== [1/3] 安装 Xvfb (虚拟显示器, 让无界面服务器能跑浏览器) ====="
sudo apt-get update -y
sudo apt-get install -y xvfb

echo "===== [2/3] 安装 Google Chrome ====="
if command -v google-chrome &>/dev/null; then
  echo "Chrome 已安装: $(google-chrome --version)"
else
  wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -O /tmp/google-chrome.deb
  sudo apt-get install -y /tmp/google-chrome.deb
  rm -f /tmp/google-chrome.deb
  echo "Chrome 安装完成: $(google-chrome --version)"
fi

echo "===== [3/3] 安装 Python websocket-client ====="
python3 -c "import websocket" 2>/dev/null || pip3 install websocket-client 2>/dev/null || sudo apt-get install -y python3-websocket

echo ""
echo "✅ 环境安装完成!"
echo "下一步运行: bash server_start_weread.sh"
