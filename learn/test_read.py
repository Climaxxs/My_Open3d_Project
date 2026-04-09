import open3d as o3d

pcd = o3d.io.read_point_cloud("C:\\Users\\cyy24\\Desktop\\毕业设计\\BM-GCN-main\\example_images\\1.ply")
print(pcd.points)
o3d.visualization.draw_geometries([pcd], window_name="点云预览")