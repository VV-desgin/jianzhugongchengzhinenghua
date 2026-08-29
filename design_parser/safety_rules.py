"""安全距离检查（基于施工安全材料）。

规则编号（本模块自定，来源=施工图安全注意事项）：
- R-SAFE-001 墙壁光缆最低离地高度 >= 3m（GB 51158-2015 6.4.14 标准值）
- R-SAFE-002 架空光缆跨越公路最低离地高度 >= 5.5m（YD/T 5102-2024 表11）
- R-SAFE-003 光缆与电力线交越垂直净距（10KV 以下：有防雷保护 2m/无 4m；35KV~110KV：3m/5m）
- R-SAFE-004~009 墙壁光缆与其他管线最小间距（平行/交叉，按配置的净距表）
- R-SAFE-010 直埋光缆与其他地下设施最小净距（YD/T 5102-2024 表7）
- R-SAFE-011 杆路与其他设施最小水平净距（YD/T 5102-2024 表10）
- R-SAFE-012 架空吊线防雷接地间距（GB 51158-2015 6.4.10）

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
    """R-SAFE-001/002：光缆最低离地高度（3m 墙壁 / 7m 架空跨路）。"""
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
        is_aerial = "AERIEN" in mode or "架空" in mode
        threshold = cfg["aerial_cable"]["road_crossing_min_ground_height_m"] if is_aerial else cfg["wall_cable"]["min_ground_height_m"]
        rule = "R-SAFE-002" if is_aerial else "R-SAFE-001"
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
                # 电压档位匹配：从高到低取最大命中档（YD/T 5102-2024 表12）
                kv = "10kv_below"
                if "1000" in v:
                    kv = "750kv_1000kv"
                elif "750" in v:
                    kv = "500kv_750kv"
                elif "500" in v:
                    kv = "330kv_500kv"
                elif "330" in v:
                    kv = "220kv_330kv"
                elif "220" in v:
                    kv = "110kv_220kv"
                elif "110" in v:
                    kv = "35kv_110kv"
                elif "35" in v:
                    kv = "35kv_110kv"
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
    # 压缩空气管：GB 51158-2015 表7.6.3 无该档位（R-SAFE-006 不适用），遇到图层时显式记跳过
    has_air_layer = any(
        any(k.upper() in key.upper() for k in keywords.get("压缩空气管", ["压缩空气"]))
        for key in proj.layers
    )
    if has_air_layer and "压缩空气管" not in clearances:
        skipped.append("压缩空气管：GB 51158-2015 表7.6.3 无该档位（R-SAFE-006 不适用），跳过")
    for util_type, spec in clearances.items():
        kws = keywords.get(util_type, [util_type])
        feats = []
        for key, fs in proj.layers.items():
            upper = key.upper()
            if any(k.upper() in upper for k in kws):
                feats.extend(fs)
        if not feats:
            continue
        if not isinstance(spec, dict) or "parallel_mm" not in spec or "crossing_mm" not in spec:
            continue
        rule = rule_ids.get(util_type)
        if rule is None:
            skipped.append(f"{util_type}：配置存在但无对应规则映射，跳过（待核对归属）")
            continue
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



def _find_layer_by_keywords(proj, keywords):
    """按关键词匹配图层并返回要素列表。"""
    feats = []
    for key, fs in proj.layers.items():
        upper = key.upper()
        if any(k.upper() in upper for k in keywords):
            feats.extend(fs)
    return feats


def check_direct_buried_clearance(proj, cfg: dict) -> tuple:
    """R-SAFE-010：直埋光缆与其他地下设施最小净距（YD/T 5102-2024 表7）。"""
    issues, skipped = [], []
    _, cables = _layer(proj, "CABLE")
    table = cfg.get("direct_buried_clearances_m") or {}
    buried_cables = []
    for cable in cables:
        mode = (_prop(cable, "MODE_POSE", "MODE_POSE") or "").upper()
        if any(k in mode for k in ("SOUTERRAIN", "直埋", "BURIED", "UNDERGROUND")):
            buried_cables.append(cable)
    if not buried_cables:
        skipped.append("直埋净距检查：无直埋/地下敷设光缆（MODE_POSE 含 SOUTERRAIN/直埋）")
        return issues, skipped
    # 地下设施关键词（扩展 utility_layer_keywords）
    kw = cfg.get("utility_layer_keywords", {})
    facility_map = {
        "duct_pipe": kw.get("通信管道", ["通信管道", "DUCT"]),
        "power_cable": kw.get("电力线", ["电力", "POWER", "ELEC"]),
        "water_pipe": kw.get("给水管", ["给水", "WATER", "EAU"]),
        "gas_pipe": kw.get("燃气管", ["燃气", "GAS", "GAZ"]),
        "heat_drain": kw.get("热力管", ["热力", "HEAT", "CHALEUR"]) + kw.get("排水管", ["排水", "DRAIN"]),
    }
    found_any = False
    for cable in buried_cables:
        g1 = cable._geometry
        if g1 is None:
            continue
        code = _prop(cable, "CODE") or ""
        for key, specs in table.items():
            if key in ("note",) or not isinstance(specs, dict):
                continue
            # 前缀匹配：water_pipe_lt300 → water_pipe
            prefix = key.split("_")[0] + "_" + key.split("_")[1] if "_" in key else key
            kws = facility_map.get(prefix)
            if not kws:
                # 兼容直接 key（如 duct_pipe）
                kws = facility_map.get(key)
            if not kws:
                continue
            feats = _find_layer_by_keywords(proj, kws)
            if not feats:
                continue
            found_any = True
            parallel_m = specs.get("parallel")
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
                    continue  # 交叉场景数据缺失 Z 值时无法判定，跳过（平行规则为主）
                if parallel_m is None:
                    continue
                d = _min_line_distance_m(g1, g2, cable.original_crs)
                if d is not None and d < parallel_m:
                    issues.append(_issue("R-SAFE-010", "CABLE", code,
                                         f"直埋光缆 {code} 与 {key} 平行净距 {d:.3f}m 低于要求 {parallel_m}m"))
    if not found_any:
        skipped.append("直埋净距检查：工程数据无地下设施图层（给水管/燃气管/电力电缆等）")
    return issues, skipped


def check_pole_horizontal_clearance(proj, cfg: dict) -> tuple:
    """R-SAFE-011：杆路与其他设施最小水平净距（YD/T 5102-2024 表10）。"""
    issues, skipped = [], []
    _, poles = _layer(proj, "PTECH")
    if not poles:
        skipped.append("杆路净距检查：无 PTECH（电杆）图层")
        return issues, skipped
    table = cfg.get("pole_horizontal_clearances_m") or {}
    kw = cfg.get("utility_layer_keywords", {})
    facility_map = {
        "tree_city": kw.get("树木", ["树木", "TREE", "ARBRE"]),
        "building": kw.get("建筑", ["建筑", "BUILDING", "BATIMENT"]),
        "fire_hydrant": kw.get("消火栓", ["消火栓", "HYDRANT"]),
    }
    found_any = False
    for pole in poles:
        g1 = pole._geometry
        if g1 is None:
            continue
        code = _prop(pole, "CODE") or ""
        for key, limit in table.items():
            if key in ("note",) or isinstance(limit, list) or isinstance(limit, str):
                continue
            kws = facility_map.get(key)
            if not kws:
                continue
            feats = _find_layer_by_keywords(proj, kws)
            if not feats:
                continue
            found_any = True
            for ufeat in feats:
                g2 = ufeat._geometry
                if g2 is None:
                    continue
                d = _min_line_distance_m(g1, g2, pole.original_crs)
                if d is not None and d < limit:
                    issues.append(_issue("R-SAFE-011", "PTECH", code,
                                         f"电杆 {code} 与 {key} 水平净距 {d:.3f}m 低于要求 {limit}m"))
    if not found_any:
        skipped.append("杆路净距检查：工程数据无树木/建筑/消火栓等设施图层")
    return issues, skipped


def check_lightning_grounding(proj, cfg: dict) -> tuple:
    """R-SAFE-012：架空吊线防雷接地间距（GB 51158-2015 6.4.10：300~500m 接地、1km 绝缘子断开）。"""
    issues, skipped = [], []
    _, cables = _layer(proj, "CABLE")
    lcfg = cfg.get("lightning_grounding") or {}
    if not lcfg:
        skipped.append("防雷检查：无 lightning_grounding 配置")
        return issues, skipped
    interval = lcfg.get("messenger_wire_grounding_interval_m") or [300, 500]
    low, high = interval
    found = False
    for cable in cables:
        props = cable.properties or {}
        length = props.get("longueur") or props.get("LONGUEUR")
        try:
            length_m = float(length)
        except (TypeError, ValueError):
            continue
        mode = (_prop(cable, "MODE_POSE", "MODE_POSE") or "").upper()
        if not any(k in mode for k in ("AERIEN", "架空", "AERIAL")):
            continue
        found = True
        # 长度超过接地间隔上限且无接地字段 → 提示需人工确认（工程数据一般无接地记录）
        grounding = (_prop(cable, "GROUNDING", "MISE_A_TERRE", "接地") or "").upper()
        has_gnd = any(k in grounding for k in ("OUI", "YES", "1", "有"))
        if length_m > high and not has_gnd:
            issues.append(_issue("R-SAFE-012", "CABLE", _prop(cable, "CODE") or "",
                                 f"架空光缆 {_prop(cable, 'CODE') or ''} 长度 {length_m:.0f}m 超过吊线接地间隔上限 {high}m"
                                 f"（GB 51158 6.4.10 要求每 {low}~{high}m 接地），工程数据无接地记录，需人工确认"))
    if not found:
        skipped.append("防雷检查：无架空（AERIEN/架空）光缆数据")
    return issues, skipped

def run_safety_checks(proj, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """运行全部安全距离检查。"""
    cfg = _load_config(config_path)
    issues, skipped = [], []
    for fn in (check_ground_height, check_power_crossing, check_utility_clearances,
               check_direct_buried_clearance, check_pole_horizontal_clearance,
               check_lightning_grounding):
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
