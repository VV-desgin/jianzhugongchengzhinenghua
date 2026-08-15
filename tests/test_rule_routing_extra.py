"""Task A5: 规则路由补齐测试（TDD 先行）。

R005_3/R027/R028/R033 已接入 GIS 类目路由；R005_1（官方 R-REL-001，
SITE.CODE=ZPM.CODE 双向一一对应）实现与官方一致，但与现有正确案例包
（TC-01 2.6 等采用 ZPM.CODE=ZPM-xx + ZPM.REF_PM=SITE.CODE 编码模型）
冲突，口径待官方/需求方确认，暂不路由（见 docs/07_业务参数说明.md）。
"""
from api import RULE_ROUTING

ACTIVE = {"R005_3", "R027", "R028", "R033"}
NOT_ROUTED = {"R005_1"}
GIS_CATS = ["完整设计图", "竣工图", "竣工图（含BOM）", "设计图（含纤芯）"]


def test_gis_categories_route_active_extra_rules():
    for cat in GIS_CATS:
        assert ACTIVE.issubset(set(RULE_ROUTING[cat]))


def test_r005_1_not_routed_pending_scope_confirmation():
    for cat in GIS_CATS:
        assert NOT_ROUTED.isdisjoint(set(RULE_ROUTING[cat]))
