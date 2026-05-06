import os

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QComboBox, QDialogButtonBox,
    QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon

from src.utils import km_to_unit, unit_to_km, _get_file_type
from src.dialogs.attachments import AddAttachmentDialog
from src.dialogs.viewers import _open_file


# ── pick part dialog ──────────────────────────────────────────────────────────

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


# ── maintenance item dialog ───────────────────────────────────────────────────

class MaintenanceItemDialog(QDialog):
    def __init__(self, parent=None, item=None, unit="km", db=None, get_resources_folder=None,
                 vehicle_id=None, window_icon=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Service" if item else "Add Service")
        if window_icon is not None:
            self.setWindowIcon(window_icon)
        self.setMinimumWidth(460)
        self._unit = unit
        self._db = db
        self._get_resources_folder = get_resources_folder
        self._vehicle_id = vehicle_id
        self._staged_files: list[str] = []
        self._removed_files: list[dict] = []
        self._parts_data: list[dict] = []
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
        self.interval_dist.setValue(km_to_unit(
            item["interval_miles"], unit) if item and item["interval_miles"] else 0)

        self.interval_months = QSpinBox()
        self.interval_months.setRange(0, 120)
        self.interval_months.setSpecialValueText("None")
        self.interval_months.setValue(
            item["interval_months"] or 0 if item else 0)

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
        self._parts_table.setHorizontalHeaderLabels(
            ["Part Name", "Part Number", "Qty"])
        self._parts_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._parts_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._parts_table.setFixedHeight(110)
        self._parts_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._parts_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._parts_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
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
            self._parts_table.setItem(
                row, 1, QTableWidgetItem(p["part_number"]))
            qty = QTableWidgetItem(str(p["quantity"]))
            qty.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                 Qt.AlignmentFlag.AlignVCenter)
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
            pix = QPixmap(path)
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
                QMessageBox.critical(
                    self, "Error", f"Could not save attachment:\n{e}")
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
        ft = meta.get("file_type") or _get_file_type(path)
        image_paths, img_row = [], 0
        if ft == "image":
            for i in range(self._staged_list.count()):
                m = self._staged_list.item(i).data(Qt.ItemDataRole.UserRole)
                if m and m.get("file_type", "image") == "image":
                    if m["path"] == path:
                        img_row = len(image_paths)
                    image_paths.append(m["path"])
        _open_file(self, path, ft, image_paths, img_row)

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
            QMessageBox.warning(
                self, "Required", "At least one interval (distance or months) is required.")
            return
        self.accept()

    def get_data(self):
        return {
            "name":            self.name.text().strip(),
            "interval_miles":  unit_to_km(self.interval_dist.value(), self._unit) or None,
            "interval_months": self.interval_months.value() or None,
        }
