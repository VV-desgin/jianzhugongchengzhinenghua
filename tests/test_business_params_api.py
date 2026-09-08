"""Task A3: /agent/business-params 接口测试（TDD 先行）。"""
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_business_params_endpoint():
    r = client.get("/agent/business-params")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["fiber_policy"]["required_cores_default"] == 4
    assert data["_meta"]["source"].startswith("依据")


def test_data_pipeline_response_carries_business_params():
    """data-pipeline 响应顶层必须携带 business_params，供 Dify 总控透传 BOM 工具。"""
    from pathlib import Path
    import pytest

    fixture = Path(__file__).resolve().parent / "data" / "regression" / "TC-01_正确工程案例.xlsx"
    if not fixture.exists():
        pytest.skip("TC-01 fixture missing")
    with open(fixture, "rb") as fh:
        r = client.post("/agent/data-pipeline", files={"file": (fixture.name, fh, "application/octet-stream")})
    assert r.status_code == 200
    j = r.json()
    assert j.get("success") is True
    bp = j.get("business_params") or {}
    assert bp.get("fiber_policy", {}).get("required_cores_default") == 4
