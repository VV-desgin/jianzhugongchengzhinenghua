"""验收要求：test_recursive_file_scan —— 递归发现嵌套目录内 SHP 配套文件，且不误报缺失。"""

REQUIRED_FILES = {
    "IMB": {"shp", "shx", "dbf", "prj"},
    "SITE": {"shp", "shx", "dbf", "prj"},
    "BOITE": {"shp", "shx", "dbf", "prj"},
    "CABLE": {"shp", "shx", "dbf", "prj"},
    "PTECH": {"shp", "shx", "dbf", "prj"},
    "INFRASTRUCTURE": {"shp", "shx", "dbf", "prj"},
    "ZNRO": {"shp", "shx", "dbf", "prj"},
    "ZPM": {"shp", "shx", "dbf", "prj"},
}


def _basenames(entries):
    return {e.replace("\\", "/").rsplit("/", 1)[-1].upper() for e in entries}


def test_recursive_file_scan(client, upload_survey):
    resp = upload_survey()
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    # 1) 嵌套目录（Plan_de_récolement/Shape/...）中的配套文件必须全部被递归发现
    inside = data["file_info"].get("files_inside", [])
    basenames = _basenames(inside)
    for layer, exts in REQUIRED_FILES.items():
        for ext in exts:
            assert f"{layer}.{ext}".upper() in basenames, f"递归扫描未发现 {layer}.{ext}"

    # 2) 已存在文件不得误报缺失：R001 不应产生任何失败
    r001_failures = [i for i in data["review"]["issues"] if i["rule_id"] == "R001"]
    assert r001_failures == []

    # 3) 完整性检查的缺失清单应为空
    assert not data["file_info"].get("missing_shp_parts")
