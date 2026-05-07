import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from src.main_window import VehicleApp


def _set_app_id():
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "VehicleLog.MaintenanceLog")
    except Exception:
        pass


def main():
    _set_app_id()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    ico_path = os.path.join(os.path.dirname(__file__), "assets", "vehicle_log.ico")
    if os.path.isfile(ico_path):
        app.setWindowIcon(QIcon(ico_path))

    window = VehicleApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
