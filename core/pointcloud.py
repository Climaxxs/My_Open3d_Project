import open3d as o3d


def build_pcd(points):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    return pcd


def safe_preprocess(pcd):
    n = len(pcd.points)
    print(f"原始点数: {n}")

    # ================= 1️⃣ 自适应下采样 =================
    if n > 80000:
        voxel = 0.02
    elif n > 40000:
        voxel = 0.015
    elif n > 20000:
        voxel = 0.012
    else:
        voxel = 0.01

    print(f"体素大小: {voxel}")
    pcd = pcd.voxel_down_sample(voxel)

    print(f"下采样后: {len(pcd.points)}")

    # ================= 2️⃣ 半径滤波（核心） =================
    try:
        print("半径滤波...")

        pcd, ind = pcd.remove_radius_outlier(
            nb_points=8,
            radius=voxel * 3
        )
        pcd = pcd.select_by_index(ind)

        print(f"半径滤波后: {len(pcd.points)}")

    except Exception as e:
        print("半径滤波失败:", e)

    # ================= 3️⃣ 法线（可选） =================
    try:
        print("法线估计...")

        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=voxel * 5,
                max_nn=20
            )
        )

    except Exception as e:
        print("法线失败:", e)

    return pcd