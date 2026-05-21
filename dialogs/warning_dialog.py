"""警告对话框 - 提示用户尚未加载点云"""

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt


class WarningDialog(QDialog):
    """当用户试图在无点云时进行测量操作时弹出的提示"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("操作提示")
        self.setFixedSize(320, 150)

        title = QLabel("无法进行测量")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")

        desc = QLabel("当前未加载点云数据\n请先导入点云文件")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray; font-size:12px;")

        btn_ok = QPushButton("我知道了")
        btn_ok.clicked.connect(self.accept)

        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #409eff;
                color: white;
                padding: 8px;
                border-radius: 6px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
        """)

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
        """)
