"""可视化模块 - 管理 Open3D 可视化窗口生命周期和点选交互
窗口只创建一次，后续加载文件只换点云数据，避免重复创建窗口导致的崩溃
"""

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QWindow
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from core.picker import PointPicker

import open3d as o3d
import win32gui
import time


class VisualizationManager(QObject):
    """管理 Open3D 渲染窗口，首次加载创建窗口，后续加载只换点云数据"""

    distance_measured = pyqtSignal(float)
    points_updated = pyqtSignal(list)
    mode_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vis = None
        self.pcd = None
        self.picker = None
        self.o3d_hwnd = None
        self._container = None
        self._container_layout = None
        self._initialized = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_vis)

    @property
    def is_picking(self):
        return self.picker is not None and self.picker.picking_mode

    @property
    def is_continuous(self):
        return self.picker is not None and self.picker.continuous_mode

    # ---- 窗口生命周期 ----

    def load_point_cloud(self, pcd, container_widget):
        """加载点云：首次创建窗口，后续只换数据"""
        if self._initialized:
            self._swap_data(pcd)
        else:
            self._init_window(pcd, container_widget)
        self.pcd = pcd

    def _init_window(self, pcd, container_widget):
        """首次：创建 Open3D 窗口并嵌入 Qt"""
        self.vis = o3d.visualization.Visualizer()
        self.vis.create_window("PointCloudView", 800, 600)
        self.vis.add_geometry(pcd)

        opt = self.vis.get_render_option()
        opt.point_size = 3.0

        time.sleep(0.3)

        self.o3d_hwnd = win32gui.FindWindow(None, "PointCloudView")
        qwindow = QWindow.fromWinId(self.o3d_hwnd)

        self._container = container_widget
        self._container_layout = QVBoxLayout(container_widget)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        widget = QWidget.createWindowContainer(qwindow)
        self._container_layout.addWidget(widget)

        self._create_picker(pcd)
        self._timer.start(30)
        self._initialized = True

    def _swap_data(self, pcd):
        """后续加载：移除旧点云，添加新点云，重建 Picker"""
        self.vis.remove_geometry(self.pcd, False)
        self.vis.add_geometry(pcd, False)
        self.pcd = pcd

        self.picker.rebind_pcd(pcd)
        self.vis.reset_view_point(True)
        self.vis.update_renderer()

    def _create_picker(self, pcd):
        """创建 PointPicker 并将回调桥接为 Qt 信号"""
        self.picker = PointPicker(self.vis, pcd)
        self.picker.bind_window(self.o3d_hwnd)
        self.picker.set_callbacks(
            on_distance=lambda d: self.distance_measured.emit(d),
            on_points_updated=lambda pts: self.points_updated.emit(pts),
        )
        self.picker.on_mode_changed = lambda: self.mode_changed.emit()

    def destroy(self):
        """彻底销毁窗口（程序退出时调用）"""
        self._timer.stop()

        if self.picker:
            self.picker.stop()
            self.picker = None

        if self.vis:
            self.vis.destroy_window()
            self.vis = None

        self.o3d_hwnd = None
        self.pcd = None
        self._initialized = False

        if self._container_layout:
            while self._container_layout.count():
                item = self._container_layout.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)
            self._container_layout.setParent(None)
            self._container_layout = None
            self._container = None

    # ---- 内部更新循环 ----

    def _update_vis(self):
        if self.vis:
            self.vis.poll_events()
            self.vis.update_renderer()
            if self.picker:
                self.picker.update()

    # ---- 选点模式 ----

    def start_pick(self):
        if self.picker:
            self.picker.start_pick()

    def start_continuous(self):
        if self.picker:
            self.picker.start_continuous()

    def stop_pick(self):
        if self.picker:
            self.picker.stop()

    def undo(self):
        if self.picker:
            self.picker.undo()

    def redo(self):
        if self.picker:
            self.picker.redo()

    def clear_picker(self):
        if self.picker:
            self.picker.clear()

    def get_points(self):
        if self.picker:
            return self.picker.get_points()
        return []

    def get_last_distance(self):
        if self.picker:
            return self.picker.get_last_distance()
        return 0.0

    # ---- 几何体操作 ----

    def add_geometry(self, geom, reset_bounding_box=True):
        if self.vis:
            self.vis.add_geometry(geom, reset_bounding_box)

    def remove_geometry(self, geom, reset_bounding_box=True):
        if self.vis:
            self.vis.remove_geometry(geom, reset_bounding_box)

    def update_renderer(self):
        if self.vis:
            self.vis.update_renderer()

    def reset_view(self):
        if self.vis:
            self.vis.reset_view_point(True)
