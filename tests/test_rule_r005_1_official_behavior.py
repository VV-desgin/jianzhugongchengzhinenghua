"""R005_1（官方 R-REL-001）：SITE(TYPE=PM).CODE 与 ZPM.CODE 双向一一对应。

实现与官方规则库 v2.0 R-REL-001 一致（SITE.CODE = ZPM.CODE）。
当前未接入 data-pipeline 路由（与现有正确案例包编码模型冲突，口径待确认），
本测试锁定实现行为，供官方确认口径后一键启用。
"""

from types import SimpleNamespace

from design_parser.rule_engine import check_site_pm_zpm_bidirectional


def _ctx(sites, zpms):
    site_feats = [SimpleNamespace(properties=s) for s in sites]
    zpm_feats = [SimpleNamespace(properties=z) for z in zpms]
    return SimpleNamespace(layers={"SITE": site_feats, "ZPM": zpm_feats})


def test_code_match_bidirectional_no_issue():
    """官方口径：SITE.CODE=PM-01 与 ZPM.CODE=PM-01 双向对应 → 无问题。"""
    ctx = _ctx(
        [{"CODE": "PM-01", "TYPE": "PM"}],
        [{"CODE": "PM-01"}],
    )
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_zpm_ref_pm_linkage_alone_passes():
    """外键模型（ZPM.CODE=ZPM-01 + ZPM.REF_PM=PM-01）：2026-08-22 双口径优化后
    允许 REF_PM 等价关联（依据官方校验规则 6.4/6.5：REF_PM=SITE.CODE=ZPM.CODE）→ 0 问题。"""
    ctx = _ctx(
        [{"CODE": "PM-01", "TYPE": "PM"}],
        [{"CODE": "ZPM-01", "REF_PM": "PM-01"}],
    )
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_broken_ref_pm_link_still_flagged():
    """双口径下孤立语义保留：REF_PM 指向不存在的 PM 仍双向报错。"""
    ctx = _ctx(
        [{"CODE": "PM-01", "TYPE": "PM"}],
        [{"CODE": "ZPM-01", "REF_PM": "PM-NOWHERE"}],
    )
    issues = check_site_pm_zpm_bidirectional(ctx)
    assert len(issues) == 2
    assert all(i.rule_id == "R005_1" and not i.passed for i in issues)
    descs = " ".join(i.error_description for i in issues)
    assert "PM-01" in descs and "ZPM-01" in descs


def test_mixed_model_all_pass():
    """同码与 REF_PM 外键混合模型：两个 PM 都被覆盖 → 0 问题。"""
    ctx = _ctx(
        [{"CODE": "PM-01", "TYPE": "PM"}, {"CODE": "PM-02", "TYPE": "PM"}],
        [{"CODE": "ZPM-01", "REF_PM": "PM-01"}, {"CODE": "PM-02"}],
    )
    assert check_site_pm_zpm_bidirectional(ctx) == []


def test_missing_site_or_zpm_flagged():
    ctx = _ctx(
        [{"CODE": "PM-01", "TYPE": "PM"}, {"CODE": "PM-02", "TYPE": "PM"}],
        [{"CODE": "PM-01"}],
    )
    issues = check_site_pm_zpm_bidirectional(ctx)
    assert len(issues) == 1
    assert "PM-02" in issues[0].error_description


def test_no_layers_returns_empty():
    ctx = SimpleNamespace(layers={})
    assert check_site_pm_zpm_bidirectional(ctx) == []
