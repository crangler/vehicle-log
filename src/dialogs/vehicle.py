from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox, QTextEdit, QDialogButtonBox,
    QMessageBox, QDateEdit,
)
from PySide6.QtCore import QDate

from src.utils import km_to_unit, unit_to_km


# ── vehicle dialog ───────────────────────────────────────────────────────────

class VehicleDialog(QDialog):
    def __init__(self, parent=None, vehicle=None, unit="km"):
        super().__init__(parent)
        self.setWindowTitle("Edit Vehicle" if vehicle else "Add Vehicle")
        self.setMinimumWidth(420)
        self._unit = unit
        self._build_ui(vehicle, unit)

    def _build_ui(self, v, unit):
        layout = QFormLayout(self)

        def val(field, default=""):
            return (v[field] or default) if v else default

        self.nickname = QLineEdit(val("nickname"))
        self.year = QSpinBox()
        self.year.setRange(1900, 2100)
        self.year.setValue(v["year"] if v else 2020)
        self.make = QLineEdit(val("make"))
        self.model = QLineEdit(val("model"))
        self.trim = QLineEdit(val("trim"))
        self.color = QLineEdit(val("color"))
        self.vin = QLineEdit(val("vin"))
        self.license_plate = QLineEdit(val("license_plate"))
        self.current_mileage = QSpinBox()
        self.current_mileage.setRange(0, 9_999_999)
        self.current_mileage.setSingleStep(100)
        self.current_mileage.setValue(km_to_unit(
            v["current_mileage"], unit) if v else 0)

        self.odometer_reading_date = QDateEdit()
        self.odometer_reading_date.setCalendarPopup(True)
        self.odometer_reading_date.setDisplayFormat("yyyy-MM-dd")
        self.odometer_reading_date.setSpecialValueText(" ")
        self.odometer_reading_date.setMinimumDate(QDate(1900, 1, 1))
        stored_date = val("odometer_reading_date")
        if stored_date:
            self.odometer_reading_date.setDate(
                QDate.fromString(stored_date, "yyyy-MM-dd"))
        else:
            self.odometer_reading_date.setDate(QDate.currentDate())

        self.notes = QTextEdit(val("notes"))
        self.notes.setFixedHeight(70)

        layout.addRow("Nickname:",                    self.nickname)
        layout.addRow("Year *:",                      self.year)
        layout.addRow("Make *:",                      self.make)
        layout.addRow("Model *:",                     self.model)
        layout.addRow("Trim:",                        self.trim)
        layout.addRow("Color:",                       self.color)
        layout.addRow("VIN:",                         self.vin)
        layout.addRow("License Plate:",               self.license_plate)
        layout.addRow(f"Odometer ({unit}):",          self.current_mileage)
        layout.addRow("Odometer Reading Date:",
                      self.odometer_reading_date)
        layout.addRow("Notes:",                       self.notes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate_and_accept(self):
        if not self.make.text().strip():
            QMessageBox.warning(self, "Required", "Make is required.")
            return
        if not self.model.text().strip():
            QMessageBox.warning(self, "Required", "Model is required.")
            return
        self.accept()

    def get_data(self):
        d = self.odometer_reading_date.date()
        return {
            "nickname":               self.nickname.text().strip() or None,
            "year":                   self.year.value(),
            "make":                   self.make.text().strip(),
            "model":                  self.model.text().strip(),
            "trim":                   self.trim.text().strip() or None,
            "color":                  self.color.text().strip() or None,
            "vin":                    self.vin.text().strip() or None,
            "license_plate":          self.license_plate.text().strip() or None,
            "current_mileage":        unit_to_km(self.current_mileage.value(), self._unit),
            "odometer_reading_date":  d.toString("yyyy-MM-dd") if d.isValid() else None,
            "notes":                  self.notes.toPlainText().strip() or None,
        }
