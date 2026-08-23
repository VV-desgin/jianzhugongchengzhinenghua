# -*- coding: utf-8 -*-
"""R031 字段值域：包内 CSV 无表头（值;值）时首行合法值不得被误判。"""
from pathlib import Path
from types import SimpleNamespace

from design_parser.rule_engine import check_field_domain


class _Feat:
    def __init__(self, props):
        self.properties = props
        self.feature_id = str(props.get("CODE", ""))


def _ctx(tmpdir: Path, csv_name: str, content: str, layers):
    (tmpdir / csv_name).write_text(content, encoding="utf-8")
    pkg = SimpleNamespace(temp_dir=tmpdir)
    return SimpleNamespace(package=pkg, layers=layers)


def test_headerless_csv_first_row_is_valid():
    """无表头 CSV：首行值（如 DEPLOYE）必须属于合法域，不得误报。"""
    tmp = Path(__import__("tempfile").mkdtemp(prefix="r031_"))
    ctx = _ctx(
        tmp,
        "l_statut.csv",
        "DEPLOYE;DEPLOYE\nEN PROJET;EN PROJET\n",
        {"BOITE": [_Feat({"CODE": "PBO-01", "STATUT": "DEPLOYE"})]},
    )
    hits = [i for i in check_field_domain(ctx) if i.rule_id == "R031"]
    assert hits == []


def test_headerless_csv_invalid_value_flagged():
    """无表头 CSV：不在域内的值仍要报。"""
    tmp = Path(__import__("tempfile").mkdtemp(prefix="r031_"))
    ctx = _ctx(
        tmp,
        "l_statut.csv",
        "DEPLOYE;DEPLOYE\nEN PROJET;EN PROJET\n",
        {"BOITE": [_Feat({"CODE": "PBO-01", "STATUT": "XXX"})]},
    )
    hits = [i for i in check_field_domain(ctx) if i.rule_id == "R031"]
    assert len(hits) == 1


def test_csv_with_header_still_works():
    """带表头的 CSV：表头行跳过，数据行全部参与校验。"""
    tmp = Path(__import__("tempfile").mkdtemp(prefix="r031_"))
    ctx = _ctx(
        tmp,
        "l_statut.csv",
        "STATUT;LIBELLE\nDEPLOYE;DEPLOYE\nEN PROJET;EN PROJET\n",
        {"BOITE": [_Feat({"CODE": "PBO-01", "STATUT": "EN PROJET"})]},
    )
    hits = [i for i in check_field_domain(ctx) if i.rule_id == "R031"]
    assert hits == []
