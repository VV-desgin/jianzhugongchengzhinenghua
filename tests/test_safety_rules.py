"""安全距离检查测试（R-SAFE-001~009，基于施工安全材料阈值）。"""

import json

from shapely.geometry import LineString

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData
from design_parser.safety_rules import _load_config, run_safety_checks


def _feat(layer, fid, geom, props, crs="EPSG:4326"):
    return UnifiedFeature(source_layer_name=layer, feature_id=fid,
                          geometry=geom, properties=props, original_crs=crs)


def _proj(layers):
    p = ProjectData.__new__(ProjectData)
    p.layers = layers
    return p


def test_config_values_from_material():
    cfg = _load_config()
    assert cfg["wall_cable"]["min_ground_height_m"] == 3.0  # GB 51158-2015 6.4.14 标准值
    assert cfg["aerial_cable"]["road_crossing_min_ground_height_m"] == 5.5
    assert cfg["wall_cable_clearances_mm"]["避雷线接地引线"] == {"parallel_mm": 1000, "crossing_mm": 300}
    assert cfg["wall_cable_clearances_mm"]["电力线"] == {"parallel_mm": 200, "crossing_mm": 100}
    assert cfg["wall_cable_clearances_mm"]["热力管"] == {"parallel_mm": 500, "crossing_mm": 300}
    assert cfg["power_line_crossing_vertical_m"]["10kv_below"]["without_lightning_protection"] == 4.0


def test_ground_height_3d():
    low = _feat("CABLE", 0, LineString([(0, 0, 2.0), (1, 1, 4.0)]), {"CODE": "C-1"})
    ok = _feat("CABLE", 1, LineString([(0, 0, 5.0), (1, 1, 6.0)]), {"CODE": "C-2"})
    data = run_safety_checks(_proj({"CABLE": [low, ok]}))
    ids = {i["object_id"]: i["rule_id"] for i in data["issues"]}
    assert ids.get("C-1") == "R-SAFE-001"
    assert "C-2" not in ids


def test_aerial_cable_road_height():
    aerial = _feat("CABLE", 0, LineString([(0, 0, 5.0), (1, 1, 8.0)]),
                   {"CODE": "C-A", "MODE_POSE": "AERIEN"})
    data = run_safety_checks(_proj({"CABLE": [aerial]}))
    assert any(i["rule_id"] == "R-SAFE-002" and i["object_id"] == "C-A" for i in data["issues"])


def test_power_crossing_vertical_gap():
    cable = _feat("CABLE", 0, LineString([(0, 0, 10.0), (2, 0, 10.0)]), {"CODE": "C-1"})
    power = _feat("POWER", 0, LineString([(1, -1, 6.0), (1, 1, 6.0)]),
                  {"CODE": "P-1", "VOLTAGE": "10KV"})  # 无防雷保护 -> 4m，实际垂直差 4m -> 恰好达标? 10-6=4
    data = run_safety_checks(_proj({"CABLE": [cable], "POWER": [power]}))
    # 垂直净距 4.0 不低于 4.0 -> 不判违规
    assert not any(i["rule_id"] == "R-SAFE-003" for i in data["issues"])

    power2 = _feat("POWER", 0, LineString([(1, -1, 5.0), (1, 1, 5.0)]),
                   {"CODE": "P-2", "VOLTAGE": "10KV"})  # 垂直差 5m -> 无保护 4m 达标，但有保护 2m 也达标
    data2 = run_safety_checks(_proj({"CABLE": [cable], "POWER": [power2]}))
    assert not any(i["rule_id"] == "R-SAFE-003" for i in data2["issues"])

    power3 = _feat("POWER", 0, LineString([(1, -1, 7.0), (1, 1, 7.0)]),
                   {"CODE": "P-3", "VOLTAGE": "10KV"})  # 垂直差 3m < 4m -> 违规
    data3 = run_safety_checks(_proj({"CABLE": [cable], "POWER": [power3]}))
    assert any(i["rule_id"] == "R-SAFE-003" for i in data3["issues"])


def test_utility_parallel_clearance():
    # 两条近似平行线，间距约 0.0000005 度（~0.055m < 0.15m 电力线平行净距）
    cable = _feat("CABLE", 0, LineString([(0, 0), (0.001, 0)]), {"CODE": "C-1"})
    power_near = _feat("POWER", 0, LineString([(0, 0.0000005), (0.001, 0.0000005)]), {"CODE": "P-1"})
    data = run_safety_checks(_proj({"CABLE": [cable], "POWER": [power_near]}))
    assert any(i["rule_id"] == "R-SAFE-004" for i in data["issues"])

    power_far = _feat("POWER", 0, LineString([(0, 0.00001), (0.001, 0.00001)]), {"CODE": "P-2"})
    data2 = run_safety_checks(_proj({"CABLE": [cable], "POWER": [power_far]}))
    assert not any(i["rule_id"] == "R-SAFE-004" for i in data2["issues"])


def test_safety_check_empty_and_source():
    data = run_safety_checks(_proj({}))
    assert data["total"] == 0
    assert "source" in data and "YD/T 5102-2024" in data["source"]
    assert data["counts"] == {}


def test_safety_check_endpoint_shape(client):
    """接口返回固定结构（无图层项目）。"""
    import tempfile
    import zipfile
    from pathlib import Path

    tmp = tempfile.mkdtemp(prefix="safety_pkg_")
    zip_path = Path(tmp) / "empty_pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("readme.txt", "no layers")
    with zip_path.open("rb") as f:
        resp = client.post("/project/load", files={"file": ("empty_pkg.zip", f, "application/zip")})
    assert resp.status_code == 200
    pid = resp.json()["data"]["project_id"]

    r = client.get(f"/project/{pid}/safety-check")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total"] == 0
    assert "issues" in data and "skipped" in data and "source" in data


def test_direct_buried_clearance():
    """R-SAFE-010：直埋光缆与地下设施平行净距（YD/T 5102-2024 表7）。"""
    buried = _feat("CABLE", 0, LineString([(0, 0), (0.01, 0)]),
                   {"CODE": "B-1", "MODE_POSE": "SOUTERRAIN"})
    water_near = _feat("WATER", 0, LineString([(0, 0.000002), (0.01, 0.000002)]),
                       {"CODE": "W-1"})  # ~0.2m < 0.5m 给水管平行净距
    data = run_safety_checks(_proj({"CABLE": [buried], "WATER": [water_near]}))
    assert any(i["rule_id"] == "R-SAFE-010" for i in data["issues"])

    water_far = _feat("WATER", 0, LineString([(0, 0.00002), (0.01, 0.00002)]),
                      {"CODE": "W-2"})  # ~1m > 0.5m 达标
    data2 = run_safety_checks(_proj({"CABLE": [buried], "WATER": [water_far]}))
    assert not any(i["rule_id"] == "R-SAFE-010" for i in data2["issues"])


def test_pole_horizontal_clearance():
    """R-SAFE-011：电杆与树木水平净距（YD/T 5102-2024 表10：市区树木 0.5m）。"""
    pole = _feat("PTECH", 0, LineString([(0, 0), (0.01, 0)]), {"CODE": "P-1"})
    tree_near = _feat("TREE", 0, LineString([(0.000002, 0), (0.000003, 0)]),
                      {"CODE": "T-1"})  # ~0.2m < 0.5m
    data = run_safety_checks(_proj({"PTECH": [pole], "TREE": [tree_near]}))
    assert any(i["rule_id"] == "R-SAFE-011" for i in data["issues"])


def test_lightning_grounding_long_aerial():
    """R-SAFE-012：架空光缆长度超过接地间隔且无接地记录 → 提示人工确认。"""
    long_aerial = _feat("CABLE", 0, LineString([(0, 0), (0, 0.01)]),
                        {"CODE": "C-LONG", "MODE_POSE": "AERIEN", "longueur": 1200})
    data = run_safety_checks(_proj({"CABLE": [long_aerial]}))
    assert any(i["rule_id"] == "R-SAFE-012" for i in data["issues"])

    grounded = _feat("CABLE", 0, LineString([(0, 0), (0, 0.01)]),
                     {"CODE": "C-GND", "MODE_POSE": "AERIEN", "longueur": 1200, "GROUNDING": "OUI"})
    data2 = run_safety_checks(_proj({"CABLE": [grounded]}))
    assert not any(i["rule_id"] == "R-SAFE-012" for i in data2["issues"])
