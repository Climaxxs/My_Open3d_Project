"""家畜点云尺寸测量系统 - 应用入口"""

import sys
from PyQt6.QtWidgets import QApplication
from controller.main_controller import MainController

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = MainController()
    window.show()

    sys.exit(app.exec())
 