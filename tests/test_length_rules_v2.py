"""字段长度 v2.0 对齐测试（官方字段口径配置 v2.0）。

依据：docs/官方固定数据/字段口径配置_v2.0.json length_rules（来源=字段别名映射表 v2.0）。
键名为 DBF 截断名（保持既有键名，只对齐值）；CABLE_AMON 按官方已确认 Longueur=30 覆盖 v2.0 表 20。
"""

import io

import yaml

LAYERS = yaml.safe_load(io.open("design_parser/mappings/layer_mapping.yaml", encoding="utf-8"))["layers"]


def _fl(layer, key):
    return LAYERS[layer]["field_lengths"].get(key)


def test_cable_lengths_v2():
    assert _fl("CABLE", "CAPACITE") == 3
    assert _fl("CABLE", "DIAMETRE") == 2
    assert _fl("CABLE", "MODULO") == 2
    assert _fl("CABLE", "LONGUEUR") == 10
    assert _fl("CABLE", "NB_FIBRE_U") == 3
    assert _fl("CABLE", "NB_FIBRE_D") == 3


def test_boite_lengths_v2():
    assert _fl("BOITE", "CAPACITE") == 3
    assert _fl("BOITE", "NB_FIBRE_U") == 3
    assert _fl("BOITE", "NB_CASSETT") == 3
    assert _fl("BOITE", "NB_SPLICES") == 5
    assert _fl("BOITE", "CODE_POSTA") == 5
    assert _fl("BOITE", "TYPE_STRUC") == 50


def test_other_layers_lengths_v2():
    assert _fl("INFRASTRUCTURE", "LONGUEUR") == 10
    assert _fl("PTECH", "NB_BOITIER") == 2
    assert _fl("PTECH", "CODE_POSTA") == 5
    assert _fl("SITE", "CODE_POSTA") == 5
    assert _fl("IMB", "NUM_GESTIO") == 23


def test_cable_amont_override_kept():
    """官方已确认 CABLE_AMONT Longueur=30，覆盖 v2.0 表 20（2026-08-08 口径）。"""
    assert _fl("BOITE", "CABLE_AMON") == 30


def test_numeric_values_not_length_flagged():
    """DBF 数值列（int/float）不参与 R032 字符串长度比较：13.470000000000001 等全精度
    float 字符串化后长度 15~18 位，属数值列宽语义，不应按串长误报（赛题 314 条回归）。"""
    from types import SimpleNamespace

    from design_parser.rule_engine import check_field_length

    feats = [SimpleNamespace(
        properties={"CODE": "CABLE-001", "LONGUEUR": 13.473601128875206, "CAPACITE": 24},
        feature_id="f1")]
    ctx = SimpleNamespace(layers={"CABLE": feats})
    assert [i for i in check_field_length(ctx) if i.rule_id == "R032"] == []


def test_long_text_still_flagged():
    """文本字段超长仍须报 R032（数值跳过不影响文本检查）。"""
    from types import SimpleNamespace

    from design_parser.rule_engine import check_field_length

    feats = [SimpleNamespace(properties={"CODE": "X" * 35}, feature_id="f1")]
    ctx = SimpleNamespace(layers={"CABLE": feats})
    hits = [i for i in check_field_length(ctx) if i.rule_id == "R032"]
    assert len(hits) == 1
    assert "CODE" in (hits[0].problem_location or "")
