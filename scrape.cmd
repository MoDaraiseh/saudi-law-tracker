@echo off
REM Wrapper for Task Scheduler / cron: run the daily scrape, then check that
REM every enabled source actually ran recently. Run from the repo root so
REM .env and relative paths resolve; output is appended to logs\cron.log.
REM See README.md's "Scheduling" section for how to register this with
REM Windows Task Scheduler.
REM
REM Exit code (visible as Task Scheduler's "Last Run Result"):
REM   0        scrape succeeded and no source is stale
REM   nonzero  the scrape itself failed, OR `status --max-age-hours` found a
REM            source with no successful run in the last 36 hours
cd /d "%~dp0"

".venv\Scripts\python.exe" -m saudi_law_tracker scrape >> "logs\cron.log" 2>&1
set SCRAPE_EXIT=%ERRORLEVEL%

".venv\Scripts\python.exe" -m saudi_law_tracker status --max-age-hours 36 >> "logs\cron.log" 2>&1
set STATUS_EXIT=%ERRORLEVEL%

if %SCRAPE_EXIT% NEQ 0 exit /b %SCRAPE_EXIT%
exit /b %STATUS_EXIT%
