import os

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QDialogButtonBox,
    QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QComboBox, QDateEdit,
)
from PySide6.QtCore import Qt, QDate, QSize
from PySide6.QtGui import QPixmap, QIcon

from src.utils import km_to_unit, unit_to_km, _get_file_type
from src.dialogs.attachments import AddAttachmentDialog
from src.dialogs.viewers import _open_file
from src.dialogs.maintenance import PickPartDialog


# ── log service dialog ───────────────────────────────────────────────────────

class LogServiceDialog(QDialog):
    def __init__(self, parent, db, vehicles, *, vehicle_id=None, item_id=None, unit="km",
                 get_resources_folder=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Service Entry" if entry else "Log Service")
        self.setMinimumWidth(460)
        self._db = db
        self._unit = unit
        self._get_resources_folder = get_resources_folder
        self._staged_images: list[str] = []
        self._removed_images: list[dict] = []
        self._parts_data: list[dict] = []
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

        self.shop = QLineEdit()
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
            pix = QPixmap(path)
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
            self._parts_table.setItem(
                row, 1, QTableWidgetItem(p["part_number"]))
            qty = QTableWidgetItem(str(p["quantity"]))
            qty.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                 Qt.AlignmentFlag.AlignVCenter)
            self._parts_table.setItem(row, 2, qty)

    def _add_part(self):
        vid = self.vehicle_combo.currentData()
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
            self.service_date.setDate(QDate.fromString(
                entry["service_date"], "yyyy-MM-dd"))
        if entry["mileage_at_service"]:
            self.mileage.setValue(km_to_unit(
                entry["mileage_at_service"], self._unit))
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
                QMessageBox.critical(
                    self, "Error", f"Could not save attachment:\n{e}")
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
