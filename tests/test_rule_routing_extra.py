"""Task A5: 规则路由补齐测试（TDD 先行）。"""
from api import RULE_ROUTING

EXTRA = {"R005_1", "R005_3", "R027", "R028", "R033"}
GIS_CATS = ["完整设计图", "竣工图", "竣工图（含BOM）", "设计图（含纤芯）"]


def test_gis_categories_route_extra_rules():
    for cat in GIS_CATS:
        assert EXTRA.issubset(set(RULE_ROUTING[cat]))
