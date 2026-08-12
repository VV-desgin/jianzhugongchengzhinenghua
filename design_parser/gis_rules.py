"""GIS 空间检查框架：实现官方审查规则库 R-GIS-001 ~ R-GIS-006。

- R-GIS-001 范围多边形防重叠（ZNRO/ZPM 同层内两两不相交面积；允许共边/相切）
- R-GIS-002 光交箱范围包含（SITE TYPE=PM 点在归属 ZPM 内）
- R-GIS-003 终端盒范围包含（BOITE TYPE=PBO 点在归属 ZPM 内）
- R-GIS-004 光缆范围包含（CABLE DISTRIBUTION 全部端点和折点在归属 ZPM 内）
- R-GIS-005 光缆自环（ORIGINE != EXTREMITE）
- R-GIS-006 光缆与设备端点空间重合（端点距设备点 <= tolerance，默认 0.5 米）

所有检查输出统一 issue 结构：
{rule_id, object_type, object_id, field, severity, message, source}
"""
from typing import Dict, List, Any, Optional

from shapely.geometry import Point

from .spatial_utils import point_distance_m

DEFAULT_TOLERANCE_M = 0.5
SEVERITY = {
    "R-GIS-001": "中",
    "R-GIS-002": "高",
    "R-GIS-003": "高",
    "R-GIS-004": "高",
    "R-GIS-005": "中",
    "R-GIS-006": "致命",
}
SOURCE = "gis_rules"


def _issue(rule_id: str, obj_type: str, obj_id: str, message: str) -> Dict[str, Any]:
    return {
        "rule_id": rule_id,
        "object_type": obj_type,
        "object_id": obj_id,
        "field": "",
        "severity": SEVERITY.get(rule_id, "中"),
        "message": message,
        "source": SOURCE,
    }


def _layer(proj, prefix: str):
    key = proj._find_engineering_layer(prefix)
    return key, (proj.layers.get(key, []) if key else [])


def _prop(feat, *names):
    props = feat.properties or {}
    for n in names:
        v = props.get(n)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return None


def check_zone_overlap(proj) -> List[Dict[str, Any]]:
    """R-GIS-001：同图层多边形不得有重叠区域（可共边/相切）。"""
    issues = []
    for layer_name in ("ZNRO", "ZPM"):
        _, feats = _layer(proj, layer_name)
        for i in range(len(feats)):
            for j in range(i + 1, len(feats)):
                a, b = feats[i]._geometry, feats[j]._geometry
                if a is None or b is None:
                    continue
                try:
                    inter = a.intersection(b)
                    if inter.area > 1e-9:
                        ca = _prop(feats[i], "CODE") or f"#{i}"
                        cb = _prop(feats[j], "CODE") or f"#{j}"
                        issues.append(_issue(
                            "R-GIS-001", f"图层 {layer_name}",
                            f"{ca} / {cb}",
                            f"范围 {layer_name} 的 {ca} 与 {cb} 存在重叠区域"))
                except Exception:
                    continue
    return issues


def _zpm_index(proj):
    _, zpm_feats = _layer(proj, "ZPM")
    return {(_prop(f, "CODE") or ""): f for f in zpm_feats}


def _point_in_zpm(point: Point, zpm_feat) -> bool:
    poly = zpm_feat._geometry
    if poly is None or point is None:
        return False
    return point.within(poly) or poly.contains(point)


def check_range_containment(proj) -> List[Dict[str, Any]]:
    """R-GIS-002/003/004：SITE(PM)/BOITE(PBO)/CABLE(DISTRIBUTION) 必须位于归属 ZPM 内。"""
    issues = []
    zpm_index = _zpm_index(proj)

    def contained(obj_type, prefix, type_field, type_value, ref_field):
        _, feats = _layer(proj, prefix)
        for f in feats:
            if type_field and _prop(f, type_field) != type_value:
                continue
            code = _prop(f, "CODE") or ""
            ref = _prop(f, ref_field) or code
            zpm = zpm_index.get(ref)
            if zpm is None:
                continue  # 归属缺失由孤立性/关联规则处理，本规则只做空间包含
            geom = f._geometry
            if geom is None:
                continue
            pts = []
            if geom.geom_type == "Point":
                pts = [geom]
            elif geom.geom_type == "LineString":
                pts = [Point(c) for c in geom.coords]
            if not pts:
                continue
            outside = [p for p in pts if not _point_in_zpm(p, zpm)]
            if outside:
                issues.append(_issue(
                    "R-GIS-002" if obj_type == "SITE" else ("R-GIS-003" if obj_type == "BOITE" else "R-GIS-004"),
                    obj_type, code,
                    f"{obj_type} {code} 存在点位（{len(outside)} 个）超出归属 ZPM {ref} 范围"))

    contained("SITE", "SITE", "TYPE", "PM", "REF_PM")
    contained("BOITE", "BOITE", "TYPE", "PBO", "REF_PM")
    contained("CABLE", "CABLE", "TYPE_CABLE", "DISTRIBUTION", "REF_PM")
    return issues


def check_cable_self_loop(proj) -> List[Dict[str, Any]]:
    """R-GIS-005：光缆 ORIGINE 与 EXTREMITE 不得相同。"""
    issues = []
    _, feats = _layer(proj, "CABLE")
    for f in feats:
        o = _prop(f, "ORIGINE", "START_CODE")
        e = _prop(f, "EXTREMITE", "END_CODE")
        if o and e and o == e:
            issues.append(_issue("R-GIS-005", "CABLE", o,
                                 f"光缆 {_prop(f, 'CODE') or o} 首尾连接同一设备 {o}（自环）"))
    return issues


def check_endpoint_on_device(proj, tolerance_m: float = DEFAULT_TOLERANCE_M) -> List[Dict[str, Any]]:
    """R-GIS-006：光缆端点必须与引用设备的点坐标重合（容差 tolerance_m 米）。"""
    issues = []
    _, cables = _layer(proj, "CABLE")
    # 设备点索引：code -> (layer, feature)
    device_index = {}
    for layer_name in ("BOITE", "PTECH", "SITE", "IMB", "INFRASTRUCTURE", "ZNRO", "ZPM"):
        _, feats = _layer(proj, layer_name)
        for f in feats:
            code = _prop(f, "CODE")
            if code:
                device_index.setdefault(code, (layer_name, f))

    def endpoint_dist(feat, first: bool):
        geom = feat._geometry
        if geom is None or geom.geom_type != "LineString":
            return None
        coords = list(geom.coords)
        return Point(coords[0] if first else coords[-1])

    for cable in cables:
        code = _prop(cable, "CODE") or ""
        for side, ref_field in (("起点", ("ORIGINE", "START_CODE")), ("终点", ("EXTREMITE", "END_CODE"))):
            ref = _prop(cable, *ref_field)
            if not ref:
                continue
            dev = device_index.get(ref)
            if dev is None:
                continue  # 引用不存在由 R-REL-004 处理
            dev_layer, dev_feat = dev
            pt = endpoint_dist(cable, side == "起点")
            dpt = dev_feat._geometry
            if pt is None or dpt is None:
                continue
            if dpt.geom_type == "Point":
                d = point_distance_m(pt, dpt, cable.original_crs or dev_feat.original_crs)
            else:
                d = point_distance_m(pt, dpt.representative_point()
                                     if hasattr(dpt, "representative_point") else dpt,
                                     cable.original_crs or dev_feat.original_crs)
            if d > tolerance_m:
                issues.append(_issue(
                    "R-GIS-006", "CABLE", code,
                    f"光缆 {code} {side}设备 {ref}（{dev_layer}）空间距离 {d:.3f}m 超过容差 {tolerance_m}m"))
    return issues


def run_gis_checks(proj, tolerance_m: float = DEFAULT_TOLERANCE_M) -> Dict[str, Any]:
    """运行全部 GIS 空间检查，返回 issues 与按规则统计。"""
    issues = []
    issues += check_zone_overlap(proj)
    issues += check_range_containment(proj)
    issues += check_cable_self_loop(proj)
    issues += check_endpoint_on_device(proj, tolerance_m=tolerance_m)
    counts: Dict[str, int] = {}
    for i in issues:
        counts[i["rule_id"]] = counts.get(i["rule_id"], 0) + 1
    return {
        "tolerance_m": tolerance_m,
        "total": len(issues),
        "counts": counts,
        "issues": issues,
    }
