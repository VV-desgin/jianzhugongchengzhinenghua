"""CABLE_AMONT 长度检查测试（length_rules.json 配置驱动）。

官方口径已确认（2026-08-08）：CABLE_AMONT（上游/入箱光缆编号）Longueur 设为 30，
按全串校验（含固定前缀与末尾 -NNN 纤芯号/端口号），>30 判超长。
"""

from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData
from design_parser.rule_engine import RuleContext, check_field_length, _effective_length_text
from design_parser.rule_table_reader import parse_rule_library


def _make_rules_xlsx(path: Path):
    """构造官方规则库（Longueur 仍写 20，用于验证 length_rules.json 的 max_len=30 覆盖生效）。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "校验规则"
    ws.append(["NO.", "NO.", "检测项", "检测内容", "涉及图层", "涉及字段", "规则", "备注"])
    ws2 = wb.create_sheet("BOITE")
    ws2.append(["Nom champ", "字段描述", "Descriptif champ", "Exemple", "Type\nchamp",
                "Longueur\nchamp", "Format de saisie", "Obligatoire\nO/C/N",
                "Description de la condition", "Contrainte de remplissage"])
    ws2.append(["CABLE_AMONT", "上游/入箱光缆编号", "Reference", "CDI-UNF-TNG01-BOK01-01-001",
                "Texte", "20", "CDI-UNF-<PMParent>-<NumTiroir>-<NumCableSortant>-<Increment>",
                "O", "", "Format à définir"])
    wb.save(path)
    wb.close()


def _feat(fid, props):
    return UnifiedFeature(source_layer_name="BOITE", feature_id=fid,
                          geometry=None, properties=props, original_crs="EPSG:4326")


def _stub_proj(layers, rule_xlsx):
    p = ProjectData.__new__(ProjectData)
    p.layers = layers
    p.qgs = None
    p.package = SimpleNamespace(temp_dir=rule_xlsx.parent)
    p.outer_package = None
    p.inner_packages = []
    p._rule_library = None
    p.get_unified_objects = lambda name: []
    p.get_rule_library = lambda: parse_rule_library(rule_xlsx)
    return p


def test_effective_length_text_full_string():
    # 全串口径：前缀与 -NNN 均计入长度，不剥离
    assert _effective_length_text("CABLE_AMONT", "CDI-UNF-EJA01-MRJ01-TDI01-001") == "CDI-UNF-EJA01-MRJ01-TDI01-001"
    assert _effective_length_text("CABLE_AMON", "CTR-INWI-EJA01-001") == "CTR-INWI-EJA01-001"
    assert _effective_length_text("CABLE_AMONT", "CDI-UNF-EJA01-MRJ02-TDI03") == "CDI-UNF-EJA01-MRJ02-TDI03"
    # 非配置字段不受影响
    assert _effective_length_text("NOM", "CDI-UNF-EJA01-MRJ01-TDI01-001") == "CDI-UNF-EJA01-MRJ01-TDI01-001"


def test_cable_amont_full_string_not_flagged(tmp_path):
    """真实数据全串 18/25/29 位均 <=30，即使官方 xlsx 写 20 也不误报（max_len 覆盖生效）。"""
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CABLE_AMON": "CDI-UNF-EJA01-MRJ01-TDI01-001"}),  # 29
            _feat(1, {"CODE": "BPE-002", "CABLE_AMON": "CTR-INWI-EJA01-001"}),              # 18
            _feat(2, {"CODE": "BPE-003", "CABLE_AMON": "CDI-UNF-EJA01-MRJ02-TDI03"}),       # 25
        ],
    }, xlsx)
    ctx = RuleContext(proj)
    results = check_field_length(ctx)
    assert results == [], f"30 位全串口径下不应报超长: {[r.error_description for r in results]}"


def test_cable_amont_over_30_flagged(tmp_path):
    """全串长度 >30 仍应报 R032 超长。"""
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-004", "CABLE_AMON": "CDI-UNF-EJA01-MRJ01-TDI01-001-EXTRA"}),  # 35
        ],
    }, xlsx)
    ctx = RuleContext(proj)
    results = check_field_length(ctx)
    assert any(r.rule_id == "R032" for r in results), "全串超过 30 应报超长"
