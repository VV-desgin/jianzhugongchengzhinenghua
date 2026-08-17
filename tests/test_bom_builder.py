"""后端标准 BOM 生成（bom_builder）与纤芯占用预置（fiber_assignments）测试。"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from design_parser.bom_builder import build_bom
from design_parser.business_params import load_business_params
from design_parser.rule_engine import build_fiber_assignments


class _FakeFeat:
    def __init__(self, props):
        self.properties = props


class _FakeCtx:
    def __init__(self, layers):
        self.layers = layers


def _eng(objects):
    return {"project_id": "t", "objects": objects}


def test_bom_cable_formula():
    """光缆 5.253KM 按 2KM/盘向上取整 → 3盘6KM（损耗/预留/取整链路）。"""
    eng = _eng({
        "cable": [{"code": "C1", "longueur": 5.253, "capacite": 24, "modulo": 6,
                   "origine": "A", "extremite": "B", "nb_fibre_util": 6}],
        "boite": [], "ptech": [], "site": [], "infrastructure": [],
    })
    result = build_bom(eng)
    cable = next(it for it in result["bom_items"] if it["物料编码"] == "500002050")
    assert cable["设计数量"] == pytest.approx(5.253)
    assert cable["损耗数量"] == pytest.approx(5.253 * 0.05)
    assert cable["最终数量"] == 6.0  # ceil(5.565/2)=3 盘 → 6KM


def test_bom_pole_reuse_deduction():
    """电杆利旧冲减：设计 2 根、1 根 reuse=yes → 新建 1 根且标记待人工确认。"""
    eng = _eng({
        "cable": [], "boite": [],
        "ptech": [
            {"code": "P1", "type": "7m 4英寸", "hauteur_appui": 7},
            {"code": "P2", "type": "7m 4英寸", "hauteur_appui": 7, "reuse": "yes"},
        ],
        "site": [], "infrastructure": [],
    })
    result = build_bom(eng)
    pole = next(it for it in result["bom_items"] if it["物料编码"] == "500002480")
    assert pole["设计数量"] == 1
    assert pole["置信状态"] == "待人工确认"
    assert "利旧冲减" in pole["计算依据"]


def test_bom_box_mapping():
    """箱体按容量映射：容量 72 → FDT(500002054)，16 → 16口光箱(500002142)。"""
    eng = _eng({
        "cable": [], "ptech": [], "site": [], "infrastructure": [],
        "boite": [
            {"code": "B1", "type": "FDT", "capacite": 72},
            {"code": "B2", "type": "16口", "capacite": 16},
        ],
    })
    result = build_bom(eng)
    codes = [it["物料编码"] for it in result["bom_items"]]
    assert "500002054" in codes
    assert "500002142" in codes


def test_bom_params_source_marked():
    """所有 BOM 行数据来源标注行业参考默认值，待官方确认。"""
    eng = _eng({"cable": [], "boite": [], "ptech": [], "site": [], "infrastructure": []})
    result = build_bom(eng)
    assert result["success"] is True
    assert result["summary"]["confirm_count"] >= 0
    for it in result["bom_items"]:
        assert "待官方确认" in it["数据来源"]


def test_fiber_assignments_generation():
    """已用芯数>0 的光缆生成预置占用（tube/fiber/core 与纤芯工具一致）。"""
    ctx = _FakeCtx({
        "CABLE": [
            _FakeFeat({"CODE": "C1", "ORIGINE": "A", "EXTREMITE": "B",
                       "NB_FIBRE_U": 6, "CAPACITE": 24, "MODULO": 6}),
            _FakeFeat({"CODE": "C2", "ORIGINE": "A", "EXTREMITE": "B",
                       "NB_FIBRE_U": 0, "CAPACITE": 24, "MODULO": 6}),
            _FakeFeat({"CODE": "C3"}),  # 无已用芯数 → 跳过
        ],
    })
    fa = build_fiber_assignments(ctx)
    assert len(fa) == 1
    assert fa[0]["cable_code"] == "C1"
    assert len(fa[0]["assigned"]) == 6
    # 6 芯：cores_per_tube=4 → tube1=1~4, tube2=5~6
    assert fa[0]["assigned"][0] == {"tube": 1, "fiber": 1, "core": 1}
    assert fa[0]["assigned"][3] == {"tube": 1, "fiber": 1, "core": 4}
    assert fa[0]["assigned"][4] == {"tube": 2, "fiber": 1, "core": 1}


def test_fiber_assignments_no_layer():
    """无 CABLE 图层 → 空列表。"""
    ctx = _FakeCtx({"BOITE": []})
    assert build_fiber_assignments(ctx) == []
