@echo off
rem Double-click entry point. All Chinese messages come from launcher.py, so this file
rem stays pure ASCII: cmd parses .cmd files in the OEM code page, and mixing Chinese in
rem here is the classic way to get mojibake or a broken parser.
chcp 65001 >nul
title XGame
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%~dp0python\python.exe" "%~dp0launcher.py" %*
if errorlevel 1 (
    echo.
    echo XGame did not start. See runtime\last-error.txt and logs\xgame.log under the data folder.
    pause
)
