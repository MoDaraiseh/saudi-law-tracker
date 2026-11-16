# Scheduling

The daily job is: run `scrape`, run `status --max-age-hours 36` so a source
that's stopped scraping successfully gets flagged rather than just silently
going quiet, then run the live smoke test (`pytest -m live
tests/test_live_smoke.py`) as a second, independent check that every enabled
source still returns at least one verified, dated row against the *live*
site — not just a fixture. `scrape.cmd` at the repo root already does all
three, in order, appending output to `logs\cron.log` and exiting non-zero if
any of them failed (so Task Scheduler's "Last Run Result" reflects any of
the three).

## Windows Task Scheduler

1. Confirm `scrape.cmd` runs cleanly by hand first: `.\scrape.cmd` from the
   repo root, then check `logs\cron.log` for `STALE` / errors.
2. Open Task Scheduler → **Create Task…** (not *Basic Task*, so you get the
   full options below).
3. **General** tab: name it (e.g. `saudi-law-tracker daily scrape`); select
   **Run whether user is logged on or not**; check **Run with highest
   privileges** only if your `.venv`/network setup actually needs it (it
   usually doesn't).
4. **Triggers** tab → **New…** → Daily, pick a time (e.g. 06:00), **Enabled**.
5. **Actions** tab → **New…** → Action: *Start a program*; **Program/script**:
   the full path to `scrape.cmd` (e.g.
   `C:\Users\<you>\saudi-law-tracker\scrape.cmd`); **Start in**: the repo root
   (e.g. `C:\Users\<you>\saudi-law-tracker`) — `scrape.cmd` also `cd /d`s
   there itself, but setting it here too avoids surprises if the task is ever
   invoked with a different working directory.
6. **Conditions**/**Settings** tabs: on a laptop, uncheck "Start the task only
   if the computer is on AC power" unless that's genuinely what you want.
7. Save. To verify: right-click the task → **Run**, then check
   `logs\cron.log` and the task's **Last Run Result** column (`0x0` =
   success; anything else = the scrape failed or a source is stale).

Equivalent one-liner via `schtasks` (run as the user who should own the
task, from an elevated prompt only if you also chose "highest privileges"
above):

```powershell
schtasks /Create /TN "saudi-law-tracker daily scrape" /TR "C:\Users\<you>\saudi-law-tracker\scrape.cmd" /SC DAILY /ST 06:00 /RL LIMITED
```

## cron (Linux/macOS)

`status` and the smoke test should run even if `scrape` itself failed, and
the redirect needs to wrap the whole compound command (not just the last
part) to capture all three:

```
0 6 * * *  { cd /path/to/saudi-law-tracker && .venv/bin/saudi-law-tracker scrape ; .venv/bin/saudi-law-tracker status --max-age-hours 36 ; .venv/bin/pytest -m live tests/test_live_smoke.py ; } >> logs/cron.log 2>&1
```
