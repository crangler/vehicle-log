import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

from src.database import DatabaseManager
from src.utils import _get_file_type
from src.dialogs.part import PartDialog


# ── parts tab ────────────────────────────────────────────────────────────────

PARTS_COLUMNS = ["Part Name", "Part #",
                 "Alt Part #", "Supplier", "Price", "URL"]


class PartsTab(QWidget):
    def __init__(self, db: DatabaseManager, get_resources_folder=None):
        super().__init__()
        self.db = db
        self.get_resources_folder = get_resources_folder
        self._vehicle_id: int | None = None
        self._part_ids:   list[int] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel(
            "Select a vehicle in the Garage tab to view its parts.")
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
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
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
            self.vehicle_label.setText(
                "Select a vehicle in the Garage tab to view its parts.")
            return
        vehicle = self.db.get_vehicle(self._vehicle_id)
        name = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(f"<b>{name}</b>")
        self._load_parts()

    def _load_parts(self):
        parts = self.db.get_all_parts(self._vehicle_id)
        self._part_ids = [p["id"] for p in parts]
        self.table.setRowCount(len(parts))

        for row, p in enumerate(parts):
            price_str = f"${p['price']:.2f}" if p["price"] else "—"
            cells = [
                p["name"],
                p["part_number"] or "—",
                p["alt_part_number"] or "—",
                p["supplier"] or "—",
                price_str,
                p["url"] or "—",
            ]
            for col, text in enumerate(cells):
                cell = QTableWidgetItem(text)
                if col == 4:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._part_ids[row] if row >= 0 else None

    def _add_part(self):
        if self._vehicle_id is None:
            QMessageBox.information(
                self, "No Vehicle", "Select a vehicle in the Garage tab first.")
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
            QMessageBox.information(
                self, "No URL", "No URL saved for this part.")
