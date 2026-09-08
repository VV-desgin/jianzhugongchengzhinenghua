"""官方编码格式模板：前缀结构 + 各段长度规则（当前仅根节点白名单被规则引擎使用）。

- 配置：design_parser/mappings/code_format_templates.json
- 规则引擎只消费 root_codes（R008 根节点白名单）；
  完整的模板匹配机制（split_code/match_template/auto_match）暂无调用方，已移除。
  若后续要落地官方 CODE 格式校验（如 PBO-<Trigramme>-<Quartier>-<n°>），
  需先补规则与测试再恢复模板匹配。
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import List

_TEMPLATE_PATH = Path(__file__).parent / "mappings" / "code_format_templates.json"


@lru_cache(maxsize=1)
def load_templates() -> dict:
    return json.loads(_TEMPLATE_PATH.read_text(encoding="utf-8"))


def root_codes() -> List[str]:
    return [c.upper() for c in load_templates().get("root_codes", [])]


def is_root_code(code: str) -> bool:
    up = str(code or "").upper()
    return any(up == r or up.startswith(r) for r in root_codes())
