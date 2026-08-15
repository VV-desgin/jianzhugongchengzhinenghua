"""Task A4: engineering_data 增加 reuse（利旧）字段测试（TDD 先行）。"""
from design_parser.project_data import ENGINEERING_OBJECTS, _normalize_reuse


def test_engineering_objects_include_reuse_key():
    for obj_key in ("cable", "boite", "ptech", "site", "infrastructure"):
        assert "reuse" in ENGINEERING_OBJECTS[obj_key]


def test_normalize_reuse_values():
    assert _normalize_reuse("OUI") == "yes"
    assert _normalize_reuse("YES") == "yes"
    assert _normalize_reuse("REUTILISATION") == "yes"
    assert _normalize_reuse("1") == "yes"
    assert _normalize_reuse("利旧") == "yes"
    assert _normalize_reuse("NON") == "no"
    assert _normalize_reuse(None) == "no"
