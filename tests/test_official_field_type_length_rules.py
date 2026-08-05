"""P0-1：官方字段说明（Type champ / Longueur champ）驱动 R018/R032 检查。

AgentA 交付：
- /rule-library 的 executable_rules 新增 field_type_check（R018）与
  field_length_check（R032）条件；
- 规则引擎 R018（字段类型）/ R032（字段长度）读取官方字段说明执行，
  同时保留 YAML 配置检查（R018 修复归一化字段名解析）。
"""

from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData
from design_parser.rule_engine import (
    RuleContext,
    check_field_length,
    check_field_types,
)
from design_parser.rule_table_reader import parse_rule_library


def _make_rules_xlsx(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "校验规则"
    ws.append(["NO.", "NO.", "检测项", "检测内容", "涉及图层", "涉及字段", "规则", "备注"])
    ws2 = wb.create_sheet("BOITE")
    ws2.append(["Nom champ", "字段描述", "Descriptif champ", "Exemple", "Type\nchamp",
                "Longueur\nchamp", "Format de saisie", "Obligatoire\nO/C/N",
                "Description de la condition", "Contrainte de remplissage"])
    ws2.append(["CODE", "光箱编码", "Code", "BPE-001", "Texte", "30", "Saisie libre", "O", "", ""])
    ws2.append(["CAPACITE", "容量", "Capacite", "144", "Entier", "3", "Saisie libre", "O", "", ""])
    ws2.append(["HAUTEUR", "高度", "Hauteur", "3.5", "Double", "4", "Saisie libre", "C", "", ""])
    ws2.append(["NOM", "现场命名", "Nom", "BPE-001", "Texte", "5", "Saisie libre", "C", "", ""])
    ws2.append(["LONGUEUR", "长度", "Longueur", "13.47", "Double", "10", "Saisie libre", "C", "", ""])
    wb.save(path)
    wb.close()


def _feat(fid, props):
    return UnifiedFeature(
        source_layer_name="BOITE",
        feature_id=fid,
        geometry=None,
        properties=props,
        original_crs="EPSG:4326",
    )


def _stub_proj(layers, rule_xlsx):
    """构造最小 ProjectData 桩：含图层、真实解析的规则库与包临时目录。"""
    p = ProjectData.__new__(ProjectData)
    p.layers = layers
    p.qgs = None
    p.package = SimpleNamespace(temp_dir=rule_xlsx.parent)
    p.outer_package = None
    p.inner_packages = []
    p._rule_library = None
    p.get_unified_objects = lambda name: []

    def _get_rule_library():
        if p._rule_library is None:
            p._rule_library = parse_rule_library(rule_xlsx)
        return p._rule_library

    p.get_rule_library = _get_rule_library
    return p


def test_r018_official_type_check(tmp_path):
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CAPACITE": 144, "HAUTEUR": "3.5"}),
            _feat(1, {"CODE": "BPE-002", "CAPACITE": "abc", "HAUTEUR": "高"}),
        ],
    }, xlsx)
    results = proj.run_rule("R018")
    failed = [r for r in results if not r.passed]
    assert len(failed) == 2
    assert all(r.rule_id == "R018" for r in failed)
    fields = sorted(r.problem_location.replace("字段 ", "") for r in failed)
    assert fields == ["CAPACITE", "HAUTEUR"]
    # 官方字段说明来源信息出现在对应错误说明中（CAPACITE 由 YAML 配置判定，HAUTEUR 由官方说明判定）
    official_msgs = [r.error_description for r in failed if "官方字段说明" in (r.error_description or "")]
    assert len(official_msgs) == 1 and "HAUTEUR" in official_msgs[0]


def test_r018_official_type_allows_convertible_values(tmp_path):
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CAPACITE": 144.0, "HAUTEUR": "3,5"}),
            _feat(1, {"CODE": "BPE-002", "CAPACITE": "144", "HAUTEUR": 3.5}),
        ],
    }, xlsx)
    results = proj.run_rule("R018")
    assert all(r.passed for r in results)  # 无失败


def test_r032_official_length_check(tmp_path):
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CAPACITE": 144, "HAUTEUR": 3.5}),
            _feat(1, {"CODE": "X" * 31, "CAPACITE": 144}),
        ],
    }, xlsx)
    results = proj.run_rule("R032")
    failed = [r for r in results if not r.passed]
    assert len(failed) == 1
    assert failed[0].rule_id == "R032"
    assert "CODE" in failed[0].error_description
    assert "31" in failed[0].actual_value
    # 数值 144 / 3.5 不因 float 尾缀或小数位误报长度
    assert all("CAPACITE" not in r.error_description for r in results)


def test_no_rule_library_no_official_checks():
    p = ProjectData.__new__(ProjectData)
    p.layers = {
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CAPACITE": 144, "HAUTEUR": "高"}),
            _feat(1, {"CODE": "BPE-002", "CAPACITE": 144, "HAUTEUR": "12345"}),
        ],
    }
    p.qgs = None
    p.package = None
    p.outer_package = None
    p.inner_packages = []
    p._rule_library = None
    p.get_unified_objects = lambda name: []

    def _empty():
        if p._rule_library is None:
            p._rule_library = {}
        return p._rule_library

    p.get_rule_library = _empty
    ctx = RuleContext(p)
    # 无规则库时不产生官方字段说明类检查；YAML 未配置 HAUTEUR，故均无结果
    assert check_field_types(ctx) == []
    assert check_field_length(ctx) == []


def test_r032_official_numeric_float_no_false_positive(tmp_path):
    """AgentC 审查发现：官方 Longueur 是 DBF 存储列宽，数值字段的高精度 float
    不应按 Python 字符串长度误报（如 CABLE.LONGUEUR=13.473601128875206）。"""
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "LONGUEUR": 13.473601128875206}),
            _feat(1, {"CODE": "BPE-002", "LONGUEUR": 1.2345678901234567}),
        ],
    }, xlsx)
    results = proj.run_rule("R032")
    assert all(r.passed for r in results)  # 数值字段（Double）不做官方长度检查


def test_r018_official_na_sentinel_not_flagged(tmp_path):
    """AgentC 审查发现：'NA'/'N/A'/'SANS OBJET' 等缺失哨兵不算类型错误（含 YAML 路径）。"""
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CAPACITE": "NA", "HAUTEUR": "NA"}),
            _feat(1, {"CODE": "BPE-002", "CAPACITE": "N/A", "HAUTEUR": "SANS OBJET"}),
        ],
    }, xlsx)
    results = proj.run_rule("R018")
    assert all(r.passed for r in results)


def test_r032_official_sentinel_not_length_flagged(tmp_path):
    """缺失哨兵不参与官方长度检查（如 NOM 规格 5 位、值为 SANS OBJET 10 字符）。"""
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "NOM": "SANS OBJET"}),
        ],
    }, xlsx)
    results = proj.run_rule("R032")
    assert all(r.passed for r in results)
