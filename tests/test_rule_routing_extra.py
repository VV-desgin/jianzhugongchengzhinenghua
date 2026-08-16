"""Task A5: 规则路由补齐测试（TDD 先行）。

R005_1/R005_3/R027/R028/R033 已接入 GIS 类目路由。
R005_1 按官方 R-REL-001（SITE.CODE=ZPM.CODE 双向一一对应）口径启用，
2026-08-16 用户决策：优先遵循官方源文件口径。
"""
from api import RULE_ROUTING

ACTIVE = {"R005_1", "R005_3", "R027", "R028", "R033"}
GIS_CATS = ["完整设计图", "竣工图", "竣工图（含BOM）", "设计图（含纤芯）"]


def test_gis_categories_route_active_extra_rules():
    for cat in GIS_CATS:
        assert ACTIVE.issubset(set(RULE_ROUTING[cat]))
