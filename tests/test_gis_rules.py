"""GIS 空间检查框架测试（R-GIS-001~006）。"""

from shapely.geometry import LineString, Point, Polygon

from design_parser.feature import UnifiedFeature
from design_parser.gis_rules import (
    check_cable_self_loop,
    check_endpoint_on_device,
    check_range_containment,
    check_zone_overlap,
    run_gis_checks,
)
from design_parser.project_data import ProjectData


def _feat(layer, fid, geom, props, crs="EPSG:4326"):
    return UnifiedFeature(source_layer_name=layer, feature_id=fid,
                          geometry=geom, properties=props, original_crs=crs)


def _proj(layers):
    p = ProjectData.__new__(ProjectData)
    p.layers = layers
    return p


def test_zone_overlap_and_touch():
    proj = _proj({
        "ZNRO": [
            _feat("ZNRO", 0, Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]), {"CODE": "Z1"}),
            _feat("ZNRO", 1, Polygon([(2, 0), (6, 0), (6, 4), (2, 4)]), {"CODE": "Z2"}),  # 重叠
        ],
        "ZPM": [
            _feat("ZPM", 0, Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]), {"CODE": "P1"}),
            _feat("ZPM", 1, Polygon([(2, 0), (4, 0), (4, 2), (2, 2)]), {"CODE": "P2"}),  # 仅共边
        ],
    })
    issues = check_zone_overlap(proj)
    assert [i["rule_id"] for i in issues] == ["R-GIS-001"]  # 只有 ZNRO 重叠，ZPM 共边不算


def test_range_containment():
    zpm = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    proj = _proj({
        "ZPM": [_feat("ZPM", 0, zpm, {"CODE": "PM-1"})],
        "SITE": [
            _feat("SITE", 0, Point(5, 5), {"CODE": "PM-1", "TYPE": "PM", "REF_PM": "PM-1"}),
            _feat("SITE", 1, Point(50, 50), {"CODE": "PM-2", "TYPE": "PM", "REF_PM": "PM-1"}),  # 越界
        ],
        "BOITE": [
            _feat("BOITE", 0, Point(3, 3), {"CODE": "B-1", "TYPE": "PBO", "REF_PM": "PM-1"}),
            _feat("BOITE", 1, Point(30, 30), {"CODE": "B-2", "TYPE": "PBO", "REF_PM": "PM-1"}),  # 越界
        ],
        "CABLE": [
            _feat("CABLE", 0, LineString([(1, 1), (9, 9)]),
                  {"CODE": "C-1", "TYPE_CABLE": "DISTRIBUTION", "REF_PM": "PM-1"}),
            _feat("CABLE", 1, LineString([(1, 1), (20, 20)]),
                  {"CODE": "C-2", "TYPE_CABLE": "DISTRIBUTION", "REF_PM": "PM-1"}),  # 越界
        ],
    })
    issues = check_range_containment(proj)
    ids = {i["object_id"]: i["rule_id"] for i in issues}
    assert ids.get("PM-2") == "R-GIS-002"
    assert ids.get("B-2") == "R-GIS-003"
    assert ids.get("C-2") == "R-GIS-004"
    assert "PM-1" not in ids and "B-1" not in ids and "C-1" not in ids


def test_cable_self_loop():
    proj = _proj({
        "CABLE": [
            _feat("CABLE", 0, LineString([(0, 0), (1, 1)]),
                  {"CODE": "C-1", "ORIGINE": "B-1", "EXTREMITE": "B-1"}),
            _feat("CABLE", 1, LineString([(0, 0), (2, 2)]),
                  {"CODE": "C-2", "ORIGINE": "B-1", "EXTREMITE": "B-2"}),
        ],
    })
    issues = check_cable_self_loop(proj)
    assert len(issues) == 1 and issues[0]["object_id"] == "B-1"


def test_endpoint_on_device_tolerance():
    proj = _proj({
        "CABLE": [
            _feat("CABLE", 0, LineString([(0, 0), (0.000005, 0.000005)]),
                  {"CODE": "C-1", "ORIGINE": "B-1", "EXTREMITE": "B-2"}),  # 端点距设备 ~0.7m
        ],
        "BOITE": [
            _feat("BOITE", 0, Point(0, 0), {"CODE": "B-1"}),
            _feat("BOITE", 1, Point(0.00002, 0.00002), {"CODE": "B-2"}),  # 距端点 ~2.2m
        ],
    })
    issues = check_endpoint_on_device(proj, tolerance_m=0.5)
    assert len(issues) == 1  # 起点 ~0 通过，终点 ~2.2m 超过 0.5m
    assert issues[0]["rule_id"] == "R-GIS-006"
    assert "B-2" in issues[0]["message"]


def test_run_gis_checks_empty_and_api_shape():
    proj = _proj({})
    data = run_gis_checks(proj, tolerance_m=0.5)
    assert data["total"] == 0
    assert data["tolerance_m"] == 0.5
    assert data["issues"] == []
