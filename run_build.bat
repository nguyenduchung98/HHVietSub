@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

title HHVietSub - Build & Run Production
echo.
echo  ========================================
echo      HHVietSub - Dong Goi & Chay
echo  ========================================
echo.

where node.exe >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Node.js trong PATH.
    pause
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay npm.cmd.
    pause
    exit /b 1
)

echo [1/2] Dang build giao dien va main process...
call npm.cmd run build
if errorlevel 1 (
    echo [LOI] Build that bai.
    pause
    exit /b 1
)

echo.
echo [2/2] Dang khoi dong HHVietSub Production Mode...
call npx.cmd electron .

echo.
echo HHVietSub da dung.
pause
endlocal
