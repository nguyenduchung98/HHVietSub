@echo off
setlocal
cd /d "%~dp0"
echo ========================================
echo   HHVietSub - Setup VieNeu-TTS Backend
echo ========================================
where uv >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua co uv. Cai bang lenh: winget install astral-sh.uv
  pause
  exit /b 1
)
if not exist "runtime\VieNeu-TTS\.git" (
  if not exist "runtime" mkdir "runtime"
  git clone --depth 1 https://github.com/pnnbao97/VieNeu-TTS.git "runtime\VieNeu-TTS"
  if errorlevel 1 goto :error
) else (
  echo [OK] Da co ma nguon VieNeu-TTS.
)
cd /d "%~dp0runtime\VieNeu-TTS"
uv sync --group gpu
if errorlevel 1 goto :error
uv pip install transformers accelerate peft
if errorlevel 1 goto :error
echo.
echo [OK] VieNeu-TTS backend da san sang.
echo Model Ngoc Huyen se tu tai o lan tao dau tien.
pause
exit /b 0
:error
echo.
echo [LOI] Khong the cai VieNeu-TTS. Xem thong bao phia tren.
pause
exit /b 1
