@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_background.ps1" -OpenBrowser
if errorlevel 1 pause
