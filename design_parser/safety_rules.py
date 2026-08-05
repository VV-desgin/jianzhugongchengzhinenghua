"""安全距离检查（基于数据方提供的施工安全材料，2026-08-05）。

规则编号（本模块自定，来源=施工图安全注意事项）：
- R-SAFE-001 墙壁光缆最低离地高度 >= 4.5m（架空方式跨路时 >= 7m，见 R-SAFE-002）
- R-SAFE-002 架空光缆跨越公路最低离地高度 >= 7m
- R-SAFE-003 光缆与电力线交越垂直净距（10KV 以下：有防雷保护 2m/无 4m；35KV~110KV：3m/5m）
- R-SAFE-004~009 墙壁光缆与其他管线最小间距（平行/交叉，按配置的净距表）

说明：
- 高度类检查（001/002/003）依赖三维坐标（Z 值）；二维数据无法判定时跳过并记入 skipped。
- 平行净距用二维最小距离（米）判定；交叉净距需要 Z 值（在交点插值求垂直间距），无 Z 时跳过。
- 缺失哨兵值（NA/N/A 等）不判违规。
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional

from shapely.geometry import Point

from .spatial_utils import point_distance_m

SOURCE = "safety_distances"
SEVERITY = {
    "R-SAFE-001": "高",
    "R-SAFE-002": "高",
    "R-SAFE-003": "致命",
    "R-SAFE-004": "高",
    "R-SAFE-005": "高",
    "R-SAFE-006": "高",
    "R-SAFE-007": "高",
    "R-SAFE-008": "高",
    "R-SAFE-009": "高",
}
MISSING_SENTINELS = ("", "NA", "N/A", "NULL", "NONE", "SANS OBJET", "-")


def _load_config(path: Optional[Path] = None) -> dict:
    if path is None:
        path = Path(__file__).parent / "mappings" / "safety_distances.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _issue(rule_id: str, obj_type: str, obj_id: str, message: str) -> Dict[str, Any]:
    return {
        "rule_id": rule_id,
        "object_type": obj_type,
        "object_id": obj_id,
        "field": "",
        "severity": SEVERITY.get(rule_id, "高"),
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
        if v is None:
            continue
        s = str(v).strip()
        if s and s.upper() not in MISSING_SENTINELS:
            return s
    return None


def _has_z(geom) -> bool:
    try:
        coords = list(geom.coords)
        return bool(coords) and len(coords[0]) >= 3
    except Exception:
        return False


def _min_z(geom) -> Optional[float]:
    if not _has_z(geom):
        return None
    try:
        return min(c[2] for c in geom.coords if len(c) >= 3)
    except Exception:
        return None


def _z_at_xy(geom, x: float, y: float) -> Optional[float]:
    """在线段上按 XY 线性插值 Z（简化：找最近顶点对插值）。"""
    try:
        coords = [c for c in geom.coords if len(c) >= 3]
    except Exception:
        return None
    if not coords:
        return None
    best = None
    best_d = float("inf")
    for c in coords:
        d = (c[0] - x) ** 2 + (c[1] - y) ** 2
        if d < best_d:
            best_d = d
            best = c
    return best[2] if best is not None else None


def _min_line_distance_m(line1, line2, crs: Optional[str]) -> Optional[float]:
    """采样折点求两条线的最小距离（米）。"""
    try:
        c1 = list(line1.coords)
        c2 = list(line2.coords)
    except Exception:
        return None
    if not c1 or not c2:
        return None
    best = float("inf")
    for a in c1:
        pa = Point(a[0], a[1])
        for b in c2:
            pb = Point(b[0], b[1])
            d = point_distance_m(pa, pb, crs)
            if d < best:
                best = d
    return best


def check_ground_height(proj, cfg: dict) -> tuple:
    """R-SAFE-001/002：光缆最低离地高度（4.5m 墙壁 / 7m 架空跨路）。"""
    issues, skipped = [], []
    _, cables = _layer(proj, "CABLE")
    for f in cables:
        code = _prop(f, "CODE") or ""
        geom = f._geometry
        if geom is None:
            continue
        if not _has_z(geom):
            skipped.append(f"光缆 {code}：二维数据无 Z，无法检查离地高度")
            continue
        mode = (_prop(f, "MODE_POSE", "MODE_POSE") or "").upper()
        threshold = cfg["aerial_cable"]["road_crossing_min_ground_height_m"] if (
            "AERIEN" in mode or "架空" in mode) else cfg["wall_cable"]["min_ground_height_m"]
        rule = "R-SAFE-002" if threshold >= 7 else "R-SAFE-001"
        z = _min_z(geom)
        if z is not None and z < threshold:
            issues.append(_issue(rule, "CABLE", code,
                                 f"光缆 {code} 最低离地高度 {z:.2f}m 低于要求 {threshold}m"))
    return issues, skipped


def check_power_crossing(proj, cfg: dict) -> tuple:
    """R-SAFE-003：光缆与电力线交越垂直净距（按电压等级与防雷保护）。"""
    issues, skipped = [], []
    _, cables = _layer(proj, "CABLE")
    power_keywords = cfg["utility_layer_keywords"]["电力线"]
    power_feats = []
    for key, feats in proj.layers.items():
        upper = key.upper()
        if any(k.upper() in upper for k in power_keywords):
            power_feats.extend(feats)
    if not power_feats:
        return issues, skipped
    table = cfg["power_line_crossing_vertical_m"]
    for cable in cables:
        g1 = cable._geometry
        if g1 is None or not _has_z(g1):
            continue
        for pfeat in power_feats:
            g2 = pfeat._geometry
            if g2 is None:
                continue
            try:
                inter = g1.intersection(g2)
            except Exception:
                continue
            if inter.is_empty or inter.geom_type not in ("Point", "MultiPoint"):
                continue  # 非交越（平行/分离）由平行净距规则处理
            pts = list(inter.geoms) if inter.geom_type == "MultiPoint" else [inter]
            for pt in pts:
                z1 = _z_at_xy(g1, pt.x, pt.y)
                z2 = _z_at_xy(g2, pt.x, pt.y)
                if z1 is None or z2 is None:
                    continue
                gap = abs(z1 - z2)
                v = (_prop(pfeat, "VOLTAGE", "TENSION") or "").upper()
                kv = "35kv_110kv" if any(k in v for k in ("35", "110")) else "10kv_below"
                prot = (_prop(pfeat, "LIGHTNING_PROTECTION", "PROTECTION") or "").upper()
                with_prot = any(k in prot for k in ("OUI", "YES", "TRUE", "1", "有"))
                threshold = table[kv]["with_lightning_protection" if with_prot else "without_lightning_protection"]
                if gap < threshold:
                    issues.append(_issue(
                        "R-SAFE-003", "CABLE", _prop(cable, "CODE") or "",
                        f"光缆 {_prop(cable, 'CODE') or ''} 与电力线 {_prop(pfeat, 'CODE') or ''} 交越垂直净距 "
                        f"{gap:.2f}m 低于要求 {threshold}m（{kv}，{'有' if with_prot else '无'}防雷保护）"))
    return issues, skipped


def check_utility_clearances(proj, cfg: dict) -> tuple:
    """R-SAFE-004~009：墙壁光缆与其他管线平行/交叉净距。"""
    issues, skipped = [], []
    _, cables = _layer(proj, "CABLE")
    if not cables:
        return issues, skipped
    clearances = cfg["wall_cable_clearances_mm"]
    keywords = cfg["utility_layer_keywords"]
    rule_ids = {
        "电力线": "R-SAFE-004",
        "给水管": "R-SAFE-005",
        "压缩空气管": "R-SAFE-006",
        "热力管": "R-SAFE-007",
        "避雷线接地引线": "R-SAFE-008",
        "工作保护地线": "R-SAFE-009",
    }
    for util_type, spec in clearances.items():
        kws = keywords.get(util_type, [util_type])
        feats = []
        for key, fs in proj.layers.items():
            upper = key.upper()
            if any(k.upper() in upper for k in kws):
                feats.extend(fs)
        if not feats:
            continue
        rule = rule_ids[util_type]
        parallel_m = spec["parallel_mm"] / 1000.0
        crossing_m = spec["crossing_mm"] / 1000.0
        for cable in cables:
            g1 = cable._geometry
            if g1 is None:
                continue
            for ufeat in feats:
                g2 = ufeat._geometry
                if g2 is None:
                    continue
                try:
                    inter = g1.intersection(g2)
                    crossing = not inter.is_empty and inter.geom_type in ("Point", "MultiPoint")
                except Exception:
                    crossing = False
                if crossing:
                    if _has_z(g1) and _has_z(g2):
                        gap = None
                        pts = list(inter.geoms) if inter.geom_type == "MultiPoint" else [inter]
                        for pt in pts:
                            z1, z2 = _z_at_xy(g1, pt.x, pt.y), _z_at_xy(g2, pt.x, pt.y)
                            if z1 is not None and z2 is not None:
                                gap = abs(z1 - z2)
                                break
                        if gap is not None and gap < crossing_m:
                            issues.append(_issue(rule, "CABLE", _prop(cable, "CODE") or "",
                                                 f"光缆与{util_type}交叉垂直净距 {gap:.3f}m 低于要求 {crossing_m}m"))
                    else:
                        skipped.append(f"{util_type}交叉检查需 Z 值，已跳过")
                    continue
                d = _min_line_distance_m(g1, g2, cable.original_crs)
                if d is not None and d < parallel_m:
                    issues.append(_issue(rule, "CABLE", _prop(cable, "CODE") or "",
                                         f"光缆与{util_type}平行净距 {d:.3f}m 低于要求 {parallel_m}m"))
    return issues, skipped


def run_safety_checks(proj, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """运行全部安全距离检查。"""
    cfg = _load_config(config_path)
    issues, skipped = [], []
    for fn in (check_ground_height, check_power_crossing, check_utility_clearances):
        iss, skp = fn(proj, cfg)
        issues.extend(iss)
        skipped.extend(skp)
    counts: Dict[str, int] = {}
    for i in issues:
        counts[i["rule_id"]] = counts.get(i["rule_id"], 0) + 1
    return {
        "source": cfg["source"],
        "total": len(issues),
        "counts": counts,
        "issues": issues,
        "skipped": skipped[:20],
        "skipped_count": len(skipped),
    }
