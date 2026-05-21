"""后台线程模块 - 异步加载点云文件，避免阻塞UI"""

from PyQt6.QtCore import QThread, pyqtSignal
import open3d as o3d
import numpy as np


class PointCloudLoadThread(QThread):
    """在后台线程中加载点云文件，加载完成后通过信号通知主线程"""

    finished = pyqtSignal(object)  # 发射 numpy 点数组，失败时发射 None
    progress = pyqtSignal(str)     # 发射加载进度描述

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        self.progress.emit("读取点云...")

        pcd = o3d.io.read_point_cloud(self.file_path)

        if pcd.is_empty():
            self.finished.emit(None)
            return

        points = np.asarray(pcd.points)

        self.progress.emit(f"加载完成: {len(points)} 点")

        self.finished.emit(points)
