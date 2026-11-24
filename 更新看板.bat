@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   投资雷达 · 每日更新
echo ================================================
echo.

REM 更新看板
python -m invest_radar --board
if errorlevel 1 goto fail

REM 同时出文本版（可选，注释掉就不要）
REM python -m invest_radar

echo.
echo 完成。看板: out\dashboard.html
goto end

:fail
echo.
echo [!] 运行失败，检查是否装了依赖:
echo     pip install akshare requests pandas mootdx

:end
echo.
pause
