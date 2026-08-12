"""规程知识库解析器测试（《施工规程知识库.xlsx》结构）。"""

import tempfile
import zipfile
from pathlib import Path

from openpyxl import Workbook

from design_parser.procedure_reader import (
    find_procedure_files,
    read_procedure_kb,
    search_procedure_kb,
)


def _make_kb(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "PCP安装操作规程"
    ws.append(["施工对象", "工序名称", "操作步骤", "使用材料", "工艺要求",
               "测试要求", "安全要求", "验收标准", "常见错误", "页码及章节来源"])
    ws.append(["PCP接头", "PCP安装", "1.验证RFID\n2.电缆准备", "RFID标签",
               "须由供应商执行", "RFID可读性验证", "接头悬挂安装",
               "RFID可读", "RFID缺失", "第9-11页"])
    ws.append(["光纤电缆", "电缆端接", "1.穿入光器件", "光纤电缆",
               "注意最小弯曲半径", "", "遵守弯曲半径",
               "光纤正确分配", "光纤识别错误", "第12页"])
    wb.save(path)
    wb.close()


def test_find_procedure_files(tmp_path):
    _make_kb(tmp_path / "施工规程知识库.xlsx")
    (tmp_path / "BOM_LIST.xlsx").touch()
    files = find_procedure_files(tmp_path)
    assert len(files) == 1
    assert "规程" in files[0].name


def test_read_procedure_kb(tmp_path):
    p = tmp_path / "施工规程知识库.xlsx"
    _make_kb(p)
    data = read_procedure_kb(p)
    assert len(data["entries"]) == 2
    first = data["entries"][0]
    assert first["施工对象"] == "PCP接头"
    assert first["工序名称"] == "PCP安装"
    assert "页码及章节来源" in first


def test_search_procedure_kb(tmp_path):
    p = tmp_path / "施工规程知识库.xlsx"
    _make_kb(p)
    hit = search_procedure_kb(p, "端接")
    assert len(hit["entries"]) == 1
    assert hit["entries"][0]["工序名称"] == "电缆端接"
    miss = search_procedure_kb(p, "不存在的关键词")
    assert miss["entries"] == []


def test_procedure_kb_endpoint(client):
    tmp = tempfile.mkdtemp(prefix="proc_pkg_")
    kb = Path(tmp) / "施工规程知识库.xlsx"
    _make_kb(kb)
    zip_path = Path(tmp) / "proc_pkg.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.write(kb, kb.name)
    with zip_path.open("rb") as f:
        resp = client.post("/project/load", files={"file": ("proc_pkg.zip", f, "application/zip")})
    assert resp.status_code == 200, resp.text
    pid = resp.json()["data"]["project_id"]

    r = client.get(f"/project/{pid}/procedure-kb")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    # 2026-08-11 起 procedure-kb 优先返回固定官方规程（docs/官方固定数据/施工规程知识库v2.0.xlsx，10 条），
    # 固定文件缺失时回退包内规程文件（2 条）
    assert len(body["data"]["entries"]) >= 2

    r2 = client.get(f"/project/{pid}/procedure-kb", params={"keyword": "端接"})
    assert len(r2.json()["data"]["entries"]) == 1
