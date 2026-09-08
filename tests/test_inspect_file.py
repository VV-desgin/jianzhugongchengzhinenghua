"""单文件识别上传接口测试（/agent/inspect-file）。"""

import tempfile
import zipfile
from pathlib import Path

from openpyxl import Workbook


def _make_xlsx(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Material Code", "物料名称", "数量"])
    ws.append(["MAT-001", "光分路器", 1])
    wb.save(path)
    wb.close()


def test_inspect_excel_bom(client):
    tmp = tempfile.mkdtemp(prefix="inspect_")
    xlsx = Path(tmp) / "BOM_LIST.xlsx"
    _make_xlsx(xlsx)
    with xlsx.open("rb") as f:
        r = client.post("/agent/inspect-file", files={"file": ("BOM_LIST.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["file_name"] == "BOM_LIST.xlsx"
    assert data["file_category"] == "BOM表"
    assert data["is_archive"] is False


def test_inspect_pdf(client):
    tmp = tempfile.mkdtemp(prefix="inspect_")
    pdf = Path(tmp) / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    with pdf.open("rb") as f:
        r = client.post("/agent/inspect-file", files={"file": ("doc.pdf", f, "application/pdf")})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["file_category"] == "PDF文档"


def test_inspect_zip_archive(client):
    tmp = tempfile.mkdtemp(prefix="inspect_")
    xlsx = Path(tmp) / "BOM_LIST.xlsx"
    _make_xlsx(xlsx)
    zp = Path(tmp) / "pkg.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.write(xlsx, "BOM_LIST.xlsx")
    with zp.open("rb") as f:
        r = client.post("/agent/inspect-file", files={"file": ("pkg.zip", f, "application/zip")})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["is_archive"] is True
    assert data["archive_type"] == "zip"
    assert any("BOM_LIST" in n for n in data.get("files_inside", []))


def test_unified_error_response(client):
    """未知项目返回统一错误结构（success=false + error.code/message）。"""
    r = client.get("/project/not-exist/relations")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == 404
    assert body["error"]["message"]
