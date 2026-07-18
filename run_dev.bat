@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

title HHVietSub - Dev
echo.
echo  ========================================
echo      HHVietSub - Electron Dev Runner
echo  ========================================
echo.

where node.exe >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Node.js trong PATH.
    echo Vui long cai Node.js roi chay lai file nay.
    pause
    exit /b 1
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay npm.cmd.
    echo Vui long cai lai Node.js kem npm.
    pause
    exit /b 1
)

set "DCC_PYTHON=C:\Users\Admin\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe"
if not exist "%DCC_PYTHON%" (
    set "DCC_PYTHON=C:\Users\Admin\AppData\Local\Programs\Python\Python314\python.exe"
)

if not exist "node_modules\electron\cli.js" (
    echo [1/2] Dang cai dependency dev...
    call npm.cmd install
    if errorlevel 1 (
        echo [LOI] Cai dependency that bai.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Dependency da san sang.
)

echo [2/2] Dang khoi dong HHVietSub...
echo Nhan Ctrl+C de dung dev server.
echo.
call npm.cmd run dev

echo.
echo HHVietSub da dung.
pause
endlocal
