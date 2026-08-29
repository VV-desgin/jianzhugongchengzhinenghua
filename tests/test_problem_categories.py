# -*- coding: utf-8 -*-
"""问题分类映射：新规则必须有显式分类，不得全部落入默认「工程合理性」。"""
from design_parser.problem_categories import problem_category_for


def test_new_rules_have_explicit_categories():
    assert problem_category_for("R-GIS-007") == "spatial_safety"
    assert problem_category_for("R-SAFE-010") == "spatial_safety"
    assert problem_category_for("R-SAFE-011") == "spatial_safety"
    assert problem_category_for("R-SAFE-012") == "spatial_safety"
    assert problem_category_for("R-FIBER-003") == "resource"
    assert problem_category_for("R-FIBER-002") == "resource"
    assert problem_category_for("R-LIFE-001") == "logic_consistency"
    assert problem_category_for("R034") == "resource"
    assert problem_category_for("R031") == "data_completeness"
    assert problem_category_for("R030") == "resource"
    assert problem_category_for("R029") == "spatial_safety"
    assert problem_category_for("R006_3") == "spatial_safety"
    assert problem_category_for("R005_1") == "logic_consistency"
    assert problem_category_for("R007_1") == "resource"
    assert problem_category_for("R007_2") == "resource"
