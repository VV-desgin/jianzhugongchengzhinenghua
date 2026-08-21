"""R005_2（官方 R-REL-002）：BOITE(TYPE=PBO).REF_PM ↔ SITE(TYPE=PM).CODE 双向主从孤立性。

官方审查规则库 v2.0 R-REL-002：提取 BOITE(TYPE=PBO) 的 REF_PM，在 SITE 图层中查找
对应 CODE；必须存在对应关系（BOITE.REF_PM = SITE.CODE），严重等级=高。
2026-08-22 决策：依据官方规则库启用路由（与 R005_1/R005_3 同组）。
"""

from types import SimpleNamespace

from api import RULE_ROUTING
from design_parser.rule_engine import ALL_RULES, check_site_pm_boite_pbo_bidirectional

GIS_CATS = ["完整设计图", "竣工图", "竣工图（含BOM）", "设计图（含纤芯）"]


def test_r005_2_routed_in_gis_categories():
    for cat in GIS_CATS:
        assert "R005_2" in RULE_ROUTING[cat]


def test_r005_2_registered_in_engine():
    assert "R005_2" in ALL_RULES


def _ctx(boites, sites):
    boite_feats = [SimpleNamespace(properties=b, feature_id=f"b{i}") for i, b in enumerate(boites)]
    site_feats = [SimpleNamespace(properties=s, feature_id=f"s{i}") for i, s in enumerate(sites)]
    return SimpleNamespace(layers={"BOITE": boite_feats, "SITE": site_feats})


def test_pbo_ref_pm_exists_no_issue():
    """官方口径：BOITE(TYPE=PBO).REF_PM 能在 SITE(TYPE=PM).CODE 中找到 → 无问题。"""
    ctx = _ctx(
        [{"CODE": "PBO-01", "TYPE": "PBO", "REF_PM": "PM-01"}],
        [{"CODE": "PM-01", "TYPE": "PM"}],
    )
    assert check_site_pm_boite_pbo_bidirectional(ctx) == []


def test_pbo_ref_pm_missing_flagged():
    """PBO.REF_PM 指向不存在的 PM → 双向各报 1 条 R005_2（引用缺失 + PM 未被引用）。"""
    ctx = _ctx(
        [{"CODE": "PBO-01", "TYPE": "PBO", "REF_PM": "PM-NOWHERE"}],
        [{"CODE": "PM-01", "TYPE": "PM"}],
    )
    issues = check_site_pm_boite_pbo_bidirectional(ctx)
    assert len(issues) == 2
    assert all(i.rule_id == "R005_2" and not i.passed for i in issues)
    descs = " ".join(i.error_description for i in issues)
    assert "PM-NOWHERE" in descs and "PM-01" in descs


def test_site_pm_without_pbo_reference_flagged():
    """SITE PM 未被任何 PBO 的 REF_PM 引用 → 报 1 条 R005_2（主从孤立反向）。"""
    ctx = _ctx(
        [{"CODE": "PBO-01", "TYPE": "PBO", "REF_PM": "PM-01"}],
        [{"CODE": "PM-01", "TYPE": "PM"}, {"CODE": "PM-02", "TYPE": "PM"}],
    )
    issues = check_site_pm_boite_pbo_bidirectional(ctx)
    assert len(issues) == 1
    assert issues[0].rule_id == "R005_2" and not issues[0].passed
    assert "PM-02" in issues[0].error_description


def test_no_layers_returns_empty():
    assert check_site_pm_boite_pbo_bidirectional(SimpleNamespace(layers={})) == []
