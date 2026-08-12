"""P0-01：审查统计按严重等级计算，warning 不计入 failed_rules。

覆盖验收要求：
- passed=True → 计入 passed
- passed=False, severity=warning → 计入 warning，不计入 failed
- passed=False, severity=error → 计入 failed
- passed=False, severity=fatal → 计入 failed
- R032 长度超限 → issue 保留、severity=warning、failed_rules 不增加
- R007 CODE 重复 / R008 引用不存在 → failed_rules 增加
"""

from api import _effective_severity, _normalize_severities, _severity_counts
from design_parser.check_result import CheckResult


def _r(rule_id, passed=True, severity=None):
    return CheckResult(
        check_object="检查对象",
        passed=passed,
        problem_location="问题位置",
        actual_value="实际值",
        expected_value="标准值",
        rule_id=rule_id,
        error_description="错误说明",
        severity=severity,
    )


def test_passed_true_counts_passed():
    s = _severity_counts([_r("R001", passed=True)])
    assert s == {"total_rules": 1, "warning_rules": 0, "failed_rules": 0, "passed_rules": 1}


def test_warning_not_failed():
    s = _severity_counts([_r("R032", passed=False, severity="warning")])
    assert s["warning_rules"] == 1
    assert s["failed_rules"] == 0
    assert s["passed_rules"] == 0


def test_error_counts_failed():
    s = _severity_counts([_r("R008", passed=False, severity="error")])
    assert s["failed_rules"] == 1
    assert s["warning_rules"] == 0


def test_fatal_counts_failed():
    s = _severity_counts([_r("R007", passed=False, severity="fatal")])
    assert s["failed_rules"] == 1
    assert s["warning_rules"] == 0


def test_severity_counts_mixed():
    results = [
        _r("R001", passed=True),
        _r("R032", passed=False, severity="warning"),
        _r("R007", passed=False, severity="fatal"),
        _r("R008", passed=False, severity="error"),
    ]
    s = _severity_counts(results)
    assert s == {"total_rules": 4, "warning_rules": 1, "failed_rules": 2, "passed_rules": 1}


def test_severity_map_normalization():
    results = [
        _r("R032", passed=False),      # 未配置 → warning
        _r("R-BOM-001", passed=False), # 未配置 → warning
        _r("R007", passed=False),      # SEVERITY_MAP → fatal
        _r("R008", passed=False),      # SEVERITY_MAP → error
    ]
    _normalize_severities(results)
    assert results[0].severity == "warning"
    assert results[1].severity == "warning"
    assert results[2].severity == "fatal"
    assert results[3].severity == "error"
    s = _severity_counts(results)
    assert s["failed_rules"] == 2
    assert s["warning_rules"] == 2


def test_r032_length_warning_kept_not_failed():
    """长度超限 R032：issue 保留（passed=False）、severity=warning、不计入 failed_rules。"""
    results = [_r("R032", passed=False, severity="warning")]
    _normalize_severities(results)
    assert results[0].passed is False          # issue 保留
    assert results[0].severity == "warning"    # 等级不变
    s = _severity_counts(results)
    assert s["failed_rules"] == 0
    assert s["warning_rules"] == 1


def test_r007_r008_count_failed():
    """CODE 重复 R007 / 引用不存在 R008 必须计入 failed_rules。"""
    results = [
        _r("R007", passed=False, severity="fatal"),
        _r("R008", passed=False, severity="error"),
        _r("R021", passed=False, severity="error"),
    ]
    s = _severity_counts(results)
    assert s["failed_rules"] == 3
    assert s["warning_rules"] == 0


def test_effective_severity_fallback():
    r = _r("R032", passed=False, severity=None)
    assert _effective_severity(r) == "warning"
    r2 = _r("R007", passed=False, severity=None)
    assert _effective_severity(r2) == "fatal"
