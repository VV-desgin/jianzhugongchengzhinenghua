"""零值核心计算字段拦截（评测 TC-14：LONGUEUR=0.0 长度缺失）。

- R005 必填非空：核心计算字段（CABLE/INFRASTRUCTURE.LONGUEUR 等）0.0/负值视为缺失；
- BOM：存在零长度光缆时，光缆/钢绞线行标「待人工确认」，不再静默计入。
"""

from types import SimpleNamespace

from design_parser.bom_builder import build_bom
from design_parser.rule_engine import check_required_fields


def _feat(props):
    return SimpleNamespace(properties=props, feature_id="f1")


def test_cable_zero_length_flagged():
    ctx = SimpleNamespace(layers={"CABLE": [_feat({"CODE": "CABLE-01", "LONGUEUR": 0.0})]})
    hits = [i for i in check_required_fields(ctx)
            if i.rule_id == "R005" and "LONGUEUR" in (i.problem_location or "")]
    assert len(hits) == 1
    assert "长度为零或负数，视为长度缺失" in hits[0].error_description


def test_cable_positive_length_ok():
    ctx = SimpleNamespace(layers={"CABLE": [_feat({"CODE": "CABLE-01", "LONGUEUR": 14.14})]})
    assert check_required_fields(ctx) == []


def test_cable_negative_length_flagged():
    ctx = SimpleNamespace(layers={"CABLE": [_feat({"CODE": "CABLE-01", "LONGUEUR": -1.0})]})
    hits = [i for i in check_required_fields(ctx) if i.rule_id == "R005"]
    assert len(hits) == 1


def test_string_zero_flagged():
    ctx = SimpleNamespace(layers={"CABLE": [_feat({"CODE": "CABLE-01", "LONGUEUR": "0.0"})]})
    hits = [i for i in check_required_fields(ctx) if i.rule_id == "R005"]
    assert len(hits) == 1


def test_infrastructure_zero_length_flagged():
    ctx = SimpleNamespace(layers={"INFRASTRUCTURE": [_feat({"CODE": "INF-01", "LONGUEUR": 0})]})
    hits = [i for i in check_required_fields(ctx) if i.rule_id == "R005"]
    assert len(hits) == 1


def test_bom_zero_length_cable_marked_manual():
    eng = {
        "project_id": "p1",
        "objects": {
            "cable": [{"code": "CABLE-01", "longueur": 0.0, "type": "DISTRIBUTION", "capacite": 24},
                      {"code": "CABLE-02", "longueur": 14.14, "type": "DISTRIBUTION", "capacite": 24}],
            "boite": [], "ptech": [], "site": [], "infrastructure": [],
        },
    }
    bom = build_bom(eng)
    cable = [it for it in bom["bom_items"] if it["\u7269\u6599\u7f16\u7801"] == "500002050"]
    assert cable and cable[0]["\u7f6e\u4fe1\u72b6\u6001"] == "\u5f85\u4eba\u5de5\u786e\u8ba4"
    assert "\u96f6\u503c" in cable[0]["\u8ba1\u7b97\u65b9\u5f0f"] or "\u7f3a\u5931" in cable[0]["\u8ba1\u7b97\u65b9\u5f0f"]
