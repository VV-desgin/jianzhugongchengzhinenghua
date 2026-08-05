"""上下游关系建模测试（CABLE.ORIGINE/EXTREMITE → 设备对象，引用字段，距离统计）。"""

from shapely.geometry import LineString, Point

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData


def _feat(layer, fid, geom, props, crs="EPSG:4326"):
    return UnifiedFeature(source_layer_name=layer, feature_id=fid,
                          geometry=geom, properties=props, original_crs=crs)


def _make_proj():
    proj = ProjectData.__new__(ProjectData)
    proj.layers = {
        "CABLE": [
            _feat("CABLE", 0, LineString([(0.0, 0.0), (0.001, 0.001)]),
                  {"CODE": "CDI-001", "ORIGINE": "B-1", "EXTREMITE": "P-1"}),
            _feat("CABLE", 1, LineString([(0.0, 0.0), (0.002, 0.002)]),
                  {"CODE": "CDI-002", "ORIGINE": "B-1", "EXTREMITE": "GHOST-9"}),
        ],
        "BOITE": [_feat("BOITE", 0, Point(0.0, 0.0),
                        {"CODE": "B-1", "REF_NRO": "NRO-1", "REF_PM": "PM-1"})],
        "PTECH": [_feat("PTECH", 0, Point(0.0015, 0.0015), {"CODE": "P-1"})],
    }
    return proj


def test_cable_edges_resolved_and_unresolved():
    data = _make_proj().get_relations()
    edges = {e["cable_code"]: e for e in data["cable_edges"]}
    assert edges["CDI-001"]["upstream"]["code"] == "B-1"
    assert edges["CDI-001"]["upstream"]["layer"] == "BOITE"
    assert edges["CDI-001"]["downstream"]["code"] == "P-1"
    assert edges["CDI-001"]["downstream"]["layer"] == "PTECH"
    # CDI-002 下游引用不存在的对象 → unresolved_refs
    assert any(r["cable_code"] == "CDI-002" and r["side"] == "downstream"
               and r["code"] == "GHOST-9" for r in data["unresolved_refs"])


def test_distances_and_stats():
    data = _make_proj().get_relations()
    stats = data["distance_stats"]
    assert stats["count"] == 3  # 三条可计算距离（CDI-001 两端 + CDI-002 起点）
    assert stats["min_m"] == 0.0
    assert stats["max_m"] > 0  # PTECH 距端点约 55 米（0.0005 度）
    # 端点重合的对象距离应为 0
    edges = {e["cable_code"]: e for e in data["cable_edges"]}
    assert edges["CDI-001"]["upstream"]["distance_m"] == 0.0


def test_references_and_index():
    data = _make_proj().get_relations()
    refs = [r for r in data["references"] if r["layer"] == "BOITE"]
    assert refs[0]["code"] == "B-1"
    assert refs[0]["ref_nro"] == "NRO-1"
    assert refs[0]["ref_pm"] == "PM-1"
    assert data["objects_indexed"]["BOITE"] == 1
    assert data["objects_indexed"]["PTECH"] == 1


def test_relations_empty_structure(client):
    """无 GIS 图层的项目返回空结构而非报错。"""
    import tempfile
    import zipfile
    from pathlib import Path

    tmp = tempfile.mkdtemp(prefix="rel_pkg_")
    zip_path = Path(tmp) / "empty_pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("readme.txt", "no layers")
    with zip_path.open("rb") as f:
        resp = client.post("/project/load", files={"file": ("empty_pkg.zip", f, "application/zip")})
    assert resp.status_code == 200, resp.text
    pid = resp.json()["data"]["project_id"]

    r = client.get(f"/project/{pid}/relations")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    data = body["data"]
    assert data["project_id"] == pid
    assert data["objects_indexed"] == {}
    assert data["cable_edges"] == []
    assert data["distance_stats"]["count"] == 0
