@echo off
setlocal
cd /d "%~dp0.."

if "%MYSQL_PASSWORD%"=="" (
  echo Please set MYSQL_PASSWORD before running this script.
  pause
  exit /b 1
)

tools\python38\python.exe -c "import os, runpy, sys; from pathlib import Path; script = next(Path('customer_history_job').glob('**/scripts/build_stock_pressure_reports.py')); sys.argv = [str(script), '--host', '127.0.0.1', '--port', '3306', '--user', 'root', '--password', os.environ.get('MYSQL_PASSWORD', ''), '--database', 'pos_ods', '--start-date', '2026-04-01', '--end-date', '2026-04-07', '--sale-dept', '\u830c\u5e73\u53bf\u70df\u8349\u4e13\u5356\u5c40']; runpy.run_path(str(script), run_name='__main__')"

pause
