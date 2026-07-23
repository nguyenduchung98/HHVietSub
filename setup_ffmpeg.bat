@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   HHVietSub - Kiem tra & Cai dat FFmpeg
echo ========================================
where ffmpeg.exe >nul 2>nul
if not errorlevel 1 goto :ready
echo Dang cai dat FFmpeg bang winget...
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :error
echo.
echo Da cai xong FFmpeg. Vui long khoi dong lai ung dung HHVietSub.
pause
exit /b 0
:ready
ffmpeg -version | findstr /b "ffmpeg version"
echo [OK] FFmpeg da san sang va hoat dong tot.
pause
exit /b 0
:error
echo [LOI] Khong the cai dat FFmpeg tu dong. Vui long cai Gyan.FFmpeg thu cong.
pause
exit /b 1
