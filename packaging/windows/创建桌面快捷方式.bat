@echo off
rem Creates a desktop shortcut (no installer, so the package does it itself).
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0launcher.py" --create-shortcut
pause
