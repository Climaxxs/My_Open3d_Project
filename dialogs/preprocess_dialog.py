from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt


class PreprocessDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("点云预处理")
        self.setFixedSize(320, 160)

        self.choice = False  # 默认不处理

        #标题
        title = QLabel("是否对点云进行预处理？")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")

        #说明
        desc = QLabel("包含：下采样 + 去噪处理\n（推荐开启）")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray; font-size:12px;")

        #按钮
        btn_no = QPushButton("直接加载")
        btn_yes = QPushButton("推荐处理")

        btn_no.clicked.connect(self.choose_no)
        btn_yes.clicked.connect(self.choose_yes)

        #按钮样式
        btn_no.setStyleSheet("""
            QPushButton {
                background-color: #dddddd;
                padding: 8px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #cccccc;
            }
        """)

        btn_yes.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        #布局
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_no)
        btn_layout.addWidget(btn_yes)

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        #整体样式
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
        """)

    def choose_yes(self):
        self.choice = True
        self.accept()

    def choose_no(self):
        self.choice = False
        self.accept()

    def get_choice(self):
        return self.choice