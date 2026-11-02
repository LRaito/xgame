@echo off
rem Adds a Windows Firewall inbound rule so phones / tablets on the same Wi-Fi can reach
rem the server. Needs elevation, so it re-launches allow-lan.ps1 through a UAC prompt.
rem The rule only allows THIS package's python.exe (never "all python.exe").
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -Wait -FilePath powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','%~dp0allow-lan.ps1','-Root','%~dp0.')"
pause
