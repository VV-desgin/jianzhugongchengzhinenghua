"""官方 SRO TOPO / 单箱页格式（表头不在首行）的纤芯重复占用检出测试。"""

from design_parser.case_checks import find_fiber_core_duplicates


def _official_sro_sheet():
    return [
        ["retour", "SRO-JAD-MAR-0001"],
        ["SRO", None, None, "Type Epissure", None, "Distribution"],
        ["SRO Port", "ODF Code", "ODF Port", None, None, "Section", "Code"],
        [1, "ODF01", 1, "E", None, "0001", "CDI-JAD-MAR-0001"],
        [1, "ODF01", 1, "E", None, "0001", "CDI-JAD-MAR-0001"],  # 重复占用
        [2, "ODF01", 2, "E", None, "0001", "CDI-JAD-MAR-0001"],
    ]


def test_official_sro_topo_header_not_first_row():
    issues = find_fiber_core_duplicates({"SRO-JAD-MAR-0001": _official_sro_sheet()})
    assert any(i["rule_id"] == "R-FIBER-001" for i in issues)
    assert any("ODF01/1" in i["message"] for i in issues)


def test_official_single_box_header_not_first_row():
    sheet = [
        ["retour", "PBO-JAD-MAR-0001"],
        ["Distribution", None, None, None, None, "Type Epissure"],
        ["Entrée", "Capacité", "N°", "T", "F"],
        ["CDI-JAD-MAR-0009", "24FO", 1, 1, 1],
        ["CDI-JAD-MAR-0009", "24FO", 1, 1, 1],  # 重复 N°1
        ["CDI-JAD-MAR-0009", "24FO", 2, 1, 2],
    ]
    issues = find_fiber_core_duplicates({"PBO-JAD-MAR-0001": sheet})
    assert any("N°1" in i["message"] for i in issues)


def test_normal_case_still_works():
    sheet = [
        ["所属节点", "托盘编号", "光分路器", "IN", "OUT"],
        ["PBO-01", "托盘1", "无", "1", "Cable-001"],
        ["PBO-01", "托盘1", "无", "1", "Cable-002"],
        ["PBO-01", "托盘1", "SP#1", "1", "Cable-003"],
    ]
    issues = find_fiber_core_duplicates({"纤芯连接与分配": sheet})
    assert len(issues) == 1


def test_data_pipeline_exposes_fiber_tables(client):
    """data-pipeline 的 engineering_data 应输出 fiber_tables（供 Dify 纤芯工具 V0.5 使用）。"""
    from pathlib import Path
    case = Path(__file__).resolve().parents[1] / "tests" / "data" / "standard_cases" / "纤芯重复占用案例.xlsx"
    with open(case, "rb") as f:
        resp = client.post(
            "/agent/data-pipeline",
            files={"file": (case.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            data={"excel_limit": "0", "pdf_chars": "0", "include_tables": "false"},
        )
    assert resp.status_code == 200
    data = resp.json()
    ft = (data.get("engineering_data") or {}).get("fiber_tables") or []
    assert any(t.get("sheet") == "纤芯连接与分配" for t in ft), ft
