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


def test_different_filename_same_bytes_misses_cache(client):
    """缓存键必须含文件名：同字节不同文件名不得复用旧 project_name/project_id。"""
    _pipeline_cache.clear()
    src = CASES / "正确工程案例.xlsx"
    data = {"compact": "false"}
    with src.open("rb") as f1, src.open("rb") as f2:
        a = client.post("/agent/data-pipeline", data=data, files={"file": ("正确工程案例.xlsx", f1, "")}, timeout=300).json()
        b = client.post("/agent/data-pipeline", data=data, files={"file": ("renamed.xlsx", f2, "")}, timeout=300).json()
    assert a["success"] and b["success"]
    assert a["project_id"] != b["project_id"]
    assert a["project_name"] != b["project_name"]


def test_lru_hit_refreshes_recency(monkeypatch, client):
    """缓存命中必须刷新 LRU 顺序：A 命中后，淘汰应发生在最久未使用的 B 而非 A。"""
    import api
    monkeypatch.setattr(api, "_PIPELINE_CACHE_MAX_ENTRIES", 2)
    _pipeline_cache.clear()
    data = {"compact": "false"}
    def up(fname):
        with (CASES / fname).open("rb") as f:
            return client.post("/agent/data-pipeline", data=data, files={"file": (fname, f, "")}, timeout=300).json()
    a1 = up("正确工程案例.xlsx")
    up("编码重复案例.xlsx")
    a2 = up("正确工程案例.xlsx")        # 命中 A → 刷新 recency
    assert a2["project_id"] == a1["project_id"]
    up("孤立设备案例.xlsx")            # 第 3 个 → 应淘汰 B（编码重复）
    a3 = up("正确工程案例.xlsx")        # A 应仍在缓存
    assert a3["project_id"] == a1["project_id"]
    assert len(_pipeline_cache) <= 2
