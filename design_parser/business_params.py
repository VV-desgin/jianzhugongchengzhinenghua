"""业务参数加载：唯一事实源 design_parser/mappings/business_params.json。"""
import json
from pathlib import Path
from typing import Optional

DEFAULT_BUSINESS_PARAMS = {
    "_meta": {"source": "行业参考默认值，待官方确认",
              "official_pending": ["D01", "D02", "D03", "D04", "D05", "D06", "D07"]},
    "loss_rates": {"500002050": {"rate": 0.05, "category": "cable"},
                   "200001033": {"rate": 0.03, "category": "wire"},
                   "poles": {"rate": 0.0, "spare_rate": 0.02}},
    "reserve_lengths": {"pcp_joint_m": 1.35, "splice_per_side_m": 7.5,
                        "manhole_m": 0.75, "pole_m": 7.5, "endpoint_m": 3.5},
    "packaging": {"500002050": {"unit": "km", "pack": 2.0, "round": "ceil"},
                  "500000510": {"round": "exact", "by": "splice_points"}},
    "reuse": {"flag_field": "reuse",
              "high_possible": ["500002480", "500002337", "500002159", "500004729"],
              "manual_verify": ["200001033"],
              "default": "new_with_notice"},
    "fiber_policy": {"required_cores_default": 4, "splice_cores_per_pcp": 4,
                     "through_splice": True, "park_protected": True,
                     "park_in_splice_count": False},
    "instruction_levels": ["pcp", "process"],
    "process_cards": ["PCP安装", "光缆成端与熔接", "分光器安装", "光路测试"],
}

_PATH = Path(__file__).resolve().parent / "mappings" / "business_params.json"


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_business_params(path: Optional[Path] = None) -> dict:
    """加载业务参数；文件缺失/损坏时回退内置默认值。"""
    p = Path(path) if path else _PATH
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return DEFAULT_BUSINESS_PARAMS
        merged = _deep_merge(DEFAULT_BUSINESS_PARAMS, data)
        merged.setdefault("_meta", {}).setdefault(
            "source", "行业参考默认值，待官方确认")
        return merged
    except (OSError, ValueError):
        return DEFAULT_BUSINESS_PARAMS
