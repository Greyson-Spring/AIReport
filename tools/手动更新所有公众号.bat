@echo off
chcp 65001 >nul
title 手动更新所有公众号
echo ============================================
echo   手动更新所有公众号文章
echo   (需要 Edge + 宿主机代理已启动)
echo ============================================
echo.
cd /d %~dp0
python manual_update.py
echo.
pause
