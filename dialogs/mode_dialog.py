from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QLabel

class ModeDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("选择测量模式")

        self.mode = None

        layout = QVBoxLayout()

        label = QLabel("请选择测量方式：")
        layout.addWidget(label)

        btn_simple = QPushButton("简单测量（椭圆拟合）")
        btn_precise = QPushButton("精细测量（泊松重建 + 凸包）")

        btn_simple.clicked.connect(self.choose_simple)
        btn_precise.clicked.connect(self.choose_precise)

        layout.addWidget(btn_simple)
        layout.addWidget(btn_precise)

        self.setLayout(layout)

    def choose_simple(self):
        self.mode = "simple"
        self.accept()

    def choose_precise(self):
        self.mode = "precise"
        self.accept()

    def get_mode(self):
        return self.mode