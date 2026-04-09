import open3d as o3d
import numpy as np

# 加载一个示例点云
Knot = o3d.data.KnotMesh()
mesh = o3d.io.read_triangle_mesh(Knot.path)
pcd = mesh.sample_points_uniformly(number_of_points=2000)

# 1. 下采样 (减少点数，加快后续处理)
downpcd = pcd.voxel_down_sample(voxel_size=0.05)
print(f"下采样: {len(pcd.points)} -> {len(downpcd.points)} 点")

# 2. 计算并着色法线 (用于估计表面朝向)
downpcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
# 使用法线信息进行着色
downpcd.paint_uniform_color([0.6, 0.6, 0.6]) # 灰色

# 3. 裁剪点云 (只保留一个范围内的点)
bbox = o3d.geometry.AxisAlignedBoundingBox(min_bound=(-1, -1, -1),
                                            max_bound=(1, 1, 1))
cropped_pcd = downpcd.crop(bbox)
print(f"裁剪后: {len(cropped_pcd.points)} 点")

# 可视化对比
pcd.paint_uniform_color([1, 0, 0]) # 原始点云：红色
o3d.visualization.draw_geometries([pcd, downpcd, cropped_pcd],
                                   window_name="处理流程: 原始(红) / 下采样(灰) / 裁剪",
                                   point_show_normal=False) # 此处关闭法线显示以免杂乱