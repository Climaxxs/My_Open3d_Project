import open3d as o3d

def load_point_cloud_file(file_path):
    return o3d.io.read_point_cloud(file_path)