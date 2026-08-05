"""P0-2：纤芯重复占用规则（R-FIBER-001）接入正式规则引擎。

- case_checks.find_fiber_core_duplicates 为公共检测函数（案例逻辑）；
- 规则引擎 check_fiber_core_duplicate 读取项目内纤芯 Excel 表执行；
- 注册进 ALL_RULES/RULE_IDS/SEVERITY_MAP 后，run_rule / run_all_rules 自动包含。
"""
import shutil
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from design_parser.project_data import ProjectData
from design_parser.rule_engine import ALL_RULES, RULE_IDS, SEVERITY_MAP

CASE_DIR = Path(__file__).resolve().parents[1] / "tests" / "data" / "standard_cases"


def _make_fiber_xlsx(path: Path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "纤芯连接与分配"
    ws.append(["所属节点", "托盘编号", "光分路器", "IN", "OUT"])
    for r in rows:
        ws.append(r)
    wb.save(path)
    wb.close()


def _stub_proj(temp_dir: Path):
    proj = ProjectData.__new__(ProjectData)
    proj.layers = {}
    proj.qgs = None
    proj.package = SimpleNamespace(temp_dir=str(temp_dir))
    proj.outer_package = None
    proj.inner_packages = []
    proj._rule_library = {}
    proj.get_unified_objects = lambda name: []
    proj.get_rule_library = lambda: {}
    return proj


def test_registered_in_rule_engine():
    assert "R-FIBER-001" in ALL_RULES
    assert callable(ALL_RULES["R-FIBER-001"])
    assert RULE_IDS.get("FIBER_CORE_DUPLICATE") == "R-FIBER-001"
    assert SEVERITY_MAP.get("R-FIBER-001") == "error"


def test_no_fiber_table_no_results(tmp_path):
    proj = _stub_proj(tmp_path)
    assert proj.run_rule("R-FIBER-001") == []


def test_duplicate_detected_via_run_rule(tmp_path):
    xlsx = tmp_path / "纤芯分配表.xlsx"
    _make_fiber_xlsx(xlsx, [
        ("BPE-01", "灰分盘 01", "SP#1 (2:4)", "Cable-001 Core 1", "Cable-002 Core 1"),
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 5", "Parking area"),
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 5", "Cable-007 Core 1"),
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 5", "Cable-008 Core 1"),
    ])
    proj = _stub_proj(tmp_path)
    results = proj.run_rule("R-FIBER-001")
    failed = [r for r in results if not r.passed]
    assert len(failed) == 2
    assert all(r.rule_id == "R-FIBER-001" for r in failed)
    assert all("Cable-001 Core 5" in r.problem_location for r in failed)
    assert all(r.severity == "error" for r in failed)


def test_splitter_rows_and_unique_cores_pass(tmp_path):
    xlsx = tmp_path / "纤芯分配表.xlsx"
    _make_fiber_xlsx(xlsx, [
        ("BPE-01", "灰分盘 01", "SP#1 (2:4)", "Cable-001 Core 1", "Cable-002 Core 1"),
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 5", "Parking area"),
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 6", "Cable-007 Core 1"),
    ])
    proj = _stub_proj(tmp_path)
    assert proj.run_rule("R-FIBER-001") == []


def test_standard_duplicate_case_through_engine(tmp_path):
    """「纤芯重复占用案例」经正式引擎执行，命中 2 条 R-FIBER-001。"""
    case = CASE_DIR / "纤芯重复占用案例.xlsx"
    if not case.is_file():
        return
    shutil.copy2(case, tmp_path / case.name)
    proj = _stub_proj(tmp_path)
    failed = [r for r in proj.run_rule("R-FIBER-001") if not r.passed]
    assert len(failed) == 2
    assert all(r.rule_id == "R-FIBER-001" for r in failed)


def test_standard_baseline_through_engine_no_false_positive(tmp_path):
    """正确工程案例经正式引擎执行，不应命中 R-FIBER-001。"""
    baseline = CASE_DIR / "正确工程案例.xlsx"
    if not baseline.is_file():
        return
    shutil.copy2(baseline, tmp_path / baseline.name)
    proj = _stub_proj(tmp_path)
    assert proj.run_rule("R-FIBER-001") == []


def test_run_all_rules_includes_fiber_rule(tmp_path):
    """run_all_rules 自动执行新规则，且异常不会中断其它规则。"""
    xlsx = tmp_path / "纤芯分配表.xlsx"
    _make_fiber_xlsx(xlsx, [
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 5", "Parking area"),
        ("BPE-01", "熔接托盘 01", "无", "Cable-001 Core 5", "Cable-007 Core 1"),
    ])
    proj = _stub_proj(tmp_path)
    results = proj.run_all_rules()
    fiber_failed = [r for r in results if r.rule_id == "R-FIBER-001" and not r.passed]
    assert len(fiber_failed) == 1
    assert any(r.rule_id == "R001" for r in results)  # 其它规则仍正常执行
