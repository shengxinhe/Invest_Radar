@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title 投资雷达 - 本机服务

echo ================================================================
echo   投资雷达 · 本机服务
echo ================================================================
echo.
echo   本机访问:     http://127.0.0.1:8000
echo   手机(装 Tailscale):  https://rancho.duiker-ling.ts.net
echo   手机(同一 WiFi):     http://192.168.2.223:8000
echo.
echo   关掉这个窗口 = 服务停止
echo ================================================================
echo.

REM ---------- 1. 检查 Python ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 找不到 python，请先安装 Python 3.11+
    pause
    exit /b 1
)

REM ---------- 2. 端口占用清理 ----------
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [警告] 8000 端口被 PID %%a 占用，正在关闭...
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 2 >nul
)

REM ---------- 3. 检查前端构建 ----------
if not exist "web_build\index.html" (
    echo [提示] 未找到前端构建产物，正在构建...
    pushd web
    call npm run build
    popd
    if not exist "web_build\index.html" (
        echo [错误] 前端构建失败
        pause
        exit /b 1
    )
)

REM ---------- 4. 数据库备份（每天首次启动）----------
set "STAMPFILE=data\.last_backup"
set "TODAY=%date:~0,4%%date:~5,2%%date:~8,2%"
set "LAST="
if exist "%STAMPFILE%" set /p LAST=<"%STAMPFILE%"
if not "!LAST!"=="!TODAY!" (
    if exist "data\radar.db" (
        echo [备份] 正在备份数据库...
        if not exist "data\backups" mkdir "data\backups"
        python -c "import sqlite3,shutil,os,sys; s=r'data\radar.db'; c=sqlite3.connect(s); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); ok=c.execute('PRAGMA integrity_check').fetchone()[0]; c.close(); d=r'data\backups\radar_auto_"!TODAY!".db'; shutil.copy2(s,d); print(('OK ' if ok=='ok' else 'BAD ')+d)"
        echo !TODAY!>"%STAMPFILE%"
    )
)

REM ---------- 5. 启动服务 ----------
echo.
echo [启动] 服务运行中... 按 Ctrl+C 停止
echo.
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --log-level warning

echo.
echo [停止] 服务已退出
pause
