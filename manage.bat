@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem Use UTF-8 codepage for Unicode output
chcp 65001 >nul

set "PS=powershell -NoProfile -ExecutionPolicy Bypass"

rem Wrapper for PowerShell manager (ASCII comments for compatibility)
rem Usage:
rem   manage.bat            - open menu
rem   manage.bat start      - start server
rem   manage.bat stop       - stop server
rem   manage.bat restart    - restart server
rem   manage.bat status     - server status
rem   manage.bat tail       - tail logs

if "%~1"=="" (
  %PS% -File ".\manage.ps1"
) else (
  rem Forward optional message/revision for DB commands
  %PS% -File ".\manage.ps1" -Action "%~1" -Message "%~2" -Revision "%~3"
)

endlocal
pause
