import os

from PySide6.QtWidgets import QMainWindow, QTabWidget, QStatusBar, QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import QSettings

from src.database import DatabaseManager
from src.themes import dark_palette, light_palette
from src.utils import app_icon
from src.tabs.garage import GarageTab
from src.tabs.schedule import ScheduleTab
from src.tabs.service_log import ServiceLogTab
from src.tabs.services import ServicesTab
from src.tabs.parts import PartsTab
from src.tabs.settings import SettingsTab


_TAB_ICONS = [
    "fa5s.car",
    "fa5s.calendar-check",
    "fa5s.history",
    "fa5s.tools",
    "fa5s.puzzle-piece",
    "fa5s.cog",
]


# ── main window ──────────────────────────────────────────────────────────────

class VehicleApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.settings = QSettings("VehicleLog", "VehicleMaintenanceLog")
        self.setWindowTitle("Vehicle Maintenance Log")
        self.setMinimumSize(1000, 560)
        self._set_app_icon()
        self._build_ui()
        self._apply_theme(self.settings.value("theme", "dark"))
        self._apply_unit(self.settings.value("unit", "km"))

    def _set_app_icon(self):
        ico = os.path.join(os.path.dirname(__file__), "..", "assets", "vehicle_log.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))

    @property
    def unit(self) -> str:
        return self.settings.value("unit", "km")

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.garage_tab = GarageTab(
            self.db, self._on_vehicle_selected,
            lambda: self.unit,
            lambda: self.settings.value("resources_folder", ""),
        )
        self.schedule_tab = ScheduleTab(
            self.db, lambda: self.unit,
            self._on_service_logged,
            lambda: self.settings.value("resources_folder", ""),
        )
        self.log_tab = ServiceLogTab(
            self.db,
            lambda: self.unit,
            lambda: self.settings.value("resources_folder", ""),
            self._on_service_logged,
        )
        self.services_tab = ServicesTab(self.db, lambda: self.unit,
                                        lambda: self.settings.value("resources_folder", ""))
        self.parts_tab = PartsTab(
            self.db, lambda: self.settings.value("resources_folder", ""))
        self.settings_tab = SettingsTab(
            self.db,
            self._apply_theme, self._apply_unit,
            lambda path: self.settings.setValue("resources_folder", path),
            current_theme=self.settings.value("theme", "dark"),
            current_unit=self.settings.value("unit", "km"),
            current_resources_folder=self.settings.value(
                "resources_folder", ""),
        )
        self.tabs.addTab(self.garage_tab,    app_icon("fa5s.car"),            "Garage")
        self.tabs.addTab(self.schedule_tab,  app_icon("fa5s.calendar-check"), "Schedule")
        self.tabs.addTab(self.log_tab,       app_icon("fa5s.history"),        "Log")
        self.tabs.addTab(self.services_tab,  app_icon("fa5s.tools"),          "Services")
        self.tabs.addTab(self.parts_tab,     app_icon("fa5s.puzzle-piece"),   "Parts")
        self.tabs.addTab(self.settings_tab,  app_icon("fa5s.cog"),            "Settings")
        self.setCentralWidget(self.tabs)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status()

    def _update_tab_icons(self):
        for i, name in enumerate(_TAB_ICONS):
            self.tabs.setTabIcon(i, app_icon(name))

    def _apply_theme(self, theme: str):
        QApplication.instance().setPalette(
            dark_palette() if theme == "dark" else light_palette())
        self.settings.setValue("theme", theme)
        self._update_tab_icons()
        self.settings_tab.sync_theme(theme)

    def _apply_unit(self, unit: str):
        self.settings.setValue("unit", unit)
        self.settings_tab.sync_unit(unit)
        self.garage_tab.refresh()
        self.schedule_tab.refresh()
        self.log_tab.refresh()
        self.services_tab.refresh()

    def _on_service_logged(self):
        self.schedule_tab.refresh()
        self.log_tab.refresh()

    def _on_vehicle_selected(self, vehicle_id: int | None):
        self.schedule_tab.set_vehicle(vehicle_id)
        self.log_tab.set_vehicle(vehicle_id)
        self.services_tab.set_vehicle(vehicle_id)
        self.parts_tab.set_vehicle(vehicle_id)
        self._update_status()

    def _update_status(self):
        n = len(self.db.get_all_vehicles())
        self.status_bar.showMessage(f"{n} vehicle{'s' if n != 1 else ''}")

    def closeEvent(self, event):
        self.db.close()
        super().closeEvent(event)
