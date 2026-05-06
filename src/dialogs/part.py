import os

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox, QTextEdit, QDialogButtonBox,
    QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QComboBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon

from src.utils import _get_file_type
from src.dialogs.attachments import AddAttachmentDialog
from src.dialogs.viewers import _open_file


# ── part dialog ───────────────────────────────────────────────────────────────

class PartDialog(QDialog):
    def __init__(self, parent=None, part=None, vehicles=None, default_vehicle_id=None,
                 db=None, get_resources_folder=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Part" if part else "Add Part")
        self.setMinimumWidth(460)
        self._db = db
        self._get_resources_folder = get_resources_folder
        self._staged_images: list[str] = []
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

        self.name = QLineEdit(val("name"))
        self.part_number = QLineEdit(val("part_number"))
        self.alt_part_number = QLineEdit(val("alt_part_number"))
        self.supplier = QLineEdit(val("supplier"))
        self.url = QLineEdit(val("url"))
        self.price = QDoubleSpinBox()
        self.price.setRange(0, 99_999)
        self.price.setPrefix("$")
        self.price.setDecimals(2)
        self.price.setValue(part["price"] or 0 if part else 0)
        self.notes = QTextEdit(val("notes"))
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
            pix = QPixmap(path)
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
                QMessageBox.critical(
                    self, "Error", f"Could not save attachment:\n{e}")
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
