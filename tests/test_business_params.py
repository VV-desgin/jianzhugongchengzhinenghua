"""Task A1: business_params 加载器测试（TDD 先行）。"""
from design_parser.business_params import load_business_params


def test_load_returns_expected_keys():
    p = load_business_params()
    assert "loss_rates" in p and "reserve_lengths" in p and "packaging" in p
    assert "reuse" in p and "fiber_policy" in p and "instruction_levels" in p


def test_defaults_when_file_missing(tmp_path):
    p = load_business_params(tmp_path / "not_exist.json")
    assert p["fiber_policy"]["required_cores_default"] == 4
    assert p["_meta"]["source"].startswith("行业参考默认值")


def test_loss_rate_defaults():
    p = load_business_params()
    assert p["loss_rates"]["500002050"]["rate"] == 0.05
    assert p["loss_rates"]["poles"]["rate"] == 0.0
