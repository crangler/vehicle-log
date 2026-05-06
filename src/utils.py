import os
import calendar
import sqlite3
from datetime import date

from PySide6.QtGui import QColor


# ── helpers ────────────────────────────────────────────────────────────────

_IMAGE_EXTS = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'})
_VIDEO_EXTS = frozenset({
    '.mp4', '.avi', '.mov', '.mkv', '.wmv',
    '.m4v', '.webm', '.mpeg', '.mpg'})
_PDF_EXTS = frozenset({'.pdf'})


def _get_file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS:
        return 'image'
    if ext in _VIDEO_EXTS:
        return 'video'
    if ext in _PDF_EXTS:
        return 'pdf'
    return 'other'


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


KM_PER_MI = 1.60934


def km_to_unit(km: int | None, unit: str) -> int:
    if km is None:
        return 0
    return round(km / KM_PER_MI) if unit == "mi" else round(km)


def unit_to_km(val: int | None, unit: str) -> int:
    if val is None:
        return 0
    return round(val * KM_PER_MI) if unit == "mi" else round(val)


# ── default maintenance schedule ───────────────────────────────────────────
# (name, interval_distance, interval_months, sort_order)
# distance values are in km (app default)

DEFAULT_ITEMS = [
    ("Oil Change",           8_000,  6,  1),
    ("Tire Rotation",       12_000,  6,  2),
    ("Air Filter",          24_000, 12,  3),
    ("Cabin Air Filter",    24_000, 12,  4),
    ("Wiper Blades",          None, 12,  5),
    ("Battery",               None, 48,  6),
    ("Brake Fluid",           None, 24,  7),
    ("Brake Pads",          40_000, None, 8),
    ("Spark Plugs",         48_000, None, 9),
    ("Transmission Fluid",  48_000, None, 10),
    ("Coolant Flush",       48_000, 36, 11),
    ("Serpentine Belt",     80_000, None, 12),
    ("Timing Belt",         96_000, None, 13),
    ("Fuel Filter",         48_000, None, 14),
]


# ── schedule status ─────────────────────────────────────────────────────────

STATUS_OK = "OK"
STATUS_DUE_SOON = "Due Soon"
STATUS_OVERDUE = "Overdue"
STATUS_UNKNOWN = "Unknown"

PRIORITY = [STATUS_OVERDUE, STATUS_DUE_SOON, STATUS_OK]
DIST_WARNING = 500
DAYS_WARNING = 30

STATUS_COLORS = {
    STATUS_OVERDUE: QColor("#c0392b"),
    STATUS_DUE_SOON: QColor("#e67e22"),
    STATUS_OK: QColor("#27ae60"),
    STATUS_UNKNOWN: QColor("#7f8c8d"),
}


def compute_status(
    item: sqlite3.Row,
    last: sqlite3.Row | None,
    vehicle: sqlite3.Row,
) -> tuple[str, int | None, date | None]:
    if not last:
        return STATUS_UNKNOWN, None, None

    today = date.today()
    current_dist = vehicle["current_mileage"]
    next_dist = None
    next_date = None
    dist_status = STATUS_OK
    date_status = STATUS_OK

    if item["interval_miles"] and last["mileage_at_service"] is not None:
        next_dist = last["mileage_at_service"] + item["interval_miles"]
        if current_dist >= next_dist:
            dist_status = STATUS_OVERDUE
        elif current_dist >= next_dist - DIST_WARNING:
            dist_status = STATUS_DUE_SOON

    if item["interval_months"] and last["service_date"]:
        next_date = add_months(date.fromisoformat(
            last["service_date"]), item["interval_months"])
        if today >= next_date:
            date_status = STATUS_OVERDUE
        elif (next_date - today).days <= DAYS_WARNING:
            date_status = STATUS_DUE_SOON

    return min(dist_status, date_status, key=PRIORITY.index), next_dist, next_date
