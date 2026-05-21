"""预处理对话框 - 询问用户是否对加载的点云进行下采样+去噪"""

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt


class PreprocessDialog(QDialog):
    """加载点云后弹出，让用户选择是否进行自适应预处理"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("点云预处理")
        self.setFixedSize(320, 160)

        self.choice = False

        title = QLabel("是否对点云进行预处理？")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")

        desc = QLabel("包含：下采样 + 去噪处理\n（推荐开启）")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray; font-size:12px;")

        btn_no = QPushButton("直接加载")
        btn_yes = QPushButton("推荐处理")

        btn_no.clicked.connect(self.choose_no)
        btn_yes.clicked.connect(self.choose_yes)

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

        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
        """)

    def choose_yes(self):
        """用户选择预处理"""
        self.choice = True
        self.accept()

    def choose_no(self):
        """用户跳过预处理"""
        self.choice = False
        self.accept()

    def get_choice(self):
        """返回用户选择：True=预处理，False=直接加载"""
        return self.choice
