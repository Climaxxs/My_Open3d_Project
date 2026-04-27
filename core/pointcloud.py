import open3d as o3d
import numpy as np
from scipy.spatial._qhull import ConvexHull
import alphashape

def build_pcd(points):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    return pcd
#预处理
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

        pcd, _ = pcd.remove_radius_outlier(
            nb_points=8,
            radius=voxel * 3
        )
        #pcd = pcd.select_by_index(ind)

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
#obb测量体长
def measure_dimensions_obb(pcd):
    obb = pcd.get_oriented_bounding_box()

    #三个尺寸（未排序）
    extents = obb.extent  # [e1, e2, e3]

    #按大小排序：体长 > 体宽 > 体高
    order = np.argsort(extents)[::-1]
    length, width, height = extents[order]

    #方向轴
    axes = obb.R[:, order]  # 每一列是一个方向向量

    center = obb.center

    #生成三条测量线的端点
    endpoints = []
    for i in range(3):
        axis = axes[:, i]
        half = extents[order[i]] / 2
        p1 = center - axis * half
        p2 = center + axis * half
        endpoints.append((p1, p2))

    return length, width, height, center, axes, endpoints,obb


# ==================== 新增：最小二乘椭圆拟合 ====================
def fit_ellipse_least_squares(yz_points):

    if len(yz_points) < 6:
        return 0, 0

    x = yz_points[:, 0]
    y = yz_points[:, 1]

    # 构建设计矩阵
    D = np.column_stack([x ** 2, x * y, y ** 2, x, y, np.ones_like(x)])

    # 散射矩阵
    S = D.T @ D

    # 约束矩阵（保证是椭圆不是双曲线）
    C = np.zeros((6, 6))
    C[0, 2] = 2
    C[2, 0] = 2
    C[1, 1] = -1

    # 广义特征值求解
    try:
        E, V = np.linalg.eig(np.linalg.inv(S) @ C)
    except np.linalg.LinAlgError:
        E, V = np.linalg.eig(np.linalg.pinv(S) @ C)

    # 取正特征值对应的特征向量
    real_E = np.real(E)
    idx = np.argmax(real_E)
    coeffs = np.real(V[:, idx])

    A, B, C_ell, D_coeff, E_coeff, F = coeffs

    # 推导几何参数
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
    points = np.asarray(pcd.points)

    # PCA 主轴
    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    # 胸部区域
    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    # 切片
    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    # 根据方法选择 a, b
    if method == 'ls':
        a, b = fit_ellipse_least_squares(yz)
    else:
        # 原 PCA 方法
        mean2 = np.mean(yz, axis=0)
        centered2 = yz - mean2
        cov2 = np.cov(centered2.T)
        eigvals2, _ = np.linalg.eig(cov2)
        a = 2 * np.sqrt(eigvals2[0])
        b = 2 * np.sqrt(eigvals2[1])

    if a <= 0 or b <= 0:
        return measure_chest_convex_hull(pcd)  # 兜底

    # 周长
    C = np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b)))
    return float(C)


def create_chest_ellipse_geometry(pcd, method='ls'):

    points = np.asarray(pcd.points)

    # PCA
    mean = np.mean(points, axis=0)
    centered = points - mean
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]
    proj = centered @ eigvecs

    # 胸部区域
    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)
    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    # 截面
    center_x = np.mean(chest[:, 0])
    thickness = 0.02
    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]
    yz = slice_pts[:, 1:3]

    # 二维中心
    mean2 = np.mean(yz, axis=0)
    centered2 = yz - mean2

    # 椭圆方向和半轴
    if method == 'ls':
        # 最小二乘拟合得到 a, b
        a, b = fit_ellipse_least_squares(yz)
        # 用 PCA 得到方向（最小二乘不直接给方向）
        cov2 = np.cov(centered2.T)
        _, eigvecs2 = np.linalg.eig(cov2)
        if np.linalg.det(eigvecs2) < 0:
            eigvecs2[:, 1] *= -1
    else:
        # 原 PCA 方法
        cov2 = np.cov(centered2.T)
        eigvals2, eigvecs2 = np.linalg.eig(cov2)
        a = 2 * np.sqrt(max(eigvals2[0], eigvals2[1]))
        b = 2 * np.sqrt(min(eigvals2[0], eigvals2[1]))

    if a <= 0 or b <= 0:
        # 兜底：返回空 LineSet
        line_set = o3d.geometry.LineSet()
        return line_set, 0, 0

    if a < b:
        a, b = b, a

    # 椭圆点
    theta = np.linspace(0, 2 * np.pi, 200)
    ellipse_2d = np.stack([
        a / 2 * np.cos(theta),
        b / 2 * np.sin(theta)
    ], axis=1)
    ellipse_2d = ellipse_2d @ eigvecs2.T + mean2

    # 回到 3D
    ellipse_3d = np.zeros((ellipse_2d.shape[0], 3))
    ellipse_3d[:, 0] = center_x
    ellipse_3d[:, 1:3] = ellipse_2d
    ellipse_3d = ellipse_3d @ eigvecs.T + mean

    # LineSet
    lines = [[i, i + 1] for i in range(len(ellipse_3d) - 1)]
    lines.append([len(ellipse_3d) - 1, 0])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(ellipse_3d)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.colors = o3d.utility.Vector3dVector([[0, 1, 0]] * len(lines))

    return line_set, a, b

#泊松
def poisson_reconstruct(pcd, depth=8, scale=1.1, linear_fit=False):

    if len(pcd.points) < 100:
        raise ValueError("点云太少，无法重建")

    print("开始泊松重建...")

    # ===== 1️⃣ 法向量（必须！）=====
    if not pcd.has_normals():
        print("估计法向量...")
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=0.03,
                max_nn=30
            )
        )

    # 法向统一方向（很关键！否则会翻面）
    pcd.orient_normals_consistent_tangent_plane(50)

    # ===== 2️⃣ 泊松重建 =====
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd,
        depth=depth,
        scale=scale,
        linear_fit=linear_fit
    )

    print("泊松完成")

    # ===== 3️⃣ 去除低密度区域（关键优化）=====
    densities = np.asarray(densities)

    threshold = np.quantile(densities, 0.02)  # 去掉最稀疏的2%
    vertices_to_remove = densities < threshold

    mesh.remove_vertices_by_mask(vertices_to_remove)

    print("低密度区域已剔除")

    # ===== 4️⃣ 平滑（可选但推荐）=====
    mesh = mesh.filter_smooth_simple(number_of_iterations=2)

    # ===== 5️⃣ 重新计算法向 =====
    mesh.compute_vertex_normals()

    return mesh

#凸包
def measure_chest_convex_hull(pcd):
    points = np.asarray(pcd.points)

    # PCA
    mean = np.mean(points, axis=0)
    centered = points - mean

    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)

    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]

    proj = centered @ eigvecs

    # 胸部区域
    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)

    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    # 截面
    center_x = np.mean(chest[:, 0])
    thickness = 0.02

    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]

    yz = slice_pts[:, 1:3]

    # 凸包
    hull = ConvexHull(yz)
    hull_pts = yz[hull.vertices]

    # 周长
    perimeter = 0
    for i in range(len(hull_pts)):
        p1 = hull_pts[i]
        p2 = hull_pts[(i+1) % len(hull_pts)]
        perimeter += np.linalg.norm(p1 - p2)

    return float(perimeter)

#画凸包
def create_chest_convex_hull_geometry(pcd):
    points = np.asarray(pcd.points)

    # PCA
    mean = np.mean(points, axis=0)
    centered = points - mean

    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)

    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]

    proj = centered @ eigvecs

    # 胸部区域
    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)

    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    # 截面
    center_x = np.mean(chest[:, 0])
    thickness = 0.02

    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]

    yz = slice_pts[:, 1:3]

    # 凸包
    hull = ConvexHull(yz)
    hull_pts = yz[hull.vertices]

    # 回到3D
    hull_3d = np.zeros((len(hull_pts), 3))
    hull_3d[:, 0] = center_x
    hull_3d[:, 1:3] = hull_pts

    hull_3d = hull_3d @ eigvecs.T + mean

    # LineSet
    lines = [[i, i+1] for i in range(len(hull_3d)-1)]
    lines.append([len(hull_3d)-1, 0])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(hull_3d)
    line_set.lines = o3d.utility.Vector2iVector(lines)

    # 用红色区分（和椭圆绿区分）
    line_set.colors = o3d.utility.Vector3dVector([[1, 0, 0]] * len(lines))

    return line_set

#凹包
def measure_chest_concave_hull(pcd, alpha=0.03):

    points = np.asarray(pcd.points)

    # PCA
    mean = np.mean(points, axis=0)
    centered = points - mean

    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]

    proj = centered @ eigvecs

    # 截面
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

    # 直接用 perimeter（最干净）
    return float(shape.length)

#画凹包
def create_chest_concave_hull_geometry(pcd, alpha=0.03):
    points = np.asarray(pcd.points)

    # PCA
    mean = np.mean(points, axis=0)
    centered = points - mean

    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eig(cov)
    order = np.argsort(eigvals)[::-1]
    eigvecs = eigvecs[:, order]

    proj = centered @ eigvecs
    proj = crop_by_percent(proj, axis=1, lower=0.0, upper=0.8)
    # 截面
    x = proj[:, 0]
    chest_min = np.percentile(x, 30)
    chest_max = np.percentile(x, 45)

    mask = (x > chest_min) & (x < chest_max)
    chest = proj[mask]

    center_x = np.mean(chest[:, 0])
    thickness = 0.02

    slice_mask = np.abs(proj[:, 0] - center_x) < thickness
    slice_pts = proj[slice_mask]

    #裁剪
    # y = slice_pts[:, 1]
    #
    # y_max = np.percentile(y, 80)
    # mask = y < y_max
    #
    # slice_pts = slice_pts[mask]

    yz = slice_pts[:, 1:3]

    # 凹包
    shape = alphashape.alphashape(yz, alpha)

    if shape is None or shape.is_empty:
        return None

    coords = np.array(shape.exterior.coords)

    # 回到3D
    hull_3d = np.zeros((len(coords), 3))
    hull_3d[:, 0] = center_x
    hull_3d[:, 1:3] = coords

    hull_3d = hull_3d @ eigvecs.T + mean

    # LineSet
    lines = [[i, i+1] for i in range(len(hull_3d)-1)]
    lines.append([len(hull_3d)-1, 0])

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(hull_3d)
    line_set.lines = o3d.utility.Vector2iVector(lines)

    # 紫色
    line_set.colors = o3d.utility.Vector3dVector([[1, 0, 1]] * len(lines))

    return line_set
# 裁剪函数
def crop_by_percent(points, axis=2, lower=0.0, upper=1.0):

    vals = points[:, axis]

    low_val = np.percentile(vals, lower * 100)
    high_val = np.percentile(vals, upper * 100)

    mask = (vals >= low_val) & (vals <= high_val)

    return points[mask]

def create_test_cylinder(radius=0.5, height=2.0, n=5000):
    theta = np.random.uniform(0, 2*np.pi, n)
    z = np.random.uniform(-height/2, height/2, n)

    x = radius * np.cos(theta)
    y = radius * np.sin(theta)

    points = np.vstack((x, y, z)).T

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    return pcd