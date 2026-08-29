# -*- coding: utf-8 -*-
"""投影坐标系（EPSG:32629）下端点距离类规则回归：R010/R023/R024/R006_6。

背景：旧实现硬编码 WGS84 测地线，把米制坐标当经纬度，pyproj 对纬度 >90 抛错或返回 NaN，
投影数据下「端点完全重合」被误报（或 R023 漏报）。修复后按 feature 的 original_crs 计算距离。
"""
from types import SimpleNamespace

import pytest
from shapely.geometry import LineString, Point

from design_parser.feature import UnifiedFeature
from design_parser.models import Box, Cable
from design_parser.rule_engine import (
    check_cable_breakpoints,
    check_cable_device_endpoint_match,
    check_cable_endpoint_on_boite,
    check_cable_endpoint_on_device,
)

CRS = "EPSG:32629"  # UTM 29N，Morocco 常用投影


def _feat(layer, fid, geom, props, crs=CRS):
    return UnifiedFeature(layer, fid, geom, props, original_crs=crs)


def test_r010_exact_endpoints_projected_crs_no_false_positive():
    """投影坐标系下端点与设备点完全重合，R010 不得误报。"""
    box_a = Box(id="1", code="PBO-A", geometry=Point(500000.0, 3650000.0), properties={})
    box_b = Box(id="2", code="PBO-B", geometry=Point(500100.0, 3650100.0), properties={})
    cable = Cable(id="1", code="C-1",
                  geometry=LineString([(500000.0, 3650000.0), (500100.0, 3650100.0)]),
                  start_device="PBO-A", end_device="PBO-B", properties={})
    ctx = SimpleNamespace(boxes=[box_a, box_b], cables=[cable], layers={}, device_code_index={}, crs=CRS)
    try:
        hits = [r for r in check_cable_endpoint_on_device(ctx) if not r.passed]
    except Exception as e:
        pytest.fail(f"R010 在投影坐标系下崩溃: {e}")
    assert hits == []


def test_r010_offset_projected_crs_still_flagged():
    """投影坐标系下端点偏移超过容差，R010 仍要检出。"""
    box_a = Box(id="1", code="PBO-A", geometry=Point(500000.0, 3650000.0), properties={})
    box_b = Box(id="2", code="PBO-B", geometry=Point(500102.0, 3650100.0), properties={})
    cable = Cable(id="1", code="C-1",
                  geometry=LineString([(500000.0, 3650000.0), (500100.0, 3650100.0)]),
                  start_device="PBO-A", end_device="PBO-B", properties={})
    ctx = SimpleNamespace(boxes=[box_a, box_b], cables=[cable], layers={}, device_code_index={}, crs=CRS)
    try:
        hits = [r for r in check_cable_endpoint_on_device(ctx) if not r.passed]
    except Exception as e:
        pytest.fail(f"R010 在投影坐标系下崩溃: {e}")
    assert len(hits) == 1


def test_r023_projected_crs_flags_isolated_endpoints():
    """投影坐标系下相距 >max_gap 的光缆端点，R023 必须检出孤立端点。"""
    c1 = _feat("CABLE", 0, LineString([(500000.0, 3650000.0), (500010.0, 3650010.0)]), {"CODE": "C-1"})
    c2 = _feat("CABLE", 1, LineString([(501000.0, 3651000.0), (501010.0, 3651010.0)]), {"CODE": "C-2"})
    ctx = SimpleNamespace(layers={"CABLE": [c1, c2]}, boxes=[], cables=[], device_code_index={}, crs=CRS)
    try:
        hits = [r for r in check_cable_breakpoints(ctx) if not r.passed]
    except Exception as e:
        pytest.fail(f"R023 在投影坐标系下崩溃: {e}")
    assert len(hits) >= 4


def test_r024_exact_endpoints_projected_crs_no_false_positive():
    """投影坐标系下 ORIGINE/EXTREMITE 与端点一一重合，R024 不得误报。"""
    box_a = Box(id="1", code="DEV-A", geometry=Point(500000.0, 3650000.0), properties={})
    box_b = Box(id="2", code="DEV-B", geometry=Point(500100.0, 3650100.0), properties={})
    cable = Cable(id="1", code="C-1",
                  geometry=LineString([(500000.0, 3650000.0), (500100.0, 3650100.0)]),
                  start_device="DEV-A", end_device="DEV-B", properties={})
    ctx = SimpleNamespace(boxes=[box_a, box_b], cables=[cable], layers={}, device_code_index={}, crs=CRS)
    try:
        hits = [r for r in check_cable_device_endpoint_match(ctx) if not r.passed]
    except Exception as e:
        pytest.fail(f"R024 在投影坐标系下崩溃: {e}")
    assert hits == []


def test_r024_offset_projected_crs_still_flagged():
    """投影坐标系下设备点偏移超过容差，R024 仍要检出。"""
    box_a = Box(id="1", code="DEV-A", geometry=Point(500000.0, 3650000.0), properties={})
    box_b = Box(id="2", code="DEV-B", geometry=Point(500102.0, 3650100.0), properties={})
    cable = Cable(id="1", code="C-1",
                  geometry=LineString([(500000.0, 3650000.0), (500100.0, 3650100.0)]),
                  start_device="DEV-A", end_device="DEV-B", properties={})
    ctx = SimpleNamespace(boxes=[box_a, box_b], cables=[cable], layers={}, device_code_index={}, crs=CRS)
    try:
        hits = [r for r in check_cable_device_endpoint_match(ctx) if not r.passed]
    except Exception as e:
        pytest.fail(f"R024 在投影坐标系下崩溃: {e}")
    assert len(hits) == 1


def test_r006_6_exact_endpoints_projected_crs_no_false_positive():
    """投影坐标系下 CABLE 端点与 BOITE 坐标完全重合，R006_6 不得误报。"""
    layers = {
        "BOITE": [
            _feat("BOITE", 0, Point(500000.0, 3650000.0), {"CODE": "PBO-A"}),
            _feat("BOITE", 1, Point(500100.0, 3650100.0), {"CODE": "PBO-B"}),
        ],
        "CABLE": [
            _feat("CABLE", 0, LineString([(500000.0, 3650000.0), (500100.0, 3650100.0)]),
                  {"CODE": "C-1", "ORIGINE": "PBO-A", "EXTREMITE": "PBO-B"}),
        ],
    }
    ctx = SimpleNamespace(layers=layers, boxes=[], cables=[], device_code_index={}, crs=CRS)
    try:
        hits = [r for r in check_cable_endpoint_on_boite(ctx) if not r.passed]
    except Exception as e:
        pytest.fail(f"R006_6 在投影坐标系下崩溃: {e}")
    assert hits == []
