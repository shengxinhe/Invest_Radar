@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   临时外网访问（Cloudflare Quick Tunnel）
echo ================================================
echo.
echo   说明：
echo     - 需要先下载 cloudflared.exe 放到 tools\ 目录
echo     - 会生成一个 xxx.trycloudflare.com 的临时地址
echo     - 每次重启地址会变，适合临时测试
echo     - 长期使用请用 Tailscale Serve（见 README）
echo.
if not exist "tools\cloudflared.exe" (
    echo [ERROR] 找不到 tools\cloudflared.exe
    echo         下载: https://github.com/cloudflare/cloudflared/releases
    pause
    exit /b 1
)
tools\cloudflared.exe tunnel --url http://127.0.0.1:8000
pause
