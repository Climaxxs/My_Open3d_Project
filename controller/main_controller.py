from PyQt6.QtWidgets import QMainWindow, QFileDialog, QVBoxLayout, QProgressDialog, QWidget, QMessageBox, \
    QTableWidgetItem
from PyQt6.QtGui import QWindow
from PyQt6.QtCore import QTimer

from ui_test import Ui_MainWindow
from controller.threads import PointCloudLoadThread
from core.pointcloud import build_pcd, safe_preprocess
from core.pointcloud import measure_dimensions_obb
from core.pointcloud import measure_chest_circumference
from core.pointcloud import create_chest_ellipse_geometry
from core.pointcloud import poisson_reconstruct
from core.pointcloud import measure_chest_convex_hull
from core.pointcloud import create_chest_convex_hull_geometry
from core.pointcloud import measure_chest_concave_hull
from core.pointcloud import create_chest_concave_hull_geometry
from core.pointcloud import create_test_cylinder
from dialogs.preprocess_dialog import PreprocessDialog
from dialogs.warning_dialog import WarningDialog
from dialogs.mode_dialog import ModeDialog

import open3d as o3d
import win32gui
import time
from datetime import datetime


class MainController(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 表格初始化
        self.ui.tableRecords.horizontalHeader().setStretchLastSection(True)
        self.ui.tableRecords.setColumnWidth(0, 60)
        self.ui.tableRecords.setColumnWidth(1, 80)
        self.ui.tableRecords.setColumnWidth(2, 80)

        self.ui.btnLoad.clicked.connect(self.load_point_cloud)
        self.ui.btnAuto.clicked.connect(self.measure_auto)
        self.ui.checkShowLength.stateChanged.connect(self.toggle_dimension_lines)
        self.ui.btnClear.clicked.connect(self.clear_measurements)

        self.vis = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_vis)

        self.points = None
        self.pcd = None

        # 几何体引用
        self.dimension_lines = []  # 三条测量线
        self.show_length = True
        self.obb = None
        self.ellipse = None
        self.hull = None
        self.concave = None

    # ==================== 加载 ====================

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

    def on_loaded(self, points):

        self.progress.close()

        if points is None:
            return

        self.points = points

        # 先销毁旧窗口
        if self.vis:
            self.vis.destroy_window()
            self.vis = None

        # 弹窗询问是否预处理
        dialog = PreprocessDialog()

        if dialog.exec():
            do_preprocess = dialog.get_choice()
        else:
            return

        # 构建 + 滤波
        pcd = build_pcd(points)
        if do_preprocess:
            print("用户选择：预处理")
            pcd = safe_preprocess(pcd)
        else:
            print("用户选择：直接加载")
        self.pcd = pcd

        original_count = len(points)
        processed_count = len(pcd.points)

        self.ui.labelPointCount.setText(
            f"原始：{original_count} | 处理后：{processed_count}"
        )

        self.show_point_cloud()

    # ==================== 显示 ====================

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

    def update_vis(self):
        if self.vis:
            self.vis.poll_events()
            self.vis.update_renderer()

    # ==================== 测量（核心修改）====================

    def measure_auto(self):

        dialog = ModeDialog()
        if not dialog.exec():
            return

        mode = dialog.get_mode()

        # 防御：没有点云不允许测量
        if self.pcd is None:
            dialog = WarningDialog()
            dialog.exec()
            return

        try:
            if mode == "simple":
                # ------ 简单模式 ------
                length, width, height, center, axes, endpoints, obb = measure_dimensions_obb(self.pcd)

                # 胸围：用最小二乘椭圆拟合（默认 method='ls'）
                chest = measure_chest_circumference(self.pcd, method='ls')
                # 椭圆可视化
                ellipse, a, b = create_chest_ellipse_geometry(self.pcd, method='PCA')

                self.ellipse = ellipse
                self.hull = None
                self.concave = None

                print(f"简单测量完成：体长={length:.3f}, 胸围={chest:.3f}, a={a:.3f}, b={b:.3f}")

            elif mode == "precise":
                # ------ 精细模式 ------
                print("精细测量：泊松重建中...")

                mesh = poisson_reconstruct(self.pcd)

                # 转回点云（用于 OBB）
                pcd_dense = mesh.sample_points_poisson_disk(50000)

                length, width, height, center, axes, endpoints, obb = measure_dimensions_obb(pcd_dense)

                # 胸围：凹包法
                chest = measure_chest_concave_hull(pcd_dense)

                self.ellipse = None
                self.hull = None
                self.concave = create_chest_concave_hull_geometry(pcd_dense)

                print(f"精细测量完成：体长={length:.3f}, 胸围={chest:.3f}")

            # ===== 更新 UI =====
            self.ui.editBodyLength.setText(f"体长：{length:.3f} m")
            self.ui.editWidth.setText(f"体高：{width:.3f} m")
            self.ui.editHeight.setText(f"体宽：{height:.3f} m")
            self.ui.editChest.setText(f"胸围: {chest:.3f} m")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"测量失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return

        # ===== 清理旧几何 =====
        if hasattr(self, "dimension_lines"):
            for g in self.dimension_lines:
                self.vis.remove_geometry(g, False)

        if self.obb:
            self.vis.remove_geometry(self.obb, False)

        if self.ellipse:
            self.vis.remove_geometry(self.ellipse, False)

        if self.hull:
            self.vis.remove_geometry(self.hull, False)

        if self.concave:
            self.vis.remove_geometry(self.concave, False)

        # ===== 创建新几何 =====
        self.dimension_lines = self.create_dimension_lines(endpoints)

        self.obb = obb
        self.obb.color = (1, 1, 0)  # 黄色 OBB 盒子

        # ===== 显示几何 =====
        if self.ui.checkShowLength.isChecked():
            for g in self.dimension_lines:
                self.vis.add_geometry(g, False)
            self.vis.add_geometry(self.obb, False)

        if self.ellipse:
            self.vis.add_geometry(self.ellipse, False)

        if self.hull:
            self.vis.add_geometry(self.hull, False)

        if self.concave:
            self.vis.add_geometry(self.concave, False)

        self.vis.update_renderer()

        # ===== 写入表格 =====
        self.add_measurement_record("体长", length)
        self.add_measurement_record("体高", width)
        self.add_measurement_record("体宽", height)
        self.add_measurement_record("胸围", chest)

    # ==================== 辅助方法 ====================

    def create_dimension_lines(self, endpoints):

        colors = [
            [1, 0, 0],  # 红：体长
            [0, 1, 0],  # 绿：体宽
            [0, 0, 1],  # 蓝：体高
        ]

        geometries = []

        for i, (p1, p2) in enumerate(endpoints):
            line = o3d.geometry.LineSet()
            line.points = o3d.utility.Vector3dVector([p1, p2])
            line.lines = o3d.utility.Vector2iVector([[0, 1]])
            line.colors = o3d.utility.Vector3dVector([colors[i]])
            geometries.append(line)

        return geometries

    def toggle_dimension_lines(self):

        if not hasattr(self, "dimension_lines"):
            return

        show = self.ui.checkShowLength.isChecked()

        for g in self.dimension_lines:
            if show:
                self.vis.add_geometry(g, False)
            else:
                self.vis.remove_geometry(g, False)

        if self.obb:
            if show:
                self.vis.add_geometry(self.obb, False)
            else:
                self.vis.remove_geometry(self.obb, False)

        if self.ellipse:
            if show:
                self.vis.add_geometry(self.ellipse, False)
            else:
                self.vis.remove_geometry(self.ellipse, False)

        if self.hull:
            if show:
                self.vis.add_geometry(self.hull, False)
            else:
                self.vis.remove_geometry(self.hull, False)

        if self.concave:
            if show:
                self.vis.add_geometry(self.concave, False)
            else:
                self.vis.remove_geometry(self.concave, False)

        self.vis.update_renderer()

    # ==================== 表格 ====================

    def add_measurement_record(self, m_type, value):

        table = self.ui.tableRecords
        row = table.rowCount()
        table.insertRow(row)

        # 编号
        table.setItem(row, 0, QTableWidgetItem(str(row + 1)))

        # 类型
        table.setItem(row, 1, QTableWidgetItem(m_type))

        # 数值
        table.setItem(row, 2, QTableWidgetItem(f"{value:.3f}"))

        # 单位
        table.setItem(row, 3, QTableWidgetItem("m"))

        # 时间
        now = datetime.now().strftime("%H:%M:%S")
        table.setItem(row, 4, QTableWidgetItem(now))

    def clear_measurements(self):

        # 清表格
        self.ui.tableRecords.setRowCount(0)

        # 清几何
        if hasattr(self, "dimension_lines"):
            for g in self.dimension_lines:
                self.vis.remove_geometry(g, False)

        if self.obb:
            self.vis.remove_geometry(self.obb, False)
            self.obb = None

        if self.ellipse:
            self.vis.remove_geometry(self.ellipse, False)
            self.ellipse = None

        if self.hull:
            self.vis.remove_geometry(self.hull, False)
            self.hull = None

        if self.concave:
            self.vis.remove_geometry(self.concave, False)
            self.concave = None

        self.vis.update_renderer()