# -*- coding: utf-8 -*-
"""规则健康检查（上线门禁）：
1. 来源完整性：68 条规则在 09 追溯表均有 Source ID 与 Evidence；
2. 路由覆盖：ALL_RULES 中未路由清单（R007_1/R007_2 为有意保留，白名单）；
3. 配置-规则映射一致性：safety_distances.json 与 safety_rules.py rule_ids 互查；
4. 文档完整性：docs/16 规则总表无空描述。
"""
import ast
import json
import sys
from pathlib import Path

import openpyxl

REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "design_parser" / "rule_engine.py"
API = REPO / "api.py"
DOC16 = REPO / "docs" / "16_规则总表.md"
DOC09 = REPO / "docs" / "09_知识库来源追溯与规则映射_更新版.xlsx"
SAFETY_PY = REPO / "design_parser" / "safety_rules.py"
SAFETY_JSON = REPO / "design_parser" / "mappings" / "safety_distances.json"

INTENTIONAL_UNROUTED = {"R007_1", "R007_2"}
KNOWN_UNMAPPED = {"燃气管", "电缆线路"}  # 已标注待核对归属
KNOWN_NO_SPEC = {"压缩空气管"}  # 国标表7.6.3 无档位，R-SAFE-006 不适用


def dict_keys(path, name):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name and isinstance(node.value, ast.Dict):
                    return [k.value for k in node.value.keys]
    return []


def main():
    fails, warns, infos = [], [], []
    engine_rules = set(dict_keys(ENGINE, "ALL_RULES"))
    routing = {}
    tree = ast.parse(API.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "RULE_ROUTING" and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        routing[k.value] = [e.value for e in v.elts]
    routed = set().union(*routing.values()) if routing else set()
    unrouted = sorted(engine_rules - routed)
    for rid in unrouted:
        (infos if rid in INTENTIONAL_UNROUTED else warns).append(f"未路由：{rid}")

    # 09 追溯完整性
    wb = openpyxl.load_workbook(DOC09, data_only=True)
    ws = wb["规则映射"]
    traced = {}
    for row in ws.iter_rows(min_row=2):
        rid = row[0].value
        if rid:
            traced[rid] = (row[3].value, row[9].value)
    missing = sorted(engine_rules - set(traced))
    for rid in missing:
        fails.append(f"09 追溯缺失：{rid}")
    for rid, (src, ev) in traced.items():
        if not src or str(src).strip() in ("", "—", "-"):
            fails.append(f"09 无 Source ID：{rid}")
        if not ev or str(ev).strip() in ("", "—", "-"):
            fails.append(f"09 无 Evidence：{rid}")
    infos.append(f"09 追溯行数：{len(traced)}（应 68）")

    # 16 表空描述
    t16 = DOC16.read_text(encoding="utf-8")
    empty_desc = []
    for line in t16.splitlines():
        if line.startswith("| ") and "规则ID" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 6 and cells[0] and not cells[5]:
                empty_desc.append(cells[0])
    for rid in empty_desc:
        fails.append(f"16 表描述为空：{rid}")

    # safety 配置-规则映射一致性
    sd = json.loads(SAFETY_JSON.read_text(encoding="utf-8"))
    clearances = {k for k in sd.get("wall_cable_clearances_mm", {}) if k != "note"}
    tree2 = ast.parse(SAFETY_PY.read_text(encoding="utf-8"))
    rule_ids = {}
    for node in ast.walk(tree2):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "rule_ids" for t in node.targets):
            if isinstance(node.value, ast.Dict):
                rule_ids = {k.value: v.value for k, v in zip(node.value.keys, node.value.values)}
    no_spec = sorted(set(rule_ids) - clearances)
    no_rule = sorted(clearances - set(rule_ids))
    for k in no_spec:
        (infos if k in KNOWN_NO_SPEC else warns).append(f"规则无配置档位：{k}")
    for k in no_rule:
        (infos if k in KNOWN_UNMAPPED else warns).append(f"配置无规则映射：{k}")

    print("== 规则健康检查 ==")
    for i in infos:
        print("INFO ", i)
    for w in warns:
        print("WARN ", w)
    for f in fails:
        print("FAIL ", f)
    print(f"== 汇总：FAIL={len(fails)} WARN={len(warns)} INFO={len(infos)} ==")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
