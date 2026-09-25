@echo off
REM CheerCustom uninstaller
taskkill /F /IM pythonw.exe 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v CheerDoubleMapper /f 2>nul
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v CheerCustomMapper /f 2>nul
rmdir /s /q "%LOCALAPPDATA%\Cheerdots\CheerCustom" 2>nul
echo [OK] Uninstalled. PodMouse settings are untouched
echo (to restore pointer cycle inside PodMouse, open this tool once and press rollback before uninstalling)
pause
