"""主控制器 - 应用编排层，负责UI初始化、子模块创建与信号连接、文件加载、键盘事件"""

from PyQt6.QtWidgets import QMainWindow, QFileDialog, QProgressDialog, QMessageBox
from PyQt6.QtCore import Qt

from ui_test import Ui_MainWindow
from controller.threads import PointCloudLoadThread
from controller.visualization_manager import VisualizationManager
from controller.measurement_controller import MeasurementController, MeasuredDimensions
from controller.data_manager import DataManager

from core.pointcloud import build_pcd, safe_preprocess

from dialogs.preprocess_dialog import PreprocessDialog
from dialogs.warning_dialog import WarningDialog


class MainController(QMainWindow):
    """应用主窗口，将可视化、测量、数据三个子模块串联起来"""

    def __init__(self):
        super().__init__()

        # 1. 加载 UI
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.tableRecords.horizontalHeader().setStretchLastSection(True)

        # 2. 点云原始数据（不属于任何子模块）
        self.points = None
        self.pcd = None

        # 3. 创建子模块（依赖注入）
        self.vis_mgr = VisualizationManager(self)
        self.meas_ctrl = MeasurementController(self)
        self.data_mgr = DataManager(self.ui.tableRecords, self)

        # 4. 连接信号
        self._connect_ui_signals()
        self._connect_submodule_signals()

        self.showMaximized()

    # ---- UI信号连接 ----

    def _connect_ui_signals(self):
        """将 UI 按钮点击连接到对应的方法"""
        self.ui.btnLoad.clicked.connect(self.load_point_cloud)
        self.ui.btnSave.clicked.connect(self.export_data)
        self.ui.btnMeasure.clicked.connect(self.start_pick_mode)
        self.ui.btnMultiMeasure.clicked.connect(self.start_continuous_mode)
        self.ui.btnAuto.clicked.connect(self.measure_auto)
        self.ui.btnView.clicked.connect(self.vis_mgr.reset_view)
        self.ui.btnClear.clicked.connect(self.clear_measurements)
        self.ui.btnUndo.clicked.connect(self._on_undo)
        self.ui.btnRedo.clicked.connect(self._on_redo)
        self.ui.checkShowLength.toggled.connect(self._on_toggle_lines)

    # ---- 子模块信号连接 ----

    def _connect_submodule_signals(self):
        """将子模块的 Qt 信号连接到 UI 更新方法"""
        self.vis_mgr.distance_measured.connect(self._on_distance)
        self.vis_mgr.points_updated.connect(self._update_points_text)
        self.vis_mgr.mode_changed.connect(self.update_pick_button_states)
        self.meas_ctrl.measurement_complete.connect(self._on_auto_done)
        self.meas_ctrl.error_occurred.connect(lambda msg: QMessageBox.critical(self, "错误", msg))

    # ---- 加载点云 ----

    def load_point_cloud(self):
        """打开文件对话框，通过后台线程异步加载点云文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择点云", "", "*.ply *.pcd "#限定可选择的文件防止文件格式问题
        )
        if not file_path:
            return

        self.progress = QProgressDialog("加载中...", None, 0, 0, self)
        self.progress.show()

        self.thread = PointCloudLoadThread(file_path)
        self.thread.finished.connect(self._on_loaded)
        self.thread.start()

    def _on_loaded(self, points):
        """加载完成回调：预处理 -> 构建点云 -> 创建可视化窗口"""
        self.progress.close()

        if points is None:
            return

        self.points = points

        dialog = PreprocessDialog()
        if not dialog.exec():
            return

        pcd = build_pcd(points)
        if dialog.get_choice():
            pcd = safe_preprocess(pcd)

        self.pcd = pcd

        self.ui.labelPointCount.setText(
            DataManager.update_point_count(len(points), len(pcd.points))
        )

        # 首次调用创建窗口，后续调用只换点云数据
        self.vis_mgr.load_point_cloud(pcd, self.ui.open3dWidget)

    # ---- 选点模式 ----

    def start_pick_mode(self):
        """切换单次选点模式：无点云时警告，已激活时退出"""
        if self.pcd is None:
            WarningDialog().exec()
            return

        if self.vis_mgr.is_picking:
            self._exit_pick_mode()
            return

        if self.vis_mgr.is_continuous:
            self.vis_mgr.stop_pick()

        self.vis_mgr.start_pick()
        self.update_pick_button_states()
        self.ui.textPoints.setText("")
        self.ui.textPoints.setPlaceholderText("Ctrl+Shift+点击选择2个点...")
        self.ui.labelPickStatus.setText("💡 单次测量：Ctrl+Shift+点击选择2个点")

    def start_continuous_mode(self):
        """切换连续选点模式：无点云时警告，已激活时退出"""
        if self.pcd is None:
            WarningDialog().exec()
            return

        if self.vis_mgr.is_continuous:
            self._exit_pick_mode()
            return

        if self.vis_mgr.is_picking:
            self.vis_mgr.stop_pick()

        self.vis_mgr.start_continuous()
        self.update_pick_button_states()
        self.ui.textPoints.setText("")
        self.ui.textPoints.setPlaceholderText("Ctrl+Shift+点击连续选点...")
        self.ui.labelPickStatus.setText("💡 连续测量：Ctrl+Shift+点击，每2个点计算距离")

    def _exit_pick_mode(self):
        """退出所有选点模式，重置右侧面板显示"""
        self.vis_mgr.stop_pick()
        self.update_pick_button_states()
        self.ui.textPoints.setText("")
        self.ui.textPoints.setPlaceholderText("Ctrl+Shift+点击选择点...")
        self.ui.editDistance.setText("0.00")
        self.ui.labelPickStatus.setText("💡 提示：按住Ctrl+Shift点击点云选点")

    # ---- 选点回调 ----

    def _on_distance(self, d):
        """PointPicker 测距回调：更新显示并记录到表格"""
        self.ui.editDistance.setText(f"{d:.3f} m")
        self.data_mgr.add_record("手动测量", d)

    def _update_points_text(self, points):
        """PointPicker 选点变化回调：更新坐标文本显示"""
        text = ""
        for i, p in enumerate(points):
            text += f"点{i + 1}: ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})\n"
        self.ui.textPoints.setText(text)

    def update_pick_button_states(self):
        """根据当前选点模式切换按钮的 CSS active 状态和文字"""
        if self.vis_mgr.picker is None:
            return

        if self.vis_mgr.is_picking:
            self.ui.btnMeasure.setProperty("class", "active")
            self.ui.btnMeasure.setText("📍 选点中... (点击退出)")
        else:
            self.ui.btnMeasure.setProperty("class", "")
            self.ui.btnMeasure.setText("📍 点选测量")

        if self.vis_mgr.is_continuous:
            self.ui.btnMultiMeasure.setProperty("class", "active")
            self.ui.btnMultiMeasure.setText("🔗 连续测量中... (点击退出)")
        else:
            self.ui.btnMultiMeasure.setProperty("class", "")
            self.ui.btnMultiMeasure.setText("🔗 连续测量")

        # 强制刷新 Qt 样式表
        self.ui.btnMeasure.style().unpolish(self.ui.btnMeasure)
        self.ui.btnMeasure.style().polish(self.ui.btnMeasure)
        self.ui.btnMultiMeasure.style().unpolish(self.ui.btnMultiMeasure)
        self.ui.btnMultiMeasure.style().polish(self.ui.btnMultiMeasure)

    def _on_undo(self):
        self.vis_mgr.undo()
        points = self.vis_mgr.get_points()
        self._update_points_text(points)
        if len(points) < 2:
            self.ui.editDistance.setText("0.00")

    def _on_redo(self):
        self.vis_mgr.redo()
        points = self.vis_mgr.get_points()
        self._update_points_text(points)
        if len(points) >= 2:
            distance = self.vis_mgr.get_last_distance()
            self.ui.editDistance.setText(f"{distance:.3f} m")

    # ---- 自动测量 ----

    def measure_auto(self):
        """执行自动测量：先停止手动选点，再委托给 MeasurementController"""
        if self.vis_mgr.picker:
            self.vis_mgr.stop_pick()
            self.update_pick_button_states()

        if self.pcd is None:
            WarningDialog().exec()
            return

        self.meas_ctrl.run_auto_measurement(self.pcd, self.vis_mgr)

    def _on_auto_done(self, result):
        """自动测量完成：更新右侧面板和表格"""
        self.ui.editBodyLength.setText(f"体长：{result.length:.3f}")
        self.ui.editHeight.setText(f"体高：{result.height:.3f}")
        self.ui.editWidth.setText(f"体宽：{result.width:.3f}")
        self.ui.editChest.setText(f"胸围：{result.chest:.3f}")

        self.data_mgr.set_auto_results(result.to_dict())

        self.data_mgr.add_record("体长", result.length)
        self.data_mgr.add_record("体高", result.height)
        self.data_mgr.add_record("体宽", result.width)
        self.data_mgr.add_record("胸围", result.chest)

    def _on_toggle_lines(self, checked):
        """切换测量线/OBB/网格的显示与隐藏"""
        self.meas_ctrl.toggle_measurement_lines(self.vis_mgr, checked)

    # ---- 导出 ----

    def export_data(self):
        """委托 DataManager 执行完整导出流程"""
        self.data_mgr.export_data(self)

    # ---- 清空 ----

    def clear_measurements(self):
        """清空所有测量数据：停止选点、清空表格、清除 Picker 几何体"""
        if self.vis_mgr.picker:
            self.vis_mgr.stop_pick()
            self.update_pick_button_states()

        self.data_mgr.clear_records()

        if self.vis_mgr.picker:
            self.vis_mgr.clear_picker()

        self.vis_mgr.update_renderer()

    # ---- 键盘 ----

    def keyPressEvent(self, event):
        """Escape 键退出选点模式"""
        if event.key() == Qt.Key.Key_Escape:
            self._exit_pick_mode()
        super().keyPressEvent(event)
