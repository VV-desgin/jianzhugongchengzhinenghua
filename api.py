# api.py —— 通信设计审查 Agent 完整服务
# 功能：文件识别、工程加载、规则审查、BOM 生成、纤芯分配、文档理解、LLM 报告生成
import sys
import os
import hashlib
import uuid
import tempfile
import shutil
import json
import re
import difflib
import asyncio
import time
from collections import defaultdict
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.concurrency import run_in_threadpool
import httpx
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from design_parser.excel_reader import read_excel
from design_parser.business_params import load_business_params
from design_parser.pdf_reader import extract_text_from_pdf
from design_parser.package import ProjectPackage
from design_parser.project_data import ProjectData
from design_parser.rule_table_reader import find_rule_files, parse_rule_library
from design_parser.bom_fiber_reader import (
    find_excel_files, find_gpkg_files, workbook_summary,
    read_sheet_rows, gpkg_summary, read_gpkg_rows,
)
from design_parser.rule_engine import ALL_RULES, RuleContext, SEVERITY_MAP, FIBER_SHEET_KEYWORDS

def _effective_severity(r):
    """有效严重等级：SEVERITY_MAP 优先，未配置默认 warning（P0-01）。"""
    return SEVERITY_MAP.get(r.rule_id) or r.severity or "warning"


def _normalize_severities(results):
    """统一严重等级：SEVERITY_MAP 覆盖；未配置规则默认 warning（P0-01）。"""
    for r in results:
        if r.rule_id in SEVERITY_MAP:
            r.severity = SEVERITY_MAP[r.rule_id]
        elif r.severity is None:
            r.severity = "warning"
    return results


def _severity_counts(results):
    """按严重等级统计（P0-01）：warning 不计入 failed_rules。"""
    total = len(results)
    warning_rules = sum(
        1 for r in results
        if not r.passed and _effective_severity(r) == "warning"
    )
    failed_rules = sum(
        1 for r in results
        if not r.passed and _effective_severity(r) in {"error", "fatal"}
    )
    return {
        "total_rules": total,
        "warning_rules": warning_rules,
        "failed_rules": failed_rules,
        "passed_rules": total - warning_rules - failed_rules,
    }

from design_parser.check_result import CheckResult
from design_parser.problem_categories import CATEGORY_LABELS, problem_category_for
from schemas import (
    ApiResponse,
    CheckResultOut,
    RunRulesRequest,
    HealthResponse,
    DataPipelineResponse,
    BusinessParamsOut,
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
        "R-GIS-007","R-FIBER-003","R-LIFE-001","R034",  # 2026-08-24 TC-18/21/22/23 新规则
        "R006","R006_3","R006_4","R006_5","R006_6","R024","R025","R026","R029","R030","R031",  # 2026-08-23 接入未路由规则（全量扫描零误报）
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001","R-FIBER-002","R-BOM-001",
        "R005_1","R005_2","R005_3","R027","R028","R033"  # R005_1/R005_2 按官方 R-REL-001/002 口径启用（2026-08-16/22 按官方口径确认）
    ],
    "场勘设计图": [
        "R006","R031",  # 2026-08-23 接入（全量扫描零误报）
        "R001","R002","R003","R004","R005","R007"
    ],
    "竣工图": [
        "R-GIS-007","R-FIBER-003","R-LIFE-001","R034",  # 2026-08-24 TC-18/21/22/23 新规则
        "R006","R006_3","R006_4","R006_5","R006_6","R024","R025","R026","R029","R030","R031",  # 2026-08-23 接入未路由规则（全量扫描零误报）
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001","R-FIBER-002","R-BOM-001",
        "R005_1","R005_2","R005_3","R027","R028","R033"  # R005_1/R005_2 按官方 R-REL-001/002 口径启用（2026-08-16/22 按官方口径确认）
    ],
    "竣工图（含BOM）": [
        "R-GIS-007","R-FIBER-003","R-LIFE-001","R034",  # 2026-08-24 TC-18/21/22/23 新规则
        "R006","R006_3","R006_4","R006_5","R006_6","R024","R025","R026","R029","R030","R031",  # 2026-08-23 接入未路由规则（全量扫描零误报）
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001","R-FIBER-002","R-BOM-001",
        "R005_1","R005_2","R005_3","R027","R028","R033"  # R005_1/R005_2 按官方 R-REL-001/002 口径启用（2026-08-16/22 按官方口径确认）
    ],
    "设计图（含纤芯）": [
        "R-GIS-007","R-FIBER-003","R-LIFE-001","R034",  # 2026-08-24 TC-18/21/22/23 新规则
        "R006","R006_3","R006_4","R006_5","R006_6","R024","R025","R026","R029","R030","R031",  # 2026-08-23 接入未路由规则（全量扫描零误报）
        "R001","R002","R003","R004","R005","R005_4","R007","R008","R009",
        "R010","R011","R013","R014","R015","R016","R017","R018","R032",
        "R019","R020","R021","R022","R023","R-FIBER-001","R-FIBER-002","R-BOM-001",
        "R005_1","R005_2","R005_3","R027","R028","R033"  # R005_1/R005_2 按官方 R-REL-001/002 口径启用（2026-08-16/22 按官方口径确认）
    ],
    "Excel 工程包": [
        "R-FIBER-003","R-LIFE-001","R034",  # 2026-08-24 TC-21/22/23 新规则（R-GIS-007 需几何，Excel 跳过）
        "R006","R031",  # 2026-08-23 接入（Excel 案例零误报）
        "R005","R005_4","R007","R008","R009",
        "R011","R012","R016","R018","R019","R020","R021","R022","R032","R033","R-FIBER-001","R-BOM-001"
    ],
}

# 有界结果缓存：同一包（文件 SHA256 + 参数 + 规则版本）TTL 内秒回，避免评审/复测重复解析
_PIPELINE_CACHE_VERSION = "20260823-r005-negheight-r008-modepose-unrouted11-msg20260824-tc18-21-22-23-safe3m-safe-unmapped-skip-20260830"  # 规则/逻辑变更时递增，自动失效旧缓存
_PIPELINE_CACHE_TTL_S = 3600
_PIPELINE_CACHE_MAX_ENTRIES = 32
_PIPELINE_CACHE_MAX_BYTES = 64 * 1024 * 1024
_pipeline_cache: Dict[str, tuple] = {}  # key -> (ts, result)


def _pipeline_cache_key(content: bytes, filename: str, excel_limit: int, pdf_chars: int, include_tables: bool, compact: bool) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"{digest}|{filename}|{excel_limit}|{pdf_chars}|{int(include_tables)}|{int(compact)}|{_PIPELINE_CACHE_VERSION}"


def _pipeline_cache_get(key: str) -> Optional[dict]:
    now = time.time()
    entry = _pipeline_cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    if now - ts > _PIPELINE_CACHE_TTL_S:
        _pipeline_cache.pop(key, None)
        return None
    # 命中刷新 LRU 顺序（dict 插入序 = 最近使用序），使淘汰语义符合 LRU 而非 FIFO
    _pipeline_cache.pop(key, None)
    _pipeline_cache[key] = (ts, data)
    return data


def _pipeline_cache_put(key: str, data: dict) -> None:
    now = time.time()
    _pipeline_cache[key] = (now, data)
    # 惰性清理：过期项
    expired = [k for k, (ts, _d) in _pipeline_cache.items() if now - ts > _PIPELINE_CACHE_TTL_S]
    for k in expired:
        _pipeline_cache.pop(k, None)
    # LRU 条目上限（dict 保持插入序，popitem(last=False) 淘汰最旧）
    while len(_pipeline_cache) > _PIPELINE_CACHE_MAX_ENTRIES:
        _pipeline_cache.pop(next(iter(_pipeline_cache)))
    # 总字节上限（近似 json 长度）
    total = 0
    sizes = {}
    for k, (ts, d) in _pipeline_cache.items():
        try:
            sizes[k] = len(json.dumps(d, ensure_ascii=False, default=str))
        except Exception:
            sizes[k] = 1024 * 1024
        total += sizes[k]
    while total > _PIPELINE_CACHE_MAX_BYTES and _pipeline_cache:
        k = next(iter(_pipeline_cache))
        total -= sizes.get(k, 1024 * 1024)
        _pipeline_cache.pop(k, None)


projects: Dict[str, ProjectData] = {}
last_full_results: Dict[str, tuple] = {}  # project_id -> (ts, results)；随项目 TTL 过期清理

SERIOUS_SEVERITY_LEVELS = {"fatal"}

app = FastAPI(title="通信设计审查 Agent 工具", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=(
        r"http://(localhost|127\.0\.0\.1)(:\d+)?"
        r"|http://(118\.31\.127\.213|43\.138\.167\.41)(:\d+)?"
    ),
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level: <7} | {message}")
logger.add("api.log", rotation="10 MB", level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}")

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """HTTP 异常统一返回 {success:false, data:null, error:{code,message}} 结构。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=build_response(success=False, data=None,
                               error={"code": exc.status_code, "message": str(exc.detail)}),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """未捕获异常统一返回 500，并记录 Traceback。"""
    logger.exception(f"未处理异常: {exc}")
    return JSONResponse(
        status_code=500,
        content=build_response(success=False, data=None,
                               error={"code": 500, "message": "服务器内部错误"}),
    )

@app.get("/health", response_model=HealthResponse)
async def health():
    return {"status": "ok"}


@app.get("/tf/{filename}")
async def serve_test_file(filename: str):
    """临时测试桥接：提供 /tmp/tf 下的工程文件供 Dify remote_url 下载。"""
    if not _ENABLE_TF_BRIDGE:
        raise HTTPException(404, "file not found")
    base = Path("/tmp/tf")
    base_resolved = base.resolve()
    target = (base / filename).resolve()
    if not target.is_file() or not str(target).startswith(str(base_resolved) + os.sep):
        raise HTTPException(404, "file not found")
    return FileResponse(target, filename=filename)


@app.get("/agent/business-params", response_model=BusinessParamsOut)
async def business_params():
    """返回业务参数（损耗/预留/取整/利旧/纤芯/施工指令）。"""
    return build_response(success=True, data=load_business_params())


@app.post("/agent/bom")
async def agent_bom(
    project_id: Optional[str] = Body(None),
    engineering_data: Optional[dict] = Body(None),
):
    """后端标准 BOM 计算：设计对象→物料（官方映射表）→损耗/预留/取整（business_params）。

    输入 project_id（已解析项目）或 engineering_data（含 objects）。
    输出 bom_items（设计/损耗/预留/最终数量/计算依据/置信状态）+ summary。
    后端 BOM 计算，不再依赖 Dify BOM 工具 V0.6。
    """
    from design_parser.bom_builder import build_bom
    eng = None
    if project_id:
        proj = get_project(project_id)
        eng = {"project_id": project_id, "objects": proj.get_engineering_data()["objects"]}
    elif engineering_data:
        eng = engineering_data
    else:
        raise HTTPException(400, "请提供 project_id 或 engineering_data")
    try:
        result = build_bom(eng)
        return build_response(success=True, data=result)
    except Exception as e:
        logger.exception(f"BOM 计算失败: {e}")
        raise HTTPException(500, f"BOM 计算失败: {e}")

def get_project(project_id: str) -> ProjectData:
    proj = projects.get(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在或已过期")
    return proj


_PROJECT_TTL_SECONDS = 2 * 60 * 60  # 项目数据保留 2 小时，超时后清理临时文件


def _store_project(project_id: str, proj) -> None:
    """保存项目并记录创建时间；顺带清理过期项目，防止临时文件无限堆积。"""
    try:
        proj._created_at = time.time()
    except Exception:
        pass
    projects[project_id] = proj
    now = time.time()
    for pid in [
        k for k, v in list(projects.items())
        if now - getattr(v, "_created_at", now) > _PROJECT_TTL_SECONDS
    ]:
        old = projects.pop(pid, None)
        if old is not None:
            try:
                old.cleanup()
            except Exception:
                pass
            logger.info(f"清理过期项目: {pid}")
    for pid in [k for k, (ts, _r) in list(last_full_results.items()) if now - ts > _PROJECT_TTL_SECONDS]:
        last_full_results.pop(pid, None)



# 内网/保留地址前缀（SSRF 防护）
_SAFE_FETCH_MAX_BYTES = 200 * 1024 * 1024  # 200MB
_MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 上传文件上限 1GB（流式读取计数，防内存 DoS）
_ENABLE_TF_BRIDGE = os.environ.get("ENABLE_TF_BRIDGE", "1") == "1"  # /tf 测试桥开关：默认开启以支撑 Dify remote_url，生产可置 0 关闭


def _is_private_ip(host: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return True
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _validate_url_host(url: str) -> None:
    """校验 file_url 的协议与主机，拒绝本机/内网/保留地址（防 SSRF）；DNS 解析失败一律拒绝。"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "file_url 仅支持 http/https 协议")
    parsed = urlparse(url)
    if not parsed.hostname:
        raise HTTPException(400, "file_url 主机无效")
    host = parsed.hostname
    if host in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(400, "file_url 禁止访问本机/内网地址")
    import socket
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise HTTPException(400, f"file_url 无法解析主机: {host}")
    for info in infos:
        if _is_private_ip(info[4][0]):
            raise HTTPException(400, "file_url 禁止访问内网/保留地址")


def _safe_fetch_url_sync(url: str, max_bytes: int = _SAFE_FETCH_MAX_BYTES) -> bytes:
    """逐跳校验主机并流式下载（限制大小）；同步版本供线程池端点调用。"""
    current = url
    for _hop in range(6):
        _validate_url_host(current)
        resp = requests.get(current, stream=True, allow_redirects=False, timeout=30)
        try:
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    raise HTTPException(400, "file_url 重定向缺少 Location")
                current = str(requests.utils.urljoin(current, loc))
                continue
            resp.raise_for_status()
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(413, f"file_url 下载超过大小上限 {max_bytes // (1024*1024)}MB")
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            resp.close()
    raise HTTPException(400, "file_url 重定向次数过多")


async def _read_upload_bytes(file: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """流式读取上传文件，超限抛 413，避免匿名上传打爆内存。"""
    if max_bytes is None:
        max_bytes = _MAX_UPLOAD_BYTES
    data = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(413, f"上传文件超过大小上限 {max_bytes // (1024 * 1024)}MB")
    return bytes(data)


async def _safe_fetch_url(url: str, max_bytes: int = _SAFE_FETCH_MAX_BYTES) -> bytes:
    """async 包装：下载放入线程池，避免阻塞事件循环（供遗留 async 端点使用）。"""
    return await run_in_threadpool(_safe_fetch_url_sync, url, max_bytes)


def _read_upload_bytes_sync(file: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """同步流式读取上传文件（线程池端点使用），超限抛 413。"""
    if max_bytes is None:
        max_bytes = _MAX_UPLOAD_BYTES
    data = bytearray()
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > max_bytes:
            raise HTTPException(413, f"上传文件超过大小上限 {max_bytes // (1024 * 1024)}MB")
    return bytes(data)

def build_response(data=None, success=True, error=None):
    return ApiResponse(success=success, data=data, error=error).model_dump()

def _count_cables(proj: ProjectData) -> int:
    """计算光缆总条数（非图层数），用于 R019 动态阈值判定。

    """
    return sum(len(feats) for name, feats in proj.layers.items() if "CABLE" in name.upper())

def _collect_fiber_tables(proj, max_sheets=10, max_rows=200):
    """收集包内纤芯相关 Excel 表（供纤芯分配工具使用）。"""
    from design_parser.bom_fiber_reader import EXCEL_EXTS, list_sheet_names, read_sheet_rows
    import re
    out = []
    seen = set()
    for root in _project_roots(proj):
        try:
            files = sorted(Path(root).rglob("*"))
        except OSError:
            continue
        for f in files:
            if not f.is_file() or f.suffix.lower() not in EXCEL_EXTS:
                continue
            try:
                key = str(f.resolve())
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            try:
                names = list_sheet_names(f)
            except Exception:
                continue
            wanted = [
                n for n in names
                if n == "纤芯连接与分配"
                or any(k in n.lower() for k in FIBER_SHEET_KEYWORDS)
                or re.match(r"^(SRO|BPE|PBO)[-_]", n)
            ]
            for n in wanted[:max_sheets]:
                try:
                    data = read_sheet_rows(f, sheet=n, limit=max_rows)
                except Exception:
                    continue
                if data.get("headers"):
                    out.append({"file": f.name, "sheet": n,
                             "headers": data["headers"], "rows": data["rows"][:max_rows]})
    return out


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
    excel_official = False
    has_gis_files = False
    bom_sheet = False

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
            try:
                from design_parser.excel_adapter import excel_has_official_sheets
                for f in pkg.temp_dir.rglob("*"):
                    if f.is_file() and f.suffix.lower() in (".xlsx", ".xls") and excel_has_official_sheets(f):
                        excel_official = True
                        break
            except Exception:
                pass
            try:
                from design_parser.excel_adapter import excel_has_bom_sheet
                for f in pkg.temp_dir.rglob("*"):
                    if f.is_file() and f.suffix.lower() in (".xlsx", ".xls") and excel_has_bom_sheet(f):
                        bom_sheet = True
                        break
            except Exception:
                pass
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
            has_gis_files = True
            can_parse = True
        elif excel_official:
            can_parse = True
        elif bom_sheet:
            can_parse = True
    elif original_filename.lower().endswith(('.shp', '.gpkg', '.qgs')):
        can_parse = True
    elif original_filename.lower().endswith(('.xlsx', '.xls')):
        try:
            from design_parser.excel_adapter import excel_has_official_sheets, excel_has_bom_sheet
            excel_official = excel_has_official_sheets(Path(file_path))
            bom_sheet = excel_has_bom_sheet(Path(file_path))
            can_parse = excel_official or bom_sheet
        except Exception:
            can_parse = False
    if (excel_official or bom_sheet) and not has_gis_files:
        category = "Excel 工程包"

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
    inside_gis = False
    if files_inside:
        _inside = " ".join(files_inside).upper()
        inside_gis = any(_x in _inside for _x in [".QGS", ".QGZ", ".SHP", ".GPKG"])

    survey_keywords = ["场勘", "SURVEY", "FIELD"]
    if any(kw in name_upper for kw in survey_keywords):
        return "场勘设计图"

    if not inside_gis and ("BOM" in name_upper or "物料" in name_upper):
        return "BOM表"
    if not inside_gis and ("纤芯" in name_upper or "FIBER" in name_upper):
        return "纤芯分配表"
    if not inside_gis and ("规程" in name_upper or "SPEC" in name_upper):
        return "施工规程"
    if not inside_gis and ("图层" in name_upper or "字段说明" in name_upper or "LAYER" in name_upper):
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
def inspect_single_file(file: UploadFile = File(...)):
    """单文件识别（Excel/PDF/CSV/SHP/DBF/压缩包等）：返回类别与解析建议，不入库。"""
    original_filename = file.filename or "unknown"
    content = _read_upload_bytes_sync(file)
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
def load_project(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix
    if suffix.lower() not in ('.zip', '.rar'):
        raise HTTPException(status_code=400, detail="仅支持 zip/rar 格式")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = _read_upload_bytes_sync(file)
        tmp.write(content)
        tmp.close()
        proj_id = str(uuid.uuid4())
        proj = ProjectData(tmp.name)
        _store_project(proj_id, proj)
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
    fixed = Path(__file__).resolve().parent / "docs" / "官方固定数据" / "施工规程知识库v2.0.xlsx"
    if fixed.exists():
        return build_response(data=search_procedure_kb(fixed, keyword or ""))  # 固定官方规程（v2.0）
    proj = get_project(project_id)
    for root in _project_roots(proj):
        files = find_procedure_files(Path(root))
        if files:
            return build_response(data=search_procedure_kb(files[0], keyword or ""))
    return build_response(data={"file": "", "entries": []})


@app.get("/project/{project_id}/construction-kb", response_model=ApiResponse)
async def get_construction_kb_endpoint(project_id: str, object_type: str = "", material_code: str = ""):
    """施工指令素材（B6 后端素材版）：官方施工规程 PCP/工序 + 物料-工序映射表。"""
    get_project(project_id)
    from design_parser.construction_kb import get_construction_kb
    data = get_construction_kb(object_type=object_type or "", material_code=material_code or "")
    return build_response(data={"project_id": project_id, **data})


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


@app.get("/project/{project_id}/raw-file")
async def get_raw_file(project_id: str, file: str):
    """返回工程包内的原始文档文件（如 xlsx/shp/pdf），供下游读取。"""
    proj = get_project(project_id)
    target = Path(file).name  # 仅取文件名，防路径穿越
    roots = _project_roots(proj)
    matches = [p for root in roots for p in Path(root).rglob(target) if p.is_file()]
    if not matches:
        # 单文件上传会被重命名为临时名：按后缀唯一匹配兜底
        ext = Path(file).suffix.lower()
        candidates = [
            p for root in roots for p in Path(root).rglob("*")
            if p.is_file() and p.suffix.lower() == ext
        ]
        if len(candidates) == 1:
            return FileResponse(str(candidates[0]), filename=target)
    if matches:
        return FileResponse(str(matches[0]), filename=target)
    raise HTTPException(404, f"未找到文件: {file}")


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
def run_all_and_cache(project_id: str):
    proj = get_project(project_id)
    results = proj.run_all_rules()
    last_full_results[project_id] = (time.time(), results)
    output = [CheckResultOut(**r.model_dump()).model_dump() for r in results]
    return build_response(data=output)

@app.get("/project/{project_id}/export", response_model=ApiResponse)
def export_results(project_id: str):
    entry = last_full_results.get(project_id)
    if entry is None or time.time() - entry[0] > _PROJECT_TTL_SECONDS:
        last_full_results.pop(project_id, None)
        raise HTTPException(status_code=404, detail="请先执行全量审查（结果已过期）")
    results = entry[1]
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
        content = await _read_upload_bytes(file)
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            content = await _safe_fetch_url(file_url)
            original_filename = file_url.rstrip("/").split("/")[-1]
            if not original_filename or "." not in original_filename:
                original_filename = "downloaded_file.zip"
            suffix = Path(original_filename).suffix
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"下载文件失败: {e}")
    else:
        raise HTTPException(400, "请提供 file 或 file_url")

    request_id = uuid.uuid4().hex[:12]
    logger.info(f"[{request_id}] 收到文件: {original_filename}（{len(content)} 字节）")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    archive_path = tmp.name

    try:
        file_info = inspect_file(archive_path, original_filename)
        if not file_info["can_be_parsed"]:
            raise HTTPException(400, detail="文件不可解析，无法继续")

        proj = ProjectData(archive_path)
        project_id = str(uuid.uuid4())
        _store_project(project_id, proj)

        review_results = proj.run_all_rules()
        last_full_results[project_id] = (time.time(), review_results)
        layers_info = proj.get_layer_info() if hasattr(proj, 'get_layer_info') else []

        # P0-01：warning 不计入 failed_count，按严重等级统计（不改动 serious_issues 判定）
        total_checks = len(review_results)
        failed_count = sum(
            1 for r in review_results
            if not r.passed and _effective_severity(r) in {"error", "fatal"}
        )
        warning_count = sum(
            1 for r in review_results
            if not r.passed and _effective_severity(r) == "warning"
        )
        passed_count = total_checks - failed_count - warning_count
        total_cables = _count_cables(proj)
        serious_issues = _collect_serious_issues(review_results, total_cables)

        if serious_issues:
            blocking_reasons = []
            fix_suggestions = []
            for issue in serious_issues:
                rid = issue.get("rule_id", "未知")
                obj = issue.get("check_object", "未知")
                desc = issue.get("error_description", "未知")
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
                "layers_info": layers_info,
                "review_summary": {
                    "total_checks": total_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                    "warning": warning_count,
                    "serious_issues": []
                } if not isinstance(serious_issues, list) else {
                    "total_checks": total_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                    "warning": warning_count,
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
                "request_id": request_id,
                "reason": "检测到严重问题，需人工修正后再生成报告",
                "blocking_reasons": blocking_reasons,
                "fix_suggestions": fix_suggestions,
                "partial_data": partial_data,
                "review_summary": {
                    "total_checks": total_checks,
                    "passed": passed_count,
                    "failed": failed_count,
                    "warning": warning_count,
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
        content = await _read_upload_bytes(file)
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            content = await _safe_fetch_url(file_url)
            original_filename = file_url.rstrip("/").split("/")[-1]
            if not original_filename or "." not in original_filename:
                original_filename = "downloaded_file.zip"
            suffix = Path(original_filename).suffix
        except HTTPException:
            raise
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
        project_id = str(uuid.uuid4())
        _store_project(project_id, proj)

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
    warning_by_rule = defaultdict(int)
    failed_by_rule = defaultdict(int)
    for r in review_results:
        if not r.passed:
            failures_by_rule[r.rule_id].append({
                "object": r.check_object,
                "desc": r.error_description,
                "location": r.problem_location
            })
            if _effective_severity(r) in {"error", "fatal"}:
                failed_by_rule[r.rule_id] += 1
            else:
                warning_by_rule[r.rule_id] += 1

    review_summary = {}
    for rule_id, items in failures_by_rule.items():
        review_summary[rule_id] = {
            "total_failures": len(items),
            "warning_count": warning_by_rule[rule_id],
            "failed_count": failed_by_rule[rule_id],
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
    "Excel 工程包": "full_design",
    "QGIS工程": "unknown",
    "未知文件": "unknown",
}

@app.post("/agent/data-pipeline", response_model=DataPipelineResponse)
def data_pipeline(
    file: UploadFile = File(None),
    file_url: Optional[str] = Body(None),
    excel_limit: int = Body(0),
    pdf_chars: int = Body(3000),
    include_tables: bool = Body(False),
    compact: bool = Body(False),
):
    """
    纯数据流水线：不经过 LLM，直接将解析与审查的结构化 JSON 返回。
    供下游 Agent 读取。

    输出契约同时包含：
    - 新契约字段：success, project_name, project_type, summary, review, warnings, errors
    - 旧字段（硬约束）：file_info, layers, review_results, serious_issues_detected, excel_data, pdf_text
    """
    if file is not None:
        original_filename = file.filename
        content = _read_upload_bytes_sync(file)
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            content = _safe_fetch_url_sync(file_url)
            original_filename = file_url.rstrip("/").split("/")[-1]
            if not original_filename or "." not in original_filename:
                original_filename = "downloaded_file.zip"
            suffix = Path(original_filename).suffix
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"下载文件失败: {e}")
    else:
        raise HTTPException(400, "请提供 file 或 file_url")

    cache_key = _pipeline_cache_key(content, original_filename, excel_limit, pdf_chars, include_tables, compact)
    cached = _pipeline_cache_get(cache_key)
    if cached is not None:
        hit = dict(cached)
        hit["request_id"] = uuid.uuid4().hex[:12]
        logger.info(f"[{hit['request_id']}] " + "命中结果缓存" + f": {original_filename}（{len(content)} 字节） project_id={hit['project_id']}")
        return hit

    request_id = uuid.uuid4().hex[:12]
    logger.info(f"[{request_id}] 收到文件: {original_filename}（{len(content)} 字节）")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    archive_path = tmp.name

    project_id = str(uuid.uuid4())

    result = {
        "success": False,
        "request_id": request_id,
        "project_id": project_id,
        "project_name": "",
        "project_type": "unknown",
        "summary": {"layer_count": 0, "object_count": 0},
        "review": {"total_rules": 0, "passed_rules": 0, "failed_rules": 0, "warning_rules": 0, "issues": []},
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
        "business_params": {},
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
            _store_project(project_id, proj)
            result["layers"] = proj.get_layer_info()
            logger.info(f"工程加载完成: {len(result['layers'])} 个图层")
            result["engineering_data"] = {
                "project_id": project_id,
                "project_type": getattr(proj, "project_type", "unknown"),
                "objects": proj.get_engineering_data()["objects"],
            }
            result["business_params"] = load_business_params()
            ctx = RuleContext(proj)  # 复用同一上下文：避免 47+ 规则各自重复扫描全部图层
            try:
                fiber_tables = _collect_fiber_tables(proj)
                if not compact and fiber_tables:
                    result["engineering_data"]["fiber_tables"] = fiber_tables
            except Exception:
                pass
            try:
                from design_parser.rule_engine import build_fiber_assignments
                fa = build_fiber_assignments(ctx)
                if fa:
                    result["engineering_data"]["fiber_assignments"] = fa
            except Exception:
                pass
            if getattr(proj, "is_excel_project", False):
                result["review_scope"] = "non_spatial"
                result["skipped_gis_rules"] = ["R-GIS-001~006", "R-SAFE-001~009", "R010", "R013", "R014", "R015", "R017", "R023", "R025", "R026", "R027", "R028"]
                result["warnings"].append("纯 Excel 工程包：无空间坐标，GIS 空间规则已跳过")
                if any("BOM" in k.upper() and "物料" in k for k in proj.layers):
                    lib_found = any(
                        any(("material" in f.name.lower() or "物料" in f.name or "编码" in f.name)
                            for f in find_excel_files(Path(root), kinds=("bom",)))
                        for root in _project_roots(proj)
                    )
                    if not lib_found:
                        result["warnings"].append("未找到物料编码库（material_code_*/BOM_LIST*），R-BOM-001 使用官方默认物料库兜底")
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
            logger.exception(f"工程数据加载失败: {e}")
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
                    rule_params = {}
                    if rid == "R002":
                        # 部分类别（场勘设计图/Excel 纯表格包）允许缺少部分官方图层：
                        # 只要存在 BOITE 图层就不做强制的全量 8 图层 fatal，避免误报（2026-08-30 补注释，行为未变）
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

                # R-GIS / R-SAFE 专用模块并入主流程（空间/安全规则，结果并入 review.issues）
                if has_gis:
                    try:
                        from design_parser.gis_rules import run_gis_checks
                        from design_parser.safety_rules import run_safety_checks
                        _sev_map = {"致命": "fatal", "高": "error", "中": "warning"}
                        for mod_issues in (run_gis_checks(proj)["issues"], run_safety_checks(proj)["issues"]):
                            for iss in mod_issues:
                                all_results.append(CheckResult(
                                    check_object=str(iss.get("object_type") or ""),
                                    passed=False,
                                    problem_location=str(iss.get("object_id") or ""),
                                    actual_value="",
                                    expected_value="",
                                    rule_id=str(iss.get("rule_id") or ""),
                                    error_description=str(iss.get("message") or ""),
                                    severity=_sev_map.get(str(iss.get("severity") or ""), "warning"),
                                ))
                    except Exception:
                        pass

                # 严重等级按官方知识库v2.0 对齐（SEVERITY_MAP：致命/高/中 → fatal/error/warning）
                _normalize_severities(all_results)
                review_results_out = [CheckResultOut(**r.model_dump()).model_dump() for r in all_results]
                result["review_results"] = review_results_out

                # P0-01：warning 不计入 failed_rules，按严重等级统计
                _stats = _severity_counts(all_results)
                total_rules = _stats["total_rules"]
                passed_rules = _stats["passed_rules"]
                failed_rules = _stats["failed_rules"]
                warning_rules = _stats["warning_rules"]
                eng_objects = (result.get("engineering_data") or {}).get("objects") or {}
                code_lookup = {}
                for obj_key, items in eng_objects.items():
                    for item in items:
                        code = item.get("code")
                        if code:
                            code_lookup[str(code).upper()] = item.get("id") or f"{obj_key}:{code}"
                codes_sorted = sorted(code_lookup.keys(), key=len, reverse=True)
                issues = []
                for r in all_results:
                    if not r.passed:
                        obj_ref = ""
                        if codes_sorted:
                            haystack = " ".join(str(x or "") for x in (r.check_object, r.error_description)).upper()
                            for code in codes_sorted:
                                if code in haystack:
                                    obj_ref = code_lookup[code]
                                    break
                        cat_key = problem_category_for(r.rule_id)
                        issues.append({
                            "rule_id": r.rule_id,
                            "object_type": r.check_object,
                            "object_id": r.problem_location or "",
                            "object_ref": obj_ref,
                            "passed": r.passed,
                            "actual_value": r.actual_value or "",
                            "expected_value": r.expected_value or "",
                            "field": "",
                            "severity": r.severity or "warning",
                            "message": r.error_description or "",
                            "source": "rule_engine",
                            "problem_category": cat_key,
                            "problem_category_label": CATEGORY_LABELS.get(cat_key, cat_key),
                        })
                categories = {}
                for iss in issues:
                    key = iss["problem_category"]
                    entry = categories.get(key)
                    if entry is None:
                        entry = {"label": iss["problem_category_label"], "count": 0}
                        categories[key] = entry
                    entry["count"] += 1
                result["review"] = {
                    "total_rules": total_rules,
                    "warning_rules": warning_rules,
                    "rule_count": len(rule_ids) + (18 if has_gis else 0),  # 覆盖规则数：引擎路由 + GIS6 + SAFE12（total_rules 仍为检查项数）
                    "passed_rules": passed_rules,
                    "failed_rules": failed_rules,
                    "categories": categories,
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
        _rule_dist = {}
        for _iss in (result.get("review") or {}).get("issues") or []:
            _rule_dist[_iss["rule_id"]] = _rule_dist.get(_iss["rule_id"], 0) + 1
        logger.info(
            f"规则审查完成: {result['review']['passed_rules']}/{result['review']['total_rules']} 通过，"
            f"{result['review']['failed_rules']} 失败；问题分布: "
            + ", ".join(f"{k}={v}" for k, v in sorted(_rule_dist.items()))
        )

        try:
            if excel_limit > 0:
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
            pkg = getattr(proj, "package", None)  # 复用已解压包，避免重复解压
            pdf_paths = list(pkg.temp_dir.rglob("*.pdf")) if pkg is not None else []
            pdf_text = {}
            for fp in pdf_paths:
                try:
                    full = extract_text_from_pdf(str(fp))
                    pdf_text[fp.name] = full[:pdf_chars]
                except Exception as e:
                    pdf_text[fp.name] = f"提取失败: {e}"
            result["pdf_text"] = pdf_text
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
        if compact:
            result["excel_data"] = {}
            result["engineering_data"].pop("fiber_tables", None)
            result["review_results"] = []
            result["pdf_text"] = {}
            result["bom_tables"] = {}
            result["fiber_tables"] = {}
        logger.info(
            f"[{request_id}] 流水线完成: project_id={project_id} success={result['success']} "
            f"图层={result['summary']['layer_count']} 对象={result['summary']['object_count']}"
        )

    except Exception as e:
        logger.exception(f"数据流水线全局异常: {e}")
        result["status"] = "error"
        result["success"] = False
        result["errors"].append(str(e))
    finally:
        Path(archive_path).unlink(missing_ok=True)
        # 保留解压文件供 project_id 后续接口（bom/fiber/table-data 等）取数；
        # 过期项目由 _store_project 的 TTL 清理临时文件，避免无限堆积。

    if result.get("success"):
        _pipeline_cache_put(cache_key, result)
    return result

@app.post("/agent/orchestrate")
async def orchestrate(
    file: UploadFile = File(None),
    file_url: Optional[str] = Body(None)
):
    """总控 Agent：文件识别→审查→文档理解→决策→BOM/纤芯→综合报告"""
    request_id = uuid.uuid4().hex[:12]
    if file is not None:
        original_filename = file.filename
        content = await _read_upload_bytes(file)
        suffix = Path(original_filename).suffix
    elif file_url is not None:
        try:
            content = await _safe_fetch_url(file_url)
            original_filename = file_url.rstrip("/").split("/")[-1]
            if not original_filename or "." not in original_filename:
                original_filename = "downloaded_file.zip"
            suffix = Path(original_filename).suffix
        except HTTPException:
            raise
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
        project_id = str(uuid.uuid4())
        _store_project(project_id, proj)

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
            warning_by_rule = defaultdict(int)
            failed_by_rule = defaultdict(int)
            serious_issue_list = []
            for r in results:
                if not r.passed:
                    failures_by_rule[r.rule_id].append({
                        "object": r.check_object,
                        "desc": r.error_description,
                        "location": r.problem_location
                    })
                    if _effective_severity(r) in {"error", "fatal"}:
                        failed_by_rule[r.rule_id] += 1
                    else:
                        warning_by_rule[r.rule_id] += 1
            review_summary = {}
            for rid, items in failures_by_rule.items():
                review_summary[rid] = {
                    "total_failures": len(items),
                    "warning_count": warning_by_rule[rid],
                    "failed_count": failed_by_rule[rid],
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
                "failed_count": sum(v["failed_count"] for v in review_summary.values()),
                "warning_count": sum(v["warning_count"] for v in review_summary.values())
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
                rid = issue.get("rule_id", "未知")
                obj = issue.get("check_object", "未知")
                desc = issue.get("error_description", "未知")
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
            "request_id": request_id,
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
