import sys
import os
import shutil
import sqlite3
import calendar
from datetime import date
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout, QLineEdit,
    QSpinBox, QDoubleSpinBox, QTextEdit, QDialogButtonBox, QStatusBar,
    QMessageBox, QHeaderView, QTabWidget, QLabel, QComboBox, QPushButton,
    QDateEdit, QRadioButton, QButtonGroup, QGroupBox, QFileDialog,
    QListWidget, QListWidgetItem, QScrollArea, QSlider,
)
from PySide6.QtCore import Qt, QDate, QEvent, QSettings, QSize, QUrl
from PySide6.QtGui import QColor, QBrush, QPalette, QDesktopServices, QPixmap, QIcon

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PySide6.QtMultimediaWidgets import QVideoWidget
    _HAS_MULTIMEDIA = True
except ImportError:
    _HAS_MULTIMEDIA = False

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    _HAS_PDF = True
except ImportError:
    _HAS_PDF = False


# ── helpers ────────────────────────────────────────────────────────────────

_IMAGE_EXTS = frozenset({'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'})
_VIDEO_EXTS = frozenset({'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.m4v', '.webm', '.mpeg', '.mpg'})
_PDF_EXTS   = frozenset({'.pdf'})

def _get_file_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _IMAGE_EXTS: return 'image'
    if ext in _VIDEO_EXTS: return 'video'
    if ext in _PDF_EXTS:   return 'pdf'
    return 'other'


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year  = d.year + month // 12
    month = month % 12 + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


KM_PER_MI = 1.60934

def km_to_unit(km, unit: str) -> int:
    if km is None:
        return 0
    return round(km / KM_PER_MI) if unit == "mi" else round(km)

def unit_to_km(val, unit: str) -> int:
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


# ── database ───────────────────────────────────────────────────────────────

class DatabaseManager:
    def __init__(self, db_path="vehicles.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate_per_vehicle_items()
        self._migrate_service_log_images()
        self._migrate_odometer_reading_date()
        self._migrate_parts()
        for v in self.conn.execute("SELECT id FROM vehicles"):
            self._seed_vehicle_maintenance_items(v["id"])

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname        TEXT,
                year            INTEGER NOT NULL,
                make            TEXT NOT NULL,
                model           TEXT NOT NULL,
                trim            TEXT,
                color           TEXT,
                vin             TEXT,
                license_plate   TEXT,
                current_mileage       INTEGER DEFAULT 0,
                odometer_reading_date TEXT,
                notes                 TEXT,
                date_added            TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS maintenance_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id      INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                interval_miles  INTEGER,
                interval_months INTEGER,
                sort_order      INTEGER DEFAULT 99
            );

            CREATE TABLE IF NOT EXISTS service_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id          INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                item_id             INTEGER NOT NULL REFERENCES maintenance_items(id),
                service_date        TEXT NOT NULL,
                mileage_at_service  INTEGER,
                cost                REAL,
                shop                TEXT,
                parts               TEXT,
                notes               TEXT
            );

            CREATE TABLE IF NOT EXISTS parts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id      INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                part_number     TEXT,
                alt_part_number TEXT,
                supplier        TEXT,
                url             TEXT,
                price           REAL,
                notes           TEXT
            );

            CREATE TABLE IF NOT EXISTS part_images (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id   INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                path      TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'image'
            );

            CREATE TABLE IF NOT EXISTS vehicle_images (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                path        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_log_images (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id  INTEGER NOT NULL REFERENCES service_log(id) ON DELETE CASCADE,
                path    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS maintenance_item_files (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id   INTEGER NOT NULL REFERENCES maintenance_items(id) ON DELETE CASCADE,
                path      TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'image'
            );

            CREATE TABLE IF NOT EXISTS maintenance_item_parts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id  INTEGER NOT NULL REFERENCES maintenance_items(id) ON DELETE CASCADE,
                part_id  INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS service_log_parts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id   INTEGER NOT NULL REFERENCES service_log(id) ON DELETE CASCADE,
                part_id  INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1
            );
        """)
        self.conn.commit()

    def _migrate_per_vehicle_items(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(maintenance_items)")}
        if "vehicle_id" in cols:
            return
        self.conn.execute(
            "ALTER TABLE maintenance_items ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE"
        )
        global_items = self.conn.execute(
            "SELECT * FROM maintenance_items WHERE vehicle_id IS NULL"
        ).fetchall()
        vehicles = self.conn.execute("SELECT id FROM vehicles").fetchall()
        id_map = {}
        for item in global_items:
            for v in vehicles:
                cur = self.conn.execute(
                    "INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order) VALUES (?,?,?,?,?)",
                    (v["id"], item["name"], item["interval_miles"], item["interval_months"], item["sort_order"]),
                )
                id_map[(item["id"], v["id"])] = cur.lastrowid
        for entry in self.conn.execute("SELECT id, vehicle_id, item_id FROM service_log").fetchall():
            new_id = id_map.get((entry["item_id"], entry["vehicle_id"]))
            if new_id:
                self.conn.execute("UPDATE service_log SET item_id=? WHERE id=?", (new_id, entry["id"]))
        self.conn.execute("DELETE FROM maintenance_items WHERE vehicle_id IS NULL")
        self.conn.commit()

    def _migrate_service_log_images(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(service_log_images)")}
        if "file_type" not in cols:
            self.conn.execute(
                "ALTER TABLE service_log_images ADD COLUMN file_type TEXT NOT NULL DEFAULT 'image'"
            )
            self.conn.commit()

    def _migrate_odometer_reading_date(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(vehicles)")}
        if "odometer_reading_date" not in cols:
            self.conn.execute("ALTER TABLE vehicles ADD COLUMN odometer_reading_date TEXT")
            self.conn.commit()

    def _migrate_parts(self):
        cols = {row[1] for row in self.conn.execute("PRAGMA table_info(parts)")}
        if "notes" not in cols:
            self.conn.execute("ALTER TABLE parts ADD COLUMN notes TEXT")
            self.conn.commit()

    def _seed_vehicle_maintenance_items(self, vehicle_id):
        if self.conn.execute(
            "SELECT COUNT(*) FROM maintenance_items WHERE vehicle_id=?", (vehicle_id,)
        ).fetchone()[0] == 0:
            self.conn.executemany(
                "INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order) VALUES (?,?,?,?,?)",
                [(vehicle_id, name, dist, months, order) for name, dist, months, order in DEFAULT_ITEMS],
            )
            self.conn.commit()

    # vehicles

    def add_vehicle(self, data):
        cur = self.conn.execute("""
            INSERT INTO vehicles
                (nickname, year, make, model, trim, color, vin, license_plate, current_mileage, odometer_reading_date, notes)
            VALUES
                (:nickname, :year, :make, :model, :trim, :color, :vin, :license_plate, :current_mileage, :odometer_reading_date, :notes)
        """, data)
        self.conn.commit()
        self._seed_vehicle_maintenance_items(cur.lastrowid)

    def update_vehicle(self, vehicle_id, data):
        self.conn.execute("""
            UPDATE vehicles
            SET nickname=:nickname, year=:year, make=:make, model=:model,
                trim=:trim, color=:color, vin=:vin, license_plate=:license_plate,
                current_mileage=:current_mileage, odometer_reading_date=:odometer_reading_date,
                notes=:notes
            WHERE id=:id
        """, {**data, "id": vehicle_id})
        self.conn.commit()

    def delete_vehicle(self, vehicle_id):
        self.conn.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
        self.conn.commit()

    def get_all_vehicles(self):
        return self.conn.execute(
            "SELECT * FROM vehicles ORDER BY year DESC, make, model"
        ).fetchall()

    def get_vehicle(self, vehicle_id):
        return self.conn.execute(
            "SELECT * FROM vehicles WHERE id=?", (vehicle_id,)
        ).fetchone()

    # maintenance items

    def get_maintenance_items(self, vehicle_id):
        return self.conn.execute(
            "SELECT * FROM maintenance_items WHERE vehicle_id=? ORDER BY sort_order, name",
            (vehicle_id,),
        ).fetchall()

    def add_maintenance_item(self, vehicle_id, data) -> int:
        max_order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM maintenance_items WHERE vehicle_id=?",
            (vehicle_id,),
        ).fetchone()[0]
        cur = self.conn.execute(
            """INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order)
               VALUES (:vehicle_id, :name, :interval_miles, :interval_months, :sort_order)""",
            {**data, "vehicle_id": vehicle_id, "sort_order": max_order + 1},
        )
        self.conn.commit()
        return cur.lastrowid

    def update_maintenance_item(self, item_id, data):
        self.conn.execute(
            """UPDATE maintenance_items
               SET name=:name, interval_miles=:interval_miles, interval_months=:interval_months
               WHERE id=:id""",
            {**data, "id": item_id},
        )
        self.conn.commit()

    def delete_maintenance_item(self, item_id):
        self.conn.execute("DELETE FROM service_log WHERE item_id=?", (item_id,))
        self.conn.execute("DELETE FROM maintenance_items WHERE id=?", (item_id,))
        self.conn.commit()

    def get_maintenance_item_files(self, item_id):
        return self.conn.execute(
            "SELECT * FROM maintenance_item_files WHERE item_id=? ORDER BY id", (item_id,)
        ).fetchall()

    def add_maintenance_item_file(self, item_id, path, file_type='image'):
        self.conn.execute(
            "INSERT INTO maintenance_item_files (item_id, path, file_type) VALUES (?, ?, ?)",
            (item_id, path, file_type),
        )
        self.conn.commit()

    def delete_maintenance_item_file(self, file_id):
        self.conn.execute("DELETE FROM maintenance_item_files WHERE id=?", (file_id,))
        self.conn.commit()

    def get_maintenance_item_parts(self, item_id):
        return self.conn.execute("""
            SELECT mip.id, mip.item_id, mip.part_id, mip.quantity,
                   p.name, p.part_number
            FROM maintenance_item_parts mip
            JOIN parts p ON mip.part_id = p.id
            WHERE mip.item_id = ?
            ORDER BY p.name
        """, (item_id,)).fetchall()

    def set_maintenance_item_parts(self, item_id, parts):
        self.conn.execute("DELETE FROM maintenance_item_parts WHERE item_id=?", (item_id,))
        for p in parts:
            self.conn.execute(
                "INSERT INTO maintenance_item_parts (item_id, part_id, quantity) VALUES (?,?,?)",
                (item_id, p["part_id"], p["quantity"]),
            )
        self.conn.commit()

    def get_service_log_parts(self, log_id):
        return self.conn.execute("""
            SELECT slp.id, slp.log_id, slp.part_id, slp.quantity,
                   p.name, p.part_number
            FROM service_log_parts slp
            JOIN parts p ON slp.part_id = p.id
            WHERE slp.log_id = ?
            ORDER BY p.name
        """, (log_id,)).fetchall()

    def set_service_log_parts(self, log_id, parts):
        self.conn.execute("DELETE FROM service_log_parts WHERE log_id=?", (log_id,))
        for p in parts:
            self.conn.execute(
                "INSERT INTO service_log_parts (log_id, part_id, quantity) VALUES (?,?,?)",
                (log_id, p["part_id"], p["quantity"]),
            )
        self.conn.commit()

    def get_service_log_count_for_item(self, item_id) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM service_log WHERE item_id=?", (item_id,)
        ).fetchone()[0]

    # parts

    def get_all_parts(self, vehicle_id=None):
        if vehicle_id is None:
            return self.conn.execute(
                "SELECT * FROM parts ORDER BY vehicle_id, name"
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM parts WHERE vehicle_id=? ORDER BY name", (vehicle_id,)
        ).fetchall()

    def get_part(self, part_id):
        return self.conn.execute(
            "SELECT * FROM parts WHERE id=?", (part_id,)
        ).fetchone()

    def add_part(self, data) -> int:
        cur = self.conn.execute("""
            INSERT INTO parts (vehicle_id, name, part_number, alt_part_number, supplier, url, price, notes)
            VALUES (:vehicle_id, :name, :part_number, :alt_part_number, :supplier, :url, :price, :notes)
        """, data)
        self.conn.commit()
        return cur.lastrowid

    def update_part(self, part_id, data):
        self.conn.execute("""
            UPDATE parts
            SET vehicle_id=:vehicle_id, name=:name, part_number=:part_number,
                alt_part_number=:alt_part_number, supplier=:supplier, url=:url, price=:price,
                notes=:notes
            WHERE id=:id
        """, {**data, "id": part_id})
        self.conn.commit()

    def delete_part(self, part_id):
        self.conn.execute("DELETE FROM parts WHERE id=?", (part_id,))
        self.conn.commit()

    def get_part_images(self, part_id):
        return self.conn.execute(
            "SELECT * FROM part_images WHERE part_id=? ORDER BY id", (part_id,)
        ).fetchall()

    def add_part_image(self, part_id, path, file_type='image'):
        self.conn.execute(
            "INSERT INTO part_images (part_id, path, file_type) VALUES (?, ?, ?)",
            (part_id, path, file_type),
        )
        self.conn.commit()

    def delete_part_image(self, image_id):
        self.conn.execute("DELETE FROM part_images WHERE id=?", (image_id,))
        self.conn.commit()

    # vehicle images

    def get_vehicle_images(self, vehicle_id):
        return self.conn.execute(
            "SELECT * FROM vehicle_images WHERE vehicle_id=? ORDER BY id", (vehicle_id,)
        ).fetchall()

    def add_vehicle_image(self, vehicle_id, path):
        self.conn.execute(
            "INSERT INTO vehicle_images (vehicle_id, path) VALUES (?, ?)", (vehicle_id, path)
        )
        self.conn.commit()

    def delete_vehicle_image(self, image_id):
        self.conn.execute("DELETE FROM vehicle_images WHERE id=?", (image_id,))
        self.conn.commit()

    # service log images

    def get_service_log_entries(self, vehicle_id):
        return self.conn.execute("""
            SELECT sl.*, mi.name AS service_name
            FROM service_log sl
            JOIN maintenance_items mi ON sl.item_id = mi.id
            WHERE sl.vehicle_id = ?
            ORDER BY sl.service_date DESC, sl.id DESC
        """, (vehicle_id,)).fetchall()

    def get_service_log_images(self, log_id):
        return self.conn.execute(
            "SELECT * FROM service_log_images WHERE log_id=? ORDER BY id", (log_id,)
        ).fetchall()

    def add_service_log_image(self, log_id, path, file_type='image'):
        self.conn.execute(
            "INSERT INTO service_log_images (log_id, path, file_type) VALUES (?, ?, ?)",
            (log_id, path, file_type),
        )
        self.conn.commit()

    def delete_service_log_image(self, image_id):
        self.conn.execute("DELETE FROM service_log_images WHERE id=?", (image_id,))
        self.conn.commit()

    # schedule

    def get_schedule(self, vehicle_id):
        vehicle = self.get_vehicle(vehicle_id)
        items   = self.get_maintenance_items(vehicle_id)
        result  = []
        for item in items:
            last = self.conn.execute("""
                SELECT * FROM service_log
                WHERE vehicle_id=? AND item_id=?
                ORDER BY service_date DESC, mileage_at_service DESC
                LIMIT 1
            """, (vehicle_id, item["id"])).fetchone()
            result.append((item, last, vehicle))
        return result

    # service log

    def log_service(self, data) -> int:
        cur = self.conn.execute("""
            INSERT INTO service_log
                (vehicle_id, item_id, service_date, mileage_at_service, cost, shop, parts, notes)
            VALUES
                (:vehicle_id, :item_id, :service_date, :mileage_at_service, :cost, :shop, :parts, :notes)
        """, data)
        self.conn.commit()
        return cur.lastrowid

    def get_service_log_entry(self, log_id):
        return self.conn.execute(
            "SELECT * FROM service_log WHERE id=?", (log_id,)
        ).fetchone()

    def update_service_log(self, log_id, data):
        self.conn.execute("""
            UPDATE service_log
            SET vehicle_id=:vehicle_id, item_id=:item_id, service_date=:service_date,
                mileage_at_service=:mileage_at_service, cost=:cost, shop=:shop,
                parts=:parts, notes=:notes
            WHERE id=:id
        """, {**data, "id": log_id})
        self.conn.commit()

    def close(self):
        self.conn.close()


# ── schedule status ─────────────────────────────────────────────────────────

STATUS_OK       = "OK"
STATUS_DUE_SOON = "Due Soon"
STATUS_OVERDUE  = "Overdue"
STATUS_UNKNOWN  = "Unknown"

PRIORITY        = [STATUS_OVERDUE, STATUS_DUE_SOON, STATUS_OK]
DIST_WARNING    = 500
DAYS_WARNING    = 30

STATUS_COLORS = {
    STATUS_OVERDUE:  QColor("#c0392b"),
    STATUS_DUE_SOON: QColor("#e67e22"),
    STATUS_OK:       QColor("#27ae60"),
    STATUS_UNKNOWN:  QColor("#7f8c8d"),
}


def compute_status(item, last, vehicle):
    if not last:
        return STATUS_UNKNOWN, None, None

    today        = date.today()
    current_dist = vehicle["current_mileage"]
    next_dist    = None
    next_date    = None
    dist_status  = STATUS_OK
    date_status  = STATUS_OK

    if item["interval_miles"] and last["mileage_at_service"] is not None:
        next_dist = last["mileage_at_service"] + item["interval_miles"]
        if current_dist >= next_dist:
            dist_status = STATUS_OVERDUE
        elif current_dist >= next_dist - DIST_WARNING:
            dist_status = STATUS_DUE_SOON

    if item["interval_months"] and last["service_date"]:
        next_date = add_months(date.fromisoformat(last["service_date"]), item["interval_months"])
        if today >= next_date:
            date_status = STATUS_OVERDUE
        elif (next_date - today).days <= DAYS_WARNING:
            date_status = STATUS_DUE_SOON

    return min(dist_status, date_status, key=PRIORITY.index), next_dist, next_date


# ── themes ──────────────────────────────────────────────────────────────────

def _make_palette(
    window, window_text, base, alt_base, text, button, button_text,
    highlight, highlighted_text,
) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(window))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(window_text))
    p.setColor(QPalette.ColorRole.Base,            QColor(base))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(alt_base))
    p.setColor(QPalette.ColorRole.Text,            QColor(text))
    p.setColor(QPalette.ColorRole.Button,          QColor(button))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(button_text))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(highlight))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(highlighted_text))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(base))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(text))
    return p


def dark_palette() -> QPalette:
    return _make_palette(
        window="#2d2d2d", window_text="#dcdcdc",
        base="#1e1e1e",   alt_base="#282828",
        text="#dcdcdc",
        button="#373737", button_text="#dcdcdc",
        highlight="#2a82da", highlighted_text="#000000",
    )


def light_palette() -> QPalette:
    return _make_palette(
        window="#f0f0f0", window_text="#000000",
        base="#ffffff",   alt_base="#e9e9e9",
        text="#000000",
        button="#f0f0f0", button_text="#000000",
        highlight="#0078d7", highlighted_text="#ffffff",
    )


# ── dialogs ─────────────────────────────────────────────────────────────────

class VehicleDialog(QDialog):
    def __init__(self, parent=None, vehicle=None, unit="km"):
        super().__init__(parent)
        self.setWindowTitle("Edit Vehicle" if vehicle else "Add Vehicle")
        self.setMinimumWidth(420)
        self._unit = unit
        self._build_ui(vehicle, unit)

    def _build_ui(self, v, unit):
        layout = QFormLayout(self)

        def val(field, default=""):
            return (v[field] or default) if v else default

        self.nickname        = QLineEdit(val("nickname"))
        self.year            = QSpinBox()
        self.year.setRange(1900, 2100)
        self.year.setValue(v["year"] if v else 2020)
        self.make            = QLineEdit(val("make"))
        self.model           = QLineEdit(val("model"))
        self.trim            = QLineEdit(val("trim"))
        self.color           = QLineEdit(val("color"))
        self.vin             = QLineEdit(val("vin"))
        self.license_plate   = QLineEdit(val("license_plate"))
        self.current_mileage = QSpinBox()
        self.current_mileage.setRange(0, 9_999_999)
        self.current_mileage.setSingleStep(100)
        self.current_mileage.setValue(km_to_unit(v["current_mileage"], unit) if v else 0)

        self.odometer_reading_date = QDateEdit()
        self.odometer_reading_date.setCalendarPopup(True)
        self.odometer_reading_date.setDisplayFormat("yyyy-MM-dd")
        self.odometer_reading_date.setSpecialValueText(" ")
        self.odometer_reading_date.setMinimumDate(QDate(1900, 1, 1))
        stored_date = val("odometer_reading_date")
        if stored_date:
            self.odometer_reading_date.setDate(QDate.fromString(stored_date, "yyyy-MM-dd"))
        else:
            self.odometer_reading_date.setDate(QDate.currentDate())

        self.notes           = QTextEdit(val("notes"))
        self.notes.setFixedHeight(70)

        layout.addRow("Nickname:",                    self.nickname)
        layout.addRow("Year *:",                      self.year)
        layout.addRow("Make *:",                      self.make)
        layout.addRow("Model *:",                     self.model)
        layout.addRow("Trim:",                        self.trim)
        layout.addRow("Color:",                       self.color)
        layout.addRow("VIN:",                         self.vin)
        layout.addRow("License Plate:",               self.license_plate)
        layout.addRow(f"Odometer ({unit}):",          self.current_mileage)
        layout.addRow("Odometer Reading Date:",       self.odometer_reading_date)
        layout.addRow("Notes:",                       self.notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate_and_accept(self):
        if not self.make.text().strip():
            QMessageBox.warning(self, "Required", "Make is required.")
            return
        if not self.model.text().strip():
            QMessageBox.warning(self, "Required", "Model is required.")
            return
        self.accept()

    def get_data(self):
        d = self.odometer_reading_date.date()
        return {
            "nickname":               self.nickname.text().strip() or None,
            "year":                   self.year.value(),
            "make":                   self.make.text().strip(),
            "model":                  self.model.text().strip(),
            "trim":                   self.trim.text().strip() or None,
            "color":                  self.color.text().strip() or None,
            "vin":                    self.vin.text().strip() or None,
            "license_plate":          self.license_plate.text().strip() or None,
            "current_mileage":        unit_to_km(self.current_mileage.value(), self._unit),
            "odometer_reading_date":  d.toString("yyyy-MM-dd") if d.isValid() else None,
            "notes":                  self.notes.toPlainText().strip() or None,
        }


class LogServiceDialog(QDialog):
    def __init__(self, parent, db, vehicles, *, vehicle_id=None, item_id=None, unit="km",
                 get_resources_folder=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Service Entry" if entry else "Log Service")
        self.setMinimumWidth(460)
        self._db                    = db
        self._unit                  = unit
        self._get_resources_folder  = get_resources_folder
        self._staged_images: list[str]   = []
        self._removed_images: list[dict] = []
        self._parts_data:    list[dict]  = []
        if entry:
            self._preferred_item_id = entry["item_id"]
            vehicle_id = entry["vehicle_id"]
        else:
            self._preferred_item_id = item_id
        self._build_ui(vehicles, vehicle_id, unit)
        if entry:
            self._populate_from_entry(entry)
        elif item_id is not None:
            self._populate_parts_from_item(item_id)

    def _build_ui(self, vehicles, vehicle_id, unit):
        layout = QFormLayout(self)

        self.vehicle_combo = QComboBox()
        for v in vehicles:
            label = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            self.vehicle_combo.addItem(label, v["id"])
        if vehicle_id is not None:
            idx = next((i for i in range(self.vehicle_combo.count())
                        if self.vehicle_combo.itemData(i) == vehicle_id), 0)
            self.vehicle_combo.setCurrentIndex(idx)

        self.item_combo = QComboBox()
        self.vehicle_combo.currentIndexChanged.connect(self._refresh_items)
        self._refresh_items()

        self.service_date = QDateEdit(QDate.currentDate())
        self.service_date.setCalendarPopup(True)
        self.service_date.setDisplayFormat("yyyy-MM-dd")

        self.mileage = QSpinBox()
        self.mileage.setRange(0, 9_999_999)
        self.mileage.setSingleStep(100)

        self.cost = QDoubleSpinBox()
        self.cost.setRange(0, 99_999)
        self.cost.setPrefix("$")
        self.cost.setDecimals(2)

        self.shop  = QLineEdit()
        self.shop.setPlaceholderText("Leave blank if DIY")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(60)

        layout.addRow("Vehicle:",               self.vehicle_combo)
        layout.addRow("Service:",               self.item_combo)
        layout.addRow("Date:",                  self.service_date)
        layout.addRow(f"Odometer ({unit}):",   self.mileage)
        layout.addRow("Cost:",                  self.cost)
        layout.addRow("Shop:",                  self.shop)

        parts_container = QWidget()
        parts_vbox = QVBoxLayout(parts_container)
        parts_vbox.setContentsMargins(0, 4, 0, 0)
        parts_vbox.setSpacing(4)

        parts_hdr = QHBoxLayout()
        parts_hdr.addWidget(QLabel("Parts:"))
        parts_hdr.addStretch()
        for _label, _slot in [("Add", self._add_part), ("Remove", self._remove_part)]:
            btn = QPushButton(_label)
            btn.clicked.connect(_slot)
            parts_hdr.addWidget(btn)
        parts_vbox.addLayout(parts_hdr)

        self._parts_table = QTableWidget()
        self._parts_table.setColumnCount(3)
        self._parts_table.setHorizontalHeaderLabels(["Part Name", "Part Number", "Qty"])
        self._parts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._parts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._parts_table.setFixedHeight(110)
        self._parts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._parts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._parts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._parts_table.verticalHeader().setVisible(False)
        parts_vbox.addWidget(self._parts_table)

        layout.addRow(parts_container)
        layout.addRow("Notes:",                 self.notes)

        img_container = QWidget()
        img_vbox = QVBoxLayout(img_container)
        img_vbox.setContentsMargins(0, 4, 0, 0)
        img_vbox.setSpacing(4)

        att_hdr = QHBoxLayout()
        att_hdr.addWidget(QLabel("Attachments:"))
        att_hdr.addStretch()
        for label, slot in [
            ("Add",    self._add_staged_image),
            ("Remove", self._remove_staged_image),
            ("Open",   self._open_attachment),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            att_hdr.addWidget(btn)
        img_vbox.addLayout(att_hdr)

        self._staged_list = QListWidget()
        self._staged_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._staged_list.setIconSize(QSize(80, 60))
        self._staged_list.setFixedHeight(100)
        self._staged_list.setFlow(QListWidget.Flow.LeftToRight)
        self._staged_list.setWrapping(False)
        self._staged_list.setSpacing(4)
        self._staged_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._staged_list.doubleClicked.connect(self._open_attachment)
        img_vbox.addWidget(self._staged_list)

        layout.addRow(img_container)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _refresh_items(self):
        vid = self.vehicle_combo.currentData()
        items = self._db.get_maintenance_items(vid) if vid is not None else []
        self.item_combo.clear()
        for it in items:
            self.item_combo.addItem(it["name"], it["id"])
        if self._preferred_item_id is not None:
            idx = next((i for i in range(self.item_combo.count())
                        if self.item_combo.itemData(i) == self._preferred_item_id), -1)
            if idx >= 0:
                self.item_combo.setCurrentIndex(idx)
            self._preferred_item_id = None

    def _add_image_item(self, img_type: str, img_id, path: str, file_type: str = 'image'):
        if file_type == 'image':
            pix  = QPixmap(path)
            icon = QIcon(pix.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)) if not pix.isNull() else QIcon()
        else:
            icon = QIcon()
        item = QListWidgetItem(icon, os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole,
                     {"type": img_type, "id": img_id, "path": path, "file_type": file_type})
        self._staged_list.addItem(item)

    def _populate_parts_from_item(self, item_id: int):
        for p in self._db.get_maintenance_item_parts(item_id):
            self._parts_data.append({
                "part_id":     p["part_id"],
                "name":        p["name"],
                "part_number": p["part_number"] or "",
                "quantity":    p["quantity"],
            })
        self._refresh_parts_table()

    def _populate_parts_from_log(self, log_id: int):
        for p in self._db.get_service_log_parts(log_id):
            self._parts_data.append({
                "part_id":     p["part_id"],
                "name":        p["name"],
                "part_number": p["part_number"] or "",
                "quantity":    p["quantity"],
            })
        self._refresh_parts_table()

    def _refresh_parts_table(self):
        self._parts_table.setRowCount(len(self._parts_data))
        for row, p in enumerate(self._parts_data):
            self._parts_table.setItem(row, 0, QTableWidgetItem(p["name"]))
            self._parts_table.setItem(row, 1, QTableWidgetItem(p["part_number"]))
            qty = QTableWidgetItem(str(p["quantity"]))
            qty.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._parts_table.setItem(row, 2, qty)

    def _add_part(self):
        vid       = self.vehicle_combo.currentData()
        all_parts = self._db.get_all_parts(vid)
        if not all_parts:
            QMessageBox.information(
                self, "No Parts",
                "No parts found for this vehicle. Add parts in the Parts tab first.",
            )
            return
        added_ids = {p["part_id"] for p in self._parts_data}
        available = [p for p in all_parts if p["id"] not in added_ids]
        if not available:
            QMessageBox.information(self, "All Parts Added",
                                    "All available parts for this vehicle have already been added.")
            return
        dlg = PickPartDialog(self, available)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            part_id, quantity = dlg.get_selection()
            part = next(p for p in all_parts if p["id"] == part_id)
            self._parts_data.append({
                "part_id":     part_id,
                "name":        part["name"],
                "part_number": part["part_number"] or "",
                "quantity":    quantity,
            })
            self._refresh_parts_table()

    def _remove_part(self):
        row = self._parts_table.currentRow()
        if row < 0 or row >= len(self._parts_data):
            return
        self._parts_data.pop(row)
        self._refresh_parts_table()

    def get_parts_data(self) -> list[dict]:
        return [{"part_id": p["part_id"], "quantity": p["quantity"]} for p in self._parts_data]

    def _populate_from_entry(self, entry):
        if entry["service_date"]:
            self.service_date.setDate(QDate.fromString(entry["service_date"], "yyyy-MM-dd"))
        if entry["mileage_at_service"]:
            self.mileage.setValue(km_to_unit(entry["mileage_at_service"], self._unit))
        if entry["cost"]:
            self.cost.setValue(entry["cost"])
        if entry["shop"]:
            self.shop.setText(entry["shop"])
        if entry["notes"]:
            self.notes.setPlainText(entry["notes"])
        self._populate_parts_from_log(entry["id"])
        for att in self._db.get_service_log_images(entry["id"]):
            ft = att["file_type"] if "file_type" in att.keys() else "image"
            self._add_image_item("existing", att["id"], att["path"], ft)

    def _add_staged_image(self):
        rf = self._get_resources_folder() if self._get_resources_folder else ""
        if not rf:
            QMessageBox.warning(
                self, "No Resources Folder",
                "Please set a Resources Folder in Settings before adding attachments.",
            )
            return
        dlg = AddAttachmentDialog(self, rf)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save attachment:\n{e}")
                return
            ft = _get_file_type(dest)
            self._staged_images.append(dest)
            self._add_image_item("staged", None, dest, ft)

    def _open_attachment(self):
        row = self._staged_list.currentRow()
        if row < 0:
            return
        meta = self._staged_list.item(row).data(Qt.ItemDataRole.UserRole)
        if not meta:
            return
        path = meta["path"]
        ft   = meta.get("file_type") or _get_file_type(path)
        if ft == "image":
            image_paths = []
            img_row = 0
            for i in range(self._staged_list.count()):
                m = self._staged_list.item(i).data(Qt.ItemDataRole.UserRole)
                if m and m.get("file_type", "image") == "image":
                    if m["path"] == path:
                        img_row = len(image_paths)
                    image_paths.append(m["path"])
            ImageViewerDialog(self, image_paths, img_row).exec()
        elif ft == "video":
            if _HAS_MULTIMEDIA:
                VideoViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif ft == "pdf":
            if _HAS_PDF:
                PdfViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _remove_staged_image(self):
        row = self._staged_list.currentRow()
        if row < 0:
            return
        meta = self._staged_list.item(row).data(Qt.ItemDataRole.UserRole)
        if meta and meta["type"] == "existing":
            self._removed_images.append(meta)
        else:
            path = meta["path"] if meta else None
            if path and path in self._staged_images:
                self._staged_images.remove(path)
            try:
                if path:
                    os.remove(path)
            except OSError:
                pass
        self._staged_list.takeItem(row)

    def reject(self):
        for path in self._staged_images:
            try:
                os.remove(path)
            except OSError:
                pass
        self._staged_images.clear()
        super().reject()

    def get_staged_images(self) -> list[str]:
        images = list(self._staged_images)
        self._staged_images.clear()
        return images

    def get_removed_images(self) -> list[dict]:
        removed = list(self._removed_images)
        self._removed_images.clear()
        return removed

    def get_data(self):
        return {
            "vehicle_id":         self.vehicle_combo.currentData(),
            "item_id":            self.item_combo.currentData(),
            "service_date":       self.service_date.date().toString("yyyy-MM-dd"),
            "mileage_at_service": unit_to_km(self.mileage.value(), self._unit) or None,
            "cost":               self.cost.value() or None,
            "shop":               self.shop.text().strip() or None,
            "parts":              None,
            "notes":              self.notes.toPlainText().strip() or None,
        }


class PickPartDialog(QDialog):
    def __init__(self, parent, parts):
        super().__init__(parent)
        self.setWindowTitle("Add Part")
        self.setMinimumWidth(320)
        self._parts = parts
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)
        self._combo = QComboBox()
        for p in self._parts:
            label = p["name"]
            if p["part_number"]:
                label += f"  ({p['part_number']})"
            self._combo.addItem(label, p["id"])
        layout.addRow("Part:", self._combo)
        self._qty = QSpinBox()
        self._qty.setRange(1, 999)
        self._qty.setValue(1)
        layout.addRow("Quantity:", self._qty)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_selection(self) -> tuple[int, int]:
        return self._combo.currentData(), self._qty.value()


class MaintenanceItemDialog(QDialog):
    def __init__(self, parent=None, item=None, unit="km", db=None, get_resources_folder=None,
                 vehicle_id=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Service" if item else "Add Service")
        self.setMinimumWidth(460)
        self._unit                 = unit
        self._db                   = db
        self._get_resources_folder = get_resources_folder
        self._vehicle_id           = vehicle_id
        self._staged_files: list[str]   = []
        self._removed_files: list[dict] = []
        self._parts_data:   list[dict]  = []
        self._build_ui(item, unit)
        if item and db:
            self._populate_files(item["id"])
            self._populate_parts(item["id"])

    def _build_ui(self, item, unit):
        layout = QFormLayout(self)

        self.name = QLineEdit(item["name"] if item else "")

        self.interval_dist = QSpinBox()
        self.interval_dist.setRange(0, 999_999)
        self.interval_dist.setSingleStep(500)
        self.interval_dist.setSpecialValueText("None")
        self.interval_dist.setValue(km_to_unit(item["interval_miles"], unit) if item and item["interval_miles"] else 0)

        self.interval_months = QSpinBox()
        self.interval_months.setRange(0, 120)
        self.interval_months.setSpecialValueText("None")
        self.interval_months.setValue(item["interval_months"] or 0 if item else 0)

        layout.addRow("Service Name *:",              self.name)
        layout.addRow(f"Distance interval ({unit}):", self.interval_dist)
        layout.addRow("Time interval (months):",      self.interval_months)

        parts_container = QWidget()
        parts_vbox = QVBoxLayout(parts_container)
        parts_vbox.setContentsMargins(0, 4, 0, 0)
        parts_vbox.setSpacing(4)

        parts_hdr = QHBoxLayout()
        parts_hdr.addWidget(QLabel("Parts:"))
        parts_hdr.addStretch()
        for label, slot in [("Add", self._add_part), ("Remove", self._remove_part)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            parts_hdr.addWidget(btn)
        parts_vbox.addLayout(parts_hdr)

        self._parts_table = QTableWidget()
        self._parts_table.setColumnCount(3)
        self._parts_table.setHorizontalHeaderLabels(["Part Name", "Part Number", "Qty"])
        self._parts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._parts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._parts_table.setFixedHeight(110)
        self._parts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._parts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._parts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._parts_table.verticalHeader().setVisible(False)
        parts_vbox.addWidget(self._parts_table)

        layout.addRow(parts_container)

        att_container = QWidget()
        att_vbox = QVBoxLayout(att_container)
        att_vbox.setContentsMargins(0, 4, 0, 0)
        att_vbox.setSpacing(4)

        att_hdr = QHBoxLayout()
        att_hdr.addWidget(QLabel("Attachments:"))
        att_hdr.addStretch()
        for label, slot in [
            ("Add",    self._add_staged_file),
            ("Remove", self._remove_staged_file),
            ("Open",   self._open_attachment),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            att_hdr.addWidget(btn)
        att_vbox.addLayout(att_hdr)

        self._staged_list = QListWidget()
        self._staged_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._staged_list.setIconSize(QSize(80, 60))
        self._staged_list.setFixedHeight(100)
        self._staged_list.setFlow(QListWidget.Flow.LeftToRight)
        self._staged_list.setWrapping(False)
        self._staged_list.setSpacing(4)
        self._staged_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._staged_list.doubleClicked.connect(self._open_attachment)
        att_vbox.addWidget(self._staged_list)

        layout.addRow(att_container)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _populate_files(self, item_id: int):
        for f in self._db.get_maintenance_item_files(item_id):
            ft = f["file_type"] if "file_type" in f.keys() else "image"
            self._add_file_item("existing", f["id"], f["path"], ft)

    def _populate_parts(self, item_id: int):
        for p in self._db.get_maintenance_item_parts(item_id):
            self._parts_data.append({
                "part_id":     p["part_id"],
                "name":        p["name"],
                "part_number": p["part_number"] or "",
                "quantity":    p["quantity"],
            })
        self._refresh_parts_table()

    def _refresh_parts_table(self):
        self._parts_table.setRowCount(len(self._parts_data))
        for row, p in enumerate(self._parts_data):
            self._parts_table.setItem(row, 0, QTableWidgetItem(p["name"]))
            self._parts_table.setItem(row, 1, QTableWidgetItem(p["part_number"]))
            qty = QTableWidgetItem(str(p["quantity"]))
            qty.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._parts_table.setItem(row, 2, qty)

    def _add_part(self):
        if not self._db:
            return
        all_parts = self._db.get_all_parts(self._vehicle_id)
        if not all_parts:
            QMessageBox.information(
                self, "No Parts",
                "No parts found for this vehicle. Add parts in the Parts tab first.",
            )
            return
        added_ids = {p["part_id"] for p in self._parts_data}
        available = [p for p in all_parts if p["id"] not in added_ids]
        if not available:
            QMessageBox.information(self, "All Parts Added",
                                    "All available parts for this vehicle have already been added.")
            return
        dlg = PickPartDialog(self, available)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            part_id, quantity = dlg.get_selection()
            part = next(p for p in all_parts if p["id"] == part_id)
            self._parts_data.append({
                "part_id":     part_id,
                "name":        part["name"],
                "part_number": part["part_number"] or "",
                "quantity":    quantity,
            })
            self._refresh_parts_table()

    def _remove_part(self):
        row = self._parts_table.currentRow()
        if row < 0 or row >= len(self._parts_data):
            return
        self._parts_data.pop(row)
        self._refresh_parts_table()

    def get_parts_data(self) -> list[dict]:
        return [{"part_id": p["part_id"], "quantity": p["quantity"]} for p in self._parts_data]

    def _add_file_item(self, tag: str, file_id, path: str, file_type: str = 'image'):
        if file_type == 'image':
            pix  = QPixmap(path)
            icon = QIcon(pix.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)) if not pix.isNull() else QIcon()
        else:
            icon = QIcon()
        it = QListWidgetItem(icon, os.path.basename(path))
        it.setData(Qt.ItemDataRole.UserRole,
                   {"type": tag, "id": file_id, "path": path, "file_type": file_type})
        self._staged_list.addItem(it)

    def _add_staged_file(self):
        rf = self._get_resources_folder() if self._get_resources_folder else ""
        if not rf:
            QMessageBox.warning(
                self, "No Resources Folder",
                "Please set a Resources Folder in Settings before adding attachments.",
            )
            return
        dlg = AddAttachmentDialog(self, rf)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save attachment:\n{e}")
                return
            ft = _get_file_type(dest)
            self._staged_files.append(dest)
            self._add_file_item("staged", None, dest, ft)

    def _open_attachment(self):
        row = self._staged_list.currentRow()
        if row < 0:
            return
        meta = self._staged_list.item(row).data(Qt.ItemDataRole.UserRole)
        if not meta:
            return
        path = meta["path"]
        ft   = meta.get("file_type") or _get_file_type(path)
        if ft == "image":
            image_paths = []
            img_row = 0
            for i in range(self._staged_list.count()):
                m = self._staged_list.item(i).data(Qt.ItemDataRole.UserRole)
                if m and m.get("file_type", "image") == "image":
                    if m["path"] == path:
                        img_row = len(image_paths)
                    image_paths.append(m["path"])
            ImageViewerDialog(self, image_paths, img_row).exec()
        elif ft == "video":
            if _HAS_MULTIMEDIA:
                VideoViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif ft == "pdf":
            if _HAS_PDF:
                PdfViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _remove_staged_file(self):
        row = self._staged_list.currentRow()
        if row < 0:
            return
        meta = self._staged_list.item(row).data(Qt.ItemDataRole.UserRole)
        if meta and meta["type"] == "existing":
            self._removed_files.append(meta)
        else:
            path = meta["path"] if meta else None
            if path and path in self._staged_files:
                self._staged_files.remove(path)
            try:
                if path:
                    os.remove(path)
            except OSError:
                pass
        self._staged_list.takeItem(row)

    def reject(self):
        for path in self._staged_files:
            try:
                os.remove(path)
            except OSError:
                pass
        self._staged_files.clear()
        super().reject()

    def get_staged_files(self) -> list[str]:
        files = list(self._staged_files)
        self._staged_files.clear()
        return files

    def get_removed_files(self) -> list[dict]:
        removed = list(self._removed_files)
        self._removed_files.clear()
        return removed

    def _validate_and_accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Required", "Service name is required.")
            return
        if self.interval_dist.value() == 0 and self.interval_months.value() == 0:
            QMessageBox.warning(self, "Required", "At least one interval (distance or months) is required.")
            return
        self.accept()

    def get_data(self):
        return {
            "name":            self.name.text().strip(),
            "interval_miles":  unit_to_km(self.interval_dist.value(), self._unit) or None,
            "interval_months": self.interval_months.value() or None,
        }


# ── image viewer ─────────────────────────────────────────────────────────────

class ImageViewerDialog(QDialog):
    _ZOOM_STEP = 1.25

    def __init__(self, parent, paths: list[str], index: int = 0):
        super().__init__(parent)
        self._paths = paths
        self._index = index
        self._pixmap = QPixmap()
        self._scale  = 1.0
        self._fit    = True
        self._build_ui()
        self.resize(900, 650)
        self._load_image()

    def _build_ui(self):
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidgetResizable(False)
        self._scroll.viewport().installEventFilter(self)
        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidget(self._img_label)
        layout.addWidget(self._scroll)

        bar = QHBoxLayout()
        self._prev_btn = QPushButton("◀ Prev")
        self._prev_btn.clicked.connect(self._prev)
        self._next_btn = QPushButton("Next ▶")
        self._next_btn.clicked.connect(self._next)
        bar.addWidget(self._prev_btn)
        bar.addWidget(self._next_btn)
        bar.addStretch()

        zoom_out = QPushButton("−")
        zoom_out.setFixedWidth(28)
        zoom_out.clicked.connect(self._zoom_out)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(52)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_in = QPushButton("+")
        zoom_in.setFixedWidth(28)
        zoom_in.clicked.connect(self._zoom_in)
        self._fit_btn = QPushButton("Fit")
        self._fit_btn.setCheckable(True)
        self._fit_btn.setChecked(True)
        self._fit_btn.clicked.connect(self._toggle_fit)

        bar.addWidget(zoom_out)
        bar.addWidget(self._zoom_label)
        bar.addWidget(zoom_in)
        bar.addWidget(self._fit_btn)
        layout.addLayout(bar)

    def _load_image(self):
        if not self._paths:
            return
        self._pixmap = QPixmap(self._paths[self._index])
        name = os.path.basename(self._paths[self._index])
        self.setWindowTitle(f"{name}  ({self._index + 1} of {len(self._paths)})")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < len(self._paths) - 1)
        self._apply_display()

    def _apply_display(self):
        if self._pixmap.isNull():
            self._img_label.setText("(Image not found)")
            return
        if self._fit:
            scaled = self._pixmap.scaled(
                self._scroll.viewport().size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._scale = scaled.width() / self._pixmap.width()
        else:
            scaled = self._pixmap.scaled(
                round(self._pixmap.width()  * self._scale),
                round(self._pixmap.height() * self._scale),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._img_label.setPixmap(scaled)
        self._img_label.resize(scaled.size())
        self._zoom_label.setText(f"{round(self._scale * 100)}%")

    def _toggle_fit(self, checked: bool):
        self._fit = checked
        self._fit_btn.setChecked(checked)
        self._apply_display()

    def _zoom_in(self):
        self._set_zoom(self._scale * self._ZOOM_STEP)

    def _zoom_out(self):
        self._set_zoom(self._scale / self._ZOOM_STEP)

    def _set_zoom(self, factor: float):
        self._fit = False
        self._fit_btn.setChecked(False)
        self._scale = max(0.05, min(factor, 10.0))
        self._apply_display()

    def _prev(self):
        if self._index > 0:
            self._index -= 1
            self._load_image()

    def _next(self):
        if self._index < len(self._paths) - 1:
            self._index += 1
            self._load_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit:
            self._apply_display()

    def eventFilter(self, source, event):
        if source is self._scroll.viewport() and event.type() == QEvent.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.angleDelta().y() > 0:
                    self._zoom_in()
                else:
                    self._zoom_out()
                return True
        return super().eventFilter(source, event)

    def keyPressEvent(self, event):
        k = event.key()
        if k == Qt.Key.Key_Left:
            self._prev()
        elif k == Qt.Key.Key_Right:
            self._next()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom_in()
        elif k == Qt.Key.Key_Minus:
            self._zoom_out()
        elif k == Qt.Key.Key_0 and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._toggle_fit(True)
        elif k == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)


# ── video viewer dialog ───────────────────────────────────────────────────────

class VideoViewerDialog(QDialog):
    def __init__(self, parent, path: str):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self._path = path
        self._build_ui()
        self.resize(860, 560)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._video_widget = QVideoWidget()
        layout.addWidget(self._video_widget)

        self._player = QMediaPlayer(self)
        self._audio  = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.setVideoOutput(self._video_widget)
        self._player.setSource(QUrl.fromLocalFile(self._path))

        controls = QHBoxLayout()

        self._play_btn = QPushButton("▶ Play")
        self._play_btn.setFixedWidth(80)
        self._play_btn.clicked.connect(self._toggle_play)
        controls.addWidget(self._play_btn)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._player.setPosition)
        controls.addWidget(self._slider)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setFixedWidth(90)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        controls.addWidget(self._time_label)

        layout.addLayout(controls)

        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.play()

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _on_state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_btn.setText("⏸ Pause" if playing else "▶ Play")

    def _on_duration_changed(self, duration: int):
        self._slider.setRange(0, duration)
        self._update_time()

    def _on_position_changed(self, position: int):
        if not self._slider.isSliderDown():
            self._slider.setValue(position)
        self._update_time()

    def _update_time(self):
        self._time_label.setText(
            f"{self._fmt_ms(self._player.position())} / {self._fmt_ms(self._player.duration())}"
        )

    def closeEvent(self, event):
        self._player.stop()
        super().closeEvent(event)


# ── pdf viewer dialog ─────────────────────────────────────────────────────────

class PdfViewerDialog(QDialog):
    _ZOOM_STEP = 1.25

    def __init__(self, parent, path: str):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(path))
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)
        self._zoom = 1.0
        self._build_ui(path)
        self.resize(800, 960)

    def _build_ui(self, path: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._doc = QPdfDocument(self)
        self._doc.load(path)

        self._view = QPdfView(self)
        self._view.setDocument(self._doc)
        self._view.setPageMode(QPdfView.PageMode.MultiPage)
        self._view.setZoomMode(QPdfView.ZoomMode.Custom)
        self._view.setZoomFactor(self._zoom)
        layout.addWidget(self._view)

        bar = QHBoxLayout()
        bar.addStretch()
        zoom_out = QPushButton("−")
        zoom_out.setFixedWidth(28)
        zoom_out.clicked.connect(self._zoom_out)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setFixedWidth(52)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_in = QPushButton("+")
        zoom_in.setFixedWidth(28)
        zoom_in.clicked.connect(self._zoom_in)
        bar.addWidget(zoom_out)
        bar.addWidget(self._zoom_label)
        bar.addWidget(zoom_in)
        layout.addLayout(bar)

    def _zoom_in(self):
        self._set_zoom(self._zoom * self._ZOOM_STEP)

    def _zoom_out(self):
        self._set_zoom(self._zoom / self._ZOOM_STEP)

    def _set_zoom(self, factor: float):
        self._zoom = max(0.1, min(factor, 5.0))
        self._view.setZoomFactor(self._zoom)
        self._zoom_label.setText(f"{round(self._zoom * 100)}%")


# ── add image dialog ─────────────────────────────────────────────────────────

class AddImageDialog(QDialog):
    def __init__(self, parent, resources_folder: str):
        super().__init__(parent)
        self.setWindowTitle("Add Vehicle Image")
        self.setMinimumWidth(500)
        self._resources_folder = resources_folder
        self._source_path = ""
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        src_row = QHBoxLayout()
        self._src_edit = QLineEdit()
        self._src_edit.setReadOnly(True)
        self._src_edit.setPlaceholderText("No file selected")
        src_row.addWidget(self._src_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_source)
        src_row.addWidget(browse_btn)
        layout.addRow("Image File *:", src_row)

        self._folder_combo = QComboBox()
        self._folder_combo.setEditable(True)
        self._folder_combo.lineEdit().setPlaceholderText("Resources root  (type a name to create a subfolder)")
        self._populate_folders()
        layout.addRow("Folder:", self._folder_combo)

        self._filename_edit = QLineEdit()
        self._filename_edit.setPlaceholderText("Auto-filled when image is selected")
        layout.addRow("Filename *:", self._filename_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _populate_folders(self):
        self._folder_combo.clear()
        self._folder_combo.addItem("")
        try:
            for entry in sorted(os.scandir(self._resources_folder), key=lambda e: e.name.lower()):
                if entry.is_dir():
                    self._folder_combo.addItem(entry.name)
        except OSError:
            pass

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)",
        )
        if path:
            self._source_path = path
            self._src_edit.setText(path)
            self._filename_edit.setText(os.path.basename(path))

    def _validate_and_accept(self):
        if not self._source_path:
            QMessageBox.warning(self, "Required", "Please select an image file.")
            return
        if not self._filename_edit.text().strip():
            QMessageBox.warning(self, "Required", "Please enter a filename.")
            return
        self.accept()

    def get_destination_path(self) -> str:
        dest_dir = self._resources_folder
        subfolder = self._folder_combo.currentText().strip()
        if subfolder:
            dest_dir = os.path.join(dest_dir, subfolder)
            os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, self._filename_edit.text().strip())
        if os.path.abspath(dest_path) != os.path.abspath(self._source_path):
            shutil.copy2(self._source_path, dest_path)
        return dest_path


_ATTACHMENT_FILTER = (
    "All Supported (*.png *.jpg *.jpeg *.gif *.bmp *.webp "
    "*.mp4 *.avi *.mov *.mkv *.wmv *.m4v *.webm *.mpeg *.mpg *.pdf);;"
    "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;"
    "Videos (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v *.webm *.mpeg *.mpg);;"
    "PDF Documents (*.pdf)"
)


class AddAttachmentDialog(AddImageDialog):
    """Like AddImageDialog but accepts images, videos, and PDFs."""

    def __init__(self, parent, resources_folder: str):
        super().__init__(parent, resources_folder)
        self.setWindowTitle("Add Attachment")

    def _build_ui(self):
        super()._build_ui()
        layout = self.layout()
        for i in range(layout.rowCount()):
            label = layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            if label and label.widget() and label.widget().text() == "Image File *:":
                label.widget().setText("Select File *:")
                break

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Attachment", "", _ATTACHMENT_FILTER,
        )
        if path:
            self._source_path = path
            self._src_edit.setText(path)
            self._filename_edit.setText(os.path.basename(path))


# ── garage tab ──────────────────────────────────────────────────────────────

class GarageTab(QWidget):
    def __init__(self, db: DatabaseManager, on_vehicle_changed, get_unit, get_resources_folder):
        super().__init__()
        self.db = db
        self.on_vehicle_changed = on_vehicle_changed
        self.get_unit = get_unit
        self.get_resources_folder = get_resources_folder
        self._vehicle_ids:  list[int] = []
        self._image_ids:    list[int] = []
        self._image_paths:  list[str] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        btn_row = QHBoxLayout()
        for label, slot in [
            ("Add Vehicle", self._add_vehicle),
            ("Edit",        self._edit_vehicle),
            ("Delete",      self._delete_vehicle),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_vehicle)
        self.table.currentCellChanged.connect(lambda row, *_: self._row_changed(row))
        layout.addWidget(self.table)

        # images section
        img_hdr = QHBoxLayout()
        img_hdr.addWidget(QLabel("Images:"))
        img_hdr.addStretch()
        for label, slot in [
            ("Add Image", self._add_image),
            ("Remove",    self._remove_image),
            ("Open",      self._open_image),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            img_hdr.addWidget(btn)
        layout.addLayout(img_hdr)

        self._image_list = QListWidget()
        self._image_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._image_list.setIconSize(QSize(100, 75))
        self._image_list.setFixedHeight(130)
        self._image_list.setFlow(QListWidget.Flow.LeftToRight)
        self._image_list.setWrapping(False)
        self._image_list.setSpacing(4)
        self._image_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._image_list.doubleClicked.connect(self._open_image)
        layout.addWidget(self._image_list)

    def refresh(self):
        unit = self.get_unit()
        self.table.setHorizontalHeaderLabels([
            "Nickname / Name", "Year", "Make", "Model", "Trim", "Color",
            "Plate", f"Odometer ({unit})", "Odometer Date",
        ])

        vehicles          = self.db.get_all_vehicles()
        self._vehicle_ids = [v["id"] for v in vehicles]
        self.table.setRowCount(len(vehicles))

        for row, v in enumerate(vehicles):
            display_name = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            cells = [
                display_name, str(v["year"]), v["make"], v["model"],
                v["trim"] or "", v["color"] or "", v["license_plate"] or "",
                f"{km_to_unit(v['current_mileage'], unit):,}", v["odometer_reading_date"] or "",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 7:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)

        self._load_images(self.selected_id())

    def _row_changed(self, row):
        vid = self._vehicle_ids[row] if row >= 0 else None
        self.on_vehicle_changed(vid)
        self._load_images(vid)

    def selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._vehicle_ids[row] if row >= 0 else None

    def _add_vehicle(self):
        dlg = VehicleDialog(self, unit=self.get_unit())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.add_vehicle(dlg.get_data())
            self.refresh()

    def _edit_vehicle(self):
        vid = self.selected_id()
        if vid is None:
            return
        dlg = VehicleDialog(self, self.db.get_vehicle(vid), unit=self.get_unit())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_vehicle(vid, dlg.get_data())
            self.refresh()

    def _delete_vehicle(self):
        vid = self.selected_id()
        if vid is None:
            return
        v    = self.db.get_vehicle(vid)
        name = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
        if QMessageBox.question(
            self, "Delete Vehicle", f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_vehicle(vid)
            self.refresh()

    def _load_images(self, vehicle_id: int | None):
        self._image_ids   = []
        self._image_paths = []
        self._image_list.clear()
        if vehicle_id is None:
            return
        images = self.db.get_vehicle_images(vehicle_id)
        self._image_ids   = [img["id"]   for img in images]
        self._image_paths = [img["path"] for img in images]
        for path in self._image_paths:
            pix = QPixmap(path)
            if pix.isNull():
                icon = QIcon()
            else:
                icon = QIcon(pix.scaled(
                    100, 75,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            self._image_list.addItem(QListWidgetItem(icon, os.path.basename(path)))

    def _add_image(self):
        resources_folder = self.get_resources_folder()
        if not resources_folder:
            QMessageBox.warning(
                self, "No Resources Folder",
                "Please set a Resources Folder in Settings before adding images.",
            )
            return
        vid = self.selected_id()
        if vid is None:
            QMessageBox.information(self, "No Vehicle Selected", "Select a vehicle before adding an image.")
            return
        dlg = AddImageDialog(self, resources_folder)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save image:\n{e}")
                return
            self.db.add_vehicle_image(vid, dest)
            self._load_images(vid)

    def _remove_image(self):
        row = self._image_list.currentRow()
        if row < 0 or row >= len(self._image_ids):
            return
        path = self._image_paths[row]
        if QMessageBox.question(
            self, "Remove Image",
            f"Delete '{os.path.basename(path)}' from the Resources folder and remove it from this vehicle?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_vehicle_image(self._image_ids[row])
            try:
                os.remove(path)
            except OSError:
                pass
            self._load_images(self.selected_id())

    def _open_image(self):
        row = self._image_list.currentRow()
        if row < 0 or not self._image_paths:
            return
        ImageViewerDialog(self, self._image_paths, row).exec()


# ── schedule tab ─────────────────────────────────────────────────────────────

class ScheduleTab(QWidget):
    def __init__(self, db: DatabaseManager, get_unit, on_service_logged, get_resources_folder):
        super().__init__()
        self.db                    = db
        self.get_unit              = get_unit
        self._on_service_logged    = on_service_logged
        self._get_resources_folder = get_resources_folder
        self._vehicle_id:   int | None = None
        self._item_ids:     list[int]  = []
        self._last_entries: list       = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel("Select a vehicle in the Garage tab to view its schedule.")
        top_row.addWidget(self.vehicle_label)
        top_row.addStretch()
        self.log_btn = QPushButton("Log Service")
        self.log_btn.setEnabled(False)
        self.log_btn.clicked.connect(self._log_service)
        top_row.addWidget(self.log_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_or_log_selected)
        layout.addWidget(self.table)

    def set_vehicle(self, vehicle_id: int | None):
        self._vehicle_id = vehicle_id
        self.refresh()

    def refresh(self):
        unit = self.get_unit()
        self.table.setHorizontalHeaderLabels([
            "Service", "Interval", "Last Done",
            f"At ({unit})", f"Next ({unit})", "Next (date)", "Status",
        ])

        if self._vehicle_id is None:
            self.table.setRowCount(0)
            self._item_ids = []
            self.log_btn.setEnabled(False)
            self.vehicle_label.setText("Select a vehicle in the Garage tab to view its schedule.")
            return

        vehicle = self.db.get_vehicle(self._vehicle_id)
        name    = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(
            f"<b>{name}</b> &nbsp;·&nbsp; Odometer: {km_to_unit(vehicle['current_mileage'], unit):,} {unit}"
        )
        self.log_btn.setEnabled(True)

        rows               = self.db.get_schedule(self._vehicle_id)
        self._item_ids     = [item["id"] for item, _, _ in rows]
        self._last_entries = [last for _, last, _ in rows]
        self.table.setRowCount(len(rows))

        for row, (item, last, v) in enumerate(rows):
            interval_parts = []
            if item["interval_miles"]:
                interval_parts.append(f"{km_to_unit(item['interval_miles'], unit):,} {unit}")
            if item["interval_months"]:
                interval_parts.append(f"{item['interval_months']} mo")
            interval_str = " / ".join(interval_parts) if interval_parts else "—"

            status, next_dist, next_date = compute_status(item, last, v)

            last_done     = last["service_date"] if last else "Never"
            at_dist       = f"{km_to_unit(last['mileage_at_service'], unit):,}" if last and last["mileage_at_service"] else "—"
            next_dist_str = f"{km_to_unit(next_dist, unit):,}" if next_dist is not None else "—"
            next_date_str = next_date.isoformat() if next_date else "—"

            color = STATUS_COLORS[status]
            cells = [item["name"], interval_str, last_done, at_dist, next_dist_str, next_date_str, status]

            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col in (3, 4):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 6:
                    cell.setForeground(QBrush(color))
                self.table.setItem(row, col, cell)

    def _selected_item_id(self) -> int | None:
        row = self.table.currentRow()
        return self._item_ids[row] if row >= 0 else None

    def _log_service(self):
        dlg = LogServiceDialog(
            self,
            self.db,
            self.db.get_all_vehicles(),
            vehicle_id=self._vehicle_id,
            item_id=self._selected_item_id(),
            unit=self.get_unit(),
            get_resources_folder=self._get_resources_folder,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry_id = self.db.log_service(dlg.get_data())
            for path in dlg.get_staged_images():
                self.db.add_service_log_image(entry_id, path, _get_file_type(path))
            self.db.set_service_log_parts(entry_id, dlg.get_parts_data())
            self._on_service_logged()

    def _edit_or_log_selected(self):
        row = self.table.currentRow()
        if row < 0 or self._vehicle_id is None:
            return
        last = self._last_entries[row] if row < len(self._last_entries) else None
        if last is None:
            self._log_service()
            return
        entry = self.db.get_service_log_entry(last["id"])
        dlg = LogServiceDialog(
            self,
            self.db,
            self.db.get_all_vehicles(),
            unit=self.get_unit(),
            get_resources_folder=self._get_resources_folder,
            entry=entry,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_service_log(last["id"], dlg.get_data())
            for img in dlg.get_removed_images():
                self.db.delete_service_log_image(img["id"])
                try:
                    os.remove(img["path"])
                except OSError:
                    pass
            for path in dlg.get_staged_images():
                self.db.add_service_log_image(last["id"], path, _get_file_type(path))
            self.db.set_service_log_parts(last["id"], dlg.get_parts_data())
            self._on_service_logged()


# ── services tab ─────────────────────────────────────────────────────────────

class ServicesTab(QWidget):
    def __init__(self, db: DatabaseManager, get_unit, get_resources_folder=None):
        super().__init__()
        self.db                    = db
        self.get_unit              = get_unit
        self.get_resources_folder  = get_resources_folder
        self._vehicle_id: int | None = None
        self._item_ids:   list[int]  = []
        self._file_ids:   list[int]  = []
        self._file_paths: list[str]  = []
        self._file_types: list[str]  = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel("Select a vehicle in the Garage tab to manage its services.")
        top_row.addWidget(self.vehicle_label)
        top_row.addStretch()
        for label, slot in [
            ("Add Service", self._add_item),
            ("Edit",        self._edit_item),
            ("Delete",      self._delete_item),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            top_row.addWidget(btn)
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_item)
        self.table.currentCellChanged.connect(lambda row, *_: self._row_changed(row))
        layout.addWidget(self.table)

        att_hdr = QHBoxLayout()
        att_hdr.addWidget(QLabel("Attachments:"))
        att_hdr.addStretch()
        for label, slot in [
            ("Add",    self._add_attachment),
            ("Remove", self._remove_attachment),
            ("Open",   self._open_attachment),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            att_hdr.addWidget(btn)
        layout.addLayout(att_hdr)

        self._file_list = QListWidget()
        self._file_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._file_list.setIconSize(QSize(100, 75))
        self._file_list.setFixedHeight(130)
        self._file_list.setFlow(QListWidget.Flow.LeftToRight)
        self._file_list.setWrapping(False)
        self._file_list.setSpacing(4)
        self._file_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._file_list.doubleClicked.connect(self._open_attachment)
        layout.addWidget(self._file_list)

    def set_vehicle(self, vehicle_id: int | None):
        self._vehicle_id = vehicle_id
        self.refresh()

    def refresh(self):
        unit = self.get_unit()
        self.table.setHorizontalHeaderLabels([
            "Service Name", f"Distance Interval ({unit})", "Time Interval (months)",
        ])

        if self._vehicle_id is None:
            self.table.setRowCount(0)
            self._item_ids = []
            self.vehicle_label.setText("Select a vehicle in the Garage tab to manage its services.")
            self._load_files(None)
            return

        vehicle = self.db.get_vehicle(self._vehicle_id)
        name    = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(f"<b>{name}</b>")

        items          = self.db.get_maintenance_items(self._vehicle_id)
        self._item_ids = [item["id"] for item in items]
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            dist_str  = f"{km_to_unit(item['interval_miles'], unit):,}" if item["interval_miles"] else "—"
            month_str = str(item["interval_months"])  if item["interval_months"] else "—"
            for col, text in enumerate([item["name"], dist_str, month_str]):
                cell = QTableWidgetItem(text)
                if col in (1, 2):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

        self._load_files(self._selected_id())

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._item_ids[row] if 0 <= row < len(self._item_ids) else None

    def _row_changed(self, row):
        self._load_files(self._item_ids[row] if 0 <= row < len(self._item_ids) else None)

    def _load_files(self, item_id: int | None):
        self._file_ids   = []
        self._file_paths = []
        self._file_types = []
        self._file_list.clear()
        if item_id is None:
            return
        for f in self.db.get_maintenance_item_files(item_id):
            self._file_ids.append(f["id"])
            self._file_paths.append(f["path"])
            self._file_types.append(f["file_type"])
            if f["file_type"] == "image":
                pix  = QPixmap(f["path"])
                icon = QIcon(pix.scaled(100, 75, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)) if not pix.isNull() else QIcon()
            else:
                icon = QIcon()
            self._file_list.addItem(QListWidgetItem(icon, os.path.basename(f["path"])))

    def _add_attachment(self):
        rf = self.get_resources_folder() if self.get_resources_folder else ""
        if not rf:
            QMessageBox.warning(
                self, "No Resources Folder",
                "Please set a Resources Folder in Settings before adding attachments.",
            )
            return
        iid = self._selected_id()
        if iid is None:
            QMessageBox.information(self, "No Service Selected", "Select a service before adding an attachment.")
            return
        dlg = AddAttachmentDialog(self, rf)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save attachment:\n{e}")
                return
            self.db.add_maintenance_item_file(iid, dest, _get_file_type(dest))
            self._load_files(iid)

    def _remove_attachment(self):
        row = self._file_list.currentRow()
        if row < 0 or row >= len(self._file_ids):
            return
        path = self._file_paths[row]
        if QMessageBox.question(
            self, "Remove Attachment",
            f"Delete '{os.path.basename(path)}' from the Resources folder and remove it from this service?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_maintenance_item_file(self._file_ids[row])
            try:
                os.remove(path)
            except OSError:
                pass
            self._load_files(self._selected_id())

    def _open_attachment(self):
        row = self._file_list.currentRow()
        if row < 0 or row >= len(self._file_paths):
            return
        path = self._file_paths[row]
        ft   = self._file_types[row] if row < len(self._file_types) else _get_file_type(path)
        if ft == "image":
            image_paths = [p for p, t in zip(self._file_paths, self._file_types) if t == "image"]
            img_row     = self._file_types[:row].count("image")
            ImageViewerDialog(self, image_paths, img_row).exec()
        elif ft == "video":
            if _HAS_MULTIMEDIA:
                VideoViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif ft == "pdf":
            if _HAS_PDF:
                PdfViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _add_item(self):
        if self._vehicle_id is None:
            return
        dlg = MaintenanceItemDialog(self, unit=self.get_unit(),
                                    db=self.db,
                                    get_resources_folder=self.get_resources_folder,
                                    vehicle_id=self._vehicle_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            item_id = self.db.add_maintenance_item(self._vehicle_id, dlg.get_data())
            for path in dlg.get_staged_files():
                self.db.add_maintenance_item_file(item_id, path, _get_file_type(path))
            self.db.set_maintenance_item_parts(item_id, dlg.get_parts_data())
            self.refresh()

    def _edit_item(self):
        iid = self._selected_id()
        if iid is None:
            return
        items = {item["id"]: item for item in self.db.get_maintenance_items(self._vehicle_id)}
        dlg = MaintenanceItemDialog(self, items[iid], unit=self.get_unit(),
                                    db=self.db,
                                    get_resources_folder=self.get_resources_folder,
                                    vehicle_id=self._vehicle_id)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_maintenance_item(iid, dlg.get_data())
            for f in dlg.get_removed_files():
                self.db.delete_maintenance_item_file(f["id"])
                try:
                    os.remove(f["path"])
                except OSError:
                    pass
            for path in dlg.get_staged_files():
                self.db.add_maintenance_item_file(iid, path, _get_file_type(path))
            self.db.set_maintenance_item_parts(iid, dlg.get_parts_data())
            self.refresh()

    def _delete_item(self):
        iid = self._selected_id()
        if iid is None:
            return
        items     = {item["id"]: item for item in self.db.get_maintenance_items(self._vehicle_id)}
        name      = items[iid]["name"]
        log_count = self.db.get_service_log_count_for_item(iid)

        msg = f"Delete '{name}'?"
        if log_count:
            msg += f"\n\nThis will also delete {log_count} service log record{'s' if log_count != 1 else ''}."

        if QMessageBox.question(
            self, "Delete Service", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_maintenance_item(iid)
            self.refresh()


# ── service log tab ──────────────────────────────────────────────────────────

class ServiceLogTab(QWidget):
    def __init__(self, db: DatabaseManager, get_unit, get_resources_folder, on_service_logged):
        super().__init__()
        self.db = db
        self.get_unit = get_unit
        self.get_resources_folder = get_resources_folder
        self._on_service_logged = on_service_logged
        self._vehicle_id:  int | None = None
        self._log_ids:     list[int]  = []
        self._image_ids:   list[int]  = []
        self._image_paths: list[str]  = []
        self._file_types:  list[str]  = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel("Select a vehicle in the Garage tab to view its service log.")
        top_row.addWidget(self.vehicle_label)
        top_row.addStretch()
        edit_btn = QPushButton("Edit Entry")
        edit_btn.clicked.connect(self._edit_entry)
        top_row.addWidget(edit_btn)
        log_btn = QPushButton("Log Service")
        log_btn.clicked.connect(self._log_service)
        top_row.addWidget(log_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(lambda row, *_: self._row_changed(row))
        self.table.doubleClicked.connect(self._edit_entry)
        layout.addWidget(self.table)

        img_hdr = QHBoxLayout()
        img_hdr.addWidget(QLabel("Attachments:"))
        img_hdr.addStretch()
        for label, slot in [
            ("Add",    self._add_attachment),
            ("Remove", self._remove_attachment),
            ("Open",   self._open_attachment),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            img_hdr.addWidget(btn)
        layout.addLayout(img_hdr)

        self._image_list = QListWidget()
        self._image_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._image_list.setIconSize(QSize(100, 75))
        self._image_list.setFixedHeight(130)
        self._image_list.setFlow(QListWidget.Flow.LeftToRight)
        self._image_list.setWrapping(False)
        self._image_list.setSpacing(4)
        self._image_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._image_list.doubleClicked.connect(self._open_attachment)
        layout.addWidget(self._image_list)

    def set_vehicle(self, vehicle_id: int | None):
        self._vehicle_id = vehicle_id
        self.refresh()

    def refresh(self):
        unit = self.get_unit()
        self.table.setHorizontalHeaderLabels([
            "Service", "Date", f"Odometer ({unit})", "Cost", "Shop",
        ])

        if self._vehicle_id is None:
            self.table.setRowCount(0)
            self._log_ids = []
            self.vehicle_label.setText("Select a vehicle in the Garage tab to view its service log.")
            self._load_images(None)
            return

        vehicle = self.db.get_vehicle(self._vehicle_id)
        name = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(f"<b>{name}</b>")

        entries = self.db.get_service_log_entries(self._vehicle_id)
        self._log_ids = [e["id"] for e in entries]
        self.table.setRowCount(len(entries))

        for row, e in enumerate(entries):
            dist_str = f"{km_to_unit(e['mileage_at_service'], unit):,}" if e["mileage_at_service"] else "—"
            cost_str = f"${e['cost']:.2f}" if e["cost"] else "—"
            for col, text in enumerate([
                e["service_name"], e["service_date"], dist_str, cost_str, e["shop"] or "—",
            ]):
                cell = QTableWidgetItem(text)
                if col in (2, 3):
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

        self._load_images(self._selected_log_id())

    def _selected_log_id(self) -> int | None:
        row = self.table.currentRow()
        return self._log_ids[row] if 0 <= row < len(self._log_ids) else None

    def _row_changed(self, row):
        self._load_images(self._log_ids[row] if 0 <= row < len(self._log_ids) else None)

    def _load_images(self, log_id: int | None):
        self._image_ids   = []
        self._image_paths = []
        self._file_types  = []
        self._image_list.clear()
        if log_id is None:
            return
        attachments = self.db.get_service_log_images(log_id)
        self._image_ids   = [a["id"]        for a in attachments]
        self._image_paths = [a["path"]       for a in attachments]
        self._file_types  = [a["file_type"]  for a in attachments]
        for path, ft in zip(self._image_paths, self._file_types):
            if ft == "image":
                pix  = QPixmap(path)
                icon = QIcon(pix.scaled(
                    100, 75,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )) if not pix.isNull() else QIcon()
            else:
                icon = QIcon()
            self._image_list.addItem(QListWidgetItem(icon, os.path.basename(path)))

    def _add_attachment(self):
        resources_folder = self.get_resources_folder()
        if not resources_folder:
            QMessageBox.warning(
                self, "No Resources Folder",
                "Please set a Resources Folder in Settings before adding attachments.",
            )
            return
        lid = self._selected_log_id()
        if lid is None:
            QMessageBox.information(self, "No Entry Selected", "Select a service log entry before adding an attachment.")
            return
        dlg = AddAttachmentDialog(self, resources_folder)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save attachment:\n{e}")
                return
            self.db.add_service_log_image(lid, dest, _get_file_type(dest))
            self._load_images(lid)

    def _remove_attachment(self):
        row = self._image_list.currentRow()
        if row < 0 or row >= len(self._image_ids):
            return
        path = self._image_paths[row]
        if QMessageBox.question(
            self, "Remove Attachment",
            f"Delete '{os.path.basename(path)}' from the Resources folder and remove it from this entry?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_service_log_image(self._image_ids[row])
            try:
                os.remove(path)
            except OSError:
                pass
            self._load_images(self._selected_log_id())

    def _open_attachment(self):
        row = self._image_list.currentRow()
        if row < 0 or row >= len(self._image_paths):
            return
        path = self._image_paths[row]
        ft   = self._file_types[row] if row < len(self._file_types) else _get_file_type(path)
        if ft == "image":
            image_paths = [p for p, t in zip(self._image_paths, self._file_types) if t == "image"]
            img_row     = self._file_types[:row].count("image")
            ImageViewerDialog(self, image_paths, img_row).exec()
        elif ft == "video":
            if _HAS_MULTIMEDIA:
                VideoViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif ft == "pdf":
            if _HAS_PDF:
                PdfViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _edit_entry(self):
        lid = self._selected_log_id()
        if lid is None:
            return
        entry = self.db.get_service_log_entry(lid)
        dlg = LogServiceDialog(
            self,
            self.db,
            self.db.get_all_vehicles(),
            vehicle_id=self._vehicle_id,
            unit=self.get_unit(),
            get_resources_folder=self.get_resources_folder,
            entry=entry,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_service_log(lid, dlg.get_data())
            for img in dlg.get_removed_images():
                self.db.delete_service_log_image(img["id"])
                try:
                    os.remove(img["path"])
                except OSError:
                    pass
            for path in dlg.get_staged_images():
                self.db.add_service_log_image(lid, path, _get_file_type(path))
            self.db.set_service_log_parts(lid, dlg.get_parts_data())
            self._on_service_logged()

    def _log_service(self):
        dlg = LogServiceDialog(
            self,
            self.db,
            self.db.get_all_vehicles(),
            vehicle_id=self._vehicle_id,
            unit=self.get_unit(),
            get_resources_folder=self.get_resources_folder,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry_id = self.db.log_service(dlg.get_data())
            for path in dlg.get_staged_images():
                self.db.add_service_log_image(entry_id, path, _get_file_type(path))
            self.db.set_service_log_parts(entry_id, dlg.get_parts_data())
            self._on_service_logged()


# ── parts tab ────────────────────────────────────────────────────────────────

class PartDialog(QDialog):
    def __init__(self, parent=None, part=None, vehicles=None, default_vehicle_id=None,
                 db=None, get_resources_folder=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Part" if part else "Add Part")
        self.setMinimumWidth(460)
        self._db                   = db
        self._get_resources_folder = get_resources_folder
        self._staged_images: list[str]   = []
        self._removed_images: list[dict] = []
        self._build_ui(part, vehicles or [], default_vehicle_id)
        if part and db:
            for img in db.get_part_images(part["id"]):
                ft = img["file_type"] if "file_type" in img.keys() else "image"
                self._add_image_item("existing", img["id"], img["path"], ft)

    def _build_ui(self, part, vehicles, default_vehicle_id):
        layout = QFormLayout(self)

        self.vehicle_combo = QComboBox()
        for v in vehicles:
            label = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            self.vehicle_combo.addItem(label, v["id"])
        vid = part["vehicle_id"] if part else default_vehicle_id
        if vid is not None:
            idx = next((i for i in range(self.vehicle_combo.count())
                        if self.vehicle_combo.itemData(i) == vid), 0)
            self.vehicle_combo.setCurrentIndex(idx)

        def val(field):
            return (part[field] or "") if part else ""

        self.name            = QLineEdit(val("name"))
        self.part_number     = QLineEdit(val("part_number"))
        self.alt_part_number = QLineEdit(val("alt_part_number"))
        self.supplier        = QLineEdit(val("supplier"))
        self.url             = QLineEdit(val("url"))
        self.price           = QDoubleSpinBox()
        self.price.setRange(0, 99_999)
        self.price.setPrefix("$")
        self.price.setDecimals(2)
        self.price.setValue(part["price"] or 0 if part else 0)
        self.notes           = QTextEdit(val("notes"))
        self.notes.setFixedHeight(60)

        layout.addRow("Vehicle *:",       self.vehicle_combo)
        layout.addRow("Part Name *:",     self.name)
        layout.addRow("Part Number:",     self.part_number)
        layout.addRow("Alt Part Number:", self.alt_part_number)
        layout.addRow("Supplier:",        self.supplier)
        layout.addRow("URL:",             self.url)
        layout.addRow("Price:",           self.price)
        layout.addRow("Notes:",           self.notes)

        img_container = QWidget()
        img_vbox = QVBoxLayout(img_container)
        img_vbox.setContentsMargins(0, 4, 0, 0)
        img_vbox.setSpacing(4)

        att_hdr = QHBoxLayout()
        att_hdr.addWidget(QLabel("Images:"))
        att_hdr.addStretch()
        for label, slot in [
            ("Add",    self._add_staged_image),
            ("Remove", self._remove_staged_image),
            ("Open",   self._open_attachment),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            att_hdr.addWidget(btn)
        img_vbox.addLayout(att_hdr)

        self._staged_list = QListWidget()
        self._staged_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._staged_list.setIconSize(QSize(80, 60))
        self._staged_list.setFixedHeight(100)
        self._staged_list.setFlow(QListWidget.Flow.LeftToRight)
        self._staged_list.setWrapping(False)
        self._staged_list.setSpacing(4)
        self._staged_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._staged_list.doubleClicked.connect(self._open_attachment)
        img_vbox.addWidget(self._staged_list)

        layout.addRow(img_container)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _add_image_item(self, img_type: str, img_id, path: str, file_type: str = 'image'):
        if file_type == 'image':
            pix  = QPixmap(path)
            icon = QIcon(pix.scaled(80, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)) if not pix.isNull() else QIcon()
        else:
            icon = QIcon()
        item = QListWidgetItem(icon, os.path.basename(path))
        item.setData(Qt.ItemDataRole.UserRole,
                     {"type": img_type, "id": img_id, "path": path, "file_type": file_type})
        self._staged_list.addItem(item)

    def _add_staged_image(self):
        rf = self._get_resources_folder() if self._get_resources_folder else ""
        if not rf:
            QMessageBox.warning(
                self, "No Resources Folder",
                "Please set a Resources Folder in Settings before adding images.",
            )
            return
        dlg = AddAttachmentDialog(self, rf)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not save attachment:\n{e}")
                return
            ft = _get_file_type(dest)
            self._staged_images.append(dest)
            self._add_image_item("staged", None, dest, ft)

    def _remove_staged_image(self):
        row = self._staged_list.currentRow()
        if row < 0:
            return
        meta = self._staged_list.item(row).data(Qt.ItemDataRole.UserRole)
        if meta and meta["type"] == "existing":
            self._removed_images.append(meta)
        else:
            path = meta["path"] if meta else None
            if path and path in self._staged_images:
                self._staged_images.remove(path)
            try:
                if path:
                    os.remove(path)
            except OSError:
                pass
        self._staged_list.takeItem(row)

    def _open_attachment(self):
        row = self._staged_list.currentRow()
        if row < 0:
            return
        meta = self._staged_list.item(row).data(Qt.ItemDataRole.UserRole)
        if not meta:
            return
        path = meta["path"]
        ft   = meta.get("file_type") or _get_file_type(path)
        if ft == "image":
            image_paths = []
            img_row = 0
            for i in range(self._staged_list.count()):
                m = self._staged_list.item(i).data(Qt.ItemDataRole.UserRole)
                if m and m.get("file_type", "image") == "image":
                    if m["path"] == path:
                        img_row = len(image_paths)
                    image_paths.append(m["path"])
            ImageViewerDialog(self, image_paths, img_row).exec()
        elif ft == "video":
            if _HAS_MULTIMEDIA:
                VideoViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif ft == "pdf":
            if _HAS_PDF:
                PdfViewerDialog(self, path).exec()
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def reject(self):
        for path in self._staged_images:
            try:
                os.remove(path)
            except OSError:
                pass
        self._staged_images.clear()
        super().reject()

    def get_staged_images(self) -> list[str]:
        images = list(self._staged_images)
        self._staged_images.clear()
        return images

    def get_removed_images(self) -> list[dict]:
        removed = list(self._removed_images)
        self._removed_images.clear()
        return removed

    def _validate_and_accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Required", "Part name is required.")
            return
        self.accept()

    def get_data(self):
        return {
            "vehicle_id":      self.vehicle_combo.currentData(),
            "name":            self.name.text().strip(),
            "part_number":     self.part_number.text().strip() or None,
            "alt_part_number": self.alt_part_number.text().strip() or None,
            "supplier":        self.supplier.text().strip() or None,
            "url":             self.url.text().strip() or None,
            "price":           self.price.value() or None,
            "notes":           self.notes.toPlainText().strip() or None,
        }


PARTS_COLUMNS = ["Part Name", "Part #", "Alt Part #", "Supplier", "Price", "URL"]


class PartsTab(QWidget):
    def __init__(self, db: DatabaseManager, get_resources_folder=None):
        super().__init__()
        self.db = db
        self.get_resources_folder = get_resources_folder
        self._vehicle_id: int | None = None
        self._part_ids:   list[int]  = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel("Select a vehicle in the Garage tab to view its parts.")
        top_row.addWidget(self.vehicle_label)
        top_row.addStretch()

        for label, slot in [
            ("Add Part",  self._add_part),
            ("Edit",      self._edit_part),
            ("Delete",    self._delete_part),
            ("Open URL",  self._open_url),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            top_row.addWidget(btn)

        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(len(PARTS_COLUMNS))
        self.table.setHorizontalHeaderLabels(PARTS_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._edit_part)
        layout.addWidget(self.table)

    def set_vehicle(self, vehicle_id: int | None):
        self._vehicle_id = vehicle_id
        self.refresh()

    def refresh(self):
        if self._vehicle_id is None:
            self.table.setRowCount(0)
            self._part_ids = []
            self.vehicle_label.setText("Select a vehicle in the Garage tab to view its parts.")
            return
        vehicle = self.db.get_vehicle(self._vehicle_id)
        name    = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(f"<b>{name}</b>")
        self._load_parts()

    def _load_parts(self):
        parts          = self.db.get_all_parts(self._vehicle_id)
        self._part_ids = [p["id"] for p in parts]
        self.table.setRowCount(len(parts))

        for row, p in enumerate(parts):
            price_str = f"${p['price']:.2f}" if p["price"] else "—"
            cells = [
                p["name"],
                p["part_number"]     or "—",
                p["alt_part_number"] or "—",
                p["supplier"]        or "—",
                price_str,
                p["url"]             or "—",
            ]
            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col == 4:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._part_ids[row] if row >= 0 else None

    def _add_part(self):
        if self._vehicle_id is None:
            QMessageBox.information(self, "No Vehicle", "Select a vehicle in the Garage tab first.")
            return
        dlg = PartDialog(
            self,
            vehicles=self.db.get_all_vehicles(),
            default_vehicle_id=self._vehicle_id,
            db=self.db,
            get_resources_folder=self.get_resources_folder,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            part_id = self.db.add_part(dlg.get_data())
            for path in dlg.get_staged_images():
                self.db.add_part_image(part_id, path, _get_file_type(path))
            self.refresh()

    def _edit_part(self):
        pid = self._selected_id()
        if pid is None:
            return
        dlg = PartDialog(
            self,
            part=self.db.get_part(pid),
            vehicles=self.db.get_all_vehicles(),
            db=self.db,
            get_resources_folder=self.get_resources_folder,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_part(pid, dlg.get_data())
            for img in dlg.get_removed_images():
                self.db.delete_part_image(img["id"])
                try:
                    os.remove(img["path"])
                except OSError:
                    pass
            for path in dlg.get_staged_images():
                self.db.add_part_image(pid, path, _get_file_type(path))
            self._load_parts()

    def _delete_part(self):
        pid = self._selected_id()
        if pid is None:
            return
        part = self.db.get_part(pid)
        if QMessageBox.question(
            self, "Delete Part", f"Delete '{part['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_part(pid)
            self._load_parts()

    def _open_url(self):
        pid = self._selected_id()
        if pid is None:
            return
        url = self.db.get_part(pid)["url"]
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(self, "No URL", "No URL saved for this part.")


# ── settings tab ─────────────────────────────────────────────────────────────

class SettingsTab(QWidget):
    def __init__(self, apply_theme, apply_unit, save_resources_folder,
                 current_theme, current_unit, current_resources_folder):
        super().__init__()
        self._apply_theme          = apply_theme
        self._apply_unit           = apply_unit
        self._save_resources_folder = save_resources_folder
        self._build_ui(current_theme, current_unit, current_resources_folder)

    def _build_ui(self, current_theme, current_unit, current_resources_folder):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        # Theme
        theme_box    = QGroupBox("Theme")
        theme_layout = QVBoxLayout(theme_box)
        self._dark_btn  = QRadioButton("Dark")
        self._light_btn = QRadioButton("Light")
        self._theme_grp = QButtonGroup(self)
        self._theme_grp.addButton(self._dark_btn,  0)
        self._theme_grp.addButton(self._light_btn, 1)
        theme_layout.addWidget(self._dark_btn)
        theme_layout.addWidget(self._light_btn)
        (self._dark_btn if current_theme == "dark" else self._light_btn).setChecked(True)
        self._theme_grp.idClicked.connect(
            lambda bid: self._apply_theme("dark" if bid == 0 else "light")
        )
        outer.addWidget(theme_box)

        # Unit
        unit_box    = QGroupBox("Distance Unit")
        unit_layout = QVBoxLayout(unit_box)
        self._km_btn = QRadioButton("Kilometers (km)")
        self._mi_btn = QRadioButton("Miles (mi)")
        self._unit_grp = QButtonGroup(self)
        self._unit_grp.addButton(self._km_btn, 0)
        self._unit_grp.addButton(self._mi_btn, 1)
        unit_layout.addWidget(self._km_btn)
        unit_layout.addWidget(self._mi_btn)
        (self._km_btn if current_unit == "km" else self._mi_btn).setChecked(True)
        self._unit_grp.idClicked.connect(
            lambda bid: self._apply_unit("km" if bid == 0 else "mi")
        )
        outer.addWidget(unit_box)

        # Resources folder
        res_box    = QGroupBox("Resources Folder")
        res_layout = QVBoxLayout(res_box)
        path_row   = QHBoxLayout()
        self._res_path = QLineEdit(current_resources_folder or "")
        self._res_path.setReadOnly(True)
        self._res_path.setPlaceholderText("No folder selected")
        path_row.addWidget(self._res_path)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_resources)
        path_row.addWidget(browse_btn)
        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self._open_resources)
        path_row.addWidget(open_btn)
        res_layout.addLayout(path_row)
        outer.addWidget(res_box)

        outer.addStretch()

    def sync_theme(self, theme: str):
        (self._dark_btn if theme == "dark" else self._light_btn).setChecked(True)

    def sync_unit(self, unit: str):
        (self._km_btn if unit == "km" else self._mi_btn).setChecked(True)

    def _browse_resources(self):
        start = self._res_path.text() or ""
        folder = QFileDialog.getExistingDirectory(self, "Select Resources Folder", start)
        if folder:
            self._res_path.setText(folder)
            self._save_resources_folder(folder)

    def _open_resources(self):
        path = self._res_path.text()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.information(self, "No Folder", "No resources folder has been selected.")


# ── main window ──────────────────────────────────────────────────────────────

class VehicleApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db       = DatabaseManager()
        self.settings = QSettings("VehicleLog", "VehicleMaintenanceLog")
        self.setWindowTitle("Vehicle Maintenance Log")
        self.setMinimumSize(1000, 560)
        self._build_ui()
        self._apply_theme(self.settings.value("theme", "dark"))
        self._apply_unit(self.settings.value("unit", "km"))

    @property
    def unit(self) -> str:
        return self.settings.value("unit", "km")

    def _build_ui(self):
        self.tabs          = QTabWidget()
        self.garage_tab    = GarageTab(
            self.db, self._on_vehicle_selected,
            lambda: self.unit,
            lambda: self.settings.value("resources_folder", ""),
        )
        self.schedule_tab  = ScheduleTab(
            self.db, lambda: self.unit,
            self._on_service_logged,
            lambda: self.settings.value("resources_folder", ""),
        )
        self.log_tab       = ServiceLogTab(
            self.db,
            lambda: self.unit,
            lambda: self.settings.value("resources_folder", ""),
            self._on_service_logged,
        )
        self.services_tab  = ServicesTab(self.db, lambda: self.unit,
                                         lambda: self.settings.value("resources_folder", ""))
        self.parts_tab     = PartsTab(self.db, lambda: self.settings.value("resources_folder", ""))
        self.settings_tab  = SettingsTab(
            self._apply_theme, self._apply_unit,
            lambda path: self.settings.setValue("resources_folder", path),
            current_theme=self.settings.value("theme", "dark"),
            current_unit=self.settings.value("unit", "km"),
            current_resources_folder=self.settings.value("resources_folder", ""),
        )
        self.tabs.addTab(self.garage_tab,    "Garage")
        self.tabs.addTab(self.schedule_tab,  "Schedule")
        self.tabs.addTab(self.log_tab,       "Log")
        self.tabs.addTab(self.services_tab,  "Services")
        self.tabs.addTab(self.parts_tab,     "Parts")
        self.tabs.addTab(self.settings_tab,  "Settings")
        self.setCentralWidget(self.tabs)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status()

    def _apply_theme(self, theme: str):
        QApplication.instance().setPalette(dark_palette() if theme == "dark" else light_palette())
        self.settings.setValue("theme", theme)
        self.settings_tab.sync_theme(theme)

    def _apply_unit(self, unit: str):
        self.settings.setValue("unit", unit)
        self.settings_tab.sync_unit(unit)
        self.garage_tab.refresh()
        self.schedule_tab.refresh()
        self.log_tab.refresh()
        self.services_tab.refresh()

    def _on_service_logged(self):
        self.schedule_tab.refresh()
        self.log_tab.refresh()

    def _on_vehicle_selected(self, vehicle_id: int | None):
        self.schedule_tab.set_vehicle(vehicle_id)
        self.log_tab.set_vehicle(vehicle_id)
        self.services_tab.set_vehicle(vehicle_id)
        self.parts_tab.set_vehicle(vehicle_id)
        self._update_status()

    def _update_status(self):
        n = len(self.db.get_all_vehicles())
        self.status_bar.showMessage(f"{n} vehicle{'s' if n != 1 else ''}")

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VehicleApp()
    window.show()
    sys.exit(app.exec())
