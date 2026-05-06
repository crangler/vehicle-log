# Vehicle Maintenance Log

A desktop application for tracking vehicle maintenance schedules, service history, and parts catalogs. Built with Python and PySide6 (Qt), with a local SQLite database.

## Features

- **Multiple vehicles** — manage any number of vehicles with details like year, make, model, trim, color, VIN, license plate, and odometer readings
- **Maintenance schedule** — per-vehicle schedule with color-coded status (OK / Due Soon / Overdue) based on distance and/or time intervals; pre-seeded with 14 common items (oil change, tire rotation, etc.)
- **Service log** — record each service event with date, mileage, cost, shop, and notes; attach images, videos, or PDFs
- **Parts catalog** — per-vehicle parts list with part number, alternate part number, supplier, URL, price, and notes; supports image/video attachments
- **Report generation** — export an HTML service report for a selected date range
- **Settings** — dark/light theme, km/mi distance units, configurable resources folder with optional auto-created sub-folders per vehicle

## Requirements

- Python 3.14+
- PySide6 6.11+

## Setup

```powershell
# Create and activate a virtual environment (uv recommended)
uv sync

# Or with pip
python -m venv .venv
.venv\Scripts\activate
pip install pyside6
```

## Running

```powershell
.venv\Scripts\activate
python app.py
```

## Architecture

Single-file application (`app.py`) with the following structure:

| Class | Purpose |
|---|---|
| `DatabaseManager` | SQLite wrapper (`vehicles.db`) — all CRUD and schema migrations |
| `VehicleApp` | `QMainWindow` — top-level window and tab container |
| `GarageTab` | Vehicle list with add/edit/delete |
| `ScheduleTab` | Maintenance schedule with status indicators |
| `ServicesTab` | Per-item service history and logging |
| `ServiceLogTab` | Full service log with report generation |
| `PartsTab` | Parts catalog per vehicle |
| `SettingsTab` | Theme, units, and folder settings |

## Database

SQLite database stored as `vehicles.db` in the working directory. Schema migrations run automatically on startup — safe to run against an existing database from earlier versions.
