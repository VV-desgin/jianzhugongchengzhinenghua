"""无法识别字段映射建议接口测试（P0-3：collect_unrecognized_fields 接入 API）。"""

import api
from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData


def _feature(props):
    return UnifiedFeature(source_layer_name="X", feature_id=0, geometry=None, properties=props)


def _make_proj():
    proj = ProjectData.__new__(ProjectData)
    proj.layers = {
        "CABLE": [_feature({"CODE": "CDI-001", "FIBER_COUNT": 24,
                            "LONGUEUR": "125.5", "FABRIQUANT": "MAKER"})],
        "BOITE": [_feature({"CODE": "B-01", "TYPE": "PBO", "CODE_PTC": "PTC-1"})],
        "UNKNOWN_LAYER": [_feature({"FOO": 1})],
    }
    return proj


def test_suggest_unrecognized_field_mappings():
    fields = api.suggest_unrecognized_field_mappings(_make_proj())
    by_key = {(e["layer"], e["field"]): e for e in fields}

    # FABRIQUANT 与 field_map 中候选 FABRICANT 相似 -> 模糊建议
    fab = by_key[("CABLE", "FABRIQUANT")]
    assert fab["suggested_standard_field"] == "FABRICANT"
    assert fab["suggestion_source"] == "field_map_fuzzy"
    assert fab["known_official_field"] is True

    # LONGUEUR 是官方字段（field_lengths/required_fields 已登记）但未映射
    lg = by_key[("CABLE", "LONGUEUR")]
    assert lg["suggested_standard_field"] is None
    assert lg["known_official_field"] is True

    # CODE_PTC 官方字段已登记
    ptc = by_key[("BOITE", "CODE_PTC")]
    assert ptc["known_official_field"] is True

    # 未配置图层 -> 无法建议，且非官方字段
    foo = by_key[("UNKNOWN_LAYER", "FOO")]
    assert foo["suggested_standard_field"] is None
    assert foo["known_official_field"] is False

    # 已识别字段（CODE/FIBER_COUNT/TYPE）不应出现在列表中
    assert ("CABLE", "CODE") not in by_key
    assert ("CABLE", "FIBER_COUNT") not in by_key
    assert ("BOITE", "TYPE") not in by_key


def test_collect_unrecognized_fields_compat():
    """原 collect_unrecognized_fields 行为保持不变（layer/field 二元组）。"""
    fields = api.collect_unrecognized_fields(_make_proj())
    keys = {(e["layer"], e["field"]) for e in fields}
    assert ("CABLE", "FABRIQUANT") in keys
    assert ("BOITE", "CODE_PTC") in keys
    assert ("UNKNOWN_LAYER", "FOO") in keys
    assert ("CABLE", "CODE") not in keys


def test_unrecognized_fields_endpoint(client):
    proj = _make_proj()
    pid = "uf-test-001"
    api.projects[pid] = proj
    try:
        r = client.get(f"/project/{pid}/unrecognized-fields")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        data = body["data"]
        assert data["project_id"] == pid
        assert data["count"] == len(data["unrecognized_fields"])
        by_key = {(e["layer"], e["field"]): e for e in data["unrecognized_fields"]}
        assert ("CABLE", "FABRIQUANT") in by_key
        assert ("UNKNOWN_LAYER", "FOO") in by_key
    finally:
        api.projects.pop(pid, None)


def test_unrecognized_fields_endpoint_empty(client):
    proj = ProjectData.__new__(ProjectData)
    proj.layers = {}
    pid = "uf-test-empty"
    api.projects[pid] = proj
    try:
        r = client.get(f"/project/{pid}/unrecognized-fields")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 0
        assert data["unrecognized_fields"] == []
    finally:
        api.projects.pop(pid, None)
