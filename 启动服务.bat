@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   投资雷达 · 启动服务
echo ================================================
echo.
echo   本机访问:  http://127.0.0.1:8000
echo.
echo   手机访问有两种方式（见 README）：
echo     1) 局域网:  http://^<本机内网IP^>:8000
echo     2) 外网:    用自己的 Tailscale（tailscale serve --bg 8000）
echo.

REM 端口占用检查
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [WARN] 端口 8000 被 PID %%a 占用，正在清理...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 2 >nul
)

python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
pause
