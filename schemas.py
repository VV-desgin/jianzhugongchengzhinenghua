from pydantic import BaseModel, Field
from typing import List, Optional, Any
from enum import Enum
from pydantic import BaseModel
from typing import List, Optional

class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[Any] = None  # 字符串或结构化 {code, message}

class LayerInfo(BaseModel):
    layer_name: str
    geometry_type: str
    fields: List[tuple]   # [(name, type)]
    feature_count: int

class CheckResultOut(BaseModel):
    check_object: str
    passed: bool
    problem_location: Optional[str] = None
    actual_value: Optional[str] = None
    expected_value: Optional[str] = None
    rule_id: str
    error_description: Optional[str] = None
    severity: Optional[str] = None

class RunRulesRequest(BaseModel):
    rule_ids: Optional[List[str]] = None   # None 或空列表表示全部
    params: Optional[dict] = None           # 规则参数，如 {"R002": {"required_layers": ["boite"]}}

class CableLength(BaseModel):
    cable_id: str
    length: Optional[float] = None
    unit: str = "meters"

class DeviceCount(BaseModel):
    total_devices: int
    by_layer: dict   # {"boite": 2, ...}

class FileInfo(BaseModel):
    filename: str
    size_bytes: int
    mime_type: Optional[str] = None

class InspectResponse(BaseModel):
    file_name: str
    is_archive: bool
    archive_type: Optional[str] # zip, rar, qgz 等
    files_inside: Optional[List[FileInfo]] = None
    file_category: Optional[str] = None  # 场勘设计图/完整设计图/竣工图/...
    missing_shp_parts: Optional[List[str]] = None  # 若为 SHP 相关，缺少的配套文件
    can_be_parsed: bool
    message: str

class ShpCheckResponse(BaseModel):
    is_valid: bool
    missing_files: List[str]
    message: str

class HealthResponse(BaseModel):
    """GET /health 健康检查响应。"""
    status: str

class DataPipelineResponse(BaseModel):
    """POST /agent/data-pipeline 响应契约（含 request_id 对账字段）。"""
    success: bool
    request_id: str
    project_id: str
    project_name: str
    project_type: str
    summary: dict
    review: dict
    warnings: list
    errors: list
    status: str
    file_info: dict
    layers: list
    review_results: list
    serious_issues_detected: bool
    excel_data: dict
    pdf_text: dict
    engineering_data: dict
    bom_tables: Optional[dict] = None
    fiber_tables: Optional[dict] = None
    review_scope: Optional[str] = None
    skipped_gis_rules: Optional[list] = None
    review_message: Optional[str] = None
