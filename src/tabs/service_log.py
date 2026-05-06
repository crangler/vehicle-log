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
from src.utils import km_to_unit, _get_file_type
from src.dialogs.log_service import LogServiceDialog
from src.dialogs.attachments import AddAttachmentDialog
from src.dialogs.viewers import _open_file
from src.dialogs.report import ReportOptionsDialog, ServiceReportDialog, _build_report_html


# ── service log tab ──────────────────────────────────────────────────────────

class ServiceLogTab(QWidget):
    def __init__(
        self,
        db: DatabaseManager,
        get_unit: Callable[[], str],
        get_resources_folder: Callable[[], str],
        on_service_logged: Callable[[], None],
    ):
        super().__init__()
        self.db = db
        self.get_unit = get_unit
        self.get_resources_folder = get_resources_folder
        self._on_service_logged = on_service_logged
        self._vehicle_id: int | None = None
        self._log_ids: list[int] = []
        self._image_ids: list[int] = []
        self._image_paths: list[str] = []
        self._file_types: list[str] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top_row = QHBoxLayout()
        self.vehicle_label = QLabel(
            "Select a vehicle in the Garage tab to view its service log.")
        top_row.addWidget(self.vehicle_label)
        top_row.addStretch()
        edit_btn = QPushButton("Edit Entry")
        edit_btn.clicked.connect(self._edit_entry)
        top_row.addWidget(edit_btn)
        log_btn = QPushButton("Log Service")
        log_btn.clicked.connect(self._log_service)
        top_row.addWidget(log_btn)
        report_btn = QPushButton("Generate Report…")
        report_btn.clicked.connect(self._generate_report)
        top_row.addWidget(report_btn)
        layout.addLayout(top_row)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.currentCellChanged.connect(
            lambda row, *_: self._row_changed(row))
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
            self.vehicle_label.setText(
                "Select a vehicle in the Garage tab to view its service log.")
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
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, cell)

        self._load_images(self._selected_log_id())

    def _selected_log_id(self) -> int | None:
        row = self.table.currentRow()
        return self._log_ids[row] if 0 <= row < len(self._log_ids) else None

    def _row_changed(self, row):
        self._load_images(self._log_ids[row] if 0 <= row < len(
            self._log_ids) else None)

    def _load_images(self, log_id: int | None):
        self._image_ids = []
        self._image_paths = []
        self._file_types = []
        self._image_list.clear()
        if log_id is None:
            return
        attachments = self.db.get_service_log_images(log_id)
        self._image_ids = [a["id"] for a in attachments]
        self._image_paths = [a["path"] for a in attachments]
        self._file_types = [a["file_type"] for a in attachments]
        for path, ft in zip(self._image_paths, self._file_types):
            if ft == "image":
                pix = QPixmap(path)
                icon = QIcon(pix.scaled(
                    100, 75,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )) if not pix.isNull() else QIcon()
            else:
                icon = QIcon()
            self._image_list.addItem(
                QListWidgetItem(icon, os.path.basename(path)))

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
            QMessageBox.information(
                self, "No Entry Selected", "Select a service log entry before adding an attachment.")
            return
        dlg = AddAttachmentDialog(self, resources_folder)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                dest = dlg.get_destination_path()
            except Exception as e:
                QMessageBox.critical(
                    self, "Error", f"Could not save attachment:\n{e}")
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
        ft = self._file_types[row] if row < len(
            self._file_types) else _get_file_type(path)
        image_paths = [p for p, t in zip(
            self._image_paths, self._file_types) if t == "image"]
        img_row = self._file_types[:row].count("image")
        _open_file(self, path, ft, image_paths, img_row)

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
                self.db.add_service_log_image(
                    entry_id, path, _get_file_type(path))
            self.db.set_service_log_parts(entry_id, dlg.get_parts_data())
            self._on_service_logged()

    def _generate_report(self):
        if self._vehicle_id is None:
            QMessageBox.information(
                self, "No Vehicle", "Select a vehicle in the Garage tab first.")
            return
        opts = ReportOptionsDialog(self)
        if opts.exec() != QDialog.DialogCode.Accepted:
            return
        date_from, date_to = opts.get_range()
        vehicle = self.db.get_vehicle(self._vehicle_id)
        entries = self.db.get_service_log_entries_range(
            self._vehicle_id, date_from, date_to)
        parts_map = self.db.get_service_log_parts_for_entries(
            [e["id"] for e in entries])
        unit = self.get_unit()
        html = _build_report_html(
            vehicle, entries, unit, date_from, date_to, parts_map)
        name = vehicle["nickname"] or f"{vehicle['year']} {vehicle['make']} {vehicle['model']}"
        ServiceReportDialog(self, html=html, vehicle_name=name,
                            date_from=date_from, date_to=date_to).exec()
