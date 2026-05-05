import numpy as np
import open3d as o3d
import win32gui, win32api, win32con
import time


class PointPicker:
    def __init__(self, vis, pcd):
        self.vis = vis
        self.pcd = pcd
        self.points = np.asarray(pcd.points)

        self.picked_indices = []
        self.picked_spheres = []
        self.measurement_lines = []

        # 撤销/重做栈
        self.undo_stack = []  # 存储被撤销的 (indices, spheres, lines)

        self.picking_mode = False
        self.continuous_mode = False

        self.o3d_hwnd = None
        self._last_click_time = 0  # 初始化在__init__中
        self._last_cursor_pos = (0, 0)

        # 构建KD树
        self._build_kdtree()

        # 回调
        self.on_distance = None
        self.on_points_updated = None
        self.on_mode_changed = None

    def _build_kdtree(self):
        try:
            self.kdtree = o3d.geometry.KDTreeFlann(self.pcd)
        except Exception as e:
            print(f"[Picker] KD树构建失败: {e}")
            self.kdtree = None

    def bind_window(self, hwnd):
        self.o3d_hwnd = hwnd

    def set_callbacks(self, on_distance=None, on_points_updated=None, on_mode_changed=None):
        self.on_distance = on_distance
        self.on_points_updated = on_points_updated
        self.on_mode_changed = on_mode_changed

    # ================= 模式 =================
    def start_pick(self):
        self.clear()
        self.picking_mode = True
        self.continuous_mode = False
        print("[Picker] 单次测量模式：Ctrl+Shift+点击选择点")
        if self.on_mode_changed:
            self.on_mode_changed()

    def start_continuous(self):
        self.clear()
        self.continuous_mode = True
        self.picking_mode = False
        print("[Picker] 连续测量模式：Ctrl+Shift+点击选择点")
        if self.on_mode_changed:
            self.on_mode_changed()

    def stop(self):
        self.picking_mode = False
        self.continuous_mode = False
        print("[Picker] 退出选点模式")
        if self.on_mode_changed:
            self.on_mode_changed()

    # ================= 主循环 =================
    def update(self):
        if not (self.picking_mode or self.continuous_mode):
            return
        self._check_click()

    # ================= 点击检测 =================
    def _check_click(self):
        if self.o3d_hwnd is None:
            return

        # 检查窗口是否还存在
        if not win32gui.IsWindow(self.o3d_hwnd):
            return

        # 使用Ctrl+Shift+点击
        ctrl = win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000
        shift = win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000
        left = win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000

        if not (ctrl and shift and left):
            return

        cursor = win32gui.GetCursorPos()
        hwnd = win32gui.WindowFromPoint(cursor)

        # 检查是否在Open3D窗口上
        if hwnd != self.o3d_hwnd:
            return

        # 防抖
        now = time.time()
        if now - self._last_click_time < 0.5:
            return

        # 防止鼠标不动时的重复触发
        if cursor == self._last_cursor_pos and now - self._last_click_time < 1.0:
            return

        self._last_click_time = now
        self._last_cursor_pos = cursor

        rect = win32gui.GetWindowRect(self.o3d_hwnd)
        x = cursor[0] - rect[0]
        y = cursor[1] - rect[1]

        # 确保坐标在窗口内
        if x < 0 or y < 0:
            return

        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        if x >= width or y >= height:
            return

        self._process_click(x, y)

    # ================= 拾取算法 =================
    def _process_click(self, screen_x, screen_y):
        print(f"[Picker] 点击位置: ({screen_x:.0f}, {screen_y:.0f})")

        idx = self._precise_pick(screen_x, screen_y)

        if idx is None:
            idx = self._fallback_pick(screen_x, screen_y)

        if idx is None:
            print("[Picker] 未检测到点")
            return

        if idx in self.picked_indices:
            print(f"[Picker] 点 {idx} 已被选择")
            return

        # 添加点前清空重做栈（新操作后不能重做）
        self.undo_stack.clear()

        self._add_point(idx)

        if len(self.picked_indices) >= 2:
            self._measure_last()

        if self.picking_mode and len(self.picked_indices) == 2:
            self.stop()

    def _precise_pick(self, screen_x, screen_y):
        if self.kdtree is None:
            return None

        try:
            vc = self.vis.get_view_control()
            cam = vc.convert_to_pinhole_camera_parameters()

            intrinsic = cam.intrinsic.intrinsic_matrix
            extrinsic = cam.extrinsic

            # 获取窗口大小
            rect = win32gui.GetWindowRect(self.o3d_hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            # 相机参数
            fx, fy = intrinsic[0, 0], intrinsic[1, 1]
            cx, cy = intrinsic[0, 2], intrinsic[1, 2]

            # 计算射线方向（相机坐标系）
            ray_dir_cam = np.array([
                (screen_x - cx) / fx,
                (screen_y - cy) / fy,
                1.0
            ])
            ray_dir_cam = ray_dir_cam / np.linalg.norm(ray_dir_cam)

            # 转换到世界坐标系
            rot = extrinsic[:3, :3]
            trans = extrinsic[:3, 3]

            # 相机原点在世界坐标
            camera_origin = -rot.T @ trans

            # 射线方向在世界坐标
            ray_dir_world = rot.T @ ray_dir_cam
            ray_dir_world = ray_dir_world / np.linalg.norm(ray_dir_world)

            # 沿射线采样
            best_idx = None
            best_score = float('inf')

            # 自适应采样范围
            bbox = self.pcd.get_axis_aligned_bounding_box()
            diag = np.linalg.norm(bbox.get_max_bound() - bbox.get_min_bound())

            t_min = 0.05 * diag
            t_max = 2.0 * diag
            num_samples = 300

            for t in np.linspace(t_min, t_max, num_samples):
                point = camera_origin + t * ray_dir_world

                # KD树搜索
                [k, idx, dist] = self.kdtree.search_knn_vector_3d(point, 1)

                if dist[0] < best_score:
                    # 计算垂直距离
                    point_on_pcd = self.points[idx[0]]
                    vec_to_point = point_on_pcd - camera_origin
                    proj_length = np.dot(vec_to_point, ray_dir_world)

                    if proj_length > 0:
                        perpendicular_dist = np.linalg.norm(
                            vec_to_point - proj_length * ray_dir_world
                        )

                        # 综合评分（权重可调整）
                        score = perpendicular_dist * 0.8 + dist[0] * 0.2

                        if score < best_score:
                            best_score = score
                            best_idx = idx[0]

            if best_idx is not None and best_score < 0.1:  # 10cm阈值
                print(f"[Picker] 精确拾取成功，评分: {best_score:.4f}")
                return best_idx

            return None

        except Exception as e:
            print(f"[Picker] 精确拾取错误: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _fallback_pick(self, screen_x, screen_y):
        """后备方法 - 基于投影"""
        try:
            vc = self.vis.get_view_control()
            cam = vc.convert_to_pinhole_camera_parameters()

            intrinsic = cam.intrinsic.intrinsic_matrix
            extrinsic = cam.extrinsic

            # 转换所有点到相机坐标
            points_h = np.hstack([self.points, np.ones((len(self.points), 1))])
            points_cam = (np.linalg.inv(extrinsic) @ points_h.T).T[:, :3]

            # 只考虑前方的点
            mask = points_cam[:, 2] > 0.01
            if not np.any(mask):
                return None

            valid_indices = np.where(mask)[0]
            valid_points = points_cam[mask]

            fx, fy = intrinsic[0, 0], intrinsic[1, 1]
            cx, cy = intrinsic[0, 2], intrinsic[1, 2]

            # 投影到屏幕
            u = fx * valid_points[:, 0] / valid_points[:, 2] + cx
            v = fy * valid_points[:, 1] / valid_points[:, 2] + cy

            # 计算屏幕距离
            screen_dist = np.sqrt((u - screen_x) ** 2 + (v - screen_y) ** 2)

            # 深度加权
            depths = valid_points[:, 2]
            depth_weight = 1.0 / (1.0 + depths * 0.3)

            # 综合评分
            scores = screen_dist * depth_weight

            best_idx = np.argmin(scores)

            if screen_dist[best_idx] < 150:  # 150像素阈值
                print(f"[Picker] 后备拾取成功，距离: {screen_dist[best_idx]:.1f}px")
                return valid_indices[best_idx]

            return None

        except Exception as e:
            print(f"[Picker] 后备拾取错误: {e}")
            return None

    # ================= 添加点 =================
    def _add_point(self, idx):
        self.picked_indices.append(idx)
        coord = self.points[idx]

        print(f"[Picker] ✓ 选中点 {len(self.picked_indices)}: "
              f"({coord[0]:.3f}, {coord[1]:.3f}, {coord[2]:.3f})")

        # 创建球体标记
        sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.02)
        sphere.paint_uniform_color([1, 0, 0])
        sphere.translate(coord)

        self.vis.add_geometry(sphere, False)
        self.picked_spheres.append(sphere)
        self.vis.update_renderer()

        if self.on_points_updated:
            self.on_points_updated(self.get_points())

    # ================= 测距 =================
    def _measure_last(self):
        i1, i2 = self.picked_indices[-2], self.picked_indices[-1]
        p1, p2 = self.points[i1], self.points[i2]

        d = np.linalg.norm(p2 - p1)

        print(f"[Picker] 📏 距离: {d:.3f} m")

        # 创建测量线
        line = o3d.geometry.LineSet()
        line.points = o3d.utility.Vector3dVector([p1, p2])
        line.lines = o3d.utility.Vector2iVector([[0, 1]])
        line.colors = o3d.utility.Vector3dVector([[0, 1, 0]])

        self.vis.add_geometry(line, False)
        self.measurement_lines.append(line)
        self.vis.update_renderer()

        if self.on_distance:
            self.on_distance(d)

    # ================= 工具方法 =================
    def get_points(self):
        return [self.points[i] for i in self.picked_indices]

    def get_last_distance(self):
        if len(self.picked_indices) >= 2:
            p1 = self.points[self.picked_indices[-2]]
            p2 = self.points[self.picked_indices[-1]]
            return np.linalg.norm(p2 - p1)
        return 0.0

    def undo(self):
        if not self.picked_indices:
            print("[Picker] 没有可撤销的操作")
            return

        # 保存当前状态到重做栈
        saved_state = {
            'indices': self.picked_indices.copy(),
            'spheres': self.picked_spheres.copy(),
            'lines': self.measurement_lines.copy()
        }
        self.undo_stack.append(saved_state)
        # 执行撤销
        removed_idx = self.picked_indices.pop()

        # 如果有测量线，也撤销测量线
        if self.measurement_lines:
            # 如果最后一个操作产生了测量线（即当前有偶数个点，且至少2个点）
            removed_line = self.measurement_lines.pop()
            self.vis.remove_geometry(removed_line, False)

        # 移除球体
        if self.picked_spheres:
            removed_sphere = self.picked_spheres.pop()
            self.vis.remove_geometry(removed_sphere, False)

        self.vis.update_renderer()

        print(f"[Picker] ↩ 撤销点 {len(self.picked_indices) + 1} (可重做 {len(self.undo_stack)} 步)")

        # 更新回调
        if self.on_points_updated:
            self.on_points_updated(self.get_points())

    def redo(self):
        """重做：恢复最后一次撤销"""
        if not self.undo_stack:
            print("[Picker] 没有可重做的操作")
            return

        # 恢复之前的状态
        saved_state = self.undo_stack.pop()

        # 清除当前状态
        for sphere in self.picked_spheres:
            self.vis.remove_geometry(sphere, False)
        for line in self.measurement_lines:
            self.vis.remove_geometry(line, False)

        # 恢复保存的状态
        self.picked_indices = saved_state['indices']
        self.picked_spheres = saved_state['spheres']
        self.measurement_lines = saved_state['lines']

        # 重新添加几何体
        for sphere in self.picked_spheres:
            self.vis.add_geometry(sphere, False)
        for line in self.measurement_lines:
            self.vis.add_geometry(line, False)

        self.vis.update_renderer()

        print(f"[Picker] ↪ 重做 (剩余可重做 {len(self.undo_stack)} 步)")

        # 更新回调
        if self.on_points_updated:
            self.on_points_updated(self.get_points())

        # 如果有测量结果，更新距离
        if len(self.picked_indices) >= 2 and self.on_distance:
            distance = self.get_last_distance()
            self.on_distance(distance)

    def clear(self):
        # 清除所有选点和可视化
        for sphere in self.picked_spheres:
            self.vis.remove_geometry(sphere, False)
        for line in self.measurement_lines:
            self.vis.remove_geometry(line, False)

        self.picked_indices.clear()
        self.picked_spheres.clear()
        self.measurement_lines.clear()
        self.undo_stack.clear()

        # 重置点击时间（不要删除属性）
        self._last_click_time = 0
        self._last_cursor_pos = (0, 0)

        self.vis.update_renderer()
        print("[Picker] 🗑 清除所有选点")