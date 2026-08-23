"""负值高度拦截（架空设备高度 < 0 → R005，2026-08-23）。

背景：PTECH.HAUTEUR_APPUI 设为 -5 时系统未报错；物理上架空设备高度不可能小于 0。
0 视为合法（如 CHAMBRE 类技术点高度 0 表示不适用），仅拦截负值。
"""
from types import SimpleNamespace

from design_parser.rule_engine import check_required_fields


class _Feat:
    def __init__(self, props):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))


def _issues(props):
    ctx = SimpleNamespace(layers={"PTECH": [_Feat(props)]})
    return check_required_fields(ctx, required_fields={})


def test_negative_height_flagged():
    """HAUTEUR_APPUI=-5 → R005 error（高度不可能小于 0）。"""
    issues = _issues({"CODE": "PTC-01", "TYPE": "POTEAU", "HAUTEUR_APPUI": -5})
    hits = [i for i in issues if i.rule_id == "R005"]
    assert len(hits) == 1
    assert hits[0].passed is False
    assert hits[0].severity == "error"
    assert "挂高为负值，高度不可能小于 0" in hits[0].error_description
    assert "HAUTEUR_APPUI" in hits[0].problem_location


def test_negative_height_alias_flagged():
    """DBF 截断别名 HAUTEUR_AP=-5 同样拦截。"""
    issues = _issues({"CODE": "PTC-02", "TYPE": "POTEAU", "HAUTEUR_AP": -5.0})
    hits = [i for i in issues if i.rule_id == "R005"]
    assert len(hits) == 1
    assert "HAUTEUR_AP" in hits[0].problem_location


def test_zero_height_not_flagged():
    """高度 0 不拦截（CHAMBRE 等场景合法，与既有基线一致）。"""
    issues = _issues({"CODE": "PTC-03", "TYPE": "CHAMBRE", "HAUTEUR_APPUI": 0})
    assert not [i for i in issues if i.rule_id == "R005"]


def test_positive_height_not_flagged():
    """正常电杆高度（如 7m）不拦截。"""
    issues = _issues({"CODE": "PTC-04", "TYPE": "POTEAU", "HAUTEUR_APPUI": 7})
    assert not [i for i in issues if i.rule_id == "R005"]
