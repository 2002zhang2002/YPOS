@echo off
setlocal ENABLEEXTENSIONS
set APP_DIR=%~dp0

if exist "%APP_DIR%CustomerHistorySync_Config.exe" (
  start "" "%APP_DIR%CustomerHistorySync_Config.exe"
) else if exist "%APP_DIR%configurator_gui.py" (
  py -3 "%APP_DIR%configurator_gui.py"
) else (
  echo Configurator not found.
  pause
)
