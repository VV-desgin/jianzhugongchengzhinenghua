"""任务单要求：test_health —— 启动后 /health 返回 200 和固定 JSON。"""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
