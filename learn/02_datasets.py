import open3d as o3d

# 加载内置示例点云（斯坦福兔子）
bunny = o3d.data.BunnyMesh()
mesh = o3d.io.read_triangle_mesh(bunny.path)
print("网格信息:", mesh)
print("顶点数:", len(mesh.vertices))
print("三角形数:", len(mesh.triangles))
o3d.visualization.draw_geometries([mesh])

# 将网格转换为点云（采样）
pcd = mesh.sample_points_uniformly(number_of_points=1000)
print("采样后点云点数:", len(pcd.points))
o3d.visualization.draw_geometries([pcd])

# 并排可视化网格和点云
mesh.compute_vertex_normals() # 计算法线以便着色
o3d.visualization.draw_geometries([mesh, pcd],
                                   window_name="网格 vs 点云",
                                   mesh_show_wireframe=True, # 网格显示线框
                                   width=800, height=600)