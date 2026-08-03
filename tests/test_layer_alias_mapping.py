"""任务单要求：test_layer_alias_mapping —— INFRA/INFRASTRUCTURE 等别名统一为标准名。"""

STANDARD_LAYERS = ["IMB", "SITE", "BOITE", "CABLE", "PTECH", "INFRASTRUCTURE", "ZNRO", "ZPM"]


def test_layer_alias_mapping(client, upload_survey):
    resp = upload_survey()
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    layers = data["layers"]
    names = [layer["name"] for layer in layers]

    # 8 个官方标准图层必须可追溯
    for std in STANDARD_LAYERS:
        assert std in names, f"缺少标准图层 {std}"

    # 对外统一使用 INFRASTRUCTURE，不允许 INFRA 作为标准名泄漏
    assert "INFRA" not in names

    # 每个图层都必须保留原始名称
    for layer in layers:
        assert layer.get("source_layer_name"), f"{layer['name']} 缺少 source_layer_name"

    # INFRASTRUCTURE 的原始名只允许是标准名或其别名
    infra = next(layer for layer in layers if layer["name"] == "INFRASTRUCTURE")
    assert infra["source_layer_name"].upper() in ("INFRASTRUCTURE", "INFRA")
