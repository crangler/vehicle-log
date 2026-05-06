import os
from collections.abc import Callable

from src.utils import app_icon

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon

from src.database import DatabaseManager
from src.utils import km_to_unit, _get_file_type
from src.dialogs.maintenance import MaintenanceItemDialog
from src.dialogs.attachments import AddAttachmentDialog
from src.dialogs.viewers import _open_file


# ── services tab ─────────────────────────────────────────────────────────────

class ServicesTab(QWidget):
    def __init__(
        self,
        db: DatabaseManager,
        get_unit: Callable[[], str],
        get_resources_folder: Callable[[], str] | None = None,
    ):
        super().__init__()
        self.db = db
        self.get_unit = get_unit
        self.get_resources_folder = get_resources_folder
        self._vehicle_id: int | None = None
        self._item_ids: list[int] = []
        self._file_ids: list[int] = []
        self._file_paths: list[str] = []
        self._file_types: list[str] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel(
            "Select a vehicle in the Garage tab to manage its services.")
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
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_item)
        self.table.currentCellChanged.connect(
            lambda row, *_: self._row_changed(row))
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
            self.vehicle_label.setText(
                "Select a vehicle in the Garage tab to manage its services.")
            self._load_files(None)
            return

        vehicle = self.db.get_vehicle(self._vehicle_id)
        name = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        self.vehicle_label.setText(f"<b>{name}</b>")

        items = self.db.get_maintenance_items(self._vehicle_id)
        self._item_ids = [item["id"] for item in items]
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            dist_str = f"{km_to_unit(item['interval_miles'], unit):,}" if item["interval_miles"] else "—"
            month_str = str(item["interval_months"]
                            ) if item["interval_months"] else "—"
            for col, text in enumerate([item["name"], dist_str, month_str]):
                cell = QTableWidgetItem(text)
                if col in (1, 2):
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

        self._load_files(self._selected_id())

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        return self._item_ids[row] if 0 <= row < len(self._item_ids) else None

    def _row_changed(self, row):
        self._load_files(self._item_ids[row] if 0 <= row < len(
            self._item_ids) else None)

    def _load_files(self, item_id: int | None):
        self._file_ids = []
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
                pix = QPixmap(f["path"])
                icon = QIcon(pix.scaled(100, 75, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)) if not pix.isNull() else QIcon()
            else:
                icon = QIcon()
            self._file_list.addItem(QListWidgetItem(
                icon, os.path.basename(f["path"])))

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
            QMessageBox.information(
                self, "No Service Selected", "Select a service before adding an attachment.")
            return
        dlg = AddAttachmentDialog(self, rf)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Could not save attachment:\n{e}")
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
        ft = self._file_types[row] if row < len(
            self._file_types) else _get_file_type(path)
        image_paths = [p for p, t in zip(
            self._file_paths, self._file_types) if t == "image"]
        img_row = self._file_types[:row].count("image")
        _open_file(self, path, ft, image_paths, img_row)

    def _add_item(self):
        if self._vehicle_id is None:
            return
        dlg = MaintenanceItemDialog(self, unit=self.get_unit(),
                                    db=self.db,
                                    get_resources_folder=self.get_resources_folder,
                                    vehicle_id=self._vehicle_id,
                                    window_icon=app_icon("fa5s.tools"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            item_id = self.db.add_maintenance_item(
                self._vehicle_id, dlg.get_data())
            for path in dlg.get_staged_files():
                self.db.add_maintenance_item_file(
                    item_id, path, _get_file_type(path))
            self.db.set_maintenance_item_parts(item_id, dlg.get_parts_data())
            self.refresh()

    def _edit_item(self):
        iid = self._selected_id()
        if iid is None:
            return
        dlg = MaintenanceItemDialog(self, self.db.get_maintenance_item(iid), unit=self.get_unit(),
                                    db=self.db,
                                    get_resources_folder=self.get_resources_folder,
                                    vehicle_id=self._vehicle_id,
                                    window_icon=app_icon("fa5s.tools"))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_maintenance_item(iid, dlg.get_data())
            for f in dlg.get_removed_files():
                self.db.delete_maintenance_item_file(f["id"])
                try:
                    os.remove(f["path"])
                except OSError:
                    pass
            for path in dlg.get_staged_files():
                self.db.add_maintenance_item_file(
                    iid, path, _get_file_type(path))
            self.db.set_maintenance_item_parts(iid, dlg.get_parts_data())
            self.refresh()

    def _delete_item(self):
        iid = self._selected_id()
        if iid is None:
            return
        name = self.db.get_maintenance_item(iid)["name"]
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
