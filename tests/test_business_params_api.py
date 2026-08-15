"""Task A3: /agent/business-params 接口测试（TDD 先行）。"""
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_business_params_endpoint():
    r = client.get("/agent/business-params")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["fiber_policy"]["required_cores_default"] == 4
    assert data["_meta"]["source"].startswith("行业参考默认值")
