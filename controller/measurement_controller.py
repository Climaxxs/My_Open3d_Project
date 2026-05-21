"""自动测量模块 - OBB包围盒尺寸、胸围拟合、泊松重建管线"""

from PyQt6.QtCore import QObject, pyqtSignal

from core.pointcloud import (
    measure_dimensions_obb,
    measure_chest_circumference,
    create_chest_ellipse_geometry,
    create_chest_convex_hull_geometry,
    poisson_reconstruct,
    measure_chest_concave_hull,
    create_chest_concave_hull_geometry,
)
from dialogs.mode_dialog import ModeDialog

import open3d as o3d


class MeasuredDimensions:
    """自动测量结果数据容器
    """

    def __init__(self, length, width, height, chest):
        self.length = length  # 体长
        self.height = height  # 体高
        self.width = width    # 体宽
        self.chest = chest    # 胸围

    def to_dict(self):
        return {
            "体长": self.length,
            "体高": self.height,
            "体宽": self.width,
            "胸围": self.chest,
        }


class MeasurementController(QObject):
    """封装自动测量管线，通过 Qt 信号返回结果或错误"""

    measurement_complete = pyqtSignal(object)  # 携带 MeasuredDimensions 实例
    error_occurred = pyqtSignal(str)           # 携带错误消息

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dimension_lines = []
        self.obb = None
        self.ellipse = None
        self.convex_hull = None
        self.concave = None
        self.recon_mesh = None

    # ---- 公共接口 ----

    def run_auto_measurement(self, pcd, vis_mgr):
        """执行自动测量完整管线：模式选择 -> 清理旧几何 -> 测量 -> 添加新几何到可视化"""
        dialog = ModeDialog()
        if not dialog.exec():
            return False

        self.clear_geometries(vis_mgr)

        try:
            mode = dialog.get_mode()

            if mode == "simple":
                dims = self._measure_simple(pcd)
            else:
                dims = self._measure_precise(pcd)

            # OBB 颜色统一设为黄色
            self.obb.color = (1, 1, 0)

            vis_mgr.add_geometry(self.obb, False)
            for g in self.dimension_lines:
                vis_mgr.add_geometry(g, False)
            if self.ellipse:
                vis_mgr.add_geometry(self.ellipse, False)
            if self.convex_hull:
                vis_mgr.add_geometry(self.convex_hull, False)
            if self.concave:
                vis_mgr.add_geometry(self.concave, False)
            if self.recon_mesh:
                vis_mgr.add_geometry(self.recon_mesh, False)

            vis_mgr.update_renderer()
            self.measurement_complete.emit(dims)
            return True

        except Exception as e:
            self.error_occurred.emit(str(e))
            return False

    def clear_geometries(self, vis_mgr):
        """从可视化中移除所有当前测量的几何体"""
        self._remove_all_geometries(vis_mgr)
        self.dimension_lines = []
        self.obb = None
        self.ellipse = None
        self.convex_hull = None
        self.concave = None
        self.recon_mesh = None

    def toggle_measurement_lines(self, vis_mgr, visible):
        """切换测量线的显示/隐藏"""
        if visible:
            if self.obb:
                vis_mgr.add_geometry(self.obb, False)
            for g in self.dimension_lines:
                vis_mgr.add_geometry(g, False)
            if self.ellipse:
                vis_mgr.add_geometry(self.ellipse, False)
            if self.convex_hull:
                vis_mgr.add_geometry(self.convex_hull, False)
            if self.concave:
                vis_mgr.add_geometry(self.concave, False)
            if self.recon_mesh:
                vis_mgr.add_geometry(self.recon_mesh, False)
        else:
            self._remove_all_geometries(vis_mgr)
        vis_mgr.update_renderer()

    def _remove_all_geometries(self, vis_mgr):
        """移除所有几何体但保留引用（用于临时隐藏）"""
        for g in self.dimension_lines:
            vis_mgr.remove_geometry(g, False)
        if self.obb:
            vis_mgr.remove_geometry(self.obb, False)
        if self.ellipse:
            vis_mgr.remove_geometry(self.ellipse, False)
        if self.convex_hull:
            vis_mgr.remove_geometry(self.convex_hull, False)
        if self.concave:
            vis_mgr.remove_geometry(self.concave, False)
        if self.recon_mesh:
            vis_mgr.remove_geometry(self.recon_mesh, False)

    # ---- 内部测量管线 ----

    def _measure_simple(self, pcd):
        """简单模式：OBB + 椭圆拟合胸围"""
        length, width, height, center, axes, endpoints, obb = measure_dimensions_obb(pcd)
        chest = measure_chest_circumference(pcd)

        self.ellipse, _, _ = create_chest_ellipse_geometry(pcd)
        self.convex_hull = None
        self.concave = None
        self.recon_mesh = None
        self.obb = obb
        self.dimension_lines = self._create_dimension_lines(endpoints)

        return MeasuredDimensions(length, width, height, chest)

    def _measure_precise(self, pcd):
        """精细模式：泊松重建 + 凹包胸围"""
        mesh = poisson_reconstruct(pcd)
        pcd_dense = mesh.sample_points_poisson_disk(50000)

        length, width, height, center, axes, endpoints, obb = measure_dimensions_obb(pcd_dense)
        chest = measure_chest_concave_hull(pcd_dense)

        self.concave = create_chest_concave_hull_geometry(pcd_dense)
        self.convex_hull = None
        self.ellipse = None
        # self.recon_mesh = mesh
        # # 浅蓝色半透明显示泊松重建网格
        # self.recon_mesh.paint_uniform_color([0.3, 0.5, 0.9])
        # self.recon_mesh.compute_vertex_normals()
        self.obb = obb
        self.dimension_lines = self._create_dimension_lines(endpoints)

        return MeasuredDimensions(length, width, height, chest)

    def _create_dimension_lines(self, endpoints):
        """根据 OBB 端点创建三条彩色尺寸线 (RGB: 红/绿/蓝)"""
        colors = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        geoms = []

        for i, (p1, p2) in enumerate(endpoints):
            line = o3d.geometry.LineSet()
            line.points = o3d.utility.Vector3dVector([p1, p2])
            line.lines = o3d.utility.Vector2iVector([[0, 1]])
            line.colors = o3d.utility.Vector3dVector([colors[i]])
            geoms.append(line)

        return geoms
