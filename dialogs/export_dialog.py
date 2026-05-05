from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QComboBox
from PyQt6.QtCore import Qt


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("导出测量数据")
        self.setFixedSize(350, 210)

        self.format_choice = "csv"  # 默认CSV

        # 标题
        title = QLabel("选择导出格式")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:16px; font-weight:bold;")

        # 说明
        desc = QLabel("将测量记录导出为文件")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: gray; font-size:12px;")

        # 格式选择下拉框
        self.combo_format = QComboBox()
        self.combo_format.addItem("📄 CSV 文件 (.csv)", "csv")
        self.combo_format.addItem("📊 Excel 文件 (.xlsx)", "xlsx")
        self.combo_format.addItem("📝 文本文件 (.txt)", "txt")
        self.combo_format.setStyleSheet("""
            QComboBox {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 10px;
                font-size: 13px;
                min-width: 260px;
            }
            QComboBox:hover {
                border: 1px solid #409eff;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                border: 1px solid #ddd;
                selection-background-color: #409eff;
                selection-color: white;
                padding: 5px;
            }
        """)

        # 按钮
        btn_export = QPushButton("📤 导出")
        btn_cancel = QPushButton("取消")

        btn_export.clicked.connect(self.choose_export)
        btn_cancel.clicked.connect(self.reject)

        # 导出按钮样式 - 绿色（与推荐处理按钮一致）
        btn_export.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)

        # 取消按钮样式 - 灰色
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #dddddd;
                padding: 8px 20px;
                border-radius: 6px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #cccccc;
            }
        """)

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_export)

        # 主布局
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(self.combo_format)
        layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        # 整体样式 - 白色背景圆角（与其他对话框一致）
        self.setStyleSheet("""
            QDialog {
                background-color: white;
                border-radius: 10px;
            }
        """)

    def choose_export(self):
        self.format_choice = self.combo_format.currentData()
        self.accept()

    def get_format(self):
        return self.format_choice