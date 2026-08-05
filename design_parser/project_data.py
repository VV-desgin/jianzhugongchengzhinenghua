
from .excel_reader import read_excel
from .package import ProjectPackage
from .qgs_reader import QgsProject, QgsLayerMeta
from .layer_reader import LayerReader, count_vector_features, FIONA_AVAILABLE, PYSHP_AVAILABLE
from .feature import UnifiedFeature
from .adapter import LayerAdapter
from .check_result import CheckResult
from .rule_engine import RuleContext, ALL_RULES, SEVERITY_MAP
from typing import Dict, List, Optional
from pathlib import Path
from shapely.geometry import shape
from loguru import logger

try:
    import fiona
except ModuleNotFoundError as exc:
    if exc.name != 'fiona':
        raise
    fiona = None

try:
    import shapefile as pyshp
except ModuleNotFoundError as exc:
    if exc.name != 'shapefile':
        raise
    pyshp = None
import json
import pandas as pd

# BOM/??????????????????????????? + ?????
ENGINEERING_OBJECTS = {
    "cable": {
        "code": ["CODE", "CABLE_CODE"],
        "longueur": ["LONGUEUR", "LGR_REELLE", "LGR_CARTO"],
        "capacite": ["CAPACITE", "CAPACITY", "FIBER_COUNT"],
        "type": ["TYPE_CABLE", "TYPE"],
        "nb_fibre_util": ["NB_FIBRE_U", "NB_FIBRE_UTIL", "NB_FIBRE_D", "fiber_count"],
        "hauteur_appui": [],
    },
    "boite": {
        "code": ["CODE", "BOITE_CODE", "ID"],
        "longueur": [],
        "capacite": ["CAPACITE", "CAPACITY"],
        "type": ["TYPE", "TYPE_BOITE", "BOXTYPE", "TYPE_FONC", "FONCTION"],
        "nb_fibre_util": ["NB_FIBRE_U", "NB_FIBRE_UTIL", "NBFUTILE"],
        "hauteur_appui": ["HAUTEUR_AP", "HAUTEUR_APPUI", "HAUTEUR"],
    },
    "ptech": {
        "code": ["CODE", "PTECH_CODE"],
        "longueur": [],
        "capacite": ["CAPACITE", "CAPACITY"],
        "type": ["TYPE"],
        "nb_fibre_util": ["NB_FIBRE_U", "NB_FIBRE_UTIL"],
        "hauteur_appui": ["HAUTEUR_AP", "HAUTEUR_APPUI"],
    },
}


class ProjectData:
    """工程设计文件解析核心：解压工程包 → 读取 QGS 工程 → 加载所有矢量/表格图层"""
    def __init__(self, archive_path: str):
        outer_pkg = ProjectPackage(archive_path)
        logger.info(f"工程包已解压: {Path(archive_path).name} → {outer_pkg.temp_dir}")
        self.outer_package = outer_pkg
        self.inner_packages = []
        self.extract_failures = list(outer_pkg.extract_failures)

        qgs_files = list(outer_pkg.temp_dir.rglob('*.qgs'))

        qgz_paths = list(outer_pkg.temp_dir.rglob('*.qgz'))
        for qgz_path in qgz_paths:
            try:
                inner_pkg = ProjectPackage(str(qgz_path))
                self.inner_packages.append(inner_pkg)
                self.extract_failures.extend(inner_pkg.extract_failures)
                inner_qgs = list(inner_pkg.temp_dir.rglob('*.qgs'))
                qgs_files.extend(inner_qgs)
            except Exception as e:
                pass

        self.inner_package = self.inner_packages[-1] if self.inner_packages else None

        if not qgs_files:
            self.has_qgis = False
            self.layers = {}
            self.package = self.inner_package if self.inner_package else self.outer_package
            logger.info("未发现 QGIS 工程文件，按普通文件包处理")
            return

        if len(qgs_files) > 1:
            qgs_path = self._select_best_qgs(qgs_files)
        else:
            qgs_path = qgs_files[0]
        logger.info(f"选中 QGIS 工程: {qgs_path.name}（候选 {len(qgs_files)} 个）")

        temp_dir = outer_pkg.temp_dir
        self.package = outer_pkg
        for inner_pkg in self.inner_packages:
            try:
                qgs_path.relative_to(inner_pkg.temp_dir)
                temp_dir = inner_pkg.temp_dir
                self.package = inner_pkg
                break
            except ValueError:
                continue

        self.has_qgis = True
        self.qgs = QgsProject(qgs_path)
        self.reader = LayerReader(temp_dir)
        self.layers: Dict[str, List[UnifiedFeature]] = {}
        self._load_all_layers()

    def _read_vector_file_features(self, actual_path: Path, layer_name: Optional[str],
                                   source_name: str) -> List[UnifiedFeature]:
        """读取矢量图层：SHP 统一走 LayerReader（fiona/pyshp 双后端），其他格式仅 fiona。

        fiona 不可用（如 Python 3.14+）且非 SHP 时返回空列表，由上层按缺失/空图层处理。"""
        if actual_path.suffix.lower() == '.shp':
            meta = QgsLayerMeta(name=source_name, data_source=actual_path.name,
                                geometry_type=None, srs_authid=None)
            try:
                return LayerReader(actual_path.parent).read_vector_layer(meta)
            except Exception:
                return []
        if fiona is None or not FIONA_AVAILABLE:
            return []
        try:
            src = fiona.open(actual_path, layer=layer_name) if layer_name else fiona.open(actual_path)
            with src:
                crs = src.crs.get('init') or src.crs.get('authid')
                features = []
                for i, feat in enumerate(src):
                    geom = shape(feat['geometry']) if feat['geometry'] else None
                    props = dict(feat['properties'])
                    features.append(UnifiedFeature(
                        source_layer_name=source_name,
                        feature_id=i,
                        geometry=geom,
                        properties=props,
                        original_crs=crs
                    ))
            return features
        except Exception:
            return []

    # 标准图层名集合（与 layer_mapping.yaml 中的 key 对应）
    STANDARD_LAYER_NAMES = frozenset({
        'BOITE', 'CABLE', 'IMB', 'SITE', 'PTECH', 'ZNRO', 'ZPM',
        'SRO', 'INFRASTRUCTURE'
    })

    def _select_best_qgs(self, qgs_files: List[Path]) -> Path:
        """五级择优策略：关键字优先级 → 标准图层检查 → GPKG优先 → 要素总数降序 → 平局处理"""
        search_dirs = []
        if hasattr(self, 'outer_package') and self.outer_package:
            search_dirs.append(self.outer_package.temp_dir)
        if hasattr(self, 'inner_packages'):
            for ip in self.inner_packages:
                search_dirs.append(ip.temp_dir)
        elif hasattr(self, 'inner_package') and self.inner_package:
            search_dirs.append(self.inner_package.temp_dir)

        def _display_path(p: Path) -> str:
            """生成可区分同名文件的完整相对路径"""
            for d in search_dirs:
                try:
                    return str(p.relative_to(d))
                except ValueError:
                    continue
            return str(p)

        def _count_layer_features(ds: str) -> int:
            """统计数据源要素数（SHP 走 LayerReader 双后端，GPKG 等仅 fiona）"""
            actual_path = self._find_vector_file(ds, search_dirs)
            if not actual_path:
                return 0
            try:
                layer_name = None
                if '|layername=' in ds:
                    layer_name = ds.split('|layername=')[1].rstrip('.shp')
                if actual_path.suffix.lower() == '.shp':
                    return count_vector_features(actual_path)
                if fiona is None or not FIONA_AVAILABLE:
                    return 0
                if layer_name:
                    with fiona.open(actual_path, layer=layer_name) as src:
                        return len(src)
                with fiona.open(actual_path) as src:
                    return len(src)
            except Exception:
                return 0

        candidates = []

        for qf in qgs_files:
            try:
                qgs = QgsProject(qf)
                has_gpkg = False
                total_features = 0
                ds_types = set()
                standard_layer_count = 0

                for layer_meta in qgs.layers:
                    ds = layer_meta.data_source
                    if ds.startswith(('http://', 'https://', 'type=xyz')):
                        continue

                    if '.gpkg' in ds:
                        has_gpkg = True
                        ds_types.add('GPKG')
                    elif '.shp' in ds:
                        ds_types.add('SHP')

                    if layer_meta.name.upper() in self.STANDARD_LAYER_NAMES:
                        standard_layer_count += 1

                    total_features += _count_layer_features(ds)

                ds_type_str = '/'.join(sorted(ds_types)) if ds_types else 'N/A'
                file_size = qf.stat().st_size if qf.exists() else 0

                candidates.append({
                    'path': qf,
                    'has_gpkg': has_gpkg,
                    'total_features': total_features,
                    'file_size': file_size,
                    'standard_layers': standard_layer_count,
                })
            except Exception as e:
                pass

        if not candidates:
            return qgs_files[0]

        KEYWORD_BONUS = [
            '完整设计图', '竣工图', 'Plan_de_récolement',
            '设计图（含纤芯）', '竣工图（含BOM）'
        ]
        KEYWORD_PENALTY = ['场勘设计图', '场勘']
        for c in candidates:
            path_str = str(c['path'])
            for kw in KEYWORD_BONUS:
                if kw in path_str:
                    c['total_features'] += 100000
                    break
            for kw in KEYWORD_PENALTY:
                if kw in path_str:
                    c['total_features'] = max(0, c['total_features'] - 100000)
                    break

        gpkg_candidates = [c for c in candidates if c['has_gpkg']]
        if gpkg_candidates:
            max_standard_all = max(c['standard_layers'] for c in candidates)
            max_standard_gpkg = max(c['standard_layers'] for c in gpkg_candidates)

            if max_standard_gpkg >= max_standard_all:
                if len(gpkg_candidates) > 1:
                    gpkg_candidates.sort(key=lambda c: c['total_features'], reverse=True)
                best = gpkg_candidates[0]
                return best['path']
            else:
                pass

        candidates.sort(key=lambda c: c['total_features'], reverse=True)

        best_count = candidates[0]['total_features']
        tied = [c for c in candidates if c['total_features'] == best_count]

        if len(tied) > 1:
            non_kancha = [c for c in tied if '场勘设计图' not in str(c['path'])]
            if non_kancha:
                excluded = [c for c in tied if c not in non_kancha]
                for ex in excluded:
                    pass
                tied = non_kancha

            if len(tied) > 1:
                tied.sort(key=lambda c: c['file_size'], reverse=True)

        best = tied[0]
        if best['total_features'] <= 0:
            best = candidates[0] if candidates else {'path': qgs_files[0], 'total_features': 0}

        return best['path']

    def _find_vector_file(self, data_source: str, search_dirs: List[Path]) -> Optional[Path]:
        """
        根据 QGIS 图层数据源字符串,在搜索目录中精确定位矢量文件。
        支持 shapefile 和 geopackage（含 layer 参数）。
        优先匹配相同扩展名,避免跨格式交叉加载导致设备编号体系不一致。
        """
        if '|layername=' in data_source:
            parts = data_source.split('|layername=')
            file_name = Path(parts[0]).name
        else:
            file_name = Path(data_source).name

        target_name = file_name.lower()
        target_ext = Path(file_name).suffix.lower()

        for d in search_dirs:
            #  当存在多个同名文件时（如"完整设计图"和"场勘设计图"目录下都有 BOITE.shp），
            #        选择文件大小最大的那个（空SHP通常只有100 bytes，有数据的有数千 bytes）。
            best_match = None
            best_size = -1
            for ext in ('.shp', '.gpkg'):
                for f in d.rglob(f'*{ext}'):
                    if f.name.lower() == target_name:
                        try:
                            sz = f.stat().st_size
                            if sz > best_size:
                                best_match = f
                                best_size = sz
                        except OSError:
                            pass
            if best_match is not None:
                return best_match

            # 防止 GPKG 图层的 CABLE 错误匹配到 SHP 图层的 CABLE
            if target_ext:
                target_stem = Path(target_name.replace(target_ext, '')).stem.lower()
                for f in d.rglob(f'*{target_ext}'):
                    if target_stem in f.stem.lower() or f.stem.lower() in target_stem:
                        return f

            target_stem = Path(file_name).stem.lower()
            for ext in ('.shp', '.gpkg'):
                if ext == target_ext:
                    continue
                for f in d.rglob(f'{target_stem}{ext}'):
                    return f

            for ext in ('.shp', '.gpkg'):
                if ext == target_ext:
                    continue
                for f in d.rglob(f'*{ext}'):
                    if target_stem in f.stem.lower() or f.stem.lower() in target_stem:
                        return f
        return None

    def _load_all_layers(self):
        search_dirs = [self.package.temp_dir]
        if hasattr(self, 'outer_package') and self.outer_package != self.package:
            search_dirs.append(self.outer_package.temp_dir)
        if hasattr(self, 'inner_packages'):
            for ip in self.inner_packages:
                search_dirs.append(ip.temp_dir)
        elif hasattr(self, 'inner_package') and self.inner_package:
            search_dirs.append(self.inner_package.temp_dir)
        search_dirs = list(set(search_dirs))

        #  记录 QGS 中定义但矢量文件缺失的图层，确保它们出现在结果中
        self.missing_layers = []

        for layer_meta in self.qgs.layers:
            ds = layer_meta.data_source
            if ds.startswith(('http://', 'https://', 'type=xyz')):
                continue

            actual_path = self._find_vector_file(ds, search_dirs)
            if not actual_path:
                self.layers[layer_meta.name] = []
                self.missing_layers.append({
                    "name": layer_meta.name,
                    "data_source": ds,
                })
                continue

            layer_name = None
            if '|layername=' in ds:
                layer_name = ds.split('|layername=')[1].rstrip('.shp')

            try:
                features = self._read_vector_file_features(actual_path, layer_name, layer_meta.name)
                self._normalize_field_names(features)
                self.layers[layer_meta.name] = features

                if len(features) > 0 and all(f._geometry is None for f in features):
                    self._repair_empty_geometry(layer_meta.name, features, search_dirs)

            except Exception:
                pass

        # Fallback: 若某些图层加载为 0 个要素,尝试直接根据图层名搜索 .shp 并强制加载
        #  当存在多个同名 .shp 时，选择文件大小最大的（有数据的）
        for layer_meta in self.qgs.layers:
            if layer_meta.name in self.layers and len(self.layers[layer_meta.name]) == 0:
                for d in search_dirs:
                    candidates = []
                    for f in d.rglob(f'{layer_meta.name}.shp'):
                        if f.stem.lower() == layer_meta.name.lower():
                            try:
                                candidates.append((f, f.stat().st_size))
                            except OSError:
                                pass
                    if not candidates:
                        continue
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    f = candidates[0][0]
                    try:
                        features = self._read_vector_file_features(f, None, layer_meta.name)
                        self.layers[layer_meta.name] = features
                    except Exception:
                        pass
                    if len(self.layers[layer_meta.name]) > 0:
                        break

        self._ensure_full_cable_load(search_dirs)

        self._load_csv_json_files(search_dirs)
        logger.info(f"图层加载汇总: 共 {len(self.layers)} 个图层")
        for _ln, _feats in self.layers.items():
            logger.info(f"  图层 {_ln}: {len(_feats)} 个要素")
        if self.missing_layers:
            logger.info(f"  缺失图层: {[m['name'] for m in self.missing_layers]}")

        # 安全网：从所有矢量文件收集全部设备代码,作为 R008 的补充集
        #     避免因跨格式模糊匹配导致 BOX 与 CABLE 加载了不同编号体系的数据
        self._supplementary_device_codes = set()
        for d in search_dirs:
            for ext in ('.shp', '.gpkg'):
                for f in d.rglob(f'*{ext}'):
                    try:
                        # SHP：fiona 不可用时用 pyshp 回退读取 CODE 字段
                        if f.suffix.lower() == '.shp' and (fiona is None or not FIONA_AVAILABLE):
                            if not PYSHP_AVAILABLE or pyshp is None:
                                continue
                            with pyshp.Reader(str(f)) as src:
                                field_names = [x[0] for x in src.fields[1:]]
                                if 'CODE' not in field_names:
                                    continue
                                code_idx = field_names.index('CODE')
                                for rec in src.records():
                                    if code_idx < len(rec):
                                        code = str(rec[code_idx])
                                        if code and code != 'None':
                                            self._supplementary_device_codes.add(code)
                            continue
                        if fiona is None or not FIONA_AVAILABLE:
                            continue
                        with fiona.open(f) as src:
                            schema_props = src.schema.get('properties', {})
                            code_candidates = [k for k in schema_props if k.upper() == 'CODE']
                            if not code_candidates:
                                continue
                            for feat in src:
                                code = str(feat['properties'].get('CODE', ''))
                                if code:
                                    self._supplementary_device_codes.add(code)
                    except Exception:
                        pass

    def _ensure_full_cable_load(self, search_dirs: List[Path]):
        """确保 CABLE 图层加载了所有记录（包括被标记为删除的记录）。

        当存在多个同名 CABLE.shp 时，选择文件大小最大的（有数据的）。
        SHP 文件的 DBF 中被标记为"已删除"的记录（首字节 0x2A='*'），
        fiona 迭代时会跳过，此处手动读取并补充到要素列表。
        """
        for layer_name in list(self.layers.keys()):
            if 'CABLE' not in layer_name.upper():
                continue

            for d in search_dirs:
                candidates = []
                for f in d.rglob(f'{layer_name}.shp'):
                    if f.stem.lower() == layer_name.lower():
                        try:
                            candidates.append((f, f.stat().st_size))
                        except OSError:
                            pass
                if not candidates:
                    continue
                candidates.sort(key=lambda x: x[1], reverse=True)
                shp_path = candidates[0][0]
                if shp_path and shp_path.exists():
                    try:
                        features = self._read_vector_file_features(shp_path, None, layer_name)
                        # 用 DBF 头记录数判断是否有被跳过的删除记录（fiona/pyshp 迭代均会跳过）
                        total_records = len(features)
                        try:
                            import struct
                            with open(shp_path.with_suffix('.dbf'), 'rb') as f:
                                header = f.read(32)
                                if len(header) >= 12:
                                    total_records = struct.unpack('<I', header[4:8])[0]
                        except Exception:
                            pass

                        if total_records > len(features):
                            deleted_feats = self._read_deleted_dbf_records(
                                shp_path, layer_name, len(features)
                            )
                            features.extend(deleted_feats)

                        self.layers[layer_name] = features
                        break
                    except Exception:
                        pass
            break

    @staticmethod
    def _read_deleted_dbf_records(shp_path: Path, layer_name: str,
                                   start_id: int) -> List[UnifiedFeature]:
        """从 DBF 文件中读取被标记为删除的记录属性。

        SHP 文件的 DBF 组件中，每条记录的第一个字节是删除标志：
        0x20 (空格) = 活跃记录，0x2A (*) = 已删除记录。
        fiona 迭代时会跳过删除记录，但 len() 仍计入。
        本方法手动解析 DBF 二进制文件，提取删除记录的属性数据。
        """
        import struct

        dbf_path = shp_path.with_suffix('.dbf')
        if not dbf_path.exists():
            return []

        try:
            with open(dbf_path, 'rb') as f:
                header = f.read(32)
                num_records = struct.unpack('<I', header[4:8])[0]
                header_size = struct.unpack('<H', header[8:10])[0]
                record_length = struct.unpack('<H', header[10:12])[0]

                # 读取字段描述符（每个 32 字节，以 0x0D 结尾）
                fields = []
                f.seek(32)
                while True:
                    field_data = f.read(32)
                    if not field_data or field_data[0:1] == b'\r':
                        break
                    name = field_data[0:11].split(b'\x00')[0].decode('latin-1', errors='ignore').strip()
                    ftype = chr(field_data[11])
                    flen = field_data[16]
                    fields.append((name, ftype, flen))

                # 读取所有记录，提取删除记录
                f.seek(header_size)
                deleted_features = []
                feat_id = start_id

                for rec_idx in range(num_records):
                    flag = f.read(1)
                    record_data = f.read(record_length - 1)

                    if flag == b'*':
                        # 删除记录 - 解析属性
                        props = {}
                        offset = 0
                        for fname, ftype, flen in fields:
                            raw = record_data[offset:offset + flen]
                            try:
                                value = raw.decode('latin-1').strip()
                            except Exception:
                                value = ''

                            if ftype == 'N':
                                try:
                                    value = int(value) if '.' not in value else float(value)
                                except (ValueError, TypeError):
                                    pass
                            elif ftype == 'L':
                                value = (value.upper() == 'T')

                            if value in ('', 'NULL', 'None', 'N/A'):
                                value = None

                            props[fname] = value
                            offset += flen

                        deleted_features.append(UnifiedFeature(
                            source_layer_name=layer_name,
                            feature_id=feat_id,
                            geometry=None,
                            properties=props,
                            original_crs=None
                        ))
                        feat_id += 1

                return deleted_features
        except Exception as e:
            return []

    def _load_csv_json_files(self, search_dirs: List[Path]):
        """扫描并加载 CSV / JSON 文件（独立于 QGIS 图层的表格数据）"""
        import pandas as pd
        import json

        loaded_stems = set()

        for d in search_dirs:
            for csv_file in d.rglob('*.csv'):
                if csv_file.stem in loaded_stems:
                    continue
                try:
                    df = pd.read_csv(csv_file)
                    features = []
                    for i, (_, row) in enumerate(df.iterrows()):
                        props = {k: (None if pd.isna(v) else v) for k, v in row.to_dict().items()}
                        features.append(UnifiedFeature(
                            source_layer_name=csv_file.stem,
                            feature_id=i,
                            geometry=None,
                            properties=props
                        ))
                    self.layers[csv_file.stem] = features
                    loaded_stems.add(csv_file.stem)
                except Exception as e:
                    pass

            for json_file in d.rglob('*.json'):
                if json_file.stem in loaded_stems:
                    continue
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    features = []
                    if isinstance(data, list):
                        for i, item in enumerate(data):
                            props = item if isinstance(item, dict) else {'value': item}
                            features.append(UnifiedFeature(
                                source_layer_name=json_file.stem,
                                feature_id=i,
                                geometry=None,
                                properties=props
                            ))
                    elif isinstance(data, dict):
                        features.append(UnifiedFeature(
                            source_layer_name=json_file.stem,
                            feature_id=0,
                            geometry=None,
                            properties=dict(data)
                        ))
                    if features:
                        self.layers[json_file.stem] = features
                        loaded_stems.add(json_file.stem)
                except Exception as e:
                    pass

    @staticmethod
    def _normalize_field_names(features: List[UnifiedFeature]):
        """将 SHP 截断字段名（10字符限制）自动补全为官方完整字段名"""
        truncated_fields = {
            # BOITE
            'CODE_POSTA': 'CODE_POSTAL',
            'NB_LOGEMEN': 'NB_LOGEMENT',
            'NB_FIBRE_U': 'NB_FIBRE_UTIL',
            'NB_FIBRE_D': 'NB_FIBRE_DISP',
            'NB_CASSETT': 'NB_CASSETTES_MAX',
            'CABLE_AMON': 'CABLE_AMONT',
            'PROPRIETAI': 'PROPRIETAIRE',
            'GESTIONNAI': 'GESTIONNAIRE',
            'REF_PRODUI': 'REF_PRODUIT',
            'NB_FIBRE_': 'NB_FIBRE_UTIL',
            # IMB
            'NUMERO_VOI': 'NUMERO_VOIE',
            'COMPLEME_1': 'COMPLEMENT_VOIE',
            'NOM_BATIME': 'NOM_BATIMENT',
            'TYPE_BATIM': 'TYPE_BATIMENT',
            'TYPE_CLIEN': 'TYPE_CLIENT',
            'RACCORDEME': 'RACCORDEMENT',
            'NUM_GESTIO': 'NUM_GESTIONNAIRE',
            'COL_MONTAN': 'COL_MONTANTE',
            'SOUS_SOL_C': 'SOUS_SOL_COMMUN',
            'BPE_CODE': 'BPE_CODE',
            # PTECH
            'HAUTEUR_AP': 'HAUTEUR_APPUI',
            'TYPE_APPUI': 'TYPE_APPUI',
            'EFFORT_APP': 'EFFORT_APPUI',
            'NB_BOITIER': 'NB_BOITIERS',
            # SITE
            'REF_PRODUI': 'REF_PRODUIT',
            # CABLE
            'CODE_INFRA': 'CODE_INFRA',
            'TYPE_CABLE': 'TYPE_CABLE',
            'MODE_POSE': 'MODE_POSE',
            # COMMON
            'CODE_PT': 'CODE_PTC',
        }
        for feat in features:
            old_props = dict(feat.properties)
            new_props = {}
            for k, v in old_props.items():
                # 优先保留完整名,截断名做补全
                if k in truncated_fields:
                    full_name = truncated_fields[k]
                    if full_name not in old_props:
                        new_props[full_name] = v
                new_props[k] = v
            feat.properties = new_props

    def _repair_empty_geometry(self, layer_name: str, original_features: List[UnifiedFeature],
                               search_dirs: List[Path]):
        """尝试通过匹配图层名的 .shp 文件修复全部要素几何丢失的问题"""
        for d in search_dirs:
            for candidate in d.rglob(f'{layer_name}.shp'):
                if candidate.stem.lower() == layer_name.lower():
                    try:
                        repaired = self._read_vector_file_features(candidate, None, layer_name)
                        self.layers[layer_name] = repaired
                        return
                    except Exception:
                        pass

        for d in search_dirs:
            for f in d.rglob('*.shp'):
                if layer_name.lower() in f.stem.lower():
                    try:
                        repaired = self._read_vector_file_features(f, None, layer_name)
                        self.layers[layer_name] = repaired
                        return
                    except Exception:
                        pass

    def get_layer_info(self) -> list:
        """返回所有图层信息。

         禁止跳过空图层。空图层也必须出现在结果中，
        明确区分"图层不存在"和"图层存在但要素为 0"。
         对外返回统一标准名称，原始名称保留在 source_layer_name 字段中。
        """
        LAYER_ALIAS_MAP = {
            'INFRA': 'INFRASTRUCTURE',
            'INFRASTRUCTURE': 'INFRASTRUCTURE',
            'BOITE': 'BOITE',
            'CABLE': 'CABLE',
            'IMB': 'IMB',
            'SITE': 'SITE',
            'PTECH': 'PTECH',
            'ZNRO': 'ZNRO',
            'ZPM': 'ZPM',
            'SRO': 'SRO',
        }

        infos = []
        for layer_name, feats in self.layers.items():
            first = feats[0] if feats else None
            if first:
                field_info = [(k, type(v).__name__) for k, v in first.properties.items()]
                geom = first.geometry_type
                geom_type = geom.value if geom else "none"
            else:
                field_info = []
                geom_type = "none"

            upper_name = layer_name.upper()
            standard_name = LAYER_ALIAS_MAP.get(upper_name, layer_name)

            infos.append({
                "layer_name": layer_name,
                "name": standard_name,
                "source_layer_name": layer_name,
                "exists": True,
                "geometry_type": geom_type,
                "fields": field_info,
                "feature_count": len(feats),
            })
        return infos
    def get_engineering_data(self) -> dict:
        """?????????? BOM / ???????????

        ???? objects.cable / objects.boite / objects.ptech?
        ???? code?longueur?capacite?type?nb_fibre_util?hauteur_appui?
        ????????????? None???????????
        """
        result = {"objects": {"cable": [], "boite": [], "ptech": []}}
        for obj_key, field_map in ENGINEERING_OBJECTS.items():
            layer_key = self._find_engineering_layer(obj_key.upper())
            if layer_key is None:
                continue
            for feat in self.layers.get(layer_key, []):
                props = feat.properties or {}
                item = {}
                for out_field, src_keys in field_map.items():
                    value = None
                    for k in src_keys:
                        v = props.get(k)
                        if v is not None and str(v).strip() != "":
                            value = v
                            break
                    if value is None:
                        continue  # ????/????????? JSON ????
                    if out_field in ("longueur", "capacite", "nb_fibre_util", "hauteur_appui"):
                        try:
                            num = float(value)
                            value = int(num) if num.is_integer() else num
                        except (TypeError, ValueError):
                            pass
                    item[out_field] = value
                result["objects"][obj_key].append(item)
        return result

    def _find_engineering_layer(self, prefix: str) -> Optional[str]:
        """?????????????? CABLE?BOITE?PTECH??"""
        for key in self.layers:
            if key.upper().startswith(prefix):
                return key
        return None

    def get_relations(self, include_distances: bool = True) -> dict:
        """上下游关系建模：CABLE.ORIGINE/EXTREMITE 引用 → 设备对象；BOITE/SITE 引用字段。

        输出：
        - objects_indexed: 参与关系建模的对象索引统计（按图层）
        - cable_edges: 每条光缆的 upstream/downstream（含解析到的对象与距离，单位米）
        - unresolved_refs: 引用到但未找到对象的编码（便于追溯数据问题）
        - references: BOITE/SITE 的 REF_NRO/REF_PM/REF_PLAQUE/REF_SRO 引用
        - distance_stats: 端点↔设备距离统计（用于空间阈值校准）
        """
        from .spatial_utils import point_distance_m
        from shapely.geometry import Point

        relation_layers = ("BOITE", "PTECH", "SITE", "IMB", "INFRASTRUCTURE", "ZNRO", "ZPM")

        def is_relation_layer(upper):
            if upper.startswith(("L_", "TYPE")):  # CSV ????l_xxx/Type xxx????????
                return False
            return any(upper == rl or upper.startswith(rl) for rl in relation_layers)
        index = {}
        indexed_count = {}
        for key, feats in self.layers.items():
            upper = key.upper()
            if not is_relation_layer(upper):
                continue
            for feat in feats:
                code = feat.properties.get("CODE") or feat.properties.get("code")
                if code:
                    index.setdefault(str(code), []).append({"layer": upper, "feature": feat})
            indexed_count[upper] = len(feats)

        def resolve(code):
            matches = index.get(str(code))
            return matches[0] if matches else None

        def endpoint_pt(geom, first):
            if geom is None or geom.geom_type != "LineString":
                return None
            coords = list(geom.coords)
            return Point(coords[0] if first else coords[-1])

        edges = []
        unresolved = []
        distances = []
        cable_key = self._find_engineering_layer("CABLE")
        for feat in self.layers.get(cable_key or "", []):
            props = feat.properties or {}
            up_code = props.get("ORIGINE") or props.get("START_CODE")
            down_code = props.get("EXTREMITE") or props.get("END_CODE")
            edge = {"cable_code": props.get("CODE") or props.get("code")}
            for side, code in (("upstream", up_code), ("downstream", down_code)):
                if not code:
                    continue
                target = resolve(code)
                if target is None:
                    unresolved.append({"cable_code": edge["cable_code"], "side": side, "code": str(code)})
                    edge[side] = None
                    continue
                item = {"code": str(code), "layer": target["layer"]}
                if include_distances:
                    pt = endpoint_pt(feat._geometry, side == "upstream")
                    tgeom = target["feature"]._geometry
                    if pt is not None and tgeom is not None:
                        if tgeom.geom_type != "Point" and hasattr(tgeom, "representative_point"):
                            tgeom = tgeom.representative_point()
                        d = point_distance_m(pt, tgeom, feat.original_crs)
                        item["distance_m"] = round(d, 3)
                        distances.append(d)
                edge[side] = item
            edges.append(edge)

        references = []
        for layer in ("BOITE", "SITE"):
            lk = self._find_engineering_layer(layer)
            for feat in self.layers.get(lk or "", []):
                props = feat.properties or {}
                code = props.get("CODE") or props.get("code")
                refs = {k.lower(): props.get(k) for k in ("REF_NRO", "REF_PM", "REF_PLAQUE", "REF_SRO") if props.get(k)}
                if refs:
                    references.append({"layer": layer, "code": code, **refs})

        stats = {"count": len(distances), "min_m": None, "median_m": None, "max_m": None}
        if distances:
            s = sorted(distances)
            n = len(s)
            median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
            stats.update({"min_m": round(s[0], 3), "median_m": round(median, 3), "max_m": round(s[-1], 3)})

        return {
            "objects_indexed": indexed_count,
            "cable_edges": edges,
            "unresolved_refs": unresolved,
            "references": references,
            "distance_stats": stats,
        }

    def get_unified_objects(self, layer_name: str):
        feats = self.layers.get(layer_name)
        if not feats:
            return []
        adapter = LayerAdapter()
        return adapter.convert_layer(feats, layer_name)

    def get_feature_values(self, layer_name: str, limit: int = 10):
        feats = self.layers.get(layer_name, [])
        return [feat.properties for feat in feats[:limit]]

    def get_upstream_downstream(self, cable_layer: str, device_layers: list,
                                start_field='START_CODE', end_field='END_CODE') -> dict:
        code_to_device = {}
        for dev_layer in device_layers:
            for feat in self.layers.get(dev_layer, []):
                code = (feat.properties.get('CODE') or
                        feat.properties.get('code') or
                        feat.properties.get('Code'))
                if code:
                    code_to_device[code] = feat
        cables = self.layers.get(cable_layer, [])
        relations = {}
        for i, cable in enumerate(cables):
            props = cable.properties
            start_code = (props.get(start_field) or
                          props.get(start_field.lower()) or
                          props.get(start_field.upper()))
            end_code = (props.get(end_field) or
                        props.get(end_field.lower()) or
                        props.get(end_field.upper()))
            rel = {}
            if start_code and start_code in code_to_device:
                rel['start'] = code_to_device[start_code]
            if end_code and end_code in code_to_device:
                rel['end'] = code_to_device[end_code]
            if rel:
                relations[i] = rel
        return relations

    def compute_spatial_relations(self, layer1: str, layer2: str, relation='intersects') -> list:
        from shapely import intersects, touches, within, crosses
        func_map = {
            'intersects': intersects,
            'touches': touches,
            'within': within,
            'crosses': crosses
        }
        func = func_map.get(relation, intersects)
        feats1 = self.layers.get(layer1, [])
        feats2 = self.layers.get(layer2, [])
        pairs = []
        for i, f1 in enumerate(feats1):
            if f1._geometry is None:
                continue
            for j, f2 in enumerate(feats2):
                if f2._geometry is None:
                    continue
                if func(f1._geometry, f2._geometry):
                    pairs.append((i, j))
        return pairs

    def run_rule(self, rule_id: str, **kwargs) -> List[CheckResult]:
        rule_func = ALL_RULES.get(rule_id)
        if not rule_func:
            return [CheckResult(check_object=rule_id, passed=False,
                                error_description="规则不存在", rule_id=rule_id)]
        try:
            ctx = RuleContext(self)
            results = rule_func(ctx, **kwargs)
        except Exception as e:
            results = [CheckResult(check_object=rule_id, passed=False,
                                problem_location="执行异常", actual_value=str(e),
                                expected_value="正常", rule_id=rule_id,
                                error_description=f"规则执行失败: {e}")]
        default_severity = SEVERITY_MAP.get(rule_id, "warning")
        for r in results:
            if r.severity is None:
                r.severity = default_severity
        return results

    def run_all_rules(self, rule_params: Optional[dict] = None) -> List[CheckResult]:
        ctx = RuleContext(self)
        results = []
        for rule_id, rule_func in ALL_RULES.items():
            if rule_func is None:
                continue
            default_severity = SEVERITY_MAP.get(rule_id, "warning")
            try:
                if rule_params and rule_id in rule_params:
                    res = rule_func(ctx, **rule_params[rule_id])
                else:
                    res = rule_func(ctx)
                results.extend(res)
            except Exception as e:
                results.append(CheckResult(
                    check_object=f"规则 {rule_id}",
                    passed=False,
                    problem_location="规则执行异常",
                    actual_value=str(e),
                    expected_value="正常执行",
                    rule_id=rule_id,
                    error_description=f"规则执行出错: {e}",
                    severity=default_severity,
                ))
        for r in results:
            if r.severity is None:
                r.severity = SEVERITY_MAP.get(r.rule_id, "warning")
        return results

    def find_file(self, extensions: list, filename: str = None):
        """在解压目录中递归查找符合条件的文件,返回第一个匹配路径或 None"""
        search_dirs = [self.package.temp_dir]
        if hasattr(self, 'outer_package') and self.outer_package and self.outer_package != self.package:
            search_dirs.append(self.outer_package.temp_dir)
        if hasattr(self, 'inner_package') and self.inner_package:
            search_dirs.append(self.inner_package.temp_dir)
        for d in search_dirs:
            for f in d.rglob('*'):
                if f.suffix.lower() in extensions:
                    if filename and f.name != filename:
                        continue
                    return f
        return None

    def get_excel_data(self, filename: str = None) -> Dict[str, List[dict]]:
        """读取工程包中的所有 Excel 文件,返回 {文件名-工作表名: [行数据列表]}"""
        excel_files = []
        search_dirs = [self.package.temp_dir]
        if hasattr(self, 'outer_package') and self.outer_package != self.package:
            search_dirs.append(self.outer_package.temp_dir)
        if hasattr(self, 'inner_package') and self.inner_package:
            search_dirs.append(self.inner_package.temp_dir)
        for d in search_dirs:
            for f in d.rglob('*'):
                if f.suffix.lower() in ('.xlsx', '.xls'):
                    if filename and f.name != filename:
                        continue
                    excel_files.append(f)
        if not excel_files:
            return {}

        all_data = {}
        for f in excel_files:
            try:
                file_data = read_excel(str(f))
                for sheet, rows in file_data.items():
                    key = f"{f.name}-{sheet}"
                    all_data[key] = rows
            except Exception as e:
                pass
        return all_data

    def get_pdf_text(self, filename: str = None) -> str:
        """读取工程包中的 PDF 文件,返回文本内容"""
        pdf_file = self.find_file(['.pdf'], filename)
        if not pdf_file:
            return ""
        from .pdf_reader import extract_text_from_pdf
        return extract_text_from_pdf(str(pdf_file))

    def cleanup(self):
        if hasattr(self, 'outer_package') and self.outer_package is not None:
            self.outer_package.cleanup()
        if hasattr(self, 'inner_package') and self.inner_package is not None:
            self.inner_package.cleanup()
