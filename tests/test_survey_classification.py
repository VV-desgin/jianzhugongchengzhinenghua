"""任务单要求：test_survey_classification —— 官方场勘包识别为 survey_design。"""


def test_survey_classification(client, upload_survey):
    resp = upload_survey()
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["project_type"] == "survey_design"

    # 官方包 P0 关键计数
    counts = {layer["name"]: layer["feature_count"] for layer in data["layers"]}
    assert counts.get("IMB") == 51
    assert counts.get("SITE") == 1
    assert counts.get("BOITE") == 0
    assert counts.get("CABLE") == 0
    assert counts.get("PTECH") == 0
