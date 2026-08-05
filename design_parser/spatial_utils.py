# design_parser/spatial_utils.py
from shapely.geometry import Point, LineString, Polygon
from shapely.strtree import STRtree
from typing import List, Tuple, Optional
import pyproj

# 初始化测地线计算器（WGS84椭球）
_geod = pyproj.Geod(ellps='WGS84')

def _degrees_to_meters_approx(lat: float) -> float:
    """近似：纬度 lat 处 1 度经度对应的米数，1 度纬度 ≈ 111320 米"""
    import math
    return math.cos(math.radians(lat)) * 111320.0

def point_geodesic_distance(p1: Point, p2: Point) -> float:
    """计算两点间的测地线距离（米）"""
    _, _, dist = _geod.inv(p1.x, p1.y, p2.x, p2.y)
    return dist

def point_distance_m(p1: Point, p2: Point, crs: Optional[str] = None) -> float:
    """?????????

    ??????? EPSG:4326/4490????????
    ??????? EPSG:26191??????????????
    """
    if crs:
        try:
            from pyproj import CRS
            if CRS.from_user_input(crs).is_geographic:
                return point_geodesic_distance(p1, p2)
        except Exception:
            pass
    low = (crs or "").lower()
    if any(k in low for k in ("4326", "4490", "wgs84", "cgcs2000", "geograph")):
        return point_geodesic_distance(p1, p2)
    return p1.distance(p2)


def build_point_index(points: List[Tuple[str, Point]]):
    """根据设备点列表构建 STRtree 空间索引，返回索引和对应的 code 列表"""
    if not points:
        return None, []
    geoms = [p[1] for p in points]
    codes = [p[0] for p in points]
    return STRtree(geoms), codes

def check_endpoint_on_device(cable_geom: LineString, point_index: Optional[STRtree],
                             device_codes: List[str], tolerance: float = 0.5) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    检查光缆首尾端点是否与设备点重合。
    tolerance: 测地线距离阈值，单位 米
    返回: (是否两端都重合, 起始缺失的设备码, 终止缺失的设备码)
    """
    if point_index is None or len(device_codes) == 0:
        return False, "无设备数据", "无设备数据"

    start_pt = Point(cable_geom.coords[0])
    end_pt = Point(cable_geom.coords[-1])

    start_match = None
    end_match = None

    lat_start = start_pt.y
    lat_end = end_pt.y
    deg_tol_start = tolerance / _degrees_to_meters_approx(lat_start)
    deg_tol_end = tolerance / _degrees_to_meters_approx(lat_end)

    buffer_start = start_pt.buffer(deg_tol_start)
    candidates = point_index.query(buffer_start)
    for idx in candidates:
        geom = point_index.geometries[idx]
        if point_geodesic_distance(start_pt, geom) <= tolerance:
            start_match = device_codes[idx]
            break

    buffer_end = end_pt.buffer(deg_tol_end)
    candidates = point_index.query(buffer_end)
    for idx in candidates:
        geom = point_index.geometries[idx]
        if point_geodesic_distance(end_pt, geom) <= tolerance:
            end_match = device_codes[idx]
            break

    start_ok = start_match is not None
    end_ok = end_match is not None
    missing_start = None if start_ok else "起始端点"
    missing_end = None if end_ok else "终止端点"
    return (start_ok and end_ok), missing_start, missing_end

def check_point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """检查点是否在面内（拓扑关系，与坐标系无关）"""
    return point.within(polygon)

def check_cable_crossing(cable1: LineString, cable2: LineString) -> bool:
    """检查两条光缆是否存在非端点交叉（拓扑关系）"""
    return cable1.crosses(cable2)

def min_distance(obj1, obj2) -> float:
    """
    计算两个几何对象之间的最小测地线距离（米）。
    对于复杂几何，简化为比较两个对象所有顶点之间的测地线距离，取最小值。
    """
    def get_vertices(geom):
        if geom.geom_type == 'Point':
            return [geom]
        elif geom.geom_type == 'LineString':
            return [Point(c) for c in geom.coords]
        elif geom.geom_type == 'Polygon':
            return [Point(c) for c in geom.exterior.coords]
        else:
            try:
                return [Point(c) for c in geom.coords]
            except NotImplementedError:
                return []

    verts1 = get_vertices(obj1)
    verts2 = get_vertices(obj2)
    if not verts1 or not verts2:
        return float('inf')

    min_d = float('inf')
    for v1 in verts1:
        for v2 in verts2:
            d = point_geodesic_distance(v1, v2)
            if d < min_d:
                min_d = d
    return min_d