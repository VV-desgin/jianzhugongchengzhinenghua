"""官方编码格式模板：前缀结构 + 各段长度规则。

- 配置：design_parser/mappings/code_format_templates.json
- 模板 = 前缀段规则（prefix_segments）+ 主体段规则（segments，含可选段/multi 段）
- 对任意新设备类型：只需在配置中新增/复用模板，auto_match 自动按规则匹配，无需改代码
- 根节点（POP/SRO）白名单也来自该配置，供 R008 等规则使用
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

_TEMPLATE_PATH = Path(__file__).parent / "mappings" / "code_format_templates.json"


@lru_cache(maxsize=1)
def load_templates() -> Dict:
    return json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def root_codes() -> List[str]:
    return [c.upper() for c in load_templates().get("root_codes", [])]


def split_code(code: str, separator: Optional[str] = None) -> List[str]:
    sep = separator or load_templates().get("separator", "-")
    return [p for p in str(code).split(sep) if p != ""]


def _seg_ok(seg: str, rule: Dict) -> bool:
    charset = rule.get("charset", "A-Z0-9")
    lo, hi = int(rule.get("min", 1)), int(rule.get("max", 99))
    pattern = f"^[{charset}]{{{lo},{hi}}}$"
    return bool(re.match(pattern, seg, re.IGNORECASE))


def match_template(code: str, template: Dict) -> Optional[Dict]:
    """按模板解析编码；返回 {prefix, segments} 或 None。"""
    parts = split_code(code, template.get("separator", "-"))
    pref_rules = template.get("prefix_segments", [])
    body_rules = template.get("segments", [])
    if len(parts) < len(pref_rules) + 1:
        return None
    for i, rule in enumerate(pref_rules):
        if not _seg_ok(parts[i], rule):
            return None
    body = parts[len(pref_rules):]
    result = {"prefix": parts[:len(pref_rules)], "segments": {}}
    idx = 0
    for rule in body_rules:
        if rule.get("multi"):
            rest = body[idx:]
            total = sum(len(s) for s in rest) + (len(rest) - 1)
            if not rest or total > int(rule.get("max", 99)) or not all(_seg_ok(s, rule) for s in rest):
                return None
            result["segments"][rule["name"]] = "-".join(rest)
            idx = len(body)
            continue
        if idx >= len(body):
            if rule.get("optional"):
                continue
            return None
        seg = body[idx]
        if not _seg_ok(seg, rule):
            if rule.get("optional"):
                continue
            return None
        result["segments"][rule["name"]] = seg
        idx += 1
    if idx < len(body):
        return None
    return result


def auto_match(code: str, field: Optional[str] = None) -> Optional[Dict]:
    """自动匹配模板；可指定字段（如 CABLE_AMONT）优先。返回带模板信息的解析结果。"""
    data = load_templates()
    candidates = [t for t in data.get("templates", [])]
    if field:
        candidates = sorted(candidates, key=lambda t: 0 if t.get("field") == field else 1)
    for t in candidates:
        m = match_template(code, t)
        if m:
            return {"template": t["id"], "description": t.get("description", ""), **m}
    return None


def is_root_code(code: str) -> bool:
    up = str(code or "").upper()
    return any(up == r or up.startswith(r) for r in root_codes())
