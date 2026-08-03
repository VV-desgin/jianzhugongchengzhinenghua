"""图层读取器：读取 QGS 元信息对应的矢量图层与表格图层。

矢量图层优先使用 fiona（Python 3.10 ~ 3.13），缺失时回退到纯 Python 的
pyshp（所有 Python 版本可用），保证 Python 3.14+ 上执行
`pip install -r requirements.txt` 后即可直接运行。
"""
import os
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
from shapely.geometry import shape

from .feature import UnifiedFeature
from .qgs_reader import QgsLayerMeta

try:
    import fiona
    _fiona_imported = True
except ModuleNotFoundError as exc:
    if exc.name != "fiona":
        raise
    _fiona_imported = False

try:
    import shapefile as pyshp
    _pyshp_imported = True
except ModuleNotFoundError as exc:
    if exc.name != "shapefile":
        raise
    _pyshp_imported = False

# 可通过环境变量强制选择后端（fiona / pyshp），便于回归测试：
#   $env:DESIGN_PARSER_VECTOR_BACKEND="pyshp"; python -m pytest tests -q
_FORCE_BACKEND = os.environ.get("DESIGN_PARSER_VECTOR_BACKEND", "").strip().lower()

FIONA_AVAILABLE = _fiona_imported and (_FORCE_BACKEND in ("", "fiona"))
PYSHP_AVAILABLE = _pyshp_imported and (_FORCE_BACKEND in ("", "pyshp"))


def count_vector_features(path: Path) -> int:
    """统计矢量文件要素数（fiona 优先，pyshp 回退）；异常时返回 0。"""
    try:
        if FIONA_AVAILABLE:
            with fiona.open(str(path)) as src:
                return len(src)
        if PYSHP_AVAILABLE:
            with pyshp.Reader(str(path)) as src:
                return len(src)
    except Exception:
        pass
    return 0


class LayerReader:
    def __init__(self, base_path: Path):
        self.base_path = base_path

    def read_vector_layer(self, meta: QgsLayerMeta) -> List[UnifiedFeature]:
        """读取 SHP 等矢量图层（fiona 优先，pyshp 纯 Python 回退）。"""
        full_path = self.base_path / meta.data_source
        if FIONA_AVAILABLE:
            return self._read_fiona(full_path, meta)
        if PYSHP_AVAILABLE:
            return self._read_pyshp(full_path, meta)
        raise RuntimeError(
            "缺少矢量读取后端：未安装 fiona 或 pyshp。\n"
            "请执行 `pip install -r requirements.txt`（会自动安装 pyshp）。"
        )

    # ── fiona 后端（Python 3.10 ~ 3.13 首选） ──
    def _read_fiona(self, full_path: Path, meta: QgsLayerMeta) -> List[UnifiedFeature]:
        features = []
        with fiona.open(full_path) as src:
            crs = src.crs.get('init') or src.crs.get('authid')
            for i, feat in enumerate(src):
                geom = shape(feat['geometry']) if feat['geometry'] else None
                props = dict(feat['properties'])
                props.pop('fid', None)
                features.append(UnifiedFeature(
                    source_layer_name=meta.name,
                    feature_id=i,
                    geometry=geom,
                    properties=props,
                    original_crs=crs
                ))
        return features

    # ── pyshp 回退后端（纯 Python，支持 3.14+） ──
    def _read_pyshp(self, full_path: Path, meta: QgsLayerMeta) -> List[UnifiedFeature]:
        """使用 pyshp 读取 SHP：按 .cpg → utf-8 → gbk 顺序尝试解码 DBF。"""
        cpg_enc = None
        cpg_path = full_path.with_suffix('.cpg')
        if cpg_path.exists():
            try:
                cpg_enc = cpg_path.read_text(encoding='utf-8', errors='ignore').strip()
            except OSError:
                pass
        candidates = []
        if cpg_enc:
            candidates.append(cpg_enc)
        candidates += ['utf-8', 'gbk']

        last_exc = None
        for enc in dict.fromkeys(candidates):
            reader = pyshp.Reader(str(full_path), encoding=enc)
            try:
                shape_records = reader.shapeRecords()
            except Exception as exc:  # noqa: BLE001 - 编码不匹配时尝试下一种
                reader.close()
                last_exc = exc
                continue
            try:
                return self._features_from_shape_records(reader, shape_records, meta, full_path)
            finally:
                reader.close()
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"无法读取矢量文件: {full_path}")

    def _features_from_shape_records(self, reader, shape_records, meta: QgsLayerMeta, full_path: Path) -> List[UnifiedFeature]:
        crs = self._crs_from_prj(self._read_prj(full_path)) or meta.srs_authid
        field_names = [f[0] for f in reader.fields[1:]]
        features = []
        for i, shape_record in enumerate(shape_records):
            shp = shape_record.shape
            geometry = None
            if shp.shapeType != 0 and shp.points:
                geometry = shape(shp.__geo_interface__)
            props = dict(zip(field_names, shape_record.record))
            props.pop('fid', None)
            features.append(UnifiedFeature(
                source_layer_name=meta.name,
                feature_id=i,
                geometry=geometry,
                properties=props,
                original_crs=crs
            ))
        return features

    @staticmethod
    def _crs_from_prj(prj_text: Optional[str]) -> Optional[str]:
        """从 .prj 的 WKT 文本中解析 EPSG 编码（如 'EPSG:32629'）。"""
        if not prj_text:
            return None
        # 取最后一个 AUTHORITY["EPSG","..."]：外层 PROJCS/GEOGCS 才是数据坐标系
        matches = re.findall(r'AUTHORITY\["EPSG"\s*,\s*"(\d+)"\]', prj_text, re.IGNORECASE)
        if matches:
            return f"EPSG:{matches[-1]}"
        return None

    @staticmethod
    def _read_prj(full_path: Path) -> Optional[str]:
        """读取同名 .prj 文件（pyshp 不提供 prj 属性，需自行读取）。"""
        prj_path = full_path.with_suffix('.prj')
        if not prj_path.exists():
            return None
        try:
            text = prj_path.read_text(encoding='utf-8', errors='ignore').strip()
            return text or None
        except OSError:
            return None

    def read_table(self, file_path: Path, layer_name: str) -> List[UnifiedFeature]:
        """读取 Excel/CSV/DBF 表格，特征无几何"""
        full_path = self.base_path / file_path
        suffix = full_path.suffix.lower()
        if suffix not in ('.xls', '.xlsx', '.csv', '.dbf'):
            return []
        elif suffix == '.csv':
            df = pd.read_csv(full_path)
        elif suffix == '.dbf':
            from dbfread import DBF
            table = DBF(str(full_path), load=True)
            df = pd.DataFrame(iter(table))
        elif suffix in ('.xls', '.xlsx'):
            df = pd.read_excel(full_path, engine='openpyxl' if suffix == '.xlsx' else None)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}")

        features = []
        for idx, row in df.iterrows():
            props = row.to_dict()
            features.append(UnifiedFeature(
                source_layer_name=layer_name,
                feature_id=idx,
                geometry=None,
                properties=props
            ))
        return features
