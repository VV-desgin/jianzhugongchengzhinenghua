#!/usr/bin/env python3
"""稳定性回归检查：关键基线逐项断言（不依赖 pytest）。

基线：
- 场勘设计图.zip：survey_design，43/43/0，23 图层/244 对象
- 赛题一.zip：full_design，277/49/228，规则分布精确一致，R008/R012/R021/R032=0
- 赛题四-摩洛哥.rar：as_built，277/49/228（与赛题一同数据）
- TC-01_正确工程案例.xlsx：Excel 工程包，109/8/98（warning 3：R-BOM-001×3），R007=1 R021=97 R-BOM-001=3，review_scope=non_spatial（P0-01 起 warning 不计入 failed_rules）

用法：python tools/regression_check.py
"""
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api import app

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("DESIGN_PARSER_DATA_DIR", str(ROOT / "tests" / "data")))
CASE = Path(os.environ.get("DESIGN_PARSER_CASE_FILE", str(ROOT / "tests" / "data" / "regression" / "TC-01_正确工程案例.xlsx")))

SAITI1_RULES = {
    "R019": 147, "R022": 49, "R017": 23, "R007": 4,
    "R005_4": 2, "R014": 1, "R020": 1, "R023": 1,
}


def run_pipeline(c, path, filename, content_type=None):
    with open(path, "rb") as f:
        return c.post("/agent/data-pipeline",
                      files={"file": (filename, f, content_type or "")}, timeout=900).json()


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), name, detail)
    return cond


def main():
    ok = True
    with TestClient(app) as c:
        # 1) 场勘（数据缺失时跳过，可用 DESIGN_PARSER_DATA_DIR 指定）
        try:
            d = run_pipeline(c, DATA / "场勘设计图.zip", "场勘设计图.zip")
            rev = d.get("review") or {}
            ok &= check("场勘: project_type=survey_design", d.get("project_type") == "survey_design", d.get("project_type"))
            ok &= check("场勘: 43/43/0", (rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules")) == (43, 43, 0), str((rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules"))))
            ok &= check("场勘: 23层/244对象", (d.get("summary") or {}).get("layer_count") == 23 and (d.get("summary") or {}).get("object_count") == 244)
        except FileNotFoundError as e:
            print(f"SKIP 场勘: 数据缺失 {e}；可设置环境变量 DESIGN_PARSER_DATA_DIR")

        # 2) 赛题一
        try:
            d = run_pipeline(c, DATA / "赛题一.zip", "赛题一.zip")
            rev = d.get("review") or {}
            rules = Counter(i.get("rule_id") for i in (rev.get("issues") or []))
            ok &= check("赛题一: full_design", d.get("project_type") == "full_design", d.get("project_type"))
            ok &= check("赛题一: 277/49/228", (rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules")) == (277, 49, 228), str((rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules"))))
            ok &= check("赛题一: 规则分布精确", dict(rules) == SAITI1_RULES, str(dict(rules)))
            ok &= check("赛题一: R008/R012/R021/R032=0", rules.get("R008", 0) == 0 and rules.get("R012", 0) == 0 and rules.get("R021", 0) == 0 and rules.get("R032", 0) == 0)
        except FileNotFoundError as e:
            print(f"SKIP 赛题一: 数据缺失 {e}；可设置环境变量 DESIGN_PARSER_DATA_DIR 指向 01_官方赛题资料")

        # 3) 赛题四
        try:
            d = run_pipeline(c, DATA / "赛题四- 摩洛哥.rar", "赛题四-摩洛哥.rar")
            rev = d.get("review") or {}
            rules = Counter(i.get("rule_id") for i in (rev.get("issues") or []))
            ok &= check("赛题四: as_built", d.get("project_type") == "as_built", d.get("project_type"))
            ok &= check("赛题四: 277/49/228", (rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules")) == (277, 49, 228), str((rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules"))))
            ok &= check("赛题四: 规则分布精确", dict(rules) == SAITI1_RULES, str(dict(rules)))
        except FileNotFoundError as e:
            print(f"SKIP 赛题四: 数据缺失 {e}；可设置环境变量 DESIGN_PARSER_DATA_DIR 指向 01_官方赛题资料")

        # 4) TC-01 Excel（数据缺失时跳过，可用 DESIGN_PARSER_CASE_FILE 指定）
        try:
            d = run_pipeline(c, CASE, "TC-01_正确工程案例.xlsx")
            rev = d.get("review") or {}
            rules = Counter(i.get("rule_id") for i in (rev.get("issues") or []))
            ok &= check("TC-01: Excel 工程包", (d.get("file_info") or {}).get("file_category") == "Excel 工程包")
            ok &= check("TC-01: 109/8/98 warning=3", (rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules"), rev.get("warning_rules")) == (109, 8, 98, 3), str((rev.get("total_rules"), rev.get("passed_rules"), rev.get("failed_rules"), rev.get("warning_rules"))))
            ok &= check("TC-01: R007=1 R021=97 R-BOM-001=3", rules.get("R007", 0) == 1 and rules.get("R021", 0) == 97 and rules.get("R-BOM-001", 0) == 3, str(dict(rules)))
            ok &= check("TC-01: non_spatial", d.get("review_scope") == "non_spatial")
        except FileNotFoundError as e:
            print(f"SKIP TC-01: 测试数据缺失 {e}；可设置环境变量 DESIGN_PARSER_CASE_FILE 指向 TC-01_正确工程案例.xlsx")

    print("\\n稳定性回归:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
