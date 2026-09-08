"""P1-06：business_params 快照与加载器/API 同源。"""

import json
from pathlib import Path

from design_parser.business_params import load_business_params


def test_snapshot_matches_loader():
    snap_path = (
        Path(__file__).resolve().parents[1]
        / "design_parser"
        / "mappings"
        / "business_params_snapshot.json"
    )
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    live = load_business_params()
    assert snap["_meta"]["official_decisions"] == live["_meta"]["official_decisions"]
    for key in ("loss_rates", "reserve_lengths", "packaging", "fiber_policy"):
        assert snap[key] == live[key]
