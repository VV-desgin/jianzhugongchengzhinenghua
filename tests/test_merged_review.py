# -*- coding: utf-8 -*-
"""规则执行入口一致性：ProjectData.run_all_rules 必须合并 R-GIS 与 R-SAFE 结果。

背景：/project/{id}/rules/run、run-all-and-cache、/agent/full-pipeline 只跑 ALL_RULES(50)，
GIS/SAFE 只由 data-pipeline 合并，同一项目不同入口审查覆盖不一致。
"""
from shapely.geometry import LineString

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData


def test_run_all_rules_merges_gis_and_safety_rules():
    """run_all_rules 输出必须包含 R-GIS-005（自环）与 R-SAFE-001（离地高度）命中。"""
    p = ProjectData.__new__(ProjectData)
    low_z = UnifiedFeature("CABLE", 0, LineString([(0, 0, 2.0), (10, 0, 2.0)]), {"CODE": "C-WALL"})
    loop = UnifiedFeature("CABLE", 1, LineString([(20, 0, 5.0), (30, 1, 5.0)]),
                          {"CODE": "C-LOOP", "ORIGINE": "DEV-A", "EXTREMITE": "DEV-A"})
    p.layers = {"CABLE": [low_z, loop]}
    p.package = None  # 桩项目无压缩包，RuleContext 需访问该属性
    p.qgs = None
    results = p.run_all_rules()
    ids = {r.rule_id for r in results}
    assert "R-SAFE-001" in ids
    assert "R-GIS-005" in ids
