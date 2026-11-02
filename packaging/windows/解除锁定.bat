@echo off
rem Clears the "downloaded from the Internet" mark (MOTW) on every file in this folder.
rem If double-clicking 启动游戏平台.cmd does nothing or SmartScreen blocks it, run this once.
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0launcher.py" --unlock
pause
