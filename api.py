# api.py —— 通信设计审查 Agent 完整服务
# 功能：文件识别、工程加载、规则审查、BOM 生成、纤芯分配、文档理解、LLM 报告生成
import sys
import os
import uuid
import tempfile
import shutil
import json
import re
import difflib
import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import httpx
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from design_parser.excel_reader import read_excel
from design_parser.pdf_reader import extract_text_from_pdf
from design_parser.package import ProjectPackage
from design_parser.project_data import ProjectData
from design_parser.rule_table_reader import find_rule_files, parse_rule_library
from design_parser.bom_fiber_reader import (
    find_excel_files, find_gpkg_files, workbook_summary,
    read_sheet_rows, gpkg_summary, read_gpkg_rows,
)
from design_parser.rule_engine import ALL_RULES, RuleContext
from design_parser.check_result import CheckResult
from schemas import (
    ApiResponse,
    CheckResultOut,
    RunRulesRequest,
)

LLM_API_URL = os.environ.get("LLM_API_URL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

def _check_llm_config():
    """检查 LLM 配置是否有效，无效则抛出 502 异常并给出明确提示。

    """
    if not LLM_API_URL or not LLM_API_URL.startswith("http"):
        raise HTTPException(502, "LLM 未配置：请设置环境变量 LLM_API_URL（需以 http:// 或 https:// 开头）")
    if not LLM_API_KEY:
        raise HTTPException(502, "LLM 未配置：请设置环境变量 LLM_API_KEY")
    if not LLM_MODEL:
        raise HTTPException(502, "LLM 未配置：请设置环境变量 LLM_MODEL")

RULE_ROUTING = {
    "完整设计图": [
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001"
    ],
    "场勘设计图": [
        "R001","R002","R003","R004","R005","R007"
    ],
    "竣工图": [
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001"
    ],
    "竣工图（含BOM）": [
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001"
    ],
    "设计图（含纤芯）": [
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001"
    ],
}

projects: Dict[str, ProjectData] = {}
last_full_results: Dict[str, List[CheckResult]] = {}

SERIOUS_SEVERITY_LEVELS = {"fatal"}

app = FastAPI(title="通信设计审查 Agent 工具", version="3.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level: <7} | {message}")
logger.add("api.log", rotation="10 MB", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}")

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """?????????{success:false, data:null, error:{code,message}}?"""
    return JSONResponse(
        status_code=exc.status_code,
        content=build_response(success=False, data=None,
                               error={"code": exc.status_code, "message": str(exc.detail)}),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """???????????? Traceback?"""
    logger.exception(f"?????: {exc}")
    return JSONResponse(
        status_code=500,
        content=build_response(success=False, data=None,
                               error={"code": 500, "message": "服务器内部错误"}),
    )

@app.get("/health")
async def health():
    return {"status": "ok"}

def get_project(project_id: str) -> ProjectData:
    proj = projects.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在或已过期")
    return proj

def build_response(data=None, success=True, error=None):
    return ApiResponse(success=success, data=data, error=error).model_dump()

def _count_cables(proj: ProjectData) -> int:
    """计算光缆总条数（非图层数），用于 R019 动态阈值判定。

    """
    return sum(len(feats) for name, feats in proj.layers.items() if "CABLE" in name.upper())

def _collect_serious_issues(results: list, total_cables: int = 0) -> List[dict]:
    """遍历审查结果，收集 severity='fatal' 且 passed=False 的阻断级问题。

    R019 动态阈值：当 R019 失败数 > 光缆总数/2 时，将所有 R019 失败也提升为阻断级。
    """
    serious = []
    r019_failures = []
    for r in results:
        if r.passed:
            continue
        if r.severity in SERIOUS_SEVERITY_LEVELS:
            serious.append({
                "rule_id": r.rule_id,
                "check_object": r.check_object,
                "error_description": r.error_description,
                "problem_location": r.problem_location,
            })
        elif r.rule_id == "R019":
            r019_failures.append(r)

    if total_cables > 0 and len(r019_failures) > total_cables / 2:
        for r in r019_failures:
            serious.append({
                "rule_id": r.rule_id,
                "check_object": r.check_object,
                "error_description": r.error_description,
                "problem_location": r.problem_location,
            })

    return serious

def inspect_file(file_path: str, original_filename: str) -> dict:
    suffix = Path(original_filename).suffix.lower()
    archive_exts = {'.zip', '.rar', '.qgz', '.7z'}
    is_archive = suffix in archive_exts
    archive_type = None
    files_inside = None
    missing_shp = None
    warnings = []

    if is_archive:
        archive_type = suffix.lstrip('.')
        try:
            pkg = ProjectPackage(file_path)
            all_items = list(pkg.temp_dir.rglob('*'))
            files_inside = [str(item.relative_to(pkg.temp_dir)) for item in all_items if item.is_file()]
            shp_groups = {}
            for f in files_inside:
                base = Path(f).stem.lower()
                ext = Path(f).suffix.lower()
                if ext in ['.shp', '.shx', '.dbf', '.prj']:
                    shp_groups.setdefault(base, []).append(ext)
            missing_shp = []
            for base, exts in shp_groups.items():
                required = {'.shp', '.shx', '.dbf', '.prj'}
                missing = required - set(exts)
                if missing:
                    shp_file = next((f for f in files_inside if Path(f).stem.lower() == base and Path(f).suffix.lower() == '.shp'), "")
                    missing_shp.append({
                        "layer_name": base,
                        "relative_path": shp_file,
                        "missing_extensions": sorted(missing),
                        "rule_id": "R001"
                    })
            if not missing_shp:
                missing_shp = None
            pkg.cleanup()
        except Exception as e:
            files_inside = [f"解压失败: {e}"]
            warnings.append(f"解压失败: {e}")
    else:
        files_inside = None

    category = _guess_file_category(original_filename, files_inside, warnings)
    can_parse = False
    if is_archive and files_inside:
        inside_str = " ".join(files_inside).upper()
        if any(ext in inside_str for ext in [".QGS", ".QGZ", ".SHP", ".GPKG"]):
            can_parse = True
    elif original_filename.lower().endswith(('.shp', '.gpkg', '.qgs')):
        can_parse = True

    return {
        "file_name": original_filename,
        "is_archive": is_archive,
        "archive_type": archive_type,
        "files_inside": files_inside,
        "file_category": category,
        "missing_shp_parts": missing_shp,
        "can_be_parsed": can_parse,
        "warnings": warnings,
    }

def _guess_file_category(filename: str, files_inside: list = None, warnings: list = None) -> str:
    """判定文件类别。

    判定顺序：
    1) 明确文件名/路径关键词（场勘/survey/field → survey_design）
    2) 工程目录和业务特征
    3) QGIS 工程文件存在性
    4) 无法确认时返回 unknown + warning
    """
    if warnings is None:
        warnings = []
    name_upper = filename.upper()

    survey_keywords = ["场勘", "SURVEY", "FIELD"]
    if any(kw in name_upper for kw in survey_keywords):
        return "场勘设计图"

    if "BOM" in name_upper or "物料" in name_upper:
        return "BOM表"
    if "纤芯" in name_upper or "FIBER" in name_upper:
        return "纤芯分配表"
    if "规程" in name_upper or "SPEC" in name_upper:
        return "施工规程"
    if "图层" in name_upper or "字段说明" in name_upper or "LAYER" in name_upper:
        return "图层字段说明"

    if files_inside:
        inside_str = " ".join(files_inside).upper()

        if ".QGS" in inside_str or ".QGZ" in inside_str:
            if "BOM" in inside_str:
                return "竣工图（含BOM）"
            if "纤芯" in inside_str:
                return "设计图（含纤芯）"
            return "完整设计图"
        if any(ext in inside_str for ext in [".SHP", ".GPKG"]):
            return "场勘设计图"


    if name_upper.endswith(".QGS") or name_upper.endswith(".QGZ"):
        return "QGIS工程"
    if name_upper.endswith(".SHP"):
        return "SHP图层"
    if name_upper.endswith(".XLS") or name_upper.endswith(".XLSX"):
        return "Excel表格"
    if name_upper.endswith(".CSV"):
        return "CSV数据"
    if name_upper.endswith(".PDF"):
        return "PDF文档"

    warnings.append("无法确认文件类别，返回 unknown")
    return "未知文件"

def collect_unrecognized_fields(proj: ProjectData) -> List[Dict[str, str]]:
    """收集未在 layer_mapping.yaml 中定义的字段"""
    yaml_path = Path(__file__).parent / "design_parser" / "mappings" / "layer_mapping.yaml"
    if not yaml_path.exists():
        return []
    
    with open(yaml_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    layers_config = config.get('layers', {})
    
    unrecognized = []
    for layer_name, feats in proj.layers.items():
        if not feats:
            continue
        first_feat = feats[0]
        actual_fields = set(first_feat.properties.keys())
        
        matched_config = None
        for cfg_key in layers_config:
            if cfg_key.upper() in layer_name.upper():
                matched_config = layers_config[cfg_key]
                break
        
        if matched_config is None:
            for f in actual_fields:
                unrecognized.append({"layer": layer_name, "field": f})
        else:
            field_map = matched_config.get('field_map', {})
            candidate_fields = set()
            for std_field, candidates in field_map.items():
                if candidates is None:
                    continue
                if isinstance(candidates, list):
                    candidate_fields.update(candidates)
                else:
                    candidate_fields.add(str(candidates))
            for f in actual_fields:
                if f not in candidate_fields:
                    unrecognized.append({"layer": layer_name, "field": f})
    
    return unrecognized

def _load_layer_mapping_config() -> dict:
    """加载 layer_mapping.yaml（文件缺失时返回空配置）。"""
    yaml_path = Path(__file__).parent / "design_parser" / "mappings" / "layer_mapping.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _normalize_field_token(name) -> str:
    """归一化字段名：仅保留字母数字并转大写，用于忽略大小写与下划线差异。"""
    return re.sub(r"[^A-Za-z0-9]", "", str(name)).upper()


def _known_official_fields(config: dict) -> set:
    """汇总官方字段清单：required_fields + 各图层 field_lengths + field_map 候选名（归一化）。"""
    known = set()
    for layer_cfg in config.get("layers", {}).values():
        known.update(_normalize_field_token(k) for k in layer_cfg.get("field_lengths", {}))
        for candidates in layer_cfg.get("field_map", {}).values():
            if isinstance(candidates, list):
                known.update(_normalize_field_token(c) for c in candidates)
            elif candidates is not None:
                known.add(_normalize_field_token(candidates))
    for fields in config.get("required_fields", {}).values():
        known.update(_normalize_field_token(f) for f in fields)
    return known


def _suggest_standard_field(field: str, field_map: dict):
    """尝试给出标准字段映射建议，返回 (标准键, 来源, 置信度)。"""
    norm = _normalize_field_token(field)
    best_std, best_source, best_score = None, None, 0.0

    for std_field, candidates in field_map.items():
        if candidates is None:
            continue
        cands = candidates if isinstance(candidates, list) else [candidates]
        for cand in cands:
            cand_norm = _normalize_field_token(cand)
            if cand_norm == norm:
                return std_field, "field_map_exact", 1.0
            score = difflib.SequenceMatcher(None, norm, cand_norm).ratio()
            if score >= 0.82 and max(len(norm), len(cand_norm)) >= 6 and score > best_score:
                best_std, best_source, best_score = std_field, "field_map_fuzzy", score
        std_norm = _normalize_field_token(std_field)
        if std_norm == norm:
            return std_field, "standard_key_exact", 1.0
        score = difflib.SequenceMatcher(None, norm, std_norm).ratio()
        if score >= 0.82 and max(len(norm), len(std_norm)) >= 6 and score > best_score:
            best_std, best_source, best_score = std_field, "standard_key_fuzzy", score

    if best_std is None:
        return None, None, None
    return best_std, best_source, round(best_score, 2)


def suggest_unrecognized_field_mappings(proj: ProjectData) -> List[Dict]:
    """收集未在 layer_mapping.yaml field_map 中定义的字段，并给出映射建议。"""
    config = _load_layer_mapping_config()
    layers_config = config.get("layers", {})
    known_official = _known_official_fields(config)

    results = []
    for layer_name, feats in proj.layers.items():
        if not feats:
            continue
        actual_fields = set(feats[0].properties.keys())

        matched_config = None
        for cfg_key in layers_config:
            if cfg_key.upper() in layer_name.upper():
                matched_config = layers_config[cfg_key]
                break

        if matched_config is None:
            for f in sorted(actual_fields):
                results.append({
                    "layer": layer_name,
                    "field": f,
                    "suggested_standard_field": None,
                    "suggestion_source": None,
                    "suggestion_confidence": None,
                    "known_official_field": _normalize_field_token(f) in known_official,
                    "note": "图层未在 layer_mapping.yaml 中配置，无法给出映射建议",
                })
            continue

        field_map = matched_config.get("field_map", {})
        candidate_fields = set()
        for candidates in field_map.values():
            if candidates is None:
                continue
            if isinstance(candidates, list):
                candidate_fields.update(candidates)
            else:
                candidate_fields.add(str(candidates))

        for f in sorted(actual_fields):
            if f in candidate_fields:
                continue
            std_field, source, confidence = _suggest_standard_field(f, field_map)
            is_official = _normalize_field_token(f) in known_official
            if is_official:
                note = "官方字段清单或 field_lengths 已登记，但尚未加入 field_map；建议补充映射"
            elif source:
                note = "与 field_map 中候选字段相似，建议人工确认后补充映射"
            else:
                note = "未知字段，需人工确认是否保留或映射"
            results.append({
                "layer": layer_name,
                "field": f,
                "suggested_standard_field": std_field,
                "suggestion_source": source,
                "suggestion_confidence": confidence,
                "known_official_field": is_official,
                "note": note,
            })

    return results


@app.post("/agent/inspect-file", response_model=ApiResponse)
async def inspect_single_file(file: UploadFile = File(...)):
    """单文件识别（Excel/PDF/CSV/SHP/DBF/压缩包等）：返回类别与解析建议，不入库。"""
    original_filename = file.filename or "unknown"
    content = await file.read()
    suffix = Path(original_filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(content)
        tmp.close()
        info = inspect_file(tmp.name, original_filename)
        return build_response(data=info)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


@app.post("/project/load", response_model=ApiResponse)
async def load_project(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix
    if suffix.lower() not in ('.zip', '.rar'):
        raise HTTPException(status_code=400, detail="仅支持 zip/rar 格式")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.close()
        proj_id = str(uuid.uuid4())[:8]
        proj = ProjectData(tmp.name)
        projects[proj_id] = proj
        return build_response(data={"project_id": proj_id})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {e}")
    finally:
        Path(tmp.name).unlink(missing_ok=True)

@app.get("/project/{project_id}/layers", response_model=ApiResponse)
async def get_layers(project_id: str):
    proj = get_project(project_id)
    infos = proj.get_layer_info()
    return build_response(data=infos)


def _project_roots(proj):
    """返回项目的解压根目录列表（外层/内层/包装）。"""
    roots = []
    pkg = getattr(proj, "package", None)
    if pkg is not None:
        roots.append(pkg.temp_dir)
    outer = getattr(proj, "outer_package", None)
    if outer is not None and outer.temp_dir not in roots:
        roots.append(outer.temp_dir)
    for ip in getattr(proj, "inner_packages", []) or []:
        if ip.temp_dir not in roots:
            roots.append(ip.temp_dir)
    return roots


def _find_table_file(roots, file_name):
    for root in roots:
        for p in Path(root).rglob(file_name):
            if p.is_file():
                return p
    return None


@app.get("/project/{project_id}/bom-tables", response_model=ApiResponse)
async def get_bom_tables(project_id: str):
    """列出项目中的 BOM 物料表（Excel）及前 50 行样例。"""
    proj = get_project(project_id)
    files = []
    for root in _project_roots(proj):
        for f in find_excel_files(Path(root), kinds=("bom",)):
            files.append(workbook_summary(f, row_limit=50))
    return build_response(data={"files": files})


@app.get("/project/{project_id}/fiber-tables", response_model=ApiResponse)
async def get_fiber_tables(project_id: str):
    """列出项目中的纤芯数据：纤芯表格（Excel）与 BOX/CABLE/SRO 矢量层（GPKG）。"""
    proj = get_project(project_id)
    workbooks, vectors = [], []
    for root in _project_roots(proj):
        root_p = Path(root)
        for f in find_excel_files(root_p, kinds=("fiber",)):
            workbooks.append(workbook_summary(f, row_limit=50))
        for g in find_gpkg_files(root_p):
            vectors.append(gpkg_summary(g))
    return build_response(data={"workbooks": workbooks, "vectors": vectors})


@app.get("/project/{project_id}/table-data", response_model=ApiResponse)
async def get_table_data(project_id: str, file: str, sheet: Optional[str] = None,
                         limit: int = 100, filter: Optional[str] = None,
                         page: int = 1, page_size: Optional[int] = None):
    """读取指定表格数据：file 为文件名，sheet 可省；GPKG 按层读取。"""
    proj = get_project(project_id)
    p = _find_table_file(_project_roots(proj), file)
    if p is None:
        raise HTTPException(404, f"未找到表格文件: {file}")
    limit = max(1, min(limit, 1000))
    if p.suffix.lower() == ".gpkg":
        return build_response(data=read_gpkg_rows(p, limit=limit))
    return build_response(data=read_sheet_rows(p, sheet=sheet, limit=limit, filter=filter, page=page, page_size=page_size))



@app.get("/project/{project_id}/rule-library", response_model=ApiResponse)
async def get_rule_library(project_id: str):
    """返回官方规则库解析结果：校验规则 + 图层字段说明 + 可执行条件。"""
    proj = get_project(project_id)
    for root in _project_roots(proj):
        files = find_rule_files(Path(root))
        if files:
            return build_response(data=parse_rule_library(files[0]))
    return build_response(data={
        "file": "", "validation_rules": [],
        "field_specs": {}, "executable_rules": [],
    })


@app.get("/project/{project_id}/relations", response_model=ApiResponse)
async def get_relations(project_id: str, include_distances: bool = True):
    """上下游关系建模：CABLE.ORIGINE/EXTREMITE → 设备对象，BOITE/SITE 引用字段，端点距离统计。"""
    proj = get_project(project_id)
    data = proj.get_relations(include_distances=include_distances)
    data["project_id"] = project_id
    return build_response(data=data)


@app.get("/project/{project_id}/procedure-kb", response_model=ApiResponse)
async def get_procedure_kb(project_id: str, keyword: Optional[str] = None):
    """规程知识库检索：返回《施工规程知识库.xlsx》结构化条目，可按关键词过滤。"""
    from design_parser.procedure_reader import find_procedure_files, search_procedure_kb
    proj = get_project(project_id)
    for root in _project_roots(proj):
        files = find_procedure_files(Path(root))
        if files:
            return build_response(data=search_procedure_kb(files[0], keyword or ""))
    return build_response(data={"file": "", "entries": []})


@app.get("/project/{project_id}/gis-check", response_model=ApiResponse)
async def get_gis_check(project_id: str, tolerance: float = 0.5):
    """GIS 空间检查（R-GIS-001~006）：范围重叠/包含/自环/端点重合，容差默认 0.5 米。"""
    from design_parser.gis_rules import run_gis_checks
    proj = get_project(project_id)
    return build_response(data=run_gis_checks(proj, tolerance_m=tolerance))


@app.get("/project/{project_id}/safety-check", response_model=ApiResponse)
async def get_safety_check(project_id: str):
    """安全距离检查（R-SAFE-001~009）：离地高度/电力线交越净距/管线平行交叉净距。"""
    from design_parser.safety_rules import run_safety_checks
    proj = get_project(project_id)
    return build_response(data=run_safety_checks(proj))


@app.get("/project/{project_id}/engineering-data", response_model=ApiResponse)
async def get_engineering_data(project_id: str):
    """返回统一工程对象数据（objects.cable/boite/ptech），供 BOM / 纤芯分配工作流使用。"""
    proj = get_project(project_id)
    data = {
        "project_id": project_id,
        "project_type": getattr(proj, "project_type", "unknown"),
        "objects": proj.get_engineering_data()["objects"],
    }
    return build_response(data=data)


@app.get("/project/{project_id}/unrecognized-fields", response_model=ApiResponse)
async def get_unrecognized_fields(project_id: str):
    """返回未识别字段及映射建议，供适配/接入方补充 layer_mapping.yaml。"""
    proj = get_project(project_id)
    fields = suggest_unrecognized_field_mappings(proj)
    return build_response(data={
        "project_id": project_id,
        "count": len(fields),
        "unrecognized_fields": fields,
    })

@app.get("/project/{project_id}/device/{code}", response_model=ApiResponse)
async def get_device(project_id: str, code: str, crs: Optional[str] = None):
    """查询设备（可用 crs 参数将坐标转换到目标坐标系，默认原始坐标系）。"""
    from design_parser.spatial_utils import reproject_coords
    proj = get_project(project_id)
    for layer_name, features in proj.layers.items():
        for feat in features:
            if feat.properties.get('CODE') == code or feat.properties.get('code') == code:
                geom = None if feat._geometry is None else feat.get_coordinates()
                out_crs = crs or feat.original_crs
                if geom is not None and crs:
                    geom = reproject_coords(geom, feat.original_crs, crs)
                return build_response(data={
                    "layer": layer_name,
                    "properties": feat.properties,
                    "geometry": geom,
                    "geometry_type": feat.geometry_type.value if feat.geometry_type else None,
                    "crs": out_crs,
                })
    raise HTTPException(status_code=404, detail="设备未找到")
@app.get("/project/{project_id}/trace/{code}", response_model=ApiResponse)
async def get_trace(project_id: str, code: str):
    proj = get_project(project_id)
    connections = []
    for name in proj.layers:
        if "CABLE" in name.upper():
            cables = proj.get_unified_objects(name)
            for cable in cables:
                if cable.start_device == code or cable.end_device == code:
                    connections.append({
                        "cable_code": cable.code,
                        "start_device": cable.start_device,
                        "end_device": cable.end_device,
                        "length": cable.length
                    })
    return build_response(data=connections)

@app.get("/project/{project_id}/rules", response_model=ApiResponse)
async def list_rules(project_id: str):
    rules = [{"rule_id": rid, "available": func is not None} for rid, func in ALL_RULES.items()]
    return build_response(data=rules)

@app.post("/project/{project_id}/rules/run", response_model=ApiResponse)
async def run_rules(project_id: str, req: RunRulesRequest):
    proj = get_project(project_id)
    results: List[CheckResult] = []
    if req.rule_ids:
        for rid in req.rule_ids:
            params = (req.params or {}).get(rid, {})
            res = proj.run_rule(rid, **params)
            results.extend(res)
    else:
        results = proj.run_all_rules(rule_params=req.params or {})
    output = [CheckResultOut(**r.model_dump()).model_dump() for r in results]
    return build_response(data=output)

@app.get("/project/{project_id}/cable/{code}/length", response_model=ApiResponse)
async def get_cable_length(project_id: str, code: str):
    proj = get_project(project_id)
    for name in proj.layers:
        if "CABLE" in name.upper():
            cables = proj.get_unified_objects(name)
            for cable in cables:
                if cable.code == code or cable.id == code:
                    length = cable.length or (cable.geometry.length if cable.geometry else None)
                    return build_response(data={"cable_code": code, "length": length, "unit": "meters"})
    raise HTTPException(status_code=404, detail="光缆未找到")

@app.get("/project/{project_id}/stats/devices", response_model=ApiResponse)
async def get_device_stats(project_id: str):
    proj = get_project(project_id)
    counts = {}
    total = 0
    for layer_name, features in proj.layers.items():
        if features and features[0].geometry_type and features[0].geometry_type.value == "point":
            cnt = len(features)
            counts[layer_name] = cnt
            total += cnt
    return build_response(data={"total_devices": total, "by_layer": counts})

@app.post("/project/{project_id}/rules/run-all-and-cache", response_model=ApiResponse)
async def run_all_and_cache(project_id: str):
    proj = get_project(project_id)
    results = proj.run_all_rules()
    last_full_results[project_id] = results
    output = [CheckResultOut(**r.model_dump()).model_dump() for r in results]
    return build_response(data=output)

@app.get("/project/{project_id}/export", response_model=ApiResponse)
async def export_results(project_id: str):
    if project_id not in last_full_results:
        raise HTTPException(status_code=404, detail="请先执行全量审查")
    results = last_full_results[project_id]
    output = [CheckResultOut(**r.model_dump()).model_dump() for r in results]
    return build_response(data=output)

@app.post("/agent/full-pipeline")
async def full_pipeline(
    file: UploadFile = File(None),
    file_url: Optional[str] = Body(None)
):
    """全流程：文件识别 → 工程加载 → 审查 → 调用 LLM 生成报告"""
    if file is not None:
        original_filename = file.filename
        content = await file.read()
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                content = resp.content
                original_filename = file_url.rstrip("/").split("/")[-1]
                if not original_filename or "." not in original_filename:
                    original_filename = "downloaded_file.zip"
                suffix = Path(original_filename).suffix
        except Exception as e:
            raise HTTPException(400, f"下载文件失败: {e}")
    else:
        raise HTTPException(400, "请提供 file 或 file_url")
    logger.info(f"收到文件: {original_filename}（{len(content)} 字节）")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    archive_path = tmp.name

    try:
        file_info = inspect_file(archive_path, original_filename)
        if not file_info["can_be_parsed"]:
            raise HTTPException(400, detail="文件不可解析，无法继续")

        proj = ProjectData(archive_path)
        project_id = str(uuid.uuid4())[:8]
        projects[project_id] = proj

        review_results = proj.run_all_rules()
        last_full_results[project_id] = review_results
        layers_info = proj.get_layer_info() if hasattr(proj, 'get_layer_info') else []

        failures = [r for r in review_results if not r.passed]
        total_checks = len(review_results)
        passed_count = total_checks - len(failures)
        failed_count = len(failures)

        total_cables = _count_cables(proj)
        serious_issues = _collect_serious_issues(review_results, total_cables)

        if serious_issues:
            blocking_reasons = []
            fix_suggestions = []
            for issue in serious_issues:
                rid = issue.get("rule_id", "?")
                obj = issue.get("check_object", "?")
                desc = issue.get("error_description", "?")
                blocking_reasons.append(f"规则 {rid}: {obj} — {desc}")
                if rid in ("R005", "R005_4"):
                    fix_suggestions.append(
                        f"请核对 {obj} 的 CODE/ORIGINE/EXTREMITE 是否与设备图层一致：{desc}"
                    )
                elif rid in ("R010", "R024"):
                    fix_suggestions.append(
                        f"请检查 {obj} 的几何位置是否准确落在对应设备上：{desc}"
                    )
                elif rid in ("R019", "R020", "R030"):
                    fix_suggestions.append(
                        f"请核实 {obj} 的容量数据或关联关系：{desc}"
                    )
                elif rid in ("R001", "R002", "R003", "R004"):
                    fix_suggestions.append(
                        f"请检查设计文件完整性或图层命名规范：{desc}"
                    )
                else:
                    fix_suggestions.append(
                        f"请修复 {obj} 的异常：{desc}"
                    )
            partial_data = {
                "layers_info": layers_info if 'layers_info' in dir() else [],
                "review_summary": {
                    "total_checks": total_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                    "serious_issues": []
                } if not isinstance(serious_issues, list) else {
                    "total_checks": total_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                    "serious_issues": [
                        {
                            "rule_id": s.get("rule_id"),
                            "check_object": s.get("check_object"),
                            "error_description": s.get("error_description")
                        }
                        for s in serious_issues
                    ]
                }
            }
            return {
                "status": "blocked",
                "reason": "检测到严重问题，需人工修正后再生成报告",
                "blocking_reasons": blocking_reasons,
                "fix_suggestions": fix_suggestions,
                "partial_data": partial_data,
                "review_summary": {
                    "total_checks": total_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                    "serious_issues": serious_issues
                }
            }

        unrecognized_fields = collect_unrecognized_fields(proj)

        failures_by_rule = defaultdict(list)
        for r in review_results:
            if not r.passed:
                failures_by_rule[r.rule_id].append({
                    "object": r.check_object,
                    "desc": r.error_description,
                    "location": r.problem_location
                })

        review_summary = {}
        for rule_id, items in failures_by_rule.items():
            review_summary[rule_id] = {
                "total_failures": len(items),
                "sample_failures": items[:5]
            }

        layers_summary = [
            {
                "layer_name": l["layer_name"],
                "geometry_type": l["geometry_type"],
                "feature_count": l["feature_count"],
                "field_count": len(l["fields"])
            }
            for l in layers_info
        ]

        summary = {
            "file": file_info,
            "layers": layers_summary,
            "review_summary": review_summary,
            "unrecognized_fields": unrecognized_fields
        }

        system_prompt = (
            "你是一名通信工程设计报告专家。"
            "请严格根据提供的工程摘要 JSON 生成一份正式的审查报告。"
            "使用 Markdown 格式，包含以下章节：\n"
            "## 一、文件概况\n"
            "## 二、数据解析结果\n"
            "（如果摘要中存在 `unrecognized_fields`，请对每个未识别字段给出映射建议）\n"
            "## 三、审查结果\n"
            "（按审查类别分组，说明每类问题的总数和典型案例，**不要**罗列所有对象，除非样本数很少）\n"
            "## 四、整改建议\n"
            "## 五、结论\n"
            "禁止编造任何数据，所有数字必须来自摘要。"
        )
        user_message = f"请根据以下工程摘要生成审查报告：\n{json.dumps(summary, ensure_ascii=False, indent=2)}"

        llm_payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,
            "stream": False
        }
        headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}

        _check_llm_config()
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(LLM_API_URL, json=llm_payload, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(502, f"LLM 调用失败: {resp.text}")
            data = resp.json()
            final_report = data["choices"][0]["message"]["content"]

        return {
            "status": "success",
            "project_id": project_id,
            "final_report": final_report,
            "layers_info": layers_info
        }

    finally:
        Path(archive_path).unlink(missing_ok=True)

@app.post("/agent/auto-review")
async def auto_review(
    file: UploadFile = File(None),
    file_url: Optional[str] = Body(None)
):
    """自动识别文件类型，执行对应规则集，返回审查摘要"""
    if file is not None:
        original_filename = file.filename
        content = await file.read()
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                content = resp.content
                original_filename = file_url.rstrip("/").split("/")[-1]
                if not original_filename or "." not in original_filename:
                    original_filename = "downloaded_file.zip"
                suffix = Path(original_filename).suffix
        except Exception as e:
            raise HTTPException(400, f"下载文件失败: {e}")
    else:
        raise HTTPException(400, "请提供 file 或 file_url")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    archive_path = tmp.name

    try:
        file_info = inspect_file(archive_path, original_filename)

        reviewable_categories = list(RULE_ROUTING.keys())
        if file_info["file_category"] not in reviewable_categories:
            return {
                "status": "not_reviewable",
                "file_category": file_info["file_category"],
                "message": f"文件类别为「{file_info['file_category']}」，不属于智能审查范围，请转交其他 Agent 处理",
                "file_info": file_info
            }

        proj = ProjectData(archive_path)
        project_id = str(uuid.uuid4())[:8]
        projects[project_id] = proj

        rule_ids = RULE_ROUTING.get(file_info["file_category"], [])
        review_results = []
        for rid in rule_ids:
            try:
                res = proj.run_rule(rid)
                review_results.extend(res)
            except Exception as e:
                review_results.append(CheckResult(
                    check_object=f"规则 {rid}",
                    passed=False,
                    problem_location="规则执行异常",
                    actual_value=str(e),
                    expected_value="正常执行",
                    rule_id=rid,
                    error_description=f"规则执行出错: {e}"
                ))

    finally:
        Path(archive_path).unlink(missing_ok=True)

    failures_by_rule = defaultdict(list)
    for r in review_results:
        if not r.passed:
            failures_by_rule[r.rule_id].append({
                "object": r.check_object,
                "desc": r.error_description,
                "location": r.problem_location
            })

    review_summary = {}
    for rule_id, items in failures_by_rule.items():
        review_summary[rule_id] = {
            "total_failures": len(items),
            "sample_failures": items[:5]
        }

    return {
        "status": "success",
        "project_id": project_id,
        "file_category": file_info["file_category"],
        "file_info": file_info,
        "review_summary": review_summary
    }

PROJECT_TYPE_MAP = {
    "场勘设计图": "survey_design",
    "完整设计图": "full_design",
    "竣工图": "as_built",
    "竣工图（含BOM）": "as_built",
    "设计图（含纤芯）": "full_design",
    "QGIS工程": "unknown",
    "未知文件": "unknown",
}

@app.post("/agent/data-pipeline")
async def data_pipeline(
    file: UploadFile = File(None),
    file_url: Optional[str] = Body(None),
    excel_limit: int = Body(500),
    pdf_chars: int = Body(3000),
    include_tables: bool = Body(False),
):
    """
    纯数据流水线：不经过 LLM，直接将解析与审查的结构化 JSON 返回。
    供下游 Agent 直接消费。

    输出契约同时包含：
    - 新契约字段：success, project_name, project_type, summary, review, warnings, errors
    - 旧字段（硬约束）：file_info, layers, review_results, serious_issues_detected, excel_data, pdf_text
    """
    if file is not None:
        original_filename = file.filename
        content = await file.read()
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                content = resp.content
                original_filename = file_url.rstrip("/").split("/")[-1]
                if not original_filename or "." not in original_filename:
                    original_filename = "downloaded_file.zip"
                suffix = Path(original_filename).suffix
        except Exception as e:
            raise HTTPException(400, f"下载文件失败: {e}")
    else:
        raise HTTPException(400, "请提供 file 或 file_url")

    logger.info(f"收到文件: {original_filename}（{len(content)} 字节）")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    archive_path = tmp.name

    project_id = str(uuid.uuid4())

    result = {
        "success": False,
        "project_id": project_id,
        "project_name": "",
        "project_type": "unknown",
        "summary": {"layer_count": 0, "object_count": 0},
        "review": {"total_rules": 0, "passed_rules": 0, "failed_rules": 0, "issues": []},
        "warnings": [],
        "errors": [],
        "status": "error",
        "file_info": {},
        "layers": [],
        "review_results": [],
        "serious_issues_detected": False,
        "excel_data": {},
        "pdf_text": {},
        "engineering_data": {"project_id": project_id, "project_type": "unknown", "objects": {"cable": [], "boite": [], "ptech": [], "site": [], "infrastructure": []}},
        "bom_tables": {"files": []},
        "fiber_tables": {"workbooks": [], "vectors": []},
    }

    proj = None
    try:
        file_info = inspect_file(archive_path, original_filename)
        result["file_info"] = file_info
        result["project_name"] = Path(original_filename).stem
        result["project_type"] = PROJECT_TYPE_MAP.get(
            file_info.get("file_category", ""), "unknown"
        )
        logger.info(f"文件分类: {file_info.get('file_category', '')} → project_type={result['project_type']}")
        if file_info.get("warnings"):
            result["warnings"].extend(file_info["warnings"])

        if not file_info.get("can_be_parsed", False):
            result["status"] = "not_parseable"
            result["errors"].append(file_info.get("reason", "无法解析，请检查文件格式"))
            return result

        try:
            proj = ProjectData(archive_path)
            proj.project_type = result.get("project_type", "unknown")
            projects[project_id] = proj
            result["layers"] = proj.get_layer_info()
            logger.info(f"工程加载完成: {len(result['layers'])} 个图层")
            result["engineering_data"] = {
                "project_id": project_id,
                "project_type": getattr(proj, "project_type", "unknown"),
                "objects": proj.get_engineering_data()["objects"],
            }
            if include_tables:
                bom_files, fiber_wb, fiber_vec = [], [], []
                for root in _project_roots(proj):
                    root_p = Path(root)
                    for f in find_excel_files(root_p, kinds=("bom",)):
                        bom_files.append(workbook_summary(f, row_limit=50))
                    for f in find_excel_files(root_p, kinds=("fiber",)):
                        fiber_wb.append(workbook_summary(f, row_limit=50))
                    for g in find_gpkg_files(root_p):
                        fiber_vec.append(gpkg_summary(g))
                result["bom_tables"] = {"files": bom_files}
                result["fiber_tables"] = {"workbooks": fiber_wb, "vectors": fiber_vec}
            for _f in getattr(proj, "extract_failures", []):
                result["warnings"].append(f"解压失败: {_f}")
        except Exception as e:
            logger.warning(f"工程数据加载失败: {e}")
            result["status"] = "project_load_failed"
            result["errors"].append(f"工程数据加载失败: {e}")
            return result

        reviewable_categories = set(RULE_ROUTING.keys())
        rule_ids = RULE_ROUTING.get(file_info.get("file_category", ""), [])
        has_gis = bool(proj.layers)

        if rule_ids and has_gis and file_info.get("file_category", "") in reviewable_categories:
            all_results = []
            try:
                for rid in rule_ids:
                    if rid not in ALL_RULES:
                        continue
                    rule_func = ALL_RULES[rid]
                    ctx = RuleContext(proj)
                    rule_params = {}
                    if rid == "R002":
                        lower_layers = [l.lower() for l in proj.layers]
                        if "boite" in lower_layers:
                            rule_params["required_layers"] = ["BOITE"]
                    try:
                        res = rule_func(ctx, **rule_params)
                        if isinstance(res, list):
                            all_results.extend(res)
                        else:
                            all_results.append(res)
                    except Exception as e:
                        all_results.append(CheckResult(
                            check_object=f"规则 {rid}",
                            passed=False,
                            problem_location="规则执行异常",
                            actual_value=str(e),
                            expected_value="正常执行",
                            rule_id=rid,
                            error_description=f"规则执行出错: {e}"
                        ))

                review_results_out = [CheckResultOut(**r.model_dump()).model_dump() for r in all_results]
                result["review_results"] = review_results_out

                total_rules = len(all_results)
                passed_rules = sum(1 for r in all_results if r.passed)
                failed_rules = total_rules - passed_rules
                issues = []
                for r in all_results:
                    if not r.passed:
                        issues.append({
                            "rule_id": r.rule_id,
                            "object_type": r.check_object,
                            "object_id": r.problem_location or "",
                            "field": "",
                            "severity": r.severity or "warning",
                            "message": r.error_description or "",
                            "source": "rule_engine",
                        })
                result["review"] = {
                    "total_rules": total_rules,
                    "passed_rules": passed_rules,
                    "failed_rules": failed_rules,
                    "issues": issues,
                }

                total_cables = _count_cables(proj)
                serious_issues = _collect_serious_issues(all_results, total_cables)
                result["serious_issues_detected"] = bool(serious_issues)
            except Exception as e:
                logger.warning(f"规则审查执行异常: {e}")
                result["review_results"] = [{
                    "check_object": "审查引擎",
                    "passed": False,
                    "rule_id": "pipeline",
                    "error_description": f"规则审查执行异常: {e}"
                }]
                result["errors"].append(f"规则审查执行异常: {e}")
        else:
            result["review_results"] = []
            result["review_message"] = (
                "跳过审查（非可审查类别或无 GIS 图层数据）"
            )
            result["warnings"].append("跳过审查（非可审查类别或无 GIS 图层数据）")
        logger.info(
            f"规则审查完成: {result['review']['passed_rules']}/{result['review']['total_rules']} 通过，"
            f"{result['review']['failed_rules']} 失败"
        )

        try:
            raw_excel = proj.get_excel_data()
            excel_data = {}
            for key, rows in raw_excel.items():
                excel_data[key] = rows[:excel_limit]
            result["excel_data"] = excel_data
        except Exception as e:
            logger.warning(f"Excel 数据提取失败: {e}")
            result["excel_data"] = {"error": str(e)}
            result["warnings"].append(f"Excel 数据提取失败: {e}")

        try:
            pkg = ProjectPackage(archive_path)
            pdf_paths = list(pkg.temp_dir.rglob("*.pdf"))
            pdf_text = {}
            for fp in pdf_paths:
                try:
                    full = extract_text_from_pdf(str(fp))
                    pdf_text[fp.name] = full[:pdf_chars]
                except Exception as e:
                    pdf_text[fp.name] = f"提取失败: {e}"
            result["pdf_text"] = pdf_text
            pkg.cleanup()
        except Exception as e:
            logger.warning(f"PDF 文本提取失败: {e}")
            result["pdf_text"] = {"error": str(e)}
            result["warnings"].append(f"PDF 文本提取失败: {e}")

        layer_count = len(result["layers"])
        object_count = sum(l.get("feature_count", 0) for l in result["layers"])
        result["summary"] = {
            "layer_count": layer_count,
            "object_count": object_count,
        }

        result["status"] = "success"
        result["success"] = True
        logger.info(
            f"流水线完成: project_id={project_id} success={result['success']} "
            f"图层={result['summary']['layer_count']} 对象={result['summary']['object_count']}"
        )

    except Exception as e:
        logger.exception(f"数据流水线全局异常: {e}")
        result["status"] = "error"
        result["success"] = False
        result["errors"].append(str(e))
    finally:
        Path(archive_path).unlink(missing_ok=True)
        if proj is not None:
            try:
                proj.cleanup()
            except Exception:
                pass

    return result

@app.post("/agent/orchestrate")
async def orchestrate(
    file: UploadFile = File(None),
    file_url: Optional[str] = Body(None)
):
    """总控 Agent：文件识别→审查→文档理解→决策→BOM/纤芯→综合报告"""
    if file is not None:
        original_filename = file.filename
        content = await file.read()
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                content = resp.content
                original_filename = file_url.rstrip("/").split("/")[-1]
                if not original_filename or "." not in original_filename:
                    original_filename = "downloaded_file.zip"
                suffix = Path(original_filename).suffix
        except Exception as e:
            raise HTTPException(400, f"下载文件失败: {e}")
    else:
        raise HTTPException(400, "请提供 file 或 file_url")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    archive_path = tmp.name

    project_id = None
    try:
        file_info = inspect_file(archive_path, original_filename)
        if not file_info.get("can_be_parsed", False):
            return {
                "status": "rejected",
                "reason": "文件不可解析，流程终止",
                "file_info": file_info,
                "final_report": None
            }

        proj = ProjectData(archive_path)
        project_id = str(uuid.uuid4())[:8]
        projects[project_id] = proj

        has_geodata = getattr(proj, 'has_qgis', False)

        async def run_review():
            if not has_geodata:
                return None, False
            reviewable = ["完整设计图", "场勘设计图", "竣工图"]
            if file_info["file_category"] not in reviewable:
                return None, False
            rule_ids = RULE_ROUTING.get(file_info["file_category"], [])
            results = []
            for rid in rule_ids:
                try:
                    res = proj.run_rule(rid)
                    results.extend(res)
                except Exception as e:
                    results.append(CheckResult(
                        check_object=f"规则 {rid}",
                        passed=False,
                        problem_location="规则执行异常",
                        actual_value=str(e),
                        expected_value="正常执行",
                        rule_id=rid,
                        error_description=f"规则执行出错: {e}"
                    ))
            failures_by_rule = defaultdict(list)
            serious_issue_list = []
            for r in results:
                if not r.passed:
                    failures_by_rule[r.rule_id].append({
                        "object": r.check_object,
                        "desc": r.error_description,
                        "location": r.problem_location
                    })
            review_summary = {}
            for rid, items in failures_by_rule.items():
                review_summary[rid] = {
                    "total_failures": len(items),
                    "sample_failures": items[:5]
                }
            total_checks = len(results)
            passed_count = total_checks - sum(v["total_failures"] for v in review_summary.values())
            total_cables = _count_cables(proj)
            serious_issue_list = _collect_serious_issues(results, total_cables)
            serious = bool(serious_issue_list)

            layers_info = proj.get_layer_info()
            return {
                "layers_info": layers_info,
                "review_summary": review_summary,
                "serious_issues": serious,
                "serious_issue_list": serious_issue_list,
                "total_checks": total_checks,
                "passed_count": passed_count,
                "failed_count": sum(v["total_failures"] for v in review_summary.values())
            }, serious

        async def analyze_documents():
            pkg = ProjectPackage(archive_path)
            search_dirs = [pkg.temp_dir]
            excel_files, pdf_files = [], []
            for d in search_dirs:
                for f in d.rglob("*"):
                    if f.suffix.lower() in ('.xlsx', '.xls'):
                        excel_files.append(f)
                    elif f.suffix.lower() == '.pdf':
                        pdf_files.append(f)

            excel_summary = {}
            for f in excel_files:
                try:
                    raw = read_excel(str(f))
                    rows = list(raw.values())[0] if raw else []
                    columns = list(rows[0].keys()) if rows else []
                    excel_summary[f.name] = {
                        "total_rows": len(rows),
                        "columns": columns,
                        "sample_rows": rows[:10]
                    }
                except Exception as e:
                    excel_summary[f.name] = {"error": str(e)}

            pdf_texts = {}
            for f in pdf_files:
                try:
                    full = extract_text_from_pdf(str(f))
                    pdf_texts[f.name] = full[:3000]
                except Exception as e:
                    logger.warning(f"PDF 处理异常: {f.name}: {e}")
                    pass

            if not excel_summary and not pdf_texts:
                return None

            doc_prompt = (
                "你是一个通信工程项目文档分析专家。请根据 Excel 摘要和 PDF 内容，"
                "用自然语言总结：1. Excel 主要物料及数量级，有无异常；2. PDF 规程的关键步骤；"
                "3. 两者是否存在不匹配。禁止编造数据。"
            )
            msg_data = {
                "excel": {k: {
                    "total_rows": v.get("total_rows"),
                    "columns": v.get("columns"),
                    "sample_rows": v.get("sample_rows", []),
                } for k, v in excel_summary.items()},
                "pdf": pdf_texts,
            }
            user_msg = json.dumps(msg_data, ensure_ascii=False, indent=2)

            if len(user_msg) > 5000:
                for k in msg_data["excel"]:
                    if "sample_rows" in msg_data["excel"][k]:
                        msg_data["excel"][k]["sample_rows"] = msg_data["excel"][k]["sample_rows"][:5]
                user_msg = json.dumps(msg_data, ensure_ascii=False, indent=2)

            if len(user_msg) > 5000:
                for k in msg_data["excel"]:
                    msg_data["excel"][k]["sample_rows"] = []
                user_msg = json.dumps(msg_data, ensure_ascii=False, indent=2)

            llm_payload = {
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": doc_prompt},
                    {"role": "user", "content": user_msg}
                ],
                "temperature": 0.3, "stream": False
            }
            headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
            _check_llm_config()
            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    resp = await client.post(LLM_API_URL, json=llm_payload, headers=headers)
                    if resp.status_code == 200:
                        return resp.json()["choices"][0]["message"]["content"]
                    else:
                        logger.error(f"文档理解 LLM 调用失败: {resp.text}")
                        return None
            except Exception as e:
                logger.error(f"文档理解异常: {e}")
                return None
            finally:
                pkg.cleanup()

        review_task = asyncio.create_task(run_review())
        doc_task = asyncio.create_task(analyze_documents())
        review_data, serious_issues = await review_task
        doc_understanding = await doc_task

        if serious_issues and review_data is not None:
            review_info = review_data
            partial_data = {
                "layers_info": review_info.get("layers_info", []),
                "review_summary": review_info.get("review_summary", {}),
                "passed_checks": review_info.get("passed_count", 0),
                "total_checks": review_info.get("total_checks", 0),
            }
            MAX_SERIOUS_ISSUES = 100
            raw_serious_list = review_info.get("serious_issue_list", [])
            total_serious_count = len(raw_serious_list)
            is_truncated = total_serious_count > MAX_SERIOUS_ISSUES
            serious_list_for_response = raw_serious_list[:MAX_SERIOUS_ISSUES]

            blocking_reasons = []
            fix_suggestions = []
            for issue in serious_list_for_response:
                rid = issue.get("rule_id", "?")
                obj = issue.get("check_object", "?")
                desc = issue.get("error_description", "?")
                blocking_reasons.append(f"规则 {rid}: {obj} — {desc}")
                if rid in ("R005", "R005_4"):
                    fix_suggestions.append(
                        f"请核对 {obj} 的 CODE/ORIGINE/EXTREMITE 是否与设备图层一致：{desc}"
                    )
                elif rid in ("R010", "R024"):
                    fix_suggestions.append(
                        f"请检查 {obj} 的几何位置是否准确落在对应设备上：{desc}"
                    )
                elif rid in ("R019", "R020", "R030"):
                    fix_suggestions.append(
                        f"请核实 {obj} 的容量数据或关联关系：{desc}"
                    )
                elif rid in ("R001", "R002", "R003", "R004"):
                    fix_suggestions.append(
                        f"请检查设计文件完整性或图层命名规范：{desc}"
                    )
                else:
                    fix_suggestions.append(
                        f"请修复 {obj} 的异常：{desc}"
                    )
            return {
                "status": "blocked_with_degradation",
                "partial_data": partial_data,
                "blocking_reasons": blocking_reasons,
                "fix_suggestions": fix_suggestions,
                "truncated": is_truncated,
                "total_serious_issues": total_serious_count,
                "max_displayed_issues": MAX_SERIOUS_ISSUES,
                "reason": "检测到严重问题，已降级返回部分结构化数据",
                "final_report": None,
                "review_summary": {
                    "total_checks": review_info.get("total_checks", 0),
                    "passed": review_info.get("passed_count", 0),
                    "failed": review_info.get("failed_count", 0),
                    "serious_issues": serious_list_for_response,
                    "serious_issues_truncated": is_truncated,
                    "total_serious_issues": total_serious_count,
                    "layers_info": review_info.get("layers_info", [])
                }
            }

        if review_data is not None:
            layers_summary = [
                {"layer_name": l["layer_name"], "geometry_type": l["geometry_type"],
                 "feature_count": l["feature_count"], "field_count": len(l["fields"])}
                for l in review_data.get("layers_info", [])
            ]
            final_context = {
                "file_info": file_info,
                "layers": layers_summary,
                "review_summary": review_data.get("review_summary", {}),
                "document_understanding": doc_understanding,
                "status": "审查通过" if not serious_issues else "存在严重问题"
            }
            system_prompt = (
                "你是一名通信工程设计报告专家。请根据审查数据和文档理解，"
                "生成一份综合项目报告。必须包含以下章节：\n"
                "## 一、文件概况\n"
                "## 二、审查结果\n"
                "## 三、附件文档分析\n"
                "## 四、整改建议\n"
                "## 五、结论\n"
                "禁止编造数据。"
            )
        else:
            final_context = {
                "file_info": file_info,
                "document_understanding": doc_understanding,
                "status": "仅包含附件文档，无设计图数据"
            }
            system_prompt = (
                "你是一名通信工程项目文档分析专家。请根据文档理解结果，生成一份文档分析报告。"
                "包含以下章节：\n"
                "## 一、文件概况\n"
                "## 二、Excel 物料分析\n"
                "## 三、PDF 规程分析\n"
                "## 四、结论与建议\n"
                "禁止编造数据。"
            )

        user_message = json.dumps(final_context, ensure_ascii=False, indent=2)

        llm_payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,
            "stream": False
        }
        headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}

        _check_llm_config()
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(LLM_API_URL, json=llm_payload, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(502, f"LLM 调用失败: {resp.text}")
            data = resp.json()
            final_report = data["choices"][0]["message"]["content"]

        return {
            "status": "success",
            "project_id": project_id,
            "has_geodata": has_geodata,
            "serious_issues_detected": serious_issues if review_data else False,
            "final_report": final_report,
            "document_understanding": doc_understanding
        }

    finally:
        Path(archive_path).unlink(missing_ok=True)

@app.get("/project/{project_id}/excel")
async def get_excel(project_id: str, filename: str = None):
    proj = get_project(project_id)
    data = proj.get_excel_data(filename)
    return build_response(data=data)

@app.get("/project/{project_id}/pdf")
async def get_pdf(project_id: str, filename: str = None):
    proj = get_project(project_id)
    text = proj.get_pdf_text(filename)
    return build_response(data={"text": text})

def main():
    """启动 API 服务"""
    import socket
    import uvicorn
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", 8000))
    except OSError:
        print("端口 8000 已被占用：请先关闭旧服务进程，再重新启动。")
        sys.exit(1)
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
