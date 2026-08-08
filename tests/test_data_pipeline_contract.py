"""验收要求：test_data_pipeline_contract —— /agent/data-pipeline 返回字段和数据类型稳定。"""

REQUIRED_TOP_KEYS = [
    "success", "project_id", "project_name", "project_type",
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
    assert isinstance(data["project_name"], str)
    assert data["project_type"] in {"survey_design", "full_design", "as_built", "unknown"}

    # summary 与 layers 一致
    assert isinstance(data["summary"]["layer_count"], int)
    assert isinstance(data["summary"]["object_count"], int)
    assert data["summary"]["layer_count"] == len(data["layers"])
    assert data["summary"]["object_count"] == sum(l["feature_count"] for l in data["layers"])

    # review 契约：success 与业务审查通过必须分开
    assert set(data["review"].keys()) == {"total_rules", "passed_rules", "failed_rules", "issues"}
    assert data["review"]["total_rules"] == data["review"]["passed_rules"] + data["review"]["failed_rules"]
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
