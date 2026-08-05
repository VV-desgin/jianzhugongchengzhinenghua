from typing import List, Optional, Dict, Any
from collections import defaultdict
import re
import json
import yaml
from pathlib import Path

import pyproj
from shapely.geometry import Point, LineString, Polygon

from .feature import UnifiedFeature
from .models import Cable, Box
from .check_result import CheckResult
from .spatial_utils import (
    build_point_index,
    check_endpoint_on_device,
    check_point_in_polygon,
    check_cable_crossing,
    min_distance,
    point_geodesic_distance,
)

RULE_IDS = {
    "FILE_MISSING": "R001",
    "LAYER_MISSING": "R002",
    "LAYER_NAME_INVALID": "R003",
    "LAYER_GEOM_TYPE_INVALID": "R004",
    "REQUIRED_FIELD_EMPTY": "R005",
    "FIELD_TYPE_INVALID": "R006",
    "CODE_DUPLICATE": "R007",
    "REFERENCE_NOT_EXIST": "R008",
    "ISOLATED_OBJECT": "R009",
    "CABLE_ENDPOINT_NOT_ON_DEVICE": "R010",
    "CAPACITY_EXCEEDED": "R011",
    "FIBER_DUPLICATE": "R012",
    "FIBER_CORE_DUPLICATE": "R-FIBER-001",
    "LAYER_EMPTY": "R016",
    "CRS_INCONSISTENT": "R017",
    "FIELD_TYPE_CHECK": "R018",
    "CAPACITY_MISMATCH": "R019",
    "PBO_CAPACITY_INSUFFICIENT": "R020",
    "REQUIRED_FIELDS_EXIST": "R021",
    "PBO_COVERAGE_INSUFFICIENT": "R022",
    "CABLE_BREAKPOINT": "R023",
    "CABLE_DEVICE_ENDPOINT_MATCH": "R024",
    "ZNRO_OVERLAP": "R025",
    "ZPM_OVERLAP": "R026",
    "SITE_PM_IN_ZPM": "R027",
    "BOITE_PBO_IN_ZPM": "R028",
    "CABLE_DISTRIBUTION_IN_ZPM": "R029",
    "PM_PBO_PORT_CAPACITY": "R030",
    "FIELD_DOMAIN_CHECK": "R031",
    "FIELD_LENGTH_CHECK": "R032",
    "OFFICIAL_LAYERS_EMPTY": "R033",
    "SITE_PM_ZPM_BIDIRECTIONAL": "R005_1",
    "SITE_PM_BOITE_PBO_BIDIRECTIONAL": "R005_2",
    "SITE_PM_CABLE_DISTRIBUTION_BIDIRECTIONAL": "R005_3",
    "CABLE_BOITE_SITE_BIDIRECTIONAL": "R005_4",
    "SITE_PM_IN_ZPM_V2": "R006_3",
    "BOITE_PBO_IN_ZPM_V2": "R006_4",
    "CABLE_DISTRIBUTION_IN_ZPM_V2": "R006_5",
    "CABLE_ENDPOINT_ON_BOITE": "R006_6",
    "PBO_NB_FIBRE_UTIL_EXCEEDS_CAPACITE": "R007_1",
    "PM_PBO_PORT_EXCEEDS_CABLE_CAPACITY": "R007_2",
}

SEVERITY_MAP = {
    # fatal（阻断级）：触发后阻止报告生成
    "R005_1": "fatal",
    "R005_2": "fatal",
    "R005_3": "fatal",
    "R005_4": "fatal",
    "R006_3": "fatal",
    "R006_4": "fatal",
    "R006_5": "fatal",
    "R006_6": "fatal",
    "R007_1": "fatal",
    "R007_2": "fatal",
    "R010": "fatal",
    "R013": "fatal",
    "R014": "fatal",
    "R015": "fatal",
    "R023": "fatal",
    # error（严重）：记录但不阻断
    "R005": "error",
    "R006": "error",
    "R007": "error",
    "R008": "error",
    "R011": "error",
    "R012": "error",
    "R-FIBER-001": "error",
    "R019": "error",
    "R033": "error",
}

OFFICIAL_LAYERS = {
    "IMB": "point",
    "SITE": "point",
    "BOITE": "point",
    "CABLE": "line",
    "PTECH": "point",
    "INFRASTRUCTURE": "line",
    "ZNRO": "polygon",
    "ZPM": "polygon",
}

OFFICIAL_LAYER_FILE_PATTERNS = [
    "IMB.shp", "IMB.shx", "IMB.dbf", "IMB.prj",
    "SITE.shp", "SITE.shx", "SITE.dbf", "SITE.prj",
    "BOITE.shp", "BOITE.shx", "BOITE.dbf", "BOITE.prj",
    "CABLE.shp", "CABLE.shx", "CABLE.dbf", "CABLE.prj",
    "PTECH.shp", "PTECH.shx", "PTECH.dbf", "PTECH.prj",
    "INFRASTRUCTURE.shp", "INFRASTRUCTURE.shx", "INFRASTRUCTURE.dbf", "INFRASTRUCTURE.prj",
    "ZNRO.shp", "ZNRO.shx", "ZNRO.dbf", "ZNRO.prj",
    "ZPM.shp", "ZPM.shx", "ZPM.dbf", "ZPM.prj",
]

LAYER_ALIASES = {
    "INFRASTRUCTURE": ("INFRA",),
}

def _layer_alias_names(standard_name: str) -> tuple:
    """返回标准图层名及其全部可接受别名。"""
    return (standard_name,) + LAYER_ALIASES.get(standard_name, ())

def _pattern_basenames(pattern: str) -> set:
    """返回文件模式对应的小写基础文件名集合（含别名，如 INFRASTRUCTURE.shp -> {infrastructure.shp, infra.shp}）。"""
    p = Path(pattern)
    ext = p.suffix.lower()
    names = {p.stem.upper() + ext}
    for alias in LAYER_ALIASES.get(p.stem.upper(), ()):
        names.add(alias + ext)
    return {n.lower() for n in names}

def _collect_available_files(ctx) -> list:
    """递归收集外层与内层解压目录中的所有文件路径（去重）。"""
    files = []
    seen = set()
    packages = []
    for pkg in (getattr(ctx, "outer_package", None), ctx.package):
        if pkg is None or id(pkg) in seen:
            continue
        packages.append(pkg)
        seen.add(id(pkg))
    for pkg in packages:
        try:
            files.extend(pkg.list_all_files())
        except Exception:
            continue
    return files

class RuleContext:
    def __init__(self, project_data):
        self.package = project_data.package
        self.qgs = project_data.qgs
        self.layers = project_data.layers

        self.outer_package = getattr(project_data, 'outer_package', None)
        self.inner_packages = getattr(project_data, 'inner_packages', [])
        self.inner_package = getattr(project_data, 'inner_package', None)

        self.cables = []
        for name in self.layers:
            if "CABLE" in name.upper():
                objs = project_data.get_unified_objects(name)
                self.cables.extend(objs)

        self.boxes = []
        device_keywords = ["BOX", "BOITE", "PTECH", "IMB", "SITE", "ZNRO", "ZPM", "SRO"]
        for name in self.layers:
            if any(kw in name.upper() for kw in device_keywords):
                objs = project_data.get_unified_objects(name)
                self.boxes.extend(objs)

        self.device_code_index = {}
        for box in self.boxes:
            if isinstance(box, Box):
                code = box.code
            else:
                code = box.properties.get('CODE')
            if code:
                self.device_code_index[code] = box

        if hasattr(project_data, '_supplementary_device_codes'):
            for code in project_data._supplementary_device_codes:
                if code and code not in self.device_code_index:
                    self.device_code_index[code] = None


        # 官方规则库（图层字段说明/可执行条件），由 ProjectData 缓存，解析失败时置空
        self.rule_library = None
        try:
            self.rule_library = project_data.get_rule_library()
        except Exception:
            self.rule_library = None

def _safe_geometry(obj):
    """安全获取几何属性，兼容 UnifiedFeature._geometry 和模型对象.geometry"""
    if hasattr(obj, 'geometry'):
        return obj.geometry
    if hasattr(obj, '_geometry'):
        return obj._geometry
    return None

def load_required_fields_config():
    yaml_path = Path(__file__).parent / "mappings" / "layer_mapping.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('required_fields', {})


def check_file_missing(ctx: RuleContext, required_files: Optional[List[str]] = None) -> List[CheckResult]:
    if required_files is None:
        required_files = OFFICIAL_LAYER_FILE_PATTERNS
    if not required_files:
        return []
    results = []
    available = {Path(f).name.lower() for f in _collect_available_files(ctx)}
    for req_file in required_files:
        passed = bool(available & _pattern_basenames(req_file))
        results.append(CheckResult(
            check_object=f"文件 {req_file}",
            passed=passed,
            problem_location=None if passed else "压缩包（递归扫描后仍未找到）",
            actual_value="缺失" if not passed else "存在",
            expected_value="存在",
            rule_id=RULE_IDS["FILE_MISSING"],
            error_description=None if passed else f"缺少文件: {req_file}"
        ))
    return results


def check_layer_missing(ctx: RuleContext, required_layers: Optional[List[str]] = None) -> List[CheckResult]:
    if required_layers is None:
        required_layers = list(OFFICIAL_LAYERS.keys())
    if not required_layers:
        return []
    results = []
    present_upper = set()
    for meta in getattr(ctx.qgs, "layers", []) or []:
        if meta.name:
            present_upper.add(meta.name.upper())
    for name in ctx.layers:
        present_upper.add(name.upper())
    for layer_name in required_layers:
        passed = any(alias.upper() in present_upper for alias in _layer_alias_names(layer_name))
        results.append(CheckResult(
            check_object=f"图层 {layer_name}",
            passed=passed,
            problem_location=None if passed else "QGIS工程",
            actual_value="缺失" if not passed else "存在",
            expected_value="存在",
            rule_id=RULE_IDS["LAYER_MISSING"],
            error_description=None if passed else f"缺少图层: {layer_name}"
        ))
    return results


def check_layer_name(ctx: RuleContext, expected_names: Optional[Dict[str, str]] = None) -> List[CheckResult]:
    if expected_names is None:
        expected_names = {k: k for k in OFFICIAL_LAYERS}
    if not expected_names:
        return []
    results = []
    actual_names = set()
    for meta in getattr(ctx.qgs, "layers", []) or []:
        if meta.name:
            actual_names.add(meta.name.upper())
    for name in ctx.layers:
        actual_names.add(name.upper())
    for req_name, standard_name in expected_names.items():
        found = any(alias.upper() in actual_names for alias in _layer_alias_names(req_name))
        passed = found
        results.append(CheckResult(
            check_object=f"图层名称 {req_name}",
            passed=passed,
            problem_location=None if passed else "QGIS工程图层列表",
            actual_value=req_name if found else "缺失",
            expected_value=standard_name,
            rule_id=RULE_IDS["LAYER_NAME_INVALID"],
            error_description=None if passed else f"图层名称应为 '{standard_name}'"
        ))
    return results


def check_layer_geom_type(ctx: RuleContext, expected_types: Optional[Dict[str, str]] = None) -> List[CheckResult]:
    if expected_types is None:
        expected_types = dict(OFFICIAL_LAYERS)
    if not expected_types:
        return []
    results = []
    loaded_upper = {name.upper(): name for name in ctx.layers}
    for standard_name, exp in expected_types.items():
        matched_key = None
        for alias in _layer_alias_names(standard_name):
            if alias.upper() in loaded_upper:
                matched_key = loaded_upper[alias.upper()]
                break
        if matched_key is None:
            continue
        feats = ctx.layers.get(matched_key, [])
        if not feats:
            continue
        geom = feats[0].geometry_type
        actual = geom.value if geom else None
        if actual is None:
            continue
        passed = actual == exp.lower()
        results.append(CheckResult(
            check_object=f"图层 {standard_name}",
            passed=passed,
            problem_location=None if passed else f"图层 {standard_name}",
            actual_value=actual,
            expected_value=exp,
            rule_id=RULE_IDS["LAYER_GEOM_TYPE_INVALID"],
            error_description=None if passed else f"几何类型应为 {exp}，实际为 {actual}"
        ))
    return results


def check_required_fields(ctx: RuleContext, required_fields: Optional[Dict[str, List[str]]] = None) -> List[CheckResult]:
    if required_fields is None:
        required_fields = load_required_fields_config()
    if not required_fields:
        return []

    results = []
    for layer_name, features in ctx.layers.items():
        matched_fields = None
        for cfg_key, fields in required_fields.items():
            if cfg_key.upper() in layer_name.upper():
                matched_fields = fields
                break
        if not matched_fields:
            continue

        for feat in features:
            props = feat.properties
            for field in matched_fields:
                if field not in props:
                    continue
                value = props[field]
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    results.append(CheckResult(
                        check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                        passed=False,
                        problem_location=f"字段 {field}",
                        actual_value="空",
                        expected_value="非空",
                        rule_id=RULE_IDS["REQUIRED_FIELD_EMPTY"],
                        error_description=f"必填字段 '{field}' 为空"
                    ))
    return results


def check_field_type_invalid(ctx: RuleContext) -> List[CheckResult]:
    """R006: 检查字段值类型是否与 YAML 配置的预期类型一致（如 int/float）"""
    yaml_path = Path(__file__).parent / "mappings" / "layer_mapping.yaml"
    if not yaml_path.exists():
        return []
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    layers_config = config.get('layers', {})
    results = []
    for layer_name, features in ctx.layers.items():
        matched_config = None
        for cfg_key in layers_config:
            if cfg_key.upper() in layer_name.upper():
                matched_config = layers_config[cfg_key]
                break
        if not matched_config:
            continue
        conversions = matched_config.get('type_conversions', {})
        for feat in features:
            props = feat.properties
            for field, target_type in conversions.items():
                if field not in props:
                    continue
                value = props[field]
                if value is None:
                    continue
                if target_type == 'int' and not isinstance(value, int):
                    results.append(CheckResult(
                        check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                        passed=False,
                        problem_location=f"字段 {field}",
                        actual_value=f"类型 {type(value).__name__}",
                        expected_value="整数",
                        rule_id="R006",
                        error_description=f"字段 '{field}' 应为整数类型，实际为 {type(value).__name__}"
                    ))
                elif target_type == 'float' and not isinstance(value, (int, float)):
                    results.append(CheckResult(
                        check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                        passed=False,
                        problem_location=f"字段 {field}",
                        actual_value=f"类型 {type(value).__name__}",
                        expected_value="浮点数",
                        rule_id="R006",
                        error_description=f"字段 '{field}' 应为浮点数类型，实际为 {type(value).__name__}"
                    ))
    return results


def _field_specs_by_layer(ctx: RuleContext) -> Dict[str, List[Dict[str, Any]]]:
    """返回官方规则库中的图层字段说明（{图层: [字段字典]}），无规则库时为空。"""
    lib = getattr(ctx, "rule_library", None) or {}
    return lib.get("field_specs", {}) or {}


def _match_spec_layer(spec_layer: str, layer_name: str) -> bool:
    """官方字段说明 sheet（如 BOITE/CABLE）与运行时图层名匹配（大小写不敏感）。"""
    s = spec_layer.strip().upper()
    n = layer_name.strip().upper()
    return bool(s) and s in n


def _case_insensitive_get(props: Dict[str, Any], key: str):
    """字段读取：优先精确匹配，其次大小写不敏感匹配（DBF/GPKG 字段名可能大小写不一）。"""
    if key in props:
        return props[key]
    k_upper = key.upper()
    for k, v in props.items():
        if str(k).upper() == k_upper:
            return v
    return None


def _normalize_type_name(raw: str) -> str:
    return raw.upper().replace("É", "E").replace("È", "E").strip()


_NUMERIC_TYPE_NAMES = (
    "ENTIER", "INTEGER", "INT", "LONG", "SMALLINT",
    "DOUBLE", "NUMERIQUE", "NUMERIC", "REEL", "REAL", "DECIMAL", "FLOAT", "NUMBER",
)


def _is_missing_sentinel(value) -> bool:
    """常见缺失值标记（NA / N/A / SANS OBJET / NULL / 空串）不算类型或长度违规。"""
    if value is None:
        return True
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return True
        return s.upper() in ("NA", "N/A", "NULL", "NONE", "SANS OBJET", "/")
    return False


def _is_int_like(value) -> bool:
    """整数值判定：int/整数 float/可转换字符串（含 '144.0'、千分位下划线）均通过。"""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        s = value.strip().replace(" ", "").replace("_", "")
        if not s:
            return False
        try:
            return float(s.replace(",", ".")).is_integer()
        except ValueError:
            return False
    return False


def _is_number_like(value) -> bool:
    """数值判定：int/float/可转换字符串（兼容小数逗号）通过。"""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        s = value.strip().replace(" ", "")
        if not s:
            return False
        try:
            float(s.replace(",", "."))
            return True
        except ValueError:
            return False
    return False


def _official_type_check(field: str, spec_type: str, value) -> Optional[str]:
    """按官方 Type champ 校验值类型；通过返回 None，不通过返回期望类型标签。"""
    t = _normalize_type_name(spec_type)
    if t in ("ENTIER", "INTEGER", "INT", "LONG", "SMALLINT"):
        return None if _is_int_like(value) else "整数"
    if t in ("DOUBLE", "NUMERIQUE", "NUMERIC", "REEL", "REAL", "DECIMAL", "FLOAT", "NUMBER"):
        return None if _is_number_like(value) else "数值"
    return None  # Texte / 未知类型不强制，避免误报


def _field_value_for_length(value):
    """长度计算用字符串：整数 float 去掉 .0 尾缀，字符串去首尾空白，避免长度误报。"""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        return value.strip()
    return str(value)


def _parse_spec_length(raw: str) -> Optional[int]:
    """从官方 Longueur champ 提取正整数（如 '30' / '30.0'）。"""
    import re as _re
    m = _re.search(r"\d+", raw or "")
    if not m:
        return None
    try:
        return int(m.group(0))
    except (ValueError, TypeError):
        return None


def check_code_duplicate(ctx: RuleContext) -> List[CheckResult]:
    results = []
    code_count = {}
    for box in ctx.boxes:
        code = box.code if isinstance(box, Box) else box.properties.get('CODE')
        if code:
            code_count[code] = code_count.get(code, 0) + 1
    for code, count in code_count.items():
        if count > 1:
            dup_boxes = [b for b in ctx.boxes if b.code == code]
            ids = ', '.join([b.id for b in dup_boxes])
            results.append(CheckResult(
                check_object=f"设备代码 {code}",
                passed=False,
                problem_location="CODE",
                actual_value=f"重复 {count} 次",
                expected_value="唯一",
                rule_id=RULE_IDS["CODE_DUPLICATE"],
                error_description=f"设备代码重复，涉及对象ID: {ids}"
            ))
    cable_codes = {}
    for cable in ctx.cables:
        if cable.code:
            cable_codes[cable.code] = cable_codes.get(cable.code, 0) + 1
    for code, count in cable_codes.items():
        if count > 1:
            dup_cables = [c for c in ctx.cables if c.code == code]
            ids = ', '.join([c.id for c in dup_cables])
            results.append(CheckResult(
                check_object=f"光缆代码 {code}",
                passed=False,
                problem_location="CODE",
                actual_value=f"重复 {count} 次",
                expected_value="唯一",
                rule_id=RULE_IDS["CODE_DUPLICATE"],
                error_description=f"光缆代码重复，涉及对象ID: {ids}"
            ))
    return results


def check_reference_exists(ctx: RuleContext) -> List[CheckResult]:
    results = []
    device_codes = set()
    for box in ctx.boxes:
        if isinstance(box, Box):
            device_codes.add(box.code)
        else:
            device_codes.add(box.properties.get('CODE'))
    device_codes.update(ctx.device_code_index.keys())
    for cable in ctx.cables:
        if isinstance(cable, Cable):
            start = cable.start_device
            end = cable.end_device
            code = cable.code or cable.id
        else:
            start = cable.properties.get('ORIGINE')
            end = cable.properties.get('EXTREMITE')
            code = cable.properties.get('CODE', cable.properties.get('fid', str(cable.feature_id)))
        for field, label in [('start', start), ('end', end)]:
            dev_code = start if field == 'start' else end
            if dev_code and dev_code not in device_codes:
                results.append(CheckResult(
                    check_object=f"光缆 {code}",
                    passed=False,
                    problem_location=f"字段 {field}",
                    actual_value=dev_code,
                    expected_value="存在的设备代码",
                    rule_id=RULE_IDS["REFERENCE_NOT_EXIST"],
                    error_description=f"引用的{label}设备代码 '{dev_code}' 不存在"
                ))
    return results


def check_isolated_objects(ctx: RuleContext) -> List[CheckResult]:
    results = []
    connected = set()
    for cable in ctx.cables:
        if isinstance(cable, Cable):
            s = cable.start_device
            e = cable.end_device
        else:
            s = cable.properties.get('ORIGINE')
            e = cable.properties.get('EXTREMITE')
        if s: connected.add(s)
        if e: connected.add(e)

    for box in ctx.boxes:
        code = box.code if isinstance(box, Box) else box.properties.get('CODE')
        if not code:
            continue
        boite_type = box.properties.get('TYPE') if not isinstance(box, Box) else getattr(box, 'type', None)
        if hasattr(box, 'properties'):
            boite_type = box.properties.get('TYPE')
        else:
            boite_type = getattr(box, 'type', None)
        if boite_type not in ('BPE', 'PBO'):
            continue
        if code not in connected:
            results.append(CheckResult(
                check_object=f"设备 {code}",
                passed=False,
                problem_location="拓扑",
                actual_value="未连接",
                expected_value="至少被一条光缆连接",
                rule_id=RULE_IDS["ISOLATED_OBJECT"],
                error_description=f"光盒子 {code}（{boite_type}）在拓扑中孤立，无光缆连接"
            ))
    return results


def check_cable_endpoint_on_device(ctx: RuleContext, tolerance: float = 0.5) -> List[CheckResult]:
    results = []
    if not ctx.boxes or not ctx.cables:
        return results

    point_list = []
    for box in ctx.boxes:
        if isinstance(box, Box):
            code = box.code
            geom = box.geometry
        else:
            code = box.properties.get('CODE')
            geom = getattr(box, 'geometry', None)
        if code and geom is not None and isinstance(geom, Point):
            point_list.append((code, geom))
    if not point_list:
        return results

    index, codes = build_point_index(point_list)

    for cable in ctx.cables:
        if isinstance(cable, Cable):
            code = cable.code
            geom = cable.geometry
        else:
            code = cable.properties.get('CODE')
            geom = _safe_geometry(cable)
        if geom is None or not isinstance(geom, LineString):
            continue
        ok, missing_start, missing_end = check_endpoint_on_device(
            geom, index, codes, tolerance
        )
        if not ok:
            problem = f"{missing_start or ''} {missing_end or ''}".strip()
            results.append(CheckResult(
                check_object=f"光缆 {code or '未知编码'}",
                passed=False,
                problem_location=problem,
                actual_value="端点未重合",
                expected_value=f"与设备点距离 ≤ {tolerance}m",
                rule_id=RULE_IDS["CABLE_ENDPOINT_NOT_ON_DEVICE"],
                error_description=f"光缆{problem}未在 {tolerance}m 范围内找到设备点"
            ))
    return results


def check_capacity_exceeded(ctx: RuleContext, max_capacity: Optional[int] = None) -> List[CheckResult]:
    results = []
    if max_capacity is None:
        return results
    for box in ctx.boxes:
        if box.capacity and box.capacity > max_capacity:
            results.append(CheckResult(
                check_object=f"设备 {box.code}",
                passed=False,
                problem_location="字段 capacity",
                actual_value=str(box.capacity),
                expected_value=f"≤ {max_capacity}",
                rule_id=RULE_IDS["CAPACITY_EXCEEDED"],
                error_description=f"容量 {box.capacity} 超过上限 {max_capacity}"
            ))
    return results


def check_fiber_duplicate(ctx: RuleContext) -> List[CheckResult]:
    """R012: 检查光缆纤芯是否超配（已用纤芯 > 可用纤芯）"""
    results = []
    cable_features = []
    for layer_name, features in ctx.layers.items():
        if 'CABLE' in layer_name.upper():
            cable_features = features
            break
    if not cable_features:
        for cable in ctx.cables:
            code = cable.code if isinstance(cable, Cable) else cable.properties.get('CODE')
            nb_util = (cable.properties.get('NB_FIBRE_U') or cable.properties.get('NB_FIBRE_UTIL'))
            nb_disp = (cable.properties.get('NB_FIBRE_D') or cable.properties.get('NB_FIBRE_DISP'))
            if nb_util is not None and nb_disp is not None:
                try:
                    if int(nb_util) > int(nb_disp):
                        results.append(CheckResult(
                            check_object=f"光缆 {code}",
                            passed=False,
                            problem_location="纤芯占用",
                            actual_value=f"已用 {nb_util}, 可用 {nb_disp}",
                            expected_value="已用纤芯 ≤ 可用纤芯",
                            rule_id="R012",
                            error_description=f"光缆 {code} 已用纤芯 ({nb_util}) 超过可用纤芯 ({nb_disp})"
                        ))
                except (ValueError, TypeError):
                    continue
        return results

    for feat in cable_features:
        props = feat.properties
        code = props.get('CODE')
        nb_util = props.get('NB_FIBRE_U') or props.get('NB_FIBRE_UTIL')
        nb_disp = props.get('NB_FIBRE_D') or props.get('NB_FIBRE_DISP')
        if nb_util is None or nb_disp is None:
            continue
        try:
            util = int(nb_util)
            disp = int(nb_disp)
        except (ValueError, TypeError):
            continue
        if util > disp:
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location="纤芯占用",
                actual_value=f"已用 {util}, 可用 {disp}",
                expected_value="已用纤芯 ≤ 可用纤芯",
                rule_id="R012",
                error_description=f"光缆 {code} 已用纤芯 ({util}) 超过可用纤芯 ({disp})"
            ))
    return results


def _project_roots(ctx: RuleContext) -> List[Path]:
    """返回项目包全部解压根目录（外层包/主包/内嵌包），不存在时返回空。"""
    roots: List[Path] = []
    for attr in ("package", "outer_package"):
        pkg = getattr(ctx, attr, None)
        if pkg is not None and getattr(pkg, "temp_dir", None) is not None:
            roots.append(Path(pkg.temp_dir))
    for ip in getattr(ctx, "inner_packages", []) or []:
        if getattr(ip, "temp_dir", None) is not None:
            roots.append(Path(ip.temp_dir))
    return [r for r in roots if r.exists()]


FIBER_SHEET_KEYWORDS = ("纤芯", "接续", "分配", "topo", "splice", "fiber", "fibre")
FIBER_SHEET_ROW_LIMIT = 1000


def _find_fiber_excel_sheets(ctx: RuleContext) -> Dict[str, Dict[str, Any]]:
    """收集项目内纤芯相关 Excel 工作表（{文件路径: {sheet: {headers, rows}}}）。

    只读取工作表名含纤芯/接续/分配/topo/splice/fiber 关键词或 SRO/BPE/PBO 页签的表，
    单表最多 FIBER_SHEET_ROW_LIMIT 行，避免扫描 BOM 大表拖慢规则引擎。
    """
    from .bom_fiber_reader import EXCEL_EXTS, list_sheet_names, read_sheet_rows

    out: Dict[str, Dict[str, Any]] = {}
    seen = set()
    for root in _project_roots(ctx):
        try:
            files = sorted(root.rglob("*"))
        except OSError:
            continue
        for f in files:
            if not f.is_file() or f.suffix.lower() not in EXCEL_EXTS:
                continue
            try:
                key = str(f.resolve())
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            try:
                names = list_sheet_names(f)
            except Exception:
                continue
            wanted = [
                n for n in names
            ]
            wanted = [
                n for n in names
                if n == "纤芯连接与分配"
                or any(k in n.lower() for k in FIBER_SHEET_KEYWORDS)
                or re.match(r"^(SRO|BPE|PBO)[-_]", n)
            ]
            if not wanted:
                continue
            sheet_data = {}
            for n in wanted:
                try:
                    data = read_sheet_rows(f, sheet=n, limit=FIBER_SHEET_ROW_LIMIT)
                except Exception:
                    continue
                if data.get("headers"):
                    sheet_data[n] = data
            if sheet_data:
                out[key] = sheet_data
    return out


def check_fiber_core_duplicate(ctx: RuleContext) -> List[CheckResult]:
    """R-FIBER-001：纤芯连接与分配表中，无分路器时同一输入纤芯被重复使用。"""
    from .case_checks import find_fiber_core_duplicates

    results: List[CheckResult] = []
    for sheet_data in _find_fiber_excel_sheets(ctx).values():
        sheets = {
            name: [data["headers"]] + data["rows"]
            for name, data in sheet_data.items()
        }
        for issue in find_fiber_core_duplicates(sheets):
            results.append(CheckResult(
                check_object=f"纤芯 {issue['object']}",
                passed=False,
                problem_location=issue["object"],
                actual_value="输入纤芯被重复使用",
                expected_value="同一输入纤芯仅使用一次",
                rule_id="R-FIBER-001",
                error_description=issue["message"],
                severity="error",
            ))
    return results


def check_device_in_coverage(ctx: RuleContext, coverage_layer: str = "INFRASTRUCTURE") -> List[CheckResult]:
    results = []
    coverage_features = ctx.layers.get(coverage_layer, [])
    if not coverage_features:
        return results
    polygons = []
    for feat in coverage_features:
        geom = feat._geometry
        if geom and isinstance(geom, Polygon):
            polygons.append(geom)
    if not polygons:
        return results
    for box in ctx.boxes:
        geom = box.geometry if isinstance(box, Box) else _safe_geometry(box)
        if not geom or not isinstance(geom, Point):
            continue
        inside = any(poly.contains(geom) for poly in polygons)
        if not inside:
            results.append(CheckResult(
                check_object=f"设备 {box.code if isinstance(box, Box) else box.properties.get('CODE')}",
                passed=False,
                problem_location="覆盖区域",
                actual_value="不在任何覆盖区域内",
                expected_value="处于覆盖区域内",
                rule_id="R013",
                error_description="设备点未在任何覆盖区域面内"
            ))
    return results


def check_cable_crossing_rule(ctx: RuleContext) -> List[CheckResult]:
    results = []
    cable_geoms = []
    for cable in ctx.cables:
        geom = cable.geometry if isinstance(cable, Cable) else _safe_geometry(cable)
        if geom and isinstance(geom, LineString):
            code = cable.code if isinstance(cable, Cable) else cable.properties.get('CODE')
            cable_geoms.append((code, geom))
    for i in range(len(cable_geoms)):
        for j in range(i+1, len(cable_geoms)):
            code1, geom1 = cable_geoms[i]
            code2, geom2 = cable_geoms[j]
            if check_cable_crossing(geom1, geom2):
                results.append(CheckResult(
                    check_object=f"光缆 {code1} 与 {code2}",
                    passed=False,
                    problem_location="交叉点",
                    actual_value="存在错误交叉",
                    expected_value="仅允许端点接触",
                    rule_id="R014",
                    error_description=f"光缆 {code1} 和 {code2} 发生非端点交叉"
                ))
    return results


def check_distance_between(ctx: RuleContext, layer1: str = "", layer2: str = "",
                           min_dist: float = 0.5) -> List[CheckResult]:
    results = []
    if not layer1 or not layer2:
        return results
    feats1 = ctx.layers.get(layer1, [])
    feats2 = ctx.layers.get(layer2, [])
    if not feats1 or not feats2:
        return results
    for i, f1 in enumerate(feats1):
        if f1._geometry is None:
            continue
        for j, f2 in enumerate(feats2):
            if f2._geometry is None:
                continue
            if layer1 == layer2 and i == j:
                continue
            d = min_distance(f1._geometry, f2._geometry)
            if d < min_dist:
                results.append(CheckResult(
                    check_object=f"{layer1} id={i} vs {layer2} id={j}",
                    passed=False,
                    problem_location=f"最近距离 {d:.3f}m",
                    actual_value=str(round(d, 3)),
                    expected_value=f"≥ {min_dist}m",
                    rule_id="R015",
                    error_description=f"对象间距 {d:.3f}m < 规定最小距离 {min_dist}m"
                ))
    return results


def check_layer_empty(ctx: RuleContext) -> List[CheckResult]:
    results = []
    for layer_name, features in ctx.layers.items():
        if len(features) == 0:
            results.append(CheckResult(
                check_object=f"图层 {layer_name}",
                passed=False,
                problem_location="图层数据",
                actual_value="0 个要素",
                expected_value="至少包含1个要素",
                rule_id=RULE_IDS["LAYER_EMPTY"],
                error_description=f"图层 '{layer_name}' 为空，不包含任何要素"
            ))
    return results


def check_official_layers_empty(ctx: RuleContext) -> List[CheckResult]:
    """R033: 检查 8 个官方图层是否至少各有 1 条数据。"""
    results = []
    loaded_lookup = {name.upper(): name for name in ctx.layers.keys()}

    for official_name in OFFICIAL_LAYERS:
        matched_name = loaded_lookup.get(official_name.upper())
        if matched_name is None:
            results.append(CheckResult(
                check_object=f"图层 {official_name}",
                passed=False,
                problem_location="QGIS 工程图层列表",
                actual_value="图层缺失",
                expected_value=f"存在 {official_name} 图层且至少 1 条数据",
                rule_id="R033",
                error_description=f"官方图层 '{official_name}' 未找到（可能不存在或命名不正确）"
            ))
            continue

        features = ctx.layers.get(matched_name, [])
        count = len(features)
        if count == 0:
            results.append(CheckResult(
                check_object=f"图层 {official_name}",
                passed=False,
                problem_location=f"图层 {matched_name}",
                actual_value="0 条数据",
                expected_value="至少 1 条数据",
                rule_id="R033",
                error_description=f"官方图层 '{official_name}' 存在但为空（0 条数据）"
            ))
        else:
            results.append(CheckResult(
                check_object=f"图层 {official_name}",
                passed=True,
                actual_value=f"{count} 条数据",
                expected_value="至少 1 条数据",
                rule_id="R033",
            ))

    return results


def check_crs_consistency(ctx: RuleContext, target_crs: Optional[str] = None) -> List[CheckResult]:
    results = []
    crs_map = {}
    for layer_name, features in ctx.layers.items():
        if not features:
            continue
        first_feat = features[0]
        crs = first_feat.original_crs
        crs_map[layer_name] = crs if crs else "未定义"

    if target_crs is None:
        yaml_path = Path(__file__).parent / "mappings" / "layer_mapping.yaml"
        if yaml_path.exists():
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            target_crs = config.get('target_crs', 'EPSG:4490')
        else:
            target_crs = 'EPSG:4490'
    
    target_crs_lower = target_crs.lower()
    for layer_name, crs in crs_map.items():
        if crs.lower() != target_crs_lower:
            results.append(CheckResult(
                check_object=f"图层 {layer_name}",
                passed=False,
                problem_location="坐标系",
                actual_value=crs,
                expected_value=target_crs,
                rule_id=RULE_IDS["CRS_INCONSISTENT"],
                error_description=f"图层 '{layer_name}' 的坐标系为 {crs}，与目标 {target_crs} 不一致"
            ))
    
    unique_crs = {c.lower() for c in crs_map.values()}
    if len(unique_crs) > 1:
        results.append(CheckResult(
            check_object="所有图层",
            passed=False,
            problem_location="坐标系",
            actual_value=str(unique_crs),
            expected_value="所有图层坐标系一致",
            rule_id=RULE_IDS["CRS_INCONSISTENT"],
            error_description="不同图层使用了不同的坐标系，请统一"
        ))
    return results


def check_field_types(ctx: RuleContext) -> List[CheckResult]:
    """R018: 字段类型检查 = YAML 配置（int/float）+ 官方字段说明 Type champ（Texte/Entier/Double…）。"""
    results = []
    flagged = set()  # (图层, 要素, 字段) 已判定字段，避免 YAML 与官方字段说明重复报

    # 1) YAML 图层配置中的类型转换（归一化字段名经 field_map 解析到原始字段）
    yaml_path = Path(__file__).parent / "mappings" / "layer_mapping.yaml"
    if yaml_path.exists():
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        layers_config = config.get('layers', {})
        for layer_name, features in ctx.layers.items():
            matched_config = None
            for cfg_key in layers_config:
                if cfg_key.upper() in layer_name.upper():
                    matched_config = layers_config[cfg_key]
                    break
            if not matched_config:
                continue
            conversions = matched_config.get('type_conversions', {})
            if not conversions:
                continue
            field_map = matched_config.get('field_map', {}) or {}
            for feat in features:
                props = feat.properties
                for norm_field, target_type in conversions.items():
                    fm = field_map.get(norm_field)
                    raw_fields = fm if isinstance(fm, list) and fm else [norm_field]
                    for raw in raw_fields:
                        value = props.get(raw)
                        if _is_missing_sentinel(value):
                            continue
                        if target_type == 'int' and not _is_int_like(value):
                            results.append(CheckResult(
                                check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                                passed=False,
                                problem_location=f"字段 {raw}",
                                actual_value=str(value),
                                expected_value="可转换为整数",
                                rule_id=RULE_IDS["FIELD_TYPE_CHECK"],
                                error_description=f"字段 '{raw}' 的值 '{value}' 无法转换为整数"
                            ))
                            flagged.add((layer_name, feat.feature_id, raw.upper()))
                        elif target_type == 'float' and not _is_number_like(value):
                            results.append(CheckResult(
                                check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                                passed=False,
                                problem_location=f"字段 {raw}",
                                actual_value=str(value),
                                expected_value="可转换为浮点数",
                                rule_id=RULE_IDS["FIELD_TYPE_CHECK"],
                                error_description=f"字段 '{raw}' 的值 '{value}' 无法转换为浮点数"
                            ))
                            flagged.add((layer_name, feat.feature_id, raw.upper()))
                        break
    # 2) 官方字段说明（Type champ）驱动：Entier→整数，Double/Numérique→数值，Texte 不强制
    for spec_layer, fields in _field_specs_by_layer(ctx).items():
        for layer_name, features in ctx.layers.items():
            if not _match_spec_layer(spec_layer, layer_name):
                continue
            for f in fields:
                field = f.get("name", "").strip()
                spec_type = f.get("type", "").strip()
                if not field or not spec_type:
                    continue
                for feat in features:
                    props = feat.properties
                    value = _case_insensitive_get(props, field)
                    if _is_missing_sentinel(value):
                        continue
                    if (layer_name, feat.feature_id, field.upper()) in flagged:
                        continue
                    expected = _official_type_check(field, spec_type, value)
                    if expected is None:
                        continue
                    results.append(CheckResult(
                        check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                        passed=False,
                        problem_location=f"字段 {field}",
                        actual_value=str(value),
                        expected_value=expected,
                        rule_id=RULE_IDS["FIELD_TYPE_CHECK"],
                        error_description=f"字段 '{field}' 的值 '{value}' 应为{expected}（官方字段说明 Type={spec_type}）"
                    ))
    return results


def check_capacity_match(ctx: RuleContext) -> List[CheckResult]:
    results = []
    device_capacity = {}
    for box in ctx.boxes:
        code = box.code if isinstance(box, Box) else box.properties.get('CODE')
        if not code:
            continue
        cap = box.capacity if isinstance(box, Box) else box.properties.get('CAPACITE')
        if cap is None:
            continue
        try:
            cap_num = int(re.findall(r'\d+', str(cap))[0]) if re.findall(r'\d+', str(cap)) else None
            if cap_num:
                device_capacity[code] = cap_num
        except:
            pass
    for cable in ctx.cables:
        code = cable.code if isinstance(cable, Cable) else cable.properties.get('CODE')
        start = cable.start_device if isinstance(cable, Cable) else cable.properties.get('ORIGINE')
        end = cable.end_device if isinstance(cable, Cable) else cable.properties.get('EXTREMITE')
        cap = cable.capacity if isinstance(cable, Cable) else cable.properties.get('CAPACITE')
        if cap is None:
            continue
        try:
            cable_cap_num = int(re.findall(r'\d+', str(cap))[0]) if re.findall(r'\d+', str(cap)) else None
        except:
            continue
        if cable_cap_num is None:
            continue
        if start and start in device_capacity:
            dev_cap = device_capacity[start]
            if cable_cap_num > dev_cap:
                results.append(CheckResult(
                    check_object=f"光缆 {code}",
                    passed=False,
                    problem_location=f"起点设备 {start}",
                    actual_value=f"光缆容量 {cable_cap_num}, 设备容量 {dev_cap}",
                    expected_value="光缆容量 ≤ 设备容量",
                    rule_id=RULE_IDS["CAPACITY_MISMATCH"],
                    error_description=f"光缆容量 ({cable_cap_num}) 超过起点设备 {start} 容量 ({dev_cap})"
                ))
        if end and end in device_capacity:
            dev_cap = device_capacity[end]
            if cable_cap_num > dev_cap:
                results.append(CheckResult(
                    check_object=f"光缆 {code}",
                    passed=False,
                    problem_location=f"终点设备 {end}",
                    actual_value=f"光缆容量 {cable_cap_num}, 设备容量 {dev_cap}",
                    expected_value="光缆容量 ≤ 设备容量",
                    rule_id=RULE_IDS["CAPACITY_MISMATCH"],
                    error_description=f"光缆容量 ({cable_cap_num}) 超过终点设备 {end} 容量 ({dev_cap})"
                ))
    return results


def check_pbo_capacity(ctx: RuleContext) -> List[CheckResult]:
    results = []
    for box in ctx.boxes:
        code = box.code if isinstance(box, Box) else box.properties.get('CODE')
        if not code:
            continue
        original_feat = None
        for layer_name, features in ctx.layers.items():
            for feat in features:
                if feat.properties.get('CODE') == code:
                    original_feat = feat
                    break
            if original_feat:
                break
        if original_feat is None:
            continue
        boite_type = original_feat.properties.get('TYPE')
        if boite_type != 'PBO':
            continue
        nb_fibre_util = original_feat.properties.get('NB_FIBRE_U') or original_feat.properties.get('NB_FIBRE_UTIL')
        if nb_fibre_util is None:
            continue
        try:
            nb_util = int(nb_fibre_util)
        except (ValueError, TypeError):
            continue
        cap = original_feat.properties.get('CAPACITE')
        if cap is None:
            continue
        try:
            cap_num = int(re.findall(r'\d+', str(cap))[0]) if re.findall(r'\d+', str(cap)) else None
        except:
            continue
        if cap_num is None:
            continue
        if nb_util > cap_num:
            results.append(CheckResult(
                check_object=f"设备 {code}",
                passed=False,
                problem_location="容量检查",
                actual_value=f"已用纤芯 {nb_util}, 容量 {cap_num}",
                expected_value="已用纤芯 ≤ 容量",
                rule_id=RULE_IDS["PBO_CAPACITY_INSUFFICIENT"],
                error_description=f"PBO 已用纤芯 ({nb_util}) 超过容量 ({cap_num})"
            ))
    return results


def check_required_fields_exist(ctx: RuleContext) -> List[CheckResult]:
    required_fields = load_required_fields_config()
    if not required_fields:
        return []
    results = []
    for layer_name, features in ctx.layers.items():
        if not features:
            continue
        first_feat = features[0]
        props = first_feat.properties
        matched_fields = None
        for cfg_key, fields in required_fields.items():
            if cfg_key.upper() in layer_name.upper():
                matched_fields = fields
                break
        if not matched_fields:
            continue
        TRUNCATED_MAP = {
            'CODE_POSTA': 'CODE_POSTAL', 'CODE_PT': 'CODE_PTC',
            'NUMERO_VOI': 'NUMERO_VOIE', 'NUMERO_VO': 'NUMERO_VOIE',
            'COMPLEME_1': 'COMPLEMENT_VOIE', 'COMPLEMEN': 'COMPLEMENT_NUM',
            'NOM_BATIME': 'NOM_BATIMENT', 'NOM_BATI': 'NOM_BATIMENT',
            'TYPE_BATIM': 'TYPE_BATIMENT', 'TYPE_BATI': 'TYPE_BATIMENT',
            'TYPE_CLIEN': 'TYPE_CLIENT', 'TYPE_CLIE': 'TYPE_CLIENT',
            'NB_LOC_RES': 'NB_LOC_RES', 'NB_LOC_PRO': 'NB_LOC_PRO',
            'NB_LOC_TOT': 'NB_LOC_TOT',
            'RACCORDEME': 'RACCORDEMENT', 'RACCORDE': 'RACCORDEMENT',
            'NUM_GESTIO': 'NUM_GESTIONNAIRE', 'NUM_GESTI': 'NUM_GESTIONNAIRE',
            'COL_MONTAN': 'COL_MONTANTE', 'COL_MONTA': 'COL_MONTANTE',
            'SOUS_SOL_C': 'SOUS_SOL_COMMUN',
            'BPE_CODE': 'BPE_CODE',
            'NB_FIBRE_U': 'NB_FIBRE_UTIL', 'NB_FIBRE_': 'NB_FIBRE_UTIL',
            'NB_FIBRE_D': 'NB_FIBRE_DISP',
            'CABLE_AMON': 'CABLE_AMONT',
            'NB_CASSETT': 'NB_CASSETTES_MAX',
            'HAUTEUR_AP': 'HAUTEUR_APPUI',
            'TYPE_APPUI': 'TYPE_APPUI',
            'EFFORT_APP': 'EFFORT_APPUI',
            'NB_BOITIER': 'NB_BOITIERS',
            'REF_PRODUI': 'REF_PRODUIT', 'REF_PRODU': 'REF_PRODUIT',
            'PROPRIETAI': 'PROPRIETAIRE', 'PROPRIETA': 'PROPRIETAIRE',
            'GESTIONNAI': 'GESTIONNAIRE', 'GESTIONNA': 'GESTIONNAIRE',
            'PROPRIETAR': 'PROPRIETAIRE',
        }
        for field in matched_fields:
            if field not in props:
                truncated_found = False
                field_upper = field.upper()
                for prop_key in props:
                    prop_upper = prop_key.upper()
                    if prop_key in TRUNCATED_MAP and TRUNCATED_MAP[prop_key] == field:
                        truncated_found = True
                        break
                    if prop_upper[:10] == field_upper[:10]:
                        truncated_found = True
                        break
                    if prop_upper in field_upper or field_upper in prop_upper:
                        truncated_found = True
                        break
                if not truncated_found:
                    results.append(CheckResult(
                        check_object=f"图层 {layer_name}",
                        passed=False,
                        problem_location=f"字段 {field}",
                        actual_value="字段不存在",
                        expected_value=f"必填字段 '{field}'",
                        rule_id="R021",
                        error_description=f"图层 '{layer_name}' 缺少必填字段 '{field}'"
                    ))
    return results


def check_pbo_coverage(ctx: RuleContext) -> List[CheckResult]:
    results = []
    imb_data = {}
    if "IMB" in ctx.layers:
        for feat in ctx.layers["IMB"]:
            bpe_code = feat.properties.get('BPE_CODE')
            nb_loc_tot = feat.properties.get('NB_LOC_TOT')
            if bpe_code and nb_loc_tot is not None:
                try:
                    imb_data[bpe_code] = int(nb_loc_tot)
                except (ValueError, TypeError):
                    continue
    if not imb_data:
        for layer_name, features in ctx.layers.items():
            if "IMB" in layer_name.upper():
                for feat in features:
                    bpe_code = feat.properties.get('BPE_CODE')
                    nb_loc_tot = feat.properties.get('NB_LOC_TOT')
                    if bpe_code and nb_loc_tot is not None:
                        try:
                            imb_data[bpe_code] = int(nb_loc_tot)
                        except (ValueError, TypeError):
                            continue
                break

    for box in ctx.boxes:
        code = box.code if isinstance(box, Box) else box.properties.get('CODE')
        if not code:
            continue
        original_feat = None
        for layer_name, features in ctx.layers.items():
            for feat in features:
                if feat.properties.get('CODE') == code:
                    original_feat = feat
                    break
            if original_feat:
                break
        if original_feat is None:
            continue
        boite_type = original_feat.properties.get('TYPE')
        if boite_type != 'PBO':
            continue
        coverage = imb_data.get(code, 0)
        if coverage == 0:
            continue
        cap = original_feat.properties.get('CAPACITE')
        if cap is None:
            continue
        try:
            cap_num = int(re.findall(r'\d+', str(cap))[0]) if re.findall(r'\d+', str(cap)) else None
        except:
            continue
        if cap_num is None:
            continue
        if cap_num < coverage:
            results.append(CheckResult(
                check_object=f"设备 {code}",
                passed=False,
                problem_location="容量覆盖检查",
                actual_value=f"容量 {cap_num}, 覆盖户数 {coverage}",
                expected_value="容量 ≥ 覆盖户数",
                rule_id="R022",
                error_description=f"PBO 容量 ({cap_num}) 小于覆盖建筑户数 ({coverage})"
            ))
    return results


def check_cable_breakpoints(ctx: RuleContext, max_gap: float = 100.0) -> List[CheckResult]:
    """R023: 全局光缆端点连接性检查，检测孤立端点（最近邻距离 > max_gap 米）"""
    results = []
    geod = pyproj.Geod(ellps='WGS84')

    all_endpoints = []
    for feat in _get_cable_features(ctx):
        geom = _safe_geometry(feat) if not isinstance(feat, (Cable,)) else feat.geometry
        if geom is None or not isinstance(geom, LineString):
            continue
        code = feat.properties.get('CODE') if not isinstance(feat, (Cable,)) else feat.code
        all_endpoints.append((geom.coords[0][0], geom.coords[0][1], code, "起点"))
        all_endpoints.append((geom.coords[-1][0], geom.coords[-1][1], code, "终点"))

    if len(all_endpoints) < 2:
        return results

    for i, (lon1, lat1, code1, label1) in enumerate(all_endpoints):
        min_dist = float('inf')
        nearest_code = None
        for j, (lon2, lat2, code2, label2) in enumerate(all_endpoints):
            if i == j:
                continue
            if code1 == code2:
                continue
            _, _, d = geod.inv(lon1, lat1, lon2, lat2)
            if d < min_dist:
                min_dist = d
                nearest_code = code2
        if min_dist > max_gap:
            results.append(CheckResult(
                check_object=f"光缆 {code1} 的{label1}",
                passed=False,
                problem_location="孤立端点",
                actual_value=f"最近邻距离 {min_dist:.1f}m (最近光缆 {nearest_code})",
                expected_value=f"≤ {max_gap}m",
                rule_id=RULE_IDS["CABLE_BREAKPOINT"],
                error_description=f"光缆 {code1} 的{label1}孤立，与最近光缆 {nearest_code} 端点距离 {min_dist:.1f}m 超过阈值 {max_gap}m"
            ))
    return results

def _get_cable_features(ctx: RuleContext):
    for layer_name, features in ctx.layers.items():
        if 'CABLE' in layer_name.upper():
            return features
    return ctx.cables


def check_cable_device_endpoint_match(ctx: RuleContext, tolerance: float = 0.5) -> List[CheckResult]:
    results = []
    if not ctx.cables:
        return results

    device_geom = {}
    for box in ctx.boxes:
        code = box.code if isinstance(box, Box) else box.properties.get('CODE')
        geom = box.geometry if isinstance(box, Box) else _safe_geometry(box)
        if code and geom and isinstance(geom, Point):
            device_geom[code] = geom

    for cable in ctx.cables:
        if isinstance(cable, Cable):
            code = cable.code or cable.id
            origine = cable.start_device
            extremite = cable.end_device
            geom = cable.geometry
        else:
            code = cable.properties.get('CODE') or str(cable.feature_id)
            origine = cable.properties.get('ORIGINE')
            extremite = cable.properties.get('EXTREMITE')
            geom = _safe_geometry(cable)

        if geom is None or not isinstance(geom, LineString):
            continue

        if origine and extremite and origine == extremite:
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location="ORIGINE == EXTREMITE",
                actual_value=f"ORIGINE={origine}, EXTREMITE={extremite}",
                expected_value="ORIGINE ≠ EXTREMITE",
                rule_id=RULE_IDS["CABLE_DEVICE_ENDPOINT_MATCH"],
                error_description=f"光缆起点设备和终点设备相同 ({origine})，形成自环"
            ))
            continue

        if not origine or not extremite:
            continue

        pt_o = device_geom.get(origine)
        pt_e = device_geom.get(extremite)
        if not pt_o or not pt_e:
            continue

        start_pt = Point(geom.coords[0])
        end_pt = Point(geom.coords[-1])

        d_o_s = point_geodesic_distance(pt_o, start_pt)
        d_o_e = point_geodesic_distance(pt_o, end_pt)
        d_e_s = point_geodesic_distance(pt_e, start_pt)
        d_e_e = point_geodesic_distance(pt_e, end_pt)

        match1 = (d_o_s <= tolerance and d_e_e <= tolerance)
        match2 = (d_o_e <= tolerance and d_e_s <= tolerance)

        if not (match1 or match2):
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location="设备代码与端点不匹配",
                actual_value=f"ORIGINE距离起点{d_o_s:.1f}m终点{d_o_e:.1f}m; EXTREMITE距离起点{d_e_s:.1f}m终点{d_e_e:.1f}m",
                expected_value=f"ORIGINE/EXTREMITE 设备点与光缆两端点一一重合 (≤{tolerance}m)",
                rule_id=RULE_IDS["CABLE_DEVICE_ENDPOINT_MATCH"],
                error_description=f"光缆 {code} 的设备代码与端点未正确对应"
            ))
    return results


def check_znro_overlap(ctx: RuleContext) -> List[CheckResult]:
    results = []
    layer_name = None
    for name in ctx.layers:
        if 'ZNRO' in name.upper():
            layer_name = name
            break
    if not layer_name:
        return results

    polys = []
    for feat in ctx.layers[layer_name]:
        geom = feat._geometry
        if geom and isinstance(geom, Polygon):
            polys.append((feat.properties.get('CODE', feat.feature_id), geom))

    for i in range(len(polys)):
        for j in range(i+1, len(polys)):
            code1, poly1 = polys[i]
            code2, poly2 = polys[j]
            if poly1.intersects(poly2) and not poly1.touches(poly2):
                results.append(CheckResult(
                    check_object=f"ZNRO 多边形重叠",
                    passed=False,
                    problem_location=f"{code1} 与 {code2}",
                    actual_value="存在重叠区域",
                    expected_value="仅允许共边或共点（相切）",
                    rule_id="R025",
                    error_description=f"ZNRO 图层中 {code1} 与 {code2} 多边形重叠"
                ))
    return results


def check_zpm_overlap(ctx: RuleContext) -> List[CheckResult]:
    results = []
    layer_name = None
    for name in ctx.layers:
        if 'ZPM' in name.upper():
            layer_name = name
            break
    if not layer_name:
        return results

    polys = []
    for feat in ctx.layers[layer_name]:
        geom = feat._geometry
        if geom and isinstance(geom, Polygon):
            polys.append((feat.properties.get('CODE', feat.feature_id), geom))

    for i in range(len(polys)):
        for j in range(i+1, len(polys)):
            code1, poly1 = polys[i]
            code2, poly2 = polys[j]
            if poly1.intersects(poly2) and not poly1.touches(poly2):
                results.append(CheckResult(
                    check_object=f"ZPM 多边形重叠",
                    passed=False,
                    problem_location=f"{code1} 与 {code2}",
                    actual_value="存在重叠区域",
                    expected_value="仅允许共边或共点（相切）",
                    rule_id="R026",
                    error_description=f"ZPM 图层中 {code1} 与 {code2} 多边形重叠"
                ))
    return results


def _build_zpm_index(ctx: RuleContext) -> Dict[str, Polygon]:
    zpm_index = {}
    for layer_name in ctx.layers:
        if 'ZPM' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                code = feat.properties.get('CODE')
                geom = feat._geometry
                if code and geom and isinstance(geom, Polygon):
                    zpm_index[code] = geom
            break
    return zpm_index


def check_site_pm_in_zpm(ctx: RuleContext) -> List[CheckResult]:
    results = []
    zpm_index = _build_zpm_index(ctx)
    if not zpm_index:
        return results

    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                site_type = feat.properties.get('TYPE')
                if site_type != 'PM':
                    continue
                code = feat.properties.get('CODE')
                geom = feat._geometry
                if not code or not geom or not isinstance(geom, Point):
                    continue
                poly = zpm_index.get(code)
                if not poly:
                    continue
                if not poly.contains(geom):
                    results.append(CheckResult(
                        check_object=f"SITE PM {code}",
                        passed=False,
                        problem_location="不在对应ZPM内",
                        actual_value=f"坐标 ({geom.x:.6f}, {geom.y:.6f})",
                        expected_value=f"必须在 ZPM {code} 多边形内",
                        rule_id="R027",
                        error_description=f"光交箱 PM {code} 未在对应的 ZPM 范围内"
                    ))
            break
    return results


def check_boite_pbo_in_zpm(ctx: RuleContext) -> List[CheckResult]:
    results = []
    zpm_index = _build_zpm_index(ctx)
    if not zpm_index:
        return results

    site_to_zpm = {}
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    site_code = feat.properties.get('CODE')
                    if site_code and site_code in zpm_index:
                        site_to_zpm[site_code] = site_code
            break

    for layer_name in ctx.layers:
        if 'BOITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') != 'PBO':
                    continue
                ref_pm = feat.properties.get('REF_PM')
                if not ref_pm:
                    continue
                zpm_code = site_to_zpm.get(ref_pm)
                if not zpm_code:
                    continue
                poly = zpm_index.get(zpm_code)
                if not poly:
                    continue
                geom = feat._geometry
                if not geom or not isinstance(geom, Point):
                    continue
                if not poly.contains(geom):
                    results.append(CheckResult(
                        check_object=f"BOITE PBO {feat.properties.get('CODE')}",
                        passed=False,
                        problem_location=f"不在 ZPM {zpm_code} 内",
                        actual_value=f"坐标 ({geom.x:.6f}, {geom.y:.6f})",
                        expected_value=f"必须在 ZPM {zpm_code} 多边形内",
                        rule_id="R028",
                        error_description=f"终端盒 PBO {feat.properties.get('CODE')} 未在归属的 ZPM 范围内"
                    ))
            break
    return results


def check_cable_distribution_in_zpm(ctx: RuleContext) -> List[CheckResult]:
    results = []
    zpm_index = _build_zpm_index(ctx)
    if not zpm_index:
        return results

    site_to_zpm = {}
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    site_code = feat.properties.get('CODE')
                    if site_code and site_code in zpm_index:
                        site_to_zpm[site_code] = site_code
            break

    for cable in ctx.cables:
        if isinstance(cable, Cable):
            type_cable = getattr(cable, 'type_cable', None)
            ref_pm = getattr(cable, 'ref_pm', None)
            code = cable.code
            geom = cable.geometry
        else:
            type_cable = cable.properties.get('TYPE_CABLE')
            ref_pm = cable.properties.get('REF_PM')
            code = cable.properties.get('CODE')
            geom = _safe_geometry(cable)

        if type_cable != 'DISTRIBUTION':
            continue
        if not ref_pm or not geom or not isinstance(geom, LineString):
            continue
        zpm_code = site_to_zpm.get(ref_pm)
        if not zpm_code:
            continue
        poly = zpm_index.get(zpm_code)
        if not poly:
            continue

        outside_pts = []
        for pt in geom.coords:
            point = Point(pt)
            if not poly.contains(point):
                outside_pts.append(pt)
        if outside_pts:
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location=f"部分点不在 ZPM {zpm_code} 内",
                actual_value=f"出界点数量: {len(outside_pts)}",
                expected_value="所有节点均位于ZPM内",
                rule_id="R029",
                error_description=f"DISTRIBUTION光缆 {code} 的几何存在位于 ZPM {zpm_code} 外的点"
            ))
    return results


def check_pm_pbo_port_capacity(ctx: RuleContext) -> List[CheckResult]:
    results = []
    pm_codes = set()
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    code = feat.properties.get('CODE')
                    if code:
                        pm_codes.add(code)
            break

    if not pm_codes:
        return results

    def extract_num(val):
        if val is None:
            return 0
        nums = re.findall(r'\d+', str(val))
        return int(nums[0]) if nums else 0

    pm_pbo_sum = defaultdict(int)
    for layer_name in ctx.layers:
        if 'BOITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') != 'PBO':
                    continue
                ref_pm = feat.properties.get('REF_PM')
                if ref_pm and ref_pm in pm_codes:
                    cap = extract_num(feat.properties.get('CAPACITE'))
                    pm_pbo_sum[ref_pm] += cap
            break

    pm_cable_sum = defaultdict(int)
    for layer_name in ctx.layers:
        if 'CABLE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE_CABLE') != 'DISTRIBUTION':
                    continue
                ref_pm = feat.properties.get('REF_PM')
                if ref_pm and ref_pm in pm_codes:
                    cap_num = extract_num(feat.properties.get('CAPACITE'))
                    pm_cable_sum[ref_pm] += cap_num
            break

    for pm_code in pm_codes:
        pbo_total = pm_pbo_sum.get(pm_code, 0)
        cable_total = pm_cable_sum.get(pm_code, 0)
        if pbo_total > cable_total:
            results.append(CheckResult(
                check_object=f"PM {pm_code}",
                passed=False,
                problem_location="PBO端口容量 vs 光缆芯数",
                actual_value=f"PBO容量和={pbo_total}, 光缆芯数和={cable_total}",
                expected_value="PBO容量之和 ≤ 光缆芯数之和",
                rule_id="R030",
                error_description=f"PM {pm_code} 下 PBO 端口总容量 ({pbo_total}) 超过以该PM为逻辑起点的DISTRIBUTION光缆芯数总和 ({cable_total})"
            ))
    return results


def check_field_domain(ctx: RuleContext) -> List[CheckResult]:
    """R031: 检查字段值是否在 CSV 定义的域值范围内（兼容分号、逗号分隔）"""
    yaml_path = Path(__file__).parent / "mappings" / "layer_mapping.yaml"
    if not yaml_path.exists():
        return []
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    csv_rules = config.get('csv_validation', [])
    if not csv_rules:
        return []

    results = []
    csv_data = {}
    search_dirs = [ctx.package.temp_dir]
    if hasattr(ctx, 'outer_package') and ctx.outer_package:
        search_dirs.append(ctx.outer_package.temp_dir)
    if hasattr(ctx, 'inner_packages'):
        for ip in ctx.inner_packages:
            search_dirs.append(ip.temp_dir)
    elif hasattr(ctx, 'inner_package') and ctx.inner_package:
        search_dirs.append(ctx.inner_package.temp_dir)
    search_dirs = list(set(search_dirs))

    import csv as csv_module

    for rule in csv_rules:
        csv_file = rule['csv_file']
        if csv_file not in csv_data:
            file_path = None
            for d in search_dirs:
                for f in d.rglob(csv_file):
                    file_path = f
                    break
                if file_path:
                    break
            if not file_path:
                continue

            try:
                valid_vals = set()
                with open(file_path, 'r', encoding='utf-8-sig') as csvf:
                    sample = csvf.read(4096)
                    csvf.seek(0)
                    dialect = csv_module.Sniffer().sniff(sample, delimiters=';,')
                    reader = csv_module.reader(csvf, dialect)
                    next(reader, None)
                    for row in reader:
                        if not row:
                            continue
                        val = row[0].strip()
                        if val:
                            valid_vals.add(val)
                csv_data[csv_file] = valid_vals
            except Exception as e:
                continue

        target_layer = rule['target_layer']
        target_field = rule['target_field']
        valid_set = csv_data.get(csv_file, set())
        if not valid_set:
            continue

        for layer_name, features in ctx.layers.items():
            if target_layer != '*' and target_layer.upper() not in layer_name.upper():
                continue
            for feat in features:
                value = feat.properties.get(target_field)
                if value is None:
                    continue
                value_str = str(value).strip()
                is_valid = value_str in valid_set
                if not is_valid:
                    value_upper = value_str.upper()
                    valid_upper = {v.upper() for v in valid_set}
                    if value_upper in valid_upper:
                        is_valid = True
                    else:
                        for v in valid_upper:
                            if value_upper in v or v in value_upper:
                                is_valid = True
                                break
                        if not is_valid:
                            value_first = value_upper.split()[0].split(';')[0].split(',')[0]
                            for v in valid_upper:
                                v_first = v.split()[0].split(';')[0].split(',')[0]
                                if value_first == v_first:
                                    is_valid = True
                                    break
                if not is_valid:
                    results.append(CheckResult(
                        check_object=f"{layer_name} 要素 {feat.properties.get('CODE', feat.feature_id)}",
                        passed=False,
                        problem_location=f"字段 {target_field}",
                        actual_value=value_str,
                        expected_value=f"在 CSV 域值表中 ({', '.join(sorted(valid_set)[:10])}...)",
                        rule_id="R031",
                        error_description=f"字段 '{target_field}' 的值 '{value_str}' 不在允许的域值范围内"
                    ))
    return results


_LENGTH_RULES_CACHE = None


def _load_length_rules():
    """加载长度检查配置（length_rules.json）。"""
    global _LENGTH_RULES_CACHE
    if _LENGTH_RULES_CACHE is None:
        p = Path(__file__).parent / "mappings" / "length_rules.json"
        try:
            _LENGTH_RULES_CACHE = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _LENGTH_RULES_CACHE = {"enabled": False, "rules": {}}
    return _LENGTH_RULES_CACHE


_PREFIX_RE = re.compile(r"^[A-Z]{2,4}-[A-Z]{2,6}-")
_PORT_RE = re.compile(r"-\d{3}$")


def _effective_length_text(field, value):
    """按配置计算有效长度文本。

    支持：
    - prefix_mode="auto" ：自动剥除固定前缀（如 CDI-UNF- / CTR-INWI-）；
    - strip_increment=true ：剥除末尾 -NNN（Increment/端口号）。
    仅对配置中的字段生效，其他字段保持全串。
    """
    cfg = _load_length_rules()
    text = _field_value_for_length(value)
    if not cfg.get("enabled"):
        return text
    rules = cfg.get("rules", {})
    rule = {}
    for _k, _v in rules.items():
        if field.upper() == _k.upper() or field[:10].upper() == _k[:10].upper():
            rule = _v
            break
    if not rule:
        return text
    if rule.get("prefix_mode") == "auto":
        m = _PREFIX_RE.match(text)
        if m:
            text = text[len(m.group(0)):]
    if rule.get("strip_increment"):
        m = _PORT_RE.search(text)
        if m:
            text = text[:m.start()]
    return text


def check_field_length(ctx: RuleContext) -> List[CheckResult]:
    """R032: 字段长度检查 = YAML 配置最大长度 + 官方字段说明 Longueur champ。"""
    results = []
    flagged = set()  # (图层, 要素, 字段) 已判定字段，避免 YAML 与官方字段说明重复报

    # 1) YAML 图层配置中的最大长度（保留既有行为，数值长度归一化避免 .0 误报）
    yaml_path = Path(__file__).parent / "mappings" / "layer_mapping.yaml"
    if yaml_path.exists():
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        layers_config = config.get('layers', {})
        for layer_name, features in ctx.layers.items():
            matched_config = None
            for cfg_key in layers_config:
                if cfg_key.upper() in layer_name.upper():
                    matched_config = layers_config[cfg_key]
                    break
            if not matched_config:
                continue
            field_lengths = matched_config.get('field_lengths', {})
            if not field_lengths:
                continue
            for feat in features:
                for field, max_len in field_lengths.items():
                    value = feat.properties.get(field)
                    if _is_missing_sentinel(value):
                        continue
                    text = _effective_length_text(field, value)
                    if len(text) > max_len:
                        results.append(CheckResult(
                            check_object=f"{layer_name} 要素 {feat.properties.get('CODE', feat.feature_id)}",
                            passed=False,
                            problem_location=f"字段 {field}",
                            actual_value=f"长度 {len(text)}",
                            expected_value=f"≤ {max_len}",
                            rule_id="R032",
                            error_description=f"字段 '{field}' 的长度 ({len(text)}) 超过最大允许长度 ({max_len})"
                        ))
                        flagged.add((layer_name, feat.feature_id, field.upper()))
    # 2) 官方字段说明（Longueur champ）驱动
    for spec_layer, fields in _field_specs_by_layer(ctx).items():
        for layer_name, features in ctx.layers.items():
            if not _match_spec_layer(spec_layer, layer_name):
                continue
            for f in fields:
                field = f.get("name", "").strip()
                max_len = _parse_spec_length(f.get("length", ""))
                if not field or max_len is None:
                    continue
                spec_type = f.get("type", "").strip()
                # 官方 Longueur 是 DBF 存储列宽（如 N(10,3)），数值字段用 Python float 字符串长度比较必误报，跳过
                if _normalize_type_name(spec_type) in _NUMERIC_TYPE_NAMES:
                    continue
                for feat in features:
                    props = feat.properties
                    value = _case_insensitive_get(props, field)
                    if _is_missing_sentinel(value):
                        continue
                    if (layer_name, feat.feature_id, field.upper()) in flagged:
                        continue
                    text = _effective_length_text(field, value)
                    if len(text) > max_len:
                        results.append(CheckResult(
                            check_object=f"{layer_name} 要素 {props.get('CODE', feat.feature_id)}",
                            passed=False,
                            problem_location=f"字段 {field}",
                            actual_value=f"长度 {len(text)}",
                            expected_value=f"≤ {max_len}",
                            rule_id=RULE_IDS["FIELD_LENGTH_CHECK"],
                            error_description=f"字段 '{field}' 的长度 ({len(text)}) 超过官方字段说明允许的最大长度 ({max_len})"
                        ))
    return results


def check_site_pm_zpm_bidirectional(ctx: RuleContext) -> List[CheckResult]:
    """R005_1: SITE(TYPE=PM) 的 CODE 与 ZPM 的 CODE 双向一一对应检查"""
    results = []

    site_pm_codes = set()
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    code = feat.properties.get('CODE')
                    if code:
                        site_pm_codes.add(code)
            break

    zpm_codes = set()
    for layer_name in ctx.layers:
        if 'ZPM' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                code = feat.properties.get('CODE')
                if code:
                    zpm_codes.add(code)
            break

    if not site_pm_codes and not zpm_codes:
        return results

    for code in sorted(site_pm_codes):
        if code not in zpm_codes:
            results.append(CheckResult(
                check_object=f"SITE PM {code}",
                passed=False,
                problem_location="ZPM 图层",
                actual_value="ZPM 中无对应 CODE",
                expected_value=f"ZPM 中存在 CODE={code}",
                rule_id="R005_1",
                error_description=f"SITE 中 PM {code} 在 ZPM 图层中找不到对应的 CODE"
            ))

    for code in sorted(zpm_codes):
        if code not in site_pm_codes:
            results.append(CheckResult(
                check_object=f"ZPM {code}",
                passed=False,
                problem_location="SITE 图层",
                actual_value="SITE 中无对应 TYPE=PM 的记录",
                expected_value=f"SITE 中存在 TYPE=PM 且 CODE={code}",
                rule_id="R005_1",
                error_description=f"ZPM 图层中 {code} 在 SITE(TYPE=PM) 中找不到对应的记录"
            ))

    return results


def check_site_pm_boite_pbo_bidirectional(ctx: RuleContext) -> List[CheckResult]:
    """R005_2: BOITE(TYPE=PBO).REF_PM ↔ SITE(TYPE=PM).CODE 双向引用检查"""
    results = []

    site_pm_codes = set()
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    code = feat.properties.get('CODE')
                    if code:
                        site_pm_codes.add(code)
            break

    boite_pbo_refs = {}
    for layer_name in ctx.layers:
        if 'BOITE' in layer_name.upper() or 'BOX' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                boite_type = feat.properties.get('TYPE') or feat.properties.get('TYPE_FONC')
                if not boite_type:
                    code = feat.properties.get('CODE') or ''
                    if code.upper().startswith('PBO'):
                        boite_type = 'PBO'
                    elif code.upper().startswith('BPE'):
                        boite_type = 'BPE'
                if boite_type != 'PBO':
                    continue
                ref_pm = feat.properties.get('REF_PM')
                code = feat.properties.get('CODE')
                if ref_pm:
                    boite_pbo_refs[code or feat.feature_id] = ref_pm
            break

    if not site_pm_codes and not boite_pbo_refs:
        return results

    for boite_code, ref_pm in boite_pbo_refs.items():
        if ref_pm not in site_pm_codes:
            results.append(CheckResult(
                check_object=f"BOITE PBO {boite_code}",
                passed=False,
                problem_location="REF_PM 字段",
                actual_value=f"REF_PM={ref_pm}",
                expected_value="SITE(TYPE=PM) 中存在对应的 CODE",
                rule_id="R005_2",
                error_description=f"BOITE PBO {boite_code} 的 REF_PM={ref_pm} 在 SITE(TYPE=PM) 中不存在"
            ))

    ref_pm_set = set(boite_pbo_refs.values())
    for code in sorted(site_pm_codes):
        if code not in ref_pm_set:
            results.append(CheckResult(
                check_object=f"SITE PM {code}",
                passed=False,
                problem_location="BOITE 图层",
                actual_value="无 BOITE(TYPE=PBO) 引用",
                expected_value="至少一个 BOITE(TYPE=PBO) 的 REF_PM 指向此 CODE",
                rule_id="R005_2",
                error_description=f"SITE PM {code} 未被任何 BOITE(TYPE=PBO) 的 REF_PM 引用"
            ))

    return results


def check_site_pm_cable_distribution_bidirectional(ctx: RuleContext) -> List[CheckResult]:
    """R005_3: CABLE(TYPE_CABLE=DISTRIBUTION).REF_PM ↔ SITE(TYPE=PM).CODE 双向引用检查"""
    results = []

    site_pm_codes = set()
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    code = feat.properties.get('CODE')
                    if code:
                        site_pm_codes.add(code)
            break

    cable_refs = {}
    cable_features = _get_cable_features(ctx)
    for feat in cable_features:
        type_cable = feat.properties.get('TYPE_CABLE') if hasattr(feat, 'properties') else None
        if type_cable != 'DISTRIBUTION':
            continue
        ref_pm = feat.properties.get('REF_PM')
        code = feat.properties.get('CODE') if hasattr(feat, 'properties') else None
        if ref_pm:
            cable_refs[code or feat.feature_id] = ref_pm

    if not site_pm_codes and not cable_refs:
        return results

    for cable_code, ref_pm in cable_refs.items():
        if ref_pm not in site_pm_codes:
            results.append(CheckResult(
                check_object=f"CABLE DISTRIBUTION {cable_code}",
                passed=False,
                problem_location="REF_PM 字段",
                actual_value=f"REF_PM={ref_pm}",
                expected_value="SITE(TYPE=PM) 中存在对应的 CODE",
                rule_id="R005_3",
                error_description=f"CABLE DISTRIBUTION {cable_code} 的 REF_PM={ref_pm} 在 SITE(TYPE=PM) 中不存在"
            ))

    ref_pm_set = set(cable_refs.values())
    for code in sorted(site_pm_codes):
        if code not in ref_pm_set:
            results.append(CheckResult(
                check_object=f"SITE PM {code}",
                passed=False,
                problem_location="CABLE 图层",
                actual_value="无 CABLE(TYPE_CABLE=DISTRIBUTION) 引用",
                expected_value="至少一个 CABLE(TYPE_CABLE=DISTRIBUTION) 的 REF_PM 指向此 CODE",
                rule_id="R005_3",
                error_description=f"SITE PM {code} 未被任何 CABLE(TYPE_CABLE=DISTRIBUTION) 的 REF_PM 引用"
            ))

    return results


def check_cable_boite_site_bidirectional(ctx: RuleContext) -> List[CheckResult]:
    """R005_4: CABLE(DISTRIBUTION) 端点与 BOITE(BPE/PBO)/SITE(PM) 双向检查"""
    results = []

    valid_device_codes = set()
    for layer_name in ctx.layers:
        upper = layer_name.upper()
        if 'BOITE' in upper or 'BOX' in upper:
            for feat in ctx.layers[layer_name]:
                boite_type = feat.properties.get('TYPE') or feat.properties.get('TYPE_FONC')
                if not boite_type:
                    code_val = feat.properties.get('CODE') or ''
                    if code_val.upper().startswith('PBO'):
                        boite_type = 'PBO'
                    elif code_val.upper().startswith('BPE'):
                        boite_type = 'BPE'
                if boite_type in ('BPE', 'PBO'):
                    code = feat.properties.get('CODE')
                    if code:
                        valid_device_codes.add(code)
        elif 'SITE' in upper:
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    code = feat.properties.get('CODE')
                    if code:
                        valid_device_codes.add(code)
        elif 'SRO' in upper:
            for feat in ctx.layers[layer_name]:
                code = feat.properties.get('CODE')
                if code:
                    valid_device_codes.add(code)

    site_pm_codes = set()
    boite_bpe_pbo_codes = set()
    sro_codes = set()
    for layer_name in ctx.layers:
        upper = layer_name.upper()
        if 'SITE' in upper:
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    code = feat.properties.get('CODE')
                    if code:
                        site_pm_codes.add(code)
        elif 'BOITE' in upper or 'BOX' in upper:
            for feat in ctx.layers[layer_name]:
                boite_type = feat.properties.get('TYPE') or feat.properties.get('TYPE_FONC')
                if not boite_type:
                    code_val = feat.properties.get('CODE') or ''
                    if code_val.upper().startswith('PBO'):
                        boite_type = 'PBO'
                    elif code_val.upper().startswith('BPE'):
                        boite_type = 'BPE'
                if boite_type in ('BPE', 'PBO'):
                    code = feat.properties.get('CODE')
                    if code:
                        boite_bpe_pbo_codes.add(code)
        elif 'SRO' in upper:
            for feat in ctx.layers[layer_name]:
                code = feat.properties.get('CODE')
                if code:
                    sro_codes.add(code)

    cable_endpoints = set()
    cable_features = _get_cable_features(ctx)
    for feat in cable_features:
        type_cable = (feat.properties.get('TYPE_CABLE') or
                      feat.properties.get('TYPE_FONC') or '')
        if type_cable.upper() != 'DISTRIBUTION':
            continue
        origine = feat.properties.get('ORIGINE')
        extremite = feat.properties.get('EXTREMITE')
        code = feat.properties.get('CODE') if hasattr(feat, 'properties') else str(feat.feature_id)
        if origine:
            cable_endpoints.add(origine)
            if origine not in valid_device_codes:
                results.append(CheckResult(
                    check_object=f"CABLE DISTRIBUTION {code}",
                    passed=False,
                    problem_location="ORIGINE 字段",
                    actual_value=f"ORIGINE={origine}",
                    expected_value="BOITE(BPE/PBO)、SITE(PM) 或 SRO 的 CODE",
                    rule_id="R005_4",
                    error_description=f"CABLE DISTRIBUTION {code} 的 ORIGINE={origine} 在 BOITE(BPE/PBO)、SITE(PM) 和 SRO 中均不存在"
                ))
        if extremite:
            cable_endpoints.add(extremite)
            if extremite not in valid_device_codes:
                results.append(CheckResult(
                    check_object=f"CABLE DISTRIBUTION {code}",
                    passed=False,
                    problem_location="EXTREMITE 字段",
                    actual_value=f"EXTREMITE={extremite}",
                    expected_value="BOITE(BPE/PBO)、SITE(PM) 或 SRO 的 CODE",
                    rule_id="R005_4",
                    error_description=f"CABLE DISTRIBUTION {code} 的 EXTREMITE={extremite} 在 BOITE(BPE/PBO)、SITE(PM) 和 SRO 中均不存在"
                ))

    for code in sorted(site_pm_codes):
        if code not in cable_endpoints:
            results.append(CheckResult(
                check_object=f"SITE PM {code}",
                passed=False,
                problem_location="CABLE 端点",
                actual_value="未被任何 CABLE(DISTRIBUTION) 连接",
                expected_value="至少一条 CABLE(DISTRIBUTION) 的 ORIGINE/EXTREMITE 包含此 CODE",
                rule_id="R005_4",
                error_description=f"SITE PM {code} 未被任何 CABLE(DISTRIBUTION) 的 ORIGINE 或 EXTREMITE 引用"
            ))

    for code in sorted(boite_bpe_pbo_codes):
        if code not in cable_endpoints:
            results.append(CheckResult(
                check_object=f"BOITE {code}",
                passed=False,
                problem_location="CABLE 端点",
                actual_value="未被任何 CABLE(DISTRIBUTION) 连接",
                expected_value="至少一条 CABLE(DISTRIBUTION) 的 ORIGINE/EXTREMITE 包含此 CODE",
                rule_id="R005_4",
                error_description=f"BOITE {code} 未被任何 CABLE(DISTRIBUTION) 的 ORIGINE 或 EXTREMITE 引用"
            ))

    for code in sorted(sro_codes):
        if code not in cable_endpoints:
            results.append(CheckResult(
                check_object=f"SRO {code}",
                passed=False,
                problem_location="CABLE 端点",
                actual_value="未被任何 CABLE(DISTRIBUTION) 连接",
                expected_value="至少一条 CABLE(DISTRIBUTION) 的 ORIGINE/EXTREMITE 包含此 CODE",
                rule_id="R005_4",
                error_description=f"SRO {code} 未被任何 CABLE(DISTRIBUTION) 的 ORIGINE 或 EXTREMITE 引用"
            ))

    return results


def check_site_pm_in_zpm_v2(ctx: RuleContext) -> List[CheckResult]:
    """R006_3: SITE.TYPE=PM 的坐标必须在对应 ZPM 多边形内"""
    results = []
    zpm_index = _build_zpm_index(ctx)
    if not zpm_index:
        return results

    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') != 'PM':
                    continue
                code = feat.properties.get('CODE')
                geom = feat._geometry
                if not code or not geom or not isinstance(geom, Point):
                    continue
                poly = zpm_index.get(code)
                if not poly:
                    continue
                if not poly.contains(geom):
                    results.append(CheckResult(
                        check_object=f"SITE PM {code}",
                        passed=False,
                        problem_location="不在对应ZPM内",
                        actual_value=f"坐标 ({geom.x:.6f}, {geom.y:.6f})",
                        expected_value=f"必须在 ZPM {code} 多边形内",
                        rule_id="R006_3",
                        error_description=f"光交箱 PM {code} 未在对应的 ZPM 范围内"
                    ))
            break
    return results


def check_boite_pbo_in_zpm_v2(ctx: RuleContext) -> List[CheckResult]:
    """R006_4: BOITE.TYPE=PBO 的坐标必须在对应 ZPM 多边形内（通过 REF_PM→SITE.CODE→ZPM.CODE 关联）"""
    results = []
    zpm_index = _build_zpm_index(ctx)
    if not zpm_index:
        return results

    site_to_zpm = {}
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    site_code = feat.properties.get('CODE')
                    if site_code and site_code in zpm_index:
                        site_to_zpm[site_code] = site_code
            break

    for layer_name in ctx.layers:
        if 'BOITE' in layer_name.upper() or 'BOX' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                boite_type = feat.properties.get('TYPE') or feat.properties.get('TYPE_FONC')
                if not boite_type:
                    code_val = feat.properties.get('CODE') or ''
                    if code_val.upper().startswith('PBO'):
                        boite_type = 'PBO'
                    elif code_val.upper().startswith('BPE'):
                        boite_type = 'BPE'
                if boite_type != 'PBO':
                    continue
                ref_pm = feat.properties.get('REF_PM')
                if not ref_pm:
                    continue
                zpm_code = site_to_zpm.get(ref_pm)
                if not zpm_code:
                    continue
                poly = zpm_index.get(zpm_code)
                if not poly:
                    continue
                geom = feat._geometry
                if not geom or not isinstance(geom, Point):
                    continue
                if not poly.contains(geom):
                    results.append(CheckResult(
                        check_object=f"BOITE PBO {feat.properties.get('CODE')}",
                        passed=False,
                        problem_location=f"不在 ZPM {zpm_code} 内",
                        actual_value=f"坐标 ({geom.x:.6f}, {geom.y:.6f})",
                        expected_value=f"必须在 ZPM {zpm_code} 多边形内",
                        rule_id="R006_4",
                        error_description=f"终端盒 PBO {feat.properties.get('CODE')} 未在归属的 ZPM 范围内"
                    ))
            break
    return results


def check_cable_distribution_in_zpm_v2(ctx: RuleContext) -> List[CheckResult]:
    """R006_5: CABLE.TYPE_CABLE=DISTRIBUTION 的所有坐标点必须在对应 ZPM 内"""
    results = []
    zpm_index = _build_zpm_index(ctx)
    if not zpm_index:
        return results

    site_to_zpm = {}
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                if feat.properties.get('TYPE') == 'PM':
                    site_code = feat.properties.get('CODE')
                    if site_code and site_code in zpm_index:
                        site_to_zpm[site_code] = site_code
            break

    for cable in ctx.cables:
        if isinstance(cable, Cable):
            type_cable = getattr(cable, 'type_cable', None)
            ref_pm = getattr(cable, 'ref_pm', None)
            code = cable.code
            geom = cable.geometry
        else:
            type_cable = cable.properties.get('TYPE_CABLE')
            ref_pm = cable.properties.get('REF_PM')
            code = cable.properties.get('CODE')
            geom = _safe_geometry(cable)

        if type_cable != 'DISTRIBUTION':
            continue
        if not ref_pm or not geom or not isinstance(geom, LineString):
            continue
        zpm_code = site_to_zpm.get(ref_pm)
        if not zpm_code:
            continue
        poly = zpm_index.get(zpm_code)
        if not poly:
            continue

        outside_pts = []
        for pt in geom.coords:
            point = Point(pt)
            if not poly.contains(point):
                outside_pts.append(pt)
        if outside_pts:
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location=f"部分点不在 ZPM {zpm_code} 内",
                actual_value=f"出界点数量: {len(outside_pts)}",
                expected_value="所有节点均位于ZPM内",
                rule_id="R006_5",
                error_description=f"DISTRIBUTION光缆 {code} 的几何存在位于 ZPM {zpm_code} 外的点"
            ))
    return results


def check_cable_endpoint_on_boite(ctx: RuleContext, tolerance: float = 0.5) -> List[CheckResult]:
    """R006_6: CABLE 端点必须与 BOITE 坐标重合，兼容反向绘制"""
    results = []

    boite_geom = {}
    for layer_name in ctx.layers:
        if 'BOITE' in layer_name.upper() or 'BOX' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                code = feat.properties.get('CODE')
                geom = feat._geometry
                if code and geom and isinstance(geom, Point):
                    boite_geom[code] = geom
            break

    if not boite_geom:
        return results

    cable_features = _get_cable_features(ctx)
    for feat in cable_features:
        code = feat.properties.get('CODE') if hasattr(feat, 'properties') else str(feat.feature_id)
        origine = feat.properties.get('ORIGINE')
        extremite = feat.properties.get('EXTREMITE')
        geom = feat._geometry

        if geom is None or not isinstance(geom, LineString):
            continue

        if origine and extremite and origine == extremite:
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location="ORIGINE == EXTREMITE",
                actual_value=f"ORIGINE={origine}, EXTREMITE={extremite}",
                expected_value="ORIGINE ≠ EXTREMITE",
                rule_id="R006_6",
                error_description=f"光缆 {code} 起点和终点设备相同 ({origine})"
            ))
            continue

        if not origine or not extremite:
            continue

        pt_o = boite_geom.get(origine)
        pt_e = boite_geom.get(extremite)
        if not pt_o or not pt_e:
            continue

        start_pt = Point(geom.coords[0])
        end_pt = Point(geom.coords[-1])

        d_o_s = point_geodesic_distance(pt_o, start_pt)
        d_o_e = point_geodesic_distance(pt_o, end_pt)
        d_e_s = point_geodesic_distance(pt_e, start_pt)
        d_e_e = point_geodesic_distance(pt_e, end_pt)

        match_normal = (d_o_s <= tolerance and d_e_e <= tolerance)
        match_reverse = (d_o_e <= tolerance and d_e_s <= tolerance)

        if not (match_normal or match_reverse):
            results.append(CheckResult(
                check_object=f"光缆 {code}",
                passed=False,
                problem_location="端点与 BOITE 坐标不重合",
                actual_value=f"O→起点{d_o_s:.1f}m 终点{d_o_e:.1f}m; E→起点{d_e_s:.1f}m 终点{d_e_e:.1f}m",
                expected_value=f"ORIGINE/EXTREMITE 对应 BOITE 坐标与光缆首末端一一重合 (≤{tolerance}m)",
                rule_id="R006_6",
                error_description=f"光缆 {code} 的端点与对应 BOITE 坐标偏差超过 {tolerance}m"
            ))

    return results


def check_pbo_nb_fibre_util_exceeds_capacite(ctx: RuleContext) -> List[CheckResult]:
    """R007_1: BOITE 中 TYPE=PBO 的元素，NB_FIBRE_UTIL ≤ CAPACITE（数字部分）"""
    results = []

    for layer_name in ctx.layers:
        if 'BOITE' not in layer_name.upper() and 'BOX' not in layer_name.upper():
            continue
        for feat in ctx.layers[layer_name]:
            code = feat.properties.get('CODE')
            type_val = feat.properties.get('TYPE') or feat.properties.get('TYPE_FONC')
            if not type_val:
                if code and code.startswith('PBO'):
                    type_val = 'PBO'

            if not type_val or type_val.upper() != 'PBO':
                continue

            nb_fibre_util_raw = feat.properties.get('NB_FIBRE_UTIL') or feat.properties.get('NB_FIBRE_U')
            capacite_raw = feat.properties.get('CAPACITE')

            try:
                nb_fibre_util = int(re.sub(r'\D', '', str(nb_fibre_util_raw))) if nb_fibre_util_raw is not None else None
                capacite = int(re.sub(r'\D', '', str(capacite_raw))) if capacite_raw is not None else None
            except (ValueError, TypeError):
                nb_fibre_util, capacite = None, None

            if nb_fibre_util is None or capacite is None:
                continue

            passed = nb_fibre_util <= capacite
            results.append(CheckResult(
                check_object=f"PBO 箱体 {code or feat.feature_id}",
                passed=passed,
                problem_location="NB_FIBRE_UTIL vs CAPACITE",
                actual_value=f"NB_FIBRE_UTIL={nb_fibre_util}, CAPACITE={capacite}",
                expected_value=f"NB_FIBRE_UTIL ≤ CAPACITE",
                rule_id="R007_1",
                error_description=(
                    f"PBO {code}: NB_FIBRE_UTIL({nb_fibre_util}) > CAPACITE({capacite})"
                    if not passed else ""
                )
            ))
        break

    return results


def check_pm_pbo_port_exceeds_cable_capacity(ctx: RuleContext) -> List[CheckResult]:
    """R007_2: 每个 PM 下所有 PBO 的 CAPACITE 之和 ≤ 以该 PM 为 ORIGINE 的 DISTRIBUTION 光缆 CAPACITE 之和"""
    results = []

    def _extract_int(val):
        """提取整数值"""
        try:
            return int(re.sub(r'\D', '', str(val)))
        except (ValueError, TypeError):
            return None

    def _get_type(feat):
        """获取类型，兼容 GPKG 的 TYPE_FONC 和 CODE 前缀"""
        t = feat.properties.get('TYPE') or feat.properties.get('TYPE_FONC')
        if t:
            return t.upper()
        code = feat.properties.get('CODE', '')
        for prefix in ('PBO', 'BPE', 'BPI'):
            if code.startswith(prefix):
                return prefix
        return None

    pm_sites: Dict[str, Any] = {}
    for layer_name in ctx.layers:
        if 'SITE' in layer_name.upper():
            for feat in ctx.layers[layer_name]:
                t = feat.properties.get('TYPE', '').upper()
                code = feat.properties.get('CODE')
                if t == 'PM' and code:
                    pm_sites[code] = code
            break

    if not pm_sites:
        return results

    pm_pbo_capacities: Dict[str, int] = {code: 0 for code in pm_sites}
    for layer_name in ctx.layers:
        if 'BOITE' not in layer_name.upper() and 'BOX' not in layer_name.upper():
            continue
        for feat in ctx.layers[layer_name]:
            if _get_type(feat) != 'PBO':
                continue
            ref_pm = feat.properties.get('REF_PM')
            if not ref_pm or ref_pm not in pm_pbo_capacities:
                continue
            cap = _extract_int(feat.properties.get('CAPACITE'))
            if cap is not None:
                pm_pbo_capacities[ref_pm] += cap
        break

    pm_cable_capacities: Dict[str, int] = {code: 0 for code in pm_sites}
    for layer_name in ctx.layers:
        if 'CABLE' not in layer_name.upper():
            continue
        for feat in ctx.layers[layer_name]:
            type_cable = (feat.properties.get('TYPE_CABLE') or '').upper()
            if type_cable != 'DISTRIBUTION':
                continue
            origine = feat.properties.get('ORIGINE')
            if not origine or origine not in pm_cable_capacities:
                continue
            cap = _extract_int(feat.properties.get('CAPACITE'))
            if cap is not None:
                pm_cable_capacities[origine] += cap
        break

    for pm_code in pm_sites:
        pbo_sum = pm_pbo_capacities.get(pm_code, 0)
        cable_sum = pm_cable_capacities.get(pm_code, 0)

        if pbo_sum == 0:
            continue

        passed = pbo_sum <= cable_sum
        results.append(CheckResult(
            check_object=f"PM 站点 {pm_code}",
            passed=passed,
            problem_location="PBO 端口之和 vs DISTRIBUTION 光缆芯数",
            actual_value=f"PBO CAPACITE 之和={pbo_sum}, CABLE(DISTRIBUTION) CAPACITE 之和={cable_sum}",
            expected_value=f"PBO 端口之和 ≤ 上游光缆芯数之和",
            rule_id="R007_2",
            error_description=(
                f"PM {pm_code}: PBO 端口之和({pbo_sum}) > 上游 DISTRIBUTION 光缆芯数之和({cable_sum})"
                if not passed else ""
            )
        ))

    return results


ALL_RULES = {
    "R001": check_file_missing,
    "R002": check_layer_missing,
    "R003": check_layer_name,
    "R004": check_layer_geom_type,
    "R005": check_required_fields,
    "R006": check_field_type_invalid,
    "R007": check_code_duplicate,
    "R008": check_reference_exists,
    "R009": check_isolated_objects,
    "R010": check_cable_endpoint_on_device,
    "R011": check_capacity_exceeded,
    "R012": check_fiber_duplicate,
    "R-FIBER-001": check_fiber_core_duplicate,
    "R013": check_device_in_coverage,
    "R014": check_cable_crossing_rule,
    "R015": check_distance_between,
    "R016": check_layer_empty,
    "R017": check_crs_consistency,
    "R018": check_field_types,
    "R019": check_capacity_match,
    "R020": check_pbo_capacity,
    "R021": check_required_fields_exist,
    "R022": check_pbo_coverage,
    "R023": check_cable_breakpoints,
    "R024": check_cable_device_endpoint_match,
    "R025": check_znro_overlap,
    "R026": check_zpm_overlap,
    "R027": check_site_pm_in_zpm,
    "R028": check_boite_pbo_in_zpm,
    "R029": check_cable_distribution_in_zpm,
    "R030": check_pm_pbo_port_capacity,
    "R031": check_field_domain,
    "R032": check_field_length,
    "R033": check_official_layers_empty,
    "R005_1": check_site_pm_zpm_bidirectional,
    "R005_2": check_site_pm_boite_pbo_bidirectional,
    "R005_3": check_site_pm_cable_distribution_bidirectional,
    "R005_4": check_cable_boite_site_bidirectional,
    "R006_3": check_site_pm_in_zpm_v2,
    "R006_4": check_boite_pbo_in_zpm_v2,
    "R006_5": check_cable_distribution_in_zpm_v2,
    "R006_6": check_cable_endpoint_on_boite,
    "R007_1": check_pbo_nb_fibre_util_exceeds_capacite,
    "R007_2": check_pm_pbo_port_exceeds_cable_capacity,
}
