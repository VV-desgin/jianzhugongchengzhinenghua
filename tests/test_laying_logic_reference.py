"""跨图层敷设逻辑引用校验（2026-08-23 优化）。

- CABLE.CODE_INFRA → INFRASTRUCTURE.CODE（光缆承载基础设施，官方字段必填）；
- INFRASTRUCTURE.ORIGINE/EXTREMITE → IMB/PTECH/SITE/BOITE.CODE（管道/杆路端点承载逻辑）。
"""
from types import SimpleNamespace

from design_parser.rule_engine import check_reference_exists


class _Feat:
    def __init__(self, props):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))


def _ctx(layers, cables):
    return SimpleNamespace(layers=layers, boxes=[], device_code_index={}, cables=cables)


def test_cable_code_infra_dangling():
    """光缆 CODE_INFRA 指向不存在的承载基础设施 → R008 error。"""
    ctx = _ctx(
        {"INFRASTRUCTURE": [_Feat({"CODE": "INF-01"})], "CABLE": []},
        [_Feat({"CODE": "CABLE-01", "CODE_INFRA": "INF-99"})],
    )
    hits = [i for i in check_reference_exists(ctx) if i.rule_id == "R008"]
    assert len(hits) == 1
    assert hits[0].problem_location == "字段 CODE_INFRA"
    assert hits[0].severity == "error"
    assert "承载基础设施编码 'INF-99' 不存在" in hits[0].error_description


def test_cable_code_infra_valid():
    """CODE_INFRA 存在 → 不报。"""
    ctx = _ctx(
        {"INFRASTRUCTURE": [_Feat({"CODE": "INF-01"})], "CABLE": []},
        [_Feat({"CODE": "CABLE-01", "CODE_INFRA": "INF-01"})],
    )
    assert not [i for i in check_reference_exists(ctx) if i.problem_location == "字段 CODE_INFRA"]


def test_cable_code_infra_skip_without_infra_layer():
    """无 INFRASTRUCTURE 图层时不查 CODE_INFRA（避免与缺图层规则重复）。"""
    ctx = _ctx({"CABLE": []}, [_Feat({"CODE": "CABLE-01", "CODE_INFRA": "INF-99"})])
    assert not [i for i in check_reference_exists(ctx) if i.problem_location == "字段 CODE_INFRA"]


def test_infrastructure_endpoint_dangling():
    """基础设施终点引用不存在的建筑/设备编码 → R008 error。"""
    ctx = _ctx(
        {"INFRASTRUCTURE": [_Feat({"CODE": "INF-01", "ORIGINE": "PTC-01", "EXTREMITE": "BAT-99"})],
         "PTECH": [_Feat({"CODE": "PTC-01"})]},
        [],
    )
    hits = [i for i in check_reference_exists(ctx) if i.rule_id == "R008"]
    assert len(hits) == 1
    assert hits[0].problem_location == "字段 EXTREMITE"
    assert "设备/建筑编码 'BAT-99' 不存在" in hits[0].error_description


def test_infrastructure_endpoint_valid():
    """基础设施端点指向存在的 PTECH/IMB 等 → 不报。"""
    ctx = _ctx(
        {"INFRASTRUCTURE": [_Feat({"CODE": "INF-01", "ORIGINE": "PTC-01", "EXTREMITE": "IMB-01"})],
         "PTECH": [_Feat({"CODE": "PTC-01"})],
         "IMB": [_Feat({"CODE": "IMB-01"})]},
        [],
    )
    assert not [i for i in check_reference_exists(ctx) if i.rule_id == "R008"]


def test_cable_endpoint_dangling_still_flagged():
    """原有光缆端点引用检查不受影响。"""
    ctx = _ctx(
        {"BOITE": [_Feat({"CODE": "PBO-01"})], "CABLE": []},
        [_Feat({"CODE": "CABLE-01", "ORIGINE": "PBO-01", "EXTREMITE": "GHOST-99"})],
    )
    hits = [i for i in check_reference_exists(ctx) if i.rule_id == "R008"]
    assert any(i.problem_location == "字段 end" and "GHOST-99" in i.actual_value for i in hits)
