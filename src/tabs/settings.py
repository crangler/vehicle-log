import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton,
    QButtonGroup, QLineEdit, QPushButton, QMessageBox, QFileDialog,
)
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


# ── settings tab ─────────────────────────────────────────────────────────────

class SettingsTab(QWidget):
    def __init__(self, db, apply_theme, apply_unit, save_resources_folder,
                 current_theme, current_unit, current_resources_folder):
        super().__init__()
        self._db = db
        self._apply_theme = apply_theme
        self._apply_unit = apply_unit
        self._save_resources_folder = save_resources_folder
        self._build_ui(current_theme, current_unit, current_resources_folder)

    def _build_ui(self, current_theme, current_unit, current_resources_folder):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        # Theme
        theme_box = QGroupBox("Theme")
        theme_layout = QVBoxLayout(theme_box)
        self._dark_btn = QRadioButton("Dark")
        self._light_btn = QRadioButton("Light")
        self._theme_grp = QButtonGroup(self)
        self._theme_grp.addButton(self._dark_btn,  0)
        self._theme_grp.addButton(self._light_btn, 1)
        theme_layout.addWidget(self._dark_btn)
        theme_layout.addWidget(self._light_btn)
        (self._dark_btn if current_theme ==
         "dark" else self._light_btn).setChecked(True)
        self._theme_grp.idClicked.connect(
            lambda bid: self._apply_theme("dark" if bid == 0 else "light")
        )
        outer.addWidget(theme_box)

        # Unit
        unit_box = QGroupBox("Distance Unit")
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
        res_box = QGroupBox("Resources Folder")
        res_layout = QVBoxLayout(res_box)
        path_row = QHBoxLayout()
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

        # Default folders
        folders_box = QGroupBox("Use Default Folders")
        folders_layout = QVBoxLayout(folders_box)
        self._folders_yes = QRadioButton("Yes")
        self._folders_no = QRadioButton("No")
        self._folders_grp = QButtonGroup(self)
        self._folders_grp.addButton(self._folders_yes, 1)
        self._folders_grp.addButton(self._folders_no,  0)
        self._folders_no.setChecked(True)
        folders_layout.addWidget(self._folders_yes)
        folders_layout.addWidget(self._folders_no)
        self._create_folders_btn = QPushButton("Create Folders")
        self._create_folders_btn.setEnabled(False)
        self._create_folders_btn.clicked.connect(self._create_default_folders)
        folders_layout.addWidget(self._create_folders_btn)
        self._folders_grp.idClicked.connect(
            lambda bid: self._create_folders_btn.setEnabled(bid == 1)
        )
        outer.addWidget(folders_box)

        outer.addStretch()

    def _create_default_folders(self):
        resources = self._res_path.text().strip()
        if not resources:
            QMessageBox.warning(self, "No Resources Folder",
                                "Please set a Resources Folder before creating folders.")
            return
        if not os.path.isdir(resources):
            QMessageBox.warning(self, "Resources Folder Not Found",
                                f"The Resources folder is not accessible:\n{resources}")
            return

        vehicles = self._db.get_all_vehicles()
        if not vehicles:
            QMessageBox.information(
                self, "No Vehicles", "No vehicles found in the database.")
            return

        subfolders = ["Parts", "Services", "Service Log"]
        created, skipped = [], []
        for v in vehicles:
            folder_name = v["nickname"] or f"{v['year']} {v['make']} {v['model']}"
            vehicle_dir = os.path.join(resources, folder_name)
            is_new = not os.path.exists(vehicle_dir)
            for sub in subfolders:
                os.makedirs(os.path.join(vehicle_dir, sub), exist_ok=True)
            (created if is_new else skipped).append(folder_name)

        parts = []
        if created:
            parts.append(f"Created: {', '.join(created)}")
        if skipped:
            parts.append(
                f"Already existed (subfolders ensured): {', '.join(skipped)}")
        QMessageBox.information(self, "Folders Created", "\n".join(parts))

    def sync_theme(self, theme: str):
        (self._dark_btn if theme == "dark" else self._light_btn).setChecked(True)

    def sync_unit(self, unit: str):
        (self._km_btn if unit == "km" else self._mi_btn).setChecked(True)

    def _browse_resources(self):
        start = self._res_path.text() or ""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Resources Folder", start)
        if folder:
            self._res_path.setText(folder)
            self._save_resources_folder(folder)

    def _open_resources(self):
        path = self._res_path.text()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.information(
                self, "No Folder", "No resources folder has been selected.")
