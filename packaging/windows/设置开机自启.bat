@echo off
rem Toggles "start with Windows" (run this script again to turn it off).
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0launcher.py" --toggle-autostart
pause
