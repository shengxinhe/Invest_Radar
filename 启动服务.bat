@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   Investment Radar - Starting Service
echo ================================================
echo.
echo   Local:       http://127.0.0.1:8000
echo   Phone / WAN: https://rancho.duiker-ling.ts.net
echo.
echo   ts.net requires: 1) PC Tailscale online  2) this service running
echo   Phone must connect to Tailscale App first
echo.

REM ===== 端口占用检查（防止僵尸进程导致启动失败）=====
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [WARN] Port 8000 already in use by PID %%a
    echo        Killing old process...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 2 >nul
)

REM ===== 启动 =====
echo [OK] Starting...
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
pause
