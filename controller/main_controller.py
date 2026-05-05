from PyQt6.QtWidgets import QMainWindow, QFileDialog, QVBoxLayout, QProgressDialog, QWidget, QMessageBox, \
    QTableWidgetItem
from PyQt6.QtGui import QWindow
from PyQt6.QtCore import QTimer, Qt

from ui_test import Ui_MainWindow
from controller.threads import PointCloudLoadThread

from core.pointcloud import build_pcd, safe_preprocess
from core.pointcloud import measure_dimensions_obb
from core.pointcloud import measure_chest_circumference
from core.pointcloud import create_chest_ellipse_geometry
from core.pointcloud import poisson_reconstruct
from core.pointcloud import measure_chest_concave_hull
from core.pointcloud import create_chest_concave_hull_geometry

from core.picking.picker import PointPicker

from core.export import MeasurementExporter

from dialogs.preprocess_dialog import PreprocessDialog
from dialogs.warning_dialog import WarningDialog
from dialogs.mode_dialog import ModeDialog
from dialogs.export_dialog import ExportDialog
from dialogs.no_data_dialog import NoDataDialog

import open3d as o3d
import win32gui
import time
import numpy as np
from datetime import datetime
import os


class MainController(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 表格
        self.ui.tableRecords.horizontalHeader().setStretchLastSection(True)

        # 按钮
        self.ui.btnLoad.clicked.connect(self.load_point_cloud)
        self.ui.btnSave.clicked.connect(self.export_data)
        self.ui.btnMeasure.clicked.connect(self.start_pick_mode)  # 改为切换模式
        self.ui.btnMultiMeasure.clicked.connect(self.start_continuous_mode)  # 改为切换模式
        self.ui.btnAuto.clicked.connect(self.measure_auto)
        self.ui.btnView.clicked.connect(self.reset_view)

        self.ui.btnClear.clicked.connect(self.clear_measurements)
        self.ui.btnUndo.clicked.connect(self.undo_pick)
        self.ui.btnRedo.clicked.connect(self.redo_pick)

        # 数据
        self.vis = None
        self.pcd = None
        self.points = None

        # 几何
        self.dimension_lines = []
        self.obb = None
        self.ellipse = None
        self.concave = None

        # 自动测量结果缓存（用于导出）
        self.auto_measurement_results = {}

        # picker
        self.picker = None
        self.o3d_hwnd = None

        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_vis)
        self.showMaximized()

    # ================= 加载 =================

    def load_point_cloud(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择点云", "", "*.ply *.pcd *.xyz *.txt"
        )
        if not file_path:
            return

        self.progress = QProgressDialog("加载中...", None, 0, 0, self)
        self.progress.show()

        self.thread = PointCloudLoadThread(file_path)
        self.thread.finished.connect(self.on_loaded)
        self.thread.start()

    def on_loaded(self, points):
        self.progress.close()

        if points is None:
            return

        self.points = points

        if self.vis:
            # 退出选点模式
            if self.picker:
                self.picker.stop()
                self.update_pick_button_states()
            self.vis.destroy_window()

        dialog = PreprocessDialog()
        if not dialog.exec():
            return

        pcd = build_pcd(points)
        if dialog.get_choice():
            pcd = safe_preprocess(pcd)

        self.pcd = pcd

        self.ui.labelPointCount.setText(
            f"原始：{len(points)} | 处理后：{len(pcd.points)}"
        )

        self.show_point_cloud()

    # ================= 显示 =================

    def show_point_cloud(self):
        self.vis = o3d.visualization.Visualizer()
        self.vis.create_window("PointCloudView", 800, 600)
        self.vis.add_geometry(self.pcd)

        opt = self.vis.get_render_option()
        opt.point_size = 3.0

        time.sleep(0.3)

        self.o3d_hwnd = win32gui.FindWindow(None, "PointCloudView")

        qwindow = QWindow.fromWinId(self.o3d_hwnd)

        container = self.ui.open3dWidget
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        widget = QWidget.createWindowContainer(qwindow)
        layout.addWidget(widget)

        # 每次重建 picker
        self.picker = PointPicker(self.vis, self.pcd)
        self.picker.bind_window(self.o3d_hwnd)
        self.picker.set_callbacks(
            on_distance=self.on_distance,
            on_points_updated=self.update_points_text
        )

        # 连接模式切换信号
        self.picker.on_mode_changed = self.update_pick_button_states

        self.timer.start(30)

    def update_vis(self):
        if self.vis:
            self.vis.poll_events()
            self.vis.update_renderer()

            if self.picker:
                self.picker.update()

    # ================= 导出 =================
    def export_data(self):
        # 获取表格数据
        table_data = self.get_table_data()

        measurement_summary = self._get_measurement_summary()

        has_table_data = len(table_data) > 0
        has_summary = len(measurement_summary) > 0

        if not has_table_data and not has_summary:
            # 完全没有数据时，显示提示对话框
            self._show_no_data_dialog()
            return

        if not has_table_data and has_summary:
            # 有摘要但没有表格数据时，确认是否导出
            reply = QMessageBox.question(
                self,
                "导出确认",
                "当前没有测量记录明细，\n是否仅导出测量结果摘要？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.No:
                return

        # 选择导出格式
        dialog = ExportDialog(self)
        if not dialog.exec():
            return

        export_format = dialog.get_format()

        # 选择保存路径
        file_filters = {
            "csv": "CSV 文件 (*.csv)",
            "xlsx": "Excel 文件 (*.xlsx)",
            "txt": "文本文件 (*.txt)"
        }

        default_name = f"测量报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存测量报告", default_name, file_filters.get(export_format, "所有文件 (*.*)")
        )

        if not file_path:
            return

        # 执行导出
        success, message = self.do_export(file_path, export_format, table_data)

        if success:
            QMessageBox.information(self, "导出成功", f"测量数据已成功导出到：\n{file_path}")
            # 打开文件所在目录
            os.startfile(os.path.dirname(file_path))
        else:
            QMessageBox.critical(self, "导出失败", message)

    def _get_measurement_summary(self):
        summary = {}

        # 优先使用缓存的自动测量结果
        if self.auto_measurement_results:
            summary.update(self.auto_measurement_results)
            return summary

        # 从右侧面板获取
        body_text = self.ui.editBodyLength.text().strip()
        width_text = self.ui.editWidth.text().strip()
        height_text = self.ui.editHeight.text().strip()
        chest_text = self.ui.editChest.text().strip()

        try:
            if body_text and body_text != "0.00" and body_text != "":
                summary["体长"] = float(body_text)
        except ValueError:
            pass

        try:
            if width_text and width_text != "0.00" and width_text != "":
                summary["体高"] = float(width_text)
        except ValueError:
            pass

        try:
            if height_text and height_text != "0.00" and height_text != "":
                summary["体宽"] = float(height_text)
        except ValueError:
            pass

        try:
            if chest_text and chest_text != "0.00" and chest_text != "":
                summary["胸围"] = float(chest_text)
        except ValueError:
            pass

        return summary

    def _show_no_data_dialog(self):
        """显示无数据提示对话框"""
        dialog = NoDataDialog(self)
        dialog.exec()

    def get_table_data(self):
        """获取表格中的所有数据"""
        table = self.ui.tableRecords
        data = []

        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)

        return data

    def do_export(self, file_path, export_format, table_data, measurement_summary=None):

        if measurement_summary is None:
            measurement_summary = {}

        if export_format == "csv":
            return MeasurementExporter.export_to_csv(file_path, table_data, measurement_summary)
        elif export_format == "xlsx":
            return MeasurementExporter.export_to_xlsx(file_path, table_data, measurement_summary)
        elif export_format == "txt":
            return MeasurementExporter.export_to_txt(file_path, table_data, measurement_summary)
        else:
            return False, "不支持的导出格式"


    # ================= Picker UI =================

    def on_distance(self, d):
        self.ui.editDistance.setText(f"{d:.3f} m")
        self.add_measurement_record("手动测量", d)

    def update_points_text(self, points):
        text = ""
        for i, p in enumerate(points):
            text += f"点{i + 1}: ({p[0]:.3f},{p[1]:.3f},{p[2]:.3f})\n"
        self.ui.textPoints.setText(text)

    # ================= 模式切换 =================

    def start_pick_mode(self):
        if self.pcd is None:
            WarningDialog().exec()
            return

        # 如果已经处于单次选点模式，则退出
        if self.picker and self.picker.picking_mode:
            self.exit_pick_mode()
            return

        # 退出连续模式（如果有）
        if self.picker and self.picker.continuous_mode:
            self.picker.stop()

        # 开始单次选点
        if self.picker:
            self.picker.start_pick()
            self.update_pick_button_states()
            self.ui.textPoints.setText("")
            self.ui.textPoints.setPlaceholderText("Ctrl+Shift+点击选择2个点...")
            self.ui.labelPickStatus.setText("💡 单次测量：Ctrl+Shift+点击选择2个点")

    def start_continuous_mode(self):
        if self.pcd is None:
            WarningDialog().exec()
            return

        # 如果已经处于连续模式，则退出
        if self.picker and self.picker.continuous_mode:
            self.exit_pick_mode()
            return

        # 退出单次模式（如果有）
        if self.picker and self.picker.picking_mode:
            self.picker.stop()

        # 开始连续选点
        if self.picker:
            self.picker.start_continuous()
            self.update_pick_button_states()
            self.ui.textPoints.setText("")
            self.ui.textPoints.setPlaceholderText("Ctrl+Shift+点击连续选点...")
            self.ui.labelPickStatus.setText("💡 连续测量：Ctrl+Shift+点击，每2个点计算距离")

    def exit_pick_mode(self):
        if self.picker:
            self.picker.stop()

        self.update_pick_button_states()
        self.ui.textPoints.setText("")
        self.ui.textPoints.setPlaceholderText("Ctrl+Shift+点击选择点...")
        self.ui.editDistance.setText("0.00")
        self.ui.labelPickStatus.setText("💡 提示：按住Ctrl+Shift点击点云选点")

    def on_distance(self, d):
        """手动测量距离回调"""
        self.ui.editDistance.setText(f"{d:.3f} m")
        self.add_measurement_record("手动测量", d)

    def update_points_text(self, points):
        text = ""
        for i, p in enumerate(points):
            text += f"点{i + 1}: ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})\n"
        self.ui.textPoints.setText(text)

    def update_pick_button_states(self):
        """更新按钮状态 - 使用CSS属性选择器"""
        if self.picker is None:
            return

        # 单次测量按钮
        if self.picker.picking_mode:
            self.ui.btnMeasure.setProperty("class", "active")
            self.ui.btnMeasure.setText("📍 选点中... (点击退出)")
        else:
            self.ui.btnMeasure.setProperty("class", "")
            self.ui.btnMeasure.setText("📍 点选测量")

        # 连续测量按钮
        if self.picker.continuous_mode:
            self.ui.btnMultiMeasure.setProperty("class", "active")
            self.ui.btnMultiMeasure.setText("🔗 连续测量中... (点击退出)")
        else:
            self.ui.btnMultiMeasure.setProperty("class", "")
            self.ui.btnMultiMeasure.setText("🔗 连续测量")

        # 强制刷新样式
        self.ui.btnMeasure.style().unpolish(self.ui.btnMeasure)
        self.ui.btnMeasure.style().polish(self.ui.btnMeasure)
        self.ui.btnMultiMeasure.style().unpolish(self.ui.btnMultiMeasure)
        self.ui.btnMultiMeasure.style().polish(self.ui.btnMultiMeasure)

    # 撤销
    def undo_pick(self):
        if self.picker:
            self.picker.undo()
            # 更新显示
            points = self.picker.get_points()
            self.update_points_text(points)
            if len(points) < 2:
                self.ui.editDistance.setText("0.00")

    # 重做
    def redo_pick(self):
        if self.picker:
            self.picker.redo()
            # 更新显示
            points = self.picker.get_points()
            self.update_points_text(points)
            # 如果有2个或以上的点，计算最后一个距离
            if len(points) >= 2:
                distance = self.picker.get_last_distance()
                self.ui.editDistance.setText(f"{distance:.3f} m")

    def reset_view(self):
        if self.vis:
            self.vis.reset_view_point(True)

    # ================= 自动测量 =================

    def measure_auto(self):
        # 停止选点
        if self.picker:
            self.picker.stop()
            self.update_pick_button_states()

        if self.pcd is None:
            WarningDialog().exec()
            return

        dialog = ModeDialog()
        if not dialog.exec():
            return

        # 清理旧几何
        for g in self.dimension_lines:
            self.vis.remove_geometry(g, False)
        self.dimension_lines = []

        if self.obb:
            self.vis.remove_geometry(self.obb, False)
            self.obb = None

        if self.ellipse:
            self.vis.remove_geometry(self.ellipse, False)
            self.ellipse = None

        if self.concave:
            self.vis.remove_geometry(self.concave, False)
            self.concave = None

        try:
            mode = dialog.get_mode()

            if mode == "simple":
                length, width, height, center, axes, endpoints, obb = measure_dimensions_obb(self.pcd)
                chest = measure_chest_circumference(self.pcd)

                self.ellipse, _, _ = create_chest_ellipse_geometry(self.pcd)
                self.concave = None

            else:
                mesh = poisson_reconstruct(self.pcd)
                pcd_dense = mesh.sample_points_poisson_disk(50000)

                length, width, height, center, axes, endpoints, obb = measure_dimensions_obb(pcd_dense)
                chest = measure_chest_concave_hull(pcd_dense)

                self.concave = create_chest_concave_hull_geometry(pcd_dense)
                self.ellipse = None

            self.obb = obb
            self.obb.color = (1, 1, 0)

            self.dimension_lines = self.create_dimension_lines(endpoints)

            # 添加几何
            self.vis.add_geometry(self.obb, False)

            for g in self.dimension_lines:
                self.vis.add_geometry(g, False)

            if self.ellipse:
                self.vis.add_geometry(self.ellipse, False)

            if self.concave:
                self.vis.add_geometry(self.concave, False)

            self.vis.update_renderer()

            # UI
            self.ui.editBodyLength.setText(f"{length:.3f}")
            self.ui.editWidth.setText(f"{width:.3f}")
            self.ui.editHeight.setText(f"{height:.3f}")
            self.ui.editChest.setText(f"{chest:.3f}")

            # 缓存测量结果供导出使用
            self.auto_measurement_results = {
                "体长": length,
                "体高": width,
                "体宽": height,
                "胸围": chest
            }

            # 表格
            self.add_measurement_record("体长", length)
            self.add_measurement_record("体高", width)
            self.add_measurement_record("体宽", height)
            self.add_measurement_record("胸围", chest)

        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))

    # ================= 几何 =================

    def create_dimension_lines(self, endpoints):
        colors = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        geoms = []

        for i, (p1, p2) in enumerate(endpoints):
            line = o3d.geometry.LineSet()
            line.points = o3d.utility.Vector3dVector([p1, p2])
            line.lines = o3d.utility.Vector2iVector([[0, 1]])
            line.colors = o3d.utility.Vector3dVector([colors[i]])
            geoms.append(line)

        return geoms

    # ================= 表格 =================

    def add_measurement_record(self, m_type, value):
        table = self.ui.tableRecords
        row = table.rowCount()
        table.insertRow(row)

        table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        table.setItem(row, 1, QTableWidgetItem(m_type))
        table.setItem(row, 2, QTableWidgetItem(f"{value:.3f}"))
        table.setItem(row, 3, QTableWidgetItem("m"))

        now = datetime.now().strftime("%H:%M:%S")
        table.setItem(row, 4, QTableWidgetItem(now))

    def clear_measurements(self):
        # 退出选点模式
        if self.picker:
            self.picker.stop()
            self.update_pick_button_states()

        self.ui.tableRecords.setRowCount(0)

        if self.picker:
            self.picker.clear()

        if self.vis:
            self.vis.update_renderer()

    # ================= 键盘 =================

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.exit_pick_mode()

        super().keyPressEvent(event)