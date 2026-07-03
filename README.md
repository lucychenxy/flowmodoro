# Flowmo

Flowmo is a small Flowmodoro timer for recording focused work sessions.

Current scope:

- Windows-first Python desktop app using Tkinter.
- Local SQLite database for sessions and settings.
- Interface languages: English by default, with Chinese and German available.
- Work categories: reading, experiments, writing, teaching, meetings, admin.
- Forward timer with start/end buttons.
- Rest duration calculated as `work duration / break coefficient`.
- Recent tab with stacked bar charts for current day/week/month/year hourly work patterns.
- Category pie chart with total duration and percentage labels.
- History tab for reviewing any past day/week/month/year from a calendar date picker.
- Log tab for recent session records.

## Install on Windows

Most users should install Flowmo from the latest GitHub Release:

1. Open the [Flowmo v.0.0.2 release](https://github.com/lucychenxy/flowmodoro/releases/tag/v.0.0.2).
2. Download `Flowmo-Setup-v.0.0.2.exe`.
3. Run the installer.

The installer copies Flowmo to your local user programs folder and creates shortcuts.

## Build from Source

Clone the repository and run the app directly:

```powershell
python -m flowmo
```

The app creates its database at `data/flowmo.sqlite3`.

Run tests with:

```powershell
python -m unittest
```

To build the Windows executable yourself, install PyInstaller in the app environment once:

```powershell
conda install -n flowmo pyinstaller
```

Then build:

```powershell
conda run -n flowmo pyinstaller --noconfirm --clean Flowmo.spec
```

The executable is created at `dist/Flowmo.exe`.

To build a Windows installer yourself:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows_installer.ps1 -Version v.0.0.2
```

The installer is created at `release/Flowmo-Setup-v.0.0.2.exe`.

## Notes for Future Cross-Platform Work

The database and session logic are kept separate from the Tkinter UI. A future
Linux desktop, Android, web, or wearable client can reuse the SQLite schema or
sync against the same session model.

## Declaration of AI Use
Flowmo is my first vibe coding work - more than 90% of the code are written by codex
