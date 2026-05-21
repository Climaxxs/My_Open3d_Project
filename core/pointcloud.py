"""点云处理核心算法 - OBB尺寸测量、胸围拟合、泊松重建"""

import open3d as o3d
import numpy as np
from scipy.spatial._qhull import ConvexHull
import alphashape


def build_pcd(points):
    """将 numpy 数组转换为 Open3D 点云对象"""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    return pcd


def safe_preprocess(pcd):
    """自适应预处理管线：体素下采样 -> 半径滤波去噪 -> 法线估计"""
    n = len(pcd.points)
    print(f"原始点数: {n}")

    # 根据点数自适应选择体素大小
    if n > 80000:
        voxel = 0.02
    elif n > 40000:
        voxel = 0.015
    elif n > 20000:
        voxel = 0.012
    else:
        voxel = 0.01

    # 半径滤波去除离群点
    try:
        print("半径滤波...")
        pcd, _ = pcd.remove_radius_outlier(
            nb_points=8,
            radius=voxel * 3
        )
        print(f"半径滤波后: {len(pcd.points)}")
    except Exception as e:
        print("半径滤波失败:", e)

    print(f"体素大小: {voxel}")
    pcd = pcd.voxel_down_sample(voxel)
    print(f"下采样后: {len(pcd.points)}")

    # 法线估计（后续泊松重建等需要）
    try:
        print("法线估计...")
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=voxel * 5,
                max_nn=20
            )
        )
        print("成功")
    except Exception as e:
        print("法线失败:", e)

    return pcd


def measure_dimensions_obb(pcd):
    """计算点云的有向包围盒，返回排序后的 (体长, 体高, 体宽) 及几何信息"""
    obb = pcd.get_oriented_bounding_box()

    extents = obb.extent

    # 按大小降序排列：体长 > 体宽 > 体高
    order = np.argsort(extents)[::-1]
    length, height, width = extents[order]

    axes = obb.R[:, order]
    center = obb.center

    # 生成三条测量线的端点
    endpoints = []
    for i in range(3):
        axis = axes[:, i]
        half = extents[order[i]] / 2
        p1 = center - axis * half
        p2 = center + axis * half
        endpoints.append((p1, p2))

    return length, width, height, center, axes, endpoints, obb


def fit_ellipse_least_squares(yz_points):
    """最小二乘椭圆拟合 (Fitzgibbon 方法)，返回半轴 (a, b)"""
    if len(yz_points) < 6:
        return 0, 0

    x = yz_points[:, 0]
    y = yz_points[:, 1]

    D = np.column_stack([x ** 2, x * y, y ** 2, x, y, np.ones_like(x)])
    S = D.T @ D

    # 约束矩阵：保证拟合结果是椭圆而非双曲线
    C = np.zeros((6, 6))
    C[0, 2] = 2
    C[2, 0] = 2
    C[1, 1] = -1

    try:
        E, V = np.linalg.eig(np.linalg.inv(S) @ C)
    except np.linalg.LinAlgError:
        E, V = np.linalg.eig(np.linalg.pinv(S) @ C)

    real_E = np.real(E)
    idx = np.argmax(real_E)
    coeffs = np.real(V[:, idx])

    A, B, C_ell, D_coeff, E_coeff, F = coeffs

    # 从一般二次曲线参数推导半轴长度
    denom = B ** 2 - 4 * A * C_ell
    if np.abs(denom) < 1e-10:
        return 0, 0

    numerator = 2 * (A * E_coeff ** 2 + C_ell * D_coeff ** 2
                     - B * D_coeff * E_coeff + denom * F)

    term_a = A + C_ell - np.sqrt((A - C_ell) ** 2 + B ** 2)
    term_b = A + C_ell + np.sqrt((A - C_ell) ** 2 + B ** 2)

    if np.abs(term_a) < 1e-10 or np.abs(term_b) < 1e-10:
        return 0, 0

    a_sq = numerator / (denom * term_a)
    b_sq = numerator / (denom * term_b)

    a = np.sqrt(np.abs(a_sq))
    b = np.sqrt(np.abs(b_sq))

    if a < b:
        a, b = b, a

    return a, b


def measure_chest_circumference(pcd, method='ls'):
    """胸围测量：PCA定位躯干主轴 -> 胸部截面 -> 椭圆拟合计周长
    method='ls' 为最小二乘拟合，method='pca' 为传统 PCA 方法
    """
    points = np.asarray(pcd.points)

    # PCA 寻找躯干主轴
    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    # 沿主轴截取胸部区域 (30%-45%)
    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    if method == 'ls':
        a, b = fit_ellipse_least_squares(yz)
    else:
        mean2 = np.mean(yz, axis=0)
        centered2 = yz - mean2
        cov2 = np.cov(centered2.T)
        eigvals2, _ = np.linalg.eig(cov2)
        a = 2 * np.sqrt(eigvals2[0])
        b = 2 * np.sqrt(eigvals2[1])

    if a <= 0 or b <= 0:
        return measure_chest_convex_hull(pcd)  # 椭圆退化时回落凸包

    # Ramanujan 椭圆周长近似公式
    C = np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b)))
    return float(C)


def create_chest_ellipse_geometry(pcd, method='ls'):
    """创建胸部截面椭圆的 3D LineSet 几何体（绿色）"""
    points = np.asarray(pcd.points)

    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    mean2 = np.mean(yz, axis=0)
    centered2 = yz - mean2

    if method == 'ls':
        a, b = fit_ellipse_least_squares(yz)
        cov2 = np.cov(centered2.T)
        _, eigvecs2 = np.linalg.eig(cov2)
        if np.linalg.det(eigvecs2) < 0:
            eigvecs2[:, 1] *= -1
    else:
        cov2 = np.cov(centered2.T)
        eigvals2, eigvecs2 = np.linalg.eig(cov2)
        a = 2 * np.sqrt(max(eigvals2[0], eigvals2[1]))
        b = 2 * np.sqrt(min(eigvals2[0], eigvals2[1]))

    if a <= 0 or b <= 0:
        line_set = o3d.geometry.LineSet()
        return line_set, 0, 0

    if a < b:
        a, b = b, a

    # 生成椭圆轮廓点 (200个采样点)
    theta = np.linspace(0, 2 * np.pi, 200)
    ellipse_2d = np.stack([
        a / 2 * np.cos(theta),
        b / 2 * np.sin(theta)
    ], axis=1)
    ellipse_2d = ellipse_2d @ eigvecs2.T + mean2

    # 映射回 3D
    ellipse_3d = np.zeros((ellipse_2d.shape[0], 3))
    ellipse_3d[:, 0] = center_x
    ellipse_3d[:, 1:3] = ellipse_2d
    ellipse_3d = ellipse_3d @ eigvecs.T + mean

    lines = [[i, i + 1] for i in range(len(ellipse_3d) - 1)]
    lines.append([len(ellipse_3d) - 1, 0])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(ellipse_3d)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.colors = o3d.utility.Vector3dVector([[0, 1, 0]] * len(lines))

    return line_set, a, b


def poisson_reconstruct(pcd, depth=8, scale=1.1, linear_fit=False):
    """泊松曲面重建：法线定向 -> 重建 -> 剔除低密度区域 -> 平滑

    注意：输入点云必须已估算法线，否则会自动计算
    """
    if len(pcd.points) < 100:
        raise ValueError("点云太少，无法重建")

    print("开始泊松重建...")

    # 确保有法线
    if not pcd.has_normals():
        print("估计法向量...")
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=0.03,
                max_nn=30
            )
        )

    # 统一法线方向（关键步骤，避免翻面）
    pcd.orient_normals_consistent_tangent_plane(50)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd,
        depth=depth,
        scale=scale,
        linear_fit=linear_fit
    )

    print("泊松完成")

    # 剔除最稀疏的 2% 顶点
    densities = np.asarray(densities)
    threshold = np.quantile(densities, 0.02)
    vertices_to_remove = densities < threshold
    mesh.remove_vertices_by_mask(vertices_to_remove)

    print("低密度区域已剔除")

    # 拉普拉斯平滑
    mesh = mesh.filter_smooth_simple(number_of_iterations=2)

    mesh.compute_vertex_normals()

    return mesh


def measure_chest_convex_hull(pcd):
    points = np.asarray(pcd.points)

    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    hull = ConvexHull(yz)
    hull_pts = yz[hull.vertices]

    perimeter = 0
    for i in range(len(hull_pts)):
        p1 = hull_pts[i]
        p2 = hull_pts[(i + 1) % len(hull_pts)]
        perimeter += np.linalg.norm(p1 - p2)

    return float(perimeter)


def create_chest_convex_hull_geometry(pcd):
    """创建胸部截面凸包的 3D LineSet 几何体（红色）"""
    points = np.asarray(pcd.points)

    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    hull = ConvexHull(yz)
    hull_pts = yz[hull.vertices]

    hull_3d = np.zeros((len(hull_pts), 3))
    hull_3d[:, 0] = center_x
    hull_3d[:, 1:3] = hull_pts
    hull_3d = hull_3d @ eigvecs.T + mean

    lines = [[i, i + 1] for i in range(len(hull_3d) - 1)]
    lines.append([len(hull_3d) - 1, 0])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(hull_3d)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.colors = o3d.utility.Vector3dVector([[1, 0, 0]] * len(lines))

    return line_set


def measure_chest_concave_hull(pcd, alpha=0.03):
    """Alpha-shape 凹包法测量胸围（精细模式）"""
    points = np.asarray(pcd.points)

    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    shape = alphashape.alphashape(yz, alpha)

    if shape is None or shape.is_empty:
        return 0.0

    return float(shape.length)


def create_chest_concave_hull_geometry(pcd, alpha=0.03):
    """创建胸部截面凹包的 3D LineSet 几何体（紫色）"""
    points = np.asarray(pcd.points)

    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    # 裁剪 Y 轴方向的外围噪声
    proj = crop_by_percent(proj, axis=1, lower=0.0, upper=0.8)

    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    shape = alphashape.alphashape(yz, alpha)

    if shape is None or shape.is_empty:
        return None

    coords = np.array(shape.exterior.coords)

    hull_3d = np.zeros((len(coords), 3))
    hull_3d[:, 0] = center_x
    hull_3d[:, 1:3] = coords
    hull_3d = hull_3d @ eigvecs.T + mean

    lines = [[i, i + 1] for i in range(len(hull_3d) - 1)]
    lines.append([len(hull_3d) - 1, 0])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(hull_3d)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.colors = o3d.utility.Vector3dVector([[1, 0, 1]] * len(lines))

    return line_set


def crop_by_percent(points, axis=2, lower=0.0, upper=1.0):
    """沿指定轴按百分位数范围裁剪点云"""
    vals = points[:, axis]
    low_val = np.percentile(vals, lower * 100)
    high_val = np.percentile(vals, upper * 100)
    mask = (vals >= low_val) & (vals <= high_val)
    return points[mask]


def create_test_cylinder(radius=0.5, height=2.0, n=5000):
    """生成测试用圆柱体点云"""
    theta = np.random.uniform(0, 2 * np.pi, n)
    z = np.random.uniform(-height / 2, height / 2, n)

    x = radius * np.cos(theta)
    y = radius * np.sin(theta)

    points = np.vstack((x, y, z)).T

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    return pcd
