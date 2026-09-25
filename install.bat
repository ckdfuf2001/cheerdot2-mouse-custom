@echo off
REM CheerCustom v1.0 installer (CheerDots2 M-key customizer)
REM PodMouse does NOT need to be modified. Requires: PodMouse installed+paired,
REM Python 3.8+ (with tkinter, standard on python.org Windows builds).

set DST=%LOCALAPPDATA%\Cheerdots\CheerCustom
echo [1/4] Python check...
python --version 2>nul
if errorlevel 1 (
  echo PYTHON NOT FOUND. Install Python 3 from https://www.python.org/downloads/
  echo (check "Add python.exe to PATH" during install)
  pause
  exit /b 1
)
echo [2/4] Copy files to %DST%
mkdir "%DST%" 2>nul
copy /y "%~dp0cheer_double.py" "%DST%\" || (echo COPY FAILED & pause & exit /b 1)
copy /y "%~dp0cheer_physical.py" "%DST%\" 2>nul
copy /y "%~dp0start_cheer_double.bat" "%DST%\" 2>nul
echo [3/4] Python deps (websockets)...
python -m pip install --quiet websockets 2>nul
echo [4/4] Autostart registration...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v CheerDoubleMapper /t REG_SZ /d "%DST%\start_cheer_double.bat" /f >nul
echo.
echo [OK] Installed. Start PodMouse first, then run:
echo     %DST%\start_cheer_double.bat
start "" "%DST%\start_cheer_double.bat"
pause
