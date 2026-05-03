import sys
import sqlite3
import calendar
from datetime import date
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout, QLineEdit,
    QSpinBox, QDoubleSpinBox, QTextEdit, QDialogButtonBox, QStatusBar,
    QMessageBox, QHeaderView, QTabWidget, QLabel, QComboBox, QPushButton,
    QDateEdit, QRadioButton, QButtonGroup, QGroupBox, QFileDialog,
)
from PySide6.QtCore import Qt, QDate, QSettings, QUrl
from PySide6.QtGui import QColor, QBrush, QPalette, QDesktopServices


# ── helpers ────────────────────────────────────────────────────────────────

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
                current_mileage INTEGER DEFAULT 0,
                notes           TEXT,
                date_added      TEXT DEFAULT (date('now'))
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
                price           REAL
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
                (nickname, year, make, model, trim, color, vin, license_plate, current_mileage, notes)
            VALUES
                (:nickname, :year, :make, :model, :trim, :color, :vin, :license_plate, :current_mileage, :notes)
        """, data)
        self.conn.commit()
        self._seed_vehicle_maintenance_items(cur.lastrowid)

    def update_vehicle(self, vehicle_id, data):
        self.conn.execute("""
            UPDATE vehicles
            SET nickname=:nickname, year=:year, make=:make, model=:model,
                trim=:trim, color=:color, vin=:vin, license_plate=:license_plate,
                current_mileage=:current_mileage, notes=:notes
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

    def add_maintenance_item(self, vehicle_id, data):
        max_order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM maintenance_items WHERE vehicle_id=?",
            (vehicle_id,),
        ).fetchone()[0]
        self.conn.execute(
            """INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order)
               VALUES (:vehicle_id, :name, :interval_miles, :interval_months, :sort_order)""",
            {**data, "vehicle_id": vehicle_id, "sort_order": max_order + 1},
        )
        self.conn.commit()

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

    def add_part(self, data):
        self.conn.execute("""
            INSERT INTO parts (vehicle_id, name, part_number, alt_part_number, supplier, url, price)
            VALUES (:vehicle_id, :name, :part_number, :alt_part_number, :supplier, :url, :price)
        """, data)
        self.conn.commit()

    def update_part(self, part_id, data):
        self.conn.execute("""
            UPDATE parts
            SET vehicle_id=:vehicle_id, name=:name, part_number=:part_number,
                alt_part_number=:alt_part_number, supplier=:supplier, url=:url, price=:price
            WHERE id=:id
        """, {**data, "id": part_id})
        self.conn.commit()

    def delete_part(self, part_id):
        self.conn.execute("DELETE FROM parts WHERE id=?", (part_id,))
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

    def log_service(self, data):
        self.conn.execute("""
            INSERT INTO service_log
                (vehicle_id, item_id, service_date, mileage_at_service, cost, shop, parts, notes)
            VALUES
                (:vehicle_id, :item_id, :service_date, :mileage_at_service, :cost, :shop, :parts, :notes)
        """, data)
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
        self.notes           = QTextEdit(val("notes"))
        self.notes.setFixedHeight(70)

        layout.addRow("Nickname:",            self.nickname)
        layout.addRow("Year *:",              self.year)
        layout.addRow("Make *:",              self.make)
        layout.addRow("Model *:",             self.model)
        layout.addRow("Trim:",                self.trim)
        layout.addRow("Color:",               self.color)
        layout.addRow("VIN:",                 self.vin)
        layout.addRow("License Plate:",       self.license_plate)
        layout.addRow(f"Odometer ({unit}):", self.current_mileage)
        layout.addRow("Notes:",               self.notes)

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
        return {
            "nickname":        self.nickname.text().strip() or None,
            "year":            self.year.value(),
            "make":            self.make.text().strip(),
            "model":           self.model.text().strip(),
            "trim":            self.trim.text().strip() or None,
            "color":           self.color.text().strip() or None,
            "vin":             self.vin.text().strip() or None,
            "license_plate":   self.license_plate.text().strip() or None,
            "current_mileage": unit_to_km(self.current_mileage.value(), self._unit),
            "notes":           self.notes.toPlainText().strip() or None,
        }


class LogServiceDialog(QDialog):
    def __init__(self, parent, db, vehicles, *, vehicle_id=None, item_id=None, unit="km"):
        super().__init__(parent)
        self.setWindowTitle("Log Service")
        self.setMinimumWidth(420)
        self._db   = db
        self._unit = unit
        self._preferred_item_id = item_id
        self._build_ui(vehicles, vehicle_id, unit)

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
        self.parts = QTextEdit()
        self.parts.setFixedHeight(60)
        self.parts.setPlaceholderText("Brand, part number, etc.")
        self.notes = QTextEdit()
        self.notes.setFixedHeight(60)

        layout.addRow("Vehicle:",               self.vehicle_combo)
        layout.addRow("Service:",               self.item_combo)
        layout.addRow("Date:",                  self.service_date)
        layout.addRow(f"Odometer ({unit}):",   self.mileage)
        layout.addRow("Cost:",                  self.cost)
        layout.addRow("Shop:",                  self.shop)
        layout.addRow("Parts:",                 self.parts)
        layout.addRow("Notes:",                 self.notes)

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

    def get_data(self):
        return {
            "vehicle_id":         self.vehicle_combo.currentData(),
            "item_id":            self.item_combo.currentData(),
            "service_date":       self.service_date.date().toString("yyyy-MM-dd"),
            "mileage_at_service": unit_to_km(self.mileage.value(), self._unit) or None,
            "cost":               self.cost.value() or None,
            "shop":               self.shop.text().strip() or None,
            "parts":              self.parts.toPlainText().strip() or None,
            "notes":              self.notes.toPlainText().strip() or None,
        }


class MaintenanceItemDialog(QDialog):
    def __init__(self, parent=None, item=None, unit="km"):
        super().__init__(parent)
        self.setWindowTitle("Edit Service" if item else "Add Service")
        self.setMinimumWidth(380)
        self._unit = unit
        self._build_ui(item, unit)

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

        layout.addRow("Service Name *:",           self.name)
        layout.addRow(f"Distance interval ({unit}):", self.interval_dist)
        layout.addRow("Time interval (months):",   self.interval_months)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

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


# ── garage tab ──────────────────────────────────────────────────────────────

class GarageTab(QWidget):
    def __init__(self, db: DatabaseManager, on_vehicle_changed, get_unit):
        super().__init__()
        self.db = db
        self.on_vehicle_changed = on_vehicle_changed
        self.get_unit = get_unit
        self._vehicle_ids: list[int] = []
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

    def refresh(self):
        unit = self.get_unit()
        self.table.setHorizontalHeaderLabels([
            "Nickname / Name", "Year", "Make", "Model", "Trim", "Color",
            "Plate", f"Odometer ({unit})", "Added",
        ])

        vehicles          = self.db.get_all_vehicles()
        self._vehicle_ids = [v["id"] for v in vehicles]
        self.table.setRowCount(len(vehicles))

        for row, v in enumerate(vehicles):
            display_name = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            cells = [
                display_name, str(v["year"]), v["make"], v["model"],
                v["trim"] or "", v["color"] or "", v["license_plate"] or "",
                f"{km_to_unit(v['current_mileage'], unit):,}", v["date_added"],
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 7:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)

    def _row_changed(self, row):
        self.on_vehicle_changed(self._vehicle_ids[row] if row >= 0 else None)

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


# ── schedule tab ─────────────────────────────────────────────────────────────

class ScheduleTab(QWidget):
    def __init__(self, db: DatabaseManager, get_unit):
        super().__init__()
        self.db       = db
        self.get_unit = get_unit
        self._vehicle_id: int | None = None
        self._item_ids:   list[int]  = []
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

        rows           = self.db.get_schedule(self._vehicle_id)
        self._item_ids = [item["id"] for item, _, _ in rows]
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
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.log_service(dlg.get_data())
            self.refresh()


# ── services tab ─────────────────────────────────────────────────────────────

class ServicesTab(QWidget):
    def __init__(self, db: DatabaseManager, get_unit):
        super().__init__()
        self.db          = db
        self.get_unit    = get_unit
        self._vehicle_id: int | None = None
        self._item_ids:   list[int]  = []
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
        layout.addWidget(self.table)

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

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._item_ids[row] if row >= 0 else None

    def _add_item(self):
        if self._vehicle_id is None:
            return
        dlg = MaintenanceItemDialog(self, unit=self.get_unit())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.add_maintenance_item(self._vehicle_id, dlg.get_data())
            self.refresh()

    def _edit_item(self):
        iid = self._selected_id()
        if iid is None:
            return
        items = {item["id"]: item for item in self.db.get_maintenance_items(self._vehicle_id)}
        dlg = MaintenanceItemDialog(self, items[iid], unit=self.get_unit())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_maintenance_item(iid, dlg.get_data())
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


# ── parts tab ────────────────────────────────────────────────────────────────

class PartDialog(QDialog):
    def __init__(self, parent=None, part=None, vehicles=None, default_vehicle_id=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Part" if part else "Add Part")
        self.setMinimumWidth(440)
        self._build_ui(part, vehicles or [], default_vehicle_id)

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

        layout.addRow("Vehicle *:",       self.vehicle_combo)
        layout.addRow("Part Name *:",     self.name)
        layout.addRow("Part Number:",     self.part_number)
        layout.addRow("Alt Part Number:", self.alt_part_number)
        layout.addRow("Supplier:",        self.supplier)
        layout.addRow("URL:",             self.url)
        layout.addRow("Price:",           self.price)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

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
        }


PARTS_COLUMNS = ["Vehicle", "Part Name", "Part #", "Alt Part #", "Supplier", "Price", "URL"]


class PartsTab(QWidget):
    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db
        self._part_ids: list[int] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Vehicle:"))
        self.vehicle_filter = QComboBox()
        self.vehicle_filter.setMinimumWidth(200)
        self.vehicle_filter.currentIndexChanged.connect(self._load_parts)
        top_row.addWidget(self.vehicle_filter)
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

    def _populate_filter(self):
        current_vid = self.vehicle_filter.currentData()
        self.vehicle_filter.blockSignals(True)
        self.vehicle_filter.clear()
        self.vehicle_filter.addItem("All Vehicles", None)
        for v in self.db.get_all_vehicles():
            label = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            self.vehicle_filter.addItem(label, v["id"])
        if current_vid is not None:
            idx = next((i for i in range(self.vehicle_filter.count())
                        if self.vehicle_filter.itemData(i) == current_vid), 0)
            self.vehicle_filter.setCurrentIndex(idx)
        self.vehicle_filter.blockSignals(False)

    def refresh(self):
        self._populate_filter()
        self._load_parts()

    def _load_parts(self):
        vehicle_id     = self.vehicle_filter.currentData()
        parts          = self.db.get_all_parts(vehicle_id)
        self._part_ids = [p["id"] for p in parts]
        self.table.setRowCount(len(parts))

        for row, p in enumerate(parts):
            v          = self.db.get_vehicle(p["vehicle_id"])
            v_name     = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            price_str  = f"${p['price']:.2f}" if p["price"] else "—"
            cells = [
                v_name,
                p["name"],
                p["part_number"]     or "—",
                p["alt_part_number"] or "—",
                p["supplier"]        or "—",
                price_str,
                p["url"]             or "—",
            ]
            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col == 5:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._part_ids[row] if row >= 0 else None

    def _add_part(self):
        dlg = PartDialog(
            self,
            vehicles=self.db.get_all_vehicles(),
            default_vehicle_id=self.vehicle_filter.currentData(),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.add_part(dlg.get_data())
            self.refresh()

    def _edit_part(self):
        pid = self._selected_id()
        if pid is None:
            return
        dlg = PartDialog(self, part=self.db.get_part(pid), vehicles=self.db.get_all_vehicles())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_part(pid, dlg.get_data())
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
        self.garage_tab    = GarageTab(self.db, self._on_vehicle_selected, lambda: self.unit)
        self.schedule_tab  = ScheduleTab(self.db, lambda: self.unit)
        self.services_tab  = ServicesTab(self.db, lambda: self.unit)
        self.parts_tab     = PartsTab(self.db)
        self.settings_tab  = SettingsTab(
            self._apply_theme, self._apply_unit,
            lambda path: self.settings.setValue("resources_folder", path),
            current_theme=self.settings.value("theme", "dark"),
            current_unit=self.settings.value("unit", "km"),
            current_resources_folder=self.settings.value("resources_folder", ""),
        )
        self.tabs.addTab(self.garage_tab,    "Garage")
        self.tabs.addTab(self.schedule_tab,  "Schedule")
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
        self.services_tab.refresh()

    def _on_vehicle_selected(self, vehicle_id: int | None):
        self.schedule_tab.set_vehicle(vehicle_id)
        self.services_tab.set_vehicle(vehicle_id)
        self.parts_tab.refresh()
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
