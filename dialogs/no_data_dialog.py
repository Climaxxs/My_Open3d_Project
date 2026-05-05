from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
from PyQt6.QtCore import Qt


class NoDataDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("提示")
        self.setFixedSize(340, 300)

        # 图标
        icon = QLabel("📋")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")

        # 标题
        title = QLabel("暂无测量数据")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")

        # 说明
        desc = QLabel("请先进行测量操作：\n• 手动选点测量（Ctrl+Shift+点击）\n• 自动测量（一键测量体尺）")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray; font-size:12px; line-height: 1.5;")

        # 按钮
        btn_ok = QPushButton("        我知道了")
        btn_ok.clicked.connect(self.accept)

        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #409eff;
                color: white;
                padding: 10px 30px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #66b1ff;
            }
        """)

        # 布局
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.addStretch()
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addWidget(btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        self.setLayout(layout)

        # 整体样式
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
        """)