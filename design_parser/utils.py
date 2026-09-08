# 工具函数：坐标转换等空间计算辅助
def convert_coords(geometry, src_crs: str, dst_crs: str):
    """坐标系转换（需要 pyproj）"""
    from pyproj import Transformer
    from shapely.ops import transform
    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return transform(transformer.transform, geometry)