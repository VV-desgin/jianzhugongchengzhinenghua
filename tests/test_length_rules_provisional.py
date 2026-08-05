"""CABLE_AMONT 长度检查临时口径测试（length_rules.json 配置驱动）。

官方确认前按团队暂定口径：固定前缀（<类型>-<运营商>-）与末尾 -NNN（Increment）
不计入长度，仅设备标识部分计（<=20）。官方确认后通过配置一键切换。
"""
"""CABLE_AMONT 长度检查临时口径测试（length_rules.json 配置驱动）。

末尾 -NNN（Increment）已确认是光缆内部纤芯号/端口号，不计入编号长度；
固定前缀（<类型>-<运营商>-）暂不计入，仅编号主体计（<=20）。最终计法待数据方确认，可通过配置一键切换。
"""

from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from design_parser.feature import UnifiedFeature
from design_parser.project_data import ProjectData
from design_parser.rule_engine import RuleContext, check_field_length, _effective_length_text
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


def test_effective_length_text_provisional():
    # 全串 29 -> 剥前缀 8 + 剥 -NNN 4 = 基础 17
    assert _effective_length_text("CABLE_AMONT", "CDI-UNF-EJA01-MRJ01-TDI01-001") == "EJA01-MRJ01-TDI01"
    # CTR 系列：剥 CTR-INWI- 8 + -001 4 = EJA01
    assert _effective_length_text("CABLE_AMON", "CTR-INWI-EJA01-001") == "EJA01"
    # 无 -NNN：只剥前缀
    assert _effective_length_text("CABLE_AMONT", "CDI-UNF-EJA01-MRJ02-TDI03") == "EJA01-MRJ02-TDI03"
    # 非配置字段不受影响
    assert _effective_length_text("NOM", "CDI-UNF-EJA01-MRJ01-TDI01-001") == "CDI-UNF-EJA01-MRJ01-TDI01-001"


def test_cable_amont_provisional_not_flagged(tmp_path):
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-001", "CABLE_AMON": "CDI-UNF-EJA01-MRJ01-TDI01-001"}),
            _feat(1, {"CODE": "BPE-002", "CABLE_AMON": "CTR-INWI-EJA01-001"}),
        ],
    }, xlsx)
    ctx = RuleContext(proj)
    results = check_field_length(ctx)
    assert results == [], f"临时口径下不应报超长: {[r.error_description for r in results]}"


def test_cable_amont_base_over_limit_still_flagged(tmp_path):
    xlsx = tmp_path / "图层表字段说明和数据校验规则.xlsx"
    _make_rules_xlsx(xlsx)
    proj = _stub_proj({
        "BOITE": [
            _feat(0, {"CODE": "BPE-003", "CABLE_AMON": "CDI-UNF-EJA01-MRJ01-TDI01-SUPERLONGSEG"}),
        ],
    }, xlsx)
    ctx = RuleContext(proj)
    results = check_field_length(ctx)
    assert any(r.rule_id == "R032" for r in results), "基础码超 20 仍应报超长"
