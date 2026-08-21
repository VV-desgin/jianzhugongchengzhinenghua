"""B6 施工指令后端素材：construction-kb（官方施工规程 v2.0 + 物料-工序映射表）。

GET /project/{id}/construction-kb?object_type=&material_code=
返回：procedures（工序级作业卡素材）+ materials（物料-工序映射行）+ warnings。
"""

from pathlib import Path

from design_parser.construction_kb import get_construction_kb

REQUIRED_PROC_KEYS = {
    "index", "object", "name", "steps", "materials",
    "process_requirements", "test_requirements", "safety_requirements",
    "acceptance_criteria", "common_errors", "source",
}


def test_procedures_loaded_from_fixed_kb():
    data = get_construction_kb()
    procs = data["procedures"]
    assert len(procs) >= 10, "官方施工规程 v2.0 应为 10 条工序"
    assert REQUIRED_PROC_KEYS.issubset(procs[0].keys()), procs[0].keys()
    assert ("PCP" in procs[0]["object"]) or ("PCP" in procs[0]["name"])


def test_material_lookup_by_code():
    data = get_construction_kb(material_code="500003800")
    mats = data["materials"]
    assert any(m["material_code"] == "500003800" for m in mats)
    assert all(m["procedure"] for m in mats)


def test_object_type_filter_limits_procedures():
    all_data = get_construction_kb()
    pcp_data = get_construction_kb(object_type="PCP")
    assert 0 < len(pcp_data["procedures"]) <= len(all_data["procedures"])


def test_unknown_code_empty_with_warning():
    data = get_construction_kb(material_code="NO-SUCH-CODE")
    assert data["materials"] == []
    assert any("未匹配" in w for w in data["warnings"])


def test_missing_kb_dir_returns_empty_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("DESIGN_PARSER_FIXED_DATA_DIR", str(tmp_path))
    data = get_construction_kb()
    assert data["procedures"] == [] and data["materials"] == []
    assert data["warnings"]


def test_endpoint_contract():
    from fastapi.testclient import TestClient

    from api import app

    case = Path(__file__).resolve().parents[1] / "tests" / "data" / "standard_cases" / "正确工程案例.xlsx"
    with TestClient(app) as c:
        with case.open("rb") as f:
            r = c.post("/agent/data-pipeline", files={"file": ("正确工程案例.xlsx", f, "")}, timeout=300)
        assert r.status_code == 200
        pid = r.json()["project_id"]
        g = c.get(f"/project/{pid}/construction-kb?object_type=PCP")
        assert g.status_code == 200
        body = g.json()
        assert body["success"] is True
        assert body["data"]["project_id"] == pid
        assert "procedures" in body["data"] and body["data"]["procedures"]
        assert "materials" in body["data"] and "warnings" in body["data"]
