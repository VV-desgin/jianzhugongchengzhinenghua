# -*- coding: utf-8 -*-
"""R006 字段类型：yaml 配置键（小写）需与图层字段名（大写）大小写不敏感匹配。"""
from types import SimpleNamespace

from design_parser.rule_engine import check_field_type_invalid


class _Feat:
    def __init__(self, props):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))


def _ctx(layer_name, feats):
    return SimpleNamespace(layers={layer_name: feats})


def test_uppercase_field_with_bad_value_flagged():
    """真实 yaml 配置 BOITE.capacity=int，字段 CAPACITE='abc' → R006 命中。"""
    ctx = _ctx("BOITE", [_Feat({"CODE": "BPE-01", "CAPACITE": "abc"})])
    hits = [i for i in check_field_type_invalid(ctx) if i.rule_id == "R006"]
    assert len(hits) == 1
    assert hits[0].problem_location == "字段 CAPACITE"


def test_uppercase_field_with_valid_int_ok():
    """字段 CAPACITE=12（int）→ 不命中。"""
    ctx = _ctx("BOITE", [_Feat({"CODE": "BPE-01", "CAPACITE": 12})])
    assert not [i for i in check_field_type_invalid(ctx) if i.rule_id == "R006"]


def test_float_field_valid_float_ok():
    """CABLE.length=float 配置，字段 LGR_REELLE=14.14 → 不命中。"""
    ctx = _ctx("CABLE", [_Feat({"CODE": "CABLE-01", "LGR_REELLE": 14.14})])
    assert not [i for i in check_field_type_invalid(ctx) if i.rule_id == "R006"]


def test_float_field_with_text_flagged():
    """CABLE.length=float 配置，字段 LGR_REELLE='abc' → R006 命中。"""
    ctx = _ctx("CABLE", [_Feat({"CODE": "CABLE-01", "LGR_REELLE": "abc"})])
    hits = [i for i in check_field_type_invalid(ctx) if i.rule_id == "R006"]
    assert len(hits) == 1
    assert hits[0].problem_location == "字段 LGR_REELLE"
