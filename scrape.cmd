@echo off
REM Wrapper for Task Scheduler / cron: run the daily scrape from the repo root
REM so .env and relative paths resolve, appending output to logs\cron.log.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m saudi_law_tracker scrape >> "logs\cron.log" 2>&1
