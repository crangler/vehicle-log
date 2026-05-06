import os
from collections.abc import Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon

from src.database import DatabaseManager
from src.utils import km_to_unit
from src.dialogs.vehicle import VehicleDialog
from src.dialogs.attachments import AddImageDialog
from src.dialogs.viewers import ImageViewerDialog


# ── garage tab ──────────────────────────────────────────────────────────────

class GarageTab(QWidget):
    def __init__(
        self,
        db: DatabaseManager,
        on_vehicle_changed: Callable[[int | None], None],
        get_unit: Callable[[], str],
        get_resources_folder: Callable[[], str],
    ):
        super().__init__()
        self.db = db
        self.on_vehicle_changed = on_vehicle_changed
        self.get_unit = get_unit
        self.get_resources_folder = get_resources_folder
        self._vehicle_ids: list[int] = []
        self._image_ids: list[int] = []
        self._image_paths: list[str] = []
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
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self._edit_vehicle)
        self.table.currentCellChanged.connect(
            lambda row, *_: self._row_changed(row))
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

        vehicles = self.db.get_all_vehicles()
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
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
        dlg = VehicleDialog(self, self.db.get_vehicle(vid),
                            unit=self.get_unit())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.db.update_vehicle(vid, dlg.get_data())
            self.refresh()

    def _delete_vehicle(self):
        vid = self.selected_id()
        if vid is None:
            return
        v = self.db.get_vehicle(vid)
        name = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
        if QMessageBox.question(
            self, "Delete Vehicle", f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self.db.delete_vehicle(vid)
            self.refresh()

    def _load_images(self, vehicle_id: int | None):
        self._image_ids = []
        self._image_paths = []
        self._image_list.clear()
        if vehicle_id is None:
            return
        images = self.db.get_vehicle_images(vehicle_id)
        self._image_ids = [img["id"] for img in images]
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
            self._image_list.addItem(
                QListWidgetItem(icon, os.path.basename(path)))

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
            QMessageBox.information(
                self, "No Vehicle Selected", "Select a vehicle before adding an image.")
            return
        dlg = AddImageDialog(self, resources_folder)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Could not save image:\n{e}")
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
