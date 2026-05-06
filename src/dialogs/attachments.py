import os
import shutil

from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QPushButton, QComboBox,
    QDialogButtonBox, QMessageBox, QHBoxLayout, QFileDialog,
)


# ── attachment filter ─────────────────────────────────────────────────────────

_ATTACHMENT_FILTER = (
    "All Supported (*.png *.jpg *.jpeg *.gif *.bmp *.webp "
    "*.mp4 *.avi *.mov *.mkv *.wmv *.m4v *.webm *.mpeg *.mpg *.pdf);;"
    "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;"
    "Videos (*.mp4 *.avi *.mov *.mkv *.wmv *.m4v *.webm *.mpeg *.mpg);;"
    "PDF Documents (*.pdf)"
)


# ── add image dialog ─────────────────────────────────────────────────────────

class AddImageDialog(QDialog):
    def __init__(self, parent, resources_folder: str):
        super().__init__(parent)
        self.setWindowTitle("Add Vehicle Image")
        self.setMinimumWidth(500)
        self._resources_folder = resources_folder
        self._source_path = ""
        self._build_ui()

    def _build_ui(self):
        layout = QFormLayout(self)

        src_row = QHBoxLayout()
        self._src_edit = QLineEdit()
        self._src_edit.setReadOnly(True)
        self._src_edit.setPlaceholderText("No file selected")
        src_row.addWidget(self._src_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_source)
        src_row.addWidget(browse_btn)
        layout.addRow("Image File *:", src_row)

        self._folder_combo = QComboBox()
        self._folder_combo.setEditable(True)
        self._folder_combo.lineEdit().setPlaceholderText(
            "Resources root  (type a name to create a subfolder)")
        self._populate_folders()
        layout.addRow("Folder:", self._folder_combo)

        self._filename_edit = QLineEdit()
        self._filename_edit.setPlaceholderText(
            "Auto-filled when image is selected")
        layout.addRow("Filename *:", self._filename_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _populate_folders(self):
        self._folder_combo.clear()
        self._folder_combo.addItem("", "")
        try:
            for top in sorted(os.scandir(self._resources_folder), key=lambda e: e.name.lower()):
                if not top.is_dir():
                    continue
                self._folder_combo.addItem(top.name, top.name)
                try:
                    for sub in sorted(os.scandir(top.path), key=lambda e: e.name.lower()):
                        if sub.is_dir():
                            display = f"  {top.name} / {sub.name}"
                            value = f"{top.name}/{sub.name}"
                            self._folder_combo.addItem(display, value)
                except OSError:
                    pass
        except OSError:
            pass

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)",
        )
        if path:
            self._source_path = path
            self._src_edit.setText(path)
            self._filename_edit.setText(os.path.basename(path))

    def _validate_and_accept(self):
        if not self._source_path:
            QMessageBox.warning(
                self, "Required", "Please select an image file.")
            return
        if not self._filename_edit.text().strip():
            QMessageBox.warning(self, "Required", "Please enter a filename.")
            return
        self.accept()

    def get_destination_path(self) -> str:
        dest_dir = self._resources_folder
        idx = self._folder_combo.currentIndex()
        if idx >= 0:
            subfolder = self._folder_combo.itemData(idx)
        else:
            subfolder = self._folder_combo.currentText().strip()
        if subfolder:
            dest_dir = os.path.join(dest_dir, *subfolder.split("/"))
            os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, self._filename_edit.text().strip())
        if os.path.abspath(dest_path) != os.path.abspath(self._source_path):
            shutil.copy2(self._source_path, dest_path)
        return dest_path


class AddAttachmentDialog(AddImageDialog):
    """Like AddImageDialog but accepts images, videos, and PDFs."""

    def __init__(self, parent, resources_folder: str):
        super().__init__(parent, resources_folder)
        self.setWindowTitle("Add Attachment")

    def _build_ui(self):
        super()._build_ui()
        layout = self.layout()
        for i in range(layout.rowCount()):
            label = layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
            if label and label.widget() and label.widget().text() == "Image File *:":
                label.widget().setText("Select File *:")
                break

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Attachment", "", _ATTACHMENT_FILTER,
        )
        if path:
            self._source_path = path
            self._src_edit.setText(path)
            self._filename_edit.setText(os.path.basename(path))
