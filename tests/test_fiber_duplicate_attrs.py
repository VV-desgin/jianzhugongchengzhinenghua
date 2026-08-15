"""R-FIBER-002：同路由光缆按 1~N 芯连续占用推断纤芯重复占用。"""

from types import SimpleNamespace

from design_parser.rule_engine import check_fiber_duplicate_by_cable_attrs


def _ctx(cables):
    feats = [SimpleNamespace(properties=c) for c in cables]
    return SimpleNamespace(layers={"CABLE": feats})


def test_same_route_overlap_detected():
    ctx = _ctx([
        {"CODE": "CABLE-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 6},
        {"CODE": "CABLE-DUP-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 6},
    ])
    issues = check_fiber_duplicate_by_cable_attrs(ctx)
    assert len(issues) == 1
    assert issues[0].rule_id == "R-FIBER-002"
    assert issues[0].severity == "warning"
    assert "同路由" in issues[0].error_description and "推断" in issues[0].error_description


def test_different_routes_no_issue():
    ctx = _ctx([
        {"CODE": "CABLE-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 6},
        {"CODE": "CABLE-02", "ORIGINE": "PBO-01", "EXTREMITE": "PBO-02", "NB_FIBRE_U": 6},
    ])
    assert check_fiber_duplicate_by_cable_attrs(ctx) == []


def test_single_cable_no_issue():
    ctx = _ctx([{"CODE": "CABLE-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 6}])
    assert check_fiber_duplicate_by_cable_attrs(ctx) == []


def test_zero_or_missing_usage_no_issue():
    ctx = _ctx([
        {"CODE": "CABLE-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 0},
        {"CODE": "CABLE-DUP-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01"},
    ])
    assert check_fiber_duplicate_by_cable_attrs(ctx) == []


def test_same_code_duplicate_record_skipped():
    ctx = _ctx([
        {"CODE": "CABLE-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 6},
        {"CODE": "CABLE-01", "ORIGINE": "PM-01", "EXTREMITE": "PBO-01", "NB_FIBRE_U": 6},
    ])
    assert check_fiber_duplicate_by_cable_attrs(ctx) == []
