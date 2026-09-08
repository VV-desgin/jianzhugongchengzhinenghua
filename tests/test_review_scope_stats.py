"""P1-07/P2-01：审查四口径统计与对象引用词边界匹配。"""

from api import _review_scope_stats, resolve_object_ref


def test_review_scope_stats_four_levels_consistent():
    stats = _review_scope_stats(
        "完整设计图",
        ["CABLE", "BOITE", "PTECH"],
        {"R001", "R005", "R-GIS-007"},
        18,
        True,
        "",
    )
    assert stats["requirement_count"] == 39
    assert stats["registered_rule_count"] >= stats["applicable_rule_count"]
    assert stats["applicable_rule_count"] >= stats["executed_rule_count"]
    assert stats["executed_instance_count"] == 18
    assert stats["spatial_modules_executed"] is True
    assert stats["spatial_skip_reason"] == ""


def test_review_scope_stats_spatial_skipped_without_layers():
    stats = _review_scope_stats("完整设计图", [], set(), 0, False, "无 GIS 图层")
    assert stats["spatial_modules_executed"] is False
    assert stats["spatial_skip_reason"].startswith("无 GIS 图层")


def test_object_ref_does_not_match_prefix_codes():
    lookup = {"C-1": "cable:C-1", "C-10": "cable:C-10"}
    assert resolve_object_ref(("C-1 与 PTC 冲突", ""), lookup) == "cable:C-1"
    assert resolve_object_ref(("C-10 与 PTC 冲突", ""), lookup) == "cable:C-10"
    assert resolve_object_ref(("C-100 与 PTC 冲突", ""), lookup) == ""


def test_object_ref_fallback_used_when_no_code_match():
    lookup = {"C-1": "cable:C-1"}
    assert resolve_object_ref(("规则执行异常", ""), lookup, "cable:C-1") == "cable:C-1"
