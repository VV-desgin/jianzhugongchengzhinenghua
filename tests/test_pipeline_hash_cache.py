"""有界哈希结果缓存：同一包（文件 SHA256 + 参数 + 规则版本）TTL 内秒回，project_id 复用。

上限：32 条 / 1 小时 / 64MB（LRU），避免无限堆积；规则版本号参与 key，代码变更自动失效。
"""

from pathlib import Path

from fastapi.testclient import TestClient

from api import _pipeline_cache, app

CASES = Path(__file__).resolve().parents[1] / "tests" / "data" / "standard_cases"


def _upload(client, fname, compact=False, include_tables=False):
    data = {"compact": "true" if compact else "false", "include_tables": "true" if include_tables else "false"}
    with (CASES / fname).open("rb") as f:
        r = client.post("/agent/data-pipeline", data=data, files={"file": (fname, f, "")}, timeout=300)
    assert r.status_code == 200, r.text[:200]
    return r.json()


def test_repeat_upload_hits_cache_same_project():
    _pipeline_cache.clear()
    with TestClient(app) as c:
        a = _upload(c, "正确工程案例.xlsx")
        b = _upload(c, "正确工程案例.xlsx")
    assert a["success"] and b["success"]
    assert a["project_id"] == b["project_id"]   # 命中缓存，复用工程
    assert a["request_id"] != b["request_id"]   # request_id 仍唯一
    assert a["review"] == b["review"]


def test_cache_key_includes_compact_param():
    _pipeline_cache.clear()
    with TestClient(app) as c:
        a = _upload(c, "正确工程案例.xlsx", compact=False)
        b = _upload(c, "正确工程案例.xlsx", compact=True)
    assert a["project_id"] != b["project_id"]   # 参数不同 → 不同 key


def test_different_file_misses_cache():
    _pipeline_cache.clear()
    with TestClient(app) as c:
        a = _upload(c, "正确工程案例.xlsx")
        b = _upload(c, "编码重复案例.xlsx")
    assert a["project_id"] != b["project_id"]


def test_cache_bounded_eviction(monkeypatch):
    import api
    monkeypatch.setattr(api, "_PIPELINE_CACHE_MAX_ENTRIES", 2)
    _pipeline_cache.clear()
    with TestClient(app) as c:
        a = _upload(c, "正确工程案例.xlsx")
        _upload(c, "编码重复案例.xlsx")
        _upload(c, "孤立设备案例.xlsx")        # 第 3 个 → 淘汰第 1 个
        d = _upload(c, "正确工程案例.xlsx")     # 应 miss（新 project_id）
    assert d["project_id"] != a["project_id"]
    assert len(_pipeline_cache) <= 2


def test_cache_ttl_expiry(monkeypatch):
    import api
    monkeypatch.setattr(api, "_PIPELINE_CACHE_TTL_S", -1)
    _pipeline_cache.clear()
    with TestClient(app) as c:
        a = _upload(c, "正确工程案例.xlsx")
        b = _upload(c, "正确工程案例.xlsx")
    assert a["project_id"] != b["project_id"]   # TTL 过期 → miss
