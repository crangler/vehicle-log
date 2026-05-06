import sys
from PySide6.QtWidgets import QApplication
from src.main_window import VehicleApp


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = VehicleApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
