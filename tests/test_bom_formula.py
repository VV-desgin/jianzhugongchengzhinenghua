"""Task A2: BOM 确定性公式测试（TDD 先行）。"""
from design_parser.business_params import load_business_params
from design_parser.bom_formula import compute_bom_quantity

P = load_business_params()


def test_cable_example_from_xlsx():
    # 净量 5.253KM，损耗 5%，预留 1接头+4杆+1端部=0.0485KM，
    # 2KM/盘向上取整 → 3 盘 = 6KM
    counts = {"pcp": 0, "splice": 1, "manhole": 0, "pole": 4, "endpoint": 1}
    r = compute_bom_quantity("500002050", 5.253, counts, P, unit="KM")
    assert abs(r["loss"] - 0.26265) < 1e-6
    assert abs(r["reserve"] - 0.0485) < 1e-6
    assert abs(r["before_pack"] - 5.56415) < 1e-6
    assert abs(r["final"] - 6.0) < 1e-6
    assert "3" in r["detail"] and "6" in r["detail"]


def test_splice_exact_no_packaging():
    r = compute_bom_quantity("500000510", 24.0, {}, P, unit="PC")
    assert r["final"] == 24.0 and r["loss"] == 0.0


def test_pole_integer():
    r = compute_bom_quantity("500002337", 8.0, {}, P, unit="PC")
    assert r["final"] == 8.0
