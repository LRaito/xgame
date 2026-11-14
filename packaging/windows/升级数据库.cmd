@echo off
rem Upgrade the database structure in place. Close the XGame server window first.
rem Keep this file pure ASCII: cmd parses .cmd files in the OEM code page.
chcp 65001 >nul
title XGame - Upgrade database
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%~dp0python\python.exe" "%~dp0launcher.py" --upgrade-db
set "RC=%errorlevel%"
rem Result messages ([ OK ] / [FAIL]) come from launcher.py; keep this file ASCII.
pause
exit /b %RC%
