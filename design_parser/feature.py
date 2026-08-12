from shapely.geometry import Point, LineString, Polygon
from typing import Any, Dict, Optional
from enum import Enum
#定义统一特征对象 UnifiedFeature，包含几何、属性、来源等。
class GeomType(str, Enum):
    POINT = "point"
    LINE = "line"
    POLYGON = "polygon"

class UnifiedFeature:
    def __init__(self, source_layer_name: str, feature_id: int,
                 geometry: Any, properties: Dict[str, Any],
                 original_crs: Optional[str] = None):
        self.source_layer_name = source_layer_name
        self.feature_id = feature_id
        self._geometry = geometry          # shapely geometry 或 None
        self.properties = properties
        self.original_crs = original_crs

    @property
    def geometry_type(self) -> Optional[GeomType]:
        if isinstance(self._geometry, Point):
            return GeomType.POINT
        elif isinstance(self._geometry, LineString):
            return GeomType.LINE
        elif isinstance(self._geometry, Polygon):
            return GeomType.POLYGON
        return None

    def get_coordinates(self):
        """返回简单的坐标表示"""
        if isinstance(self._geometry, Point):
            return [self._geometry.x, self._geometry.y]
        elif isinstance(self._geometry, LineString):
            return list(self._geometry.coords)
        elif isinstance(self._geometry, Polygon):
            return list(self._geometry.exterior.coords)
        return None

    def __repr__(self):
        return f"<UnifiedFeature {self.source_layer_name}:{self.feature_id}>"