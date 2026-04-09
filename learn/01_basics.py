import open3d as o3d
import numpy as np
#print("Open3D版本:", o3d.__version__)

# 1. 创建点云 (最简单的例子：创建5个点)
points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 1]], dtype=np.float64)
pcd = o3d.geometry.PointCloud()
pcd.points = o3d.utility.Vector3dVector(points) # 关键：将NumPy数组转换为Open3D格式
#print("点云中共有", len(pcd.points), "个点")

# 获取点的坐标（转为NumPy数组）
points = np.asarray(pcd.points)
print(f"点坐标:\n{points}")

# 获取第一个点的坐标
first_point = pcd.points[0]
print(f"第一个点: {first_point}")

# 获取点的数量
num_points = len(pcd.points)
print(f"点数: {num_points}")

# 为点云添加颜色（RGB值在0-1之间）
colors = np.array([
    [1, 0, 0],  # 红色
    [0, 1, 0],  # 绿色
    [0, 0, 1],  # 蓝色
    [1, 1, 0]   # 黄色
])
pcd.colors = o3d.utility.Vector3dVector(colors)


# 统一设置所有点为红色
#pcd.paint_uniform_color([1, 0, 0])
#o3d.visualization.draw_geometries([pcd], window_name="我的第一个点云")

# 获取点云的范围
points = np.asarray(pcd.points)
min_bound = points.min(axis=0)
max_bound = points.max(axis=0)
print(f"X范围: [{min_bound[0]:.3f}, {max_bound[0]:.3f}]")
print(f"Y范围: [{min_bound[1]:.3f}, {max_bound[1]:.3f}]")
print(f"Z范围: [{min_bound[2]:.3f}, {max_bound[2]:.3f}]")

# 计算中心点
center = points.mean(axis=0)
print(f"中心点: {center}")