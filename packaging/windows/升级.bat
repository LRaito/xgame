@echo off
rem Auto-upgrade wrapper. It copies upgrade.ps1 into %TEMP% and runs it from there:
rem the upgrade renames the whole xgame folder at the end, and Windows refuses to rename a
rem folder that contains an open file -- including the script PowerShell is reading.
rem Run with /auto when the launcher calls it (no pause at the end).
setlocal
chcp 65001 >nul
set "ROOT=%~dp0."
set "SCRIPT=%TEMP%\xgame-upgrade.ps1"
copy /y "%~dp0upgrade.ps1" "%SCRIPT%" >nul
if errorlevel 1 (
    echo Cannot copy upgrade.ps1 to %TEMP%.
    pause
    exit /b 1
)
cd /d "%TEMP%"
if /i "%~1"=="/auto" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Root "%ROOT%" -Auto
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Root "%ROOT%"
)
set "CODE=%ERRORLEVEL%"
del "%SCRIPT%" >nul 2>&1
if /i not "%~1"=="/auto" pause
exit /b %CODE%
