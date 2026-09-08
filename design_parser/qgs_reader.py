import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional
#解析 QGIS 工程文件（.qgs，本质是 XML），提取图层名、数据源路径、几何类型、坐标系和字段信息。
class QgsLayerMeta:
    def __init__(self, name: str, data_source: str, geometry_type: str,
                 srs_authid: Optional[str], fields: Optional[list] = None):
        self.name = name
        self.data_source = data_source       # 相对于工程文件的路径
        self.geometry_type = geometry_type   # point / line / polygon
        self.srs_authid = srs_authid         # 如 'EPSG:4326'
        self.fields = fields or []           # [(field_name, field_type)]

class QgsProject:
    def __init__(self, qgs_path: Path):
        self.qgs_path = qgs_path
        self.layers: List[QgsLayerMeta] = []
        self._parse()

    def _parse(self):
        tree = ET.parse(self.qgs_path)
        root = tree.getroot()
        for maplayer in root.findall('.//maplayer'):
            name = maplayer.find('layername')
            source = maplayer.find('datasource')
            if name is None or source is None:
                continue
            geom_type = self._parse_geom_type(maplayer)
            srs = self._parse_srs(maplayer)
            fields = self._parse_fields(maplayer)
            self.layers.append(QgsLayerMeta(
                name=name.text,
                data_source=source.text,
                geometry_type=geom_type,
                srs_authid=srs,
                fields=fields
            ))

    def _parse_geom_type(self, maplayer) -> Optional[str]:
        type_elem = maplayer.find('geometrytype')
        if type_elem is not None and type_elem.text:
            return type_elem.text.lower()
        return None

    def _parse_srs(self, maplayer) -> Optional[str]:
        srs_elem = maplayer.find('.//spatialrefsys/authid')
        if srs_elem is not None and srs_elem.text:
            return srs_elem.text
        return None

    def _parse_fields(self, maplayer) -> list:
        fields = []
        attrs_elem = maplayer.find('attributes')
        if attrs_elem is not None:
            for attr in attrs_elem.findall('attribute'):
                fname = attr.get('name')
                ftype = attr.get('type')
                if fname:
                    fields.append((fname, ftype or 'unknown'))
        return fields