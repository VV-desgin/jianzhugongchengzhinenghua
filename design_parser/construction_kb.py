"""B6 施工指令后端素材：读取官方固定知识库（施工规程 v2.0 + 设计对象-物料-工序映射表）。

供 Dify 施工工具/总控在生成施工指令时补充「工序级作业卡素材」：
- procedures：官方施工规程知识库 v2.0 的 10 条 PCP 安装工序（步骤/材料/工艺/测试/安全/验收/来源）；
- materials：设计对象-物料-工序映射表（官方 29+ 物料码 → 设计对象/对应工序）。

数据源固定为 docs/官方固定数据/（可用环境变量 DESIGN_PARSER_FIXED_DATA_DIR 覆盖，部署时指向 /root/docs/官方固定数据）。
"""

import os
from pathlib import Path
from typing import Any, Dict, List

import openpyxl

_PROC_FILE = "施工规程知识库v2.0.xlsx"
_MAT_FILE = "设计对象-物料-工序映射表.xlsx"
_CACHE: Dict[str, Any] = {}


def _fixed_dir() -> Path:
    env = os.environ.get("DESIGN_PARSER_FIXED_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "docs" / "官方固定数据"


def _cached(path: Path, loader):
    key = str(path)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    hit = _CACHE.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    data = loader(path)
    _CACHE[key] = (mtime, data)
    return data


def _rows(path: Path, sheet_keyword: str = ""):
    """读取 Excel 全部行（首行为表头），返回 (headers, rows)。"""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = None
        if sheet_keyword:
            for s in wb.worksheets:
                if sheet_keyword in s.title:
                    ws = s
                    break
        ws = ws or wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    return headers, rows[1:]


def _cell(row, headers, name) -> str:
    try:
        idx = headers.index(name)
    except ValueError:
        return ""
    v = row[idx] if idx < len(row) else None
    return "" if v is None else str(v).strip()


def _load_procedures(path: Path) -> List[Dict[str, Any]]:
    headers, rows = _rows(path, "PCP")
    out = []
    for i, row in enumerate(rows, 1):
        name = _cell(row, headers, "工序名称")
        if not name:
            continue
        out.append({
            "index": i,
            "object": _cell(row, headers, "施工对象"),
            "name": name,
            "steps": _cell(row, headers, "操作步骤"),
            "materials": _cell(row, headers, "使用材料"),
            "process_requirements": _cell(row, headers, "工艺要求"),
            "test_requirements": _cell(row, headers, "测试要求"),
            "safety_requirements": _cell(row, headers, "安全要求（原文未有直接说明，根据原文施工要求推演结果）"),
            "acceptance_criteria": _cell(row, headers, "验收标准"),
            "common_errors": _cell(row, headers, "常见错误（原文未有直接说明，根据原文施工要求推演结果）"),
            "source": _cell(row, headers, "页码及章节来源"),
        })
    return out


def _load_materials(path: Path) -> List[Dict[str, Any]]:
    headers, rows = _rows(path, "设计对象")
    out = []
    for i, row in enumerate(rows, 1):
        code = _cell(row, headers, "物料编码")
        if not code:
            continue
        out.append({
            "index": _cell(row, headers, "序号") or str(i),
            "object_type": _cell(row, headers, "设计对象类型"),
            "sub_type": _cell(row, headers, "子类型"),
            "material_code": code,
            "original_description": _cell(row, headers, "原文物料描述"),
            "material_description": _cell(row, headers, "物料描述"),
            "unit": _cell(row, headers, "单位"),
            "layer": _cell(row, headers, "设计图层"),
            "procedure": _cell(row, headers, "对应工序"),
        })
    return out


def _match(item: Dict[str, Any], keyword: str) -> bool:
    kw = keyword.strip().upper()
    if not kw:
        return True
    return any(kw in str(v).upper() for v in item.values() if isinstance(v, str))


def get_construction_kb(object_type: str = "", material_code: str = "") -> Dict[str, Any]:
    """返回施工指令素材：工序作业卡（procedures）+ 物料-工序映射（materials）+ 提示（warnings）。"""
    fixed = _fixed_dir()
    warnings: List[str] = []
    proc_path = fixed / _PROC_FILE
    mat_path = fixed / _MAT_FILE

    procedures = _cached(proc_path, _load_procedures) if proc_path.exists() else []
    materials = _cached(mat_path, _load_materials) if mat_path.exists() else []
    if not procedures and not materials:
        warnings.append(f"官方固定知识库缺失或为空（{fixed}），返回空结构")

    if object_type:
        procedures = [p for p in procedures if _match(p, object_type)]
        materials = [m for m in materials if _match(m, object_type)]
    if material_code:
        materials = [m for m in materials if m["material_code"] == material_code]
        if not materials:
            warnings.append(f"物料编码 {material_code} 未匹配到官方物料-工序映射表")

    return {
        "query": {"object_type": object_type, "material_code": material_code},
        "procedures": procedures,
        "materials": materials,
        "warnings": warnings,
    }
