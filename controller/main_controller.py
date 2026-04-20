from PyQt6.QtWidgets import QMainWindow, QFileDialog, QVBoxLayout, QProgressDialog, QWidget
from PyQt6.QtGui import QWindow
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from ui_test import Ui_MainWindow
from controller.threads import PointCloudLoadThread
from core.pointcloud import build_pcd, safe_preprocess

import open3d as o3d
import win32gui
import time


class MainController(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.btnLoad.clicked.connect(self.load_point_cloud)

        self.vis = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_vis)

        self.points = None
        self.pcd = None

    # ================= 加载 =================
    def load_point_cloud(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择点云", "", "*.ply *.pcd *.xyz *.txt"
        )

        if not file_path:
            return

        self.progress = QProgressDialog("加载中...", None, 0, 0, self)
        self.progress.setMinimumDuration(0)
        self.progress.show()

        self.thread = PointCloudLoadThread(file_path)
        self.thread.progress.connect(self.progress.setLabelText)
        self.thread.finished.connect(self.on_loaded)

        self.thread.start()

    # ================= 加载完成 =================
    def on_loaded(self, points):

        self.progress.close()

        if points is None:
            return

        self.points = points

        # 先销毁旧窗口（关键）
        if self.vis:
            self.vis.destroy_window()
            self.vis = None

        #弹窗询问
        reply = QMessageBox.question(
            self,
            "点云预处理",
            "是否对点云进行滤波处理？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        # 构建 + 滤波（此时没有窗口，最安全）
        pcd = build_pcd(points)
        if reply == QMessageBox.StandardButton.Yes:
            print("用户选择：进行滤波")
            pcd = safe_preprocess(pcd)
        else:
            print("用户选择：不滤波")

        self.pcd = pcd

        self.show_point_cloud()

    # ================= 显示 =================
    def show_point_cloud(self):

        self.vis = o3d.visualization.Visualizer()
        self.vis.create_window("Open3D", visible=True)
        self.vis.add_geometry(self.pcd)

        time.sleep(0.3)

        hwnd = win32gui.FindWindow(None, "Open3D")
        if hwnd == 0:
            print("找不到窗口")
            return

        qwindow = QWindow.fromWinId(hwnd)

        container = self.ui.open3dWidget
        layout = container.layout()

        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)

        # 清空旧控件
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget().deleteLater()

        widget = QWidget.createWindowContainer(qwindow)
        layout.addWidget(widget)

        self.timer.start(30)

    # ================= 刷新 =================
    def update_vis(self):
        if self.vis:
            self.vis.poll_events()
            self.vis.update_renderer()