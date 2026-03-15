from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow
import sys, os

def resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller EXE."""
    if hasattr(sys, "_MEIPASS"):           # PyInstaller sets this at runtime
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())