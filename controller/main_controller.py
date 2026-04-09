from PyQt6.QtWidgets import QMainWindow, QFileDialog
from ui_test import Ui_MainWindow
from core.pointcloud import load_point_cloud_file
import open3d as o3d
import win32gui
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer


class MainController(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.btnLoad.clicked.connect(self.load_point_cloud)

        self.vis = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_vis)

    def load_point_cloud(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择点云文件",
            "",
            "Point Cloud Files (*.ply *.pcd *.xyz *.txt)"
        )

        if not file_path:
            return

        self.pcd = load_point_cloud_file(file_path)

        self.show_point_cloud()

    def show_point_cloud(self):
        if self.vis is not None:
            self.vis.destroy_window()

        self.vis = o3d.visualization.Visualizer()
        self.vis.create_window(visible=True)

        self.vis.add_geometry(self.pcd)

        # 获取Open3D窗口句柄
        hwnd = win32gui.FindWindow(None, "Open3D")

        # 获取Qt控件句柄
        widget = self.ui.open3dWidget
        widget_hwnd = int(widget.winId())

        # 嵌入窗口
        win32gui.SetParent(hwnd, widget_hwnd)

        # 调整大小
        win32gui.MoveWindow(
            hwnd,
            0,
            0,
            widget.width(),
            widget.height(),
            True
        )

        self.timer.start(30)

    def update_vis(self):
        if self.vis:
            self.vis.poll_events()
            self.vis.update_renderer()