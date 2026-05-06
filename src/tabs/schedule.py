import os
from collections.abc import Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush

from src.database import DatabaseManager
from src.utils import km_to_unit, compute_status, STATUS_COLORS, _get_file_type
from src.dialogs.log_service import LogServiceDialog


# ── schedule tab ─────────────────────────────────────────────────────────────

class ScheduleTab(QWidget):
    def __init__(
        self,
        db: DatabaseManager,
        get_unit: Callable[[], str],
        on_service_logged: Callable[[], None],
        get_resources_folder: Callable[[], str],
    ):
        super().__init__()
        self.db = db
        self.get_unit = get_unit
        self._on_service_logged = on_service_logged
        self._get_resources_folder = get_resources_folder
        self._vehicle_id: int | None = None
        self._item_ids: list[int] = []
        self._last_entries: list = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel(
            "Select a vehicle in the Garage tab to view its schedule.")
        top_row.addWidget(self.vehicle_label)
        top_row.addStretch()
        self.log_btn = QPushButton("Log Service")
        self.log_btn.setEnabled(False)
        self.log_btn.clicked.connect(self._log_service)
        top_row.addWidget(self.log_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
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
            self.vehicle_label.setText(
                "Select a vehicle in the Garage tab to view its schedule.")
            return

        vehicle = self.db.get_vehicle(self._vehicle_id)
        name = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(
            f"<b>{name}</b> &nbsp;·&nbsp; Odometer: {km_to_unit(vehicle['current_mileage'], unit):,} {unit}"
        )
        self.log_btn.setEnabled(True)

        rows = self.db.get_schedule(self._vehicle_id)
        self._item_ids = [item["id"] for item, _, _ in rows]
        self._last_entries = [last for _, last, _ in rows]
        self.table.setRowCount(len(rows))

        for row, (item, last, v) in enumerate(rows):
            interval_parts = []
            if item["interval_miles"]:
                interval_parts.append(
                    f"{km_to_unit(item['interval_miles'], unit):,} {unit}")
            if item["interval_months"]:
                interval_parts.append(f"{item['interval_months']} mo")
            interval_str = " / ".join(interval_parts) if interval_parts else "—"

            status, next_dist, next_date = compute_status(item, last, v)

            last_done = last["service_date"] if last else "Never"
            at_dist = f"{km_to_unit(last['mileage_at_service'], unit):,}" if last and last["mileage_at_service"] else "—"
            next_dist_str = f"{km_to_unit(next_dist, unit):,}" if next_dist is not None else "—"
            next_date_str = next_date.isoformat() if next_date else "—"

            color = STATUS_COLORS[status]
            cells = [item["name"], interval_str, last_done,
                     at_dist, next_dist_str, next_date_str, status]

            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col in (3, 4):
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
                self.db.add_service_log_image(
                    entry_id, path, _get_file_type(path))
            self.db.set_service_log_parts(entry_id, dlg.get_parts_data())
            self._on_service_logged()

    def _edit_or_log_selected(self):
        row = self.table.currentRow()
        if row < 0 or self._vehicle_id is None:
            return
        last = self._last_entries[row] if row < len(
            self._last_entries) else None
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
                self.db.add_service_log_image(
                    last["id"], path, _get_file_type(path))
            self.db.set_service_log_parts(last["id"], dlg.get_parts_data())
            self._on_service_logged()
