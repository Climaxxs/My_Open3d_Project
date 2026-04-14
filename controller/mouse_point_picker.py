"""
鼠标点选处理器 - 处理Open3D点云中的鼠标点选功能
"""

import numpy as np
import open3d as o3d
from PyQt6.QtCore import Qt, QPoint
import win32gui
import win32con

# 导入窗口钩子
from controller.window_hook import WindowHook, get_open3d_window_handle


class MousePointPicker:
    """处理鼠标点选的核心类"""

    def __init__(self, visualizer, point_cloud, open3d_widget):
        """
        初始化鼠标点选器

        Args:
            visualizer: Open3D Visualizer实例
            point_cloud: Open3D PointCloud实例
            open3d_widget: Qt Widget，Open3D窗口嵌入其中
        """
        self.vis = visualizer
        self.pcd = point_cloud
        self.widget = open3d_widget

        # 状态管理
        self.is_picking_mode = False
        self.selected_points = []  # 选中的3D点坐标列表
        self.selected_indices = []  # 选中的点索引列表
        self.markers = []  # 视觉标记（球体）列表

        # 点云数据
        self.points_array = np.asarray(point_cloud.points) if point_cloud else None

        # KD树用于加速查询（延迟初始化）
        self.kdtree = None

        # 窗口钩子
        self.window_hook = None
        self.open3d_hwnd = None

        # 鼠标点击回调队列（用于在主线程中处理）
        self.click_queue = []

    def enable_picking_mode(self):
        """启用点选模式"""
        self.is_picking_mode = True
        self.widget.setCursor(Qt.CursorShape.CrossCursor)
        print("点选模式已启用")

        # 安装窗口钩子以捕获Open3D窗口内的鼠标点击
        self._install_window_hook()

    def disable_picking_mode(self):
        """禁用点选模式"""
        self.is_picking_mode = False
        self.widget.setCursor(Qt.CursorShape.ArrowCursor)
        print("点选模式已禁用")

        # 卸载窗口钩子
        self._uninstall_window_hook()

    def handle_mouse_click(self, screen_x, screen_y):

        """
        处理鼠标点击事件

        Args:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标

        Returns:
            point_3d: 选中的3D点坐标，如果未选中则返回None
        """
        if not self.is_picking_mode:
            print("错误：点选模式未启用")
            return None

        # === 测试代码开始 ===
        print(f"鼠标点击被捕获！坐标: ({screen_x}, {screen_y})")

        # 临时测试：返回点云中的第一个点
        if self.points_array is not None and len(self.points_array) > 0:
            test_point = self.points_array[0]
            print(f"测试返回点: {test_point}")
            return test_point
        # === 测试代码结束 ===

        if self.points_array is None or len(self.points_array) == 0:
            print("错误：点云数据为空")
            return None

        # 坐标转换和射线投射
        point_3d, index = self._ray_cast_to_point_cloud(screen_x, screen_y)

        if point_3d is not None:
            self.selected_points.append(point_3d)
            self.selected_indices.append(index)
            self._add_visual_marker(point_3d)
            print(f"选中点: {point_3d}, 索引: {index}")
            return point_3d
        else:
            print("未选中任何点")
            return None

    def _screen_to_window(self, screen_x, screen_y):
        """
        屏幕坐标转换为Open3D窗口坐标

        Args:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标

        Returns:
            window_x, window_y: Open3D窗口内的坐标
        """
        # 获取widget在屏幕上的位置
        widget_pos = self.widget.mapToGlobal(QPoint(0, 0))

        # 计算相对坐标
        relative_x = screen_x - widget_pos.x()
        relative_y = screen_y - widget_pos.y()

        # 确保坐标在widget范围内
        relative_x = max(0, min(relative_x, self.widget.width()))
        relative_y = max(0, min(relative_y, self.widget.height()))

        return relative_x, relative_y

    def _ray_cast_to_point_cloud(self, screen_x, screen_y):
        """
        射线投射：将2D屏幕坐标转换为3D点云坐标

        Args:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标

        Returns:
            (point_3d, index): 3D点坐标和索引，如果未找到则返回(None, -1)
        """
        # 转换到窗口坐标
        window_x, window_y = self._screen_to_window(screen_x, screen_y)

        try:
            # 获取Open3D视图控制
            view_control = self.vis.get_view_control()

            # 尝试获取投影和视图矩阵
            # 注意：Open3D API可能在不同版本中有所变化
            projection_matrix = view_control.get_projection_matrix()
            view_matrix = view_control.get_view_matrix()

            # 创建射线
            ray_origin, ray_direction = self._create_ray(
                window_x, window_y, projection_matrix, view_matrix
            )

            # 查找最近点
            return self._find_closest_point_on_ray(ray_origin, ray_direction)

        except AttributeError as e:
            print(f"Open3D API错误: {e}")
            print("尝试使用备选点选方案...")
            return self._alternative_point_selection(window_x, window_y)
        except Exception as e:
            print(f"射线投射错误: {e}")
            return None, -1

    def _create_ray(self, window_x, window_y, projection_matrix, view_matrix):
        """
        创建从相机出发的射线

        Args:
            window_x: 窗口X坐标
            window_y: 窗口Y坐标
            projection_matrix: 投影矩阵（4x4）
            view_matrix: 视图矩阵（4x4）

        Returns:
            ray_origin, ray_direction: 射线起点和方向
        """
        # 获取窗口尺寸
        width = self.widget.width()
        height = self.widget.height()

        if width == 0 or height == 0:
            print("错误：窗口尺寸为0")
            return np.array([0, 0, 0]), np.array([0, 0, 1])

        # 将窗口坐标转换为归一化设备坐标（NDC）
        # Open3D可能使用y轴向下，NDC范围[-1, 1]
        ndc_x = (2.0 * window_x / width) - 1.0
        ndc_y = 1.0 - (2.0 * window_y / height)  # y轴翻转

        # 创建近平面和远平面点（在NDC空间中）
        # 近平面z = -1，远平面z = 1（OpenGL风格）
        near_ndc = np.array([ndc_x, ndc_y, -1.0, 1.0])
        far_ndc = np.array([ndc_x, ndc_y, 1.0, 1.0])

        # 计算逆矩阵
        try:
            inv_projection = np.linalg.inv(projection_matrix)
            inv_view = np.linalg.inv(view_matrix)
        except np.linalg.LinAlgError as e:
            print(f"矩阵求逆失败: {e}")
            return np.array([0, 0, 0]), np.array([0, 0, 1])

        # 将NDC坐标转换到视图空间
        near_view = inv_projection @ near_ndc
        far_view = inv_projection @ far_ndc

        # 透视除法
        near_view = near_view / near_view[3]
        far_view = far_view / far_view[3]

        # 将视图空间坐标转换到世界空间
        near_world = inv_view @ near_view
        far_world = inv_view @ far_view

        near_world = near_world / near_world[3]
        far_world = far_world / far_world[3]

        # 提取3D坐标
        ray_origin = near_world[:3]
        ray_end = far_world[:3]

        # 计算射线方向
        ray_direction = ray_end - ray_origin
        ray_direction = ray_direction / np.linalg.norm(ray_direction)

        print(f"射线: 起点={ray_origin}, 方向={ray_direction}")
        return ray_origin, ray_direction

    def _find_closest_point_on_ray(self, ray_origin, ray_direction):
        """
        查找射线上最近的点云点

        Args:
            ray_origin: 射线起点
            ray_direction: 射线方向

        Returns:
            (point_3d, index): 最近的点坐标和索引
        """
        if self.points_array is None or len(self.points_array) == 0:
            return None, -1

        # 归一化射线方向
        ray_dir_normalized = ray_direction / np.linalg.norm(ray_direction)

        # 对于大型点云，使用KD树加速
        if len(self.points_array) > 10000 and self.kdtree is None:
            self.kdtree = o3d.geometry.KDTreeFlann(self.pcd)

        min_distance = float('inf')
        closest_point = None
        closest_index = -1

        # 简单线性搜索（适用于中小型点云）
        for i, point in enumerate(self.points_array):
            # 计算点到射线的距离
            # 使用向量投影方法
            point_vec = point - ray_origin
            projection_length = np.dot(point_vec, ray_dir_normalized)

            # 只考虑射线方向上的点（投影长度为正）
            if projection_length < 0:
                continue

            # 计算投影点
            projected_point = ray_origin + projection_length * ray_dir_normalized

            # 计算点到射线的垂直距离
            distance = np.linalg.norm(point - projected_point)

            # 更新最近点
            if distance < min_distance:
                min_distance = distance
                closest_point = point
                closest_index = i

        # 设置距离阈值（根据点云尺度调整）
        # 如果点云有尺度信息，可以动态调整阈值
        threshold = 0.1  # 默认阈值

        if min_distance < threshold:
            print(f"找到最近点: 索引={closest_index}, 距离={min_distance:.4f}")
            return closest_point, closest_index
        else:
            print(f"未找到足够近的点，最小距离={min_distance:.4f}")
            return None, -1

    def _alternative_point_selection(self, window_x, window_y):
        """
        备选点选方案（当Open3D API不可用时）

        Args:
            window_x: 窗口X坐标
            window_y: 窗口Y坐标

        Returns:
            (point_3d, index): 选中的点坐标和索引
        """
        print(f"使用备选方案选择点: window({window_x}, {window_y})")

        if self.points_array is None or len(self.points_array) == 0:
            return None, -1

        # 尝试使用投影方法选择最近的点
        try:
            return self._select_point_by_projection(window_x, window_y)
        except Exception as e:
            print(f"投影选择失败: {e}")
            # 回退到简单方法：返回点云中的第一个点
            if len(self.points_array) > 0:
                return self.points_array[0], 0
            return None, -1

    def _select_point_by_projection(self, window_x, window_y):
        """
        通过投影方法选择最近的点

        Args:
            window_x: 窗口X坐标
            window_y: 窗口Y坐标

        Returns:
            (point_3d, index): 选中的点坐标和索引
        """
        # 获取窗口尺寸
        width = self.widget.width()
        height = self.widget.height()

        # 获取Open3D视图控制
        view_control = self.vis.get_view_control()

        # 尝试获取相机参数并投影点
        try:
            # 获取相机参数
            camera_params = view_control.get_camera_parameters()

            # 获取相机内在矩阵和外部矩阵
            intrinsic = camera_params.intrinsic
            extrinsic = camera_params.extrinsic

            # 将点云点投影到屏幕
            projected_points = []
            for i, point in enumerate(self.points_array):
                # 将3D点转换为齐次坐标
                point_homo = np.array([point[0], point[1], point[2], 1.0])

                # 应用外部矩阵（世界到相机）
                point_cam = extrinsic @ point_homo

                # 应用内在矩阵（相机到图像）
                point_img = intrinsic.intrinsic_matrix @ point_cam[:3]

                # 归一化
                if point_img[2] > 0:  # 深度为正（在相机前方）
                    x = point_img[0] / point_img[2]
                    y = point_img[1] / point_img[2]

                    # 转换为像素坐标（假设原点在左上角）
                    pixel_x = x
                    pixel_y = y

                    projected_points.append((pixel_x, pixel_y, i))

            if not projected_points:
                return None, -1

            # 找到距离点击位置最近的点
            min_distance = float('inf')
            closest_index = -1
            closest_point = None

            for px, py, idx in projected_points:
                # 计算欧氏距离
                distance = np.sqrt((px - window_x)**2 + (py - window_y)**2)

                if distance < min_distance:
                    min_distance = distance
                    closest_index = idx
                    closest_point = self.points_array[idx]

            # 设置距离阈值（像素）
            if min_distance < 20:  # 20像素阈值
                return closest_point, closest_index
            else:
                return None, -1

        except AttributeError as e:
            print(f"相机参数API不可用: {e}")
            raise e
        except Exception as e:
            print(f"投影计算错误: {e}")
            raise e

    def _add_visual_marker(self, point_3d):
        """
        在选中点添加红色球体标记

        Args:
            point_3d: 3D点坐标
        """
        try:
            # 创建球体标记
            sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.02)
            sphere.translate(point_3d)
            sphere.paint_uniform_color([1, 0, 0])  # 红色

            # 添加到可视化器
            self.vis.add_geometry(sphere)
            self.markers.append(sphere)

            # 更新渲染
            self.vis.update_geometry(sphere)
            self.vis.poll_events()
            self.vis.update_renderer()

            print(f"添加视觉标记在: {point_3d}")

        except Exception as e:
            print(f"添加视觉标记失败: {e}")

    def clear_selection(self):
        """清除所有选中的点和标记"""
        try:
            # 移除所有标记
            for marker in self.markers:
                try:
                    self.vis.remove_geometry(marker)
                except:
                    pass  # 忽略移除错误

            self.markers.clear()
            self.selected_points.clear()
            self.selected_indices.clear()

            print("已清除所有选中的点")

        except Exception as e:
            print(f"清除选择失败: {e}")

    def get_selected_points_count(self):
        """获取选中的点数"""
        return len(self.selected_points)

    def get_last_selected_point(self):
        """获取最后选中的点"""
        if self.selected_points:
            return self.selected_points[-1]
        return None

    def get_all_selected_points(self):
        """获取所有选中的点"""
        return self.selected_points.copy()

    # ==================== 窗口钩子相关方法 ====================

    def _install_window_hook(self):
        """安装窗口钩子以捕获Open3D窗口内的鼠标点击"""
        try:
            # 获取Open3D窗口句柄
            self.open3d_hwnd = get_open3d_window_handle()
            if not self.open3d_hwnd:
                print("警告：无法找到Open3D窗口句柄，鼠标点击可能无法在Open3D窗口内捕获")
                return False

            # 创建窗口钩子实例
            self.window_hook = WindowHook(self.open3d_hwnd, self._window_hook_callback)

            # 安装钩子
            if self.window_hook.install_hook():
                print("窗口钩子安装成功，现在可以捕获Open3D窗口内的鼠标点击")
                return True
            else:
                print("窗口钩子安装失败")
                return False

        except Exception as e:
            print(f"安装窗口钩子时出错: {e}")
            return False

    def _uninstall_window_hook(self):
        """卸载窗口钩子"""
        if self.window_hook:
            try:
                self.window_hook.uninstall_hook()
                self.window_hook = None
                print("窗口钩子已卸载")
            except Exception as e:
                print(f"卸载窗口钩子时出错: {e}")

    def _window_hook_callback(self, window_x, window_y):
        """
        窗口钩子回调函数，处理Open3D窗口内的鼠标点击

        Args:
            window_x: Open3D窗口内的X坐标（相对于窗口左上角）
            window_y: Open3D窗口内的Y坐标（相对于窗口左上角）
        """
        if not self.is_picking_mode:
            return

        print(f"窗口钩子捕获到鼠标点击: 窗口坐标({window_x}, {window_y})")

        # 将窗口坐标转换为屏幕坐标
        screen_x, screen_y = self._window_to_screen(window_x, window_y)
        print(f"转换为屏幕坐标: ({screen_x}, {screen_y})")

        # 处理鼠标点击（直接调用handle_mouse_click）
        # 注意：这个回调在Windows消息循环中调用，可能需要考虑线程安全
        self._process_hooked_click(screen_x, screen_y)

    def _window_to_screen(self, window_x, window_y):
        """将Open3D窗口坐标转换为屏幕坐标"""
        try:
            if not self.open3d_hwnd:
                return window_x, window_y

            # 获取窗口在屏幕上的位置
            rect = win32gui.GetWindowRect(self.open3d_hwnd)
            screen_x = rect[0] + window_x
            screen_y = rect[1] + window_y

            return screen_x, screen_y

        except Exception as e:
            print(f"坐标转换失败: {e}")
            return window_x, window_y

    def _process_hooked_click(self, screen_x, screen_y):
        """
        处理窗口钩子捕获的鼠标点击
        这个方法可以直接调用，因为它在Windows消息循环中
        """
        try:
            # 调用现有的handle_mouse_click方法
            # 注意：这里直接调用，可能需要考虑重入问题
            selected_point = self.handle_mouse_click(screen_x, screen_y)

            # 如果需要通知主线程，可以在这里添加信号或回调
            # 但目前直接处理应该没问题，因为Open3D的渲染也在主线程
            return selected_point

        except Exception as e:
            print(f"处理钩子点击时出错: {e}")
            return None

    def process_pending_clicks(self):
        """处理挂起的点击事件（如果使用队列的话）"""
        # 目前不使用队列，直接处理
        pass