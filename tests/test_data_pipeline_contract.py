"""验收要求：test_data_pipeline_contract —— /agent/data-pipeline 返回字段和数据类型稳定。"""

REQUIRED_TOP_KEYS = [
    "success", "project_id", "project_name", "project_type",
    "request_id",
    "layers", "summary", "review", "warnings", "errors",
    "engineering_data",
]

REQUIRED_LAYER_KEYS = ["name", "exists", "feature_count", "geometry_type", "source_layer_name"]

REQUIRED_ISSUE_KEYS = ["rule_id", "object_type", "object_id", "field", "severity", "message", "source"]


def test_data_pipeline_contract(client, upload_survey):
    resp = upload_survey()
    assert resp.status_code == 200
    data = resp.json()

    # 顶层契约字段
    for key in REQUIRED_TOP_KEYS:
        assert key in data, f"缺少顶层字段 {key}"

    assert isinstance(data["success"], bool)
    assert isinstance(data["project_id"], str) and data["project_id"]
    assert isinstance(data["request_id"], str) and data["request_id"]
    assert isinstance(data["project_name"], str)
    assert data["project_type"] in {"survey_design", "full_design", "as_built", "unknown"}

    # summary 与 layers 一致
    assert isinstance(data["summary"]["layer_count"], int)
    assert isinstance(data["summary"]["object_count"], int)
    assert data["summary"]["layer_count"] == len(data["layers"])
    assert data["summary"]["object_count"] == sum(l["feature_count"] for l in data["layers"])

    # review 契约：success 与业务审查通过必须分开
    assert set(data["review"].keys()) == {"total_rules", "passed_rules", "failed_rules", "warning_rules", "issues", "categories"}
    assert data["review"]["total_rules"] == data["review"]["passed_rules"] + data["review"]["failed_rules"] + data["review"]["warning_rules"]
    assert isinstance(data["review"]["issues"], list)
    for issue in data["review"]["issues"]:
        for key in REQUIRED_ISSUE_KEYS:
            assert key in issue, f"review.issues 缺少字段 {key}"

    # layers 契约
    for layer in data["layers"]:
        for key in REQUIRED_LAYER_KEYS:
            assert key in layer, f"layers[] 缺少字段 {key}"
        assert isinstance(layer["exists"], bool)
        assert isinstance(layer["feature_count"], int)

    assert isinstance(data["warnings"], list)
    assert isinstance(data["errors"], list)


def test_validate_url_host_rejects_loopback_private_and_bad_scheme():
    """file_url 主机校验：本机/内网/保留地址/非 http(s) 必须拒绝（防 SSRF）。"""
    import pytest
    from fastapi import HTTPException
    from api import _validate_url_host
    for url in ("http://127.0.0.1/x.zip", "http://localhost/x.zip", "http://10.1.2.3/x.zip",
                 "http://169.254.169.254/latest/meta-data", "file:///etc/passwd"):
        with pytest.raises(HTTPException):
            _validate_url_host(url)


def test_file_url_loopback_rejected_by_endpoint(client):
    """data-pipeline 的 file_url 传内网地址返回 400 禁止访问，且不触发 asyncio.run 崩溃。"""
    r = client.post("/agent/data-pipeline", data={"file_url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 400
    msg = (r.json().get("error") or {}).get("message") or ""
    assert "禁止访问" in msg
    assert "asyncio.run" not in msg


def test_upload_size_cap_rejected(client, monkeypatch):
    """上传超过 _MAX_UPLOAD_BYTES 必须 413 拒绝，不得全量读入内存。"""
    import api as api_module
    monkeypatch.setattr(api_module, "_MAX_UPLOAD_BYTES", 64)
    r = client.post("/agent/inspect-file",
                       files={"file": ("big.xlsx", b"x" * 200, "application/octet-stream")})
    assert r.status_code == 413
