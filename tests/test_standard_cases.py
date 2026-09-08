"""10 个标准测试案例的自动化验证（标准答案由我们基于官方规则库判定）。

每个案例文件在 tests/data/standard_cases/ 下，期望命中的规则编号见下方映射。
运行：python -m pytest tests/test_standard_cases.py -q
"""

from pathlib import Path

import pytest

from design_parser.case_checks import baseline_material_codes, check_case

CASE_DIR = Path(__file__).resolve().parents[1] / "tests" / "data" / "standard_cases"

# 案例 -> 期望命中的规则编号（我们的标准答案）
EXPECTED_RULES = {
    "正确工程案例.xlsx": set(),
    "光缆未连接案例.xlsx": {"R-REL-004"},
    # 编码被清空/覆盖时，光缆端点引用同时失配（真实级联问题，一并检出）
    "字段为空案例.xlsx": {"R-FLD-001", "R-REL-004"},
    "编码重复案例.xlsx": {"R-FLD-002", "R-REL-004"},
    "孤立设备案例.xlsx": {"R-REL-001"},
    "缺少图层案例.xlsx": {"R-FILE-001"},
    "缺少文件案例数据.xlsx": {"R-FILE-001"},
    "容量超限案例.xlsx": {"R-DAT-001"},
    "纤芯重复占用案例.xlsx": {"R-FIBER-001"},
    "BOM物料无法匹配案例.xlsx": {"R-BOM-001"},
}


def _all_cases():
    if not CASE_DIR.is_dir():
        return []
    return sorted(CASE_DIR.glob("*.xlsx"))


def test_all_ten_cases_present():
    files = _all_cases()
    assert len(files) == 10, f"案例文件数量不对: {[f.name for f in files]}"


@pytest.mark.parametrize("case_file", _all_cases(), ids=lambda p: p.name)
def test_case_expected_rules(case_file: Path):
    baseline = CASE_DIR / "正确工程案例.xlsx"
    known = baseline_material_codes(baseline)
    issues = check_case(case_file, known_material_codes=known)
    hit = {i["rule_id"] for i in issues}
    expected = EXPECTED_RULES[case_file.name]
    assert hit == expected, (
        f"{case_file.name}: 命中 {sorted(hit)}，期望 {sorted(expected)}\n"
        + "\n".join(f"  - {i['rule_id']} {i['message']}" for i in issues)
    )


def test_baseline_has_no_false_positive():
    """正确工程案例不应命中任何规则（基线无问题）。"""
    case_file = CASE_DIR / "正确工程案例.xlsx"
    issues = check_case(case_file, known_material_codes=baseline_material_codes(case_file))
    assert issues == [], f"正确案例误报: {issues}"
