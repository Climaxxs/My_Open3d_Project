import open3d as o3d
import numpy as np
import copy

# 1. 读取点云
print("1. 读取点云...")
pcd = o3d.io.read_point_cloud("C:\\Users\\cyy24\\Desktop\\毕业设计\\BM-GCN-main\\example_images\\1.ply")

# 2. 复制一份用于处理
print("\n2. 复制点云...")
pcd_processed = copy.deepcopy(pcd)

# 3. 平移点云
print("3. 平移点云...")
pcd_processed.translate((1, 0, 0))

# 4. 旋转点云
print("4. 旋转点云...")
R = pcd_processed.get_rotation_matrix_from_xyz((0, np.pi/6, 0))
pcd_processed.rotate(R)

# 5. 缩放点云
print("5. 缩放点云...")
pcd_processed.scale(0.9, center=pcd_processed.get_center())

# 6. 添加颜色
print("6. 添加颜色...")
pcd_processed.paint_uniform_color([0, 1, 0])  # 绿色

# 7. 保存处理后的点云
print("7. 保存点云...")
o3d.io.write_point_cloud("output/cow_processed.ply", pcd_processed)

# 8. 可视化对比
print("\n8. 可视化对比...")
pcd.paint_uniform_color([1, 0, 0])  # 原始为红色
o3d.visualization.draw_geometries([pcd, pcd_processed])

print("完成！")