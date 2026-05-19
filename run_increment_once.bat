@echo off
setlocal ENABLEEXTENSIONS
set APP_DIR=%~dp0
set LOG_DIR=%APP_DIR%logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set LOG_FILE=%LOG_DIR%\run_increment.log

echo ==== [%date% %time%] INCREMENT START ==== > "%LOG_FILE%"
echo ==== [%date% %time%] INCREMENT START ====
echo [info] Realtime output is enabled. Log file: %LOG_FILE%

if exist "%APP_DIR%CustomerHistorySync_Win7.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "& { & '%APP_DIR%CustomerHistorySync_Win7.exe' --config '%APP_DIR%config.json' --mode auto 2>&1 | Tee-Object -FilePath '%LOG_FILE%' -Append; exit $LASTEXITCODE }"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "& { py -3 -u '%APP_DIR%full_customer_history_sync.py' --config '%APP_DIR%config.json' --mode auto 2>&1 | Tee-Object -FilePath '%LOG_FILE%' -Append; exit $LASTEXITCODE }"
)

set EXIT_CODE=%ERRORLEVEL%
echo ==== [%date% %time%] INCREMENT END code=%EXIT_CODE% ==== >> "%LOG_FILE%"
echo ==== [%date% %time%] INCREMENT END code=%EXIT_CODE% ====

echo Exit code: %EXIT_CODE%
echo Log file: %LOG_FILE%
pause
exit /b %EXIT_CODE%
