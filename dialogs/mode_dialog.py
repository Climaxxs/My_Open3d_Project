from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt


class ModeDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("选择测量模式")
        self.setFixedSize(380, 220)

        self.mode = None

        # 标题
        title = QLabel("请选择测量方式")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")

        # 说明
        desc = QLabel("简单测量：快速椭圆拟合\n精细测量：泊松重建 + 凹包计算（耗时较长）")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray; font-size:12px;")

        # 按钮
        btn_simple = QPushButton(" 简单测量")
        btn_precise = QPushButton(" 精细测量")

        btn_simple.clicked.connect(self.choose_simple)
        btn_precise.clicked.connect(self.choose_precise)

        # 简单测量按钮样式 - 绿色
        btn_simple.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 10px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        # 精细测量按钮样式 - 蓝色
        btn_precise.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 10px;
                border-radius: 6px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)

        # 布局
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addWidget(btn_simple)
        btn_layout.addWidget(btn_precise)

        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addStretch()

        self.setLayout(layout)

        # 整体样式
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
        """)

    def choose_simple(self):
        self.mode = "simple"
        self.accept()

    def choose_precise(self):
        self.mode = "precise"
        self.accept()

    def get_mode(self):
        return self.mode