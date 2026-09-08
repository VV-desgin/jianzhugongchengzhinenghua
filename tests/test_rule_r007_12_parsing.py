# -*- coding: utf-8 -*-
"""R007_1/R007_2 数字解析回归：斜杠复合值（"12/24"）取第一个整数，而非剥离非数字成 1224。

规则当前未路由（R007_1 与 R020 重复、R007_2 由 R030 替代），但注册于 ALL_RULES，
解析口径必须正确，避免将来启用时误报。
"""
from types import SimpleNamespace

from design_parser.rule_engine import (
    check_pbo_nb_fibre_util_exceeds_capacite,
    check_pm_pbo_port_exceeds_cable_capacity,
)


class _Feat:
    def __init__(self, props):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))


def _ctx(layers):
    return SimpleNamespace(layers=layers, boxes=[], cables=[], device_code_index={})


def test_r007_1_slash_overflow_flagged():
    """NB_FIBRE_UTIL=12/2（12 芯）> CAPACITE=2/12（2 芯）应报；旧解析 122≤212 会漏报。"""
    ctx = _ctx({"BOITE": [
        _Feat({"CODE": "PBO-01", "TYPE": "PBO", "NB_FIBRE_UTIL": "12/2", "CAPACITE": "2/12"})]})
    hits = [i for i in check_pbo_nb_fibre_util_exceeds_capacite(ctx) if not i.passed]
    assert len(hits) == 1
    assert "12" in hits[0].actual_value


def test_r007_1_slash_valid_not_flagged():
    """NB_FIBRE_UTIL=2/12（2 芯）≤ CAPACITE=12/24（12 芯），不得误报。"""
    ctx = _ctx({"BOITE": [
        _Feat({"CODE": "PBO-01", "TYPE": "PBO", "NB_FIBRE_UTIL": "2/12", "CAPACITE": "12/24"})]})
    assert not [i for i in check_pbo_nb_fibre_util_exceeds_capacite(ctx) if not i.passed]


def test_r007_2_slash_overflow_flagged():
    """PBO 容量 12/2（12）> DISTRIBUTION 光缆 2/12（2）应报；旧解析 122≤212 会漏报。"""
    layers = {
        "SITE": [_Feat({"CODE": "PM-01", "TYPE": "PM"})],
        "BOITE": [_Feat({"CODE": "PBO-01", "TYPE": "PBO", "REF_PM": "PM-01", "CAPACITE": "12/2"})],
        "CABLE": [_Feat({"CODE": "C-1", "TYPE_CABLE": "DISTRIBUTION",
                         "ORIGINE": "PM-01", "CAPACITE": "2/12"})],
    }
    ctx = _ctx(layers)
    hits = [i for i in check_pm_pbo_port_exceeds_cable_capacity(ctx) if not i.passed]
    assert len(hits) == 1
    assert "PM-01" in hits[0].check_object
