@echo off
chcp 65001 >nul
echo ================================================
echo   微信读书采集 - 宿主机服务启动器
echo   (需要已登录微信读书的Edge + 宿主机代理)
echo ================================================
echo.

REM 1. 启动 Edge(带调试口, 独立配置) 并打开阅读器页
set EDGE="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not exist %EDGE% set EDGE="C:\Program Files\Microsoft\Edge\Application\msedge.exe"
set PROFILE=%USERPROFILE%\Desktop\project\edge-weread-profile
set READER=https://weread.qq.com/web/mp/reader/1b742a6224d505f5758535f33303831363733383033e66

echo [1/2] 启动 Edge(调试口9222)...
start "weread-edge" %EDGE% --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 --remote-allow-origins=* --user-data-dir="%PROFILE%" "%READER%"
echo       若Edge未登录微信读书，请在窗口中扫码登录，并确认阅读器页能显示文章。
echo.

REM 2. 启动宿主机代理(HTTP :9000)
echo [2/2] 启动宿主机代理...
start "weread-agent" cmd /k "chcp 65001 >nul && cd /d %~dp0 && python host_weread_agent.py"

echo.
echo 完成! 两个服务已启动:
echo   - Edge 调试口 : http://localhost:9222  (别关窗口, 保持微信读书登录+阅读器页)
echo   - 宿主机代理  : http://localhost:9000  (抓取请求经它转发)
echo.
echo 注意: 这两个窗口要保持运行, 关闭则无法抓取。
pause
