# -*- coding: utf-8 -*-
"""RULE-02 真值表测试：R004 / R005_1 / R007 规则逻辑语义锁定。

依据：
- 06 表 G7/R004、G9/I9/R005_1、G18/I18/R007
- 09 规则映射表对应行
- 官方审查规则库 v2.0 对应条目

每个规则按"真值表"形式给出正反例，锁定当前代码实现语义。
"""
from types import SimpleNamespace

from design_parser.rule_engine import (
    check_layer_geom_type,
    check_site_pm_zpm_bidirectional,
    check_code_duplicate,
)
from design_parser.feature import GeomType


class _Feat:
    def __init__(self, props, geom=None):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))
        self._geometry = geom

    @property
    def geometry_type(self):
        if isinstance(self._geometry, GeomType):
            return self._geometry
        return None


def _ctx(layers, boxes=None, cables=None):
    return SimpleNamespace(
        layers=layers,
        boxes=boxes or [],
        cables=cables or [],
        device_code_index={},
    )


# ============================================================
# R004: 图层几何类型检查（OFFICIAL_LAYERS 定义）
# ============================================================

def test_r004_geom_type_match_passes():
    """R004 真值表：几何类型匹配 → 无问题。"""
    ctx = _ctx({"IMB": [_Feat({"CODE": "IMB-01"}, GeomType.POINT)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].rule_id == "R004"


def test_r004_geom_type_mismatch_flagged():
    """R004 真值表：几何类型不匹配 → R004 error。"""
    ctx = _ctx({"IMB": [_Feat({"CODE": "IMB-01"}, GeomType.LINE)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].rule_id == "R004"
    assert "point" in results[0].expected_value
    assert "line" in results[0].actual_value


def test_r004_layer_not_in_expected_skipped():
    """R004 真值表：图层不在 OFFICIAL_LAYERS 中 → 跳过（不报）。"""
    ctx = _ctx({"UNKNOWN_LAYER": [_Feat({"CODE": "X-01"})]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 0


def test_r004_layer_empty_skipped():
    """R004 真值表：图层存在但无要素 → 跳过（不报）。"""
    ctx = _ctx({"IMB": []})
    results = check_layer_geom_type(ctx)
    assert len(results) == 0


def test_r004_alias_infra_matches_infrastructure():
    """R004 真值表：INFRA 别名匹配 INFRASTRUCTURE → 按线类型检查。"""
    ctx = _ctx({"INFRA": [_Feat({"CODE": "INF-01"}, GeomType.LINE)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is True


def test_r004_alias_infra_wrong_type_flagged():
    """R004 真值表：INFRA 别名但几何类型错误 → R004 error。"""
    ctx = _ctx({"INFRA": [_Feat({"CODE": "INF-01"}, GeomType.POINT)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].rule_id == "R004"


def test_r004_case_insensitive_layer_match():
    """R004 真值表：图层名大小写不敏感匹配。"""
    ctx = _ctx({"imb": [_Feat({"CODE": "IMB-01"}, GeomType.POINT)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is True


def test_r004_polygon_layer_correct():
    """R004 真值表：ZNRO 多边形类型正确 → 通过。"""
    ctx = _ctx({"ZNRO": [_Feat({"CODE": "ZNRO-01"}, GeomType.POLYGON)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is True


def test_r004_polygon_layer_wrong_type():
    """R004 真值表：ZNRO 点类型错误 → R004 error。"""
    ctx = _ctx({"ZNRO": [_Feat({"CODE": "ZNRO-01"}, GeomType.POINT)]})
    results = check_layer_geom_type(ctx)
    assert len(results) == 1
    assert results[0].passed is False


# ============================================================
# R005_1: SITE(TYPE=PM) 与 ZPM 双向覆盖检查
# ============================================================

def test_r005_1_code_match_passes():
    """R005_1 真值表：同码匹配（SITE.CODE=ZPM.CODE）→ 无问题。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "PM-01", "TYPE": "PM"})],
        "ZPM": [_Feat({"CODE": "PM-01"})],
    })
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_r005_1_ref_pm_linkage_passes():
    """R005_1 真值表：外键匹配（ZPM.REF_PM=SITE.CODE）→ 无问题。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "PM-01", "TYPE": "PM"})],
        "ZPM": [_Feat({"CODE": "ZPM-01", "REF_PM": "PM-01"})],
    })
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_r005_1_broken_ref_pm_flagged_both():
    """R005_1 真值表：REF_PM 指向不存在的 PM → 双向报错。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "PM-01", "TYPE": "PM"})],
        "ZPM": [_Feat({"CODE": "ZPM-01", "REF_PM": "PM-NOWHERE"})],
    })
    issues = check_site_pm_zpm_bidirectional(ctx)
    assert len(issues) == 2
    assert all(i.rule_id == "R005_1" and not i.passed for i in issues)


def test_r005_1_isolated_site_flagged():
    """R005_1 真值表：SITE PM 在 ZPM 中无对应 → 双向报错（PM 孤立 + ZPM 孤立）。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "PM-01", "TYPE": "PM"})],
        "ZPM": [_Feat({"CODE": "PM-02"})],
    })
    issues = check_site_pm_zpm_bidirectional(ctx)
    assert len(issues) == 2
    descs = " ".join(i.error_description for i in issues)
    assert "PM-01" in descs
    assert "PM-02" in descs


def test_r005_1_isolated_zpm_flagged():
    """R005_1 真值表：ZPM 在 SITE 中无对应 → 双向报错。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "PM-02", "TYPE": "PM"})],
        "ZPM": [_Feat({"CODE": "PM-01"})],
    })
    issues = check_site_pm_zpm_bidirectional(ctx)
    assert len(issues) == 2
    descs = " ".join(i.error_description for i in issues)
    assert "PM-01" in descs
    assert "PM-02" in descs


def test_r005_1_mixed_model_all_pass():
    """R005_1 真值表：同码+外键混合模型 → 全部通过。"""
    ctx = _ctx({
        "SITE": [
            _Feat({"CODE": "PM-01", "TYPE": "PM"}),
            _Feat({"CODE": "PM-02", "TYPE": "PM"}),
        ],
        "ZPM": [
            _Feat({"CODE": "ZPM-01", "REF_PM": "PM-01"}),
            _Feat({"CODE": "PM-02"}),
        ],
    })
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_r005_1_no_layers_returns_empty():
    """R005_1 真值表：无 SITE/ZPM 图层 → 返回空。"""
    ctx = _ctx({})
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_r005_1_no_pm_site_returns_empty():
    """R005_1 真值表：SITE 无 TYPE=PM → 仅 ZPM 侧报错（ZPM 无对应 PM）。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "SITE-01", "TYPE": "OTHER"})],
        "ZPM": [_Feat({"CODE": "ZPM-01"})],
    })
    issues = check_site_pm_zpm_bidirectional(ctx)
    assert len(issues) == 1
    assert "ZPM-01" in issues[0].error_description


def test_r005_1_or_semantics_not_and():
    """R005_1 真值表：OR 语义（同码或外键任一满足即通过），不是 AND。"""
    ctx = _ctx({
        "SITE": [_Feat({"CODE": "PM-01", "TYPE": "PM"})],
        "ZPM": [_Feat({"CODE": "ZPM-01", "REF_PM": "PM-01"})],
    })
    # 仅 REF_PM 匹配，同码不匹配 → 仍应通过（OR 语义）
    assert check_site_pm_zpm_bidirectional(ctx) == []


# ============================================================
# R007: 编码唯一性检查（同层/同容器内 CODE 不重复）
# ============================================================

def test_r007_unique_codes_pass():
    """R007 真值表：CODE 唯一 → 无问题。"""
    ctx = _ctx(
        layers={},
        boxes=[
            SimpleNamespace(code="BPE-01", id="box-1", properties={"CODE": "BPE-01"}),
            SimpleNamespace(code="BPE-02", id="box-2", properties={"CODE": "BPE-02"}),
        ],
    )
    assert check_code_duplicate(ctx) == []


def test_r007_duplicate_box_code_flagged():
    """R007 真值表：boxes 内 CODE 重复 → R007 fatal。"""
    ctx = _ctx(
        layers={},
        boxes=[
            SimpleNamespace(code="BPE-01", id="box-1", properties={"CODE": "BPE-01"}),
            SimpleNamespace(code="BPE-01", id="box-2", properties={"CODE": "BPE-01"}),
        ],
    )
    issues = check_code_duplicate(ctx)
    assert len(issues) == 1
    assert issues[0].rule_id == "R007"
    assert issues[0].passed is False
    assert "BPE-01" in issues[0].check_object


def test_r007_duplicate_cable_code_flagged():
    """R007 真值表：cables 内 CODE 重复 → R007 fatal。"""
    ctx = _ctx(
        layers={},
        cables=[
            SimpleNamespace(code="CABLE-01", id="cable-1", properties={"CODE": "CABLE-01"}),
            SimpleNamespace(code="CABLE-01", id="cable-2", properties={"CODE": "CABLE-01"}),
        ],
    )
    issues = check_code_duplicate(ctx)
    assert len(issues) == 1
    assert issues[0].rule_id == "R007"
    assert issues[0].passed is False


def test_r007_cross_layer_same_code_flagged():
    """R007 真值表：不同图层（boxes 容器内）CODE 重复 → R007 fatal。

    当前实现中 boxes 容器包含 BOITE/PTECH/SITE/IMB/ZNRO/ZPM 等，
    跨图层同 CODE 也会被检出（实现语义为 boxes 容器内唯一）。
    """
    ctx = _ctx(
        layers={},
        boxes=[
            SimpleNamespace(code="SHARED-01", id="box-1", properties={"CODE": "SHARED-01"}),
            SimpleNamespace(code="SHARED-01", id="box-2", properties={"CODE": "SHARED-01"}),
        ],
    )
    issues = check_code_duplicate(ctx)
    assert len(issues) == 1
    assert issues[0].rule_id == "R007"


def test_r007_empty_code_skipped():
    """R007 真值表：CODE 为空 → 跳过（不报）。"""
    ctx = _ctx(
        layers={},
        boxes=[
            SimpleNamespace(code=None, id="box-1", properties={"CODE": ""}),
            SimpleNamespace(code=None, id="box-2", properties={}),
        ],
    )
    assert check_code_duplicate(ctx) == []


def test_r007_multiple_duplicates_all_flagged():
    """R007 真值表：多组重复 → 每组分别报。"""
    ctx = _ctx(
        layers={},
        boxes=[
            SimpleNamespace(code="DUP-01", id="box-1", properties={"CODE": "DUP-01"}),
            SimpleNamespace(code="DUP-01", id="box-2", properties={"CODE": "DUP-01"}),
            SimpleNamespace(code="DUP-02", id="box-3", properties={"CODE": "DUP-02"}),
            SimpleNamespace(code="DUP-02", id="box-4", properties={"CODE": "DUP-02"}),
        ],
    )
    issues = check_code_duplicate(ctx)
    assert len(issues) == 2
    assert all(i.rule_id == "R007" for i in issues)


def test_r007_box_and_cable_same_code_both_flagged():
    """R007 真值表：box 与 cable 同名 → 分别报（boxes 和 cables 独立检查）。"""
    ctx = _ctx(
        layers={},
        boxes=[
            SimpleNamespace(code="SAME-01", id="box-1", properties={"CODE": "SAME-01"}),
            SimpleNamespace(code="SAME-01", id="box-2", properties={"CODE": "SAME-01"}),
        ],
        cables=[
            SimpleNamespace(code="SAME-01", id="cable-1", properties={"CODE": "SAME-01"}),
            SimpleNamespace(code="SAME-01", id="cable-2", properties={"CODE": "SAME-01"}),
        ],
    )
    issues = check_code_duplicate(ctx)
    assert len(issues) == 2  # boxes 一组 + cables 一组


def test_r007_no_data_returns_empty():
    """R007 真值表：无 boxes/cables → 返回空。"""
    ctx = _ctx(layers={}, boxes=[], cables=[])
    assert check_code_duplicate(ctx) == []
