"""验收要求：test_invalid_archive —— 损坏压缩包返回结构化错误，不导致服务崩溃。"""


def test_invalid_archive(client, tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"this is not a zip archive - intentionally corrupted for testing")

    with broken.open("rb") as f:
        resp = client.post(
            "/agent/data-pipeline",
            files={"file": ("broken.zip", f, "application/zip")},
        )

    # 返回结构化错误而非 500 / Traceback
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert isinstance(data["errors"], list) and data["errors"]
    assert "Traceback" not in resp.text

    # 服务未崩溃，仍可继续提供健康检查
    assert client.get("/health").status_code == 200
