"""engineering_data 统一工程对象输出测试（供 BOM / 纤芯分配工作流使用）。

对外格式与 boss 约定一致：
{
  "project_id": "...",
  "project_type": "...",
  "objects": {
    "cable": [...], "boite": [...], "ptech": [...]
  }
}
每种对象只输出其相关字段，缺失字段省略（不输出 null）。
"""

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData

REQUIRED_OBJECT_KEYS = {"cable", "boite", "ptech"}
REQUIRED_FIELD_KEYS = {"code", "longueur", "capacite", "type", "nb_fibre_util", "hauteur_appui"}


def _feature(props):
    return UnifiedFeature(source_layer_name="X", feature_id=0, geometry=None, properties=props)


def test_engineering_data_mapping_from_official_fields():
    """官方字段（LONGUEUR/TYPE_CABLE/NB_FIBRE_U/HAUTEUR_AP 等）正确映射到统一字段。"""
    proj = ProjectData.__new__(ProjectData)
    proj.layers = {
        "CABLE": [_feature({"CODE": "CDI-001", "LONGUEUR": "125.5", "CAPACITE": 24,
                            "TYPE_CABLE": "ADSS", "NB_FIBRE_U": 4})],
        "BOITE": [_feature({"CODE": "B-01", "TYPE": "PBO", "CAPACITE": 12, "NB_FIBRE_U": 2})],
        "PTECH": [_feature({"CODE": "P-01", "TYPE": "appui", "HAUTEUR_AP": "6.2"})],
    }
    data = proj.get_engineering_data()
    objs = data["objects"]
    assert set(objs.keys()) == REQUIRED_OBJECT_KEYS
    assert objs["cable"][0] == {"code": "CDI-001", "longueur": 125.5, "capacite": 24,
                                "type": "ADSS", "nb_fibre_util": 4}
    assert objs["boite"][0] == {"code": "B-01", "capacite": 12, "type": "PBO", "nb_fibre_util": 2}
    assert objs["ptech"][0] == {"code": "P-01", "type": "appui", "hauteur_appui": 6.2}


def test_engineering_data_empty_layers_structure():
    """图层缺失或为空时仍返回固定结构。"""
    proj = ProjectData.__new__(ProjectData)
    proj.layers = {}
    data = proj.get_engineering_data()
    assert set(data["objects"].keys()) == REQUIRED_OBJECT_KEYS
    for arr in data["objects"].values():
        assert arr == []

    proj.layers = {"CABLE": []}
    data = proj.get_engineering_data()
    assert data["objects"]["cable"] == []


def test_engineering_data_in_pipeline(client, upload_survey):
    """/agent/data-pipeline 响应包含 engineering_data（boss 格式：project_id/project_type/objects）。"""
    resp = upload_survey()
    assert resp.status_code == 200
    data = resp.json()
    ed = data["engineering_data"]
    assert set(ed.keys()) == {"project_id", "project_type", "objects"}
    assert ed["project_id"] == data["project_id"]
    assert ed["project_type"] == data["project_type"]
    assert set(ed["objects"].keys()) == REQUIRED_OBJECT_KEYS
    for arr in ed["objects"].values():
        assert isinstance(arr, list)
        for item in arr:
            assert "code" in item
            assert set(item.keys()) <= REQUIRED_FIELD_KEYS


def test_engineering_data_endpoint(client, upload_survey):
    """GET /project/{id}/engineering-data 返回同一 boss 格式。"""
    resp = upload_survey()
    pid = resp.json()["project_id"]
    r2 = client.get(f"/project/{pid}/engineering-data")
    assert r2.status_code == 200
    body = r2.json()
    assert body["success"] is True
    data = body["data"]
    assert set(data.keys()) == {"project_id", "project_type", "objects"}
    assert data["project_id"] == pid
    assert set(data["objects"].keys()) == REQUIRED_OBJECT_KEYS
