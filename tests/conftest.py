"""pytest 公共夹具：内存 FastAPI 客户端与官方场勘包定位。"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    """内存测试客户端，等价于启动后的 /agent/data-pipeline 服务。"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def survey_zip_path():
    """定位官方《场勘设计图.zip》，找不到时跳过相关集成测试。"""
    candidates = []
    env = os.environ.get("SURVEY_ZIP", "").strip()
    if env:
        candidates.append(Path(env))
    candidates.append(PROJECT_ROOT / "tests" / "data" / "场勘设计图.zip")
    for p in candidates:
        if p.is_file():
            return p
    pytest.skip("未找到官方场勘设计图.zip：请放置到 tests/data/ 或设置 SURVEY_ZIP 环境变量")


@pytest.fixture(scope="session")
def upload_survey(client, survey_zip_path):
    """上传官方场勘包并返回 /agent/data-pipeline 的 Response。"""

    def _upload():
        with survey_zip_path.open("rb") as f:
            return client.post(
                "/agent/data-pipeline",
                files={"file": ("场勘设计图.zip", f, "application/zip")},
            )

    return _upload
