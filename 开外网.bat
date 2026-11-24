@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   投资雷达 · 开启外网（免费，无需域名）
echo ================================================
echo.
echo 前提：先运行 启动服务.bat，确认 http://127.0.0.1:8000 能打开
echo.
echo 下面的网址是临时公网地址，手机在任何网络都能访问
echo 每次重启都会变，把它添加到手机主屏幕后就不用管了
echo.
echo 按任意键开始...
pause >nul
echo.
tools\cloudflared.exe tunnel --url http://127.0.0.1:8000
pause
