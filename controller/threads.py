from PyQt6.QtCore import QThread, pyqtSignal
import open3d as o3d
import numpy as np


class PointCloudLoadThread(QThread):
    finished = pyqtSignal(object)
    progress = pyqtSignal(str)

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