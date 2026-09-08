"""验收要求：test_empty_layers_preserved —— 空图层必须存在于 layers 返回值中。"""

EMPTY_LAYERS = ["BOITE", "CABLE", "PTECH", "INFRASTRUCTURE", "ZNRO", "ZPM"]


def test_empty_layers_preserved(client, upload_survey):
    resp = upload_survey()
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    layers = {layer["name"]: layer for layer in data["layers"]}
    for name in EMPTY_LAYERS:
        assert name in layers, f"空图层 {name} 不应被跳过"
        assert layers[name]["exists"] is True
        assert layers[name]["feature_count"] == 0
