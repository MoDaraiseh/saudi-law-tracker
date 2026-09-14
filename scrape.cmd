@echo off
REM Wrapper for Task Scheduler / cron: run the daily scrape, check that every
REM enabled source actually ran recently, then run the live smoke test as a
REM second, independent check. Run from the repo root so .env and relative
REM paths resolve; output is appended to logs\cron.log. See README.md's
REM "Scheduling" section for how to register this with Windows Task
REM Scheduler.
REM
REM The smoke test (tests\test_live_smoke.py) is deliberately redundant with
REM `scrape`'s own min_expected_docs/zero_rows check: this is the guard that
REM should have caught SLT-03 originally (a scraper whose selectors drift out
REM from under the live site's real markup, quietly returning 0 verified
REM rows). It's excluded from the normal `pytest` run since it hits real
REM external sites; only the scheduled job runs it.
REM
REM Exit code (visible as Task Scheduler's "Last Run Result"):
REM   0        scrape succeeded, no source is stale, and the smoke test found
REM            a verified dated row for every enabled source
REM   nonzero  any of the above three checks failed -- see logs\cron.log for
REM            which one and, for the smoke test, which source
cd /d "%~dp0"

".venv\Scripts\python.exe" -m saudi_law_tracker scrape >> "logs\cron.log" 2>&1
set SCRAPE_EXIT=%ERRORLEVEL%

".venv\Scripts\python.exe" -m saudi_law_tracker status --max-age-hours 36 >> "logs\cron.log" 2>&1
set STATUS_EXIT=%ERRORLEVEL%

".venv\Scripts\python.exe" -m pytest -m live tests\test_live_smoke.py >> "logs\cron.log" 2>&1
set SMOKE_EXIT=%ERRORLEVEL%

if %SCRAPE_EXIT% NEQ 0 exit /b %SCRAPE_EXIT%
if %STATUS_EXIT% NEQ 0 exit /b %STATUS_EXIT%
exit /b %SMOKE_EXIT%
