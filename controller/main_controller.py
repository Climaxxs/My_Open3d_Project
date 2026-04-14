from PyQt6.QtWidgets import QMainWindow, QFileDialog
from ui_test import Ui_MainWindow
from core.pointcloud import load_point_cloud_file
import open3d as o3d
import win32gui
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QTimer
from PyQt6 import QtCore, QtGui
import numpy as np

# 导入鼠标点选处理器
from controller.mouse_point_picker import MousePointPicker


class MainController(QMainWindow):
    def __init__(self):
        super().__init__()

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # 连接按钮事件
        self.ui.btnLoad.clicked.connect(self.load_point_cloud)
        self.ui.btnMeasure.clicked.connect(self.toggle_measure_mode)
        self.ui.btnClear.clicked.connect(self.clear_measurements)

        # Open3D相关属性
        self.vis = None
        self.pcd = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_vis)

        # 鼠标选点相关属性
        self.point_picker = None
        self.is_measure_mode = False

        # 安装事件过滤器到open3dWidget
        self.ui.open3dWidget.installEventFilter(self)

    def load_point_cloud(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,"选择点云文件","",
            "Point Cloud Files (*.ply *.pcd *.xyz *.txt)"
        )

        if not file_path:
            return

        self.pcd = load_point_cloud_file(file_path)

        self.show_point_cloud()

    def show_point_cloud(self):
        if self.vis is not None:
            self.vis.destroy_window()
            self.point_picker = None

        self.vis = o3d.visualization.Visualizer()
        self.vis.create_window(window_name="Open3D",visible=True)

        self.vis.add_geometry(self.pcd)

        # 创建点选择器
        self.point_picker = MousePointPicker(
            self.vis, self.pcd, self.ui.open3dWidget
        )

        #获取Open3D窗口句柄
        hwnd = win32gui.FindWindow(None, "Open3D")

        # 获取Qt控件句柄
        widget = self.ui.open3dWidget
        widget_hwnd = int(widget.winId())

        # 嵌入窗口
        win32gui.SetParent(hwnd, widget_hwnd)

        # 调整大小
        win32gui.MoveWindow(
            hwnd,0,0,
            widget.width(),
            widget.height(),
            True
        )

        self.timer.start(30)

        # 更新统计信息
        if self.pcd:
            point_count = len(self.pcd.points) if self.pcd.points else 0
            self.ui.labelPointCount.setText(f"点云数量：{point_count}")

    def update_vis(self):
        if self.vis:
            self.vis.poll_events()
            self.vis.update_renderer()

    def toggle_measure_mode(self):
        """切换测量模式"""
        if self.point_picker is None:
            print("错误：点选择器未初始化，请先加载点云")
            return

        self.is_measure_mode = not self.is_measure_mode

        if self.is_measure_mode:
            self.point_picker.enable_picking_mode()
            self.ui.btnMeasure.setText("📍 退出点选")
            # 设置按钮为红色表示正在测量
            self.ui.btnMeasure.setStyleSheet("""
                QPushButton {
                    background-color: #d83b01;
                    border: none;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 10px 20px;
                    text-align: left;
                    min-height: 35px;
                }
                QPushButton:hover {
                    background-color: #e84b11;
                    padding-left: 25px;
                    transition: all 0.3s;
                }
            """)
        else:
            self.point_picker.disable_picking_mode()
            self.ui.btnMeasure.setText("📍 点选测量")
            # 恢复原始样式
            self.ui.btnMeasure.setStyleSheet("""
                QPushButton {
                    background-color: #2d5a2d;
                    border: none;
                    border-radius: 8px;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: bold;
                    padding: 10px 20px;
                    text-align: left;
                    min-height: 35px;
                }
                QPushButton:hover {
                    background-color: #3d6a3d;
                    padding-left: 25px;
                    transition: all 0.3s;
                }
            """)

    def eventFilter(self, obj, event):
        """事件过滤器处理鼠标点击"""
        if obj == self.ui.open3dWidget and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                # 获取鼠标位置
                pos = event.pos()
                screen_pos = self.ui.open3dWidget.mapToGlobal(pos)

                # 调试信息
                print(f"Qt事件过滤器捕获到点击: widget坐标({pos.x()}, {pos.y()}), 屏幕坐标({screen_pos.x()}, {screen_pos.y()})")

                if self.is_measure_mode and self.point_picker:
                    # 处理点选
                    selected_point = self.point_picker.handle_mouse_click(
                        screen_pos.x(), screen_pos.y()
                    )

                    if selected_point is not None:
                        self.update_selected_points_display(selected_point)
                        self.calculate_measurements()

                    return True  # 事件已处理
                else:
                    print(f"点击未处理: is_measure_mode={self.is_measure_mode}, point_picker={self.point_picker is not None}")

        return super().eventFilter(obj, event)

    def update_selected_points_display(self, point):
        """更新右侧面板显示选中的点"""
        if point is None:
            return

        # 格式化坐标显示
        point_text = f"({point[0]:.3f}, {point[1]:.3f}, {point[2]:.3f})"

        # 获取当前文本
        current_text = self.ui.textPoints.toPlainText()
        if current_text:
            current_text += "\n"
        current_text += point_text

        # 更新显示
        self.ui.textPoints.setPlainText(current_text)

        # 更新统计信息：选中的点数量
        if self.point_picker:
            selected_count = self.point_picker.get_selected_points_count()
            self.ui.labelPointCount.setText(f"点云数量：{len(self.pcd.points) if self.pcd else 0} | 选中的点：{selected_count}")

    def calculate_measurements(self):
        """计算测量结果"""
        if not self.point_picker:
            return

        points = self.point_picker.get_all_selected_points()

        if len(points) >= 2:
            # 计算最后两个点之间的距离
            p1 = np.array(points[-2])
            p2 = np.array(points[-1])
            distance = np.linalg.norm(p2 - p1)

            # 更新距离显示
            self.ui.editDistance.setText(f"{distance:.3f}")

            # 更新测量次数
            measure_count = len(points) - 1
            self.ui.labelMeasureCount.setText(f"测量次数：{measure_count}")

            # 如果是家畜点云，可以计算体长（这里简单使用距离作为体长）
            self.ui.editBodyLength.setText(f"{distance:.3f}")

    def clear_measurements(self):
        """清除所有测量"""
        if self.point_picker:
            self.point_picker.clear_selection()

        # 清空UI显示
        self.ui.textPoints.clear()
        self.ui.editDistance.clear()
        self.ui.editBodyLength.clear()

        # 更新统计信息
        point_count = len(self.pcd.points) if self.pcd else 0
        self.ui.labelPointCount.setText(f"点云数量：{point_count}")
        self.ui.labelMeasureCount.setText(f"测量次数：0")

        # 如果处于测量模式，退出
        if self.is_measure_mode:
            self.toggle_measure_mode()

        print("已清除所有测量")