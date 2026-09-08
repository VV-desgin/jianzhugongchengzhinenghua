"""P2 优化项测试：坐标系转换工具。"""

from design_parser.spatial_utils import reproject_coords


def test_reproject_same_crs_returns_as_is():
    coords = [[1.0, 2.0, 3.0]]
    assert reproject_coords(coords, "EPSG:4326", "EPSG:4326") == coords


def test_reproject_geographic_to_geographic():
    # 4326 -> 4490 都是经纬度地理坐标系，数值基本不变
    out = reproject_coords([[116.0, 30.0]], "EPSG:4326", "EPSG:4490")
    assert abs(out[0][0] - 116.0) < 1e-6
    assert abs(out[0][1] - 30.0) < 1e-6


def test_reproject_projected_to_geographic_changes():
    out = reproject_coords([[0.0, 0.0]], "EPSG:26191", "EPSG:4326")
    # 26191 原点（0,0）对应摩洛哥附近经纬度，应发生明显变化
    assert out[0][0] != 0.0 or out[0][1] != 0.0


def test_reproject_invalid_crs_returns_original():
    coords = [[1.0, 2.0]]
    assert reproject_coords(coords, "BADCRS", "EPSG:4326") == coords
    assert reproject_coords(coords, None, "EPSG:4326") == coords
