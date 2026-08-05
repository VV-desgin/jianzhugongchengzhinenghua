"""BOM / 纤芯数据解析：统一读取 Excel 表格与 GPKG 矢量图层为结构化数据。

供 BOM 生成、纤芯分配工作流消费。真实数据形态：
- BOM_LIST.xlsx / material_code_*.xls（BOM 物料清单与物料编码库）
- SRO-*-TOPO_*.xlsx（纤芯拓扑表）
- BOX / CABLE / SRO.gpkg（纤芯矢量图层）

约定：
- 表格统一输出 {"file", "kind", "sheets": [{"name", "row_count", "rows"}]}
- 行数据统一输出 {"file", "sheet", "headers", "rows"}，首行为表头；
- 超大表（如 BOM_LIST 104 万行）只读取前 limit 行，避免内存与响应膨胀。
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

BOM_KEYWORDS = ("bom", "material", "list", "物料", "编码")
FIBER_KEYWORDS = ("fiber", "fibre", "topo", "splice", "纤芯", "接续", "分配",
                  "上游", "下游", "upstream", "downstream")
EXCEL_EXTS = (".xlsx", ".xls")
_FILE_CACHE: Dict[str, tuple] = {}


def _cached_file(path: Path, key: str, builder):
    """按（路径+键+修改时间）缓存解析结果，文件变动后自动重算。"""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0
    ck = (str(path), key, mtime)
    hit = _FILE_CACHE.get(ck)
    if hit is not None:
        return hit
    result = builder()
    _FILE_CACHE[ck] = result
    return result



DEFAULT_ROW_LIMIT = 100
HEADER_SCAN_ROWS = 10


def _detect_header_index(raw_rows: List[list]) -> int:
    """自动识别真实表头行：多级合并表头（如 SRO TOPO）前几行为元信息。
    优先取“无数字单元格最多”的行（表头多为纯文本列名），兼容合并表头占位空格。
    """
    if not raw_rows:
        return 0
    scan = raw_rows[:HEADER_SCAN_ROWS]
    total_counts = [
        sum(1 for c in r if c is not None and str(c).strip() != "")
        for r in scan
    ]
    first = total_counts[0]
    mx_total = max(total_counts)
    if first >= 5 or first == mx_total:
        return 0
    alpha_counts = [
        sum(1 for c in r if c is not None and str(c).strip() and not any(ch.isdigit() for ch in str(c).strip()))
        for r in scan
    ]
    mx_alpha = max(alpha_counts)
    if mx_alpha >= 5 and mx_alpha >= first * 2:
        return alpha_counts.index(mx_alpha)
    if mx_total - first >= 5 and mx_total >= first * 2:
        return total_counts.index(mx_total)
    return 0


def classify_table(name: str) -> str:
    """按文件名判断表格类型：bom / fiber / other。"""
    low = name.lower()
    if any(k in low for k in FIBER_KEYWORDS):
        return "fiber"
    if any(k in low for k in BOM_KEYWORDS):
        return "bom"
    return "other"


def find_excel_files(root: Path, kinds: tuple = ("bom", "fiber")) -> List[Path]:
    """递归查找指定类型的 Excel 文件（.xlsx/.xls）。"""
    out = []
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in EXCEL_EXTS:
            if classify_table(f.name) in kinds:
                out.append(f)
    return sorted(out)


def find_gpkg_files(root: Path) -> List[Path]:
    """递归查找 GPKG 矢量文件（纤芯 BOX/CABLE/SRO 等）。"""
    return sorted(f for f in root.rglob("*.gpkg") if f.is_file())


def _to_serializable(value: Any) -> Any:
    """把 Excel/矢量属性值转为可 JSON 序列化的基础类型。"""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):  # datetime/date
        return value.isoformat()
    return str(value)


def _xlsx_sheets(path: Path) -> List[Dict[str, Any]]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return [{"name": ws.title, "row_count": ws.max_row or 0} for ws in wb.worksheets]
    finally:
        wb.close()


def _xls_sheets(path: Path) -> List[Dict[str, Any]]:
    import xlrd
    wb = xlrd.open_workbook(str(path))
    return [{"name": sh.name, "row_count": sh.nrows} for sh in wb.sheets()]


def list_sheet_names(path: Path) -> List[str]:
    """返回 Excel 文件所有工作表名（只读元数据，适合超大文件）。"""
    if path.suffix.lower() == ".xlsx":
        return [s["name"] for s in _xlsx_sheets(path)]
    return [s["name"] for s in _xls_sheets(path)]


def workbook_summary(path: Path, row_limit: int = DEFAULT_ROW_LIMIT) -> Dict[str, Any]:
    """返回 Excel 工作簿摘要（缓存：按文件+修改时间）。"""
    def build():
        suffix = path.suffix.lower()
        sheets = _xlsx_sheets(path) if suffix == ".xlsx" else _xls_sheets(path)
        for s in sheets:
            data = read_sheet_rows(path, sheet=s["name"], limit=row_limit)
            s["rows"] = data["rows"]
            s["headers"] = data["headers"]
        return {"file": path.name, "kind": classify_table(path.name), "sheets": sheets}
    return _cached_file(path, f"summary:{row_limit}", build)
def read_sheet_rows(path: Path, sheet: Optional[str] = None,
                    limit: int = DEFAULT_ROW_LIMIT, filter: Optional[str] = None,
                    page: int = 1, page_size: Optional[int] = None) -> Dict[str, Any]:
    """读取指定工作表数据，自动识别真实表头（兼容多级合并表头）。

    支持：
    - limit/（page+page_size）分页；默认页大小为 limit（上限 1000）；
    - filter：字段值包含关键字（忽畧大小写）。
    注意：使用 filter 时会全表扫描（大表可能较慢）。
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size if page_size is not None else limit), 1000))
    suffix = path.suffix.lower()
    raw_rows: List[list] = []
    if suffix == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            ws = next((w for w in wb.worksheets if w.title == sheet), wb.worksheets[0])
            sheet_name = ws.title
            for row in ws.iter_rows(values_only=True):
                raw_rows.append([_to_serializable(c) for c in row])
                if not filter and page == 1 and len(raw_rows) >= HEADER_SCAN_ROWS + page_size:
                    break
        finally:
            wb.close()
    else:
        import xlrd
        wb = xlrd.open_workbook(str(path))
        sh = next((s for s in wb.sheets() if s.name == sheet), wb.sheets()[0])
        sheet_name = sh.name
        for r_idx in range(sh.nrows):
            raw_rows.append([_to_serializable(sh.cell_value(r_idx, c)) for c in range(sh.ncols)])
            if not filter and page == 1 and len(raw_rows) >= HEADER_SCAN_ROWS + page_size:
                break
    header_idx = _detect_header_index(raw_rows)
    headers = raw_rows[header_idx] if raw_rows else []
    all_rows = raw_rows[header_idx + 1:]
    if filter:
        kw = filter.strip().lower()
        all_rows = [r for r in all_rows if any(kw in str(v).lower() for v in r if v is not None)]
    total = len(all_rows)
    start_idx = (page - 1) * page_size
    rows = all_rows[start_idx:start_idx + page_size]
    return {"file": path.name, "kind": classify_table(path.name),
            "sheet": sheet_name, "headers": headers, "rows": rows,
            "total": total, "page": page, "page_size": page_size}

def gpkg_summary(path: Path) -> Dict[str, Any]:
    """返回 GPKG 矢量图层摘要：图层名、要素数、字段清单、前 DEFAULT_ROW_LIMIT 行。"""
    import fiona
    with fiona.open(path) as src:
        fields = list(src.schema["properties"].keys())
        count = len(src)
        rows = []
        for i, feat in enumerate(src):
            if i >= DEFAULT_ROW_LIMIT:
                break
            rows.append([_to_serializable(feat["properties"].get(f)) for f in fields])
        return {
            "file": path.name,
            "layer": src.name,
            "count": count,
            "fields": fields,
            "rows": rows,
        }


def read_gpkg_rows(path: Path, limit: int = DEFAULT_ROW_LIMIT) -> Dict[str, Any]:
    """读取 GPKG 图层前 limit 行（与 read_sheet_rows 结构一致）。"""
    import fiona
    limit = max(1, min(int(limit), 1000))
    with fiona.open(path) as src:
        fields = list(src.schema["properties"].keys())
        rows = []
        for i, feat in enumerate(src):
            if i >= limit:
                break
            rows.append([_to_serializable(feat["properties"].get(f)) for f in fields])
        return {"file": path.name, "kind": "fiber", "sheet": src.name,
                "headers": fields, "rows": rows}
