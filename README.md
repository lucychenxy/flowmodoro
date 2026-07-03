# Flowmo

Flowmo is a small Flowmodoro timer for recording focused work sessions.

Current scope:

- Windows-first Python desktop app using Tkinter.
- Local SQLite database for sessions and settings.
- Work categories: reading, experiments, writing, teaching, meetings, admin.
- Forward timer with start/end buttons.
- Rest duration calculated as `work duration / break coefficient`.
- Recent tab with stacked bar charts for current day/week/month/year hourly work patterns.
- Category pie chart with total duration and percentage labels.
- History tab for reviewing any past day/week/month/year from a calendar date picker.
- Log tab for recent session records.

## Run

```powershell
python -m flowmo
```

The app creates its database at `data/flowmo.sqlite3`.

## Test

```powershell
python -m unittest
```

## Notes for Future Cross-Platform Work

The database and session logic are kept separate from the Tkinter UI. A future
Linux desktop, Android, web, or wearable client can reuse the SQLite schema or
sync against the same session model.

## Declaration of AI Use
Flowmo is my first vibe coding work - more than 90% of the code are written by codex
