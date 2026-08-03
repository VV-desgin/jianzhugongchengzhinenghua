"""任务单要求补充测试：fiona 缺失（如 Python 3.14）时 pyshp 纯 Python 回退可正常读取官方 SHP。"""
import zipfile
from pathlib import Path

import pytest

from design_parser.layer_reader import LayerReader, PYSHP_AVAILABLE
from design_parser.qgs_reader import QgsLayerMeta


@pytest.fixture(scope="session")
def extracted_survey_dir(tmp_path_factory, survey_zip_path):
    """解压官方场勘包到临时目录，返回解压根目录。"""
    target = tmp_path_factory.mktemp("survey_extract")
    with zipfile.ZipFile(survey_zip_path) as z:
        z.extractall(target)
    return target


def _meta(name: str, rel_path: str, geom_type: str = "point", srs: str = None) -> QgsLayerMeta:
    return QgsLayerMeta(
        name=name,
        data_source=rel_path,
        geometry_type=geom_type,
        srs_authid=srs,
        fields=None,
    )


def _force_pyshp(monkeypatch):
    """强制走 pyshp 回退路径（模拟 fiona 缺失）。"""
    if not PYSHP_AVAILABLE:
        pytest.skip("pyshp 未安装，无法测试回退路径")
    monkeypatch.setattr("design_parser.layer_reader.FIONA_AVAILABLE", False)


def test_pyshp_fallback_reads_official_imb(monkeypatch, extracted_survey_dir):
    """官方 IMB 图层通过 pyshp 回退读取：51 个要素、带几何、带属性、带 CRS。"""
    _force_pyshp(monkeypatch)
    reader = LayerReader(extracted_survey_dir)
    feats = reader.read_vector_layer(
        _meta("IMB", "Plan_de_récolement/Shape/IMB.shp", "point", "EPSG:32629")
    )
    assert len(feats) == 51
    assert all(f.geometry_type is not None for f in feats)
    assert all(f.original_crs and "EPSG:" in str(f.original_crs).upper() for f in feats)
    assert feats[0].properties, "pyshp 回退应读到 DBF 属性"


def test_pyshp_fallback_empty_layer_preserved(monkeypatch, extracted_survey_dir):
    """官方 BOITE 空图层通过 pyshp 回退读取：0 要素但读取成功（exists 由上层判定）。"""
    _force_pyshp(monkeypatch)
    reader = LayerReader(extracted_survey_dir)
    feats = reader.read_vector_layer(
        _meta("BOITE", "Plan_de_récolement/Shape/BOITE.shp", "point", "EPSG:32629")
    )
    assert feats == []


def test_pyshp_crs_parsing():
    """.prj WKT 中能解析出 EPSG 编码。"""
    prj = 'PROJCS["WGS 84 / UTM zone 29N",GEOGCS["WGS 84",DATUM["WGS_1984"],AUTHORITY["EPSG","4326"]],AUTHORITY["EPSG","32629"]]'
    crs = LayerReader._crs_from_prj(prj)
    assert crs == "EPSG:32629"


def test_pyshp_crs_missing_returns_none():
    assert LayerReader._crs_from_prj(None) is None
    assert LayerReader._crs_from_prj("") is None
