# -*- coding: utf-8 -*-
"""TC-18/TC-21/TC-22/TC-23 新规则单元测试。

- R-GIS-007：同类空间实体坐标完全重叠（TC-18）
- R-FIBER-003：光缆容量与业务占用相容（TC-21）
- R-LIFE-001：跨图层生命周期挂载排他（TC-22）
- R034：支撑件物理承载与挂载上限（TC-23）
"""
from types import SimpleNamespace

from design_parser.rule_engine import (
    check_cable_capacity_business_compat,
    check_lifecycle_mount_exclusivity,
    check_point_coordinate_overlap,
    check_support_capacity_limit,
)


class _Feat:
    def __init__(self, props):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))
        self._geometry = None


def _ctx(layers):
    return SimpleNamespace(layers=layers, boxes=[], cables=[], device_code_index={})


# ---------- R-GIS-007 ----------

def test_same_layer_point_overlap_flagged():
    """同图层不同 CODE 的点实体坐标完全相同 → R-GIS-007 error（TC-18）。"""
    ctx = _ctx({
        "PTECH": [
            _Feat({"CODE": "PTC-01", "X": -8.4999, "Y": 33.2001}),
            _Feat({"CODE": "PTC-OVERLAP-01", "X": -8.4999, "Y": 33.2001}),
        ]
    })
    hits = [i for i in check_point_coordinate_overlap(ctx) if i.rule_id == "R-GIS-007"]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert "PTC-01" in hits[0].error_description and "PTC-OVERLAP-01" in hits[0].error_description


def test_same_coordinate_same_code_not_flagged():
    """相同 CODE 的重复要素由 R007 负责，R-GIS-007 不重复报。"""
    ctx = _ctx({
        "PTECH": [
            _Feat({"CODE": "PTC-01", "X": -8.4999, "Y": 33.2001}),
            _Feat({"CODE": "PTC-01", "X": -8.4999, "Y": 33.2001}),
        ]
    })
    assert not [i for i in check_point_coordinate_overlap(ctx) if i.rule_id == "R-GIS-007"]


def test_cross_layer_same_coordinate_ok():
    """跨图层同坐标是正常挂载（PBO 在电杆点位），不报。"""
    ctx = _ctx({
        "PTECH": [_Feat({"CODE": "PTC-01", "X": -8.4999, "Y": 33.2001})],
        "BOITE": [_Feat({"CODE": "PBO-01", "X": -8.4999, "Y": 33.2001})],
    })
    assert not [i for i in check_point_coordinate_overlap(ctx) if i.rule_id == "R-GIS-007"]


def test_different_coordinates_ok():
    ctx = _ctx({
        "PTECH": [
            _Feat({"CODE": "PTC-01", "X": -8.4999, "Y": 33.2001}),
            _Feat({"CODE": "PTC-02", "X": -8.4998, "Y": 33.2002}),
        ]
    })
    assert not [i for i in check_point_coordinate_overlap(ctx) if i.rule_id == "R-GIS-007"]


def test_missing_coordinates_no_crash():
    ctx = _ctx({"PTECH": [_Feat({"CODE": "PTC-01"}), _Feat({"CODE": "PTC-02"})]})
    assert not [i for i in check_point_coordinate_overlap(ctx) if i.rule_id == "R-GIS-007"]


# ---------- R-FIBER-003 ----------

def test_distribution_zero_capacity_flagged():
    """DISTRIBUTION 光缆 CAPACITE=0 但在用纤芯 6 → R-FIBER-003 error（TC-21）。"""
    ctx = _ctx({
        "CABLE": [_Feat({"CODE": "CABLE-01", "TYPE_CABLE": "DISTRIBUTION",
                         "CAPACITE": 0, "NB_FIBRE_U": 6, "NB_FIBRE_D": 6})]
    })
    hits = [i for i in check_cable_capacity_business_compat(ctx) if i.rule_id == "R-FIBER-003"]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert "CABLE-01" in hits[0].error_description and "0" in hits[0].error_description


def test_distribution_usage_over_capacity_flagged():
    """已分配纤芯数大于容量 → R-FIBER-003 error。"""
    ctx = _ctx({
        "CABLE": [_Feat({"CODE": "CABLE-01", "TYPE_CABLE": "DISTRIBUTION",
                         "CAPACITE": 12, "NB_FIBRE_U": 6, "NB_FIBRE_D": 13})]
    })
    hits = [i for i in check_cable_capacity_business_compat(ctx) if i.rule_id == "R-FIBER-003"]
    assert len(hits) == 1


def test_distribution_valid_capacity_ok():
    ctx = _ctx({
        "CABLE": [_Feat({"CODE": "CABLE-01", "TYPE_CABLE": "DISTRIBUTION",
                         "CAPACITE": 12, "NB_FIBRE_U": 6, "NB_FIBRE_D": 6})]
    })
    assert not [i for i in check_cable_capacity_business_compat(ctx) if i.rule_id == "R-FIBER-003"]


def test_non_distribution_zero_capacity_ok():
    """非 DISTRIBUTION 业务类型不做该约束（避免误伤干线/集客光缆口径）。"""
    ctx = _ctx({
        "CABLE": [_Feat({"CODE": "CABLE-01", "TYPE_CABLE": "TRANSPORT",
                         "CAPACITE": 0, "NB_FIBRE_U": 0, "NB_FIBRE_D": 0})]
    })
    assert not [i for i in check_cable_capacity_business_compat(ctx) if i.rule_id == "R-FIBER-003"]


# ---------- R-LIFE-001 ----------

def test_active_box_on_abandoned_support_flagged():
    """在用终端盒挂载在 ABANDONNE 电杆上 → R-LIFE-001 error（TC-22）。"""
    ctx = _ctx({
        "BOITE": [_Feat({"CODE": "PBO-01", "STATUT": "DEPLOYE", "CODE_PTC": "PTC-01"})],
        "PTECH": [_Feat({"CODE": "PTC-01", "STATUT": "ABANDONNE"})],
    })
    hits = [i for i in check_lifecycle_mount_exclusivity(ctx) if i.rule_id == "R-LIFE-001"]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert "PBO-01" in hits[0].error_description and "PTC-01" in hits[0].error_description


def test_active_box_on_active_support_ok():
    ctx = _ctx({
        "BOITE": [_Feat({"CODE": "PBO-01", "STATUT": "DEPLOYE", "CODE_PTC": "PTC-01"})],
        "PTECH": [_Feat({"CODE": "PTC-01", "STATUT": "DEPLOYE"})],
    })
    assert not [i for i in check_lifecycle_mount_exclusivity(ctx) if i.rule_id == "R-LIFE-001"]


def test_abandoned_box_on_abandoned_support_ok():
    """双方均废弃 → 生命周期一致，不报。"""
    ctx = _ctx({
        "BOITE": [_Feat({"CODE": "PBO-01", "STATUT": "ABANDONNE", "CODE_PTC": "PTC-01"})],
        "PTECH": [_Feat({"CODE": "PTC-01", "STATUT": "ABANDONNE"})],
    })
    assert not [i for i in check_lifecycle_mount_exclusivity(ctx) if i.rule_id == "R-LIFE-001"]


def test_active_cable_on_abandoned_infrastructure_flagged():
    """在用光缆依附废弃管道 → R-LIFE-001 error。"""
    ctx = _ctx({
        "CABLE": [_Feat({"CODE": "CABLE-01", "STATUT": "DEPLOYE", "CODE_INFRA": "INF-01"})],
        "INFRASTRUCTURE": [_Feat({"CODE": "INF-01", "STATUT": "ABANDONNE"})],
    })
    hits = [i for i in check_lifecycle_mount_exclusivity(ctx) if i.rule_id == "R-LIFE-001"]
    assert len(hits) == 1


# ---------- R034 ----------

def test_nb_boitier_huge_flagged():
    """NB_BOITIER=9999 超出物理承载上限 → R034 error（TC-23）。"""
    ctx = _ctx({"PTECH": [_Feat({"CODE": "PTC-01", "NB_BOITIER": 9999})]})
    hits = [i for i in check_support_capacity_limit(ctx) if i.rule_id == "R034"]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert "PTC-01" in hits[0].error_description


def test_nb_boitier_negative_flagged():
    ctx = _ctx({"PTECH": [_Feat({"CODE": "PTC-01", "NB_BOITIER": -1})]})
    hits = [i for i in check_support_capacity_limit(ctx) if i.rule_id == "R034"]
    assert len(hits) == 1


def test_nb_boitier_normal_ok():
    ctx = _ctx({"PTECH": [_Feat({"CODE": "PTC-01", "NB_BOITIER": 1})]})
    assert not [i for i in check_support_capacity_limit(ctx) if i.rule_id == "R034"]


def test_actual_boxes_over_limit_flagged():
    """拓扑层：同一支撑件实际下挂设备数超过上限 → R034 error。"""
    boxes = [_Feat({"CODE": f"PBO-{i:02d}", "CODE_PTC": "PTC-01"}) for i in range(9)]
    ctx = _ctx({"PTECH": [_Feat({"CODE": "PTC-01", "NB_BOITIER": 1})], "BOITE": boxes})
    hits = [i for i in check_support_capacity_limit(ctx) if i.rule_id == "R034"]
    assert len(hits) == 1


def test_actual_boxes_within_limit_ok():
    boxes = [_Feat({"CODE": f"PBO-{i:02d}", "CODE_PTC": "PTC-01"}) for i in range(4)]
    ctx = _ctx({"PTECH": [_Feat({"CODE": "PTC-01", "NB_BOITIER": 1})], "BOITE": boxes})
    assert not [i for i in check_support_capacity_limit(ctx) if i.rule_id == "R034"]
